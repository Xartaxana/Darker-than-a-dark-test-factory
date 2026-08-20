---
id: AT-BUG-089
title: "Ветка подписи «Ch N/M» (readingChapterTotal>1) была недостижима корпусом (до фикса 2026-08-20) — work-страница фикстур не рендерила select#selected_id"
type: test_debt
debt_kind: missing_fixture
severity: minor
status: Fixed
found_in: "exploratory charter CH-011 (2026-08-20), followup_tc[3] — JS-пробой измерено sel:false, opts:0"
fixed_in: "framework (test-only, без сборки приложения) — framework/data/recording_builder.py (_chapter_select_html, render_work_page_html(chapter_titles=...), WORK_MULTI_CHAPTER_FILENAME/WORK_MULTI_CHAPTER_TITLES), scripts/build_replay_recordings.py (build_work_multi_chapter), framework/data/recordings/work_multi_chapter.mitm (новая запись)"
last_seen_in: ""
test_cases: []
runs: [CH-011]
duplicates: []
regression_of: ""
status_since: "2026-08-20T12:01:14Z"
updated: "2026-08-20T12:01:14Z"
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

# AT-BUG-089 — фикстуре work-страницы не хватало `select#selected_id` (минимум 2 option) для ветки «Ch N/M» (до фикса 2026-08-20)

## Окружение
- Долг тестовой системы (`type: test_debt`, `debt_kind: missing_fixture`).
  Затрагивает `bridge-scroll-reporting` (подпись «Ch N/M» под полоской
  прогресса, `BottomBar.kt:76-81`) и любой будущий сценарий, которому нужна
  work-страница с несколькими главами. Адресат: `test-automator`/владелец
  `recording_builder.py::render_work_page_html` (`framework/data/recording_builder.py:734`).

## Суть долга

Подпись «Ch N / M» под полоской прогресса чтения рисуется ТОЛЬКО при
`chTot > 1` (`BottomBar.kt:76-81`). `chTot`/`chCur` читаются бриджем РОВНО из
`document.getElementById('selected_id')` (`ao3_bridge.js:976-978`) — при
отсутствии этого `<select>` бридж молча подставляет `chCur=1, chTot=1`, и
подпись не показывается никогда, независимо от реального числа глав работы.

На момент завода (2026-08-20, до фикса) `framework/data/recording_builder.py::render_work_page_html`
(def `:772`, тело `:772-857` — номера СВЕЖИЕ, после фикса; на момент завода
def был `:734`) НЕ рендерила `<select>` вовсе (сверено по HEAD `app-under-test`,
критик-гейт 2026-08-20). JS-пробой (замер CH-011, DOM живой work-страницы
фикстуры): `sel:false, opts:0` — этот негатив был верен ДО фикса; устранён
test-maintainer тем же ходом (см. «Обсуждение» ниже).

**Уточнение к тексту плана CH-011 (важно для исполнителя — предыдущая
редакция этого тикета сама повторяла ошибку плана, критик-гейт поймал):**
`render_work_page_html:845` (было `:791` на момент завода) вызывает
`_work_meta_group_and_stats_html` (`:691`, было `:679`), который РЕАЛЬНО
рендерит `<dl class="stats">` (`:713`, было `:701`) и
`<dt class="chapters">Chapters:</dt><dd class="chapters">1/1</dd>` (`:715`,
было `:703`) — `dl.stats`/`dd.chapters` СУЩЕСТВУЮТ в `render_work_page_html`,
план и предыдущая редакция этого тикета ошибочно утверждали обратное. Это НЕ
работает для ветки «Ch N/M»: `chTot` читается бриджем НЕ из `dd.chapters`, а
СТРОГО из `#selected_id` — существование `dd.chapters` НЕРЕЛЕВАНТНО этому
долгу, но отрицать его существование неверно. Ещё два вхождения
`dd.chapters`/похожей разметки в кодовой базе фикстур относятся к ДРУГИМ
поверхностям (блёрб листинга `_blurb_html:351`, было `:339`, `dd.chapters` на
`:377`, было `:365`; страница metadata-fetch `render_work_metadata_page_html:944`,
было `:890`, `dd.chapters` на `:986`, было `:932` — `AT-BUG-061`) и к ветке
«Ch N/M» work-страницы отношения не имеют.

