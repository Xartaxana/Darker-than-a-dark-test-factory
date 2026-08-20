"""Фикстуры и хуки прогона.

Стратегия состояния: тесты стартуют из известного состояния через фикстуры
(clean_app / seeded_library), порядок тестов не важен. Артефакты падения крепятся
автоматически хуком pytest_runtest_makereport.
"""
from __future__ import annotations

import json
import os
import warnings

import pytest

from framework.config import settings
from framework.core import adb, driver_factory, mitm, reporting
from framework.data import recording_builder as rb
from framework.data import works as W
from framework.data.works import Work
from framework.steps import app_steps

_DOWNLOADED_WORK_FIXTURE = settings.DATA_DIR / "fixtures" / "downloaded_work.html"


def pytest_configure(config):
    config.addinivalue_line("markers", "p0: smoke — гоняется на каждой сборке")
    config.addinivalue_line("markers", "p1: регрессия")
    config.addinivalue_line("markers", "live: требует живого AO3")
    config.addinivalue_line("markers", "replay: требует replay-прокси")
    config.addinivalue_line(
        "markers",
        "produces_download: тест легитимно инициирует реальное скачивание "
        "файла в download-директорию приложения — download_oracle не считает "
        "результат незапрошенным (класс BUG-014)",
    )
    # spec-p3-second-emulator N1 (констрейнт 3г/B19): allure-изоляция ПЕР-СТЕК
    # без правки addopts/pytest.ini (--clean-alluredir остаётся, аргумент
    # обратной совместимости B15) - override `config.option.allure_report_dir`
    # (то же поле, что читает `allure_pytest.plugin.pytest_configure`,
    # `--alluredir`/dest=`allure_report_dir`) значением `settings.ALLURE_RESULTS`
    # (уже читает `ALLURE_RESULTS` env, framework/config/settings.py — дефолт
    # прежний `framework/allure-results`, обратная совместимость стека 1 без
    # правок). Работает ТОЛЬКО если этот хук вызывается ДО
    # `allure_pytest.plugin.pytest_configure` (порядок регистрации плагинов —
    # witness DoD, не чтение, см. runs/).
    #
    # Совет критика (критик-раунд, 2026-08-20): override ТОЛЬКО когда
    # ALLURE_RESULTS явно стоит в os.environ - иначе ручной `--alluredir
    # <путь>` (CLI-флаг, тот же config.option.allure_report_dir) тихо
    # проглатывался бы дефолтом settings.ALLURE_RESULTS даже без всякого
    # намерения стек-изоляции.
    if os.environ.get("ALLURE_RESULTS"):
        config.option.allure_report_dir = str(settings.ALLURE_RESULTS)


def _ensure_no_residual_device_proxy() -> None:
    """AT-BUG-064, кандидат фикса (а): снимает ОСТАТОЧНЫЙ device-прокси,
    переживший рестарт эмулятора/аварийное завершение предыдущей
    сессии-worker'а (`mitm.ensure_no_residual_proxy()` — подробный докстринг
    там), ДО ЛЮБОЙ работы сессии — не только replay-тестов. Вынесена в
    отдельную ЧИСТУЮ функцию (тот же приём, что `_ensure_replay_ca`/
    `_ensure_upstream_fast` ниже, N2 критик-вход attempt 4): pytest 9
    запрещает прямой вызов декорированной fixture-функции, а device-free
    юнит-проба (`test_residual_proxy_guard_unit.py`) обязана звать эту
    логику напрямую с монки-патченным `mitm.ensure_no_residual_proxy`, без
    реального adb.

    ВТОРАЯ точка вызова (B2, критик-вход rework attempt 2): также из
    `pytest_runtest_setup()` ниже, СРАЗУ после `_reset_ca_check()`, если
    в ЭТОМ тесте случился device-liveness recovery — см. докстринг хука.
    Без второй точки проверка была недостижима ровно для сценария из
    заголовка бага (остаток переживает ПЕРЕЗАПУСК эмулятора): session-
    scoped `_ensure_app_installed` инстанцируется один раз ДО первого
    теста сессии, recovery же может произойти В ЛЮБОЙ момент прогона
    (АО3_EMU device-liveness guard, AT-BUG-026)."""
    stale = mitm.ensure_no_residual_proxy()
    if stale is not None:
        warnings.warn(
            f"AT-BUG-064: остаточный device-прокси '{stale}' обнаружен на "
            "старте прогона (пережил рестарт эмулятора или аварийное "
            "завершение предыдущей сессии/worker'а) -- снят автоматически."
        )


def _ensure_default_font_scale() -> None:
    """AT-BUG-066, твин `_ensure_no_residual_device_proxy()`: снимает
    ОСТАТОЧНЫЙ системный масштаб шрифта (`adb.set_font_scale()`), переживший
    рестарт эмулятора/аварийное завершение предыдущей сессии-worker'а
    (`adb.ensure_default_font_scale()` — подробный докстринг там), ДО ЛЮБОЙ
    работы сессии. Вынесена в отдельную ЧИСТУЮ функцию по тому же приёму, что
    `_ensure_no_residual_device_proxy` (pytest 9 запрещает прямой вызов
    декорированной fixture-функции; device-free юнит-проба обязана звать эту
    логику напрямую с монки-патченным `adb.ensure_default_font_scale`, без
    реального adb).

    ВТОРАЯ точка вызова — из `pytest_runtest_setup()` ниже, СРАЗУ после
    `_ensure_no_residual_device_proxy()`, если в ЭТОМ тесте случился
    device-liveness recovery: без неё проверка была бы недостижима ровно для
    сценария заголовка `AT-BUG-066` (остаток переживает ПЕРЕЗАПУСК
    эмулятора) — тот же аргумент, что B2 `AT-BUG-064`."""
    stale = adb.ensure_default_font_scale()
    if stale is not None:
        warnings.warn(
            f"AT-BUG-066: остаточный font_scale='{stale}' обнаружен на старте "
            "прогона (пережил рестарт эмулятора или аварийное завершение "
            f"предыдущей сессии/worker'а) -- сброшен автоматически в "
            f"{adb.DEFAULT_FONT_SCALE}."
        )


def _ensure_default_night_mode() -> None:
    """AT-BUG-066, твин `_ensure_default_font_scale()`/`_ensure_no_residual_
    device_proxy()`: снимает ОСТАТОЧНЫЙ режим тёмной темы ОС (`adb.
    set_night_mode()`), переживший рестарт эмулятора/аварийное завершение
    предыдущей сессии-worker'а (`adb.ensure_default_night_mode()` —
    докстринг там), ДО ЛЮБОЙ работы сессии. Та же вторая точка вызова из
    `pytest_runtest_setup()` после device-liveness recovery, по тем же
    причинам."""
    stale = adb.ensure_default_night_mode()
    if stale is not None:
        warnings.warn(
            f"AT-BUG-066: остаточный night mode='{stale}' обнаружен на старте "
            "прогона (пережил рестарт эмулятора или аварийное завершение "
            f"предыдущей сессии/worker'а) -- сброшен автоматически в "
            f"{adb.DEFAULT_NIGHT_MODE!r}."
        )


@pytest.fixture(scope="session", autouse=True)
def _ensure_app_installed():
    """AT-BUG-064, кандидат фикса (а): подключает `_ensure_no_residual_device_
    proxy()` (см. её докстринг) именно СЮДА, а не отдельной новой `autouse`-
    фикстурой: эта фикстура — УЖЕ единственная session-scoped autouse точка
    входа conftest.py, которую ~20 существующих device-free юнит-проб
    (`test_*_unit.py`) переопределяют no-op'ом, чтобы не трогать устройство
    при сборе полного набора (см. `test_mitm_proxy_reachable_unit.py` и
    сиблинги); отдельная новая session-autouse фикстура заставила бы КАЖДУЮ
    из них ловить реальный adb-вызов, если её тоже не переопределить —
    присоединение к уже переопределяемой точке даёт классовую полноту без
    правки полутора десятков файлов.

    AT-BUG-066 (сиблинг класса, найденный критиком по правилу 9 CLAUDE.md на
    приёмке AT-BUG-064): та же логика подключена здесь для font_scale/night
    mode — тот же класс персистентной Android-настройки, тот же аргумент
    единой переопределяемой точки.

    spec-p3-second-emulator N3 (B22/B26): `driver_factory.check_device_lease()`
    вызывается ПЕРВОЙ строкой — ДОПОЛНИТЕЛЬНАЯ (не единственная — план N3
    прямо это называет) ранняя сверка лизы: незалиженный прогон стека 2
    падает ДО ЛЮБОГО реального adb-вызова этой фикстуры (residual-proxy/
    font_scale/night_mode/install), не только на первом `driver` теста.
    Авторитетная точка — `create_driver` (function/driver-scoped, вызывается
    КАЖДЫМ тестом) — эта session-scoped сверка не заменяет её, только даёт
    более ранний/дешёвый сигнал на старте сессии."""
    driver_factory.check_device_lease()
    _ensure_no_residual_device_proxy()
    _ensure_default_font_scale()
    _ensure_default_night_mode()
    if not adb.is_installed():
        adb.install()
    yield


# AT-BUG-026 (device-liveness guard, контейнмент): один инстанс НА ВСЮ
# pytest-сессию (module-level, тот же приём, что `_ca_checked`/
# `_download_oracle_last_post` — переживает отдельные тесты, сбрасывается
# только новым процессом pytest). `recovery_count` копится по ВСЕМ тестам
# сессии, не за один тест — см. `driver_factory.DeviceLivenessGuard`.
_DEVICE_GUARD = driver_factory.DeviceLivenessGuard(
    max_recoveries=settings.MAX_RECOVERIES_PER_SESSION
)

