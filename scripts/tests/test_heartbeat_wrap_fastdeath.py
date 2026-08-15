"""Юнит-тесты детектора серийной быстрой смерти + возврата бюджета
(spec-heartbeat-fastdeath.md v2, 2026-08-15). Дополнение к
test_heartbeat_wrap.py/test_heartbeat_wrap_budget.py — отдельный файл
(owns scripts/tests/test_heartbeat_wrap*), не трогает существующие тесты.

Изоляция путей — урок BL-3 (budget-rework), расширенный этой спекой:
все пути (лок/reaps/escalations/sla/budget/fastdeath) под tmp_path;
регресс-щит в конце файла (пин 21) требует ОБА изолируемых пути
(budget_path, fastdeath_path) в `_paths()` ВСЕХ трёх сиблингов.

Контроль runtime — монкипатч `hw.time.monotonic` управляемой
последовательностью значений (`_mono`): первый вызов внутри run_pass —
t_spawn (сразу после успешного _popen), второй — в момент, когда rc
уже получен (runtime = второе значение − t_spawn). Ровно 2 вызова на
проход, доходящий до `rc = p.wait(...)` успешно; 1 вызов на
timeout-kill (t_spawn есть, runtime не считается); 0 вызовов на
spawn-failed/BUSY/ранние budget-выходы (до _popen код их не достигает).
"""
from __future__ import annotations

import datetime
import json
import sys

import pytest

import heartbeat_wrap as hw
import loop_lock as ll

NOW = datetime.datetime(2026, 8, 15, 12, 0, 0, tzinfo=datetime.timezone.utc)


def _sla(tmp_path, lock_stale=2):
    p = tmp_path / "state" / "sla.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"version: 1\nthresholds:\n  lock_stale: {lock_stale}\n", encoding="utf-8")
    return p


def _paths(tmp_path, budget=None, fastdeath=None, **sla_kw):
    """budget=None -> файла нет (безлимит), тот же контракт, что
    test_heartbeat_wrap_budget.py::_paths. fastdeath=None -> файла нет
    (свежий счётчик); строка/байты -> преднаписанное содержимое
    heartbeat-fastdeath.json (для пинов corrupt/prime-count)."""
    budget_path = tmp_path / "state" / "heartbeat-budget.txt"
    if budget is not None:
        budget_path.parent.mkdir(parents=True, exist_ok=True)
        budget_path.write_text(str(budget), encoding="utf-8")
    fastdeath_path = tmp_path / "state" / "heartbeat-fastdeath.json"
    if fastdeath is not None:
        fastdeath_path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(fastdeath, (bytes, bytearray)):
            fastdeath_path.write_bytes(fastdeath)
        else:
            fastdeath_path.write_text(fastdeath, encoding="utf-8")
    return {
        "lock_file": tmp_path / "state" / "loop.lock",
        "reaps_path": tmp_path / "state" / "loop-lock-reaps.json",
        "escalations_path": tmp_path / "state" / "escalations.md",
        "sla_path": _sla(tmp_path, **sla_kw),
        "budget_path": budget_path,
        "fastdeath_path": fastdeath_path,
    }


class FakeProc:
    def __init__(self, pid, wait_plan):
        self.pid = pid
        self._plan = list(wait_plan)

    def wait(self, timeout=None):
        if not self._plan:
            return 0
        step = self._plan.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


def _mono(values):
    """Монкипатч-заглушка time.monotonic: отдаёт значения по очереди,
    падает AssertionError при перерасходе (ловит несовпадение числа
    вызовов с ожиданием сценария)."""
    it = iter(values)

    def fn():
        try:
            return next(it)
        except StopIteration:
            raise AssertionError(
                "time.monotonic() вызван больше раз, чем тест предусмотрел значений")
    return fn


@pytest.fixture()
def orch_log(tmp_path, monkeypatch):
    import log_append as la
    log_path = tmp_path / "state" / "orchestrator-log.md"
    monkeypatch.setattr(la, "ORCH_LOG", log_path, raising=True)
    monkeypatch.setattr(la, "_verify_environment", lambda **kw: (True, ""), raising=True)
    return log_path


def _read(path):
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _dir_escalations_path(tmp_path):
    """Намеренно ДИРЕКТОРИЯ на месте state/escalations.md — реальный
    OSError (не монкипатч глобального os.replace: тот же os-модуль
    используется loop_lock для лока/reaps, монкипатч сломал бы acquire
    целиком) на read_bytes()/os.replace() внутри
    _write_singleton_escalation (класс BL-4, спека п.2а)."""
    p = tmp_path / "state" / "escalations.md"
    p.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------------------
# Пин 1: одна быстрая смерть -> count=1, эскалации нет, суффикс fastdeath=1
# ---------------------------------------------------------------------------

