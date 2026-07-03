# HANDOFF — точка возобновления

Обновлено: 2026-07-03 (сессия Opus 4.8). Читать первым при старте новой сессии.

## Итоги сессии 2026-07-03 (Opus 4.8) — коротко

Сессия шла по «архитектурным» задачам под сильную модель:
1. **Спецификация тёмной фабрики** (docs/06) + `rules.yaml` v2 + `sla.yaml` — детали ниже.
2. **Борда опубликована на GitHub Pages** — https://xartaxana.github.io/Darker-than-a-dark-test-factory/
   (репозиторий https://github.com/Xartaxana/Darker-than-a-dark-test-factory, `origin`,
   ветка master). PAT подключён, карточки НЕ двигать до board-inbound.
3. **Спайк B РЕШЁН** (mitmproxy record→replay) — детали в отдельном разделе ниже.
4. **Пункт 2 ЗАВЕРШЁН:** инструкции агентов обновлены под docs/06 (5 файлов
   `.claude/agents/`):
   - **failure-analyst** — вердикт `APP_CHANGED` (D9) + сверка `git log app-under-test`
     между сборками (только чтение), цитата коммита в обоснование;
   - **fix-verifier** — три режима: `verify` (D1), `recheck-rejected` (D4),
     `still-repro` (D3); ведёт `status_since`/`reopen_count`/`dispute_count`/
     `last_seen_in`; пинг-понг ≥ `sla.reopened_pingpong` → Blocked + эскалация;
   - **bug-reporter** — роли `creator`/`responder` (D6, ведёт `## Обсуждение`,
     `awaiting`), `regression_of` (D7), дубликат от человека (D10);
   - **test-maintainer** — охватывает `APP_CHANGED`/`Intended` (D5/D9): тест под НОВОЕ
     поведение, не маскировка;
   - **qa-orchestrator** — Шаг 0 `pre_steps` (stale_locks, sla_sweep,
     board_inbound[план], build_watch[план]); принцип «permission-окно = дефект»
     (деградировать+логировать, не ждать); передаёт `mode`/`role` в Task.
   Всё согласовано с `state/rules.yaml` v2.

5. **Пункт 3 — ядро board_inbound ГОТОВО** (сильной моделью), обвязка делегирована
   субагенту. Дизайн: [07-board-inbound.md](07-board-inbound.md). Ядро
   `scripts/board_inbound.py` — трёхсторонняя сверка курсор↔борда↔артефакт (различает
   правку человека от рассинхрона), whitelist переходов, конфликт→Blocked+эскалация,
   вставка `status_since` в legacy-артефакты, UTF-8 stdout. `board_sync.py` пишет
   курсор `state/board-cursor.json` (контракт). Проверено по всем веткам, закоммичено.
   **Обвязка (делегирована субагенту, принята и закоммичена):** синхронизация
   комментариев борда↔`## Обсуждение` (формат `board/<KEY>/comments/<NNNN>.md` снят с
   исходников TrackState), `git pull` борды с деградацией при офлайне, 15 pytest-тестов
   (`scripts/tests/`, 15 passed), `Sync-BoardInbound` в board.ps1. Пометка [план] с
   board_inbound снята в qa-orchestrator.md и rules.yaml. board_inbound готов к работе
   в pre_steps. **Остаётся [план]:** build_watch (сборка APK по git-пушу приложения).
   - **Известное наблюдение (не баг ядра, не триггерится сейчас):** `bs._parse_frontmatter`
     через PyYAML коэрсит ISO-таймстампы в datetime (`str()` → пробел вместо `T`).
     Ядро сравнивает только строковые статусы (не таймстампы), поэтому безопасно;
     синхронизация комментариев читает `created` сырой строкой в обход этого. Если в
     будущем ядро начнёт сравнивать таймстамп-поля как строки — учесть.

