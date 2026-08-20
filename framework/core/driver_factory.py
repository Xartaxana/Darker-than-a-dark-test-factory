"""Создание и закрытие сессии Appium. Ядро не знает об экранах приложения."""
from __future__ import annotations

import ctypes
import json
import os
import re
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from appium import webdriver
from appium.webdriver.client_config import AppiumClientConfig

from framework.config import capabilities, settings
from framework.core import adb

_TASKS_PS1 = settings.REPO_ROOT / "scripts" / "tasks.ps1"
# AT-BUG-063 (F1/F4, rework attempt 2): состояние, которое `scripts/tasks.ps1
# ::Start-Emulator` пишет СРАЗУ после разрешения `-Gpu`/`-AvdName` (параметр >
# env > дефолт) -- единственный способ recovery узнать РЕАЛЬНО действующие
# значения, включая случай явного CLI-параметра МИМО переменной окружения
# (критик-вход attempt 2, воспроизведённый сценарий RUN-20260811-0405).
_EMULATOR_SESSION_STATE_FILE = settings.REPO_ROOT / "state" / "emulator-session.json"
# Реальный список GPU-бэкендов, используемых в этом проекте (tasks.ps1:178-182,
# docs/environment-setup.md "Полный canary-регресс", bugs/AT-BUG-021.md) --
# белый список, не character-escaping: значение вне списка молча отбрасывается
# (recovery падает на дефолт tasks.ps1), а не передаётся дальше непроверенным.
_VALID_GPU_BACKENDS = frozenset({"host", "swiftshader_indirect", "angle_indirect"})
# AVD-имена в этом проекте — простые идентификаторы (ao3_test_api34/29/26,
# AT-BUG-024/028); регекс, а не закрытый enum, чтобы новый AVD не требовал
# правки этого файла -- но пробел/`;`/кавычка/что угодно небезопасное для
# аргумента отбрасываются так же, как невалидный GPU-бэкенд.
_AVD_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
# AT-BUG-026, находка красной пробы w1 (2026-07-28, живое устройство): сразу
# после Start-Emulator (boot_completed=1 уже подтверждён) `adb install`
# иногда падает `NullPointerException: StorageManager.getVolumes() on a null
# object reference` — гостевой storage/vold-сервис ещё не settled. Сиблинг
# класса AT-BUG-013 (`_wait_package_service_ready` покрывает ТОЛЬКО готовность
# `pm path android`, эта гонка проявляется на шаг позже — во время самой
# установки, которую `_wait_package_service_ready` не перепроверяет). Bounded
# retry — тот же класс решения, что и весь остальной модуль (конечный, не
# бесконечный), НЕ новый самодельный поллинг getprop (мы не ждём boot заново,
# только даём storage-сервису ещё немного времени settled'иться).
_APP_VERIFY_RETRIES = 3
_APP_VERIFY_BACKOFF = 5.0
# AT-BUG-026, та же красная проба: ПЕРВАЯ Appium-сессия сразу после recovery
# иногда не успевает settle — `WebDriverException: Appium Settings app is not
# running after 30000ms` (класс уже задокументирован в истории этого бага,
# `bugs/AT-BUG-026.md`: «первая Appium-сессия после рестарта не успела
# settle»). Бounded доп.попытки — ТОЛЬКО когда вызывающий код (`driver`
# фикстура) явно просит (`settle_retries>0`, т.е. recovery только что
# произошёл в ЭТОМ тесте) — обычный путь (recovery не требовался) поведение
# НЕ меняет.
_SETTLE_RETRY_BACKOFF = 15.0
# ~300s: Start-Emulator (буд с фолбэком -no-snapshot-load на этом хосте,
# AT-BUG-012) + Install-MitmCA (bash-скрипт, remount /system+/apex, рестарт
# framework) — оба шага исполняются ОДНИМ вызовом `-WritableSystem`, суммарно
# исторически укладываются в единицы минут; запас на порядок над обычным
# happy-path буда, тот же класс решения, что и остальные конечные таймауты
# этого модуля/adb.py (AT-BUG-007/009).
_EMULATOR_RESTART_TIMEOUT = 300.0

# spec-p3-second-emulator N3: машинная лиза device-стека. Файл ОТДЕЛЬНЫЙ на
# стек (`state/device-lease-<N>.json`, зеркалит `tasks.ps1::Use-DeviceStack` —
# ОДНА семантика статуса, ДВЕ реализации: PS для взятия/`-Release`, Python
# здесь — для ЧОКПОИНТА на пути исполнения прогона, B14 плана). Порт
# APPIUM_URL определяет стек (4723=1, 4725=2) — незнакомый порт (легаси/
# кастомный вызов, НЕ мигрированный на Use-DeviceStack) молча пропускает
# чокпоинт целиком (back-compat: носители, не перечисленные в owns N3,
# продолжают работать по стеку 1 без правок, план N3 "Носители Invoke-Pytest,
# не взятые в owns N3... продолжают работать по стеку 1 без правок").
_DEVICE_LEASE_STACK_PORTS = {1: 4723, 2: 4725}
# Окна — ОЦЕНКА (F-30, docs/tasks/p3-second-emulator.md N3), НЕ замер;
# калибруется живыми прогонами N2/N4. Идентичны PS-стороне
# (`tasks.ps1::$_DEVICE_LEASE_*_SECONDS`) — сверены юнитами обеих сторон на
# одинаковых входах (scripts/tests/test_p3_device_lease_status.py +
# framework/tests/test_device_lease_checkpoint_unit.py).
_DEVICE_LEASE_GRACE_SECONDS = 600.0
_DEVICE_LEASE_IDLE_SECONDS = 1800.0
_DEVICE_LEASE_TTL_SECONDS = 14400.0

_LEASE_FREE = "free"
_LEASE_ACTIVE = "active"
_LEASE_IDLE = "idle"
_LEASE_RECLAIMED = "reclaimed"

# Non-blocker 6 (критик-раунд 2): чтение файла лизы конкурирует с ЭКСКЛЮЗИВНЫМ
# хэндлом `tasks.ps1::Take-DeviceLeaseSlot` (FileMode.Open, FileShare.None) —
# на Windows это ловится как `PermissionError`/WinError 32, а НЕ как
# `FileNotFoundError`. Без ретрая окно take-лока читалось как «лизы нет
# вовсе» — на стеке 2 это ЛОЖНЫЙ `DeviceLeaseInvalidStackError` («возьми
# Use-DeviceStack -N 2») прямо посреди штатного взятия соседним процессом.
_LEASE_READ_RETRIES = 3
_LEASE_READ_RETRY_DELAY = 0.1

# БЛОКЕР B-R4-1 (критик-раунд 4): решение чокпоинта и штамп PID обязаны быть
# ОДНОЙ атомарной операцией — read->decide->os.replace без замка давал
# нескольким ОДНОВРЕМЕННЫМ процессам пройти арбитра (замер r4_simul: 4 из 4 в
# одном раунде). Замок — sidecar-файл `<лиза>.lock` через O_CREAT|O_EXCL
# (единственный атомарный примитив, доступный обеим платформам без новых
# зависимостей; зеркалит роль эксклюзивного FileShare.None-хэндла PS-стороны
# `Take-DeviceLeaseSlot`). Смерть держателя не оставляет замок навечно:
# stale-break по мёртвому PID держателя ЛИБО возрасту замка (см.
# `_break_stale_cas_lock`). Розыгрыш после stale-break честный: break — только
# unlink, победителя определяет ПОВТОРНЫЙ O_EXCL-create.
# Остаточный риск (named): замок арбитрирует python-vs-python (сценарий
# блокера — N одновременных чокпоинтов); PS-сторона в замке не участвует —
# её взятие защищено собственным эксклюзивным хэндлом, а окно
# «PS переписал лизу между нашим чтением и записью» требует одновременного
# ручного Use-DeviceStack ПОД уже идущим прогоном того же владельца и в
# худшем случае перештамповывает heartbeat той же лизы.
_LEASE_CAS_RETRIES = 40
_LEASE_CAS_RETRY_DELAY = 0.05
_LEASE_CAS_STALE_SECONDS = 10.0


class DeviceLeaseError(RuntimeError):
    """N3: чужая лиза блокирует прогон на этом device-стеке. НЕ `ENV_ISSUE`
    (это не поломанная среда — это конфликт ВЛАДЕНИЯ живым/недавно живым
    устройством) — маркер `DEVICE_LEASE_BLOCKED` в начале сообщения
    (greppable, тот же дух, что `ENV_ISSUE`): для test-runner промпта это
    класс `Blocked`, НЕ красный кейс (план N3, «Поведение вызывающего при
    отказе»)."""


class DeviceLeaseInvalidStackError(RuntimeError):
    """N3: стек 2 требует лизу БЕЗУСЛОВНО (асимметричный дефолт B27/B18) —
    лиза отсутствует ЛИБО истекла (reclaimed), а Use-DeviceStack -N 2 никто
    не запускал. Отдельный класс от `DeviceLeaseError` (там — конфликт с
    ЖИВЫМ чужим владельцем; здесь — лизы просто НЕТ ни у кого), оба —
    подклассы `DeviceLeaseError`-семьи по духу, но НЕ должны маскировать
    друг друга при отладке; message несёт тот же `DEVICE_LEASE_BLOCKED`
    маркер (test-runner трактует ОБА как Blocked)."""


