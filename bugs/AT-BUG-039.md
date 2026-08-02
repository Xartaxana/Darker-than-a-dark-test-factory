---
id: AT-BUG-039
title: "browser_steps.assert_tap_to_scroll_delta: диагностика scrollY снята ДО опроса, а не после — тот же класс, что AT-BUG-036"
type: test_debt
debt_kind: flaky_test
severity: minor
status: Open
found_in: "критик-вход D1-верификации AT-BUG-036, 2026-08-02: класс-полнота проверена целиком по поверхности message= у wait_for/wait_until в framework/"
fixed_in: ""
last_seen_in: ""
test_cases: ["TC-124", "TC-125", "TC-126", "TC-127"]
runs: []
duplicates: []
regression_of: ""
status_since: "2026-08-02T02:11:33Z"
updated: "2026-08-02T15:25:00Z"
reopen_count: 0
dispute_count: 0
awaiting: none
resolution: ""
resolution_comment: ""
known_issue: "false"
blocked_reason: ""
lock: ""
gitlab_issue: ""
---

# AT-BUG-039 — замороженная диагностика в assert_tap_to_scroll_delta

## Окружение
Долг тестовой системы (`type: test_debt`; `debt_kind: flaky_test` — тот же класс, что `AT-BUG-036`: дефект не роняет тест ложно, но уводит триаж падения не туда). Не зависит от сборки приложения — фикс целиком во `framework/steps/`.

## Суть долга

`framework/steps/browser_steps.py:750-757` (`assert_tap_to_scroll_delta`):

```python
    wait_until(
        driver, _matches, timeout=timeout,
        message=(
            f"scrollY не изменился на ожидаемую дельту {expected_delta:.1f}px "
            f"(±{tolerance_px:.1f}px) относительно scrollY до тапа={scroll_before} "
            f"за {timeout}с (текущий scrollY={get_webview_scroll_y(driver)})"
        ),
    )
```

`get_webview_scroll_y(driver)` — аргумент вызова, вычисляется Python'ом ДО входа в `wait_until`, то есть ДО единственного последующего опроса (та же WebView round-trip латентность, ради которой опрос введён — докстринг `browser_steps.py:739-742`). При таймауте текст падения несёт scrollY, снятый ДО ожидания, под подписью «текущий» — мягче, чем `None` в исходном классе `AT-BUG-036` (там опрос вообще не завершался), но так же уводит триаж: значение неактуально, читается как «текущее состояние», а не как «то, что было в момент вызова».

Найден критиком при D1-верификации `AT-BUG-036` — обход сиблингов внутренней оси `framework/steps/`, заявленный при F1-ревью батча tabs (2026-07-31), оказался неполным именно на этом экземпляре (см. `bugs/AT-BUG-036.md`, поправка координатора 2026-08-02).

## Образец фикса
`framework/steps/app_steps.py::wait_persisted_tab_count` (после `AT-BUG-036` attempt 2): опрос сохраняет последнее наблюдение в замыкание/holder ВНУТРИ предиката, диагностика читает его ПОСЛЕ `wait_for`/`wait_until`, не до.

## Критерий готовности (Fixed)

