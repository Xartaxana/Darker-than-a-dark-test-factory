"""Device-free юнит-проба `BaseScreen.swipe_to_text`/`swipe_up_to_text` —
AT-BUG-048 (fling-инерция Compose-списка проглатывает искомую строку между
редкими опросами; `settings_screen.tap_display_mode`/TC-093,
`RUN-20260803-2012`).

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

Красная проба (AT-BUG-048, DoD): этот же файл, прогнанный против
ДОКОММИТНОЙ версии `base_screen.py`/`waits.py` (`git stash` — временно снимает
только правки этих двух ОТСЛЕЖИВАЕМЫХ файлов, сам этот новый файл не
отслеживается и не попадает в stash), падает на сценарии (1): фейковые часы
там не продвигаются вовсе (старый код ждёт РЕАЛЬНЫМ `time.sleep` через
`selenium.webdriver.support.wait`, который эта проба не патчит), поэтому
`find_elements` всегда видит фейковое время `0` — вне окна видимости — и
`swipe_to_text` детерминированно возвращает `False` при существующей строке
(дословный вывод обоих прогонов — в отчёте test-maintainer, не в этом файле).

Не требует устройства/эмулятора. Переопределяет session-scoped autouse-фикстуру
`_ensure_app_installed` из `conftest.py` (в духе `test_navigate_timeout_unit.py`,
AT-BUG-025) — та иначе дёрнула бы `adb pm list packages` при сборе тестов.
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
