"""Бизнес-шаги системного SAF picker (DocumentsUI) — инфраструктура AT-BUG-005,
инкремент 1 (B4, `bugs/AT-BUG-005.md`). Доводит экспорт/импорт/выбор-папки до
конца сценария через тот же UiAutomator2-сеанс, что и остальное приложение
(см. `framework/screens/documents_ui.py` — DocumentsUI работает в том же
пакете `com.android.documentsui` на всех трёх поверхностях, переключения
пакета на стороне Appium не требуется).

ВАЖНО: это НЕ автоматизация TC-021 целиком — только шаги, доводящие пикер до
конца (SettingsScreen.kt: `CreateDocument` :617, `GetContent` :613,
`OpenDocumentTree` :597). Полная сборка TC-021 — задача test-automator после
снятия блокера (см. «Критерий готовности» в AT-BUG-005.md).

Детерминизм (spec AT-BUG-005, п.4-5):
- Файлы/каталоги, которые пикер должен УВИДЕТЬ, готовятся заранее adb-шеллом
  (см. `framework/tests/test_saf_infra_probe.py::saf_probe_workspace`), не
  создаются кликами внутри самого пикера (кроме результата CreateDocument —
  это и есть проверяемое поведение).
- Стартовый каталог DocumentsUI недетерминирован (последний каталог,
  использованный ЭТИМ вызывающим пакетом, независимо от контракта) — каждый
  шаг ниже ЯВНО выбирает root перед навигацией: `DocumentsUIScreen.open_root`
  (drawer, стабильный AOSP-лейбл "Downloads") для CreateDocument/GetContent;
  `DocumentsUIScreen.reset_to_root` (клик по первому сегменту breadcrumb'а —
  drawer недоступен на single-root устройстве, сверено на живом дереве) для
  OpenDocumentTree.
- `pm clear <pkg>` (`framework.core.adb.clear_app_data()`, уже используется в
  фикстуре `clean_app`) ПОДТВЕРЖДЕНО сбрасывает persisted URI permission grant
  на стороне ОС: `adb shell dumpsys activity permissions` показывал
  `UriPermission{... tree/primary:Download/ao3_saf_probe ...}` ДО `pm clear` и
  пустой блок «ACTIVITY MANAGER URI PERMISSIONS ... (nothing)» сразу после
  (проверено вручную 2026-07-09 на emulator-5554). Поэтому teardown НЕ должен
  отдельно отзывать грант (`revokeUriPermission` и т.п.) — только удалять
  файлы/каталоги на `/sdcard`, которые сам создал; ОС сама забывает грант при
  следующем `pm clear` (который и так вызывается `clean_app` в начале
  следующего теста).
- OpenDocumentTree: САМ каталог "Download" (и другие стандартные top-level
  директории — DCIM/Pictures/...) выбрать НЕЛЬЗЯ — системная защита
  приватности блокирует кнопку USE THIS FOLDER («Can't use this folder, to
  protect your privacy, choose another folder», сверено на живом дереве);
  нужна ВЛОЖЕННАЯ подпапка (см. `subpath` ниже).
"""
from __future__ import annotations

import allure

from framework.screens.base_screen import BaseScreen
from framework.screens.documents_ui import DocumentsUIScreen
from framework.screens.navigation import BottomNav
from framework.screens.settings_screen import SettingsScreen
from framework.steps import app_steps

DOWNLOADS_ROOT = "Downloads"


