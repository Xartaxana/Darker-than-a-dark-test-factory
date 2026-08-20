"""Бизнес-шаги уровня приложения: установка состояния, запуск, навигация.
Единственный слой, где допустим allure.step (Given/When/Then). Без локаторов —
только композиция экранов и core.
"""
from __future__ import annotations

import json
import re
import shutil
import tempfile
from pathlib import Path

import allure
from appium.webdriver.common.appiumby import AppiumBy

from framework.config import settings
from framework.core import adb
from framework.core.waits import assert_holds_for, wait_for, wait_until
from framework.data import seed_db
from framework.data.works import Work
from framework.screens.browser_screen import BrowserScreen
from framework.screens.navigation import BottomNav


@allure.step("Given приложение с чистыми данными")
def clean_state():
    adb.clear_app_data()


@allure.step("Given в библиотеку засеяны работы с рейтингами")
def seed_library(works: list[tuple[Work, str]]):
    seed_db.seed(works)


@allure.step("Given в библиотеку засеяны работы с рейтингами, timestamp по порядку в списке")
def seed_library_ordered(works: list[tuple[Work, str]]):
    """TC-187: `seed_db.seed_ordered` — та же ОДНА транзакция device round-trip,
    что `seed_db.seed`, но каждая строка получает СТРОГО возрастающий
    `timestamp` по своей позиции в `works` — нужно, когда порядок обработки
    очереди `ORDER BY timestamp DESC` (`WorkRatingDao.getWorksWithEmptyTitle`)
    обязан быть детерминированным. См. докстринг `seed_db.seed_ordered`."""
    seed_db.seed_ordered(works)


@allure.step("Given в библиотеку засеяны записи с опциональными rating/comment/tags")
def seed_with_comment(rows: list[tuple[Work, str | None, str | None, str | None]]):
    seed_db.seed_with_comment(rows)


@allure.step("Given в библиотеку засеяны записи с опциональными rating/comment/tags, timestamp по порядку в списке")
def seed_with_comment_ordered(rows: list[tuple[Work, str | None, str | None, str | None]]):
    """TC-062: `seed_db.seed_with_comment_ordered` — та же ОДНА транзакция
    device round-trip, что `seed_db.seed_with_comment`, но каждая строка
    получает СТРОГО возрастающий `timestamp` по своей позиции в `rows` —
    заменяет несколько последовательных вызовов `seed_with_comment` (см.
    докстринг `seed_db.seed_with_comment_ordered`)."""
    seed_db.seed_with_comment_ordered(rows)


@allure.step("Given засеян(ы) filter-профиль(и): {profiles}")
def seed_filter_profiles(profiles: list[tuple[str, str]]) -> list[str]:
    """profiles: список (name, queryString) — сохранённые фильтр-поиски
    (TC-021 round-trip filterProfiles; TC-041/TC-042). Возвращает сгенерированные
    `id` в том же порядке (AT-BUG-073 критерий готовности п.3, см.
    `seed_db.seed_filter_profiles`) — существующие вызывающие игнорируют возврат,
    новые (область `sync`) могут его использовать."""
    return seed_db.seed_filter_profiles(profiles)


@allure.step("Given работа {work.title} засеяна с рейтингом {rating} и скачанным файлом")
def seed_downloaded_work(work: Work, rating: str, fixture_html: Path) -> str:
    """Кладёт `fixture_html` на устройство и заполняет `downloadPath` работы —
    без обращения к DownloadRepository/сети (TC-034/TC-035/TC-036)."""
    paths = seed_db.seed_with_download([(work, rating, fixture_html)])
    return paths[work.ao3_id]


@allure.step("Given работы засеяны с рейтингами и общим скачанным файлом")
def seed_downloaded_works(rows: list[tuple[Work, str, Path]]) -> dict[str, str]:
    """Как `seed_downloaded_work`, но НЕСКОЛЬКО работ одним батчем — каждая строка
    получает СВОЙ рейтинг, но может переиспользовать один и тот же локальный HTML-
    фикстур (TC-065: 5 работ на вкладке Files с разными рейтингами)."""
    return seed_db.seed_with_download(rows)


@allure.step("Given засеяны записи с комбинацией rating/comment/tags/downloadPath одной строкой")
def seed_with_comment_and_download(
    rows: list[tuple[Work, str | None, str | None, str | None, Path]]
) -> dict[str, str]:
    """Тонкая обёртка над `seed_db.seed_with_comment_and_download` (AT-BUG-046
    baseline A/C) — тот же приём, что остальные `seed_*` в этом модуле (Given-шаг
    с allure.step, без собственной логики). Нужна TC-256: baseline с ЛОКАЛЬНЫМИ
    title/fandom/wordCount, отличными от фикстурной work-страницы, rating=None,
    непустые comment/tags и реальный downloadPath — ОДНОЙ строкой (см. докстринг
    `seed_db.seed_with_comment_and_download`)."""
    return seed_db.seed_with_comment_and_download(rows)


@allure.step("Given в уже выбранной SAF-папке загрузок появляется файл {filename}")
def place_file_in_download_folder(remote_dir: str, filename: str, content: str) -> str:
    """Кладёт файл (adb push, вне UI) в каталог, УЖЕ выбранный ранее через
    `saf_steps.saf_pick_folder` в этой же сессии — не в момент самого выбора.

    TC-039: порядок «сначала выбрать папку, потом положить в неё orphan-файл»
    обязателен, если этот `ao3Id` совпадает с работой, которую последующий Restore
    должен ИМПОРТИРОВАТЬ (не пропустить как дубликат). Если такой файл лежит в
    папке уже НА МОМЕНТ выбора, `SettingsViewModel.setDownloadFolderUri` (синхронно)
    запускает `scanForDownloads(silent=true)` (`SettingsScreen.kt:523-530`), но САМ
    скан выполняется АСИНХРОННО (`viewModelScope.launch`) — раз файла в Room ещё нет
    (Library пуста по Given кейса), этот скан ДОБАВЛЯЕТ пустую stub-строку с этим
    `ao3Id` (`existing == null -> added++`) СРАЗУ, КАК ТОЛЬКО дойдёт очередь, и
    последующий Restore видит `ao3Id` уже существующим (`existingIds`) и
    ПРОПУСКАЕТ работу из backup как дубликат вместо импорта (воспроизведено на
    первом прогоне TC-039 — см. докстринг `restore_scan_workspace`). Вызывающий
    код обязан САМ гарантировать, что скан, запущенный самим ВЫБОРОМ папки, уже
    закончился до вызова этой функции с «настоящим» файлом (см. приём с
    decoy-файлом другого `ao3Id` в `restore_scan_workspace` — наблюдаемый диалог
    «Scan complete» как детерминированное доказательство завершения корутины); эта
    функция сама по себе — только механический adb push, без такой гарантии."""
    remote_file = f"{remote_dir}/{filename}"
    tmp_dir = Path(tempfile.mkdtemp(prefix="ao3_place_file_"))
    try:
        local = tmp_dir / filename
        local.write_text(content, encoding="utf-8")
        adb.push_external(local, remote_file)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return remote_file


