---
id: AT-BUG-029
title: "listing_basic.mitm не несёт .html-файл скачивания (недостаёт одной транзакции) — блокирует автоматизацию TC-115 (edge-vs-level BUG-014 через листинг)"
type: test_debt
debt_kind: missing_fixture
severity: minor
status: Verified
found_in: "test-designer, проектирование области settings/downloads auto-download-favorite (needs-design по BUG-014), 2026-07-28"
fixed_in: "framework (test-only, без сборки приложения) — scripts/build_replay_recordings.py, framework/data/recordings/listing_basic.mitm, framework/tests/test_downloads.py"
last_seen_in: ""
test_cases: ["TC-115"]
runs: []
duplicates: []
regression_of: ""
status_since: "2026-07-29T09:35:11Z"
updated: "2026-07-29T09:35:11Z"
reopen_count: 0
dispute_count: 0
awaiting: none
resolution: ""
resolution_comment: ""
known_issue: "false"
blocked_reason: ""
lock: ""
---

# AT-BUG-029 — В listing_basic.mitm недостаёт одной транзакции (.html-файл) для TC-115

## Окружение

Не зависит от сборки приложения: долг тестовой системы (`type: test_debt`,
`debt_kind: missing_fixture`). Текущая тестируемая сборка 1.10 (versionCode 11).
Класс СМЕЖНЫЙ с уже закрытым `AT-BUG-004` (Verified, 2026-07-09), но НЕ дубликат —
AT-BUG-004 закрыл отсутствие replay-инфраструктуры КАК ТАКОВОЙ (mitm не подключён к
conftest, записей не было вообще); эта находка — про узкий пробел уже ПОСЛЕ того,
как инфраструктура доведена: существующей записи `listing_basic.mitm` не хватает
РОВНО ОДНОЙ транзакции (`.html`-файл скачивания) для одного конкретного сценария
(TC-115).

## Суть долга

**Поправка 2026-07-28 (critic-вход, разбор вердикта ДОРАБОТАТЬ):** первая версия
этого бага ошибочно диагностировала пробел как «нет комбинации ДВУХ записей
(листинг + work-с-download) в одном flow-файле». Парсинг самих `.mitm`-записей и
`scripts/build_replay_recordings.py:24-50` (`build_listing_basic`) опровергает
это: `listing_basic.mitm` УЖЕ несёт ТРИ транзакции — `base_flow` (листинг),
`filtered_flow` (та же HTML под filtered URL) и, что важно здесь,
`work_page_flow = rb.make_html_get_flow(first_work.url,
rb.render_work_page_html(first_work))` (:47) — GET work-страницы `ALL_WORKS[0]`
= `W.LOVED` (`framework/data/works.py:31`), той же работы, что использует
`build_work_with_download`. Work-страница-с-download-ссылкой для W.LOVED в
`listing_basic.mitm` УЖЕ ЕСТЬ.

`TC-115.md` (проектируется тем же ходом, что этот баг — регрессионный тест на
edge-vs-level класс BUG-014 через ВХОД С ЛИСТИНГА, зеркало уже автоматизируемого
TC-114 через панель работы) требует ОДНОВРЕМЕННО:

1. WebView в момент правки комментария показывает ЛИСТИНГОВУЮ страницу с блёрбом
   работы W (`li.work.blurb`) — иначе Rate-кнопка/bottom-sheet (`RatingOverlay`,
   вход `applyRating`) физически недостижимы; **уже покрыто** `base_flow`
   `listing_basic.mitm`.
2. Фоновый OkHttp-вызов `DownloadRepository.downloadWork` (GET work-страницы работы
   W + GET `.html`-файла) РЕАЛЬНО резолвится через replay и завершается файлом,
   ЕСЛИ (и только если) сработал дефект BUG-014 — иначе негативный Then кейса
   («файл не появился») истинен ВСЕГДА независимо от того, сработал баг или нет
   (ложно-зелёный тест). GET work-страницы W.LOVED — **уже покрыто**
   `work_page_flow` `listing_basic.mitm` (см. выше). Отсутствует РОВНО ОДНА
   транзакция: GET `.html`-файла (`rb.download_url(work)` →
   `rb.render_downloaded_work_html(work)`, тот же приём, что `download_flow` в
   `build_work_with_download`, :76-77) — её `listing_basic.mitm` не несёт.