def _device_lease_file(stack: int):
    return settings.REPO_ROOT / "state" / f"device-lease-{stack}.json"


def _warn_lease(message: str) -> None:
    """Диагностика N3-лизы. Отдельная от `_warn_recovery` (та подписывается
    `AT-BUG-063 recovery:` — совсем другой механизм, чужой префикс в логе
    лизы сбивал бы разбор). `stderr` по тем же причинам, что там: попадает и
    в Captured-секцию отчёта, и в Allure-аттачмент."""
    print(f"p3-N3 device-lease: {message}", file=sys.stderr)


_DEVICE_LEASE_STACK_DEVICES = {1: "emulator-5554", 2: "emulator-5556"}


def _coerce_lease_pid(raw):
    """Non-blocker 3 (критик-раунд 2): `pytest_pid` приходит из JSON и НЕ обязан
    быть числом (руками правленный файл, оборванная запись, чужая версия схемы
    дают строку/список/словарь/`true`). Раньше такое значение доезжало до
    `pid <= 0` в `_is_pid_alive` и падало `TypeError: '<=' not supported
    between instances of 'str' and 'int'` ПОСРЕДИ чокпоинта — прогон
    заклинивало до ручного `Use-DeviceStack -Release`.

    Контракт: не-число (и не-положительное) = «pid отсутствует» — ровно тот же
    исход, что `"pytest_pid": null` (стартовое grace-окно / idle по возрасту).
    Симметрично PS-стороне (`tasks.ps1::Resolve-DeviceLeasePid`). `bool`
    отсекается отдельно: `int(True) == 1` — валидный PID 1, а JSON `true`
    заведомо не PID."""
    if raw is None or isinstance(raw, bool):
        return None
    try:
        pid = int(raw)
    except (TypeError, ValueError):
        return None
    return pid if pid > 0 else None


def _is_pid_alive(pid) -> bool:
    """N3 B1 (критик-вход rework attempt 2): живость `pytest_pid` лизы.

    НЕ `os.kill(pid, 0)` на Windows: Python транслирует ЛЮБОЙ `sig`, кроме
    `CTRL_C_EVENT`/`CTRL_BREAK_EVENT`, в `TerminateProcess(handle, sig)`
    (документированное поведение stdlib на этой платформе) — `sig=0` РЕАЛЬНО
    завершил бы процесс вместо проверки существования, катастрофа для
    read-only liveness-чека. `OpenProcess` с
    `PROCESS_QUERY_LIMITED_INFORMATION` — чисто read-only хэндл, ничего не
    меняет; `NULL`-хэндл = процесс не существует (или недоступен — трактуем
    консервативно "не подтверждена жизнь = мертва", не ждём вечно чужого
    пользователя). Без новой зависимости psutil (requirements.txt её не
    несёт, заводить ради одной проверки нежелательно). Нестандартный `os.name`
    (не 'nt', гипотетический не-Windows прогон) — POSIX-путь `os.kill(pid, 0)`
    легален (задокументированное no-op-поведение sig=0 на POSIX).

    Non-blocker 7 (критик-раунд 2) — ПРИНЯТЫЙ ОСТАТОЧНЫЙ РИСК, не недосмотр:
    переиспользованный ОС номер PID (Windows перевыдаёт номера агрессивно)
    держит лизу в статусе `active` до TTL 4ч — сверки ВРЕМЕНИ СТАРТА процесса
    против штампа лизы здесь НЕТ. Её пришлось бы завести полем схемы лизы
    (`pytest_pid_started_utc`), писать здесь через `GetProcessTimes`/ctypes и
    сверять на PS-стороне `Get-Process .StartTime` с допуском на формат и
    часовой пояс — новая поверхность отказа В ОБЕИХ реализациях ради проблемы,
    чьё ПОСЛЕДСТВИЕ fail-safe: ложно-живой PID БЛОКИРУЕТ взятие/адопцию, а НЕ
    выдаёт устройство двум прогонам, и эскейп-хэтч (`Use-DeviceStack -Release`)
    назван в самом сообщении отказа. Симметричный комментарий —
    `tasks.ps1::Test-DeviceLeasePidAlive`."""
    pid = _coerce_lease_pid(pid)
    if pid is None:
        return False
    if os.name != "nt":
        try:
            os.kill(int(pid), 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True  # процесс существует, просто не наш пользователь
        except OSError:
            return False
        return True
    process_query_limited_information = 0x1000
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    handle = kernel32.OpenProcess(process_query_limited_information, False, int(pid))
    if not handle:
        return False
    kernel32.CloseHandle(handle)
    return True


def _detect_device_lease_stack() -> int | None:
    """N3 B5 (критик-вход rework attempt 2 — ПЕРЕПИСАНО): стек по
    `settings.APPIUM_URL`/`settings.DEVICE_NAME`; незнакомые ОБА -> `None`
    (легаси/кастомный вызов, лиза НЕ участвует, back-compat).

    РАНЬШЕ детекция смотрела ТОЛЬКО на хвост строки APPIUM_URL
    (`.endswith(f":{port}")`) — `http://127.0.0.1:4725/wd/hub` (валидный
    APPIUM_URL с путём) не заканчивается на ":4725", детекция молча
    возвращала `None`, и стек 2 проходил чокпоинт БЕЗ ЛИЗЫ ВООБЩЕ (дыра в
    асимметричном B27-дефолте, который весь смысл в том, чтобы стек 2 НИКОГДА
    не работал без лизы). Порт теперь читается через `urlparse(...).port`
    (устойчив к любому хвосту пути/query).

    Дополнительно сверяем `AO3_DEVICE` (`settings.DEVICE_NAME`) — стек
    однозначно определяется и по устройству, независимо от формы URL. Если
    ОБА сигнала известны, но называют РАЗНЫЕ стеки, окружение
    сконфигурировано несогласованно (например `AO3_DEVICE=emulator-5556`
    при всё ещё `APPIUM_URL=...:4723`) — явный отказ, чокпоинт не угадывает."""
    port = urlparse(settings.APPIUM_URL).port
    stack_by_port = next((s for s, p in _DEVICE_LEASE_STACK_PORTS.items() if p == port), None)
    device_name = getattr(settings, "DEVICE_NAME", None)
    stack_by_device = next((s for s, d in _DEVICE_LEASE_STACK_DEVICES.items() if d == device_name), None)

    if stack_by_port is None and stack_by_device is None:
        return None
    if stack_by_port is not None and stack_by_device is not None and stack_by_port != stack_by_device:
        raise DeviceLeaseError(
            "DEVICE_LEASE_BLOCKED (p3-second-emulator N3, B5): рассинхрон AO3_DEVICE "
            f"({device_name!r} -> стек {stack_by_device}) и APPIUM_URL "
            f"({settings.APPIUM_URL!r} -> стек {stack_by_port}) — окружение сконфигурировано "
            "непоследовательно, чокпоинт отказывается угадывать стек. Проверь Use-DeviceStack -N "
            "и переменные окружения перед повтором."
        )
    return stack_by_device if stack_by_device is not None else stack_by_port


def _parse_lease_timestamp(raw) -> datetime | None:
    if not raw or not isinstance(raw, str):
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


_LEASE_ABSENT_MISSING = ""
_LEASE_ABSENT_LOCKED = "locked"
_LEASE_ABSENT_CORRUPT = "corrupt"


def _read_device_lease(stack: int) -> dict | None:
    """Тонкая обёртка над `_read_device_lease_with_reason` для вызывающих,
    которым причина отсутствия не нужна."""
    return _read_device_lease_with_reason(stack)[0]


def _read_device_lease_with_reason(stack: int) -> tuple[dict | None, str]:
    """Отсутствующий/нечитаемый/битый файл — штатный случай ("free"),
    аналог `_read_emulator_session_state` (AT-BUG-063): диагностика через
    `_warn_recovery` (stderr, попадает в Allure-аттачмент), НЕ throw —
    вызывающий код (`_device_lease_checkpoint`) сам решает семантику
    отсутствующей лизы по стеку.

    Non-blocker 6 (критик-раунд 2): sharing violation ОТЛИЧАЕТСЯ от отсутствия
    файла. `FileNotFoundError` — честное «лизы нет». `PermissionError`/WinError
    32/33 — ФАЙЛ ЕСТЬ, его прямо сейчас держит эксклюзивно
    `Take-DeviceLeaseSlot` соседнего процесса (окно единицы миллисекунд):
    ретраим `_LEASE_READ_RETRIES` раз по `_LEASE_READ_RETRY_DELAY`, и только
    исчерпав — WARN + «трактуется как отсутствующая». Без этого окно take-лока
    давало на стеке 2 ЛОЖНЫЙ отказ «лиза отсутствует — возьми Use-DeviceStack
    -N 2» поверх штатно берущегося стека.

    Мелкий пункт 2 (критик-раунд 3): возвращает ПРИЧИНУ отсутствия
    (`_LEASE_ABSENT_*`), чтобы отказ стека 2 называл ИСТИННЫЙ повод, а не
    только «лизы нет». Прежде исчерпанный sharing violation попадал в WARN
    (легко потерять), а пользователь получал совет «возьми Use-DeviceStack
    -N 2» — ровно то, чего делать НЕ надо, когда файл занят конкурентом."""
    path = _device_lease_file(stack)
    raw = None
    for attempt in range(_LEASE_READ_RETRIES):
        try:
            raw = path.read_text(encoding="utf-8-sig")
            break
        except FileNotFoundError:
            return None, _LEASE_ABSENT_MISSING
        except OSError as exc:
            transient = isinstance(exc, PermissionError) or getattr(exc, "winerror", None) in (32, 33)
            if transient and attempt < _LEASE_READ_RETRIES - 1:
                time.sleep(_LEASE_READ_RETRY_DELAY)
                continue
            _warn_lease(
                f"лиза стека {stack} ({path}) нечитаема "
                f"({type(exc).__name__}: {exc}"
                f"{'; sharing violation не разошёлся за %d попыток' % _LEASE_READ_RETRIES if transient else ''})"
                " — трактуется как отсутствующая."
            )
            return None, (_LEASE_ABSENT_LOCKED if transient else _LEASE_ABSENT_CORRUPT)
    if raw is None:
        return None, _LEASE_ABSENT_MISSING
    try:
        data = json.loads(raw)
    except ValueError as exc:
        _warn_lease(
            f"лиза стека {stack} ({path}) содержит битый JSON "
            f"({type(exc).__name__}: {exc}) — трактуется как отсутствующая."
        )
        return None, _LEASE_ABSENT_CORRUPT
    if not isinstance(data, dict):
        return None, _LEASE_ABSENT_CORRUPT
    return data, ""


def _lease_status(lease: dict | None, now: datetime, pid_alive_fn=None) -> str:
    """N3 B1 (критик-вход rework attempt 2 — ПЕРЕПИСАНО): статус лизы
    {free|active|idle|reclaimed} — ЧИСТАЯ функция, зеркалит
    `tasks.ps1::Get-DeviceLeaseStatus` (ОДНА семантика, ДВЕ реализации,
    сверено юнитами обеих сторон на одинаковых входах).

    Переход active->idle РАНЬШЕ не был реализован: поле `status` лизы
    ВСЕГДА писалось `"active"` (heartbeat/reclaim), НИКТО не переводил его
    в `"idle"`, а живость `pytest_pid` не проверялась вовсе — статус ТЕПЕРЬ
    вычисляется ЧИТАТЕЛЕМ по факту живости процесса (`pid_alive_fn`, дефолт
    `_is_pid_alive`, инжектируемый для юнитов); поле `status` в самом файле
    лизы — чисто диагностическое, эта функция его больше не читает.

    Алгоритм:
    - `pytest_pid` ЖИВ (`pid_alive_fn` -> True) и `age <= TTL` -> `active`
      (TTL — верхняя страховка для ДОЛГОЖИВУЩЕГО процесса между отдельными
      `create_driver`, не грейс-окно старта).
    - `pytest_pid` ОТСУТСТВУЕТ (лиза только что взята, `create_driver` ещё
      ни разу не вызывался) и `age <= Grace` -> `active` (короткое стартовое
      окно, короче Idle/TTL).
    - ИНАЧЕ (pid мёртв, ИЛИ отсутствует-за-грейсом, ИЛИ жив-но-heartbeat-
      протух-за-TTL) -> `idle`, пока `age <= Idle`, дальше `reclaimed`.
      Idle-окно ВСЕГДА меряется от `heartbeat_utc` (или `taken_utc`-
      фолбэка) — момент фактической смерти процесса неизвестен, только
      последний heartbeat."""
    if lease is None:
        return _LEASE_FREE
    pid_alive_fn = pid_alive_fn or _is_pid_alive
    last = _parse_lease_timestamp(lease.get("heartbeat_utc")) or _parse_lease_timestamp(lease.get("taken_utc"))
    if last is None:
        return _LEASE_FREE
    age = (now - last).total_seconds()
    # Non-blocker 3: не-числовой `pytest_pid` нормализуется в None
    # («отсутствует») ДО любого использования — раньше он падал TypeError
    # внутри `_is_pid_alive` и ронял чокпоинт.
    pytest_pid = _coerce_lease_pid(lease.get("pytest_pid"))
    if pytest_pid is not None and pid_alive_fn(pytest_pid):
        if age <= _DEVICE_LEASE_TTL_SECONDS:
            return _LEASE_ACTIVE
        # жив, но heartbeat не обновлялся дольше TTL - падает в idle/reclaimed ниже
    elif pytest_pid is None and age <= _DEVICE_LEASE_GRACE_SECONDS:
        return _LEASE_ACTIVE
    return _LEASE_RECLAIMED if age > _DEVICE_LEASE_IDLE_SECONDS else _LEASE_IDLE


def _write_device_lease(stack: int, lease: dict) -> None:
    """N3 B3 (критик-вход rework attempt 2): атомарная запись (темп-файл +
    `os.replace` — атомарен на Windows тоже, `MoveFileEx` с
    `MOVEFILE_REPLACE_EXISTING` со времён Python 3.3). Раньше
    `path.write_text(...)` писал НЕАТОМАРНО: читатель, попавший на середину
    записи, видел партиальный/битый JSON и ошибочно трактовал живую лизу как
    "битую -> free" — тот же класс риска, что критик воспроизвёл на
    PS-стороне (двойная/тройная выдача при неатомарной RMW)."""
    path = _device_lease_file(stack)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}-{uuid.uuid4().hex[:8]}")
    tmp.write_text(json.dumps(lease), encoding="utf-8")
    os.replace(tmp, path)


