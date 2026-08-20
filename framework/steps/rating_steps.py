"""Бизнес-шаги выставления рейтинга (GWT).

В live-режиме выставление рейтинга на странице работы требует навигации по AO3
(сторонний сайт). Основной P0-smoke опирается на сидинг данных; эти шаги —
для точечных сценариев и будущего replay-режима.
"""
from __future__ import annotations

import logging
import re
import time

import allure

from framework.core import contexts
from framework.core.waits import assert_holds_for, wait_for, wait_until
from framework.data import seed_db
from framework.screens.browser_screen import BrowserScreen
from framework.screens.navigation import BottomNav
from framework.screens.rating_overlay import RatingOverlay
from framework.steps import browser_steps

# AT-BUG-057: тот же regex, что `BrowserViewModel.onPageLoaded` (app-under-test,
# BrowserViewModel.kt:476) использует для вычисления `isWorkPage` из URL —
# диагностика ниже обязана согласовываться с реальным условием приложения, а не
# с приблизительной эвристикой.
_WORK_URL_RE = re.compile(r"/works/(\d+)")

logger = logging.getLogger(__name__)


def _work_page_diagnosis(driver) -> str:
    """Читает текущий URL активной WebView-вкладки и признак work-page (тот же
    regex, что вычисляет `isWorkPage` в приложении) для сообщения об ошибке —
    AT-BUG-057: голое «меню рейтинга не появилось» не отличало «навигация не
    дошла до work-page» (URL не совпал) от «панель не отрендерилась на верной
    странице» (URL совпал, а `RatingMenu` всё равно не появился — состояние
    `isWorkPage` не успело примениться или панель скрыта чем-то ещё). Не
    бросает исключений — падение самой диагностики не должно маскировать
    исходный assert падением другого класса."""
    try:
        with contexts.in_webview(driver):
            url = driver.current_url or ""
    except Exception as exc:  # noqa: BLE001 — диагностика best-effort
        return f"url=<не удалось прочитать: {exc!r}>"
    return f"url={url!r} work_page={bool(_WORK_URL_RE.search(url))}"


@allure.step("When открыта страница работы {work_id}")
def open_work_page(driver, work_id: str):
    BrowserScreen(driver).open_work(work_id)


@allure.step("When открыта первая ЖИВАЯ (не 404/интерстишл) work-страница из кандидатов {candidate_ids}")
def open_live_work_page(driver, candidate_ids: list[str], max_attempts: int = 5) -> str:
    """TC-118 (TEST_BUG fix, test-maintainer, 2026-08-11, `runs/RUN-20260811-0405.md`
    root_cause): `open_work_page` сама по себе не проверяет живучесть id —
    навигация на голову волатильной живой ленты AO3 («Latest Works»,
    `browser_steps.LIVE_LISTING_URL`) может попасть на работу, удалённую/
    скрытую между скрапом листинга и навигацией, AO3 в этом случае штатно
    отдаёт 404 (не Cloudflare, как ошибочно предполагала прежняя диагностика).

    Перебирает `candidate_ids` ПО ПОРЯДКУ (голова листинга — самый свежий
    кандидат первым, порядок листинга не переставляется) и открывает каждый,
    проверяя двойной якорь идентичности документа
    (`browser_steps.probe_live_work_page_identity`: pathname `^/works/\\d` +
    маркер реального контента, `selectors.WORK_PAGE_CONTENT_MARKERS`) — тот же
    контракт, что финальный ассерт TC-118 использует ДЛЯ ЭТОЙ же страницы, но
    здесь БЕЗ исключения при неудаче: неживой кандидат пропускается (с
    Allure-заметкой, включающей `title` страницы — отличает штатную AO3 404 от
    Cloudflare-интерстишла и прочего, не гадает вслепую), пробуется следующий.
    Бюджет ограничен `max_attempts` (не безусловный перебор всей ленты).
    Возвращает id первого живого кандидата; если ни один из `max_attempts`
    первых кандидатов не живой — падает с перечнем всех попыток (сигнал того,
    что живая лента AO3 деградировала сильнее, чем единичный мёртвый id, и
    тест не должен угадывать дальше)."""
    attempted: list[str] = []
    for work_id in candidate_ids[:max_attempts]:
        open_work_page(driver, work_id)
        identity = browser_steps.probe_live_work_page_identity(driver)
        attempted.append(f"{work_id}: {identity}")
        if identity["is_live"]:
            return work_id
        allure.attach(
            f"кандидат {work_id} НЕ живая work-страница: {identity}",
            name=f"tc-118-fallback-skip-{work_id}",
            attachment_type=allure.attachment_type.TEXT,
        )
    raise AssertionError(
        f"ни один из {len(candidate_ids[:max_attempts])} кандидатов живой ленты AO3 не "
        f"отдал реальный work-контент за {max_attempts} попыток: {attempted}"
    )


