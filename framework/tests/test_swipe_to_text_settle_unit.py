"""Device-free юнит-проба `BaseScreen.swipe_to_text`/`swipe_up_to_text` —
AT-BUG-048 (fling-инерция Compose-списка проглатывает искомую строку между
редкими опросами; `settings_screen.tap_display_mode`/TC-093,
`RUN-20260803-2012`) и AT-BUG-080 (якорь «присутствует» уже обрезанным
кромкой вьюпорта — сосед по строке, например кнопка «Clear…» рядом с «Clear
all ratings» или Switch тумблера, ещё вне дерева; `settings_screen.
open_clear_all_dialog`/TC-004, `RUN-20260816-1831`).

Фейковый driver держит ФЕЙКОВЫЕ часы (`_FakeClock`, подставлены вместо
`framework.core.waits.time` — единственное место, где `swipe_to_text` реально
ждёт: `poll_for`), а не спит по-настоящему — искомый текст «видим» только в
заданном окне фейкового времени (`visible_windows`), симулируя проскок между
опросами под нагрузкой. Проверяет:

1. Проскок ловится: искомый текст «виден» только в узком окне фейкового
   времени МЕЖДУ дискретными моментами, когда старый алгоритм (один снимок
   сразу после `driver.swipe`, `is_present(timeout=1)`) успевал бы проверить —
   новый алгоритм (несколько коротких свайпов + поллинг всего settle-окна
   после каждого, `poll_for`) эту строку ловит.
2. Диагностика различает «конец списка» (отпечаток видимых текстов не
   изменился после свайпа) от «список ещё двигался» (лимит `max_swipes`
   исчерпан, но список не уткнулся) — `screen.last_swipe_diagnostic`.
3. Строка, видимая сразу (без нужды свайпать) — `swipe_to_text` возвращает
   `True` без единого вызова `driver.swipe`.

4. **AT-BUG-080:** якорь «присутствует» СРАЗУ (та же ветка `is_present`, что
   сценарий (3)), но его bounds обрезаны кромкой вьюпорта на 9px (симулирует
   `_FakeClippingSwipeDriver`, реальная геометрия падения TC-004,
   `RUN-20260816-1831`) — `swipe_to_text` обязан ДОВЕСТИ строку доп.
   свайпом(ами) в том же направлении, пока bounds не окажутся внутри
   вьюпорта с запасом (`SWIPE_ANCHOR_MARGIN_PX`), а не вернуть `True` сразу
   на обрезанном состоянии (иначе сосед по строке — кнопка/тумблер — рискует
   остаться вне дерева, TC-004/TC-119/TC-129/TC-181/TC-188/TC-015/TC-252).

Красная проба (AT-BUG-048, DoD): этот же файл, прогнанный против
ДОКОММИТНОЙ версии `base_screen.py`/`waits.py` (`git stash` — временно снимает
только правки этих двух ОТСЛЕЖИВАЕМЫХ файлов, сам этот новый файл не
отслеживается и не попадает в stash), падает на сценарии (1): фейковые часы
там не продвигаются вовсе (старый код ждёт РЕАЛЬНЫМ `time.sleep` через
`selenium.webdriver.support.wait`, который эта проба не патчит), поэтому
`find_elements` всегда видит фейковое время `0` — вне окна видимости — и
`swipe_to_text` детерминированно возвращает `False` при существующей строке
(дословный вывод обоих прогонов — в отчёте test-maintainer, не в этом файле).

Красная проба (AT-BUG-080, DoD): против ДОКОММИТНОЙ версии `base_screen.py`
(до этого фикса) сценарий (4) падает на утверждении «был хотя бы один
ДОПОЛНИТЕЛЬНЫЙ `driver.swipe`» — старый `_swipe_search` объявлял успех сразу
по присутствию (`if self.is_present(loc, timeout=2): return True, ""`, без
проверки bounds/вьюпорта вовсе), НИ ОДНОГО доп. свайпа не делал вне зависимости
от геометрии — `driver.swipe_calls` оставался пуст. Проверяется НАБЛЮДАЕМОЕ
поведение (число вызовов `driver.swipe`), а не внутренние методы напрямую —
устойчиво к тому, что сам фикс добавляет НОВЫЕ методы (`_anchor_clipped_by_
viewport`/`_settle_clipped_anchor`), которых в доскоммитном коде нет вовсе.

Не требует устройства/эмулятора. Переопределяет session-scoped autouse-фикстуру
`_ensure_app_installed` из `conftest.py` (в духе `test_navigate_timeout_unit.py`,
AT-BUG-025) — та иначе дёрнула бы `adb pm list packages` при сборе тестов.

Rework (критик-вход, 4 блокера, живые пробы) добавил 3 device-free пробы:
- Б3 (`test_swipe_to_text_does_not_nudge_anchor_at_opposite_edge`/
  `test_swipe_up_to_text_does_not_nudge_anchor_at_opposite_edge`): якорь,
  ЦЕЛИКОМ видимый у кромки, ПРОТИВОПОЛОЖНОЙ направлению поиска, не должен
  довозиться доп. свайпом — регрессия, которую критик воспроизвёл живым
  пробой (`_anchor_clipped_by_viewport` без учёта направления проверяла ОБЕ
  кромки и выводила уже видимую строку из дерева).
- Б2 (`test_find_row_sibling_raises_instead_of_wrong_row`): `find_row_sibling`
  с известными bounds якоря, но БЕЗ ни одного own-row кандидата, обязана
  честно упасть `AssertionError`, а не молча вернуть `candidates[0]` (узел
  ЧУЖОГО ряда — критик воспроизвёл `DELETE-OF-ANOTHER-ROW`).
"""
from __future__ import annotations