Порядок «архитектурного» плана (согласован с владельцем): спайк B ✓ → обновление
агентов под docs/06 ✓ → board_inbound ✓ (ядро+обвязка, готов) →
**репетиция тёмного дня** (следующий) → SAF-пикер.
Рутина (sla-sweep/stale-locks/build-watch скрипты, автоматизация 41 Approved-кейса) —
не под сильную модель, отложена.

## Что готово

- **Фаза 0/1/2** — без изменений, см. предыдущие записи ниже и
  [environment-setup.md](environment-setup.md), [../framework/README.md](../framework/README.md).
- **Фаза 3 (автоматизация Approved-кейсов) — ИДЁТ, первый батч закрыт.**
  Черновик прошлой сессии (TC-007/008/016/017) стабилизирован и провалидирован:
  - **TC-007** → `Automated` (`test_rating.py::test_rate_work_from_work_page_panel`)
  - **TC-008** → `Automated` (`test_rating.py::test_deselect_rating_on_work_page_panel`)
  - **TC-016** → был `Automated` и стабилен ещё с прошлой сессии, подтверждено без изменений
  - **TC-017** → `Automated` (`test_library.py::test_comment_only_not_in_any_rating_tab`)
  - **TC-009** → обоснованно возвращён в `Review` — тот же replay-блокер, что у
    TC-013/014/015 (нужна фикстура листинга с блёрбом синтетической работы,
    `framework/data/recordings/` пусто, спайк B не завершён)
  - **TC-021** (backup/SAF) сознательно не тронут — отдельная задача, лок оставлен
  - Все Automated-кейсы подтверждены 3 стабильными зелёными прогонами + полный
    P0 smoke 17/17 (регрессий от правок в `conftest.py` нет)
  - Найдены и исправлены 2 реальных бага **в тестах** (не в приложении):
    порядок фикстур (сидинг должен идти строго до старта Appium-сессии — иначе
    `pm clear`/сидинг не подхватываются уже запущенным процессом) и переход на
    вкладку Browse перед повторным тапом рейтинга (RatingMenu рендерится только
    там). Плюс обход особенности `savePanelRating` (скрейп реальной 404-страницы
    для несуществующего синтетического `ao3_id`) через новую фикстуру
    `placeholder_seeded_work` (`framework/tests/conftest.py`).
  - **Пользователь ОСТАНОВИЛ конвейер здесь намеренно** — дальше не диспетчеризировать
    новые Approved-кейсы, продолжать в новой сессии.
- **Статусы test-cases сейчас** (55 всего): 9 `Automated` (5 smoke + TC-007/008/016/017),
  **41 `Approved`** (готовы к автоматизации), 8 `Review` (TC-009/013/014/015 — replay-блокер;
  TC-020/024/031/037 — P3, ждут решения человека), 1 `Draft` (TC-006, ждёт решения по BUG-001).
- **Борда** пересобрана и закоммичена (`0fada79`).
- **Permission-audit / автономность qa-loop** — большая ревизия в этой сессии
  (подробности ниже, раздел «Автономность qa-loop»).
- **Спецификация «тёмной фабрики» написана (2026-07-03)** —
  [06-dark-factory.md](06-dark-factory.md): событийная модель (build-watch,
  board-inbound, SLA-sweep, расписание), матрица реакций на действия разработчика
  D1–D12 (Rejected/Intended/комментарии/сборка без фикса/регрессия от фикса и т.д.),
  эскалации. Синхронно обновлены: `state/rules.yaml` → **v2** (pre_steps + 4 новых
  правила), создан `state/sla.yaml`, правки в docs/03/04/05 и шаблоне бага
  (`status_since`, `awaiting`, `## Обсуждение`…). Реализация — Фаза 4.5 роадмапа
  (docs/04): скрипты build-watch/sla-sweep/board-inbound + обновление 4 агентов
  под новые режимы. Матрица D1–D12 действует уже сейчас (переходы человек пока
  делает правкой frontmatter).
