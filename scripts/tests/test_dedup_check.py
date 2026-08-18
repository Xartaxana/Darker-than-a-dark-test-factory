"""Юнит-тесты dedup_check — WARN-детектора дублирующих тест-кейсов.

Механизм заведён словом оператора 2026-08-18: слияние (spec-p1-dedup v7)
ретроактивно по построению (rules.yaml — его явный non-goal), поэтому ничто
не мешало ПОРОЖДАТЬ дубли при написании. Замер, показавший цену: четыре
P1-кейса TC-197/199/200/201 — таблица истинности 2x2 по двум флагам,
выписанная четырьмя отдельными кейсами.

Ярус WARN — тоже решение оператора: признак «похожести» эвристический, и
гейт, блокирующий легитимный кейс, был бы обойдён. Поэтому тесты пинуют
ИМЕННО храповик (новое кричит, известное молчит) и границы порога.
"""
from __future__ import annotations

import pytest

import dedup_check as dc


def _case(tmp_path, case_id, title, area="browser", status="Approved"):
    d = tmp_path / area
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{case_id}.md").write_text(
        f"---\nid: {case_id}\ntitle: \"{title}\"\nstatus: {status}\n"
        f"priority: P1\n---\n\n# {case_id}\n", encoding="utf-8")
    return d / f"{case_id}.md"


# --- нормализация ----------------------------------------------------------

def test_normalize_drops_stopwords_punctuation_and_case():
    toks = dc.normalize_tokens("«Баннер» над листингом, НЕ показывается (для теста)")
    assert "баннер" in toks and "листингом" in toks
    assert "над" not in toks, "служебное слово раздувает пересечение"
    assert "не" not in toks
    assert not any("«" in t or "," in t for t in toks)


def test_normalize_is_yo_insensitive():
    assert dc.normalize_tokens("блёрб") == dc.normalize_tokens("блерб")


# --- граница порога (M6: НА границе и ЗА ней) ------------------------------

def test_threshold_boundary_is_inclusive(tmp_path):
    """Порог задан как `>=`: ровно на пороге пара СЧИТАЕТСЯ кандидатом.
    Введённый лимит без пина на границе — ровно тот дефект, из-за которого
    v8 уехал в прод с необнаруживаемым лимитом (урок критик-входа)."""
    a = {"aaa", "bbb", "ccc", "ddd"}
    b = {"aaa", "bbb", "eee", "fff"}
    assert dc.jaccard(a, b) == pytest.approx(1 / 3)

    _case(tmp_path, "TC-001", "aaa bbb ccc ddd")
    _case(tmp_path, "TC-002", "aaa bbb eee fff")

    on_border = dc.find_similar_pairs(dc.collect_cases(tmp_path), threshold=1 / 3)
    assert len(on_border) == 1, "на границе пара обязана считаться"

    past_border = dc.find_similar_pairs(dc.collect_cases(tmp_path), threshold=0.34)
    assert past_border == [], "за границей пара считаться НЕ должна"


def test_jaccard_empty_sets_do_not_divide_by_zero():
    assert dc.jaccard(set(), set()) == 0.0
    assert dc.jaccard({"a"}, set()) == 0.0


# --- область сравнения -----------------------------------------------------

def test_pairs_are_compared_only_within_one_area(tmp_path):
    """Одинаковые формулировки в РАЗНЫХ областях описывают разные механизмы
    («Restore …» в backup и в sync) — межобластные пары дали бы шум."""
    _case(tmp_path, "TC-001", "восстановление данных из архива", area="backup")
    _case(tmp_path, "TC-002", "восстановление данных из архива", area="sync")
    assert dc.find_similar_pairs(dc.collect_cases(tmp_path), threshold=0.3) == []

    _case(tmp_path, "TC-003", "восстановление данных из архива", area="backup")
    pairs = dc.find_similar_pairs(dc.collect_cases(tmp_path), threshold=0.3)
    assert [sorted(p["key"]) for p in pairs] == [["TC-001", "TC-003"]]


# --- храповик BASELINE -----------------------------------------------------

