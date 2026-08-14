"""doctor — самопроверка окружения фабрики (профилактика находки A3, docs/08).

Автономная фабрика не может зависеть от ручного восстановления окружения: перед
scheduled-проходом /qa-loop убеждаемся, что стенд цел, и при провале поднимаем
эскалацию вместо тихого падения на середине прогона.

Проверки (класс core — без них конвейер не работает вовсе; класс run — без них
невозможны UI-прогоны, но pre_steps/триаж документов возможны):
  core: venv-python запускается; pytest/yaml импортируются в venv;
        state/{rules,sla,app-under-test}.yaml на месте
  run:  java/adb исполняются (пути из scripts/env.ps1); AVD ao3_test_api34
        существует; node/npx.cmd в PATH; appium установлен (tools/appium);
        gradlew.bat в app-under-test; APK по apk_path существует; guest IPv4
        pin (disable_ipv6=1 на устройстве, если оно поднято — ESC-015);
        живой loop.lock с мёртвым pid (heartbeat-сирота, M1/R4); пакет на
        устройстве соответствует yaml (vc + sha base.apk,
        mech-device-build-check)

Коды выхода: 0 — всё OK/WARN; 1 — есть FAIL (эскалация уже записана).
FAIL дедуплицируется: одна строка **DOCTOR** на проверку, пока не устранена.

Запуск: python scripts/doctor.py [--no-escalate]
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

import board_sync as bs
import sla_utils

REPO = bs.REPO
VENV_PY = REPO / "framework" / ".venv" / "Scripts" / "python.exe"
ENV_PS1 = REPO / "scripts" / "env.ps1"
APP = REPO / "app-under-test"
AUT_PATH = REPO / "state" / "app-under-test.yaml"
ESCALATIONS_PATH = REPO / "state" / "escalations.md"
LOCK_FILE = REPO / "state" / "loop.lock"
SLA_PATH = REPO / "state" / "sla.yaml"
AVD_NAME = "ao3_test_api34"
# mech-device-build-check (spec-device-build-check.md v3): истина —
# framework/config/settings.py:24 (`APP_PACKAGE = "com.example.ao3_wrapper"`),
# сверено builder'ом при реализации.
PACKAGE_ID = "com.example.ao3_wrapper"

_which = shutil.which


def _run(args: list[str], *, timeout: int = 60) -> tuple[int, str]:
    try:
        p = subprocess.run(args, timeout=timeout, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "timeout"
    except OSError as e:
        return 127, str(e)


def _adb_device_serial(adb: Path) -> str | None:
    """Канонический признак присутствия устройства (тот же паттерн, что
    scripts/tasks.ps1::Get-Device): первая строка `adb devices` в состоянии
    `device`. None — устройства нет (не «adb сломан», см. `_run` для ошибок
    вызова)."""
    rc, out = _run([str(adb), "devices"])
    if rc != 0:
        return None
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) == 2 and parts[1] == "device":
            return parts[0]
    return None


def _lock_payload(lock_file: Path) -> dict | None:
    if not lock_file.exists():
        return None
    try:
        data = json.loads(lock_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _lock_age_hours(payload: dict, *, now: datetime.datetime | None = None) -> float | None:
    """Возраст лока в часах по payload['ts']; None — ts отсутствует/не
    парсится (свежесть не проверить — тот же принцип, что loop_lock.py).

    Критик-фикс (2026-08-09, класс 2а вместе с loop_lock._parse_ts): naive
    ISO ts (без 'Z') давал naive datetime, вычитание которого с aware `now`
    роняло TypeError и валило ВЕСЬ preflight (doctor — шаг 1 каждого
    прохода). Naive результат трактуется как UTC — та же единая семантика,
    что и в loop_lock._parse_ts."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    ts_raw = payload.get("ts")
    if not ts_raw:
        return None
    try:
        ts = datetime.datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=datetime.timezone.utc)
    return (now - ts).total_seconds() / 3600.0


