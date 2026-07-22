"""Область performance/stability (test-cases/performance/, TC-096..099,
docs/01-test-strategy.md §9 area E2): относительные бюджеты/тренды, НЕ
абсолютные SLA — эмулятор существенно медленнее/вариативнее реального
устройства, разброс таймингов AVD ожидаем и сам по себе не дефект.
"""
from __future__ import annotations

import statistics

import allure
import pytest

from framework.data import recording_builder as rb
from framework.data import works as W
from framework.steps import app_steps, browser_steps, library_steps, perf_steps, rating_steps, settings_steps

# Реально записанная домашняя страница archiveofourown.org (спайк B, см.
# `framework/tests/canary/test_ao3_selectors.py::AO3_HOME_SMOKE_FILENAME` —
# та же константа, определена здесь локально по тому же паттерну модуля,
# без кросс-импорта между тест-модулями).
AO3_HOME_SMOKE_FILENAME = "ao3_home_smoke.mitm"

# Множитель щедрого относительного запаса над МЕДИАНОЙ baseline-прогонов
# (решение test-automator, 2026-07-22, документируется здесь и в TC-096/
# TC-097.md): x2.5 — заведомо больше наблюдаемого разброса AVD-таймингов
# (единичная живая калибровка на emulator-5554 при написании этого теста:
# тёплый повторный старт даёт TotalTime=0мс/WaitTime=15мс, холодный —
# TotalTime=3728мс — контраст на порядки; x2.5 НАД медианой именно холодных
# прогонов ловит реальную деградацию (напр. кратный рост), не единичное
# дрожание эмулятора). BASELINE_RUNS=5 — эмпирическое «несколько прогонов»
# из кейса: достаточно для устойчивой медианы, не настолько много, чтобы
# сделать P1-тест избыточно дорогим.
BUDGET_MULTIPLIER = 2.5
BASELINE_RUNS = 5
# Пол бюджета — защита от вырожденно малой медианы (напр. один прогон почти
# 0мс из-за аномалии среды): без пола x2.5*медиана могла бы дать бюджет,
# который наблюдаемый шум эмулятора тривиально пробивает, породив ложный fail
# не о регрессии, а о калибровке.
MIN_COLD_START_BUDGET_MS = 500
MIN_WEBVIEW_LOAD_BUDGET_S = 1.0


@pytest.mark.p1
@allure.id("TC-096")
@allure.title("Холодный старт укладывается в относительный бюджет TotalTime/WaitTime (am start -W)")
def test_cold_start_within_relative_budget(driver):
    # Given baseline — BASELINE_RUNS холодных стартов на этом же эмуляторе
    # (force-stop+pm clear перед КАЖДЫМ — гарантирует, что это действительно
    # холодные старты, а не тёплые no-op с TotalTime=0, см. TC-096.md)
    baseline = perf_steps.cold_start_baseline(BASELINE_RUNS)
    median_total = statistics.median(m["TotalTime"] for m in baseline)
    median_wait = statistics.median(m["WaitTime"] for m in baseline)
    budget_total_ms = max(median_total * BUDGET_MULTIPLIER, MIN_COLD_START_BUDGET_MS)
    budget_wait_ms = max(median_wait * BUDGET_MULTIPLIER, MIN_COLD_START_BUDGET_MS)

    # When ещё один холодный старт замеряется как наблюдаемый (независимый
    # прогон, не входит в baseline — не самосравнение с самим собой)
    observed = perf_steps.measure_cold_start()

    # Then TotalTime и WaitTime укладываются в щедрый относительный бюджет
    assert observed["TotalTime"] <= budget_total_ms, (
        f"холодный старт TotalTime={observed['TotalTime']}ms превышает относительный "
        f"бюджет {budget_total_ms:.0f}ms (медиана {BASELINE_RUNS} baseline-прогонов="
        f"{median_total:.0f}ms x{BUDGET_MULTIPLIER})"
    )
    assert observed["WaitTime"] <= budget_wait_ms, (
        f"холодный старт WaitTime={observed['WaitTime']}ms превышает относительный "
        f"бюджет {budget_wait_ms:.0f}ms (медиана {BASELINE_RUNS} baseline-прогонов="
        f"{median_wait:.0f}ms x{BUDGET_MULTIPLIER})"
    )
    # And приложение фактически запущено (нативная оболочка отрисована)
    app_steps.wait_ui_ready(driver)


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-097")
@allure.title("Первая загрузка WebView укладывается в относительный бюджет до сигнала завершения загрузки (replay)")
@pytest.mark.parametrize("replay", [AO3_HOME_SMOKE_FILENAME], indirect=True)
def test_webview_first_load_within_relative_budget(clean_app, replay, driver):
    # Given приложение запущено в replay-режиме на ao3_home_smoke.mitm, домашняя
    # страница уже единожды загрузилась штатным стартом приложения (эта загрузка
    # НЕ входит в замер — только явные повторные навигации ниже)
    app_steps.wait_home_ready_for_deep_link(driver)

    # Given baseline — BASELINE_RUNS повторных навигаций на этой же replay-записи
    # (server_replay_reuse=true — повторный запрос того же URL отдаёт тот же
    # записанный ответ детерминированно, см. framework/core/mitm.py::start_replay)
    baseline = perf_steps.webview_load_baseline(driver, BASELINE_RUNS)
    median = statistics.median(baseline)
    budget_s = max(median * BUDGET_MULTIPLIER, MIN_WEBVIEW_LOAD_BUDGET_S)

    # When ещё одна навигация замеряется как наблюдаемая
    observed = perf_steps.measure_home_page_load_time(driver)

    # Then время от навигации до __ao3AppDark укладывается в относительный бюджет
    assert observed <= budget_s, (
        f"загрузка WebView заняла {observed:.2f}s, бюджет {budget_s:.2f}s (медиана "
        f"{BASELINE_RUNS} baseline-прогонов={median:.2f}s x{BUDGET_MULTIPLIER})"
    )