def test_known_pair_is_silent_and_new_pair_warns(tmp_path):
    """Суть механизма: корпус не может стать хуже НЕЗАМЕТНО. Известные пары
    считаются, но не кричат; кричат только новые."""
    _case(tmp_path, "TC-001", "баннер над листингом сообщает причину скрытия")
    _case(tmp_path, "TC-002", "баннер над листингом сообщает обе причины скрытия")
    baseline = {frozenset({"TC-001", "TC-002"})}

    fresh, known = dc.run(tmp_path, threshold=0.3, baseline=baseline)
    assert fresh == [] and len(known) == 1

    _case(tmp_path, "TC-003", "баннер над листингом сообщает третью причину скрытия")
    fresh, known = dc.run(tmp_path, threshold=0.3, baseline=baseline)
    assert len(known) == 1
    assert {tuple(sorted(p["key"])) for p in fresh} == {
        ("TC-001", "TC-003"), ("TC-002", "TC-003")}


def test_repo_baseline_covers_the_current_corpus():
    """Пин на живой корпус: в момент введения гейт обязан быть ЧИСТЫМ, иначе
    его сразу начнут игнорировать. Падение здесь = появился новый дубль
    (это и есть сигнал) либо BASELINE ужали без разбора."""
    fresh, known = dc.run()
    assert fresh == [], f"новые кандидаты в дубли: {[sorted(p['key']) for p in fresh]}"
    assert known, "BASELINE не должен быть пустым — корпус их содержит"


# --- детектор 2: вложенность сценария --------------------------------------

SCENARIO = """
## Сценарий (Given-When-Then)

**Given** приложение запущено с сидом библиотеки и дефолтными настройками
**When** пользователь открывает листинговую страницу каталога
**Then** над списком присутствует узел баннера с дословным текстом
"""
EXTRA = "**And** позиция списка не изменилась после повторного открытия\n"


def _case_with_scenario(tmp_path, case_id, body, area="browser"):
    d = tmp_path / area
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{case_id}.md").write_text(
        f"---\nid: {case_id}\ntitle: \"кейс {case_id}\"\nstatus: Approved\n---\n"
        f"\n# {case_id}\n{body}\n## Заметки\nпрочее\n", encoding="utf-8")


def test_steps_are_extracted_from_the_scenario_section(tmp_path):
    _case_with_scenario(tmp_path, "TC-001", SCENARIO)
    steps = dc.collect_cases(tmp_path)[0]["steps"]
    assert len(steps) == 3
    assert steps[0].startswith("given:") and steps[2].startswith("then:")
    assert "## заметки" not in " ".join(steps), "секция за сценарием не должна попадать"


def test_longer_case_continuing_a_shorter_one_is_flagged(tmp_path):
    """Слово оператора: «если один кейс повторяет шаги другого, но проходит
    на пару шагов дальше — не надо писать новый, надо расширить старый»."""
    _case_with_scenario(tmp_path, "TC-001", SCENARIO)
    _case_with_scenario(tmp_path, "TC-002", SCENARIO + EXTRA)

    pairs = dc.find_prefix_pairs(dc.collect_cases(tmp_path))
    assert len(pairs) == 1
    assert pairs[0]["short"]["id"] == "TC-001", "расширять надо КОРОТКИЙ кейс"
    assert pairs[0]["long"]["id"] == "TC-002"
    assert pairs[0]["shared"] == 3 and pairs[0]["extra"] == 1


def test_equal_length_scenarios_are_not_a_prefix_pair(tmp_path):
    """Одинаковая длина — это класс «таблица истинности» (детектор 1), а не
    «расширь старый»; смешивать их значило бы давать неверный совет."""
    _case_with_scenario(tmp_path, "TC-001", SCENARIO)
    _case_with_scenario(tmp_path, "TC-002", SCENARIO)
    assert dc.find_prefix_pairs(dc.collect_cases(tmp_path)) == []


