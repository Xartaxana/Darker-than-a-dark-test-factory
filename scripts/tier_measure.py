"""tier_measure.py -- измерение ФАКТИЧЕСКОЙ модели воркера по его
собственному jsonl-транскрипту Claude Code.

Порт из эталонного репо D:\\Improving_AI\\Operating-System-for-LLMs,
tools/tier_echo.py (функции iter_transcript_models/count_models/
SKIP_MODELS), 2026-07-19 -- порт D-0083 их DECISIONS_FULL.md. Кросс-репо
импорт между OS-репо и этим (AO3_tests) запрещён политикой изоляции
деплоев -- этот модуль самостоятельный, без импорта из tools/tier_echo.py
эталона; логика скопирована и адаптирована под канон этого репо (docstring-
стиль scripts/log_append.py, а не оригинала).

Мотивация (докстринг log_append.py, инцидент F-44 этого репо, и два
прецедента OS-репо, ради которых порт делается сейчас): ярусное
требование, закрываемое ТОЛЬКО самодекларацией поля model в
logs/routing-log.jsonl, не ловит расхождение между заявленной и
фактически исполнившей задачу моделью -- ни полную подмену (заявлен
fable, исполнен opus), ни частичную mid-worker подмену (fable -> sonnet
на части ходов одного воркера). Реальный замер по транскрипту воркера
закрывает это лучше самодекларации (D-0063 OS-репо: "код гарантирует
встречу с замером, суждение о расхождении -- за сессией/координатором").

Функции:
  iter_transcript_models(path) -- yields строку message.model на каждый
    assistant-ход jsonl-транскрипта (в порядке появления в файле),
    пропуская синтетические строки (SKIP_MODELS) и любые битые/невалидные
    строки молча (не роняя разбор остальных).
  count_models(models) -- dict {model: счёт ходов}, порядок --
    первого появления (обычный dict, Python 3.7+).
  find_worker_transcript(worker_ref) -- по хэндлу воркера routing-log.jsonl
    (D-0076, поле worker_ref) находит jsonl-транскрипт субагента на диске,
    если ref детерминированно на него указывает.

Байт-безопасное чтение (errors="replace") -- тот же принцип, что у
эталона tier_echo.py и у tools/dod_gate.py/dod_track.py OS-репо: файл
транскрипта может содержать невалидные UTF-8 байты, замена вместо падения
не роняет чтение остальных строк.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

# Зеркалит tools/usage_report.py:317 OS-репо (см. докстринг tools/tier_echo.py
# эталона за цитату) -- харнесс-внутренние stop-sequence-строки транскрипта
# несут model=="<synthetic>", это не реальный ход субагента и искажало бы
# счёт/список моделей.
SKIP_MODELS = {"<synthetic>"}

# D-0083, добавление этого порта (не было в эталоне tier_echo.py -- там
# путь транскрипта приходит готовым в SubagentStop payload'е): worker_ref
# routing-log.jsonl (D-0076) детерминированно указывает на транскрипт
# только в форме "async:<id>" или "agent:<id>", id -- [a-z0-9-]+ (реальные
# id субагентов Claude Code -- lowercase hex-строки, эмпирически
# подтверждено на этой машине: ls ~/.claude/projects/*/*/subagents/ дал
# имена вида agent-a01d9bf5189387b76.jsonl). Прочие конвенции worker_ref
# этого репо (cli:<ISO>, job:<...>, retro:<...>, lock:<...>, произвольные
# описательные строки вроде "wr"/"wr-A") не несут такого пути -- функция
# возвращает None для них, не пытаясь угадывать иначе (тот же принцип
# отказа от угадывания, что в tier_echo.py._extract_agent_transcript_path).
_WORKER_REF_RE = re.compile(r"^(?:async|agent):([a-z0-9-]+)$")


def _projects_dir() -> Path:
    """~/.claude/projects (expanduser), вычисляется при КАЖДОМ вызове, а
    не один раз при импорте модуля -- так тесты могут monkeypatch эту
    функцию напрямую (изоляция от реального домашнего каталога и от
    других тестов процесса), не трогая os.environ/Path.home глобально."""
    return Path("~/.claude/projects").expanduser()


def iter_transcript_models(path):
    """Yields одну строку model на каждый assistant-ход jsonl-транскрипта,
    в порядке появления в файле. Формат строки (type=="assistant",
    message.model) и SKIP_MODELS-фильтр -- буквально порт
    tier_echo.iter_transcript_models эталона (см. докстринг модуля).
    Битые JSON-строки и строки без валидного message.model -- пропускаются
    молча, не роняя разбор остальных строк файла."""
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if not isinstance(obj, dict) or obj.get("type") != "assistant":
                continue
            message = obj.get("message")
            if not isinstance(message, dict):
                continue
            model = message.get("model")
            if isinstance(model, str) and model and model not in SKIP_MODELS:
                yield model


def count_models(models) -> dict:
    """Считает ходы на модель, сохраняя порядок первого появления (обычный
    dict Python 3.7+ -- порядок вставки), для детерминированного вывода
    предупреждений вызывающей стороны (log_append.py)."""
    counts: dict = {}
    for model in models:
        counts[model] = counts.get(model, 0) + 1
    return counts


def find_worker_transcript(worker_ref):
    """Path к jsonl-транскрипту субагента по хэндлу worker_ref
    routing-log.jsonl (D-0076), либо None, если ref не имеет формы
    async:<id>/agent:<id> (id = [a-z0-9-]+) -- прочие формы (cli:/lock:/
    job:/retro:/описательные строки) не несут детерминированного пути,
    None возвращается без попытки угадать иначе.

    Ищет ~/.claude/projects/*/*/subagents/agent-<id>.jsonl (expanduser);
    возвращает первое совпадение glob'а, либо None, если файл не найден
    (id не существует, транскрипт ещё не создан харнессом, и т.п.)."""
    if not isinstance(worker_ref, str):
        return None
    m = _WORKER_REF_RE.match(worker_ref)
    if not m:
        return None
    agent_id = m.group(1)
    matches = list(_projects_dir().glob(f"*/*/subagents/agent-{agent_id}.jsonl"))
    if not matches:
        return None
    return matches[0]
