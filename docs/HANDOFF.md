# HANDOFF — точка возобновления

Обновлено: 2026-07-14 вечер (сессия двух проходов /qa-loop + борда,
полный Lead Fable). Читать первым при старте. Итоги порт-прохода
2026-07-12 и его остатки — в git-истории этого файла (коммит 5bf130d
и далее) и в «Открытых хвостах» ниже.

**Session Start (детектор пропуска handoff, .claude/skills/session-handoff/):**
первым действием новой сессии — `git status --short`,
`git log origin/master..master --oneline` и
`python scripts/log_append.py open-dispatches` (D-0076: показанные
открытые delegated сверить — воркер жив / результат ждёт / фантом;
фантом — пометкой в notes следующего события). Грязное дерево или
неотправленные коммиты = прошлая сессия закрылась без
handoff-проверки — зафиксировать находкой в журнале (`log_append`),
не поглощать молча. Затем — preflight шаг 0 (сверка яруса).

Здесь ТОЛЬКО resume-заметки и критичный контекст (правило G1, docs/08 →
docs/09). Всё остальное живёт в своих местах:

| Что | Где |
|---|---|
| Очередь, счётчики, локи, эскалации | `state/factory-status.md` — **генерируется** `scripts/queue_snapshot.py`; ручные числа запрещены (A4) |
| План текущих работ | [09-improvement-plan.md](09-improvement-plan.md) |
| Спецификация фабрики (события, D1–D12, SLA) | [06-dark-factory.md](06-dark-factory.md) |
| Runtime-модель оркестрации | [03-agent-system.md](03-agent-system.md) §1 |
| Окружение, спайки A/B/C, инциденты WHPX/снапшот | [environment-setup.md](environment-setup.md) |
| История сессий | git log (подробные итоги — в сообщениях коммитов) |

## Где мы (2026-07-14 вечер, штатное закрытие)

**Ярус: закрыта на Fable (полный Lead), окон деградации не было.**
Следующая сессия — штатный preflight шаг 0. Итоги предыдущей сессии
этого же дня (внедрение ревью docs/10, Этап 4, exploratory-цикл) — в
git-истории HANDOFF (16279d3) и коммитах e7e226c..89073e3.

**Правило (CLAUDE.md «Ярусы»): очередь фабрики (when-условия
rules.yaml) диспатчится ТОЛЬКО проходом /qa-loop.** Ручные диспатчи
Lead — для не-конвейерной работы.