@allure.step("When приложение запущено (нативный UI готов)")
def wait_ui_ready(driver) -> None:
    """Ждёт отрисовки нативной оболочки (WebView-контейнер в дереве) — без ожидания
    контента AO3. Для сценариев, не зависящих от стороннего сайта."""
    from selenium.webdriver.support import expected_conditions as EC
    wait_until(driver, EC.presence_of_element_located(
        (AppiumBy.CLASS_NAME, "android.webkit.WebView")),
        message="нативная оболочка приложения не отрисовалась")


@allure.step("When приложение запущено и AO3 загрузился")
def wait_app_ready(driver) -> str:
    return BrowserScreen(driver).wait_ao3_loaded()


@allure.step("When приложение запущено и домашняя вкладка полностью догрузилась (onPageFinished)")
def wait_home_ready_for_deep_link(driver) -> None:
    """Закрывает класс гонки deep-link vs home-load (area=tabs, TC-022/023/024/025,
    ревью 2026-07-18 п.5): используется ВМЕСТО `wait_ui_ready` перед ПЕРВЫМ
    `open_deep_link` в тесте, когда счёт/позиции вкладок зависят от того, что
    `openOrNavigateDeepLink` (BrowserViewModel.kt:637-644) пойдёт веткой
    «добавить вкладку», а не «навигировать плейсхолдер-Home на месте» (это
    происходит, только если `tabs[0].url` уже разошёлся с HOME_URL, что
    гарантировано лишь ПОСЛЕ `onPageLoaded` для домашней страницы). Не заменяет
    `wait_ui_ready` для остальных тестов — эта проверка сильнее и не нужна там,
    где деталь первого deep-link не влияет на количество вкладок."""
    BrowserScreen(driver).wait_home_page_loaded()


@allure.step("When открыт экран {tab}")
def open_tab(driver, tab: str):
    BottomNav(driver).open(tab)


@allure.step("Given UiAutomator2 waitForIdleTimeout снижен до {ms}мс")
def set_fast_idle_timeout(driver, ms: int = 100) -> None:
    """TC-176 (CH-009 test-automator note #4): дефолтный `waitForIdleTimeout`
    подвесил `find_elements` на 12.9-13.7с во время анимации snackbar'а
    (UiAutomator2 ждёт «покоя» дерева) — без этой настройки бюджет ожидания
    появления/исчезновения snackbar'а ненадёжен. Не локатор — настройка
    драйвера, поэтому живёт здесь, а не в screens/."""
    driver.update_settings({"waitForIdleTimeout": ms})


@allure.step("Then нижняя навигация свёрнута (панель не видна за ручкой-пилюлей)")
def assert_bottom_nav_collapsed(driver) -> None:
    """TC-136: доказывает `navExpanded = false` (MainActivity.kt:332) — после
    безусловного перехода на Browse (`onOpenWork`, MainActivity.kt:329-333)
    нижняя навигация свёрнута за ручкой-пилюлей, наблюдаемо как отсутствие
    пунктов Browse/Library/Settings на экране. Использует НОВУЮ публичную
    обёртку `BottomNav.is_visible()` (`framework/screens/navigation.py`) —
    прежде видимость определял только приватный `_nav_visible()`, вызываемый
    исключительно изнутри `navigation.py`; отдельного локатора эта обёртка не
    вводит, только делает существующую проверку доступной шагам (единственный
    блокер автоматизации TC-136, снят test-automator'ом)."""
    assert not BottomNav(driver).is_visible(), (
        "нижняя навигация неожиданно видна (ожидали свёрнутое состояние "
        "navExpanded=false сразу после перехода на Browse через карточку Library)"
    )


@allure.step("When приложение перезапущено")
def restart_app(driver):
    driver.terminate_app("com.example.ao3_wrapper")
    driver.activate_app("com.example.ao3_wrapper")


@allure.step("When системная тема ОС переключена: dark={dark}")
def set_system_dark_mode(dark: bool):
    """Переключение системной темы (`adb shell cmd uimode night yes/no`), не действие
    внутри приложения — см. TC-049 (тема System следует за ОС)."""
    adb.set_night_mode(dark)


@allure.step("When системный font_scale установлен в {scale}")
def set_font_scale(scale: float):
    """TC-107: системный масштаб шрифта, применяется ДО старта приложения.
    Вызывающий код обязан восстановить `1.0` в teardown (см. `adb.set_font_scale`)."""
    adb.set_font_scale(scale)


@allure.step("Given плотность экрана измерена (adb shell wm density)")
def measure_screen_density() -> int:
    """TC-148: РЕАЛЬНАЯ плотность текущего прогона (не хардкод из
    документации) — порог 48dp переводится в device px через это значение."""
    return adb.screen_density()


@allure.step("Then процесс приложения жив (pidof)")
def assert_process_alive():
    pid = adb.pidof_app()
    assert pid is not None, "процесс приложения не найден (pidof пуст) — похоже на краш"


@allure.step("When в приложение отправлен deep-link {url}")
def open_deep_link(url: str) -> None:
    """Реальный Android `ACTION_VIEW` intent (не `driver.get()`/`execute_script`) —
    единственный НАДЁЖНЫЙ способ загрузить ПРОИЗВОЛЬНЫЙ URL в НЕ-нулевую вкладку
    (area=tabs, TC-023/024/025, разведка 2026-07-18): `driver.get()`/`execute_script`
    внутри WEBVIEW-контекста ВСЕГДА бьют по вкладке-0 (chromedriver прилипает к
    первому когда-либо созданному WebView, см. докстринг
    `browser_screen.py::tab_chip_locator`), тогда как deep-link обрабатывается САМИМ
    приложением (`MainActivity.onNewIntent`->`onResume`->
    `BrowserViewModel.handleDeepLink`->`openOrNavigateDeepLink`) через РЕАЛЬНЫЙ
    Android `WebView.loadUrl()` — минуя chromedriver целиком, поэтому не подвержен
    прилипанию. `MainActivity` объявлен `launchMode="singleTask"` с intent-filter на
    `archiveofourown.org` (AndroidManifest.xml) — повторные intent'ы уже запущенному
    процессу идут через `onNewIntent`, не перезапускают Activity."""
    adb.shell(f'am start -a android.intent.action.VIEW -d "{url}" {settings.APP_PACKAGE}')