*(Все номера строк в этом разделе датированы 2026-08-20 после фикса —
критик-гейт прохода 9 сверил построчно с рабочим деревом; координатор
обновил вслед за диффом.)*

## Критерий готовности (Fixed)

**Код фикстуры (обязательно для перехода Fixed — ВЫПОЛНЕНО 2026-08-20, см.
«Обсуждение»):** `render_work_page_html` рендерит `<select id="selected_id">`
минимум с ДВУМЯ `<option>` (разные номера/заголовки глав, как на реальной
многоглавой work-странице AO3) — эмпирически подтверждено JS-пробоем на
собранной записи: `sel:true, opts>=2`. Достаточно ОДНОЙ работы/варианта
фикстуры с такой разметкой (не обязательно менять ВСЕ существующие
work-страницы) — существующие однo-option/без-select работы НЕ обязаны
исчезнуть, чтобы не задеть уже-зелёные кейсы, читающие текущую разметку.

**TC-покрытие (ОТДЕЛЬНЫЙ follow-up, НЕ блокирует Fixed — правка координатора
прохода 9 по предписанию критик-гейта Б6, 2026-08-20):** хотя бы один
тест-кейс (см. `test_cases`, заполняется тем, кто доведёт до кейса) должен
реально проверить подпись «Ch N/M» на этой фикстуре и пройти зелёным —
это ЗЕЛЁНЫЙ пункт очереди (не критерий Fixed самого test_debt-тикета:
фикстура — инфраструктурная готовность, TC на её основе — отдельная
задача test-designer/test-automator), поставлен в очередь как
`AT-BUG-089-CH-N-M-TC-COVERAGE` (`state/escalations.md`). D1-верификация
(`fix-verifier`, правило rules.yaml "Верифицировать исправленный баг")
проверяет КОД-критерий выше (byte-identical guard + JS-witness +
контрактные/юнит-тесты) — отсутствие TC в `test_cases` НЕ повод для
Reopened, пока follow-up висит в очереди с явным владельцем.

## Анализ

Класс — «недостающая фикстура тестового корпуса» (`missing_fixture`, тот же
смысл, что `AT-BUG-035`/`AT-BUG-006`): наблюдаемое поведение приложения
(подпись «Ch N/M») не является дефектом приложения — код бриджа корректно
читает `#selected_id`, когда он есть; корпус фикстур просто никогда не
рендерил многоглавую work-страницу. Severity — minor: ветка косметическая
(подпись под полоской прогресса), не блокирует ни один уже спроектированный
кейс (`TC-267` явно вынесла эту ветку из своего скоупа и сослалась на этот
тикет), не про data/visibility-риск.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|

## Обсуждение
Канал человек ↔ фабрика.

**[test-maintainer @ 2026-08-20T12:01:14Z] Open → Fixed. Критерий готовности
выполнен эмпирически.**

`render_work_page_html` (`framework/data/recording_builder.py:772-857`)
получил новый опциональный параметр `chapter_titles: tuple[str, ...] | None
= None` (дефолт `None` — вывод байт-в-байт идентичен прежней сигнатуре для
ВСЕХ существующих вызовов, эмпирически сверено `git status --porcelain --
framework/data/recordings/` ПОСЛЕ полной перегенерации ВСЕХ `.mitm`
`scripts/build_replay_recordings.py` — ни одна существующая запись не
изменилась ни байтом). При заданных `chapter_titles` (минимум 2 заголовка,
ИНАЧЕ `ValueError` — граница закрыта критик-гейтом прохода 9, было молчаливым
пропуском изначально) новый хелпер `_chapter_select_html` (комментарий
`:746-756`, тело `:757-770`) рендерит `<li><form
id="chap_index">...<select id="selected_id" name="selected_id">...<option
...>...</select>...</form></li>` — СИБЛИНГ download-`<li>`, ВНУТРИ `<ul
class="work navigation actions">`, ПОСЛЕ него (не меняет regression-
инварианты AT-BUG-035/AT-BUG-074 — kudo/meta/wrapper порядок считается от
`</ul>`, не от содержимого внутри неё; первый `<option>` — `selected`,
соответствует реальному поведению AO3 — открытая work-страница без явного
выбора показывает первую главу).

