"""Юнит-тесты anchor_lint — WARN-линтера якорей `file:line` в тест-кейсах.

Класс дефекта: код под кейсом сменился (переименован/удалён/укоротился),
якорь в кейсе молчит. Линтер ловит ТОЛЬКО грубый дрейф — файл не найден или
номер строки за концом файла; смысловой дрейф содержимого строки вне
скоупа (докстринг модуля).

Фикстуры — ИЗОЛИРОВАННЫЕ tmp_path-деревья (не живой репозиторий), кроме
одного smoke-теста на живом репо (правило DoD: не полный регресс, только
smoke «не падает и выходит 0»).
"""
from __future__ import annotations

import pytest

import anchor_lint as al


def _case(tmp_path, case_id, body, area="browser", status="Approved"):
    d = tmp_path / "cases" / area
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{case_id}.md").write_text(
        f"---\nid: {case_id}\ntitle: \"кейс {case_id}\"\nstatus: {status}\n---\n"
        f"\n# {case_id}\n{body}\n", encoding="utf-8")
    return d / f"{case_id}.md"


def _app_file(tmp_path, relpath, n_lines):
    p = tmp_path / "app" / relpath
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(f"line {i}" for i in range(1, n_lines + 1)) + "\n",
                 encoding="utf-8")
    return p


def _fw_file(tmp_path, relpath, n_lines):
    """Файл под изолированным framework/-корнем фикстуры (НЕ живой репо)."""
    p = tmp_path / "framework" / relpath
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(f"line {i}" for i in range(1, n_lines + 1)) + "\n",
                 encoding="utf-8")
    return p


def _scripts_file(tmp_path, relpath, n_lines):
    """Файл под изолированным scripts/-корнем фикстуры (НЕ живой репо)."""
    p = tmp_path / "scripts" / relpath
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(f"line {i}" for i in range(1, n_lines + 1)) + "\n",
                 encoding="utf-8")
    return p


# --- извлечение якорей ------------------------------------------------------

def test_extract_anchors_basic():
    anchors = al.extract_anchors("см. `BrowseSidePanel.kt:110` и `ao3_bridge.js:513`")
    assert anchors == [("BrowseSidePanel.kt", 110), ("ao3_bridge.js", 513)]


def test_extract_anchors_range_takes_first_number():
    anchors = al.extract_anchors("`MainActivity.kt:764-783`")
    assert anchors == [("MainActivity.kt", 764)]


def test_extract_anchors_comma_tail_is_same_file_extra_anchor():
    anchors = al.extract_anchors("`SettingsScreen.kt:214, 277`")
    assert anchors == [("SettingsScreen.kt", 214), ("SettingsScreen.kt", 277)]


def test_extract_anchors_ignores_non_anchor_extensions():
    """`.md`/`.yaml` — не код приложения, не должны попадать в якоря."""
    anchors = al.extract_anchors("bugs/BUG-019.md, docs/feature-registry.yaml")
    assert anchors == []


def test_extract_anchors_scans_frontmatter_too():
    """Якоря часто лежат внутри `requirements:` фронтматтера, не в теле —
    линтер обязан их видеть, а не только тело после `---`."""
    text = ('---\nid: TC-001\nrequirements: "ao3_bridge.js:673-689 текст"\n'
            'status: Approved\n---\n\nтело без якорей\n')
    assert al.extract_anchors(text) == [("ao3_bridge.js", 673)]


# --- проверка якоря против app-under-test/ ----------------------------------

def test_anchor_within_file_length_is_clean(tmp_path):
    app_file = _app_file(tmp_path, "src/Foo.kt", 50)
    index = {app_file.name: [app_file]}
    ok, reason = al.check_anchor("Foo.kt", 50, index, {})
    assert ok and reason is None


def test_anchor_past_end_of_file_warns(tmp_path):
    app_file = _app_file(tmp_path, "src/Foo.kt", 50)
    index = {app_file.name: [app_file]}
    ok, reason = al.check_anchor("Foo.kt", 51, index, {})
    assert not ok
    assert "за концом файла" in reason and "максимум 50" in reason


def test_anchor_boundary_exact_last_line_is_clean(tmp_path):
    """M6: граница `line <= счётчик строк` — ровно на границе якорь чист."""
    app_file = _app_file(tmp_path, "src/Foo.kt", 10)
    index = {app_file.name: [app_file]}
    ok, _ = al.check_anchor("Foo.kt", 10, index, {})
    assert ok, "номер строки == длине файла обязан считаться валидным"


