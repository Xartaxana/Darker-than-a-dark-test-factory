"""stale_locks — pre_step шага 0: снятие протухших локов упавших агентов.

Лок в frontmatter артефакта: lock: "<agent>:<ISO-timestamp>" (ставит верхний
уровень /qa-loop перед диспатчем воркера, снимает по завершении). Если воркер
упал/оборвался, лок остаётся навсегда и артефакт выпадает из конвейера
(прецедент — TC-021, лок с 2026-07-02). Правило (docs/06 §5): лок старше
sla.thresholds.lock_stale часов => снять, залогировать в orchestrator-log.

Что НЕ трогаем:
- lock: "wip" — ручной лок человека (rules.skip_locks), снимает только человек;
- свежие локи (моложе порога) — агент, возможно, ещё работает;
- статус артефакта — постановка лока статус не меняет, восстанавливать нечего.

Нечитаемый лок (не "wip", но и не "<agent>:<ISO>") невозможно проверить на
свежесть — он снимается с [WARN]: вечный мусорный лок хуже, чем лишний проход
правила по артефакту.

Запуск: python scripts/stale_locks.py [--dry-run] [--now <ISO>]
Идемпотентен: повторный запуск без новых протухших локов ничего не делает.
Код выхода: 0 — штатно (в т.ч. с действиями), 1 — ошибка выполнения.
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

import board_sync as bs  # парсер frontmatter/обход артефактов — единое место правды

REPO = bs.REPO
SLA_PATH = REPO / "state" / "sla.yaml"
ORCH_LOG = REPO / "state" / "orchestrator-log.md"

DEFAULT_LOCK_STALE_H = 2.0

LOCK_RE = re.compile(r"^(?P<agent>[A-Za-z0-9_-]+):(?P<ts>\d{4}-\d{2}-\d{2}T[0-9:.]+Z?)$")


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _parse_ts(value: str) -> datetime.datetime | None:
    try:
        return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def load_lock_stale_hours() -> float:
    """thresholds.lock_stale из state/sla.yaml; при любой проблеме — дефолт."""
    if not SLA_PATH.exists():
        return DEFAULT_LOCK_STALE_H
    text = SLA_PATH.read_text(encoding="utf-8", errors="replace")
    try:
        import yaml
        data = yaml.safe_load(text) or {}
        value = (data.get("thresholds") or {}).get("lock_stale")
        if value is not None:
            return float(value)
    except Exception:
        pass
    m = re.search(r"(?m)^\s*lock_stale:\s*([\d.]+)", text)
    return float(m.group(1)) if m else DEFAULT_LOCK_STALE_H


def _completion_recorded(artifact_name: str, lock_value: str) -> bool:
    """Есть ли в orchestrator-log признак штатного завершения по артефакту.

    Различает формулировку («агент завершился, но забыл лок» vs «агент упал») —
    на решение снимать лок не влияет."""
    if not ORCH_LOG.exists():
        return False
    log = ORCH_LOG.read_text(encoding="utf-8", errors="replace").lower()
    name = artifact_name.lower()
    for line in log.splitlines():
        if name in line and ("лок снят" in line or "lock снят" in line):
            return True
    return False


def _clear_lock(src: Path, *, dry: bool) -> bool:
    text = src.read_text(encoding="utf-8")
    new, n = re.subn(r'(?m)^lock:\s*.*$', 'lock: ""', text, count=1)
    if n == 0:
        return False
    if not dry:
        src.write_text(new, encoding="utf-8")
    return True


def _append_orch_log(artifact_rel: str, outcome: str, *, dry: bool) -> None:
    if dry:
        return
    stamp = _utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"| {stamp} | pre_step stale_locks | stale_locks.py | {artifact_rel} | {outcome} |\n"
    header = "" if ORCH_LOG.exists() else (
        "# Журнал оркестратора\n\n| Время | Правило | Агент | Артефакт | Исход |\n|---|---|---|---|---|\n"
    )
    with ORCH_LOG.open("a", encoding="utf-8") as f:
        if header:
            f.write(header)
        f.write(line)


def sweep(*, now: datetime.datetime | None = None, dry: bool = False) -> list[str]:
    """Один идемпотентный проход. Возвращает строки-отчёты по каждому действию."""
    now = now or _utcnow()
    threshold_h = load_lock_stale_hours()
    report: list[str] = []

    for _itype, meta, _body, src in bs._iter_artifacts():
        lock = str(meta.get("lock") or "").strip()
        if not lock:
            continue
        rel = src.relative_to(REPO).as_posix() if src.is_relative_to(REPO) else src.name
        if lock == "wip":
            report.append(f"  [SKIP] {rel}: ручной лок wip — точка человека, не трогаем")
            continue

        m = LOCK_RE.match(lock)
        ts = _parse_ts(m.group("ts")) if m else None
        if ts is None:
            outcome = f"Снят нечитаемый лок {lock!r} (невозможно проверить свежесть)"
            if _clear_lock(src, dry=dry):
                _append_orch_log(rel, outcome, dry=dry)
                report.append(f"  [WARN] {rel}: {outcome}{' (dry-run)' if dry else ''}")
            continue

        age_h = (now - ts).total_seconds() / 3600.0
        if age_h <= threshold_h:
            report.append(f"  [OK] {rel}: лок {lock} свежий ({age_h:.1f}ч ≤ {threshold_h}ч)")
            continue

        finished = _completion_recorded(src.name, lock)
        why = ("завершение в логе есть — агент забыл снять лок"
               if finished else "завершения в логе нет — агент, вероятно, упал")
        outcome = f"Снят протухший лок {lock} (возраст {age_h:.1f}ч > {threshold_h}ч; {why})"
        if _clear_lock(src, dry=dry):
            _append_orch_log(rel, outcome, dry=dry)
            report.append(f"  [STALE] {rel}: {outcome}{' (dry-run)' if dry else ''}")
        else:
            report.append(f"  [WARN] {rel}: строка lock: не найдена при снятии — пропуск")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Снятие протухших локов (pre_step stale_locks)")
    parser.add_argument("--dry-run", action="store_true", help="показать действия, ничего не менять")
    parser.add_argument("--now", help="переопределить текущее время (ISO, для отладки/тестов)")
    args = parser.parse_args(argv)

    now = _parse_ts(args.now) if args.now else None
    if args.now and now is None:
        print(f"[ERROR] --now не разобран: {args.now}")
        return 1

    report = sweep(now=now, dry=args.dry_run)
    actions = [r for r in report if "[STALE]" in r or "[WARN]" in r]
    print(f"stale_locks: артефактов с локами: {len(report)}, действий: {len(actions)}"
          f"{' (dry-run)' if args.dry_run else ''}")
    for line in report:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