@allure.step("When на странице работы выставлен рейтинг {rating}")
def rate_current_work(driver, rating: str):
    # Встроенная панель WorkRatingPanel (RatingMenu) на странице работы, как и
    # нижняя навигация, скрыта на вкладке Browse за нижней ручкой-пилюлей
    # (BottomBar.kt: AnimatedVisibility(selectedTab != BROWSE || navExpanded)) —
    # раскрываем её тем же механизмом, что и BottomNav.
    BottomNav(driver).ensure_visible()
    overlay = RatingOverlay(driver)
    if not overlay.is_visible():
        raise AssertionError(
            f"меню рейтинга не появилось на странице работы ({_work_page_diagnosis(driver)})"
        )
    overlay.choose(rating)


# --- TC-256 (AT-BUG-074): дожидается асинхронного upsert'а Room после
# JS-события auto-mark-as-read (`Ao3JsBridge.onWorkFinished`,
# `viewModelScope.launch`) — прямое чтение Room (`seed_db.read_work_ratings_
# full()`), без похода в UI (тот же приём, что `app_steps.wait_for_tabs_count`/
# `settings_steps` polling-функции). Слой steps (не tests/) — `wait_for`/
# `framework.core.waits` запрещён в tests/ напрямую (docs/08 C1, arch_check.py).
@allure.step("Then рейтинг работы {work_id} становится {expected}")
def wait_for_rating(work_id: str, expected: str, timeout: int = 20) -> dict:
    """Опрашивает `seed_db.read_work_ratings_full()` до появления
    `rating == expected` у строки `work_id`. Возвращает ПОЛНУЮ строку (не
    только факт совпадения рейтинга) — вызывающий код читает из неё
    downloadPath/comment/tags/title/fandom/word_count/timestamp для
    последующих Then-ассертов без второго похода в Room."""
    wait_for(
        lambda: seed_db.read_work_ratings_full().get(work_id, {}).get("rating") == expected,
        timeout=timeout,
        message=f"rating работы {work_id} не стал {expected!r}",
    )
    return seed_db.read_work_ratings_full()[work_id]


@allure.step("When на странице работы в панели рейтинга раскрыт раздел тегов и добавлен личный тег «{tag}»")
def add_tag_via_panel(driver, tag: str):
    """TC-114 (edge-vs-level, зеркало TC-115 через встроенную панель work-page
    вместо bottom-sheet листинга): панель `RatingMenu` — ОБЩИЙ composable с
    bottom-sheet листинга (`add_tag_via_listing_overlay`), но, как и в
    `rate_current_work`, спрятана за `AnimatedVisibility` нижней навигации на
    вкладке Browse — раскрываем её тем же механизмом (`BottomNav.ensure_visible()`)
    перед использованием `RatingOverlay`."""
    BottomNav(driver).ensure_visible()
    overlay = RatingOverlay(driver)
    if not overlay.is_visible():
        raise AssertionError(
            f"меню рейтинга не появилось на странице работы ({_work_page_diagnosis(driver)})"
        )
    overlay.toggle_tags()
    overlay.enter_tag_input(tag)
    overlay.confirm_tag_input()


