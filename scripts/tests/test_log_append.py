"""Тесты scripts/log_append.py — каноничное добавление строк в журналы."""
from __future__ import annotations

import io
import json
import subprocess

import pytest

try:
    import log_append_d0076 as la
except ImportError:
    import log_append as la

import tier_measure


@pytest.fixture()
def logs(tmp_path, monkeypatch):
    routing = tmp_path / "logs" / "routing-log.jsonl"
    orch = tmp_path / "state" / "orchestrator-log.md"
    monkeypatch.setattr(la, "ROUTING_LOG", routing, raising=True)
    monkeypatch.setattr(la, "ORCH_LOG", orch, raising=True)
    # Порт-батч штаба: защита от «тихо-успешен вне среды» (_verify_environment)
    # требует, чтобы каталог журнала уже существовал И был частью git-репо —
    # tmp_path ни то, ни другое. Все поведенческие тесты этого файла проверяют
    # логику append_routing/append_orchestrator САМУ ПО СЕБЕ, не среду; стаб
    # держит её "валидной" здесь, отдельные тесты ниже проверяют
    # _verify_environment напрямую, без этого стаба.
    monkeypatch.setattr(la, "_verify_environment", lambda **kw: (True, ""), raising=True)
    return routing, orch


def test_routing_appends_json_line_with_ts(logs):
    routing, _ = logs
    la.main(["routing", "--event", "delegated", "--agent", "builder",
             "--model", "sonnet", "--task-id", "t-001",
             "--worker-ref", "wr-cli",
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
        la.append_routing("rejected", "builder", model="sonnet", by="opus",
                          task_id="t-003", attempt=1)
    with pytest.raises(SystemExit):  # failure_class вне enum
        la.append_routing("rejected", "builder", model="sonnet", by="opus",
                          task_id="t-003", attempt=1, failure_class="vibes")
    with pytest.raises(SystemExit):  # нет attempt
        la.append_routing("rejected", "builder", model="sonnet", by="opus",
                          task_id="t-003", failure_class="spec")
    la.append_routing("rejected", "builder", model="sonnet", by="opus",
                      task_id="t-003",
                      attempt=2, failure_class="capability", notes="причина")
    rec = json.loads(routing.read_text(encoding="utf-8"))
    assert rec["attempt"] == 2
    assert rec["failure_class"] == "capability"


def test_routing_accepted_builder_requires_witness(logs):
    # D-0052: accepted по builder без witness = самосертификация.
    routing, _ = logs
    with pytest.raises(SystemExit):
        la.append_routing("accepted", "builder", model="sonnet", by="opus",
                          task_id="t-004")
    la.append_routing("accepted", "builder", model="sonnet", by="opus",
                      task_id="t-004",
                      witness="python -m pytest scripts/tests -q -> 241 passed")
    rec = json.loads(routing.read_text(encoding="utf-8"))
    assert "241 passed" in rec["witness"]
    # scout принимается без witness (его след — Trail в дайджесте, D-0046);
    # by=sonnet проходит матрицу D-0058 (tier(sonnet)=1 > tier(scout)=0)
    la.append_routing("accepted", "scout", model="haiku", by="sonnet",
                      task_id="t-005")
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
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001", worker_ref="wr")
    la.append_routing("accepted", "builder", model="sonnet", by="opus",
                      task_id="t-001",
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
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001", worker_ref="wr")
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-002", worker_ref="wr")
    lines = routing.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[1])["task_id"] == "t-002"


def test_delegated_fresh_id_gap_or_lower_rejected_names_expected_id(logs):
    routing, _ = logs
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001", worker_ref="wr")
    with pytest.raises(SystemExit, match="t-002"):  # разрыв
        la.append_routing("delegated", "builder", model="sonnet", task_id="t-005", worker_ref="wr")
    with pytest.raises(SystemExit, match="t-002"):  # ниже ожидаемого, ранее не встречался
        la.append_routing("delegated", "builder", model="sonnet", task_id="t-000", worker_ref="wr")
    # ни один из отклонённых вызовов не дописался в журнал
    assert len(routing.read_text(encoding="utf-8").splitlines()) == 1


def test_delegated_continuation_after_rejected_or_escalated_passes(logs):
    routing, _ = logs
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001", worker_ref="wr")
    la.append_routing("rejected", "builder", model="sonnet", by="opus",
                      task_id="t-001",
                      attempt=1, failure_class="capability")
    # ретрай на тот же task_id тем же agent -- легально ТОЛЬКО с
    # attempt>=2 и существующим rejected (D-0058 порт, ветка "в")
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                      attempt=2, worker_ref="wr")
    # continuation другим ярусом (critic) -- легально без доп. флагов
    # (ветка "б")
    la.append_routing("escalated", "critic", model="opus", task_id="t-001")
    la.append_routing("delegated", "critic", model="opus", task_id="t-001", worker_ref="wr")
    lines = routing.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 5
    # следующий свежий id всё ещё считается от t-001 (единственный t-NNN)
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-002", worker_ref="wr")
    assert len(routing.read_text(encoding="utf-8").splitlines()) == 6


def test_delegated_on_accepted_task_id_rejected_without_reopen_flag(logs):
    routing, _ = logs
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001", worker_ref="wr")
    la.append_routing("accepted", "builder", model="sonnet", by="opus",
                      task_id="t-001",
                      witness="pytest -q -> passed")
    with pytest.raises(SystemExit, match="t-001"):
        la.append_routing("delegated", "builder", model="sonnet", task_id="t-001", worker_ref="wr")
    assert len(routing.read_text(encoding="utf-8").splitlines()) == 2


def test_delegated_on_accepted_task_id_passes_with_reopen_flag(logs):
    routing, _ = logs
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001", worker_ref="wr")
    la.append_routing("accepted", "builder", model="sonnet", by="opus",
                      task_id="t-001",
                      witness="pytest -q -> passed")
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                      reopen_task="F-23: коллизия, повторное открытие осознанно",
                      worker_ref="wr")
    lines = routing.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    rec = json.loads(lines[-1])
    assert rec["task_id"] == "t-001"
    assert "reopen" in rec["notes"] and "F-23" in rec["notes"]


