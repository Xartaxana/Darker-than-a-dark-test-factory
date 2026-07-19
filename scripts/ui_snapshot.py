"""ui_snapshot — компактная ref-проекция живого дерева UI (экономия токенов воркеров).

Идея (agent-browser): вместо полного uiautomator/page_source XML (десятки КБ на
каждый взгляд — automator дважды упирался в лимит сессии на этом) агенту отдаётся
короткий пронумерованный список ТОЛЬКО значимых узлов (интерактивные или несущие
подпись), а `--ref eN` печатает готовые локаторы-кандидаты для конкретного узла —
вставляемые прямо в код screens (см. framework/screens/base_screen.py: by_desc/
by_text — это и есть приоритет наших локаторов content-desc > text > XPath).

Три источника входа:
  python scripts/ui_snapshot.py                 # живое снятие: adb exec-out uiautomator dump
  python scripts/ui_snapshot.py --file dump.xml # уже сохранённый дамп (или page_source)
  cat dump.xml | python scripts/ui_snapshot.py --stdin

Режимы вывода:
  (по умолчанию)     компактный список значимых узлов с ref [eN]
  --ref eN           локаторы-кандидаты для узла eN (content-desc/text/XPath + tap-фолбэк)
  --full             сырой XML как есть (эскейп-люк, если компактная проекция мешает)

Живое снятие (без --file/--stdin) требует adb в PATH и УСПЕШНО завершается только
если ничего не держит accessibility-service параллельно. Частая причина отказа —
активная Appium-сессия (сама держит uiautomator): тогда получишь внятную ошибку с
подсказкой сохранить driver.page_source в файл и передать через --file. Appium-клиент
внутри этого скрипта НЕ поднимается — задача ровно про проекцию уже полученного XML.

НЕ парсер общего назначения: рассчитан на формат `uiautomator dump` (атрибуты class/
text/content-desc/resource-id/bounds/clickable/.../scrollable) и на page_source
Appium, который использует тот же формат для UiAutomator2-драйвера.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

# Windows-консоль (cp1251) искажает кириллицу в print — форсируем UTF-8 (как в board_sync.py).
# Оба потока: SystemExit-подсказки и сводка узлов идут в stderr, не только в stdout.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

BOUNDS_RE = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")

# Критерий значимости узла (§2 спеки): интерактивный ИЛИ несёт подпись.
INTERACTIVE_BOOL_ATTRS = ("clickable", "long-clickable", "checkable", "scrollable")


def _is_true(v) -> bool:
    return str(v).strip().lower() == "true"


def _is_input_focusable(attrib: dict) -> bool:
    """focusable-input: поле ввода, доступное фокусу, даже если само не clickable
    (частый случай для Compose-текстовых полей)."""
    cls = attrib.get("class", "") or ""
    return _is_true(attrib.get("focusable")) and "EditText" in cls


def _is_significant(attrib: dict) -> bool:
    if any(_is_true(attrib.get(a)) for a in INTERACTIVE_BOOL_ATTRS):
        return True
    if _is_input_focusable(attrib):
        return True
    if str(attrib.get("text") or "").strip():
        return True
    if str(attrib.get("content-desc") or "").strip():
        return True
    return False


def _short_class(cls: str) -> str:
    cls = cls or ""
    return cls.rsplit(".", 1)[-1] if cls else "?"


def _label_for(attrib: dict) -> str:
    """Приоритет подписи: text -> content-desc (как в компактной строке узла)."""
    text = str(attrib.get("text") or "").strip()
    if text:
        return text
    return str(attrib.get("content-desc") or "").strip()


def _flags_for(attrib: dict) -> list[str]:
    flags = []
    if _is_true(attrib.get("clickable")) or _is_true(attrib.get("long-clickable")):
        flags.append("click")
    if attrib.get("enabled") is not None and not _is_true(attrib.get("enabled")):
        flags.append("enabled=false")
    if _is_true(attrib.get("checked")):
        flags.append("checked")
    if _is_true(attrib.get("scrollable")):
        flags.append("scroll")
    return flags


def _parse_bounds(s: str | None) -> tuple[int, int, int, int] | None:
    if not s:
        return None
    m = BOUNDS_RE.match(s)
    if not m:
        return None
    x1, y1, x2, y2 = (int(g) for g in m.groups())
    return x1, y1, x2, y2


def _bounds_str(b: tuple[int, int, int, int] | None) -> str:
    if not b:
        return "?"
    x1, y1, x2, y2 = b
    return f"{x1},{y1}..{x2},{y2}"


def _bounds_center(b: tuple[int, int, int, int]) -> tuple[int, int]:
    x1, y1, x2, y2 = b
    return (x1 + x2) // 2, (y1 + y2) // 2


# --- Дерево: обход, ref-нумерация, поиск подписанного предка -----------------

@dataclass
class Node:
    elem: ET.Element
    parent: "Node | None"
    sibling_index: int = 0  # 1-based индекс среди СИБЛИНГОВ С ТЕМ ЖЕ class (для XPath tag[n])
    ref: int | None = None
    children: list["Node"] = field(default_factory=list)


def _walk(root: ET.Element) -> list[Node]:
    """Возвращает узлы в порядке обхода дерева (pre-order = порядок документа) —
    именно этот порядок и определяет детерминированную нумерацию ref."""
    nodes: list[Node] = []

    def rec(elem: ET.Element, parent: Node | None) -> None:
        node = Node(elem=elem, parent=parent)
        nodes.append(node)
        if parent is not None:
            parent.children.append(node)
        for child in elem:
            rec(child, node)

    rec(root, None)

    # sibling_index — 1-based индекс среди детей общего родителя с тем же class
    # (семантика XPath `tag[n]`, не позиция среди ВСЕХ детей).
    for node in nodes:
        siblings = node.parent.children if node.parent is not None else nodes[:1]
        cls = node.elem.get("class", "")
        count = 0
        for sib in siblings:
            if sib.elem.get("class", "") == cls:
                count += 1
                if sib is node:
                    node.sibling_index = count
                    break
    return nodes


def _assign_refs(nodes: list[Node]) -> dict[str, Node]:
    ref_map: dict[str, Node] = {}
    n = 0
    for node in nodes:
        if _is_significant(node.elem.attrib):
            n += 1
            node.ref = n
            ref_map[f"e{n}"] = node
    return ref_map


def _nearest_labeled_ancestor(node: Node) -> Node | None:
    """«Ближайший подписанный родитель» (§3): первый предок с content-desc,
    text или resource-id — используем как якорь минимального XPath."""
    cur = node.parent
    while cur is not None:
        a = cur.elem.attrib
        if (str(a.get("content-desc") or "").strip()
                or str(a.get("text") or "").strip()
                or str(a.get("resource-id") or "").strip()):
            return cur
        cur = cur.parent
    return None


def _xpath_quote(s: str) -> str:
    if '"' not in s:
        return f'"{s}"'
    if "'" not in s:
        return f"'{s}'"
    return "concat(" + ", '\"', ".join(f'"{p}"' for p in s.split('"')) + ")"


def _xpath_from_ancestor(node: Node, ancestor: Node | None) -> str:
    """Минимальная глубина: путь ТОЛЬКО от ближайшего подписанного предка до узла,
    не от корня всего дерева."""
    chain: list[Node] = []
    cur: Node | None = node
    while cur is not None and cur is not ancestor:
        chain.append(cur)
        cur = cur.parent
    chain.reverse()  # ancestor -> ... -> node
    segs = [f'{n.elem.get("class", "*") or "*"}[{n.sibling_index}]' for n in chain]
    rel = "/".join(segs)

    if ancestor is None:
        return "//" + rel if rel else "//*"

    a = ancestor.elem.attrib
    desc = str(a.get("content-desc") or "").strip()
    rid = str(a.get("resource-id") or "").strip()
    text = str(a.get("text") or "").strip()
    if desc:
        anchor = f"//*[@content-desc={_xpath_quote(desc)}]"
    elif rid:
        anchor = f"//*[@resource-id={_xpath_quote(rid)}]"
    else:
        anchor = f"//*[@text={_xpath_quote(text)}]"
    return anchor + ("/" + rel if rel else "")


# --- Кандидаты локаторов (§3): приоритет content-desc -> text -> XPath -------

def _candidates_for(node: Node) -> list[str]:
    """Кандидаты в порядке приоритета framework/screens/base_screen.py
    (by_desc -> by_text -> XPath), плюс tap-фолбэк по центру bounds."""
    attrib = node.elem.attrib
    desc = str(attrib.get("content-desc") or "").strip()
    text = str(attrib.get("text") or "").strip()
    bounds = _parse_bounds(attrib.get("bounds"))
    out: list[str] = []

    if desc:
        out.append(f'content-desc -> self.by_desc("{desc}")'
                    f'   # AppiumBy.ACCESSIBILITY_ID, "{desc}"')
    if text:
        out.append(f'text -> self.by_text("{text}")'
                    f'   # UiSelector().text("{text}")')
    if not desc and not text:
        ancestor = _nearest_labeled_ancestor(node)
        xpath = _xpath_from_ancestor(node, ancestor)
        out.append("XPath (мин. глубина через ближайшего подписанного родителя) -> "
                    f"(AppiumBy.XPATH, '{xpath}')")
    if bounds:
        cx, cy = _bounds_center(bounds)
        out.append(f"tap-фолбэк (центр bounds) -> self.driver.tap([({cx}, {cy})])")
    return out


# --- Рендер ---------------------------------------------------------------

def render_compact(nodes: list[Node]) -> str:
    lines = []
    for node in nodes:
        if node.ref is None:
            continue
        attrib = node.elem.attrib
        cls = _short_class(attrib.get("class", ""))
        label = _label_for(attrib)
        flags = _flags_for(attrib)
        bounds = _parse_bounds(attrib.get("bounds"))
        parts = [f"[e{node.ref}]", cls, f'"{label}"']
        if flags:
            parts.append(" ".join(flags))
        parts.append(f"bounds={_bounds_str(bounds)}")
        lines.append(" ".join(parts))
    return "\n".join(lines)


def render_ref_detail(node: Node) -> str:
    attrib = node.elem.attrib
    cls = _short_class(attrib.get("class", ""))
    label = _label_for(attrib)
    bounds = _parse_bounds(attrib.get("bounds"))
    header = f'[e{node.ref}] {cls} "{label}" bounds={_bounds_str(bounds)}'
    lines = [header, "Кандидаты локаторов (по приоритету):"]
    for i, c in enumerate(_candidates_for(node), 1):
        lines.append(f"  {i}. {c}")
    return "\n".join(lines)


# --- Ввод: --file / --stdin / живой adb --------------------------------------

def _extract_xml(text: str) -> str:
    """adb exec-out иногда примешивает служебные строки в stdout вокруг XML —
    вырезаем от `<?xml`/`<hierarchy` до закрывающего `</hierarchy>`."""
    start = text.find("<?xml")
    if start == -1:
        start = text.find("<hierarchy")
    if start == -1:
        return ""
    end = text.rfind("</hierarchy>")
    if end == -1:
        return text[start:]
    return text[start:end + len("</hierarchy>")]


def _live_dump() -> str:
    env = dict(os.environ)
    # MSYS_NO_PATHCONV=1: на Windows/Git-Bash автоконверсия путей может исковеркать
    # "/dev/tty" в аргументах adb — как и в scripts/seed-room-db.sh/install-mitm-ca.sh.
    env["MSYS_NO_PATHCONV"] = "1"
    env["MSYS2_ARG_CONV_EXCL"] = "*"
    try:
        result = subprocess.run(
            ["adb", "exec-out", "uiautomator", "dump", "/dev/tty"],
            capture_output=True, env=env, timeout=20,
        )
    except FileNotFoundError:
        raise SystemExit("adb не найден в PATH — используй --file <path> с сохранённым "
                          "page_source/дампом, либо --stdin.")
    except subprocess.TimeoutExpired:
        raise SystemExit(
            "adb завис (timeout 20s) при снятии живого дерева. Частая причина — активная "
            "Appium-сессия уже держит uiautomator/accessibility-service, и параллельный "
            "`adb uiautomator dump` конфликтует с ней.\n"
            "Сохрани дерево из самой сессии и передай его сюда:\n"
            "  Python (в тесте/отладке): open('dump.xml','w',encoding='utf-8')."
            "write(driver.page_source)\n"
            "  затем: python scripts/ui_snapshot.py --file dump.xml"
        )
    stdout = result.stdout.decode("utf-8", errors="replace")
    stderr = result.stderr.decode("utf-8", errors="replace")
    xml_text = _extract_xml(stdout)
    if result.returncode != 0 or not xml_text:
        raise SystemExit(
            f"не удалось снять живое дерево через `adb exec-out uiautomator dump` "
            f"(код возврата {result.returncode}).\n"
            f"stderr: {stderr.strip() or '(пусто)'}\n"
            "Частая причина — активная Appium-сессия держит uiautomator/accessibility-service.\n"
            "Сохрани driver.page_source в файл и передай через --file <path> (или --stdin)."
        )
    return xml_text


def _get_input(args: argparse.Namespace) -> str:
    if args.file:
        return args.file.read_text(encoding="utf-8", errors="replace")
    if args.stdin:
        return sys.stdin.read()
    return _live_dump()


# --- CLI ----------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="ui_snapshot.py",
        description="Компактная ref-проекция живого UI-дерева (uiautomator dump / page_source).",
    )
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--file", type=Path, help="дамп/page_source из файла")
    src.add_argument("--stdin", action="store_true", help="читать XML из stdin")
    ap.add_argument("--full", action="store_true", help="напечатать сырой XML как есть")
    ap.add_argument("--ref", metavar="eN", help="локаторы-кандидаты для узла eN")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    xml_text = _get_input(args)

    if args.full:
        print(xml_text)
        return 0

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        print(f"не удалось разобрать XML: {e}", file=sys.stderr)
        return 1

    nodes = _walk(root)
    ref_map = _assign_refs(nodes)

    if args.ref:
        key = args.ref if args.ref.startswith("e") else f"e{args.ref}"
        node = ref_map.get(key)
        if node is None:
            print(f"узел {args.ref} не найден (в снимке {len(ref_map)} значимых узлов)",
                  file=sys.stderr)
            return 1
        print(render_ref_detail(node))
        return 0

    print(render_compact(nodes))
    print(f"\n{len(ref_map)} значимых узлов из {len(nodes)} в дереве "
          f"(--ref eN — локаторы-кандидаты, --full — сырой XML).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
