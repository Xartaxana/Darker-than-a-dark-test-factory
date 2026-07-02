"""Управление mitmproxy для replay-режима. В Фазе 1 транспорт эмулятор→прокси на
Windows-хосте ещё доводится (см. docs/environment-setup.md §Спайк B), поэтому здесь —
интерфейс и запуск/остановка процесса; подключение к прогонам активируется, когда
транспорт будет зафиксирован. В live-режиме не используется.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from framework.config import settings

_proc: subprocess.Popen | None = None


def start_replay(flows_file: Path) -> None:
    """Поднимает mitmdump в режиме воспроизведения записанных флоу."""
    global _proc
    mitm = settings.FRAMEWORK_ROOT / ".venv" / "Scripts" / "mitmdump.exe"
    _proc = subprocess.Popen(
        [str(mitm), "--listen-host", "0.0.0.0", "--listen-port", "8080",
         "--server-replay", str(flows_file), "--set", "server_replay_reuse=true", "-q"],
    )


def start_record(flows_file: Path) -> None:
    global _proc
    mitm = settings.FRAMEWORK_ROOT / ".venv" / "Scripts" / "mitmdump.exe"
    _proc = subprocess.Popen(
        [str(mitm), "--listen-host", "0.0.0.0", "--listen-port", "8080",
         "-w", str(flows_file), "-q"],
    )


def stop() -> None:
    global _proc
    if _proc is not None:
        _proc.terminate()
        _proc = None
