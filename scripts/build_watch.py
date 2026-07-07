"""build_watch — pre_step шага 0: пуш разработчика → сборка APK → app-under-test.yaml.

Событие E1 тёмной фабрики (docs/06 §1): `git fetch` в app-under-test/; появились
новые коммиты относительно state/app-under-test.yaml:source_commit → checkout
удалённого HEAD (detached) → `gradlew.bat assembleDebug` → обновить
state/app-under-test.yaml (source_commit/apk_sha256/built_at, сброс
smoke_status/regression_status в not_run). Изменение yaml — триггер правила
«Новая сборка → smoke, затем regression» на ЭТОМ ЖЕ проходе /qa-loop.

Coalescing (D11): несколько пушей подряд → собирается только последний коммит,
промежуточные фиксируются в поле coalesced_commits (пропущены сознательно).

Деградация:
- fetch не прошёл (офлайн) → [WARN], код 0 — проверим на следующем проходе;
- сборка упала → эскалация в state/escalations.md (строка БЕЗ тега [sla:] —
  снимает человек), yaml НЕ обновляется, код 1.

Окружение сборки: JAVA_HOME/ANDROID_HOME берутся из scripts/env.ps1 (парсинг),
т.к. автономный запуск не гарантирует их в окружении процесса.

Запуск: python scripts/build_watch.py [--dry-run]
NB: сборка gradle идёт минуты — вызывать с увеличенным timeout (600с+).
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import re
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

import board_sync as bs

REPO = bs.REPO
APP = REPO / "app-under-test"
AUT_PATH = REPO / "state" / "app-under-test.yaml"
ESCALATIONS_PATH = REPO / "state" / "escalations.md"
ORCH_LOG = REPO / "state" / "orchestrator-log.md"
ENV_PS1 = REPO / "scripts" / "env.ps1"
APK_REL = "app/build/outputs/apk/debug/app-debug.apk"

BUILD_TIMEOUT_S = 1200


def _utcnow_s() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run(args: list[str], *, cwd: Path | None = None, env: dict | None = None,
         timeout: int = 120) -> tuple[int, str]:
    """Обёртка subprocess; подменяется в тестах (никакого реального git/gradle)."""
    try:
        p = subprocess.run(args, cwd=cwd, env=env, timeout=timeout,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, f"timeout {timeout}s: {' '.join(args)}"
    except OSError as e:
        return 127, str(e)


def build_env() -> dict | None:
    """JAVA_HOME/ANDROID_HOME из scripts/env.ps1 поверх текущего окружения."""
    import os
    env = dict(os.environ)
    if not ENV_PS1.exists():
        return env
    text = ENV_PS1.read_text(encoding="utf-8", errors="replace")
    root = str(REPO)
    for var in ("JAVA_HOME", "ANDROID_HOME", "ANDROID_SDK_ROOT", "ANDROID_AVD_HOME"):
        m = re.search(rf'\$env:{var}\s*=\s*"([^"]+)"', text)
        if m:
            env[var] = m.group(1).replace("$root", root).replace(
                "$env:ANDROID_HOME", env.get("ANDROID_HOME", ""))
    if "JAVA_HOME" in env:
        env["PATH"] = str(Path(env["JAVA_HOME"]) / "bin") + ";" + env.get("PATH", "")
    return env


def _read_field(text: str, field: str) -> str | None:
    m = re.search(rf'(?m)^{field}:\s*"?([^"\n#]*[^"\n# ])"?\s*(#.*)?$', text)
    return m.group(1).strip() if m else None


def _rewrite_field(text: str, field: str, value: str) -> str:
    """Заменяет значение поля, сохраняя хвостовой комментарий; нет поля — добавляет
    после source_commit (или в конец файла)."""
    pattern = re.compile(rf'(?m)^{field}:\s*[^#\n]*(?P<comment>#.*)?$')
    m = pattern.search(text)
    if m:
        comment = f"   {m.group('comment')}" if m.group("comment") else ""
        return pattern.sub(f"{field}: {value}{comment}", text, count=1)
    anchor = re.search(r"(?m)^(source_commit:.*)$", text)
    if anchor:
        return text.replace(anchor.group(1), f"{anchor.group(1)}\n{field}: {value}", 1)
    return text.rstrip("\n") + f"\n{field}: {value}\n"


def detect_new_commits() -> dict | None:
    """fetch + сравнение с source_commit. None = проверить не удалось (офлайн)."""
    rc, out = _run(["git", "-C", str(APP), "fetch", "origin"], timeout=180)
    if rc != 0:
        print(f"  [WARN] git fetch не прошёл (офлайн/недоступен origin): {out.strip()[:200]}")
        return None
    rc, tip = _run(["git", "-C", str(APP), "rev-parse", "FETCH_HEAD"])
    if rc != 0:
        print(f"  [WARN] rev-parse FETCH_HEAD: {tip.strip()[:200]}")
        return None
    tip = tip.strip()
    current = _read_field(AUT_PATH.read_text(encoding="utf-8"), "source_commit") or ""
    if tip == current:
        return {"tip": tip, "new": []}
    rc, lst = _run(["git", "-C", str(APP), "rev-list", "--reverse", f"{current}..{tip}"])
    new = [s for s in lst.split() if s] if rc == 0 else [tip]
    return {"tip": tip, "new": new}


def read_app_versions() -> tuple[str | None, str | None]:
    """versionName/versionCode из gradle-файла модуля app."""
    for name in ("app/build.gradle.kts", "app/build.gradle"):
        p = APP / name
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        code = re.search(r"versionCode\s*=?\s*(\d+)", text)
        vname = re.search(r'versionName\s*=?\s*"([^"]+)"', text)
        return (vname.group(1) if vname else None, code.group(1) if code else None)
    return None, None


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _append_escalation(reason: str) -> None:
    header = "" if ESCALATIONS_PATH.exists() else (
        "# Эскалации фабрики\n\nАктивные варнинги, требующие человека "
        "(docs/06 §4). Строку удаляет человек по разрешении.\n\n")
    with ESCALATIONS_PATH.open("a", encoding="utf-8") as f:
        f.write(header + f"- [{_utcnow_s()}] **BUILD** — {reason}\n")


def _append_orch_log(outcome: str) -> None:
    header = "" if ORCH_LOG.exists() else (
        "# Журнал оркестратора\n\n| Время | Правило | Агент | Артефакт | Исход |\n|---|---|---|---|---|\n")
    with ORCH_LOG.open("a", encoding="utf-8") as f:
        f.write(header + f"| {_utcnow_s()} | pre_step build_watch | build_watch.py | "
                         f"state/app-under-test.yaml | {outcome} |\n")


def update_aut(tip: str, coalesced: list[str], apk_sha: str) -> None:
    text = AUT_PATH.read_text(encoding="utf-8")
    vname, vcode = read_app_versions()
    text = _rewrite_field(text, "source_commit", tip)
    text = _rewrite_field(text, "coalesced_commits",
                          "[" + ", ".join(s[:8] for s in coalesced) + "]")
    if vname:
        text = _rewrite_field(text, "version_name", f'"{vname}"')
    if vcode:
        text = _rewrite_field(text, "version_code", vcode)
    text = _rewrite_field(text, "apk_sha256", f'"{apk_sha}"')
    text = _rewrite_field(text, "built_at", f'"{_utcnow_s()}"')
    text = _rewrite_field(text, "smoke_status", "not_run")
    text = _rewrite_field(text, "regression_status", "not_run")
    AUT_PATH.write_text(text, encoding="utf-8")


def watch(*, dry: bool = False) -> int:
    det = detect_new_commits()
    if det is None:
        return 0                      # офлайн — не ошибка, проверим в следующий проход
    if not det["new"]:
        print("build_watch: новых коммитов нет")
        return 0

    tip, new = det["tip"], det["new"]
    coalesced = new[:-1]              # D11: собираем только последний
    print(f"build_watch: новых коммитов: {len(new)}, собираем {tip[:8]}"
          + (f", пропущены (coalesced): {', '.join(s[:8] for s in coalesced)}" if coalesced else ""))
    if dry:
        print("  (dry-run: без checkout/сборки/записи)")
        return 0

    rc, out = _run(["git", "-C", str(APP), "checkout", "--detach", tip])
    if rc != 0:
        _append_escalation(f"checkout {tip[:8]} не прошёл: {out.strip()[:300]}")
        _append_orch_log(f"FAIL: checkout {tip[:8]}")
        print(f"  [FAIL] checkout: {out.strip()[:300]}")
        return 1

    rc, out = _run([str(APP / "gradlew.bat"), "assembleDebug"],
                   cwd=APP, env=build_env(), timeout=BUILD_TIMEOUT_S)
    apk = APP / APK_REL
    if rc != 0 or not apk.exists():
        tail = out.strip()[-400:]
        _append_escalation(f"сборка APK {tip[:8]} упала (rc={rc}): …{tail}")
        _append_orch_log(f"FAIL: gradlew assembleDebug rc={rc} для {tip[:8]}")
        print(f"  [FAIL] gradlew assembleDebug rc={rc}\n…{tail}")
        return 1

    update_aut(tip, coalesced, _sha256(apk))
    _append_orch_log(f"OK: собрана сборка {tip[:8]}"
                     + (f", coalesced {len(coalesced)}" if coalesced else ""))
    print(f"  [OK] сборка {tip[:8]} готова, app-under-test.yaml обновлён "
          f"(smoke/regression сброшены в not_run)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="build_watch: пуш приложения → сборка APK")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    return watch(dry=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
