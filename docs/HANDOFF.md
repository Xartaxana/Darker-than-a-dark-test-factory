# HANDOFF — точка возобновления

Обновлено: 2026-07-02 (Fable 5). Читать первым при старте новой сессии.

## Что готово

- **Фаза 0** (окружение) и **Фаза 1** (каркас фреймворка) — завершены. P0 smoke = 9
  тестов, дважды подряд 9/9 зелёные. Детали: [environment-setup.md](environment-setup.md),
  [../framework/README.md](../framework/README.md).
- **9 агентов** в `.claude/agents/` + оркестрация `state/rules.yaml` + скиллы
  `.claude/skills/` (`/qa-loop`, `/run-suite`, `/triage`, `/board`). См.
  [03-agent-system.md](03-agent-system.md).
- **Визуальная борда** (проекция артефактов в TrackState): [05-board.md](05-board.md).
  Живой локальный просмотр без коммитов: `Show-Board` (сервер 127.0.0.1:8777 с кнопкой
  «↻ Обновить»). Полный TrackState/Pages — `Sync-Board`/`Open-Board`.
- Репозиторий под git (нужно провайдеру TrackState и для Pages потом). Всё закоммичено.

## Как поднять окружение (в новом окне)

```powershell
. D:\AO3_tests\scripts\env.ps1     # JAVA_HOME/ANDROID_HOME/PATH
. D:\AO3_tests\scripts\tasks.ps1   # Start-Emulator, Start-Appium, Install-App, Invoke-Smoke
. D:\AO3_tests\scripts\board.ps1   # Show-Board (живая доска)
```
Appium ОБЯЗАТЕЛЬНО с `--allow-insecure uiautomator2:chromedriver_autodownload`
(Start-Appium это делает). Эмулятор `ao3_test_api34`, API 34.

## СЛЕДУЮЩАЯ ЗАДАЧА: Фаза 2 — тест-дизайн P0/P1

Цель: агенты **test-strategist** и **test-designer** оформляют полноценные тест-кейсы
в формате Given-When-Then по всем P0/P1-областям (docs/01 §6): рейтинги, фильтрация
видимости, табы (10 шт., undo, персистентность), Library (фильтры/сортировки),
downloads, filter-profiles, заметки/теги, backup/restore, settings, error page.
Ориентир ~60–80 кейсов. Человек утверждает P0/P1 (Draft/Review → Approved).

Порядок: можно через `/qa-loop` (оркестратор подхватит правила «needs-design» и
«PROJECT.md изменился»), либо запускать агентов точечно через Task. После создания
кейсов пересобрать борду (`Show-Board`) и дать человеку на утверждение.

Уже есть стартовые артефакты (не с нуля): `test-cases/smoke/TC-001..005` (Automated),
`test-cases/library/TC-006` (Draft), `bugs/BUG-001` (Open, подписи Library), `runs/RUN-...`
(Closed). Фоновая задача task_1397829e — расхождение подписей Library для test-designer.

## Критичные факты, чтобы не переоткрывать (беречь токены — см. [[token-efficiency-practices]])

- **Локаторы выводить из кода приложения (место рендера!) → живое дерево → скриншот в
  последнюю очередь.** Ловушки Compose: `tab.label.uppercase()` (вкладки Library в
  ВЕРХНЕМ регистре FAVORITE/KUDOSED/READ/PENDING/DISLIKED/FILES), `AnimatedVisibility`
  (нижняя навигация Browse/Library/Settings скрыта на Browse за нижней ручкой-пилюлей —
  `BottomNav._expand_pill`), клик висит на родителе текстового узла, `UiScrollable` не
  видит Compose-скролл (использовать `swipe_to_text`). Панель инструментов — слева.
- **Сидинг Library:** `framework/data/seed_db.py` (взять созданную приложением БД →
  INSERT в `work_ratings` → вернуть; rating = имя enum SAVE/LIKE/READ/PENDING/DISLIKE;
  тянуть db+wal+shm вместе). Работает на debug-сборке через run-as.
- **Cloudflare bot-check** иногда на старте (риск R-03) — smoke это обходит (нативный UI+сидинг).
- **Git Bash + adb:** экспортировать `MSYS_NO_PATHCONV=1`. Фоновые процессы — не через
  Start-Process (умирают по завершении вызова).
- **Борда TrackState (десктоп/CLI) читает закоммиченный HEAD**, не рабочую папку; живой
  HTML-просмотр (`Show-Board`/board_server.py) — без коммитов.

## Открытые хвосты (не блокируют Фазу 2)

- Спайк B (mitmproxy replay): захват трафика эмулятора на Windows пуст — вероятно
  Windows Firewall на mitmdump. Довести, когда дойдём до replay-режима.
- Фоновый сервер борды (порт 8777) мог остаться запущен из прошлой сессии — при нужде
  перезапустить `Show-Board`.