def test_delegated_empty_journal_expects_t001(logs):
    routing, _ = logs
    assert not routing.exists()
    with pytest.raises(SystemExit, match="t-001"):
        la.append_routing("delegated", "builder", model="sonnet", task_id="t-999", worker_ref="wr")
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001", worker_ref="wr")
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
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001", worker_ref="wr")
    la.append_routing("delegated", "test-maintainer", model="sonnet",
                      task_id="at-bug-005", worker_ref="wr")
    lines = routing.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[1])["task_id"] == "at-bug-005"


def test_delegated_substring_t_nn_inside_descriptive_id_treated_as_descriptive(logs):
    # Спека п.3 (t-009, попытка 2): id вроде "fix-t-12-encoding" содержит
    # substring "t-12", но НЕ full-match с ^t-(\d+)$ — значит трактуется как
    # описательный и проходит свободно как новый, без применения проверки
    # последовательности (и без влияния на последующий max(t-NNN)).
    routing, _ = logs
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001", worker_ref="wr")
    la.append_routing("delegated", "test-maintainer", model="sonnet",
                      task_id="fix-t-12-encoding", worker_ref="wr")
    lines = routing.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[1])["task_id"] == "fix-t-12-encoding"
    # substring "t-12" не должен был войти в подсчёт max(t-NNN): следующий
    # свежий последовательный id всё ещё t-002, а не t-013.
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-002", worker_ref="wr")
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
    la.append_routing("rejected", "test-maintainer", model="sonnet", by="opus",
                      task_id="at-bug-003", attempt=1, failure_class="capability")
    la.append_routing("delegated", "test-maintainer", model="sonnet",
                      task_id="at-bug-003", worker_ref="wr")
    assert len(routing.read_text(encoding="utf-8").splitlines()) == 2


def test_delegated_id_with_spaces_stripped(logs):
    # t-010 (критик F-C по t-009): " t-002 " раньше молча уходил в
    # описательную ветку; теперь id нормализуется strip'ом и проходит
    # проверку последовательности, в журнал пишется очищенным.
    routing, _ = logs
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001", worker_ref="wr")
    la.append_routing("delegated", "builder", model="sonnet", task_id=" t-002 ", worker_ref="wr")
    lines = routing.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[1])["task_id"] == "t-002"


def test_delegated_fresh_sequential_id_fails_on_wrong_case(logs):
    # t-010 (критик F-C): "T-002" похож на последовательность, но не в
    # канонической форме — явный отказ вместо тихой описательной трактовки.
    routing, _ = logs
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001", worker_ref="wr")
    with pytest.raises(SystemExit, match="канонической форме"):
        la.append_routing("delegated", "builder", model="sonnet", task_id="T-002", worker_ref="wr")
    assert len(routing.read_text(encoding="utf-8").splitlines()) == 1


def test_non_delegated_fresh_t_nnn_skips_sequence_check_and_jumps_max(logs):
    # t-010 (критик F-D по t-009): фиксируем ИНВАРИАНТ, а не желаемое —
    # гард последовательности бьёт только по delegated; accepted со свежим
    # t-NNN проходит без проверки и сдвигает max для последующих свежих id.
    routing, _ = logs
    la.append_routing("accepted", "builder", model="sonnet", by="opus",
                      task_id="t-050",
                      witness="pytest -q -> passed")
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-051", worker_ref="wr")
    lines = routing.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[1])["task_id"] == "t-051"
    with pytest.raises(SystemExit, match="t-052"):
        la.append_routing("delegated", "builder", model="sonnet", task_id="t-002", worker_ref="wr")


# D-0058 (порт OS-репо, task_id journal-port-by-basis): поле 'by' и матрица
# приёмки для accepted/rejected; ветки continuation/retry для delegated на
# СУЩЕСТВУЮЩИЙ открытый task_id.

def test_by_required_for_accepted_and_rejected(logs):
    routing, _ = logs
    with pytest.raises(SystemExit, match="--by"):
        la.append_routing("accepted", "builder", model="sonnet",
                          task_id="t-001", witness="pytest -q -> passed")
    with pytest.raises(SystemExit, match="--by"):
        la.append_routing("rejected", "builder", model="sonnet",
                          task_id="t-001", attempt=1, failure_class="capability")
    assert not routing.exists()


