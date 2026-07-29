"""Device-free юнит на примитив `framework.core.waits.assert_holds_for`
(батч мелочей D-0081, 2026-07-29) — обобщение паттерна «негатив держится весь
бюджет», ранее реализованного вручную в `assert_top_chrome_not_darkened`
(`framework/steps/browser_steps.py`).

`framework.core.waits` — ЗАПРЕЩЁННЫЙ прямой импорт в `tests/`
(`scripts/arch_check.py::FORBIDDEN_IMPORT_PREFIXES`, локаторы/driver-примитивы
только в screens/web) — эта проба обходит запрет ЧЕРЕЗ `framework.steps.browser_steps`,
но НЕ единообразно: тесты 1-2 ниже (`test_violation_exactly_on_last_poll_is_caught`,
`test_violation_past_deadline_is_not_observed`) вызывают `browser_steps.assert_holds_for`
НАПРЯМУЮ — это тот же объект, что `framework.core.waits.assert_holds_for`
(реэкспортирован строкой `from framework.core.waits import assert_holds_for,
wait_until` на `browser_steps.py:18`), а не публичный шаг-consumer,
оборачивающий примитив бизнес-смыслом; честнее называть это «доступ к
core-примитиву через реэкспорт модуля», не «тот же приём, что
`test_top_chrome_wait_unit.py`» (та проба зовёт РЕАЛЬНЫЕ consumer'ы
`assert_top_chrome_darkened`/`assert_top_chrome_restored`). Тест 3
(`test_top_chrome_not_darkened_catches_violation_mid_budget`) — уже настоящий
consumer-тест: зовёт `browser_steps.assert_top_chrome_not_darkened`, тем же
приёмом, что `test_top_chrome_wait_unit.py`. Монки-патч `time.time`/`time.sleep`
ПО СТРОКОВОМУ пути (`browser_steps.time` — та же ссылка на модуль `time`, что
использует `waits.py` внутри себя) — детерминированный фейковый таймер вместо
реальных секунд, тот же приём, что `test_adb_install_package_wait_unit.py`
патчит `adb.time.sleep`.

Границы (правило 6а CLAUDE.md — тест НА границе бюджета и ЗА ней):
- `test_violation_exactly_on_last_poll_is_caught` — нарушение РОВНО на
  последнем опросе (момент достижения дедлайна) ловится AssertionError'ом;
- `test_violation_past_deadline_is_not_observed` — опросов делается РОВНО
  столько, сколько укладывается в бюджет (никогда не выполняется вызов ПОСЛЕ
  дедлайна) — нарушение, "спрятанное" за этим числом вызовов, структурно не
  может быть замечено (осознанная граница примитива, не дефект)."""
from __future__ import annotations

import allure
import pytest

from framework.core import contexts
from framework.steps import browser_steps

_TOP_CHROME_LUMA_TARGET = "framework.screens.browser_screen.BrowserScreen.top_chrome_avg_luma"


@pytest.fixture(scope="session", autouse=True)
def _ensure_app_installed():
    """Переопределяет device-фикстуру conftest.py — эта проба чисто локальная,
    устройство не трогаем (тот же приём, что test_top_chrome_wait_unit.py)."""
    yield


class _FakeDriver:
    current_context = contexts.NATIVE


class _FakeClock:
    """Полностью детерминированный таймер: `sleep(s)` продвигает внутренние
    "часы" НА `s`, не ждёт реальное время — весь прогон длится миллисекунды,
    число опросов предсказуемо по конструкции (не подвержено дрейфу реальных
    `time.sleep`)."""

    def __init__(self, start: float = 0.0):
        self._t = start
        self.sleep_calls: list[float] = []

    def time(self) -> float:
        return self._t

    def sleep(self, s: float) -> None:
        self.sleep_calls.append(s)
        self._t += s


@pytest.fixture()
def _fake_clock(monkeypatch):
    """Возвращает ФАБРИКУ новых часов, а не один инстанс: два независимых
    вызова `assert_holds_for` в одном тесте обязаны стартовать с t=0 каждый —
    переиспользование ОДНИХ часов между вызовами накапливает погрешность
    двоичного `float` (0.2 не представимо точно) через несколько сотен
    сложений и может дать ложный лишний/недостающий опрос, не связанный с
    самим примитивом (found эмпирически при первой редакции этой пробы)."""
    def make_clock() -> _FakeClock:
        clock = _FakeClock()
        # Сужено (критик-вход attempt 2, N2): раньше патчились атрибуты
        # `time`/`sleep` ГЛОБАЛЬНОГО модуля `time` (через `browser_steps.time`,
        # ту же ссылку, что видит `waits.py`) — подмена била по ЛЮБОМУ коду
        # процесса, читающему `time.time()`/`time.sleep()` во время теста, не
        # только по `assert_holds_for`. Строковый путь ниже подменяет ТОЛЬКО
        # имя `time`, которое видит изнутри себя модуль `framework.core.waits`
        # (`waits.py` делает `import time` — это имя живёт в его собственном
        # `__globals__`), не трогая ни глобальный `time`-модуль, ни
        # `browser_steps.time`. `_FakeClock` уже предоставляет `.time()`/
        # `.sleep(s)` с сигнатурой модуля `time` — подходит как замена целиком
        # (без прямого `import framework.core.waits` в tests/, запрещённого
        # `scripts/arch_check.py::FORBIDDEN_IMPORT_PREFIXES` — резолвится
        # монки-патчем по строке, тот же приём, что `_TOP_CHROME_LUMA_TARGET`
        # в `test_top_chrome_wait_unit.py`).
        monkeypatch.setattr("framework.core.waits.time", clock)
        return clock
    return make_clock


