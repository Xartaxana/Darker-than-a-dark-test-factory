"""ДЕПРЕКИРОВАНО (spec-factory-window v6, К5д, 2026-08-16, слово оператора
2026-08-16 «в идеале heartbeat просто подталкивает фабрику в открытом
окне»): `scripts/heartbeat.cmd` БОЛЬШЕ НЕ ВЫЗЫВАЕТ этот модуль — вызывает
`scripts/factory_watchdog.py` (сторож окна, не запускатель headless-
прохода). Архитектура «невидимая фабрика в фоне» заменена на «окно-
фабрика + сторож»: `/qa-loop` теперь ведёт скилл `.claude/skills/
factory/SKILL.md` из ОТКРЫТОГО окна Claude Code, не эта обёртка из
Task Scheduler.

Обе ветки этого модуля мертвы в production, но КОД И ТЕСТЫ ОСТАЮТСЯ
(страховка отката — `python -m pytest scripts/tests -q` держит
`test_heartbeat_wrap*.py` зелёными; см. CLAUDE.md «Чини класс, а не
экземпляр» — если откат понадобится, обёртка снова рабочая, не
переписывается заново):
  1. **child-spawn-ветка** (acquire/BUSY/Popen/kill-tree/release/M4-строка,
     основное тело докстринга ниже) — код МЁРТВ, никто не вызывает
     `run_pass`/`main` этого модуля из production-пути.
  2. **бюджет+fastdeath-ветка** (`state/heartbeat-budget.txt`,
     `state/heartbeat-fastdeath.json`, `HEARTBEAT-BUDGET`/
     `HEARTBEAT-CHILD-DEATH`-эскалации) — тоже МЕРТВА: бюджет прогонов
     ПЕРЕЕЗЖАЕТ в аргумент `/factory N` (лимит срабатываний одного
     прохода окна = 5, слово оператора 2026-08-16 — см. К1 п.3 спеки),
     `state/heartbeat-fastdeath.json` — мёртвый runtime-файл (не пишется,
     не читается никаким живым путём); эскалация `HEARTBEAT-BUDGET`
     БОЛЬШЕ НЕ РОЖДАЕТСЯ (некому — `_write_budget`/`_schtasks_disable` не
     вызываются из production).

TTL-источник (К4 спеки): эта ветка ОСТАЁТСЯ на `sla_utils.
load_lock_stale_hours` (см. `compute_max_pass_sec` ниже) — НЕ переходит
на новую `load_loop_lock_ttl_hours` (та — для loop_lock.py/doctor.py/
сторожа, живых читателей).

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
обобщено в `_write_singleton_escalation`); здоровый проход (rc=0) или
медленная смерть (runtime >= FAST_DEATH_SEC) сбрасывает счётчик в 0.
Задача планировщика НЕ отключается (смерть-серия самоизлечивается,
когда причину чинит оператор). Если бюджет прогонов был сожжён в ЭТОМ
проходе (декремент прошёл без OSError) и смерть быстрая — бюджет
возвращается перечиткой+инкрементом (не восстановлением старого
значения — конкурентная правка оператора не должна быть затёрта). Обе
записи (счётчик, эскалация) никогда не бросают исключение наружу
run_pass (класс BL-4 — писатель эскалаций на занятом escalations.md
раньше сиротил лок; починено для ВСЕХ трёх площадок singleton-эскалаций
через общий catch внутри `_write_singleton_escalation`). См.
_read_fastdeath/_write_fastdeath/_fastdeath_increment/_fastdeath_reset/
_refund_budget.
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
FAST_DEATH_SEC = 120.0
FAST_DEATH_ESCALATE_AT = 3
HEARTBEAT_CHILD_DEATH_KEY = "HEARTBEAT-CHILD-DEATH"
HEARTBEAT_CHILD_DEATH_TAG = "heartbeat:child-death"


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


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


def _popen(args: list[str], *, env: dict) -> subprocess.Popen:
    """Обёртка вокруг Popen; подменяется в тестах. БЕЗ PIPE (B4): внуки
    процесса (appium/adb/gradle деревья, что claude.cmd порождает внутри
    /qa-loop) держали бы хэндлы stdout/stderr и `wait()` после `taskkill`
    висел бы мимо таймаута."""
    return subprocess.Popen(args, env=env)


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
    default = {"count": 0, "first_ts": None, "last_ts": None, "last_rc": None}
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
                         runtime: float | None) -> str:
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
    момент записи строки, не момент события)."""
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
            "logs/heartbeat.log; причину чинит оператор/Lead, счётчик сбросится "
            "сам первым здоровым проходом")
        _write_singleton_escalation(escalations_path, HEARTBEAT_CHILD_DEATH_KEY,
                                    HEARTBEAT_CHILD_DEATH_TAG, message, now)
        suffix += " escalated"
    return suffix


