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
RATING_BADGE = "[data-ao3-badge]"
TAG_HIGHLIGHT = "[data-ao3-tag-hl]"
HIDDEN_NOTICE_ID = "ao3-companion-hidden-notice"
SAVE_PROFILE_BTN = "[data-ao3-save-profile]"


def blurb_by_work_id(work_id: str) -> str:
    return f"li#work_{work_id}.work.blurb"