def test_anchor_boundary_one_past_last_line_warns(tmp_path):
    app_file = _app_file(tmp_path, "src/Foo.kt", 10)
    index = {app_file.name: [app_file]}
    ok, _ = al.check_anchor("Foo.kt", 11, index, {})
    assert not ok, "первая строка ЗА концом файла обязана считаться битой"


def test_anchor_missing_file_warns(tmp_path):
    ok, reason = al.check_anchor("Ghost.kt", 1, {}, {})
    assert not ok and reason == "файл не найден"


def test_anchor_valid_if_any_candidate_covers_the_line(tmp_path):
    """Несколько файлов с одинаковым basename (например build/ копия и
    исходник) — якорь чист, если ХОТЯ БЫ ОДИН кандидат достаточно длинный."""
    short = _app_file(tmp_path, "build/Foo.kt", 5)
    long_ = _app_file(tmp_path, "src/Foo.kt", 50)
    index = {"Foo.kt": [short, long_]}
    ok, _ = al.check_anchor("Foo.kt", 30, index, {})
    assert ok


# --- второй корень (framework/) и исключения --------------------------------

def test_py_anchor_on_framework_root_is_clean(tmp_path):
    """Дозаказ координатора: py-якорь на файл в ИЗОЛИРОВАННОМ framework/-корне
    фикстуры — тестовая обвязка входит в класс «код под кейсом сменился»."""
    cases_dir = tmp_path / "cases"
    app_dir = tmp_path / "app"
    fw_dir = tmp_path / "framework"
    _fw_file(tmp_path, "steps/browser_steps.py", 50)
    _case(tmp_path, "TC-008", "`browser_steps.py:30`")

    broken, total = al.run(cases_dir, app_dir, fw_dir, tmp_path / "scripts",
                           tmp_path / "no-docs.md", tmp_path / "no-charters")
    assert total == 1 and broken == [], "framework/-файл обязан считаться кандидатом"


def test_py_anchor_on_scripts_root_is_clean(tmp_path):
    """Дозаказ координатора (2-й раунд): scripts/ — ТРЕТИЙ корень поиска,
    тот же аргумент, что framework/ — обвязка конвейера входит в класс.
    Тот же механизм, что framework-тест выше."""
    cases_dir = tmp_path / "cases"
    app_dir = tmp_path / "app"
    fw_dir = tmp_path / "framework"
    scripts_dir = tmp_path / "scripts"
    _scripts_file(tmp_path, "arch_check.py", 90)
    _case(tmp_path, "TC-011", "`arch_check.py:80`")

    broken, total = al.run(cases_dir, app_dir, fw_dir, scripts_dir,
                           tmp_path / "no-docs.md", tmp_path / "no-charters")
    assert total == 1 and broken == [], "scripts/-файл обязан считаться кандидатом"


def test_file_only_in_venv_is_not_a_candidate(tmp_path):
    """.venv — site-packages, не тестовая обвязка: файл, лежащий ТОЛЬКО там,
    не должен становиться кандидатом (иначе якорь ложно считается чистым)."""
    cases_dir = tmp_path / "cases"
    app_dir = tmp_path / "app"
    fw_dir = tmp_path / "framework"
    _fw_file(tmp_path, ".venv/Lib/site-packages/somepkg/conftest.py", 999)
    _case(tmp_path, "TC-009", "`conftest.py:5`")

    broken, total = al.run(cases_dir, app_dir, fw_dir, tmp_path / "scripts",
                           tmp_path / "no-docs.md", tmp_path / "no-charters")
    assert total == 1 and len(broken) == 1
    assert broken[0]["reason"] == "файл не найден", \
        ".venv не должен обходиться — иначе якорь ложно-зелёный"


def test_file_only_in_allure_results_is_not_a_candidate(tmp_path):
    """allure-* (сгенерированные отчёты) — тот же класс шума, что .venv."""
    cases_dir = tmp_path / "cases"
    app_dir = tmp_path / "app"
    fw_dir = tmp_path / "framework"
    _fw_file(tmp_path, "allure-results/attach/dump.js", 5)
    _case(tmp_path, "TC-010", "`dump.js:1`")

    broken, total = al.run(cases_dir, app_dir, fw_dir, tmp_path / "scripts",
                           tmp_path / "no-docs.md", tmp_path / "no-charters")
    assert total == 1 and len(broken) == 1
    assert broken[0]["reason"] == "файл не найден"


