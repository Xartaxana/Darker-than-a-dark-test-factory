"""permission_audit — восстановить, какие Bash/PowerShell-команды (включая субагентов)
вероятно требовали ручного подтверждения, и почему.

Прямого лога «показан permission-диалог» нет, поэтому аудит эвристический:
берём все tool_use из транскриптов текущего проекта, прогоняем через те же правила,
что и харнесс (allowlist settings.json/settings.local.json + известные auto-allow +
sandbox-эвристики «cannot be statically analyzed»), и печатаем те, что НЕ прошли бы
без вопроса — с категорией причины и предложением фикса.

Запуск:  python scripts/permission_audit.py [--minutes 120] [--all]
  --minutes N  смотреть только команды за последние N минут (default 180)
  --all        игнорировать фильтр времени
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROJECT_KEY = "D--AO3-tests"
CLAUDE_PROJECTS = Path(os.path.expanduser("~")) / ".claude" / "projects" / PROJECT_KEY

# --- команды, которые харнесс авто-разрешает без allowlist (усечённый практичный список) ---
AUTO_ALLOW_ANY_ARGS = {
    "cat", "head", "tail", "wc", "stat", "ls", "cd", "echo", "sleep", "which", "diff",
    "true", "false", "seq", "basename", "dirname", "realpath", "cut", "tr", "comm",
    "readlink", "expr", "type", "uname", "df", "du", "nl", "od", "id", "date",
}
AUTO_ALLOW_VALIDATED = {"grep", "rg", "find", "sort", "uniq", "jq", "sed", "ps", "xargs",
                        "file", "tree", "hostname", "pgrep", "lsof", "printf", "man"}
GIT_RO = {"status", "log", "diff", "show", "blame", "branch", "tag", "remote", "ls-files",
          "rev-parse", "describe", "reflog", "shortlog", "cat-file", "for-each-ref",
          "worktree", "stash"}

SANDBOX_HEURISTICS = [
    (re.compile(r'export\s+\w+="[^"]*\$\{?\w+'), "export VAR со ссылкой на другую переменную (array-subscript эвристика)"),
    (re.compile(r"\bnohup\b"), "nohup / ручной фон"),
    (re.compile(r"\$\("), "командная подстановка $(...)"),
    (re.compile(r"\bfor\s+\w+\s+in\b.*\bdo\b", re.S), "цикл for...do в shell"),
    (re.compile(r"\buntil\b|\bwhile\b.*\bdo\b", re.S), "цикл while/until"),
    (re.compile(r"&\s*$", re.M), "фоновый запуск через &"),
]


def load_allow_patterns() -> list[tuple[str, str]]:
    """[(tool, pattern), ...] из settings.json + settings.local.json."""
    out = []
    for name in ("settings.json", "settings.local.json"):
        p = REPO / ".claude" / name
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            print(f"[warn] не смог прочитать {name}: {e}", file=sys.stderr)
            continue
        for entry in data.get("permissions", {}).get("allow", []):
            m = re.match(r"^(\w+)\((.*)\)$", entry, re.S)
            if m:
                out.append((m.group(1), m.group(2)))
            else:
                out.append((entry, ""))  # голое имя тула, например WebSearch
    return out


def matches_allow(tool: str, cmd: str, patterns) -> bool:
    for ptool, pat in patterns:
        if ptool != tool:
            continue
        if not pat:
            return True
        if pat.endswith("*"):
            if cmd.startswith(pat[:-1]):
                return True
        elif " *" in pat:  # форма "foo *" — префикс до звёздочки
            if cmd.startswith(pat.split(" *")[0]):
                return True
        elif fnmatch.fnmatch(cmd, pat) or cmd == pat:
            return True
    return False


def is_auto_allowed(cmd: str) -> bool:
    """Грубая оценка встроенного auto-allow (только однострочные простые команды)."""
    if "\n" in cmd.strip():
        return False
    # цепочки — каждая часть должна быть auto-allowed
    parts = re.split(r"\s*(?:&&|\|\||;|\|)\s*", cmd.strip())
    for part in parts:
        if not part:
            continue
        tokens = part.strip().split()
        if not tokens:
            continue
        head = tokens[0].strip('"')
        base = os.path.basename(head).lower().removesuffix(".exe")
        if base == "git" and len(tokens) > 1 and tokens[1] in GIT_RO:
            continue
        if base in AUTO_ALLOW_ANY_ARGS or base in AUTO_ALLOW_VALIDATED:
            continue
        return False
    return True


def sandbox_flags(cmd: str) -> list[str]:
    flags = [reason for rx, reason in SANDBOX_HEURISTICS if rx.search(cmd)]
    if "\n" in cmd.strip():
        flags.append("многострочная команда (несколько statement'ов в одном вызове)")
    return flags


def iter_tool_calls(minutes: float | None, session: str | None = None):
    """(when, source, agent_type, tool, command) по всем транскриптам проекта."""
    cutoff = None if minutes is None else time.time() - minutes * 60
    files: list[tuple[Path, str]] = []
    for jl in CLAUDE_PROJECTS.glob("*.jsonl"):
        files.append((jl, "main"))
    for sub in CLAUDE_PROJECTS.glob("*/subagents/agent-*.jsonl"):
        if session and session not in str(sub):
            continue
        agent_type = "subagent"
        meta = sub.with_name(sub.name.replace(".jsonl", ".meta.json"))
        if meta.exists():
            try:
                agent_type = json.loads(meta.read_text(encoding="utf-8")).get("agentType", "subagent")
            except Exception:  # noqa: BLE001
                pass
        files.append((sub, agent_type))

    for path, source in files:
        if session and source == "main" and session not in path.name:
            continue
        if cutoff and path.stat().st_mtime < cutoff:
            continue  # файл не менялся в окне — пропускаем целиком
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line or '"tool_use"' not in line:
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:  # noqa: BLE001
                        continue
                    ts = obj.get("timestamp")
                    when = None
                    if ts:
                        try:
                            when = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
                        except Exception:  # noqa: BLE001
                            pass
                    if cutoff and when and when < cutoff:
                        continue
                    for item in obj.get("message", {}).get("content", []) or []:
                        if isinstance(item, dict) and item.get("type") == "tool_use" \
                                and item.get("name") in ("Bash", "PowerShell"):
                            cmd = (item.get("input") or {}).get("command", "")
                            yield when, path.name, source, item["name"], cmd
        except OSError:
            continue


def collect_suspects(minutes: float | None, session: str | None = None):
    """Прогнать все tool_use через allowlist + sandbox-эвристики.

    Возвращает (suspects, total), где suspects — список
    (when, agent, tool, cmd, reason) для команд, которые ВЕРОЯТНО требовали
    ручного подтверждения. Вынесено из main() отдельной чистой функцией,
    чтобы юнит-тесты могли проверять фильтрацию без парсинга stdout.
    """
    patterns = load_allow_patterns()
    suspects = []
    total = 0
    for when, fname, agent, tool, cmd in iter_tool_calls(minutes, session):
        total += 1
        allowed = matches_allow(tool, cmd, patterns)
        flags = sandbox_flags(cmd)
        if (allowed and not flags) or is_auto_allowed(cmd):
            continue
        reason = []
        if not allowed:
            reason.append("нет совпадения с allowlist")
        reason += flags
        suspects.append((when, agent, tool, cmd, reason))
    return suspects, total


def main(argv=None):
    if os.name == "nt":  # консоль Windows в cp866 душит кириллицу — форсим utf-8
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=180)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--session", help="фильтр: только транскрипты, чьи пути содержат эту подстроку (id сессии)")
    ap.add_argument("--summary", action="store_true", help="сводка по группам вместо полного списка")
    args = ap.parse_args(argv)
    minutes = None if getattr(args, "all") else args.minutes

    suspects, total = collect_suspects(minutes, args.session)

    print(f"Просканировано вызовов Bash/PowerShell: {total}"
          + ("" if minutes is None else f" (за последние {minutes:g} мин)")
          + (f" · сессия *{args.session[:8]}*" if args.session else ""))
    print(f"Вероятно требовали подтверждения: {len(suspects)}\n")

    if args.summary:
        from collections import Counter, defaultdict
        by_agent = Counter(a for _, a, *_ in suspects)
        by_reason = Counter(r for *_, reasons in suspects for r in reasons)
        examples: dict[str, str] = {}
        for _, agent, _tool, cmd, reasons in suspects:
            for r in reasons:
                examples.setdefault(r, " ".join(cmd.split())[:110])
        print("По агентам:")
        for a, n in by_agent.most_common():
            print(f"  {n:4d}  {a}")
        print("\nПо причинам:")
        for r, n in by_reason.most_common():
            print(f"  {n:4d}  {r}")
            print(f"        пример: {examples[r]}")
    else:
        for when, agent, tool, cmd, reason in suspects:
            t = datetime.fromtimestamp(when, tz=timezone.utc).strftime("%H:%M:%S") if when else "--:--:--"
            one_line = " ".join(cmd.split())[:150]
            print(f"[{t}] {agent} / {tool}")
            print(f"  cmd: {one_line}")
            print(f"  причина: {'; '.join(reason)}")
            print()
    if suspects:
        print("Рекомендации по категориям:")
        print(" - «нет совпадения с allowlist» → добавить wildcard-паттерн в .claude/settings.json")
        print(" - «многострочная/цикл/nohup/подстановка» → allowlist НЕ поможет; перенести логику")
        print("   в именованную функцию scripts/tasks.ps1 и запретить паттерн в .claude/agents/*.md")
        print(" - помнить: settings.json перечитывается только новыми (суб)агентами, не на лету")


if __name__ == "__main__":
    main()