@allure.step("When в открывшемся с листинга bottom-sheet выбран рейтинг {rating}")
def rate_via_listing_overlay(driver, rating: str):
    """Нативный `RatingOverlay` (bottom-sheet, ui/components/RatingOverlay.kt),
    открытый Rate-кнопкой листинга (`browser_steps.tap_rate_button`) — в отличие от
    встроенной панели (`rate_current_work`) НЕ спрятан за `AnimatedVisibility` нижней
    навигации (рендерится в `BrowserScreen.kt` безусловно при `showRatingOverlay=true`,
    поверх WebView), поэтому `BottomNav.ensure_visible()` здесь не нужен."""
    overlay = RatingOverlay(driver)
    assert overlay.is_visible(), "нативный bottom-sheet рейтинга не появился после Rate-кнопки листинга"
    overlay.choose(rating)


@allure.step("When bottom-sheet рейтинга закрыт тапом по затемнённой области")
def dismiss_rating_overlay(driver):
    """`onSave`/`onSaveNote` (BrowserScreen.kt) вызывают `applyRating(..., dismiss=false)` —
    bottom-sheet НЕ закрывается сам после выбора рейтинга (позволяет дописать note/tags
    без переоткрытия), закрывается только явным тапом по scrim (см.
    `RatingOverlay.dismiss`, TC-009)."""
    RatingOverlay(driver).dismiss()


@allure.step("Then панель рейтинга присутствует в дереве и кликабельна (без изменения выбора)")
def assert_rating_panel_present_and_clickable(driver):
    """TC-107 (font_scale=1.3): доказывает присутствие/кликабельность панели без
    реального тапа (изменение сохранённого рейтинга не входит в сценарий кейса,
    в отличие от `rate_current_work`)."""
    BottomNav(driver).ensure_visible()
    overlay = RatingOverlay(driver)
    if not overlay.is_visible():
        raise AssertionError(
            f"меню рейтинга не появилось на странице работы (font_scale=1.3) "
            f"({_work_page_diagnosis(driver)})"
        )
    assert overlay.is_clickable_attr(overlay.button_container_locator("SAVE")), (
        "кнопка рейтинга Favorite не кликабельна (font_scale=1.3)"
    )


@allure.step("Given зафиксирован baseline цвета кнопки рейтинга {rating} на панели работы")
def capture_panel_rating_baseline(driver, rating: str) -> float:
    """Раскрывает панель `RatingMenu` (если ещё не раскрыта) и измеряет исходный
    (невыбранный) цвет её кнопки `rating` — baseline для `assert_rating_button_selected`
    (TC-010, см. `RatingOverlay.button_avg_luma`)."""
    BottomNav(driver).ensure_visible()
    overlay = RatingOverlay(driver)
    if not overlay.is_visible():
        raise AssertionError(
            f"меню рейтинга не появилось на странице работы ({_work_page_diagnosis(driver)})"
        )
    return overlay.button_avg_luma(rating)


@allure.step("Given зафиксирован baseline цвета кнопки рейтинга {rating} в открытом bottom-sheet листинга")
def capture_listing_overlay_baseline(driver, rating: str) -> float:
    """Как `capture_panel_rating_baseline`, но для bottom-sheet, открытого Rate-кнопкой
    листинга (`rate_via_listing_overlay`) — тот же виджет `RatingMenu`, но не спрятан
    за `AnimatedVisibility` нижней навигации, `BottomNav.ensure_visible()` не нужен
    (см. докстринг `rate_via_listing_overlay`, TC-009)."""
    overlay = RatingOverlay(driver)
    assert overlay.is_visible(), "нативный bottom-sheet рейтинга не появился после Rate-кнопки листинга"
    return overlay.button_avg_luma(rating)


@allure.step("Then кнопка рейтинга {rating} визуально отражает выбор немедленно")
def assert_rating_button_selected(driver, rating: str, baseline_luma: float, timeout: int = 6, ratio: float = 0.75):
    """Опрашивает luma кнопки (общий приём для встроенной панели work-page И
    bottom-sheet листинга — оба используют один и тот же composable `RatingMenu`),
    пока она не потемнеет относительно `baseline_luma` (переход в `ratingAccent` —
    насыщенный тёмный цвет против светлого невыбранного фона, см.
    `RatingOverlay.button_avg_luma`) — опрос вместо одноразового чтения, тот же
    паттерн, что `browser_steps.assert_webview_darkened` (анимация
    `animateColorAsState`, 180мс tween, не мгновенна кадр-в-кадр). TC-009/TC-010."""
    def _selected(d):
        luma = RatingOverlay(d).button_avg_luma(rating)
        return luma < baseline_luma * ratio
    wait_until(
        driver, _selected, timeout=timeout,
        message=f"кнопка рейтинга {rating} не изменила цвет относительно baseline={baseline_luma:.1f} за {timeout}с",
    )


