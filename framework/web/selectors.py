"""DOM-селекторы AO3, зеркалящие контракт из app assets/ao3_bridge.js.
СОБРАНЫ В ОДНОМ МЕСТЕ намеренно: когда AO3 меняет разметку, чинится только этот файл,
а canary-suite (tests/canary) первым ловит расхождение.

Проверенные паттерны (PROJECT.md §Fragility note):
  - работа-блёрб: li[id^="work_"].work.blurb
  - заголовок: h4.heading a (первый);  автор: h4.heading a[rel=author]
  - счётчик слов: .stats .words
  - теги: ul.tags.commas a.relationship|character|warning|freeform
Инжектированные приложением элементы (bridge):
  - Rate-кнопка: 28px-кружок в правом верхнем углу блёрба
  - бейдж рейтинга и Note-кнопка
"""

# AO3 native
# Заголовок h1 присутствует и на живых страницах AO3, и на промежуточной странице
# Cloudflare-проверки (R-03) — используется как стабильный элемент для
# ОТНОСИТЕЛЬНОГО измерения размера текста (textZoom/fontSizeStep, TC-051/052/053:
# WebView масштабирует рендеринг текста, это не выражается через getComputedStyle,
# но меняет geometry — getBoundingClientRect), а не для проверки контента AO3.
PAGE_HEADING = "h1"

WORK_BLURB = "li[id^='work_'].work.blurb"
BLURB_TITLE = "h4.heading a"
BLURB_AUTHOR = "h4.heading a[rel='author']"
BLURB_WORDCOUNT = ".stats .words"
TAGS_CONTAINER = "ul.tags.commas"

# Инжектируется приложением (ao3_bridge.js) — bridge помечает элементы data-атрибутами
# (стабильнее классов). Сверено с assets/ao3_bridge.js.
BTN_WRAP = "[data-ao3-btn-wrap]"
RATE_BUTTON = "[data-ao3-rate-btn]"
NOTE_BUTTON = "[data-ao3-note-btn]"
TAG_BUTTON = "[data-ao3-tag-btn]"
# `[data-ao3-badge]` (прежний RATING_BADGE) УДАЛЁН (AT-BUG-004 инкремент 3): в
# ao3_bridge.js этот атрибут встречается ТОЛЬКО в defensive-очистке
# (`applyRatings`: `li.querySelectorAll('[data-ao3-badge]').forEach(remove)`) —
# элемент с ним НИКОГДА не создаётся; проверка по нему всегда возвращала False
# (латентный TEST_BUG с инкремента 1, пойман при отладке TC-009-пробы, сверено
# живым DOM). Проставленный рейтинг наблюдаем как непрозрачный `background-color`
# самой Rate-кнопки (`updateRateButton` красит `RATE_BUTTON` цветом `BADGE[rating]`,
# не создаёт отдельный элемент) — см. `ListingPage.badge_for`.
TAG_HIGHLIGHT = "[data-ao3-tag-hl]"
# Всплывающая подсказка Note/Tag-кнопки (`ao3_bridge.js::getTooltip`) — единственный
# экземпляр на страницу (`document.body.appendChild`), id стабилен. Клик по НЕЙ (не
# по самой Note-кнопке) открывает нативный `RatingOverlay` с развёрнутым комментарием
# (`signalRateWithNote`) — см. TC-044, `makeNoteButton`/`showTooltip`.
NOTE_TOOLTIP = "#ao3-note-tooltip"
HIDDEN_NOTICE_ID = "ao3-companion-hidden-notice"
SAVE_PROFILE_BTN = "[data-ao3-save-profile]"

# Реальный DOM-инпут формы AO3 Sort & Filter (#work-filters, не инжектируется bridge) —
# TC-040, ao3_bridge.js::injectSaveFilterButton читает `form.elements` по имени
# `work_search[words_from]`. Сверено с `sort_filter_form.mitm` (реальная запись).
WORK_SEARCH_WORDS_FROM = "#work_search_words_from"


def blurb_by_work_id(work_id: str) -> str:
    return f"li#work_{work_id}.work.blurb"


# Инжектируется при открытии локально скачанного файла (BrowserScreen.kt
# injectReaderCss/loadTabContent) — TC-034: мобильный viewport добавляется, только
# если в сыром HTML его не было, id стиля стабилен ("ao3-reader-css").
VIEWPORT_META = "meta[name='viewport']"
READER_CSS_STYLE = "#ao3-reader-css"

# Кастомная themed error page (BrowserScreen.kt buildErrorHtml) — показывается вместо
# дефолтной страницы ошибки WebView/Chrome при onReceivedError главного фрейма
# (TC-046). Класс `.wrap` — контейнер разметки этой конкретной страницы, не
# пересекается с реальной разметкой AO3 (сверено с buildErrorHtml: `<div class="wrap">`).
ERROR_PAGE_HEADING = ".wrap h1"
ERROR_PAGE_RETRY_LINK = ".wrap a"