@allure.step("Then текущий pid процесса приложения зафиксирован")
def capture_app_pid() -> str:
    """TC-133 (critic-блокер B3, attempt 2): снимок pid ДО ухода в фон — для
    последующей сверки НА РАВЕНСТВО с pid ПОСЛЕ возврата на передний план
    (`assert_app_pid_unchanged`). `assert_process_alive` доказывает лишь «жив
    хоть какой-то процесс приложения» — этого недостаточно: если процесс убит
    СИСТЕМОЙ, пока приложение в фоне, и поднят холодно тем же `am start -n`
    (вкладки восстанавливаются из prefs), `assert_process_alive` тоже пройдёт,
    хотя это уже сценарий TC-134 (`force_stop`), а не TC-133 (простой возврат
    живого процесса). Только сверка pid ДО/ПОСЛЕ различает эти два сценария."""
    pid = adb.pidof_app()
    assert pid is not None, "процесс приложения не найден (pidof пуст) до ухода в фон"
    return pid


@allure.step("Then pid процесса приложения не изменился (тот же процесс): было {pid_before}")
def assert_app_pid_unchanged(pid_before: str) -> None:
    """TC-133: pid ПОСЛЕ возврата на передний план обязан побайтово совпасть с
    `pid_before` (см. `capture_app_pid`) — иначе процесс был перезапущен
    (системой в фоне или иначе), а не просто ушёл в фон и вернулся."""
    pid_after = adb.pidof_app()
    assert pid_after == pid_before, (
        f"pid процесса изменился: было {pid_before!r}, стало {pid_after!r} — "
        f"процесс НЕ пережил уход в фон (похоже на смерть+холодный перезапуск, "
        f"сценарий TC-134), а не простой возврат живого процесса (TC-133)"
    )


@allure.step("When приложение отправлено в фон (HOME, процесс не завершается)")
def send_app_to_background(driver) -> None:
    """TC-133: `adb shell input keyevent KEYCODE_HOME` уводит Activity в фон
    (`onPause`/`onStop`), в отличие от `restart_app_via_adb` (`am force-stop`,
    реальная смерть процесса) — процесс и его in-memory состояние
    (`deepLinkHandled`, список открытых вкладок) остаются живыми, ничего не
    сбрасывается.

    Critic-блокер B3 (attempt 2): само по себе отправление keyevent'а не
    наблюдаемо — `adb.shell` глотает returncode/stderr (см. докстринг
    `assert_persisted_marker_count`), поэтому тихо не сработавший HOME (сценарий
    б критика) неотличим от штатного успешного ухода в фон, если не дождаться
    ЭФФЕКТА. Дожидаемся `driver.query_app_state(APP_PACKAGE) < 4` (Appium
    `ApplicationState`: 4 == `RUNNING_IN_FOREGROUND`) — приложение реально
    покинуло передний план. Это же закрывает гонку между HOME и последующим
    `am start` в `bring_app_to_foreground_without_deep_link` (без ожидания
    `am start` мог прийти раньше, чем система обработала HOME)."""
    adb.shell("input keyevent KEYCODE_HOME")
    wait_for(
        lambda: driver.query_app_state(settings.APP_PACKAGE) < 4,
        timeout=10,
        message=(
            "приложение не покинуло передний план после KEYCODE_HOME "
            "(query_app_state осталось RUNNING_IN_FOREGROUND=4) — похоже на "
            "тихо не сработавший HOME"
        ),
    )


@allure.step("When нажата клавиша громкости {direction} (`input keyevent KEYCODE_VOLUME_{direction}`)")
def press_volume_key(driver, direction: str, oracle, timeout: int = 5) -> None:
    """AT-BUG-072 (test_debt, Fixed): обёртка над `adb shell input keyevent
    KEYCODE_VOLUME_DOWN/UP` по образцу `send_app_to_background` выше (`input
    keyevent KEYCODE_HOME` + ожидание `driver.query_app_state`) — голое
    нажатие клавиши само по себе НЕ наблюдаемо (`adb.shell` глотает
    returncode/stderr, см. докстринг `send_app_to_background`), поэтому тихо
    не сработавшее нажатие неотличимо от штатного эффекта без явного
    ожидания ПОСЛЕДСТВИЯ.

    `oracle` — параметризуемый предикат `Callable[[], bool]` без аргументов
    (вызывающий код замыкает нужный контекст в лямбде, тот же приём, что
    предикаты `wait_for` по всему фреймворку) — подтверждает, что нажатие
    СОСТОЯЛОСЬ. Конкретный наблюдаемый эффект зависит от сценария
    (`browse-volume-button-paging`, `MainActivity.kt:105-124,304-310`,
    `volumePageHandler`):
      - перехват активен (настройка `volume_button_scroll` ON, вкладка
        Browse фронтмост) — сдвиг `window.scrollY` активной вкладки
        (`BrowserViewModel.scrollActivePageBy` -> `evalJs(...
        window.scrollBy(0, Math.round(innerHeight*0.9)*direction)...)`),
        строго проверяется отдельно `browser_steps.
        assert_volume_page_scroll_delta` (TC-252);
      - перехват неактивен (настройка OFF либо активная вкладка != Browse,
        `MainActivity.kt:304` `volumePagingActive`) — штатное системное
        изменение громкости, наблюдаемое через `adb.volume_dialog_visible()`
        (`dumpsys window windows`, окно `VolumeDialogImpl` — НЕ входит в
        accessibility-дерево Appium, т.к. это отдельное OS-окно вне
        `app_package`, но видно через adb; TC-253/255).

    direction: `"down"` -> `KEYCODE_VOLUME_DOWN`, `"up"` -> `KEYCODE_VOLUME_UP`."""
    keycodes = {"down": "KEYCODE_VOLUME_DOWN", "up": "KEYCODE_VOLUME_UP"}
    assert direction in keycodes, f"direction должен быть 'down'/'up', получено {direction!r}"
    adb.shell(f"input keyevent {keycodes[direction]}")
    wait_for(
        oracle,
        timeout=timeout,
        message=(
            f"клавиша громкости {keycodes[direction]} не произвела наблюдаемого "
            f"эффекта за {timeout}с — похоже на тихо не сработавшее нажатие "
            f"(adb.shell глотает returncode, см. AT-BUG-072)"
        ),
    )


@allure.step(
    "Then системный индикатор громкости (VolumeDialogImpl) не появился в течение "
    "{budget_s}с после нажатия клавиши"
)
def assert_no_volume_dialog_appears(budget_s: float = 1.5, interval_s: float = 0.3) -> None:
    """TC-252: перехват `MainActivity.onKeyDown`/`onKeyUp` (возвращает `true`,
    событие потребляется до штатной обработки громкости системой) означает,
    что `VolumeDialogImpl` не должен возникнуть ВООБЩЕ — не гонка «появится
    чуть позже», а структурное отсутствие пути к показу диалога, пока
    перехват активен. Опрашивает ВЕСЬ бюджет (`assert_holds_for`, не
    одноразовое чтение) — симметрично `browser_steps.assert_scroll_unchanged`:
    негативный инвариант ловит и отложенный/анимированный показ диалога, не
    только мгновенный снимок сразу после нажатия."""
    assert_holds_for(
        lambda: not adb.volume_dialog_visible(),
        budget_s=budget_s,
        interval_s=interval_s,
        msg=(
            "системный индикатор громкости (VolumeDialogImpl, dumpsys window "
            "windows) появился после нажатия клавиши громкости, хотя перехват "
            "`MainActivity.volumePageHandler` должен был подавить его целиком "
            "(AT-BUG-072/TC-252)"
        ),
    )


