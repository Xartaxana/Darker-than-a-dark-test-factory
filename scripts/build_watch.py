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

--- M-A: двухрежимный источник сборки (спека spec-build-source-dual-mode v4) ---

`--provided pipeline:<iid>|job:<id>` — ОТДЕЛЬНАЯ ветка (A5), обрабатывается ДО
detect_new_commits (тот про local-пуши, provided-поток от него не зависит):
скачивает готовый debug-артефакт из GitLab CI СВОЕГО repo (endpoint строится
ТОЛЬКО из api_base(read_repo_url()) + числового ref — никогда из внешнего
текста), копирует APK в канонический путь, честно читает версии из
output-metadata.json архива, пишет build_source: provided + provided_ref.
Локальная ветка (update_aut) СИММЕТРИЧНО пишет build_source: local +
provided_ref: "" (C2) — yaml никогда не врёт про источник.

Скачивание — bs.download_artifact(): urllib с ЯВНЫМ запретом авто-редиректа
(GitLabClient._request НЕ используется — тот портит бинарь json-fallback'ом);
ЛЮБОЙ 3xx повторяется БЕЗ PRIVATE-TOKEN (C4), кап цепочки редиректов 3; кап
тела загрузки 250МБ потоково (Content-Length не доверяем). Извлечение —
безопасное: капы 200МБ/500 членов ДО extractall И потоково при фактической
записи; zip-slip/symlink-члены отклоняются явно ДО extractall (не полагаемся
молча на санитайзинг stdlib); не-UTF8 имена — отказ; отсутствие app-debug.apk
(release-раскладка) — отказ с перечнем фактических путей архива.

404/протухший артефакт → [WARN] + fallback build_source: local (обычная
локальная сборка) + эскалация. Прочие отказы (битый zip/zip-бомба/zip-slip/
не-UTF8/нет apk/нет metadata) → [FAIL] + эскалация, БЕЗ fallback (--provided —
осознанное действие оператора/разработчика, молчаливая подмена на локальную
сборку была бы сюрпризом).

Идемпотентность по ref (B11): запрошенный ref совпадает с yaml И файл на диске
проходит sha256-сверку → «уже актуально», без сети.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

import board_sync as bs
import gitlab_sync as gs

REPO = bs.REPO
APP = REPO / "app-under-test"
AUT_PATH = REPO / "state" / "app-under-test.yaml"
ESCALATIONS_PATH = REPO / "state" / "escalations.md"
ORCH_LOG = REPO / "state" / "orchestrator-log.md"
ENV_PS1 = REPO / "scripts" / "env.ps1"
APK_REL = "app/build/outputs/apk/debug/app-debug.apk"
# M-B.1: источник версий ОДИН для local/provided — output-metadata.json,
# который AGP кладёт РЯДОМ с APK (та же директория). Regex по gradle убран.
METADATA_REL = "app/build/outputs/apk/debug/output-metadata.json"

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
    закрыт в board_sync.py/board_inbound.py/gitlab_sync.py/stale_locks.py.

    AT-BUG-041 остаток (п.(а), батч): разделитель между 'field:' и значением —
    [ \\t]* (только горизонтальные пробел/таб), НЕ \\s* — '\\s' в Python re
    матчит и '\\n'/'\\r' (не только пробел/таб), так что на поле с ПУСТЫМ
    значением ('field:' без хвоста на своей строке) старый \\s* пересекал
    перевод строки и продолжал жадно съедать пробельные символы дальше,
    поглощая НАЧАЛО следующей строки в тело замены (доказано эмпирически:
    'coalesced_commits:\\nversion_code: 11\\n' с заменой 'coalesced_commits'
    -> '[]' стирало строку version_code целиком). [ \\t]* останавливается на
    границе строки — [^#\\r\\n]*/lookahead ниже уже эту границу удерживают
    для остальной части значения."""
    pattern = re.compile(rf'(?m)^{field}:[ \t]*[^#\r\n]*(?P<comment>#[^\r\n]*)?(?=\r?\n|$)')
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
    # AT-BUG-041 остаток (п.(г), батч): read_bytes/decode вместо read_text —
    # унификация класса (последний читатель модуля через text-режим);
    # поведенчески нейтрально — результат сразу проходит _read_field's
    # .strip(), CRLF/LF-разница не наблюдаема вызывающим кодом.
    current = _read_field(AUT_PATH.read_bytes().decode("utf-8"), "source_commit") or ""
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


def read_app_versions(metadata_path: Path) -> tuple[str | None, str | None]:
    """M-B.1: versionName/versionCode из output-metadata.json (AGP пишет его
    РЯДОМ с APK — источник ОДИН для local-сборки и provided-артефакта; regex
    по gradle убран). Путь ПАРАМЕТРОМ (A5) — исключает приписывание локальных
    версий скачанному билду (или наоборот).

    M-B.2: файла нет / битый JSON / нет elements[0] -> (None, None) ЦЕЛИКОМ
    (не частично) — вызывающий код превращает это в literal 'unknown' +
    эскалацию BUILD-VERSION-UNKNOWN, не переносит старые значения."""
    if not metadata_path.exists():
        return None, None
    try:
        data = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, None
    elements = data.get("elements") or []
    if not elements or not isinstance(elements[0], dict):
        return None, None
    el = elements[0]
    vname = el.get("versionName")
    vcode = el.get("versionCode")
    vname_s = str(vname) if vname not in (None, "") else None
    vcode_s = str(vcode) if vcode is not None else None
    if not vname_s or not vcode_s:
        return None, None
    return vname_s, vcode_s


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_and_eol(path: Path) -> tuple[str, str]:
    """(текст файла, EOL-стиль по факту) — '' / '\\n', если файла нет/
    нечитаем. AT-BUG-041 остаток (п.(в), батч): текст нужен ДВАЖДЫ —
    определить eol И добить перевод строки перед append, если файл
    существует, но не кончается EOL (дозаказ, п.2 — тот же приём, что
    loop_lock._write_loop_escalation: `elif not text.endswith('\\n'):
    text += eol`). Тот же образец, что board_inbound._file_eol
    (AT-BUG-038)."""
    if not path.exists():
        return "", "\n"
    try:
        text = path.read_bytes().decode("utf-8", errors="replace")
    except OSError:
        return "", "\n"
    return text, ("\r\n" if "\r\n" in text else "\n")


def _append_escalation(reason: str) -> None:
    # AT-BUG-041 остаток (п.(в), батч): open("a", encoding="utf-8") БЕЗ
    # newline="" писал os.linesep (CRLF на Windows) независимо от стиля
    # файла — образец правильной формы: log_append.py::_append_line
    # (newline="\n"/"" — обе отключают трансляцию на запись, см. докстринг
    # той функции). newline="" + явный eol в строке ниже держат байты
    # ровно такими, каких мы просим. `pad` (дозаказ, п.2) — файл
    # существует, но не кончается EOL -> добивка перед новой строкой, не
    # слияние с последней существующей.
    text, eol = _read_and_eol(ESCALATIONS_PATH)
    header = "" if ESCALATIONS_PATH.exists() else (
        "# Эскалации фабрики\n\nАктивные варнинги, требующие человека "
        "(docs/06 §4). Строку удаляет человек по разрешении.\n\n").replace("\n", eol)
    pad = eol if (text and not text.endswith("\n")) else ""
    line = f"- [{_utcnow_s()}] **BUILD** — {reason}{eol}"
    with ESCALATIONS_PATH.open("a", encoding="utf-8", newline="") as f:
        f.write(header + pad + line)


def _append_orch_log(outcome: str) -> None:
    # AT-BUG-041 остаток (п.(в), батч) — см. _append_escalation; pad — дозаказ п.2.
    text, eol = _read_and_eol(ORCH_LOG)
    header = "" if ORCH_LOG.exists() else (
        "# Журнал оркестратора\n\n| Время | Правило | Агент | Артефакт | Исход |\n|---|---|---|---|---|\n"
    ).replace("\n", eol)
    pad = eol if (text and not text.endswith("\n")) else ""
    line = (f"| {_utcnow_s()} | pre_step build_watch | build_watch.py | "
            f"state/app-under-test.yaml | {outcome} |{eol}")
    with ORCH_LOG.open("a", encoding="utf-8", newline="") as f:
        f.write(header + pad + line)


def _apply_version_fields(text: str, vname: str | None, vcode: str | None, *, context: str) -> str:
    """M-B.2: не читается -> version-поля = literal 'unknown' + эскалация
    BUILD-VERSION-UNKNOWN + [WARN]; старые значения НЕ переносятся."""
    if not vname or not vcode:
        _append_escalation(
            f"BUILD-VERSION-UNKNOWN: {context} — output-metadata.json не даёт "
            f"versionName/versionCode (vname={vname!r}, vcode={vcode!r}); "
            f"версии выставлены 'unknown'")
        print(f"  [WARN] BUILD-VERSION-UNKNOWN: {context} — версии сборки неизвестны")
        vname = vname or "unknown"
        vcode = vcode or "unknown"
    text = _rewrite_field(text, "version_name", f'"{vname}"')
    text = _rewrite_field(text, "version_code", vcode)
    return text


def update_aut(tip: str, coalesced: list[str], apk_sha: str) -> None:
    # AT-BUG-041 (сиблинг AT-BUG-038/040, класс 1 — EOL-перегон): read_bytes/
    # write_bytes вместо read_text/write_text. Text-режим (newline=None)
    # молча перегоняет ВСЕ окончания строк файла при КАЖДОЙ записи (на
    # Windows LF -> CRLF), даже если правится набор отдельных полей —
    # доказано критиком на копии реального (чисто-LF) app-under-test.yaml.
    text = AUT_PATH.read_bytes().decode("utf-8")
    vname, vcode = read_app_versions(APP / METADATA_REL)
    text = _rewrite_field(text, "source_commit", tip)
    text = _rewrite_field(text, "coalesced_commits",
                          "[" + ", ".join(s[:8] for s in coalesced) + "]")
    text = _apply_version_fields(text, vname, vcode, context=f"локальная сборка {tip[:8]}")
    text = _rewrite_field(text, "apk_sha256", f'"{apk_sha}"')
    text = _rewrite_field(text, "built_at", f'"{_utcnow_s()}"')
    # C2: симметрия источника — локальная ветка ВСЕГДА возвращает поля в
    # local-состояние (после provided-прохода следующая локальная сборка не
    # оставляет yaml во вранье про источник).
    text = _rewrite_field(text, "build_source", "local")
    text = _rewrite_field(text, "provided_ref", '""')
    # Критик-вход (мелочь 3): race_note — ТОЛЬКО про provided-режим; local-
    # сборка обязана явно зачистить его тоже (не оставлять чужую гонку
    # висеть после смены источника обратно на local).
    text = _rewrite_field(text, "race_note", '""')
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


# =============================================================================
# M-A: двухрежимный источник сборки — provided-канал
# =============================================================================

# Критик-вход (мелочь 4): [0-9], не \d — Python re по умолчанию \d матчит
# ЛЮБОЙ Unicode-символ категории Nd (десятичная цифра), не только ASCII
# 0-9 (напр. арабо-индийские/деванагари цифры); ref идёт напрямую в
# endpoint (api_base + число) — сузили до заведомо ASCII-числа.
PROVIDED_REF_RE = re.compile(r"^(pipeline|job):([0-9]+)$")
BUILD_DEBUG_JOB_NAME = "build:debug"

# A4: капы (потоковые счётчики, заголовкам/заявленным размерам не доверяем).
MAX_REDIRECTS = 3
MAX_BODY_BYTES = 250 * 1024 * 1024
MAX_EXTRACTED_BYTES = 200 * 1024 * 1024
MAX_ZIP_MEMBERS = 500


class ArtifactError(Exception):
    """Отказ скачивания/извлечения provided-артефакта. [FAIL] + эскалация,
    БЕЗ fallback на local (--provided — осознанное действие, не подменяем
    молча тем, о чём не просили)."""


class ArtifactNotFoundError(ArtifactError):
    """404/протухший артефакт / нет job build:debug в пайплайне.
    [WARN] + fallback build_source: local + эскалация (A4)."""


def _parse_provided_ref(ref: str, flag_name: str = "--provided") -> tuple[str, int]:
    """Критик-вход (нит 1, 2026-08-10): `flag_name` параметризован — общая
    функция обслуживает ДВЕ CLI-поверхности (--provided, --download-only);
    хардкод '--provided' в сообщении рапортовал бы чужим флагом при вызове
    из download_only() (напр. `--download-only bogus` печатал бы
    «[FAIL] --provided 'bogus'...» — вводящее в заблуждение имя)."""
    m = PROVIDED_REF_RE.match((ref or "").strip())
    if not m:
        raise ValueError(
            f"{flag_name} '{ref}': ожидается 'pipeline:<iid>' или 'job:<id>' "
            f"(ТОЛЬКО число — endpoint строится ИЗ него, никогда из текста)")
    return m.group(1), int(m.group(2))


def _repo_url() -> str:
    """Локальная копия gs.read_repo_url(), но читает СВОЙ (монкипатчащийся
    тестами через bw.AUT_PATH) путь — НЕ gs.AUT_PATH (независимый модульный
    атрибут, `repo` тестовая фикстура патчит только bw.*).

    AT-BUG-041 остаток (п.(г)-аналог, дозаказ): read_bytes/decode вместо
    read_text — унификация класса читателей этого модуля; поведение
    yaml.safe_load не меняется (CRLF/LF-разница не наблюдаема парсером)."""
    import yaml
    data = yaml.safe_load(AUT_PATH.read_bytes().decode("utf-8")) or {}
    repo = data.get("repo")
    if not repo:
        raise SystemExit(f"build_watch: {AUT_PATH} — поле 'repo:' отсутствует или пусто")
    return str(repo).strip()


def _resolve_job(client: gs.GitLabClient, kind: str, num: int) -> dict:
    """kind: "pipeline"|"job". Возвращает job dict GitLab API (id, status,
    finished_at, pipeline.sha, artifacts_file)."""
    if kind == "job":
        try:
            _status, job = client.get(f"/jobs/{num}")
        except gs.GitLabHTTPError as e:
            if e.status == 404:
                raise ArtifactNotFoundError(f"job {num} не найден (404)") from e
            raise ArtifactError(f"job {num}: {e}") from e
        return job or {}
    try:
        _status, jobs = client.get(f"/pipelines/{num}/jobs", params={"per_page": 100})
    except gs.GitLabHTTPError as e:
        if e.status == 404:
            raise ArtifactNotFoundError(f"pipeline {num} не найден (404)") from e
        raise ArtifactError(f"pipeline {num}: {e}") from e
    jobs = jobs or []
    candidates = [j for j in jobs if j.get("name") == BUILD_DEBUG_JOB_NAME]
    if not candidates:
        raise ArtifactNotFoundError(
            f"pipeline {num}: job '{BUILD_DEBUG_JOB_NAME}' не найден среди "
            f"{len(jobs)} джобов пайплайна")
    return max(candidates, key=lambda j: j.get("id") or 0)


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """A4/C4: отключает АВТО-редирект целиком — redirect_request() -> None
    заставляет urlopen поднять HTTPError с кодом 3xx вместо молчаливого
    follow (стандартный идиом stdlib). Дальше редирект обрабатывается
    ВРУЧНУЮ в _http_get_binary — Location берётся, PRIVATE-TOKEN на
    повторный запрос НЕ передаётся."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _http_get_binary(url: str, token: str | None, *, opener=None,
                      max_redirects: int = MAX_REDIRECTS,
                      max_body_bytes: int = MAX_BODY_BYTES,
                      timeout: int = 120) -> bytes:
    """A4: без авто-редиректа; ЛЮБОЙ 3xx (301/302/303/307/308) повторяется
    БЕЗ PRIVATE-TOKEN; кап цепочки редиректов <= max_redirects (петля =
    отказ); кап тела <= max_body_bytes ПОТОКОВЫМ счётчиком при чтении
    (Content-Length заголовку не доверяем).

    `opener` — инъекция для тестов (объект с `.open(request, timeout=...)`,
    без реальной сети); по умолчанию — настоящий urllib-opener без
    HTTPRedirectHandler по умолчанию (заменён _NoRedirectHandler)."""
    real_opener = opener or urllib.request.build_opener(_NoRedirectHandler)
    current_url = url
    current_token = token
    redirects = 0
    while True:
        headers = {"PRIVATE-TOKEN": current_token} if current_token else {}
        req = urllib.request.Request(current_url, headers=headers, method="GET")
        try:
            resp = real_opener.open(req, timeout=timeout)
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 303, 307, 308):
                redirects += 1
                if redirects > max_redirects:
                    raise ArtifactError(
                        f"кап цепочки редиректов ({max_redirects}) превышен: {current_url}") from e
                location = e.headers.get("Location") if e.headers else None
                if not location:
                    raise ArtifactError(f"редирект {e.code} без заголовка Location: {current_url}") from e
                current_url = urllib.parse.urljoin(current_url, location)
                current_token = None   # C4: PRIVATE-TOKEN НЕ уезжает на редиректе
                continue
            if e.code == 404:
                raise ArtifactNotFoundError(f"HTTP 404: {current_url}") from e
            raise ArtifactError(f"HTTP {e.code}: {current_url}") from e
        except urllib.error.URLError as e:
            raise ArtifactError(f"сетевая ошибка ({current_url}): {e.reason}") from e
        try:
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_body_bytes:
                    raise ArtifactError(
                        f"тело артефакта превышает кап {max_body_bytes} байт "
                        f"(потоковый счётчик — Content-Length заголовку не доверяем)")
                chunks.append(chunk)
            return b"".join(chunks)
        finally:
            close = getattr(resp, "close", None)
            if close:
                close()


