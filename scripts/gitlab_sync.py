"""gitlab_sync — однонаправленный идемпотентный sync bugs/BUG-*.md -> GitLab Issues.

Задача N3 (docs/tasks/2026-08-01_gitlab-bugs-publish.md): публикация багов
ПРИЛОЖЕНИЯ (id-префикс `BUG-`, frontmatter `type` отсутствует или `app_bug`)
в GitLab Issues проекта из state/app-under-test.yaml (`repo:`). AT-BUG-*
(test debt фабрики) пропускаются молча — это решение оператора 2026-08-01,
не фильтр качества.

Канонический источник — bugs/*.md; синхронизация ОДНОНАПРАВЛЕННАЯ (правки в
GitLab обратно не тянутся). Идемпотентность держит frontmatter-поле
`gitlab_issue: <iid>`; при его отсутствии выполняется adopt-поиск по
префиксу заголовка "BUG-NNN" (защита от дублей) ДО создания нового issue.

stdlib-only сетевой слой (urllib.request) — без новых зависимостей;
PyYAML для чтения frontmatter/app-under-test.yaml уже существующая
зависимость репозитория (framework/requirements.txt), не новая.

CLI:
  python scripts/gitlab_sync.py                 # sync всех подходящих BUG-*
  python scripts/gitlab_sync.py --bug BUG-011    # только один
  python scripts/gitlab_sync.py --dry-run        # офлайн, план (create/sync-check)
  python scripts/gitlab_sync.py --check          # офлайн-детектор несинхронизированных

Аутентификация: токен ТОЛЬКО из env GITLAB_TOKEN (заголовок PRIVATE-TOKEN).
--dry-run/--check работают полностью офлайн, без токена и без сети — сетевой
транспорт (GitLabClient) в этих режимах не создаётся вовсе.

Сетевой слой вынесен в GitLabClient с инъекцией транспорта (`transport`
параметр конструктора либо монкипатч модульного `_default_transport`) —
тесты подменяют его без сети (scripts/tests/test_gitlab_sync.py).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
BUGS_DIR = REPO / "bugs"
AUT_PATH = REPO / "state" / "app-under-test.yaml"

# Тот же паттерн, что board_sync._parse_frontmatter/validate_frontmatter, но
# заточен на нахождение ТОЧНОЙ границы для writeback: non-greedy `.*?` перед
# `\r?\n---\r?\n` останавливается на ПЕРВОЙ строке "---" после открывающей —
# это важно, т.к. тело bug-файла легитимно содержит горизонтальные линии
# markdown "---" (напр. bugs/BUG-014.md перед "## Чек-лист качества"); слепой
# re.sub по любому "^---$" задел бы их.
FRONTMATTER_RE = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)

# Строка существующего поля gitlab_issue внутри тела frontmatter (не EOL —
# он захватывается отдельно/остаётся нетронутым при replace). Шаблон
# docs/templates/bug-report.md с 2026-08-01 кладёт пустой плейсхолдер
# 'gitlab_issue: ""' в КАЖДЫЙ новый bug-файл -- writeback обязана ЗАМЕНИТЬ
# эту строку, а не слепо вставлять вторую (BUG-021 живьём: две строки
# 'gitlab_issue:' -> невалидный YAML, PyYAML.safe_load молча берёт
# последнее значение без ошибки -- баг маскировался, но портил данные).
# `\s*` перед двоеточием (R3 остатка critic-входа writeback-фикса,
# 2026-08-02, HANDOFF.md): ловит и ключ с пробелом(ами) перед ':'
# ('gitlab_issue :', 'gitlab_issue  :'), которые PyYAML.safe_load тоже
# успешно парсит как то же поле, но старый паттерн без `\s*` их не находил
# -> insert-ветка вставила бы ВТОРУЮ строку 'gitlab_issue:' поверх такого
# frontmatter (тот же класс дубля, что и породивший это поле). Якорь `^`
# + отсутствие `\s*` ПОСЛЕ 'gitlab_issue' (т.е. следующий символ обязан
# быть пробелом/двоеточием) сохраняет НЕ-матч на похожих ключах
# ('gitlab_issue_x:') — это НЕ то же поле. Контракт применения — ТОЛЬКО
# срез тела frontmatter (text[body_start:body_end] в writeback_gitlab_issue
# ниже), не весь файл: одноимённая строка в ТЕЛЕ bug-файла (после
# frontmatter) вне области поиска и writeback её не трогает.
# `[ \t]*`, не `\s*` (критик-вход раунда 2, N4): `\s` включает перевод
# строки — на входе 'gitlab_issue\n: 5' матч перескочил бы строку; в
# валидных bugs/*.md недостижимо, но паттерн точнее по намерению.
GITLAB_ISSUE_LINE_RE = re.compile(r"^gitlab_issue[ \t]*:[^\r\n]*", re.MULTILINE)

TITLE_MAX = 255

# Маппинг статуса фабрики в GitLab issue state (правило спеки; словарь GitLab
# API — issue.state ∈ {"opened", "closed"}, не "open"; PUT state_event
# принимает глаголы "close"/"reopen", это отдельный словарь ниже).
STATE_MAP = {
    "Open": "opened",
    "Reopened": "opened",
    "Fixed": "opened",
    "Blocked": "opened",
    "Verified": "closed",
    "Rejected": "closed",
    "Intended": "closed",
}

FOOTER_TMPL = (
    "\n\n---\n*Экспортировано из тест-фабрики (`bugs/{bug_id}.md`); "
    "канонический источник — артефакт фабрики, правки в GitLab обратно "
    "не синхронизируются; ссылки на attachments/ указывают на локальные "
    "артефакты фабрики.*"
)


class BugSyncError(Exception):
    """Ошибка обработки ОДНОГО бага (репортится, остальные обрабатываются)."""


class GitLabHTTPError(Exception):
    def __init__(self, status: int, body: bytes, method: str, url: str):
        self.status = status
        self.body = body
        try:
            snippet = body.decode("utf-8", errors="replace")[:300]
        except AttributeError:
            snippet = str(body)[:300]
        msg = f"GitLab API {method} {url} -> HTTP {status}: {snippet}"
        if status == 401:
            msg += (" (подсказка: проверьте переменную окружения GITLAB_TOKEN "
                     "и её scope 'api')")
        super().__init__(msg)


# --- Проект из state/app-under-test.yaml -----------------------------------

def read_repo_url() -> str:
    data = yaml.safe_load(AUT_PATH.read_text(encoding="utf-8")) or {}
    repo = data.get("repo")
    if not repo:
        raise SystemExit(
            f"gitlab_sync: {AUT_PATH} — поле 'repo:' отсутствует или пусто")
    return str(repo).strip()


def parse_project(repo_url: str) -> tuple[str, str]:
    """https://gitlab.com/Xartaxana1/ao3-wrapper -> ("gitlab.com", "Xartaxana1/ao3-wrapper").

    parsed.hostname (+ ':' + port), НЕ parsed.netloc (рекомендация 3
    критик-ревью): netloc включает userinfo ("user:pass@host"), если он
    присутствует в repo URL — тогда он утёк бы в api_base() и дальше в
    тексты ошибок GitLabHTTPError/SystemExit."""
    parsed = urllib.parse.urlparse(repo_url)
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    path = parsed.path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    if not host or not path:
        raise SystemExit(f"gitlab_sync: не удалось разобрать repo URL '{repo_url}'")
    return host, path


def api_base(repo_url: str) -> str:
    host, path = parse_project(repo_url)
    encoded = urllib.parse.quote(path, safe="")
    return f"https://{host}/api/v4/projects/{encoded}"


# --- Сетевой слой (тонкий, инъекция транспорта для тестов) -----------------

def _default_transport(method: str, url: str, headers: dict, data: bytes | None):
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except urllib.error.URLError as e:
        # Нет HTTP-статуса вовсе (DNS/сеть недоступны) — синтетический 0,
        # тот же путь обработки ошибок (_request подскажет про GITLAB_TOKEN
        # только на 401, тут просто прозрачно всплывёт сообщение urllib).
        return 0, str(e.reason).encode("utf-8", errors="replace")


class GitLabClient:
    def __init__(self, base_url: str, token: str | None, transport=None):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._transport = transport

    def _run_transport(self, method, url, headers, data):
        transport = self._transport or _default_transport
        return transport(method, url, headers, data)

    def _request(self, method: str, path: str, *, params: dict | None = None,
                 json_body=None):
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        headers: dict[str, str] = {}
        if self.token:
            headers["PRIVATE-TOKEN"] = self.token
        data = None
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        status, body = self._run_transport(method, url, headers, data)
        if status >= 400 or status == 0:
            raise GitLabHTTPError(status, body or b"", method, url)
        parsed = None
        if body:
            try:
                parsed = json.loads(body)
            except (json.JSONDecodeError, TypeError):
                parsed = body.decode("utf-8", errors="replace") if isinstance(body, bytes) else body
        return status, parsed

    def get(self, path: str, params: dict | None = None):
        return self._request("GET", path, params=params)

    def post(self, path: str, json_body):
        return self._request("POST", path, json_body=json_body)

    def put(self, path: str, json_body):
        return self._request("PUT", path, json_body=json_body)


# --- Артефакты bugs/*.md ----------------------------------------------------

def discover_bugs(bug_filter: str | None = None) -> list[Path]:
    if bug_filter:
        p = BUGS_DIR / f"{bug_filter}.md"
        return [p] if p.exists() else []
    if not BUGS_DIR.exists():
        return []
    files = []
    for p in sorted(BUGS_DIR.glob("*.md")):
        if p.name.upper() == "README.MD":
            continue
        # Префикс "BUG-" исключает "AT-BUG-*.md" (начинается с "AT-"), не
        # только по договорённости, но и структурно (stem не начинается с
        # "BUG-"). type-фильтр ниже (is_app_bug) — вторая, независимая
        # защита на случай аномалии frontmatter (спека требует ОБЕ проверки).
        if not p.stem.startswith("BUG-"):
            continue
        files.append(p)
    return files


def load_bug(path: Path) -> tuple[dict, str]:
    """Возвращает (meta, body) — body ВЕРБАТИМ (всё после закрывающего
    '---\\n' frontmatter, без модификаций) для description issue."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise BugSyncError(f"{path.name}: не читается ({e})")
    m = FRONTMATTER_RE.match(text)
    if not m:
        raise BugSyncError(f"{path.name}: битый frontmatter (нет закрывающего '---')")
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as e:
        raise BugSyncError(f"{path.name}: frontmatter не парсится YAML ({e})")
    if not isinstance(meta, dict):
        raise BugSyncError(f"{path.name}: frontmatter не является отображением полей")
    body = text[m.end():]
    return meta, body


