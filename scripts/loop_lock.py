"""loop_lock — анти-наложение проходов /qa-loop + детектор «фабрика
систематически умирает» (docs/06 §5 «Расписание», гейт docs/11 §1).

До этого скрипта наложение проходов исключалось только тем, что их
запускал человек по одному (сверка 2026-07-17: ни qa-loop SKILL, ни
scripts/ лок не ставили — «обещанный механизм без кода»).

Лок — JSON-файл `{"holder": <строка>, "pid": <int>, "ts": "<ISO>"}`
(по умолчанию state/loop.lock). Свежесть меряется ОТДЕЛЬНЫМ порогом
`state/sla.yaml → thresholds.loop_lock_ttl_hours` (дефолт 4ч, fallback
на lock_stale того же файла — sla_utils.load_loop_lock_ttl_hours,
spec-factory-window v6 К4, 2026-08-16). ДО этой правки использовался
общий `thresholds.lock_stale` (та же величина, что и локи артефактов у
scripts/stale_locks.py) — пороги теперь РАЗВЕДЕНЫ: stale_locks.py и
депрекируемый heartbeat_wrap.py остаются на lock_stale; loop_lock.py
(этот модуль) и doctor-чек «живой loop.lock с мёртвым pid» — на новой
load_loop_lock_ttl_hours.

acquire:
  - лока нет ИЛИ он протух (возраст > lock_stale) => записать новый
    лок, ACQUIRED, exit 0. Протухший лок сначала REAPED (печатается
    прежний holder/ts) и инкрементирует счётчик подряд снятых
    (state/loop-lock-reaps.json). Нечитаемый/битый лок (JSON не
    парсится или ts не парсится) снимается тем же путём (REAPED,
    свежесть не проверить, значит небезопасно ждать вечно — тот же
    принцип, что «нечитаемый лок» у stale_locks.py), НО N2 (docs/09
    «Мелкое хозяйство» п.5, 2026-07-18): счётчик подряд снятых он НЕ
    инкрементирует — битый файл это мусор (никогда не был валидным
    локом живого прохода), а не свидетельство умершего прохода;
    death-streak считает только генуинно протухшие локи с известным
    возрастом.
  - лок живой => BUSY, exit 1.
release:
  - лока нет => RELEASED (noop), exit 0.
  - holder совпадает (или --force) => удалить лок, сбросить счётчик
    подряд снятых в 0 (успешный release = фабрика жива), exit 0.
  - иначе => REFUSED, exit 1.
status:
  - печатает состояние (NONE/LIVE/STALE/CORRUPT) + счётчик подряд
    снятых. Ничего не меняет. exit 0 всегда.

При count >= 2 подряд снятых acquire дополнительно дописывает/обновляет
строку-эскалацию в state/escalations.md с id вида LOOP-<N> и тегом
`[loop:reaped]` (НЕ `[sla:...]` — та форма зарезервирована за
sla_sweep.py: sla_sweep.rewrite_registry() на каждом проходе удаляет
[sla:*]-строки, которых нет в его собственном wanted-словаре, и снёс
бы наш маркер, если бы мы взяли тот же тег; строки без тега [sla:]
sla_sweep не трогает — см. докстринг sla_sweep.py). Дедупликация:
одна открытая LOOP-эскалация обновляется на месте (счётчик в тексте),
не дублируется; после того как человек удаляет строку (штатный способ
закрыть эскалацию — см. ESCALATIONS_HEADER), нумерация следующего
инцидента начинается заново с LOOP-1 — истории прошлых номеров нигде
не хранится, это сознательное упрощение (см. отчёт builder'а).

Запуск: python scripts/loop_lock.py acquire|release|status
  [--lock-file state/loop.lock] [--holder <строка>] [--force]
  [--now <ISO>] [--reaps-file ...] [--escalations-file ...] [--sla-file ...]
Код выхода: acquire — 0 ACQUIRED / 1 BUSY; release — 0 RELEASED / 1 REFUSED;
status — всегда 0.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

import sla_utils

REPO = Path(__file__).resolve().parent.parent
DEFAULT_LOCK_FILE = REPO / "state" / "loop.lock"
DEFAULT_REAPS_PATH = REPO / "state" / "loop-lock-reaps.json"
DEFAULT_ESCALATIONS_PATH = REPO / "state" / "escalations.md"
DEFAULT_SLA_PATH = REPO / "state" / "sla.yaml"

DEFAULT_LOCK_STALE_H = sla_utils.DEFAULT_LOCK_STALE_H
DEFAULT_LOOP_LOCK_TTL_H = sla_utils.DEFAULT_LOOP_LOCK_TTL_H
REAP_ESCALATION_THRESHOLD = 2

# AT-BUG-041: [^\r\n]* вместо .*$ — под '$' в (?m)-режиме '.' всё же матчит
# '\r' (не матчит только '\n'), так что жадный '.*$' на CRLF-файле поглощал
# бы завершающий '\r' строки в тело матча и терял его при замене (та же
# граница, что уже закрыта в board_sync.py/board_inbound.py/gitlab_sync.py/
# stale_locks.py после AT-BUG-038/040 — образец _LOCK_FIELD_RE).
LOOP_LINE_RE = re.compile(
    r"(?m)^- \[(?P<ts>[^\]]+)\] \*\*(?P<key>LOOP-\d+)\*\* \[loop:reaped\] — [^\r\n]*")
LOOP_KEY_RE = re.compile(r"LOOP-(\d+)")

ESCALATIONS_HEADER = (
    "# Эскалации фабрики\n\nАктивные варнинги, требующие человека "
    "(docs/06 §4). Строку удаляет человек по разрешении.\n\n"
)


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _parse_ts(value: str) -> datetime.datetime | None:
    """ISO ts -> aware datetime (UTC), либо None (не парсится).

    Критик-фикс (2026-08-09, heartbeat_wrap-диспатч, класс 2а): naive ISO
    (без 'Z'/offset — теоретически возможный, хоть и не наш собственный,
    формат payload.ts) давал aware-naive datetime, вычитание которого с
    aware `now` (_utcnow()) роняет TypeError и в acquire(), и в status() —
    падение на КАЖДОМ preflight'е (doctor — шаг 1 каждого прохода). Naive
    результат трактуется как UTC (та же семантика, что и весь модуль:
    все свои ts пишутся с суффиксом 'Z' — naive может появиться только у
    чужого/ручного лока)."""
    if not value:
        return None
    try:
        ts = datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=datetime.timezone.utc)
    return ts


def load_lock_stale_hours(sla_path: Path) -> float:
    """thresholds.lock_stale из sla.yaml.

    Общий парсер — scripts/sla_utils.py (docs/09 «Мелкое хозяйство» п.5,
    2026-07-18): раньше был байт-идентичной копией stale_locks.py (разный
    лок-файл, тот же источник порога и тот же fallback — сама логика
    парсинга не отличалась ни байтом). Обёртка сохранена (сигнатура с
    обязательным sla_path, как раньше) для обратной совместимости и для
    вызывающих, которым нужен ИМЕННО lock_stale (stale_locks.py) — сама
    staleness-проверка ЭТОГО модуля больше её не использует (см.
    load_loop_lock_ttl_hours ниже, spec-factory-window v6 К4)."""
    return sla_utils.load_lock_stale_hours(sla_path, DEFAULT_LOCK_STALE_H)


def load_loop_lock_ttl_hours(sla_path: Path) -> float:
    """thresholds.loop_lock_ttl_hours (fallback lock_stale ТОГО ЖЕ файла) —
    spec-factory-window v6 К4 (2026-08-16): TTL, которым acquire/status
    этого модуля меряют свежесть лока — ОТДЕЛЁН от lock_stale (тот
    остаётся источником для stale_locks.py/депрекируемого
    heartbeat_wrap.py, К5д). Обёртка над sla_utils.load_loop_lock_ttl_hours
    (единый источник правды, тот же приём, что load_lock_stale_hours
    выше)."""
    return sla_utils.load_loop_lock_ttl_hours(sla_path, DEFAULT_LOOP_LOCK_TTL_H)


def _atomic_write_text(path: Path, text: str) -> None:
    """Атомарная запись через tmp+rename.

    AT-BUG-041 (сиблинг AT-BUG-038/040, класс 1 — EOL-перегон): write_bytes
    вместо write_text. Text-режим (newline=None) транслирует '\\n' в
    os.linesep при КАЖДОЙ записи (на Windows — CRLF), включая партиальную
    правку существующего файла в _write_loop_escalation (та функция читает
    исходный контент байтово — см. её докстринг/тело — так что здесь '\\n'
    в тексте уже означает буквальный '\\n' исходного файла, а не место для
    ОС-специфичной трансляции); для freshly-сгенерированного JSON
    (lock/reaps) поведение то же — байт-в-байт, без сюрприза для platform-
    зависимого EOL."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(text.encode("utf-8"))
    os.replace(tmp, path)


