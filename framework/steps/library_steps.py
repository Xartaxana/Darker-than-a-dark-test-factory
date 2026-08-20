"""Бизнес-шаги экрана Library (GWT)."""
from __future__ import annotations

import logging
import time

import allure

from framework.core.waits import assert_holds_for
from framework.screens.library_screen import FILES_TAB, TAB_BY_RATING, LibraryScreen

logger = logging.getLogger(__name__)


@allure.step("When открыта вкладка Library для рейтинга {rating}")
def open_library_tab_for(driver, rating: str):
    LibraryScreen(driver).open_tab_for_rating(rating)


@allure.step("When открыта вкладка Library FILES")
def open_files_tab(driver):
    LibraryScreen(driver).open_tab(FILES_TAB)


@allure.step("Then виден таб Favorite (Library загрузился)")
def assert_library_loaded(driver):
    assert LibraryScreen(driver).has_work("FAVORITE", timeout=8), (
        "экран Library не отрисовался (не видна вкладка FAVORITE)"
    )


@allure.step("Then вкладки Library идут слева направо: {labels}")
def assert_library_tabs_order(driver, labels: list[str]):
    lib = LibraryScreen(driver)
    positions = [(label, lib.tab_label_x(label)) for label in labels]
    missing = [label for label, x in positions if x is None]
    assert not missing, f"вкладки не найдены: {missing}"
    xs = [x for _, x in positions]
    assert xs == sorted(xs), (
        f"порядок вкладок слева направо не соответствует ожидаемому: {positions}"
    )


@allure.step("Then во вкладке {rating} присутствует работа «{title}»")
def assert_work_in_tab(driver, rating: str, title: str):
    lib = LibraryScreen(driver).open_tab_for_rating(rating)
    assert lib.has_work(title), (
        f"работа «{title}» не найдена во вкладке {TAB_BY_RATING[rating]}"
    )


@allure.step("Then во вкладке {rating} НЕТ работы «{title}»")
def assert_work_not_in_tab(driver, rating: str, title: str):
    """AT-BUG-083 (сиблинг AT-BUG-082, D-0043 «класс, не экземпляр»): раньше
    делала ОДИН `has_work(timeout=4)` сразу после `open_tab_for_rating` — тот
    же класс гонки с анимацией `HorizontalPager` (см. блок-комментарий у
    `_poll_tab_absent` ниже). Теперь settle+hold опрос через `_poll_tab_absent`,
    обобщённый из `_poll_files_tab_absent` (AT-BUG-082) на ЛЮБУЮ вкладку."""
    tab_label = TAB_BY_RATING[rating]
    lib = LibraryScreen(driver).open_tab_for_rating(rating)
    assert _poll_tab_absent(lib, title, tab_label), (
        f"работа «{title}» неожиданно присутствует во вкладке {tab_label}"
    )


@allure.step("Then во вкладке {rating} работа «{title}» показывает личные теги «{tags_text}»")
def assert_work_tags_visible(driver, rating: str, title: str, tags_text: str):
    lib = LibraryScreen(driver).open_tab_for_rating(rating)
    assert lib.has_work(title), (
        f"работа «{title}» не найдена во вкладке {TAB_BY_RATING[rating]}"
    )
    assert lib.has_tags_text(tags_text), (
        f"личные теги «{tags_text}» не отображены на карточке «{title}»"
    )


@allure.step("Then во вкладке {rating} работа «{title}» показывает note-иконку (сохранённый комментарий)")
def assert_work_note_icon_visible(driver, rating: str, title: str):
    lib = LibraryScreen(driver).open_tab_for_rating(rating)
    assert lib.has_work(title), (
        f"работа «{title}» не найдена во вкладке {TAB_BY_RATING[rating]}"
    )
    assert lib.has_note_icon(), (
        f"note-иконка не отображена на карточке «{title}»"
    )


@allure.step("Then во вкладке FILES присутствует работа «{title}»")
def assert_work_in_files_tab(driver, title: str):
    lib = LibraryScreen(driver).open_tab(FILES_TAB)
    assert lib.has_work(title), f"работа «{title}» не найдена во вкладке FILES"


