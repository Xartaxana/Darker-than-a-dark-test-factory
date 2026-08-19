"""Юнит-тесты scripts/factory_watchdog.py — сторож окна-фабрики
(spec-factory-window v6 К3, docs/tasks/factory-visible-window.md,
2026-08-16). Все пути (лок/mode/state/sla/escalations/orchestrator-log)
— под tmp_path, время инжектится через now=... (детерминированные тесты).
toast_fn подменяется фейком (живая WinRT-проба — отдельный witness,
не юнит)."""
from __future__ import annotations

import datetime
import json

import factory_watchdog as fw

NOW = datetime.datetime(2026, 8, 16, 12, 0, 0, tzinfo=datetime.timezone.utc)


def _paths(tmp_path):
    return {
        "lock_file": tmp_path / "state" / "loop.lock",
        "mode_file": tmp_path / "state" / "factory-mode.json",
        "state_file": tmp_path / "state" / "factory-watchdog.json",
        "sla_file": tmp_path / "state" / "sla.yaml",
        "escalations_file": tmp_path / "state" / "escalations.md",
        "orchestrator_log": tmp_path / "state" / "orchestrator-log.md",
    }


def _write_sla(p, ttl=4):
    p["sla_file"].parent.mkdir(parents=True, exist_ok=True)
    p["sla_file"].write_text(
        f"version: 1\nthresholds:\n  lock_stale: 2\n  loop_lock_ttl_hours: {ttl}\n",
        encoding="utf-8")


def _write_lock(p, holder="qa-loop:x", ts=None, pid=1234):
    p["lock_file"].parent.mkdir(parents=True, exist_ok=True)
    ts = ts or NOW.strftime("%Y-%m-%dT%H:%M:%SZ")
    p["lock_file"].write_text(
        json.dumps({"holder": holder, "pid": pid, "ts": ts}), encoding="utf-8")


def _write_mode(p, mode="active", updated_ts=None, passes_done=0, nonce="n1"):
    p["mode_file"].parent.mkdir(parents=True, exist_ok=True)
    p["mode_file"].write_text(json.dumps({
        "mode": mode,
        "session_nonce": nonce,
        "updated_ts": updated_ts or NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "passes_done": passes_done,
        "budget_total": 5,
        "session_started_ts": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "heartbeat_note": "",
        "stopped_reason": "",
    }), encoding="utf-8")


def _mode_snap_dict(mode="active", updated_ts=None, passes_done=0, nonce="n1"):
    """Снимок mode-файла В ТОЙ ЖЕ форме, что fw._mode_snapshot() читает из
    файла, записанного _write_mode(...) с ТЕМИ ЖЕ аргументами — нужен,
    чтобы «прошлый снимок» в state-файле совпадал с текущим прочитанным
    mode-файлом (иначе прогресс детектируется КАЖДЫЙ тик просто потому,
    что в тесте не смоделирован предыдущий снимок, и last_progress_ts
    всегда сбрасывается на now — тишина никогда не накапливается).
    `nonce="n1"` — дефолт `_write_mode()`'s `nonce` (Д п.4: session_nonce
    входит в снимок с v7)."""
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
    }
    base.update(fields)
    p["state_file"].write_text(json.dumps(base), encoding="utf-8")


class _NoToast:
    """toast_fn заглушка — считает вызовы, никогда не бьёт по сети."""
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


# --- bootstrap --------------------------------------------------------------

def test_bootstrap_no_state_file_writes_snapshots_silently(tmp_path):
    p = _paths(tmp_path)
    _write_sla(p)
    toast = _NoToast()

    code = fw.run_tick(now=NOW, toast_fn=toast, **p)

    assert code == 0
    state = _read_state(p)
    assert state["last_progress_ts"] == fw._fmt_ts(NOW)
    assert state["last_state"] == "ok"
    assert not p["escalations_file"].exists()
    assert not toast.calls


def test_bootstrap_corrupt_state_file_treated_as_no_snapshots(tmp_path):
    p = _paths(tmp_path)
    _write_sla(p)
    p["state_file"].parent.mkdir(parents=True, exist_ok=True)
    p["state_file"].write_text("not json at all", encoding="utf-8")
    toast = _NoToast()

    code = fw.run_tick(now=NOW, toast_fn=toast, **p)

    assert code == 0
    state = _read_state(p)                    # перезаписан валидным bootstrap-снимком
    assert state["last_state"] == "ok"
    orch = _read_orch(p)
    assert "bootstrap" in orch and "factory-watchdog.json" in orch


