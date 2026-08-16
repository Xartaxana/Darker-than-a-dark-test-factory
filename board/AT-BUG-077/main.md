---
key: "AT-BUG-077"
project: "AO3"
issueType: "bug"
status: "bug-open"
priority: "p2"
summary: "test_heartbeat_wrap.py::test_happy_path_order_and_child_env падает детерминированно, когда `python -m pytest scripts/tests` запущен ИЗ сессии, уже несущей AO3_LOOP_HOLDER (вложенный heartbeat)"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "sev:minor"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-15T20:45:00Z"
updated: "2026-08-15T20:45:00Z"
archived: false
resolution: null
---

# test_heartbeat_wrap.py::test_happy_path_order_and_child_env падает детерминированно, когда `python -m pytest scripts/tests` запущен ИЗ сессии, уже несущей AO3_LOOP_HOLDER (вложенный heartbeat)

_Спроецировано из `bugs/AT-BUG-077.md` (источник правды).
Статус в нашей машине: **Open**._

# AT-BUG-077 — `test_happy_path_order_and_child_env` не изолирован от ambient `AO3_LOOP_HOLDER`, ложно падает под вложенным heartbeat

## Окружение

Не зависит от сборки приложения: долг тестовой системы (`type: test_debt`,
`debt_kind: broken_environment` — тест зависит от НЕЧИСТОГО окружения
запуска, а не от продукта). Обнаружено в сессии test-maintainer,
диспетчированной ПОД активным heartbeat-циклом (мой процесс наследует
`AO3_LOOP_HOLDER` от обёртки `scripts/heartbeat_wrap.py`, канон D-0040/
фабрика heartbeat, см. коммиты `a613233`/`454b12d`/`f085d79`).

## Суть долга

`scripts/tests/test_heartbeat_wrap.py::test_happy_path_order_and_child_env`
(строка ~158-159) собирает `without_extra` — копию env, переданного дочернему
`claude`-процессу, ВЫЧЕРКНУВ ключ `AO3_LOOP_HOLDER` — и сравнивает с
`dict(os.environ)` БЕЗ той же вычёрки:

```python
without_extra = {k: v for k, v in captured["env"].items() if k != "AO3_LOOP_HOLDER"}
assert without_extra == dict(os.environ)
```

Пока тестовый процесс сам НЕ несёт `AO3_LOOP_HOLDER` в своём `os.environ`,
сравнение корректно. Но если `python -m pytest scripts/tests` запущен ИЗ
сессии, которая САМА является дочерним процессом активного heartbeat-цикла
(канонический сценарий: QA-агент/test-maintainer/test-automator и т.п.,
диспетчированные во время работы `heartbeat_wrap.py` — обычный режим
фабрики, не редкий edge case), `os.environ` уже несёт унаследованный
`AO3_LOOP_HOLDER` (значение ВНЕШНЕГО, объемлющего цикла). Правая часть
сравнения (`dict(os.environ)`) этот ключ не теряет, левая (`without_extra`)
— теряет по построению (явная вычёрка) → `assert` падает с «Right contains
1 more item: AO3_LOOP_HOLDER: ...».

Воспроизведено детерминированно (не флейк — сравнение константных множеств
ключей):

```
$ echo $AO3_LOOP_HOLDER
heartbeat:2026-08-15T20:30:02Z:8e10f8d2
$ python -m pytest scripts/tests/test_heartbeat_wrap.py::test_happy_path_order_and_child_env -q
FAILED scripts/tests/test_heartbeat_wrap.py::test_happy_path_order_and_child_env
AssertionError: assert {...} == {...}
  Right contains 1 more item:
  {'AO3_LOOP_HOLDER': 'heartbeat:2026-08-15T20:30:02Z:8e10f8d2'}
1 failed in 0.29s
```

Полный прогон `python -m pytest scripts/tests -q` в ЭТОЙ же сессии:
`1 failed, 1296 passed, 1 skipped` — единственный красный именно этот тест;
никаких файлов в `scripts/` этой сессией не менялось (диспетчированный
скоуп — только `framework/tests/test_downloads.py` и `test-cases/downloads/
TC-154.md`/`TC-037.md`, `git diff -- scripts/` пуст), т.е. падение не
регрессия от этого диспатча, а свойство самого теста при вложенном запуске.

## Почему это блокер обвязки, а не флейк продукта

