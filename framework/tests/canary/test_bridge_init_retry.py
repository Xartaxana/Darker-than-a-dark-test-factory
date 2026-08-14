"""TC-195/TC-196 — область «bridge/canary: инициализация bridge при РАННЕМ
onPageFinished» (needs-design, docs/01-test-strategy.md §9, R-02). Проверяет
retry-контракт `ao3_bridge.js:1-19` (guard `!document.head || !document.body`
до `window.__ao3Bridge = true`; повтор через `DOMContentLoaded` при
`readyState === 'loading'` И безусловный `setTimeout(ao3BridgeInit, 250)`)
через прямой JS-харнесс (`framework.steps.bridge_harness_steps`) —
детерминированную замену нативной гонки Android WebView, недоступной через
mitm-replay content-дизайн (AT-BUG-067)."""
from __future__ import annotations

import time

import allure
import pytest

from framework.data import recording_builder as rb
from framework.data import works as W
from framework.steps import app_steps, bridge_harness_steps, browser_steps

# rework-фикс B3/B2 (TC-195/TC-196 критик attempt 1): idempotency-окно
# отсчитывается от МОМЕНТА ЗАВЕРШЕНИЯ атомарного `execute_script` шага, не от
# первого вызова скрипта — перекрывает интервал самоперевзводящейся
# `setTimeout`-цепочки (250мс) с запасом.
_IDEMPOTENCY_WINDOW_S = 0.4