def _pid_alive(pid: int) -> bool | None:
    """True/False — подтверждённая живость; None — сам вызов tasklist
    недоступен/ошибся (rc!=0) — НЕИЗВЕСТНО, не считается «мёртв».

    Критик-фикс (2026-08-09, п.4): раньше rc!=0 схлопывался в False
    («мёртв») — ошибка ИНСТРУМЕНТА давала ложный WARN осиротевшего лока.
    Унифицировано с scripts/heartbeat_wrap.py::_tasklist_alive: ошибка
    tasklist == «неизвестно», не факт смерти процесса; здесь неизвестность
    — отдельная (третья) ветка вызывающего кода, не «жив»/«мёртв»."""
    rc, out = _run(["tasklist", "/FI", f"PID eq {pid}"])
    if rc != 0:
        return None
    return str(pid) in out


def _heartbeat_lock_dead_pid_check() -> Check:
    """[M1/R4, plan-m1-m4.md v3; runs/REHEARSAL-2026-08-04.md N1 разбор
    2026-08-09]: живой (LIVE по TTL state/sla.yaml thresholds.lock_stale)
    state/loop.lock, чей payload.pid НЕ является работающим процессом,
    сигнализирует осиротевший лок обёртки (kill машины/среды между
    scripts/heartbeat_wrap.py::acquire и его finally-release).

    Применяется ТОЛЬКО к holder'ам `heartbeat:*`: честный долгоживущий pid
    существует только у лока обёртки (payload.pid = os.getpid() самой
    обёртки, живущей весь проход). Интерактивный лок (CLI-вызов
    `loop_lock.py acquire` изнутри SKILL qa-loop) несёт pid ОДНОКРАТНОГО
    короткоживущего процесса — он мёртв уже через секунду после acquire
    штатно; чек на нём давал бы ложный WARN на КАЖДОМ preflight'е, если бы
    не был сужен до heartbeat:*-holder'ов.

    Оговорка (переиспользование pid ОС): в теории мёртвый heartbeat-pid
    может совпасть с чужим, позже стартовавшим процессом — код это не
    исключает (маловероятно в пределах TTL-окна по умолчанию 2ч), см.
    также docstring loop_lock.py про честность/переиспользование pid."""
    name = "живой loop.lock с мёртвым pid"
    payload = _lock_payload(LOCK_FILE)
    if payload is None:
        return Check(name, "run", True, "лока нет/нечитаем — н/п")
    holder = str(payload.get("holder") or "")
    if not holder.startswith("heartbeat:"):
        return Check(name, "run", True,
                    f"holder={holder!r} не heartbeat:* — pid не информативен, "
                    "проверка не применима")
    threshold_h = sla_utils.load_lock_stale_hours(SLA_PATH)
    age_h = _lock_age_hours(payload)
    if age_h is None or age_h > threshold_h:
        return Check(name, "run", True,
                    "лок не LIVE (протух/ts нечитаем) — TTL-страховка справится сама")
    pid = payload.get("pid")
    if not isinstance(pid, int):
        return Check(name, "run", True, f"pid отсутствует/некорректен в payload ({pid!r}) — н/п")
    alive = _pid_alive(pid)
    if alive is None:
        return Check(name, "run", True,
                    f"pid-проверка недоступна для pid={pid} (tasklist rc!=0/ошибка "
                    "вызова) — не считается признаком осиротения")
    detail = (f"holder={holder} pid={pid} жив" if alive else
             f"holder={holder} pid={pid} НЕ является работающим процессом — лок "
             "осиротел (kill обёртки/машины между acquire и release); TTL-страховка "
             f"снимет через {threshold_h}ч, либо снять сейчас вручную "
             "`python scripts/loop_lock.py release --force`")
    return Check(name, "run", alive, detail, warn=not alive)


def _env_paths() -> dict[str, Path]:
    """JAVA_HOME/ANDROID_HOME/ANDROID_AVD_HOME из scripts/env.ps1."""
    out: dict[str, Path] = {}
    if not ENV_PS1.exists():
        return out
    text = ENV_PS1.read_text(encoding="utf-8", errors="replace")
    root = str(REPO)
    for var in ("JAVA_HOME", "ANDROID_HOME", "ANDROID_AVD_HOME"):
        m = re.search(rf'\$env:{var}\s*=\s*"([^"]+)"', text)
        if m:
            out[var] = Path(m.group(1).replace("$root", root))
    return out


