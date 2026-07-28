"""Создание и закрытие сессии Appium. Ядро не знает об экранах приложения."""
from __future__ import annotations

import subprocess
import time

from appium import webdriver
from appium.webdriver.client_config import AppiumClientConfig

from framework.config import capabilities, settings
from framework.core import adb

_TASKS_PS1 = settings.REPO_ROOT / "scripts" / "tasks.ps1"
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
    каскада `ReadTimeoutError` на следующих replay-тестах."""
    cmd = [
        "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
        f". \"{_TASKS_PS1}\"; Start-Emulator -WritableSystem",
    ]
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
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
