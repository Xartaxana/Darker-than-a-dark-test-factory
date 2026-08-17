"""Бизнес-шаги экрана Settings (GWT)."""
from __future__ import annotations

import time
from typing import Callable

import allure

from framework.config import settings
from framework.core import adb, contexts
from framework.core.waits import assert_holds_for, wait_for, wait_until
from framework.data import seed_db
from framework.screens.base_screen import BaseScreen
from framework.screens.navigation import BottomNav
from framework.screens.rating_overlay import RatingOverlay
from framework.screens.settings_screen import SettingsScreen


@allure.step("Then экран Settings отрисован")
def assert_settings_loaded(driver):
    assert SettingsScreen(driver).is_loaded(), "экран Settings не отрисовался (нет секции Theme)"


@allure.step("Then контролы темы/шрифта/яркости в Settings присутствуют в дереве и кликабельны")
def assert_reader_controls_present_and_clickable(driver):
    """TC-107 (font_scale=1.3): доказывает, что увеличенный масштаб не вытеснил
    контролы из accessibility-дерева и не сделал их некликабельными — НЕ
    проверяет визуальную обрезку/наложение (testability gap, см. TC-107.md)."""
    screen = SettingsScreen(driver)
    for mode in ("LIGHT", "DARK", "SYSTEM"):
        loc = screen.theme_button_locator(mode)
        assert screen.is_present(loc), f"кнопка темы «{mode}» не найдена в дереве (font_scale=1.3)"
        assert screen.is_clickable_attr(loc), f"кнопка темы «{mode}» не кликабельна (font_scale=1.3)"
    for step in range(7):
        loc = screen.font_size_button_locator(step)
        assert screen.is_present(loc), f"кнопка размера шрифта (шаг {step}) не найдена в дереве (font_scale=1.3)"
        assert screen.is_clickable_attr(loc), f"кнопка размера шрифта (шаг {step}) не кликабельна (font_scale=1.3)"
    assert screen.is_present(screen.BRIGHTNESS_SLIDER), "слайдер Brightness не найден в дереве (font_scale=1.3)"


@allure.step("When выбрана тема {mode}")
def select_theme(driver, mode: str):
    SettingsScreen(driver).select_theme(mode)


@allure.step("Given в Settings включена опция «Auto-download favorite works»")
def enable_auto_download(driver):
    SettingsScreen(driver).set_auto_download(True)


@allure.step("Then в Settings тумблер «Auto-download favorite works» показывает {expected}")
def assert_auto_download_enabled(driver, expected: bool = True):
    """TC-113 (attempt 2, критик-вход): `enable_auto_download`/`set_auto_download`
    тапает тумблер УСЛОВНО (только если текущее состояние не совпадает с желаемым,
    см. докстринг `SettingsScreen.set_auto_download`) и сам ничего не утверждает —
    без явного assert'а непроизошедший переход OFF->ON тоже дал бы зелёный тест,
    если остальные Then кейса от состояния тумблера не зависят. Читает тот же
    `is_auto_download_checked`, что и `set_auto_download`."""
    actual = SettingsScreen(driver).is_auto_download_checked()
    assert actual == expected, (
        f"тумблер «Auto-download favorite works» показывает {actual}, ожидали {expected}"
    )


@allure.step("Given в Settings включена опция «Tap to scroll (work pages)»")
def enable_tap_to_scroll(driver):
    """AT-BUG-030/TC-119/120/122: `BrowserScreen.kt` реактивно (`LaunchedEffect
    (tapToScroll)`) переинжектирует `window.__ao3TapToScroll` при каждой
    навигации/смене настройки — включать можно ДО открытия work-страницы (тот же
    порядок, что `enable_auto_download`/`test_auto_download_triggers_on_loved_rating`)."""
    SettingsScreen(driver).set_tap_to_scroll(True)


@allure.step("Then в Settings тумблер «Tap to scroll (work pages)» показывает {expected}")
def assert_tap_to_scroll_enabled(driver, expected: bool = True):
    """TC-123: собственный Given кейса («tap_to_scroll = OFF, дефолт») сверяется
    явным assert'ом, а не молчаливо предполагается — тот же класс, что
    `assert_auto_download_enabled` (TC-113): без него негативный инвариант был
    бы неотличим от кейса, где предпосылка тумблера случайно не выполнена
    (например, состояние утекло из другого прогона)."""
    actual = SettingsScreen(driver).is_tap_to_scroll_checked()
    assert actual == expected, (
        f"тумблер «Tap to scroll (work pages)» показывает {actual}, ожидали {expected}"
    )


@allure.step("When в Settings тумблер «Auto-apply on navigation» установлен в {enabled}")
def set_auto_apply_filter_toggle(driver, enabled: bool):
    """TC-181/184/185: реактивная связка Settings→MainActivity→BrowserViewModel
    (`MainActivity.kt:176-178 LaunchedEffect`) применяет новое значение немедленно,
    без рестарта — тумблер можно переключать в любой момент сценария, ДО или ПОСЛЕ
    навигации на Browse (в отличие от `enable_tap_to_scroll`, чей гейт вычисляется
    один раз при инъекции)."""
    SettingsScreen(driver).set_auto_apply_filter(enabled)


@allure.step("Then в Settings тумблер «Auto-apply on navigation» показывает {expected}")
def assert_auto_apply_filter_enabled(driver, expected: bool = True):
    """TC-181: Given-предпосылка (дефолт ON) сверяется явным assert'ом, а не
    предполагается — тот же класс, что `assert_auto_download_enabled`/
    `assert_tap_to_scroll_enabled`."""
    actual = SettingsScreen(driver).is_auto_apply_filter_checked()
    assert actual == expected, (
        f"тумблер «Auto-apply on navigation» показывает {actual}, ожидали {expected}"
    )


@allure.step("Given в Settings включена опция «Infinite scroll (listing pages)»")
def enable_infinite_scroll(driver):
    """TC-129/TC-130: дефолт ON (`infiniteScroll: Boolean = true`,
    SettingsScreen.kt:77) — вызов идемпотентен (тот же приём, что
    `enable_tap_to_scroll`); явный вызов делает Given TC-130 независимым от
    значения дефолта (гейт `ao3_bridge.js:530` вычисляется ОДИН РАЗ при инъекции,
    на загрузке листинговой страницы — тумблер обязан быть установлен ДО перехода
    на неё, см. заметки TC-130)."""
    SettingsScreen(driver).set_infinite_scroll(True)