def is_app_bug(meta: dict) -> bool:
    bug_type = meta.get("type")
    return bug_type in (None, "", "app_bug")


def is_seeded(meta: dict) -> bool:
    """Батч мелочей (репетиция тёмного дня, разбор 2026-08-09): сеяный
    артефакт репетиции/учений (schemas/bug.schema.yaml, поле `seeded`) — в
    GitLab не публикуется никогда, ни полным sync, ни точечным --bug.
    Нормализация обязательна — как у остальных читателей строковых bool
    репо (queue_snapshot:187, sla_sweep:190-194, ui_snapshot:56): PyYAML
    парсит `seeded: true` БЕЗ кавычек в bool True, а validate_frontmatter
    приводит bool к нижнему регистру до enum-проверки — schema-валидная
    форма проходила бы мимо строгого сравнения и сеяный утекал бы в
    GitLab (блокер 1 критик-входа 2026-08-09)."""
    return str(meta.get("seeded") or "").strip().lower() == "true"


def writeback_gitlab_issue(path: Path, iid: int) -> None:
    """Если в frontmatter УЖЕ есть строка 'gitlab_issue: <...>' (шаблонный
    плейсхолдер или предыдущий iid) — заменяет ТОЛЬКО эту строку на
    'gitlab_issue: <iid>'. Иначе вставляет новую строку ПЕРЕД закрывающим
    '---' frontmatter (прежнее поведение). Остальной файл в обоих случаях
    байт-в-байт нетронут (никакого yaml-dump). Поле `updated` НЕ трогается
    (sync-метаданные — не содержательная правка, спека раздела Writeback).

    БАЙТОВЫЙ ввод/вывод (read_bytes/write_bytes) намеренно, НЕ read_text/
    write_text: text-режим Path.read_text/write_text открывает файл с
    newline=None (universal newlines) — при ЛЮБОЙ записи это молча
    перегоняет ВСЕ окончания строк файла на '\\n', даже если исходный файл
    был CRLF (BUG-013 воспроизведение критика: вставка 18 байт -> рост
    файла на 161 при 8 из 11 целевых bugs/*.md LF и 3 CRLF). Вставляемый
    eol (insert-ветка) выбирается по факту, какой символ стоит сразу после
    конца frontmatter-тела в САМОМ файле (m.end(1)) — не глобальная
    перегонка; replace-ветка EOL не трогает вовсе (заменяется только
    содержимое строки ДО EOL, сам EOL остаётся в 'хвосте' файла как был)."""
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise BugSyncError(f"{path.name}: не декодируется как UTF-8 при writeback ({e})")
    m = FRONTMATTER_RE.match(text)
    if not m:
        raise BugSyncError(f"{path.name}: битый frontmatter при writeback")

    body_start, body_end = m.start(1), m.end(1)
    field_match = GITLAB_ISSUE_LINE_RE.search(text[body_start:body_end])
    if field_match is not None:
        abs_start = body_start + field_match.start()
        abs_end = body_start + field_match.end()
        new_text = text[:abs_start] + f"gitlab_issue: {iid}" + text[abs_end:]
    else:
        insert_at = body_end
        eol = "\r\n" if text[insert_at:].startswith("\r\n") else "\n"
        new_text = text[:insert_at] + f"{eol}gitlab_issue: {iid}" + text[insert_at:]
    path.write_bytes(new_text.encode("utf-8"))


