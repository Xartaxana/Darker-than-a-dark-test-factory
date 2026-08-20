---
id: AT-BUG-076
title: "Методическая норма Data Setup «auto_apply_filter материализуется только фактическим переключением тумблера» жила только прозой закрытого CH-010 — не была зафиксирована постоянным носителем, читаемым будущими test-designer-сессиями"
type: test_debt
debt_kind: missing_fixture
severity: minor
status: Verified
found_in: "test-designer, followup CH-010 followup_tc#3 (rework attempt по критику task_id CH-010-followup3-methodology, 2026-08-15): предыдущая попытка закрыла followup_tc#3 ТОЛЬКО прозой в docs/01-test-strategy.md §9 без id-токена, машина (scripts/sla_sweep.py FOLLOWUP_TC_ID_RE) закрытие не видела; вдобавок сама формулировка нормы была фактически неверна (см. «Суть долга»)"
fixed_in: "test-maintainer, 2026-08-19 (6 якорей §9 + settings_steps.py:90)"
last_seen_in: ""
test_cases: []
runs: []
duplicates: []
regression_of: ""
status_since: "2026-08-20T04:10:00Z"
updated: "2026-08-20T04:10:00Z"
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

# AT-BUG-076 — Data Setup-норма про `auto_apply_filter` жила только прозой чартера, не постоянным носителем (плюс сама норма была неверна)

## Окружение

Не зависит от сборки приложения: долг тестовой системы (`type: test_debt`,
`debt_kind: missing_fixture` — читай как «недостающая тестовая
инфраструктура/методический носитель», ближайшая категория схемы; тот же
приём, что у AT-BUG-010/022/033/070 для находок, не укладывающихся буквально
ни в один enum-пункт `schemas/bug.schema.yaml`). Класс СМЕЖНЫЙ с AT-BUG-010
(находка, известная 2026-07-02, жила заметкой в теле кейса и не была
заведена артефактом до 2026-07-14) и с AT-BUG-070 (followup_tc CH-010,
закрытый ссылкой на test_debt-баг, а не новым TC) — но не дубликат ни
одного: AT-BUG-010 про несидируемое NULL-поле в `seed_db.py`, AT-BUG-070 про
отсутствующий наблюдательный примитив адресации вкладок; здесь долг —
методическая норма Data Setup, которую сама фабрика (правило B4 машины
`scripts/sla_sweep.py`) не могла увидеть закрытой, пока не получила
id-токен.

## Суть долга

`exploratory-charters/CH-010.md` (`followup_tc[3]`) закрывал методическую
находку #5 сессии («ключ `auto_apply_filter` в `shared_prefs/
ao3_settings.xml` требует особого обращения при снятии снимков ДО того, как
сцена его материализовала») правкой прозы в `docs/01-test-strategy.md` §9 —
БЕЗ id-токена вида `TC-\d+`/`(AT-)?BUG-\d+`, которого требует
`FOLLOWUP_TC_ID_RE` (`scripts/sla_sweep.py:112`) для распознавания
обработанной записи. `python scripts/sla_sweep.py --dry-run` продолжал бы
показывать 0 действий по этой записи, а эскалация `CH-010:followup_tc#3` в
`state/escalations.md` возникала бы каждый проход — норма фактически
невидима машине конвейера, хотя прозой формально «закрыта».

**Вдобавок сама формулировка нормы была фактически НЕВЕРНА** (поймано
критиком по коду приложения при приёмке этого followup): исходная правка
утверждала, что ключ `auto_apply_filter` материализуется «после первого
визита на экран Settings» (со ссылкой `SettingsScreen.kt:538-539` — тоже
неверной, это код ДРУГОГО ключа, `toggleHideRating`). Фактически:

- единственное место записи — `setAutoApplyFilter` (`SettingsScreen.kt:595`,
  сама функция начинается `:593`), вызывается ИСКЛЮЧИТЕЛЬНО из
  `onCheckedChange` тумблера (`:897`);
