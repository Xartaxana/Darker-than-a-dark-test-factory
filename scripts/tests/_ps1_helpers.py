"""Общий хелпер для юнит-тестов scripts/tasks.ps1 (spec-p3-second-emulator N1).

НЕ файл с тестами (не матчит `test_*.py`, pytest его не собирает) - импортируется
явно тестовыми модулями, которым нужно дот-сорсить tasks.ps1 РЕАЛЬНЫМ PowerShell
и вызвать конкретную функцию изолированно.

Дисциплина: `$root` внутри tasks.ps1 задан ЛИТЕРАЛОМ `"D:\\AO3_tests"` (строка 6) -
дот-сорсинг ЭТОГО (worktree) файла НЕ меняет резолюцию `$root` (эмпирически
проверено builder-сессией p3-second-emulator N1, 2026-08-20: dot-source
worktree-копии tasks.ps1 всё равно даёт `$root=D:\\AO3_tests`). Поэтому КАЖДЫЙ
вызов, который может тронуть диск через `$root` (Set-EmulatorSessionState,
Start-Emulator), переопределяет `$root` СРАЗУ ПОСЛЕ дот-сорсинга на tmp_path -
тот же приём, что пинованный `framework/tests/test_device_liveness_guard_unit.py::
test_tasks_ps1_set_emulator_session_state_writes_resolved_params`. Дот-сорсится
именно WORKTREE-копия (по пути `__file__`), чтобы упражнять КОД ЭТОЙ правки, а не
main-репо.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

TASKS_PS1 = Path(__file__).resolve().parents[2] / "scripts" / "tasks.ps1"


def run_ps(command: str, timeout: int = 60) -> subprocess.CompletedProcess:
    """Запускает `command` реальным Windows PowerShell (`powershell`, НЕ pwsh -
    tasks.ps1 писан под PS 5.1 семантику, каноническая форма CLAUDE.md).
    `command` НЕ включает дот-сорсинг - вызывающий код сам решает, нужен ли
    `$root`-оверрайд ДО или ПОСЛЕ него.

    Кодировка (критик-раунд B1/advice-3, 2026-08-20, найдено ЭТИМ раундом
    эмпирически): на этом хосте PowerShell 5.1 пишет редиректнутый stdout/
    stderr в OEM-кодовой странице консоли (cp866), а Python-дефолт
    `text=True` без explicit encoding декодирует `locale.getpreferredencoding()`
    (cp1251 на этом хосте) - несовпадение даёт МОЛЧАЛИВУЮ порчу кириллицы
    (не исключение, просто нечитаемые байты), что ловилось только тестами,
    реально СРАВНИВАЮЩИМИ кириллический текст сообщений жнеца. Фикс - явно
    форсируем `[Console]::OutputEncoding` в UTF-8 БЕЗ BOM внутри самого
    PowerShell-процесса и декодируем ответ как utf-8 на python-стороне -
    единая, платформо-независимая кодировка вместо угадывания OEM-CP хоста.
    """
    utf8_prefix = "[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false); "
    return subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", utf8_prefix + command],
        capture_output=True, text=True, encoding="utf-8", timeout=timeout,
    )


def dot_source_prefix(fake_root: Path | None = None) -> str:
    """Префикс команды: дот-сорсит tasks.ps1 (worktree-копия), опционально
    переопределяет `$root` на `fake_root` СРАЗУ ПОСЛЕ (см. докстринг модуля) -
    ни один вызов ЭТОГО модуля не пишет в реальный `D:\\AO3_tests\\state\\`."""
    prefix = f". '{TASKS_PS1}'; "
    if fake_root is not None:
        prefix += f"$root = '{fake_root}'; "
    return prefix
