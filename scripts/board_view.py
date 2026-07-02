"""board_view — лёгкая HTML-борда для локального просмотра БЕЗ git и без коммитов.

Читает те же артефакты (test-cases/, bugs/, runs/), что и board_sync, и рендерит
самодостаточный board-view.html (данные вшиты внутрь, открывается по file://).
Для стадии 1 (смотрим статусы локально) — обновил и открыл, никаких коммитов.

Полноценная борда TrackState (для GitHub Pages) генерируется отдельно board_sync.py.

Запуск:  python scripts/board_view.py   # пишет board-view.html и печатает путь
"""
from __future__ import annotations

import html
import json
from pathlib import Path

from board_sync import (  # переиспользуем парсер и метаданные статусов — один источник
    REPO, STATUSES, STATUS_MAP, _iter_artifacts, _labels_for, _priority_for,
)

OUT = REPO / "board-view.html"

STATUS_NAME = {sid: name for sid, name, _ in STATUSES}
STATUS_CAT = {sid: cat for sid, _, cat in STATUSES}
CAT_COLOR = {"new": "#b23", "indeterminate": "#b70", "done": "#264"}
TYPE_TITLE = {"test-case": "Test Cases", "bug": "Bugs", "run": "Test Runs"}
# Порядок колонок по типам (наши статусные машины)
COLUMNS = {
    "test-case": ["tc-draft", "tc-review", "tc-approved", "tc-automated"],
    "bug": ["bug-open", "bug-reopened", "bug-blocked", "bug-fixed", "bug-verified", "bug-rejected", "bug-intended"],
    "run": ["run-needstriage", "run-triaged", "run-closed"],
}


def collect():
    by_type: dict[str, list[dict]] = {"test-case": [], "bug": [], "run": []}
    for itype, meta, _body, src in _iter_artifacts():
        status_id = STATUS_MAP[itype].get(str(meta.get("status", "")))
        by_type[itype].append({
            "key": str(meta["id"]),
            "summary": str(meta.get("title", meta["id"])),
            "status": status_id,
            "status_name": STATUS_NAME.get(status_id, str(meta.get("status"))),
            "priority": _priority_for(itype, meta).upper(),
            "labels": _labels_for(itype, meta),
            "src": src.relative_to(REPO).as_posix(),
        })
    return by_type


def render(by_type) -> str:
    def esc(s):
        return html.escape(str(s))

    sections = []
    total = 0
    for itype in ("test-case", "bug", "run"):
        tickets = by_type[itype]
        total += len(tickets)
        cols_html = []
        for sid in COLUMNS[itype]:
            cards = [t for t in tickets if t["status"] == sid]
            card_html = "".join(
                f'<div class="card" title="{esc(t["src"])}">'
                f'<div class="k">{esc(t["key"])} <span class="pri p{esc(t["priority"])}">{esc(t["priority"])}</span></div>'
                f'<div class="s">{esc(t["summary"])}</div>'
                f'<div class="lbls">{"".join(f"<span>{esc(l)}</span>" for l in t["labels"][:4])}</div>'
                f'</div>'
                for t in cards
            )
            cols_html.append(
                f'<div class="col"><div class="colhead" style="border-color:{CAT_COLOR[STATUS_CAT[sid]]}">'
                f'{esc(STATUS_NAME[sid])} <b>{len(cards)}</b></div>{card_html or "<div class=empty>—</div>"}</div>'
            )
        sections.append(
            f'<h2>{esc(TYPE_TITLE[itype])} <span class="cnt">{len(tickets)}</span></h2>'
            f'<div class="board">{"".join(cols_html)}</div>'
        )

    return f"""<!doctype html><html lang=ru><head><meta charset=utf-8>
<title>AO3 QA — борда</title>
<style>
:root{{color-scheme:light dark}}
body{{font:14px/1.4 system-ui,Segoe UI,sans-serif;margin:0;padding:20px;background:#faf7f5;color:#1a1a1a}}
@media(prefers-color-scheme:dark){{body{{background:#16130f;color:#e7e2da}}.card{{background:#221d17;border-color:#3a332a}}.colhead{{background:#1d1813}}}}
h1{{margin:0 0 4px}} .sub{{color:#888;margin-bottom:20px}}
h2{{margin:26px 0 10px;font-size:16px}} .cnt{{color:#888;font-weight:normal}}
.board{{display:flex;gap:12px;overflow-x:auto;padding-bottom:6px}}
.col{{min-width:190px;flex:1}}
.colhead{{font-size:12px;text-transform:uppercase;letter-spacing:.04em;padding:6px 8px;border-left:3px solid;background:#efe9e4;border-radius:4px;margin-bottom:8px}}
.colhead b{{float:right}}
.card{{background:#fff;border:1px solid #e3ddd6;border-radius:6px;padding:8px 10px;margin-bottom:8px;box-shadow:0 1px 2px rgba(0,0,0,.04)}}
.k{{font-weight:600;font-size:12px;color:#a44}} .s{{margin:3px 0}}
.pri{{font-size:10px;padding:1px 5px;border-radius:8px;background:#eee;color:#555;float:right}}
.pP0{{background:#c0392b;color:#fff}}.pP1{{background:#e08600;color:#fff}}.pP2{{background:#dfd8cf;color:#333}}.pP3{{background:#eee;color:#777}}
.lbls span{{display:inline-block;font-size:10px;color:#777;background:#f1ece7;border-radius:6px;padding:0 5px;margin:2px 3px 0 0}}
.empty{{color:#bbb;text-align:center;padding:6px}}
</style></head><body>
<h1>AO3 Reader — QA борда</h1>
<div class=sub>Локальный просмотр без коммитов · {total} тикетов · источник: test-cases/ · bugs/ · runs/ · пересобрать: <code>python scripts/board_view.py</code></div>
{"".join(sections)}
</body></html>"""


def build():
    by_type = collect()
    OUT.write_text(render(by_type), encoding="utf-8")
    n = sum(len(v) for v in by_type.values())
    print(f"board-view.html собран: {n} тикетов -> {OUT}")


if __name__ == "__main__":
    build()