@allure.step("Then панель рейтинга на странице работы БОЛЬШЕ НЕ отражает выбор {rating}")
def assert_panel_rating_deselected(driver, rating: str, selected_baseline_luma: float, timeout: int = 10, ratio: float = 0.75):
    """Симметрично `assert_rating_button_selected` — обратное направление
    (TC-020: панель должна вернуться к невыбранному светлому цвету кнопки после
    Clear all ratings). `selected_baseline_luma` — luma, снятая ПОКА рейтинг ещё
    был выставлен (тёмный `ratingAccent`); ждём, пока кнопка не посветлеет
    заметно выше этого значения — тот же приём деления на `ratio`, что
    `browser_steps.assert_webview_lightened`. Раскрывает панель (`BottomNav.
    ensure_visible()`), если она успела свернуться после переключения вкладок."""
    from framework.screens.navigation import BottomNav
    BottomNav(driver).ensure_visible()
    def _deselected(d):
        luma = RatingOverlay(d).button_avg_luma(rating)
        return luma > selected_baseline_luma / ratio
    wait_until(
        driver, _deselected, timeout=timeout,
        message=(
            f"кнопка рейтинга {rating} осталась в выбранном виде (luma не поднялась выше "
            f"{selected_baseline_luma / ratio:.1f}, baseline выбранного={selected_baseline_luma:.1f}) "
            f"после Clear all ratings — панель не отразила очистку без reload"
        ),
    )


@allure.step("When в открытом bottom-sheet листинга раскрыто поле комментария и сохранён текст «{comment}»")
def add_note_via_listing_overlay(driver, comment: str):
    """TC-074/075 (live-ветвь): раскрывает поле комментария в уже открытом (Rate-
    кнопкой листинга) нативном `RatingOverlay` и сохраняет текст через "Save note" —
    живой аналог `seed_with_comment` из TC-075/077 (replay), доказывающий тот же
    контракт `applyRatings` через реальный UI-ввод, а не сидинг."""
    overlay = RatingOverlay(driver)
    assert overlay.is_visible(), "нативный bottom-sheet рейтинга не открыт — нечего раскрывать"
    overlay.toggle_comment()
    overlay.enter_comment(comment)
    overlay.save_note()


@allure.step("When в открытом bottom-sheet листинга раскрыт раздел тегов и добавлен личный тег «{tag}»")
def add_tag_via_listing_overlay(driver, tag: str):
    """TC-076/077 (live-ветвь): раскрывает раздел личных тегов в уже открытом bottom-
    sheet и добавляет `tag` через поле ввода + кнопку "Add" — требует уже выставленного
    рейтинга (раздел недоступен без него, см. `RatingOverlay.toggle_tags`)."""
    overlay = RatingOverlay(driver)
    assert overlay.is_visible(), "нативный bottom-sheet рейтинга не открыт — нечего раскрывать"
    overlay.toggle_tags()
    overlay.enter_tag_input(tag)
    overlay.confirm_tag_input()


@allure.step("Then overlay рейтинга открыт с развёрнутым полем комментария, предзаполненным «{expected_text}»")
def assert_note_overlay_expanded_with_text(driver, expected_text: str):
    """AT-BUG-085 сиблинг-аудит (D-0043): оба чтения здесь — ПОЗИТИВНЫЕ опросы
    присутствия (`is_visible`/`comment_expanded` → `BaseScreen.is_present`,
    сам ждёт ПОЯВЛЕНИЯ узла до своего `timeout`) — не подвержены классу гонки
    AT-BUG-085 (которая била только НЕГАТИВНОЕ чтение `not comment_expanded()`,
    короткозамыкавшееся на первом снимке без ожидания ИСЧЕЗНОВЕНИЯ узла).
    Оставлено без изменений."""
    overlay = RatingOverlay(driver)
    assert overlay.is_visible(), "overlay рейтинга не открылся по Note-кнопке"
    assert overlay.comment_expanded(), (
        "поле комментария должно быть развёрнуто сразу («Hide note» виден), "
        "а не свёрнуто за «Add a note»"
    )
    assert overlay.comment_text_visible(expected_text), (
        f"поле комментария не предзаполнено текстом «{expected_text}»"
    )


