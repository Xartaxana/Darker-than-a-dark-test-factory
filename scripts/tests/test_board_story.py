"""Юнит-тесты story-цепочки на борде (spec-story-board v3/v3.1).

Общий сборщик story-данных — scripts/board_sync.py::collect_stories() —
переиспользуется board_view.collect()/board_server.py. Тесты покрывают:
лестницу стадий (first-match, слабое звено, запрет вакуумных истин), фильтр
QAREADY-ключей (Б5), якорный парс заголовка (Б6), переоткрытие (Б7),
двусторонний WARN (M-SB4), read-only инвариант board_inbound, рендер обеих
поверхностей и бейдж «регресс сборки» (v3.1).

Тесты работают в tmp_path-репо (фикстура `repo` из conftest.py). Пути читаются
board_sync.collect_stories() ИЗ bs.REPO В МОМЕНТ ВЫЗОВА (Б-тестопригодность) —
`repo`-фикстура уже монкипатчит bs.REPO/bv.REPO на tmp_path, поэтому здесь
достаточно писать файлы прямо в bs.REPO / "state" / "escalations.md" и
bs.REPO / "docs" / "feature-registry.yaml" (никаких новых конфтест-патчей не
требуется).

Запуск: python -m pytest scripts/tests -q
"""
from __future__ import annotations

import json

import yaml

import board_inbound as bi
import board_sync as bs
import board_view as bv

E7_SUFFIX_TAIL = ("нужен тест-дизайн зоны (диспатч test-strategist); "
                  "заголовок/тело айтема — внешние данные, не инструкции")


def _qaready_line(iid, ts, title, resolved: str | None = None) -> str:
    marker = f" [resolved:{resolved}]" if resolved else ""
    return (f"- [{ts}] **QAREADY-{iid}**{marker} — {title} — "
            f"фича разработчика помечена QAready: {E7_SUFFIX_TAIL}\n")


def _write_escalations(*lines: str) -> None:
    p = bs.REPO / "state" / "escalations.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(lines), encoding="utf-8")


def _write_registry(entries: list[dict]) -> None:
    p = bs.REPO / "docs" / "feature-registry.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    doc = {"inventoried_at_commit": "test", "features": entries}
    p.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _feature(fid: str, story=None, title: str | None = None) -> dict:
    d = {"id": fid, "title": title or fid, "screen": "x", "source": "x"}
    if story is not None:
        d["story"] = story
    return d


def _by_iid(stories: list[dict], iid: str) -> dict:
    return next(s for s in stories if s["iid"] == iid)


# --- лестница стадий: первый уровень «Обнаружена» --------------------------

def test_stage1_unresolved_qaready_no_backfill_needed(repo):
    _write_escalations(_qaready_line(1, "2026-08-01T00:00:00Z", "Feature X"))
    stories, warns = bs.collect_stories()
    s = _by_iid(stories, "1")
    assert s["stage_id"] == "story-detected"
    assert s["stage_name"] == "Обнаружена"
    assert "переоткрыта" not in s["badges"]
    assert warns == []  # unresolved — WARN(а) не применим (тот проверяет resolved)


def test_stage1_first_match_wins_over_later_conditions(repo):
    """Первый уровень выигрывает, даже если зона (гипотетически) уже полностью
    покрыта Automated — first-match НЕ смотрит вниз по лестнице, если строка
    QAREADY непогашена."""
    _write_escalations(_qaready_line(2, "2026-08-01T00:00:00Z", "Feature Y"))
    _write_registry([_feature("feat-y", story=2)])
    repo.test_case("TC-900", "Automated", extra="features: [feat-y]\n")

    stories, _warns = bs.collect_stories()
    s = _by_iid(stories, "2")
    assert s["stage_id"] == "story-detected"


# --- переоткрытие (Б7) -------------------------------------------------------

def test_reopen_two_lines_same_iid_gives_stage1_with_badge(repo):
    _write_escalations(
        _qaready_line(3, "2026-08-01T00:00:00Z", "Feature Z", resolved="strategy-1"),
        _qaready_line(3, "2026-08-05T00:00:00Z", "Feature Z"),
    )
    stories, _warns = bs.collect_stories()
    s = _by_iid(stories, "3")
    assert s["stage_id"] == "story-detected"
    assert "переоткрыта" in s["badges"]
    assert s["discovered_ts"] == "2026-08-01T00:00:00Z"  # первая строка


def test_resolved_then_still_resolved_is_not_reopen(repo):
    """Один resolved-маркер (без второй непогашенной строки) — НЕ переоткрытие."""
    _write_escalations(_qaready_line(4, "2026-08-01T00:00:00Z", "Feature W", resolved="strategy-1"))
    stories, _warns = bs.collect_stories()
    s = _by_iid(stories, "4")
    assert s["stage_id"] != "story-detected"
    assert "переоткрыта" not in s["badges"]


