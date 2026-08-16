"""Тесты scripts/mechanism_gate.py — осевой гейт D-0055 (твин OS-репо)."""
from __future__ import annotations

import pytest

import mechanism_gate as mg

MAP_SAMPLE = "## Ось 1 — Деплои\n## Ось 3 — Роли\n## Ось 6 — Внутренние оси\n"


def test_parse_axes_follows_the_map_not_a_constant():
    assert mg.parse_axes(MAP_SAMPLE) == [1, 3, 6]
    assert mg.parse_axes("") == []


def test_mechanism_paths_filters_ao3_prefixes_with_boundary():
    staged = ["CLAUDE.md", ".claude/agents/scout.md",
              ".claude/skills/qa-loop/SKILL.md", "schemas/agent-output.json",
              "state/rules.yaml", "scripts/log_append.py", "framework/conftest.py"]
    # 2026-07-31: log_append.py ВНУТРИ невода (журнальный гейт — механизм
    # по D-0065; до этого стоял здесь негативным примером — граница
    # сдвинута сознательно, находка critic при ревью AT-BUG-033).
    assert mg.mechanism_paths(staged) == [
        "CLAUDE.md", ".claude/agents/scout.md", ".claude/skills/qa-loop/SKILL.md",
        "schemas/agent-output.json", "state/rules.yaml", "scripts/log_append.py"]
    # F-D: файловые префиксы матчатся точно.
    assert mg.mechanism_paths(["CLAUDE.md.bak", "state/rules.yaml.orig"]) == []
    # D-0065 OS-репо: самозащита цепочки; прочие scripts/ вне (D-0055).
    assert mg.mechanism_paths(["scripts/mechanism_gate.py",
                               ".githooks/commit-msg"]) == [
        "scripts/mechanism_gate.py", ".githooks/commit-msg"]
    assert mg.mechanism_paths(["scripts/board_sync.py"]) == []
    # Граница невода вокруг журнального гейта: сам файл — механизм,
    # его тесты — нет.
    assert mg.mechanism_paths(["scripts/tests/test_log_append.py"]) == []
    assert mg.mechanism_paths(["scripts/log_append.py.bak"]) == []
    # 2026-08-09 (некрит-9, M1+M4): heartbeat_wrap решает, состоится ли
    # scheduled-проход — механизм; его тесты — вне невода (тот же образец,
    # что log_append.py выше).
    assert mg.mechanism_paths(["scripts/heartbeat_wrap.py"]) == ["scripts/heartbeat_wrap.py"]
    assert mg.mechanism_paths(["scripts/tests/test_heartbeat_wrap.py"]) == []
    # 2026-08-14 (spec-device-build-check.md v3, вердикт Q5): doctor —
    # preflight-гейт, тот же образец, что heartbeat_wrap выше.
    assert mg.mechanism_paths(["scripts/doctor.py"]) == ["scripts/doctor.py"]
    assert mg.mechanism_paths(["scripts/tests/test_doctor.py"]) == []
    # 2026-07-23: срез карты — вход гейта, тихая правка = обход осей.
    assert mg.mechanism_paths(["state/sibling-map.snapshot.md"]) == [
        "state/sibling-map.snapshot.md"]
    assert mg.mechanism_paths(["state/sibling-map.snapshot.md.bak"]) == []
    # 2026-08-15 (D-0099-порт): сама Lead-привязка — вход гейта (tier-
    # требование читает из неё ожидаемый ярус), тот же образец, что срез
    # карты выше.
    assert mg.mechanism_paths(["delegation.config.yaml"]) == [
        "delegation.config.yaml"]
    assert mg.mechanism_paths(["delegation.config.yaml.bak"]) == []
    # 2026-08-16 (spec-factory-window v6, К5г): сторож окна-фабрики —
    # тот же образец, что heartbeat_wrap/doctor выше.
    assert mg.mechanism_paths(["scripts/factory_watchdog.py"]) == [
        "scripts/factory_watchdog.py"]
    assert mg.mechanism_paths(["scripts/tests/test_factory_watchdog.py"]) == []


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


# ---------------------------------------------------------------------------
# SKIP_RE — якорь ^\s* + MULTILINE (порт штабного фикса fadb7c0 OS-репо,
# полигон Dog D-0093; решение Lead 2026-07-28: перенять). Без якоря
# .search() матчил инлайн-цитату синтаксиса отказа посреди прозы
# коммит-сообщения, глуша гейт целиком.
# ---------------------------------------------------------------------------

