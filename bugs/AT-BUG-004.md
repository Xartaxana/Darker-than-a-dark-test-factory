---
id: AT-BUG-004
title: "Replay-инфраструктура не доведена: нет записей work/листинг-страниц и mitm-фикстуры в conftest — блокирует автоматизацию 10 P0/P1 кейсов"
type: test_debt
debt_kind: missing_fixture
severity: major
status: Fixed
found_in: "батч автоматизации downloads TC-032..036, 2026-07-08 (test-automator); класс известен с 2026-07-03 (TC-009/013/014/015)"
fixed_in: "commit ca6301b (framework/data/recording_builder.py, framework/data/recordings/work_with_download.mitm, framework/data/recordings/listing_duplicate_work.mitm, framework/tests/test_replay_infra_probe.py, framework/steps/browser_steps.py, framework/steps/rating_steps.py, framework/web/listing_page.py, framework/web/selectors.py, framework/web/work_page.py, scripts/build_replay_recordings.py, .gitattributes)"
last_seen_in: ""
test_cases: ["TC-009", "TC-013", "TC-014", "TC-015", "TC-032", "TC-033", "TC-012", "TC-043", "TC-044", "TC-045"]
runs: []
duplicates: []
regression_of: ""
status_since: "2026-07-09T13:30:00Z"
updated: "2026-07-09T13:30:00Z"
reopen_count: 0
dispute_count: 0
awaiting: none
lock: ""
---

# AT-BUG-004 — Replay-инфраструктура (mitm) не подключена к тестам

## Окружение
- Не зависит от сборки приложения: долг тестовой системы (`type: test_debt`,
  `debt_kind: missing_fixture`). Класс блокера повторно вскрыт при
  автоматизации батча downloads (TC-032/033); впервые зафиксирован при
  возврате TC-009/013/014/015 в Review (2026-07-02/03) — очередь на него
  до сих пор не была заведена, только заметки в телах кейсов.

## Суть долга

Спайк B (docs/environment-setup.md, закрыт 2026-07-03) доказал работоспособность
цикла record→replay (CA в mount-namespace, mitmdump-обёртка в
`framework/core/mitm.py`), но механизм не доведён до пригодности в тестах:

1. `framework/core/mitm.py` (`start_replay`/`set_device_proxy`) и
   `framework/config/settings.PROXY_HOST_ALIAS` не подключены ни к одной
   pytest-фикстуре в `framework/tests/conftest.py`; маркер `replay`
   зарегистрирован, но ни один тест им не пользуется.
2. В `framework/data/recordings/` есть только `ao3_home_smoke.mitm`; нет
   записей: страницы работы `GET /works/{id}` с валидной download-ссылкой +
   самого `GET /downloads/.../*.html` (нужно TC-032/033), листингов для
   rating/visibility-кейсов (TC-009/013/014/015 — детали в телах кейсов).

Заблокированные кейсы: TC-013/014/015 (P0, visibility), TC-009 (P0, rating),
TC-032/033 (P1, downloads) — все возвращены в Review с одинаковым классом
блокера.

## Критерий готовности (Fixed)

- В `conftest.py` есть replay-фикстура (proxy на устройство + mitmdump replay
  + teardown), используемая хотя бы одним зелёным тестом.
- Записаны и лежат в `framework/data/recordings/`: work-страница с открытым
  HTML-скачиванием (+ сам .html) и записи, требуемые кейсами
  TC-009/013/014/015 (по их заметкам).
- Хотя бы один из заблокированных кейсов доведён до зелёного прогона на
  replay (доказательство пригодности), остальные разблокированы для
  test-automator (вернуть их из Review в Approved — решение test-designer/Lead).
- Smoke без регресса.

## Анализ

Долг «механизм есть, продукта нет»: record→replay доказан спайком, но не
превращён в фикстуру и библиотеку записей. Чинит фабрика по правилу
«Устранить test debt» (B4) — объём заметный (запись live-сессий + проводка
фикстуры), возможно, стоит разбить на шаги при диспатче. Fixed не ждёт
сборку приложения.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|

