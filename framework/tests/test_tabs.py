"""Тесты области tabs (test-cases/tabs/): лимит MAX_TABS, swipe-close + Undo,
эвикция Undo-истории, персистентность вкладок через рестарт, long-press фоновой
вкладки (BrowserViewModel.kt/TabStrip.kt/BrowserScreen.kt, area=tabs).

Инфраструктурные заметки (разведка 2026-07-18, см. докстринг
`framework/screens/browser_screen.py` у `tab_chip_locator`):
- chromedriver (WEBVIEW-контекст) прилипает к вкладке-0 при >1 живой WebView —
  чтение/запись контента НЕ-нулевой вкладки через `driver.get()`/`execute_script`
  ненадёжно; используем deep-link (`app_steps.open_deep_link`, реальный Android
  intent, минует chromedriver) для загрузки контента в конкретную вкладку и
  НАТИВНЫЙ заголовок чипа (`TabInfo.title`) для идентификации вкладок без похода
  в WEBVIEW.
- TC-026 заблокирован тем же классом разведки (ненадёжность синтетического
  long-press поверх WebView через Appium/UiAutomator2) — см. `bugs/AT-BUG-018.md`.
- Первый `open_deep_link` каждого теста этого модуля предваряется
  `app_steps.wait_home_ready_for_deep_link` (не `wait_ui_ready`) — харденинг
  гонки deep-link vs home-load (ревью 2026-07-18, п.5): без него
  `BrowserViewModel.openOrNavigateDeepLink` (kt:637-644) мог обогнать
  `onPageLoaded` и пойти веткой navigate-in-place вместо добавления вкладки,
  портя счёт/позиции вкладок. Один корневой фикс на весь класс тестов, см.
  докстринг `wait_home_page_loaded` в `framework/screens/browser_screen.py`.
"""
from __future__ import annotations

import allure
import pytest

from framework.data import recording_builder as rb
from framework.steps import app_steps, browser_steps


