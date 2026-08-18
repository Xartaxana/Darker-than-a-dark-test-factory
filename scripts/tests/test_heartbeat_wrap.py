"""Юнит-тесты scripts/heartbeat_wrap.py (M1+M4, plan-m1-m4.md v3).

Изоляция: все пути лока — tmp_path (нет repo-фикстуры/монкипатча —
run_pass() принимает пути параметрами, тот же стиль, что test_loop_lock.py).
Popen/taskkill/tasklist подменяются монкипатчем модульных функций
hw._popen/hw._taskkill_tree/hw._tasklist_alive — тот же образец, что
FakeRunner в test_build_watch.py (bw._run).

Живой смок kill-дерева (реальный child, спавнящий внука, реальный
taskkill/tasklist) — ОТДЕЛЬНЫЙ прогон вне pytest (см. отчёт builder'а,
раздел R2 плана): teardown-ветка подменяемым раннером не доказуема сама
по себе (класс AT-BUG-014), но здесь она покрыта на уровне ПОРЯДКА
вызовов и решения "снимать/не снимать лок" по факту `_tasklist_alive`.
"""
from __future__ import annotations

import datetime
import json
import os
import subprocess

import pytest

import heartbeat_wrap as hw
import loop_lock as ll

NOW = datetime.datetime(2026, 8, 9, 12, 0, 0, tzinfo=datetime.timezone.utc)


def _sla(tmp_path, lock_stale=2):
    p = tmp_path / "state" / "sla.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"version: 1\nthresholds:\n  lock_stale: {lock_stale}\n", encoding="utf-8")
    return p


def _paths(tmp_path, **sla_kw):
    # Критик-фикс BL-3 (rework attempt 2, 2026-08-15): budget_path ДОБАВЛЕН
    # сюда — без него run_pass(**p) в этом файле читал/писал БОЕВОЙ
    # state/heartbeat-budget.txt (критик замерил: 17 тестов сожгли 9 боевых
    # прогонов; при боевом N<=0 юнит-тест позвал бы НАСТОЯЩИЙ
    # schtasks /disable живой задачи AO3-QA-Heartbeat). tmp_path-путь без
    # созданного файла = безлимит, тот же класс изоляции, что остальные
    # пути ниже.
    # BL-3 расширен spec-heartbeat-fastdeath.md v2 (пин 21): fastdeath_path
    # тем же классом — без него run_pass(**p) читал/писал бы боевой
    # state/heartbeat-fastdeath.json.
    return {
        "lock_file": tmp_path / "state" / "loop.lock",
        "reaps_path": tmp_path / "state" / "loop-lock-reaps.json",
        "escalations_path": tmp_path / "state" / "escalations.md",
        "sla_path": _sla(tmp_path, **sla_kw),
        "budget_path": tmp_path / "state" / "heartbeat-budget.txt",
        "fastdeath_path": tmp_path / "state" / "heartbeat-fastdeath.json",
    }


class FakeProc:
    """Подменяет subprocess.Popen: программируемая последовательность
    .wait() (returncode | raise TimeoutExpired | raise произвольное
    исключение), фиксирует pid и переданный env."""

    def __init__(self, pid, wait_plan, args=None, env=None):
        self.pid = pid
        self._plan = list(wait_plan)
        self.args = args
        self.env = env
        self.wait_calls: list[float | None] = []

    def wait(self, timeout=None):
        self.wait_calls.append(timeout)
        if not self._plan:
            return 0
        step = self._plan.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


@pytest.fixture()
def orch_log(tmp_path, monkeypatch):
    """append_orchestrator пишет в state/orchestrator-log.md — берём
    родной модуль log_append и его REPO-константу под tmp_path (та же
    защита _verify_environment требует каталог+git; создаём .git-маркер
    минимально через monkeypatch _verify_environment на no-op success)."""
    import log_append as la
    log_path = tmp_path / "state" / "orchestrator-log.md"
    monkeypatch.setattr(la, "ORCH_LOG", log_path, raising=True)
    monkeypatch.setattr(la, "_verify_environment", lambda **kw: (True, ""), raising=True)
    return log_path


def _read_orch(path):
    return path.read_text(encoding="utf-8") if path.exists() else ""


# ---------------------------------------------------------------------------
# BUSY — claude не вызван, exit 0, журнальная строка
# ---------------------------------------------------------------------------