@allure.step("Given в Settings выключена опция «Infinite scroll (listing pages)»")
def disable_infinite_scroll(driver):
    """TC-129: симметрично `enable_infinite_scroll` (TC-130) — гейт
    `ao3_bridge.js:530` вычисляется ОДИН РАЗ при инъекции на загрузке
    листинговой страницы, тумблер обязан быть выставлен ДО перехода на неё
    (переключение после загрузки не действует ретроактивно — non-goal кейса)."""
    SettingsScreen(driver).set_infinite_scroll(False)


@allure.step("Then в Settings тумблер «Infinite scroll (listing pages)» показывает {expected}")
def assert_infinite_scroll_enabled(driver, expected: bool = True):
    """TC-129 (класс ложно-зелёных #2, CLAUDE.md): `set_infinite_scroll` тапает
    тумблер УСЛОВНО (только если текущее состояние не совпадает с желаемым) и
    сам ничего не утверждает — без явного assert'а непроизошедший переход
    ON->OFF был бы неотличим от случая, где Given кейса случайно не выполнен.
    Тот же приём, что `assert_tap_to_scroll_enabled`/`assert_auto_download_enabled`."""
    actual = SettingsScreen(driver).is_infinite_scroll_checked()
    assert actual == expected, (
        f"тумблер «Infinite scroll (listing pages)» показывает {actual}, ожидали {expected}"
    )


@allure.step("When в Settings тумблер «Hide {rating_label} works» установлен в {enabled}")
def set_hide_rating(driver, rating_label: str, enabled: bool):
    SettingsScreen(driver).set_hide_rating(rating_label, enabled)


@allure.step("Then в Settings тумблер «Hide {rating_label} works» показывает {expected}")
def assert_rating_hidden(driver, rating_label: str, expected: bool):
    """TC-094: проверка состояния, установленного ДРУГИМ входом (side panel) — читает
    то же самое `uiState.isHidden(rating)`, что и `set_hide_rating`/TC-015."""
    actual = SettingsScreen(driver).is_rating_hidden(rating_label)
    assert actual == expected, (
        f"тумблер «Hide {rating_label} works» показывает {actual}, ожидали {expected}"
    )


@allure.step("When в Settings Display mode установлен в «{label}»")
def set_display_mode(driver, label: str):
    SettingsScreen(driver).tap_display_mode(label)


@allure.step("Given в Settings формат загрузки переключён на «{label}»")
def select_download_format(driver, label: str):
    """AT-BUG-071: TextButton "HTML"/"EPUB" (SettingsScreen.kt:969-1003) — тот же
    приём клика на родителе TextButton, что `select_theme`/`tap_display_mode`.
    Идемпотентности НЕ проверяет (в отличие от `set_auto_download` — тот тумблер,
    этот сегментированный выбор из ровно двух значений всегда переключается тапом
    по целевой метке независимо от текущего состояния)."""
    SettingsScreen(driver).tap_download_format(label)


@allure.step("Given в Settings включена опция «Page with volume buttons»")
def enable_volume_button_scroll(driver):
    """AT-BUG-072/TC-252: дефолт ON (`volumeButtonScroll: Boolean = true`,
    SettingsScreen.kt:86) — вызов идемпотентен (тот же приём, что
    `enable_infinite_scroll`/`enable_tap_to_scroll`); явный вызов делает Given
    TC-252 независимым от значения дефолта."""
    SettingsScreen(driver).set_volume_button_scroll(True)


@allure.step("Given в Settings выключена опция «Page with volume buttons»")
def disable_volume_button_scroll(driver):
    """TC-253 (off-инвариант): симметрично `enable_volume_button_scroll`."""
    SettingsScreen(driver).set_volume_button_scroll(False)


@allure.step("Then в Settings тумблер «Page with volume buttons» показывает {expected}")
def assert_volume_button_scroll_enabled(driver, expected: bool = True):
    """Given-предпосылка кейса сверяется явным assert'ом, а не предполагается —
    тот же класс, что `assert_tap_to_scroll_enabled`/`assert_infinite_scroll_enabled`."""
    actual = SettingsScreen(driver).is_volume_button_scroll_checked()
    assert actual == expected, (
        f"тумблер «Page with volume buttons» показывает {actual}, ожидали {expected}"
    )


@allure.step("When открыт диалог «Clear all ratings» и подтверждён")
def clear_all_ratings(driver):
    s = SettingsScreen(driver)
    s.open_clear_all_dialog()
    assert s.clear_dialog_visible(), "диалог подтверждения очистки не появился"
    s.confirm_clear_all()


