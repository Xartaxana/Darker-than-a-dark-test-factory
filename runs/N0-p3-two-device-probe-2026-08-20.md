# N0 — эмпирическая проба двух устройств (программа П3)

Дата: 2026-08-20, окно паузы фабрики (~16:00-16:10 local), исполнитель:
Lead (Fable, dispatch_skipped — короткоживущее окно). План:
docs/tasks/p3-second-emulator.md v8, узел N0.

## Итоги замеров (все witness — дословные выводы)

### (в) Серийники/порядок
Второй эмулятор получил `emulator-5556` (порядок запуска); сперва
`offline`, после буда `device`:
```
List of devices attached
emulator-5554   device
emulator-5556   offline
```

### (б) фаза 1 — голые adb-пути, БЕЗ ANDROID_SERIAL
`Start-Emulator -AvdName ao3_test_api29` при живом чужом устройстве:
**ЛОЖНЫЙ УСПЕХ оракула буда** — третий вариант отказа, ОПАСНЕЕ
предсказанных (не null-Trim краш, а молчаливый ложный позитив):
```
Waiting for device boot (snapshot, up to 45s)...
Emulator booted.                     <- это ЧУЖОЙ emulator-5554
Pinning guest to IPv4 (disabling guest IPv6, ESC-015)...
WARNING: WARNING: guest IPv6 pin FAILED (disable_ipv6='', sysctl не применился).
START-EMULATOR RETURNED OK (без исключения)
```
- Оракул объявил буд по чужому устройству, пока api29 ещё холодный.
- `Set-GuestIPv4Pin` (голый adb) провалился → класс зависаний ESC-015
  возвращается при 2 устройствах. Премиссы B3 плана подтверждены.
- Примечание для N1: вызов вернул exit code 1 при «RETURNED OK» —
  warning-путь IPv6 даёт ненулевой код при успешном возврате функции.

### (б) фаза 2 — класс-фикс ANDROID_SERIAL
```
bare result: 'adb.exe: more than one device/emulator'
env result: '1'        <- ANDROID_SERIAL=emulator-5556, getprop работает
```

### Ожидание буда своим серийником + (а) RAM
`adb -s emulator-5556 shell getprop sys.boot_completed` цикл → `1`,
settle 20 c:
```
boot_completed(5556)='1'
free RAM after settle: 2,27 GB
```
До пробы (один эмулятор + фабрика): 3.48 GB. **Дельта api29 ≈ 1.2 GB;
итог 2.27 GB > abort-порога 1.0 GB, но запас невелик. F-30: НИЖНЯЯ
ОЦЕНКА — клон api34 (hw.ramSize=2G) будет тяжелее api29.**

### (г) Witness соответствия AVD↔серийник
```
adb -s emulator-5556 emu avd name -> ao3_test_api29 / OK
```

### Teardown (якорный килл, фабричный не тронут)
```
BEFORE: 16356 ao3_test_api34 | 21324 ao3_test_api29
AFTER:  16356 ao3_test_api34
```

### Восстановление state/emulator-session.json (hygiene п.8)
Байтовая копия до пробы; восстановление; сверка:
```
SHA256 до/после == C4BD9D86A50616BB1D03FEB8F3770054DE035986FFF393564DDDE4DC79109B14
содержимое: {"gpu":"swiftshader_indirect","avd_name":"ao3_test_api34",...}
```

### Стек 1 жив (после пробы)
```
emulator-5554   device
APPIUM /status: HTTP 200, ready=True
```

## Выводы для N1/N2

1. Премиссы B3/B6 подтверждены эмпирикой; фактический режим отказа
   оракула — молчаливый ложный успех через чужое устройство (снапшот-
   ветка), это строже мотивирует фикс «оракул по emulator-$Port».
2. ANDROID_SERIAL как класс-фикс работает (getprop подтверждён).
3. RAM: два эмулятора помещаются с запасом ~1.3 GB над порогом на
   ЛЁГКОМ втором образе; для клона api34 в N2 обязателен `-Memory`
   (урезка) и повторный замер. Вопрос оператору «докупка vs посменный»
   остаётся открытым до замера N2.
4. Новое для N1 (не было в плане): exit code 1 при успешном возврате
   Start-Emulator (warning-путь IPv6-пина) — шов для callers,
   проверяющих $LASTEXITCODE.
