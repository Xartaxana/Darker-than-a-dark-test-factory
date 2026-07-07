"""Юнит-тесты doctor (scripts/doctor.py) на фейковом окружении."""
from __future__ import annotations

from pathlib import Path

import pytest

import doctor as dr


@pytest.fixture()
def env(repo, monkeypatch):
    """Минимальное «здоровое» окружение в tmp: все файлы на месте, сабпроцессы ok."""
    root = repo.root
    monkeypatch.setattr(dr, "REPO", root, raising=True)
    monkeypatch.setattr(dr, "VENV_PY", root / "venv" / "python.exe", raising=True)
    monkeypatch.setattr(dr, "ENV_PS1", root / "scripts" / "env.ps1", raising=True)
    monkeypatch.setattr(dr, "APP", root / "app-under-test", raising=True)
    monkeypatch.setattr(dr, "AUT_PATH", root / "state" / "app-under-test.yaml", raising=True)
    monkeypatch.setattr(dr, "ESCALATIONS_PATH", root / "state" / "escalations.md", raising=True)
    monkeypatch.setattr(dr, "_run", lambda args, timeout=60: (0, "deps-ok"), raising=True)
    monkeypatch.setattr(dr, "_which", lambda name: f"C:/fake/{name}", raising=True)

    def touch(rel: str, text: str = "x") -> Path:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    touch("venv/python.exe")
    touch("scripts/env.ps1",
          '$root = "IGNORED"\n'
          '$env:JAVA_HOME        = "$root\\tools\\jdk"\n'
          '$env:ANDROID_HOME     = "$root\\tools\\android-sdk"\n'
          '$env:ANDROID_AVD_HOME = "$root\\tools\\avd"\n')
    touch("tools/jdk/bin/java.exe")
    touch("tools/android-sdk/platform-tools/adb.exe")
    touch(f"tools/avd/{dr.AVD_NAME}.ini")
    touch("tools/appium/package.json")
    touch("app-under-test/gradlew.bat")
    touch("state/rules.yaml")
    touch("state/sla.yaml")
    touch("schemas/transitions.yaml")
    touch("state/app-under-test.yaml", "apk_path: app-under-test/app.apk\n")
    touch("app-under-test/app.apk")
    # env.ps1 использует $root репозитория — подменяем подстановку на tmp-корень
    monkeypatch.setattr(dr, "_env_paths", lambda: {
        "JAVA_HOME": root / "tools" / "jdk",
        "ANDROID_HOME": root / "tools" / "android-sdk",
        "ANDROID_AVD_HOME": root / "tools" / "avd",
    }, raising=True)
    return touch


def test_healthy_env_all_ok(repo, env):
    checks = dr.run_checks()
    assert all(c.ok for c in checks), [f"{c.name}: {c.detail}" for c in checks if not c.ok]
    assert dr.main([]) == 0
    assert not (repo.root / "state" / "escalations.md").exists()


def test_missing_adb_fails_and_escalates(repo, env):
    (repo.root / "tools" / "android-sdk" / "platform-tools" / "adb.exe").unlink()

    assert dr.main([]) == 1

    esc = repo.read_artifact("state/escalations.md")
    assert "**DOCTOR**" in esc and "adb" in esc


def test_escalation_deduplicated(repo, env):
    (repo.root / "tools" / "android-sdk" / "platform-tools" / "adb.exe").unlink()

    dr.main([])
    dr.main([])

    esc = repo.read_artifact("state/escalations.md")
    assert esc.count("**DOCTOR**") == 1


def test_missing_apk_is_warn_not_fail(repo, env):
    (repo.root / "app-under-test" / "app.apk").unlink()

    checks = dr.run_checks()
    apk = next(c for c in checks if c.name == "APK по apk_path")
    assert not apk.ok and apk.warn
    assert dr.main([]) == 0            # WARN не валит doctor


def test_no_escalate_flag(repo, env):
    (repo.root / "tools" / "android-sdk" / "platform-tools" / "adb.exe").unlink()

    assert dr.main(["--no-escalate"]) == 1
    assert not (repo.root / "state" / "escalations.md").exists()
