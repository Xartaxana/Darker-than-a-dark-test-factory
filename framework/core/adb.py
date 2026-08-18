"""Тонкая обёртка над adb. Всё общение с устройством вне Appium идёт сюда:
управление данными приложения, logcat, скриншоты, сидинг Room через run-as.
Ничего не знает об экранах приложения — переиспользуемо.
"""
from __future__ import annotations

import re
import shlex
import subprocess
import sys
import time
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


def shell(cmd: str, timeout: float = settings.ADB_SHELL_TIMEOUT) -> str:
    """`timeout` переопределяется вызывающим кодом для shell-команд ДРУГОГО
    класса, чем «обычная быстрая» (AT-BUG-009, инкремент 2) — например,
    `seed_db.ensure_db_initialized()` зовёт `am start -W` (блокирующий вызов,
    ждёт полной прорисовки окна) с `settings.ADB_LAUNCH_TIMEOUT`, не дефолтом."""
    return _run(["-s", settings.DEVICE_NAME, "shell", cmd], timeout=timeout).stdout


def force_stop() -> None:
    shell(f"am force-stop {_PKG}")


def volume_dialog_visible() -> bool:
    """AT-BUG-072: системный индикатор громкости (`VolumeDialogImpl`,
    процесс `com.android.systemui`) — отдельное OS-окно (WindowManager,
    `TYPE_VOLUME_OVERLAY`), НЕ часть `app_package` и потому недоступное
    Appium accessibility-локаторам, но видимое в `dumpsys window windows`
    (эмпирика emulator-5554, 2026-08-16: `Window #3 Window{... u0
    VolumeDialogImpl}` появляется сразу после `input keyevent
    KEYCODE_VOLUME_DOWN/UP`, когда клавиша НЕ перехвачена приложением, и
    исчезает сам через несколько секунд — auto-dismiss, не требует явного
    закрытия). Используется как наблюдаемый оракул `app_steps.
    press_volume_key`/`assert_no_volume_dialog_appears`: позитивный (TC-253/
    255 — штатная обработка громкости, диалог ПОКАЗЫВАЕТСЯ) и негативный
    (TC-252 — перехват активен, диалог НЕ должен появиться вовсе)."""
    out = shell("dumpsys window windows | grep -i volumedialog")
    return "volumedialog" in out.lower()


def clear_app_data() -> None:
    """Полный сброс приложения к состоянию чистой установки (pm clear).

    AT-BUG-026 B2 (критик-вход attempt 3): в отличие от `shell()` (отбрасывает
    returncode подпроцесса — годится для best-effort зондов вроде
    `download_oracle`, где отсутствие каталога — валидный исход), ЭТА операция
    ЛОГИЧЕСКИ КРИТИЧНА: КАЖДЫЙ device-тест полагается на реально очищенное
    состояние ДО сидинга/старта. Молчаливый no-op на мёртвом/офлайн устройстве
    (`adb shell` возвращает пустой/ошибочный stdout, ненулевой returncode, но
    `shell()` тихо отбросил бы это) продолжил бы прогон на устаревших данных
    вместо честного отказа — устройство считалось бы «очищенным», не будучи
    таковым.

    B1 (device-liveness guard в `pytest_runtest_setup`, ДО любой
    device-фикстуры) делает этот путь практически недостижимым В ШТАТНОМ
    ПОТОКЕ ЭТОГО репозитория (guard уже подтвердил присутствие/восстановил
    устройство ДО того, как pytest успевает инстанцировать `clean_app`/
    `seeded_library`/любую сидинг-фикстуру) — но это структурная защита
    ПОРЯДКОМ ФИКСТУР, не гарантия самой функции: TOCTOU-окно между
    guard-проверкой и фактическим вызовом `pm clear` остаётся теоретически
    возможным, и любой БУДУЩИЙ вызывающий код, который решит звать
    `clear_app_data()` в обход `clean_app`/`seeded_library` (например,
    напрямую из нового теста/степа), не получил бы защиты B1 вовсе. Поэтому
    returncode проверяется здесь же, а не только полагается на порядок
    фикстур — та же независимая от вызывающего кода гарантия, что уже даёт
    `install()` (проверяет `"Success" not in cp.stdout`)."""
    cp = _run(["-s", settings.DEVICE_NAME, "shell", f"pm clear {_PKG}"])
    if cp.returncode != 0:
        raise RuntimeError(
            f"pm clear {_PKG} завершился returncode={cp.returncode} — "
            "устройство недоступно/офлайн или иная ошибка очистки данных "
            f"(AT-BUG-026 B2). stdout={cp.stdout!r} stderr={cp.stderr!r}"
        )


def is_installed() -> bool:
    return _PKG in shell("pm list packages")