- [x] `assert_tap_to_scroll_delta` читает `scrollY` для диагностики ПОСЛЕ опроса (последнее реально наблюдённое значение), не до вызова `wait_until`.
- [x] Красная проба: искусственный недостижимый `expected_delta` показывает в тексте падения scrollY, снятый ПОСЛЕ опроса (не устаревшее пред-опросное значение).
- [~] Существующие вызывающие зелёные — 3/3 подряд для TC-124/TC-126/TC-127; TC-125 2/3 (3-й прогон упал fail-fast'ом на НЕсвязанном с фиксом шаге, см. `state/escalations.md` ESC-014). НЕ закрыт этой сессией.
- [x] arch_check/validate_frontmatter 0/0.
- [x] Ни одно изменение не внесено в `app-under-test/`.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|

## Обсуждение

**2026-08-02T02:11:33Z — координатор (Sonnet), заведение по докладу критик-входа D1 AT-BUG-036:**
Критик прошёл всю поверхность `message=` у `wait_for`/`wait_until` в `framework/steps`, `framework/screens`, `framework/web`, `framework/core` (перечень вхождений в его вердикте) и нашёл ровно один неучтённый экземпляр — этот. Не добавлено строкой в `bugs/AT-BUG-037.md` (тот же класс «диагностика ожидания», но файл был локом `test-maintainer` в момент находки — правило 4 CLAUDE.md, чужие незакоммиченные пути не трогать) — заведён отдельным test_debt. Диспатч по B4 — следующим проходом qa-loop, после AT-BUG-037.

**2026-08-02T~15:20Z — test-maintainer (Sonnet), B4-фикс:**

Фикс (`framework/steps/browser_steps.py::assert_tap_to_scroll_delta`) — holder-паттерн по образцу `app_steps.wait_persisted_tab_count` (AT-BUG-036 attempt 2), буквально то, что просил образец диспатча: `holder: dict[str, int]` заполняется ВНУТРИ `_matches` на каждом опросе; `wait_until` больше не несёт вызов `get_webview_scroll_y(driver)` как часть `message=` (устранён и сам класс дефекта, и лишний WebView round-trip на каждом вызове, включая зелёные — вторая половина severity-обоснования бага); при `TimeoutException` от `wait_until` — перехват и переброс нового `TimeoutException` с `holder.get('scroll_y')`, тем же приёмом, что уже используется в этом файле для `open_listing_with_retry` (`browser_steps.py:1304-1310`, `except TimeoutException as exc: raise TimeoutException(...) from exc`) — не изобретённый заново приём, а уже существующий в файле паттерн.

**Уточнение манифеста диспатча:** «потребители — canary tap-zone-guard тесты (`test_tap_zone_guard.py`)» фактически неверно — `grep -n assert_tap_to_scroll_delta framework/ -r` даёт РОВНО 2 файла: `browser_steps.py` (определение + `return get_webview_scroll_y(driver)` на успехе, не тронут) и `framework/tests/test_reading_ux.py` (4 вызова: TC-124 ×2, TC-125 ×2, TC-126 ×1, TC-127 ×1). `test_tap_zone_guard.py` эту функцию не вызывает вовсе (проверено grep'ом ДО прогона, не полагался на текст диспатча). Прогонялись реальные потребители: TC-124/125/126/127.

**Красная проба (изолированная, без устройства):** `get_webview_scroll_y` монки-патчен на функцию со счётчиком (каждый вызов возвращает следующее целое), `assert_tap_to_scroll_delta(driver=None, scroll_before=0, inner_height=1800, direction=1, timeout=2)` вызван напрямую — `WebDriverWait` не трогает `driver` нигде, кроме передачи в предикат, поэтому `driver=None` безопасен. Дословный вывод (`python -X utf8 <red_probe script>`, venv `framework/.venv/Scripts/python.exe`):
```
EXCEPTION TYPE: TimeoutException
EXCEPTION MSG: Message: scrollY не изменился на ожидаемую дельту 1710.0px (±256.5px) относительно scrollY до тапа=0 за 2с (последнее наблюдённое внутри опроса scrollY=6)
CALLS OBSERVED (poll order): [0, 1, 2, 3, 4, 5, 6]
LAST_POLLED_VALUE=6 present_in_message=True
NUM_POLLS=7
PROBE_OK(message carries LAST-polled value, not a frozen pre-poll one)=True
```
Сообщение несёт `scrollY=6` — значение ПОСЛЕДНЕГО (7-го, индекс 6) опроса, не первого (`0`, что было бы вычислено ДО входа в `wait_until` старым кодом). Счётчик (не константа) в фейке — намеренно: демонстрирует, что репортится именно ПОЗДНЕЕ наблюдение опроса, а не любое произвольное значение.

**Прогон реальных потребителей (`Invoke-Pytest tests/test_reading_ux.py -k "test_tap_zone_top_third_scrolls_up or test_tap_zone_bottom_third_scrolls_down or test_tap_to_scroll_live_push_and_reload_persistence or test_tap_to_scroll_survives_kill_and_relaunch" -v`, device-уровень, after autotest message/diagnostics fix):**
- Раунд 1: `4 passed, 2 deselected in 271.25s (0:04:31)`, `PYTEST_EXIT=0`.
- Раунд 2: `4 passed, 2 deselected in 271.22s (0:04:31)`, `PYTEST_EXIT=0`.
- Раунд 3: `test_tap_zone_top_third_scrolls_up` PASSED, `test_tap_zone_bottom_third_scrolls_down` PASSED, `test_tap_to_scroll_live_push_and_reload_persistence` PASSED, `test_tap_to_scroll_survives_kill_and_relaunch` (TC-125) RERUN затем FAILED — `urllib3.exceptions.ReadTimeoutError: HTTPConnectionPool(host='127.0.0.1', port=4723): Read timed out. (read timeout=40)` на `core/navigate.py::navigate` → `driver.get()`, вызванном из `rating_steps.open_work_page` (Given-навигация TC-125, ДО первого обращения к изменённой `assert_tap_to_scroll_delta` в этом тесте). Framework-встроенный rerun (`pytest.ini --reruns 1 --only-rerun ReadTimeoutError|MaxRetryError`) повторил ТОТ ЖЕ вызов и упал ИДЕНТИЧНО — 2 подряд `ReadTimeoutError` на одном и том же шаге. `1 failed, 3 passed, 2 deselected, 1 rerun in 379.01s`, `PYTEST_EXIT=1`.

Это буквальный триггер CLAUDE.md «Fail-fast среды» (docs/06 §5, тот же класс что ESC-008). Остановлены дальнейшие прогоны/3-зелёные-подряд-погоня per протокол; выполнен диагностический мини-прогон:
- `Get-Device` → `DEVICE: emulator-5554` (эмулятор жив).
- Appium health-check `GET :4723/status` → `{"value":{"ready":true,"message":"The server is ready to accept new connections",...}}` (сервер здоров).
- mitm-CA: `adb shell "ls /apex/com.android.conscrypt/cacerts | wc -l"` → `134` (известное здоровое значение, см. ESC-001/ESC-008 — деградации CA не видно).

Все три диагностики здоровы; ни qemu-краш (0xc0000005), ни отсутствие CA, ни IPv6-транзит (известные корни ESC-006/007/008/001/009) не подтверждаются. Трасса падения (`navigate`/`driver.get`) НЕ пересекается с изменённым кодом (`assert_tap_to_scroll_delta`) — падение произошло в Given-навигации ДО первого вызова изменённой функции в этом тесте, так что причинной неоднозначности «код или среда» здесь по факту нет; тем не менее протокол безусловен (2 идентичных env-класса фейла = остановиться), поэтому статус AT-BUG-039 НЕ переведён в Fixed этой сессией. Полная запись — `state/escalations.md` ESC-014.

`arch_check.py`/`validate_frontmatter.py`: оба `0 ошибок, 0 предупреждений`.

Замеченный аналог (D-0037, не в скоупе): `assert_tap_to_scroll_delta` после успешного `wait_until` делает ЕЩЁ ОДИН отдельный вызов `get_webview_scroll_y(driver)` для `return` (строка после `wait_until`) — не тот же класс дефекта (не диагностика падения, значение свежее и корректное), но тот же лишний WebView round-trip; можно было бы отдавать `holder["scroll_y"]`, сэкономив round-trip на КАЖДОМ успешном вызове. Не тронуто — вне описанного критерия готовности бага (только диагностика падения), NON-GOALS диспатча запрещает рефакторинг за пределами названного.

Устройство/Appium/CA оставлены в здоровом, поднятом состоянии (device-очередь сессии не пуста, гасить не следует). Файлы изменены, НЕ закоммичены: `framework/steps/browser_steps.py` (фикс), `bugs/AT-BUG-039.md` (этот файл — чек-лист/обсуждение), `state/escalations.md` (ESC-014). Lock не снят — снимет координатор.

**2026-08-02T~15:45Z — test-maintainer (Sonnet), продолжение того же attempt, по решению координатора ESC-014:**

Решение координатора: текущих доказательств недостаточно для Fixed, критерий закрывается одиночным чистым прогоном TC-125 на свежей Appium-сессии (среда по диагностике здорова, трасса падения не касается фикса).

Свежая сессия: `Stop-NodeProcesses; Start-Appium` → `Appium started and ready on :4723`; `Get-Device` → `DEVICE: emulator-5554` (подтверждён ДО прогона). Одиночный прогон (`Invoke-Pytest tests/test_reading_ux.py -k test_tap_to_scroll_survives_kill_and_relaunch -v`), дословный вывод:
```
tests/test_reading_ux.py::test_tap_to_scroll_survives_kill_and_relaunch[work_with_download.mitm] ERROR [100%]
...
RuntimeError: ESC-009: сокет не смог открыть прямое TCP-соединение 2606:4700:10::6814:902 (host: archiveofourown.org:443, IPv6 (AAAA)) в бюджет 5.0s. ...
core\mitm.py:126: RuntimeError
5 deselected, 1 error in 13.89s
PYTEST_EXIT=1
```

Это НЕ тот же `ReadTimeoutError`, что в 3-м раунде исходной верификации — другая сигнатура (`ERROR` в setup фикстуры `replay`/`_ensure_upstream_fast`, не `FAILED` в теле теста на `driver.get()`), пойманная УЖЕ существующим fail-fast guard'ом `assert_upstream_fast` (введён специально по вердикту `ESC-009`). Позитивный контроль тем же ходом: прямой TCP-connect на IPv4-адрес того же хоста (`104.20.8.2:443`) — `IPv4_CONNECT_OK=True elapsed_ms=101` (IPv4-плечо здорово). `netsh interface ipv6 show prefixpolicies` — ремедиум ESC-009 (`60 4 ::ffff:0:0/96`) всё ещё применён на хосте, тем не менее IPv6-транзит к Cloudflare недоступен за отведённый бюджет — похоже на рецидив корня 3 ESC-009 (или нюанс, что policy не решает саму недоступность транзита, только порядок предпочтения адресов).

Так как это НЕ инструктированный координатором случай «зелёный» и НЕ буквально «тот же ReadTimeoutError на том же шаге» (сигнатура другая, но однозначно env-класс — setup-фикстура, вне изменённого кода), решение: не гонять повторно (fail-fast — сеть подтверждённо больна прямым измерением), `AT-BUG-039` оставлен **Open**, критерий «потребители зелёные» остаётся `[~]`, статус НЕ переведён в Fixed. Полная запись — `state/escalations.md` ESC-014 (вторая серия, дописана в конец записи, сама запись не удалена/не переписана). Эмулятор/Appium оставлены поднятыми (следующим берёт D5-rework). Lock не снят.

## Чек-лист качества (bug-reporter проходит перед публикацией)
- [x] Проверены дубликаты среди открытых test_debt: не совпадает с AT-BUG-036 (другой файл/функция, тот же класс — сиблинг, не дубликат), AT-BUG-037 (N2/N2а — другой приём-дефект, «глотание исключения», не «пред-опросное вычисление диагностики»)
- [x] Severity обоснована влиянием: minor (уводит триаж, не роняет тест ложно; плюс лишний WebView round-trip на каждом вызове, включая зелёные)
- [x] Приложены материалы: вердикт критика D1-верификации AT-BUG-036 (2026-08-02)
- [x] Нет изменений кода приложения