def _fastdeath_reset(fastdeath_path: Path) -> str:
    """Сбрасывает счётчик серии в 0 (rc==0 либо медленная смерть, спека
    п.3). Здоровый проход при УЖЕ нулевом/отсутствующем счётчике файл НЕ
    переписывает и НЕ создаёт — запись только при сбросе с ненулевого
    значения. Возвращает суффикс `` или ` fastdeath-reset`."""
    data = _read_fastdeath(fastdeath_path)
    if data["count"] == 0:                            # уже int (B2: приведено в _read_fastdeath)
        return ""
    _write_fastdeath(fastdeath_path, {"count": 0, "first_ts": None,
                                      "last_ts": None, "last_rc": None})
    return " fastdeath-reset"


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
    la.append_orchestrator([RULE, AGENT, ARTIFACT, outcome])


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
    WARN-состояния, не крах вызова).

    Бюджет (spec-heartbeat-budget.md v1) проверяется СТРОГО ПОСЛЕ
    BUSY-шортката (BUSY не жжёт бюджет) и СТРОГО ДО запуска ребёнка:
    N<=0 — самоотключение задачи + эскалация; файл есть, но не
    парсится — та же эскалация, задачу НЕ отключаем (оператор чинит
    файл). Оба ранних выхода обязаны освободить лок сами (в отличие от
    BUSY-ветки — там лок чужой).

    Детектор серийной быстрой смерти + возврат бюджета
    (spec-heartbeat-fastdeath.md v2) — таблица исходов ЕДИНСТВЕННЫЙ
    источник правды (спека §«M-A» п.3): BUSY и ранние budget-выходы
    fastdeath-счётчик НЕ трогают; spawn-failed и (rc!=0, runtime <
    FAST_DEATH_SEC) — инкремент (+ refund бюджета, если он был сожжён
    В ЭТОМ проходе); rc==0 или (rc!=0, runtime >= FAST_DEATH_SEC) —
    сброс в 0; exit=error/timeout-kill — no-op."""
    lock_file = Path(lock_file)
    reaps_path = Path(reaps_path)
    escalations_path = Path(escalations_path)
    sla_path = Path(sla_path)
    budget_path = Path(budget_path)
    fastdeath_path = Path(fastdeath_path)

    # Критик-фикс BL-4 (rework attempt 2, 2026-08-15): compute_max_pass_sec
    # вычислен ЗДЕСЬ — ДО acquire(), а не между acquire и внутренним
    # try/finally, как было. Класс: любое исключение в окне между взятием
    # лока и входом в try/finally НЕ снимает лок — сирота до TTL (тот же
    # класс, что необорачиваемый _write_budget ниже, BL-4). sla_utils.
    # load_lock_stale_hours сама не бросает (ловит всё внутри, докстринг
    # sla_utils.py), но зависимость от sla_path здесь никак не связана с
    # holder/acquire — меньшее вмешательство: подвинуть вызов раньше лока,
    # а не оборачивать его в try/except на месте.
    max_pass_sec, clamped = compute_max_pass_sec(sla_path)
    if clamped:
        print(f"MAX_PASS ужат до {int(round(max_pass_sec / 60))} мин по sla lock_stale")

    now = now or _utcnow()
    holder = _new_holder(now)
    code, lines = ll.acquire(lock_file=lock_file, holder=holder, reaps_path=reaps_path,
                             escalations_path=escalations_path, sla_path=sla_path, now=now)
    for line in lines:
        print(line)

    if code != 0:
        print(f"BUSY: holder={holder} — проход не запускался (claude не вызван)")
        la.append_orchestrator([RULE, AGENT, ARTIFACT, "BUSY, проход не запускался"])
        return 0

    # --- бюджет прогонов: строго после BUSY (BUSY не жжёт бюджет), строго
    # до запуска ребёнка. Лок к этой точке уже НАШ (acquire вернул
    # ACQUIRED) — оба ранних выхода освобождают его сами.
    budget = _read_budget(budget_path)
    if budget == _BUDGET_CORRUPT:
        print(f"BUDGET corrupt: {budget_path} не парсится в целое число — "
              "проход не запускался")
        _write_singleton_escalation(escalations_path, HEARTBEAT_BUDGET_KEY,
                                    HEARTBEAT_BUDGET_TAG, _BUDGET_CORRUPT_MSG, now)
        _release_and_finish("budget=corrupt, проход не запускался",
                            lock_file=lock_file, holder=holder, reaps_path=reaps_path)
        return 0
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
        return 0

    child_env = dict(os.environ)
    child_env["AO3_LOOP_HOLDER"] = holder
    args = [claude_cmd, *(child_args if child_args is not None else DEFAULT_CHILD_ARGS)]
    try:
        p = _popen(args, env=child_env)
    except Exception as e:
        # Неудачный spawn не жжёт бюджет: _write_budget ниже просто не
        # достигается на этой ветке. Таблица исходов M-A п.3: spawn-failed
        # — тот же операторский симптом класса, что серия быстрых смертей
        # («тика не было, фабрика молча стоит»), мгновенный по определению
        # — считается серией (инкремент fastdeath, refund не применим —
        # бюджет тут не жёгся).
        outcome = f"spawn-failed:{e}"
        outcome += _fastdeath_increment(fastdeath_path, escalations_path, now, None, None)
        print(outcome)
        _release_and_finish(outcome, lock_file=lock_file, holder=holder, reaps_path=reaps_path)
        return 0

    # t_spawn — сразу после успешного _popen (спека §«M-A» п.1): точка
    # отсчёта runtime для детектора быстрой смерти.
    t_spawn = time.monotonic()

    budget_burned = False
    if budget != _BUDGET_UNLIMITED:
        # декремент ПОСЛЕ успешного Popen (бюджет = фактически стартовавшие
        # проходы) — N>0 гарантирован веткой выше (<=0 уже вернула).
        # Критик-фикс BL-4 (rework attempt 2): исключение здесь — тот же
        # класс, что необёрнутый _popen раньше (окно между acquire и
        # try/finally) — ребёнок УЖЕ запущен (p существует), ронять проход
        # сейчас означало бы сирота-лок + брошенный живой child. Не роняем:
        # печатаем и идём дальше в штатный try/finally (wait/release).
        try:
            _write_budget(budget_path, budget - 1)
            budget_burned = True  # M-B: refund допустим ТОЛЬКО если декремент прошёл (спека)
        except OSError as e:
            print(f"BUDGET decrement failed (бюджет не сожжён): {e}")

    should_release = True
    outcome = "exit=unknown"
    try:
        try:
            rc = p.wait(timeout=max_pass_sec)
            outcome = f"exit={rc}"
            # Таблица исходов M-A п.3: rc!=0 и runtime < FAST_DEATH_SEC —
            # быстрая смерть (инкремент + refund, если бюджет был сожжён);
            # rc==0 ЛИБО (rc!=0 и runtime >= FAST_DEATH_SEC) — сброс.
            runtime = time.monotonic() - t_spawn
            if rc != 0 and runtime < FAST_DEATH_SEC:
                outcome += _fastdeath_increment(fastdeath_path, escalations_path, now, rc, runtime)
                if budget_burned:
                    outcome += _refund_budget(budget_path)
            else:
                outcome += _fastdeath_reset(fastdeath_path)
        except subprocess.TimeoutExpired:
            _taskkill_tree(p.pid)
            try:
                p.wait(kill_wait_sec)
            except subprocess.TimeoutExpired:
                pass  # пост-проверка ниже решает по факту, не по этому wait
            alive = _tasklist_alive(p.pid)
            if alive:
                should_release = False
                outcome = "timeout-kill release=kill-failed"
                print("kill-failed, лок оставлен")
            else:
                outcome = "timeout-kill release=ok"
        except Exception as e:                      # child умер/raise
            outcome = f"exit=error:{e}"
    finally:
        if should_release:
            try:
                rcode, rlines = ll.release(lock_file=lock_file, holder=holder,
                                           reaps_path=reaps_path)
                for line in rlines:
                    print(line)
                if rcode != 0:
                    # REFUSED: holder лока при finally уже не наш (fallback-
                    # сценарий M2 — SKILL сам держит свой qa-loop-holder,
                    # либо взял лок заново после того, как наш пропал) —
                    # ОЖИДАЕМЫЙ исход, не инцидент (см. докстринг модуля).
                    outcome += " release=refused-expected"
                    print(f"REFUSED (ожидаемо, fallback-сценарий): holder={holder} "
                          "не совпал — лок обёртки не наш к моменту release")
            except Exception as e:
                # [некритично п.5] Исключение release() НЕ должно съедать
                # M4-строку — finally всё равно обязан её дописать.
                outcome += f" release=error:{e}"
        la.append_orchestrator([RULE, AGENT, ARTIFACT, outcome])
    return 0


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
