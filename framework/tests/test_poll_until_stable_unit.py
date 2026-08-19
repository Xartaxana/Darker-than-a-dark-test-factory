"""Device-free юниты `framework.core.waits.poll_until_stable` — ESC-035
(`state/escalations.md`, AT-BUG-082 эскалация правила 6, РЕШЕНИЕ Lead
2026-08-18T10:25Z).

Дефект (`waits.py` до фикса): `while streak < stable_reads and time.time() <
deadline` проверял дедлайн ДО повторного чтения — если ОДНО чтение
`read_fn()` стоит дороже ВСЕГО `timeout`, тело цикла не исполнялось НИ РАЗУ
после первого чтения, второе чтение никогда не происходило, `streak`
навсегда оставался 1 < `stable_reads` (по умолчанию 2) — `converged` был
СТРУКТУРНО недостижим, не просто маловероятен. Фикс — do-while: дедлайн
проверяется ПОСЛЕ чтения, минимум `stable_reads` чтений гарантирован
независимо от wall-clock бюджета.

Приём фейковых часов — тот же, что `test_assert_holds_for_unit.py`
(`_FakeClock`, монки-патч `framework.core.waits.time` по СТРОКОВОМУ пути —
подменяет ТОЛЬКО имя `time`, которое видит изнутри себя модуль
`framework.core.waits`, не глобальный модуль `time`). Здесь `read_fn` сам
двигает часы вперёд ЧЕРЕЗ `advance()` (симулирует цену ЧТЕНИЯ), отдельно от
`sleep()`, которую вызывает сам примитив между опросами — оба метода
двигают ОДНИ фейковые "часы", видимые `waits.py`.

Границы (правило 6а CLAUDE.md — тест НА границе и ЗА ней):
- `test_expensive_read_still_gets_minimum_reads_and_converges` — чтение
  ДОРОЖЕ всего бюджета целиком (крайний случай, где старая семантика
  структурно ломалась) — регресс-пин на сам дефект ESC-035;
- `test_timeout_zero_still_performs_minimum_reads` — `timeout=0` (граница
  самого лимита: бюджета нет вообще) — тот же класс дефекта на границе.

Обе границы параметризованы по `stable_reads in (2, 3, 4)` (критик-вход
round3, 2026-08-19): ПЕРВАЯ редакция do-while-фикса гарантировала минимум
чтений ТОЛЬКО при `stable_reads<=2` — дедлайн-`break` не был увязан со
счётчиком реально выполненных чтений, поэтому при `stable_reads=3/4` цикл
всё равно обрывался после 2 чтений (регресс к структурной недостижимости
`converged`, тот же класс дефекта, который фикс обязан был устранить
целиком, не для одного значения параметра). `test_round1_fix_still_fails_at_
stable_reads_ge_3` — красная проба ИМЕННО этой промежуточной редакции (тот
же приём эмбеддинга старой семантики, что `test_old_semantics_fails_where_
fix_converges` ниже), воспроизводящая witness критика буквально:
`stable_reads=2: reads=2 converged=True`, `stable_reads=3: reads=2
converged=False`, `stable_reads=4: reads=2 converged=False`."""
from __future__ import annotations

import allure
import pytest

from framework.core import waits


class _FakeClock:
    """См. `test_assert_holds_for_unit.py::_FakeClock` — идентичный приём:
    `sleep(s)` двигает внутренние "часы" вперёд, реальное время не тратится."""

    def __init__(self, start: float = 0.0):
        self._t = start

    def time(self) -> float:
        return self._t

    def sleep(self, s: float) -> None:
        self._t += s

    def advance(self, s: float) -> None:
        """`read_fn` зовёт это САМ, симулируя цену ЧТЕНИЯ — отдельно от
        `sleep()`, которую вызывает сам примитив МЕЖДУ опросами (`interval`).
        Обе двигают ОДНИ фейковые часы, которые видит `waits.py`."""
        self._t += s


@pytest.fixture()
def fake_clock(monkeypatch):
    """Свежие часы на тест (t=0) — монки-патч ПО СТРОКОВОМУ пути
    `framework.core.waits.time`, тот же приём, что `test_assert_holds_for_
    unit.py::_fake_clock` (не трогает глобальный модуль `time`)."""
    clock = _FakeClock()
    monkeypatch.setattr("framework.core.waits.time", clock)
    return clock


