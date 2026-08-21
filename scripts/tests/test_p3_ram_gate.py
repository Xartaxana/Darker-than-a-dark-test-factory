"""spec-p3-second-emulator N3 (хвост N2 §6 п.3): RAM-гейт КОДОМ в
`Start-Emulator` (`-MinFreeGBPreStart`/`-MinFreeGBPostStart`) + `Get-FreeMemoryGB`.

Device-free: `-FreeMemoryProvider`/`-PortListenerResolver`/`-AdbDevicesProvider`
и т.п. - инжектируемые seam'ы (тот же приём, что остальные N1 юниты
`test_p3_start_emulator_appium_ports.py`), реальный `emulator.exe`/adb НЕ
запускается - Start-Process/wait-цикл НИКОГДА не достигаются на pre-start
abort (throw ДО `Start-Process`).

ПРИМЕЧАНИЕ (найдено этой сессией, критик-вход rework attempt 2, B4): весь
POST-start путь (после `boot_completed`, где живёт fix-совет 3 - гашение +
верификация + `Undo-EmulatorSessionStateEntry`) НЕ имеет device-free seam'а
для `$emu`/`$adb`-БИНАРНИКА (только для доменных провайдеров вроде
`-AdbDevicesProvider`, которые в этой ветке кода не читаются вовсе - реальный
`& $adb wait-for-device`/`getprop sys.boot_completed`-поллинг стоит ЖЁСТКО)
- вопреки более раннему докстрингу этого файла (утверждавшему обратное без
реального теста, подтверждающего это) юнит-тестами POST-start ветка целиком
НЕ покрыта и не может быть без нового seam'а для самого исполняемого
emulator.exe/adb.exe (архитектурная правка вне DoD этой задачи - не
расширяю scope по правилу 2, докладываю находкой). Закрыто ЧАСТИЧНО: прямой
юнит на `Undo-EmulatorSessionStateEntry` (сама функция отката, ниже) -
device-free, не требует эмулятора; end-to-end post-start abort (реальное
гашение "adb -s <serial> emu kill" + 10с-поллинг + Stop-OrphanedQemu) -
остаётся device-witness координатора, не этого файла.

!!! ГРАНИЦА ИЗОЛЯЦИИ (M1, критик-раунд 3) !!! `fake_root` подменяет ТОЛЬКО
`$root`. `$env:ANDROID_HOME`/`PATH` ставит `env.ps1`, дот-сорсимый ПЕРВОЙ
СТРОКОЙ `tasks.ps1`, — от НАСТОЯЩЕГО корня и ДО подмены; `$adb`/`$emu`
резолвятся из ANDROID_HOME и остаются РЕАЛЬНЫМИ. Значит `fake_root` сам по
себе НЕ делает пробу device-free: всё, что способно дойти до
`Start-Process $emu`/`& $adb ...`, ОБЯЗАНО инжектировать шов (`-Launcher`,
`-AdbDevicesProvider`, `-BootCompletedProvider`, `-EmuKiller`,
`-WaitForDeviceProvider`). Шесть проб этого файла выглядели device-free
только потому, что в worktree нет `tools/`; в главном чекауте они подняли бы
шесть живых эмуляторов, а фолбэк-ветка снесла бы чужой живой qemu. Тот же
текст — в `_ps1_helpers.dot_source_prefix`, чтобы класс не повторился в
следующей PS-пробе.

ИЗОЛЯЦИЯ `$root` (критик-раунд 2, найдено ЭТИМ раундом эмпирически): пробы,
где RAM-гейт НЕ абортит (граница ровно на пороге, fail-soft `$null`, явный
`-MinFreeGBPreStart 0`, дефолт стека 1), доходят до
`Set-EmulatorSessionState` - и БЕЗ переопределения `$root` писали РЕАЛЬНЫЙ
`state/emulator-session.json` репозитория, создавая там `by_serial`-записи
несуществующих подъёмов (в worktree этой задачи так и появилась запись
`emulator-5556` c `avd_name=ao3_test_api34`, ошибочно принятая за фабрикацию
бэкфилла). КАЖДАЯ проба этого файла ТЕПЕРЬ дот-сорсится с
`fake_root=tmp_path` - тот же приём, что уже применяли Undo-пробы ниже.
"""
from __future__ import annotations

