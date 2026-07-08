---
key: "TC-032"
project: "AO3"
issueType: "test-case"
status: "tc-review"
priority: "p1"
summary: "Авто-скачивание запускается при простановке Loved с включённым Auto-download"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:downloads", "risk:R-05"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-08T17:26:00Z"
updated: "2026-07-08T17:26:00Z"
archived: false
resolution: null
---

# Авто-скачивание запускается при простановке Loved с включённым Auto-download

_Спроецировано из `test-cases/downloads/TC-032.md` (источник правды).
Статус в нашей машине: **Review**._

# TC-032 — Авто-скачивание при рейтинге Loved

## Предусловия
- Приложение запущено с чистыми данными.
- В Settings включена опция "Auto-download saved works".
- Открыта страница работы `/works/{id}` (replay-запись с валидной download-ссылкой в
  `li.download a[href*=".html"]`), работа ещё не имеет рейтинга.

## Сценарий (Given-When-Then)

**Given** "Auto-download saved works" включена в Settings
**And** открыта страница работы без рейтинга, страница содержит валидную
download-ссылку в разметке AO3

**When** пользователь через панель `RatingMenu` ставит рейтинг Loved

**Then** запускается скачивание файла (наблюдаемо: индикатор загрузки или появление
open-иконки на карточке работы в Library без ручного вызова Download)
**And** после завершения работа в Library (вкладка FAVORITE) имеет заполненный
`downloadPath` (проверяется косвенно — иконка "открыть локальный файл" на карточке)
**And** файл открывается через `file://` и содержит стилизованный (не сырой) контент
работы

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Работа | работа из replay-записи с download-ссылкой (`framework/data/recordings/`) |
| Настройка | "Auto-download saved works" = ON |

## Заметки для автоматизации
- Требует replay-режима с записанной страницей работы, содержащей реальную разметку
  `li.download a[href*=".html"]` — live-режим на живом AO3 нестабилен и не подходит
  для регрессии этого сценария.
- Скачивание использует cookies WebView (`CookieManager`) — в replay-режиме
  свериться, что механизм скачивания (`DownloadRepository.downloadFromUrl`) корректно
  резолвит URL через mitmproxy, а не пытается уйти в реальную сеть.
- Не смешивать с ручным скачиванием из Library (см. TC-033) — это отдельный вход,
  инициируемый автоматически при простановке рейтинга.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов

## Заблокировано (test-automator, 2026-07-08)

Возвращён в `Review` — невозможно закодировать имеющимися средствами, тот же класс
блокера, что и TC-009/013/014/015 (см. заметки в тех кейсах).

**Причина:** кейс по дизайну требует replay-запись страницы работы с валидной
разметкой `li.download a[href*=".html"]` — `DownloadRepository.downloadWork`
(`fetchDownloadUrl`) реально ходит по `workUrl` через `OkHttpClient` (не через
WebView), парсит `href="(/downloads/[^"]*\.html[^"]*)"` regex'ом и затем качает
сам файл по найденному URL — то есть нужны ДВЕ записанные HTTP-транзакции
(страница работы + сам `.html`-файл) с валидными cookies, для конкретной
существующей на archiveofourown.org работы с открытым скачиванием. В
`framework/data/recordings/` пока лежит только `ao3_home_smoke.mitm` (запись
главной страницы) — записи страницы работы с download-ссылкой нет.

Спайк B (`docs/environment-setup.md`, закрыт 2026-07-03) доказал, что цикл
record→replay технически работает (CA в mount-namespace, mitmdump-обёртка в
`framework/core/mitm.py`) — но это ТОЛЬКО механизм, сама запись под этот кейс не
сделана, и `framework/core/mitm.py`/`framework/config/settings.PROXY_HOST_ALIAS`
не подключены ни к одной pytest-фикстуре (`conftest.py`) — `replay`-маркер
зарегистрирован в `pytest_configure`, но ни один тест им не помечен и не
запускает `mitm.start_replay`/`set_device_proxy`. Live-режим на реальном AO3
исключён самими заметками кейса (нестабилен для регрессии, плюс скачивание
синтетической `ao3_id=900000001` с реального archiveofourown.org
недетерминировано/не существует).

**Что нужно, чтобы разблокировать:**
1. Записать (реальный визит в live-режиме с mitmdump в режиме записи) флоу
   `GET /works/{id}` + `GET /downloads/.../*.html` для конкретной публичной
   работы с открытым HTML-скачиванием — сохранить как
   `framework/data/recordings/work_with_download.mitm`.
2. Подключить `framework/core/mitm.py` (`start_replay`/`set_device_proxy`) к
   pytest-фикстуре в `conftest.py` (например `replay_work_with_download`),
   аналогично тому, что уже описано как недостающее для TC-009/013/014/015.

Область помечена нуждающейся в доводке replay-инфраструктуры — не APP_BUG,
не TEST_BUG; инфраструктурный блокер, тот же класс, что и в rating/visibility.