@pytest.mark.p0
@pytest.mark.live
@allure.id("TC-098")
@allure.title("Отсутствие FATAL EXCEPTION/ANR в logcat при прогоне P0-smoke")
@pytest.mark.parametrize("placeholder_seeded_work", [W.LOVED], indirect=True)
def test_no_crash_or_anr_during_smoke_path(placeholder_seeded_work, driver):
    work = placeholder_seeded_work
    # Given logcat очищен непосредственно перед сценарием
    perf_steps.logcat_clear_before_scenario()

    # When пользователь проходит представительный smoke-путь: запуск → Browse
    # (домашняя AO3-страница, TC-001)
    app_steps.wait_app_ready(driver)
    # → Library (TC-006)
    app_steps.open_tab(driver, "Library")
    library_steps.assert_library_loaded(driver)
    # → Settings (TC-002)
    app_steps.open_tab(driver, "Settings")
    settings_steps.assert_settings_loaded(driver)
    # → простановка рейтинга Loved на существующей засеянной работе (TC-007:
    # панель RatingMenu рендерится только на вкладке Browse)
    app_steps.open_tab(driver, "Browse")
    rating_steps.open_work_page(driver, work.ao3_id)
    rating_steps.rate_current_work(driver, "SAVE")
    app_steps.open_tab(driver, "Library")
    library_steps.assert_work_in_tab(driver, "SAVE", work.title)

    # Then захваченный logcat не содержит FATAL EXCEPTION/ANR своего пакета
    # (testability gap на ANR-часть — см. perf_steps.assert_no_crash_or_anr
    # докстринг/TC-098.md «Заметки для автоматизации»)
    perf_steps.assert_no_crash_or_anr()


@pytest.mark.p0
@pytest.mark.replay
@allure.id("TC-099")
@allure.title("Память не растёт безоткатно за длинную WebView-сессию до 10 табов")
@pytest.mark.parametrize("replay", [rb.LISTING_BASIC_FILENAME], indirect=True)
def test_memory_trend_recovers_after_closing_tabs(replay, clean_app, driver):
    """Инвариант: рост памяти в длинной WebView-сессии (до MAX_TABS=10) обратим —
    за закрытием вкладок следует наблюдаемое снижение PSS относительно
    локального пика, а не монотонное удержание у пика/дальнейший рост.
    Критерий — ТРЕНД по трём точкам замера (baseline → пик → откат), не
    абсолютный порог PSS в МБ (docs/01-test-strategy.md §9; см. также
    операционализацию критерия в `perf_steps.assert_memory_trend_recovered`)."""
    app_steps.wait_home_ready_for_deep_link(driver)

    # Given baseline (1 вкладка Home, уже загружена) — TOTAL PSS
    baseline_pss = perf_steps.measure_total_pss()

    # When открыто 10 вкладок (MAX_TABS, тот же механизм добавления вкладки, что
    # TC-022): исходная Home-вкладка (уже реальный AO3-контент от штатного
    # старта) + 9 через deep-link на listing_basic.mitm (реальная навигация —
    # WebView-нагрузка в каждой; server_replay_reuse=true допускает повтор одной
    # и той же записи без исчерпания)
    for _ in range(9):
        app_steps.open_deep_link(rb.LISTING_BASIC_URL)
    browser_steps.assert_tab_strip_visible(driver, timeout=10)
    browser_steps.assert_tab_limit_dialog_not_shown(driver)
    # Пик СНИМАЕТСЯ ПОСЛЕ settle (фикс rejected attempt 1, critic-вход
    # perf-batch-096-099-review, 2026-07-22): сырой замер сразу после шторма
    # открытия 9 вкладок транзиентно раздут (незавершённые
    # аллокации/неотработавший GC) — без settle это раздутие маскировало
    # безоткатную утечку под ложный "возврат" при последующем оседании,
    # см. `perf_steps.wait_memory_settled` докстринг и
    # `perf_steps.MEMORY_RECOVERY_FRACTION` за эмпирикой обоих контролей.
    peak_pss = perf_steps.wait_memory_settled()

    # And пользователь закрывает 9 из 10 вкладок обратно до 1 (swipe-up по
    # позиции 0, тот же механизм, что TC-023/024), даёт WebView-процессу время
    # осесть (опрос TOTAL PSS до стабилизации, НЕ sleep)
    for _ in range(9):
        browser_steps.swipe_close_tab(driver, 0)
    after_close_pss = perf_steps.wait_memory_settled()

    # Then третий замер (после закрытия 9 вкладок) ближе к baseline, чем к пику
    # — память откатывается вниз после освобождения ресурсов
    perf_steps.assert_memory_trend_recovered(baseline_pss, peak_pss, after_close_pss)