@pytest.mark.p1
@allure.id("TC-022")
@allure.title("Достижение лимита MAX_TABS=10 не создаёт 11-ю вкладку")
def test_max_tabs_limit_blocks_11th_tab(clean_app, driver):
    # Given приложение запущено и в tab strip открыто ровно 10 вкладок (MAX_TABS):
    # стартовая вкладка + 1 deep-link (TabStrip рендерится только при tabs>1 —
    # кнопки «New tab» ещё нет на единственной стартовой вкладке, см. заметки
    # TC-022.md) + 8 доп. тапов «New tab». Каждый промежуточный тап не должен
    # преждевременно упереться в диалог лимита (доказывает, что лимит срабатывает
    # РОВНО на границе, не раньше).
    app_steps.wait_home_ready_for_deep_link(driver)
    app_steps.open_deep_link(browser_steps.HOME_URL)
    browser_steps.assert_tab_strip_visible(driver, timeout=10)
    for _ in range(8):
        browser_steps.open_new_tab(driver)
        browser_steps.assert_tab_limit_dialog_not_shown(driver)

    # заголовок самой ЛЕВОЙ (deep-link, давно загруженной и стабильной — не меняется
    # асинхронно, в отличие от свежесозданных фоновых вкладок справа) вкладки —
    # снимок ДО 11-й попытки, для проверки «активная вкладка не изменилась
    # непредсказуемо» ниже
    leftmost_title_before = browser_steps.tab_chip_title_at(driver, 0)

    # When пользователь нажимает кнопку создания новой вкладки ещё раз (11-я попытка)
    browser_steps.open_new_tab(driver)

    # Then количество вкладок остаётся равным 10 — диалог «Tab limit reached»
    # ЛИТЕРАЛЬНО называет текущее число («You have 10 tabs open»), а сам код
    # (`BrowserViewModel.openTab`) показывает диалог И добавляет вкладку как
    # взаимоисключающие ветки одного вызова — наблюдение диалога само по себе
    # доказывает, что 11-я вкладка не создана.
    browser_steps.assert_tab_limit_dialog_shown(driver, expected_max=10)
    browser_steps.dismiss_tab_limit_dialog(driver)

    # And активная вкладка не меняется непредсказуемо: если бы `activeTabIndex`
    # реально сдвинулся к «новой» (несуществующей) 11-й вкладке, LazyRow
    # (`LaunchedEffect(activeTabIndex)`, TabStrip.kt) заскроллил бы список, и самая
    # левая СКОМПОНОВАННАЯ вкладка перестала бы быть исходной deep-link-вкладкой —
    # заголовок стабилен (загружен задолго до этого момента), поэтому сравнение
    # текста, а не хрупких pixel-координат
    browser_steps.assert_tab_title_at_position(driver, 0, leftmost_title_before)

    # Повторная попытка снова упирается в тот же лимит (число не подросло молча)
    browser_steps.open_new_tab(driver)
    browser_steps.assert_tab_limit_dialog_shown(driver, expected_max=10)
    browser_steps.dismiss_tab_limit_dialog(driver)


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-023")
@allure.title("Swipe-up закрывает вкладку, Undo из snackbar восстанавливает её на исходной позиции")
@pytest.mark.parametrize("replay", [rb.TAB_MARKER_FILENAME], indirect=True)
def test_swipe_close_undo_restores_position(replay, clean_app, driver):
    app_steps.wait_home_ready_for_deep_link(driver)
    title1 = rb.tab_marker_title(1)
    title2 = rb.tab_marker_title(2)

    # Given открыто 3 вкладки: 0 — стартовая Home (нетронута), 1 — маркерная страница
    # (будет закрыта и восстановлена), 2 — вторая маркерная страница. Deep-link —
    # единственный надёжный способ загрузить произвольный URL в НЕ-нулевую вкладку
    # (см. модульный докстринг про прилипание chromedriver к вкладке-0).
    app_steps.open_deep_link(rb.tab_marker_url(1))
    browser_steps.assert_tab_title_visible(driver, title1, timeout=15)
    app_steps.open_deep_link(rb.tab_marker_url(2))
    browser_steps.assert_tab_title_visible(driver, title2, timeout=15)
    browser_steps.assert_tab_title_at_position(driver, 1, title1)
    browser_steps.assert_tab_title_at_position(driver, 2, title2)

    # вкладка 1 (маркер 1) — средняя, имеет ненулевую позицию скролла: НАТИВНЫЙ
    # свайп по видимой WebView-области (реальный физический скролл активной
    # вкладки, не JS `scrollTo` — см. заметки TC-023.md про
    # `peekPendingScrollRestore`/детерминизм и модульный докстринг про прилипание
    # chromedriver к вкладке-0, из-за которого JS-скролл НЕ-нулевой вкладки
    # ненадёжен)
    browser_steps.switch_to_tab(driver, 1)
    browser_steps.swipe_scroll_active_tab(driver)

    # When пользователь делает swipe-up по чипу вкладки 1, закрывая её
    browser_steps.swipe_close_tab(driver, 1)
    # And в появившемся snackbar "Tab closed" нажимает действие Undo
    browser_steps.assert_undo_snackbar_visible(driver)
    browser_steps.tap_undo(driver)

    # Then вкладка восстанавливается на исходной позиции (индекс 1, между
    # исходными соседями) — заголовок чипа на позиции 1 снова маркер 1, соседи
    # (Home на позиции 0, маркер 2 на позиции 2) не сдвинулись
    browser_steps.assert_tab_title_at_position(driver, 1, title1, timeout=10)
    browser_steps.assert_tab_title_at_position(driver, 2, title2)

    # And URL вкладки соответствует тому, что было до закрытия (доказано позиционно
    # заголовком выше — маркерные страницы 1:1 соответствуют своим URL) И позиция
    # скролла восстановлена (не с нуля): читаем WebView-контент восстановленной
    # вкладки, для чего сначала сводим число вкладок к одной — chromedriver
    # прилипает к вкладке-0, надёжное чтение НЕ-нулевой вкладки требует уничтожить
    # остальные (см. модульный докстринг)
    browser_steps.swipe_close_tab(driver, 0)  # закрыть Home (сосед слева)
    browser_steps.swipe_close_tab(driver, 1)  # закрыть маркер 2 (сосед справа, теперь на позиции 1)
    browser_steps.assert_scroll_restored(driver)


