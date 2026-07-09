"""Тесты scripts/log_append.py — каноничное добавление строк в журналы."""
from __future__ import annotations

import io
import json

import pytest

import log_append as la


@pytest.fixture()
def logs(tmp_path, monkeypatch):
    routing = tmp_path / "logs" / "routing-log.jsonl"
    orch = tmp_path / "state" / "orchestrator-log.md"
    monkeypatch.setattr(la, "ROUTING_LOG", routing, raising=True)
    monkeypatch.setattr(la, "ORCH_LOG", orch, raising=True)
    return routing, orch


def test_routing_appends_json_line_with_ts(logs):
    routing, _ = logs
    la.main(["routing", "--event", "delegated", "--agent", "builder",
             "--model", "sonnet", "--task-id", "t-001",
             "--category", "implementation", "--notes", "тест"])
    lines = routing.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["event"] == "delegated"
    assert rec["agent"] == "builder"
    assert rec["model"] == "sonnet"
    assert rec["task_id"] == "t-001"
    assert rec["notes"] == "тест"
    assert rec["ts"].startswith("20") and "T" in rec["ts"]


def test_main_returns_0_when_stdout_console_codepage_cannot_encode_notes(logs, monkeypatch):
    # Прецедент (docs/HANDOFF.md, chip task_305afa14): scripts/log_append.py
    # успешно дописывает строку в файл (_append_line, encoding="utf-8"), но
    # затем падал с exit 1 на финальном print(line) в stdout, если консоль
    # Windows была в узкой кодовой странице (напр. cp1251), а --notes
    # содержала символ вне неё (напр. "≠"). Ложный exit 1 мог заставить
    # вызывающего ретраить и задублировать запись в журнале. Симулируем
    # именно такую консоль: TextIOWrapper с encoding="cp1251", errors="strict"
    # поверх BytesIO — как реальный узкий поток stdout, до правки
    # (sys.stdout.reconfigure в main()) print() на нём бросал
    # UnicodeEncodeError на символ "≠".
    routing, _ = logs
    buf = io.BytesIO()
    narrow_stdout = io.TextIOWrapper(buf, encoding="cp1251", errors="strict",
                                      newline="\n")
    monkeypatch.setattr("sys.stdout", narrow_stdout)

    # Убедиться, что сценарий воспроизводит исходный баг: без reconfigure
    # запись символа "≠" в этот поток действительно бросает UnicodeEncodeError.
    with pytest.raises(UnicodeEncodeError):
        narrow_stdout.write("≠")
    # write() выше мог продвинуть внутренний буфер TextIOWrapper в неполное
    # состояние — пересоздаём поток для чистого прогона main().
    buf = io.BytesIO()
    narrow_stdout = io.TextIOWrapper(buf, encoding="cp1251", errors="strict",
                                      newline="\n")
    monkeypatch.setattr("sys.stdout", narrow_stdout)

    exit_code = la.main(["routing", "--event", "dispatch_skipped",
                          "--agent", "scout", "--category", "recon",
                          "--notes", "тест ≠ дефект"])
    assert exit_code == 0

    lines = routing.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["notes"] == "тест ≠ дефект"


def test_routing_model_required_for_delegated_escalated_accepted_rejected(logs):
    routing, _ = logs
    for event in ("delegated", "escalated", "accepted", "rejected"):
        with pytest.raises(SystemExit):
            la.append_routing(event, "builder")
    assert not routing.exists()


def test_routing_model_optional_for_other_events(logs):
    routing, _ = logs
    la.append_routing("lead_degraded", "lead", notes="лимит подписки")
    rec = json.loads(routing.read_text(encoding="utf-8"))
    assert rec["event"] == "lead_degraded"
    assert "model" not in rec


def test_routing_events_match_claude_md_policy(logs):
    # CLAUDE.md «Журнал маршрутизации»: полный список событий политики.
    # Расхождение = скрипт молча отклоняет легитимное событие (прецедент:
    # dispatch_skipped, 2026-07-08).
    assert la.ROUTING_EVENTS == {
        "delegated", "accepted", "rejected", "escalated", "decomposable",
        "dispatch_skipped", "defect_found", "lead_degraded", "lead_restored",
    }