def device_present() -> bool:
    """Позитивная сверка присутствия устройства (класс `Get-Device`/`tasks.ps1`,
    CLAUDE.md permission-hygiene п.6: пустой/ошибочный вывод голого adb ≠ факт
    отсутствия устройства). Парсит `adb devices` (полный путь к `adb.exe` —
    `settings.ADB`, не зависит от PATH сессии) и ищет `settings.DEVICE_NAME` в
    состоянии `device` (не `offline`/`unauthorized`/отсутствует вовсе) — то же
    состояние, которое печатает PowerShell `Get-Device` как `DEVICE: <serial>`.
    Используется device-liveness guard'ом (AT-BUG-026,
    `framework/core/driver_factory.py::DeviceLivenessGuard`) перед КАЖДОЙ
    попыткой создать Appium-сессию."""
    try:
        cp = _run(["devices"], timeout=settings.ADB_SHELL_TIMEOUT)
    except TimeoutError:
        return False
    for line in cp.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[0] == settings.DEVICE_NAME and parts[1] == "device":
            return True
    return False


def _wait_package_service_ready(timeout: float) -> None:
    """Ждёт готовности гостевого package-сервиса перед первой попыткой `adb
    install` — Python-эквивалент PowerShell `tasks.ps1::Wait-PackageServiceReady`
    (принят на приёмке AT-BUG-013). `boot_completed=1` НЕ гарантирует, что
    package-сервис уже поднялся: install сразу после буда может словить
    `cmd: Can't find service: package`, хотя устройство по `Get-Device`/`adb
    devices` уже есть. Сигнал готовности — первый непустой ответ `pm path
    android`, содержащий `package:` (пустой вывод/ошибка = сервис ещё не готов;
    несколько подряд успехов не требуются — как и в PS-версии). Отличие от
    PS-версии НАМЕРЕННОЕ: там fail-soft (Warning + install пробуется), здесь
    fail-fast (RuntimeError, install не пробуется) — решение приёмки, не рассинхрон.
    Короткий поллинг с конечным таймаутом; неудача — явная `RuntimeError` с
    контекстом (сколько ждали, сколько попыток), не молчаливый бесконечный
    retry. Ноль дополнительной задержки на счастливом пути: если первый же
    опрос вернул `package:`, цикл завершается немедленно, ни одного `sleep`.
    """
    deadline = time.monotonic() + timeout
    attempts = 0
    while True:
        attempts += 1
        try:
            out = shell("pm path android", timeout=settings.ADB_SHELL_TIMEOUT)
        except TimeoutError:
            out = ""
        if "package:" in out:
            return
        if time.monotonic() >= deadline:
            raise RuntimeError(
                f"adb.install(): package-сервис гостя не ответил за {timeout}s "
                f"('pm path android' пуст/ошибка после {attempts} попыток) - "
                "AT-BUG-013: следующий 'adb install' мог бы упасть "
                "'cmd: Can't find service: package'."
            )
        time.sleep(1)


def install(
    apk: str = settings.APK_PATH,
    reinstall: bool = True,
    package_service_timeout: float | None = None,
) -> None:
    """Устанавливает APK на устройство. AT-BUG-013 (queue-пункт 1, docs/HANDOFF.md
    — замеченный аналог класса, закрытый ранее только для канонического пути
    `tasks.ps1::Install-App`): перед первой попыткой `adb install` ждёт
    готовности package-сервиса гостя (см. `_wait_package_service_ready`) — этот
    путь вызывается из `conftest.py::_ensure_app_installed` при fresh-boot,
    минуя tasks.ps1. `package_service_timeout=None` — дефолт
    `settings.PACKAGE_SERVICE_WAIT_TIMEOUT`, резолвится на КАЖДЫЙ вызов (не на
    момент импорта модуля), чтобы тесты/вызывающий код могли переопределить его
    точечно, не трогая settings глобально."""
    _wait_package_service_ready(
        settings.PACKAGE_SERVICE_WAIT_TIMEOUT
        if package_service_timeout is None
        else package_service_timeout
    )
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


def set_font_scale(scale: float) -> None:
    """Переключает системный масштаб шрифта (`settings put system font_scale`) —
    простейший детерминированный способ подхватить увеличенный шрифт (TC-107):
    применяется ДО старта приложения, не зависит от live-конфига активности
    (тот же класс системной настройки, что `set_night_mode`). Вызывающий код
    ОБЯЗАН восстановить дефолт (`1.0`) в teardown — иначе следующий тест
    наследует изменённый масштаб (тот же класс, что logcat в TC-098/105)."""
    shell(f"settings put system font_scale {scale}")