# Тело сценария вынесено в отдельную функцию (не только в тело `test_*`) —
# ПОВТОРНО используется красной пробой AT-BUG-067 (3 раздельные пробы,
# критерий готовности бага): пробы монки-патчат `bridge_harness_steps.
# _read_bridge_js_text`, а затем запускают ЭТУ ЖЕ функцию, чтобы наблюдать
# естественный PASS/FAIL пробного прогона на identичных assert'ах — не
# скриптованное «ожидание», а реальный красный прогон.
def _run_tc195_scenario(driver) -> None:
    # Given приложение открыло replay-листинг с 5 засеянными work-блёрбами,
    # режим replay; приложение уже инжектировало bridge на своём
    # onPageFinished (штатное состояние — враппers на каждом блёрбе)
    app_steps.wait_ui_ready(driver)
    browser_steps.open_listing(driver, rb.LISTING_BASIC_URL)
    blurb_count = len(W.ALL)

    # And (rework attempt 2, критик — обязательный пункт критерия готовности
    # п.2): ПРЕЖДЕ чем запускать харнесс, детерминированно дождаться, что
    # приложение РЕАЛЬНО успело инжектировать bridge на этом листинге —
    # `open_listing` ждёт только появления блёрбов в DOM (гонка НЕ с bridge,
    # задокументирована в докстринге `assert_every_blurb_has_unrated_rate_button`
    # ниже), поэтому без отдельного опроса `before_anchor == 0` мог бы
    # пройти ТРИВИАЛЬНО (враппers ещё не появились сами по себе), маскируя
    # сломанную логику очистки в `simulate_early_bridge_injection`.
    browser_steps.assert_every_blurb_has_unrated_rate_button(driver)
    given_count = bridge_harness_steps.count_rate_button_wraps(driver)
    assert given_count == blurb_count, (
        f"штатное состояние ДО харнесса: ожидали {blurb_count} враппers "
        f"(приложение уже инжектировало bridge на своём onPageFinished), "
        f"нашли {given_count} — харнесс запускается до реальной инжекции "
        f"приложением, якорь `before_anchor == 0` ниже был бы вакуумным"
    )

    # And JS-контекст страницы приведён харнессом в состояние «ранний
    # onPageFinished с readyState=loading»: ВСЕ уже существующие враппers
    # удалены, document.head/document.body/document.readyState затенены,
    # window.__ao3Bridge сброшен, текст ao3_bridge.js выполнен один раз как
    # ПЕРВЫЙ вызов (эквивалент первого onPageFinished) — этот вызов не
    # завершает инициализацию, а регистрирует DOMContentLoaded-листенер и
    # взводит безусловный setTimeout(ao3BridgeInit, 250)
    bridge_harness_steps.simulate_early_bridge_injection(driver, "loading")

    # And (контрольная точка ДО When — позитивный якорь, класс TC-118/
    # AT-BUG-029): на блёрбах листинга Rate-кнопок ещё НЕТ. Без этого якоря
    # Then был бы неотличим от харнесса, тихо провалившегося затенить DOM,
    # ЛИБО от вакуумного зелёного, считающего СТАРЫЕ враппers приложения.
    # Проверка обязана опираться на РЕАЛЬНОЕ штатное состояние ДО харнесса
    # (given_count == blurb_count выше), иначе она сама может быть
    # вакуумной — этот якорь снят сразу ПОСЛЕ given_count, не вместо него.
    before_anchor = bridge_harness_steps.count_rate_button_wraps(driver)
    assert before_anchor == 0, (
        f"якорь ДО When: ожидали 0 враппers сразу после "
        f"simulate_early_bridge_injection, нашли {before_anchor} — либо "
        f"очистка существующих враппers не сработала, либо тени "
        f"head/body/readyState не удержались (см. AT-BUG-067 п.2)"
    )
    bridge_flag_after_injection = bridge_harness_steps.read_bridge_flag(driver)
    assert bridge_flag_after_injection is False, (
        f"якорь ДО When: ожидали window.__ao3Bridge falsy сразу после "
        f"simulate_early_bridge_injection (сброшен через `delete "
        f"window.__ao3Bridge` ДО выполнения текста скрипта, первый вызов "
        f"скрипта не завершает инициализацию), получили "
        f"{bridge_flag_after_injection!r} — см. AT-BUG-067 п.2"
    )

    # When ОДНИМ атомарным execute_script: снимаются тени, СИНХРОННО
    # замеряется count (before), диспетчится DOMContentLoaded (адресует
    # событие зарегистрированному {once:true} листенеру напрямую), СИНХРОННО
    # замеряется count и __ao3Bridge (after, bridgeFlag)
    result = bridge_harness_steps.restore_shadow_and_dispatch_dcl(driver, dispatch_dcl=True)

    # Then before === 0 (снятие теней само по себе не инициализирует bridge
    # мгновенно), after === числу блёрбов, bridgeFlag === true — Rate-кнопка
    # появилась на КАЖДОМ work-блёрбе БЕЗ повторной навигации/перезагрузки, и
    # успех детерминированно приписан именно DCL-диспетчу (атомарность
    # исключает случайный тик setTimeout-цепочки между шагами)
    assert result["before"] == 0, f"before ожидали 0, получили результат {result}"
    assert result["after"] == blurb_count, (
        f"after ожидали {blurb_count} (по числу блёрбов), получили результат {result}"
    )
    assert result["bridgeFlag"] is True, f"__ao3Bridge ожидали true, получили результат {result}"

    # And (idempotency, rework-фикс B3: отсчёт от завершения атомарного
    # вызова) ожидание продлевается ещё >=300мс от момента завершения
    # атомарного execute_script — гарантированно перекрывает следующий тик
    # самоперевзводящейся setTimeout-цепочки (интервал 250мс); число Rate-
    # кнопок остаётся ровно тем же (не задвоилось) — наблюдаемый инвариант,
    # не приписываемый конкретно guard'у window.__ao3Bridge (:5/:19) — см.
    # rework-фикс B4 в TC-195.md: задвоение способны блокировать ДВА
    # независимых механизма (:5/:19 И per-element :872).
    time.sleep(_IDEMPOTENCY_WINDOW_S)
    final_count = bridge_harness_steps.count_rate_button_wraps(driver)
    assert final_count == blurb_count, (
        f"после >={_IDEMPOTENCY_WINDOW_S * 1000:.0f}мс от завершения атомарного шага "
        f"ожидали count={blurb_count} (не задвоилось), получили {final_count}"
    )


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-195")
@allure.title(
    "Ранний onPageFinished (readyState=loading, DOM ещё не готов) не «сжигает» "
    "инжекцию: Rate-кнопки листинга появляются без ручной перезагрузки, оба "
    "независимых повтора не задваивают их"
)
@pytest.mark.parametrize("replay", [rb.LISTING_BASIC_FILENAME], indirect=True)
def test_bridge_init_retry_dcl_loading_idempotent(clean_app, replay, driver):
    _run_tc195_scenario(driver)