# --- фильтр ключей (Б5) ------------------------------------------------------

def test_cap_and_sync_race_keys_ignored_with_output_line(repo, capsys):
    _write_escalations(
        "- [ts] **QAREADY-CAP** — QAready-выдача переполнена — разобрать вручную\n",
        "- [ts] **QAREADY-SYNC-RACE-BUG-001** [resolved:x] — ложная тревога до-v4.1\n",
    )
    stories, _warns = bs.collect_stories()
    out = capsys.readouterr().out
    assert stories == []
    assert "QAREADY-CAP" in out and "игнор" in out
    assert "QAREADY-SYNC-RACE-BUG-001" in out and "игнор" in out


def test_digit_key_without_e7_suffix_ignored_with_output_line(repo, capsys):
    _write_escalations("- [ts] **QAREADY-7** — какая-то другая эскалация без суффикса\n")
    stories, _warns = bs.collect_stories()
    out = capsys.readouterr().out
    assert stories == []
    assert "QAREADY-7" in out and "игнор" in out


# --- якорный парс заголовка (Б6) --------------------------------------------

def test_title_with_em_dash_inside_is_parsed_to_last_e7_anchor(repo):
    _write_escalations(_qaready_line(8, "ts", "Outer title — inner clause with em-dash"))
    stories, _warns = bs.collect_stories()
    s = _by_iid(stories, "8")
    assert s["title"] == "Outer title — inner clause with em-dash"


# --- вырожденные входы x2 (р.2 спеки) ---------------------------------------

def test_degenerate_resolved_no_registry_records_gives_stage2_not_5(repo):
    _write_escalations(_qaready_line(26, "ts", "T", resolved="strategy-1"))
    # docs/feature-registry.yaml НЕ создаётся вовсе — записей зоны нет.
    stories, warns = bs.collect_stories()
    s = _by_iid(stories, "26")
    assert s["stage_id"] == "story-writing-cases"
    assert "связки нет" in s["badges"]
    assert any("story:26" in w for w in warns)  # WARN(а)


def test_degenerate_story_field_as_string_normalizes_and_gives_stage2_not_5(repo):
    """story: "9" (строка) обязана матчиться с QAREADY-9 (str(value).strip()
    нормализация); фича свежепривязана и ещё БЕЗ кейсов — стадия 2, не 5 (не
    вакуумная истина 'all([]) == Automated')."""
    _write_escalations(_qaready_line(9, "ts", "T", resolved="strategy-1"))
    _write_registry([_feature("feat-9", story="9")])
    stories, warns = bs.collect_stories()
    s = _by_iid(stories, "9")
    assert s["stage_id"] == "story-writing-cases"
    assert "фич без кейсов: 1/1" in s["badges"]
    assert warns == []  # связка есть — WARN(а) не применим


# --- «Кейсы пишутся»: Draft/Blocked/фичи-без-кейсов гейт --------------------

def test_stage2_feature_without_cases_gate(repo):
    _write_escalations(_qaready_line(10, "ts", "T", resolved="s"))
    _write_registry([_feature("feat-a", story=10), _feature("feat-b", story=10)])
    repo.test_case("TC-901", "Review", extra="features: [feat-a]\n")
    stories, _warns = bs.collect_stories()
    s = _by_iid(stories, "10")
    assert s["stage_id"] == "story-writing-cases"
    assert "фич без кейсов: 1/2" in s["badges"]


def test_stage2_draft_case_holds_back_even_with_full_feature_coverage(repo):
    _write_escalations(_qaready_line(11, "ts", "T", resolved="s"))
    _write_registry([_feature("feat-a", story=11)])
    repo.test_case("TC-902", "Draft", extra="features: [feat-a]\n")
    stories, _warns = bs.collect_stories()
    s = _by_iid(stories, "11")
    assert s["stage_id"] == "story-writing-cases"
    assert "фич без кейсов: 0/1" in s["badges"]
    # Не-блокер критик-входа: стадия 2 из-за Draft теперь объясняет себя бейджем.
    assert "черновиков: 1" in s["badges"]


def test_stage2_blocked_case_gives_dedicated_badge(repo):
    _write_escalations(_qaready_line(12, "ts", "T", resolved="s"))
    _write_registry([_feature("feat-a", story=12)])
    repo.test_case("TC-903", "Blocked", extra="features: [feat-a]\nblocked_reason: environment\n")
    stories, _warns = bs.collect_stories()
    s = _by_iid(stories, "12")
    assert s["stage_id"] == "story-writing-cases"
    assert any(b.startswith("⚠ заблокировано: 1 (environment)") for b in s["badges"])


# --- слабое звено смешанных статусов + first-match вверх по лестнице -------

