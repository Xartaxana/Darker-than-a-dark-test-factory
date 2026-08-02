---
key: "AT-BUG-038"
project: "AO3"
issueType: "bug"
status: "bug-verified"
priority: "p2"
summary: "писатели frontmatter в board-скриптах: EOL-перегон + отсутствие границы frontmatter"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "sev:minor"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-02T02:06:36Z"
updated: "2026-08-02T02:06:36Z"
archived: false
resolution: "done"
---

# писатели frontmatter в board-скриптах: EOL-перегон + отсутствие границы frontmatter

_Спроецировано из `bugs/AT-BUG-038.md` (источник правды).
Статус в нашей машине: **Verified**._

# AT-BUG-038 — долг класса EOL-перегон и отсутствия границы frontmatter

## Окружение
Долг тестовой системы (`type: test_debt`; `debt_kind: flaky_test` — класс порчи данных писателями: операционный симптом — недетерминированные полнофайловые диффы на клонах с `core.autocrlf=false` или Linux-окружениях). Не зависит от сборки приложения — фикс целиком в `scripts/`.

## Суть долга

Два класса дефекта в скриптах, которые пишут поля frontmatter артефактов:

### Класс 1 — EOL-перегон (маскируется `core.autocrlf=true`)
Писатели используют `read_text`/`write_text` (newline=None, стандартное поведение — текстовое преобразование EOL):
- `scripts/board_sync.py:~235-296` (`approve_test_case`, `set_priority`, `set_severity`)
- `scripts/board_inbound.py:~196-251` (`_replace_field`, `writeback`)

При `core.autocrlf=true` (текущее состояние в этом репо) переобразование маскируется. На клоне с `autocrlf=false` или в Linux-окружении фикс пишет ВЕСЬ файл с перегоном окончаний строк целиком (диффы становятся полнофайловыми, шумные).

### Класс 2 — отсутствие границы frontmatter
`(?m)^field:` применяется ко ВСЕМУ файлу БЕЗ ограничения телом frontmatter — может зацепить строку в теле артефакта, если там лежит совпадающий паттерн. Образец соседнего кода `board_inbound.py:203` (`_set_field`) уже несёт верный replace-or-insert контракт, но regex поиска не ограничен границей `---`.

### Образец правильной реализации обоих классов
`scripts/gitlab_sync.py::writeback_gitlab_issue`:
- `read_bytes`/`write_bytes` (байтовый режим, точный контроль EOL)
- `eol` переопределяется ПО ФАКТУ (вычисляется из первой найденной последовательности в исходном файле)
- replace-or-insert строго в теле frontmatter (поиск `GITLAB_ISSUE_LINE_RE`
  ведётся по срезу `text[body_start:body_end]` — границы даёт группа 1
  `FRONTMATTER_RE`, то есть тело frontmatter ДО закрывающего `---`).
  [Правка Lead при приёмке 2026-08-02: исходная формулировка приводила
  regex `[^-]*?^---`, которого в коде нет, — экземпляр класса «haiku
  заполняет пробелы правдоподобием», п.(б) очереди калибровки №5;
  пойман приёмкой, как и оба прежних прецедента.]

## Критерий готовности (Fixed)