def test_routing_accepts_defect_found_without_model(logs):
    # D-0052/D-0053 OS-репо: defect_found ссылается полем ref на task_id
    # исходного accepted; model не требуется — её несёт исходное событие.
    routing, _ = logs
    la.append_routing("defect_found", "builder", task_id="t-002",
                      ref="t-001", category="implementation",
                      notes="что сломалось")
    rec = json.loads(routing.read_text(encoding="utf-8"))
    assert rec["event"] == "defect_found"
    assert rec["ref"] == "t-001"
    assert "model" not in rec


def test_routing_task_id_required_for_task_events(logs):
    # D-0053: несущие факты — типизированными полями, не прозой в notes.
    routing, _ = logs
    for event in ("delegated", "accepted", "escalated"):
        with pytest.raises(SystemExit):
            la.append_routing(event, "scout", model="haiku")
    with pytest.raises(SystemExit):
        la.append_routing("defect_found", "builder", ref="t-001")
    assert not routing.exists()


def test_routing_rejected_requires_attempt_and_failure_class(logs):
    routing, _ = logs
    with pytest.raises(SystemExit):  # нет failure_class
        la.append_routing("rejected", "builder", model="sonnet",
                          task_id="t-003", attempt=1)
    with pytest.raises(SystemExit):  # failure_class вне enum
        la.append_routing("rejected", "builder", model="sonnet",
                          task_id="t-003", attempt=1, failure_class="vibes")
    with pytest.raises(SystemExit):  # нет attempt
        la.append_routing("rejected", "builder", model="sonnet",
                          task_id="t-003", failure_class="spec")
    la.append_routing("rejected", "builder", model="sonnet", task_id="t-003",
                      attempt=2, failure_class="capability", notes="причина")
    rec = json.loads(routing.read_text(encoding="utf-8"))
    assert rec["attempt"] == 2
    assert rec["failure_class"] == "capability"


def test_routing_accepted_builder_requires_witness(logs):
    # D-0052: accepted по builder без witness = самосертификация.
    routing, _ = logs
    with pytest.raises(SystemExit):
        la.append_routing("accepted", "builder", model="sonnet",
                          task_id="t-004")
    la.append_routing("accepted", "builder", model="sonnet", task_id="t-004",
                      witness="python -m pytest scripts/tests -q -> 241 passed")
    rec = json.loads(routing.read_text(encoding="utf-8"))
    assert "241 passed" in rec["witness"]
    # scout принимается без witness (его след — Trail в дайджесте, D-0046)
    la.append_routing("accepted", "scout", model="haiku", task_id="t-005")
    assert len(routing.read_text(encoding="utf-8").splitlines()) == 2


def test_routing_accepts_dispatch_skipped_without_model(logs):
    routing, _ = logs
    la.append_routing("dispatch_skipped", "scout", category="recon",
                      notes="точечная сверка известных файлов")
    rec = json.loads(routing.read_text(encoding="utf-8"))
    assert rec["event"] == "dispatch_skipped"
    assert rec["agent"] == "scout"


def test_routing_rejects_unknown_event(logs):
    with pytest.raises(SystemExit):
        la.append_routing("started", "builder", model="sonnet")


def test_routing_appends_not_overwrites(logs):
    # task_id t-001, не t-006: с D-0060/F-23 fresh task_id для delegated
    # обязан быть max(t-NNN)+1, а журнал в этом тесте пуст (см. отчёт
    # builder'а, t-009 — существующий тест скорректирован).
    routing, _ = logs
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001")
    la.append_routing("accepted", "builder", model="sonnet", task_id="t-001",
                      witness="pytest -q -> passed")
    assert len(routing.read_text(encoding="utf-8").splitlines()) == 2


