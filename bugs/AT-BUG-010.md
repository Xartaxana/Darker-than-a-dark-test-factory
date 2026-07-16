---
id: AT-BUG-010
title: "seed_db.py не поддерживает NULL-значения nullable-полей при сидинге (word_count) — блокирует автоматизацию TC-031 (P3, library, граница сортировки)"
type: test_debt
debt_kind: missing_fixture
severity: minor
status: Verified
found_in: "test-designer (design-library-remainder, доклад аналога по D-0043, 2026-07-14): блокер жил заметкой в теле TC-031 с 2026-07-02 и не был заведён bug-артефактом — тот же класс пробела, что AT-BUG-004/005/006"
fixed_in: "n/a (test_debt, device-free — сборка приложения не участвует)"
last_seen_in: ""
test_cases: ["TC-031"]
runs: []
duplicates: []
regression_of: ""
status_since: "2026-07-17T00:00:00Z"
updated: "2026-07-17T00:00:00Z"
reopen_count: 0
dispute_count: 0
awaiting: none
lock: ""
---

# AT-BUG-010 — Сидинг NULL-полей не поддержан (word_count) — блокер TC-031

## Окружение
- Не зависит от сборки приложения: долг тестовой системы (`type: test_debt`,
  `debt_kind: missing_fixture`). Известен с проектирования TC-031
  (2026-07-02) как заметка в теле кейса; заведён отслеживаемым артефактом
  2026-07-14 по докладу test-designer (правило 9 CLAUDE.md: находка,
  оставленная заметкой в теле кейса, невидима правилу B4).

## Суть долга

`test-cases/library/TC-031.md` (P3, area library, risk R-06 — «работы без
word_count уходят в конец при сортировке Word count») требует засеять работу
с `word_count = NULL`. `framework/data/seed_db.py::_insert_rows` берёт
`word_count` из `Work` dataclass с дефолтом 1000 и не даёт способа передать
NULL — граничный сценарий несидируем, кейс не автоматизируем как есть.

Заметка TC-031 упоминает аналогичную зависимость `rating=NULL` для
TC-014/TC-017 (запись 2026-07-02): с тех пор появился `seed_with_comment`
(comment-only, `rating=null` — используется автоматизированным TC-017), так
что rating-грань, вероятно, уже закрыта — при взятии долга ПРОВЕРИТЬ и
зафиксировать здесь, закрыта ли она фактически, прежде чем расширять скоуп.

Заблокирован: TC-031 (P3). Новые кейсы TC-060..065 (2026-07-14) блокеров НЕ
несут (сверено test-designer'ом при их проектировании: пустая строка author —
не NULL, сидится штатно).

## Критерий готовности (Fixed)

- `seed_db.py` позволяет явную передачу NULL для nullable-колонок
  `work_ratings` (минимум `wordCount`; способ — решение исполнителя:
  sentinel/Optional в `Work` или отдельная функция), INSERT кладёт NULL,
  чтение (`read_work_ratings`) возвращает None без искажения.
- Device-free юнит-проба по образцу `test_seed_filter_profiles_unit.py`
  (вставка NULL + чтение) зелёная.
- Заметка «требует доработки seed_db.py» в TC-031 обновлена ссылкой на этот
  баг/факт закрытия.
- Smoke без регресса (или обоснованная опора на регресс юнит/затронутых проб —
  дифф device-free).

## Анализ

Класс — «граница/вариант данных не выражается сидингом» (missing_fixture),
самый младший из открытых долгов (P3-кейс против P0/P1 у AT-BUG-005/006/009).
Приоритет — после них; Fixed не ждёт сборку приложения (B4).

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| 2026-07-17 | n/a (test_debt, device-free долг — сборка приложения не участвует, эмулятор не поднимался) | Независимый прогон `tests/test_seed_null_wordcount_unit.py` (2 теста: insert кладёт NULL / INSERT OR REPLACE не искажает NULL) + `tests/test_seed_filter_profiles_unit.py` (2 теста, минимальный smoke соседнего сидинг-модуля) | `4 passed in 1.05s`, `PYTEST_EXIT=0` (см. witness ниже). Код прочитан: `Work.word_count: int \| None`, `_insert_rows` кладёт `work.word_count` напрямую bind-параметром (NULL штатно через sqlite3, без искажения в 0); проба именно это и проверяет (не мок — реальная временная sqlite-БД со схемой `work_ratings`, `assert ... is None`, отдельно проверен INSERT OR REPLACE поверх существующего значения). `read_work_ratings()` читает `row["wordCount"]` тем же способом, что проба — `sqlite3.Row` возвращает `None` для NULL-колонки нативно, отдельной обработки не требуется (частичная сверка по коду, TC-021 round-trip UI-прогоном не покрыт — не в скоупе этого долга). `test-cases/library/TC-031.md` подтверждённо обновлён ссылкой на закрытие (раздел «Заметки для автоматизации»: «Блокер снят... AT-BUG-010 → Fixed»). Побочная проверка rating=NULL (TC-014/TC-017) из «Обсуждения» подтверждена по коду и статусу артефакта: TC-017.md — `status: Automated`, `automation_status: active`. | **Verified.** Критерий готовности выполнен по всем 4 пунктам; witness — фактический независимый прогон (не переиспользование записи test-maintainer). |

## Обсуждение

**2026-07-14T18:40:00Z — Lead (Fable), заведение по докладу test-designer
(design-library-remainder):** доклад-аналог D-0043 при проектировании
TC-060..065 — блокер TC-031 жил только заметкой в теле кейса, класс тот же,
что уже закрывался для AT-BUG-004/005/006 (заметка вместо артефакта =
невидимость для B4). Диспатч — штатным B4-правилом, приоритет за
AT-BUG-005/006/009.

