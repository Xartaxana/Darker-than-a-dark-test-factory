---
id: AT-BUG-041
title: "build_watch.py::update_aut (+ спящие sla_sweep.rewrite_registry/loop_lock._atomic_write_text): EOL-перегон партиальных писателей scripts/, класс шире frontmatter-границы"
type: test_debt
debt_kind: flaky_test
severity: minor
status: Fixed
found_in: "критик-вход D1-верификации AT-BUG-040, 2026-08-02: класс 1 (EOL-перегон) не совпадает по границе с классом 2 (frontmatter-boundary) - аргумент 'config-файл без frontmatter' исключает только класс 2"
fixed_in: "test-maintainer, 2026-08-02T14:39:03Z (attempt 2, после критик-входа приёмки): build_watch.py::update_aut + sla_sweep.py::rewrite_registry + loop_lock.py::_atomic_write_text/_write_loop_escalation переведены на байтовый I/O; закрыты остаточные \\r-глотающие регрессы в границах полей (build_watch._rewrite_field, loop_lock.LOOP_LINE_RE) И класс-полнота нового контента (sla_sweep.rewrite_registry/loop_lock._write_loop_escalation теперь пишут новые строки в EOL-стиле файла, не хардкод \\n) — см. Обсуждение"
last_seen_in: ""
test_cases: []
runs: []
duplicates: []
regression_of: ""
status_since: "2026-08-02T14:18:27Z"
updated: "2026-08-02T14:39:03Z"
reopen_count: 0
dispute_count: 0
awaiting: none
resolution: ""
resolution_comment: ""
known_issue: "false"
blocked_reason: ""
lock: "fix-verifier:2026-08-03T09:23:51Z"
gitlab_issue: ""
---

# AT-BUG-041 — EOL-перегон партиальных писателей scripts/ (класс шире frontmatter-границы)

## Окружение
Долг тестовой системы (`type: test_debt`; `debt_kind: flaky_test` — та же категория, что `AT-BUG-038`/`AT-BUG-040`). severity **minor** (не major, как `AT-BUG-040`): здесь только EOL-перегон, без доказанной потери данных — предмет ближе к `AT-BUG-038`.

## Суть долга

`AT-BUG-038`/`AT-BUG-040` закрыли класс «партиальный писатель существующего файла через `read_text`/`write_text`» ТОЛЬКО на писателях frontmatter-полей markdown-артефактов. Критик-вход D1-верификации `AT-BUG-040` показал: класс 1 (EOL-перегон при партиальной правке) НЕ зависит от наличия frontmatter-границы — это два независимых класса, и аргумент «config-файл без markdown-тела» релевантен только классу 2 (граница поиска поля), не классу 1.

### `scripts/build_watch.py::update_aut` (строки ~184-197) — ЖИВОЙ экземпляр
Партиально правит `state/app-under-test.yaml` через `read_text`/`write_text`. Доказано критиком прогоном на КОПИИ РЕАЛЬНОГО файла (сегодня чисто-LF, 13 bare-LF строк): результат — 13 CRLF, перегон произошёл. `build_watch.py` — pre_step №3 (`state/rules.yaml:28`), `update_aut` срабатывает на КАЖДОМ новом коммите app-under-test — достижимость не гипотетическая, файл уже в уязвимом состоянии сегодня.

### `scripts/sla_sweep.py::rewrite_registry` (строки ~291,324) — спящий экземпляр
`read_text(splitlines(keepends))` + `write_text` — партиальная правка (НЕ полная регенерация, как ошибочно записано в `bugs/AT-BUG-040.md` до поправки координатора). На реальном (сейчас CRLF) `state/escalations.md` перегона нет; на LF-клоне того же контента — есть (`CRLF=0 → CRLF=7`, доказано критиком). Спит только потому, что файл случайно CRLF сегодня.

### `scripts/loop_lock.py::_atomic_write_text` (строки ~176-194) — тот же механизм
Не проверен критиком так же детально, как `rewrite_registry`, но использует тот же приём (partial read/write) — кандидат той же оси, требует отдельной проверки при фиксе.

## Не входит в скоуп (не блокер, зафиксировано отдельно координатором)