def test_busy_does_not_launch_claude_and_logs(tmp_path, orch_log, monkeypatch):
    p = _paths(tmp_path)
    # Критик-фикс BL-3 (C2): ll.acquire не принимает budget_path — явные
    # kwargs вместо **p (которое теперь несёт budget_path для run_pass).
    ll.acquire(lock_file=p["lock_file"], reaps_path=p["reaps_path"],
              escalations_path=p["escalations_path"], sla_path=p["sla_path"],
              holder="heartbeat:other:aaaaaaaa", now=NOW)

    calls = []
    monkeypatch.setattr(hw, "_popen", lambda *a, **kw: calls.append((a, kw)), raising=True)

    rc = hw.run_pass(now=NOW + datetime.timedelta(minutes=5), **p)

    assert rc == 0
    assert calls == []                                   # claude НЕ вызван
    assert "heartbeat:other:aaaaaaaa" in json.loads(p["lock_file"].read_text())["holder"]
    text = _read_orch(orch_log)
    assert "BUSY, проход не запускался" in text


# ---------------------------------------------------------------------------
# happy path — порядок acquire/claude/release/журнал; env дочернего
# содержит AO3_LOOP_HOLDER и не теряет системное окружение
# ---------------------------------------------------------------------------

def test_happy_path_order_and_child_env(tmp_path, orch_log, monkeypatch):
    p = _paths(tmp_path)
    captured = {}

    def fake_popen(args, *, env):
        assert p["lock_file"].exists()                    # acquire уже прошёл (лок на диске)
        captured["args"] = args
        captured["env"] = env
        return FakeProc(pid=4242, wait_plan=[0])

    monkeypatch.setattr(hw, "_popen", fake_popen, raising=True)
    released = {}
    real_release = ll.release

    def spy_release(**kw):
        released["called"] = True
        return real_release(**kw)

    monkeypatch.setattr(ll, "release", spy_release, raising=True)

    rc = hw.run_pass(now=NOW, **p)

    assert rc == 0
    assert released.get("called") is True
    assert not p["lock_file"].exists()                    # released
    assert captured["args"][0] == hw.CLAUDE_CMD
    assert captured["args"][1:] == hw.DEFAULT_CHILD_ARGS
    assert captured["env"]["AO3_LOOP_HOLDER"].startswith("heartbeat:")
    # Критик-фикс (некритично п.6, 2026-08-09): ужато до сравнения СЛОВАРЕЙ
    # целиком (как в test_build_watch.py::test_fetch_env_extra_preserves_
    # os_environ), не только одного ключа PATH — env-надбавка МИНУС
    # AO3_LOOP_HOLDER обязана байт-в-байт совпасть с os.environ.
    # AT-BUG-077 фикс: AO3_LOOP_HOLDER вычёркивается из ОБЕИХ частей —
    # если тестовый процесс сам является дочерним процессом активного
    # heartbeat-цикла (вложенный запуск), os.environ уже несёт унаследо-
    # ванный AO3_LOOP_HOLDER внешнего цикла; вычёркивание только слева
    # ложно ломало сравнение в этом сценарии.
    without_extra = {k: v for k, v in captured["env"].items() if k != "AO3_LOOP_HOLDER"}
    ambient_env = {k: v for k, v in os.environ.items() if k != "AO3_LOOP_HOLDER"}
    assert without_extra == ambient_env
    text = _read_orch(orch_log)
    assert "exit=0" in text


# ---------------------------------------------------------------------------
# child умер/raise — release исполнен + строка с exit
# ---------------------------------------------------------------------------

def test_child_nonzero_exit_still_releases(tmp_path, orch_log, monkeypatch):
    p = _paths(tmp_path)
    monkeypatch.setattr(hw, "_popen",
                        lambda args, env: FakeProc(pid=111, wait_plan=[7]), raising=True)

    rc = hw.run_pass(now=NOW, **p)

    assert rc == 0
    assert not p["lock_file"].exists()
    assert "exit=7" in _read_orch(orch_log)


def test_child_raises_unexpected_exception_still_releases(tmp_path, orch_log, monkeypatch):
    p = _paths(tmp_path)
    monkeypatch.setattr(
        hw, "_popen",
        lambda args, env: FakeProc(pid=112, wait_plan=[ValueError("boom")]), raising=True)

    rc = hw.run_pass(now=NOW, **p)

    assert rc == 0
    assert not p["lock_file"].exists()                    # release всё равно исполнен
    text = _read_orch(orch_log)
    assert "exit=error:" in text and "boom" in text


# ---------------------------------------------------------------------------
# Критик-фикс п.1/п.5 (2026-08-09): rcode ll.release() учитывается —
# REFUSED (fallback-сценарий M2) помечается «release=refused-expected»,
# а исключение release() не съедает M4-строку.
# ---------------------------------------------------------------------------

