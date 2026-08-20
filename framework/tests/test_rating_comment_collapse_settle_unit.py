"""Device-free юнит-проба `rating_steps._poll_comment_collapsed`/
`assert_comment_collapsed_with_text` — AT-BUG-085 (settle+hold опрос для
негативного Then после сохранения комментария в `RatingOverlay`).

Прямой аналог `test_library_files_tab_settle_unit.py`/`test_library_tab_
settle_unit.py` (AT-BUG-082/083), применённый к ДРУГОМУ модулю/UI-механизму
(`rating_steps.py`/`RatingOverlay.comment_expanded`, не `library_steps.py`/
`LibraryScreen.has_work`) — см. блок-комментарий у `_poll_comment_collapsed`
в `rating_steps.py` за полным разбором класса гонки и локализацией
(recomposition-лаг, НЕ анимация — `RatingMenu` переключает `showComment` без
`animateColorAsState`/`AnimatedVisibility`).

Мокает `RatingOverlay.comment_expanded` НА УРОВНЕ КЛАССА (не сам новый
хелпер) — проверяет РЕАЛЬНЫЙ код `rating_steps._poll_comment_collapsed`/
`assert_comment_collapsed_with_text`, тот же приём, что exemplar-файлы выше.
`_COMMENT_COLLAPSE_SETTLE_TIMEOUT`/`_COMMENT_COLLAPSE_SETTLE_INTERVAL`/
`_COMMENT_COLLAPSE_HOLD_BUDGET`/`_COMMENT_COLLAPSE_HOLD_INTERVAL` укорочены
монкипатчем модульных констант `rating_steps` — не связано с логикой самого
фикса, только со скоростью ЭТОГО юнит-теста.

Проверяет:
1. **Транзитный ложный позитив** (стейл-снимок «Hide note» ещё в дереве:
   `comment_expanded` возвращает `True` на первых N вызовах, затем `False`) —
   `_poll_comment_collapsed` НЕ падает: settle-опрос сходится к реальному
   свёрнутому виду, транзитная стейл-строка отброшена.
2. **Различающий негатив (красная проба, старая ДОКОММИТНАЯ семантика):** ТА
   ЖЕ мок-последовательность, прогнанная через семантику ДО AT-BUG-085
   (`not overlay.comment_expanded()`, ОДИН вызов сразу после сохранения) —
   детерминированно ловит `True` на первом опросе и падает (ровно
   воспроизводит `bugs/AT-BUG-085.md`: TC-115 красный в полном
   `test_downloads.py`).
3. **Реальная (persistent) регрессия НЕ маскируется** (граница settle-бюджета
   — «за» ней, см. п.6а CLAUDE.md): `comment_expanded` возвращает `True`
   ПОСТОЯННО весь settle-бюджет — `_poll_comment_collapsed` возвращает
   `False`, `assert_comment_collapsed_with_text` честно падает
   `AssertionError` с ожидаемым текстом.
4. **Settle-фаза сходится за 1 чтение на happy path, но hold-фаза всё равно
   тратит свой бюджет** (граница settle-бюджета — «на» ней, немедленная
   сходимость — минимальный краевой случай settle-фазы) — намеренное
   расширение наблюдаемого окна, не регрессия производительности.
5. **Красная проба (поздняя регрессия):** `[False, True, True]` — первое
   чтение settle-фазы сразу даёт «свёрнуто» (early-exit), но комментарий
   РЕАЛЬНО разворачивается на всех последующих чтениях (поздняя регрессия
   внутри hold-окна) — hold-фаза обязана поймать это и вернуть `False`.
6. **Различающий сигнал для п.5:** ТА ЖЕ мок-последовательность, прогнанная
   через settle-only семантику (БЕЗ hold) — детерминированно возвращает
   `True` (collapsed) — пропускает позднюю регрессию, доказывая, что
   мок-сценарий РЕАЛЬНО различает settle-only/settle+hold (не тривиален).

Не требует устройства/эмулятора — переопределяет session-scoped autouse
`_ensure_app_installed` (conftest.py), тот же приём, что exemplar-файлы выше.
"""
from __future__ import annotations

import time

import allure
import pytest

from framework.screens.rating_overlay import RatingOverlay
from framework.steps import rating_steps


@pytest.fixture(scope="session", autouse=True)
def _ensure_app_installed():
    yield


@pytest.fixture(autouse=True)
def _fast_settle_poll(monkeypatch):
    """Укорачивает settle+hold бюджет опроса (AT-BUG-085) — не связано с
    логикой самого фикса, только со скоростью ЭТОГО юнит-теста (реальный
    `time.sleep`, без фейковых часов: интервалы малы настолько, что
    суммарное время теста остаётся долями секунды)."""
    monkeypatch.setattr(rating_steps, "_COMMENT_COLLAPSE_SETTLE_TIMEOUT", 0.6)
    monkeypatch.setattr(rating_steps, "_COMMENT_COLLAPSE_SETTLE_INTERVAL", 0.05)
    monkeypatch.setattr(rating_steps, "_COMMENT_COLLAPSE_HOLD_BUDGET", 0.3)
    monkeypatch.setattr(rating_steps, "_COMMENT_COLLAPSE_HOLD_INTERVAL", 0.05)


