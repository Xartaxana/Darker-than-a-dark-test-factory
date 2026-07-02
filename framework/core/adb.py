"""Тонкая обёртка над adb. Всё общение с устройством вне Appium идёт сюда:
управление данными приложения, logcat, скриншоты, сидинг Room через run-as.
Ничего не знает об экранах приложения — переиспользуемо.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from framework.config import settings

_PKG = settings.APP_PACKAGE


def _run(args: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(
        [settings.ADB, *args],
        capture_output=True, text=True, **kw,
    )


def shell(cmd: str) -> str:
    return _run(["-s", settings.DEVICE_NAME, "shell", cmd]).stdout


def force_stop() -> None:
    shell(f"am force-stop {_PKG}")


def clear_app_data() -> None:
    """Полный сброс приложения к состоянию чистой установки (pm clear)."""
    shell(f"pm clear {_PKG}")


def is_installed() -> bool:
    return _PKG in shell("pm list packages")


def install(apk: str = settings.APK_PATH, reinstall: bool = True) -> None:
    args = ["-s", settings.DEVICE_NAME, "install"]
    if reinstall:
        args.append("-r")
    args.append(apk)
    cp = _run(args)
    if "Success" not in cp.stdout:
        raise RuntimeError(f"APK install failed: {cp.stdout}{cp.stderr}")


def logcat_dump(dest: Path, lines: int = 400) -> None:
    out = shell(f"logcat -d -t {lines}")
    dest.write_text(out, encoding="utf-8", errors="replace")


def logcat_clear() -> None:
    _run(["-s", settings.DEVICE_NAME, "logcat", "-c"])


# --- run-as: доступ к приватным данным приложения (работает на debug-сборке) ---

def run_as(cmd: str) -> str:
    return shell(f"run-as {_PKG} {cmd}")


def pull_app_file(rel_path: str, dest: Path) -> bool:
    """Тянет файл из приватной песочницы приложения на хост через run-as cat (бинарно)."""
    cp = subprocess.run(
        [settings.ADB, "-s", settings.DEVICE_NAME, "exec-out",
         "run-as", _PKG, "cat", rel_path],
        capture_output=True,  # bytes, без text=True
    )
    if cp.returncode != 0 or not cp.stdout:
        return False
    dest.write_bytes(cp.stdout)
    return True


def push_app_file(src: Path, rel_path: str) -> None:
    """Кладёт файл в приватную песочницу приложения через /data/local/tmp + run-as cp."""
    tmp = f"/data/local/tmp/{src.name}"
    _run(["-s", settings.DEVICE_NAME, "push", str(src), tmp])
    run_as(f"cp {tmp} {rel_path}")
    shell(f"rm -f {tmp}")