class Check:
    def __init__(self, name: str, cls: str, ok: bool, detail: str, warn: bool = False):
        self.name, self.cls, self.ok, self.detail, self.warn = name, cls, ok, detail, warn

    @property
    def label(self) -> str:
        return "OK" if self.ok else ("WARN" if self.warn else "FAIL")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _apk_sha256_check(apk_path: Path | None, apk_exists: bool, aut_text: str) -> Check:
    """A2/C1 (spec-build-source-dual-mode v4): три состояния границы, НЕ
    наивный FAIL. См. вызывающий код (run_checks) за обоснованием."""
    name = "APK sha256 соответствует yaml"
    if apk_path is None or not apk_exists:
        return Check(name, "run", False,
                    "н/п — файла нет (см. чек 'APK по apk_path')", warn=True)

    m_sha = re.search(r'(?m)^apk_sha256:\s*"?([^"\r\n#]*)"?\s*(#.*)?$', aut_text)
    yaml_sha = (m_sha.group(1).strip() if m_sha else "")
    m_vname = re.search(r'(?m)^version_name:\s*"?([^"\r\n#]*)"?\s*(#.*)?$', aut_text)
    m_vcode = re.search(r'(?m)^version_code:\s*([^\r\n#]*)\s*(#.*)?$', aut_text)
    versions_unknown = any(
        m and m.group(1).strip().lower() == "unknown" for m in (m_vname, m_vcode))

    if not yaml_sha or yaml_sha.lower() == "unknown" or versions_unknown:
        return Check(name, "run", False,
                    f"apk_sha256/версии пусты или 'unknown' в yaml (apk_sha256={yaml_sha!r}) "
                    "— сверка невозможна, сборка не полностью зафиксирована", warn=True)

    actual_sha = _sha256_file(apk_path)
    if actual_sha == yaml_sha:
        return Check(name, "run", True, f"совпадает ({actual_sha[:12]}…)")
    return Check(name, "run", False,
                f"НЕ совпадает: файл={actual_sha[:12]}… yaml={yaml_sha[:12]}… — APK "
                "подменён/перезаписан мимо build_watch; путь восстановления: перепрогнать "
                "`python scripts/build_watch.py [--provided <ref>]` либо восстановить APK "
                "вручную")


def _parse_pm_path_base_apk(pm_path_out: str) -> str | None:
    """Парс `adb shell pm path <pkg>`: строки `package:<abs-path>` (сплит-APK
    — несколько строк, напр. `split_config.*` — игнорируются). Возвращает
    путь, оканчивающийся на `/base.apk`; None — такой строки нет / вывод
    пуст."""
    for line in (pm_path_out or "").splitlines():
        line = line.strip()
        if not line.startswith("package:"):
            continue
        path = line[len("package:"):].strip()
        if path.endswith("/base.apk"):
            return path
    return None


def _parse_sha256sum_hex(sha_out: str) -> str | None:
    """Парс `adb shell sha256sum <path>`: формат `<hex>  <путь>` — берётся
    ПЕРВЫЙ токен, lower(). None — вывод пуст/не парсится."""
    text = (sha_out or "").strip()
    if not text:
        return None
    first_line = text.splitlines()[0].strip()
    tokens = first_line.split()
    if not tokens:
        return None
    # Валидация формы токена (Б2б критик-входа приёмки): `_run` склеивает
    # stdout+stderr, поэтому диагностический текст при rc=0 стал бы «хэшем»
    # и дал ложный WARN — ошибка инструмента не должна становиться сигналом
    # (инвариант ветки 4 спеки).
    tok = tokens[0].lower()
    return tok if re.fullmatch(r"[0-9a-f]{64}", tok) else None


