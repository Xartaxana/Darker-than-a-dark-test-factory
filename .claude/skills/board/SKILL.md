---
name: board
description: Пересобрать визуальную борду TrackState из QA-артефактов (test-cases/bugs/runs) и подсказать, как её открыть. Использовать, когда пользователь просит "обновить борду", "показать доску/тикеты/статусы", "пересобрать board".
---

# /board — синхронизация и просмотр борды

Борда — это проекция наших артефактов в формат TrackState (см. docs/05-board.md).
Источник правды остаётся за `test-cases/`, `bugs/`, `runs/`; `board/` — генерируемое зеркало.

Шаги:
1. Запусти генератор: `python scripts/board_sync.py` (пересобирает `board/` из артефактов).
2. Закоммить `board/`: локальный провайдер TrackState читает **закоммиченный HEAD**,
   поэтому без коммита приложение не увидит изменения. (Скрипт `Sync-Board` в
   `scripts/board.ps1` делает и то, и другое.)
3. Покажи пользователю сводку тикетов (можно через
   `tools/ts-cli/trackstate.exe search --target local --jql "project = AO3 ORDER BY key ASC"`):
   сколько TC/bug/run и их статусы.
4. Напомни, как открыть визуально: `Open-Board` (десктоп TrackState → Local repository →
   папка D:\AO3_tests). Для доступа по URL — путь на GitHub Pages в docs/05-board.md.

Границы: борда read-only-проекция; правки статусов делаются в артефактах агентами, не в board/.
