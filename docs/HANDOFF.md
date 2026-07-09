# HANDOFF — точка возобновления

Обновлено: 2026-07-09 (закрытие сессии qa-loop B4 + механизменная волна).
Читать первым при старте новой сессии.

Здесь ТОЛЬКО resume-заметки и критичный контекст (правило G1, docs/08 →
docs/09). Всё остальное живёт в своих местах:

| Что | Где |
|---|---|
| Очередь, счётчики, локи, эскалации | `state/factory-status.md` — **генерируется** `scripts/queue_snapshot.py`; ручные числа запрещены (A4) |
| План текущих работ | [09-improvement-plan.md](09-improvement-plan.md) (этапы, решения владельца 2026-07-07) |
| Спецификация фабрики (события, D1–D12, SLA) | [06-dark-factory.md](06-dark-factory.md) |
| Runtime-модель оркестрации | [03-agent-system.md](03-agent-system.md) §1 |
| Окружение, спайки A/B/C | [environment-setup.md](environment-setup.md) |
| История сессий | git log (подробные итоги — в сообщениях коммитов) |

## Где мы (2026-07-09, закрытие сессии)

**Проход /qa-loop B4 выполнен** (коммиты edb9595..642dc30, оба репо запушены):

- **AT-BUG-003 (test_debt, B3-поля) — Fixed и ПРИНЯТ**: test-maintainer
  бэкфиллнул `automation_status: active` на 9 pre-gate Automated-кейсах
  (TC-001..005, 007, 008, 016, 017) без фиктивного ревью; witness сверен
  Lead'ом (15/15 Automated несут поле), легальность переходов досверена по
  transitions.yaml. ЖДЁТ fix-verifier по D1 (test_debt — сборку не ждёт).
- **AT-BUG-004 (replay-инфра) — attempt 1 ОТКЛОНЁН critic'ом** (правило 3а).
  Инкремент по сути готов (фикстура `replay` в conftest, синтетическая
  `listing_basic.mitm` на 5 работ, TC-013 зелёный ×3, p0 18 passed), но
  блокер: teardown фикстуры не покрывает отказ `start_replay` (утечка
  device-proxy + орфан mitmdump). **Код инкремента ЛЕЖИТ НЕЗАКОММИЧЕННЫМ в
  рабочем дереве** (framework/core/mitm.py, conftest.py, browser_steps.py,
  data/recording_builder.py, recordings/listing_basic.mitm,
  tests/test_visibility.py, scripts/build_replay_recordings.py,
  docs/environment-setup.md) — НЕ коммитить и НЕ отбрасывать: это задел
  attempt 2. Спека фикса — в `## Обсуждение` бага (блокер + 2 некритичных:
  гонка open_listing, недетерминизм .mitm). Attempt 2 — тот же ярус
  (test-maintainer/sonnet), witness: зелёный TC-013 на replay + smoke.

**Механизменная волна по вопросам оператора** (та же сессия; сессия шла на
Opus = деградированный Lead, окно ретроактивно оформлено парой
lead_degraded/lead_restored с приёмкой D-0044 после переключения на Fable):

1. **Env-негатив ≠ отсутствие объекта** (ложный «эмулятор down» из голого
   `adb` вне PATH): `Get-Device` в tasks.ps1 (DEVICE/NO DEVICE, полный путь),
   CLAUDE.md «Дисциплина команд» п.6, правило в промптах critic/scout/builder
   + 6 device-QA агентов, нота в /permission-audit (fb41872).
2. **Правило 3а расширено**: critic обязателен для builder-класс диффов
   ЛЮБОГО воркера, вкл. QA-агентов конвейера (47f77c1).
3. **Деградация Lead п.4 — сверка яруса в ОБЕИХ точках**: вход (перед первым
   Lead-действием; для /qa-loop — НОВЫЙ шаг 0 preflight в SKILL.md), выход
   (видимый подъём = доказательство окна, журнал не аргумент), внешняя сеть
   (чек калибровки). 1efef9f + 642dc30.
4. **F-21 в OS-репо** (docs/FINDINGS.md) + очередь для Lead OS-репо в их
   CURRENT_CONTEXT.md (порт п.4, чек калибровки, D-номер; порт env-дисциплины
   в их триаду). OS-репо запушен (main = ff863bc).

