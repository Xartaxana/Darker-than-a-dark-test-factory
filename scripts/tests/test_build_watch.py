"""Юнит-тесты pre_step build_watch (scripts/build_watch.py).

Реальные git/gradle не вызываются: bw._run подменяется фейковым раннером,
который отвечает канонными выводами и (для gradlew) создаёт APK-файл.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

import build_watch as bw

OLD_SHA = "a" * 40
MID_SHA = "b" * 40
TIP_SHA = "c" * 40

AUT_TEXT = f"""app: ao3-wrapper
repo: https://gitlab.com/Xartaxana1/ao3-wrapper
source_commit: {OLD_SHA}   # старая сборка
version_name: "1.10"
version_code: 11
build_type: debug
apk_path: app-under-test/{bw.APK_REL}
apk_sha256: "deadbeef"
built_at: "2026-07-02T02:39:46"
smoke_status: passed     # not_run | passed | failed
regression_status: passed
"""

GRADLE_KTS = 'android { defaultConfig { versionCode = 12\nversionName = "1.11" } }\n'


def _setup(repo, *, new_commits=(MID_SHA, TIP_SHA)):
    aut = repo.root / "state" / "app-under-test.yaml"
    aut.parent.mkdir(parents=True, exist_ok=True)
    aut.write_text(AUT_TEXT, encoding="utf-8")
    gradle = repo.root / "app-under-test" / "app" / "build.gradle.kts"
    gradle.parent.mkdir(parents=True, exist_ok=True)
    gradle.write_text(GRADLE_KTS, encoding="utf-8")
    return aut, list(new_commits)


class FakeRunner:
    """Отвечает как git/gradle; пишет журнал вызовов для ассертов."""

    def __init__(self, repo_root: Path, new_commits: list[str],
                 *, fetch_rc=0, gradle_rc=0, checkout_rc=0, rev_list_rc=0,
                 fetch_out=None, token_fetch_rc=0, token_fetch_out=""):
        self.root = repo_root
        self.new = new_commits
        self.fetch_rc, self.gradle_rc, self.checkout_rc = fetch_rc, gradle_rc, checkout_rc
        self.rev_list_rc = rev_list_rc
        self.fetch_out = fetch_out if fetch_out is not None else "fatal: unable to access"
        self.token_fetch_rc = token_fetch_rc
        self.token_fetch_out = token_fetch_out
        self.calls: list[str] = []
        self.envs: list[dict | None] = []

    def __call__(self, args, *, cwd=None, env=None, timeout=120):
        cmd = " ".join(str(a) for a in args)
        self.calls.append(cmd)
        self.envs.append(env)
        if "fetch" in cmd:
            if "credential.helper=" in cmd:                     # M3 token-ретрай
                return self.token_fetch_rc, self.token_fetch_out
            return self.fetch_rc, "" if self.fetch_rc == 0 else self.fetch_out
        if "rev-parse" in cmd:
            return 0, (self.new[-1] if self.new else OLD_SHA) + "\n"
        if "rev-list" in cmd:
            if self.rev_list_rc != 0:
                return self.rev_list_rc, "fatal: Invalid revision range"
            return 0, "\n".join(self.new) + "\n"
        if "checkout" in cmd:
            return self.checkout_rc, "" if self.checkout_rc == 0 else "error: pathspec"
        if "gradlew" in cmd:
            if self.gradle_rc == 0:
                apk = self.root / "app-under-test" / bw.APK_REL
                apk.parent.mkdir(parents=True, exist_ok=True)
                apk.write_bytes(b"fake-apk-bytes")
            return self.gradle_rc, "BUILD SUCCESSFUL" if self.gradle_rc == 0 else "BUILD FAILED: err"
        raise AssertionError(f"неожиданная команда: {cmd}")


@pytest.fixture()
def runner(repo, monkeypatch):
    def make(**kw):
        new = kw.pop("new_commits", (MID_SHA, TIP_SHA))
        _, commits = _setup(repo, new_commits=new)
        r = FakeRunner(repo.root, commits, **kw)
        monkeypatch.setattr(bw, "_run", r, raising=True)
        return r
    return make


def test_no_new_commits_noop(repo, runner):
    runner(new_commits=())          # rev-parse вернёт OLD_SHA == source_commit
    before = repo.read_artifact("state/app-under-test.yaml")

    assert bw.watch() == 0
    assert repo.read_artifact("state/app-under-test.yaml") == before


def test_new_commits_build_updates_yaml(repo, runner):
    r = runner()

    assert bw.watch() == 0

    text = repo.read_artifact("state/app-under-test.yaml")
    assert f"source_commit: {TIP_SHA}" in text
    assert "# старая сборка" in text                        # комментарий пережил правку
    assert f"coalesced_commits: [{MID_SHA[:8]}]" in text    # D11
    assert 'version_name: "1.11"' in text and "version_code: 12" in text
    assert "smoke_status: not_run" in text and "regression_status: not_run" in text
    assert "deadbeef" not in text                           # sha256 пересчитан
    log = repo.read_artifact("state/orchestrator-log.md")
    assert "pre_step build_watch" in log and TIP_SHA[:8] in log
    assert any("gradlew" in c for c in r.calls)


def test_build_failure_escalates_and_keeps_yaml(repo, runner):
    runner(gradle_rc=1)
    before = repo.read_artifact("state/app-under-test.yaml")

    assert bw.watch() == 1

    assert repo.read_artifact("state/app-under-test.yaml") == before
    esc = repo.read_artifact("state/escalations.md")
    assert "**BUILD**" in esc and "[sla:" not in esc        # без тега — снимает человек


def test_offline_fetch_degrades_quietly(repo, runner):
    runner(fetch_rc=128)
    assert bw.watch() == 0
    assert not (repo.root / "state" / "escalations.md").exists()


def test_shallow_clone_rev_list_failure_degrades_to_tip_only(repo, runner, capsys):
    """docs/09 «Мелкое хозяйство» п.3: shallow-клон app-under-test -> `git
    rev-list current..tip` падает (родитель недоступен локально) -> сборка
    всё равно проходит (guard, не unshallow), но деградация теперь ВИДНА в
    выводе (WARN), а не тихо теряется в coalesced_commits: []."""
    r = runner(rev_list_rc=128)

    assert bw.watch() == 0

    text = repo.read_artifact("state/app-under-test.yaml")
    assert f"source_commit: {TIP_SHA}" in text
    assert "coalesced_commits: []" in text          # диапазон не восстановлен -> пуст
    out = capsys.readouterr().out
    assert "[WARN]" in out and "shallow" in out
    assert any("rev-list" in c for c in r.calls)


def test_dry_run_detects_but_does_not_build(repo, runner):
    r = runner()
    before = repo.read_artifact("state/app-under-test.yaml")

    assert bw.watch(dry=True) == 0

    assert repo.read_artifact("state/app-under-test.yaml") == before
    assert not any("gradlew" in c or "checkout" in c for c in r.calls)


# ---------------------------------------------------------------------------
# M3 (plan-m1-m4.md v3, [B9][B7], 2026-08-09): headless-safe fetch creds
# ---------------------------------------------------------------------------

AUTH_FAIL_OUT = ("fatal: could not read Username for 'https://gitlab.com': "
                 "terminal prompts disabled")


def test_fetch_env_extra_preserves_os_environ(repo, runner, monkeypatch):
    """env-надбавка GIT_TERMINAL_PROMPT/GCM_INTERACTIVE ДОБАВЛЯЕТСЯ поверх
    os.environ, не заменяет его целиком (B7: голый словарь терял бы
    SystemRoot/PATH и git не видел бы GITLAB_TOKEN)."""
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)
    r = runner()

    assert bw.watch(dry=True) == 0

    fetch_env = r.envs[0]
    assert fetch_env is not None
    assert fetch_env.get("GIT_TERMINAL_PROMPT") == "0"
    assert fetch_env.get("GCM_INTERACTIVE") == "never"
    # Надбавка, не замена (B7): fetch_env МИНУС две добавленные ключа обязан
    # байт-в-байт совпасть с os.environ на момент вызова (SystemRoot/PATH и
    # прочее — не потеряны). os.environ на Windows хранит ключи в верхнем
    # регистре независимо от их написания в коде — сверяем через dict(...),
    # не хардкодя написание отдельных имён (класс F-34: сужающий фильтр
    # регистра ловил бы ложный негатив на "SystemRoot" != "SYSTEMROOT").
    extra_keys = {"GIT_TERMINAL_PROMPT", "GCM_INTERACTIVE"}
    without_extra = {k: v for k, v in fetch_env.items() if k not in extra_keys}
    base = {k: v for k, v in dict(os.environ).items() if k not in extra_keys}
    assert without_extra == base


def test_fallback_only_on_auth_signature_offline_rc_gets_no_retry(repo, runner, monkeypatch):
    """Офлайн/сетевой rc (сигнатура НЕ совпадает) — ретрая нет ДАЖЕ при
    наличии GITLAB_TOKEN."""
    monkeypatch.setenv("GITLAB_TOKEN", "sekrit-token-value")
    r = runner(fetch_rc=128, fetch_out="fatal: unable to access 'https://gitlab.com/x': "
                                        "Could not resolve host")

    assert bw.watch() == 0

    fetch_calls = [c for c in r.calls if "fetch" in c]
    assert len(fetch_calls) == 1
    assert not any("credential.helper=" in c for c in r.calls)


def test_no_token_keeps_prior_warn_path_no_retry(repo, runner, monkeypatch, capsys):
    """Сигнатура auth-отказа совпадает, но GITLAB_TOKEN не задан — прежний
    [WARN]-путь без ретрая."""
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)
    r = runner(fetch_rc=128, fetch_out=AUTH_FAIL_OUT)

    assert bw.watch() == 0

    fetch_calls = [c for c in r.calls if "fetch" in c]
    assert len(fetch_calls) == 1
    out = capsys.readouterr().out
    assert "[WARN]" in out
    assert "GITLAB_TOKEN" not in out


def test_auth_signature_no_match_gets_unrecognized_marker(repo, runner, monkeypatch, capsys):
    """[R5(a)] Страховка: rc!=0 без совпадения сигнатуры несёт явную
    пометку «сигнатура ... не распознана» в [WARN] — детектор видим,
    даже если regex когда-нибудь перестанет ловить реальный отказ."""
    monkeypatch.setenv("GITLAB_TOKEN", "sekrit-token-value")
    r = runner(fetch_rc=128, fetch_out="fatal: unable to access 'https://gitlab.com/x': "
                                        "Could not resolve host")

    assert bw.watch() == 0

    out = capsys.readouterr().out
    assert "не распознана" in out


def test_auth_failure_with_token_retries_and_succeeds(repo, runner, monkeypatch, capsys):
    monkeypatch.setenv("GITLAB_TOKEN", "sekrit-token-value")
    r = runner(fetch_rc=128, fetch_out=AUTH_FAIL_OUT, token_fetch_rc=0, token_fetch_out="")

    assert bw.watch() == 0

    fetch_calls = [c for c in r.calls if "fetch" in c]
    assert len(fetch_calls) == 2                              # primary + ретрай
    assert any("credential.helper=" in c for c in r.calls)
    out = capsys.readouterr().out
    assert "[INFO] fetch через GITLAB_TOKEN" in out
    text = repo.read_artifact("state/app-under-test.yaml")
    assert f"source_commit: {TIP_SHA}" in text                # сборка продолжилась после ретрая


def test_retry_failure_prints_redacted_out2(repo, runner, monkeypatch, capsys):
    """Критик-фикс (некритично п.3, 2026-08-09): неуспешный ретрай с
    GITLAB_TOKEN печатает СВОЙ (редактированный) вывод — иначе scope-отказ
    токена (read_repository не выдан) недиагностируем оператором."""
    secret = "sekrit-token-value-abc"
    monkeypatch.setenv("GITLAB_TOKEN", secret)
    r = runner(fetch_rc=128, fetch_out=AUTH_FAIL_OUT, token_fetch_rc=1,
               token_fetch_out=f"remote: 403 Forbidden (scope insufficient, token={secret})")

    assert bw.watch() == 0

    out = capsys.readouterr().out
    assert "ретрай с GITLAB_TOKEN тоже не прошёл" in out
    assert "403 Forbidden" in out
    assert secret not in out                                  # редактирован
    assert "***" in out


def test_redact_strips_token_from_output_and_argv(repo, runner, monkeypatch, capsys):
    secret = "sekrit-token-value-zzz"
    monkeypatch.setenv("GITLAB_TOKEN", secret)
    auth_out = (f"fatal: could not read Username for 'https://gitlab.com': "
               f"terminal prompts disabled (echoed token={secret} rejected)")
    r = runner(fetch_rc=128, fetch_out=auth_out, token_fetch_rc=1,
               token_fetch_out="retry failed too")

    assert bw.watch() == 0

    out = capsys.readouterr().out
    assert secret not in out
    assert "***" in out
    assert not any(secret in c for c in r.calls)              # argv не несёт литерала токена
