---
key: "AT-BUG-040"
project: "AO3"
issueType: "bug"
status: "bug-verified"
priority: "p1"
summary: "scripts/sla_sweep.py::apply_pingpong_block и scripts/stale_locks.py::_clear_lock: EOL-перегон + stale_locks несёт живой data-loss (жадный regex без границы frontmatter)"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "sev:major"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-02T02:41:00Z"
updated: "2026-08-02T02:41:00Z"
archived: false
resolution: "done"
---

# scripts/sla_sweep.py::apply_pingpong_block и scripts/stale_locks.py::_clear_lock: EOL-перегон + stale_locks несёт живой data-loss (жадный regex без границы frontmatter)

_Спроецировано из `bugs/AT-BUG-040.md` (источник правды).
Статус в нашей машине: **Verified**._

# AT-BUG-040 — sla_sweep/stale_locks: EOL-перегон + живой data-loss в stale_locks

## Окружение
Долг тестовой системы (`type: test_debt`; `debt_kind: flaky_test` — та же категория, что `AT-BUG-038`, того же класса писателей frontmatter). severity **major**, не minor как у `AT-BUG-038`: `stale_locks.py::_clear_lock` несёт не только EOL-перегон, но и ДОКАЗАННЫЙ путь потери данных (см. ниже), причём на скрипте, выполняющемся как pre_step №1 КАЖДОГО прохода `/qa-loop`.

## Суть долга

Класс — тот же, что `bugs/AT-BUG-038.md` (писатели полей frontmatter, не переведённые на образец `gitlab_sync.py::writeback_gitlab_issue`), но AT-BUG-038 закрыл только `board_sync.py`/`board_inbound.py` по своему явному DoD. Критик-вход её D1-верификации прошёл ось `scripts/` целиком и нашёл два непочиненных живых собрата — оба пишут именно артефакты (не конфиг), оба доказаны эмпирически на реальных данных репозитория:

### `scripts/sla_sweep.py::apply_pingpong_block` (строки ~268-280)
`read_text`/`write_text` — под `core.autocrlf=true` маскируется, на чисто-LF артефакте перегоняет ВЕСЬ файл в CRLF (доказано: `CRLF count: 16` на тестовом чисто-LF артефакте). Дополнительно: эта функция ВЫЗЫВАЕТ `board_inbound._rewrite_field`/`_set_field` — то есть уже частично унаследовала AT-BUG-038-фикс границы frontmatter (класс 2 там починился попутно), но сама точка входа (`read_text`/`write_text`) осталась незамкнутой в байтовый режим.

### `scripts/stale_locks.py::_clear_lock` (строки ~114-121) — ЖИВОЙ DATA-LOSS
`read_text` + `re.subn(r'(?m)^lock:\s*.*$', ...)` по ВСЕМУ тексту файла (без границы frontmatter, класс 2 AT-BUG-038) + `write_text` (класс 1). Жадный `\s*.*$` без границы демонстрирует РЕАЛЬНУЮ потерю данных, не только теоретический риск:

```
до:    lock:\n\nextra_field: keepme\n---
после: lock: ""\n---
```

Строка `extra_field: keepme` УДАЛЯЕТСЯ. Путь срабатывает, когда протухший лок НЕПУСТОЙ (штатное условие функции — она чистит именно протухшие непустые локи), а следующее поле frontmatter лежит достаточно близко, чтобы жадный `.*$` его поглотил через `\s*` многострочного `(?m)`-режима (переносы строк матчятся `\s`).

**Достижимость — не гипотетическая.** `stale_locks.py` — pre_step №1 в `state/rules.yaml:25` и `.claude/skills/qa-loop/SKILL.md:80` — выполняется на КАЖДОМ проходе `/qa-loop`, безусловно. На момент находки 64 из 197 артефактов репозитория — чисто-LF (измерено критиком). EOL-перегон при этом реален уже сегодня на этой платформе, не только на гипотетическом клоне с `autocrlf=false`.

## Образец правильной реализации
`scripts/gitlab_sync.py::writeback_gitlab_issue` (как и у `AT-BUG-038`): `read_bytes`/`write_bytes`, `eol` по факту исходного файла, replace-or-insert строго в срезе тела frontmatter (`FRONTMATTER_RE`/`_frontmatter_body_span`, образец уже есть в `board_sync.py`/`board_inbound.py` после фикса `AT-BUG-038`).