def test_single_fast_death_increments_without_escalation(tmp_path, orch_log, monkeypatch):
    p = _paths(tmp_path)
    monkeypatch.setattr(hw, "_popen", lambda args, env: FakeProc(pid=1, wait_plan=[1]),
                        raising=True)
    monkeypatch.setattr(hw.time, "monotonic", _mono([0.0, 1.0]), raising=True)

    rc = hw.run_pass(now=NOW, **p)

    assert rc == 0
    data = json.loads(p["fastdeath_path"].read_text(encoding="utf-8"))
    assert data["count"] == 1
    assert "HEARTBEAT-CHILD-DEATH" not in _read(p["escalations_path"])
    text = _read(orch_log)
    assert "fastdeath=1" in text
    assert "escalated" not in text


# ---------------------------------------------------------------------------
# B3 (критик rework attempt 2, решение Lead — чинить код, не спеку): пин
# семантики ts — `last_ts` персистируется как момент СМЕРТИ ребёнка
# (_utcnow() внутри _fastdeath_increment), НЕ `now` начала прохода.
# Монкипатчим hw._utcnow на значение, отличное от `now`, переданного в
# run_pass — last_ts обязан совпасть с моментом смерти, не со стартом.
# ---------------------------------------------------------------------------

def test_fastdeath_last_ts_is_death_moment_not_pass_start(tmp_path, orch_log, monkeypatch):
    p = _paths(tmp_path)
    monkeypatch.setattr(hw, "_popen", lambda args, env: FakeProc(pid=1, wait_plan=[1]),
                        raising=True)
    monkeypatch.setattr(hw.time, "monotonic", _mono([0.0, 1.0]), raising=True)

    death_moment = datetime.datetime(2026, 8, 15, 12, 5, 30, tzinfo=datetime.timezone.utc)
    monkeypatch.setattr(hw, "_utcnow", lambda: death_moment, raising=True)
    pass_start = NOW                                    # 2026-08-15T12:00:00Z != death_moment

    rc = hw.run_pass(now=pass_start, **p)

    assert rc == 0
    data = json.loads(p["fastdeath_path"].read_text(encoding="utf-8"))
    assert data["last_ts"] == "2026-08-15T12:05:30Z"
    assert data["last_ts"] != pass_start.strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Пин 2: x3 подряд -> эскалация, singleton (4-й повтор — строка одна)
# ---------------------------------------------------------------------------

def test_three_in_a_row_escalates_singleton_dedup_on_fourth(tmp_path, orch_log, monkeypatch):
    p = _paths(tmp_path)
    monkeypatch.setattr(hw, "_popen", lambda args, env: FakeProc(pid=1, wait_plan=[1]),
                        raising=True)

    for i in range(3):
        monkeypatch.setattr(hw.time, "monotonic", _mono([0.0, 1.0]), raising=True)
        hw.run_pass(now=NOW + datetime.timedelta(seconds=i), **p)

    esc = _read(p["escalations_path"])
    assert esc.count("HEARTBEAT-CHILD-DEATH") == 1
    assert "[heartbeat:child-death]" in esc
    text = _read(orch_log)
    assert "fastdeath=3 escalated" in text

    monkeypatch.setattr(hw.time, "monotonic", _mono([0.0, 1.0]), raising=True)
    hw.run_pass(now=NOW + datetime.timedelta(seconds=3), **p)

    esc2 = _read(p["escalations_path"])
    assert esc2.count("HEARTBEAT-CHILD-DEATH") == 1


# ---------------------------------------------------------------------------
# Пин 3: здоровый проход после серии -> count=0, fastdeath-reset,
# существующая эскалация НЕ тронута
# ---------------------------------------------------------------------------

def test_healthy_pass_after_series_resets_without_touching_escalation(
        tmp_path, orch_log, monkeypatch):
    p = _paths(tmp_path)
    monkeypatch.setattr(hw, "_popen", lambda args, env: FakeProc(pid=1, wait_plan=[1]),
                        raising=True)
    for i in range(3):
        monkeypatch.setattr(hw.time, "monotonic", _mono([0.0, 1.0]), raising=True)
        hw.run_pass(now=NOW + datetime.timedelta(seconds=i), **p)

    esc_before = _read(p["escalations_path"])
    assert "HEARTBEAT-CHILD-DEATH" in esc_before

    monkeypatch.setattr(hw, "_popen", lambda args, env: FakeProc(pid=2, wait_plan=[0]),
                        raising=True)
    monkeypatch.setattr(hw.time, "monotonic", _mono([0.0, 5.0]), raising=True)
    hw.run_pass(now=NOW + datetime.timedelta(seconds=10), **p)

    data = json.loads(p["fastdeath_path"].read_text(encoding="utf-8"))
    assert data["count"] == 0
    assert "fastdeath-reset" in _read(orch_log)
    esc_after = _read(p["escalations_path"])
    assert esc_after == esc_before


