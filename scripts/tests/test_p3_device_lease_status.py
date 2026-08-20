"""spec-p3-second-emulator N3: `Get-DeviceLeaseStatus` (машинная лиза стека) -
ЧИСТАЯ функция статуса {free|active|idle|reclaimed}, device-free, без реального
времени/файлов/процессов (инжектируемые `-Now`/`-PidAliveResolver`).

Реальный PowerShell (`powershell`, дот-сорсит WORKTREE-копию `scripts/tasks.ps1`,
паттерн `_ps1_helpers.py`, тот же приём, что `test_p3_stop_node_processes.py`).
Окна GRACE/IDLE/TTL передаются ЯВНО в каждом вызове (не полагаемся на
script-level дефолты `$_DEVICE_LEASE_*_SECONDS`) - тесты детерминированы
независимо от того, изменятся ли когда-нибудь оценочные (F-30) константы;
отдельный тест ниже сверяет ФАКТИЧЕСКИЕ дефолтные значения с задокументированной
оценкой плана (600/1800/14400 = 10 мин/30 мин/4 ч).

Найдено ЭТОЙ сессией эмпирически (не предположение, класс M6/F-30-калибровка):
Windows PowerShell 5.1 (`powershell.exe`, канонический интерпретатор репо)
держит ISO8601-timestamp из `ConvertFrom-Json` СТРОКОЙ; PowerShell 7+ (`pwsh`)
автоматически десериализует такую строку в `[datetime]`. Функция ветвится по
фактическому типу (`$lastRaw -is [datetime]`) - тесты ниже конструируют лизу
И строкой (canonical, PS 5.1 путь), И явным `[datetime]`-объектом (pwsh-путь),
чтобы оба пути были покрыты одним и тем же набором проб.

B1 (критик-вход rework attempt 2 - ПЕРЕПИСАНО): статус ТЕПЕРЬ вычисляется по
живости `pytest_pid` (`-PidAliveResolver`, инжектируемый - НИКАКОЙ реальный
`Get-Process` в тестах не вызывается), поле `status` лизы больше НЕ читается
функцией вовсе - тесты ниже НЕ передают `status` в конструируемых лизах.
"""
from __future__ import annotations

from _ps1_helpers import dot_source_prefix, run_ps

_NOW = "2026-01-01T12:00:00.0000000Z"

_ALIVE = "-PidAliveResolver { param($ProcId) $true }"
_DEAD = "-PidAliveResolver { param($ProcId) $false }"


def _lease_cmd(*, heartbeat_offset_sec: float | None, taken_offset_sec: float = 0,
               pytest_pid=None, as_datetime: bool = False,
               heartbeat_literal: str | None = None) -> str:
    """Строит PS-выражение `$lease` со смещёнными от `_NOW` таймстампами.
    `heartbeat_offset_sec=None` - поле `heartbeat_utc` не выставляется вовсе
    (лиза без heartbeat, статус читается из `taken_utc`, как штампует
    Use-DeviceStack при взятии ДО первого create_driver).
    `heartbeat_literal` - буквальная PS-строка для heartbeat_utc (B7: битый
    heartbeat, не производная от `$now`)."""
    parts = []
    parts.append("$now = [datetime]::Parse('%s', [System.Globalization.CultureInfo]::InvariantCulture, [System.Globalization.DateTimeStyles]::RoundtripKind)" % _NOW)
    parts.append(f"$taken = $now.AddSeconds(-{taken_offset_sec})")
    pid_expr = "$null" if pytest_pid is None else str(pytest_pid)
    if heartbeat_literal is not None:
        hb_value = f"'{heartbeat_literal}'"
    elif heartbeat_offset_sec is None:
        hb_value = "$null"
    else:
        hb_expr = f"$now.AddSeconds(-{heartbeat_offset_sec})"
        hb_value = hb_expr if as_datetime else f"({hb_expr}).ToString('o')"
    parts.append(
        "$lease = [pscustomobject]@{ owner_token='TOK'; taken_utc=$taken.ToString('o'); "
        f"heartbeat_utc={hb_value}; pytest_pid={pid_expr}; status='active' }}"
    )
    return "\n".join(parts)


