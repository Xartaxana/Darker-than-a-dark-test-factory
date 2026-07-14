"""Управление mitmproxy для replay-режима.

Спайк B закрыт (2026-07-03, docs/environment-setup.md): доказан полный цикл
record→replay HTTPS-трафика WebView приложения. Ключевые условия, без которых
не работает:
  * эмулятор запущен с -writable-system (scripts/tasks.ps1 Start-Emulator -WritableSystem);
  * CA mitmproxy внедрён namespace-aware способом (scripts/install-mitm-ca.sh +
    ca-mount.sh): tmpfs поверх /system + /apex conscrypt cacerts в init-namespace,
    затем перезапуск фреймворка, чтобы новый zygote унаследовал mount; SELinux-контекст
    каталогов-точек — system_security_cacerts_file (иначе крэш system_server);
  * прокси гостя выставлен на 10.0.2.2:8080 (set_device_proxy).

В live-режиме модуль не используется.
"""
from __future__ import annotations

import socket
import subprocess
import time
from pathlib import Path

from framework.config import settings

_proc: subprocess.Popen | None = None
_PORT = "8080"
_READY_TIMEOUT = 15  # сек — ждать, пока mitmdump реально слушает порт


def _mitmdump() -> str:
    return str(settings.FRAMEWORK_ROOT / ".venv" / "Scripts" / "mitmdump.exe")


def _wait_listening(port: int, timeout: int) -> None:
    """Ждёт, пока mitmdump реально начнёт слушать `port` — Popen возвращает
    управление сразу, а mitmdump поднимается не мгновенно (импорт аддонов,
    парсинг --server-replay). Без ожидания первая навигация теста может уйти
    мимо ещё не поднятого прокси."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.3)
    raise TimeoutError(f"mitmdump не поднял порт {port} за {timeout}s")


def start_replay(flows_file: Path) -> None:
    """Поднимает mitmdump, отдавая записанные флоу приложению. Блокируется до тех
    пор, пока порт не начнёт слушаться (см. `_wait_listening`).

    Флаги подобраны на закрытии спайка B:
      server_replay_reuse=true — один и тот же ответ на повторные запросы (страница
        AO3 тянет ассеты многократно);
      server_replay_extra=forward — незаписанные запросы уходят на живой сервер
        (без него они падают 404 и ломают загрузку);
      connection_strategy=lazy — не открывать соединение к серверу, пока не понадобится.
    """
    global _proc
    _proc = subprocess.Popen([
        _mitmdump(), "--listen-host", "0.0.0.0", "--listen-port", _PORT,
        "--server-replay", str(flows_file),
        "--set", "server_replay_reuse=true",
        "--set", "server_replay_extra=forward",
        "--set", "connection_strategy=lazy",
        "-q",
    ])
    _wait_listening(int(_PORT), _READY_TIMEOUT)


def start_record(flows_file: Path) -> None:
    """Поднимает mitmdump на запись трафика в flows_file."""
    global _proc
    _proc = subprocess.Popen([
        _mitmdump(), "--listen-host", "0.0.0.0", "--listen-port", _PORT,
        "-w", str(flows_file), "-q",
    ])


def stop() -> None:
    """Останавливает mitmdump и ждёт реального завершения процесса (не только
    terminate()) — иначе следующий start_replay/start_record того же прогона
    может застать порт ещё занятым уходящим процессом (WinError 10048)."""
    global _proc
    if _proc is not None:
        _proc.terminate()
        try:
            _proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _proc.kill()
            _proc.wait(timeout=5)
        _proc = None


def set_device_proxy() -> None:
    """Направляет HTTP(S) гостя на mitmdump хоста (10.0.2.2 = host loopback из qemu).

    `timeout=settings.ADB_SHELL_TIMEOUT` (AT-BUG-009): зависший/неотвечающий
    adb-shell иначе подвешивает вызов навсегда — кандидат в корень наблюдения
    №1 AT-BUG-009 (ReadTimeoutError на TC-013 внутри driver.get() ПОСЛЕ этого
    вызова на нагруженной длинной сессии). Истечение — явная `TimeoutError` с
    контекстом, не молчаливый клин."""
    cmd = [settings.ADB, "shell", "settings", "put", "global",
           "http_proxy", settings.PROXY_HOST_ALIAS]
    try:
        subprocess.run(cmd, check=True, timeout=settings.ADB_SHELL_TIMEOUT)
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(
            f"adb shell settings put http_proxy (set_device_proxy) не ответил "
            f"за {settings.ADB_SHELL_TIMEOUT}s (AT-BUG-009)"
        ) from exc


def clear_device_proxy() -> None:
    """Снимает прокси гостя (после прогона, чтобы live-трафик шёл напрямую).

    Тот же конечный `timeout` (AT-BUG-009), что `set_device_proxy` — teardown
    обязан завершаться явной ошибкой, а не висеть, даже если `check=False`
    (истечение таймаута — не то же самое, что ненулевой returncode, и не
    подавляется `check=False`)."""
    cmd = [settings.ADB, "shell", "settings", "put", "global",
           "http_proxy", ":0"]
    try:
        subprocess.run(cmd, check=False, timeout=settings.ADB_SHELL_TIMEOUT)
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(
            f"adb shell settings put http_proxy (clear_device_proxy) не "
            f"ответил за {settings.ADB_SHELL_TIMEOUT}s (AT-BUG-009)"
        ) from exc