# --- Маппинг bug -> GitLab issue --------------------------------------------

def desired_gitlab_state(status: str) -> str:
    try:
        return STATE_MAP[status]
    except KeyError:
        raise BugSyncError(
            f"неизвестный status '{status}' — маппинг в GitLab issue state "
            f"не определён (ожидается один из {sorted(STATE_MAP)})")


def build_title(bug_id: str, title: str) -> str:
    full = f"{bug_id}: {title}"
    if len(full) > TITLE_MAX:
        full = full[:TITLE_MAX]
    return full


# Наружный словарь ярлыков (решение владельца 2026-08-09): внутренний
# статус `Fixed` («починено, ЖДЁТ QA-верификации» — D1 ещё впереди)
# наружу проецируется ярлыком `QAready` — разработчику «Fixed» читается
# как «готово/закрыто», тогда как работа только входит в тестирование.
# Внутренняя машина статусов НЕ переименована (schemas/transitions.yaml
# остаётся единственным источником правды по статусам); словарь живёт
# ТОЛЬКО в проекции labels. Обратного словаря нет: статусы issue/label
# внутрь не переносятся (граница канала — docs/06 §3а).
STATUS_LABEL_ALIASES = {"Fixed": "QAready"}


def desired_labels(meta: dict) -> list[str]:
    severity = meta.get("severity", "")
    status = meta.get("status", "")
    status_label = STATUS_LABEL_ALIASES.get(status, status)
    return ["qa-factory", f"severity::{severity}", f"qa-status::{status_label}"]


