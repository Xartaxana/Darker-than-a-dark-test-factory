# HANDOFF — точка возобновления

Обновлено: 2026-07-08. Читать первым при старте новой сессии.

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

## Где мы (2026-07-08, утро)

**Первый живой проход /qa-loop ВЫПОЛНЕН** (2026-07-07/08, коммиты 0e0140a..9de3a73):

- **BUG-002 (test_debt)** устранён test-maintainer'ом и **Verified** независимым
  fix-verifier (smoke 9/9 ×3 у мейнтейнера + статика 0/0 и повторный 9/9 у
  верификатора). Гейт D1 и evidence-контракт C2 обкатаны живьём.
- **Батч browser TC-050..TC-055 автоматизирован 6/6** (`framework/tests/test_side_panel.py`),
  включая жестовые: TC-053 через `mobile: pinchOpen/CloseGesture`, TC-055 через
  сырые W3C multi-touch + luma-прокси скриншота (ограничения задокументированы в
  кейсах). Статусы ОСТАВЛЕНЫ Approved, `automated_by` заполнены — по гейту F1.
- **F2 (agent_output)** отработал у всех троих воркеров без шероховатостей.
- arch_check 0/0, ALLOWLIST пуст. 226 тестов scripts/tests зелёные.

Тулинг борды за проход (по решениям владельца, builder ×5): проекция
`lock` → assignee + `wip:<agent>`; Blocked-колонки TC/run; кнопки переходов
генерируются из `via_board` матрицы (нелегальные исчезли); производная колонка
**Awaiting Review** (Approved + automated_by — только проекция, машина не тронута);
wip-бейдж на живой доске; **scripts/ui_snapshot.py** — компактная ref-проекция
UI-дерева (идея agent-browser), воркерам предписано смотреть живое дерево только
через неё (`--ref eN` даёт готовые локаторы), правило вшито в промпты
automator/maintainer.

## СЛЕДУЮЩИЙ ШАГ: второй проход /qa-loop — ревью гейта F1

Первое сработающее правило — **«Ревью нового автотеста»** → test-reviewer (opus)
на TC-050..TC-055 (6 кейсов в колонке Awaiting Review). Это первый живой клиент
полного гейта F1: reviewer переводит Approved→Automated + ставит
`automation_status: active`, либо возвращает `review: changes_requested`
(кейс остаётся в Awaiting Review, доработку заберёт automator правилом выше).

Дальше в очереди (актуальное — `state/factory-status.md`, генерируется):

- **31 Approved-кейс без automated_by** → батчи по area, P1 (владелец: P0 → P1):
  downloads ×5 (TC-032..036), tabs ×4, rating ×4, settings ×3, filter-profiles ×3;
  P2/P3 после. **TC-021 (backup, P0) НЕ брать** — SAF-блокер, отдельная задача.
- docs/01 §9 (needs-design) всё ещё протух — правило «Спроектировать кейсы»
  может диспатчить test-designer вхолостую; актуализация test-strategist'ом
  так и не влезла в лимит 3 воркфлоу/проход.

Находки живого прохода (копить для «репетиции тёмного дня как регресс», C3):

1. **Обрыв лимита подписки убивает фоновых воркеров**; транскрипт МОЖЕТ теряться
   (первый automator — потерян, builder — уцелел и продолжился по SendMessage).
   Лечение: передавать новому воркеру рабочее дерево как задел; правило
   «заполняй automated_by СРАЗУ по готовности кейса, не в конце батча».
2. Фоновые процессы (board_server) гибнут вместе с сессией — перезапускать.
3. Транзитный host-ANR SystemUI на холодном старте эмулятора — не app-bug.
4. max_triggered_workflows=3 съедается быстро (maintainer + fix-verifier по
   цепочке D1 — уже 2 слота); ревью уехало на следующий проход — это норма.

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
. D:\AO3_tests\scripts\tasks.ps1   # Start-Emulator, Start-Appium(npx.cmd-фикс), Stop-NodeProcesses, Install-App
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
- **Cloudflare bot-check** на старте (R-03); Git Bash + adb: `MSYS_NO_PATHCONV=1`.
- **Не гонять сканирование файлов bash-циклом** — Grep/Read по одному (sandbox
  всегда просит подтверждение на цикл). Правка `.claude/settings.json` спрашивает
  всегда (защита от самоизменения) — это единственное неустранимое окно.

## Открытые хвосты (вне Этапа 1 — см. docs/09 Этапы 2–4)

- TC-009/013/014/015 в Review: транспорт replay готов, нужна фикстура ЛИСТИНГА
  с блёрбом синтетической работы + встроить `install-mitm-ca.sh` в test-runner.
- SAF file/folder picker не автоматизируется штатно (блокер TC-021 и части
  download/backup-кейсов) — нужен обход, отдельная задача.
- 4 кейса P3 в Review (TC-020/024/031/037) + TC-006 Draft (ждёт решения BUG-001);
  R-09 (filter-profiles), R-10 (notes/tags) — proposed, ждут утверждения.
- **docs/01 §9 (needs-design) протух**: области уже закрыты дизайном,
  но метки остались — правило «Спроектировать кейсы» будет диспатчить
  test-designer вхолостую. Актуализировать test-strategist'ом, когда влезет
  в лимит прохода.
- `settings.local.json` разрастается за прогоны — чистить через `/permission-audit`
  (шаг 4) периодически; `Invoke-Suite`/`Install-App` через Bash требуют
  `-ExecutionPolicy Bypass` — зашить Bypass в функции tasks.ps1.
