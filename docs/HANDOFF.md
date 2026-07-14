# HANDOFF — точка возобновления

Обновлено: 2026-07-14 (сессия строительства фабрики по ревью docs/10,
полный Lead Fable). Читать первым при старте. Итоги порт-прохода
2026-07-12 и его остатки — в git-истории этого файла (коммит 5bf130d
и далее) и в «Открытых хвостах» ниже.

**Session Start (детектор пропуска handoff, .claude/skills/session-handoff/):**
первым действием новой сессии — `git status --short` и
`git log origin/master..master --oneline`. Грязное дерево или
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

## Где мы (2026-07-14, штатное закрытие)

**Ярус: закрыта на Fable (полный Lead), окон деградации не было.**
Следующая сессия — штатный preflight шаг 0.

**Правило (CLAUDE.md «Ярусы»): очередь фабрики (when-условия
rules.yaml) диспатчится ТОЛЬКО проходом /qa-loop.** Ручные диспатчи
Lead — для не-конвейерной работы.

**Сделано этой сессией** (внедрение внешнего ревью docs/10 + Этап 4;
все циклы приёмки замкнуты — builder/scout/critic/exploratory,
witness'ы в журнале; подробности — в сообщениях коммитов
e7e226c..89073e3). Параллельно шёл проход фабрики в другой сессии —
его итоги в 856c752 (TC-021 автоматизирован, AT-BUG-007 Verified):
- **Ревью docs/10 разобрано**: сверка → docs/09 §5; release-readiness
  секция в factory-status; **coverage-map** (`scripts/coverage_map.py`,
  генерируемая проекция; риски R-02/R-07 не покрыты дизайном — R-02
  закроет canary Этапа 3); historical-снимок §9 стратегии закрыт (D1).
- **Решения владельца 2026-07-14**: R-09/R-10 и R-12..R-15 УТВЕРЖДЕНЫ
  (§5 полон, 15 рисков); security — минимальный smoke (частичный
  пересмотр отказа E4); non-func порядок прежний (Этап 4).
- **4 non-func области в §9 как needs-design** (E2→E1→E3→security) —
  дизайн пойдёт конвейером; C4-инварианты — обязанность test-designer
  + детектор в чек-листе test-reviewer (первый боевой кейс — TC-059).
- **D1 impact-selection целиком**: `state/impact-map.yaml` (владелец —
  Lead) + `scripts/impact_select.py` + встройка в правило 1 rules.yaml
  (fail-safe в FULL; аудит — поле `selection` рана).
- **Exploratory-механизм целиком**: роль exploratory-tester + шаблон +
  каталог + схема + валидатор + правило rules.yaml + скан SKILL +
  метрики factory-status + reaper локов (блокер critic). **CH-001
  исполнен**: находка (System-тема красит WebView — TC-049 исключал
  WebView) → TC-059 Approved со строкой инварианта; полный цикл
  charter→кейс замкнут. Остаток миссии CH-001 — кандидат CH-002.
- **run.schema: `tc_results` + `selection`**; test-runner обязан
  заполнять per-TC результаты из allure и гнать regression по
  impact-селекции. Гэп run↔TC закрыт контрактом; coverage-map детектит
  прогоны без поля.
- Мелочь: UTF-8 в mechanism_gate обоих репо (ось 1 парно; попутно
  снята лживая заметка «НЕ живой файл»), `automated_by` в settings
  канонизирован. 336 self-tests (+25 за сессию).

## СЛЕДУЮЩИЙ ШАГ

1. **Проход /qa-loop (оператор запускает в отдельной сессии).** Это
   ПЕРВЫЙ проход с новыми механизмами: regression по impact-селекции,
   tc_results в run-отчёте, charter-правило (Planned charter'ов сейчас
   нет — правило вхолостую, это норм). В очереди: F1-ревью автотеста
   TC-021, автоматизация TC-059, дизайн 4 needs-design областей §9.
2. **Решения человека:** Review→Approved с борды (батч из прошлого
   закрытия: TC-009/012/013/014/015/032/033/043/044/045 +
   TC-056/057/058 + P3 TC-020/024/031/037); развилка TC-015/BUG-001;
   TC-006 Draft; test_debt «subprocess без таймаута» (AT-BUG-007).
3. **Lead, не-фабричное:** еженедельная калибровка ~2026-07-14
   (журналы обоих репо). Для неё зафиксировано этой сессией: разрыв
   «delegated записан 12:14, критик реально запущен 12:50» (класс
   F-30 — запись в журнале ≠ запущенный воркер; заметил оператор);
   ручные диспатчи exploratory-tester/test-designer до шага 2 — след
   в журнале.
4. **Очередь механики (docs/09):** остаток класса «типы артефактов в
   N местах» (п.11: transitions/sla/board/единый список областей);
   shallow-клон app-under-test (дефолтный диапазон impact_select);
   CH-002 по остатку миссии CH-001.

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
