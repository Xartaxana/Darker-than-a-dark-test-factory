# Раннеры тестового фреймворка. Использование:
#   . D:\AO3_tests\scripts\tasks.ps1
#   Start-Emulator ; Start-Appium ; Invoke-Smoke
# Требует предварительно: . D:\AO3_tests\scripts\env.ps1 (для JAVA_HOME/ANDROID_HOME/PATH)
$ErrorActionPreference = "Stop"
# $root — от местоположения ЭТОГО файла (родитель scripts\), а не литералом:
# литерал D:\AO3_tests заставлял копию из git-worktree молча исполнять главный
# чекаут (Push-Location в чужой framework\ => witness воркера недействителен).
# Фолбэк на литерал — только для экзотики без $PSScriptRoot (вставка в консоль).
$root = if ($PSScriptRoot) { Split-Path -Parent $PSScriptRoot } else { "D:\AO3_tests" }
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

function Get-AdbOutput {
    # Хелпер для Set-GuestIPv4Pin: инкапсулирует null-safe .Trim() (B1
    # критик-вход attempt 2, 2026-08-03) - голый `(& $adb ...).Trim()` падает
    # на $null-выводе (та же ловушка, что существующий `.Trim()` в
    # снапшот-буд-цикле Start-Emulator, ниже - сиблинг, вне скоупа этой
    # правки, см. отчёт). `2>$null` не сливает stderr в возвращаемое значение.
    param([Parameter(Mandatory)][string]$Adb, [Parameter(Mandatory)][string[]]$AdbArgs)
    $out = & $Adb @AdbArgs 2>$null
    if ($null -eq $out) { return "" }
    return (($out | Out-String)).Trim()
}