@allure.step("Then baseline-замер соответствует ВЫБРАННОМУ состоянию кнопки {rating} (якорь Given)")
def assert_baseline_indicates_selected(driver, rating: str, selected_baseline_luma: float,
                                       deselected_threshold: float = 178.9,
                                       timeout: float = 10.0) -> float:
    """R1 (критик D5, 2026-08-02): якорь Given. Без него `selected_baseline_luma`,
    случайно снятая с уже НЕвыбранной/дефолтной кнопки (например, seed-фикстура
    не успела применить рейтинг до открытия страницы работы), была бы
    неотличима от настоящего выбранного состояния — тест дал бы ложно-зелёный
    результат на сломанном Given (порог деселекта заведомо не превышался бы,
    раз baseline с самого начала был «уже светлый»). Историческая калибровка
    (test-automator 2026-07-18, TC-009/TC-010/TC-020): выбранный `ratingAccent`
    тёмный, luma заметно НИЖЕ порога деселекта `≈178.9`.

    ОПРОС, а не одноразовый снимок (критик D5, финальный раунд 2026-08-03):
    цвет кнопки становится «выбранным» не в момент открытия страницы, а когда
    `onPageLoaded` АСИНХРОННО перечитает рейтинг из Room
    (`BrowserViewModel.kt:463-509`, корутина) и `animateColorAsState` доиграет
    переход в `ratingAccent` (180мс tween). Жёсткий assert сразу после
    `capture_panel_rating_baseline` падал бы на всяком прогоне, где Given
    установлен ВЕРНО, но не успел проявиться к первому кадру, — это ложно-красный
    того же класса, что описан у `rating_steps.assert_rating_button_selected`
    (опрашивающий сиблинг, тот же luma-прокси того же `RatingMenu`). Здесь опрос
    в ту же сторону (кнопка ТЕМНЕЕТ до порога), поэтому:

    - если первичный замер уже ниже порога — возвращаем его немедленно, лишних
      чтений дерева не делаем;
    - иначе опрашиваем `button_avg_luma` до `timeout` и возвращаем ОСЕВШЕЕ
      значение — именно оно, а не ранний (ещё светлый) снимок, обязано служить
      baseline'ом последующих Then: baseline, снятый до конца анимации, завысил
      бы порог деселекта `selected_baseline_luma / ratio` и ослабил бы обе
      парные проверки;
    - если за весь бюджет кнопка так и не потемнела — `AssertionError` (Given
      кейса действительно сломан).

    Если ни одного УСПЕШНОГО перечитывания не случилось (драйвер-вызов завис —
    `last error` внутри `wait_for`), исходный `TimeoutError` пробрасывается
    целиком: тип и контекст нужны зарегистрированному fail-fast-детектору среды
    (AT-BUG-009), подменять его собственным `AssertionError` нельзя (тот же
    приём, что в `assert_filter_profile_count`)."""
    if selected_baseline_luma < deselected_threshold:
        return selected_baseline_luma

    overlay = RatingOverlay(driver)
    observed: list[float] = []

    def _settled() -> bool:
        luma = overlay.button_avg_luma(rating)
        observed.append(luma)
        return luma < deselected_threshold

    try:
        wait_for(
            _settled, timeout=timeout,
            message=f"кнопка рейтинга {rating} не пришла в выбранное состояние",
        )
    except TimeoutError:
        if not observed:
            # Ни одного успешного перечитывания — наблюдения нет, диагностировать
            # нечего; пробрасываем исходный TimeoutError без искажения.
            raise

    settled = observed[-1] if observed else selected_baseline_luma
    assert settled < deselected_threshold, (
        f"baseline luma={settled:.1f} (первичный замер {selected_baseline_luma:.1f}, "
        f"опрос {timeout:.0f}с, наблюдения: {[round(v, 1) for v in observed]}) НЕ ниже "
        f"порога деселекта {deselected_threshold:.1f} — похоже, Given кейса не установил "
        f"кнопку рейтинга в выбранное состояние (рейтинг SAVE не применился до измерения "
        f"baseline)"
    )
    return settled


@allure.step("Then панель рейтинга на странице работы ВСЁ ЕЩЁ отражает выбор {rating} (без reload)")
def assert_panel_rating_still_selected(driver, rating: str, selected_baseline_luma: float, ratio: float = 0.75,
                                        budget_s: float = 10.0, interval_s: float = 0.5):
    """Наблюдаемый факт (без утверждения причины — R2, критик D5 2026-08-02):
    непосредственно после Clear all ratings, БЕЗ reload, кнопка рейтинга
    `{rating}` остаётся визуально выбранной. Симметрична
    `rating_steps.assert_panel_rating_deselected` (тот же luma-прокси кнопки,
    тот же `ratio`/порог деселекта), но проверяет ОТСУТСТВИЕ перехода —
    негативное утверждение.

    Негативные утверждения держат ВЕСЬ бюджет, не читают один снимок
    (`waits.assert_holds_for`, докстринг `waits.py:46-74`, B6 критик D5):
    одноразовое чтение сразу после возврата на вкладку не отличило бы
    «стабильно выбрано» от «уже начало меняться, просто не успели прочитать
    именно в этот момент» — опрос всего бюджета ловит отложенный переход,
    который случился бы позже первого снимка.

    Бюджет 10с = таймаут парной ПОЗИТИВНОЙ проверки
    `rating_steps.assert_panel_rating_deselected` (критик D5, финальный раунд
    2026-08-03: прежние 4с здесь были короче парных 10с там). Асимметрия
    делала негативное утверждение слабее позитивного: переход, случившийся на
    6-й секунде, парная проверка ЗАСЧИТАЛА бы как «панель отразила очистку», а
    этот шаг уже не наблюдал бы его и дал бы зелёный «состояние удержано» —
    два шага противоречили бы друг другу на одном и том же явлении. Окно
    наблюдения обеих сторон обязано совпадать; сокращать его можно только
    замером, показывающим, что переход физически не может прийти позже, — такого
    замера нет (BUG-012 Intended означает «перехода нет вовсе», а не «он быстрый»).
    Цена: +6с к прогону Then (а) — приемлемо для P3-кейса."""
    BottomNav(driver).ensure_visible()
    threshold = selected_baseline_luma / ratio

    def _still_selected() -> bool:
        luma = RatingOverlay(driver).button_avg_luma(rating)
        assert luma <= threshold, (
            f"кнопка рейтинга {rating} неожиданно посветлела до {luma:.1f} (порог "
            f"деселекта {threshold:.1f}, baseline выбранного={selected_baseline_luma:.1f}) "
            f"после Clear all ratings БЕЗ reload"
        )
        return True

    assert_holds_for(
        _still_selected, budget_s=budget_s, interval_s=interval_s,
        msg=f"кнопка рейтинга {rating} не удержала выбранное состояние весь бюджет {budget_s}с",
    )


@allure.step("When страница работы перезагружена (WebView reload)")
def reload_active_webview_page(driver, timeout: int | None = None):
    """Настоящий reload документа WebView (`window.location.reload()`) — НЕ
    повторная навигация на тот же URL. Эмпирически подтверждено (красный
    прогон TC-020, 2026-08-02): повторный вызов `BrowserScreen.open_work`/
    `navigate()` (Selenium `driver.get(url)`) на уже открытый URL НЕ
    триггерит `WebViewClient.onPageFinished` — Chromium трактует навигацию
    на идентичный URL как no-op, `BrowserViewModel.onPageLoaded` не
    вызывается, `currentPageRating` не перечитывается (второй Then кейса
    ложно не срабатывал бы на такой «псевдо-перезагрузке»). Пул-ту-рефреш
    приложения (`SwipeRefreshLayout.setOnRefreshListener { webView.reload()
    }`, `app-under-test/.../BrowserScreen.kt:553`) вызывает ИМЕННО
    `WebView.reload()` — `window.location.reload()` из JS даёт тот же эффект
    (полноценная навигация с сетевым запросом, `onPageFinished` срабатывает
    штатно, см. `onPageFinished`, `BrowserScreen.kt:575-614`)."""
    with contexts.in_webview(driver, timeout):
        driver.execute_script("window.location.reload();")
        wait_until(
            driver,
            lambda d: d.execute_script("return document.readyState;") == "complete",
            timeout=timeout if timeout is not None else settings.WEBVIEW_LOAD_TIMEOUT,
            message="страница работы не завершила reload (document.readyState != complete)",
        )