import json

from _ps1_helpers import dot_source_prefix, run_ps

# M1 (БЛОКЕР МЕРЖА, критик-раунд 3): маркер-бросающий `-Launcher`. Образец
# подхода - маркер-бросающий `-OrphanCleaner` в
# test_p3_start_emulator_appium_ports.py::test_orphan_branch_wired_via_
# injectable_seams_reaches_orphan_cleaner_not_throw: проба НАМЕРЕННО
# останавливается ровно в точке, где начался бы живой side-effect.
#
# Зачем: `fake_root` изолирует ТОЛЬКО `$root`. `$emu`/`$adb` резолвятся из
# `$env:ANDROID_HOME`, который ставит `env.ps1` (дот-сорсится строкой 11
# tasks.ps1) от НАСТОЯЩЕГО корня - ДО подмены. Шесть проб этого файла
# проходят RAM-гейт и раньше доезжали до РЕАЛЬНОГО `Start-Process
# emulator.exe`; в worktree это маскировало отсутствие `tools/`, в главном
# чекауте канонический прогон поднял бы 6 живых эмуляторов (две пробы - на
# 5554 с ao3_test_api34!), а фолбэк-ветка позвала бы
# `Stop-OrphanedQemu -AvdName ao3_test_api34` и убила бы ЖИВОЙ фабричный
# qemu. Воспроизведено суррогатным emulator.exe (валидный PE вместо
# настоящего): проба печатала "Waiting for device boot (emulator-5556,
# snapshot, up to 2s)..." - т.е. Start-Process ИСПОЛНИЛСЯ.
#
# ВАЖНО (найдено эмпирически ЭТИМ раундом): внутри `-Launcher` НЕЛЬЗЯ писать
# `Write-Output` рядом с возвратом значения - `& $Launcher ...` соберёт В
# МАССИВ и вывод, и процесс, а `$proc` дальше уедет в
# `Stop-OrphanedQemu -LauncherProc` (типизирован `[System.Diagnostics.Process]`)
# и упадёт биндингом "Cannot convert System.Object[]". Поэтому маркер несёт
# САМ ТЕКСТ ИСКЛЮЧЕНИЯ (путь включён в него), а не отдельная строка вывода.
_LAUNCH_MARKER = "STOP_BEFORE_LIVE_START_PROCESS_MARKER"
_MARKER_LAUNCHER = (
    "-Launcher { param($Path,$ArgList) throw \"%s path=$Path args=$($ArgList -join ' ')\" } " % _LAUNCH_MARKER
)


def _assert_no_real_launch(cp) -> None:
    """Решающая проверка M1: реальный `Start-Process` НЕ достигнут.

    `"Waiting for device boot"` печатается СЛЕДУЮЩЕЙ строкой ПОСЛЕ возврата
    лаунчера - её появление означает, что запуск состоялся (ровно этот
    витнесс дал суррогатный emulator.exe в красной пробе). Маркер-лаунчер
    бросает ДО неё, поэтому её отсутствие + наличие маркера = "дошли ровно
    до точки запуска и не запустили"."""
    assert "Waiting for device boot" not in cp.stdout, (
        f"РЕАЛЬНЫЙ Start-Process достигнут - шов -Launcher обойдён:\n{cp.stdout}"
    )


def _assert_launcher_reached(cp) -> None:
    """Гейт НЕ абортил: дошли до точки запуска (лаунчер позван) и там встали.

    Маркер несёт путь к бинарнику - заодно видно, что запускали БЫ именно
    `emulator.exe` из `$env:ANDROID_HOME` (тот самый реальный путь, который
    `fake_root` не изолирует)."""
    assert _LAUNCH_MARKER in cp.stdout, f"лаунчер не позван / маркер не пойман:\n{cp.stdout}"
    assert "emulator.exe" in cp.stdout, f"маркер без пути к бинарнику:\n{cp.stdout}"
    _assert_no_real_launch(cp)


# --- Get-FreeMemoryGB ---

