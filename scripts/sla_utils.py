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
"""
from __future__ import annotations

import re
from pathlib import Path

DEFAULT_LOCK_STALE_H = 2.0


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
