# Раннеры тестового фреймворка. Использование:
#   . D:\AO3_tests\scripts\tasks.ps1
#   Start-Emulator ; Start-Appium ; Invoke-Smoke
# Требует предварительно: . D:\AO3_tests\scripts\env.ps1 (для JAVA_HOME/ANDROID_HOME/PATH)
$ErrorActionPreference = "Stop"
$root = "D:\AO3_tests"
. "$root\scripts\env.ps1"
$venv = "$root\framework\.venv\Scripts"

function Clear-EmulatorStaleLocks {
    # AT-BUG-012: крэш quickboot-буда (см. Start-Emulator) оставляет стейл-локи
    # AVD, которые путают следующий подъём. Чистим ПЕРЕД стартом (штатная
    # гигиена) и повторно после детекта крэша (перед фолбэком). Идемпотентна:
    # отсутствие файлов — не ошибка.
    #
    # AT-BUG-014: hardware-qemu.ini.lock иногда оказывается НЕПУСТОЙ ДИРЕКТОРИЕЙ
    # (внутри лежит файл pid) — так остаётся после жёсткого килла зависшего
    # qemu-system-x86_64. Remove-Item -Force без -Recurse на непустой директории
    # падает NullReferenceException, которую -ErrorAction SilentlyContinue НЕ
    # гасит, и это останавливает весь Start-Emulator. Ветвим по типу элемента.
    #
    # AT-BUG-024: параметризовано именем AVD (дефолт — прежнее поведение,
    # обратная совместимость с вызовами без аргумента).
    param([string]$AvdName = "ao3_test_api34")
    $avdDir = "$root\tools\avd\$AvdName.avd"
    foreach ($name in @("multiinstance.lock", "hardware-qemu.ini.lock")) {
        $p = Join-Path $avdDir $name
        if (Test-Path $p) {
            if (Test-Path $p -PathType Container) {
                Remove-Item $p -Recurse -Force -ErrorAction SilentlyContinue
            } else {
                Remove-Item $p -Force -ErrorAction SilentlyContinue
            }
            Write-Host "Removed stale lock: $p" -ForegroundColor Yellow
        }
    }
}