def _mock_comment_expanded_sequence(monkeypatch, values: list[bool]):
    """Подменяет `RatingOverlay.comment_expanded` последовательностью
    `values` — N-й вызов возвращает `values[N]`, индекс зажимается на
    последнем элементе (исчерпание списка держит ПОСЛЕДНЕЕ значение,
    симулируя settled steady state — тот же приём, что
    `_mock_has_work_sequence` в `test_library_files_tab_settle_unit.py`)."""
    calls: list[int] = [0]

    def _fake_comment_expanded(self, timeout: int = 6) -> bool:
        idx = min(calls[0], len(values) - 1)
        calls[0] += 1
        return values[idx]

    monkeypatch.setattr(RatingOverlay, "comment_expanded", _fake_comment_expanded)
    return calls


class _NoOpDriver:
    """`RatingOverlay(driver)` не читает дерево напрямую под пробой —
    `comment_expanded` замокан на уровне класса."""

    current_context = "NATIVE_APP"


@pytest.mark.p1
@allure.id("AT-BUG-085-settle-poll-discards-transient-stale-positive")
@allure.title("Проба: _poll_comment_collapsed не падает на транзитном стейл-снимке «Hide note» (AT-BUG-085)")
def test_poll_comment_collapsed_discards_transient_stale_positive(monkeypatch):
    # Given comment_expanded «видит» «Hide note» на первых 2 опросах (стейл-
    # снимок ещё не ушедшего из дерева узла во время recomposition-лага),
    # затем settled на реальном свёрнутом виде
    calls = _mock_comment_expanded_sequence(monkeypatch, [True, True, False])
    overlay = RatingOverlay(_NoOpDriver())

    assert rating_steps._poll_comment_collapsed(overlay) is True, (
        "settle+hold-опрос не сошёлся к свёрнутому виду после транзитного "
        f"стейл-позитива (вызовов comment_expanded: {calls[0]})"
    )
    assert calls[0] >= 3, f"мок вернул settled слишком рано, сценарий не различает: {calls[0]} вызовов"


@pytest.mark.p1
@allure.id("AT-BUG-085-old-single-read-semantics-fails-on-same-transient-scenario")
@allure.title("Красная проба: докоммитная ОДНОРАЗОВАЯ семантика падает ровно на том сценарии, где rework проходит")
def test_old_single_read_semantics_fails_on_same_transient_scenario(monkeypatch):
    """Прогоняет ТУ ЖЕ мок-последовательность через семантику ДО AT-BUG-085
    (`not overlay.comment_expanded()`, ОДИН вызов сразу после `save_note()`,
    без settle-опроса) — первый элемент последовательности `True` (стейл-
    позитив «Hide note» ещё в дереве) — старый код детерминированно ловит его
    и падает. Ровно воспроизводит `bugs/AT-BUG-085.md` (TC-115)."""
    _mock_comment_expanded_sequence(monkeypatch, [True, True, False])
    overlay = RatingOverlay(_NoOpDriver())

    old_semantics_result = not overlay.comment_expanded()

    assert old_semantics_result is False, (
        "докоммитная (до AT-BUG-085) одноразовая семантика ОЖИДАЕМО ловит "
        "стейл-позитив на первом снимке (это и есть воспроизведённый класс "
        "AT-BUG-085) — если это утверждение падает, мок-сценарий больше не "
        "различает старый/новый код"
    )


@pytest.mark.p1
@allure.id("AT-BUG-085-settle-poll-still-catches-real-regression")
@allure.title("Проба: assert_comment_collapsed_with_text честно падает, если комментарий ДЕЙСТВИТЕЛЬНО остался развёрнут (за границей settle-бюджета)")
def test_assert_comment_collapsed_still_fails_on_persistent_expansion(monkeypatch):
    # Given comment_expanded ПОСТОЯННО возвращает True весь settle-бюджет (и
    # за его пределами) — реальная регрессия, не транзитный recomposition-лаг
    calls = _mock_comment_expanded_sequence(monkeypatch, [True])
    overlay = RatingOverlay(_NoOpDriver())

    assert rating_steps._poll_comment_collapsed(overlay) is False, (
        "settle-опрос ошибочно счёл комментарий свёрнутым при ПОСТОЯННОМ "
        "(за границей settle-бюджета) присутствии «Hide note» — реальная "
        "регрессия замаскирована — недопустимо"
    )
    # And сам allure-хелпер honestly поднимает AssertionError с ожидаемым текстом
    monkeypatch.setattr(rating_steps, "RatingOverlay", lambda driver: overlay)
    with pytest.raises(AssertionError, match="должно свернуться в компактное превью"):
        rating_steps.assert_comment_collapsed_with_text(_NoOpDriver(), "re-save-note")
    assert calls[0] > 1, f"должен был потратить весь settle-бюджет на постоянном True: {calls[0]} вызовов"