def _join_list(value) -> str:
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value)


def build_description(meta: dict, body: str) -> str:
    rows: list[tuple[str, str]] = []
    if meta.get("severity"):
        rows.append(("Severity", str(meta["severity"])))
    if meta.get("status"):
        rows.append(("Статус фабрики", str(meta["status"])))
    if meta.get("found_in"):
        rows.append(("found_in", str(meta["found_in"])))
    if meta.get("test_cases"):
        rows.append(("test_cases", _join_list(meta["test_cases"])))
    if meta.get("runs"):
        rows.append(("runs", _join_list(meta["runs"])))

    table_lines = ["| Поле | Значение |", "|---|---|"]
    table_lines += [f"| {k} | {v} |" for k, v in rows]
    table = "\n".join(table_lines)

    footer = FOOTER_TMPL.format(bug_id=meta.get("id", ""))
    return f"{table}\n\n{body}{footer}"


def _require_iid(obj, bug_id: str, context: str) -> int:
    """Достаёт 'iid' из ответа GitLab (dict) или падает с BugSyncError,
    называющей баг и первые ~200 символов тела ответа — вместо необработанного
    KeyError, который валил бы весь батч (блокер 2 критик-ревью)."""
    iid = obj.get("iid") if isinstance(obj, dict) else None
    if not iid:
        if isinstance(obj, (dict, list)):
            snippet = json.dumps(obj, ensure_ascii=False)[:200]
        else:
            snippet = str(obj)[:200]
        raise BugSyncError(
            f"{bug_id}: ответ GitLab на {context} не содержит поля 'iid' "
            f"(тело: {snippet})")
    return int(iid)


# --- Sync одного бага --------------------------------------------------------