def test_orchestrator_log_write_failure_does_not_kill_tick_and_leaves_diagnosable_trace(
        tmp_path, capsys):
    """Батч мелочей п.3: `_append_orchestrator_line` (M4-писатель сторожа)
    отказывает (каталог лога недоступен — тут: родитель существует как
    ФАЙЛ, mkdir(parents=True, exist_ok=True) бьёт OSError'ом) — тик обязан
    отработать штатно (code==0, state-файл записан валидно), а отказ
    записи — оставить диагностируемый след (печать), не уйти молча."""
    p = _paths(tmp_path)
    _write_sla(p)
    # orchestrator_log лежит ПОД файлом (не каталогом) — mkdir родителя
    # структурно не может выполниться.
    blocker = tmp_path / "state" / "blocked-orch"
    blocker.parent.mkdir(parents=True, exist_ok=True)
    blocker.write_text("не каталог", encoding="utf-8")
    p["orchestrator_log"] = blocker / "orchestrator-log.md"
    # bootstrap-ветка (нет state-файла) с notes_now непустым: битый
    # mode-файл добавляет заметку -> код доходит до _append_orchestrator_line.
    p["mode_file"].parent.mkdir(parents=True, exist_ok=True)
    p["mode_file"].write_text("{not valid json", encoding="utf-8")
    toast = _NoToast()

    code = fw.run_tick(now=NOW, toast_fn=toast, **p)

    assert code == 0                                  # тик не упал
    state = _read_state(p)
    assert state["last_state"] == "ok"                 # state всё равно записан
    assert not p["orchestrator_log"].exists()           # запись физически не состоялась
    out = capsys.readouterr().out
    assert "ORCHESTRATOR-LOG write failed" in out        # диагностируемый след


# --- п.0: битые mode/lock (bootstrap НЕ активен — state-файл валиден) ------

def test_corrupt_mode_file_treated_as_missing_with_orchestrator_note(tmp_path):
    p = _paths(tmp_path)
    _write_sla(p)
    _write_state(p, last_state="ok")
    p["mode_file"].parent.mkdir(parents=True, exist_ok=True)
    p["mode_file"].write_text("{not valid json", encoding="utf-8")
    toast = _NoToast()

    code = fw.run_tick(now=NOW, toast_fn=toast, **p)

    assert code == 0
    state = _read_state(p)
    assert state["last_state"] == "ok"          # ветка 1 (mode нет) — тишина
    orch = _read_orch(p)
    assert "factory-mode.json" in orch and "К3 п.0" in orch


def test_corrupt_lock_file_noted_and_treated_as_present_stale_candidate(tmp_path):
    """Битый лок при mode=stopped: считается протухшим СРАЗУ (без
    вычисления возраста) -> STALLED («лок без вождения»)."""
    p = _paths(tmp_path)
    _write_sla(p)
    _write_state(p, last_state="ok")
    _write_mode(p, mode="stopped")
    p["lock_file"].parent.mkdir(parents=True, exist_ok=True)
    p["lock_file"].write_text("garbage, not json", encoding="utf-8")
    toast = _NoToast()

    code = fw.run_tick(now=NOW, toast_fn=toast, **p)

    assert code == 0
    state = _read_state(p)
    assert state["last_state"] == "stalled"
    orch = _read_orch(p)
    assert "loop.lock" in orch and "К3 п.0" in orch
    esc = _read_esc(p)
    assert "FACTORY-STALLED" in esc and "[factory:stalled]" in esc


def test_state_file_nonlist_notes_does_not_kill_tick(tmp_path):
    """Б-3 (критик r2): валидный JSON-объект state-файла с НЕлистовым
    `notes` (число) не должен ронять тик TypeError'ом до _write_state —
    иначе состояние самоподдерживается и сторож слепнет бессрочно.
    Тик обязан отработать штатно: тревога объявлена (тишина за порогом),
    state-файл перезаписан валидным снимком."""
    p = _paths(tmp_path)
    _write_sla(p)
    old = NOW - datetime.timedelta(minutes=240)
    _write_state(p, last_state="ok",
                 last_progress_ts=old.strftime("%Y-%m-%dT%H:%M:%SZ"),
                 last_mode_snapshot={"mode": "active",
                                     "updated_ts": old.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                     "passes_done": 0, "session_nonce": "n1"},
                 notes=5)                       # нелистовой тип — раньше TypeError
    _write_mode(p, mode="active",
                updated_ts=old.strftime("%Y-%m-%dT%H:%M:%SZ"))
    toast = _NoToast()

    code = fw.run_tick(now=NOW, toast_fn=toast, **p)

    assert code == 0
    state = _read_state(p)
    assert state["last_state"] == "stalled"       # тревога объявлена
    assert isinstance(state["notes"], list)       # снимок перезаписан валидно
    esc = _read_esc(p)
    assert "FACTORY-STALLED" in esc


def test_lock_valid_json_missing_ts_is_corrupt_for_progress_and_orphan(tmp_path):
    p = _paths(tmp_path)
    _write_sla(p)
    _write_state(p, last_state="ok")
    _write_mode(p, mode="stopped")
    p["lock_file"].parent.mkdir(parents=True, exist_ok=True)
    p["lock_file"].write_text('{"holder": "ghost"}', encoding="utf-8")
    toast = _NoToast()

    code = fw.run_tick(now=NOW, toast_fn=toast, **p)

    assert _read_state(p)["last_state"] == "stalled"


# --- branch 1: mode-файла нет — carve-out ручного прохода (лок ИГНОРИРУЕТСЯ) -