# --- TC-087/088: свёрнутое превью комментария (Save note/Clear note) ---

@allure.step("Then bottom-sheet рейтинга остаётся открытым")
def assert_overlay_still_open(driver):
    """AT-BUG-085 сиблинг-аудит (D-0043): `is_visible()` — позитивный опрос
    присутствия, не подвержен классу гонки AT-BUG-085 (см. докстринг
    `assert_note_overlay_expanded_with_text`). Оставлено без изменений."""
    assert RatingOverlay(driver).is_visible(), (
        "bottom-sheet рейтинга неожиданно закрылся"
    )


# --- AT-BUG-085: settle+hold опрос для негативного Then после сохранения
# комментария — тот же двухфазный приём, что `library_steps._poll_tab_absent`
# (AT-BUG-082/083), применённый к ДРУГОМУ UI-механизму этого модуля.
#
# Локализация (живое чтение `ui/components/RatingOverlay.kt`, `RatingMenu`):
# переключение `showComment` НЕ анимировано — ни `animateColorAsState`, ни
# `AnimatedVisibility` на этой ветке НЕТ, это простой Compose `if (!showComment
# && comment.isNotBlank()) {...превью...} else {TextButton("Hide note"/"Add a
# note")}` — ЭТО доказано чтением кода. Задержка на recomposition/measure/
# layout ПЕРЕД тем, как новое дерево реально отражается в accessibility
# snapshot под нагрузкой (тот же класс задержки, что WARNING `LibraryScreen.
# _settle_tab_switch` в AT-BUG-082 наблюдении) — ОЦЕНКА конкретного механизма
# задержки, НЕ изолирована отдельным замером (F-30; критик-гейт О3,
# 2026-08-20); на корректность самого фикса это не влияет — см. следующий
# абзац, он не зависит от точного механизма. Async Room-запись / JS-мост
# `applyRatings` НЕ на критическом пути этого конкретного чтения — оба
# пишутся/читаются через `onSaveNote`, но `showComment=false` выставляется
# СИНХРОННО в том же обработчике клика, до ухода в `onSaveNote`.
#
# `assert_comment_collapsed_with_text` раньше делала ОДИН
# `overlay.comment_expanded()` СРАЗУ после `add_note_via_listing_overlay`
# (тап «Save note», возврат немедленный). `comment_expanded()` →
# `BaseScreen.is_present(by_text("Hide note"))` ждёт ПОЯВЛЕНИЯ узла, но
# возвращает `True` НЕМЕДЛЕННО на первом же снимке, если узел ещё присутствует
# — НЕ ждёт его ИСЧЕЗНОВЕНИЯ. Если «Hide note» ещё не успел уйти из дерева на
# момент чтения, `not comment_expanded()` падает мгновенно, без единого шанса
# на устаканивание (TC-115, `bugs/AT-BUG-085.md`). ЭТО — достаточное и
# самостоятельное основание фикса, доказано чтением `base_screen.py` (критик-
# гейт AT-BUG-085, 2026-08-20).
#
# Окно наблюдения (критик-гейт О1, 2026-08-20): старая семантика читала ОДИН
# раз с timeout=6s (полное непрерывное окно ожидания появления). Новое
# settle+hold покрывает settle(до 3.0s, интервал 0.3s) + hold(до 4.0s,
# интервал 0.3s) ≈ до 5.9s суммарно, с блокирующими паузами `sleep(0.3)`
# между чтениями (не непрерывное наблюдение, а дискретный опрос) — короче
# исходных 6s и с бюджетом слепых промежутков ~0.9s. Признано практически
# незначимым: реэкспансия — persistent-состояние (не транзиентный всплеск),
# 5+ независимых живых прогонов (worker + критик) сошлись зелёными; бюджет
# сознательно НЕ увеличен до 6s, чтобы не удлинять КАЖДЫЙ вызов без
# доказанной необходимости — при первом же рецидиве флака здесь пересмотреть
# это решение в первую очередь.
#
# Стоимость чтения `comment_expanded` в этом контексте (settle-интервал 0.3s
# read_timeout=1) живым замером НЕ откалибрована под D-0043 (докстринг
# `waits.poll_until_stable`, критик-гейт О2, 2026-08-20) — унаследована от
# `library_steps._poll_tab_absent` без замера на этом конкретном экране.
# Направление отказа безопасное (ложный красный, не ложный зелёный) —
# остаточный риск, не блокер.
_COMMENT_COLLAPSE_SETTLE_TIMEOUT = 3.0
_COMMENT_COLLAPSE_SETTLE_INTERVAL = 0.3
_COMMENT_COLLAPSE_SETTLE_READ_TIMEOUT = 1
_COMMENT_COLLAPSE_HOLD_BUDGET = 4.0
_COMMENT_COLLAPSE_HOLD_INTERVAL = 0.3