def _device_package_check(adb_available: bool, serial: str | None,
                          dumpsys_out: str | None, installed_sha: str | None,
                          aut_text: str) -> Check:
    """Третье звено цепочки идентичности сборки (spec-device-build-check.md
    v3): сборка→yaml закрыт build_watch (M-B), yaml→файл закрыт
    `_apk_sha256_check` (A2/C1) — здесь устройство↔yaml. Чистая функция:
    вся работа с процессами (adb devices/dumpsys/pm path/sha256sum) — в
    `run_checks`; `installed_sha` — уже посчитанный вызывающим кодом sha256
    установленного base.apk (`_parse_pm_path_base_apk` + `_parse_sha256sum_hex`
    поверх реальных adb-вызовов), либо None, если путь/хэш не удалось
    получить. Ветки — ДОСЛОВНО спека (7 состояний границы)."""
    name = "пакет на устройстве соответствует yaml"

    if not adb_available:
        return Check(name, "run", True, "н/п — adb недоступен")
    if serial is None:
        return Check(name, "run", True, "н/п — устройства нет (эмулятор не поднят)")

    m_vcode = re.search(r'(?m)^version_code:\s*([^\r\n#]*)\s*(#.*)?$', aut_text)
    yaml_vcode = (m_vcode.group(1).strip() if m_vcode else "")
    if not yaml_vcode or yaml_vcode.lower() == "unknown":
        return Check(name, "run", False,
                    f"сверка невозможна: yaml не фиксирует сборку "
                    f"(version_code={yaml_vcode!r})", warn=True)

    m_sha = re.search(r'(?m)^apk_sha256:\s*"?([^"\r\n#]*)"?\s*(#.*)?$', aut_text)
    yaml_sha = (m_sha.group(1).strip() if m_sha else "")
    sha_available = bool(yaml_sha) and yaml_sha.lower() != "unknown"

    if not dumpsys_out or not dumpsys_out.strip():
        return Check(name, "run", True,
                    "н/п — вызов adb не удался (rc!=0/timeout/пустой вывод)")

    # Якорь БЛОКОМ пакета (Б7/ветка 5): фильтр `dumpsys package <arg>`
    # подстрочный — вывод может нести несколько блоков (androidTest-пакет
    # <PACKAGE_ID>.test, hidden system packages). "] (" сразу после ID не
    # даёт "<PACKAGE_ID>.test" случайно матчить якорь.
    anchor = f"Package [{PACKAGE_ID}] ("
    start = dumpsys_out.find(anchor)
    if start == -1:
        return Check(name, "run", True,
                    "н/п — пакет не установлен; conftest/Install-App поставит "
                    "из apk_path")
    # Граница блока — ОТСТУП-ТОЛЕРАНТНАЯ (Б2а критик-входа приёмки):
    # реальный `dumpsys package` печатает блоки внутри секции `Packages:` с
    # отступом, поэтому голый find("\nPackage [") границу не находит и блок
    # тёк бы до EOF (versionCode мог бы быть прочитан из чужого блока).
    # Живой вывод на этом стенде не снят (NO DEVICE) — форма ниже корректна
    # в обеих раскладках.
    m_next = re.compile(r"(?m)^[ \t]*Package \[").search(dumpsys_out, start + len(anchor))
    next_start = m_next.start() if m_next else -1
    block_text = dumpsys_out[start:] if next_start == -1 else dumpsys_out[start:next_start]
    m_vc_device = re.search(r'versionCode=(\S+)', block_text)
    if m_vc_device is None:
        return Check(name, "run", True,
                    "н/п — versionCode не найден в блоке пакета dumpsys")
    device_vcode = m_vc_device.group(1)

    # Б1 критик-входа приёмки: у каждой WARN-ветки своя диагностика (sha-ветка
    # не печатает заведомо РАВНЫЕ vc как улику), общий — только путь
    # восстановления.
    recovery = ("прогон пойдёт не на том билде; ПЕРЕД любым device-правилом "
                "выполни Install-App (scripts/tasks.ps1)")
    if device_vcode != yaml_vcode:
        return Check(name, "run", False,
                    f"на устройстве vc={device_vcode}, yaml vc={yaml_vcode} — " + recovery,
                    warn=True)

    if not sha_available:
        return Check(name, "run", True,
                    f"vc={device_vcode} совпадает; идентичность sha не подтверждена: "
                    "apk_sha256 в yaml пуст/unknown")

    if not installed_sha:
        return Check(name, "run", True, "н/п — путь base.apk не получен")

    if installed_sha.lower() != yaml_sha.lower():
        return Check(name, "run", False,
                    f"vc совпал ({device_vcode}), но sha установленного base.apk НЕ "
                    f"совпадает: устройство={installed_sha[:12]}… yaml={yaml_sha[:12]}… — "
                    + recovery, warn=True)

    return Check(name, "run", True,
                f"vc={device_vcode}, sha установленного base.apk совпадает с yaml "
                f"({installed_sha[:12]}…)")


