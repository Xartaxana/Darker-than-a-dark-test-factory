"""Дерево accessibility нативного слоя (UiAutomator2 `page_source` XML) и
геометрия попарного пересечения `bounds` интерактивных узлов (TC-150). Не
знает о конкретных экранах/локаторах приложения — чистая структура и
математика поверх уже читаемого XML-дерева, симметрично `BaseScreen.
_parse_bounds` (`framework/screens/base_screen.py`), но эта версия
дополнительно строит карту узел->родитель (`_parse_bounds` там работает с
ОДНИМ узлом, не с деревом целиком) — нужна ТОЛЬКО здесь, чтобы отличить
«родитель-потомок» (ожидаемое вложение) от «два независимых интерактивных
соседа» (TC-150 Then), не по одной лишь геометрии.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass

Bounds = tuple[int, int, int, int]

# Given/When TC-150: признак интерактивности — `clickable=true` ЛИБО явная
# роль button/switch/tab по имени `class` узла. В этом приложении Compose-
# кликабельные модификаторы почти всегда отдают `clickable="true"` без
# явного `Role` (сверено: `Role.*` не используется нигде в
# app-under-test — см. requirements TC-150), вторая ветка сохранена для
# полноты формулировки кейса и системных виджетов со встроенной ролью.
_INTERACTIVE_ROLE_HINTS = ("button", "switch", "tab")


def _is_true(value) -> bool:
    return str(value).strip().lower() == "true"


def _parse_bounds(bounds_str: str | None) -> Bounds | None:
    """Тот же парсер формата `bounds="[x1,y1][x2,y2]"`, что `BaseScreen.
    _parse_bounds` — намеренно НЕ импортируется оттуда (тот метод завязан на
    экземпляр `BaseScreen`, этот модуль — чистые функции без driver)."""
    if not bounds_str:
        return None
    try:
        left, right = bounds_str.split("][")
        x1, y1 = left.lstrip("[").split(",")
        x2, y2 = right.rstrip("]").split(",")
        return int(x1), int(y1), int(x2), int(y2)
    except (ValueError, AttributeError):
        return None


def _is_interactive(attrib: dict) -> bool:
    if _is_true(attrib.get("clickable")):
        return True
    cls = (attrib.get("class") or "").lower()
    return any(hint in cls for hint in _INTERACTIVE_ROLE_HINTS)


def _label_for(attrib: dict) -> str:
    """Приоритет подписи для отчёта о находке: content-desc -> text ->
    resource-id -> class (тот же приоритет, что у локаторов `BaseScreen`:
    `by_desc` > `by_text` > XPath)."""
    for key in ("content-desc", "text", "resource-id"):
        value = (attrib.get(key) or "").strip()
        if value:
            return value
    return attrib.get("class") or "?"


@dataclass(frozen=True)
class InteractiveNode:
    """Один интерактивный узел на конкретном снимке accessibility-дерева."""
    label: str
    bounds: Bounds
    elem: ET.Element


@dataclass(frozen=True)
class Overlap:
    """Находка: два РАЗНЫХ (не parent-child) интерактивных узла одного
    снимка, чьи `bounds` пересекаются."""
    a: InteractiveNode
    b: InteractiveNode
    rect: Bounds


def parse_interactive_nodes(page_source: str) -> tuple[list[InteractiveNode], dict[ET.Element, ET.Element]]:
    """Парсит `page_source` в список интерактивных узлов + карту `узел ->
    родитель` этого ЖЕ снимка. Узлы без распознаваемых `bounds`, с
    `displayed != "true"` (не на экране сейчас) или с вырожденным
    прямоугольником (нулевая ширина/высота) пропускаются — не предмет
    геометрии пересечения."""
    root = ET.fromstring(page_source)
    parent_map: dict[ET.Element, ET.Element] = {
        child: parent for parent in root.iter() for child in parent
    }
    nodes: list[InteractiveNode] = []
    for elem in root.iter():
        attrib = elem.attrib
        if not _is_interactive(attrib):
            continue
        if attrib.get("displayed") not in (None, "true"):
            continue
        bounds = _parse_bounds(attrib.get("bounds"))
        if bounds is None:
            continue
        x1, y1, x2, y2 = bounds
        if x2 <= x1 or y2 <= y1:
            continue
        nodes.append(InteractiveNode(label=_label_for(attrib), bounds=bounds, elem=elem))
    return nodes, parent_map


def _is_ancestor(candidate: ET.Element, node: ET.Element, parent_map: dict[ET.Element, ET.Element]) -> bool:
    """`True`, если `candidate` — предок `node` в дереве ЭТОГО снимка (идём
    вверх от `node` по карте родителей)."""
    current = parent_map.get(node)
    while current is not None:
        if current is candidate:
            return True
        current = parent_map.get(current)
    return False


def _is_parent_child(a: InteractiveNode, b: InteractiveNode, parent_map: dict[ET.Element, ET.Element]) -> bool:
    """Ожидаемое вложение (TC-150 Then, «не по одной лишь геометрии»): один
    узел — предок другого В ДЕРЕВЕ этого снимка. Два интерактивных узла с
    пересекающимися `bounds`, ни один из которых не предок другого (напр.
    независимый сосед, чей hit-box наехал на соседний), НЕ считаются
    parent-child и остаются кандидатом в находку."""
    return _is_ancestor(a.elem, b.elem, parent_map) or _is_ancestor(b.elem, a.elem, parent_map)


def _intersect(a: Bounds, b: Bounds) -> Bounds | None:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    if ix1 < ix2 and iy1 < iy2:
        return ix1, iy1, ix2, iy2
    return None


def find_overlaps(page_source: str) -> list[Overlap]:
    """TC-150 ядро: попарно для ВСЕХ интерактивных узлов ОДНОГО снимка
    (`page_source`) — пропускает parent-child пары (см. `_is_parent_child`),
    для остальных вычисляет пересечение прямоугольников `bounds`. Пустой
    список = свойство «bounds РАЗНЫХ интерактивных узлов не пересекаются»
    держится на этом снимке."""
    nodes, parent_map = parse_interactive_nodes(page_source)
    overlaps: list[Overlap] = []
    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            a, b = nodes[i], nodes[j]
            if _is_parent_child(a, b, parent_map):
                continue
            rect = _intersect(a.bounds, b.bounds)
            if rect is not None:
                overlaps.append(Overlap(a=a, b=b, rect=rect))
    return overlaps