@allure.step("When приложение возвращено на передний план БЕЗ нового deep-link intent'а")
def bring_app_to_foreground_without_deep_link() -> None:
    """TC-133: `am start -n <package>/<activity>` БЕЗ флага `-d` — в отличие от
    `open_deep_link` (шлёт `-a android.intent.action.VIEW -d "<url>"`, непустой
    `dataString`), этот intent несёт ПУСТОЙ `dataString`. `MainActivity` объявлен
    `launchMode="singleTask"` с intent-filter на `archiveofourown.org`
    (AndroidManifest.xml, см. докстринг `open_deep_link`) — компонентный intent
    без `-d`, посланный уже запущенному процессу (`singleTask`), тоже матчится
    через `onNewIntent`->`onResume`, а не перезапускает Activity/процесс — что и
    доказывает `assert_app_pid_unchanged` рядом с вызовом этого шага (TC-133,
    critic-блокер B3), а не предполагает недоказанным путём. Отличие от
    deep-link intent'а — только в том, что `intent.dataString` у этого intent'а
    `null`, поэтому `handleDeepLink`/`openOrNavigateDeepLink` не вызываются
    вовсе на этом событии (MainActivity.kt:96-101: `if (!deepLinkHandled) { ...;
    intent.dataString?.let { handleDeepLink } }` — `dataString` пуст, `let` не
    выполняется) — это подтверждают Then-шаги теста (набор вкладок не меняется),
    а не сам этот intent-вызов."""
    adb.shell(f"am start -n {settings.APP_PACKAGE}/{settings.APP_ACTIVITY}")


_TABS_PREFS_PATH = f"/data/data/{settings.APP_PACKAGE}/shared_prefs/ao3_settings.xml"


def _read_tabs_prefs_raw() -> str:
    """Сырой XML SharedPreferences приложения (`run-as cat`) — общий источник
    для `wait_tabs_persisted` (сентинел-присутствие) и парсерами ниже (TC-131:
    точный СЧЁТ вкладок/вхождений, не просто присутствие сентинела).

    AT-BUG-055 (Fixed): раньше это был голый `adb.run_as(f"cat {path}")` —
    `adb.shell()` отбрасывает `returncode`/`stderr` (`framework/core/adb.py`),
    поэтому нечитаемый/отвалившийся ответ (устройство офлайн, `run-as`
    отказал) неотличимо совпадал с легитимно пустым/отсутствующим файлом:
    `_parse_persisted_tabs` на таком входе штатно возвращал `[]`, и «0
    вкладок» означало и то и другое одновременно. Теперь читает через
    `adb.run_as_file_or_raise` (`framework/core/adb.py`) — тот же
    echo-sentinel-приём, что уже закрыл аналогичный класс в
    `seed_db._schema_ready`/`settings_steps.assert_ratings_present`
    (AT-BUG-044/045): честно различает «прочитано» / «файла легитимно ещё
    нет» / «отвалившийся adb/run-as» (последнее — явный `RuntimeError`, не
    молчаливая пустая строка)."""
    return adb.run_as_file_or_raise(_TABS_PREFS_PATH)


@allure.step("Then вкладки сохранены в SharedPreferences (сентинел «{sentinel}» найден)")
def wait_tabs_persisted(sentinel: str, timeout: int = 10) -> None:
    """Опрашивает файл SharedPreferences приложения (`ao3_settings.xml`, через
    `_read_tabs_prefs_raw`/`run-as cat` — тот же приём, что `pull_app_file`),
    пока в нём не появится `sentinel` — TC-025: `saveTabsToPrefs`
    (BrowserViewModel.kt `scheduleSave`) ДЕБАУНСИТ запись на 500мс после
    каждого скролл-события; принудительная остановка процесса (`am
    force-stop`) ДО истечения этого окна теряет несохранённое состояние
    безвозвратно (отменённая корутина никогда не допишет файл) —
    одноразовое чтение/фиксированная пауза было бы гонкой с этим дебаунсом,
    поэтому здесь именно опрос РЕАЛЬНОГО файла на диске, а не UI.

    AT-BUG-055 (Fixed): раньше читал `adb.run_as(f"cat {path}")` напрямую
    (собственная слепая копия того же примитива, что `_read_tabs_prefs_raw`
    использовала параллельно) — теперь единая точка чтения
    `_read_tabs_prefs_raw()`, честная (см. её докстринг). Отвалившийся
    adb/run-as больше не маскируется под «сентинел ещё не появился»: честное
    исключение из `_read_tabs_prefs_raw` ловится и ретраится самим `wait_for`
    (сохраняется в `last`), а на итоговом таймауте всплывает в тексте
    ошибки (`; last error: ...`) — тот же контракт, что уже описан у
    `wait_persisted_tab_count` (AT-BUG-036)."""

    def _check() -> bool:
        return sentinel in _read_tabs_prefs_raw()

    wait_for(_check, timeout=timeout,
             message=f"вкладки с сентинелом {sentinel!r} не появились в {_TABS_PREFS_PATH}")


_AM_KILLED_BY_AM_MARKER = "killedByAm=true"
_AM_RACE_LOGCAT_LINES = 400


@allure.step("Then вкладки сохранены в SharedPreferences после cold-start deep-link "
              "(сентинел «{sentinel}», устойчиво к гонке ActivityManager remove-task)")