function Set-GuestIPv4Pin {
    # env-ipv4-pin-0803 (решение владельца 2026-08-03): фабрика использует IPv4,
    # IPv6-транзит хоста флапает как чёрная дыра (ESC-009/014/015, state/escalations.md).
    # Хостовая половина уже IPv4-first (netsh prefix policies), но гостевой
    # Android/Chromium эмулятора этой политике не подчиняется — сам резолвит и
    # предпочитает IPv6, зависая на мёртвом транзите (ESC-015: `driver.get()`
    # виснет в WebView, пока Chromium ждёт мёртвый AAAA-маршрут). Образ рутован —
    # пиним гостя на IPv4 sysctl'ом через adb; пин НЕ переживает ребут/новый буд,
    # поэтому вызывается из Start-Emulator при КАЖДОМ подъёме, не один раз.
    # Не блокирующий: отказ пина (не-root образ / sysctl недоступен) не валит
    # подъём эмулятора — печатается WARNING, разбор — доктору/человеку (doctor.py).
    #
    # Вынесена в отдельную функцию (критик-вход attempt 2, B1): тестируется
    # изолированно стабом $Adb, без запуска реального эмулятора.
    #
    # B1 (БЛОКЕР attempt 1): под глобальным $ErrorActionPreference='Stop'
    # (строка 5) ЛЮБАЯ stderr-строка нативной команды через `2>&1` становится
    # завершающей NativeCommandError — ветка WARNING была НЕДОСТИЖИМА, отказ
    # пина рвал весь Start-Emulator ПОСЛЕ бута и ДО Install-MitmCA. Локальный
    # $ErrorActionPreference='Continue' на время этой функции (try/finally,
    # восстановление гарантировано) + `2>$null` вместо `2>&1` (не сливаем
    # stderr в возвращаемое значение) устраняют оба пути падения.
    param([Parameter(Mandatory)][string]$Adb)

    Write-Host "Pinning guest to IPv4 (disabling guest IPv6, ESC-015)..." -ForegroundColor Cyan
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $suPrefix = $null
        $adbRootedByUs = $false

        $suOut = Get-AdbOutput -Adb $Adb -AdbArgs @("shell", "su 0 id")
        if ($suOut -match 'uid=0') {
            $suPrefix = "su 0 "
        } else {
            # su недоступен напрямую - пробуем adb root (некоторые сборки требуют
            # перевода adbd в root-режим отдельно от su-бинарника гостя) и повтор.
            Get-AdbOutput -Adb $Adb -AdbArgs @("root") | Out-Null
            Start-Sleep 2
            & $Adb wait-for-device 2>$null
            # B2 (критик-вход attempt 2): предикат ПОСЛЕ adb root — голый `id`,
            # НЕ `su 0 id`. Если adbd рутован, а su-бинаря в образе нет, `su 0 id`
            # ложно провалился бы, хотя пин уже возможен напрямую без su, и adbd
            # остался бы root на всю сессию без надобности (см. adbRootedByUs/unroot
            # ниже).
            $idOut = Get-AdbOutput -Adb $Adb -AdbArgs @("shell", "id")
            if ($idOut -match 'uid=0') {
                $suPrefix = ""
                $adbRootedByUs = $true
            }
        }

        if ($null -eq $suPrefix) {
            Write-Warning "WARNING: guest IPv6 pin FAILED (su 0 недоступен и adb root не дал uid=0 - образ не рутован)."
            return
        }

        Get-AdbOutput -Adb $Adb -AdbArgs @("shell", "${suPrefix}sysctl -w net.ipv6.conf.all.disable_ipv6=1") | Out-Null
        Get-AdbOutput -Adb $Adb -AdbArgs @("shell", "${suPrefix}sysctl -w net.ipv6.conf.default.disable_ipv6=1") | Out-Null
        # Находка живой верификации attempt 2 (2026-08-03, полный холодный рестарт с
        # новым кодом): `all`/`default` НЕ гарантируют per-interface эффект на этом
        # AVD — `conf/wlan0/disable_ipv6` наблюдался снова 0 через ~секунды-десятки
        # секунд ПОСЛЕ успешного пина `all`/`default` (Android netd/Wi-Fi-фреймворк,
        # похоже, переустанавливает его при обычной сетевой реинициализации), пока
        # `all`/`eth0`/прочие интерфейсы оставались 1 - `ip -6 addr` снова показывал
        # `inet6`-строки НА wlan0. Явный цикл по КАЖДОМУ `/proc/sys/net/ipv6/conf/*/
        # disable_ipv6` (включая wlan0 индивидуально) эмпирически устойчив (проверено
        # ожиданием 55с+ после установки - не откатывается).
        $suPrefixTrimmed = $suPrefix.Trim()
        $loopCmd = if ($suPrefixTrimmed) {
            "$suPrefixTrimmed sh -c 'for f in /proc/sys/net/ipv6/conf/*/disable_ipv6; do echo 1 > `$f; done'"
        } else {
            "sh -c 'for f in /proc/sys/net/ipv6/conf/*/disable_ipv6; do echo 1 > `$f; done'"
        }
        Get-AdbOutput -Adb $Adb -AdbArgs @("shell", $loopCmd) | Out-Null

        $disabled = Get-AdbOutput -Adb $Adb -AdbArgs @("shell", "cat /proc/sys/net/ipv6/conf/all/disable_ipv6")

        # Сверка ЭФФЕКТОМ (CLAUDE.md permission-hygiene п.6), не наличием команды:
        # disable_ipv6=1 обязан снять ВСЕ гостевые IPv6-адреса интерфейсов (проверено
        # эмпирически на ao3_test_api34: до пина `ip -6 addr` несёт site/link-scope
        # адреса на eth0/wlan0/dummy0 - НЕ "scope global", этот AVD никогда не
        # показывает global-scope IPv6).
        # B3 (критик-вход attempt 2): критерий — отсутствие строк, матчащих
        # `inet6\s` (не общая пустота вывода целиком) - другой образ/версия
        # iproute2 может печатать интерфейсные заголовки без адресных строк,
        # что сделало бы пустоту-всего-вывода хрупким критерием (вечный
        # ложный WARNING). WARNING-текст разведён по фактической причине.
        $addrOut = Get-AdbOutput -Adb $Adb -AdbArgs @("shell", "ip -6 addr")
        $inet6Lines = @($addrOut -split "`r?`n" | Where-Object { $_ -match 'inet6\s' })

        if ($disabled -eq "1" -and $inet6Lines.Count -eq 0) {
            Write-Host "guest IPv6: disabled (pin OK)" -ForegroundColor Green
        } elseif ($disabled -ne "1") {
            Write-Warning "WARNING: guest IPv6 pin FAILED (disable_ipv6='$disabled', sysctl не применился)."
        } else {
            Write-Warning ("WARNING: guest IPv6 pin FAILED (disable_ipv6=1, но остались inet6-адреса: " +
                ($inet6Lines -join " | ") + ")")
        }

        if ($adbRootedByUs) {
            # B2: root поднимали ТОЛЬКО ради пина - возвращаем adbd в исходный
            # (не-root) режим, чтобы не менять семантику последующих
            # Install-App/прогонов на этой сессии.
            & $Adb unroot 2>$null | Out-Null
            Start-Sleep 1
            & $Adb wait-for-device 2>$null
        }
    } finally {
        $ErrorActionPreference = $prevEap
    }
}