# Метки, которыми ВЛАДЕЕТ sync (единственные снимаемые при рассинхроне) —
# severity::* и qa-status::*; "qa-factory" тоже наш, но всегда желаем и никогда
# не становится устаревшим, снимать нечего. Любая другая метка (ручная метка
# разработчика вроде "workflow::doing") — чужая, sync её не трогает никогда
# (изменение спеки Lead 2026-08-01: PUT labels замещал всё множество и стирал
# бы ручные метки; add_labels/remove_labels — аддитивный API GitLab).
OWN_LABEL_PREFIXES = ("severity::", "qa-status::")


def _label_changes(current_labels: set[str], desired: list[str]) -> tuple[list[str], list[str]]:
    """Возвращает (add_labels, remove_labels) для аддитивного PUT.

    add_labels — желаемые метки, которых ещё нет среди текущих.
    remove_labels — СВОИ метки (см. OWN_LABEL_PREFIXES), присутствующие
    сейчас, но отсутствующие среди желаемых (устаревший severity/qa-status).
    Issue label-синхронна, когда оба списка пусты (желаемые ⊆ текущих И нет
    своих устаревших)."""
    desired_set = set(desired)
    add = [label for label in desired if label not in current_labels]
    remove = sorted(
        label for label in current_labels
        if label.startswith(OWN_LABEL_PREFIXES) and label not in desired_set
    )
    return add, remove


# --- M-D/D4/E4: safeguard против уничтожения QAready-сигнала гонкой --------
#
# gitlab_sync НЕ бежит в проходе /qa-loop (только session-handoff/ad-hoc) —
# окно «разработчик поставил qa-status::QAready вручную, gitlab_inbound
# (M-D) ещё не перевёл внутренний статус бага в Fixed, человек тем временем
# запустил gitlab_sync» НЕ ограничено проходом. Без safeguard'а _label_changes
# считал бы qa-status::QAready «устаревшей своей меткой» (desired_labels()
# для НЕ-Fixed статуса хочет qa-status::<Open|Reopened|...>, не QAready) и
# remove_labels стёр бы сигнал разработчика молча. Вес защиты — здесь: при
# remove qa-status::QAready с бага в Open|Reopened — skip ИМЕННО этой метки
# (остальные add/remove в том же PUT остаются штатными) + персистентная
# эскалация с дедупом ключа (образец gitlab_inbound._qaready_key_already_pending,
# gitlab_inbound.py:490-508) + [WARN] в stdout.
#
# v4.1 (2026-08-10, разбор ПЕРВОГО живого прогона с этим safeguard'ом):
# граница изначальной v4 («НЕ-Fixed») оказалась ШИРЕ задуманного — на
# Verified/Rejected/Intended (BUG-001/BUG-057, issue #1/#18 УЖЕ закрыты)
# guard молча пропустил снятие ярлыка-сироты + завёл 2 ложные эскалации.
# Сужено до Open|Reopened (QAREADY_SAFEGUARD_STATUSES) — терминальные и
# Fixed-статусы означают, что наша проекция УЖЕ ушла дальше сигнала
# разработчика, снятие qa-status::QAready там легитимно.
QAREADY_LABEL = "qa-status::QAready"
ESCALATIONS_PATH = REPO / "state" / "escalations.md"


def _escalation_key_already_pending(key: str) -> bool:
    """Дедуп по ключу (та же якорная детекция `[resolved:...]`, что
    gitlab_inbound._qaready_key_already_pending) — одна строка на ключ, не
    строка на каждый прогон sync, пока гонка длится."""
    if not ESCALATIONS_PATH.exists():
        return False
    pat = re.compile(r"\*\*" + re.escape(key) + r"\*\*(\s*\[resolved:[^\]]*\])?")
    for line in ESCALATIONS_PATH.read_text(encoding="utf-8", errors="replace").splitlines():
        if key not in line:
            continue
        m = pat.search(line)
        if m and not m.group(1):
            return True
    return False


def _append_escalation(key: str, reason: str) -> None:
    import datetime
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    header = "" if ESCALATIONS_PATH.exists() else (
        "# Эскалации фабрики\n\nАктивные варнинги, требующие человека "
        "(docs/06 §4). Живёт до разрешения; запись не удаляется, а "
        "помечается resolved при закрытии.\n\n")
    ESCALATIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with ESCALATIONS_PATH.open("a", encoding="utf-8") as f:
        if header:
            f.write(header)
        f.write(f"- [{stamp}] **{key}** — {reason}\n")


QAREADY_SAFEGUARD_STATUSES = ("Open", "Reopened")