@pytest.mark.p1
@pytest.mark.parametrize("stable_reads", [2, 3, 4])
@allure.id("ESC-035-poll-until-stable-expensive-read-still-converges")
@allure.title("poll_until_stable: read_fn дороже ВСЕГО бюджета -- stable_reads чтений всё равно выполнены, converged=True (регресс-пин ESC-035, параметризован по stable_reads)")
def test_expensive_read_still_gets_minimum_reads_and_converges(fake_clock, stable_reads):
    """Регресс-пин на сам дефект ESC-035: КАЖДЫЙ вызов `read_fn` стоит 5.0s --
    дороже ВСЕГО `timeout=1.0s` бюджета целиком. ДО фикса (`while ... and
    time.time() < deadline` -- дедлайн ДО чтения) тело цикла не исполнилось
    бы ни разу после первого чтения (t=5.0 > deadline=1.0 уже после ПЕРВОГО
    чтения) -- второе чтение никогда бы не произошло, `streak` навсегда 1,
    `converged` структурно недостижим. Фикс обязан выполнить РОВНО
    `stable_reads` чтений, несмотря на то, что бюджет исчерпан уже после
    первого -- параметризовано по `stable_reads in (2, 3, 4)` (критик-вход
    round3): промежуточная редакция фикса держала эту гарантию ТОЛЬКО при
    `stable_reads<=2`, см. `test_round1_fix_still_fails_at_stable_reads_ge_3`
    ниже для красной пробы именно этого случая."""
    calls = {"n": 0}

    def read_fn():
        calls["n"] += 1
        fake_clock.advance(5.0)  # каждое чтение стоит 5s -- дороже timeout=1.0s целиком
        return "same-value"

    last, converged = waits.poll_until_stable(read_fn, stable_reads=stable_reads, timeout=1.0, interval=0.2)

    assert calls["n"] == stable_reads, f"ожидали ровно stable_reads={stable_reads} чтений, было {calls['n']}"
    assert converged is True, "совпадающие значения обязаны сойтись, несмотря на то, что чтение дороже бюджета"
    assert last == "same-value"


@pytest.mark.p1
@allure.id("ESC-035-poll-until-stable-mismatch-converged-false")
@allure.title("poll_until_stable: значения не совпадают -- converged=False")
def test_values_never_match_converged_false(fake_clock):
    """Дешёвые чтения (часы не двигаются read_fn'ом), но ЗНАЧЕНИЯ каждый раз
    РАЗНЫЕ -- `streak` никогда не растёт выше 1, цикл обязан честно исчерпать
    бюджет (`timeout=1.0`, `interval=0.2` -> дедлайн ровно после 6-го чтения,
    считая от t=0) и вернуть `converged=False`, не зависнуть."""
    calls = {"n": 0}

    def read_fn():
        calls["n"] += 1
        return f"value-{calls['n']}"  # всегда новое значение -- streak никогда не растёт

    last, converged = waits.poll_until_stable(read_fn, stable_reads=2, timeout=1.0, interval=0.2)

    assert converged is False
    # t=0 (чтение1) -> sleep 0.2 -> t=0.2 (чтение2, streak=1, t<1.0, продолжаем)
    # -> ...чтение3(t=0.4)...чтение4(t=0.6)...чтение5(t=0.8)...чтение6(t=1.0,
    # t>=deadline -- стоп). Ровно 6 чтений, не 5 и не 7.
    assert calls["n"] == 6, f"ожидали ровно 6 чтений (бюджет 1.0s/interval 0.2s), было {calls['n']}"
    assert last == f"value-{calls['n']}"


@pytest.mark.p1
@allure.id("ESC-035-poll-until-stable-exact-stable-reads-count")
@allure.title("poll_until_stable: ровно stable_reads совпадений -- сходится без лишних чтений")
def test_converges_after_exactly_stable_reads_no_extra_reads(fake_clock):
    """`stable_reads=3`: первые 3 чтения совпадают -- цикл ОБЯЗАН
    остановиться сразу по достижении `streak==3`, НЕ делая 4-е чтение
    (несмотря на щедрый бюджет `timeout=10.0`) -- иначе тест не отличит
    "сошлось ровно на границе" от "продолжает читать после сходимости"
    (4-е значение в списке нарочно ломает streak, если бы было прочитано)."""
    values = ["v", "v", "v", "DIFFERENT-would-break-streak-if-read"]
    calls = {"n": 0}

    def read_fn():
        idx = calls["n"]
        calls["n"] += 1
        return values[idx]

    last, converged = waits.poll_until_stable(read_fn, stable_reads=3, timeout=10.0, interval=0.1)

    assert calls["n"] == 3, f"ожидали ровно 3 чтения (stable_reads), было {calls['n']} -- лишние чтения после сходимости"
    assert converged is True
    assert last == "v"


@pytest.mark.p1
@pytest.mark.parametrize("stable_reads", [2, 3, 4])
@allure.id("ESC-035-poll-until-stable-timeout-zero-boundary")
@allure.title("poll_until_stable: timeout=0 (граница лимита) -- минимум stable_reads чтений всё равно выполнен (параметризован по stable_reads)")
def test_timeout_zero_still_performs_minimum_reads(fake_clock, stable_reads):
    """M6 (правило 6а CLAUDE.md) -- граница введённого лимита: `timeout=0`
    означает "бюджета нет вообще" -- ДО фикса это тот же класс дефекта, что
    "чтение дороже бюджета" (тело цикла не исполнилось бы ни разу). Фикс
    обязан гарантировать минимум `stable_reads` чтений НЕЗАВИСИМО от
    wall-clock бюджета, включая нулевой -- параметризовано по `stable_reads
    in (2, 3, 4)` (критик-вход round3, тот же мотив, что у теста выше)."""
    calls = {"n": 0}

    def read_fn():
        calls["n"] += 1
        return "same"

    last, converged = waits.poll_until_stable(read_fn, stable_reads=stable_reads, timeout=0, interval=0.2)

    assert calls["n"] == stable_reads, f"ожидали ровно {stable_reads} чтений (stable_reads) даже при timeout=0, было {calls['n']}"
    assert converged is True
    assert last == "same"