@allure.step("Given открыт Settings, докручено до «{text}»")
def open_settings_scrolled_to(driver, text: str) -> None:
    """Общая подготовка для всех трёх проб (docs/08 C1 — locator/driver-примитивы
    скрыты за steps/screens, тесты вызывают только это): нативная оболочка готова
    (AO3 грузить не нужно — сценарии этого модуля целиком в Settings/DocumentsUI),
    открыт Settings, докручено до кнопки, за которой сразу последует SAF-контракт.

    Пробует ОБА направления (`swipe_to_text` вниз, затем `swipe_up_to_text` вверх)
    — для проб AT-BUG-005 (всегда стартующих сверху свежеоткрытого Settings)
    первого достаточно и второе не вызывается; TC-021 нужен и обратный ход:
    после «Clear all ratings» (Compose-диалог, скролл НЕ сбрасывается, в отличие
    от возврата из внешней DocumentsUI Activity) текущая позиция ниже «Restore»,
    и назад к нему можно вернуться только вверх."""
    app_steps.wait_ui_ready(driver)
    BottomNav(driver).go_settings()
    ss = SettingsScreen(driver)
    assert ss.is_loaded(), "экран Settings не отрисовался"
    _scroll_settings_to(driver, text)


def _scroll_settings_to(driver, text: str) -> None:
    """Докручивает УЖЕ открытый Settings до `text`, пробуя оба направления. Без
    собственной проверки `is_loaded()` (заголовок "Theme" — самая ВЕРХНЯЯ секция
    экрана): если текущая позиция проскроллена вниз (TC-021 — повторный заход
    после «Clear all ratings»), "Theme" временно не в дереве (см. заметки
    Compose-дискуссии AT-BUG-005 про `verticalScroll`) — это не значит, что экран
    не Settings, только что мы не наверху. Проверку «мы вообще на Settings»
    делают вызывающие (`open_settings_scrolled_to` — по свежему открытию;
    `rescroll_settings_to` полагается на уже пройденную ранее в этой сессии)."""
    ss = SettingsScreen(driver)
    found = ss.swipe_to_text(text) or ss.swipe_up_to_text(text)
    assert found, f"не удалось проскроллить до «{text}» (ни вниз, ни вверх)"


@allure.step("Given экран Settings снова докручен до «{text}» (повторный заход в той же сессии)")
def rescroll_settings_to(driver, text: str) -> None:
    """Как `open_settings_scrolled_to`, но БЕЗ `app_steps.wait_ui_ready` (проверка
    наличия `android.webkit.WebView`) и без `SettingsScreen.is_loaded()`
    (заголовок "Theme" наверху экрана — не найдётся, пока мы проскроллены вниз):
    обе проверки валидны только сразу после холодного открытия Settings, не при
    повторном заходе в той же сессии. `wait_ui_ready` вдобавок конкретно ищет
    `android.webkit.WebView`, которого нет в дереве на вкладках Library/Settings
    (см. `framework/screens/navigation.py` — WebView существует только на
    Browse), поэтому его повторный вызов гарантированно таймаутит. TC-021:
    между Clear all ratings и Restore нужно вернуться на Settings и докрутиться
    заново без обеих проверок «свежего» открытия — только `go_settings`
    (идемпотентен) и скролл."""
    BottomNav(driver).go_settings()
    _scroll_settings_to(driver, text)


@allure.step("Then лейбл Download folder показывает «{label}»")
def assert_download_folder_label(driver, label: str) -> None:
    """DocumentFile.fromTreeUri(...).name, SettingsScreen.kt:889 — подтверждает, что
    persisted URI-грант реально применился, не только факт закрытия picker'а.

    Возврат из внешней Activity (DocumentsUI) сбрасывает scroll-позицию Settings на
    верх экрана (сверено на живом дереве/скриншоте — после ALLOW список снова
    показывает "CONTENT VISIBILITY" сверху) — поэтому докручиваем заново
    (`swipe_to_text`), а не полагаемся на то, что секция уже видна."""
    ss = SettingsScreen(driver)
    assert ss.swipe_to_text(label), f"лейбл Download folder не обновился на «{label}»"


def tap_settings_action(driver, label: str) -> None:
    """Тап по кнопке экрана Settings, запускающей SAF-контракт приложения (`label` —
    видимый текст: "Back up" -> CreateDocument, "Restore" -> GetContent, "Pick" ->
    OpenDocumentTree). Все три — точное совпадение текста (UiSelector.text() матчит
    точно, не подстрокой), коллизий с соседними заголовками ("Back up data"/"Restore
    from backup") нет. Тонкая обёртка вместо нового локатора в settings_screen.py —
    единственные три точки входа, нужные SAF-инфраструктуре инкремента 1 на чужом
    (Settings) экране; не расширяет владение файлами за пределы AT-BUG-005."""
    b = BaseScreen(driver)
    b.tap(b.by_text(label))