# B1 (критик-вход attempt 3, ДОРАБОТАТЬ): guard, живущий ТОЛЬКО в setup
# фикстуры `driver`, недостижим для тестов, где `replay`/`clean_app`/
# `seeded_library`-семья перечислена В СИГНАТУРЕ ТЕСТА РАНЬШЕ `driver`
# (`test_x(clean_app, replay, driver)`) — pytest инстанцирует фикстуры В
# ПОРЯДКЕ АРГУМЕНТОВ, значит `replay`(-> `mitm.set_device_proxy()`, кидает
# `CalledProcessError` НАПРЯМУЮ на мёртвом устройстве) или `clean_app`(->
# `adb.clear_app_data()`, тихий no-op — см. B2 ниже) успевают тронуть
# мёртвое устройство ДО того, как guard вообще получает шанс сработать.
# Сообщение, переданное `warnings.warn` фикстурой `driver` (если recovery
# произошёл ИМЕННО в этот вызов ensure_ready) — читается той же фикстурой
# ниже, чтобы решить `settle_retries` (находка красной пробы w1).
_pending_recovery_warning: str | None = None


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item: pytest.Item) -> None:
    """AT-BUG-026 B1: device-liveness guard обязан выполниться ДО того, как
    pytest начнёт инстанцировать ЛЮБУЮ device-трогающую фикстуру ТЕКУЩЕГО
    теста — не только `driver`. `tryfirst=True` гарантирует, что ЭТА
    реализация хука отработает РАНЬШЕ встроенной
    (`_pytest.runner.pytest_runtest_setup`, которая и вызывает
    `item.session._setupstate.setup(item)` — саму fixture-инстанциацию):
    без явного `tryfirst` порядок держался бы на детали реализации pytest
    (LIFO-порядок регистрации плагинов), полагаться на неё молча — то же
    нарушение, что описывает CLAUDE.md про env-негатив без сверки.

    Признак «тест трогает устройство» — `"driver" in item.fixturenames`,
    НЕ перечисление device-фикстур поимённо: КАЖДЫЙ существующий device-тест
    (`replay`/`clean_app`/`seeded_library`-семья) запрашивает `driver` В ТОЙ
    ЖЕ сигнатуре (grep-проверено по `framework/tests/` — единственное
    исключение, device-free unit-пробы вида `test_replay_ca_check_unit.py`,
    `driver` не запрашивают вовсе); `item.fixturenames` — ПОЛНОЕ транзитивное
    множество, не зависящее от ПОРЯДКА аргументов в сигнатуре. Единый
    самообновляющийся признак вместо allowlist, который пришлось бы
    поддерживать вручную при каждой новой device-фикстуре.

    Если `ensure_ready()` бросает `DeviceRecoveryError` (лимит исчерпан или
    сам restart не вернул устройство) — исключение поднимается ИЗ ЭТОГО
    хука, ДО вызова `item.setup()`: pytest трактует это как ошибку setup'а
    теста, ни одна фикстура (включая `clean_app`/`replay`) вообще не
    инстанцируется — короткое замыкание сохраняется в точности как раньше,
    просто точка вызова поднята выше по стеку.

    R1 (критик-вход attempt 4): `_pending_recovery_warning` сбрасывается
    в `None` В САМОМ НАЧАЛЕ хука, ДО проверки `"driver" in
    item.fixturenames` — устаревающий глобал иначе пережил бы тест БЕЗ
    `driver` (тот вернётся раньше, не тронув переменную) и следующий
    device-тест мог бы унаследовать `_pending_recovery_warning` от теста
    ДВА-ИЛИ-БОЛЕЕ шага назад, если между ними не было ни одного вызова
    `ensure_ready()`, устанавливающего своё собственное значение (в
    штатном потоке `ensure_ready()` вызывается на КАЖДОМ device-тесте и
    сама переустанавливает переменную — но явный сброс ДО предиката не
    полагается на этот побочный эффект как единственную гарантию).

    R2 (критик-вход attempt 4): `warnings.warn(...)` для recovery-WARN
    перенесён СЮДА, в сам хук — раньше жил в фикстуре `driver`, которая
    инстанцируется ПОСЛЕ `clean_app`/`replay` (см. их докстринги про
    порядок аргументов сигнатуры теста): если один из НИХ падает на
    setup ДО того, как pytest дойдёт до `driver`, состоявшееся recovery
    не давало WARN вовсе (оставалась только терминальная B3-строка в
    самом конце прогона, без per-тестовой атрибуции). Плагин `warnings`
    захватывает предупреждения из ЛЮБОЙ фазы протокола, включая хуки
    setup, поэтому перенос не меняет видимость WARN на happy path,
    только чинит путь падения соседних фикстур.

    B2 (AT-BUG-064, критик-вход rework attempt 2): `_ensure_no_residual_
    device_proxy()` вызывается ЗДЕСЬ же, рядом с `_reset_ca_check()` —
    твин уже существующего паттерна `_reset_ca_check`: СРАБАТЫВАЕТ на том же
    условии (recovery произошёл в ЭТОМ тесте), но профиль отказа другой —
    `_reset_ca_check()` только сбрасывает module-level флаг (без adb-вызова),
    а `_ensure_no_residual_device_proxy()` реально ХОДИТ В ADB
    (`mitm.ensure_no_residual_proxy()` → `settings get/put global
    http_proxy`), то есть может кинуть `TimeoutError` на нездоровом
    устройстве. Recovery ребутит эмулятор через snapshot-boot
    `tasks.ps1::Start-Emulator`, module/session-level проверка об этом не
    знает сама по себе, если её единственная точка вызова —
    `_ensure_app_installed`, session-scoped и потому инстанцируемая РОВНО
    ОДИН раз на весь прогон, до первого теста, а не после КАЖДОГО
    recovery. Заголовок AT-BUG-064 — «остаточный прокси переживает
    ПЕРЕЗАПУСК ЭМУЛЯТОРА»: recovery-путь — ровно тот перезапуск, и до
    этой правки проверка (а), добавленная attempt 1, была НЕДОСТИЖИМА
    для него (снята только на старте сессии, session-scope не
    переинстанцируется). `ensure_no_residual_proxy()` не кеширует
    результат сама (в отличие от `_ca_checked`) — каждый вызов заново
    читает `adb shell settings get global http_proxy`, поэтому
    достаточно позвать функцию повторно, без отдельного flag-сброса.

    F1 (критик-вход на AT-BUG-064, батч мелочей 0812): вызов
    `_ensure_no_residual_device_proxy()` стоит ПОСЛЕ
    `warnings.warn(_pending_recovery_warning)`, не до него — именно из-за
    adb-профиля отказа выше: если adb на нездоровом устройстве кидает
    `TimeoutError`, исключение из вызова, стоявшего РАНЬШЕ `warnings.warn`,
    глушило recovery-WARN целиком (R2 выше существует именно чтобы этот WARN
    гарантированно был виден per-тестово) — recovery-факт остался бы
    незалогированным. Порядок ПОСЛЕ `warnings.warn` не теряет диагностику
    recovery, даже если сама проверка остаточного прокси упадёт следом.

    AT-BUG-066 (сиблинг класса, критик-вход AT-BUG-064): `_ensure_default_
    font_scale()`/`_ensure_default_night_mode()` вызываются ЗДЕСЬ же, СРАЗУ
    после `_ensure_no_residual_device_proxy()` — тот же твин-паттерн, тот же
    аргумент (recovery ребутит эмулятор через snapshot-boot, session-scoped
    `_ensure_app_installed` инстанцируется РОВНО РАЗ и не видит recovery,
    случившийся посреди прогона).

    Non-blocker 2 (критик-вход rework attempt 2, spec-p3-second-emulator
    N3): `driver_factory.check_device_lease()` теперь звучит ЗДЕСЬ ЖЕ,
    ПЕРВЫМ device-related вызовом хука (до `ensure_ready()`) — не только в
    session-scoped `_ensure_app_installed` (там — разовая ранняя сверка НА
    СТАРТ сессии) и не только в `create_driver` (авторитетная точка, но
    инстанцируется ПОСЛЕ `clean_app`/`replay`/`seeded_library`, если те
    стоят раньше `driver` в сигнатуре теста — ТОТ ЖЕ порядковый класс
    риска, что B1 выше уже чинит для `ensure_ready()`: `clean_app`/`replay`
    реально трогают adb ДО того, как `driver` вообще успевает
    инстанцироваться). Незалиженный чужой стек 2 теперь падает ДО
    `pm clear`/`set_device_proxy`, не только до создания Appium-сессии.

    Отклонение от буквального текста задачи ("первой строкой pytest_
    runtest_setup... до ensure_ready()"): вызов гейтится ТЕМ ЖЕ условием
    `"driver" in item.fixturenames`, что и `ensure_ready()` ниже, а не
    стоит перед этим гейтом безусловно для КАЖДОГО теста сессии (включая
    device-free юниты) — репозиторий системно бережёт device-free пробы от
    любого adb/устройство-связанного пути (см. докстринг `_ensure_app_
    installed` про ~20 переопределяющих юнит-проб); `check_device_lease()`
    файл-based и обычно дёшев, но безусловный вызов на КАЖДОМ из тысяч
    device-free тестов сессии добавил бы стек-2-релевантную проверку туда,
    где её раньше не было вовсе, без выигрыша (device-free тест лизу не
    держит и не блокируется её отсутствием намеренно)."""
    global _pending_recovery_warning
    _pending_recovery_warning = None
    if "driver" not in item.fixturenames:
        return
    driver_factory.check_device_lease()
    _pending_recovery_warning = _DEVICE_GUARD.ensure_ready()
    if _pending_recovery_warning is not None:
        _reset_ca_check()
        warnings.warn(_pending_recovery_warning)
        _ensure_no_residual_device_proxy()
        _ensure_default_font_scale()
        _ensure_default_night_mode()


def _reset_ca_check() -> None:
    """AT-BUG-026 F4 (критик-вход attempt 3): recovery ребутит эмулятор
    (`Start-Emulator -WritableSystem` сама переустанавливает mitm-CA — см.
    `driver_factory._restart_emulator_writable_system`), но module-level кеш
    `_ca_checked` (AT-BUG-011, «проверка CA — раз на сессию») об этом не
    знает и остаётся `True`, если ХОТЯ БЫ ОДИН replay-тест этой сессии уже
    прошёл проверку раньше. Если CA почему-то НЕ переустановился в рамках
    ИМЕННО этого recovery (частичный сбой `tasks.ps1`, гонка) — следующий
    replay-тест НЕ переспросит `_ensure_replay_ca()` (кеш всё ещё `True`) и
    упрётся в 120–240с `ReadTimeoutError` вместо мгновенной понятной
    `RuntimeError`, которую сама проверка AT-BUG-011 существует, чтобы
    предотвратить — то есть контейнмент сам создал бы ИМЕННО тот класс
    каскада, который должен предотвращать. Сброс кеша ПОСЛЕ КАЖДОГО
    recovery форсирует одну дешёвую повторную проверку (adb+openssl, доли
    секунды) на первом СЛЕДУЮЩЕМ replay-тесте — happy path (CA реально
    переустановился) платит только эту проверку, несчастливый путь получает
    быстрый диагноз вместо зависания."""
    global _ca_checked
    _ca_checked = False