def test_release_refused_expected_marks_outcome(tmp_path, orch_log, monkeypatch):
    """Симулирует fallback-сценарий M2: пока claude «работал», кто-то
    другой (SKILL под своим qa-loop-holder) перезаписал лок обёртки своим
    holder'ом. К моменту finally `ll.release(holder=<наш>)` получает
    REFUSED (holder не совпал) — ОЖИДАЕМЫЙ исход, помечается суффиксом,
    чужой лок НЕ снимается."""
    p = _paths(tmp_path)

    def fake_popen(args, *, env):
        proc = FakeProc(pid=666, wait_plan=[0])
        p["lock_file"].write_text(
            json.dumps({"holder": "qa-loop:fallback-holder", "pid": 1,
                       "ts": "2026-08-09T12:00:05Z"}),
            encoding="utf-8")
        return proc

    monkeypatch.setattr(hw, "_popen", fake_popen, raising=True)

    rc = hw.run_pass(now=NOW, **p)

    assert rc == 0
    payload = json.loads(p["lock_file"].read_text())
    assert payload["holder"] == "qa-loop:fallback-holder"    # чужой лок НЕ снят
    text = _read_orch(orch_log)
    assert "exit=0 release=refused-expected" in text


def test_release_exception_does_not_eat_journal_line(tmp_path, orch_log, monkeypatch):
    """Критик-фикс п.5: исключение из ll.release() не должно съесть M4-строку."""
    p = _paths(tmp_path)
    monkeypatch.setattr(hw, "_popen",
                        lambda args, env: FakeProc(pid=777, wait_plan=[0]), raising=True)

    def boom_release(**kw):
        raise RuntimeError("release blew up")

    monkeypatch.setattr(ll, "release", boom_release, raising=True)

    rc = hw.run_pass(now=NOW, **p)

    assert rc == 0
    text = _read_orch(orch_log)
    assert "exit=0 release=error:" in text and "release blew up" in text


# ---------------------------------------------------------------------------
# Критик-фикс п.4: _tasklist_alive — ошибка самого tasklist трактуется
# КОНСЕРВАТИВНО как "жив" (унифицировано с doctor.py::_pid_alive, где та
# же ошибка — "неизвестно", третье состояние).
# ---------------------------------------------------------------------------

def test_tasklist_alive_treats_tool_error_rc_as_alive(monkeypatch):
    def fake_run(args, **kw):
        class R:
            returncode = 1
            stdout = "ERROR: недоступен"
            stderr = ""
        return R()
    monkeypatch.setattr(subprocess, "run", fake_run, raising=True)

    assert hw._tasklist_alive(12345) is True


def test_tasklist_alive_treats_oserror_as_alive(monkeypatch):
    def fake_run(args, **kw):
        raise OSError("tasklist not found")
    monkeypatch.setattr(subprocess, "run", fake_run, raising=True)

    assert hw._tasklist_alive(12345) is True


def test_tasklist_alive_confirms_dead_on_clean_empty_result(monkeypatch):
    def fake_run(args, **kw):
        class R:
            returncode = 0
            stdout = "INFO: No tasks are running which match the specified criteria.\n"
            stderr = ""
        return R()
    monkeypatch.setattr(subprocess, "run", fake_run, raising=True)

    assert hw._tasklist_alive(12345) is False


# ---------------------------------------------------------------------------
# timeout → kill-ветка + release + строка «timeout-kill»
# ---------------------------------------------------------------------------

def test_timeout_kill_tree_dead_releases(tmp_path, orch_log, monkeypatch):
    p = _paths(tmp_path)
    monkeypatch.setattr(
        hw, "_popen",
        lambda args, env: FakeProc(pid=222, wait_plan=[
            subprocess.TimeoutExpired(cmd="claude", timeout=1), 0]),
        raising=True)
    kill_calls = []
    monkeypatch.setattr(hw, "_taskkill_tree",
                        lambda pid: (kill_calls.append(pid), (0, "SUCCESS"))[1], raising=True)
    monkeypatch.setattr(hw, "_tasklist_alive", lambda pid: False, raising=True)

    rc = hw.run_pass(now=NOW, **p)

    assert rc == 0
    assert kill_calls == [222]
    assert not p["lock_file"].exists()                    # дерево мертво -> released
    text = _read_orch(orch_log)
    assert "timeout-kill release=ok" in text