**Регрессия охвата в `stale_locks.py::_clear_lock` (введена фиксом `AT-BUG-040`, НЕ этим багом):** строгий `FRONTMATTER_RE` (образец `AT-BUG-038`) требует закрывающий `---\r?\n`; протухший лок в файле БЕЗ хвостового перевода строки перед `---`, С BOM, или с битым frontmatter — теперь НЕ снимается (`changed=False`), тогда как ДО фикса `AT-BUG-040` (жадный regex по всему файлу) он снимался (ценой риска задеть соседнее поле). Артефакт навсегда застревает залоченным — прецедент класса: `TC-021` историческая застрявшая блокировка до ручного вмешательства. Критик измерил: сегодня 0 из 204 артефактов в этом состоянии — не блокер, не критично сейчас, но требует внимания при следующем касании `stale_locks.py` (возможный фикс: fallback на менее строгий поиск ТОЛЬКО для случая «строгий не совпал», с явным `[WARN]` вместо тихого `False`).

## Критерий готовности (Fixed)

- [x] `build_watch.py::update_aut` переведён на read_bytes/write_bytes (образец `gitlab_sync.py`/`board_sync.py`/`board_inbound.py` после AT-BUG-038/040).
- [x] `sla_sweep.py::rewrite_registry` переведён на read_bytes/write_bytes.
- [x] `loop_lock.py::_atomic_write_text` проверен на тот же класс и, подтверждён (единственный партиальный read-modify-write потребитель — `_write_loop_escalation`), переведён аналогично.
- [x] Новые байтовые LF/CRLF тесты по образцу `scripts/tests/test_at_bug_040_eol.py` для всех затронутых функций.
- [x] Существующие тесты `scripts/tests` зелёные, без регресса.
- [x] arch_check/validate_frontmatter — 0/0.
- [x] Ни одно изменение НЕ вносится в `app-under-test/`.
- [ ] Опционально (не обязательно для Fixed этого бага, но рекомендовано в очередь): разобрать регрессию охвата `_clear_lock` выше — либо явным `[WARN]`-логированием тихого пропуска, либо fallback-поиском для нестрогих случаев.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|

## Обсуждение

**2026-08-02T02:38:33Z — координатор (Sonnet), заведение по докладу критик-входа D1 AT-BUG-040:**
Четвёртая находка класса «партиальный текстовый писатель scripts/» за этот проход qa-loop (после AT-BUG-036→039, AT-BUG-038→040). Класс продолжается отдельным артефактом (правило 9/D-0043), не блокирует приёмку AT-BUG-040 (тот закрыт корректно на своём заявленном скоупе — sla_sweep.apply_pingpong_block + stale_locks._clear_lock). Диспатч B4 — очередным проходом (не приоритетный, в отличие от AT-BUG-040: здесь косметический EOL-перегон без доказанной потери данных).

**2026-08-02T14:18:27Z — test-maintainer (Sonnet), фикс + новые тесты (B4):**

Сделано (все три пункта критерия готовности):

1. `scripts/build_watch.py::update_aut` — `AUT_PATH.read_bytes().decode("utf-8")` /
   `AUT_PATH.write_bytes(text.encode("utf-8"))` вместо `read_text`/`write_text`.
2. `scripts/sla_sweep.py::rewrite_registry` — тот же переход
   (`ESCALATIONS_PATH.read_bytes().decode(...)` / `.write_bytes(...)`); внутренняя логика
   (`splitlines(keepends=True)` + join) не менялась — она уже корректно распознаёт и
   сохраняет и `\n`, и `\r\n` терминаторы, проблема была только в самой точке I/O.
3. `scripts/loop_lock.py::_atomic_write_text` — проверен и ПОДТВЕРЖДЁН тем же классом:
   единственный партиальный read-modify-write потребитель — `_write_loop_escalation`
   (читает существующий `escalations.md`, точечно обновляет/дописывает ОДНУ
   `LOOP-N`-строку). Переведён на `write_bytes` внутри `_atomic_write_text`; чтение в
   `_write_loop_escalation` — на `read_bytes().decode("utf-8")`. Остальные потребители
   `_atomic_write_text` (`_save_reaps`, запись лок-файла в `acquire()`) пишут
   свежесгенерированный JSON целиком (не partial-правка существующего контента) —
   переход на `write_bytes` для них побочно безопасен (байт-в-байт `\n` вместо
   `os.linesep`-трансляции на Windows), семантика JSON не зависит от EOL.

Два ПОПУТНЫХ остаточных регресса того же класса (границы полей), пойманных
СОБСТВЕННЫМИ байтовыми тестами до сдачи (не замаскированы — оба были красные до
фикса регэкспов):