# --- AT-BUG-082/083: settle+hold опрос для негативного Then ЛЮБОЙ вкладки ---
# AT-BUG-083 (D-0043 «класс, не экземпляр», queued follow-up AT-BUG-082):
# `assert_work_not_in_tab` (ЛЮБАЯ rating-вкладка — FAVORITE/KUDOSED/READ/
# PENDING/DISLIKED, не только FILES) была СТРУКТУРНО ИДЕНТИЧНА
# `assert_work_not_in_files_tab` ДО AT-BUG-082: один `has_work(timeout=4)`
# сразу после `open_tab_for_rating`/`open_tab` — тот же класс гонки, разбор
# ниже относится к ней в РАВНОЙ мере. `_poll_tab_absent` — обобщение
# исходного `_poll_files_tab_absent` на произвольную вкладку (принимает
# `tab_label` для сообщений/логов вместо жёстко зашитого «FILES»);
# `_poll_files_tab_absent` оставлена тонкой обёрткой (`tab_label="FILES"`) —
# сохраняет старое имя/сигнатуру для `assert_work_not_in_files_tab` и
# существующих юнит-проб (`test_library_files_tab_settle_unit.py`).
#
# `LibraryScreen.open_tab`/`open_tab_for_rating` таплю по вкладке top bar,
# реализованной через `HorizontalPager` (`LibraryScreen.kt:238`) — сам Compose
# АНИМИРОВАННО скроллит страницы; во время скролла ИСХОДНАЯ (ещё не полностью
# ушедшая с экрана) страница временно сосуществует с ЦЕЛЕВОЙ в accessibility-
# дереве. Прежний (докоммитный, ДО AT-BUG-082) код (`is_present(timeout=4)`,
# ОДИН `WebDriverWait`) возвращал `True` НЕМЕДЛЕННО на первом же снимке, где
# заголовок найден ГДЕ УГОДНО на экране — включая ещё не до конца ушедшую
# СТАРУЮ вкладку (например FAVORITE, где работа реально есть до скачивания),
# что ошибочно трактовалось как «работа появилась на FILES» (`bugs/
# AT-BUG-082.md`: 7-й тест по порядку в `test_downloads.py`, TC-112, красный
# ТОЛЬКО в полном прогоне файла). Тот же класс гонки, что `AT-BUG-081` (Then
# читает раньше, чем состояние устаканилось), но здесь слой — UI-анимация
# Pager'а, не асинхронная запись Room. AT-BUG-082 Б2/Б3 критик-вход:
# `LibraryScreen.open_tab` теперь сам ждёт устаканивания Pager'а ПЕРЕД
# возвратом (см. `library_screen.py`, `_settle_tab_switch`) — settle-фаза
# ниже, соответственно, реже видит транзитный стейл-позитив вовсе, но
# оставлена как вторая линия защиты (settle внутри `open_tab` — best-effort,
# не гарантирует конвергенции, см. её докстринг).
#
# Фаза 1 (settle) опрашивает `has_work` до `_FILES_TAB_SETTLE_TIMEOUT` секунд
# (шаг `_FILES_TAB_SETTLE_INTERVAL`, БЫСТРОЕ одиночное чтение на каждом шаге,
# `_FILES_TAB_SETTLE_READ_TIMEOUT`) — отфильтровывает транзитный стейл-
# позитив ещё-не-ушедшей соседней вкладки; тот же приём, что
# `settings_steps._poll_ratings_marker` (AT-BUG-081). Если присутствие НИКОГДА
# не сходится к отсутствию за весь settle-бюджет — это уже НЕ транзитный
# артефакт, а persistent-регрессия, возвращается `False` немедленно.
#
# AT-BUG-082 Б1 критик-вход (rework, живой пробой): attempt 1 (settle-фаза
# БЕЗ фазы 2 ниже) выходил на ПЕРВОМ ЖЕ чтении «отсутствует» — фактическое
# наблюдаемое окно негатива схлопнулось с прежних 4с (старая ОДНОРАЗОВАЯ
# семантика наблюдала присутствие В ЛЮБОЙ момент 4с-окна) до
# `_FILES_TAB_SETTLE_READ_TIMEOUT=1s` в худшем случае немедленной сходимости.
# Критик воспроизвёл живым прогоном: работа появляется на FILES через ~1.5с
# (внутри старого 4с окна, ПОСЛЕ первого «отсутствует»-чтения attempt 1) —
# attempt 1 давал ложный PASS там, где старая семантика честно давала FAIL.
# Фаза 2 (hold) ниже держит «отсутствует» ФИКСИРОВАННЫЙ
# `_FILES_TAB_ABSENT_HOLD_BUDGET` (`waits.assert_holds_for`, докстринг
# буквально описывает нужный паттерн: «держать» негатив весь бюджет, не
# полагаться на первый снимок) — суммарное окно наблюдения (settle + hold)
# ГАРАНТИРОВАННО >= старых 4с независимо от того, как быстро settle-фаза
# сошлась к отсутствию (hold-бюджет фиксирован, не «остаток» вычитанием уже
# потраченного времени — проще и надёжнее арифметики остатка).
_FILES_TAB_SETTLE_TIMEOUT = 3.0
_FILES_TAB_SETTLE_INTERVAL = 0.3
_FILES_TAB_SETTLE_READ_TIMEOUT = 1
_FILES_TAB_ABSENT_HOLD_BUDGET = 4.0
_FILES_TAB_ABSENT_HOLD_INTERVAL = 0.3


