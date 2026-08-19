---
key: "AT-BUG-073"
project: "AO3"
issueType: "bug"
status: "bug-fixed"
priority: "p1"
summary: "Нет автоматизационной инфраструктуры для области sync: мок GitLab-сниппета (/api/v4/snippets), сидер sync_tombstones, возврат id профиля из seed_filter_profiles, перехват исходящего тела публикации"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "test_case:TC-207", "test_case:TC-208", "test_case:TC-209", "test_case:TC-210", "test_case:TC-211", "test_case:TC-212", "test_case:TC-213", "test_case:TC-214", "test_case:TC-215", "test_case:TC-216", "test_case:TC-217", "test_case:TC-221", "test_case:TC-222", "test_case:TC-223", "test_case:TC-224", "test_case:TC-225", "test_case:TC-226", "test_case:TC-227", "test_case:TC-228", "test_case:TC-229", "test_case:TC-230", "test_case:TC-231", "test_case:TC-233", "test_case:TC-234", "sev:major"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-19T14:46:00Z"
updated: "2026-08-19T14:46:00Z"
archived: false
resolution: null
---

# Нет автоматизационной инфраструктуры для области sync: мок GitLab-сниппета (/api/v4/snippets), сидер sync_tombstones, возврат id профиля из seed_filter_profiles, перехват исходящего тела публикации

_Спроецировано из `bugs/AT-BUG-073.md` (источник правды).
Статус в нашей машине: **Fixed**._

# AT-BUG-073 — Автоматизация области sync заблокирована: нет мока GitLab-сниппета, сидера надгробий, id профиля и перехвата исходящего тела

## Окружение

- Не зависит от сборки приложения: долг тестовой системы (`type: test_debt`,
  `debt_kind: missing_fixture`). Область `sync` (переинвентаризация
  `strategy-59be96c6-reinventory-0814`, needs-design закрыта дизайн-батчем
  `needs-design-59be96c6-batch-0814`) — совершенно новая для фреймворка,
  своей инфраструктуры не имела вовсе до этого дизайна.

## Суть долга

Критик-вход приёмки дизайн-батча (24 из 49 новых кейсов, area `sync`)
проверил заявления кейсов об инвентаре фабрики собственным поиском и
подтвердил: **ни одного примитива этого класса в фреймворке нет**.

1. **Мок GitLab Snippet API.** Приложение публикует/читает состояние через
   `/api/v4/snippets` (`SyncRepository.kt`, транспорт сборки `59be96c6` —
   см. `strategy-59be96c6-reinventory-0814`). Ни одна из 9 существующих
   `.mitm`-записей в `framework/data/recordings/` не несёт пути
   `/api/v4/snippets` — сверено дампом путей всех записей. Без мока ЛЮБОЙ
   сценарий синка (успех/ошибка/конфликт) либо не запускается, либо уходит
   в живую сеть.
2. **Сидер `sync_tombstones`.** Таблица надгробий (`kind TEXT, id TEXT,
   deletedAt INTEGER`, составной PK) не имеет ни сидера, ни хелпера прямой
   записи в `framework/data/seed_db.py` — `grep -rn "sync_tombstones"
   framework/` пуст. Кейсы, воспроизводящие «работа/профиль уже удалены
   ранее» (TC-211, TC-215, TC-217 и др.), требуют прямого сидинга этой
   таблицы, минуя UI.
3. **`seed_filter_profiles` не возвращает `id`.** Сверено
   (`framework/data/seed_db.py:515-524`) — сидер создаёт профиль, но не
   отдаёт вызывающему его `id` для последующей адресации (напр. надгробие
   профиля по конкретному `id` в TC-212/213).
4. **Нет перехвата ИСХОДЯЩЕГО тела публикации.** Несколько кейсов (TC-211,
   TC-215, TC-231, TC-234 и др.) используют как оракул содержимое JSON,
   которое приложение ОТПРАВЛЯЕТ на сниппет (напр. отсутствие записи в
   массиве `tombstones` после снятия надгробия) — фреймворк умеет читать
   ВХОДЯЩИЕ мок-ответы (обычный replay), но не перехватывать/инспектировать
   исходящее тело POST/PATCH-запроса публикации.

## Критерий готовности (Fixed)

