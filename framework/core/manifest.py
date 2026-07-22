"""Статическая инспекция `AndroidManifest.xml` через `aapt dump xmltree` — не
требует Appium-сессии/устройства, только доступный на диске APK. Обёртка ничего
не знает о КОНКРЕТНОМ приложении (принимает произвольный `apk_path`, дефолт —
`settings.APK_PATH`); бизнес-факты (exported/intent-filter/cleartext/backup) —
`framework/steps/security_steps.py`.

Инструмент — `aapt` из build-tools SDK (`settings.AAPT`), НЕ `dumpsys package`
(misc-batch-0722, замечание critic прохода (5), `docs/09-history.md:771-773`):
атрибуты `exported`/`cleartextTraffic`/`fullBackupContent` в `dumpsys` неполны/
косвенны для надёжной автоматизации — `aapt` читает их напрямую из
скомпилированного бинарного манифеста.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field

from framework.config import settings

_DUMP_TIMEOUT = 30.0


@dataclass
class Node:
    """Один элемент манифеста (`E: имя (line=N)`). `attrs` — атрибуты этого узла
    (`A:`-строки на том же уровне отступа); `children` — вложенные элементы."""

    name: str
    indent: int
    attrs: dict[str, str] = field(default_factory=dict)
    children: list["Node"] = field(default_factory=list)


def dump_xmltree(apk_path: str | None = None, entry: str = "AndroidManifest.xml") -> str:
    """Запускает `aapt dump xmltree <apk> <entry>`, возвращает сырой текстовый вывод.
    Конечный `timeout` (тот же класс защиты, что `core/adb.py::_run` — AT-BUG-009):
    зависший локальный процесс не должен подвешивать прогон навсегда."""
    apk = apk_path or settings.APK_PATH
    try:
        cp = subprocess.run(
            [settings.AAPT, "dump", "xmltree", apk, entry],
            capture_output=True, text=True, timeout=_DUMP_TIMEOUT,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(f"aapt dump xmltree не ответил за {_DUMP_TIMEOUT}s") from exc
    if cp.returncode != 0 or not cp.stdout.strip():
        raise RuntimeError(
            f"aapt dump xmltree {entry} завершился с ошибкой (код {cp.returncode}): "
            f"{cp.stderr or cp.stdout!r}"
        )
    return cp.stdout


def _parse_attr_value(rest: str) -> str:
    """Разбирает правую часть `A:`-строки: `="value" (Raw: "value")` -> `value`;
    `=@0x7f120000` (resource reference) -> `@0x7f120000` как есть;
    `=(type 0x12)0xffffffff` (typed int/bool) -> `0xffffffff`."""
    rest = rest.strip()
    if rest.startswith('"'):
        m = re.match(r'"([^"]*)"', rest)
        return m.group(1) if m else rest
    if rest.startswith("@"):
        return rest.split()[0]
    m = re.search(r"\)(0x[0-9a-fA-F]+)$", rest)
    if m:
        return m.group(1)
    return rest


_E_RE = re.compile(r"^E:\s*(\S+)")
_A_RE = re.compile(r"^A:\s*([\w:.\-]+)\(.*?\)=(.*)$")


def parse_xmltree(text: str) -> Node:
    """Строит дерево из текстового вывода `aapt dump xmltree`.

    Эмпирически проверено на реальном выводе (`docs/09-history.md`, misc-batch-0722):
    отступ кодирует вложенность, и атрибуты (`A:`) СВОЕГО узла идут на ТОМ ЖЕ уровне
    отступа, что и его дочерние элементы (`E:`) — оба на 2 пробела глубже самого узла.
    Пример (`<manifest><uses-sdk .../></manifest>`):
    ```
      E: manifest (line=2)
        A: android:versionCode(...)=...      # атрибут manifest, отступ 4
        E: uses-sdk (line=7)                 # ребёнок manifest, тоже отступ 4
          A: android:minSdkVersion(...)=...  # атрибут uses-sdk, отступ 6
    ```
    Поэтому оба типа строк обрабатываются одним правилом: вытолкнуть из стека узлы
    с отступом >= текущего, затем — для `E:` протолкнуть новый узел в стек (он
    получает дальнейшие `A:`/`E:` как своих), для `A:` просто приписать атрибут
    новой вершине стека (без проталкивания — у атрибута нет своих детей)."""
    root = Node(name="__root__", indent=-1)
    stack: list[Node] = [root]
    for raw in text.splitlines():
        if not raw.strip() or raw.strip().startswith("N:"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        content = raw.strip()
        while stack[-1].indent >= indent:
            stack.pop()
        if content.startswith("E:"):
            m = _E_RE.match(content)
            name = m.group(1) if m else content
            node = Node(name=name, indent=indent)
            stack[-1].children.append(node)
            stack.append(node)
        elif content.startswith("A:"):
            m = _A_RE.match(content)
            if m:
                stack[-1].attrs[m.group(1)] = _parse_attr_value(m.group(2))
    return root


def find_all(node: Node, tag: str) -> list[Node]:
    """Рекурсивно ищет ВСЕ узлы с именем `tag` в поддереве `node` (включая сам `node`)."""
    result = [node] if node.name == tag else []
    for child in node.children:
        result.extend(find_all(child, tag))
    return result