## Обсуждение

**2026-07-08T15:30:00Z — оркестратор /qa-loop (по отчёту test-automator):**
класс повторился на втором батче (downloads) — заведена явная очередь вместо
заметок по кейсам. Диспатч по B4 — следующими проходами; при диспатче учесть
рекомендацию исполнителя: сначала запись work-flow + фикстура, затем
разблокировка кейсов по областям.

**2026-07-08T19:00:00Z — test-automator (батч rating P1: TC-012/043/044/045):**
класс повторился третий раз — все 4 кейса батча упёрлись в один и тот же
механизм (`li[id^="work_"].work.blurb` на листинговой странице, инжектируемый
`ao3_bridge.js`: `applyRatings`/`applyAllFilters`/note-кнопка), а не в четыре
разных проблемы:
- TC-012 (applyRatings синхронизирует бейдж по двум вхождениям работы на
  странице) — нужна фикстура листинга с ДВУМЯ `<li id="work_{id}">` одного и
  того же `ao3_id` (доп. требование сверх «просто листинг с несколькими
  разными работами», нужного для TC-009/013/014/015).
- TC-043 (comment-only не скрыт фильтрацией на листинге) — нужна та же
  фикстура листинга, что и TC-013/014/015, с блёрбом comment-only работы;
  вторая половина сценария (не в рейтинговых вкладках Library) уже покрыта
  TC-017/`test_library.py` без листинга.
- TC-044 (Note-кнопка на листинге открывает overlay) — Note-кнопка существует
  только внутри блёрба листинга; тот же блокер.
- TC-045 (личные теги не влияют на видимость) — механически идентичен
  TC-013/014/015 (`applyAllFilters` не читает `tags` вовсе), нужна та же
  фикстура + Disliked-работа с непустыми тегами.

Оценка объёма для разблокировки батча: 1 базовая листинговая HTML-фикстура
(несколько разных синтетических работ, минимум одна Disliked, одна
comment-only) закрывает TC-013/014/015/043/045 разом; TC-044 нужен только
непустой `comment` у одной из работ фикстуры (уже есть в том же наборе, если
comment-only работа получит непустой comment — что и так требуется); TC-012
нужна ОТДЕЛЬНАЯ вариация фикстуры с дублированным `ao3_id` — не покрывается
базовой листинговой записью, стоит отдельного шага при диспатче B4.

**2026-07-08T23:55:00Z — test-maintainer (B4, инкремент 1):** первый связный шаг
сделан, `status` намеренно оставлен `Open` — полный критерий готовности шире
(остаток decomposable ниже, см. `agent_output` диспатча).

Сделано:
1. `framework/tests/conftest.py::replay` — рабочая replay-фикстура: proxy на
   устройство (`mitm.set_device_proxy`), `mitmdump --server-replay` на записи
   `request.param` (indirect-параметризация), гарантированный teardown
   (`mitm.stop` + `mitm.clear_device_proxy` в `finally`). Использует маркер
   `replay` (уже был зарегистрирован, впервые подключён к реальному тесту).
   `framework/core/mitm.py` дополнен ожиданием реального прослушивания порта
   (`start_replay` раньше возвращался сразу после `Popen`, до факта bind) и
   ожиданием завершения процесса в `stop()` (иначе следующий прогон мог
   застать порт ещё занятым уходящим mitmdump).