- Мок GitLab Snippet API: минимум GET (текущий снимок)/POST (создание)/PATCH
  (обновление) `/api/v4/snippets` с настраиваемым содержимым ответа,
  интегрируемый в существующий mitm/replay-механизм ЛИБО отдельный
  fixture-слой (решение исполнителя).
- Сидер/хелпер прямой записи `sync_tombstones` (по образцу
  `_insert_rows_filter_profiles`).
- `seed_filter_profiles` возвращает `id` созданного профиля (или ID-карту
  при множественном сидинге).
- Примитив перехвата исходящего тела запроса публикации (хотя бы для
  снепшота одного запроса — не полная запись сессии).
- Хотя бы 3-4 кейса из `test_cases` доведены до зелёного прогона на этой
  инфраструктуре (доказательство пригодности каждого из четырёх пробелов
  минимум одним потребителем); остальные разблокированы для
  test-automator.
- Smoke без регресса.

## Анализ

Класс — «новая область фичи не имеет ни одного инфраструктурного примитива»
(шире `AT-BUG-004`/`AT-BUG-071`, которые чинили ОДИН конкретный пробел в уже
существующей области `downloads`). Здесь область целиком новая, и все
четыре пробела нужны РАЗНЫМ подмножествам из 24 кейсов — единый тикет
класса (D-0043 CLAUDE.md), не 4 отдельных, т.к. один исполнитель
(test-automator) естественно закроет все четыре при первом касании области
sync, и дробление создало бы 4 конкурирующих owns на один каталог
`test-cases/sync/`.

`TC-207..210, TC-218..220, TC-232` (features: конфигурация/ручной
запуск/ошибки без сложного мока, приватность-сравнение манифеста) — этим
тикетом НЕ покрыты (критик не включил их в `test_cases`); часть из них,
возможно, automatable без полного мока API — решает test-automator при
первом касании области.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| 2026-08-19 | vc=12 (emulator-5554, Appium 4723, соответствует yaml) | TC-207, TC-208, TC-211, TC-213, TC-215 (`framework/tests/test_sync.py`, 5 тестов — по одному потребителю на каждый из 4 примитивов + LWW-дубль) | test-maintainer, собственная DoD-демонстрация (НЕ fix-verifier): `Invoke-Pytest tests/test_sync.py -v` — 5/5 PASSED, повторено 3 РАЗА ПОДРЯД (588.76s / 769.38s / 586.63s, PYTEST_EXIT=0 во всех трёх). `Invoke-Smoke` (`-m p0`, 49 тестов): 48 passed, 1 failed (`tests/canary/test_ao3_selectors.py::test_bridge_marker_present_live` — `@pytest.mark.live`, живой archiveofourown.org, `TimeoutException` на поиске элемента; НЕ использует `mitm`/`replay`/`sync_replay` — структурно вне путей кода, тронутых этим фиксом). Изолированный повторный прогон ИМЕННО этого теста отдельно: `1 passed in 15.53s` — подтверждает транзиентный live-network флейк (класс задокументирован в собственном докстринге `test_ao3_selectors.py`: «Cloudflare bot-check, R-03»), не детерминированную регрессию. `arch_check.py`: ошибок 0, предупреждений 5 (все — предсуществующий allowlist, не новые). `Invoke-Pytest tests/ --collect-only`: 650 тестов собираются без ошибок. | Fixed |
| 2026-08-19 | framework, device-free (критик-вход attempt 4 — доработка, эмулятор НЕ поднимался) | н/п (device-free юнит-пробы примитивов, не продуктовые TC) | test-maintainer, доработка по критик-входу (3 блокера + класс-пробел «новый примитив -> device-free юнит-проба» + 3 замечания «малой кровью», см. Обсуждение): `Invoke-Pytest tests/test_capture_addon_unit.py tests/test_mitm_capture_read_unit.py tests/test_seed_sync_tombstones_unit.py tests/test_mitm_start_replay_capture_unit.py -v` — `17 passed in 7.61s`, `PYTEST_EXIT=0`. `python scripts/validate_frontmatter.py` — `validate_frontmatter: ошибок 0, предупреждений 0`. `Invoke-Pytest tests/ --collect-only -q` — `667 tests collected` (было 650, +17 новых device-free юнит-проб). `python scripts/arch_check.py` — `ошибок 0, предупреждений 5` (те же предсуществующие). `tests/test_sync.py` НЕ перепрогонялся (TC-215 хардение — диагностируемые assert без изменения байт-в-байт поведения зелёного пути, подтверждено критиком заранее). | Fixed |

