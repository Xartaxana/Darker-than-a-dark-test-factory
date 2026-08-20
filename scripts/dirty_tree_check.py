"""dirty_tree_check — pre_step 0: детектор грязного рабочего дерева на старте
прохода (класс: kill между работой и коммитом теряет деливераблы — leftover-
дифф должен быть ВИДИМ до диспатчей, план 2026-08-20, критик D1).

Источник: `git status --porcelain -z`, НЕ голый `--porcelain` (не-ASCII пути
без -z приходят октальными эскейпами вида "\\320\\272...") и НЕ `--ignored`
(игнорируемые пути не наш интерес — porcelain и так их не печатает). Формат
-z эмпирически проверен (scratchpad этого прохода, git-bash на Windows):
записи разделены NUL, путь начинается с 4-го байта записи (XY + один
разделяющий пробел), rename/copy (X или Y == 'R'/'C') несёт ВТОРОЕ NUL-поле —
оригинальный путь. Без -z путь с пробелом/кириллицей ломает наивный построчный
парсинг; с -z экранирования нет вовсе (core.quotepath не влияет).

Пути с префиксом "scratchpad/" исключаются — housekeeping-норма CLAUDE.md
(разовые файлы туда и не в коммит); всё остальное — кандидат в leftover.

Для каждого оставшегося пути: mtime (удалённый путь — метка "deleted", mtime
недоступен физически). Разбивка на "недавно изменено" (< LIVE_WRITER_
THRESHOLD_MINUTES минут — вероятно живой параллельный писатель, легальный
исход) и "старше" (вероятный leftover убитого прохода) — правило 4 CLAUDE.md
("Сверка пересечения — не только по путям"): работа другой живой сессии не
трогаем, только предупреждаем.

Непустой (после фильтра scratchpad/) срез -> [WARN]-блок в stdout + строка в
state/orchestrator-log.md через КАНОНИЧЕСКИЙ механизм (log_append.
append_orchestrator — импортирован, не продублирован: тот же формат таблицы,
что stale_locks/sla_sweep/board_inbound и остальные pre_steps).

Код выхода ВСЕГДА 0 — это информатор, не гейт: отказ git (бинарник не найден/
cwd не git-репо/любая иная ошибка вызова) деградирует в [WARN]-строку, не
роняет проход (правило 5 спеки, симметрично _verify_environment в
log_append.py).

Критик-раунд 1 (2026-08-20), закрытые блокеры: B1 (порядок секций
older/deleted ПЕРЕД recent -- приоритет общего бюджета TRUNCATE_AFTER не
даёт recent-срезу вытеснить leftover из отчёта, см. _format_warn); F1
(сбой записи в orchestrator-log -- видимая строка отчёта, не тихий
проглот, см. _log_to_orchestrator/build_report); F2 (адрес журнала
завязан на проверяемый --repo, не на module-level log_append.ORCH_LOG);
F3 (rename-записи показывают "old -> new", не только новый путь).

Запуск: python scripts/dirty_tree_check.py [--repo <path>]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

import log_append  # канонический писатель state/orchestrator-log.md — переиспользуем, не дублируем формат

REPO = Path(__file__).resolve().parents[1]

SCRATCHPAD_PREFIX = "scratchpad/"

# Лимиты введённые ЭТИМ детектором (правило 6а CLAUDE.md: граничный тест на
# каждом из них обязателен — см. scripts/tests/test_dirty_tree_check.py).
LIVE_WRITER_THRESHOLD_MINUTES = 10.0   # < порога -> "recent" (вероятно живая сессия)
TRUNCATE_AFTER = 30                    # печатаем не больше стольких путей, дальше "и ещё N"


# --------------------------------------------------------------------------
# Парсинг git status --porcelain -z
# --------------------------------------------------------------------------

def parse_porcelain_z(text: str) -> list[tuple[str, str, str, str | None]]:
    """Разбирает уже декодированный вывод `git status --porcelain -z`.

    Возвращает список (x, y, path, orig_path|None) — orig_path заполнен
    только для rename/copy записей (x или y в {'R', 'C'}).

    Устойчив к мусору в потоке (адверсариальный DoD-пункт «пустое имя-мусор
    в -z потоке»): токен короче 3 символов (нет полноценного заголовка
    "XY ") или с пустым путём — пропускается без падения; если запись
    rename/copy не находит НЕПУСТОГО следующего токена под orig_path (поток
    оборван или там сам мусор), orig_path остаётся None, курсор НЕ
    поглощает этот токен — он будет рассмотрен и отброшен на следующей
    итерации как самостоятельный (короткий/пустой) токен."""
    tokens = text.split("\0")
    entries: list[tuple[str, str, str, str | None]] = []
    i = 0
    n = len(tokens)
    while i < n:
        token = tokens[i]
        i += 1
        if len(token) < 3:
            continue  # мусор/пустой токен (в т.ч. хвостовой пустой после финального \0)
        x, y = token[0], token[1]
        path = token[3:]
        if not path:
            continue  # заголовок есть, путь пуст — мусор
        orig_path: str | None = None
        if x in ("R", "C") or y in ("R", "C"):
            if i < n and tokens[i] != "":
                orig_path = tokens[i]
                i += 1
        entries.append((x, y, path, orig_path))
    return entries


def collect_dirty_entries(cwd: Path) -> list[tuple[str, str, str, str | None]] | None:
    """Реальный вызов git. None — деградация (git не найден/cwd не
    существует/не git-репозиторий/любая иная ошибка вызова) — вызывающий
    печатает [WARN]-строку деградации и НЕ роняет процесс (правило 5)."""
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain", "-z"],
            cwd=str(cwd), capture_output=True,
        )
    except (FileNotFoundError, OSError):
        return None
    if proc.returncode != 0:
        return None
    text = proc.stdout.decode("utf-8", errors="replace")
    return parse_porcelain_z(text)


# --------------------------------------------------------------------------
# Классификация: mtime / deleted / recent / older
# --------------------------------------------------------------------------

def classify(entries: list[tuple[str, str, str, str | None]], cwd: Path,
             now: datetime) -> list[dict]:
    """entries -> список записей с категорией: 'deleted' (путь не существует
    на диске или mtime физически недоступен), 'recent' (mtime моложе
    LIVE_WRITER_THRESHOLD_MINUTES минут — вероятно живой параллельный
    писатель), 'older' (вероятный leftover). Схлопнутая untracked-директория
    ("sub/") берёт mtime самой директории — тот же Path.stat(), обычная
    операция ФС."""
    result: list[dict] = []
    for x, y, path, orig_path in entries:
        full = cwd / path
        status = f"{x}{y}"
        base = {"path": path, "orig_path": orig_path, "status": status}
        if not full.exists():
            result.append({**base, "category": "deleted", "mtime": None, "age_min": None})
            continue
        try:
            mtime_ts = full.stat().st_mtime
        except OSError:
            result.append({**base, "category": "deleted", "mtime": None, "age_min": None})
            continue
        mtime_dt = datetime.fromtimestamp(mtime_ts, tz=timezone.utc)
        age_min = (now - mtime_dt).total_seconds() / 60.0
        category = "recent" if age_min < LIVE_WRITER_THRESHOLD_MINUTES else "older"
        result.append({**base, "category": category, "mtime": mtime_dt, "age_min": age_min})
    return result


def _filter_scratchpad(entries: list[tuple[str, str, str, str | None]]
                       ) -> list[tuple[str, str, str, str | None]]:
    return [e for e in entries if not e[2].startswith(SCRATCHPAD_PREFIX)]


# --------------------------------------------------------------------------
# Форматирование WARN-блока
# --------------------------------------------------------------------------

def _fmt_entry(e: dict) -> str:
    # F3 (критик-фикс): rename/copy показывает orig_path -- "R old -> new",
    # не только новый путь (без этого переименование выглядит как обычный
    # untracked/modified путь, теряя связь со старым именем).
    label = f"{e['orig_path']} -> {e['path']}" if e.get("orig_path") else e["path"]
    if e["category"] == "deleted":
        return f"  [{e['status']}] {label} — deleted (mtime недоступен)"
    ts_label = e["mtime"].strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"  [{e['status']}] {label} — mtime {ts_label} ({e['age_min']:.1f} мин назад)"


def _format_warn(classified: list[dict]) -> str:
    total = len(classified)
    recent = [e for e in classified if e["category"] == "recent"]
    older = [e for e in classified if e["category"] == "older"]
    deleted = [e for e in classified if e["category"] == "deleted"]

    lines = [
        f"[WARN] dirty_tree_check: {total} путей в рабочем дереве вне "
        "scratchpad/ — грязное дерево на старте прохода"
    ]
    printed = 0

    def emit_section(title: str, items: list[dict]) -> None:
        nonlocal printed
        if not items or printed >= TRUNCATE_AFTER:
            return
        lines.append("")
        lines.append(title)
        for e in items:
            if printed >= TRUNCATE_AFTER:
                return
            lines.append(_fmt_entry(e))
            printed += 1

    # B1 (критик-фикс): older/deleted -- ИМЕННО leftover-кандидаты, ради
    # которых существует детектор -- печатаются ПЕРВЫМИ и получают
    # приоритет общего бюджета TRUNCATE_AFTER; recent (вероятно легальная
    # живая сессия, второстепенный сигнал) печатается ПОСЛЕДНИМ и забирает
    # только остаток бюджета. Раньше recent шёл первым и мог единолично
    # выесть весь бюджет -- older полностью пропадал из отчёта при большом
    # recent-срезе (критик D1, живой прецедент этого прохода).
    emit_section("Старше (вероятный leftover убитого прохода):", older)
    emit_section("Удалено (mtime недоступен):", deleted)
    emit_section(
        f"Изменено < {LIVE_WRITER_THRESHOLD_MINUTES:.0f} мин назад "
        "(вероятно, живой параллельный писатель — легальный исход «чужая "
        "живая сессия»):", recent)

    if printed < total:
        lines.append("")
        lines.append(f"... и ещё {total - printed}")

    lines.append("")
    lines.append(
        "leftover разобрать ДО диспатчей: по-путёвый осмотр диффа "
        "(git diff --stat -- <путь>), затем принять/откатить/оставить с "
        "причиной; НЕ заметать в коммит молча."
    )
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Orchestrator-log — переиспользуем log_append.append_orchestrator
# --------------------------------------------------------------------------

def _log_to_orchestrator(classified: list[dict], repo: Path) -> tuple[bool, str]:
    """Пишет ОДНУ строку через канонический механизм (log_append.
    append_orchestrator — импортирован, формат не продублирован).

    F2 (критик-фикс): адрес журнала завязан на ПРОВЕРЯЕМЫЙ `repo`, а не на
    module-level log_append.ORCH_LOG (= <репо самого log_append.py>/state/
    orchestrator-log.md — константа, вычисленная от РАСПОЛОЖЕНИЯ файла
    log_append.py, а не от --repo этого вызова). Без привязки к `repo`
    строка ВСЕГДА уходила бы в РЕАЛЬНЫЙ репозиторий даже когда --repo
    указывает на другое дерево (тестовый tmp-репо, второй деплой) — тихая
    запись не туда. Решение: временно подменяем log_append.ORCH_LOG на
    <repo>/state/orchestrator-log.md ТОЛЬКО на время этого вызова и
    восстанавливаем в finally (даже при исключении) — модуль-синглтон
    log_append не остаётся в чужом состоянии для следующего вызова
    процесса (напр. другой pre_step, импортирующий тот же модуль).

    F1 (критик-фикс): возвращает (ok, message) вместо тихого проглатывания
    сбоя. Любой сбой (вне git-репо/state отсутствует/иное) НЕ роняет
    детектор (правило 5: код выхода всегда 0), но message уходит в
    ВИДИМУЮ строку отчёта (build_report) — раньше сбой журнала был
    неотличим от успеха: [WARN] в stdout был, а факт "orchestrator-log НЕ
    записан" молчал."""
    target = repo / "state" / "orchestrator-log.md"
    original = log_append.ORCH_LOG
    log_append.ORCH_LOG = target
    try:
        log_append.append_orchestrator([
            "pre_step dirty_tree_check",
            "dirty_tree_check.py",
            f"{len(classified)} путей вне scratchpad/ (repo={repo})",
            "WARN: грязное дерево на старте прохода, leftover требует разбора до диспатчей",
        ])
        return True, ""
    except (Exception, SystemExit) as exc:
        # SystemExit не наследует Exception (BaseException) -- append_routing/
        # append_orchestrator сигнализируют отказ ИМЕННО SystemExit (см.
        # log_append.py _verify_environment); ловим оба, иначе сбой журнала
        # проходит сквозь этот try и роняет детектор (правило 5).
        return False, str(exc)
    finally:
        log_append.ORCH_LOG = original