- открытие экрана Settings само по себе только ЧИТАЕТ
  `prefs.getBoolean("auto_apply_filter", true)` (`:201`) — ничего не
  пишет;
- хелпер `framework/screens/settings_screen.py:228-233`
  (`set_auto_apply_filter`) ИДЕМПОТЕНТЕН: тапает тумблер, только если
  текущее состояние отличается от желаемого — при дефолте ON и желаемом ON
  визит в Settings + вызов хелпера НЕ материализует ключ вовсе;
- живой контрпример уже был в самом CH-010.md (строки 731-733 рабочего
  дерева на момент находки): Settings был посещён (`is_auto_apply_checked`
  через UI), но «prefs-ключ намеренно не материализовался».

Если бы норму не поймали до `status: Review`, будущие test-designer-сессии
и чартеры получили бы предписание «предварять пробу визитом в Settings» —
которое НЕ материализует ключ при дефолтном/совпадающем состоянии и
воспроизводило бы саму находку #5 заново.

Отдельно критик указал на опасность рекомендации «использовать
`active_filter_profile_id` как самостоятельный атомарный якорь» БЕЗ
оговорки: `BrowserViewModel.kt:590-596` УДАЛЯЕТ этот ключ (`remove(...)`)
при снятии профиля (`id == null`) — для проб, чей Then — «профиль снят»
(класс BUG-068/TC-205), отсутствие ключа СОВПАДАЕТ с ожидаемым исходом,
контроль валидности вырождается в то самое ложно-позитивное «как будто всё
ОК», против которого писалась исходная заметка.

## Критерий готовности (Fixed)

- `docs/01-test-strategy.md` §9, блок «filter-profiles/browser:
  авто-применение фильтра при навигации» несёт ИСПРАВЛЕННУЮ методическую
  заметку Data Setup: материализация ключа привязана к ФАКТИЧЕСКОМУ
  переключению тумблера (`SettingsScreen.kt:593-595`, вызов `:897`), явно
  говорит, что визит в Settings САМ ПО СЕБЕ ничего не пишет, называет
  идемпотентность `settings_steps.set_auto_apply_filter_toggle` и несёт оговорку
  про непригодность `active_filter_profile_id` как якоря валидности для
  проб с Then «профиль снят».
- `exploratory-charters/CH-010.md`, `followup_tc[3]` несёт id-токен
  `AT-BUG-076` (детектируется `FOLLOWUP_TC_ID_RE`,
  `scripts/sla_sweep.py:112`).
- `python scripts/sla_sweep.py --dry-run` не показывает эскалацию
  `CH-010:followup_tc#3` как необработанную.
- `python scripts/validate_frontmatter.py` — без ошибок по обоим файлам.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| 2026-08-20 | doc-only, не зависит от сборки APK; app-under-test HEAD сверки якорей `fdd3f72884105d1453448e0c9a7f2b109588b182` (2026-08-19T19:12:30+02:00) | нет (`test_cases: []`, carve-out doc-only test_debt) | все 9 якорей `docs/01-test-strategy.md` §9 (`BrowserScreen.kt:687-697`/`:690`/`:697`, `BrowserViewModel.kt:1182`/`onPageLoaded:636`/`:669-671`/`applyFilter:754`/`:768`/`:746-752`, `SettingsScreen.kt:82`/`:599-601`/`:903`/`:207`, `MainActivity.kt:229-230`, `settings_screen.py:267-272`, `settings_steps.py:88`/`:90`) дословно сверены `Read`-ом с текущим кодом — 100% совпадение, ни одного нового рассинхрона. ДВА исполняемых пункта Критерия готовности прогнаны живьём координатором (критик-гейт Б3, 2026-08-20 — исходная запись подставляла Read-сверку вместо них): `python scripts/sla_sweep.py --dry-run` → `sla_sweep: действий: 0 (dry-run)`; `python scripts/validate_frontmatter.py` → `ошибок 0, предупреждений 0`. | Verified |