Известный дефект тулинга (чип task_305afa14, не начат): `log_append.py`
пишет строку в журнал, потом падает на эхо-print при не-cp1251 символах
(напр. `≠`) с exit 1 — запись УЖЕ в файле, НЕ ретраить (даст дубль).

## СЛЕДУЮЩИЙ ШАГ: третий проход /qa-loop

Перед стартом — **шаг 0 preflight (НОВЫЙ)**: сверить свою модель с ярусом
Lead (Fable); ниже → `lead_degraded` до первого диспатча. Далее очередь
(эмулятор один — R6/R11/R13 контендят, приоритет по порядку правил):

1. **R6 «Верифицировать исправленный баг»** → fix-verifier на AT-BUG-003
   (Fixed, test_debt — сборку не ждёт; проверка: 15/15 Automated с
   automation_status + validate_frontmatter 0).
2. **R11 attempt 2 AT-BUG-004** → test-maintainer, спека в теле бага;
   рабочее дерево уже содержит задел (см. выше). После фикса блокера — путь
   к Fixed открыт по критерию инкремента 1 (полный Fixed шире — decomposable
   остаток в баге: вариация для TC-012, download-flow для TC-032/033).
3. **R13 «Ревью нового автотеста»** → test-reviewer на TC-034/035/036
   (downloads, Approved + automated_by, без review).
4. **R14 автоматизация** Approved-кейсов батчами (актуальное —
   `state/factory-status.md`); TC-021 (backup) НЕ брать — SAF-блокер.

Заметка о среде на момент закрытия: эмулятор был поднят с `-writable-system`
+ mitm CA установлен (проверять `Get-Device`, не голым adb; CA — только если
`mount | grep cacerts` пуст).

Итог Этапа 1 (для истории):

- ✅ **A1**: `/qa-loop` диспатчит воркеров с ВЕРХНЕГО уровня (вложенная оркестрация
  не работает — находка репетиции 2026-07-04); qa-orchestrator — read-only
  планировщик для `--dry-run`. rules.yaml v3.
- ✅ **A2**: все 4 pre_steps исполняемы: `scripts/{stale_locks,sla_sweep,board_inbound,build_watch}.py`
  + тесты `scripts/tests/` (43 passed). Формат эскалаций: строки `[sla:<rule>]`
  управляются sla_sweep (самоочистка), строки без тега снимает человек.
- ✅ **A4/G1**: `scripts/queue_snapshot.py` → `state/factory-status.md`.
- ✅ doctor.py (11 проверок, эскалация при FAIL) — preflight `/qa-loop`.
- ✅ **G3**: `schemas/{test-case,bug,run}.schema.yaml` + `validate_frontmatter.py`
  в preflight; реальные артефакты чистые.
- ✅ Интеграционная проверка (2026-07-07): pre_steps в бою (снят протухший лок
  TC-021), планировщик `--dry-run` вернул корректный план и 3 находки:
  smoke_status рассинхрон (исправлен), §9 стратегии протух, canary-правило без
  suite (закомментировано [план] в rules.yaml до Этапа 3).
**Фаза 3 (автоматизация Approved-кейсов) РАЗМОРОЖЕНА**: Этапы 1–2 закрыты,
возобновление — батчами по area (P0 → P1) внутри живого `/qa-loop` (см.
«СЛЕДУЮЩИЙ ШАГ» выше). Протухший лок TC-021 снят stale_locks ещё 2026-07-07.

## Как поднять окружение (в новом окне)

```powershell
. D:\AO3_tests\scripts\env.ps1     # JAVA_HOME/ANDROID_HOME/PATH
. D:\AO3_tests\scripts\tasks.ps1   # Start-Emulator, Start-Appium(npx.cmd-фикс), Stop-NodeProcesses, Install-App, Get-Device
. D:\AO3_tests\scripts\board.ps1   # Show-Board (живая доска)
```

