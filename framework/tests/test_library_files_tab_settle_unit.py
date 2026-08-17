"""Device-free юнит-проба `library_steps.assert_work_not_in_files_tab` —
AT-BUG-082 (`LibraryScreen.open_tab`/`open_tab_for_rating` таплю по вкладке
top bar, реализованной через `HorizontalPager`, `LibraryScreen.kt:238`; во
время анимированного скролла пейджера ИСХОДНАЯ ещё-не-ушедшая вкладка
временно сосуществует с ЦЕЛЕВОЙ в accessibility-дереве — одноразовый
`is_present(timeout=4)` мог поймать заголовок работы, реально принадлежащий
СТАРОЙ вкладке, и ложно провалить негативный Then «работы нет во FILES»).

Мокает `LibraryScreen.has_work` НА УРОВНЕ КЛАССА (не сам новый хелпер) —
проверяет РЕАЛЬНЫЙ код `library_steps._poll_files_tab_absent`/
`assert_work_not_in_files_tab`, как `test_settings_ratings_fail_closed_unit.py`
мокает `adb.run_as` под `settings_steps` (тот же приём: мок транспортного слоя,
не деталей самой функции под пробой). `_FILES_TAB_SETTLE_TIMEOUT`/
`_FILES_TAB_SETTLE_INTERVAL`/`_FILES_TAB_ABSENT_HOLD_BUDGET`/
`_FILES_TAB_ABSENT_HOLD_INTERVAL` укорочены монкипатчем модульных констант
`library_steps` — тот же приём, что `_fast_ratings_poll` в
`test_settings_ratings_fail_closed_unit.py` (`settings.RATINGS_DB_POLL_TIMEOUT`)
— не связано с логикой самого фикса, только со скоростью ЭТОГО юнит-теста.

**AT-BUG-082 Б1/Б4 критик-вход rework (2026-08-17).** Attempt 1 (settle-фаза
БЕЗ фазы hold) выходил на ПЕРВОМ же чтении «отсутствует» — фактическое
наблюдаемое окно негатива схлопнулось с прежних 4с (старая ОДНОРАЗОВАЯ
семантика наблюдала присутствие В ЛЮБОЙ момент 4с-окна) до
`_FILES_TAB_SETTLE_READ_TIMEOUT` в худшем случае немедленной сходимости.
Критик воспроизвёл живым прогоном: работа появляется на FILES через ~1.5с
(внутри старого 4с окна, ПОСЛЕ первого «отсутствует»-чтения attempt 1) —
attempt 1 давал ложный PASS там, где старая семантика честно давала FAIL.
`_poll_files_tab_absent` теперь ДЕРЖИТ «отсутствует» (`waits.assert_holds_for`)
фиксированный `_FILES_TAB_ABSENT_HOLD_BUDGET` ПОСЛЕ settle-фазы — ловит
именно такую позднюю регрессию (тесты
`test_hold_phase_catches_late_reappearance_after_immediate_settle`/
`test_settle_only_semantics_misses_late_reappearance` ниже).

Проверяет:
1. **Транзитный ложный позитив** (стейл-снимок СТАРОЙ вкладки: `has_work`
   возвращает `True` на первых N вызовах, затем `False` — симулирует
   `HorizontalPager`, доскроллявший до целевой страницы к N-му опросу) —
   `assert_work_not_in_files_tab` НЕ падает: settle-опрос сходится к
   реальному отсутствию, транзитная стейл-строка отброшена (hold-фаза после
   settle тоже держит `False` весь свой бюджет, не мешает).
2. **Различающий негатив (красная проба, старая ДОКОММИТНАЯ семантика):** ТА
   ЖЕ мок-последовательность, прогнанная через семантику ДО AT-BUG-082
   (`not lib.has_work(title, timeout=4)`, ОДИН вызов сразу после открытия
   вкладки) — детерминированно ловит `True` на первом опросе и падает.
3. **Реальная (persistent) регрессия НЕ маскируется:** `has_work` возвращает
   `True` ПОСТОЯННО весь settle-бюджет (работа реально осталась на вкладке) —
   `assert_work_not_in_files_tab` падает `AssertionError` с ожидаемым
   текстом; settle-фаза не переходит к hold, честно возвращает `False` сразу
   по исчерпании settle-бюджета.
4. **Settle-фаза по-прежнему сходится за 1 чтение на happy path, НО hold-фаза
   (Б1) всё равно тратит свой бюджет** — намеренное расширение наблюдаемого
   окна, не регрессия производительности: `_poll_files_tab_absent` больше НЕ
   ограничивается первым снимком (в этом и была суть Б1-дефекта attempt 1).
5. **Б1 красная проба (критик-вход, живой прогон):** `[False, True, True]` —
   первое чтение settle-фазы сразу даёт «отсутствует» (early-exit, ровно
   attempt-1 сценарий), но работа РЕАЛЬНО появляется на всех последующих
   чтениях (поздняя регрессия внутри исторического 4с-окна) — hold-фаза
   обязана поймать это и вернуть `False`, а не `True`.
6. **Различающий сигнал для Б1:** ТА ЖЕ мок-последовательность `[False, True,
   True]`, прогнанная через attempt-1 семантику (settle-only, БЕЗ hold) —
   детерминированно возвращает `True` (absent) — пропускает позднюю
   регрессию, доказывая, что мок-сценарий РЕАЛЬНО различает attempt-1/rework
   (не тривиален).

Не требует устройства/эмулятора — переопределяет session-scoped autouse
`_ensure_app_installed` (conftest.py), тот же приём, что
`test_swipe_to_text_settle_unit.py`/`test_settings_ratings_fail_closed_unit.py`.
"""
from __future__ import annotations

