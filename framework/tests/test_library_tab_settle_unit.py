"""Device-free юнит-проба `library_steps.assert_work_not_in_tab` — AT-BUG-083
(сиблинг AT-BUG-082, D-0043 «класс, не экземпляр»): `assert_work_not_in_tab`
(ЛЮБАЯ rating-вкладка Library — FAVORITE/KUDOSED/READ/PENDING/DISLIKED, не
только FILES) была СТРУКТУРНО ИДЕНТИЧНА `assert_work_not_in_files_tab` ДО
AT-BUG-082: `LibraryScreen.open_tab`/`open_tab_for_rating` таплю по вкладке
`HorizontalPager` (`LibraryScreen.kt:238`), затем ОДИН `has_work(timeout=4)`
сразу после — во время анимации перехода исходная (ещё не ушедшая) страница
временно сосуществует с целевой в accessibility-дереве, одноразовое чтение
могло поймать заголовок работы, реально принадлежащий СТАРОЙ вкладке.

`assert_work_not_in_tab` теперь делегирует в `_poll_tab_absent` — обобщение
`_poll_files_tab_absent` (AT-BUG-082) на произвольный `tab_label`, ТА ЖЕ
settle+hold логика. Этот файл — прямой аналог `test_library_files_tab_
settle_unit.py` (та же структура/приёмы: мок `LibraryScreen.has_work` на
уровне класса, монкипатч `open_tab`/`open_tab_for_rating`, укороченные
settle/hold-константы через фикстуру `_fast_settle_poll`), нацеленный на
`assert_work_not_in_tab`/`_poll_tab_absent` вместо `assert_work_not_in_
files_tab`/`_poll_files_tab_absent` — доказывает, что обобщение (AT-BUG-083)
даёт ТУ ЖЕ различающую силу на rating-вкладке (не FILES), не только
структурно (общий код), но и эмпирически (та же красная проба).

Проверяет (см. `test_library_files_tab_settle_unit.py` за более подробным
разбором каждого сценария — здесь то же самое, но через
`assert_work_not_in_tab`/`_poll_tab_absent`):
1. Транзитный ложный позитив не маскирует реальное отсутствие (settle-фаза
   сходится).
2. Красная проба: докоммитная ОДНОРАЗОВАЯ семантика (`not has_work(timeout=4)`,
   как было у `assert_work_not_in_tab` ДО ЭТОЙ правки) детерминированно ловит
   ТОТ ЖЕ транзитный стейл-позитив и падает — доказывает, что мок-сценарий
   реально различает старый/новый код (не тривиален).
3. Реальная (persistent) регрессия НЕ маскируется — `assert_work_not_in_tab`
   честно падает, сообщение называет ПРАВИЛЬНУЮ вкладку рейтинга (не «FILES»
   — обобщение параметризует `tab_label`, не хардкодит).
4. Б1-класс: поздняя регрессия (появилась ПОСЛЕ первого settle-чтения, но до
   истечения исторического окна наблюдения) ловится hold-фазой на
   rating-вкладке ТАК ЖЕ, как на FILES (AT-BUG-082 Б1) — и НЕ ловится
   settle-only (attempt-1) семантикой на ТОЙ ЖЕ последовательности
   (различающий сигнал).

Не требует устройства/эмулятора — переопределяет session-scoped autouse
`_ensure_app_installed` (conftest.py), тот же приём, что
`test_library_files_tab_settle_unit.py`.
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
    """Укорачивает settle+hold бюджет опроса (AT-BUG-082/083 — те же общие
    константы `library_steps`, используемые и `_poll_files_tab_absent`, и
    `_poll_tab_absent`) — не связано с логикой самого фикса, только со
    скоростью ЭТОГО юнит-теста."""
    monkeypatch.setattr(library_steps, "_FILES_TAB_SETTLE_TIMEOUT", 0.6)
    monkeypatch.setattr(library_steps, "_FILES_TAB_SETTLE_INTERVAL", 0.05)
    monkeypatch.setattr(library_steps, "_FILES_TAB_ABSENT_HOLD_BUDGET", 0.3)
    monkeypatch.setattr(library_steps, "_FILES_TAB_ABSENT_HOLD_INTERVAL", 0.05)


def _mock_has_work_sequence(monkeypatch, values: list[bool]):
    """Подменяет `LibraryScreen.has_work` последовательностью `values` —
    N-й вызов возвращает `values[N]`, индекс зажимается на последнем элементе
    (тот же приём, что `test_library_files_tab_settle_unit.py`)."""
    calls: list[int] = [0]

    def _fake_has_work(self, title: str, timeout: int | None = None) -> bool:
        idx = min(calls[0], len(values) - 1)
        calls[0] += 1
        return values[idx]

    monkeypatch.setattr(LibraryScreen, "has_work", _fake_has_work)
    return calls


class _NoOpDriver:
    """`assert_work_not_in_tab` реально не нужен живой driver — `has_work` и
    `open_tab_for_rating`/`open_tab` замокана на уровне класса, никакого
    реального Appium-вызова не происходит."""

    current_context = "NATIVE_APP"


@pytest.mark.p1
@allure.id("AT-BUG-083-settle-poll-discards-transient-stale-positive")
@allure.title("Проба: assert_work_not_in_tab не падает на транзитном стейл-снимке СОСЕДНЕЙ вкладки (AT-BUG-083)")
def test_assert_work_not_in_tab_discards_transient_stale_positive(monkeypatch):
    # Given has_work «видит» работу на первых 2 опросах (стейл-снимок СТАРОЙ
    # вкладки, ещё не ушедшей во время анимации HorizontalPager), затем
    # settled на реальном отсутствии (целевая rating-вкладка действительно
    # пуста от этой работы) — и остаётся отсутствующей (hold-фаза не мешает)
    calls = _mock_has_work_sequence(monkeypatch, [True, True, False])
    monkeypatch.setattr(LibraryScreen, "open_tab", lambda self, label: self)
    lib = LibraryScreen(_NoOpDriver())

    # When/Then settle-опрос сходится к отсутствию — не падает
    assert library_steps._poll_tab_absent(lib, "A Loved Test Work", "KUDOSED") is True, (
        "settle+hold-опрос не сошёлся к отсутствию после транзитного стейл-позитива "
        f"(вызовов has_work: {calls[0]})"
    )
    # Различающая проверка: сценарий реально потребовал >1 опроса (не тривиален)
    assert calls[0] >= 3, f"мок вернул settled слишком рано, сценарий не различает: {calls[0]} вызовов"


@pytest.mark.p1
@allure.id("AT-BUG-083-old-single-read-semantics-would-have-failed")
@allure.title("Красная проба: докоммитная ОДНОРАЗОВАЯ семантика assert_work_not_in_tab падает ровно на том сценарии, где фикс проходит")
def test_old_single_read_semantics_fails_on_same_transient_scenario(monkeypatch):
    """Различающий сигнал (AT-BUG-083, прямой аналог AT-BUG-082 red-пробы):
    прогоняет ТУ ЖЕ мок-последовательность через семантику `assert_work_not_
    in_tab` ДО ЭТОЙ правки (`not lib.has_work(title, timeout=4)`, ОДИН вызов
    сразу после `open_tab_for_rating`, без settle-опроса). Первый элемент
    последовательности — `True` (стейл-позитив) — старый код детерминированно
    поймал бы его и упал."""
    _mock_has_work_sequence(monkeypatch, [True, True, False])
    monkeypatch.setattr(LibraryScreen, "open_tab", lambda self, label: self)
    lib = LibraryScreen(_NoOpDriver())

    old_semantics_result = not lib.has_work("A Loved Test Work", timeout=4)

    assert old_semantics_result is False, (
        "докоммитная (до AT-BUG-083) одноразовая семантика assert_work_not_in_tab "
        "ОЖИДАЕМО ловит стейл-позитив на первом снимке (это и есть воспроизведённый "
        "класс AT-BUG-082/083) — если это утверждение падает, мок-сценарий больше "
        "не различает старый/новый код"
    )


@pytest.mark.p1
@allure.id("AT-BUG-083-settle-poll-still-catches-real-regression")
@allure.title("Проба: assert_work_not_in_tab честно падает с ПРАВИЛЬНОЙ вкладкой в сообщении, если работа ДЕЙСТВИТЕЛЬНО осталась (реальная регрессия не маскируется)")
def test_assert_work_not_in_tab_still_fails_on_persistent_presence(monkeypatch):
    # Given has_work ПОСТОЯННО возвращает True весь settle-бюджет — реальная
    # регрессия (работа реально осталась на rating-вкладке), не транзитная
    # анимация
    calls = _mock_has_work_sequence(monkeypatch, [True])
    monkeypatch.setattr(LibraryScreen, "open_tab", lambda self, label: self)
    lib = LibraryScreen(_NoOpDriver())

    assert library_steps._poll_tab_absent(lib, "A Loved Test Work", "PENDING") is False, (
        "settle-опрос ошибочно счёл работу отсутствующей при ПОСТОЯННОМ "
        "присутствии (реальная регрессия замаскирована — недопустимо)"
    )
    # And сам Then honestly поднимает AssertionError с ПРАВИЛЬНОЙ вкладкой в
    # тексте (обобщение параметризует tab_label по rating, не хардкодит FILES)
    monkeypatch.setattr(library_steps, "LibraryScreen", lambda driver: lib)
    with pytest.raises(AssertionError, match="неожиданно присутствует во вкладке PENDING"):
        library_steps.assert_work_not_in_tab(_NoOpDriver(), "PENDING", "A Loved Test Work")
    assert calls[0] > 1, f"должен был потратить весь settle-бюджет на постоянном True: {calls[0]} вызовов"


@pytest.mark.p1
@allure.id("AT-BUG-083-hold-phase-catches-late-reappearance-after-immediate-settle")
@allure.title("Красная проба: поздняя регрессия ([False, True, True, ...]) на rating-вкладке реально ловится hold-фазой")
def test_hold_phase_catches_late_reappearance_after_immediate_settle(monkeypatch):
    """AT-BUG-082 Б1-класс, воспроизведённый через `assert_work_not_in_tab`
    (AT-BUG-083): работа, появившаяся ПОЗЖЕ момента, на котором settle-фаза
    уже сошлась к «отсутствует» (первое же чтение — `False`, early-exit) —
    settle-only (attempt-1) семантика вернула бы `True` (absent) и никогда не
    перечитывала бы `has_work` снова, пропуская регрессию, случившуюся ПОЗЖЕ
    первого чтения. Мок: `has_work` даёт `False` на ПЕРВОМ вызове, затем
    `True` на ВСЕХ последующих — hold-фаза обязана поймать это и вернуть
    `False` (не absent)."""
    calls = _mock_has_work_sequence(monkeypatch, [False, True, True])
    monkeypatch.setattr(LibraryScreen, "open_tab", lambda self, label: self)
    lib = LibraryScreen(_NoOpDriver())

    result = library_steps._poll_tab_absent(lib, "A Loved Test Work", "DISLIKED")

    assert result is False, (
        "hold-фаза не поймала позднюю регрессию на rating-вкладке (работа "
        f"появилась ПОСЛЕ первого settle-чтения) — вернула absent=True; "
        f"вызовов has_work: {calls[0]}"
    )
    # Различающий сигнал: settle-фаза реально сошлась НА ПЕРВОМ чтении
    # (early-exit), а hold-фаза реально успела сделать хотя бы один доп.
    # опрос ПОСЛЕ settle.
    assert calls[0] >= 2, (
        f"мок-сценарий не дошёл до hold-фазы вовсе — не различает Б1-класс: {calls[0]} вызовов"
    )


@pytest.mark.p1
@allure.id("AT-BUG-083-settle-only-semantics-misses-late-reappearance")
@allure.title("Красная проба: settle-only (attempt-1, без hold) НЕ ловит ту же позднюю регрессию на rating-вкладке")
def test_settle_only_semantics_misses_late_reappearance(monkeypatch):
    """Прогоняет ТУ ЖЕ мок-последовательность (`[False, True, True]`), что
    `test_hold_phase_catches_late_reappearance_after_immediate_settle` выше,
    через settle-фазу БЕЗ hold (буквальная копия ПЕРВОЙ, не финальной,
    редакции `_poll_files_tab_absent` до Б1-rework'а AT-BUG-082) — доказывает,
    что мок-сценарий РЕАЛЬНО различает settle-only/settle+hold (не
    тривиален) на rating-вкладке ТАК ЖЕ, как на FILES."""
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
        "settle-only (attempt-1) семантика ОЖИДАЕМО пропускает позднюю "
        "регрессию на rating-вкладке (это и есть воспроизведённый класс "
        "Б1/AT-BUG-083) — если это утверждение падает, мок-сценарий больше "
        "не различает settle-only/settle+hold"
    )