def test_orchestrator_row_format(logs):
    _, orch = logs
    la.main(["orchestrator", "Правило X", "test-automator", "TC-050", "OK: готово"])
    line = orch.read_text(encoding="utf-8").splitlines()[-1]
    cells = [c.strip() for c in line.strip("|").split("|")]
    assert len(cells) == 5
    assert cells[0].endswith("Z")
    assert cells[1:] == ["Правило X", "test-automator", "TC-050", "OK: готово"]


def test_orchestrator_escapes_pipes_and_newlines(logs):
    _, orch = logs
    la.append_orchestrator(["a|b", "агент", "х", "строка\nдве"])
    line = orch.read_text(encoding="utf-8").splitlines()[-1]
    assert "a\\|b" in line
    assert "\nдве" not in line and "строка две" in line


def test_orchestrator_requires_exactly_four_cells(logs):
    with pytest.raises(SystemExit):
        la.append_orchestrator(["только", "три", "ячейки"])


# D-0060/F-23: две параллельные сессии выдали один task_id (t-008) двум
# разным задачам в append-only журнале. Новый task_id обязан быть
# max(существующих t-NNN)+1; повторный delegated на уже accepted task_id —
# коллизия, требует осознанного --reopen-task.

def test_delegated_fresh_sequential_id_passes(logs):
    routing, _ = logs
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001")
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-002")
    lines = routing.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[1])["task_id"] == "t-002"


def test_delegated_fresh_id_gap_or_lower_rejected_names_expected_id(logs):
    routing, _ = logs
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001")
    with pytest.raises(SystemExit, match="t-002"):  # разрыв
        la.append_routing("delegated", "builder", model="sonnet", task_id="t-005")
    with pytest.raises(SystemExit, match="t-002"):  # ниже ожидаемого, ранее не встречался
        la.append_routing("delegated", "builder", model="sonnet", task_id="t-000")
    # ни один из отклонённых вызовов не дописался в журнал
    assert len(routing.read_text(encoding="utf-8").splitlines()) == 1


def test_delegated_continuation_after_rejected_or_escalated_passes(logs):
    routing, _ = logs
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001")
    la.append_routing("rejected", "builder", model="sonnet", task_id="t-001",
                      attempt=1, failure_class="capability")
    # ретрай на тот же task_id — легальное продолжение, не коллизия
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001")
    la.append_routing("escalated", "critic", model="opus", task_id="t-001")
    la.append_routing("delegated", "critic", model="opus", task_id="t-001")
    lines = routing.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 5
    # следующий свежий id всё ещё считается от t-001 (единственный t-NNN)
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-002")
    assert len(routing.read_text(encoding="utf-8").splitlines()) == 6


def test_delegated_on_accepted_task_id_rejected_without_reopen_flag(logs):
    routing, _ = logs
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001")
    la.append_routing("accepted", "builder", model="sonnet", task_id="t-001",
                      witness="pytest -q -> passed")
    with pytest.raises(SystemExit, match="t-001"):
        la.append_routing("delegated", "builder", model="sonnet", task_id="t-001")
    assert len(routing.read_text(encoding="utf-8").splitlines()) == 2


def test_delegated_on_accepted_task_id_passes_with_reopen_flag(logs):
    routing, _ = logs
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001")
    la.append_routing("accepted", "builder", model="sonnet", task_id="t-001",
                      witness="pytest -q -> passed")
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                      reopen_task="F-23: коллизия, повторное открытие осознанно")
    lines = routing.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    rec = json.loads(lines[-1])
    assert rec["task_id"] == "t-001"
    assert "reopen" in rec["notes"] and "F-23" in rec["notes"]


def test_delegated_empty_journal_expects_t001(logs):
    routing, _ = logs
    assert not routing.exists()
    with pytest.raises(SystemExit, match="t-001"):
        la.append_routing("delegated", "builder", model="sonnet", task_id="t-999")
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001")
    assert json.loads(routing.read_text(encoding="utf-8").splitlines()[0])["task_id"] == "t-001"