- **Борда опубликована на GitHub Pages (2026-07-03)** —
  https://xartaxana.github.io/Darker-than-a-dark-test-factory/ (репозиторий
  https://github.com/Xartaxana/Darker-than-a-dark-test-factory, публичный, ветка
  master). Данные читаются в рантайме из board/ HEAD — `Sync-Board` теперь сам
  пушит origin. Пользователь создал fine-grained PAT (Contents: RW) и подключил
  на борде — запись С борды работает, но **договорённость: карточки не двигаем**,
  пока не реализован board-inbound (иначе Sync-Board перезапишет изменения борды).
  gh CLI НЕ авторизован; GitHub API — токеном из git credential fill (см. память
  github-auth-via-gcm). Приоритетный следующий шаг Фазы 4.5: board_inbound.py.

## СЛЕДУЮЩАЯ ЗАДАЧА: продолжить Фазу 3

`/qa-loop` в новой сессии → оркестратор продолжит батчами по area, P0 сначала, по
оставшимся **41 Approved**-кейсу. Порядок такой же, как раньше: rating/library P0
уже почти закрыты (кроме TC-009/010/011/012), дальше settings/backup/tabs/library
P1 и т.д. TC-021 (backup/SAF) — лок `test-automator:2026-07-02T22:22:24Z` уже стоит,
это отдельная незавершённая задача (SAF picker не автоматизируется штатно).

**Перед стартом нового прохода реши, коммитить ли текущий рабочий прогресс** — сейчас
некоммичены (не запрашивалось в этой сессии):
- `framework/tests/conftest.py`, `test_rating.py`, `state/traceability.md`,
  изменённые `test-cases/{rating,library,visibility,backup}/*.md` — результат
  стабилизации TC-007/008/017 (Automated) и TC-009 (Review);
- `scripts/tasks.ps1` — фикс `Start-Appium` (`npx` → `npx.cmd`, см. ниже);
- `.claude/agents/{qa-orchestrator,test-automator,test-maintainer}.md`,
  `.claude/settings.json`, `.claude/skills/permission-audit/SKILL.md` — правки
  инструкций/allowlist из ревизии автономности (см. ниже).

## КРИТИЧНО: автономность qa-loop, раунд 2 (сессия 2026-07-03)

Прошлая сессия (2026-07-02/03) уже чинила это один раз; в этой сессии всплыли
новые классы проблем — конвейер реально прогонялся впервые целиком (Фаза 3), и
вскрылось то, что раньше не проявлялось.

- **Разобрано 3 волны уведомлений** через `/permission-audit` (окна 180/60 мин +
  разбор скриншотов после). Скрипт: `scripts/permission_audit.py`.
- **`.claude/settings.json` (версионируемый, общий) расширен**: wildcard'ы для
  `& { env.ps1; tasks.ps1; Start-Emulator/Start-Appium/Install-App/Stop-NodeProcesses/
  Invoke-Suite* }` (обёрточная форма с `-ExecutionPolicy Bypass`, которой не было),
  безопасные read-only паттерны (`Get-CimInstance`, `Get-ChildItem`, `Test-Path`,
  `Select-String -Path`, `Get-NetTCPConnection`, `Get-Process -Id`, `git status*`,
  `git diff*`, `curl` на любой `127.0.0.1:<port>`), и **важный фикс глобов**:
  `Edit(.claude/agents/**)`/`Write(...)` не покрывали файлы НАПРЯМУЮ в `agents/`/
  `skills/` (только вложенные) — добавлены паттерны `.claude/agents/*` и
  `.claude/skills/*` рядом с `**`-вариантами.
- **`.claude/settings.local.json` (личные «Allow always») регулярно разрастается
  до 200+ строк за проход** — почти всё дубли уже широких правил, разовая история
  установки или (важно!) **легитимизированный антипаттерн**. Дважды за сессию
  чистил до ~8 высокоуровневых записей (`WebSearch`, `Skill(...)`, `Read(...)`,
  `gh release *`, `ts-cli`). **`/permission-audit` теперь сам включает этот шаг**
  (см. `.claude/skills/permission-audit/SKILL.md`, шаг 4) — гоняй его периодически,
  не только по жалобе на волну.