# ---------------------------------------------------------------------------
# Пин N5 (новый, критик rework attempt 2): здоровый проход (rc=0) при
# ОТСУТСТВУЮЩЕМ файле счётчика — файл НЕ создаётся (в отличие от пина 3,
# где серия уже была и файл существовал; здесь — самый первый тик машины).
# ---------------------------------------------------------------------------

def test_healthy_pass_with_absent_counter_file_does_not_create_it(
        tmp_path, orch_log, monkeypatch):
    p = _paths(tmp_path)                              # fastdeath=None -> файла нет
    monkeypatch.setattr(hw, "_popen", lambda args, env: FakeProc(pid=1, wait_plan=[0]),
                        raising=True)
    monkeypatch.setattr(hw.time, "monotonic", _mono([0.0, 5.0]), raising=True)

    rc = hw.run_pass(now=NOW, **p)

    assert rc == 0
    assert not p["fastdeath_path"].exists()
    text = _read(orch_log)
    assert "exit=0" in text
    assert "fastdeath-reset" not in text


# ---------------------------------------------------------------------------
# Пин 4: медленная смерть (runtime >= FAST_DEATH_SEC) -> счётчик сброшен
# ---------------------------------------------------------------------------

def test_slow_death_resets_counter(tmp_path, orch_log, monkeypatch):
    p = _paths(tmp_path, fastdeath=json.dumps(
        {"count": 2, "first_ts": "2026-08-15T10:00:00Z",
         "last_ts": "2026-08-15T10:00:00Z", "last_rc": 1}))
    monkeypatch.setattr(hw, "_popen", lambda args, env: FakeProc(pid=1, wait_plan=[1]),
                        raising=True)
    monkeypatch.setattr(hw.time, "monotonic", _mono([0.0, hw.FAST_DEATH_SEC + 50]),
                        raising=True)

    rc = hw.run_pass(now=NOW, **p)

    assert rc == 0
    data = json.loads(p["fastdeath_path"].read_text(encoding="utf-8"))
    assert data["count"] == 0
    assert "fastdeath-reset" in _read(orch_log)


# ---------------------------------------------------------------------------
# Пин 5: битый json счётчика -> трактован как 0, следующая смерть пишет 1
# ---------------------------------------------------------------------------

def test_corrupt_json_treated_as_zero_self_heals(tmp_path, orch_log, monkeypatch):
    p = _paths(tmp_path)
    p["fastdeath_path"].parent.mkdir(parents=True, exist_ok=True)
    p["fastdeath_path"].write_bytes(b"{not json")
    monkeypatch.setattr(hw, "_popen", lambda args, env: FakeProc(pid=1, wait_plan=[1]),
                        raising=True)
    monkeypatch.setattr(hw.time, "monotonic", _mono([0.0, 1.0]), raising=True)

    rc = hw.run_pass(now=NOW, **p)

    assert rc == 0
    data = json.loads(p["fastdeath_path"].read_text(encoding="utf-8"))
    assert data["count"] == 1


# ---------------------------------------------------------------------------
# Пин 23 (новый, критик rework attempt 2, B2): счётчик с не-числовым
# "count" ({"count":"abc"} / {"count":[1]}) — на ВЕТКЕ ИНКРЕМЕНТА (быстрая
# смерть) И на ВЕТКЕ СБРОСА (rc=0) — трактуется как 0 (спека п.2), наружу
# ничего не летит (ни TypeError, ни ValueError), M4-строка ЧЕСТНАЯ (не
# ложный `exit=error:invalid literal...`), лок снят.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_count", ["abc", [1]], ids=["string-abc", "list"])
def test_non_numeric_count_treated_as_zero_on_increment_branch(
        tmp_path, orch_log, monkeypatch, bad_count):
    p = _paths(tmp_path, fastdeath=json.dumps(
        {"count": bad_count, "first_ts": "t0", "last_ts": "t0", "last_rc": 1}))
    monkeypatch.setattr(hw, "_popen", lambda args, env: FakeProc(pid=1, wait_plan=[1]),
                        raising=True)
    monkeypatch.setattr(hw.time, "monotonic", _mono([0.0, 1.0]), raising=True)

    rc = hw.run_pass(now=NOW, **p)

    assert rc == 0
    data = json.loads(p["fastdeath_path"].read_text(encoding="utf-8"))
    assert data["count"] == 1                       # трактован как 0 -> инкремент даёт 1
    text = _read(orch_log)
    assert "exit=1 fastdeath=1" in text              # честная M4, не проглоченная ошибка типа
    assert "exit=error" not in text
    assert not p["lock_file"].exists()


