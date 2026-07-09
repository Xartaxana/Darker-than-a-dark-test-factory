"""Page object системного Storage Access Framework picker (DocumentsUI,
package `com.android.documentsui`, AOSP API 34) — используется app'ом для
backup/restore/download-folder (`SettingsScreen.kt`: `CreateDocument` :617,
`GetContent` :613, `OpenDocumentTree` :597). DocumentsUI — чужой (системный)
код, поэтому «место рендера» в репозитории отсутствует по определению
(AT-BUG-005, «Локаторная дисциплина»): локаторы выведены из живого дерева
(`python scripts/ui_snapshot.py` на открытом пикере, emulator-5554,
2026-07-09) — все по `resource-id` (`com.android.documentsui:id/*` /
`android:id/*`), НЕ по координатам/индексам, за одним документированным
исключением ниже (`_root_breadcrumb_segment`).

Одна WHY-заметка на три поверхности: все три ActivityResultContracts
открывают Activity одного и того же пакета `com.android.documentsui`
(включая системный confirm-диалог «Allow ... to access files in ...?» —
это тоже `com.android.documentsui`, НЕ отдельный PermissionController) —
один и тот же UiAutomator2-сеанс видит все три поверхности без переключения
контекста/пакета на стороне Appium.

Три поверхности:
  (а) CreateDocument — диалог сохранения (переименование + SAVE);
  (б) GetContent — браузер файлов (выбор существующего файла по имени);
  (в) OpenDocumentTree — выбор папки (навигация + USE THIS FOLDER + ALLOW).
"""
from __future__ import annotations

from appium.webdriver.common.appiumby import AppiumBy

from framework.screens.base_screen import BaseScreen

_PKG = "com.android.documentsui"