def _poll_tab_absent(lib: LibraryScreen, title: str, tab_label: str) -> bool:
    """Возвращает `True`, если `title` settled на ОТСУТСТВИИ на текущей
    вкладке `tab_label` (фаза 1) И остаётся отсутствующей весь
    `_FILES_TAB_ABSENT_HOLD_BUDGET` (фаза 2) — см. блок-комментарий у
    констант выше (AT-BUG-082 Б1/Б4 критик-вход rework, обобщено на любую
    вкладку в AT-BUG-083). `tab_label` — только для сообщений/логов, не
    влияет на логику опроса (одна и та же гонка на любой вкладке того же
    `HorizontalPager`)."""
    deadline = time.monotonic() + _FILES_TAB_SETTLE_TIMEOUT
    present = lib.has_work(title, timeout=_FILES_TAB_SETTLE_READ_TIMEOUT)
    settle_reads = 1
    while present and time.monotonic() < deadline:
        time.sleep(_FILES_TAB_SETTLE_INTERVAL)
        present = lib.has_work(title, timeout=_FILES_TAB_SETTLE_READ_TIMEOUT)
        settle_reads += 1
    if present:
        # Никогда не сходилось к отсутствию за весь settle-бюджет — persistent
        # присутствие, настоящая регрессия (не транзитный артефакт анимации).
        return False
    if settle_reads > 1:
        # Б4 критик-вход: транзитный стейл-позитив был ПРОГЛОЧЕН settle-фазой
        # (сошлись к отсутствию не с первого чтения) — паспорт факта, не
        # молчаливое решение, иначе "фикс подтверждён живыми прогонами"
        # неотличим от "гонка просто не выстрелила в этом прогоне" (правило 14).
        logger.warning(
            "AT-BUG-082/083 (library_steps._poll_tab_absent): транзитный "
            "стейл-позитив «%s» на вкладке %s проглочен settle-фазой за "
            "%d чтени(й/е) — расследуй, если повторяется часто (может "
            "означать, что анимация Pager'а систематически шире "
            "_FILES_TAB_SETTLE_TIMEOUT=%.1fs)",
            title, tab_label, settle_reads, _FILES_TAB_SETTLE_TIMEOUT,
        )
    try:
        assert_holds_for(
            lambda: not lib.has_work(title, timeout=_FILES_TAB_SETTLE_READ_TIMEOUT),
            budget_s=_FILES_TAB_ABSENT_HOLD_BUDGET,
            interval_s=_FILES_TAB_ABSENT_HOLD_INTERVAL,
            msg=f"работа «{title}» вновь появилась во вкладке {tab_label} во время hold-окна наблюдения",
        )
    except AssertionError:
        # Б1/Б4 критик-вход: ПОЗДНЯЯ регрессия — появилась ПОСЛЕ того, как
        # settle-фаза уже сошлась к отсутствию, но ДО истечения полного окна
        # наблюдения (ровно сценарий живой пробы критика). hold-фаза её ловит
        # (см. докстринг констант) — лог оставляет паспорт факта рядом с
        # итоговым AssertionError вызывающего Then (assert_work_not_in_files_tab/
        # assert_work_not_in_tab).
        logger.warning(
            "AT-BUG-082/083 (library_steps._poll_tab_absent): работа "
            "«%s» вновь появилась во вкладке %s во время hold-окна "
            "наблюдения (после %d settle-чтени(й/е)) — ПОЗДНЯЯ регрессия, "
            "пойманная hold-фазой (старый settle-only код пропустил бы её)",
            title, tab_label, settle_reads,
        )
        return False
    return True


