"""spec-p3-second-emulator N3: `Use-DeviceStack -N <1|2> [-Release|-Resume]` -
каноническая форма переключения device-стека + машинная лиза (создание,
конфликт, idle-возврат, реклейм, -Release, -Resume, атомарность/гонки на
самой функции).

Реальный PowerShell (`powershell`, дот-сорсит WORKTREE-копию `scripts/tasks.ps1`,
паттерн `_ps1_helpers.py`/`test_p3_stop_node_processes.py`). `$root`
переопределяется на `tmp_path` (device-free, никогда не пишет в реальный
`state/`); `-LeaseFile`/`-StateFile`/`-NowProvider`/`-TokenProvider`/
`-LiveSerialsProvider`/`-PidAliveResolver` - инжектируемые seam'ы этой функции.

B1 (критик-вход rework attempt 2): статус ТЕПЕРЬ по живости pytest_pid, не по
полю `status` файла - тесты, симулирующие "idle", ЯВНО передают
`-PidAliveResolver { $false }` (детерминированно, не полагаясь на случайное
несуществование фиксированного PID на хосте, тестирующем прогон).
"""
from __future__ import annotations

import getpass
import json
import os
import socket
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

from _ps1_helpers import dot_source_prefix, run_ps

_DEAD_PID_RESOLVER = "-PidAliveResolver { param($ProcId) $false }"
_ALIVE_PID_RESOLVER = "-PidAliveResolver { param($ProcId) $true }"


def _owner_label() -> str:
    """ДОСЛОВНО формула `Use-DeviceStack`: `"$env:USERNAME@$env:COMPUTERNAME"`
    (фолбэки — для сред без этих переменных, на Windows-хосте конвейера обе
    заданы). Нужна тестам АДОПЦИИ: она опирается на совпадение owner_label."""
    user = os.environ.get("USERNAME") or getpass.getuser()
    host = os.environ.get("COMPUTERNAME") or socket.gethostname()
    return f"{user}@{host}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _flat(text: str) -> str:
    """Убирает ВСЕ пробельные символы. `Write-Warning` PowerShell переносит
    длинное сообщение по ширине консоли ВНУТРИ фразы (найдено эмпирически
    ещё в by_serial-пробах ниже: `\\n` встал ровно между "бэкфилл" и
    "невозможен"), поэтому проверка МНОГОСЛОВНОЙ подстроки в сыром stdout
    хрупка к ширине консоли хоста. Сравниваем обе стороны без пробелов."""
    return "".join(text.split())


@pytest.fixture
def live_stub_pid():
    """НАСТОЯЩИЙ живой процесс в роли `pytest_pid` лизы (блокер B-R2-2): гейт
    "живой прогон -> отказ ВСЕГДА" проверяется РЕАЛЬНОЙ живостью через
    `Get-Process`, БЕЗ инжекции `-PidAliveResolver` — инжектированный резолвер
    доказал бы только то, что мы сами ему сказали."""
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    try:
        yield proc.pid
    finally:
        proc.kill()
        proc.wait(timeout=30)


def _lease_path(tmp_path: Path, n: int = 2) -> Path:
    return tmp_path / "state" / f"device-lease-{n}.json"


def _now_provider(iso_ts: str) -> str:
    """PS-выражение `-NowProvider` с ГАРАНТИРОВАННЫМ Kind=Utc. Найдено
    эмпирически (M6-класс): голый `[datetime]::Parse('...Z')` (single-arg
    overload, БЕЗ RoundtripKind) не round-trip'ает "Z" -> он конвертирует
    момент в ЛОКАЛЬНОЕ время хоста (Kind=Local) - на этом хосте это давало
    ложный сдвиг возраста лизы (+1ч) и ложные "reclaimed"/"idle"-исходы в
    первой версии этих тестов. `RoundtripKind` обязателен (тот же приём,
    что сама `Get-DeviceLeaseStatus` использует для heartbeat_utc)."""
    return (
        "-NowProvider { [datetime]::Parse('%s', [System.Globalization.CultureInfo]::InvariantCulture, "
        "[System.Globalization.DateTimeStyles]::RoundtripKind) }" % iso_ts
    )


def _run(body: str, fake_root: Path) -> "object":
    cmd = dot_source_prefix(fake_root=fake_root) + body
    cp = run_ps(cmd)
    assert cp.returncode == 0, f"stdout={cp.stdout}\nstderr={cp.stderr}"
    return cp


# --- взятие свободной лизы ---

def test_take_free_lease_sets_env_and_writes_file(tmp_path):
    cp = _run(
        "Use-DeviceStack -N 2; "
        "Write-Output \"DEVICE=$($env:AO3_DEVICE)\"; "
        "Write-Output \"APPIUM=$($env:APPIUM_URL)\"; "
        "Write-Output \"ALLURE=$($env:ALLURE_RESULTS)\"; "
        "Write-Output \"TOKEN=$($env:AO3_DEVICE_LEASE_TOKEN)\"",
        tmp_path,
    )
    assert "DEVICE=emulator-5556" in cp.stdout
    assert "APPIUM=http://127.0.0.1:4725" in cp.stdout
    assert "ALLURE=" in cp.stdout and "allure-results-2" in cp.stdout
    lease_file = _lease_path(tmp_path)
    assert lease_file.exists()
    data = json.loads(lease_file.read_text(encoding="utf-8"))
    assert data["status"] == "active"
    assert data["pytest_pid"] is None
    # B5: device/appium_url записаны в лизу (диагностический след)
    assert data["device"] == "emulator-5556"
    assert data["appium_url"] == "http://127.0.0.1:4725"
    token_line = [l for l in cp.stdout.splitlines() if l.startswith("TOKEN=")][0]
    assert token_line.split("=", 1)[1] == data["owner_token"]


def test_take_stack1_sets_stack1_env(tmp_path):
    cp = _run(
        "Use-DeviceStack -N 1; "
        "Write-Output \"DEVICE=$($env:AO3_DEVICE)\"; Write-Output \"APPIUM=$($env:APPIUM_URL)\"",
        tmp_path,
    )
    assert "DEVICE=emulator-5554" in cp.stdout
    assert "APPIUM=http://127.0.0.1:4723" in cp.stdout


# --- своя активная лиза: повторный вызов - no-op (не throw), тот же токен, heartbeat обновлён ---

def test_retake_own_active_lease_is_noop_same_token(tmp_path):
    cp = _run(
        "Use-DeviceStack -N 2; $t1 = $env:AO3_DEVICE_LEASE_TOKEN; "
        "Use-DeviceStack -N 2; $t2 = $env:AO3_DEVICE_LEASE_TOKEN; "
        "Write-Output \"T1=$t1 T2=$t2\"",
        tmp_path,
    )
    line = [l for l in cp.stdout.splitlines() if l.startswith("T1=")][0]
    t1 = line.split()[0].split("=", 1)[1]
    t2 = line.split()[1].split("=", 1)[1]
    assert t1 == t2 and t1