`python -m pytest scripts/tests -q` — канонический DoD-гейт «без регресса»
для ЛЮБОГО test-maintainer/test-automator диспатча, трогающего `scripts/`
ИЛИ идущего по чек-листу до зелёного `arch_check`+`scripts/tests` (см.
CLAUDE.md «Дисциплина команд» п.1, «скрипты обвязки — только
`python scripts/<имя>.py`»/`scripts/tests`). Поскольку heartbeat — штатный
механизм фоновой доставки задач (не экспериментальный), а сессии
QA-агентов регулярно запускаются как дети heartbeat-цикла, ЛЮБОЙ такой
диспатч, доходящий до этого гейта, детерминированно получит один ложный
красный — не отличимый по тексту от настоящей регрессии без ручного
разбора (как в этой сессии).

## Критерий готовности (Fixed)

- `test_happy_path_order_and_child_env` вычёркивает `AO3_LOOP_HOLDER` из
  ОБЕИХ частей сравнения (`os.environ`-снимок тоже без этого ключа), ЛИБО
  тест явно очищает/подделывает `AO3_LOOP_HOLDER` в собственном
  `os.environ` через `monkeypatch.delenv(..., raising=False)` до вызова
  `hw.run_pass`, чтобы сравнение было корректно независимо от того, несёт
  ли объемлющий процесс свой heartbeat-холдер.
- Повторный прогон `python -m pytest scripts/tests/test_heartbeat_wrap.py -q`
  зелёный ОБОИМИ способами: (а) с `AO3_LOOP_HOLDER`, установленным в
  окружении вызова (воспроизведение этого бага), и (б) без него (исходный
  сценарий) — оба варианта приложены witness'ом.
- `python -m pytest scripts/tests -q` — 0 failed.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|

## Обсуждение

**2026-08-16 — builder (sonnet), примечание (spec-factory-window v6,
К5е — не чинил, вне owns этого диспатча).** Архитектура сменилась
«окно-фабрика + сторож»: `scripts/heartbeat.cmd` (Task Scheduler,
`AO3-QA-Heartbeat`) больше НЕ вызывает `scripts/heartbeat_wrap.py` —
вызывает `scripts/factory_watchdog.py` (см. докстринг-деприкацию
`heartbeat_wrap.py` и `docs/06-dark-factory.md` §5). Ambient-условие,
делавшее этот баг ОРГАНИЧЕСКИ воспроизводимым (QA-агент, диспетчиро-
ванный planировщиком ПОКА `heartbeat_wrap.py` реально держит проход и
прокидывает `AO3_LOOP_HOLDER` дочернему `claude`), в production БОЛЬШЕ
НЕ ВОЗНИКАЕТ — некому запускать эту цепочку вживую. Баг остаётся
**Open** (сам дефект теста — `without_extra` вычёркивает
`AO3_LOOP_HOLDER` только из ОДНОЙ стороны сравнения — НЕ исправлен,
критерий готовности из тела бага не тронут). Repro теперь ТОЛЬКО
синтетический: вручную выставить `AO3_LOOP_HOLDER` в env перед `python
-m pytest scripts/tests/test_heartbeat_wrap.py -q` (как в исходном
воспроизведении бага) — код обёртки и её тесты остаются живыми
(страховка отката, `test_heartbeat_wrap*.py` держатся зелёными в общем
прогоне `scripts/tests`), просто путь до этого сравнения больше не
проходится ambient-путём.

**2026-08-15 — test-maintainer, заведение (found_in, не чинил — вне owns
диспатча RUN-20260815-0337-TC154-APP_CHANGED, D-0037 scope не
расширяется).** Обнаружено при штатном DoD-шаге 4 (`python -m pytest
scripts/tests -q`) диспатча про TC-154/TC-037 (APP_CHANGED, литерал
диалога скана). Диспатч не owns `scripts/`, самостоятельно не чинил;
докладываю здесь и ссылкой в `runs/RUN-20260815-0337.md`. Решение о
диспетче фикса — за Lead.

## Чек-лист качества
- [x] Проверены дубликаты: grep `bugs/` по `AO3_LOOP_HOLDER`/
      `test_heartbeat_wrap`/`test_happy_path_order_and_child_env` — 0
      совпадений до этого файла.
- [x] Суть долга ясна и воспроизводима: дословный вывод прогона приложен
      (echo `AO3_LOOP_HOLDER` + изолированный прогон теста + полный прогон
      `scripts/tests`).
- [x] Severity: minor — не блокирует ни один существующий TC
      (`test_cases: []`), гейт можно перепрогнать отдельно/распознать
      причину вручную; но регулярно шумит ложным красным под heartbeat.
- [x] Ни одно изменение не внесено в `app-under-test/` и в `scripts/`
      (только заведение бага, фикс не начинался).
- [x] id — max+1 существующих (`AT-BUG-076` был максимальным на момент
      заведения).