# --- AT-BUG-066: fail-safe снятие ОСТАТОЧНЫХ персистентных Android-settings ---
#
# Тот же класс, что AT-BUG-064 закрыл для `global http_proxy`
# (`mitm.ensure_no_residual_proxy()`): `set_font_scale()`/`set_night_mode()`
# выше выставляют ПЕРСИСТЕНТНЫЕ Android-settings, снимаемые СЕЙЧАС только
# in-process `try/finally` фикстуры/тела теста — не переживает hard-kill
# worker'а/креш машины МЕЖДУ установкой и восстановлением. Следующий прогон
# на таком устройстве стартует с увеличенным шрифтом/тёмной темой ОС, ничего
# об этом не зная — тесты, чувствительные к системной теме/масштабу, могут
# падать по НЕВЕРНОЙ причине («баг приложения», хотя фактически грязное
# окружение). Твин `get_device_proxy()`/`ensure_no_residual_proxy()` из
# `mitm.py`, подключается вызывающим кодом (`conftest.py`) в ту же
# session-scope точку + перевзведение после device-liveness recovery.

DEFAULT_FONT_SCALE = 1.0  # системный дефолт Android; независимая от
# `framework/tests/test_accessibility.py::DEFAULT_FONT_SCALE` константа того
# же значения — `adb.py` не импортирует тестовые модули.

DEFAULT_NIGHT_MODE = "no"  # `cmd uimode night` без аргумента печатает
# `Night mode: no/yes/auto` — живой замер (emulator-5554, 2026-08-14, см.
# `bugs/AT-BUG-066.md`) подтвердил чистое устройство стартует с "no".

_NIGHT_MODE_RE = re.compile(r"Night mode:\s*(\w+)")


def get_font_scale() -> str | None:
    """Читает системный масштаб шрифта (`settings get system font_scale`) —
    fail-safe read-back для `ensure_default_font_scale()` (AT-BUG-066, твин
    `mitm.get_device_proxy()`/AT-BUG-064 F2). Ненулевой `returncode` adb
    (устройство offline/unauthorized) НЕ читается как «дефолт» — явно
    отличимый `None` + предупреждение в stderr (CLAUDE.md permission-hygiene
    п.6: пустой вывод env-тула — не факт отсутствия объекта, а промах
    вызова/сбой среды). Зависший adb уже оборачивается `_run()` в явную
    `TimeoutError` (AT-BUG-009) — сюда такое исключение не долетает,
    поднимается напрямую вызывающему коду."""
    cp = _run(["-s", settings.DEVICE_NAME, "shell", "settings get system font_scale"])
    if cp.returncode != 0:
        print(
            f"AT-BUG-066 WARNING: adb shell settings get system font_scale "
            f"вернул код {cp.returncode} (устройство offline/unauthorized?) -- "
            f"stderr: {cp.stderr.strip()!r} -- get_font_scale() не может "
            "определить текущее значение, возвращаю None (не путать с "
            "\"дефолт\"); не бросаю, чтобы не ронять сессию.",
            file=sys.stderr,
        )
        return None
    return cp.stdout.strip()


def ensure_default_font_scale() -> str | None:
    """AT-BUG-066, твин `mitm.ensure_no_residual_proxy()`: fail-safe сброс
    ОСТАТОЧНОГО системного масштаба шрифта на подъёме окружения/сессии.

    Читает текущее значение (`get_font_scale()`) и, если оно НЕ «чисто» (не
    пусто, не `"null"`, не уже `DEFAULT_FONT_SCALE`), сбрасывает его
    (`set_font_scale(DEFAULT_FONT_SCALE)`) и возвращает СТАРОЕ значение —
    вызывающий код (`conftest.py`) решает, как это залогировать. Возвращает
    `None` на счастливом пути (уже дефолт, счастливый путь — ноль лишних
    adb-записей) И когда `get_font_scale()` не смог определить значение (adb
    сбойнул — уже залогировано предупреждение там, здесь чинить нечего).

    Неразборчивое непустое значение (не парсится как `float`) НЕ трогается —
    трактуется как «неизвестный формат, не наше дело» (тот же принцип
    осторожности, что `mitm.ensure_no_residual_proxy()`: она тоже опознаёт
    только конкретный набор «чистых» строк, не пытается интерпретировать
    произвольные значения прокси)."""
    current = get_font_scale()
    if current is None:
        return None
    stripped = current.strip()
    if stripped in ("", "null"):
        return None
    try:
        value = float(stripped)
    except ValueError:
        return None
    if value == DEFAULT_FONT_SCALE:
        return None
    set_font_scale(DEFAULT_FONT_SCALE)
    return stripped