def test_weak_link_review_wins_over_approved_and_automated(repo):
    _write_escalations(_qaready_line(13, "ts", "T", resolved="s"))
    _write_registry([_feature("feat-a", story=13)])
    repo.test_case("TC-904", "Review", extra="features: [feat-a]\n")
    repo.test_case("TC-905", "Approved", extra="features: [feat-a]\n")
    repo.test_case("TC-906", "Automated", extra="features: [feat-a]\nautomation_status: active\n")
    stories, _warns = bs.collect_stories()
    s = _by_iid(stories, "13")
    assert s["stage_id"] == "story-review"


def test_weak_link_approved_without_review_gives_automation_stage(repo):
    _write_escalations(_qaready_line(14, "ts", "T", resolved="s"))
    _write_registry([_feature("feat-a", story=14)])
    repo.test_case("TC-907", "Approved", extra="features: [feat-a]\n")
    repo.test_case("TC-908", "Automated", extra="features: [feat-a]\nautomation_status: active\n")
    stories, _warns = bs.collect_stories()
    s = _by_iid(stories, "14")
    assert s["stage_id"] == "story-automation"


def test_all_automated_gives_covered_stage(repo):
    _write_escalations(_qaready_line(15, "ts", "T", resolved="s"))
    _write_registry([_feature("feat-a", story=15)])
    repo.test_case("TC-909", "Automated", extra="features: [feat-a]\nautomation_status: active\n")
    stories, _warns = bs.collect_stories()
    s = _by_iid(stories, "15")
    assert s["stage_id"] == "story-covered"


# --- Merged (П1 Р0 п.5, spec-p1-dedup v7): дубль-кейс засчитан в «Покрыта» --

def test_merged_case_counts_toward_covered_stage(repo):
    """Зона с ОДНИМ Automated и ОДНИМ Merged кейсом — «Покрыта», не «слабое
    звено» (Merged добавлен в unknown_cases-исключение и в all()-проверку)."""
    _write_escalations(_qaready_line(21, "ts", "T", resolved="s"))
    _write_registry([_feature("feat-a", story=21)])
    repo.test_case("TC-920", "Automated", extra="features: [feat-a]\nautomation_status: active\n")
    repo.test_case("TC-921", "Merged", extra=(
        "features: [feat-a]\nautomated_by: \"\"\nautomation_status: \"\"\n"
        "merged_into: TC-920\n"))
    stories, _warns = bs.collect_stories()
    s = _by_iid(stories, "21")
    assert s["stage_id"] == "story-covered"


def test_merged_only_zone_is_covered_all_merged(repo):
    """Граница: ВСЕ кейсы зоны — Merged (0 Automated) — всё ещё «Покрыта»
    (all() над {Automated, Merged}, не только «есть хоть один Automated»)."""
    _write_escalations(_qaready_line(22, "ts", "T", resolved="s"))
    _write_registry([_feature("feat-a", story=22)])
    repo.test_case("TC-922", "Merged", extra=(
        "features: [feat-a]\nautomated_by: \"\"\nautomation_status: \"\"\n"
        "merged_into: TC-900\n"))
    stories, _warns = bs.collect_stories()
    s = _by_iid(stories, "22")
    assert s["stage_id"] == "story-covered"


def test_merged_case_excluded_from_green_badge_denominator(repo):
    """Знаменатель бейджа «зелёные в RUN» — БЕЗ Merged (у него automated_by
    пуст, он никогда не появится в tc_results): 1 Automated + 1 Merged
    зоны -> знаменатель 1, не 2."""
    _write_escalations(_qaready_line(23, "ts", "T", resolved="s"))
    _write_registry([_feature("feat-a", story=23)])
    repo.test_case("TC-923", "Automated", extra="features: [feat-a]\nautomation_status: active\n")
    repo.test_case("TC-924", "Merged", extra=(
        "features: [feat-a]\nautomated_by: \"\"\nautomation_status: \"\"\n"
        "merged_into: TC-923\n"))
    repo.run("RUN-20260501-0000", "Closed", extra="tc_results: { TC-923: passed }\n")
    stories, _warns = bs.collect_stories()
    s = _by_iid(stories, "23")
    assert any("зелёные в RUN-20260501-0000: 1/1" in b for b in s["badges"])


# --- «Покрыта»: последний прогон + отсутствие TC в tc_results --------------

def test_covered_stage_green_badge_uses_latest_run_by_id(repo):
    _write_escalations(_qaready_line(16, "ts", "T", resolved="s"))
    _write_registry([_feature("feat-a", story=16)])
    repo.test_case("TC-910", "Automated", extra="features: [feat-a]\nautomation_status: active\n")
    repo.run("RUN-20260101-0000", "Closed", extra="tc_results: { TC-910: failed }\n")
    repo.run("RUN-20260201-0000", "Closed", extra="tc_results: { TC-910: passed }\n")  # max id — этот
    stories, _warns = bs.collect_stories()
    s = _by_iid(stories, "16")
    assert any("зелёные в RUN-20260201-0000: 1/1" in b for b in s["badges"])