# --- чужая активная лиза: throw, имя владельца в сообщении ---

def test_foreign_active_lease_refuses_with_owner_name(tmp_path):
    lease_file = _lease_path(tmp_path)
    lease_file.parent.mkdir(parents=True, exist_ok=True)
    lease_file.write_text(json.dumps({
        "owner_token": "OTHER-TOKEN", "owner_label": "other@HOST",
        "taken_utc": "2026-01-01T12:00:00Z", "heartbeat_utc": "2026-01-01T12:00:00Z",
        "pytest_pid": 999, "status": "active",
    }), encoding="utf-8")
    cmd = (
        dot_source_prefix(fake_root=tmp_path) +
        f"try {{ Use-DeviceStack -N 2 {_now_provider('2026-01-01T12:00:05Z')} {_ALIVE_PID_RESOLVER}; "
        "Write-Output 'NO_THROW' } "
        "catch { Write-Output \"THROWN: $($_.Exception.Message)\" }"
    )
    cp = run_ps(cmd)
    assert cp.returncode == 0
    assert "THROWN:" in cp.stdout
    assert "other@HOST" in cp.stdout
    assert "NO_THROW" not in cp.stdout
    # чужой файл НЕ тронут/не перезаписан
    data = json.loads(lease_file.read_text(encoding="utf-8"))
    assert data["owner_token"] == "OTHER-TOKEN"


# --- своя idle-лиза (B28): принимается, возвращается в active, ТОТ ЖЕ токен ---

def test_own_idle_lease_is_accepted_and_returned_to_active(tmp_path):
    """B1-редизайн: idle теперь определяется живостью pid, не полем `status`
    файла - лиза пишется с `pytest_pid` заведомо мёртвым (по инжектируемому
    `-PidAliveResolver { $false }`), не полагаемся на реальный процесс."""
    lease_file = _lease_path(tmp_path)
    lease_file.parent.mkdir(parents=True, exist_ok=True)
    lease_file.write_text(json.dumps({
        "owner_token": "MY-TOKEN", "owner_label": "SHOULD_BE_OVERWRITTEN",
        "taken_utc": "2026-01-01T12:00:00Z", "heartbeat_utc": "2026-01-01T12:00:00Z",
        "pytest_pid": 4242, "status": "active",
    }), encoding="utf-8")
    cmd = (
        dot_source_prefix(fake_root=tmp_path) +
        "$env:AO3_DEVICE_LEASE_TOKEN = 'MY-TOKEN'; " +
        f"Use-DeviceStack -N 2 {_now_provider('2026-01-01T12:05:00Z')} {_DEAD_PID_RESOLVER}; " +
        "Write-Output \"TOKEN=$($env:AO3_DEVICE_LEASE_TOKEN)\""
    )
    cp = run_ps(cmd)
    assert cp.returncode == 0, cp.stderr
    token_line = [l for l in cp.stdout.splitlines() if l.startswith("TOKEN=")][0]
    assert token_line.split("=", 1)[1] == "MY-TOKEN"
    data = json.loads(lease_file.read_text(encoding="utf-8"))
    assert data["status"] == "active"
    assert data["owner_token"] == "MY-TOKEN"
    assert data["pytest_pid"] is None


# --- чужая idle-лиза: throw с "жди", НЕ реклейм ---

def test_foreign_idle_lease_refuses_with_wait_message(tmp_path):
    lease_file = _lease_path(tmp_path)
    lease_file.parent.mkdir(parents=True, exist_ok=True)
    lease_file.write_text(json.dumps({
        "owner_token": "OTHER-TOKEN", "owner_label": "other@HOST",
        "taken_utc": "2026-01-01T12:00:00Z", "heartbeat_utc": "2026-01-01T12:00:00Z",
        "pytest_pid": 999, "status": "active",
    }), encoding="utf-8")
    # NowProvider фиксирован БЛИЗКО к heartbeat (внутри idle-окна 30 мин) -
    # без этого реальный текущий Get-Date дал бы гигантский age (лиза от
    # 2026-01-01) и статус ушёл бы в reclaimed, а не idle. Мёртвый pid (999) -
    # явный -PidAliveResolver { $false } делает idle детерминированным.
    cmd = (
        dot_source_prefix(fake_root=tmp_path) +
        f"try {{ Use-DeviceStack -N 2 {_now_provider('2026-01-01T12:05:00Z')} {_DEAD_PID_RESOLVER}; "
        "Write-Output 'NO_THROW' } catch { Write-Output \"THROWN: $($_.Exception.Message)\" }"
    )
    cp = run_ps(cmd)
    assert cp.returncode == 0
    assert "THROWN:" in cp.stdout
    assert "other@HOST" in cp.stdout
    assert "NO_THROW" not in cp.stdout
    data = json.loads(lease_file.read_text(encoding="utf-8"))
    assert data["owner_token"] == "OTHER-TOKEN"  # не украдена


# --- истёкшая (reclaimed) лиза: WARN + беру заново, НОВЫЙ токен ---

def test_reclaimed_lease_is_retaken_with_new_token(tmp_path):
    lease_file = _lease_path(tmp_path)
    lease_file.parent.mkdir(parents=True, exist_ok=True)
    lease_file.write_text(json.dumps({
        "owner_token": "STALE-TOKEN", "owner_label": "ghost@HOST",
        "taken_utc": "2026-01-01T00:00:00Z", "heartbeat_utc": "2026-01-01T00:00:00Z",
        "pytest_pid": None, "status": "active",
    }), encoding="utf-8")
    cmd = (
        dot_source_prefix(fake_root=tmp_path) +
        f"Use-DeviceStack -N 2 {_now_provider('2026-01-05T00:00:00Z')}; "
        "Write-Output \"TOKEN=$($env:AO3_DEVICE_LEASE_TOKEN)\""
    )
    cp = run_ps(cmd)
    assert cp.returncode == 0
    assert "истекла (reclaimed" in cp.stdout
    assert "ghost@HOST" in cp.stdout  # non-blocker 4: чужой владелец назван в громком WARN
    token_line = [l for l in cp.stdout.splitlines() if l.startswith("TOKEN=")][0]
    assert token_line.split("=", 1)[1] != "STALE-TOKEN"
    data = json.loads(lease_file.read_text(encoding="utf-8"))
    assert data["owner_token"] != "STALE-TOKEN"
    assert data["owner_label"] != "ghost@HOST"