import time

import allure
import pytest

from framework.screens.library_screen import LibraryScreen
from framework.steps import library_steps


@pytest.fixture(scope="session", autouse=True)
def _ensure_app_installed():
    yield


@pytest.fixture(autouse=True)
def _fast_settle_poll(monkeypatch):
    """Укорачивает settle+hold бюджет опроса (AT-BUG-082) — не связано с
    логикой самого фикса, только со скоростью ЭТОГО юнит-теста (реальный
    `time.sleep`, без фейковых часов: интервалы малы настолько, что
    суммарное время теста остаётся долями секунды)."""
    monkeypatch.setattr(library_steps, "_FILES_TAB_SETTLE_TIMEOUT", 0.6)
    monkeypatch.setattr(library_steps, "_FILES_TAB_SETTLE_INTERVAL", 0.05)
    monkeypatch.setattr(library_steps, "_FILES_TAB_ABSENT_HOLD_BUDGET", 0.3)
    monkeypatch.setattr(library_steps, "_FILES_TAB_ABSENT_HOLD_INTERVAL", 0.05)


def _mock_has_work_sequence(monkeypatch, values: list[bool]):
    """Подменяет `LibraryScreen.has_work` последовательностью `values` —
    N-й вызов возвращает `values[N]`, индекс зажимается на последнем элементе
    (исчерпание списка держит ПОСЛЕДНЕЕ значение, симулируя settled steady
    state — тот же приём зажатого индекса, что `_FakeSwipeDriver.
    fingerprint_states` в `test_swipe_to_text_settle_unit.py`)."""
    calls: list[int] = [0]

    def _fake_has_work(self, title: str, timeout: int | None = None) -> bool:
        idx = min(calls[0], len(values) - 1)
        calls[0] += 1
        return values[idx]

    monkeypatch.setattr(LibraryScreen, "has_work", _fake_has_work)
    return calls


class _NoOpDriver:
    """`LibraryScreen(driver).open_tab(...)` реально не нужен под пробой —
    `has_work` замокан на уровне класса и не читает дерево; `open_tab`
    делает `self.tap(self.by_text(label))`, которая тоже замокана отдельно
    там, где нужно избежать реального Appium-вызова."""

    current_context = "NATIVE_APP"


@pytest.mark.p1
@allure.id("AT-BUG-082-settle-poll-discards-transient-stale-positive")
@allure.title("Проба: assert_work_not_in_files_tab не падает на транзитном стейл-снимке СТАРОЙ вкладки (AT-BUG-082)")
def test_assert_work_not_in_files_tab_discards_transient_stale_positive(monkeypatch):
    # Given has_work «видит» работу на первых 2 опросах (стейл-снимок СТАРОЙ
    # вкладки, ещё не ушедшей с экрана во время анимации HorizontalPager),
    # затем settled на реальном отсутствии (целевая вкладка FILES
    # действительно пуста) — и остаётся отсутствующей (hold-фаза не мешает)
    calls = _mock_has_work_sequence(monkeypatch, [True, True, False])
    monkeypatch.setattr(LibraryScreen, "open_tab", lambda self, label: self)
    lib = LibraryScreen(_NoOpDriver())

    # When/Then settle-опрос сходится к отсутствию — не падает
    assert library_steps._poll_files_tab_absent(lib, "A Loved Test Work") is True, (
        "settle+hold-опрос не сошёлся к отсутствию после транзитного стейл-позитива "
        f"(вызовов has_work: {calls[0]})"
    )
    # Различающая проверка: сценарий реально потребовал >1 опроса (не тривиален)
    assert calls[0] >= 3, f"мок вернул settled слишком рано, сценарий не различает: {calls[0]} вызовов"