def get_night_mode() -> str | None:
    """Читает текущий режим тёмной темы (`cmd uimode night` БЕЗ аргумента —
    режим ЗАПРОСА, симметричный `cmd uimode night yes/no` из `set_night_mode`).

    AT-BUG-066, живой замер (emulator-5554, 2026-08-14, см. `bugs/AT-BUG-066.md`
    «Обсуждение»): `cmd uimode night` печатает `Night mode: no`/`Night mode:
    yes`/`Night mode: auto` — надёжный человекочитаемый read-back,
    ПРЕДПОЧТЁННЫЙ над `settings get secure ui_night_mode` (тот отдаёт голое
    число; замер подтвердил `no`->`"1"`, `yes`->`"2"` в ЭТОЙ сессии, но
    `auto`->? не измерялось напрямую — раскладка 0/1/2 всё ещё не полностью
    верифицирована документацией AOSP). `cmd uimode night` без параметра
    снимает эту неоднозначность целиком: он же используется приложением
    Android для того же запроса.

    Возвращает сырое слово (`"yes"`/`"no"`/`"auto"`, не хардкодим allowlist —
    иное слово Android тоже вернулось бы как есть) либо `None` на ненулевом
    `returncode` или неразборчивом выводе (тот же fail-safe профиль, что
    `get_font_scale()`)."""
    cp = _run(["-s", settings.DEVICE_NAME, "shell", "cmd uimode night"])
    if cp.returncode != 0:
        print(
            f"AT-BUG-066 WARNING: adb shell cmd uimode night (запрос) вернул "
            f"код {cp.returncode} -- stderr: {cp.stderr.strip()!r} -- "
            "get_night_mode() не может определить текущий режим, возвращаю "
            "None; не бросаю, чтобы не ронять сессию.",
            file=sys.stderr,
        )
        return None
    m = _NIGHT_MODE_RE.search(cp.stdout)
    return m.group(1) if m else None


def ensure_default_night_mode() -> str | None:
    """AT-BUG-066, твин `ensure_default_font_scale()`/`mitm.
    ensure_no_residual_proxy()`: fail-safe сброс ОСТАТОЧНОГО режима тёмной
    темы ОС на подъёме окружения/сессии — снимаемого сейчас ТОЛЬКО in-process
    `try/finally` в телах тестов (`test_settings.py` TC-049/TC-059,
    `test_compatibility.py` TC-110 — `app_steps.set_system_dark_mode(False)`
    в `finally`), не переживающим hard-kill между установкой и
    восстановлением.

    Читает текущий режим (`get_night_mode()`); если он уже `DEFAULT_NIGHT_
    MODE` («no») либо неразборчив/adb сбойнул (`get_night_mode()` вернул
    `None`) — ничего не делает. Иначе (`"yes"`, `"auto"` — ЛЮБОЙ отличный от
    дефолта режим, тесты этого репозитория сознательно `"auto"` никогда не
    выставляют) сбрасывает в `"no"` (`set_night_mode(False)`) и возвращает
    СТАРОЕ значение — вызывающий код (`conftest.py`) решает, как это
    залогировать."""
    current = get_night_mode()
    if current is None or current == DEFAULT_NIGHT_MODE:
        return None
    set_night_mode(False)
    return current


def pidof_app() -> str | None:
    """PID процесса приложения (`pidof <pkg>`) или `None`, если процесс не
    запущен — прокси «процесс жив» (TC-107), тот же приём, что уже использует
    `security_steps.assert_logcat_has_no_sensitive_data` для скоупинга logcat."""
    return shell(f"pidof {_PKG}").strip() or None


def logcat_dump(dest: Path, lines: int = 400) -> None:
    out = shell(f"logcat -d -t {lines}")
    dest.write_text(out, encoding="utf-8", errors="replace")


def logcat_clear() -> None:
    _run(["-s", settings.DEVICE_NAME, "logcat", "-c"])


# --- run-as: доступ к приватным данным приложения (работает на debug-сборке) ---

def run_as(cmd: str) -> str:
    return shell(f"run-as {_PKG} {cmd}")


_RUN_AS_FILE_RC_SENTINEL = "AT_BUG_055_RUN_AS_FILE_RC="