import allure
import pytest

from framework.core import waits
from framework.screens import base_screen
from framework.screens.base_screen import BaseScreen


@pytest.fixture(scope="session", autouse=True)
def _ensure_app_installed():
    """Переопределяет device-фикстуру conftest.py (см. докстринг модуля) — эта
    проба чисто локальная, устройство не трогаем."""
    yield


class _FakeClock:
    """Подставляется вместо `framework.core.waits.time` — `poll_for`
    (единственное место реального ожидания в `swipe_to_text`) продвигает эти
    часы через `.sleep()`, а не спит по-настоящему."""

    def __init__(self) -> None:
        self.now = 0.0

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class _FakeElement:
    def __init__(self, text: str) -> None:
        self._text = text

    def get_attribute(self, name: str):
        return self._text if name == "text" else None


class _FakeSwipeDriver:
    """Минимальный фейк Appium-драйвера для `swipe_to_text`/`swipe_up_to_text`.

    `visible_windows` — список `(start, end)` фейкового времени, когда целевой
    текст присутствует в дереве (симулирует проскок вьюпорта). `fingerprint_states`
    — последовательность "снимков" видимого списка для каждого ПОСЛЕДОВАТЕЛЬНОГО
    вызова отпечатка (`_scroll_fingerprint`, локатор `textMatches`); индекс
    зажат на последнем элементе — исчерпание списка симулирует «список
    уткнулся в конец» (отпечаток перестаёт меняться)."""

    def __init__(self, clock: _FakeClock, target_text: str,
                visible_windows: list[tuple[float, float]],
                fingerprint_states: list[str]) -> None:
        self.clock = clock
        self.target_text = target_text
        self.visible_windows = visible_windows
        self.fingerprint_states = fingerprint_states
        self._fp_call_n = 0
        self.current_context = "NATIVE_APP"
        self.swipe_calls: list[tuple[int, int, int]] = []

    def get_window_size(self):
        return {"width": 1080, "height": 2400}

    def swipe(self, x, y1, x2, y2, duration_ms):
        del x, x2
        self.swipe_calls.append((y1, y2, duration_ms))

    def find_elements(self, by, value):
        del by
        if "textMatches" in value:
            idx = min(self._fp_call_n, len(self.fingerprint_states) - 1)
            self._fp_call_n += 1
            return [_FakeElement(self.fingerprint_states[idx])]
        if f'text("{self.target_text}")' in value:
            now = self.clock.time()
            if any(start <= now <= end for start, end in self.visible_windows):
                return [_FakeElement(self.target_text)]
            return []
        return []