def wait_tabs_persisted_after_cold_start_deep_link(url: str, sentinel: str, timeout: int = 20) -> None:
    """AT-BUG-087 (test_debt, flaky_test, Fixed) — TC-135
    (`test_cold_start_deep_link_reuses_single_home_tab`) звала голый
    `wait_tabs_persisted(timeout=20)` СРАЗУ после `open_deep_link` на процессе,
    только что поднятом ПОСЛЕ `clean_state()` (`pm clear`) на УЖЕ ЖИВОЙ
    Appium-сессии — это НЕ проблема латентности персиста (докстринг TC-135
    документировал окно t+6.3-7.3с, критик-расследование 2026-07-31).

    Живая диагностика этого бага (2026-08-20, 6 изолированных прогонов на
    ИЗМЕРЕННО свежей Appium-сессии, `-s` + `adb logcat`/prefs post-mortem)
    нашла РЕАЛЬНУЮ причину: `pm clear` синхронно возвращает успех ДО того, как
    внутренняя асинхронная уборка ActivityManager по предыдущей задаче
    (`ActivityTaskManager: Destroy timeout of remove-task`, ~150-200мс после
    `pm clear`) гарантированно завершилась. Если zygote-форк, поднятый СЛЕДУЮЩИМ
    `am start` (deep-link cold-start), попадает в это окно, ActivityManager
    убивает СВЕЖЕСОЗДАННЫЙ процесс САМ (наблюдался логкэт-паттерн: `Zygote:
    Forked child process <pid>` немедленно (<10мс) следом `ActivityManager:
    ProcessRecord{...} start not valid, killing pid=<pid>, killedByAm=true`) —
    `BrowserViewModel` в этом прогоне вообще НИКОГДА не инициализировался, маркер
    физически НЕ появляется НИ ЗА КАКОЙ таймаут (живой контроль: 90с опрос с
    интервалом 0.2с, `last_raw_len=0` весь бюджет — не "медленно", а "никогда";
    воспроизведено 2 раза из 6 изолированных прогонов, ~33%). Увеличение
    `timeout` здесь НЕ фикс (маскировка без эффекта — ждать нечего, процесс
    мёртв), фактическая латентность на ЗДОРОВЫХ прогонах (без гонки) —
    ~13-14с (выросла против 6.3-7.3с 2026-07-31, но это отдельное наблюдение,
    не причина красных прогонов: 13-14с всё ещё укладывается в 20с-бюджет).

    Фикс — детерминированное различение УБИТ-ГОНКОЙ / РЕАЛЬНО-МЕДЛЕННО ПОСЛЕ
    таймаута (не ретраит вслепую, не маскирует потенциальную иную причину):
    `adb.pidof_app() is None` ПОСЛЕ истечения `timeout` доказывает лишь «процесс
    сейчас не жив» — это истинно и при гонке AM, и (критик-блокер Б5,
    2026-08-20) при (а) РЕАЛЬНОМ крахе приложения на первом холодном старте
    после `pm clear` (если он не всегда воспроизводится, слепой ретрай на
    голом `pidof_app() is None` молча превратил бы КРАСНЫЙ прогон в зелёный —
    ровно маскировка регрессии, которую test-maintainer обязан ИЗБЕГАТЬ), и
    (б) при отвале самой adb-команды (`adb.shell`/`_run`, `framework/core/
    adb.py`, может вернуть пустой stdout не из-за мёртвого процесса
    приложения, а из-за сбоя транспорта). Принадлежность смерти процесса
    ИМЕННО гонке AM remove-task подтверждается ОТДЕЛЬНО — строкой
    `killedByAm=true` в логкэте (см. живой паттерн `Zygote: Forked child
    process <pid>` немедленно следом `ActivityManager: ... killing pid=<pid>,
    killedByAm=true` выше в этом докстринге): ПЕРЕД ретраем снимается
    `adb.shell("logcat -d -t ...")` и прикладывается через `allure.attach`
    (тот же стиль, что `perf_steps.assert_no_crash_or_anr`/
    `security_steps`) — ретрай происходит ТОЛЬКО если маркер найден; если
    процесс мёртв, но маркера в логкэте нет, это НЕИЗВЕСТНАЯ причина смерти
    (потенциальный краш приложения ИЛИ отвал adb) — `raise` без ретрая, не
    маскируем. Факт срабатывания ретрая (Б6) сам по себе тоже приложен через
    `allure.attach` ДО повторного `open_deep_link` — без этого частота гонки
    была бы ненаблюдаема в отчётах фабрики (зелёный-с-ретраем неотличим от
    зелёного-с-первого-раза).

    Повтор — ОДИН раз (не бесконечный ретрай): исходный `am start`, доказано,
    детерминированно убивается ГОНКОЙ, а не системной перегрузкой — вторая
    попытка почти всегда не попадает в то же узкое окно (эмпирически: race
    hit НЕ повторялся 2 раза подряд ни разу в 6 прогонах диагностики).
    Повторный `am start` с ТЕМ ЖЕ url безопасен — `MainActivity`
    `launchMode="singleTask"`, `openOrNavigateDeepLink` идемпотентна для
    одного и того же url (см. докстринг `open_deep_link`). Если ретрай ТОЖЕ
    падает по той же причине (killedByAm=true повторно) — итоговый
    `TimeoutError` пробрасывается наружу (bounded-ретрай, не бесконечный
    цикл): юнит-пробы см. `test_cold_start_deep_link_am_race_retry_unit.py`.

    Область: только TC-135 (единственный вызывающий этот шаг) — НЕ трогает
    дефолтный `wait_tabs_persisted`/`open_deep_link`, используемые TC-025 и
    остальными потребителями (не задета сторонняя латентность/поведение)."""
    open_deep_link(url)
    try:
        wait_tabs_persisted(sentinel, timeout=timeout)
        return
    except TimeoutError:
        if adb.pidof_app() is not None:
            raise  # процесс жив -- не гонка AM remove-task, не маскируем иную причину

        logcat_text = adb.shell(
            f"logcat -d -t {_AM_RACE_LOGCAT_LINES}", timeout=settings.ADB_SHELL_TIMEOUT
        )
        allure.attach(
            logcat_text, name="AT-BUG-087-logcat-on-pidof-none",
            attachment_type=allure.attachment_type.TEXT,
        )
        if _AM_KILLED_BY_AM_MARKER not in logcat_text:
            # Процесс мёртв, но НЕ доказано, что это гонка AM remove-task --
            # неизвестная причина (потенциальный краш приложения или отвал
            # adb, критик-блокер Б5) -- не маскируем слепым ретраем.
            raise

        allure.attach(
            f"AM-kill detected ({_AM_KILLED_BY_AM_MARKER}), retrying deep_link "
            f"once, timeout={timeout}s",
            name="AT-BUG-087-retry-fired", attachment_type=allure.attachment_type.TEXT,
        )
        # Процесс убит гонкой ActivityManager remove-task (AT-BUG-087),
        # подтверждено логкэтом -- Android сам не перезапускает; переотправляем
        # deep-link intent один раз (bounded -- исключение из этого вызова
        # пробрасывается наружу, если ретрай тоже не успел).
        open_deep_link(url)
        wait_tabs_persisted(sentinel, timeout=timeout)