def test_get_free_memory_gb_computes_from_provider(tmp_path):
    cp = run_ps(
        dot_source_prefix(fake_root=tmp_path) +
        "$g = Get-FreeMemoryGB -OsInfoProvider { [pscustomobject]@{ FreePhysicalMemory = 2097152 } }; "  # 2 GB в КБ
        "Write-Output \"G=$g\""
    )
    assert cp.returncode == 0
    assert "G=2" in cp.stdout


def test_get_free_memory_gb_null_when_provider_fails(tmp_path):
    cp = run_ps(
        dot_source_prefix(fake_root=tmp_path) +
        "$g = Get-FreeMemoryGB -OsInfoProvider { $null }; "
        "Write-Output \"ISNULL=$($null -eq $g)\""
    )
    assert cp.returncode == 0
    assert "ISNULL=True" in cp.stdout


# --- Start-Emulator: RAM-гейт ВЫКЛЮЧЕН по умолчанию (back-compat) ---

def test_ram_gate_disabled_by_default_does_not_call_provider(tmp_path):
    """Back-compat: дефолт 0 (-Port 5554) -> FreeMemoryProvider НЕ вызывается
    вовсе. M1: порт СВОБОДЕН (`-PortListenerResolver { $null }`), поэтому
    проба доходит до точки запуска - её держит маркер-лаунчер, а не
    отсутствие `tools/`."""
    cp = run_ps(
        dot_source_prefix(fake_root=tmp_path) +
        "$calls = 0; "
        "try { Start-Emulator -Port 5554 -FreeMemoryProvider { $script:calls++; 99.0 } "
        "-PortListenerResolver { $null } -ProcessInfoResolver { $null } "
        "-AdbDevicesProvider { @() } " + _MARKER_LAUNCHER + "-ErrorAction Stop } catch { "
        "Write-Output \"CAUGHT: $($_.Exception.Message)\" }; "
        "Write-Output \"CALLS=$calls\""
    )
    assert cp.returncode == 0, cp.stderr
    assert "CALLS=0" in cp.stdout
    _assert_launcher_reached(cp)


# --- pre-start abort ---

def test_ram_gate_prestart_aborts_before_any_side_effect(tmp_path):
    """Free RAM ниже порога -> throw ДО Start-Process/Set-EmulatorSessionState -
    witness: `$root/state/` НЕ создаётся (Set-EmulatorSessionState создала бы
    его), OrphanCleaner/PortListenerResolver вообще не важны, порт свободен
    ($null владелец). Витнесс ТЕПЕРЬ ИЗМЕРЯЕТСЯ (assert ниже), а не только
    заявлен докстрингом — раньше `$root` не переопределялся вовсе и «не
    создаётся» проверить было негде."""
    cp = run_ps(
        dot_source_prefix(fake_root=tmp_path) +
        "try { Start-Emulator -Port 5556 -MinFreeGBPreStart 3.5 "
        "-FreeMemoryProvider { 2.0 } -PortListenerResolver { $null } " + _MARKER_LAUNCHER +
        "-ErrorAction Stop; "
        "Write-Output 'NO_THROW' } catch { Write-Output \"THROWN: $($_.Exception.Message)\" }"
    )
    assert cp.returncode == 0
    assert "THROWN:" in cp.stdout
    assert "RAM-гейт (pre-start)" in cp.stdout
    assert "NO_THROW" not in cp.stdout
    assert not (tmp_path / "state").exists(), "abort ДО Set-EmulatorSessionState - state/ не создан"
    # КОНТРОЛЬНАЯ ПАРА к M1: гейт абортил -> точка запуска НЕ достигнута вовсе
    # (лаунчер даже не позван - в отличие от проб, проходящих гейт).
    assert _LAUNCH_MARKER not in cp.stdout
    _assert_no_real_launch(cp)