Без исправления: фоновый GET `.html`-файла (второй шаг `downloadWork`, ЕСЛИ он
случится из-за бага) уйдёт через `server_replay_extra=forward`
(`framework/core/mitm.py:121`, «незаписанные запросы уходят на живой сервер») на
реальный `archiveofourown.org`, где синтетического download-пути не существует —
попытка молча провалится (404/таймаут), файл не появится НЕЗАВИСИМО от того,
вызвался ли `downloadWork()` в принципе. Оракул побочных эффектов (`download_oracle`,
conftest.py, класс BUG-014) в этом случае НЕ отличает «бага нет» от «бага не поймали
из-за дыры в фикстуре» — тест был бы неинформативным приёмом регрессии, а не
осмысленной защитой.

## Критерий готовности (Fixed)

Минимальный фикс — добавить недостающий `.html`-flow в `build_listing_basic()`
(`scripts/build_replay_recordings.py:24-50`), по образцу `download_flow` из
`build_work_with_download` (:76-77):

```python
download_flow = rb.make_html_get_flow(rb.download_url(first_work),
                                       rb.render_downloaded_work_html(first_work))
...
rb.write_flows(path, [base_flow, filtered_flow, work_page_flow, download_flow])
```

Путь «расширить сигнатуру `start_replay` до списка flows-файлов» из первой
версии этого бага УБРАН из критерия готовности — он не нужен: раз work-страница
W.LOVED уже в `listing_basic.mitm`, комбинировать два ОТДЕЛЬНЫХ `.mitm`-файла в
одной сессии `replay`-фикстуры не требуется вовсе, это был переразмеренный
критерий поверх реального (двухстрочного) пробела.

**Остаётся ли это отдельным test_debt-тикетом при правке в ~2 строки?** Да —
осознанно, не по инерции: правило 4 воркфлоу test-designer требует завести
test_debt-баг на ЛЮБОЙ блокер автоматизации, обнаруженный в заметках кейса,
независимо от размера фикса — тикет служит машиночитаемым триггером очереди
«Устранить test debt» (B4, `state/rules.yaml`), которую проза заметки кейса не
триггерит вовсе (см. прецедент AT-BUG-004/005/006, на который ссылается сам
промпт test-designer: блокеры-заметки без тикета годами не попадали в очередь).
Размер диффа фикса не отменяет этого — он лишь снижает severity/объём работы
самого тикета (severity minor уже стоит верно).

Готово, когда:
- `build_listing_basic()` несёт четвёртый flow (`.html` W.LOVED), `listing_basic.mitm`
  пересобран (`python scripts/build_replay_recordings.py`).
- `framework/tests/test_downloads.py::test_edit_note_on_already_saved_work_via_listing_overlay_does_not_redownload`
  (или аналогичное имя) реализован и подключён к TC-115, использует ОДИН
  `listing_basic.mitm` (без правки `mitm.py::start_replay`).
- Красная проба: временное восстановление условий BUG-014 (или прямой вызов
  `downloadWork` в тестовом хуке) РЕАЛЬНО создаёт файл в download-директории и
  `download_oracle` его ловит — доказательство, что негативный Then содержателен,
  а не тривиально истинен из-за дыры в фикстуре.
- Тест TC-115 реализован и подключён к фикстуре — зелёный прогон TC-115 НЕ входит
  в критерий Fixed ЭТОГО test_debt, он зависит от отдельного app_bug BUG-014
  (`status: Open` в приложении на момент фикса этого долга) и придёт сам, без
  правки теста, когда BUG-014 будет исправлен в app-under-test.
- `python -m pytest scripts/tests -q` без регресса.

## Верификация (заполняет fix-verifier)