@pytest.fixture()
def driver():
    """Сессия Appium на тест. no_reset=True — состоянием управляют фикстуры данных.

    AT-BUG-026 (контейнмент): device-liveness guard (см. `pytest_runtest_setup`
    выше) уже отработал ДО setup ЭТОГО (и любого другого device-) теста —
    проверил присутствие устройства и, если оно исчезло (вероятностный
    qemu-краш `0xc0000005` или иной класс NO DEVICE), сделал ОГРАНИЧЕННОЕ
    авто-восстановление (см. `driver_factory.DeviceLivenessGuard` — там же
    границы: recovery только при отсутствии устройства, лимит за сессию,
    идемпотентность, честный FAILED/ERROR текущего теста без маскировки).
    Эта фикстура ЧИТАЕТ результат того вызова (`_pending_recovery_warning`),
    не вызывает `ensure_ready()` САМА (B1: единственная точка вызова —
    хук, чтобы recovery гарантированно происходил РАНЬШЕ `replay`/
    `clean_app`/`seeded_library`, а не только раньше `driver`).
    Recovery отмечается `warnings.warn`, вызванным ИЗ ХУКА
    `pytest_runtest_setup` (R2, критик-вход attempt 4 — перенесено ИЗ этой
    фикстуры, см. докстринг хука выше: `driver` инстанцируется ПОСЛЕ
    `clean_app`/`replay` по сигнатуре большинства device-тестов, и WARN,
    живущий здесь, терялся бы, если одна из НИХ падает на setup раньше)
    — WARN-атрибуция видна в отчёте прогона независимо от исхода самого
    теста; эта фикстура сама `warnings.warn` больше не зовёт, только читает
    `_pending_recovery_warning` для `settle_retries`.
    Лимит исчерпан -> `DeviceRecoveryError` (сообщение начинается с
    `ENV_ISSUE`) поднимается из хука ДО setup ЛЮБОЙ фикстуры теста —
    короткое замыкание, не 20-секундный таймаут на каждом следующем тесте.

    `settle_retries=2` передаётся `create_driver` ТОЛЬКО когда recovery
    произошёл В ЭТОМ тесте (`warn_message is not None`) — находка красной
    пробы w1 (2026-07-28): первая Appium-сессия сразу после рестарта
    эмулятора иногда не успевает "устояться" (`bugs/AT-BUG-026.md`, известный
    класс). Обычный путь (recovery не требовался) settle_retries=0 — поведение
    не меняется."""
    warn_message = _pending_recovery_warning
    drv = driver_factory.create_driver(
        no_reset=True, settle_retries=(2 if warn_message is not None else 0)
    )
    yield drv
    driver_factory.quit_driver(drv)


@pytest.fixture()
def clean_app():
    """Чистое приложение (pm clear) ДО старта сессии. Возвращает фабрику драйвера."""
    app_steps.clean_state()
    yield


@pytest.fixture()
def seeded_library():
    """Библиотека с по одной работе на каждый рейтинг (без обращения к AO3).
    Сидинг делается до создания сессии Appium."""
    app_steps.clean_state()
    app_steps.seed_library([
        (W.LOVED, "SAVE"),
        (W.KUDOSED, "LIKE"),
        (W.READ, "READ"),
        (W.PENDING, "PENDING"),
        (W.DISLIKED, "DISLIKE"),
    ])
    yield W


@pytest.fixture()
def loved_work_seeded():
    """Работа LOVED засеяна с рейтингом SAVE (Favorite) до старта сессии Appium —
    тот же порядок обязателен, что и в `seeded_library`/`comment_only_work`: иначе
    driver успевает запустить приложение до сидинга, а `pm clear`/сидинг после
    запуска сессии не перезапускает уже работающий процесс (WebView остаётся в
    неопределённом состоянии — см. TC-008)."""
    app_steps.clean_state()
    app_steps.seed_library([(W.LOVED, "SAVE")])
    yield W.LOVED


@pytest.fixture()
def kudosed_work_seeded():
    """Работа LOVED засеяна с рейтингом LIKE (Kudosed) до старта сессии Appium —
    тот же порядок и то же обоснование, что `loved_work_seeded` (см. её
    докстринг). Нужна для области rating/bridge: авто-клик kudos
    (TC-139/142/143, docs/01-test-strategy.md §9) — негативы, стартующие из
    уже-Kudosed состояния, без личных тегов."""
    app_steps.clean_state()
    app_steps.seed_library([(W.LOVED, "LIKE")])
    yield W.LOVED


@pytest.fixture()
def placeholder_seeded_work(request):
    """Работа `request.param` засеяна как placeholder БЕЗ рейтинга (rating=None), но
    с полными title/author/fandom/wordCount — до старта сессии Appium (тот же порядок,
    что и `seeded_library`). Нужна для TC-007: `savePanelRating` (BrowserViewModel.kt)
    скрейпит title/author из живого DOM страницы работы только когда для `workId` ещё
    нет строки в Room; для синтетических `ao3_id` (не существующих на archiveofourown.org)
    скрейп страницы вернёт пустые поля. Предзаполненный placeholder переводит панель на
    ветку "обновить существующую строку" — без сетевого скрейпа, см. test_rating.py."""
    work = request.param
    app_steps.clean_state()
    app_steps.seed_with_comment([(work, None, None, None)])
    yield work


def _seed_downloaded_work_default() -> tuple[Work, str]:
    """Общий сидинг LOVED/SAVE + скачанный локальный HTML-файл — один вызов,
    используемый ОБОИМИ `downloaded_work_seeded` (ниже, только `Work`) и
    `downloaded_work_seeded_with_path` (`Work` + device-путь, TC-174/TC-189) —
    не копия сидинг-логики (F1-ревью TC-174 замечание 2, D-0043 «чини класс, а не
    экземпляр»: было — тест-файл дублировал эту фикстуру почти дословно ради
    единственного отличия, возврата пути)."""
    app_steps.clean_state()
    device_path = app_steps.seed_downloaded_work(W.LOVED, "SAVE", _DOWNLOADED_WORK_FIXTURE)
    return W.LOVED, device_path


@pytest.fixture()
def downloaded_work_seeded():
    """Работа LOVED засеяна с рейтингом Loved (SAVE) и уже «скачанным» локальным
    HTML-файлом (downloadPath заполнен, файл реально существует на устройстве) —
    без сетевого скачивания (DownloadRepository не задействован), см.
    TC-034/TC-035/TC-036. Тот же порядок (clean_state до сессии Appium), что и
    seeded_library/loved_work_seeded — обязателен."""
    work, _device_path = _seed_downloaded_work_default()
    yield work


@pytest.fixture()
def downloaded_work_seeded_with_path():
    """Как `downloaded_work_seeded` (тот же сидинг через общий хелпер
    `_seed_downloaded_work_default`, без копии логики), но ДОПОЛНИТЕЛЬНО
    возвращает device-путь `downloadPath` (нужен TC-174/TC-189, чтобы собрать
    ожидаемый `file://`-URL той же формулой, что `WorkRating.localFileUrl()`
    (LibraryScreen.kt:345-347: `file://$path`, path уже НЕ несёт схему), не
    хардкодя путь — тот же приём, что
    `test_security_file_access.py::_PROBE_TARGET_ABS_PATH`, только путь здесь
    получен из фактического возврата сидинга, а не собран вручную)."""
    work, device_path = _seed_downloaded_work_default()
    yield work, device_path


# TC-256 (AT-BUG-074): baseline с ЛОКАЛЬНЫМИ title/fandom/wordCount, отличными
# от канонических значений work-страницы `listing_basic.mitm` несёт для
# `W.LOVED` (`"A Loved Test Work"`/`"Fandom Alpha"`/`4200`, см.
# `recording_builder.py::render_work_page_html`/`ALL_WORKS`) — тот же приём,
# что Given TC-151/TC-152 (`test-cases/rating/TC-256.md` «Предусловия»):
# ao3_id ДОЛЖЕН совпадать с `W.LOVED.ao3_id` (единственный, чья work-страница
# записана в `listing_basic.mitm`), но title/fandom/wordCount — намеренно
# ДРУГИЕ значения, чтобы Then кейса (локальные метаданные НЕ перезаписываются
# скрейпом) был содержателен, а не тривиален совпадением.
_TC256_LOCAL_WORK = Work(
    W.LOVED.ao3_id, "ЛОКАЛЬНЫЙ заголовок", W.LOVED.author, "Мой фандом", 777777
)


@pytest.fixture()
def tc256_auto_read_baseline():
    """Работа W (`ao3_id` = `W.LOVED.ao3_id`) засеяна ОДНОЙ строкой
    (`seed_db.seed_with_comment_and_download`, AT-BUG-046): `rating=None`,
    комментарий `"note A"`, тег `"tagA"`, ЛОКАЛЬНЫЕ `title`/`fandom`/
    `wordCount` (`_TC256_LOCAL_WORK`, отличные от канонической work-страницы
    фикстуры) и реальный скачанный файл на устройстве (`downloadPath`) — до
    старта сессии Appium (тот же порядок/обоснование, что `loved_work_seeded`
    и остальные `*_seeded` фикстуры выше). Возвращает `(work, device_path)`."""
    app_steps.clean_state()
    tags_json = json.dumps(["tagA"])
    rows = [(_TC256_LOCAL_WORK, None, "note A", tags_json, _DOWNLOADED_WORK_FIXTURE)]
    device_paths = app_steps.seed_with_comment_and_download(rows)
    yield _TC256_LOCAL_WORK, device_paths[_TC256_LOCAL_WORK.ao3_id]


@pytest.fixture()
def library_all_one_rating_seeded():
    """5 работ `works.ALL` засеяны с ОДНИМ рейтингом (PENDING) — все пять оказываются
    на одной вкладке Library, что нужно для TC-027 (фильтр word count)/TC-029
    (фильтр по фандому): фильтр сравнивает работы в пределах одной вкладки, а не
    вперемешку с рейтинговой раскладкой по вкладкам (см. заметки в телах кейсов).
    Порядок (clean_state до сессии Appium) — тот же контракт, что и seeded_library."""
    app_steps.clean_state()
    app_steps.seed_library([(w, "PENDING") for w in W.ALL])
    yield W.ALL


@pytest.fixture()
def library_word_count_boundary_seeded():
    """`works.ALL` + два work'а с word_count РОВНО на границах диапазона фильтра
    ([1000, 5000] — `WORD_COUNT_MIN_BOUNDARY`/`WORD_COUNT_MAX_BOUNDARY`), все с
    ОДНИМ рейтингом (PENDING) на одной вкладке — нужно для TC-027 (C4-ретрофит
    2026-07-18): доказать включительность границ фильтра (`>= min`/`<= max`),
    непроверяемую на исходной пятёрке `ALL` (ни одно её значение не совпадает
    с 1000/5000 точно). ОТДЕЛЬНАЯ фикстура от `library_all_one_rating_seeded`
    (не расширяет её состав) — та же пятёрка используется TC-029 (фильтр по
    фандому), которому 2 лишние работы не нужны."""
    app_steps.clean_state()
    rows = [(w, "PENDING") for w in W.ALL] + [
        (W.WORD_COUNT_MIN_BOUNDARY, "PENDING"),
        (W.WORD_COUNT_MAX_BOUNDARY, "PENDING"),
    ]
    app_steps.seed_library(rows)
    yield W.ALL + [W.WORD_COUNT_MIN_BOUNDARY, W.WORD_COUNT_MAX_BOUNDARY]