@pytest.mark.p1
@allure.id("AT-BUG-082-old-single-read-semantics-would-have-failed")
@allure.title("Красная проба: докоммитная ОДНОРАЗОВАЯ семантика падает ровно на том сценарии, где rework проходит")
def test_old_single_read_semantics_fails_on_same_transient_scenario(monkeypatch):
    """Различающий сигнал (критик-урок AT-BUG-071): прогоняет ТУ ЖЕ
    мок-последовательность через семантику ДО AT-BUG-082
    `not lib.has_work(title, timeout=4)` — ОДИН вызов сразу после открытия
    вкладки, без settle-опроса. Первый элемент последовательности — `True`
    (стейл-позитив) — старый код детерминированно поймал бы его и упал."""
    _mock_has_work_sequence(monkeypatch, [True, True, False])
    monkeypatch.setattr(LibraryScreen, "open_tab", lambda self, label: self)
    lib = LibraryScreen(_NoOpDriver())

    old_semantics_result = not lib.has_work("A Loved Test Work", timeout=4)

    assert old_semantics_result is False, (
        "докоммитная (до AT-BUG-082) одноразовая семантика ОЖИДАЕМО ловит "
        "стейл-позитив на первом снимке (это и есть воспроизведённый класс "
        "AT-BUG-082) — если это утверждение падает, мок-сценарий больше не "
        "различает старый/новый код"
    )


@pytest.mark.p1
@allure.id("AT-BUG-082-settle-poll-still-catches-real-regression")
@allure.title("Проба: assert_work_not_in_files_tab честно падает, если работа ДЕЙСТВИТЕЛЬНО осталась на вкладке (реальная регрессия не маскируется)")
def test_assert_work_not_in_files_tab_still_fails_on_persistent_presence(monkeypatch):
    # Given has_work ПОСТОЯННО возвращает True весь settle-бюджет — реальный
    # баг (работа действительно скачалась и осталась на вкладке FILES), не
    # транзитная анимация
    calls = _mock_has_work_sequence(monkeypatch, [True])
    monkeypatch.setattr(LibraryScreen, "open_tab", lambda self, label: self)
    lib = LibraryScreen(_NoOpDriver())

    assert library_steps._poll_files_tab_absent(lib, "A Loved Test Work") is False, (
        "settle-опрос ошибочно счёл работу отсутствующей при ПОСТОЯННОМ "
        "присутствии (реальная регрессия замаскирована — недопустимо)"
    )
    # And сам allure-хелпер honestly поднимает AssertionError с ожидаемым текстом
    monkeypatch.setattr(library_steps, "LibraryScreen", lambda driver: lib)
    with pytest.raises(AssertionError, match="неожиданно присутствует во вкладке FILES"):
        library_steps.assert_work_not_in_files_tab(_NoOpDriver(), "A Loved Test Work")
    assert calls[0] > 1, f"должен был потратить весь settle-бюджет на постоянном True: {calls[0]} вызовов"


@pytest.mark.p2
@allure.id("AT-BUG-082-settle-phase-early-exit-hold-phase-still-spends-budget")
@allure.title("Проба: settle-фаза сходится за 1 чтение на happy path, но hold-фаза (Б1) всё равно дожидается своего бюджета")
def test_settle_phase_early_exit_but_hold_phase_still_spends_budget(monkeypatch):
    """AT-BUG-082 Б1 критик-вход: намеренно ЗАМЕНЯЕТ прежнюю пробу
    «settle-опрос останавливается сразу по settled, не жуёт весь бюджет
    впустую, calls == 1» — та проба стала неверной ПОСЛЕ Б1-фикса: hold-фаза
    ПО ДИЗАЙНУ тратит свой бюджет ЦЕЛИКОМ (`assert_holds_for` не выходит
    досрочно на успехе — см. её докстринг), даже когда settle сошлась
    немедленно. Это ОСОЗНАННЫЙ trade-off (шире окно наблюдения ценой
    нескольких лишних дешёвых опросов), не регрессия производительности."""
    # Given has_work сразу и постоянно возвращает False (типичный happy path —
    # целевая вкладка уже settled к моменту первого опроса)
    calls = _mock_has_work_sequence(monkeypatch, [False])
    monkeypatch.setattr(LibraryScreen, "open_tab", lambda self, label: self)
    lib = LibraryScreen(_NoOpDriver())

    assert library_steps._poll_files_tab_absent(lib, "A Loved Test Work") is True
    # Hold-фаза (Б1) сделала хотя бы один опрос ПОВЕРХ первого settle-чтения —
    # отличие от attempt-1 (settle-only), где calls == 1 навсегда.
    assert calls[0] > 1, (
        f"hold-фаза (Б1) не сделала ни одного доп. опроса после settle-фазы — "
        f"регрессия к attempt-1 (early-exit без hold): {calls[0]} вызовов"
    )