## Критерий готовности (Fixed)

- [x] `scripts/sla_sweep.py::apply_pingpong_block` переведён на read_bytes/write_bytes (образец `gitlab_sync.py`/`board_inbound.py` после AT-BUG-038).
- [x] `scripts/stale_locks.py::_clear_lock` переведён на read_bytes/write_bytes + ограничен телом frontmatter (переиспользован `board_sync.py::_subn_frontmatter_field`, тот же образец, что и AT-BUG-038) + жадный `\s*.*$` заменён на `[^\r\n]*` (не поглощает соседние строки/переносы).
- [x] Новый байтовый тест воспроизводит ИМЕННО демонстрированный data-loss сценарий (непустой протухший `lock:` + соседнее поле `extra_field`) — до фикса тест падает (соседнее поле теряется), после — проходит (поле сохраняется).
- [x] Новые байтовые LF/CRLF-тесты по образцу `scripts/tests/test_board_writeback_eol.py` для обеих функций.
- [x] Существующие тесты `scripts/tests` зелёные (полный набор, без регресса).
- [x] arch_check/validate_frontmatter — 0/0.
- [x] Ни одно изменение НЕ вносится в `app-under-test/`.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| 2026-08-02 | device-free (framework/scripts only, app-under-test не тронут) | `python -m pytest scripts/tests -q` (809 passed, 1 skipped, 0 failed); новый регресс-тест `scripts/tests/test_at_bug_040_eol.py::test_clear_lock_data_loss_regression_at_bug_040` подтверждённо ПАДАЛ на pre-fix коде (`AssertionError: assert 'extra_field: keepme' in '---\r\nid: BUG-999\r\nlock: ""\r\n---\r\n\r\n# BUG-999\r\n\r\nbody\r\n'`) и ПРОШЁЛ после фикса; `test_clear_lock_byte_exact_eol_preserved[LF]` также падал pre-fix (перегон на CRLF: `b'\r' not in b'---\r\nid: TC-950\r\n...'` — assertion failed) и прошёл post-fix; `arch_check.py` → `ошибок 0, предупреждений 0`; `validate_frontmatter.py` → `ошибок 0, предупреждений 0` | test-maintainer (Sonnet), самопрогон DoD |
| 2026-08-02 | device-free, независимая верификация fix-verifier (Sonnet), рабочее дерево поверх HEAD=027681e, `app-under-test/` не тронут | (a) `test_cases: []` — carve-out для `type: test_debt` в обвязке (scripts/, без привязываемых TC), DoD-демонстрация исполнена буквально; (b) полный `powershell -NoProfile -ExecutionPolicy Bypass -Command ". D:\AO3_tests\scripts\tasks.ps1; Invoke-Pytest ../scripts/tests -q"` → `809 passed, 1 skipped in 26.98s`, `PYTEST_EXIT=0`; (c) изолированный `Invoke-Pytest ../scripts/tests/test_at_bug_040_eol.py -v` → все 5 поимённо: `test_apply_pingpong_block_byte_exact_eol_preserved[LF]` PASSED, `[CRLF]` PASSED, `test_clear_lock_byte_exact_eol_preserved[LF]` PASSED, `[CRLF]` PASSED, `test_clear_lock_data_loss_regression_at_bug_040` PASSED — `5 passed in 1.72s`; (d) КОНТРОЛЬНАЯ ПРОБА (не переиспользован вывод test-maintainer): вытянул pre-fix `_clear_lock` буквально из `git show HEAD:scripts/stale_locks.py` (текущий рабочий файл не закоммичен — HEAD ещё несёт баг-версию `re.subn(r'(?m)^lock:\s*.*$', ...)` + `read_text`/`write_text`), скопировал в scratch-скрипт и прогнал на артефакте `b'---\nid: BUG-999\nlock:\n\nextra_field: keepme\n---\n\n# BUG-999\n\nbody\n'` — результат `'---\nid: BUG-999\nlock: ""\n---\n\n# BUG-999\n\nbody\n'`, `extra_field present: False` (данные потеряны, подтверждено самостоятельно); тот же артефакт через живой импорт `import stale_locks as sl; sl._clear_lock(...)` текущего (пост-фикс) кода → `'---\nid: BUG-999\nlock: ""\n\nextra_field: keepme\n---\n\n# BUG-999\n\nbody\n'`, `extra_field present: True` (сохранено); (e) `arch_check.py` → `ошибок 0, предупреждений 0`; `validate_frontmatter.py` → `ошибок 0, предупреждений 0`; (f) `git diff HEAD -- scripts/sla_sweep.py scripts/stale_locks.py` — диф ограничен ровно описанной правкой I/O (read_bytes/write_bytes, `_LOCK_FIELD_RE`/`bs._subn_frontmatter_field`), без побочных изменений; `app-under-test/` в `git status`/`git diff --stat` не фигурирует вовсе. Вердикт: все 5 DoD-пунктов критерия готовности подтверждены независимо → `Fixed → Verified`. | fix-verifier (Sonnet), независимая верификация D1 |