**ВНИМАНИЕ fix-verifier (mode=verify, D1):** TC-115 ОЖИДАЕМО красный —
регрессионный замок на `bugs/BUG-014.md` (`type: app_bug`, `status: Open` на
момент этого Fixed), НЕ на пробел этого test_debt. Красный прогон TC-115 —
**НЕ основание** переводить этот `AT-BUG-029` обратно в `Reopened` по
стандартному протоколу «репро осталось → Reopened». Верифицируй ФИКСТУРНЫЙ
артефакт долга напрямую: device-free юнит
`framework/tests/test_recording_builder_unit.py` (проверяет, что
`listing_basic.mitm` несёт 4 flow, включая `rb.download_url(first_work)` /
`rb.render_downloaded_work_html(first_work)`) — зелёный без устройства. TC-115
станет валидным критерием Fixed только для BUG-014, не для этого долга.

| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| — | — | — | — | Open, ждёт фикса |
| 2026-07-28 | app 1.10 (versionCode 11, debug, неизменна — test_debt в фреймворке) | TC-115 (`test_edit_note_on_already_saved_work_via_listing_overlay_does_not_redownload`, новый) + `python -m pytest scripts/tests -q` + регрессия `test_rate_work_from_listing_overlay` (TC-009, x5 параметризаций, тот же `listing_basic.mitm`) | TC-115: FAILED (ожидаемо-красный, см. «Обсуждение» — реальный файл скачан живым BUG-014, `assert_download_icon_shown` не прошёл, `download_oracle` поймал незапрошенный файл). `scripts/tests`: 682 passed, 1 skipped, без регресса. TC-009 x5: 5 passed — остальные потребители `listing_basic.mitm` не задеты добавлением четвёртого flow. `Get-Device`: `DEVICE: emulator-5554` | **Fixed (test_debt)** — критерий готовности этого долга выполнен; продуктовый TC-115 остаётся красным по ВНЕШНЕЙ причине (см. ниже), не входит в критерий этого Fixed |
| 2026-07-29 | framework test-only, без сборки приложения (device-free юнит; `Get-Device` не запрашивался — верификация не требует устройства, см. предупреждение в этом разделе) | `framework/tests/test_recording_builder_unit.py` (39 items — оба целевых юнита + весь модуль как минимальный smoke области recording-builder: `listing_paginated.mitm`/`works_multi.mitm` не задеты) — `powershell -NoProfile -ExecutionPolicy Bypass -Command ". D:\AO3_tests\scripts\tasks.ps1; Invoke-Pytest tests/test_recording_builder_unit.py -v"` | `test_listing_basic_has_exactly_four_flows` PASSED, `test_listing_basic_has_download_html_flow_for_first_work` PASSED (подтверждает `rb.download_url(first_work)`/`rb.render_downloaded_work_html(first_work)` — ровно тот flow, что требует критерий готовности) — весь модуль: `39 passed`, `PYTEST_EXIT=0`. TC-115 не перезапускался этим ходом (заведомо ожидаемо-красный по BUG-014, `status: Open` — см. предупреждение выше и запись 2026-07-28; красный TC-115 НЕ основание для Reopened) | **Verified** — критерий готовности test_debt подтверждён напрямую device-free юнитом; `Fixed → Verified` |

## Обсуждение

**2026-07-29T09:37:00Z — координатор (правка по критик-входу, единственный блокер):**
критик подтвердил существо D1-верификации (39 passed, обе целевые пробы,
переход легален), единственный блокер — `status_since`/`updated` были
проставлены `00:00:00Z` вместо фактического момента перехода (сравнение с
`state/orchestrator-log.md`: диспатч D1 09:35:11Z). Поля исправлены на
`2026-07-29T09:35:11Z`; повторная верификация не требуется (критик явно это
оговорил). Ригор-замечания критика (N1 validate_frontmatter, N2 негатив о
собратьях, N3/N4 носитель S1/S3 и рассинхрон HANDOFF) — переданы отдельно,
не блокируют это accepted.

