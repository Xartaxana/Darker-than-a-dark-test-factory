"""Device-free красная/зелёная проба AT-BUG-044 — гонка «файл БД vs схема БД».

Диагноз (critic-вход приёмки D1 `AT-BUG-042`, подтверждён двумя независимыми
живыми воспроизведениями — см. `bugs/AT-BUG-044.md`): Room создаёт ФАЙЛ БД
(`ao3_ratings.db`) раньше, чем прогоняет миграции/CREATE TABLE — старый гейт
`ensure_db_initialized` (`_db_exists`, `test -f`) сигнализировал «готово» в
этом окне, и последующий `_insert_rows` падал `sqlite3.OperationalError: no
such table: work_ratings`.

Живая эмпирическая проверка ЭТОГО ЖЕ окна (на устройстве `emulator-5554`,
2026-08-03, on-device tight-loop без host-сетевой задержки — host-driven
поллинг слишком груб, чтобы поймать окно, оно уже.) дала 6/6 попаданий
"no such table: work_ratings" при гейте по файлу и 0/6 при гейте по схеме
(см. `bugs/AT-BUG-044.md` §Верификация). Эта проба — device-free
ДЕТЕРМИНИРОВАННАЯ реконструкция ТОГО ЖЕ механизма на одном общем таймлайне:
файл "появляется" раньше, чем схема, и показывает (а) что гейт по файлу
сигнализировал бы готовность ПРЕЖДЕВРЕМЕННО (RED), (б) что актуальная
`ensure_db_initialized()` (гейт `_schema_ready`) не возвращается до
фактической готовности схемы (GREEN) — воспроизводимо на КАЖДОМ прогоне,
без флейка живого тайминга.

Переопределяет session-scoped autouse-фикстуру `_ensure_app_installed` из
`conftest.py` (тот же приём, что `test_seed_filter_profiles_unit.py`/
`test_subprocess_timeout_unit.py`) — эта проба чисто локальная, устройство не
трогаем.
"""
from __future__ import annotations

import allure
import pytest

from framework.data import seed_db


@pytest.fixture(scope="session", autouse=True)
def _ensure_app_installed():
    yield


class _FakeDeviceTimeline:
    """Один таймлайн: файл БД появляется на тике `file_appears_at`, таблица
    `work_ratings` — только на более позднем тике `schema_ready_at` (Room ещё
    гоняет миграции/CREATE TABLE) — то же взаимное упорядочение, что диагноз
    AT-BUG-044 и живая проба на `emulator-5554` (файл раньше схемы)."""

    def __init__(self, file_appears_at: int, schema_ready_at: int):
        assert file_appears_at < schema_ready_at, "проба моделирует именно 'файл раньше схемы'"
        self.tick = 0
        self.file_appears_at = file_appears_at
        self.schema_ready_at = schema_ready_at

    def step(self) -> None:
        self.tick += 1

    def db_exists(self) -> bool:
        """То же условие, что старый гейт `_db_exists`/`test -f`."""
        return self.tick >= self.file_appears_at

    def schema_ready(self) -> bool:
        """То же условие, что актуальный гейт `_schema_ready`."""
        return self.tick >= self.schema_ready_at


@pytest.mark.p1
@allure.id("AT-BUG-044-red-file-gate-fires-before-schema")
@allure.title("Красная проба: файловый гейт (_db_exists) сигнализирует «готово» ДО появления схемы (AT-BUG-044, окно диагноза)")
def test_file_only_gate_reports_ready_before_schema_exists():
    # Given таймлайн: файл появляется на тике 1, схема — только на тике 4
    # (то же взаимное упорядочение, что живая проба на устройстве: файл
    # раньше схемы)
    timeline = _FakeDeviceTimeline(file_appears_at=1, schema_ready_at=4)
    timeline.step()  # тик 1: файл уже есть, схемы ещё нет

    # Then файловый гейт (СТАРАЯ логика ensure_db_initialized ДО AT-BUG-044)
    # уже считает БД готовой — именно это окно роняло _insert_rows
    # «no such table: work_ratings» (см. живую пробу в bugs/AT-BUG-044.md)
    assert timeline.db_exists() is True
    assert timeline.schema_ready() is False


@pytest.mark.p1
@allure.id("AT-BUG-044-green-ensure-db-initialized-waits-for-schema")
@allure.title("Зелёная проба: ensure_db_initialized (AT-BUG-044) ждёт СХЕМУ, а не файл, на том же таймлайне")
def test_ensure_db_initialized_waits_past_the_file_ready_tick(monkeypatch):
    # Given тот же таймлайн, что в красной пробе выше (файл на тике 1, схема
    # на тике 4) — но теперь опрашивается через ФАКТИЧЕСКУЮ
    # ensure_db_initialized(), не реконструкцию
    timeline = _FakeDeviceTimeline(file_appears_at=1, schema_ready_at=4)
    calls: list[tuple[int, bool, bool]] = []  # (tick, file_ready_here, schema_ready_here)

    def _fake_schema_ready() -> bool:
        # Каждый опрос предиката = один "тик" поллинга (wait_for зовёт
        # предикат в цикле) — моделирует течение времени на устройстве.
        timeline.step()
        calls.append((timeline.tick, timeline.db_exists(), timeline.schema_ready()))
        return timeline.schema_ready()

    monkeypatch.setattr(seed_db, "_schema_ready", _fake_schema_ready)
    monkeypatch.setattr(seed_db.adb, "shell", lambda *a, **kw: "")
    monkeypatch.setattr(seed_db.adb, "force_stop", lambda: None)

    # When
    seed_db.ensure_db_initialized()

    # Then RED-срез виден изнутри: на самом первом опросе файл уже "есть"
    # (старый гейт `_db_exists` вернул бы True и функция вернулась бы ЗДЕСЬ,
    # до того как таблица создана)
    assert calls[0] == (1, True, False)

    # Then GREEN: актуальный код НЕ вернулся на первом опросе — опросов было
    # ровно столько, сколько нужно, чтобы схема реально стала готова
    assert len(calls) == 4
    assert calls[-1] == (4, True, True)
