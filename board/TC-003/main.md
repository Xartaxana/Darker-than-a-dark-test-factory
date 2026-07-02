---
key: "TC-003"
project: "AO3"
issueType: "test-case"
status: "tc-automated"
priority: "p0"
summary: "Засеянная работа попадает в свою вкладку Library"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:library", "risk:R-04"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-02T03:00:00Z"
updated: "2026-07-02T03:00:00Z"
archived: false
resolution: "done"
---

# Засеянная работа попадает в свою вкладку Library

_Спроецировано из `test-cases/smoke/TC-003.md` (источник правды).
Статус в нашей машине: **Automated**._

# TC-003 — Рейтинг → правильная вкладка Library

## Сценарий (Given-When-Then)
**Given** в Room засеяна работа с рейтингом R (по одной на каждый из SAVE/LIKE/READ/PENDING/DISLIKE)
**When** открыт экран Library и выбрана вкладка для рейтинга R
**Then** засеянная работа присутствует в этой вкладке

## Заметки
Детерминизм через сидинг Room (framework/data/seed_db.py), без обращения к AO3.
Параметризован на 5 рейтингов. Вкладки: FAVORITE/KUDOSED/READ/PENDING/DISLIKED.