def _is_symlink_member(zi: zipfile.ZipInfo) -> bool:
    """C6: unix-права члена архива хранятся в старших 16 битах external_attr
    (S_IFLNK = 0xA000 << 16). Архивы GitLab CI создаются на Linux-раннере —
    поле заполнено честно."""
    mode = (zi.external_attr >> 16) & 0xFFFF
    return (mode & 0xF000) == 0xA000


def _is_suspicious_member_path(name: str) -> bool:
    """B12/C6: zip-slip — абсолютный путь или '..'-сегмент. Проверяется ДО
    extractall (stdlib с некоторой версии сам санирует такие пути, но молча
    — нам нужен ЯВНЫЙ, наблюдаемый отказ, не тихая перезапись имени)."""
    norm = name.replace("\\", "/")
    if norm.startswith("/"):
        return True
    return ".." in norm.split("/")


def _member_name_is_utf8(zi: zipfile.ZipInfo) -> tuple[bool, bytes]:
    """Возвращает (валидно_ли_utf8, исходные_байты_имени). Если бит UTF-8
    флага (0x800) установлен — zipfile уже декодировал имя как UTF-8 (валидно
    по построению). Иначе имя декодировано zipfile'ом как cp437 — реконструируем
    исходные байты и проверяем, валидны ли они как UTF-8 (легитимные
    современные архивы почти всегда ставят флаг; отсутствие флага + байты, не
    являющиеся валидным UTF-8, — легаси/чужеродная кодировка, отказ)."""
    if zi.flag_bits & 0x800:
        return True, zi.filename.encode("utf-8")
    raw = zi.filename.encode("cp437", errors="replace")
    try:
        raw.decode("utf-8")
        return True, raw
    except UnicodeDecodeError:
        return False, raw


