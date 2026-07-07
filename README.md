# AO3 Reader — Тестовый проект

Автоматизированное тестирование Android-приложения **ao3-wrapper**
(https://gitlab.com/Xartaxana1/ao3-wrapper) — WebView-обёртки над AO3 с локальной
системой рейтингов (Kotlin, Jetpack Compose, Room, JS-bridge).

**Ключевое ограничение:** мы тестируем приложение как чёрный ящик и **не имеем права
вносить изменения в код приложения**. Весь тестовый код, документация и агенты живут
в этом репозитории.

## Структура плана

| Документ | Содержание |
|---|---|
| [docs/01-test-strategy.md](docs/01-test-strategy.md) | Стратегия тестирования: скоуп, уровни, риски, приоритеты P0–P3, режимы live/replay |
| [docs/02-framework-architecture.md](docs/02-framework-architecture.md) | Архитектура тестового фреймворка: стек, слои, паттерны, структура каталогов, конвенции |
| [docs/03-agent-system.md](docs/03-agent-system.md) | Система агентов: роли, триггеры, статусная машина артефактов, оркестрация |
| [docs/04-roadmap.md](docs/04-roadmap.md) | Дорожная карта внедрения по фазам с критериями выхода |
| [docs/templates/](docs/templates/) | Шаблоны артефактов: тест-кейс (GWT), баг-репорт, отчёт о прогоне |
| [docs/08-external-architecture-review.md](docs/08-external-architecture-review.md) | Внешнее ревью архитектуры тёмной QA-фабрики: пробелы, best practices и предложения к roadmap |
| [docs/09-improvement-plan.md](docs/09-improvement-plan.md) | План улучшений по итогам ревью 08 + решения владельца (2026-07-07): этапы, критерии выхода, отклонённое |

## Целевая структура репозитория (после реализации)

```
D:\AO3_tests\
├── README.md
├── docs/                  # стратегия, план, архитектура, агенты, шаблоны
├── test-cases/            # тест-кейсы в Given-When-Then (markdown + YAML frontmatter)
├── bugs/                  # реестр багов (markdown + YAML frontmatter со статусами)
├── runs/                  # отчёты о прогонах
├── framework/             # код тестового фреймворка (см. docs/02) — РЕАЛИЗОВАН, P0 smoke зелёный
├── .claude/
│   ├── agents/            # 9 определений агентов (субагенты Claude Code) — СОЗДАНЫ
│   └── skills/            # /qa-loop, /run-suite, /triage — СОЗДАНЫ
└── state/                 # rules.yaml, orchestrator-log.md, traceability.md, app-under-test.yaml
```

## Как это запускать (агенты)

- `/qa-loop` — один проход конвейера: **верхний уровень** сам выполняет pre_steps,
  сканирует статусы артефактов и по [state/rules.yaml](state/rules.yaml) диспатчит
  воркеров глубины 1 (qa-orchestrator — только планировщик для `--dry-run`, docs/03 §1).
- `/run-suite [smoke|regression|canary]` — прогон набора через **test-runner**.
- `/triage [RUN-…]` — разбор падений: **failure-analyst** → **bug-reporter** /
  **test-maintainer**.

9 агентов (docs/03): qa-orchestrator, test-strategist, test-designer, test-automator,
test-runner, failure-analyst, bug-reporter, fix-verifier, test-maintainer. У каждого —
персона+границы, триггер, воркфлоу, шаблон, чек-лист готовности, эскалация. Общая
незыблемая граница: **никто не правит код в `app-under-test/`**.

## Визуальная борда (для человека)

Статусы агентов видны не только в YAML, но и как доска/канбан через **TrackState.AI**.
`board/` — генерируемая проекция наших артефактов (источник правды — `test-cases/`,
`bugs/`, `runs/`). Подробно — [docs/05-board.md](docs/05-board.md).

```powershell
. D:\AO3_tests\scripts\board.ps1
Show-Board     # живая доска в браузере с кнопкой «↻ Обновить», БЕЗ коммитов (стадия 1)
Sync-Board     # пересобрать board/ + git commit (для десктоп TrackState / Pages)
Open-Board     # десктоп TrackState (Local repository -> D:\AO3_tests)
```

Или скилл `/board`. Живая HTML-доска (`Show-Board`) пересобирается из артефактов по
кнопке, без коммитов. Полный TrackState проверен официальным CLI: 8 стартовых тикетов
(6 TC, 1 bug, 1 run) видны через JQL.

Быстрое возобновление работы — [docs/HANDOFF.md](docs/HANDOFF.md).

## Принципы (унаследованы из референсов)

- **BMAD TEA**: риск-ориентированное планирование, приоритеты P0–P3, шаблоны с
  чек-листами валидации, каждый артефакт имеет машиночитаемый статус.
- **dmtools / Dark Factory**: оркестратор со статусной машиной, по одному
  специализированному агенту на этап конвейера, локи против двойной обработки,
  эскалация человеку через статус `Blocked`, агенты **создают и верифицируют** баги,
  но никогда не чинят код приложения.