def test_ram_gate_prestart_boundary_passes_exactly_at_threshold(tmp_path):
    """M6: free РОВНО НА границе (free == порог) - гейт НЕ абортит (строгое
    `<`, не `<=`). Порт занят фейковым "своим" qemu, чтобы дойти до throw
    ПОСЛЕ RAM-гейта детерминированно (оркестрация полного Start-Process не
    нужна для этой пробы - гейт стоит раньше side-effect'ов)."""
    cp = run_ps(
        dot_source_prefix(fake_root=tmp_path) +
        "try { Start-Emulator -Port 5556 -MinFreeGBPreStart 3.5 -FreeMemoryProvider { 3.5 } "
        "-PortListenerResolver { $null } " + _MARKER_LAUNCHER + "-ErrorAction Stop; "
        "Write-Output 'NO_THROW' } "
        "catch { Write-Output \"THROWN: $($_.Exception.Message)\" }"
    )
    assert cp.returncode == 0
    # РОВНО на границе гейт НЕ абортит. РАНЬШЕ это "доказывалось" тем, что throw
    # приходил "из другого места" - на деле из РЕАЛЬНОГО Start-Process (M1).
    # ТЕПЕРЬ исход детерминирован: throw обязан быть маркером лаунчера, а не
    # RAM-гейтом, и реального запуска не было.
    assert "RAM-гейт (pre-start)" not in cp.stdout
    _assert_launcher_reached(cp)


def test_ram_gate_prestart_null_free_memory_skips_gate_fail_soft(tmp_path):
    """Fail-soft: провайдер вернул $null (WMI недоступен) -> гейт МОЛЧА
    пропускается (неспособность ИЗМЕРИТЬ не абортит)."""
    cp = run_ps(
        dot_source_prefix(fake_root=tmp_path) +
        "try { Start-Emulator -Port 5556 -MinFreeGBPreStart 3.5 -FreeMemoryProvider { $null } "
        "-PortListenerResolver { $null } " + _MARKER_LAUNCHER + "-ErrorAction Stop; "
        "Write-Output 'NO_THROW' } "
        "catch { Write-Output \"THROWN: $($_.Exception.Message)\" }"
    )
    assert cp.returncode == 0
    assert "RAM-гейт (pre-start)" not in cp.stdout
    _assert_launcher_reached(cp)


def test_ram_gate_disabled_min_zero_never_aborts_regardless_of_free(tmp_path):
    """Граница ЗА пределом снизу: -MinFreeGBPreStart 0 ЯВНЫМ параметром
    (B4, критик-вход rework attempt 2: "явное отключение — только явным
    параметром" — дефолт для -Port != 5554 БОЛЬШЕ НЕ 0, см. тесты default-
    порогов ниже) - гейт выключен ДАЖЕ при абсурдно низком free (0.01 GB)."""
    cp = run_ps(
        dot_source_prefix(fake_root=tmp_path) +
        "try { Start-Emulator -Port 5556 -MinFreeGBPreStart 0 -FreeMemoryProvider { 0.01 } "
        "-PortListenerResolver { $null } " + _MARKER_LAUNCHER + "-ErrorAction Stop; "
        "Write-Output 'NO_THROW' } "
        "catch { Write-Output \"THROWN: $($_.Exception.Message)\" }"
    )
    assert cp.returncode == 0
    assert "RAM-гейт" not in cp.stdout
    _assert_launcher_reached(cp)


# --- B4 (критик-вход rework attempt 2): дефолтные пороги подключены к
# РЕАЛЬНОМУ пути (-Port != 5554), без ЯВНОГО параметра ---

def test_ram_gate_default_threshold_for_non_5554_port_is_wired_prestart(tmp_path):
    """B4: РАНЬШЕ дефолт был 0 для ЛЮБОГО порта (ненулевые пороги передавали
    ТОЛЬКО тесты) - реальный вызов Use-DeviceStack/Start-Emulator -Port 5556
    БЕЗ явного -MinFreeGBPreStart НИКОГДА не гейтился. Дефолт ТЕПЕРЬ 3.5 GB
    (план: клон+1.0 GB буфер) для -Port != 5554 - throw БЕЗ явного параметра
    вообще."""
    cp = run_ps(
        dot_source_prefix(fake_root=tmp_path) +
        "try { Start-Emulator -Port 5556 -FreeMemoryProvider { 2.0 } "
        "-PortListenerResolver { $null } " + _MARKER_LAUNCHER + "-ErrorAction Stop; "
        "Write-Output 'NO_THROW' } "
        "catch { Write-Output \"THROWN: $($_.Exception.Message)\" }"
    )
    assert cp.returncode == 0
    assert "THROWN:" in cp.stdout
    assert "RAM-гейт (pre-start)" in cp.stdout
    assert "3.5 GB" in cp.stdout
    assert "NO_THROW" not in cp.stdout
    # Контрольная пара: гейт абортил -> лаунчер не позван вовсе
    assert _LAUNCH_MARKER not in cp.stdout
    _assert_no_real_launch(cp)