- [x] Оба скрипта (`board_sync.py` и `board_inbound.py`) переведены на образец `gitlab_sync.py::writeback_gitlab_issue` (read_bytes/write_bytes + eol по факту + replace-or-insert в frontmatter).
- [x] Существующие тесты `scripts/tests` зелёные (включая board-тесты, если они есть).
- [x] Новые байтовые тесты LF/CRLF по образцу `test_gitlab_sync.py` writeback-тестов (проверка сохранения EOL исходного файла).
- [x] arch_check/validate_frontmatter 0/0.
- [x] Ни одно изменение не внесено в `app-under-test/`.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| 2026-08-02 | device-free (test_debt, framework/app-under-test не при чём) | Нет живых TC — device-free фикс писателей frontmatter (`scripts/`): `python -m pytest scripts/tests -q` (полный набор, 3 прогона подряд) → `804 passed, 1 skipped in 25.23s` / `804 passed, 1 skipped in 26.19s` / `804 passed, 1 skipped in 29.47s` (0 failed во всех трёх); из них 12 новых байтовых LF/CRLF-тестов `scripts/tests/test_board_writeback_eol.py` (approve_test_case/set_priority/set_severity/apply_status/apply_conflict/append_discussion — по 2 варианта EOL, плюс проверка границы frontmatter: строка вида `status: ...`/`priority: ...`/`severity: ...` в ТЕЛЕ артефакта не тронута). `python scripts/arch_check.py` → `arch_check: ошибок 0, предупреждений 0`. `python scripts/validate_frontmatter.py` → `validate_frontmatter: ошибок 0, предупреждений 0`. `git status` подтверждает: правки только в `scripts/board_sync.py`, `scripts/board_inbound.py`, `scripts/tests/test_board_writeback_eol.py`, `bugs/AT-BUG-038.md` — `app-under-test/` не тронут. | Все зелёные, без регресса (3/3 подряд) | test-maintainer: Fixed, ждёт fix-verifier (переход Fixed→Verified не входит в мой guard) |
| 2026-08-02 | device-free (test_debt, framework/app-under-test не при чём) — НЕЗАВИСИМАЯ верификация fix-verifier, отдельный прогон | `test_cases: []` — carve-out test_debt в обвязке применён (12 новых device-free байтовых тестов заменяют TC): (1) полное чтение `scripts/board_sync.py`/`scripts/board_inbound.py` — подтверждено: оба используют `read_bytes().decode("utf-8")`/`write_bytes(...encode("utf-8"))`, `FRONTMATTER_RE = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)`, поиск/замена полей строго в срезе `text[start:end]` тела frontmatter (`_subn_frontmatter_field`/`_rewrite_field`/`_set_field`), новый EOL для вставляемых строк — по факту (`_file_eol`, `"\r\n" if text[insert_at:insert_at+2]=="\r\n" else "\n"`) — соответствует образцу `gitlab_sync.py::writeback_gitlab_issue` буквально; (2) свой прогон `powershell -NoProfile -ExecutionPolicy Bypass -Command ". D:\AO3_tests\scripts\tasks.ps1; Invoke-Pytest ../scripts/tests -q"` → `804 passed, 1 skipped in 25.41s` / `PYTEST_EXIT=0` (0 failed, независимый от самопрогона test-maintainer); (3) отдельно `-v` только на новом файле → все 12 кейсов поимённо PASSED: `test_approve_test_case_byte_exact_eol_preserved[LF/CRLF]`, `test_set_priority_byte_exact_eol_preserved[LF/CRLF]`, `test_set_severity_byte_exact_eol_preserved[LF/CRLF]`, `test_apply_status_byte_exact_eol_preserved[LF/CRLF]`, `test_apply_conflict_byte_exact_eol_preserved[LF/CRLF]`, `test_append_discussion_new_content_matches_file_eol[LF/CRLF]` — `12 passed in 1.69s`; (4) `python scripts/arch_check.py` → `ошибок 0, предупреждений 0`; `python scripts/validate_frontmatter.py` → `ошибок 0, предупреждений 0`; (5) `git diff --stat` этой сессии: изменения по этому багу ограничены `scripts/board_sync.py` (+85/-…), `scripts/board_inbound.py` (+105/-…), новый `scripts/tests/test_board_writeback_eol.py`, `bugs/AT-BUG-038.md`; `git status -- app-under-test/` — пусто (не тронут). Замечены ПОСТОРОННИЕ незакоммиченные правки в рабочем дереве (`bugs/AT-BUG-035.md`, `bugs/AT-BUG-036.md`, `bugs/AT-BUG-037.md`, `exploratory-charters/PERTURBATIONS.md`, `exploratory-charters/CH-008.md` (new), `logs/routing-log.jsonl`, `state/orchestrator-log.md`, `state/board-cursor.json`) — это ШУМ от параллельной работы (gitlab-bugs-publish и др. сессии), НЕ часть диффа этого бага и не app-under-test; после независимого прогона `git status` на них не сдвинулся (пересборки board-cursor.json моим прогоном не было — REPO-монкипатч тестов на tmp_path подтверждён изолированным). | Всё зелёное, регрессов нет; независимый прогон совпадает с самопрогоном test-maintainer (804/1 skipped) | fix-verifier: Fixed → Verified. Лок снят. |

