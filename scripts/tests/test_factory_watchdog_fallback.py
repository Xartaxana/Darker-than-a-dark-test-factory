"""Юнит-тесты ночного резерва (Д1, консолидированная секция
spec-factory-window v7, docs/tasks/factory-visible-window.md) поверх
scripts/factory_watchdog.py. Два слоя:

  A) `run_tick(..., reserve_runner=<fake>)` — TRIGGER-гейт (delay/
     night_fallback/бюджет/fastdeath-предикат/slowdeath-предикат/probe) и
     бухгалтерия состояния (стрики/тосты/notes) по КОНТРОЛИРУЕМОМУ исходу
     резервного прохода (`reserve_runner` — точка внедрения, добавленная
     ИМЕННО для этого слоя тестов).
  B) `fw._run_reserve_pass(...)` НАПРЯМУЮ (монкипатч `hw._popen`, реальные
     файлы под tmp_path) — CAS/guard two_empty (ТРИ условия), канал
     last-pass-summary (парсер/ts-сверка/битый JSON).

toast_fn — ТОЛЬКО заглушка `_NoToast` (слово оператора: живые тосты
шумят — ни одного живого тоста в этих прогонах)."""
from __future__ import annotations

import datetime
import json

import pytest

import factory_watchdog as fw
import heartbeat_wrap as hw
import log_append as la
import pass_summary as ps

NOW = datetime.datetime(2026, 8, 16, 23, 0, 0, tzinfo=datetime.timezone.utc)


@pytest.fixture(autouse=True)
def _isolate_log_append(tmp_path, monkeypatch):
    """permission-hygiene (critical, Б1 rework): с Б1 `run_fallback_pass`
    пишет M4-строку через `log_append.append_orchestrator` НА ВСЕХ исходах
    (busy/spawned/spawn_failed/timeout_kill) — этот модуль косвенно (через
    `fw._run_reserve_pass`) зовёт `hw.run_fallback_pass` НАПРЯМУЮ в
    "B"-слое тестов. `log_append.ORCH_LOG`/`_verify_environment` без
    монкипатча пишут в РЕАЛЬНЫЙ `state/orchestrator-log.md` репозитория —
    autouse-фикстура закрывает это на ВСЮ сьюту файла разом (не полагаясь
    на то, что каждый новый тест не забудет свой собственный монкипатч)."""
    log_path = tmp_path / "isolated-orchestrator-log.md"
    monkeypatch.setattr(la, "ORCH_LOG", log_path, raising=True)
    monkeypatch.setattr(la, "_verify_environment", lambda **kw: (True, ""), raising=True)
    return log_path


def _paths(tmp_path):
    return {
        "lock_file": tmp_path / "state" / "loop.lock",
        "mode_file": tmp_path / "state" / "factory-mode.json",
        "state_file": tmp_path / "state" / "factory-watchdog.json",
        "sla_file": tmp_path / "state" / "sla.yaml",
        "escalations_file": tmp_path / "state" / "escalations.md",
        "orchestrator_log": tmp_path / "state" / "orchestrator-log.md",
        "pass_summary_file": tmp_path / "state" / "last-pass-summary.json",
        "fastdeath_file": tmp_path / "state" / "heartbeat-fastdeath.json",
    }


def _write_sla(p, ttl=4):
    p["sla_file"].parent.mkdir(parents=True, exist_ok=True)
    p["sla_file"].write_text(
        f"version: 1\nthresholds:\n  lock_stale: 2\n  loop_lock_ttl_hours: {ttl}\n",
        encoding="utf-8")


def _write_mode(p, mode="active", updated_ts=None, passes_done=0, nonce="n1",
                budget_total=5, night_fallback=None, driver="factory-skill"):
    p["mode_file"].parent.mkdir(parents=True, exist_ok=True)
    data = {
        "mode": mode,
        "session_nonce": nonce,
        "updated_ts": updated_ts or NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "passes_done": passes_done,
        "budget_total": budget_total,
        "session_started_ts": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "heartbeat_note": "",
        "stopped_reason": "",
        "driver": driver,
    }
    if night_fallback is not None:
        data["night_fallback"] = night_fallback
    p["mode_file"].write_text(json.dumps(data), encoding="utf-8")


def _mode_snap_dict(mode="active", updated_ts=None, passes_done=0, nonce="n1"):
    return {"mode": mode, "updated_ts": updated_ts, "passes_done": passes_done,
           "session_nonce": nonce}


def _write_state(p, **fields):
    p["state_file"].parent.mkdir(parents=True, exist_ok=True)
    base = {
        "last_lock_snapshot": {"exists": False, "corrupt": False, "holder": None,
                               "ts": None, "raw_hash": None},
        "last_mode_snapshot": {"mode": None, "updated_ts": None, "passes_done": None,
                               "session_nonce": None},
        "last_progress_ts": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "last_alert_ts": None,
        "last_state": "ok",
        "notes": [],
        "stalled_since": None,
        "empty_streak": 0,
        "slowdeath_streak": 0,
        "slowdeath_last_ts": None,
        "slowdeath_stopped": False,
        "unknown_streak": 0,
        "last_fallback_ts": None,
        "last_fallback_toast_ts": None,
        "last_fastdeath_toast_ts": None,
        "last_slowdeath_toast_ts": None,
        "fallback_runs": 0,
        "self_write_snapshot": None,
        "fallback_holder": None,
    }
    base.update(fields)
    p["state_file"].write_text(json.dumps(base), encoding="utf-8")


class _NoToast:
    def __init__(self, shown=True):
        self.calls = []
        self.shown = shown

    def __call__(self, title, message):
        self.calls.append((title, message))
        return self.shown, "FAKE"


def _read_state(p):
    return json.loads(p["state_file"].read_text(encoding="utf-8"))


def _read_orch(p):
    if not p["orchestrator_log"].exists():
        return ""
    return p["orchestrator_log"].read_text(encoding="utf-8")


def _read_esc(p):
    if not p["escalations_file"].exists():
        return ""
    return p["escalations_file"].read_text(encoding="utf-8")


def _stalled_setup(p, *, stalled_since_minutes_ago, night_fallback=None, budget_total=5,
                   passes_done=0, extra_state=None):
    """Готовит state+mode так, что тик увидит mode активный STALLED
    (branch 3, no-lock ветка) с заданным возрастом эпизода."""
    _write_sla(p)
    started = NOW - datetime.timedelta(minutes=200)     # тишина явно > STALL_NO_LOCK(60)
    stalled_since = NOW - datetime.timedelta(minutes=stalled_since_minutes_ago)
    state_kwargs = dict(
        last_state="stalled", last_progress_ts=fw._fmt_ts(started),
        last_mode_snapshot=_mode_snap_dict("active", fw._fmt_ts(started), passes_done),
        stalled_since=fw._fmt_ts(stalled_since),
        last_alert_ts=fw._fmt_ts(NOW - datetime.timedelta(hours=5)),
    )
    if extra_state:
        state_kwargs.update(extra_state)
    _write_state(p, **state_kwargs)
    _write_mode(p, mode="active", updated_ts=fw._fmt_ts(started), night_fallback=night_fallback,
               budget_total=budget_total, passes_done=passes_done)