def test_by_not_required_for_delegated_or_escalated(logs):
    # 'by' -- самодекларация ПРИНИМАЮЩЕГО; delegated/escalated его не несут.
    routing, _ = logs
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001", worker_ref="wr")
    la.append_routing("escalated", "critic", model="opus", task_id="t-001")
    lines = routing.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert "by" not in json.loads(lines[0])
    assert "by" not in json.loads(lines[1])


def test_accepted_matrix_passes_when_by_tier_strictly_above_agent(logs):
    routing, _ = logs
    # agent=builder -> tier sonnet(1); by=opus -> tier(2) > 1: проходит.
    la.append_routing("accepted", "builder", model="sonnet", by="opus",
                      task_id="t-001", witness="pytest -q -> passed")
    rec = json.loads(routing.read_text(encoding="utf-8"))
    assert rec["by"] == "opus"


def test_accepted_matrix_fails_when_by_tier_not_above_agent_and_no_basis(logs):
    routing, _ = logs
    # agent=builder -> tier sonnet(1); by=sonnet (равный ярус) без basis.
    with pytest.raises(SystemExit, match="D-0058"):
        la.append_routing("accepted", "builder", model="sonnet", by="sonnet",
                          task_id="t-001", witness="pytest -q -> passed")
    # by ниже яруса исполнителя (haiku < sonnet) без basis -- тоже отказ.
    with pytest.raises(SystemExit, match="D-0058"):
        la.append_routing("accepted", "builder", model="sonnet", by="haiku",
                          task_id="t-001", witness="pytest -q -> passed")
    assert not routing.exists()


def test_accepted_matrix_basis_rescues_non_strict_tier(logs):
    routing, _ = logs
    # tier(by=sonnet) не строго выше tier(builder=sonnet), но basis=critic
    # (Sonnet-координатор принимает Sonnet-воркера только с critic-входом,
    # CLAUDE.md «Роль != ярус») -- спасает.
    la.append_routing("accepted", "builder", model="sonnet", by="sonnet",
                      basis="critic", task_id="t-001",
                      witness="pytest -q -> passed")
    rec = json.loads(routing.read_text(encoding="utf-8"))
    assert rec["basis"] == "critic"
    la.append_routing("accepted", "builder", model="sonnet", by="sonnet",
                      basis="queued-to-lead", task_id="t-002",
                      witness="pytest -q -> passed")
    lines = routing.read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[1])["basis"] == "queued-to-lead"


def test_accepted_matrix_invalid_basis_does_not_rescue(logs):
    routing, _ = logs
    with pytest.raises(SystemExit, match="D-0058"):
        la.append_routing("accepted", "builder", model="sonnet", by="sonnet",
                          basis="vibes", task_id="t-001",
                          witness="pytest -q -> passed")
    assert not routing.exists()


def test_accepted_matrix_agent_lead_skips_matrix(logs):
    # agent=lead -- матрица D-0058 не применяется, 'by' сам по себе
    # достаточен независимо от tier.
    routing, _ = logs
    la.append_routing("accepted", "lead", model="fable", by="haiku",
                      task_id="t-001")
    rec = json.loads(routing.read_text(encoding="utf-8"))
    assert rec["by"] == "haiku"
    assert "basis" not in rec


def test_accepted_matrix_qa_agent_reads_tier_from_frontmatter(logs):
    # test-automator: .claude/agents/test-automator.md -> model: sonnet
    # (frontmatter, read-only). tier(sonnet)=1: by=opus(2) проходит,
    # by=sonnet(1) без basis -- нет.
    routing, _ = logs
    la.append_routing("accepted", "test-automator", model="sonnet", by="opus",
                      task_id="t-001")
    with pytest.raises(SystemExit, match="D-0058"):
        la.append_routing("accepted", "test-automator", model="sonnet",
                          by="sonnet", task_id="t-002")
    assert len(routing.read_text(encoding="utf-8").splitlines()) == 1


def test_accepted_matrix_unknown_agent_warns_and_by_suffices(logs, capsys):
    # Агент вне статического списка и без .claude/agents/<agent>.md ->
    # предупреждение в stderr, генератор НЕ блокирует (будущий агент
    # конвейера, ещё не описанный).
    routing, _ = logs
    la.append_routing("accepted", "future-qa-agent", model="sonnet",
                      by="haiku", task_id="t-001")
    rec = json.loads(routing.read_text(encoding="utf-8"))
    assert rec["by"] == "haiku"
    captured = capsys.readouterr()
    assert "WARNING" in captured.err
    assert "future-qa-agent" in captured.err