## Обсуждение

**[test-maintainer @ 2026-08-19, критик-вход attempt 4 — доработка ДО Fixed].**
Критик вернул ДОРАБОТАТЬ (device-free ретрай, эмулятор не поднимался,
sync-батарея НЕ перепрогонялась — вердикт критика: для TC-215 поведение
байт-в-байт прежнее). Устранено:

1. **Блокер** `capture_addon.py` — `if not out or not substr: return` молча
   отключал перехват целиком при пустой `capture_url_substr`, хотя пустая
   подстрока задокументирована как «перехватывать всё» (ловушка ложно-
   зелёного негативного оракула, напр. TC-216 «ни одного PUT/POST»). Фикс:
   условие сужено до `if not out: return` — фильтр по подстроке (уже
   корректно трактовавший `""` как «без фильтра», т.к. `"" in любая_строка`)
   больше не подавляется избыточной проверкой.
2. **Блокер** `mitm.start_replay` — несогласованная пара
   (`capture_url_substr` задан, `capture_out=None`) раньше молча НЕ грузила
   addon вовсе. Фикс: явный fail-fast `ValueError` ДО спавна mitmdump.
3. **Блокер** `bugs/AT-BUG-073.md` `status_since`/`updated` — были
   проштампованы будущим временем (+2ч от фактического UTC записи). Фикс:
   приведены к фактическому UTC (`date -u`), `python scripts/
   validate_frontmatter.py` — `ошибок 0, предупреждений 0` (дословный вывод
   в witness ниже). Урок класса: штамповать `status_since`/`updated` ТОЛЬКО
   фактическим моментом правки (`date -u`), не оценкой/округлением вперёд.
4. **Класс-пробел** «новый примитив без device-free юнит-пробы» (собратья —
   три `test_mitm_*_unit.py`) — добавлены 4 новых файла (17 юнит-проб,
   device-free, без mitmdump/порта 8080/устройства):
   `framework/tests/test_capture_addon_unit.py` (6 проб —
   `RequestBodyCapture.request`: пустая подстрока ловит всё, включая
   НЕСВЯЗАННЫЕ URL; заданная подстрока фильтрует; GET игнорируется; пустой
   `capture_out` — no-op; все три метода публикации POST/PUT/PATCH ловятся),
   `framework/tests/test_mitm_capture_read_unit.py` (4 пробы —
   `read_captured_requests`: нет файла → `[]`; пустой файл → `[]`; валидные
   строки парсятся; битая последняя строка пропускается с warning, см. п.5),
   `framework/tests/test_seed_sync_tombstones_unit.py` (3 пробы —
   `_insert_rows_sync_tombstones`: вставка; INSERT OR REPLACE по составному
   PK при повторном (kind,id); ОДИНАКОВЫЙ id с РАЗНЫМ kind — две независимые
   строки, граница составного PK), `framework/tests/
   test_mitm_start_replay_capture_unit.py` (4 пробы — обе стороны границы
   п.2: `substr` без `out` бросает ValueError ДО Popen; `substr` С `out` не
   бросает и строит корректные `-s`/`--set` args; ни один capture-арг —
   прежнее поведение неизменно; `out` без `substr` — валидно, «перехватывать
   всё»).
5. **Малой кровью**: `read_captured_requests` — битая/оборванная ПОСЛЕДНЯЯ
   JSONL-строка теперь пропускается (warning в stderr, `AT-BUG-073`/
   `WARNING` в тексте) вместо голого `JSONDecodeError`; докстринг обновлён,
   покрыто юнит-пробой (п.4).
6. **Малой кровью**: `conftest.py::sync_replay._start` — `assert not
   started["value"]` на повторный вызов `start(...)` (класс осиротевшего
   mitmdump на порту 8080, AT-BUG-043) — тот же флаг, что уже питал
   teardown, теперь ограждает и setup.