def _fake_runner_factory(calls, *, result=None, classification=None, cas_ok=None,
                         wrote_two_empty=False, telemetry_delta=1):
    def _runner(**kwargs):
        calls.append(kwargs)
        return {
            "result": result or {"outcome": "spawned", "child_rc": 0, "fast_death": False,
                                 "holder": "heartbeat:x:aaaa0000", "mode_write": {"passes_done": 1}},
            "classification": classification,
            "cas_ok": cas_ok,
            "wrote_two_empty": wrote_two_empty,
            "telemetry_delta": telemetry_delta,
        }
    return _runner


# ===========================================================================
# A1. Триггер — задержка (M6: до/на/за FALLBACK_DELAY_MIN=15)
# ===========================================================================

def test_trigger_skipped_before_delay(tmp_path):
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=14)
    calls = []
    fw.run_tick(now=NOW, toast_fn=_NoToast(), reserve_runner=_fake_runner_factory(calls), **p)
    assert calls == []


def test_trigger_fires_exactly_at_delay_boundary(tmp_path):
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=15)
    calls = []
    fw.run_tick(now=NOW, toast_fn=_NoToast(), reserve_runner=_fake_runner_factory(calls), **p)
    assert len(calls) == 1


def test_trigger_fires_after_delay(tmp_path):
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=30)
    calls = []
    fw.run_tick(now=NOW, toast_fn=_NoToast(), reserve_runner=_fake_runner_factory(calls), **p)
    assert len(calls) == 1


def test_trigger_first_tick_of_episode_never_fires(tmp_path):
    """stalled_since=None в state -> первый тик эпизода стартует stalled_since=now
    -> elapsed=0 < 15 -> резерв не стартует ДАЖЕ если mode STALLED уже сейчас."""
    p = _paths(tmp_path)
    _write_sla(p)
    started = NOW - datetime.timedelta(minutes=200)
    _write_state(p, last_state="ok", last_progress_ts=fw._fmt_ts(started),
                last_mode_snapshot=_mode_snap_dict("active", fw._fmt_ts(started)))
    _write_mode(p, mode="active", updated_ts=fw._fmt_ts(started))
    calls = []
    fw.run_tick(now=NOW, toast_fn=_NoToast(), reserve_runner=_fake_runner_factory(calls), **p)
    assert calls == []
    assert _read_state(p)["stalled_since"] == fw._fmt_ts(NOW)


# ===========================================================================
# A2. night_fallback: off / absent(=on) / on
# ===========================================================================

def test_night_fallback_off_skips_trigger_with_note(tmp_path):
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=30, night_fallback="off")
    calls = []
    fw.run_tick(now=NOW, toast_fn=_NoToast(), reserve_runner=_fake_runner_factory(calls), **p)
    assert calls == []
    assert any("night_fallback=off" in n for n in _read_state(p)["notes"])


def test_night_fallback_absent_key_defaults_to_on(tmp_path):
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=30, night_fallback=None)
    calls = []
    fw.run_tick(now=NOW, toast_fn=_NoToast(), reserve_runner=_fake_runner_factory(calls), **p)
    assert len(calls) == 1


def test_night_fallback_explicit_on(tmp_path):
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=30, night_fallback="on")
    calls = []
    fw.run_tick(now=NOW, toast_fn=_NoToast(), reserve_runner=_fake_runner_factory(calls), **p)
    assert len(calls) == 1


def test_mode_missing_no_reserve_at_all(tmp_path):
    """К3 п.8 (Д): mode-файла нет/нечитаем -> резерва НЕТ (ветка 1, не 3)."""
    p = _paths(tmp_path)
    _write_sla(p)
    _write_state(p, last_state="ok")
    calls = []
    fw.run_tick(now=NOW, toast_fn=_NoToast(), reserve_runner=_fake_runner_factory(calls), **p)
    assert calls == []
    assert _read_state(p)["last_state"] == "ok"


# ===========================================================================
# A3. Бюджет
# ===========================================================================

def test_budget_exhausted_skips_trigger(tmp_path):
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=30, budget_total=5, passes_done=5)
    calls = []
    fw.run_tick(now=NOW, toast_fn=_NoToast(), reserve_runner=_fake_runner_factory(calls), **p)
    assert calls == []
    assert any("бюджет доехал" in n for n in _read_state(p)["notes"])


def test_budget_available_fires_trigger(tmp_path):
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=30, budget_total=5, passes_done=4)
    calls = []
    fw.run_tick(now=NOW, toast_fn=_NoToast(), reserve_runner=_fake_runner_factory(calls), **p)
    assert len(calls) == 1


def test_budget_unlimited_none_fires_trigger(tmp_path):
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=30, budget_total=None, passes_done=999)
    calls = []
    fw.run_tick(now=NOW, toast_fn=_NoToast(), reserve_runner=_fake_runner_factory(calls), **p)
    assert len(calls) == 1


# ===========================================================================
# A3б. Б3 (критик-раунд Д1, rework attempt 2): защищённое int-приведение
# budget_total/passes_done в гейте бюджета — non-throwing (BL-4)
# ===========================================================================

def test_budget_total_numeric_string_does_not_crash_tick_and_fires_trigger(tmp_path):
    """budget_total='20' (ЧИСЛОВАЯ строка — оператор мог вписать в
    кавычках вручную) — коэрцируется int()'ом, НЕ роняет тик TypeError'ом
    на сравнении int<str, резерв стартует штатно (4 < 20), state
    обновляется."""
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=30, budget_total="20", passes_done=4)
    calls = []
    code = fw.run_tick(now=NOW, toast_fn=_NoToast(), reserve_runner=_fake_runner_factory(calls),
                       **p)
    assert code == 0
    assert len(calls) == 1
    state = _read_state(p)
    assert state["last_state"] == "stalled"                # state обновился штатно


def test_budget_total_non_numeric_garbage_blocks_reserve_with_corrupt_note(tmp_path):
    """budget_total='not-a-number' — НЕ коэрцируется -> corrupt-mode,
    резерв консервативно НЕ стартует (не рискуем прогнать мимо
    непрочитанного лимита), notes ЯВНО называют мусор оператору."""
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=30, budget_total="not-a-number", passes_done=0)
    calls = []
    code = fw.run_tick(now=NOW, toast_fn=_NoToast(), reserve_runner=_fake_runner_factory(calls),
                       **p)
    assert code == 0
    assert calls == []
    assert any("corrupt-mode" in n for n in _read_state(p)["notes"])


