---
id: AT-BUG-061
title: "Нет replay-записи work-страниц archiveofourown.org/works/<id>?view_adult=true для HttpURLConnection-пути «Fetch missing metadata» — блокирует TC-186/TC-187"
type: test_debt
debt_kind: missing_fixture
severity: minor
status: Fixed
found_in: "test-designer, проектирование области `docs/01-test-strategy.md` §9 «settings: контролы, отсутствовавшие в реестре», пункт 1 «Fetch missing metadata» (needs-design, P1), 2026-08-10"
fixed_in: "framework (test-only, без сборки приложения) — framework/data/recording_builder.py, scripts/build_replay_recordings.py, framework/data/recordings/work_metadata_fetch.mitm, framework/tests/test_recording_builder_unit.py"
last_seen_in: ""
test_cases: ["TC-186", "TC-187"]
runs: []
duplicates: []
regression_of: ""
status_since: "2026-08-10T16:40:00Z"
updated: "2026-08-10T16:40:00Z"
reopen_count: 0
dispute_count: 0
awaiting: none
resolution: ""
resolution_comment: ""
known_issue: "false"
blocked_reason: ""
lock: ""
gitlab_issue: ""
---

# AT-BUG-061 — Работа «Fetch missing metadata» не имеет replay-записи для своего HTTP-пути (не WebView)

## Окружение

Не зависит от сборки приложения: долг тестовой системы (`type: test_debt`,
`debt_kind: missing_fixture`). Текущая тестируемая сборка `6f884d97`
(versionCode 12).

## Суть долга

`SettingsViewModel.fetchMissingMetadata`
(`app-under-test/app/src/main/java/com/example/ao3_wrapper/ui/settings/SettingsScreen.kt:231-255`)
идёт по РАБОТАМ с пустым `title` (`repo.getWorksNeedingMetadata()` →
`RatingRepository.kt:62` `getWorksWithEmptyTitle`) и для каждой открывает
`https://archiveofourown.org/works/<ao3Id>?view_adult=true` через
**`HttpURLConnection`** (`:259-264`, `fetchAo3WorkPage`, до 3 попыток, темп
1500 мс между работами) — тот же класс пути, что download-flow
(`DownloadRepository.downloadWork`, `OkHttpClient`, НЕ WebView), а не
навигация в WebView.

