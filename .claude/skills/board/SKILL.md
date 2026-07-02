---
name: board
description: Пересобрать визуальную борду TrackState из QA-артефактов (test-cases/bugs/runs) и подсказать, как её открыть. Использовать, когда пользователь просит "обновить борду", "показать доску/тикеты/статусы", "пересобрать board".
---

# /board — просмотр и синхронизация борды

Борда — проекция наших артефактов (`test-cases/`, `bugs/`, `runs/` — источник правды)
в визуальный вид. Есть два уровня (см. docs/05-board.md).

## Стадия 1 (по умолчанию): быстрый HTML-просмотр БЕЗ коммитов
Если пользователь просто хочет «посмотреть борду»:
1. `python scripts/board_view.py` — пересобирает `board-view.html` из артефактов.
2. Открой его (`Show-Board` в scripts/board.ps1 делает и то, и другое) — это канбан по
   типам с колонками-статусами. Никаких коммитов, `board-view.html` в .gitignore.
3. Покажи пользователю сводку: сколько TC/bug/run и по каким статусам.

## Стадия 2 (TrackState / подготовка к Pages): нужен commit
Только когда нужен UI TrackState или публикация:
1. `python scripts/board_sync.py` → пересобирает `board/` (формат TrackState).
2. Коммит `board/` — локальный провайдер TrackState читает **закоммиченный HEAD**
   (`Sync-Board` делает генерацию + commit).
3. `Open-Board` (десктоп TrackState → Local repository → D:\AO3_tests) или
   `Show-BoardCli` (JQL). Для URL — GitHub Pages, путь в docs/05-board.md.

Границы: борда read-only-проекция; статусы правятся в артефактах агентами, не в board/.
