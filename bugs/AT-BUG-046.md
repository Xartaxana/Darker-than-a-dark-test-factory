---
id: AT-BUG-046
title: "seed_db.py не даёт прямого сидинга комбинированных baseline-строк work_ratings (comment+tags+downloadPath; rating=null+downloadPath), а read_work_ratings() не отдаёт title/author/downloadPath — TC-151/152/155/156 вынуждены строить состояние дверями приложения"
type: test_debt
debt_kind: missing_fixture
severity: minor
status: Fixed
found_in: "test-designer, дизайн follow-up exploratory-charters/CH-008.md (кандидаты followup_tc 1 и 4-5); признак — CH-007 и CH-008 независимо просили то же самое (рецидив без бага, CH-008.md Follow-up: «test-maintainer/test-designer: seed_db.read_work_ratings() не отдаёт title/author/downloadPath … Второй запрос: seed_db не умеет сеять baseline A и C — оба пришлось строить дверями под измерением»)"
fixed_in: "151ee6e"
last_seen_in: ""
test_cases: [TC-151, TC-152, TC-155, TC-156]
runs: [CH-007, CH-008]
duplicates: []
regression_of: ""
status_since: "2026-08-03T18:55:00Z"
updated: "2026-08-03T18:55:00Z"
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

# AT-BUG-046 — seed_db не сеет комбинированные baseline-строки work_ratings напрямую; read_work_ratings неполон

## Окружение
Долг тестовой системы (`type: test_debt`, `debt_kind: missing_fixture`) — не
зависит от сборки приложения, поверхность целиком в `framework/data/seed_db.py`.

## Суть долга

Три связанных пробела одной и той же поверхности (`framework/data/seed_db.py`),
все три уже назывались прозой в follow-up двух эксплораторных чартеров
(CH-007, CH-008) без машиночитаемого артефакта — ровно класс, о котором
предупреждает CLAUDE.md (прецедент AT-BUG-004/005/006: «блокеры жили
заметками с 2026-07-02, заведены багами только 2026-07-08/09»):

1. **`read_work_ratings()` (`:234-`) не отдаёт `title`/`author`/
   `downloadPath`** — `SELECT` (`:253-255`) явно перечисляет
   `ao3Id, rating, comment, tags, fandom, wordCount`, пропуская три поля.
   Любой кейс, ассертящий сохранность ВСЕХ полей строки `work_ratings`
   (downloadPath/title/author survive-checks — TC-151/152/155/156) вынужден
   писать собственный SELECT в обход этой функции (как это делали
   эксплораторные пробы CH-007/CH-008), вместо переиспользования готового
   framework-примитива.
2. **Нет прямого сидинга baseline «comment+tags+downloadPath одновременно»**
   (CH-008 baseline A): `seed_with_comment`/`_insert_rows_full` (`:172-193`)
   пишут `comment`/`tags`, но `downloadPath` жёстко `None` (`:190`);
   `seed_with_download`/`_insert_rows_with_download` (`:374-388`) пишут
   `downloadPath`, но `comment`/`tags` жёстко `None` (`:385`). Обе функции
   идут `INSERT OR REPLACE` на одну строку — композиция вызовов взаимно
   разрушительна (докстринг `framework/tests/conftest.py:313-318` уже
   предупреждает об этом на уровне комментария, но обходного пути не даёт).
3. **Нет прямого сидинга baseline «rating=null+downloadPath»** (CH-008
   baseline C): `seed_with_download` типизирована как `rating: str` (не
   `str | None`), а `_insert_rows_with_download` жёстко ассертит `rating in
   _RATING_ENUM` (`:379`) — `None` эту проверку не проходит; единственная
   функция, допускающая `rating=None` (`_insert_rows_full`), не принимает
   `downloadPath`.

Следствие: любой design/automation, которому нужна строка с
`comment`+`tags`+`downloadPath` одновременно ИЛИ `rating=null`+
`downloadPath`, вынужден строить состояние ДВЕРЯМИ приложения (панель/overlay)
поверх базового сидинга — то есть тест, ассертящий сохранность полей ПОСЛЕ
двери X, зависит от корректности ДРУГОЙ двери Y для собственного сетапа. Это
не только неудобно, но и хрупко: если дверь Y когда-нибудь сама станет
предметом регрессии, сломается сетап теста, проверяющего дверь X.

