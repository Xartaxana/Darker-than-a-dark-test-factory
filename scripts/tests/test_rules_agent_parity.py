"""Parity-тест: агенты, диспатчащиеся правилами state/rules.yaml, присутствуют
в enum поля `agent` schemas/agent-output.schema.yaml (класс-детектор B1,
батч мелочей D-0081, 2026-07-21).

Рассинхрон enum с rules.yaml уже ловился на практике молча (комментарий
agent-output.schema.yaml: «прецедент CH-001..003 — exploratory-tester писал
test-strategist», enum-строка врёт молча) — этот тест механизирует ту же
сверку вместо ручного «правишь rules.yaml — сверь enum».

Единственное намеренное исключение — critic: в режиме charter-plan-review
он отдаёт вердикт координатору напрямую (SKILL.md qa-loop, «документный
класс») и agent_output не эмитит, поэтому в enum отсутствует НАМЕРЕННО (см.
комментарий у поля `agent` в самой схеме). Зафиксировано константой, а не
голым исключением по имени в теле теста — чтобы намерение было видно и
чтобы случайное появление critic в enum (без снятия исключения) тоже
подсвечивалось второй проверкой ниже.
"""
from __future__ import annotations

import yaml

import board_sync as bs

REPO = bs.REPO
RULES_PATH = REPO / "state" / "rules.yaml"
SCHEMA_PATH = REPO / "schemas" / "agent-output.schema.yaml"

# Единственное намеренное исключение из enum (см. docstring модуля и
# комментарий agent-output.schema.yaml у поля `agent`, вердикт critic
# B1/N1 2026-07-21).
ENUM_EXCEPTIONS = frozenset({"critic"})


def _rules_dispatch_agents() -> set[str]:
    data = yaml.safe_load(RULES_PATH.read_text(encoding="utf-8")) or {}
    return {r.get("dispatch") for r in data.get("rules", []) if r.get("dispatch")}


def _schema_agent_enum() -> set[str]:
    data = yaml.safe_load(SCHEMA_PATH.read_text(encoding="utf-8")) or {}
    enum = ((data.get("fields") or {}).get("agent") or {}).get("enum") or []
    return set(enum)


def test_every_dispatch_agent_in_schema_enum():
    """Каждый агент, на которого ссылается dispatch: в rules.yaml (кроме
    намеренного исключения critic), обязан быть в enum схемы."""
    rules_agents = _rules_dispatch_agents()
    schema_enum = _schema_agent_enum()

    missing = (rules_agents - ENUM_EXCEPTIONS) - schema_enum
    assert not missing, (
        "агенты dispatch: из state/rules.yaml отсутствуют в enum "
        f"schemas/agent-output.schema.yaml (agent): {sorted(missing)}"
    )


def test_enum_exception_is_still_excluded():
    """Критик реально исключён из enum сейчас — если бы кто-то добавил его
    в enum, не убрав константу-исключение выше, эта проверка укажет на
    рассинхрон намерения с фактом (исключение стало бы бессмысленным)."""
    schema_enum = _schema_agent_enum()
    assert ENUM_EXCEPTIONS & schema_enum == set(), (
        "ENUM_EXCEPTIONS содержит агента, который на самом деле уже есть "
        "в enum схемы — константа-исключение устарела, пересмотри её"
    )


def test_enum_exception_is_actually_dispatched_by_rules():
    """Обратная сверка: исключение должно называть реального агента из
    rules.yaml, а не мёртвую строку (иначе исключение ничего не защищает)."""
    rules_agents = _rules_dispatch_agents()
    assert ENUM_EXCEPTIONS <= rules_agents, (
        "ENUM_EXCEPTIONS называет агента, которого нет среди dispatch: "
        f"rules.yaml — проверь актуальность исключения: {sorted(ENUM_EXCEPTIONS - rules_agents)}"
    )
