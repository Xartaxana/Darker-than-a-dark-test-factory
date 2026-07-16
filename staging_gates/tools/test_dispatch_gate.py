"""Юнит-смоки tools/dispatch_gate.py (t-152, policy-as-code «ход вниз»).
Прямые вызовы decide() для всех веток + echo-JSON смок подпроцессом
(спека явно требует "юнит-тесты всех веток").

Штабной вариант: dispatch_gate.py в tools/ этого репо -- БЕЗ изменений
относительно кита (см. exam_fullgates_kit/staging_hq/README.md, п.
"dispatch_gate.py -- БЕЗ изменений"), поэтому тест-кейсы перенесены
как есть из exam_fullgates_kit/tools/test_dispatch_gate.py (t-159)."""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dispatch_gate  # noqa: E402

SCRIPT = Path(__file__).resolve().parent / "dispatch_gate.py"


def _run_hook(payload: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _builder_payload(prompt: str, description=None) -> dict:
    tool_input = {"subagent_type": "builder", "prompt": prompt}
    if description is not None:
        tool_input["description"] = description
    return {"tool_name": "Task", "tool_input": tool_input}


# ---------------------------------------------------------------------
# Не Task/Agent -- всегда пропуск.
# ---------------------------------------------------------------------


def test_non_task_tool_passes():
    exit_code, message = dispatch_gate.decide({"tool_name": "Bash", "tool_input": {}})
    assert exit_code == 0
    assert message == ""


def test_missing_tool_input_does_not_crash():
    exit_code, message = dispatch_gate.decide({"tool_name": "Task"})
    assert exit_code == 0


# ---------------------------------------------------------------------
# Проверка 1: DoD-маркеры для builder'а.
# ---------------------------------------------------------------------


def test_builder_without_dod_markers_blocks():
    exit_code, message = dispatch_gate.decide(
        _builder_payload("Просто поправь опечатку в файле x.py.", description="sonnet: fix typo")
    )
    assert exit_code == 2
    assert "без DoD" in message
    assert "правило 11" in message


def test_builder_with_dod_literal_passes_check1():
    # "Почини" (не "поправь") -- намеренно избегаем подстроки "правь"
    # из WRITE_INDICATORS_RE, см. test_write_indicator_substring_
    # collision_in_pravj_is_a_known_finding ниже про эту коллизию.
    exit_code, message = dispatch_gate.decide(
        _builder_payload("Почини опечатку. DoD: тест зелёный.", description="sonnet: fix")
    )
    assert exit_code == 0


def test_builder_with_criteria_priyomki_passes_check1():
    exit_code, message = dispatch_gate.decide(
        _builder_payload(
            "Почини опечатку. Критерии приёмки: тест проходит.", description="sonnet: fix"
        )
    )
    assert exit_code == 0


def test_builder_with_criteria_priyomki_genitive_singular_passes_check1():
    exit_code, message = dispatch_gate.decide(
        _builder_payload(
            "Нет критерия приёмки указано явно тут.", description="sonnet: fix"
        )
    )
    assert exit_code == 0


def test_builder_with_witness_passes_check1():
    exit_code, message = dispatch_gate.decide(
        _builder_payload("Почини опечатку, приложи witness.", description="sonnet: fix")
    )
    assert exit_code == 0


def test_builder_with_verification_run_passes_check1():
    exit_code, message = dispatch_gate.decide(
        _builder_payload(
            "Почини опечатку и прогони проверочный прогон.", description="sonnet: fix"
        )
    )
    assert exit_code == 0
    # /проверочн\w+ прогон/i требует буквально слово "прогон" СРАЗУ
    # после "проверочн\w+ " -- "проверочную команду" НЕ матчится (нет
    # слова "прогон"), это отдельная (валидная) ветка -- проверяем
    # блок, а не пропуск, чтобы не выдать чужое поведение за DoD-маркер.
    exit_code2, message2 = dispatch_gate.decide(
        _builder_payload(
            "Почини опечатку и прогони проверочную команду.", description="sonnet: fix"
        )
    )
    assert exit_code2 == 2
    assert "без DoD" in message2

    exit_code3, _ = dispatch_gate.decide(
        _builder_payload(
            "Почини опечатку и прогони проверочную прогон.", description="sonnet: fix"
        )
    )
    assert exit_code3 == 0


def test_pravj_word_boundary_does_not_match_poprav_or_isprav():
    """НЕГАТИВНЫЙ ЛОК (решение координатора, t-152 retry): исходная
    находка (WRITE_INDICATORS_RE без \\b матчил "правь" ПОДСТРОКОЙ
    внутри "поправь"/"исправь") пофикшена \\b-границами -- "поправь"
    и "исправь" (обычные синонимы "почини", не сигнал владения
    путями) БОЛЬШЕ НЕ триггерят write-признак/требование манифеста.
    До фикса этот же промпт давал exit_code=2, "манифеста" in message
    (см. git-историю этого теста)."""
    exit_code, message = dispatch_gate.decide(
        _builder_payload(
            "DoD: тест зелёный. Пожалуйста, поправь опечатку в файле x.py.",
            description="sonnet: fix typo",
        )
    )
    assert exit_code == 0

    exit_code2, message2 = dispatch_gate.decide(
        _builder_payload(
            "DoD: тест зелёный. Пожалуйста, исправь опечатку в файле x.py.",
            description="sonnet: fix typo",
        )
    )
    assert exit_code2 == 0


def test_pravj_word_boundary_still_matches_standalone_word():
    # "Правь" как отдельное слово-императив (после пробела/начала
    # строки) -- ДОЛЖЕН по-прежнему триггерить write-признак; \b не
    # выключил проверку целиком, только убрал ложные подстроки.
    exit_code, message = dispatch_gate.decide(
        _builder_payload(
            "DoD: тест зелёный. Правь файл x.py по спеке.",
            description="sonnet: fix",
        )
    )
    assert exit_code == 2
    assert "манифеста" in message


def test_dod_marker_case_insensitive():
    exit_code, _ = dispatch_gate.decide(
        _builder_payload("правка. dod: тест зелёный.", description="sonnet: x")
    )
    assert exit_code == 0


# ---------------------------------------------------------------------
# Проверка 2: манифест на пишущем builder-диспатче.
# ---------------------------------------------------------------------


def test_builder_readonly_no_write_indicators_skips_check2():
    # DoD есть, признаков записи нет -- манифест не требуется.
    exit_code, message = dispatch_gate.decide(
        _builder_payload(
            "Прочитай файл x.py и скажи, что там. DoD: явный ответ да/нет.",
            description="sonnet: read",
        )
    )
    assert exit_code == 0


def test_builder_write_indicator_without_manifest_blocks():
    exit_code, message = dispatch_gate.decide(
        _builder_payload(
            "DoD: тест зелёный. Правь файл x.py по спеке.", description="sonnet: fix"
        )
    )
    assert exit_code == 2
    assert "манифеста" in message
    assert "D-0073" in message


def test_builder_write_indicator_with_full_manifest_passes():
    prompt = (
        "DoD: тест зелёный, witness приложен. Создай файл x.py. "
        "МАНИФЕСТ: дано — репо целиком; owns — tools/x.py."
    )
    exit_code, message = dispatch_gate.decide(
        _builder_payload(prompt, description="sonnet: write x")
    )
    assert exit_code == 0


def test_builder_write_indicator_with_only_owns_blocks():
    # "owns" сам по себе -- write-признак И один из двух манифест-
    # маркеров, но "дано"/given отсутствует -- манифест НЕПОЛОН.
    prompt = "DoD: witness есть. owns: tools/x.py. Измени файл x.py."
    exit_code, message = dispatch_gate.decide(
        _builder_payload(prompt, description="sonnet: write x")
    )
    assert exit_code == 2
    assert "манифеста" in message


def test_builder_write_indicator_with_only_given_blocks():
    prompt = "DoD: witness есть. Given: репо целиком. Создай файл x.py."
    exit_code, message = dispatch_gate.decide(
        _builder_payload(prompt, description="sonnet: write x")
    )
    assert exit_code == 2
    assert "манифеста" in message


def test_builder_dano_and_given_english_variant_recognized():
    prompt = (
        "DoD: witness есть. Given: репо целиком. owns: tools/x.py. Создай файл x.py."
    )
    exit_code, _ = dispatch_gate.decide(_builder_payload(prompt, description="sonnet: write x"))
    assert exit_code == 0


# ---------------------------------------------------------------------
# Проверка 3: лейбл description начинается с модели воркера.
# ---------------------------------------------------------------------


def test_missing_description_skips_check3():
    # DoD есть, признаков записи нет -- description вообще не передан.
    exit_code, message = dispatch_gate.decide(
        _builder_payload("Прочитай файл. DoD: явный ответ.")
    )
    assert exit_code == 0
    assert message == ""


def test_description_without_model_prefix_blocks():
    exit_code, message = dispatch_gate.decide(
        _builder_payload("Прочитай файл. DoD: явный ответ.", description="fix the bug")
    )
    assert exit_code == 2
    assert "модели воркера" in message
    assert "правило 7" in message


def test_description_with_model_prefix_variants_pass():
    for prefix in ["sonnet: ", "sonnet-", "sonnet ", "haiku: ", "opus: ", "fable: ", "claude: "]:
        exit_code, message = dispatch_gate.decide(
            _builder_payload(
                "Прочитай файл. DoD: явный ответ.", description=f"{prefix}делает работу"
            )
        )
        assert exit_code == 0, f"prefix {prefix!r} should pass, got {message!r}"


def test_description_model_prefix_case_insensitive():
    exit_code, _ = dispatch_gate.decide(
        _builder_payload("Прочитай файл. DoD: явный ответ.", description="Sonnet: делает работу")
    )
    assert exit_code == 0


def test_description_check_applies_to_critic():
    payload = {
        "tool_name": "Task",
        "tool_input": {"subagent_type": "critic", "prompt": "Ревью диффа.", "description": "review diff"},
    }
    exit_code, message = dispatch_gate.decide(payload)
    assert exit_code == 2
    assert "модели воркера" in message


def test_description_check_applies_to_scout():
    payload = {
        "tool_name": "Task",
        "tool_input": {"subagent_type": "scout", "prompt": "Найди файл.", "description": "find file"},
    }
    exit_code, message = dispatch_gate.decide(payload)
    assert exit_code == 2
    assert "модели воркера" in message


def test_description_check_passes_for_critic_with_model_label():
    payload = {
        "tool_name": "Task",
        "tool_input": {
            "subagent_type": "critic",
            "prompt": "Ревью диффа.",
            "description": "opus: review diff",
        },
    }
    exit_code, message = dispatch_gate.decide(payload)
    assert exit_code == 0


# ---------------------------------------------------------------------
# Пункт 4: critic/scout -- проверки 1 и 2 НЕ применяются.
# ---------------------------------------------------------------------


def test_critic_without_dod_markers_not_blocked_by_check1():
    payload = {
        "tool_name": "Task",
        "tool_input": {
            "subagent_type": "critic",
            "prompt": "Ревью диффа, без единого DoD-слова тут.",
            "description": "opus: review",
        },
    }
    exit_code, message = dispatch_gate.decide(payload)
    assert exit_code == 0


def test_scout_write_indicator_without_manifest_not_blocked_by_check2():
    payload = {
        "tool_name": "Task",
        "tool_input": {
            "subagent_type": "scout",
            "prompt": "Правь файл и создай файл заметок (это НЕ builder, проверка 2 не применяется).",
            "description": "haiku: scout",
        },
    }
    exit_code, message = dispatch_gate.decide(payload)
    assert exit_code == 0


# ---------------------------------------------------------------------
# Приоритет 1 -> 2 -> 3 при нескольких одновременных нарушениях.
# ---------------------------------------------------------------------


def test_priority_dod_wins_over_label():
    # Нет DoD И плохой лейбл одновременно -- сообщение про DoD (check 1).
    exit_code, message = dispatch_gate.decide(
        _builder_payload("Правь файл x.py.", description="fix it now")
    )
    assert exit_code == 2
    assert "без DoD" in message


def test_priority_manifest_wins_over_label():
    prompt = "DoD: witness есть. Правь файл x.py."
    exit_code, message = dispatch_gate.decide(_builder_payload(prompt, description="fix it now"))
    assert exit_code == 2
    assert "манифеста" in message


# ---------------------------------------------------------------------
# echo-JSON смок подпроцессом.
# ---------------------------------------------------------------------


def test_echo_json_blocks_builder_without_dod():
    result = _run_hook(_builder_payload("Просто поправь.", description="sonnet: fix"))
    assert result.returncode == 2
    assert "без DoD" in result.stderr


def test_echo_json_passes_builder_with_dod():
    result = _run_hook(
        _builder_payload("Почини. DoD: тест зелёный.", description="sonnet: fix")
    )
    assert result.returncode == 0
    assert result.stderr == ""


def test_echo_json_blocks_missing_manifest():
    result = _run_hook(
        _builder_payload("DoD: тест зелёный. Правь файл x.py.", description="sonnet: fix")
    )
    assert result.returncode == 2
    assert "манифеста" in result.stderr


def test_echo_json_blocks_bad_label():
    result = _run_hook(
        _builder_payload("Прочитай файл. DoD: ответ.", description="fix the bug")
    )
    assert result.returncode == 2
    assert "модели воркера" in result.stderr


def test_echo_json_malformed_json_fails_open():
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input="{not valid json",
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0
    assert result.stderr == ""


# ---------------------------------------------------------------------
# t-159 (очередь v5 п.3): кодировка stdin -- кириллические маркеры
# («Дано:», «критерии приёмки») обязаны распознаваться ДВУМЯ формами
# передачи -- ASCII-safe \uXXXX-эскейпы (json.dumps default,
# ensure_ascii=True) И сырые UTF-8 байты (ensure_ascii=False, без
# text=True/encoding на subprocess -- ровно то, как харнесс реально
# кормит stdin дочернего процесса). До фикса (sys.stdin.read() без
# явного UTF-8) форма (2) давала mojibake и ложный блок манифеста
# (cp1251 -- платформенная кодировка этой машины) -- см. докстринг
# dispatch_gate.py за эмпирику воспроизведения.
# ---------------------------------------------------------------------

_CYRILLIC_MANIFEST_PAYLOAD = {
    "tool_name": "Task",
    "tool_input": {
        "subagent_type": "builder",
        "prompt": (
            "DoD: критерии приёмки — тест зелёный, witness приложен. "
            "Дано: репо целиком. owns: tools/x.py. Правь файл x.py по спеке."
        ),
        "description": "sonnet: fix",
    },
}


def test_cyrillic_markers_recognized_via_ascii_safe_json_escapes():
    # ensure_ascii=True (json.dumps default) -- \uXXXX-эскейпы, форма,
    # которая "случайно работала" бы и ДО фикса (чистый ASCII на
    # проводе, платформенная кодировка stdin не участвует).
    raw = json.dumps(_CYRILLIC_MANIFEST_PAYLOAD, ensure_ascii=True).encode("ascii")
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=raw,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")


def test_cyrillic_markers_recognized_via_raw_utf8_bytes():
    # ensure_ascii=False + сырые UTF-8-байты БЕЗ text=True/encoding на
    # subprocess -- эта форма ловит регресс: ДО фикса давала
    # exit_code=2 (mojibake на маркерах "Дано:"/"owns" под cp1251).
    raw = json.dumps(_CYRILLIC_MANIFEST_PAYLOAD, ensure_ascii=False).encode("utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=raw,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
