"""gitlab_note — исходящая нота на ПРОИЗВОЛЬНЫЙ GitLab issue проекта.

Зачем: канал «вопрос разработчику в стори» (слово владельца 2026-08-19:
вопросы о коде/работе разработчиков ходят к разработчикам — комментарием
в баг, новым багом ИЛИ нотой в стори). gitlab_sync умеет ноты только у
БАГОВ (bugs/BUG-*.md с gitlab_issue); этот скрипт закрывает шов для
issue без QA-артефакта-носителя (стори, work item с issue-iid).

Канонические формы:
    python scripts/gitlab_note.py <iid> --text "текст ноты"
    python scripts/gitlab_note.py <iid> --text-file <путь>
    python scripts/gitlab_note.py <iid> --text "..." --dry-run

Поведение:
- iid — целое >0 (iid issue в проекте из framework/.gitlab-repo-url,
  тот же резолв, что у gitlab_sync).
- --text XOR --text-file; пустой/пробельный текст — ошибка (exit 1).
- Нота публикуется С ПРЕФИКСОМ "[qa] " (маркер источника ДЛЯ ЛЮДЕЙ;
  машинного само-фильтра у gitlab_inbound НЕТ — он отбрасывает только
  system:true), если текст уже не начинается с "[qa]".
- КОД-ГЕЙТ эхо-класса: iid, привязанный к багу (bugs/*.md с
  gitlab_issue == iid), ОТКЛОНЯЕТСЯ (exit 1) — на баг-issue нота
  вернулась бы gitlab_inbound'ом в «## Обсуждение» как чужая; канал
  для багов — «## Обсуждение» артефакта + gitlab_sync.
- --dry-run: печатает целевой path и текст, сети/токена не требует.
- Без GITLAB_TOKEN — exit 2 (тот же контракт, что gitlab_sync).
- Ошибка API (404 несуществующий iid и т.п.) — exit 1 с телом ответа.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gitlab_sync as gs  # noqa: E402

QA_PREFIX = "[qa] "


def build_note_body(text: str) -> str:
    """Нормализованный текст ноты: непустой, с [qa]-маркером источника."""
    if text is None or not text.strip():
        raise ValueError("текст ноты пуст")
    text = text.strip()
    if not text.startswith("[qa]"):
        text = QA_PREFIX + text
    return text


def post_note(client, iid: int, body: str) -> dict:
    """POST /issues/<iid>/notes. Возвращает JSON созданной ноты.

    Контракт GitLabClient.post — кортеж (status, parsed); ошибки HTTP
    клиент поднимает сам (GitLabHTTPError), здесь распаковка успеха.
    """
    _status, parsed = client.post(f"/issues/{iid}/notes", {"body": body})
    return parsed if isinstance(parsed, dict) else {}


def bug_owning_iid(iid: int) -> str | None:
    """id бага, чей gitlab_issue == iid, либо None (гейт эхо-класса)."""
    for path in gs.discover_bugs():
        try:
            meta, _ = gs.load_bug(path)
        except gs.BugSyncError:
            continue
        try:
            if int(str(meta.get("gitlab_issue", "")).strip() or 0) == iid:
                return str(meta.get("id") or path.stem)
        except ValueError:
            continue
    return None


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("iid", type=int, help="iid issue в проекте")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--text", default=None, help="текст ноты")
    src.add_argument("--text-file", default=None, metavar="PATH",
                     help="файл с текстом ноты (UTF-8)")
    parser.add_argument("--dry-run", action="store_true",
                        help="печатает план без сети/токена")
    args = parser.parse_args(argv)

    if args.iid <= 0:
        print(f"gitlab_note: iid должен быть > 0, получен {args.iid}",
              file=sys.stderr)
        return 1

    if args.text_file is not None:
        path = Path(args.text_file)
        if not path.is_file():
            print(f"gitlab_note: файл не найден: {path}", file=sys.stderr)
            return 1
        raw = path.read_text(encoding="utf-8")
    else:
        raw = args.text

    try:
        body = build_note_body(raw)
    except ValueError as e:
        print(f"gitlab_note: {e}", file=sys.stderr)
        return 1

    owner = bug_owning_iid(args.iid)
    if owner is not None:
        print(
            f"gitlab_note: issue {args.iid} принадлежит багу {owner} — нота "
            "вернулась бы gitlab_inbound'ом эхом в «## Обсуждение»; канал "
            "для багов — правка «## Обсуждение» артефакта + gitlab_sync",
            file=sys.stderr,
        )
        return 1

    if args.dry_run:
        print(f"DRY-RUN POST /issues/{args.iid}/notes ({len(body)} символов):")
        print(body)
        return 0

    token = os.environ.get("GITLAB_TOKEN")
    if not token:
        print(
            "gitlab_note: переменная окружения GITLAB_TOKEN не задана (нужен "
            "personal access token со scope 'api'); для офлайн-проверки "
            "используйте --dry-run",
            file=sys.stderr,
        )
        return 2

    repo_url = gs.read_repo_url()
    client = gs.GitLabClient(gs.api_base(repo_url), token)
    try:
        note = post_note(client, args.iid, body)
    except gs.GitLabHTTPError as e:
        print(f"[ERROR] gitlab_note: {e}", file=sys.stderr)
        return 1
    print(f"gitlab_note: нота {note.get('id')} создана на issue {args.iid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
