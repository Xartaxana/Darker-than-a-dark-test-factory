"""sla_sweep — pre_step шага 0: просрочки SLA → реестр эскалаций (docs/06 §4).

Сверяет возраст статусов артефактов (status_since, fallback updated) с порогами
state/sla.yaml и ведёт реестр state/escalations.md:

  - [<когда замечено>] **<KEY>** [sla:<правило>] — <причина> | нужно: <действие>

Правила v1:
  bug_open_<severity>   — Open/Reopened баг висит дольше порога своей severity;
                          blocker эскалируется НЕМЕДЛЕННО (sla.yaml: «алерт
                          немедленно при создании», immediate_alerts.new_blocker_bug)
  bug_fixed_waiting_build — Fixed, но сборки новее момента перевода так и нет
  blocked_any           — любой артефакт в Blocked ждёт человека дольше порога
  run_needs_triage      — прогон висит без триажа (конвейер, вероятно, встал)
  question_unanswered   — awaiting: dev без движения дольше порога
  pingpong              — reopen_count/dispute_count ≥ reopened_pingpong →
                          баг переводится в Blocked + эскалация (docs/06 D8)

Дедупликация: одна строка на (артефакт, правило); повторные проходы не плодят
дублей и сохраняют исходное время обнаружения. Строки [sla:*], чья причина
устранена, снимаются автоматически (реестр = АКТИВНЫЕ варнинги); строки без тега
[sla:] (например, конфликты board_inbound) не трогаем — их снимает человек.

Запуск: python scripts/sla_sweep.py [--dry-run] [--now <ISO>]
Код выхода: 0 — штатно, 1 — ошибка выполнения.
"""
from __future__ import annotations

import argparse
import datetime
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

import board_sync as bs      # обход артефактов/парсер frontmatter
import board_inbound as bi   # _rewrite_field/_set_field — правка frontmatter как в inbound

REPO = bs.REPO
SLA_PATH = REPO / "state" / "sla.yaml"
ESCALATIONS_PATH = REPO / "state" / "escalations.md"
ORCH_LOG = REPO / "state" / "orchestrator-log.md"
AUT_PATH = REPO / "state" / "app-under-test.yaml"

ESCALATIONS_HEADER = (
    "# Эскалации фабрики\n\nАктивные варнинги, требующие человека "
    "(docs/06 §4). Строку удаляет человек по разрешении.\n\n"
)

# - [ts] **KEY** [sla:rule] — текст
TAGGED_LINE_RE = re.compile(
    r"^- \[(?P<ts>[^\]]+)\] \*\*(?P<key>[^*]+)\*\* \[sla:(?P<rule>[a-z_]+)\] — ")

DEFAULTS = {
    "bug_open_blocker": 24, "bug_open_critical": 72, "bug_open_major": 168,
    "bug_open_minor": 720, "bug_fixed_waiting_build": 72, "blocked_any": 24,
    "run_needs_triage": 12, "question_unanswered": 48, "reopened_pingpong": 2,
}


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _parse_ts(value) -> datetime.datetime | None:
    """ISO-строка или datetime (PyYAML коэрсит незакавыченные) → aware datetime."""
    if isinstance(value, datetime.datetime):
        return value if value.tzinfo else value.replace(tzinfo=datetime.timezone.utc)
    if not value:
        return None
    try:
        dt = datetime.datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=datetime.timezone.utc)
    except ValueError:
        return None


def load_thresholds() -> dict:
    out = dict(DEFAULTS)
    if not SLA_PATH.exists():
        return out
    text = SLA_PATH.read_text(encoding="utf-8", errors="replace")
    try:
        import yaml
        data = yaml.safe_load(text) or {}
        found = data.get("thresholds") or {}
    except Exception:
        found = {m.group(1): m.group(2)
                 for m in re.finditer(r"(?m)^\s{2}([a-z_]+):\s*([\d.]+)", text)}
    for k, v in found.items():
        try:
            out[k] = float(v)
        except (TypeError, ValueError):
            pass
    return out


def _built_at() -> datetime.datetime | None:
    if not AUT_PATH.exists():
        return None
    m = re.search(r'(?m)^built_at:\s*"?([^"\n]+)"?', AUT_PATH.read_text(encoding="utf-8"))
    return _parse_ts(m.group(1)) if m else None