- **Найден и закрыт реальный обход правила «не поллить sleep-циклом»**:
  test-automator написал отдельные файлы `wait_appium.ps1`/`wait_file_grow.ps1`
  (тот же `do { Start-Sleep N } while(...)`, спрятанный в файл вместо инлайн-команды —
  такой файл легче проходит sandbox-проверку и тише получает «Allow always»).
  Причина, по которой агент вообще к этому прибегнул — реальный баг
  **`scripts/tasks.ps1::Start-Appium`**: `Start-Process -FilePath "npx"` на этой
  машине резолвится не в `npx.cmd`, а куда-то не туда (наблюдалось — открывался
  Notepad). **Исправлено**: `"npx"` → `"npx.cmd"` в `Start-Appium` (строка ~23).
  В `.claude/agents/test-automator.md` добавлен явный запрет и на сам манёвр
  (не писать `wait_*.ps1`-костыли в scratchpad), и подсказка чинить `tasks.ps1`
  напрямую, если штатная функция сломана — это территория агента (`scripts/`),
  а не `app-under-test/`.
- **`qa-orchestrator.md` дважды поправлен**: (1) запрет диспетчеризировать Task
  асинхронно + затем поллить его завершение ручным `sleep`/`timeout ... while true` —
  теперь либо синхронный Task, либо простое завершение хода без polling-Bash;
  (2) сканирование локов/статусов test-cases — через `Grep`, не bash-цикл
  `for f in ...; do ... done` (sandbox всегда просит подтверждение на такой цикл);
  (3) коммит борды — однострочный `git commit -m "текст"`, без heredoc
  `-m "$(cat <<'EOF' ...)"` (та же причина — многострочная команда).
- **Самопроверка**: во время самого аудита я (ассистент) дважды сам создал лишние
  уведомления — `Bash(python -m json.tool ...)` после каждого `Edit` «на всякий
  случай» (лишний, `Edit` уже гарантирует применение правки) и bash-цикл
  `for f in a.ps1 b.ps1 c.ps1; do ...; done` для просмотра нескольких scratch-файлов
  (тот же антипаттерн, который в этот момент чинил у других агентов). Зафиксировано
  в памяти [[avoid-bash-for-reads]] — для нескольких известных файлов один `Read`
  на файл, не bash-цикл; не гонять валидацию Bash'ем после Edit/Write.
- **Не устранимо по дизайну**: правка самого `.claude/settings.json` («Allow Claude
  to edit settings.json») спрашивает всегда — это защита от самоизменения разрешений,
  встречается только при мета-работе над конфигами, не в обычном `/qa-loop`.

## Как поднять окружение (в новом окне)

```powershell
. D:\AO3_tests\scripts\env.ps1     # JAVA_HOME/ANDROID_HOME/PATH
. D:\AO3_tests\scripts\tasks.ps1   # Start-Emulator, Start-Appium(health-check, npx.cmd-фикс), Stop-NodeProcesses, Install-App
. D:\AO3_tests\scripts\board.ps1   # Show-Board (живая доска)
```
Эмулятор `ao3_test_api34` (API 34). К концу этой сессии эмулятор/Appium
предположительно остановлены агентом — перезапускать чистым в новой сессии.
Сервер борды на 8777 мог остаться жить.

## Критичные факты (беречь токены)

- **Истина = код приложения.** PROJECT.md устарел. CLAUDE.md точнее.
- **Локаторы**: код (место рендера!) → живое дерево → скриншот. Ловушки Compose:
  `tab.label.uppercase()`, `AnimatedVisibility` (нижняя навигация скрыта за пилюлей
  на Browse; **RatingMenu рендерится только на вкладке Browse** — см. фикс TC-008),
  клик на родителе текстового узла, `UiScrollable` не видит Compose-скролл
  (`swipe_to_text`).