def run_checks() -> list[Check]:
    checks: list[Check] = []
    env = _env_paths()

    # --- core -----------------------------------------------------------
    if VENV_PY.exists():
        rc, out = _run([str(VENV_PY), "-c", "import pytest, yaml; print('deps-ok')"])
        checks.append(Check("venv-python + pytest/yaml", "core", rc == 0 and "deps-ok" in out,
                            out.strip()[:120] or "запущен"))
    else:
        checks.append(Check("venv-python + pytest/yaml", "core", False, f"нет {VENV_PY}"))

    for rel in ("state/rules.yaml", "state/sla.yaml", "state/app-under-test.yaml",
                "schemas/transitions.yaml"):
        checks.append(Check(rel, "core", (REPO / rel).exists(), "на месте" if (REPO / rel).exists() else "отсутствует"))

    # --- run --------------------------------------------------------------
    java = env.get("JAVA_HOME", Path("")) / "bin" / "java.exe"
    if java.exists():
        rc, _out = _run([str(java), "-version"])
        checks.append(Check("java (JAVA_HOME из env.ps1)", "run", rc == 0, str(java)))
    else:
        checks.append(Check("java (JAVA_HOME из env.ps1)", "run", False, f"нет {java}"))

    adb = env.get("ANDROID_HOME", Path("")) / "platform-tools" / "adb.exe"
    if adb.exists():
        rc, _out = _run([str(adb), "version"])
        checks.append(Check("adb (ANDROID_HOME из env.ps1)", "run", rc == 0, str(adb)))
    else:
        checks.append(Check("adb (ANDROID_HOME из env.ps1)", "run", False, f"нет {adb}"))

    avd_home = env.get("ANDROID_AVD_HOME")
    avd_ok = bool(avd_home and (avd_home / f"{AVD_NAME}.ini").exists())
    checks.append(Check(f"AVD {AVD_NAME}", "run", avd_ok,
                        f"{avd_home}/{AVD_NAME}.ini" if avd_ok else "ini не найден"))

    node_ok = bool(_which("node")) and bool(_which("npx.cmd") or _which("npx"))
    checks.append(Check("node + npx.cmd в PATH", "run", node_ok,
                        _which("node") or "node не найден"))

    appium_dir = REPO / "tools" / "appium"
    appium_ok = (appium_dir / "node_modules" / "appium").exists() or (appium_dir / "package.json").exists()
    checks.append(Check("appium (tools/appium)", "run", appium_ok,
                        str(appium_dir) if appium_ok else "не установлен"))

    checks.append(Check("gradlew.bat (app-under-test)", "run", (APP / "gradlew.bat").exists(),
                        "на месте" if (APP / "gradlew.bat").exists() else "отсутствует"))

    # env-ipv4-pin-0803 (решение владельца 2026-08-03, ESC-015): Start-Emulator
    # пинит гостя на IPv4 при каждом подъёме (scripts/tasks.ps1), но пин не
    # переживает ребут/новый буд без прохода через Start-Emulator (напр. ручной
    # `adb emu kill` + сторонний запуск emulator.exe). Устройства нет — чек не
    # применим (skip, НЕ FAIL): doctor не поднимает эмулятор сам.
    # device_serial инициализирован здесь (не только в ветке adb.exists()),
    # чтобы mech-device-build-check ниже мог переиспользовать его без
    # NameError, когда adb вовсе недоступен (второй `adb devices` не зовётся,
    # spec-device-build-check.md v3).
    device_serial: str | None = None
    if adb.exists():
        device_serial = _adb_device_serial(adb)
        if device_serial is None:
            checks.append(Check("guest IPv4 pin", "run", True,
                                "н/п — устройства нет (эмулятор не поднят)"))
        else:
            # Находка живой верификации 2026-08-03 (attempt 2, полный холодный
            # рестарт): `net.ipv6.conf.ALL.disable_ipv6` — недостаточный сигнал.
            # Android асинхронно (~60с после буда, вне контроля Start-Emulator)
            # переустанавливает per-interface `conf/wlan0/disable_ipv6` обратно в 0,
            # ПОКА `all`/`default` остаются 1 — старый чек (`cat .../all/...`) давал
            # ЛОЖНЫЙ OK на живом устройстве с реально присутствующими IPv6-адресами
            # на wlan0 (воспроизведено эмпирически). Тот же класс, что B3-фикс
            # tasks.ps1::Set-GuestIPv4Pin — сверяем ЭФФЕКТОМ (`ip -6 addr`, строки
            # `inet6 `), не отдельным агрегатным флагом.
            rc, out = _run([str(adb), "-s", device_serial, "shell", "ip", "-6", "addr"])
            inet6_lines = [ln for ln in out.splitlines() if re.search(r"inet6\s", ln)]
            pinned = rc == 0 and not inet6_lines
            checks.append(Check(
                "guest IPv4 pin", "run", pinned,
                (f"inet6-адреса присутствуют на {device_serial} "
                 f"({len(inet6_lines)} шт., напр. {inet6_lines[0].strip()!r}) — "
                 "перезапусти эмулятор через Start-Emulator (scripts/tasks.ps1)")
                if not pinned else f"нет inet6-адресов на {device_serial}",
                warn=not pinned))
    else:
        checks.append(Check("guest IPv4 pin", "run", True, "н/п — adb недоступен"))

    # docs/09 «Мелкое хозяйство» п.3 (2026-07-18): чисто информационная
    # видимость shallow-статуса клона app-under-test для человека — ok=True
    # ВСЕГДА (shallow — легитимное, ожидаемое состояние экономии места, не
    # поломка окружения; build_watch.py уже устойчив к нему своим guard'ом
    # в detect_new_commits). Не FAIL и не WARN: не эскалирует, не шумит.
    if APP.exists():
        rc, out = _run(["git", "-C", str(APP), "rev-parse", "--is-shallow-repository"])
        # Батч-пункт 3 (косметика, наблюдение critic 07-18): rc != 0 значит
        # git-плюмбинг не подтвердил репозиторий (каталог не git вовсе, либо
        # git недоступен) — это НЕ то же самое, что «полный (не-shallow)
        # клон». Раньше оба случая молча схлопывались в detail="полный
        # клон", что вводило в заблуждение про не-git каталог.
        if rc != 0:
            detail = "не git-репозиторий (git rev-parse не подтвердил репозиторий)"
        elif out.strip() == "true":
            detail = ("shallow — build_watch.py деградирует диапазон коммитов "
                       "(coalesced_commits), это ожидаемо (docs/09 п.3)")
        else:
            detail = "полный клон"
    else:
        detail = f"нет {APP}"
    checks.append(Check("app-under-test git-глубина", "run", True, detail))

    apk_ok, apk_detail = False, "state/app-under-test.yaml не найден"
    apk_path_for_sha: Path | None = None
    aut_text_for_sha = ""
    if AUT_PATH.exists():
        aut_text_for_sha = AUT_PATH.read_text(encoding="utf-8")
        m = re.search(r"(?m)^apk_path:\s*(\S+)", aut_text_for_sha)
        if m:
            apk = REPO / m.group(1)
            apk_ok, apk_detail = apk.exists(), str(apk)
            apk_path_for_sha = apk
        else:
            apk_detail = "apk_path не указан"
    # APK может законно отсутствовать до первой сборки build_watch — это WARN, не FAIL
    checks.append(Check("APK по apk_path", "run", apk_ok, apk_detail, warn=not apk_ok))

    # A2/C1 (spec-build-source-dual-mode v4): sha256-чек APK против yaml —
    # ловит подмену/перезапись APK мимо build_watch (напр. следующий локальный
    # assembleDebug молча перезаписал canonical-путь под провайденной yaml-
    # записью). Границы НЕ наивный FAIL: файла нет -> WARN (отдаётся
    # существующему чеку выше — «APK может законно отсутствовать»);
    # apk_sha256 пуст/unknown ИЛИ версии unknown (M-B.2 незавершённая запись)
    # -> WARN (сверка невозможна/сборка не полностью зафиксирована); ОБА есть
    # и различаются -> FAIL с путём восстановления (иначе фабрика стоит
    # молча-надолго — FAIL снимает env-правила прохода, SKILL.md:84-87).
    checks.append(_apk_sha256_check(apk_path_for_sha, apk_ok, aut_text_for_sha))

    # mech-device-build-check (spec-device-build-check.md v3): третье звено
    # цепочки идентичности сборки — устройство↔yaml (сборка→yaml уже закрыт
    # build_watch/M-B, yaml→файл — чеком выше). serial переиспользован из
    # блока guest IPv4 pin, второй `adb devices` не зовётся. Все 3 adb-вызова
    # (dumpsys/pm path/sha256sum) безусловны при живом serial — какая ветка
    # применится, решает чистая функция ниже по своим правилам (напр. пакет
    # не установлен -> installed_sha всё равно останется None, не проблема).
    dumpsys_out: str | None = None
    installed_sha: str | None = None
    if adb.exists() and device_serial is not None:
        rc_d, out_d = _run([str(adb), "-s", device_serial, "shell", "dumpsys",
                            "package", PACKAGE_ID])
        dumpsys_out = out_d if rc_d == 0 and out_d.strip() else None
        rc_p, out_p = _run([str(adb), "-s", device_serial, "shell", "pm", "path",
                            PACKAGE_ID])
        base_apk_path = _parse_pm_path_base_apk(out_p) if rc_p == 0 else None
        if base_apk_path:
            rc_s, out_s = _run([str(adb), "-s", device_serial, "shell",
                                "sha256sum", base_apk_path])
            installed_sha = _parse_sha256sum_hex(out_s) if rc_s == 0 else None
    checks.append(_device_package_check(adb.exists(), device_serial, dumpsys_out,
                                        installed_sha, aut_text_for_sha))

    # M1/R4 (plan-m1-m4.md v3, 2026-08-09): сирота-детектор для heartbeat-обёртки.
    checks.append(_heartbeat_lock_dead_pid_check())

    return checks