def test_covered_stage_tc_absent_from_latest_run_not_green_but_no_crash(repo):
    _write_escalations(_qaready_line(17, "ts", "T", resolved="s"))
    _write_registry([_feature("feat-a", story=17), _feature("feat-b", story=17)])
    repo.test_case("TC-911", "Automated", extra="features: [feat-a]\nautomation_status: active\n")
    repo.test_case("TC-912", "Automated", extra="features: [feat-b]\nautomation_status: active\n")
    # Последний прогон несёт результат только ОДНОГО из двух TC зоны.
    repo.run("RUN-20260301-0000", "Closed", extra="tc_results: { TC-911: passed }\n")
    stories, _warns = bs.collect_stories()
    s = _by_iid(stories, "17")
    assert any("зелёные в RUN-20260301-0000: 1/2" in b for b in s["badges"])


def test_covered_stage_no_run_at_all_omits_green_badge(repo):
    _write_escalations(_qaready_line(18, "ts", "T", resolved="s"))
    _write_registry([_feature("feat-a", story=18)])
    repo.test_case("TC-913", "Automated", extra="features: [feat-a]\nautomation_status: active\n")
    stories, _warns = bs.collect_stories()
    s = _by_iid(stories, "18")
    assert not any(b.startswith("зелёные в") for b in s["badges"])


def test_covered_stage_no_zone_tc_present_in_latest_run_omits_badge(repo):
    """TC зоны существуют, но НИ ОДИН не встречается в tc_results последнего
    прогона (прогон бьёт другую область) — бейдж отсутствует целиком, не
    показывает "0/N зелёных" (легенда: отсутствие бейджа ≠ красное)."""
    _write_escalations(_qaready_line(19, "ts", "T", resolved="s"))
    _write_registry([_feature("feat-a", story=19)])
    repo.test_case("TC-914", "Automated", extra="features: [feat-a]\nautomation_status: active\n")
    repo.run("RUN-20260401-0000", "Closed", extra="tc_results: { TC-999: passed }\n")
    stories, _warns = bs.collect_stories()
    s = _by_iid(stories, "19")
    assert not any(b.startswith("зелёные в") for b in s["badges"])


def test_covered_stage_quarantine_badge(repo):
    _write_escalations(_qaready_line(20, "ts", "T", resolved="s"))
    _write_registry([_feature("feat-a", story=20)])
    repo.test_case("TC-915", "Automated",
                    extra="features: [feat-a]\nautomation_status: quarantined\n")
    stories, _warns = bs.collect_stories()
    s = _by_iid(stories, "20")
    assert any(b.startswith("автотестов в карантине: 1") for b in s["badges"])


# --- багов на кейсах стори (Б9), оба канала ---------------------------------

def test_bugs_channel_a_open_bug_on_zone_tc(repo):
    _write_escalations(_qaready_line(21, "ts", "T", resolved="s"))
    _write_registry([_feature("feat-a", story=21)])
    repo.test_case("TC-916", "Review", extra="features: [feat-a]\n")
    repo.bug("BUG-916", "Open", extra='test_cases: ["TC-916"]\n')
    stories, _warns = bs.collect_stories()
    s = _by_iid(stories, "21")
    assert "BUG-916" in s["bug_keys"]
    assert any("багов на кейсах стори: 1" in b for b in s["badges"])


def test_bugs_channel_a_verified_bug_excluded(repo):
    _write_escalations(_qaready_line(22, "ts", "T", resolved="s"))
    _write_registry([_feature("feat-a", story=22)])
    repo.test_case("TC-917", "Review", extra="features: [feat-a]\n")
    repo.bug("BUG-917", "Verified", extra='test_cases: ["TC-917"]\n')
    stories, _warns = bs.collect_stories()
    s = _by_iid(stories, "22")
    assert s["bug_keys"] == []


def test_bugs_channel_b_red_lock_open_bug_counted(repo):
    _write_escalations(_qaready_line(23, "ts", "T", resolved="s"))
    _write_registry([_feature("feat-a", story=23)])
    repo.test_case("TC-918", "Review", extra="features: [feat-a]\nred_lock: BUG-918\n")
    repo.bug("BUG-918", "Open")
    stories, _warns = bs.collect_stories()
    s = _by_iid(stories, "23")
    assert "BUG-918" in s["bug_keys"]


def test_bugs_channel_b_stale_red_lock_verified_bug_not_counted(repo):
    """Протухший замок Verified-бага счётчик не завышает (р.2 не-блокер 2)."""
    _write_escalations(_qaready_line(24, "ts", "T", resolved="s"))
    _write_registry([_feature("feat-a", story=24)])
    repo.test_case("TC-919", "Review", extra="features: [feat-a]\nred_lock: BUG-919\n")
    repo.bug("BUG-919", "Verified")
    stories, _warns = bs.collect_stories()
    s = _by_iid(stories, "24")
    assert s["bug_keys"] == []