def _poll_files_tab_absent(lib: LibraryScreen, title: str) -> bool:
    """Тонкая обёртка над `_poll_tab_absent(lib, title, "FILES")` — сохраняет
    старое имя/сигнатуру (AT-BUG-082) для `assert_work_not_in_files_tab` и
    существующих юнит-проб (`test_library_files_tab_settle_unit.py`)."""
    return _poll_tab_absent(lib, title, "FILES")


@allure.step("Then во вкладке FILES НЕТ работы «{title}»")
def assert_work_not_in_files_tab(driver, title: str):
    lib = LibraryScreen(driver).open_tab(FILES_TAB)
    assert _poll_files_tab_absent(lib, title), (
        f"работа «{title}» неожиданно присутствует во вкладке FILES"
    )


@allure.step("When работа «{title}» открыта из Library в Browse (добавляется вкладка)")
def open_work_in_browser(driver, title: str):
    lib = LibraryScreen(driver)
    assert lib.has_work(title), f"работа «{title}» не найдена в Library"
    lib.open_work(title)


@allure.step("When пользователь тапает open-иконку работы «{title}» (открыть скачанный файл)")
def open_downloaded_file(driver, title: str):
    lib = LibraryScreen(driver)
    assert lib.has_work(title), f"работа «{title}» не найдена"
    lib.tap_open_icon(title)


@allure.step("When пользователь тапает download-иконку работы «{title}» (ручное скачивание)")
def download_via_card(driver, title: str):
    lib = LibraryScreen(driver)
    assert lib.has_work(title), f"работа «{title}» не найдена"
    lib.tap_download_icon(title)


@allure.step("When long-press по карточке «{title}», в overlay выбрано «{action}»")
def delete_via_overlay(driver, title: str, action: str):
    lib = LibraryScreen(driver)
    assert lib.has_work(title), f"работа «{title}» не найдена"
    lib.long_press_work(title)
    assert lib.delete_overlay_visible(), "overlay удаления не появился после long-press"
    if action == "Delete work":
        lib.tap_delete_work()
    elif action == "Delete downloaded file":
        lib.tap_delete_downloaded_file()
    else:
        raise ValueError(f"неизвестное действие overlay: {action}")


# TC-176 rework attempt2 (классовая правка, критик-вход rework attempt1):
# длительность СВОЕГО long-press-жеста ниже, чем `LibraryScreen.long_press_work`
# (1000мс) — эмпирически проверено на живом устройстве (10+ успешных срабатываний
# overlay на этой длительности, 0 промахов «overlay не появился»), запас над
# системным long-press-порогом Android (`ViewConfiguration.getLongPressTimeout()`,
# по умолчанию 500мс, приложение его не переопределяет — `combinedClickable`
# без кастомного `viewConfiguration` в `LibraryScreen.kt` WorkCard) — 100мс.
# Не уменьшать дальше без новой серии живых прогонов (риск ложного НЕ-срабатывания
# long-press перевешивает выигрыш в тайминге за пределами уже проверенного значения).
_OPEN_IN_BACKGROUND_LONG_PRESS_DURATION_MS = 600


