"""Юнит-тесты ядра и обвязки board_inbound (docs/07).

Покрытие classify(): apply / reject / conflict / noop-stale / reopen-from-any,
вставка status_since в legacy-артефакт, а также обвязка: перенос комментариев
TrackState в ## Обсуждение (формат board/<KEY>/comments/<NNNN>.md) и дедуп.

Все тесты работают в tmp_path-репо (фикстура `repo` в conftest), реальные bugs/
не затрагиваются. Запуск:
    framework/.venv/Scripts/python.exe -m pytest scripts/tests -q
"""
from __future__ import annotations

import board_inbound as bi


def _classify_one(key: str):
    states = {ts.key: ts for ts in bi.gather()}
    return bi.classify(states[key]), states


# --- classify(): ветки whitelist / рассинхрон / конфликт ---------------------

def test_apply_valid_transition(repo):
    """Человек Open→Fixed (в whitelist), агент не трогал → apply + запись статуса."""
    src = repo.bug("BUG-100", "Open", extra="status_since: \"2026-07-01T00:00:00Z\"\n")
    repo.board_card("BUG-100", "bug", "Fixed")
    repo.cursor({"BUG-100": {"itype": "bug", "artifact_status": "Open", "board_status": "Open"}})

    action, _ = _classify_one("BUG-100")
    assert action.kind == "apply"
    assert action.new_status == "Fixed"

    bi.apply_status(action.src, action.new_status, dry=False)
    text = src.read_text(encoding="utf-8")
    assert "status: Fixed" in text
    assert "status_since:" in text


def test_reject_out_of_whitelist(repo):
    """Человек Open→Verified (НЕ в whitelist для bug) → reject, артефакт не тронут."""
    src = repo.bug("BUG-101", "Open")
    repo.board_card("BUG-101", "bug", "Verified")
    repo.cursor({"BUG-101": {"itype": "bug", "artifact_status": "Open", "board_status": "Open"}})

    action, _ = _classify_one("BUG-101")
    assert action.kind == "reject"
    assert "status: Open" in src.read_text(encoding="utf-8")


def test_conflict_both_moved(repo):
    """И человек (→Fixed), и агент (→Blocked) подвинули один тикет → conflict→Blocked + эскалация."""
    src = repo.bug("BUG-102", "Blocked")  # артефакт уже сдвинут агентом
    repo.board_card("BUG-102", "bug", "Fixed")  # карточку сдвинул человек
    repo.cursor({"BUG-102": {"itype": "bug", "artifact_status": "Open", "board_status": "Open"}})

    action, states = _classify_one("BUG-102")
    assert action.kind == "conflict"

    ts = states["BUG-102"]
    bi.apply_conflict(action, ts.board_status, ts.artifact_status, dry=False)
    assert "status: Blocked" in src.read_text(encoding="utf-8")
    assert bi.ESCALATIONS_PATH.exists()
    assert "BUG-102" in bi.ESCALATIONS_PATH.read_text(encoding="utf-8")
    # B5: причина конфликта детерминирована — нужно решение человека.
    assert "blocked_reason: product_decision" in src.read_text(encoding="utf-8")