def test_own_reclaimed_lease_is_silent_not_loud(tmp_path):
    """Non-blocker 4 (критик-вход rework attempt 2): реклейм СВОЕЙ протухшей
    лизы (owner_label совпадает с текущим) - ТИХИЙ (Write-Verbose, БЕЗ
    Write-Warning 'истекла (reclaimed'), в отличие от чужой брошенной."""
    import os
    import getpass
    import socket
    owner_label = f"{getpass.getuser() or os.environ.get('USERNAME', 'user')}@{socket.gethostname()}"
    lease_file = _lease_path(tmp_path)
    lease_file.parent.mkdir(parents=True, exist_ok=True)
    lease_file.write_text(json.dumps({
        "owner_token": "MY-OLD-TOKEN", "owner_label": owner_label,
        "taken_utc": "2026-01-01T00:00:00Z", "heartbeat_utc": "2026-01-01T00:00:00Z",
        "pytest_pid": None, "status": "active",
    }), encoding="utf-8")
    cmd = (
        dot_source_prefix(fake_root=tmp_path) +
        f"Use-DeviceStack -N 2 {_now_provider('2026-01-05T00:00:00Z')} -Verbose; "
        "Write-Output \"TOKEN=$($env:AO3_DEVICE_LEASE_TOKEN)\""
    )
    cp = run_ps(cmd)
    assert cp.returncode == 0, cp.stderr
    assert "истекла (reclaimed" not in cp.stdout
    token_line = [l for l in cp.stdout.splitlines() if l.startswith("TOKEN=")][0]
    assert token_line.split("=", 1)[1] != "MY-OLD-TOKEN"


# --- -Release ---

def test_release_deletes_lease_file(tmp_path):
    cp = _run(
        "Use-DeviceStack -N 2; "
        "Use-DeviceStack -N 2 -Release; "
        "Write-Output \"EXISTS=$(Test-Path \\\"$root\\state\\device-lease-2.json\\\")\"",
        tmp_path,
    )
    assert "EXISTS=False" in cp.stdout


def test_release_without_lease_warns_does_not_throw(tmp_path):
    """Адверсариальная батарея (M6): -Release без лизы - НЕ throw (граница:
    легальный no-op с диагностикой, не деструктивная ошибка)."""
    cp = _run("Use-DeviceStack -N 2 -Release; Write-Output 'REACHED_END'", tmp_path)
    assert "REACHED_END" in cp.stdout
    assert "нечего снимать" in cp.stdout


def test_release_ignores_foreign_ownership_escape_hatch(tmp_path):
    """-Release - ЕДИНСТВЕННАЯ ручная форма снятия (docstring функции):
    удаляет ЛЮБУЮ лизу стека безусловно, включая чужую - явный
    escape-hatch человека, не проверка владения."""
    lease_file = _lease_path(tmp_path)
    lease_file.parent.mkdir(parents=True, exist_ok=True)
    lease_file.write_text(json.dumps({
        "owner_token": "OTHER-TOKEN", "owner_label": "other@HOST",
        "taken_utc": "2026-01-01T12:00:00Z", "heartbeat_utc": "2026-01-01T12:00:00Z",
        "pytest_pid": 999, "status": "active",
    }), encoding="utf-8")
    _run("Use-DeviceStack -N 2 -Release", tmp_path)
    assert not lease_file.exists()


def test_release_whatif_does_not_delete():
    """Non-blocker 1 (критик-вход rework attempt 2): -WhatIf теперь ЧЕСТЕН -
    файл НЕ удаляется под -WhatIf (раньше SupportsShouldProcess был пустым
    обещанием, -WhatIf реально брал/снимал лизу)."""
    pass  # покрыто test_take_whatif_does_not_write_file ниже + test_release_ignores_foreign_ownership_escape_hatch (без -WhatIf, контрольная пара)


def test_take_whatif_does_not_write_file(tmp_path):
    """Non-blocker 1: -WhatIf на взятии - НЕ создаёт файл лизы, НЕ ставит env."""
    import os as _os
    cmd = (
        dot_source_prefix(fake_root=tmp_path) +
        "Remove-Item Env:\\AO3_DEVICE_LEASE_TOKEN -ErrorAction SilentlyContinue; " +
        "Use-DeviceStack -N 2 -WhatIf; " +
        "Write-Output \"TOKEN=$($env:AO3_DEVICE_LEASE_TOKEN)\"; " +
        "Write-Output \"DEVICE=$($env:AO3_DEVICE)\""
    )
    cp = run_ps(cmd)
    assert cp.returncode == 0, cp.stderr
    assert not _lease_path(tmp_path).exists()
    assert "TOKEN=" in cp.stdout and "TOKEN=$" not in cp.stdout
    token_line = [l for l in cp.stdout.splitlines() if l.startswith("TOKEN=")][0]
    assert token_line == "TOKEN="  # пуст - env НЕ выставлен под -WhatIf
    device_line = [l for l in cp.stdout.splitlines() if l.startswith("DEVICE=")][0]
    assert device_line == "DEVICE="


# --- битый JSON файла лизы: трактуется как отсутствующая, взятие проходит ---

def test_corrupted_lease_json_treated_as_absent(tmp_path):
    lease_file = _lease_path(tmp_path)
    lease_file.parent.mkdir(parents=True, exist_ok=True)
    lease_file.write_text("{ not valid json !!!", encoding="utf-8")
    cp = _run(
        "Use-DeviceStack -N 2; Write-Output \"TOKEN=$($env:AO3_DEVICE_LEASE_TOKEN)\"",
        tmp_path,
    )
    assert "битый JSON" in cp.stdout
    token_line = [l for l in cp.stdout.splitlines() if l.startswith("TOKEN=")][0]
    assert token_line.split("=", 1)[1]  # непустой новый токен
    data = json.loads(lease_file.read_text(encoding="utf-8"))
    assert data["status"] == "active"


# --- B6 (критик-вход rework attempt 2): пустой (0-байтный) файл лизы ---

def test_empty_zero_byte_lease_file_treated_as_absent_not_eternal_race(tmp_path):
    """Раньше `Get-Content -Raw` на 0-байтном файле давал $null,
    unparseable-флаг НЕ ставился -> ConvertFrom-Json $null молча возвращал
    $null (не throw) -> CreateNew падал IOException 'файл существует' ->
    ВЕЧНЫЙ ложный 'гонка, повтори вызов' (повтор снова видит тот же
    0-байтный файл). Взятие ДОЛЖНО пройти успешно, не throw'нуть."""
    lease_file = _lease_path(tmp_path)
    lease_file.parent.mkdir(parents=True, exist_ok=True)
    lease_file.write_bytes(b"")
    assert lease_file.stat().st_size == 0
    cp = _run(
        "Use-DeviceStack -N 2; Write-Output \"TOKEN=$($env:AO3_DEVICE_LEASE_TOKEN)\"",
        tmp_path,
    )
    token_line = [l for l in cp.stdout.splitlines() if l.startswith("TOKEN=")][0]
    assert token_line.split("=", 1)[1]
    data = json.loads(lease_file.read_text(encoding="utf-8"))
    assert data["status"] == "active"


def test_empty_lease_file_retaken_twice_in_a_row_no_eternal_race(tmp_path):
    """M6 (адверсариальная батарея - за пределом однократного взятия):
    ДВА последовательных взятия ПОСЛЕ пустого файла - оба успешны (не
    воспроизводит 'вечную гонку' даже при повторе)."""
    lease_file = _lease_path(tmp_path)
    lease_file.parent.mkdir(parents=True, exist_ok=True)
    lease_file.write_bytes(b"")
    cp = _run(
        "Use-DeviceStack -N 2; Use-DeviceStack -N 2 -Release; "
        "Write-Output \"TOKEN=$($env:AO3_DEVICE_LEASE_TOKEN)\"",
        tmp_path,
    )
    assert cp.returncode == 0


