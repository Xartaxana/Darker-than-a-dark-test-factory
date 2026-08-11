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
import sys
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


def _mitmdump() -> list[str]:
    """Командный префикс запуска mitmdump.

    НЕ exe-шим `.venv/Scripts/mitmdump.exe`: Windows Smart App Control
    (enforcement с 2026-08-04, VerifiedAndReputablePolicyState=1) блокирует
    локально сгенерированные неподписанные шимы venv — WinError 4551,
    69/165 ERROR в RUN-20260804-1301, 144 события CodeIntegrity 3033/3077.
    Тот же mitmdump запускается через ПОДПИСАННЫЙ python.exe венва
    (энтрипойнт mitmproxy.tools.main:mitmdump — ровно то, что зовёт шим);
    исключений SAC не поддерживает, откат на шим — только при выключенном
    SAC. Сверка обхода: `--version` даёт Mitmproxy 11.1.3 (2026-08-04)."""
    python = str(settings.FRAMEWORK_ROOT / ".venv" / "Scripts" / "python.exe")
    return [
        python, "-c",
        "import sys; from mitmproxy.tools.main import mitmdump; sys.exit(mitmdump())",
    ]


def _assert_own_listener() -> None:
    """Замок против ЧУЖОГО слушателя порта `_PORT` (ESC-009, живой
    прецедент сессии 2026-07-30: mitmdump фикстуры умер сразу после старта
    (Errno 10048 — порт уже занят чужим процессом), но `_wait_listening`
    честно подтвердила «порт слушается» — это был ЧУЖОЙ mitmdump (например
    критика, работающего параллельно), и тест прошёл ЗЕЛЁНЫМ по ЧУЖОЙ
    записи вместо падения). `_wait_listening` доказывает только то, что
    ПОРТ занят — не то, что это НАШ `_proc`. Зовётся сразу после
    `_spawn_and_wait_listening` в `start_replay`/`start_record` (классовая
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


# --- AT-BUG-043: гонка teardown(stop())/startup(start_replay|start_record)
# порта 8080 на Windows ---
#
# Диагностика (bugs/AT-BUG-043.md, state/escalations.md ESC-016): двукратный
# `[Errno 10048] ... address already in use` в setup replay-фикстуры, на
# РАЗНЫХ узлах разных прогонов, при том что порт в состоянии покоя свободен.
# Красная проба (scratchpad, ~150 циклов: idle stop->start, 20 конкурентных
# keep-alive соединений через реальный replay-трафик, CPU-сатурация 11
# фоновых процессов на 12-ядерной машине, 31 живой переход между соседними
# replay-тестами на реальном устройстве) НЕ смогла детерминированно
# воспроизвести саму гонку в этой сессии — ни один вариант не дал WinError
# 10048 повторно (см. bugs/AT-BUG-043.md, Обсуждение, полный протокол проб).
# Причинная неоднозначность НЕ снята: вклад реальной нагрузки полного стека
# (emulator+Appium+adb, конкурирующей за CPU/IO именно в момент двух
# исторических инцидентов) в исходном отчёте не исключён этой сессией.
#
# Несмотря на отсутствие красного повтора, ниже — defence-in-depth ИМЕННО
# по механизму (а), названному в исходной диагностике: `Popen.wait()` на
# Windows может вернуть код завершения процесса РАНЬШЕ, чем ОС полностью
# освободит порт для нового bind() (WaitForSingleObject сигнализирует
# раньше завершения асинхронной очистки ресурса драйвером). Это не
# ослабление таймаута (не голый sleep) — активная проверка bind() с
# ретраем и явным диагнозом при исчерпании бюджета.
_PORT_RELEASE_TIMEOUT = 5.0  # сек — бюджет ожидания освобождения порта в stop()
_START_RETRY_BUDGET = 10.0  # сек — суммарный бюджет ретраев Popen на конфликт bind
_START_RETRY_BACKOFF = 0.3  # сек — пауза между попытками Popen


def _wait_port_released(port: int, timeout: float | None = None) -> None:
    """После подтверждённой смерти `_proc` (`stop()`) активно проверяет, что
    порт `port` РЕАЛЬНО доступен для НОВОГО bind() — не то же самое, что
    «никто не отвечает на connect()» (это делает connect_ex-поллинг внутри
    `_spawn_and_wait_listening`, для другого случая: там ждём появления
    слушателя, здесь — исчезновения ресурса, который слушателя больше не
    имеет, но ОС ещё не освободила). Пробует bind() пробным сокетом в цикле;
    успех -> сразу закрывает пробный сокет и возвращается (счастливый путь:
    единственная попытка, задержка для человека незаметна — так вело себя
    ~150/150 циклов диагностики AT-BUG-043).

    ИЗМЕНЕНО (AT-BUG-043 attempt 2, критик-вход, блокер 1): раньше исчерпание
    `timeout` бросало `TimeoutError` наружу — `stop()` пробрасывал её
    вызывающему, а `conftest.py` teardown (`mitm.stop()`; `mitm.
    clear_device_proxy()` ПОДРЯД, без `try/finally`) на этом исключении НЕ
    снимал прокси устройства: порча среды (`settings put global http_proxy
    10.0.2.2:8080` остаётся выставленным) на весь остаток прогона —
    воспроизведено device-free пробой критика («stop() бросил TimeoutError
    через 5.0s... clear_device_proxy вызван: False»), гарантированно бьёт
    в сценарии ESC-009 (чужой mitmdump держит порт). Enforcing-слой ЭТОГО
    инварианта остаётся на СТОРОНЕ СТАРТА (`_spawn_and_wait_listening`
    ретраит именно конфликт bind — для того он и есть); эта функция теперь
    НИКОГДА не бросает — на исчерпании таймаута пишет видимый диагноз в
    stderr и ВОЗВРАЩАЕТСЯ, чтобы `stop()` гарантированно мог продолжить
    (а `conftest.py` — снять прокси через `finally`, см. блокер 1(б)).

    Видимый сигнал ретрая (детектор рецидива, критик-вход attempt 2, правило
    10в CLAUDE.md «Fail-fast среды»): и счастливый путь С ретраями (порт
    освободился НЕ с первой попытки), и путь исчерпания таймаута печатают
    строку в stderr с числом попыток/фактической длительностью — иначе
    молчаливый успешный ретрай навсегда гасит сигнатуру WinError 10048 и
    делает исходную гипотезу гонки непроверяемой.

    `timeout=None` (по умолчанию) читает `_PORT_RELEASE_TIMEOUT` ВНУТРИ
    тела функции, а не через дефолт-параметр — иначе значение защёлкивается
    на момент импорта модуля, и юнит-проба на инвариант «`stop()` без
    явного `timeout` не бросает» (attempt 2) не смогла бы ускорить прогон
    monkeypatch'ем модульной константы."""
    if timeout is None:
        timeout = _PORT_RELEASE_TIMEOUT
    deadline = time.time() + timeout
    start = time.time()
    attempts = 0
    last_exc: OSError | None = None
    while time.time() < deadline:
        attempts += 1
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            probe.bind(("0.0.0.0", port))
            if attempts > 1:
                print(
                    f"AT-BUG-043: порт {port} освободился после {attempts} "
                    f"попыток bind() за {time.time() - start:.2f}s (гонка "
                    "teardown/startup сработала, ретрай справился)",
                    file=sys.stderr,
                )
            return
        except OSError as exc:
            last_exc = exc
            time.sleep(0.1)
        finally:
            probe.close()
    print(
        f"AT-BUG-043 WARNING: порт {port} не освободился за {timeout}s "
        f"после остановки mitmdump ({attempts} попыток bind(), последняя "
        f"ошибка: {last_exc}) — НЕ бросаю (блокер 1, критик-вход attempt "
        "2), чтобы не сорвать teardown (clear_device_proxy); enforcing-слой "
        "— ретрай на старте (_spawn_and_wait_listening).",
        file=sys.stderr,
    )


