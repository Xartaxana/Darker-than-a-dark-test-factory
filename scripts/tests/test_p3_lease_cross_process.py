"""spec-p3-second-emulator N3, БЛОКЕР B-R2-1 (критик-раунд 2): связка
«взятие лизы в процессе А -> чокпоинт в процессе Б» на НАСТОЯЩИХ отдельных
процессах.

Почему отдельный файл, а не проба внутри `test_p3_use_device_stack.py`
(PS-сторона) или `framework/tests/test_device_lease_checkpoint_unit.py`
(python-сторона): воспроизведённый критиком дефект жил РОВНО В ШВЕ между
ними — каждая сторона по отдельности была зелёной. Процесс А — реальный
`powershell` (`Use-DeviceStack -N 1`), процесс Б — реальный python-подпроцесс
с ЧИСТЫМ окружением (без `AO3_DEVICE_LEASE_TOKEN`, как у pytest, запущенного
отдельно от powershell-процесса взятия). Инжектированных резолверов нет ни на
одной стороне.

Device-free: `$root` PS-стороны переопределён на `tmp_path`, а
`driver_factory._device_lease_file` в подпроцессе указывает на тот же
`tmp_path`-файл — реальный `state/device-lease-*.json` не трогается,
устройство/Appium не нужны.

Интерпретатор процесса Б: `framework/.venv` (нужен `appium` в site-packages).
В worktree его нет (gitignore) — берём venv ГЛАВНОГО чекаута, а
`PYTHONPATH` направляем на ЭТОТ worktree, чтобы упражнялся КОД ЭТОЙ правки
(тот же приём, что self-check фреймворк-юнитов из worktree).
"""
from __future__ import annotations

import getpass
import json
import os
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from _ps1_helpers import dot_source_prefix, run_ps

_WORKTREE_ROOT = Path(__file__).resolve().parents[2]
_MAIN_CHECKOUT = Path("D:/AO3_tests")


def _owner_label() -> str:
    user = os.environ.get("USERNAME") or getpass.getuser()
    host = os.environ.get("COMPUTERNAME") or socket.gethostname()
    return f"{user}@{host}"