# --- TC-018/TC-019: диалог подтверждения Clear all ratings отдельно от полного
# цикла (`clear_all_ratings` выше, используется TC-004) — открытие/отмена/тексты
# проверяются по отдельности, без побочного эффекта подтверждения. ---

@allure.step("When пользователь нажимает кнопку «Clear…» (секция Data)")
def open_clear_all_dialog(driver):
    SettingsScreen(driver).open_clear_all_dialog()


@allure.step("Then появляется диалог подтверждения «Clear all ratings?»")
def assert_clear_all_dialog_visible(driver):
    assert SettingsScreen(driver).clear_dialog_visible(), (
        "диалог подтверждения «Clear all ratings?» не появился после нажатия «Clear…»"
    )


@allure.step("Then текст диалога предупреждает об удалении всех рейтингов")
def assert_clear_all_dialog_body(driver):
    assert SettingsScreen(driver).clear_dialog_body_visible(), (
        "текст диалога про удаление всех рейтингов не найден"
    )


@allure.step("When в диалоге «Clear all ratings?» нажат Cancel")
def cancel_clear_all_dialog(driver):
    SettingsScreen(driver).cancel_dialog()


@allure.step("Then диалог «Clear all ratings?» закрыт")
def assert_clear_all_dialog_closed(driver, timeout: int = 3):
    assert not SettingsScreen(driver).is_present(
        SettingsScreen(driver).by_text("Clear all ratings?"), timeout=timeout
    ), "диалог подтверждения остался открыт после Cancel"


# Относительный путь к БД приложения — тот же, что `seed_db._DB_REL`
# (не импортируется напрямую: `seed_db._DB_REL` приватная граница модуля,
# держим отдельную копию литерала, как и раньше делал этот файл).
_RATINGS_DB_REL = "databases/ao3_ratings.db"


def _poll_ratings_marker(
    read_fn: Callable[[], str], settled: Callable[[str], bool], timeout: float | None = None,
) -> str:
    """AT-BUG-081: общий опрос для трёх Then-хелперов ниже
    (`assert_no_ratings`/`assert_ratings_present`/`assert_rating_rows_empty`).

    `SettingsViewModel.confirmClearAll()` (`SettingsScreen.kt:545-548`)
    запускает `viewModelScope.launch(Dispatchers.IO) { repo.clearAllRatings()
    }` — БЕЗ await и без какого-либо UI-сигнала «удаление завершено». Прежний
    код делал ОДИН `read_fn()` сразу после того, как UI-тап вернул
    управление — это гонка между быстрым Appium round-trip и асинхронной
    Room-записью: `read_fn()` мог успеть выполниться ДО того, как корутина
    отработала. Эмпирически подтверждено (bugs/AT-BUG-081.md): 3 изолированных
    перезапуска `tests/test_smoke.py::test_clear_all_ratings` подряд дали
    PASS/FAIL/PASS, второй упал на `assert_no_ratings` с "в БД: '5'" при
    штатно прошедшем `confirm_clear_all`.

    Опрашивает `read_fn()` до `settings.RATINGS_DB_POLL_TIMEOUT` секунд
    (шаг `settings.RATINGS_DB_POLL_INTERVAL`), пока `settled(out)` не вернёт
    `True`, и возвращает ПОСЛЕДНИЙ прочитанный `out` (сырой, с маркером) —
    вызывающий Then-хелпер сам разбирает маркер/тело и решает финальный
    assert. `settled` обязан вернуть `True` НЕМЕДЛЕННО (на первом снимке) для
    `NOSQLITE`-деградации и для отсутствия `OK`-маркера (транспорт/SELECT
    ошибка) — это ДЕТЕРМИНИРОВАННЫЕ исходы, не гонка с записью, ждать их
    «устаканивания» бюджетом нечего; опрос имеет смысл только для веток,
    ждущих КОНКРЕТНОГО значения count/rows после `OK`.

    Первый опрос — сразу (t=0), без начальной паузы (симметрично
    `waits.poll_for`/`assert_holds_for`)."""
    timeout = timeout if timeout is not None else settings.RATINGS_DB_POLL_TIMEOUT
    interval = settings.RATINGS_DB_POLL_INTERVAL
    deadline = time.monotonic() + timeout
    out = read_fn()
    while not settled(out) and time.monotonic() < deadline:
        time.sleep(interval)
        out = read_fn()
    return out


def _read_ratings_count() -> str:
    """Общая remote-команда `SELECT COUNT(*) FROM work_ratings` с fail-closed
    маркером (AT-BUG-045) — используется И `assert_no_ratings`, И
    `assert_ratings_present` (AT-BUG-081: вынесена в отдельную функцию, чтобы
    оба Then-хелпера опрашивали ОДИН И ТОТ ЖЕ read, не расходящиеся копии
    команды)."""
    return adb.run_as(
        "sh -c 'command -v sqlite3 >/dev/null 2>&1 || { echo NOSQLITE; exit 0; }; "
        f"sqlite3 {_RATINGS_DB_REL} \"SELECT COUNT(*) FROM work_ratings\" 2>&1 && echo OK'"
    ).strip()


def _no_sqlite_marker_missing_error(step: str, out: str) -> RuntimeError:
    """AT-BUG-045: общий текст ошибки для трёх Then-хелперов ниже — вынесено,
    чтобы формулировка не разъезжалась по копипасте."""
    return RuntimeError(
        f"{step}: не удалось прочитать work_ratings через adb (ни маркер "
        f"NOSQLITE, ни OK не найдены в выводе — похоже на отказ транспорта, "
        f"а не на намеренную деградацию 'нет sqlite3'), сырой вывод: {out!r}"
    )