## Критерий готовности (Fixed)

- [x] `read_work_ratings()` (или новая функция рядом) отдаёт полный набор
  полей строки `work_ratings`, включая `title`/`author`/`downloadPath`, без
  изменения существующей сигнатуры/потребителей TC-021 (backup/restore).
  Реализовано НОВОЙ функцией `read_work_ratings_full()` (+ приватный
  `_read_full_rows(db)`, вынесенный для device-free юнитов) — `read_work_ratings()`
  не тронута ни на строку, чтобы не сломать `backup_steps.
  assert_restored_fields_match` (сравнение `actual != expected` по фиксированному
  набору из 5 ключей).
- [x] Добавлена функция сидинга (или расширена существующая), принимающая ОДНОЙ
  строкой `comment`+`tags`+`downloadPath` вместе (baseline A CH-008).
  Реализовано `seed_with_comment_and_download()` (+ `_insert_rows_full_with_download`).
- [x] Добавлена функция сидинга (или расширена существующая), принимающая
  `rating=None` вместе с `downloadPath` (baseline C CH-008) — без нарушения
  `_RATING_ENUM`-инварианта для непустых значений. Закрыто ТОЙ ЖЕ функцией
  `seed_with_comment_and_download()` — `rating` в её сигнатуре опционален
  (`str | None`), assert `rating is None or rating in _RATING_ENUM` пропускает
  `None`, но по-прежнему ассертит непустой мусор (юнит-проба ниже). Одна
  функция закрывает обе грани (A и C), т.к. обеим нужно одно и то же:
  `downloadPath` независим от `comment`/`tags`/`rating`.
- [ ] TC-151/152/155/156 (или их автоматизированные версии) используют новые
  примитивы вместо построения baseline дверями приложения, где это возможно
  без потери сути проверяемого сценария. **Вне мандата этого фикса** (кейсы —
  Review, не Automated; их automation ведёт test-automator/test-designer, не
  test-maintainer, D-0037 — scope не расширяется); примитивы готовы к
  переиспользованию.
- [x] `arch_check.py`/`validate_frontmatter.py` — 0/0 после правок.
- [x] Ни одно изменение не внесено в `app-under-test/` (`git status --porcelain
  -- app-under-test/` — пусто, сверено).

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| 2026-08-03 | ao3_test_api34, emulator-5554, no app rebuild (framework-only) | device-free: `test_seed_db_full_baseline_unit.py` (5 новых юнитов) — 3x подряд PASS (14, 5, 5 passed — первый прогон вместе с `test_seed_null_wordcount_unit.py`/`test_seed_db_schema_race_unit.py`/`test_seed_filter_profiles_unit.py`, далее только новый файл); live: `test_seed_db_full_baseline_live.py::test_seed_with_comment_and_download_baseline_a_and_c_round_trip` — 3x подряд PASS (68.45s, 8.04s, 7.61s); существующие потребители: TC-021 (`test_backup_restore.py`) — 3x подряд PASS (75.98s/74.08s/71.17s); TC-141 (`test_rating.py::test_edit_tag_on_already_saved_work_via_panel_does_not_click_kudos`) — 3x подряд PASS (45.60s/47.06s/45.68s) | Все зелёные, все PYTEST_EXIT=0 | test-maintainer: механизм закрыт, ждёт critic-вход (правило CLAUDE.md — ядровая логика сидинга, тот же класс, что AT-BUG-044) |

## Обсуждение

**[test-designer @ 2026-08-03T18:30:00Z]**

Заведено при проектировании regression-lock кейсов TC-151/152/155/156
(follow-up `exploratory-charters/CH-008.md`, кандидаты 1 и 4-5 `followup_tc`)
по правилу CLAUDE.md/D-0043 «чини класс, а не экземпляр» — блокер, названный
в «Заметках для автоматизации» кейса, обязан получить машиночитаемый артефакт
в ТОМ ЖЕ ходе, а не остаться прозой (прецедент AT-BUG-004/005/006, на который
прямо указывает workflow test-designer). CH-007 (2026-08-02) и CH-008
(2026-08-03) независимо друг от друга просили то же самое дважды — это и есть
рецидив, который правило требует не повторять в третий раз.