def _parse_persisted_tabs(raw: str) -> list[dict]:
    """Извлекает и JSON-парсит массив TabSnapshot из `open_tabs_urls`
    (`BrowserViewModel.kt saveTabsToPrefs`/`TabSnapshot`). НЕ substring-подсчёт
    `"url":"` — эта подстрока встречается ДВАЖДЫ на вкладку: раз в самом
    `TabSnapshot.url`, раз в единственной записи её `historyEntries`
    (`HistoryEntry.url`, `HistoryEntry.kt`) — наивный substring-счёт переоценил
    бы число вкладок ровно в ~2 раза. Честный JSON-парсинг даёт точный список
    объектов — длина списка == число вкладок, `item["url"]` — url КОНКРЕТНОЙ
    вкладки (не её истории).

    Текстовое содержимое `<string>`-тега SharedPreferences эскейпит только
    `&`/`<`/`>` (не `"` — не значение атрибута), Gson-эскейп `=` -> `\\u003d`
    внутри JSON штатно раскрывается самим `json.loads` (см. `wait_tabs_persisted`
    за той же практикой, сверено на живом файле устройства при разведке
    TC-025). Отсутствующий ключ `open_tabs_urls` -> пустой список — валидный
    исход (файл ещё не создан/только что после `pm clear`, ИЛИ приложение
    ещё ни разу не вызывало `saveTabsToPrefs`), не ошибка парсинга.

    AT-BUG-055 (Fixed): `raw` сюда попадает ТОЛЬКО из честного
    `_read_tabs_prefs_raw()` — нечитаемый/отвалившийся ответ adb/run-as уже
    отфильтрован явным исключением НИЖЕ по стеку (`adb.run_as_file_or_raise`),
    сюда он не доходит. Раньше при НАЙДЕННОМ, но БИТОМ/обрезанном ключе
    `open_tabs_urls` (`json.loads` кидает `JSONDecodeError`) эта функция тоже
    молча возвращала `[]` — неотличимо от «вкладок реально нет». Это тоже
    часть класса «нечитаемый вход не должен становиться `[]`»: ключ
    ПРИСУТСТВУЕТ (значит, приложение его писало), но его нельзя разобрать —
    подозрение на повреждённый/обрезанный ответ транспорта, не на
    легитимное отсутствие вкладок, поэтому теперь явный `RuntimeError`."""
    m = re.search(r'name="open_tabs_urls"[^>]*>(.*?)</string>', raw, re.DOTALL)
    if not m:
        return []
    text = m.group(1)
    text = (
        text.replace("&lt;", "<").replace("&gt;", ">")
        .replace("&quot;", '"').replace("&apos;", "'")
        .replace("&#10;", "\n").replace("&amp;", "&")
    )
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise RuntimeError(
            "open_tabs_urls присутствует в prefs, но не распарсился как JSON "
            f"(AT-BUG-055) — похоже на обрезанный/повреждённый ответ "
            f"run-as, не на легитимное отсутствие вкладок. Сырой текст ключа: "
            f"{text!r}"
        ) from exc


@allure.step("Then в prefs open_tabs_urls зафиксировано РОВНО {expected_count} вкладок(и)")
def wait_persisted_tab_count(expected_count: int, timeout: int = 10) -> None:
    """TC-131: опрашивает (не читает один раз) точное число вкладок в
    `open_tabs_urls` — тот же класс debounce/apply()-гонки, что закрывает
    `wait_tabs_persisted`, только по ТОЧНОМУ счёту объектов (нужно доказать
    «11-я вкладка НЕ создана», не просто «сентинел где-то есть/нет»).

    Диагностика при таймауте обязана нести ФАКТИЧЕСКОЕ последнее прочитанное
    значение, а не None (AT-BUG-036: `message=` для `wait_for` — обычная
    строка, вычисляется в момент ВЫЗОВА, до первого опроса; f-строка,
    подставленная прямо в аргумент, замораживает `holder` пустым). Приём —
    как в `settings_steps.assert_filter_profile_count`: ждать в
    `try/except TimeoutError`, читать `holder["count"]` для сообщения ПОСЛЕ
    того, как опрос уже случился (ленивое вычисление).

    ВАЖНО (AT-BUG-036, attempt 2 — critic-фикс): `except TimeoutError: pass`
    глотал исходное исключение целиком — вместе с ним терялся контекст
    `wait_for` (`; last error: ...`), на который матчит зарегистрированный
    fail-fast-детектор среды (`TimeoutError`/`ReadTimeoutError` на одном
    шаге, класс AT-BUG-009: например зависший adb). Если `_check` не
    сделала НИ ОДНОГО успешного наблюдения (predicate падает на КАЖДОМ
    опросе — `holder` пуст), диагностировать «последнее наблюдение»
    нечего: исходный `TimeoutError` пробрасывается ЦЕЛИКОМ (сохраняет и
    тип исключения, и `; last error: ...`-контекст). Если хотя бы одно
    наблюдение было (predicate читала prefs успешно, просто счёт не
    совпал) — падение честное `AssertionError` с последним наблюдением;
    причина `wait_for` (если исключение всё же было поймано на каком-то
    из опросов) дописывается к сообщению отдельно, не теряется."""
    holder: dict[str, int] = {}
    wait_err: TimeoutError | None = None

    def _check() -> bool:
        holder["count"] = len(_parse_persisted_tabs(_read_tabs_prefs_raw()))
        return holder["count"] == expected_count

    try:
        wait_for(_check, timeout=timeout, message="число вкладок в open_tabs_urls не сошлось")
    except TimeoutError as exc:
        wait_err = exc
        if "count" not in holder:
            # Опрос НИ РАЗУ не смог прочитать/распарсить prefs (например,
            # adb завис — AT-BUG-009): наблюдения нет, диагностировать
            # нечего. Пробрасываем исходный TimeoutError целиком — тип
            # исключения и "; last error: ..."-контекст доходят до
            # fail-fast-детектора среды без искажения.
            raise
    assert holder.get("count") == expected_count, (
        f"число вкладок в open_tabs_urls не стало {expected_count} "
        f"(последнее наблюдение: {holder.get('count')})"
        + (f"; ожидание прервано: {wait_err}" if wait_err is not None else "")
    )


@allure.step("Then вхождений URL {marker_url} в open_tabs_urls: {expected_count}")
def assert_persisted_marker_count(
    marker_url: str, expected_count: int, expected_total: int | None = None,
) -> None:
    """Мгновенная сверка (не опрос) — вызывающий код обязан САМ гарантировать
    стабильность файла ДО вызова (напр. предшествующим `wait_persisted_tab_count`
    на этом же снимке состояния) — TC-131: точное число вкладок с данным url
    (0 — «URL безвозвратно потерян», не открыт ни в новой вкладке, ни поверх
    существующей).

    `expected_total`, если задан (critic-блокер B2, attempt 2): позитивный
    якорь источника — доказывает, что `_read_tabs_prefs_raw()` реально прочитал
    непустой/валидный prefs-файл, а не отдал вакуумный `[]` (`actual == 0 ==
    expected_count` прошло бы, не прочитав реального состояния устройства).
    AT-BUG-055 (Fixed): САМ вакуумный `[]` на нечитаемом/отвалившемся
    adb/run-as теперь закрыт у источника — `_read_tabs_prefs_raw`/
    `_parse_persisted_tabs` кидают `RuntimeError` вместо молчаливого `""`/`[]`
    (см. их докстринги), так что `expected_total` больше не единственная
    линия защиты от этого конкретного класса; остаётся как ДОПОЛНИТЕЛЬНЫЙ
    позитивный якорь целостности снимка (например, ловит рассинхрон ожиданий
    вызывающего кода, не только транспортный отказ). По умолчанию `None` не
    меняет поведение существующих вызовов."""
    tabs = _parse_persisted_tabs(_read_tabs_prefs_raw())
    if expected_total is not None:
        assert len(tabs) == expected_total, (
            f"общее число вкладок в open_tabs_urls: {len(tabs)}, ожидали "
            f"{expected_total} (пустое/битое чтение prefs-файла даёт вакуумный "
            f"ноль вхождений маркера — сигнал недостоверного снимка состояния)"
        )
    actual = sum(1 for t in tabs if t.get("url") == marker_url)
    assert actual == expected_count, (
        f"вхождений URL {marker_url!r} в open_tabs_urls: {actual} (всего вкладок "
        f"в prefs: {len(tabs)}), ожидали {expected_count}"
    )