**2026-07-28 — test-designer, заведение (правило 4 промпта test-designer):**
блокер обнаружен при проектировании TC-115 (шаг 4 воркфлоу test-designer — блокер
в заметках для автоматизации ОБЯЗАН быть заведён test_debt-багом в том же ходе, не
оставлен только прозой тела кейса, урок AT-BUG-004/005/006 про заметки, живущие
годами без баг-тикета). Дизайн кейса завершён и полон (`TC-115.md`, `status:
Review`) — ограничена ТОЛЬКО автоматизация; сам кейс НЕ переведён в `Blocked`.
Основание — `schemas/transitions.yaml` (машина `test-case`, `initial: [Draft,
Review]`, :78 и :94-95): комментарий у `initial` прямо говорит «test-designer:
Draft при спорных требованиях, иначе сразу Review» — TC-115 не несёт спорного
ТРЕБОВАНИЯ (никакого расхождения PROJECT.md/UI нет), поэтому `Review` — штатный
начальный статус, а не самовольное избегание `Blocked`. Дополнительно
`{from: "*", to: Review, by: [human, test-automator, test-maintainer], ref:
"вернуть на доработку (прецедент TC-009: replay-блокер)"}` (:94-95) явно называет
именно ЭТОТ класс ситуации («replay-блокер») легальным поводом быть/оставаться в
`Review`, с прямым прецедентом TC-009. Транзиция test-case `*→Blocked` (:96-97) —
актор `factory` (эскалация деградации/конфликта, прецедент TC-013..015), не
`test-designer`/`human`; заводимый здесь `missing_fixture` — рутинный долг
инфраструктуры, не деградация/конфликт, эскалация не требуется.

**2026-07-28 — test-maintainer (B4, фикс долга).** Реализован ровно критерий
готовности из раздела выше:

1. `build_listing_basic()` (`scripts/build_replay_recordings.py`) получил
   четвёртый flow — `download_flow = rb.make_html_get_flow(rb.download_url(first_work),
   rb.render_downloaded_work_html(first_work))` — рядом с уже существующими
   `base_flow`/`filtered_flow`/`work_page_flow`, тем же приёмом, что `download_flow`
   в `build_work_with_download`. `listing_basic.mitm` пересобран
   (`python scripts/build_replay_recordings.py`, venv-python framework — голый
   `python` в PATH не резолвит `mitmproxy`, тот же класс, что «Дисциплина команд»
   п.6 для env-зависимых тулов).
2. Реализован `framework/tests/test_downloads.py::
   test_edit_note_on_already_saved_work_via_listing_overlay_does_not_redownload`,
   подключён к TC-115 (`@allure.id("TC-115")`), использует ОДИН `listing_basic.mitm`
   — `mitm.py::start_replay` не тронут. Given — `loved_work_seeded` (W.LOVED
   засеяна SAVE, `downloadPath=null`, тот же порядок «сидинг ДО сессии Appium», что
   TC-032/033) + `settings_steps.enable_auto_download`; When — Rate-кнопкой листинга
   открыт bottom-sheet уже-Favorite работы, раскрыто и сохранено поле комментария
   («re-save-note», через `rating_steps.add_note_via_listing_overlay`); Then —
   комментарий персистентен, карточка в Library по-прежнему несёт download-иконку
   (не open), без `@pytest.mark.produces_download` (`download_oracle` — общий
   инвариант-оракул).