7. **Малой кровью**: `test_sync.py::test_sync_publish_full_state` (TC-215) —
   разбор перехваченного тела (`body=None`, отсутствующий `content`,
   `content` не строкой, отсутствующие `version`/`works`/`filterProfiles`/
   `tombstones`) переведён на диагностируемые `assert` с f-строками ДО
   каждого следующего обращения, вместо голых `TypeError`/`KeyError` —
   поведение для ЗЕЛЁНОГО прогона байт-в-байт прежнее (не перепрогонялось
   на устройстве, критик подтвердил это заранее).

**Остаток очереди (строкой, не прозой):** `gitlab_snippet_mock.
make_snippet_create_flow` (POST create) — без потребителя в этом инкременте
(ни TC-207/208/211/213/215 не используют `include_create=True`); первый
естественный потребитель — **TC-223** («Первое устройство: авто-создание
приватного сниппета», `test_cases` этого тикета).

Witness этой доработки — дословный вывод `Invoke-Pytest` точечно по 4 новым
файлам (17/17 PASSED) + `validate_frontmatter.py` (0/0) + `Invoke-Pytest
tests/ --collect-only` (667 тестов, было 650 — +17 новых device-free) +
`arch_check.py` (0 ошибок, те же 5 предсуществующих warning) — все в записи
журнала маршрутизации этого хода. Эмулятор НЕ поднимался, `tests/test_sync.py`
на устройстве НЕ перепрогонялся (соответствует ограничению координатора).

**[test-maintainer @ 2026-08-19] Фикс — все 4 примитива, Open → Fixed.**

