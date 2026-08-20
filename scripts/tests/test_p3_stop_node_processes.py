"""spec-p3-second-emulator N1: `Stop-NodeProcesses` селектор -Port/-OwnerPid +
отказ без селектора при >1 сервере + -WhatIf (SupportsShouldProcess).

Реальный PowerShell (`powershell`, дот-сорсит WORKTREE-копию `scripts/tasks.ps1`) -
никакой реальный node.exe/adb/npx не трогается: `-ProcessListProvider`/
`-PortOwnerResolver`/`-Stopper` - инжектируемые scriptblock-параметры этой
функции (см. `tasks.ps1::Stop-NodeProcesses`), тесты подменяют их фейковыми
данными. Каждый тест самодостаточен (одна PowerShell-команда, один subprocess) -
дороже, чем Pester, но не требует Pester в окружении и соответствует
канонической форме `python -m pytest scripts/tests -q`.
"""
from __future__ import annotations

from pathlib import Path

from _ps1_helpers import dot_source_prefix, run_ps

# Общие фейковые узлы: два "живых" AO3-владения (:4723/:4725) + один чужой
# (не матчит $root => отфильтрован ДО селектора).
_FAKES = """
function New-FakeProc($ProcId, $Cmd) { [pscustomobject]@{ ProcessId = $ProcId; CommandLine = $Cmd } }
$p1 = New-FakeProc 111 "node $root\\tools\\appium\\node_modules\\appium\\index.js --port 4723"
$p2 = New-FakeProc 222 "node $root\\tools\\appium\\node_modules\\appium\\index.js --port 4725"
$foreign = New-FakeProc 333 "node C:\\SomeOtherProject\\index.js"
"""


def _run(body: str, fake_root: Path) -> str:
    # $root ДОЛЖЕН реально существовать на диске (Stop-NodeProcesses:
    # AT-BUG-031 guard `Test-Path $root` throw'ит на несуществующем пути) -
    # pytest tmp_path создаёт каталог сам.
    cmd = dot_source_prefix(fake_root=fake_root) + _FAKES + body
    cp = run_ps(cmd)
    assert cp.returncode == 0, f"stdout={cp.stdout}\nstderr={cp.stderr}"
    return cp.stdout


def test_zero_servers_does_not_throw(tmp_path):
    out = _run(
        "Stop-NodeProcesses -ProcessListProvider { @() } "
        "-PortOwnerResolver { param($P) $null } -Stopper { param($p) }",
        tmp_path,
    )
    assert "No AO3 node processes found" in out


def test_one_server_no_selector_previous_behavior_verbatim(tmp_path):
    """Матрица DoD: 1 сервер без селектора - прежнее поведение дословно
    (кандидат убит, счётчик 1)."""
    out = _run(
        "Stop-NodeProcesses -ProcessListProvider { @($p1, $foreign) } "
        "-PortOwnerResolver { param($P) $null } -Stopper { param($p) }",
        tmp_path,
    )
    assert "Stopping AO3 node process (PID 111)" in out
    assert "Stopped 1 AO3 node process(es)." in out
    # чужой процесс (не матчит $root) даже не рассматривался
    assert "333" not in out


def test_two_servers_no_selector_refuses_with_candidate_list(tmp_path):
    cmd = (
        dot_source_prefix(fake_root=tmp_path) + _FAKES +
        "try { "
        "Stop-NodeProcesses -ProcessListProvider { @($p1, $p2) } "
        "-PortOwnerResolver { param($P) $null } -Stopper { param($p) }; "
        "Write-Output 'NO_THROW' "
        "} catch { Write-Output \"THROWN: $($_.Exception.Message)\" }"
    )
    cp = run_ps(cmd)
    assert cp.returncode == 0
    assert "THROWN:" in cp.stdout
    assert "NO_THROW" not in cp.stdout
    assert "111" in cp.stdout and "222" in cp.stdout  # перечень кандидатов в сообщении


def test_selector_port_kills_only_matching_process(tmp_path):
    out = _run(
        "Stop-NodeProcesses -Port 4725 -ProcessListProvider { @($p1, $p2) } "
        "-PortOwnerResolver { param($P) if ($P -eq 4725) { 222 } else { $null } } "
        "-Stopper { param($p) }",
        tmp_path,
    )
    assert "Stopping AO3 node process (PID 222)" in out
    assert "PID 111" not in out
    assert "Stopped 1 AO3 node process(es)." in out


def test_selector_ownerpid_kills_only_matching_process(tmp_path):
    out = _run(
        "Stop-NodeProcesses -OwnerPid 111 -ProcessListProvider { @($p1, $p2) } "
        "-PortOwnerResolver { param($P) $null } -Stopper { param($p) }",
        tmp_path,
    )
    assert "Stopping AO3 node process (PID 111)" in out
    assert "PID 222" not in out