## Обсуждение

**2026-08-02T02:15:53Z — координатор (Sonnet), заведение по докладу критик-входа D1 AT-BUG-038:**
Критик прошёл ось `scripts/` (писатели frontmatter) целиком по докладу и нашёл эти два экземпляра эмпирически (собрал pre-fix код в scratchpad, прогнал сценарии на реальных чисто-LF артефактах). `AT-BUG-038` сам по себе закрыт корректно на своём заявленном скоупе (`board_sync.py`/`board_inbound.py`) — этот баг продолжает класс отдельным артефактом (правило 9 CLAUDE.md/D-0043), не блокирует приёмку AT-BUG-038. Severity **major** (не minor, как у AT-BUG-038) — из-за доказанного data-loss пути на критичном pre_step-скрипте, исполняемом безусловно каждым проходом конвейера. Диспатч B4 — приоритетно (не «при следующем touch файла»: путь уже достижим сегодня).

**2026-08-02T02:26:22Z — test-maintainer (Sonnet), фикс:**
Оба сиблинга починены device-free.

1. `sla_sweep.py::apply_pingpong_block` — `read_text`/`write_text` → `read_bytes().decode("utf-8")`/`write_bytes(new.encode("utf-8"))`. Граница frontmatter (класс 2) уже была унаследована из AT-BUG-038 через вызовы `bi._rewrite_field`/`bi._set_field` — правился только I/O.
2. `stale_locks.py::_clear_lock` — байтовый I/O + замена перенесена на `board_sync.py::_subn_frontmatter_field` (уже существующий helper, введённый AT-BUG-038, ограничивающий поиск ТЕЛОМ frontmatter) с новым паттерном `_LOCK_FIELD_RE = re.compile(r"(?m)^lock:[^\r\n]*")` вместо жадного `\s*.*$`.

Регресс-тест данных потерь (`test_clear_lock_data_loss_regression_at_bug_040`) СНАЧАЛА прогнан на pre-fix коде и подтверждённо падал (`extra_field: keepme` пропадал), только затем применён фикс и тест прогнан повторно — прошёл. Байтовый LF-тест `test_clear_lock_byte_exact_eol_preserved[LF]` тоже падал pre-fix (перегон на CRLF) и прошёл post-fix. Новый тестовый файл — `scripts/tests/test_at_bug_040_eol.py` (5 тестов: 2×EOL для `apply_pingpong_block`, 2×EOL для `_clear_lock`, 1 data-loss регресс).

Полный `scripts/tests` — 809 passed, 1 skipped, без регресса. `arch_check.py`/`validate_frontmatter.py` — 0/0 оба.

Сиблинги оси `scripts/` (правило 9/D-0043): дополнительно проверены все `write_text(`-вызовы в `scripts/*.py` (кроме `tests/`) на предмет партиальной правки существующего frontmatter-артефакта. `build_watch.py::update_aut` тоже использует text-режим I/O над `state/app-under-test.yaml`, но это ЦЕЛИКОМ config-файл без markdown-тела/frontmatter-границы (тот же класс, что сам баг явно исключает формулировкой «пишут именно артефакты (не конфиг)») — не сиблинг этой оси, фиксирую как рассмотренное и осознанно не тронутое (см. `escalations` agent_output ниже). Остальные писатели (`board_view.py`, `queue_snapshot.py`, `coverage_map.py`, `board_inbound.py`/`board_sync.py` JSON-writers, `loop_lock.py::_atomic_write_text`) — либо полная регенерация файла целиком (не партиальная правка поля, риска EOL-перегона нет по конструкции), либо не frontmatter-артефакты (JSON/локи). Новых живых сиблингов не найдено.