# --- WARN двусторонний (M-SB4) ----------------------------------------------

def test_warn_a_resolved_qaready_no_registry_record(repo):
    _write_escalations(_qaready_line(30, "ts", "T", resolved="s"))
    stories, warns = bs.collect_stories()
    assert any("QAREADY-30" in w and "стратег забыл конвенцию" in w for w in warns)


def test_warn_b_registry_record_without_qaready_line(repo):
    _write_registry([_feature("feat-a", story=31)])
    stories, warns = bs.collect_stories()
    assert any("story:31" in w and "сирота" in w for w in warns)
    assert stories == []  # нет QAREADY-строки -> нет карточки вовсе


def test_no_warn_when_link_present_and_qaready_unresolved(repo):
    _write_escalations(_qaready_line(32, "ts", "T"))  # НЕ resolved
    _write_registry([_feature("feat-a", story=32)])
    stories, warns = bs.collect_stories()
    assert warns == []


# --- 0 сторей -> 0 карточек без падения --------------------------------------

def test_zero_stories_no_crash(repo):
    stories, warns = bs.collect_stories()
    assert stories == []
    assert warns == []
    bs.build()  # не должен упасть
    index = json.loads((bs.BOARD / ".trackstate" / "index" / "issues.json").read_text(encoding="utf-8"))
    assert not any(i["issueType"] == "story" for i in index)


# --- регресс сборки (v3.1) --------------------------------------------------

def test_regression_badge_no_matching_run_branch(repo):
    _write_escalations(_qaready_line(40, "ts", "T"))
    repo.app_under_test("2026-08-10T00:00:00Z")
    # source_commit по умолчанию НЕ пишет Repo.app_under_test — добавим явно.
    p = bs.REPO / "state" / "app-under-test.yaml"
    p.write_text(p.read_text(encoding="utf-8") + 'source_commit: "deadbeef00000000000000000000000000000000"\n',
                 encoding="utf-8")
    stories, _warns = bs.collect_stories()
    s = _by_iid(stories, "40")
    assert "регресс сборки: прогона ещё не было" in s["badges"]


def test_regression_badge_k_zero_dedup_old_bug_excluded(repo):
    """K=0: баг найден на этом RUN-id, но found_in — ДРУГОЙ (старый) коммит —
    это дедуп в старый баг, не новый дефект этой сборки. Заодно — Б2: только
    regression совпал, smoke явно назван «нет прогона»."""
    _write_escalations(_qaready_line(41, "ts", "T"))
    commit = "cafebabe11111111111111111111111111111111"
    p = bs.REPO / "state" / "app-under-test.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f'source_commit: "{commit}"\n', encoding="utf-8")
    repo.run("RUN-20260501-0000", "Triaged",
             extra=f'suite: regression\ntotals: {{ passed: 9, failed: 1, skipped: 0, quarantined: 0 }}\n'
                   f'source_commit: "{commit}"\n')
    repo.bug("BUG-950", "Open", extra='runs: ["RUN-20260501-0000"]\nfound_in: "build oldcommit"\n')
    stories, _warns = bs.collect_stories()
    s = _by_iid(stories, "41")
    assert ("регресс сборки: smoke: нет прогона на этой сборке · "
            "regression RUN-20260501-0000 9/10 · разобрано · "
            "новых багов в прогоне: 0") in s["badges"]


def test_regression_badge_k_one_new_bug_counted(repo):
    """K=1: found_in несёт короткий хэш текущего source_commit (8 символов) —
    новый дефект этой сборки. Заодно — Б2: только smoke совпал, regression
    явно назван «нет прогона»."""
    _write_escalations(_qaready_line(42, "ts", "T"))
    commit = "6f884d979a5c19465c6d8647737376864f424555"
    p = bs.REPO / "state" / "app-under-test.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f'source_commit: "{commit}"\n', encoding="utf-8")
    repo.run("RUN-20260601-0000", "NeedsTriage",
             extra='suite: smoke\ntotals: { passed: 5, failed: 0, skipped: 0, quarantined: 0 }\n'
                   f'source_commit: "{commit}"\n')
    repo.bug("BUG-951", "Open", extra='runs: ["RUN-20260601-0000"]\nfound_in: "build 6f884d97"\n')
    stories, _warns = bs.collect_stories()
    s = _by_iid(stories, "42")
    assert ("регресс сборки: smoke RUN-20260601-0000 5/5 · разбирается · "
            "regression: нет прогона на этой сборке · "
            "новых багов в прогоне: 1") in s["badges"]


