---
id: AT-BUG-038
title: "писатели frontmatter в board-скриптах: EOL-перегон + отсутствие границы frontmatter"
type: test_debt
debt_kind: flaky_test
severity: minor
status: Open
found_in: "критик-входы gitlab-bugs-publish/AT-BUG-036, 2026-08-01/02"
fixed_in: ""
last_seen_in: ""
test_cases: []
runs: []
duplicates: []
regression_of: ""
status_since: "2026-08-02T00:00:00Z"
updated: "2026-08-02T00:00:00Z"
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

- [ ] Оба скрипта (`board_sync.py` и `board_inbound.py`) переведены на образец `gitlab_sync.py::writeback_gitlab_issue` (read_bytes/write_bytes + eol по факту + replace-or-insert в frontmatter).
- [ ] Существующие тесты `scripts/tests` зелёные (включая board-тесты, если они есть).
- [ ] Новые байтовые тесты LF/CRLF по образцу `test_gitlab_sync.py` writeback-тестов (проверка сохранения EOL исходного файла).
- [ ] arch_check/validate_frontmatter 0/0.
- [ ] Ни одно изменение не внесено в `app-under-test/`.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|

## Обсуждение
Канал человек ↔ фабрика.

## Чек-лист качества (bug-reporter проходит перед публикацией)
- [x] Проверены дубликаты (AT-BUG-036 — иной класс; AT-BUG-026/029/032/033/034 — другие классы)
- [x] Severity обоснована влиянием: minor (операционный симптом — диффы по EOL, не потеря функциональности)
- [x] Приложены материалы: вердикт критика N4 gitlab-bugs-publish (HANDOFF.md lines 699-712)
- [x] Нет изменений кода приложения