def test_cursor_advanced_prevents_false_conflict(repo):
    """Регрессия: после apply курсор продвигается, поэтому повторный проход БЕЗ
    board_sync (краш/пропуск sync) даёт noop, а НЕ ложный конфликт.

    Без продвижения курсора: проход 2 видел бы борду=Fixed (человек), артефакт=Fixed
    (применили), курсор=Open/Open → human_moved И agent_moved → ложный конфликт →
    баг ошибочно в Blocked + эскалация. Проверяем, что этого не происходит."""
    import json
    src = repo.bug("BUG-108", "Open", extra="status_since: \"2026-07-01T00:00:00Z\"\n")
    repo.board_card("BUG-108", "bug", "Fixed")
    repo.cursor({"BUG-108": {"itype": "bug", "artifact_status": "Open", "board_status": "Open"}})

    # Проход 1: применяет Open→Fixed и продвигает курсор.
    bi.reconcile(dry=False)
    assert "status: Fixed" in src.read_text(encoding="utf-8")
    cur = json.loads(bi.CURSOR_PATH.read_text(encoding="utf-8"))
    assert cur["BUG-108"] == {"itype": "bug", "artifact_status": "Fixed", "board_status": "Fixed"}

    # Проход 2 БЕЗ board_sync между ними (борда всё ещё Fixed, артефакт Fixed).
    actions2 = bi.reconcile(dry=False)
    a2 = next(a for a in actions2 if a.key == "BUG-108")
    assert a2.kind == "noop", f"ожидался noop, получено {a2.kind}: {a2.detail}"
    # Артефакт не должен быть переведён в Blocked, эскалации по BUG-108 быть не должно.
    assert "status: Fixed" in src.read_text(encoding="utf-8")
    if bi.ESCALATIONS_PATH.exists():
        assert "BUG-108" not in bi.ESCALATIONS_PATH.read_text(encoding="utf-8")


def test_noop_stale_only_agent(repo):
    """Только агент подвинул артефакт (борда отстала) → noop, sync догонит."""
    repo.bug("BUG-103", "Fixed")
    repo.board_card("BUG-103", "bug", "Open")  # борда ещё на старом
    repo.cursor({"BUG-103": {"itype": "bug", "artifact_status": "Open", "board_status": "Open"}})

    action, _ = _classify_one("BUG-103")
    assert action.kind == "noop"


def test_reopen_from_any(repo):
    """`любой → Open` — ручное переоткрытие из whitelist «*», даже из Fixed."""
    src = repo.bug("BUG-104", "Fixed")
    repo.board_card("BUG-104", "bug", "Open")
    repo.cursor({"BUG-104": {"itype": "bug", "artifact_status": "Fixed", "board_status": "Fixed"}})

    action, _ = _classify_one("BUG-104")
    assert action.kind == "apply"
    assert action.new_status == "Open"


def test_tc_review_to_approved(repo):
    """test-case Review→Approved (whitelist §3) → apply."""
    repo.test_case("TC-100", "Review")
    repo.board_card("TC-100", "test-case", "Approved")
    repo.cursor({"TC-100": {"itype": "test-case", "artifact_status": "Review", "board_status": "Review"}})

    action, _ = _classify_one("TC-100")
    assert action.kind == "apply"
    assert action.new_status == "Approved"


def test_no_cursor_is_base(repo):
    """Тикет без курсора (первый sync) → noop (принят за базу), даже если статусы разошлись."""
    repo.bug("BUG-105", "Fixed")
    repo.board_card("BUG-105", "bug", "Open")
    repo.cursor({})  # курсора для BUG-105 нет

    action, _ = _classify_one("BUG-105")
    assert action.kind == "noop"


# --- вставка status_since в legacy-артефакт (нет поля) -----------------------

def test_status_since_inserted_into_legacy(repo):
    """Legacy-баг без status_since: apply вставляет поле сразу после status:."""
    src = repo.bug("BUG-106", "Open")  # без status_since
    assert "status_since" not in src.read_text(encoding="utf-8")
    repo.board_card("BUG-106", "bug", "Fixed")
    repo.cursor({"BUG-106": {"itype": "bug", "artifact_status": "Open", "board_status": "Open"}})

    action, _ = _classify_one("BUG-106")
    bi.apply_status(action.src, action.new_status, dry=False)
    text = src.read_text(encoding="utf-8")
    assert "status_since:" in text
    # поле должно стоять сразу после строки status:
    lines = [ln for ln in text.splitlines()]
    si = next(i for i, ln in enumerate(lines) if ln.startswith("status:"))
    assert lines[si + 1].startswith("status_since:")


def test_reopen_bumps_count(repo):
    """→Reopened инкрементирует reopen_count (или вставляет reopen_count: 1)."""
    src = repo.bug("BUG-107", "Fixed", extra="reopen_count: 2\n")
    repo.board_card("BUG-107", "bug", "Open")  # сначала переоткрытие → Open? нужен Reopened
    # прямой вызов apply_status на Reopened (whitelist Open|Reopened, но bump — по статусу)
    bi.apply_status(src, "Reopened", dry=False)
    assert "reopen_count: 3" in src.read_text(encoding="utf-8")


