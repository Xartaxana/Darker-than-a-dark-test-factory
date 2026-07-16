"""critic_snapshot.py -- PreToolUse-хук: снимок дерева при КАЖДОМ
критик-вызове (kit v4 "full+gates", прогон N10).

STAGING_HQ ВАРИАНТ (t-159 п.7 -- НЕ активирован, staging-копия для
ревью и постановки Lead'ом, D-0069): единственное отличие от кита --
байтовое stdin-чтение (см. main()), тот же класс правки, что t-159
п.3/dispatch_gate.py. Логика снимка/семантика расхождения (ниже) НЕ
изменена.

Отличие от critic_gate.py (диет-kit v3): ЛИМИТА НЕТ -- полная
политика держит per-diff критика (правило 3), хук только фиксирует
факт: на момент каждого критик-вызова пишется/перезаписывается
.claude/critic_snapshot.json {ts, tree_hash, files_count}. Грейдер
сверяет ПОСЛЕДНИЙ снимок с финальным деревом: расхождение = "финал
не ревьюился" (неубираемый факт, не блок). Форма диспатча критика
проверяется отдельным dispatch_gate.py (лейбл) -- при его блоке
вызов не состоится и настоящий PreToolUse-side-effect снимка
безвреден: снимок перезапишется ближайшим состоявшимся вызовом;
след последнего РЕАЛЬНОГО ревью держится тем, что заблокированный
вызов не порождает работы критика.

tree_hash -- sha256 по отсортированному списку "{rel_path}:{sha256}"
всех файлов, исключая каталоги .claude/.git/__pycache__/.pytest_cache
(по имени на любой глубине) и logs/routing-log.jsonl -- алгоритм
байт-в-байт как compute_tree_hash() диет-kit v3 (t-150), грейдеры
переиспользуют ту же сверку.

t-159 (очередь v5 п.4) СЕМАНТИКА РАСХОЖДЕНИЯ -- явно, буквально:
"расхождение снимка = финал не совпал с ПОСЛЕДНИМ снимком критика"
означает КОНКРЕТНО "правки дерева ПОСЛЕ последнего Task/Agent-
ДИСПАТЧА критика" -- не "после последнего ревью критика" вообще.
Это различие материально: критик может РЕВЬЮИТЬ несколько раз в
одном и том же диспатче (агент читает, комментирует, читает снова)
без единого НОВОГО Task/Agent-вызова -- снимок пишется PreToolUse
ОДИН РАЗ, в момент диспатча, ДО того как критик реально что-то
прочитал в этом вызове; любые правки дерева, случившиеся ПОСЛЕ этого
момента диспатча, будут видны хуку как "расхождение", даже если
критик их честно перечитал в рамках ТОГО ЖЕ вызова (это уже
покрывает staleness внутри одного вызова -- хук не видит нутро
вызова, только before/after снимок относительно момента диспатча).

CONTINUATION-РЕ-РЕВЬЮ ХУКУ НЕВИДИМО (поправка 2026-07-16,
docs/tasks/2026-07-16_economy-exam-run7.md, разбор №10б-t1): если
координатор продолжает диалог с УЖЕ ЗАПУЩЕННЫМ критик-агентом через
инструмент continuation-канала (SendMessage к существующему
agent_id/session, НЕ новый Task/Agent-вызов) -- critic_snapshot.py НЕ
СРАБАТЫВАЕТ ВООБЩЕ, поскольку матчер этого хука (.claude/settings.json,
PreToolUse) зарегистрирован ТОЛЬКО на tool_name=="Task"|"Agent"
(main() явно фильтрует `if tool_name not in ("Task","Agent"): return 0`).
Живой прецедент №10б-t1: критик перепроверил дифф на 15 входах ПОСЛЕ
фикса через continuation того же critic-агента без нового
Task-диспатча -- снимок остался от ПЕРВОГО (исходного) диспатча,
грейдер увидел "расхождение" (финал не совпал со снимком), хотя
ре-ревью реально состоялось -- ОГРАНИЧЕНИЕ ИЗМЕРИТЕЛЯ, не факт "финал
не ревьюился".

ЭМПИРИЧЕСКАЯ ПРОВЕРКА "есть ли хук-точка на continuation-канал"
(t-159, метод -- тот же grep -a установленного бинарника claude.exe,
что дал схемы XWb/zWb в tools/dod_gate.py/tools/main_gate.py,
позитивный/негативный контроль F-30/F-34): ДА, точка существует В
ПРИНЦИПЕ, но НЕ АКТИВИРОВАНА в этом ките. Находки:
 1. Раннер хуков вызывает PreToolUse ОБЩЕЙ функцией для ЛЮБОГО
    tool_name (не только Task/Agent) -- строка из бандла: "let u=
    {...kf(o,void 0,n),hook_event_name:\"PreToolUse\",tool_name:e,
    tool_input:r,tool_use_id:t};yield*vP({hookInput:u,toolUseID:t,
    matchQuery:e,...})" внутри generator'а, логирующего
    "executePreToolHooks called for tool: ${e}" -- `e` (matchQuery)
    -- ЛЮБОЕ имя тула, включая continuation-инструмент; settings.json
    "matcher" фильтрует, КАКИЕ команды сработают на этом событии, не
    само событие.
 2. Continuation-инструмент этого харнесса -- отдельный, РЕАЛЬНО
    зарегистрированный тул с ИМЕНЕМ "SendMessage" (найдено буквально
    в бандле: `eh="SendMessage"`; `Mi({name:eh,searchHint:"send
    messages to agent teammates",...})` -- полноценное определение
    тула, не служебная строка). Это означает: hook-раннер способен
    вызвать PreToolUse СОБЫТИЕ для вызова SendMessage ТОЧНО ТАК ЖЕ,
    как для Task/Agent -- механизм общий.
 3. НЕ ПРОВЕРЕНО живым смоком (вне роли builder этой задачи, D-0037 --
    потребовало бы реального SendMessage-вызова к живому агенту под
    активным хуком): (а) СОВПАДАЕТ ли реальный tool_name полезной
    нагрузки PreToolUse для SendMessage буквально со строкой
    "SendMessage" (по аналогии с tool_input.subagent_type для
    Task/Agent, задокументированной в tools/dispatch_gate.py t-150
    смоком) -- ожидаемо да (тот же паттерн `name:eh`, что у любого
    другого зарегистрированного тула), но НЕ подтверждено живым
    payload'ом; (б) какая часть tool_input у SendMessage несёт
    целевой agent_id/session -- нужна для того, чтобы снимок мог бы
    (если бы это было в scope) обновляться на continuation ТОЖЕ.
 ВЫВОД для этого коммита: семантика расхождения задокументирована
 (выше), хук-точка для устранения слепоты ЕСТЬ (matcher можно
 расширить на "Task|SendMessage" в settings.json), но её АКТИВАЦИЯ
 -- новый enforcement-effect на .claude/settings.json -- вне
 объявленного scope пункта 4 (спека просит "документировать
 семантику + проверить эмпирикой, есть ли хук-точка", не "включить
 её") и, будь она включена, подпадает под D-0069/CLAUDE.md правило 2
 (самоактивирующийся enforcement-файл размещает Lead при приёмке, не
 builder) -- решение и размещение оставлены координатору.
"""

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