def test_ram_gate_default_threshold_for_5554_stays_zero_back_compat(tmp_path):
    """B4 контрольная проба (back-compat): дефолт стека 1 (-Port 5554)
    ОСТАЁТСЯ 0 (выключен) БЕЗ явного параметра - легаси-носители, не
    мигрированные на Use-DeviceStack -N 2, поведения не меняют."""
    cp = run_ps(
        dot_source_prefix(fake_root=tmp_path) +
        "$calls = 0; "
        "try { Start-Emulator -Port 5554 -FreeMemoryProvider { $script:calls++; 0.01 } "
        "-PortListenerResolver { $null } -ProcessInfoResolver { $null } "
        "-AdbDevicesProvider { @() } " + _MARKER_LAUNCHER + "-ErrorAction Stop } catch { "
        "Write-Output \"CAUGHT: $($_.Exception.Message)\" }; "
        "Write-Output \"CALLS=$calls\""
    )
    assert cp.returncode == 0, cp.stderr
    assert "CALLS=0" in cp.stdout
    _assert_launcher_reached(cp)


def test_ram_gate_default_threshold_boundary_exactly_at_3_5_passes(tmp_path):
    """M6: default-порог (3.5 GB) - граница РОВНО НА пороге не абортит
    (строгое `<`), БЕЗ явного -MinFreeGBPreStart."""
    cp = run_ps(
        dot_source_prefix(fake_root=tmp_path) +
        "try { Start-Emulator -Port 5556 -FreeMemoryProvider { 3.5 } "
        "-PortListenerResolver { $null } " + _MARKER_LAUNCHER + "-ErrorAction Stop; "
        "Write-Output 'NO_THROW' } "
        "catch { Write-Output \"THROWN: $($_.Exception.Message)\" }"
    )
    assert cp.returncode == 0
    assert "RAM-гейт (pre-start)" not in cp.stdout
    _assert_launcher_reached(cp)


# --- M1-БОНУС (критик-раунд 3): POST-START abort ЦЕЛИКОМ, юнитом ---
#
# Прежний докстринг этого файла объявлял post-start ветку непокрываемой
# («нет device-free seam'а для $emu/$adb-БИНАРНИКА») и оставлял её принятым
# остаточным риском B4. Шов `-Launcher` + доведённые до конца adb-швы
# (`-AdbDevicesProvider` теперь обслуживает И оракул буда, И поллинг
# подтверждения гашения; новые `-BootCompletedProvider`/`-EmuKiller`)
# закрывают гэп: ветка проходится ЦЕЛИКОМ без единого живого бинарника.