def _safe_extract_zip(data: bytes, dest_dir: Path) -> tuple[Path, Path]:
    """B12/C5/C6: капы (<=200МБ распакованного, <=500 членов) ДО extractall
    (по заявленным `sum(file_size)`/`len(infolist())`) И потоковым счётчиком
    ПОСЛЕ фактической записи (заявленным размерам заголовка не верим — их
    контролирует автор архива); только `zipfile.extractall` в ПУСТУЮ tmp-
    директорию (никакого ручного `os.path.join` по `namelist()`); symlink-
    члены и подозрительные (zip-slip) пути отклоняются ЯВНО ДО extractall;
    не-UTF8 имена членов — отказ с именем hex'ом; отсутствие app-debug.apk
    (release-раскладка) — отказ с перечнем фактических путей архива;
    output-metadata.json обязателен рядом с APK."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise ArtifactError(f"битый zip-архив: {e}") from e

    with zf:
        infolist = zf.infolist()
        if len(infolist) > MAX_ZIP_MEMBERS:
            raise ArtifactError(
                f"zip-бомба: {len(infolist)} членов архива > лимита {MAX_ZIP_MEMBERS}")
        declared_total = sum(zi.file_size for zi in infolist)
        if declared_total > MAX_EXTRACTED_BYTES:
            raise ArtifactError(
                f"zip-бомба: заявленный распакованный размер {declared_total} байт "
                f"> лимита {MAX_EXTRACTED_BYTES}")

        for zi in infolist:
            if _is_symlink_member(zi):
                raise ArtifactError(f"symlink-член архива запрещён: {zi.filename!r}")
            if _is_suspicious_member_path(zi.filename):
                raise ArtifactError(f"подозрительный путь члена архива (zip-slip): {zi.filename!r}")
            ok_utf8, raw_bytes = _member_name_is_utf8(zi)
            if not ok_utf8:
                raise ArtifactError(f"не-UTF8 имя члена архива: {raw_bytes.hex()}")

        # Только extractall в пустую tmp-директорию — не ручной join по namelist().
        #
        # Критик-мелочь 1 (2026-08-10, разбор эмпирикой): попытка доказать эту
        # ветку byte-патчем ЗАНИЖЕННОГО central-directory file_size (тот же
        # приём, что _member_name_is_utf8-тест) провалилась НЕ из-за слабости
        # теста, а из-за реального поведения cpython zipfile — `ZipExtFile.
        # __init__` ставит `self._left = zinfo.file_size` и `_read1()` делает
        # `data = data[:self._left]`: физическая запись НЕ МОЖЕТ превысить
        # ДЕКЛАРИРОВАННЫЙ file_size через `extractall()` (при попытке солгать
        # заниженно она просто обрывает поток и валит `BadZipFile: Bad CRC-32`
        # раньше, чем что-либо запишется сверх декларации). Это значит: через
        # ЛЕГИТИМНЫЙ `zipfile.extractall()` (единственный путь извлечения в
        # этом коде — ручного join нет) written_total НИКОГДА не превысит
        # sum(zi.file_size), т.е. пре-чек ВЫШЕ уже ловит любой одетый bomb-
        # сценарий; постфактум-счётчик ниже — оставлен ЯВНО как defense-in-
        # depth (риск диска принят: дешёвый повторный проход по файлам после
        # extractall) на случай будущих изменений поведения stdlib или
        # редких путей (несколько членов с совпадающими именами и т.п.), НЕ
        # потому что он ловит какой-то конкретный сегодняшний обход пре-чека.
        #
        # Находка ПО ХОДУ той же эмпирики (не мелочь критика, замечено
        # самостоятельно): zf.extractall() САМ может поднять zipfile.
        # BadZipFile (напр. Bad CRC-32 — битый/обрезанный в транзите архив;
        # реалистичный сценарий, не только синтетический byte-патч) — ДО
        # этой правки такое исключение НЕ ловилось (try/except выше покрывал
        # только zipfile.ZipFile(...) — парсинг, не extractall), и улетало
        # бы наружу СЫРЫМ zipfile.BadZipFile мимо ArtifactError/
        # ArtifactNotFoundError — download_artifact/watch_provided его не
        # ловят, весь build_watch.py упал бы трейсбеком вместо честного
        # [FAIL]+эскалации.
        try:
            zf.extractall(dest_dir)
        except zipfile.BadZipFile as e:
            raise ArtifactError(f"битый/обрезанный zip-архив при извлечении: {e}") from e
        written_total = sum(
            f.stat().st_size for f in dest_dir.rglob("*") if f.is_file())
        if written_total > MAX_EXTRACTED_BYTES:
            raise ArtifactError(
                f"zip-бомба: фактически записано {written_total} байт "
                f"> лимита {MAX_EXTRACTED_BYTES} (заявленным размерам заголовка не доверяли)")

    apk_matches = sorted(dest_dir.rglob("app-debug.apk"))
    if not apk_matches:
        all_paths = sorted(str(p.relative_to(dest_dir)) for p in dest_dir.rglob("*") if p.is_file())
        raise ArtifactError(
            "в архиве нет app-debug.apk (release-раскладка? "
            f"фактические пути архива: {all_paths})")
    apk_path = apk_matches[0]
    metadata_path = apk_path.parent / "output-metadata.json"
    if not metadata_path.exists():
        raise ArtifactError(f"output-metadata.json отсутствует рядом с APK ({apk_path})")
    return apk_path, metadata_path


def download_artifact(client: gs.GitLabClient, kind: str, num: int, token: str,
                       base_url: str, *, opener=None) -> dict:
    """A4: резолвит ref (pipeline:<iid>|job:<id>) в job, качает zip-архив
    джоба БЕЗ авто-редиректов, безопасно извлекает в пустую tmp-директорию,
    находит app-debug.apk + output-metadata.json.

    Возвращает {"apk_path", "metadata_path", "source_commit", "built_at",
    "tmp_dir"} — ВЫЗЫВАЮЩИЙ обязан прибрать tmp_dir (shutil.rmtree) после
    того, как скопирует apk_path/metadata_path — они живут ВНУТРИ tmp_dir."""
    job = _resolve_job(client, kind, num)
    job_id = job.get("id")
    if not job_id:
        raise ArtifactNotFoundError(f"{kind}:{num}: job id отсутствует в ответе API")
    if not job.get("artifacts_file"):
        raise ArtifactNotFoundError(
            f"{kind}:{num}: job {job_id} без артефактов (протух/не собран/expired)")
    pipeline = job.get("pipeline") or {}
    source_commit = pipeline.get("sha")
    finished_at = job.get("finished_at")
    if not source_commit or not finished_at:
        raise ArtifactError(
            f"{kind}:{num}: ответ API job {job_id} без pipeline.sha/finished_at")

    url = f"{base_url}/jobs/{job_id}/artifacts"
    body = _http_get_binary(url, token, opener=opener)

    tmp_dir = Path(tempfile.mkdtemp(prefix="build_watch_artifact_"))
    try:
        apk_path, metadata_path = _safe_extract_zip(body, tmp_dir)
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise

    return {"apk_path": apk_path, "metadata_path": metadata_path,
            "source_commit": source_commit, "built_at": finished_at, "tmp_dir": tmp_dir}


def _local_commits_ahead_of_provided(source_commit: str) -> str:
    """A1: гонка источников — provided-sha может быть СТАРШЕ, чем то, что уже
    есть в удалённом app-under-test (разработчик продолжил пушить после
    коммита, вошедшего в скачанный артефакт). Best-effort: fetch недоступен
    (офлайн) -> молча пусто (та же деградация уже видна для local-пути через
    detect_new_commits на следующем обычном проходе). Непустой результат
    печатается И уходит в yaml-комментарий (критик: проигравший источник не
    должен исчезать молча)."""
    fetch_env = dict(os.environ) | GIT_FETCH_ENV_EXTRA
    rc, _out = _run(["git", "-C", str(APP), "fetch", "origin"], timeout=60, env=fetch_env)
    if rc != 0:
        return ""
    rc, tip = _run(["git", "-C", str(APP), "rev-parse", "FETCH_HEAD"])
    if rc != 0:
        return ""
    tip = tip.strip()
    if not tip or tip == source_commit:
        return ""
    rc, lst = _run(["git", "-C", str(APP), "rev-list", "--reverse", f"{source_commit}..{tip}"])
    if rc != 0:
        return ""
    shas = [s for s in lst.split() if s]
    if not shas:
        return ""
    return (f"поверх provided {source_commit[:8]} {len(shas)} несобранных коммитов: "
            + ", ".join(s[:8] for s in shas))


def update_aut_provided(ref: str, source_commit: str, built_at: str, apk_sha: str,
                         metadata_path: Path) -> None:
    text = AUT_PATH.read_bytes().decode("utf-8")
    vname, vcode = read_app_versions(metadata_path)

    race_note = _local_commits_ahead_of_provided(source_commit)
    if race_note:
        print(f"  [INFO] {race_note}")
    # Критик-вход (мелочь 3, 2026-08-10): race_note НЕ встраивается в
    # хвостовой комментарий source_commit — _rewrite_field ПЕРЕИСПОЛЬЗУЕТ
    # существующий хвостовой комментарий поля при КАЖДОЙ последующей
    # перезаписи (задумано для человеческих аннотаций вроде "# 2026-06-28"),
    # так что встроенный туда race-note пережил бы следующую запись этого
    # же поля и стал бы враньём (устаревшая гонка приписывалась бы новой
    # сборке). Отдельное поле `race_note` — ВСЕГДА перезаписывается явно
    # (пусто, если гонки нет), зачищается каждой записью, никогда не липнет.
    text = _rewrite_field(text, "source_commit", source_commit)
    text = _rewrite_field(text, "race_note", f'"{race_note}"')
    text = _rewrite_field(text, "coalesced_commits", "[]")
    text = _apply_version_fields(text, vname, vcode, context=f"provided {ref}")
    text = _rewrite_field(text, "apk_sha256", f'"{apk_sha}"')
    # C8: built_at = finished_at джоба/пайплайна из API, НЕ время скачивания.
    text = _rewrite_field(text, "built_at", f'"{built_at}"')
    text = _rewrite_field(text, "build_source", "provided")
    text = _rewrite_field(text, "provided_ref", f'"{ref}"')
    text = _rewrite_field(text, "smoke_status", "not_run")
    text = _rewrite_field(text, "regression_status", "not_run")
    AUT_PATH.write_bytes(text.encode("utf-8"))


def watch_provided(ref: str) -> int:
    try:
        kind, num = _parse_provided_ref(ref)
    except ValueError as e:
        print(f"  [FAIL] {e}")
        return 1

    aut_text = AUT_PATH.read_bytes().decode("utf-8") if AUT_PATH.exists() else ""
    current_ref = (_read_field(aut_text, "provided_ref") or "").strip('"')
    if current_ref == ref:
        # B11: идемпотентность по ref — sha-сверка на диске, БЕЗ сети.
        apk_field = (_read_field(aut_text, "apk_path") or "").strip()
        expected_sha = (_read_field(aut_text, "apk_sha256") or "").strip('"')
        apk = (REPO / apk_field) if apk_field else None
        if apk is not None and apk.exists() and expected_sha and expected_sha.lower() != "unknown" \
                and _sha256(apk) == expected_sha:
            print(f"build_watch --provided: {ref} уже актуально "
                  f"(sha256 совпадает, скачивание пропущено — B11)")
            return 0

    token = os.environ.get("GITLAB_TOKEN")
    if not token:
        _append_escalation(f"--provided {ref}: GITLAB_TOKEN не задан, скачивание невозможно")
        print(f"  [FAIL] --provided {ref}: нет GITLAB_TOKEN в окружении")
        return 1

    repo_url = _repo_url()
    base = gs.api_base(repo_url)
    client = gs.GitLabClient(base, token)

    try:
        artifact = download_artifact(client, kind, num, token, base)
    except ArtifactNotFoundError as e:
        print(f"  [WARN] --provided {ref}: {e} — пробуем штатный локальный путь build_watch")
        rc = watch(dry=False)
        # Критик-вход (мелочь 2): НЕ утверждать «откатилась на local», пока
        # это не факт — watch() мог найти «новых коммитов нет» (source_commit
        # уже совпадает с tip) и НИЧЕГО не поменять; тогда yaml остаётся
        # ровно тем, чем был ДО этого вызова (в т.ч. build_source: provided,
        # если он был таким) — сообщение обязано отражать РЕАЛЬНЫЙ исход.
        aut_after = AUT_PATH.read_bytes().decode("utf-8") if AUT_PATH.exists() else ""
        build_source_after = (_read_field(aut_after, "build_source") or "").strip()
        if build_source_after == "local":
            outcome = "фабрика перешла на build_source: local (локальная сборка выполнена)"
        else:
            outcome = (f"локальный watch() НЕ изменил build_source (сейчас: "
                      f"{build_source_after or 'неизвестно'!r}) — вероятно, новых "
                      f"local-коммитов не было; yaml остался как был ДО этого вызова")
        _append_escalation(f"--provided {ref}: артефакт недоступен/протух ({e}) — {outcome}")
        return rc
    except ArtifactError as e:
        _append_escalation(f"--provided {ref}: {e}")
        print(f"  [FAIL] --provided {ref}: {e}")
        return 1

    try:
        dest = APP / APK_REL
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(artifact["apk_path"], dest)
        apk_sha = _sha256(dest)
        update_aut_provided(ref, artifact["source_commit"], artifact["built_at"],
                            apk_sha, artifact["metadata_path"])
    finally:
        shutil.rmtree(artifact["tmp_dir"], ignore_errors=True)

    _append_orch_log(f"OK: provided {ref} sha {artifact['source_commit'][:8]}")
    print(f"  [OK] --provided {ref}: APK установлен из артефакта "
          f"({artifact['source_commit'][:8]}), app-under-test.yaml обновлён "
          f"(smoke/regression сброшены в not_run)")
    return 0


def download_only(ref: str, dest_dir: str) -> int:
    """B2 (критик-раунд 2026-08-10): точечная загрузка БЕЗ побочных эффектов
    на state/app-under-test.yaml или канонический путь — носитель A3(б) для
    fix-verifier.md («скачать модулем build_watch (download-функция),
    установить точечно... ГЛОБАЛЬНЫЙ state/app-under-test.yaml НЕ трогать»).
    Скачивает артефакт, безопасно извлекает, копирует APK и
    output-metadata.json в `dest_dir` (создаётся, если нет), печатает их
    пути (`APK: <path>` / `METADATA: <path>`) и завершается — canonical
    apk_path НЕ читается и НЕ пишется вовсе; yaml (state/app-under-test.yaml)
    ЧИТАЕТСЯ (_repo_url() — только поле `repo:`, для api_base), но НИКОГДА
    не пишется (критик-вход, нит 2: «не читаются» про yaml было неточно)."""
    try:
        kind, num = _parse_provided_ref(ref, flag_name="--download-only")
    except ValueError as e:
        print(f"  [FAIL] {e}")
        return 1

    token = os.environ.get("GITLAB_TOKEN")
    if not token:
        print(f"  [FAIL] --download-only {ref}: нет GITLAB_TOKEN в окружении")
        return 1

    repo_url = _repo_url()
    base = gs.api_base(repo_url)
    client = gs.GitLabClient(base, token)

    try:
        artifact = download_artifact(client, kind, num, token, base)
    except ArtifactError as e:
        print(f"  [FAIL] --download-only {ref}: {e}")
        return 1

    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    apk_dest = dest / artifact["apk_path"].name
    metadata_dest = dest / artifact["metadata_path"].name
    try:
        shutil.copy2(artifact["apk_path"], apk_dest)
        shutil.copy2(artifact["metadata_path"], metadata_dest)
    finally:
        shutil.rmtree(artifact["tmp_dir"], ignore_errors=True)

    print(f"APK: {apk_dest}")
    print(f"METADATA: {metadata_dest}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="build_watch: пуш приложения → сборка APK")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--provided", default=None, metavar="pipeline:<iid>|job:<id>",
                        help="A3/A5: собрать НЕ из локального push, а из готового "
                             "GitLab CI артефакта СВОЕГО repo")
    parser.add_argument("--download-only", default=None, metavar="pipeline:<iid>|job:<id>",
                        help="B2: точечная загрузка артефакта БЕЗ побочных эффектов "
                             "(yaml/канонический путь не трогает) — печатает пути "
                             "APK/output-metadata.json в --dest; для fix-verifier A3(б)")
    parser.add_argument("--dest", default=None, metavar="<dir>",
                        help="каталог назначения для --download-only (обязателен вместе с ним)")
    args = parser.parse_args(argv)
    if args.download_only:
        if not args.dest:
            print("build_watch: --download-only требует --dest <dir>")
            return 1
        return download_only(args.download_only, args.dest)
    if args.provided:
        return watch_provided(args.provided)
    return watch(dry=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
