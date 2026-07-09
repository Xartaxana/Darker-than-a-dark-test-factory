"""Генератор synthetic-recordings для replay-режима (AT-BUG-004).

Пересобирает `.mitm`-файлы в `framework/data/recordings/` из
`framework/data/recording_builder.py`. Идемпотентен — перезаписывает существующие
файлы. Запускать при любой правке разметки листинга (`_blurb_html`) или после того,
как AO3 поменяла реальную структуру `li.work.blurb` (сверять с
`framework/web/selectors.py` и живым деревом, `python scripts/ui_snapshot.py`).

Использование (из корня репозитория, как и любой скрипт обвязки):
    python scripts/build_replay_recordings.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from framework.config import settings  # noqa: E402
from framework.data import recording_builder as rb  # noqa: E402
from framework.data.works import ALL as ALL_WORKS  # noqa: E402


def build_listing_basic() -> Path:
    """Одна листинговая страница с блёрбами всех эталонных работ
    (`framework/data/works.py::ALL`) — покрывает TC-013/014/015/043/045
    (см. `bugs/AT-BUG-004.md` §Обсуждение, оценка объёма test-automator)."""
    html = rb.render_listing_html(ALL_WORKS)
    flow = rb.make_html_get_flow(rb.LISTING_BASIC_URL, html)
    path = settings.RECORDINGS_DIR / rb.LISTING_BASIC_FILENAME
    rb.write_flows(path, [flow])
    return path


def main() -> None:
    path = build_listing_basic()
    print(f"written: {path}")


if __name__ == "__main__":
    main()