def _run_tc196_scenario(driver) -> None:
    # Given приложение открыло replay-листинг с 5 засеянными work-блёрбами,
    # режим replay
    app_steps.wait_ui_ready(driver)
    browser_steps.open_listing(driver, rb.LISTING_BASIC_URL)
    blurb_count = len(W.ALL)

    # And (rework attempt 2, критик — обязательный пункт критерия готовности
    # п.2), тот же приём, что в TC-195: дождаться РЕАЛЬНОЙ инжекции bridge
    # приложением ДО запуска харнесса — `open_listing` ждёт только появления
    # блёрбов, не bridge (см. докстринг ниже), без этого шага якорь
    # `before_anchor == 0` мог бы пройти вакуумно.
    browser_steps.assert_every_blurb_has_unrated_rate_button(driver)
    given_count = bridge_harness_steps.count_rate_button_wraps(driver)
    assert given_count == blurb_count, (
        f"штатное состояние ДО харнесса: ожидали {blurb_count} враппers "
        f"(приложение уже инжектировало bridge на своём onPageFinished), "
        f"нашли {given_count} — харнесс запускается до реальной инжекции "
        f"приложением, якорь `before_anchor == 0` ниже был бы вакуумным"
    )

    # And JS-контекст приведён харнессом в состояние «ранний onPageFinished,
    # DOMContentLoaded для этого document уже не произойдёт»: враппers
    # удалены, head/body затенены, readyState затенён значением, ОТЛИЧНЫМ от
    # 'loading' ('complete') — из-за этого guard НЕ регистрирует
    # DOMContentLoaded-листенер (ao3_bridge.js:12-14 не срабатывает), но
    # безусловный setTimeout(ao3BridgeInit, 250) (:15) всё равно взводится
    bridge_harness_steps.simulate_early_bridge_injection(driver, "complete")

    # And (контрольная точка ДО When, тот же позитивный якорь класса TC-118/
    # AT-BUG-029) — без него Then «count == числу блёрбов через >=300мс» шёл
    # бы вакуумно, посчитав СТАРЫЕ враппers приложения вместо новых от
    # setTimeout-пути. Опирается на given_count == blurb_count выше.
    before_anchor = bridge_harness_steps.count_rate_button_wraps(driver)
    assert before_anchor == 0, (
        f"якорь ДО When: ожидали 0 враппers сразу после "
        f"simulate_early_bridge_injection, нашли {before_anchor} (см. "
        f"AT-BUG-067 п.2)"
    )
    bridge_flag_after_injection = bridge_harness_steps.read_bridge_flag(driver)
    assert bridge_flag_after_injection is False, (
        f"якорь ДО When: ожидали window.__ao3Bridge falsy сразу после "
        f"simulate_early_bridge_injection, получили "
        f"{bridge_flag_after_injection!r} — см. AT-BUG-067 п.2"
    )

    # When шаг 1, ОДНИМ execute_script: снимает тени и СИНХРОННО замеряет
    # count сразу после снятия (rework-фикс B2 TC-196.md: детерминированный
    # факт, не гонка с реальным временем) — dispatch_dcl=False, в этом пути
    # DOMContentLoaded-листенер не зарегистрирован, диспатчить нечего
    result = bridge_harness_steps.restore_shadow_and_dispatch_dcl(driver, dispatch_dcl=False)

    # Then результат шага 1 показывает count === 0 — само по себе снятие
    # теней не инициализирует bridge мгновенно
    assert result["before"] == 0, f"before ожидали 0, получили результат {result}"

    # When шаг 2 — реальное время: >=300мс ожидания ПОСЛЕ завершения шага 1
    # (перекрывает интервал таймера ~250мс с запасом)
    time.sleep(_IDEMPOTENCY_WINDOW_S)

    # Then по истечении ожидания Rate-кнопка появилась на КАЖДОМ work-блёрбе
    # БЕЗ повторной навигации/перезагрузки И БЕЗ единого диспатча
    # DOMContentLoaded; window.__ao3Bridge === true — появление кнопок
    # приписывается отложенному setTimeout-таймеру (единственный оставшийся
    # канал в этом пути)
    final_count = bridge_harness_steps.count_rate_button_wraps(driver)
    assert final_count == blurb_count, (
        f"после >={_IDEMPOTENCY_WINDOW_S * 1000:.0f}мс ожидали count={blurb_count} "
        f"(по числу блёрбов, setTimeout-путь), получили {final_count}"
    )
    browser_steps.assert_bridge_marker_present(driver)


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-196")
@allure.title(
    "Ранний onPageFinished, когда DOMContentLoaded уже не случится "
    "(readyState != loading): Rate-кнопки листинга всё равно появляются без "
    "ручной перезагрузки — спасает безусловный setTimeout(250)"
)
@pytest.mark.parametrize("replay", [rb.LISTING_BASIC_FILENAME], indirect=True)
def test_bridge_init_retry_setTimeout_only_path(clean_app, replay, driver):
    _run_tc196_scenario(driver)