2. `framework/data/recording_builder.py` (новый) + генератор
   `scripts/build_replay_recordings.py` — конструируют `.mitm`-записи
   программно (`mitmproxy.io.FlowWriter`), т.к. живая запись невозможна
   (синтетические `ao3_id` не существуют на archiveofourown.org — см. «Причина»
   в TC-013.md). HTML 1:1 повторяет проверенную разметку AO3
   (`framework/web/selectors.py`, `PROJECT.md` §Fragility note), без внешних
   `<script src>`/`<link>` — самодостаточна, не зависит от сети на ассетах.
   Записана `framework/data/recordings/listing_basic.mitm`: один листинг с
   блёрбами ВСЕХ 5 эталонных работ (`framework/data/works.py::ALL`, включая
   `DISLIKED` и `KUDOSED`) — по анализу выше закрывает TC-013/014/015/043/045
   (личные теги/comment для конкретного сценария подставляются сидингом,
   `seed_with_comment` уже поддерживает и то, и другое — доп. правок
   `seed_db.py` не потребовалось).
3. `framework/steps/browser_steps.py` — шаги `open_listing`/`assert_blurb_hidden`/
   `assert_blurb_visible` (обёртки над уже существовавшим
   `framework/web/listing_page.py::ListingPage`, который test-designer подготовил
   заранее, до этого инкремента не использовался).
4. `framework/tests/test_visibility.py` (новый) — TC-013 автоматизирован на
   replay: `test_disliked_hidden_on_listing`, зелёный 3 раза подряд (2× 100%
   изолированно ~21s + 1× внутри полного p0-набора). Кейс TC-013.md НЕ
   переведён из `Review` — по матрице переходов (`schemas/transitions.yaml`)
   `Review → Approved` только `by: [human]`/`qa-loop` (P2/P3), решение не за
   test-maintainer.
5. Окружение доведено до состояния, пригодного для replay: эмулятор
   перезапущен с `-writable-system`, `bash scripts/install-mitm-ca.sh`
   прогнан заново (mount не переживает reboot — CA не был установлен на
   момент старта диспатча, `mount | grep cacerts` было пусто).
   `docs/environment-setup.md` дополнен коротким разделом с описанием
   доведённого механизма (ссылка на этот баг).

Разблокировано для test-automator (фикстура пригодна, решение о переводе
Review→Approved — test-designer/Lead): **TC-013, TC-014, TC-015, TC-043,
TC-045** — все используют одну и ту же `listing_basic.mitm`; TC-044 получает
Note-кнопку автоматически, если у соответствующей работы фикстуры непустой
`comment` (уже поддержано сидингом).

Остаток — НЕ входит в этот инкремент, decomposable для следующего прохода B4:
- TC-012 — отдельная вариация фикстуры с ДВУМЯ `<li id="work_{id}">` одного и
  того же `ao3_id` (не покрывается `listing_basic.mitm`).
- TC-032/TC-033 — запись download-flow: `GET /works/{id}` с валидной
  download-ссылкой + сам `GET /downloads/.../*.html`; тот же
  `recording_builder.py` переиспользуется (написан с расчётом на будущие
  записи, не только на листинг), но сама разметка work-страницы с
  `li.download a[href*=".html"]` ещё не собрана.
- TC-009 — тот же replay-блокер по духу, но сценарий (простановка рейтинга из
  листинга через bottom-sheet) не тестировался этим инкрементом; фикстуры
  должно хватать, но зелёного прогона нет — не заявляю сделанным.

**2026-07-08T21:45:00Z — critic (приёмка инкремента 1, правило 3а):** вердикт
**REJECT / ДОРАБОТАТЬ** — attempt 1 отклонён. По сути инкремент решает задачу
(механизм подключён, запись валидна и точна по контракту с сайтом, класс
разложен корректно, границы не нарушены), но есть блокер приёмки:

- **БЛОКЕР — `framework/tests/conftest.py` (fixture `replay`): teardown НЕ
  гарантирован на пути отказа setup'а.** `set_device_proxy()` и `start_replay()`
  вызываются ВНЕ `try`; если `start_replay` бросит `TimeoutError` (порт не
  забиндился за `_READY_TIMEOUT`), `finally` не выполнится — на устройстве
  останется глобальный `http_proxy` на мёртвый mitmdump (КАЖДЫЙ последующий тест
  сессии роутится в дохлый прокси и падает) + орфан `_proc` (каскад
  `WinError 10048` по порту). Прямо противоречит DoD-1 «корректный teardown» и
  имеет межтестовый радиус поражения. Фикс: обернуть `set_device_proxy()` +
  `start_replay()` в тот же `try`, что и `yield`.