def test_post_start_ram_gate_abort_full_branch_is_unit_covered(tmp_path):
    """M1-бонус: RAM-гейт POST-start отрабатывает ПОЛНЫЙ сценарий отката.

    Оркестрация: `-Launcher` отдаёт НАСТОЯЩИЙ, но безобидный процесс
    (`powershell -Command Start-Sleep 60`) - `Stop-OrphanedQemu` типизирован
    `[System.Diagnostics.Process]`, поэтому фейковый PSCustomObject не
    связался бы; заодно `$proc.HasExited` честно работает. Оракул буда сразу
    видит устройство, getprop сразу отдаёт "1", RAM-провайдер отдаёт
    достаточно ДО старта и мало ПОСЛЕ (пара вызовов), поллинг подтверждения
    гашения видит устройство ушедшим.

    Проверяем ВСЕ обещания ветки: emu kill позван для нужного серийника;
    гашение подтверждено; `by_serial` откачена
    (`Undo-EmulatorSessionStateEntry` - зовётся по-настоящему, пишет в
    `tmp_path`); throw несёт причину; ни IPv4-пин, ни mitm-CA не выполнялись
    (до них не дошло)."""
    state_file = tmp_path / "state" / "emulator-session.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps({
        "gpu": "host", "avd_name": "prev_avd", "updated_utc": "2026-08-19T00:00:00Z",
        "by_serial": {"emulator-5554": {"gpu": "host", "avd_name": "prev_avd",
                                        "updated_utc": "2026-08-19T00:00:00Z"}},
    }), encoding="utf-8")
    cmd = (
        dot_source_prefix(fake_root=tmp_path) +
        "$killCalls = @(); $freeCalls = 0; "
        # Оракул буда видит устройство сразу; поллинг ПОСЛЕ emu kill - уже нет.
        "$killed = $false; "
        "try { Start-Emulator -Port 5556 -AvdName 'fake_avd_post_start' "
        "-MinFreeGBPreStart 0 -MinFreeGBPostStart 1.0 "
        "-FreeMemoryProvider { $script:freeCalls++; if ($script:freeCalls -ge 1 -and $script:killed) { 0.5 } "
        "    elseif ($script:freeCalls -ge 1) { 0.5 } else { 9.0 } } "
        "-PortListenerResolver { $null } "
        "-AdbDevicesProvider { param($A) if ($script:killed) { @('List of devices attached','') } "
        "    else { @('List of devices attached', 'emulator-5556 device') } } "
        "-BootCompletedProvider { param($A) '1' } "
        "-EmuKiller { param($A,$S) $script:killCalls += $S; $script:killed = $true } "
        # ТОЛЬКО процесс в выводе scriptblock'а (никакого Write-Output рядом -
        # иначе `$proc` станет массивом, см. комментарий у _MARKER_LAUNCHER).
        "-Launcher { param($Path,$ArgList) "
        "    Start-Process -FilePath 'powershell' -ArgumentList '-NoProfile','-Command','Start-Sleep 60' -PassThru } "
        "-ErrorAction Stop; Write-Output 'NO_THROW' } "
        "catch { Write-Output \"THROWN: $($_.Exception.Message)\" }; "
        "Write-Output \"KILLED_SERIALS=$($killCalls -join ',')\""
    )
    cp = run_ps(cmd, timeout=120)
    assert cp.returncode == 0, f"stdout={cp.stdout}\nstderr={cp.stderr}"
    assert "NO_THROW" not in cp.stdout, cp.stdout
    # (а) сработал именно POST-start гейт
    assert "RAM-гейт (post-start)" in cp.stdout, cp.stdout
    # (б) emu kill позван РОВНО для своего серийника
    assert "KILLED_SERIALS=emulator-5556" in cp.stdout, cp.stdout
    # (в) гашение ПОДТВЕРЖДЕНО поллингом (не на слово)
    assert "гашение подтверждено: True" in cp.stdout, cp.stdout
    # (г) Undo-EmulatorSessionStateEntry реально откатил by_serial своего порта,
    #     не тронув соседний стек
    data = json.loads(state_file.read_text(encoding="utf-8"))
    assert "emulator-5556" not in data["by_serial"], data
    assert "emulator-5554" in data["by_serial"], data
    # (д) до IPv4-пина/mitm-CA не дошло
    assert "Installing mitmproxy CA" not in cp.stdout