# --------------------------------------------------------------------------
# Точка входа
# --------------------------------------------------------------------------

def build_report(cwd: Path, *, now: datetime | None = None,
                  log_orchestrator: bool = True) -> str:
    """Полный проход: собрать -> отфильтровать scratchpad/ -> классифицировать
    -> отформатировать. Возвращает готовый текст для stdout (main() просто
    печатает его). `log_orchestrator=False` — для тестов, которым не нужна
    сторона-эффект журнала (сам journal-путь покрыт отдельными тестами)."""
    now = now or datetime.now(timezone.utc)
    raw = collect_dirty_entries(cwd)
    if raw is None:
        return (
            "[WARN] dirty_tree_check: git недоступен или это не "
            "git-репозиторий — детектор деградировал, leftover-проверка "
            "пропущена (проход не остановлен)"
        )
    filtered = _filter_scratchpad(raw)
    if not filtered:
        return "dirty_tree_check: чисто"
    classified = classify(filtered, cwd, now)
    report = _format_warn(classified)
    if log_orchestrator:
        ok, msg = _log_to_orchestrator(classified, cwd)
        if not ok:
            # F1 (критик-фикс): сбой журнала -- видимая строка отчёта, не
            # тихий проглот.
            report += f"\n\nстрока в orchestrator-log НЕ записана: {msg}"
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="pre_step: детектор грязного дерева на старте прохода")
    parser.add_argument("--repo", default=str(REPO),
                        help="корень репозитория для проверки (по умолчанию — текущий)")
    args = parser.parse_args(argv)
    print(build_report(Path(args.repo)))
    return 0  # правило 5: код выхода ВСЕГДА 0 — информатор, не гейт


if __name__ == "__main__":
    sys.exit(main())