def _since(meta: dict) -> datetime.datetime | None:
    """Время текущего статуса: status_since, иначе updated (легаси-артефакты)."""
    return _parse_ts(meta.get("status_since")) or _parse_ts(meta.get("updated"))


def _age_h(meta: dict, now: datetime.datetime) -> float | None:
    since = _since(meta)
    return (now - since).total_seconds() / 3600.0 if since else None


def _s_bool(value) -> bool:
    """`known_issue` во frontmatter: bool (PyYAML) или строка 'true'/'false'."""
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() == "true"


def _severity_rule(meta: dict) -> str:
    sev = str(meta.get("severity", "major")).lower()
    return f"bug_open_{sev}" if f"bug_open_{sev}" in DEFAULTS else "bug_open_major"


def collect_wanted(now: datetime.datetime, thr: dict) -> tuple[dict, list]:
    """(key, rule) -> message; плюс список мутаций pingpong→Blocked."""
    wanted: dict[tuple[str, str], str] = {}
    mutations: list[tuple[Path, str]] = []  # (src, key) для перевода в Blocked
    built = _built_at()

    for itype, meta, _body, src in bs._iter_artifacts():
        key = str(meta.get("id"))
        status = str(meta.get("status", ""))
        age = _age_h(meta, now)
        since = _since(meta)
        since_s = since.strftime("%Y-%m-%dT%H:%M:%SZ") if since else "?"

        # blocked_any — любой тип артефакта
        if status == "Blocked" and age is not None and age > thr["blocked_any"]:
            reason = str(meta.get("blocked_reason") or "").strip()
            reason_s = f" (причина: {reason})" if reason else ""
            wanted[(key, "blocked_any")] = (
                f"в Blocked с {since_s}{reason_s} | нужно: разобрать причину и вывести из Blocked")

        if itype == "run" and status == "NeedsTriage" and age is not None \
                and age > thr["run_needs_triage"]:
            wanted[(key, "run_needs_triage")] = (
                f"прогон без триажа с {since_s} — конвейер, вероятно, встал "
                f"| нужно: запустить /qa-loop или разобрать вручную")

        if itype != "bug":
            continue

        # B1/B2: resolution (accepted_risk/wontfix) и known_issue — сознательное
        # решение владельца оставить баг открытым; периодическая SLA-нагрузка по
        # severity здесь — шум, не сигнал (docs/06 D13/D14).
        deliberately_open = bool(str(meta.get("resolution") or "").strip()) \
            or _s_bool(meta.get("known_issue"))
        sev_rule = _severity_rule(meta)
        if status in ("Open", "Reopened") and age is not None and not deliberately_open:
            immediate_blocker = sev_rule == "bug_open_blocker"
            if immediate_blocker or age > thr[sev_rule]:
                sev = str(meta.get("severity", "major")).lower()
                wanted[(key, sev_rule)] = (
                    f"{sev}-баг {status.lower()} с {since_s} без движения "
                    f"| нужно: Fixed/Rejected/Intended или комментарий с планом")

        if status == "Fixed" and age is not None and age > thr["bug_fixed_waiting_build"]:
            if built is None or (since is not None and built <= since):
                wanted[(key, "bug_fixed_waiting_build")] = (
                    f"Fixed с {since_s}, но новой сборки нет "
                    f"| нужно: запушить/собрать сборку с фиксом")

        if str(meta.get("awaiting", "")).lower() == "dev" and age is not None \
                and age > thr["question_unanswered"]:
            wanted[(key, "question_unanswered")] = (
                f"ждёт ответа разработчика (awaiting: dev) с {since_s} "
                f"| нужно: ответить в ## Обсуждение")

        # pingpong (D8/D4): фикс/спор не сходится → Blocked + эскалация.
        # Легальные источники — по матрице (schemas/transitions.yaml): Open, Reopened
        # (D8, reopen_count) и Rejected (D4, dispute_count). Из Fixed НЕ блокируем —
        # у fix-verifier должен остаться шанс верифицировать свежий фикс.
        counts = [int(meta.get("reopen_count") or 0), int(meta.get("dispute_count") or 0)]
        if max(counts) >= thr["reopened_pingpong"] and status in ("Open", "Reopened", "Rejected"):
            wanted[(key, "pingpong")] = (
                f"пинг-понг: reopen/dispute достиг {max(counts)} "
                f"| нужно: живое обсуждение с разработчиком; баг переведён в Blocked")
            mutations.append((src, key))

    return wanted, mutations