def test_snapshot_fallback_relaunch_also_goes_through_launcher_seam(tmp_path):
    """M1, ВТОРАЯ точка запуска: фолбэк `-no-snapshot-load`. Именно эта ветка
    делала аварию особенно дорогой - перед вторым запуском она зовёт
    `Stop-OrphanedQemu -AvdName <AVD>`, а две из шести проб шли с дефолтным
    `ao3_test_api34`, т.е. в главном чекауте подмели бы ЖИВОЙ фабричный qemu.

    Оракул буда НИКОГДА не видит устройство -> снапшот-таймаут -> фолбэк.
    Считаем вызовы лаунчера: первый - обычный, второй обязан нести
    `-no-snapshot-load` и тоже пройти ЧЕРЕЗ ШОВ (а не через живой
    Start-Process)."""
    cmd = (
        dot_source_prefix(fake_root=tmp_path) +
        "$launches = @(); "
        "try { Start-Emulator -Port 5556 -AvdName 'fake_avd_fallback' -SnapshotBootTimeoutSec 1 "
        "-MinFreeGBPreStart 0 -MinFreeGBPostStart 0 "
        "-PortListenerResolver { $null } "
        "-AdbDevicesProvider { param($A) @('List of devices attached','') } "
        "-WaitForDeviceProvider { param($A) $null } "
        "-BootCompletedProvider { param($A) '1' } "
        "-OrphanCleaner { param($Avd) $null } "
        "-Launcher { param($Path,$ArgList) $script:launches += ($ArgList -join ' '); "
        "    if ($script:launches.Count -ge 2) { throw '" + _LAUNCH_MARKER + " second' } "
        "    Start-Process -FilePath 'powershell' -ArgumentList '-NoProfile','-Command','Start-Sleep 60' -PassThru } "
        "-ErrorAction Stop; Write-Output 'NO_THROW' } "
        "catch { Write-Output \"THROWN: $($_.Exception.Message)\" }; "
        "Write-Output \"LAUNCH_COUNT=$($launches.Count)\"; "
        "Write-Output \"SECOND_ARGS=$($launches[1])\""
    )
    cp = run_ps(cmd, timeout=120)
    assert cp.returncode == 0, f"stdout={cp.stdout}\nstderr={cp.stderr}"
    assert "LAUNCH_COUNT=2" in cp.stdout, cp.stdout
    assert "-no-snapshot-load" in cp.stdout, cp.stdout
    assert _LAUNCH_MARKER in cp.stdout, cp.stdout


def test_post_start_ram_gate_boundary_exactly_at_threshold_does_not_abort(tmp_path):
    """M6-граница к бонусу: free РОВНО НА post-start пороге (1.0) - abort'а
    НЕТ (строгое `<`). Позитивный оракул - шов `-GuestPinner` (стоит СРАЗУ
    ПОСЛЕ гейта): его маркер в stdout доказывает, что гейт пройден без
    abort'а. Шов введён постмерж N3: без него проба доходила до реального
    `adb root`/`adb wait-for-device` внутри Set-GuestIPv4Pin и в главном
    чекауте блокировалась навсегда (в worktree маскировалось отсутствием
    tools/ - живой экземпляр класса M1)."""
    state_file = tmp_path / "state" / "emulator-session.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps({"by_serial": {}}), encoding="utf-8")
    cmd = (
        dot_source_prefix(fake_root=tmp_path) +
        "try { Start-Emulator -Port 5556 -AvdName 'fake_avd_boundary' "
        "-MinFreeGBPreStart 0 -MinFreeGBPostStart 1.0 -FreeMemoryProvider { 1.0 } "
        "-PortListenerResolver { $null } "
        "-AdbDevicesProvider { param($A) @('List of devices attached', 'emulator-5556 device') } "
        "-WaitForDeviceProvider { param($A) $null } "
        "-OrphanCleaner { param($Avd) $null } "
        "-GuestPinner { param($A) Write-Output 'PIN_SEAM_REACHED' } "
        "-BootCompletedProvider { param($A) '1' } "
        "-EmuKiller { param($A,$S) Write-Output \"UNEXPECTED_KILL=$S\" } "
        "-Launcher { param($Path,$ArgList) "
        "    Start-Process -FilePath 'powershell' -ArgumentList '-NoProfile','-Command','Start-Sleep 60' -PassThru } "
        "-ErrorAction Stop; Write-Output 'REACHED_PAST_POST_START_GATE' } "
        "catch { Write-Output \"THROWN: $($_.Exception.Message)\" }"
    )
    cp = run_ps(cmd, timeout=120)
    assert cp.returncode == 0, cp.stderr
    assert "PIN_SEAM_REACHED" in cp.stdout, cp.stdout
    assert "RAM-гейт (post-start)" not in cp.stdout, cp.stdout
    assert "UNEXPECTED_KILL" not in cp.stdout, cp.stdout


# --- B4 fix-совет 3 (критик-вход rework attempt 2): Undo-EmulatorSessionStateEntry ---
#
# Device-free прямой юнит на саму функцию отката (см. примечание докстринга
# файла выше про отсутствие post-start seam'а для реального $adb/emulator.exe -
# end-to-end post-start abort не покрыт этим файлом, только сама функция
# отката, которую post-start ветка вызывает).