def test_branch1_no_mode_file_is_silent_even_with_stale_lock(tmp_path):
    p = _paths(tmp_path)
    _write_sla(p, ttl=1)
    _write_state(p, last_state="ok")
    # лок протух бы по любому TTL — не должен иметь значения в ветке 1
    _write_lock(p, ts=(NOW - datetime.timedelta(hours=10)).strftime("%Y-%m-%dT%H:%M:%SZ"))
    toast = _NoToast()

    code = fw.run_tick(now=NOW, toast_fn=toast, **p)

    assert code == 0
    assert _read_state(p)["last_state"] == "ok"
    assert not toast.calls


def test_branch1_recovers_from_prior_stalled_state(tmp_path):
    """mode-файл исчез (или снова читается как «нет») после того, как
    сторож ранее объявил stalled — переход stalled->ok гасит эскалацию."""
    p = _paths(tmp_path)
    _write_sla(p)
    _write_state(p, last_state="stalled",
                 last_alert_ts=fw._fmt_ts(NOW - datetime.timedelta(hours=1)))
    fw._write_singleton_escalation(p["escalations_file"], "было плохо", NOW)
    toast = _NoToast()

    code = fw.run_tick(now=NOW, toast_fn=toast, **p)

    assert code == 0
    assert _read_state(p)["last_state"] == "ok"
    esc = _read_esc(p)
    assert fw.FACTORY_STALLED_RESOLVED_MARKER in esc


# --- branch 2: mode=stopped ---------------------------------------------

def test_branch2_stopped_no_lock_is_silent(tmp_path):
    p = _paths(tmp_path)
    _write_sla(p)
    _write_state(p, last_state="ok")
    _write_mode(p, mode="stopped")
    toast = _NoToast()

    code = fw.run_tick(now=NOW, toast_fn=toast, **p)

    assert _read_state(p)["last_state"] == "ok"
    assert not toast.calls