def test_passes_done_non_numeric_garbage_blocks_reserve_with_corrupt_note(tmp_path):
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=30, budget_total=5, passes_done="abc")
    calls = []
    code = fw.run_tick(now=NOW, toast_fn=_NoToast(), reserve_runner=_fake_runner_factory(calls),
                       **p)
    assert code == 0
    assert calls == []
    assert any("corrupt-mode" in n for n in _read_state(p)["notes"])


# ===========================================================================
# A4. fastdeath/slowdeath предикаты + probe (M6 границы count/6ч)
# ===========================================================================

def _write_fastdeath(p, count, last_ts):
    p["fastdeath_file"].parent.mkdir(parents=True, exist_ok=True)
    p["fastdeath_file"].write_text(json.dumps(
        {"count": count, "first_ts": last_ts, "last_ts": last_ts, "last_rc": 1}),
        encoding="utf-8")


def test_fastdeath_block_recent_skips_trigger(tmp_path):
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=30)
    _write_fastdeath(p, count=3, last_ts=fw._fmt_ts(NOW - datetime.timedelta(hours=1)))
    calls = []
    fw.run_tick(now=NOW, toast_fn=_NoToast(), reserve_runner=_fake_runner_factory(calls), **p)
    assert calls == []
    assert any("fastdeath-серия" in n for n in _read_state(p)["notes"])


def test_fastdeath_block_below_threshold_fires(tmp_path):
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=30)
    _write_fastdeath(p, count=2, last_ts=fw._fmt_ts(NOW - datetime.timedelta(minutes=5)))
    calls = []
    fw.run_tick(now=NOW, toast_fn=_NoToast(), reserve_runner=_fake_runner_factory(calls), **p)
    assert len(calls) == 1


def test_fastdeath_block_probe_after_6h_fires_despite_count(tmp_path):
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=30)
    _write_fastdeath(p, count=9, last_ts=fw._fmt_ts(NOW - datetime.timedelta(hours=6, seconds=1)))
    calls = []
    fw.run_tick(now=NOW, toast_fn=_NoToast(), reserve_runner=_fake_runner_factory(calls), **p)
    assert len(calls) == 1


def test_fastdeath_block_probe_boundary_exactly_6h_still_blocked(tmp_path):
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=30)
    _write_fastdeath(p, count=9, last_ts=fw._fmt_ts(NOW - datetime.timedelta(hours=6)))
    calls = []
    fw.run_tick(now=NOW, toast_fn=_NoToast(), reserve_runner=_fake_runner_factory(calls), **p)
    assert calls == []


def test_slowdeath_block_recent_skips_trigger(tmp_path):
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=30, extra_state={
        "slowdeath_streak": 3,
        "slowdeath_last_ts": fw._fmt_ts(NOW - datetime.timedelta(hours=1)),
    })
    calls = []
    fw.run_tick(now=NOW, toast_fn=_NoToast(), reserve_runner=_fake_runner_factory(calls), **p)
    assert calls == []
    assert any("slowdeath-серия" in n for n in _read_state(p)["notes"])


def test_slowdeath_block_probe_after_6h_fires(tmp_path):
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=30, extra_state={
        "slowdeath_streak": 3,
        "slowdeath_last_ts": fw._fmt_ts(NOW - datetime.timedelta(hours=6, seconds=1)),
    })
    calls = []
    fw.run_tick(now=NOW, toast_fn=_NoToast(), reserve_runner=_fake_runner_factory(calls), **p)
    assert len(calls) == 1


# ===========================================================================
# A5. Исходы резерва -> бухгалтерия стриков
# ===========================================================================

def test_outcome_busy_does_not_touch_any_streak(tmp_path):
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=30, extra_state={"empty_streak": 1})
    calls = []
    runner = _fake_runner_factory(
        calls, result={"outcome": "busy", "child_rc": None, "fast_death": False,
                      "holder": "x", "mode_write": None}, classification=None)
    fw.run_tick(now=NOW, toast_fn=_NoToast(), reserve_runner=runner, **p)
    state = _read_state(p)
    assert state["empty_streak"] == 1                    # не тронут
    assert state["fallback_runs"] == 1                   # telemetry_delta применён


def test_outcome_spawn_failed_does_not_touch_empty_or_slowdeath(tmp_path):
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=30, extra_state={"empty_streak": 1,
                                                                  "slowdeath_streak": 1})
    calls = []
    runner = _fake_runner_factory(
        calls, result={"outcome": "spawn_failed", "child_rc": None, "fast_death": True,
                      "holder": "x", "mode_write": None}, classification=None)
    fw.run_tick(now=NOW, toast_fn=_NoToast(), reserve_runner=runner, **p)
    state = _read_state(p)
    assert state["empty_streak"] == 1
    assert state["slowdeath_streak"] == 1


def test_outcome_timeout_kill_increments_slowdeath_only(tmp_path):
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=30)
    calls = []
    runner = _fake_runner_factory(
        calls, result={"outcome": "timeout_kill", "child_rc": None, "fast_death": False,
                      "holder": "x", "mode_write": None}, classification=None)
    fw.run_tick(now=NOW, toast_fn=_NoToast(), reserve_runner=runner, **p)
    state = _read_state(p)
    assert state["slowdeath_streak"] == 1
    assert state["slowdeath_last_ts"] == fw._fmt_ts(NOW)
    assert state["empty_streak"] == 0


def test_outcome_spawned_slow_nonzero_rc_increments_slowdeath_not_fastdeath(tmp_path):
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=30)
    calls = []
    runner = _fake_runner_factory(
        calls, result={"outcome": "spawned", "child_rc": 1, "fast_death": False,
                      "holder": "x", "mode_write": None}, classification=None)
    fw.run_tick(now=NOW, toast_fn=_NoToast(), reserve_runner=runner, **p)
    assert _read_state(p)["slowdeath_streak"] == 1


def test_outcome_spawned_success_resets_slowdeath_streak(tmp_path):
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=30, extra_state={
        "slowdeath_streak": 2, "slowdeath_last_ts": fw._fmt_ts(NOW), "slowdeath_stopped": False})
    calls = []
    runner = _fake_runner_factory(
        calls, result={"outcome": "spawned", "child_rc": 0, "fast_death": False,
                      "holder": "x", "mode_write": {"passes_done": 1}},
        classification="nonempty", cas_ok=True)
    fw.run_tick(now=NOW, toast_fn=_NoToast(), reserve_runner=runner, **p)
    state = _read_state(p)
    assert state["slowdeath_streak"] == 0
    assert state["slowdeath_last_ts"] is None
    assert state["empty_streak"] == 0


def test_outcome_spawned_success_empty_increments_empty_streak(tmp_path):
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=30, extra_state={"empty_streak": 0})
    calls = []
    runner = _fake_runner_factory(
        calls, result={"outcome": "spawned", "child_rc": 0, "fast_death": False,
                      "holder": "x", "mode_write": {"passes_done": 1}},
        classification="empty", cas_ok=True)
    fw.run_tick(now=NOW, toast_fn=_NoToast(), reserve_runner=runner, **p)
    assert _read_state(p)["empty_streak"] == 1