def test_undo_emulator_session_state_entry_removes_only_target_serial(tmp_path):
    state_file = tmp_path / "state" / "emulator-session.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps({
        "gpu": "swiftshader_indirect", "avd_name": "ao3_corridor_api34",
        "updated_utc": "2026-08-20T12:00:00Z",
        "by_serial": {
            "emulator-5554": {"gpu": "host", "avd_name": "ao3_test_api34", "updated_utc": "2026-08-19T00:00:00Z"},
            "emulator-5556": {"gpu": "swiftshader_indirect", "avd_name": "ao3_corridor_api34", "updated_utc": "2026-08-20T12:00:00Z"},
        },
    }), encoding="utf-8")
    cp = run_ps(
        dot_source_prefix(fake_root=tmp_path) +
        "Undo-EmulatorSessionStateEntry -Port 5556"
    )
    assert cp.returncode == 0, cp.stderr
    assert "RAM-гейт (post-start) abort" in cp.stdout
    data = json.loads(state_file.read_text(encoding="utf-8"))
    assert "emulator-5556" not in data["by_serial"]
    # ТОЛЬКО целевой серийник снят - соседний (emulator-5554, ДРУГОЙ стек) НЕ тронут.
    assert "emulator-5554" in data["by_serial"]
    assert data["by_serial"]["emulator-5554"]["avd_name"] == "ao3_test_api34"
    # флэт top-level поля ("последний записавший стек") НЕ трогаются (докстринг
    # функции: "откат ТОЛЬКО by_serial... шире по духу AT-BUG-063 - вне скоупа").
    assert data["avd_name"] == "ao3_corridor_api34"


def test_undo_emulator_session_state_entry_missing_serial_is_noop(tmp_path):
    """M6 (адверсариальная батарея): серийника, который откатывают, НЕТ в
    by_serial вовсе (например RAM-гейт абортил ДО первой Set-EmulatorSessionState-
    записи для этого порта) - тихий no-op, файл НЕ переписывается вовсе (не
    просто "остаётся тем же по содержимому" - НИКАКОЙ Write-FileAtomic-вызов)."""
    state_file = tmp_path / "state" / "emulator-session.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps({
        "gpu": "host", "avd_name": "ao3_test_api34", "updated_utc": "2026-08-19T00:00:00Z",
        "by_serial": {"emulator-5554": {"gpu": "host", "avd_name": "ao3_test_api34", "updated_utc": "2026-08-19T00:00:00Z"}},
    }), encoding="utf-8")
    before_mtime = state_file.stat().st_mtime_ns
    cp = run_ps(
        dot_source_prefix(fake_root=tmp_path) +
        "Undo-EmulatorSessionStateEntry -Port 5556"
    )
    assert cp.returncode == 0, cp.stderr
    assert "RAM-гейт (post-start) abort" not in cp.stdout
    assert state_file.stat().st_mtime_ns == before_mtime


def test_undo_emulator_session_state_entry_missing_state_file_is_noop(tmp_path):
    """M6: state-файл ОТСУТСТВУЕТ вовсе (гейт абортил на самом первом
    подъёме стека) - тихий no-op, НЕ создаёт файл, НЕ throw."""
    cp = run_ps(
        dot_source_prefix(fake_root=tmp_path) +
        "Undo-EmulatorSessionStateEntry -Port 5556; Write-Output 'REACHED_END'"
    )
    assert cp.returncode == 0, cp.stderr
    assert "REACHED_END" in cp.stdout
    assert not (tmp_path / "state" / "emulator-session.json").exists()


def test_undo_emulator_session_state_entry_corrupt_json_warns_skips(tmp_path):
    """M6: битый JSON state-файла - WARN + пропуск (fail-soft, НЕ throw -
    тот же класс отказоустойчивости, что Set-EmulatorSessionState)."""
    state_file = tmp_path / "state" / "emulator-session.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text("{ not valid json !!!", encoding="utf-8")
    cp = run_ps(
        dot_source_prefix(fake_root=tmp_path) +
        "Undo-EmulatorSessionStateEntry -Port 5556; Write-Output 'REACHED_END'"
    )
    assert cp.returncode == 0, cp.stderr
    assert "нечитаем" in cp.stdout
    assert "REACHED_END" in cp.stdout
