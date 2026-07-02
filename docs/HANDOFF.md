# HANDOFF — точка возобновления

Обновлено: 2026-07-03 (Fable 5). Читать первым при старте новой сессии.

## Что готово

- **Фаза 0** (окружение), **Фаза 1** (каркас, P0 smoke 9/9) — см. [environment-setup.md](environment-setup.md),
  [../framework/README.md](../framework/README.md).
- **Фаза 2 (тест-дизайн P0/P1) — ЗАВЕРШЕНА.** 55 тест-кейсов: TC-001..005 (Automated,
  smoke), TC-006 (Draft, привязан к BUG-001), TC-007..049 (дизайн по §9 стратегии),
  TC-050..055 (новая область `browser` — side panel/жесты). Человек утвердил:
  **45 Approved + 5 Automated**; в Review остались только 4 P3 (TC-020, 024, 031, 037).
- **Стратегия** [01-test-strategy.md](01-test-strategy.md) обновлена решениями человека:
  - §1: иерархия источников истины — **код app-under-test > CLAUDE.md > PROJECT.md**
    (PROJECT.md устарел, НЕ опираться; расхождения фиксировать в §10, сам файл не править);
  - §5: **R-11 утверждён** (тема/шрифт/яркость — хрупкая зона); R-09/R-10 всё ещё proposed;
  - §6/§9: **side panel важнее экрана Settings** как область (порядок работ), кейсы при этом P1;
  - TC-048 переписан: мгновенное применение тёмной темы (включая WebView через
    `LaunchedEffect(darkTheme)`+`reload()`) — ожидаемый PASS, не заготовленный APP_BUG.
- **Борда**: живой сервер (Show-Board, 127.0.0.1:8777) умеет сортировку по приоритету,
  кнопку ✓ Approve (Review→Approved пишет в .md), выпадающий выбор приоритета,
  боковую панель с полным текстом кейса (рендер markdown). POST `/approve`, `/priority`
  в board_server.py; логика статусов — board_sync.py (`approve_test_case`, `set_priority`).
  `board.ps1` пересохранён в UTF-8 BOM — работает прямой `. scripts\board.ps1; Show-Board`.

## СЛЕДУЮЩАЯ ЗАДАЧА: Фаза 3 — автоматизация Approved-кейсов

`/qa-loop` → оркестратор диспатчит test-automator на 45 Approved-кейсов (батчами по area,
P0 сначала). **Прошлый прогон был остановлен на середине** (перезапуск ради новых
разрешений) — остался НЕЗАКОММИЧЕННЫЙ ЧЕРНОВОЙ прогресс (в этом коммите):
- `framework/tests/test_rating.py` (TC-007, TC-008), `framework/tests/test_library.py`
  (TC-016, TC-017) — написаны, но **НЕ провалидированы** (нет 3 зелёных прогонов,
  статусы кейсов не переведены в Automated, traceability не дописан);
- расширения: `seed_db.py` (+46 строк — похоже, добавлен comment-only сидинг),
  `navigation.py`, `app_steps.py`, `rating_steps.py`, `conftest.py` (+фикстуры
  `seeded_library`, `comment_only_work`).
Первым делом test-automator должен ПРОВЕРИТЬ этот черновик (прогнать, довести до
стабильности или переписать), а не начинать с нуля.

## КРИТИЧНО: автономность qa-loop (сессия 2026-07-02/03 была про это)

Пользователь требует, чтобы qa-loop работал БЕЗ ручных подтверждений. Сделано:
- `.claude/settings.json` — 69 allow-паттернов (борда, env/tasks, adb, pytest, git
  commit локально). **Перечитывается только новыми (суб)агентами — стартуй прогон в
  СВЕЖЕЙ сессии**, иначе часть паттернов не активна.
- `scripts/tasks.ps1`: `Start-Appium` теперь сам ждёт готовности (health-check /status,
  таймаут 60s), добавлен `Stop-NodeProcesses`. Агентам ЗАПРЕЩЕНО (в их .md): ручной
  polling `sleep`/curl-циклами, `nohup`/`&`-фон, bash-`export JAVA_HOME/PATH`
  (только `env.ps1`), многострочные склейки команд (**одна команда = один вызов Bash**).
- Скилл **`/permission-audit`** + `scripts/permission_audit.py` — при жалобе на «волну
  уведомлений» запускать его (сканирует транскрипты main+субагентов, находит виновников
  и причину: несовпадение allowlist ≠ sandbox «cannot be statically analyzed» —
  фиксы разные). Скриншоты у пользователя НЕ просить.

## Как поднять окружение (в новом окне)

```powershell
. D:\AO3_tests\scripts\env.ps1     # JAVA_HOME/ANDROID_HOME/PATH
. D:\AO3_tests\scripts\tasks.ps1   # Start-Emulator, Start-Appium(health-check), Stop-NodeProcesses, Install-App, Invoke-Smoke
. D:\AO3_tests\scripts\board.ps1   # Show-Board (живая доска, теперь без обёрток)
```
Эмулятор `ao3_test_api34` (API 34). К концу прошлой сессии эмулятор/Appium были
остановлены (qemu разъедался до 3.3GB за долгий прогон — перезапускать чистым).
Сервер борды на 8777 мог остаться жить.

## Критичные факты (беречь токены)

- **Истина = код приложения.** PROJECT.md устарел (пример: «WebView dark mode applies
  on next cold start» — неверно, реально мгновенно через reload). CLAUDE.md точнее.
- **Локаторы**: код (место рендера!) → живое дерево → скриншот. Ловушки Compose:
  `tab.label.uppercase()` (вкладки Library ВЕРХНИМ регистром), `AnimatedVisibility`
  (нижняя навигация скрыта за пилюлей на Browse), клик на родителе текстового узла,
  `UiScrollable` не видит Compose-скролл (`swipe_to_text`).
- **Side panel Browse** (`BrowseSidePanel.kt`): Home, Fullscreen, A-/A+ (fontSizeStep
  0..6 → `textZoom`, TEXT_ZOOMS 100..190), Contrast (тема). Яркость — ЖЕСТ (2 пальца
  вертикально, порог 20dp; pinch ≥30dp — шрифт). Всё пишет в тот же стейт, что Settings.
- **Сидинг**: `framework/data/seed_db.py` (rating = enum SAVE/LIKE/READ/PENDING/DISLIKE;
  db+wal+shm вместе; run-as на debug). В незакоммиченном черновике — comment-only режим.
- **Cloudflare bot-check** на старте (R-03) — smoke обходит; Git Bash + adb:
  `MSYS_NO_PATHCONV=1`.
- Борда TrackState (десктоп/CLI) читает закоммиченный HEAD; живой Show-Board — рабочую папку.

## Открытые хвосты

- 4 кейса P3 в Review (TC-020/024/031/037) + TC-006 Draft (ждёт решения по BUG-001).
- R-09 (filter-profiles), R-10 (notes/tags) — proposed, ждут утверждения человеком.
- Спайк B (mitmproxy replay) — захват на Windows пуст (вероятно firewall), довести к replay-режиму.
- SAF file/folder picker не автоматизируется (блокер для части download/backup-кейсов);
  seed_db расширить под tags/downloadPath (частично сделано в черновике automator'а).