def _spawn_and_wait_listening(args: list[str], ready_timeout: int) -> subprocess.Popen:
    """Popen + ожидание слушателя с ретраем НА КОНФЛИКТ BIND (AT-BUG-043).

    Раньше `start_replay`/`start_record` делали Popen один раз и ждали
    `_wait_listening` весь `ready_timeout`, даже если СВОЙ процесс уже умер
    (конфликт порта) — 15с впустую на попытку, обречённую с первой секунды,
    и голый `TimeoutError` без диагноза причины. Здесь: если свой `Popen`
    завершается САМ, ничего не заслушав в течение попытки — считаем это
    конфликтом bind (та же гонка, что `_wait_port_released` лечит на
    стороне `stop()`; этот путь — второй, симметричный слой защиты,
    единственный работающий, когда предыдущий mitmdump умер в ДРУГОМ
    pytest-процессе — исторический прецедент ESC-016: гонка ловилась на
    ПЕРВОМ replay-тесте свежего прогона, `stop()` текущего процесса тут
    вообще не звался) — ретраит Popen с коротким бэкоффом в пределах
    `_START_RETRY_BUDGET`.

    НЕ путать со случаем «порт слушается ЧУЖИМ процессом» (ESC-009): если
    connect() успевает ДО того, как наш процесс поспевает умереть (или он
    вовсе не умирает) — цикл возвращает `proc` как обычно, и решает, СВОЙ
    это слушатель или чужой, `_assert_own_listener()` СРАЗУ ПОСЛЕ возврата
    отсюда (вызывающий код, как раньше) — семантика замка ESC-009 не
    тронута. Если процесс жив, но НЕ заслушал порт за полный
    `ready_timeout` — это НЕ гонка порта (та убивает процесс почти
    мгновенно) — ретрая нет, поведение идентично прежнему поведению до
    AT-BUG-043 (голая `TimeoutError`).

    ВЛАДЕНИЕ ХЭНДЛОМ (AT-BUG-043 attempt 2, критик-вход, блокер 2): модуль-
    уровневый `_proc` присваивается СРАЗУ после КАЖДОГО `Popen()` — не
    только при успешном возврате функции. Раньше `start_replay`/
    `start_record` присваивали `_proc = _spawn_and_wait_listening(...)`
    только на нормальный возврат — на ветке «процесс жив, но не поднял
    порт за `ready_timeout`» (см. ниже, эта функция БРОСАЕТ, а не
    возвращает) `_proc` оставался `None`, и живой mitmdump становился
    сиротой: `stop()` не имел хэндла, чтобы его остановить — регрессия
    против до-фиксового кода, где `_proc = Popen(...)` присваивался сразу
    (живой прецедент такой ветки-сироты — `bugs/AT-BUG-025.md:206-213`).
    Проба критика подтвердила: «процессов порождено: 1; mitm._proc после
    отказа: None». Теперь ЛЮБОЙ исход этой функции оставляет `_proc` в
    согласованном состоянии: живой процесс (ветка `TimeoutError` ниже) —
    `_proc` указывает на него, `stop()` его остановит; мёртвый процесс
    (ветка `RuntimeError` — ретраи исчерпаны) — `_proc` явно сброшен в
    `None` (мёртвый хэндл никому не нужен, ничейного ЖИВОГО процесса при
    этом не остаётся — дохлые процессы на промежуточных попытках ретрая
    безобидны, они уже заменены следующим `Popen`)."""
    global _proc
    deadline = time.time() + _START_RETRY_BUDGET
    attempt = 0
    while True:
        attempt += 1
        attempt_start = time.time()
        proc = subprocess.Popen(args)
        _proc = proc  # владение с момента Popen -- AT-BUG-043 attempt 2, блокер 2
        poll_deadline = attempt_start + ready_timeout
        listening = False
        while time.time() < poll_deadline:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                if s.connect_ex(("127.0.0.1", int(_PORT))) == 0:
                    listening = True
                    break
            if proc.poll() is not None:
                break  # свой процесс уже умер -- слушателя дальше не будет
            time.sleep(0.3)
        if listening:
            if attempt > 1:
                print(
                    f"AT-BUG-043: mitmdump поднял порт {_PORT} с попытки "
                    f"{attempt} (гонка teardown/startup сработала на "
                    "старте, ретрай Popen справился)",
                    file=sys.stderr,
                )
            return proc
        if proc.poll() is None:
            # процесс жив, но не поднял порт за полный ready_timeout -- НЕ
            # гонка bind (та роняет процесс почти мгновенно) -- прежнее
            # поведение, без ретрая. _proc уже указывает на этот живой
            # процесс (владение выше) -- stop() сможет его остановить.
            raise TimeoutError(f"mitmdump не поднял порт {_PORT} за {ready_timeout}s")
        died_after = time.time() - attempt_start
        if attempt > 1:
            print(
                f"AT-BUG-043: mitmdump (попытка {attempt}) умер кодом "
                f"{proc.returncode} через {died_after:.1f}s -- похоже на "
                "конфликт bind, ретраю", file=sys.stderr,
            )
        if time.time() >= deadline:
            _proc = None  # мёртвый процесс -- не оставляем ничейный ЖИВОЙ хэндл
            raise RuntimeError(
                f"mitmdump (попытка {attempt}) завершился кодом {proc.returncode} "
                f"через {died_after:.1f}s, не начав слушать порт {_PORT} -- "
                f"похоже на конфликт bind (либо иная мгновенная ошибка "
                f"запуска -- битый .mitm/неверный флаг; проверьте stderr "
                f"процесса вручную), ретраи исчерпаны за "
                f"{_START_RETRY_BUDGET}s (AT-BUG-043)"
            )
        time.sleep(_START_RETRY_BACKOFF)