## Обсуждение
Канал человек ↔ фабрика.

**2026-08-02 — test-maintainer, Open → Fixed.** Оба скрипта переведены на
образец `gitlab_sync.py::writeback_gitlab_issue`: `read_bytes`/`write_bytes` +
`FRONTMATTER_RE`-граница тела frontmatter + вставка нового контента с EOL,
вычисленным по факту (символ сразу после точки вставки/файл целиком для
`append_discussion`), не жёстким `os.linesep`/`\n`. В `board_sync.py` —
`approve_test_case`/`set_priority`/`set_severity` через новый общий
`_subn_frontmatter_field`; в `board_inbound.py` — `_rewrite_field`/`_set_field`/
`_bump_reopen_count` (используются `apply_status`/`apply_conflict`) и
`append_discussion` (новый контент берёт EOL-стиль файла через `_file_eol`).

Побочная находка при реализации (не отдельный баг, тот же класс 2): первая
версия патчей использовала `[ \t]*$` для value-специфичных regex'ов
(`approve_test_case`/`set_priority`/`set_severity`/`_bump_reopen_count`/
`updated:`-паттерн) — под CRLF (как пишет `Path.write_text` на Windows, чем
пользуется фикстура `conftest.Repo`) `$` не матчился сразу после `[^\r\n]*`/
`[ \t]*`, потому что между значением и `\n` оставался непоглощённый `\r`;
поймано полным прогоном `scripts/tests` (10 упавших) ДО коммита — заменено на
lookahead `(?=\r?\n|$)` везде, где нужен якорь конца значения; `[^\r\n]*` без
`$` (как в `_rewrite_field`) якоря не требует и CRLF обрабатывает корректно
изначально. Оставлено в этом обсуждении, а не заведено новым test_debt —
находка полностью устранена в рамках этого же фикса, не блокер, не
самостоятельный дефект.

Замеченный (не тронутый, вне DoD этого бага) сиблинг того же класса: у
`scripts/build_watch.py` собственная локальная функция `_rewrite_field`
(строка ~92) с той же сигнатурой, что раньше была в `board_inbound.py`, —
не проверял, использует ли она `read_text`/`write_text` без границы
frontmatter; DoD этой задачи ограничен `board_sync.py`/`board_inbound.py`,
scope не расширяю (D-0037).

**Поправка приёмки (координатор, 2026-08-02T02:15:53Z, критик-вход D1 fix-verifier).**
Формулировка выше называла ЕДИНСТВЕННЫМ сиблингом `build_watch.py` — это
наименее релевантный писатель (пишет `state/app-under-test.yaml`, обычный
конфиг-YAML, не артефакт frontmatter). Критик-вход независимо доказал два
более релевантных живых собрата, которые дифф не тронул и отчёты не
назвали: `scripts/sla_sweep.py::apply_pingpong_block` (read_text/write_text,
доказан полнофайловый CRLF-перегон на чисто-LF артефакте) и
`scripts/stale_locks.py::_clear_lock` (read_text/write_text + `re.subn`
БЕЗ границы frontmatter + жадный `\s*.*$` — доказан не только перегон, но
и ЖИВОЙ latent data-loss: при пустом `lock:` соседнее поле frontmatter
удаляется тем же вызовом). `stale_locks.py` — pre_step №1 КАЖДОГО прохода
qa-loop, 64 из 197 артефактов репозитория сейчас чисто-LF — достижимость
не гипотетическая. Заведён отдельным test_debt `bugs/AT-BUG-040.md`
(severity major — не просто EOL-шум, а доказанный data-loss путь на
критичном pre_step-скрипте), не строкой в этом баге — критерий готовности
ЭТОГО бага (`board_sync.py`/`board_inbound.py`) выполнен полностью и
самодостаточно, класс продолжается новым артефактом (D-0043).

