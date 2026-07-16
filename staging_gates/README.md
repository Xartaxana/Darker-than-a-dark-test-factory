# staging_gates/ — штабной порт-батч policy-as-code гейтов (не активировано)

**НЕ АКТИВИРОВАНО.** Это staging-копия для ревью и постановки их Lead'ом
(D-0069: самоактивирующийся enforcement-файл builder на путь не кладёт —
кладёт содержимым сюда, на боевой путь ставит Lead при приёмке).
Содержимое этого каталога НЕ подключено ни к одному активному `hooksPath`
— ни к штабу (`D:\Improving_AI\Operating-System-for-LLMs`), ни к этому
деплою (`D:\AO3_tests`), ни к текущей сессии, создавшей этот порт.
Активация — решение и действие их Lead'а, не этой сдачи.

Образец формы — `D:\Improving_AI\exam_fullgates_kit\staging_hq\README.md`
(штабной порт того же батча в exam_fullgates_kit).

## Что здесь

Вербатим-копии (byte-identical, без содержательной адаптации к AO3 — это
staging ДЛЯ ревью Lead'ом, не готовая к прогону версия) пяти гейтов и их
тестов из штаба (`D:\Improving_AI\Operating-System-for-LLMs\tools\`):

- `tools/dispatch_gate.py` + `tools/test_dispatch_gate.py`
- `tools/critic_snapshot.py` (без отдельного `test_critic_snapshot.py` —
  такого файла нет и в штабе; сверено `Grep`'ом по `tools/`, см. "Проверено")
- `tools/dod_track.py` + `tools/test_dod_track.py`
- `tools/dod_gate.py` + `tools/test_dod_gate.py`
- `tools/main_gate.py` + `tools/test_main_gate.py`

Логика внутри — ровно штабная (PreToolUse: dispatch_gate + critic_snapshot;
PostToolUse: dod_track; SubagentStop: dod_gate; Stop: main_gate; подробности
— докстринги файлов). Здесь НЕТ штабных "STAGING_HQ ВАРИАНТ"-адаптаций,
которые есть в `exam_fullgates_kit/staging_hq/` (byte-safe stdin,
doc-only-исключение и т.п.) — этот порт-батч их не переносил и не изобретал
собственных; это чистая копия штабной версии как есть, ЖДЁТ адаптационных
решений их Lead'а (ниже), а не предвосхищает их.

## Известные точки адаптации (для их Lead'а при активации)

Порт НЕ решает эти вопросы содержательно (не в scope этой сдачи — "staging
для ревью", не "готовая к прогону версия"). Список — чтобы решение при
активации не терялось:

1. **Путь скриптов: `tools/` (штаб) vs `scripts/` (AO3).** Хук-команды в
   штабном `settings.json` — `python tools/dispatch_gate.py` и т.д.
   (относительные, из корня репо). В AO3 конвенция другая: вся обвязка
   конвейера лежит в `scripts/` (`scripts/log_append.py`,
   `scripts/mechanism_gate.py` — свой, уже существующий и уже активный
   независимый механизм, НЕ то же самое, что штабной `mechanism_gate.py`,
   если такой в этом батче встретится: пересечение имён — не пересечение
   логики, Lead должен сверить сам перед подключением). Активация требует
   решить: держать эти гейты в `staging_gates/tools/` как отдельный
   неймспейс (и звать `python staging_gates/tools/dispatch_gate.py`), или
   переносить содержимым в `scripts/` рядом с существующей обвязкой —
   и в обоих случаях поправить пути в фрагменте хуков (см. ниже).

2. **`.claude/settings.json`: сейчас в AO3 НЕТ ключа `hooks` вообще** —
   только `permissions.allow` (сверено чтением `D:\AO3_tests\.claude\
   settings.json`, read-only, см. "Проверено"). Активация — это
   ДОБАВЛЕНИЕ блока `hooks` (см. `settings.fragment.json` рядом), НЕ
   перезапись существующего файла; Lead сам решает, мержить ли вручную
   или другим способом.

3. **Формы verification-команд.** Штабная каноничная форма —
   `python -m pytest tools/ gateway/ -q`; `dod_track.py`/`dod_gate.py`
   распознают "верифицирующую команду" регэкспом
   `pytest|python\s+-m\s+pytest|python\s+.*test` (case-insensitive,
   докстринг `dod_track.py`). В AO3 канонические формы гигиены (CLAUDE.md,
   раздел "Дисциплина команд") — `python -m pytest scripts/tests -q`
   (скрипты-обвязка, штатно матчится тем же регэкспом — содержит
   `pytest`) И `powershell ... "; . D:\AO3_tests\scripts\tasks.ps1;
   Invoke-Pytest <аргументы>"` (framework/device-тесты через tasks.ps1 —
   `Invoke-Pytest` тоже содержит подстроку `pytest`, матчится тем же
   регэкспом без изменений). НЕ матчится регэкспом: чисто device-смок без
   слова test/pytest (`Get-Device`, голый `adb shell ...`, `arch_check.py`,
   `doctor.py` и т.п.) — если такие формы должны легально закрывать DoD
   как witness, регэксп нужно расширять; это решение их Lead'а, не
   предрешено здесь.

4. **Doc-only исключение (`dod_gate.py`/`main_gate.py`).** Штабная версия
   освобождает от прогона правки ТОЛЬКО `.md`/`.json`. В AO3 журнал
   маршрутизации — `.jsonl` (`logs/routing-log.jsonl`), не покрыт этим
   исключением как есть (расширение `.jsonl` ≠ `.json`); Lead решает,
   считать ли дозапись строки в journal тем же "doc-only" классом или нет.

5. **`dod_track.py` item-2а** (штабное исключение "не признавать
   самотесты гейтовой инфры зелёным прогоном для правок самих гейтов") —
   в этом порту НЕ решено ни так, ни так (в отличие от
   `exam_fullgates_kit/staging_hq/`, где решение явно принято и
   задокументировано). Если сессии AO3 будут сами дорабатывать эти гейты
   — Lead решает, переносить исключение или нет, тем же прецедентом, что
   у staging_hq.

## `settings.fragment.json`

Шаблон блока `hooks` в штабной форме (пути `tools/...` — placeholder,
требуют решения п.1 выше перед реальным подключением). НЕ является частью
активного `.claude/settings.json` AO3 — отдельный файл специально, чтобы
не создавать риск случайного мержа мимо ревью.

## Manifest

given (read-only): `tools/{dispatch_gate,critic_snapshot,dod_track,
dod_gate,main_gate}.py` + `test_*.py` штаба
(`D:\Improving_AI\Operating-System-for-LLMs\tools\`),
`exam_fullgates_kit/staging_hq/README.md` (образец формы),
`D:\AO3_tests\.claude\settings.json` (сверка текущего состояния, read-only).
owns: `D:\AO3_tests\staging_gates\**` (эта директория).
non-goals: `D:\AO3_tests\.claude\settings.json`, `.githooks/`, `state/`,
`schemas/` — не трогать; их `CLAUDE.md`/`.claude/agents/*` — правит
параллельный builder, не трогать; ничего из перечисленного выше не
активировать; git commit не делать.

## Проверено (builder, порт-батч)

- Байт-идентичность копий штабным оригиналам — `diff -q` по всем 9 файлам
  (5 гейтов + 4 теста): все 9 — `identical`.
- Синтаксис всех 9 файлов — `python -c "import ast; ast.parse(...)"` из
  `staging_gates/tools/`: все OK.
- Отсутствие `test_critic_snapshot.py` в штабе сверено `Glob`'ом
  (`**/test_critic_snapshot*` от корня штаба — 0 файлов) с позитивным
  контролем тем же инструментом и синтаксисом (`**/test_dod_gate*` — нашёл
  `tools/test_dod_gate.py` и дубль в `toolkit/tools/`, подтверждая, что
  поиск в принципе работает и пустой результат — не промах вызова, F-30/
  F-34) — не пропуск копирования, штабного файла для критик-снапшота
  попросту нет.
- Текущее содержимое `D:\AO3_tests\.claude\settings.json` прочитано
  (read-only) — подтверждено отсутствие ключа `hooks`, только
  `permissions.allow`.
- **НЕ пройдено формальным `pytest`** внутри AO3 — не в объявленном scope
  этой сдачи (staging для ревью, не параллельный активный тестовый набор);
  тот же non-goal, что у `exam_fullgates_kit/staging_hq/`.