@pytest.fixture()
def library_wordcount_scroll_seeded():
    """`works.ALL` + `works.SCROLL_FILLERS` (10 доп. работ с малым word_count), все с
    ОДНИМ рейтингом (PENDING) на одной вкладке — список выше высоты экрана, нужен
    для TC-030 (проверка сброса скролла при смене сортировки на Word count high-to-low:
    филлеры с малым word_count гарантированно уходят в конец после сортировки, не
    мешая проверке относительного порядка пяти эталонных работ)."""
    app_steps.clean_state()
    rows = [(w, "PENDING") for w in W.ALL] + [(w, "PENDING") for w in W.SCROLL_FILLERS]
    app_steps.seed_library(rows)
    yield W.ALL


@pytest.fixture()
def library_downloaded_only_seeded():
    """3 работы с одним рейтингом (SAVE/Favorite): 2 без файла (downloadPath=null), 1 —
    с уже «скачанным» локальным файлом (downloadPath заполнен, файл реально существует
    на устройстве) — без сетевого скачивания, тот же приём, что и downloaded_work_seeded
    (TC-034/035/036). Нужна для TC-028 (фильтр downloaded-only).

    Сидинг в ДВА последовательных вызова: сначала обе без-файловые строки через
    `seed_library` (seed_db.seed), затем файловая — через `seed_downloaded_work`
    (seed_db.seed_with_download). Второй вызов пуллит уже записанную первым вызовом
    БД с устройства и ДОБАВЛЯЕТ свою строку (INSERT OR REPLACE по ao3Id, см.
    seed_db._insert_rows_with_download) — прежние две строки не затираются, это тот
    же паттерн, каким уже сосуществуют последовательные сидинг-вызовы в этом файле.
    Порядок (clean_state до сессии Appium) — тот же контракт, что и остальные
    фикстуры данных."""
    app_steps.clean_state()
    app_steps.seed_library([(W.KUDOSED, "SAVE"), (W.READ, "SAVE")])
    app_steps.seed_downloaded_work(W.LOVED, "SAVE", _DOWNLOADED_WORK_FIXTURE)
    yield {"downloaded": W.LOVED, "no_file": [W.KUDOSED, W.READ]}


@pytest.fixture()
def library_null_wordcount_seeded():
    """TC-031: 2 работы с валидным word_count (READ=800, LOVED=4200) +
    `works.NULL_WORD_COUNT_TARGET` (word_count=None), все три с ОДНИМ рейтингом
    (PENDING) на одной вкладке — граница отсутствующего word_count в сортировке
    (AT-BUG-010, Fixed). `seed_library`/`seed()` уже достаточно — `Work.word_count`
    типизирован `int | None`, `seed_with_comment` не нужен (rating не NULL, comment/
    tags не участвуют)."""
    app_steps.clean_state()
    app_steps.seed_library([
        (W.READ, "PENDING"),
        (W.LOVED, "PENDING"),
        (W.NULL_WORD_COUNT_TARGET, "PENDING"),
    ])
    yield {"with_wordcount": [W.READ, W.LOVED], "null_wordcount": W.NULL_WORD_COUNT_TARGET}


@pytest.fixture()
def library_tags_and_seeded():
    """TC-060: 3 работы с ОДНИМ рейтингом (SAVE), различающиеся только `tags` —
    W1 оба выбранных тега, W2 только один (частичное пересечение), W3 ни одного.
    Работы не входят в `works.ALL` (специфичны для этого кейса) — созданы напрямую,
    тот же приём, что и `NULL_WORD_COUNT_TARGET`/`WORD_COUNT_MIN_BOUNDARY`."""
    app_steps.clean_state()
    w1 = Work("900000601", "TC-060 Both Tags Work", "seed_author_tc060_w1", "Fandom TC060", 1000)
    w2 = Work("900000602", "TC-060 One Tag Work", "seed_author_tc060_w2", "Fandom TC060", 1000)
    w3 = Work("900000603", "TC-060 No Match Work", "seed_author_tc060_w3", "Fandom TC060", 1000)
    app_steps.seed_with_comment([
        (w1, "SAVE", None, json.dumps(["fluff", "hurt-comfort"])),
        (w2, "SAVE", None, json.dumps(["fluff"])),
        (w3, "SAVE", None, json.dumps(["canon-divergent"])),
    ])
    yield (w1, w2, w3)


@pytest.fixture()
def library_freetext_search_seeded():
    """TC-061: 3 работы с ОДНИМ рейтингом (SAVE) — только W1 содержит подстроку
    "wintersong" (в `comment`), W2/W3 не содержат её ни в одном текстовом поле
    (title/author/fandom/tags/comment)."""
    app_steps.clean_state()
    w1 = Work("900000611", "TC-061 Match In Comment Work", "seed_author_tc061_w1",
              "Fandom TC061 Alpha", 1000)
    w2 = Work("900000612", "TC-061 No Match Work Two", "seed_author_tc061_w2",
              "Fandom TC061 Beta", 1000)
    w3 = Work("900000613", "TC-061 No Match Work Three", "seed_author_tc061_w3",
              "Fandom TC061 Gamma", 1000)
    app_steps.seed_with_comment([
        (w1, "SAVE", "Reread this every wintersong", None),
        (w2, "SAVE", None, None),
        (w3, "SAVE", None, None),
    ])
    yield (w1, w2, w3)


@pytest.fixture()
def library_last_read_order_seeded():
    """TC-062: 3 работы с ОДНИМ рейтингом (SAVE), засеянные ОДНИМ вызовом
    `seed_with_comment_ordered` — каждая получает СТРОГО возрастающий
    `timestamp` по своей позиции в списке (см. `seed_db._insert_rows_full_
    ordered`), в хронологическом порядке Mango -> Apple -> Zebra (Mango —
    наименьший `timestamp`, Zebra — наибольший, первая в `ORDER BY timestamp
    DESC`). Заголовки подобраны так, чтобы ни порядок вставки, ни алфавит не
    совпадали с ожидаемым порядком по `timestamp` (Zebra, Apple, Mango).

    Rework attempt 2 (критик-вход TC-186-188 B3, 2026-08-14): раньше — ТРИ
    ПОСЛЕДОВАТЕЛЬНЫХ вызова `seed_with_comment` (по одной работе на вызов,
    каждый свой `force_stop()`/`ensure_db_initialized()` round-trip) — тот же
    класс экспозиции гонке `bugs/AT-BUG-069.md` (`regression_of:
    AT-BUG-044`), что закрыл `seed_ordered` для TC-187, только ТРИ round-trip
    вместо двух. Мигрирована на `seed_with_comment_ordered` — ОДИН round-trip,
    порядок `timestamp` гарантирован локально по позиции в списке."""
    app_steps.clean_state()
    mango = Work("900000621", "Mango Work", "seed_author_tc062_mango", "Fandom TC062", 1000)
    apple = Work("900000622", "Apple Work", "seed_author_tc062_apple", "Fandom TC062", 1000)
    zebra = Work("900000623", "Zebra Work", "seed_author_tc062_zebra", "Fandom TC062", 1000)
    app_steps.seed_with_comment_ordered([
        (mango, "SAVE", None, None),
        (apple, "SAVE", None, None),
        (zebra, "SAVE", None, None),
    ])
    yield (mango, apple, zebra)


@pytest.fixture()
def library_author_sort_seeded():
    """TC-064: 3 работы с ОДНИМ рейтингом (PENDING) — W1 author="Zoe Martinez",
    W2 author="Amy Chen", W3 author="" (пустой, допустим схемой) — плюс
    `works.SCROLL_FILLERS` (непустой author) для гарантированного скролла, тот
    же приём, что TC-030/TC-063."""
    app_steps.clean_state()
    w1 = Work("900000641", "TC-064 Zoe Work", "Zoe Martinez", "Fandom TC064", 1000)
    w2 = Work("900000642", "TC-064 Amy Work", "Amy Chen", "Fandom TC064", 1000)
    w3 = Work("900000643", "TC-064 Empty Author Work", "", "Fandom TC064", 1000)
    rows = [(w1, "PENDING"), (w2, "PENDING"), (w3, "PENDING")] + [
        (w, "PENDING") for w in W.SCROLL_FILLERS
    ]
    app_steps.seed_library(rows)
    yield (w1, w2, w3)


@pytest.fixture()
def library_files_rating_seeded():
    """TC-065: `works.ALL`, каждая с рейтингом, соответствующим её "естественному"
    имени (LOVED=SAVE, KUDOSED=LIKE, READ=READ, PENDING=PENDING, DISLIKED=DISLIKE —
    тот же маппинг, что `seeded_library`), и с уже «скачанным» локальным HTML-файлом
    (общий переиспользуемый файл `_DOWNLOADED_WORK_FIXTURE`, downloadPath заполнен) —
    все 5 видны на вкладке Files. Засеяны ОДНИМ батчем в порядке DISLIKED, PENDING,
    READ, KUDOSED, LOVED (обратном ожидаемому результату сортировки Rating) —
    защита от случайного совпадения результата с порядком вставки."""
    app_steps.clean_state()
    app_steps.seed_downloaded_works([
        (W.DISLIKED, "DISLIKE", _DOWNLOADED_WORK_FIXTURE),
        (W.PENDING, "PENDING", _DOWNLOADED_WORK_FIXTURE),
        (W.READ, "READ", _DOWNLOADED_WORK_FIXTURE),
        (W.KUDOSED, "LIKE", _DOWNLOADED_WORK_FIXTURE),
        (W.LOVED, "SAVE", _DOWNLOADED_WORK_FIXTURE),
    ])
    yield W.ALL


@pytest.fixture()
def library_mixed_download_status_seeded():
    """B2 (misc-batch-lead-queue-0729, attempt 2, критик-вход) — device-witness
    card-scoped дискриминации `has_download_icon`/`has_open_icon`
    (`_card_icon_locator`, `library_screen.py`): раньше это утверждалось только
    по факту XPath-скоупа (батч мелочей D-0081) — КАЖДЫЙ существующий
    потребитель (TC-032/033/034/035/115/065) засеивает работы с ОДИНАКОВЫМ
    download-статусом (все скачаны или ни одной), так что дискриминация между
    РАЗНЫМИ статусами на одной вкладке ни разу не проверялась на живом дереве.

    ДВЕ работы, ОДИН рейтинг (PENDING — одна вкладка): `W.PENDING` засеяна
    БЕЗ downloadPath (`seed_library`, обычная карточка — download-иконка),
    `W.DISLIKED` засеяна С downloadPath (`seed_downloaded_work`,
    open-иконка) — рейтинг переопределён (не «естественный» DISLIKE), это
    легитимно: `seed_downloaded_work` принимает рейтинг параметром независимо
    от идентичности `Work` (тот же приём, что TC-064 в этом файле — синтетические
    `Work` с рейтингом, не совпадающим с именем).

    Порядок вызовов ОБЯЗАТЕЛЕН: `seed_library` ПЕРВЫМ кладёт baseline-строку
    `W.PENDING` (downloadPath=null); `seed_downloaded_work` ВТОРЫМ пуллит УЖЕ
    записанный baseline (см. `seed_db._pull_baseline`) и добавляет свою строку
    `W.DISLIKED` рядом, не затирая первую (`INSERT OR REPLACE` бьёт по разным
    `ao3Id`) — обратный порядок оставил бы только одну строку."""
    app_steps.clean_state()
    app_steps.seed_library([(W.PENDING, "PENDING")])
    app_steps.seed_downloaded_work(W.DISLIKED, "PENDING", _DOWNLOADED_WORK_FIXTURE)
    yield W.PENDING, W.DISLIKED