Awaiting: none (test_debt, не требует ответа dev).

**[test-maintainer @ 2026-08-03T18:55:00Z]**

Фикс (`151ee6e`, `framework/data/seed_db.py`):

1. **`read_work_ratings_full()`** (+ приватный `_read_full_rows(db: Path)`) —
   НОВАЯ функция рядом с `read_work_ratings()`, не расширение её сигнатуры.
   `read_work_ratings()` осталась НЕТРОНУТОЙ: она — фиксированный контракт
   `backup_steps.assert_restored_fields_match`/TC-021 (сравнение `actual !=
   expected` по РОВНО 5 ключам); добавление title/author/downloadPath в её
   возврат сломало бы это сравнение первым же прогоном TC-021 (проверено живым
   прогоном — см. таблицу верификации, TC-021 зелёный 3x после фикса, то есть
   старый контракт действительно не тронут). `_read_full_rows` вынесен
   отдельно от pull-обёртки специально, чтобы device-free юниты вызывали
   РЕАЛЬНЫЙ код разбора строки (SQL + JSON tags) на временной локальной
   sqlite-БД, не подделывая сам хелпер и не трогая устройство.
2. **`seed_with_comment_and_download()`** (+ приватный
   `_insert_rows_full_with_download`) — ОДНА функция закрывает ОБЕ грани
   долга (baseline A и C), потому что обеим нужно одно и то же свойство:
   `downloadPath` независим от `comment`/`tags`/`rating`. Сигнатура строки:
   `(work, rating: str | None, comment: str | None, tags: str | None,
   local_html_path: Path)`. `rating=None` легален (baseline C,
   `assert rating is None or rating in _RATING_ENUM` — тот же паттерн, что
   `_insert_rows_full`), непустой мусор по-прежнему ассертится (юнит
   `test_garbage_rating_still_asserted`). Существующие `seed_with_comment`/
   `seed_with_download`/`_insert_rows_full`/`_insert_rows_with_download` НЕ
   изменены — новая функция ДОПОЛНЯЕТ, не заменяет (для строк, которым не
   нужны оба поля сразу, дешевле пользоваться прежними хелперами).

Ассерт по третьему чекбоксу (TC-151/152/155/156 переходят на новые
примитивы) — вне мандата test-maintainer (D-0037): кейсы в `Review`, их
automation — работа test-automator/test-designer при следующем проходе;
здесь только сняты примитивы-блокеры, названные в их «Заметках для
автоматизации».

**Живая верификация:** `seed_with_comment_and_download` засеяла ОДНИМ вызовом
две работы — baseline A (`rating=SAVE`, `comment`, `tags=["tagA","tagB"]`,
`downloadPath`) и baseline C (`rating=None`, `comment`, `downloadPath`) — на
`emulator-5554`; `read_work_ratings_full()` прочитала обе строки назад с ВСЕМИ
полями совпавшими (title/author/fandom/word_count/rating/comment/tags/
downloadPath), 3 прогона подряд, без флейка (68s/8s/8s — первый прогон
дороже за счёт холодного `pm clear`/`am start -W`, воспроизводимо). Параллельно
`read_work_ratings()` (старая функция) сверена на том же прогоне — её ключи
остались РОВНО тем же 5-элементным набором, что до фикса.

## Чек-лист качества (заводящий проходит перед публикацией)
- [x] Проверены дубликаты среди открытых test_debt — не пересекается с
  `AT-BUG-032`/`AT-BUG-045` (другая поверхность: `adb`/pid-проверки и
  Then-ассерты `settings_steps.py`, не сидинг `work_ratings`); с `AT-BUG-004`/
  `AT-BUG-005` (replay-инфраструктура и SAF, уже Verified, другой класс)
- [x] Severity обоснована влиянием: minor — не блокирует НИКАКОЙ прогон
  (обходной путь — построение дверями — работает и уже использовался
  эксплораторными сессиями), но повышает хрупкость и объём работы будущей
  автоматизации TC-151/152/155/156
- [x] Приложены материалы: точные строки `seed_db.py` (172-193, 234-255,
  374-388), дословные цитаты follow-up CH-007/CH-008
- [x] Нет изменений кода приложения