@allure.step("When long-press по карточке «{title}», в overlay выбрано «Open in background tab»")
def open_in_background_via_overlay(driver, title: str):
    """TC-173/174/175/176/189: overlay действий — тот же, что открывает
    `delete_via_overlay` (long-press карточки), первый пункт — «Open in
    background tab» (`WorkActionsSheetContent`, LibraryScreen.kt).

    TC-176 rework attempt2 (критик-вход rework attempt1, недостаточный запас
    тайминга burst-окна — `bugs/AT-BUG-075.md`): классовая правка примитива,
    затрагивает ВСЕХ потребителей (TC-173/174/175/176/189) — таргетно
    перепрогнаны все пятеро после правки, регрессии не найдено. Раньше тело
    дублировало ОДИН find (через `has_work`) ДВАЖДЫ подряд (`has_work` →
    `long_press_work`, который сам делает `find`) и держало ОТДЕЛЬНЫЙ
    `assert delete_overlay_visible()` ПЕРЕД `tap_open_in_background()`, хотя
    сам `tap()` уже ждёт `element_to_be_clickable` на целевом пункте overlay —
    оба были буквально избыточным повторным round-trip'ом Appium-команды на
    УЖЕ известное состояние (карточка видна — доказано предусловиями
    сценария/предыдущими шагами; overlay откроется тем же кодовым путём, что
    и у карточки №1, которая уже отработала в этом самом тесте).

    TC-176 rework attempt3 (`bugs/AT-BUG-075.md`, критик-вход rework
    attempt2, находка 2 — слоевой дрейф): раньше эта функция САМА делала
    `driver.execute_script("mobile: longClickGesture", ...)` и сама собирала
    локатор карточки, дублируя `LibraryScreen.long_press_work` вопреки
    `docs/02-framework-architecture.md:44` («long-press — зона `screens/`,
    не `steps/`»). Теперь делегирует В `long_press_work` (параметризован
    `duration_ms`) — ОДИН locator/gesture-путь для ВСЕХ вызывающих (включая
    `delete_via_overlay`), не два копии одной логики. `find()` карточки
    выполняется внутри `long_press_work`, служит и precondition-проверкой —
    поднимает `TimeoutException`, если карточка не найдена.

    AT-BUG-075 rework attempt3 добавляла отдельный степ `find_work_card_
    element` + пред-найденный элемент карточки №2 (передавался через
    `element=` в `long_press_work`, вынося дорогой `find()` ЗА ПРЕДЕЛЫ
    таймингово-чувствительного burst-окна TC-176) — снято rework attempt4
    (координатор): измеримый эффект тонул в разбросе между прогонами
    (диапазон natural gap СТАЛ ШИРЕ, не уже), а сам приём вводил новый класс
    флака (`StaleElementReferenceException` на закэшированном elementId,
    непойманный `--reruns`). `element=`-параметр убран из сигнатур обеих
    функций (критик-гейт О-1, 2026-08-20) — ни один вызывающий код его не
    передавал. Сразу `tap_open_in_background()` (сам ждёт появления/
    кликабельности пункта — отдельный `delete_overlay_visible()` перед ним
    был чистым дублированием его собственного ожидания). Эффект правки
    rework attempt2 — см. TC-176.md, раздел «Тайминг burst-окна»; для
    TC-173/174/175/189 (без тайминговых ограничений) эффект — только
    ускорение прогона, семантика не меняется."""
    lib = LibraryScreen(driver)
    lib.long_press_work(title, duration_ms=_OPEN_IN_BACKGROUND_LONG_PRESS_DURATION_MS)
    lib.tap_open_in_background()


@allure.step("Then overlay действий Library закрыт")
def assert_actions_overlay_closed(driver, timeout: int | None = None):
    """TC-175: `pendingActions` сбрасывается в `null` СРАЗУ по тапу пункта
    overlay (LibraryScreen.kt), независимо от исхода самого действия —
    проверяется через отсутствие соседнего пункта «Delete work» того же
    bottom sheet (не заводит отдельный локатор — переиспользует
    `delete_overlay_visible`)."""
    assert not LibraryScreen(driver).delete_overlay_visible(timeout=timeout if timeout is not None else 2), (
        "overlay действий Library неожиданно остался открыт"
    )


@allure.step("Then карточка «{title}» показывает download-иконку (файл не скачан)")
def assert_download_icon_shown(driver, title: str):
    lib = LibraryScreen(driver)
    assert lib.has_work(title), f"работа «{title}» не найдена"
    assert lib.has_download_icon(title), f"download-иконка не появилась у «{title}»"


@allure.step("Then карточка «{title}» показывает open-иконку (файл скачан)")
def assert_open_icon_shown(driver, title: str, timeout: int | None = None):
    """`timeout` — явный override дефолта (8с): скачивание через сеть (TC-032/033,
    DownloadRepository.downloadWork через replay-прокси) асинхронное и медленнее,
    чем локальная фикстура (downloaded_work_seeded), где дефолта достаточно."""
    lib = LibraryScreen(driver)
    assert lib.has_work(title, timeout=timeout), f"работа «{title}» не найдена"
    assert lib.has_open_icon(title, timeout=timeout), f"open-иконка не появилась у «{title}»"