def test_accepted_matrix_frontmatter_present_but_model_unrecognized_warns(
        logs, capsys, tmp_path, monkeypatch):
    # Батч-пункт 1б: "frontmatter агента с нераспознанным model" -- отдельная
    # от уже покрытой test_accepted_matrix_unknown_agent_warns_and_by_suffices
    # ветка. Та проверяет агента БЕЗ файла .claude/agents/<agent>.md вовсе
    # (_read_agent_frontmatter_model возвращает None из-за OSError на
    # чтении). Эта проверяет агента, у которого файл ЕСТЬ и frontmatter
    # парсится, но значение поля model не входит в TIER_ORDER (ни haiku, ни
    # sonnet, ни opus, ни fable) -- код доходит до того же предупреждения
    # (_resolve_agent_tier: `if model in TIER_ORDER: return model` не
    # срабатывает, обе ветки падают в один _warn_stderr) другим путём.
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "custom-qa-agent.md").write_text(
        "---\nname: custom-qa-agent\nmodel: gpt-4\ndescription: x\n---\n\nбody\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(la, "AGENTS_DIR", agents_dir, raising=True)

    routing, _ = logs
    la.append_routing("accepted", "custom-qa-agent", model="sonnet",
                      by="haiku", task_id="t-001")
    rec = json.loads(routing.read_text(encoding="utf-8"))
    assert rec["by"] == "haiku"
    captured = capsys.readouterr()
    assert "WARNING" in captured.err
    assert "custom-qa-agent" in captured.err


def test_rejected_by_present_no_tier_check(logs):
    # Буквальное чтение спеки OS-репо: rejected несёт 'by' без tier/basis-
    # проверки -- любой by (в т.ч. ниже яруса исполнителя) легален.
    routing, _ = logs
    la.append_routing("rejected", "builder", model="sonnet", by="haiku",
                      task_id="t-001", attempt=1, failure_class="capability")
    rec = json.loads(routing.read_text(encoding="utf-8"))
    assert rec["by"] == "haiku"


def test_delegated_retry_same_agent_open_task_requires_attempt_and_rejected(logs):
    # Ветка "в": agent совпадает с предыдущим delegated -- легально ТОЛЬКО
    # с attempt>=2 И существующим rejected по этому task_id.
    routing, _ = logs
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001", worker_ref="wr")
    # ни attempt, ни rejected -- дубль-паттерн (ветка "г").
    with pytest.raises(SystemExit, match="дубль"):
        la.append_routing("delegated", "builder", model="sonnet", task_id="t-001", worker_ref="wr")
    # attempt>=2, но rejected по-прежнему нет -- всё ещё отказ.
    with pytest.raises(SystemExit, match="дубль"):
        la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                          attempt=2, worker_ref="wr")
    assert len(routing.read_text(encoding="utf-8").splitlines()) == 1
    la.append_routing("rejected", "builder", model="sonnet", by="opus",
                      task_id="t-001", attempt=1, failure_class="capability")
    # теперь rejected есть -- attempt>=2 достаточно (ветка "в", легально).
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                      attempt=2, worker_ref="wr")
    assert len(routing.read_text(encoding="utf-8").splitlines()) == 3


def test_rejected_after_accepted_reopens_task_without_reopen_flag(logs, capsys):
    # Батч-пункт 1а (по признанной семантике AO3, CLAUDE.md «журнал
    # маршрутизации»: rejected/defect_found ПОСЛЕ accepted возвращает задачу
    # в «открыта» — следствие reopen-семантики AO3). Проверено чтением кода
    # ДО написания теста: гейт "task_id уже закрыт, нужен --reopen-task"
    # закодирован ТОЛЬКО внутри ветки `event == "delegated"` (append_routing);
    # событие rejected эту ветку не проходит вовсе и пишется без всякой
    # проверки предыдущего lifecycle-события. Фактическое поведение:
    routing, _ = logs
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                      worker_ref="wr")
    la.append_routing("accepted", "builder", model="sonnet", by="opus",
                      task_id="t-001", witness="pytest -q -> passed")
    # rejected после accepted проходит БЕЗ --reopen-task (в отличие от
    # delegated, для которого это было бы SystemExit).
    la.append_routing("rejected", "builder", model="sonnet", by="opus",
                      task_id="t-001", attempt=1, failure_class="capability")
    lines = routing.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    assert json.loads(lines[-1])["event"] == "rejected"

    # open-dispatches: rejected не считается "открытым ДИСПАТЧЕМ" (никто не
    # делегирован прямо сейчас) -- lifecycle-скан open-dispatches помечает
    # открытым только task_id, чьё ПОСЛЕДНЕЕ событие -- delegated.
    capsys.readouterr()
    la.main(["open-dispatches"])
    assert "t-001" not in capsys.readouterr().out

    # Но для ГЕЙТА повторного delegated задача снова "открыта": следующий
    # delegated по t-001 НЕ требует --reopen-task (последнее событие --
    # rejected, не accepted) -- ветка continuation/retry применяется как к
    # обычной открытой задаче (attempt>=2 + существующий rejected).
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                      attempt=2, worker_ref="wr-2")
    lines = routing.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 4
    assert "reopen" not in json.loads(lines[-1]).get("notes", "")

    # После повторного delegated open-dispatches снова видит t-001 открытым.
    la.main(["open-dispatches"])
    assert "OPEN DISPATCH: t-001 agent=builder since" in capsys.readouterr().out


