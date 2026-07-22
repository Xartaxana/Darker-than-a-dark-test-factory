"""Бизнес-шаги нефункциональной области performance/stability (TC-096..099,
test-cases/performance/, docs/01-test-strategy.md §9 area E2).

Ни один замер здесь не вводит НОВЫХ локаторов/маркеров: TC-097 переиспользует
уже существующий JS-маркер `window.__ao3AppDark`
(`framework/screens/browser_screen.py::BrowserScreen.wait_home_page_loaded`),
TC-096/TC-099 — генерические adb-примитивы (`framework/core/adb.py`). Этот
модуль — только композиция (GWT, allure.step), как и остальные steps/*.
"""
from __future__ import annotations

import time

import allure

from framework.config import settings
from framework.core import adb, contexts
from framework.core.navigate import navigate
from framework.core.waits import wait_for
from framework.screens.browser_screen import BrowserScreen
from framework.steps import browser_steps


# --- TC-096: холодный старт (am start -W TotalTime/WaitTime) ---

@allure.step("Given/When холодный старт приложения замерен (force-stop+pm clear+am start -W)")
def measure_cold_start(timeout: float | None = None) -> dict[str, int]:
    """Гарантирует ХОЛОДНЫЙ старт: `force_stop()` + `clear_app_data()` ДО
    запуска — иначе `am start -W` для уже запущенного процесса тривиально
    вернёт `TotalTime: 0` (см. `adb.parse_am_start_metrics`), не измеряя
    реальный холодный путь (TC-096.md «Заметки для автоматизации»/«Given»).
    Возвращает `{'TotalTime': мс, 'WaitTime': мс}`."""
    adb.force_stop()
    adb.clear_app_data()
    output = adb.shell(
        f"am start -W -n {settings.APP_PACKAGE}/{settings.APP_ACTIVITY}",
        timeout=timeout or settings.ADB_LAUNCH_TIMEOUT,
    )
    return adb.parse_am_start_metrics(output)


@allure.step("Given baseline холодного старта: {n} прогонов на этом эмуляторе")
def cold_start_baseline(n: int = 5) -> list[dict[str, int]]:
    return [measure_cold_start() for _ in range(n)]


# --- TC-097: первая загрузка WebView (replay) до появления __ao3AppDark ---

@allure.step("When замерено время загрузки домашней AO3-страницы (навигация → __ao3AppDark)")
def measure_home_page_load_time(driver, timeout: int | None = None) -> float:
    """Засекает время МЕЖДУ навигацией (`driver.get`) и появлением JS-маркера
    `window.__ao3AppDark` — момент начала отсчёта ЭТОЙ функции (не запуск
    процесса, см. TC-097.md «не смешивать с TC-096»). Маркер и его семантика
    (флаг тёмной темы, пушится синхронно внутри `onPageFinished`, детерминированный
    признак «страница догрузилась», НЕ маркер готовности bridge) уже определены и
    опрашиваются существующим кодом — `BrowserScreen.wait_home_page_loaded`;
    здесь только временная обвязка вокруг него, локатор/маркер не дублируется.

    Сам `driver.get()` — ЧАСТЬ измеряемого интервала (не обёрнут
    `WEBVIEW_LOAD_TIMEOUT`, как остальные call-site'ы `browser_steps.py`,
    AT-BUG-025/027 — это исказило бы замер того же порядка величины). Вместо
    этого используется measurement-safe fail-safe
    `settings.PERF_MEASUREMENT_HANG_GUARD` (на порядок больше любой
    правдоподобной длительности загрузки, см. обоснование числа в
    `settings.py`) — ловит только генуинный бесконечный хенг WebView
    (класс AT-BUG-025), не рабочий предел измерения; нормальная и даже
    заметно деградировавшая (но конечная) загрузка остаётся далеко под этой
    границей и замеряется точно, без искажения."""
    screen = BrowserScreen(driver)
    start = time.monotonic()
    with contexts.in_webview(driver, timeout):
        navigate(driver, browser_steps.HOME_URL, settings.PERF_MEASUREMENT_HANG_GUARD)
    screen.wait_home_page_loaded(timeout)
    return time.monotonic() - start


@allure.step("Given baseline первой загрузки WebView: {n} прогонов на replay")
def webview_load_baseline(driver, n: int = 5, timeout: int | None = None) -> list[float]:
    return [measure_home_page_load_time(driver, timeout) for _ in range(n)]


# --- TC-098: отсутствие FATAL EXCEPTION / ANR в logcat при smoke-пути ---

@allure.step("Given logcat очищен")
def logcat_clear_before_scenario() -> None:
    adb.logcat_clear()