def _read_lock_raw(lock_file: Path) -> dict | None:
    """None — лока нет. {} и более — распарсенный JSON (может не содержать
    holder/ts при битом файле — вызывающий код это отдельно обрабатывает)."""
    if not lock_file.exists():
        return None
    try:
        data = json.loads(lock_file.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return {}


def _load_reaps(reaps_path: Path) -> dict:
    default = {"count": 0, "last_ts": None, "holders": []}
    if not reaps_path.exists():
        return default
    try:
        data = json.loads(reaps_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default
    if not isinstance(data, dict):
        return default
    data.setdefault("count", 0)
    data.setdefault("last_ts", None)
    data.setdefault("holders", [])
    return data


def _save_reaps(reaps_path: Path, data: dict) -> None:
    _atomic_write_text(reaps_path, json.dumps(data, ensure_ascii=False, indent=2))


def _bump_reap_counter(reaps_path: Path, reaped_holder: str, now: datetime.datetime) -> dict:
    data = _load_reaps(reaps_path)
    data["count"] = int(data.get("count", 0)) + 1
    data["last_ts"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    holders = list(data.get("holders", []))
    holders.append(reaped_holder)
    data["holders"] = holders
    _save_reaps(reaps_path, data)
    return data


def _reset_reap_counter(reaps_path: Path) -> None:
    _save_reaps(reaps_path, {"count": 0, "last_ts": None, "holders": []})


def _write_loop_escalation(escalations_path: Path, count: int, now: datetime.datetime) -> str:
    """Дописывает/обновляет ОДНУ открытую LOOP-эскалацию. Возвращает её ключ.

    AT-BUG-041 (класс 1 — EOL-перегон): чтение read_bytes/decode вместо
    read_text — text-режим на чтении уже транслирует CRLF -> LF
    (universal newlines), что вместе с write_text на записи и давало
    полный перегон EOL реестра эскалаций при партиальной правке одной
    LOOP-строки.

    attempt 2 (критик-вход приёмки): НОВЫЙ контент (добавляемая строка при
    первом появлении LOOP-эскалации, добивка перевода строки перед ней)
    обязан брать EOL-стиль САМОГО файла по факту, не хардкод '\\n' — тот же
    образец и аргумент, что sla_sweep.rewrite_registry / board_inbound.
    _file_eol (AT-BUG-038); ветка «обновление УЖЕ существующей LOOP-N-строки
    на месте» (m matched) EOL не трогает вовсе — уже верно."""
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    text = escalations_path.read_bytes().decode("utf-8") if escalations_path.exists() else ""
    eol = "\r\n" if "\r\n" in text else "\n"
    msg = (f"{count} проходов подряд умерли с локом — фабрика систематически "
           f"падает, нужен разбор человеком")

    m = LOOP_LINE_RE.search(text)
    if m:
        new_line = f"- [{m.group('ts')}] **{m.group('key')}** [loop:reaped] — {msg}"
        new_text = text[:m.start()] + new_line + text[m.end():]
        key = m.group("key")
    else:
        nums = [int(x) for x in LOOP_KEY_RE.findall(text)]
        key = f"LOOP-{max(nums) + 1 if nums else 1}"
        if not text:
            text = ESCALATIONS_HEADER
        elif not text.endswith("\n"):
            text += eol
        new_text = text + f"- [{stamp}] **{key}** [loop:reaped] — {msg}{eol}"

    _atomic_write_text(escalations_path, new_text)
    return key


def acquire(*, lock_file: Path, holder: str, reaps_path: Path, escalations_path: Path,
            sla_path: Path, now: datetime.datetime | None = None) -> tuple[int, list[str]]:
    now = now or _utcnow()
    # К4 (spec-factory-window v6, 2026-08-16): свежесть лока меряется
    # loop_lock_ttl_hours (fallback lock_stale ЭТОГО ЖЕ файла), не голым
    # lock_stale — см. load_loop_lock_ttl_hours.
    threshold_h = load_loop_lock_ttl_hours(sla_path)
    existing = _read_lock_raw(lock_file)
    lines: list[str] = []
    reaped_prev_holder: str | None = None

    if existing is not None:
        prev_holder = existing.get("holder") or "<unknown>"
        prev_ts_raw = existing.get("ts") or "?"
        ts = _parse_ts(str(existing.get("ts", "")))
        age_h = (now - ts).total_seconds() / 3600.0 if ts is not None else None

        if age_h is not None and age_h <= threshold_h:
            lines.append(
                f"BUSY: holder={prev_holder} ts={prev_ts_raw} "
                f"возраст={age_h:.2f}ч <= порога {threshold_h}ч")
            return 1, lines

        # N2 (docs/09 «Мелкое хозяйство» п.5, 2026-07-18): битый/нечитаемый
        # лок (JSON не парсится или ts отсутствует/не парсится) — снимается
        # так же (REAPED), но НЕ считается в death-streak. Счётчик мерит
        # «фабрика систематически умирает» — генуинно протухшие локи с
        # известным возрастом; мусорный файл ничего не говорит о том, умер
        # ли предыдущий проход, инкремент по нему был ложным сигналом.
        if age_h is None:
            reason = "лок нечитаем/битый — свежесть не проверить"
            countable = False
        else:
            reason = f"возраст {age_h:.2f}ч > порога {threshold_h}ч"
            countable = True
        lines.append(f"REAPED: прежний holder={prev_holder} ts={prev_ts_raw} ({reason})")
        if countable:
            reaped_prev_holder = prev_holder

    payload = {"holder": holder, "pid": os.getpid(), "ts": now.strftime("%Y-%m-%dT%H:%M:%SZ")}
    _atomic_write_text(lock_file, json.dumps(payload, ensure_ascii=False, indent=2))
    lines.append(f"ACQUIRED: holder={holder} ts={payload['ts']}")

    if reaped_prev_holder is not None:
        reaps = _bump_reap_counter(reaps_path, reaped_prev_holder, now)
        lines.append(f"REAP-STREAK: подряд снятых={reaps['count']}")
        if reaps["count"] >= REAP_ESCALATION_THRESHOLD:
            key = _write_loop_escalation(escalations_path, reaps["count"], now)
            lines.append(f"ESCALATION: {key} — фабрика систематически умирает")

    return 0, lines


def release(*, lock_file: Path, holder: str, reaps_path: Path,
            force: bool = False) -> tuple[int, list[str]]:
    if not lock_file.exists():
        return 0, ["RELEASED: лока и так не было (noop)"]

    existing = _read_lock_raw(lock_file) or {}
    cur_holder = existing.get("holder") or "<unknown>"

    if not force and cur_holder != holder:
        return 1, [
            f"REFUSED: лок принадлежит holder={cur_holder!r}, "
            f"запрошен release от holder={holder!r} (нужен --force)"
        ]

    lock_file.unlink()
    _reset_reap_counter(reaps_path)
    tail = " (force, чужой holder)" if force and cur_holder != holder else ""
    return 0, [f"RELEASED: holder={cur_holder}{tail}"]


def status(*, lock_file: Path, reaps_path: Path, sla_path: Path,
           now: datetime.datetime | None = None) -> tuple[int, list[str]]:
    now = now or _utcnow()
    threshold_h = load_loop_lock_ttl_hours(sla_path)  # К4 — см. acquire()
    reaps = _load_reaps(reaps_path)
    lines: list[str] = []

    existing = _read_lock_raw(lock_file)
    if existing is None:
        lines.append("NONE: лока нет")
    else:
        holder = existing.get("holder") or "<unknown>"
        ts_raw = existing.get("ts") or "?"
        ts = _parse_ts(str(existing.get("ts", "")))
        if ts is None:
            lines.append(f"CORRUPT: лок нечитаем holder={holder} ts={ts_raw!r}")
        else:
            age_h = (now - ts).total_seconds() / 3600.0
            state = "LIVE" if age_h <= threshold_h else "STALE"
            lines.append(
                f"{state}: holder={holder} ts={ts_raw} "
                f"возраст={age_h:.2f}ч (порог {threshold_h}ч)")

    lines.append(f"REAP-STREAK: подряд снятых={reaps['count']} last_ts={reaps['last_ts']}")
    return 0, lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="loop_lock — анти-наложение проходов /qa-loop")
    parser.add_argument("action", choices=["acquire", "release", "status"])
    parser.add_argument("--lock-file", default=str(DEFAULT_LOCK_FILE))
    parser.add_argument("--holder", default=None, help='по умолчанию "qa-loop:<ISO now>"')
    parser.add_argument("--force", action="store_true",
                         help="release: снять лок независимо от holder")
    parser.add_argument("--now", help="переопределить текущее время (ISO, для отладки/тестов)")
    parser.add_argument("--reaps-file", default=str(DEFAULT_REAPS_PATH))
    parser.add_argument("--escalations-file", default=str(DEFAULT_ESCALATIONS_PATH))
    parser.add_argument("--sla-file", default=str(DEFAULT_SLA_PATH))
    args = parser.parse_args(argv)

    now = _parse_ts(args.now) if args.now else None
    if args.now and now is None:
        print(f"[ERROR] --now не разобран: {args.now}")
        return 1
    now = now or _utcnow()

    lock_file = Path(args.lock_file)
    reaps_path = Path(args.reaps_file)
    escalations_path = Path(args.escalations_file)
    sla_path = Path(args.sla_file)
    holder = args.holder or f"qa-loop:{now.strftime('%Y-%m-%dT%H:%M:%SZ')}"

    if args.action == "acquire":
        code, lines = acquire(lock_file=lock_file, holder=holder, reaps_path=reaps_path,
                               escalations_path=escalations_path, sla_path=sla_path, now=now)
    elif args.action == "release":
        code, lines = release(lock_file=lock_file, holder=holder, reaps_path=reaps_path,
                               force=args.force)
    else:
        code, lines = status(lock_file=lock_file, reaps_path=reaps_path, sla_path=sla_path,
                              now=now)

    for line in lines:
        print(line)
    return code


if __name__ == "__main__":
    sys.exit(main())