def test_outcome_spawned_success_unknown_channel_increments_unknown_streak(tmp_path):
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=30, extra_state={"unknown_streak": 0})
    calls = []
    runner = _fake_runner_factory(
        calls, result={"outcome": "spawned", "child_rc": 0, "fast_death": False,
                      "holder": "x", "mode_write": {"passes_done": 1}},
        classification="unknown", cas_ok=True)
    fw.run_tick(now=NOW, toast_fn=_NoToast(), reserve_runner=runner, **p)
    state = _read_state(p)
    assert state["unknown_streak"] == 1
    assert any("канал last-pass-summary неизвестен" in n for n in state["notes"])


def test_unknown_streak_reaches_threshold_toasts_channel_broken(tmp_path):
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=30, extra_state={"unknown_streak": 2})
    calls = []
    runner = _fake_runner_factory(
        calls, result={"outcome": "spawned", "child_rc": 0, "fast_death": False,
                      "holder": "x", "mode_write": {"passes_done": 1}},
        classification="unknown", cas_ok=True)
    toast = _NoToast()
    fw.run_tick(now=NOW, toast_fn=toast, reserve_runner=runner, **p)
    state = _read_state(p)
    assert state["unknown_streak"] == 3
    assert any("канал сводки прохода сломан" in n for n in state["notes"])
    assert any(c[0] == "[factory:fallback-channel]" for c in toast.calls)


# ===========================================================================
# A6. slowdeath-стоп: эскалация+тост один раз на эпизод, не пишет mode=stopped
# ===========================================================================

def test_slowdeath_reaching_threshold_escalates_and_toasts_once(tmp_path):
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=30, extra_state={
        "slowdeath_streak": 2, "slowdeath_stopped": False})
    calls = []
    runner = _fake_runner_factory(
        calls, result={"outcome": "timeout_kill", "child_rc": None, "fast_death": False,
                      "holder": "x", "mode_write": None})
    toast = _NoToast()
    fw.run_tick(now=NOW, toast_fn=toast, reserve_runner=runner, **p)
    state = _read_state(p)
    assert state["slowdeath_streak"] == 3
    assert state["slowdeath_stopped"] is True
    esc = _read_esc(p)
    assert "FACTORY-FALLBACK-BROKEN" in esc and "[factory:fallback-broken]" in esc
    assert any(c[0] == "[factory:fallback-broken]" for c in toast.calls)
    # mode-файл НЕ тронут этим механизмом (slowdeath-стоп не пишет mode=stopped)
    mode_after = json.loads(p["mode_file"].read_text(encoding="utf-8"))
    assert mode_after["mode"] == "active"


def test_slowdeath_stop_does_not_re_toast_on_subsequent_still_blocked_ticks(tmp_path):
    """slowdeath_streak уже >= порога И slowdeath_stopped уже True (эпизод
    уже объявлен) -> сама блокирующая ветка (A4) даже не доходит до
    reserve_runner (блокировка предикатом) -> тост не зовётся повторно."""
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=30, extra_state={
        "slowdeath_streak": 3, "slowdeath_stopped": True,
        "slowdeath_last_ts": fw._fmt_ts(NOW - datetime.timedelta(minutes=1)),
    })
    calls = []
    toast = _NoToast()
    fw.run_tick(now=NOW, toast_fn=toast, reserve_runner=_fake_runner_factory(calls), **p)
    assert calls == []
    assert not toast.calls


# ===========================================================================
# A6б. fastdeath-стоп: тост + СВОЙ кулдаун (last_fastdeath_toast_ts) —
# симметрично slowdeath-стопу выше
# ===========================================================================

def _runner_bumping_fastdeath_to(p, new_count, telemetry_delta=1):
    """Фейковый reserve_runner, симулирующий побочный эффект РЕАЛЬНОГО
    `_run_child` — фактическую запись heartbeat-fastdeath.json с count=
    new_count (гейт ДО запуска смотрит на count ДО этого прохода —
    предзаселяем count=new_count-1, ниже порога, чтобы гейт пропустил;
    сам "проход" поднимает count до new_count)."""
    def _runner(**kwargs):
        p["fastdeath_file"].parent.mkdir(parents=True, exist_ok=True)
        p["fastdeath_file"].write_text(json.dumps(
            {"count": new_count, "first_ts": fw._fmt_ts(NOW), "last_ts": fw._fmt_ts(NOW),
             "last_rc": 1}), encoding="utf-8")
        return {
            "result": {"outcome": "spawned", "child_rc": 1, "fast_death": True,
                      "holder": "x", "mode_write": None},
            "classification": None, "cas_ok": None, "wrote_two_empty": False,
            "telemetry_delta": telemetry_delta,
        }
    return _runner


def test_fastdeath_reaching_threshold_toasts_with_own_cooldown_field(tmp_path):
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=30)
    _write_fastdeath(p, count=2, last_ts=fw._fmt_ts(NOW - datetime.timedelta(minutes=5)))
    toast = _NoToast()
    fw.run_tick(now=NOW, toast_fn=toast, reserve_runner=_runner_bumping_fastdeath_to(p, 3), **p)
    state = _read_state(p)
    assert state["last_fastdeath_toast_ts"] == fw._fmt_ts(NOW)
    assert any(c[0] == "[factory:child-death]" for c in toast.calls)


def test_fastdeath_toast_respects_own_cooldown_independent_of_slowdeath(tmp_path):
    """last_slowdeath_toast_ts свежий (СВОЙ кулдаун другого класса) НЕ
    подавляет fastdeath-тост — и наоборот, доказываем независимость двух
    полей друг от друга."""
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=30, extra_state={
        "last_slowdeath_toast_ts": fw._fmt_ts(NOW - datetime.timedelta(minutes=1)),
        "last_fastdeath_toast_ts": None,
    })
    _write_fastdeath(p, count=2, last_ts=fw._fmt_ts(NOW - datetime.timedelta(minutes=5)))
    toast = _NoToast()
    fw.run_tick(now=NOW, toast_fn=toast, reserve_runner=_runner_bumping_fastdeath_to(p, 3), **p)
    assert any(c[0] == "[factory:child-death]" for c in toast.calls)   # НЕ подавлен


def test_fastdeath_toast_cooldown_suppresses_repeat_within_window(tmp_path):
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=30, extra_state={
        "last_fastdeath_toast_ts": fw._fmt_ts(NOW - datetime.timedelta(hours=1)),
    })
    _write_fastdeath(p, count=2, last_ts=fw._fmt_ts(NOW - datetime.timedelta(minutes=5)))
    toast = _NoToast()
    fw.run_tick(now=NOW, toast_fn=toast, reserve_runner=_runner_bumping_fastdeath_to(p, 4), **p)
    assert not any(c[0] == "[factory:child-death]" for c in toast.calls)


