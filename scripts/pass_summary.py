"""pass_summary — канал пустоты прохода headless-ребёнка (Д п.5,
консолидированная секция spec-factory-window v7,
docs/tasks/factory-visible-window.md, 2026-08-16).

Ночной резерв (`scripts/factory_watchdog.py::run_fallback_pass`) спавнит
headless `/qa-loop 5` и получает наружу только `child_rc`/`outcome` —
СКОЛЬКО правил сработало и осталась ли отложенная работа, знает только
сама сессия `/qa-loop` (шаг 6 «Сводка», `.claude/skills/qa-loop/SKILL.md`).
Этот скрипт — единственный писатель `state/last-pass-summary.json`
(gitignored): headless-сессия вызывает его ПОСЛЕДНИМ шагом прохода,
сторож читает файл ПОСЛЕ возврата `run_fallback_pass` и сверяет `ts` с
окном прохода (битый/протухший/отсутствующий файл — «неизвестно», НЕ
«пусто» — иначе отказ канала молча снял бы two_empty-терминатор
unlimited-резерва: пустые проходы дают `rc==0`, slowdeath не взводится,
`passes_done` растёт до бесконечности).

**Машинный ts (Б5 r5)** — СКРИПТ САМ ставит `ts` (не координатор
текстом): единственный дом пина формата, не зависящий от локали/формата
даты, который координатор мог бы напечатать неточно.

Формат `state/last-pass-summary.json`:
    {"ts": "<ISO UTC, скрипт сам>", "triggered": <int>=0,
     "deferred": <int>=0, "rescan_delta": <int>=0}

`triggered` — сколько правил сработало (диспетчеризовано воркерам) за
проход; `deferred` — сколько строк в секции «отложено» шага 6;
`rescan_delta` — суммарная дельта ре-скана 4а (новые срабатывания,
рождённые самим проходом). «Пустой» проход по определению К1 п.4 спеки
(строгое 4-условное: состоялся И `triggered==0` И `deferred==0` И
`rescan_delta==0`) — интерпретация ЦЕЛИКОМ на стороне читателя
(`factory_watchdog.py`), этот скрипт только фиксирует три числа.

Запуск (шаг 6 qa-loop, ЕДИНСТВЕННЫЙ вызывающий):
  python scripts/pass_summary.py --triggered <N> --deferred <M> --rescan <K>
Атомарная запись (tmp + os.replace, класс BL-4) — никогда не бросает
исключение наружу; отказ записи печатается и код возврата 1 (headless-
сессия видит явный отказ, но проход дальше не роняет — шаг 6 идёт
последним)."""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

REPO = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_PATH = REPO / "state" / "last-pass-summary.json"


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def write_summary(*, triggered: int, deferred: int, rescan_delta: int,
                  output_path: Path = DEFAULT_OUTPUT_PATH,
                  now: datetime.datetime | None = None) -> dict:
    """Пишет `state/last-pass-summary.json` атомарно (tmp + os.replace).
    Возвращает записанный dict (ts — машинный, из `now` или `_utcnow()`).
    Отрицательные значения — ValueError (защита от опечатки в аргументе,
    не немой мусор в файле)."""
    for name, value in (("triggered", triggered), ("deferred", deferred),
                        ("rescan_delta", rescan_delta)):
        if value < 0:
            raise ValueError(f"pass_summary: {name}={value} < 0 — не может быть отрицательным")
    now = now or _utcnow()
    data = {
        "ts": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "triggered": int(triggered),
        "deferred": int(deferred),
        "rescan_delta": int(rescan_delta),
    }
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = output_path.with_name(output_path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, output_path)
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="pass_summary — канал пустоты прохода headless-ребёнка (Д п.5)")
    parser.add_argument("--triggered", type=int, required=True,
                        help="сколько правил сработало (диспетчеризовано) за проход")
    parser.add_argument("--deferred", type=int, required=True,
                        help="сколько строк в секции «отложено» шага 6")
    parser.add_argument("--rescan", type=int, required=True, dest="rescan_delta",
                        help="суммарная дельта ре-скана 4а (новые срабатывания)")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH),
                        help="ТОЛЬКО для тестов/смок-прогонов")
    args = parser.parse_args(argv)

    try:
        data = write_summary(triggered=args.triggered, deferred=args.deferred,
                             rescan_delta=args.rescan_delta, output_path=Path(args.output))
    except ValueError as e:
        print(f"pass_summary: отказ — {e}")
        return 1
    except OSError as e:
        print(f"pass_summary: запись не удалась — {e}")
        return 1

    print(f"pass_summary: ts={data['ts']} triggered={data['triggered']} "
          f"deferred={data['deferred']} rescan_delta={data['rescan_delta']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
