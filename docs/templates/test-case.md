---
id: TC-000            # уникальный, никогда не переиспользуется
title: Краткое название сценария
area: rating          # rating | visibility | tabs | library | downloads | filter-profiles | backup | settings | errors | canary
priority: P1          # P0 | P1 | P2 | P3
risk: R-04            # ссылка на риск из docs/01 §5 (если есть)
status: Draft         # Draft | Review | Approved | Automated
automated_by: ""      # путь к тесту + имя функции, заполняет test-automator
automation_status: "" # B3, только при Automated: active | quarantined | needs_maintenance | deprecated | retired (машина automation в schemas/transitions.yaml)
quarantine_reason: "" # обязателен при quarantined (иначе ERROR валидатора)
quarantine_since: ""  # ISO-время входа в карантин; обязателен при quarantined
quarantine_expiry: "" # дедлайн карантина; пусто = quarantine_since + sla.quarantine_max
quarantine_owner: ""  # кто выводит из карантина (обычно test-maintainer)
requirements: "PROJECT.md §Screens/Browser"   # источник требования
features: []           # id из docs/feature-registry.yaml (список, можно несколько)
blocked_reason: ""    # environment | missing_fixture | product_decision | dev_answer | permissions — заполнить при status: Blocked (docs/06 B5)
lock: ""              # агент:timestamp — ставит оркестратор
---

# TC-000 — {Название}

## Предусловия
- Состояние приложения (чистое / seed `seeds/<name>.json`), режим (replay/live),
  какая страница/экран открыты.

## Сценарий (Given-When-Then)

**Given** приложение запущено с чистыми данными и открыта страница работы `/works/{id}`
**And** панель рейтинга раскрыта

**When** пользователь нажимает рейтинг «Loved»

**Then** рейтинг сохранён: бейдж «Loved» появляется на странице без перезагрузки
**And** работа отображается во вкладке Loved экрана Library

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Работа | ao3_id из `data/works.py` |

## Заметки для автоматизации
- Какие шаги/экраны фреймворка использовать, известные подводные камни.

## Чек-лист качества (test-designer проходит перед `Review`)
- [ ] Один сценарий — один кейс; нет «и ещё проверить...»
- [ ] Given описывает полное состояние, воспроизводимое фикстурами
- [ ] Then проверяет наблюдаемое поведение, а не реализацию
- [ ] Указаны приоритет, область и источник требования
- [ ] Кейс независим от порядка выполнения других кейсов
