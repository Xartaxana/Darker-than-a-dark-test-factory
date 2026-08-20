"""new_case_status_gate — pre-commit гейт против нелегальной инициализации
статуса нового test-case (спека C v2, C2; инцидент
TEST-DESIGNER-APPROVED-OUT-OF-MANIFEST — часть 3 из 11 файлов инцидента
были НОВЫМИ файлами, заведёнными сразу со status: Approved, минуя
Draft/Review).

schemas/transitions.yaml machines.test-case:
    initial: [Draft, Review]
    ...*->Approved — только by: [human] (via_board) либо by: [qa-loop]
    (и только для P2/P3, "пока не реализован").

Файл test-case, добавленный (`git diff --cached --diff-filter=A`) в этот
коммит, со status ВНЕ {Draft, Review} — не мог легально получить этот
статус: единственный способ статуса стать Approved — ЖИВОЙ переход
ПОСЛЕ создания файла (human/qa-loop), не единомоментное заведение файла
уже в этом статусе. Такой коммит отклоняется (rc=1).

ОХВАТ (намеренно узкий, докстринг обязателен по спеке): только НОВЫЕ
(added) файлы test-cases/ этого коммита — 3 из 11 файлов инцидента
TEST-DESIGNER-APPROVED-OUT-OF-MANIFEST. Остаточный детектор для
TRACKED-флипов (существующий Draft/Review-файл руками агента без
легального актора переводится в Approved вне human/qa-loop) — actor-
матрица schemas/transitions.yaml + чек 5 калибровки OS (named, не
реализован этим скриптом: ретроактивная сверка истории коммитов —
отдельная, более дорогая задача).

Деградация: любой отказ git (не git-репозиторий, git не найден, битый
индекс) -> rc 0 + одна строка "[WARN] ..." на stdout — информатор-гейт,
не должен наглухо блокировать коммиты при битом git. Битый/непарсящийся
frontmatter добавленного файла -> тоже WARN, не падение (файл пропускается
из проверки статуса, но коммит не блокируется этим одним файлом).

C2-F4 (критик-раунд): эта fail-open ветка (битый/непарсящийся frontmatter
пропускается WARN'ом, не блокирует) НЕ безнадзорна — компенсирующий
детектор уже существует и живёт в ДРУГОМ механизме: как только такой
файл всё-таки закоммичен, `scripts/validate_frontmatter.py` на СЛЕДУЮЩЕМ
preflight-прогоне (`/qa-loop`) даёт ERROR «frontmatter отсутствует или
не парсится» (см. `validate()` в этом соседнем скрипте) — окно между
коммитом и следующим preflight остаётся, но файл не проваливается в
тишину навсегда.

Пустой список added test-cases файлов -> rc 0 МОЛЧА (не замедлять каждый
коммит без добавленных кейсов).

Вызывается из .githooks/pre-commit после escape_check.py/enforcement_probe.py.

Запуск: python scripts/new_case_status_gate.py
Коды выхода: 0 — чисто/не применимо/git отказал (WARN); 1 — есть
нелегальная инициализация статуса (ERROR, перечень файлов).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import board_sync as bs  # noqa: E402

REPO = SCRIPTS_DIR.parent
LEGAL_INITIAL_STATUSES = {"Draft", "Review"}


def _run_git(args: list[str]) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            ["git", *args], cwd=REPO, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=10,
        )
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return 1, "", str(exc)
    return proc.returncode, proc.stdout, proc.stderr


def added_test_case_paths() -> list[str] | None:
    """Staged added-пути под test-cases/ (git-строки, POSIX, как есть в
    индексе). ОДИН git-вызов (`-z`: NUL-разделённый вывод — устойчив к
    пробелам/не-ASCII в имени файла без риска quotePath-экранирования).
    None — git отказал (отличать от [] — пустого, но легального, списка).

    F1 (критик-раунд C v2, воспроизведено): `--no-renames` ОБЯЗАТЕЛЕН —
    без него `git mv test-cases/TC-XXX.md test-cases/TC-YYY.md` +
    одновременная смена `status:` внутри того же коммита детектируется
    git'ом как переименование (`R`, similarity-эвристика), а НЕ как
    добавление — такая запись НЕ матчит `--diff-filter=A` вовсе и
    полностью обходит этот гейт (сосед по хуку `enforcement_probe.py`
    несёт тот же критик-фикс F2/t-339, см. `_staged_files` там). С
    `--no-renames` git репортует пару D(старый путь)+A(новый путь) —
    новый путь ловится диффом штатно.

    Парсинг парами (`i += 2`): корректен ТОЛЬКО при `--diff-filter=A` +
    `--no-renames` одновременно — фильтр гарантирует единственный статус
    "A" в потоке (никаких R-записей, которым нужно 3 токена: статус +
    старый путь + новый путь)."""
    rc, out, _err = _run_git(
        ["diff", "--cached", "--name-status", "--diff-filter=A",
         "--no-renames", "-z", "--", "test-cases"]
    )
    if rc != 0:
        return None
    parts = [p for p in out.split("\0") if p != ""]
    paths: list[str] = []
    i = 0
    while i < len(parts):
        status = parts[i]
        path = parts[i + 1] if i + 1 < len(parts) else None
        if status == "A" and path is not None:
            paths.append(path)
        i += 2
    return paths


def staged_content(path: str) -> str | None:
    """Содержимое файла В ИНДЕКСЕ (`git show :<path>`) — staged-версия,
    не рабочее дерево (могут отличаться). None — git отказал."""
    rc, out, _err = _run_git(["show", f":{path}"])
    if rc != 0:
        return None
    return out


def main(argv: list[str] | None = None) -> int:
    paths = added_test_case_paths()
    if paths is None:
        print("[WARN] new_case_status_gate: `git diff --cached` отказал — "
              "гейт пропущен (fail-open, не блокировать коммит битым git)")
        return 0
    if not paths:
        return 0

    violations: list[tuple[str, str]] = []
    for path in paths:
        text = staged_content(path)
        if text is None:
            print(f"[WARN] new_case_status_gate: `git show :{path}` отказал — "
                  f"проверка статуса этого файла пропущена")
            continue
        meta, _body = bs._parse_frontmatter(text)
        if not meta:
            print(f"[WARN] new_case_status_gate: {path} — frontmatter "
                  f"отсутствует/не парсится, проверка статуса пропущена")
            continue
        status = str(meta.get("status", "") or "").strip()
        if status not in LEGAL_INITIAL_STATUSES:
            violations.append((path, status))

    if violations:
        print("[ERROR] new_case_status_gate: нелегальная инициализация "
              "статуса нового test-case:")
        for path, status in violations:
            print(f"  {path}: status={status!r} — initial легален только "
                  f"{sorted(LEGAL_INITIAL_STATUSES)}")
        print("schemas/transitions.yaml machines.test-case: "
              "`initial: [Draft, Review]` (test-designer: Draft при спорных "
              "требованиях, иначе сразу Review); `*->Approved` — только "
              "`by: [human]`/`by: [qa-loop]` у СУЩЕСТВУЮЩЕГО файла, не "
              "заведение файла сразу в этом статусе.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