- `build_watch.py::_rewrite_field` — жадный `[^#\n]*(?P<comment>#.*)?$` матчил `\r` (не
  исключён ни классом символов, ни `.`), поглощая его в тело замены на строке БЕЗ
  хвостового комментария (эмпирически: `version_code: 11\r\n` → `version_code: 99\n`).
  Заменён на `[^#\r\n]*(?P<comment>#[^\r\n]*)?(?=\r?\n|$)` — тот же образец границы, что
  уже закрыт в `board_sync.py`/`board_inbound.py`/`gitlab_sync.py`/`stale_locks.py`.
  Дополнительно: ветка «поля нет в файле» (типично `coalesced_commits` — этого поля
  НЕТ в реальном `state/app-under-test.yaml` на 2026-08-02, т.е. эта ветка исполняется
  на КАЖДОМ реальном вызове `update_aut`) раньше вставляла новую строку с хардкодным
  `\n` независимо от стиля файла — заводила перманентно смешанный EOL уже на первой
  сборке. Теперь разделитель — EOL-стиль файла по факту (тот же приём, что
  `board_inbound._file_eol`).
- `loop_lock.LOOP_LINE_RE` — тот же класс: `.*$` вместо `[^\r\n]*` глотал `\r` при
  обновлении УЖЕ существующей `LOOP-N`-строки на CRLF-файле. Исправлено.

Новые тесты: `scripts/tests/test_at_bug_041_eol.py` — параметризованные LF/CRLF на
`update_aut` (со строкой-с-комментарием и без, отдельно проверяет границу
`_rewrite_field`), `rewrite_registry` (kept-only ранний return байт-в-байт + removal
сохраняет нетронутые строки байт-в-байт) и `_write_loop_escalation` (обновление
существующей `LOOP-N`-строки на месте + добавление первой).

**Witness (дословный вывод, три прогона подряд зелёные):**

```
python -m pytest scripts/tests -q
...
835 passed, 1 skipped in 27.66s
```
```
python -m pytest scripts/tests -q
...
835 passed, 1 skipped in 25.62s
```
```
python -m pytest scripts/tests -q
...
835 passed, 1 skipped in 32.71s
```
```
python scripts/arch_check.py
arch_check: ошибок 0, предупреждений 0
python scripts/validate_frontmatter.py
validate_frontmatter: ошибок 0, предупреждений 0
```

Изменённые файлы: `scripts/build_watch.py`, `scripts/sla_sweep.py`,
`scripts/loop_lock.py`, `scripts/tests/test_at_bug_041_eol.py` (новый),
`bugs/AT-BUG-041.md`. Ни одна правка в `app-under-test/`. Статус переведён
`Open → Fixed` (guard-переход B4, `schemas/transitions.yaml`); лок баг-артефакта не
трогал (`lock: "test-maintainer:2026-08-02T14:06:42Z"` — снимет координатор).
Скоуп ровно по критерию готовности; регрессия охвата `stale_locks.py::_clear_lock`
(раздел «Не входит в скоуп» выше) НЕ трогалась — остаётся queued отдельной строкой,
как и зафиксировано координатором при заведении.

**2026-08-02T14:39:03Z — test-maintainer (Sonnet), attempt 2 (после критик-входа приёмки):**

Критик подтвердил ядро attempt 1 (мутационные пробы красные, сужения регэксп-границ
нет, семантика цела) и вернул ОДИН блокер: класс-полнота в моих же owns-путях — я
закрыл перегон СУЩЕСТВУЮЩИХ строк, но НЕ заметил, что НОВЫЙ контент в этих же двух
функциях по-прежнему собирается хардкодным `\n`, а не EOL-стилем файла (тот же
подкласс, что я сам закрыл в `build_watch._rewrite_field`, ветка «поля нет», тем же
аргументом — и не перенёс аналогию на соседние точки, правило 9). Живой
`state/escalations.md` сейчас 820 CRLF / 0 bare-LF; первая же post-fix эскалация без
этого исправления завела бы файл в перманентно смешанный EOL.

Доделано:

1. `scripts/sla_sweep.py::rewrite_registry` — `eol = "\r\n" if "\r\n" in text else "\n"`
   вычисляется по прочитанному файлу; `new_lines.append(...{eol})` вместо `...\n`;
   `ESCALATIONS_HEADER` (константа, всегда `\n`-стиля) при вставке в CRLF-файл теперь
   `.replace("\n", eol)` — образец `board_inbound._file_eol` (AT-BUG-038).
2. `scripts/loop_lock.py::_write_loop_escalation` — тот же приём: `eol` вычисляется из
   прочитанного текста; ветка «LOOP-строки ещё нет» — и добивка `text += eol` (было
   `"\n"`), и сама новая строка `...{eol}` (было `...\n`). Ветка «обновление
   существующей LOOP-N на месте» EOL не трогает вовсе (уже была верна в attempt 1).

Новые тесты (граница и за ней, по образцу `test_append_discussion_new_content_matches_file_eol`):