# ===========================================================================
# A7. Независимость 4 классов кулдаунов тостов
# ===========================================================================

def test_fallback_launch_toast_cooldown_independent_of_alert_cooldown(tmp_path):
    """last_alert_ts свежий (в кулдауне тревоги) НЕ подавляет тост запуска
    резерва — свой собственный кулдаун (last_fallback_toast_ts)."""
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=30, extra_state={
        "last_alert_ts": fw._fmt_ts(NOW - datetime.timedelta(minutes=1)),   # тревога только что была
        "last_fallback_toast_ts": None,
    })
    calls = []
    runner = _fake_runner_factory(
        calls, result={"outcome": "spawned", "child_rc": 0, "fast_death": False,
                      "holder": "x", "mode_write": {"passes_done": 1}},
        classification="nonempty", cas_ok=True)
    toast = _NoToast()
    fw.run_tick(now=NOW, toast_fn=toast, reserve_runner=runner, **p)
    assert any(c[0] == "[factory:fallback]" for c in toast.calls)


def test_fallback_launch_toast_fires_on_every_launch_no_4h_cooldown(tmp_path):
    """Н3 (Lead-решение, критик-раунд Д1): тост запуска резерва — ОДИН НА
    КАЖДЫЙ запуск (семантика спеки), НЕ 4ч-кулдаун — свежий
    `last_fallback_toast_ts` (1 мин назад) НЕ подавляет следующий
    легитимный запуск (этот код-путь и так исполняется ≤1 раз/тик —
    гейт делает своё дело; поле остаётся диагностической меткой)."""
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=30, extra_state={
        "last_fallback_toast_ts": fw._fmt_ts(NOW - datetime.timedelta(minutes=1)),
    })
    calls = []
    runner = _fake_runner_factory(
        calls, result={"outcome": "spawned", "child_rc": 0, "fast_death": False,
                      "holder": "x", "mode_write": {"passes_done": 1}},
        classification="nonempty", cas_ok=True)
    toast = _NoToast()
    fw.run_tick(now=NOW, toast_fn=toast, reserve_runner=runner, **p)
    assert any(c[0] == "[factory:fallback]" for c in toast.calls)


def test_fallback_launch_toast_updates_diagnostic_ts_field(tmp_path):
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=30, extra_state={
        "last_fallback_toast_ts": None,
    })
    calls = []
    runner = _fake_runner_factory(
        calls, result={"outcome": "spawned", "child_rc": 0, "fast_death": False,
                      "holder": "x", "mode_write": {"passes_done": 1}},
        classification="nonempty", cas_ok=True)
    fw.run_tick(now=NOW, toast_fn=_NoToast(shown=True), reserve_runner=runner, **p)
    assert _read_state(p)["last_fallback_toast_ts"] == fw._fmt_ts(NOW)


# ===========================================================================
# B. _run_reserve_pass напрямую — CAS/guard two_empty, канал last-pass-summary
# ===========================================================================

class _FakeProc:
    def __init__(self, pid, rc=0):
        self.pid = pid
        self._rc = rc

    def wait(self, timeout=None):
        return self._rc


def _base_reserve_kwargs(p, tmp_path, target_nonce="n1", current_empty_streak=0):
    return dict(
        lock_file=p["lock_file"], reaps_path=tmp_path / "state" / "loop-lock-reaps.json",
        escalations_path=p["escalations_file"], sla_path=p["sla_file"],
        fastdeath_path=p["fastdeath_file"], pass_summary_path=p["pass_summary_file"],
        mode_file=p["mode_file"], target_nonce=target_nonce,
        current_empty_streak=current_empty_streak, now=NOW, log_path=None,
    )


def test_reserve_pass_cas_increments_passes_done(tmp_path, monkeypatch):
    p = _paths(tmp_path)
    _write_sla(p)
    _write_mode(p, mode="active", passes_done=3, nonce="n1", driver="watchdog-fallback")
    monkeypatch.setattr(hw, "_popen", lambda args, **kw: _FakeProc(pid=1, rc=0), raising=True)
    ps.write_summary(triggered=1, deferred=0, rescan_delta=0,
                     output_path=p["pass_summary_file"], now=NOW)

    out = fw._run_reserve_pass(**_base_reserve_kwargs(p, tmp_path))

    assert out["result"]["outcome"] == "spawned"
    assert out["result"]["child_rc"] == 0
    assert out["cas_ok"] is True
    assert out["classification"] == "nonempty"
    mode_after = json.loads(p["mode_file"].read_text(encoding="utf-8"))
    assert mode_after["passes_done"] == 4
    assert mode_after["driver"] == "watchdog-fallback"


def test_reserve_pass_cas_fails_on_nonce_mismatch_takeover(tmp_path, monkeypatch):
    p = _paths(tmp_path)
    _write_sla(p)
    _write_mode(p, mode="active", passes_done=3, nonce="DIFFERENT-TAKEOVER-NONCE")
    monkeypatch.setattr(hw, "_popen", lambda args, **kw: _FakeProc(pid=1, rc=0), raising=True)
    ps.write_summary(triggered=0, deferred=0, rescan_delta=0,
                     output_path=p["pass_summary_file"], now=NOW)

    out = fw._run_reserve_pass(**_base_reserve_kwargs(p, tmp_path, target_nonce="n1"))

    assert out["cas_ok"] is False
    mode_after = json.loads(p["mode_file"].read_text(encoding="utf-8"))
    assert mode_after["passes_done"] == 3          # НЕ тронут — не наш эпизод


def test_reserve_pass_cas_fails_when_mode_became_stopped_mid_pass(tmp_path, monkeypatch):
    p = _paths(tmp_path)
    _write_sla(p)
    _write_mode(p, mode="stopped", passes_done=3, nonce="n1")
    monkeypatch.setattr(hw, "_popen", lambda args, **kw: _FakeProc(pid=1, rc=0), raising=True)
    ps.write_summary(triggered=0, deferred=0, rescan_delta=0,
                     output_path=p["pass_summary_file"], now=NOW)

    out = fw._run_reserve_pass(**_base_reserve_kwargs(p, tmp_path, target_nonce="n1"))

    assert out["cas_ok"] is False
    mode_after = json.loads(p["mode_file"].read_text(encoding="utf-8"))
    assert mode_after["passes_done"] == 3