def _heartbeat_device_lease(stack: int, lease: dict, now: datetime) -> None:
    """Обновляет `heartbeat_utc`/`pytest_pid` (ТЕКУЩИЙ процесс — heartbeat
    фактический, N3: "timestamp обновляется на КАЖДОМ create_driver") и
    ставит `status="active"` (B28: своя idle-лиза принимается и
    возвращается в active тем же ходом; сам статус, читаемый ОБРАТНО,
    теперь вычисляется по pid-живости — см. `_lease_status` — поле здесь
    чисто диагностическое). N3 B5 (критик-вход rework attempt 2): пишет
    `device`/`appium_url` — диагностический след того, ЧЕМ фактически была
    взята/обновлена эта лиза (сверяется человеком при разборе рассинхрона,
    см. `_detect_device_lease_stack`). Отказ записи — WARN, НЕ роняет прогон
    (тот же fail-soft дух, что PS-сторона: heartbeat — страховка, не гейт
    присутствия устройства)."""
    updated = dict(lease)
    updated["heartbeat_utc"] = now.isoformat()
    updated["pytest_pid"] = os.getpid()
    updated["status"] = _LEASE_ACTIVE
    updated["device"] = settings.DEVICE_NAME
    updated["appium_url"] = settings.APPIUM_URL
    try:
        _write_device_lease(stack, updated)
    except OSError as exc:
        _warn_lease(
            f"heartbeat лизы стека {stack} не записан "
            f"({type(exc).__name__}: {exc}) — не блокирует прогон."
        )


def _current_owner_label() -> str:
    """Метка владельца тикета — ДОСЛОВНО та же формула, что PS-сторона
    (`tasks.ps1::Use-DeviceStack`: `"$env:USERNAME@$env:COMPUTERNAME"`).
    Фолбэки (`getpass`/`socket`) — для гипотетической среды без этих
    переменных; на Windows-хосте конвейера обе всегда заданы."""
    user = os.environ.get("USERNAME") or ""
    host = os.environ.get("COMPUTERNAME") or ""
    if not user:
        import getpass
        try:
            user = getpass.getuser()
        except Exception:  # noqa: BLE001 — метка владельца не должна ронять прогон
            user = "unknown"
    if not host:
        import socket
        host = socket.gethostname()
    return f"{user}@{host}"


def _same_appium_endpoint(a, b) -> bool:
    """Сравнение APPIUM_URL по (хост, порт), не по строке: `http://127.0.0.1:4725`
    и `http://127.0.0.1:4725/wd/hub` — ОДИН И ТОТ ЖЕ сервер (форма с `/wd/hub`
    реально встречается, см. докстринг `_detect_device_lease_stack`), а
    строковое сравнение объявило бы их разными и запретило бы адопцию на
    ровном месте."""
    if not a or not b or not isinstance(a, str) or not isinstance(b, str):
        return False
    pa, pb = urlparse(a), urlparse(b)
    return (pa.hostname, pa.port) == (pb.hostname, pb.port)