**Поправка приёмки (координатор, 2026-08-02T02:38:33Z, критик-вход D1 fix-verifier).**
Разбор выше СМЕШИВАЛ два независимых класса этого бага: аргумент
«config-файл без frontmatter-границы» релевантен ТОЛЬКО классу 2 (граница
поиска поля), но НЕ классу 1 (EOL-перегон при партиальной правке) — вреду
класса 1 наличие frontmatter не нужно вовсе. Критик прогнал точку I/O
`build_watch.py::update_aut` (:184-197) на копии РЕАЛЬНОГО
`state/app-under-test.yaml` (сегодня чисто-LF, 13 bare-LF) — результат:
`13 CRLF`, перегон произошёл. `build_watch.py` — pre_step №3
(`state/rules.yaml:28`), `update_aut` срабатывает на каждом новом коммите
app-under-test. Заведён отдельным test_debt `bugs/AT-BUG-041.md` (severity
minor — перегон косметический, потери данных нет, в отличие от главного
предмета ЭТОГО бага). Формулировка «полная регенерация, риска нет по
конструкции» для `sla_sweep.py::rewrite_registry` (:291,324) и
`loop_lock.py::_atomic_write_text` (:176-194) ТАКЖЕ неточна — критик
показал прогоном, что обе функции партиально правят (`read_text(
splitlines(keepends))`/`write_text`), а не регенерируют целиком; на
реальном (сейчас CRLF) `state/escalations.md` перегона нет, но на LF-клоне
того же контента — есть (`CRLF=0 → CRLF=7`). Спящий сиблинг, не
отсутствующий; строка в `bugs/AT-BUG-041.md` заводит и его. Дополнительно
критик нашёл НЕ-блокирующую регрессию охвата в самом фиксе `_clear_lock`:
строгий `FRONTMATTER_RE` (введённый AT-BUG-038) больше не снимает
протухший лок, если у файла нет хвостового перевода строки перед `---`,
есть BOM, или frontmatter битый — раньше (до фикса) эти случаи хоть и
несли риск порчи соседних полей, но лок СНИМАЛСЯ; теперь лок остаётся
навсегда (прецедент класса — застрявший TC-021 до ручного вмешательства).
Сегодня 0 из 204 артефактов в этом состоянии (измерено критиком) — не
блокер приёмки, зафиксировано строкой в `bugs/AT-BUG-041.md` для будущего
касания `stale_locks.py`.

**2026-08-02T02:41:00Z — fix-verifier (Sonnet), независимая верификация D1:**
Carve-out D-0043/Lead 2026-07-29 применён явно: `type: test_debt` в обвязке `scripts/`, `test_cases: []` штатен, замена — DoD-демонстрация из «Критерий готовности» бага, исполненная буквально живым прогоном (не чтением кода). Прогнала независимо (свой вызов, не переиспользование вывода test-maintainer): полный `scripts/tests` (809 passed/1 skipped), изолированно `test_at_bug_040_eol.py -v` (все 5 поимённо), КОНТРОЛЬНУЮ ПРОБУ data-loss — pre-fix `_clear_lock` вытянут буквально из `git show HEAD:scripts/stale_locks.py` (рабочее дерево фикса ещё не закоммичено, HEAD = баг-версия), прогнан в scratch-скрипте: `extra_field` терялся; тот же артефакт через живой импорт текущего `stale_locks.py` — `extra_field` сохранён. `arch_check.py`/`validate_frontmatter.py` — 0/0. `git diff HEAD -- scripts/sla_sweep.py scripts/stale_locks.py` — диф ограничен ровно заявленной I/O-правкой, `app-under-test/` не затронут вовсе. Все 7 пунктов «Критерий готовности» подтверждены независимо → `status: Fixed → Verified`.

## Чек-лист качества (bug-reporter проходит перед публикацией)
- [x] Проверены дубликаты среди открытых test_debt: не совпадает с AT-BUG-038 (другие файлы, тот же класс — сиблинг, не дубликат), AT-BUG-039 (другая ось — framework/steps диагностика ожидания, не scripts/ writer)
- [x] Severity обоснована влиянием: major — доказанная потеря данных (не гипотеза), на критичном pre_step, достижимом сегодня (64/197 артефактов чисто-LF)
- [x] Приложены материалы: вердикт критика D1-верификации AT-BUG-038 (2026-08-02), включая воспроизведённые python-пробы на реальных данных
- [x] Нет изменений кода приложения
