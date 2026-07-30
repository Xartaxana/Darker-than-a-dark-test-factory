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

import os
import socket
import subprocess
import time
from pathlib import Path

from framework.config import settings

_proc: subprocess.Popen | None = None
_PORT = "8080"
_READY_TIMEOUT = 15  # сек — ждать, пока mitmdump реально слушает порт

# --- AT-BUG-011: fail-fast проверка mitm-CA в системном APEX-сторе доверия ---

_DEFAULT_OPENSSL = r"C:\Program Files\Git\usr\bin\openssl.exe"
_APEX_CACERTS_DIR = "/apex/com.android.conscrypt/cacerts/"


def _ca_pem_path() -> Path:
    override = os.environ.get("AO3_MITM_CA_PEM")
    if override:
        return Path(override)
    return Path.home() / ".mitmproxy" / "mitmproxy-ca-cert.pem"


def _openssl_path() -> str:
    return os.environ.get("AO3_OPENSSL", _DEFAULT_OPENSSL)


def is_ca_installed() -> bool:
    """Проверяет присутствие mitm-CA в системном APEX-сторе доверия conscrypt —
    ТА ЖЕ проверка, что `install-mitm-ca.sh`/`Install-MitmCA` печатают как
    «CA visible in apex store: OK» (см. `scripts/install-mitm-ca.sh`, последний
    блок): вычисляет `subject_hash_old` CA-сертификата через `openssl` (тем же
    способом, что и сам install-скрипт) и ищет файл `<hash>.0` в
    `/apex/com.android.conscrypt/cacerts/` на устройстве через `adb shell ls`.

    Не устанавливает и не переустанавливает CA — только сообщает присутствие;
    вызывающий код (`framework/tests/conftest.py::_ensure_replay_ca`) решает,
    что делать при отсутствии (AT-BUG-011: раньше отсутствие CA обнаруживалось
    только 120–240с ReadTimeoutError'ом на первом replay-тесте)."""
    ca_pem = _ca_pem_path()
    if not ca_pem.exists():
        raise RuntimeError(
            f"CA PEM не найден: {ca_pem} — mitmdump ни разу не запускался "
            f"(он генерирует CA-сертификат при первом старте). AT-BUG-011."
        )
    try:
        hash_cp = subprocess.run(
            [_openssl_path(), "x509", "-inform", "PEM", "-subject_hash_old",
             "-in", str(ca_pem), "-noout"],
            capture_output=True, text=True, timeout=settings.ADB_SHELL_TIMEOUT,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(
            f"openssl subject_hash_old (is_ca_installed) не ответил за "
            f"{settings.ADB_SHELL_TIMEOUT}s (AT-BUG-011)"
        ) from exc
    if hash_cp.returncode != 0:
        raise RuntimeError(
            f"openssl subject_hash_old упал на {ca_pem}: "
            f"{hash_cp.stdout}{hash_cp.stderr} (AT-BUG-011)"
        )
    ca_hash = hash_cp.stdout.strip()
    try:
        ls_cp = subprocess.run(
            [settings.ADB, "shell", "ls", _APEX_CACERTS_DIR],
            capture_output=True, text=True, timeout=settings.ADB_SHELL_TIMEOUT,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(
            f"adb shell ls {_APEX_CACERTS_DIR} (is_ca_installed) не ответил за "
            f"{settings.ADB_SHELL_TIMEOUT}s (AT-BUG-011)"
        ) from exc
    return f"{ca_hash}.0" in ls_cp.stdout


# --- ESC-009: fail-fast проверка достижимости апстрима прокси->AO3 ---
#
# Диагноз (state/escalations.md ESC-009, «Корень 3», Lead Fable + critic
# a9a831c9060df5aa5, 2026-07-30): хост имеет живой IPv6-адрес/маршрут, но
# IPv6-ТРАНЗИТ — чёрная дыра. RFC 6724 предпочитает IPv6, `getaddrinfo`
# отдаёт AAAA-записи первыми, mitmproxy пробует адреса ПОСЛЕДОВАТЕЛЬНО и
# платит ~21с Windows TCP-connect-таймаута ЗА КАЖДЫЙ мёртвый IPv6-адрес
# (замер: 2x21с на archiveofourown.org + 21с на ajax.googleapis.com).
# `server_replay_extra=forward` тянет незаписанные URL с живого AO3 ->
# суммарная задержка не укладывается в WEBVIEW_LOAD_TIMEOUT ->
# `driver.get()` падает `ReadTimeoutError` через ~166с вместо мгновенной
# диагностики среды. AT-BUG-017 (`wait_device_proxy_reachable`) проверяет
# только плечо устройство->хост-прокси — это плечо прокси->upstream
# оставалось непокрытым.
UPSTREAM_CONNECT_BUDGET = 5.0  # сек — бюджет ОДНОЙ попытки connect() к апстриму


def assert_upstream_fast(host: str = "archiveofourown.org", port: int = 443) -> None:
    """Пробует соединиться с ПЕРВЫМ адресом резолва `host:port` (тот же
    порядок, что использует резолвер ОС и, вслед за ним, mitmproxy) с
    коротким собственным бюджетом (`UPSTREAM_CONNECT_BUDGET`, НЕ дефолтный
    Windows TCP-таймаут ~21с). Недостижимость первого адреса за бюджет ->
    явная `RuntimeError` с диагнозом ESC-009 — мгновенный явный отказ вместо
    166-секундного `ReadTimeoutError` на первой replay-навигации теста."""
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    family, _, _, _, sa = infos[0]
    s = socket.socket(family, socket.SOCK_STREAM)
    s.settimeout(UPSTREAM_CONNECT_BUDGET)
    try:
        s.connect(sa)
    except OSError as exc:
        family_name = "IPv6 (AAAA)" if family == socket.AF_INET6 else "IPv4 (A)"
        raise RuntimeError(
            f"ESC-009: первый по порядку резолва адрес {sa[0]} апстрима "
            f"{host}:{port} ({family_name}) недостижим за "
            f"{UPSTREAM_CONNECT_BUDGET}s. mitmproxy (server_replay_extra="
            "forward) соединяется с апстримом ПОСЛЕДОВАТЕЛЬНО по адресам "
            "резолва — мёртвый первый адрес (известный корень: мёртвый "
            "IPv6-транзит хоста при живом IPv6-маршруте, RFC 6724 отдаёт "
            "AAAA первыми) стоил бы ~21с реального TCP-таймаута КАЖДЫЙ раз, "
            "суммарно не укладываясь в WEBVIEW_LOAD_TIMEOUT — вместо этого "
            "мгновенный явный отказ. См. state/escalations.md ESC-009."
        ) from exc
    finally:
        s.close()


def _mitmdump() -> str:
    return str(settings.FRAMEWORK_ROOT / ".venv" / "Scripts" / "mitmdump.exe")


def _assert_own_listener() -> None:
    """Замок против ЧУЖОГО слушателя порта `_PORT` (ESC-009, живой
    прецедент сессии 2026-07-30: mitmdump фикстуры умер сразу после старта
    (Errno 10048 — порт уже занят чужим процессом), но `_wait_listening`
    честно подтвердила «порт слушается» — это был ЧУЖОЙ mitmdump (например
    критика, работающего параллельно), и тест прошёл ЗЕЛЁНЫМ по ЧУЖОЙ
    записи вместо падения). `_wait_listening` доказывает только то, что
    ПОРТ занят — не то, что это НАШ `_proc`. Зовётся сразу после
    `_wait_listening` в `start_replay`/`start_record` (классовая
    полнота — оба места поднимают mitmdump на тот же порт тем же
    паттерном)."""
    returncode = _proc.poll() if _proc is not None else None
    if returncode is not None:
        raise RuntimeError(
            f"mitmdump завершился кодом {returncode} сразу после старта, но "
            f"порт {_PORT} слушается — это ЧУЖОЙ процесс, тест пошёл бы по "
            "чужой записи (прецедент: Errno 10048, сессия 2026-07-30, "
            "ESC-009)."
        )


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
    _assert_own_listener()


def wait_device_proxy_reachable(timeout: float | None = None) -> None:
    """AT-BUG-017: `_wait_listening` (см. выше) проверяет ГОТОВНОСТЬ mitmdump
    только на ХОСТ-порту — недостаточно. `replay`-фикстура зовёт
    `set_device_proxy()`, затем `start_replay()` (блокируется до хост-порта),
    но первая реальная навигация теста иногда всё равно ловит
    `net::ERR_PROXY_CONNECTION_FAILED` в `driver.get()` — похоже на race
    NAT-уровня qemu (проброс порта/ARP) или задержку применения системной
    настройки прокси Android'ом относительно момента, когда WebView реально
    открывает TCP-соединение. Эта проверка закрывает шов СО СТОРОНЫ
    УСТРОЙСТВА: поллит TCP-достижимость `settings.PROXY_HOST_ALIAS` через
    `adb shell nc` (toybox, есть на стандартном AVD-образе — проверено вручную
    на emulator-5554) — пустой stdin, `-w1` таймаут установления соединения,
    `-q1` не ждать данных сверх EOF (нам важен только факт TCP-коннекта, не
    ответ прокси). Короткий поллинг с конечным таймаутом
    (`settings.PROXY_DEVICE_REACHABLE_TIMEOUT`, тот же паттерн, что
    `adb._wait_package_service_ready`, AT-BUG-013) — исчерпание даёт явную
    `TimeoutError` с контекстом, не молчаливый клин; счастливый путь обычно
    возвращается с первой попытки (mitmdump к этому моменту уже подтверждённо
    слушает хост-порт), ноль лишней задержки."""
    host, _, port = settings.PROXY_HOST_ALIAS.partition(":")
    effective_timeout = (
        settings.PROXY_DEVICE_REACHABLE_TIMEOUT if timeout is None else timeout
    )
    marker = "AO3_PROXY_REACHABLE"
    cmd = [
        settings.ADB, "shell",
        f"echo -n | nc -w 1 -q 1 {host} {port} && echo {marker} || echo NOPE",
    ]
    deadline = time.time() + effective_timeout
    attempts = 0
    while True:
        attempts += 1
        try:
            cp = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=settings.ADB_SHELL_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            cp = None
        if cp is not None and marker in cp.stdout:
            return
        if time.time() >= deadline:
            raise TimeoutError(
                f"прокси {settings.PROXY_HOST_ALIAS} не достижим со стороны "
                f"устройства за {effective_timeout}s ({attempts} попыток) — "
                "AT-BUG-017: mitmdump слушает хост-порт, но устройство пока "
                "не может до него достучаться (race NAT/применения настройки)."
            )
        time.sleep(0.3)


def start_record(flows_file: Path) -> None:
    """Поднимает mitmdump на запись трафика в flows_file.

    ESC-009 (классовая полнота): раньше эта функция НЕ звала
    `_wait_listening` вовсе (в отличие от `start_replay`) — вызывающий код
    не имел гарантии, что порт реально поднят, ДО первой навигации записи;
    и `_assert_own_listener()` — тот же замок против чужого слушателя, что
    и в `start_replay` (одна поверхность отказа, два места запуска)."""
    global _proc
    _proc = subprocess.Popen([
        _mitmdump(), "--listen-host", "0.0.0.0", "--listen-port", _PORT,
        "-w", str(flows_file), "-q",
    ])
    _wait_listening(int(_PORT), _READY_TIMEOUT)
    _assert_own_listener()


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