@allure.step("Then в БД приложения рейтинги ещё присутствуют (диалог не подтверждён)")
def assert_ratings_present():
    """Обратная проверка к `assert_no_ratings` — тот же деградационный приём
    (образ без бинаря sqlite3 не блокирует Then, проверку тогда делает UI-слой
    вызывающего теста, см. `assert_no_ratings`).

    AT-BUG-045 (тот же класс, что `seed_db._schema_ready()`, AT-BUG-044):
    раньше маркер деградации был `"NOSQLITE" in out or out == ""` — пустой
    `out` БЕЗ `NOSQLITE` трактовался как то же самое «нет sqlite3», но
    `2>/dev/null` подавлял ЛЮБОЙ stderr remote-стороны, а `adb.run_as` (через
    `adb.shell`/`adb._run().stdout`) отбрасывает returncode — отказ ТРАНСПОРТА
    (устройство offline/adb упал) даёт тот же пустой `out`, и Then про
    состояние БД молча пропускался вместо честного FAIL/ERROR. Fix (приём
    `_schema_ready`): `2>&1` вместо `2>/dev/null` (ошибка не теряется) +
    позитивный маркер `OK`, который remote-shell печатает, ТОЛЬКО если сам
    SELECT реально исполнился. Три исхода: `NOSQLITE` в выводе — легитимная
    деградация «нет бинаря/запрос не прошёл», skip; суффикс `OK` — реальные
    данные, парсим текст ДО маркера; ни то ни другое (в т.ч. пустой `out` —
    транспорт ничего не вернул) — явный `RuntimeError`, не тихий return.

    ИНКРЕМЕНТ 2 (attempt 2, critic-вход rework): attempt 1 печатал `NOSQLITE`
    через `... 2>&1 && echo OK || echo NOSQLITE'` — `|| echo NOSQLITE` ловил
    ЛЮБОЙ ненулевой exit `sqlite3`, не только «бинаря нет». Живой зонд критика
    на `emulator-5554` (бинарь `sqlite3` РЕАЛЬНО есть): SELECT из
    несуществующей таблицы дал `'Error: in prepare, no such table:
    work_ratings\nNOSQLITE\n'` — все три хелпера молча делали `return`
    (ложный зелёный Then на состоянии гонки AT-BUG-044, вместо честного
    `RuntimeError`). Fix: `NOSQLITE` теперь печатает ТОЛЬКО отдельный
    `command -v sqlite3` гейт ПЕРЕД самим SELECT (`command -v sqlite3
    >/dev/null 2>&1 || { echo NOSQLITE; exit 0; }; sqlite3 ... 2>&1 && echo
    OK`) — реальное отсутствие бинаря коротит выполнение до SELECT; любая
    ошибка самого SELECT (нет таблицы / БД заблокирована / файла нет) теперь
    остаётся сырым текстом БЕЗ какого-либо маркера и попадает в ту же ветку
    `RuntimeError`, что и пустой транспортный `out`.

    AT-BUG-081: опрашивает `_read_ratings_count()` (см. `_poll_ratings_marker`
    за полным разбором класса гонки) — settled сразу на `NOSQLITE`/отсутствии
    `OK`-маркера (детерминированные исходы), иначе ждёт, пока count перестанет
    быть `"0"`/пустым (например, seed-фикстура ещё дописывает Room)."""
    def _settled(out: str) -> bool:
        if "NOSQLITE" in out or not out.endswith("OK"):
            return True
        return out[: -len("OK")].strip() not in ("0", "")

    out = _poll_ratings_marker(_read_ratings_count, _settled)
    if "NOSQLITE" in out:
        return
    if not out.endswith("OK"):
        raise _no_sqlite_marker_missing_error("assert_ratings_present", out)
    count = out[: -len("OK")].strip()
    assert count not in ("0", ""), f"ожидали >0 рейтингов в БД (диалог ещё не подтверждён), получили: {count!r}"


@allure.step("Then читаем сырые строки work_ratings (различающий замер)")
def read_rating_rows() -> str:
    """Возвращает вывод `SELECT ao3Id, rating, timestamp FROM work_ratings` с
    маркером `OK`/`NOSQLITE` (AT-BUG-045) — различающий замер, НЕ `COUNT`
    (критик D5, 2026-08-02): `COUNT` не отличает
    конкурирующих писателей — `WorkRatingPanel`'s `onDispose` re-save (стухшее
    значение, обычно `SAVE`) от `onWorkFinished` auto-READ
    (`BrowserViewModel.kt:1198-1224` + `ao3_bridge.js:1114-1147`, срабатывает на
    scroll-restore независимо от Clear all/dispose). Используется точечно в
    диагностике `AT-BUG-042`.

    AT-BUG-045: вывод теперь несёт тот же fail-closed маркер, что
    `assert_ratings_present`/`assert_no_ratings` — `NOSQLITE` (намеренная
    деградация) ИЛИ суффикс `OK` (SELECT реально исполнился, тело ДО маркера —
    сырые строки, возможно пустые) — вызывающий код (`assert_rating_rows_empty`)
    сам разбирает маркер и решает, что делать с пустым/иным выводом; голый
    пустой `out` без всякого маркера — то же самое «транспорт ничего не
    вернул», что и в двух других хелперах."""
    return adb.run_as(
        "sh -c 'command -v sqlite3 >/dev/null 2>&1 || { echo NOSQLITE; exit 0; }; "
        f"sqlite3 {_RATINGS_DB_REL} "
        '"SELECT ao3Id, rating, timestamp FROM work_ratings" 2>&1 && echo OK\''
    ).strip()


