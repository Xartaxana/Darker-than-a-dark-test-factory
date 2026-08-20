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

function Get-FreeMemoryGB {
    # spec-p3-second-emulator N3 (хвост N2 §6 п.3, RAM-гейт КОДОМ): свободная
    # физическая RAM хоста в GB, округлено до 2 знаков. `-OsInfoProvider` -
    # инжектируемый seam (тот же приём, что Start-Emulator's
    # -PortListenerResolver/-ProcessInfoResolver) для device-free юнита без
    # реального WMI-запроса. `FreePhysicalMemory` (Win32_OperatingSystem) -
    # килобайты; `$null`, если провайдер не смог получить данные (WMI
    # недоступен) - вызывающий код (Start-Emulator) трактует `$null` как
    # "гейт пропущен, замер невозможен" (fail-soft, не абортит на
    # неспособности ИЗМЕРИТЬ - только на подтверждённой нехватке).
    param(
        [scriptblock]$OsInfoProvider = { Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue }
    )
    $os = & $OsInfoProvider
    if (-not $os -or -not $os.FreePhysicalMemory) { return $null }
    # FreePhysicalMemory -- КБ (Win32_OperatingSystem); 1024*1024 КБ = 1 ГБ
    # (двоичный ГБ, не десятичный) -- НЕ используем литерал `1MB` как делитель
    # (численно совпадает с 1024*1024, но читатель мог бы принять его за
    # "перевод в МБ", а не в ГБ -- пишем делитель явно).
    return [math]::Round($os.FreePhysicalMemory / (1024 * 1024), 2)
}

function Resolve-DeviceSerial {
    # spec-p3-second-emulator N1, критик-раунд B1 (2026-08-20): tasks.ps1
    # ДОТ-СОРСИТСЯ КАЖДЫМ вызовом (констрейнт 6) - Install-App/
    # Wait-PackageServiceReady/Install-MitmCA, вызванные КАНОНИЧЕСКОЙ формой
    # как самостоятельные точки входа, каждый живёт в СВОЁМ powershell-
    # процессе и НЕ наследует $env:ANDROID_SERIAL, выставленный внутри
    # Start-Emulator в ДРУГОМ процессе. При двух живых устройствах голый adb
    # в этих функциях падал бы дословно как в N0-пробе:
    # 'adb.exe: more than one device/emulator'. Единая точка разрешения
    # серийника для ЛЮБОЙ публичной adb-функции - приоритет:
    #   1) явный -Serial (вызывающий знает точно, например Start-Emulator
    #      передаёт свой детерминированный `emulator-$Port`);
    #   2) $env:ANDROID_SERIAL, если он уже стоит В ЭТОМ ЖЕ процессе
    #      (например несколько функций вызваны из одного скрипта/сессии);
    #   3) $env:AO3_DEVICE (зеркало framework/config/settings.py DEVICE_NAME
    #      - тот же env, которым конфигурируется сам фреймворк для второго
    #      стека, N1 констрейнт 4);
    #   4) "emulator-5554" - прежний неявный дефолт (back-compat: одиночный
    #      стек без всякой параметризации продолжает работать как раньше).
    # Функция И возвращает разрешённый серийник, И устанавливает его в
    # $env:ANDROID_SERIAL для ТЕКУЩЕГО процесса - адресация остаётся единой
    # (adb.exe читает ANDROID_SERIAL нативно, ни один вызывающий код не
    # добавляет пообъектный `-s`), просто переразрешается заново на каждый
    # отдельный вызов вместо однократного наследования.
    param([string]$Serial = "")
    if (-not $Serial) {
        $Serial = if ($env:ANDROID_SERIAL) { $env:ANDROID_SERIAL }
            elseif ($env:AO3_DEVICE) { $env:AO3_DEVICE }
            else { "emulator-5554" }
    }
    $env:ANDROID_SERIAL = $Serial
    return $Serial
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
    # spec-p3-second-emulator N1 (констрейнт 3в): -Port (дефолт 5554, зеркалит
    # Start-Emulator) -- пишет ДОПОЛНИТЕЛЬНУЮ секцию `by_serial[emulator-$Port]`
    # (read-modify-write, СОХРАНЯЯ записи других стеков) РЯДОМ с прежними ФЛЭТ
    # top-level полями (gpu/avd_name/updated_utc, дословно как раньше -- "последний
    # записавший стек", обратная совместимость с AT-BUG-063 пинами framework/tests/
    # test_device_liveness_guard_unit.py, которые читают/пишут ТОЛЬКО флэт-поля и
    # НИКОГДА `by_serial`). driver_factory.py::_read_emulator_session_state
    # предпочитает `by_serial[<свой серийник>]`, если она есть, иначе откатывается
    # на флэт-поля -- легаси-файлы (записанные ДО этой правки) читаются как раньше.
    param(
        [Parameter(Mandatory)][string]$Gpu,
        [Parameter(Mandatory)][string]$AvdName,
        [int]$Port = 5554
    )
    try {
        $stateDir = "$root\state"
        if (-not (Test-Path $stateDir)) { New-Item -ItemType Directory -Path $stateDir -Force | Out-Null }
        $stateFile = "$stateDir\emulator-session.json"
        $serial = "emulator-$Port"
        $updatedUtc = (Get-Date).ToUniversalTime().ToString("o")

        # Read-modify-write секции by_serial: сохраняем записи ДРУГИХ стеков, если
        # файл уже существовал. Нечитаемый/битый существующий файл -- не блокирует
        # запись, by_serial просто начинается заново (тот же fail-soft дух, что
        # остальная эта функция); флэт top-level поля текущего вызова всё равно
        # перезапишутся корректно ниже.
        $bySerial = [ordered]@{}
        if (Test-Path $stateFile) {
            try {
                $existingRaw = [System.IO.File]::ReadAllText($stateFile)
                $existingObj = $existingRaw | ConvertFrom-Json -ErrorAction Stop
                if ($existingObj -and $existingObj.by_serial) {
                    foreach ($prop in $existingObj.by_serial.PSObject.Properties) {
                        $bySerial[$prop.Name] = $prop.Value
                    }
                }
            } catch {
                Write-Warning "WARNING: emulator-session.json существующее содержимое нечитаемо ($_) - by_serial секция начата заново."
            }
        }
        $bySerial[$serial] = [ordered]@{
            gpu         = $Gpu
            avd_name    = $AvdName
            updated_utc = $updatedUtc
        }

        $payload = [ordered]@{
            gpu         = $Gpu
            avd_name    = $AvdName
            updated_utc = $updatedUtc
            by_serial   = $bySerial
        } | ConvertTo-Json -Compress -Depth 5
        # `[System.IO.File]::WriteAllText`-семейство с явным `UTF8Encoding($false)`
        # (внутри Write-FileAtomic) пишет БЕЗ BOM — `Set-Content -Encoding UTF8` в
        # Windows PowerShell 5.1 пишет UTF-8 С BOM, что валило `json.loads` на
        # python-стороне (`JSONDecodeError: Unexpected UTF-8 BOM`, AT-BUG-063
        # attempt 2). N3 B3 (критик-вход rework attempt 2, "тот же класс",
        # D-0043): темп+Replace вместо голого WriteAllText — та же неатомарная
        # RMW-запись, тот же фикс, что Test-BySerialBackfill/Use-DeviceStack.
        Write-FileAtomic -Path $stateFile -Content $payload
    } catch {
        Write-Warning "WARNING: emulator-session.json state write failed ($_) - device-liveness recovery may fall back to defaults (AT-BUG-063)."
    }
}

function Undo-EmulatorSessionStateEntry {
    # N3 B4 (критик-вход rework attempt 2, fix-совет 3): Start-Emulator пишет
    # by_serial[emulator-$Port] СРАЗУ после разрешения -Gpu/-AvdName (см.
    # Set-EmulatorSessionState) — ЗАДОЛГО до буда/RAM-гейта post-start. Если
    # post-start RAM-гейт абортит (эмулятор гасится ПОСЛЕ буда), запись уже
    # лежит в state-файле и называет AVD, который только что погашен — ровно
    # класс инцидента N2 §5 (recovery ДРУГОГО серийника прочитал бы эту
    # запись и попытался бы поднять мёртвый AVD). Снимает ТОЛЬКО
    # by_serial[emulator-$Port] (флэт top-level "последний записавший стек" -
    # шире по духу существующего AT-BUG-063 компромисса, откат которого - вне
    # скоупа этого фикса, см. отчёт). Fail-soft: ошибка отката — WARN, не throw
    # (тот же класс отказоустойчивости, что Set-EmulatorSessionState).
    param([Parameter(Mandatory)][int]$Port)
    $stateFile = "$root\state\emulator-session.json"
    if (-not (Test-Path $stateFile)) { return }
    try {
        $raw = [System.IO.File]::ReadAllText($stateFile)
        $obj = $raw | ConvertFrom-Json -ErrorAction Stop
    } catch {
        Write-Warning "Undo-EmulatorSessionStateEntry: state-файл нечитаем ($_) - откат пропущен."
        return
    }
    $serial = "emulator-$Port"
    if (-not $obj.by_serial -or -not ($obj.by_serial.PSObject.Properties.Name -contains $serial)) {
        return
    }
    $bySerial = [ordered]@{}
    foreach ($prop in $obj.by_serial.PSObject.Properties) {
        if ($prop.Name -ne $serial) { $bySerial[$prop.Name] = $prop.Value }
    }
    $payload = [ordered]@{
        gpu = $obj.gpu; avd_name = $obj.avd_name; updated_utc = $obj.updated_utc; by_serial = $bySerial
    } | ConvertTo-Json -Compress -Depth 5
    try {
        Write-FileAtomic -Path $stateFile -Content $payload
        Write-Warning "Start-Emulator: RAM-гейт (post-start) abort - by_serial[$serial] снята из emulator-session.json (не оставляем state на погашенный AVD, N2-инцидент §5)."
    } catch {
        Write-Warning "Undo-EmulatorSessionStateEntry: запись отката не удалась ($_) - by_serial[$serial] может по-прежнему указывать на погашенный AVD."
    }
}

function Stop-OrphanedQemu {
    # Общий кусок орфан-очистки (вынесен из инлайна B2 критик-раунда,
    # 2026-08-20) - используется И существующим AT-BUG-012/014 фолбэком
    # (снапшот-буд не поднял устройство), И новой веткой port-occupancy в
    # Start-Emulator (порт занят МЁРТВЫМ - в смысле "без своего adb-девайса" -
    # владельцем-qemu, живого устройства на нём нет). AT-BUG-014 (корень):
    # $LauncherProc — это Start-Process-лаунчер emulator.exe, а НЕ фактический
    # дочерний qemu-system-x86_64.exe (отдельный процесс, отдельный PID). На
    # этом хосте qemu переживает килл лаунчера (наблюдалось 30+ минут) и
    # легитимно держит hardware-qemu.ini.lock, из-за чего Clear-EmulatorStaleLocks
    # спотыкается о ЖИВОЙ, а не мёртвый артефакт при каждой следующей попытке.
    # Убиваем и лаунчер (если передан и ещё жив), и его прямых qemu-детей, и
    # подчищаем возможных осиротевших qemu-процессов этого же AVD по командной
    # строке (страховка на случай, если родственная связь уже разорвана -
    # единственный путь, когда $LauncherProc не передан вовсе).
    #
    # N1/B5 (плана): якорь `-avd\s+<name>\b` - substring-матч БЕЗ анкера
    # заматчил бы клон `ao3_test_api34_2` в командной строке при поиске
    # `ao3_test_api34` ([regex]::Escape-only матч, БЕЗ этого якоря, ловил
    # substring где угодно в командной строке). Второй стек (N2+) несёт имя
    # AVD без общего префикса именно чтобы избежать этого класса, но якорь -
    # структурная защита независимо от конкретных имён.
    param(
        [Parameter(Mandatory)][string]$AvdName,
        [System.Diagnostics.Process]$LauncherProc = $null
    )
    if ($LauncherProc -and -not $LauncherProc.HasExited) {
        $qemuChildren = Get-CimInstance Win32_Process -Filter "ParentProcessId=$($LauncherProc.Id)" -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match 'qemu-system' }
        foreach ($child in $qemuChildren) {
            Write-Host "Killing qemu-system child process (PID $($child.ProcessId))..." -ForegroundColor Yellow
            Stop-Process -Id $child.ProcessId -Force -ErrorAction SilentlyContinue
        }
        Stop-Process -Id $LauncherProc.Id -Force -ErrorAction SilentlyContinue
    }
    $avdAnchor = "-avd\s+$([regex]::Escape($AvdName))\b"
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match 'qemu-system' -and $_.CommandLine -match $avdAnchor } |
        ForEach-Object {
            Write-Host "Killing orphaned qemu-system process for $AvdName (PID $($_.ProcessId))..." -ForegroundColor Yellow
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
    Start-Sleep 2
    Clear-EmulatorStaleLocks -AvdName $AvdName
}