Эмулятор `ao3_test_api34` (API 34). Replay-режим: `Start-Emulator -WritableSystem`
→ boot → `bash scripts/install-mitm-ca.sh` (после КАЖДОГО старта эмулятора; сам
перезапускает фреймворк ~1 мин) → `Install-App` → mitmdump → прокси гостя
`10.0.2.2:8080`. Детали и разбор — environment-setup.md §Спайк B.

## Критичные факты (беречь токены)

- **Истина = код приложения.** PROJECT.md устарел. CLAUDE.md точнее.
- **Локаторы**: код (место рендера!) → живое дерево (ТОЛЬКО через
  `python scripts/ui_snapshot.py`, не сырой page_source) → скриншот. Ловушки Compose:
  `tab.label.uppercase()`, `AnimatedVisibility` (нижняя навигация скрыта за пилюлей
  на Browse; **RatingMenu рендерится только на вкладке Browse**), клик на родителе
  текстового узла, `UiScrollable` не видит Compose-скролл (`swipe_to_text`).
- **Порядок фикстур критичен**: сидинг строго ДО создания Appium-сессии (фикстура
  `driver`), иначе `pm clear`/сидинг не подхватываются запущенным процессом.
  Готовые фикстуры: `seeded_library`/`comment_only_work`/`loved_work_seeded`/
  `placeholder_seeded_work` (`framework/tests/conftest.py`).
- **`savePanelRating`** (`BrowserViewModel.kt`): для несуществующего синтетического
  `ao3_id` панель скрейпит 404 → пустые поля. Обход — `placeholder_seeded_work`
  (строка с `rating=None`, но полными title/author/wordCount).
- **Side panel Browse** (`BrowseSidePanel.kt`): Home, Fullscreen, A-/A+, Contrast,
  яркость-жест (2 пальца, ≥20dp; pinch ≥30dp — шрифт).
- **Env-негатив ≠ отсутствие объекта** (CLAUDE.md «Дисциплина команд» п.6):
  голый `adb` в Bash-туле НЕ в PATH — пустой вывод/`command not found` это промах
  вызова, не «устройства нет». Присутствие устройства — только `Get-Device`
  (DEVICE/NO DEVICE); прецедент: ложный «эмулятор down» у critic 2026-07-08.
- **Cloudflare bot-check** на старте (R-03); adb в PowerShell после env.ps1;
  Git Bash: `MSYS_NO_PATHCONV=1` (если вообще нужен — предпочитай PowerShell-форму).
- **Не гонять сканирование файлов bash-циклом** — Grep/Read по одному (sandbox
  всегда просит подтверждение на цикл). Правка `.claude/settings.json` спрашивает
  всегда (защита от самоизменения) — это единственное неустранимое окно.

## Открытые хвосты (вне Этапа 1 — см. docs/09 Этапы 2–4)

- TC-009/013/014/015 в Review: листинговая фикстура ПОСТРОЕНА (attempt 1
  AT-BUG-004, незакоммиченный задел в дереве — см. «Где мы»); после attempt 2
  разблокировка Review→Approved — решение test-designer/Lead. Отдельный хвост:
  встроить `install-mitm-ca.sh` в test-runner (mount не переживает reboot).
- SAF file/folder picker не автоматизируется штатно (блокер TC-021 и части
  download/backup-кейсов) — **заведён AT-BUG-005** (2026-07-09, был только
  прозой здесь до этой даты — см. следующий пункт).
- filter-profiles (TC-040/041/042): `seed_db.py` не поддерживает таблицу
  `filter_profiles`, для TC-040 нет replay-записи формы AO3 Sort&Filter —
  **заведён AT-BUG-006** (2026-07-09).
- 4 кейса P3 в Review (TC-020/024/031/037) + TC-006 Draft (ждёт решения BUG-001);
  R-09 (filter-profiles), R-10 (notes/tags) — proposed, ждут утверждения.
- **Новая ось для SIBLING_MAP — ПЕРЕНЕСЕНО** (обе под-оси внесены в
  «Ось 6» карты OS-репо 2026-07-08 Lead'ом OS-сессии; строки ниже —
  история). Было: (правило 9 CLAUDE.md; из этой сессии в репо
  Operating-System-for-LLMs не коммитим): `when`-условия rules.yaml ↔ ручные
  метки/статусы в доках, которые правила читают (прецеденты: `needs-design`
  в docs/01 §9, smoke_status-рассинхрон 2026-07-07). Класс: метка протухает,
  если её снятие не закреплено за конкретным агентом в том же ходе.