def _poll_comment_collapsed(overlay: RatingOverlay) -> bool:
    """Возвращает `True`, если поле комментария settled на СВЁРНУТОМ виде
    (фаза 1, `_COMMENT_COLLAPSE_SETTLE_TIMEOUT`) И остаётся свёрнутым весь
    `_COMMENT_COLLAPSE_HOLD_BUDGET` (фаза 2) — см. блок-комментарий выше за
    полным разбором класса гонки (AT-BUG-085, обобщение AT-BUG-082/083
    `library_steps._poll_tab_absent` на другой UI-механизм)."""
    deadline = time.monotonic() + _COMMENT_COLLAPSE_SETTLE_TIMEOUT
    expanded = overlay.comment_expanded(timeout=_COMMENT_COLLAPSE_SETTLE_READ_TIMEOUT)
    settle_reads = 1
    while expanded and time.monotonic() < deadline:
        time.sleep(_COMMENT_COLLAPSE_SETTLE_INTERVAL)
        expanded = overlay.comment_expanded(timeout=_COMMENT_COLLAPSE_SETTLE_READ_TIMEOUT)
        settle_reads += 1
    if expanded:
        # Никогда не сходилось к свёрнутому виду за весь settle-бюджет —
        # persistent-регрессия, не транзитный артефакт recomposition-лага.
        return False
    if settle_reads > 1:
        logger.warning(
            "AT-BUG-085 (rating_steps._poll_comment_collapsed): транзитный "
            "стейл-позитив «Hide note» проглочен settle-фазой за %d "
            "чтени(й/е) — расследуй, если повторяется часто (может означать, "
            "что recomposition/layout систематически шире "
            "_COMMENT_COLLAPSE_SETTLE_TIMEOUT=%.1fs)",
            settle_reads, _COMMENT_COLLAPSE_SETTLE_TIMEOUT,
        )
    try:
        assert_holds_for(
            lambda: not overlay.comment_expanded(timeout=_COMMENT_COLLAPSE_SETTLE_READ_TIMEOUT),
            budget_s=_COMMENT_COLLAPSE_HOLD_BUDGET,
            interval_s=_COMMENT_COLLAPSE_HOLD_INTERVAL,
            msg="поле комментария вновь развернулось во время hold-окна наблюдения",
        )
    except AssertionError:
        logger.warning(
            "AT-BUG-085 (rating_steps._poll_comment_collapsed): поле "
            "комментария вновь развернулось во время hold-окна наблюдения "
            "(после %d settle-чтени(й/е)) — ПОЗДНЯЯ регрессия, пойманная "
            "hold-фазой (старый одноразовый код пропустил бы её)",
            settle_reads,
        )
        return False
    return True


@allure.step("Then после сохранения поле комментария свёрнуто в превью с текстом «{text}»")
def assert_comment_collapsed_with_text(driver, text: str):
    overlay = RatingOverlay(driver)
    assert _poll_comment_collapsed(overlay), (
        "поле комментария должно свернуться в компактное превью, а не остаться развёрнутым"
    )
    assert overlay.comment_text_visible(text), (
        f"свёрнутое превью комментария не показывает текст «{text}»"
    )


