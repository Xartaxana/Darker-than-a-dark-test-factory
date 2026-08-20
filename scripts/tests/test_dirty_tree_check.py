"""Юнит-тесты pre_step dirty_tree_check (scripts/dirty_tree_check.py).

Поведенческие тесты (git status/mtime/фильтр/WARN-блок/orchestrator-log) —
на РЕАЛЬНОМ временном git-репо (tmp_path: git init, коммит, порча), НЕ на
замоканном тексте, как требует спека. Низкоуровневый парсер -z (`parse_
porcelain_z`) дополнительно бьётся напрямую сконструированными байтовыми
потоками — адверсариальные пункты (пустое имя-мусор, оборванный rename)
недостижимы через реальный git штатно, только инъекцией.

conftest.py директории уже кладёт scripts/ на sys.path (см. header).
"""
from __future__ import annotations

import datetime as dt
import os
import subprocess
import sys
from pathlib import Path

import pytest

import dirty_tree_check as dtc
import log_append as la


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    p = subprocess.run(["git"] + args, cwd=str(cwd), capture_output=True,
                        text=True, encoding="utf-8", errors="replace")
    assert p.returncode == 0, f"git {args} failed: {p.stdout}\n{p.stderr}"
    return p


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(["init", "-q"], root)
    _git(["config", "user.email", "test@example.com"], root)
    _git(["config", "user.name", "Test"], root)
    (root / "state").mkdir()
    return root