def _status(*, heartbeat_offset_sec, pytest_pid=None, as_datetime=False,
            grace=600, idle=1800, ttl=14400, pid_resolver: str = "",
            heartbeat_literal: str | None = None, taken_offset_sec: float = 0) -> str:
    cmd = (
        dot_source_prefix() +
        _lease_cmd(heartbeat_offset_sec=heartbeat_offset_sec, pytest_pid=pytest_pid,
                   as_datetime=as_datetime, heartbeat_literal=heartbeat_literal,
                   taken_offset_sec=taken_offset_sec) +
        f"\n$s = Get-DeviceLeaseStatus -Lease $lease -Now $now -GraceSeconds {grace} "
        f"-IdleSeconds {idle} -TtlSeconds {ttl} {pid_resolver}\nWrite-Output \"S=$s\""
    )
    cp = run_ps(cmd)
    assert cp.returncode == 0, f"stdout={cp.stdout}\nstderr={cp.stderr}"
    for line in cp.stdout.splitlines():
        if line.startswith("S="):
            return line[2:].strip()
    raise AssertionError(f"no S= line: {cp.stdout}")


def test_absent_lease_is_free():
    cmd = dot_source_prefix() + (
        "$now = Get-Date; $s = Get-DeviceLeaseStatus -Lease $null -Now $now; Write-Output \"S=$s\""
    )
    cp = run_ps(cmd)
    assert cp.returncode == 0
    assert "S=free" in cp.stdout


def test_missing_timestamp_is_free():
    cmd = dot_source_prefix() + (
        "$now = Get-Date; "
        "$lease = [pscustomobject]@{ owner_token='TOK'; taken_utc=$null; heartbeat_utc=$null; pytest_pid=$null; status=$null }; "
        "$s = Get-DeviceLeaseStatus -Lease $lease -Now $now; Write-Output \"S=$s\""
    )
    cp = run_ps(cmd)
    assert cp.returncode == 0
    assert "S=free" in cp.stdout


def test_both_timestamps_unparseable_is_free():
    cmd = dot_source_prefix() + (
        "$now = Get-Date; "
        "$lease = [pscustomobject]@{ owner_token='TOK'; taken_utc='not-a-date'; heartbeat_utc='also-not-a-date'; pytest_pid=$null; status=$null }; "
        "$s = Get-DeviceLeaseStatus -Lease $lease -Now $now; Write-Output \"S=$s\""
    )
    cp = run_ps(cmd)
    assert cp.returncode == 0
    assert "S=free" in cp.stdout


# --- B7 (критик-вход rework attempt 2): битый heartbeat, валидный taken - фолбэк, НЕ free ---

def test_corrupted_heartbeat_falls_back_to_valid_taken_utc():
    """Раньше PS смотрела на falsy heartbeat_utc ТОЛЬКО (не отказ парсинга) -
    неразбираемая-но-непустая строка ловилась в общий catch -> 'free', расходясь
    с Python (`_parse_lease_timestamp(hb) or _parse_lease_timestamp(taken)`).
    taken_utc свежий (5с назад), pid отсутствует - должно дать 'active' (грейс),
    НЕ 'free'."""
    assert _status(heartbeat_offset_sec=None, taken_offset_sec=5,
                   heartbeat_literal="not-a-valid-timestamp") == "active"


# --- ACTIVE (pid ЖИВ -> TTL-окно) ---

def test_active_pid_alive_within_ttl():
    assert _status(heartbeat_offset_sec=10, pytest_pid=12345, pid_resolver=_ALIVE) == "active"


def test_active_pid_alive_ttl_boundary_is_active():
    """M6: РОВНО на границе (age == TtlSeconds) - ещё active (age <= ttl)."""
    assert _status(heartbeat_offset_sec=14400, pytest_pid=12345, ttl=14400, pid_resolver=_ALIVE) == "active"


def test_pid_alive_beyond_ttl_falls_through_to_reclaimed():
    """M6: pid ЖИВ, но heartbeat не обновлялся дольше TTL - падает в
    idle/reclaimed по возрасту (TTL(4ч) > Idle(30мин) по построению - всегда
    попадает сразу в reclaimed, не в idle)."""
    assert _status(heartbeat_offset_sec=14400.001, pytest_pid=12345, ttl=14400, idle=1800, pid_resolver=_ALIVE) == "reclaimed"


# --- ACTIVE (pid ОТСУТСТВУЕТ -> Grace-окно, стартовое) ---

def test_active_no_pid_within_grace_is_active():
    assert _status(heartbeat_offset_sec=10) == "active"


def test_active_no_pid_grace_boundary_is_active():
    """M6: РОВНО на границе (age == GraceSeconds) - ещё active (age <= grace)."""
    assert _status(heartbeat_offset_sec=600, grace=600) == "active"


def test_no_pid_beyond_grace_is_idle_not_reclaimed():
    """B1-редизайн (ПОВЕДЕНИЕ ИЗМЕНИЛОСЬ): раньше "нет pid, за грейсом" ->
    reclaimed НАПРЯМУЮ. Теперь grace - короткое стартовое окно ВНУТРИ
    широкого idle-окна: за грейсом, но в пределах idle -> 'idle', НЕ
    'reclaimed' (план N3: "idle при отсутствующем pytest_pid")."""
    assert _status(heartbeat_offset_sec=600.001, grace=600, idle=1800) == "idle"