@allure.step("Then захваченный logcat не содержит FATAL EXCEPTION/ANR своего пакета")
def assert_no_crash_or_anr(lines: int = 4000) -> None:
    """Testability gap (ANR-часть — см. TC-098.md «Заметки для автоматизации»,
    docs/01-test-strategy.md §9 area E2): короткий представительный smoke-путь
    может не спровоцировать ANR вовсе (нужно устойчивое зависание UI-потока
    >5с) — отсутствие `ANR in <package>` здесь доказывает лишь «не произошло
    НА ЭТОМ прогоне», не «свободно от ANR-рисков в принципе». `FATAL
    EXCEPTION` — полноценно drivable часть (детерминированно пишется в logcat
    при любом необработанном исключении процесса приложения)."""
    text = adb.shell(f"logcat -d -t {lines}", timeout=settings.ADB_SHELL_TIMEOUT)
    assert "FATAL EXCEPTION" not in text, (
        "logcat содержит 'FATAL EXCEPTION' за время smoke-прогона — "
        "процесс приложения крашнулся"
    )
    anr_marker = f"ANR in {settings.APP_PACKAGE}"
    assert anr_marker not in text, (
        f"logcat содержит {anr_marker!r} — приложение поймало ANR за время smoke-прогона"
    )


# --- TC-099: memory sanity (TOTAL PSS, тренд baseline → пик → откат) ---

@allure.step("Then TOTAL PSS процесса приложения замерен (dumpsys meminfo)")
def measure_total_pss() -> int:
    return adb.total_pss_kb()


@allure.step("When памяти дано осесть до стабильного значения (опрос TOTAL PSS до стабилизации)")
def wait_memory_settled(timeout: int = 30, stable_ratio: float = 0.05) -> int:
    """ART/WebView освобождают память АСИНХРОННО (critic-caveat приёмки
    TC-099.md, 2026-07-21) — одноразовое чтение сразу после закрытия вкладок
    (или сразу после шторма открытия) ловит гонку с GC, а не реальное
    состояние. Опрашивает `adb.total_pss_kb()` через `core.waits.wait_for`
    (НЕ `sleep`), пока ДВА ПОДРЯД замера не разойдутся меньше чем на
    `stable_ratio` от предыдущего значения, либо не истечёт `timeout` — в
    обоих случаях возвращает ПОСЛЕДНИЙ прочитанный замер: best-effort settle
    (истечение таймаута не бросает исключение — финальное значение всё равно
    осмысленно, просто без гарантии полной стабилизации).

    **ИСПОЛЬЗУЕТСЯ ДВАЖДЫ в TC-099** (фикс rejected attempt 1, critic-вход
    приёмки perf-batch-096-099-review, 2026-07-22): и для пикового замера
    (сразу после шторма 9x `open_deep_link`), и для замера после отката
    (сразу после 9x `swipe_close_tab`). Attempt 1 снимал peak СЫРЫМ замером
    БЕЗ settle — транзиентная раздутость сразу после шторма открытия
    (незавершённые аллокации/ещё не отработавший GC) попадала в `peak_kb`,
    и последующее оседание этого транзиентного шума (безотносительно к
    закрытию вкладок) давало ложный "возврат" даже при НУЛЕВОМ закрытии
    вкладок (см. `MEMORY_RECOVERY_FRACTION` за эмпирикой негативного
    контроля). Settle ОБОИХ замеров (peak и after_close) устраняет этот шум
    из обеих сторон разности — учитывается только память, реально удерживаемая
    живыми вкладками, не шум GC вокруг момента замера."""
    readings: list[int] = []

    def _settled() -> bool:
        readings.append(adb.total_pss_kb())
        if len(readings) < 2:
            return False
        prev, cur = readings[-2], readings[-1]
        return abs(cur - prev) <= prev * stable_ratio

    try:
        wait_for(_settled, timeout=timeout, message="TOTAL PSS не стабилизировался")
    except TimeoutError:
        pass
    return readings[-1]