def _qaready_removal_safeguard(bug_id: str, status: str, remove_labels: list[str]) -> list[str]:
    """D4/E4 (v4.1, разбор живого прогона builder-смока 2026-08-10): remove
    qa-status::QAready — skip ЭТОЙ метки ТОЛЬКО на Open|Reopened (сигнал
    разработчика ещё НЕ сведён внутренним статусом). Границу «НЕ-Fixed»
    (изначальная v4) сузили: живой sync поймал ложные срабатывания на
    Verified/Rejected/Intended (BUG-001/BUG-057) — там наша проекция УЖЕ
    ушла дальше (issue закрыт), снятие qa-status::QAready легитимно и
    обязано проходить, иначе ярлык-сирота остаётся рядом с закрытым issue
    навсегда. Персистентная эскалация (дедуп по ключу) + [WARN] — только
    для реального срабатывания guard'а. Прочие remove_labels не трогаются."""
    if QAREADY_LABEL not in remove_labels or status not in QAREADY_SAFEGUARD_STATUSES:
        return remove_labels
    key = f"QAREADY-SYNC-RACE-{bug_id}"
    if not _escalation_key_already_pending(key):
        _append_escalation(
            key,
            f"{bug_id}: gitlab_sync собрался снять ярлык {QAREADY_LABEL} "
            f"(внутренний статус {status} — Open|Reopened, сигнал ещё не "
            f"сведён) — вероятная гонка с gitlab_inbound (ярлык поставлен "
            f"разработчиком, ещё не обработан). Ярлык СОХРАНЁН, снятие "
            f"пропущено; разберитесь и пометьте [resolved:<task_id>] после "
            f"проверки.")
    print(f"[WARN] gitlab_sync: {bug_id} — снятие {QAREADY_LABEL} пропущено "
          f"(внутренний статус {status}, см. эскалацию {key})")
    return [label for label in remove_labels if label != QAREADY_LABEL]


def _diff_and_update(client: GitLabClient, iid: int, issue: dict, *,
                      title: str, description: str, labels: list[str],
                      desired_state: str, bug_id: str, status: str) -> str:
    current_title = issue.get("title", "")
    current_description = issue.get("description") or ""
    current_labels = set(issue.get("labels") or [])
    current_state = issue.get("state", "")

    add_labels, remove_labels = _label_changes(current_labels, labels)
    remove_labels = _qaready_removal_safeguard(bug_id, status, remove_labels)

    changes: dict = {}
    if current_title != title:
        changes["title"] = title
    if current_description != description:
        changes["description"] = description
    if add_labels:
        changes["add_labels"] = ",".join(add_labels)
    if remove_labels:
        changes["remove_labels"] = ",".join(remove_labels)

    state_changed = current_state != desired_state
    if not changes and not state_changed:
        return "unchanged"
    if changes:
        client.put(f"/issues/{iid}", changes)
    if state_changed:
        state_event = "close" if desired_state == "closed" else "reopen"
        client.put(f"/issues/{iid}", {"state_event": state_event})
    return "updated"


def sync_bug(client: GitLabClient, path: Path, meta: dict, body: str) -> str:
    """Синхронизирует ОДИН уже загруженный баг (meta/body — результат
    load_bug). Возвращает короткий исход: created/adopted/updated/unchanged."""
    bug_id = str(meta.get("id", path.stem))
    status = str(meta.get("status", ""))
    desired_state = desired_gitlab_state(status)
    title = build_title(bug_id, str(meta.get("title", "")))
    description = build_description(meta, body)
    labels = desired_labels(meta)

    existing_iid = meta.get("gitlab_issue")
    if existing_iid:
        try:
            iid = int(existing_iid)
        except (TypeError, ValueError):
            raise BugSyncError(
                f"{bug_id}: некорректное поле gitlab_issue={existing_iid!r} "
                f"(ожидается целое число issue iid)")
        _status, issue = client.get(f"/issues/{iid}")
        return _diff_and_update(client, iid, issue or {}, title=title,
                                 description=description, labels=labels,
                                 desired_state=desired_state, bug_id=bug_id,
                                 status=status)

    # Adopt-защита от дублей: поиск существующего issue по заголовку ДО create.
    # Условие сужено (рекомендация 2 критик-ревью): чистый startswith(bug_id)
    # даёт ложное совпадение "BUG-100" внутри заголовка "BUG-1000: ..." —
    # префикс легален, только если сразу после bug_id НЕ идёт ещё одна цифра.
    _status, results = client.get("/issues", params={
        "search": bug_id, "in": "title", "per_page": 100})
    found = None
    for issue in (results or []):
        title_str = str(issue.get("title", ""))
        if title_str.startswith(bug_id) and not title_str[len(bug_id):][:1].isdigit():
            found = issue
            break

    if found is not None:
        iid = _require_iid(found, bug_id, "adopt-поиск (GET /issues)")
        writeback_gitlab_issue(path, iid)
        return "adopted:" + _diff_and_update(
            client, iid, found, title=title, description=description,
            labels=labels, desired_state=desired_state, bug_id=bug_id,
            status=status)

    _status, created = client.post("/issues", {
        "title": title, "description": description,
        "labels": ",".join(labels)})
    iid = _require_iid(created, bug_id, "создание issue (POST /issues)")
    if desired_state == "closed":
        client.put(f"/issues/{iid}", {"state_event": "close"})
    writeback_gitlab_issue(path, iid)
    return "created"