def start_replay(flows_file: Path) -> None:
    """Поднимает mitmdump, отдавая записанные флоу приложению. Блокируется до тех
    пор, пока порт не начнёт слушаться (см. `_spawn_and_wait_listening` —
    AT-BUG-043).

    Флаги подобраны на закрытии спайка B:
      server_replay_reuse=true — один и тот же ответ на повторные запросы (страница
        AO3 тянет ассеты многократно);
      server_replay_extra=forward — незаписанные запросы уходят на живой сервер
        (без него они падают 404 и ломают загрузку);
      connection_strategy=lazy — не открывать соединение к серверу, пока не понадобится.
    """
    global _proc
    _proc = _spawn_and_wait_listening([
        *_mitmdump(), "--listen-host", "0.0.0.0", "--listen-port", _PORT,
        "--server-replay", str(flows_file),
        "--set", "server_replay_reuse=true",
        "--set", "server_replay_extra=forward",
        "--set", "connection_strategy=lazy",
        "-q",
    ], _READY_TIMEOUT)
    _assert_own_listener()


def wait_device_proxy_reachable(timeout: float | None = None) -> None:
    """AT-BUG-017: `_spawn_and_wait_listening` (см. выше) проверяет ГОТОВНОСТЬ
    mitmdump только на ХОСТ-порту — недостаточно. `replay`-фикстура зовёт
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
    и в `start_replay` (одна поверхность отказа, два места запуска).
    Использует `_spawn_and_wait_listening` (AT-BUG-043) — тот же ретрай на
    конфликт bind, что `start_replay`; классовая полнота, не только
    `start_replay`."""
    global _proc
    _proc = _spawn_and_wait_listening([
        *_mitmdump(), "--listen-host", "0.0.0.0", "--listen-port", _PORT,
        "-w", str(flows_file), "-q",
    ], _READY_TIMEOUT)
    _assert_own_listener()