**Сделано этой сессией** (два прохода /qa-loop + борда; коммиты
7a6c9fa, f99fd8b, 9fce6cc; witness'ы — в журнале маршрутизации):
- **Проход 1:** AT-BUG-005 финал — честный failed (свежий p0 из 19
  тестов, TC-021 теперь в smoke: 18/1, упал TC-013 → заведён
  **AT-BUG-009** flaky major); F1: TC-021 changes_requested
  (C4-инвариант отсутствовал и скрывал дыру filterProfiles),
  **TC-027..030 Automated+active** (независимый прогон 4/4).
- **Проход 2:** AT-BUG-009 инкремент 1 — timeout-класс N1 из
  AT-BUG-007 ЗАКРЫТ (`adb.py`/`mitm.py`, ADB_SHELL_TIMEOUT=30s /
  TRANSFER=120s, зависший adb = явная TimeoutError; unit-проба);
  TC-021 доработан (строка Инвариант + filterProfiles в сидинге и
  Room-сверке, `review` снят → **повторное F1-ревью в очереди**);
  **TC-060..065** закрыли весь library-остаток §9 (needs-design
  снята); **AT-BUG-010** заведён (TC-031: seed_db не сидит
  word_count=NULL — класс «заметка вместо артефакта»).
- **AT-BUG-009, наблюдение №2** (в баге): Appium-сессия висла ~44 мин
  у ревьюера БЕЗ mitm/replay → корень сужен к длинной живой сессии
  Appium/эмулятора, не к прокси. Известный фон для триажа.
- **D-0076 действует** (порт параллельной сессии, 1cfb8f8): delegated
  только с `--worker-ref`; open-dispatches на закрытии чист. Два огреха
  журнала этой сессии закрыты в самих проходах ретро-записями
  (accepted at-bug-005-close; пропущенный delegated f1-tc021-rework —
  пометкой в notes его accepted).
- **Борда:** живой сервер добавлен в `.claude/launch.json` (конфиг
  `board`, порт 8777, board_server.py — стадия 1 без коммитов);
  **docs/09 п.10** — доделка TrackState-форка (решение владельца:
  правая панель тикета, сортировки/фильтры, колонки с коммитом,
  комментарии в обе стороны; Approve-кнопка НЕ нужна — drag +
  board_inbound), одним заходом с п.9 (фикс кириллицы — первым).

## СЛЕДУЮЩИЙ ШАГ

1. **Проход /qa-loop.** В очереди: повторное F1-ревью TC-021
   (гейт Approved→Automated; оно же — critic-вход по диффу доработки);
   B4 — AT-BUG-006 грань 2 (реальная mitm-запись формы Sort&Filter,
   порядок в баге), AT-BUG-009 (корень набл.№2 + 2 чистых p0),
   AT-BUG-010 (NULL-сидинг); автоматизация TC-038 (guard заметок:
   маркер блокера в кейсе устарел — SAF снят, сверить перед
   диспатчем). **AT-BUG-005 не диспатчить вхолостую**: его последний
   пункт (smoke без регресса) заблокирован AT-BUG-009.
2. **Решения человека:** Review→Approved с борды (батч:
   TC-009/012/013/014/015/032/033/043/044/045 + TC-056/057/058 +
   P3 TC-020/024/031/037 + новые **TC-060..065**); развилка
   TC-015/BUG-001; TC-006 Draft.
3. **Lead, не-фабричное:** еженедельная калибровка ~2026-07-14
   (журналы обоих репо; заметка прошлой сессии о классе F-30 в силе);
   C4-ретрофит 11 старых комбинаторных кейсов (docs/09 п.4, очередь
   test-designer); docs/09 п.9+10 (борда, форк) — Lead-заход.
4. **Очередь механики (docs/09):** остаток класса «типы артефактов в
   N местах» (п.11); shallow-клон app-under-test (дефолтный диапазон
   impact_select); CH-002 по остатку миссии CH-001.

## Как поднять окружение (в новом окне)

```powershell
. D:\AO3_tests\scripts\env.ps1     # JAVA_HOME/ANDROID_HOME/PATH
. D:\AO3_tests\scripts\tasks.ps1   # Start-Emulator, Start-Appium, Install-App, Get-Device...
. D:\AO3_tests\scripts\board.ps1   # Show-Board (живая доска)
```

Эмулятор `ao3_test_api34` (API 34, WHPX). Replay-режим:
`Start-Emulator -WritableSystem` — **CA mitmproxy ставится
автоматически внутри** (признак успеха в выводе: «CA visible in apex
store: OK»); затем `Install-App` (после pm clear/wipe — заново) →
mitmdump → прокси гостя `10.0.2.2:8080`. Ручной фолбэк CA:
`Install-MitmCA` (tasks.ps1). **Ловушка: quickboot-снапшот может быть
битым** — эмулятор тихо гаснет, Start-Emulator висит на
wait-for-device; диагностика/лечение (`-no-snapshot-load`) —
environment-setup.md.

## Критичные факты (беречь токены)

- **Истина = код приложения.** PROJECT.md устарел (BUG-001 — коллекция
  расхождений). CLAUDE.md точнее.
- **Локаторы**: код (место рендера!) → живое дерево (`python scripts/ui_snapshot.py`)
  → скриншот. Ловушки Compose: `tab.label.uppercase()`, `AnimatedVisibility`,
  клик на родителе текстового узла, `UiScrollable` не видит Compose-скролл.
  DocumentsUI — НЕ Compose, классические View (documents_ui.py).
- **Порядок фикстур критичен**: сидинг строго ДО создания Appium-сессии.
  Фикстуры: `seeded_library`/`comment_only_work`/`loved_work_seeded`/
  `placeholder_seeded_work`/`library_*_seeded` + `replay` (mitm) —
  `framework/tests/conftest.py`; сидинг профилей — `seed_filter_profiles`.
- **Teardown-класс:** ВЕСЬ device-setup фикстуры + yield — в одном try,
  finally чистит безусловно и идемпотентно. Critic проверяет всегда.
- **Журнал**: accepted/rejected теперь ТОЛЬКО с `--by` (матрица ярусов
  enforce'ится log_append.py); continuation/retry — CLAUDE.md.
- **Рейтинг-бейдж на листинге** = background-color `[data-ao3-rate-btn]`;
  `[data-ao3-badge]` МЁРТВ — не возвращать.
- **`savePanelRating`**: несуществующий синтетический `ao3_id` → скрейп 404 →
  пустые поля; обход — `placeholder_seeded_work`.
- **Env-негатив ≠ отсутствие объекта** (CLAUDE.md «Дисциплина команд» п.6):
  присутствие устройства — только `Get-Device`; несущие утверждения о
  среде — только после сверки измерением (F-30).
- **Зависание suite**: постмортем до kill; таймаут-гейт AT-BUG-007 теперь
  превращает клин в retriable-fail за ≤240с. Известный флаки — AT-BUG-008
  (не заводить дубли).
- **Эмулятор + GPU-инференс не совмещать**; эмулятор гасить при пустой
  эмуляторной очереди (сейчас — ПОГАШЕН, Appium тоже).
- Cloudflare bot-check на старте (R-03); Git Bash: `MSYS_NO_PATHCONV=1`
  (предпочитай PowerShell-форму).
- `.ps1` с кириллицей — только UTF-8 BOM (CLAUDE.md п.7).

## Открытые хвосты (вне текущей очереди)

- **Перепрогнать интегрированный авто-CA** («один вызов
  `Start-Emulator -WritableSystem` → CA сам встал») при следующем
  здоровом replay-подъёме — отложенный witness mitm-ca-autoinstall.
- Журнал (некритичные critic по порту): 2 недостающих теста
  (rejected-после-accepted как документируемое поведение; frontmatter
  с нераспознанным model), data-quality basis при проходящем tier,
  кириллические `SystemExit` в log_append.py (класс кодировок).
- Некритичные замечания critic по AT-BUG-004 инкр.3 (при касании
  файлов): докстринг `browser_steps.py::assert_rating_badge_visible`;
  `ListingPage.badge_for` по вхождениям (нужен автоматизации TC-012).
- Устаревшая заметка в TC-028 про эскалацию seed_db (уже неактуальна)
  — почистит test-reviewer при F1.
- Минорные пробелы §9 — ЗАКРЫТЫ этой сессией (TC-056/057/058).
- `settings.local.json` разрастается — периодически `/permission-audit`
  (в эту сессию не гонялся).
- Опционально (владелец): `del C:\Windows\System32\drivers\aehd.sys`
  (мёртвый файл, служба удалена).
