"""Юнит-тесты gitlab_inbound (scripts/gitlab_inbound.py).

Device-free и network-free: сетевой транспорт GitLabClient подменяется
FakeTransport (тот же паттерн, что scripts/tests/test_gitlab_sync.py, локальная
копия — изоляция файлов теста друг от друга) — ни один тест не обращается к
реальной сети/gitlab.com. Артефакты — во временном bugs_dir (env fixture),
реальные bugs/*.md репозитория и state/gitlab-cursor.json/escalations.md НЕ
читаются и НЕ пишутся.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import board_inbound as bi
import gitlab_inbound as gi
import gitlab_sync as gs


# --- Фикстуры -----------------------------------------------------------

class FakeTransport:
    """Заменяет сетевой вызов GitLabClient. responses — список
    (status, body) в порядке ожидаемых вызовов; body — dict/list (сериализуется
    в JSON) либо bytes/str."""

    def __init__(self, responses):
        self.calls: list[dict] = []
        self._responses = list(responses)

    def __call__(self, method, url, headers, data):
        self.calls.append({
            "method": method, "url": url, "headers": dict(headers),
            "json": json.loads(data) if data else None,
        })
        if not self._responses:
            raise AssertionError(f"FakeTransport: неожиданный вызов {method} {url}")
        status, body = self._responses.pop(0)
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        return status, body


def _client(responses) -> tuple[gs.GitLabClient, FakeTransport]:
    transport = FakeTransport(responses)
    client = gs.GitLabClient(
        "https://gitlab.com/api/v4/projects/Xartaxana1%2Fao3-wrapper",
        "tok-123", transport=transport)
    return client, transport


def _note(note_id, *, system=False, username="dev",
         created="2026-08-09T10:00:00Z", body="Текст ноты.") -> dict:
    return {"id": note_id, "system": system,
            "author": {"username": username}, "created_at": created, "body": body}


def _write_bug(dir_: Path, bug_id: str, *, title="Заголовок бага",
               severity="major", status="Open", gitlab_issue=1,
               discussion: str = "", checklist: bool = False,
               eol: str = "\n", extra: str = "") -> Path:
    front = (
        f"---{eol}"
        f"id: {bug_id}{eol}"
        f'title: "{title}"{eol}'
        f"severity: {severity}{eol}"
        f"status: {status}{eol}"
        f"gitlab_issue: {gitlab_issue}{eol}"
        f"{extra}"
        f'updated: "2026-08-01T00:00:00Z"{eol}'
        f"---{eol}"
    )
    parts = [f"{eol}# Заголовок{eol}{eol}Тело описания бага.{eol}"]
    if discussion is not None:
        parts.append(f"{eol}## Обсуждение{eol}")
        if discussion:
            parts.append(f"{eol}{discussion}{eol}")
    if checklist:
        parts.append(f"{eol}## Чек-лист качества{eol}- [ ] пункт{eol}")
    text = front + "".join(parts)
    p = dir_ / f"{bug_id}.md"
    p.write_bytes(text.encode("utf-8"))
    return p


@pytest.fixture()
def env(tmp_path, monkeypatch):
    bugs_dir = tmp_path / "bugs"
    bugs_dir.mkdir()
    monkeypatch.setattr(gs, "BUGS_DIR", bugs_dir, raising=True)
    aut = tmp_path / "state" / "app-under-test.yaml"
    aut.parent.mkdir(parents=True, exist_ok=True)
    aut.write_text(
        "app: ao3-wrapper\nrepo: https://gitlab.com/Xartaxana1/ao3-wrapper\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(gs, "AUT_PATH", aut, raising=True)
    monkeypatch.setattr(gi, "REPO", tmp_path, raising=True)
    monkeypatch.setattr(gi, "CURSOR_PATH", tmp_path / "state" / "gitlab-cursor.json",
                        raising=True)
    monkeypatch.setattr(bi, "ESCALATIONS_PATH", tmp_path / "state" / "escalations.md",
                        raising=True)
    return bugs_dir


def _selected(bugs_dir):
    return gi.select_bugs(gs.discover_bugs())


# --- select_bugs: is_app_bug ∧ ¬is_seeded ∧ gitlab_issue --------------------

def test_select_bugs_filters_seeded_missing_issue_and_test_debt(env):
    _write_bug(env, "BUG-001", gitlab_issue=1)
    _write_bug(env, "BUG-002", gitlab_issue="")          # нет issue — не выбран
    _write_bug(env, "BUG-003", gitlab_issue=3, extra='seeded: "true"\n')
    (env / "AT-BUG-004.md").write_text(
        '---\nid: AT-BUG-004\ntitle: "долг"\nseverity: minor\nstatus: Open\n'
        'type: test_debt\ngitlab_issue: 4\nupdated: "2026-08-01T00:00:00Z"\n---\n\nтело\n',
        encoding="utf-8")

    selected = _selected(env)
    ids = [bug_id for _p, bug_id, _iid, _s in selected]
    assert ids == ["BUG-001"]


# --- Базовые: вставка в секцию, awaiting, updated, курсор -------------------

def test_new_note_lands_in_discussion_section_before_checklist(env):
    p = _write_bug(env, "BUG-010", status="Open", gitlab_issue=10, checklist=True)
    client, transport = _client([(200, [_note(100, body="Привет из GitLab")])])

    summary = gi.run(client, _selected(env), dry=False)

    assert summary["written_total"] == 1
    assert summary["written_bugs"] == ["BUG-010"]
    text = p.read_text(encoding="utf-8")
    assert "**[gitlab:dev @ 2026-08-09T10:00:00Z]** > Привет из GitLab" in text
    assert "awaiting: qa" in text
    disc_i = text.index("## Обсуждение")
    replica_i = text.index("**[gitlab:dev")
    checklist_i = text.index("## Чек-лист качества")
    assert disc_i < replica_i < checklist_i, "реплика обязана быть В секции, не в EOF после чек-листа"
    assert len(transport.calls) == 1

    cursor = gi.load_cursor()
    assert cursor.get("BUG-010") == 100


# --- Ранний выход по курсору: note.id <= cursor — пропуск, 1 GET -----------

def test_note_id_leq_cursor_is_skipped_early_exit(env):
    p = _write_bug(env, "BUG-011", gitlab_issue=11)
    gi._bump_cursor("BUG-011", 50)
    client, transport = _client([(200, [_note(50)])])

    summary = gi.run(client, _selected(env), dry=False)

    assert summary["written_total"] == 0
    assert len(transport.calls) == 1
    assert "**[" not in p.read_text(encoding="utf-8")


def test_second_run_is_idempotent_via_cursor(env):
    p = _write_bug(env, "BUG-012", gitlab_issue=12)
    client1, _t1 = _client([(200, [_note(100)])])
    gi.run(client1, _selected(env), dry=False)
    assert p.read_text(encoding="utf-8").count("**[gitlab:dev") == 1

    client2, transport2 = _client([(200, [_note(100)])])  # та же нота всё ещё видна GitLab
    summary2 = gi.run(client2, _selected(env), dry=False)

    assert summary2["written_total"] == 0
    assert len(transport2.calls) == 1
    assert p.read_text(encoding="utf-8").count("**[gitlab:dev") == 1


def test_reset_cursor_with_replica_already_in_file_is_second_layer_dedup(env):
    p = _write_bug(env, "BUG-013", gitlab_issue=13)
    client1, _t1 = _client([(200, [_note(100, body="Уже перенесённая нота")])])
    gi.run(client1, _selected(env), dry=False)
    assert p.read_text(encoding="utf-8").count("Уже перенесённая нота") == 1

    gi.CURSOR_PATH.unlink()  # курсор потерян/сброшен
    client2, _t2 = _client([(200, [_note(100, body="Уже перенесённая нота")])])
    summary2 = gi.run(client2, _selected(env), dry=False)

    assert summary2["written_total"] == 0
    assert p.read_text(encoding="utf-8").count("Уже перенесённая нота") == 1


# --- system-нота: пропуск, но курсор всё равно двигается (см. докстринг gi) --

def test_system_note_is_skipped_but_advances_cursor(env):
    _write_bug(env, "BUG-014", gitlab_issue=14)
    client, _t = _client([(200, [_note(5, system=True, body="changed the description")])])

    summary = gi.run(client, _selected(env), dry=False)

    assert summary["written_total"] == 0
    assert summary["skipped_system_total"] == 1
    assert gi.load_cursor().get("BUG-014") == 5


# --- B1: фильтра по автору токена нет — нота владельца тоже доезжает --------

def test_owner_authored_note_is_not_filtered_by_author(env):
    p = _write_bug(env, "BUG-015", gitlab_issue=15)
    client, _t = _client([(200, [_note(1, username="Xartaxana1", body="Моя же заметка")])])

    summary = gi.run(client, _selected(env), dry=False)

    assert summary["written_total"] == 1
    assert "**[gitlab:Xartaxana1" in p.read_text(encoding="utf-8")


# --- Терминальный статус: awaiting не трогается + эскалация (R2) -----------

def test_terminal_status_does_not_set_awaiting_but_escalates(env):
    p = _write_bug(env, "BUG-016", status="Verified", gitlab_issue=16,
                   extra="awaiting: none\n")
    client, _t = _client([(200, [_note(1, body="Вопрос на закрытом баге")])])

    summary = gi.run(client, _selected(env), dry=False)

    assert summary["written_total"] == 1
    assert summary["closed_with_notes"] == ["BUG-016"]
    text = p.read_text(encoding="utf-8")
    assert "awaiting: none" in text
    assert "awaiting: qa" not in text
    assert bi.ESCALATIONS_PATH.exists()
    esc = bi.ESCALATIONS_PATH.read_text(encoding="utf-8")
    assert "BUG-016" in esc
    assert "Verified" in esc


# --- Деградация: офлайн/401 глобально останавливает батч --------------------

def test_401_error_degrades_globally_and_stops_batch(env):
    _write_bug(env, "BUG-020", gitlab_issue=20)
    _write_bug(env, "BUG-021", gitlab_issue=21)
    client, transport = _client([(401, {"message": "401 Unauthorized"})])

    summary = gi.run(client, _selected(env), dry=False)

    assert summary["degraded"] is True
    assert len(transport.calls) == 1   # BUG-021 не опрашивался вовсе


def test_offline_network_error_degrades_globally(env):
    _write_bug(env, "BUG-022", gitlab_issue=22)
    _write_bug(env, "BUG-023", gitlab_issue=23)
    client, transport = _client([(0, b"network unreachable")])

    summary = gi.run(client, _selected(env), dry=False)

    assert summary["degraded"] is True
    assert len(transport.calls) == 1


def test_main_without_token_degrades_with_no_network_call(env, monkeypatch, capsys):
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)

    def _boom(*_a, **_kw):
        raise AssertionError("транспорт не должен вызываться без токена")
    monkeypatch.setattr(gs, "_default_transport", _boom, raising=True)

    _write_bug(env, "BUG-024", gitlab_issue=24)
    code = gi.main([])
    out = capsys.readouterr().out
    assert code == 0
    assert "деградация" in out


# --- 404 одного iid не валит батч -------------------------------------------

def test_404_for_one_bug_does_not_kill_batch(env):
    _write_bug(env, "BUG-030", gitlab_issue=30)
    p2 = _write_bug(env, "BUG-031", gitlab_issue=31)
    client, transport = _client([
        (404, {"message": "404 Not Found"}),      # BUG-030
        (200, [_note(1, body="норм")]),            # BUG-031
    ])

    summary = gi.run(client, _selected(env), dry=False)

    assert summary["partial_failures"] == ["BUG-030"]
    assert summary["written_bugs"] == ["BUG-031"]
    assert "норм" in p2.read_text(encoding="utf-8")


# --- БЛОКЕР критик-входа: сортировка API по created_at, не по id ------------

def test_note_after_cursor_note_in_page_order_is_still_collected(env):
    """Воспроизведение пробы критика: одна страница
    [id=200(12:00), id=50(11:00), id=201(10:00)], курсор=100. Нота id=50
    (<=курсора) стоит МЕЖДУ 200 и 201 в выдаче (сортировка по created_at, не
    по id) — старый код обрывал сканирование страницы по первой встреченной
    note.id<=cursor и НИКОГДА не видел бы 201 (в т.ч. на повторных проходах,
    т.к. батч-bump поднял бы курсор до 200). Фикс: страница дочитывается
    целиком, все ноты с id>cursor собираются независимо от позиции."""
    p = _write_bug(env, "BUG-069", gitlab_issue=69)
    gi._bump_cursor("BUG-069", 100)
    client, transport = _client([
        (200, [
            _note(200, created="2026-08-09T12:00:00Z", body="Нота двести."),
            _note(50, created="2026-08-09T11:00:00Z", body="Нота пятьдесят (старая)."),
            _note(201, created="2026-08-09T10:00:00Z", body="Нота двести один."),
        ]),
    ])

    summary = gi.run(client, _selected(env), dry=False)

    assert summary["written_total"] == 2
    text = p.read_text(encoding="utf-8")
    assert "Нота двести." in text
    assert "Нота двести один." in text, "нота id=201 обязана перенестись — БЛОКЕР"
    assert "Нота пятьдесят" not in text
    assert len(transport.calls) == 1        # курсор встречен на этой же странице
    assert gi.load_cursor().get("BUG-069") == 201   # max id среди просмотренных нот

    # Повторный прогон (курсор уже поднят до 201) — идемпотентен, ничего не теряет.
    client2, transport2 = _client([
        (200, [
            _note(200, created="2026-08-09T12:00:00Z", body="Нота двести."),
            _note(201, created="2026-08-09T10:00:00Z", body="Нота двести один."),
        ]),
    ])
    summary2 = gi.run(client2, _selected(env), dry=False)
    assert summary2["written_total"] == 0
    assert len(transport2.calls) == 1


# --- Пагинация: кап MAX_PAGES — ГРАНИЦА и ЗА НЕЙ (правило 6а) --------------

def test_pagination_cap_boundary_cursor_found_on_last_allowed_page(env, monkeypatch):
    """Курсор обнаружен РОВНО на последней разрешённой (3-й) странице —
    успех, НЕ кап (граница «на»)."""
    monkeypatch.setattr(gi, "PER_PAGE", 2, raising=True)
    p = _write_bug(env, "BUG-040", gitlab_issue=40)
    gi._bump_cursor("BUG-040", 5)
    # Разное created/body у каждой ноты — иначе дедуп-ключ (автор,время,первая
    # строка) совпал бы у нескольких синтетических нот с одинаковыми дефолтами.
    notes = [_note(i, created=f"2026-08-09T{i:02d}:00:00Z", body=f"Нота {i}.")
             for i in range(10, 4, -1)]
    client, transport = _client([
        (200, notes[0:2]),
        (200, notes[2:4]),
        (200, notes[4:6]),   # id=5 == курсор -> ранний выход здесь
    ])

    summary = gi.run(client, _selected(env), dry=False)

    assert summary["written_total"] == 5   # 6,7,8,9,10
    assert len(transport.calls) == 3
    text = p.read_text(encoding="utf-8")
    assert text.count("**[gitlab:dev") == 5
    assert gi.load_cursor().get("BUG-040") == 10


def test_pagination_cap_exceeded_zero_writes_cursor_untouched_escalation(env, monkeypatch):
    """3 полные страницы, курсор ни разу не встречен -> ГРОМКИЙ ОТКАЗ: 0
    записей, курсор не изменён, эскалация есть (граница «за»)."""
    monkeypatch.setattr(gi, "PER_PAGE", 2, raising=True)
    p = _write_bug(env, "BUG-041", gitlab_issue=41)
    # Курсор МЕНЬШЕ всех id нот ниже — ни одна страница не остановит скан
    # раньше капа (это и форсирует ГРОМКИЙ ОТКАЗ).
    gi._bump_cursor("BUG-041", 1)
    client, transport = _client([
        (200, [_note(10), _note(9)]),
        (200, [_note(8), _note(7)]),
        (200, [_note(6), _note(5)]),
    ])

    summary = gi.run(client, _selected(env), dry=False)

    assert summary["cap_bugs"] == ["BUG-041"]
    assert summary["written_total"] == 0
    assert "**[" not in p.read_text(encoding="utf-8")
    assert gi.load_cursor().get("BUG-041") == 1   # курсор НЕ тронут
    assert len(transport.calls) == 3
    esc = bi.ESCALATIONS_PATH.read_text(encoding="utf-8")
    assert "BUG-041" in esc
    assert "канал не гарантирует порядок" in esc


# --- --check: четыре исхода --------------------------------------------------

def test_check_clean_exit0(env, monkeypatch, capsys):
    _write_bug(env, "BUG-050", gitlab_issue=50)
    monkeypatch.setenv("GITLAB_TOKEN", "tok-123")
    transport = FakeTransport([(200, [_note(1, system=True)])])
    monkeypatch.setattr(gs, "_default_transport", transport, raising=True)

    code = gi.main(["--check"])
    out = capsys.readouterr().out

    assert code == 0
    assert "чисто" in out


def test_check_no_token_degrades_exit0(env, monkeypatch, capsys):
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)

    def _boom(*_a, **_kw):
        raise AssertionError("не должен вызываться")
    monkeypatch.setattr(gs, "_default_transport", _boom, raising=True)

    code = gi.main(["--check"])
    out = capsys.readouterr().out

    assert code == 0
    assert "деградация" in out


def test_check_pending_notes_exit1(env, monkeypatch, capsys):
    _write_bug(env, "BUG-051", gitlab_issue=51)
    monkeypatch.setenv("GITLAB_TOKEN", "tok-123")
    transport = FakeTransport([(200, [_note(1, body="ещё не перенесено")])])
    monkeypatch.setattr(gs, "_default_transport", transport, raising=True)

    code = gi.main(["--check"])
    out = capsys.readouterr().out

    assert code == 1
    assert "необработанных" in out
    assert "BUG-051" in out
    # --check не пишет (dry) — артефакт не тронут
    assert "ещё не перенесено" not in (env / "BUG-051.md").read_text(encoding="utf-8")


def test_check_partial_degradation_exit0_when_reachable_clean(env, monkeypatch, capsys):
    _write_bug(env, "BUG-052", gitlab_issue=52)
    _write_bug(env, "BUG-053", gitlab_issue=53)
    monkeypatch.setenv("GITLAB_TOKEN", "tok-123")
    transport = FakeTransport([
        (404, {"message": "Not Found"}),        # BUG-052
        (200, [_note(1, system=True)]),          # BUG-053 — доступен, чисто
    ])
    monkeypatch.setattr(gs, "_default_transport", transport, raising=True)

    code = gi.main(["--check"])
    out = capsys.readouterr().out

    assert code == 0
    assert "частичная деградация" in out
    assert "BUG-052" in out


def test_check_pending_takes_priority_over_partial_degradation(env, monkeypatch, capsys):
    """[исход 4] «доступные баги при этом проверяются, их N>0 имеет приоритет
    → exit 1» — частичный отказ ПО ДРУГОМУ багу не маскирует реальные
    необработанные ноты у доступных."""
    _write_bug(env, "BUG-054", gitlab_issue=54)
    _write_bug(env, "BUG-055", gitlab_issue=55)
    monkeypatch.setenv("GITLAB_TOKEN", "tok-123")
    transport = FakeTransport([
        (404, {"message": "Not Found"}),                 # BUG-054
        (200, [_note(1, body="висит непрочитанная")]),    # BUG-055
    ])
    monkeypatch.setattr(gs, "_default_transport", transport, raising=True)

    code = gi.main(["--check"])
    out = capsys.readouterr().out

    assert code == 1
    assert "необработанных" in out
    assert "BUG-055" in out


# --- Адверсариальная батарея -------------------------------------------------

def test_multiline_body_quoted_in_crlf_file_no_mixed_eol(env):
    p = _write_bug(env, "BUG-060", gitlab_issue=60, eol="\r\n")
    before = p.read_bytes()
    assert before.count(b"\n") == before.count(b"\r\n")   # фикстура чисто CRLF

    client, _t = _client([(200, [_note(
        1, body="Первая строка.\nВторая строка.\nТретья.")])])
    gi.run(client, _selected(env), dry=False)

    after = p.read_bytes()
    assert after.replace(b"\r\n", b"").count(b"\n") == 0, "не должно остаться LF-сирот в CRLF-файле"
    assert "> Первая строка.\r\n> Вторая строка.\r\n> Третья.".encode("utf-8") in after


def test_empty_or_whitespace_body_skipped_with_warn(env, capsys):
    p = _write_bug(env, "BUG-061", gitlab_issue=61)
    client, _t = _client([(200, [
        _note(2, body="Нормальная нота.", created="2026-08-09T11:00:00Z"),
        _note(1, body="   \n  \n", created="2026-08-09T10:00:00Z"),
    ])])

    summary = gi.run(client, _selected(env), dry=False)
    out = capsys.readouterr().out

    assert summary["written_total"] == 1
    assert "Нормальная нота" in p.read_text(encoding="utf-8")
    assert "[WARN]" in out
    assert "BUG-061" in out


def test_body_with_replica_marker_not_mistaken_for_phantom_reply(env):
    p = _write_bug(env, "BUG-062", gitlab_issue=62)
    tricky = "Перед этим замечу:\n**[qa @ 2026-01-01T00:00:00Z]** старая цитата"
    client, _t = _client([(200, [_note(1, body=tricky)])])

    gi.run(client, _selected(env), dry=False)

    text = p.read_text(encoding="utf-8")
    replicas = bi._existing_replicas(text)
    assert len(replicas) == 1, "квотированная строка '**[...]**' не должна распознаваться как вторая реплика"


def test_body_with_heading_line_does_not_close_section_chronological_order(env):
    p = _write_bug(env, "BUG-063", gitlab_issue=63, checklist=True)
    tricky_1 = "## Подзаголовок в теле ноты\nОстальной текст первой ноты."
    client, _t = _client([
        (200, [
            # API отдаёт sort=desc — новейшая (10:00) ПЕРВОЙ в странице.
            _note(2, body="Вторая нота.", created="2026-08-09T10:00:00Z"),
            _note(1, body=tricky_1, created="2026-08-09T09:00:00Z"),
        ]),
    ])

    gi.run(client, _selected(env), dry=False)

    text = p.read_text(encoding="utf-8")
    first_i = text.index("Остальной текст первой ноты")
    second_i = text.index("Вторая нота.")
    checklist_i = text.index("## Чек-лист качества")
    assert first_i < second_i < checklist_i
    # квотированный '## ' не закрыл секцию для второй вставки
    assert "> ## Подзаголовок в теле ноты" in text