Новая фикстура `build_work_multi_chapter` (`scripts/build_replay_recordings.py`)
пишет `framework/data/recordings/work_multi_chapter.mitm`
(`rb.WORK_MULTI_CHAPTER_FILENAME`, work = `ALL_WORKS[0]`/`LOVED`, заголовки
`rb.WORK_MULTI_CHAPTER_TITLES = ("Chapter One", "Chapter Two")`) — единственная
запись, несущая ветку; остальные work-страницы намеренно НЕ изменены
(критерий готовности: «существующие однo-option/без-select работы НЕ обязаны
исчезнуть»), подтверждено вышеупомянутой byte-identical сверкой.

**Witness (JS-пробой, bridge-harness/jsdom, `document.getElementById
('selected_id')` — та же функция, что реально читает `ao3_bridge.js:976-978`):**
```
ok: True
results: {'selPresent': True, 'optsCount': 2}
WITNESS: sel:true, opts:2
PROBE_PASS
```

**Witness (device-free unit/contract-регрессия, без device):**
```
Invoke-Pytest tests/test_recording_builder_unit.py -v
  64 passed in 0.40s, PYTEST_EXIT=0

Invoke-Pytest tests/bridge -v
  122 passed in 94.35s (0:01:34), PYTEST_EXIT=0

python -m pytest scripts/tests -q --ignore=scripts/tests/test_anchor_lint.py
  1672 passed, 9 skipped in 66.56s (0:01:06)

python scripts/validate_frontmatter.py
  validate_frontmatter: ошибок 0, предупреждений 0

python scripts/arch_check.py
  arch_check: ошибок 0, предупреждений 7 (7 — предсуществующие allowlisted
  test-debt находки в других файлах, не связаны с этим диффом)
```

`scripts/tests/test_anchor_lint.py` (11 падений) — НЕ регрессия этого диффа:
изолирующий прогон (`git stash push -- framework/data/recording_builder.py
scripts/build_replay_recordings.py`, повтор прогона, `git stash pop`) дал
ИДЕНТИЧНЫЕ 11 падений БЕЗ этого диффа вовсе — `scripts/anchor_lint.py`/
`scripts/tests/test_anchor_lint.py` уже несли большой незакоммиченный WIP-дифф
(150+60 строк) ДО начала этого хода, чужой и вне scope этой задачи (owns —
только `bugs/AT-BUG-089.md`/`recording_builder.py`-и-фикстуры). Не трогал.

**Пункт 6 DoD**: `test_cases: []` оставлен пустым намеренно — ни один кейс
ещё не проверяет ветку «Ch N/M» на новой фикстуре (доводка — отдельная
задача test-designer/test-automator).

`app-under-test/` не тронут за весь ход.