@pytest.fixture()
def library_favorite_scroll_and_disliked_neighbor_seeded():
    """TC-177 (library batch 2, story #28): вкладка Favorite (SAVE) прокручиваема
    (5 эталонных `W.ALL` + `W.SCROLL_FILLERS`, тот же приём, что TC-030/TC-063 —
    сортировка НЕ трогается, остаётся дефолтной Last read). Вкладка Disliked
    засеяна ОТДЕЛЬНОЙ работой (не входит в `W.ALL`, чтобы не задваивать её
    рейтинг) — нужна только как «соседняя вкладка, достаточно далеко, чтобы
    Favorite была утилизирована пейджером», прокручиваемость Disliked не
    требуется (см. Предусловия TC-177)."""
    app_steps.clean_state()
    disliked_neighbor = Work("900000177", "TC-177 Disliked Neighbor Work",
                              "seed_author_tc177", "Fandom TC177", 500)
    rows = [(w, "SAVE") for w in W.ALL] + [(w, "SAVE") for w in W.SCROLL_FILLERS] + [
        (disliked_neighbor, "DISLIKE"),
    ]
    app_steps.seed_library(rows)
    yield {"favorite": W.ALL, "disliked_neighbor": disliked_neighbor}


@pytest.fixture()
def library_favorite_and_files_scroll_seeded():
    """TC-178/TC-179 (library batch 2, story #28) — общая фикстура (заметки
    обоих кейсов допускают переиспользование): ОБЕ вкладки прокручиваемы.

    - Favorite (SAVE) — 5 эталонных `W.ALL` + `W.SCROLL_FILLERS` (без
      downloadPath), тот же приём, что TC-030/TC-063/TC-177.
    - Files — `W.FILES_SCROLL_FILLERS` (10 работ, downloadPath заполнен через
      `seed_downloaded_works`, рейтинг PENDING — сама вкладка Files определяется
      наличием `downloadPath`, не рейтингом, `LibraryViewModel.kt:67/:75`),
      каждая с УНИКАЛЬНЫМ word_count (21..30) — нужно для TC-179 (немедленный
      Word-count-реордер активной вкладки Files, в отличие от отложенного
      сброса Favorite).

    Порядок вызовов ОБЯЗАТЕЛЕН: `seed_library` (Favorite) первым кладёт
    baseline, `seed_downloaded_works` (Files) вторым добавляет свои строки
    рядом (тот же контракт, что `library_mixed_download_status_seeded` выше)."""
    app_steps.clean_state()
    favorite_rows = [(w, "SAVE") for w in W.ALL] + [(w, "SAVE") for w in W.SCROLL_FILLERS]
    app_steps.seed_library(favorite_rows)
    files_rows = [(w, "PENDING", _DOWNLOADED_WORK_FIXTURE) for w in W.FILES_SCROLL_FILLERS]
    app_steps.seed_downloaded_works(files_rows)
    yield {"favorite": W.ALL, "files": W.FILES_SCROLL_FILLERS}


@pytest.fixture()
def comment_only_work():
    """Одна работа засеяна как comment-only (rating=NULL, непустой comment) —
    без обращения к AO3. Сидинг делается до создания сессии Appium (см.
    seeded_library — тот же порядок обязателен, иначе драйвер успевает
    запустить приложение раньше сидинга)."""
    app_steps.clean_state()
    app_steps.seed_with_comment([(W.KUDOSED, None, "test note", None)])
    yield W.KUDOSED


@pytest.fixture()
def disliked_work_with_tags_seeded():
    """TC-045: ПАРА работ с ОДИНАКОВЫМИ личными тегами, различающихся только
    `rating` — доказывает независимость видимости от `tags` как СВОЙСТВО, не на
    единичном примере (test-reviewer changes_requested, 2026-07-18): `W.DISLIKED`
    (скрывается фильтрацией по умолчанию — Disliked в hidden-set) и `W.LOVED`
    (rating=SAVE, НЕ в hidden-set) засеяны с ОДНИМ и тем же набором тегов
    `["spoiler", "reread-candidate"]`. Если бы `tags` хоть как-то влияли на
    excluded/visible, одинаковые теги дали бы одинаковый исход для обеих работ —
    вместо этого исход противоположный (DISLIKED скрыта, LOVED видна), что и
    доказывает, что переключает видимость исключительно `rating`
    (`applyAllFilters`, `ao3_bridge.js`, читает только `ratings[workId]`/`hidden`,
    см. TC-045.md «Причина»)."""
    app_steps.clean_state()
    tags = json.dumps(["spoiler", "reread-candidate"])
    app_steps.seed_with_comment([
        (W.DISLIKED, "DISLIKE", None, tags),
        (W.LOVED, "SAVE", None, tags),
    ])
    yield W.DISLIKED, W.LOVED


@pytest.fixture()
def disliked_work_with_comment_seeded():
    """TC-075: работа `works.DISLIKED` засеяна с рейтингом DISLIKE и непустым
    комментарием "TC-075 seeded comment" — Note-кнопка на replay-листинге
    инжектируется тогда и только тогда, когда есть comment (тот же контракт, что
    `note_work_seeded`/TC-044, на работе DISLIKED вместо READ, см. AT-BUG-023)."""
    app_steps.clean_state()
    app_steps.seed_with_comment([(W.DISLIKED, "DISLIKE", "TC-075 seeded comment", None)])
    yield W.DISLIKED


@pytest.fixture()
def disliked_work_with_custom_tag_seeded():
    """TC-077: работа `works.DISLIKED` засеяна с рейтингом DISLIKE и личным тегом
    "tc077-custom-tag", заведомо отсутствующим среди AO3-тегов карточки в
    `listing_basic.mitm` — Tag-кнопка на replay-листинге инжектируется тогда и
    только тогда, когда есть личный тег вне AO3-тегов (тот же контракт, что
    `tagged_work_seeded`/TC-056, на работе DISLIKED, см. AT-BUG-023)."""
    app_steps.clean_state()
    app_steps.seed_with_comment([
        (W.DISLIKED, "DISLIKE", None, json.dumps(["tc077-custom-tag"])),
    ])
    yield W.DISLIKED


@pytest.fixture()
def tagged_work_seeded():
    """TC-056: работа `works.LOVED` засеяна с рейтингом LIKE и личными тегами
    `["Fluff", "Angst"]` — «Fluff» совпадает (без учёта регистра) с freeform-тегом
    карточки, зашитым в КАЖДЫЙ блёрб `listing_basic.mitm`
    (`recording_builder._blurb_html`), «Angst» не совпадает ни с одним AO3-тегом
    фикстуры."""
    app_steps.clean_state()
    app_steps.seed_with_comment([
        (W.LOVED, "LIKE", None, json.dumps(["Fluff", "Angst"])),
    ])
    yield W.LOVED


@pytest.fixture()
def note_work_seeded():
    """TC-044: работа `works.READ` засеяна с рейтингом LIKE и непустым комментарием —
    Note-кнопка (карандаш) на листинге инжектируется `applyRatings` только когда для
    работы есть непустой `comment` (см. `ao3_bridge.js`)."""
    app_steps.clean_state()
    app_steps.seed_with_comment([(W.READ, "LIKE", "Existing note text", None)])
    yield W.READ


@pytest.fixture()
def note_and_tags_work_seeded():
    """TC-089: работа `works.PENDING` засеяна ОДНИМ вызовом `seed_with_comment` с
    рейтингом Pending, непустым комментарием "Library indicator note" и непустым
    JSON-списком личных тегов `["indicator-tag"]` — комбинация полей, которую ни
    одна существующая фикстура не покрывает целиком (`note_work_seeded` не сидит
    `tags`, `tagged_work_seeded`/`disliked_work_with_tags_seeded` не сидят
    `comment`), нужная для проверки, что ОБА индикатора карточки Library
    (note-иконка и строка тегов) читаются из одной и той же строки `WorkRating`."""
    app_steps.clean_state()
    app_steps.seed_with_comment([
        (W.PENDING, "PENDING", "Library indicator note", json.dumps(["indicator-tag"])),
    ])
    yield W.PENDING


@pytest.fixture()
def two_filter_profiles_seeded():
    """Два фильтр-профиля ("Profile A"/"Profile B", различимые queryString) засеяны
    в `filter_profiles` ДО старта сессии Appium — тот же порядок обязателен, что и
    `seeded_library` (AT-BUG-006, грань 3: TC-042 требует ДВА одновременных профиля,
    чтобы отличить «удалён именно нужный» от «весь список случайно очищен»).
    `seed_db.seed_filter_profiles` генерирует `id`/`timestamp` сама — вызывающему
    коду (кейсам) они не нужны, сверка по имени/queryString."""
    app_steps.clean_state()
    app_steps.seed_filter_profiles([
        ("Profile A", "work_search%5Bquery%5D=profile-a-test"),
        ("Profile B", "work_search%5Bquery%5D=profile-b-test"),
    ])
    yield ("Profile A", "Profile B")


@pytest.fixture()
def filter_profile_applied_seeded():
    """Один фильтр-профиль ("My saved search") засеян ДО старта сессии Appium (тот
    же порядок, что `two_filter_profiles_seeded`) — TC-041: применение сохранённого
    профиля из FilterPanel листинга.

    `queryString` — НЕ произвольная строка (в отличие от `two_filter_profiles_seeded`,
    где кейс TC-042 никогда не навигирует по ней): это РОВНО
    `recording_builder.FILTER_APPLIED_QUERY_STRING`, подобранный так, что
    `applyFilter` (BrowserViewModel.kt) построит URL, БАЙТ-В-БАЙТ совпадающий с
    `recording_builder.LISTING_FILTERED_URL` — вторым flow, записанным в
    `listing_basic.mitm` (`scripts/build_replay_recordings.py::build_listing_basic`).
    Без этого совпадения server-replay не находит flow и уходит в live-сеть
    (`server_replay_extra=forward`) — см. докстринг `LISTING_FILTERED_URL`."""
    app_steps.clean_state()
    app_steps.seed_filter_profiles([("My saved search", rb.FILTER_APPLIED_QUERY_STRING)])
    yield "My saved search"


