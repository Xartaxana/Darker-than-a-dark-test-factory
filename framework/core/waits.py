"""Явные ожидания. Прямой sleep в тестах/шагах/экранах запрещён конвенцией —
всё ожидание проходит здесь (условие + таймаут из config).
"""
from __future__ import annotations

import time
from typing import Callable, TypeVar

from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    WebDriverException,
)
from selenium.webdriver.support.ui import WebDriverWait

from framework.config import settings

T = TypeVar("T")

_IGNORED = (NoSuchElementException, StaleElementReferenceException, WebDriverException)


def wait_until(driver, condition: Callable[[object], T], timeout: int | None = None,
               message: str = "") -> T:
    timeout = timeout if timeout is not None else settings.DEFAULT_TIMEOUT
    return WebDriverWait(driver, timeout, poll_frequency=0.4,
                         ignored_exceptions=_IGNORED).until(condition, message)


def wait_for(predicate: Callable[[], bool], timeout: int | None = None,
             message: str = "condition not met") -> None:
    """Ожидание произвольного предиката (например, состояния данных через adb)."""
    timeout = timeout if timeout is not None else settings.DEFAULT_TIMEOUT
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            if predicate():
                return
        except Exception as e:  # noqa: BLE001
            last = e
        time.sleep(0.4)
    raise TimeoutError(f"{message} (after {timeout}s){f'; last error: {last}' if last else ''}")


def poll_for(predicate: Callable[[], bool], timeout: float, interval: float = 0.4) -> bool:
    """Опрашивает `predicate()` в течение `timeout` секунд с шагом `interval`,
    возвращает `True` при ПЕРВОМ успехе. В отличие от `wait_for`, НЕ поднимает
    исключение при неуспехе — возвращает `False`, когда бюджет исчерпан
    (вызывающий код сам решает, что делать дальше, например попробовать
    следующий свайп — `BaseScreen.swipe_to_text`, AT-BUG-048). Первый опрос —
    сразу (t=0), без начальной паузы (симметрично `assert_holds_for`)."""
    deadline = time.time() + timeout
    while True:
        try:
            if predicate():
                return True
        except Exception:  # noqa: BLE001
            pass
        if time.time() >= deadline:
            return False
        time.sleep(interval)


def assert_holds_for(check: Callable[[], bool], budget_s: float, interval_s: float,
                      msg: str = "condition violated during budget") -> None:
    """Опрашивает `check()` ВЕСЬ бюджет `budget_s` (шаг `interval_s`), падает
    `AssertionError` при ПЕРВОМ нарушении — обобщение паттерна «негатив держится
    весь бюджет», введённого для `assert_top_chrome_not_darkened`
    (`framework/steps/browser_steps.py`, tap-zone guard TC-119/122). Симметрично
    `wait_until`/`wait_for` (которые возвращаются при ПЕРВОМ True) — этот примитив
    для обратного случая: доказать, что условие НЕ нарушается НИ РАЗУ за всё
    окно, в котором мог бы случиться отложенный/анимированный эффект. Один
    ранний снимок (`check()` вызван один раз сразу после действия) не доказывает
    этого — эффект, пришедший позже первого снимка, но ещё в пределах бюджета,
    иначе бы проскочил незамеченным.

    `check` — либо возвращает `bool` (`False` -> `AssertionError(msg)`), либо
    сам поднимает `AssertionError` с более информативным сообщением (диагностика
    текущего замера) — оба варианта считаются нарушением.

    Первый опрос — сразу (t=0), без начальной паузы. Последний опрос выполняется
    РОВНО в момент достижения дедлайна включительно — граница бюджета: нарушение
    ИМЕННО на этом последнем опросе ловится; нарушение, случившееся уже ПОСЛЕ
    дедлайна (строго за пределами бюджета, когда опрос больше не выполняется),
    этим вызовом не наблюдается — это осознанная граница, не дефект (симметрично
    границе `budget_s` любого `MAX_*`-таймаута в проекте)."""
    deadline = time.time() + budget_s
    while True:
        assert check(), msg
        if time.time() >= deadline:
            return
        time.sleep(interval_s)