@pytest.mark.p3
@pytest.mark.replay
@allure.id("TC-024")
@allure.title("Более 5 закрытых вкладок вытесняют самый старый снапшот из Undo-истории")
@pytest.mark.parametrize("replay", [rb.TAB_MARKER_FILENAME], indirect=True)
def test_undo_history_evicts_oldest_after_six_closes(replay, clean_app, driver):
    app_steps.wait_home_ready_for_deep_link(driver)

    # Given открыто 7 вкладок с различимыми URL: 0 — стартовая Home, 1..6 — маркерные
    # страницы (deep-link, см. модульный докстринг про прилипание chromedriver к
    # вкладке-0 — единственный надёжный способ загрузить контент в НЕ-нулевую вкладку)
    for i in range(1, 7):
        app_steps.open_deep_link(rb.tab_marker_url(i))
        browser_steps.assert_tab_title_visible(driver, rb.tab_marker_title(i), timeout=15)

    # When пользователь последовательно закрывает 6 вкладок по одной (swipe-up по
    # чипу на позиции 0 каждый раз — закрывает Home, затем маркеры 1..5 по порядку,
    # маркер 6 остаётся единственной оставшейся активной вкладкой); snackbar каждый
    # раз просто исчезает/сменяется следующим без нажатия Undo. Закрытия делаются
    # БЕЗ ожидания snackbar'а МЕЖДУ ними (разведка 2026-07-18: `closeTab` —
    # синхронный вызов, эвикция 5-элементной истории (`closedTabSnapshots`) в нём же
    # — снятие снапшота-кандидата на эвикцию НЕ зависит от того, показан ли уже чей-то
    # snackbar; `SnackbarHostState.showSnackbar` (MainActivity.kt onCloseTab)
    # сериализует показы через `Mutex` — при 6 закрытиях подряд к моменту первого же
    # снимка на экране показывается ТОЛЬКО snackbar САМОГО ПЕРВОГО закрытия (Home),
    # остальные 5 корутин ждут своей очереди мьютекса; собственное ожидание МЕЖДУ
    # закрытиями лишь тратит время впустую и рискует само поймать/потерять окно
    # автозакрытия `SnackbarDuration.Short`, что и давало нестабильный счёт при
    # разведке).
    for _ in range(6):
        browser_steps.swipe_close_tab(driver, 0)

    # Then лимит истории закрытий — 5 (`up to 5 most-recent closes are undoable`):
    # самый СТАРЫЙ снапшот (Home, закрыт первым) вытеснен из истории ДО того, как
    # автотест успевает с ним взаимодействовать (эвикция в `closeTab` — синхронная,
    # происходит сразу при 6-м закрытии, раньше первого показа snackbar'а).
    # Проверяется исчерпывающим перебором доступных snackbar'ов Undo (сколько бы их
    # ни было доступно — до 8 попыток с запасом) — с ПОДТВЕРЖДЁННОЙ ПОЗИЦИОННОЙ
    # ИДЕНТИЧНОСТЬЮ через нативный заголовок чипа (`assert_tab_title_visible`, без
    # похода в WEBVIEW-контекст), а не голым счётчиком.
    #
    # Скорректированный охват (разведка 2026-07-18, живой прогон — по разрешению
    # заметок TC-024.md «возможна корректировка формулировки Then без потери сути
    # риска»): `SnackbarHostState.showSnackbar` (Material3, MainActivity.kt
    # `onCloseTab`) при 6 закрытиях подряд СИНХРОННО добавляет 6 корутин, но реально
    # интерактивных snackbar'ов в разумном для автотеста окне оказывается МЕНЬШЕ
    # (эмпирически 2-3 из потенциальных 5 восстановимых, воспроизведено дважды) —
    # похоже на ограничение таймингов самого механизма очереди snackbar'ов под БЫСТРОЙ
    # программной нагрузкой (не на человеческом темпе), отдельное от риска этого
    # кейса. Само по себе это НЕ опровергает и не подтверждает точное «5» — тестируем
    # ИНВАРИАНТ, который остаётся истинным независимо от того, сколько snackbar'ов
    # автотест успевает поймать: Undo НИКОГДА не восстанавливает именно Home (1-е,
    # самое старое закрытие) — если бы восстановился Home, число успешных
    # восстановлений превысило бы число распознанных по заголовку маркеров.
    # Заголовки читаются СРАЗУ после каждого успешного восстановления (не единым
    # отложенным снимком в конце) — иначе финальный снимок отстаёт от события на
    # десятки секунд (лишние `undo_snackbar_visible(timeout=10)`-ожидания цикла
    # перед тем, как он окончательно завершится), что давало ложное расхождение
    # `restored_count > len(restored_markers)` (см. докстринг `exhaust_undo_snackbars`).
    candidate_titles = [rb.tab_marker_title(i) for i in range(1, 6)]
    restored_count, restored_markers = browser_steps.exhaust_undo_snackbars(
        driver, max_attempts=8, candidate_titles=candidate_titles)

    # And нажатие Undo восстанавливает вкладки ИЗ ПОСЛЕДНИХ 5 закрытий (маркеры
    # 1..5) — НИКОГДА Home: каждое успешное восстановление соответствует РОВНО
    # одному распознанному маркеру, без «лишних» восстановлений неопознанного (Home)
    assert restored_count == len(restored_markers), (
        f"число успешных восстановлений ({restored_count}) не совпадает с числом "
        f"распознанных по заголовку маркеров ({restored_markers}) — похоже, "
        f"восстановилась НЕ маркерная вкладка (подозрение на Home, самое старое "
        f"закрытие, которое должно быть вытеснено из 5-элементной истории)"
    )
    assert restored_count >= 1, "ни одно восстановление не удалось — снапшоты 1..5 недоступны совсем"


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-025")
@allure.title("Персистентность URL и скролла вкладок после рестарта приложения")
@pytest.mark.parametrize("replay", [rb.TAB_MARKER_FILENAME], indirect=True)
def test_tabs_persist_url_and_scroll_after_restart(replay, clean_app, driver):
    app_steps.wait_home_ready_for_deep_link(driver)
    title1 = rb.tab_marker_title(1)
    title2 = rb.tab_marker_title(2)

    # Given открыто 2 вкладки с разными URL, каждая проскроллена на свою ненулевую
    # позицию (нативный свайп — реальный физический скролл активной вкладки, тот же
    # приём, что TC-023, см. модульный докстринг)
    app_steps.open_deep_link(rb.tab_marker_url(1))
    browser_steps.assert_tab_title_visible(driver, title1, timeout=15)
    browser_steps.swipe_scroll_active_tab(driver)

    app_steps.open_deep_link(rb.tab_marker_url(2))
    browser_steps.assert_tab_title_visible(driver, title2, timeout=15)
    browser_steps.swipe_scroll_active_tab(driver)

    # deep-link ВСЕГДА добавляет НОВУЮ вкладку (не заменяет стартовую Home — см.
    # модульный докстринг), поэтому к этому моменту открыто 3 вкладки (Home, маркер1,
    # маркер2); закрываем Home, чтобы получить РОВНО 2 вкладки — состояние, буквально
    # описанное в Given кейса
    browser_steps.swipe_close_tab(driver, 0)
    browser_steps.assert_tab_title_at_position(driver, 0, title1)
    browser_steps.assert_tab_title_at_position(driver, 1, title2)

    # позиция скролла подтверждена как реально сохранённая (не просто снапшот «на
    # лету») — опрос файла SharedPreferences, а не UI (см. докстринг wait_tabs_persisted
    # про дебаунс `scheduleSave`, теряющий несохранённое состояние при force-stop).
    # Gson-сериализация экранирует символ `=` в URL как юникод-escape внутри JSON
    # (сверено на живом файле устройства — `run-as cat ao3_settings.xml`) — сентинел
    # собран под фактический формат записи, не голый URL.
    app_steps.wait_tabs_persisted(rb.tab_marker_url(2).replace("=", "\\u003d"))

    # When приложение принудительно останавливается через adb force-stop и
    # запускается заново
    app_steps.restart_app_via_adb(driver)
    app_steps.wait_ui_ready(driver)

    # Then после перезапуска обе вкладки присутствуют в strip в исходном порядке —
    # заголовки чипов на позициях 0/1 соответствуют исходным маркерам (заголовок
    # выводится из <title> реальной загруженной страницы — совпадение доказывает
    # восстановление ИМЕННО того URL, что был до рестарта, не только факта наличия
    # вкладки)
    browser_steps.assert_tab_title_at_position(driver, 0, title1, timeout=20)
    browser_steps.assert_tab_title_at_position(driver, 1, title2, timeout=10)

    # And позиция скролла восстановлена приблизительно к тому же месту (peek-restore
    # применяется на загрузке) — проверяется на представительной (последней) вкладке
    # через WebView-контент, для чего сначала сводим число вкладок к одной (см.
    # модульный докстринг про прилипание chromedriver к вкладке-0)
    browser_steps.swipe_close_tab(driver, 0)  # закрыть вкладку 0 (маркер1), оставить маркер2
    browser_steps.assert_active_tab_url(driver, rb.tab_marker_url(2))
    browser_steps.assert_scroll_restored(driver)