def _can_adopt_lease(lease: dict, pid_alive_fn=None) -> tuple[bool, str]:
    """БЛОКЕР B-R2-1 (критик-раунд 2): можно ли чокпоинту ПРОДОЛЖИТЬ чужой по
    env-токену, но СВОЙ по владельцу тикет.

    Мотив: `Use-DeviceStack` выполняется в процессе А (одноразовый powershell),
    а pytest живёт в процессе Б — `$env:AO3_DEVICE_LEASE_TOKEN` в Б НЕ
    наследуется, и лиза, взятая секунду назад тем же человеком на той же
    машине для того же устройства, читалась как «чужая АКТИВНАЯ» →
    `DeviceLeaseError`. Критик воспроизвёл ровно это.

    Условия адопции (ВСЕ обязательны, любое несовпадение → прежние отказы):
      1. `owner_label` лизы == текущему (`user@host`);
      2. `device` лизы == `settings.DEVICE_NAME` И `appium_url` лизы == текущему
         `settings.APPIUM_URL` (по хосту+порту) — лиза, взятая ДЛЯ ДРУГОГО
         устройства/сервера, НЕ наша, сколько бы ни совпадала метка владельца;
      3. `pytest_pid` отсутствует / мёртв / это МЫ САМИ (адопция уже
         состоялась на предыдущем `create_driver` этого же процесса —
         без этой ветки второй `create_driver` отказал бы сам себе,
         увидев собственный ЖИВОЙ pid как «чужой живой прогон»).

    Возвращает `(можно, причина_отказа)` — причина попадает в диагностику,
    чтобы «почему не адоптировалось» не приходилось угадывать."""
    pid_alive_fn = pid_alive_fn or _is_pid_alive
    if lease.get("owner_label") != _current_owner_label():
        return False, f"owner_label лизы ({lease.get('owner_label')!r}) != текущего ({_current_owner_label()!r})"
    lease_device = lease.get("device")
    if lease_device != settings.DEVICE_NAME:
        return False, f"device лизы ({lease_device!r}) != текущего settings.DEVICE_NAME ({settings.DEVICE_NAME!r})"
    if not _same_appium_endpoint(lease.get("appium_url"), settings.APPIUM_URL):
        return False, (
            f"appium_url лизы ({lease.get('appium_url')!r}) != текущего "
            f"settings.APPIUM_URL ({settings.APPIUM_URL!r})"
        )
    pid = _coerce_lease_pid(lease.get("pytest_pid"))
    if pid is not None and pid != os.getpid() and pid_alive_fn(pid):
        return False, f"pytest_pid={pid} ЖИВ — под лизой идёт настоящий прогон"
    return True, ""


def _break_stale_cas_lock(lock_path) -> None:
    """B-R4-1: замок, переживший своего держателя, ломается — иначе смерть
    процесса под замком заклинила бы чокпоинт до ручного вмешательства.
    Критерии стейла (любой достаточен): PID держателя мёртв; возраст замка
    больше `_LEASE_CAS_STALE_SECONDS` (весь критический участок — одно чтение
    + одна запись файла, десятки миллисекунд; 10с — запас на два порядка);
    замок нечитаем/битый И его mtime старше того же окна. Break = ТОЛЬКО
    unlink: победителя следующего розыгрыша определяет повторный
    O_EXCL-create, поэтому двое сломавших один стейл не проходят оба."""
    try:
        raw = lock_path.read_text(encoding="utf-8")
        holder = json.loads(raw)
    except (OSError, ValueError):
        holder = None
    stale = False
    if isinstance(holder, dict):
        holder_pid = _coerce_lease_pid(holder.get("pid"))
        taken = _parse_lease_timestamp(holder.get("taken_utc"))
        age = (datetime.now(timezone.utc) - taken).total_seconds() if taken else None
        stale = (holder_pid is None or not _is_pid_alive(holder_pid)) or (
            age is not None and age > _LEASE_CAS_STALE_SECONDS)
    else:
        try:
            mtime_age = time.time() - lock_path.stat().st_mtime
            stale = mtime_age > _LEASE_CAS_STALE_SECONDS
        except OSError:
            return  # исчез сам — следующий O_EXCL-create разыграет заново
    if stale:
        try:
            lock_path.unlink()
        except OSError:
            pass  # конкурент сломал первым — розыгрыш всё равно через O_EXCL


def _release_cas_lock_if_owned(lock_path) -> None:
    """Снятие замка ТОЛЬКО при подтверждённом владении (критик-раунд 5,
    fixes[1]): после age-взлома живого-но-замороженного держателя его finally
    иначе снимал бы ЧУЖОЙ замок — один взлом каскадировал в полную потерю
    взаимного исключения (замер r5_stale2: третий процесс входил мгновенно).
    Нечитаемый/чужой замок НЕ трогаем — его доломает stale-break следующего
    претендента (заклинивания нет)."""
    try:
        holder = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if not (isinstance(holder, dict)
            and _coerce_lease_pid(holder.get("pid")) == os.getpid()):
        return
    try:
        lock_path.unlink()
    except OSError:
        pass


@contextmanager
def _device_lease_cas_lock(stack: int):
    """B-R4-1: критическая секция «прочитал лизу -> решил -> заштамповал».
    Захват — атомарный `os.open(O_CREAT|O_EXCL)` sidecar-файла; занято —
    ретраи с коротким сном и stale-break (см. `_break_stale_cas_lock`).
    Исчерпание ретраев — `DeviceLeaseError` с маркером DEVICE_LEASE_BLOCKED
    (транзиентный отказ: правильное действие — повторить прогон, не лезть в
    файлы руками). Снятие замка — в finally, включая пути исключений
    самого чокпоинта (отказ по чужой лизе не должен держать замок), но
    ТОЛЬКО своего (`_release_cas_lock_if_owned`)."""
    path = _device_lease_file(stack)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    acquired = False
    for attempt in range(_LEASE_CAS_RETRIES):
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, json.dumps({
                    "pid": os.getpid(),
                    "taken_utc": datetime.now(timezone.utc).isoformat(),
                }).encode("utf-8"))
            finally:
                os.close(fd)
            acquired = True
            break
        except FileExistsError:
            _break_stale_cas_lock(lock_path)
            time.sleep(_LEASE_CAS_RETRY_DELAY)
        except OSError as exc:
            # Небитовый сбой ФС (например, каталог только что удалили) —
            # короткий ретрай тем же циклом, дальше честный отказ ниже.
            _warn_lease(
                f"CAS-замок лизы стека {stack}: попытка {attempt + 1} не удалась "
                f"({type(exc).__name__}: {exc}) — ретраю."
            )
            time.sleep(_LEASE_CAS_RETRY_DELAY)
    if not acquired:
        raise DeviceLeaseError(
            "DEVICE_LEASE_BLOCKED (p3-second-emulator N3, B-R4-1): CAS-замок "
            f"чокпоинта стека {stack} ({lock_path}) занят дольше "
            f"{_LEASE_CAS_RETRIES * _LEASE_CAS_RETRY_DELAY:.1f}с — соседний "
            "процесс держит критическую секцию аномально долго. ПОВТОРИ прогон; "
            "если повторяется — проверь зависшие python-процессы и удали замок."
        )
    try:
        yield
    finally:
        _release_cas_lock_if_owned(lock_path)


def _assert_no_foreign_live_run(lease: dict, stack: int) -> None:
    """БЛОКЕР B-R4-2 (критик-раунд 4): токенная ветка (`is_own` по env-токену)
    пропускала предикат живости ВООБЩЕ — прогон Б с унаследованным env-токеном
    проходил чокпоинт ПРИ ЖИВОМ прогоне А и затирал его PID в лизе (замер
    r4_sametoken). Предикат ТОТ ЖЕ, что в `_can_adopt_lease` (условие 3):
    живой `pytest_pid`, и это НЕ МЫ САМИ, — под лизой уже идёт настоящий
    прогон, второй одновременный не легален ни с каким токеном. Легитимные
    пути не страдают: повторный `create_driver` того же процесса видит СВОЙ
    pid; возврат из idle и перезапуск после смерти видят МЁРТВЫЙ pid;
    свежевзятая лиза несёт `pytest_pid=null` (pytest-xdist в проекте не
    используется — сверено критиком раунда 4 позитивно-контролируемым
    поиском)."""
    pid = _coerce_lease_pid(lease.get("pytest_pid"))
    if pid is not None and pid != os.getpid() and _is_pid_alive(pid):
        raise DeviceLeaseError(
            f"DEVICE_LEASE_BLOCKED (p3-second-emulator N3, B-R4-2): под лизой "
            f"стека {stack} УЖЕ ИДЁТ прогон (pytest_pid={pid} жив, это не текущий "
            f"процесс {os.getpid()}) — второй одновременный прогон не допускается "
            "независимо от токена. Дождись завершения либо сними лизу явно: "
            f"Use-DeviceStack -N {stack} -Release."
        )