@pytest.mark.parametrize("bad_count", ["abc", [1]], ids=["string-abc", "list"])
def test_non_numeric_count_treated_as_zero_on_reset_branch(
        tmp_path, orch_log, monkeypatch, bad_count):
    p = _paths(tmp_path, fastdeath=json.dumps(
        {"count": bad_count, "first_ts": "t0", "last_ts": "t0", "last_rc": 1}))
    monkeypatch.setattr(hw, "_popen", lambda args, env: FakeProc(pid=1, wait_plan=[0]),
                        raising=True)
    monkeypatch.setattr(hw.time, "monotonic", _mono([0.0, 1.0]), raising=True)

    rc = hw.run_pass(now=NOW, **p)

    assert rc == 0
    data = hw._read_fastdeath(p["fastdeath_path"])   # семантика через тот же читатель (B2)
    assert data["count"] == 0
    text = _read(orch_log)
    assert "exit=0" in text
    assert "fastdeath-reset" not in text             # УЖЕ трактован как 0 -> reset ничего не пишет
    assert "exit=error" not in text
    assert not p["lock_file"].exists()


# ---------------------------------------------------------------------------
# Пин 6: M-B — бюджет 3 -> быстрая смерть -> файл снова 3, budget-refunded
# ---------------------------------------------------------------------------

def test_fast_death_refunds_budget_full_cycle(tmp_path, orch_log, monkeypatch):
    p = _paths(tmp_path, budget=3)
    monkeypatch.setattr(hw, "_popen", lambda args, env: FakeProc(pid=1, wait_plan=[1]),
                        raising=True)
    monkeypatch.setattr(hw.time, "monotonic", _mono([0.0, 1.0]), raising=True)

    rc = hw.run_pass(now=NOW, **p)

    assert rc == 0
    assert p["budget_path"].read_text(encoding="utf-8") == "3"
    assert "budget-refunded" in _read(orch_log)


# ---------------------------------------------------------------------------
# Пин 7: оператор переписал бюджет во время прохода -> возврат от НОВОГО
# значения (не восстановление старого)
# ---------------------------------------------------------------------------

def test_refund_rereads_current_value_not_stale_snapshot(tmp_path, orch_log, monkeypatch):
    p = _paths(tmp_path, budget=3)

    class ClobberProc:
        def __init__(self, pid):
            self.pid = pid

        def wait(self, timeout=None):
            # симуляция: оператор переписал бюджет ПОКА claude «работал»
            # (между декрементом и смертью)
            p["budget_path"].write_text("7", encoding="utf-8")
            return 1

    monkeypatch.setattr(hw, "_popen", lambda args, env: ClobberProc(pid=1), raising=True)
    monkeypatch.setattr(hw.time, "monotonic", _mono([0.0, 1.0]), raising=True)

    rc = hw.run_pass(now=NOW, **p)

    assert rc == 0
    assert p["budget_path"].read_text(encoding="utf-8") == "8"    # 7+1, НЕ 3


# ---------------------------------------------------------------------------
# Пин 8 (переписан, критик rework attempt 2 — прежняя версия была
# вакуумной: budget=None означал, что _refund_budget вообще не
# вызывается, декремент не жёгся, refund не пытался ничего создать по
# тривиальной причине). Новый сценарий: бюджет ЕСТЬ (3), но оператор
# УДАЛЯЕТ файл ПОКА ребёнок «работает» (между декрементом и быстрой
# смертью) — _refund_budget обязан перечитать (получить unlimited) и
# пропустить возврат, не воссоздавая файл (удаление файла = «снять
# лимит», спека §«M-B»).
# ---------------------------------------------------------------------------

def test_refund_skipped_when_unlimited_and_file_not_created(tmp_path, orch_log, monkeypatch):
    p = _paths(tmp_path, budget=3)

    class DeletingProc:
        def __init__(self, pid):
            self.pid = pid

        def wait(self, timeout=None):
            p["budget_path"].unlink()      # оператор снял лимит, пока проход "работал"
            return 1

    monkeypatch.setattr(hw, "_popen", lambda args, env: DeletingProc(pid=1), raising=True)
    monkeypatch.setattr(hw.time, "monotonic", _mono([0.0, 1.0]), raising=True)

    rc = hw.run_pass(now=NOW, **p)

    assert rc == 0
    assert not p["budget_path"].exists()               # НЕ пересоздан
    text = _read(orch_log)
    assert "budget-refunded" not in text


# ---------------------------------------------------------------------------
# Пин 9: M-B негатив — медленная смерть -> возврата нет (сожжён честно)
# ---------------------------------------------------------------------------

def test_slow_death_does_not_refund_budget(tmp_path, orch_log, monkeypatch):
    p = _paths(tmp_path, budget=3)
    monkeypatch.setattr(hw, "_popen", lambda args, env: FakeProc(pid=1, wait_plan=[1]),
                        raising=True)
    monkeypatch.setattr(hw.time, "monotonic", _mono([0.0, hw.FAST_DEATH_SEC + 10]),
                        raising=True)

    rc = hw.run_pass(now=NOW, **p)

    assert rc == 0
    assert p["budget_path"].read_text(encoding="utf-8") == "2"
    assert "budget-refunded" not in _read(orch_log)


# ---------------------------------------------------------------------------
# Пин 10: singleton-хелпер после рефакторинга — формат budget-ветки
# байт-в-байт прежний (обобщение _write_budget_escalation)
# ---------------------------------------------------------------------------

