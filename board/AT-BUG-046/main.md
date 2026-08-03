---
key: "AT-BUG-046"
project: "AO3"
issueType: "bug"
status: "bug-open"
priority: "p2"
summary: "seed_db.py не даёт прямого сидинга комбинированных baseline-строк work_ratings (comment+tags+downloadPath; rating=null+downloadPath), а read_work_ratings() не отдаёт title/author/downloadPath — TC-151/152/155/156 вынуждены строить состояние дверями приложения"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "test_case:TC-151", "test_case:TC-152", "test_case:TC-155", "test_case:TC-156", "run:CH-007", "run:CH-008", "sev:minor"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-03T18:30:00Z"
updated: "2026-08-03T18:30:00Z"
archived: false
resolution: null
---

# seed_db.py не даёт прямого сидинга комбинированных baseline-строк work_ratings (comment+tags+downloadPath; rating=null+downloadPath), а read_work_ratings() не отдаёт title/author/downloadPath — TC-151/152/155/156 вынуждены строить состояние дверями приложения

_Спроецировано из `bugs/AT-BUG-046.md` (источник правды).
Статус в нашей машине: **Open**._

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

- [ ] `read_work_ratings()` (или новая функция рядом) отдаёт полный набор
  полей строки `work_ratings`, включая `title`/`author`/`downloadPath`, без
  изменения существующей сигнатуры/потребителей TC-021 (backup/restore).
- [ ] Добавлена функция сидинга (или расширена существующая), принимающая ОДНОЙ
  строкой `comment`+`tags`+`downloadPath` вместе (baseline A CH-008).
- [ ] Добавлена функция сидинга (или расширена существующая), принимающая
  `rating=None` вместе с `downloadPath` (baseline C CH-008) — без нарушения
  `_RATING_ENUM`-инварианта для непустых значений.
- [ ] TC-151/152/155/156 (или их автоматизированные версии) используют новые
  примитивы вместо построения baseline дверями приложения, где это возможно
  без потери сути проверяемого сценария.
- [ ] `arch_check.py`/`validate_frontmatter.py` — 0/0 после правок.
- [ ] Ни одно изменение не внесено в `app-under-test/`.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|

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