function Set-EmulatorSessionState {
    # AT-BUG-063 (F1/F4, rework attempt 2, критик-вход): единственное место,
    # где device-liveness recovery (`framework/core/driver_factory.py`) может
    # узнать, каким GPU-бэкендом/AVD эмулятор был поднят ИЗНАЧАЛЬНО -- в т.ч.
    # когда `-Gpu`/`-AvdName` переданы ЯВНЫМ CLI-параметром МИМО переменной
    # окружения (исходный воспроизведённый сценарий RUN-20260811-0405, который
    # attempt 1 не закрыл -- та правка полагалась ТОЛЬКО на `$env:AO3_EMU_GPU`,
    # унаследованный python-подпроцессом, и никогда не видела явный `-Gpu host`
    # ручного вызова). Вызывается из `Start-Emulator` СРАЗУ ПОСЛЕ разрешения
    # `$Gpu` (параметр > env > дефолт, комментарий выше) -- пишет уже
    # РАЗРЕШЁННОЕ значение, не сырой параметр. Не блокирующая: ошибка записи
    # (нет прав/диска) не должна ронять сам Start-Emulator -- WARN и
    # продолжение, тот же класс отказоустойчивости, что Set-GuestIPv4Pin выше.
    param([Parameter(Mandatory)][string]$Gpu, [Parameter(Mandatory)][string]$AvdName)
    try {
        $stateDir = "$root\state"
        if (-not (Test-Path $stateDir)) { New-Item -ItemType Directory -Path $stateDir -Force | Out-Null }
        $payload = [ordered]@{
            gpu         = $Gpu
            avd_name    = $AvdName
            updated_utc = (Get-Date).ToUniversalTime().ToString("o")
        } | ConvertTo-Json -Compress
        # `Set-Content -Encoding UTF8` в Windows PowerShell 5.1 пишет UTF-8 С BOM --
        # найдено красной пробой AT-BUG-063 attempt 2: `json.loads` на python-стороне
        # (`driver_factory._read_emulator_session_state`) падал
        # `JSONDecodeError: Unexpected UTF-8 BOM` на РЕАЛЬНО записанном файле.
        # `[System.IO.File]::WriteAllText` с явным `UTF8Encoding($false)` пишет
        # БЕЗ BOM.
        $utf8NoBom = New-Object System.Text.UTF8Encoding $false
        [System.IO.File]::WriteAllText("$stateDir\emulator-session.json", $payload, $utf8NoBom)
    } catch {
        Write-Warning "WARNING: emulator-session.json state write failed ($_) - device-liveness recovery may fall back to defaults (AT-BUG-063)."
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
    # AT-BUG-063: фиксируем РАЗРЕШЁННЫЕ (пост-фолбэк) значения -- это единственный
    # момент, когда известно фактическое намерение вызова (CLI-параметр, env-переменная
    # или дефолт), см. Set-EmulatorSessionState выше.
    Set-EmulatorSessionState -Gpu $Gpu -AvdName $AvdName
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

    Set-GuestIPv4Pin -Adb $adb

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

function Ensure-BridgeHarness {
    # spec-p2-pyramid-bridge N5 (docs/tasks/p2-pyramid-bridge.md Р3, B7):
    # bootstrap харнесса L2 bridge (framework/bridge_harness/ — device-free
    # jsdom контракт-тесты ao3_bridge.js, framework/tests/bridge/). Дом
    # версионируется (package.json + package-lock.json коммитятся,
    # node_modules/ в .gitignore, B1 — tools/ в .gitignore не годится, класс
    # t-155) — эта функция ставит зависимости (`npm ci`, детерминированный
    # install из lock-файла) ТОЛЬКО когда node_modules отсутствует, идемпотентна
    # при повторных вызовах.
    #
    # Отсутствие node в PATH — явный отказ с инструкцией, НЕ молчаливый skip
    # (DoD N5: "Отсутствие node/jsdom при p1-прогоне = ЖЁСТКИЙ отказ с
    # сообщением-инструкцией"): этой же диагностике вторит conftest.py
    # framework/tests/bridge/ на случай, если харнесс НЕ был поднят перед
    # прогоном (вызов этой функции пропущен) — двойная страховка одного факта,
    # не дублирование логики (PS печатает инструкцию, Python поднимает
    # RuntimeError на пути прогона теста).
    $harnessDir = "$root\framework\bridge_harness"
    if (-not (Test-Path $harnessDir)) {
        throw "Ensure-BridgeHarness: $harnessDir не найден - дерево репозитория повреждено или framework/bridge_harness/ не склонирован."
    }
    $node = Get-Command node -ErrorAction SilentlyContinue
    if (-not $node) {
        throw "Ensure-BridgeHarness: node не найден в PATH - bridge-harness (L2, docs/tasks/p2-pyramid-bridge.md) требует Node.js. Установи Node.js (https://nodejs.org/) и повтори."
    }
    $jsdomMarker = "$harnessDir\node_modules\jsdom\package.json"
    if (Test-Path $jsdomMarker) {
        Write-Host "Bridge harness: node_modules/jsdom уже установлен (Ensure-BridgeHarness no-op)." -ForegroundColor Green
        return
    }
    Write-Host "Bridge harness: node_modules отсутствует - выполняю npm ci в $harnessDir..." -ForegroundColor Cyan
    Push-Location $harnessDir
    try {
        & npm ci
        $code = $LASTEXITCODE
        if ($code -ne 0) { throw "Ensure-BridgeHarness: npm ci завершился с кодом $code в $harnessDir." }
    } finally {
        Pop-Location
    }
    if (-not (Test-Path $jsdomMarker)) {
        throw "Ensure-BridgeHarness: npm ci завершился успешно, но $jsdomMarker всё ещё отсутствует - проверь вывод npm выше."
    }
    Write-Host "Bridge harness: jsdom установлен." -ForegroundColor Green
}

function Start-Appium {
    # F1 (spec F v2, критик-фиксы норматив): резидентный guard — на :4723 может уже
    # жить чужой/долгоживущий Appium (фабрика). Порт занят -> NO-OP по умолчанию,
    # печать диагностики владельца, новый процесс НЕ стартуем. -Restart гасит
    # ТОЛЬКО процесс, чей CommandLine содержит $root (зеркало проверки владения
    # Stop-NodeProcesses выше, урок AT-BUG-031) - чужой владелец не гасится.
    param([int]$TimeoutSeconds = 60, [switch]$Restart)

    # Первым шагом - однозначный владелец порта. -State Listen обязателен: без
    # него Get-NetTCPConnection на :4723 отдаёт 2+ строк (Established и т.п.) и
    # ломает WQL-фильтр ниже (критик-замер). Имя переменной - $ownerPid, НЕ $pid
    # ($pid - read-only automatic variable, присваивание падает под
    # $ErrorActionPreference='Stop').
    $ownerPid = Get-NetTCPConnection -LocalPort 4723 -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty OwningProcess

    if ($ownerPid) {
        $ownerProc = Get-CimInstance Win32_Process -Filter "ProcessId=$ownerPid" -ErrorAction SilentlyContinue

        if ($Restart) {
            if ($ownerProc -and $ownerProc.CommandLine -and $ownerProc.CommandLine -match [regex]::Escape($root)) {
                $killedPid = $ownerPid
                $killedCommandLine = $ownerProc.CommandLine
                Write-Host "Start-Appium -Restart: останавливаю владельца :4723 (PID $killedPid, наш процесс)..." -ForegroundColor Yellow
                # F2-B1 (критик-вход): БЕЗ -ErrorAction SilentlyContinue - под глобальным
                # $ErrorActionPreference='Stop' (строка 5) отказ Stop-Process (нет прав,
                # процесс уже не тот PID и т.п.) обязан прервать функцию, не потеряться.
                Stop-Process -Id $killedPid -Force
                # Не верим килу на слово Start-Sleep'ом фиксированной длины - опрашиваем
                # владельца порта до пустоты с дедлайном. Закрывает невидимый EADDRINUSE
                # свежего npx, если процесс не успел освободить сокет (F2-F4).
                $killDeadline = (Get-Date).AddSeconds(15)
                do {
                    Start-Sleep -Milliseconds 500
                    $stillOwner = Get-NetTCPConnection -LocalPort 4723 -State Listen -ErrorAction SilentlyContinue |
                        Select-Object -First 1 -ExpandProperty OwningProcess
                } while ($stillOwner -and (Get-Date) -lt $killDeadline)
                if ($stillOwner) {
                    throw "Start-Appium -Restart: PID $killedPid ($killedCommandLine) не отпустил :4723 за 15с после Stop-Process - порт всё ещё занят."
                }
                $ownerPid = $null
                # падает сквозь if в свежий старт ниже
            } else {
                throw "владелец :4723 не наш (CommandLine не содержит `$root) - гасить отказываюсь."
            }
        } else {
            if ($ownerProc) {
                $uptime = (Get-Date) - $ownerProc.CreationDate
                Write-Host ("Appium уже слушает :4723 - PID $ownerPid, запущен $($ownerProc.CreationDate), " +
                    "uptime $uptime") -ForegroundColor Yellow
            } else {
                Write-Host "порт 4723 занят, владелец не резолвится (чужой/проброшенный сервер)" -ForegroundColor Yellow
            }
            # F2-B2 (критик-вход): восстанавливаем контракт функции "/status ready либо
            # throw" на резидентном пути тоже - один inline shallow-опрос (НЕ -Deep -
            # деградировавший резидент не трогаем сессиями чужого прогона).
            try {
                $residentReady = (Invoke-WebRequest -Uri "http://127.0.0.1:4723/status" -UseBasicParsing -TimeoutSec 5).Content -match '"ready":true'
            } catch {
                $residentReady = $false
            }
            if ($residentReady) {
                Write-Host "резидентный, /status ready" -ForegroundColor Green
                return
            } else {
                throw "резидентный, /status НЕ отвечает - процесс жив, сервер мёртв; перезапуск: Start-Appium -Restart"
            }
        }
    }

    # Свежий старт (порт свободен, либо -Restart легально освободил его выше).
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
    # /status отвечает и у деградировавшего сервера (класс AT-BUG-064/NoSuchDriverError) -
    # "ready" здесь означает только HTTP-готовность, НЕ здоровье сессии.
    Write-Host "Appium started, /status ready (здоровье НЕ проверено - Test-AppiumHealthy -Deep)" -ForegroundColor Green
}

function Get-DeviceSerials {
    # F2-F2 (критик-вход): общий оракул присутствия устройства - раньше дословно
    # дублировался в Get-Device и Test-AppiumHealthy -Deep. Полный путь к adb.exe -
    # НЕ зависит от PATH. Возвращает массив серийников в состоянии `device` (может
    # быть пустым массивом) - НЕ печатает ничего, форму вывода решает вызывающий код.
    # F2-F1: try/catch - под глобальным $ErrorActionPreference='Stop' отсутствие
    # adb.exe (нативная команда не резолвится) кидает терминирующее исключение, а
    # не даёт пустой $lines - без catch это ломает контракт "пустой массив = нет
    # устройств" у ОБОИХ вызывающих (Get-Device и Test-AppiumHealthy -Deep).
    try {
        $lines = & "$env:ANDROID_HOME\platform-tools\adb.exe" devices
    } catch {
        Write-Warning "Get-DeviceSerials: вызов adb devices упал ($_) - ANDROID_HOME/adb.exe недоступен?"
        return @()
    }
    return @($lines | Select-Object -Skip 1 |
        Where-Object { $_ -match '\sdevice$' } |
        ForEach-Object { ($_ -split '\s+')[0] })
}

function Test-AppiumHealthy {
    # F2 (spec F v2, критик-фиксы норматив): двухслойная проверка здоровья
    # Appium-сервера.
    # (а) shallow - HTTP GET /status: код 200 и value.ready=true. Достаточно
    #     часто (дёшево), но НЕ ловит класс AT-BUG-064/NoSuchDriverError -
    #     сервер отвечает ready=true, а реальная сессия падает.
    # (б) -Deep - создаёт и тут же удаляет РЕАЛЬНУЮ сессию (минимальные caps
    #     платформы Android/UiAutomator2, зеркало framework/config/capabilities.py
    #     и framework/config/settings.py DEVICE_NAME/PLATFORM_VERSION дефолтов -
    #     без app_package/app_activity). Deep требует живого устройства - без
    #     него ловить нечего, поэтому при NO DEVICE deep-слой пропускается явно
    #     (НЕ тихо считается провалом).
    #     F2-B5 (критик-вход): -Deep ТРЕБУЕТ СВОБОДНОГО устройства - на нём НЕ
    #     должна идти чужая сессия/сьют. Ответственность за это - на ВЫЗЫВАЮЩЕМ
    #     коде, функция это НЕ проверяет и проверить не может (никакого способа
    #     отличить "устройство свободно" от "чужая UIA2-сессия сейчас активна"
    #     через ADB). Вторая UIA2-сессия на занятом устройстве рвёт чужой прогон
    #     (правило 4 CLAUDE.md, общий ресурс с глобальным побочным эффектом).
    #     Утверждение "ничего не запускает на устройстве, только присоединяется"
    #     из ПРЕДЫДУЩЕЙ редакции СНЯТО как непроверенное: создание UIA2-сессии
    #     без app-capability поднимает io.appium.settings / UIA2-сервер на
    #     устройстве - это ОЦЕНКА, не проверено живым замером (владение :4723
    #     у фабрики, live-Deep на приёмке Lead).
    # F2-B3/B4 (критик-вход): POST /session - таймаут $SessionTimeoutSec (дефолт
    #     120с, зеркало settings.APPIUM_HTTP_TIMEOUT: холодная докачка
    #     chromedriver/создание сессии по дефолтам занимает 60-90с) + ОДНА
    #     повторная попытка с backoff $backoffSec между попытками (см. ниже) -
    #     первая попытка легитимно может упасть settle-классом (AT-BUG-026,
    #     `Appium Settings app is not running after 30000ms` сразу после
    #     recovery/раннего старта устройства) - отказ ПЕРВОЙ попытки НЕ вердикт,
    #     отказ ОБЕИХ попыток - вердикт FAILED.
    # Возвращает $true/$false; диагностика - в вывод (Write-Host/Write-Warning),
    # не только в возврат - вызывающий код видит причину без доп. запросов.
    param([switch]$Deep, [string]$AppiumUrl = "http://127.0.0.1:4723", [int]$SessionTimeoutSec = 120)

    $shallowOk = $false
    try {
        $resp = Invoke-WebRequest -Uri "$AppiumUrl/status" -UseBasicParsing -TimeoutSec 5
        $json = $resp.Content | ConvertFrom-Json
        $shallowOk = ($resp.StatusCode -eq 200) -and ($json.value.ready -eq $true)
    } catch {
        Write-Warning "Test-AppiumHealthy: /status запрос не удался ($_)."
        $shallowOk = $false
    }

    if (-not $shallowOk) {
        Write-Host "Test-AppiumHealthy: FAILED (shallow, /status не ready)" -ForegroundColor Red
        return $false
    }

    if (-not $Deep) {
        Write-Host "Test-AppiumHealthy: OK (shallow, /status ready=true)" -ForegroundColor Green
        return $true
    }

    $serials = Get-DeviceSerials
    if ($serials.Count -eq 0) {
        Write-Host "Test-AppiumHealthy: deep-слой пропущен: NO DEVICE (shallow OK)" -ForegroundColor Yellow
        return $true
    }

    # Мин. caps - зеркало framework/config/settings.py (DEVICE_NAME дефолт
    # "emulator-5554", PLATFORM_VERSION="" = любой) без обращения к Python.
    $deviceName = if ($env:AO3_DEVICE) { $env:AO3_DEVICE } else { "emulator-5554" }
    $platformVersion = $env:AO3_PLATFORM_VERSION
    $caps = [ordered]@{
        platformName             = "Android"
        "appium:automationName"  = "UiAutomator2"
        "appium:deviceName"      = $deviceName
        "appium:newCommandTimeout" = 30
    }
    if ($platformVersion) { $caps["appium:platformVersion"] = $platformVersion }
    $body = @{ capabilities = @{ alwaysMatch = $caps; firstMatch = @(@{}) } } | ConvertTo-Json -Depth 6

    # F2-B4: backoff зеркалит framework/core/driver_factory.py::_SETTLE_RETRY_BACKOFF
    # (реальное значение константы - 15.0с, не приблизительная цифра из устной
    # спеки; сверено чтением driver_factory.py по правилу builder-роли п.3 -
    # реальность/эмпирика приоритетнее устного приближения).
    $backoffSec = 15
    $maxAttempts = 2
    $sessionId = $null
    $created = $false
    $lastCreateErr = $null
    for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
        try {
            $createResp = Invoke-WebRequest -Uri "$AppiumUrl/session" -Method Post -Body $body `
                -ContentType "application/json" -TimeoutSec $SessionTimeoutSec -UseBasicParsing
            $createJson = $createResp.Content | ConvertFrom-Json
            $sessionId = $createJson.value.sessionId
            if (-not $sessionId) { $sessionId = $createJson.sessionId }
            if ($sessionId) {
                $created = $true
                Write-Host "Test-AppiumHealthy: deep-слой - сессия создана (id $sessionId, попытка $attempt/$maxAttempts)" -ForegroundColor Green
                break
            }
            $lastCreateErr = "сессия создана, но sessionId в ответе не найден"
        } catch {
            $lastCreateErr = $_
        }
        if ($attempt -lt $maxAttempts) {
            Write-Warning ("Test-AppiumHealthy: deep-слой - попытка $attempt/$maxAttempts POST /session не удалась " +
                "($lastCreateErr) - settle-класс (AT-BUG-026), повтор через ${backoffSec}с...")
            Start-Sleep -Seconds $backoffSec
        }
    }
    if (-not $created) {
        Write-Warning "Test-AppiumHealthy: deep-слой FAILED - POST /session не удался за $maxAttempts попытки(у) ($lastCreateErr)."
        return $false
    }

    $deleted = $false
    try {
        Invoke-WebRequest -Uri "$AppiumUrl/session/$sessionId" -Method Delete -TimeoutSec 10 -UseBasicParsing | Out-Null
        $deleted = $true
        Write-Host "Test-AppiumHealthy: deep-слой - сессия $sessionId удалена" -ForegroundColor Green
    } catch {
        # F2-F3 (критик-вход): это НЕ "сервер нездоров" - сессия УЖЕ доказала
        # работоспособность (создание прошло). Отдельный, менее тревожный вердикт:
        # утечка сессии на очистке, не провал самого health-check'а сервера.
        Write-Warning ("Test-AppiumHealthy: deep-слой - сессия $sessionId создана (сервер работоспособен), " +
            "но DELETE не подтвердился ($_) - возможна утечка сессии, это НЕ вердикт 'сервер нездоров'.")
    }

    if ($created -and $deleted) {
        Write-Host "Test-AppiumHealthy: OK (deep, сессия создана и удалена)" -ForegroundColor Green
        return $true
    }
    return $false
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
    $rootMatched = @($allNode | Where-Object { $_.CommandLine -and $_.CommandLine -match [regex]::Escape($root) })
    # spec-p2-pyramid-bridge N5 (docs/tasks/p2-pyramid-bridge.md Р3/Р5, B7):
    # framework/bridge_harness/run_bridge.js лежит ПОД $root, поэтому подпроцесс
    # харнесса (по одному short-lived вызову на каждый bridge-тест,
    # framework/tests/bridge/conftest.py::_bridge_call_raw) МАТЧИТ $root тем же
    # regex'ом, что appium-воркер, и убивался бы этой функцией без явного
    # исключения — гоняющийся `Invoke-Pytest -m bridge` параллельно с
    # Stop-NodeProcesses (например, из другого шага конвейера) терял бы
    # результат теста. Исключаем по подстроке "bridge_harness" в CommandLine
    # (узкая, не общий "node_modules" и т.п. — не задевает appium-воркер).
    $owned = @($rootMatched | Where-Object { $_.CommandLine -notmatch 'bridge_harness' })
    $bridgeExcluded = @($rootMatched | Where-Object { $_.CommandLine -match 'bridge_harness' })
    if ($bridgeExcluded.Count -gt 0) {
        foreach ($p in $bridgeExcluded) {
            Write-Host "Skipping bridge-harness node process (PID $($p.ProcessId), N5 exclusion): $($p.CommandLine)" -ForegroundColor Cyan
        }
    }
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
    # C9/E1 (spec-build-source-dual-mode v4): -d (allow version downgrade) -
    # носитель принципа "любая установка при смене источника" в ШТАТНОМ пути,
    # закрывает ВСЕ вызывающие роли разом (test-runner, fix-verifier,
    # test-automator, run-suite, чартеры) без правки их промптов. Сборки
    # отладочные, pm сохраняет данные при -d.
    # B4 (критик-решение Lead, 2026-08-10): -d НЕ спасает от несовпадения
    # подписи (INSTALL_FAILED_UPDATE_INCOMPATIBLE) - живой замер builder-
    # смока показал, что CI-артефакт (провайдед) и local-сборка в этом
    # проекте подписаны РАЗНЫМИ debug-ключами (KEYSTORE_BASE64 не настроен
    # в .gitlab-ci.yml проекта) - переход provided<->local падает на этой
    # ошибке НЕЗАВИСИМО от -d. Fallback: детект строки в выводе adb ->
    # громкий WARN -> uninstall (пакет com.example.ao3_wrapper,
    # settings.py:24 APP_PACKAGE) -> повторный install.
    param([int]$PackageServiceTimeoutSec = 30)
    Wait-PackageServiceReady -TimeoutSec $PackageServiceTimeoutSec | Out-Null
    $apk = "$root\app-under-test\app\build\outputs\apk\debug\app-debug.apk"
    $adb = "$env:ANDROID_HOME\platform-tools\adb.exe"
    $out = & $adb install -r -d $apk 2>&1
    $out | ForEach-Object { Write-Output $_ }
    if (($out -join "`n") -match "INSTALL_FAILED_UPDATE_INCOMPATIBLE") {
        Write-Warning ("Install-App: подписи не совпадают (INSTALL_FAILED_UPDATE_INCOMPATIBLE) - " +
            "uninstall+install, app state (данные приложения) будет потерян.")
        & $adb uninstall com.example.ao3_wrapper | ForEach-Object { Write-Output $_ }
        & $adb install -r -d $apk | ForEach-Object { Write-Output $_ }
    }
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
    # F2-F2 (критик-вход): оракул серийников вынесен в Get-DeviceSerials (общий с
    # Test-AppiumHealthy -Deep) - раньше дублировался здесь дословно.
    $serials = Get-DeviceSerials
    if ($serials.Count -gt 0) { foreach ($s in $serials) { Write-Host "DEVICE: $s" } }
    else { Write-Host "NO DEVICE" }
}

Write-Host "Tasks loaded: Start-Emulator, Install-MitmCA, Start-Appium, Test-AppiumHealthy, Get-DeviceSerials, Stop-NodeProcesses, Ensure-BridgeHarness, Install-App, Invoke-Smoke, Invoke-Suite, Invoke-Pytest, Show-Report, Get-Device" -ForegroundColor Green