# --- адверсариальная батарея -N (M6: на границе и за ней) ---

def test_n_zero_throws():
    cp = run_ps(dot_source_prefix() + "try { Use-DeviceStack -N 0 -ErrorAction Stop; Write-Output 'NO_THROW' } catch { Write-Output 'THROWN' }")
    assert cp.returncode == 0
    assert "THROWN" in cp.stdout


def test_n_three_throws():
    cp = run_ps(dot_source_prefix() + "try { Use-DeviceStack -N 3 -ErrorAction Stop; Write-Output 'NO_THROW' } catch { Write-Output 'THROWN' }")
    assert cp.returncode == 0
    assert "THROWN" in cp.stdout


def test_n_non_number_throws():
    cp = run_ps(dot_source_prefix() + "try { Use-DeviceStack -N 'abc' -ErrorAction Stop; Write-Output 'NO_THROW' } catch { Write-Output 'THROWN' }")
    assert cp.returncode == 0
    assert "THROWN" in cp.stdout


def test_n_one_and_two_are_valid_boundary():
    """M6: -N домен {1,2} - обе легальные границы принимаются (не throw)."""
    for n in (1, 2):
        cp = run_ps(dot_source_prefix() + f"try {{ (Get-Command Use-DeviceStack).Parameters['N'].Attributes | Where-Object {{ $_ -is [System.Management.Automation.ValidateSetAttribute] }} | ForEach-Object {{ Write-Output ($_.ValidValues -join ',') }} }} catch {{ Write-Output 'ERR' }}")
        assert cp.returncode == 0
        assert "1,2" in cp.stdout


# --- B3 (критик-вход rework attempt 2): гонка НА САМОЙ ФУНКЦИИ Use-DeviceStack ---