# --- обвязка: комментарии TrackState → ## Обсуждение -------------------------

def test_collect_board_comments_format(repo):
    """Читает board/<KEY>/comments/<NNNN>.md в Comment (author/created/body)."""
    repo.board_comment("BUG-200", "0001", "dev@team", "2026-07-04T10:00:00.000Z", "Почему это баг?")
    comments = bi.collect_board_comments("BUG-200")
    assert len(comments) == 1
    c = comments[0]
    assert c.author == "dev@team"
    assert c.created == "2026-07-04T10:00:00.000Z"
    assert c.body == "Почему это баг?"


def test_collect_board_comments_sorted(repo):
    repo.board_comment("BUG-201", "0002", "dev", "2026-07-04T11:00:00Z", "вторая")
    repo.board_comment("BUG-201", "0001", "dev", "2026-07-04T10:00:00Z", "первая")
    comments = bi.collect_board_comments("BUG-201")
    assert [c.cid for c in comments] == ["0001", "0002"]


def test_sync_comments_appends_and_awaiting(repo):
    """Новая реплика человека → строка в ## Обсуждение + awaiting: qa."""
    src = repo.bug("BUG-202", "Open")
    repo.board_card("BUG-202", "bug", "Open")
    repo.cursor({"BUG-202": {"itype": "bug", "artifact_status": "Open", "board_status": "Open"}})
    repo.board_comment("BUG-202", "0001", "dev@team", "2026-07-04T10:00:00Z", "Не воспроизводится у меня.")

    bi.reconcile(dry=False)
    text = src.read_text(encoding="utf-8")
    assert "## Обсуждение" in text
    assert "**[dev@team @ 2026-07-04T10:00:00Z]** Не воспроизводится у меня." in text
    assert "awaiting: qa" in text


def test_sync_comments_dedup(repo):
    """Уже перенесённая реплика (тот же автор+время+текст) не дублируется на повторном проходе."""
    src = repo.bug("BUG-203", "Open")
    repo.board_card("BUG-203", "bug", "Open")
    repo.cursor({"BUG-203": {"itype": "bug", "artifact_status": "Open", "board_status": "Open"}})
    repo.board_comment("BUG-203", "0001", "dev", "2026-07-04T10:00:00Z", "реплика раз")

    bi.reconcile(dry=False)
    bi.reconcile(dry=False)  # второй проход — не должен продублировать
    text = src.read_text(encoding="utf-8")
    assert text.count("**[dev @ 2026-07-04T10:00:00Z]** реплика раз") == 1


def test_sync_comments_creates_section_if_missing(repo):
    """Legacy-артефакт без ## Обсуждение: раздел создаётся при переносе реплики."""
    src = repo.bug("BUG-204", "Open")
    assert "## Обсуждение" not in src.read_text(encoding="utf-8")
    repo.cursor({"BUG-204": {"itype": "bug", "artifact_status": "Open", "board_status": "Open"}})
    repo.board_card("BUG-204", "bug", "Open")
    repo.board_comment("BUG-204", "0001", "dev", "2026-07-04T10:00:00Z", "первый коммент")

    bi.reconcile(dry=False)
    assert "## Обсуждение" in src.read_text(encoding="utf-8")


def test_dry_run_does_not_write(repo):
    """--dry-run: ни статус, ни комментарии не пишутся на диск."""
    src = repo.bug("BUG-205", "Open")
    repo.board_card("BUG-205", "bug", "Fixed")
    repo.cursor({"BUG-205": {"itype": "bug", "artifact_status": "Open", "board_status": "Open"}})
    repo.board_comment("BUG-205", "0001", "dev", "2026-07-04T10:00:00Z", "коммент")

    before = src.read_text(encoding="utf-8")
    bi.reconcile(dry=True)
    assert src.read_text(encoding="utf-8") == before