def test_two_empty_guard_writes_stop_when_all_three_conditions_hold(tmp_path, monkeypatch):
    p = _paths(tmp_path)
    _write_sla(p)
    _write_mode(p, mode="active", passes_done=3, nonce="n1", driver="watchdog-fallback")
    monkeypatch.setattr(hw, "_popen", lambda args, **kw: _FakeProc(pid=1, rc=0), raising=True)
    ps.write_summary(triggered=0, deferred=0, rescan_delta=0,
                     output_path=p["pass_summary_file"], now=NOW)

    out = fw._run_reserve_pass(**_base_reserve_kwargs(p, tmp_path, target_nonce="n1",
                                                       current_empty_streak=1))

    assert out["classification"] == "empty"
    assert out["wrote_two_empty"] is True
    mode_after = json.loads(p["mode_file"].read_text(encoding="utf-8"))
    assert mode_after["mode"] == "stopped"
    assert mode_after["stopped_reason"] == "two_empty"
    assert mode_after["passes_done"] == 4           # ОДНА запись — инкремент И стоп вместе


def test_two_empty_guard_busy_pulse_cancels_stop_condition_v(tmp_path, monkeypatch):
    """DoD-юнит: «BUSY-пульс окна во время прохода отменяет two_empty» —
    driver в mode-файле показывает "factory-skill" (окно живо пульсировало,
    в т.ч. BUSY-попыткой) -> guard-условие (в) не выполнено -> two_empty
    НЕ пишется, обычный инкремент passes_done — да."""
    p = _paths(tmp_path)
    _write_sla(p)
    _write_mode(p, mode="active", passes_done=3, nonce="n1", driver="factory-skill")
    monkeypatch.setattr(hw, "_popen", lambda args, **kw: _FakeProc(pid=1, rc=0), raising=True)
    ps.write_summary(triggered=0, deferred=0, rescan_delta=0,
                     output_path=p["pass_summary_file"], now=NOW)

    out = fw._run_reserve_pass(**_base_reserve_kwargs(p, tmp_path, target_nonce="n1",
                                                       current_empty_streak=1))

    assert out["wrote_two_empty"] is False
    mode_after = json.loads(p["mode_file"].read_text(encoding="utf-8"))
    assert mode_after["mode"] == "active"          # НЕ остановлен
    assert mode_after["passes_done"] == 4           # но инкремент прошёл


def test_two_empty_guard_first_empty_pass_does_not_stop(tmp_path, monkeypatch):
    """current_empty_streak=0 -> prospective=1 < EMPTY_STREAK_STOP(2) ->
    НЕ стоп (нужны ДВА пустых подряд)."""
    p = _paths(tmp_path)
    _write_sla(p)
    _write_mode(p, mode="active", passes_done=3, nonce="n1", driver="watchdog-fallback")
    monkeypatch.setattr(hw, "_popen", lambda args, **kw: _FakeProc(pid=1, rc=0), raising=True)
    ps.write_summary(triggered=0, deferred=0, rescan_delta=0,
                     output_path=p["pass_summary_file"], now=NOW)

    out = fw._run_reserve_pass(**_base_reserve_kwargs(p, tmp_path, target_nonce="n1",
                                                       current_empty_streak=0))

    assert out["wrote_two_empty"] is False
    mode_after = json.loads(p["mode_file"].read_text(encoding="utf-8"))
    assert mode_after["mode"] == "active"


# ---------------------------------------------------------------------------
# Б3 (критик-раунд Д1, rework attempt 2): passes_done='0' (числовая
# СТРОКА) не глушит CAS/two_empty — критик-сценарий, ДВА тика подряд
# ---------------------------------------------------------------------------

def test_passes_done_string_zero_does_not_silence_cas_across_two_ticks(tmp_path, monkeypatch):
    """mode-файл несёт `passes_done: "0"` (строка — прежний идиом `value
    or 0` НЕ срабатывал бы: непустая строка truthy, мусорный str утекал в
    `+1` арифметику -> TypeError). Тик 1: CAS проходит, passes_done
    записывается int'ом (1), streak=1 < 2 -> НЕ стоп. Тик 2 (тот же
    сценарий, пустой снова): streak достигает 2 -> two_empty пишется той
    же (единственной) записью, что CAS-инкремент."""
    p = _paths(tmp_path)
    _write_sla(p)
    _write_mode(p, mode="active", passes_done="0", nonce="n1", driver="watchdog-fallback")
    monkeypatch.setattr(hw, "_popen", lambda args, **kw: _FakeProc(pid=1, rc=0), raising=True)
    ps.write_summary(triggered=0, deferred=0, rescan_delta=0,
                     output_path=p["pass_summary_file"], now=NOW)

    out1 = fw._run_reserve_pass(**_base_reserve_kwargs(p, tmp_path, target_nonce="n1",
                                                        current_empty_streak=0))
    assert out1["cas_ok"] is True
    assert out1["classification"] == "empty"
    assert out1["wrote_two_empty"] is False
    mode_after1 = json.loads(p["mode_file"].read_text(encoding="utf-8"))
    assert mode_after1["passes_done"] == 1              # int, НЕ строка/крах
    assert mode_after1["mode"] == "active"

    later = NOW + datetime.timedelta(minutes=100)
    ps.write_summary(triggered=0, deferred=0, rescan_delta=0,
                     output_path=p["pass_summary_file"], now=later)
    out2 = fw._run_reserve_pass(**_base_reserve_kwargs(p, tmp_path, target_nonce="n1",
                                                        current_empty_streak=1), )

    assert out2["cas_ok"] is True
    assert out2["classification"] == "empty"
    assert out2["wrote_two_empty"] is True
    mode_after2 = json.loads(p["mode_file"].read_text(encoding="utf-8"))
    assert mode_after2["mode"] == "stopped"
    assert mode_after2["stopped_reason"] == "two_empty"
    assert mode_after2["passes_done"] == 2


def test_passes_done_non_numeric_garbage_in_cas_treated_as_zero_with_stderr_note(
        tmp_path, monkeypatch, capsys):
    """passes_done='abc' (мусор, не число вовсе) -> трактован как 0
    (печатается предупреждение — оператор видит), CAS всё равно
    применяется (инкремент от 0), НЕ роняется."""
    p = _paths(tmp_path)
    _write_sla(p)
    _write_mode(p, mode="active", passes_done="abc", nonce="n1", driver="watchdog-fallback")
    monkeypatch.setattr(hw, "_popen", lambda args, **kw: _FakeProc(pid=1, rc=0), raising=True)
    ps.write_summary(triggered=1, deferred=0, rescan_delta=0,
                     output_path=p["pass_summary_file"], now=NOW)

    out = fw._run_reserve_pass(**_base_reserve_kwargs(p, tmp_path, target_nonce="n1"))

    assert out["cas_ok"] is True
    mode_after = json.loads(p["mode_file"].read_text(encoding="utf-8"))
    assert mode_after["passes_done"] == 1
    assert "нечисловой" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Б3: blanket except в on_pass_done — non-throwing (BL-4), лок НЕ сиротится
# ---------------------------------------------------------------------------