@allure.step("When bottom-sheet рейтинга закрыт и снова открыт Rate-кнопкой работы {work_id}")
def reopen_listing_overlay(driver, work_id: str):
    """Закрывает bottom-sheet тапом по scrim и открывает его заново той же Rate-
    кнопкой листинга — доказательство персистентности в Room (TC-087/088/090/091),
    не только локального Compose-состояния overlay, которое было бы потеряно при
    пересоздании composable."""
    dismiss_rating_overlay(driver)
    browser_steps.tap_rate_button(driver, work_id)
    assert RatingOverlay(driver).is_visible(), (
        f"нативный bottom-sheet рейтинга не открылся повторно для работы {work_id}"
    )


@allure.step("Then после переоткрытия overlay комментарий по-прежнему предзаполнен «{text}»")
def assert_comment_persisted(driver, text: str, timeout: int = 8):
    overlay = RatingOverlay(driver)
    assert overlay.is_visible(), "overlay рейтинга не открылся при повторном открытии"
    assert overlay.comment_text_visible(text, timeout=timeout), (
        f"комментарий «{text}» не сохранился после переоткрытия overlay — "
        "потеряна персистентность в Room"
    )


@allure.step("When тап по свёрнутому превью комментария «{text}» — поле раскрывается")
def tap_comment_preview(driver, text: str):
    RatingOverlay(driver).tap_comment_preview(text)


@allure.step("When нажата «Clear note»")
def clear_note(driver):
    RatingOverlay(driver).clear_note()


@allure.step("Then поле комментария пусто, виден тоггл «Add a note»")
def assert_comment_cleared(driver, timeout: int | None = None):
    assert RatingOverlay(driver).add_note_toggle_visible(timeout=timeout or 4), (
        "после Clear note ожидали тоггл «Add a note» вместо превью со старым текстом"
    )


# --- TC-090/091: добавление/удаление личного тега через bottom-sheet листинга ---

@allure.step("When раздел личных тегов overlay раскрыт")
def open_tags_section(driver):
    overlay = RatingOverlay(driver)
    assert overlay.is_visible(), "нативный bottom-sheet рейтинга не открыт — нечего раскрывать"
    overlay.toggle_tags()


@allure.step("When раздел личных тегов overlay свёрнут")
def collapse_tags_section(driver):
    RatingOverlay(driver).hide_tags()


@allure.step("When тап по выбранному чипу «{tag}»")
def tap_selected_chip(driver, tag: str):
    RatingOverlay(driver).tap_selected_chip(tag)


@allure.step("Then лейбл раздела тегов показывает «Saved tags ({n})»")
def assert_tags_count_label_visible(driver, n: int, timeout: int | None = None):
    assert RatingOverlay(driver).tags_count_label_visible(n, timeout=timeout or 6), (
        f"лейбл «Saved tags ({n})» не появился"
    )


@allure.step("Then чип «{tag}» присутствует среди выбранных тегов overlay")
def assert_chip_visible(driver, tag: str, timeout: int = 6):
    assert RatingOverlay(driver).chip_visible(tag, timeout=timeout), (
        f"чип «{tag}» не найден среди тегов overlay"
    )


