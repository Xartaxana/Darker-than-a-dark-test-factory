"""hygiene_gate.py -- PreToolUse-хук командной гигиены в WARN-РЕЖИМЕ
(НЕ блокирующий) для тулов Bash|PowerShell. Порт штабного
tools/hygiene_gate.py (Operating-System-for-LLMs) на канон AO3,
скоуп v1 -- УЗКИЙ: только один детект-класс, «запись в журнал мимо
python scripts/log_append.py» (CLAUDE.md, «Дисциплина команд» п.4:
"Журналы конвейера -- через python scripts/log_append.py"). Три
других класса референса (cd-префикс, ` 2>&1`, `python -c`/heredoc) --
NON-GOALS этой задачи (спека: "расширение на другие классы -- НЕ твоя
задача"), не портированы.

АДАПТАЦИЯ К AO3 (отличия от референса):

1. Два журнала, не один: у штаба единственный routing-log; здесь
   logs/routing-log.jsonl (routing) И state/orchestrator-log.md
   (orchestrator) -- оба триггерят класс (спека, «Адаптация к AO3»).
2. Каноническая форма -- НЕ Edit/Write-тул (в AO3 журнал вообще не
   правится вручную), а конкретная команда `python scripts/log_append.py`
   (правило 4 «Дисциплина команд»). Присутствие подстроки "log_append.py"
   в команде (case-insensitive) считается канонической формой и
   отменяет срабатывание -- решение по неоднозначности спеки
   (буквально: "И это НЕ канонический вызов python scripts/log_append.py"),
   тот же принцип, что штабное решение по классу (г) в его референсе:
   заголовок класса -- «мимо log_append.py», не «любая команда с
   > /journal-подстрокой»; при реальном каноническом вызове
   log_append.py сам делает I/O через open()/Path.write_text, а не
   через shell-редирект -- но спека прямо просит проверить
   исключение как отдельное условие, не полагаться на то, что
   комбинация "canonical + redirect" никогда не встретится на
   практике (adversarial-тест ниже это проверяет явно).
3. PowerShell-токены записи (Add-Content/Set-Content/Out-File) --
   AO3-специфика (среда Windows/PowerShell), у штаба их нет: канон
   AO3 явно допускает PowerShell как альтернативу Bash (settings.json
   matcher "Bash|PowerShell"), поэтому набор write-индикаторов шире
   штабного (printf/echo) на эти три PowerShell-cmdlet'а.

Условие срабатывания (все три части обязательны, AND):
  (а) подстрока "routing-log" ИЛИ "orchestrator-log" (case-insensitive);
  (б) индикатор записи: `>` (покрывает и `>>`, т.к. `>>` содержит `>`)
      ИЛИ токен printf/echo/Add-Content/Set-Content/Out-File
      (word-boundary regex, case-insensitive);
  (в) НЕ канонический вызов -- подстроки "log_append.py" НЕТ в команде.

Формат вывода -- ДОСЛОВНО тот же контракт, что у референса (уже
эмпирически сверен ТАМ по бинарнику харнесса claude.exe: Zod-схема
PreToolUse-хука несёт hookSpecificOutput.additionalContext опционально,
permissionDecision -- НАМЕРЕННО не используется в warn-режиме, см. B1
референса: "allow" авто-аппрувил бы флагнутую команду). Повторную
сверку бинарника в этой сессии не делал -- контракт наследуется от уже
проверенного источника (референс читан целиком по манифесту задачи),
не самостоятельная гипотеза.

Fail-open: не-Bash/PowerShell тул, пустой/битый stdin, payload не
dict, command не строка/пустая строка, любое внутреннее исключение
-- везде тихий пропуск, exit 0, никогда ненулевой код.

Безопасность на больших входах: все проверки -- substring (`in`,
O(n)) или простой \b-regex БЕЗ вложенных квантификаторов -- линейны
по длине команды, катастрофического backtracking нет. Лимитов
(MAX_*, потолков длины) в этом модуле НЕТ -- граничные тесты для них
поэтому не нужны (правило 6а CLAUDE.md кита применяется только к
введённым лимитам).
"""

from __future__ import annotations

import json
import re
import sys

JOURNAL_SUBSTRINGS = ("routing-log", "orchestrator-log")
CANONICAL_SUBSTRING = "log_append.py"

WRITE_TOKEN_RE = re.compile(
    r"\b(printf|echo|Add-Content|Set-Content|Out-File)\b", re.IGNORECASE
)

MSG_JOURNAL_BYPASS = (
    "журнал пишется только через python scripts/log_append.py "
    "(CLAUDE.md, «Дисциплина команд» п.4)"
)


def _has_journal_substring(command_lower: str) -> bool:
    return any(s in command_lower for s in JOURNAL_SUBSTRINGS)


def _has_write_indicator(command: str) -> bool:
    return ">" in command or bool(WRITE_TOKEN_RE.search(command))


def _is_canonical_call(command_lower: str) -> bool:
    return CANONICAL_SUBSTRING in command_lower


def _is_journal_bypass(command: str) -> bool:
    lower = command.lower()
    if not _has_journal_substring(lower):
        return False
    if not _has_write_indicator(command):
        return False
    if _is_canonical_call(lower):
        return False
    return True


def decide(payload: dict) -> tuple[int, dict | None]:
    """Чистая логика, без I/O -- тестируемая напрямую (тот же стиль,
    что референс). exit_code ВСЕГДА 0 (WARN-режим). Возвращает
    (0, None) на тихий пропуск, (0, dict) -- dict уже готов к
    json.dumps на stdout при срабатывании."""
    if not isinstance(payload, dict):
        return 0, None

    tool_name = payload.get("tool_name")
    if tool_name not in ("Bash", "PowerShell"):
        return 0, None

    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return 0, None
    command = tool_input.get("command")
    if not isinstance(command, str) or not command:
        return 0, None

    if not _is_journal_bypass(command):
        return 0, None

    context = "Командная гигиена (WARN, не блокирует): " + MSG_JOURNAL_BYPASS
    # Ключа permissionDecision здесь НЕТ НАМЕРЕННО -- warn не трогает
    # permission-путь (см. докстринг модуля / B1 референса).
    return 0, {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": context,
        }
    }


def _reconfigure_stdout_utf8() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def main() -> int:
    _reconfigure_stdout_utf8()

    # Байт-безопасный паттерн: sys.stdin.buffer.read() обходит
    # платформенную кодировку текстового sys.stdin, явный decode
    # utf-8 с errors="replace" -- fail-open на битые байты.
    raw_bytes = sys.stdin.buffer.read()
    raw = raw_bytes.decode("utf-8", errors="replace")
    try:
        payload = json.loads(raw)
    except Exception:
        return 0

    try:
        exit_code, output = decide(payload)
    except Exception:
        return 0

    if output is not None:
        sys.stdout.write(json.dumps(output, ensure_ascii=False) + "\n")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