def test_regression_badge_partial_suite_match_names_missing_suite_explicitly(repo):
    """Б2 (критик-проба): smoke текущей сборки есть, regression — нет. Прежний
    агрегированный формат («48/49 · чисто») молчал о regression вовсе —
    теперь явная строка «regression: нет прогона на этой сборке», НЕ ветка
    «прогона ещё не было» целиком (та легальна только когда ОБА suite пусты)."""
    _write_escalations(_qaready_line(45, "ts", "T"))
    commit = "aaaa11122223333444455556666777788889999"
    p = bs.REPO / "state" / "app-under-test.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f'source_commit: "{commit}"\n', encoding="utf-8")
    repo.run("RUN-20260901-0000", "Closed",
             extra='suite: smoke\ntotals: { passed: 48, failed: 1, skipped: 0, quarantined: 0 }\n'
                   f'source_commit: "{commit}"\n')
    stories, _warns = bs.collect_stories()
    s = _by_iid(stories, "45")
    badge = next(b for b in s["badges"] if b.startswith("регресс сборки"))
    assert "smoke RUN-20260901-0000 48/49 · чисто" in badge
    assert "regression: нет прогона на этой сборке" in badge
    assert badge != "регресс сборки: прогона ещё не было"


def test_regression_badge_both_suites_matched_shows_both_segments(repo):
    _write_escalations(_qaready_line(46, "ts", "T"))
    commit = "bbbb11122223333444455556666777788889999"
    p = bs.REPO / "state" / "app-under-test.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f'source_commit: "{commit}"\n', encoding="utf-8")
    repo.run("RUN-20261001-0000", "Triaged",
             extra='suite: smoke\ntotals: { passed: 10, failed: 0, skipped: 0, quarantined: 0 }\n'
                   f'source_commit: "{commit}"\n')
    repo.run("RUN-20261001-0100", "NeedsTriage",
             extra='suite: regression\ntotals: { passed: 20, failed: 2, skipped: 0, quarantined: 0 }\n'
                   f'source_commit: "{commit}"\n')
    stories, _warns = bs.collect_stories()
    s = _by_iid(stories, "46")
    badge = next(b for b in s["badges"] if b.startswith("регресс сборки"))
    assert badge == (
        "регресс сборки: smoke RUN-20261001-0000 10/10 · разобрано · "
        "regression RUN-20261001-0100 20/22 · разбирается · "
        "новых багов в прогоне: 0"
    )


def test_regression_badge_k_matches_7_char_hex_token_prefix(repo):
    """Б3б (критик-проба, живой прецедент bugs/BUG-050..052.md «commit
    63f6aac»): found_in несёт 7-символьный (не 8) hex-токен — обязан
    матчиться ПРЕФИКСОМ current_commit."""
    _write_escalations(_qaready_line(47, "ts", "T"))
    commit = "63f6aac3b1ea1dfad82f68b8196aa6cf56f41853"
    p = bs.REPO / "state" / "app-under-test.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f'source_commit: "{commit}"\n', encoding="utf-8")
    repo.run("RUN-20261101-0000", "Closed",
             extra='suite: regression\ntotals: { passed: 3, failed: 0, skipped: 0, quarantined: 0 }\n'
                   f'source_commit: "{commit}"\n')
    repo.bug("BUG-952", "Open",
             extra='runs: ["RUN-20261101-0000"]\nfound_in: "1.10 (versionCode 11), commit 63f6aac"\n')
    stories, _warns = bs.collect_stories()
    s = _by_iid(stories, "47")
    assert "новых багов в прогоне: 1" in next(b for b in s["badges"] if b.startswith("регресс сборки"))


def test_regression_badge_k_six_char_hex_token_below_threshold_not_matched(repo):
    """Граница СНИЗУ: hex-токен ДЛИНОЙ 6 (< 7) НЕ считается идентификатором
    коммита — не матчится, даже если он буквально является префиксом текущего
    commit (rule 6a: тест на границе и за ней)."""
    _write_escalations(_qaready_line(48, "ts", "T"))
    commit = "abc123deadbeef0000000000000000000000000"
    p = bs.REPO / "state" / "app-under-test.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f'source_commit: "{commit}"\n', encoding="utf-8")
    repo.run("RUN-20261201-0000", "Closed",
             extra='suite: regression\ntotals: { passed: 1, failed: 0, skipped: 0, quarantined: 0 }\n'
                   f'source_commit: "{commit}"\n')
    # "abc123" — ровно 6 hex-символов, префикс commit, НО короче порога.
    repo.bug("BUG-953", "Open",
             extra='runs: ["RUN-20261201-0000"]\nfound_in: "build abc123 (short)"\n')
    stories, _warns = bs.collect_stories()
    s = _by_iid(stories, "48")
    assert "новых багов в прогоне: 0" in next(b for b in s["badges"] if b.startswith("регресс сборки"))