@allure.step("Then таблица work_ratings пуста (сырые строки, различающий замер)")
def assert_rating_rows_empty():
    """Якорь состояния БД для TC-020 Then (б): подтверждает, что к моменту
    перезагрузки страницы `Clear all ratings` ДЕЙСТВИТЕЛЬНО опустошил
    `work_ratings`. Без него провал Then (б) не различал бы «панель не
    перечитала Room» и «в Room по-прежнему лежит рейтинг» — а это два разных
    дефекта (BUG-012-класс против BUG-022-класса).

    Отличие от `assert_no_ratings` (`COUNT`): при провале печатает САМИ строки
    `ao3Id|rating|timestamp` — единственное, что различает конкурирующих
    писателей (`SAVE` = dispose-save панели, `BUG-022`; `READ` = `onWorkFinished`
    auto-mark), см. докстринг `read_rating_rows`. Та же деградация к UI-слою на
    образах без бинаря `sqlite3`, что у `assert_no_ratings`.

    AT-BUG-045: `read_rating_rows()` теперь несёт `OK`-маркер поверх сырых
    строк — распаковываем его здесь тем же приёмом, что и в двух остальных
    хелперах (см. `assert_ratings_present`); пустое ТЕЛО (до маркера) при
    наличии `OK` — легитимный ожидаемый Then (таблица пуста), пустой `out`
    БЕЗ всякого маркера — отказ транспорта, ERROR.

    AT-BUG-081: опрашивает `read_rating_rows()` (см. `_poll_ratings_marker`
    за полным разбором класса гонки — та же async-запись `confirmClearAll()`,
    что и `assert_no_ratings`) — settled сразу на `NOSQLITE`/отсутствии
    `OK`-маркера, иначе ждёт, пока тело не станет пустой строкой."""
    def _settled(out: str) -> bool:
        if "NOSQLITE" in out or not out.endswith("OK"):
            return True
        return out[: -len("OK")].strip() == ""

    out = _poll_ratings_marker(read_rating_rows, _settled)
    if "NOSQLITE" in out:
        return
    if not out.endswith("OK"):
        raise _no_sqlite_marker_missing_error("assert_rating_rows_empty", out)
    rows = out[: -len("OK")].strip()
    assert rows == "", f"ожидали пустую work_ratings после Clear all ratings, в БД строки: {rows!r}"


@allure.step("Then в БД приложения нет ни одного рейтинга")
def assert_no_ratings():
    """AT-BUG-045: тот же fail-closed маркер, что `assert_ratings_present`
    (см. её докстринг за полным разбором класса дефекта) — раньше пустой
    `out` без `NOSQLITE` маскировал отказ транспорта под легитимную
    деградацию «нет sqlite3».

    AT-BUG-081: `SettingsViewModel.confirmClearAll()` (`SettingsScreen.kt:
    545-548`) пишет `repo.clearAllRatings()` в `viewModelScope.launch(
    Dispatchers.IO)` БЕЗ await и без UI-сигнала завершения — раньше эта
    функция делала ОДИН `_read_ratings_count()` СРАЗУ после
    `confirm_clear_all()`, гонясь с асинхронной записью (эмпирика: 3
    изолированных прогона TC-004 дали PASS/FAIL/PASS, второй упал с
    "ожидали 0 рейтингов, в БД: '5'" при штатно прошедшем шаге подтверждения
    диалога — см. `bugs/AT-BUG-081.md`). Теперь опрашивает через
    `_poll_ratings_marker` (см. её докстринг за полным разбором) — settled
    сразу на `NOSQLITE`/отсутствии `OK`-маркера (детерминированные исходы,
    не гонка), иначе ждёт, пока count не станет `"0"`."""
    def _settled(out: str) -> bool:
        if "NOSQLITE" in out or not out.endswith("OK"):
            return True
        return out[: -len("OK")].strip() == "0"

    out = _poll_ratings_marker(_read_ratings_count, _settled)
    # На части образов нет бинаря sqlite3 — тогда проверку делает UI-слой (пустые вкладки)
    if "NOSQLITE" in out:
        return
    if not out.endswith("OK"):
        raise _no_sqlite_marker_missing_error("assert_no_ratings", out)
    count = out[: -len("OK")].strip()
    assert count == "0", f"ожидали 0 рейтингов, в БД: {count!r}"


# --- Общий стейт side panel <-> Settings (theme_mode/font_size_step) ---
# ThemeModeRow/FontSizeRow (SettingsScreen.kt) рисуют выбор через цвет фона
# TextButton, не через accessibility `selected`/`checked` (сверено на живом дереве:
# `selected="false"` у всех вариантов независимо от выбора) — поэтому «Settings
# отражает изменение из панели» наблюдаемо не через UI-дерево Settings, а через
# общий источник истины обоих входов: оба вызывают один и тот же
# SettingsViewModel.setThemeMode/setFontSizeStep (MainActivity.kt), который пишет
# в тот же SharedPreferences-файл, что и читает SettingsScreen при следующем
# открытии. Тот же паттерн деградации к прямому чтению, что и `assert_no_ratings`.

@allure.step("Then сохранённая тема (SharedPreferences) = {mode}")
def assert_theme_mode_pref(mode: str):
    out = adb.run_as("cat shared_prefs/ao3_settings.xml")
    assert f'name="theme_mode">{mode}<' in out, f"theme_mode != {mode} в SharedPreferences: {out}"


@allure.step("Then сохранённое состояние Auto-apply on navigation (SharedPreferences auto_apply_filter) = {expected}")
def assert_auto_apply_filter_pref(expected: bool):
    """TC-181: `SettingsScreen.kt:539` (`prefs.edit().putBoolean("auto_apply_filter",
    enabled).apply()`) — стандартная Android SharedPreferences boolean-запись
    (`<boolean name="auto_apply_filter" value="false" />`), тот же файл
    `ao3_settings.xml`, что читает `assert_theme_mode_pref`."""
    out = adb.run_as("cat shared_prefs/ao3_settings.xml")
    expected_str = "true" if expected else "false"
    assert f'name="auto_apply_filter" value="{expected_str}"' in out, (
        f"auto_apply_filter != {expected_str} в SharedPreferences: {out}"
    )


@allure.step("Then сохранённый размер шрифта (SharedPreferences font_size_step) = {step}")
def assert_font_size_step_pref(step: int):
    out = adb.run_as("cat shared_prefs/ao3_settings.xml")
    assert f'name="font_size_step" value="{step}"' in out, \
        f"font_size_step != {step} в SharedPreferences: {out}"


# --- Scan for downloads (silent auto-триггер после смены папки загрузок/Restore,
# TC-037/TC-038) — общий AlertDialog "Scan complete" (SettingsScreen.kt:1215-1230),
# без других общих полей с остальным экраном Settings, тот же паттерн, что
# `backup_steps.assert_backup_created_dialog`/`assert_restore_result_dialog`: локатор
# сугубо для этого одноразового диалога, отдельный screen-метод не заводим.

@allure.step("Then появляется диалог «Scan complete» с текстом «{expected_text}»")
def assert_scan_complete_dialog(driver, expected_text: str, timeout: int = 15) -> None:
    b = BaseScreen(driver)
    assert b.is_present(b.by_text("Scan complete"), timeout=timeout), (
        "диалог результата скана (silent, авто-триггер после смены папки загрузок) "
        "не появился — либо скан ничего не нашёл (Idle остался), либо не запустился"
    )
    assert b.is_present(b.by_text(expected_text), timeout=2), (
        f"текст результата скана не совпал с ожидаемым «{expected_text}»"
    )