def _device_lease_checkpoint() -> None:
    """N3 чокпоинт лизы — вызывается КАЖДЫМ `create_driver` (function/
    driver-scoped, B14/B26 плана: героятбит на каждом создании сессии, не
    только на старте сессии pytest). Асимметрия стеков (B18/B27):
    - стек 2 — лиза ОБЯЗАТЕЛЬНА безусловно (`free`/`reclaimed` -> отказ,
      никакого молчаливого auto-take — Use-DeviceStack ЕДИНСТВЕННЫЙ, кто
      берёт/реклеймит лизу; create_driver только ВАЛИДИРУЕТ существующую);
    - стек 1 — отказ ТОЛЬКО при конфликте с ЧУЖОЙ АКТИВНОЙ лизой (легаси-
      совместимость: немигрированные носители работают без лизы вовсе).
    Своя `idle`-лиза (ЛЮБОЙ стек) — принимается, возвращается в `active`
    (B28). Чужая `idle` — отказ с "жди до <момент>" (само ожидание — на
    ВЫЗЫВАЮЩЕМ коде, не здесь: N3 план, "Поведение вызывающего при
    отказе"). Незнакомый порт APPIUM_URL (легаси/кастомный стек) — no-op.

    B-R4-1 (критик-раунд 4): всё решение (чтение -> оценка -> штамп) — под
    CAS-замком `_device_lease_cas_lock`: N одновременных чокпоинтов обязаны
    пропустить РОВНО ОДИН прогон (замер r4_simul до фикса: 4 из 4)."""
    stack = _detect_device_lease_stack()
    if stack is None:
        return
    with _device_lease_cas_lock(stack):
        _device_lease_checkpoint_locked(stack)


def _device_lease_checkpoint_locked(stack: int) -> None:
    """Тело чокпоинта ПОД CAS-замком (B-R4-1) — читает лизу, решает и
    штампует как одна критическая секция; вне замка не вызывать."""
    now = datetime.now(timezone.utc)
    lease, absent_reason = _read_device_lease_with_reason(stack)
    status = _lease_status(lease, now)
    own_token = os.environ.get("AO3_DEVICE_LEASE_TOKEN", "")
    is_own = bool(lease) and bool(own_token) and lease.get("owner_token") == own_token

    # БЛОКЕР B-R2-1: АДОПЦИЯ чокпоинтом. Env-токен отсутствует/не совпадает, но
    # тикет наш по владельцу+устройству и под ним нет ЖИВОГО прогона — штампуем
    # свой PID и heartbeat (`_heartbeat_device_lease` ниже, атомарный
    # `os.replace`) и продолжаем. Это закрывает связку «взял в процессе А →
    # pytest в процессе Б» БЕЗ изменения промптового воркфлоу.
    # Токен кладём и в собственное окружение: следующие `create_driver` этого
    # же процесса пойдут быстрым путём `is_own`, без повторной адопции.
    if lease is not None and not is_own and status in (_LEASE_ACTIVE, _LEASE_IDLE):
        adoptable, why_not = _can_adopt_lease(lease)
        if adoptable:
            is_own = True
            token = lease.get("owner_token")
            if token:
                os.environ["AO3_DEVICE_LEASE_TOKEN"] = str(token)
            _warn_lease(
                f"стек {stack}: лиза ПРОДОЛЖЕНА адопцией (owner_label="
                f"{lease.get('owner_label')!r}, owner_token={token!r}, device="
                f"{lease.get('device')!r}) — env-токен этого процесса не совпадал/отсутствовал, "
                f"живого pytest_pid под лизой нет; штампую свой PID {os.getpid()}."
            )
        else:
            _warn_lease(f"стек {stack}: адопция НЕ применена — {why_not}.")

    if stack == 2:
        if status in (_LEASE_FREE, _LEASE_RECLAIMED):
            # Мелкий пункт 2 (критик-раунд 3): назвать ИСТИННУЮ причину в САМОМ
            # тексте отказа. Файл, занятый конкурентом (sharing violation не
            # разошёлся за все ретраи), — это НЕ «лизы нет»: совет «возьми
            # Use-DeviceStack -N 2» здесь ВРЕДЕН (перетрёт чужое взятие),
            # правильное действие — повторить через секунду.
            if absent_reason == _LEASE_ABSENT_LOCKED:
                raise DeviceLeaseInvalidStackError(
                    "DEVICE_LEASE_BLOCKED (p3-second-emulator N3): файл лизы стека 2 "
                    f"({_device_lease_file(2)}) ЗАНЯТ другим процессом — sharing violation "
                    f"не разошёлся за {_LEASE_READ_RETRIES} попыток ("
                    f"{_LEASE_READ_RETRY_DELAY * 1000:.0f} мс каждая). Лиза, скорее всего, "
                    "ЕСТЬ — её прямо сейчас берёт/обновляет соседний процесс "
                    "(Use-DeviceStack держит файл эксклюзивно на время взятия). "
                    "ПОВТОРИ прогон через секунду; НЕ бери лизу заново — повторное взятие "
                    "затрёт чужое. Если повторяется постоянно — проверь, не завис ли другой "
                    "процесс (Use-DeviceStack -N 2 -Release снимает застрявшую лизу)."
                )
            corrupt_note = (
                " Файл лизы существует, но НЕ РАЗОБРАН (битый JSON/не-объект) — трактован "
                "как отсутствующий; если это повторяется, сними лизу явно: "
                "Use-DeviceStack -N 2 -Release."
                if absent_reason == _LEASE_ABSENT_CORRUPT else ""
            )
            raise DeviceLeaseInvalidStackError(
                "DEVICE_LEASE_BLOCKED (p3-second-emulator N3): стек 2 требует лизу "
                "БЕЗУСЛОВНО (асимметричный дефолт B27) — лиза отсутствует или "
                "истекла. Возьми: Use-DeviceStack -N 2." + corrupt_note
            )
        if status == _LEASE_ACTIVE:
            if not is_own:
                owner = lease.get("owner_label", "неизвестен")
                raise DeviceLeaseError(
                    "DEVICE_LEASE_BLOCKED (p3-second-emulator N3): стек 2 занят "
                    f"чужой АКТИВНОЙ лизой (владелец: {owner}) — ждать нечего, лиза жива."
                )
            _assert_no_foreign_live_run(lease, stack)  # B-R4-2
            _heartbeat_device_lease(stack, lease, now)
            return
        # status == idle
        if not is_own:
            owner = lease.get("owner_label", "неизвестен")
            last = _parse_lease_timestamp(lease.get("heartbeat_utc")) or _parse_lease_timestamp(lease.get("taken_utc"))
            wait_until = (last + timedelta(seconds=_DEVICE_LEASE_IDLE_SECONDS)).isoformat() if last else "неизвестно"
            raise DeviceLeaseError(
                "DEVICE_LEASE_BLOCKED (p3-second-emulator N3): стек 2 в ожидании "
                f"(idle), чужой владелец ({owner}) может вернуться — жди до "
                f"{wait_until} либо запроси освобождение (Use-DeviceStack -N 2 -Release)."
            )
        _assert_no_foreign_live_run(lease, stack)  # B-R4-2: idle бывает и у ЖИВОГО pid с протухшим за TTL heartbeat
        _heartbeat_device_lease(stack, lease, now)  # B28: своя idle -> active
        return

    # стек 1: отказ ТОЛЬКО при конфликте с чужой АКТИВНОЙ лизой
    if status == _LEASE_ACTIVE:
        if not is_own:
            owner = lease.get("owner_label", "неизвестен")
            raise DeviceLeaseError(
                "DEVICE_LEASE_BLOCKED (p3-second-emulator N3): стек 1 — конфликт "
                f"с чужой АКТИВНОЙ лизой (владелец: {owner})."
            )
        _assert_no_foreign_live_run(lease, stack)  # B-R4-2
        _heartbeat_device_lease(stack, lease, now)
        return
    if status == _LEASE_IDLE and is_own:
        _assert_no_foreign_live_run(lease, stack)  # B-R4-2
        _heartbeat_device_lease(stack, lease, now)  # B28
        return
    # free / reclaimed / чужая idle — легальный дефолт стека 1, ЛИЗУ НЕ ТРОГАЕМ
    # (чужую idle-лизу не крадём — легаси-путь просто её игнорирует)
    return


def check_device_lease() -> None:
    """Публичная обёртка чокпоинта — зовётся И `create_driver` (АВТОРИТЕТНАЯ
    точка, B14), И session-фикстурой `conftest.py::_ensure_app_installed`
    (ДОПОЛНИТЕЛЬНАЯ ранняя сверка, план N3: "session-фикстура conftest —
    только дополнительная ранняя сверка, heartbeat идёт из create_driver").
    Раздельное имя — чтобы отличать вызовы в трассировке/моках тестов."""
    _device_lease_checkpoint()


class DeviceRecoveryError(RuntimeError):
    """ENV_ISSUE (AT-BUG-026): device-liveness guard не смог восстановить
    устройство, либо лимит восстановлений за сессию уже исчерпан. Сообщение
    ВСЕГДА начинается с `ENV_ISSUE` — greppable-маркер для триажа
    (failure-analyst/run-артефакт), см. `schemas/evidence.yaml::ENV_ISSUE`."""