def apply_pingpong_block(src: Path, now: datetime.datetime, *, dry: bool) -> str:
    text = src.read_text(encoding="utf-8")
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    new, changed = bi._rewrite_field(text, "status", "Blocked")
    if not changed:
        return f"  [WARN] {src.name}: нет строки status: — pingpong-блок не применён"
    new = bi._set_field(new, "status_since", f'"{stamp}"')
    new, _ = bi._rewrite_field(new, "updated", f'"{stamp}"')
    # B5: причина известна детерминированно — фикс/спор не сходится, нужно живое
    # обсуждение с разработчиком (D8/D4), это и есть product_decision.
    new = bi._set_field(new, "blocked_reason", "product_decision")
    if not dry:
        src.write_text(new, encoding="utf-8")
    return f"  [BLOCK] {src.name}: pingpong → Blocked{' (dry-run)' if dry else ''}"


def rewrite_registry(wanted: dict, now: datetime.datetime, *, dry: bool) -> tuple[list[str], list[str]]:
    """Обновляет escalations.md. Возвращает (added, removed) как 'KEY(rule)'."""
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    old_lines = (ESCALATIONS_PATH.read_text(encoding="utf-8").splitlines(keepends=True)
                 if ESCALATIONS_PATH.exists() else [])

    kept: list[str] = []
    satisfied: set[tuple[str, str]] = set()
    removed: list[str] = []
    for line in old_lines:
        m = TAGGED_LINE_RE.match(line)
        if not m:
            kept.append(line)          # заголовок, пустые, строки без тега — не трогаем
            continue
        pair = (m.group("key"), m.group("rule"))
        if pair in wanted:
            kept.append(line)          # активен — сохраняем с исходным временем
            satisfied.add(pair)
        else:
            removed.append(f"{pair[0]}({pair[1]})")   # причина устранена — снимаем

    added: list[str] = []
    new_lines: list[str] = []
    for (key, rule), msg in sorted(wanted.items()):
        if (key, rule) in satisfied:
            continue
        new_lines.append(f"- [{stamp}] **{key}** [sla:{rule}] — {msg}\n")
        added.append(f"{key}({rule})")

    if not added and not removed:
        return [], []
    content = "".join(kept) if kept else ESCALATIONS_HEADER
    if kept and not any(l.startswith("#") for l in kept):
        content = ESCALATIONS_HEADER + content
    content += "".join(new_lines)
    if not dry:
        ESCALATIONS_PATH.write_text(content, encoding="utf-8")
    return added, removed


def _append_orch_log(outcome: str, now: datetime.datetime, *, dry: bool) -> None:
    if dry:
        return
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"| {stamp} | pre_step sla_sweep | sla_sweep.py | state/escalations.md | {outcome} |\n"
    header = "" if ORCH_LOG.exists() else (
        "# Журнал оркестратора\n\n| Время | Правило | Агент | Артефакт | Исход |\n|---|---|---|---|---|\n")
    with ORCH_LOG.open("a", encoding="utf-8") as f:
        if header:
            f.write(header)
        f.write(line)


def sweep(*, now: datetime.datetime | None = None, dry: bool = False) -> list[str]:
    now = now or _utcnow()
    thr = load_thresholds()
    wanted, mutations = collect_wanted(now, thr)

    report: list[str] = []
    for src, _key in mutations:
        report.append(apply_pingpong_block(src, now, dry=dry))
    added, removed = rewrite_registry(wanted, now, dry=dry)
    for item in added:
        report.append(f"  [ESC+] {item}")
    for item in removed:
        report.append(f"  [ESC-] {item} — причина устранена, снято")
    if added or removed:
        _append_orch_log(
            f"эскалации: +{len(added)} ({', '.join(added) or '—'}), "
            f"-{len(removed)} ({', '.join(removed) or '—'})", now, dry=dry)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SLA-sweep: просрочки → state/escalations.md")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--now", help="переопределить текущее время (ISO, для тестов)")
    args = parser.parse_args(argv)

    now = _parse_ts(args.now) if args.now else None
    if args.now and now is None:
        print(f"[ERROR] --now не разобран: {args.now}")
        return 1

    report = sweep(now=now, dry=args.dry_run)
    print(f"sla_sweep: действий: {len(report)}{' (dry-run)' if args.dry_run else ''}")
    for line in report:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
