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
"""
from __future__ import annotations

import argparse
import os
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
                 status: str, *, dry: bool) -> dict:
    """Возвращает {"outcome": "ok"|"cap", "written": int, "skipped_system": int}.

    Может бросить gs.GitLabHTTPError (404/401/сеть) — обрабатывает вызывающая
    сторона (run()), это НЕ ошибка одного бага по построению."""
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
    for path, bug_id, iid, status in selected:
        try:
            result = process_bug(client, path, bug_id, iid, status, dry=dry)
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


# --- Печать / CLI -------------------------------------------------------------

def _summary_line(summary: dict) -> str:
    bugs_str = ", ".join(summary["written_bugs"]) if summary["written_bugs"] else "-"
    return (f"gitlab_inbound: нот перенесено {summary['written_total']} "
            f"({bugs_str}); пропущено system={summary['skipped_system_total']}; "
            f"закрытых с нотами={len(summary['closed_with_notes'])}")


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
        return 0
    print(_summary_line(summary))
    return 0


def _print_check(summary: dict) -> int:
    if summary["degraded"]:
        print(f"gitlab_inbound --check: деградация ({summary['degraded_reason']})")
        return 0
    pending = list(summary["written_bugs"])
    pending += [b for b in summary["cap_bugs"] if b not in pending]
    n = summary["written_total"] + len(summary["cap_bugs"])
    if n > 0:
        # Капнутый баг несёт МИНИМУМ MAX_PAGES*PER_PAGE нот (300 по
        # умолчанию), не 1 — считать его "+1" в N было бы вводящим в
        # заблуждение занижением; уточняющая приписка называет это явно
        # (критик-вход диффа).
        cap_note = (f" (в т.ч. {len(summary['cap_bugs'])} багов в капе — "
                    f"нот больше)") if summary["cap_bugs"] else ""
        print(f"gitlab_inbound --check: необработанных нот {n}{cap_note}: "
              f"{', '.join(pending)}")
        return 1
    if summary["partial_failures"]:
        print("gitlab_inbound --check: частичная деградация: "
              f"{', '.join(summary['partial_failures'])} недоступны")
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
        return _print_check(summary)
    return _print_run(summary)


if __name__ == "__main__":
    sys.exit(main())