**[test-designer @ 2026-08-20T10:20:00Z] Заведено по followup CH-011 (#3).**
Источник — `exploratory-charters/CH-011.md`, `followup_tc[3]` дословно:
«Запрос ФИКСТУРЫ (адресат test-automator/владелец recording_builder): ветка
подписи «Ch N / M» недостижима корпусом — work-странице нужен select#selected_id
минимум с двумя option. Измерено JS-пробой: sel:false, opts:0.» —
инфраструктурный долг, не продуктовый кейс (по прецеденту CH-010 followup_tc#2
→ AT-BUG-070, Lead-решение 2026-08-15: follow-up, закрывающийся долгом/тест-гэпом,
закрывается BUG-токеном, не новым TC). `test_cases: []` намеренно пуст — на
момент завода не блокирует ни один Approved/Automated кейс (`TC-267` спроектирован
этим же ходом и явно исключил ветку «Ch N/M» из своего скоупа, сославшись
сюда, вместо того чтобы молча упереться в блокер).

`app-under-test/` не затронут — только чтение и заведение тикета.

**[координатор @ 2026-08-20T12:15:00Z] Критик-гейт прохода 9 — ДОРАБОТАТЬ,
6 блокеров, все закрыты дословно.** Б1 (реестр `bridge_selectors.py`:
`#selected_id` получил `pages=("work_multi_chapter.mitm",)`, комментарий
переписан; новая `.mitm` добавлена в `pages` шести соседних записей
`dd.relationship`/`dd.freeform`/`dd.fandom`/`dd.words`/`#chapters`/
`#kudo_submit` — `Invoke-Pytest tests/bridge -v` → 129 passed, PYTEST_EXIT=0,
было 122). Б2 (4 новых юнита в `test_recording_builder_unit.py`: select
присутствует/отсутствует по умолчанию, count `<option>`==len(titles),
sibling-порядок после download-li внутри `<ul>`). Б3 (`ValueError` при
`len(chapter_titles) < 2`, параметризованный тест на границе `len0`/`len1` —
`recording_builder.py` докстринг обновлён) — `Invoke-Pytest
tests/test_recording_builder_unit.py -v` → 69 passed, PYTEST_EXIT=0, было 64.
Б4/Б5 (стале-текст + протухшие якоря) — секции «Суть долга»/title/H1/
«Обсуждение» выше датированы и перепроверены построчно против рабочего
дерева. Б6 (Критерий готовности) — раздел выше разделён на «Код фикстуры»
(выполнено) и «TC-покрытие» (follow-up, не блокирует Fixed) — очередь
`AT-BUG-089-CH-N-M-TC-COVERAGE` заведена в `state/escalations.md`.

Побочная находка координатора при написании Б2-тестов (не блокер, к
сведению test-maintainer/critic): существующий (ДО этого диффа) тест
`test_render_work_page_html_kudo_submit_is_sibling_not_nested` вычисляет
`ul_end` наивным ПЕРВЫМ `body.index("</ul>", ul_start)`, что находит
закрывающий тег ВЛОЖЕННОГО `<ul class="download-list expandable">`, а не
внешнего `<ul class="work navigation actions">` — `ul_block` там усечён
ДО вложенного списка, и негативная проверка `'id="kudo_submit"' not in
ul_block` проходит тривиально независимо от реального места узла. Мои новые
тесты считают ВТОРОЙ `</ul>` явно (см. `test_render_work_page_html_chapter_
select_is_sibling_after_download_inside_ul`). Существующий тест не тронут —
D-0043 сиблинг вне owns-скоупа этого B4-фикса, докладываю, не расширяю.

Дословный вывод после ВСЕХ правок: `python scripts/validate_frontmatter.py`
→ `ошибок 0, предупреждений 0`; `python scripts/arch_check.py` → `ошибок 0,
предупреждений 7` (тот же известный baseline).

## Чек-лист качества (bug-reporter проходит перед публикацией)
- [x] Проверены дубликаты среди открытых багов (`bugs/`, status != Verified/Rejected) — новый долг, дубликатов не найдено (сосед `AT-BUG-061` — другая поверхность, metadata-fetch, разграничено выше)
- [x] Репро-шаги воспроизводят проблему на чистом состоянии (JS-пробой DOM фикстуры, детерминированно)
- [x] Severity обоснована влиянием на пользователя, а не эмоцией (minor — косметическая подпись, ни один кейс не заблокирован)
- [x] Источник: exploratory-charter CH-011.md, followup_tc[3]
- [x] Ни одно изменение не внесено в код приложения
