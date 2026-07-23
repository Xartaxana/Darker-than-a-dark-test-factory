"""Тесты scripts/mechanism_gate.py — осевой гейт D-0055 (твин OS-репо)."""
from __future__ import annotations

import mechanism_gate as mg

MAP_SAMPLE = "## Ось 1 — Деплои\n## Ось 3 — Роли\n## Ось 6 — Внутренние оси\n"


def test_parse_axes_follows_the_map_not_a_constant():
    assert mg.parse_axes(MAP_SAMPLE) == [1, 3, 6]
    assert mg.parse_axes("") == []


def test_mechanism_paths_filters_ao3_prefixes_with_boundary():
    staged = ["CLAUDE.md", ".claude/agents/scout.md",
              ".claude/skills/qa-loop/SKILL.md", "schemas/agent-output.json",
              "state/rules.yaml", "scripts/log_append.py", "framework/conftest.py"]
    assert mg.mechanism_paths(staged) == [
        "CLAUDE.md", ".claude/agents/scout.md", ".claude/skills/qa-loop/SKILL.md",
        "schemas/agent-output.json", "state/rules.yaml"]
    # F-D: файловые префиксы матчатся точно.
    assert mg.mechanism_paths(["CLAUDE.md.bak", "state/rules.yaml.orig"]) == []
    # D-0065 OS-репо: самозащита цепочки; прочие scripts/ вне (D-0055).
    assert mg.mechanism_paths(["scripts/mechanism_gate.py",
                               ".githooks/commit-msg"]) == [
        "scripts/mechanism_gate.py", ".githooks/commit-msg"]
    assert mg.mechanism_paths(["scripts/board_sync.py"]) == []
    # 2026-07-23: срез карты — вход гейта, тихая правка = обход осей.
    assert mg.mechanism_paths(["state/sibling-map.snapshot.md"]) == [
        "state/sibling-map.snapshot.md"]
    assert mg.mechanism_paths(["state/sibling-map.snapshot.md.bak"]) == []


def test_decide_skip_and_block_only_from_commit_message():
    # F-A: в твине нет DECISIONS_FULL — и блок, и отказ только из сообщения.
    code, _ = mg.decide("feat: X\n\nось 1: покрыта\nось 3: н-п (ролей не трогает)\n"
                        "ось 6: покрыта — schemas тем же коммитом",
                        ["CLAUDE.md"], MAP_SAMPLE)
    assert code == 0
    code, reason = mg.decide("feat: X", ["CLAUDE.md"], MAP_SAMPLE)
    assert code == 1 and "1, 3, 6" in reason
    code, _ = mg.decide("docs: опечатка\n\nоси: не-механизм (опечатка)",
                        ["CLAUDE.md"], MAP_SAMPLE)
    assert code == 0


def test_decide_merge_and_non_mechanism_pass_and_fail_closed():
    code, _ = mg.decide("Merge branch 'x'", ["CLAUDE.md"], MAP_SAMPLE, merging=True)
    assert code == 0
    code, _ = mg.decide("chore: тесты", ["framework/conftest.py"], MAP_SAMPLE)
    assert code == 0
    code, reason = mg.decide("feat: X", ["CLAUDE.md"], None)
    assert code == 1 and "fail-closed" in reason


def test_prose_is_not_an_answer():
    assert mg.find_missing("все оси покрыты", [1, 3]) == [1, 3]


AXES_OK = "ось 1: покрыта\nось 3: н-п (роли не тронуты)\nось 6: покрыта"


def test_tier_line_required_and_family_match():
    # Осевой блок пройден, tier-строки нет — отказ с инструкцией очереди.
    code, reason = mg.decide_full(f"feat: X\n\n{AXES_OK}",
                                  ["CLAUDE.md"], MAP_SAMPLE)
    assert code == 1 and "Нет строки" in reason
    # Точная привязка и вхождение семейства (model id) — обе проходят.
    for tier in ("fable", "claude-fable-5"):
        code, _ = mg.decide_full(f"feat: X\n\n{AXES_OK}\ntier: {tier}",
                                 ["CLAUDE.md"], MAP_SAMPLE)
        assert code == 0, tier
    # Ярус ниже привязки — отказ.
    code, reason = mg.decide_full(f"feat: X\n\n{AXES_OK}\ntier: sonnet",
                                  ["CLAUDE.md"], MAP_SAMPLE)
    assert code == 1 and "sonnet" in reason