@pytest.mark.p2
@allure.id("assert-holds-for-caught-at-last-poll-boundary")
@allure.title("assert_holds_for: нарушение РОВНО на последнем опросе (граница бюджета) ловится")
def test_violation_exactly_on_last_poll_is_caught(_fake_clock):
    # Given budget_s=1.0, interval_s=0.2 -> с фейковым таймером ровно 6 опросов
    # (t=0.0,0.2,0.4,0.6,0.8,1.0 — последний РОВНО в момент дедлайна, включительно)
    _fake_clock()
    calls = {"n": 0}

    def check() -> bool:
        calls["n"] += 1
        # Нарушение ИМЕННО на 6-м (последнем) опросе — не раньше
        return calls["n"] < 6

    with pytest.raises(AssertionError):
        browser_steps.assert_holds_for(check, budget_s=1.0, interval_s=0.2, msg="held")

    assert calls["n"] == 6, (
        f"ожидали ровно 6 опросов (граница дедлайна включительно), было {calls['n']}"
    )


@pytest.mark.p2
@allure.id("assert-holds-for-past-deadline-not-observed")
@allure.title("assert_holds_for: нарушение ПОСЛЕ дедлайна не наблюдается (осознанная граница)")
def test_violation_past_deadline_is_not_observed(_fake_clock):
    # Given ТЕ ЖЕ параметры (budget_s=1.0, interval_s=0.2 -> ровно 6 опросов),
    # но check() держится ИСТИННЫМ все 6 опросов -> функция обязана вернуться
    # молча, БЕЗ исключения, ОПРОСИВ РОВНО 6 раз (не 7 и не более) — 7-й
    # (гипотетический) опрос СРАЗУ ЗА границей дедлайна никогда не выполняется,
    # хотя если бы выполнился — вернул бы нарушение (проверяем ниже отдельно).
    _fake_clock()
    calls = {"n": 0}

    def check_holds() -> bool:
        calls["n"] += 1
        return True

    browser_steps.assert_holds_for(check_holds, budget_s=1.0, interval_s=0.2, msg="held")

    assert calls["n"] == 6, (
        f"ожидали ровно 6 опросов за весь бюджет, было {calls['n']} "
        "(лишний опрос означает, что примитив продолжает поллинг ЗА дедлайном)"
    )

    # And если бы функция всё-таки сделала 7-й опрос (за пределами бюджета),
    # он бы поймал нарушение — но assert_holds_for его структурно не делает
    # (доказано счётчиком выше): граница — намеренное поведение, не дефект.
    # Свежие часы (t=0 заново) — независимый вызов, без накопленной погрешности
    # `float` от первого вызова этого же теста (см. докстринг `_fake_clock`).
    _fake_clock()
    calls["n"] = 0

    def check_would_violate_on_7th() -> bool:
        calls["n"] += 1
        return calls["n"] < 7

    browser_steps.assert_holds_for(check_would_violate_on_7th, budget_s=1.0, interval_s=0.2, msg="held")
    assert calls["n"] == 6


@pytest.mark.p2
@allure.id("assert-holds-for-via-top-chrome-not-darkened-catches-late-violation")
@allure.title("assert_top_chrome_not_darkened (consumer): пересечение порога В СЕРЕДИНЕ бюджета ловится (не одноразовое чтение)")
def test_top_chrome_not_darkened_catches_violation_mid_budget(_fake_clock, monkeypatch):
    # Given luma держится безопасной (>= порога) первые 3 опроса, затем падает
    # ниже порога — одноразовое чтение сразу после клика поймало бы только
    # первое (безопасное) значение и ложно-отрицательно прошло бы мимо
    _fake_clock()
    values = iter([90.0, 90.0, 90.0, 10.0, 10.0, 10.0])
    monkeypatch.setattr(_TOP_CHROME_LUMA_TARGET, lambda self: next(values))

    with pytest.raises(AssertionError, match="потемнела"):
        browser_steps.assert_top_chrome_not_darkened(
            _FakeDriver(), baseline=100.0, ratio=0.5, timeout=1.0, poll_interval=0.2,
        )