@pytest.fixture(autouse=True)
def _fake_clock(monkeypatch):
    """Подставляет фейковые часы вместо `framework.core.waits.time` (единственное
    место реального ожидания внутри `swipe_to_text`/`swipe_up_to_text` —
    `poll_for`) и делает начальную проверку `is_present(timeout=2)` мгновенной
    (`_probe_present`, без реального ожидания) — иначе тест ждал бы РЕАЛЬНЫЕ
    секунды на каждом сценарии без всякой пользы (сам `is_present` не под
    пробой; проверяется алгоритм свайп-поиска)."""
    clock = _FakeClock()
    monkeypatch.setattr(waits, "time", clock)
    monkeypatch.setattr(
        base_screen.BaseScreen, "is_present",
        lambda self, locator, timeout=5: self._probe_present(locator),
    )
    return clock


@pytest.mark.p1
@allure.id("AT-BUG-048-swipe-to-text-catches-fling-flyby")
@allure.title("Проба: swipe_to_text ловит строку, проскакивающую вьюпорт между редкими опросами (fling-инерция, AT-BUG-048)")
def test_swipe_to_text_catches_narrow_visibility_window(_fake_clock):
    # Given строка «видна» только в узком окне фейкового времени (симулирует
    # проскок вьюпорта под инерцией) — список «двигается» (отпечаток меняется
    # на каждый вызов, until index exhausted)
    driver = _FakeSwipeDriver(
        clock=_fake_clock,
        target_text="Display mode",
        visible_windows=[(2.0, 2.5)],
        fingerprint_states=[f"state-{i}" for i in range(10)],
    )
    screen = BaseScreen(driver)

    # When ищем строку свайпами вниз
    found = screen.swipe_to_text("Display mode")

    # Then строка поймана (не проскочила незамеченной), несмотря на узкое окно
    # видимости — settle-поллинг после каждого короткого свайпа перекрывает
    # весь диапазон фейкового времени, а не один снимок сразу после возврата
    assert found is True, (
        f"swipe_to_text не поймал строку в узком окне видимости "
        f"{driver.visible_windows} (AT-BUG-048 регресс); "
        f"diagnostic={screen.last_swipe_diagnostic!r}, swipes={driver.swipe_calls}"
    )
    assert screen.last_swipe_diagnostic == "", (
        f"диагностика обязана быть пустой при успехе: {screen.last_swipe_diagnostic!r}"
    )
    # Свайп реально понадобился (окно не в t=0) — не искусственный "already visible"
    assert driver.swipe_calls, "сценарий должен был потребовать хотя бы один свайп"


@pytest.mark.p2
@allure.id("AT-BUG-048-swipe-to-text-no-swipe-when-already-visible")
@allure.title("Проба: swipe_to_text не свайпает, если строка уже видна (без изменений поведения)")
def test_swipe_to_text_returns_true_without_swiping_when_already_visible():
    # Given строка видна с самого начала (окно покрывает t=0)
    driver = _FakeSwipeDriver(
        clock=_FakeClock(), target_text="Theme",
        visible_windows=[(0.0, 999.0)], fingerprint_states=["state"],
    )
    screen = BaseScreen(driver)

    found = screen.swipe_to_text("Theme")

    assert found is True
    assert driver.swipe_calls == [], (
        f"строка уже видна — свайп не должен был понадобиться, "
        f"но были вызовы: {driver.swipe_calls}"
    )


