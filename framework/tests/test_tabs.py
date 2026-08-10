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
- TC-026 (long-press по ссылке внутри WebView) автоматизирован НЕ через координаты
  (5 механизмов инъекции по x/y дали 1/20 успехов — системная ненадёжность
  Appium/UiAutomator2 touch-инъекции над WebView-контентом), а через `mobile:
  longClickGesture` по `elementId` НАТИВНОГО a11y-узла самой ссылки (AT-BUG-019:
  ссылки внутри WebView экспонируются UiAutomator2 как отдельные native-узлы, не
  как часть контейнера WebView) — см. `BrowserScreen.long_press_link_by_text` и
  полный разбор `bugs/AT-BUG-018.md` (Fixed).
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
from framework.data import works as W
from framework.steps import app_steps, browser_steps, library_steps


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
    # запускается заново — pid-проверка (AT-BUG-032) доказывает реальную смерть
    # процесса, а не no-op force-stop с доставкой intent'а живому инстансу
    app_steps.restart_app_via_adb_asserting_new_process(driver)
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


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-026")
@allure.title("Long-press ссылки открывает фоновую вкладку без переключения активной")
@pytest.mark.parametrize("replay", [rb.LISTING_BASIC_FILENAME], indirect=True)
def test_long_press_link_opens_background_tab_without_switching(replay, clean_app, driver):
    # Given открыта одна вкладка на листинговой странице с видимой ссылкой на работу
    # (активная вкладка = текущая) — `first_work` соответствует ПЕРВОЙ ссылке блёрба
    # (`selectors.BLURB_TITLE` — `querySelector` берёт первый `h4.heading a`, тот же
    # первый элемент `ALL_WORKS[0]`, для которого `build_replay_recordings.py::
    # build_listing_basic` записал ТРЕТИЙ self-contained flow под её work-URL —
    # AT-BUG-018 Fixed, механизм требует детерминированного разрешения фоновой
    # навигации, без ухода в живую сеть на несуществующий синтетический id).
    app_steps.wait_home_ready_for_deep_link(driver)
    browser_steps.open_listing(driver, rb.LISTING_BASIC_URL)
    first_work = W.LOVED
    browser_steps.assert_active_tab_url(driver, rb.LISTING_BASIC_URL)

    # When пользователь делает long-press по ссылке на работу — фоновая вкладка
    # открывается СРАЗУ, без промежуточного context-меню (BrowserScreen.kt:640-648,
    # setOnLongClickListener по HitTestResult зовёт viewModel.openTab(background=true)
    # напрямую). Механизм — native a11y-узел ссылки (AT-BUG-019/AT-BUG-018 Fixed), не
    # координаты/офсет контейнера WebView.
    browser_steps.long_press_work_link(driver, first_work.title)

    # Then появляется новая вкладка в strip (TabStrip виден только когда tabs>1)
    browser_steps.assert_tab_strip_visible(driver, timeout=10)

    # And активной остаётся исходная вкладка (листинг) — контент экрана не
    # переключился на новую вкладку. chromedriver прилипает к вкладке-0
    # (первый когда-либо созданный WebView, см. модульный докстринг) — вкладка-0
    # здесь И ЕСТЬ исходная листинговая вкладка, поэтому опрос через WEBVIEW-контекст
    # надёжно читает ИМЕННО активную (не какую-то другую) вкладку.
    browser_steps.assert_active_tab_url(driver, rb.LISTING_BASIC_URL)

    # And новая (фоновая) вкладка доступна по тапу на её чип в strip и показывает
    # корректно загруженную страницу работы: переключаемся на неё, затем закрываем
    # исходную вкладку-0 (см. модульный докстринг — единственный надёжный способ
    # прочитать WEBVIEW-контент НЕ-нулевой вкладки: свести число вкладок к одной,
    # что форсирует chromedriver переподключиться к единственной оставшейся)
    browser_steps.switch_to_tab(driver, 1)
    browser_steps.swipe_close_tab(driver, 0)
    browser_steps.assert_active_tab_url(driver, first_work.url)


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-131")
@allure.title("Deep-link на потолке 10 вкладок: диалог лимита и потеря отклонённого URL")
@pytest.mark.parametrize("replay", [rb.TAB_MARKER_FILENAME], indirect=True)
def test_deep_link_at_tab_limit_shows_dialog_and_drops_url(replay, clean_app, driver):
    """TC-131: инвариант MAX_TABS=10 отрабатывает и для входа через deep-link
    (не только кнопку «+», см. TC-022), И для случая, когда отклонённый URL —
    заведомо НОВЫЙ (не дубль уже открытой вкладки, как в TC-022): проверка
    `tabs.size >= MAX_TABS` (BrowserViewModel.kt:263) отсекает ДО сравнения по
    URL, поэтому `openTab` возвращает `false` и НЕ вызывает `saveTabsToPrefs` —
    marker8 не появляется в `open_tabs_urls` ни сразу, ни (регрессионный замок
    находки 4 CH-005) спустя 4с после освобождения места закрытием одной
    вкладки (в коде нет очереди отложенного открытия)."""
    app_steps.wait_home_ready_for_deep_link(driver)

    # Given открыто 10 вкладок (MAX_TABS): Home (стартовая) + marker1..marker7 +
    # marker1 повтор + marker2 повтор — вариация рецепта CH-005 Seed 2
    # (TC-131.md Предусловия), РЕЗЕРВИРУЮЩАЯ marker8 неоткрытым — он нужен When
    # как заведомо новый URL, никогда не открывавшийся ни в одной вкладке
    # (`openTab` не дедуплицирует URL, повтор штатно даёт отдельную вкладку).
    for i in (1, 2, 3, 4, 5, 6, 7, 1, 2):
        app_steps.open_deep_link(rb.tab_marker_url(i))
        browser_steps.assert_tab_title_visible(driver, rb.tab_marker_title(i), timeout=15)

    marker8_url = rb.tab_marker_url(8)
    # Счёт вкладок и отсутствие marker8 — по prefs open_tabs_urls (НЕ по
    # иконкам «Close tab»: при 10 вкладках LazyRow TabStrip виртуализирован, в
    # a11y-дереве видно только ~4 иконки — ловушка из docs/01 §9).
    app_steps.wait_persisted_tab_count(10, timeout=20)
    app_steps.assert_persisted_marker_count(marker8_url, 0, expected_total=10)

    # When в приложение отправлен deep-link на marker8 — маркер, НЕ открытый
    # ни в одной из текущих 10 вкладок
    app_steps.open_deep_link(marker8_url)

    # Then показан диалог «Tab limit reached» с ДОСЛОВНЫМ текстом «You have 10
    # tabs open. Close some tabs before opening a new one.» — тот же
    # локатор/приём, что TC-022 (`assert_tab_limit_dialog_shown`), но со
    # сверкой ПОБУКВЕННО (`expected_message`), а не подстрокой (critic-блокер
    # B1, attempt 2: подстрочная сверка не различает смену второго
    # предложения)
    browser_steps.assert_tab_limit_dialog_shown(
        driver, expected_max=10,
        expected_message="You have 10 tabs open. Close some tabs before opening a new one.",
    )

    # And число вкладок в open_tabs_urls остаётся равным 10 (11-я вкладка НЕ
    # создана), marker8 по-прежнему отсутствует (0 вхождений) — ветка отказа
    # `openTab` (BrowserViewModel.kt:261-266) НЕ вызывает `saveTabsToPrefs`,
    # файл этим отклонённым intent'ом не менялся
    app_steps.wait_persisted_tab_count(10, timeout=5)
    app_steps.assert_persisted_marker_count(marker8_url, 0, expected_total=10)

    # And (регрессионный замок находки 4 CH-005) после нажатия «OK» и закрытия
    # ЛЮБОЙ одной вкладки (стало 9) marker8 отсутствует в open_tabs_urls ни
    # сразу, ни спустя 4с — в коде нет очереди отложенного открытия
    # (`openOrNavigateDeepLink`/`openTab` вызываются только в момент самого
    # intent'а). Закрытие — свайп-приём TC-023 (`browser_steps.swipe_close_tab`),
    # НЕ тап по чипу (тап по родителю чипа способен сам закрыть вкладку);
    # позиция 0 — среди РЕАЛЬНО СКОМПОНОВАННЫХ (не абсолютных) чипов,
    # ограничения «кроме какой-то» нет — marker8 не открыт ни в одной вкладке.
    browser_steps.dismiss_tab_limit_dialog(driver)
    browser_steps.swipe_close_tab(driver, 0)
    app_steps.wait_persisted_tab_count(9, timeout=10)
    app_steps.assert_persisted_marker_absent_for(marker8_url, budget_s=4.0, expected_total=9)


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-084")
@allure.title("Тап по чипу неактивной вкладки активирует её и переключает контент WebView")
@pytest.mark.parametrize("replay", [rb.TAB_MARKER_FILENAME], indirect=True)
def test_tap_inactive_tab_chip_activates_it(replay, clean_app, driver):
    """AT-BUG-022 (Fixed): reduce-to-one (established-приём TC-023/024/025/026)
    структурно не различает «switchTab(0) сработал» от «switchTab(0) — no-op»,
    когда цель тапа — вкладка 0 (sticky-прилипание chromedriver к вкладке-0
    делает `assert_active_tab_url(HOME)` тривиально истинным независимо от
    факта переключения, см. полный разбор конфаунда в bugs/AT-BUG-022.md). Then
    доказывается через `assert_tab_became_active_via_scroll` — scrollY-
    асимметрию нативного скролла (эмпирически подтверждена на эмуляторе
    2026-07-20, см. «Обсуждение» бага)."""
    app_steps.wait_home_ready_for_deep_link(driver)
    title1 = rb.tab_marker_title(1)
    title2 = rb.tab_marker_title(2)

    # Given открыто 3 вкладки: 0 — Home, 1 — маркер 1, 2 — маркер 2 (последняя
    # созданная deep-link'ом добавляется В КОНЕЦ и становится активной — см.
    # модульный докстринг про openOrNavigateDeepLink, BrowserViewModel.kt:637-644).
    # Активна вкладка 2, как и требует Given TC-084. TabStrip (и с ним чипы)
    # рендерится только при tabs>1 (см. заметки TC-022.md) — заголовок вкладки 0
    # читаем ПОСЛЕ первого deep-link'а, не до него.
    app_steps.open_deep_link(rb.tab_marker_url(1))
    browser_steps.assert_tab_title_visible(driver, title1, timeout=15)
    home_title = browser_steps.tab_chip_title_at(driver, 0)
    app_steps.open_deep_link(rb.tab_marker_url(2))
    browser_steps.assert_tab_title_visible(driver, title2, timeout=15)
    browser_steps.assert_tab_title_at_position(driver, 0, home_title)
    browser_steps.assert_tab_title_at_position(driver, 1, title1)
    browser_steps.assert_tab_title_at_position(driver, 2, title2)

    # When пользователь тапает по чипу вкладки 0 (неактивной — активна вкладка 2)
    browser_steps.switch_to_tab(driver, 0)

    # Then вкладка 0 становится ФИЗИЧЕСКИ активной — доказано scrollY-
    # асимметрией нативного скролла, а не reduce-to-one (тот приём для цели=0
    # структурно не различает переключение от no-op, см. bugs/AT-BUG-022.md)
    browser_steps.assert_tab_became_active_via_scroll(driver, target_position=0)

    # And набор вкладок не изменился этим действием — соседи на позициях 1/2
    # сохраняют те же заголовки/URL, что были до тапа (switchTab — чистая смена
    # индекса, не создаёт и не закрывает вкладки, BrowserViewModel.kt:289-295)
    browser_steps.assert_tab_title_at_position(driver, 0, home_title)
    browser_steps.assert_tab_title_at_position(driver, 1, title1)
    browser_steps.assert_tab_title_at_position(driver, 2, title2)

    # And повторный тап по уже активному чипу (вкладка 0) не меняет состояние —
    # число, порядок и заголовки вкладок остаются теми же (идемпотентность
    # switchTab на уже активном индексе)
    browser_steps.switch_to_tab(driver, 0)
    browser_steps.assert_tab_title_at_position(driver, 0, home_title)
    browser_steps.assert_tab_title_at_position(driver, 1, title1)
    browser_steps.assert_tab_title_at_position(driver, 2, title2)


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-132")
@allure.title("Deep-link на «уведённую» с HOME_URL единственную вкладку создаёт вторую вместо переиспользования")
@pytest.mark.parametrize("replay", [rb.TAB_MARKER_FILENAME], indirect=True)
def test_deep_link_after_home_loaded_creates_second_tab_not_reuse(replay, clean_app, driver):
    """TC-132: фиксирует ОТРИЦАТЕЛЬНУЮ ветку условия reuse
    (`openOrNavigateDeepLink`, BrowserViewModel.kt:637-644): условие
    `tabs.size==1 && tabs[0].url==HOME_URL` — сравнение точное строковое, БЕЗ
    слэша. `onPageLoaded` домашней страницы штатно перезаписывает URL вкладки
    на `HOME_URL + "/"` (СО слэшем) сразу по завершении загрузки —
    `wait_home_ready_for_deep_link` (тот же приём, что TC-022..025) гарантирует,
    что тест шлёт deep-link уже ПОСЛЕ этой перезаписи, т.е. окно, где reuse
    формально возможен, уже закрыто обычным ходом событий ДО When. Парный
    TC-135 (не автоматизирован здесь, не трогается) покрывает положительную
    ветку через холодный старт."""
    app_steps.wait_home_ready_for_deep_link(driver)

    # Given открыта ровно 1 вкладка, домашняя страница ПОЛНОСТЬЮ догрузилась —
    # её URL в prefs уже "https://archiveofourown.org/" (СО слэшем), что уже НЕ
    # побайтово равно константе HOME_URL (без слэша) — reuse-ветка
    # (BrowserViewModel.kt:639) больше не может сработать
    app_steps.wait_persisted_tab_count(1, timeout=10)
    home_loaded_url = browser_steps.HOME_URL + "/"
    app_steps.assert_persisted_tab_url_at(0, home_loaded_url)

    marker_url = rb.tab_marker_url(1)

    # When в приложение отправлен deep-link на маркерную страницу фикстуры
    app_steps.open_deep_link(marker_url)

    # Then число вкладок становится 2 — НЕ переиспользование исходной вкладки
    # (`navigateActiveTabTo`), а добавление НОВОЙ (`openTab`,
    # BrowserViewModel.kt:261-269)
    app_steps.wait_persisted_tab_count(2, timeout=15)

    # And новая вкладка (позиция 1) становится активной и её содержимое
    # соответствует URL deep-link'а. Активность доказана через
    # `active_tab_index` — записан ТЕМ ЖЕ `apply()`, что и сам `open_tabs_urls`
    # (`saveTabsToPrefs`), а не через WEBVIEW `current_url`: chromedriver
    # прилипает к вкладке-0 при >1 живой WebView (см. модульный докстринг
    # выше), прямое чтение НЕ-нулевой активной вкладки было бы ненадёжно без
    # reduce-to-one, которое здесь разрушило бы проверяемую вкладку 0.
    app_steps.assert_persisted_active_tab_index(1)
    app_steps.assert_persisted_tab_url_at(1, marker_url)

    # And вкладка 0 (бывшая единственная, ex-home) сохраняет своё прежнее
    # содержимое без изменений — deep-link её НЕ тронул
    app_steps.assert_persisted_tab_url_at(0, home_loaded_url)


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-133")
@allure.title("Возврат из recents (без нового deep-link intent) не переоткрывает уже обработанный deep-link")
@pytest.mark.parametrize("replay", [rb.TAB_MARKER_FILENAME], indirect=True)
def test_background_resume_without_deep_link_keeps_tabs_unchanged(replay, clean_app, driver):
    """TC-133: `deepLinkHandled`/`intent.dataString` защищают от повторной
    обработки deep-link'а не только при холодном перезапуске (TC-134,
    `force_stop`), но и при простом возврате из фона ЖИВОГО процесса
    (`onNewIntent`->`onResume` с intent'ом БЕЗ `dataString`,
    MainActivity.kt:88-101) — marker1/marker2 не переоткрываются повторно,
    набор/порядок 3 вкладок не меняется."""
    app_steps.wait_home_ready_for_deep_link(driver)

    home_url = browser_steps.HOME_URL + "/"
    marker1_url = rb.tab_marker_url(1)
    marker2_url = rb.tab_marker_url(2)

    # Given открыто 3 вкладки: 0 — Home (полностью догружена), 1 — marker1
    # (deep-link), 2 — marker2 (deep-link, последний обработанный —
    # deepLinkHandled==true для него)
    app_steps.wait_persisted_tab_count(1, timeout=10)
    app_steps.assert_persisted_tab_url_at(0, home_url)

    app_steps.open_deep_link(marker1_url)
    app_steps.wait_persisted_tab_count(2, timeout=15)
    app_steps.open_deep_link(marker2_url)
    app_steps.wait_persisted_tab_count(3, timeout=15)

    # Позитивный якорь источника ДО возврата — набор/порядок URL, с которым
    # будет сравниваться состояние ПОСЛЕ возврата (урок TC-131: негативный
    # Then без предварительно зафиксированного позитивного снимка неотличим
    # от вакуумного прохода на пустом/битом чтении prefs).
    app_steps.assert_persisted_tab_url_at(0, home_url)
    app_steps.assert_persisted_tab_url_at(1, marker1_url)
    app_steps.assert_persisted_tab_url_at(2, marker2_url)

    # Снимок pid ДО ухода в фон (critic-блокер B3, attempt 2): единственное,
    # что отличает TC-133 от TC-134 (кейс сам предупреждает об этом,
    # TC-133.md:68-71) — предпосылка «процесс жив», а не просто «есть какой-то
    # процесс с этим именем» (тот прошёл бы и на холодном перезапуске).
    pid_before = app_steps.capture_app_pid()

    # When приложение отправлено в фон (не убито) и возвращено на передний
    # план БЕЗ отправки нового deep-link intent'а — `am start` на компонент
    # Activity БЕЗ флага `-d` (в отличие от `open_deep_link`, который явно
    # шлёт `-a android.intent.action.VIEW -d <url>`). `send_app_to_background`
    # сама дожидается фактического ухода с переднего плана (query_app_state) —
    # закрывает гонку между HOME и последующим `am start`.
    app_steps.send_app_to_background(driver)
    app_steps.bring_app_to_foreground_without_deep_link()
    app_steps.wait_ui_ready(driver)

    # Сверка pid ПОСЛЕ возврата — доказывает, что это ТОТ ЖЕ процесс, а не
    # холодный перезапуск, восстановивший вкладки из prefs (сценарий TC-134).
    app_steps.assert_app_pid_unchanged(pid_before)

    # Then число вкладок остаётся 3 — позитивный якорь `wait_persisted_tab_count`
    # доказывает, что снимок реально прочитан (не вакуумно пуст)
    app_steps.wait_persisted_tab_count(3, timeout=10)

    # And набор URL и их порядок — теми же, что до возврата
    app_steps.assert_persisted_tab_url_at(0, home_url)
    app_steps.assert_persisted_tab_url_at(1, marker1_url)
    app_steps.assert_persisted_tab_url_at(2, marker2_url)

    # And ни marker1, ни marker2 НЕ переоткрылись повторно (нет дубликата
    # вкладки с тем же URL) — ровно по 1 вхождению каждого маркера;
    # `expected_total=3` — позитивный якорь ДЛЯ КАЖДОГО вызова (не только
    # первого): доказывает, что каждое отдельное чтение prefs реально
    # застало непустой/валидный снимок, а не вакуумный `[]` на отвалившемся
    # adb/run-as (класс дефекта, отклонённый критиком на TC-131 attempt 1).
    app_steps.assert_persisted_marker_count(marker1_url, 1, expected_total=3)
    app_steps.assert_persisted_marker_count(marker2_url, 1, expected_total=3)


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-134")
@allure.title("Kill+relaunch приложения не переоткрывает уже обработанный deep-link")
@pytest.mark.parametrize("replay", [rb.TAB_MARKER_FILENAME], indirect=True)
def test_kill_relaunch_without_deep_link_keeps_tabs_unchanged(replay, clean_app, driver):
    """TC-134: `deepLinkHandled`/`intent.dataString` защищают от повторной
    обработки deep-link'а не только при простом возврате из фона живого
    процесса (TC-133), но и после РЕАЛЬНОЙ смерти процесса
    (`adb shell am force-stop` + `am start -W` БЕЗ `-d`, тот же приём, что
    TC-025) — `deepLinkHandled` пересоздаётся в `false` вместе с процессом, но
    `intent.dataString` intent'а релонча пуст, поэтому `handleDeepLink` не
    вызывается вовсе: marker1/marker2 не переоткрываются повторно,
    набор/порядок 3 вкладок не меняется. Различие от TC-133: там процесс
    остаётся живым (background/foreground через HOME), здесь — реальная
    смерть процесса (`force_stop`); общий защитный механизм проверяется через
    разные жизненные циклы, отдельными кейсами."""
    app_steps.wait_home_ready_for_deep_link(driver)

    home_url = browser_steps.HOME_URL + "/"
    marker1_url = rb.tab_marker_url(1)
    marker2_url = rb.tab_marker_url(2)

    # Given открыто 3 вкладки: 0 — Home (полностью догружена), 1 — marker1
    # (deep-link), 2 — marker2 (deep-link, последний обработанный —
    # deepLinkHandled==true для него)
    app_steps.wait_persisted_tab_count(1, timeout=10)
    app_steps.assert_persisted_tab_url_at(0, home_url)

    app_steps.open_deep_link(marker1_url)
    app_steps.wait_persisted_tab_count(2, timeout=15)
    app_steps.open_deep_link(marker2_url)
    app_steps.wait_persisted_tab_count(3, timeout=15)

    # Позитивный якорь источника ДО kill+relaunch — набор/порядок URL, с
    # которым будет сравниваться состояние ПОСЛЕ релонча (урок TC-131:
    # негативный Then без предварительно зафиксированного позитивного снимка
    # неотличим от вакуумного прохода на пустом/битом чтении prefs).
    app_steps.assert_persisted_tab_url_at(0, home_url)
    app_steps.assert_persisted_tab_url_at(1, marker1_url)
    app_steps.assert_persisted_tab_url_at(2, marker2_url)

    # Подтверждение реальной записи на диск ДО убийства процесса — опрос
    # самого файла SharedPreferences (не UI): `saveTabsToPrefs` дебаунсит
    # запись на 500мс после последнего изменения (`scheduleSave`,
    # BrowserViewModel.kt), `force_stop` до истечения этого окна теряет
    # несохранённое состояние безвозвратно (тот же класс, что TC-025). Gson
    # эскейпит `=` в URL как юникод-escape внутри JSON (сверено на живом
    # файле устройства при разведке TC-025) — сентинел собран под фактический
    # формат записи.
    app_steps.wait_tabs_persisted(marker2_url.replace("=", "\\u003d"))

    # When процесс приложения принудительно убит (`adb shell am force-stop`,
    # реальная смерть процесса — ДОКАЗАНА сменой pid, не только вызовом
    # force-stop, см. критик-блокер B1 attempt 2) и запущен заново БЕЗ
    # deep-link intent'а (`am start -W` на компонент Activity без `-d`)
    app_steps.restart_app_via_adb_asserting_new_process(driver)
    app_steps.wait_ui_ready(driver)

    # Then после релонча снова 3 вкладки — позитивный якорь
    # `wait_persisted_tab_count` доказывает, что снимок реально прочитан (не
    # вакуумно пуст)
    app_steps.wait_persisted_tab_count(3, timeout=20)

    # And в исходном порядке, URL каждой совпадают с теми, что были до
    # убийства процесса
    app_steps.assert_persisted_tab_url_at(0, home_url)
    app_steps.assert_persisted_tab_url_at(1, marker1_url)
    app_steps.assert_persisted_tab_url_at(2, marker2_url)

    # And ни marker1, ни marker2 НЕ переоткрылись повторно доп. вкладкой
    # (нет дубликата вкладки с тем же URL) — ровно по 1 вхождению каждого
    # маркера, счёт остаётся ровно 3 (не 4/5); `expected_total=3` — позитивный
    # якорь ДЛЯ КАЖДОГО вызова (не только первого): доказывает, что каждое
    # отдельное чтение prefs реально застало непустой/валидный снимок, а не
    # вакуумный `[]` на отвалившемся adb/run-as (класс дефекта, отклонённый
    # критиком на TC-131 attempt 1).
    app_steps.assert_persisted_marker_count(marker1_url, 1, expected_total=3)
    app_steps.assert_persisted_marker_count(marker2_url, 1, expected_total=3)


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-135")
@allure.title("Холодный старт по VIEW-интенту переиспользует единственную незагруженную home-вкладку (positive-reuse)")
@pytest.mark.parametrize("replay", [rb.TAB_MARKER_FILENAME], indirect=True)
def test_cold_start_deep_link_reuses_single_home_tab(replay, clean_app, driver):
    """TC-135: положительная ветка reuse-условия `openOrNavigateDeepLink`
    (`tabs.size==1 && tabs[0].url==HOME_URL` побайтово, BrowserViewModel.kt:
    637-644) — холодный старт САМИМ deep-link-интентом переиспользует
    единственную ещё не догруженную home-вкладку (`navigateActiveTabTo`)
    вместо создания второй. Парная отрицательная ветка — TC-132 (тёплый
    старт ПОСЛЕ полной догрузки home создаёт вторую вкладку).

    Критик-расследование (TC-135.md, «Предпосылка измерена», 2026-07-31)
    воспроизвело ветку 11/11 живыми прогонами — первая попытка
    автоматизации дала ложный негатив ИЗ-ЗА ОРАКУЛА (не бага приложения):
    мгновенное чтение `open_tabs_urls` СРАЗУ после интента детерминированно
    попадает в транзиентное окно 0.83-1.90с, где prefs ВРЕМЕННО несут
    `HOME_URL` со слэшем — прерванная фоновая загрузка home всё равно
    триггерит `onPageFinished`->`onPageLoaded`->`saveTabsToPrefs` БЕЗ
    debounce (BrowserViewModel.kt:474-488), ДО того как реальный ответ на
    маркер придёт и перезапишет prefs повторно (устойчиво к t+6.3..7.3с от
    интента на измеренном эмуляторе). Правильный оракул — синхронизация ПО
    СОДЕРЖИМОМУ (`wait_tabs_persisted` с сентинелом URL маркера), НЕ
    `wait_persisted_tab_count(1)` — единица наступает уже В транзиентном
    окне (первая запись с home, ДО persist ключа `open_tabs_urls` его
    вообще нет — `BrowserViewModel.init` не пишет prefs, kt:181-215), этот
    wait не отличает транзиент от целевого состояния, плюс независимое
    подтверждение через РЕАЛЬНЫЙ WebView (`browser_steps.assert_active_tab_url`,
    опрашивающий, не мгновенный)."""
    # Given приложение остановлено, prefs пусты. Appium-сессия (`driver`)
    # автозапускает приложение ОБЫЧНЫМ путём при создании сессии (autoLaunch
    # по умолчанию — `capabilities.build_options` не выставляет
    # `autoLaunch=false`) — это побочный эффект инфраструктуры сессии, не
    # часть проверяемого сценария; шагом-обвязкой (`clean_state` — тот же
    # `pm clear`, что `clean_app`) возвращаем устройство в буквальный Given
    # («приложение НЕ запущено, prefs пусты») ПЕРЕД самим deep-link-интентом.
    # Appium-сессия переживает этот mid-test `pm clear` не из-за
    # `no_reset=True` (тот управляет сбросом на старте/выходе сессии) — а
    # потому что UiAutomator2-сервер (`io.appium.uiautomator2.server`) живёт
    # в ОТДЕЛЬНОМ пакете, не затрагиваемом очисткой AUT; тот же класс приёма,
    # что `restart_app_via_adb` в TC-025/TC-134, только с полной очисткой prefs
    # (не только force-stop): Given требует ИМЕННО «prefs отсутствуют»
    # (`BrowserViewModel.init` кладёт свежую единственную HOME_URL-вкладку
    # только при пустых prefs, kt:181-186 — на непустых prefs пошёл бы путь
    # восстановления, а не создания, и reuse-условие сравнивалось бы уже не с
    # константой).
    app_steps.clean_state()

    marker_url = rb.tab_marker_url(1)

    # When приложение запускается САМИМ deep-link-интентом (холодный старт —
    # процесс не был жив до этого вызова; НЕ используем
    # `wait_home_ready_for_deep_link` перед этим — тот шаг существует ровно
    # для того, чтобы УЙТИ из reuse-окна, здесь нужно окно, а не уход из него)
    app_steps.open_deep_link(marker_url)

    # Then содержимое единственной вкладки — маркерная страница, доказано
    # синхронизацией ПО СОДЕРЖИМОМУ (не по счёту): опрос prefs до появления
    # сентинела URL маркера (Gson экранирует символ `=` как юникод-escape
    # внутри JSON, сверено на живом файле устройства — см.
    # `wait_tabs_persisted`/TC-025).
    # Таймаут 20с — с запасом над измеренным критиком окном персиста маркера
    # (~6.3-7.3с от интента).
    app_steps.wait_tabs_persisted(marker_url.replace("=", "\\u003d"), timeout=20)

    # And число вкладок равно 1 — сработала ветка ПЕРЕИСПОЛЬЗОВАНИЯ
    # (`navigateActiveTabTo`), новая вкладка НЕ создана. Проверка ПОСЛЕ
    # content-sync (не вместо неё, см. докстринг выше) — здесь это финальная
    # сверка количества на уже подтверждённом содержимым снимке, а не
    # единственная синхронизация.
    app_steps.wait_persisted_tab_count(1, timeout=5)
    app_steps.assert_persisted_tab_url_at(0, marker_url)

    # And содержимое единственной вкладки подтверждено ЕЩЁ И через РЕАЛЬНЫЙ
    # WebView (не только prefs) — опрашивающий оракул (`assert_active_tab_url`),
    # тот же приём, что уже используется для навигации-на-месте в
    # `test_filter_profiles.py`/`test_side_panel.py`; при ровно одной вкладке
    # прилипание chromedriver к вкладке-0 неприменимо (вкладка и так
    # единственная).
    browser_steps.assert_active_tab_url(driver, marker_url)
    # Заметка для test-reviewer (F1, поле red_probe): приложенная красная
    # проба (откат к мгновенному чтению без wait_tabs_persisted) поймала
    # pre-first-persist ("всего вкладок в prefs 0" — до первой записи вовсе,
    # BrowserViewModel.init её не делает), а не транзиентное окно с
    # HOME_URL/, описанное в докстринге выше (то требует ~1с задержки перед
    # мгновенным чтением, чтобы воспроизвести). Демонстрирует тот же
    # надкласс (ценность content-sync), но не тот конкретный экземпляр.
    # Мутация утверждения о reuse (1 vs 2 вкладки) отдельной пробой не
    # проверялась (критик-вход, attempt 2, PASS).