function Start-Emulator {
    # -WritableSystem: нужен для replay-режима (установка CA mitmproxy в системное
    # хранилище, scripts/install-mitm-ca.sh). Для live-прогонов не требуется.
    #
    # AT-BUG-012: quickboot-снапшот default_boot нестабилен на этом WHPX-хосте —
    # qemu-процесс тихо исчезает к ~20-й секунде буда (голый `adb wait-for-device`
    # в этом случае висит НАВСЕГДА, устройство не появится никогда), плюс после
    # крэша остаются стейл-локи. Воспроизведено 6+ раз за 2026-07-10..07-17
    # разными сессиями/агентами на одном и том же снапшоте без его пересоздания —
    # это не единичная порченая запись, а системная хрупкость снапшот-restore на
    # этом хосте (docs/environment-setup.md, AT-BUG-012). Обход дешёвый и
    # проверенный: чистый `-no-snapshot-load` поднимается штатно каждый раз.
    # Поэтому вместо блокирующего wait-for-device — поллинг с таймаутом:
    # не дождались устройства/процесс умер → автофолбэк на чистую загрузку.
    # -Gpu / AO3_EMU_GPU: GPU-бэкенд qemu. Дефолт swiftshader_indirect —
    # единственный стабильный на этом хосте для replay-нагрузки (AT-BUG-016).
    # Оверрайд введён для диагностики AT-BUG-021 (краши qemu 0xc0000005 на
    # тяжёлых live-страницах): ремедиация п.1 бага — прогон под альтернативным
    # бэкендом (host / angle_indirect). Параметр > env > дефолт.
    # AT-BUG-024: -AvdName параметризует имя AVD (дефолт — прежний ao3_test_api34,
    # обратная совместимость обязательна — существующие вызовы без аргумента не меняют
    # поведение). Второй (нижний API) AVD — ao3_test_api29 (AT-BUG-028: перевод с
    # api26 — embedded WebView Chrome 69 EOL, структурно несовместим с текущим
    # appium-chromedriver; api26 AVD оставлен на диске неиспользуемым).
    param([switch]$WritableSystem, [int]$SnapshotBootTimeoutSec = 45, [string]$Gpu = "", [string]$AvdName = "ao3_test_api34")
    if (-not $Gpu) { $Gpu = if ($env:AO3_EMU_GPU) { $env:AO3_EMU_GPU } else { "swiftshader_indirect" } }
    $adb = "$env:ANDROID_HOME\platform-tools\adb.exe"
    $emu = "$env:ANDROID_HOME\emulator\emulator.exe"

    Clear-EmulatorStaleLocks -AvdName $AvdName

    $emuArgs = @("-avd",$AvdName,"-no-boot-anim","-gpu",$Gpu)
    if ($WritableSystem) { $emuArgs += "-writable-system" }

    $proc = Start-Process -FilePath $emu -ArgumentList $emuArgs -WindowStyle Minimized -PassThru
    Write-Host "Waiting for device boot (snapshot, up to ${SnapshotBootTimeoutSec}s)..." -ForegroundColor Cyan

    $deadline = (Get-Date).AddSeconds($SnapshotBootTimeoutSec)
    $deviceUp = $false
    do {
        Start-Sleep 2
        if ($proc.HasExited) { break }
        $lines = & $adb devices
        $deviceUp = @($lines | Select-Object -Skip 1 | Where-Object { $_ -match '\sdevice$' }).Count -gt 0
    } while (-not $deviceUp -and (Get-Date) -lt $deadline)

    if (-not $deviceUp) {
        # Снапшот-буд не поднял устройство в отведённое время — по AT-BUG-012
        # это известный класс крэша quickboot на этом хосте, не зависание,
        # которое стоит пережидать дольше. Явный автофолбэк, не молча.
        Write-Warning ("Start-Emulator: снапшот-буд не поднял устройство за ${SnapshotBootTimeoutSec}s " +
            "(AT-BUG-012: известная нестабильность quickboot-снапшота default_boot на этом хосте) - " +
            "фолбэк на чистую загрузку -no-snapshot-load.")
        # AT-BUG-014 (корень): $proc — это Start-Process-launcher emulator.exe, а НЕ
        # фактический дочерний qemu-system-x86_64.exe (отдельный процесс, отдельный
        # PID). На этом хосте qemu переживает килл лаунчера (наблюдалось 30+ минут) и
        # легитимно держит hardware-qemu.ini.lock, из-за чего Clear-EmulatorStaleLocks
        # ниже спотыкается о ЖИВОЙ, а не мёртвый артефакт при каждой следующей попытке.
        # Убиваем и лаунчер, и его прямых qemu-детей, и подчищаем возможных
        # осиротевших qemu-процессов этого же AVD по командной строке (страховка на
        # случай, если родственная связь уже разорвана).
        if (-not $proc.HasExited) {
            $qemuChildren = Get-CimInstance Win32_Process -Filter "ParentProcessId=$($proc.Id)" -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -match 'qemu-system' }
            foreach ($child in $qemuChildren) {
                Write-Host "Killing qemu-system child process (PID $($child.ProcessId))..." -ForegroundColor Yellow
                Stop-Process -Id $child.ProcessId -Force -ErrorAction SilentlyContinue
            }
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        }
        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match 'qemu-system' -and $_.CommandLine -match [regex]::Escape($AvdName) } |
            ForEach-Object {
                Write-Host "Killing orphaned qemu-system process for $AvdName (PID $($_.ProcessId))..." -ForegroundColor Yellow
                Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
            }
        Start-Sleep 2
        Clear-EmulatorStaleLocks -AvdName $AvdName
        $fallbackArgs = $emuArgs + "-no-snapshot-load"
        $proc = Start-Process -FilePath $emu -ArgumentList $fallbackArgs -WindowStyle Minimized -PassThru
        & $adb wait-for-device
    }

    do { Start-Sleep 2; $b = (& $adb shell getprop sys.boot_completed).Trim() } while ($b -ne "1")
    Write-Host "Emulator booted." -ForegroundColor Green
    if ($WritableSystem) {
        # Автовызов сразу после boot_completed этого же старта — гарантированно
        # чистая загрузка (install-mitm-ca.sh рассчитан именно на неё: повторный
        # прогон без перезагрузки эмулятора копит tmpfs-mount'ы, см. шапку скрипта).
        # Поэтому идемпотентность обеспечивается местом вызова, а не самим скриптом:
        # Install-MitmCA здесь вызывается ровно один раз за один буд эмулятора.
        Write-Host "Installing mitmproxy CA (writable-system boot)..." -ForegroundColor Cyan
        Install-MitmCA
    }
}