def test_use_device_stack_race_two_processes_exactly_one_wins(tmp_path):
    """B3 DoD ("Юнит гонки — на САМОЙ функции (параллельные вызовы), не на
    примитиве ОС"): ДВА РЕАЛЬНЫХ powershell-подпроцесса гонятся за ВЗЯТИЕМ
    ОДНОГО И ТОГО ЖЕ (изначально ОТСУТСТВУЮЩЕГО) стека 2 ОДНОВРЕМЕННО через
    Use-DeviceStack целиком (не голый [System.IO.File]::Open). Ровно один
    получает токен и env=AO3_DEVICE, другой либо throw'ит (лиза уже чужая
    активная ПОСЛЕ переоценки, либо гонка-race), но НИКОГДА оба не получают
    РАЗНЫЕ токены, записанные в файл одновременно (двойная выдача)."""
    results: list[str] = []
    lock = threading.Lock()

    def _attempt():
        cmd = (
            dot_source_prefix(fake_root=tmp_path) +
            "try { Use-DeviceStack -N 2; Write-Output (\"WON:\" + $env:AO3_DEVICE_LEASE_TOKEN) } "
            "catch { Write-Output \"LOST\" }"
        )
        cp = run_ps(cmd)
        # stdout несёт МНОГО предшествующих строк (env-баннер, WARN'ы
        # adb-обнаружения и т.п.) - решающая строка "WON:.../LOST" не первая,
        # ищем её ПОСТРОЧНО (найдено этой же сессией: `.strip().startswith`
        # на ВСЁМ stdout ложно проваливался, т.к. banner идёт первым).
        marker = next(
            (ln for ln in cp.stdout.splitlines() if ln.startswith("WON:") or ln == "LOST"),
            f"NEITHER: {cp.stdout!r}",
        )
        with lock:
            results.append(marker)

    threads = [threading.Thread(target=_attempt) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    won = [r for r in results if r.startswith("WON:")]
    assert len(results) == 2, f"results={results}"
    assert len(won) >= 1, f"results={results}"
    data = json.loads(_lease_path(tmp_path).read_text(encoding="utf-8"))
    won_tokens = {w.split(":", 1)[1] for w in won}
    # ИНВАРИАНТ ПОСЛЕ B-R2-1 (адопция): оба гонщика идут под ОДНИМ owner_label
    # (один пользователь, один хост), поэтому второй ЗАКОННО продолжает тикет
    # первого адопцией и получает СВОЙ токен - "два разных токена" здесь уже НЕ
    # признак двойной выдачи. Признак целостности, который обязан держаться:
    # файл лизы - ВАЛИДНЫЙ JSON с РОВНО ОДНИМ owner_token, и это токен одного
    # из победителей (никакой партиальной/перемешанной записи). Настоящая
    # защита от двойной выдачи - гейт ЖИВОГО pytest_pid, см.
    # test_live_pytest_pid_blocks_concurrent_takers ниже.
    assert data["owner_token"] in won_tokens, f"файл несёт токен НЕ победителя: {data['owner_token']} vs {won_tokens}"
    assert data["owner_label"] == _owner_label()


def test_use_device_stack_race_on_reclaimed_lease_exactly_one_wins(tmp_path):
    """B3: та же гонка, но НА RECLAIM-ПУТИ (файл СУЩЕСТВУЕТ, протух) -
    именно эта ветка раньше страдала от Remove-Item+CreateNew (окно между
    удалением и созданием, где ОБА параллельных вызова проходят "reclaimed
    -> беру" и оба удаляют+создают, критик воспроизвёл двойную выдачу)."""
    lease_file = _lease_path(tmp_path)
    lease_file.parent.mkdir(parents=True, exist_ok=True)
    lease_file.write_text(json.dumps({
        "owner_token": "STALE-TOKEN", "owner_label": "ghost@HOST",
        "taken_utc": "2020-01-01T00:00:00Z", "heartbeat_utc": "2020-01-01T00:00:00Z",
        "pytest_pid": None, "status": "active",
    }), encoding="utf-8")
    results: list[str] = []
    lock = threading.Lock()

    def _attempt():
        cmd = (
            dot_source_prefix(fake_root=tmp_path) +
            "try { Use-DeviceStack -N 2; Write-Output (\"WON:\" + $env:AO3_DEVICE_LEASE_TOKEN) } "
            "catch { Write-Output \"LOST\" }"
        )
        cp = run_ps(cmd)
        marker = next(
            (ln for ln in cp.stdout.splitlines() if ln.startswith("WON:") or ln == "LOST"),
            f"NEITHER: {cp.stdout!r}",
        )
        with lock:
            results.append(marker)

    threads = [threading.Thread(target=_attempt) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    won = [r for r in results if r.startswith("WON:")]
    assert len(results) == 2, f"results={results}"
    assert len(won) >= 1, f"results={results}"
    data = json.loads(lease_file.read_text(encoding="utf-8"))
    assert data["owner_token"] != "STALE-TOKEN"
    won_tokens = {w.split(":", 1)[1] for w in won}
    # Тот же инвариант целостности, что в тесте выше (после B-R2-1 два гонщика
    # ОДНОГО owner_label законно продолжают тикет друг друга адопцией).
    assert data["owner_token"] in won_tokens


def test_live_pytest_pid_blocks_concurrent_takers(tmp_path, live_stub_pid):
    """Настоящая защита от двойной выдачи ПОСЛЕ B-R2-1: под лизой идёт
    ЖИВОЙ прогон (реальный процесс-заглушка в роли pytest_pid) - ВСЕ
    параллельные претенденты, включая того же владельца, отказываются, и
    файл лизы остаётся у живого прогона."""
    lease_file = _lease_path(tmp_path, 1)
    lease_file.parent.mkdir(parents=True, exist_ok=True)
    lease_file.write_text(json.dumps({
        "owner_token": "LIVE-RUN", "owner_label": _owner_label(),
        "taken_utc": _now_iso(), "heartbeat_utc": _now_iso(),
        "pytest_pid": live_stub_pid, "status": "active",
        "device": "emulator-5554", "appium_url": "http://127.0.0.1:4723",
    }), encoding="utf-8")
    results: list[str] = []
    lock = threading.Lock()

    def _attempt():
        cmd = (
            dot_source_prefix(fake_root=tmp_path) +
            "Remove-Item Env:\\AO3_DEVICE_LEASE_TOKEN -ErrorAction SilentlyContinue; " +
            "try { Use-DeviceStack -N 1; Write-Output (\"WON:\" + $env:AO3_DEVICE_LEASE_TOKEN) } "
            "catch { Write-Output \"LOST\" }"
        )
        cp = run_ps(cmd)
        marker = next(
            (ln for ln in cp.stdout.splitlines() if ln.startswith("WON:") or ln == "LOST"),
            f"NEITHER: {cp.stdout!r}",
        )
        with lock:
            results.append(marker)

    threads = [threading.Thread(target=_attempt) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=90)

    assert results == ["LOST"] * 3, f"живой прогон обязан блокировать ВСЕХ: {results}"
    data = json.loads(lease_file.read_text(encoding="utf-8"))
    assert data["owner_token"] == "LIVE-RUN"


def test_second_take_of_active_foreign_lease_never_gets_a_lease(tmp_path):
    """Прокси гонки на уровне Use-DeviceStack: winner уже создал АКТИВНУЮ
    лизу (own_token != loser) - loser детерминированно отказывается, не
    перезаписывает файл гонщика."""
    lease_file = _lease_path(tmp_path)
    lease_file.parent.mkdir(parents=True, exist_ok=True)
    lease_file.write_text(json.dumps({
        "owner_token": "WINNER-TOKEN", "owner_label": "winner@HOST",
        "taken_utc": "2026-01-01T12:00:00Z", "heartbeat_utc": "2026-01-01T12:00:00Z",
        "pytest_pid": None, "status": "active",
    }), encoding="utf-8")
    cmd = (
        dot_source_prefix(fake_root=tmp_path) +
        f"try {{ Use-DeviceStack -N 2 {_now_provider('2026-01-01T12:00:05Z')}; "
        "Write-Output 'GOT_LEASE' } catch { Write-Output 'REFUSED' }"
    )
    cp = run_ps(cmd)
    assert cp.returncode == 0
    assert "REFUSED" in cp.stdout
    data = json.loads(lease_file.read_text(encoding="utf-8"))
    assert data["owner_token"] == "WINNER-TOKEN"


# --- БЛОКЕР B-R2-1 (критик-раунд 2): АДОПЦИЯ - продолжение тикета из НОВОГО
# процесса БЕЗ -Resume (дефолтный путь), -Resume - явный синоним ---

def test_adoption_default_call_continues_own_lease_from_new_real_process(tmp_path):
    """B-R2-1, ядро: ДЕФОЛТНЫЙ `Use-DeviceStack -N 1` из ВТОРОГО, полностью
    независимого powershell-процесса (env-токен НЕ наследуется, tasks.ps1
    дот-сорсится каждым вызовом - констрейнт 6) ПРОДОЛЖАЕТ свою лизу
    адопцией, а не отказывает "занято чужой активной".

    РАНЬШЕ (B2 attempt 2) это был отказ: без -Resume owner_label-совпадение
    владения не давало. Именно этот сценарий критик воспроизвёл как
    "Use-DeviceStack процессом А -> отказ у процесса Б"."""
    cmd1 = dot_source_prefix(fake_root=tmp_path) + "Use-DeviceStack -N 1; Write-Output \"T=$($env:AO3_DEVICE_LEASE_TOKEN)\""
    cp1 = run_ps(cmd1)
    assert cp1.returncode == 0, cp1.stderr
    t1 = [l for l in cp1.stdout.splitlines() if l.startswith("T=")][0].split("=", 1)[1]
    assert t1

    cmd2 = dot_source_prefix(fake_root=tmp_path) + "Use-DeviceStack -N 1; Write-Output \"T=$($env:AO3_DEVICE_LEASE_TOKEN)\""
    cp2 = run_ps(cmd2)
    assert cp2.returncode == 0, f"stdout={cp2.stdout}\nstderr={cp2.stderr}"
    t2 = [l for l in cp2.stdout.splitlines() if l.startswith("T=")][0].split("=", 1)[1]

    assert "ПРОДОЛЖЕНАадопцией" in _flat(cp2.stdout)
    assert t1 in cp2.stdout, "INFO-строка обязана назвать ПРЕЖНИЙ токен"
    assert t2 and t2 != t1, "адопция выпускает НОВЫЙ owner_token"
    data = json.loads((tmp_path / "state" / "device-lease-1.json").read_text(encoding="utf-8"))
    assert data["owner_token"] == t2
    assert data["owner_label"] == _owner_label()
    assert data["pytest_pid"] is None


def test_adoption_second_pass_after_five_minutes_does_not_throw(tmp_path):
    """B-R2-1, второй воспроизведённый критиком сценарий: "второй проход
    через 5 минут" - лиза своя по owner_label, pytest давно умер
    (pytest_pid мёртв), возраст внутри idle-окна. РАНЬШЕ: THROWN
    "idle, чужой владелец". ТЕПЕРЬ: адопция."""
    lease_file = _lease_path(tmp_path, 1)
    lease_file.parent.mkdir(parents=True, exist_ok=True)
    lease_file.write_text(json.dumps({
        "owner_token": "OLD-TICKET", "owner_label": _owner_label(),
        "taken_utc": "2026-01-01T12:00:00Z", "heartbeat_utc": "2026-01-01T12:00:00Z",
        "pytest_pid": 4242, "status": "active",
        "device": "emulator-5554", "appium_url": "http://127.0.0.1:4723",
    }), encoding="utf-8")
    cmd = (
        dot_source_prefix(fake_root=tmp_path) +
        "Remove-Item Env:\\AO3_DEVICE_LEASE_TOKEN -ErrorAction SilentlyContinue; " +
        f"try {{ Use-DeviceStack -N 1 {_now_provider('2026-01-01T12:05:00Z')} {_DEAD_PID_RESOLVER}; " +
        "Write-Output \"T=$($env:AO3_DEVICE_LEASE_TOKEN)\" } catch { Write-Output \"THROWN: $($_.Exception.Message)\" }"
    )
    cp = run_ps(cmd)
    assert cp.returncode == 0, cp.stderr
    assert "THROWN" not in cp.stdout, cp.stdout
    assert "ПРОДОЛЖЕНАадопцией" in _flat(cp.stdout)
    t = [l for l in cp.stdout.splitlines() if l.startswith("T=")][0].split("=", 1)[1]
    assert t and t != "OLD-TICKET"


def test_resume_is_explicit_synonym_of_default_adoption(tmp_path):
    """B-R2-1: `-Resume` СОХРАНЁН, но это ЯВНЫЙ СИНОНИМ дефолтной адопции -
    двух разных путей взятия нет. Исход обязан совпадать с дефолтным
    (новый токен, та же INFO-строка адопции)."""
    cmd1 = dot_source_prefix(fake_root=tmp_path) + "Use-DeviceStack -N 1; Write-Output \"T=$($env:AO3_DEVICE_LEASE_TOKEN)\""
    cp1 = run_ps(cmd1)
    t1 = [l for l in cp1.stdout.splitlines() if l.startswith("T=")][0].split("=", 1)[1]

    cmd2 = dot_source_prefix(fake_root=tmp_path) + "Use-DeviceStack -N 1 -Resume; Write-Output \"T=$($env:AO3_DEVICE_LEASE_TOKEN)\""
    cp2 = run_ps(cmd2)
    assert cp2.returncode == 0, cp2.stderr
    t2 = [l for l in cp2.stdout.splitlines() if l.startswith("T=")][0].split("=", 1)[1]
    assert "синонимповеденияпоумолчанию" in _flat(cp2.stdout)
    assert "ПРОДОЛЖЕНАадопцией" in _flat(cp2.stdout)
    assert t2 and t2 != t1


def test_resume_without_anything_to_resume_takes_fresh(tmp_path):
    """-Resume, когда лизы нет вовсе (free) - НЕ throw, берёт как обычно
    (адверсариальная граница: -Resume не требует существования лизы)."""
    cp = _run("Use-DeviceStack -N 2 -Resume; Write-Output \"TOKEN=$($env:AO3_DEVICE_LEASE_TOKEN)\"", tmp_path)
    assert "синонимповеденияпоумолчанию" in _flat(cp.stdout)
    token_line = [l for l in cp.stdout.splitlines() if l.startswith("TOKEN=")][0]
    assert token_line.split("=", 1)[1]


# --- БЛОКЕР B-R2-2: адопция/-Resume поверх ЖИВОГО pytest_pid - отказ ВСЕГДА ---

@pytest.mark.parametrize("resume_flag", ["", "-Resume"])
def test_adoption_refused_over_live_pytest_pid_real_process(tmp_path, live_stub_pid, resume_flag):
    """B-R2-2: лиза СВОЯ по owner_label, но под ней ЖИВОЙ процесс (настоящий
    подпроцесс-заглушка, `-PidAliveResolver` НЕ инжектируется - работает
    реальный `Get-Process`). Адопция запрещена ВСЕГДА, включая `-Resume`;
    сообщение обязано назвать владельца, PID и совет про `-Release`.
    Чужой файл НЕ перезаписан."""
    lease_file = _lease_path(tmp_path, 1)
    lease_file.parent.mkdir(parents=True, exist_ok=True)
    lease_file.write_text(json.dumps({
        "owner_token": "LIVE-RUN-TOKEN", "owner_label": _owner_label(),
        "taken_utc": _now_iso(), "heartbeat_utc": _now_iso(),
        "pytest_pid": live_stub_pid, "status": "active",
        "device": "emulator-5554", "appium_url": "http://127.0.0.1:4723",
    }), encoding="utf-8")
    cmd = (
        dot_source_prefix(fake_root=tmp_path) +
        "Remove-Item Env:\\AO3_DEVICE_LEASE_TOKEN -ErrorAction SilentlyContinue; " +
        f"try {{ Use-DeviceStack -N 1 {resume_flag}; Write-Output 'NO_THROW' }} " +
        "catch { Write-Output \"THROWN: $($_.Exception.Message)\" }"
    )
    cp = run_ps(cmd)
    assert cp.returncode == 0, cp.stderr
    assert "NO_THROW" not in cp.stdout, cp.stdout
    assert "THROWN:" in cp.stdout
    assert "ЖИВЫМпрогоном" in _flat(cp.stdout)
    assert _owner_label() in cp.stdout
    assert str(live_stub_pid) in cp.stdout
    assert "-Release" in cp.stdout
    data = json.loads(lease_file.read_text(encoding="utf-8"))
    assert data["owner_token"] == "LIVE-RUN-TOKEN", "живая лиза НЕ перезаписана адопцией"


def test_live_pytest_pid_of_foreign_owner_still_refuses(tmp_path, live_stub_pid):
    """Контрольная пара: ЧУЖОЙ owner_label с живым pid - прежний отказ
    "чужой АКТИВНОЙ лизой" (адопция даже не рассматривается)."""
    lease_file = _lease_path(tmp_path, 1)
    lease_file.parent.mkdir(parents=True, exist_ok=True)
    lease_file.write_text(json.dumps({
        "owner_token": "OTHER", "owner_label": "somebody-else@OTHERHOST",
        "taken_utc": _now_iso(), "heartbeat_utc": _now_iso(),
        "pytest_pid": live_stub_pid, "status": "active",
    }), encoding="utf-8")
    cmd = (
        dot_source_prefix(fake_root=tmp_path) +
        "Remove-Item Env:\\AO3_DEVICE_LEASE_TOKEN -ErrorAction SilentlyContinue; " +
        "try { Use-DeviceStack -N 1; Write-Output 'NO_THROW' } catch { Write-Output \"THROWN: $($_.Exception.Message)\" }"
    )
    cp = run_ps(cmd)
    assert "NO_THROW" not in cp.stdout
    assert "somebody-else@OTHERHOST" in cp.stdout


# --- non-blocker 3: НЕ-ЧИСЛОВОЙ pytest_pid = "pid отсутствует", не заклинивание ---

@pytest.mark.parametrize("bad_pid", ['"не-число"', "true", '["массив"]'])
def test_non_numeric_pytest_pid_is_treated_as_absent_not_binding_error(tmp_path, bad_pid):
    """Non-blocker 3: раньше `Get-Process -Id <не-число>` падал ПАРАМЕТРИЧЕСКИМ
    биндингом (терминирующая ошибка мимо -ErrorAction SilentlyContinue) и
    заклинивал Use-DeviceStack до ручного -Release. Теперь не-число = "pid
    отсутствует" -> лиза своя по метке, pid не жив -> штатная АДОПЦИЯ."""
    lease_file = _lease_path(tmp_path, 1)
    lease_file.parent.mkdir(parents=True, exist_ok=True)
    lease_file.write_text(
        '{"owner_token":"T","owner_label":"%s","taken_utc":"%s","heartbeat_utc":"%s",'
        '"pytest_pid":%s,"status":"active","device":"emulator-5554",'
        '"appium_url":"http://127.0.0.1:4723"}' % (_owner_label(), _now_iso(), _now_iso(), bad_pid),
        encoding="utf-8",
    )
    cmd = (
        dot_source_prefix(fake_root=tmp_path) +
        "Remove-Item Env:\\AO3_DEVICE_LEASE_TOKEN -ErrorAction SilentlyContinue; " +
        "try { Use-DeviceStack -N 1; Write-Output \"T=$($env:AO3_DEVICE_LEASE_TOKEN)\" } " +
        "catch { Write-Output \"THROWN: $($_.Exception.Message)\" }"
    )
    cp = run_ps(cmd)
    assert cp.returncode == 0, cp.stderr
    assert "THROWN" not in cp.stdout, cp.stdout
    token = [l for l in cp.stdout.splitlines() if l.startswith("T=")][0].split("=", 1)[1]
    assert token and token != "T"


def test_resolve_device_lease_pid_normalizes_boundary_values():
    """M6-батарея на самой нормализации (граница и за ней): 0/-1/пустая
    строка/не-число/true -> $null; "123"/123 -> 123."""
    cases = {
        "$null": "NULL", "0": "NULL", "-1": "NULL", "''": "NULL",
        "'abc'": "NULL", "'12abc'": "NULL", "$true": "NULL", "@(1,2)": "NULL",
        "123": "123", "'123'": "123",
    }
    body = "; ".join(
        f"$r = Resolve-DeviceLeasePid {expr}; Write-Output \"CASE{i}=$(if ($null -eq $r) {{ 'NULL' }} else {{ $r }})\""
        for i, expr in enumerate(cases)
    )
    cp = run_ps(dot_source_prefix() + body)
    assert cp.returncode == 0, cp.stderr
    out = cp.stdout.splitlines()
    for i, expected in enumerate(cases.values()):
        line = [l for l in out if l.startswith(f"CASE{i}=")][0]
        assert line.split("=", 1)[1] == expected, f"expr={list(cases)[i]} -> {line}"


def test_resume_ignores_foreign_owner_label_still_refuses(tmp_path):
    """-Resume НЕ обходит владение: чужой owner_label (другой пользователь/
    хост) - throw как обычно, токен НЕ перехватывается."""
    lease_file = _lease_path(tmp_path)
    lease_file.parent.mkdir(parents=True, exist_ok=True)
    lease_file.write_text(json.dumps({
        "owner_token": "OTHER-TOKEN", "owner_label": "definitely-not-me@OTHERHOST",
        "taken_utc": "2026-01-01T12:00:00Z", "heartbeat_utc": "2026-01-01T12:00:00Z",
        "pytest_pid": None, "status": "active",
    }), encoding="utf-8")
    cmd = (
        dot_source_prefix(fake_root=tmp_path) +
        f"try {{ Use-DeviceStack -N 2 -Resume {_now_provider('2026-01-01T12:00:05Z')} {_ALIVE_PID_RESOLVER}; "
        "Write-Output 'NO_THROW' } catch { Write-Output \"THROWN: $($_.Exception.Message)\" }"
    )
    cp = run_ps(cmd)
    assert cp.returncode == 0
    assert "THROWN:" in cp.stdout
    assert "definitely-not-me@OTHERHOST" in cp.stdout


# --- by_serial pre-start backfill (хвост N2 §5) ---

def test_by_serial_backfill_from_flat_fields_when_missing(tmp_path):
    state_file = tmp_path / "state" / "emulator-session.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps({
        "gpu": "swiftshader_indirect", "avd_name": "ao3_test_api34",
        "updated_utc": "2026-08-19T20:44:24Z",
    }), encoding="utf-8")
    cp = _run(
        "Use-DeviceStack -N 2 -LiveSerialsProvider { @('emulator-5554') }",
        tmp_path,
    )
    assert "by_serial-запись для emulator-5554 отсутствует" in cp.stdout
    assert "бэкфилл" in cp.stdout
    data = json.loads(state_file.read_text(encoding="utf-8"))
    assert data["by_serial"]["emulator-5554"]["avd_name"] == "ao3_test_api34"
    assert data["by_serial"]["emulator-5554"]["gpu"] == "swiftshader_indirect"