def test_two_tier_lines_any_below_binding_fails():
    """Штабной фикс t-278 (OS-репо 07-22): .search() матчил только первую
    tier-строку — цитата с высоким ярусом маскировала настоящую низкую
    декларацию. findall: отказ, если ХОТЬ ОДНА строка ниже привязки."""
    # Маскировка: цитированная fable-строка ПЕРВОЙ, реальная sonnet — ниже.
    msg = f"feat: X\n\n{AXES_OK}\ntier: fable\n(цитата штаба)\ntier: sonnet"
    code, reason = mg.decide_full(msg, ["CLAUDE.md"], MAP_SAMPLE)
    assert code == 1 and "sonnet" in reason
    # Обратный порядок — тот же отказ (порядок строк не играет).
    msg = f"feat: X\n\n{AXES_OK}\ntier: sonnet\ntier: fable"
    code, reason = mg.decide_full(msg, ["CLAUDE.md"], MAP_SAMPLE)
    assert code == 1
    # Две легальные строки (цитата fable + своя fable) — проходят.
    msg = f"feat: X\n\n{AXES_OK}\ntier: fable\ntier: claude-fable-5"
    assert mg.decide_full(msg, ["CLAUDE.md"], MAP_SAMPLE) == (0, "")
    # Skip-ветка и merge tier-строку не требуют (невод исключений прежний).
    code, _ = mg.decide_full("docs: опечатка\n\nоси: не-механизм (опечатка)",
                             ["CLAUDE.md"], MAP_SAMPLE)
    assert code == 0
    code, _ = mg.decide_full("Merge branch 'x'", ["CLAUDE.md"], MAP_SAMPLE,
                             merging=True)
    assert code == 0


# ---------------------------------------------------------------------------
# resolve_map_source — тройная цепочка источника карты (2026-07-23)
# ---------------------------------------------------------------------------

def _chain(monkeypatch, tmp_path, env=None, live=None, snapshot=None):
    """Собирает изолированную цепочку: env-значение (или его отсутствие),
    подменённые пути живой карты и среза (существуют, только если задан
    текст)."""
    live_path = tmp_path / "live" / "SIBLING_MAP.md"
    snap_path = tmp_path / "snap" / "sibling-map.snapshot.md"
    if live is not None:
        live_path.parent.mkdir(parents=True, exist_ok=True)
        live_path.write_text(live, encoding="utf-8")
    if snapshot is not None:
        snap_path.parent.mkdir(parents=True, exist_ok=True)
        snap_path.write_text(snapshot, encoding="utf-8")
    monkeypatch.setattr(mg, "MAP_PATH", live_path)
    monkeypatch.setattr(mg, "MAP_SNAPSHOT_PATH", snap_path)
    if env is None:
        monkeypatch.delenv(mg.MAP_ENV_VAR, raising=False)
    else:
        monkeypatch.setenv(mg.MAP_ENV_VAR, env)


def test_resolve_env_override_wins_over_live_and_snapshot(monkeypatch, tmp_path):
    env_map = tmp_path / "env-map.md"
    env_map.write_text("## Ось 7 — Env\n", encoding="utf-8")
    _chain(monkeypatch, tmp_path, env=str(env_map),
           live="## Ось 1 — Live\n", snapshot="## Ось 2 — Snap\n")
    text, label, used_snapshot = mg.resolve_map_source()
    assert mg.parse_axes(text) == [7]
    assert mg.MAP_ENV_VAR in label
    assert used_snapshot is False