**Замена device-прогону (carve-out, doc-only test_debt, `test_cases: []`).** Обоснование: `debt_kind: missing_fixture`, поверхность — прозаический методический носитель `docs/01-test-strategy.md` §9 + докстринг `settings_steps.py:90`, устройственного предмета нет — device-прогон не может исполнить «проверяемое поведение» (это не код). Каждый `file:line`-якорь прочитан `Read`-ом из АКТУАЛЬНОГО `app-under-test` дерева и сверен построчно с прозой заметки — все совпали ТОЧНО (см. таблицу выше); это подкрепляет ТОЛЬКО фактическую точность якорей, НЕ заменяет исполнение DoD (критик-гейт Б3, 2026-08-20: буквальный прогон `sla_sweep --dry-run`/`validate_frontmatter` теперь в таблице выше). `anchor_lint.py` прогнан живьём (WARN-ярус) — `якорей 889, битых 0` — но его скоуп (`scripts/anchor_lint.py:25`, `rglob` только по `test-cases/**/*.md`) НЕ покрывает ни один артефакт этого бага (`docs/01-test-strategy.md`, `exploratory-charters/CH-010.md`, `framework/steps/settings_steps.py`); приведён здесь для полноты картины (общий индикатор здоровья якорей репо), не как подтверждение ИМЕННО этих 9 якорей — та работа сделана только Read-сверкой выше. Пробел скоупа уже зарегистрирован отдельно: `ANCHOR-LINT-SCOPE-AND-SEMANTIC-DRIFT-GAP` (`state/escalations.md`).

## Обсуждение

**2026-08-15 — test-designer, заведение и фикс одним ходом (rework по
критику, task_id CH-010-followup3-methodology).** Критик вернул FAIL с
двумя блокерами: (1) закрытие followup_tc#3 невидимо машине без id-токена;
(2) сама методическая формулировка неверна по коду. Оба устранены этим же
ходом: `docs/01-test-strategy.md` §9 переписан (материализация ключа —
только фактическое переключение, ссылка на код исправлена `:538-539` →
`:593-595`/`:897`, добавлена оговорка про `active_filter_profile_id` и
пробы «профиль снят»), `CH-010.md` `followup_tc[3]` несёт токен
`AT-BUG-076`. `app-under-test/` не изменён — правка целиком в `docs/` и
`bugs/`.

**2026-08-15 (координатор, приёмка round2) — статус исправлен на `Open`.**
Критик (round2) указал: `status: Fixed`, выставленный test-designer при
заведении, обходит `schemas/transitions.yaml` (`bug.initial: [Open]`,
переход `Open → Fixed` под guard `type: test_debt` легален только
`by: [test-maintainer, test-automator]` — test-designer в акторы не
входит); сиблинг `AT-BUG-070` (тот же чартер, тот же класс находки)
заведён именно `Open`. Содержательный фикс (правка `docs/01-test-strategy.md`
§9) уже В ДЕРЕВЕ и верифицирован критиком построчно по коду приложения —
переоткрывать его не нужно; но формальный переход `Open → Fixed` обязан
сделать актор матрицы. `awaiting: none` (не `qa`) — до перехода это ещё не
предмет верификации fix-verifier'ом. Правило B4 (`state/rules.yaml:114`,
`type: test_debt И status: Open` → `test-maintainer`) штатно подберёт эту
запись следующим срабатыванием; ожидаемое действие test-maintainer —
короткая сверка (тем же прогоном `sla_sweep.py --dry-run` +
`validate_frontmatter.py`, оба уже зелёные) и перевод `Open → Fixed`
без повторной содержательной правки.

**2026-08-18 — test-maintainer, короткая сверка (B4, task_id
AT-BUG-076-verify).** Выполнены оба скрипта из «Критерия готовности»:
`python scripts/sla_sweep.py --dry-run` → `sla_sweep: действий: 0
(dry-run)` (эскалация `CH-010:followup_tc#3` НЕ показана — id-токен
`AT-BUG-076` в `followup_tc[3]` гасит её штатно); `python
scripts/validate_frontmatter.py` → `ошибок 0, предупреждений 0`. Оба
зелёные.