def test_singleton_escalation_budget_format_unchanged_after_generalization(tmp_path):
    esc = tmp_path / "state" / "escalations.md"
    hw._write_singleton_escalation(esc, hw.HEARTBEAT_BUDGET_KEY, hw.HEARTBEAT_BUDGET_TAG,
                                   "тестовое сообщение budget", NOW)
    text = esc.read_text(encoding="utf-8")
    assert "**HEARTBEAT-BUDGET** [heartbeat:budget] — тестовое сообщение budget" in text

    hw._write_singleton_escalation(esc, hw.HEARTBEAT_BUDGET_KEY, hw.HEARTBEAT_BUDGET_TAG,
                                   "обновлённое сообщение", NOW + datetime.timedelta(minutes=1))
    text2 = esc.read_text(encoding="utf-8")
    assert text2.count("HEARTBEAT-BUDGET") == 1                  # singleton dedup
    assert "обновлённое сообщение" in text2


# ---------------------------------------------------------------------------
# Пин 11: быстрая смерть не сиротит лок — штатный finally/release исполнен
# ---------------------------------------------------------------------------

def test_fast_death_does_not_orphan_lock(tmp_path, orch_log, monkeypatch):
    p = _paths(tmp_path)
    monkeypatch.setattr(hw, "_popen", lambda args, env: FakeProc(pid=1, wait_plan=[1]),
                        raising=True)
    monkeypatch.setattr(hw.time, "monotonic", _mono([0.0, 1.0]), raising=True)

    rc = hw.run_pass(now=NOW, **p)

    assert rc == 0
    assert not p["lock_file"].exists()


# ---------------------------------------------------------------------------
# Пин 12: граница FAST_DEATH_SEC (M6) — НА границе (== FAST_DEATH_SEC) и
# ЗА ней (FAST_DEATH_SEC - 0.01)
# ---------------------------------------------------------------------------

def test_boundary_runtime_exactly_fast_death_sec_is_slow_death_reset(
        tmp_path, orch_log, monkeypatch):
    p = _paths(tmp_path, fastdeath=json.dumps(
        {"count": 1, "first_ts": "2026-08-15T10:00:00Z",
         "last_ts": "2026-08-15T10:00:00Z", "last_rc": 1}))
    monkeypatch.setattr(hw, "_popen", lambda args, env: FakeProc(pid=1, wait_plan=[1]),
                        raising=True)
    monkeypatch.setattr(hw.time, "monotonic", _mono([0.0, hw.FAST_DEATH_SEC]), raising=True)

    rc = hw.run_pass(now=NOW, **p)

    assert rc == 0
    data = json.loads(p["fastdeath_path"].read_text(encoding="utf-8"))
    assert data["count"] == 0
    assert "fastdeath-reset" in _read(orch_log)


def test_boundary_runtime_just_under_fast_death_sec_is_fast_death_increment(
        tmp_path, orch_log, monkeypatch):
    p = _paths(tmp_path)
    monkeypatch.setattr(hw, "_popen", lambda args, env: FakeProc(pid=1, wait_plan=[1]),
                        raising=True)
    monkeypatch.setattr(hw.time, "monotonic", _mono([0.0, hw.FAST_DEATH_SEC - 0.01]),
                        raising=True)

    rc = hw.run_pass(now=NOW, **p)

    assert rc == 0
    data = json.loads(p["fastdeath_path"].read_text(encoding="utf-8"))
    assert data["count"] == 1
    assert "fastdeath=1" in _read(orch_log)


# ---------------------------------------------------------------------------
# Пин 13: граница порога — count==2 без эскалации, count==3 с эскалацией
# ---------------------------------------------------------------------------

def test_threshold_boundary_count_2_no_escalation_count_3_escalates(
        tmp_path, orch_log, monkeypatch):
    p = _paths(tmp_path)
    monkeypatch.setattr(hw, "_popen", lambda args, env: FakeProc(pid=1, wait_plan=[1]),
                        raising=True)

    monkeypatch.setattr(hw.time, "monotonic", _mono([0.0, 1.0]), raising=True)
    hw.run_pass(now=NOW, **p)
    monkeypatch.setattr(hw.time, "monotonic", _mono([0.0, 1.0]), raising=True)
    hw.run_pass(now=NOW + datetime.timedelta(seconds=1), **p)

    assert "HEARTBEAT-CHILD-DEATH" not in _read(p["escalations_path"])
    data = json.loads(p["fastdeath_path"].read_text(encoding="utf-8"))
    assert data["count"] == 2

    monkeypatch.setattr(hw.time, "monotonic", _mono([0.0, 1.0]), raising=True)
    hw.run_pass(now=NOW + datetime.timedelta(seconds=2), **p)

    assert "HEARTBEAT-CHILD-DEATH" in _read(p["escalations_path"])
    data = json.loads(p["fastdeath_path"].read_text(encoding="utf-8"))
    assert data["count"] == 3