def test_delegated_continuation_different_agent_open_task_no_flags_needed(logs):
    # Ветка "б": agent новой строки отличается от agent ВСЕХ предыдущих
    # delegated этого task_id -- легально без attempt/rejected.
    routing, _ = logs
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001", worker_ref="wr")
    la.append_routing("delegated", "critic", model="opus", task_id="t-001", worker_ref="wr")
    lines = routing.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[1])["agent"] == "critic"


# D-0076 (порт OS-репо, инцидент F-44): --worker-ref обязателен для delegated
# (фантомная запись без запущенного воркера иначе неотличима от честной),
# и подкоманда open-dispatches -- скан незакрытых delegated по журналу.

def test_worker_ref_required_for_delegated(logs):
    routing, _ = logs
    with pytest.raises(SystemExit, match="worker-ref"):
        la.append_routing("delegated", "builder", model="sonnet", task_id="t-001")
    with pytest.raises(SystemExit, match="worker-ref"):
        la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                          worker_ref="   ")
    assert not routing.exists()
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                      worker_ref="job:bg-4471")
    rec = json.loads(routing.read_text(encoding="utf-8"))
    assert rec["worker_ref"] == "job:bg-4471"


def test_worker_ref_not_required_for_accepted_rejected_and_other_events(logs):
    routing, _ = logs
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                      worker_ref="wr")
    la.append_routing("accepted", "builder", model="sonnet", by="opus",
                      task_id="t-001", witness="pytest -q -> passed")
    la.append_routing("rejected", "builder", model="sonnet", by="opus",
                      task_id="t-002", attempt=1, failure_class="capability")
    la.append_routing("dispatch_skipped", "scout", category="recon",
                      notes="точечная сверка известных файлов")
    lines = routing.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 4
    for line in lines[1:]:
        assert "worker_ref" not in json.loads(line)


def test_open_dispatches_empty_journal_prints_nothing(logs, capsys):
    routing, _ = logs
    assert not routing.exists()
    exit_code = la.main(["open-dispatches"])
    assert exit_code == 0
    assert capsys.readouterr().out == ""


def test_open_dispatches_shows_open_delegated(logs, capsys):
    routing, _ = logs
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                      worker_ref="wr")
    exit_code = la.main(["open-dispatches"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "OPEN DISPATCH: t-001 agent=builder since" in out


def test_open_dispatches_closed_by_accepted_not_shown(logs, capsys):
    routing, _ = logs
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                      worker_ref="wr")
    la.append_routing("accepted", "builder", model="sonnet", by="opus",
                      task_id="t-001", witness="pytest -q -> passed")
    exit_code = la.main(["open-dispatches"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "t-001" not in out
    assert out == ""


def test_open_dispatches_reopen_chain_is_open(logs, capsys):
    # delegated -> accepted (закрыт) -> delegated --reopen-task (снова открыт):
    # AO3-специфика (reopen легален), в отличие от эталонного репо, где
    # "accepted закрывает навсегда" -- здесь это правило НЕ действует.
    routing, _ = logs
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                      worker_ref="wr")
    la.append_routing("accepted", "builder", model="sonnet", by="opus",
                      task_id="t-001", witness="pytest -q -> passed")
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                      worker_ref="wr-reopen",
                      reopen_task="F-23: коллизия, повторное открытие осознанно")
    exit_code = la.main(["open-dispatches"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "OPEN DISPATCH: t-001 agent=builder since" in out


def test_open_dispatches_retry_chain_is_open(logs, capsys):
    # delegated -> rejected -> delegated (attempt=2, ретрай тем же agent):
    # задача остаётся открытой на всём протяжении, включая ретрай.
    routing, _ = logs
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                      worker_ref="wr")
    la.append_routing("rejected", "builder", model="sonnet", by="opus",
                      task_id="t-001", attempt=1, failure_class="capability")
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                      attempt=2, worker_ref="wr-retry")
    exit_code = la.main(["open-dispatches"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "OPEN DISPATCH: t-001 agent=builder since" in out


def test_open_dispatches_multiple_open_ordered_oldest_first(logs, capsys):
    routing, _ = logs
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                      worker_ref="wr-a")
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-002",
                      worker_ref="wr-b")
    la.append_routing("accepted", "builder", model="sonnet", by="opus",
                      task_id="t-002", witness="pytest -q -> passed")
    la.append_routing("delegated", "critic", model="opus", task_id="t-003",
                      worker_ref="wr-c")
    exit_code = la.main(["open-dispatches"])
    assert exit_code == 0
    out = capsys.readouterr().out.splitlines()
    # t-002 закрыт (accepted) и не должен фигурировать; t-001 и t-003 открыты,
    # t-001 -- старейший (продолжает быть delegated дольше).
    assert len(out) == 2
    assert out[0].startswith("OPEN DISPATCH: t-001 ")
    assert out[1].startswith("OPEN DISPATCH: t-003 ")


# Порт-батч штаба (D:\Improving_AI\Operating-System-for-LLMs): CLI-флаг
# --replaces-worker -- эталон логики: правило 9в2 tools/journal_validator.py
# OS-репо (маркер replaces_worker:<хэндл> в notes, легализующий повторный
# delegated по ОТКРЫТОМУ task_id тем же agent'ом БЕЗ вердикта -- замена
# умершего воркера, не ретрай правила 6).

def test_replaces_worker_valid_ref_legalizes_redelegation_without_attempt(logs):
    routing, _ = logs
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                      worker_ref="wr-A")
    # Тот же agent, задача открыта (нет accepted/rejected), нет --attempt --
    # без --replaces-worker это был бы запрещённый дубль-паттерн (см.
    # test_delegated_retry_same_agent_open_task_requires_attempt_and_rejected).
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                      worker_ref="wr-B", replaces_worker="wr-A",
                      notes="воркер завис, замена без вердикта")
    lines = routing.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    rec = json.loads(lines[1])
    assert rec["worker_ref"] == "wr-B"
    assert "attempt" not in rec
    assert "replaces_worker:wr-A" in rec["notes"]
    assert "воркер завис" in rec["notes"]