Сверка формулировки §9 по коду (только чтением, `app-under-test/` не
трогал): `SettingsScreen.kt:593-595` (`setAutoApplyFilter`, пишет
`prefs.edit().putBoolean("auto_apply_filter", enabled)`), `:897`
(`onCheckedChange = { viewModel.setAutoApplyFilter(it) }`), `:201`
(`prefs.getBoolean("auto_apply_filter", true)`, только чтение) — ВСЕ
ТРИ ссылки на `SettingsScreen.kt` совпадают с текущим кодом ТОЧНО.

Но два из трёх ссылок на framework-слой, названных в самом DoD этой
сверки, УСТАРЕЛИ (номера строк уехали после того, как заметка была
написана 2026-08-15 — методика/содержание остаются верными, разъехались
только номера строк):
- `docs/01-test-strategy.md:1567` ссылается на `BrowserViewModel.kt:
  590-596` для логики `remove("active_filter_profile_id")` при снятии
  профиля. В ТЕКУЩЕМ дереве строки 590-596 — это `setAutoApplyFilter`/
  `getActiveFilterQueryString` (другой код); реальная функция
  `setActiveFilter` с `remove("active_filter_profile_id")` теперь на
  `:599-605` (сама логика — точь-в-точь как описано в заметке, просто
  сдвинулась). Причина сдвига: коммит `aa377e0` в `app-under-test`
  («Fix undo-at-ceiling, infinite-scroll navigation traps, and
  copy-URL guard», 2026-08-16 12:43:21 +0200) — landed НА СЛЕДУЮЩИЙ
  ДЕНЬ после того, как правка заметки (2026-08-15) уже сослалась на
  старые номера строк того же файла.
- `docs/01-test-strategy.md:1574-1575` ссылается на
  `framework/screens/settings_screen.py:228-233` для
  `SettingsScreen.set_auto_apply_filter`. В ТЕКУЩЕМ дереве функция
  `set_auto_apply_filter` — на `:266-271` (идемпотентная логика та же:
  тапает, только если `is_auto_apply_filter_checked() != enabled`).
  То же для `framework/steps/settings_steps.py:85` (заметка) →
  фактически `set_auto_apply_filter_toggle` на `:88`.

Содержание методической нормы (материализация ключа только фактическим
переключением; визит в Settings ничего не пишет; идемпотентность
хелпера; оговорка про `active_filter_profile_id` как якорь ТОЛЬКО для
Then «профиль применён», не для Then «профиль снят») по коду
ПОДТВЕРЖДЕНО верным — расхождение исключительно в номерах строк трёх
ссылок, не в сути нормы. По явному фокру DoD этой сверки («если
что-то расходится — не трогай статус, опиши находку, верни
blocked/failed») статус НЕ меняю (остаётся `Open`), правку
`docs/01-test-strategy.md` НЕ вношу (не мой мандат в этом ходе —
сверка заявлена read-only, «без правок»). Решение нужно от Lead: (а)
авторизовать точечную правку трёх номеров строк (`590-596`→`599-605`,
`228-233`→`266-271`, `:85`→`:88`) как тривиальную, не
«содержательную» — после чего Open→Fixed делает test-maintainer тем
же классом работы; либо (б) явно подтвердить, что дрейф номеров строк
не блокирует Fixed (суть нормы кодом подтверждена), и тогда
test-maintainer завершает переход отдельным коротким ходом без
повторной сверки скриптов.

**2026-08-18T07:45Z — координатор (sonnet, /qa-loop 5), решение по варианту (а).**
Авторизую точечную правку трёх номеров строк (`590-596`→`599-605`,
`228-233`→`266-271`, `:85`→`:88`) как тривиальную (точность ссылки,
не содержание методики — суть нормы уже подтверждена кодом этим же
ходом). test-maintainer следующим срабатыванием B4 вносит правку ТРЁХ
номеров строк (без повторной сверки sla_sweep/validate_frontmatter —
уже зелёные и не зависят от номеров строк в прозе) и делает
Open→Fixed тем же ходом.

