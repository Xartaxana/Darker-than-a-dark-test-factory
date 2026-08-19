"""ЧАСТИЧНО ДЕПРЕКИРОВАНО (spec-factory-window v7 = v6 + Д1 ночной резерв,
docs/tasks/factory-visible-window.md §Д, 2026-08-16, слово оператора
2026-08-16 «в идеале heartbeat просто подталкивает фабрику в открытом
окне»): `scripts/heartbeat.cmd` БОЛЬШЕ НЕ ВЫЗЫВАЕТ `run_pass`/`main` этого
модуля НАПРЯМУЮ — вызывает `scripts/factory_watchdog.py` (сторож окна).
Архитектура «невидимая фабрика в фоне» заменена на «окно-фабрика + сторож»:
`/qa-loop` ведёт скилл `.claude/skills/factory/SKILL.md` из ОТКРЫТОГО окна
Claude Code как штатный путь. НО: класс «фон не ведёт» (v6-редакция этой
шапки) ПЕРЕСТАЛ БЫТЬ ВЕРНЫМ БЕЗ ОГОВОРОК с Д1 — `heartbeat.cmd`
ТРАНЗИТИВНО вызывает child-spawn-машинерию ЭТОГО модуля: сторож
(`factory_watchdog.py`), увидев мёртвое окно (STALLED ≥ 15 мин, предикаты
fastdeath/slowdeath чисты, `night_fallback` не выключен), спавнит ОДИН
резервный проход через `run_fallback_pass(...)` НИЖЕ — тот же самый
acquire/Popen/kill-tree/release-контур, что и депрекированный `run_pass`.

Судьба веток (v7, после Д1):

  1. **child-spawn-ядро** (acquire/BUSY/Popen/kill-tree/release/REFUSED,
     вынесено в общее `_run_child(...)`) — ЖИВОЕ: используется ОБОИМИ
     `run_pass` (прежний контракт, вечный `0`, из production НЕ
     вызывается — страховка отката, старые пины `test_heartbeat_wrap*.py`
     держатся зелёными) И `run_fallback_pass` (НОВАЯ точка входа Д1,
     production-путь через `factory_watchdog.py`, см. её докстринг ниже).
  2. **fastdeath-учёт** (`state/heartbeat-fastdeath.json`,
     `HEARTBEAT-CHILD-DEATH`-эскалация) — ЖИВОЙ (снова): `run_fallback_pass`
     инкрементирует/сбрасывает тот же файл через общее ядро. **Правка
     семантики (Д п.6, консолидированная секция — серии ДИЗЪЮНКТНЫ):**
     сброс (`_fastdeath_reset`) теперь происходит ТОЛЬКО при
     `child_rc == 0` — медленный отказ (`rc != 0`, `runtime >=
     FAST_DEATH_SEC`) БОЛЬШЕ НЕ СБРАСЫВАЕТ fastdeath (раньше сбрасывал —
     это ошибка старой модели «не-быстрая смерть = здоровая»; теперь
     медленные отказы копят ОТДЕЛЬНУЮ серию `slowdeath` — её домен ВНЕ
     этого модуля, в `scripts/factory_watchdog.py`, т.к. серия живёт в
     `state/factory-watchdog.json`, не здесь). `timeout_kill` НЕ трогает
     fastdeath вовсе (ни инкремент, ни сброс) — она относится ТОЛЬКО к
     slowdeath-серии сторожа.
  3. **бюджет-ветка** (`state/heartbeat-budget.txt`, `HEARTBEAT-BUDGET`,
     `_write_budget`/`_schtasks_disable`) — ОСТАЁТСЯ МЁРТВОЙ: бюджет
     прогонов живёт в `/factory N` (окно) и в `passes_done`/`budget_total`
     `state/factory-mode.json` (резерв, через `on_pass_done`), НЕ в этом
     файле. `run_fallback_pass(..., budget_enabled=False)` эту ветку явно
     НЕ вызывает — `budget_enabled=True` не реализован (`NotImplementedError`
     на вызов), недостижимость — КОДОМ, не дисциплиной.

TTL-источник (К4 спеки): эта ветка ОСТАЁТСЯ на `sla_utils.
load_lock_stale_hours` (см. `compute_max_pass_sec` ниже) — НЕ переходит
на новую `load_loop_lock_ttl_hours` (та — для loop_lock.py/doctor.py/
сторожа, живых читателей); `run_fallback_pass` использует ТОТ ЖЕ клamp
(МAX_PASS-киллер легален и для резерва — архив v3 §9).

--- Исходный докстринг (M1+M4, живой контекст на момент, когда обёртка
была ЕЩЁ production-путём) сохранён ниже без изменений: ---

heartbeat_wrap — честная обёртка вокруг heartbeat.cmd (M1+M4, план
plan-m1-m4.md v3, критик-на-план PASS 2026-08-09; контекст:
runs/REHEARSAL-2026-08-04.md §«Находки окна» N1/N6).

До этого скрипта heartbeat.cmd (12 строк) НЕ брал и НЕ снимал лок сам —
лок брал/снимал сам SKILL qa-loop изнутри прохода (шаг 0а/чек-лист
закрытия). Смерть координатора между acquire и release (краш claude.cmd,
OOM машины, обрыв Task Scheduler) оставляла лок сиротой до TTL-страховки
(2ч, state/sla.yaml thresholds.lock_stale) — находка N1. Документированный
в SKILL `release` без `--holder` при этом никогда не срабатывал (дефолт
holder = `qa-loop:<ISO СЕЙЧАС>` ≠ holder acquire → REFUSED exit 1) — то
есть даже штатное завершение прохода latently не снимало лок правильно
(находка B5).

Это исправлено переносом владения локом СЮДА — в долгоживущую обёртку,
а не в короткоживущий CLI-вызов внутри прохода:

  1. holder = `heartbeat:<ISO>:<nonce8>` — нонс на каждый запуск (утёкший
     env прошлого запуска не совпадает ни с чем, класс B4).
  2. Лок берётся ПРОГРАММНЫМ вызовом `loop_lock.acquire(...)` (точная
     keyword-only сигнатура модуля) — payload несёт `os.getpid()` этого
     процесса-обёртки: честный ДОЛГОЖИВУЩИЙ pid (обёртка живёт весь
     проход, в отличие от однократного интерактивного CLI-вызова
     loop_lock.py, который умирает через секунду после acquire).
     --stale-hours/TTL-override НЕ существует и не вводится этим скриптом
     (B1 плана): единственный источник свежести — state/sla.yaml
     thresholds.lock_stale, как и для интерактивного пути.
  3. BUSY (лок жив, чужой holder) → печать + строка в
     state/orchestrator-log.md + exit 0. claude.cmd НЕ запускается вовсе
     (закрывает N2 планировщиковой ветки кодом, не дисциплиной).
  4. claude запускается `subprocess.Popen(...)` БЕЗ PIPE (stdout/stderr
     наследуются от heartbeat.cmd, который уже перенаправляет их в
     logs/heartbeat.log) — c PIPE внуки процесса держат хэндлы и
     `wait()` после `taskkill` виснет мимо таймаута (B4). Единственная
     env-надбавка — `AO3_LOOP_HOLDER=<holder>` дочернему процессу
     (B4: никаких мутаций os.environ/setx текущего процесса).
  5. `p.wait(timeout=MAX_PASS_SEC)`; MAX_PASS_SEC — см. compute_max_pass_sec()
     (кламп R1 из sla lock_stale, инвариант «лок не переживает обёртку»
     стоит на коде, не на дисциплине).
  6. `TimeoutExpired` → `taskkill /T /F /PID <p.pid>` (дерево по PID
     Popen-объекта: TimeoutExpired САМ не несёт pid, а `run()` убивал бы
     только прямого ребёнка, не внуков — appium/adb-процессы конвейера
     плодят именно такие деревья) → повторный `p.wait(30)` (проглатывает
     собственный TimeoutExpired, не даёт ему всплыть мимо finally) →
     пост-проверка `tasklist` — дерево реально мертво?
       - мертво  → release штатный, строка «timeout-kill release=ok»;
       - живо    → лок НЕ снимается (release пропускается, работает
         TTL-страховка), строка «timeout-kill release=kill-failed» +
         печать «kill-failed, лок оставлен» (снятие открыло бы наложение
         со следующим каденсом при реально живом первом проходе).
     Ошибка/отсутствие самого `taskkill`-бинаря НЕ съедает release —
     `_taskkill_tree` никогда не бросает исключение наружу (ловит OSError
     сама), решение «снимать ли лок» принимается ТОЛЬКО по факту
     `tasklist`-проверки, не по коду возврата `taskkill`.
  7. `finally:` — release (если разрешён п.6) + журнальная строка M4
     ЧЕРЕЗ `log_append.append_orchestrator` (прямой импорт модуля, не
     subprocess) `("heartbeat-обёртка", "heartbeat_wrap",
     "logs/heartbeat.log", "<исход>")`. Строка пишется при ЛЮБОЙ смерти
     child (нормальный exit, исключение, timeout). Остаток N6 (некрит-10,
     явно): эта строка доказывает «проход был/умер» — потерянные события
     ВНУТРИ самого прохода она не восстанавливает; это закрывает
     дисциплина журнала координатора (open-dispatches).

     Критик-фикс (2026-08-09, единственная непокрытая ветка спеки п.7):
     `ll.release(...)` возвращает `(rcode, lines)` — rcode!=0 (REFUSED)
     раньше молча отбрасывался, и журнальная строка несла штатный исход,
     хотя лок обёртки на самом деле НЕ был снят. REFUSED здесь ОЖИДАЕМЫЙ
     исход fallback-сценария M2 (SKILL qa-loop сам держит свой
     qa-loop-holder, либо перехватил лок заново после того, как холдер
     обёртки пропал/протух до её собственного release) — не инцидент.
     Такой REFUSED дописывает в исход журнальной строки суффикс
     " release=refused-expected" (напр. `exit=0 release=refused-expected`)
     — детекторы (чек 3б session-handoff «пары start/orchestrator-строка»,
     doctor — только для holder'ов `heartbeat:*`, здесь холдер уже не наш,
     значит doctor и не должен его видеть) получают явный сигнал вместо
     тихого «release=ok». Само исключение `ll.release()` (не REFUSED, а
     реальный сбой вызова) ловится отдельно и НЕ съедает M4-строку —
     суффикс `" release=error:<кратко>"`.

heartbeat_wrap.py включён в MECHANISM_PREFIXES scripts/mechanism_gate.py
(некрит-9): он решает, состоится ли проход /qa-loop вовсе — гейт-класс
на пути исполнения, не генератор/свипер.

Запуск (production, без флагов — heartbeat.cmd вызывает ровно так, абсолютным
путём python.exe — критик-фикс п.7, симметрия с CLAUDE_CMD, PATH задачи
планировщика не измерен):
  C:/Users/user/AppData/Local/Programs/Python/Python312/python.exe scripts/heartbeat_wrap.py
Флаги ниже — ТОЛЬКО для тестов/смок-прогонов (пути лока/креды claude
никогда не переопределяются в heartbeat.cmd):
  --lock-file/--reaps-file/--escalations-file/--sla-file — временные пути
  --claude-cmd — путь к исполняемому файлу вместо claude.cmd (смок kill-дерева)

Бюджет прогонов (spec-heartbeat-budget.md v1, 2026-08-15): state/
heartbeat-budget.txt — одно целое число, gitignored, интерфейс оператора
намеренно без CLI/хелперов. Проверяется СТРОГО ПОСЛЕ BUSY-шортката (BUSY
не жжёт бюджет) и СТРОГО ДО запуска ребёнка: файла нет — безлимит (текущее
поведение байт-в-байт); N>0 — декремент ПОСЛЕ успешного Popen (неудачный
spawn бюджет не жжёт); N<=0 — ребёнка не запускать, `schtasks /change /tn
AO3-QA-Heartbeat /disable`, строка в orchestrator-log + эскалация
`HEARTBEAT-BUDGET` в state/escalations.md (файл НЕ удаляется; отказ
disable логируется, no-op-тик); мусор в файле — не запускать + та же
эскалация, задачу НЕ отключать (оператор чинит файл). См.
_read_budget/_write_budget/_schtasks_disable/_write_singleton_escalation.

Детектор серийной быстрой смерти + возврат бюджета
(spec-heartbeat-fastdeath.md v2, 2026-08-15, инцидент 8+ подряд мёртвых
тиков на протухшем OAuth-токене): `rc != 0 AND runtime < FAST_DEATH_SEC`
(120с, без env-ручки) — быстрая смерть. state/heartbeat-fastdeath.json
(gitignored, .gitignore:33-44) копит счётчик подряд; ЛЮБАЯ ошибка
чтения/парса трактуется как count=0 (самовосстановление, в отличие от
budget-файла — намерение оператора здесь не пишется руками). При
count>=3 подряд — singleton-эскалация `HEARTBEAT-CHILD-DEATH`
[heartbeat:child-death] (та же машинерия, что HEARTBEAT-BUDGET —
обобщено в `_write_singleton_escalation`); текст эскалации указывает на
`logs/fallback-YYYYMMDD.log` (Д1: живой производственный вызыватель —
`run_fallback_pass`, не замороженный `logs/heartbeat.log`) и называет ДВА
пути сброса — сторож сбрасывает реестр при живом прогрессе окна ИЛИ
пробный запуск при `last_ts` реестра старше 6ч (спека:
docs/tasks/factory-visible-window.md §Д п.6 «Единый стартовый гейт»;
реализация — `factory_watchdog._series_blocked`).

**Правка семантики (Д п.6, консолидированная секция — серии
ДИЗЪЮНКТНЫ, ЗАМЕНЯЕТ прежнее правило ниже):** сброс счётчика (rc=0)
происходит ТОЛЬКО при `child_rc == 0`. Медленный отказ (`rc != 0 И
runtime >= FAST_DEATH_SEC`) БОЛЬШЕ НЕ СБРАСЫВАЕТ fastdeath (прежняя
редакция ошибочно трактовала «не-быстрая смерть» как здоровую — на
самом деле это ОТДЕЛЬНАЯ серия `slowdeath`, её домен и хранилище — ВНЕ
этого модуля, `state/factory-watchdog.json`/`scripts/factory_watchdog.py`,
т.к. `run_pass` не знает о слоudeath вовсе, а `run_fallback_pass` не
хранит эту серию сам — её накапливает вызывающий сторож по возвращённому
исходу). `timeout_kill` НЕ трогает fastdeath НИКАК (ни инкремент, ни
сброс) — она относится ТОЛЬКО к slowdeath-серии сторожа. Задача
планировщика НЕ отключается (смерть-серия самоизлечивается, когда
причину чинит оператор). Если бюджет прогонов был сожжён в ЭТОМ
проходе (декремент прошёл без OSError) и смерть быстрая — бюджет
возвращается перечиткой+инкрементом (не восстановлением старого
значения — конкурентная правка оператора не должна быть затёрта; ветка
`run_fallback_pass` бюджет не трогает вовсе, budget_enabled=False). Обе
записи (счётчик, эскалация) никогда не бросают исключение наружу
`run_pass`/`run_fallback_pass` (класс BL-4 — писатель эскалаций на
занятом escalations.md раньше сиротил лок; починено для ВСЕХ площадок
singleton-эскалаций через общий catch внутри
`_write_singleton_escalation`). См.
_read_fastdeath/_write_fastdeath/_fastdeath_increment/_fastdeath_reset/
_fastdeath_after_spawn/_refund_budget.

Общее ядро `_run_child(...)` (Д п.2): acquire/spawn(Popen без
PIPE)/wait-или-timeout-kill/tasklist/release/REFUSED/fastdeath-учёт —
ОДНА реализация, вызывается ОБОИМИ `run_pass` (через `pre_spawn`/
`post_spawn`-хуки — бюджет-логика ЦЕЛИКОМ остаётся в `run_pass`,
`_run_child` о бюджете не знает) И `run_fallback_pass` (через
`pre_spawn`=`on_spawn`-обёртку, `on_pass_done`-CAS-хук, `stdout_target`=
файловый дескриптор `logs/fallback-*.log`). Дублирование
acquire/kill-tree/tasklist/release/REFUSED/fastdeath между двумя точками
входа запрещено (D-0043) — обе используют эту функцию.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import secrets
import subprocess
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

import log_append as la
import loop_lock as ll
import sla_utils

REPO = Path(__file__).resolve().parent.parent
DEFAULT_LOCK_FILE = REPO / "state" / "loop.lock"
DEFAULT_REAPS_PATH = REPO / "state" / "loop-lock-reaps.json"
DEFAULT_ESCALATIONS_PATH = REPO / "state" / "escalations.md"
DEFAULT_SLA_PATH = REPO / "state" / "sla.yaml"
DEFAULT_BUDGET_PATH = REPO / "state" / "heartbeat-budget.txt"
DEFAULT_FASTDEATH_PATH = REPO / "state" / "heartbeat-fastdeath.json"

# Тот же абсолютный путь, что был в прежнем heartbeat.cmd (npm global
# claude.cmd не гарантированно в PATH scheduled-контекста Task Scheduler).
CLAUDE_CMD = r"C:\Users\user\AppData\Roaming\npm\claude.cmd"
DEFAULT_CHILD_ARGS = ["-p", "/qa-loop 3", "--model", "sonnet"]

DEFAULT_MAX_PASS_MIN = 100.0
TIMEOUT_KILL_WAIT_S = 30

RULE = "heartbeat-обёртка"
AGENT = "heartbeat_wrap"
ARTIFACT = "logs/heartbeat.log"

# --- бюджет прогонов (spec-heartbeat-budget.md v1, 2026-08-15) ------------
# Носитель: state/heartbeat-budget.txt — одно целое число, gitignored
# (per-host операционное состояние, класс emulator-session.json). Файла
# нет => безлимит (текущее поведение байт-в-байт). Интерфейс оператора —
# ОДНО число в ОДНОМ файле, намеренно без CLI/хелперов (внешняя критика
# фабрики: «правила лечатся добавлением правил»).
TASK_NAME = "AO3-QA-Heartbeat"
_BUDGET_MAX_BYTES = 1024
_BUDGET_UNLIMITED = "unlimited"
_BUDGET_CORRUPT = "corrupt"
HEARTBEAT_BUDGET_KEY = "HEARTBEAT-BUDGET"
_BUDGET_EXHAUSTED_MSG = ("бюджет исчерпан, задача самоотключена; продолжение — "
                         "новое число в файл + Enable")
_BUDGET_CORRUPT_MSG = ("state/heartbeat-budget.txt не парсится в целое число — "
                       "проход остановлен; задача НЕ отключена, оператор чинит "
                       "файл, следующий тик подхватит")
# AT-BUG-041-класс (EOL-перегон): '[^\r\n]*' вместо '.*$' под (?m) — см.
# докстринг loop_lock.LOOP_LINE_RE, тот же образец, ключ здесь ФИКСИРОВАН
# (не нумеруется LOOP-N) — состояние singleton, не растущий счётчик.
# Регекс строки собирается внутри _write_singleton_escalation() из key/tag
# через re.escape(...) (Патч E, критик rework attempt 2) — здесь больше не
# захардкожен, единственный источник правды HEARTBEAT_BUDGET_KEY + тег
# "heartbeat:budget", передаваемые вызывающим кодом.
HEARTBEAT_BUDGET_TAG = "heartbeat:budget"

# --- детектор серийной быстрой смерти + возврат бюджета
# (spec-heartbeat-fastdeath.md v2, 2026-08-15) ------------------------------
FAST_DEATH_SEC = float(os.environ.get("AO3_FASTDEATH_SEC", "120") or 120)
# r6-фикс (Д п.6): MAX_PASS_SEC env-настраиваем — малое значение могло дать
# timeout_kill за <120с, что раньше давало ОБА инкремента (fastdeath И
# slowdeath) на одном исходе. FAST_DEATH_SEC теперь ТОЖЕ env-настраиваем
# (AO3_FASTDEATH_SEC, дефолт 120) исключительно для тестов на границе (M6);
# production не переопределяет.
FAST_DEATH_ESCALATE_AT = 3
HEARTBEAT_CHILD_DEATH_KEY = "HEARTBEAT-CHILD-DEATH"
HEARTBEAT_CHILD_DEATH_TAG = "heartbeat:child-death"

# --- лимиты подписки (spec-factory-window v8, 2026-08-18) -----------------
# ОТДЕЛЬНЫЙ класс исхода, НЕ fastdeath: ребёнок умирает за секунды с rc=1 и
# единственной строкой вида "You've hit your weekly limit · resets 2am
# (Europe/Paris)". Это НЕ поломка (чинить нечего) и НЕ повод будить
# оператора тревогой — до сброса ни окно, ни резерв проехать не могут
# ФИЗИЧЕСКИ, поэтому и спавнить резерв бессмысленно (эпизод 2026-08-17:
# 4 запуска в лимитное окно, 7 тостов, ни один не назвал причину).
#
# Носитель факта — вывод ребёнка в logs/fallback-*.log: PIPE не
# используется by construction (класс B4, внуки держали бы хэндлы и wait()
# висел бы мимо таймаута), поэтому детект читает ХВОСТ файла по смещению,
# снятому ДО спавна. Нет log_path (тестовый/CLI-путь) — детекта нет,
# поведение прежнее байт-в-байт.
# Критик-раунд v8.1 (блокер Б2): `\w+` НЕ матчит дефисный span — «5-hour
# limit» проваливался целиком, а докстринг ниже объявлял его поддержанным.
# Промах регекса ОТКАТЫВАЕТ поведение к до-v8 (ложные тосты «поломка»), то
# есть класс не деградирует мягко — он исчезает. Поэтому: (а) `[\w-]+`;
# (б) ВТОРАЯ альтернатива под формулировку «usage limit reached … reset at».
# Список формулировок вендора эмпирически НЕ исчерпан (воспроизвести лимит
# со стенда нельзя, F-30) — при появлении новой строки чинится добавлением
# паттерна сюда, юнит на вариант обязателен.
USAGE_LIMIT_PATTERNS = (
    re.compile(r"you'?ve\s+hit\s+your\s+(?P<span>[\w-]+)\s+limit"
               r"(?:[^\r\n]*?resets?(?:\s+at)?\s+(?P<reset>[^\r\n]*))?",
               re.IGNORECASE),
    re.compile(r"(?:claude\s+)?usage\s+limit\s+reached"
               r"(?:[^\r\n]*?reset(?:s|\s+at|\s+\w+\s+at)?\s+(?P<reset>[^\r\n]*))?",
               re.IGNORECASE),
)
# «2am (Europe/Paris)», «11:30pm (Europe/Paris)», «2am» — час/минуты/
# am-pm/зона; всё, кроме часа, опционально (формулировка вендора может
# смениться — тогда reset_ts=None и потребитель берёт консервативный
# дефолт, но КЛАСС исхода всё равно распознан).
_RESET_CLOCK_RE = re.compile(
    r"(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<ampm>am|pm)?"
    r"(?:[^(\r\n]*\((?P<tz>[A-Za-z_]+/[A-Za-z_]+)\))?",
    re.IGNORECASE)
USAGE_LIMIT_TAIL_BYTES = 8192
# Н4 (критик v8.1): сколько ПОСЛЕДНИХ непустых строк среза считать зоной
# «причина смерти». Фраза вендора живёт и в самом репо — без сужения любое
# её эхо в выводе ребёнка при rc!=0 открывало бы окно тишины на часы.
USAGE_LIMIT_TAIL_LINES = 40
# Сброса не распознали — сколько спать до следующей пробы. Совпадает с
# прежним слепым probe-окном fastdeath-серии (_series_blocked, 6ч): при
# нераспознанном формате поведение НЕ хуже прежнего.
USAGE_LIMIT_DEFAULT_SLEEP_H = 6.0
HEARTBEAT_USAGE_LIMIT_KEY = "HEARTBEAT-USAGE-LIMIT"
HEARTBEAT_USAGE_LIMIT_TAG = "heartbeat:usage-limit"

# --- Б-1б (критик rework attempt 2, 2026-08-19): горизонт вменяемости
# reset_ts ------------------------------------------------------------------
# `reset_ts`, посчитанный ДАЛЬШЕ горизонта — почти наверняка ошибка парсера
# (сорванная зона/дата), а не реальный лимит вендора: `weekly` — реальный
# класс лимита длится максимум ~неделю (запас до 8 суток — под дрейф
# часовых поясов у границы недели), `5-hour` — на порядок короче (запас до
# суток), неизвестный/иной span — консервативный дефолт (не ýже weekly).
# Горизонт применяется В `parse_usage_limit` (после `_parse_reset_ts`) — он
# не может жить в `_parse_reset_ts` самой (та не знает span).
USAGE_LIMIT_HORIZON_WEEKLY_DAYS = 8.0
USAGE_LIMIT_HORIZON_5HOUR_DAYS = 1.0
USAGE_LIMIT_HORIZON_DEFAULT_DAYS = 8.0


def _usage_limit_horizon_hours(span: str) -> float:
    """span (уже .lower()) -> горизонт вменяемости в часах. Пустой/
    незнакомый span -> дефолт (8 суток, не ýже weekly)."""
    s = (span or "").lower()
    if s == "5-hour":
        return USAGE_LIMIT_HORIZON_5HOUR_DAYS * 24.0
    if s == "weekly":
        return USAGE_LIMIT_HORIZON_WEEKLY_DAYS * 24.0
    return USAGE_LIMIT_HORIZON_DEFAULT_DAYS * 24.0

# --- Н3 (критик-хвост v8, docs/HANDOFF.md §7а, 2026-08-19): дата в подсказке
# сброса --------------------------------------------------------------------
# Баг ДО этой правки: `_RESET_CLOCK_RE` искало ЛЮБЫЕ 1-2 цифры как час —
# «resets Aug 20 2am» отдавало час=20 (взятый из «20» дня месяца), а «2am»
# и сама дата пропадали без следа: «resets Aug 20 2am» в 10:00Z читалось
# как «сегодня в 20:00Z» вместо «завтра в 02:00Z». Молчаливо — ни один
# note/print не называл дату замеченной-и-отброшенной. Починка: дата
# ищется и ВЫРЕЗАЕТСЯ из строки ДО поиска часа — её цифры больше не могут
# попасть в часовой регекс.
_MONTH_NUMS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
              "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
_MONTH_PART = (r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
              r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|"
              r"dec(?:ember)?")
# «Aug 20», «August 20th», «20 Aug» — месяц ТЕКСТОМ (числовые даты вида
# «08/20» вендор пока не присылал, F-30 — список форм не исчерпан) в любом
# порядке относительно дня. Месяц — явный список (не `[a-z]*`-обвес вокруг
# аббревиатуры): открытый `[a-z]*` матчил бы «novel 20» как «nov»+«el» и
# давал ложную дату там, где её нет.
_RESET_DATE_RE = re.compile(
    r"\b(?:(?P<month1>" + _MONTH_PART + r")\.?\s+(?P<day1>\d{1,2})(?:st|nd|rd|th)?\b"
    r"|(?P<day2>\d{1,2})(?:st|nd|rd|th)?\s+(?P<month2>" + _MONTH_PART + r")\.?\b)",
    re.IGNORECASE)

# --- Б-1г (критик rework attempt 2, 2026-08-19): дата — только ДО часа / в
# ТОЙ ЖЕ клаузе -----------------------------------------------------------
# Баг ДО этой правки: `_RESET_DATE_RE.search` искал ПЕРВЫЙ дата-подобный
# токен во ВСЁМ хвосте подсказки сброса, даже если он относился к СОСЕДНЕЙ
# мысли, не к моменту сброса. Витнес-кейсы критика: «resets 2am
# (Europe/Paris) — plan renewed Aug 3» (дата после эм-даша — посторонняя
# заметка), «resets 2am; see changelog May 1 for details» (после точки с
# запятой), «resets at 3pm (Europe/Paris) [ref 12 Mar incident]» (после
# квадратной скобки) — во всех трёх «дата» на самом деле не про сброс, но
# старый код подставлял её. Круглые скобки — НЕ разделитель клаузы: именно в
# них живёт IANA-зона («2am (Europe/Paris)»), обрезать по ним нельзя.
_CLAUSE_BREAK_RE = re.compile(r"[—–;\[]")


def _clause_text(reset_text: str) -> str:
    """Урезает подсказку сброса до конца ПЕРВОЙ клаузы (см. докстринг
    `_CLAUSE_BREAK_RE`) — дата и час ищутся только в этой клаузе, не во всём
    хвосте строки. Разделителей нет -> строка не меняется (регресс-щит для
    прежних форматов вендора, где хвост — это ровно момент сброса)."""
    text = reset_text or ""
    m = _CLAUSE_BREAK_RE.search(text)
    return text[:m.start()] if m else text


def _extract_reset_date(reset_text: str) -> tuple:
    """Ищет дату («Aug 20»/«20 Aug»-подобный токен) в подсказке сброса —
    ДО поиска часа. Возвращает `(month, day, rest, warn)`:
      - `month`/`day` — int|None (None — дата не найдена ИЛИ найдена, но
        синтаксически невалидна: несуществующий месяц/день вне 1-31);
      - `rest` — `reset_text` С ВЫРЕЗАННЫМ токеном даты (даже при невалидной
        дате: её цифры НЕ должны достаться часовому регексу — консервативный
        фолбэк, не молчаливая порча часа);
      - `warn` — диагностика для НЕ-МОЛЧАЛИВОГО лога (печатает вызывающий),
        если токен похож на дату, но не проходит валидацию."""
    m = _RESET_DATE_RE.search(reset_text or "")
    if not m:
        return None, None, (reset_text or ""), None
    month_name = (m.group("month1") or m.group("month2") or "")[:3].lower()
    day_raw = m.group("day1") or m.group("day2")
    rest = reset_text[:m.start()] + " " + reset_text[m.end():]
    month = _MONTH_NUMS.get(month_name)
    try:
        day = int(day_raw)
    except (TypeError, ValueError):
        return None, None, rest, f"день не распознан в дате {m.group(0)!r}"
    if month is None or not (1 <= day <= 31):
        return None, None, rest, f"дата вне диапазона/не распознана: {m.group(0)!r}"
    return month, day, rest, None


def _parse_reset_ts(reset_text: str, now: datetime.datetime) -> tuple:
    """«2am (Europe/Paris)» / «Aug 20 2am (Europe/Paris)» -> ближайший
    БУДУЩИЙ момент этого локального времени (и, если дата названа, ЭТОЙ
    даты) в UTC. Возвращает `(datetime|None, note)`.

    Н3 (2026-08-19): дата ищется `_extract_reset_date` ПЕРВОЙ и вырезается
    из текста — час ищется по остатку, так что дата больше НЕ маскируется
    под час (см. докстринг `_RESET_DATE_RE`). Б-1г (критик rework attempt 2,
    2026-08-19): поиск ведётся только в ПЕРВОЙ клаузе подсказки (см.
    `_clause_text`) — дата/час из СОСЕДНЕЙ мысли (после эм-даша/точки с
    запятой/квадратной скобки) больше не подставляется.

    Б-1е (критик rework attempt 2, 2026-08-19): дата-подобный, но
    СИНТАКСИЧЕСКИ невалидный токен (день вне 1-31) и дата, невалидная
    КАЛЕНДАРНО (29/30 февраля и т.п.) — ОДНО правило: `reset_ts=None`
    ЦЕЛИКОМ, час НЕ «спасается» отдельно от даты (раньше день вне 1-31 терял
    дату молча и час из остатка строки давал правдоподобный, но
    сфабрикованный результат — «Aug 32 2am» превращалось в «сегодня/завтра
    2am», хотя намерение сообщения было разбито; календарно-невозможная
    дата уже давала None по построению — теперь оба класса дают его
    одинаково). Дата без распознаваемого часа — тот же консервативный
    фолбэк. Всё — с диагностической строкой в лог (`print`, класс BL-4), а
    не молчаливым угадыванием.

    Зона без tzdata (голый Windows-хост без пакета `tzdata` — зависимость
    НЕ объявлена в framework/requirements.txt намеренно: механизм обязан
    работать и без неё) -> `(None, "<причина>")`; потребитель берёт
    консервативный дефолт. Класс E-негатива: отсутствие зоны — не факт
    «лимита нет», а неизвестность ВРЕМЕНИ."""
    clause = _clause_text(reset_text or "")
    month, day, clock_text, date_warn = _extract_reset_date(clause)
    if date_warn:
        # Б-1е: НЕ продолжаем к поиску часа — дата-подобный невалидный токен
        # обнуляет ВЕСЬ момент сброса, час из остатка строки не «спасает»
        # результат отдельно от битой даты.
        print(f"usage-limit: подсказка {reset_text!r} несёт похожий на дату "
              f"токен, но {date_warn} — момент сброса неизвестен ЦЕЛИКОМ "
              "(консервативный фолбэк, час НЕ восстанавливается отдельно "
              "от невалидной даты)")
        return None, f"дата-подобный токен невалиден: {reset_text!r}"

    m = _RESET_CLOCK_RE.search(clock_text or "")
    if not m:
        if month is not None:
            print(f"usage-limit: подсказка {reset_text!r} несёт дату "
                  f"{month:02d}-{day:02d}, но без распознаваемого часа — "
                  "момент сброса неизвестен (консервативный фолбэк)")
            return None, f"дата без часа: {reset_text!r}"
        return None, "время сброса не распознано"

    hour = int(m.group("hour"))
    minute = int(m.group("minute") or 0)
    ampm = (m.group("ampm") or "").lower()
    if ampm == "pm" and hour < 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None, f"время сброса вне диапазона: {reset_text!r}"

    tz_name = m.group("tz")
    tzinfo = datetime.timezone.utc
    note = "зона не названа — трактована как UTC"
    if tz_name:
        try:
            from zoneinfo import ZoneInfo          # локальный импорт: см. докстринг
            tzinfo = ZoneInfo(tz_name)
            note = ""
        except Exception as e:                      # ZoneInfoNotFoundError и родня
            return None, f"зона {tz_name} недоступна ({e.__class__.__name__})"

    local_now = now.astimezone(tzinfo)
    if month is not None:
        try:
            target = local_now.replace(month=month, day=day, hour=hour, minute=minute,
                                       second=0, microsecond=0)
        except ValueError as e:
            print(f"usage-limit: дата {month:02d}-{day:02d} невалидна для года "
                  f"{local_now.year} ({e}) — момент сброса неизвестен "
                  "(консервативный фолбэк)")
            return None, f"дата невалидна для года {local_now.year}: {reset_text!r}"
        if target <= local_now:
            # Б-1а (критик rework attempt 2, 2026-08-19): раньше здесь был
            # откат на СЛЕДУЮЩИЙ ГОД (`target.replace(year=target.year+1)`).
            # Вендор НИКОГДА не называет год в подсказке — если названный
            # момент (месяц+день+час) уже в прошлом относительно `now`, это
            # почти наверняка НЕ «через год», а устаревшее/битое сообщение
            # (эхо старого лога, сдвиг часов на сервере и т.п.). Откат на год
            # вперёд превращал такую путаницу в правдоподобную, но
            # ФАБРИКОВАННУЮ дату — консервативный фолбэк честнее: момент
            # сброса неизвестен, потребитель берёт USAGE_LIMIT_DEFAULT_SLEEP_H.
            print(f"usage-limit: названный момент {month:02d}-{day:02d} "
                  f"{hour:02d}:{minute:02d} уже прошёл относительно "
                  f"{local_now.isoformat()} — момент сброса неизвестен "
                  "(консервативный фолбэк, БЕЗ отката на следующий год)")
            return None, f"названный момент уже прошёл: {reset_text!r}"
    else:
        target = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= local_now:
            target += datetime.timedelta(days=1)
    return target.astimezone(datetime.timezone.utc), note


def parse_usage_limit(text: str, now: datetime.datetime) -> dict | None:
    """Распознаёт в тексте сообщение о лимите подписки.

    Возвращает `None` (не лимит) либо dict: `raw` (сама строка),
    `span` ("weekly"/"5-hour"/...), `reset_ts` (datetime UTC|None),
    `reset_hint` (сырой хвост «2am (Europe/Paris)»|None), `note`
    (почему `reset_ts` пуст, если пуст).

    Б-1б (критик rework attempt 2, 2026-08-19): `reset_ts`, посчитанный
    ДАЛЬШЕ горизонта вменяемости (`_usage_limit_horizon_hours(span)`),
    отбрасывается тем же консервативным фолбэком (`reset_ts=None` +
    диагностика в `print`/`note`) — момент дальше горизонта почти наверняка
    ошибка парсера, не реальный лимит вендора."""
    if not text:
        return None
    # ПОСЛЕДНЕЕ совпадение по ВСЕМ паттернам: в срезе может лежать эхо
    # прошлой строки, актуальна самая свежая.
    m = None
    for pattern in USAGE_LIMIT_PATTERNS:
        for candidate in pattern.finditer(text):
            if m is None or candidate.start() >= m.start():
                m = candidate
    if m is None:
        return None
    groups = m.groupdict()                     # у второго паттерна нет span
    raw = m.group(0).strip()
    span = (groups.get("span") or "").lower()
    reset_hint = (groups.get("reset") or "").strip() or None
    reset_ts, note = (None, "строка без части «resets»")
    if reset_hint:
        reset_ts, note = _parse_reset_ts(reset_hint, now)
    if reset_ts is not None:
        horizon_h = _usage_limit_horizon_hours(span)
        delta_h = (reset_ts - now).total_seconds() / 3600.0
        if delta_h > horizon_h:
            print(f"usage-limit: reset_ts {reset_ts.isoformat()} "
                  f"({delta_h:.1f}ч от now) дальше горизонта вменяемости "
                  f"({horizon_h:.0f}ч, span={span!r}) — момент сброса "
                  "неизвестен (консервативный фолбэк)")
            note = (f"reset_ts за горизонтом вменяемости ({horizon_h:.0f}ч "
                    f"для span={span!r}): было {reset_ts.isoformat()}")
            reset_ts = None
    return {"raw": raw, "span": span,
            "reset_ts": reset_ts, "reset_hint": reset_hint, "note": note}


def read_usage_limit(log_path, offset: int, now: datetime.datetime,
                     tail_bytes: int = USAGE_LIMIT_TAIL_BYTES,
                     tail_lines: int = USAGE_LIMIT_TAIL_LINES) -> dict | None:
    """Читает НАСТОЯЩИЙ ХВОСТ нашего среза лога ребёнка и отдаёт
    `parse_usage_limit` по нему.

    Критик-раунд v8.1 (блокер Б1): прежняя версия делала `seek(offset)` +
    `read(8192)`, то есть читала ГОЛОВУ среза, а не хвост, вопреки
    собственному докстрингу. Замер критика: лимит после 8КБ вывода — детект
    ЕСТЬ, после 9КБ — НЕТ, молча; реальный лог успешного прохода
    (`logs/fallback-20260818.log`) весит 6580 байт, то есть 80% окна, а
    stderr ребёнка слит в тот же дескриптор. Отказ был не гипотетическим:
    ребёнок, поработавший и упёршийся в лимит ПОСРЕДИ прохода, откатывал всё
    поведение к до-v8 (ложные тосты «поломка», слепой 6ч-probe).

    Нижняя граница чтения = `max(offset, size - tail_bytes)`: наш срез
    (никогда не читаем чужой вывод до спавна) И его хвост.

    `tail_lines` (Н4) сужает поверхность ложноположительного детекта: фраза
    вендора встречается и в самом репо (этот файл, тесты), а любой её вывод
    ребёнка при rc!=0 открывал бы многочасовое окно тишины. Ищем только в
    последних непустых строках — там, где живёт причина смерти.

    Non-throwing (BL-4): нечитаемый файл/битая кодировка -> None.

    Н-собрат (2026-08-19): чтение хвоста вынесено в `_read_log_tail` — тот
    же читатель кормит и `classify_death_reason` (auth/network/unknown), не
    только лимит подписки (D-0043: одна реализация чтения хвоста)."""
    text = _read_log_tail(log_path, offset, tail_bytes, tail_lines)
    if text is None:
        return None
    return parse_usage_limit(text, now)


def _read_log_tail(log_path, offset: int, tail_bytes: int, tail_lines: int) -> str | None:
    """Читает НАСТОЯЩИЙ ХВОСТ среза лога (offset..EOF, максимум `tail_bytes`
    с конца файла), последние `tail_lines` непустых строк — общий читатель
    для usage-limit-детекта (`read_usage_limit`) И классификатора причины
    смерти (`classify_death_reason`, ниже). Нижняя граница чтения =
    `max(offset, size - tail_bytes)` — то же правило, что было в
    `read_usage_limit` (см. её докстринг, критик-раунд v8.1 Б1/Н4).

    `log_path=None` (тестовый/CLI-путь без файла) -> `None` (детекта нет).
    Non-throwing (BL-4): нечитаемый файл/битая кодировка -> `None`, не
    исключение наружу."""
    if log_path is None:
        return None
    try:
        path = Path(log_path)
        size = path.stat().st_size
        start = max(0, int(offset or 0), size - max(0, int(tail_bytes)))
        with path.open("rb") as fh:
            fh.seek(start)
            chunk = fh.read()
    except (OSError, ValueError) as e:
        print(f"log-tail: хвост лога не прочитан ({e}) — детекта нет")
        return None
    text = chunk.decode("utf-8", errors="replace")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if tail_lines and tail_lines > 0:
        lines = lines[-tail_lines:]
    return "\n".join(lines)


# --- Н-собрат критик-входа v8 (docs/HANDOFF.md §7а, D-0043, 2026-08-19) -----
# «Внешняя невозможность, трактованная как поломка исполнителя» — не только
# лимит подписки. Протухший OAuth/разлогин (прецедент HEARTBEAT-AUTH,
# закрыт перелогином оператора 2026-08-15 — реальная строка вывода,
# logs/heartbeat.log:146, "Failed to authenticate: OAuth session expired
# and could not be refreshed") и обрыв сети/5xx дают РОВНО ТУ ЖЕ немую
# жалобу «N быстрых смертей подряд — см. logs/fallback-*.log», от которой
# заводился v8-детектор лимита. Механизм чтения хвоста лога (_read_log_tail
# выше) уже стоит на пути исполнения — здесь распознавание расширено ещё
# двумя классами + явным unknown-фолбэком (класс E-негатива: канал сломан/
# причина нераспознана — НЕ факт «поломки без причины», а неизвестность
# причины).
DEATH_REASON_LIMIT = "limit"
DEATH_REASON_AUTH = "auth"
DEATH_REASON_NETWORK = "network"
DEATH_REASON_UNKNOWN = "unknown"

DEATH_REASON_LABELS = {
    DEATH_REASON_LIMIT: "лимит подписки",
    DEATH_REASON_AUTH: "логин/авторизация протухли",
    DEATH_REASON_NETWORK: "сеть/сервер недоступны",
    DEATH_REASON_UNKNOWN: "причина не распознана",
}

# --- Н-2 (критик rework attempt 2, 2026-08-19): сужение регексов ----------
# Три отдельных промаха, обнаруженных на ревью:
#   (а) голый `\b401\b` матчил ЛЮБОЕ число 401 (номер батча, хэш коммита,
#       строку лога) как «протухшая авторизация» — сужено до HTTP-контекста:
#       401 засчитывается ТОЛЬКО в ОДНОЙ строке текста с «http»/«status»/
#       «unauthorized» (см. `_auth_401_in_http_context`).
#   (б) «Internal Server Error» матчила и ВНУТРИ Python-трейсбека, где это
#       часто имя ИСКЛЮЧЕНИЯ приложения («InternalServerError: ...»), не
#       сетевой отказ — вынесена в отдельный regex, не срабатывающий при
#       наличии маркера `Traceback (most recent call last)`.
#   (в) «429 Too Many Requests» — rate-limit ОТ САМОГО API, не сетевой сбой
#       (сеть/сервер ДОСТУПНЫ, просто отказали по квоте) — убрана из
#       network-класса целиком. Выбор: `unknown` (не `network`) — влияния на
#       поток управления это НЕ имеет (slowdeath/fastdeath серии копятся
#       одинаково для network/unknown), заводить отдельный DEATH_REASON_*
#       ради одной фразы без потребителя избыточно; при появлении
#       потребителя (напр. отдельный cooldown для rate-limit) — новый класс
#       заводится тогда.
_AUTH_REASON_RE = re.compile(
    r"failed to authenticate|oauth|unauthorized|"
    r"(?:invalid|expired|revoked)\s+(?:api[- ]?key|token|credential|session)|"
    r"not\s+logged\s+in|please\s+(?:log|sign)\s*in|re-?authenticate|"
    r"credentials?\s+(?:invalid|missing|not\s+found)",
    re.IGNORECASE)

_BARE_401_RE = re.compile(r"\b401\b")
_HTTP_CONTEXT_WORDS_RE = re.compile(r"https?|status|unauthorized", re.IGNORECASE)


def _auth_401_in_http_context(text: str) -> bool:
    """Н-2(а): голый `401` засчитывается как auth ТОЛЬКО если та же СТРОКА
    текста несёт `http`/`status`/`unauthorized` — номер батча/хэш коммита/
    произвольное число не должны ложно срабатывать."""
    for line in (text or "").splitlines():
        if _BARE_401_RE.search(line) and _HTTP_CONTEXT_WORDS_RE.search(line):
            return True
    return False


_NETWORK_REASON_RE = re.compile(
    r"econnrefused|econnreset|etimedout|enotfound|eai_again|getaddrinfo|"
    r"socket hang up|connection refused|connection reset|"
    r"network\s+(?:error|is\s+unreachable|unreachable)|fetch failed|"
    r"dns\s+(?:resolution|lookup)\s+failed|bad gateway|service unavailable|"
    r"gateway timeout",
    re.IGNORECASE)

_TRACEBACK_MARKER_RE = re.compile(r"Traceback \(most recent call last\)", re.IGNORECASE)
_INTERNAL_SERVER_ERROR_RE = re.compile(r"internal server error", re.IGNORECASE)


def classify_death_reason(tail_text: str | None) -> str:
    """Классифицирует ХВОСТ лога ребёнка (см. `_read_log_tail`) по причине
    быстрой смерти: `auth`/`network`/`unknown`. `limit` сюда НЕ входит — его
    распознаёт `parse_usage_limit`; вызывающий код (`run_fallback_pass`)
    проверяет лимит ПЕРВЫМ (он специфичнее — несёт момент сброса) и зовёт
    эту функцию только для остатка. Пустой/`None`/нечитаемый хвост ->
    `unknown` (канал сломан ≠ причина известна).

    Н-2 (2026-08-19): «Internal Server Error» НЕ засчитывается внутри
    Python-трейсбека (см. `_TRACEBACK_MARKER_RE`); «429 Too Many Requests» —
    НЕ `network` вовсе (rate-limit API, не сбой сети/сервера) -> `unknown`;
    голый `401` — только в HTTP-контексте той же строки (см.
    `_auth_401_in_http_context`)."""
    if not tail_text:
        return DEATH_REASON_UNKNOWN
    if _AUTH_REASON_RE.search(tail_text) or _auth_401_in_http_context(tail_text):
        return DEATH_REASON_AUTH
    if _NETWORK_REASON_RE.search(tail_text):
        return DEATH_REASON_NETWORK
    if (not _TRACEBACK_MARKER_RE.search(tail_text)
            and _INTERNAL_SERVER_ERROR_RE.search(tail_text)):
        return DEATH_REASON_NETWORK
    return DEATH_REASON_UNKNOWN


def _fastdeath_revert_one(fastdeath_path: Path, escalations_path: Path | None = None,
                          now: datetime.datetime | None = None) -> str:
    """Откатывает РОВНО ОДИН инкремент, сделанный текущим вызовом (исход
    переклассифицирован в usage_limit — смерть от лимита поломкой НЕ
    является и серию поломок копить не должна).

    НЕ сбрасывает счётчик в 0: прежние инкременты могли быть настоящими
    отказами, их история — не наша (класс «чини экземпляр, который сам
    создал»).

    Н1 (критик v8.1): откат счётчика ОБЯЗАН откатывать и эскалацию, которую
    этот счётчик успел поднять. `_fastdeath_increment` пишет singleton
    `HEARTBEAT-CHILD-DEATH` при достижении порога ДО того, как мы узнаём
    причину; без переписывания в человеко-читаемом файле оставалась ложная
    «поломка» при чистом реестре — реестр и эскалация расходились (замер
    критика: count=2 + смерть от лимита -> реестр 2, а в escalations.md
    «3 быстрых смертей подряд»). Non-throwing (BL-4)."""
    try:
        data = _read_fastdeath(fastdeath_path)
        count = int(data.get("count") or 0)
        if count <= 0:
            return ""
        was_escalated = count >= FAST_DEATH_ESCALATE_AT
        count -= 1
        _write_fastdeath(fastdeath_path, {
            "count": count,
            "first_ts": data.get("first_ts") if count else None,
            "last_ts": data.get("last_ts") if count else None,
            "last_rc": data.get("last_rc") if count else None,
        })
        if was_escalated and count < FAST_DEATH_ESCALATE_AT and escalations_path is not None:
            _write_singleton_escalation(
                Path(escalations_path), HEARTBEAT_CHILD_DEATH_KEY,
                HEARTBEAT_CHILD_DEATH_TAG,
                "ПЕРЕКЛАССИФИЦИРОВАНО: последняя смерть — лимит подписки, не "
                f"поломка; серия откачена до {count} (порог {FAST_DEATH_ESCALATE_AT}). "
                "Человеку чинить нечего: резерв ждёт сброса лимита. См. "
                "logs/fallback-*.log",
                now or _utcnow())
        return f" fastdeath-откат={count}"
    except Exception as e:                          # non-throwing (BL-4)
        print(f"usage-limit: откат fastdeath не удался: {e}")
        return ""


def _fastdeath_annotate_reason(fastdeath_path: Path, escalations_path: Path,
                               reason: str | None, now: datetime.datetime, *,
                               runtime: float | None = None,
                               log_hint: str = "logs/fallback-*.log") -> None:
    """Н-собрат (2026-08-19): дописывает класс причины (`auth`/`network`/
    `unknown`) в реестр серии ПОСЛЕ инкремента. Инкремент сам (внутри
    `_fastdeath_after_spawn`, вызванного `_run_child` СРАЗУ по получении
    `rc`) причины не знает — хвост лога читает только `run_fallback_pass`,
    ПОСЛЕ `_run_child` вернул управление. Если серия УЖЕ эскалирована
    (`HEARTBEAT-CHILD-DEATH` уже написан БЕЗ причины) — переписывает ТУ ЖЕ
    singleton-строку, ДОБАВЛЯЯ класс причины К прежнему формату сообщения
    `_fastdeath_increment` (тот же `log_hint`-артефакт и spec-указатель —
    регресс-щит: прежний текст называл КОНКРЕТНЫЙ `logs/fallback-
    YYYYMMDD.log`, переписывание не смеет заменить его безымянной
    звёздочкой, см. test_fastdeath_escalation_message_verbatim_*).

    Н-1 (критик rework attempt 2, 2026-08-19): `runtime` — та же величина,
    что несёт исходное сообщение `_fastdeath_increment` (`r["runtime"]`
    вызывающего `run_fallback_pass`); ПЕРЕЗАПИСАННОЕ этой функцией
    сообщение раньше теряло `runtime=` целиком — регресс относительно
    исходного текста, который эта функция замещает.

    `reason=None` — no-op (ветка usage_limit: свой класс, эту функцию не
    зовут). Non-throwing (BL-4)."""
    if reason is None:
        return
    try:
        data = _read_fastdeath(fastdeath_path)
        if data["count"] == 0:
            return
        data["last_reason"] = reason
        _write_fastdeath(fastdeath_path, data)
        if data["count"] >= FAST_DEATH_ESCALATE_AT:
            label = DEATH_REASON_LABELS.get(reason, reason)
            runtime_txt = f"{runtime:.1f}с" if runtime is not None else "мгновенно (spawn-failed)"
            message = (
                f"{data['count']} быстрых смертей подряд, класс причины: "
                f"{label} [{reason}], окно {data.get('first_ts')}.."
                f"{data.get('last_ts')}, последний rc={data.get('last_rc')}, "
                f"runtime={runtime_txt}; первые строки причины — {log_hint}; "
                "причину чинит оператор/Lead — сбросит сторож при живом "
                "прогрессе окна ИЛИ пробный запуск через 6ч (спека: "
                "docs/tasks/factory-visible-window.md §Д п.6 «Единый "
                "стартовый гейт»; реализация — factory_watchdog._series_blocked)")
            _write_singleton_escalation(escalations_path, HEARTBEAT_CHILD_DEATH_KEY,
                                        HEARTBEAT_CHILD_DEATH_TAG, message, now)
    except Exception as e:                          # non-throwing (BL-4)
        print(f"FASTDEATH reason-annotate failed (non-throwing): {e}")

# --- ночной резерв (Д1, консолидированная секция spec-factory-window v7) --
DEFAULT_FALLBACK_CHILD_ARGS = ["-p", "/qa-loop 5", "--model", "sonnet"]
DEFAULT_FALLBACK_LOG_DIR = REPO / "logs"


def fallback_log_path(now: datetime.datetime, *, log_dir: Path = DEFAULT_FALLBACK_LOG_DIR) -> Path:
    """`logs/fallback-YYYYMMDD.log` (Д п.2) — М4-артефакт ночного резерва на
    ВСЕХ исходах run_fallback_pass (busy/spawned/spawn_failed/timeout_kill);
    fastdeath-эскалация указывает на этот же путь."""
    return Path(log_dir) / f"fallback-{now.strftime('%Y%m%d')}.log"


def _fallback_artifact_rel(now: datetime.datetime) -> str:
    """REPO-относительная строка `logs/fallback-YYYYMMDD.log` — М4-
    артефакт-колонка `run_fallback_pass` (Б1, критик-раунд Д1): та же
    дата-схема, что `fallback_log_path`, но НЕЗАВИСИМАЯ от фактического
    `log_path`-параметра (тесты могут передать произвольный tmp-путь для
    самого файла — колонка orchestrator-log остаётся стандартной, симметрия
    с `run_pass.ARTIFACT`, которая тоже не равна реальному пути
    перенаправления stdout)."""
    return f"logs/fallback-{now.strftime('%Y%m%d')}.log"


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _fmt_ts_utc(dt: datetime.datetime | None) -> str:
    """ISO-Z из aware/naive datetime (naive — трактуется как UTC, тот же
    образец, что вся ts-запись модуля). None -> пустая строка."""
    if dt is None:
        return ""
    if dt.tzinfo is not None:
        dt = dt.astimezone(datetime.timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_holder(now: datetime.datetime | None = None) -> str:
    """holder = heartbeat:<ISO>:<nonce8> — нонс на каждый запуск (B4:
    утёкший env прошлого запуска не совпадает ни с чем)."""
    now = now or _utcnow()
    nonce = secrets.token_hex(4)
    return f"heartbeat:{now.strftime('%Y-%m-%dT%H:%M:%SZ')}:{nonce}"


def compute_max_pass_sec(sla_path: Path) -> tuple[float, bool]:
    """MAX_PASS_SEC [R1] = min(env AO3_HEARTBEAT_MAX_PASS_MIN (default 100
    мин), 0.9 * loop_lock.load_lock_stale_hours(sla) * 60) * 60 — кламп
    ВЫЧИСЛЯЕТСЯ из sla (не хардкод: порог живёт в state/sla.yaml, его
    снижение не должно молча возвращать дыру B1).

    Возвращает (MAX_PASS_SEC, ужат_ли_по_sla). Юниты: env 150 при TTL 2ч
    → 108 мин (ужат); default env (100) при TTL 1ч → 54 мин (ужат)."""
    try:
        env_min = float(os.environ.get("AO3_HEARTBEAT_MAX_PASS_MIN", DEFAULT_MAX_PASS_MIN))
    except (TypeError, ValueError):
        env_min = DEFAULT_MAX_PASS_MIN
    ttl_h = sla_utils.load_lock_stale_hours(Path(sla_path))
    sla_cap_min = 0.9 * ttl_h * 60
    if sla_cap_min < env_min:
        return sla_cap_min * 60.0, True
    return env_min * 60.0, False


def _popen(args: list[str], *, env: dict, stdout=None, stderr=None) -> subprocess.Popen:
    """Обёртка вокруг Popen; подменяется в тестах. БЕЗ PIPE (B4): внуки
    процесса (appium/adb/gradle деревья, что claude.cmd порождает внутри
    /qa-loop) держали бы хэндлы stdout/stderr и `wait()` после `taskkill`
    висел бы мимо таймаута. `stdout`/`stderr` — ТОЛЬКО прямой файловый
    дескриптор (Д п.2, `run_fallback_pass`) или `None` (наследование от
    родителя, прежнее поведение `run_pass`) — НИКОГДА `subprocess.PIPE`
    (тот же класс B4: анонимный pipe без читателя блокирует ребёнка)."""
    return subprocess.Popen(args, env=env, stdout=stdout, stderr=stderr)


def _taskkill_tree(pid: int) -> tuple[int, str]:
    """taskkill /T /F /PID <pid> — дерево процессов по PID Popen-объекта.
    НИКОГДА не бросает исключение наружу (OSError — бинарь не найден и
    т.п. — ловится и превращается в код 127): решение «снимать ли лок»
    принимается ТОЛЬКО постфактум по `_tasklist_alive`, не по коду
    возврата этой функции — ошибка/отсутствие taskkill сама по себе НЕ
    съедает release."""
    try:
        p = subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except OSError as e:
        return 127, str(e)


def _tasklist_alive(pid: int) -> bool:
    """Пост-проверка R2: дерево реально мертво после taskkill? Ошибка
    самого вызова tasklist трактуется КОНСЕРВАТИВНО — pid считается
    живым (лок не снимается, TTL-страховка сработает позже вместо
    рискованного двойного release). Унифицировано (критик-фикс п.4,
    2026-08-09) с scripts/doctor.py::_pid_alive: ошибка tasklist ==
    «неизвестно», не «мёртв»/«жив» само по себе — здесь unknown
    сознательно схлопывается в True (безопасный дефолт «не снимать»,
    цена ошибки — лишний цикл до TTL, не двойной release); doctor не
    может так же схлопнуть unknown в «жив» молча, потому что там это
    напрямую решает ok/warn отображаемого чек-пункта — там unknown
    остаётся ТРЕТЬИМ состоянием (см. _pid_alive возвращает bool | None)."""
    try:
        p = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if p.returncode != 0:
            return True
        return str(pid) in (p.stdout or "")
    except OSError:
        return True


def _read_budget(budget_path: Path) -> int | str:
    """Читает state/heartbeat-budget.txt БАЙТАМИ (не read_text/encoding=
    "utf-8" — критик-фикс BL-1/BL-2, rework attempt 2, 2026-08-15).

    Оператор пишет файл из PowerShell 5.1: `echo 3 > file` даёт
    UTF-16LE-с-BOM (read_text(encoding="utf-8") падал UnicodeDecodeError
    НАРУЖУ run_pass ПОСЛЕ взятого лока — сирота до TTL); `'3' |
    Set-Content -Encoding UTF8` даёт UTF-8-с-BOM (raw.strip() не считал
    BOM-символ '﻿' пробельным — ложный `_BUDGET_CORRUPT` на валидном
    числе). Декодирование — каскадом "utf-8-sig" (снимает BOM сам, если
    он есть, и корректно читает голый UTF-8 без BOM) -> при неудаче
    "utf-16" (второй по вероятности вид, который реально пишет
    PowerShell 5.1; сам определяет BE/LE по BOM) -> при неудаче обоих —
    corrupt. Чтение ограничено `_BUDGET_MAX_BYTES` (файл — ОДНО число,
    оператор не пишет туда мегабайты; отсутствие потолка держало бы в
    памяти произвольно большой файл на каждом тике).

    Возвращает int (бюджет), `_BUDGET_UNLIMITED` (файла нет — безлимит,
    текущее поведение байт-в-байт) или `_BUDGET_CORRUPT` (файл есть, но
    НЕ парсится целым числом — ошибка чтения/оба декодирования упали/
    после strip пусто/int() падает). Намерение лимита БЫЛО — corrupt
    fail LOUD в сторону остановки, не тихий безлимит."""
    if not budget_path.exists():
        return _BUDGET_UNLIMITED
    try:
        with budget_path.open("rb") as f:
            raw = f.read(_BUDGET_MAX_BYTES)
    except OSError:
        return _BUDGET_CORRUPT
    try:
        text = raw.decode("utf-8-sig")
    except (UnicodeDecodeError, UnicodeError):
        try:
            text = raw.decode("utf-16")
        except (UnicodeDecodeError, UnicodeError):
            return _BUDGET_CORRUPT
    text = text.strip()
    if not text:
        return _BUDGET_CORRUPT
    try:
        return int(text)
    except ValueError:
        return _BUDGET_CORRUPT


def _write_budget(budget_path: Path, value: int) -> None:
    """Декремент бюджета — вызывается ТОЛЬКО после успешного Popen
    ребёнка (бюджет = фактически стартовавшие проходы)."""
    budget_path.write_text(str(value), encoding="utf-8")


def _schtasks_disable(task_name: str = TASK_NAME) -> tuple[int, str]:
    """schtasks /change /tn <task_name> /disable — самоотключение при
    исчерпании бюджета. НИКОГДА не бросает исключение наружу (тот же
    приём, что _taskkill_tree): ребёнка в любом случае уже не запускаем,
    этот вызов только best-effort отключает планировщик — отказ
    логируется, не роняет тик (следующий тик повторит попытку, пока файл
    бюджета всё ещё <= 0)."""
    try:
        p = subprocess.run(["schtasks", "/change", "/tn", task_name, "/disable"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except OSError as e:
        return 127, str(e)


def _append_m4_safe(fields: list[str]) -> None:
    """Non-throwing M4-писатель (класс BL-4, критик r2 ночного контура):
    `la.append_orchestrator` был ЕДИНСТВЕННЫМ бросающим писателем на
    production-пути резерва — OSError (журнал занят) пропускал финальную
    запись state тика (следующий тик закрывал эпизод собственной записью
    резерва), а SystemExit из `la._verify_environment` пролетал мимо
    catch-all `main()` (except Exception) и ронял задачу планировщика.
    Ловим ОБА named-класса; KeyboardInterrupt намеренно не глотаем."""
    try:
        la.append_orchestrator(fields)
    except (Exception, SystemExit) as e:      # noqa: BLE001 — см. докстринг
        print(f"M4 write failed: {e}")


def _write_singleton_escalation(escalations_path: Path, key: str, tag: str, message: str,
                                now: datetime.datetime) -> None:
    """Дописывает/обновляет ОДНУ открытую singleton-эскалацию с фиксированным
    `key`/`tag` — обобщение прежнего `_write_budget_escalation` (D-0043,
    класс singleton-эскалаций спеки spec-heartbeat-fastdeath.md v2 §«Рефакторинг»),
    тот же приём, что loop_lock._write_loop_escalation, но ключ НЕ
    нумеруется (LOOP-N) — состояние singleton, второй одновременной
    причины того же класса быть не может, дедуп по (key, tag). Тег
    `[heartbeat:*]` (не `[sla:...]`) — sla_sweep.rewrite_registry трогает
    только свои [sla:*]-строки (см. докстринг sla_sweep.py); эскалация
    переживает его проходы, пока оператор не удалит строку сам (штатный
    способ закрыть — см. ll.ESCALATIONS_HEADER). Регекс строки собирается
    из key/tag через re.escape(...) (Патч E).

    Класс BL-4 (спека п.2а, воспроизведено критиком 2026-08-15 на
    ДЕЙСТВУЮЩЕМ коде): раньше OSError записи (напр. PermissionError из
    os.replace по занятому редактором escalations.md) пробрасывался
    НАРУЖУ run_pass ПОСЛЕ acquire — loop.lock оставался сиротой до TTL, а
    M4-строка не писалась вовсе. Здесь — тот же приём «никогда не
    бросает наружу», что _taskkill_tree/_schtasks_disable: OSError
    ловится ВНУТРИ, печатается `ESCALATION write failed: <e>`, вызывающий
    run_pass продолжает штатный finally/release.

    Rework attempt 2 (критик B1, 2026-08-15): `except OSError` ловил не
    весь класс BL-4 — `read_bytes().decode("utf-8")` на не-utf8
    escalations.md бросает UnicodeDecodeError (подкласс ValueError, НЕ
    OSError) — критик воспроизвёл ровно ту же сироту-лок пробу раунда 1,
    другим входом. `except (OSError, ValueError)` закрывает оба класса
    отказа записи (I/O и декодирование)."""
    try:
        line_re = re.compile(
            r"(?m)^- \[(?P<ts>[^\]]+)\] \*\*" + re.escape(key) +
            r"\*\* \[" + re.escape(tag) + r"\] — [^\r\n]*")
        stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        text = escalations_path.read_bytes().decode("utf-8") if escalations_path.exists() else ""
        eol = "\r\n" if "\r\n" in text else "\n"

        m = line_re.search(text)
        if m:
            new_line = f"- [{m.group('ts')}] **{key}** [{tag}] — {message}"
            new_text = text[:m.start()] + new_line + text[m.end():]
        else:
            if not text:
                text = ll.ESCALATIONS_HEADER
            elif not text.endswith("\n"):
                text += eol
            new_text = text + f"- [{stamp}] **{key}** [{tag}] — {message}{eol}"

        escalations_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = escalations_path.with_name(escalations_path.name + ".tmp")
        tmp.write_bytes(new_text.encode("utf-8"))
        os.replace(tmp, escalations_path)
    except (OSError, ValueError) as e:   # ValueError ⊃ UnicodeDecodeError: не-utf8 escalations.md
        print(f"ESCALATION write failed: {e}")


def _read_fastdeath(fastdeath_path: Path) -> dict:
    """Читает state/heartbeat-fastdeath.json. ЛЮБАЯ ошибка чтения/парса
    (файла нет, битый json, не dict) трактуется как count=0 —
    самовосстановление (спека п.2, В ОТЛИЧИЕ от budget, где corrupt =
    непонятное намерение оператора и fail loud: этот файл пишется/
    читается ТОЛЬКО механизмом, оператор его не редактирует)."""
    # Н-собрат (2026-08-19): "last_reason" — класс причины (auth/network/
    # unknown), дописывается ПОСЛЕ инкремента (_fastdeath_annotate_reason,
    # см. её докстринг) — старые файлы без ключа получают None из default,
    # обратная совместимость (merge через out.update(data) ниже).
    default = {"count": 0, "first_ts": None, "last_ts": None, "last_rc": None,
              "last_reason": None}
    if not fastdeath_path.exists():
        return dict(default)
    try:
        data = json.loads(fastdeath_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return dict(default)
    if not isinstance(data, dict):
        return dict(default)
    out = dict(default)
    out.update(data)
    # Rework attempt 2 (критик B2, 2026-08-15): приведение "count" к int
    # ЖИЛО у вызывающих (_fastdeath_increment/_fastdeath_reset) — не
    # число (списки/строки-не-число) там либо TypeError'ил НАРУЖУ
    # run_pass (сирота-лок), либо (при рассинхроне веток) проглатывался
    # общим except Exception вокруг p.wait и портил M4-строку ложным
    # exit=error. Приведение — ЗДЕСЬ, внутри охраняемого читателя: не
    # число => весь файл трактуем как count=0 (спека п.2, тот же принцип,
    # что битый json).
    try:
        out["count"] = int(out.get("count") or 0)
    except (TypeError, ValueError):
        return dict(default)
    return out


def _write_fastdeath(fastdeath_path: Path, data: dict) -> None:
    """Пишет state/heartbeat-fastdeath.json. НИКОГДА не бросает исключение
    наружу (класс BL-4, спека п.2а) — тот же приём, что
    _taskkill_tree/_schtasks_disable: OSError ловится и печатается
    `FASTDEATH write failed: <e>`.

    Rework attempt 2 (критик B1, симметрично _write_singleton_escalation):
    `except (OSError, ValueError)` — json.dumps сам не декодирует, но тот
    же класс отказа («I/O и не-текстовые проблемы записи») закрывается
    единообразно с писателем эскалаций."""
    try:
        fastdeath_path.parent.mkdir(parents=True, exist_ok=True)
        fastdeath_path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
    except (OSError, ValueError) as e:
        print(f"FASTDEATH write failed: {e}")


def _fastdeath_increment(fastdeath_path: Path, escalations_path: Path,
                         now: datetime.datetime, rc: int | None,
                         runtime: float | None,
                         log_hint: str = "logs/heartbeat.log") -> str:
    """Инкрементирует счётчик серии быстрых смертей (spawn-failed или
    rc!=0 и runtime < FAST_DEATH_SEC), пишет файл, при достижении порога
    FAST_DEATH_ESCALATE_AT пишет/обновляет singleton-эскалацию
    HEARTBEAT-CHILD-DEATH. Возвращает M4-суффикс
    ` fastdeath=<N>[ escalated]` (спека п.6). Порядок (спека п.2а/п.4,
    пин 14): счётчик пишется ДО попытки записи эскалации — падение
    писателя эскалаций не теряет инкремент.

    Rework attempt 2 (критик B3, решение Lead — чинить код, не спеку):
    `last_ts`/`first_ts` — момент СМЕРТИ ребёнка (спека п.2), НЕ `now`
    начала прохода: `stamp` берётся из `_utcnow()` здесь, на месте.
    Аргумент `now` остаётся ТОЛЬКО меткой строки реестра эскалаций
    (`_write_singleton_escalation`, семантика ll._write_loop_escalation —
    момент записи строки, не момент события).

    Rework attempt 2 (Б2, критик-раунд Д1): `log_hint` — параметризованный
    путь-указатель в тексте эскалации (симметрия M4-артефакта). Дефолт
    `"logs/heartbeat.log"` — для (депрекированного) `run_pass`;
    `run_fallback_pass` передаёт СВОЙ `logs/fallback-YYYYMMDD.log` через
    `_run_child(..., fastdeath_log_hint=...)`. Текст также называет ДВА
    пути сброса (шапка модуля :165-172 — целевой текст, этот код
    приводится к нему): сторож сбрасывает реестр при живом прогрессе окна
    ИЛИ пробный запуск при `last_ts` реестра старше 6ч — НЕ «сбросится сам
    первым здоровым проходом» (прежняя формулировка была неточной: для
    `run_fallback_pass` сброс тоже возможен ТОЛЬКО через здоровый
    (`rc==0`) резервный проход, но триггерится СТОРОЖЕМ, не «само собой»)."""
    data = _read_fastdeath(fastdeath_path)
    prev_count = data["count"]                       # уже int (B2: приведено в _read_fastdeath)
    count = prev_count + 1
    stamp = _utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")  # B3: момент смерти, не начала прохода
    first_ts = data.get("first_ts") if prev_count > 0 and data.get("first_ts") else stamp
    _write_fastdeath(fastdeath_path, {"count": count, "first_ts": first_ts,
                                      "last_ts": stamp, "last_rc": rc})
    suffix = f" fastdeath={count}"
    if count >= FAST_DEATH_ESCALATE_AT:
        runtime_txt = f"{runtime:.1f}с" if runtime is not None else "мгновенно (spawn-failed)"
        message = (
            f"{count} быстрых смертей подряд, окно {first_ts}..{stamp}, "
            f"последний rc={rc}, runtime={runtime_txt}; первые строки причины — "
            f"{log_hint}; причину чинит оператор/Lead — сбросит сторож при живом "
            "прогрессе окна ИЛИ пробный запуск через 6ч (спека: "
            "docs/tasks/factory-visible-window.md §Д п.6 «Единый стартовый "
            "гейт»; реализация — factory_watchdog._series_blocked)")
        _write_singleton_escalation(escalations_path, HEARTBEAT_CHILD_DEATH_KEY,
                                    HEARTBEAT_CHILD_DEATH_TAG, message, now)
        suffix += " escalated"
    return suffix


def _fastdeath_reset(fastdeath_path: Path) -> str:
    """Сбрасывает счётчик серии в 0. **Правка Д п.6 (консолидированная
    секция, серии ДИЗЪЮНКТНЫ):** вызывается ТОЛЬКО при `child_rc == 0`
    (см. `_fastdeath_after_spawn` ниже) — прежняя редакция вызывала это и
    на медленной смерти (`rc != 0`, `runtime >= FAST_DEATH_SEC`), что
    ошибочно роднило «не-быструю смерть» со «здоровым проходом»; теперь
    медленный отказ НЕ трогает fastdeath вовсе (своя серия — slowdeath,
    вне этого модуля). Здоровый проход при УЖЕ нулевом/отсутствующем
    счётчике файл НЕ переписывает и НЕ создаёт — запись только при сбросе
    с ненулевого значения. Возвращает суффикс `` или ` fastdeath-reset`."""
    data = _read_fastdeath(fastdeath_path)
    if data["count"] == 0:                            # уже int (B2: приведено в _read_fastdeath)
        return ""
    _write_fastdeath(fastdeath_path, {"count": 0, "first_ts": None,
                                      "last_ts": None, "last_rc": None})
    return " fastdeath-reset"


def _fastdeath_after_spawn(fastdeath_path: Path, escalations_path: Path,
                           now: datetime.datetime, rc: int, runtime: float,
                           log_hint: str = "logs/heartbeat.log") -> tuple[bool, str]:
    """fastdeath-учёт ПОСЛЕ получения `rc` дочернего процесса (Д п.6,
    консолидированная секция — серии ДИЗЪЮНКТНЫ). Общая точка для
    `_run_child`, используется ОБОИМИ `run_pass`/`run_fallback_pass`:

    - `rc == 0` -> сброс (`_fastdeath_reset`), `fast_death=False`;
    - `rc != 0` И `runtime < FAST_DEATH_SEC` -> инкремент
      (`_fastdeath_increment`), `fast_death=True`;
    - `rc != 0` И `runtime >= FAST_DEATH_SEC` (медленный отказ) -> NO-OP:
      ни инкремент, ни сброс (домен медленных отказов — `slowdeath`,
      серия вне этого модуля, см. `scripts/factory_watchdog.py`).

    `timeout_kill` эту функцию НЕ зовёт вовсе (вызывающий код `_run_child`
    решает это до получения `rc`) — не инкрементирует и не сбрасывает
    fastdeath ни при каких условиях; DoD-юнит «timeout_kill не
    инкрементирует fastdeath, инкрементирует slowdeath» — вторая половина
    (slowdeath) проверяется в тестах `factory_watchdog.py` по возвращённому
    `outcome=="timeout_kill"`.

    Возвращает `(fast_death, suffix)`."""
    if rc == 0:
        return False, _fastdeath_reset(fastdeath_path)
    if runtime is not None and runtime < FAST_DEATH_SEC:
        return True, _fastdeath_increment(fastdeath_path, escalations_path, now, rc, runtime,
                                          log_hint=log_hint)
    return False, ""


def _refund_budget(budget_path: Path) -> str:
    """M-B: возврат бюджета после быстрой смерти (спека §«M-B»).
    ПЕРЕЧИТЫВАЕТ текущее значение (оператор мог переписать файл за время
    прохода — восстанавливать старое значение нельзя, класс clobber) и,
    если оно int, пишет current+1. unlimited/corrupt — возврат
    пропускается со строкой `BUDGET refund skipped (<причина>)`; НЕ имеет
    права СОЗДАТЬ файл, если его нет (удаление оператором = «снять
    лимит»). OSError записи — та же защита, что у декремента (печать, не
    падение). Возвращает суффикс `` или ` budget-refunded`."""
    current = _read_budget(budget_path)
    if current == _BUDGET_UNLIMITED:
        print("BUDGET refund skipped (unlimited, файла нет)")
        return ""
    if current == _BUDGET_CORRUPT:
        print("BUDGET refund skipped (budget corrupt)")
        return ""
    new_value = current + 1
    try:
        _write_budget(budget_path, new_value)
    except OSError as e:
        print(f"BUDGET refund write failed: {e}")
        return ""
    print(f"BUDGET refund: +1 ({new_value})")
    return " budget-refunded"


def _release_and_finish(outcome: str, *, lock_file: Path, holder: str,
                        reaps_path: Path) -> None:
    """Release лока + M4-журнальная строка для РАННИХ budget-выходов
    (corrupt/exhausted/spawn-failed) — лок к этому месту уже НАШ (acquire
    вернул ACQUIRED выше по run_pass), в отличие от BUSY-ветки, где лок
    чужой и release не нужен. Тот же учёт REFUSED/исключения, что в
    финалке run_pass для пути с запущенным ребёнком (критик-фикс п.1/п.5,
    2026-08-09): REFUSED помечается суффиксом, исключение release() не
    съедает журнальную строку."""
    try:
        rcode, rlines = ll.release(lock_file=lock_file, holder=holder, reaps_path=reaps_path)
        for line in rlines:
            print(line)
        if rcode != 0:
            outcome += " release=refused-expected"
            print(f"REFUSED (ожидаемо, fallback-сценарий): holder={holder} "
                  "не совпал — лок обёртки не наш к моменту release")
    except Exception as e:
        outcome += f" release=error:{e}"
    _append_m4_safe([RULE, AGENT, ARTIFACT, outcome])


def _run_child(*, lock_file: Path, reaps_path: Path, escalations_path: Path, sla_path: Path,
              fastdeath_path: Path, claude_cmd: str, child_args: list[str],
              now: datetime.datetime, kill_wait_sec: float, max_pass_sec: float,
              holder: str, stdout_target=None, pre_spawn=None, on_spawn_failed=None,
              post_spawn=None, on_pass_done=None,
              fastdeath_log_hint: str = "logs/heartbeat.log") -> dict:
    """Общее ядро child-spawn-контура (Д п.2, консолидированная секция):
    acquire → (BUSY-выход | опциональный `pre_spawn`-абóрт | Popen → wait/
    timeout-kill/tasklist → release/REFUSED). Единственная реализация
    acquire/kill-tree/tasklist/release/REFUSED/fastdeath-учёта — вызывается
    ОБОИМИ `run_pass` (прежний контракт, holder=`heartbeat:*`) и
    `run_fallback_pass` (Д1, тот же holder-класс); дублирование запрещено
    (D-0043).

    Хуки (ВСЕ опциональны, run_pass и run_fallback_pass используют РАЗНЫЕ
    поднаборы — бюджет-логика ЦЕЛИКОМ в run_pass, эта функция о бюджете не
    знает):
    - `pre_spawn()` -> `str|None` — вызывается ПОСЛЕ успешного acquire, ДО
      Popen. Ненулевой (не-None) возврат = АБОРТ: Popen НЕ вызывается,
      `outcome="pre_spawn_abort"`, `abort_reason=<возврат>`; лок НЕ
      релизится этой функцией — вызывающий код (тот, кто уже держит его
      закрытым в pre_spawn) отвечает за release сам (run_pass использует
      это для budget corrupt/exhausted — `_release_and_finish` внутри
      самого хука). `None` = продолжить (побочные эффекты разрешены —
      run_fallback_pass инкрементирует fallback_runs здесь через `on_spawn`).
    - `on_spawn_failed()` — вызывается, если Popen ПОСЛЕ успешного
      `pre_spawn()` всё же бросил исключение (компенсирующий откат
      побочных эффектов pre_spawn, напр. отмена инкремента fallback_runs).
    - `post_spawn()` — вызывается СРАЗУ после успешного Popen (после
      фиксации `t_spawn`), ДО `p.wait(...)` — run_pass декрементирует
      бюджет здесь (byte-в-byte прежний порядок: t_spawn ДО декремента).
    - `on_pass_done(rc, runtime)` — вызывается ТОЛЬКО при `rc == 0`
      (результативный проход), ПОКА лок ЕЩЁ держится (до release в
      `finally`) — run_fallback_pass передаёт сюда CAS-инкремент
      `passes_done` мод-файла (Д п.3).

    Возвращает dict: `outcome` (`busy|pre_spawn_abort|spawn_failed|
    spawned|timeout_kill`), `abort_reason`, `spawn_error`, `wait_exception`,
    `child_rc`, `runtime`, `kill_alive`, `acquire_lines`, `print_lines`,
    `fast_death`, `fastdeath_suffix`, `release_called`, `release_rcode`,
    `release_lines`, `release_error`, `holder`."""
    result = {
        "outcome": None, "abort_reason": None, "spawn_error": None,
        "wait_exception": None, "child_rc": None, "runtime": None,
        "kill_alive": None, "acquire_lines": [], "print_lines": [],
        "fast_death": False, "fastdeath_suffix": "",
        "release_called": False, "release_rcode": None, "release_lines": [],
        "release_error": None, "holder": holder,
    }
    code, lines = ll.acquire(lock_file=lock_file, holder=holder, reaps_path=reaps_path,
                             escalations_path=escalations_path, sla_path=sla_path, now=now)
    result["acquire_lines"] = lines
    if code != 0:
        result["outcome"] = "busy"
        return result

    if pre_spawn is not None:
        abort_reason = pre_spawn()
        if abort_reason is not None:
            result["outcome"] = "pre_spawn_abort"
            result["abort_reason"] = abort_reason
            return result   # лок ОСТАЁТСЯ держан — release отвечает вызывающий (см. докстринг)

    child_env = dict(os.environ)
    child_env["AO3_LOOP_HOLDER"] = holder
    args = [claude_cmd, *child_args]
    popen_kwargs = {"env": child_env}
    if stdout_target is not None:
        popen_kwargs["stdout"] = stdout_target
        popen_kwargs["stderr"] = subprocess.STDOUT

    should_release = True
    try:
        try:
            p = _popen(args, **popen_kwargs)
        except Exception as e:
            result["outcome"] = "spawn_failed"
            result["spawn_error"] = e
            if on_spawn_failed is not None:
                on_spawn_failed()
            should_release = False   # ребёнок не запущен — нечего релизить ЗДЕСЬ (вызывающий сам)
            return result

        # t_spawn — сразу после успешного _popen: точка отсчёта runtime
        # для детектора быстрой/медленной смерти.
        t_spawn = time.monotonic()
        if post_spawn is not None:
            post_spawn()

        try:
            rc = p.wait(timeout=max_pass_sec)
            runtime = time.monotonic() - t_spawn
            result["outcome"] = "spawned"
            result["child_rc"] = rc
            result["runtime"] = runtime
            fast_death, suffix = _fastdeath_after_spawn(
                fastdeath_path, escalations_path, now, rc, runtime, log_hint=fastdeath_log_hint)
            result["fast_death"] = fast_death
            result["fastdeath_suffix"] = suffix
            if rc == 0 and on_pass_done is not None:
                on_pass_done(rc, runtime)
        except subprocess.TimeoutExpired:
            _taskkill_tree(p.pid)
            try:
                p.wait(kill_wait_sec)
            except subprocess.TimeoutExpired:
                pass  # пост-проверка ниже решает по факту, не по этому wait
            alive = _tasklist_alive(p.pid)
            result["outcome"] = "timeout_kill"
            result["kill_alive"] = alive
            if alive:
                should_release = False
                result["print_lines"].append("kill-failed, лок оставлен")
        except Exception as e:                      # child умер/raise
            result["outcome"] = "spawned"
            result["wait_exception"] = e
    finally:
        if should_release:
            result["release_called"] = True
            try:
                rcode, rlines = ll.release(lock_file=lock_file, holder=holder,
                                           reaps_path=reaps_path)
                result["release_rcode"] = rcode
                result["release_lines"] = rlines
            except Exception as e:
                result["release_error"] = e
    return result


def run_pass(*, lock_file: Path = DEFAULT_LOCK_FILE,
            reaps_path: Path = DEFAULT_REAPS_PATH,
            escalations_path: Path = DEFAULT_ESCALATIONS_PATH,
            sla_path: Path = DEFAULT_SLA_PATH,
            budget_path: Path = DEFAULT_BUDGET_PATH,
            fastdeath_path: Path = DEFAULT_FASTDEATH_PATH,
            claude_cmd: str = CLAUDE_CMD,
            child_args: list[str] | None = None,
            now: datetime.datetime | None = None,
            kill_wait_sec: float = TIMEOUT_KILL_WAIT_S) -> int:
    """Один проход обёртки: acquire → (BUSY-выход | бюджет-выход | запуск
    claude → wait/kill → release) → журнальная строка. Возвращает 0
    всегда (обёртка не должна ронять Task Scheduler ненулевым кодом ни на
    BUSY, ни на kill-failed, ни на исчерпанный/битый бюджет — это видимые
    WARN-состояния, не крах вызова). ПРЕЖНИЙ КОНТРАКТ (byte-в-byte) —
    тонкая обёртка над `_run_child` (см. её докстринг): вся бюджет-логика
    (проверка/декремент/refund) — ЗДЕСЬ, через `pre_spawn`/`post_spawn`
    хуки; `_run_child` о бюджете не знает.

    Бюджет (spec-heartbeat-budget.md v1) проверяется СТРОГО ПОСЛЕ
    BUSY-шортката (BUSY не жжёт бюджет) и СТРОГО ДО запуска ребёнка:
    N<=0 — самоотключение задачи + эскалация; файл есть, но не
    парсится — та же эскалация, задачу НЕ отключаем (оператор чинит
    файл). Оба ранних выхода обязаны освободить лок сами (в отличие от
    BUSY-ветки — там лок чужой).

    Детектор серийной быстрой смерти + возврат бюджета
    (spec-heartbeat-fastdeath.md v2, ПРАВКА Д п.6 — серии дизъюнктны) —
    BUSY и ранние budget-выходы fastdeath-счётчик НЕ трогают; spawn-failed
    и (rc!=0, runtime < FAST_DEATH_SEC) — инкремент (+ refund бюджета,
    если он был сожжён В ЭТОМ проходе); rc==0 — сброс в 0; (rc!=0,
    runtime >= FAST_DEATH_SEC) и timeout-kill — NO-OP (не инкремент, не
    сброс — медленные отказы больше НЕ трактуются как здоровые)."""
    lock_file = Path(lock_file)
    reaps_path = Path(reaps_path)
    escalations_path = Path(escalations_path)
    sla_path = Path(sla_path)
    budget_path = Path(budget_path)
    fastdeath_path = Path(fastdeath_path)

    # Критик-фикс BL-4 (rework attempt 2, 2026-08-15): compute_max_pass_sec
    # вычислен ЗДЕСЬ — ДО acquire(), а не между acquire и внутренним
    # try/finally, как было.
    max_pass_sec, clamped = compute_max_pass_sec(sla_path)
    if clamped:
        print(f"MAX_PASS ужат до {int(round(max_pass_sec / 60))} мин по sla lock_stale")

    now = now or _utcnow()
    holder = _new_holder(now)

    budget_state: dict = {"value": None, "burned": False}

    def _budget_pre_spawn():
        budget = _read_budget(budget_path)
        budget_state["value"] = budget
        if budget == _BUDGET_CORRUPT:
            print(f"BUDGET corrupt: {budget_path} не парсится в целое число — "
                  "проход не запускался")
            _write_singleton_escalation(escalations_path, HEARTBEAT_BUDGET_KEY,
                                        HEARTBEAT_BUDGET_TAG, _BUDGET_CORRUPT_MSG, now)
            _release_and_finish("budget=corrupt, проход не запускался",
                                lock_file=lock_file, holder=holder, reaps_path=reaps_path)
            return "corrupt"
        if budget != _BUDGET_UNLIMITED and budget <= 0:
            print("BUDGET<=0: бюджет исчерпан — проход не запускался (claude не вызван)")
            disable_rc, disable_out = _schtasks_disable()
            if disable_rc == 0:
                print(f"самоотключение: задача {TASK_NAME} disabled")
                disable_note = "disable=ok"
            else:
                print(f"disable failed: rc={disable_rc} out={disable_out.strip()}")
                disable_note = "disable=failed"
            _write_singleton_escalation(escalations_path, HEARTBEAT_BUDGET_KEY,
                                        HEARTBEAT_BUDGET_TAG, _BUDGET_EXHAUSTED_MSG, now)
            _release_and_finish(f"budget<=0, проход не запускался, {disable_note}",
                                lock_file=lock_file, holder=holder, reaps_path=reaps_path)
            return "exhausted"
        return None

    def _budget_post_spawn():
        # декремент ПОСЛЕ успешного Popen (бюджет = фактически стартовавшие
        # проходы). Критик-фикс BL-4: исключение здесь не роняет проход —
        # ребёнок УЖЕ запущен, ронять сейчас означало бы сирота-лок.
        budget = budget_state["value"]
        if budget != _BUDGET_UNLIMITED:
            try:
                _write_budget(budget_path, budget - 1)
                budget_state["burned"] = True
            except OSError as e:
                print(f"BUDGET decrement failed (бюджет не сожжён): {e}")

    r = _run_child(
        lock_file=lock_file, reaps_path=reaps_path, escalations_path=escalations_path,
        sla_path=sla_path, fastdeath_path=fastdeath_path, claude_cmd=claude_cmd,
        child_args=(child_args if child_args is not None else DEFAULT_CHILD_ARGS),
        now=now, kill_wait_sec=kill_wait_sec, max_pass_sec=max_pass_sec, holder=holder,
        stdout_target=None, pre_spawn=_budget_pre_spawn, post_spawn=_budget_post_spawn)

    for line in r["acquire_lines"]:
        print(line)

    if r["outcome"] == "busy":
        print(f"BUSY: holder={holder} — проход не запускался (claude не вызван)")
        _append_m4_safe([RULE, AGENT, ARTIFACT, "BUSY, проход не запускался"])
        return 0

    if r["outcome"] == "pre_spawn_abort":
        return 0   # budget-хук уже сделал release + M4-строку сам (_release_and_finish)

    for line in r["print_lines"]:
        print(line)

    if r["outcome"] == "spawn_failed":
        # Неудачный spawn не жжёт бюджет (декремент — в post_spawn, который
        # на этой ветке не достигается). spawn-failed мгновенный по
        # определению — считается серией (инкремент fastdeath, refund не
        # применим — бюджет тут не жёгся).
        outcome = f"spawn-failed:{r['spawn_error']}"
        outcome += _fastdeath_increment(fastdeath_path, escalations_path, now, None, None)
        print(outcome)
        _release_and_finish(outcome, lock_file=lock_file, holder=holder, reaps_path=reaps_path)
        return 0

    if r["outcome"] == "timeout_kill":
        outcome = "timeout-kill release=kill-failed" if r["kill_alive"] else "timeout-kill release=ok"
    elif r["wait_exception"] is not None:
        outcome = f"exit=error:{r['wait_exception']}"
    else:
        outcome = f"exit={r['child_rc']}"
        outcome += r["fastdeath_suffix"]
        if r["fast_death"] and budget_state["burned"]:
            outcome += _refund_budget(budget_path)

    for line in r["release_lines"]:
        print(line)
    if r["release_rcode"] not in (None, 0):
        # REFUSED: holder лока при finally уже не наш (fallback-сценарий M2
        # — SKILL сам держит свой qa-loop-holder, либо взял лок заново
        # после того, как наш пропал) — ОЖИДАЕМЫЙ исход, не инцидент.
        outcome += " release=refused-expected"
        print(f"REFUSED (ожидаемо, fallback-сценарий): holder={holder} "
              "не совпал — лок обёртки не наш к моменту release")
    elif r["release_error"] is not None:
        # [некритично п.5] Исключение release() НЕ должно съедать M4-строку.
        outcome += f" release=error:{r['release_error']}"

    _append_m4_safe([RULE, AGENT, ARTIFACT, outcome])
    return 0


def run_fallback_pass(*, child_args: list[str] | None = None, budget_enabled: bool = False,
                      on_spawn=None, on_pass_done=None,
                      claude_cmd: str = CLAUDE_CMD,
                      lock_file: Path = DEFAULT_LOCK_FILE,
                      reaps_path: Path = DEFAULT_REAPS_PATH,
                      escalations_path: Path = DEFAULT_ESCALATIONS_PATH,
                      sla_path: Path = DEFAULT_SLA_PATH,
                      fastdeath_path: Path = DEFAULT_FASTDEATH_PATH,
                      log_path: Path | None = None,
                      artifact: str | None = None,
                      now: datetime.datetime | None = None,
                      kill_wait_sec: float = TIMEOUT_KILL_WAIT_S) -> dict:
    """Ночной резерв (Д п.2, консолидированная секция) — ОДИН резервный
    проход `/qa-loop 5` через ОБЩЕЕ ядро `_run_child` (acquire/kill-tree/
    tasklist/release/REFUSED/fastdeath-учёт — та же реализация, что
    `run_pass`; дублирование запрещено, D-0043). Вызывается
    `scripts/factory_watchdog.py` при STALLED-триггере (К3+Д п.1).

    `budget_enabled=False` — бюджет-ветка (`state/heartbeat-budget.txt`,
    `_schtasks_disable`) ОТКЛЮЧЕНА КОДОМ: единственное легальное значение
    этого параметра — `False`; `True` роняет `NotImplementedError` СРАЗУ
    (до acquire, без побочных эффектов) — недостижимость поддерживается
    явным ассертом, не пустой веткой (иначе ноль в боевом
    `heartbeat-budget.txt` отключил бы саму задачу сторожа, архив v3 Б3).
    Бюджет ночи — ЕДИНСТВЕННО через `on_pass_done`/`passes_done` мод-файла
    (Д п.3), не через этот файл.

    `on_spawn` — коллбэк БЕЗ аргументов, вызывается ПОСЛЕ успешного
    acquire, ДО Popen (BUSY НЕ вызывает его вовсе — by construction, тот
    же порог, что в `_run_child.pre_spawn`). Компенсирующий non-throwing
    откат на `spawn_failed` (архив v3 F2) — `on_spawn` МОЖЕТ вернуть
    zero-arg callable «undo»: если Popen после этого всё же не удался,
    `run_fallback_pass` сам вызывает этот callable (под тем же локом, ДО
    release) — публичная сигнатура остаётся ОДНИМ коллбэком, как в спеке.

    `on_pass_done(rc, runtime)` — вызывается ТОЛЬКО при `rc == 0`, ПОКА
    лок ещё держится (Д п.3: CAS-инкремент `passes_done` ДО release);
    возвращаемое значение (снимок фактически записанных полей mode-файла
    ИЛИ `None` при отказе/`nonce`-несовпадении) уходит в исход как
    `mode_write` — сторож использует его как `self_write_snapshot`
    (атрибуция прогресса, Д п.4).

    `log_path` — файловый путь (НЕ PIPE, класс B4): stdout/stderr ребёнка
    открываются в РЕЖИМЕ ДОБАВЛЕНИЯ (`"ab"`) и закрываются по завершении.
    `None` — потоки наследуются от родителя (тесты/смок без записи в
    файл). Производственный вызывающий (`factory_watchdog.py`) передаёт
    `fallback_log_path(now)` (`logs/fallback-YYYYMMDD.log`).

    **Б1 (критик-раунд Д1): M4-строка ЗА КАЖДЫЙ резервный проход, НА ВСЕХ
    исходах (busy/spawned/spawn_failed/timeout_kill)** — через
    `log_append.append_orchestrator([RULE, AGENT, artifact, outcome])`,
    симметрия с `run_pass`. `artifact` — параметр (не жёстко привязан к
    фактическому `log_path`, тот же образец, что `run_pass.ARTIFACT` не
    равен реальному месту перенаправления stdout): по умолчанию
    `logs/fallback-YYYYMMDD.log`, вычисленный из `now`
    (`_fallback_artifact_rel`). Та же строка передаётся в
    `_fastdeath_increment(..., log_hint=artifact)` — текст эскалации
    HEARTBEAT-CHILD-DEATH указывает на ТОТ ЖЕ путь, что M4-колонка.

    Возвращает `{outcome: busy|spawned|spawn_failed|timeout_kill,
    child_rc, fast_death, holder, mode_write}`."""
    if budget_enabled:
        raise NotImplementedError(
            "run_fallback_pass: budget_enabled=True не реализован — бюджет "
            "ночного резерва ЕДИНСТВЕННО через on_pass_done/passes_done "
            "мод-файла (Д п.3); бюджет-ветка heartbeat-budget.txt отключена "
            "КОДОМ (архив v3 Б3) — см. докстринг")

    lock_file = Path(lock_file)
    reaps_path = Path(reaps_path)
    escalations_path = Path(escalations_path)
    sla_path = Path(sla_path)
    fastdeath_path = Path(fastdeath_path)

    max_pass_sec, _clamped = compute_max_pass_sec(sla_path)
    now = now or _utcnow()
    holder = _new_holder(now)
    args = child_args if child_args is not None else DEFAULT_FALLBACK_CHILD_ARGS
    artifact = artifact if artifact is not None else _fallback_artifact_rel(now)

    undo_box: dict = {"undo": None}
    mode_write_box: dict = {"value": None}

    def _pre_spawn():
        if on_spawn is not None:
            undo_box["undo"] = on_spawn()
        return None    # on_spawn НИКОГДА не абортит спавн — только считает

    def _on_spawn_failed():
        undo = undo_box["undo"]
        if undo is not None:
            try:
                undo()
            except Exception as e:            # non-throwing (BL-4) — откат best-effort
                print(f"FALLBACK on_spawn undo failed: {e}")

    def _on_pass_done(rc, runtime):
        if on_pass_done is not None:
            mode_write_box["value"] = on_pass_done(rc, runtime)

    log_fh = None
    log_offset = 0
    if log_path is not None:
        log_path = Path(log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        # смещение ДО спавна — граница «наш вывод» для usage-limit детекта
        # (v8). Берём размером файла, а не log_fh.tell(): у файла,
        # открытого в "ab", позиция до первой записи платформозависима.
        try:
            log_offset = log_path.stat().st_size if log_path.exists() else 0
        except OSError:
            log_offset = 0
        log_fh = log_path.open("ab")

    try:
        r = _run_child(
            lock_file=lock_file, reaps_path=reaps_path, escalations_path=escalations_path,
            sla_path=sla_path, fastdeath_path=fastdeath_path, claude_cmd=claude_cmd,
            child_args=args, now=now, kill_wait_sec=kill_wait_sec,
            max_pass_sec=max_pass_sec, holder=holder, stdout_target=log_fh,
            pre_spawn=_pre_spawn, on_spawn_failed=_on_spawn_failed,
            on_pass_done=_on_pass_done, fastdeath_log_hint=artifact)
    finally:
        if log_fh is not None:
            log_fh.close()

    for line in r["acquire_lines"]:
        print(line)
    for line in r["print_lines"]:
        print(line)

    # --- v8: лимит подписки — ПЕРЕКЛАССИФИКАЦИЯ исхода до M4-строки -------
    # Смерть от лимита выглядит как fastdeath (rc!=0, секунды), но поломкой
    # НЕ является: серию поломок не копит, тревогу не поднимает, а несёт
    # ВРЕМЯ СБРОСА — единственный факт, по которому сторож знает, когда
    # снова есть смысл будить кого-либо.
    # Н-собрат (2026-08-19): хвост читается ОДИН раз здесь и кормит ОБА
    # распознавателя — лимит (специфичнее, несёт момент сброса) и, если
    # лимита нет, класс auth/network/unknown (см. classify_death_reason).
    usage_limit = None
    death_reason = None
    _tail_text = None
    if r["outcome"] == "spawned" and r["child_rc"] not in (0, None):
        _tail_text = _read_log_tail(log_path, log_offset, USAGE_LIMIT_TAIL_BYTES,
                                    USAGE_LIMIT_TAIL_LINES)
        usage_limit = parse_usage_limit(_tail_text, now) if _tail_text else None
        if usage_limit is not None:
            death_reason = DEATH_REASON_LIMIT

    # --- Б1 (критик-раунд Д1): M4-строка НА ВСЕХ исходах ------------------
    fast_death = r["fast_death"]
    if r["outcome"] == "busy":
        m4_outcome = "BUSY, резервный проход не запускался"

    elif r["outcome"] == "spawn_failed":
        # spawn-failed мгновенный по определению — считается серией (та же
        # трактовка, что run_pass: docstring модуля §M-A).
        _fastdeath_increment(fastdeath_path, escalations_path, now, None, None,
                             log_hint=artifact)
        fast_death = True
        m4_outcome = f"spawn-failed:{r['spawn_error']}"
        # _run_child НЕ релизит лок на этой ветке (ребёнок не запущен,
        # решение «как релизить» — за вызывающим, тот же приём, что у
        # run_pass/_release_and_finish) — релизим здесь явно, non-throwing.
        try:
            rcode, rlines = ll.release(lock_file=lock_file, holder=holder, reaps_path=reaps_path)
            for line in rlines:
                print(line)
            if rcode != 0:
                m4_outcome += " release=refused-expected"
                print(f"REFUSED (ожидаемо, fallback-сценарий): holder={holder} "
                      "не совпал — лок резерва не наш к моменту release")
        except Exception as e:
            m4_outcome += f" release=error:{e}"
            print(f"FALLBACK release=error:{e}")

    else:
        # spawned (нормальный/wait_exception) или timeout_kill — _run_child
        # уже попытался release (кроме timeout_kill+alive: release_rcode
        # остаётся None by construction, should_release=False).
        if r["outcome"] == "timeout_kill":
            m4_outcome = ("timeout-kill release=kill-failed" if r["kill_alive"]
                         else "timeout-kill release=ok")
        elif r["wait_exception"] is not None:
            m4_outcome = f"exit=error:{r['wait_exception']}"
        elif usage_limit is not None:
            reset_txt = (_fmt_ts_utc(usage_limit["reset_ts"]) if usage_limit["reset_ts"]
                        else f"неизвестно ({usage_limit['note']})")
            m4_outcome = (f"usage-limit ({usage_limit['span'] or 'подписка'}) "
                         f"reset={reset_txt}")
            if fast_death:
                m4_outcome += _fastdeath_revert_one(fastdeath_path, escalations_path, now)
                fast_death = False
        else:
            m4_outcome = f"exit={r['child_rc']}" + r["fastdeath_suffix"]
            # Д-2 (критик rework attempt 2, 2026-08-19): причина
            # классифицируется для ЛЮБОГО rc != 0, не только для
            # fastdeath-серии — slowdeath (домен factory_watchdog.py,
            # НЕ пишет heartbeat-fastdeath.json/эскалацию
            # HEARTBEAT-CHILD-DEATH — это другой регистр) тоже нуждается
            # в классе причины для своей ноты/тоста. Прежде классификация
            # жила ПОД `if fast_death:` — медленный отказ (rc!=0,
            # runtime>=FAST_DEATH_SEC) молча уходил в «unknown» на стороне
            # сторожа, хотя хвост лога уже был прочитан и мог назвать
            # auth/network честно.
            if r["child_rc"] not in (0, None):
                death_reason = classify_death_reason(_tail_text)
                m4_outcome += f" reason={death_reason}"
            if fast_death:
                # Н-собрат: та же жалоба «N быстрых смертей подряд» — если
                # тайл называет auth/network, реестр и эскалация дожны
                # назвать причину, не просто считать смерти (unknown —
                # честный фолбэк, не «поломка без причины»). Регистр
                # HEARTBEAT-CHILD-DEATH — ТОЛЬКО серия быстрых смертей;
                # slowdeath получает класс через возврат `death_reason`
                # ВЫШЕ (не пишет сюда).
                _fastdeath_annotate_reason(fastdeath_path, escalations_path,
                                           death_reason, now,
                                           runtime=r["runtime"], log_hint=artifact)

        for line in r["release_lines"]:
            print(line)
        if r["release_rcode"] not in (None, 0):
            m4_outcome += " release=refused-expected"
            print(f"REFUSED (ожидаемо, fallback-сценарий): holder={holder} "
                  "не совпал — лок резерва не наш к моменту release")
        elif r["release_error"] is not None:
            m4_outcome += f" release=error:{r['release_error']}"
            print(f"FALLBACK release=error:{r['release_error']}")

    _append_m4_safe([RULE, AGENT, artifact, m4_outcome])

    return {
        "outcome": r["outcome"],
        "child_rc": r["child_rc"],
        "fast_death": fast_death,
        "holder": holder,
        "mode_write": mode_write_box["value"],
        # v8: None (лимита нет) либо dict parse_usage_limit — сторож берёт
        # отсюда `reset_ts` и молчит до него.
        "usage_limit": usage_limit,
        # Н-собрат: "limit"/"auth"/"network"/"unknown"|None (None — рано
        # классифицировать: rc==0/busy/spawn_failed/timeout_kill/
        # wait_exception — не этот класс исхода вовсе).
        "death_reason": death_reason,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="heartbeat_wrap — честная обёртка вокруг heartbeat.cmd (M1+M4)")
    parser.add_argument("--lock-file", default=str(DEFAULT_LOCK_FILE))
    parser.add_argument("--reaps-file", default=str(DEFAULT_REAPS_PATH))
    parser.add_argument("--escalations-file", default=str(DEFAULT_ESCALATIONS_PATH))
    parser.add_argument("--sla-file", default=str(DEFAULT_SLA_PATH))
    parser.add_argument("--claude-cmd", default=CLAUDE_CMD,
                        help="ТОЛЬКО для тестов/смок-прогонов kill-дерева")
    args = parser.parse_args(argv)
    return run_pass(lock_file=Path(args.lock_file), reaps_path=Path(args.reaps_file),
                    escalations_path=Path(args.escalations_file), sla_path=Path(args.sla_file),
                    claude_cmd=args.claude_cmd)


if __name__ == "__main__":
    sys.exit(main())
