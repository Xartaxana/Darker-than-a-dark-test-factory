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

- `/qa-loop` — один проход конвейера: **qa-orchestrator** сканирует статусы артефактов
  и по [state/rules.yaml](state/rules.yaml) диспатчит нужных агентов.
- `/run-suite [smoke|regression|canary]` — прогон набора через **test-runner**.
- `/triage [RUN-…]` — разбор падений: **failure-analyst** → **bug-reporter** /
  **test-maintainer**.

9 агентов (docs/03): qa-orchestrator, test-strategist, test-designer, test-automator,
test-runner, failure-analyst, bug-reporter, fix-verifier, test-maintainer. У каждого —
персона+границы, триггер, воркфлоу, шаблон, чек-лист готовности, эскалация. Общая
незыблемая граница: **никто не правит код в `app-under-test/`**.

Быстрое возобновление работы — [docs/HANDOFF.md](docs/HANDOFF.md).

## Принципы (унаследованы из референсов)

- **BMAD TEA**: риск-ориентированное планирование, приоритеты P0–P3, шаблоны с
  чек-листами валидации, каждый артефакт имеет машиночитаемый статус.
- **dmtools / Dark Factory**: оркестратор со статусной машиной, по одному
  специализированному агенту на этап конвейера, локи против двойной обработки,
  эскалация человеку через статус `Blocked`, агенты **создают и верифицируют** баги,
  но никогда не чинят код приложения.