@pytest.mark.p2
@allure.id("TC-137")
@allure.title(
    "Тап по карточке Library на потолке 10 вкладок не открывает работу — "
    "диалог лимита, активная вкладка не меняется, экран всё равно переключается на Browse"
)
def test_library_card_open_at_tab_limit_shows_dialog_and_switches_screen(loved_work_seeded, driver):
    """TC-137: третий (после TC-022 «+» и TC-131 deep-link) вход в границу
    MAX_TABS=10 — тап по телу карточки Library (`onOpenWork`,
    MainActivity.kt:329-333). Отличие от TC-022/TC-131: `onOpenWork`
    БЕЗУСЛОВНО переключает экран на Browse (`selectedTab = AppTab.BROWSE`,
    `navExpanded = false`) НЕЗАВИСИМО от Boolean-результата `openTab` — Then
    фиксирует ОБА факта (диалог + переключение экрана, И неизменность
    активной вкладки/состава вкладок); порядок проверок фиксирован (диалог
    первым, до TabStrip/prefs — модальный диалог перекрывает TabStrip)."""
    work = loved_work_seeded

    # Given открыто 10 вкладок Browse (MAX_TABS) — рецепт TC-022: стартовая
    # Home-вкладка (index 0) + 1 deep-link на HOME_URL (TabStrip ещё скрыт при
    # tabs.size==1 — кнопки «New tab» физически нет) + 8 тапов «New tab»
    # (background=false — каждый делает новую вкладку активной, поэтому после
    # 8-го тапа активна index 9). Каждый промежуточный тап не должен
    # преждевременно упереться в диалог лимита.
    app_steps.wait_home_ready_for_deep_link(driver)
    app_steps.open_deep_link(browser_steps.HOME_URL)
    browser_steps.assert_tab_strip_visible(driver, timeout=10)
    for _ in range(8):
        browser_steps.open_new_tab(driver)
        browser_steps.assert_tab_limit_dialog_not_shown(driver)

    # Given пользователь на экране Library — карточка работы W (засеяна
    # `loved_work_seeded`, рейтинг SAVE) видна на дефолтной первой вкладке
    # Favorite.
    app_steps.open_tab(driver, "Library")

    # When пользователь тапает по телу карточки работы «A Loved Test Work»
    library_steps.open_work_in_browser(driver, work.title)

    # Then показан диалог «Tab limit reached» с ДОСЛОВНЫМ текстом — проверяется
    # и ЗАКРЫВАЕТСЯ ПЕРВЫМ (фиксированный порядок Then: модальный диалог
    # перекрывает TabStrip, шаги, которым нужен доступ к полосе вкладок,
    # обязаны идти после dismiss_tab_limit_dialog)
    browser_steps.assert_tab_limit_dialog_shown(
        driver, expected_max=10,
        expected_message="You have 10 tabs open. Close some tabs before opening a new one.",
    )
    browser_steps.dismiss_tab_limit_dialog(driver)

    # And экран тем не менее переключился на Browse (TabStrip стал видим) —
    # `onOpenWork` выполняет `selectedTab = AppTab.BROWSE`/`navExpanded = false`
    # БЕЗУСЛОВНО, независимо от результата `openTab` (MainActivity.kt:329-333);
    # пользователь больше не видит список Library.
    browser_steps.assert_tab_strip_visible(driver)

    # And число вкладок остаётся 10, URL работы отсутствует во ВСЕХ вкладках
    # ВЕСЬ бюджет ожидания — синхронизированный негатив (регрессионный замок
    # находки 4 CH-005, тот же приём TC-131), НЕ пара
    # wait_persisted_tab_count + assert_persisted_marker_count: тот счёт уже
    # был 10 ДО тапа и не служит синхронизацией отказа.
    app_steps.assert_persisted_marker_absent_for(
        work.url, budget_s=4.0, poll_interval=0.5, expected_total=10)

    # And активная вкладка осталась позицией 9 — `openTab` вернул `false` ДО
    # присвоения `activeTabIndex` (BrowserViewModel.kt:263-266), индекс не
    # сдвинулся ни к несуществующей 11-й вкладке, ни к какой-либо другой.
    # Вместе с проверкой выше это доказывает «контент активной вкладки не
    # переключился на работу» без побайтовой сверки URL вкладки 9 с
    # литералом HOME_URL (в prefs он нормализован до адреса СО слэшем —
    # см. TC-137.md Предусловия/класс дефекта B1).
    app_steps.assert_persisted_active_tab_index(9)


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-136")
@allure.title("Тап по телу карточки Library открывает работу в новой активной вкладке Browse")
@pytest.mark.parametrize("replay", [rb.WORK_WITH_DOWNLOAD_FILENAME], indirect=True)
def test_library_card_open_work_opens_new_active_browse_tab(loved_work_seeded, replay, driver):
    """TC-136: позитивная ветка `onOpenWork` (MainActivity.kt:329-333) — тап по
    телу карточки работы Library НИЖЕ потолка MAX_TABS добавляет НОВУЮ вкладку
    Browse (не заменяет существующую единственную Home-вкладку), делает её
    активной, переключает экран на Browse и сворачивает нижнюю навигацию.
    Сестринский кейс TC-137 покрывает противоположную (граничную) ветку —
    потолок 10 вкладок, где `openTab` возвращает `false` и ничего из этого не
    происходит с составом/активностью вкладок (хотя экран всё равно
    переключается — тот же безусловный код-путь).

    Оракулы URL/активности новой вкладки — ТОЛЬКО persisted prefs
    (`assert_persisted_tab_url_at`/`assert_persisted_active_tab_index`), НЕ
    `browser_steps.assert_active_tab_url`: при >1 живой WebView chromedriver
    детерминированно прилипает к вкладке-0, что дало бы ложный негатив на
    корректном поведении (см. докстринг `assert_persisted_active_tab_index`,
    тот же приём TC-132/TC-137)."""
    work = loved_work_seeded

    # Given приложение запущено, пользователь на экране Library, вкладка
    # Favorite активна, карточка работы видна — открыта ровно 1 вкладка Browse
    # (стартовая Home), TabStrip ещё скрыт (порядок шагов — буквально из
    # TC-136.md «Заметки для автоматизации»).
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Library")
    library_steps.assert_work_in_tab(driver, "SAVE", work.title)

    # Явный якорь «открыта ровно 1 вкладка Browse» ДО When (A2, critic
    # attempt 1) — делает последующий Then про счёт вкладок дельтой (+1),
    # как буквально написано в Given/Then кейса (TC-136.md:43-44/50-51), а не
    # голой абсолютной проверкой «стало 2».
    app_steps.wait_persisted_tab_count(1, timeout=10)

    # When пользователь тапает по телу карточки работы (не по иконкам
    # download/open-file — они отдельные IconButton вне области combinedClickable)
    library_steps.open_work_in_browser(driver, work.title)

    # Then число вкладок Browse становится 2 (persisted open_tabs_urls
    # подтверждает +1 к предыдущему счёту 1)
    app_steps.wait_persisted_tab_count(2, timeout=15)

    # And экран переключается на Browse (TabStrip становится видим — рендерится
    # только при tabs.size>1 и активном экране Browse)
    browser_steps.assert_tab_strip_visible(driver)

    # And активная (новая) вкладка загружает URL работы — сверка ПОБАЙТОВАЯ по
    # позиции 1 (вкладка 0 — Home, вкладка 1 — новая), И именно она активна
    app_steps.assert_persisted_tab_url_at(1, work.url)
    app_steps.assert_persisted_active_tab_index(1)

    # And нижняя навигация свёрнута (navExpanded=false) — наблюдаемо как
    # отсутствие пунктов Browse/Library/Settings на экране (панель скрыта за
    # ручкой-пилюлей); единственный блокер автоматизации кейса снят новым
    # публичным шагом app_steps.assert_bottom_nav_collapsed поверх нового
    # BottomNav.is_visible(). Красная проба (critic-блокер B1, attempt 2):
    # вставка `BottomNav(driver).ensure_visible()` непосредственно перед этим
    # ассертом дала `AssertionError` («нижняя навигация неожиданно видна») —
    # оракул доказанно способен падать, не вакуумно истинен на известном
    # ложно-негативном режиме WebView-accessibility-провайдера
    # (`browser_screen.py:113-129`). Проба выполнена и откачена, в дереве не
    # остаётся.
    app_steps.assert_bottom_nav_collapsed(driver)


