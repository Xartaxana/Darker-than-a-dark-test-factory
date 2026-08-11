"""Создание и закрытие сессии Appium. Ядро не знает об экранах приложения."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

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
    result: dict[str, str] = {}
    gpu = data.get("gpu")
    if isinstance(gpu, str) and gpu in _VALID_GPU_BACKENDS:
        result["gpu"] = gpu
    elif gpu is not None:
        _warn_recovery(
            f"WARNING: gpu={gpu!r} из state-файла ОТБРОШЕН (не в белом списке "
            f"{sorted(_VALID_GPU_BACKENDS)}) — GPU-предпосылка прогона этим "
            "recovery НЕ восстанавливается."
        )
    avd_name = data.get("avd_name")
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
    updated_utc = data.get("updated_utc")
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
