"""Юнит-тесты scripts/sla_utils.py — общий парсер lock_stale (docs/09
«Мелкое хозяйство» п.5, 2026-07-18: раньше две байт-идентичные копии в
stale_locks.py и loop_lock.py)."""
from __future__ import annotations

import sla_utils as su


def test_missing_file_returns_default(tmp_path):
    assert su.load_lock_stale_hours(tmp_path / "no-such.yaml") == su.DEFAULT_LOCK_STALE_H


def test_explicit_default_override_on_missing_file(tmp_path):
    assert su.load_lock_stale_hours(tmp_path / "no-such.yaml", default=9.5) == 9.5


def test_reads_threshold_from_yaml(tmp_path):
    p = tmp_path / "sla.yaml"
    p.write_text("version: 1\nthresholds:\n  lock_stale: 4.5\n", encoding="utf-8")
    assert su.load_lock_stale_hours(p) == 4.5


def test_unparseable_yaml_falls_back_to_regex(tmp_path, monkeypatch):
    """yaml.safe_load недоступен/падает -> regex-фолбэк по строке lock_stale:."""
    p = tmp_path / "sla.yaml"
    p.write_text("thresholds:\n  lock_stale: 3\n  [broken", encoding="utf-8")
    assert su.load_lock_stale_hours(p) == 3.0


def test_no_lock_stale_field_returns_default(tmp_path):
    p = tmp_path / "sla.yaml"
    p.write_text("version: 1\nthresholds:\n  other_field: 7\n", encoding="utf-8")
    assert su.load_lock_stale_hours(p) == su.DEFAULT_LOCK_STALE_H


def test_used_identically_by_both_call_sites(tmp_path):
    """Регрессия дедупа: stale_locks.py и loop_lock.py обязаны отдавать то
    же значение, что и sla_utils напрямую, для одного и того же файла."""
    import loop_lock as ll
    import stale_locks as sl

    p = tmp_path / "sla.yaml"
    p.write_text("thresholds:\n  lock_stale: 6\n", encoding="utf-8")

    assert ll.load_lock_stale_hours(p) == 6.0
    assert su.load_lock_stale_hours(p) == 6.0

    monkeypatch_sla = sl.SLA_PATH
    try:
        sl.SLA_PATH = p
        assert sl.load_lock_stale_hours() == 6.0
    finally:
        sl.SLA_PATH = monkeypatch_sla
