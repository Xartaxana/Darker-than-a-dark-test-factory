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

## Как смотреть — локально (стадия 1)

Есть два способа. Для повседневного «глянуть статусы» — первый (без коммитов).

### A. Живая доска в браузере с кнопкой «↻ Обновить» — БЕЗ git и коммитов (рекомендуется)

[scripts/board_server.py](../scripts/board_server.py) поднимает локальный сервер
(`http://127.0.0.1:8777/`), который **пересобирает доску из артефактов на каждый
запрос**. В окне есть кнопка **↻ Обновить** — она просто перезагружает страницу, а
данные каждый раз читаются заново из `test-cases/`, `bugs/`, `runs/`. Никаких коммитов.

```powershell
. D:\AO3_tests\scripts\board.ps1
Show-Board        # запускает сервер и открывает браузер; Ctrl+C в окне — остановить
```

Это канбан по типам (Test Cases / Bugs / Runs) с колонками-статусами, карточками,
приоритетами и метками. Рендер общий с `board_view.py` (флаг `live=True` добавляет кнопку).

Разовый статический снимок без сервера (файл `board-view.html`, в `.gitignore`):
```powershell
Save-BoardHtml    # board_view.py -> board-view.html + открыть (без кнопки Обновить)
```

### B. Полноценный TrackState (десктоп) — нужен commit

Нужен, когда хочется именно UI TrackState (иерархия, JQL-фильтры и т.п.) или перед
переходом на Pages. Локальный провайдер TrackState читает **закоммиченный HEAD**,
поэтому здесь коммит обязателен:

```powershell
Sync-Board        # пересобрать board/ + git commit
Open-Board        # trackstate.exe -> Local repository -> папка D:\AO3_tests
Show-BoardCli     # или headless: JQL-поиск через CLI, тоже читает HEAD
```

Проверено: CLI/приложение читают борду (`session --target local` → ok, JQL находит все
тикеты). Требование локального провайдера — репозиторий инициализирован git (сделано).

> **Почему так:** TrackState — git-native, его локальный провайдер берёт содержимое
> через `git show HEAD:<path>`, то есть видит только закоммиченное. Поэтому для «просто
> посмотреть без коммитов» используем HTML-просмотр (A); TrackState (B) — когда нужен
> его UI или публикация на Pages.

## Как смотреть — по URL (GitHub Pages) ✅ установлено 2026-07-03

Репозиторий опубликован: https://github.com/Xartaxana/Darker-than-a-dark-test-factory
(публичный, remote `origin`, ветка `master`). Борда:

**https://xartaxana.github.io/Darker-than-a-dark-test-factory/**

Как устроено (адаптация `IstiN/trackstate-setup`, без форка — workflow лежит у нас):

1. `.github/workflows/install-update-trackstate.yml` собирает Flutter web-приложение
   TrackState (ref запинен на релиз) и деплоит на Pages (Source: GitHub Actions,
   включается самим workflow через `actions/configure-pages`).
2. Отдельный `dataPath` НЕ нужен: приложение сканирует дерево репозитория и берёт
   первый `project.json` — наш лежит в `board/project.json`
   (проверено по исходникам: `lib/data/repositories/trackstate_repository.dart`).
3. Данные читаются **в рантайме** через GitHub API из ветки `master` — после
   `Sync-Board` (commit + push!) борда по URL актуальна без пересборки приложения.
   Workflow перезапускается только для обновления самого TrackState
   (вкладка Actions → «Install / Update TrackState» → Run workflow).
4. Чтение публичного репозитория работает без токена (лимит GitHub API для
   анонимов — 60 запросов/час с IP). Для записи из борды — вход с fine-grained PAT
   `contents:write` (по желанию; штатная запись у нас идёт через артефакты +
   `Sync-Board`, обратный канал — docs/06 §3).

> Внимание: теперь `Sync-Board`/оркестратор после коммита борды должен делать и
> `git push`, иначе опубликованная борда отстаёт от локальной.

## Обратный канал: борда как вход для человека (Фаза 4.5, docs/06 §3)

Для тёмной фабрики борда перестаёт быть только зеркалом: разработчик двигает
карточку (`Fixed`, `Rejected`, `Intended`, `Approved` для TC) или оставляет
комментарий, а фабрика применяет это к артефактам. Принципы:

- Источник правды **остаётся за артефактами**; с борды принимается только узкий
  whitelist человеческих переходов (см. docs/06 §3), всё прочее игнорируется с
  варнингом.
- Реализация ✅ (2026-07-04, ядро — трёхсторонняя сверка через курсор):
  `scripts/board_inbound.py`, вызывается оркестратором на шаге 0 (`pre_steps`);
  комментарии карточек ↔ раздел `## Обсуждение` артефакта.
- Конфликт «человек и агент изменили статус по-разному» → артефакт `Blocked` +
  запись в `state/escalations.md`; конфликт решает человек, а не «последний писавший».
- Просроченные позиции подсвечиваются меткой `attention` — `[план]`: генерация
  board_sync по `state/escalations.md` пока НЕ реализована (сверено
  критик-ревью 2026-07-17; до реализации просрочки видны в escalations.md
  и дайджесте factory-status).

Чтобы разработчик мог двигать карточки не с этой машины — нужна публикация на
GitHub Pages (раздел выше) с PAT `contents:write`.

## Принятое направление доделки (решение владельца 2026-07-14)

Доделка TrackState-форка — очередь [docs/09 п.9–10](09-improvement-plan.md):
первым — фикс кириллицы sync-виджета (п.9), затем правая панель тикета,
сортировки/фильтры, колонки с коммитом, комментарии в обе стороны (п.10).
Approve-кнопка НЕ нужна — покрыта drag + board_inbound. Живой сервер борды —
конфиг `board` в `.claude/launch.json` (порт 8777). Статус — в docs/09, здесь
не ведётся.

## Куда развивать (опционально)

В релизе TrackState есть `trackstate-claude.skill` и CLI-команды
`trackstate ticket create/ticket transition`. Если позже захотим, чтобы агенты писали
статусы **нативно в борду** (без проекции), можно перевести их на эти команды — но это
меняет источник правды (см. решение: сейчас выбрана проекция + узкий обратный канал).