EXCLUDED_DIR_NAMES = {".claude", ".git", "__pycache__", ".pytest_cache"}
EXCLUDED_REL_FILES = {Path("logs") / "routing-log.jsonl"}
SNAPSHOT_REL_PATH = Path(".claude") / "critic_snapshot.json"


def compute_tree_hash(root: Path) -> tuple[str, int]:
    entries = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if any(part in EXCLUDED_DIR_NAMES for part in rel.parts):
            continue
        if rel in EXCLUDED_REL_FILES:
            continue
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        entries.append(f"{rel.as_posix()}:{digest}")
    tree = hashlib.sha256("\n".join(entries).encode("utf-8")).hexdigest()
    return tree, len(entries)


def main() -> int:
    # STAGING_HQ (t-159 п.7-style): байтовое stdin-чтение, тот же
    # класс правки, что t-159 п.3/dispatch_gate.py -- применено
    # единообразно ко всем staging_hq хукам, не только к тому, что
    # спека называла явно.
    raw_bytes = sys.stdin.buffer.read()
    raw = raw_bytes.decode("utf-8", errors="replace")
    try:
        payload = json.loads(raw)
    except Exception:
        return 0  # fail open: не наш формат -- не мешаем

    tool_name = payload.get("tool_name")
    tool_input = payload.get("tool_input") or {}
    if tool_name not in ("Task", "Agent"):
        return 0
    if tool_input.get("subagent_type") != "critic":
        return 0

    cwd = Path(payload.get("cwd") or ".")
    try:
        tree_hash, files_count = compute_tree_hash(cwd)
        snap = cwd / SNAPSHOT_REL_PATH
        snap.parent.mkdir(parents=True, exist_ok=True)
        snap.write_text(
            json.dumps(
                {
                    "ts": datetime.now().isoformat(),
                    "tree_hash": tree_hash,
                    "files_count": files_count,
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
    except Exception:
        return 0  # снимок -- измеритель, не гейт: не роняем диспатч
    return 0


if __name__ == "__main__":
    sys.exit(main())