def test_on_pass_done_internal_exception_is_non_throwing_and_does_not_orphan_lock(
        tmp_path, monkeypatch, capsys):
    p = _paths(tmp_path)
    _write_sla(p)
    _write_mode(p, mode="active", passes_done=0, nonce="n1")
    monkeypatch.setattr(hw, "_popen", lambda args, **kw: _FakeProc(pid=1, rc=0), raising=True)
    monkeypatch.setattr(
        fw, "_classify_pass_summary",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom-classify")), raising=True)

    out = fw._run_reserve_pass(**_base_reserve_kwargs(p, tmp_path, target_nonce="n1"))

    assert out["result"]["outcome"] == "spawned"
    assert out["result"]["child_rc"] == 0
    assert out["cas_ok"] is None                 # исключение случилось ДО постановки флага
    assert not p["lock_file"].exists()            # лок НЕ осиротел
    assert "on_pass_done unexpected error" in capsys.readouterr().out
    mode_after = json.loads(p["mode_file"].read_text(encoding="utf-8"))
    assert mode_after["passes_done"] == 0          # запись НЕ применилась (честный non-throwing отказ)


# ---------------------------------------------------------------------------
# Канал last-pass-summary — парсер/ts-сверка/битый JSON
# ---------------------------------------------------------------------------

def test_channel_missing_file_is_unknown(tmp_path, monkeypatch):
    p = _paths(tmp_path)
    _write_sla(p)
    _write_mode(p, mode="active", nonce="n1", driver="watchdog-fallback")
    monkeypatch.setattr(hw, "_popen", lambda args, **kw: _FakeProc(pid=1, rc=0), raising=True)
    # pass_summary_file НЕ создан вовсе

    out = fw._run_reserve_pass(**_base_reserve_kwargs(p, tmp_path, target_nonce="n1"))

    assert out["classification"] == "unknown"


def test_channel_corrupt_json_is_unknown(tmp_path, monkeypatch):
    p = _paths(tmp_path)
    _write_sla(p)
    _write_mode(p, mode="active", nonce="n1", driver="watchdog-fallback")
    monkeypatch.setattr(hw, "_popen", lambda args, **kw: _FakeProc(pid=1, rc=0), raising=True)
    p["pass_summary_file"].parent.mkdir(parents=True, exist_ok=True)
    p["pass_summary_file"].write_bytes(b"{not json")

    out = fw._run_reserve_pass(**_base_reserve_kwargs(p, tmp_path, target_nonce="n1"))

    assert out["classification"] == "unknown"


def test_channel_stale_ts_before_pass_start_is_unknown(tmp_path, monkeypatch):
    """ts протух (от предыдущего, УЖЕ завершённого прохода) -> НЕ пусто,
    неизвестно."""
    p = _paths(tmp_path)
    _write_sla(p)
    _write_mode(p, mode="active", nonce="n1", driver="watchdog-fallback")
    monkeypatch.setattr(hw, "_popen", lambda args, **kw: _FakeProc(pid=1, rc=0), raising=True)
    stale_ts = NOW - datetime.timedelta(hours=2)
    ps.write_summary(triggered=0, deferred=0, rescan_delta=0,
                     output_path=p["pass_summary_file"], now=stale_ts)

    out = fw._run_reserve_pass(**_base_reserve_kwargs(p, tmp_path, target_nonce="n1"))

    assert out["classification"] == "unknown"


def test_channel_fresh_ts_at_pass_start_boundary_is_valid(tmp_path, monkeypatch):
    p = _paths(tmp_path)
    _write_sla(p)
    _write_mode(p, mode="active", nonce="n1", driver="watchdog-fallback")
    monkeypatch.setattr(hw, "_popen", lambda args, **kw: _FakeProc(pid=1, rc=0), raising=True)
    ps.write_summary(triggered=0, deferred=0, rescan_delta=0,
                     output_path=p["pass_summary_file"], now=NOW)     # ровно now

    out = fw._run_reserve_pass(**_base_reserve_kwargs(p, tmp_path, target_nonce="n1"))

    assert out["classification"] == "empty"


def test_channel_nonzero_fields_is_nonempty(tmp_path, monkeypatch):
    p = _paths(tmp_path)
    _write_sla(p)
    _write_mode(p, mode="active", nonce="n1", driver="watchdog-fallback")
    monkeypatch.setattr(hw, "_popen", lambda args, **kw: _FakeProc(pid=1, rc=0), raising=True)
    ps.write_summary(triggered=0, deferred=2, rescan_delta=0,
                     output_path=p["pass_summary_file"], now=NOW)

    out = fw._run_reserve_pass(**_base_reserve_kwargs(p, tmp_path, target_nonce="n1"))

    assert out["classification"] == "nonempty"


# ---------------------------------------------------------------------------
# on_spawn телеметрия — busy НЕ инкрементирует
# ---------------------------------------------------------------------------

def test_reserve_pass_busy_does_not_touch_telemetry(tmp_path):
    p = _paths(tmp_path)
    _write_sla(p)
    _write_mode(p, mode="active", nonce="n1")
    import loop_lock as ll
    ll.acquire(lock_file=p["lock_file"], reaps_path=tmp_path / "state" / "loop-lock-reaps.json",
              escalations_path=p["escalations_file"], sla_path=p["sla_file"],
              holder="qa-loop:other", now=NOW)

    out = fw._run_reserve_pass(**_base_reserve_kwargs(p, tmp_path, target_nonce="n1"))

    assert out["result"]["outcome"] == "busy"
    assert out["telemetry_delta"] == 0


# ===========================================================================
# Н1 (Lead-решение, критик-раунд Д1): fallback_runs/fallback_runs_24h —
# инкремент В STATE-ФАЙЛЕ ДО Popen (не только в памяти)
# ===========================================================================

def test_on_spawn_writes_fallback_runs_to_state_file_before_popen(tmp_path, monkeypatch):
    p = _paths(tmp_path)
    state_file = tmp_path / "state" / "factory-watchdog.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    old_window = [fw._fmt_ts(NOW - datetime.timedelta(hours=1)),
                 fw._fmt_ts(NOW - datetime.timedelta(hours=2))]
    state_file.write_text(json.dumps({"fallback_runs": 5, "fallback_runs_24h": 2,
                                      "fallback_runs_24h_ts": old_window}), encoding="utf-8")
    _write_mode(p, mode="active", nonce="n1")
    seen = {}

    def fake_popen(args, **kw):
        # Пикаем state-файл РОВНО в момент вызова Popen — on_spawn (через
        # pre_spawn) обязан был выполниться и записать ДО этого момента.
        seen["fallback_runs_at_popen_time"] = json.loads(
            state_file.read_text(encoding="utf-8"))["fallback_runs"]
        return _FakeProc(pid=1, rc=0)

    monkeypatch.setattr(hw, "_popen", fake_popen, raising=True)
    ps.write_summary(triggered=0, deferred=0, rescan_delta=0,
                     output_path=p["pass_summary_file"], now=NOW)

    kwargs = _base_reserve_kwargs(p, tmp_path, target_nonce="n1")
    kwargs["state_file"] = state_file
    fw._run_reserve_pass(**kwargs)

    assert seen["fallback_runs_at_popen_time"] == 6       # уже инкрементирован ДО Popen
    final = json.loads(state_file.read_text(encoding="utf-8"))
    assert final["fallback_runs"] == 6
    assert final["fallback_runs_24h"] == 3                # 2 старых (в окне) + 1 новый
    assert len(final["fallback_runs_24h_ts"]) == 3