def _dismiss_ok_dialog(driver, before_dismiss=None) -> None:
    """Закрывает собственный (не DocumentsUI) диалог-результат приложения («Backup
    created» / «Backup restored», SettingsScreen.kt ExportState.Done/ImportState.Done) —
    общий "OK" на обоих, поэтому не заводим для этого отдельный локатор в
    settings_screen.py (эти диалоги не имеют других общих полей с остальным экраном
    Settings, локатор сугубо для завершения SAF-раунд-трипа).

    `before_dismiss(driver)`, если передан, вызывается ПОСЛЕ появления диалога, но ДО
    тапа по OK — окно для проверки его содержимого (заголовок/текст с counts), нужное
    TC-021 (`framework/steps/backup_steps.py`): сама эта функция знает только про общую
    кнопку "OK", а не про конкретный текст результата."""
    b = BaseScreen(driver)
    if b.is_present(b.by_text("OK"), timeout=10):
        if before_dismiss is not None:
            before_dismiss(driver)
        b.tap(b.by_text("OK"))


@allure.step("When в системном пикере подтверждено сохранение файла ({filename})")
def saf_save_document(driver, filename: str | None = None, before_dismiss=None) -> None:
    """CreateDocument-диалог: явный root Downloads, (опционально) переименование,
    SAVE, закрытие диалога-результата приложения. `filename=None` — оставить имя,
    предложенное приложением (`ao3_backup_$date.json`, SettingsScreen.kt:958-959).
    `before_dismiss` — см. `_dismiss_ok_dialog`."""
    s = DocumentsUIScreen(driver)
    assert s.is_loaded(), "CreateDocument picker не открылся (нет toolbar DocumentsUI)"
    s.open_root(DOWNLOADS_ROOT)
    if filename is not None:
        s.set_filename(filename)
    s.tap_save()
    _dismiss_ok_dialog(driver, before_dismiss)


@allure.step("When в системном пикере выбран файл {display_name}")
def saf_pick_file(driver, display_name: str, before_dismiss=None) -> None:
    """GetContent-браузер: явный root Downloads, тап по файлу с именем display_name,
    закрытие диалога-результата приложения. `before_dismiss` — см. `_dismiss_ok_dialog`."""
    s = DocumentsUIScreen(driver)
    assert s.is_loaded(), "GetContent picker не открылся (нет toolbar DocumentsUI)"
    s.open_root(DOWNLOADS_ROOT)
    s.tap_file(display_name)
    _dismiss_ok_dialog(driver, before_dismiss)


@allure.step("When в системном пикере выбрана папка {subpath} и подтверждён доступ")
def saf_pick_folder(driver, subpath: str) -> None:
    """OpenDocumentTree: сброс к истинному root'у (`reset_to_root` — drawer недоступен
    на single-root устройстве), навигация по `subpath` (например "Download/at_bug_005_saf_probe" —
    сегменты через "/", каждый — видимое имя папки на текущем экране), USE THIS FOLDER,
    подтверждение системного ALLOW. `subpath` обязан вести во ВЛОЖЕННУЮ папку — сам
    "Download" системная защита приватности не даёт выбрать (см. докстринг модуля)."""
    s = DocumentsUIScreen(driver)
    assert s.is_loaded(), "OpenDocumentTree picker не открылся (нет toolbar DocumentsUI)"
    s.reset_to_root()
    for part in subpath.split("/"):
        s.open_folder(part)
    assert s.use_this_folder_enabled(), (
        f"USE THIS FOLDER выключена для '{subpath}' — вероятно, это защищённый системой "
        "top-level каталог (Download/DCIM/... сам по себе нельзя выбрать), нужна вложенная подпапка"
    )
    s.tap_use_this_folder()
    s.tap_allow()