def poll_until_stable(read_fn: Callable[[], T], stable_reads: int = 2,
                       timeout: float = 2.0, interval: float = 0.2) -> tuple[T, bool]:
    """Опрашивает `read_fn()`, пока результат не совпадёт `stable_reads` раз
    ПОДРЯД, либо не истечёт `timeout` — обобщение приёма «фингерпринт
    стабилизировался», уже проверенного на `BaseScreen._scroll_fingerprint`/
    `_settle_clipped_anchor` (AT-BUG-048/080): settle без выделенного UI-
    сигнала «анимация/переход завершены» (AT-BUG-082 Б2/Б3 критик-вход —
    `LibraryScreen.open_tab`, `HorizontalPager`-переход между вкладками, где
    нет надёжного `selected`-атрибута для опроса).

    Возвращает `(last_value, converged)` — `last_value` ПОСЛЕДНЕЕ прочитанное
    значение независимо от исхода (best-effort settle, симметрично
    `_settle_clipped_anchor`: неуспевшая устаканиться анимация не блокирует
    вызывающий код, а отдаёт последнее известное состояние), `converged`
    различает «реально стабилизировалось» от «бюджет истёк раньше, чем набралось
    `stable_reads` подряд одинаковых чтений» — вызывающий код решает, логировать
    ли диагностику незавершённого settle (AT-BUG-082 Б4: проглоченное
    незавершённое ожидание не должно быть немым).

    Первый опрос — сразу (t=0, streak=1); каждый следующий — через `interval`.
    Совпадающие подряд идущие чтения увеличивают streak, несовпадение сбрасывает
    его на 1 (не на 0 — сам текущий отличающийся отсчёт уже участвует в НОВОЙ
    серии).

    **ESC-035 (do-while, критик-вход AT-BUG-082 round2 + Lead-разбор
    2026-08-18T10:25Z):** дедлайн проверяется ПОСЛЕ чтения, не до —
    гарантирует МИНИМУМ `stable_reads` чтений НЕЗАВИСИМО от wall-clock
    бюджета (включая `timeout=0`), для ЛЮБОГО `stable_reads`, не только
    дефолтного `2`. До этого фикса `while streak < stable_reads and
    time.time() < deadline` проверял дедлайн ДО повторного чтения: если ОДНО
    чтение `read_fn()` стоит дороже ВСЕГО `timeout`, тело цикла не
    исполнялось НИ РАЗУ после первого чтения — второе чтение никогда не
    происходило, `streak` навсегда оставался 1 < `stable_reads` (по
    умолчанию 2) — `converged` был СТРУКТУРНО недостижим, а не просто
    маловероятен.

    **Критик-вход round3 (2026-08-19, живой пробой, параметризованный по
    `stable_reads`):** ПЕРВАЯ редакция этого фикса чинила ТОЛЬКО экземпляр
    (`stable_reads<=2`), не класс — дедлайн-`break` стоял внутри тела БЕЗ
    учёта того, сколько чтений реально сделано, поэтому при `stable_reads=3`
    цикл всё ещё обрывался после 2 чтений (`streak<3`, но `time.time() >=
    deadline` уже истинно даже на дешёвом/быстром прогоне) — `converged`
    оставался структурно недостижим при `stable_reads>=3`, ровно тот же
    класс дефекта, который эта правка обязана была устранить целиком. Фикс
    ниже считает `reads` (число выполненных чтений) ОТДЕЛЬНО от `streak` —
    дедлайн-`break` разрешён ТОЛЬКО когда `reads >= stable_reads`, то есть
    после того, как минимум гарантированно выполнен, для ЛЮБОГО
    `stable_reads` (см. `test_poll_until_stable_unit.py`, параметризация по
    `stable_reads in (2, 3, 4)` — регресс-пин на ИМЕННО этот повторный
    дефект).

    Худший случай СТОИМОСТИ теперь явный:
    `stable_reads × read_cost` (плюс `(stable_reads - 1) × interval` сна
    между чтениями) — это НИЖНЯЯ граница времени вызова, `timeout` её НЕ
    отменяет, только ограничивает попытки ПОСЛЕ первых `stable_reads`
    чтений, если значения продолжают отличаться. **Классовая норма
    (D-0043):** бюджет времени у settle-опроса (как `timeout` этого
    примитива, так и внешний таймаут вызывающего кода) обязан быть КРАТНО
    больше ЗАМЕРЕННОЙ стоимости одного `read_fn()` — не унаследованной «на
    веру» оценки. Ярлык стоимости чтения («дешёвый»/«дорогой») ОБЯЗАН
    перепроверяться живым замером при переносе `read_fn` в новый контекст
    вызова (другой экран, другая частота вызова) — не наследуется молча из
    исходного контекста, где он был измерен (см. `docs/08-external-
    architecture-review.md` §C6: ярлык «дешёвый» у `BaseScreen.
    _scroll_fingerprint`, истинный в контексте `_settle_clipped_anchor`
    (≤3 вызова на Settings), оказался ложным при переносе в
    `LibraryScreen._settle_tab_switch` — 1.99-3.51s/чтение на card-
    насыщенном Library, БЕЗ живой перепроверки при переносе)."""
    deadline = time.time() + timeout
    last = read_fn()
    reads = 1
    streak = 1
    while streak < stable_reads:
        time.sleep(interval)
        current = read_fn()
        reads += 1
        streak = streak + 1 if current == last else 1
        last = current
        if streak >= stable_reads:
            break
        # Дедлайн разрешает СДАТЬСЯ (перестать пытаться сойтись) только
        # ПОСЛЕ того, как минимум `stable_reads` чтений уже выполнен —
        # иначе (критик-вход round3) при `stable_reads>=3` цикл обрывался
        # раньше, чем успевал сделать столько чтений, и `converged` снова
        # становился структурно недостижим для этих значений `stable_reads`.
        if reads >= stable_reads and time.time() >= deadline:
            break
    return last, streak >= stable_reads
