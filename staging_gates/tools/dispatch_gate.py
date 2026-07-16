"""dispatch_gate.py (t-152, policy-as-code «ход вниз») -- PreToolUse-хук
Claude Code на Task/Agent-тул, проверяющий ФОРМУ диспатча ДО отправки
(D-0054/D-0073/правило 7 CLAUDE.md кита): DoD-маркеры в промпте
builder'а, манифест-маркеры на пишущем диспатче, лейбл description
начинается с модели воркера. Механизация правила 11 CLAUDE.md
(«воркер вернёт вопросами» -> «диспатч не уйдёт вовсе», слово
оператора 07-16, docs/tasks/2026-07-16_policy-as-code-design.md
п.1 «ход ВНИЗ»).

КОНТРАКТ PreToolUse -- та же эмпирика, что в tools/critic_gate.py
этого кита (payload["tool_name"] in {"Task","Agent"} для вызова
субагента, tool_input.subagent_type, payload["cwd"], exit 0 без
вывода -- разрешить, exit 2 + stderr -- заблокировать). ДОПОЛНЕНО
СОБСТВЕННОЙ эмпирикой t-150 живых смоков (тот же кит,
scratchpad/t150_dod_smoke/smoke_builder4_transcript.jsonl): реальный
tool_input вызова Agent содержал поля {"description": str,
"subagent_type": str, "prompt": str, "run_in_background": bool} --
т.е. tool_input.description и tool_input.prompt -- РЕАЛЬНЫЕ,
подтверждённые живым payload'ом поля, не гипотеза. Если поле
description ОТСУТСТВУЕТ в tool_input -- проверка 3 (лейбл)
ПРОПУСКАЕТСЯ (не блокирует) -- задокументированный факт, спека т-152
прямо это разрешает («Если поля description в payload нет — пропуск,
задокументируй факт»).

ЭМПИРИКА ПОРЯДКА НЕСКОЛЬКИХ ХУКОВ НА ОДНОМ MATCHER (спека т-152 п.6
требует явно; смок -- отдельный probe в
scratchpad/t152_hook_order_probe/, НЕ в этом ките, дешёвый
диагностический эксперимент с двумя фиктивными хуками на
matcher="Bash"): несколько command-хуков под ОДНИМ matcher-блоком
PreToolUse ВСЕ выполняются, НЕЗАВИСИМО от exit_code друг друга --
exit 2 ПЕРВОГО хука НЕ отменяет запуск ВТОРОГО того же события
(зафиксировано: probe_a.py exit 2 + probe_b.py exit 0 на одном
Bash-вызове -- ОБА получили пару hook_started/hook_response в
transcript, ОБА дописали свою строку в лог; итоговая блокировка
тула -- ОБЪЕДИНЕНИЕ: любой exit 2 в массиве блокирует, но это НЕ
short-circuit цепочка).

ПОСЛЕДСТВИЕ ДЛЯ ЭТОГО КИТА (НАХОДКА, не решается этим файлом и вне
объявленного scope т-152 -- вынесена в отчёт координатору): порядок
регистрации (dispatch_gate ПЕРЕД critic_gate в settings.json, как
требует спека п.6) НЕ даёт защитный short-circuit. Если dispatch_gate
блокирует диспатч критика (например, из-за лейбла без модели),
critic_gate.py ВСЁ РАВНО выполнится на том же событии и, если это
первый вызов критика в сессии/каталоге, СПИШЕТ его "один вызов на
сессию" (создаст .claude/critic_used + critic_snapshot.json), хотя
сам диспатч был заблокирован dispatch_gate'ом и критик реально не
запустился. Это гонка/расход лимита на заблокированной попытке --
дефект ВЗАИМОДЕЙСТВИЯ двух гейтов, не самого dispatch_gate.py.

ПРОВЕРКИ (только для tool_name in {"Task","Agent"}; любой другой
тул -- пропуск exit 0 без побочных эффектов; хук STATELESS -- спека
п.5, никаких файлов состояния не создаёт и не читает):

 1. subagent_type == "builder": tool_input.prompt должен содержать
    DoD-маркер (DOD_MARKERS_RE ниже). Нет ни одного совпадения ->
    БЛОК (BLOCK_MESSAGE_NO_DOD).
 2. subagent_type == "builder" И prompt содержит признак записи
    (WRITE_INDICATORS_RE) -- КОНСЕРВАТИВНАЯ эвристика спеки:
    блокируем ТОЛЬКО когда есть write-признак И НЕТ ОБОИХ
    манифест-маркеров (MANIFEST_GIVEN_RE И MANIFEST_OWNS_RE, оба
    обязательны) -> БЛОК (BLOCK_MESSAGE_NO_MANIFEST). Write-признаков
    нет -> проверка 2 пропускается целиком (read-only диспатч
    манифеста не требует, правило 11 кита). "owns" сам по себе --
    одновременно write-признак И один из двух манифест-маркеров
    (спека явно: "если owns уже есть, значит манифест писали") --
    значит промпт, где встретилось только "owns" без "дано"/"given",
    ловится этой же проверкой (write-признак есть, манифест неполон).
 3. ЛЮБОЙ subagent_type (включая critic/scout): tool_input.description,
    ЕСЛИ ПРИСУТСТВУЕТ, должен начинаться с модели воркера
    (LABEL_MODEL_PREFIX_RE) -> иначе БЛОК (BLOCK_MESSAGE_NO_LABEL).
    description отсутствует в payload -> проверка 3 пропускается.
 4. critic/scout (и любой subagent_type != "builder") -- проверки 1
    и 2 НЕ применяются (их DoD-форма другая, спека явно ограничивает
    семантику текстом промпта только для builder'а).

ПРИОРИТЕТ при НЕСКОЛЬКИХ одновременных нарушениях: 1 -> 2 -> 3,
первое найденное -- единственное сообщение в stderr (хук блокирует
ОДНИМ exit 2, не накапливает список). Спека порядок конфликтующих
сообщений не определяет явно -- это самостоятельное инженерное
решение (естественный порядок перечисления проверок в спеке),
задокументировано, не молча.

Fail-open на нераспознаваемый JSON -- тот же принцип, что у
critic_gate.py/dod_track.py/dod_gate.py этого кита.

t-152 RETRY (координатор, 2026-07-16, чинит НАХОДКУ №2 из
builder-отчёта t-152): WRITE_INDICATORS_RE ПЕРЕВЕДЕНА на \\b-границы
слова (py3 re -- Unicode-aware по умолчанию для str-паттернов, \\b
корректно видит границу между кириллическими буквами и
пробелом/пунктуацией/началом строки). ДО этой правки "правь" (без
границ) матчился ПОДСТРОКОЙ внутри обычных слов -- "поправь",
"исправь", "заправь", "направь" -- т.к. между "о"/"с"/"а" и "п" нет
границы \\w|\\W, а буквальный текст спеки "правь" всё равно находился
как substring где угодно внутри слова. С \\b "\\bправь\\b" матчит
ТОЛЬКО "правь" как отдельный токен (после пробела/пунктуации/начала
строки, до пробела/пунктуации/конца строки) -- "поправь"/"исправь"
теперь НЕ триггерят write-признак (негативный лок --
test_dispatch_gate.py, test_pravj_word_boundary_does_not_match_
poprav_or_isprav). Остальные альтернативы (owns/запиши/создай
файл/измени файл) получили те же \\b-границы для единообразия
(координатор просил границы для write-признаков в целом, не только
для "правь"); MANIFEST_GIVEN_RE/MANIFEST_OWNS_RE НЕ тронуты --
retry-спека называла только WRITE_INDICATORS_RE, расширять на
манифест-маркеры сам не стал (не в объявленном scope этого ретрая).

t-159 ФИКС КОДИРОВКИ STDIN (очередь v5 п.3, найдено в журнале
№10б-t1): кириллические маркеры («Дано:», «критерии приёмки») не
распознавались на реальном харнессе. ЭМПИРИКА (позитивный/негативный
контроль, F-30/F-34): `sys.stdin.read()` -- текстовое чтение --
декодирует байты кодировкой `sys.stdin.encoding`, которая на этой
машине равна `locale.getpreferredencoding()` = "cp1251" (проверено
`python -c "import locale,sys;print(locale.getpreferredencoding(),
sys.stdin.encoding)"` -> "cp1251 cp1251"), НЕ UTF-8. Харнесс пишет
payload UTF-8-байтами -- при чтении через cp1251 кириллица
превращается в mojibake, регексы MANIFEST_GIVEN_RE/DOD_MARKERS_RE
перестают матчить. Прямое воспроизведение ДО фикса (subprocess с
СЫРЫМИ UTF-8-байтами на stdin, БЕЗ text=True/encoding -- ровно так,
как харнесс кормит дочерний процесс): промпт с "Дано: репо целиком.
owns: tools/x.py." и DoD-маркерами дал exit_code=2 с mojibake-
сообщением "манифеста ... не найден" -- ложный блок легального
пишущего диспатча (scratchpad-проба builder-сессии t-159).
ФИКС: читаем stdin БАЙТАМИ (`sys.stdin.buffer.read()`, обходит
текстовый слой и его платформенную кодировку) и декодируем ЯВНО UTF-8
с fallback `errors="replace"` (харнесс отправляет UTF-8 -- основной
путь; replace вместо strict -- защита от битых байтов, чтобы хук не
падал исключением на мусорном вводе, тот же fail-open принцип, что у
остального парсинга этого файла). Юнит-тест с кириллицей гоняется
ДВУМЯ формами (test_dispatch_gate.py): (1) через subprocess с
ASCII-safe JSON (`ensure_ascii=True` -- \\uXXXX-эскейпы, независимо от
платформенной кодировки, это была бы "случайно рабочая" форма и ДО
фикса) и (2) через subprocess с СЫРЫМИ UTF-8-байтами (`ensure_ascii=
False`, input=bytes без text=True) -- именно форма (2) ловит регресс
до фикса; обе обязаны проходить одинаково ПОСЛЕ фикса.
"""