- Некритично (на будущее, не блокеры, но желательно в attempt 2, т.к. дёшево и
  усиливает доказательство пригодности): (2) `browser_steps.open_listing` ждёт
  СТАТИЧНОЕ присутствие блёрба (истинно сразу после парсинга DOM), а не факт
  скрытия после нативного round-trip (`applyRatings→applyAllFilters`); `assert_
  blurb_hidden` — одноразовое чтение без `wait_until` → гонка, 3 зелёных прогона
  прошли на латентности переключения в WEBVIEW, а не на синхронизации. Опрашивать
  пост-условие (`display:none` у DISLIKED-блёрба). (3) `recording_builder.py`
  использует `uuid.uuid4()` для conn-id → `.mitm` недетерминирован (перегенерация
  пачкает diff, артефакт не сверить с генератором); докстринг зря зовёт его
  «идемпотентным». Зафиксировать id.
- Witness воркера (p0 18 passed, TC-013 ×2 зелёный) critic'ом НЕ воспроизведён
  независимо: остаётся самодекларацией воркера; сверить при поднятом эмуляторе в
  attempt 2 (fix + re-run даст свежий witness).

**2026-07-08T22:00:00Z — Lead (поправка к записи critic'а):** причина
непроверки witness'а, названная critic'ом («`adb devices` пуст → эмулятор не
поднят»), НЕВЕРНА. Оператор указал на работающее окно эмулятора; сверка
`. scripts/env.ps1; adb devices` → `emulator-5554 device` — эмулятор был поднят
(worker перезапустил его с `-writable-system`, на экране отрендерена
`listing_basic.mitm`). У critic'а `adb devices` вернул пусто потому, что `adb`
не в PATH без загруженного `env.ps1` (tooling-промах, не состояние среды).
Вердикт REJECT в силе — блокер teardown найден чтением кода и от эмулятора не
зависит; но воспроизведение green-прогона критику было ДОСТУПНО. Класс (правило
9): env-зависимые инструменты (`adb`/`emulator`) надо звать через канонические
формы с загрузкой `env.ps1`/`tasks.ps1` (permission-hygiene CLAUDE.md) — иначе
`command not found`/пустой вывод принимается за отсутствие объекта. Для attempt
2 эмулятор доступен; CA-переустановку делать только если `mount | grep cacerts`
пуст, не вслепую.

Классовая полнота (правило 9) и границы (app-under-test/ не тронут, TC-013
остался Review, статус бага Open, переходов не тем актором нет) — подтверждены
critic'ом. Новая ось SIBLING_MAP не требуется.

**Attempt 2 (следующий проход B4):** тот же ярус (test-maintainer/sonnet) —
одно отклонение, эскалация не требуется (правило 6). Спека фикса: (а) блокер
teardown обязателен; (б) гонка `open_listing` и (в) детерминизм `.mitm` —
рекомендованы; новый witness = зелёный TC-013 на replay + smoke без регресса на
поднятом эмуляторе.

**2026-07-09T11:40:00Z — test-maintainer (B4, инкремент 2, фикс блокера
приёмки attempt 1):** `status` намеренно оставлен `Open` — перевод Open→Fixed
и оценка полноты критерия остаются приёмкой Lead+critic по правилу 3а (тот же
паттерн, что и в инкременте 1).

Сделано (все три пункта из спеки attempt 2, включая оба рекомендованных):
1. **Блокер teardown (обязательный).** `framework/tests/conftest.py::replay` —
   `mitm.set_device_proxy()` и `mitm.start_replay()` перенесены ВНУТРЬ `try`,
   вместе с `yield`; `finally` (тот же `mitm.stop()` + `mitm.clear_device_proxy()`)
   теперь гарантированно выполняется при отказе на ЛЮБОМ шаге setup'а —
   `clear_device_proxy()` идемпотентен (`check=False`, безусловно ставит `:0`),
   поэтому безопасен даже если `set_device_proxy()` сам не выполнился. Устраняет
   каскад «мёртвый прокси на все последующие тесты сессии», найденный critic'ом.
2. **Гонка `open_listing`/`assert_blurb_*` (рекомендация 1).**
   `framework/steps/browser_steps.py::assert_blurb_hidden`/`assert_blurb_visible` —
   заменено одноразовое чтение `ListingPage.is_hidden` на опрос через `wait_until`
   (тот же примитив, что уже использовался в `open_listing`): пост-условие
   (`display:none` после `applyRatings→applyAllFilters`) теперь дожидается
   реальной синхронизации, а не латентности переключения контекста в WEBVIEW.
3. **Детерминизм `.mitm` (рекомендация 2).** `framework/data/recording_builder.py` —
   при разборе обнаружилось, что `uuid.uuid4()` для conn-id был не единственным
   источником недетерминизма: `Flow.__init__`/`Request.make`/`Response.make`
   митмпрокси сами берут `uuid.uuid4()`/`time.time()` для `flow.id` и
   `timestamp_created/timestamp_start/timestamp_end` — те же поля, что не влияют
   на матчинг `server-replay` (см. докстринг модуля), поэтому зафиксированы на
   детерминированные значения (md5-хэш от роли+URL для id, `0` для таймстемпов).
   Проверено эмпирически: два подряд запуска `python scripts/build_replay_recordings.py`
   теперь дают байт-в-байт идентичный `listing_basic.mitm` (`fc /b` — 0 расхождений);
   докстринг генератора «идемпотентен» — теперь верен буквально, не только по
   намерению.

Witness (свежий прогон на поднятом эмуляторе `emulator-5554`, CA-mount уже был
на месте — `mount | grep cacerts` непуст, переустановка не потребовалась):
- `Invoke-Pytest tests/test_visibility.py -v` — `test_disliked_hidden_on_listing[listing_basic.mitm]`
  зелёный ДВАЖДЫ подряд отдельными прогонами (23.27s, затем 23.68s).
- `Invoke-Pytest -m p0 -v` — полный p0-набор (18 тестов) без регресса,
  `18 passed, 9 deselected in 552.43s`.

Классовая полнота (правило 9): фикс детерминизма расширен на ВСЕ источники
недетерминизма одного класса («библиотека сама генерирует id/timestamp» —
проверено по факту, не только по conn-id из рекомендации critic'а), а не
только на явно указанный `uuid.uuid4()` в `_client_conn`/`_server_conn`.

Границы не нарушены: `app-under-test/` не тронут; TC-013/014/015/043/045 не
переведены из `Review` (решение test-designer/Lead); TC-012/032/033/009
(decomposable-остаток) не тронуты, их судьба — отдельный проход B4.

Разблокировано для test-automator (без изменений к инкременту 1, разблокировка
подтверждена свежим witness'ом): TC-013, TC-014, TC-015, TC-043, TC-045.

**2026-07-09T10:44:00Z — critic (приёмка инкремента 2, правило 3а):** вердикт
**ACCEPT**. Проверено трассировкой и независимым воспроизведением (не на слово):
(1) teardown-блокер закрыт по ВСЕМ путям отказа setup'а (`set_device_proxy`
бросает / `start_replay` бросает `TimeoutError` с уже присвоенным `_proc` /
`Popen` сам бросает — во всех трёх `finally` корректно останавливает
mitmdump и снимает прокси); немаркирующая заметка на будущее — если сам
`stop()` бросит (`_proc.kill()+wait(timeout=5)` не уложится), порядок
`stop()`→`clear_device_proxy()` в `finally` оставит прокси; не блокер, но
надёжнее снять прокси первым. (2) Гонка `open_listing` устранена —
`wait_until`-поллинг реально ждёт пост-условие `display:none`, тест
избирателен (DISLIKED скрыт И LOVED виден в одном прогоне — «спрятать всё»
не прошёл бы). (3) Детерминизм `.mitm` воспроизведён critic'ом лично: два
запуска `build_replay_recordings.py` дали byte-identical файлы. (4) Witness
TC-013 воспроизведён critic'ом независимо на поднятом эмуляторе (`Get-Device`
канонической формой) — 23.83s, зелёный; полный p0-набор critic не
перепрогонял (остаётся самодекларацией воркера по этому пункту). (5)
Классовая полнота (правило 9) подтверждена: пройдены все фикстуры
`conftest.py`, sibling'ов паттерна «ресурс захвачен вне try, второй может
упасть» кроме `replay` нет.

**Fixed НЕ ставить** (сверка «## Критерий готовности» ПОЛНОСТЬЮ): буллет
«work-страница с download-ссылкой + сам .html (TC-032/033)» явно назван
критерием готовности и НЕ выполнен этим инкрементом — это не входит в
льготу «остальные разблокированные кейсы»; статус `Open` — верное решение
test-maintainer'а, подтверждено. Остаток для следующего прохода B4:
download-flow запись (TC-032/033), вариация фикстуры с дублированным
`ao3_id` (TC-012), зелёный прогон rating-сценария (TC-009).

**2026-07-09T13:30:00Z — test-maintainer (B4, инкремент 3, финальный
остаток):** все три пункта из остатка инкремента 2 сделаны; `status: Open →
Fixed` (guard-переход test-maintainer, `schemas/transitions.yaml`,
`{from: Open, to: Fixed, by: [test-maintainer, test-automator], guard:
{type: test_debt}}`) — сверка «## Критерий готовности» построчно ниже.

Сделано (commit `ca6301b`):
1. **Download-flow запись (TC-032/033).** `framework/data/recording_builder.py`
   дополнен `render_work_page_html`/`render_downloaded_work_html`/
   `download_href`/`download_url`/`_download_list_html` — work-страница
   (`#workskin`, `h2.title.heading`, `h3.byline.heading a[rel=author]`, сверено
   с `PROJECT.md` §Fragility note) с валидной `li.download a[href*=".html"]`
   (вложенный `ul.download-list`, PDF/HTML/MOBI/EPUB — реальная разметка AO3;
   сверено с `PROJECT.md` §Download flow и `DownloadRepository.kt`
   (`fetchDownloadUrl`: `OkHttpClient`, НЕ WebView, regex
   `href="(/downloads/[^"]*\.html[^"]*)"`, ОБЕ транзакции — GET work-страницы и
   GET самого `.html` — идут через один и тот же `replay`-прокси, поэтому
   записаны в ОДИН `.mitm`)). `scripts/build_replay_recordings.py::
   build_work_with_download()` — работа `W.LOVED` (произвольный выбор,
   сценарий не завязан на конкретную работу). Записан
   `framework/data/recordings/work_with_download.mitm` (2 flow: work-страница
   + `.html`).
2. **Вариация фикстуры для TC-012.** Дублированный блёрб — переиспользован
   существующий `render_listing_html([work, work])` БЕЗ правок генератора (уже
   принимал произвольный список, дедупликации не делал).
   `scripts/build_replay_recordings.py::build_listing_duplicate_work()`.
   Записан `framework/data/recordings/listing_duplicate_work.mitm`; проверено
   (не только логикой генератора, но и по факту записанного тела) — `li
   id="work_900000001"` встречается в HTML ровно 2 раза.
3. **Зелёный прогон-доказательство rating-сценария (TC-009).**
   `framework/tests/test_replay_infra_probe.py` (новый модуль) —
   `test_rate_from_listing_bottom_sheet_on_replay_fixture` на
   `listing_basic.mitm` (та же фикстура инкремента 1, фикстуры хватило —
   подтверждено прогоном, не только анализом). НЕ автоматизация TC-009:
   `@allure.id("AT-BUG-004-rating-probe")`, не `"TC-009"` — намеренно, чтобы не
   создавать у инструментов, читающих allure-id, ложное впечатление
   автоматизации кейса (сверено: `scripts/board_sync.py`/`arch_check.py` не
   связывают allure.id с `test-cases/*.md` автоматически, но конвенция
   репозитория — allure.id = TC-xxx только для реально закодированных кейсов).
   `test-cases/rating/TC-009.md` НЕ тронут (остаётся `Review`). Новые шаги:
   `browser_steps.tap_rate_button`/`assert_rating_badge_visible`,
   `rating_steps.rate_via_listing_overlay`, `ListingPage.rate_button` —
   собраны по паттерну `test_visibility.py` (steps, не локаторы в tests/,
   `wait_until` вместо одноразового чтения).

**Class-fix по правилу 9 (найден при отладке пункта 3, НЕ запрошен диспетчем,
докладываю по правилу воркеров «замеченные аналоги — в отчёте»):**
`ListingPage.badge_for`/`WorkPage.has_badge` проверяли `[data-ao3-badge]` —
разбор `ao3_bridge.js` показал, что этот атрибут встречается ТОЛЬКО в
defensive-очистке (`applyRatings`: `li.querySelectorAll('[data-ao3-badge]')
.forEach(b => b.remove())`) — элемент с ним НИКОГДА не создаётся нигде в
коде приложения. Проверка всегда возвращала `False` — латентный TEST_BUG,
живущий с инкремента 1 (`badge_for` был написан, но не имел вызывающего кода
до пункта 3 этого инкремента — поэтому не проявлялся раньше). Локатор выведен
из места рендера (`updateRateButton` в `ao3_bridge.js`: красит САМУ
`[data-ao3-rate-btn]` цветом `BADGE[rating].bg`, не создаёт отдельный
элемент) и верифицирован живым деревом (диагностический скрипт,
`driver.value_of_css_property('background-color')` до/после тапа:
`rgba(0, 0, 0, 0)` → `rgba(232, 237, 245, 1)` для рейтинга READ) — фикс:
`badge_for` теперь проверяет непрозрачность `background-color` кнопки. Тем же
разбором найдено: `WorkPage.has_badge()` — не просто неверный селектор, а
неверная предпосылка (на work-странице bridge вообще не инжектирует
Rate-кнопку/бейдж — `applyRatings` проходит только по
`li[id^="work_"].work.blurb` листинга, которых на work-странице нет); метод
удалён целиком (был неиспользуемым, `WorkPage` нигде не импортируется —
нулевой риск). `selectors.RATING_BADGE` удалена из `selectors.py` с
пояснением.

**Побочная находка (housekeeping, не test_debt баг):** `git add` бинарных
`.mitm` печатал ложное "LF will be replaced by CRLF" (`core.autocrlf=true`,
файлы не помечены `binary`) — сверено побайтово (`SHA256` диска ==
`git show :path`, т.е. `git checkout`-эквивалент): на практике не корродирует
(git's binary-детектор перепроверяет перед конвертацией), но полагаться на
неявную эвристику для воспроизводимого бинарного формата — риск для будущих
клонов/чекаутов на другой машине. Добавлен `.gitattributes` (`*.mitm binary`)
— защищает весь `framework/data/recordings/`, включая уже закоммиченные
`listing_basic.mitm`/`ao3_home_smoke.mitm`.

Witness:
- Детерминизм: `python scripts/build_replay_recordings.py` дважды подряд →
  `fc /b` — 0 расхождений для всех трёх `.mitm` (`listing_basic.mitm`,
  `listing_duplicate_work.mitm`, `work_with_download.mitm`).
- `Invoke-Pytest tests/test_replay_infra_probe.py -v` — зелёный ДВАЖДЫ подряд
  отдельными прогонами (21.37s, затем 20.90s), оба ПОСЛЕ фикса
  `badge_for`/до фикса тест падал `TimeoutException` на несуществующем
  `[data-ao3-badge]` (воспроизведено и задокументировано намеренно, не
  скрыто).
- `Invoke-Pytest -m p0 -v` — полный p0-набор (18 тестов) без регресса,
  `18 passed, 9 deselected in 593.54s` (включает `test_rating.py`,
  `test_visibility.py::test_disliked_hidden_on_listing`,
  `test_smoke.py`, `test_library.py` — ни один не использовал
  `badge_for`/`has_badge` ранее, регресса на самом фиксе нет).
- `python D:\AO3_tests\scripts\arch_check.py` — `ошибок 0, предупреждений 0`.
- `python -m pytest D:\AO3_tests\scripts\tests -q` — `262 passed`.

**Сверка «## Критерий готовности (Fixed)» построчно:**
- «В `conftest.py` есть replay-фикстура ..., используемая хотя бы одним
  зелёным тестом» — ВЫПОЛНЕН (инкремент 1, подтверждён повторно этим
  прогоном).
- «Записаны и лежат в `framework/data/recordings/`: work-страница с открытым
  HTML-скачиванием (+ сам .html) и записи, требуемые кейсами
  TC-009/013/014/015» — ВЫПОЛНЕН этим инкрементом (`work_with_download.mitm`
  добавлен; `listing_basic.mitm` для TC-009/013/014/015 — с инкремента 1,
  пригодность для TC-009 теперь подтверждена прогоном, не только анализом).
- «Хотя бы один из заблокированных кейсов доведён до зелёного прогона на
  replay ..., остальные разблокированы для test-automator» — ВЫПОЛНЕН
  (TC-013 — инкремент 1, без изменений).
- «Smoke без регресса» — ВЫПОЛНЕН (p0 18/18 выше).

Все 4 буллета выполнены → `status: Fixed`. TC-012/032/033/043/044/045
формальным текстом критерия не перечислены поимённо (только TC-009/013/014/
015) — но их фикстуры (`work_with_download.mitm`, `listing_duplicate_work.mitm`,
`listing_basic.mitm`) готовы; разблокировка/перевод Review→Approved —
по-прежнему решение test-designer/Lead, не test-maintainer.

Границы: `app-under-test/` не тронут; `test-cases/*.md` frontmatter не тронут
(TC-009/012/032/033 остаются `Review`); чужие незакоммиченные пути
(`logs/routing-log.jsonl`, `state/board-cursor.json`) не тронуты и не
закоммичены. Верификация (`Fixed → Verified`) — за fix-verifier, новая сборка
приложения не нужна (фикс целиком во фреймворке).

**2026-07-09T12:52:00Z — critic (приёмка инкремента 3, правило 3а): ACCEPT;
Lead: приёмка оформлена, Fixed подтверждён.** Проверено независимо: контракт
download-flow построчно против `DownloadRepository.fetchDownloadUrl` (regex
берёт первое `/downloads/...*.html`; порядок pdf->html в записи это учитывает),
детерминизм перегенерацией (нулевой git-diff), проба TC-009 зелёная (22.06s),
переход Open->Fixed легален (transitions.yaml guard test_debt). Незапрошенный
class-fix мёртвого `[data-ao3-badge]`-локатора верифицирован по ao3_bridge.js.
Некритичное, В ОЧЕРЕДЬ (не блокирует Verified): (1) докстринг
`framework/steps/browser_steps.py::assert_rating_badge_visible` устарел —
упоминает `[data-ao3-badge]`, фактическая проверка по background-color
Rate-кнопки; (2) `ListingPage.badge_for` смотрит только первое вхождение —
будущей автоматизации TC-012 (двойной блёрб, `listing_duplicate_work.mitm`)
понадобится вариант по ВСЕМ вхождениям. Дальше по конвейеру: D1 fix-verifier.