#: Минимальная доля РОСТА (peak-baseline), которую обязан вернуть откат
#: (peak-after_close).
#:
#: **История решения (не удалять — 2 витка калибровки):**
#:
#: Виток 1 (2026-07-22, живой прогон на emulator-5554): первая
#: операционализация («after_close ближе к baseline, чем к пику», т.е. >=50%
#: возврата) не прошла на РЕАЛЬНОМ здоровом поведении приложения —
#: baseline=152085KB, пик=164846KB (рост=12761KB), после отката 9 из 10
#: вкладок=158977KB (возврат=5869KB=46% роста). Заменено количественным
#: порогом MEMORY_RECOVERY_FRACTION=0.15.
#:
#: **Виток 1 порог 0.15 был ОШИБОЧЕН — не пропускал целевой класс дефекта
#: (rejected attempt 1, critic-вход приёмки perf-batch-096-099-review,
#: 2026-07-22).** Причина: `peak_kb` снимался СЫРЫМ замером сразу после
#: шторма открытия 9 вкладок, БЕЗ `wait_memory_settled` (settle вызывался
#: только перед третьим замером). Сырой пиковый замер транзиентно раздут
#: (незавершённые аллокации/неотработавший GC сразу после шторма открытия);
#: последующее оседание ЭТОГО транзиентного шума давало ложный "возврат"
#: даже при НУЛЕВОМ закрытии вкладок — эмпирика критика: негативный контроль
#: (0 из 10 вкладок закрыто = искусственная безоткатная утечка) давал
#: ~29.5-30.5% "возврата" — assert 0.15 НЕ упал бы на реальном дефекте.
#:
#: **Виток 2 (2026-07-22, attempt 2 фикс).** Peak ТЕПЕРЬ ТОЖЕ снимается через
#: `wait_memory_settled()` (не сырым замером) — оба замера, участвующие в
#: разности (`peak`, `after_close`), осевшие; транзиентный шум шторма
#: открытия больше не течёт ни в `growth_kb`, ни в `recovered_kb`. Порог
#: пересчитан на новых (осевших с обеих сторон) числах:
#: - Негативный контроль (0 из 10 вкладок закрыто, 2 живых прогона):
#:   growth=8847KB/recovered=91KB=1.03%; growth=8672KB/recovered=88KB=1.01%.
#:   Стабильно ~1% — settle обеих точек убрал почти весь шум, который раньше
#:   маскировал безоткатную утечку.
#: - Здоровый прогон (9 из 10 вкладок закрыто, 4 живых прогона):
#:   24.49% (2155/8800KB), 18.53% (2400/12955KB), 14.28% (1092/7646KB, САМЫЙ
#:   низкий из 4х — WebView этого приложения не multi-process, общие
#:   закэшированные ресурсы между вкладками не обязаны схлопываться к
#:   baseline сразу), и один прогон >=15% (прошёл под порогом виток-1, точные
#:   числа не сохранены). Диапазон здорового ~14-25%, минимум 14.28%.
#: MEMORY_RECOVERY_FRACTION=0.08 (8%): ~8x запас НАД потолком шума
#: негативного контроля (~1%) и ~1.8x запас ПОД минимумом здорового диапазона
#: (14.28%) — отделяет класс «безоткатная утечка» (~1%) от класса «частичный,
#: но реальный откат» (>=14%) с честным зазором на обе стороны, не подгонка
#: под единственный прогон.
MEMORY_RECOVERY_FRACTION = 0.08


@allure.step("Then TOTAL PSS после отката вернул заметную долю пикового роста (тренд обратим)")
def assert_memory_trend_recovered(baseline_kb: int, peak_kb: int, after_close_kb: int) -> None:
    """Операционализация критерия TC-099 (решение test-automator, «Caveat для
    автоматизации» кейса, critic-вход приёмки 2026-07-21; см.
    `MEMORY_RECOVERY_FRACTION` за эмпирическим обоснованием конкретного
    порога). Голый строгий `after_close < peak` рискует флаком — единичный
    замер может случайно оказаться на волосок ниже пика без реального отката
    (GC асинхронен); голое `< peak` также тривиально проходит на
    ПРЕНЕБРЕЖИМОМ отступе (1KB), не доказывая тренд. Вместо этого требуем,
    чтобы откат `peak - after_close` был не меньше `MEMORY_RECOVERY_FRACTION`
    от наблюдаемого роста `peak - baseline` — количественный, но щедрый порог
    «заметного» отката."""
    assert peak_kb > baseline_kb, (
        f"пик ({peak_kb}KB) не превышает baseline ({baseline_kb}KB) — сценарий не создал "
        f"наблюдаемой нагрузки, тренд неприменим"
    )
    growth_kb = peak_kb - baseline_kb
    recovered_kb = peak_kb - after_close_kb
    min_recovery_kb = growth_kb * MEMORY_RECOVERY_FRACTION
    assert recovered_kb >= min_recovery_kb, (
        f"после отката TOTAL PSS={after_close_kb}KB вернул только {recovered_kb}KB из "
        f"{growth_kb}KB пикового роста (baseline={baseline_kb}KB, пик={peak_kb}KB) — "
        f"ожидали возврат минимум {min_recovery_kb:.0f}KB "
        f"({MEMORY_RECOVERY_FRACTION*100:.0f}% роста); память не показывает обратимый тренд"
    )