def test_skip_re_standalone_line_passes():
    # (а) легальная skip-строка отдельной строкой в начале блока → активна.
    msg = "feat: механизм X\n\nоси: не-механизм (причина)\n\nдоп. текст\n"
    assert mg.SKIP_RE.search(msg)


def test_skip_re_standalone_line_with_indent_passes():
    # (б) та же строка с отступом пробелами → активна (якорь ^\s*).
    msg = "feat: механизм X\n\n   оси: не-механизм (причина с отступом)\n"
    assert mg.SKIP_RE.search(msg)


def test_skip_re_inline_quote_mid_sentence_not_a_declaration():
    # (в) цитата ЧУЖОЙ skip-строки в середине предложения текста → НЕ
    # считается декларацией (иначе цитата обходила бы гейт).
    msg = ("feat: механизм X\n\nсм. чужую строку «оси: не-механизм (x)» "
           "из другого коммита\n")
    assert not mg.SKIP_RE.search(msg)
    code, reason = mg.decide(msg, ["CLAUDE.md"], MAP_SAMPLE)
    assert code == 1 and "Осевой блок" in reason


def test_skip_re_line_starting_with_quote_before_marker_not_a_declaration():
    # (г) граница: строка НАЧИНАЕТСЯ с цитатной кавычки/ёлочки перед
    # маркером — не декларация (перед «оси» стоит непробельный символ,
    # якорь ^\s* его не пропускает).
    msg_guillemet = "feat: механизм X\n\n«оси: не-механизм (пример)»\n"
    assert not mg.SKIP_RE.search(msg_guillemet)
    msg_straight = 'feat: механизм X\n\n"оси: не-механизм (пример)"\n'
    assert not mg.SKIP_RE.search(msg_straight)


def test_skip_re_first_line_no_leading_newline_matches():
    # skip-строка — самая первая строка сообщения целиком, без ведущего
    # \n: MULTILINE ^ матчит и позицию 0, не только позицию сразу после \n.
    msg = "оси: не-механизм (причина, без ведущего текста)\n\nдоп. текст\n"
    assert mg.SKIP_RE.search(msg)
    code, _ = mg.decide(msg, ["CLAUDE.md"], MAP_SAMPLE)
    assert code == 0


def test_skip_re_matches_on_crlf_message():
    msg = "feat: механизм X\r\n\r\nоси: не-механизм (причина)\r\n"
    assert mg.SKIP_RE.search(msg)


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


# ---------------------------------------------------------------------------
# resolve_lead_binding — D-0099-порт (2026-08-15): семейство Lead-привязки
# из delegation.config.yaml, fail-safe -> "fable" + WARN.
# ---------------------------------------------------------------------------

def _cfg(model: str, *, key: str = "subscription") -> str:
    return f"roles:\n  lead:\n    {key}:\n      model: {model}\n"


def test_resolve_lead_binding_none_and_empty_default_to_fable():
    assert mg.resolve_lead_binding(None) == "fable"
    assert mg.resolve_lead_binding("") == "fable"


def test_resolve_lead_binding_valid_opus_config_returns_family_not_model_id():
    # Р9: резолвер возвращает СЕМЕЙСТВО ("opus"), не литеральный model-id
    # ("claude-opus-5").
    assert mg.resolve_lead_binding(_cfg("claude-opus-5")) == "opus"


def test_resolve_lead_binding_api_key_fallback_when_no_subscription():
    assert mg.resolve_lead_binding(_cfg("claude-opus-5", key="api")) == "opus"


