"""sla_utils — общий парсер порога lock_stale из state/sla.yaml.

Раньше load_lock_stale_hours() существовал двумя байт-идентичными копиями
в scripts/stale_locks.py и scripts/loop_lock.py (класс «sla-threshold-parser»,
docs/09 «Мелкое хозяйство» п.5, 2026-07-18) — оба комментария честно
называли это независимой копией ради разных лок-файлов, но сам парсер
(yaml.safe_load -> thresholds.lock_stale -> regex-фолбэк -> дефолт) был
идентичен байт-в-байт. Единая точка правды здесь; обе точки вызывают её.

Публичный контракт: load_lock_stale_hours(sla_path) -> float. При любой
проблеме (файла нет, YAML не парсится, поля нет, значение не число) —
DEFAULT_LOCK_STALE_H (или явный override через параметр default).

load_loop_lock_ttl_hours(sla_path) -> float (spec-factory-window v6, К4,
2026-08-16): ОТДЕЛЬНЫЙ порог `thresholds.loop_lock_ttl_hours` (дефолт 4ч)
для того же файла — «возраст самого лока» в матрице сторожа
(scripts/factory_watchdog.py К3 п.2) и doctor-чек «живой loop.lock с
мёртвым pid» (loop_lock.py acquire/status тоже переходят на неё).
Ключа нет в файле, но файл существует и читается — ФОЛБЭК на
`load_lock_stale_hours(sla_path)` ЭТОГО ЖЕ файла (не на голый
DEFAULT_LOCK_STALE_H): старые фикстуры/деплои, знающие только
`lock_stale`, не должны молча получить другое число. Файла нет вовсе —
свой дефолт `default` (DEFAULT_LOOP_LOCK_TTL_H). stale_locks.py и
депрекируемый heartbeat_wrap.py (К5д) на эту функцию НЕ переходят —
остаются на load_lock_stale_hours (К4 спеки).
"""
from __future__ import annotations

import re
from pathlib import Path

DEFAULT_LOCK_STALE_H = 2.0
DEFAULT_LOOP_LOCK_TTL_H = 4.0


def load_lock_stale_hours(sla_path: Path, default: float = DEFAULT_LOCK_STALE_H) -> float:
    """thresholds.lock_stale из sla_path; при любой проблеме — default.

    Порядок: YAML-парсинг (yaml.safe_load, ключ thresholds.lock_stale) ->
    если модуль yaml недоступен/файл не парсится — regex-фолбэк по строке
    `lock_stale: <число>` -> если и это не нашлось — default. Тот же
    порядок, что был в обеих независимых копиях до объединения."""
    if not sla_path.exists():
        return default
    text = sla_path.read_text(encoding="utf-8", errors="replace")
    try:
        import yaml
        data = yaml.safe_load(text) or {}
        value = (data.get("thresholds") or {}).get("lock_stale")
        if value is not None:
            return float(value)
    except Exception:
        pass
    m = re.search(r"(?m)^\s*lock_stale:\s*([\d.]+)", text)
    return float(m.group(1)) if m else default


def load_loop_lock_ttl_hours(sla_path: Path, default: float = DEFAULT_LOOP_LOCK_TTL_H) -> float:
    """thresholds.loop_lock_ttl_hours из sla_path; ключа нет -> fallback на
    thresholds.lock_stale ТОГО ЖЕ файла (load_lock_stale_hours(sla_path,
    default=default)); файла нет вовсе -> default (см. докстринг модуля)."""
    if not sla_path.exists():
        return default
    text = sla_path.read_text(encoding="utf-8", errors="replace")
    try:
        import yaml
        data = yaml.safe_load(text) or {}
        value = (data.get("thresholds") or {}).get("loop_lock_ttl_hours")
        if value is not None:
            return float(value)
    except Exception:
        pass
    m = re.search(r"(?m)^\s*loop_lock_ttl_hours:\s*([\d.]+)", text)
    if m:
        return float(m.group(1))
    return load_lock_stale_hours(sla_path, default=default)