def test_found_in_matches_commit_helper_boundary():
    commit = "deadbeef00112233445566778899aabbccddeeff"  # первые 7 = "deadbee", первые 8 = "deadbeef"
    assert bs._found_in_matches_commit("build deadbee (7 chars, exact prefix)", commit) is True
    assert bs._found_in_matches_commit("build deadbeef (8 chars, exact prefix)", commit) is True
    assert bs._found_in_matches_commit("build deadbe (6 chars — под порогом ≥7)", commit) is False
    assert bs._found_in_matches_commit("build 1234567 (7 chars, wrong value)", commit) is False


def test_regression_badge_run_source_commit_mismatch_excluded(repo):
    """Прогон существует, но его source_commit — ДРУГАЯ сборка — не матчится,
    ветка «прогона ещё не было»."""
    _write_escalations(_qaready_line(43, "ts", "T"))
    p = bs.REPO / "state" / "app-under-test.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('source_commit: "currentcommit0000000000000000000000000"\n', encoding="utf-8")
    repo.run("RUN-20260701-0000", "Closed",
             extra='suite: regression\ntotals: { passed: 1, failed: 0, skipped: 0, quarantined: 0 }\n'
                   'source_commit: "othercommit000000000000000000000000000"\n')
    stories, _warns = bs.collect_stories()
    s = _by_iid(stories, "43")
    assert "регресс сборки: прогона ещё не было" in s["badges"]


def test_regression_badge_legacy_run_without_source_commit_excluded(repo):
    """Легаси-run без поля source_commit вовсе (до 2026-08-10) — не берётся в
    кандидаты (run.schema.yaml: опционален для прогонов до 2026-08-10)."""
    _write_escalations(_qaready_line(44, "ts", "T"))
    p = bs.REPO / "state" / "app-under-test.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('source_commit: "currentcommit0000000000000000000000000"\n', encoding="utf-8")
    repo.run("RUN-20260801-0000", "Closed",
             extra='suite: regression\ntotals: { passed: 1, failed: 0, skipped: 0, quarantined: 0 }\n')
    stories, _warns = bs.collect_stories()
    s = _by_iid(stories, "44")
    assert "регресс сборки: прогона ещё не было" in s["badges"]


def test_regression_badge_same_on_every_card(repo):
    _write_escalations(
        _qaready_line(45, "ts", "T45"),
        _qaready_line(46, "ts", "T46"),
    )
    stories, _warns = bs.collect_stories()
    s45 = _by_iid(stories, "45")
    s46 = _by_iid(stories, "46")
    badge45 = next(b for b in s45["badges"] if b.startswith("регресс сборки"))
    badge46 = next(b for b in s46["badges"] if b.startswith("регресс сборки"))
    assert badge45 == badge46


# --- STATUS_MAP-зеркало tc-awaiting-review (read-only инвариант) -----------

def test_story_stages_not_in_status_map():
    for sid in bs.STORY_STAGE_IDS:
        assert sid not in bs.STATUS_MAP.get("test-case", {}).values()
        assert sid not in bs.STATUS_MAP.get("bug", {}).values()
        assert sid not in bs.STATUS_MAP.get("run", {}).values()
    assert "story" not in bs.STATUS_MAP


def test_story_workflow_has_no_board_transitions():
    """machine "story" не существует в schemas/transitions.yaml -> нет кнопок
    переходов вовсе (read-only)."""
    cfg = bs._workflows_config()
    assert cfg["story-workflow"]["transitions"] == []
    assert cfg["story-workflow"]["statuses"] == bs.STORY_STAGE_IDS


def test_story_issue_type_registered():
    ids = {t["id"] for t in bs.ISSUE_TYPES}
    assert "story" in ids


def test_story_hierarchy_level_is_zero(repo):
    """Критик-вход Б4 (решение Lead): уровня 1 в этом репо никогда не было —
    story идёт на том же hierarchyLevel 0, что test-case/bug/run."""
    story_type = next(t for t in bs.ISSUE_TYPES if t["id"] == "story")
    assert story_type["hierarchyLevel"] == 0
    for t in bs.ISSUE_TYPES:
        if t["id"] != "story":
            assert t["hierarchyLevel"] == 0  # паритет с остальными типами


# --- статус вне enum: слабое звено + WARN (не-блокер критик-входа) ----------

def test_unknown_tc_status_forces_stage2_with_warn_not_silent_covered(repo):
    """Раньше ЛЮБОЙ статус, не пойманный явными Review/Approved-ветками, молча
    утекал в "Покрыта" (else без проверки). Статус вне enum test-case.schema.yaml
    обязан трактоваться как слабое звено + WARN, не падать и не давать
    ложное "Покрыта"."""
    _write_escalations(_qaready_line(70, "ts", "T", resolved="s"))
    _write_registry([_feature("feat-a", story=70)])
    repo.test_case("TC-970", "TotallyUnknownStatus", extra="features: [feat-a]\n")
    stories, warns = bs.collect_stories()
    s = _by_iid(stories, "70")
    assert s["stage_id"] == "story-writing-cases"
    assert any("TC-970" in w and "TotallyUnknownStatus" in w for w in warns)


