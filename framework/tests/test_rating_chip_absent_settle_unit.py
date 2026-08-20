"""Device-free юнит-проба `rating_steps._poll_chip_absent`/`assert_chip_absent`
— AT-BUG-090 (settle+hold опрос для негативного Then сразу после
стейт-меняющего действия: `tap_selected_chip` — удаление тега;
`reopen_listing_overlay` — закрытие+переоткрытие bottom-sheet).

Прямой аналог `test_rating_comment_collapse_settle_unit.py` (AT-BUG-085),
применённый к ДРУГОМУ примитиву того же файла/composable-семьи
(`rating_steps.py`/`RatingOverlay.chip_visible`, не `comment_expanded`) —
4-й член класса AT-BUG-081/082/083/085 (см. блок-комментарий у
`_poll_chip_absent` в `rating_steps.py` за полным разбором класса гонки).

Мокает `RatingOverlay.chip_visible` НА УРОВНЕ КЛАССА (не сам новый хелпер) —
проверяет РЕАЛЬНЫЙ код `rating_steps._poll_chip_absent`/`assert_chip_absent`,
тот же приём, что exemplar-файл AT-BUG-085.
`_CHIP_ABSENT_SETTLE_TIMEOUT`/`_CHIP_ABSENT_SETTLE_INTERVAL`/
`_CHIP_ABSENT_HOLD_BUDGET`/`_CHIP_ABSENT_HOLD_INTERVAL` укорочены монкипатчем
модульных констант `rating_steps` — не связано с логикой самого фикса, только
со скоростью ЭТОГО юнит-теста.

Проверяет:
1. **Транзитный ложный позитив** (стейл-снимок чипа ещё в дереве:
   `chip_visible` возвращает `True` на первых N вызовах, затем `False`) —
   `_poll_chip_absent` НЕ падает: settle-опрос сходится к реальному
   отсутствующему виду, транзитная стейл-строка отброшена.
2. **Различающий негатив (красная проба, старая ДОКОММИТНАЯ семантика):** ТА
   ЖЕ мок-последовательность, прогнанная через семантику ДО AT-BUG-090
   (`not overlay.chip_visible()`, ОДИН вызов сразу после действия) —
   детерминированно ловит `True` на первом опросе и падает (ровно
   воспроизводит класс дефекта AT-BUG-090/085: TC-091 гипотетически красный).
3. **Реальная (persistent) регрессия НЕ маскируется**: `chip_visible`
   возвращает `True` ПОСТОЯННО весь settle-бюджет — `_poll_chip_absent`
   возвращает `False`, `assert_chip_absent` честно падает `AssertionError` с
   ожидаемым текстом.
4. **Settle-фаза сходится за 1 чтение на happy path, но hold-фаза всё равно
   тратит свой бюджет** — намеренное расширение наблюдаемого окна, не
   регрессия производительности.
5. **Красная проба (поздняя регрессия):** `[False, True, True]` — первое
   чтение settle-фазы сразу даёт «отсутствует» (early-exit), но чип РЕАЛЬНО
   появляется на всех последующих чтениях (поздняя регрессия внутри
   hold-окна) — hold-фаза обязана поймать это и вернуть `False`.
6. **Различающий сигнал для п.5:** ТА ЖЕ мок-последовательность, прогнанная
   через settle-only семантику (БЕЗ hold) — детерминированно возвращает
   `True` (absent) — пропускает позднюю регрессию, доказывая, что
   мок-сценарий РЕАЛЬНО различает settle-only/settle+hold (не тривиален).

Не требует устройства/эмулятора — переопределяет session-scoped autouse
`_ensure_app_installed` (conftest.py), тот же приём, что exemplar-файл выше.
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
    """Укорачивает settle+hold бюджет опроса (AT-BUG-090) — не связано с
    логикой самого фикса, только со скоростью ЭТОГО юнит-теста (реальный
    `time.sleep`, без фейковых часов: интервалы малы настолько, что
    суммарное время теста остаётся долями секунды)."""
    monkeypatch.setattr(rating_steps, "_CHIP_ABSENT_SETTLE_TIMEOUT", 0.6)
    monkeypatch.setattr(rating_steps, "_CHIP_ABSENT_SETTLE_INTERVAL", 0.05)
    monkeypatch.setattr(rating_steps, "_CHIP_ABSENT_HOLD_BUDGET", 0.3)
    monkeypatch.setattr(rating_steps, "_CHIP_ABSENT_HOLD_INTERVAL", 0.05)


def _mock_chip_visible_sequence(monkeypatch, values: list[bool]):
    """Подменяет `RatingOverlay.chip_visible` последовательностью `values` —
    N-й вызов возвращает `values[N]`, индекс зажимается на последнем элементе
    (исчерпание списка держит ПОСЛЕДНЕЕ значение, симулируя settled steady
    state — тот же приём, что `_mock_comment_expanded_sequence`
    (AT-BUG-085) / `_mock_has_work_sequence` (AT-BUG-082/083))."""
    calls: list[int] = [0]

    def _fake_chip_visible(self, tag: str, timeout: int = 6) -> bool:
        idx = min(calls[0], len(values) - 1)
        calls[0] += 1
        return values[idx]

    monkeypatch.setattr(RatingOverlay, "chip_visible", _fake_chip_visible)
    return calls


class _NoOpDriver:
    """`RatingOverlay(driver)` не читает дерево напрямую под пробой —
    `chip_visible` замокан на уровне класса."""

    current_context = "NATIVE_APP"


@pytest.mark.p1
@allure.id("AT-BUG-090-settle-poll-discards-transient-stale-positive")
@allure.title("Проба: _poll_chip_absent не падает на транзитном стейл-снимке присутствия чипа (AT-BUG-090)")
def test_poll_chip_absent_discards_transient_stale_positive(monkeypatch):
    # Given chip_visible «видит» чип на первых 2 опросах (стейл-снимок ещё не
    # ушедшего из дерева узла во время recomposition-лага после
    # tap_selected_chip/reopen_listing_overlay), затем settled на реальном
    # отсутствующем виде
    calls = _mock_chip_visible_sequence(monkeypatch, [True, True, False])
    overlay = RatingOverlay(_NoOpDriver())

    assert rating_steps._poll_chip_absent(overlay, "Angst") is True, (
        "settle+hold-опрос не сошёлся к отсутствующему виду после "
        f"транзитного стейл-позитива (вызовов chip_visible: {calls[0]})"
    )
    assert calls[0] >= 3, f"мок вернул settled слишком рано, сценарий не различает: {calls[0]} вызовов"


@pytest.mark.p1
@allure.id("AT-BUG-090-old-single-read-semantics-fails-on-same-transient-scenario")
@allure.title("Красная проба: докоммитная ОДНОРАЗОВАЯ семантика падает ровно на том сценарии, где rework проходит")
def test_old_single_read_semantics_fails_on_same_transient_scenario(monkeypatch):
    """Прогоняет ТУ ЖЕ мок-последовательность через семантику ДО AT-BUG-090
    (`not overlay.chip_visible()`, ОДИН вызов сразу после
    `tap_selected_chip`/`reopen_listing_overlay`, без settle-опроса) — первый
    элемент последовательности `True` (стейл-позитив чипа ещё в дереве) —
    старый код детерминированно ловит его и падает. Ровно воспроизводит класс
    дефекта (AT-BUG-090, идентичный AT-BUG-085/TC-115)."""
    _mock_chip_visible_sequence(monkeypatch, [True, True, False])
    overlay = RatingOverlay(_NoOpDriver())

    old_semantics_result = not overlay.chip_visible("Angst")

    assert old_semantics_result is False, (
        "докоммитная (до AT-BUG-090) одноразовая семантика ОЖИДАЕМО ловит "
        "стейл-позитив на первом снимке (это и есть воспроизведённый класс) "
        "— если это утверждение падает, мок-сценарий больше не различает "
        "старый/новый код"
    )


@pytest.mark.p1
@allure.id("AT-BUG-090-settle-poll-still-catches-real-regression")
@allure.title("Проба: assert_chip_absent честно падает, если чип ДЕЙСТВИТЕЛЬНО остался виден (за границей settle-бюджета)")
def test_assert_chip_absent_still_fails_on_persistent_visibility(monkeypatch):
    # Given chip_visible ПОСТОЯННО возвращает True весь settle-бюджет (и за
    # его пределами) — реальная регрессия, не транзитный recomposition-лаг
    calls = _mock_chip_visible_sequence(monkeypatch, [True])
    overlay = RatingOverlay(_NoOpDriver())

    assert rating_steps._poll_chip_absent(overlay, "Angst") is False, (
        "settle-опрос ошибочно счёл чип отсутствующим при ПОСТОЯННОМ (за "
        "границей settle-бюджета) присутствии — реальная регрессия "
        "замаскирована — недопустимо"
    )
    # And сам allure-хелпер honestly поднимает AssertionError с ожидаемым текстом
    monkeypatch.setattr(rating_steps, "RatingOverlay", lambda driver: overlay)
    with pytest.raises(AssertionError, match="неожиданно присутствует среди тегов overlay"):
        rating_steps.assert_chip_absent(_NoOpDriver(), "Angst")
    assert calls[0] > 1, f"должен был потратить весь settle-бюджет на постоянном True: {calls[0]} вызовов"


@pytest.mark.p2
@allure.id("AT-BUG-090-settle-phase-immediate-convergence-hold-phase-still-spends-budget")
@allure.title("Проба: settle-фаза сходится за 1 чтение на happy path, но hold-фаза всё равно дожидается своего бюджета")
def test_settle_phase_immediate_convergence_but_hold_phase_still_spends_budget(monkeypatch):
    """Симметрично одноимённой пробе AT-BUG-085: hold-фаза ПО ДИЗАЙНУ тратит
    свой бюджет ЦЕЛИКОМ (`assert_holds_for` не выходит досрочно на успехе),
    даже когда settle сошлась немедленно (граничный случай settle-бюджета —
    1 чтение, минимум возможного). Осознанный trade-off, не регрессия
    производительности."""
    calls = _mock_chip_visible_sequence(monkeypatch, [False])
    overlay = RatingOverlay(_NoOpDriver())

    assert rating_steps._poll_chip_absent(overlay, "Angst") is True
    assert calls[0] > 1, (
        f"hold-фаза не сделала ни одного доп. опроса после settle-фазы — "
        f"регрессия к settle-only (early-exit без hold): {calls[0]} вызовов"
    )


@pytest.mark.p1
@allure.id("AT-BUG-090-hold-phase-catches-late-reappearance-after-immediate-settle")
@allure.title("Красная проба: поздняя регрессия ([False, True, True, ...]) реально ловится hold-фазой")
def test_hold_phase_catches_late_reappearance_after_immediate_settle(monkeypatch):
    """Чип, вновь появившийся ПОЗЖЕ момента, на котором settle-фаза уже
    сошлась к «отсутствует» (первое же чтение — `False`, early-exit) —
    settle-only (без hold) вернул бы `True` (absent) и НИКОГДА не перечитывал
    бы `chip_visible` снова, пропуская регрессию, случившуюся ПОЗЖЕ первого
    чтения, но всё ещё внутри hold-окна наблюдения."""
    calls = _mock_chip_visible_sequence(monkeypatch, [False, True, True])
    overlay = RatingOverlay(_NoOpDriver())

    result = rating_steps._poll_chip_absent(overlay, "Angst")

    assert result is False, (
        "hold-фаза не поймала позднюю регрессию (чип появился ПОСЛЕ первого "
        f"settle-чтения) — вернула absent=True; вызовов chip_visible: {calls[0]}"
    )
    assert calls[0] >= 2, (
        f"мок-сценарий не дошёл до hold-фазы вовсе — не различает позднюю регрессию: {calls[0]} вызовов"
    )


@pytest.mark.p1
@allure.id("AT-BUG-090-settle-only-semantics-misses-late-reappearance")
@allure.title("Красная проба: settle-only (без hold) НЕ ловит ту же позднюю регрессию")
def test_settle_only_semantics_misses_late_reappearance(monkeypatch):
    """Прогоняет ТУ ЖЕ мок-последовательность (`[False, True, True]`), что
    `test_hold_phase_catches_late_reappearance_after_immediate_settle` выше,
    через settle-only семантику (settle-фаза БЕЗ hold — буквальная копия
    `_poll_chip_absent` без второй фазы) — доказывает, что мок-сценарий
    РЕАЛЬНО различает settle-only/settle+hold (не тривиален)."""
    _mock_chip_visible_sequence(monkeypatch, [False, True, True])
    overlay = RatingOverlay(_NoOpDriver())

    def _settle_only(overlay: RatingOverlay, tag: str) -> bool:
        deadline = time.monotonic() + rating_steps._CHIP_ABSENT_SETTLE_TIMEOUT
        visible = overlay.chip_visible(tag, timeout=rating_steps._CHIP_ABSENT_SETTLE_READ_TIMEOUT)
        while visible and time.monotonic() < deadline:
            visible = overlay.chip_visible(tag, timeout=rating_steps._CHIP_ABSENT_SETTLE_READ_TIMEOUT)
        return not visible

    old_result = _settle_only(overlay, "Angst")

    assert old_result is True, (
        "settle-only семантика ОЖИДАЕМО пропускает позднюю регрессию (это и "
        "есть воспроизведённый класс) — если это утверждение падает, "
        "мок-сценарий больше не различает settle-only/settle+hold"
    )
