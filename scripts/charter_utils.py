"""charter_utils — общий обход exploratory-charters/ верхнего уровня.

Дедуп D-0081 (батч мелочей 2026-07-21, задача B): `_iter_charters()`
существовал байт-в-байт идентичной копией в scripts/sla_sweep.py и
scripts/queue_snapshot.py. scripts/stale_locks.py решает смежную, но НЕ
идентичную задачу: его `_iter_charter_locks()` обходит тот же каталог
(top-level `*.md`, skip README, parse frontmatter, только записи с
`id`), но возвращает генератор кортежей `(type, meta, body, path)` —
sweep() в stale_locks.py нужен именно `path`, чтобы перезаписать/снять
лок файла; это ДРУГАЯ сигнатура и другой тип возврата, не тот же
экземпляр `_iter_charters` (список dict), что был в двух других
модулях. Здесь единая точка правды для ОБЕИХ форм: один внутренний
обход (`_iter_charter_files`), поверх которого:
  - `_iter_charters()`      — список frontmatter-словарей (sla_sweep,
                              queue_snapshot — путь к файлу им не нужен);
  - `_iter_charter_files()` — генератор (meta, body, path) — из него
                              stale_locks достраивает свою 4-кортежную
                              форму (type, meta, body, path).

Имена с ведущим подчёркиванием, хоть и импортируются между модулями —
та же конвенция, что уже в кодовой базе (bs._parse_frontmatter,
bs._iter_artifacts, bi._rewrite_field): «внутренний обвязочный
помощник», не «стабильный публичный API пакета».

REPO не хранится модульной константой: обход принимает `repo: Path`
явным аргументом — вызывающие модули передают СВОЙ модульный REPO
(который тесты monkeypatch'ят per-module: ss.REPO/qs.REPO/sl.REPO),
поэтому изоляция тестов не ломается.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterator

import board_sync as bs

CHARTER_DIRNAME = "exploratory-charters"


def _iter_charter_files(repo: Path) -> Iterator[tuple[dict, str, Path]]:
    """(meta, body, path) для каждого charter'а верхнего уровня
    `repo/exploratory-charters/`.

    Не-рекурсивный glob (`glob("*.md")`, НЕ `rglob`) — `attachments/*.md`
    (скриншоты/дампы UI-дерева сессий exploratory-tester'а) не артефакты
    и не должны попадать в обход (находка critic N3). README.md
    пропускается явной проверкой имени (НЕ фильтром по маске "CH-*.md" —
    такой фильтр по ошибке исключил бы charter с некорректным id/именем
    файла, что ловится тестом validate_frontmatter на заведомо плохой
    id). Отдаёт только записи с непустым `id` во frontmatter. Каталога
    может не быть или он может быть пустым — это не ошибка, просто
    пустой обход (вызывающий код рендерит нули, не падает).
    """
    base = Path(repo) / CHARTER_DIRNAME
    if not base.exists():
        return
    for md in sorted(base.glob("*.md")):
        if md.name.upper() == "README.MD":
            continue
        meta, body = bs._parse_frontmatter(md.read_text(encoding="utf-8", errors="replace"))
        if meta.get("id"):
            yield meta, body, md


def _iter_charters(repo: Path) -> list[dict]:
    """Список frontmatter-словарей charter'ов (без body/path) — форма,
    нужная sla_sweep._charter_queue_wanted/queue_snapshot._charter_stats
    (путь к файлу им не нужен, в отличие от stale_locks._iter_charter_locks,
    который строит свою 4-кортежную форму поверх _iter_charter_files)."""
    return [meta for meta, _body, _path in _iter_charter_files(repo)]
