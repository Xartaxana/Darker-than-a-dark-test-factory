# N3 постмерж device-witness — 2026-08-21 (Lead/Fable, главный чекаут)

Условия приёмки мержа — критик-раунд 5, fixes[2] (журнал
p3-n3-lease-usedevicestack, accepted 2026-08-20T23:36). Все прогоны —
каноническими формами из главного чекаута, мерж 4cc913fa + хвосты
ba271e3e/9380e805/e584b910.

## 1. Стек 2 С лизой (api29, первое живое Use-DeviceStack -N 2)

- `Start-Emulator -Port 5556 -AvdName 'ao3_test_api29'` — снапшот-бут
  45с-окна, «Emulator booted (emulator-5556)», IPv4-пин OK. RAM-гейт
  живьём: pre-start дефолт для порта ≠5554 (3.5 GB) пройден при
  6.37 GB free.
- `Use-DeviceStack -N 2` (взятие): «лиза стека 2 взята
  (owner=user@WIN-35QE0JOJJUA)», env AO3_DEVICE=emulator-5556
  APPIUM_URL=http://127.0.0.1:4725 ALLURE_RESULTS=...allure-results-2.
- `Start-Appium -Port 4725` — первый подъём второго Appium: 60с
  дефолт-таймаута НЕ ХВАТИЛО (холодный npx-старт второго инстанса
  ~90-120с), /status ready дождались внешним поллом 120с. Хвост в
  очередь: поднять дефолт -TimeoutSeconds или задокументировать.
- `Use-DeviceStack -N 2` (новый процесс): «своя лиза стека 2 ПРОДОЛЖЕНА
  адопцией (... прежний pytest_pid=отсутствовал не жив) — выпущен новый
  токен» — живая ветка адопции с ротацией токена.
- `Install-App` — Success (streamed install на api29).
- `Invoke-Pytest tests\test_smoke.py::test_app_launches_and_loads_ao3 -q`
  → **1 passed in 55.23s**, PYTEST_EXIT=0. Лиза после прогона:
  `pytest_pid: 20200`, status active, device emulator-5556,
  appium_url :4725 — чокпоинт штамповал живьём.
- `Use-DeviceStack -N 2 -Release` — «лиза стека 2 снята», файл удалён.

## 2. Стек 1 БЕЗ лизы (легаси-дефолт)

- `Start-Emulator -Port 5554` (дефолтный AVD api34) — снапшот-бут OK,
  stale-локи AVD сняты самим Start-Emulator.
- `Start-Appium` (без -Port → 4723): резидентный guard живьём — «Appium
  уже слушает :4723 — PID 12104, uptime 17:05», «резидентный (:4723),
  /status ready» — чужой (фабричный) Appium НЕ перезапущен (F1-ветка).
- Тот же смок легаси-формой (без Use-DeviceStack) →
  **1 passed in 28.04s**, PYTEST_EXIT=0. Файл state/device-lease-1.json
  НЕ создан (легаси-путь лизу не требует и не заводит).

## 3. Живой post-start-abort (одноразовый api26 @5558)

`Start-Emulator -Port 5558 -AvdName 'ao3_test_api26'
-MinFreeGBPreStart 0.1 -MinFreeGBPostStart 99`:
бут → «RAM-гейт (post-start) — free 1.59 GB < 99 GB — abort, гашу
только что поднятый emulator-5558 ... чистое гашение emu kill» →
«by_serial[emulator-5558] снята из emulator-session.json» → throw.
Соседи не тронуты (гейт гасит ТОЛЬКО свой серийник); после пробы
Get-DeviceSerials показывал только живые стеки.

## 4. Сверка мусора state/ по ФС (gitignore скрывает лизы от git)

`ls state/ | grep lease|lock|tmp-|bak-` → только loop.lock /
loop-lock-reaps.json (фабричные, штатно). Ни лиз, ни CAS-локов, ни
темп/бэкап-файлов не осталось.

## Найденный и починенный по дороге дефект (класс M1)

Полный канон scripts/tests ВИС в главном чекауте (>10 мин; в worktree
171с): проба ram_gate, прошедшая post-start гейт, доходила до реального
`adb root`/`adb wait-for-device` ВНУТРИ Set-GuestIPv4Pin (шва не было),
subprocess-пайп держался внуком после kill. Фикс e584b910: шов
`-GuestPinner` (+ позитивный оракул PIN_SEAM_REACHED, контракт швов
_ps1_helpers дополнен, замороженный префикс replay-пина Б9а). Журнал:
defect_found ref=p3-n3-lease-usedevicestack + accepted
(канон 2011 passed, 1 skipped in 176.82s).

## Инциденты среды (не разрешены, оператору)

1. **4 осиротевших `adb wait-for-device`-клиента** (PID 13416, 12984,
   5488, 16712) от таймаут-прогонов до фикса. Безвредны (ждут вечно,
   порт/устройство не держат); Stop-Process отклонён классификатором
   среды — уборка руками оператора при случае.
2. **Сирота-лаунчер `emulator.exe` PID 21248** (создан 2026-08-21
   00:16:12, родитель мёртв): CommandLine несёт ПУТЬ ИЗ WORKTREE
   `...agent-a60a4639232aedc27\tools\...emulator.exe -avd ao3_test_api34
   -port 5556`, при том что tools/ в worktree ОТСУТСТВУЕТ (ни файла, ни
   junction на момент разбора). qemu-ребёнка нет, порт не держит, его
   stale-локи AVD сняты следующим стартом. Атрибуция не удалась
   (родительский powershell мёртв); временное окно совпадает с
   каноном 00:13-00:16 (до GuestPinner-фикса). Оставлен жить; если
   всплывёт второй экземпляр — это незакрытый носитель класса M1,
   разбор обязателен.