def _append_escalation(reason: str) -> None:
    existing = ESCALATIONS_PATH.read_text(encoding="utf-8") if ESCALATIONS_PATH.exists() else ""
    if reason in existing:
        return  # дедуп: уже поднято, не плодим
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    header = "" if existing else (
        "# Эскалации фабрики\n\nАктивные варнинги, требующие человека "
        "(docs/06 §4). Строку удаляет человек по разрешении.\n\n")
    with ESCALATIONS_PATH.open("a", encoding="utf-8") as f:
        f.write(header + f"- [{stamp}] **DOCTOR** — {reason}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Самопроверка окружения фабрики")
    parser.add_argument("--no-escalate", action="store_true",
                        help="только отчёт, без записи в escalations.md")
    args = parser.parse_args(argv)

    checks = run_checks()
    fails = [c for c in checks if not c.ok and not c.warn]
    for c in checks:
        print(f"  [{c.label}] ({c.cls}) {c.name} — {c.detail}")
    print(f"doctor: {len(checks)} проверок, FAIL: {len(fails)}, "
          f"WARN: {sum(1 for c in checks if c.warn and not c.ok)}")

    if fails and not args.no_escalate:
        for c in fails:
            _append_escalation(f"окружение сломано: {c.name} ({c.detail}) — "
                               f"починить до следующего scheduled-прохода")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