@pytest.mark.p2
@allure.id("AT-BUG-048-swipe-to-text-diagnoses-end-of-list")
@allure.title("Проба: swipe_to_text диагностирует «конец списка» (отпечаток не изменился), отличая его от «строки нет»")
def test_swipe_to_text_diagnoses_end_of_list_distinctly():
    # Given строки не будет НИКОГДА, а отпечаток видимого списка перестаёт
    # меняться после второго свайпа (список физически уткнулся в низ)
    driver = _FakeSwipeDriver(
        clock=_FakeClock(), target_text="Never Rendered Label",
        visible_windows=[],
        fingerprint_states=["top", "middle", "bottom", "bottom", "bottom"],
    )
    screen = BaseScreen(driver)

    found = screen.swipe_to_text("Never Rendered Label")

    assert found is False
    assert "КОНЕЦ СПИСКА" in screen.last_swipe_diagnostic, (
        f"диагностика обязана называть «конец списка» при неизменном "
        f"отпечатке, получили: {screen.last_swipe_diagnostic!r}"
    )
    # НЕ должна была потратить весь бюджет max_swipes=8 — детекция конца
    # обязана оборвать цикл раньше (иначе диагностика бесполезна на практике)
    assert len(driver.swipe_calls) < 8 * 3, (
        f"детекция конца списка не оборвала цикл раньше лимита: "
        f"{len(driver.swipe_calls)} свайпов"
    )


@pytest.mark.p2
@allure.id("AT-BUG-048-swipe-to-text-diagnoses-still-scrolling-not-found")
@allure.title("Проба: swipe_to_text отличает «список ещё двигался, лимит исчерпан» от «конец списка»")
def test_swipe_to_text_diagnoses_still_scrolling_when_limit_exhausted():
    # Given строки нет, но список ПРОДОЛЖАЕТ показывать новый контент на
    # каждом свайпе до самого исчерпания max_swipes (отпечаток всегда новый)
    driver = _FakeSwipeDriver(
        clock=_FakeClock(), target_text="Never Rendered Label",
        visible_windows=[],
        fingerprint_states=[f"state-{i}" for i in range(64)],
    )
    screen = BaseScreen(driver)

    found = screen.swipe_to_text("Never Rendered Label", max_swipes=4)

    assert found is False
    assert "НЕ НАЙДЕНА" in screen.last_swipe_diagnostic and "список ещё двигался" in screen.last_swipe_diagnostic, (
        f"диагностика обязана называть «список ещё двигался» (лимит "
        f"исчерпан, конец не достигнут), получили: {screen.last_swipe_diagnostic!r}"
    )
    assert "КОНЕЦ СПИСКА" not in screen.last_swipe_diagnostic


@pytest.mark.p2
@allure.id("AT-BUG-048-swipe-up-to-text-shares-fling-fix")
@allure.title("Проба: swipe_up_to_text (симметричный swipe_to_text) тоже ловит проскок — тот же _swipe_search")
def test_swipe_up_to_text_catches_narrow_visibility_window(_fake_clock):
    # Given то же узкое окно видимости, что в основном сценарии — проверяет,
    # что фикс получил и swipe_up_to_text (симметрично, AT-BUG-048 «класс, не
    # экземпляр»), не только swipe_to_text
    driver = _FakeSwipeDriver(
        clock=_fake_clock, target_text="Reader",
        visible_windows=[(2.0, 2.5)],
        fingerprint_states=[f"state-{i}" for i in range(10)],
    )
    screen = BaseScreen(driver)

    found = screen.swipe_up_to_text("Reader")

    assert found is True, (
        f"swipe_up_to_text не поймал строку в узком окне видимости "
        f"(AT-BUG-048, симметричный дефект); swipes={driver.swipe_calls}"
    )
    # Направление свайпа — вверх (y1 < y2, в отличие от swipe_to_text)
    assert driver.swipe_calls, "сценарий должен был потребовать хотя бы один свайп"
    first_y1, first_y2, _ = driver.swipe_calls[0]
    assert first_y1 < first_y2, (
        f"swipe_up_to_text обязан свайпать СНИЗУ ВВЕРХ (y1<y2), получили "
        f"y1={first_y1}, y2={first_y2}"
    )