def test_no_pid_beyond_idle_is_reclaimed():
    assert _status(heartbeat_offset_sec=1800.001, grace=600, idle=1800) == "reclaimed"


# --- IDLE (pid МЁРТВ -> idle-окно от heartbeat_utc) ---

def test_dead_pid_within_idle_window_is_idle():
    assert _status(heartbeat_offset_sec=100, pytest_pid=12345, idle=1800, pid_resolver=_DEAD) == "idle"


def test_dead_pid_idle_boundary_is_idle():
    """M6: РОВНО на границе (age == IdleSeconds) - ещё idle (age <= idle)."""
    assert _status(heartbeat_offset_sec=1800, pytest_pid=12345, idle=1800, pid_resolver=_DEAD) == "idle"


def test_dead_pid_beyond_idle_window_is_reclaimed():
    """M6: idle-окно истекло - reclaimed."""
    assert _status(heartbeat_offset_sec=1800.001, pytest_pid=12345, idle=1800, pid_resolver=_DEAD) == "reclaimed"


# --- pwsh-путь (heartbeat_utc уже [datetime], не строка) ---

def test_active_status_with_datetime_typed_heartbeat_pwsh_path():
    """Найдено эмпирически (M6): pwsh 7+ авто-десериализует ISO8601 в
    [datetime] внутри ConvertFrom-Json - функция обязана распознать ЭТОТ
    тип напрямую, не только строку (иначе implicit ToString() теряет
    точность/Kind и даёт ложный возраст, живой инцидент этой сессии)."""
    assert _status(heartbeat_offset_sec=10, as_datetime=True) == "active"


def test_idle_status_with_datetime_typed_heartbeat_beyond_grace():
    assert _status(heartbeat_offset_sec=700, as_datetime=True, grace=600, idle=1800) == "idle"


# --- taken_utc используется, если heartbeat_utc не выставлен вовсе ---

def test_falls_back_to_taken_utc_when_no_heartbeat_yet():
    """Свежевзятая лиза (Use-DeviceStack только что создала файл) - ДО
    первого create_driver heartbeat_utc == taken_utc по построению
    (Use-DeviceStack пишет их равными), но функция обязана уметь читать
    ИМЕННО из taken_utc, если heartbeat_utc отсутствует вовсе (defensive)."""
    assert _status(heartbeat_offset_sec=None, taken_offset_sec=5) == "active"


# --- PidAliveResolver реально вызывается с ПРАВИЛЬНЫМ pid ---

def test_pid_alive_resolver_receives_correct_pid():
    cmd = (
        dot_source_prefix() +
        _lease_cmd(heartbeat_offset_sec=10, pytest_pid=98765) +
        "\n$seen = $null\n"
        "$s = Get-DeviceLeaseStatus -Lease $lease -Now $now -PidAliveResolver "
        "{ param($ProcId) $script:seen = $ProcId; $true }\n"
        "Write-Output \"SEEN=$seen\""
    )
    cp = run_ps(cmd)
    assert cp.returncode == 0
    assert "SEEN=98765" in cp.stdout


# --- дефолтные окна функции сверены с задокументированной оценкой плана ---

def test_default_windows_match_documented_estimate():
    """docs/tasks/p3-second-emulator.md N3: grace ~10 мин / idle ~30 мин /
    TTL 4 ч - ОЦЕНКА (F-30). Сверяем ФАКТИЧЕСКИЕ дефолты скрипта, не
    пересказ спеки."""
    cmd = dot_source_prefix() + (
        "Write-Output \"G=$_DEVICE_LEASE_GRACE_SECONDS I=$_DEVICE_LEASE_IDLE_SECONDS T=$_DEVICE_LEASE_TTL_SECONDS\""
    )
    cp = run_ps(cmd)
    assert cp.returncode == 0
    assert "G=600 I=1800 T=14400" in cp.stdout


# --- default PidAliveResolver зовёт Test-DeviceLeasePidAlive (реальный Get-Process) ---

def test_default_pid_alive_resolver_reports_dead_for_implausible_pid():
    """Без явного -PidAliveResolver - дефолт зовёт РЕАЛЬНЫЙ
    Test-DeviceLeasePidAlive/Get-Process. PID 999999999 практически
    гарантированно не существует на любом Windows-хосте (макс. PID
    Windows на порядки меньше) - детерминированный негативный контроль
    дефолтного пути (не polluting с реальным текущим процессом)."""
    assert _status(heartbeat_offset_sec=100, pytest_pid=999999999, idle=1800) == "idle"