@allure.step("Then карточка «{title}» НЕ показывает download-иконку (card-scoped дискриминация)")
def assert_download_icon_not_shown(driver, title: str, timeout: int | None = None):
    """Негатив-парник `assert_download_icon_shown` — нужен для доказательства
    card-scoped дискриминации `_card_icon_locator` (B2, misc-batch-lead-queue-0729
    attempt 2): на экране с НЕСКОЛЬКИМИ карточками разного download-статуса эта
    проверка ловит регрессию к screen-wide поиску (старый баг, см. докстринг
    `_card_icon_locator` в `library_screen.py`) — карточка «{title}» имеет
    open-иконку у СОСЕДА, но своей download-иконки быть не должно."""
    lib = LibraryScreen(driver)
    assert lib.has_work(title), f"работа «{title}» не найдена"
    assert not lib.has_download_icon(title, timeout=timeout if timeout is not None else 4), (
        f"download-иконка неожиданно присутствует у «{title}» "
        "(похоже на screen-wide утечку локатора с чужой карточки)"
    )


@allure.step("Then карточка «{title}» НЕ показывает open-иконку (card-scoped дискриминация)")
def assert_open_icon_not_shown(driver, title: str, timeout: int | None = None):
    """Негатив-парник `assert_open_icon_shown` — см. `assert_download_icon_not_shown`."""
    lib = LibraryScreen(driver)
    assert lib.has_work(title), f"работа «{title}» не найдена"
    assert not lib.has_open_icon(title, timeout=timeout if timeout is not None else 4), (
        f"open-иконка неожиданно присутствует у «{title}» "
        "(похоже на screen-wide утечку локатора с чужой карточки)"
    )


# --- Фильтр-панель (TC-027/TC-028/TC-029) ---

@allure.step("When пользователь открывает фильтр-панель Library")
def open_library_filter_sheet(driver):
    lib = LibraryScreen(driver)
    lib.open_filter_sheet()
    assert lib.is_filter_sheet_open(), "фильтр-панель Library не открылась"


@allure.step("When пользователь задаёт диапазон word count min={min_words} max={max_words} и применяет фильтр")
def apply_word_count_filter(driver, min_words: str = "", max_words: str = ""):
    lib = LibraryScreen(driver)
    if min_words:
        lib.set_min_words(min_words)
    if max_words:
        lib.set_max_words(max_words)
    lib.tap_apply_filters()


@allure.step("When пользователь выбирает фандом «{fandom}» в фильтр-панели и применяет фильтр")
def apply_fandom_filter(driver, fandom: str):
    lib = LibraryScreen(driver)
    lib.open_fandom_picker()
    lib.select_fandom_option(fandom)
    lib.tap_apply_filters()


@allure.step("When пользователь устанавливает чекбокс downloaded-only={checked} и применяет фильтр")
def apply_downloaded_only_filter(driver, checked: bool):
    lib = LibraryScreen(driver)
    lib.set_downloaded_only(checked)
    lib.tap_apply_filters()


# --- Личные теги / свободный текст (TC-060/TC-061) ---

@allure.step("When пользователь выбирает теги {tags} в фильтр-панели и применяет фильтр")
def apply_tags_filter(driver, tags: list[str]):
    lib = LibraryScreen(driver)
    for tag in tags:
        lib.select_tag(tag)
    lib.tap_apply_filters()


@allure.step("When пользователь вводит запрос «{query}» в поле «Search any field» и применяет фильтр")
def apply_search_filter(driver, query: str):
    lib = LibraryScreen(driver)
    lib.set_search_query(query)
    lib.tap_apply_filters()


@allure.step("When пользователь очищает поле поиска (крестик) и применяет фильтр")
def clear_search_filter(driver):
    lib = LibraryScreen(driver)
    lib.clear_search_query()
    lib.tap_apply_filters()


# --- Сортировка (TC-030) ---

@allure.step("When запомнена исходная Y-позиция верхней видимой карточки")
def capture_topmost_card_y(driver, known_titles: list[str]) -> int:
    lib = LibraryScreen(driver)
    top = lib.topmost_visible_title(known_titles)
    assert top is not None, "не удалось определить верхнюю видимую карточку из известных"
    return lib.visible_card_y(top)


@allure.step("When список Library проскроллен вниз (виден маркер «{marker_title}»)")
def scroll_library_down_to(driver, marker_title: str):
    lib = LibraryScreen(driver)
    assert lib.swipe_to_text(marker_title), (
        f"не удалось проскроллить список Library до «{marker_title}»"
    )


@allure.step("When пользователь открывает dropdown сортировки в top bar и выбирает «{label}»")
def select_library_sort(driver, label: str, current_label: str = "Last read"):
    lib = LibraryScreen(driver)
    lib.open_sort_menu(current_label=current_label)
    lib.select_sort_option(label)