@allure.step("When диалог результата скана закрыт (OK)")
def dismiss_scan_dialog(driver) -> None:
    BaseScreen(driver).tap(BaseScreen(driver).by_text("OK"))


# --- Saved AO3 Filters (TC-042: удаление фильтр-профиля из Settings) ---

@allure.step("Then в Settings в секции «Saved AO3 Filters» отображается профиль «{name}»")
def assert_filter_profile_listed(driver, name: str, timeout: int | None = None):
    """AT-BUG-062: на провале сообщает ФАКТИЧЕСКИЙ список имён профилей из БД
    (`seed_db.read_filter_profiles()`, host-side, не требует остановленного
    приложения — тот же контракт, что `assert_filter_profiles_have_query_strings`
    уже использует), чтобы отличить «профиль сохранён под ДРУГИМ именем» (гипотеза
    1: гонка ввода в диалоге) от «имя в БД верное, но UI-прокрутка его не поймала»
    (гипотеза 2, AT-BUG-048) — раньше падение сообщало только факт отсутствия, обе
    гипотезы давали неотличимое сообщение (см. `bugs/AT-BUG-062.md`)."""
    if SettingsScreen(driver).has_filter_profile(name, timeout=timeout):
        return
    try:
        actual_names = sorted(row["name"] for row in seed_db.read_filter_profiles())
    except Exception as exc:  # noqa: BLE001
        actual_names = [f"<не удалось прочитать БД: {exc}>"]
    raise AssertionError(
        f"фильтр-профиль «{name}» не найден в списке Settings; "
        f"фактические имена в БД filter_profiles: {actual_names}"
    )


@allure.step("Then в Settings в секции «Saved AO3 Filters» профиль «{name}» отсутствует")
def assert_filter_profile_not_listed(driver, name: str, timeout: int = 3):
    """`expect_absent=True` (rework AT-BUG-062, non-blocker (а)): негативный
    ассерт ОЖИДАЕТ, что прямой свайп-проход не поймает `name` — это штатный
    успешный исход, не отказ, требующий диагностического page_source-снимка
    ДО фолбэка (тот снимок писал шумную XML-аттачку в Allure на каждом
    зелёном прогоне этого ассерта)."""
    assert not SettingsScreen(driver).has_filter_profile(name, timeout=timeout, expect_absent=True), (
        f"фильтр-профиль «{name}» всё ещё виден в списке Settings — ожидали удалённым"
    )


@allure.step("When в Settings удалён фильтр-профиль «{name}»")
def delete_filter_profile(driver, name: str):
    SettingsScreen(driver).delete_filter_profile(name)


# --- Saved AO3 Filters (TC-085/TC-086: переименование фильтр-профиля) ---

@allure.step("When в Settings профиль «{old_name}» переименован в «{new_name}»")
def rename_filter_profile(driver, old_name: str, new_name: str):
    SettingsScreen(driver).rename_filter_profile(old_name, new_name)


@allure.step("Then в Settings ровно {expected} строк(и) с именем «{name}»")
def assert_filter_profile_count(driver, name: str, expected: int, timeout: int | None = None):
    """`confirmRenameFilter` пишет в Room асинхронно (`viewModelScope.launch(Dispatchers.IO)`,
    SettingsScreen.kt) — recomposed список отстаёт от тапа по "Rename" на короткое,
    но ненулевое окно (тот же класс гонки, что `browser_steps.assert_active_tab_url`
    описывает для `pendingNavigationUrl`). `SettingsScreen.count_filter_profile_occurrences`
    делает разовое `find_elements` без ожидания — одноразовое чтение сразу после
    `rename_filter_profile` было бы гонкой; здесь опрашиваем, пока счётчик не
    совпадёт с ожидаемым или не истечёт таймаут.

    AT-BUG-037 (N2, приём — образец `app_steps.wait_persisted_tab_count`, AT-BUG-036
    attempt 2): `except TimeoutError: pass` терял исходное исключение целиком, вместе
    с ним — контекст `wait_for` (`; last error: ...`), на который матчит
    зарегистрированный fail-fast-детектор среды (AT-BUG-009). Если предикат ни разу
    не смог прочитать дерево (`last["value"]` так и остался `None` — например,
    зависший driver-вызов), диагностировать «последнее наблюдение» нечего — исходный
    `TimeoutError` пробрасывается целиком. Если хотя бы одно наблюдение было
    (счётчик читался, просто не совпал) — честный `AssertionError` с фактическим
    последним значением; причина `wait_for` (если исключение всё же было поймано на
    каком-то из опросов) дописывается к сообщению отдельно, не теряется."""
    screen = SettingsScreen(driver)
    last: dict[str, int | None] = {"value": None}
    wait_err: TimeoutError | None = None

    def _matches() -> bool:
        last["value"] = screen.count_filter_profile_occurrences(name)
        return last["value"] == expected

    try:
        wait_for(_matches, timeout=timeout, message=f"количество строк с именем «{name}» не сошлось")
    except TimeoutError as exc:
        wait_err = exc
        if last["value"] is None:
            # Опрос ни разу не смог прочитать счётчик (например, driver-вызов
            # завис) — наблюдения нет, диагностировать нечего. Пробрасываем
            # исходный TimeoutError целиком — тип исключения и
            # "; last error: ..."-контекст доходят до fail-fast-детектора
            # среды без искажения.
            raise
    assert last["value"] == expected, (
        f"ожидали {expected} строк(и) с именем «{name}» в Settings, реально {last['value']}"
        + (f"; ожидание прервано: {wait_err}" if wait_err is not None else "")
    )