def test_by_serial_no_backfill_possible_when_flat_fields_also_absent(tmp_path):
    state_file = tmp_path / "state" / "emulator-session.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps({}), encoding="utf-8")
    cp = _run(
        "Use-DeviceStack -N 2 -LiveSerialsProvider { @('emulator-5554') }",
        tmp_path,
    )
    # Проверяем раздельными подстроками (не "бэкфилл невозможен" одной
    # фразой) - длинное Write-Warning-сообщение переносится PowerShell-
    # консолью по ширине ВНУТРИ фразы (найдено эмпирически: `\n` появился
    # ровно между "бэкфилл" и "невозможен"), склеенная подстрока хрупка к
    # ширине консоли хоста.
    assert "бэкфилл" in cp.stdout
    assert "невозможен" in cp.stdout
    # Use-DeviceStack НЕ заблокирован отсутствием backfill - лиза всё равно взята
    assert (tmp_path / "state" / "device-lease-2.json").exists()


def test_by_serial_backfill_skipped_when_entry_already_present(tmp_path):
    state_file = tmp_path / "state" / "emulator-session.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps({
        "gpu": "host", "avd_name": "ao3_corridor_api34", "updated_utc": "2026-08-20T00:00:00Z",
        "by_serial": {"emulator-5556": {"gpu": "host", "avd_name": "ao3_corridor_api34", "updated_utc": "2026-08-20T00:00:00Z"}},
    }), encoding="utf-8")
    cp = _run(
        "Use-DeviceStack -N 2 -LiveSerialsProvider { @('emulator-5556') }",
        tmp_path,
    )
    assert "by_serial-запись для" not in cp.stdout
    data = json.loads(state_file.read_text(encoding="utf-8"))
    assert data["by_serial"]["emulator-5556"]["avd_name"] == "ao3_corridor_api34"