def test_branch2_stopped_fresh_lock_is_silent(tmp_path):
    p = _paths(tmp_path)
    _write_sla(p, ttl=4)
    _write_state(p, last_state="ok")
    _write_mode(p, mode="stopped")
    _write_lock(p, ts=(NOW - datetime.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"))
    toast = _NoToast()

    code = fw.run_tick(now=NOW, toast_fn=toast, **p)

    assert _read_state(p)["last_state"] == "ok"


def test_branch2_stopped_orphan_lock_boundary_exactly_ttl_is_silent(tmp_path):
    """Граница НА пороге TTL (ровно 4ч) — НЕ протух (`>`, не `>=`)."""
    p = _paths(tmp_path)
    _write_sla(p, ttl=4)
    _write_state(p, last_state="ok")
    _write_mode(p, mode="stopped")
    _write_lock(p, ts=(NOW - datetime.timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M:%SZ"))
    toast = _NoToast()

    code = fw.run_tick(now=NOW, toast_fn=toast, **p)

    assert _read_state(p)["last_state"] == "ok"


def test_branch2_stopped_orphan_lock_boundary_past_ttl_is_stalled(tmp_path):
    """Граница ЗА порогом TTL (4ч + 1с) — STALLED."""
    p = _paths(tmp_path)
    _write_sla(p, ttl=4)
    _write_state(p, last_state="ok")
    _write_mode(p, mode="stopped")
    _write_lock(p, ts=(NOW - datetime.timedelta(hours=4, seconds=1)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"))
    toast = _NoToast()

    code = fw.run_tick(now=NOW, toast_fn=toast, **p)

    assert _read_state(p)["last_state"] == "stalled"
    assert toast.calls                                       # первая транзиция -> тост


# --- branch 3: mode активный ---------------------------------------------

def test_branch3_active_no_lock_within_threshold_is_ok(tmp_path):
    p = _paths(tmp_path)
    _write_sla(p)
    started = NOW - datetime.timedelta(minutes=30)
    _write_state(p, last_state="ok", last_progress_ts=fw._fmt_ts(started),
                last_mode_snapshot=_mode_snap_dict("active", fw._fmt_ts(started)))
    _write_mode(p, mode="active", updated_ts=fw._fmt_ts(started))
    toast = _NoToast()

    code = fw.run_tick(now=NOW, toast_fn=toast, stall_no_lock_min=60, **p)

    assert _read_state(p)["last_state"] == "ok"


def test_branch3_active_no_lock_boundary_exactly_60_is_ok(tmp_path):
    p = _paths(tmp_path)
    _write_sla(p)
    started = NOW - datetime.timedelta(minutes=60)
    _write_state(p, last_state="ok", last_progress_ts=fw._fmt_ts(started),
                last_mode_snapshot=_mode_snap_dict("active", fw._fmt_ts(started)))
    _write_mode(p, mode="active", updated_ts=fw._fmt_ts(started))
    toast = _NoToast()

    code = fw.run_tick(now=NOW, toast_fn=toast, stall_no_lock_min=60, **p)

    assert _read_state(p)["last_state"] == "ok"


def test_branch3_active_no_lock_boundary_past_60_is_stalled(tmp_path):
    p = _paths(tmp_path)
    _write_sla(p)
    started = NOW - datetime.timedelta(minutes=60, seconds=1)
    _write_state(p, last_state="ok", last_progress_ts=fw._fmt_ts(started),
                last_mode_snapshot=_mode_snap_dict("active", fw._fmt_ts(started)))
    _write_mode(p, mode="active", updated_ts=fw._fmt_ts(started))
    toast = _NoToast()

    code = fw.run_tick(now=NOW, toast_fn=toast, stall_no_lock_min=60, **p)

    assert _read_state(p)["last_state"] == "stalled"


def test_branch3_active_with_lock_boundary_exactly_90_is_ok(tmp_path):
    p = _paths(tmp_path)
    _write_sla(p)
    started = NOW - datetime.timedelta(minutes=90)
    _write_lock(p, ts=fw._fmt_ts(started))
    lock_snap_prior = fw._lock_snapshot(p["lock_file"])
    _write_state(p, last_state="ok", last_progress_ts=fw._fmt_ts(started),
                last_mode_snapshot=_mode_snap_dict("active", fw._fmt_ts(started)),
                last_lock_snapshot=lock_snap_prior)
    _write_mode(p, mode="active", updated_ts=fw._fmt_ts(started))
    toast = _NoToast()

    code = fw.run_tick(now=NOW, toast_fn=toast, stall_inpass_min=90, **p)

    assert _read_state(p)["last_state"] == "ok"


def test_branch3_active_with_lock_boundary_past_90_is_stalled(tmp_path):
    p = _paths(tmp_path)
    _write_sla(p)
    started = NOW - datetime.timedelta(minutes=90, seconds=1)
    _write_lock(p, ts=fw._fmt_ts(started))
    lock_snap_prior = fw._lock_snapshot(p["lock_file"])
    _write_state(p, last_state="ok", last_progress_ts=fw._fmt_ts(started),
                last_mode_snapshot=_mode_snap_dict("active", fw._fmt_ts(started)),
                last_lock_snapshot=lock_snap_prior)
    _write_mode(p, mode="active", updated_ts=fw._fmt_ts(started))
    toast = _NoToast()

    code = fw.run_tick(now=NOW, toast_fn=toast, stall_inpass_min=90, **p)

    assert _read_state(p)["last_state"] == "stalled"


def test_branch3_progress_via_mode_updated_ts_resets_silence(tmp_path):
    """Пульс (updated_ts мода изменился относительно снапшота) -> прогресс
    засчитан -> last_progress_ts=now, тишина НЕ накопилась."""
    p = _paths(tmp_path)
    _write_sla(p)
    old = NOW - datetime.timedelta(minutes=200)
    _write_state(p, last_state="ok", last_progress_ts=fw._fmt_ts(old),
                last_mode_snapshot={"mode": "active", "updated_ts": fw._fmt_ts(old),
                                    "passes_done": 0, "session_nonce": "n1"})
    _write_mode(p, mode="active", updated_ts=fw._fmt_ts(NOW))   # свежий пульс

    code = fw.run_tick(now=NOW, toast_fn=_NoToast(), stall_no_lock_min=60, **p)

    state = _read_state(p)
    assert state["last_state"] == "ok"
    assert state["last_progress_ts"] == fw._fmt_ts(NOW)


def test_branch3_lock_holder_change_counts_as_progress(tmp_path):
    """Прогресс И через изменение лока (новый holder/ts), не только mode."""
    p = _paths(tmp_path)
    _write_sla(p)
    old = NOW - datetime.timedelta(minutes=200)
    _write_state(p, last_state="ok", last_progress_ts=fw._fmt_ts(old),
                last_lock_snapshot={"exists": True, "corrupt": False,
                                    "holder": "qa-loop:old", "ts": fw._fmt_ts(old),
                                    "raw_hash": "irrelevant"})
    _write_mode(p, mode="active", updated_ts=fw._fmt_ts(old))
    _write_lock(p, holder="qa-loop:new", ts=fw._fmt_ts(NOW))

    code = fw.run_tick(now=NOW, toast_fn=_NoToast(), stall_inpass_min=90, **p)

    state = _read_state(p)
    assert state["last_state"] == "ok"
    assert state["last_progress_ts"] == fw._fmt_ts(NOW)


# --- branch 4: транзиции, тост-кулдаун -------------------------------------

def test_transition_ok_to_stalled_writes_escalation_log_and_toast(tmp_path):
    p = _paths(tmp_path)
    _write_sla(p)
    started = NOW - datetime.timedelta(minutes=61)
    _write_state(p, last_state="ok", last_progress_ts=fw._fmt_ts(started),
                last_mode_snapshot=_mode_snap_dict("active", fw._fmt_ts(started)))
    _write_mode(p, mode="active", updated_ts=fw._fmt_ts(started))
    toast = _NoToast()

    fw.run_tick(now=NOW, toast_fn=toast, stall_no_lock_min=60, **p)

    esc = _read_esc(p)
    assert "FACTORY-STALLED" in esc and "[factory:stalled]" in esc
    orch = _read_orch(p)
    assert "ok->stalled" in orch
    assert toast.calls and toast.calls[0][0] == "[factory:stalled]"


def test_repeated_stalled_ticks_do_not_re_escalate_or_re_toast(tmp_path):
    """Продолжающаяся тревога (уже stalled в прошлом тике) — НЕ пишет
    новую эскалацию/лог/тост повторно (только на транзиции)."""
    p = _paths(tmp_path)
    _write_sla(p)
    started = NOW - datetime.timedelta(minutes=200)
    _write_state(p, last_state="stalled", last_progress_ts=fw._fmt_ts(started),
                last_mode_snapshot=_mode_snap_dict("active", fw._fmt_ts(started)),
                last_alert_ts=fw._fmt_ts(NOW - datetime.timedelta(minutes=30)))
    _write_mode(p, mode="active", updated_ts=fw._fmt_ts(started))
    toast = _NoToast()

    fw.run_tick(now=NOW, toast_fn=toast, stall_no_lock_min=60, **p)

    assert not p["escalations_file"].exists()
    assert not toast.calls
    orch = _read_orch(p)
    assert "ok->stalled" not in orch


def test_toast_cooldown_suppresses_second_toast_within_window_but_still_escalates(tmp_path):
    """Recovery потом повторный stall в течение 4ч кулдауна: эскалация и
    orchestrator-строка пишутся на транзиции ВСЕГДА, тост — только если
    кулдаун истёк."""
    p = _paths(tmp_path)
    _write_sla(p)
    recent_alert = NOW - datetime.timedelta(hours=1)         # < 4ч кулдауна
    started = NOW - datetime.timedelta(minutes=61)
    _write_state(p, last_state="ok", last_progress_ts=fw._fmt_ts(started),
                last_mode_snapshot=_mode_snap_dict("active", fw._fmt_ts(started)),
                last_alert_ts=fw._fmt_ts(recent_alert))
    _write_mode(p, mode="active", updated_ts=fw._fmt_ts(started))
    toast = _NoToast()

    fw.run_tick(now=NOW, toast_fn=toast, stall_no_lock_min=60,
               cooldown_hours=4.0, **p)

    esc = _read_esc(p)
    assert "FACTORY-STALLED" in esc                           # эскалация пишется всегда
    assert not toast.calls                                    # тост подавлен кулдауном
    state = _read_state(p)
    assert state["last_alert_ts"] == fw._fmt_ts(recent_alert)  # не обновился


def test_toast_cooldown_boundary_exactly_4h_allows_toast(tmp_path):
    p = _paths(tmp_path)
    _write_sla(p)
    old_alert = NOW - datetime.timedelta(hours=4)              # ровно на границе
    started = NOW - datetime.timedelta(minutes=61)
    _write_state(p, last_state="ok", last_progress_ts=fw._fmt_ts(started),
                last_mode_snapshot=_mode_snap_dict("active", fw._fmt_ts(started)),
                last_alert_ts=fw._fmt_ts(old_alert))
    _write_mode(p, mode="active", updated_ts=fw._fmt_ts(started))
    toast = _NoToast()

    fw.run_tick(now=NOW, toast_fn=toast, stall_no_lock_min=60,
               cooldown_hours=4.0, **p)

    assert toast.calls                                         # >= кулдаун -> тост разрешён


def test_toast_cooldown_boundary_just_under_4h_suppresses(tmp_path):
    p = _paths(tmp_path)
    _write_sla(p)
    old_alert = NOW - datetime.timedelta(hours=4) + datetime.timedelta(seconds=1)
    started = NOW - datetime.timedelta(minutes=61)
    _write_state(p, last_state="ok", last_progress_ts=fw._fmt_ts(started),
                last_mode_snapshot=_mode_snap_dict("active", fw._fmt_ts(started)),
                last_alert_ts=fw._fmt_ts(old_alert))
    _write_mode(p, mode="active", updated_ts=fw._fmt_ts(started))
    toast = _NoToast()

    fw.run_tick(now=NOW, toast_fn=toast, stall_no_lock_min=60,
               cooldown_hours=4.0, **p)

    assert not toast.calls


def test_toast_failure_does_not_prevent_escalation_or_crash(tmp_path):
    p = _paths(tmp_path)
    _write_sla(p)
    started = NOW - datetime.timedelta(minutes=61)
    _write_state(p, last_state="ok", last_progress_ts=fw._fmt_ts(started),
                last_mode_snapshot=_mode_snap_dict("active", fw._fmt_ts(started)))
    _write_mode(p, mode="active", updated_ts=fw._fmt_ts(started))
    toast = _NoToast(shown=False)                              # тост "не показался"

    code = fw.run_tick(now=NOW, toast_fn=toast, stall_no_lock_min=60, **p)

    assert code == 0
    assert "FACTORY-STALLED" in _read_esc(p)


def test_transition_stalled_to_ok_resolves_escalation_and_logs(tmp_path):
    p = _paths(tmp_path)
    _write_sla(p)
    fresh = NOW
    _write_state(p, last_state="stalled", last_progress_ts=fw._fmt_ts(fresh),
                last_mode_snapshot=_mode_snap_dict("active", fw._fmt_ts(NOW)),
                last_alert_ts=fw._fmt_ts(NOW - datetime.timedelta(hours=1)))
    fw._write_singleton_escalation(p["escalations_file"], "стояла тревога", NOW)
    _write_mode(p, mode="active", updated_ts=fw._fmt_ts(NOW))
    toast = _NoToast()

    fw.run_tick(now=NOW, toast_fn=toast, stall_no_lock_min=60, **p)

    esc = _read_esc(p)
    assert fw.FACTORY_STALLED_RESOLVED_MARKER in esc
    assert esc.count("FACTORY-STALLED") == 1                   # singleton, не задублирован
    orch = _read_orch(p)
    assert "stalled->ok" in orch
    assert not toast.calls                                     # recovery не шлёт тост


# --- non-throwing / env overrides ------------------------------------------

def test_non_throwing_missing_parent_dirs_everywhere(tmp_path):
    """Ни один из каталогов не существует заранее — сторож создаёт их сам
    (mkdir parents=True) и не падает."""
    p = _paths(tmp_path / "deeply" / "nested")
    _write_sla(p)

    code = fw.run_tick(now=NOW, toast_fn=_NoToast(), **p)

    assert code == 0
    assert p["state_file"].exists()


def test_main_never_raises_and_exits_0_on_totally_missing_state(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # permission-hygiene: --no-toast defensively (bootstrap-ветка не должна
    # доходить до show_toast вовсе, но флаг здесь бесплатно закрывает риск
    # будущей правки сценария, поднимающей его до STALLED).
    code = fw.main([
        "--lock-file", str(tmp_path / "state" / "loop.lock"),
        "--mode-file", str(tmp_path / "state" / "factory-mode.json"),
        "--state-file", str(tmp_path / "state" / "factory-watchdog.json"),
        "--sla-file", str(tmp_path / "state" / "sla.yaml"),
        "--escalations-file", str(tmp_path / "state" / "escalations.md"),
        "--orchestrator-log", str(tmp_path / "state" / "orchestrator-log.md"),
        "--now", "2026-08-16T12:00:00Z", "--no-toast",
    ])
    assert code == 0


# --- permission-hygiene (слово оператора 2026-08-16 вечер, повтор):
# --no-toast/AO3_FACTORY_NO_TOAST подменяют show_toast заглушкой ДО того,
# как run_tick вообще мог бы его вызвать — poison-pill монкипатч show_toast
# доказывает, что живой тост НЕ звонится, даже если сценарий STALLED. -----

def test_cli_no_toast_flag_suppresses_real_toast_even_when_stalled(tmp_path, monkeypatch):
    p = _paths(tmp_path)
    _write_sla(p)
    started = NOW - datetime.timedelta(minutes=61)
    _write_state(p, last_state="ok", last_progress_ts=fw._fmt_ts(started),
                last_mode_snapshot=_mode_snap_dict("active", fw._fmt_ts(started)))
    _write_mode(p, mode="active", updated_ts=fw._fmt_ts(started))

    def _poison(*a, **kw):
        raise AssertionError("show_toast НЕ должен звониться при --no-toast")
    monkeypatch.setattr(fw, "show_toast", _poison, raising=True)

    code = fw.main([
        "--lock-file", str(p["lock_file"]), "--mode-file", str(p["mode_file"]),
        "--state-file", str(p["state_file"]), "--sla-file", str(p["sla_file"]),
        "--escalations-file", str(p["escalations_file"]),
        "--orchestrator-log", str(p["orchestrator_log"]),
        "--now", fw._fmt_ts(NOW), "--no-toast",
    ])

    assert code == 0
    assert _read_state(p)["last_state"] == "stalled"       # тревога всё равно объявлена
    assert "FACTORY-STALLED" in _read_esc(p)                # эскалация пишется независимо от тоста


def test_cli_env_no_toast_suppresses_real_toast(tmp_path, monkeypatch):
    p = _paths(tmp_path)
    _write_sla(p)
    started = NOW - datetime.timedelta(minutes=61)
    _write_state(p, last_state="ok", last_progress_ts=fw._fmt_ts(started),
                last_mode_snapshot=_mode_snap_dict("active", fw._fmt_ts(started)))
    _write_mode(p, mode="active", updated_ts=fw._fmt_ts(started))
    monkeypatch.setenv("AO3_FACTORY_NO_TOAST", "1")

    def _poison(*a, **kw):
        raise AssertionError("show_toast НЕ должен звониться при AO3_FACTORY_NO_TOAST=1")
    monkeypatch.setattr(fw, "show_toast", _poison, raising=True)

    code = fw.main([
        "--lock-file", str(p["lock_file"]), "--mode-file", str(p["mode_file"]),
        "--state-file", str(p["state_file"]), "--sla-file", str(p["sla_file"]),
        "--escalations-file", str(p["escalations_file"]),
        "--orchestrator-log", str(p["orchestrator_log"]),
        "--now", fw._fmt_ts(NOW),
    ])

    assert code == 0
    assert _read_state(p)["last_state"] == "stalled"


def test_env_overrides_stall_thresholds(monkeypatch, tmp_path):
    """Permission-hygiene (слово оператора 2026-08-16 вечер, повтор):
    этот сценарий реально пересекает порог STALLED -> fw.main() без
    --no-toast звал бы РЕАЛЬНЫЙ show_toast (живой WinRT-тост на экране
    оператора) при каждом прогоне pytest — пин через `--no-toast`
    (CLI-флаг, добавленный этим же диффом) закрывает находку."""
    p = _paths(tmp_path)
    _write_sla(p)
    started = NOW - datetime.timedelta(minutes=10)
    _write_state(p, last_state="ok", last_progress_ts=fw._fmt_ts(started),
                last_mode_snapshot=_mode_snap_dict("active", fw._fmt_ts(started)))
    _write_mode(p, mode="active", updated_ts=fw._fmt_ts(started))
    monkeypatch.setenv("AO3_FACTORY_STALL_MIN", "5")            # ужимаем порог env'ом

    def _poison(*a, **kw):
        raise AssertionError("show_toast НЕ должен звониться в юнит-тестах (permission-hygiene)")
    monkeypatch.setattr(fw, "show_toast", _poison, raising=True)

    code = fw.main([
        "--lock-file", str(p["lock_file"]), "--mode-file", str(p["mode_file"]),
        "--state-file", str(p["state_file"]), "--sla-file", str(p["sla_file"]),
        "--escalations-file", str(p["escalations_file"]),
        "--orchestrator-log", str(p["orchestrator_log"]),
        "--now", fw._fmt_ts(NOW), "--no-toast",
    ])

    assert code == 0
    assert _read_state(p)["last_state"] == "stalled"           # 10мин > env-порога 5мин


# --- Б-1 (критик-фикс, 2026-08-16): накопитель notes + дедуп ---------------

def test_notes_field_written_on_bootstrap_with_corrupt_mode(tmp_path):
    p = _paths(tmp_path)
    _write_sla(p)
    p["mode_file"].parent.mkdir(parents=True, exist_ok=True)
    p["mode_file"].write_text("{not valid json", encoding="utf-8")

    code = fw.run_tick(now=NOW, toast_fn=_NoToast(), **p)

    assert code == 0
    state = _read_state(p)
    assert len(state["notes"]) == 1
    assert "factory-mode.json" in state["notes"][0]
    orch = _read_orch(p)
    assert "notes:" in orch and "factory-mode.json" in orch


def test_notes_dedup_same_corrupt_mode_across_two_ticks_no_new_log_line(tmp_path):
    """Устойчиво битый mode-файл ДВА тика подряд — orchestrator-log
    получает СТРОКУ ТОЛЬКО НА ПЕРВОМ тике (notes не изменились -> дедуп)."""
    p = _paths(tmp_path)
    _write_sla(p)
    p["mode_file"].parent.mkdir(parents=True, exist_ok=True)
    p["mode_file"].write_text("{not valid json", encoding="utf-8")

    fw.run_tick(now=NOW, toast_fn=_NoToast(), **p)                # bootstrap -> 1 строка
    orch_after_first = _read_orch(p)
    notes_lines_first = orch_after_first.count("notes:")
    assert notes_lines_first == 1

    later = NOW + datetime.timedelta(minutes=30)
    fw.run_tick(now=later, toast_fn=_NoToast(), **p)               # тот же битый файл

    orch_after_second = _read_orch(p)
    assert orch_after_second.count("notes:") == 1                  # НЕ выросло — дедуп
    state = _read_state(p)
    assert len(state["notes"]) == 1                                # поле по-прежнему актуально


def test_notes_new_anomaly_after_stable_ok_produces_new_log_line(tmp_path):
    """notes меняются (появляется новая аномалия) -> НОВАЯ строка, даже
    если предыдущий тик был чист."""
    p = _paths(tmp_path)
    _write_sla(p)
    _write_state(p, last_state="ok", notes=[])
    p["lock_file"].parent.mkdir(parents=True, exist_ok=True)
    p["lock_file"].write_text("garbage, not json", encoding="utf-8")

    code = fw.run_tick(now=NOW, toast_fn=_NoToast(), **p)

    assert code == 0
    orch = _read_orch(p)
    assert orch.count("notes:") == 1
    assert "loop.lock" in orch
    assert _read_state(p)["notes"] == [
        f"{fw._rel_path(p['lock_file'])}: нечитаем/без валидного ts — трактован как "
        "сирота-кандидат (К3 п.0)"]


def test_notes_cleared_when_anomaly_recovers_logs_recovery_line(tmp_path):
    """Аномалия исчезла (файл починен) -> notes стали пустыми -> строка о
    смене набора notes. Н-7 (критик r2): формулировка нейтральная
    («сняты (были: ...)»), НЕ «аномалии устранены» — среди notes бывают
    одноразовые события (отказ тоста), уходящие сами без устранения."""
    p = _paths(tmp_path)
    _write_sla(p)
    stale_note = f"{fw._rel_path(p['mode_file'])}: нечитаем — трактован как «файла нет» (К3 п.0)"
    _write_state(p, last_state="ok", notes=[stale_note])
    _write_mode(p, mode="stopped")                                  # починен -> валидный JSON

    code = fw.run_tick(now=NOW, toast_fn=_NoToast(), **p)

    assert code == 0
    assert _read_state(p)["notes"] == []
    orch = _read_orch(p)
    assert "notes: сняты (были: " in orch
    assert "аномалии устранены" not in orch


def test_toast_failure_recorded_in_notes(tmp_path):
    p = _paths(tmp_path)
    _write_sla(p)
    started = NOW - datetime.timedelta(minutes=61)
    _write_state(p, last_state="ok", last_progress_ts=fw._fmt_ts(started),
                last_mode_snapshot=_mode_snap_dict("active", fw._fmt_ts(started)), notes=[])
    _write_mode(p, mode="active", updated_ts=fw._fmt_ts(started))
    toast = _NoToast(shown=False)

    code = fw.run_tick(now=NOW, toast_fn=toast, stall_no_lock_min=60, **p)

    assert code == 0
    state = _read_state(p)
    assert any("тост не показан" in n for n in state["notes"])
    orch = _read_orch(p)
    assert "тост не показан" in orch


# --- Б-2 (критик-фикс, 2026-08-16): якорь [resolved:...] сразу после KEY ---

def test_escalation_resolved_marker_immediately_after_key(tmp_path):
    p = _paths(tmp_path)
    _write_sla(p)
    fw._write_singleton_escalation(p["escalations_file"], "восстановлено", NOW, resolved=True)

    esc = p["escalations_file"].read_text(encoding="utf-8")

    assert "**FACTORY-STALLED** [resolved:factory-watchdog-recovered] [factory:stalled]" in esc


def test_knock_resolve_knock_rewrites_same_line_not_two(tmp_path):
    """Критик-сценарий дословно: стук (stalled) -> гашение (ok) ->
    повторный стук (stalled) -> ОДНА строка FACTORY-STALLED, без якоря
    resolved на финальном состоянии (перезаписан заново)."""
    p = _paths(tmp_path)
    _write_sla(p)

    # тик 1: ok -> stalled (первый стук)
    started = NOW - datetime.timedelta(minutes=61)
    _write_state(p, last_state="ok", last_progress_ts=fw._fmt_ts(started),
                last_mode_snapshot=_mode_snap_dict("active", fw._fmt_ts(started)), notes=[])
    _write_mode(p, mode="active", updated_ts=fw._fmt_ts(started))
    fw.run_tick(now=NOW, toast_fn=_NoToast(), stall_no_lock_min=60, **p)
    esc1 = p["escalations_file"].read_text(encoding="utf-8")
    assert esc1.count("FACTORY-STALLED") == 1
    assert "[resolved:" not in esc1

    # тик 2: stalled -> ok (гашение) — свежий прогресс "чинит" тишину
    t2 = NOW + datetime.timedelta(minutes=1)
    _write_mode(p, mode="active", updated_ts=fw._fmt_ts(t2))        # пульс — прогресс есть
    fw.run_tick(now=t2, toast_fn=_NoToast(), stall_no_lock_min=60, **p)
    esc2 = p["escalations_file"].read_text(encoding="utf-8")
    assert esc2.count("FACTORY-STALLED") == 1
    assert "[resolved:factory-watchdog-recovered]" in esc2

    # тик 3: снова тишина > порога -> ok -> stalled (повторный стук)
    t3 = t2 + datetime.timedelta(minutes=61)
    fw.run_tick(now=t3, toast_fn=_NoToast(), stall_no_lock_min=60, **p)
    esc3 = p["escalations_file"].read_text(encoding="utf-8")

    assert esc3.count("FACTORY-STALLED") == 1                        # ТА ЖЕ строка, не вторая
    assert "[resolved:" not in esc3                                  # маркер снят повторным стуком


# --- Н-5 (критик-пин, 2026-08-16): битый лок при mode=active -> порог in-pass, не no-lock ---

def test_corrupt_lock_active_mode_uses_inpass_threshold_not_no_lock_threshold(tmp_path):
    """Битый лок при активном mode = «лок есть» (К3 п.0) -> порог
    STALL_IN_PASS (90), НЕ STALL_NO_LOCK (60). 75 мин: было бы STALLED
    при (ошибочном) пороге 60, остаётся ok при верном пороге 90."""
    p = _paths(tmp_path)
    _write_sla(p)
    started = NOW - datetime.timedelta(minutes=75)
    _write_state(p, last_state="ok", last_progress_ts=fw._fmt_ts(started),
                last_mode_snapshot=_mode_snap_dict("active", fw._fmt_ts(started)), notes=[])
    _write_mode(p, mode="active", updated_ts=fw._fmt_ts(started))
    p["lock_file"].parent.mkdir(parents=True, exist_ok=True)
    p["lock_file"].write_text("garbage, not json", encoding="utf-8")

    code = fw.run_tick(now=NOW, toast_fn=_NoToast(), stall_no_lock_min=60,
                       stall_inpass_min=90, **p)

    assert code == 0
    assert _read_state(p)["last_state"] == "ok"