@pytest.fixture()
def library_and_filter_profile_seeded():
    """TC-197 (баннер скрытых работ, четыре варианта таблицы истинности
    `ratedHidden × filterActive`): объединяет `seeded_library` (по одной работе
    на каждый рейтинг, в т.ч. `W.DISLIKED` с `rating=DISLIKE`) И
    `filter_profile_applied_seeded` (профиль "My saved search",
    `queryString=rb.FILTER_APPLIED_QUERY_STRING`, тот же байт-в-байт URL, что
    `rb.LISTING_FILTERED_URL`) — ОДНА фикстура для ВСЕХ четырёх вариантов
    кейса, а не отдельная на каждый: варианты A/D не выбирают сохранённый
    профиль (наличие незадействованной строки `filter_profiles` не влияет ни
    на один их Then), варианты B/C выбирают. Обе таблицы (`WorkRating` и
    `filter_profiles`) независимы — порядок вызовов `seed_library`/
    `seed_filter_profiles` друг на друга не влияет (в отличие от
    `library_mixed_download_status_seeded`, где порядок ОБЯЗАТЕЛЕН из-за
    общей baseline-строки той же таблицы)."""
    app_steps.clean_state()
    app_steps.seed_library([
        (W.LOVED, "SAVE"),
        (W.KUDOSED, "LIKE"),
        (W.READ, "READ"),
        (W.PENDING, "PENDING"),
        (W.DISLIKED, "DISLIKE"),
    ])
    app_steps.seed_filter_profiles([("My saved search", rb.FILTER_APPLIED_QUERY_STRING)])
    yield "My saved search"


_ca_checked = False  # AT-BUG-011: fail-fast проверка mitm-CA — один раз на сессию


def _ensure_replay_ca() -> None:
    """Предусловие replay-тестов (AT-BUG-011): без mitm-CA в системном APEX-сторе
    WebView отвергает TLS к mitmproxy, и тест виснет `ReadTimeoutError` через
    120–240с (APPIUM_HTTP_TIMEOUT x rerun-гейт AT-BUG-007) вместо мгновенной
    понятной ошибки. Кешируется в module-level `_ca_checked` — проверяется
    (adb + openssl вызов) один раз на первом replay-тесте сессии, не на каждом."""
    global _ca_checked
    if _ca_checked:
        return
    if not mitm.is_ca_installed():
        raise RuntimeError(
            "mitm-CA отсутствует в системном сторе доверия (стирается любым "
            "ребутом эмулятора без -writable-system) — поднимите среду "
            "`Start-Emulator -WritableSystem` или выполните "
            "`Install-MitmCA`/`bash scripts/install-mitm-ca.sh` (AT-BUG-011)."
        )
    _ca_checked = True


_upstream_checked = False  # ESC-009: fail-fast проверка апстрима — один раз на сессию


def _ensure_upstream_fast() -> None:
    """Предусловие replay-тестов (ESC-009): апстрим `mitm.assert_upstream_fast()`
    (см. `framework/core/mitm.py` — диагноз «мёртвый IPv6-транзит хоста»)
    проверяется РАЗ на сессию, тем же паттерном module-level кеша, что
    `_ca_checked`/`_ensure_replay_ca()` (AT-BUG-011) чуть выше. Не связано с
    device-liveness recovery (`_reset_ca_check`) — состояние сетевого
    транзита хоста не меняется рестартом эмулятора, поэтому отдельный флаг
    не сбрасывается тем хуком."""
    global _upstream_checked
    if _upstream_checked:
        return
    mitm.assert_upstream_fast()
    _upstream_checked = True


def _proxy_reachable_timeout() -> int | None:
    """N2 (критик-вход attempt 4): выбор таймаута ожидания достижимости
    прокси СО СТОРОНЫ УСТРОЙСТВА, вынесенный из тела фикстуры `replay` в
    отдельную ЧИСТУЮ функцию — единственная причина: сделать выбор
    таймаута device-free-тестируемым. `replay` — генераторная фикстура
    (`mitm.set_device_proxy()`/`start_replay()`/реальный файл записи), её
    саму напрямую не вызвать вне pytest-инстанцирования (pytest 9 запрещает
    прямой вызов декорированной fixture-функции); эта функция несёт РОВНО
    решающую логику (см. `replay` ниже, найдено красной пробой w1,
    2026-07-28) и не трогает сеть/устройство — читает только module-level
    `_pending_recovery_warning` и `settings.PROXY_DEVICE_REACHABLE_TIMEOUT_
    AFTER_RECOVERY`. Recovery произошёл В ЭТОМ тесте -> увеличенный
    таймаут; иначе -> `None` (дефолт `mitm.wait_device_proxy_reachable`,
    поведение до находки w1 не меняется)."""
    if _pending_recovery_warning is not None:
        return settings.PROXY_DEVICE_REACHABLE_TIMEOUT_AFTER_RECOVERY
    return None


@pytest.fixture()
def replay(request):
    """Поднимает mitmdump в режиме server-replay на записи `request.param` (имя файла
    в `framework/data/recordings/`) и направляет прокси устройства на него на время
    теста; гарантированный teardown возвращает прокси и глушит mitmdump независимо от
    исхода теста. Параметризуется indirect'ом (см. `test_visibility.py`) —
    `@pytest.mark.parametrize("replay", [<filename>], indirect=True)`.

    Требует `@pytest.mark.replay` на тесте (см. `pytest_configure`) и окружение,
    доведённое до Спайка B: эмулятор запущен с `-writable-system`
    (`Start-Emulator -WritableSystem`) и CA mitmproxy установлен
    (`bash scripts/install-mitm-ca.sh`) — см. `docs/environment-setup.md`.
    Подключение к conftest — часть AT-BUG-004, инкремент 1 (сам механизм record→replay
    доказан спайком B, до этой фикстуры не был подключён ни к одному тесту).
    Перед стартом проверяет присутствие CA (`_ensure_replay_ca`, AT-BUG-011) —
    падает мгновенно и явно вместо таймаута, если среда поднята без CA. Сразу
    следом проверяет достижимость АПСТРИМА прокси->AO3 (`_ensure_upstream_fast`,
    ESC-009) — плечо, непокрытое AT-BUG-017 (тот проверяет только
    устройство->хост-прокси): без этой проверки мёртвый IPv6-транзит хоста
    даёт не мгновенный отказ, а ~166с `ReadTimeoutError` на первой навигации.
    После `set_device_proxy()`+`start_replay()` ждёт достижимости прокси СО
    СТОРОНЫ УСТРОЙСТВА (`mitm.wait_device_proxy_reachable`, AT-BUG-017) — до
    `yield`: `start_replay()` подтверждает готовность только хост-порта, а
    первая навигация теста иногда ловила интермиттентный
    `net::ERR_PROXY_CONNECTION_FAILED` (race NAT-уровня qemu / задержка
    применения системной настройки прокси Android'ом), не покрытый
    rerun-whitelist `pytest.ini` — тест теперь не видит этот транзиент.

    AT-BUG-026 B1, находка красной пробы w1 (attempt 3): ЕСЛИ device-liveness
    recovery произошёл В ЭТОМ тесте (`_pending_recovery_warning is not None`
    — тот же признак, что использует `driver` для `settle_retries`) —
    достижимость прокси ждём увеличенным таймаутом
    (`settings.PROXY_DEVICE_REACHABLE_TIMEOUT_AFTER_RECOVERY`): СРАЗУ после
    restart эмулятора (который ТАКЖЕ переустанавливает CA и рестартует
    framework/zygote) сетевой adb-мост/NAT иногда не успевает settle'иться за
    дефолтные 10s — живой witness этой сессии поймал `TimeoutError` на 26
    попытках. Обычный путь (recovery не требовался) таймаут не меняется —
    поведение до этой находки идентично. Сам выбор таймаута вынесен в
    `_proxy_reachable_timeout()` (N2, критик-вход attempt 4) — device-free
    юнит-проба покрывает обе ветки без реального устройства."""
    _ensure_replay_ca()
    _ensure_upstream_fast()
    flow_name = request.param
    flows_file = settings.RECORDINGS_DIR / flow_name
    assert flows_file.exists(), (
        f"replay-запись не найдена: {flows_file} "
        f"(сгенерировать: framework/.venv/Scripts/python.exe scripts/build_replay_recordings.py)"
    )
    proxy_reachable_timeout = _proxy_reachable_timeout()
    try:
        mitm.set_device_proxy()
        mitm.start_replay(flows_file)
        mitm.wait_device_proxy_reachable(timeout=proxy_reachable_timeout)
        yield flows_file
    finally:
        # clear_device_proxy идемпотентен (check=False, ставит ":0" безусловно) —
        # безопасно звать даже если set_device_proxy выше не выполнился/упал:
        # teardown должен покрывать ЛЮБую точку отказа setup'а, не только yield.
        #
        # AT-BUG-043 attempt 2 (критик-вход, блокер 1): mitm.stop()/
        # clear_device_proxy() РАЗДЕЛЬНЫМ try/finally — твин уже
        # существующего паттерна exploratory-charters/attachments/CH-007/
        # test_ch007_probe.py:132-136 (stop_replay). До этой правки оба
        # вызова шли подряд БЕЗ защиты: если stop() бросал исключение (было
        # штатно на неосвобождённом порте до фикса _wait_port_released,
        # либо любое будущее исключение из terminate()/wait()),
        # clear_device_proxy() не выполнялся вовсе — прокси устройства
        # (`settings put global http_proxy 10.0.2.2:8080`) оставался
        # выставленным на весь остаток прогона. Проба критика: «stop()
        # бросил TimeoutError через 5.0s... clear_device_proxy вызван:
        # False». stop() теперь сам не бросает по этой причине (см. его
        # докстринг) — этот try/finally остаётся вторым, независимым слоем
        # защиты от ЛЮБОГО будущего исключения из stop().
        try:
            mitm.stop()
        finally:
            mitm.clear_device_proxy()