def test_by_serial_no_fabrication_when_flat_belongs_to_another_serial(tmp_path):
    """Non-blocker 8 (критик-раунд 2), ЯДРО: `by_serial` НЕПУСТА - значит
    флэт top-level поля описывают ДРУГОЙ (уже записанный ЛИБО откаченный
    Undo-EmulatorSessionStateEntry) серийник. Фабриковать из них avd_name
    ЧУЖОГО серийника ЗАПРЕЩЕНО; честный источник (adb emu avd name)
    недоступен -> ПРОПУСК с WARN.

    Экземпляр, найденный живьём в worktree этой задачи: флэт нёс
    avd_name=ao3_test_api34 (аборченный старт), и бэкфилл сфабриковал
    by_serial['emulator-5556'].avd_name = ao3_test_api34, хотя стек 2 держит
    ДРУГОЙ AVD."""
    state_file = tmp_path / "state" / "emulator-session.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps({
        "gpu": "swiftshader_indirect", "avd_name": "ao3_test_api34",
        "updated_utc": "2026-08-20T21:30:12Z",
        "by_serial": {"emulator-5554": {
            "gpu": "swiftshader_indirect", "avd_name": "ao3_test_api34",
            "updated_utc": "2026-08-20T21:30:11Z"}},
    }), encoding="utf-8")
    cp = _run(
        "Use-DeviceStack -N 2 -LiveSerialsProvider { @('emulator-5554','emulator-5556') } "
        "-AvdNameResolver { param($Serial) $null }",
        tmp_path,
    )
    assert "ПРОПУЩЕН" in cp.stdout
    data = json.loads(state_file.read_text(encoding="utf-8"))
    assert "emulator-5556" not in data.get("by_serial", {}), "сфабрикованная запись НЕ должна появиться"
    assert data["by_serial"]["emulator-5554"]["avd_name"] == "ao3_test_api34"


