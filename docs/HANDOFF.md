# HANDOFF — точка возобновления

Обновлено: 2026-07-09 ~21:00 (закрытие сессии). Сессия: возобновление после
перезагрузки хоста (включение WHPX), координатор стартовал на Sonnet
(деградационное окно закрыто), основная работа — полный Lead (Fable).
Читать первым при старте.

Здесь ТОЛЬКО resume-заметки и критичный контекст (правило G1, docs/08 →
docs/09). Всё остальное живёт в своих местах:

| Что | Где |
|---|---|
| Очередь, счётчики, локи, эскалации | `state/factory-status.md` — **генерируется** `scripts/queue_snapshot.py`; ручные числа запрещены (A4) |
| План текущих работ | [09-improvement-plan.md](09-improvement-plan.md) |
| Спецификация фабрики (события, D1–D12, SLA) | [06-dark-factory.md](06-dark-factory.md) |
| Runtime-модель оркестрации | [03-agent-system.md](03-agent-system.md) §1 |
| Окружение, спайки A/B/C, инциденты aehd/WHPX | [environment-setup.md](environment-setup.md) |
| История сессий | git log (подробные итоги — в сообщениях коммитов) |

## Где мы (2026-07-09, вечерняя сессия, штатное закрытие)

**Ярус: закрыта на Fable (полный Lead).** Окно деградации Sonnet
(16:15–16:34 по ts журнала) закрыто парой `lead_degraded`/`lead_restored`,
приёмка окна по D-0044 — нарушений нет. Следующая сессия — штатный
preflight шаг 0: сверить свою модель с ярусом Fable; ниже →
`lead_degraded` до первого Lead-действия.

**Миграция AEHD→WHPX ЗАВЕРШЕНА** (детали и уроки —
environment-setup.md «Миграция на WHPX выполнена»):
- WHPX включён владельцем, эмулятор на нём работает штатно (полный p0
  18/18 прошёл боевой нагрузкой).
- Ложный след «нестабильность WHPX» разрешён: истинная причина флаппинга
  была EXT4-panic userdata, побитого BSOD'ом 15:02 → вылечено
  `-wipe-data`. Урок: после краха хоста с поднятым эмулятором первым
  подозревать ФС геста (`-show-kernel`), не гипервизор.
- **AEHD и WHPX взаимоисключающи без ребута** — фоллбэка «переключиться
  на aehd на лету» не существует. Удаление aehd (sunset 31.12.2026) — за
  владельцем после периода стабильности WHPX.
- APK 1.10/11 установлен на свежий userdata, CA-скрипт отработал.
  Эмулятор и Appium ПОГАШЕНЫ при закрытии (правило пустой эмуляторной
  очереди).

**Сделано этой сессией (все циклы приёмки замкнуты, всё закоммичено):**
- **AT-BUG-004: Fixed → Verified** (D1 fix-verifier, переделегирование
  void-диспатча; независимые прогоны + построчная сверка критерия).
  Цикл бага замкнут полностью.
- **AT-BUG-005 инкремент 1 принят** (SAF-инфраструктура): спека Lead в
  баг-файле → test-maintainer → critic (attempt 1 REJECT по блокеру
  teardown-класса AT-BUG-004-инкремента-2) → attempt 2 принят с
  инъекционным доказательством. В дереве: `framework/screens/
  documents_ui.py`, `framework/steps/saf_steps.py`,
  `framework/tests/test_saf_infra_probe.py` (3 сценария, 2× зелёные).
  Факты: pm clear сбрасывает persisted URI-грант; `saf_pick_folder`
  закрывает и класс-блокер TC-038. Баг Open: полный Fixed = зелёный
  TC-021 (этап test-automator).
- **AT-BUG-006 инкремент 1 принят** (device-free): `seed_filter_profiles`
  в seed_db.py по образцу work_ratings + юнит-проба. Баг Open: грань 2
  (replay-запись формы Sort&Filter) и грань 3 (зелёный TC-041/042) в
  очереди. Для грани 3 понадобится обёртка app_steps + conftest-фикстура
  по образцу seeded_library (доклад воркера).
