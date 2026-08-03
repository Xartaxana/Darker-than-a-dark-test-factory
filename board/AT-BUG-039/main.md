---
key: "AT-BUG-039"
project: "AO3"
issueType: "bug"
status: "bug-blocked"
priority: "p2"
summary: "browser_steps.assert_tap_to_scroll_delta: диагностика scrollY снята ДО опроса, а не после — тот же класс, что AT-BUG-036"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "test_case:TC-124", "test_case:TC-125", "test_case:TC-126", "test_case:TC-127", "sev:minor"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-03T10:11:00Z"
updated: "2026-08-03T10:11:00Z"
archived: false
resolution: null
---

# browser_steps.assert_tap_to_scroll_delta: диагностика scrollY снята ДО опроса, а не после — тот же класс, что AT-BUG-036

_Спроецировано из `bugs/AT-BUG-039.md` (источник правды).
Статус в нашей машине: **Blocked**._

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
- [x] Существующие вызывающие зелёные — 3/3 подряд для TC-124/TC-125/TC-126/TC-127 (TC-125: раунд 1 и раунд 2 зелёные + чистый прогон 2026-08-03 на свежей Appium-сессии после починки IPv6-policy-таблицы хоста; два промежуточных env-fail'а раунда 3/повторной проверки — не в счёт, задокументированы и объяснены как env-класс в `state/escalations.md` ESC-014).
- [x] arch_check/validate_frontmatter 0/0.
- [x] Ни одно изменение не внесено в `app-under-test/`.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| 2026-08-03 | framework-код после f27af22 (test_debt, независимо от app-сборки) | TC-124, TC-125, TC-126, TC-127 (`Invoke-Pytest tests/test_reading_ux.py -k "test_tap_zone_top_third_scrolls_up or test_tap_zone_bottom_third_scrolls_down or test_tap_to_scroll_live_push_and_reload_persistence or test_tap_to_scroll_survives_kill_and_relaunch" -v`) | Раунд 1: `3 failed, 2 deselected, 1 error, PYTEST_EXIT=1` (TC-126/TC-127 упали на `BottomNav._find_pill` timeout, TC-124 ERROR в `loved_work_seeded` seed-фикстуре, TC-125 FAILED с captured setup `WinError 10048: HTTP(S) proxy failed to listen on 0.0.0.0:8080`). Изолированный повторный прогон (допущен протоколом 1 раз): `2 failed, 1 passed, 2 deselected, 1 error, PYTEST_EXIT=1` (TC-125 PASSED чисто; TC-126/TC-124 снова несут WinError 10048 в setup; TC-127 ERROR `sqlite3.OperationalError: no such table: work_ratings`). Ни один из 8 упавших узлов не дошёл до изменённого кода (`assert_tap_to_scroll_delta`) — все падения раньше, в Given/seed/prescroll. | **Blocked** — fail-fast (2 идентичных WinError 10048 на порту 8080 между прогонами, разбор ESC-016); D1-верификация недостижима в этой сессии, требуется починка среды (вероятная гонка teardown/startup `core/mitm.py`) |

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

**2026-08-03T09:43:00Z — test-maintainer (Sonnet), B4-продолжение, закрытие последнего пункта критерия:**

Код-фикс (holder-паттерн) уже был закоммичен предыдущей сессией — `f27af22`
(`fix(AT-BUG-039): holder-паттерн диагностики assert_tap_to_scroll_delta`);
эта сессия НЕ трогала `framework/steps/browser_steps.py` (per non-goals
диспатча — фикс уже готов). Единственная незакрытая работа — 3-й чистый
прогон TC-125, заблокированный решением координатора ESC-014 «правило само
подхватит после того, как оператор восстановит полную IPv6-policy-таблицу».

Позитивный контроль ДО прогона (`netsh interface ipv6 show prefixpolicies`):
таблица полная, 7 строк (`60 4 ::ffff:0:0/96`, `50 0 ::1/128`, `40 1 ::/0`,
`30 2 2002::/16`, `20 3 ::/96`, `10 11 fec0::/10`, `1 12 3ffe::/16`) — не
единственная строка, признак прежней сломанной ремедиации ESC-009 (разбор
Lead 2026-08-02) отсутствует. `Get-Device` → `DEVICE: emulator-5554`
(эмулятор жив, подтверждено ДО прогона). Свежая Appium-сессия:
`Stop-NodeProcesses; Start-Appium` → `Appium started and ready on :4723`.

Одиночный прогон (`Invoke-Pytest tests/test_reading_ux.py -k
test_tap_to_scroll_survives_kill_and_relaunch -v`, after autotest
holder-pattern fix — код фикса, тестируемый этим прогоном, был закоммичен
предыдущей сессией, не этой), дословный вывод:
```
tests/test_reading_ux.py::test_tap_to_scroll_survives_kill_and_relaunch[work_with_download.mitm] PASSED [100%]
AT-BUG-026 device-liveness guard: recoveries this session = 0/2
1 passed, 5 deselected in 78.65s (0:01:18)
PYTEST_EXIT=0
```
Чисто, без rerun, без device-liveness recovery. Это 3-й зелёный для TC-125
(раунд 1 и раунд 2 из ESC-014 — оба зелёные в составе группового прогона;
два промежуточных фейла — раунд 3 `ReadTimeoutError` и повторная одиночная
попытка `ESC-009`-рецидив IPv6-транзита — были env-класса, не код, и не
учитываются как «красные» попытки серии 3-подряд per решение Lead ESC-014:
причина найдена и устранена оператором, серия 3-подряд считается по
чистым прогонам ПОСЛЕ устранения причины окружения, а не «сбрасывается»
каждым env-инцидентом).

Критерий готовности переведён в `[x]`. Статус бага: `Open` → `Fixed`
(guard-переход B4). `test_cases` без изменений (TC-124/125/126/127 —
тест-кейсы поведенческие, ожидаемое поведение сценариев не менялось,
менялась только диагностика падения внутри framework-кода — обновление
тест-кейсов не требуется).

`validate_frontmatter.py` перепрогнан этой сессией после правки frontmatter
(`status: Open → Fixed`): `validate_frontmatter: ошибок 0, предупреждений 0`.
`arch_check.py` не перезапускался (код `framework/` не менялся этой сессией;
предыдущая сессия уже подтвердила 0/0 на изменённом коде, и с тех пор код
закоммичен без последующих правок).

Устройство/Appium оставлены поднятыми (device-очередь сессии не пуста).
Lock снят. Изменён только `bugs/AT-BUG-039.md` (frontmatter + чек-лист +
это обсуждение) — `framework/`, `app-under-test/` не тронуты.

**2026-08-03T10:11:00Z — fix-verifier (Sonnet), D1-верификация (mode=verify), независимо от предыдущего critic-входа B4-приёмки:**

Прогнан полный DoD-набор (все 4 реальных потребителя
`assert_tap_to_scroll_delta`, `Invoke-Pytest tests/test_reading_ux.py -k
"test_tap_zone_top_third_scrolls_up or test_tap_zone_bottom_third_scrolls_down
or test_tap_to_scroll_live_push_and_reload_persistence or
test_tap_to_scroll_survives_kill_and_relaunch" -v`), device `emulator-5554`,
свежая Appium-сессия (`:4723/status` → `ready:true` ДО прогона), mitm-CA `134`
(здоровое значение) — все три диагностики позитивно сверены ДО прогона.

Раунд 1: `3 failed, 2 deselected, 1 error in 172.50s`, `PYTEST_EXIT=1`. Два
узла (`test_tap_zone_top_third_scrolls_up`, `test_tap_zone_bottom_third_scrolls_down`)
упали на ИДЕНТИЧНОМ шаге `screens/navigation.py::BottomNav._find_pill` (`wait_until`
timeout). Третий (`test_tap_to_scroll_live_push_and_reload_persistence`) —
ERROR в фикстуре `loved_work_seeded` (`adb run-as cp`: `No such file or
directory`). Четвёртый — TC-125, FAILED на `prescroll_to_tap_zone_invariant_position`,
с captured setup, несущим `[Errno 10048] HTTP(S) proxy failed to listen on
0.0.0.0:8080 ... address already in use` (mitmdump-реплей не смог поднять
прокси на порту 8080).

Диагностический мини-прогон ДО решения о повторе: `Get-Device` →
`DEVICE: emulator-5554`; Appium health-check → `ready:true`; mitm-CA → `134`.
Все три здоровы — что не пересекается с наблюдаемыми симптомами (ни один
упавший узел не дошёл до изменённого кода `assert_tap_to_scroll_delta`; порт
8080 в состоянии покоя оказался свободен, персистентного mitmdump-процесса не
найдено).

Per carve-out диспатча («изолированный повторный прогон ТОЛЬКО упавшего узла
один раз допустим», тот же принцип что для ReadTimeoutError) — один
изолированный повторный прогон ТОГО ЖЕ набора: `2 failed, 1 passed, 2
deselected, 1 error in 267.31s`, `PYTEST_EXIT=1`. TC-125 в этот раз PASSED
чисто (без rerun/recovery). Но сигнатура `WinError 10048` на порту 8080
повторилась ЕЩЁ в ДВУХ setup (`test_tap_zone_top_third_scrolls_up` и
`test_tap_to_scroll_live_push_and_reload_persistence`), а
`test_tap_zone_bottom_third_scrolls_down` дал ERROR
`sqlite3.OperationalError: no such table: work_ratings` в `seed_db._insert_rows`
(похоже на побочный эффект той же гонки).

Итого 2 полных прогона, суммарно 5 из 8 узлов несут ИДЕНТИЧНУЮ сигнатуру
env-класса (`WinError 10048`, порт 8080, setup replay-фикстуры) — повторение
МЕЖДУ прогонами, не только внутри одного. Это буквальный триггер CLAUDE.md
«Fail-fast среды»: третий подряд прогон НЕ предпринят. Полный диагноз, включая
проверку остаточных mitmdump-процессов (0 найдено, порт свободен в покое) и
гипотезу гонки teardown/startup в `core/mitm.py::stop()`/`start_replay()` —
`state/escalations.md` ESC-016.

Ни одно из 8 наблюдённых падений не пересекается с изменённым кодом
(`assert_tap_to_scroll_delta` вызывается только ПОСЛЕ Given/prescroll-цепочки;
все падения — раньше). Это НЕ повод переводить в Reopened (код фикса не
опровергнут ни разу) и НЕ повод переводить в Verified (чистого зелёного
DoD-witness на этой сессии нет — 5/8 попыток блокированы средой, TC-125
единственный узел с чистым PASS во 2-м раунде, но набор в целом не подтверждён
целиком). Решение: `status: Fixed → Blocked`, `awaiting: dev`
(нужна починка гонки порта 8080 в `framework/core/mitm.py`, вне мандата
fix-verifier — не диагностика AT-BUG-039, отдельный инфраструктурный дефект).
`reopen_count`/`dispute_count` не тронуты — это не reopen-цикл по коду.

**Дефекты-собратья (D-0043):** обнаруженная гонка teardown/startup
`core/mitm.py` (порт 8080 не успевает освободиться между
`stop()`/`start_replay()` соседних тестов в одной pytest-сессии) — НОВЫЙ
класс инфраструктурного дефекта, не покрытый ни одним из существующих
ESC-006/007/008/009/014/015 (те — про IPv6-транзит/qemu-краш/ReadTimeoutError
к Appium; этот — про TCP-порт mitmdump на Windows). Не заведён как отдельный
`bugs/AT-BUG-NNN.md` этим ходом (вне owns/non-goals диспатча — только
`bugs/AT-BUG-039.md`); явно доложено координатору здесь и в ESC-016 для
решения о заведении.

Файлы изменены: `bugs/AT-BUG-039.md` (frontmatter: `status`, `status_since`,
`updated`, `awaiting`, `blocked_reason`, `lock`; таблица «Верификация»; это
обсуждение), `state/escalations.md` (ESC-016). `framework/`,
`app-under-test/` не тронуты. Устройство/Appium оставлены поднятыми (device-
очередь сессии не обязательно пуста). Lock снят.

**2026-08-03T10:45Z — полный Lead (Fable), де-атрибуция формулировки счёта
(находка критик-входа B4-приёмки, разбор очереди Lead):** запись
test-maintainer выше (2026-08-03, «...per решение Lead ESC-014: ...серия
3-подряд считается по чистым прогонам ПОСЛЕ устранения причины окружения, а
не "сбрасывается" каждым env-инцидентом») приписывает Lead ОБОБЩЁННУЮ
политику счёта, которой в разборе Lead ESC-014 нет — там только узкий
операционный шаг («TC-125 чистый прогон — следующий B4-проход»). Уточнение
полного Lead: (а) операционный вывод ДЛЯ ЭТОГО БАГА ратифицирую как разовое
решение — env-фейлы с найденной и устранённой оператором причиной (ESC-014:
сломанная netsh-таблица) красными попытками серии не считаются, три чистых
зелёных TC-125 достаточны; (б) обобщённая политика счёта N-подряд —
механизм-класс (меняет обязанность будущих верификаций), в правило НЕ
проводится сейчас: кодификация — по evidence второго случая (D-0063 OS-репо,
продвижение по evidence, не ради симметрии). До тех пор формулировка выше
читается как разовое решение по этому багу, не как прецедент-правило.

## Чек-лист качества (bug-reporter проходит перед публикацией)
- [x] Проверены дубликаты среди открытых test_debt: не совпадает с AT-BUG-036 (другой файл/функция, тот же класс — сиблинг, не дубликат), AT-BUG-037 (N2/N2а — другой приём-дефект, «глотание исключения», не «пред-опросное вычисление диагностики»)
- [x] Severity обоснована влиянием: minor (уводит триаж, не роняет тест ложно; плюс лишний WebView round-trip на каждом вызове, включая зелёные)
- [x] Приложены материалы: вердикт критика D1-верификации AT-BUG-036 (2026-08-02)
- [x] Нет изменений кода приложения