def _warn_recovery(message: str) -> None:
    """AT-BUG-063 (B3, критик-вход rework attempt 3): единая точка диагностики
    recovery-параметров. До неё python-сторона механизма молчала ПОЛНОСТЬЮ —
    отсутствующий/битый state-файл, отброшенное белым списком значение и
    «применён дефолт» были неотличимы друг от друга в логе прогона, при том
    что сам заголовок этого бага — «молча деградирует», а PS-сторона
    (`tasks.ps1::Set-EmulatorSessionState`) уже пишет `Write-Warning` на своём
    отказе. Односторонняя асимметрия закрыта.

    `stderr`, а не `logging`: тот же приём, что `framework/core/mitm.py`
    (AT-BUG-043) — `framework/pytest.ini` не настраивает `log_cli`/уровни,
    поэтому `logging`-запись в дефолтной конфигурации не дошла бы ни до
    консоли, ни до Captured-секции отчёта; `stderr` попадает в обе и в
    Allure-аттачмент. Диагностика НЕ бросает и не меняет поведение —
    исключительно наблюдаемость."""
    print(f"AT-BUG-063 recovery: {message}", file=sys.stderr)


def _read_emulator_session_state() -> dict[str, str]:
    """AT-BUG-063 (F1/F4, rework attempt 2): читает `state/emulator-session.json`,
    которое `tasks.ps1::Start-Emulator` пишет СРАЗУ после разрешения
    `-Gpu`/`-AvdName` (параметр > env > дефолт) — т.е. уже РАЗРЕШЁННОЕ,
    фактически действующее значение, независимо от того, пришло оно явным
    CLI-параметром (сценарий RUN-20260811-0405, не закрытый attempt 1) или
    переменной окружения `AO3_EMU_GPU`.

    Отсутствующий/битый/пустой файл — штатный случай (эмулятор ещё ни разу не
    поднимался этой сессией через канонический `Start-Emulator`, либо файл
    гитигнорится и просто не существует на свежем чекауте) — возвращает `{}`,
    вызывающий код сам решает дефолт. Значения ВСЕГДА проходят через тот же
    белый список/regex, что и env-фолбэк ниже — файл на диске ничем не
    привилегированнее непроверенной строки, а `subprocess.run(..., env=...)`
    (не строковая интерполяция в `-Command`, см. докстринг
    `_restart_emulator_writable_system`) само по себе уже закрывает
    инъекцию — валидация здесь чисто про корректность (не передать qemu
    заведомо бессмысленный `-gpu`/`-avd`)."""
    try:
        # `utf-8-sig`, не `utf-8`: устойчиво к BOM (найдено красной пробой этой
        # задачи -- `Set-Content -Encoding UTF8` PowerShell 5.1 пишет BOM; сам
        # писатель `tasks.ps1::Set-EmulatorSessionState` уже это не делает, но
        # чтение остаётся защищённым от ЛЮБОГО BOM-пишущего пути без будущей
        # хрупкой связки с конкретной реализацией записи).
        raw = _EMULATOR_SESSION_STATE_FILE.read_text(encoding="utf-8-sig")
        data = json.loads(raw)
    except FileNotFoundError:
        # ШТАТНЫЙ случай (файл гитигнорится, эмулятор ещё не поднимался этой
        # машиной через канонический Start-Emulator) — не шумим, итоговая
        # строка `_restart_emulator_writable_system` всё равно назовёт
        # применённый источник (`default`).
        return {}
    except (OSError, ValueError) as exc:
        _warn_recovery(
            f"WARNING: state-файл {_EMULATOR_SESSION_STATE_FILE} нечитаем/битый "
            f"({type(exc).__name__}: {exc}) — параметры изначального подъёма "
            "недоступны, применяется фолбэк (env/дефолт tasks.ps1)."
        )
        return {}
    if not isinstance(data, dict):
        _warn_recovery(
            f"WARNING: state-файл {_EMULATOR_SESSION_STATE_FILE} содержит "
            f"{type(data).__name__}, а не JSON-объект — игнорируется целиком, "
            "применяется фолбэк (env/дефолт tasks.ps1)."
        )
        return {}

    # spec-p3-second-emulator N1 (констрейнт 3в): `tasks.ps1::Set-EmulatorSessionState`
    # ТЕПЕРЬ дополнительно ключует запись по серийнику (`by_serial[emulator-$Port]`)
    # рядом с ФЛЭТ top-level полями (gpu/avd_name/updated_utc — «последний
    # записавший стек», НЕИЗМЕННЫЙ формат ради обратной совместимости с
    # AT-BUG-063 пинами, которые пишут/читают ТОЛЬКО флэт-поля и никогда не
    # видят/не заполняют `by_serial`). Recovery ЭТОЙ функции предпочитает
    # запись СВОЕГО серийника (`settings.DEVICE_NAME`) из `by_serial`, если
    # она есть — иначе (legacy-файл до этой правки, серийник ещё не
    # писавшийся через by_serial, либо `by_serial` вовсе отсутствует)
    # молча откатывается на флэт top-level поля, тем самым не отличаясь от
    # поведения ДО этой правки для ЛЮБОГО существующего вызывающего кода/пробы.
    own_serial = settings.DEVICE_NAME
    by_serial = data.get("by_serial")
    own_entry = None
    if isinstance(by_serial, dict):
        candidate = by_serial.get(own_serial)
        if isinstance(candidate, dict):
            own_entry = candidate
    source = own_entry if own_entry is not None else data

    result: dict[str, str] = {}
    gpu = source.get("gpu")
    if isinstance(gpu, str) and gpu in _VALID_GPU_BACKENDS:
        result["gpu"] = gpu
    elif gpu is not None:
        _warn_recovery(
            f"WARNING: gpu={gpu!r} из state-файла ОТБРОШЕН (не в белом списке "
            f"{sorted(_VALID_GPU_BACKENDS)}) — GPU-предпосылка прогона этим "
            "recovery НЕ восстанавливается."
        )
    avd_name = source.get("avd_name")
    if isinstance(avd_name, str) and _AVD_NAME_RE.match(avd_name):
        result["avd_name"] = avd_name
    elif avd_name is not None:
        _warn_recovery(
            f"WARNING: avd_name={avd_name!r} из state-файла ОТБРОШЕН (не "
            f"соответствует {_AVD_NAME_RE.pattern}) — recovery поднимет AVD по "
            "дефолту tasks.ps1."
        )
    # B3/риск «протухание»: `updated_utc` писался с attempt 2, но НЕ читался
    # никем — теперь он попадает в диагностику (возраст state). TTL/отсечка
    # НЕ вводится (это меняло бы поведение ядра, которое эта итерация не
    # переделывает) — см. «Остаточные риски» в bugs/AT-BUG-063.md.
    updated_utc = source.get("updated_utc")
    if isinstance(updated_utc, str):
        result["updated_utc"] = updated_utc
    return result


def _state_age_note(updated_utc: str | None) -> str:
    """Человекочитаемый возраст state-файла для диагностической строки
    recovery (B3). Отдельная функция — чтобы битый/отсутствующий
    `updated_utc` НИКОГДА не ронял сам recovery (диагностика не имеет права
    быть источником отказа)."""
    if not updated_utc:
        return "возраст state неизвестен (updated_utc отсутствует)"
    try:
        ts = datetime.fromisoformat(updated_utc)
    except (TypeError, ValueError):
        return f"возраст state неизвестен (updated_utc={updated_utc!r} не разобран)"
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    age_h = (datetime.now(timezone.utc) - ts).total_seconds() / 3600.0
    return f"state записан {updated_utc} (возраст {age_h:.1f} ч)"


