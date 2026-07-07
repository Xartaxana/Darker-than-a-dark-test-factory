# HANDOFF — точка возобновления

Обновлено: 2026-07-07. Читать первым при старте новой сессии.

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

## Где мы (2026-07-07)

Идёт **Этап 1 docs/09** (runtime-фундамент по внешнему ревью docs/08):

- ✅ **A1**: `/qa-loop` диспатчит воркеров с ВЕРХНЕГО уровня (вложенная оркестрация
  не работает — находка репетиции 2026-07-04); qa-orchestrator — read-only
  планировщик для `--dry-run`. rules.yaml v3.
- ✅ **A2**: все 4 pre_steps исполняемы: `scripts/{stale_locks,sla_sweep,board_inbound,build_watch}.py`
  + тесты `scripts/tests/` (43 passed). Формат эскалаций: строки `[sla:<rule>]`
  управляются sla_sweep (самоочистка), строки без тега снимает человек.
- ✅ **A4/G1**: `scripts/queue_snapshot.py` → `state/factory-status.md`.
- ⏳ Осталось: doctor.py; схемы frontmatter + preflight (G3); интеграционный
  прогон нового `/qa-loop`; блок разрешений для новых скриптов в
  `.claude/settings.json` (правка требует подтверждения владельца).

**Фаза 3 (автоматизация Approved-кейсов) — на паузе по решению владельца** до
конца Этапа 1; возобновлять батчами по area (P0 → P1) через обновлённый конвейер.
Лок TC-021 (висит с 2026-07-02) снимет stale_locks при первом проходе.

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
- **Локаторы**: код (место рендера!) → живое дерево → скриншот. Ловушки Compose:
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
- `settings.local.json` разрастается за прогоны — чистить через `/permission-audit`
  (шаг 4) периодически; `Invoke-Suite`/`Install-App` через Bash требуют
  `-ExecutionPolicy Bypass` — зашить Bypass в функции tasks.ps1.
