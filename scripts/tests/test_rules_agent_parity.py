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

Расширение батча мелочей №2 сессии 2026-07-21 (приёмка misc-batch-0721,
D-0081) добавляет три дополнительных шва parity:

- S1: каждый dispatch-агент rules.yaml обязан иметь файл роли
  .claude/agents/<agent>.md (реестр агентов конвейера существует).
- S2: frontmatter `model:` этого файла роли обязан быть значением,
  которое реально распознаёт ярусная матрица scripts/log_append.py
  (la.TIER_ORDER — haiku/sonnet/opus/fable; ту же логику разбора
  frontmatter использует сам гейт log_append при `_resolve_agent_tier`,
  поэтому здесь переиспользуется `la._read_agent_frontmatter_model`, а
  не отдельный ре-имплементированный парсер).
- N1: двунаправленность исходного parity-теста — (а) rules_agents не
  пуст (защита от vacuous pass при дрейфе структуры rules.yaml) и (б)
  обратная сверка enum→rules.yaml (мёртвые записи enum, которые больше
  никем не диспатчатся).
"""
from __future__ import annotations

import yaml

import board_sync as bs
import log_append as la

REPO = bs.REPO
RULES_PATH = REPO / "state" / "rules.yaml"
SCHEMA_PATH = REPO / "schemas" / "agent-output.schema.yaml"
AGENTS_DIR = REPO / ".claude" / "agents"

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


def _agent_role_path(agent: str):
    return AGENTS_DIR / f"{agent}.md"


def _missing_agent_role_files(agents: set[str]) -> set[str]:
    """S1: агенты из `agents`, для которых нет файла роли
    .claude/agents/<agent>.md."""
    return {a for a in agents if not _agent_role_path(a).is_file()}


def _agents_with_unrecognized_tier_model(agents: set[str]) -> dict[str, object]:
    """S2: {agent: model} для агентов, чей frontmatter `model:` отсутствует
    (файла/поля нет — la._read_agent_frontmatter_model вернёт None) либо не
    входит в la.TIER_ORDER (та же ярусная матрица, что использует
    log_append._resolve_agent_tier)."""
    bad: dict[str, object] = {}
    for agent in agents:
        model = la._read_agent_frontmatter_model(agent)
        if model not in la.TIER_ORDER:
            bad[agent] = model
    return bad


def _dead_enum_agents(rules_agents: set[str], schema_enum: set[str]) -> set[str]:
    """N1(б): агенты enum, которых не диспатчит ни одно правило rules.yaml."""
    return schema_enum - rules_agents


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


# --- S1: dispatch-агент rules.yaml <-> файл роли .claude/agents/<agent>.md ---

def test_every_dispatch_agent_has_role_file():
    """S1: каждый dispatch-агент rules.yaml обязан иметь файл роли
    .claude/agents/<agent>.md — реестр агентов конвейера существует."""
    rules_agents = _rules_dispatch_agents()
    missing = _missing_agent_role_files(rules_agents)
    assert not missing, (
        "агенты dispatch: из state/rules.yaml не имеют файла роли "
        f".claude/agents/<agent>.md: {sorted(missing)}"
    )


def test_every_dispatch_agent_has_role_file_red_probe():
    """Красная проба S1: мутация ДАННЫХ (не файлов rules.yaml/.claude/agents/)
    — синтетический набор с несуществующим агентом обязан провалить
    _missing_agent_role_files."""
    fake_agents = {"test-runner", "nonexistent-agent-xyz"}
    missing = _missing_agent_role_files(fake_agents)
    assert missing == {"nonexistent-agent-xyz"}, (
        f"красная проба S1 не сработала как ожидалось: {sorted(missing)}"
    )


# --- S2: frontmatter model файла роли <-> ярусная матрица log_append.py ---

def test_every_dispatch_agent_has_recognized_tier_model():
    """S2: frontmatter `model:` каждого dispatch-агента (у которого файл
    роли реально существует — отсутствие файла уже отдельный failure mode
    теста S1 выше, не дублируем сообщение) обязан быть значением, которое
    распознаёт ярусная матрица log_append.py (la.TIER_ORDER)."""
    rules_agents = _rules_dispatch_agents()
    existing = {a for a in rules_agents if _agent_role_path(a).is_file()}
    bad = _agents_with_unrecognized_tier_model(existing)
    assert not bad, (
        "frontmatter model агентов dispatch: не распознаётся ярусной "
        f"матрицей log_append.py (ожидается одно из {sorted(la.TIER_ORDER)}): {bad}"
    )


def test_every_dispatch_agent_has_recognized_tier_model_red_probe_missing_file():
    """Красная проба S2 (аналогично S1): несуществующий агент — frontmatter
    model не читается (None), None не входит в la.TIER_ORDER."""
    bad = _agents_with_unrecognized_tier_model({"nonexistent-agent-xyz"})
    assert bad == {"nonexistent-agent-xyz": None}, (
        f"красная проба S2 (missing file) не сработала как ожидалось: {bad}"
    )


def test_every_dispatch_agent_has_recognized_tier_model_red_probe_bad_value(
    tmp_path, monkeypatch,
):
    """Красная проба S2, вторая форма: файл роли СУЩЕСТВУЕТ, но несёт
    нераспознаваемое значение model (напр. опечатка яруса) — отдельно от
    случая "файла вовсе нет" выше. Копия каталога в tmp_path — реальные
    .claude/agents/*.md не трогаются."""
    fake_dir = tmp_path / "agents"
    fake_dir.mkdir()
    (fake_dir / "weird-agent.md").write_text(
        "---\nname: weird-agent\nmodel: turbo\n---\n\n# weird-agent\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(la, "AGENTS_DIR", fake_dir, raising=True)
    bad = _agents_with_unrecognized_tier_model({"weird-agent"})
    assert bad == {"weird-agent": "turbo"}, (
        f"красная проба S2 (bad value) не сработала как ожидалось: {bad}"
    )


# --- N1: двунаправленность parity-теста ---

def test_rules_dispatch_agents_nonempty():
    """N1(а): защита от vacuous pass — если структура rules.yaml когда-либо
    изменится так, что `_rules_dispatch_agents()` молча вернёт пустое
    множество, все проверки "каждый агент X обязан ..." выше стали бы
    тривиально зелёными, ничего не проверяя."""
    assert _rules_dispatch_agents(), (
        "rules.yaml не дал ни одного dispatch-агента — дрейф структуры YAML "
        "(rules[].dispatch), парный тест выше рискует vacuous pass"
    )


def test_every_schema_enum_agent_is_dispatched_by_rules():
    """N1(б), обратная сверка к test_every_dispatch_agent_in_schema_enum:
    каждый агент enum agent-output обязан реально диспатчиться каким-то
    правилом rules.yaml — иначе это мёртвая запись enum (правило удалено
    или переименовано, схему не почистили)."""
    dead = _dead_enum_agents(_rules_dispatch_agents(), _schema_agent_enum())
    assert not dead, (
        "агенты enum schemas/agent-output.schema.yaml (agent) не "
        f"диспатчатся ни одним правилом state/rules.yaml: {sorted(dead)}"
    )


def test_every_schema_enum_agent_is_dispatched_by_rules_red_probe():
    """Красная проба N1(б): синтетические rules_agents/schema_enum
    (мутация данных) с мёртвой записью enum — реальные rules.yaml/схема не
    трогаются."""
    dead = _dead_enum_agents({"test-runner", "bug-reporter"},
                             {"test-runner", "ghost-agent"})
    assert dead == {"ghost-agent"}, (
        f"красная проба N1(б) не сработала как ожидалось: {sorted(dead)}"
    )