**2026-08-19 — test-maintainer, B4 retry attempt 2 (task_id AT-BUG-076-B4).**
`app-under-test` продолжал двигаться между 2026-08-18 (прошлая сверка) и
сейчас — номера строк, которые тогда «уже подтверждены точно» для
`SettingsScreen.kt` (`593-595`/`897`/`201`), к этому ходу ТОЖЕ уехали.
Дословная сверка ТЕКУЩЕЙ ревизии `app-under-test` (только чтением, не
трогал):

- `SettingsScreen.kt`: `setAutoApplyFilter` теперь `:599-601` (было
  `593-595`), вызов из `onCheckedChange` теперь `:903` (было `897`),
  чтение `prefs.getBoolean("auto_apply_filter", true)` теперь `:207`
  (было `201`).
- `BrowserViewModel.kt`: `setActiveFilter` (с `remove(
  "active_filter_profile_id")`) теперь `:746-752` (авторизованная
  правка (а) метила `599-605` — эта цифра тоже успела устареть до
  применения).
- `framework/screens/settings_screen.py`: `set_auto_apply_filter` теперь
  `:267-272` (авторизованная правка метила `266-271` — тоже на 1 строку
  разъехалось).
- `framework/steps/settings_steps.py`: `set_auto_apply_filter_toggle`
  осталась на `:88` — совпадает с авторизованной правкой, без изменений.

Обновлены ВСЕ 6 ссылок (не только 3 изначально авторизованных) — тот
же класс работы (точность номера строки, содержание нормы НЕ менялось),
явно предписано DoD этого хода читать ТЕКУЩУЮ ревизию, а не доверять
старым номерам из бага. Правка внесена в `docs/01-test-strategy.md` §9
(6 ссылок) и `exploratory-charters/CH-010.md` `followup_tc[3]` (2 из тех
же ссылок дублировались там же текстом). `app-under-test/` не
трогал.

