"""gitlab_inbound — обратный канал GitLab: notes issue → ## Обсуждение бага.

План docs (координатор): plan-gitlab-inbound.md v3, критик-на-план PASS
2026-08-09. Второй pre_step-канал того же класса, что board_inbound.py —
но источник ходов человека не борда, а комментарии (notes) GitLab issue,
созданного scripts/gitlab_sync.py (однонаправленный sync В GitLab остаётся
как есть; ЭТОТ файл читает GitLab и НИКОГДА туда не пишет).

Запуск:  python scripts/gitlab_inbound.py [--check]
Выполняется оркестратором на шаге 0 прохода, ПОСЛЕ board_inbound, ДО
build_watch (обе inbound-двери и лёгкая сеть — до 600-секундной сборки;
state/rules.yaml pre_steps).

Выборка: is_app_bug ∧ ¬is_seeded ∧ есть frontmatter gitlab_issue — те же
предикаты, что публикация в gitlab_sync.py, ИМПОРТОМ (discover_bugs,
_iter_selected, load_bug, api_base, GitLabClient, read_repo_url,
GitLabHTTPError) — не копии.

Фильтр нот: пропускается (не переносится) ТОЛЬКО `system: true` (события
GitLab — "changed the description", "closed", метки и т.п.). Фильтра ПО
АВТОРУ нет — токен принадлежит владельцу репозитория, его собственные
ручные комментарии ДОЛЖНЫ доезжать наравне с чужими. Когда/если фабрика
когда-нибудь станет писать СВОИ исходящие ноты в GitLab (сейчас — нет,
см. «Не-цели» плана), дедуп для них будет по СОХРАНЁННОМУ note id, не по
личности автора — граница на будущее, не текущий функционал.

Тело ноты переносится с префиксом блок-цитаты `> ` на КАЖДОЙ строке —
нейтрализует и `^## ` (markdown-заголовок в теле ноты не закрывает секцию
«## Обсуждение» для последующих вставок append_discussion), и `^**[`
(цитата прошлого ответа фабрики внутри ноты не распознаётся дедупом
board_inbound._existing_replicas как фантом-реплика). Рендер первой
строки — `**[gitlab:user @ t]** > текст`: `>` в середине строки литерален
(markdown), блок-цитатой рендерятся строки 2+ — ЗАДУМАНО (дедуп-ключ и
маркер важнее рендера первой строки).

Курсор (state/gitlab-cursor.json, {bug_id: last_note_id}) продвигается
ПОСЛЕ полной обработки страниц одного бага (батч, не по каждой ноте) — к
МАКСИМАЛЬНОМУ id среди ВСЕХ просмотренных нот этого бага в проходе, а не
только записанных: система/пустые ноты тоже двигают курсор дальше системных
шумовых нот (иначе issue с одними системными нотами — эмпирически
подтверждено на реальном issue #1 проекта: 2 ноты, обе system=true —
переобрабатывался бы КАЖДЫЙ проход бесконечно, и со временем накопление
системных нот от sync-правок рисковало бы ложно упереться в кап капитуляции
[R1], хотя реального необработанного контента нет). Крах ПОСЛЕ записи хотя
бы одной реплики, но ДО батч-бампа курсора — следующий проход переобработает
весь батч заново; дубль гасится ВТОРЫМ слоем дедупа
(board_inbound._existing_replicas/_replica_key на самом тексте артефакта) —
семантика at-least-once. Атомарная запись курсора (temp + os.replace).

Пагинация: GET .../notes?sort=desc&order_by=created_at&per_page=<PER_PAGE>
(страницы с НОВЕЙШИХ), ранний выход при note.id <= курсора, собранное
разворачивается (asc) перед записью. MAX_PAGES — предохранитель: страниц
пройдено MAX_PAGES без обнаружения курсора = ГРОМКИЙ ОТКАЗ по ЭТОМУ багу
(process_bug возвращает outcome="cap"): ничего не пишется, курсор НЕ
трогается (скалярный курсор не умеет «не-контигуозный кусок» — частичная
запись с бампом навсегда потеряла бы хвост), эскалация в
state/escalations.md + строка сводки.

Граница по статусу бага: на терминальных статусах (Verified/Rejected/
Intended) реплика ВСЁ РАВНО переносится (история не теряется), но
awaiting НЕ трогается (append_discussion(set_awaiting=False)) — и
персистентный след человеку через _append_escalation (иначе обязанность
испарялась бы с логом прохода: D6 не триггерится без awaiting: qa, sla_sweep
question_unanswered не видит — нет отдельной ветки под "терминальный
статус").

Сеть/офлайн: отказ сети (status 0) или 401 (протух/не тот токен) —
ГЛОБАЛЬНАЯ деградация всего прохода (не только одного бага): [WARN] +
exit 0, курсор не трогается, дальнейшие баги не опрашиваются. Нет
GITLAB_TOKEN вовсе — та же деградация БЕЗ единого сетевого вызова. 404
одного iid — ЛОКАЛЬНЫЙ отказ (issue удалён/переименован проект) — [WARN]
по этому багу, остальные обрабатываются как обычно. Прочие HTTP-коды —
тот же локальный класс, что 404 (частичный отказ по багу, батч жив).

--check: печатает диагностику и код возврата по ЧЕТЫРЕМ исходам (не
только двум, как gitlab_sync --check — этот канал реально стучится в
сеть, если токен есть):
  1) нет токена/сети целиком → "деградация (...)" + exit 0;
  2) чисто (нет неперенесённых нот, ни у одного бага нет отказа) → exit 0;
  3) есть N>0 необработанных нот (обнаружены, но не записаны — --check
     работает как dry-run: process_bug(dry=True) считает, но не пишет) →
     exit 1 + перечисление багов;
  4) валидный токен, но частичный отказ по части багов (404/HTTP) —
     "частичная деградация: BUG-... недоступны" + exit 0; НО если среди
     ДОСТУПНЫХ багов есть N>0 необработанных нот — это старше по
     приоритету (исход 3, exit 1) — недоступность части не маскирует
     реальные необработанные ноты у остальных.

Исходящие ноты в GitLab этот канал НЕ пишет никогда (не-цель плана) —
ответ фабрики уезжает штатным телом issue через gitlab_sync при следующем
sync; статусы issue (close/reopen в GitLab) в артефакты тоже не переносятся
(двусторонний статус-канал — по evidence, вне этого захода).

--- E7: подхват QAready-айтемов разработчиков (ДОПОЛНЕНИЕ E7 v2, критик-вход
принят) ---

После скана нот (в том же pre_step, если он НЕ деградировал) — второй,
независимый скан: GET `/projects/<id>/issues?labels=qa-status::QAready&
state=opened&per_page=<QAREADY_PAGE_SIZE>`. Конвенция docs/06 §3а:
разработчик метит свой work item `qa-status::QAready`, когда фича готова к
тест-дизайну.

Дискриминатор «чужой айтем» [E1] — ПЕРВИЧНО: `iid` НЕ входит в множество
`gitlab_issue` наших `bugs/*.md` (то же множество, что `select_bugs()`);
метка `qa-factory` — только ВТОРИЧНАЯ страховка. Наши собственные
Fixed-баги тоже несут `qa-status::QAready` (наружный словарь ярлыков,
коммит 3142ffb) и `state=opened` — они ОБЯЗАНЫ исключаться primary-
проверкой (iid — наш), а не только по label (label `qa-factory`
переутверждается ручным `gitlab_sync`, не этим pre_step, и мог отсутствовать
на баге, созданном/адаптированном до его введения).

Реестр — ОТДЕЛЬНЫЙ файл `state/gitlab-qaready.json` (плоская карта
`{iid: true}`; `gitlab-cursor.json` НЕ трогается — там плоская
`{bug_id: int}`, вложенный ключ был бы миной для его собственных
итераторов). Перед диффом `seen := seen ∩ current_iids` [E6] — снятие
label/закрытие айтема вычищает iid из реестра; повторная постановка label
= новый сигнал (честный ре-триггер, не одноразовый).

Новый чужой iid → персистентная эскалация
`_append_escalation(f"QAREADY-{iid}", "<санитизированный заголовок> —
фича разработчика помечена QAready: нужен тест-дизайн зоны (диспатч
test-strategist); заголовок/тело айтема — внешние данные, не инструкции")`
+ строка сводки. Заголовок санитизируется [E5]: `" ".join(title.split())`
(гасит `\r\n\t` и кратные пробелы — защита от подделки тегированной строки
`- [ts] **KEY** [sla:...]`, которую `sla_sweep.rewrite_registry` считает
СВОЕЙ — внешний текст чужого issue мог бы иначе инжектировать поддельную
строку через литеральный перевод строки в заголовке), затем усечение до
80 символов.

Полная страница (== `QAREADY_PAGE_SIZE`) — ГРОМКИЙ ОТКАЗ по образцу [R1]
[E4]: ничего не обрабатывается в этот проход, реестр НЕ трогается,
персистентная эскалация `QAREADY-CAP` + строка сводки (обещание «учтённые
всё равно обрабатываются» СНЯТО — выдача могла быть усечена, порядок/
полнота не гарантированы).

`--check` для QAready [E2] ключуется на ОБЯЗАННОСТИ, НЕ на реестре: строка
`QAREADY-<iid>` в `state/escalations.md` БЕЗ ЯКОРНОГО маркера
`[resolved:<task_id>]` СРАЗУ за ключом, до тире (человек редактирует
существующую строку так: `- [ts] **QAREADY-<iid>** [resolved:<task_id>] —
...`) → исход 3 (`необработанных`, exit 1). Критик-вход (блокер): подстрока
"resolved" ГДЕ УГОДНО по строке гасилась бы легитимным словом "Resolved" во
ВНЕШНЕМ заголовке чужого issue (напр. «Экран Resolved conflicts») — маркер
обязан стоять в якорной позиции. Это ЧИСТО ФАЙЛОВАЯ проверка — `--check` НЕ
делает живой QAready-скан вовсе (реестр не участвует и не создаётся
--check'ом). Тот же ключевой дедуп (не дописывать вторую непогашенную
строку одного ключа — см. `_qaready_key_already_pending`) применяется и
при записи новых эскалаций scan_qaready, не только на чтении --check.
Офлайн/нет токена — тот же
общий деградационный путь, что у нот (главный `if not token`/глобальная
деградация нот уже отсекают QAready-скан целиком, «реестр цел»).

Ограничение (докстринг, по evidence первого случая): GitLab Issues API —
только issues; новые типы work items (epic/task премиум-иерархий) вне
охвата.

--- A3(б): verify_build_ref из нот (spec-build-source-dual-mode v4) ---

При переносе КАЖДОЙ ноты (process_bug, тот же батч/курсор, что и сама
реплика — "реестр как у нот", отдельного скана НЕ заводим) тело ноты
сканируется на URL пайплайна/джоба GitLab СВОЕГО repo (host+path сверяются
с `gs.parse_project(gs.read_repo_url())`; URL чужого repo НЕ матчится).
Найден — из него берётся ТОЛЬКО число (iid/id), пишется в frontmatter бага
поле `verify_build_ref: "pipeline:<iid>"|"job:<id>"` (idемпотентно:
байт-безопасный writeback без изменений, если значение уже такое же).
Endpoint для скачивания артефакта этим модулем НЕ строится — это делает
fix-verifier.md (Lead-слой, вне скоупа этого файла) через build_watch's
download-функцию; consumed:/stale: маркеры (C10/E2 спеки) — тоже
исключительно его жизненный цикл, не этого скрипта.

--- M-D: обратный словарь QAready — GitLab label-события -> Fixed ---

Носитель — СОБЫТИЯ (`GET /issues/:iid/resource_label_events`), не текущее
состояние ярлыка (D2): edge-триггер с монотонными id, курсор —
ОТДЕЛЬНЫЙ файл `state/gitlab-label-cursor.json` (плоская `{bug_id:
max_event_id}`; НЕ gitlab-qaready.json — E6-прунинг чистит его по чужим
iid и вычищал бы наши; НЕ gitlab-cursor.json — вложенный ключ там
запрещён докстрингом самого файла).

D5: переиспользуется ОТВЕТ уже выполняемого E7-скана
(`fetch_qaready_issues`) — `scan_qaready` дополнительно возвращает
`our_qaready_iids` (наши iid, присутствующие в выдаче label `qa-status::
QAready`); label-события точечно запрашиваются ТОЛЬКО по нашим багам,
чей ВНУТРЕННИЙ статус Open|Reopened (наш уже-Fixed баг легально несёт
эту метку через STATUS_LABEL_ALIASES — инвариант D5: не второй флип).

Событие `add qa-status::QAready` на нашем issue при внутреннем Open|
Reopened -> Fixed (D2/D3): apply_status(..., "Fixed") + реплика в
Обсуждение с cid/created_at САМОГО события, БЕЗ awaiting (D3 — потребитель
сигнала D1 fix-verifier, не qa; awaiting: qa зажёг бы холостой D6-диспатч).
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

import board_inbound as bi
import gitlab_sync as gs

REPO = gs.REPO
CURSOR_PATH = REPO / "state" / "gitlab-cursor.json"

# Терминальные статусы бага (schemas/bug.schema.yaml enum) — граница [B7]/[R2]:
# реплика ложится в историю, но awaiting не трогается + эскалация человеку.
TERMINAL_STATUSES = {"Verified", "Rejected", "Intended"}

# Предохранители пагинации ([B2]/[R1]). Модульные константы (не локальные
# литералы в fetch_new_notes) — тесты монкипатчат их для маленьких, дешёвых
# фикстур капа/границы (правило 6а CLAUDE.md: тест НА границе и ЗА ней).
PER_PAGE = 100
MAX_PAGES = 3

# --- A3(б): verify_build_ref из нот -----------------------------------------

# Пайплайн/джоб URL СВОЕГО или чужого repo, встреченный в теле ноты:
# https://<host>/<namespace>/<project>/-/pipelines/<iid>
# https://<host>/<namespace>/<project>/-/jobs/<id>
# ИЗ ВНЕШНЕГО ТЕКСТА берётся ТОЛЬКО число (iid/id) — endpoint строится
# отдельно, из api_base(read_repo_url()) (build_watch.py), никогда из этой
# строки целиком (граница инъекции закрыта на уровне извлечения). Критик-
# вход (мелочь 4): [0-9], не \d — \d по умолчанию матчит ЛЮБОЙ Unicode-
# символ категории Nd (не только ASCII 0-9), а тело ноты — внешний
# непроверенный текст.
PIPELINE_JOB_URL_RE = re.compile(
    r'https?://([^/\s]+)/([A-Za-z0-9_.\-/]+?)/-/(pipelines|jobs)/([0-9]+)\b')

_FIELD_LINE_RE_CACHE: dict[str, re.Pattern] = {}


def _field_line_re(field: str) -> "re.Pattern":
    if field not in _FIELD_LINE_RE_CACHE:
        _FIELD_LINE_RE_CACHE[field] = re.compile(
            rf"^{re.escape(field)}[ \t]*:[^\r\n]*", re.MULTILINE)
    return _FIELD_LINE_RE_CACHE[field]


def write_frontmatter_field(path: Path, field: str, value: str) -> bool:
    """Байт-безопасный writeback ОДНОГО поля frontmatter (тот же образец, что
    gs.writeback_gitlab_issue — байтовый ввод/вывод, замена СУЩЕСТВУЮЩЕЙ
    строки поля если есть, иначе вставка перед закрывающим '---'). Локальная
    копия, не импорт: gs.writeback_gitlab_issue заточена под ОДНО конкретное
    поле gitlab_issue. Возвращает True, если значение реально изменилось
    (идемпотентность: байт-в-байт то же значение — не трогаем файл/mtime)."""
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    m = gs.FRONTMATTER_RE.match(text)
    if not m:
        return False
    body_start, body_end = m.start(1), m.end(1)
    body = text[body_start:body_end]
    field_re = _field_line_re(field)
    fm = field_re.search(body)
    new_line = f"{field}: {value}"
    if fm:
        current_line = body[fm.start():fm.end()]
        if current_line.strip() == new_line.strip():
            return False
        abs_start, abs_end = body_start + fm.start(), body_start + fm.end()
        new_text = text[:abs_start] + new_line + text[abs_end:]
    else:
        insert_at = body_end
        eol = "\r\n" if text[insert_at:insert_at + 2] == "\r\n" else "\n"
        new_text = text[:insert_at] + f"{eol}{new_line}" + text[insert_at:]
    path.write_bytes(new_text.encode("utf-8"))
    return True


def _extract_own_build_ref(body: str, own_host: str, own_path: str) -> str | None:
    """A3(б): первый URL пайплайна/джоба ТОЛЬКО СВОЕГО repo (host+path
    сверяются регистронезависимо с read_repo_url()) — URL чужого repo не
    матчится (сравнение, не просто «похоже на GitLab-ссылку»)."""
    for m in PIPELINE_JOB_URL_RE.finditer(body or ""):
        host, path, kind_word, num = m.group(1), m.group(2), m.group(3), m.group(4)
        if host.lower() != own_host.lower():
            continue
        if path.strip("/").lower() != own_path.strip("/").lower():
            continue
        kind = "pipeline" if kind_word == "pipelines" else "job"
        return f"{kind}:{num}"
    return None


# --- M-D: label-события QAready ---------------------------------------------

LABEL_CURSOR_PATH = REPO / "state" / "gitlab-label-cursor.json"
# Модульные константы (не литералы) — тесты монкипатчат для дешёвых
# фикстур капа/границы (правило 6а CLAUDE.md).
LABEL_EVENTS_PER_PAGE = 100
LABEL_EVENTS_MAX_PAGES = 3


def load_label_cursor() -> dict:
    import json
    if not LABEL_CURSOR_PATH.exists():
        return {}
    try:
        return json.loads(LABEL_CURSOR_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_label_cursor_atomic(cursor: dict) -> None:
    import json
    LABEL_CURSOR_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = LABEL_CURSOR_PATH.with_name(LABEL_CURSOR_PATH.name + ".tmp")
    tmp.write_text(json.dumps(cursor, indent=2, ensure_ascii=False, sort_keys=True),
                    encoding="utf-8")
    os.replace(tmp, LABEL_CURSOR_PATH)


def _bump_label_cursor(bug_id: str, event_id: int) -> None:
    cursor = load_label_cursor()
    cursor[bug_id] = event_id
    _write_label_cursor_atomic(cursor)


def fetch_label_events(client: gs.GitLabClient, iid: int,
                       cursor_id: int | None) -> list[dict] | None:
    """GET /issues/:iid/resource_label_events, постранично. None — кап
    LABEL_EVENTS_MAX_PAGES страниц пройден без исчерпания выдачи (громкий
    отказ, тот же паттерн, что fetch_new_notes [R1])."""
    collected: list[dict] = []
    page = 1
    while page <= LABEL_EVENTS_MAX_PAGES:
        _status, events = client.get(f"/issues/{iid}/resource_label_events", params={
            "per_page": LABEL_EVENTS_PER_PAGE, "page": page})
        events = events or []
        if not events:
            break
        for ev in events:
            eid = ev.get("id")
            if cursor_id is not None and eid is not None and eid <= cursor_id:
                continue
            collected.append(ev)
        if len(events) < LABEL_EVENTS_PER_PAGE:
            break
        page += 1
    else:
        return None
    return collected


def process_label_events(path: Path, bug_id: str, status: str, events: list[dict],
                          *, dry: bool) -> dict:
    """D2/D3: событие `add qa-status::QAready` на НАШЕМ issue при внутреннем
    Open|Reopened -> Fixed. Один переход на батч событий достаточен (при
    нескольких `add` в батче — берём первый, дальше уже не Open/Reopened)."""
    applied = False
    for ev in events:
        if applied:
            break
        if ev.get("action") != "add":
            continue
        label_name = (ev.get("label") or {}).get("name")
        if label_name != QAREADY_LABEL:
            continue
        if status not in ("Open", "Reopened"):
            continue   # [инвариант D5] наш Fixed и т.п. — НЕ второй флип
        applied = True
        if not dry:
            bi.apply_status(path, "Fixed", dry=False)
            username = (ev.get("user") or {}).get("username") or "unknown"
            comment = bi.Comment(
                key=bug_id, author=f"gitlab:{username}",
                created=ev.get("created_at", ""),
                body=(f"Метка `{QAREADY_LABEL}` выставлена на GitLab issue — "
                      f"переход Open→Fixed зафиксирован автоматически "
                      f"(второй канал, docs/06 §3а, gitlab-label)."),
                cid=f"label-{ev.get('id')}")
            bi.append_discussion(path, comment, dry=False, set_awaiting=False)
    return {"applied": applied}


def run_gitlab_labels(client: gs.GitLabClient, selected: list[tuple[Path, str, int, str]],
                      our_qaready_iids: set[int] | None, *, dry: bool) -> dict:
    """M-D.1/D5: `our_qaready_iids` — переиспользованный ответ E7-скана (наши
    iid, присутствующие в выдаче label qa-status::QAready); None — QAready-
    скан не выполнялся (капитуляция/деградация) -> outcome "skipped".

    Возвращает {"outcome": "ok"|"skipped"|"degraded", "applied_bugs": [...],
    "cap_bugs": [...], "degraded": bool, "degraded_reason": str} — та же
    сигнатура degraded-полей, что run_qaready (401/сеть на ЛЮБОМ точечном
    запросе -> глобальная деградация ЭТОГО скана, прочие HTTP-коды —
    локальный сбой по одному багу, батч продолжается)."""
    if our_qaready_iids is None:
        return {"outcome": "skipped", "applied_bugs": [], "cap_bugs": [],
                "degraded": False, "degraded_reason": ""}

    by_iid = {iid: (path, bug_id, status) for path, bug_id, iid, status in selected}
    applied_bugs: list[str] = []
    cap_bugs: list[str] = []
    for iid in sorted(our_qaready_iids & by_iid.keys()):
        path, bug_id, status = by_iid[iid]
        if status not in ("Open", "Reopened"):
            continue   # [инвариант D5]
        cursor = load_label_cursor()
        cursor_id = cursor.get(bug_id)
        try:
            events = fetch_label_events(client, iid, cursor_id)
        except gs.GitLabHTTPError as e:
            if e.status in (0, 401):
                return {"outcome": "degraded", "applied_bugs": applied_bugs,
                        "cap_bugs": cap_bugs, "degraded": True, "degraded_reason": str(e)}
            print(f"  [WARN] gitlab_inbound: label-события {bug_id} — HTTP ошибка ({e})")
            continue
        if events is None:
            if not dry:
                bi._append_escalation(
                    bug_id, "label-событий больше LABEL_EVENTS_MAX_PAGES страниц — "
                            "разобрать вручную (scripts/gitlab_inbound.py)")
            cap_bugs.append(bug_id)
            continue
        if not events:
            continue
        result = process_label_events(path, bug_id, status, events, dry=dry)
        if not dry:
            max_id = max((e.get("id") for e in events if e.get("id") is not None), default=None)
            if max_id is not None:
                _bump_label_cursor(bug_id, max_id)
        if result["applied"]:
            applied_bugs.append(bug_id)
    return {"outcome": "ok", "applied_bugs": applied_bugs, "cap_bugs": cap_bugs,
            "degraded": False, "degraded_reason": ""}


# --- E7: QAready-подхват ---------------------------------------------------

QAREADY_LABEL = "qa-status::QAready"
# Модульная константа (не литерал в fetch_qaready_issues) — тесты монкипатчат
# её для дешёвых фикстур границы капа [E4] (правило 6а CLAUDE.md).
QAREADY_PAGE_SIZE = 100
QAREADY_REGISTRY_PATH = REPO / "state" / "gitlab-qaready.json"
# Ключ эскалации из board_inbound._append_escalation: "- [ts] **KEY** — ...".
# Критик-вход (блокер): ЯКОРНАЯ форма закрытия, не подстрока "resolved" по
# ВСЕЙ строке — внешний заголовок чужого issue мог легитимно содержать слово
# "Resolved"/"resolved" (проба критика: "Экран Resolved conflicts для
# повторной синхронизации" гасила бы pending молча, единственный машинный
# детектор E7 отключался внешним текстом). Маркер закрытия обязан стоять
# СРАЗУ за ключом, ДО тире: "**QAREADY-<iid>** [resolved:<task_id>] — ...".
# Один combined-матч (не два независимых re.search) — якорит проверку
# "resolved" именно к ЭТОМУ (первому/леворасположенному, т.е. настоящему —
# внешний текст живёт ПОСЛЕ тире) вхождению ключа, group(2) is None ⇒ строка
# непогашена. Дом-стиль sla_sweep.TAGGED_LINE_RE (`[sla:rule]` в той же
# позиции). group(1) = ключ, group(2) = якорный маркер resolved (или None).
QAREADY_LINE_RE = re.compile(r"\*\*(QAREADY-[^*]+)\*\*(\s*\[resolved:[^\]]*\])?")


# --- Курсор -------------------------------------------------------------

def load_cursor() -> dict:
    """Курсор последней синхронизации. Пусто/нет файла/битый JSON = первый
    проход для ВСЕХ багов (все ноты будут увидены как новые)."""
    import json
    if not CURSOR_PATH.exists():
        return {}
    try:
        return json.loads(CURSOR_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_cursor_atomic(cursor: dict) -> None:
    import json
    CURSOR_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CURSOR_PATH.with_name(CURSOR_PATH.name + ".tmp")
    tmp.write_text(json.dumps(cursor, indent=2, ensure_ascii=False, sort_keys=True),
                    encoding="utf-8")
    os.replace(tmp, CURSOR_PATH)


def _bump_cursor(bug_id: str, note_id: int) -> None:
    """Read-modify-write ЦЕЛОГО файла курсора (не отдельного ключа): запись
    сама по себе атомарна (_write_cursor_atomic — temp + os.replace), но
    read-modify-write КАК ПОСЛЕДОВАТЕЛЬНОСТЬ — нет. Два параллельных прогона
    gitlab_inbound (не должно случаться штатно — конвейер сериализует
    pre_steps одного прохода, см. state/rules.yaml) теоретически могли бы
    гонкой потерять бамп одного из них: следствие — переобработка той же
    ноты следующим проходом и, в худшем случае, дублирующая запись реплики,
    которую гасит второй слой дедупа (board_inbound._existing_replicas/
    _replica_key на самом тексте артефакта), не курсор."""
    cursor = load_cursor()
    cursor[bug_id] = note_id
    _write_cursor_atomic(cursor)


# --- E7: реестр QAready-айтемов --------------------------------------------

def load_qaready_registry() -> dict:
    """{"<iid>": true, ...}. Пусто/нет файла/битый JSON = первый проход
    (все ТЕКУЩИЕ чужие QAready-айтемы будут увидены как новые)."""
    import json
    if not QAREADY_REGISTRY_PATH.exists():
        return {}
    try:
        return json.loads(QAREADY_REGISTRY_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_qaready_registry_atomic(registry: dict) -> None:
    import json
    QAREADY_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = QAREADY_REGISTRY_PATH.with_name(QAREADY_REGISTRY_PATH.name + ".tmp")
    tmp.write_text(json.dumps(registry, indent=2, ensure_ascii=False, sort_keys=True),
                    encoding="utf-8")
    os.replace(tmp, QAREADY_REGISTRY_PATH)


def _sanitize_qaready_title(title: str) -> str:
    """[E5] Схлопывает `\\r\\n\\t` и кратные пробелы в один пробел (гасит
    вектор подделки строки-тега `- [ts] **KEY** [sla:...]` через литеральный
    перевод строки в заголовке ЧУЖОГО issue — заголовок/тело айтема ВНЕШНИЙ
    непроверенный текст, не инструкция), затем усекает до 80 символов."""
    return " ".join((title or "").split())[:80]


# --- Выборка багов --------------------------------------------------------

def select_bugs(bugs: list[Path]) -> list[tuple[Path, str, int, str]]:
    """(path, bug_id, iid, status) для is_app_bug ∧ ¬is_seeded ∧ gitlab_issue
    (переиспользует gs._iter_selected — те же предикаты, что публикация)."""
    out: list[tuple[Path, str, int, str]] = []
    for path, meta, _body in gs._iter_selected(bugs):
        if meta is None:
            continue
        raw_iid = meta.get("gitlab_issue")
        if not raw_iid:
            continue
        try:
            iid = int(raw_iid)
        except (TypeError, ValueError):
            continue
        bug_id = str(meta.get("id", path.stem))
        status = str(meta.get("status", ""))
        out.append((path, bug_id, iid, status))
    return out


# --- Выборка нот одного issue (пагинация, ранний выход по курсору) --------

def fetch_new_notes(client: gs.GitLabClient, iid: int,
                     cursor_id: int | None) -> list[dict] | None:
    """GET .../notes?sort=desc&order_by=created_at, страницы с новейших.

    Ранний выход ПОСЛЕ страницы, где встретилась хотя бы одна нота с
    id <= cursor_id (дальше — только старые страницы). Возвращает НОВЫЕ ноты
    в хронологическом порядке (asc), либо None — кап MAX_PAGES страниц
    пройден без обнаружения курсора (см. модульный докстринг [R1]).

    ВАЖНО (критик-вход диффа, блокер): сортировка API — по created_at, НЕ по
    id. Внутри ОДНОЙ страницы `break` по первой встреченной note.id<=cursor
    обрывал бы страницу ДОСРОЧНО — нота с id>cursor, но более старым/иным
    created_at, стоящая в выдаче ПОСЛЕ ноты-курсора, никогда не была бы
    увидена (батч-bump в process_bug поднимает курсор до максимума среди
    ФАКТИЧЕСКИ собранных нот — пропущенная нота осталась бы позади курсора
    навсегда). Поэтому здесь — ДОЧИТЫВАЕМ страницу целиком (`continue`, не
    `break`, во внутреннем цикле), собирая ВСЕ ноты страницы с id>cursor
    независимо от их позиции относительно ноты-курсора; выход из ПАГИНАЦИИ
    (переход на следующую, более старую страницу не нужен) — уже ПОСЛЕ того,
    как страница дочитана целиком."""
    collected: list[dict] = []
    page = 1
    while page <= MAX_PAGES:
        _status, notes = client.get(f"/issues/{iid}/notes", params={
            "sort": "desc", "order_by": "created_at",
            "per_page": PER_PAGE, "page": page})
        notes = notes or []
        if not notes:
            break
        stopped = False
        for note in notes:
            note_id = note.get("id")
            if cursor_id is not None and note_id is not None and note_id <= cursor_id:
                stopped = True
                continue
            collected.append(note)
        if stopped:
            break
        if len(notes) < PER_PAGE:
            break  # последняя страница выдачи — короче полной
        page += 1
    else:
        # MAX_PAGES страниц пройдено, курсор ни разу не встречен — кап.
        return None
    collected.reverse()
    return collected


# --- Обработка одного бага --------------------------------------------------

def process_bug(client: gs.GitLabClient, path: Path, bug_id: str, iid: int,
                 status: str, *, dry: bool,
                 own_repo: tuple[str, str] | None = None) -> dict:
    """Возвращает {"outcome": "ok"|"cap", "written": int, "skipped_system": int}.

    Может бросить gs.GitLabHTTPError (404/401/сеть) — обрабатывает вызывающая
    сторона (run()), это НЕ ошибка одного бага по построению.

    `own_repo` — (host, path) СВОЕГО repo (A3(б)): каждая обрабатываемая нота
    (тот же батч, что и сама реплика — "реестр как у нот") сканируется на
    URL пайплайна/джоба СВОЕГО repo; найден -> verify_build_ref писется в
    frontmatter бага idемпотентно. None — сканирование ref пропускается
    (напр. read_repo_url() недоступен)."""
    cursor = load_cursor()
    cursor_id = cursor.get(bug_id)
    notes = fetch_new_notes(client, iid, cursor_id)

    if notes is None:
        if not dry:
            bi._append_escalation(
                bug_id,
                ">N новых нот за проход, канал не гарантирует порядок — "
                "разобрать вручную: проставить курсор вручную в "
                "state/gitlab-cursor.json либо временно поднять MAX_PAGES "
                "(scripts/gitlab_inbound.py)")
        return {"outcome": "cap", "written": 0, "skipped_system": 0}

    written = 0
    skipped_system = 0
    if notes:
        text = path.read_bytes().decode("utf-8")
        existing = bi._existing_replicas(text)
        set_awaiting = status not in TERMINAL_STATUSES

        for note in notes:
            if note.get("system"):
                skipped_system += 1
                continue
            raw_body = note.get("body") or ""
            if not raw_body.strip():
                print(f"  [WARN] gitlab_inbound: {bug_id} нота "
                      f"{note.get('id')} — пустое/пробельное тело, пропуск")
                continue
            author = (note.get("author") or {}).get("username") or "unknown"
            created = note.get("created_at", "")
            quoted = "\n".join(f"> {ln}" for ln in raw_body.splitlines())
            comment = bi.Comment(key=bug_id, author=f"gitlab:{author}",
                                  created=created, body=quoted,
                                  cid=str(note.get("id")))
            key = bi._replica_key(comment)
            if key in existing:
                # Второй слой дедупа (курсор сброшен/рассинхронен, реплика уже
                # в файле) — не дублируем.
                continue
            line = bi.append_discussion(path, comment, dry=dry,
                                         set_awaiting=set_awaiting)
            if not dry:
                # dry (--check) считает ноту "необработанной" (§11), но ничего
                # не переносит — строка "[COMMENT] перенесена реплика" в этом
                # режиме была бы враньём (чек 3в читает вывод).
                print(line)
            existing.add(key)
            written += 1

            # A3(б): verify_build_ref из ЭТОЙ же ноты — тот же батч/курсор,
            # что реплика (не отдельный скан). --check (dry) не пишет.
            if own_repo is not None and not dry:
                ref = _extract_own_build_ref(raw_body, own_repo[0], own_repo[1])
                if ref:
                    changed = write_frontmatter_field(path, "verify_build_ref", ref)
                    if changed:
                        print(f"  [INFO] gitlab_inbound: {bug_id} verify_build_ref <- "
                              f"{ref} (нота {note.get('id')})")

        if not dry:
            max_id = max((n.get("id") for n in notes if n.get("id") is not None),
                         default=None)
            if max_id is not None:
                _bump_cursor(bug_id, max_id)
            if written and status in TERMINAL_STATUSES:
                bi._append_escalation(
                    bug_id,
                    f"нота в GitLab на закрытом баге ({status}) — "
                    f"реанимировать или ответить вне фабрики")

    return {"outcome": "ok", "written": written, "skipped_system": skipped_system}


# --- Оркестрация прохода -----------------------------------------------------

def _own_repo_host_path() -> tuple[str, str] | None:
    """A3(б): (host, path) СВОЕГО repo — best-effort, None при недоступности
    (read_repo_url()/parse_project() не должны валить весь pre_step ради
    вспомогательного extraction'а)."""
    try:
        return gs.parse_project(gs.read_repo_url())
    except (SystemExit, Exception):
        return None


def run(client: gs.GitLabClient, selected: list[tuple[Path, str, int, str]],
        *, dry: bool) -> dict:
    """Обрабатывает список отобранных багов. Глобальная деградация (сеть/401)
    прерывает обработку немедленно — прочие HTTP-коды (в т.ч. 404) считаются
    ЛОКАЛЬНЫМ отказом по одному багу, батч продолжается."""
    summary = {
        "degraded": False, "degraded_reason": "",
        "written_bugs": [], "written_total": 0,
        "skipped_system_total": 0, "closed_with_notes": [],
        "partial_failures": [], "cap_bugs": [],
    }
    own_repo = _own_repo_host_path()
    for path, bug_id, iid, status in selected:
        try:
            result = process_bug(client, path, bug_id, iid, status, dry=dry,
                                 own_repo=own_repo)
        except gs.GitLabHTTPError as e:
            if e.status in (0, 401):
                summary["degraded"] = True
                summary["degraded_reason"] = str(e)
                return summary
            if e.status == 404:
                print(f"  [WARN] gitlab_inbound: {bug_id} issue #{iid} не "
                      f"найден (404) — пропуск")
            else:
                print(f"  [WARN] gitlab_inbound: {bug_id} issue #{iid} — "
                      f"HTTP ошибка ({e})")
            summary["partial_failures"].append(bug_id)
            continue

        if result["outcome"] == "cap":
            summary["cap_bugs"].append(bug_id)
            continue

        summary["skipped_system_total"] += result["skipped_system"]
        if result["written"]:
            summary["written_bugs"].append(bug_id)
            summary["written_total"] += result["written"]
            if status in TERMINAL_STATUSES:
                summary["closed_with_notes"].append(bug_id)
    return summary


# --- E7: скан QAready-айтемов -----------------------------------------------

def fetch_qaready_issues(client: gs.GitLabClient) -> list[dict] | None:
    """GET .../issues?labels=qa-status::QAready&state=opened. Одна страница.

    Возвращает None — выдача заполнила страницу целиком (== QAREADY_PAGE_SIZE,
    реальный total мог быть больше) — [E4] громкий отказ, не частичная
    обработка (порядок/полнота НЕ гарантированы усечённой выдачей)."""
    _status, issues = client.get("/issues", params={
        "labels": QAREADY_LABEL, "state": "opened", "per_page": QAREADY_PAGE_SIZE})
    issues = issues or []
    if len(issues) >= QAREADY_PAGE_SIZE:
        return None
    return issues


def _is_foreign_qaready(issue: dict, our_iids: set[int]) -> bool:
    """[E1] ПЕРВИЧНО: iid наш (входит в our_iids — множество gitlab_issue
    наших bugs/*.md) → не чужой. ВТОРИЧНО (страховка): метка qa-factory."""
    iid = issue.get("iid")
    labels = set(issue.get("labels") or [])
    is_ours = (iid in our_iids) or ("qa-factory" in labels)
    return not is_ours


def _qaready_key_already_pending(key: str) -> bool:
    """Критик-вход (мелочь 3): НЕ дописывать вторую непогашенную строку с
    ТЕМ ЖЕ ключом (QAREADY-<iid> ИЛИ QAREADY-CAP) — иначе, напр., капитуляция
    [E4], длящаяся несколько проходов подряд, копила бы по строке эскалации
    КАЖДЫЙ проход. Та же якорная детекция резолва, что _qaready_pending_keys
    (`[resolved:...]` СРАЗУ за ключом, до тире), но для ОДНОГО конкретного
    ключа — не читает/не пишет реестр (сигнал живёт в самой escalations.md,
    как и --check [E2])."""
    path = bi.ESCALATIONS_PATH
    if not path.exists():
        return False
    pat = re.compile(r"\*\*" + re.escape(key) + r"\*\*(\s*\[resolved:[^\]]*\])?")
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if key not in line:
            continue
        m = pat.search(line)
        if m and not m.group(1):
            return True
    return False


def scan_qaready(client: gs.GitLabClient, our_iids: set[int], *, dry: bool = False) -> dict:
    """Возвращает {"outcome": "ok"|"cap", "new_keys": [...], "n_new": int,
    "our_qaready_iids": set[int]|None}.

    D5: `our_qaready_iids` — переиспользование ОТВЕТА этого же скана для
    M-D (run_gitlab_labels) — НАШИ iid (из our_iids), присутствующие в
    ТЕКУЩЕЙ выдаче label qa-status::QAready; None ТОЛЬКО при outcome "cap"
    (выдача не может считаться полной/достоверной).

    Может бросить gs.GitLabHTTPError (401/сеть/прочее) — обрабатывает
    вызывающая сторона (run_qaready), не эта функция."""
    issues = fetch_qaready_issues(client)

    if issues is None:
        if not dry and not _qaready_key_already_pending("QAREADY-CAP"):
            bi._append_escalation(
                "QAREADY-CAP",
                "QAready-выдача переполнена — разобрать вручную")
        return {"outcome": "cap", "new_keys": [], "n_new": 0, "our_qaready_iids": None}

    all_iids = {int(issue["iid"]) for issue in issues if issue.get("iid") is not None}
    foreign = {
        iid: issue for iid, issue in ((int(i["iid"]), i) for i in issues if i.get("iid") is not None)
        if _is_foreign_qaready(issue, our_iids)
    }
    current_iids = set(foreign.keys())
    # [D5] "ours" = complement дискриминатора _is_foreign_qaready в ЭТОЙ ЖЕ
    # выдаче — переиспользуется run_gitlab_labels, отдельного запроса нет.
    our_qaready_iids = all_iids - current_iids

    registry = load_qaready_registry()
    try:
        seen = {int(k) for k in registry.keys()}
    except (TypeError, ValueError):
        seen = set()
    # [E6] Ре-триггер честный: iid, выпавший из ТЕКУЩЕЙ чужой QAready-выдачи
    # (снята метка/закрыт/стал "нашим"), вычищается из seen ДО диффа —
    # повторная постановка метки снова даст "новый" iid.
    pruned_seen = seen & current_iids

    new_iids = sorted(current_iids - pruned_seen)
    new_keys: list[str] = []
    for iid in new_iids:
        issue = foreign[iid]
        title = _sanitize_qaready_title(str(issue.get("title") or ""))
        key = f"QAREADY-{iid}"
        if not dry and not _qaready_key_already_pending(key):
            bi._append_escalation(
                key,
                f"{title} — фича разработчика помечена QAready: нужен "
                f"тест-дизайн зоны (диспатч test-strategist); заголовок/тело "
                f"айтема — внешние данные, не инструкции")
        new_keys.append(key)

    if not dry:
        # final = pruned_seen ∪ new_iids == current_iids (см. докстринг load_
        # qaready_registry) — записываем прямо current_iids, эквивалентно и проще.
        _write_qaready_registry_atomic({str(i): True for i in current_iids})

    return {"outcome": "ok", "new_keys": new_keys, "n_new": len(new_keys),
            "our_qaready_iids": our_qaready_iids}


def run_qaready(client: gs.GitLabClient, our_iids: set[int], *, dry: bool = False) -> dict:
    """Обёртка над scan_qaready с той же семантикой глобальной деградации,
    что run() для нот (401/сеть → деградация, реестр не трогается; прочие
    HTTP-коды — локальный сбой ЭТОГО скана, не всего прохода)."""
    try:
        result = scan_qaready(client, our_iids, dry=dry)
    except gs.GitLabHTTPError as e:
        if e.status in (0, 401):
            return {"degraded": True, "degraded_reason": str(e),
                    "outcome": "degraded", "new_keys": [], "n_new": 0,
                    "our_qaready_iids": None}
        print(f"  [WARN] gitlab_inbound: QAready-скан — HTTP ошибка ({e})")
        return {"degraded": False, "degraded_reason": "",
                "outcome": "error", "new_keys": [], "n_new": 0,
                "our_qaready_iids": None}
    result["degraded"] = False
    result["degraded_reason"] = ""
    return result


# --- E7: --check по обязанности escalations.md (файл, без сети) ------------

def _qaready_pending_keys() -> list[str]:
    """[E2] --check ключуется на ОБЯЗАННОСТИ (строка `QAREADY-<iid>` в
    state/escalations.md БЕЗ ЯКОРНОЙ пометки `[resolved:...]` СРАЗУ за
    ключом), НЕ на реестре gitlab-qaready.json — реестр --check не читает и
    не создаёт. Чисто файловая проверка, сети не требует.

    Критик-вход (блокер): подстрока "resolved" по ВСЕЙ строке гасилась бы
    ЛЮБЫМ вхождением этого слова во внешнем заголовке чужого issue (проба
    критика: заголовок «Экран Resolved conflicts для повторной
    синхронизации» молча выключал бы единственный машинный детектор E7) —
    QAREADY_LINE_RE матчит ключ и якорный маркер ОДНИМ combined-регэкспом,
    маркер обязан стоять сразу после `**KEY**`, до тире; внешний заголовок
    живёт ПОСЛЕ тире и попасть в эту позицию не может."""
    path = bi.ESCALATIONS_PATH
    if not path.exists():
        return []
    pending: list[str] = []
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "QAREADY-" not in line:
            continue
        m = QAREADY_LINE_RE.search(line)
        if not m:
            continue
        key = m.group(1)
        if m.group(2):   # якорный '[resolved:...]' сразу за ключом — погашена
            continue
        if key not in seen:
            seen.add(key)
            pending.append(key)
    return pending


# --- Печать / CLI -------------------------------------------------------------

def _summary_line(summary: dict) -> str:
    bugs_str = ", ".join(summary["written_bugs"]) if summary["written_bugs"] else "-"
    return (f"gitlab_inbound: нот перенесено {summary['written_total']} "
            f"({bugs_str}); пропущено system={summary['skipped_system_total']}; "
            f"закрытых с нотами={len(summary['closed_with_notes'])}")


def _qaready_summary_line(qr: dict) -> str:
    if qr["outcome"] == "cap":
        return "gitlab_inbound: QAready: капитуляция (переполнение) — см. эскалацию QAREADY-CAP"
    if qr["outcome"] == "error":
        return "gitlab_inbound: QAready: скан не удался (см. WARN выше)"
    n = qr.get("n_new", 0)
    detail = f" ({', '.join(qr['new_keys'])})" if qr.get("new_keys") else ""
    return f"gitlab_inbound: QAready: {n} новых{detail}"


def _labels_summary_line(lr: dict | None) -> str:
    if lr is None:
        return "gitlab_inbound: label-события: не сканировались"
    if lr["outcome"] == "skipped":
        return "gitlab_inbound: label-события: пропущено (QAready-скан капнул/деградировал)"
    if lr["outcome"] == "degraded":
        return f"gitlab_inbound: label-события: деградация ({lr['degraded_reason']})"
    applied = lr.get("applied_bugs") or []
    cap = lr.get("cap_bugs") or []
    detail = f" ({', '.join(applied)})" if applied else ""
    cap_detail = f"; в капе: {', '.join(cap)}" if cap else ""
    return f"gitlab_inbound: label-события: {len(applied)} применено{detail}{cap_detail}"


def _print_run(summary: dict) -> int:
    if summary["degraded"]:
        # Деградация МОГЛА наступить ПОСЛЕ того, как часть багов уже
        # обработана успешно (первый HTTP-вызов, упёршийся в 401/офлайн, не
        # обязан быть самым первым в списке) — критик-вход: исход pre_step
        # целиком печатается, не только [WARN], иначе уже сделанная работа
        # проходит мимо оператора молча.
        if summary["written_total"] or summary["skipped_system_total"]:
            print(_summary_line(summary))
        print(f"[WARN] gitlab_inbound: деградация ({summary['degraded_reason']})")
        # Критик-вход (мелочь 2): деградация НОТ пропускает QAready-скан
        # целиком (main() — `if not summary["degraded"]`) — summary["qaready"]
        # остаётся None. Молчание про QAready в этом случае неотличимо от
        # «отсканировали, новых нет» — печатаем явную строку статуса.
        if summary.get("qaready") is None:
            print("gitlab_inbound: QAready: не сканировался (деградация канала)")
        if summary.get("labels") is None:
            print(_labels_summary_line(None))
        return 0
    print(_summary_line(summary))
    qr = summary.get("qaready")
    if qr is not None:
        print(_qaready_summary_line(qr))
    print(_labels_summary_line(summary.get("labels")))
    return 0


def _print_check(summary: dict, label_check: dict | None = None) -> int:
    if summary["degraded"]:
        print(f"gitlab_inbound --check: деградация ({summary['degraded_reason']})")
        # Критик-вход (мелочь 5): не молчать про label-канал — деградация
        # нотного скана означает, что main() даже НЕ ПЫТАЛСЯ сделать
        # точечный QAready/label-скан (см. main(): `if not summary["degraded"]`)
        # — молчание неотличимо от «проверили, чисто».
        print("gitlab_inbound --check: label-inbound: не проверялся (деградация нотного скана)")
        return 0

    # [E2] QAready --check — чисто файловая проверка escalations.md, сети не
    # требует и живой скан/реестр не трогает.
    qaready_pending = _qaready_pending_keys()

    pending = list(summary["written_bugs"])
    pending += [b for b in summary["cap_bugs"] if b not in pending]
    n = summary["written_total"] + len(summary["cap_bugs"])

    # [D6] label-inbound — СЕТЕВОЙ чек (в отличие от файловой QAready-части
    # E2 выше): сверка наших Open|Reopened против label-событий.
    label_pending: list[str] = []
    label_degraded_line: str | None = None
    if label_check is not None:
        if label_check.get("degraded"):
            label_degraded_line = f"label-inbound: деградация ({label_check['degraded_reason']})"
        else:
            label_pending = list(label_check.get("applied_bugs") or [])
            label_pending += [b for b in (label_check.get("cap_bugs") or [])
                              if b not in label_pending]

    if n > 0 or qaready_pending or label_pending:
        parts = []
        if n > 0:
            # Капнутый баг несёт МИНИМУМ MAX_PAGES*PER_PAGE нот (300 по
            # умолчанию), не 1 — считать его "+1" в N было бы вводящим в
            # заблуждение занижением; уточняющая приписка называет это явно
            # (критик-вход диффа).
            cap_note = (f" (в т.ч. {len(summary['cap_bugs'])} багов в капе — "
                        f"нот больше)") if summary["cap_bugs"] else ""
            parts.append(f"необработанных нот {n}{cap_note}: {', '.join(pending)}")
        if qaready_pending:
            parts.append(f"QAready необработанных {len(qaready_pending)}: "
                         f"{', '.join(qaready_pending)}")
        if label_pending:
            parts.append(f"label-inbound несведённых {len(label_pending)}: "
                         f"{', '.join(label_pending)}")
        print(f"gitlab_inbound --check: {'; '.join(parts)}")
        return 1
    if summary["partial_failures"]:
        print("gitlab_inbound --check: частичная деградация: "
              f"{', '.join(summary['partial_failures'])} недоступны")
        return 0
    if label_degraded_line:
        print(f"gitlab_inbound --check: чисто; {label_degraded_line}")
        return 0
    print("gitlab_inbound --check: чисто")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="детектор необработанных нот (использует сеть, "
                             "если токен есть; ничего не пишет)")
    args = parser.parse_args(argv)

    token = os.environ.get("GITLAB_TOKEN")
    if not token:
        if args.check:
            print("gitlab_inbound --check: деградация (нет GITLAB_TOKEN)")
            # [D6] label-inbound — деградация видима отдельной строкой, не
            # молчаливый 0 (та же дисциплина, что F-30 CLAUDE.md).
            print("gitlab_inbound --check: label-inbound: не проверялся (нет токена)")
        else:
            print("[WARN] gitlab_inbound: деградация (нет GITLAB_TOKEN)")
        return 0

    repo_url = gs.read_repo_url()
    base_url = gs.api_base(repo_url)
    client = gs.GitLabClient(base_url, token)

    bugs = gs.discover_bugs()
    selected = select_bugs(bugs)

    summary = run(client, selected, dry=args.check)

    if args.check:
        # [E2] QAready-обязанность --check не делает живой скан (файловая
        # проверка escalations.md) — НО [D6] label-inbound ОБЯЗАН быть
        # сетевым: точечный скан (dry=True — ничего не пишет) только для
        # получения our_qaready_iids/label-событий.
        label_check = None
        if not summary["degraded"]:
            our_iids = {iid for _p, _b, iid, _s in selected}
            qr_check = run_qaready(client, our_iids, dry=True)
            if qr_check["degraded"]:
                label_check = {"outcome": "degraded", "applied_bugs": [], "cap_bugs": [],
                              "degraded": True, "degraded_reason": qr_check["degraded_reason"]}
            else:
                label_check = run_gitlab_labels(
                    client, selected, qr_check.get("our_qaready_iids"), dry=True)
        return _print_check(summary, label_check)

    # E7 QAready-скан — второй, ПОСЛЕ нот, ТОЛЬКО если ноты не деградировали
    # (общая деградация канала — реестр QAready тоже остаётся нетронутым).
    if not summary["degraded"]:
        our_iids = {iid for _p, _b, iid, _s in selected}
        qr = run_qaready(client, our_iids, dry=False)
        summary["qaready"] = qr
        if qr["degraded"]:
            summary["degraded"] = True
            summary["degraded_reason"] = qr["degraded_reason"]
            summary["labels"] = None
        else:
            # M-D/D5: label-события — ПОСЛЕ QAready, переиспользует его ответ.
            lr = run_gitlab_labels(client, selected, qr.get("our_qaready_iids"), dry=False)
            summary["labels"] = lr
            if lr.get("degraded"):
                summary["degraded"] = True
                summary["degraded_reason"] = lr["degraded_reason"]
    else:
        summary["qaready"] = None
        summary["labels"] = None

    return _print_run(summary)


if __name__ == "__main__":
    sys.exit(main())