def test_on_spawn_failed_rolls_back_fallback_runs_in_state_file(tmp_path, monkeypatch):
    p = _paths(tmp_path)
    state_file = tmp_path / "state" / "factory-watchdog.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps({"fallback_runs": 5, "fallback_runs_24h": 0,
                                      "fallback_runs_24h_ts": []}), encoding="utf-8")
    _write_mode(p, mode="active", nonce="n1")

    def boom(args, **kw):
        raise OSError("no claude.cmd")
    monkeypatch.setattr(hw, "_popen", boom, raising=True)

    kwargs = _base_reserve_kwargs(p, tmp_path, target_nonce="n1")
    kwargs["state_file"] = state_file
    out = fw._run_reserve_pass(**kwargs)

    assert out["result"]["outcome"] == "spawn_failed"
    final = json.loads(state_file.read_text(encoding="utf-8"))
    assert final["fallback_runs"] == 5             # +1 потом -1 = обратно 5
    assert final["fallback_runs_24h"] == 0         # append+pop -> обратно пусто


def test_bump_fallback_telemetry_state_file_none_is_noop_safe(tmp_path, monkeypatch):
    """state_file=None (тестовый смысл/старые вызовы) — телеметрия просто
    не пишется, НЕ падает."""
    p = _paths(tmp_path)
    _write_mode(p, mode="active", nonce="n1")
    monkeypatch.setattr(hw, "_popen", lambda args, **kw: _FakeProc(pid=1, rc=0), raising=True)
    ps.write_summary(triggered=0, deferred=0, rescan_delta=0,
                     output_path=p["pass_summary_file"], now=NOW)

    out = fw._run_reserve_pass(**_base_reserve_kwargs(p, tmp_path, target_nonce="n1"))

    assert out["result"]["outcome"] == "spawned"


# ===========================================================================
# C. Атрибуция прогресса (Д п.4) — свои сигналы резерва НЕ считаются
#    прогрессом окна (оба фронта: mode-write И лок, включая протёкший)
# ===========================================================================

def test_own_mode_write_does_not_reset_last_progress_ts(tmp_path):
    """Резерв успешно отработал (spawned rc=0) и физически переписал
    mode-файл (driver=watchdog-fallback, свежий updated_ts) — но
    `last_progress_ts` в state ДОЛЖЕН остаться на старом значении
    (эпизод STALLED продолжается: реальное окно молчит, резерв только
    подтолкнул очередь сам)."""
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=30)
    old_progress_ts = json.loads(p["state_file"].read_text(encoding="utf-8"))["last_progress_ts"]

    def _runner(**kwargs):
        # физически имитируем то, что реально пишет _run_reserve_pass/on_pass_done:
        # переписываем mode-файл свежим updated_ts/driver/passes_done САМИ.
        mode_data = json.loads(p["mode_file"].read_text(encoding="utf-8"))
        mode_data["updated_ts"] = fw._fmt_ts(NOW)
        mode_data["driver"] = "watchdog-fallback"
        mode_data["passes_done"] = mode_data.get("passes_done", 0) + 1
        p["mode_file"].write_text(json.dumps(mode_data), encoding="utf-8")
        return {
            "result": {"outcome": "spawned", "child_rc": 0, "fast_death": False,
                      "holder": "heartbeat:x:aaaa0000", "mode_write": mode_data},
            "classification": "nonempty", "cas_ok": True, "wrote_two_empty": False,
            "telemetry_delta": 1,
        }

    fw.run_tick(now=NOW, toast_fn=_NoToast(), reserve_runner=_runner, **p)

    state = _read_state(p)
    # last_progress_ts НЕ сдвинулся на `now`, несмотря на то, что mode-файл
    # физически изменился между началом и концом тика.
    assert state["last_progress_ts"] == old_progress_ts
    assert state["last_state"] == "stalled"
    # снимок КОНЦА тика в state отражает УЖЕ переписанный (резервом) mode-файл
    # — база для следующего тика, чтобы этот же дельта не всплыл повторно.
    assert state["last_mode_snapshot"]["updated_ts"] == fw._fmt_ts(NOW)


def test_own_leaked_lock_after_timeout_kill_does_not_reset_progress_next_tick(tmp_path):
    """timeout_kill с деревом, оставшимся живым (`alive=True`) — лок
    резерва ПРОТЕКАЕТ (не снят). Симулируем физическое появление лока
    (как сделал бы реальный `_run_child`) и проверяем: (а) ЭТОТ тик не
    засчитывает прогресс по нему; (б) СЛЕДУЮЩИЙ тик (лок так и висит,
    ничего больше не изменилось) ТОЖЕ не видит прогресса — протёкший
    лок сравнивается сам с собой, дельты нет."""
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=30)
    old_progress_ts = json.loads(p["state_file"].read_text(encoding="utf-8"))["last_progress_ts"]

    def _leak_lock():
        p["lock_file"].parent.mkdir(parents=True, exist_ok=True)
        p["lock_file"].write_text(json.dumps(
            {"holder": "heartbeat:leaked:aaaa0000", "pid": 4242, "ts": fw._fmt_ts(NOW)}),
            encoding="utf-8")

    def _runner(**kwargs):
        _leak_lock()
        return {
            "result": {"outcome": "timeout_kill", "child_rc": None, "fast_death": False,
                      "holder": "heartbeat:leaked:aaaa0000", "mode_write": None},
            "classification": None, "cas_ok": None, "wrote_two_empty": False,
            "telemetry_delta": 1,
        }

    fw.run_tick(now=NOW, toast_fn=_NoToast(), reserve_runner=_runner, **p)
    state1 = _read_state(p)
    assert state1["last_progress_ts"] == old_progress_ts     # тик 1: НЕ засчитан как прогресс
    assert state1["last_lock_snapshot"]["holder"] == "heartbeat:leaked:aaaa0000"

    # тик 2 (30 мин спустя): лок ВСЁ ЕЩЁ висит, mode-файл не менялся —
    # никакого нового резервного вызова (gate/delay не пересчитываем здесь,
    # достаточно доказать, что prev_lock_snap == текущий -> changed=False).
    calls = []
    later = NOW + datetime.timedelta(minutes=30)
    fw.run_tick(now=later, toast_fn=_NoToast(), reserve_runner=_fake_runner_factory(calls), **p)
    state2 = _read_state(p)
    assert state2["last_progress_ts"] == old_progress_ts     # тик 2: ВСЁ ЕЩЁ не прогресс
    assert state2["last_state"] == "stalled"