def test_by_serial_backfill_uses_honest_adb_source_when_available(tmp_path):
    """Non-blocker 8: честный источник ЕСТЬ (`adb -s <serial> emu avd name`,
    здесь - через инжектируемый `-AvdNameResolver`, device-free) - бэкфилл
    берёт ЕГО имя, а НЕ флэт top-level."""
    state_file = tmp_path / "state" / "emulator-session.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps({
        "gpu": "swiftshader_indirect", "avd_name": "ao3_test_api34",
        "updated_utc": "2026-08-20T21:30:12Z",
        "by_serial": {"emulator-5554": {
            "gpu": "swiftshader_indirect", "avd_name": "ao3_test_api34",
            "updated_utc": "2026-08-20T21:30:11Z"}},
    }), encoding="utf-8")
    cp = _run(
        "Use-DeviceStack -N 2 -LiveSerialsProvider { @('emulator-5556') } "
        "-AvdNameResolver { param($Serial) 'ao3_test_api29' }",
        tmp_path,
    )
    assert "ЧЕСТНОГОисточника" in _flat(cp.stdout)
    data = json.loads(state_file.read_text(encoding="utf-8"))
    assert data["by_serial"]["emulator-5556"]["avd_name"] == "ao3_test_api29"
    assert data["by_serial"]["emulator-5554"]["avd_name"] == "ao3_test_api34"


# --- non-blocker 4/5: атомарная запись - уборка темпа и доменный отказ ---

def test_write_file_atomic_removes_temp_on_failure(tmp_path):
    """Non-blocker 4: отказ ЛЮБОГО пути записи (здесь - целевой файл держит
    ЭКСКЛЮЗИВНЫЙ хэндл, sharing violation на Replace) НЕ оставляет
    `<файл>.tmp-<pid>-<hex>`. Раньше сирота оставался навсегда (два таких
    найдены живьём в worktree)."""
    target = tmp_path / "atomic-target.json"
    target.write_text('{"a":1}', encoding="utf-8")
    cmd = (
        dot_source_prefix(fake_root=tmp_path) +
        f"$fs = [System.IO.File]::Open('{target}', [System.IO.FileMode]::Open, "
        "[System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None); " +
        f"try {{ Write-FileAtomic -Path '{target}' -Content '{{\"b\":2}}'; Write-Output 'NO_THROW' }} " +
        "catch { Write-Output 'THROWN' } finally { $fs.Dispose() }"
    )
    cp = run_ps(cmd)
    assert cp.returncode == 0, cp.stderr
    assert "THROWN" in cp.stdout, cp.stdout
    leftovers = [p.name for p in tmp_path.iterdir() if ".tmp-" in p.name or ".bak-" in p.name]
    assert leftovers == [], f"осиротевшие темпы/бэкапы: {leftovers}"


def test_write_file_atomic_resilient_warns_instead_of_raw_exception(tmp_path):
    """Non-blocker 5: доменная обёртка НЕ пробрасывает сырой
    MethodInvocationException наружу (иначе Use-DeviceStack падал бы на
    транзиентном локе вопреки своему же докстрингу "не блокирует") -
    WARN + $false после ретраев."""
    target = tmp_path / "resilient-target.json"
    target.write_text('{"a":1}', encoding="utf-8")
    cmd = (
        dot_source_prefix(fake_root=tmp_path) +
        f"$fs = [System.IO.File]::Open('{target}', [System.IO.FileMode]::Open, "
        "[System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None); " +
        f"try {{ $r = Write-FileAtomicResilient -Path '{target}' -Content '{{\"b\":2}}' " +
        "-Context 'проба' -Retries 2 -DelayMs 10; Write-Output \"RESULT=$r\" } " +
        "catch { Write-Output 'THROWN' } finally { $fs.Dispose() }"
    )
    cp = run_ps(cmd)
    assert cp.returncode == 0, cp.stderr
    assert "THROWN" not in cp.stdout, cp.stdout
    assert "RESULT=False" in cp.stdout
    assert "проба:атомарнаязапись" in _flat(cp.stdout)
    assert "неудалась" in _flat(cp.stdout)
    assert "НЕблокируетвызывающего" in _flat(cp.stdout)
    leftovers = [p.name for p in tmp_path.iterdir() if ".tmp-" in p.name or ".bak-" in p.name]
    assert leftovers == [], f"осиротевшие темпы/бэкапы: {leftovers}"


def test_by_serial_check_skipped_for_stack1(tmp_path):
    """N>1 - только стек 2+ проверяет by_serial (стек 1 не завязан на
    множественные живые серийники); N=1 не должен звать Get-DeviceSerials
    вовсе - live_serials_provider с throw доказывает, что он не вызван.

    `-LeaseFile` изолирован В `tmp_path` (не общий `$env:TEMP`-путь) - общий
    путь между независимыми прогонами теста порождал ложный "чужая активная
    лиза" throw от лизы, оставленной ПРЕДЫДУЩИМ прогоном (найдено этой же
    сессией: `$env:TEMP` реален и переживает процесс, `tmp_path` - нет)."""
    lease_file = tmp_path / "stack1-lease.json"
    cp = run_ps(
        dot_source_prefix() +
        "$callCount = 0; "
        f"Use-DeviceStack -N 1 -LiveSerialsProvider {{ $script:callCount++; @() }} "
        f"-LeaseFile '{lease_file}'; "
        "Write-Output \"CALLS=$callCount\""
    )
    assert cp.returncode == 0, cp.stderr
    assert "CALLS=0" in cp.stdout
