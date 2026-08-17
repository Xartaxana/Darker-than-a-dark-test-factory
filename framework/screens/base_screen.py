"""Базовый Screen Object. Локаторная дисциплина: элементы ищутся хелперами отсюда,
в наследниках объявляются локаторы (один локатор — одно место). Без assert'ов и без
знания о сценариях — это делают слои steps/tests.
"""
from __future__ import annotations

import allure
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support import expected_conditions as EC

from framework.config import settings
from framework.core import contexts
from framework.core.waits import poll_for, wait_until

# --- Тюнинг свайп-поиска (AT-BUG-048) ---
# Один длинный быстрый свайп (55% высоты за 400мс) — это fling: Android/Compose
# продолжает ехать по инерции ПОСЛЕ возврата вызова driver.swipe. Вместо него
# та же ПОЛНАЯ дистанция раунда разбита на несколько КОРОТКИХ подряд идущих
# свайпов меньшей скорости (ниже порога fling — список останавливается сразу по
# отпускании, без инерции, а итоговая landing-позиция раунда не меняется). После
# ЗАВЕРШЕНИЯ полного раунда опрашивается всё settle-окно (`poll_for`), а не один
# снимок сразу после возврата — это и есть исправление самой сути дефекта
# (редкий одиночный опрос под нагрузкой мог не застать искомый текст).
SWIPE_MICRO_STEPS = 3
SWIPE_MICRO_DURATION_MS = 300
SWIPE_SETTLE_TIMEOUT_S = 1.2
SWIPE_SETTLE_POLL_INTERVAL_S = 0.3

# --- Тюнинг «доведения» якоря до кромки вьюпорта (AT-BUG-080) ---
# `_swipe_search` объявлял успех, как только якорный текст ПРИСУТСТВУЕТ в
# дереве — UIAutomator репортит bounds УЖЕ обрезанными по вьюпорту, поэтому
# «присутствует» могло означать «заглянул на 9px снизу», а не «строка
# пригодна к взаимодействию» (сосед по той же строке — кнопка/тумблер/
# подзаголовок — ещё вне дерева). SWIPE_ANCHOR_MARGIN_PX — запас от кромки
# вьюпорта, ниже которого якорь считается рискованно обрезанным; в этом
# случае раунд доводится ещё несколькими КОРОТКИМИ свайпами В ТОМ ЖЕ
# направлении (SWIPE_NUDGE_MAX_ATTEMPTS штук), пока якорь не окажется внутри
# вьюпорта с запасом — либо пока список физически не перестанет двигаться
# (последняя строка, дальше сдвигать некуда — отдаётся как есть).
SWIPE_ANCHOR_MARGIN_PX = 24
SWIPE_NUDGE_MAX_ATTEMPTS = 3
SWIPE_NUDGE_DURATION_MS = 250