def stop() -> None:
    """Останавливает mitmdump и ждёт реального завершения процесса (не только
    terminate()) — иначе следующий start_replay/start_record того же прогона
    может застать порт ещё занятым уходящим процессом (WinError 10048).

    AT-BUG-043: после подтверждённого завершения процесса дополнительно
    ждёт (`_wait_port_released`), пока порт РЕАЛЬНО не станет доступен для
    нового bind() — `Popen.wait()` на Windows может сигнализировать код
    завершения процесса раньше, чем ОС закончит асинхронное освобождение
    сокета/порта; следующий `start_replay()`/`start_record()` того же
    pytest-процесса иначе мог поймать WinError 10048 в этом узком окне.

    ИНВАРИАНТ (attempt 2, критик-вход, блокер 1): `stop()` НИКОГДА не
    бросает исключение из-за неосвобождённого порта — `_wait_port_released`
    больше не бросает `TimeoutError` (см. её докстринг), только пишет
    предупреждение в stderr и возвращается. Это гарантирует, что вызывающий
    teardown (`conftest.py::replay`) достижим до `clear_device_proxy()`
    независимо от исхода ожидания порта; `try/finally` вокруг `stop()`/
    `clear_device_proxy()` в `conftest.py` — дополнительный (не
    единственный) слой защиты на случай ДРУГИХ будущих исключений отсюда
    (например, из `terminate()`/`wait()` выше)."""
    global _proc
    if _proc is not None:
        _proc.terminate()
        try:
            _proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _proc.kill()
            _proc.wait(timeout=5)
        _proc = None
        _wait_port_released(int(_PORT))


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