def test_resolve_lead_binding_broken_forms_fall_back_to_fable_with_warn(capsys):
    broken = [
        "not: relevant\n",                                  # roles отсутствует
        "roles: null\n",                                    # roles не словарь
        "roles:\n  lead: null\n",                            # roles.lead не словарь
        "- just\n- a\n- list\n",                             # верхний уровень не словарь
        "roles:\n  lead:\n    subscription:\n      model: \"\"\n",  # model пуст
        "roles:\n  lead:\n    subscription:\n      model: gpt-5\n",  # семейство не распознано
        "roles:\n  lead:\n    subscription:\n      model: claude-opus-sonnet-5\n",  # >=2 семейства
        "not valid yaml: [unclosed\n",                       # YAML не парсится
        # BOM-мусор: PyYAML сам съедает ОДИН ведущий U+FEFF как маркер
        # документа (эмпирически проверено — одиночный BOM ПАРСИТСЯ чисто
        # и НЕ входит в этот батарею фейлов), но ДВОЙНОЙ BOM (двойное
        # кодирование/повторный BOM при конкатенации файлов) оставляет
        # второй U+FEFF ЧАСТЬЮ ключа — "﻿roles" != "roles",
        # data.get("roles") промахивается -> ветка "roles отсутствует".
        "﻿﻿" + _cfg("claude-opus-5"),
    ]
    for text in broken:
        capsys.readouterr()  # сброс перед каждым кейсом
        assert mg.resolve_lead_binding(text) == "fable", text
        assert "WARN" in capsys.readouterr().err, text


def test_resolve_lead_binding_sanitary_floor_below_opus_falls_back(capsys):
    # Б1/2а: санитарный пол — привязка НИЖЕ opus (sonnet/haiku) не
    # поддерживается этим деплоем, дефолт fable + явный WARN.
    for model in ("claude-sonnet-5", "claude-haiku-4-5"):
        capsys.readouterr()
        assert mg.resolve_lead_binding(_cfg(model)) == "fable", model
        err = capsys.readouterr().err
        assert "WARN" in err and "opus" in err, model


def test_resolve_lead_binding_pyyaml_unavailable_falls_back(monkeypatch, capsys):
    # Р3: защищённый импорт yaml ВНУТРИ резолвера -- отсутствие PyYAML не
    # роняет вызывающий гейт (commit-msg хук).
    monkeypatch.setitem(__import__("sys").modules, "yaml", None)
    assert mg.resolve_lead_binding(_cfg("claude-opus-5")) == "fable"
    assert "WARN" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# decide_full(config_text=...) — tier-декларация против привязки opus
# (D-0099-порт), Р4 (неоднозначность), Р9 (вхождение семейства model-id),
# Р12 (skip не действует для staged-конфига).
# ---------------------------------------------------------------------------

OPUS_CFG = _cfg("claude-opus-5")


@pytest.mark.parametrize("tier_value,expect_pass", [
    ("opus", True),          # литеральное совпадение с привязкой
    ("fable", True),         # резерв — семейство строго выше opus
    ("sonnet", False),       # ниже привязки
    ("claude-opus-5", True),  # Р9: вхождение семейства «opus» по подстроке
])
def test_decide_full_tier_against_opus_binding(tier_value, expect_pass):
    msg = f"feat: X\n\n{AXES_OK}\ntier: {tier_value}"
    code, reason = mg.decide_full(msg, ["CLAUDE.md"], MAP_SAMPLE,
                                  config_text=OPUS_CFG)
    assert (code == 0) == expect_pass, reason


def test_decide_full_two_tier_lines_opus_plus_fable_both_legal_passes():
    msg = f"feat: X\n\n{AXES_OK}\ntier: opus\ntier: fable"
    code, _ = mg.decide_full(msg, ["CLAUDE.md"], MAP_SAMPLE, config_text=OPUS_CFG)
    assert code == 0


def test_decide_full_two_tier_lines_opus_plus_sonnet_any_below_fails():
    msg = f"feat: X\n\n{AXES_OK}\ntier: opus\ntier: sonnet"
    code, reason = mg.decide_full(msg, ["CLAUDE.md"], MAP_SAMPLE, config_text=OPUS_CFG)
    assert code == 1 and "sonnet" in reason


def test_decide_full_single_line_ambiguous_declaration_rejected():
    # Р4 (буквальный пример спеки): ≥2 РАЗНЫХ семейства в ОДНОЙ строке
    # tier: -> отказ «декларация неоднозначна», НЕ первое совпадение
    # (которое молча приняло бы «sonnet» как «fable»/«opus» и прошло бы).
    msg = f"feat: X\n\n{AXES_OK}\ntier: sonnet (fallback от opus)"
    code, reason = mg.decide_full(msg, ["CLAUDE.md"], MAP_SAMPLE, config_text=OPUS_CFG)
    assert code == 1 and "неоднозначна" in reason