def _restart_emulator_writable_system(timeout: float = _EMULATOR_RESTART_TIMEOUT) -> None:
    """Канонический перезапуск эмулятора ОДНИМ вызовом `Start-Emulator
    -WritableSystem` (`scripts/tasks.ps1`) — НЕ самодельный поллинг
    `getprop sys.boot_completed`: вся логика ожидания буда (включая
    AT-BUG-012 quickboot-фолбэк) уже живёт в каноническом tasks.ps1, дублировать
    её здесь означало бы новый экземпляр того же класса хрупкости.

    `-WritableSystem` ОБЯЗАТЕЛЕН, не опция: `tasks.ps1::Start-Emulator` сама
    вызывает `Install-MitmCA` сразу после `boot_completed=1`, КОГДА И ТОЛЬКО
    КОГДА передан этот флаг (см. tasks.ps1:124-132) — единственный способ
    гарантировать переустановку CA, которая иначе стирается ЛЮБЫМ ребутом
    эмулятора (HANDOFF runbook) и превратила бы recovery сам в источник
    каскада `ReadTimeoutError` на следующих replay-тестах.

    AT-BUG-063 (F1/F4, rework attempt 2 — критик-вход отклонил attempt 1).
    Attempt 1 читал ТОЛЬКО `AO3_EMU_GPU` из окружения ЭТОГО python-процесса —
    критик показал эмпирически, что это НИЧЕГО не меняло: `tasks.ps1:188-189`
    уже сама фолбэчилась на `$env:AO3_EMU_GPU` при отсутствии явного `-Gpu`, и
    `subprocess.run` без `env=` и так наследует полное окружение. Реальный
    воспроизведённый сценарий (RUN-20260811-0405) — `-Gpu host` передан
    ЯВНЫМ CLI-параметром НАЧАЛЬНОМУ `Start-Emulator`, БЕЗ переменной
    окружения на сессию; такой случай attempt 1 не закрывал вовсе.

    Источник истины теперь — `state/emulator-session.json`
    (`_read_emulator_session_state`), которое `Start-Emulator` пишет сама
    СРАЗУ после разрешения параметров (параметр > env > дефолт) — видит и
    явный CLI-флаг, и переменную окружения, и дефолт одинаково, потому что
    все три уже схлопнуты в одно значение к моменту записи. `AO3_EMU_GPU`
    из окружения ЭТОГО процесса остаётся вторичным фолбэком (обратная
    совместимость: до первого `Start-Emulator` в сессии state-файла может не
    быть, а старый путь всё ещё штатно работает).

    F3 (critic, attempt 2): значения НЕ интерполируются в строку `-Command`
    (та инъекция ловилась: пробел ломал биндинг параметра, `;` исполнялся
    отдельной командой, кавычка валила парсер). Вместо этого они кладутся в
    `env=` дочернего процесса (`AO3_RECOVERY_GPU`/`AO3_RECOVERY_AVD_NAME`), а
    сама `-Command`-строка — ФИКСИРОВАННЫЙ литерал (без f-string подстановки
    непроверенных данных): PowerShell резолвит `$env:AO3_RECOVERY_*` как
    ОБЪЕКТ-значение параметра, не перепарсивает его содержимое как скрипт —
    пробел/`;`/кавычка внутри значения инертны. Белый список
    (`_VALID_GPU_BACKENDS`) и regex (`_AVD_NAME_RE`) в
    `_read_emulator_session_state`/ниже — не защита от инъекции (она уже
    закрыта механизмом передачи), а санитизация мусора (не звать qemu с
    выдуманным `-gpu`)."""
    state = _read_emulator_session_state()
    gpu_arg = state.get("gpu", "")
    gpu_source = "state" if gpu_arg else "default"
    if not gpu_arg:
        env_gpu = os.environ.get("AO3_EMU_GPU", "")
        if env_gpu and env_gpu not in _VALID_GPU_BACKENDS:
            _warn_recovery(
                f"WARNING: AO3_EMU_GPU={env_gpu!r} ОТБРОШЕНА (не в белом списке "
                f"{sorted(_VALID_GPU_BACKENDS)}) — применяется дефолт tasks.ps1."
            )
        if env_gpu in _VALID_GPU_BACKENDS:
            gpu_arg = env_gpu
            gpu_source = "env AO3_EMU_GPU"
    else:
        # B3/риск «инверсия приоритета»: state ПЕРЕКРЫВАЕТ `AO3_EMU_GPU`
        # текущей сессии, хотя runbook (docs/HANDOFF.md, docs/environment-
        # setup.md) называет переменную окружения каноническим способом
        # ЗАЯВИТЬ предпосылку прогона. Порядок приоритета этой итерацией
        # НЕ меняется (это семантика ядра, доказанного критиком), но
        # расхождение больше не проходит МОЛЧА — оператор видит, что его
        # env-заявка перекрыта историческим state. См. «Остаточные риски»
        # в bugs/AT-BUG-063.md.
        env_gpu = os.environ.get("AO3_EMU_GPU", "")
        if env_gpu and env_gpu != gpu_arg:
            _warn_recovery(
                f"WARNING: КОНФЛИКТ источников GPU — state-файл несёт "
                f"{gpu_arg!r}, а AO3_EMU_GPU текущей сессии — {env_gpu!r}. "
                f"Применяется {gpu_arg!r} (state имеет приоритет: он отражает "
                "параметры РЕАЛЬНО поднятого эмулятора). Если предпосылка "
                "сессии другая — подними эмулятор канонической формой заново "
                "или удали state/emulator-session.json."
            )
    avd_arg = state.get("avd_name", "")  # без state-файла флаг просто не передаётся -
    # tasks.ps1 применит собственный дефолт `ao3_test_api34`, как и раньше (F4:
    # у AvdName нет env-эквивалента AO3_EMU_GPU, только state-файл).

    child_env = dict(os.environ)
    child_env.pop("AO3_RECOVERY_GPU", None)
    child_env.pop("AO3_RECOVERY_AVD_NAME", None)
    if gpu_arg:
        child_env["AO3_RECOVERY_GPU"] = gpu_arg
    if avd_arg:
        child_env["AO3_RECOVERY_AVD_NAME"] = avd_arg

    ps_command = (
        f". \"{_TASKS_PS1}\"; "
        "$seArgs = @{ WritableSystem = $true }; "
        "if ($env:AO3_RECOVERY_GPU) { $seArgs.Gpu = $env:AO3_RECOVERY_GPU }; "
        "if ($env:AO3_RECOVERY_AVD_NAME) { $seArgs.AvdName = $env:AO3_RECOVERY_AVD_NAME }; "
        "Start-Emulator @seArgs"
    )
    cmd = [
        "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_command,
    ]
    # B3: одна строка на КАЖДЫЙ recovery — что фактически применено и откуда.
    # `default` значит «флаг не передан вовсе, решает tasks.ps1» (её дефолты:
    # gpu=swiftshader_indirect, avd=ao3_test_api34) — именно этот молчаливый
    # путь и был исходным дефектом бага, теперь он ВИДЕН в логе прогона.
    _warn_recovery(
        f"перезапуск эмулятора: gpu={gpu_arg or '<tasks.ps1 default>'} "
        f"(source: {gpu_source}), "
        f"avd={avd_arg or '<tasks.ps1 default>'} "
        f"(source: {'state' if avd_arg else 'default'}); "
        f"{_state_age_note(state.get('updated_utc'))}; "
        f"state-файл: {_EMULATOR_SESSION_STATE_FILE}"
    )
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=child_env)
    except subprocess.TimeoutExpired as exc:
        raise DeviceRecoveryError(
            f"ENV_ISSUE (AT-BUG-026): Start-Emulator -WritableSystem не "
            f"завершился за {timeout}s — recovery устройства не удался."
        ) from exc
    if cp.returncode != 0:
        raise DeviceRecoveryError(
            "ENV_ISSUE (AT-BUG-026): Start-Emulator -WritableSystem "
            f"завершился кодом {cp.returncode} — recovery устройства не "
            f"удался.\nstdout (хвост): {cp.stdout[-2000:]}\n"
            f"stderr (хвост): {cp.stderr[-2000:]}"
        )


def _verify_app_installed_with_retry() -> None:
    """Проверяет/переустанавливает приложение после `_restart_emulator_writable_system`
    (паттерн `conftest.py::_ensure_app_installed`) с BOUNDED retry на
    транзиентную гонку storage/vold-сервиса (см. `_APP_VERIFY_RETRIES` выше) —
    без retry ЛЮБОЙ такой транзиент валил бы ВЕСЬ recovery необратимо, хотя
    следующая попытка через несколько секунд обычно проходит.

    F5 (критик-вход attempt 3): ловим `(RuntimeError, OSError)`, не только
    `RuntimeError`. `adb.install()`/`adb.is_installed()` уходят в
    `adb._run()`, которая на зависшем/неотвечающем adb кидает `TimeoutError`
    (стандартная библиотечная — ПОДКЛАСС `OSError`, не `RuntimeError`) —
    голый `except RuntimeError` пропускал бы этот класс мимо retry-цикла И
    мимо чистого `ENV_ISSUE`-сообщения ниже, улетая наверх сырым
    `TimeoutError` без атрибуции к recovery."""
    last_exc: RuntimeError | OSError | None = None
    for attempt in range(1, _APP_VERIFY_RETRIES + 1):
        try:
            if not adb.is_installed():
                adb.install()
            return
        except (RuntimeError, OSError) as exc:
            last_exc = exc
            if attempt < _APP_VERIFY_RETRIES:
                time.sleep(_APP_VERIFY_BACKOFF)
    raise DeviceRecoveryError(
        "ENV_ISSUE (AT-BUG-026): проверка/переустановка приложения после "
        f"recovery не удалась за {_APP_VERIFY_RETRIES} попыток(-ки) — "
        f"{last_exc}"
    ) from last_exc