@pytest.mark.p1
@allure.id("AT-BUG-082-b1-hold-phase-catches-late-reappearance-after-immediate-settle")
@allure.title("Красная проба Б1: поздняя регрессия ([False, True, True, ...]) реально ловится hold-фазой")
def test_hold_phase_catches_late_reappearance_after_immediate_settle(monkeypatch):
    """Б1 критик-вход (живой прогон): работа, появившаяся ПОЗЖЕ момента, на
    котором settle-фаза уже сошлась к «отсутствует» (первое же чтение —
    `False`, early-exit settle-фазы — РОВНО attempt-1 сценарий), — attempt-1
    (settle-only, БЕЗ hold) возвращал бы `True` (absent) и НИКОГДА не
    перечитывал бы `has_work` снова, пропуская регрессию, случившуюся ПОЗЖЕ
    первого чтения, но всё ещё внутри исторического 4с окна наблюдения. Мок:
    `has_work` даёт `False` на ПЕРВОМ вызове, затем `True` на ВСЕХ
    последующих (работа реально появилась и держится) — hold-фаза обязана
    поймать это и вернуть `False` (не absent)."""
    calls = _mock_has_work_sequence(monkeypatch, [False, True, True])
    monkeypatch.setattr(LibraryScreen, "open_tab", lambda self, label: self)
    lib = LibraryScreen(_NoOpDriver())

    result = library_steps._poll_files_tab_absent(lib, "A Loved Test Work")

    assert result is False, (
        "hold-фаза не поймала позднюю регрессию (работа появилась ПОСЛЕ "
        f"первого settle-чтения) — вернула absent=True; вызовов has_work: {calls[0]}"
    )
    # Различающий сигнал: settle-фаза реально сошлась НА ПЕРВОМ чтении
    # (early-exit, ровно attempt-1 сценарий), а hold-фаза реально успела
    # сделать хотя бы один доп. опрос ПОСЛЕ settle.
    assert calls[0] >= 2, (
        f"мок-сценарий не дошёл до hold-фазы вовсе — не различает Б1: {calls[0]} вызовов"
    )


@pytest.mark.p1
@allure.id("AT-BUG-082-b1-settle-only-semantics-misses-late-reappearance")
@allure.title("Красная проба Б1: settle-only (attempt 1, без hold) НЕ ловит ту же позднюю регрессию")
def test_settle_only_semantics_misses_late_reappearance(monkeypatch):
    """Прогоняет ТУ ЖЕ мок-последовательность (`[False, True, True]`), что
    `test_hold_phase_catches_late_reappearance_after_immediate_settle` выше,
    через attempt-1 семантику (settle-фаза БЕЗ hold — буквальная копия
    `_poll_files_tab_absent` ДО этого Б1-rework'а) — доказывает, что
    мок-сценарий РЕАЛЬНО различает attempt-1/rework (не тривиален)."""
    _mock_has_work_sequence(monkeypatch, [False, True, True])
    monkeypatch.setattr(LibraryScreen, "open_tab", lambda self, label: self)
    lib = LibraryScreen(_NoOpDriver())

    def _settle_only_attempt1(lib: LibraryScreen, title: str) -> bool:
        deadline = time.monotonic() + library_steps._FILES_TAB_SETTLE_TIMEOUT
        present = lib.has_work(title, timeout=library_steps._FILES_TAB_SETTLE_READ_TIMEOUT)
        while present and time.monotonic() < deadline:
            present = lib.has_work(title, timeout=library_steps._FILES_TAB_SETTLE_READ_TIMEOUT)
        return not present

    old_result = _settle_only_attempt1(lib, "A Loved Test Work")

    assert old_result is True, (
        "attempt-1 (settle-only) семантика ОЖИДАЕМО пропускает позднюю "
        "регрессию (это и есть воспроизведённый класс Б1) — если это "
        "утверждение падает, мок-сценарий больше не различает attempt-1/rework"
    )