- **Порядок фикстур в тестах критичен**: сидинг (`app_steps.clean_state()`/
  `seed_db.seed()`) должен идти строго ДО создания Appium-сессии (фикстура `driver`),
  иначе `pm clear`/сидинг не подхватываются уже запущенным процессом. Используй
  готовые фикстуры `seeded_library`/`comment_only_work`/`loved_work_seeded`/
  `placeholder_seeded_work` (`framework/tests/conftest.py`), не вызывай сидинг
  внутри тела теста.
- **`savePanelRating` (`BrowserViewModel.kt`)**: если для `workId` ещё нет строки в
  Room, панель скрейпит title/author/wordCount с живой страницы `/works/{id}` —
  для несуществующих синтетических `ao3_id` это возвращает пустые поля (404-страница).
  Обход — предзаполнить строку с `rating=None`, но полными title/author/wordCount
  (см. `placeholder_seeded_work`), тогда панель идёт по ветке «обновить существующую».
- **Side panel Browse** (`BrowseSidePanel.kt`): Home, Fullscreen, A-/A+, Contrast,
  яркость-жест (2 пальца, порог 20dp; pinch ≥30dp — шрифт).
- **Cloudflare bot-check** на старте (R-03); Git Bash + adb: `MSYS_NO_PATHCONV=1`.
- Борда TrackState (десктоп/CLI) читает закоммиченный HEAD; живой Show-Board —
  рабочую папку.
- **Не гонять сканирование/просмотр нескольких файлов через bash-цикл** — Grep/Read
  по одному, иначе гарантированное подтверждение (sandbox-эвристика на циклы).

## Спайк B (mitmproxy replay) — РЕШЁН (2026-07-03)

Полный цикл record→replay HTTPS WebView доказан. Блокером был НЕ firewall (прежняя
гипотеза неверна), а доверие к CA в mount-namespace приложения на Android 14. Решение
и разбор — [environment-setup.md](environment-setup.md) §Спайк B. Артефакты сессии:
- `scripts/install-mitm-ca.sh` переписан (namespace-aware: mount в init-ns + `stop&&start`
  фреймворка + верный SELinux-контекст каталогов); новый `scripts/ca-mount.sh`.
- `scripts/tasks.ps1::Start-Emulator` получил флаг `-WritableSystem`.
- `framework/core/mitm.py` — рабочие флаги replay + `set/clear_device_proxy`.
- Recording-фикстура закоммичена: `framework/data/recordings/ao3_home_smoke.mitm`
  (домашняя AO3, 48 флоу). Разблокирует TC-009/013/014/015.
- **Порядок запуска replay-прогона:** `Start-Emulator -WritableSystem` → дождаться
  boot → `bash scripts/install-mitm-ca.sh` (сам перезапускает фреймворк, ~1 мин) →
  `Install-App` → mitmdump в нужном режиме → прокси гостя `10.0.2.2:8080`. Mount'ы
  не переживают reboot эмулятора — install-скрипт прогонять после каждого старта.
- **Хвост:** сейчас `install-mitm-ca.sh` — отдельный ручной шаг. Стоит встроить его в
  `test-runner`/`run-suite` для replay-режима (поднять окружение целиком автономно).
  TC-009/013/014/015 всё ещё требуют фикстуру ЛИСТИНГА с блёрбом синтетической работы
  (домашняя записана; нужна запись страницы поиска/листинга — отдельная задача дизайна).

## Открытые хвосты

- 41 Approved-кейс ждёт автоматизации (следующий батч).
- TC-009/013/014/015 в Review — транспорт replay готов (спайк B решён); осталось
  записать фикстуру листинга с блёрбом синтетической работы и встроить установку CA
  в test-runner.
- 4 кейса P3 в Review (TC-020/024/031/037) + TC-006 Draft (ждёт решения по BUG-001).
- R-09 (filter-profiles), R-10 (notes/tags) — proposed, ждут утверждения человеком.
- Спайк B (mitmproxy replay) — захват на Windows пуст (вероятно firewall), довести
  к replay-режиму — это разблокирует TC-009/013/014/015.
- SAF file/folder picker не автоматизируется (блокер TC-021 и части
  download/backup-кейсов).
- Некоммиченные изменения этой сессии — см. список в начале файла.
