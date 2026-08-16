"""Юнит-тесты scripts/pass_summary.py (Д п.5, канал пустоты прохода)."""
from __future__ import annotations

import datetime
import json

import pytest

import pass_summary as ps

NOW = datetime.datetime(2026, 8, 16, 23, 30, 0, tzinfo=datetime.timezone.utc)


def test_write_summary_writes_machine_ts_and_all_fields(tmp_path):
    out = tmp_path / "last-pass-summary.json"

    data = ps.write_summary(triggered=3, deferred=1, rescan_delta=2, output_path=out, now=NOW)

    assert data == {"ts": "2026-08-16T23:30:00Z", "triggered": 3, "deferred": 1,
                    "rescan_delta": 2}
    on_disk = json.loads(out.read_text(encoding="utf-8"))
    assert on_disk == data


def test_write_summary_zero_values_are_valid_empty_pass(tmp_path):
    out = tmp_path / "last-pass-summary.json"

    data = ps.write_summary(triggered=0, deferred=0, rescan_delta=0, output_path=out, now=NOW)

    assert data == {"ts": "2026-08-16T23:30:00Z", "triggered": 0, "deferred": 0,
                    "rescan_delta": 0}


@pytest.mark.parametrize("field", ["triggered", "deferred", "rescan_delta"])
def test_write_summary_rejects_negative_values(tmp_path, field):
    out = tmp_path / "last-pass-summary.json"
    kwargs = {"triggered": 1, "deferred": 1, "rescan_delta": 1, "output_path": out, "now": NOW}
    kwargs[field] = -1

    with pytest.raises(ValueError):
        ps.write_summary(**kwargs)
    assert not out.exists()


def test_write_summary_atomic_no_tmp_file_left_behind(tmp_path):
    out = tmp_path / "sub" / "last-pass-summary.json"

    ps.write_summary(triggered=1, deferred=0, rescan_delta=0, output_path=out, now=NOW)

    assert out.exists()
    assert not out.with_name(out.name + ".tmp").exists()


def test_write_summary_overwrites_previous_content(tmp_path):
    out = tmp_path / "last-pass-summary.json"
    ps.write_summary(triggered=5, deferred=5, rescan_delta=5, output_path=out, now=NOW)

    later = NOW + datetime.timedelta(minutes=30)
    ps.write_summary(triggered=0, deferred=0, rescan_delta=0, output_path=out, now=later)

    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["ts"] == "2026-08-17T00:00:00Z"
    assert data["triggered"] == 0


# ---------------------------------------------------------------------------
# main() — CLI
# ---------------------------------------------------------------------------

def test_main_writes_file_and_exits_0(tmp_path, capsys):
    out = tmp_path / "last-pass-summary.json"

    code = ps.main(["--triggered", "2", "--deferred", "0", "--rescan", "1",
                    "--output", str(out)])

    assert code == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["triggered"] == 2 and data["deferred"] == 0 and data["rescan_delta"] == 1
    assert "ts=" in capsys.readouterr().out


def test_main_negative_argument_exits_1_without_writing(tmp_path, capsys):
    out = tmp_path / "last-pass-summary.json"

    code = ps.main(["--triggered", "-1", "--deferred", "0", "--rescan", "0",
                    "--output", str(out)])

    assert code == 1
    assert not out.exists()
    assert "отказ" in capsys.readouterr().out


def test_main_missing_required_args_exits_nonzero_argparse(tmp_path):
    with pytest.raises(SystemExit) as exc_info:
        ps.main(["--triggered", "1"])
    assert exc_info.value.code != 0