- **AT-BUG-007 заведён** (broken_environment, MAJOR): нет таймаут-гейта —
  висящий in-flight Appium-вызов вешает весь suite вместо fail одного
  теста (диагноз critic, воспроизводимо по коду: settings.py:33-36,
  waits.py, pytest-timeout отсутствует). Дважды стоил ручного
  вмешательства за вечер.
- **AT-BUG-008 заведён** (flaky_test, minor, TC-007): тихая смерть
  процесса приложения на splash в ПОЛНОМ p0 на
  `test_rate_work_from_work_page_panel[READ]` (live); в изоляции
  проходит, crash-буфер пуст — не APP_BUG. Наблюдение после 007.

**ВНИМАНИЕ — чужие незакоммиченные пути в рабочем дереве** (параллельная
сессия, D-0065 OS-репо, самозащита enforcement-цепочки): `CLAUDE.md`,
`scripts/mechanism_gate.py`, `scripts/tests/test_mechanism_gate.py`.
НЕ трогать, НЕ коммитить, НЕ откатывать (правило 4). Если при старте
следующей сессии они уже закоммичены той сессией — пункт снят.

## СЛЕДУЮЩИЙ ШАГ: очередь пятого прохода

0. Preflight шаг 0 (ярус). Проверить, закоммитила ли параллельная сессия
   свои пути (см. ВНИМАНИЕ выше).
1. **B4 AT-BUG-007 (таймаут-гейт) — ПЕРВЫМ эмуляторным диспатчем**
   (test-maintainer): pytest-timeout (+requirements.txt тем же ходом,
   permission-hygiene п.5) и/или client read-timeout на command_executor;
   критерий и доказательство — в баг-файле. Обоснование порядка: до
   этого фикса любой полный p0 может заклинить suite (что и произошло
   дважды), а R14-батчам нужны стабильные прогоны; после фикса
   rerunfailures превращает такие зависания в retriable-fail.
2. **R14 library-батч TC-027/028/029/030** (test-automator) — отложен
   оператором с прошлой сессии, первый батч-кандидат. Затем tabs
   TC-022/023/025/026; затем P2 (settings 018/019, rating 010/011,
   downloads 038/039, errors 046). Guard R14 отсечёт TC-021/040/041/042
   (Open test_debt).
3. **Автоматизация TC-021** (test-automator) — SAF-инфраструктура готова
   (saf_steps); зелёный TC-021 закрывает критерий Fixed AT-BUG-005.
   TC-038 разблокируется тем же saf_pick_folder.
4. **B4 AT-BUG-006 грань 2** (replay-запись страницы с реальной формой
   Sort&Filter) — ОТДЕЛЬНЫЙ диспатч; решение «реальная запись vs
   recording_builder» — test-designer/Lead, не test-maintainer единолично
   (критерий в баг-файле). Затем грань 3 (зелёный TC-041/042 + обёртка
   app_steps/conftest).
5. **Решение человека/test-designer (НЕ конвейера):** перевод
   Review→Approved разблокированных AT-BUG-004 кейсов — TC-009/012/013/
   014/015/032/033/043/044/045 (фикстуры готовы, транзишен P0/P1 —
   только human).
6. §9 стратегии: живой `needs-design` остаток по library-фильтрам —
   правило 15, test-designer, когда пройдут более приоритетные.

## Как поднять окружение (в новом окне)

```powershell
. D:\AO3_tests\scripts\env.ps1     # JAVA_HOME/ANDROID_HOME/PATH
. D:\AO3_tests\scripts\tasks.ps1   # Start-Emulator, Start-Appium, Install-App, Get-Device...
. D:\AO3_tests\scripts\board.ps1   # Show-Board (живая доска)
```

Эмулятор `ao3_test_api34` (API 34, теперь WHPX). Replay-режим:
`Start-Emulator -WritableSystem` → boot → `bash scripts/install-mitm-ca.sh`
(после КАЖДОГО старта эмулятора; из Bash-тула — с `ADB=<полный путь к
adb.exe>`, голый adb там не резолвится) → `Install-App` (APK уже стоит на
текущем userdata, но после pm clear/wipe — заново) → mitmdump → прокси
гостя `10.0.2.2:8080`.

