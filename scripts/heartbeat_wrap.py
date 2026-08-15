"""heartbeat_wrap — честная обёртка вокруг heartbeat.cmd (M1+M4, план
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
_read_budget/_write_budget/_schtasks_disable/_write_budget_escalation.
"""
from __future__ import annotations

import argparse
import datetime
import os
import re
import secrets
import subprocess
import sys
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
# Патч E (критик, rework attempt 2): ключ собран через re.escape(...), не
# продублирован литералом — единственный источник правды HEARTBEAT_BUDGET_KEY.
_BUDGET_LINE_RE = re.compile(
    r"(?m)^- \[(?P<ts>[^\]]+)\] \*\*" + re.escape(HEARTBEAT_BUDGET_KEY) +
    r"\*\* \[heartbeat:budget\] — [^\r\n]*")


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


def _write_budget_escalation(escalations_path: Path, message: str,
                             now: datetime.datetime) -> None:
    """Дописывает/обновляет ОДНУ открытую HEARTBEAT-BUDGET-эскалацию —
    тот же приём, что loop_lock._write_loop_escalation, но ключ
    ФИКСИРОВАН (не нумеруется LOOP-N): состояние singleton — второй
    одновременной причины исчерпания быть не может, дедуп по задаче.
    Тег `[heartbeat:budget]` (не `[sla:...]`) — sla_sweep.rewrite_registry
    трогает только свои [sla:*]-строки (см. докстринг sla_sweep.py);
    эскалация переживает его проходы, пока оператор не удалит строку
    сам (штатный способ закрыть — см. ll.ESCALATIONS_HEADER)."""
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    text = escalations_path.read_bytes().decode("utf-8") if escalations_path.exists() else ""
    eol = "\r\n" if "\r\n" in text else "\n"

    m = _BUDGET_LINE_RE.search(text)
    if m:
        new_line = f"- [{m.group('ts')}] **{HEARTBEAT_BUDGET_KEY}** [heartbeat:budget] — {message}"
        new_text = text[:m.start()] + new_line + text[m.end():]
    else:
        if not text:
            text = ll.ESCALATIONS_HEADER
        elif not text.endswith("\n"):
            text += eol
        new_text = (text +
                    f"- [{stamp}] **{HEARTBEAT_BUDGET_KEY}** [heartbeat:budget] — {message}{eol}")

    escalations_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = escalations_path.with_name(escalations_path.name + ".tmp")
    tmp.write_bytes(new_text.encode("utf-8"))
    os.replace(tmp, escalations_path)


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
    BUSY-ветки — там лок чужой)."""
    lock_file = Path(lock_file)
    reaps_path = Path(reaps_path)
    escalations_path = Path(escalations_path)
    sla_path = Path(sla_path)
    budget_path = Path(budget_path)

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
        _write_budget_escalation(escalations_path, _BUDGET_CORRUPT_MSG, now)
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
        _write_budget_escalation(escalations_path, _BUDGET_EXHAUSTED_MSG, now)
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
        # достигается на этой ветке.
        outcome = f"spawn-failed:{e}"
        print(outcome)
        _release_and_finish(outcome, lock_file=lock_file, holder=holder, reaps_path=reaps_path)
        return 0

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
        except OSError as e:
            print(f"BUDGET decrement failed (бюджет не сожжён): {e}")

    should_release = True
    outcome = "exit=unknown"
    try:
        try:
            rc = p.wait(timeout=max_pass_sec)
            outcome = f"exit={rc}"
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