def test_resolve_env_set_but_unreadable_fails_closed_no_silent_fallback(
        monkeypatch, tmp_path):
    # ГРАНИЦА: env выставлен, файла нет — отказ, хотя ниже по цепочке
    # лежат читаемые живая карта И срез (тихий откат запрещён, F-30).
    _chain(monkeypatch, tmp_path, env=str(tmp_path / "нет-такого.md"),
           live="## Ось 1 — Live\n", snapshot="## Ось 2 — Snap\n")
    text, label, used_snapshot = mg.resolve_map_source()
    assert text is None
    assert "не читается" in label
    assert used_snapshot is False
    code, reason = mg.decide("feat: X", ["CLAUDE.md"], text, map_label=label)
    assert code == 1 and "fail-closed" in reason and mg.MAP_ENV_VAR in reason


def test_resolve_live_map_wins_over_snapshot(monkeypatch, tmp_path):
    _chain(monkeypatch, tmp_path,
           live="## Ось 1 — Live\n", snapshot="## Ось 2 — Snap\n")
    text, label, used_snapshot = mg.resolve_map_source()
    assert mg.parse_axes(text) == [1]
    assert used_snapshot is False


def test_resolve_snapshot_fallback_flagged(monkeypatch, tmp_path):
    _chain(monkeypatch, tmp_path, snapshot="## Ось 2 — Snap\n")
    text, label, used_snapshot = mg.resolve_map_source()
    assert mg.parse_axes(text) == [2]
    assert used_snapshot is True
    assert "срез" in label


def test_resolve_nothing_available_fails_closed(monkeypatch, tmp_path):
    _chain(monkeypatch, tmp_path)
    text, label, used_snapshot = mg.resolve_map_source()
    assert text is None and used_snapshot is False
    code, reason = mg.decide("feat: X", ["CLAUDE.md"], text, map_label=label)
    assert code == 1 and "fail-closed" in reason


def test_committed_snapshot_parses_contiguous_axes():
    """Анти-дрейф: реальный закоммиченный срез обязан парситься тем же
    regex'ом, что живая карта, — оси непрерывны с 1, не меньше девяти
    (срез 2026-07-23)."""
    text = mg.MAP_SNAPSHOT_PATH.read_text(encoding="utf-8")
    axes = mg.parse_axes(text)
    assert len(axes) >= 9
    assert axes == list(range(1, len(axes) + 1))


# ---------------------------------------------------------------------------
# snapshot_shrink_guard — same-commit-ужатие среза (блокер 1 вердикта critic)
# ---------------------------------------------------------------------------

def test_shrink_guard_removed_axis_without_justification_fails():
    code, reason = mg.snapshot_shrink_guard(
        "feat: X\n\nось 1: покрыта\ntier: fable",
        head_axes=[1, 2, 3], staged_axes=[1, 2])
    assert code == 1 and "3" in reason and "удалена" in reason


def test_shrink_guard_removed_axis_with_explicit_line_passes():
    code, _ = mg.snapshot_shrink_guard(
        "map: слияние осей\n\nось 3: удалена (слита с осью 1 в живой карте)",
        head_axes=[1, 2, 3], staged_axes=[1, 2])
    assert code == 0
    # Обоснование ДРУГОЙ оси не покрывает удалённую (номер несущий).
    code, reason = mg.snapshot_shrink_guard(
        "map: X\n\nось 2: удалена (причина)",
        head_axes=[1, 2, 3], staged_axes=[1, 3])
    assert code == 0  # удалена ось 2, строка есть
    code, reason = mg.snapshot_shrink_guard(
        "map: X\n\nось 2: удалена (причина)",
        head_axes=[1, 2, 3], staged_axes=[2, 3])
    assert code == 1 and "1" in reason  # удалена ось 1, строка про 2


def test_shrink_guard_growth_and_creation_do_not_trigger():
    # Рост осей — не ужатие.
    assert mg.snapshot_shrink_guard("map: X", [1, 2], [1, 2, 3]) == (0, "")
    # Срез только создаётся (HEAD-версии нет) — не ужатие.
    assert mg.snapshot_shrink_guard("map: X", [], [1, 2]) == (0, "")
    # Без изменений.
    assert mg.snapshot_shrink_guard("map: X", [1, 2], [1, 2]) == (0, "")