function Install-MitmCA {
    # Ставит CA mitmproxy в системное хранилище доверия Android (scripts/install-mitm-ca.sh,
    # docs/environment-setup.md, раздел replay). Требует чистую загрузку -writable-system
    # эмулятора (см. Start-Emulator) — сам скрипт рассчитан ровно на неё.
    $caPem = "$env:USERPROFILE\.mitmproxy\mitmproxy-ca-cert.pem"
    if (-not (Test-Path $caPem)) {
        throw "CA PEM не найден: $caPem - сначала запусти mitmdump (он генерирует CA при первом старте), затем повтори Install-MitmCA."
    }
    $env:ADB = "$env:ANDROID_HOME\platform-tools\adb.exe"
    # git-bash ПЕРВЫМ, Get-Command — фолбэком (ESC-009, 2026-07-30): Get-Command bash
    # на этом хосте резолвится в WSL-шим C:\Windows\system32\bash.exe, который при
    # сломанной/отсутствующей WSL-дистрибуции падает "execvpe(/bin/bash) failed" —
    # скрипт написан под git-bash (MSYS-пути, cygpath), WSL ему и не подходит.
    $bash = "C:\Program Files\Git\bin\bash.exe"
    if (-not (Test-Path $bash)) { $bash = (Get-Command bash -ErrorAction SilentlyContinue).Source }
    if (-not $bash -or -not (Test-Path $bash)) { throw "bash.exe не найден (ни по каноническому пути C:\Program Files\Git\bin\bash.exe, ни в PATH), Install-MitmCA требует git-bash." }
    # Проба живости резолвнутого bash ДО запуска скрипта: WSL-шим проходит Test-Path,
    # но не исполняет ничего — ловим это здесь с внятным диагнозом, а не кодом 1 скрипта.
    $probe = (& $bash -c "echo BASH_PROBE_OK" 2>&1) -join "`n"
    if ($probe -notmatch "BASH_PROBE_OK") { throw "bash по пути $bash не исполняет команды (вероятно WSL-шим вместо git-bash): $probe" }
    & $bash "$root\scripts\install-mitm-ca.sh"
    $code = $LASTEXITCODE
    if ($code -ne 0) { throw "install-mitm-ca.sh завершился с кодом $code" }
}

function Start-Appium {
    param([int]$TimeoutSeconds = 60)
    Push-Location "$root\tools\appium"
    # "npx" (без расширения) через Start-Process на некоторых машинах резолвится не в
    # npx.cmd, а в постороннюю ShellExecute-ассоциацию (наблюдалось: открывался Notepad).
    # npx.cmd — однозначный путь к реальному исполняемому файлу.
    Start-Process -FilePath "npx.cmd" `
        -ArgumentList "appium","--log-level","warn","--allow-insecure","uiautomator2:chromedriver_autodownload" `
        -WindowStyle Minimized
    Pop-Location
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        Start-Sleep 2
        try { $ready = (Invoke-WebRequest -Uri "http://127.0.0.1:4723/status" -UseBasicParsing -TimeoutSec 3).Content -match '"ready":true' } catch { $ready = $false }
    } while (-not $ready -and (Get-Date) -lt $deadline)
    if (-not $ready) { throw "Appium not ready after ${TimeoutSeconds}s (http://127.0.0.1:4723/status)" }
    Write-Host "Appium started and ready on :4723" -ForegroundColor Green
}

