---
id: CH-000              # уникальный, max+1, не переиспользуется
title: Краткая миссия сессии
area: rating            # область test-cases/ ИЛИ cross-area
risk: R-04              # рисковый якорь из docs/01 §5 (или пусто + причина в Mission)
status: Planned         # Planned | InProgress | Done
timebox_min: 60         # таймбокс сессии, минут
trigger: ""             # new-feature | app-changed | pre-release | bug-cluster
executed_at: ""         # ISO-время фактического исполнения (заполняет exploratory-tester)
executed_by: ""         # агент/модель исполнителя
found_bugs: []          # [AT-BUG-...] — заведённые по находкам (через bug-reporter)
followup_tc: []         # [TC-...] — кейсы, заведённые по находкам (через test-designer)
new_risks: []           # [R-...] — предложенные в docs/01 §10 риски
lock: ""                # агент:timestamp
---

# CH-000 — {Миссия}

## Mission
Что исследуем и зачем (одним абзацем): гипотеза о слабом месте, чем сессия
отличается от существующих кейсов области.

## Scope
- **In:** экраны/потоки/данные, входящие в сессию.
- **Out:** что сознательно не трогаем (и почему).

## Риски и гипотезы
- Какие отказы ожидаем найти (связь с риском frontmatter).

## Эвристики / туры
- Например: interruptions-тур (звонок/поворот/kill посреди операции),
  data-тур (граничные значения, unicode, пустые поля), navigation-тур
  (back/undo/deep-link), state-тур (replay vs live, протухшие cookies).

## Data setup
- Seed/фикстуры, режим (replay/live), состояние Room до сессии —
  воспроизводимо, как Given кейса.

## Протокол сессии
Хронология: что делал → что наблюдал. Скриншоты — в
`exploratory-charters/attachments/CH-NNN/`, сюда — ссылки.

## Находки
| # | Наблюдение | Вердикт (bug / test-gap / risk / ok) | Артефакт |
|---|---|---|---|
| 1 | … | … | AT-BUG-… / TC-… / R-… |

## Follow-up (обязателен при Done)
- Каждая находка-«bug» → bug-reporter (id в `found_bugs`).
- Каждая находка-«test-gap» → test-designer (id в `followup_tc`).
- Каждая находка-«risk» → предложение в docs/01 §10 (id в `new_risks`).
- Находок нет — явная строка «сессия чистая, находок нет» (валидный итог).