def _commit_initial(root: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    _git(["add", "-A"], root)
    _git(["commit", "-q", "-m", "init"], root)


NOW = dt.datetime(2026, 8, 20, 12, 0, 0, tzinfo=dt.timezone.utc)


def _touch_mtime(path: Path, when: dt.datetime) -> None:
    ts = when.timestamp()
    os.utime(path, (ts, ts))


@pytest.fixture(autouse=True)
def _no_real_orchestrator_log(monkeypatch, repo, tmp_path):
    """Оркестратор-лог — на временный файл ВНУТРИ временного репо (не в
    живой state/): log_append.append_orchestrator читает module-level
    ORCH_LOG напрямую (та же ссылка, что append_routing/main использует),
    монкипатч этой ссылки — штатный способ теста (см. test_log_append.py).
    _verify_environment пройдёт сам по себе: repo/state уже существует и
    repo — настоящий git-репозиторий (git init в фикстуре `repo`)."""
    orch = repo / "state" / "orchestrator-log.md"
    monkeypatch.setattr(la, "ORCH_LOG", orch, raising=True)
    return orch


# --------------------------------------------------------------------------
# (а) чистое дерево
# --------------------------------------------------------------------------

def test_clean_tree(repo):
    _commit_initial(repo, {"a.txt": "hello\n"})
    report = dtc.build_report(repo, now=NOW)
    assert report == "dirty_tree_check: чисто"


def test_clean_tree_no_orchestrator_write(repo, _no_real_orchestrator_log):
    _commit_initial(repo, {"a.txt": "hello\n"})
    dtc.build_report(repo, now=NOW)
    assert not _no_real_orchestrator_log.exists()


# --------------------------------------------------------------------------
# (б) modified tracked
# --------------------------------------------------------------------------

def test_modified_tracked_file_older_bucket(repo):
    _commit_initial(repo, {"a.txt": "hello\n"})
    p = repo / "a.txt"
    p.write_text("changed\n", encoding="utf-8")
    _touch_mtime(p, NOW - dt.timedelta(hours=2))

    report = dtc.build_report(repo, now=NOW)

    assert "[WARN]" in report
    assert "a.txt" in report
    assert "Старше (вероятный leftover" in report
    older_section = report.split("Старше")[1]
    assert "a.txt" in older_section


def test_modified_tracked_file_recent_bucket(repo):
    _commit_initial(repo, {"a.txt": "hello\n"})
    p = repo / "a.txt"
    p.write_text("changed\n", encoding="utf-8")
    _touch_mtime(p, NOW - dt.timedelta(minutes=1))

    report = dtc.build_report(repo, now=NOW)

    assert "Изменено < 10 мин назад" in report
    recent_section = report.split("Изменено < 10 мин назад")[1]
    assert "a.txt" in recent_section.split("Старше")[0]


def test_deleted_tracked_file(repo):
    _commit_initial(repo, {"a.txt": "hello\n"})
    (repo / "a.txt").unlink()

    report = dtc.build_report(repo, now=NOW)

    assert "Удалено (mtime недоступен)" in report
    assert "a.txt" in report
    assert "deleted" in report


# --------------------------------------------------------------------------
# (в) untracked файл и схлопнутая untracked-директория
# --------------------------------------------------------------------------

def test_untracked_file(repo):
    _commit_initial(repo, {"a.txt": "hello\n"})
    p = repo / "leftover.txt"
    p.write_text("junk\n", encoding="utf-8")
    _touch_mtime(p, NOW - dt.timedelta(hours=5))

    report = dtc.build_report(repo, now=NOW)

    assert "leftover.txt" in report
    assert "Старше" in report


def test_untracked_directory_collapsed(repo):
    _commit_initial(repo, {"a.txt": "hello\n"})
    d = repo / "leftover_dir"
    d.mkdir()
    (d / "inner.txt").write_text("junk\n", encoding="utf-8")

    report = dtc.build_report(repo, now=NOW)

    # git схлопывает целиком untracked-директорию в одну запись "leftover_dir/"
    assert "leftover_dir/" in report
    assert "inner.txt" not in report


# --------------------------------------------------------------------------
# (г) rename R-строка
# --------------------------------------------------------------------------

def test_rename_reported(repo):
    _commit_initial(repo, {"old.txt": "content\n"})
    _git(["mv", "old.txt", "new.txt"], repo)

    entries = dtc.collect_dirty_entries(repo)
    assert entries is not None
    rename_entries = [e for e in entries if e[0] == "R" or e[1] == "R"]
    assert len(rename_entries) == 1
    x, y, path, orig_path = rename_entries[0]
    assert path == "new.txt"
    assert orig_path == "old.txt"

    report = dtc.build_report(repo, now=NOW)
    # F3 (критик-фикс): rename показывает "старый -> новый", не только новый путь
    assert "old.txt -> new.txt" in report


# --------------------------------------------------------------------------
# (д) не-ASCII (кириллическое) имя файла
# --------------------------------------------------------------------------

def test_cyrillic_filename(repo):
    _commit_initial(repo, {"a.txt": "hello\n"})
    p = repo / "кириллица.txt"
    p.write_text("junk\n", encoding="utf-8")
    _touch_mtime(p, NOW - dt.timedelta(hours=1))

    report = dtc.build_report(repo, now=NOW)

    assert "кириллица.txt" in report
    # НЕ октальные эскейпы (доказательство, что -z, не голый --porcelain)
    assert "\\320" not in report


def test_filename_with_space(repo):
    _commit_initial(repo, {"a.txt": "hello\n"})
    p = repo / "d e.txt"
    p.write_text("junk\n", encoding="utf-8")
    _touch_mtime(p, NOW - dt.timedelta(hours=1))

    report = dtc.build_report(repo, now=NOW)
    assert "d e.txt" in report


# --------------------------------------------------------------------------
# (е) фильтр scratchpad/ по префиксу
# --------------------------------------------------------------------------

def test_scratchpad_filtered_out(repo):
    _commit_initial(repo, {"a.txt": "hello\n"})
    sp = repo / "scratchpad"
    sp.mkdir()
    (sp / "tmp.txt").write_text("junk\n", encoding="utf-8")

    report = dtc.build_report(repo, now=NOW)

    assert report == "dirty_tree_check: чисто"


def test_scratchpad_filtered_alongside_real_leftover(repo):
    _commit_initial(repo, {"a.txt": "hello\n"})
    sp = repo / "scratchpad"
    sp.mkdir()
    (sp / "tmp.txt").write_text("junk\n", encoding="utf-8")
    real = repo / "leftover.txt"
    real.write_text("junk\n", encoding="utf-8")
    _touch_mtime(real, NOW - dt.timedelta(hours=1))

    report = dtc.build_report(repo, now=NOW)

    assert "tmp.txt" not in report
    assert "scratchpad/tmp.txt" not in report
    assert "leftover.txt" in report


def test_scratchpad_prefix_not_substring(repo):
    """Проверка на ложное совпадение: 'scratchpad_evil/' НЕ начинается с
    'scratchpad/' (нет разделителя) — должен НЕ фильтроваться."""
    _commit_initial(repo, {"a.txt": "hello\n"})
    d = repo / "scratchpad_evil"
    d.mkdir()
    (d / "x.txt").write_text("junk\n", encoding="utf-8")

    report = dtc.build_report(repo, now=NOW)
    assert "scratchpad_evil" in report


# --------------------------------------------------------------------------
# (ж) отказ git — несуществующий cwd / подмена PATH → exit 0 + WARN
# --------------------------------------------------------------------------

def test_git_failure_nonexistent_cwd(tmp_path):
    missing = tmp_path / "does_not_exist"
    report = dtc.build_report(missing, now=NOW, log_orchestrator=False)
    assert "[WARN]" in report
    assert "деградировал" in report


def test_git_failure_not_a_repo(tmp_path):
    not_repo = tmp_path / "plain_dir"
    not_repo.mkdir()
    report = dtc.build_report(not_repo, now=NOW, log_orchestrator=False)
    assert "[WARN]" in report
    assert "деградировал" in report


def test_git_failure_path_override(monkeypatch, repo):
    """git-бинарник недостижим (PATH подменён на путь без git) —
    FileNotFoundError внутри subprocess.run, деградация, не падение."""
    monkeypatch.setenv("PATH", str(repo))  # пустая директория, git там нет
    report = dtc.build_report(repo, now=NOW, log_orchestrator=False)
    assert "[WARN]" in report
    assert "деградировал" in report


def test_main_exit_code_always_zero_on_git_failure(monkeypatch, tmp_path, capsys):
    missing = tmp_path / "nope"
    rc = dtc.main(["--repo", str(missing)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "[WARN]" in out


def test_main_exit_code_zero_on_dirty_tree(repo, capsys):
    _commit_initial(repo, {"a.txt": "hello\n"})
    (repo / "leftover.txt").write_text("junk\n", encoding="utf-8")
    rc = dtc.main(["--repo", str(repo)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "[WARN]" in out
    assert "leftover.txt" in out


# --------------------------------------------------------------------------
# (з) усечение длинного перечня — граница TRUNCATE_AFTER=30 (правило 6а: тест
# НА границе и ЗА ней)
# --------------------------------------------------------------------------

def test_truncation_boundary_exactly_30_no_truncation_marker(repo):
    _commit_initial(repo, {"a.txt": "hello\n"})
    for i in range(30):
        p = repo / f"leftover_{i:02d}.txt"
        p.write_text("junk\n", encoding="utf-8")
        _touch_mtime(p, NOW - dt.timedelta(hours=1))

    report = dtc.build_report(repo, now=NOW)

    assert "и ещё" not in report
    for i in range(30):
        assert f"leftover_{i:02d}.txt" in report


def test_truncation_boundary_31_triggers_marker(repo):
    _commit_initial(repo, {"a.txt": "hello\n"})
    for i in range(31):
        p = repo / f"leftover_{i:02d}.txt"
        p.write_text("junk\n", encoding="utf-8")
        _touch_mtime(p, NOW - dt.timedelta(hours=1))

    report = dtc.build_report(repo, now=NOW)

    assert "... и ещё 1" in report


def test_truncation_priority_older_survives_large_recent_slice(repo):
    """B1 (критик-фикс): recent-срез БОЛЬШЕ бюджета (> TRUNCATE_AFTER) не
    должен вытеснять older -- older печатается ПЕРВЫМ и обязан остаться
    видимым в отчёте вместе с заголовком секции "Старше", даже когда
    recent один способен исчерпать весь бюджет."""
    _commit_initial(repo, {"a.txt": "hello\n"})
    # older: ровно 1 файл, явный leftover-кандидат
    older_path = repo / "leftover_older.txt"
    older_path.write_text("junk\n", encoding="utf-8")
    _touch_mtime(older_path, NOW - dt.timedelta(hours=1))
    # recent: 40 файлов (> TRUNCATE_AFTER=30) -- раньше единолично съедали весь бюджет
    for i in range(40):
        p = repo / f"recent_{i:02d}.txt"
        p.write_text("junk\n", encoding="utf-8")
        _touch_mtime(p, NOW - dt.timedelta(minutes=1))

    report = dtc.build_report(repo, now=NOW)

    assert "Старше (вероятный leftover" in report
    older_section = report.split("Старше")[1]
    # секция "Изменено < 10 мин" (если присутствует) идёт ПОСЛЕ "Старше" по
    # новому порядку -- older_section может содержать и recent-заголовок
    # дальше по тексту, поэтому проверяем leftover_older.txt именно в куске
    # ДО следующего заголовка recent (или до конца, если recent не влез).
    older_only = older_section.split("Изменено <")[0]
    assert "leftover_older.txt" in older_only


def test_truncation_many_over_limit(repo):
    _commit_initial(repo, {"a.txt": "hello\n"})
    for i in range(45):
        p = repo / f"leftover_{i:02d}.txt"
        p.write_text("junk\n", encoding="utf-8")
        _touch_mtime(p, NOW - dt.timedelta(hours=1))

    report = dtc.build_report(repo, now=NOW)
    assert "... и ещё 15" in report


# --------------------------------------------------------------------------
# Граница LIVE_WRITER_THRESHOLD_MINUTES=10 (правило 6а)
# --------------------------------------------------------------------------

def test_recency_boundary_just_under_10min_is_recent(repo):
    _commit_initial(repo, {"a.txt": "hello\n"})
    p = repo / "edge.txt"
    p.write_text("junk\n", encoding="utf-8")
    _touch_mtime(p, NOW - dt.timedelta(minutes=9, seconds=59))

    report = dtc.build_report(repo, now=NOW)
    recent_section = report.split("Изменено < 10 мин назад")[1].split("Старше")[0]
    assert "edge.txt" in recent_section


def test_recency_boundary_exactly_10min_is_older(repo):
    _commit_initial(repo, {"a.txt": "hello\n"})
    p = repo / "edge.txt"
    p.write_text("junk\n", encoding="utf-8")
    _touch_mtime(p, NOW - dt.timedelta(minutes=10))

    report = dtc.build_report(repo, now=NOW)
    assert "Старше" in report
    older_section = report.split("Старше")[1]
    assert "edge.txt" in older_section
    # единственная запись -- ровно на границе 10 мин, значит recent-бакет
    # пуст, и его заголовок вовсе не печатается (emit_section пропускает
    # пустые секции) -- это и есть доказательство "не в recent".
    assert "Изменено < 10 мин назад" not in report


def test_recency_boundary_just_over_10min_is_older(repo):
    _commit_initial(repo, {"a.txt": "hello\n"})
    p = repo / "edge.txt"
    p.write_text("junk\n", encoding="utf-8")
    _touch_mtime(p, NOW - dt.timedelta(minutes=10, seconds=1))

    report = dtc.build_report(repo, now=NOW)
    older_section = report.split("Старше")[1]
    assert "edge.txt" in older_section


# --------------------------------------------------------------------------
# orchestrator-log — реальная запись через канонический механизм
# --------------------------------------------------------------------------

def test_orchestrator_log_written_via_canonical_mechanism(repo, _no_real_orchestrator_log):
    _commit_initial(repo, {"a.txt": "hello\n"})
    (repo / "leftover.txt").write_text("junk\n", encoding="utf-8")

    dtc.build_report(repo, now=NOW)

    orch = _no_real_orchestrator_log
    assert orch.exists()
    text = orch.read_text(encoding="utf-8")
    assert "pre_step dirty_tree_check" in text
    assert "dirty_tree_check.py" in text
    # формат таблицы -- та же функция, что и у остальных pre_steps
    assert text.startswith("|")


def test_orchestrator_log_reuses_append_orchestrator_not_duplicated(repo, monkeypatch):
    """Спека требует переиспользовать log_append.append_orchestrator ИМПОРТОМ,
    не дублировать формат — проверяем, что вызов реально идёт через неё
    (monkeypatch на саму функцию, не на файл)."""
    _commit_initial(repo, {"a.txt": "hello\n"})
    (repo / "leftover.txt").write_text("junk\n", encoding="utf-8")

    calls = []
    monkeypatch.setattr(la, "append_orchestrator",
                        lambda cells: calls.append(cells) or "stub-line", raising=True)
    # dirty_tree_check импортирует модуль log_append целиком и вызывает
    # log_append.append_orchestrator(...) -- патч атрибута модуля видим ему.
    dtc.build_report(repo, now=NOW)

    assert len(calls) == 1
    assert len(calls[0]) == 4


def test_orchestrator_log_write_failure_does_not_crash(repo, monkeypatch):
    """Сбой канонического механизма (напр. _verify_environment отказал) не
    должен ронять детектор -- код выхода всё равно 0, WARN уже напечатан."""
    _commit_initial(repo, {"a.txt": "hello\n"})
    (repo / "leftover.txt").write_text("junk\n", encoding="utf-8")

    def _boom(cells):
        raise SystemExit("деплой не распознан")
    monkeypatch.setattr(la, "append_orchestrator", _boom, raising=True)

    report = dtc.build_report(repo, now=NOW)  # не должно бросить исключение
    assert "[WARN]" in report


def test_orchestrator_log_write_failure_visible_in_report(repo, monkeypatch):
    """F1 (критик-фикс): сбой записи -- НЕ тихий проглот, отчёт несёт
    видимую строку с причиной ('строка в orchestrator-log НЕ записана: ...'),
    а не просто [WARN] без упоминания сбоя журнала."""
    _commit_initial(repo, {"a.txt": "hello\n"})
    (repo / "leftover.txt").write_text("junk\n", encoding="utf-8")

    def _boom(cells):
        raise SystemExit("деплой не распознан: тестовый отказ")
    monkeypatch.setattr(la, "append_orchestrator", _boom, raising=True)

    report = dtc.build_report(repo, now=NOW)

    assert "строка в orchestrator-log НЕ записана:" in report
    assert "деплой не распознан: тестовый отказ" in report


def test_orchestrator_log_address_follows_repo_param(monkeypatch, repo, tmp_path):
    """F2 (критик-фикс): адрес журнала = <--repo>/state/orchestrator-log.md,
    НЕ module-level log_append.ORCH_LOG (унаследованный от расположения
    log_append.py, не от --repo вызова). Декой-путь заведомо НЕ совпадает
    ни с одним из двух проверяемых репозиториев -- если бы адрес не был
    завязан на `repo`-параметр, запись ушла бы в декой (или молчаливо не
    туда) вместо repo/repo_b, каждый своей строкой в СВОЁМ файле."""
    decoy = tmp_path / "decoy" / "orchestrator-log.md"
    monkeypatch.setattr(la, "ORCH_LOG", decoy, raising=True)

    _commit_initial(repo, {"a.txt": "hello\n"})
    (repo / "leftover_a.txt").write_text("junk\n", encoding="utf-8")

    repo_b = tmp_path / "repo_b"
    repo_b.mkdir()
    _git(["init", "-q"], repo_b)
    _git(["config", "user.email", "test@example.com"], repo_b)
    _git(["config", "user.name", "Test"], repo_b)
    (repo_b / "state").mkdir()
    _commit_initial(repo_b, {"b.txt": "hello\n"})
    (repo_b / "leftover_b.txt").write_text("junk\n", encoding="utf-8")

    dtc.build_report(repo, now=NOW)
    dtc.build_report(repo_b, now=NOW)

    assert not decoy.exists()
    a_log = repo / "state" / "orchestrator-log.md"
    b_log = repo_b / "state" / "orchestrator-log.md"
    assert a_log.exists()
    assert b_log.exists()
    assert "путей" in a_log.read_text(encoding="utf-8")
    assert "путей" in b_log.read_text(encoding="utf-8")
    # module-level константа восстановлена после обоих вызовов (finally) --
    # не осталась в чужом состоянии для следующего вызова процесса.
    assert la.ORCH_LOG == decoy


def test_orchestrator_log_write_success_no_failure_line(repo):
    """Негативный контроль к предыдущему тесту: при УСПЕШНОЙ записи строка
    отказа отсутствует вовсе (F-34: позитивный контроль той же формы)."""
    _commit_initial(repo, {"a.txt": "hello\n"})
    (repo / "leftover.txt").write_text("junk\n", encoding="utf-8")

    report = dtc.build_report(repo, now=NOW)

    assert "строка в orchestrator-log НЕ записана" not in report


# --------------------------------------------------------------------------
# Низкоуровневый парсер -z: адверсариальные инъекции (недостижимо через
# реальный git штатно)
# --------------------------------------------------------------------------

def test_parse_porcelain_z_empty_garbage_tokens():
    # Двойной NUL создаёт пустой токен между записями; короткие мусорные
    # токены не должны ронять парсер и не должны становиться записями.
    raw = "M  a.txt\0\0?? b.txt\0"
    entries = dtc.parse_porcelain_z(raw)
    paths = [e[2] for e in entries]
    assert paths == ["a.txt", "b.txt"]


def test_parse_porcelain_z_truncated_rename_stream():
    # R-запись без следующего NUL-поля (поток оборван посреди rename) —
    # orig_path остаётся None, парсер не падает и не глотает лишнее.
    raw = "R  new.txt"
    entries = dtc.parse_porcelain_z(raw)
    assert entries == [("R", " ", "new.txt", None)]


def test_parse_porcelain_z_rename_with_empty_orig_path_token():
    # orig_path-поле присутствует, но пустое -- не поглощается как orig_path
    # (иначе следующая запись потеряется), остаётся None.
    raw = "R  new.txt\0\0?? c.txt\0"
    entries = dtc.parse_porcelain_z(raw)
    assert entries[0] == ("R", " ", "new.txt", None)
    paths = [e[2] for e in entries]
    assert "c.txt" in paths


def test_parse_porcelain_z_only_header_no_path():
    raw = "M  \0?? real.txt\0"
    entries = dtc.parse_porcelain_z(raw)
    paths = [e[2] for e in entries]
    assert paths == ["real.txt"]


def test_parse_porcelain_z_empty_input():
    assert dtc.parse_porcelain_z("") == []


def test_parse_porcelain_z_real_rename_format():
    # Эмпирически снятый формат (scratchpad-эксперимент этого прохода,
    # git-bash на Windows): "R  b.txt\0a.txt\0"
    raw = "R  b.txt\0a.txt\0"
    entries = dtc.parse_porcelain_z(raw)
    assert entries == [("R", " ", "b.txt", "a.txt")]