- **Новая ось для SIBLING_MAP** (правило 9; найдено critic'ом при ревью
  конвенции AT-BUG- 2026-07-08): один и тот же доменный паттерн живёт в
  НЕСКОЛЬКИХ полях одной схемы — в bug.schema.yaml паттерн bug-id
  продублирован в `id_pattern` И в `regression_of` (а потенциально в любом
  поле-ссылке на артефакт того же типа: duplicates, linked_bug и т.п.).
  Класс: сдвиг паттерна правит одно поле и пропускает сиблинга в том же
  файле; прецедент — regression_of отверг бы AT-BUG-002 при новом id_pattern.
- **Новая ось для SIBLING_MAP / очередь для полного Lead (найдено 2026-07-09,
  третий проход /qa-loop):** AT-BUG-005 (SAF picker) и AT-BUG-006
  (filter-profiles) были известны test-designer'у с 2026-07-02 как проза в
  «Заметках для автоматизации» кейсов, но НЕ были заведены как
  `test_debt`-баги до этого прохода — тот же паттерн, что и AT-BUG-004
  (известен с 2026-07-02/03, заведён только 2026-07-08 после 3 повторных
  попаданий в разные батчи автоматизации). Класс: конвейер триггерит
  «Устранить test debt» (R11) только по `bug.type==test_debt` в `bugs/` —
  прозу внутри тела test-case не видит НИКАКОЕ правило. Между «test-designer
  знает о блокере в момент t0» и «кто-то заводит баг» — разрыв, который
  сегодня закрывается только реактивно (правило 9, когда кто-то уже чинит
  смежный дефект) или везением (Lead случайно прочитал заметки перед
  диспетчеризацией R14, как здесь). Предложение на рассмотрение полному
  Lead (архитектурное решение, не мой ярус — Sonnet-деградация в этом
  проходе):
  1. У источника: test-designer, если «Заметки для автоматизации» описывают
     БЛОКЕР (не риск/подсказку, а отсутствующую фикстуру/API/сидинг), обязан
     завести `test_debt`-баг со ссылкой на кейс в ТОМ ЖЕ ходе, до перевода
     кейса в `Review` — не оставлять прозой.
  2. Страховка на входе R14: перед диспетчеризацией test-automator на
     Approved-кейс — грепнуть «Заметки для автоматизации» на маркеры блокера
     (устоявшиеся в этой кодовой базе формулировки: «эскалировать как
     техническую задачу», «не поддержан», «не автоматизируется штатно») и
     сверить с `bugs/`; маркер есть, покрывающего бага нет → не диспатчить
     вслепую, сначала завести/проверить баг.
  Оба пункта — новое правило в CLAUDE.md (чек-лист test-designer +
  предохранитель в логике R14), проходит через «Три вопроса к каждому
  механизму» (п.10 CLAUDE.md) при коммите. Требует и порта в SIBLING_MAP
  OS-репо (тот же класс «прозрачная метка не конвертируется в
  отслеживаемый артефакт», что и ось «`needs-design`/smoke_status» выше).
- Минорные пробелы покрытия, доложенные стратегом 2026-07-08 (решение за
  человеком, дизайн сознательно не триггерим — режим «отложенный минорный
  остаток» в §9): подсветка совпадающих AO3-тегов (rating), контролы Home и
  Fullscreen в side panel (browser).
- `settings.local.json` разрастается за прогоны — чистить через `/permission-audit`
  периодически (2026-07-08: ужат 27→17, канон pytest теперь `Invoke-Pytest`).
- Классификатор self-modification не даёт Lead'у самому расширять
  `permissions.allow` — владельцу добавить в `.claude/settings.json` строки для
  легитимных скриптов (arch_check, transitions, evidence, ui_snapshot, board_view,
  board_server, log_append — список в сводке аудита 2026-07-08), иначе они
  продолжат спрашивать подтверждение у каждого воркера.