def test_replaces_worker_marker_not_duplicated_if_already_in_notes(logs):
    routing, _ = logs
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                      worker_ref="wr-A")
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                      worker_ref="wr-B", replaces_worker="wr-A",
                      notes="уже несу маркер replaces_worker:wr-A сама по себе")
    rec = json.loads(routing.read_text(encoding="utf-8").splitlines()[1])
    assert rec["notes"].count("replaces_worker:wr-A") == 1


def test_replaces_worker_mismatched_ref_rejected(logs):
    routing, _ = logs
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                      worker_ref="wr-A")
    with pytest.raises(SystemExit, match="replaces-worker"):
        la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                          worker_ref="wr-C", replaces_worker="wr-B")
    # отклонённый вызов не дописался
    assert len(routing.read_text(encoding="utf-8").splitlines()) == 1


def test_replaces_worker_with_attempt_together_rejected(logs):
    # Штабная семантика (спека порт-батча): замена умершего воркера -- НЕ
    # ретрай, поэтому --replaces-worker и --attempt взаимоисключающие --
    # смешение двух легальных оснований в одной строке запрещено явной
    # ошибкой, а не тихо игнорируется.
    routing, _ = logs
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                      worker_ref="wr-A")
    with pytest.raises(SystemExit, match="взаимоисключающие"):
        la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                          worker_ref="wr-B", replaces_worker="wr-A", attempt=2)
    assert len(routing.read_text(encoding="utf-8").splitlines()) == 1


def test_replaces_worker_finds_ref_among_any_prior_agent_delegated(logs):
    # Эталон (journal_validator.py, task_worker_refs): прежний worker_ref
    # ищется среди ВСЕХ delegated этого task_id, не только того же agent.
    routing, _ = logs
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                      worker_ref="wr-A")
    la.append_routing("delegated", "critic", model="opus", task_id="t-001",
                      worker_ref="wr-critic")  # continuation, ветка "б"
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                      worker_ref="wr-B", replaces_worker="wr-critic")
    lines = routing.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    assert "replaces_worker:wr-critic" in json.loads(lines[2])["notes"]


def test_replaces_worker_ignored_when_not_applicable_branch(logs):
    # На СВЕЖЕМ task_id (новая задача) --replaces-worker просто не
    # консультируется -- симметрично с --reopen-task, который тоже не
    # проверяется вне своей ветки (задача закрыта accepted).
    routing, _ = logs
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                      worker_ref="wr-A", replaces_worker="wr-nonexistent")
    rec = json.loads(routing.read_text(encoding="utf-8"))
    assert "replaces_worker" not in rec.get("notes", "")


# Порт-батч штаба: защита от «тихо-успешен вне среды» (_verify_environment).
# Тесты ниже НЕ используют стаб из фикстуры `logs` -- проверяют функцию
# напрямую на реальной файловой структуре tmp_path.

def test_verify_environment_fails_when_require_dir_missing(tmp_path):
    missing = tmp_path / "logs"
    ok, msg = la._verify_environment(require_dir=missing)
    assert ok is False
    assert "не существует" in msg


def test_verify_environment_fails_when_dir_exists_but_not_git_repo(tmp_path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    ok, msg = la._verify_environment(require_dir=logs_dir)
    assert ok is False
    assert "git-репозитория" in msg


def test_verify_environment_passes_inside_real_git_repo(tmp_path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True)
    ok, msg = la._verify_environment(require_dir=logs_dir)
    assert ok is True
    assert msg == ""


def test_append_routing_refuses_outside_environment_without_stub(tmp_path, monkeypatch):
    # Смок сквозь append_routing() целиком (не только _verify_environment):
    # ROUTING_LOG указывает в tmp_path, который не git-репо и logs/ не
    # существует -- отказ ДО записи, файл не создаётся вовсе (в отличие от
    # прежнего поведения, где _append_line тихо делал mkdir(parents=True)
    # в любом месте).
    routing = tmp_path / "logs" / "routing-log.jsonl"
    monkeypatch.setattr(la, "ROUTING_LOG", routing, raising=True)
    with pytest.raises(SystemExit, match="деплой не распознан"):
        la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                          worker_ref="wr")
    assert not routing.exists()
    assert not routing.parent.exists()