@allure.step("Then в БД `filter_profiles` присутствуют записи с name=«{name}» и queryString {expected_query_strings}")
def assert_filter_profiles_have_query_strings(name: str, expected_query_strings: list[str]):
    """TC-086: после переименования в имя-дубликат обе строки таблицы `filter_profiles`
    обязаны иметь одинаковый `name`, но РАЗЛИЧНЫЕ исходные `queryString`
    (`confirmRenameFilter` — Upsert по `id`, меняет только `name` ОДНОЙ строки,
    `queryString` ни своей, ни чужой строки не трогает) — host-side чтение
    `seed_db.read_filter_profiles()`, тот же приём, что
    `backup_steps.assert_filter_profiles_match` использует для TC-021 (НЕ
    on-device sqlite3-бинарь — деградация `assert_no_ratings` к UI-фолбэку здесь
    неприменима: у этого кейса нет UI-фолбэка по построению, две одноимённые
    строки Settings не различить иначе, чем прямым чтением БД)."""
    actual = seed_db.read_filter_profiles()
    matching = [row for row in actual if row["name"] == name]
    assert len(matching) == len(expected_query_strings), (
        f"ожидали {len(expected_query_strings)} строк(и) с name=«{name}» в filter_profiles, "
        f"реально {len(matching)}: {matching}"
    )
    actual_query_strings = sorted(row["queryString"] for row in matching)
    assert actual_query_strings == sorted(expected_query_strings), (
        f"queryString записей с name=«{name}» не совпали: ожидали "
        f"{sorted(expected_query_strings)}, реально {actual_query_strings}"
    )


@allure.step("Then диалог «Scan complete» НЕ появляется (не два диалога подряд)")
def assert_no_scan_complete_dialog(driver, timeout: int = 3) -> None:
    """TC-039: ключевой наблюдаемый факт кейса — РОВНО один диалог результата после
    Restore. `importFromUri` сворачивает `scanForOrphanedDownloads()` в тот же
    `ImportState.Done` (тот же диалог, что уже проверен `assert_restore_result_dialog`)
    и НЕ трогает `scanDownloadsState` (`SettingsScreen.kt:390-400`) — поэтому
    отдельный диалог «Scan complete» структурно не может появиться следом; assert
    проверяет это явно (короткое ожидание + отсутствие), а не только присутствие
    первого диалога, как того требует заметка кейса про «not just present-check»."""
    b = BaseScreen(driver)
    assert not b.is_present(b.by_text("Scan complete"), timeout=timeout), (
        "диалог «Scan complete» появился ПОСЛЕ диалога Restore — ожидали ровно один "
        "объединённый диалог результата (Restored ... Also relinked ...), не два подряд"
    )


# --- Fetch missing metadata (секция "Data", TC-186/TC-187, AT-BUG-061) ---

@allure.step("Then подпись «Fetch missing metadata» показывает очередь из {count} работ")
def assert_metadata_fetch_queue_count(driver, count: int, timeout: int | None = None):
    screen = SettingsScreen(driver)
    screen.swipe_to_metadata_fetch()
    assert screen.metadata_queue_count_visible(count, timeout=timeout), (
        f"подпись «{count} works have no title yet» не найдена под «Fetch missing metadata»"
    )


@allure.step("When пользователь нажимает «Fetch» (Fetch missing metadata)")
def start_metadata_fetch(driver):
    screen = SettingsScreen(driver)
    screen.swipe_to_metadata_fetch()
    screen.tap_fetch_metadata()


@allure.step("Then подпись показывает прогресс «Fetching {done} / {total}…»")
def assert_metadata_fetch_progress(driver, done: int, total: int, timeout: int | None = None):
    assert SettingsScreen(driver).metadata_progress_visible(done, total, timeout=timeout), (
        f"подпись «Fetching {done} / {total}…» не появилась"
    )


@allure.step("Then кнопка на месте «Fetch» временно показывает «Stop»")
def assert_metadata_fetch_stop_button_visible(driver, timeout: int | None = None):
    assert SettingsScreen(driver).metadata_stop_button_visible(timeout=timeout), (
        "кнопка «Stop» не появилась — процесс fetch не выглядит запущенным"
    )


@allure.step("When пользователь нажимает «Stop» (Fetch missing metadata мид-процесса)")
def stop_metadata_fetch(driver):
    """Без `swipe_to_metadata_fetch` — вызывающий тест (TC-187) уже стоит на этой
    секции (предыдущий шаг того же прогона), а окно для Stop — не меньше 1.5с
    реального времени (`delay(1_500L)` между работами, SettingsScreen.kt:248):
    лишний `swipe_to_text`-опрос (даже short-circuit'нутый уже видимым текстом)
    не должен добавлять задержку внутрь этого узкого окна."""
    SettingsScreen(driver).tap_stop_metadata_fetch()


@allure.step("Then состояние Fetch missing metadata — Done, «Updated {updated} works»")
def assert_metadata_fetch_done(driver, updated: int, timeout: int | None = None):
    assert SettingsScreen(driver).metadata_done_visible(updated, timeout=timeout), (
        f"итоговая подпись Done (updated={updated}) не появилась"
    )


@allure.step("Then состояние Fetch missing metadata — Stopped, «Stopped — {updated} works updated»")
def assert_metadata_fetch_stopped(driver, updated: int, timeout: int | None = None):
    assert SettingsScreen(driver).metadata_stopped_visible(updated, timeout=timeout), (
        f"итоговая подпись Stopped (updated={updated}) не появилась"
    )


@allure.step("Then кнопка на месте «Stop» вернулась к виду «Fetch»")
def assert_metadata_fetch_button_visible(driver, timeout: int | None = None):
    assert SettingsScreen(driver).metadata_fetch_button_visible(timeout=timeout), (
        "кнопка «Fetch» не вернулась после остановки/завершения процесса"
    )


# --- Show copy-URL button toggle (секция "Debug", TC-188) ---

@allure.step("Given/When в Settings тумблер «Show copy-URL button» установлен в {enabled}")
def set_debug_copy_url(driver, enabled: bool):
    SettingsScreen(driver).set_debug_copy_url(enabled)


@allure.step("Then в Settings тумблер «Show copy-URL button» показывает {expected}")
def assert_debug_copy_url_enabled(driver, expected: bool = True):
    """TC-188 (класс ложно-зелёных #2, CLAUDE.md): `set_debug_copy_url` тапает
    тумблер УСЛОВНО (только если текущее состояние не совпадает с желаемым) и
    сам ничего не утверждает — без явного assert'а непроизошедший переход был
    бы неотличим от случая, где Given (дефолт OFF) случайно не выполнен. Тот
    же приём, что `assert_auto_download_enabled`/`assert_tap_to_scroll_enabled`."""
    actual = SettingsScreen(driver).is_debug_copy_url_checked()
    assert actual == expected, (
        f"тумблер «Show copy-URL button» показывает {actual}, ожидали {expected}"
    )
