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
        gradlew.bat в app-under-test; APK по apk_path существует

Коды выхода: 0 — всё OK/WARN; 1 — есть FAIL (эскалация уже записана).
FAIL дедуплицируется: одна строка **DOCTOR** на проверку, пока не устранена.

Запуск: python scripts/doctor.py [--no-escalate]
"""
from __future__ import annotations

import argparse
import datetime
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

REPO = bs.REPO
VENV_PY = REPO / "framework" / ".venv" / "Scripts" / "python.exe"
ENV_PS1 = REPO / "scripts" / "env.ps1"
APP = REPO / "app-under-test"
AUT_PATH = REPO / "state" / "app-under-test.yaml"
ESCALATIONS_PATH = REPO / "state" / "escalations.md"
AVD_NAME = "ao3_test_api34"

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
    if AUT_PATH.exists():
        m = re.search(r"(?m)^apk_path:\s*(\S+)", AUT_PATH.read_text(encoding="utf-8"))
        if m:
            apk = REPO / m.group(1)
            apk_ok, apk_detail = apk.exists(), str(apk)
        else:
            apk_detail = "apk_path не указан"
    # APK может законно отсутствовать до первой сборки build_watch — это WARN, не FAIL
    checks.append(Check("APK по apk_path", "run", apk_ok, apk_detail, warn=not apk_ok))

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