class BaseScreen:
    def __init__(self, driver):
        self.driver = driver
        contexts.to_native(driver)
        # Диагностика последнего неуспешного swipe_to_text/swipe_up_to_text
        # (AT-BUG-048) — различает «строки нет в списке» от «прокрутка
        # дошла до конца, строка не поймана»; пусто, пока не было неуспеха.
        self.last_swipe_diagnostic = ""

    # --- Локаторы: предпочтение content-desc > text > доступный XPath ---
    def by_desc(self, desc: str):
        return (AppiumBy.ANDROID_UIAUTOMATOR,
                f'new UiSelector().description("{desc}")')

    def by_text(self, text: str):
        return (AppiumBy.ANDROID_UIAUTOMATOR,
                f'new UiSelector().text("{text}")')

    def by_text_contains(self, text: str):
        return (AppiumBy.ANDROID_UIAUTOMATOR,
                f'new UiSelector().textContains("{text}")')

    # --- Общие операции ---
    def find(self, locator, timeout: int | None = None):
        return wait_until(self.driver, EC.presence_of_element_located(locator),
                          timeout=timeout, message=f"не найден элемент: {locator}")

    def tap(self, locator, timeout: int | None = None):
        el = wait_until(self.driver, EC.element_to_be_clickable(locator),
                        timeout=timeout, message=f"не кликабелен: {locator}")
        el.click()
        return el

    def is_present(self, locator, timeout: int = 5) -> bool:
        try:
            wait_until(self.driver, EC.presence_of_element_located(locator), timeout=timeout)
            return True
        except Exception:  # noqa: BLE001
            return False

    def wait_absent(self, locator, timeout: int | None = None) -> None:
        """Опрашивает ОТСУТСТВИЕ локатора — дожидается, пока ни один узел ему не
        соответствует (например, полное исчезновение snackbar с экрана). Симметрично
        `is_present`, но поднимает при неуспехе, а не возвращает bool: вызывающему
        коду (TC-176) нужно именно дождаться, не просто узнать текущее состояние."""
        wait_until(
            self.driver,
            lambda d: len(d.find_elements(*locator)) == 0,
            timeout=timeout,
            message=f"элемент не исчез с экрана: {locator}",
        )

    def is_enabled(self, locator, timeout: int = 5) -> bool:
        """Читает accessibility-атрибут `enabled` найденного элемента (не требует
        видимости/кликабельности — сам факт enabled=false и есть проверяемое состояние)."""
        return self.find(locator, timeout).get_attribute("enabled") == "true"

    def is_clickable_attr(self, locator, timeout: int = 5) -> bool:
        """Читает accessibility-атрибут `clickable` найденного узла БЕЗ клика (в
        отличие от `tap()`/`element_to_be_clickable`, который клика дожидается И
        выполняет) — TC-107: доказать «контрол кликабелен» без побочного эффекта
        реального нажатия (например, изменения выбранной темы/размера шрифта)."""
        return self.find(locator, timeout).get_attribute("clickable") == "true"

    def text_of(self, locator, timeout: int | None = None) -> str:
        return self.find(locator, timeout).text

    def label_of(self, locator, timeout: int | None = None) -> tuple[str, str]:
        """Возвращает `(content-desc, text)` найденного узла — чтение атрибутов
        accessibility-дерева без взаимодействия (TC-106: инспекция «непустой
        content-desc ИЛИ видимый text» на уже отрисованных контролах)."""
        el = self.find(locator, timeout)
        desc = el.get_attribute("contentDescription") or ""
        text = el.get_attribute("text") or el.text or ""
        return desc, text

    def _probe_present(self, locator) -> bool:
        """Немедленная проверка присутствия БЕЗ ожидания — прямой
        `find_elements`, а не `is_present`/`wait_until` (поллинг поверх
        поллинга исказил бы бюджет settle-окна `_swipe_search`)."""
        return len(self.driver.find_elements(*locator)) > 0

    def _scroll_fingerprint(self) -> tuple:
        """Дешёвый отпечаток текущей прокрученной позиции — набор видимых
        непустых текстов. Не изменился после свайпа => список уткнулся в
        конец (AT-BUG-048: различает «строки нет в списке» от «прокрутка
        дошла до конца, строка не поймана»)."""
        els = self.driver.find_elements(
            AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().textMatches(".+")')
        return tuple(sorted((e.get_attribute("text") or "") for e in els))

    # --- Bounds-геометрия (AT-BUG-080) ---
    _SCROLLABLE_CONTAINER = (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().scrollable(true)')

    @staticmethod
    def _parse_bounds(bounds_str: str | None) -> tuple[int, int, int, int] | None:
        """Парсит UIAutomator-атрибут `bounds="[x1,y1][x2,y2]"`. `None`, если
        строка пуста/не в этом формате — вызывающий код обязан трактовать это
        как «не удалось определить», НЕ как «обрезано» (симметрично общему
        принципу «env-негатив ≠ факт»)."""
        if not bounds_str:
            return None
        try:
            left, right = bounds_str.split("][")
            x1, y1 = left.lstrip("[").split(",")
            x2, y2 = right.rstrip("]").split(",")
            return int(x1), int(y1), int(x2), int(y2)
        except (ValueError, AttributeError):
            return None

    @staticmethod
    def _bounds_share_row(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
        """Y-диапазоны двух bounds пересекаются существенно (не просто касаются
        кромкой в 0px) — практический признак «тот же ряд списка» (AT-BUG-080,
        item 3, гард для `find_row_sibling`)."""
        _, a_top, _, a_bottom = a
        _, b_top, _, b_bottom = b
        return min(a_bottom, b_bottom) - max(a_top, b_top) > 0

    def _anchor_clipped_by_viewport(self, loc, check_bottom_edge: bool) -> bool | None:
        """`True`, если найденный `loc` обрезан ИМЕННО той кромкой скроллящегося
        вьюпорта, к которой движется ТЕКУЩИЙ поиск (bounds внутри
        `SWIPE_ANCHOR_MARGIN_PX` от неё или заходят за неё) — AT-BUG-080:
        UIAutomator репортит bounds УЖЕ обрезанными контейнером, узел
        «присутствует» хотя бы одним пикселем задолго до того, как строка
        станет пригодна к использованию (сосед по строке ещё вне дерева).

        `check_bottom_edge` — какую кромку считать обрезающей: `True` —
        ТОЛЬКО нижнюю (`swipe_to_text`, направление поиска вниз — новые строки
        входят в кадр СНИЗУ и рискуют быть обрезаны именно там), `False` —
        ТОЛЬКО верхнюю (`swipe_up_to_text`, симметрично, строки входят
        СВЕРХУ). AT-BUG-080 Б3 (критик-вход rework, живой пробой): раньше
        предикат проверял ОБЕ кромки одновременно — якорь, ЦЕЛИКОМ видимый у
        кромки, ПРОТИВОПОЛОЖНОЙ направлению поиска (например, у верхней
        кромки при `swipe_to_text` — типичная позиция, если якорь виден сразу
        после свежего открытия экрана, без единого свайпа), ложно считался
        обрезанным, и `_settle_clipped_anchor` довозил его ЕЩЁ ДАЛЬШЕ В
        НАПРАВЛЕНИИ ПОИСКА — выводя из дерева уже видимую строку (регрессия).
        Ремедий обязан быть согласован с направлением: свайпать можно только
        НАВСТРЕЧУ той кромке, к которой реально движется текущий раунд —
        значит и обрезку проверяем только по ЭТОЙ кромке.

        `None` — не удалось определить (нет `scrollable(true)`-контейнера в
        дереве или bounds не распознан); вызывающий код обязан трактовать
        `None` как «не проверено» и падать обратно на прежнее (слабое)
        поведение, а не блокировать экраны, где геометрию снять не удалось."""
        els = self.driver.find_elements(*loc)
        if not els:
            return None
        anchor = self._parse_bounds(els[0].get_attribute("bounds"))
        if anchor is None:
            return None
        containers = self.driver.find_elements(*self._SCROLLABLE_CONTAINER)
        if not containers:
            return None
        viewport = self._parse_bounds(containers[0].get_attribute("bounds"))
        if viewport is None:
            return None
        _, a_top, _, a_bottom = anchor
        _, v_top, _, v_bottom = viewport
        if check_bottom_edge:
            return a_bottom > v_bottom - SWIPE_ANCHOR_MARGIN_PX
        return a_top < v_top + SWIPE_ANCHOR_MARGIN_PX

    def _settle_clipped_anchor(self, loc, x: int, step_ys: list[int], check_bottom_edge: bool) -> None:
        """AT-BUG-080 item 1 (+ Б3 rework): `loc` уже присутствует в дереве, но
        может быть обрезан КРОМКОЙ, К КОТОРОЙ ДВИЖЕТСЯ текущий поиск (см.
        `check_bottom_edge` в `_anchor_clipped_by_viewport`) — доводит строку
        короткими доп. свайпами В ТОМ ЖЕ направлении (один микрошаг раунда за
        попытку, `step_ys[0]`->`step_ys[1]`), пока bounds якоря не окажутся
        внутри вьюпорта с запасом, либо пока список физически не перестанет
        двигаться (последняя строка, дальше сдвигать некуда — отдаём как есть,
        не блокируем тест). Якорь, обрезанный ПРОТИВОПОЛОЖНОЙ кромкой (или уже
        целиком видимый), НЕ трогаем — довоз в направлении поиска увёз бы его
        только дальше от центра. Best-effort: если геометрию снять не удалось
        (`_anchor_clipped_by_viewport` вернул `None` — нет scrollable-
        контейнера в дереве), не трогает свайп вовсе — старое поведение для
        экранов без снимаемой геометрии."""
        if self._anchor_clipped_by_viewport(loc, check_bottom_edge) is not True:
            return
        fingerprint = self._scroll_fingerprint()
        for _ in range(SWIPE_NUDGE_MAX_ATTEMPTS):
            self.driver.swipe(x, step_ys[0], x, step_ys[1], SWIPE_NUDGE_DURATION_MS)
            poll_for(lambda: self._probe_present(loc),
                    timeout=SWIPE_SETTLE_TIMEOUT_S, interval=SWIPE_SETTLE_POLL_INTERVAL_S)
            if self._anchor_clipped_by_viewport(loc, check_bottom_edge) is not True:
                return
            new_fingerprint = self._scroll_fingerprint()
            if new_fingerprint == fingerprint:
                return  # список уткнулся — дальше сдвинуть некуда
            fingerprint = new_fingerprint

    def find_row_sibling(self, anchor_text: str, xpath_predicate: str, timeout: int | None = None):
        """Возвращает ПЕРВЫЙ узел вида `//*[<xpath_predicate>]` (например,
        `'@checkable="true"'` или `'@content-desc="Delete"'`), СЛЕДУЮЩИЙ за
        `anchor_text` в document order И принадлежащий ТОЙ ЖЕ строке (Y-bounds
        пересекаются с якорем) — AT-BUG-080, item 3 (+ Б2/Б4 rework).

        Голый `following::...[1]` (как использовался до фикса в `_TAP_TO_
        SCROLL_SWITCH`/`_delete_button_locator` и т.п.) уязвим: если СВОЙ
        узел строки ещё не попал в дерево (та же клипающая обрезка вьюпорта,
        что и у самого якоря — item 1), `[1]` вернёт узел СЛЕДУЮЩЕЙ строки —
        тест не упадёт, а прочитает (или, для кнопок Rename/Delete,
        НАЖМЁТ) ЧУЖОЕ состояние — опаснее честного отказа.

        Б4: опрашивает дерево до `timeout` (по умолчанию `settings.
        DEFAULT_TIMEOUT`), а не один снимок `find_elements` без ожидания —
        своему узлу строки нужно время появиться (recomposition/settle
        якоря). Раньше объявленный параметр `timeout` игнорировался
        (единственный `find_elements` без опроса) — критик воспроизвёл живым
        прогоном `AssertionError after 0.00s (timeout=20 requested)`.

        Б2: ДВА РАЗНЫХ случая с bounds якоря принципиально различаются —
        смешивать их в одном фолбэке на `candidates[0]` небезопасно:
        - bounds якоря НЕДОСТУПНЫ ВООБЩЕ (нет `scrollable(true)`-контейнера/
          bounds не распознан) — легитимный фолбэк на прежнее поведение
          (первый в document order), симметрично `_anchor_clipped_by_
          viewport`: `None` трактуется как «не проверено», не как «не тот
          ряд»;
        - bounds якоря ИЗВЕСТНЫ, но НИ ОДИН кандидат не делит с ним ряд —
          это ИМЕННО тот случай, ради которого функция написана («свой узел
          ещё вне дерева»): молча возвращать `candidates[0]` здесь — тот же
          дефект, что чинили (критик воспроизвёл: фолбэк вернул узел ЧУЖОГО
          ряда, `DELETE-OF-ANOTHER-ROW`). Вместо этого — честно ждём (см.
          выше) и, если own-row кандидат так и не появился до `timeout`,
          падаем понятным `AssertionError`, а не возвращаем чужой элемент."""
        timeout = timeout if timeout is not None else settings.DEFAULT_TIMEOUT
        state: dict = {"element": None, "anchor_bounds_known": False,
                       "row_mismatch": False, "any_candidates": False}

        def _attempt() -> bool:
            anchor_els = self.driver.find_elements(*self.by_text(anchor_text))
            anchor_bounds = self._parse_bounds(anchor_els[0].get_attribute("bounds")) if anchor_els else None
            candidates = self.driver.find_elements(
                AppiumBy.XPATH, f'//*[@text="{anchor_text}"]/following::*[{xpath_predicate}]')
            if not candidates:
                return False
            state["any_candidates"] = True
            if anchor_bounds is None:
                state["element"] = candidates[0]
                return True
            state["anchor_bounds_known"] = True
            for cand in candidates:
                cand_bounds = self._parse_bounds(cand.get_attribute("bounds"))
                if cand_bounds is not None and self._bounds_share_row(anchor_bounds, cand_bounds):
                    state["element"] = cand
                    return True
            state["row_mismatch"] = True
            return False

        if poll_for(_attempt, timeout=timeout, interval=0.4):
            return state["element"]
        if state["anchor_bounds_known"] and state["row_mismatch"]:
            raise AssertionError(
                f"узел [{xpath_predicate}] СВОЕЙ строки «{anchor_text}» не появился за "
                f"{timeout}s — bounds якоря известны, но ни один кандидат [{xpath_predicate}] "
                f"не делит с ним ряд (свой узел строки, похоже, ещё вне дерева/обрезан кромкой "
                f"вьюпорта); чужой ряд НЕ возвращаем (AT-BUG-080 Б2)"
            )
        assert state["any_candidates"], (
            f"узел [{xpath_predicate}] после «{anchor_text}» не найден в дереве за {timeout}s"
        )
        raise AssertionError(
            f"узел [{xpath_predicate}] после «{anchor_text}» найден, но bounds якоря "
            f"«{anchor_text}» ни разу не удалось определить за {timeout}s — не могу "
            f"подтвердить принадлежность ряду"
        )

    def tap_row_sibling(self, anchor_text: str, xpath_predicate: str, timeout: int | None = None):
        """Б4 rework: тапающие call sites (`set_tap_to_scroll`/
        `delete_filter_profile`/... ) раньше проходили через `self.tap()`
        (`element_to_be_clickable`-гейт, тот же принцип, что и у любого
        другого клика в этом классе) — при переводе на `find_row_sibling`
        этот гейт кликабельности потерялся (`find_row_sibling` доказывает
        только ПРИСУТСТВИЕ узла своей строки, не готовность к клику).
        Восстанавливает гейт ПОВЕРХ уже найденного своей-строки элемента:
        `EC.element_to_be_clickable` принимает готовый `WebElement`
        (селениумовский `_predicate` не требует локатора), поэтому
        повторный поиск не нужен."""
        el = self.find_row_sibling(anchor_text, xpath_predicate, timeout)
        el = wait_until(
            self.driver, EC.element_to_be_clickable(el), timeout=timeout,
            message=f"узел [{xpath_predicate}] в строке «{anchor_text}» найден, но не кликабелен",
        )
        el.click()
        return el

    def _swipe_search(self, text: str, max_swipes: int, y1_frac: float, y2_frac: float) -> tuple[bool, str]:
        """Общая реализация `swipe_to_text`/`swipe_up_to_text` (AT-BUG-048,
        AT-BUG-080). Возвращает `(found, diagnostic)` — `diagnostic` пуст при
        `found=True`.

        `check_bottom_edge = y1_frac > y2_frac`: `swipe_to_text` тянет от
        большей доли высоты к меньшей (`y1_frac=0.8 -> y2_frac=0.25`) — палец
        движется ВВЕРХ, список едет вверх, новые строки входят в кадр СНИЗУ,
        поэтому обрезка, которая нас интересует, — именно НИЖНЯЯ кромка.
        `swipe_up_to_text` — зеркально (`y1_frac=0.25 -> y2_frac=0.8`), новые
        строки входят СВЕРХУ, интересна ВЕРХНЯЯ кромка (AT-BUG-080 Б3)."""
        loc = self.by_text(text)
        size = self.driver.get_window_size()
        x = size["width"] // 2
        y1 = int(size["height"] * y1_frac)
        y2 = int(size["height"] * y2_frac)
        step_ys = [y1 + (y2 - y1) * i // SWIPE_MICRO_STEPS for i in range(SWIPE_MICRO_STEPS + 1)]
        check_bottom_edge = y1_frac > y2_frac
        if self.is_present(loc, timeout=2):
            self._settle_clipped_anchor(loc, x, step_ys, check_bottom_edge)
            return True, ""
        fingerprint = self._scroll_fingerprint()
        for _ in range(max_swipes):
            # Полная дистанция раунда (y1->y2, как в исходном одиночном свайпе)
            # ВСЕГДА проходится целиком, короткими не-fling шагами — landing-
            # позиция после раунда остаётся той же, что и раньше (соседние
            # элементы вроде кнопки «Clear…» рядом с «Clear all ratings»
            # оказываются в кадре так же, как при одном большом свайпе); проверка
            # присутствия — ПОСЛЕ раунда, но settle-окном из нескольких опросов
            # (не один снимок сразу после возврата, AT-BUG-048).
            for i in range(SWIPE_MICRO_STEPS):
                self.driver.swipe(x, step_ys[i], x, step_ys[i + 1], SWIPE_MICRO_DURATION_MS)
            if poll_for(lambda: self._probe_present(loc),
                       timeout=SWIPE_SETTLE_TIMEOUT_S, interval=SWIPE_SETTLE_POLL_INTERVAL_S):
                # AT-BUG-080: «присутствует» ещё не значит «пригодно к
                # использованию» — доводим строку, если якорь обрезан кромкой,
                # к которой движется ЭТОТ поиск (Б3: не противоположной).
                self._settle_clipped_anchor(loc, x, step_ys, check_bottom_edge)
                return True, ""
            new_fingerprint = self._scroll_fingerprint()
            if new_fingerprint == fingerprint:
                return False, (
                    f"«{text}»: КОНЕЦ СПИСКА (позиция не изменилась после "
                    f"свайпа) — строка не поймана, список исчерпан"
                )
            fingerprint = new_fingerprint
        return False, f"«{text}»: НЕ НАЙДЕНА в списке за {max_swipes} свайпов (список ещё двигался, конец не достигнут)"

    def swipe_to_text(self, text: str, max_swipes: int = 8) -> bool:
        """Прокручивает экран свайпами, пока не покажется текст. Устойчиво к Compose,
        где UiScrollable не всегда распознаёт скроллируемый контейнер.

        AT-BUG-048: короткие контролируемые свайпы (не fling) + поллинг всего
        settle-окна после каждого — искомый текст больше не проскакивает
        вьюпорт незамеченным между редкими опросами. Неуспех логируется
        диагностикой, различающей «список исчерпан» от «список ещё двигался»
        (`self.last_swipe_diagnostic`) — сигнатура метода (bool) не меняется,
        чтобы все 10 существующих call site получили фикс бесплатно."""
        found, diagnostic = self._swipe_search(text, max_swipes, y1_frac=0.8, y2_frac=0.25)
        self.last_swipe_diagnostic = diagnostic
        if not found:
            self._attach_swipe_diagnostic(diagnostic)
        return found

    def swipe_up_to_text(self, text: str, max_swipes: int = 8) -> bool:
        """Прокручивает экран свайпами в ОБРАТНОМ направлении к `swipe_to_text` —
        нужно, когда искомый текст находится ВЫШЕ текущей позиции скролла (например,
        после подтверждения диалога, который сам не сбрасывает скролл, нужно
        вернуться к разделу, расположенному выше того, где сейчас находимся —
        см. TC-021, `framework/steps/saf_steps.py::open_settings_scrolled_to`).

        AT-BUG-048: та же fling-устойчивая реализация, что `swipe_to_text`
        (симметрично, `_swipe_search`)."""
        found, diagnostic = self._swipe_search(text, max_swipes, y1_frac=0.25, y2_frac=0.8)
        self.last_swipe_diagnostic = diagnostic
        if not found:
            self._attach_swipe_diagnostic(diagnostic)
        return found

    def _attach_swipe_diagnostic(self, diagnostic: str) -> None:
        """Прикладывает диагностику неуспешного swipe-поиска к Allure — иначе
        вызывающий `assert self.swipe_to_text(...), "статичное сообщение"`
        схлопывает «конец списка» и «строки нет» в одинаковый на вид провал
        (AT-BUG-048). Best-effort: недоступность Allure-раннера не должна
        рушить сам тест."""
        try:
            allure.attach(diagnostic, name="swipe_to_text diagnostic",
                          attachment_type=allure.attachment_type.TEXT)
        except Exception:  # noqa: BLE001
            pass

    def _attach_pre_fallback_snapshot(self, text: str) -> None:
        """AT-BUG-062, класс (не экземпляр): любой вызывающий, использующий приём
        `swipe_to_text(...) or swipe_up_to_text(...)`, теряет ПОЗИЦИЮ ОТКАЗА —
        фолбэк `swipe_up_to_text` всегда возвращает список НАВЕРХ, поэтому
        `page_source`, снятый пайплайном при итоговом провале теста
        (`framework/core/reporting.py::attach_failure_artifacts`, teardown),
        фиксирует экран УЖЕ ПОСЛЕ этого возврата, а не позицию, где прямой
        проход не поймал `text`. Снимок ЗДЕСЬ, ДО фолбэка — единственный
        источник, различающий «текста там нет» от «прокрутка проскочила
        строку» (AT-BUG-048). Best-effort, симметрично `_attach_swipe_diagnostic`.
        Изначально жил только в `SettingsScreen` (`_swipe_to_profile`) — поднят
        в `BaseScreen`, т.к. тот же паттерн `swipe_to_text(...) or
        swipe_up_to_text(...)` есть и в `framework/steps/saf_steps.py::
        _scroll_settings_to` (сиблинг, доклад AT-BUG-062 test-maintainer)."""
        try:
            allure.attach(
                self.driver.page_source,
                name=f"page_source pre-fallback (после неуспешного swipe_to_text «{text}»)",
                attachment_type=allure.attachment_type.XML,
            )
        except Exception:  # noqa: BLE001
            pass