# ---------------------------------------------------------------------------
# Пин 14: порядок — счётчик записан ДО попытки записи эскалации
# ---------------------------------------------------------------------------

def test_fastdeath_increment_writes_counter_before_escalation_attempt(tmp_path, monkeypatch):
    p = _paths(tmp_path, fastdeath=json.dumps(
        {"count": 2, "first_ts": "2026-08-15T10:00:00Z",
         "last_ts": "2026-08-15T10:00:00Z", "last_rc": 1}))
    fastdeath_path = p["fastdeath_path"]
    seen_counts = []

    def boom_escalation(*a, **kw):
        seen_counts.append(json.loads(fastdeath_path.read_text(encoding="utf-8"))["count"])
        raise RuntimeError("escalation writer blew up (тестовый маркер порядка)")

    monkeypatch.setattr(hw, "_write_singleton_escalation", boom_escalation, raising=True)

    with pytest.raises(RuntimeError):
        hw._fastdeath_increment(fastdeath_path, p["escalations_path"], NOW, 1, 1.0)

    assert seen_counts == [3]                # счётчик уже персистирован ДО попытки эскалации


# ---------------------------------------------------------------------------
# Пин 15: класс BL-4 — писатель эскалаций бросает OSError -> run_pass rc=0,
# лок снят, M4-строка записана. ТРИ площадки.
# ---------------------------------------------------------------------------

def test_bl4_escalation_write_failure_does_not_orphan_lock_budget_corrupt(
        tmp_path, orch_log, monkeypatch, capsys):
    p = _paths(tmp_path, budget="abc")
    p["escalations_path"] = _dir_escalations_path(tmp_path)
    monkeypatch.setattr(hw, "_popen",
                        lambda args, env: pytest.fail("corrupt не должен запускать claude"),
                        raising=True)

    rc = hw.run_pass(now=NOW, **p)

    assert rc == 0
    assert not p["lock_file"].exists()
    assert "ESCALATION write failed" in capsys.readouterr().out
    assert "budget=corrupt" in _read(orch_log)


def test_bl4_escalation_write_failure_does_not_orphan_lock_budget_exhausted(
        tmp_path, orch_log, monkeypatch, capsys):
    p = _paths(tmp_path, budget=0)
    p["escalations_path"] = _dir_escalations_path(tmp_path)
    monkeypatch.setattr(hw, "_popen",
                        lambda args, env: pytest.fail("не должен запускаться"), raising=True)
    monkeypatch.setattr(hw, "_schtasks_disable", lambda: (0, "SUCCESS"), raising=True)

    rc = hw.run_pass(now=NOW, **p)

    assert rc == 0
    assert not p["lock_file"].exists()
    assert "ESCALATION write failed" in capsys.readouterr().out
    assert "budget<=0" in _read(orch_log)


def test_bl4_escalation_write_failure_does_not_orphan_lock_fastdeath_threshold(
        tmp_path, orch_log, monkeypatch, capsys):
    p = _paths(tmp_path, fastdeath=json.dumps(
        {"count": 2, "first_ts": "2026-08-15T10:00:00Z",
         "last_ts": "2026-08-15T10:00:00Z", "last_rc": 1}))
    p["escalations_path"] = _dir_escalations_path(tmp_path)
    monkeypatch.setattr(hw, "_popen", lambda args, env: FakeProc(pid=1, wait_plan=[1]),
                        raising=True)
    monkeypatch.setattr(hw.time, "monotonic", _mono([0.0, 1.0]), raising=True)

    rc = hw.run_pass(now=NOW, **p)

    assert rc == 0
    assert not p["lock_file"].exists()
    assert "ESCALATION write failed" in capsys.readouterr().out
    data = json.loads(p["fastdeath_path"].read_text(encoding="utf-8"))
    assert data["count"] == 3
    assert "fastdeath=3 escalated" in _read(orch_log)


# ---------------------------------------------------------------------------
# Пин 22 (новый, критик rework attempt 2, B1): escalations.md с
# НЕ-utf8 байтами (cp1251-текст — валиден как cp1251, невалиден как utf-8,
# read_bytes().decode("utf-8") бросает UnicodeDecodeError) на ВСЕХ ТРЁХ
# площадках -> rc=0, лок СНЯТ, M4-строка записана (класс BL-4 закрыт не
# только для OSError, но и для ValueError-подкласса декодирования).
# ---------------------------------------------------------------------------

def _cp1251_escalations_path(tmp_path):
    p = tmp_path / "state" / "escalations.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    # кириллица в cp1251 — валидные байты в этой кодировке, но НЕ валидная
    # utf-8-последовательность (одиночные байты 0x80-0xFF не образуют
    # корректный utf-8 continuation) -> read_bytes().decode("utf-8")
    # бросает UnicodeDecodeError.
    p.write_bytes("Существующая эскалация в cp1251, не utf-8".encode("cp1251"))
    return p