import json
import re
import sys

DOD_MARKERS_RE = re.compile(
    r"DoD|критери[ия] приёмки|witness|проверочн\w+ прогон", re.IGNORECASE
)
WRITE_INDICATORS_RE = re.compile(
    r"\bowns\b|\bзапиши\b|\bсоздай файл\b|\bправь\b|\bизмени файл\b", re.IGNORECASE
)
MANIFEST_GIVEN_RE = re.compile(r"дано|given", re.IGNORECASE)
MANIFEST_OWNS_RE = re.compile(r"owns", re.IGNORECASE)
LABEL_MODEL_PREFIX_RE = re.compile(r"^(haiku|sonnet|opus|fable|claude)[ :-]", re.IGNORECASE)

BLOCK_MESSAGE_NO_DOD = (
    "Диспатч builder'а без DoD не уходит (правило 11): впиши критерии "
    "приёмки и проверочный прогон, чей вывод станет witness"
)
BLOCK_MESSAGE_NO_MANIFEST = (
    "Пишущий диспатч без манифеста контекста (given/owns) не уходит "
    "(правило 11/D-0073)"
)
BLOCK_MESSAGE_NO_LABEL = (
    "Лейбл диспатча начинается с модели воркера (правило 7): 'sonnet: …'"
)


def decide(payload: dict) -> tuple[int, str]:
    """Чистая логика решения, без I/O -- тестируемая напрямую (тот же
    стиль, что critic_gate.decide). Возвращает (exit_code,
    stderr_message); "" значит "ничего не писать в stderr"."""
    tool_name = payload.get("tool_name")
    if tool_name not in ("Task", "Agent"):
        return 0, ""

    tool_input = payload.get("tool_input") or {}
    subagent_type = tool_input.get("subagent_type")
    prompt = tool_input.get("prompt") or ""
    description = tool_input.get("description")

    if subagent_type == "builder":
        if not DOD_MARKERS_RE.search(prompt):
            return 2, BLOCK_MESSAGE_NO_DOD

        if WRITE_INDICATORS_RE.search(prompt):
            has_manifest = bool(MANIFEST_GIVEN_RE.search(prompt)) and bool(
                MANIFEST_OWNS_RE.search(prompt)
            )
            if not has_manifest:
                return 2, BLOCK_MESSAGE_NO_MANIFEST

    if description is not None:
        if not LABEL_MODEL_PREFIX_RE.search(description):
            return 2, BLOCK_MESSAGE_NO_LABEL

    return 0, ""


def _reconfigure_stderr_utf8():
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def main() -> int:
    _reconfigure_stderr_utf8()

    # t-159: читаем БАЙТАМИ (sys.stdin.buffer), не через текстовый
    # sys.stdin.read() -- последний декодирует платформенной
    # кодировкой (cp1251 на этой машине, см. докстринг), а харнесс
    # шлёт UTF-8; явный decode(..., errors="replace") -- основной
    # путь UTF-8, replace -- fail-open защита от битых байтов.
    raw_bytes = sys.stdin.buffer.read()
    raw = raw_bytes.decode("utf-8", errors="replace")
    try:
        payload = json.loads(raw)
    except Exception:
        # Нераспознаваемый вход -- fail open, тот же принцип, что
        # остальные хуки этого кита.
        return 0

    exit_code, message = decide(payload)
    if exit_code == 2:
        sys.stderr.write(message + "\n")
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