# --- AT-BUG-080: якорь присутствует, но обрезан кромкой вьюпорта ---

class _FakeBoundsElement:
    """Симметрично `_FakeElement`, но несёт ещё и `bounds` (UIAutomator-формат
    `"[x1,y1][x2,y2]"`) — `_anchor_clipped_by_viewport`/`_settle_clipped_anchor`
    читают именно этот атрибут (AT-BUG-080)."""

    def __init__(self, text: str, bounds: str) -> None:
        self._text = text
        self._bounds = bounds

    def get_attribute(self, name: str):
        if name == "text":
            return self._text
        if name == "bounds":
            return self._bounds
        return None


class _FakeClippingSwipeDriver:
    """Симулирует AT-BUG-080: якорный текст «присутствует» СРАЗУ (ветка
    `is_present(loc, timeout=2)` в `_swipe_search`, без нужды в основном
    раунде свайпов), но его bounds обрезаны кромкой вьюпорта на 9px — реальная
    геометрия падения TC-004 (`RUN-20260816-1831`: вьюпорт `[0,296][1080,2064]`,
    якорь `[42,2055][293,2064]`). Ровно после `nudges_needed` ДОПОЛНИТЕЛЬНЫХ
    вызовов `driver.swipe` (доводящих свайпов) bounds «доезжают» внутрь
    вьюпорта с запасом — симулирует физическое доведение строки в кадр.

    Отпечаток списка (`textMatches`) меняется на каждый вызов — свайп «не
    утыкается в конец» раньше времени, доводящий цикл не обрывается
    диагностикой «КОНЕЦ СПИСКА» до того, как якорь успеет settle'иться."""

    VIEWPORT_BOUNDS = "[0,296][1080,2064]"

    def __init__(self, clock: _FakeClock, target_text: str, nudges_needed: int) -> None:
        self.clock = clock
        self.target_text = target_text
        self.nudges_needed = nudges_needed
        self.current_context = "NATIVE_APP"
        self.swipe_calls: list[tuple[int, int, int]] = []

    def get_window_size(self):
        return {"width": 1080, "height": 2400}

    def swipe(self, x, y1, x2, y2, duration_ms):
        del x, x2
        self.swipe_calls.append((y1, y2, duration_ms))

    def find_elements(self, by, value):
        del by
        if "scrollable(true)" in value:
            return [_FakeBoundsElement("", self.VIEWPORT_BOUNDS)]
        if "textMatches" in value:
            return [_FakeBoundsElement(f"fp-{len(self.swipe_calls)}", "")]
        if f'text("{self.target_text}")' in value:
            settled = len(self.swipe_calls) >= self.nudges_needed
            bottom = 2064 - 200 if settled else 2064 - 9  # settled: щедрый запас; clipped: 9px, как в падении
            return [_FakeBoundsElement(self.target_text, f"[42,{bottom - 9}][293,{bottom}]")]
        return []