def plan_for(meta: dict) -> str:
    bug_id = str(meta.get("id", "?"))
    if meta.get("gitlab_issue"):
        return f"sync-check {bug_id} (issue #{meta['gitlab_issue']})"
    return f"create {bug_id}"


# --- Пакетные режимы (общие для CLI и тестов) -------------------------------

def _iter_selected(bugs: list[Path], skipped_seeded: list[str] | None = None):
    """Yields (path, meta, body) для отобранных app-багов. На ошибку
    парсинга (BugSyncError) печатает '[ERROR] ...' в stderr и yield'ит
    сентинель (path, None, None) — вызывающая сторона (run_dry_run/run_check/
    run_sync) обязана проверить `meta is None` и засчитать это как отказ
    (exit_code=1/had_error); генератор сам код возврата не хранит и наружу
    ничего не "возвращает" — предыдущая формулировка про "флаг через
    замыкание" была неточной (рекомендация 4 критик-ревью). На AT-BUG-*/
    type: test_debt — молча пропускает (решение оператора 2026-08-01, не
    фильтр качества, поэтому не считается ошибкой). На `seeded: "true"`
    (батч мелочей, разбор 2026-08-09) — тоже пропускает (сеяный артефакт
    репетиции/учений в GitLab не публикуется никогда), но НЕ молча:
    если вызывающая сторона передала список `skipped_seeded`, id пропущенного
    бага туда добавляется — молчаливый пропуск запрещён (--check обязан
    показать их отдельной строкой, не просто "не встретить")."""
    for path in bugs:
        try:
            meta, body = load_bug(path)
        except BugSyncError as e:
            print(f"[ERROR] {e}", file=sys.stderr)
            yield path, None, None
            continue
        if not is_app_bug(meta):
            continue
        if is_seeded(meta):
            if skipped_seeded is not None:
                skipped_seeded.append(str(meta.get("id", path.stem)))
            continue
        yield path, meta, body


def run_dry_run(bugs: list[Path]) -> int:
    exit_code = 0
    skipped_seeded: list[str] = []
    for path, meta, _body in _iter_selected(bugs, skipped_seeded=skipped_seeded):
        if meta is None:
            exit_code = 1
            continue
        print(plan_for(meta))
    if skipped_seeded:
        print(f"skipped (seeded): {len(skipped_seeded)}")
        for bug_id in skipped_seeded:
            print(f"  {bug_id}")
    return exit_code


def run_check(bugs: list[Path]) -> int:
    missing: list[str] = []
    had_error = False
    skipped_seeded: list[str] = []
    for path, meta, _body in _iter_selected(bugs, skipped_seeded=skipped_seeded):
        if meta is None:
            had_error = True
            continue
        if not meta.get("gitlab_issue"):
            missing.append(str(meta.get("id", path.stem)))
    # Сеяные (батч мелочей, разбор 2026-08-09) — ОТДЕЛЬНАЯ строка, ВСЕГДА
    # (даже когда missing/had_error пусты) -- молчаливый пропуск запрещён
    # (это находка-детектор: без строки сеяные неотличимы от "их не было").
    if skipped_seeded:
        print(f"gitlab_sync --check: skipped (seeded): {len(skipped_seeded)}")
        for bug_id in skipped_seeded:
            print(f"  {bug_id}")
    if not missing and not had_error:
        print("gitlab_sync --check: все BUG-* синхронизированы")
        return 0
    if missing:
        print("gitlab_sync --check: не синхронизированы:")
        for bug_id in missing:
            print(f"  {bug_id}")
    return 1 if (missing or had_error) else 0