def test_decide_full_ambiguous_declaration_rejected_even_when_both_families_legal():
    # Границf: даже если ОБА семейства в строке были бы легальны по
    # отдельности (opus/fable оба >= привязки opus), неоднозначность
    # всё равно отказ -- проверка "≥2 семейства" безусловна, не судит
    # по итоговому вердикту отдельных семейств (Р4: "не первое-совпадение").
    msg = f"feat: X\n\n{AXES_OK}\ntier: opus (aka fable reserve)"
    code, reason = mg.decide_full(msg, ["CLAUDE.md"], MAP_SAMPLE, config_text=OPUS_CFG)
    assert code == 1 and "неоднозначна" in reason


def test_decide_full_config_staged_blocks_skip_line():
    # Р12/М2.7: staged-пути несут delegation.config.yaml -- skip-строка
    # «оси: не-механизм» НЕ действует, осевой блок обязателен безусловно.
    msg = "feat: перепривязка\n\nоси: не-механизм (только конфиг)"
    code, reason = mg.decide_full(msg, ["delegation.config.yaml"], MAP_SAMPLE,
                                  config_text=OPUS_CFG)
    assert code == 1
    # Без конфига в staged -- то же сообщение проходит как раньше.
    code, _ = mg.decide_full(msg, ["CLAUDE.md"], MAP_SAMPLE, config_text=OPUS_CFG)
    assert code == 0


def test_decide_full_config_staged_requires_tier_line_unconditionally():
    # Осевой блок присутствует (не полагается на skip), но skip-строка
    # ТОЖЕ есть — Р12 требует tier-строку всё равно, staged-конфиг
    # снимает льготу skip целиком, не только для осевого блока.
    msg = f"feat: X\n\n{AXES_OK}\nоси: не-механизм (мимо кассы)"
    code, reason = mg.decide_full(msg, ["delegation.config.yaml"], MAP_SAMPLE,
                                  config_text=OPUS_CFG)
    assert code == 1 and "Нет строки" in reason


# ---------------------------------------------------------------------------
# _head_config_text — Б5 (HEAD-источник для commit-msg-гейта), Р11 (выбор
# builder'а: монкипатчимая функция вместо git-фикстуры).
# ---------------------------------------------------------------------------

def test_head_config_text_calls_git_show_head(monkeypatch):
    calls = []

    def fake_git(*args):
        calls.append(args)
        return OPUS_CFG

    monkeypatch.setattr(mg, "_git", fake_git)
    assert mg._head_config_text() == OPUS_CFG
    assert calls == [("show", f"HEAD:{mg.CONFIG_FILENAME}")]


def test_head_config_text_missing_file_or_head_returns_none(monkeypatch):
    # _git() глотает ошибки (capture_output) и возвращает "" и при
    # отсутствии файла в HEAD, и при отсутствии HEAD вовсе (первый коммит).
    monkeypatch.setattr(mg, "_git", lambda *a: "")
    assert mg._head_config_text() is None


def test_decide_full_same_commit_config_downgrade_does_not_affect_gate():
    # Б5 (класс snapshot_shrink_guard, второй экземпляр): decide_full
    # принимает ГОТОВЫЙ HEAD-текст параметром — не читает staged/рабочее
    # дерево сам, поэтому same-commit правка roles.lead физически не может
    # повлиять на ТЕКУЩИЙ вызов (main() — единственное место, решающее,
    # какой текст передать, и оно берёт _head_config_text(), см. тесты
    # выше). Здесь проверяется семантика самого decide_full: сообщение,
    # которое было бы легально ПРИ НОВОЙ (opus) привязке, отклоняется,
    # если фактически передана СТАРАЯ (fable) HEAD-привязка.
    old_config = _cfg("claude-fable-5")
    msg_fable = f"feat: X\n\n{AXES_OK}\ntier: fable"
    code, _ = mg.decide_full(msg_fable, ["CLAUDE.md"], MAP_SAMPLE, config_text=old_config)
    assert code == 0
    msg_opus = f"feat: X\n\n{AXES_OK}\ntier: opus"
    code, reason = mg.decide_full(msg_opus, ["CLAUDE.md"], MAP_SAMPLE, config_text=old_config)
    assert code == 1 and "opus" in reason