# --- сканирование корпуса ----------------------------------------------------

def test_run_flags_missing_and_overflowing_anchors(tmp_path):
    cases_dir = tmp_path / "cases"
    app_dir = tmp_path / "app"
    _app_file(tmp_path, "app/Foo.kt", 20)
    _case(tmp_path, "TC-001", "`Foo.kt:10` норм, `Foo.kt:25` за концом, "
                              "`Ghost.kt:1` файла нет")

    broken, total = al.run(cases_dir, app_dir, tmp_path / "framework",
                           tmp_path / "scripts", tmp_path / "no-docs.md",
                           tmp_path / "no-charters")
    assert total == 3
    reasons = {(b["file"], b["line"]): b["reason"] for b in broken}
    assert ("Foo.kt", 25) in reasons and "за концом файла" in reasons[("Foo.kt", 25)]
    assert ("Ghost.kt", 1) in reasons and reasons[("Ghost.kt", 1)] == "файл не найден"
    assert ("Foo.kt", 10) not in reasons


def test_run_range_and_comma_tail_forms(tmp_path):
    cases_dir = tmp_path / "cases"
    app_dir = tmp_path / "app"
    _app_file(tmp_path, "app/Bar.kt", 300)
    _case(tmp_path, "TC-002", "диапазон `Bar.kt:290-310` и хвост `Bar.kt:100, 400`")

    broken, total = al.run(cases_dir, app_dir, tmp_path / "framework",
                           tmp_path / "scripts", tmp_path / "no-docs.md",
                           tmp_path / "no-charters")
    # диапазон даёт якорь по 290 (чист, <=300); хвост даёт 100 (чист) и 400 (бит)
    assert total == 3
    assert len(broken) == 1
    assert broken[0]["file"] == "Bar.kt" and broken[0]["line"] == 400


def test_merged_case_is_not_scanned(tmp_path):
    cases_dir = tmp_path / "cases"
    app_dir = tmp_path / "app"
    _case(tmp_path, "TC-003", "`Ghost.kt:1`", status="Merged")
    broken, total = al.run(cases_dir, app_dir, tmp_path / "framework",
                           tmp_path / "scripts", tmp_path / "no-docs.md",
                           tmp_path / "no-charters")
    assert total == 0 and broken == []


def test_deprecated_case_is_not_scanned(tmp_path):
    cases_dir = tmp_path / "cases"
    app_dir = tmp_path / "app"
    _case(tmp_path, "TC-004", "`Ghost.kt:1`", status="Deprecated")
    broken, total = al.run(cases_dir, app_dir, tmp_path / "framework",
                           tmp_path / "scripts", tmp_path / "no-docs.md",
                           tmp_path / "no-charters")
    assert total == 0 and broken == []


def test_missing_dirs_do_not_crash(tmp_path):
    broken, total = al.run(tmp_path / "no-cases", tmp_path / "no-app",
                           tmp_path / "no-framework", tmp_path / "no-scripts",
                           tmp_path / "no-docs.md", tmp_path / "no-charters")
    assert broken == [] and total == 0


# --- код возврата ------------------------------------------------------------

def test_warn_mode_never_fails(tmp_path, capsys):
    cases_dir = tmp_path / "cases"
    app_dir = tmp_path / "app"
    _case(tmp_path, "TC-005", "`Ghost.kt:1`")
    rc = al.main(["--cases-dir", str(cases_dir), "--app-dir", str(app_dir),
                 "--framework-dir", str(tmp_path / "framework"),
                 "--scripts-dir", str(tmp_path / "scripts"),
                 "--docs-strategy-file", str(tmp_path / "no-docs.md"),
                 "--charters-dir", str(tmp_path / "no-charters")])
    assert rc == 0, "WARN-ярус не имеет права ронять прогон"
    out = capsys.readouterr().out
    assert "[WARN] TC-005: Ghost.kt:1 — файл не найден" in out
    assert "anchor_lint: якорей 1, битых 1" in out


def test_strict_boundary_zero_broken_exits_zero(tmp_path):
    cases_dir = tmp_path / "cases"
    app_dir = tmp_path / "app"
    _app_file(tmp_path, "app/Foo.kt", 20)
    _case(tmp_path, "TC-006", "`Foo.kt:10`")
    rc = al.main(["--cases-dir", str(cases_dir), "--app-dir", str(app_dir),
                 "--framework-dir", str(tmp_path / "framework"),
                 "--scripts-dir", str(tmp_path / "scripts"), "--strict",
                 "--docs-strategy-file", str(tmp_path / "no-docs.md"),
                 "--charters-dir", str(tmp_path / "no-charters")])
    assert rc == 0, "0 битых — --strict обязан быть зелёным (граница M6, снизу)"