## Критичные факты (беречь токены)

- **Истина = код приложения.** PROJECT.md устарел. CLAUDE.md точнее.
- **Локаторы**: код (место рендера!) → живое дерево (`python scripts/ui_snapshot.py`)
  → скриншот. Ловушки Compose: `tab.label.uppercase()`, `AnimatedVisibility`,
  клик на родителе текстового узла, `UiScrollable` не видит Compose-скролл.
  DocumentsUI — НЕ Compose, классические View (см. documents_ui.py).
- **Порядок фикстур критичен**: сидинг строго ДО создания Appium-сессии.
  Фикстуры: `seeded_library`/`comment_only_work`/`loved_work_seeded`/
  `placeholder_seeded_work` + `replay` (mitm) — `framework/tests/conftest.py`;
  сидинг профилей — `seed_filter_profiles` (seed_db.py).
- **Teardown-класс (двойной прецедент AT-BUG-004-инкр.2 и AT-BUG-005-attempt-1):**
  ВЕСЬ device-setup фикстуры + yield — в одном try, finally чистит
  безусловно и идемпотентно. Critic это проверяет всегда.
- **Рейтинг-бейдж на листинге** = background-color `[data-ao3-rate-btn]`;
  `[data-ao3-badge]` МЁРТВ — не возвращать.
- **`savePanelRating`**: несуществующий синтетический `ao3_id` → скрейп 404 →
  пустые поля; обход — `placeholder_seeded_work`.
- **Env-негатив ≠ отсутствие объекта** (CLAUDE.md «Дисциплина команд» п.6):
  присутствие устройства — только `Get-Device`; env-тулы — только с env.ps1.
- **Зависание suite ≠ повод убивать вслепую**: сперва postmortem (фокус WM,
  pidof пакета, logcat crash-буфер, http_proxy), потом kill. Известный клин —
  AT-BUG-007 (нет таймаут-гейта); известный флаки — AT-BUG-008 (не заводить
  дубли).
- **Эмулятор + GPU-инференс не совмещать**; эмулятор гасить при пустой
  эмуляторной очереди (environment-setup.md).
- Cloudflare bot-check на старте (R-03); Git Bash: `MSYS_NO_PATHCONV=1`
  (предпочитай PowerShell-форму).
- Не гонять сканирование файлов bash-циклом; правка `.claude/settings.json`
  спрашивает всегда.

## Открытые хвосты (вне текущей очереди)

- Некритичные замечания critic по инкременту 3 AT-BUG-004 (при следующем
  касании файлов): докстринг `browser_steps.py::assert_rating_badge_visible`;
  `ListingPage.badge_for` по всем вхождениям — понадобится автоматизации
  TC-012.
- Встроить `install-mitm-ca.sh` в test-runner (mount не переживает reboot).
- Ось 3 из осевого блока `6809e22` — В ОЧЕРЕДИ: проверить промпты
  test-automator/test-maintainer на симметричную обязанность «обнаружил
  НОВЫЙ блокер в ходе работы → test_debt-баг, не заметка».
- Очередь Lead OS-репо: чек калибровки на отказ guard'а R14 (коммит
  `4fc3fe9` SIBLING_MAP); чек калибровки на отказ таймаут-гейта — добавить
  при закрытии AT-BUG-007 (вопрос (в) правила 10 к новому механизму).
- 4 кейса P3 в Review (TC-020/024/031/037) + TC-006 Draft (ждёт решения
  BUG-001); R-09 (filter-profiles), R-10 (notes/tags) — proposed.
- Минорные пробелы покрытия (решение за человеком, §9 «отложенный минорный
  остаток»): подсветка совпадающих AO3-тегов; Home и Fullscreen в side panel.
- `settings.local.json` разрастается — периодически `/permission-audit`.
- AEHD: после периода стабильности WHPX — удалить aehd (владелец).