`framework/data/recording_builder.py`/`framework/data/recordings/` НЕ несёт
ни одного flow под URL-шаблон `works/<id>?view_adult=true` (сверено по
списку `recordings/*.mitm`: `ao3_home_smoke`, `sort_filter_form`,
`listing_basic`, `listing_duplicate_work`, `tab_markers`,
`work_with_download`, `listing_paginated`, `works_multi` — ни один не
несёт `view_adult=true` в query, и все синтетические `ao3_id`
(`framework/data/works.py::ALL`) физически не существуют на живом AO3, live
позитивные пробы этого пути ЗАПРЕЩЕНЫ (`docs/01-test-strategy.md` §9,
довод — тот же, что для авто-kudos: запросы к стороннему сайту от имени
пользователя).

Механизм replay СПОСОБЕН перехватывать этот класс трафика (прецедент —
`work_with_download.mitm` уже несёт non-WebView `OkHttpClient`-транзакции
той же природы, `recording_builder.py:68-76`; device-wide proxy
`adb shell settings put global http_proxy` — `framework/core/mitm.py:506-524`
— покрывает ЛЮБОЙ сетевой стек приложения, не только WebView, включая
голый `HttpURLConnection`), но конкретной записи под этот URL-шаблон и с
HTML-телом, несущим непустой `<title>`/автора/фандом/word_count в разметке,
которую парсит `fetchAo3WorkPage`, — нет.

Заблокированы:
- **TC-186** (позитивный путь: очередь = только строки с пустым `title`,
  прогресс `N/total`, `Done(updated)` пишет в Room только строки с
  непустым скрейпнутым `title`) — нужна запись с непустым результатом
  минимум для одной работы.
- **TC-187** (Stop мид-fetch → `Stopped(updated)` с частичным счётчиком) —
  тот же класс записи, плюс минимум ВТОРАЯ работа в очереди, чтобы Stop
  застал процесс НЕ на последней позиции.

## Критерий готовности (Fixed)

- [x] `recording_builder.py` строит flow под URL
  `https://archiveofourown.org/works/<id>?view_adult=true`
  (`work_metadata_fetch_url`/`render_work_metadata_page_html`,
  `METADATA_FETCH_WORK_A`, ao3_id `900000186`) с HTML-телом, несущим РЕАЛЬНУЮ
  разметку под `parseAo3WorkHtml` (SettingsScreen.kt:287-318) —
  `h2.title.heading` / `a[rel=author]` / `dd.fandom.tags a.tag` (ПОЛНЫЙ
  tags-список `dl.work.meta.group`, не только preface `h5.fandom.tags` —
  именно его ищет regex приложения, см. докстринг
  `render_work_metadata_page_html`) / `dd.words` (`dl.stats`) — непустой
  title/author/fandom/word_count после скрейпа.
- [x] Второй flow — `METADATA_FETCH_WORK_SECOND` (ao3_id `900000187`), нужен
  TC-187 (Stop мид-fetch: вторая работа очереди). Третий flow — HTTP 404 на
  `METADATA_FETCH_WORK_B_AO3_ID` (`900000188`) — TC-186 Given «скрейп НЕ даёт
  результата» (`fetchAo3WorkPage` возвращает `null` немедленно на 404, без
  ретраев). Все три — в одном `work_metadata_fetch.mitm`
  (`build_work_metadata_fetch`).
- [x] Проверено ФАКТОМ (не предположением по коду): `HttpURLConnection`-
  трафик `fetchAo3WorkPage` реально перехватывается device-wide прокси в
  replay-режиме — см. «Обсуждение» ниже, запись test-maintainer 2026-08-10.
- [ ] **Полная автоматизация TC-186/TC-187 (page-object локаторы, шаги,
  Then-проверки обоих кейсов) — ОТДЕЛЬНАЯ работа test-automator, сознательно
  ВЫНЕСЕНА за рамки этого прохода** (разделение диспетчером задачи: этот
  test_debt устраняется фактом существования РАБОТАЮЩЕЙ записи, не
  готовностью конкретных TC — тот же паттерн, что уже применялся в
  `AT-BUG-029` §Критерий готовности, где `status: Fixed` этого класса тикета
  не требовал зелёного TC, если причина — вне периметра самой фикстуры;
  здесь причина другая — деление труда по ролям, не блокирующий app_bug, но
  вывод тот же: `automated_by` TC-186/TC-187 остаётся пустым до отдельного
  прохода test-automator, эта строка не переоткрывает тикет).
- [x] Smoke без регресса: `python -m pytest scripts/tests -q` — 1066 passed,
  1 skipped; device-free юниты `framework/tests/test_recording_builder_unit.py`
  (включая 7 новых юнитов AT-BUG-061) — 59 passed, 0 failed; `-k _unit` по
  всему `framework/tests` — 187 passed, 0 failed, без регресса.

## Анализ

Тот же класс, что AT-BUG-004/AT-BUG-006/AT-BUG-029/AT-BUG-030 («механизм
replay существует, конкретной записи под новый URL-шаблон нет») — НЕ
дубликат ни одного из них: другой URL-шаблон (`works/<id>?view_adult=true`,
не листинг/форма/work-страница для тап-зон), другой сетевой стек
(`HttpURLConnection`, не `OkHttpClient`/WebView-навигация, хотя оба «не
WebView»-класса). Обнаружен при проектировании TC-186/TC-187, тем же ходом
(правило 4 воркфлоу test-designer). Оба кейса оставлены `status: Review`
(дизайн полон, не спорное требование) — заблокирована ТОЛЬКО автоматизация,
тот же прецедент, что AT-BUG-029/AT-BUG-030.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|

## Обсуждение

**2026-08-10T15:45:00Z — test-designer (заведение, правило 4 воркфлоу):**
блокер найден при проектировании области «settings: контролы,
отсутствовавшие в реестре», пункт 1 (`settings-fetch-missing-metadata`, P1,
R-01). Проверены существующие test_debt-баги на пересечение
(AT-BUG-004/006/029/030 — все про ДРУГИЕ URL-шаблоны/фикстуры) — дубликата
нет, заведён новый. Один тикет на оба кейса (`test_cases: ["TC-186",
"TC-187"]`) — оба упираются в одну и ту же отсутствующую запись, не по
багу на кейс.

Заведён изначально как `AT-BUG-060`, самим же ходом переномерован в
`AT-BUG-061`: слот 060 к моменту выбора номера уже был занят параллельным
`bugs/BUG-060.md` (сквозной счётчик по обоим префиксам) — см.
`bugs/AT-BUG-060.md` (артефакт-дубль, помечен для ручного `Rejected`).

**2026-08-10T16:40:00Z — test-maintainer (B4, фикс):** реализована запись
`framework/data/recordings/work_metadata_fetch.mitm` (`build_work_metadata_fetch`
в `scripts/build_replay_recordings.py`, новые `work_metadata_fetch_url`/
`render_work_metadata_page_html`/`METADATA_FETCH_WORK_A`/
`METADATA_FETCH_WORK_SECOND`/`METADATA_FETCH_WORK_B_AO3_ID` в
`recording_builder.py`) — три flow: работа A (успешный скрейп, ao3_id
`900000186`), работа SECOND (успешный скрейп, ao3_id `900000187`, для
TC-187 "работа E"), работа B (`900000188`, HTTP 404 — `fetchAo3WorkPage`
трактует 404 как «не найдено» и возвращает `null` НЕМЕДЛЕННО, без
ретраев/`delay()`, в отличие от прочих кодов — удобно и быстро для
детерминированного «скрейп не дал результата» без реального таймаута).

Разметка work-страниц — ОТДЕЛЬНЫЙ рендер `render_work_metadata_page_html`, не
переиспользование `render_work_page_html`: `parseAo3WorkHtml`
(SettingsScreen.kt:287-318) парсит РЕГЕКСАМИ, ищущими `<dd class="fandom
tags">` (полный tags-список `dl.work.meta.group` реального AO3) и `<dd
class="words">` (`dl.stats`) — ни то, ни другое не несёт
`render_work_page_html` (та строит download-flow страницу с preface-only
`h5.fandom.tags`, без `dl.stats` вовсе). Смешение сломало бы и позиционные
инварианты существующих юнитов AT-BUG-030/035, и саму разметку под парсер
этого пути. Guard дрейфа — `framework/tests/test_recording_builder_unit.py`
(7 новых юнитов, приём AT-BUG-054: РЕГЕКСЫ `parseAo3WorkHtml`, буквально те
же строки, что читает Kotlin-код, прогнаны на записанном HTML — не пересказ
парсера; плюс байт-в-байт сверка с генератором; плюс негатив F-34,
доказывающий, что regex `dd.fandom.tags` НЕ ловит preface-only `h5`-разметку
— значит позитив выше бьёт именно по `dd`, не по случайному совпадению).

**Эмпирическая сверка (DoD, по образцу `work_with_download.mitm`
AT-BUG-004):** временный device-probe (`framework/tests/`, не закоммичен,
удалён после снятия свидетельства — не входит в owns этого прохода как
постоянный файл) прогнан на `emulator-5554` через `replay`-фикстуру,
параметризованную `work_metadata_fetch.mitm`: строка Room засеяна с ЭТИМ ЖЕ
`ao3_id`, что `METADATA_FETCH_WORK_A`, но `title=""` (сразу попадает в
`getWorksNeedingMetadata`); UI Settings → «Fetch missing metadata» → «Fetch»
→ дождались подписи «Updated…»; Room прочитана `read_work_ratings_full()`.
**Факт (не предположение):** `title`/`author`/`fandom`/`word_count` строки
ПОСЛЕ fetch побайтово совпали со скрейпнутым значением `METADATA_FETCH_WORK_A`
(`"TC-186 Scraped Work Title"`/`"scraped_author_186"`/`"Scraped Fandom
One"`/`4321`) — `HttpURLConnection` (`fetchAo3WorkPage`, вызван БЕЗ WebView,
БЕЗ `OkHttpClient`) реально получил ЗАПИСАННЫЙ ответ через device-wide
прокси в replay-режиме, не ушёл в live-forward. Прогон повторён 3 раза
подряд — 3/3 зелёных (`PYTEST_EXIT=0`, `1 passed` каждый раз, ~40с на
прогон). Находка «HttpURLConnection ходит мимо прокси» — НЕ подтвердилась;
обходной путь (WireMock-порт/live-only) не понадобился.

**Разделение работы, важно для awaiting/следующего прохода:** этот проход
устраняет test_debt тем, что запись СУЩЕСТВУЕТ и РЕАЛЬНО РАБОТАЕТ (доказано
выше) — полная сборка автотестов TC-186/TC-187 (page-object локаторы в
`settings_screen.py`/шаги в `settings_steps.py`/оба Then каждого кейса) НЕ
сделана этим проходом (явный вынос из DoD делегирующего диспетчера,
«полноценные автотесты TC-186/187 — работа test-automator»). `automated_by`
обоих TC остаётся пустым; `test-cases/settings/TC-186.md`/`TC-187.md` не
тронуты (вне owns этого прохода) — их «Заметки для автоматизации» ещё
указывают на блокер как на актуальный; следующий проход test-automator
обновит эти заметки заодно со своей автоматизацией. Никакого нового
блокера не найдено — заводить дополнительный test_debt-баг не по чему.

## Чек-лист качества
- [x] Проверены дубликаты среди открытых test_debt-багов — не совпадает с
      AT-BUG-004 (листинг), AT-BUG-006 (форма Sort&Filter), AT-BUG-029
      (HTTP-транзакция листинга), AT-BUG-030 (DOM-узлы work-страницы для
      тап-зон) — другой URL-шаблон и другой сетевой путь; также сверено с
      `bugs/BUG-*.md` на предмет номера (класс собственной ошибки этой же
      сессии, см. Обсуждение)
- [x] Суть долга ясна и воспроизводима по коду
      (`SettingsScreen.kt:231-264`, `RatingRepository.kt:62`)
- [x] Severity: minor — блокирует автоматизацию двух P1-кейсов одной
      записи реестра, дизайн обоих полон
- [x] Ни одно изменение не внесено в `app-under-test/`
- [x] `test_cases: ["TC-186", "TC-187"]` — оба кейса, заблокированных ОДНОЙ
      и той же отсутствующей записью, не по багу на кейс