@pytest.mark.p1
@allure.id("AT-BUG-080-swipe-to-text-settles-clipped-anchor")
@allure.title("Проба: swipe_to_text доводит якорь, обрезанный кромкой вьюпорта, доп. свайпом (AT-BUG-080)")
def test_swipe_to_text_settles_anchor_clipped_by_viewport_edge(_fake_clock):
    # Given якорь «Clear all ratings» присутствует СРАЗУ (без основного раунда
    # свайпов), но его bounds обрезаны кромкой вьюпорта на 9px — ровно
    # геометрия падения TC-004 (RUN-20260816-1831); settle наступает после
    # ОДНОГО доп. свайпа
    driver = _FakeClippingSwipeDriver(
        clock=_fake_clock, target_text="Clear all ratings", nudges_needed=1,
    )
    screen = BaseScreen(driver)

    # When ищем строку
    found = screen.swipe_to_text("Clear all ratings")

    # Then строка найдена...
    assert found is True, (
        f"swipe_to_text не нашёл присутствующий якорь; "
        f"diagnostic={screen.last_swipe_diagnostic!r}"
    )
    # ...НО старый код («is_present» => немедленный return True без проверки
    # bounds) не сделал бы НИ ОДНОГО вызова driver.swipe в этом сценарии
    # (якорь виден сразу, основной раунд не нужен) — красная проба AT-BUG-080:
    # против докоммитной версии base_screen.py это утверждение падает
    # (swipe_calls == []).
    assert driver.swipe_calls, (
        "swipe_to_text не довёл обрезанный кромкой якорь ни одним доп. "
        "свайпом (AT-BUG-080 регресс) — старый код объявляет успех по "
        "голому присутствию, не проверяя bounds/вьюпорт"
    )
    # Довод остановился, как только якорь settle'ился (не исчерпал весь
    # бюджет SWIPE_NUDGE_MAX_ATTEMPTS=3) — детекция settle обязана обрывать
    # цикл раньше лимита, иначе она бесполезна на практике
    assert len(driver.swipe_calls) == 1, (
        f"довод не остановился сразу по settle, лишние свайпы: {driver.swipe_calls}"
    )
    # Направление довода — то же, что основной раунд swipe_to_text (вниз, y1>y2)
    nudge_y1, nudge_y2, _ = driver.swipe_calls[0]
    assert nudge_y1 > nudge_y2, (
        f"доводящий свайп обязан идти в том же направлении, что основной "
        f"раунд swipe_to_text (вниз, y1>y2), получили y1={nudge_y1}, y2={nudge_y2}"
    )


class _FakeOppositeEdgeDriver:
    """Симметрично `_FakeClippingSwipeDriver`, но якорь ЦЕЛИКОМ виден у
    кромки, ПРОТИВОПОЛОЖНОЙ направлению текущего поиска (AT-BUG-080 Б3 —
    критик воспроизвёл живой пробой регрессию: `_anchor_clipped_by_viewport`
    без учёта направления ложно считал такой якорь обрезанным и довозил его
    ЕЩЁ ДАЛЬШЕ в направлении поиска, выводя из дерева уже видимую строку).
    Bounds якоря КОНСТАНТНЫ (не зависят от числа свайпов) — тест ловит любой
    лишний доп. свайп, не только первый."""

    VIEWPORT_BOUNDS = "[0,296][1080,2064]"

    def __init__(self, clock: _FakeClock, target_text: str, anchor_bounds: str) -> None:
        self.clock = clock
        self.target_text = target_text
        self.anchor_bounds = anchor_bounds
        self.current_context = "NATIVE_APP"
        self.swipe_calls: list[tuple[int, int, int]] = []

    def get_window_size(self):
        return {"width": 1080, "height": 2400}

    def swipe(self, x, y1, x2, y2, duration_ms):
        del x, x2
        self.swipe_calls.append((y1, y2, duration_ms))

    def find_elements(self, by, value):
        del by
        if "scrollable(true)" in value:
            return [_FakeBoundsElement("", self.VIEWPORT_BOUNDS)]
        if "textMatches" in value:
            return [_FakeBoundsElement("fp", "")]
        if f'text("{self.target_text}")' in value:
            return [_FakeBoundsElement(self.target_text, self.anchor_bounds)]
        return []