**2026-07-17T09:30:00Z — test-maintainer, B4 (DEVICE-FREE, эмулятор не
поднимался — задача не зависит от устройства, ESC-001 не касается):**

Фикс:
- `framework/data/works.py::Work.word_count` перетипирован `int` → `int | None`
  (дефолт не менялся, `1000`); `_insert_rows`/`seed()`/`seed_library` уже
  передавали `work.word_count` напрямую bind-параметром в
  `sqlite3.Cursor.execute` — `None` кладёт NULL штатным поведением драйвера,
  отдельная функция/ветка не понадобилась (в отличие от `rating=NULL`, которому
  нужна была отдельная `_insert_rows_full`/`seed_with_comment`, т.к. `rating`
  там ещё и валидируется по `_RATING_ENUM`). Добавлена фикстура-работа
  `works.NULL_WORD_COUNT_TARGET` (ao3Id `900000031`) для TC-031.
- Комментарии в `seed_db.py::_insert_rows` и `works.py::Work` объясняют механизм
  и явно ссылаются на это решение, чтобы не выглядело случайным дефолтом.

Проверка пункта 3 критерия (rating=NULL грань TC-014/TC-017): по чтению кода —
**закрыта, и была закрыта РАНЕЕ, независимо от этого долга.** `seed_with_comment`
(`framework/data/seed_db.py`) уже поддерживает `rating=None` через
`_insert_rows_full`; используется фикстурами `conftest.py::comment_only_work`
(TC-017, `test_library.py::test_comment_only_not_in_any_rating_tab`, автоматизирован
и `active`) и `conftest.py::placeholder_seeded_work` (TC-007). TC-014 остаётся
`Review`/заблокирован ОТДЕЛЬНОЙ причиной (replay-транспорт mitmproxy не готов,
см. историческую заметку в самом TC-014.md) — сидинг для него, по тексту того же
файла, «уже поддержан», rating=NULL там ни при чём. TC-031.md обновлён ссылкой на
этот факт.

Witness (device-free юнит-проба, 3 прогона подряд, PYTEST_EXIT=0 на каждом):
```
> powershell -NoProfile -ExecutionPolicy Bypass -Command
  ". D:\AO3_tests\scripts\tasks.ps1; Invoke-Pytest tests/test_seed_null_wordcount_unit.py tests/test_seed_filter_profiles_unit.py -q"
.... [100%]
4 passed in 0.14s   (run 1)
4 passed in 0.14s   (run 2)
4 passed in 0.15s   (run 3)
PYTEST_EXIT=0        (все три прогона)
```
Плюс `python scripts/arch_check.py` → `ошибок 0, предупреждений 0`. Полный p0
smoke НЕ гонялся — device-free дифф (изменения не касаются adb/Appium-пути,
только чистая sqlite-логика сидинга), эмулятор не поднимался (не требуется
задачей).

Замеченных аналогов/новых блокеров при работе не найдено (единственное
соседнее место с `work.word_count` в f-строке —
`framework/data/recording_builder.py` — HTML-фикстуры для replay, не участвует
в сидинге TC-031 и не вызывается с `word_count=None` ни в одном существующем
кейсе; расширять скоуп не стал, правило 9 не триггерится — не аналог этого
класса, а другой потребитель того же поля).

Open → Fixed по guard-переходу B4 (`schemas/transitions.yaml`, test_debt).
Лок снят.

**2026-07-17T00:00:00Z — fix-verifier (D1, device-free, эмулятор не
поднимался — долг чисто sqlite-логики сидинга, UI-прогона TC-031 не
существует):**

Независимый прогон:
```
> powershell -NoProfile -ExecutionPolicy Bypass -Command
  ". D:\AO3_tests\scripts\tasks.ps1; Invoke-Pytest tests/test_seed_null_wordcount_unit.py tests/test_seed_filter_profiles_unit.py -v"
tests/test_seed_null_wordcount_unit.py::test_insert_rows_null_word_count_stores_null PASSED
tests/test_seed_null_wordcount_unit.py::test_insert_rows_null_word_count_survives_replace PASSED
tests/test_seed_filter_profiles_unit.py::test_insert_rows_filter_profiles_inserts_expected_rows PASSED
tests/test_seed_filter_profiles_unit.py::test_insert_rows_filter_profiles_replaces_on_duplicate_pk PASSED
4 passed in 1.05s
PYTEST_EXIT=0
```
Критерий готовности сверен по коду (не только по проговорке из записи
test-maintainer): `works.py::Work.word_count: int | None`, `seed_db.py::
_insert_rows` кладёт значение bind-параметром — sqlite3 штатно пишет NULL;
проба реально доказывает это (временная sqlite-БД по схеме приложения,
`assert _select_word_count(...) is None`, плюс отдельный тест на INSERT OR
REPLACE поверх существующего непустого значения — NULL не «теряется» и не
подменяется 0). `read_work_ratings()` читает `row["wordCount"]` тем же
паттерном `sqlite3.Row` — None для NULL нативно, отдельной ветки не нужно
(частичная сверка по коду; TC-021 round-trip живым UI-прогоном эта
верификация не покрывает — вне скоупа device-free долга). `TC-031.md`
подтверждённо несёт ссылку на закрытие в разделе «Заметки для
автоматизации». Побочная сверка rating=NULL (TC-014/TC-017) из записи
test-maintainer подтверждена: `TC-017.md` — `status: Automated`,
`automation_status: active` (comment-only грань закрыта отдельно и раньше,
как и заявлено).

Аналогов/новых блокеров не замечено сверх того, что уже отмечено
test-maintainer (правило 9 CLAUDE.md).

Fixed → Verified. Лок снят.
