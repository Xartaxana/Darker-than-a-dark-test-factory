"""Бизнес-шаги уровня приложения: установка состояния, запуск, навигация.
Единственный слой, где допустим allure.step (Given/When/Then). Без локаторов —
только композиция экранов и core.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import allure
from appium.webdriver.common.appiumby import AppiumBy

from framework.config import settings
from framework.core import adb
from framework.core.waits import wait_for, wait_until
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


@allure.step("Given в библиотеку засеяны записи с опциональными rating/comment/tags")
def seed_with_comment(rows: list[tuple[Work, str | None, str | None, str | None]]):
    seed_db.seed_with_comment(rows)


@allure.step("Given засеян(ы) filter-профиль(и): {profiles}")
def seed_filter_profiles(profiles: list[tuple[str, str]]):
    """profiles: список (name, queryString) — сохранённые фильтр-поиски
    (TC-021 round-trip filterProfiles; TC-041/TC-042)."""
    seed_db.seed_filter_profiles(profiles)


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


@allure.step("Then вкладки сохранены в SharedPreferences (сентинел «{sentinel}» найден)")
def wait_tabs_persisted(sentinel: str, timeout: int = 10) -> None:
    """Опрашивает файл SharedPreferences приложения (`ao3_settings.xml`, через
    `run-as cat` — тот же приём, что `pull_app_file`), пока в нём не появится
    `sentinel` — TC-025: `saveTabsToPrefs` (BrowserViewModel.kt `scheduleSave`)
    ДЕБАУНСИТ запись на 500мс после каждого скролл-события; принудительная
    остановка процесса (`am force-stop`) ДО истечения этого окна теряет
    несохранённое состояние безвозвратно (отменённая корутина никогда не
    допишет файл) — одноразовое чтение/фиксированная пауза было бы гонкой с этим
    дебаунсом, поэтому здесь именно опрос РЕАЛЬНОГО файла на диске, а не UI."""
    path = f"/data/data/{settings.APP_PACKAGE}/shared_prefs/ao3_settings.xml"

    def _check() -> bool:
        return sentinel in adb.run_as(f"cat {path}")

    wait_for(_check, timeout=timeout,
             message=f"вкладки с сентинелом {sentinel!r} не появились в {path}")


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