def run_as_file_or_raise(path: str, timeout: float = settings.ADB_SHELL_TIMEOUT) -> str:
    """Честно читает приватный файл приложения через `run-as cat` (AT-BUG-055):
    в отличие от `run_as()`/`shell()` (отбрасывают `returncode`/`stderr` —
    см. `shell()` выше), эта функция ловит код возврата ЯВНО через
    echo-sentinel ВНУТРИ той же remote-shell-сессии — тот же приём, что уже
    закрыл аналогичный класс в `seed_db._schema_ready` (AT-BUG-044),
    `settings_steps.assert_ratings_present`/`assert_no_ratings` (AT-BUG-045) и
    `conftest._snapshot_download_dir` (download-oracle-0728): `adb.shell()`
    не прокидывает `returncode` подпроцесса наружу, единственный способ узнать
    его — вывести самим `echo $?` внутри той же remote-команды.

    Три исхода:
    - `rc == 0` -> `cat` реально прочитал файл, возвращаем контент (может
      быть пустой строкой — легитимное пустое содержимое, это НЕ то же самое,
      что «файл не читался»);
    - `rc != 0` И контент пуст -> типично «No such file or directory»: файл
      ещё не создан приложением (легитимное раннее состояние, например ДО
      первой записи `SharedPreferences.apply()`) — валидный пустой результат,
      не ошибка;
    - иначе (sentinel-строка отсутствует вовсе — `run-as`/remote shell не
      выполнились совсем; ЛИБО код возврата не распознан; ЛИБО ненулевой код
      с непустым содержимым — подозрительная смесь) -> `RuntimeError` с сырым
      выводом. Раньше (AT-BUG-055) такой вход молча превращался в `""`, и
      вызывающий код (`_parse_persisted_tabs`) штатно трактовал нечитаемый
      ответ как «0 вкладок» — неотличимо от реального пустого состояния.

    AT-BUG-079 (симметричный B4-фикс класса AT-BUG-069, «Чини класс, а не
    экземпляр»): `path` раньше интерполировался БЕЗ кавычек вовсе. В отличие
    от `pull_app_file` (единственный явный `sh -c` уровень — argv передаётся
    ОТДЕЛЬНЫМИ элементами напрямую в `subprocess.run`, adb сам восстанавливает
    границы аргументов на удалённой стороне), эта функция идёт через `shell()`
    — ОДНА pre-joined python-строка, отправляемая `adb shell <строка>` ОДНИМ
    argv-элементом: `adbd` парсит её implicit-remote-shell'ом РАЗ (извлекая
    аргумент `-c` для явного ВНУТРЕННЕГО `sh -c`), а затем ВНУТРЕННИЙ `sh -c`
    парсит СВОЙ аргумент ЕЩЁ РАЗ как отдельную команду — путь проходит ДВА
    shell-парсинга, не один. Поэтому кавычек вокруг `path` (защита только
    внутреннего уровня) недостаточно самой по себе: собранная `-c`-строка
    целиком дополнительно квотируется `shlex.quote()` для ВНЕШНЕГО уровня —
    это гарантирует, что implicit remote shell доставит её ВНУТРЕННЕМУ `sh -c`
    буквально (включая наши ручные кавычки вокруг `path`), не разбив на
    отдельные аргументы по пробелам. Одинарная кавычка ВНУТРИ `path` отклоняется
    `ValueError` ДО похода на устройство — тот же fail-closed приём, что
    `pull_app_file` (AT-BUG-069 rework attempt 2): она сломала бы само
    квотирование внутреннего уровня."""
    if "'" in path:
        raise ValueError(
            f"run_as_file_or_raise: path содержит одинарную кавычку "
            f"({path!r}) — небезопасно для квотирования в remote sh -c "
            "'...'; ожидается module-level константа без кавычек "
            "(AT-BUG-079, по образцу AT-BUG-069 rework attempt 2)."
        )
    inner_script = f"cat '{path}' 2>/dev/null; echo {_RUN_AS_FILE_RC_SENTINEL}$?"
    out = shell(
        f"run-as {_PKG} sh -c {shlex.quote(inner_script)}",
        timeout=timeout,
    )
    lines = out.splitlines()
    rc: int | None = None
    if lines and lines[-1].startswith(_RUN_AS_FILE_RC_SENTINEL):
        rc_raw = lines.pop()[len(_RUN_AS_FILE_RC_SENTINEL):].strip()
        try:
            rc = int(rc_raw)
        except ValueError:
            rc = None
    content = "\n".join(lines)
    if rc == 0:
        return content
    if rc is not None and rc != 0 and not content.strip():
        return ""
    raise RuntimeError(
        f"run-as {_PKG} cat {path} не завершился однозначно успешно "
        f"(rc={rc!r}, сырой вывод={out!r}) — ожидали 0 «файл прочитан» или "
        "ненулевой БЕЗ содержимого «файла ещё нет»; похоже на отвалившийся/"
        "неоднозначный adb или run-as (устройство офлайн, пакет не "
        "debuggable, битый toybox), не на легитимное пустое состояние "
        "(AT-BUG-055)."
    )


_PULL_RC_SENTINEL = b"\nAT_BUG_069_PULL_RC="