@pytest.mark.p2
@allure.id("AT-BUG-085-settle-phase-immediate-convergence-hold-phase-still-spends-budget")
@allure.title("Проба: settle-фаза сходится за 1 чтение на happy path (граница settle-бюджета — минимальный краевой случай), но hold-фаза всё равно дожидается своего бюджета")
def test_settle_phase_immediate_convergence_but_hold_phase_still_spends_budget(monkeypatch):
    """Симметрично `test_settle_phase_early_exit_but_hold_phase_still_spends_
    budget` (AT-BUG-082 Б1): hold-фаза ПО ДИЗАЙНУ тратит свой бюджет ЦЕЛИКОМ
    (`assert_holds_for` не выходит досрочно на успехе), даже когда settle
    сошлась немедленно (граничный случай settle-бюджета — 1 чтение, минимум
    возможного). Осознанный trade-off (шире окно наблюдения ценой нескольких
    лишних дешёвых опросов), не регрессия производительности."""
    calls = _mock_comment_expanded_sequence(monkeypatch, [False])
    overlay = RatingOverlay(_NoOpDriver())

    assert rating_steps._poll_comment_collapsed(overlay) is True
    assert calls[0] > 1, (
        f"hold-фаза не сделала ни одного доп. опроса после settle-фазы — "
        f"регрессия к settle-only (early-exit без hold): {calls[0]} вызовов"
    )


@pytest.mark.p1
@allure.id("AT-BUG-085-hold-phase-catches-late-reexpansion-after-immediate-settle")
@allure.title("Красная проба: поздняя регрессия ([False, True, True, ...]) реально ловится hold-фазой")
def test_hold_phase_catches_late_reexpansion_after_immediate_settle(monkeypatch):
    """Комментарий, вновь развернувшийся ПОЗЖЕ момента, на котором settle-
    фаза уже сошлась к «свёрнуто» (первое же чтение — `False`, early-exit) —
    settle-only (без hold) вернул бы `True` (collapsed) и НИКОГДА не
    перечитывал бы `comment_expanded` снова, пропуская регрессию, случившуюся
    ПОЗЖЕ первого чтения, но всё ещё внутри hold-окна наблюдения."""
    calls = _mock_comment_expanded_sequence(monkeypatch, [False, True, True])
    overlay = RatingOverlay(_NoOpDriver())

    result = rating_steps._poll_comment_collapsed(overlay)

    assert result is False, (
        "hold-фаза не поймала позднюю регрессию (комментарий развернулся "
        f"ПОСЛЕ первого settle-чтения) — вернула collapsed=True; вызовов "
        f"comment_expanded: {calls[0]}"
    )
    assert calls[0] >= 2, (
        f"мок-сценарий не дошёл до hold-фазы вовсе — не различает позднюю регрессию: {calls[0]} вызовов"
    )


@pytest.mark.p1
@allure.id("AT-BUG-085-settle-only-semantics-misses-late-reexpansion")
@allure.title("Красная проба: settle-only (без hold) НЕ ловит ту же позднюю регрессию")
def test_settle_only_semantics_misses_late_reexpansion(monkeypatch):
    """Прогоняет ТУ ЖЕ мок-последовательность (`[False, True, True]`), что
    `test_hold_phase_catches_late_reexpansion_after_immediate_settle` выше,
    через settle-only семантику (settle-фаза БЕЗ hold — буквальная копия
    `_poll_comment_collapsed` без второй фазы) — доказывает, что мок-сценарий
    РЕАЛЬНО различает settle-only/settle+hold (не тривиален)."""
    _mock_comment_expanded_sequence(monkeypatch, [False, True, True])
    overlay = RatingOverlay(_NoOpDriver())

    def _settle_only(overlay: RatingOverlay) -> bool:
        deadline = time.monotonic() + rating_steps._COMMENT_COLLAPSE_SETTLE_TIMEOUT
        expanded = overlay.comment_expanded(timeout=rating_steps._COMMENT_COLLAPSE_SETTLE_READ_TIMEOUT)
        while expanded and time.monotonic() < deadline:
            expanded = overlay.comment_expanded(timeout=rating_steps._COMMENT_COLLAPSE_SETTLE_READ_TIMEOUT)
        return not expanded

    old_result = _settle_only(overlay)

    assert old_result is True, (
        "settle-only семантика ОЖИДАЕМО пропускает позднюю регрессию (это и "
        "есть воспроизведённый класс) — если это утверждение падает, "
        "мок-сценарий больше не различает settle-only/settle+hold"
    )