def run_sync(client: GitLabClient, bugs: list[Path]) -> int:
    exit_code = 0
    skipped_seeded: list[str] = []
    for path, meta, body in _iter_selected(bugs, skipped_seeded=skipped_seeded):
        if meta is None:
            exit_code = 1
            continue
        try:
            result = sync_bug(client, path, meta, body)
            print(f"{meta.get('id', path.stem)}: {result}")
        except BugSyncError as e:
            print(f"[ERROR] {e}", file=sys.stderr)
            exit_code = 1
        except GitLabHTTPError as e:
            print(f"[ERROR] {meta.get('id', path.stem)}: {e}", file=sys.stderr)
            exit_code = 1
    if skipped_seeded:
        print(f"skipped (seeded): {len(skipped_seeded)}")
        for bug_id in skipped_seeded:
            print(f"  {bug_id}")
    return exit_code


# Тот же формат, что id_pattern schemas/bug.schema.yaml (AT- опционален —
# структурно допустим), но --bug дополнительно отвергает AT-BUG-* явно ниже:
# AT-BUG-* формально валиден как id, но никогда не публикуется в GitLab
# (is_app_bug-фильтр молча пропустил бы его, отдав пустой вывод/тихий
# no-op — рекомендация 1 критик-ревью требует явного отказа вместо этого).
BUG_ARG_RE = re.compile(r"^(AT-)?BUG-\d{3,}$")


def validate_bug_arg(value: str) -> None:
    if not BUG_ARG_RE.match(value):
        raise SystemExit(
            f"gitlab_sync: '--bug {value}' не похож на bug-id "
            f"(ожидается формат BUG-NNN, минимум 3 цифры)")
    if not value.startswith("BUG-"):
        raise SystemExit(
            f"gitlab_sync: '--bug {value}' — публикуются только BUG-* "
            f"(AT-BUG-* — тестовый долг фабрики, в GitLab не идёт; "
            f"решение оператора 2026-08-01)")


def reject_seeded_bug_arg(bug_id: str, meta: dict) -> None:
    """Точечный --bug BUG-NNN на seeded-баге -- явный отказ (батч мелочей,
    разбор 2026-08-09): публикация сеяного артефакта репетиции/учений в
    GitLab руками -- та же ошибка, что и его публикация полным sync, только
    менее очевидная (человек мог не знать про признак seeded)."""
    if is_seeded(meta):
        raise SystemExit(
            f"gitlab_sync: '--bug {bug_id}' — сеяный артефакт репетиции/"
            f"учений (frontmatter seeded: \"true\"), в GitLab не публикуется "
            f"даже точечно (см. resolution_comment/раздел «Обсуждение» бага)")


# --- CLI ---------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bug", default=None, metavar="BUG-NNN",
                        help="ограничить sync одним багом")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true",
                      help="офлайн: печатает план (create/sync-check), без сети/токена")
    mode.add_argument("--check", action="store_true",
                      help="офлайн-детектор: список BUG-* без gitlab_issue")
    args = parser.parse_args(argv)

    if args.bug:
        validate_bug_arg(args.bug)

    bugs = discover_bugs(args.bug)
    if args.bug and not bugs:
        print(f"gitlab_sync: '{args.bug}' не найден в bugs/", file=sys.stderr)
        return 1

    if args.bug:
        try:
            bug_meta, _bug_body = load_bug(bugs[0])
        except BugSyncError as e:
            print(f"[ERROR] {e}", file=sys.stderr)
            return 1
        reject_seeded_bug_arg(args.bug, bug_meta)

    if args.check:
        return run_check(bugs)
    if args.dry_run:
        return run_dry_run(bugs)

    token = os.environ.get("GITLAB_TOKEN")
    if not token:
        print(
            "gitlab_sync: переменная окружения GITLAB_TOKEN не задана (нужен "
            "personal access token со scope 'api'); для офлайн-режима "
            "используйте --dry-run или --check",
            file=sys.stderr,
        )
        return 2

    repo_url = read_repo_url()
    base_url = api_base(repo_url)
    client = GitLabClient(base_url, token)
    return run_sync(client, bugs)


if __name__ == "__main__":
    sys.exit(main())
