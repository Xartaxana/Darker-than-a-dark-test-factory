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
    REPO, STATUSES, STATUS_MAP, _assignee_for, _iter_artifacts, _labels_for, _priority_for,
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
    for itype, meta, body, src in _iter_artifacts():
        status_id = STATUS_MAP[itype].get(str(meta.get("status", "")))
        lock = str(meta.get("lock") or "").strip()
        by_type[itype].append({
            "key": str(meta["id"]),
            "itype": itype,
            "summary": str(meta.get("title", meta["id"])),
            "status": status_id,
            "status_name": STATUS_NAME.get(status_id, str(meta.get("status"))),
            "priority": _priority_for(itype, meta).upper(),
            "labels": _labels_for(itype, meta),
            # Пустой lock -> None: бейдж "кто работает" на карточке рисуем ТОЛЬКО
            # при непустом lock (qa-agents по умолчанию не шумит, см. board_sync).
            "assignee": _assignee_for(meta) if lock else None,
            "src": src.relative_to(REPO).as_posix(),
            "body": body.strip(),
        })
    return by_type


def render(by_type, live: bool = False) -> str:
    def esc(s):
        return html.escape(str(s))

    import datetime
    stamp = datetime.datetime.now().strftime("%H:%M:%S")
    sections = []
    total = 0
    detail_map = {}
    for itype in ("test-case", "bug", "run"):
        tickets = by_type[itype]
        total += len(tickets)
        cols_html = []
        for sid in COLUMNS[itype]:
            cards = [t for t in tickets if t["status"] == sid]

            def pri_widget(t):
                if live and t["itype"] == "test-case":
                    opts = "".join(
                        f'<option value="{p}"{" selected" if p == t["priority"] else ""}>{p}</option>'
                        for p in ("P0", "P1", "P2", "P3")
                    )
                    return (f'<select class="pri pri-select p{esc(t["priority"])}" '
                            f'data-key="{esc(t["key"])}" onclick="event.stopPropagation()" '
                            f'onchange="setPriority(this)">{opts}</select>')
                return f'<span class="pri p{esc(t["priority"])}">{esc(t["priority"])}</span>'

            for t in cards:
                detail_map[t["key"]] = {
                    "summary": t["summary"], "body": t["body"], "src": t["src"],
                    "status": t["status_name"], "priority": t["priority"],
                }

            def agent_badge(t):
                if not t["assignee"]:
                    return ""
                return (f'<div class="agentrow"><span class="agent" '
                        f'title="в работе: {esc(t["assignee"])}">⚙ {esc(t["assignee"])}</span></div>')

            card_html = "".join(
                f'<div class="card" data-pri="{esc(t["priority"])}" data-key="{esc(t["key"])}" '
                f'title="{esc(t["src"])}" onclick="openDetail(event, \'{esc(t["key"])}\')">'
                f'<div class="k">{esc(t["key"])} {pri_widget(t)}</div>'
                f'<div class="s">{esc(t["summary"])}</div>'
                f'{agent_badge(t)}'
                f'<div class="lbls">{"".join(f"<span>{esc(l)}</span>" for l in t["labels"][:4])}</div>'
                + (f'<button class="approve" onclick="event.stopPropagation(); approveCard(\'{esc(t["key"])}\', this)">✓ Approve</button>'
                   if live and t["itype"] == "test-case" and t["status_name"] == "Review" else "")
                + '</div>'
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

    if live:
        # На сервере каждый GET пересобирает доску из артефактов, поэтому кнопка = reload.
        refresh_btn = '<button class="refresh" onclick="location.reload()" title="Пересобрать из артефактов">↻ Обновить</button>'
        mode_note = "Живой просмотр без коммитов (кнопка пересобирает из артефактов)"
    else:
        refresh_btn = ""
        mode_note = "Статический снимок без коммитов · пересобрать: python scripts/board_view.py"
    sort_btn = ('<button class="sortbtn" id="sortbtn" onclick="toggleSort()" '
                'title="Отсортировать карточки внутри колонок по приоритету">⇅ По приоритету</button>')

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
.card{{background:#fff;border:1px solid #e3ddd6;border-radius:6px;padding:8px 10px;margin-bottom:8px;box-shadow:0 1px 2px rgba(0,0,0,.04);cursor:pointer}}
.card:hover{{border-color:#c0392b}}
.k{{font-weight:600;font-size:12px;color:#a44}} .s{{margin:3px 0}}
.pri{{font-size:10px;padding:1px 5px;border-radius:8px;background:#eee;color:#555;float:right}}
.pP0{{background:#c0392b;color:#fff}}.pP1{{background:#e08600;color:#fff}}.pP2{{background:#dfd8cf;color:#333}}.pP3{{background:#eee;color:#777}}
.pri-select{{border:none;font:700 10px system-ui;cursor:pointer;appearance:none;-webkit-appearance:none}}
.lbls span{{display:inline-block;font-size:10px;color:#777;background:#f1ece7;border-radius:6px;padding:0 5px;margin:2px 3px 0 0}}
.agentrow{{margin-top:3px}}
.agent{{display:inline-block;font-size:10px;font-weight:600;color:#fff;background:#5b3fa0;border-radius:8px;padding:1px 6px}}
.empty{{color:#bbb;text-align:center;padding:6px}}
.refresh{{font:600 13px system-ui;cursor:pointer;border:1px solid #c94;background:#c0392b;color:#fff;border-radius:6px;padding:7px 14px;margin-left:12px}}
.refresh:hover{{background:#a93226}} .refresh:active{{transform:translateY(1px)}}
.head{{display:flex;align-items:center;flex-wrap:wrap;gap:6px}}
.sortbtn{{font:600 13px system-ui;cursor:pointer;border:1px solid #bbb;background:#efe9e4;color:#333;border-radius:6px;padding:7px 14px}}
.sortbtn.active{{background:#264;color:#fff;border-color:#264}}
.approve{{display:block;width:100%;margin-top:6px;font:600 11px system-ui;cursor:pointer;border:1px solid #2a6;background:#eafaf0;color:#194;border-radius:5px;padding:4px 6px}}
.approve:hover{{background:#264;color:#fff}} .approve:disabled{{opacity:.5;cursor:default}}
#backdrop{{position:fixed;inset:0;background:rgba(0,0,0,.25);opacity:0;pointer-events:none;transition:opacity .15s;z-index:10}}
#backdrop.open{{opacity:1;pointer-events:auto}}
#detail{{position:fixed;top:0;right:0;bottom:0;width:min(560px,92vw);background:#fff;box-shadow:-4px 0 18px rgba(0,0,0,.18);
  transform:translateX(100%);transition:transform .18s;z-index:11;display:flex;flex-direction:column}}
#detail.open{{transform:translateX(0)}}
@media(prefers-color-scheme:dark){{#detail{{background:#1d1813;color:#e7e2da}}}}
#detail .dhead{{display:flex;align-items:start;justify-content:space-between;gap:10px;padding:16px 18px;border-bottom:1px solid #e3ddd6}}
@media(prefers-color-scheme:dark){{#detail .dhead{{border-color:#3a332a}}}}
#detail .dtitle{{font-size:15px;font-weight:600;margin:0 0 4px}}
#detail .dmeta{{font-size:11px;color:#888}}
#detail .dclose{{cursor:pointer;border:none;background:none;font-size:20px;color:#888;line-height:1;padding:2px 6px}}
#detail .dclose:hover{{color:#c0392b}}
#detail .dbody{{padding:16px 18px;overflow-y:auto;flex:1;font-size:13.5px;line-height:1.6}}
#detail .dbody h3,#detail .dbody h4,#detail .dbody h5{{margin:18px 0 8px;line-height:1.3}}
#detail .dbody h3:first-child,#detail .dbody h4:first-child{{margin-top:0}}
#detail .dbody p{{margin:8px 0}}
#detail .dbody ul{{margin:6px 0;padding-left:22px}}
#detail .dbody li{{margin:3px 0}}
#detail .dbody code{{background:#f1ece7;border-radius:3px;padding:1px 5px;font:12px ui-monospace,Consolas,Menlo,monospace}}
@media(prefers-color-scheme:dark){{#detail .dbody code{{background:#2a241c}}}}
#detail .dbody table{{border-collapse:collapse;width:100%;margin:10px 0;font-size:12.5px}}
#detail .dbody th,#detail .dbody td{{border:1px solid #e3ddd6;padding:5px 8px;text-align:left}}
@media(prefers-color-scheme:dark){{#detail .dbody th,#detail .dbody td{{border-color:#3a332a}}}}
#detail .dbody th{{background:#efe9e4}}
@media(prefers-color-scheme:dark){{#detail .dbody th{{background:#241f18}}}}
</style></head><body>
<div class=head><h1>AO3 Reader — QA борда</h1>{refresh_btn}{sort_btn}</div>
<div class=sub>{mode_note} · {total} тикетов · обновлено {stamp} · источник: test-cases/ · bugs/ · runs/</div>
{"".join(sections)}
<div id="backdrop" onclick="closeDetail()"></div>
<aside id="detail">
  <div class="dhead">
    <div><div class="dtitle" id="dtitle"></div><div class="dmeta" id="dmeta"></div></div>
    <button class="dclose" onclick="closeDetail()" title="Закрыть (Esc)">×</button>
  </div>
  <div class="dbody" id="dbody"></div>
</aside>
<script>
const DETAIL = {json.dumps(detail_map, ensure_ascii=False).replace("</", "<\\/")};
function mdEsc(s) {{ return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }}
function mdInline(s) {{
  s = mdEsc(s);
  s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
  s = s.replace(/\\*\\*([^*]+)\\*\\*/g, '<strong>$1</strong>');
  return s;
}}
function renderMD(md) {{
  const lines = md.split('\\n');
  let html = '', inList = false, tHead = null, tRows = [], inTable = false;
  const flushTable = () => {{
    if (!tHead) return;
    html += '<table><thead><tr>' + tHead.map(c => '<th>' + mdInline(c) + '</th>').join('') + '</tr></thead><tbody>';
    tRows.forEach(r => {{ html += '<tr>' + r.map(c => '<td>' + mdInline(c) + '</td>').join('') + '</tr>'; }});
    html += '</tbody></table>';
    tHead = null; tRows = []; inTable = false;
  }};
  const closeList = () => {{ if (inList) {{ html += '</ul>'; inList = false; }} }};
  for (const raw of lines) {{
    const line = raw;
    if (/^\\s*\\|.*\\|\\s*$/.test(line)) {{
      const cells = line.trim().replace(/^\\||\\|$/g, '').split('|').map(c => c.trim());
      if (cells.every(c => /^:?-{{1,}}:?$/.test(c))) continue;
      if (!inTable) {{ inTable = true; tHead = cells; }} else {{ tRows.push(cells); }}
      continue;
    }} else if (inTable) {{ flushTable(); }}
    const h = line.match(/^(#{{1,6}})\\s+(.*)$/);
    if (h) {{
      closeList();
      const lvl = Math.min(h[1].length + 2, 6);
      html += '<h' + lvl + '>' + mdInline(h[2]) + '</h' + lvl + '>';
      continue;
    }}
    const li = line.match(/^\\s*-\\s+(.*)$/);
    if (li) {{
      if (!inList) {{ html += '<ul>'; inList = true; }}
      html += '<li>' + mdInline(li[1]) + '</li>';
      continue;
    }} else {{ closeList(); }}
    if (line.trim() === '') continue;
    html += '<p>' + mdInline(line) + '</p>';
  }}
  closeList();
  flushTable();
  return html;
}}
function openDetail(ev, key) {{
  const t = DETAIL[key];
  if (!t) return;
  document.getElementById('dtitle').textContent = key + ' — ' + t.summary;
  document.getElementById('dmeta').textContent = t.status + ' · ' + t.priority + ' · ' + t.src;
  document.getElementById('dbody').innerHTML = t.body ? renderMD(t.body) : '<p>(пусто)</p>';
  document.getElementById('detail').classList.add('open');
  document.getElementById('backdrop').classList.add('open');
}}
function closeDetail() {{
  document.getElementById('detail').classList.remove('open');
  document.getElementById('backdrop').classList.remove('open');
}}
document.addEventListener('keydown', e => {{ if (e.key === 'Escape') closeDetail(); }});
</script>
<script>
const PRI_ORDER = {{P0:0, P1:1, P2:2, P3:3}};
let sorted = localStorage.getItem('board.sortByPriority') === '1';
function applySort() {{
  document.querySelectorAll('.col').forEach(col => {{
    const cards = Array.from(col.querySelectorAll('.card'));
    if (!cards.length) return;
    if (sorted) {{
      cards.sort((a, b) => {{
        const pa = PRI_ORDER[a.dataset.pri] ?? 99;
        const pb = PRI_ORDER[b.dataset.pri] ?? 99;
        return pa - pb;
      }});
    }} else {{
      cards.sort((a, b) => (a.dataset.origIndex - b.dataset.origIndex));
    }}
    cards.forEach(c => col.appendChild(c));
  }});
  document.getElementById('sortbtn').classList.toggle('active', sorted);
}}
function toggleSort() {{
  sorted = !sorted;
  localStorage.setItem('board.sortByPriority', sorted ? '1' : '0');
  applySort();
}}
document.querySelectorAll('.col').forEach(col => {{
  Array.from(col.querySelectorAll('.card')).forEach((c, i) => c.dataset.origIndex = i);
}});
applySort();
async function setPriority(sel) {{
  const key = sel.dataset.key;
  const newPri = sel.value;
  const prevClass = sel.className;
  sel.disabled = true;
  try {{
    const resp = await fetch('/priority?key=' + encodeURIComponent(key) + '&priority=' + encodeURIComponent(newPri), {{ method: 'POST' }});
    const data = await resp.json();
    if (data.ok) {{
      sel.className = 'pri pri-select p' + newPri;
      sel.closest('.card').dataset.pri = newPri;
      applySort();
    }} else {{
      alert('Не удалось изменить приоритет ' + key + ': ' + data.message);
      sel.className = prevClass;
      sel.value = sel.closest('.card').dataset.pri;
    }}
  }} catch (e) {{
    alert('Ошибка запроса: ' + e);
    sel.className = prevClass;
  }} finally {{
    sel.disabled = false;
  }}
}}
async function approveCard(key, btn) {{
  btn.disabled = true;
  btn.textContent = '…';
  try {{
    const resp = await fetch('/approve?key=' + encodeURIComponent(key), {{ method: 'POST' }});
    const data = await resp.json();
    if (data.ok) {{
      location.reload();
    }} else {{
      alert('Не удалось утвердить ' + key + ': ' + data.message);
      btn.disabled = false;
      btn.textContent = '✓ Approve';
    }}
  }} catch (e) {{
    alert('Ошибка запроса: ' + e);
    btn.disabled = false;
    btn.textContent = '✓ Approve';
  }}
}}
</script>
</body></html>"""


def build():
    by_type = collect()
    OUT.write_text(render(by_type), encoding="utf-8")
    n = sum(len(v) for v in by_type.values())
    print(f"board-view.html собран: {n} тикетов -> {OUT}")


if __name__ == "__main__":
    build()