function Stop-NodeProcesses {
    # AT-BUG-031: голый `Get-Process node` матчил ЛЮБОЙ node.exe в системе по
    # имени, без проверки владения - на этом (разделяемом) хосте одновременно
    # может крутиться другой проект со своими node-процессами (наблюдалось:
    # D:\AI CRM\govard-crm, ~20 node.exe), и вызов этой функции убил бы их
    # коллатерально. Сужаем до процессов, реально принадлежащих AO3-обвязке:
    # матчим по командной строке (Get-CimInstance Win32_Process) на путь этого
    # репозитория ($root). Start-Appium запускает appium из
    # "$root\tools\appium" через локальный node_modules, поэтому дочерний
    # worker-процесс (.../tools/appium/node_modules/appium/index.js) несёт
    # $root в командной строке.
    #
    # AT-BUG-031 attempt 2 (critic-доработка, 2026-07-29): appium запускает
    # node-обёртку (npx) и node-воркер; достаточно остановить воркер
    # (совпадает по $root в командной строке) - обёртка завершается сама
    # вслед за смертью дочернего процесса (эмпирически проверено). Раньше
    # здесь был отдельный шаг "убить родителя воркера по ParentProcessId" с
    # комментарием, что npx-launcher является РОДИТЕЛЕМ воркера - critic
    # живым замером PPID (Get-CimInstance Win32_Process) это опроверг:
    # фактический родитель appium-воркера - промежуточный cmd.exe, не
    # npx-node напрямую, поэтому шаг матчился ("parents matched as
    # node.exe") НОЛЬ раз и был мёртвым кодом. Единственный теоретически
    # достижимый эффект мёртвой ветки - убийство ПОСТОРОННЕГО node.exe,
    # если он случайно унаследует переиспользованный PID мёртвого
    # cmd.exe-родителя - тот самый класс риска, против которого заведён этот
    # баг. Убрано целиком; страховка не нужна - цепочка npx-launcher сама
    # завершается, когда её дочерний appium-воркер убит (critic проверил
    # живым прогоном: адресный Stop-Process только owned-PID схлопнул всю
    # цепочку, :4723 ушёл в DOWN).
    if (-not $root -or -not (Test-Path $root)) {
        throw "Stop-NodeProcesses: `$root пуст или недействителен ('$root') - отказ убивать node-процессы вслепую (AT-BUG-031: [regex]::Escape('') заматчил бы ЛЮБУЮ командную строку)."
    }
    $allNode = Get-CimInstance Win32_Process -Filter "Name='node.exe'" -ErrorAction SilentlyContinue
    $owned = @($allNode | Where-Object { $_.CommandLine -and $_.CommandLine -match [regex]::Escape($root) })
    # Батч мелочей D-0081 (2026-07-29): раньше при 0 owned печатались ОБА
    # сообщения ("No AO3 node processes found..." И "Stopped 0 AO3 node
    # process(es)." следом) - одно сообщение на исход (if/else), функция и
    # порядок Stop-Process/Start-Sleep не тронуты.
    if ($owned.Count -eq 0) {
        Write-Host "No AO3 node processes found (nothing to stop)." -ForegroundColor Yellow
    } else {
        foreach ($p in $owned) {
            Write-Host "Stopping AO3 node process (PID $($p.ProcessId)): $($p.CommandLine)" -ForegroundColor Yellow
            Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
        }
        Write-Host "Stopped $($owned.Count) AO3 node process(es)." -ForegroundColor Green
    }
    Start-Sleep 1
}