def test_append_orchestrator_refuses_outside_environment_without_stub(tmp_path, monkeypatch):
    orch = tmp_path / "state" / "orchestrator-log.md"
    monkeypatch.setattr(la, "ORCH_LOG", orch, raising=True)
    with pytest.raises(SystemExit, match="деплой не распознан"):
        la.append_orchestrator(["Правило X", "test-automator", "TC-050", "OK"])
    assert not orch.exists()


def test_append_routing_succeeds_when_dir_exists_and_is_git_repo(tmp_path, monkeypatch):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True)
    routing = logs_dir / "routing-log.jsonl"
    monkeypatch.setattr(la, "ROUTING_LOG", routing, raising=True)
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                      worker_ref="wr")
    assert routing.exists()
    rec = json.loads(routing.read_text(encoding="utf-8"))
    assert rec["task_id"] == "t-001"


# Порт-батч штаба D-0083 (D:\Improving_AI\Operating-System-for-LLMs,
# tools/tier_echo.py, CLAUDE.md правило 4в): замер фактической модели
# воркера по jsonl-транскрипту поверх самодекларации 'model'. Тесты
# monkeypatch'ат tier_measure._projects_dir на tmp_path -- log_append.py
# импортирует тот же объект модуля tier_measure (import tier_measure),
# поэтому патч виден и внутри append_routing.

def _write_fixture_transcript(root, agent_id, models):
    path = (root / "proj" / "sess" / "subagents" / f"agent-{agent_id}.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for model in models:
            f.write(json.dumps({"type": "assistant",
                                 "message": {"model": model}},
                                ensure_ascii=False) + "\n")
    return path


def test_tier_measure_mismatch_warns_stderr_but_still_writes(logs, tmp_path,
                                                              monkeypatch, capsys):
    routing, _ = logs
    agent_id = "c03f9de7301509d98"
    _write_fixture_transcript(tmp_path, agent_id, ["opus", "opus"])
    monkeypatch.setattr(tier_measure, "_projects_dir", lambda: tmp_path,
                        raising=True)

    la.append_routing("delegated", "builder", model="fable", task_id="t-001",
                      worker_ref=f"agent:{agent_id}")

    captured = capsys.readouterr()
    assert "TIER MEASURE" in captured.err
    assert "MISMATCH" in captured.err
    assert "opus=2" in captured.err
    assert "fable" in captured.err
    # запись в журнал происходит НЕЗАВИСИМО от предупреждения (warn не
    # блокирует -- не SystemExit).
    lines = routing.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["model"] == "fable"


def test_tier_measure_match_is_silent(logs, tmp_path, monkeypatch, capsys):
    routing, _ = logs
    agent_id = "d04a0ef8412610e09"
    _write_fixture_transcript(tmp_path, agent_id, ["sonnet", "sonnet"])
    monkeypatch.setattr(tier_measure, "_projects_dir", lambda: tmp_path,
                        raising=True)

    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                      worker_ref=f"agent:{agent_id}")

    captured = capsys.readouterr()
    assert "TIER MEASURE" not in captured.err
    assert len(routing.read_text(encoding="utf-8").splitlines()) == 1


# Критик-вход attempt 2 (Q4, обязательный пункт): фикстуры выше пишут в
# message.model короткие ярусные слова ("opus", "sonnet"), а реальный
# транскрипт харнесса несёт ПОЛНЫЙ id модели (напр. "claude-sonnet-5",
# "claude-opus-4-8") при заявленном коротком слове в 'model' журнала --
# боевой путь matched-проверки в _check_tier_measurement это
# `model_lower in m.lower()` (substring), а тесты выше с короткими словами
# в фикстуре прошли бы и при регрессии substring -> точное равенство,
# что дало бы ложный MISMATCH на КАЖДОМ корректном боевом диспатче
# (транскрипт харнесса никогда не несёт короткое слово буквально).

def test_tier_measure_match_is_silent_with_realistic_full_model_id(
        logs, tmp_path, monkeypatch, capsys):
    routing, _ = logs
    agent_id = "aa1b2c3d4e5f60718"
    _write_fixture_transcript(tmp_path, agent_id, ["claude-sonnet-5"])
    monkeypatch.setattr(tier_measure, "_projects_dir", lambda: tmp_path,
                        raising=True)

    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                      worker_ref=f"agent:{agent_id}")

    captured = capsys.readouterr()
    assert "TIER MEASURE" not in captured.err
    assert len(routing.read_text(encoding="utf-8").splitlines()) == 1


def test_tier_measure_mismatch_with_realistic_full_model_id(
        logs, tmp_path, monkeypatch, capsys):
    routing, _ = logs
    agent_id = "bb2c3d4e5f607182a"
    _write_fixture_transcript(tmp_path, agent_id, ["claude-opus-4-8"])
    monkeypatch.setattr(tier_measure, "_projects_dir", lambda: tmp_path,
                        raising=True)

    la.append_routing("delegated", "builder", model="fable", task_id="t-001",
                      worker_ref=f"agent:{agent_id}")

    captured = capsys.readouterr()
    assert "TIER MEASURE" in captured.err
    assert "MISMATCH" in captured.err
    assert "claude-opus-4-8" in captured.err
    assert len(routing.read_text(encoding="utf-8").splitlines()) == 1