3. **Красная проба — живой прогон, не гипотетический хук.** BUG-014
   (`bugs/BUG-014.md`) СЕЙЧАС `status: Open` в реальном приложении — восстанавливать
   условия дефекта искусственно не потребовалось, они уже присутствуют в тестируемой
   сборке. `Invoke-Pytest -k test_edit_note_on_already_saved_work_via_listing_overlay_does_not_redownload -v`:
   `FAILED` на `library_steps.assert_download_icon_shown` (карточка показала
   open-иконку — файл реально появился), сопровождается `UserWarning` оракула:
   `download_oracle: незапрошенное скачивание — класс BUG-014. Новые/изменившиеся
   файлы в .../ao3_downloads: ['.../ao3_A Loved Test Work_900000001.html']`
   (предупреждение, не отдельный `fail`, — по дизайну M2 оракула: `call`-фаза уже
   упала на собственном assert'е теста, второй `fail` поверх не добавляется).
   Это и есть доказательство содержательности: ЕСЛИ бы четвёртый flow отсутствовал,
   фоновый `DownloadRepository.downloadWork` ушёл бы в live-сеть на несуществующий
   `ao3_id` и молча провалился (404/таймаут) — карточка осталась бы с
   download-иконкой, Then был бы ложно-зелёным НЕЗАВИСИМО от бага. С фиксом файл
   реально создаётся через replay, оракул и явный assert теста оба это ловят.
4. Зелёный прогон TC-115 НЕ достигнут в этом инкременте и намеренно НЕ входит в
   критерий Fixed этого долга — BUG-014 (`type: app_bug`, `status: Open`) живёт в
   `app-under-test/`, правка которого вне мандата test-maintainer и вне скоупа
   test_debt-долга (правило CLAUDE.md: не маскировать причину — TC-115 обязан
   оставаться красным, пока продуктовый баг не пофикшен; ослаблять assert не
   стал). Тест станет зелёным сам, без правки, после фикса BUG-014 — это и есть
   регрессионный замок, ради которого TC-115 спроектирован.
5. `python -m pytest scripts/tests -q` (venv-python): `682 passed, 1 skipped` — без
   регресса относительно бейзлайна.
6. Регрессия потребителей `listing_basic.mitm`: `Invoke-Pytest -k
   test_rate_work_from_listing_overlay -v` (TC-009, 5 параметризаций рейтингов, та
   же запись) — `5 passed` — добавление четвёртого flow не задело остальные
   сценарии на этой фикстуре.

`app-under-test/` не тронут (только чтение `BUG-014.md`/кода приложения для
диагноза, ни одной правки). Аналогичного класса пробела (недостающая транзакция в
уже существующей `.mitm`-записи) в других фикстурах при этом фиксе не замечено —
не докладываю новую ось SIBLING_MAP.

**2026-07-28/29 — test-maintainer (attempt 2, /qa-loop доработка по critic-вердикту
ДОРАБОТАТЬ, существо фикса НЕ тронуто — critic уже подтвердил его эмпирически).**
Три организационные правки:

1. `TC-115.md`: `automated_by` заполнен реальной ссылкой на тест
   (`framework/tests/test_downloads.py::
   test_edit_note_on_already_saved_work_via_listing_overlay_does_not_redownload`)
   — уводит кейс из-под условия правила «Автоматизировать Approved-кейс»
   (`automated_by` пуст) и направляет в «Ревью нового автотеста» (F1, штатный
   гейт для нового автотеста). Раздел «Заметки для автоматизации» переписан:
   убраны устаревшие «БЛОКЕР»/«недостаёт РОВНО ОДНОЙ транзакции»/«кейс не
   диспатчится, status: Review» (фикстура уже готова, статус кейса и был, и
   остаётся `Approved`) — заменены на текущее состояние (тест написан и
   подключён, ожидает F1) с явным объяснением, что красный прогон — замок на
   `BUG-014` (app_bug, `status: Open`), не дефект теста/фикстуры.
2. Раздел «Критерий готовности (Fixed)» этого файла переписан: убран
   самопротиворечивый пункт «Зелёный прогон TC-115 … (отдельная работа вне
   этого долга)» из списка «Готово, когда» — список озаглавлен как критерии
   готовности, но нёс пункт, прямо в тексте же названный НЕ критерием.
   Заменён на явную формулировку «реализован и подключён, зелёный прогон НЕ
   входит в критерий Fixed».
3. Добавлено явное предупреждение для fix-verifier (D1) перед таблицей
   «Верификация» — красный TC-115 не повод откатывать этот `test_debt` в
   `Reopened`; верифицировать нужно фикстурный артефакт (юнит ниже), не проход
   TC-115.
4. Добавлены device-free юниты
   `framework/tests/test_recording_builder_unit.py::
   test_listing_basic_has_exactly_four_flows` и
   `::test_listing_basic_has_download_html_flow_for_first_work` (имена
   поправлены координатором — прежний текст называл несуществующую функцию,
   находка critic-входа 2026-07-28) — сверяют, что `listing_basic.mitm` несёт
   РОВНО 4 flow, среди URL присутствует `rb.download_url(ALL_WORKS[0])`, тело
   этого flow равно `rb.render_downloaded_work_html(ALL_WORKS[0])`. Witness —
   см. отчёт /qa-loop этого хода.

`S3` (`bugs/BUG-014.md::test_cases`) и `S1` (недостающие work-flow
`/works/900000002..900000005` в `listing_basic.mitm`) — доложены находками в
отчёте /qa-loop, не расширяю scope этим ходом (правило 9/D-0037 CLAUDE.md).

**2026-07-29 — fix-verifier (mode=verify, D1).** Верифицировал ФИКСТУРНЫЙ
артефакт долга напрямую, device-free, как предписано предупреждением выше —
не TC-115. Прогон `framework/tests/test_recording_builder_unit.py` (канонической
формой `Invoke-Pytest`): `39 passed`, `PYTEST_EXIT=0`, включая оба целевых юнита
(`test_listing_basic_has_exactly_four_flows`,
`test_listing_basic_has_download_html_flow_for_first_work`) — `listing_basic.mitm`
несёт ровно 4 flow, среди них `rb.download_url(first_work)` с телом
`rb.render_downloaded_work_html(first_work)`. Критерий готовности test_debt
(раздел «Критерий готовности (Fixed)») выполнен целиком: четвёртый flow есть и
пересобран, TC-115 реализован и подключён к фикстуре, красная проба уже
задокументирована (запись 2026-07-28) как содержательная (не тривиально-зелёная
из-за дыры в фикстуре), `scripts/tests` без регресса (запись 2026-07-28). TC-115
намеренно не перезапускался этим ходом — предупреждение автора корректно: он
остаётся красным по BUG-014 (app_bug, Open), это НЕ регресс этого test_debt.
Аналогов класса «недостающая транзакция в уже существующей `.mitm`-записи» в
других фикстурах не замечено (докстринг модуля упоминает `listing_paginated.mitm`/
`works_multi.mitm` как соседей той же доработки — оба уже покрыты своими юнитами
в том же файле, не новый пробел). `app-under-test/` не тронут. Статус переведён
`Fixed → Verified` (`schemas/transitions.yaml`: `{from: Fixed, to: Verified, by:
[fix-verifier]}`, легально). Лок снят.

Долг переведён `Open → Fixed` (B4, guard `type: test_debt`, актор
test-maintainer легален по `schemas/transitions.yaml`). Лок снят.

## Чек-лист качества
- [x] Проверены дубликаты среди открытых test_debt-багов — не совпадает с
      AT-BUG-004 (Verified, закрыл отсутствие инфраструктуры КАК ТАКОВОЙ — mitm
      не подключён к conftest, записей не было вообще, а не недостающую ОДНУ
      транзакцию в уже существующей записи) и не пересекается с прочими
      открытыми test_debt (AT-BUG-025/026/027/028 — другие классы:
      navigate-таймаут, AVD/WebView EOL)
- [x] Суть долга ясна и воспроизводима по коду (`build_replay_recordings.py:24-50
      build_listing_basic`, `recording_builder.py` перечень записей) — перепроверена
      парсингом `.mitm` при разборе critic-вердикта 2026-07-28, диагноз исправлен
- [x] Severity: minor — блокирует автоматизацию ровно одного P1-кейса (TC-115), не
      целый батч, и сам кейс спроектирован и полноценен (design не заблокирован)
- [x] Ни одно изменение не внесено в app-under-test/
- [x] `test_cases: ["TC-115"]` указывает единственный заблокированный кейс