def test_short_shared_prefix_is_below_the_bar(tmp_path):
    """M6-граница MIN_SHARED_STEPS: 2 общих шага — обычно лишь общее
    предусловие (Given+When), дублем не является. Замер по живому корпусу:
    лучшая реальная пара даёт ровно 2 совпавших шага и НЕ является дублем
    (TC-173/TC-174 — разные вкладки и разные ожидания)."""
    two_steps = ("\n## Сценарий (Given-When-Then)\n\n"
                 "**Given** приложение запущено с сидом библиотеки и дефолтными настройками\n"
                 "**When** пользователь открывает листинговую страницу каталога\n")
    _case_with_scenario(tmp_path, "TC-001", two_steps)
    _case_with_scenario(tmp_path, "TC-002", two_steps
                        + "**Then** над списком присутствует узел баннера\n")
    assert dc.find_prefix_pairs(dc.collect_cases(tmp_path)) == []
    assert dc.find_prefix_pairs(dc.collect_cases(tmp_path), min_shared=2), \
        "при явно сниженной планке пара обязана находиться (позитивный контроль)"


def test_prefix_pair_participates_in_the_same_ratchet(tmp_path):
    _case_with_scenario(tmp_path, "TC-001", SCENARIO)
    _case_with_scenario(tmp_path, "TC-002", SCENARIO + EXTRA)
    fresh, known = dc.run(tmp_path, baseline={frozenset({"TC-001", "TC-002"})})
    assert fresh == [] and len(known) == 1


def test_case_without_scenario_section_is_skipped_by_prefix_detector(tmp_path):
    _case_with_scenario(tmp_path, "TC-001", "\n## Предусловия\n- нет сценария\n")
    _case_with_scenario(tmp_path, "TC-002", SCENARIO)
    assert dc.find_prefix_pairs(dc.collect_cases(tmp_path)) == []


# --- статусы ---------------------------------------------------------------

@pytest.mark.parametrize("status", sorted(dc.SKIPPED_STATUSES))
def test_terminal_statuses_are_not_compared(tmp_path, status):
    """Merged уже поглощён — сравнивать его на дубли значит считать одно и
    то же дважды; Blocked не развивается."""
    _case(tmp_path, "TC-001", "баннер над листингом сообщает причину скрытия")
    _case(tmp_path, "TC-002", "баннер над листингом сообщает причину скрытия",
          status=status)
    assert dc.find_similar_pairs(dc.collect_cases(tmp_path), threshold=0.3) == []


# --- код возврата ----------------------------------------------------------

def test_warn_mode_never_fails_the_preflight(tmp_path, capsys):
    _case(tmp_path, "TC-001", "баннер над листингом сообщает причину скрытия")
    _case(tmp_path, "TC-002", "баннер над листингом сообщает обе причины скрытия")
    rc = dc.main(["--cases-dir", str(tmp_path), "--threshold", "0.3"])
    assert rc == 0, "WARN-ярус не имеет права ронять preflight"
    assert "НОВЫЙ кандидат" in capsys.readouterr().out


def test_strict_mode_fails_on_new_pairs(tmp_path):
    """--strict реализован заранее, но в preflight НЕ включён: продвижение
    WARN -> ERROR идёт по evidence (D-0063), а не ради симметрии."""
    _case(tmp_path, "TC-001", "баннер над листингом сообщает причину скрытия")
    _case(tmp_path, "TC-002", "баннер над листингом сообщает обе причины скрытия")
    assert dc.main(["--cases-dir", str(tmp_path), "--threshold", "0.3", "--strict"]) == 1


def test_strict_mode_is_clean_without_new_pairs(tmp_path):
    _case(tmp_path, "TC-001", "уникальный кейс про загрузку файла")
    assert dc.main(["--cases-dir", str(tmp_path), "--strict"]) == 0


# --- устойчивость (BL-4) ---------------------------------------------------

def test_missing_directory_is_not_a_crash(tmp_path):
    assert dc.collect_cases(tmp_path / "нет-такой") == []


def test_case_without_frontmatter_is_skipped(tmp_path):
    d = tmp_path / "browser"
    d.mkdir(parents=True)
    (d / "junk.md").write_text("просто заметка без frontmatter\n", encoding="utf-8")
    _case(tmp_path, "TC-001", "нормальный кейс")
    got = dc.collect_cases(tmp_path)
    assert [c["id"] for c in got] == ["TC-001"]