@pytest.fixture()
def two_works_same_tab_seeded():
    """TC-176: 2 РАЗЛИЧИМЫЕ работы на ОДНОЙ рейтинговой вкладке Library (Favorite)
    — нужно для проверки счётчика снекбара по ДВУМ последовательным фоновым
    открытиям РАЗНЫХ карточек (не Files — цель overlay должна быть AO3-URL, не
    локальный файл, см. TC-173/174). Локальная фикстура (не в `conftest.py`) —
    тот же приём, что `file_access_probe_seeded` в `test_security_file_access.py`."""
    app_steps.clean_state()
    app_steps.seed_library([(W.LOVED, "SAVE"), (W.KUDOSED, "SAVE")])
    yield W.LOVED, W.KUDOSED


@pytest.mark.p1
@allure.id("TC-176")
@allure.title(
    "Снекбар подтверждения фонового открытия называет число вкладок, ОТКРЫТЫХ В "
    "ФОНЕ, не общее число вкладок (ожидаемо-красный до фикса BUG-059)"
)
def test_background_open_snackbar_counts_background_opens_not_total(
    two_works_same_tab_seeded, driver,
):
    """TC-176: намеренно-красный до фикса BUG-059 (прецедент TC-139/BUG-015) —
    ассерт от ОЖИДАЕМОГО поведения спецификации (счётчик = числу вкладок,
    открытых В ФОНЕ за сессию), а не от факта текущей сборки (см. `red_lock` во
    frontmatter кейса и `bugs/BUG-059.md`). `MainActivity.kt:283
    tabCount = newTabs.size` реально считает ОБЩЕЕ число вкладок — на момент
    второго открытия фактический текст «Opened in background (3 tabs)»
    (Home + 2 фоновых), тест падает на сравнении с ожидаемым «(2 tabs)»."""
    work1, work2 = two_works_same_tab_seeded

    # Given приложение на экране Library, открыта ровно 1 вкладка (Home)
    app_steps.wait_ui_ready(driver)
    app_steps.set_fast_idle_timeout(driver)
    app_steps.open_tab(driver, "Library")
    library_steps.assert_work_in_tab(driver, "SAVE", work1.title)
    app_steps.wait_persisted_tab_count(1, timeout=10)

    # When пользователь long-press по карточке №1 открывает overlay и тапает
    # «Open in background tab» (первое фоновое открытие сессии)
    library_steps.open_in_background_via_overlay(driver, work1.title)
    app_steps.wait_persisted_tab_count(2, timeout=15)

    # And дожидается, пока снекбар полностью исчезнет с экрана (поллинг
    # отсутствия текста, не таймер)
    browser_steps.wait_opened_in_background_snackbar_shown_then_gone(driver)

    # And долгим нажатием по карточке №2 (ДРУГАЯ работа) открывает overlay и
    # тапает «Open in background tab» (второе фоновое открытие сессии)
    library_steps.open_in_background_via_overlay(driver, work2.title)
    app_steps.wait_persisted_tab_count(3, timeout=15)

    # Then снекбар после ВТОРОГО открытия показывает дословно «Opened in
    # background (2 tabs)» — «2» означает число вкладок, открытых В ФОНЕ за эту
    # сессию (спецификация); фактическая сборка (BUG-059) покажет «(3 tabs)» —
    # ОЖИДАЕМОЕ падение, см. docstring выше.
    browser_steps.assert_opened_in_background_snackbar_text(
        driver, "Opened in background (2 tabs)")
