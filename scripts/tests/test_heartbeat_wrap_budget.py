"""Юнит-тесты бюджета прогонов heartbeat (spec-heartbeat-budget.md v1,
2026-08-15). Дополнение к test_heartbeat_wrap.py — отдельный файл (owns
scripts/tests/test_heartbeat_wrap*), не трогает существующие тесты.

Изоляция: тот же образец, что test_heartbeat_wrap.py — все пути
(лок/reaps/escalations/sla/budget) под tmp_path, Popen/schtasks
подменяются монкипатчем модульных функций hw._popen/hw._schtasks_disable.
"""
from __future__ import annotations

import datetime

import pytest

import heartbeat_wrap as hw
import loop_lock as ll

NOW = datetime.datetime(2026, 8, 15, 12, 0, 0, tzinfo=datetime.timezone.utc)


def _sla(tmp_path, lock_stale=2):
    p = tmp_path / "state" / "sla.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"version: 1\nthresholds:\n  lock_stale: {lock_stale}\n", encoding="utf-8")
    return p


def _paths(tmp_path, budget=None, **sla_kw):
    """budget=None -> файла нет (безлимит). Иначе пишет str(budget) как
    есть в budget_path — даёт задавать и мусорные значения ("abc"/""/" ")."""
    budget_path = tmp_path / "state" / "heartbeat-budget.txt"
    if budget is not None:
        budget_path.parent.mkdir(parents=True, exist_ok=True)
        budget_path.write_text(str(budget), encoding="utf-8")
    return {
        "lock_file": tmp_path / "state" / "loop.lock",
        "reaps_path": tmp_path / "state" / "loop-lock-reaps.json",
        "escalations_path": tmp_path / "state" / "escalations.md",
        "sla_path": _sla(tmp_path, **sla_kw),
        "budget_path": budget_path,
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


@pytest.fixture()
def orch_log(tmp_path, monkeypatch):
    """append_orchestrator пишет в state/orchestrator-log.md — тот же
    приём, что test_heartbeat_wrap.py::orch_log."""
    import log_append as la
    log_path = tmp_path / "state" / "orchestrator-log.md"
    monkeypatch.setattr(la, "ORCH_LOG", log_path, raising=True)
    monkeypatch.setattr(la, "_verify_environment", lambda **kw: (True, ""), raising=True)
    return log_path


def _read(path):
    return path.read_text(encoding="utf-8") if path.exists() else ""


# ---------------------------------------------------------------------------
# файла нет — безлимит (регресс-пин текущего поведения байт-в-байт)
# ---------------------------------------------------------------------------

def test_no_budget_file_is_unlimited_regression(tmp_path, orch_log, monkeypatch):
    p = _paths(tmp_path)                                     # budget=None -> файла нет
    calls = []

    def fake_popen(args, env):
        calls.append(1)
        return FakeProc(pid=1, wait_plan=[0])

    monkeypatch.setattr(hw, "_popen", fake_popen, raising=True)

    rc = hw.run_pass(now=NOW, **p)

    assert rc == 0
    assert calls == [1]                                      # claude запущен как раньше
    assert not p["budget_path"].exists()                      # файл не создаётся сам по себе
    assert "exit=0" in _read(orch_log)


# ---------------------------------------------------------------------------
# N=1 — запуск, файл стал "0" (следующий тик — disable-ветка)
# ---------------------------------------------------------------------------

def test_budget_one_launches_and_decrements_to_zero(tmp_path, orch_log, monkeypatch):
    p = _paths(tmp_path, budget=1)
    monkeypatch.setattr(hw, "_popen",
                        lambda args, env: FakeProc(pid=1, wait_plan=[0]), raising=True)

    rc = hw.run_pass(now=NOW, **p)

    assert rc == 0
    assert p["budget_path"].read_text(encoding="utf-8") == "0"
    assert "exit=0" in _read(orch_log)


# ---------------------------------------------------------------------------
# N=0 / N=-1 — disable-ветка (границы M6: на границе и за ней)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("budget_value", [0, -1])
def test_budget_exhausted_disables_task_and_escalates(
        tmp_path, orch_log, monkeypatch, budget_value):
    p = _paths(tmp_path, budget=budget_value)
    calls = []
    monkeypatch.setattr(hw, "_popen", lambda args, env: calls.append(1), raising=True)
    disable_calls = []
    monkeypatch.setattr(
        hw, "_schtasks_disable",
        lambda: (disable_calls.append(1), (0, "SUCCESS"))[1], raising=True)

    rc = hw.run_pass(now=NOW, **p)

    assert rc == 0
    assert calls == []                                        # claude НЕ запущен
    assert disable_calls == [1]                               # schtasks вызван
    assert p["budget_path"].read_text(encoding="utf-8") == str(budget_value)  # файл НЕ удалён/тронут
    assert not p["lock_file"].exists()                         # лок освобождён (был наш)

    esc = _read(p["escalations_path"])
    assert "**HEARTBEAT-BUDGET**" in esc
    assert "[heartbeat:budget]" in esc
    assert "бюджет исчерпан" in esc

    orch = _read(orch_log)
    assert "budget<=0" in orch
    assert "disable=ok" in orch


def test_budget_exhausted_disable_failure_logged_as_noop(tmp_path, orch_log, monkeypatch, capsys):
    p = _paths(tmp_path, budget=0)
    monkeypatch.setattr(
        hw, "_popen",
        lambda args, env: pytest.fail("claude не должен запускаться"), raising=True)
    monkeypatch.setattr(
        hw, "_schtasks_disable", lambda: (1, "ERROR: задача не найдена"), raising=True)

    rc = hw.run_pass(now=NOW, **p)

    assert rc == 0
    out = capsys.readouterr().out
    assert "disable failed" in out                            # отказ disable → лог «disable failed»
    orch = _read(orch_log)
    assert "disable=failed" in orch
    # эскалация всё равно записана — исчерпание не зависит от успеха disable,
    # следующий тик — no-op-повтор (файл бюджета всё ещё <= 0)
    assert "HEARTBEAT-BUDGET" in _read(p["escalations_path"])


def test_budget_escalation_dedup_updates_in_place(tmp_path, orch_log, monkeypatch):
    """Два прохода подряд с исчерпанным бюджетом не дублируют строку
    эскалации (та же дедуп-семантика по фиксированному ключу, что
    loop_lock._write_loop_escalation по LOOP-N)."""
    p = _paths(tmp_path, budget=0)
    monkeypatch.setattr(
        hw, "_popen",
        lambda args, env: pytest.fail("не должен запускаться"), raising=True)
    monkeypatch.setattr(hw, "_schtasks_disable", lambda: (0, "SUCCESS"), raising=True)

    hw.run_pass(now=NOW, **p)
    hw.run_pass(now=NOW + datetime.timedelta(minutes=30), **p)

    esc = _read(p["escalations_path"])
    assert esc.count("HEARTBEAT-BUDGET") == 1


# ---------------------------------------------------------------------------
# corrupted — "abc" / пустой / пробельный: НЕ запускать, НЕ отключать
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw", ["abc", "", "   ", "\t\n"])
def test_budget_corrupt_blocks_launch_without_disabling(tmp_path, orch_log, monkeypatch, raw):
    p = _paths(tmp_path, budget=raw)
    calls = []
    monkeypatch.setattr(hw, "_popen", lambda args, env: calls.append(1), raising=True)
    disable_calls = []
    monkeypatch.setattr(hw, "_schtasks_disable", lambda: disable_calls.append(1), raising=True)

    rc = hw.run_pass(now=NOW, **p)

    assert rc == 0
    assert calls == []                                         # claude НЕ запущен
    assert disable_calls == []                                 # задача НЕ отключена
    assert p["budget_path"].read_text(encoding="utf-8") == raw  # файл не тронут — оператор чинит
    assert not p["lock_file"].exists()                          # лок освобождён

    esc = _read(p["escalations_path"])
    assert "HEARTBEAT-BUDGET" in esc
    assert "не парсится" in esc

    orch = _read(orch_log)
    assert "budget=corrupt" in orch


# ---------------------------------------------------------------------------
# spawn упал → бюджет не сожжён (декремент только после успешного Popen)
# ---------------------------------------------------------------------------

def test_spawn_failure_does_not_burn_budget(tmp_path, orch_log, monkeypatch):
    p = _paths(tmp_path, budget=3)

    def boom(args, env):
        raise OSError("no such file or directory: claude.cmd")

    monkeypatch.setattr(hw, "_popen", boom, raising=True)

    rc = hw.run_pass(now=NOW, **p)

    assert rc == 0
    assert p["budget_path"].read_text(encoding="utf-8") == "3"  # НЕ сожжён
    assert not p["lock_file"].exists()                          # лок всё равно освобождён
    orch = _read(orch_log)
    assert "spawn-failed" in orch


# ---------------------------------------------------------------------------
# Патч D (критик, rework attempt 2, 2026-08-15) — 5 доп. тестов
# ---------------------------------------------------------------------------

def test_busy_shortcut_does_not_burn_budget(tmp_path, orch_log, monkeypatch):
    """BUSY-шорткат — строго ДО бюджета: чужой лок с валидным budget=2 не
    должен ни звать claude, ни трогать файл бюджета, ни звать disable."""
    p = _paths(tmp_path, budget=2)
    ll.acquire(lock_file=p["lock_file"], reaps_path=p["reaps_path"],
              escalations_path=p["escalations_path"], sla_path=p["sla_path"],
              holder="heartbeat:other:aaaaaaaa", now=NOW)

    monkeypatch.setattr(
        hw, "_popen",
        lambda args, env: pytest.fail("BUSY не должен запускать claude"), raising=True)
    monkeypatch.setattr(
        hw, "_schtasks_disable",
        lambda: pytest.fail("BUSY не жжёт бюджет — disable не должен вызываться"),
        raising=True)

    rc = hw.run_pass(now=NOW + datetime.timedelta(minutes=5), **p)

    assert rc == 0
    assert p["budget_path"].read_text(encoding="utf-8") == "2"    # бюджет НЕ тронут
    orch = _read(orch_log)
    assert "BUSY, проход не запускался" in orch


@pytest.mark.parametrize("raw,expected", [
    (b"5", 5),
    (b"5\r\n", 5),
    (b"  5  ", 5),
    (b"+5", 5),
    (b"0", 0),
    (b"-1", -1),
    (b"\xef\xbb\xbf5\r\n", 5),          # UTF-8-с-BOM: '3' | Set-Content -Encoding UTF8
    ("5\r\n".encode("utf-16"), 5),       # UTF-16-с-BOM: echo 3 > file (PowerShell 5.1)
], ids=["plain", "crlf", "padded", "plus", "zero", "negative", "utf8-bom", "utf16"])
def test_read_budget_accepts_operator_written_forms(tmp_path, raw, expected):
    budget_path = tmp_path / "state" / "heartbeat-budget.txt"
    budget_path.parent.mkdir(parents=True, exist_ok=True)
    budget_path.write_bytes(raw)

    assert hw._read_budget(budget_path) == expected


@pytest.mark.parametrize("raw", [
    b"",
    b"   \t  ",
    b"abc",
    b"5.0",
    b"\xff\xfe\x00\xd8",                 # битый суррогат (lone high surrogate) под UTF-16
    b"x" * 4096,                         # за потолком _BUDGET_MAX_BYTES
], ids=["empty", "whitespace", "letters", "float-like", "broken-surrogate", "oversized"])
def test_read_budget_corrupt_forms(tmp_path, raw):
    budget_path = tmp_path / "state" / "heartbeat-budget.txt"
    budget_path.parent.mkdir(parents=True, exist_ok=True)
    budget_path.write_bytes(raw)

    assert hw._read_budget(budget_path) == hw._BUDGET_CORRUPT


def test_undecodable_budget_file_does_not_orphan_the_lock(tmp_path, orch_log, monkeypatch):
    """BL-1 (до фикса): read_text(encoding="utf-8") бросал UnicodeDecodeError
    НАРУЖУ run_pass ПОСЛЕ acquire — лок оставался сиротой до TTL. Полный
    run_pass с побитыми байтами: rc=0, лок снят, budget=corrupt в журнале."""
    p = _paths(tmp_path)                                          # budget=None -> файла нет
    p["budget_path"].parent.mkdir(parents=True, exist_ok=True)
    p["budget_path"].write_bytes(b"\xff\xfe\x00\xd8")
    monkeypatch.setattr(
        hw, "_popen",
        lambda args, env: pytest.fail("corrupt не должен запускать claude"), raising=True)

    rc = hw.run_pass(now=NOW, **p)

    assert rc == 0
    assert not p["lock_file"].exists()                            # НЕ сирота
    orch = _read(orch_log)
    assert "budget=corrupt" in orch


def test_run_pass_default_budget_path_is_production_state(tmp_path):
    """Пин дефолта: budget_path продакшен-обёртки — ИМЕННО
    state/heartbeat-budget.txt репозитория. Плюс регресс-щит BL-3 (C1):
    соседний тестовый файл (test_heartbeat_wrap.py) обязан нести
    budget_path в своём _paths() — иначе его run_pass(**p) тихо
    возвращается к боевому DEFAULT_BUDGET_PATH (тот самый прецедент,
    который поймал критик: 17 тестов жгли боевой файл)."""
    assert hw.DEFAULT_BUDGET_PATH == hw.REPO / "state" / "heartbeat-budget.txt"

    import test_heartbeat_wrap as thw
    sibling_paths = thw._paths(tmp_path)
    assert "budget_path" in sibling_paths