@allure.step(
    "Then URL {marker_url} отсутствует в open_tabs_urls ВЕСЬ бюджет {budget_s}с "
    "(нет отложенной очереди открытия)"
)
def assert_persisted_marker_absent_for(
    marker_url: str, budget_s: float = 4.0, poll_interval: float = 0.5,
    expected_total: int | None = None,
) -> None:
    """TC-131, регрессионный замок находки 4 CH-005: держит негатив ВЕСЬ бюджет
    (`assert_holds_for`), а не одно чтение сразу после действия — доказывает
    отсутствие ИМЕННО отложенной очереди открытия (в коде её нет,
    `openOrNavigateDeepLink`/`openTab` вызываются только в момент самого
    intent'а), а не «эффект просто ещё не докатился до момента, когда мы
    посмотрели» (тот же класс, что `assert_top_chrome_not_darkened`/
    `assert_scroll_unchanged` в `browser_steps.py`).

    `expected_total`, если задан (critic-блокер B2, attempt 2): позитивный
    якорь источника на КАЖДОЙ итерации опроса — доказывает, что негатив
    «count==0» держится на реально прочитанном состоянии, не на вакуумном
    снимке. AT-BUG-055 (Fixed): отвалившийся device/`run-as` больше НЕ
    отдаёт молчаливый `""`/`[]` — `_read_tabs_prefs_raw`/`_parse_persisted_tabs`
    кидают `RuntimeError`, который здесь прокинется из `_check()` и прервёт
    `assert_holds_for` немедленно (не «держит негатив» на отказавшем
    транспорте); `expected_total` остаётся дополнительным семантическим
    якорем поверх этого."""
    def _check() -> bool:
        tabs = _parse_persisted_tabs(_read_tabs_prefs_raw())
        if expected_total is not None:
            assert len(tabs) == expected_total, (
                f"общее число вкладок в open_tabs_urls: {len(tabs)}, ожидали "
                f"{expected_total} (пустое/битое чтение prefs-файла даёт "
                f"вакуумный негатив — сигнал недостоверного снимка состояния)"
            )
        count = sum(1 for t in tabs if t.get("url") == marker_url)
        assert count == 0, (
            f"URL {marker_url!r} появился в open_tabs_urls ({count} вхожд. из "
            f"{len(tabs)} вкладок) — похоже на отложенную очередь открытия, "
            f"которой не должно быть"
        )
        return True

    assert_holds_for(
        _check, budget_s=budget_s, interval_s=poll_interval,
        msg=f"URL {marker_url!r} появился в open_tabs_urls в пределах {budget_s}s бюджета",
    )


@allure.step("Then вкладка на позиции {position} в open_tabs_urls несёт URL {expected_url}")
def assert_persisted_tab_url_at(position: int, expected_url: str) -> None:
    """TC-132: адресная сверка URL КОНКРЕТНОЙ позиции в open_tabs_urls — в
    отличие от `assert_persisted_marker_count` (только счёт вхождений маркера
    по всему списку), нужна доказать (а) вкладка 0 (бывшая единственная)
    сохранила ИМЕННО прежнее содержимое без изменений, (б) вкладка на позиции 1
    (новая) несёт ИМЕННО URL deep-link'а — а не просто «где-то в списке
    появился URL». Порядок списка `TabSnapshot` соответствует порядку
    `state.tabs` (`BrowserViewModel.kt saveTabsToPrefs`: `state.tabs.map { ... }`,
    без сортировки/дедупликации) — позиция в JSON-массиве == позиция вкладки."""
    tabs = _parse_persisted_tabs(_read_tabs_prefs_raw())
    assert 0 <= position < len(tabs), (
        f"позиция {position} вне диапазона: всего вкладок в prefs {len(tabs)}"
    )
    actual = tabs[position].get("url")
    assert actual == expected_url, (
        f"URL вкладки на позиции {position}: {actual!r}, ожидали {expected_url!r}"
    )


@allure.step("Then вкладка на позиции {position} в open_tabs_urls становится {expected_url} (с поллингом)")
def wait_persisted_tab_url_at(position: int, expected_url: str, timeout: int = 10) -> None:
    """AT-BUG-070 rework (критик round1, блокер B1): опрашивающий вариант
    `assert_persisted_tab_url_at` — нужен, когда URL на позиции меняется
    ДЕЙСТВИЕМ, чей эффект на prefs асинхронен (`SharedPreferences.apply()`,
    тот же класс debounce/apply()-гонки, что закрывает `wait_persisted_tab_count`
    выше), а не сидингом/предшествующим `wait_persisted_tab_count`, который уже
    гарантировал стабильность снимка. Одиночное чтение сразу после действия
    рискует застать ЕЩЁ не осевшую запись (гонка, не факт «URL не поменялся»).

    Диагностика при таймауте несёт ФАКТИЧЕСКОЕ последнее прочитанное значение
    (тот же приём `holder`/ленивого сообщения, что `wait_persisted_tab_count`,
    AT-BUG-036) — не просто «не совпало»."""
    holder: dict[str, object] = {}
    wait_err: TimeoutError | None = None

    def _check() -> bool:
        tabs = _parse_persisted_tabs(_read_tabs_prefs_raw())
        assert 0 <= position < len(tabs), (
            f"позиция {position} вне диапазона: всего вкладок в prefs {len(tabs)}"
        )
        holder["url"] = tabs[position].get("url")
        return holder["url"] == expected_url

    try:
        wait_for(_check, timeout=timeout, message=f"URL вкладки на позиции {position} не стал {expected_url!r}")
    except TimeoutError as exc:
        wait_err = exc
        if "url" not in holder:
            raise
    assert holder.get("url") == expected_url, (
        f"URL вкладки на позиции {position} не стал {expected_url!r} "
        f"(последнее наблюдение: {holder.get('url')!r})"
        + (f"; ожидание прервано: {wait_err}" if wait_err is not None else "")
    )