def test_strict_boundary_one_broken_exits_one(tmp_path):
    cases_dir = tmp_path / "cases"
    app_dir = tmp_path / "app"
    _case(tmp_path, "TC-007", "`Ghost.kt:1`")
    rc = al.main(["--cases-dir", str(cases_dir), "--app-dir", str(app_dir),
                 "--framework-dir", str(tmp_path / "framework"),
                 "--scripts-dir", str(tmp_path / "scripts"), "--strict",
                 "--docs-strategy-file", str(tmp_path / "no-docs.md"),
                 "--charters-dir", str(tmp_path / "no-charters")])
    assert rc == 1, "1 битый + --strict — граница M6, сверху"


# --- дополнительные источники: docs/01-test-strategy.md + charters ----------

def _docs_strategy(tmp_path, body):
    p = tmp_path / "docs" / "01-test-strategy.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"# 01 — Стратегия\n{body}\n", encoding="utf-8")
    return p


def _charter(tmp_path, ch_id, body, status="Done"):
    d = tmp_path / "charters"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{ch_id}.md"
    p.write_text(f"---\nid: {ch_id}\nstatus: {status}\n---\n\n{body}\n",
                 encoding="utf-8")
    return p


def test_docs_strategy_file_is_scanned_broken_anchor_caught(tmp_path):
    """docs/01-test-strategy.md — сверх test-cases/, битый якорь ловится."""
    cases_dir = tmp_path / "cases"
    app_dir = tmp_path / "app"
    docs_file = _docs_strategy(tmp_path, "ссылка `Ghost.kt:1` протухла")

    broken, total = al.run(cases_dir, app_dir, tmp_path / "framework",
                           tmp_path / "scripts", docs_file, tmp_path / "no-charters")
    assert total == 1
    assert broken[0]["file"] == "Ghost.kt" and broken[0]["case_id"] == "01-test-strategy.md"


def test_docs_strategy_file_without_frontmatter_uses_filename_as_id(tmp_path):
    """docs/01 не несёт frontmatter `id` — id падает на имя файла, не падает
    молча (случай отсутствия case_id в collect_cases здесь неприменим)."""
    cases_dir = tmp_path / "cases"
    app_dir = tmp_path / "app"
    _app_file(tmp_path, "app/Foo.kt", 5)
    docs_file = _docs_strategy(tmp_path, "чистый якорь `Foo.kt:5`")

    broken, total = al.run(cases_dir, app_dir, tmp_path / "framework",
                           tmp_path / "scripts", docs_file, tmp_path / "no-charters")
    assert total == 1 and broken == []


def test_history_doc_is_not_scanned_scope_is_exactly_01_file(tmp_path):
    """docs/09-history.md (или любой другой docs/-файл) НЕ входит в скоуп —
    скоуп это РОВНО путь docs/01-test-strategy.md, не каталог docs/ целиком."""
    cases_dir = tmp_path / "cases"
    app_dir = tmp_path / "app"
    history = tmp_path / "docs" / "09-history.md"
    history.parent.mkdir(parents=True, exist_ok=True)
    history.write_text("архивный битый якорь `Ghost.kt:1`\n", encoding="utf-8")
    # docs-strategy-file указывает на 01-файл, которого тут нет — history.md
    # рядом лежит, но НЕ является этим файлом и сканироваться не должен.
    docs_file = tmp_path / "docs" / "01-test-strategy.md"

    broken, total = al.run(cases_dir, app_dir, tmp_path / "framework",
                           tmp_path / "scripts", docs_file, tmp_path / "no-charters")
    assert total == 0 and broken == [], \
        "docs/09-history.md обязан игнорироваться — скоуп не вся docs/"


def test_charters_dir_is_scanned_broken_anchor_caught(tmp_path):
    cases_dir = tmp_path / "cases"
    app_dir = tmp_path / "app"
    charters_dir = tmp_path / "charters"
    _charter(tmp_path, "CH-001", "находка ссылается на `Ghost.kt:1`")

    broken, total = al.run(cases_dir, app_dir, tmp_path / "framework",
                           tmp_path / "scripts", tmp_path / "no-docs.md", charters_dir)
    assert total == 1
    assert broken[0]["case_id"] == "CH-001" and broken[0]["file"] == "Ghost.kt"