def _venv_python() -> Path:
    """Первый интерпретатор, который РЕАЛЬНО может импортировать
    `framework.core.driver_factory` с PYTHONPATH на worktree (проверяем
    запуском, а не существованием файла — F-30: утверждение о среде только
    после измерения)."""
    candidates = [
        _WORKTREE_ROOT / "framework" / ".venv" / "Scripts" / "python.exe",
        _MAIN_CHECKOUT / "framework" / ".venv" / "Scripts" / "python.exe",
        Path(sys.executable),
    ]
    env = {k: v for k, v in os.environ.items() if k != "AO3_DEVICE_LEASE_TOKEN"}
    env["PYTHONPATH"] = str(_WORKTREE_ROOT)
    for cand in candidates:
        if not cand.exists():
            continue
        probe = subprocess.run(
            [str(cand), "-c", "from framework.core import driver_factory"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(_WORKTREE_ROOT), env=env, timeout=120,
        )
        if probe.returncode == 0:
            return cand
    pytest.skip(
        "нет интерпретатора, способного импортировать framework.core.driver_factory "
        f"(пробовал: {[str(c) for c in candidates]}) — framework/.venv не найден"
    )


_CHECKPOINT_SCRIPT = """
import json, os, pathlib, sys
sys.path.insert(0, sys.argv[1])
from framework.config import settings
settings.DEVICE_NAME = "emulator-5554"
settings.APPIUM_URL = "http://127.0.0.1:4723"
from framework.core import driver_factory
lease_path = pathlib.Path(sys.argv[2])
driver_factory._device_lease_file = lambda stack: lease_path
print("ENV_TOKEN=%r" % os.environ.get("AO3_DEVICE_LEASE_TOKEN"))
try:
    driver_factory.check_device_lease()
    print("CHECKPOINT_OK PID=%d" % os.getpid())
except BaseException as exc:
    print("CHECKPOINT_FAIL %s: %s" % (type(exc).__name__, exc))
"""


def _run_checkpoint(lease_file: Path, token: str | None = None) -> subprocess.CompletedProcess:
    """Процесс Б: НАСТОЯЩИЙ отдельный python. По умолчанию — с ЧИСТЫМ
    окружением (без env-токена, шов B-R2-1); с `token` — токенная ветка
    `is_own` (шов B-R4-2: унаследованный токен НЕ легализует второй
    одновременный прогон)."""
    env = {k: v for k, v in os.environ.items() if k != "AO3_DEVICE_LEASE_TOKEN"}
    if token:
        env["AO3_DEVICE_LEASE_TOKEN"] = token
    env["PYTHONPATH"] = str(_WORKTREE_ROOT)
    return subprocess.run(
        [str(_venv_python()), "-c", _CHECKPOINT_SCRIPT, str(_WORKTREE_ROOT), str(lease_file)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(_WORKTREE_ROOT), env=env, timeout=300,
    )


# Как _CHECKPOINT_SCRIPT, но ПОСЛЕ успешного чокпоинта процесс ЖИВЁТ ещё
# argv[3] секунд (flush обязателен — первая строка читается через pipe, пока
# процесс жив): конкуренты обязаны видеть ЖИВОЙ pytest_pid победителя, иначе
# последовательная адопция (легальная!) неотличима от одновременного прохода.
_CHECKPOINT_HOLD_SCRIPT = """
import json, os, pathlib, sys, time
sys.path.insert(0, sys.argv[1])
from framework.config import settings
settings.DEVICE_NAME = "emulator-5554"
settings.APPIUM_URL = "http://127.0.0.1:4723"
from framework.core import driver_factory
lease_path = pathlib.Path(sys.argv[2])
driver_factory._device_lease_file = lambda stack: lease_path
try:
    driver_factory.check_device_lease()
    print("CHECKPOINT_OK PID=%d" % os.getpid(), flush=True)
    time.sleep(float(sys.argv[3]))
except BaseException as exc:
    print("CHECKPOINT_FAIL %s: %s" % (type(exc).__name__, exc), flush=True)
"""


def _spawn_holding_checkpoint(lease_file: Path, hold_seconds: float,
                              token: str | None = None) -> subprocess.Popen:
    env = {k: v for k, v in os.environ.items() if k != "AO3_DEVICE_LEASE_TOKEN"}
    if token:
        env["AO3_DEVICE_LEASE_TOKEN"] = token
    env["PYTHONPATH"] = str(_WORKTREE_ROOT)
    return subprocess.Popen(
        [str(_venv_python()), "-c", _CHECKPOINT_HOLD_SCRIPT,
         str(_WORKTREE_ROOT), str(lease_file), str(hold_seconds)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace",
        cwd=str(_WORKTREE_ROOT), env=env,
    )


def _take_lease_via_powershell(tmp_path: Path) -> str:
    """Процесс А: реальный `powershell`, дефолтный путь взятия."""
    cp = run_ps(dot_source_prefix(fake_root=tmp_path) + "Use-DeviceStack -N 1; Write-Output \"T=$($env:AO3_DEVICE_LEASE_TOKEN)\"")
    assert cp.returncode == 0, f"stdout={cp.stdout}\nstderr={cp.stderr}"
    token = [l for l in cp.stdout.splitlines() if l.startswith("T=")][0].split("=", 1)[1]
    assert token
    return token


def test_lease_taken_in_powershell_is_accepted_by_checkpoint_in_another_process(tmp_path):
    """B-R2-1, воспроизведение критика `r2_flow`: `Use-DeviceStack -N 1`
    процессом А -> `check_device_lease()` процессом Б. РАНЬШЕ процесс Б
    получал `DeviceLeaseError` ("стек 1 — конфликт с чужой АКТИВНОЙ лизой"),
    потому что env-токен не наследуется. ТЕПЕРЬ Б адоптирует свой же тикет по
    owner_label + device/appium_url и штампует собственный PID."""
    token = _take_lease_via_powershell(tmp_path)
    lease_file = tmp_path / "state" / "device-lease-1.json"
    assert json.loads(lease_file.read_text(encoding="utf-8"))["pytest_pid"] is None

    cp = _run_checkpoint(lease_file)

    assert "ENV_TOKEN=None" in cp.stdout, "процесс Б обязан идти БЕЗ env-токена (иначе шов не проверен)"
    assert "CHECKPOINT_OK" in cp.stdout, f"stdout={cp.stdout}\nstderr={cp.stderr}"
    child_pid = int([l for l in cp.stdout.splitlines() if l.startswith("CHECKPOINT_OK")][0].split("PID=")[1])
    data = json.loads(lease_file.read_text(encoding="utf-8"))
    assert data["pytest_pid"] == child_pid, "чокпоинт обязан заштамповать PID СВОЕГО процесса"
    assert data["owner_token"] == token, "адопция чокпоинтом НЕ меняет токен тикета"
    assert data["owner_label"] == _owner_label()


def test_second_pass_five_minutes_later_full_cycle(tmp_path):
    """B-R2-1, второй воспроизведённый критиком сценарий ("второй проход через
    5 минут"), теперь СКВОЗНО: прогон 1 (PS-взятие + чокпоинт, штампующий
    PID) закончился, его процесс умер; прогон 2 из НОВОГО powershell делает
    обычный `Use-DeviceStack -N 1` и снова гоняет чокпоинт. РАНЬШЕ: THROWN
    (idle-чужой). ТЕПЕРЬ: обе стороны продолжают тикет."""
    _take_lease_via_powershell(tmp_path)
    lease_file = tmp_path / "state" / "device-lease-1.json"
    cp_first = _run_checkpoint(lease_file)
    assert "CHECKPOINT_OK" in cp_first.stdout, cp_first.stdout
    dead_pid = int([l for l in cp_first.stdout.splitlines() if l.startswith("CHECKPOINT_OK")][0].split("PID=")[1])

    # Процесс чокпоинта уже завершился -> его PID мёртв (проба на РЕАЛЬНОЙ
    # смерти, не на инжектированном резолвере). Состарим heartbeat на 5 минут,
    # как в сценарии критика.
    data = json.loads(lease_file.read_text(encoding="utf-8"))
    assert data["pytest_pid"] == dead_pid
    aged = datetime.now(timezone.utc).timestamp() - 300
    aged_iso = datetime.fromtimestamp(aged, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    data["heartbeat_utc"] = aged_iso
    data["taken_utc"] = aged_iso
    lease_file.write_text(json.dumps(data), encoding="utf-8")

    cp_ps = run_ps(
        dot_source_prefix(fake_root=tmp_path) +
        "Remove-Item Env:\\AO3_DEVICE_LEASE_TOKEN -ErrorAction SilentlyContinue; " +
        "try { Use-DeviceStack -N 1; Write-Output \"T=$($env:AO3_DEVICE_LEASE_TOKEN)\" } " +
        "catch { Write-Output \"THROWN: $($_.Exception.Message)\" }"
    )
    assert "THROWN" not in cp_ps.stdout, cp_ps.stdout
    assert "".join(cp_ps.stdout.split()).count("ПРОДОЛЖЕНАадопцией") == 1

    cp_second = _run_checkpoint(lease_file)
    assert "CHECKPOINT_OK" in cp_second.stdout, f"stdout={cp_second.stdout}\nstderr={cp_second.stderr}"


def test_simultaneous_checkpoints_admit_exactly_one(tmp_path):
    """B-R4-1 (критик-раунд 4, ДЕТЕКТОР КЛАССА «конкурентный второй процесс»):
    4 ОДНОВРЕМЕННЫХ чокпоинта на свежей лизе (pytest_pid=null) — пройти обязан
    РОВНО ОДИН. До CAS-фикса замер критика (r4_simul) давал 4 из 4.

    Победитель после прохода ЖИВЁТ (hold) — конкуренты обязаны видеть его
    живой pytest_pid; каждый пишет ровно одну первую строку, читаем её через
    pipe, не дожидаясь конца hold-сна."""
    _take_lease_via_powershell(tmp_path)
    lease_file = tmp_path / "state" / "device-lease-1.json"
    assert json.loads(lease_file.read_text(encoding="utf-8"))["pytest_pid"] is None

    procs = [_spawn_holding_checkpoint(lease_file, 30) for _ in range(4)]
    try:
        first_lines = [p.stdout.readline().strip() for p in procs]
    finally:
        for p in procs:
            p.kill()
        for p in procs:
            p.wait(timeout=30)

    oks = [l for l in first_lines if l.startswith("CHECKPOINT_OK")]
    fails = [l for l in first_lines if l.startswith("CHECKPOINT_FAIL")]
    assert len(oks) == 1, f"одновременный чокпоинт обязан пропустить РОВНО ОДИН прогон: {first_lines}"
    assert len(fails) == 3, first_lines
    assert all("DEVICE_LEASE_BLOCKED" in l for l in fails), first_lines
    # лиза несёт PID именно победителя
    winner_pid = int(oks[0].split("PID=")[1])
    assert json.loads(lease_file.read_text(encoding="utf-8"))["pytest_pid"] == winner_pid


def test_checkpoint_same_token_blocked_while_first_run_alive(tmp_path):
    """B-R4-2 (критик-раунд 4, r4_sametoken): процесс Б с ТЕМ ЖЕ env-токеном
    (унаследованное окружение) при ЖИВОМ прогоне А — отказ токенной ветки,
    PID живого А в лизе НЕ затёрт. До фикса Б проходил и перезаписывал pid."""
    token = _take_lease_via_powershell(tmp_path)
    lease_file = tmp_path / "state" / "device-lease-1.json"

    proc_a = _spawn_holding_checkpoint(lease_file, 60, token=token)
    try:
        first_a = proc_a.stdout.readline().strip()
        assert first_a.startswith("CHECKPOINT_OK"), first_a
        pid_a = int(first_a.split("PID=")[1])

        cp_b = _run_checkpoint(lease_file, token=token)

        assert "CHECKPOINT_FAIL" in cp_b.stdout, f"stdout={cp_b.stdout}\nstderr={cp_b.stderr}"
        assert "DEVICE_LEASE_BLOCKED" in cp_b.stdout
        assert "B-R4-2" in cp_b.stdout, "отказ обязан идти из предиката токенной ветки"
        after = json.loads(lease_file.read_text(encoding="utf-8"))
        assert after["pytest_pid"] == pid_a, "PID живого прогона А затёрт вторым процессом"
    finally:
        proc_a.kill()
        proc_a.wait(timeout=30)


def test_checkpoint_refuses_when_another_live_run_holds_the_lease(tmp_path):
    """B-R2-2 в кросс-процессном виде: под лизой ЖИВОЙ pytest_pid (настоящий
    подпроцесс-заглушка) — чокпоинт ЧУЖОГО процесса обязан отказать
    `DEVICE_LEASE_BLOCKED`, а не адоптировать."""
    _take_lease_via_powershell(tmp_path)
    lease_file = tmp_path / "state" / "device-lease-1.json"
    stub = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    try:
        data = json.loads(lease_file.read_text(encoding="utf-8"))
        data["pytest_pid"] = stub.pid
        lease_file.write_text(json.dumps(data), encoding="utf-8")

        cp = _run_checkpoint(lease_file)

        assert "CHECKPOINT_FAIL" in cp.stdout, cp.stdout
        assert "DEVICE_LEASE_BLOCKED" in cp.stdout
        after = json.loads(lease_file.read_text(encoding="utf-8"))
        assert after["pytest_pid"] == stub.pid, "лиза живого прогона НЕ перехвачена"
    finally:
        stub.kill()
        stub.wait(timeout=30)