function Test-QemuPortOwnerIsOrphan {
    # B2 (критик-раунд, 2026-08-20): ЧИСТАЯ функция принятия решения "живой
    # ОРФАН qemu держит консольный порт (самолечение) vs живое устройство/
    # чужой процесс (throw)", вынесена из Start-Emulator ИМЕННО ради 100%
    # device-free юнит-теста БЕЗ риска реально дойти до Start-Process/
    # emulator.exe (единственный способ протестировать саму РЕШАЮЩУЮ ветку
    # изолированно - никакой seam на Start-Process/emulator.exe не заведён и
    # заводить его специально ради теста нежелательно, N1 NON-GOALS: без
    # live-прогона). Параметры - уже РАЗРЕШЁННЫЕ данные, никаких сайд-
    # эффектов (не трогает процессы/диск/сеть).
    param(
        [bool]$OwnerIsOwnQemu,
        [Parameter(Mandatory)][string]$Serial,
        [string[]]$AdbDevicesLines = @()
    )
    if (-not $OwnerIsOwnQemu) { return $false }
    $deviceLiveOnPort = @($AdbDevicesLines | Where-Object { $_ -match "^$([regex]::Escape($Serial))\s+device$" }).Count -gt 0
    return -not $deviceLiveOnPort
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
    #
    # spec-p3-second-emulator N1: -Port (дефолт 5554 — прежнее поведение
    # неявного дефолта emulator.exe) — ПЕРЕДАЁТСЯ ЭМУЛЯТОРУ ВСЕГДА (`-port
    # $Port`), свой серийник ДЕТЕРМИНИРОВАН как `emulator-$Port` (B20 плана —
    # диффовый `adb devices` до/после запрещён явно как racy при
    # параллельном подъёме второго стека). Домен консольного порта эмулятора —
    # СВОЙ (не общий TCP-порт 1-65535): чётный, 5554-5584 (adb-порт эмулятора —
    # следующий нечётный), явная ошибка валидации на границе и за ней.
    param(
        [switch]$WritableSystem,
        [int]$SnapshotBootTimeoutSec = 45,
        [string]$Gpu = "",
        [string]$AvdName = "ao3_test_api34",
        [ValidateScript({
            if ($_ % 2 -ne 0) {
                throw "Start-Emulator: -Port должен быть ЧЁТНЫМ (консольный порт эмулятора) - получено $_."
            }
            if ($_ -lt 5554 -or $_ -gt 5584) {
                throw "Start-Emulator: -Port вне поддерживаемого диапазона 5554-5584 - получено $_."
            }
            $true
        })]
        [int]$Port = 5554,
        [string]$Memory = "",
        # B2 (критик-раунд, 2026-08-20): инжектируемые seam'ы для device-free
        # юнит-теста ОРФАН-ветки port-occupancy (см. ниже) - тот же приём, что
        # Stop-NodeProcesses -ProcessListProvider/-PortOwnerResolver/-Stopper.
        # Дефолты зовут РЕАЛЬНЫЕ Get-NetTCPConnection/Get-CimInstance/adb -
        # поведение живого прогона не меняется, если не переданы явно.
        [scriptblock]$PortListenerResolver = {
            param($P)
            Get-NetTCPConnection -LocalPort $P -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
        },
        [scriptblock]$ProcessInfoResolver = {
            param($ProcId)
            Get-CimInstance Win32_Process -Filter "ProcessId=$ProcId" -ErrorAction SilentlyContinue
        },
        # `-AdbDevicesProvider` (B2) обслуживает ТРИ `adb devices`-вызова этой
        # функции - ветку port-occupancy, ОРАКУЛ БУДА и поллинг подтверждения
        # гашения RAM-гейта (M1, критик-раунд 3): один класс вызова - один шов
        # (D-0043). Раньше два последних звали `& $adb devices` НАПРЯМУЮ, мимо
        # объявленного шва, из-за чего "device-free" юниты доезжали до
        # реального adb.
        [scriptblock]$AdbDevicesProvider = { param($AdbPath) & $AdbPath devices },
        [scriptblock]$OrphanCleaner = { param($Avd) Stop-OrphanedQemu -AvdName $Avd },
        # M1 (БЛОКЕР МЕРЖА, критик-раунд 3): ЗАПУСК эмулятора - инжектируемый шов.
        # Без него ЛЮБАЯ проба, прошедшая RAM-гейт, доезжала до РЕАЛЬНОГО
        # `Start-Process emulator.exe`: `fake_root` подменяет только `$root`, а
        # `$emu`/`$adb` резолвятся из `$env:ANDROID_HOME`, который ставит
        # `env.ps1` (дот-сорсится строкой 11 ЭТОГО файла) от НАСТОЯЩЕГО корня -
        # ДО любой подмены. В worktree это маскировалось отсутствием `tools/`
        # (FileNotFoundError), в главном чекауте бинарники есть: воспроизведено
        # суррогатным emulator.exe - проба печатает "Waiting for device boot...",
        # т.е. Start-Process ИСПОЛНИЛСЯ, а фолбэк-ветка ниже позвала бы
        # `Stop-OrphanedQemu -AvdName ao3_test_api34` и убила бы ЖИВОЙ фабричный
        # qemu. Дефолт - ДОСЛОВНО прежний Start-Process (живой прогон не меняется).
        [scriptblock]$Launcher = {
            param($Path, $ArgList)
            Start-Process -FilePath $Path -ArgumentList $ArgList -WindowStyle Minimized -PassThru
        },
        # M1-спутники: оставшиеся ПРЯМЫЕ adb-вызовы пути подъёма, без которых
        # post-start-ветка недостижима для юнита (getprop-цикл вообще БЕЗЛИМИТЕН
        # и вешает пробу). Дефолты дословно повторяют прежний инлайн.
        [scriptblock]$BootCompletedProvider = {
            param($AdbPath) Get-AdbOutput -Adb $AdbPath -AdbArgs @("shell", "getprop", "sys.boot_completed")
        },
        [scriptblock]$EmuKiller = { param($AdbPath, $Serial) & $AdbPath -s $Serial emu kill 2>$null | Out-Null },
        [scriptblock]$WaitForDeviceProvider = { param($AdbPath) & $AdbPath wait-for-device },
        # spec-p3-second-emulator N3 (хвост N2 §6 п.3, RAM-гейт КОДОМ; B4
        # критик-вход rework attempt 2 — ПОДКЛЮЧЕНО К РЕАЛЬНОМУ ПУТИ):
        # дефолт зависит от `-Port` — 5554 (первичный/единственный стек,
        # прежнее поведение ДОСЛОВНО) держит гейт ВЫКЛЮЧЕННЫМ (0); ЛЮБОЙ
        # ДРУГОЙ порт (второй/дополнительный эмулятор — ровно то, что делает
        # стек 2) автоматически включает пороги плана. Раньше эти пороги
        # передавал ТОЛЬКО вызывающий явно — комментарий здесь ЛГАЛ, что
        # "Use-DeviceStack для стека 2 передаёт своё оценочное число":
        # Use-DeviceStack НИКОГДА не вызывает Start-Emulator (это два
        # независимых входа tasks.ps1) — единственный реальный путь
        # подключения гейта - дефолт САМОЙ Start-Emulator, ключёванный по
        # -Port. Явное отключение по-прежнему возможно (`-MinFreeGBPreStart 0
        # -MinFreeGBPostStart 0` явным параметром переопределяет дефолт-
        # выражение ниже, PowerShell параметр-биндинг это гарантирует).
        # Оценка (F-30, docs/tasks/p3-second-emulator.md "Решение оператора
        # по RAM"): клон ~2-2.5 GB (берём верхнюю/консервативную границу) +
        # буфер 1.0 GB = 3.5 GB pre-start; post-start 1.0 GB (констрейнт 1).
        # `$null` из -FreeMemoryProvider (WMI недоступен) — гейт МОЛЧА
        # пропускается (fail-soft: неспособность ИЗМЕРИТЬ не абортит подъём,
        # абортит только ПОДТВЕРЖДЁННАЯ нехватка).
        [double]$MinFreeGBPreStart = $(if ($Port -ne 5554) { 3.5 } else { 0 }),
        [double]$MinFreeGBPostStart = $(if ($Port -ne 5554) { 1.0 } else { 0 }),
        [scriptblock]$FreeMemoryProvider = { Get-FreeMemoryGB }
    )
    if (-not $Gpu) { $Gpu = if ($env:AO3_EMU_GPU) { $env:AO3_EMU_GPU } else { "swiftshader_indirect" } }
    $serial = "emulator-$Port"

    if ($MinFreeGBPreStart -gt 0) {
        $freePre = & $FreeMemoryProvider
        if ($null -ne $freePre -and $freePre -lt $MinFreeGBPreStart) {
            throw ("Start-Emulator: RAM-гейт (pre-start) - free ${freePre} GB < требуемых " +
                "${MinFreeGBPreStart} GB (N2-эмпирика runs/N2-p3-clone-bringup-stack2-2026-08-20.md: " +
                "клон+1.0 GB буфер) - abort ДО подъёма эмулятора $serial, ни один side-effect ещё не начат.")
        }
    }

    # N1 back-compat-строка (плана): РАНЬШЕ повторный Start-Emulator на живом
    # порте тихо уезжал на следующую свободную пару портов (сам emulator.exe
    # инкрементирует при занятости 5554/5555) - с ЖЁСТКОЙ адресацией по -Port
    # эта тихая подмена устройства больше недопустима. Проверка ПЕРЕД любым
    # side-effect (до Set-EmulatorSessionState/Clear-EmulatorStaleLocks/
    # Start-Process) - явная ошибка не оставляет частичного состояния.
    #
    # B2 (критик-раунд, 2026-08-20): голый throw-на-занятости шунтировал
    # самолечение AT-BUG-012/014 - живой ОСИРОТЕВШИЙ qemu (лаунчер умер,
    # qemu-дитя пережило килл, см. комментарий ниже про AT-BUG-014) держит
    # консольный порт, но $serial НЕ значится в `adb devices` как `device` -
    # раньше следующий Start-Emulator сам чистил такой орфан и продолжал,
    # теперь бы падал КАЖДЫЙ раз, и recovery driver_factory (AT-BUG-026)
    # получал бы DeviceRecoveryError вместо починки. Различаем владельца:
    # throw ТОЛЬКО если порт держит живое устройство ИЛИ ЧУЖОЙ (не наш AVD,
    # не qemu вовсе) процесс - иначе выполняем ТУ ЖЕ очистку, что фолбэк
    # ниже (Stop-OrphanedQemu), и продолжаем штатный старт.
    $adb = "$env:ANDROID_HOME\platform-tools\adb.exe"
    $emu = "$env:ANDROID_HOME\emulator\emulator.exe"
    $avdAnchor = "-avd\s+$([regex]::Escape($AvdName))\b"

    $portOwner = & $PortListenerResolver $Port
    if ($portOwner) {
        $ownerProc = & $ProcessInfoResolver $portOwner.OwningProcess
        $ownerIsOwnQemu = $ownerProc -and $ownerProc.Name -match 'qemu-system' -and $ownerProc.CommandLine -match $avdAnchor
        # Совет-по-факту (не из списка критика, но того же духа что B2): adb
        # devices зовётся ТОЛЬКО когда владелец уже похож на наш qemu -
        # держит существующее свойство "ноль лишних adb-вызовов", когда порт
        # занят чем-то заведомо чужим (см. test_start_emulator_repeated_
        # launch_on_occupied_port_is_explicit_error - там владелец powershell.exe
        # теста, adb devices не должен вызываться вовсе).
        $devLines = if ($ownerIsOwnQemu) { & $AdbDevicesProvider $adb } else { @() }
        $isOrphan = Test-QemuPortOwnerIsOrphan -OwnerIsOwnQemu $ownerIsOwnQemu -Serial $serial -AdbDevicesLines $devLines
        if ($isOrphan) {
            Write-Warning ("Start-Emulator: порт $Port занят ОРФАНОМ qemu (PID $($portOwner.OwningProcess), " +
                "AVD $AvdName) без живого устройства в 'adb devices' - похоже на класс AT-BUG-012/014 " +
                "(краш лаунчера/квикбута). Чищу орфана и продолжаю старт вместо отказа.")
            & $OrphanCleaner $AvdName
        } else {
            throw ("Start-Emulator: консольный порт $Port уже занят (PID $($portOwner.OwningProcess)) " +
                "живым устройством или чужим процессом - повторный запуск на занятом порте запрещён " +
                "(адресация теперь жёсткая по -Port, тихая подмена устройства на следующий свободный " +
                "порт больше не легальна). Останови существующий эмулятор или укажи свободный -Port.")
        }
    }

    # N1 (констрейнт 4, B3 плана): ANDROID_SERIAL - ЕДИНАЯ адресация для ВСЕГО
    # последующего adb-пути этого подъёма (adb.exe читает её нативно) -
    # getprop-цикл/Set-GuestIPv4Pin/Install-App/Wait-PackageServiceReady/
    # install-mitm-ca.sh (bash-подпроцесс наследует env) больше НЕ нуждаются в
    # пообъектном `-s`. Единственное явное исключение - оракул буда ниже
    # (`adb devices` ИГНОРИРУЕТ ANDROID_SERIAL по конструкции, матчим серийник
    # явно в выводе). Через Resolve-DeviceSerial (B1) для единообразия со
    # standalone-вызовами Install-App/Wait-PackageServiceReady/Install-MitmCA -
    # здесь $serial уже детерминирован из -Port, поэтому helper просто
    # устанавливает его и возвращает как есть (параметр дан - фолбэк-цепочка
    # env не консультируется).
    Resolve-DeviceSerial -Serial $serial | Out-Null

    # AT-BUG-063: фиксируем РАЗРЕШЁННЫЕ (пост-фолбэк) значения -- это единственный
    # момент, когда известно фактическое намерение вызова (CLI-параметр, env-переменная
    # или дефолт), см. Set-EmulatorSessionState выше.
    Set-EmulatorSessionState -Gpu $Gpu -AvdName $AvdName -Port $Port

    Clear-EmulatorStaleLocks -AvdName $AvdName

    $emuArgs = @("-avd",$AvdName,"-no-boot-anim","-gpu",$Gpu,"-port","$Port")
    if ($Memory) { $emuArgs += @("-memory","$Memory") }
    if ($WritableSystem) { $emuArgs += "-writable-system" }

    # M1: через $Launcher (дефолт = прежний Start-Process). ЕДИНСТВЕННАЯ точка
    # реального запуска в этой функции вместе с фолбэком ниже.
    $proc = & $Launcher $emu $emuArgs
    Write-Host "Waiting for device boot ($serial, snapshot, up to ${SnapshotBootTimeoutSec}s)..." -ForegroundColor Cyan

    $deadline = (Get-Date).AddSeconds($SnapshotBootTimeoutSec)
    $deviceUp = $false
    do {
        Start-Sleep 2
        if ($proc.HasExited) { break }
        $lines = & $AdbDevicesProvider $adb
        # N1/B3 (N0-проба 2026-08-20): матч ИМЕННО $serial, НЕ "любое устройство
        # в состоянии device" - оракул буда раньше объявлял буд по ЧУЖОМУ
        # emulator-5554, если тот уже был жив (молчаливый ложный успех,
        # найдено эмпирически в runs/N0-p3-two-device-probe-2026-08-20.md).
        $deviceUp = @($lines | Where-Object { $_ -match "^$([regex]::Escape($serial))\s+device$" }).Count -gt 0
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
        # случай, если родственная связь уже разорвана). Вынесено в
        # Stop-OrphanedQemu (B2 критик-раунда) - тот же кусок теперь переиспользует
        # и новая ветка port-occupancy выше (живой орфан держит консольный порт).
        Stop-OrphanedQemu -AvdName $AvdName -LauncherProc $proc
        $fallbackArgs = $emuArgs + "-no-snapshot-load"
        $proc = & $Launcher $emu $fallbackArgs  # M1: тот же шов, что первичный запуск
        # Бэрный вызов (без -s) - таргетируется через $env:ANDROID_SERIAL,
        # выставленный выше (единая адресация, констрейнт 4).
        & $WaitForDeviceProvider $adb
    }

    # Get-AdbOutput (null-safe .Trim(), констрейнт 4 п.2): голый `(& $adb ...).Trim()`
    # падал бы на $null-выводе независимо от адресации - защита остаётся.
    do { Start-Sleep 2; $b = & $BootCompletedProvider $adb } while ($b -ne "1")
    Write-Host "Emulator booted ($serial)." -ForegroundColor Green

    if ($MinFreeGBPostStart -gt 0) {
        $freePost = & $FreeMemoryProvider
        if ($null -ne $freePost -and $freePost -lt $MinFreeGBPostStart) {
            Write-Warning ("Start-Emulator: RAM-гейт (post-start) - free ${freePost} GB < " +
                "${MinFreeGBPostStart} GB (констрейнт 1 плана) - abort, гашу только что поднятый $serial " +
                "(N2-эмпирика: чистое гашение `adb -s <serial> emu kill`).")
            & $EmuKiller $adb $serial
            # B4 fix-совет 3 (критик-вход rework attempt 2): проверяем ФАКТ
            # гашения (не верим "emu kill вернул код 0" на слово) - короткий
            # поллинг adb devices; если серийник всё ещё виден - qemu-дитя
            # могло пережить emu kill (тот же класс, что AT-BUG-014 килл
            # лаунчера). Stop-OrphanedQemu зовём БЕЗУСЛОВНО после - подметает
            # и лаунчер ($proc), и его qemu-детей, и осиротевших по имени AVD
            # (идемпотентна, если всё уже мертво - Get-CimInstance просто
            # ничего не найдёт).
            $killDeadline = (Get-Date).AddSeconds(10)
            $stillUp = $true
            do {
                Start-Sleep 1
                $killLines = & $AdbDevicesProvider $adb
                $stillUp = @($killLines | Where-Object { $_ -match "^$([regex]::Escape($serial))\s+device$" }).Count -gt 0
            } while ($stillUp -and (Get-Date) -lt $killDeadline)
            if ($stillUp) {
                Write-Warning "Start-Emulator: RAM-гейт abort - $serial всё ещё виден в 'adb devices' 10с после emu kill - подметаю qemu-детей принудительно."
            }
            Stop-OrphanedQemu -AvdName $AvdName -LauncherProc $proc
            Undo-EmulatorSessionStateEntry -Port $Port
            throw ("Start-Emulator: RAM-гейт (post-start) сработал - free ${freePost} GB < " +
                "${MinFreeGBPostStart} GB, эмулятор $serial погашен (гашение подтверждено: $(-not $stillUp)), " +
                "ни IPv4-пин, ни mitm-CA не выполнялись, emulator-session.json откачен.")
        }
    }

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
    #
    # B1 (критик-раунд, 2026-08-20): САМОСТОЯТЕЛЬНАЯ каноническая точка входа
    # (`. tasks.ps1; Install-MitmCA`) - свой powershell-процесс, не наследует
    # $env:ANDROID_SERIAL из Start-Emulator (констрейнт 6), даже когда та
    # выставила его для СВОЕГО процесса при -WritableSystem автовызове (в этом
    # автовызове Resolve-DeviceSerial ниже просто подтвердит уже стоящий
    # env:ANDROID_SERIAL - параметр не дан, второй приоритет в цепочке
    # сработает без изменений). install-mitm-ca.sh адресуется через
    # `ADB="${ADB:-adb}"` + нативное чтение ANDROID_SERIAL bash-подпроцессом
    # (env наследуется в дочерний bash) - никакого -s не нужно ни здесь, ни в
    # самом .sh.
    param(
        [string]$Serial = "",
        [Nullable[int]]$Port = $null
    )
    if (-not $Serial -and $null -ne $Port) { $Serial = "emulator-$Port" }
    Resolve-DeviceSerial -Serial $Serial | Out-Null
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
    # F1 (spec F v2, критик-фиксы норматив): резидентный guard — на порту может уже
    # жить чужой/долгоживущий Appium (фабрика). Порт занят -> NO-OP по умолчанию,
    # печать диагностики владельца, новый процесс НЕ стартуем. -Restart гасит
    # ТОЛЬКО процесс, чей CommandLine содержит $root (зеркало проверки владения
    # Stop-NodeProcesses выше, урок AT-BUG-031) - чужой владелец не гасится.
    #
    # spec-p3-second-emulator N1: -Port (дефолт 4723, прежнее поведение) -
    # второй device-стек поднимает Appium на :4725 параллельно с фабричным
    # :4723; резидентный guard/владение теперь ПЕР-ПОРТ (единственный
    # прежде хардкод 4723 параметризован везде: занятость, npx --port,
    # per-стек --log, /status-поллинг, -Restart).
    param([ValidateRange(1,65535)][int]$Port = 4723, [int]$TimeoutSeconds = 60, [switch]$Restart)

    $statusUrl = "http://127.0.0.1:$Port/status"

    # Первым шагом - однозначный владелец порта. -State Listen обязателен: без
    # него Get-NetTCPConnection отдаёт 2+ строк (Established и т.п.) и
    # ломает WQL-фильтр ниже (критик-замер). Имя переменной - $ownerPid, НЕ $pid
    # ($pid - read-only automatic variable, присваивание падает под
    # $ErrorActionPreference='Stop').
    $ownerPid = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty OwningProcess

    if ($ownerPid) {
        $ownerProc = Get-CimInstance Win32_Process -Filter "ProcessId=$ownerPid" -ErrorAction SilentlyContinue

        if ($Restart) {
            # B5 (критик-раунд N1): тот же якорный предикат владения, что в
            # Stop-NodeProcesses — «.js-скрипт под $root» (владелец порта =
            # appium-воркер, исполняющий index.js под $root; неякорная
            # подстрока заматчила бы и чужой процесс, несущий $root-путь
            # простым аргументом, — класс B5/AT-BUG-031).
            $restartOwnerAnchor = [regex]::Escape($root) + '[^"\s]*\.js\b'
            if ($ownerProc -and $ownerProc.CommandLine -and $ownerProc.CommandLine -match $restartOwnerAnchor) {
                $killedPid = $ownerPid
                $killedCommandLine = $ownerProc.CommandLine
                Write-Host "Start-Appium -Restart: останавливаю владельца :$Port (PID $killedPid, наш процесс)..." -ForegroundColor Yellow
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
                    $stillOwner = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
                        Select-Object -First 1 -ExpandProperty OwningProcess
                } while ($stillOwner -and (Get-Date) -lt $killDeadline)
                if ($stillOwner) {
                    throw "Start-Appium -Restart: PID $killedPid ($killedCommandLine) не отпустил :$Port за 15с после Stop-Process - порт всё ещё занят."
                }
                $ownerPid = $null
                # падает сквозь if в свежий старт ниже
            } else {
                throw "владелец :$Port не наш (CommandLine не содержит `$root) - гасить отказываюсь."
            }
        } else {
            if ($ownerProc) {
                $uptime = (Get-Date) - $ownerProc.CreationDate
                Write-Host ("Appium уже слушает :$Port - PID $ownerPid, запущен $($ownerProc.CreationDate), " +
                    "uptime $uptime") -ForegroundColor Yellow
            } else {
                Write-Host "порт $Port занят, владелец не резолвится (чужой/проброшенный сервер)" -ForegroundColor Yellow
            }
            # F2-B2 (критик-вход): восстанавливаем контракт функции "/status ready либо
            # throw" на резидентном пути тоже - один inline shallow-опрос (НЕ -Deep -
            # деградировавший резидент не трогаем сессиями чужого прогона).
            try {
                $residentReady = (Invoke-WebRequest -Uri $statusUrl -UseBasicParsing -TimeoutSec 5).Content -match '"ready":true'
            } catch {
                $residentReady = $false
            }
            if ($residentReady) {
                Write-Host "резидентный (:$Port), /status ready" -ForegroundColor Green
                return
            } else {
                throw "резидентный (:$Port), /status НЕ отвечает - процесс жив, сервер мёртв; перезапуск: Start-Appium -Port $Port -Restart"
            }
        }
    }

    # Свежий старт (порт свободен, либо -Restart легально освободил его выше).
    Push-Location "$root\tools\appium"
    $logDir = "$root\logs"
    if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
    $logFile = "$logDir\appium-$Port.log"
    # "npx" (без расширения) через Start-Process на некоторых машинах резолвится не в
    # npx.cmd, а в постороннюю ShellExecute-ассоциацию (наблюдалось: открывался Notepad).
    # npx.cmd — однозначный путь к реальному исполняемому файлу.
    Start-Process -FilePath "npx.cmd" `
        -ArgumentList "appium","--port","$Port","--log-level","warn","--allow-insecure","uiautomator2:chromedriver_autodownload","--log","$logFile" `
        -WindowStyle Minimized
    Pop-Location
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        Start-Sleep 2
        try { $ready = (Invoke-WebRequest -Uri $statusUrl -UseBasicParsing -TimeoutSec 3).Content -match '"ready":true' } catch { $ready = $false }
    } while (-not $ready -and (Get-Date) -lt $deadline)
    if (-not $ready) { throw "Appium not ready after ${TimeoutSeconds}s ($statusUrl)" }
    # /status отвечает и у деградировавшего сервера (класс AT-BUG-064/NoSuchDriverError) -
    # "ready" здесь означает только HTTP-готовность, НЕ здоровье сессии.
    Write-Host "Appium started on :$Port, /status ready (здоровье НЕ проверено - Test-AppiumHealthy -Deep)" -ForegroundColor Green
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
    # spec-p3-second-emulator N1: дефолт -AppiumUrl теперь ИЗ ПАРАМЕТРА, а при
    # его отсутствии - из $env:APPIUM_URL (зеркало framework/config/settings.py
    # APPIUM_URL), и только затем - жёсткого литерала :4723 (второй device-стек
    # целится в :4725 без явного -AppiumUrl на каждом вызове, если env уже
    # выставлен канонической формой).
    param(
        [switch]$Deep,
        [string]$AppiumUrl = $(if ($env:APPIUM_URL) { $env:APPIUM_URL } else { "http://127.0.0.1:4723" }),
        [int]$SessionTimeoutSec = 120
    )

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
    #
    # spec-p3-second-emulator N1 (констрейнт 3а): второй device-стек держит
    # СВОЙ резидентный Appium (:4725) параллельно с фабричным (:4723) -
    # слепой "убей всех owned" убивал бы ОБА без разбора. Селектор -Port/
    # -OwnerPid выбирает КОНКРЕТНЫЙ процесс; без селектора при >1 owned
    # node-процессе - явный отказ с перечнем кандидатов (при 0/1 - прежнее
    # поведение дословно). [CmdletBinding(SupportsShouldProcess)] даёт
    # -WhatIf "бесплатно" (печатает намерение, ничего не убивает) поверх
    # СОБСТВЕННОГО детерминированного списка кандидатов ниже (стабильный,
    # не зависит от WhatIf - тесты сверяют dry-run список с живым).
    #
    # -ProcessListProvider/-PortOwnerResolver/-Stopper - инжектируемые
    # seam'ы для device-free юнит-тестов (scripts/tests): дефолты зовут
    # РЕАЛЬНЫЕ Get-CimInstance/Get-NetTCPConnection/Stop-Process, тесты
    # подменяют их фейковыми данными без касания реального хоста.
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [ValidateRange(1,65535)][Nullable[int]]$Port = $null,
        [Nullable[int]]$OwnerPid = $null,
        [scriptblock]$ProcessListProvider = { Get-CimInstance Win32_Process -Filter "Name='node.exe'" -ErrorAction SilentlyContinue },
        [scriptblock]$PortOwnerResolver = {
            param($P)
            Get-NetTCPConnection -LocalPort $P -State Listen -ErrorAction SilentlyContinue |
                Select-Object -First 1 -ExpandProperty OwningProcess
        },
        [scriptblock]$Stopper = { param($TargetPid) Stop-Process -Id $TargetPid -Force -ErrorAction SilentlyContinue }
    )
    if (-not $root -or -not (Test-Path $root)) {
        throw "Stop-NodeProcesses: `$root пуст или недействителен ('$root') - отказ убивать node-процессы вслепую (AT-BUG-031: [regex]::Escape('') заматчил бы ЛЮБУЮ командную строку)."
    }
    $allNode = & $ProcessListProvider
    # B5 (критик-раунд N1, 2026-08-20): владение — ЯКОРНЫЙ предикат
    # «.js-скрипт под $root», не подстрока $root по всей CommandLine.
    # Неякорная подстрока ловила npx-ОБЁРТКУ (npm-cli из Program Files),
    # как только в её argv попал путь --log $root\logs\appium-<port>.log:
    # один сервер = 2 кандидата => голая каноническая форма без селектора
    # бросала исключение на одностековом хосте. Якорь: токен без пробелов/
    # кавычек, начинающийся с $root и оканчивающийся .js — матчит воркер
    # (node ...\appium\index.js) и bridge-раннер (run_bridge.js), но не
    # .log-аргументы. Класс тот же, что якорь qemu-килла (-avd\s+<name>\b).
    $rootJsAnchor = [regex]::Escape($root) + '[^"\s]*\.js\b'
    $rootMatched = @($allNode | Where-Object { $_.CommandLine -and $_.CommandLine -match $rootJsAnchor })
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

    $hasSelector = ($null -ne $Port) -or ($null -ne $OwnerPid)
    $toStop = $owned
    if ($hasSelector) {
        $selectedPid = $OwnerPid
        if ($null -eq $selectedPid -and $null -ne $Port) {
            $selectedPid = & $PortOwnerResolver $Port
        }
        if ($null -eq $selectedPid) {
            # Порт без слушателя / явный PID не передан вовсе - убить НОЛЬ,
            # это НЕ ошибка (матрица DoD: "селектор мимо -> убить НОЛЬ").
            $toStop = @()
        } else {
            # Мёртвый/переиспользованный/чужой (не-AO3) PID - не входит в
            # $owned -> Where-Object естественно даёт пустой список (убить
            # НОЛЬ), без отдельной ветки.
            $toStop = @($owned | Where-Object { $_.ProcessId -eq $selectedPid })
        }
    } elseif ($owned.Count -gt 1) {
        # N3 (хвост N2 §3: "полировка WhatIf-отказа жнеца" - живой прогон
        # N2 нашёл, что список кандидатов приходил ТОЛЬКО в тексте исключения,
        # не отдельным stdout-выводом, - под -WhatIf это неудобно читать (сам
        # dry-run "зеркалит" отказ live throw'ом, приёмка N2 признала это
        # приемлемым, но кандидатов стоит видеть ДО throw, не только в тексте
        # исключения). Печатаем ОТДЕЛЬНО ДО throw - throw остаётся (dry-run
        # честно предсказывает отказ live-вызова, N2-эмпирика), но список
        # теперь виден дважды: как обычный вывод И в тексте исключения (второе
        # сохранено для совместимости с существующими тестами/catch-блоками,
        # которые читают перечень из сообщения).
        Write-Host "Candidates to stop (селектор -Port/-OwnerPid не передан):" -ForegroundColor Cyan
        foreach ($p in $owned) { Write-Host "  PID $($p.ProcessId): $($p.CommandLine)" }
        $list = ($owned | ForEach-Object { "  PID $($_.ProcessId): $($_.CommandLine)" }) -join "`n"
        throw ("Stop-NodeProcesses: найдено $($owned.Count) AO3 node-процессов без селектора " +
            "-Port/-OwnerPid - откажусь убивать все вслепую (второй device-стек может " +
            "держать свой Appium параллельно, констрейнт 3а). Кандидаты:`n$list`n" +
            "Укажи -Port <port> или -OwnerPid <pid>, чтобы выбрать конкретный.")
    }

    if ($toStop.Count -gt 0) {
        Write-Host "Candidates to stop:" -ForegroundColor Cyan
        foreach ($p in $toStop) { Write-Host "  PID $($p.ProcessId): $($p.CommandLine)" }
    }

    $stoppedCount = 0
    foreach ($p in $toStop) {
        if ($PSCmdlet.ShouldProcess("PID $($p.ProcessId): $($p.CommandLine)", "Stop-Process")) {
            Write-Host "Stopping AO3 node process (PID $($p.ProcessId)): $($p.CommandLine)" -ForegroundColor Yellow
            & $Stopper $p.ProcessId
            $stoppedCount++
        }
    }
    # Батч мелочей D-0081 (2026-07-29): раньше при 0 owned печатались ОБА
    # сообщения ("No AO3 node processes found..." И "Stopped 0 AO3 node
    # process(es)." следом) - одно сообщение на исход.
    #
    # Совет критика (критик-раунд, 2026-08-20): "No AO3 node processes found"
    # вводило в заблуждение, когда СЕЛЕКТОР был дан, но не выбрал ни одного из
    # реально найденных $owned кандидатов (порт без слушателя / мёртвый /
    # чужой PID) - процессы-то есть, просто ни один не совпал с селектором.
    # Различаем: генуинный ноль owned (сообщение как раньше) vs
    # селектор-мимо-непустого-списка (новое сообщение с числом кандидатов).
    if ($toStop.Count -eq 0 -and $hasSelector -and $owned.Count -gt 0) {
        Write-Host ("Stop-NodeProcesses: селектор не выбрал ни одного из $($owned.Count) кандидатов " +
            "(nothing to stop).") -ForegroundColor Yellow
    } elseif ($toStop.Count -eq 0) {
        Write-Host "No AO3 node processes found (nothing to stop)." -ForegroundColor Yellow
    } elseif ($stoppedCount -gt 0) {
        Write-Host "Stopped $stoppedCount AO3 node process(es)." -ForegroundColor Green
    }
    if ($stoppedCount -gt 0) { Start-Sleep 1 }
}