def test_bl4_non_utf8_escalations_does_not_orphan_lock_budget_corrupt(
        tmp_path, orch_log, monkeypatch, capsys):
    p = _paths(tmp_path, budget="abc")
    p["escalations_path"] = _cp1251_escalations_path(tmp_path)
    monkeypatch.setattr(hw, "_popen",
                        lambda args, env: pytest.fail("corrupt не должен запускать claude"),
                        raising=True)

    rc = hw.run_pass(now=NOW, **p)

    assert rc == 0
    assert not p["lock_file"].exists()
    assert "ESCALATION write failed" in capsys.readouterr().out
    assert "budget=corrupt" in _read(orch_log)


def test_bl4_non_utf8_escalations_does_not_orphan_lock_budget_exhausted(
        tmp_path, orch_log, monkeypatch, capsys):
    p = _paths(tmp_path, budget=0)
    p["escalations_path"] = _cp1251_escalations_path(tmp_path)
    monkeypatch.setattr(hw, "_popen",
                        lambda args, env: pytest.fail("не должен запускаться"), raising=True)
    monkeypatch.setattr(hw, "_schtasks_disable", lambda: (0, "SUCCESS"), raising=True)

    rc = hw.run_pass(now=NOW, **p)

    assert rc == 0
    assert not p["lock_file"].exists()
    assert "ESCALATION write failed" in capsys.readouterr().out
    assert "budget<=0" in _read(orch_log)


def test_bl4_non_utf8_escalations_does_not_orphan_lock_fastdeath_threshold(
        tmp_path, orch_log, monkeypatch, capsys):
    p = _paths(tmp_path, fastdeath=json.dumps(
        {"count": 2, "first_ts": "2026-08-15T10:00:00Z",
         "last_ts": "2026-08-15T10:00:00Z", "last_rc": 1}))
    p["escalations_path"] = _cp1251_escalations_path(tmp_path)
    monkeypatch.setattr(hw, "_popen", lambda args, env: FakeProc(pid=1, wait_plan=[1]),
                        raising=True)
    monkeypatch.setattr(hw.time, "monotonic", _mono([0.0, 1.0]), raising=True)

    rc = hw.run_pass(now=NOW, **p)

    assert rc == 0
    assert not p["lock_file"].exists()
    assert "ESCALATION write failed" in capsys.readouterr().out
    data = json.loads(p["fastdeath_path"].read_text(encoding="utf-8"))
    assert data["count"] == 3
    assert "fastdeath=3 escalated" in _read(orch_log)


# ---------------------------------------------------------------------------
# Пин 16: refund НЕ делается, если декремент упал OSError (budget_burned False)
# ---------------------------------------------------------------------------

def test_no_refund_when_decrement_raised_oserror(tmp_path, orch_log, monkeypatch, capsys):
    p = _paths(tmp_path, budget=3)
    monkeypatch.setattr(hw, "_popen", lambda args, env: FakeProc(pid=1, wait_plan=[1]),
                        raising=True)

    def boom_write_budget(path, value):
        raise OSError("disk full")

    monkeypatch.setattr(hw, "_write_budget", boom_write_budget, raising=True)
    monkeypatch.setattr(hw.time, "monotonic", _mono([0.0, 1.0]), raising=True)

    rc = hw.run_pass(now=NOW, **p)

    assert rc == 0
    assert p["budget_path"].read_text(encoding="utf-8") == "3"    # не тронут вовсе
    assert "budget-refunded" not in _read(orch_log)
    assert "BUDGET decrement failed" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Пин 17: сквозной пин обещания M-B (два тика) — budget=1 -> быстрая
# смерть -> второй тик ВСЁ ЕЩЁ запускает ребёнка, disable НЕ зван
# ---------------------------------------------------------------------------

def test_two_tick_promise_second_tick_still_launches_without_disable(
        tmp_path, orch_log, monkeypatch):
    p = _paths(tmp_path, budget=1)
    calls = []

    def fake_popen(args, env):
        calls.append(1)
        return FakeProc(pid=1, wait_plan=[1])

    monkeypatch.setattr(hw, "_popen", fake_popen, raising=True)
    monkeypatch.setattr(
        hw, "_schtasks_disable",
        lambda: pytest.fail("M-B: второй тик не должен видеть исчерпанный бюджет"),
        raising=True)

    monkeypatch.setattr(hw.time, "monotonic", _mono([0.0, 1.0]), raising=True)
    hw.run_pass(now=NOW, **p)

    assert p["budget_path"].read_text(encoding="utf-8") == "1"    # decrement 0 + refund 1
    assert len(calls) == 1

    monkeypatch.setattr(hw.time, "monotonic", _mono([0.0, 1.0]), raising=True)
    hw.run_pass(now=NOW + datetime.timedelta(minutes=1), **p)

    assert len(calls) == 2                                        # второй тик ТОЖЕ запустил ребёнка