def test_delegated_new_descriptive_task_id_passes_on_nonempty_journal(logs):
    # t-009, попытка 2: исправление п.1 спеки (была ошибка в первой версии,
    # см. отчёт попытки 1 — там это фиксировалось как расхождение). Порядок
    # t-NNN обязателен ТОЛЬКО для id, чей формат полностью (full-match)
    # совпадает с последовательностью t-(\d+). Описательный id (например,
    # новый баг at-bug-005) — не такой формат, поэтому проходит как новый
    # без проверки последовательности, даже если журнал уже непуст и в нём
    # есть t-NNN записи.
    routing, _ = logs
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001")
    la.append_routing("delegated", "test-maintainer", model="sonnet",
                      task_id="at-bug-005")
    lines = routing.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[1])["task_id"] == "at-bug-005"


def test_delegated_substring_t_nn_inside_descriptive_id_treated_as_descriptive(logs):
    # Спека п.3 (t-009, попытка 2): id вроде "fix-t-12-encoding" содержит
    # substring "t-12", но НЕ full-match с ^t-(\d+)$ — значит трактуется как
    # описательный и проходит свободно как новый, без применения проверки
    # последовательности (и без влияния на последующий max(t-NNN)).
    routing, _ = logs
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001")
    la.append_routing("delegated", "test-maintainer", model="sonnet",
                      task_id="fix-t-12-encoding")
    lines = routing.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[1])["task_id"] == "fix-t-12-encoding"
    # substring "t-12" не должен был войти в подсчёт max(t-NNN): следующий
    # свежий последовательный id всё ещё t-002, а не t-013.
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-002")
    assert len(routing.read_text(encoding="utf-8").splitlines()) == 3


def test_delegated_preexisting_descriptive_task_id_continues_freely(logs):
    # Id формата t-NNN обязателен только для СВЕЖИХ task_id (спека п.1).
    # Если task_id уже встречался в журнале (в т.ч. описательный, из истории
    # ДО этой правки) — это продолжение (п.2), формат id при этом не
    # проверяется, легальность определяется только последним lifecycle-
    # событием этого id.
    routing, _ = logs
    # Симулируем предсуществующую историю: at-bug-003 уже упоминался в
    # журнале (rejected), прежде чем эта проверка появилась.
    la.append_routing("rejected", "test-maintainer", model="sonnet",
                      task_id="at-bug-003", attempt=1, failure_class="capability")
    la.append_routing("delegated", "test-maintainer", model="sonnet",
                      task_id="at-bug-003")
    assert len(routing.read_text(encoding="utf-8").splitlines()) == 2


def test_delegated_id_with_spaces_stripped(logs):
    # t-010 (критик F-C по t-009): " t-002 " раньше молча уходил в
    # описательную ветку; теперь id нормализуется strip'ом и проходит
    # проверку последовательности, в журнал пишется очищенным.
    routing, _ = logs
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001")
    la.append_routing("delegated", "builder", model="sonnet", task_id=" t-002 ")
    lines = routing.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[1])["task_id"] == "t-002"


def test_delegated_fresh_sequential_id_fails_on_wrong_case(logs):
    # t-010 (критик F-C): "T-002" похож на последовательность, но не в
    # канонической форме — явный отказ вместо тихой описательной трактовки.
    routing, _ = logs
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001")
    with pytest.raises(SystemExit, match="канонической форме"):
        la.append_routing("delegated", "builder", model="sonnet", task_id="T-002")
    assert len(routing.read_text(encoding="utf-8").splitlines()) == 1


def test_non_delegated_fresh_t_nnn_skips_sequence_check_and_jumps_max(logs):
    # t-010 (критик F-D по t-009): фиксируем ИНВАРИАНТ, а не желаемое —
    # гард последовательности бьёт только по delegated; accepted со свежим
    # t-NNN проходит без проверки и сдвигает max для последующих свежих id.
    routing, _ = logs
    la.append_routing("accepted", "builder", model="sonnet", task_id="t-050",
                      witness="pytest -q -> passed")
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-051")
    lines = routing.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[1])["task_id"] == "t-051"
    with pytest.raises(SystemExit, match="t-052"):
        la.append_routing("delegated", "builder", model="sonnet", task_id="t-002")
