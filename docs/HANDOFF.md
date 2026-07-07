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

## Где мы (2026-07-07, ночь)

**Этапы 1 и 2 docs/09 ЗАВЕРШЕНЫ** (165 тестов scripts/tests зелёные). Из Этапа 2
вынесено решением владельца: GitLab Issues для critical+ → Этап 4 (вместе с
Telegram-ботом); хвост «репетиция тёмного дня как регресс» — после обкатки
живым проходом. Сводка сделанного — docs/09 (✅ у пунктов), контракты — docs/06
(«B1/B2/B5», «B3/B4», «F1»), журнал — git log.

## СЛЕДУЮЩИЙ ШАГ: живой проход /qa-loop (решение владельца, запуск в новой сессии)

Первый боевой запуск конвейера после волны Этапа 2. Обкатывает разом:
pre_steps, preflight (doctor → validate_frontmatter → arch_check), контракт
agent_output (F2), гейт ревью (F1), маршрут test_debt (B4), model-роутинг
воркеров. Наблюдения фиксировать — они лягут в «репетицию тёмного дня как
регресс» (docs/09, хвост C3). Шероховатости agent_output у воркеров ОЖИДАЕМЫ
(F2 живьём не обкатан): фиксировать как находки, не перестраивать конвейер на лету.

Что в очереди (актуальное — `state/factory-status.md`, генерируется):

- **BUG-002** (test_debt, weak_locator, Open) → правило «Устранить test debt» →
  test-maintainer: вынести импорты screens/`.by_text` из `test_smoke.py` в steps,
  проставить 5 недостающих `@allure.id` (если под smoke-тесты нет TC — сначала
  test-designer/человек), убрать пары из ALLOWLIST в `scripts/arch_check.py`.
- **37 Approved-кейсов** → «Автоматизировать Approved-кейс» → test-automator
  батчами по area, P0 → P1 (решение владельца). ВАЖНО: автоматор теперь НЕ
  переводит в Automated — после него срабатывает «Ревью нового автотеста» →
  test-reviewer (первые живые клиенты гейта F1).
- docs/01 §9 (needs-design) протух → правило 11 может диспатчить test-strategist
  вхолостую; актуализация стратегии — легитимная часть прохода, не находка.

Свежее от владельца (коммит b8125a0, routing MVP): модели воркеров назначены
(automator/maintainer=sonnet, analyst/reviewer=opus), появились общие субагенты
scout(haiku)/builder(sonnet)/critic(opus) и журнал делегирования — при
диспетчеризации сверяться с routing policy владельца.

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
- **docs/01 §9 (needs-design) протух**: области уже закрыты дизайном (37 Approved),
  но метки остались — правило 11 будет диспатчить test-designer вхолостую.
  Актуализировать test-strategist'ом (первый кандидат на диспатч в Этапе 2).
- `settings.local.json` разрастается за прогоны — чистить через `/permission-audit`
  (шаг 4) периодически; `Invoke-Suite`/`Install-App` через Bash требуют
  `-ExecutionPolicy Bypass` — зашить Bypass в функции tasks.ps1.
