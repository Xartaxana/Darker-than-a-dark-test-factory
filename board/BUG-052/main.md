---
key: "BUG-052"
project: "AO3"
issueType: "bug"
status: "bug-open"
priority: "p2"
summary: "Scan for downloads не показывает прогресс при большом числе файлов — кнопка выглядит зависшей"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "sev:minor"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-09T13:05:00Z"
updated: "2026-08-09T13:05:00Z"
archived: false
resolution: null
---

# Scan for downloads не показывает прогресс при большом числе файлов — кнопка выглядит зависшей

_Спроецировано из `bugs/BUG-052.md` (источник правды).
Статус в нашей машине: **Open**._

# BUG-052 — Scan for downloads без индикатора прогресса

## Окружение
- Версия: 1.10 (versionCode 11), commit 63f6aac

## Шаги воспроизведения (Given-When-Then)

**Given** в папке загрузок ≥50 html-файлов
**When** пользователь нажимает Settings → Scan for downloads
**Then (ожидание)** индикатор прогресса или блокировка кнопки на время скана
**Then (факт)** кнопка без реакции до финального снекбара «Scan complete» — выглядит зависшей, возможен повторный тап

## Частота
Всегда на большой папке.

## Анализ
UX-косметика; повторный тап запускает второй скан (следствие — дубль-снекбары).

## Обсуждение

**[qa/Lead @ 2026-08-04T18:22:00Z]** Пометка репетиции (карта
runs/REHEARSAL-2026-08-04.md, П18): предшествовавший конфликту переход
артефакта Open→Rejected был НАМЕРЕННОЙ СИМУЛЯЦИЕЙ хода фабрики рукой
Lead (перехода для актора lead в schemas/transitions.yaml нет —
зафиксировано заранее критик-входом плана). Конфликт «человек→Intended
vs агент→Rejected» — сеяная подкладка; Blocked снимет разбор T0+6ч.

**[Lead @ 2026-08-09T13:05:00Z] РАЗБОР РЕПЕТИЦИИ — ЗАКРЫТ КАК СЕЯНЫЙ.**
Свидетельство П18 получено дословно: board_inbound дал «CONFLICT →
Blocked + эскалация (человек→Intended, агент→Rejected)»,
`blocked_reason: product_decision`, строка БЕЗ [sla:]. Разбор: Blocked→Open
ходом владельца (легальный переход «*→Open by human»; исполнен Lead'ом по
слову владельца на разборе — тот же канал, что T0-ходы окна), затем
закрыт `resolution: wontfix` (дефект вымышлен). Строка конфликта в
state/escalations.md (2026-08-04T18:18:52Z) этим разрешена.
НЕ публиковать в GitLab (seeded).