# ---------------------------------------------------------------------------
# Пин 18: BUSY-тик не трогает счётчик (файл не создаётся) — явный no-op
# ---------------------------------------------------------------------------

def test_busy_tick_does_not_touch_fastdeath_file(tmp_path, orch_log, monkeypatch):
    p = _paths(tmp_path)
    ll.acquire(lock_file=p["lock_file"], reaps_path=p["reaps_path"],
              escalations_path=p["escalations_path"], sla_path=p["sla_path"],
              holder="heartbeat:other:aaaaaaaa", now=NOW)
    monkeypatch.setattr(hw, "_popen",
                        lambda args, env: pytest.fail("BUSY не должен запускать claude"),
                        raising=True)

    rc = hw.run_pass(now=NOW + datetime.timedelta(minutes=1), **p)

    assert rc == 0
    assert not p["fastdeath_path"].exists()


# ---------------------------------------------------------------------------
# Пин 19: spawn-failed инкрементит счётчик и не жжёт бюджет
# ---------------------------------------------------------------------------

def test_spawn_failed_increments_counter_without_burning_budget(tmp_path, orch_log, monkeypatch):
    p = _paths(tmp_path, budget=3)

    def boom(args, env):
        raise OSError("no such file or directory: claude.cmd")

    monkeypatch.setattr(hw, "_popen", boom, raising=True)

    rc = hw.run_pass(now=NOW, **p)

    assert rc == 0
    data = json.loads(p["fastdeath_path"].read_text(encoding="utf-8"))
    assert data["count"] == 1
    assert p["budget_path"].read_text(encoding="utf-8") == "3"
    orch = _read(orch_log)
    assert "spawn-failed" in orch
    assert "fastdeath=1" in orch


# ---------------------------------------------------------------------------
# Пин 20: M4-суффиксы — точный порядок строкой целиком
# ---------------------------------------------------------------------------

def test_m4_suffix_exact_order_fastdeath_escalated_budget_refunded_release(
        tmp_path, orch_log, monkeypatch):
    p = _paths(tmp_path, budget=3, fastdeath=json.dumps(
        {"count": 2, "first_ts": "2026-08-15T10:00:00Z",
         "last_ts": "2026-08-15T10:00:00Z", "last_rc": 1}))

    def fake_popen(args, *, env):
        proc = FakeProc(pid=1, wait_plan=[1])
        # к моменту finally holder лока уже не наш (fallback-сценарий M2,
        # тот же приём, что test_release_refused_expected_marks_outcome)
        p["lock_file"].write_text(
            json.dumps({"holder": "qa-loop:fallback-holder", "pid": 1,
                       "ts": "2026-08-15T12:00:05Z"}), encoding="utf-8")
        return proc

    monkeypatch.setattr(hw, "_popen", fake_popen, raising=True)
    monkeypatch.setattr(hw.time, "monotonic", _mono([0.0, 1.0]), raising=True)

    rc = hw.run_pass(now=NOW, **p)

    assert rc == 0
    orch = _read(orch_log)
    assert ("exit=1 fastdeath=3 escalated budget-refunded release=refused-expected"
            in orch)


# ---------------------------------------------------------------------------
# Регресс-пин дефолта (образец test_run_pass_default_budget_path_is_
# production_state)
# ---------------------------------------------------------------------------

def test_run_pass_default_fastdeath_path_is_production_state():
    assert hw.DEFAULT_FASTDEATH_PATH == hw.REPO / "state" / "heartbeat-fastdeath.json"


# ---------------------------------------------------------------------------
# Пин 21 (усилен, критик rework attempt 2): регресс-щит BL-3 расширен —
# ВСЕ sibling-модули несут В `_paths()` ОБА изолируемых пути (budget_path,
# fastdeath_path) — И значения реально указывают ВНУТРЬ tmp_path (щит
# против «ключ есть, значение боевое»: например, если кто-то по ошибке
# впишет `hw.DEFAULT_FASTDEATH_PATH` вместо `tmp_path / ...`, прежняя
# версия пина ("budget_path" in paths) этого бы не заметила).
# ---------------------------------------------------------------------------

def test_bl3_shield_all_sibling_modules_isolate_budget_and_fastdeath(tmp_path):
    import test_heartbeat_wrap as thw
    import test_heartbeat_wrap_budget as thwb

    modules = {
        "test_heartbeat_wrap": thw,
        "test_heartbeat_wrap_budget": thwb,
        "test_heartbeat_wrap_fastdeath": sys.modules[__name__],
    }
    for name, mod in modules.items():
        paths = mod._paths(tmp_path)
        for key in ("budget_path", "fastdeath_path"):
            assert key in paths, f"{name}: не изолирует {key}"
            assert str(paths[key]).startswith(str(tmp_path)), (
                f"{name}: {key}={paths[key]!r} указывает НЕ на tmp_path "
                "— возможна утечка на боевой файл")