function Wait-PackageServiceReady {
    # AT-BUG-013: sys.boot_completed=1 (см. Start-Emulator) НЕ гарантирует, что
    # гостевой package-сервис уже поднялся - Install-App сразу после буда может
    # словить `cmd: Can't find service: package`, хотя устройство по Get-Device
    # уже есть. Фактический сигнал готовности - устойчивый непустой ответ
    # `pm path android` (пустой вывод/ошибка = сервис ещё не готов). Короткий
    # поллинг с таймаутом, явное предупреждение при неудаче - НЕ молчаливый
    # бесконечный retry: вызывающий код (Install-App) сам решает, продолжать ли.
    param([int]$TimeoutSec = 30)
    $adb = "$env:ANDROID_HOME\platform-tools\adb.exe"
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    $ready = $false
    do {
        $out = & $adb shell pm path android 2>$null
        if ($out -and (($out -join "") -match 'package:')) { $ready = $true; break }
        Start-Sleep 1
    } while ((Get-Date) -lt $deadline)
    if (-not $ready) {
        Write-Warning ("Wait-PackageServiceReady: package-сервис гостя не ответил за ${TimeoutSec}s " +
            "('pm path android' пуст/ошибка) - AT-BUG-013: следующий Install-App может упасть " +
            "'cmd: Can't find service: package'.")
    }
    return $ready
}

function Install-App {
    # AT-BUG-013: короткое ожидание готовности package-сервиса перед первой
    # попыткой install - гонка с boot_completed=1 (см. Wait-PackageServiceReady).
    param([int]$PackageServiceTimeoutSec = 30)
    Wait-PackageServiceReady -TimeoutSec $PackageServiceTimeoutSec | Out-Null
    & "$env:ANDROID_HOME\platform-tools\adb.exe" install -r "$root\app-under-test\app\build\outputs\apk\debug\app-debug.apk"
}

function Invoke-Smoke {
    Push-Location "$root\framework"
    $env:AO3_MODE = "live"
    & "$venv\python.exe" -m pytest -m p0 @args
    Pop-Location
}

function Invoke-Suite {
    param([string]$Mark = "p0")
    Push-Location "$root\framework"
    & "$venv\python.exe" -m pytest -m $Mark @args
    Pop-Location
}

function Invoke-Pytest {
    # Каноничный запуск произвольных pytest-аргументов из framework/ (venv-python).
    # Агентам НЕ собирать свои вариации ". env.ps1; <путь к python> -m pytest ..." —
    # каждая новая форма не совпадает с allowlist и требует подтверждения.
    Push-Location "$root\framework"
    if (-not $env:AO3_MODE) { $env:AO3_MODE = "live" }
    & "$venv\python.exe" -m pytest @args
    $code = $LASTEXITCODE
    Pop-Location
    Write-Host "PYTEST_EXIT=$code"
}

function Show-Report {
    Push-Location "$root\framework"
    & "$venv\python.exe" -m allure serve allure-results 2>$null
    Pop-Location
}

function Get-Device {
    # Однозначная проверка присутствия устройства. Полный путь к adb.exe — НЕ зависит
    # от PATH, поэтому работает даже там, где голый `adb` не резолвится. Печатает по
    # строке "DEVICE: <serial>" на каждое устройство в состоянии `device`, либо ровно
    # "NO DEVICE". ВАЖНО (CLAUDE.md permission-hygiene п.6): пустой/ошибочный вывод
    # голого `adb` вне PATH НЕЛЬЗЯ принимать за «устройства нет» — эта функция даёт
    # однозначный сигнал, используй её для любого вывода о присутствии устройства.
    $lines = & "$env:ANDROID_HOME\platform-tools\adb.exe" devices
    $serials = @($lines | Select-Object -Skip 1 |
        Where-Object { $_ -match '\sdevice$' } |
        ForEach-Object { ($_ -split '\s+')[0] })
    if ($serials.Count -gt 0) { foreach ($s in $serials) { Write-Host "DEVICE: $s" } }
    else { Write-Host "NO DEVICE" }
}

Write-Host "Tasks loaded: Start-Emulator, Install-MitmCA, Start-Appium, Stop-NodeProcesses, Install-App, Invoke-Smoke, Invoke-Suite, Invoke-Pytest, Show-Report, Get-Device" -ForegroundColor Green