@allure.step("Then список упорядочен по убыванию word_count: {titles_desc}")
def assert_sorted_by_wordcount_desc(driver, titles_desc: list[str]):
    lib = LibraryScreen(driver)
    positions = [(t, lib.visible_card_y(t)) for t in titles_desc]
    missing = [t for t, y in positions if y is None]
    assert not missing, f"после сортировки не видны карточки: {missing}"
    ys = [y for _, y in positions]
    assert ys == sorted(ys), (
        f"порядок карточек не соответствует убыванию word_count: {positions}"
    )


@allure.step("Then триггер сортировки в top bar показывает «{label}»")
def assert_sort_trigger_label(driver, label: str):
    lib = LibraryScreen(driver)
    actual = lib.sort_trigger_label()
    assert actual == label, f"иконка-триггер сортировки не сменилась на «{label}» (сейчас: «{actual}»)"


@allure.step("Then опция сортировки «{label}» недоступна на текущей вкладке")
def assert_sort_option_unavailable(driver, label: str, current_label: str = "Last read"):
    """Открывает dropdown сортировки, проверяет отсутствие опции `label` среди
    видимых пунктов, закрывает dropdown БЕЗ выбора (TC-065: "Rating" существует
    только на вкладке Files/Downloads, `librarySortOptionsFor(isFilesTab)`)."""
    lib = LibraryScreen(driver)
    lib.open_sort_menu(current_label=current_label)
    assert not lib.is_present(lib.by_text(label), timeout=3), (
        f"опция сортировки «{label}» неожиданно доступна вне вкладки Files"
    )
    lib.close_sort_menu()


@allure.step("Then карточки видны в порядке: {titles_in_order}")
def assert_cards_in_order(driver, titles_in_order: list[str]):
    """Обобщение `assert_sorted_by_wordcount_desc` на произвольный порядок/поле
    сортировки (TC-031/TC-062/TC-063/TC-064/TC-065) — сравнивает видимые
    Y-координаты перечисленных карточек, не зависит от того, где среди них
    оказались посторонние (не перечисленные) карточки/филлеры."""
    lib = LibraryScreen(driver)
    positions = [(t, lib.visible_card_y(t)) for t in titles_in_order]
    missing = [t for t, y in positions if y is None]
    assert not missing, f"не видны карточки: {missing}"
    ys = [y for _, y in positions]
    assert ys == sorted(ys), (
        f"порядок карточек не соответствует ожидаемому: {positions}"
    )


@allure.step("Then список визуально сброшен к началу (карточка «{title}» на исходной Y-позиции)")
def assert_scroll_reset_to_top(driver, title: str, baseline_y: int, tolerance: int = 60):
    lib = LibraryScreen(driver)
    y = lib.visible_card_y(title)
    assert y is not None, f"карточка «{title}» не видна после сортировки"
    assert abs(y - baseline_y) <= tolerance, (
        f"скролл не сброшен к началу: карточка «{title}» на Y={y}, ожидалось около {baseline_y}"
    )


@allure.step("Then список остался на прежней позиции (карточка «{title}» на Y≈{baseline_y})")
def assert_scroll_retained(driver, title: str, baseline_y: int, tolerance: int = 60):
    """TC-177/TC-178: парник `assert_scroll_reset_to_top`, ПРОТИВОПОЛОЖНЫЙ по смыслу
    оракул — здесь ожидание «осталось где было», а не «вернулось к верху». Тело
    намеренно идентично (сравнение с произвольным `baseline_y`, снятым уже ПОСЛЕ
    скролла вниз, а не с Y верхней позиции) — заметки TC-177 называют это рутинным
    добавлением по образцу существующего оракула."""
    lib = LibraryScreen(driver)
    y = lib.visible_card_y(title)
    assert y is not None, f"карточка «{title}» не видна после переключения вкладок"
    assert abs(y - baseline_y) <= tolerance, (
        f"скролл неожиданно сместился: карточка «{title}» на Y={y}, ожидалось около {baseline_y}"
    )


# --- Пустая вкладка (TC-037: Library остаётся пустой после диалога Scan "0 файлов") ---

@allure.step("Then текущая вкладка Library пуста («Nothing here yet»)")
def assert_library_empty(driver, timeout: int | None = None):
    assert LibraryScreen(driver).is_empty(timeout=timeout), (
        "Library не пуста — ожидали пустое состояние «Nothing here yet»"
    )
