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
created: "2026-08-04T12:20:00Z"
updated: "2026-08-04T12:20:00Z"
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