@pytest.mark.p1
@allure.id("AT-BUG-080-swipe-to-text-no-nudge-at-opposite-edge")
@allure.title("Проба: swipe_to_text НЕ довозит якорь, целиком видимый у ВЕРХНЕЙ (противоположной направлению поиска) кромки (AT-BUG-080 Б3)")
def test_swipe_to_text_does_not_nudge_anchor_at_opposite_edge(_fake_clock):
    # Given якорь целиком внутри вьюпорта у ВЕРХНЕЙ кромки (bounds top=300,
    # в пределах SWIPE_ANCHOR_MARGIN_PX=24 от v_top=296), с щедрым запасом от
    # НИЖНЕЙ (bottom=340, далеко от v_bottom=2064) — swipe_to_text ищет ВНИЗ
    # (check_bottom_edge=True), обрезка сверху этого поиска не касается.
    driver = _FakeOppositeEdgeDriver(
        clock=_fake_clock, target_text="Theme", anchor_bounds="[42,300][293,340]",
    )
    screen = BaseScreen(driver)

    # When ищем строку (якорь виден сразу, без нужды в основном раунде свайпов)
    found = screen.swipe_to_text("Theme")

    # Then строка найдена, и НИ ОДНОГО доп. свайпа не понадобилось — довод в
    # направлении поиска (вниз) увёз бы уже видимую строку ЕЩЁ ДАЛЬШЕ от
    # центра и вывел бы её из дерева (регрессия Б3, докоммитная версия этого
    # фикса красная здесь: `_anchor_clipped_by_viewport` без direction-фильтра
    # проверяет обе кромки и ложно считает якорь обрезанным сверху).
    assert found is True
    assert driver.swipe_calls == [], (
        "swipe_to_text довёз якорь, целиком видимый у противоположной "
        f"(верхней) кромки — регрессия AT-BUG-080 Б3: {driver.swipe_calls}"
    )


@pytest.mark.p1
@allure.id("AT-BUG-080-swipe-up-to-text-no-nudge-at-opposite-edge")
@allure.title("Проба: swipe_up_to_text НЕ довозит якорь, целиком видимый у НИЖНЕЙ (противоположной направлению поиска) кромки (AT-BUG-080 Б3)")
def test_swipe_up_to_text_does_not_nudge_anchor_at_opposite_edge(_fake_clock):
    # Given якорь целиком внутри вьюпорта у НИЖНЕЙ кромки (bounds
    # bottom=2050, в пределах margin от v_bottom=2064), с щедрым запасом от
    # ВЕРХНЕЙ (top=2000, далеко от v_top=296) — swipe_up_to_text ищет ВВЕРХ
    # (check_bottom_edge=False), обрезка снизу этого поиска не касается.
    driver = _FakeOppositeEdgeDriver(
        clock=_fake_clock, target_text="Reader", anchor_bounds="[42,2000][293,2050]",
    )
    screen = BaseScreen(driver)

    found = screen.swipe_up_to_text("Reader")

    assert found is True
    assert driver.swipe_calls == [], (
        "swipe_up_to_text довёз якорь, целиком видимый у противоположной "
        f"(нижней) кромки — регрессия AT-BUG-080 Б3: {driver.swipe_calls}"
    )


@pytest.mark.p2
@allure.id("AT-BUG-080-swipe-to-text-settle-stops-at-list-end")
@allure.title("Проба: доведение обрезанного якоря обрывается, если список физически уткнулся (не бесконечный цикл)")
def test_swipe_to_text_settle_gives_up_when_list_stuck(_fake_clock):
    # Given якорь ВСЕГДА обрезан, а отпечаток списка НЕ меняется (список
    # физически уткнулся в конец, дальше сдвинуть некуда) — переопределяем
    # find_elements,
    # чтобы textMatches всегда возвращал один и тот же снимок после первого
    # доводящего свайпа
    class _StuckDriver(_FakeClippingSwipeDriver):
        def find_elements(self, by, value):
            del by
            if "scrollable(true)" in value:
                return [_FakeBoundsElement("", self.VIEWPORT_BOUNDS)]
            if "textMatches" in value:
                return [_FakeBoundsElement("stuck", "")]
            if f'text("{self.target_text}")' in value:
                return [_FakeBoundsElement(self.target_text, "[42,2055][293,2064]")]
            return []

    stuck_driver = _StuckDriver(clock=_fake_clock, target_text="Clear all ratings", nudges_needed=999)
    screen = BaseScreen(stuck_driver)

    found = screen.swipe_to_text("Clear all ratings")

    # Then якорь всё ещё считается найденным (был присутствующим с самого
    # начала) — довод не блокирует тест бесконечно, обрывается по неизменному
    # отпечатку СРАЗУ на первой попытке (не тратит весь бюджет из 3 попыток)
    assert found is True
    assert len(stuck_driver.swipe_calls) == 1, (
        f"довод обязан остановиться на первой попытке, раз отпечаток не "
        f"меняется (список физически уткнулся), получили: {stuck_driver.swipe_calls}"
    )