@pytest.fixture()
def sync_replay():
    """Фабрика ДИНАМИЧЕСКОГО replay для области `sync` (AT-BUG-073) — в отличие
    от `replay` (indirect-параметризация СТАТИЧНЫМ именем файла из
    `framework/data/recordings/`, известным на этапе collection), содержимое
    мока GitLab-снимка (`gitlab_snippet_mock.py`) обычно зависит от ЛОКАЛЬНОГО
    состояния, засеянного ВНУТРИ теста (например, `timestamp`, реально
    выставленный `seed()`, должен совпасть/сравниться с удалённым значением) —
    поэтому `.mitm`-файл строится ВНУТРИ тела теста, не может быть параметром
    `@pytest.mark.parametrize(..., indirect=True)`.

    Возвращает callable `start(flows_path, capture_out=None,
    capture_url_substr="")`, поднимающий ТОТ ЖЕ стек device-proxy/mitmdump,
    что и `replay` (переиспользует те же приватные хелперы модуля —
    `_ensure_replay_ca`/`_ensure_upstream_fast`/`_proxy_reachable_timeout` —
    НЕ дублирует их логику, только точку, откуда берётся сам flows-файл).
    Требует `@pytest.mark.replay` на тесте (тот же marker, что `replay`) —
    окружение (CA/апстрим) то же самое.

    `capture_out`/`capture_url_substr` (AT-BUG-073, критерий готовности п.4)
    — опциональный проброс в `mitm.start_replay`: когда `capture_out` задан,
    тест может позже прочитать перехваченное тело исходящей публикации через
    `mitm.read_captured_requests(capture_out)` (см. `test_sync.py::TC-215`).

    Тест обязан вызвать `start(...)` РОВНО один раз (после того как построил
    `.mitm` нужным ему содержимым, обычно ПОСЛЕ сидинга локального состояния,
    т.к. содержимому мока часто нужен реально выставленный timestamp сидинга)
    — teardown (`mitm.stop()`/`clear_device_proxy()`, тот же `try/finally`, что
    у `replay`) срабатывает независимо от того, был ли `start()` вызван,
    симметрично тому, что `replay`'s `finally` покрывает ЛЮБую точку отказа
    setup'а."""
    _ensure_replay_ca()
    _ensure_upstream_fast()
    proxy_reachable_timeout = _proxy_reachable_timeout()
    started = {"value": False}

    def _start(flows_path, capture_out=None, capture_url_substr: str = "") -> None:
        # Критик-вход (attempt 4, замечание 6): повторный вызов `start(...)` на
        # ТОЙ ЖЕ фикстуре перезаписал бы модульный `mitm._proc` вторым
        # `start_replay()`, ОСИРОТИВ первый mitmdump на порту 8080 (AT-BUG-043
        # класс — teardown этой фикстуры знает только про ОДИН `mitm.stop()`,
        # второй живой процесс на 8080 никто не остановит) — `started["value"]`
        # уже существовал для teardown, здесь он же ограждает setup.
        assert not started["value"], (
            "sync_replay: start(...) вызван повторно на одной и той же "
            "фикстуре — докстринг требует РОВНО один вызов; повторный вызов "
            "осиротил бы первый mitmdump-процесс на порту 8080 (класс "
            "AT-BUG-043, teardown знает только про ПОСЛЕДНИЙ _proc)"
        )
        # ignore_content=True (AT-BUG-073, см. докстринг `mitm.start_replay`):
        # GitLab Snippet API мок несёт POST/PUT с непредсказуемым (мерженным)
        # телом запроса — без опции server-replay матчил бы ТОЛЬКО пустое
        # тело GET (fetchRemote сработал бы), но PUT/POST publish уходил бы в
        # live forward на реальный gitlab.com.
        mitm.set_device_proxy()
        mitm.start_replay(flows_path, ignore_content=True,
                          capture_out=capture_out, capture_url_substr=capture_url_substr)
        mitm.wait_device_proxy_reachable(timeout=proxy_reachable_timeout)
        started["value"] = True

    try:
        yield _start
    finally:
        if started["value"]:
            try:
                mitm.stop()
            finally:
                mitm.clear_device_proxy()


# --- download_oracle: глобальный инвариант-оракул скачиваний (BUG-014) ---
# `DownloadRepository.downloadWork` (app-under-test) пишет файл в
# `context.getExternalFilesDir("ao3_downloads")`, когда пользователь НЕ выбрал
# кастомную SAF-папку (`customFolderUri == null`) — дефолтное состояние после
# `clean_state()`/`pm clear` (см. `DownloadRepository.kt:31-32`, `downloadWork`
# ветка `?: run { val dir = defaultDownloadDir ... }`). Это и есть путь, по
# которому TC-032 (авто-скачивание)/TC-033 (ручное скачивание) реально кладут
# файл — путь, куда БЕЗ УЧАСТИЯ пользователя мог бы попасть файл класса
# BUG-014. НЕ путать с `_DOWNLOAD_FIXTURE_REL_DIR` (`seed_db.py`,
# ВНУТРЕННЯЯ песочница `files/ao3_test_downloads`, используется фикстурами
# `downloaded_work_seeded`/`seed_downloaded_work(s)` для имитации «уже
# скачанного» состояния БЕЗ сети) и с `/sdcard/Download/<...>` (публичный SAF-
# каталог, выбираемый через `saf_steps.saf_pick_folder` в TC-038/TC-039) — ни
# тот, ни другой каталог этот оракул не наблюдает (см. докстринг `download_oracle`).
_DOWNLOAD_DIR_DEVICE = f"/sdcard/Android/data/{settings.APP_PACKAGE}/files/ao3_downloads"


# Критик-вход (download-oracle-0728, ДОРАБОТАТЬ) B1-доп.: sentinel-эхо кода
# возврата `find` сразу в stdout — отличает «каталога нет» (rc=1, штатно
# трактуется как пустой снимок) от «команда сломалась иначе» (rc вне {0,1}:
# смена пакета/пути, битый toybox, неожиданный shell) — последнее не должно
# молча выглядеть как пустая директория, WARN на распознанную аномалию.
_ORACLE_RC_SENTINEL = "ORACLE_SNAPSHOT_RC="


def _snapshot_download_dir() -> dict[str, tuple[int, int]]:
    """Снимок файлов download-директории устройства: `{путь: (размер_байт,
    mtime_epoch_сек)}`. Рекурсивно по вложенным подкаталогам (`find` рекурсивен
    по умолчанию). Пустая/отсутствующая директория — валидный пустой снимок:
    эмпирически проверено (`emulator-5554`, 2026-07-28) — `find
    <несуществующий каталог> -type f -exec stat ...` пишет
    "No such file or directory" в stderr и завершается кодом 1, но
    `adb.shell()` возвращает только `stdout` — это НЕ трактуется как сбой
    оракула, а как «файлов нет». Код возврата ловится ЯВНО через sentinel-эхо
    в САМОЙ shell-строке (см. `_ORACLE_RC_SENTINEL`) — `adb.shell()` не
    прокидывает returncode подпроцесса наружу, поэтому единственный способ
    узнать его — вывести самим `echo $?` внутри той же remote-shell-сессии.
    `rc==0` (файлы есть или каталог пуст) и `rc==1` (каталога нет) — штатные
    исходы; любой другой код -> `warnings.warn` (B1-доп., критик-вход
    download-oracle-0728): признак поломки самой поверхности зонда (смена
    пакета/пути, недоступный toybox), не позиция в бизнес-логике, поэтому
    не `fail` — основной детектор мёртвого зонда — B1/B2 liveness-канарейка
    (см. `download_oracle`), эта проверка дополнительная и дешёвая.

    M1 (критик-вход download-oracle-0728): построчный парсинг защищён от
    нечисловых токенов — испорченная/неожиданная строка (например обрывок
    `stat:`/`find:`, просочившийся в stdout не по plan) не валит `ERROR` на
    КАЖДОМ device-тесте, а даёт `warnings.warn` с этой строкой и пропускается.

    Третий признак (mtime), сверх буквального «имя+размер» спеки задачи, —
    эмпирически необходимая поправка (не своевольная правка API): pytest
    инстанцирует autouse-фикстуры (эта — тоже autouse) ДО explicitly
    requested (`clean_app`/`seeded_library`/`loved_work_seeded` и т.п., чей
    `pm clear` выполняется ПОСЛЕ pre-снимка этой фикстуры). Если предыдущий
    тест той же сессии оставил в этой директории файл с ТЕМ ЖЕ именем и
    размером (контент replay-записей побайтно детерминирован —
    `rb.WORK_WITH_DOWNLOAD_FILENAME` всегда отдаёт идентичные байты для
    `W.LOVED`, что и подтверждено прогоном TC-032→TC-033 подряд), `pm clear`
    текущего теста стирает этот файл, а тест воссоздаёт файл с тем же именем
    и размером — БЕЗ mtime диф по одному «имя+размер» не заметил бы новый
    файл (ложноотрицательный класс, обратный самой цели этой задачи). mtime
    воссозданного файла детерминированно позже старого (реальный разрыв между
    тестами — секунды), что и ловит диф."""
    out = adb.shell(
        "( find " + _DOWNLOAD_DIR_DEVICE + " -type f -exec stat -c '%s %Y %n' {} \\; ; "
        "echo " + _ORACLE_RC_SENTINEL + "$? )"
    )
    lines = out.splitlines()
    rc: int | None = None
    if lines and lines[-1].startswith(_ORACLE_RC_SENTINEL):
        rc_raw = lines.pop()[len(_ORACLE_RC_SENTINEL):].strip()
        try:
            rc = int(rc_raw)
        except ValueError:
            rc = None
    if rc not in (0, 1):
        warnings.warn(
            "download_oracle: зонд снимка вернул неожиданный/нераспознанный "
            f"код возврата ({rc!r}, ожидались 0 «есть файлы/пусто» или 1 "
            "«каталога нет») — возможна поломка probe surface (смена "
            f"пакета/пути/toybox). Сырой вывод: {out!r}"
        )
    snapshot: dict[str, tuple[int, int]] = {}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        parts = line.split(" ", 2)
        if len(parts) != 3:
            warnings.warn(f"download_oracle: не распознана строка снимка (пропущена): {line!r}")
            continue
        size_str, mtime_str, path = parts
        try:
            snapshot[path] = (int(size_str), int(mtime_str))
        except ValueError:
            warnings.warn(f"download_oracle: не распознана строка снимка (пропущена): {line!r}")
    return snapshot


_download_oracle_last_post: dict[str, tuple[int, int]] | None = None