def pull_app_file(rel_path: str, dest: Path) -> bool:
    """Тянет файл из приватной песочницы приложения на хост через run-as cat (бинарно).
    Не идёт через `_run()` (нужны сырые байты без `text=True`) — тот же конечный
    `ADB_TRANSFER_TIMEOUT` (AT-BUG-009) применён напрямую.

    AT-BUG-069 (fail-closed на транспортную ошибку, отдельно от легитимного
    отсутствия файла): живой сверкой на emulator-5554 (5 сценариев —
    реальный файл, синтетически отсутствующий путь, легитимно-пустой WAL,
    несуществующий пакет для `run-as`, несуществующая серийка устройства)
    подтверждено, что `adb exec-out` НЕ транслирует returncode/stderr
    удалённой команды: и содержимое файла, и текст ошибки `cat`
    («No such file or directory»), и текст ошибки самого `run-as`
    («unknown package: …») попадают в ОДИН и тот же локальный `cp.stdout`
    с `cp.returncode == 0` во всех трёх случаях — старая проверка
    `cp.returncode != 0 or not cp.stdout` НЕ различала «файла легитимно
    нет» от «run-as вообще не запустился» и на синтетически отсутствующем
    пути была готова записать текст ошибки `cat` в `dest` как будто это
    содержимое файла (непустой `cp.stdout`, `returncode == 0`). Единственное,
    что реально отражает состояние ЛОКАЛЬНОГО adb-клиента (устройство
    офлайн/не найдено) — `cp.returncode`/`cp.stderr` ЭТОГО subprocess-вызова
    (эмпирически: `-s emulator-9999` дал `returncode=-1`,
    `stderr=b"error: device ... not found"`, ПУСТОЙ `stdout`).

    Фикс — тот же приём, что `run_as_file_or_raise` (AT-BUG-055), только
    маркер дописывается в КОНЕЦ БИНАРНОГО `stdout` (нельзя разделить каналы
    редиректом `>&2`: живой пробой подтверждено — `exec-out` сливает remote
    stdout+stderr в один локальный stdout, `>&2` на этот вывод не влияет):
    удалённая команда сама печатает `$?` ПОСЛЕ содержимого через `printf`.
    `rfind()` берёт ПОСЛЕДНЕЕ вхождение маркера — безопасно даже если
    бинарные байты файла случайно содержат похожую подстроку раньше.
    - маркер найден, `rc == 0`, контент непуст -> `cat` реально прочитал
      файл, это его байты -> пишем в `dest`, `True`.
    - маркер найден, `rc != 0` (типично ENOENT) ИЛИ контент пуст -> `cat`
      сам не смог прочитать (легитимное отсутствие WAL/SHM — см.
      `_pull_baseline`) -> `False`, текст ошибки `cat` ИГНОРИРУЕТСЯ, не
      попадает в `dest` (не путается с байтами файла).
    - маркер ОТСУТСТВУЕТ в `stdout` вовсе -> удалённая `sh`-сессия не
      выполнилась до `printf` (`run-as` не смог переключиться на пакет —
      «unknown package»/«not debuggable» — или устройство недоступно) ->
      `RuntimeError`, fail-closed (это и есть кандидат-причина AT-BUG-069:
      раньше такой вход тоже тихо возвращал `False`, неотличимо от
      легитимного отсутствия файла).

    AT-BUG-069 rework attempt 2 (критик-вход, живая сверка): `rel_path`
    ТЕПЕРЬ обёрнут в одинарные кавычки внутри удалённой `sh -c '...'`-команды.
    Attempt 1 интерполировал `rel_path` НЕЗАКВОЧЕННЫМ — критик живьём
    подтвердил три поломки на emulator-5554: (1) путь с пробелом
    (`files/critic_sp ace.bin`, существующий читаемый файл) — `sh -c`
    делил незаквоченный путь на два `cat`-аргумента, `cat` падал с ошибкой
    на КАЖДОМ из них по отдельности, маркер печатался с `rc!=0` -> `False`
    вместо `True`+байты — тот же класс путаницы «легитимно нет» vs «сбой»,
    который весь этот фикс должен устранять, регресс; (2) пустой/пробельный
    `rel_path` — `cat` без операнда читал STDIN -> зависание до
    `ADB_TRANSFER_TIMEOUT` (120s) вместо мгновенной ошибки; (3) `rel_path`
    с метасимволами (`;`) — удалённое исполнение произвольной команды.
    `rel_path` — ВСЕГДА module-level константа (`seed_db._DB_REL`/`_WAL`/
    `_SHM`), не пользовательский ввод, но fail-closed правильнее молчаливой
    поломки: одинарная кавычка ВНУТРИ `rel_path` сломала бы само
    квотирование (закрыла бы кавычку раньше) -> явный `ValueError` ДО
    похода на устройство, а не непредсказуемая remote-команда."""
    if "'" in rel_path:
        raise ValueError(
            f"pull_app_file: rel_path содержит одинарную кавычку "
            f"({rel_path!r}) — небезопасно для квотирования в remote "
            "sh -c '...'; ожидается module-level константа без кавычек "
            "(AT-BUG-069 rework attempt 2)."
        )
    try:
        cp = subprocess.run(
            [settings.ADB, "-s", settings.DEVICE_NAME, "exec-out",
             "run-as", _PKG, "sh", "-c",
             f"cat '{rel_path}'; printf '\\nAT_BUG_069_PULL_RC=%d' $?"],
            capture_output=True,  # bytes, без text=True
            timeout=settings.ADB_TRANSFER_TIMEOUT,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(
            f"adb exec-out run-as cat {rel_path} не ответил за "
            f"{settings.ADB_TRANSFER_TIMEOUT}s (AT-BUG-009)"
        ) from exc
    idx = cp.stdout.rfind(_PULL_RC_SENTINEL)
    if idx == -1:
        raise RuntimeError(
            f"pull_app_file({rel_path}) — rc-маркер отсутствует в выводе "
            f"(returncode adb-клиента={cp.returncode!r}, stderr={cp.stderr!r}, "
            f"сырой stdout[:200]={cp.stdout[:200]!r}) — run-as/remote-shell "
            "не завершились однозначно (устройство офлайн, пакет не "
            "debuggable/не установлен, битый toybox) — НЕ то же самое, что "
            "легитимное отсутствие файла (AT-BUG-069)."
        )
    content = cp.stdout[:idx]
    rc_raw = cp.stdout[idx + len(_PULL_RC_SENTINEL):]
    try:
        rc = int(rc_raw)
    except ValueError:
        rc = None
    if rc != 0 or not content:
        return False
    dest.write_bytes(content)
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
    """Кладёт файл в приватную песочницу приложения через /data/local/tmp + run-as cp.

    AT-BUG-026 N3 (критик-вход attempt 4, тот же аргумент, что B2/
    `clear_app_data`): эта функция ПИШЕТ засеянные Room-БД/HTML-фикстуры на
    устройство (см. `framework/data/seed_db.py`) — тихий no-op на любом из
    двух КРИТИЧНЫХ шагов (push на хост-сторону /data/local/tmp, затем cp
    внутрь песочницы приложения через run-as) продолжил бы тест на
    СТАРЫХ/отсутствующих данных с ложным PASS, тот же класс риска, что
    молчаливый `pm clear`, закрытый в B2. Оба шага проверяются НАПРЯМУЮ через
    `_run()` (не через `run_as()`/`shell()`, которые отбрасывают returncode)
    — returncode != 0 -> явный `RuntimeError` с контекстом, вместо
    продолжения на непонятно каком состоянии устройства.

    Намеренно НЕ распространено на `run_as()` как таковую (публичная
    функция) и на завершающий `rm -f {tmp}`: `run_as()` используется в
    НЕСКОЛЬКИХ местах, где ненулевой returncode — ВАЛИДНЫЙ исход, не ошибка
    (например `app_steps.py`/`settings_steps.py` читают `cat` файла,
    который может легитимно отсутствовать) — превращение returncode-check
    в часть контракта `run_as()` сломало бы эти вызовы; менять её ради ОДНОГО
    вызывающего кода шире мандата узкого B4-фикса. Финальный `rm -f`
    (уборка временного файла в /data/local/tmp) — best-effort: его отказ не
    искажает засеянные данные (файл уже скопирован в песочницу шагом выше),
    только оставляет мусор в /data/local/tmp, не критично для целостности
    теста, поэтому оставлен как раньше (через `shell()`, без проверки).

    AT-BUG-079 (симметричный B4-фикс класса AT-BUG-069): `tmp`/`rel_path`
    раньше интерполировались в remote `cp`-команду БЕЗ кавычек. В отличие от
    `run_as_file_or_raise` здесь ТОЛЬКО ОДИН уровень удалённого shell-парсинга
    — `run-as PKG cp SRC DST` эксекает `cp` НАПРЯМУЮ (без явного `sh -c`
    внутри), аргументы `SRC`/`DST` уже разобраны implicit-remote-shell'ом
    `adb shell <строка>` ДО того, как run-as их увидит — так что одиночного
    квотирования одинарными кавычками (как и в `pull_app_file`) достаточно, не
    нужен `shlex.quote()`-слой `run_as_file_or_raise`. Одинарная кавычка
    ВНУТРИ `tmp`/`rel_path` отклоняется `ValueError` ДО похода на устройство
    (тот же fail-closed приём, что `pull_app_file`/`run_as_file_or_raise`) —
    проверяется ДО первого `_run()`, чтобы невалидный вход не оставил
    частичное состояние (файл уже запушенный в /data/local/tmp, но не
    скопированный в песочницу)."""
    tmp = f"/data/local/tmp/{src.name}"
    if "'" in tmp or "'" in rel_path:
        raise ValueError(
            f"push_app_file: путь содержит одинарную кавычку (tmp={tmp!r}, "
            f"rel_path={rel_path!r}) — небезопасно для квотирования в remote "
            "shell-команде; ожидается module-level константа/безопасное имя "
            "файла без кавычек (AT-BUG-079, по образцу AT-BUG-069 rework "
            "attempt 2)."
        )
    cp_push = _run(
        ["-s", settings.DEVICE_NAME, "push", str(src), tmp],
        timeout=settings.ADB_TRANSFER_TIMEOUT,
    )
    if cp_push.returncode != 0:
        raise RuntimeError(
            f"adb push {src} -> {tmp} завершился returncode={cp_push.returncode} "
            "(AT-BUG-026 N3) — устройство недоступно/офлайн, сидинг-файл НЕ "
            f"попал на устройство. stdout={cp_push.stdout!r} stderr={cp_push.stderr!r}"
        )
    cp_copy = _run(["-s", settings.DEVICE_NAME, "shell", f"run-as {_PKG} cp '{tmp}' '{rel_path}'"])
    if cp_copy.returncode != 0:
        raise RuntimeError(
            f"run-as {_PKG} cp {tmp} {rel_path} завершился "
            f"returncode={cp_copy.returncode} (AT-BUG-026 N3) — сидинг-файл НЕ "
            f"попал в песочницу приложения. stdout={cp_copy.stdout!r} "
            f"stderr={cp_copy.stderr!r}"
        )
    shell(f"rm -f '{tmp}'")


# --- Разбор вывода adb-команд для нефункциональных замеров (TC-096/TC-099,
# test-cases/performance/) — генерический парсинг формата вывода `am
# start -W`/`dumpsys meminfo`, ничего не знает о приложении сверх пакета. ---

def parse_am_start_metrics(output: str) -> dict[str, int]:
    """Парсит `TotalTime`/`WaitTime` (мс) из stdout `am start -W` (TC-096).

    Эмпирически подтверждено (live-калибровка 2026-07-22, emulator-5554): для
    УЖЕ запущенного процесса `am start -W` возвращает `TotalTime: 0` (вывод
    несёт `Warning: Activity not started, intent has been delivered to
    currently running top-most instance.`) — это НЕ холодный старт. Вызывающий
    код обязан гарантировать реальный холодный старт (`force_stop()` +
    `clear_app_data()` ДО вызова `am start -W`), иначе метрика тривиально
    «пройдёт» любой бюджет, не измерив ничего реального."""
    metrics: dict[str, int] = {}
    for key in ("TotalTime", "WaitTime"):
        m = re.search(rf"{key}:\s*(\d+)", output)
        if m:
            metrics[key] = int(m.group(1))
    if "TotalTime" not in metrics:
        raise RuntimeError(
            f"вывод 'am start -W' не содержит 'TotalTime' — запуск не подтверждён, "
            f"вывод: {output!r}"
        )
    return metrics


# --- Screen density (TC-148, accessibility touch-target sweep): порог 48dp
# переводится в device px через РЕАЛЬНО измеренную плотность текущего
# прогона, не через хардкод из документации. ---

def screen_density(timeout: float = settings.ADB_SHELL_TIMEOUT) -> int:
    """Парсит `wm density` (TC-148): `Override density: NNN` (если задана
    отдельно, например явным `wm density NNN`) имеет приоритет над `Physical
    density: NNN` — это ФАКТИЧЕСКАЯ плотность, применяемая системой поверх
    физической. По образцу `parse_am_start_metrics`/`total_pss_kb`: явный
    `RuntimeError` с сырым выводом, если ни один из двух маркеров не найден
    (не молчаливый дефолт вроде 160/320 — тихая подмена реальной плотности
    хардкодом обесценила бы весь смысл замера)."""
    out = shell("wm density", timeout=timeout)
    m = re.search(r"Override density:\s*(\d+)", out)
    if not m:
        m = re.search(r"Physical density:\s*(\d+)", out)
    if not m:
        raise RuntimeError(
            f"вывод 'wm density' не содержит ни 'Override density', ни "
            f"'Physical density' — вывод: {out!r}"
        )
    return int(m.group(1))


def total_pss_kb(timeout: float = settings.ADB_SHELL_TIMEOUT) -> int:
    """Парсит `TOTAL PSS` (КБ) из `dumpsys meminfo <package>` (TC-099) — формат
    строки сверен на живом устройстве (emulator-5554, 2026-07-22):
    `           TOTAL PSS:   157913            TOTAL RSS:   313124 ...` (секция
    "App Summary")."""
    out = shell(f"dumpsys meminfo {_PKG}", timeout=timeout)
    m = re.search(r"TOTAL PSS:\s*(\d+)", out)
    if not m:
        raise RuntimeError(
            f"вывод 'dumpsys meminfo {_PKG}' не содержит 'TOTAL PSS' — вывод: {out!r}"
        )
    return int(m.group(1))