def test_unknown_tc_status_among_otherwise_automated_zone_still_stage2(repo):
    """Смешанная зона: один TC Automated, другой — статус вне enum. НЕ должно
    молча дать "Покрыта" по одному только "нет Review/Approved в множестве"."""
    _write_escalations(_qaready_line(71, "ts", "T", resolved="s"))
    _write_registry([_feature("feat-a", story=71), _feature("feat-b", story=71)])
    repo.test_case("TC-971", "Automated", extra="features: [feat-a]\nautomation_status: active\n")
    repo.test_case("TC-972", "Corrupted", extra="features: [feat-b]\n")
    stories, warns = bs.collect_stories()
    s = _by_iid(stories, "71")
    assert s["stage_id"] == "story-writing-cases"
    assert any("TC-972" in w and "Corrupted" in w for w in warns)


# --- board_sync.build(): карточки отдельным проходом, итоговая разбивка ----

def test_build_writes_story_cards_and_summary_breakdown(repo, capsys):
    _write_escalations(_qaready_line(50, "ts", "T50"))
    bs.build()
    out = capsys.readouterr().out
    assert "story-50: стадия Обнаружена" in out
    assert "1 story)" in out

    index = json.loads((bs.BOARD / ".trackstate" / "index" / "issues.json").read_text(encoding="utf-8"))
    story_entries = [i for i in index if i["issueType"] == "story"]
    assert len(story_entries) == 1
    assert story_entries[0]["key"] == "story-50"
    assert story_entries[0]["status"] == "story-detected"

    main = (bs.BOARD / "story-50" / "main.md").read_text(encoding="utf-8")
    assert 'issueType: "story"' in main


def test_build_does_not_pollute_status_map_cycle(repo):
    """Никакого KeyError на STATUS_MAP[itype][status_str] для itype "story" —
    карточки идут отдельным проходом мимо этого цикла (M-SB3)."""
    _write_escalations(_qaready_line(51, "ts", "T51"))
    bs.build()  # не должен упасть


# --- board_inbound: read-only инвариант (board_inbound про story не знает) --

def test_board_inbound_ignores_story_cards_entirely(repo):
    _write_escalations(_qaready_line(52, "ts", "T52"))
    bs.build()

    # Человек «подвинул» story-карточку на борде — пишем произвольный
    # неизвестный board_inbound-у статус прямо в main.md (без Repo.board_card,
    # та жёстко резолвит статус через bs.STATUS_MAP[itype], которого у "story"
    # нет).
    story_main = bs.REPO / "board" / "story-52" / "main.md"
    text = story_main.read_text(encoding="utf-8")
    text = text.replace('status: "story-detected"', 'status: "story-covered"')
    story_main.write_text(text, encoding="utf-8")

    actions = bi.reconcile(dry=True)
    assert not any(a.key == "story-52" for a in actions)

    # Артефакты, от которых story синтезируется, board_inbound не трогает —
    # escalations.md остаётся тем же (никакой Blocked/апдейт).
    esc_after = (bs.REPO / "state" / "escalations.md").read_text(encoding="utf-8")
    assert "story-52" not in esc_after


# --- board_view: рендер, отсутствие approve/priority/severity контролов ----

def test_board_view_story_column_renders_badges_and_lists(repo):
    _write_escalations(_qaready_line(60, "ts", "T60"))
    _write_registry([_feature("feat-a", story=60)])
    repo.test_case("TC-960", "Review", extra="features: [feat-a]\n")

    by_type = bv.collect()
    assert len(by_type["story"]) == 1
    html_str = bv.render(by_type, live=True)

    assert "story-60" in html_str
    assert "TC-960" in html_str
    # НЕТ approve/priority/severity-контролов на story-карточке (изолируем
    # секцию Stories от JS-функций approveCard/setPriority, которые всегда
    # присутствуют в <script> ниже, но не должны быть ВЫЗВАНЫ из story-карточки).
    # Секция Stories теперь ПЕРВАЯ (слово владельца 2026-08-10) — режем до
    # СЛЕДУЮЩЕГО <h2>, а не до конца документа (прежний срез захватывал чужие
    # секции с approve-контролами и давал ложный провал инварианта read-only).
    story_section = html_str.split("<h2>Stories")[1].split("<h2>")[0]
    assert "onclick=\"event.stopPropagation(); approveCard(" not in story_section
    assert "pri-select" not in story_section
    assert "class=\"approve\"" not in story_section


def test_board_view_collect_includes_story_key_even_when_empty(repo):
    by_type = bv.collect()
    assert by_type["story"] == []