@pytest.fixture(autouse=True)
def download_oracle(request):
    """Глобальный инвариант-оракул скачиваний (решение по классу BUG-014:
    незапрошенное скачивание проходило бы незамеченным в ЛЮБОМ тесте, не
    только в угаданных заранее кейсах). ДО теста снимает снимок файлов
    `_DOWNLOAD_DIR_DEVICE` (см. константу выше), ПОСЛЕ теста — повторный
    снимок; диф new_files сверяется с ОЖИДАЕМЫМ количеством из маркера (см.
    ниже), не бинарно «есть маркер / нет».

    МАРКЕР С ОЖИДАНИЕМ (критик-вход download-oracle-0728, B1+B2 одной
    правкой): `@pytest.mark.produces_download` (без аргументов — дефолт
    `count=1`, форма совместима с уже расставленными на TC-032/TC-033) или
    `@pytest.mark.produces_download(count=N)`. Три исхода:
    - маркера нет (`expected=0`) и есть новые файлы -> `fail` «незапрошенное
      скачивание — класс BUG-014» (как раньше);
    - маркер есть и новых файлов БОЛЬШЕ ожидания -> `fail` «незапрошенное
      скачивание СВЕРХ ОЖИДАЕМОГО» — тест легитимно качает, но не СТОЛЬКО;
    - маркер есть (`expected>0`) и новых файлов МЕНЬШЕ ожидания -> `fail`
      LIVENESS «оракул не увидел ожидаемого файла — проверить поверхность
      зонда». Это и есть детектор мёртвого/сломанного зонда (B1): TC-032/
      TC-033 несут `produces_download` (дефолт count=1) и потому сами стали
      ПОСТОЯННОЙ КАНАРЕЙКОЙ — если снятие снимка когда-нибудь молча
      перестанет видеть реальные файлы (смена пакета/пути, регресс парсинга,
      сама поломка probe surface), эти два теста провалятся с понятным
      LIVENESS-сообщением вместо того, чтобы прогон тихо остался зелёным.

    Дополнительный (дешёвый) детектор поломки зонда — sentinel-код возврата
    `find` в `_snapshot_download_dir`/`_ORACLE_RC_SENTINEL`: отличает «каталога
    нет» (rc=1, штатно) от прочих кодов (WARN, не fail — основной детектор
    поломки эту роль уже покрывает через LIVENESS выше).

    ВАЖНАЯ ДЕТАЛЬ ПОВЕРХНОСТИ (эмпирически подтверждено красной пробой,
    `emulator-5554`, 2026-07-28): т.к. `pytest.fail()` вызывается из
    POST-yield кода АВТОUSE-ФИКСТУРЫ (teardown-фаза), pytest репортит это как
    `ERROR at teardown of <тест>`, НЕ как `FAILED` call-фазы — так устроен
    протокол pytest для любой autouse-фикстуры-инварианта (общий класс, не
    специфично для этого кода). Функционально эквивалентно: тест всё равно
    попадает в "short test summary info" и в невыполненные, exit-код прогона
    ненулевой (`PYTEST_EXIT=1`), CI/гейт блокируется — но при чтении вывода
    искать нужно `ERROR at teardown`, а не `FAILED`, если сообщение оракула
    не найдено в секции FAILURES.

    Гейт `"driver" not in request.fixturenames`: device-free unit-пробы
    (`test_*_unit.py`) монки-патчат `subprocess.run` НА УРОВНЕ МОДУЛЯ (см.
    `test_adb_install_package_wait_unit.py::test_install_...`,
    `test_subprocess_timeout_unit.py`, аналогично `test_replay_ca_check_unit.py`
    и др.) — недекорированный вызов `adb.shell()` внутри этой фикстуры попал
    бы под чужой фейк `subprocess.run` (тот же объект модуля, `adb.py` делает
    `import subprocess; subprocess.run(...)`) и упал бы на парсинге
    произвольного stdout фейка. Ни один из этих тестов не запрашивает
    `driver` (не трогает устройство вообще — тот же признак уже использует
    `_ensure_app_installed`-переопределение в этих же файлах), поэтому
    пропуск по этому признаку безопасен и не сужает продуктовое покрытие:
    скачивание в принципе возможно только через реальный UI/driver
    (`DownloadRepository.downloadWork` вызывается из `BrowserViewModel`,
    reachable только через панель работы/оверлей рейтинга/карточку Library).

    Края:
    - файл, появившийся МЕЖДУ тестами (async-хвост ПРЕДЫДУЩЕГО теста, не
      попавший в его собственный post-снимок) отличает pre-снимок ТЕКУЩЕГО
      теста от post-снимка предыдущего (`_download_oracle_last_post`) ->
      `warnings.warn` с явной атрибуцией «хвост предыдущего теста», БЕЗ fail
      текущего — файл не его;
    - async-скачивание, завершившееся ПОСЛЕ post-снимка ТЕКУЩЕГО теста — v1
      осознанно пропускает; несоответствие поймает WARN хвоста на
      pre-снимке СЛЕДУЮЩЕГО теста (детектор класса на один тест позже, не
      дыра — осознанное решение спеки задачи, не забытый случай);
    - вложенные подкаталоги — `find` рекурсивен по умолчанию, отдельного кода
      не требует; пустая/отсутствующая директория — валидный пустой снимок
      (см. `_snapshot_download_dir`), не ошибка оракула;
    - teardown идемпотентен и не маскирует оригинальное падение теста: если
      `setup`- ИЛИ `call`-фаза теста уже упала (`item.rep_setup`/`rep_call`,
      проставляются хуком `pytest_runtest_makereport` этого файла ДО того,
      как фикстуры начинают teardown — см. порядок фаз рантест-протокола),
      оракул при обнаружении незапрошенных/недостающих файлов только
      `warnings.warn`, не даёт второй `fail` поверх исходной ошибки (M2,
      критик-вход download-oracle-0728: раньше проверялся только `rep_call`
      — падение setup'а ДРУГОЙ фикстуры, идущей после `download_oracle` по
      порядку setup, ушло бы в отдельный `call` не запустившимся, и `rep_call`
      был бы `None`, не покрывая этот случай)."""
    global _download_oracle_last_post
    if "driver" not in request.fixturenames:
        yield
        return

    pre_snapshot = _snapshot_download_dir()
    if _download_oracle_last_post is not None:
        tail_new = {
            path: value
            for path, value in pre_snapshot.items()
            if _download_oracle_last_post.get(path) != value
        }
        if tail_new:
            warnings.warn(
                "download_oracle: файл(ы) в download-директории появились "
                "МЕЖДУ тестами (хвост предыдущего теста, не текущего — "
                f"BUG-014, атрибуция по разнице pre-снимка с последним "
                f"известным post-снимком): {sorted(tail_new)}"
            )

    yield

    post_snapshot = _snapshot_download_dir()
    _download_oracle_last_post = post_snapshot
    new_files = {
        path: value
        for path, value in post_snapshot.items()
        if pre_snapshot.get(path) != value
    }

    marker = request.node.get_closest_marker("produces_download")
    if marker is None:
        expected_count = 0
    elif marker.args:
        expected_count = marker.args[0]
    else:
        expected_count = marker.kwargs.get("count", 1)
    actual_count = len(new_files)

    message = None
    if expected_count == 0 and actual_count > 0:
        message = (
            "download_oracle: незапрошенное скачивание — класс BUG-014. "
            f"Новые/изменившиеся файлы в {_DOWNLOAD_DIR_DEVICE}: "
            f"{sorted(new_files)}. Если тест легитимно скачивает — "
            "промаркируйте тест @pytest.mark.produces_download."
        )
    elif expected_count > 0 and actual_count > expected_count:
        message = (
            "download_oracle: незапрошенное скачивание СВЕРХ ОЖИДАЕМОГО — "
            f"класс BUG-014. Ожидалось {expected_count} файл(ов) "
            f"(@pytest.mark.produces_download(count={expected_count})), "
            f"фактически {actual_count}: {sorted(new_files)}."
        )
    elif expected_count > 0 and actual_count < expected_count:
        message = (
            "download_oracle: LIVENESS — оракул НЕ УВИДЕЛ ожидаемого файла. "
            f"Тест помечен @pytest.mark.produces_download(count={expected_count}), "
            f"но в {_DOWNLOAD_DIR_DEVICE} обнаружено только {actual_count} "
            f"новых/изменившихся файлов: {sorted(new_files)}. Проверьте "
            "поверхность зонда download_oracle (снятие снимка/путь/пакет) "
            "или регресс самого скачивания в тесте."
        )

    if message is not None:
        rep_setup = getattr(request.node, "rep_setup", None)
        rep_call = getattr(request.node, "rep_call", None)
        already_failed = any(
            rep is not None and rep.failed for rep in (rep_setup, rep_call)
        )
        if already_failed:
            warnings.warn(message)
        else:
            pytest.fail(message, pytrace=False)


# --- Артефакты падений ---
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    setattr(item, f"rep_{report.when}", report)
    if report.when == "call" and report.failed:
        drv = item.funcargs.get("driver")
        if drv is not None:
            reporting.attach_failure_artifacts(drv, item.name)


# AT-BUG-026 B3 (критик-вход attempt 3): часть спеки контейнмента, п.3 —
# «run-артефакт конвейерного прогона несёт строку ENV_ISSUE с числом
# восстановлений». Реализовано в объёме, доступном ИЗНУТРИ этого файла
# (conftest/pytest-хук) — печатает ОДНУ greppable-строку в терминальный
# вывод прогона в самом конце (тот же вывод, который test-runner уже
# использует как основной источник данных для `runs/RUN-*.md`, см.
# `.claude/agents/test-runner.md`: «Собери итоги» читается из терминального
# вывода pytest, не из отдельного JSON). Строка печатается ВСЕГДА (в т.ч.
# recoveries=0) — отсутствие строки в выводе однозначно значит «прогон не
# дошёл до pytest_sessionfinish» (краш самого pytest-процесса), а не «guard
# молчит о нуле».
#
# N1 (критик-вход attempt 4): токен `ENV_ISSUE` печатается ТОЛЬКО когда
# `recovery_count > 0` — раньше он был частью строки ВСЕГДА, в т.ч. на
# полностью зелёном прогоне без единого recovery, что ломало greppable-
# семантику самого слова `ENV_ISSUE` (чужой контракт — `schemas/
# evidence.yaml`, `.claude/agents/failure-analyst.md`: вердикт по этому
# слову) и собственный приёмочный приём «grep ENV_ISSUE -> 0 совпадений =
# нет побочек» этой же задачи. Свойство «строка печатается ВСЕГДА»
# (см. абзац выше — отсутствие строки в выводе значит краш pytest-процесса
# ДО sessionfinish, не молчание guard'а о нуле) СОХРАНЕНО буквально: строка
# печатается в обеих ветках, разнится только присутствие токена.
#
# ЧЕСТНО НЕ СДЕЛАНО В ЭТОМ ДИСПАТЧЕ (явная постановка в очередь, правило 9
# CLAUDE.md, чтобы не повторить пробел attempt 2): (1) отдельное ПОЛЕ в
# `schemas/run.schema.yaml` под этот счётчик (например
# `env_issue_recoveries: {}`) и (2) обновление workflow
# `.claude/agents/test-runner.md` шаг 3/4, чтобы он транскрибировал эту
# строку В frontmatter/discussion `runs/RUN-*.md` — оба пункта трогают
# схему И чужой агентный промпт (test-runner, не test-maintainer), что
# шире мандата ЭТОГО B4-точечного фикса (driver_factory/conftest); решение
# по вопросу «стоит ли» — за координатором/Lead следующим диспатчем.
def pytest_terminal_summary(terminalreporter, exitstatus, config) -> None:
    recovery_count = _DEVICE_GUARD.recovery_count
    max_recoveries = _DEVICE_GUARD.max_recoveries
    if recovery_count > 0:
        terminalreporter.write_line(
            f"ENV_ISSUE (AT-BUG-026): device-liveness guard recoveries this "
            f"session = {recovery_count}/{max_recoveries}"
        )
    else:
        terminalreporter.write_line(
            f"AT-BUG-026 device-liveness guard: recoveries this session = "
            f"{recovery_count}/{max_recoveries}"
        )