def test_timeout_kill_failed_tree_alive_keeps_lock(tmp_path, orch_log, monkeypatch, capsys):
    p = _paths(tmp_path)
    monkeypatch.setattr(
        hw, "_popen",
        lambda args, env: FakeProc(pid=333, wait_plan=[
            subprocess.TimeoutExpired(cmd="claude", timeout=1),
            subprocess.TimeoutExpired(cmd="claude", timeout=30)]),
        raising=True)
    monkeypatch.setattr(hw, "_taskkill_tree", lambda pid: (0, "SUCCESS"), raising=True)
    monkeypatch.setattr(hw, "_tasklist_alive", lambda pid: True, raising=True)

    rc = hw.run_pass(now=NOW, **p)

    assert rc == 0
    assert p["lock_file"].exists()                        # ИСКЛЮЧЕНИЕ: лок НЕ снят
    payload = json.loads(p["lock_file"].read_text())
    assert payload["holder"].startswith("heartbeat:")
    out = capsys.readouterr().out
    assert "kill-failed, лок оставлен" in out
    text = _read_orch(orch_log)
    assert "timeout-kill release=kill-failed" in text


def test_taskkill_error_does_not_eat_release_when_tree_actually_dead(
        tmp_path, orch_log, monkeypatch):
    """Ошибка/отсутствие taskkill сама по себе НЕ съедает release — решение
    принимается ТОЛЬКО по факту _tasklist_alive."""
    p = _paths(tmp_path)
    monkeypatch.setattr(
        hw, "_popen",
        lambda args, env: FakeProc(pid=444, wait_plan=[
            subprocess.TimeoutExpired(cmd="claude", timeout=1), 0]),
        raising=True)
    monkeypatch.setattr(hw, "_taskkill_tree", lambda pid: (127, "taskkill: not found"),
                        raising=True)
    monkeypatch.setattr(hw, "_tasklist_alive", lambda pid: False, raising=True)

    rc = hw.run_pass(now=NOW, **p)

    assert rc == 0
    assert not p["lock_file"].exists()                    # taskkill rc=127 не блокирует release


# ---------------------------------------------------------------------------
# кламп R1 — обе ветки (env 150 при TTL 2ч -> 108; default env при TTL 1ч -> 54)
# ---------------------------------------------------------------------------

def test_max_pass_clamp_env_above_sla_cap(tmp_path, monkeypatch):
    sla = _sla(tmp_path, lock_stale=2)
    monkeypatch.setenv("AO3_HEARTBEAT_MAX_PASS_MIN", "150")

    sec, clamped = hw.compute_max_pass_sec(sla)

    assert clamped is True
    assert sec == pytest.approx(108 * 60)


def test_max_pass_clamp_default_env_tight_sla(tmp_path, monkeypatch):
    sla = _sla(tmp_path, lock_stale=1)
    monkeypatch.delenv("AO3_HEARTBEAT_MAX_PASS_MIN", raising=False)

    sec, clamped = hw.compute_max_pass_sec(sla)

    assert clamped is True
    assert sec == pytest.approx(54 * 60)


def test_max_pass_no_clamp_when_sla_cap_generous(tmp_path, monkeypatch):
    sla = _sla(tmp_path, lock_stale=2)
    monkeypatch.delenv("AO3_HEARTBEAT_MAX_PASS_MIN", raising=False)

    sec, clamped = hw.compute_max_pass_sec(sla)

    assert clamped is False
    assert sec == pytest.approx(hw.DEFAULT_MAX_PASS_MIN * 60)


def test_max_pass_clamp_prints_message(tmp_path, orch_log, monkeypatch, capsys):
    p = _paths(tmp_path, lock_stale=1)                    # 0.9*1*60=54 < default 100
    monkeypatch.delenv("AO3_HEARTBEAT_MAX_PASS_MIN", raising=False)
    monkeypatch.setattr(hw, "_popen",
                        lambda args, env: FakeProc(pid=555, wait_plan=[0]), raising=True)

    hw.run_pass(now=NOW, **p)

    out = capsys.readouterr().out
    assert "MAX_PASS ужат до 54 мин по sla lock_stale" in out


# ---------------------------------------------------------------------------
# holder — нонс на каждый запуск
# ---------------------------------------------------------------------------

def test_new_holder_has_heartbeat_prefix_and_unique_nonce():
    h1 = hw._new_holder(NOW)
    h2 = hw._new_holder(NOW)
    assert h1.startswith("heartbeat:2026-08-09T12:00:00Z:")
    assert h1 != h2                                       # нонс различает запуски