Начал с ревизии WIP-хвоста `ddb9c56` (~390 строк, некоммиченного критик-входа
не имевшего) — прочитал `framework/data/gitlab_snippet_mock.py`,
`framework/tests/test_sync.py`, диффы `seed_db.py`/`mitm.py`/
`recording_builder.py`/`conftest.py`/`settings_screen.py`/`settings_steps.py`/
`app_steps.py`, сверил КАЖДОЕ содержательное утверждение с исходником
приложения (`SyncRepository.kt` — эндпойнты GET raw/POST create/**PUT**
update, ТОЧНО как в докстринге мока, НЕ `PATCH` из устаревшей формулировки
находки; `SyncTombstone.kt`/`RatingRepository.kt` — LWW-семантика надгробий;
`AppDatabase.kt` — `sync_tombstones` в схеме v8, установленная сборка её уже
несёт). Решение: **принять WIP как есть** (качество высокое — построчно
цитирует источник приложения, живая находка про
`server_replay_ignore_content` задокументирована и корректна) и **достроить
поверх него** два недостающих примитива, а не переписывать с нуля.

Примитив 1 (мок GitLab Snippet API) и примитив 2 (сидер `sync_tombstones`) —
УЖЕ доказаны WIP-хвостом (TC-207/208/211, все зелёные). Достроено этим
инкрементом:

- **Примитив 3** (`seed_filter_profiles` возвращает `id`) — код уже был готов
  в WIP (`app_steps.seed_filter_profiles`/`seed_db.seed_filter_profiles`
  сигнатуры расширены backward-compatible), но БЕЗ потребителя. Написан
  TC-213 (`test_sync_tombstone_removes_filter_profile`,
  `sync_tombstone_removes_profile_seeded`): `id`, возвращённый сидером,
  подставлен в надгробие мок-снимка — синк матчит удалённое надгробие с
  локальной строкой ПО ЭТОМУ `id` (`SyncRepository.kt:181`), профиль
  исчезает с обеих UI-поверхностей (Settings список + Browse filter
  dropdown).
- **Примитив 4** (перехват исходящего тела публикации) — НЕ существовал
  вовсе. Добавлен `framework/core/capture_addon.py` (новый mitmproxy addon,
  грузится `-s` РЯДОМ с `--server-replay`, читает `flow.request` на событии
  `request()` — не мешает и не модифицируется server-replay'ем, который
  только выставляет `flow.response`) + `mitm.start_replay(...,
  capture_out=..., capture_url_substr=...)` (опциональные параметры,
  дефолт неактивен — байт-в-байт прежнее поведение всех существующих
  вызывающих) + `mitm.read_captured_requests()` (опрашивающее чтение JSONL).
  `conftest.py::sync_replay`'s `_start(...)` пробрасывает оба параметра.
  Написан TC-215 (`test_sync_publish_full_state`): перехвачено PUT-тело
  `updateSnippet`, разобран GitLab-конверт (`{"file_name":...,
  "content":"<JSON строкой>"}`) ВТОРЫМ проходом `json.loads` на вложенный
  `content` — подтверждён `version:3` и все три массива (`works`/
  `filterProfiles`/`tombstones`) с реально засеянными сущностями.

Итого 5 зелёных sync-тестов (TC-207/208/211/213/215), каждый из 4 примитивов
доказан минимум одним потребителем — критерий готовности выполнен.
Остальные `test_cases` тикета (TC-209, TC-210, TC-212, TC-214, TC-216,
TC-217, TC-221-231, TC-233, TC-234 — полный список минус уже покрытые
TC-207/208/211/213/215) разблокированы для test-automator: инфраструктура
(`gitlab_snippet_mock.py`, `sync_replay`, `seed_sync_tombstones`/
`read_sync_tombstones`, `seed_filter_profiles`-`id`, `capture_addon.py`/
`read_captured_requests`) готова и подтверждена живым потреблением.

Witness — 3 подряд зелёных прогона `tests/test_sync.py` (5/5 PASSED каждый
раз) + smoke-срез `-m p0` (48/49, единственный failed — изолированно
подтверждённый транзиентный live-flake вне путей этого фикса, см. таблицу
«Верификация» выше) — дословный вывод в записи журнала маршрутизации.

Изменены/добавлены: `framework/core/capture_addon.py` (новый),
`framework/core/mitm.py` (`start_replay`/`read_captured_requests`
расширены), `framework/tests/conftest.py` (`sync_replay._start` — два новых
опциональных параметра), `framework/tests/test_sync.py` (TC-213/TC-215 +
их фикстуры + обновлённый модульный докстринг). `gitlab_snippet_mock.py`/
`seed_db.py`/`recording_builder.py`/`settings_screen.py`/`settings_steps.py`/
`app_steps.py` — из WIP-хвоста `ddb9c56`, НЕ изменялись этим инкрементом.
`app-under-test/` не тронут.

status: Open → Fixed.

**[критик @ 2026-08-15, ревью needs-design-59be96c6-batch-0814] Находка B4.**
~25 кейсов области sync ссылались на «указание диспетчера» об отсутствующей
инфраструктуре прозой в собственных заметках, но ни один артефакт не делал
этот долг видимым правилу B4/`sla_sweep`. Координатор завёл этот тикет по
диагнозу критика (мандат — явное решение координатора, названное в вердикте
критик-входа как требуемое).

**[Lead (Fable) @ 2026-08-19] РЕШЕНИЕ ПО ПУТИ ИСПОЛНЕНИЯ (развилка HANDOFF
2026-08-18 п.2).** Из двух путей — (а) декомпозиция на 4 task_id по примитиву
/ (б) интерактивное окно — выбран **(б)**: сессия 2026-08-19 интерактивна,
timeout-kill'а нет, а аргумент «Анализа» против дробления (один исполнитель,
один каталог owns, 4 конкурирующих тикета) остаётся в силе. Тикет НЕ
дробится. Ограничения в силе: headless-диспатчи этого task_id ЗАПРЕЩЕНЫ
(правило 69fbf9b, 2 rejected(tooling) в журнале); исполнение — B4-проходом
/qa-loop из интерактивного окна. Частичная работа ~390 строк — WIP-хвост
ddb9c56 (закоммичен БЕЗ приёмки, критик-входа не было): исполнитель обязан
начать с ревизии этого хвоста (принять/переписать — его решение), а не
писать с нуля вслепую. Эскалационная лестница по правилу 6: 2 rejected яруса
sonnet уже накоплены, НО оба tooling (инфраструктурные смерти, не
capability) — интерактивная попытка sonnet легальна как первая попытка в
пригодной среде; при её содержательном провале — сразу ярус выше.

## Чек-лист качества
- [x] Проверены дубликаты (поиск по `AT-BUG-*` на `sync|snippet|tombstone`
      case-insensitive — нет)
- [x] Репро — не применимо (инфраструктурный долг, не воспроизводимый баг)
- [x] Severity обоснована (блокирует автоматизацию 24 из 49 новых P1/P2
      кейсов области)
- [x] Ни одно изменение не внесено в код приложения
