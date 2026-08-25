"""sla_utils — общие парсеры SLA-обвязки: порог lock_stale из state/sla.yaml
и ISO-штамп артефакта (`parse_ts`, см. блок Б10 ниже — единый дом разбора
штампа для sla_sweep / validate_frontmatter / coverage_map).

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

import datetime
import re
from pathlib import Path

DEFAULT_LOCK_STALE_H = 2.0
DEFAULT_LOOP_LOCK_TTL_H = 4.0

# --- Б10 (критик-раунд 3, каденция compatibility 2026-08-25): ЕДИНАЯ форма
# разбора ISO-штампа frontmatter. Класс дефекта — «штампы сравниваются как
# СТРОКИ»: coverage_map.py сортировал прогоны по `str(updated)`, из-за чего
# любой нештатный штамп («FILL_ME» — плейсхолдер шаблона run-report,
# в ASCII 'F'(0x46) > '2'(0x32)) становился НОВЕЙШИМ, делался baseline'ом
# и ГЛУШИЛ детекторы дисциплины (`tc_results`, `recoveries`) для всего
# корпуса, а также назывался «последним зелёным прогоном». Плейсхолдер лишь
# предъявил хрупкость — корневая причина в строковом сравнении, поэтому
# правило вынесено сюда: разобранная дата или None, и НИКОГДА — «строка
# как ключ сортировки».
#
# Контракт: parse_ts(value) -> aware datetime (UTC для наивных) либо None.
# None = «штамп не разобран» — вызывающая сторона ОБЯЗАНА трактовать его как
# САМЫЙ СТАРЫЙ (см. coverage_map._ts_key), направление отказа безопасное:
# недоказанная свежесть != свежесть (F-30).
#
# Дом единый по репозиторию для трёх модулей, читающих возраст артефакта:
# sla_sweep._parse_ts, validate_frontmatter._parse_iso_dt и coverage_map
# вызывают ЭТУ функцию (их прежние тела были двумя независимыми копиями
# одной формы). ОСТАТОК КЛАССА (в очередь Lead, вне owns этой задачи —
# правило 9 «чини класс»): та же форма живёт ещё в 6 местах —
# scripts/queue_snapshot.py:56, scripts/doctor.py:165,
# scripts/factory_watchdog.py:185, scripts/loop_lock.py:122,
# scripts/stale_locks.py:70, scripts/scheduled_task_reader.py:85
# (+ scripts/permission_audit.py:156 — эпоха, не frontmatter).


def parse_ts(value) -> datetime.datetime | None:
    """ISO-штамп frontmatter → aware datetime (UTC), либо None если не разобран.

    Принимает то, что реально приходит из PyYAML: `datetime` (коэрция
    незакавыченного штампа), `date` (штамп без времени), строку (штатный
    случай — закавыченный ISO, в т.ч. с суффиксом `Z` и с пробелом вместо
    `T`), а также любой прочий скаляр — он приводится к строке (историческое
    поведение sla_sweep._parse_ts: `20260825` разбирается как basic-ISO дата
    средствами `fromisoformat` 3.11+). Пустое/ложное значение, отсутствие
    ключа и мусор («FILL_ME») → None."""
    if isinstance(value, datetime.datetime):
        return value if value.tzinfo else value.replace(tzinfo=datetime.timezone.utc)
    if isinstance(value, datetime.date):
        return datetime.datetime(value.year, value.month, value.day,
                                 tzinfo=datetime.timezone.utc)
    if not value:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=datetime.timezone.utc)


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