def get_device_proxy() -> str:
    """Читает ТЕКУЩЕЕ значение `global http_proxy` устройства
    (`adb shell settings get global http_proxy`) — сырой вывод adb,
    обрезанный по краям (`"null"` — настройка никогда не выставлялась;
    `":0"` — штатное «снято»; иначе — выставленный прокси, например
    `10.0.2.2:8080`). Тот же конечный `timeout`/`TimeoutError`-паттерн, что
    `set_device_proxy`/`clear_device_proxy` (AT-BUG-009) — используется
    fail-safe проверкой AT-BUG-064 (`ensure_no_residual_proxy`)."""
    cmd = [settings.ADB, "shell", "settings", "get", "global", "http_proxy"]
    try:
        cp = subprocess.run(
            cmd, capture_output=True, text=True, check=False,
            timeout=settings.ADB_SHELL_TIMEOUT,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(
            f"adb shell settings get http_proxy (get_device_proxy) не "
            f"ответил за {settings.ADB_SHELL_TIMEOUT}s (AT-BUG-064)"
        ) from exc
    return cp.stdout.strip()


def ensure_no_residual_proxy() -> str | None:
    """AT-BUG-064, кандидат фикса (а): fail-safe снятие ОСТАТОЧНОГО
    device-прокси на подъёме окружения/сессии.

    `set_device_proxy()` выставляет persistent Android-настройку (`settings
    put global http_proxy`), которая переживает snapshot-boot эмулятора, если
    снапшот был сохранён/восстановлен с уже выставленным прокси — типовой
    путь: worker/pytest-сессия аварийно завершилась МЕЖДУ `set_device_proxy()`
    и `clear_device_proxy()` (hard-kill процесса, креш машины — НЕ штатное
    Python-исключение; `try/finally` вокруг них в `conftest.py::replay`
    (AT-BUG-043 attempt 2) покрывает только штатные исключения ВНУТРИ живого
    Python-процесса, не эти случаи). Следующий live-прогон на таком
    устройстве ловит `net::ERR_PROXY_CONNECTION_FAILED` — ДАЖЕ если ни один
    replay-тест не выполнялся в текущей сессии (наблюдение RUN-20260811-0405:
    фикстура `replay` ни разу не инстанцировалась, прокси уже стоял на
    свежем буде).

    Читает текущее значение (`get_device_proxy`) и, если оно НЕ «чистое»
    (не пусто, не `"null"`, не `":0"`), снимает его (`clear_device_proxy()`)
    и возвращает СТАРОЕ значение — вызывающий код (`conftest.py`) решает, как
    это залогировать. Возвращает `None`, если устройство уже было чистым
    (ничего не сделано — счастливый путь, дешёвый: одно adb-чтение, без
    записи)."""
    current = get_device_proxy()
    if current in ("", "null", ":0"):
        return None
    clear_device_proxy()
    return current