def test_charter_with_non_done_status_is_still_scanned(tmp_path):
    """Чартеры НЕ фильтруются по статусу (свой словарь жизненного цикла, не
    test-case-терминальность) — Blocked-чартер сканируется наравне с Done."""
    cases_dir = tmp_path / "cases"
    app_dir = tmp_path / "app"
    charters_dir = tmp_path / "charters"
    _charter(tmp_path, "CH-002", "`Ghost.kt:1`", status="Blocked")

    broken, total = al.run(cases_dir, app_dir, tmp_path / "framework",
                           tmp_path / "scripts", tmp_path / "no-docs.md", charters_dir)
    assert total == 1 and len(broken) == 1, \
        "у чартеров нет статусного фильтра — Blocked сканируется как Done"


def test_missing_docs_strategy_file_and_charters_dir_do_not_crash(tmp_path):
    broken, total = al.run(tmp_path / "no-cases", tmp_path / "no-app",
                           tmp_path / "no-framework", tmp_path / "no-scripts",
                           tmp_path / "no-docs.md", tmp_path / "no-charters")
    assert broken == [] and total == 0


# --- адверсариальная батарея --------------------------------------------------

def test_anchor_with_colon_in_surrounding_text_still_parses(tmp_path):
    """Двоеточие рядом с якорем (время, заголовок) не должно ломать разбор —
    регекс якоря матчит по basename.ext:N независимо от соседних двоеточий."""
    anchors = al.extract_anchors(
        "Время замера 12:30, файл: `Foo.kt:20`, комментарий: важно")
    assert ("Foo.kt", 20) in anchors
    # "12:30" не basename.ext — не должно давать ложный якорь
    assert all(f != "30" for f, _ in anchors)


def test_cyrillic_path_case_id_does_not_crash(tmp_path):
    """Кириллический путь/id — читается и обрабатывается без падения."""
    cases_dir = tmp_path / "cases"
    d = cases_dir / "браузер"
    d.mkdir(parents=True, exist_ok=True)
    (d / "ТК-001.md").write_text(
        '---\nid: ТК-001\ntitle: "кейс кириллица"\nstatus: Approved\n---\n\n'
        '`Ghost.kt:1`\n', encoding="utf-8")
    app_dir = tmp_path / "app"

    broken, total = al.run(cases_dir, app_dir, tmp_path / "framework",
                           tmp_path / "scripts", tmp_path / "no-docs.md",
                           tmp_path / "no-charters")
    assert total == 1 and broken[0]["case_id"] == "ТК-001"


def test_nonexistent_file_anchor_is_reported_not_crashed(tmp_path):
    ok, reason = al.check_anchor("DoesNotExist.kt", 1, {}, {})
    assert not ok and reason == "файл не найден"


def test_line_exactly_at_end_of_file_boundary_via_docs_source(tmp_path):
    """M6 граница через новый источник (docs/01): строка == длине файла чиста,
    на 1 больше — бита."""
    cases_dir = tmp_path / "cases"
    app_dir = tmp_path / "app"
    _app_file(tmp_path, "app/Bound.kt", 7)
    docs_file = _docs_strategy(
        tmp_path, "на границе `Bound.kt:7` и за границей `Bound.kt:8`")

    broken, total = al.run(cases_dir, app_dir, tmp_path / "framework",
                           tmp_path / "scripts", docs_file, tmp_path / "no-charters")
    assert total == 2 and len(broken) == 1
    assert broken[0]["line"] == 8


# --- смок на живом репозитории ----------------------------------------------

def test_smoke_on_live_repo_does_not_crash_and_exits_zero():
    """Единственный тест на реальном дереве (правило DoD): не падает, WARN-ярус
    выходит 0 даже если в живом корпусе есть битые/не найденные якоря."""
    rc = al.main([])
    assert rc == 0


def test_smoke_live_repo_new_scope_includes_docs_and_charters():
    """Живой прогон: скоуп реально расширен (счётчик якорей на HEAD заведомо
    больше, чем только test-cases/ — 899 якорей на момент замера 2026-08-20;
    порог занижен с запасом, чтобы не быть хрупким к росту корпуса)."""
    broken, total = al.run()
    assert total > 900, "новый скоуп обязан прибавить якоря сверх test-cases/"