# --- AT-BUG-090 (4-й член класса AT-BUG-081/082/083/085): settle+hold опрос
# для негативного Then сразу после стейт-меняющего действия
# (`tap_selected_chip` — удаление тега; `reopen_listing_overlay` — закрытие+
# переоткрытие bottom-sheet) — прямой аналог `_poll_comment_collapsed`
# (AT-BUG-085, тот же файл, тот же composable-семья `RatingOverlay`), только
# для `chip_visible` вместо `comment_expanded`. См. блок-комментарий у
# `_poll_comment_collapsed` (выше в этом файле) за полным разбором механизма
# гонки: `BaseScreen.is_present` (и построенный на нём `chip_visible`) ждёт
# ПОЯВЛЕНИЯ узла до `timeout`, но возвращает `True` НЕМЕДЛЕННО на первом же
# снимке, если узел ещё присутствует — не ждёт его ИСЧЕЗНОВЕНИЯ. Старая
# реализация (`not chip_visible(...)` одним снимком сразу после
# `tap_selected_chip`/`reopen_listing_overlay`) могла поймать стейл-позитив
# (чип ещё не ушёл из дерева на момент чтения) и упасть без единого шанса на
# устаканивание — тот же класс, что TC-115 (AT-BUG-085).
#
# Бюджеты позаимствованы у `_COMMENT_COLLAPSE_*` без отдельного замера под
# D-0043 (см. предупреждение критик-гейта О2 AT-BUG-085 у тех же констант) —
# унаследованы для другого чтения (`chip_visible`) БЕЗ живой калибровки на
# ЭТОМ конкретном экране; направление отказа безопасное (ложный красный, не
# ложный зелёный) — остаточный риск, не блокер (тот же trade-off, что там).
_CHIP_ABSENT_SETTLE_TIMEOUT = 3.0
_CHIP_ABSENT_SETTLE_INTERVAL = 0.3
_CHIP_ABSENT_SETTLE_READ_TIMEOUT = 1
_CHIP_ABSENT_HOLD_BUDGET = 4.0
_CHIP_ABSENT_HOLD_INTERVAL = 0.3


def _poll_chip_absent(overlay: RatingOverlay, tag: str) -> bool:
    """Возвращает `True`, если чип `tag` settled на ОТСУТСТВУЮЩЕМ виде (фаза 1,
    `_CHIP_ABSENT_SETTLE_TIMEOUT`) И остаётся отсутствующим весь
    `_CHIP_ABSENT_HOLD_BUDGET` (фаза 2) — см. блок-комментарий выше за полным
    разбором класса гонки (AT-BUG-090, 4-й член класса AT-BUG-081/082/083/085)."""
    deadline = time.monotonic() + _CHIP_ABSENT_SETTLE_TIMEOUT
    visible = overlay.chip_visible(tag, timeout=_CHIP_ABSENT_SETTLE_READ_TIMEOUT)
    settle_reads = 1
    while visible and time.monotonic() < deadline:
        time.sleep(_CHIP_ABSENT_SETTLE_INTERVAL)
        visible = overlay.chip_visible(tag, timeout=_CHIP_ABSENT_SETTLE_READ_TIMEOUT)
        settle_reads += 1
    if visible:
        # Никогда не сходилось к отсутствующему виду за весь settle-бюджет —
        # persistent-регрессия (чип реально не исчез), не транзитный артефакт
        # recomposition-лага.
        return False
    if settle_reads > 1:
        logger.warning(
            "AT-BUG-090 (rating_steps._poll_chip_absent): транзитный "
            "стейл-позитив чипа «%s» проглочен settle-фазой за %d "
            "чтени(й/е) — расследуй, если повторяется часто (может означать, "
            "что recomposition/layout систематически шире "
            "_CHIP_ABSENT_SETTLE_TIMEOUT=%.1fs)",
            tag, settle_reads, _CHIP_ABSENT_SETTLE_TIMEOUT,
        )
    try:
        assert_holds_for(
            lambda: not overlay.chip_visible(tag, timeout=_CHIP_ABSENT_SETTLE_READ_TIMEOUT),
            budget_s=_CHIP_ABSENT_HOLD_BUDGET,
            interval_s=_CHIP_ABSENT_HOLD_INTERVAL,
            msg=f"чип «{tag}» вновь появился во время hold-окна наблюдения",
        )
    except AssertionError:
        logger.warning(
            "AT-BUG-090 (rating_steps._poll_chip_absent): чип «%s» вновь "
            "появился во время hold-окна наблюдения (после %d settle-чтени(й/е)) "
            "— ПОЗДНЯЯ регрессия, пойманная hold-фазой (старый одноразовый код "
            "пропустил бы её)",
            tag, settle_reads,
        )
        return False
    return True


@allure.step("Then чип «{tag}» отсутствует среди тегов overlay")
def assert_chip_absent(driver, tag: str):
    overlay = RatingOverlay(driver)
    assert _poll_chip_absent(overlay, tag), (
        f"чип «{tag}» неожиданно присутствует среди тегов overlay"
    )