class DocumentsUIScreen(BaseScreen):
    # --- Общие локаторы/операции для всех трёх поверхностей ---
    _SHOW_ROOTS = (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().description("Show roots")')

    def by_id(self, resource_id: str):
        return (AppiumBy.ANDROID_UIAUTOMATOR, f'new UiSelector().resourceId("{resource_id}")')

    def _root_item(self, label: str):
        """Пункт списка root'ов в drawer'е «Save to»/«Open from» — TextView
        `android:id/title` внутри LinearLayout, клик на котором не срабатывает (сам текст
        не clickable в дереве); кликабелен родитель на два уровня выше (сверено на живом
        дереве roots_drawer.xml: title -> LinearLayout(non-click) -> LinearLayout(click))."""
        return (AppiumBy.XPATH,
                f'//*[@resource-id="android:id/title" and @class="android.widget.TextView" '
                f'and @text="{label}"]/../..')

    def open_root(self, label: str):
        """Явно открывает drawer root'ов и выбирает root по подписи (стабильный AOSP-лейбл,
        например "Downloads" — НЕ имя хоста устройства). Обязательный первый шаг перед
        навигацией: стартовый каталог DocumentsUI недетерминирован (последний
        использованный вызывающим пакетом), см. докстринг `framework/steps/saf_steps.py`.
        Drawer доступен только когда в системе больше одного root'а (CreateDocument/
        GetContent на этом стенде) — если кнопки нет, шаг no-op (`is_present` с коротким
        таймаутом, а не исключение)."""
        if self.is_present(self._SHOW_ROOTS, timeout=3):
            self.tap(self._SHOW_ROOTS)
            self.tap(self._root_item(label))
        return self

    def _root_breadcrumb_segment(self):
        """ЕДИНСТВЕННОЕ позиционное (не по resource-id-значению) исключение в этом файле:
        первый (левый) сегмент breadcrumb'а — всегда истинный root навигации, независимо от
        текущей глубины. Обоснование: у OpenDocumentTree на single-root устройстве drawer
        (`_SHOW_ROOTS`) отсутствует вовсе (сверено на живом дереве — нет ни одного
        ImageButton в этой поверхности), а текст самого root'а — имя устройства/AVD
        ("Android SDK built for x86_64" на emulator-5554) — недетерминирован и НЕ то же
        самое на другом хосте/эмуляторе, поэтому матчить по тексту сюда нельзя. `instance(0)`
        здесь — не индекс в произвольном списке, а обращение к семантически определённому
        первому элементу горизонтального breadcrumb'а (тот же паттерн обоснованной позиции,
        что и `BottomNav._find_pill`/`BrowserScreen.close_leftmost_tab` в этом репозитории).
        Узел в дампе несёт `clickable="false"`, но это НЕ блокирует тап и не мешает
        навигации. Со стороны фреймворка: `BaseScreen.tap` ждёт
        `EC.element_to_be_clickable`, а это условие Selenium проверяет
        `is_displayed()`/`is_enabled()` элемента — атрибут accessibility-дерева
        `clickable` вообще не читает, поэтому `wait_until` не блокируется его
        значением. Со стороны Android: сам тап — это координатный touch-event, а не
        обращение к `View.isClickable()`; RecyclerView-строки этого экрана обрабатывают
        клик через слушатель на itemView (`OnItemClickListener`-паттерн), который
        реагирует на touch независимо от того, что UiAutomator показал в атрибуте
        `clickable` (эмпирически подтверждено на живом дереве — тап навигирует)."""
        return (AppiumBy.ANDROID_UIAUTOMATOR,
                f'new UiSelector().resourceId("{_PKG}:id/breadcrumb_text").instance(0)')

    def reset_to_root(self):
        """Сбрасывает навигацию к истинному root'у, когда drawer (`open_root`) недоступен
        (OpenDocumentTree). Идемпотентно — если уже на root'е, клик по первому сегменту
        breadcrumb'а не ломает состояние (сверено на живом дереве)."""
        self.tap(self._root_breadcrumb_segment())
        return self

    def open_folder(self, name: str):
        """Заходит в подпапку по видимому имени (GridView-элемент DocumentsUI — общий
        паттерн и для файлового браузера, и для folder-tree OpenDocumentTree)."""
        self.tap(self.by_text(name))
        return self

    # --- (а) CreateDocument: диалог сохранения ---
    _FILENAME_FIELD = (AppiumBy.ANDROID_UIAUTOMATOR,
                        'new UiSelector().resourceId("android:id/title")'
                        '.className("android.widget.EditText")')
    _SAVE_BUTTON = (AppiumBy.ANDROID_UIAUTOMATOR,
                    'new UiSelector().resourceId("android:id/button1").text("SAVE")')

    def set_filename(self, filename: str):
        field = self.find(self._FILENAME_FIELD)
        field.clear()
        field.send_keys(filename)
        return self

    def tap_save(self):
        self.tap(self._SAVE_BUTTON)
        return self

    # --- (б) GetContent: браузер файлов ---
    def file_item(self, display_name: str):
        """Кликабельный CardView (`item_root`), СОДЕРЖАЩИЙ TextView с именем файла — сам
        TextView (`android:id/title`) не кликабелен (сверено на живом дереве:
        item_root clickable=true, вложенный title clickable=false), клик должен идти по
        CardView-предку. XPath с предикатом-потомком (`ancestor` без named XPath-оси в
        UiAutomator2-драйвере надёжнее описать так) — не индекс и не координаты, ищет по
        combination resource-id (стабильный across версий DocumentsUI) + видимому тексту."""
        return (AppiumBy.XPATH,
                f'//*[@resource-id="{_PKG}:id/item_root"][.//*[@text="{display_name}"]]')

    def tap_file(self, display_name: str):
        self.tap(self.file_item(display_name))
        return self

    # --- (в) OpenDocumentTree: выбор папки ---
    _USE_THIS_FOLDER = (AppiumBy.ANDROID_UIAUTOMATOR,
                         'new UiSelector().resourceId("android:id/button1")'
                         '.textStartsWith("USE THIS FOLDER")')
    _ALLOW_BUTTON = (AppiumBy.ANDROID_UIAUTOMATOR,
                     'new UiSelector().resourceId("android:id/button1").text("ALLOW")')

    def use_this_folder_enabled(self) -> bool:
        """Читает enabled-атрибут кнопки USE THIS FOLDER — на защищённых системой
        каталогах (root тома, стандартные top-level папки вроде Download/DCIM/Pictures —
        экран показывает «Can't use this folder», см. `saf_steps.py`) кнопка выключена."""
        return self.is_enabled(self._USE_THIS_FOLDER)

    def tap_use_this_folder(self):
        self.tap(self._USE_THIS_FOLDER)
        return self

    def tap_allow(self):
        """Подтверждает системный AlertDialog «Allow <app> to access files in <folder>?»
        (рендерится тем же пакетом `com.android.documentsui`, см. докстринг класса)."""
        self.tap(self._ALLOW_BUTTON)
        return self

    def is_loaded(self) -> bool:
        """Признак того, что мы вообще находимся в DocumentsUI (любая из трёх
        поверхностей) — общий toolbar-контейнер присутствует на всех трёх."""
        return self.is_present(self.by_id(f"{_PKG}:id/toolbar"), timeout=10)