# --- AT-BUG-080 Б2: find_row_sibling не возвращает узел ЧУЖОГО ряда ---

class _FakeRowSiblingDriver:
    """Симулирует AT-BUG-080 Б2 (критик воспроизвёл живым пробой): якорь
    найден с ИЗВЕСТНЫМИ bounds, xpath-кандидаты `[xpath_predicate]` после него
    ЕСТЬ в дереве, но НИ ОДИН не делит с якорем ряд (все принадлежат ЧУЖОЙ,
    соседней строке ниже) — свой узел строки физически никогда не появляется
    (симулирует «свой узел ещё вне дерева», ИМЕННО тот случай, ради которого
    `find_row_sibling` написана). До фикса Б2 функция молча возвращала
    `candidates[0]` — узел ЧУЖОГО ряда (критик: `DELETE-OF-ANOTHER-ROW`)."""

    def __init__(self, anchor_text: str, anchor_bounds: str, wrong_row_bounds: str) -> None:
        self.anchor_text = anchor_text
        self.anchor_bounds = anchor_bounds
        self.wrong_row_bounds = wrong_row_bounds
        self.current_context = "NATIVE_APP"

    def find_elements(self, by, value):
        del by
        if f'text("{self.anchor_text}")' in value:
            return [_FakeBoundsElement(self.anchor_text, self.anchor_bounds)]
        if "following::" in value:
            # Один-единственный кандидат в дереве — узел СОСЕДНЕЙ (следующей)
            # строки, не своей.
            return [_FakeBoundsElement("", self.wrong_row_bounds)]
        return []


@pytest.mark.p1
@allure.id("AT-BUG-080-find-row-sibling-does-not-return-wrong-row")
@allure.title("Проба: find_row_sibling НЕ возвращает кандидата ЧУЖОГО ряда, если bounds якоря известны, но свой узел так и не появился (AT-BUG-080 Б2)")
def test_find_row_sibling_raises_instead_of_wrong_row(_fake_clock):
    # Given якорь «Auto-download favorite works» с известными bounds одной
    # строки (y: 1000-1040), единственный xpath-кандидат в дереве принадлежит
    # ЯВНО ДРУГОЙ строке (y: 1200-1240, соседняя строка ниже, Y-диапазоны не
    # пересекаются) — свой Switch этой строки так и не появляется за весь
    # бюджет (маленький timeout=0.5 на фейковых часах — тест не ждёт реальных
    # секунд).
    driver = _FakeRowSiblingDriver(
        anchor_text="Auto-download favorite works",
        anchor_bounds="[42,1000][900,1040]",
        wrong_row_bounds="[876,1200][1038,1240]",
    )
    screen = BaseScreen(driver)

    # When/Then ищем checkable-сосед строки — функция ОБЯЗАНА честно упасть,
    # а не молча вернуть чужой ряд.
    with pytest.raises(AssertionError, match="СВОЕЙ строки"):
        screen.find_row_sibling(
            "Auto-download favorite works", '@checkable="true"', timeout=0.5,
        )
