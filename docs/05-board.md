# 05 — Визуальная борда (TrackState.AI)

Чтобы человек видел статусную машину агентов не в YAML, а как доску/канбан, мы
проецируем наши артефакты в формат [TrackState.AI](https://github.com/IstiN/trackstate)
— git-native, Jira-совместимый трекер (Flutter). Основано на наработках
`trackstate-setup-for-Dark-Factory` и `trackstate-by-Dark-Factory`.

## Модель: проекция, а не второй источник правды

- **Источник правды остаётся за агентами:** `test-cases/`, `bugs/`, `runs/`
  (markdown + YAML frontmatter). Агентов трогать не нужно.
- **`board/`** — генерируемое зеркало в формате TrackState: `project.json`,
  `config/*.json` (статусы/типы/воркфлоу), папки-тикеты `KEY/main.md`,
  `.trackstate/index/issues.json`.
- Генератор: [scripts/board_sync.py](../scripts/board_sync.py) — читает артефакты,
  мапит наши статусы на статусы TrackState (единственное место маппинга), пересобирает
  `board/` целиком. Идемпотентен.

### Маппинг статусов (наши → колонки борды по категориям new/indeterminate/done)
- **test-case:** Draft · Review · Approved · **Automated**
- **bug:** Open · Reopened · Blocked · Fixed · **Verified** · Rejected · Intended
- **run:** NeedsTriage · Triaged · **Closed**
- Приоритет: P0–P3; severity бага → приоритет (blocker/critical→P0, major→P1, minor→P2, trivial→P3).

## Как обновлять борду

```powershell
. D:\AO3_tests\scripts\board.ps1
Sync-Board        # запускает board_sync.py И делает git commit board/
```

> **Важно:** локальный провайдер TrackState читает **закоммиченный HEAD**, а не рабочую
> директорию. Поэтому после генерации нужен `git commit` — `Sync-Board` делает это сам.
> Либо запускается скиллом `/board`.

## Как смотреть — локально (сейчас)

Десктоп-приложение (портативное, Flutter, без установки Flutter SDK):
`tools/trackstate/trackstate.exe` (скачано из релиза TrackState).

```powershell
. D:\AO3_tests\scripts\board.ps1
Open-Board        # запускает trackstate.exe
# В приложении: выбрать Local repository (target = local) и папку D:\AO3_tests
```

Быстрый headless-просмотр без GUI (тот же движок, JQL):
```powershell
Show-BoardCli     # tools/ts-cli/trackstate.exe search --target local --jql "project = AO3"
```

Проверено: CLI/приложение читают борду (`session --target local` → ok, JQL находит все
тикеты). Требование локального провайдера — репозиторий инициализирован git (сделано).

## Как смотреть — по URL (потом, GitHub Pages)

Когда понадобится доступ с любого устройства:
1. Запушить `D:\AO3_tests` в GitHub-репозиторий (`board/` версионируется, `tools/` и
   `.venv` — в `.gitignore`).
2. Форкнуть `trackstate-setup`, включить Pages (Source: GitHub Actions), запустить
   workflow «Install / Update TrackState», указать в его конфиге `dataPath: board`.
3. Борда доступна по `https://<owner>.github.io/<repo>/`, читает `board/` через GitHub API.
4. Для записи из борды — fine-grained PAT с `contents:write` (по желанию; у нас запись
   идёт через артефакты + `Sync-Board`, борда read-only-зеркало).

## Куда развивать (опционально)

В релизе TrackState есть `trackstate-claude.skill` и CLI-команды
`trackstate ticket create/ticket transition`. Если позже захотим, чтобы агенты писали
статусы **нативно в борду** (без проекции), можно перевести их на эти команды — но это
меняет источник правды (см. решение: сейчас выбрана проекция).