def test_tier_measure_partial_mismatch_warns_informational_without_mismatch_label(
        logs, tmp_path, monkeypatch, capsys):
    # Слово яруса встречается (sonnet), но транскрипт несёт и другие модели
    # (частичная mid-worker подмена) -- информационное предупреждение, БЕЗ
    # метки MISMATCH (это может быть легитимный continuation, судит сессия).
    routing, _ = logs
    agent_id = "e05b1af9523721f1a"
    _write_fixture_transcript(tmp_path, agent_id, ["sonnet", "opus"])
    monkeypatch.setattr(tier_measure, "_projects_dir", lambda: tmp_path,
                        raising=True)

    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                      worker_ref=f"agent:{agent_id}")

    captured = capsys.readouterr()
    assert "TIER MEASURE" in captured.err
    assert "MISMATCH" not in captured.err
    assert len(routing.read_text(encoding="utf-8").splitlines()) == 1


def test_tier_measure_missing_transcript_is_silent(logs, tmp_path, monkeypatch,
                                                    capsys):
    routing, _ = logs
    monkeypatch.setattr(tier_measure, "_projects_dir", lambda: tmp_path,
                        raising=True)

    la.append_routing("delegated", "builder", model="fable", task_id="t-001",
                      worker_ref="agent:doesnotexist")

    captured = capsys.readouterr()
    assert "TIER MEASURE" not in captured.err
    assert len(routing.read_text(encoding="utf-8").splitlines()) == 1


def test_tier_measure_non_transcript_worker_ref_forms_are_silent(logs, tmp_path,
                                                                  monkeypatch,
                                                                  capsys):
    # worker_ref в конвенциях этого репо (cli:/job:/retro:/описательная
    # строка) не несёт детерминированного пути к транскрипту -- замер
    # тихо пропускается, точно так же, как отсутствующий транскрипт.
    routing, _ = logs
    monkeypatch.setattr(tier_measure, "_projects_dir", lambda: tmp_path,
                        raising=True)

    la.append_routing("delegated", "builder", model="fable", task_id="t-001",
                      worker_ref="job:bg-4471")

    captured = capsys.readouterr()
    assert "TIER MEASURE" not in captured.err
    assert len(routing.read_text(encoding="utf-8").splitlines()) == 1


def test_tier_measure_not_applied_to_events_outside_the_four(logs, tmp_path,
                                                               monkeypatch,
                                                               capsys):
    # dispatch_skipped не входит в TIER_MEASURED_EVENTS -- замер не
    # запускается вовсе, даже если бы worker_ref был на него похож (само
    # событие не несёт worker_ref в текущей CLI-схеме, но проверяем и
    # событийный гейт отдельно от gate по worker_ref/model).
    routing, _ = logs
    agent_id = "f06c2bfa634832f2b"
    _write_fixture_transcript(tmp_path, agent_id, ["opus"])
    monkeypatch.setattr(tier_measure, "_projects_dir", lambda: tmp_path,
                        raising=True)

    la.append_routing("dispatch_skipped", "scout", category="recon",
                      notes="точечная сверка известных файлов")

    captured = capsys.readouterr()
    assert "TIER MEASURE" not in captured.err
    assert len(routing.read_text(encoding="utf-8").splitlines()) == 1


def test_tier_measure_accepted_without_worker_ref_is_silent(logs, tmp_path,
                                                             monkeypatch, capsys):
    # accepted/rejected могут не нести worker_ref (спека п.2) -- замер
    # тихо пропускается по отсутствию worker_ref, не по форме.
    routing, _ = logs
    monkeypatch.setattr(tier_measure, "_projects_dir", lambda: tmp_path,
                        raising=True)

    la.append_routing("accepted", "builder", model="fable", by="opus",
                      task_id="t-001", witness="pytest -q -> passed")

    captured = capsys.readouterr()
    assert "TIER MEASURE" not in captured.err
    assert len(routing.read_text(encoding="utf-8").splitlines()) == 1


def test_tier_measure_broken_transcript_line_does_not_break_journal_write(
        logs, tmp_path, monkeypatch, capsys):
    # Сбой замера (здесь: транскрипт целиком из битых строк -> нет ни
    # одной измеренной модели) не должен ронять запись журнала.
    routing, _ = logs
    agent_id = "a07d2cfb745943a3c"
    path = (tmp_path / "proj" / "sess" / "subagents"
             / f"agent-{agent_id}.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not valid json at all\n", encoding="utf-8")
    monkeypatch.setattr(tier_measure, "_projects_dir", lambda: tmp_path,
                        raising=True)

    la.append_routing("delegated", "builder", model="fable", task_id="t-001",
                      worker_ref=f"agent:{agent_id}")

    captured = capsys.readouterr()
    assert "TIER MEASURE" not in captured.err
    assert len(routing.read_text(encoding="utf-8").splitlines()) == 1
