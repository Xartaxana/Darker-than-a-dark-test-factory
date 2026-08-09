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
import os
import re
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
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

# M3 (plan-m1-m4.md v3, [B9][B7], 2026-08-09): env-надбавка ТОЛЬКО для
# fetch-вызовов — GIT_TERMINAL_PROMPT=0/GCM_INTERACTIVE=never отключают
# интерактивный фолбэк GCM/git в headless Task Scheduler-контексте (без
# них падение прежде повисало бы на промпте вместо честного rc!=0/[WARN]).
GIT_FETCH_ENV_EXTRA = {"GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}

# [B9/R5] Regex ВЫВЕДЕН из дословных выводов падающего fetch (эмпирика
# builder-диспатча M3, 2026-08-09 — реальный gitlab.com-URL требующий
# auth, GIT_TERMINAL_PROMPT=0, обе формы credential.helper):
#   форма 1 (helper явно отключён -c credential.helper=):
#     "fatal: could not read Username for 'https://gitlab.com': terminal
#     prompts disabled"
#   форма 2 (активный GCM, GCM_INTERACTIVE=never, пустое credential-хранилище):
#     "fatal: Cannot prompt because user interactivity has been disabled.
#     fatal: could not read Username for 'https://gitlab.com': terminal
#     prompts disabled"
# Обе формы разделяют "could not read Username"/"terminal prompts disabled";
# GCM даёт отдельно ещё "Cannot prompt because user interactivity" — своя
# ветка альтернации на случай, если GCM когда-нибудь изменит общую
# формулировку. "Authentication failed"/"could not read Password" —
# ориентир-минимум спеки (иные формы того же класса отказа, не
# воспроизведённые буквально в этом окружении, но покрытые на случай
# другого поведения сервера/GCM).
AUTH_FAILURE_RE = re.compile(
    r"authentication failed|could not read username|could not read password|"
    r"terminal prompts disabled|cannot prompt because user interactivity",
    re.IGNORECASE)


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
    после source_commit (или в конец файла).

    AT-BUG-041: границы полей — [^#\\r\\n]* / [^\\r\\n]* + lookahead (?=\\r?\\n|$),
    НЕ [^#\\n]*/.*$. '.' в (?m)-режиме матчит '\\r' (не матчит только '\\n'), а
    класс [^#\\n] тоже его не исключает — жадный старый паттерн поглощал
    завершающий '\\r' строки в тело матча и терял его при замене на строке БЕЗ
    хвостового комментария (доказано эмпирически: 'version_code: 11\\r\\n' ->
    'version_code: 99\\n' на старом паттерне). Тот же образец границы, что уже
    закрыт в board_sync.py/board_inbound.py/gitlab_sync.py/stale_locks.py."""
    pattern = re.compile(rf'(?m)^{field}:\s*[^#\r\n]*(?P<comment>#[^\r\n]*)?(?=\r?\n|$)')
    m = pattern.search(text)
    if m:
        comment = f"   {m.group('comment')}" if m.group("comment") else ""
        return pattern.sub(f"{field}: {value}{comment}", text, count=1)
    # AT-BUG-041: поля НЕТ в файле (типично coalesced_commits — его нет и в
    # реальном state/app-under-test.yaml по состоянию на 2026-08-02, эта
    # ветка исполняется на КАЖДОМ реальном вызове update_aut) — новая строка
    # вставляется со стилем EOL самого файла (по факту, как _file_eol в
    # board_inbound.py), а не хардкодным '\n', иначе первая же вставка заводит
    # постоянно смешанный EOL в файле, который до неё был однородным.
    eol = "\r\n" if "\r\n" in text else "\n"
    anchor = re.search(r"(?m)^(source_commit:[^\r\n]*)", text)
    if anchor:
        return text.replace(anchor.group(1), f"{anchor.group(1)}{eol}{field}: {value}", 1)
    return text.rstrip("\r\n") + f"{eol}{field}: {value}{eol}"


def _redact(text: str) -> str:
    """[B7] Значение GITLAB_TOKEN -> '***' перед ЛЮБОЙ печатью fetch-вывода
    (секрет не должен оказаться в консоли/logs/heartbeat.log/orchestrator-log)."""
    token = os.environ.get("GITLAB_TOKEN", "")
    if not token:
        return text
    return text.replace(token, "***")


def _fetch_with_token(env: dict) -> tuple[int, str]:
    """[B7] Ретрай fetch с GITLAB_TOKEN через одноразовый inline
    credential-хелпер: `-c credential.helper=` сбрасывает список
    хелперов пустым значением ПЕРЕД добавлением своего — GCM не
    опрашивается первым (GCM_INTERACTIVE=never в fetch_env уже отключил
    его интерактивный фолбэк, но без сброса списка сам вызов GCM всё
    равно шёл бы первым и съедал время до отказа). Inline-хелпер выводит
    `username=oauth2`/`password=$GITLAB_TOKEN` — значение токена в argv
    НЕ попадает (раскрывается git-порождённым sh() из окружения)."""
    helper = "!f() { echo username=oauth2; echo password=$GITLAB_TOKEN; }; f"
    return _run(
        ["git", "-C", str(APP), "-c", "credential.helper=",
         "-c", f"credential.helper={helper}", "fetch", "origin"],
        timeout=60, env=env)


def detect_new_commits() -> dict | None:
    """fetch + сравнение с source_commit. None = проверить не удалось (офлайн).

    M3 (plan-m1-m4.md v3, [B9], 2026-08-09): fetch идёт с env-надбавкой
    GIT_FETCH_ENV_EXTRA (GIT_TERMINAL_PROMPT=0/GCM_INTERACTIVE=never) —
    headless Task Scheduler-контекст не может ответить на интерактивный
    промпт GCM. Провал, чья ошибка совпадает с AUTH_FAILURE_RE (эмпирика
    R5(а): реальные дословные выводы обеих форм — helper явно отключён и
    активный GCM с пустым хранилищем, обе дали "could not read
    Username"/"terminal prompts disabled") И для которого доступен
    GITLAB_TOKEN — ретраится ОДИН раз через _fetch_with_token() (60с,
    inline credential-хелпер). Провал без совпадения сигнатуры (или без
    токена) деградирует как раньше ([WARN], код 0) — та же семантика,
    что и офлайн.

    Shallow-клон app-under-test (docs/09 «Мелкое хозяйство» п.3, 2026-07-18):
    на shallow-клоне `current` (старый source_commit) типично отсутствует в
    локальной истории, `git rev-list current..tip` падает с ненулевым rc
    («fatal: Invalid revision range», эмпирически проверено на реальном
    клоне этого репо — он действительно shallow, `--is-shallow-repository`
    -> true). Полный `git fetch --unshallow` — не минимальное решение
    (качает всю историю ради метаданных coalesced_commits, которые нигде
    не блокируют сборку) — вместо этого используем УЖЕ существовавший
    fallback `rc != 0 -> new = [tip]` (собрать только tip как единственный
    новый коммит), но раньше он был ПОЛНОСТЬЮ МОЛЧАЛИВЫМ: coalesced_commits
    в app-under-test.yaml тихо получал "[]", даже если реально было
    несколько пушей подряд — оператор не мог отличить «правда один пуш» от
    «диапазон не восстановился». Guard ниже делает деградацию видимой."""
    fetch_env = dict(os.environ) | GIT_FETCH_ENV_EXTRA
    rc, out = _run(["git", "-C", str(APP), "fetch", "origin"], timeout=180, env=fetch_env)
    if rc != 0:
        token = os.environ.get("GITLAB_TOKEN", "")
        matched = bool(AUTH_FAILURE_RE.search(out))
        if matched and token:
            # [B7][R5(б)] Fallback ТОЛЬКО по auth-сигнатуре И при наличии
            # токена — офлайн/сетевой rc без совпадения сигнатуры в
            # ретрай не идёт (см. else-ветку ниже).
            rc2, out2 = _fetch_with_token(fetch_env)
            if rc2 == 0:
                print("  [INFO] fetch через GITLAB_TOKEN (GCM недоступен headless)")
                rc, out = rc2, out2
            else:
                print(f"  [WARN] git fetch не прошёл (офлайн/недоступен origin): "
                      f"{_redact(out).strip()[:200]}")
                # Критик-фикс (некритично п.3, 2026-08-09): без этой строки
                # неуспех РЕТРАЯ (напр. scope-отказ токена — read_repository
                # не выдан) недиагностируем — оператор видит только исходный
                # WARN и не узнаёт, что попытка с GITLAB_TOKEN тоже провалилась.
                print(f"  [WARN] ретрай с GITLAB_TOKEN тоже не прошёл (возможен "
                      f"scope-отказ токена): {_redact(out2).strip()[:200]}")
                return None
        else:
            # [R5(a)] Страховка: rc!=0 БЕЗ совпадения сигнатуры (или без
            # токена для ретрая) — прежний [WARN]-путь; отсутствие
            # совпадения помечается явно, чтобы «механизм есть, не
            # триггерится» было видно оператору, а не тонуло молча.
            suffix = " (сигнатура auth-отказа не распознана)" if not matched else ""
            print(f"  [WARN] git fetch не прошёл (офлайн/недоступен origin){suffix}: "
                  f"{_redact(out).strip()[:200]}")
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
    if rc == 0:
        new = [s for s in lst.split() if s]
    else:
        print(f"  [WARN] git rev-list {current[:8]}..{tip[:8]} не прошёл (вероятно, "
              f"shallow-клон app-under-test — родитель {current[:8]} недоступен локально): "
              f"диапазон не восстановить, собираем только tip как единственный новый "
              f"коммит (coalesced_commits будет пуст, даже если пушей было несколько)")
        new = [tip]
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
    # AT-BUG-041 (сиблинг AT-BUG-038/040, класс 1 — EOL-перегон): read_bytes/
    # write_bytes вместо read_text/write_text. Text-режим (newline=None)
    # молча перегоняет ВСЕ окончания строк файла при КАЖДОЙ записи (на
    # Windows LF -> CRLF), даже если правится набор отдельных полей —
    # доказано критиком на копии реального (чисто-LF) app-under-test.yaml.
    text = AUT_PATH.read_bytes().decode("utf-8")
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
    AUT_PATH.write_bytes(text.encode("utf-8"))


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
