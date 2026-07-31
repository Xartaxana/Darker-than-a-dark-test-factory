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


_TABS_PREFS_PATH = f"/data/data/{settings.APP_PACKAGE}/shared_prefs/ao3_settings.xml"


def _read_tabs_prefs_raw() -> str:
    """Сырой XML SharedPreferences приложения (`run-as cat`) — та же цель файла,
    что `wait_tabs_persisted`, вынесена отдельно для повторного использования
    парсерами ниже (TC-131: нужен точный СЧЁТ вкладок/вхождений, не просто
    присутствие сентинела)."""
    return adb.run_as(f"cat {_TABS_PREFS_PATH}")


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
    TC-025). Пустой список — валидный исход (файл ещё не создан/только что
    после `pm clear`), не ошибка парсинга."""
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
    except (json.JSONDecodeError, TypeError):
        return []


@allure.step("Then в prefs open_tabs_urls зафиксировано РОВНО {expected_count} вкладок(и)")
def wait_persisted_tab_count(expected_count: int, timeout: int = 10) -> None:
    """TC-131: опрашивает (не читает один раз) точное число вкладок в
    `open_tabs_urls` — тот же класс debounce/apply()-гонки, что закрывает
    `wait_tabs_persisted`, только по ТОЧНОМУ счёту объектов (нужно доказать
    «11-я вкладка НЕ создана», не просто «сентинел где-то есть/нет»)."""
    holder: dict[str, int] = {}

    def _check() -> bool:
        holder["count"] = len(_parse_persisted_tabs(_read_tabs_prefs_raw()))
        return holder["count"] == expected_count

    wait_for(
        _check, timeout=timeout,
        message=(
            f"число вкладок в open_tabs_urls не стало {expected_count} "
            f"(последнее наблюдение: {holder.get('count')})"
        ),
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
    непустой/валидный prefs-файл, а не отдал `""`/битый JSON (`adb.shell`
    отбрасывает returncode/stderr, `_parse_persisted_tabs` на пустом/битом
    чтении молча возвращает `[]`, из-за чего `actual == 0 == expected_count`
    прошёл бы ВАКУУМНО, не прочитав реального состояния устройства). По
    умолчанию `None` не меняет поведение существующих вызовов."""
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
    якорь источника на КАЖДОЙ итерации опроса — без него `adb.shell` (по
    отвалившемуся device/отказавшему `run-as`) молча отдаёт `""`, парсер на
    пустом/битом чтении возвращает `[]`, и негатив «count==0» держится весь
    бюджет, не прочитав ни одного реального состояния устройства."""
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