Id-токен `AT-BUG-076` уже присутствовал в `followup_tc[3]` с
2026-08-15 (заведение) — `FOLLOWUP_TC_ID_RE` его распознаёт.
`python scripts/sla_sweep.py --dry-run` → `sla_sweep: действий: 0
(dry-run)`, эскалация `CH-010:followup_tc#3` не показана (грепом
`state/escalations.md` по `CH-010` — единственное совпадение того же
чартера уже `resolved:CH-010-new-risks-R09`, другой followup_tc, не
#3). `python scripts/validate_frontmatter.py` → `ошибок 0,
предупреждений 0`. Перевожу `Open → Fixed` (guard `type: test_debt`,
B4, `schemas/transitions.yaml:102-104`), снимаю lock.

**[qa @ 2026-08-19T23:20:00Z] Критик-поправка (критик-вход приёмки).**
Содержание нормы и переход Open→Fixed критик подтвердил перепрогоном
(sla_sweep --dry-run, validate_frontmatter — оба зелёные, номера строк
сверены дословно). 3 блокера — соседи той же поверхности, не пройдены
этим ходом: тот же буллет-блок §9 (`docs/01-test-strategy.md:1573-1594`)
нёс ЕЩЁ 5 протухших якорей того же класса (`BrowserScreen.kt`,
`BrowserViewModel.onPageLoaded`/`applyFilter`, `SettingsScreen.kt`
дефолт тумблера, `MainActivity.kt` LaunchedEffect) — исправлены
координатором тем же ходом; второй носитель того же якоря,
`framework/steps/settings_steps.py:90` (докстринг цитировал
`MainActivity.kt:176-178`) — тоже исправлен. Класс («якорь `file:line`
молчит на смысловом дрейфе, `anchor_lint.py` скана `docs/`/
`exploratory-charters/` не имеет и смыслового дрейфа не ловит по
построению») — в очередь Lead, `ANCHOR-LINT-SCOPE-AND-SEMANTIC-DRIFT-GAP`
в `state/escalations.md`.

**[fix-verifier @ 2026-08-20T04:10:00Z] Verified (D1, doc-only carve-out).**
Независимая сверка ВСЕХ 9 якорей §9 + докстринга `settings_steps.py:90`
дословным `Read` актуального `app-under-test` дерева (HEAD
`fdd3f72884105d1453448e0c9a7f2b109588b182`, 2026-08-19T19:12:30+02:00) —
100% совпадение, ноль рассинхронов:
- `SettingsScreen.kt:82` → `val autoApplyFilter: Boolean = true` ✓
- `SettingsScreen.kt:599-601` → `setAutoApplyFilter` (пишет
  `putBoolean("auto_apply_filter", enabled)`) ✓
- `SettingsScreen.kt:903` → `onCheckedChange = { viewModel.setAutoApplyFilter(it) }` ✓
- `SettingsScreen.kt:207` → `prefs.getBoolean("auto_apply_filter", true)` (только чтение) ✓
- `BrowserScreen.kt:687-697` → `shouldOverrideUrlLoading`, `:690` guard
  `FILTERABLE_PAGE.containsMatchIn(url) && !url.contains("work_search")`,
  `:697` `view.post { view.loadUrl(filteredUrl) }` ✓
- `BrowserViewModel.kt:1182` → `stripDisplayParams` ✓
- `BrowserViewModel.kt onPageLoaded:636`, `:669-671` → ветка
  `if (!autoApplyFilter && activeFilterId != null) { if (pending) ... else setActiveFilter(null) }` ✓
- `BrowserViewModel.kt applyFilter:754`, `:768` →
  `if (!autoApplyFilter) pendingFilterApplication = true` ✓
- `BrowserViewModel.kt:746-752` → `setActiveFilter`, `remove("active_filter_profile_id")` при `id == null` ✓
- `MainActivity.kt:229-230` → `LaunchedEffect(settingsUiState.autoApplyFilter) { browserViewModel.setAutoApplyFilter(...) }` ✓
- `settings_screen.py:267-272` → `set_auto_apply_filter`, идемпотентный тап ✓
- `settings_steps.py:88`/`:90` → `set_auto_apply_filter_toggle`, докстринг
  цитирует `MainActivity.kt:229-230 LaunchedEffect` — совпадает ✓

`python scripts/anchor_lint.py` → `anchor_lint: якорей 889, битых 0`
(WARN-ярус, приложен как требовалось, не блокирует). Ни одного нового
рассинхрона не найдено — правка test-maintainer (2026-08-19) держится.
Замена device-прогону — doc-only carve-out (см. «Верификация» выше),
`app-under-test/` не трогал. `status: Fixed → Verified`, `known_issue`
уже `"false"`, lock снят.

## Чек-лист качества
- [x] Проверены дубликаты среди открытых test_debt-багов по теме CH-010 —
      не совпадает с `AT-BUG-070` (followup_tc#2, другой класс — недостающий
      наблюдательный примитив адресации вкладок, не методическая заметка).
- [x] Суть долга ясна и воспроизводима: сравнение прежней/новой
      формулировки заметки `docs/01-test-strategy.md` §9 + номера строк кода
      (`SettingsScreen.kt:593-595`/`:897`/`:201`,
      `settings_screen.py:228-233`, `BrowserViewModel.kt:590-596`).
- [x] Severity: minor — методический пробел, не блокирует ни один
      существующий кейс (`test_cases: []`), фикс уже применён.
- [x] Ни одно изменение не внесено в `app-under-test/`.
- [x] `test_cases: []` — долг не блокирует ни один существующий TC (норма
      адресует БУДУЩИЕ Data Setup чартеров/спек области filter-profiles).
