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

Помимо test-cases/bugs/runs (bs._iter_artifacts), обходит exploratory-charters/
верхнего уровня (CH-*.md, см. _iter_charter_locks) — задача e4-charter-lock-reaper.
ВАЖНО: схема charter.schema.yaml допускает легаси-формат лока `agent@YYYY-MM-DD`
(CH-001, заведён до канонического `agent:ISO`) — LOCK_RE его не матчит, поэтому
такой лок трактуется как «нечитаемый» и снимается с [WARN] СРАЗУ, безотносительно
возраста (тот же путь, что и «какая-то ерунда» у test-case/bug/run). Отчёт
builder'а флагует это координатору как расхождение, не тихо.

Запуск: python scripts/stale_locks.py [--dry-run] [--now <ISO>]
Идемпотентен: повторный запуск без новых протухших локов ничего не делает.
Код выхода: 0 — штатно (в т.ч. с действиями), 1 — ошибка выполнения.
"""
from __future__ import annotations

import argparse
import datetime
import itertools
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

import board_sync as bs  # парсер frontmatter/обход артефактов — единое место правды
import charter_utils     # обход exploratory-charters/ (дедуп D-0081, задача B)
import sla_utils

REPO = bs.REPO
SLA_PATH = REPO / "state" / "sla.yaml"
ORCH_LOG = REPO / "state" / "orchestrator-log.md"

DEFAULT_LOCK_STALE_H = sla_utils.DEFAULT_LOCK_STALE_H

LOCK_RE = re.compile(r"^(?P<agent>[A-Za-z0-9_-]+):(?P<ts>\d{4}-\d{2}-\d{2}T[0-9:.]+Z?)$")


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _parse_ts(value: str) -> datetime.datetime | None:
    try:
        return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _iter_charter_locks():
    """Charter'ы верхнего уровня exploratory-charters/ (*.md, НЕ attachments/),
    как (type, meta, body, path) — форма, совместимая с bs._iter_artifacts()
    для itertools.chain в sweep() ниже.

    Блокер critic-ревью механизма встройки charter'ов: exploratory-tester и
    диспатч кладут lock на charter, но bs._iter_artifacts() обходит только
    test-cases/bugs/runs (хардкод типов артефактов, board_sync.py:141) — лок
    charter'а протухал и не снимался никогда. Класс «список типов артефактов
    захардкожен в N местах»; единый источник правды по типам артефактов —
    отдельная задача очереди (расширение bs._iter_artifacts() трогает борду,
    вне owns этой задачи).

    Обход каталога — charter_utils._iter_charter_files (дедуп D-0081 задача B):
    та функция отдаёт (meta, body, path) без типа-метки "charter" — этот
    генератор добавляет её сверху, т.к. sweep() ниже нужен src (Path) для
    _clear_lock/rel, а не просто список meta, как у sla_sweep/queue_snapshot."""
    for meta, body, md in charter_utils._iter_charter_files(REPO):
        yield "charter", meta, body, md


def load_lock_stale_hours() -> float:
    """thresholds.lock_stale из state/sla.yaml; при любой проблеме — дефолт.

    Общий парсер — scripts/sla_utils.py (docs/09 «Мелкое хозяйство» п.5,
    2026-07-18): раньше был байт-идентичной копией того же кода в
    loop_lock.py. Обёртка сохранена (не голый импорт в вызывающем коде) —
    здесь own module-level SLA_PATH, сигнатура без аргумента, как раньше."""
    return sla_utils.load_lock_stale_hours(SLA_PATH, DEFAULT_LOCK_STALE_H)


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

    for _itype, meta, _body, src in itertools.chain(bs._iter_artifacts(), _iter_charter_locks()):
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