- `test_rewrite_registry_added_line_matches_file_eol` — новая строка на CRLF-/LF-файле
  берёт EOL файла, старое содержимое байт-в-байт нетронуто.
- `test_write_loop_escalation_append_new_preserves_existing_eol` (усилен) — новая
  строка (файл ЗАКАНЧИВАЕТСЯ EOL) берёт EOL файла.
- `test_write_loop_escalation_append_new_no_trailing_eol_uses_file_style` (новый,
  граница ЗА пределами предыдущего) — файл БЕЗ хвостового EOL перед точкой вставки:
  и добивка перед новой строкой, и сама строка — в стиле файла, не хардкод `\n`.

**Witness attempt 2 (дословный вывод, три прогона подряд зелёные):**

```
python -m pytest scripts/tests -q
...
839 passed, 1 skipped in 27.62s
```
```
python -m pytest scripts/tests -q
...
839 passed, 1 skipped in 27.62s
```
```
python -m pytest scripts/tests -q
...
839 passed, 1 skipped in 27.67s
```
```
python scripts/arch_check.py
arch_check: ошибок 0, предупреждений 0
python scripts/validate_frontmatter.py
validate_frontmatter: ошибок 0, предупреждений 0
```

### Известные остатки (вне скоупа, по evidence рецидива)

Четыре пункта той же поверхности (частичные текстовые писатели /
EOL-нормализация scripts/), явно НЕ вошедшие в скоуп AT-BUG-041 и НЕ починенные
здесь — зафиксированы по правилу 9 (не оставлять аналог молча), продиктованы
критик-входом приёмки, чинить их — отдельным диспатчем:

- **(а)** `build_watch._rewrite_field`: `\s*` в паттерне пересекает перевод
  строки — поле с ПУСТЫМ значением (например `field:` без хвоста на своей
  строке) съедает следующую строку целиком (тот же архетип, что
  data-loss-регресс `AT-BUG-040` до фикса `stale_locks._clear_lock`, только
  здесь предпосылка не доказана достижимой: в живом `state/app-under-test.yaml`
  пустых значений полей сегодня нет).
- **(б)** `sla_sweep.rewrite_registry` не гарантирует перевод строки перед
  append, если файл существует, но НЕ заканчивается хвостовым EOL (в отличие от
  `loop_lock._write_loop_escalation`, которая эту границу теперь явно
  обрабатывает веткой `elif not text.endswith("\n")`) — новая строка может
  слиться с последней строкой существующего контента.
- **(в)** Текстовые аппендеры без `newline=` пишут `os.linesep` (та же
  общая поверхность класса, ещё не переведённая на байтовый режим):
  `build_watch.py:186` (`_append_escalation`/`_append_orch_log` — открывают файл
  через `.open("a", encoding="utf-8")` без `newline=""`), `doctor.py:175`,
  `board_inbound.py:321`. Контрпример-образец, КАК это должно быть сделано —
  `log_append.py:712` (уже с `newline=""`).
- **(г)** `build_watch._read_field:88` — последний в этом модуле читатель через
  `AUT_PATH.read_text(encoding="utf-8")` (universal newlines на чтении), не
  переведённый на байтовый режим; на практике нейтрализован тем, что результат
  сразу проходит `.strip()` — CRLF/LF-разница не наблюдаема вызывающим кодом,
  поэтому не являлся частью критерия готовности этого бага.

Ни один из четырёх пунктов не чинится в рамках AT-BUG-041 (non-goals диспатча
attempt 2); при следующем касании соответствующего модуля — учитывать как
известный аналог того же класса.

Изменённые файлы attempt 2: `scripts/sla_sweep.py`, `scripts/loop_lock.py`,
`scripts/tests/test_at_bug_041_eol.py`, `bugs/AT-BUG-041.md`. Ни одна правка в
`app-under-test/`; живой лок прохода (`state/loop.lock`) не трогал.

## Чек-лист качества (bug-reporter проходит перед публикацией)
- [x] Проверены дубликаты среди открытых test_debt: не совпадает с AT-BUG-038 (закрыт на board_sync.py/board_inbound.py), AT-BUG-040 (закрыт на sla_sweep.apply_pingpong_block/stale_locks._clear_lock, тот же класс — сиблинг, не дубликат), AT-BUG-039 (другая ось — framework/steps диагностика ожидания)
- [x] Severity обоснована влиянием: minor — EOL-перегон косметический, потери данных не доказано (в отличие от AT-BUG-040)
- [x] Приложены материалы: вердикт критика D1-верификации AT-BUG-040 (2026-08-02), включая воспроизведённые python-пробы на реальных/LF-клонированных данных
- [x] Нет изменений кода приложения