function Wait-PackageServiceReady {
    # AT-BUG-013: sys.boot_completed=1 (см. Start-Emulator) НЕ гарантирует, что
    # гостевой package-сервис уже поднялся - Install-App сразу после буда может
    # словить `cmd: Can't find service: package`, хотя устройство по Get-Device
    # уже есть. Фактический сигнал готовности - устойчивый непустой ответ
    # `pm path android` (пустой вывод/ошибка = сервис ещё не готов). Короткий
    # поллинг с таймаутом, явное предупреждение при неудаче - НЕ молчаливый
    # бесконечный retry: вызывающий код (Install-App) сам решает, продолжать ли.
    #
    # B1 (критик-раунд, 2026-08-20): САМОСТОЯТЕЛЬНАЯ каноническая точка входа
    # (`. tasks.ps1; Wait-PackageServiceReady`) - живёт в СВОЁМ powershell-
    # процессе, НЕ наследует $env:ANDROID_SERIAL, выставленный Start-Emulator в
    # ДРУГОМ процессе (констрейнт 6: дот-сорсинг на каждый вызов). -Serial/-Port
    # + Resolve-DeviceSerial первой строкой - та же адресация, что у
    # Start-Emulator, но переразрешённая для ЭТОГО процесса. -Adb - тестовый
    # seam (тот же паттерн, что Get-AdbOutput -Adb), позволяющий подставить
    # фейковый adb.exe и получить device-free пин без реального устройства.
    param(
        [int]$TimeoutSec = 30,
        [string]$Serial = "",
        [Nullable[int]]$Port = $null,
        [string]$Adb = ""
    )
    if (-not $Serial -and $null -ne $Port) { $Serial = "emulator-$Port" }
    Resolve-DeviceSerial -Serial $Serial | Out-Null
    if (-not $Adb) { $Adb = "$env:ANDROID_HOME\platform-tools\adb.exe" }
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    $ready = $false
    do {
        $out = & $Adb shell pm path android 2>$null
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
    #
    # B1 (критик-раунд, 2026-08-20): САМОСТОЯТЕЛЬНАЯ каноническая точка входа,
    # свой powershell-процесс, не наследует $env:ANDROID_SERIAL из Start-Emulator
    # (констрейнт 6). -Serial/-Port + Resolve-DeviceSerial первой строкой,
    # передаётся тем же резолвнутым серийником в Wait-PackageServiceReady (одна
    # адресация на весь Install-App, не два независимых разрешения). -Adb -
    # тестовый seam (паттерн Get-AdbOutput -Adb), для device-free пина.
    param(
        [int]$PackageServiceTimeoutSec = 30,
        [string]$Serial = "",
        [Nullable[int]]$Port = $null,
        [string]$Adb = ""
    )
    if (-not $Serial -and $null -ne $Port) { $Serial = "emulator-$Port" }
    $resolvedSerial = Resolve-DeviceSerial -Serial $Serial
    if (-not $Adb) { $Adb = "$env:ANDROID_HOME\platform-tools\adb.exe" }
    Wait-PackageServiceReady -TimeoutSec $PackageServiceTimeoutSec -Serial $resolvedSerial -Adb $Adb | Out-Null
    $apk = "$root\app-under-test\app\build\outputs\apk\debug\app-debug.apk"
    $out = & $Adb install -r -d $apk 2>&1
    $out | ForEach-Object { Write-Output $_ }
    if (($out -join "`n") -match "INSTALL_FAILED_UPDATE_INCOMPATIBLE") {
        Write-Warning ("Install-App: подписи не совпадают (INSTALL_FAILED_UPDATE_INCOMPATIBLE) - " +
            "uninstall+install, app state (данные приложения) будет потерян.")
        & $Adb uninstall com.example.ao3_wrapper | ForEach-Object { Write-Output $_ }
        & $Adb install -r -d $apk | ForEach-Object { Write-Output $_ }
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

# --- spec-p3-second-emulator N3: машинная лиза стека ---
#
# Окна лизы (F-30 -- ОЦЕНКА, не замер; калибруется живыми прогонами N2/N4,
# см. docs/tasks/p3-second-emulator.md N3): grace ~10 мин до первого штампа
# (между шагами bring-up, ПОКА pytest ещё не подключился), idle ~30 мин
# после смерти pytest-PID (паузы "прогон -> правка -> прогон" внутри
# тикета), TTL 4 ч -- верхняя страховка, если heartbeat реально замолк.
# Формулы состояния (`Get-DeviceLeaseStatus` ниже) СВЕРЕНЫ юнитами с
# Python-стороной чокпоинта (`framework/core/driver_factory._lease_status`,
# `framework/tests/test_device_lease_checkpoint_unit.py`) -- ОДНА семантика,
# ДВЕ реализации (PS для Use-DeviceStack, Python для create_driver).
$_DEVICE_LEASE_GRACE_SECONDS = 600
$_DEVICE_LEASE_IDLE_SECONDS = 1800
$_DEVICE_LEASE_TTL_SECONDS = 14400

$_DEVICE_STACKS = @{
    1 = @{ Device = "emulator-5554"; AppiumPort = 4723; AllureDir = "framework\allure-results" }
    2 = @{ Device = "emulator-5556"; AppiumPort = 4725; AllureDir = "framework\allure-results-2" }
}

function Write-FileAtomic {
    # N3 B3 (критик-вход rework attempt 2): темп-файл + [System.IO.File]::
    # Replace/Move — критик воспроизвёл двойную/тройную выдачу лизы на
    # НЕАТОМАРНЫХ записях (голый Set-Content/WriteAllText поверх
    # существующего файла — читатель, попавший на середину записи, видит
    # партиальный/битый JSON и ошибочно трактует лизу как "битую -> free",
    # что открывает окно повторного взятия параллельным процессом).
    # `File.Replace` — атомарная замена СУЩЕСТВУЮЩЕГО файла (требует, чтобы
    # dest существовал); для НОВОГО файла (dest ещё не создан этим потоком
    # исполнения) — атомарный `File.Move` из темпа. Используется ЛЮБОЙ
    # RMW-записью state-файлов этого модуля (Use-DeviceStack heartbeat/idle-
    # own, Test-BySerialBackfill, Set-EmulatorSessionState,
    # Undo-EmulatorSessionStateEntry — "чини класс, а не экземпляр", D-0043:
    # один и тот же паттерн неатомарной RMW-записи JSON, один и тот же фикс).
    #
    # НЕ используется для ВЗЯТИЯ лизы (see Take-DeviceLeaseSlot) — там нужна
    # НАСТОЯЩАЯ компаре-и-своп семантика (кто первый — тот и взял), которую
    # File.Replace НЕ даёт (просто перезаписывает без проверки, что dest
    # всё ещё в ожидаемом состоянии — два конкурентных Replace оба "успешно"
    # отработают последовательно, оба вызывающих решат "я выиграл").
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Content
    )
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    $dir = Split-Path -Parent $Path
    if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    $tmp = "$Path.tmp-$PID-$([guid]::NewGuid().ToString('N').Substring(0,8))"
    # Non-blocker 4 (критик-раунд 2): темп удаляется в `finally` на ВСЕХ путях
    # отказа, не только на узкой Move-гонке. Раньше отказ Replace (sharing
    # violation целевого файла - штатный транзиент, пока Take-DeviceLeaseSlot
    # держит FileShare.None) оставлял `<файл>.tmp-<pid>-<hex>` НАВСЕГДА: сирота
    # такого класса найден живьём в worktree этой задачи
    # (`state/emulator-session.json.tmp-17940-922927f7`). Remove-Item
    # -ErrorAction SilentlyContinue - housekeeping не должен маскировать
    # исходное исключение записи.
    try {
    [System.IO.File]::WriteAllText($tmp, $Content, $utf8NoBom)
    if (Test-Path $Path) {
        # Найдено ЭТОЙ сессией эмпирически (M6/F-30-класс, не предположение):
        # `[System.IO.File]::Replace(src, dst, $null)` (destinationBackupFileName
        # = null, "без бэкапа" по документации .NET) на ЭТОМ хосте (Windows
        # PowerShell 5.1 / .NET Framework) кидает `ArgumentException`
        # (HRESULT=0x80070057, E_INVALIDARG) — воспроизведено детерминированно
        # в изоляции, не разовый глюк. Явный бэкап-путь работает штатно;
        # подчищаем бэкап сразу же (fail-soft — не срываем саму атомарную
        # запись, если удаление бэкапа не удалось, только WARN).
        $bak = "$Path.bak-$PID-$([guid]::NewGuid().ToString('N').Substring(0,8))"
        try {
            [System.IO.File]::Replace($tmp, $Path, $bak)
        } finally {
            if (Test-Path $bak) {
                try { Remove-Item $bak -Force -ErrorAction Stop } catch {
                    Write-Warning "Write-FileAtomic: бэкап-файл $bak не удалён ($_) - не мусор данных, только housekeeping."
                }
            }
        }
    } else {
        try {
            [System.IO.File]::Move($tmp, $Path)
        } catch [System.IO.IOException] {
            # Узкая гонка: кто-то создал $Path МЕЖДУ нашим Test-Path и Move -
            # темп подчищаем, отказ пробрасываем как есть (RMW-запись, не
            # ВЗЯТИЕ лизы — нет отдельной "гонка, повтори" семантики здесь).
            throw
        }
    }
    } finally {
        if (Test-Path $tmp) { Remove-Item $tmp -Force -ErrorAction SilentlyContinue }
    }
}

function Write-FileAtomicResilient {
    # Non-blocker 5 (критик-раунд 2): ДОМЕННАЯ обёртка над Write-FileAtomic для
    # вызывающих, чей СОБСТВЕННЫЙ докстринг обещает "НЕ блокирует"
    # (Test-BySerialBackfill - страховка recovery; heartbeat лизы - страховка
    # свежести, не гейт присутствия устройства). Голый Write-FileAtomic в этих
    # точках пробрасывал СЫРОЙ MethodInvocationException наружу и ронял
    # Use-DeviceStack целиком на ТРАНЗИЕНТНОМ sharing violation (файл в этот
    # момент держит эксклюзивно Take-DeviceLeaseSlot соседнего процесса) -
    # ровно то, чего докстринги обещали не делать.
    #
    # Семантика: транзиентный IO-отказ (IOException/UnauthorizedAccessException,
    # в т.ч. завёрнутый PowerShell в MethodInvocationException) - до $Retries
    # попыток с паузой $DelayMs; исчерпали ЛИБО не-IO отказ - WARN и $false
    # (НЕ throw). Зеркалит python-сторону (driver_factory
    # ::_heartbeat_device_lease: `except OSError -> _warn_lease(... не
    # блокирует прогон)`) - ОДНА семантика, ДВЕ реализации.
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Content,
        [Parameter(Mandatory)][string]$Context,
        [int]$Retries = 3,
        [int]$DelayMs = 100
    )
    for ($attempt = 1; $attempt -le $Retries; $attempt++) {
        try {
            Write-FileAtomic -Path $Path -Content $Content
            return $true
        } catch {
            # PowerShell заворачивает исключение .NET-метода в
            # MethodInvocationException - разворачиваем до настоящего типа, НЕ
            # полагаясь на то, что `catch [System.IO.IOException]` матчит
            # обёртку (поведение зависит от версии движка).
            $ex = $_.Exception
            while ($ex -is [System.Management.Automation.MethodInvocationException] -and $ex.InnerException) {
                $ex = $ex.InnerException
            }
            $transient = ($ex -is [System.IO.IOException]) -or ($ex -is [System.UnauthorizedAccessException])
            if ($transient -and $attempt -lt $Retries) {
                Start-Sleep -Milliseconds $DelayMs
                continue
            }
            $kind = if ($transient) { "транзиентный лок не разошёлся за $Retries попыток" } else { "нетранзиентный отказ" }
            Write-Warning "${Context}: атомарная запись $Path не удалась ($kind): $($ex.Message) - НЕ блокирует вызывающего."
            return $false
        }
    }
    return $false
}

function Resolve-DeviceLeaseTimestamp {
    # N3 B7 (критик-вход rework attempt 2, выравнивание PS/Python фолбэка):
    # ЧИСТАЯ функция парсинга ОДНОГО поля timestamp'а лизы (heartbeat_utc
    # ИЛИ taken_utc) - вызывающий код (Get-DeviceLeaseStatus) пробует
    # heartbeat_utc, при $null-результате (отсутствует ИЛИ НЕ РАЗОБРАН -
    # НЕ различаем на этом уровне) пробует taken_utc - ТА ЖЕ семантика, что
    # Python `_parse_lease_timestamp(heartbeat) or _parse_lease_timestamp(taken)`.
    # РАНЬШЕ PS-сторона фолбэчилась на taken_utc ТОЛЬКО если heartbeat_utc был
    # falsy (пустой/null), но НЕ если он был НЕРАЗБИРАЕМОЙ строкой (catch
    # молча возвращал "free", даже когда taken_utc был валиден) - расхождение
    # с Python, которое эта функция закрывает.
    param($Raw)
    if (-not $Raw) { return $null }
    try {
        if ($Raw -is [datetime]) {
            $dt = $Raw
        } else {
            # RoundtripKind (без AdjustToUniversal - несовместимы, .NET throw'ит
            # на комбинации): формат "o" ВСЕГДА несёт суффикс "Z" -> RoundtripKind
            # сам даёт Kind=Utc без доп. флага (см. докстринг Get-DeviceLeaseStatus
            # оригинала - та же находка M6/F-30, перенесена сюда без изменений).
            $dt = [datetime]::Parse([string]$Raw, [System.Globalization.CultureInfo]::InvariantCulture,
                [System.Globalization.DateTimeStyles]::RoundtripKind)
        }
        if ($dt.Kind -ne [System.DateTimeKind]::Utc) { $dt = $dt.ToUniversalTime() }
        return $dt
    } catch {
        return $null
    }
}

function Resolve-DeviceLeasePid {
    # Non-blocker 3 (критик-раунд 2): `pytest_pid` лизы приходит из JSON и НЕ
    # обязан быть числом - руками правленный файл, оборванная запись, чужая
    # версия схемы дают строку/массив/объект/true. Раньше такое значение
    # доезжало до `Get-Process -Id <не-число>` и падало ПАРАМЕТРИЧЕСКИМ
    # биндингом (терминирующая ошибка МИМО -ErrorAction SilentlyContinue) -
    # Use-DeviceStack заклинивало НАСМЕРТЬ на любом пути (даже путь взятия),
    # и вылезти можно было только `-Release`. Контракт ТЕПЕРЬ: не-число =
    # "pid отсутствует" (ровно тот же исход, что `pytest_pid: null` -
    # стартовое grace-окно / idle по возрасту), симметрично python-стороне
    # (`driver_factory._coerce_lease_pid`).
    #
    # `[bool]` отсекается ОТДЕЛЬНО: `[int]$true` = 1 в PowerShell (валидный
    # PID 1!), а JSON `true` - заведомо не PID.
    param($Raw)
    if ($null -eq $Raw) { return $null }
    if ($Raw -is [bool]) { return $null }
    if ($Raw -is [array] -or $Raw -is [hashtable] -or $Raw -is [pscustomobject]) { return $null }
    try {
        $n = [int]$Raw
    } catch {
        return $null
    }
    if ($n -le 0) { return $null }
    return $n
}

function Test-DeviceLeasePidAlive {
    # N3 B1 (критик-вход rework attempt 2): живость pytest_pid лизы - без
    # новой зависимости psutil (requirements.txt не несёт её, добавлять
    # ради одной проверки нежелательно) и БЕЗ Get-Process на постороннем
    # PID через что-то небезопасное - `Get-Process -Id` -ErrorAction
    # SilentlyContinue -> $null на несуществующем/недоступном PID, ничего
    # не убивает, чистая read-only проверка (в отличие от Python-стороны,
    # где `os.kill(pid, 0)` на Windows - документированная ловушка,
    # реально ЗАВЕРШАЕТ процесс, см. driver_factory._is_pid_alive).
    # Образец подхода - резидентный owner-guard Appium этого файла
    # (Start-Appium): та же готовность доверять факту процесса, не
    # криптографической идентичности PID.
    #
    # Non-blocker 7 (критик-раунд 2) — ПРИНЯТЫЙ ОСТАТОЧНЫЙ РИСК, НЕ недосмотр:
    # переиспользованный ОС номер PID (Windows перевыдаёт номера агрессивно)
    # держит лизу в статусе `active` до TTL 4ч — сверки времени старта
    # процесса против штампа лизы здесь НЕТ (её пришлось бы завести полем
    # схемы лизы `pytest_pid_started_utc`, писать python-стороной через
    # GetProcessTimes и сверять здесь Get-Process .StartTime с допуском на
    # формат/часовой пояс — новая поверхность отказа ради проблемы, чьё
    # ПОСЛЕДСТВИЕ fail-safe: ложно-живой PID БЛОКИРУЕТ взятие, а НЕ выдаёт
    # устройство дважды, и в самом сообщении отказа назван эскейп-хэтч
    # `-Release`). Симметричный комментарий — `driver_factory._is_pid_alive`.
    param([Parameter(Mandatory)][AllowNull()]$ProcId)
    $procIdNum = Resolve-DeviceLeasePid $ProcId
    if ($null -eq $procIdNum) { return $false }
    return [bool](Get-Process -Id $procIdNum -ErrorAction SilentlyContinue)
}

function Get-DeviceLeaseStatus {
    # N3 (B1, критик-вход rework attempt 2 — ПЕРЕПИСАНО): статус лизы стека -
    # ЧИСТАЯ функция (device-free юнит-тестируема напрямую через
    # -PidAliveResolver), возвращает "free"/"active"/"idle"/"reclaimed".
    # Переход active->idle раньше не был реализован (`status` поле лизы
    # НИКТО не переводил в "idle" — писался только "active"): статус ТЕПЕРЬ
    # ВСЕГДА вычисляется ЧИТАТЕЛЕМ по живости `pytest_pid`, поле `status` в
    # самом файле — чисто диагностическое, эта функция его не читает вовсе.
    #
    # Алгоритм (согласован с Python driver_factory._lease_status - ОДНА
    # семантика, ДВЕ реализации, сверено юнитами обеих сторон):
    #   - pytest_pid ЖИВ (PidAliveResolver -> $true) и age <= TTL -> "active"
    #     (TTL — верхняя страховка для ДОЛГОЖИВУЩЕГО процесса, не грейс).
    #   - pytest_pid ОТСУТСТВУЕТ (только что взята, create_driver ещё ни
    #     разу не вызывался) и age <= Grace -> "active" (стартовое окно,
    #     короче TTL/Idle — pytest ещё не успел стартовать).
    #   - ИНАЧЕ (pid мёртв ИЛИ (pid отсутствует и age > Grace) ИЛИ (pid жив,
    #     но heartbeat не обновлялся дольше TTL)) — "idle", пока age <= Idle,
    #     дальше "reclaimed". Окно idle ВСЕГДА меряется от heartbeat_utc
    #     (или taken_utc-фолбэка) — не от момента смерти процесса (который
    #     мы не знаем, только последний heartbeat).
    #
    # `$Lease` - deserialized-объект (PSCustomObject/hashtable) с полями
    # owner_token/taken_utc/heartbeat_utc/pytest_pid; `$null` -> "free".
    # Нечитаемый/отсутствующий timestamp (ОБА heartbeat_utc И taken_utc
    # непарсибельны/отсутствуют) -> "free".
    param(
        $Lease,
        [Parameter(Mandatory)][datetime]$Now,
        [double]$GraceSeconds = $_DEVICE_LEASE_GRACE_SECONDS,
        [double]$IdleSeconds = $_DEVICE_LEASE_IDLE_SECONDS,
        [double]$TtlSeconds = $_DEVICE_LEASE_TTL_SECONDS,
        [scriptblock]$PidAliveResolver = { param($ProcId) Test-DeviceLeasePidAlive -ProcId $ProcId }
    )
    if ($null -eq $Lease) { return "free" }
    # B7: heartbeat_utc, ПРИ ОТКАЗЕ ПАРСИНГА (не только при falsy) - фолбэк
    # на taken_utc. Раньше PS смотрела ТОЛЬКО на falsy heartbeat_utc, ловила
    # неразбираемую-но-непустую строку в общий catch -> "free", расходясь с
    # Python (`_parse_lease_timestamp(hb) or _parse_lease_timestamp(taken)`).
    $last = Resolve-DeviceLeaseTimestamp $Lease.heartbeat_utc
    if ($null -eq $last) { $last = Resolve-DeviceLeaseTimestamp $Lease.taken_utc }
    if ($null -eq $last) { return "free" }
    $age = ($Now - $last).TotalSeconds
    # Non-blocker 3: НЕ-ЧИСЛОВОЙ pytest_pid нормализуется в $null ("отсутствует")
    # ДО любого использования - резолвер живости на не-числе раньше падал
    # биндингом Get-Process и заклинивал весь Use-DeviceStack.
    $pytestPid = Resolve-DeviceLeasePid $Lease.pytest_pid
    if ($null -ne $pytestPid -and (& $PidAliveResolver $pytestPid)) {
        if ($age -le $TtlSeconds) { return "active" }
        # жив, но heartbeat не обновлялся дольше TTL - падает в idle/reclaimed ниже
    } elseif ($null -eq $pytestPid -and $age -le $GraceSeconds) {
        return "active"
    }
    if ($age -gt $IdleSeconds) { return "reclaimed" }
    return "idle"
}

function Get-EmulatorAvdName {
    # Non-blocker 8 (критик-раунд 2): ЧЕСТНЫЙ источник имени AVD для ЖИВОГО
    # серийника - `adb -s <serial> emu avd name` (витнесс соответствия,
    # прямо назван спекой docs/tasks/p3-second-emulator.md п.(г)). Вывод
    # эмуляторной консоли - имя AVD первой строкой + служебное "OK".
    # Fail-soft: adb недоступен (нет ANDROID_HOME/tools в worktree),
    # серийник не отвечает, вывод пуст -> $null, вызывающий сам решает
    # (Test-BySerialBackfill: пропуск с WARN, НЕ фабрикация).
    param([Parameter(Mandatory)][string]$Serial)
    try {
        $out = & "$env:ANDROID_HOME\platform-tools\adb.exe" -s $Serial emu avd name 2>$null
    } catch {
        Write-Warning "Get-EmulatorAvdName: вызов 'adb -s $Serial emu avd name' упал ($_) - ANDROID_HOME/adb.exe недоступен?"
        return $null
    }
    $name = @($out | ForEach-Object { "$_".Trim() } |
        Where-Object { $_ -and $_ -ne "OK" -and $_ -notmatch '^KO' }) | Select-Object -First 1
    if (-not $name) { return $null }
    return $name
}

function Test-BySerialBackfill {
    # N3, хвост N2 (§5 отчёта runs/N2-p3-clone-bringup-stack2-2026-08-20.md):
    # перед стартом стека N>1 - все ЖИВЫЕ серийники обязаны иметь свою
    # запись `by_serial` в state/emulator-session.json, иначе recovery того
    # серийника (driver_factory._read_emulator_session_state) молча
    # фолбэчится на ФЛЭТ top-level поля ("последний записавший стек") и
    # может поднять НЕ ТОТ AVD при рестарте (найдено живьём в N2 -
    # фабричный 5554 поднят ДО мержа N1, флэт-поля перезаписаны клоном).
    #
    # Решение (WARN + бэкфилл, выбор из двух легальных веток спеки
    # docs/tasks/p3-second-emulator.md N3): бэкфилл ИЗ ФЛЭТ top-level полей
    # (gpu/avd_name) - они оказались КОРРЕКТНЫМИ для затронутого серийника в
    # живом инциденте (последнее известное состояние ИМЕННО этого серийника,
    # записанное до введения by_serial). Флэт-поля тоже пусты -> бэкфилл
    # невозможен, только WARN (НЕ throw - это страховка recovery, не гейт
    # присутствия устройства, Use-DeviceStack не блокируется).
    #
    # Non-blocker 8 (критик-раунд 2) — ГРАНИЦА ЧЕСТНОСТИ бэкфилла. Флэт
    # top-level поля пишет `Set-EmulatorSessionState` ОДНИМ payload'ом ВМЕСТЕ
    # с `by_serial[emulator-<свой порт>]` и ОДНИМ И ТЕМ ЖЕ `updated_utc` -
    # значит флэт-поля ВСЕГДА описывают КОНКРЕТНЫЙ серийник, а не "любой".
    # Отсюда правило:
    #   - `by_serial` ОТСУТСТВУЕТ/ПУСТА -> файл ЛЕГАСИ (записан ДО введения
    #     секции, ровно случай инцидента N2 §5) -> флэт - единственное, что
    #     есть, бэкфилл из него ЛЕГАЛЕН (историческое поведение сохранено);
    #   - `by_serial` НЕПУСТА -> флэт принадлежит ДРУГОМУ (уже описанному
    #     ЛИБО намеренно откаченному `Undo-EmulatorSessionStateEntry` после
    #     abort'а RAM-гейта) серийнику -> фабриковать из него avd_name для
    #     ЧУЖОГО серийника ЗАПРЕЩЕНО: спрашиваем ЧЕСТНЫЙ источник
    #     (`adb -s <serial> emu avd name`), а если он недоступен - ПРОПУСК с
    #     WARN.
    # Экземпляр класса, найденный живьём в worktree этой задачи: флэт нёс
    # `avd_name=ao3_test_api34` от аборченного старта, бэкфилл сфабриковал
    # `by_serial['emulator-5556'].avd_name = ao3_test_api34` (стек 2 держит
    # ДРУГОЙ AVD) - т.е. ВОССТАНОВИЛ ровно ту запись, которую
    # `Undo-EmulatorSessionStateEntry` намеренно СНЯЛ, и подсунул recovery
    # заведомо неверный AVD. Стек->AVD жёсткой карты в проекте НЕТ
    # (`$_DEVICE_STACKS` знает только Device/AppiumPort/AllureDir, стек 2 -
    # это и `ao3_test_api29`, и `ao3_corridor_api34` в разных сценариях
    # спеки), поэтому "вычислить правильный avd_name" неоткуда - только
    # спросить устройство либо честно промолчать.
    param(
        [Parameter(Mandatory)][AllowEmptyCollection()][string[]]$LiveSerials,
        [Parameter(Mandatory)][string]$StateFile,
        [scriptblock]$AvdNameResolver = { param($Serial) Get-EmulatorAvdName -Serial $Serial }
    )
    if ($LiveSerials.Count -eq 0) { return }
    if (-not (Test-Path $StateFile)) { return }
    try {
        $raw = [System.IO.File]::ReadAllText($StateFile)
        $data = $raw | ConvertFrom-Json -ErrorAction Stop
    } catch {
        Write-Warning "Use-DeviceStack: emulator-session.json нечитаем ($_) - by_serial-проверка пропущена."
        return
    }
    $bySerial = [ordered]@{}
    if ($data.by_serial) {
        foreach ($prop in $data.by_serial.PSObject.Properties) { $bySerial[$prop.Name] = $prop.Value }
    }
    # Флэт-поля "принадлежат" уже описанному/откаченному серийнику ровно тогда,
    # когда секция by_serial НЕПУСТА (см. блок про границу честности выше).
    $flatIsClaimedByOthers = ($bySerial.Count -gt 0)
    $changed = $false
    foreach ($serial in $LiveSerials) {
        if (-not $bySerial.Contains($serial)) {
            if ($flatIsClaimedByOthers) {
                # Честный источник ИЛИ молчание - фабрикация запрещена.
                $liveAvd = & $AvdNameResolver $serial
                if ($liveAvd) {
                    Write-Warning ("Use-DeviceStack: by_serial-запись для $serial отсутствует - бэкфилл из " +
                        "ЧЕСТНОГО источника 'adb -s $serial emu avd name' (avd_name=$liveAvd); флэт " +
                        "top-level НЕ используется - он описывает другой серийник (by_serial непуста).")
                    $bySerial[$serial] = [ordered]@{
                        gpu = $null; avd_name = $liveAvd; updated_utc = (Get-Date).ToUniversalTime().ToString("o")
                    }
                    $changed = $true
                } else {
                    Write-Warning ("Use-DeviceStack: by_serial-запись для $serial отсутствует, честный источник " +
                        "(adb emu avd name) недоступен, а флэт top-level описывает ДРУГОЙ серийник - бэкфилл " +
                        "ПРОПУЩЕН (фабриковать avd_name чужого стека нельзя: recovery подняло бы неверный AVD). " +
                        "Не блокирует Use-DeviceStack - страховка recovery, не гейт устройства.")
                }
            } elseif ($data.avd_name) {
                Write-Warning ("Use-DeviceStack: by_serial-запись для $serial отсутствует (класс §5 " +
                    "N2-отчёта, легаси-файл без секции by_serial) - бэкфилл из флэт top-level " +
                    "(avd_name=$($data.avd_name), gpu=$($data.gpu)).")
                $bySerial[$serial] = [ordered]@{
                    gpu = $data.gpu; avd_name = $data.avd_name; updated_utc = $data.updated_utc
                }
                $changed = $true
            } else {
                Write-Warning ("Use-DeviceStack: by_serial-запись для $serial отсутствует, и флэт " +
                    "top-level тоже пуст - бэкфилл невозможен, recovery этого серийника может поднять " +
                    "неверный AVD (не блокирует Use-DeviceStack - страховка recovery, не гейт устройства).")
            }
        }
    }
    if ($changed) {
        $payload = [ordered]@{
            gpu = $data.gpu; avd_name = $data.avd_name; updated_utc = $data.updated_utc; by_serial = $bySerial
        } | ConvertTo-Json -Compress -Depth 5
        # N3 B3 (критик-вход rework attempt 2, "тот же класс" - D-0043): раньше
        # голый WriteAllText поверх СУЩЕСТВУЮЩЕГО файла - неатомарная RMW-запись,
        # тот же класс риска партиального/битого чтения, что нашёл критик в
        # Use-DeviceStack. Write-FileAtomic (темп+Replace) закрывает класс здесь тем
        # же ходом.
        # Non-blocker 5 (критик-раунд 2): ...Resilient - докстринг ЭТОЙ функции
        # обещает "НЕ блокирует Use-DeviceStack", а голый Write-FileAtomic
        # пробрасывал сырой MethodInvocationException на транзиентном локе и
        # ронял взятие лизы. Теперь ретрай + WARN.
        Write-FileAtomicResilient -Path $StateFile -Content $payload -Context "Use-DeviceStack (by_serial-бэкфилл)" | Out-Null
    }
}

function Take-DeviceLeaseSlot {
    # N3 B3 (критик-вход rework attempt 2): ЕДИНСТВЕННЫЙ путь мутации файла
    # лизы на ВЗЯТИИ (fresh/reclaimed/битый/пустой). Критик воспроизвёл
    # двойную/тройную выдачу лизы на старой схеме "Remove-Item ПОТОМ
    # CreateNew" (окно между удалением и созданием, где ДРУГОЙ процесс
    # проходит ту же проверку "reclaimed -> беру" и тоже удаляет+создаёт).
    #
    # Схема: [System.IO.File]::Open(..., CreateNew) — арбитр для
    # ДЕЙСТВИТЕЛЬНО отсутствующего файла (ОС гарантирует РОВНО один успешный
    # Open, это НЕ меняется относительно исходной реализации). Если файл УЖЕ
    # существует (reclaimed/битый JSON/пустой/чужая живая лиза — на этом шаге
    # НЕ различаем причину), открываем его же ЭКСКЛЮЗИВНО
    # (FileMode.Open, FileShare.None) — пока хэндл открыт, ЛЮБОЙ другой
    # процесс (свой CreateNew ИЛИ свой Open) получает IOException
    # (sharing violation) НЕМЕДЛЕННО, никто не может одновременно с нами
    # решить "лиза протухла, беру". Статус ПЕРЕОЦЕНИВАЕТСЯ ЗАНОВО внутри
    # этой секции на свежем $Now — решение принимается на актуальных данных,
    # не на данных, прочитанных ДО захвата хэндла (могли устареть за время
    # ожидания).
    #
    # B6 (критик-вход rework attempt 2): 0-байтный/пустой файл (Get-Content
    # -Raw возвращает $null на пустом файле — известная PowerShell-ловушка)
    # ТЕПЕРЬ явно трактуется как unparseable (не как "лиза без данных ->
    # непонятно") — без этой ветки [System.IO.File]::Open(CreateNew) на
    # уже-существующем 0-байтном файле раньше throw'ил "гонка, повтори"
    # ВЕЧНО (повтор снова видит тот же 0-байтный файл, снова throw).
    #
    # Возвращает [pscustomobject]@{ Outcome = 'won'|'adopted'|'raced'|'live'; Lease = <PSCustomObject|$null>; Status = <string|$null> }.
    # 'won' — слот наш, $Payload записан. 'raced' — sharing violation, кто-то
    # ДРУГОЙ держит критическую секцию ПРЯМО СЕЙЧАС (транзиент, не "лиза
    # жива") — вызывающий код различает это от 'live' (реально живая
    # активная/idle лиза, обычный конфликт владения) в сообщении отказа
    # (B6: "различай «файл существует» от «проиграна гонка»").
    #
    # БЛОКЕР B-R2-1 (критик-раунд 2) — АДОПЦИЯ. `-AdoptOwnerLabel <label>`
    # включает ветку "продолжение ТИКЕТА между одноразовыми процессами":
    # существующая ЖИВАЯ (active/idle) лиза ТОГО ЖЕ owner_label, чей
    # `pytest_pid` отсутствует ИЛИ мёртв, ПЕРЕЗАПИСЫВАЕТСЯ $Payload'ом ПОД ТЕМ
    # ЖЕ эксклюзивным хэндлом (FileShare.None) - никакого окна между
    # "решил адоптировать" и "записал". Возвращает Outcome='adopted' и
    # PreviousToken (прежний owner_token, для INFO-строки вызывающего).
    # ЖИВОЙ `pytest_pid` адопцию НЕ допускает НИКОГДА (Outcome='live') -
    # это настоящий идущий прогон, а не брошенный тикет.
    param(
        [Parameter(Mandatory)][string]$LeaseFile,
        [Parameter(Mandatory)][string]$Payload,
        [Parameter(Mandatory)][datetime]$Now,
        [Parameter(Mandatory)][scriptblock]$PidAliveResolver,
        [string]$AdoptOwnerLabel = "",
        [string]$OwnToken = ""
    )
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    $bytes = $utf8NoBom.GetBytes($Payload)
    $dir = Split-Path -Parent $LeaseFile
    if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }

    try {
        $fs = [System.IO.File]::Open($LeaseFile, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
        try { $fs.Write($bytes, 0, $bytes.Length) } finally { $fs.Close() }
        return [pscustomobject]@{ Outcome = "won"; Lease = $null; Status = $null }
    } catch [System.IO.IOException] {
        # файл уже существует - НЕ throw'им здесь, переоцениваем под замком ниже
    }

    try {
        $fs = [System.IO.File]::Open($LeaseFile, [System.IO.FileMode]::Open, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
    } catch [System.IO.IOException] {
        return [pscustomobject]@{ Outcome = "raced"; Lease = $null; Status = $null }
    }
    try {
        $reader = New-Object System.IO.StreamReader($fs, $utf8NoBom, $false, 1024, $true)
        $raw = $reader.ReadToEnd()
        $reader.Dispose()
        $existingLease = $null
        $unparseable = [string]::IsNullOrEmpty($raw)  # B6: пустой файл = битый
        if (-not $unparseable) {
            try { $existingLease = $raw | ConvertFrom-Json -ErrorAction Stop } catch { $unparseable = $true }
        }
        $freshStatus = if ($unparseable) { "free" } else { Get-DeviceLeaseStatus -Lease $existingLease -Now $Now -PidAliveResolver $PidAliveResolver }
        if ($freshStatus -eq "free" -or $freshStatus -eq "reclaimed") {
            $fs.Seek(0, [System.IO.SeekOrigin]::Begin) | Out-Null
            $fs.SetLength(0)
            $fs.Write($bytes, 0, $bytes.Length)
            $fs.Flush()
            return [pscustomobject]@{ Outcome = "won"; Lease = $existingLease; Status = $freshStatus }
        }
        # active/idle - лиза ЖИВА. Своя ПО ТОКЕНУ - отдаём вызывающему как есть
        # ('live', own-token ветка). Своя ПО owner_label с НЕживым pytest_pid -
        # АДОПЦИЯ прямо здесь, под тем же эксклюзивным хэндлом (B-R2-1).
        $ownedByToken = $OwnToken -and $existingLease -and ($existingLease.owner_token -eq $OwnToken)
        if (-not $ownedByToken -and $AdoptOwnerLabel -and $existingLease -and ($existingLease.owner_label -eq $AdoptOwnerLabel)) {
            $leasePid = Resolve-DeviceLeasePid $existingLease.pytest_pid
            $pidAlive = ($null -ne $leasePid) -and (& $PidAliveResolver $leasePid)
            if (-not $pidAlive) {
                $fs.Seek(0, [System.IO.SeekOrigin]::Begin) | Out-Null
                $fs.SetLength(0)
                $fs.Write($bytes, 0, $bytes.Length)
                $fs.Flush()
                return [pscustomobject]@{
                    Outcome = "adopted"; Lease = $existingLease; Status = $freshStatus
                    PreviousToken = $existingLease.owner_token; PreviousPid = $leasePid
                }
            }
        }
        # чужая (или своя-по-метке с ЖИВЫМ прогоном) - файл НЕ трогаем,
        # возвращаем прочитанное как есть, решение за вызывающим.
        return [pscustomobject]@{ Outcome = "live"; Lease = $existingLease; Status = $freshStatus }
    } finally {
        $fs.Dispose()
    }
}

function Invoke-DeviceLeaseAdoption {
    # БЛОКЕР B-R2-1 (критик-раунд 2): ЕДИНСТВЕННАЯ реализация адопции - и для
    # дефолтного вызова, и для `-Resume` (синоним). Выпускает НОВЫЙ
    # owner_token и отдаёт запись Take-DeviceLeaseSlot'у с
    # `-AdoptOwnerLabel`, который ПЕРЕПРОВЕРЯЕТ владение и живость pid ПОД
    # ЭКСКЛЮЗИВНЫМ хэндлом и пишет там же - между "решил" и "записал" окна нет.
    #
    # `pytest_pid` новой записи = $null НАРОЧНО: прежний pytest мёртв, новый
    # ещё не стартовал - лиза заново входит в стартовое grace-окно, а штамп
    # реального PID ставит python-чокпоинт (`driver_factory
    # ::_heartbeat_device_lease`) на первом create_driver. Это же чинит
    # сценарий критика "второй проход через 5 минут" (прежде: своя же лиза
    # из нового процесса читалась как чужая -> THROWN).
    param(
        [Parameter(Mandatory)][int]$N,
        [Parameter(Mandatory)][string]$LeaseFile,
        [Parameter(Mandatory)][datetime]$Now,
        [Parameter(Mandatory)][string]$OwnerLabel,
        [AllowEmptyString()][string]$OwnToken = "",
        [Parameter(Mandatory)][string]$Device,
        [Parameter(Mandatory)][string]$AppiumUrl,
        [Parameter(Mandatory)][scriptblock]$TokenProvider,
        [Parameter(Mandatory)][scriptblock]$PidAliveResolver
    )
    $newToken = & $TokenProvider
    $payload = [ordered]@{
        owner_token = $newToken; owner_label = $OwnerLabel
        taken_utc = $Now.ToString("o"); heartbeat_utc = $Now.ToString("o")
        pytest_pid = $null; status = "active"
        device = $Device; appium_url = $AppiumUrl
    } | ConvertTo-Json -Compress

    $result = Take-DeviceLeaseSlot -LeaseFile $LeaseFile -Payload $payload -Now $Now `
        -PidAliveResolver $PidAliveResolver -AdoptOwnerLabel $OwnerLabel -OwnToken $OwnToken
    switch ($result.Outcome) {
        "adopted" {
            $env:AO3_DEVICE_LEASE_TOKEN = $newToken
            $prevPid = if ($null -ne $result.PreviousPid) { $result.PreviousPid } else { "отсутствовал" }
            Write-Host ("Use-DeviceStack: своя лиза стека $N ПРОДОЛЖЕНА адопцией (owner_label=$OwnerLabel, " +
                "прежний owner_token=$($result.PreviousToken), прежний pytest_pid=$prevPid не жив) - " +
                "выпущен новый токен.") -ForegroundColor Green
        }
        "won" {
            # Между чтением и захватом лиза успела протухнуть/исчезнуть -
            # обычное взятие, не адопция.
            $env:AO3_DEVICE_LEASE_TOKEN = $newToken
            Write-Host "Use-DeviceStack: лиза стека $N взята (owner=$OwnerLabel; прежняя запись протухла к моменту захвата)." -ForegroundColor Green
        }
        "raced" {
            throw ("Use-DeviceStack: лиза стека $N временно заблокирована другим процессом " +
                "(гонка ВЗЯТИЯ - кто-то читает/пишет файл лизы прямо сейчас) - повтори вызов " +
                "через секунду. Если это НЕ транзиент (повторяется постоянно) - проверь, не " +
                "завис ли другой процесс, и при необходимости используй -Release.")
        }
        "live" {
            $owner = if ($result.Lease.owner_label) { $result.Lease.owner_label } else { "неизвестен" }
            $livePid = Resolve-DeviceLeasePid $result.Lease.pytest_pid
            if ($OwnToken -and $result.Lease.owner_token -eq $OwnToken) {
                $env:AO3_DEVICE_LEASE_TOKEN = $OwnToken
                Write-Host "Use-DeviceStack: лиза стека $N уже твоя (тот же токен, взята параллельно)." -ForegroundColor Green
            } elseif ($result.Lease.owner_label -eq $OwnerLabel) {
                throw ("Use-DeviceStack: стек $N занят ЖИВЫМ прогоном владельца $owner (pytest_pid=$livePid) - " +
                    "дождись завершения прогона либо сними лизу от владельца: Use-DeviceStack -N $N -Release.")
            } else {
                throw "Use-DeviceStack: стек $N занят чужой лизой (владелец: $owner) - ждать нечего, лиза жива."
            }
        }
        default {
            throw "Use-DeviceStack: Take-DeviceLeaseSlot вернул неожиданный Outcome='$($result.Outcome)' - внутренняя ошибка."
        }
    }
}

function Use-DeviceStack {
    # N3: каноническая форма переключения на device-стек 1/2 - выставляет
    # AO3_DEVICE/APPIUM_URL/ALLURE_RESULTS ПЕР-СТЕК и берёт/снимает машинную
    # лизу (`state/device-lease-<N>.json`, ОТДЕЛЬНЫЙ файл на стек).
    #
    # B3 (критик-вход rework attempt 2): ВЗЯТИЕ свободной/протухшей/битой
    # лизы идёт ЧЕРЕЗ Take-DeviceLeaseSlot (эксклюзивная критическая секция,
    # не Remove-Item+CreateNew — старая схема давала окно двойной выдачи,
    # критик воспроизвёл эмпирически). Перезапись СВОЕЙ живой лизы
    # (heartbeat/idle->active) — через Write-FileAtomic (темп+Replace, не
    # голый WriteAllText — партиальная запись НЕ должна быть видна читателю).
    #
    # ВЛАДЕНИЕ = owner_label (user@host) + СВЕЖЕСТЬ (дизайн-решение Lead,
    # критик-раунд 2, БЛОКЕР B-R2-1). Единица владения - ТИКЕТ, а не процесс;
    # продолжение тикета между одноразовыми PowerShell-процессами
    # (констрейнт 6 плана - tasks.ps1 дот-сорсится КАЖДЫМ вызовом) идёт через
    # АДОПЦИЮ:
    #   - лиза ТОГО ЖЕ owner_label, чей `pytest_pid` ОТСУТСТВУЕТ или МЁРТВ
    #     (grace/idle), продолжается ДЕФОЛТНЫМ вызовом `Use-DeviceStack -N <N>`:
    #     выпускается НОВЫЙ owner_token, файл атомарно перезаписывается ПОД
    #     ЭКСКЛЮЗИВНЫМ take-локом (Take-DeviceLeaseSlot -AdoptOwnerLabel),
    #     печатается INFO с ПРЕЖНИМ токеном;
    #   - `pytest_pid` ЖИВ -> ОТКАЗ ВСЕГДА (и с `-Resume` тоже): это идущий
    #     прогон, а не брошенный тикет; сообщение несёт имя владельца, PID и
    #     совет "дождись завершения прогона либо -Release от владельца".
    # РАНЬШЕ (B2 attempt 2) продолжение требовало явного `-Resume`, а без него
    # своя же лиза из НОВОГО процесса читалась как "чужая активная" и
    # Use-DeviceStack ОТКАЗЫВАЛ - критик воспроизвёл ровно это на связке
    # "взял процессом А -> pytest в процессе Б" и на "второй проход через 5
    # минут". `-Resume` СОХРАНЁН как ЯВНЫЙ СИНОНИМ той же адопции (семантика
    # идентична дефолтной, жёсткий гейт живого pid тот же) - двух РАЗНЫХ путей
    # взятия быть не должно.
    #
    # $env:AO3_DEVICE_LEASE_TOKEN по-прежнему наследуется ДОЧЕРНИМИ процессами
    # ЭТОЙ ЖЕ powershell-сессии (быстрый путь "лиза точно моя, тот же токен");
    # owner_token в файле переживает смерть процесса и служит опорой адопции.
    #
    # `-Release` - ЕДИНСТВЕННАЯ ручная форма снятия (permission hygiene):
    # безусловно удаляет файл лизы стека (явное человеческое действие,
    # эскейп-хэтч для застрявшего стека - НЕ проверяет владение, тот же
    # дух, что "снятие" вручную любого другого стейл-лока в этом файле,
    # AT-BUG-012 Clear-EmulatorStaleLocks).
    #
    # Non-blocker 1 (критик-вход rework attempt 2): -WhatIf ТЕПЕРЬ честен -
    # КАЖДАЯ мутирующая ветка (Release/heartbeat/idle->active/take) гейтится
    # `$PSCmdlet.ShouldProcess`, отказ -> `return` ДО экспорта env-переменных
    # (раньше -WhatIf РЕАЛЬНО брал лизу, SupportsShouldProcess был пустым
    # обещанием — паттерн ShouldProcess зеркалит Stop-NodeProcesses выше).
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [Parameter(Mandatory)][ValidateSet(1, 2)][int]$N,
        [switch]$Release,
        [switch]$Resume,
        [scriptblock]$NowProvider = { (Get-Date).ToUniversalTime() },
        [scriptblock]$TokenProvider = { [guid]::NewGuid().ToString() },
        [scriptblock]$LiveSerialsProvider = { Get-DeviceSerials },
        [scriptblock]$PidAliveResolver = { param($ProcId) Test-DeviceLeasePidAlive -ProcId $ProcId },
        [scriptblock]$AvdNameResolver = { param($Serial) Get-EmulatorAvdName -Serial $Serial },
        [string]$StateFile = "$root\state\emulator-session.json",
        [string]$LeaseFile = ""
    )
    $cfg = $_DEVICE_STACKS[$N]
    $leaseFile = if ($LeaseFile) { $LeaseFile } else { "$root\state\device-lease-$N.json" }
    $appiumUrl = "http://127.0.0.1:$($cfg.AppiumPort)"
    $ownerLabel = "$env:USERNAME@$env:COMPUTERNAME"

    if ($Release) {
        if (-not (Test-Path $leaseFile)) {
            Write-Warning "Use-DeviceStack -Release: лизы стека $N нет ($leaseFile) - нечего снимать."
            return
        }
        if (-not $PSCmdlet.ShouldProcess($leaseFile, "Release device lease stack $N")) { return }
        Remove-Item $leaseFile -Force
        Remove-Item Env:\AO3_DEVICE_LEASE_TOKEN -ErrorAction SilentlyContinue
        Write-Host "Use-DeviceStack: лиза стека $N снята (-Release)." -ForegroundColor Green
        return
    }

    if ($N -gt 1) {
        # @(...) форсирует массив: голый `& $LiveSerialsProvider` на ПУСТОМ
        # `@()`-выводе провайдера даёт $null, не пустой массив (классическая
        # PowerShell-ловушка "пустой массив -> $null через pipeline") -
        # Test-BySerialBackfill -LiveSerials Mandatory упал бы биндингом.
        $liveSerials = @(& $LiveSerialsProvider)
        Test-BySerialBackfill -LiveSerials $liveSerials -StateFile $StateFile -AvdNameResolver $AvdNameResolver
    }

    $now = & $NowProvider
    $lease = $null
    $leaseFileUnparseable = $false
    if (Test-Path $leaseFile) {
        try {
            $raw = Get-Content $leaseFile -Raw
            if ([string]::IsNullOrEmpty($raw)) {
                # B6 (критик-вход rework attempt 2): 0-байтный/пустой файл -
                # Get-Content -Raw возвращает $null на пустом файле (известная
                # PowerShell-ловушка) - explicit unparseable, НЕ молчаливое
                # ConvertFrom-Json $null (которое раньше НЕ ставило флаг и
                # давало вечный ложный "гонка, повтори вызов").
                $leaseFileUnparseable = $true
            } else {
                $lease = $raw | ConvertFrom-Json -ErrorAction Stop
            }
        } catch {
            Write-Warning "Use-DeviceStack: лиза стека $N ($leaseFile) - битый JSON, трактуется как отсутствующая."
            $lease = $null
            $leaseFileUnparseable = $true
        }
    }
    $status = if ($leaseFileUnparseable) { "free" } else { Get-DeviceLeaseStatus -Lease $lease -Now $now -PidAliveResolver $PidAliveResolver }
    $ownToken = $env:AO3_DEVICE_LEASE_TOKEN

    # B-R2-1: -Resume - ЯВНЫЙ СИНОНИМ дефолтного поведения (адопция своей
    # лизы по owner_label). Отдельного пути НЕТ - флаг сохранён только ради
    # обратной совместимости уже написанных вызовов/промптов.
    if ($Resume) {
        Write-Host ("Use-DeviceStack -Resume: синоним поведения по умолчанию (продолжение своей лизы " +
            "по owner_label = $ownerLabel) - отдельного пути взятия нет, гейт живого pytest_pid тот же.") -ForegroundColor Cyan
    }

    $isOwn = ($null -ne $lease) -and $ownToken -and ($lease.owner_token -eq $ownToken)
    # B-R2-1: своя ли лиза ПО МЕТКЕ ВЛАДЕЛЬЦА и идёт ли под ней ЖИВОЙ прогон.
    $sameOwnerLabel = ($null -ne $lease) -and (-not $leaseFileUnparseable) -and ($lease.owner_label -eq $ownerLabel)
    $leasePid = if ($null -ne $lease) { Resolve-DeviceLeasePid $lease.pytest_pid } else { $null }
    $leasePidAlive = ($null -ne $leasePid) -and (& $PidAliveResolver $leasePid)

    switch ($status) {
        "active" {
            if (-not $isOwn) {
                if ($sameOwnerLabel -and -not $leasePidAlive) {
                    if (-not $PSCmdlet.ShouldProcess($leaseFile, "Adopt own device lease stack $N (owner_label match, pytest_pid not alive)")) { return }
                    Invoke-DeviceLeaseAdoption -N $N -LeaseFile $leaseFile -Now $now `
                        -OwnerLabel $ownerLabel -OwnToken $ownToken -Device $cfg.Device -AppiumUrl $appiumUrl `
                        -TokenProvider $TokenProvider -PidAliveResolver $PidAliveResolver
                    break
                }
                $owner = if ($lease.owner_label) { $lease.owner_label } else { "неизвестен" }
                if ($sameOwnerLabel) {
                    throw ("Use-DeviceStack: стек $N занят ЖИВЫМ прогоном владельца $owner (pytest_pid=$leasePid) - " +
                        "дождись завершения прогона либо сними лизу от владельца: Use-DeviceStack -N $N -Release.")
                }
                throw "Use-DeviceStack: стек $N занят чужой АКТИВНОЙ лизой (владелец: $owner) - ждать нечего, лиза жива."
            }
            if (-not $PSCmdlet.ShouldProcess($leaseFile, "Renew (heartbeat) device lease stack $N")) { return }
            $updated = [ordered]@{
                owner_token = $lease.owner_token; owner_label = $ownerLabel
                taken_utc = $lease.taken_utc; heartbeat_utc = $now.ToString("o")
                pytest_pid = $lease.pytest_pid; status = "active"
                device = $cfg.Device; appium_url = $appiumUrl
            } | ConvertTo-Json -Compress
            # Non-blocker 5: heartbeat - страховка свежести, НЕ гейт: транзиентный
            # лок даёт WARN, не сырой MethodInvocationException наружу.
            Write-FileAtomicResilient -Path $leaseFile -Content $updated -Context "Use-DeviceStack (heartbeat стека $N)" | Out-Null
            Write-Host "Use-DeviceStack: лиза стека $N уже твоя (активна), heartbeat обновлён." -ForegroundColor Green
        }
        "idle" {
            if (-not $isOwn) {
                if ($sameOwnerLabel -and -not $leasePidAlive) {
                    if (-not $PSCmdlet.ShouldProcess($leaseFile, "Adopt own device lease stack $N (owner_label match, pytest_pid not alive)")) { return }
                    Invoke-DeviceLeaseAdoption -N $N -LeaseFile $leaseFile -Now $now `
                        -OwnerLabel $ownerLabel -OwnToken $ownToken -Device $cfg.Device -AppiumUrl $appiumUrl `
                        -TokenProvider $TokenProvider -PidAliveResolver $PidAliveResolver
                    break
                }
                $owner = if ($lease.owner_label) { $lease.owner_label } else { "неизвестен" }
                if ($sameOwnerLabel) {
                    # idle с ЖИВЫМ pid = heartbeat протух за TTL, но процесс жив.
                    throw ("Use-DeviceStack: стек $N занят ЖИВЫМ прогоном владельца $owner (pytest_pid=$leasePid, " +
                        "heartbeat протух) - дождись завершения прогона либо сними лизу от владельца: " +
                        "Use-DeviceStack -N $N -Release.")
                }
                throw ("Use-DeviceStack: стек $N в ожидании (idle), чужой владелец ($owner) может вернуться - " +
                    "жди либо запроси освобождение (Use-DeviceStack -N $N -Release).")
            }
            if (-not $PSCmdlet.ShouldProcess($leaseFile, "Resume device lease stack $N (idle -> active, B28)")) { return }
            $updated = [ordered]@{
                owner_token = $lease.owner_token; owner_label = $ownerLabel
                taken_utc = $lease.taken_utc; heartbeat_utc = $now.ToString("o")
                pytest_pid = $null; status = "active"
                device = $cfg.Device; appium_url = $appiumUrl
            } | ConvertTo-Json -Compress
            Write-FileAtomicResilient -Path $leaseFile -Content $updated -Context "Use-DeviceStack (idle->active стека $N)" | Out-Null
            $env:AO3_DEVICE_LEASE_TOKEN = $lease.owner_token
            Write-Host "Use-DeviceStack: своя idle-лиза стека $N принята (B28), возвращаю в active." -ForegroundColor Green
        }
        default {
            # "free" ИЛИ "reclaimed" - берём через Take-DeviceLeaseSlot (B3).
            # Non-blocker 4: реклейм СВОЕЙ протухшей лизы - тихий (Write-
            # Verbose, БЕЗ log_append); реклейм ЧУЖОЙ брошенной - громкий
            # (Write-Warning + log_append orchestrator-строка) - план N3
            # прямо разводит эти два случая, owner_label лизы (сохранённой
            # ДО протухания) даёт достаточный сигнал "свой ли был владелец".
            if ($status -eq "reclaimed") {
                $wasOwn = $lease -and ($lease.owner_label -eq $ownerLabel)
                if ($wasOwn) {
                    Write-Verbose "Use-DeviceStack: своя протухшая лиза стека $N реклеймится (тихо, own-reclaim, non-blocker 4)."
                } else {
                    $staleOwner = if ($lease -and $lease.owner_label) { $lease.owner_label } else { "неизвестен" }
                    Write-Warning "Use-DeviceStack: лиза стека $N истекла (reclaimed, владелец: $staleOwner) - беру заново."
                    $logScript = "$root\scripts\log_append.py"
                    if (Test-Path $logScript) {
                        try {
                            $pythonExe = if (Test-Path "$venv\python.exe") { "$venv\python.exe" } else { "python" }
                            & $pythonExe $logScript orchestrator "p3-second-emulator N3: device-lease reclaim" `
                                "Use-DeviceStack" "стек $N reclaimed (владелец: $staleOwner) -> взят $ownerLabel" 2>$null | Out-Null
                        } catch {
                            # fail-soft (докстринг выше): отсутствие интерпретатора/скрипта не
                            # роняет взятие лизы, только теряет запись в журнал.
                        }
                    }
                }
            }
            $newToken = & $TokenProvider
            $payload = [ordered]@{
                owner_token = $newToken; owner_label = $ownerLabel
                taken_utc = $now.ToString("o"); heartbeat_utc = $now.ToString("o")
                pytest_pid = $null; status = "active"
                device = $cfg.Device; appium_url = $appiumUrl
            } | ConvertTo-Json -Compress

            if (-not $PSCmdlet.ShouldProcess($leaseFile, "Take device lease stack $N")) { return }
            # B-R2-1: -AdoptOwnerLabel и здесь - между чтением (free/reclaimed) и
            # захватом хэндла лиза могла СТАТЬ живой; если она при этом СВОЯ по
            # метке и без живого pytest_pid, правильный исход - адопция, а не
            # отказ "занято".
            $result = Take-DeviceLeaseSlot -LeaseFile $leaseFile -Payload $payload -Now $now `
                -PidAliveResolver $PidAliveResolver -AdoptOwnerLabel $ownerLabel -OwnToken $ownToken
            switch ($result.Outcome) {
                "won" {
                    $env:AO3_DEVICE_LEASE_TOKEN = $newToken
                    Write-Host "Use-DeviceStack: лиза стека $N взята (owner=$ownerLabel)." -ForegroundColor Green
                }
                "adopted" {
                    $env:AO3_DEVICE_LEASE_TOKEN = $newToken
                    $prevPid = if ($null -ne $result.PreviousPid) { $result.PreviousPid } else { "отсутствовал" }
                    Write-Host ("Use-DeviceStack: своя лиза стека $N ПРОДОЛЖЕНА адопцией под замком " +
                        "(owner_label=$ownerLabel, прежний owner_token=$($result.PreviousToken), " +
                        "прежний pytest_pid=$prevPid не жив) - выпущен новый токен.") -ForegroundColor Green
                }
                "raced" {
                    # B6: РАЗЛИЧАЕМ "файл существует" (обычный путь взятия
                    # free/reclaimed выше) от "проиграна гонка" (sharing
                    # violation - кто-то ДРУГОЙ держит критическую секцию
                    # ПРЯМО СЕЙЧАС, транзиент).
                    throw ("Use-DeviceStack: лиза стека $N временно заблокирована другим процессом " +
                        "(гонка ВЗЯТИЯ - кто-то читает/пишет файл лизы прямо сейчас) - повтори вызов " +
                        "через секунду. Если это НЕ транзиент (повторяется постоянно) - проверь, не " +
                        "завис ли другой процесс, и при необходимости используй -Release.")
                }
                "live" {
                    if ($ownToken -and $result.Lease.owner_token -eq $ownToken) {
                        # редкий, но легальный случай: под замком обнаружилась
                        # СВОЯ же (уже взятая параллельно этим же токеном) лиза.
                        $env:AO3_DEVICE_LEASE_TOKEN = $ownToken
                        Write-Host "Use-DeviceStack: лиза стека $N уже твоя (взята параллельно, тот же токен)." -ForegroundColor Green
                    } else {
                        $owner = if ($result.Lease.owner_label) { $result.Lease.owner_label } else { "неизвестен" }
                        if ($result.Lease.owner_label -eq $ownerLabel) {
                            # B-R2-1: своя по метке, но с ЖИВЫМ прогоном - адопция
                            # запрещена ВСЕГДА (Take-DeviceLeaseSlot уже отказал в ней
                            # под замком, вернув 'live').
                            $livePid = Resolve-DeviceLeasePid $result.Lease.pytest_pid
                            throw ("Use-DeviceStack: стек $N занят ЖИВЫМ прогоном владельца $owner " +
                                "(pytest_pid=$livePid) - дождись завершения прогона либо сними лизу от " +
                                "владельца: Use-DeviceStack -N $N -Release.")
                        }
                        if ($result.Status -eq "active") {
                            throw "Use-DeviceStack: стек $N занят чужой АКТИВНОЙ лизой (владелец: $owner) - ждать нечего, лиза жива."
                        } else {
                            throw ("Use-DeviceStack: стек $N в ожидании (idle), чужой владелец ($owner) может вернуться - " +
                                "жди либо запроси освобождение (Use-DeviceStack -N $N -Release).")
                        }
                    }
                }
                default {
                    throw "Use-DeviceStack: Take-DeviceLeaseSlot вернул неожиданный Outcome='$($result.Outcome)' - внутренняя ошибка."
                }
            }
        }
    }

    $env:AO3_DEVICE = $cfg.Device
    $env:APPIUM_URL = $appiumUrl
    $env:ALLURE_RESULTS = "$root\$($cfg.AllureDir)"
    Write-Host ("Use-DeviceStack: стек $N - AO3_DEVICE=$($env:AO3_DEVICE) APPIUM_URL=$($env:APPIUM_URL) " +
        "ALLURE_RESULTS=$($env:ALLURE_RESULTS)") -ForegroundColor Cyan
}

Write-Host "Tasks loaded: Start-Emulator, Install-MitmCA, Start-Appium, Test-AppiumHealthy, Get-DeviceSerials, Stop-NodeProcesses, Ensure-BridgeHarness, Install-App, Invoke-Smoke, Invoke-Suite, Invoke-Pytest, Show-Report, Get-Device, Use-DeviceStack" -ForegroundColor Green