@pytest.mark.p1
@pytest.mark.parametrize(
    "stable_reads, expected_reads, expected_converged",
    [(2, 2, True), (3, 2, False), (4, 2, False)],
)
@allure.id("ESC-035-poll-until-stable-round1-fix-fails-at-stable-reads-ge-3")
@allure.title("Красная проба (критик-вход round3): промежуточная редакция do-while-фикса чинила ТОЛЬКО экземпляр (stable_reads<=2), не класс")
def test_round1_fix_still_fails_at_stable_reads_ge_3(fake_clock, stable_reads, expected_reads, expected_converged):
    """Буквальная копия ПРОМЕЖУТОЧНОЙ (round1) редакции do-while-фикса --
    дедлайн-`break` стоит ВНУТРИ тела, но БЕЗ отдельного счётчика `reads`
    (тот же баг, что в докоммитной семантике этого критик-раунда): `break`
    срабатывает по ПЕРВОМУ совпавшему `streak>=stable_reads` ИЛИ по
    дедлайну, не дожидаясь, что реально выполнено `stable_reads` чтений.
    Воспроизводит witness критика буквально (`timeout=0`, дешёвые
    ВСЕГДА-совпадающие чтения -- дедлайн истекает сразу после первого
    `sleep`, до того как `streak` успевает дорасти до `stable_reads>=3`):

        stable_reads=2: reads=2 converged=True
        stable_reads=3: reads=2 converged=False   <-- обещано >= 3
        stable_reads=4: reads=2 converged=False

    Финальный (round3) `waits.poll_until_stable` (проверено тестами выше)
    считает `reads` ОТДЕЛЬНО от `streak` и гарантирует минимум для ЛЮБОГО
    `stable_reads` -- этот тест доказывает, что сценарий РЕАЛЬНО различает
    round1/round3 (не тривиальный мок, критик-урок AT-BUG-071)."""

    def _round1_fix_poll_until_stable(read_fn, stable_reads, timeout, interval):
        deadline = fake_clock.time() + timeout
        last = read_fn()
        streak = 1
        while streak < stable_reads:
            fake_clock.sleep(interval)
            current = read_fn()
            streak = streak + 1 if current == last else 1
            last = current
            if streak >= stable_reads or fake_clock.time() >= deadline:
                break
        return last, streak >= stable_reads

    calls = {"n": 0}

    def read_fn():
        calls["n"] += 1
        return "same"  # дешёвые ВСЕГДА совпадающие чтения -- часы не двигает read_fn

    last, converged = _round1_fix_poll_until_stable(read_fn, stable_reads, timeout=0, interval=0.2)

    assert calls["n"] == expected_reads, (
        f"stable_reads={stable_reads}: ожидали {expected_reads} чтений (witness критика), было {calls['n']}"
    )
    assert converged is expected_converged, (
        f"stable_reads={stable_reads}: ожидали converged={expected_converged} (witness критика), было {converged}"
    )


@pytest.mark.p2
@allure.id("ESC-035-poll-until-stable-old-semantics-would-have-failed")
@allure.title("Красная проба: докоммитная семантика (дедлайн ДО чтения) НЕ сходится на том же сценарии, где фикс сходится")
def test_old_semantics_fails_where_fix_converges(fake_clock):
    """Буквальная копия ДОКОММИТНОГО тела цикла (`while streak < stable_reads
    and time.time() < deadline`) -- прогоняет ТОТ ЖЕ сценарий, что
    `test_expensive_read_still_gets_minimum_reads_and_converges` (чтение
    дороже бюджета целиком), доказывая, что сценарий РЕАЛЬНО различает
    старую/новую семантику (критик-урок AT-BUG-071 -- не тривиальный мок)."""
    calls = {"n": 0}

    def read_fn():
        calls["n"] += 1
        fake_clock.advance(5.0)
        return "same-value"

    def _old_semantics_poll_until_stable(read_fn, stable_reads=2, timeout=1.0, interval=0.2):
        deadline = fake_clock.time() + timeout
        last = read_fn()
        streak = 1
        while streak < stable_reads and fake_clock.time() < deadline:
            fake_clock.sleep(interval)
            current = read_fn()
            streak = streak + 1 if current == last else 1
            last = current
        return last, streak >= stable_reads

    last, converged = _old_semantics_poll_until_stable(read_fn, stable_reads=2, timeout=1.0, interval=0.2)

    assert calls["n"] == 1, (
        "докоммитная семантика ОЖИДАЕМО не делает второго чтения (дедлайн уже "
        f"истёк после первого дорогого чтения) -- было {calls['n']} чтений"
    )
    assert converged is False, "докоммитная семантика ОЖИДАЕМО структурно не может сойтись в этом сценарии"