class DeviceLivenessGuard:
    """Device-liveness guard (AT-BUG-026, контейнмент вероятностного qemu-краха
    `0xc0000005`): перед КАЖДОЙ Appium-сессией (см. фикстура `driver`,
    `framework/tests/conftest.py`) проверяет присутствие устройства
    (`adb.device_present()`, класс `Get-Device` — позитивная сверка, не
    голый пустой вывод, CLAUDE.md permission-hygiene п.6) и, если оно
    отсутствует, делает ОГРАНИЧЕННОЕ авто-восстановление вместо того, чтобы
    дать каскад `Could not find a connected Android device`/`adb.exe: no
    devices` на КАЖДОМ последующем тесте прогона (baseline 2026-07-24: 1 краш
    -> 28 каскадных errors, `bugs/AT-BUG-026.md`).

    Recovery = перезапуск эмулятора канонической формой (`Start-Emulator
    -WritableSystem`, переустанавливает mitm-CA сама) + проверка, что
    приложение всё ещё установлено (`adb.is_installed()`/`adb.install()`,
    паттерн `conftest.py::_ensure_app_installed` — userdata-партиция AVD
    обычно переживает рестарт эмулятора, но проверка дешёвая и не
    полагается на это молча).

    Границы (жёстко, спека Lead):
    - лимит `max_recoveries` — счётчик ЗА ВСЮ pytest-сессию (module-level
      инстанс в conftest.py, не за один тест). Исчерпан -> `DeviceRecoveryError`
      (`ENV_ISSUE`) БЕЗ попытки восстановления — короткое замыкание ДО
      создания Appium-сессии (`adb.device_present()` — доли секунды), не
      20-секундный таймаут `Could not find a connected Android device` на
      КАЖДОМ следующем тесте;
    - recovery срабатывает ТОЛЬКО когда устройство отсутствует — живое
      устройство с красным тестом этот guard не трогает вообще (первая же
      строка `ensure_ready` — `if adb.device_present(): return None`);
    - тест, ВО ВРЕМЯ которого устройство умерло, остаётся FAILED/ERROR
      честно — guard живёт в setup СЛЕДУЮЩЕГО теста (фикстура `driver`),
      recovery спасает только ПОСЛЕДУЮЩИЕ тесты, не маскирует исходное
      падение;
    - идемпотентность: `recovery_count` инкрементируется ДО попытки
      restart (не после успеха) — неудачная попытка тоже расходует лимит
      (иначе класс M6: граница «живёт», только если её нельзя обойти
      повторением одного и того же неудачного шага без счёта). Каждый шаг
      recovery (Start-Emulator, is_installed/install, финальная проверка
      device_present) идемпотентен сам по себе (Clear-EmulatorStaleLocks
      внутри tasks.ps1, `adb install -r`, повторный `device_present()`) —
      повторный вызов `ensure_ready()` после частичного отказа не оставляет
      противоречивое состояние счётчика/среды."""

    def __init__(self, max_recoveries: int):
        self.max_recoveries = max_recoveries
        self.recovery_count = 0

    def ensure_ready(self) -> str | None:
        """Вызывается ПЕРЕД `create_driver`. Возвращает WARN-сообщение
        (recovery произошёл — вызывающий код обязан `warnings.warn` его,
        паттерн `download_oracle`), либо `None` (устройство было на месте,
        recovery не потребовался). Бросает `DeviceRecoveryError`, если
        устройство отсутствует и лимит восстановлений уже исчерпан, либо
        сам restart не смог вернуть устройство в строй."""
        if adb.device_present():
            return None
        if self.recovery_count >= self.max_recoveries:
            raise DeviceRecoveryError(
                "ENV_ISSUE (AT-BUG-026): устройство отсутствует, лимит "
                f"восстановлений за сессию исчерпан "
                f"({self.recovery_count}/{self.max_recoveries}) — device-"
                "liveness guard остановлен, дальнейшие попытки НЕ "
                "предпринимаются (fail-fast, без каскада 20с-таймаутов на "
                "каждом следующем тесте)."
            )
        self.recovery_count += 1
        attempt = self.recovery_count
        _restart_emulator_writable_system()
        # F6 (критик-вход attempt 3): проверка присутствия устройства ПЕРЕНЕСЕНА
        # сразу после рестарта, ДО `_verify_app_installed_with_retry()` — раньше
        # стояла после нёе и, если рестарт не вернул устройство, код сначала жёг
        # ~{_APP_VERIFY_RETRIES}*{_APP_VERIFY_BACKOFF}с retry/backoff на заведомо
        # мёртвом устройстве, только потом сообщал об отказе. Если install-verify
        # сам словит транзиентную/фатальную ошибку устройства — она уже покрыта
        # её собственным `DeviceRecoveryError` (см. F5 выше), отдельная финальная
        # проверка после неё избыточна.
        if not adb.device_present():
            raise DeviceRecoveryError(
                f"ENV_ISSUE (AT-BUG-026): recovery {attempt}/"
                f"{self.max_recoveries} — Start-Emulator -WritableSystem "
                "завершился успешно (returncode=0), но устройство всё ещё "
                "отсутствует СРАЗУ после рестарта, до проверки установки "
                "приложения — recovery не удался (fail-fast, без "
                f"{_APP_VERIFY_RETRIES * _APP_VERIFY_BACKOFF:.0f}s "
                "install-retry на заведомо мёртвом устройстве)."
            )
        _verify_app_installed_with_retry()
        return (
            f"AT-BUG-026 device-liveness guard: устройство отсутствовало, "
            f"выполнено восстановление {attempt}/{self.max_recoveries} за "
            "сессию (Start-Emulator -WritableSystem + переустановка mitm-CA)."
        )


def create_driver(no_reset: bool = True, settle_retries: int = 0):
    """`settle_retries` (AT-BUG-026, device-liveness guard, находка красной
    пробы w1): число ДОПОЛНИТЕЛЬНЫХ попыток создать сессию, если ПЕРВАЯ упала
    — используется ТОЛЬКО вызывающим кодом, который знает, что recovery
    ТОЛЬКО ЧТО произошёл в этом тесте (`conftest.py::driver`), где устройство
    только что перезапущено и первая Appium-сессия иногда не успевает
    "устояться" (`WebDriverException: Appium Settings app is not running
    after 30000ms` — класс уже документирован в истории этого бага,
    `bugs/AT-BUG-026.md`). Дефолт 0 — НИКАКИХ ретраев, обычный путь (recovery
    не требовался) поведение не меняет вообще."""
    # spec-p3-second-emulator N3 (B14): чокпоинт лизы — АВТОРИТЕТНАЯ точка,
    # НА ПУТИ ИСПОЛНЕНИЯ ПРОГОНА, function/driver-scoped (каждый вызов
    # create_driver, не только начало сессии) — раньше ЛЮБОГО реального
    # обращения к Appium. Бросает `DeviceLeaseError`/`DeviceLeaseInvalidStackError`
    # (маркер `DEVICE_LEASE_BLOCKED`), если стек залижен чужим/незалижен на
    # стеке 2 — до попытки создать сессию.
    check_device_lease()
    attempts_left = settle_retries + 1
    last_exc: Exception | None = None
    while attempts_left > 0:
        attempts_left -= 1
        driver = None
        try:
            opts = capabilities.build_options(no_reset=no_reset)
            # AT-BUG-007: client-side read-timeout на command_executor. Без него единичный
            # блокирующий HTTP-вызов к Appium (мёртвый процесс приложения, сетевой ступор)
            # висит на сокете навсегда и клинит весь suite — см. settings.APPIUM_HTTP_TIMEOUT.
            #
            # retries=False (штатный параметр ClientConfig.init_args_for_pool_manager ->
            # urllib3.PoolManager(retries=...), НЕ монки-патч) отключает урллиб3-ретраи на
            # уровне HTTP: без этого urllib3 по умолчанию ретраит GET (в т.ч. driver.contexts)
            # до 3 раз при read-timeout, и висящий GET реально падает не за
            # APPIUM_HTTP_TIMEOUT, а за ~4x (измерено; см. AT-BUG-007, Обсуждение, attempt 2).
            # С retries=False и GET, и POST падают ReadTimeoutError ровно за 1x timeout —
            # предсказуемая граница вместо путаницы GET-vs-POST множителей. Компенсирующий
            # ретрай теперь на уровне теста, а не HTTP: framework/pytest.ini
            # (--reruns 1 --only-rerun ReadTimeoutError|MaxRetryError) — таргетированно на
            # класс инфраструктурных таймаутов, не на любые сетевые сбои (см. риск в
            # settings.APPIUM_HTTP_TIMEOUT).
            client_config = AppiumClientConfig(
                remote_server_addr=settings.APPIUM_URL,
                timeout=settings.APPIUM_HTTP_TIMEOUT,
                init_args_for_pool_manager={"init_args_for_pool_manager": {"retries": False}},
            )
            driver = webdriver.Remote(
                settings.APPIUM_URL, options=opts, client_config=client_config
            )
            driver.implicitly_wait(settings.IMPLICIT_WAIT)
            return driver
        except Exception as exc:  # noqa: BLE001 — ретрай только opt-in (settle_retries>0)
            last_exc = exc
            # F7 (критик-вход attempt 3): `webdriver.Remote(...)` мог УЖЕ создать
            # реальную Appium-сессию, а упасть позже (например на
            # `implicitly_wait`) — без явного `quit_driver` здесь частично
            # созданная сессия утекала бы на Appium-сервере при каждом settle-
            # ретрае (opt-in путь ПОСЛЕ recovery, settle_retries>0). `driver`
            # остаётся `None`, если упал сам `webdriver.Remote(...)` (нечего
            # закрывать) — `quit_driver` уже no-op на `None`.
            quit_driver(driver)
            if attempts_left <= 0:
                raise
            time.sleep(_SETTLE_RETRY_BACKOFF)
    raise last_exc  # pragma: no cover — недостижимо, для полноты типов


def quit_driver(driver) -> None:
    if driver is None:
        return
    try:
        driver.quit()
    except Exception:  # noqa: BLE001 — закрытие не должно ронять прогон
        pass
