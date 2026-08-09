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
"""
from __future__ import annotations

import argparse
import datetime
import os
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

# Тот же абсолютный путь, что был в прежнем heartbeat.cmd (npm global
# claude.cmd не гарантированно в PATH scheduled-контекста Task Scheduler).
CLAUDE_CMD = r"C:\Users\user\AppData\Roaming\npm\claude.cmd"
DEFAULT_CHILD_ARGS = ["-p", "/qa-loop 3", "--model", "sonnet"]

DEFAULT_MAX_PASS_MIN = 100.0
TIMEOUT_KILL_WAIT_S = 30

RULE = "heartbeat-обёртка"
AGENT = "heartbeat_wrap"
ARTIFACT = "logs/heartbeat.log"


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


def run_pass(*, lock_file: Path = DEFAULT_LOCK_FILE,
            reaps_path: Path = DEFAULT_REAPS_PATH,
            escalations_path: Path = DEFAULT_ESCALATIONS_PATH,
            sla_path: Path = DEFAULT_SLA_PATH,
            claude_cmd: str = CLAUDE_CMD,
            child_args: list[str] | None = None,
            now: datetime.datetime | None = None,
            kill_wait_sec: float = TIMEOUT_KILL_WAIT_S) -> int:
    """Один проход обёртки: acquire → (BUSY-выход | запуск claude → wait/
    kill → release) → журнальная строка. Возвращает 0 всегда (обёртка не
    должна ронять Task Scheduler ненулевым кодом ни на BUSY, ни на
    kill-failed — это видимые WARN-состояния, не крах вызова)."""
    lock_file = Path(lock_file)
    reaps_path = Path(reaps_path)
    escalations_path = Path(escalations_path)
    sla_path = Path(sla_path)

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

    max_pass_sec, clamped = compute_max_pass_sec(sla_path)
    if clamped:
        print(f"MAX_PASS ужат до {int(round(max_pass_sec / 60))} мин по sla lock_stale")

    child_env = dict(os.environ)
    child_env["AO3_LOOP_HOLDER"] = holder
    args = [claude_cmd, *(child_args if child_args is not None else DEFAULT_CHILD_ARGS)]
    p = _popen(args, env=child_env)

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