Верификация: полный `scripts/tests` — 3 прогона подряд зелёные (804/804/804,
1 skipped), включая 12 новых байтовых LF/CRLF-тестов
`scripts/tests/test_board_writeback_eol.py`. `arch_check.py`/
`validate_frontmatter.py` — 0/0. `app-under-test/` не тронут (проверено
`git status`). Лок снят.

**2026-08-02 — fix-verifier, независимая верификация, Fixed → Verified.**
Carve-out D1 для `test_debt` в обвязке применён (`test_cases: []` штатен —
задача сама несёт 12 device-free байтовых тестов вместо TC). Прочитан код
целиком: оба скрипта — `read_bytes`/`write_bytes`, `FRONTMATTER_RE`-граница
тела frontmatter, replace-or-insert строго в срезе `text[start:end]`, EOL
новых строк по факту (`_file_eol`/проверка `\r\n` сразу после точки
вставки) — соответствует образцу `gitlab_sync.py::writeback_gitlab_issue`
буквально, включая доводку под CRLF (`(?=\r?\n|$)` lookahead) из обсуждения
выше. Независимый прогон (не переиспользую вывод test-maintainer):
`powershell -NoProfile -ExecutionPolicy Bypass -Command ". D:\AO3_tests\
scripts\tasks.ps1; Invoke-Pytest ../scripts/tests -q"` →
`804 passed, 1 skipped in 25.41s`, `PYTEST_EXIT=0`; отдельно `-v` на
`test_board_writeback_eol.py` — все 12 кейсов поимённо PASSED
(`12 passed in 1.69s`). `arch_check.py`/`validate_frontmatter.py` — 0/0
(свой прогон). `git diff --stat`/`git status -- app-under-test/`
подтверждают: правки по этому багу ограничены `scripts/board_sync.py`,
`scripts/board_inbound.py`, новым `scripts/tests/test_board_writeback_eol.py`,
`bugs/AT-BUG-038.md`; `app-under-test/` пуст в статусе — не тронут.

Дефекты-собратья (D-0043, доклад, scope не расширяю): в рабочем дереве
присутствуют ПОСТОРОННИЕ незакоммиченные изменения (`bugs/AT-BUG-035.md`,
`bugs/AT-BUG-036.md`, `bugs/AT-BUG-037.md`,
`exploratory-charters/PERTURBATIONS.md`, новый
`exploratory-charters/CH-008.md`, `logs/routing-log.jsonl`,
`state/orchestrator-log.md`, `state/board-cursor.json`) — не относятся к
диффу этого бага (иная параллельная работа: gitlab-bugs-publish и т.п.),
не app-under-test, отмечаю как замеченное, не трогаю. Сиблинг
`scripts/build_watch.py::_rewrite_field` (упомянут test-maintainer выше) —
подтверждаю, остаётся не тронутым, НО критик-вход приёмки нашёл двух
БОЛЕЕ релевантных и более опасных сиблингов (`sla_sweep.py`,
`stale_locks.py` — см. поправку координатора выше), заведённых
`bugs/AT-BUG-040.md`.

Статус: **Verified**. `known_issue` уже был `"false"` (изменений не
требуется). Лок снят.

## Чек-лист качества (bug-reporter проходит перед публикацией)
- [x] Проверены дубликаты (AT-BUG-036 — иной класс; AT-BUG-026/029/032/033/034 — другие классы)
- [x] Severity обоснована влиянием: minor (операционный симптом — диффы по EOL, не потеря функциональности)
- [x] Приложены материалы: вердикт критика N4 gitlab-bugs-publish (HANDOFF.md lines 699-712)
- [x] Нет изменений кода приложения
