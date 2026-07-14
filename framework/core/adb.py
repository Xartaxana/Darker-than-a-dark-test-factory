"""Тонкая обёртка над adb. Всё общение с устройством вне Appium идёт сюда:
управление данными приложения, logcat, скриншоты, сидинг Room через run-as.
Ничего не знает об экранах приложения — переиспользуемо.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from framework.config import settings

_PKG = settings.APP_PACKAGE


def _run(
    args: list[str], timeout: float = settings.ADB_SHELL_TIMEOUT, **kw
) -> subprocess.CompletedProcess:
    """Обёртка над `subprocess.run` с конечным `timeout` (AT-BUG-009: зависший/
    неотвечающий adb-сервер иначе подвешивает вызов навсегда — тот же класс,
    что AT-BUG-007 закрыл для Appium HTTP-вызовов). Дефолт — `ADB_SHELL_TIMEOUT`
    (быстрые shell-команды); файловые операции (`install`/`push`) передают
    `timeout=settings.ADB_TRANSFER_TIMEOUT` явно. Истечение — `TimeoutError` с
    контекстом (команда, сколько ждали), не молчаливый клин/retry."""
    try:
        return subprocess.run(
            [settings.ADB, *args],
            capture_output=True, text=True, timeout=timeout, **kw,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(
            f"adb {' '.join(args)} не ответил за {timeout}s (AT-BUG-009)"
        ) from exc


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
    cp = _run(args, timeout=settings.ADB_TRANSFER_TIMEOUT)
    if "Success" not in cp.stdout:
        raise RuntimeError(f"APK install failed: {cp.stdout}{cp.stderr}")


def set_night_mode(dark: bool) -> None:
    """Переключает системную тёмную тему ОС (`cmd uimode night yes/no`) — стандартный
    способ на эмуляторе/устройстве без захода в системные настройки UI (см. TC-049)."""
    shell(f"cmd uimode night {'yes' if dark else 'no'}")


def logcat_dump(dest: Path, lines: int = 400) -> None:
    out = shell(f"logcat -d -t {lines}")
    dest.write_text(out, encoding="utf-8", errors="replace")


def logcat_clear() -> None:
    _run(["-s", settings.DEVICE_NAME, "logcat", "-c"])


# --- run-as: доступ к приватным данным приложения (работает на debug-сборке) ---

def run_as(cmd: str) -> str:
    return shell(f"run-as {_PKG} {cmd}")


def pull_app_file(rel_path: str, dest: Path) -> bool:
    """Тянет файл из приватной песочницы приложения на хост через run-as cat (бинарно).
    Не идёт через `_run()` (нужны сырые байты без `text=True`) — тот же конечный
    `ADB_TRANSFER_TIMEOUT` (AT-BUG-009) применён напрямую."""
    try:
        cp = subprocess.run(
            [settings.ADB, "-s", settings.DEVICE_NAME, "exec-out",
             "run-as", _PKG, "cat", rel_path],
            capture_output=True,  # bytes, без text=True
            timeout=settings.ADB_TRANSFER_TIMEOUT,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(
            f"adb exec-out run-as cat {rel_path} не ответил за "
            f"{settings.ADB_TRANSFER_TIMEOUT}s (AT-BUG-009)"
        ) from exc
    if cp.returncode != 0 or not cp.stdout:
        return False
    dest.write_bytes(cp.stdout)
    return True


def push_external(local_path: Path, remote_path: str) -> None:
    """Кладёт локальный файл в ПУБЛИЧНОЕ хранилище устройства (`/sdcard/...`) прямым
    `adb push` — в отличие от `push_app_file` (приватная песочница приложения через
    run-as + /data/local/tmp), сюда попадают файлы, которые должен УВИДЕТЬ системный
    SAF picker (`framework/steps/saf_steps.py`) или scanForOrphanedDownloads через
    выбранный SAF-каталог, а не сам процесс приложения напрямую."""
    _run(["-s", settings.DEVICE_NAME, "push", str(local_path), remote_path],
         timeout=settings.ADB_TRANSFER_TIMEOUT)


def push_app_file(src: Path, rel_path: str) -> None:
    """Кладёт файл в приватную песочницу приложения через /data/local/tmp + run-as cp."""
    tmp = f"/data/local/tmp/{src.name}"
    _run(["-s", settings.DEVICE_NAME, "push", str(src), tmp], timeout=settings.ADB_TRANSFER_TIMEOUT)
    run_as(f"cp {tmp} {rel_path}")
    shell(f"rm -f {tmp}")