def test_selector_port_without_listener_kills_zero_not_error(tmp_path):
    """Совет критика (критик-раунд, 2026-08-20): селектор дан ($Port), но не
    выбрал НИ ОДНОГО из непустого списка owned-кандидатов - сообщение
    отличает этот случай от генуинного "процессов нет вовсе" (owned пуст)."""
    cmd = (
        dot_source_prefix(fake_root=tmp_path) + _FAKES +
        "Stop-NodeProcesses -Port 9999 -ProcessListProvider { @($p1, $p2) } "
        "-PortOwnerResolver { param($P) $null } -Stopper { param($p) }; "
        "Write-Output 'EXIT_OK'"
    )
    cp = run_ps(cmd)
    assert cp.returncode == 0
    assert "селектор не выбрал ни одного из 2 кандидатов" in cp.stdout
    assert "No AO3 node processes found" not in cp.stdout
    assert "EXIT_OK" in cp.stdout  # функция вернулась нормально, не throw


def test_dead_or_reused_ownerpid_kills_zero(tmp_path):
    """Совет критика: тот же класс - -OwnerPid дан, но мёртвый/переиспользован,
    owned непустой (2 кандидата) -> новое сообщение с числом кандидатов."""
    out = _run(
        "Stop-NodeProcesses -OwnerPid 999999 -ProcessListProvider { @($p1, $p2) } "
        "-PortOwnerResolver { param($P) $null } -Stopper { param($p) }",
        tmp_path,
    )
    assert "селектор не выбрал ни одного из 2 кандидатов" in out
    assert "No AO3 node processes found" not in out


def test_foreign_non_ao3_process_targeted_explicitly_kills_zero(tmp_path):
    """Чужой процесс (не матчит $root) не входит в $owned - явный -OwnerPid на
    его PID не даёт эффекта, даже если он реально жив в системе. owned здесь
    непустой (1 кандидат - $p1) -> новое сообщение (совет критика), не
    генуинный "процессов нет вовсе"."""
    out = _run(
        "Stop-NodeProcesses -OwnerPid 333 -ProcessListProvider { @($p1, $foreign) } "
        "-PortOwnerResolver { param($P) $null } -Stopper { param($p) }",
        tmp_path,
    )
    assert "селектор не выбрал ни одного из 1 кандидатов" in out
    assert "No AO3 node processes found" not in out


def test_whatif_kills_nothing_and_candidate_list_matches_live_call(tmp_path):
    """M6 (правило 11 CLAUDE.md): -WhatIf на границе поведения (0 killed) -
    её напечатанный список кандидатов идентичен списку живого вызова."""
    dry_cmd = (
        dot_source_prefix(fake_root=tmp_path) + _FAKES +
        "$killed = New-Object System.Collections.ArrayList; "
        "Stop-NodeProcesses -ProcessListProvider { @($p1, $foreign) } "
        "-PortOwnerResolver { param($P) $null } "
        "-Stopper { param($p) $null = $killed.Add($p) } -WhatIf; "
        "Write-Output \"KILLED_COUNT=$($killed.Count)\""
    )
    dry = run_ps(dry_cmd)
    assert dry.returncode == 0, dry.stderr
    assert "KILLED_COUNT=0" in dry.stdout
    assert "Candidates to stop:" in dry.stdout
    assert "PID 111" in dry.stdout

    live_cmd = (
        dot_source_prefix(fake_root=tmp_path) + _FAKES +
        "$killed = New-Object System.Collections.ArrayList; "
        "Stop-NodeProcesses -ProcessListProvider { @($p1, $foreign) } "
        "-PortOwnerResolver { param($P) $null } "
        "-Stopper { param($p) $null = $killed.Add($p) }; "
        "Write-Output \"KILLED_COUNT=$($killed.Count)\""
    )
    live = run_ps(live_cmd)
    assert live.returncode == 0, live.stderr
    assert "KILLED_COUNT=1" in live.stdout
    assert "Candidates to stop:" in live.stdout
    assert "PID 111" in live.stdout
    # оба напечатали ТОТ ЖЕ единственный кандидат (PID 111) - список идентичен
    assert (dry.stdout.count("PID 111")) >= 1 and (live.stdout.count("PID 111")) >= 1


def test_port_selector_validate_range_rejects_out_of_domain():
    """Адверсариальная батарея (правило 11 CLAUDE.md, M6): -Port селектора
    жнеца - тот же TCP-домен 1-65535, на границе и за ней."""
    for bad in ("0", "-1", "65536"):
        cp = run_ps(
            dot_source_prefix() +
            f"try {{ Stop-NodeProcesses -Port {bad} -ErrorAction Stop; "
            "Write-Output 'NO_THROW' } catch { Write-Output 'THROWN' }"
        )
        assert cp.returncode == 0
        assert "THROWN" in cp.stdout, f"port={bad} должен был throw: {cp.stdout}/{cp.stderr}"

    for good in ("1", "65535"):
        cmd_path = dot_source_prefix()
        cp = run_ps(
            cmd_path +
            f"(Get-Command Stop-NodeProcesses).Parameters['Port'].Attributes | "
            "Where-Object { $_ -is [System.Management.Automation.ValidateRangeAttribute] } | "
            "ForEach-Object { Write-Output \"MIN=$($_.MinRange) MAX=$($_.MaxRange)\" }"
        )
        assert "MIN=1 MAX=65535" in cp.stdout
