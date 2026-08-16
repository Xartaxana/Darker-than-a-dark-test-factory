"""Юнит-тесты `run_fallback_pass` (Д1 ночной резерв, консолидированная
секция spec-factory-window v7, docs/tasks/factory-visible-window.md).

Изоляция — тот же класс, что test_heartbeat_wrap*.py: все пути под
tmp_path, Popen подменяется монкипатчем hw._popen. `_run_child`
(общее ядро) уже покрыт транзитивно существующими test_heartbeat_wrap*
пинами через run_pass — здесь фокус на том, что ДОБАВЛЯЕТ
run_fallback_pass поверх ядра: budget_enabled=False недостижимость,
on_spawn/on_pass_done коллбэки + откат на spawn_failed, лог-файл, исход-
словарь.
"""
from __future__ import annotations

import datetime
import json
import subprocess

import pytest

import heartbeat_wrap as hw
import loop_lock as ll

NOW = datetime.datetime(2026, 8, 16, 22, 0, 0, tzinfo=datetime.timezone.utc)


def _sla(tmp_path, lock_stale=2):
    p = tmp_path / "state" / "sla.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"version: 1\nthresholds:\n  lock_stale: {lock_stale}\n", encoding="utf-8")
    return p


def _paths(tmp_path, **sla_kw):
    return {
        "lock_file": tmp_path / "state" / "loop.lock",
        "reaps_path": tmp_path / "state" / "loop-lock-reaps.json",
        "escalations_path": tmp_path / "state" / "escalations.md",
        "sla_path": _sla(tmp_path, **sla_kw),
        "fastdeath_path": tmp_path / "state" / "heartbeat-fastdeath.json",
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
    it = iter(values)

    def fn():
        try:
            return next(it)
        except StopIteration:
            raise AssertionError("time.monotonic() перерасход в тесте")
    return fn


@pytest.fixture()
def orch_log(tmp_path, monkeypatch):
    import log_append as la
    log_path = tmp_path / "state" / "orchestrator-log.md"
    monkeypatch.setattr(la, "ORCH_LOG", log_path, raising=True)
    monkeypatch.setattr(la, "_verify_environment", lambda **kw: (True, ""), raising=True)
    return log_path


# ---------------------------------------------------------------------------
# budget_enabled=True — недостижимость КОДОМ (архив v3 Б3)
# ---------------------------------------------------------------------------

def test_budget_enabled_true_raises_before_any_side_effect(tmp_path, monkeypatch):
    p = _paths(tmp_path)
    calls = []
    monkeypatch.setattr(hw, "_popen", lambda *a, **kw: calls.append(1), raising=True)

    with pytest.raises(NotImplementedError):
        hw.run_fallback_pass(budget_enabled=True, **p)

    assert calls == []
    assert not p["lock_file"].exists()          # acquire даже не пытался — abort ДО всего


# ---------------------------------------------------------------------------
# outcome=busy — лок занят чужим holder'ом, claude НЕ запущен, on_spawn
# НЕ вызван (by construction)
# ---------------------------------------------------------------------------

def test_outcome_busy_does_not_call_on_spawn_or_launch_child(tmp_path, orch_log, monkeypatch):
    p = _paths(tmp_path)
    ll.acquire(lock_file=p["lock_file"], reaps_path=p["reaps_path"],
              escalations_path=p["escalations_path"], sla_path=p["sla_path"],
              holder="qa-loop:other", now=NOW)
    spawn_calls = []
    monkeypatch.setattr(hw, "_popen", lambda *a, **kw: pytest.fail("busy не должен спавнить"),
                        raising=True)

    result = hw.run_fallback_pass(
        on_spawn=lambda: spawn_calls.append(1), now=NOW + datetime.timedelta(minutes=1), **p)

    assert result["outcome"] == "busy"
    assert spawn_calls == []
    assert result["child_rc"] is None
    assert result["fast_death"] is False
    # лок остался чужим — резерв ничего не тронул
    assert json.loads(p["lock_file"].read_text())["holder"] == "qa-loop:other"


# ---------------------------------------------------------------------------
# outcome=spawned, rc==0 — on_spawn вызван РАЗ, on_pass_done вызван с
# (0, runtime), возвращённый snapshot уходит в mode_write
# ---------------------------------------------------------------------------

def test_outcome_spawned_success_calls_on_spawn_and_on_pass_done(tmp_path, orch_log, monkeypatch):
    p = _paths(tmp_path)
    monkeypatch.setattr(hw, "_popen", lambda args, **kw: FakeProc(pid=1, wait_plan=[0]),
                        raising=True)
    monkeypatch.setattr(hw.time, "monotonic", _mono([0.0, 5.0]), raising=True)

    spawn_calls = []
    pass_done_calls = []

    def on_spawn():
        spawn_calls.append(1)
        return None       # без undo

    def on_pass_done(rc, runtime):
        pass_done_calls.append((rc, runtime))
        return {"passes_done": 1, "driver": "watchdog-fallback"}

    result = hw.run_fallback_pass(on_spawn=on_spawn, on_pass_done=on_pass_done, now=NOW, **p)

    assert result["outcome"] == "spawned"
    assert result["child_rc"] == 0
    assert result["fast_death"] is False
    assert spawn_calls == [1]
    assert pass_done_calls == [(0, 5.0)]
    assert result["mode_write"] == {"passes_done": 1, "driver": "watchdog-fallback"}
    assert result["holder"].startswith("heartbeat:")
    assert not p["lock_file"].exists()                  # released


# ---------------------------------------------------------------------------
# outcome=spawned, rc!=0 быстрый (<120с) — on_pass_done НЕ вызван (только
# rc==0 запускает CAS-инкремент); fast_death True, fastdeath-файл инкрементнул
# ---------------------------------------------------------------------------

def test_outcome_spawned_fast_death_does_not_call_on_pass_done(tmp_path, orch_log, monkeypatch):
    p = _paths(tmp_path)
    monkeypatch.setattr(hw, "_popen", lambda args, **kw: FakeProc(pid=1, wait_plan=[1]),
                        raising=True)
    monkeypatch.setattr(hw.time, "monotonic", _mono([0.0, 1.0]), raising=True)
    pass_done_calls = []

    result = hw.run_fallback_pass(
        on_pass_done=lambda rc, rt: pass_done_calls.append((rc, rt)), now=NOW, **p)

    assert result["outcome"] == "spawned"
    assert result["child_rc"] == 1
    assert result["fast_death"] is True
    assert pass_done_calls == []
    data = json.loads(p["fastdeath_path"].read_text(encoding="utf-8"))
    assert data["count"] == 1


# ---------------------------------------------------------------------------
# outcome=spawned, rc!=0 медленный (>=120с) — fast_death False, fastdeath
# НЕ тронут (дизъюнктные серии, slowdeath — забота вызывающего сторожа)
# ---------------------------------------------------------------------------

def test_outcome_spawned_slow_death_is_noop_for_fastdeath(tmp_path, orch_log, monkeypatch):
    p = _paths(tmp_path)
    monkeypatch.setattr(hw, "_popen", lambda args, **kw: FakeProc(pid=1, wait_plan=[1]),
                        raising=True)
    monkeypatch.setattr(hw.time, "monotonic", _mono([0.0, hw.FAST_DEATH_SEC + 10]), raising=True)

    result = hw.run_fallback_pass(now=NOW, **p)

    assert result["outcome"] == "spawned"
    assert result["child_rc"] == 1
    assert result["fast_death"] is False
    assert not p["fastdeath_path"].exists()


# ---------------------------------------------------------------------------
# outcome=spawn_failed — on_spawn вызван (инкремент), Popen падает, ЕГО
# возвращённый undo-коллбэк вызывается (компенсирующий откат, non-throwing),
# лок релизится (не сиротится)
# ---------------------------------------------------------------------------

def test_outcome_spawn_failed_calls_undo_and_releases_lock(tmp_path, orch_log, monkeypatch):
    p = _paths(tmp_path)

    def boom(args, **kw):
        raise OSError("no such file or directory: claude.cmd")

    monkeypatch.setattr(hw, "_popen", boom, raising=True)

    undo_calls = []

    def on_spawn():
        return lambda: undo_calls.append(1)     # undo callable

    result = hw.run_fallback_pass(on_spawn=on_spawn, now=NOW, **p)

    assert result["outcome"] == "spawn_failed"
    assert result["child_rc"] is None
    assert undo_calls == [1]                    # откат случился
    assert not p["lock_file"].exists()           # лок НЕ осиротел
    data = json.loads(p["fastdeath_path"].read_text(encoding="utf-8"))
    assert data["count"] == 1                    # spawn-failed = мгновенная серия (как run_pass)


def test_outcome_spawn_failed_undo_exception_does_not_orphan_lock(tmp_path, orch_log, monkeypatch, capsys):
    """Non-throwing (BL-4): undo-коллбэк САМ бросает — не должен съесть
    релиз лока."""
    p = _paths(tmp_path)

    def boom(args, **kw):
        raise OSError("boom")

    monkeypatch.setattr(hw, "_popen", boom, raising=True)

    def on_spawn():
        def bad_undo():
            raise RuntimeError("undo blew up")
        return bad_undo

    result = hw.run_fallback_pass(on_spawn=on_spawn, now=NOW, **p)

    assert result["outcome"] == "spawn_failed"
    assert not p["lock_file"].exists()
    assert "FALLBACK on_spawn undo failed" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# outcome=timeout_kill — kill-дерево мертво -> released; alive -> лок
# ОСТАЁТСЯ; fastdeath НЕ тронут ни в одном случае
# ---------------------------------------------------------------------------

def test_outcome_timeout_kill_tree_dead_releases_and_skips_fastdeath(
        tmp_path, orch_log, monkeypatch):
    p = _paths(tmp_path)
    monkeypatch.setattr(
        hw, "_popen",
        lambda args, **kw: FakeProc(pid=222, wait_plan=[
            subprocess.TimeoutExpired(cmd="claude", timeout=1), 0]),
        raising=True)
    monkeypatch.setattr(hw, "_taskkill_tree", lambda pid: (0, "SUCCESS"), raising=True)
    monkeypatch.setattr(hw, "_tasklist_alive", lambda pid: False, raising=True)

    result = hw.run_fallback_pass(now=NOW, **p)

    assert result["outcome"] == "timeout_kill"
    assert result["child_rc"] is None
    assert result["fast_death"] is False
    assert not p["lock_file"].exists()
    assert not p["fastdeath_path"].exists()


def test_outcome_timeout_kill_tree_alive_keeps_lock(tmp_path, orch_log, monkeypatch, capsys):
    p = _paths(tmp_path)
    monkeypatch.setattr(
        hw, "_popen",
        lambda args, **kw: FakeProc(pid=333, wait_plan=[
            subprocess.TimeoutExpired(cmd="claude", timeout=1),
            subprocess.TimeoutExpired(cmd="claude", timeout=30)]),
        raising=True)
    monkeypatch.setattr(hw, "_taskkill_tree", lambda pid: (0, "SUCCESS"), raising=True)
    monkeypatch.setattr(hw, "_tasklist_alive", lambda pid: True, raising=True)

    result = hw.run_fallback_pass(now=NOW, **p)

    assert result["outcome"] == "timeout_kill"
    assert p["lock_file"].exists()               # НЕ снят
    assert "kill-failed, лок оставлен" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# child_args по умолчанию — лимит 5, модель sonnet (слово оператора)
# ---------------------------------------------------------------------------

def test_default_child_args_is_qa_loop_5_sonnet(tmp_path, orch_log, monkeypatch):
    p = _paths(tmp_path)
    captured = {}

    def fake_popen(args, **kw):
        captured["args"] = args
        return FakeProc(pid=1, wait_plan=[0])

    monkeypatch.setattr(hw, "_popen", fake_popen, raising=True)
    monkeypatch.setattr(hw.time, "monotonic", _mono([0.0, 1.0]), raising=True)

    hw.run_fallback_pass(now=NOW, **p)

    assert captured["args"][1:] == ["-p", "/qa-loop 5", "--model", "sonnet"]
    assert hw.DEFAULT_FALLBACK_CHILD_ARGS == ["-p", "/qa-loop 5", "--model", "sonnet"]


# ---------------------------------------------------------------------------
# лог ребёнка — файловый дескриптор (НЕ PIPE), закрыт после прохода,
# путь = fallback_log_path(now)
# ---------------------------------------------------------------------------

def test_log_path_opens_file_descriptor_not_pipe_and_closes_it(tmp_path, orch_log, monkeypatch):
    p = _paths(tmp_path)
    log_path = tmp_path / "logs" / "fallback-20260816.log"
    captured_kwargs = {}

    def fake_popen(args, **kw):
        captured_kwargs.update(kw)
        # эмулируем ребёнка, пишущего в переданный fd
        kw["stdout"].write(b"child output line\n")
        return FakeProc(pid=1, wait_plan=[0])

    monkeypatch.setattr(hw, "_popen", fake_popen, raising=True)
    monkeypatch.setattr(hw.time, "monotonic", _mono([0.0, 1.0]), raising=True)

    hw.run_fallback_pass(log_path=log_path, now=NOW, **p)

    assert captured_kwargs["stdout"] is not None
    assert captured_kwargs["stdout"] != subprocess.PIPE     # НЕ PIPE (класс B4)
    assert captured_kwargs["stderr"] == subprocess.STDOUT
    assert captured_kwargs["stdout"].closed                 # закрыт после прохода
    assert log_path.exists()
    assert b"child output line" in log_path.read_bytes()


def test_fallback_log_path_helper_format(tmp_path):
    now = datetime.datetime(2026, 8, 16, 23, 0, 0, tzinfo=datetime.timezone.utc)
    p = hw.fallback_log_path(now, log_dir=tmp_path)
    assert p == tmp_path / "fallback-20260816.log"


# ---------------------------------------------------------------------------
# holder — та же схема heartbeat:*, что run_pass (doctor распознаёт класс)
# ---------------------------------------------------------------------------

def test_holder_uses_heartbeat_prefix_scheme(tmp_path, orch_log, monkeypatch):
    p = _paths(tmp_path)
    monkeypatch.setattr(hw, "_popen", lambda args, **kw: FakeProc(pid=1, wait_plan=[0]),
                        raising=True)
    monkeypatch.setattr(hw.time, "monotonic", _mono([0.0, 1.0]), raising=True)

    result = hw.run_fallback_pass(now=NOW, **p)

    assert result["holder"].startswith("heartbeat:2026-08-16T22:00:00Z:")


# ---------------------------------------------------------------------------
# Б1 (критик-раунд Д1, rework attempt 2): M4-строка ЗА КАЖДЫЙ резервный
# проход, артефакт-колонка logs/fallback-YYYYMMDD.log, НА ВСЕХ исходах —
# юнит на каждый из четырёх (busy/spawned/spawn_failed/timeout_kill).
# ---------------------------------------------------------------------------

def _read_orch(path):
    return path.read_text(encoding="utf-8") if path.exists() else ""


def test_m4_line_written_on_busy(tmp_path, orch_log, monkeypatch):
    p = _paths(tmp_path)
    ll.acquire(lock_file=p["lock_file"], reaps_path=p["reaps_path"],
              escalations_path=p["escalations_path"], sla_path=p["sla_path"],
              holder="qa-loop:other", now=NOW)
    monkeypatch.setattr(hw, "_popen", lambda *a, **kw: pytest.fail("busy не должен спавнить"),
                        raising=True)

    hw.run_fallback_pass(now=NOW, **p)

    text = _read_orch(orch_log)
    assert "logs/fallback-20260816.log" in text
    assert "BUSY, резервный проход не запускался" in text


def test_m4_line_written_on_spawned_success(tmp_path, orch_log, monkeypatch):
    p = _paths(tmp_path)
    monkeypatch.setattr(hw, "_popen", lambda args, **kw: FakeProc(pid=1, wait_plan=[0]),
                        raising=True)
    monkeypatch.setattr(hw.time, "monotonic", _mono([0.0, 1.0]), raising=True)

    hw.run_fallback_pass(now=NOW, **p)

    text = _read_orch(orch_log)
    assert "logs/fallback-20260816.log" in text
    assert "exit=0" in text


def test_m4_line_written_on_spawn_failed(tmp_path, orch_log, monkeypatch):
    p = _paths(tmp_path)

    def boom(args, **kw):
        raise OSError("no such file or directory: claude.cmd")
    monkeypatch.setattr(hw, "_popen", boom, raising=True)

    hw.run_fallback_pass(now=NOW, **p)

    text = _read_orch(orch_log)
    assert "logs/fallback-20260816.log" in text
    assert "spawn-failed:" in text


def test_m4_line_written_on_timeout_kill(tmp_path, orch_log, monkeypatch):
    p = _paths(tmp_path)
    monkeypatch.setattr(
        hw, "_popen",
        lambda args, **kw: FakeProc(pid=222, wait_plan=[
            subprocess.TimeoutExpired(cmd="claude", timeout=1), 0]),
        raising=True)
    monkeypatch.setattr(hw, "_taskkill_tree", lambda pid: (0, "SUCCESS"), raising=True)
    monkeypatch.setattr(hw, "_tasklist_alive", lambda pid: False, raising=True)

    hw.run_fallback_pass(now=NOW, **p)

    text = _read_orch(orch_log)
    assert "logs/fallback-20260816.log" in text
    assert "timeout-kill release=ok" in text


def test_m4_artifact_param_overrides_default(tmp_path, orch_log, monkeypatch):
    """`artifact` — параметр (симметрия run_pass.ARTIFACT), не намертво
    привязан к дате: явное значение переопределяет дефолт."""
    p = _paths(tmp_path)
    monkeypatch.setattr(hw, "_popen", lambda args, **kw: FakeProc(pid=1, wait_plan=[0]),
                        raising=True)
    monkeypatch.setattr(hw.time, "monotonic", _mono([0.0, 1.0]), raising=True)

    hw.run_fallback_pass(now=NOW, artifact="logs/fallback-custom.log", **p)

    text = _read_orch(orch_log)
    assert "logs/fallback-custom.log" in text
    assert "logs/fallback-20260816.log" not in text


def test_m4_line_written_on_wait_exception(tmp_path, orch_log, monkeypatch):
    """Четвёртый крайний случай `_run_child` — child raised во время
    p.wait() (не TimeoutExpired) — тоже пишет M4."""
    p = _paths(tmp_path)
    monkeypatch.setattr(
        hw, "_popen",
        lambda args, **kw: FakeProc(pid=112, wait_plan=[ValueError("boom")]), raising=True)

    hw.run_fallback_pass(now=NOW, **p)

    text = _read_orch(orch_log)
    assert "logs/fallback-20260816.log" in text
    assert "exit=error:" in text and "boom" in text


# ---------------------------------------------------------------------------
# Б1-R2 (критик r2, самоисполнение Lead): отказ M4-писателя не роняет проход
# ---------------------------------------------------------------------------

def test_m4_writer_oserror_does_not_raise_and_pass_completes(tmp_path, orch_log, monkeypatch):
    """OSError из la.append_orchestrator (журнал занят/недоступен) НЕ
    пробрасывается из run_fallback_pass: исход возвращается штатно, лок
    снят — финальная запись state тика сторожа не будет пропущена
    (блокер r2: пропуск state -> следующий тик закрывал эпизод
    собственной записью резерва)."""
    p = _paths(tmp_path)
    monkeypatch.setattr(hw, "_popen", lambda args, **kw: FakeProc(pid=1, wait_plan=[0]),
                        raising=True)
    monkeypatch.setattr(hw.time, "monotonic", _mono([0.0, 1.0]), raising=True)

    def _boom(fields):
        raise OSError("журнал занят")
    monkeypatch.setattr(hw.la, "append_orchestrator", _boom, raising=True)

    r = hw.run_fallback_pass(now=NOW, **p)          # не бросает

    assert r["outcome"] == "spawned" and r["child_rc"] == 0
    assert not p["lock_file"].exists()               # release состоялся


def test_m4_writer_systemexit_swallowed_named_class(tmp_path, orch_log, monkeypatch):
    """SystemExit из la._verify_environment (репо не распознан) — второй
    named-класс: раньше пролетал мимо catch-all main() (except Exception)
    и ронял задачу планировщика вопреки инварианту 'sys.exit(0) всегда'."""
    p = _paths(tmp_path)
    monkeypatch.setattr(hw, "_popen", lambda args, **kw: FakeProc(pid=1, wait_plan=[0]),
                        raising=True)
    monkeypatch.setattr(hw.time, "monotonic", _mono([0.0, 1.0]), raising=True)

    def _exit(fields):
        raise SystemExit("деплой не распознан")
    monkeypatch.setattr(hw.la, "append_orchestrator", _exit, raising=True)

    r = hw.run_fallback_pass(now=NOW, **p)          # SystemExit проглочен

    assert r["outcome"] == "spawned"
    assert not p["lock_file"].exists()


# ---------------------------------------------------------------------------
# Б2: текст эскалации HEARTBEAT-CHILD-DEATH — дословный
# ---------------------------------------------------------------------------

def test_fastdeath_escalation_message_verbatim_points_to_fallback_log_and_two_reset_paths(
        tmp_path, orch_log, monkeypatch):
    p = _paths(tmp_path)
    p["fastdeath_path"].parent.mkdir(parents=True, exist_ok=True)
    p["fastdeath_path"].write_text(json.dumps(
        {"count": 2, "first_ts": "2026-08-16T20:00:00Z",
         "last_ts": "2026-08-16T20:00:00Z", "last_rc": 1}), encoding="utf-8")
    monkeypatch.setattr(hw, "_popen", lambda args, **kw: FakeProc(pid=1, wait_plan=[1]),
                        raising=True)
    monkeypatch.setattr(hw.time, "monotonic", _mono([0.0, 1.0]), raising=True)
    death_moment = datetime.datetime(2026, 8, 16, 22, 5, 0, tzinfo=datetime.timezone.utc)
    monkeypatch.setattr(hw, "_utcnow", lambda: death_moment, raising=True)

    hw.run_fallback_pass(now=NOW, **p)

    esc = p["escalations_path"].read_text(encoding="utf-8")
    assert "HEARTBEAT-CHILD-DEATH" in esc
    assert "logs/fallback-20260816.log" in esc
    assert "сбросит сторож при живом прогрессе окна ИЛИ пробный запуск через 6ч" in esc
    assert "сбросится сам первым здоровым проходом" not in esc   # прежняя формулировка снята
    # r2-фикс висячего указателя: раздел «Единый стартовый гейт» живёт в
    # спеке (docs/tasks/factory-visible-window.md §Д п.6), реализация —
    # factory_watchdog._series_blocked; текст эскалации ведёт в оба места.
    assert "docs/tasks/factory-visible-window.md" in esc
    assert "factory_watchdog._series_blocked" in esc
