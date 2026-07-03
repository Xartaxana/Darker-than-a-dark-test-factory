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

import subprocess
from pathlib import Path

from framework.config import settings

_proc: subprocess.Popen | None = None
_PORT = "8080"


def _mitmdump() -> str:
    return str(settings.FRAMEWORK_ROOT / ".venv" / "Scripts" / "mitmdump.exe")


def start_replay(flows_file: Path) -> None:
    """Поднимает mitmdump, отдавая записанные флоу приложению.

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


def start_record(flows_file: Path) -> None:
    """Поднимает mitmdump на запись трафика в flows_file."""
    global _proc
    _proc = subprocess.Popen([
        _mitmdump(), "--listen-host", "0.0.0.0", "--listen-port", _PORT,
        "-w", str(flows_file), "-q",
    ])


def stop() -> None:
    global _proc
    if _proc is not None:
        _proc.terminate()
        _proc = None


def set_device_proxy() -> None:
    """Направляет HTTP(S) гостя на mitmdump хоста (10.0.2.2 = host loopback из qemu)."""
    subprocess.run([settings.ADB, "shell", "settings", "put", "global",
                    "http_proxy", settings.PROXY_HOST_ALIAS], check=True)


def clear_device_proxy() -> None:
    """Снимает прокси гостя (после прогона, чтобы live-трафик шёл напрямую)."""
    subprocess.run([settings.ADB, "shell", "settings", "put", "global",
                    "http_proxy", ":0"], check=False)
