# HANDOFF — точка возобновления

Дата: 2026-07-02. Модель: Fable 5.

## Где мы

- **Фаза 0** (окружение) и **Фаза 1** (каркас фреймворка) — завершены.
- Фреймворк: `framework/`, Appium 3.5.2 + pytest + Allure. P0 smoke = 9 тестов,
  дважды подряд 9/9 зелёные (~3.5 мин на AVD). Запуск: `scripts/env.ps1` +
  `scripts/tasks.ps1`. Appium стартовать с
  `--allow-insecure uiautomator2:chromedriver_autodownload`.
- Окружение портативно в `tools/` (JDK 21, Android SDK, AVD `ao3_test_api34`,
  Appium, venv в `framework/.venv`). Виртуализация включена (AEHD 2.2).

## Текущая задача: СОЗДАНИЕ АГЕНТОВ (решение пользователя)

Начинаем с агентов, НЕ с тест-дизайна. Реализовать 9 агентов из
[03-agent-system.md](03-agent-system.md) как субагенты Claude Code:

`.claude/agents/*.md` — по одному файлу на агента. Стандарт содержимого (docs/03 §5):
персона+границы (для всех: «не изменять код в app-under-test/»), триггер (условие
запуска, проверяется самим агентом), пошаговый воркфлоу, ссылка на шаблон из
`docs/templates/`, чек-лист готовности, протокол эскалации (`Blocked`).

9 агентов: qa-orchestrator, test-strategist, test-designer, test-automator,
test-runner, failure-analyst, bug-reporter, fix-verifier, test-maintainer
(триггеры и артефакты — docs/03 §1, статусные машины — §2, правила — §3).

Оркестрация: `state/rules.yaml` (правила из docs/03 §3) + скиллы
`.claude/skills/`: `/qa-loop`, `/run-suite`, `/triage`.

Артефакты — markdown+YAML frontmatter: `test-cases/`, `bugs/`, `runs/`, `state/`.

## Открытые хвосты

- Фоновая задача task_1397829e для test-designer: расхождение подписей вкладок Library
  (PROJECT.md «Loved/Liked/Downloads» vs факт «Favorite/Kudosed/Files»).
- Спайк B (mitmproxy replay): захват трафика эмулятора на Windows пуст — вероятно
  Windows Firewall на mitmdump. Не блокирует; доводится когда дойдём до replay.

## Факты об UI (сверено с живым приложением, важно для локаторов)

- Нижняя навигация Browse/Library/Settings скрыта на Browse за нижней ручкой-пилюлей.
- Вкладки Library в ВЕРХНЕМ регистре: FAVORITE/KUDOSED/READ/PENDING/DISLIKED/FILES.
- Панель инструментов — вертикальная слева (PanelSide.LEFT).
- Кнопка «Clear…» с юникод-многоточием, клик в Compose на родителе.
- Cloudflare bot-check иногда на старте (риск R-03).
- Сидинг Library: `framework/data/seed_db.py` (взять БД приложения → INSERT в
  `work_ratings` → вернуть; rating = имя enum SAVE/LIKE/READ/PENDING/DISLIKE).