def _read_persisted_active_tab_index() -> int | None:
    """Читает `active_tab_index` — int-preference, записываемый ТЕМ ЖЕ
    `apply()`, что и `open_tabs_urls` (`saveTabsToPrefs`, BrowserViewModel.kt:
    372-375) — атомарно консистентен со списком вкладок на момент чтения."""
    raw = _read_tabs_prefs_raw()
    m = re.search(r'name="active_tab_index"\s+value="(-?\d+)"', raw)
    return int(m.group(1)) if m else None


@allure.step("Then активная вкладка в prefs (active_tab_index) — позиция {expected_position}")
def assert_persisted_active_tab_index(expected_position: int) -> None:
    """TC-132: доказывает, КАКАЯ вкладка активна, БЕЗ похода в WEBVIEW-контекст.
    Прямое чтение `current_url` для НЕ-нулевой активной вкладки ненадёжно:
    chromedriver прилипает к вкладке-0 при >1 живой WebView (см. модульный
    докстринг `test_tabs.py`), а свести число вкладок к одной (reduce-to-one,
    `swipe_close_tab`) здесь разрушило бы вкладку 0, которую этот же кейс (TC-132)
    обязан проверить как НЕТРОНУТУЮ. `active_tab_index` — то же самое
    `apply()`-событие, что и `open_tabs_urls` (см. `_read_persisted_active_tab_index`),
    поэтому не подвержен гонке отдельного чтения."""
    actual = _read_persisted_active_tab_index()
    assert actual == expected_position, (
        f"active_tab_index в prefs: {actual}, ожидали {expected_position}"
    )


@allure.step("When приложение принудительно остановлено (adb) и запущено заново")
def restart_app_via_adb(driver) -> None:
    """`am force-stop` + `am start -W` — РЕАЛЬНАЯ смерть процесса (не
    `driver.terminate_app`/`activate_app`, см. `restart_app` выше — тот использует
    Appium API, здесь нужен именно `core/adb`, единообразно с остальным фреймворком,
    см. заметки TC-025.md), проверяет персистентность через SharedPreferences, а не
    просто пересоздание Activity в живом процессе."""
    adb.force_stop()
    adb.shell(
        f"am start -W -n {settings.APP_PACKAGE}/{settings.APP_ACTIVITY}",
        timeout=settings.ADB_LAUNCH_TIMEOUT,
    )


@allure.step("When приложение убито и перезапущено — смена pid процесса доказана")
def restart_app_via_adb_asserting_new_process(driver) -> None:
    """TC-134 (critic-блокер B1, attempt 2): `restart_app_via_adb` сам по себе
    ничего не наблюдает — `adb.shell` отбрасывает returncode (см. докстринг
    `assert_persisted_marker_count`), поэтому тихий отказ `force_stop`
    (device busy/permission/отвал adb) неотличим от штатного kill+relaunch:
    `am start -W` без `-d`, посланный уже ЖИВОМУ `singleTask`-процессу, просто
    доставляет пустой intent через `onNewIntent` (см. докстринг
    `bring_app_to_foreground_without_deep_link`) — `dataString` пуст что при
    реальной смерти, что при несработавшем force-stop, поэтому все Then этого
    теста читают неизменившееся состояние ОБОИХ путей одинаково зелёным, не
    различив их. Обратная проверка к TC-133 `assert_app_pid_unchanged`
    (та доказывает «pid НЕ изменился» — процесс пережил переход; здесь
    наоборот доказывается, что процесс РЕАЛЬНО умер и пересоздался, семантика
    противоположная, поэтому переиспользование того ассерта было бы
    некорректным).

    AT-BUG-032 (test_debt, Fixed): та же дыра существовала у ДВУХ более старых
    вызывающих `restart_app_via_adb` напрямую — `test_tabs.py` TC-025
    (`test_tabs_persist_url_and_scroll_after_restart`) и `test_reading_ux.py`
    TC-125 (`test_tap_to_scroll_survives_kill_and_relaunch`) — оба переведены на
    ЭТУ обёртку единой точкой в `app_steps.py` (не разбросано по вызывающим
    тестам поодиночке), чтобы класс не повторился в следующем новом тесте на
    том же примитиве. `restart_app_via_adb` сам по себе НЕ удалён; единственный
    оставшийся вызывающий — `test_compatibility.py:129` — НЕ переведён в рамках
    этого бага (вне заявленного скоупа DoD — TC-025/TC-125), но здесь честно:
    это НЕ структурная гарантия смерти процесса. Между `clean_state()` (:123) и
    этим вызовом (:129) идёт `seed_with_comment()` (:124) →
    `seed_db.ensure_db_initialized` (`framework/data/seed_db.py:50-65`),
    который САМ делает `am start -W` (:54-57) и ЕЩЁ ОДИН `adb.force_stop()`
    (:64 и :65) — тем же неконтролируемым returncode-отбрасывающим примитивом,
    что и здесь. На момент вызова `restart_app_via_adb` в `test_compatibility.py`
    мёртвость процесса структурно НИЧЕМ не гарантирована («`pm clear` сам
    убивает процесс» — неверно: между `pm clear` и этой строкой процесс успевает
    ожить внутри seed-пайплайна); `restart_app_via_adb` здесь фактически
    используется как простой старт, а не как проверенный kill+relaunch. Класс
    того же долга применительно к этому вызывающему — в очереди, см. AT-BUG-032.md
    (заметки F3/F4), решение о диспетчеризации за Lead.
    `perf_steps.measure_cold_start` (TC-096) сюда не относится вовсе — эта
    функция НЕ вызывает `restart_app_via_adb`: у неё независимый путь
    (`force_stop()` + `clear_app_data()` + `am start -W`, `perf_steps.py:33-38`)
    со своей структурной защитой через `clear_app_data()`, которая ПРОВЕРЯЕТ
    returncode и кидает `RuntimeError` при отказе (`adb.py:75-81`) — не через
    `parse_am_start_metrics` (та лишь парсит `TotalTime` из вывода и падает
    только при отсутствии самого поля; тёплый no-op старт по докстрингу
    `adb.py:296-303` даёт `TotalTime: 0`, что парсится штатно и тёплый старт не
    ловит)."""
    pid_before = adb.pidof_app()
    assert pid_before is not None, "процесс не найден ДО force-stop — убивать нечего"
    restart_app_via_adb(driver)
    pid_after = adb.pidof_app()
    assert pid_after is not None, "процесс не поднялся после am start -W"
    assert pid_after != pid_before, (
        f"pid не изменился ({pid_before}) — am force-stop процесс НЕ убил "
        "(adb.shell отбрасывает returncode), релонч свёлся к доставке intent'а в "
        "ЖИВОЙ процесс: холодный старт не состоялся"
    )
