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


def test_accepted_matrix_basis_critic_rescues_sonnet_class_by_sonnet(logs):
    routing, _ = logs
    # tier(by=sonnet) не строго выше tier(builder=sonnet), но basis=critic
    # (Sonnet-координатор принимает Sonnet-воркера только с critic-входом,
    # CLAUDE.md «Роль != ярус») -- спасает.
    la.append_routing("accepted", "builder", model="sonnet", by="sonnet",
                      basis="critic", task_id="t-001",
                      witness="pytest -q -> passed")
    rec = json.loads(routing.read_text(encoding="utf-8"))
    assert rec["basis"] == "critic"


def test_accepted_matrix_queued_to_lead_illegal_for_sonnet_class_by_sonnet(logs):
    # Калибровка №4 (2026-07-28): ПРЕЦЕДЕНТНЫЙ класс (шапки (5)/(9)
    # HANDOFF) — Sonnet-координатор принимает Sonnet-класс через
    # basis=queued-to-lead, тогда как матрица D-0058 для этой пары требует
    # ИМЕННО critic. Раньше членство в BASIS_VALUES это пропускало; теперь
    # решает полная пара (tier(agent), tier(by)).
    routing, _ = logs
    with pytest.raises(SystemExit, match="нелегален для пары"):
        la.append_routing("accepted", "builder", model="sonnet", by="sonnet",
                          basis="queued-to-lead", task_id="t-001",
                          witness="pytest -q -> passed")
    assert not routing.exists()


def test_accepted_matrix_pair_gate_applies_to_frontmatter_qa_agents(logs):
    # Прецедентный класс включал QA-агентов (fix-verifier/test-maintainer/
    # test-designer): tier из frontmatter проходит ту же парную проверку.
    routing, _ = logs
    with pytest.raises(SystemExit, match="нелегален для пары"):
        la.append_routing("accepted", "test-automator", model="sonnet",
                          by="sonnet", basis="queued-to-lead", task_id="t-001")
    la.append_routing("accepted", "test-automator", model="sonnet",
                      by="sonnet", basis="critic", task_id="t-001")
    assert len(routing.read_text(encoding="utf-8").splitlines()) == 1


def test_accepted_matrix_queued_to_lead_legal_for_opus_class(logs):
    # (opus, sonnet) и (opus, opus): critic не покрывает равного себе —
    # очередь полного Lead и есть штатный basis (образец: приёмка вердикта
    # критика Sonnet-сессией (9) 2026-07-24 — легальна и ратифицирована).
    routing, _ = logs
    la.append_routing("accepted", "critic", model="opus", by="sonnet",
                      basis="queued-to-lead", task_id="t-001")
    la.append_routing("accepted", "critic", model="opus", by="opus",
                      basis="queued-to-lead", task_id="t-002")
    lines = routing.read_text(encoding="utf-8").splitlines()
    assert [json.loads(x)["basis"] for x in lines] == ["queued-to-lead"] * 2


def test_accepted_matrix_critic_basis_illegal_for_opus_class(logs):
    # Граница сверху (правило 11: тест на границе): opus-класс не
    # легализуется critic-входом — критик не ревьюит равного себе.
    routing, _ = logs
    with pytest.raises(SystemExit, match="нелегален для пары"):
        la.append_routing("accepted", "critic", model="opus", by="sonnet",
                          basis="critic", task_id="t-001")
    with pytest.raises(SystemExit, match="нелегален для пары"):
        la.append_routing("accepted", "critic", model="opus", by="opus",
                          basis="critic", task_id="t-001")
    assert not routing.exists()


def test_accepted_matrix_no_basis_rescues_coordinator_below_sonnet(logs):
    # Граница снизу (правило 11: за границей): координация ниже Sonnet не
    # предусмотрена матрицей — by=haiku не легализуется никаким basis.
    routing, _ = logs
    for basis in ("critic", "queued-to-lead"):
        with pytest.raises(SystemExit, match="D-0058"):
            la.append_routing("accepted", "scout", model="haiku", by="haiku",
                              basis=basis, task_id="t-001")
        with pytest.raises(SystemExit, match="D-0058"):
            la.append_routing("accepted", "builder", model="sonnet",
                              by="haiku", basis=basis, task_id="t-001",
                              witness="pytest -q -> passed")
    assert not routing.exists()


def test_accepted_matrix_strict_tier_short_circuits_before_basis(logs):
    # Пин порядка коротких замыканий (fix 7 вердикта calibration-4-basis-
    # gate): при tier(by) СТРОГО выше tier(agent) запись проходит по tier
    # ДО парной проверки basis — «неправильный» для пары basis не
    # отклоняется (он информационный). Это намеренная семантика.
    routing, _ = logs
    la.append_routing("accepted", "builder", model="sonnet", by="opus",
                      basis="queued-to-lead", task_id="t-001",
                      witness="pytest -q -> passed")
    rec = json.loads(routing.read_text(encoding="utf-8"))
    assert rec["basis"] == "queued-to-lead"


def test_accepted_matrix_opus_agent_by_fable_passes_without_basis(logs):
    # Пин границы: opus-ярусный агент, принятый fable, — строго выше,
    # basis не требуется (штатная приёмка полного Lead).
    routing, _ = logs
    la.append_routing("accepted", "critic", model="opus", by="fable",
                      task_id="t-001")
    rec = json.loads(routing.read_text(encoding="utf-8"))
    assert "basis" not in rec


def test_accepted_matrix_unknown_by_not_rescued_by_basis(logs):
    # by вне TIER_ORDER: basis не легализует приёмку от неизвестного
    # принимающего (ужесточение калибровки №4; раньше словарный basis
    # пропускал и это).
    routing, _ = logs
    with pytest.raises(SystemExit, match="известным ярусом"):
        la.append_routing("accepted", "builder", model="sonnet", by="gpt-5",
                          basis="critic", task_id="t-001",
                          witness="pytest -q -> passed")
    assert not routing.exists()


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


# AT-BUG-033: третье легальное основание (ветка "д") -- тот же agent
# делегируется на task_id ДВАЖДЫ по разным причинам в рамках жизненного
# цикла, прошедшего close+reopen (не ретрай, не замена мёртвого воркера).

def test_reopen_cycle_legalizes_second_delegated_same_agent_diff_review(logs):
    # Прецедент бага: critic сначала расследует неясный баг (правило 3б,
    # accepted basis=queued-to-lead), задача переоткрывается ДРУГИМ agent
    # (test-automator), вторая попытка даёт дифф, которому по правилу 3а
    # снова нужен свой критик-вход приёмки -- на ТОТ ЖЕ task_id. Легально
    # БЕЗ --attempt/rejected/--replaces-worker.
    routing, _ = logs
    la.append_routing("delegated", "critic", model="opus", task_id="t-001",
                      worker_ref="wr-critic-1", category="investigation")
    la.append_routing("accepted", "critic", model="opus", by="fable",
                      task_id="t-001", basis="queued-to-lead",
                      witness="investigation: неясный баг расследован, TC-135 подтверждён")
    la.append_routing("delegated", "test-automator", model="sonnet", task_id="t-001",
                      worker_ref="wr-auto-2",
                      reopen_task="повторная попытка автоматизации после расследования")
    # test-automator даёт builder-дифф, который ЕЩЁ НЕ принят (правило 3а
    # требует критик-вход ДО приёмки) -- задача остаётся ОТКРЫТОЙ (последнее
    # событие -- delegated test-automator), никакого accepted между reopen
    # и вторым critic-delegated ещё нет.
    # critic снова делегирован на t-001 -- теперь diff-review (правило 3а),
    # НЕ ретрай прошлого расследования и не замена мёртвого воркера.
    la.append_routing("delegated", "critic", model="opus", task_id="t-001",
                      worker_ref="wr-critic-3", category="diff-review")
    lines = routing.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 4
    rec = json.loads(lines[-1])
    assert rec["agent"] == "critic"
    assert rec["worker_ref"] == "wr-critic-3"
    assert "attempt" not in rec
    assert "replaces_worker" not in rec.get("notes", "")


def test_reopen_cycle_without_accepted_between_still_dup_pattern(logs):
    # Отрицательный контроль: если между двумя delegated этого agent НЕТ
    # accepted (например, только rejected-ретраи), ветка "д" не срабатывает
    # -- обычный дубль-паттерн по-прежнему требует --attempt/rejected или
    # --replaces-worker (регрессия существующих путей "в"/"г").
    routing, _ = logs
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                      worker_ref="wr-1")
    la.append_routing("rejected", "builder", model="sonnet", by="opus",
                      task_id="t-001", attempt=1, failure_class="capability")
    with pytest.raises(SystemExit, match="дубль"):
        la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                          worker_ref="wr-2")
    assert len(routing.read_text(encoding="utf-8").splitlines()) == 2


def test_reopen_cycle_stale_accepted_from_earlier_cycle_not_enough(logs):
    # Отрицательный контроль: accepted СТАРОГО цикла не легализует
    # ТРЕТИЙ delegated того же agent, если у ЕГО ВТОРОГО (более позднего)
    # delegated своего accepted+reopen ещё не было -- нужен accepted
    # ПОСЛЕ ПОСЛЕДНЕГО delegated именно этого agent, не любой accepted
    # где-то раньше в истории task_id.
    routing, _ = logs
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                      worker_ref="wr-1")
    la.append_routing("accepted", "builder", model="sonnet", by="opus",
                      task_id="t-001", witness="pytest -q -> passed")  # цикл 1 закрыт
    la.append_routing("delegated", "critic", model="opus", task_id="t-001",
                      worker_ref="wr-critic",
                      reopen_task="переоткрыто для повторной попытки")  # цикл 2 открыт
    # builder снова участвует в цикле 2 -- легально: accepted цикла 1
    # лежит ПОСЛЕ builder's первого (на тот момент единственного) delegated.
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                      worker_ref="wr-2")
    # цикл 2 НЕ закрывается accepted -- builder эскалирует, задача остаётся
    # открытой без нового accepted.
    la.append_routing("escalated", "builder", model="sonnet", task_id="t-001")
    # третий delegated builder: prior_agents содержит builder, последний
    # delegated builder -- это wr-2 (цикл 2); после НЕГО никакого accepted
    # нет (только escalated) -- дубль-паттерн, стейл accepted цикла 1 не
    # должен просачиваться вперёд.
    with pytest.raises(SystemExit, match="дубль"):
        la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                          worker_ref="wr-3")
    assert len(routing.read_text(encoding="utf-8").splitlines()) == 5


# AT-BUG-033 attempt 2 (критик-вердикт 2026-07-31T11:05:00Z, B1/B2) +
# критик-вход раунда 2 (B6): ветка "д" была ранним elif, глушившим (в)/(г)
# целиком; хелпер легализовал случай по ложной посылке ("любой accepted"
# вместо "настоящий --reopen-task"). Соседний класс B3 (второй критик-вход
# без accepted между) НЕ закрыт: сужение (в) под него ломало штатный
# review-раунд (12 исторических delegated) и откачено, остаток ведётся
# как AT-BUG-034. Тесты ниже воспроизводят находки критика И пинят
# итоговое поведение.

def _real_reopen_cycle(la_module, routing):
    """Хелпер сценария: critic расследует (accepted, задача закрыта),
    затем test-automator НАСТОЯЩИМ --reopen-task переоткрывает её --
    задача открыта, prior_agents={critic, test-automator}, последний
    delegated -- test-automator (несёт маркер "reopen: ..." в notes)."""
    la_module.append_routing("delegated", "critic", model="opus", task_id="t-001",
                             worker_ref="wr-critic-1", category="investigation")
    la_module.append_routing("accepted", "critic", model="opus", by="fable",
                             task_id="t-001", basis="queued-to-lead",
                             witness="investigation: неясный баг расследован")
    la_module.append_routing("delegated", "test-automator", model="sonnet",
                             task_id="t-001", worker_ref="wr-auto-2",
                             reopen_task="повторная попытка автоматизации после расследования")


def test_b1_fictitious_replaces_worker_still_rejected_in_reopened_state(logs):
    # B1: в (д)-состоянии (после НАСТОЯЩЕГО --reopen-task) фиктивный
    # --replaces-worker обязан по-прежнему отклоняться -- ветка (д) не
    # должна проходить мимо проверки фиктивной замены.
    routing, _ = logs
    _real_reopen_cycle(la, routing)
    with pytest.raises(SystemExit, match="replaces-worker"):
        la.append_routing("delegated", "critic", model="opus", task_id="t-001",
                          worker_ref="wr-critic-3",
                          replaces_worker="wr-NEVER-EXISTED")
    assert len(routing.read_text(encoding="utf-8").splitlines()) == 3


def test_b1_honest_replaces_worker_passes_and_appends_marker_in_reopened_state(logs):
    # B1: в (д)-состоянии честный --replaces-worker (совпадающий с реальным
    # прежним worker_ref) обязан пройти И дописать маркер replaces_worker:
    # в notes -- прежний баг проходил (elif "д" срабатывал раньше), но
    # маркер молча терялся (единственный носитель для journal_validator.py).
    routing, _ = logs
    _real_reopen_cycle(la, routing)
    la.append_routing("delegated", "critic", model="opus", task_id="t-001",
                      worker_ref="wr-critic-3",
                      replaces_worker="wr-critic-1")
    rec = json.loads(routing.read_text(encoding="utf-8").splitlines()[-1])
    assert rec["worker_ref"] == "wr-critic-3"
    assert "replaces_worker:wr-critic-1" in rec["notes"]
    assert "attempt" not in rec


def test_b1_replaces_worker_and_attempt_together_still_rejected_in_reopened_state(logs):
    # B1: взаимоисключение --replaces-worker/--attempt обязано срабатывать
    # и в (д)-состоянии, а не только когда (д) неприменима.
    routing, _ = logs
    _real_reopen_cycle(la, routing)
    with pytest.raises(SystemExit, match="взаимоисключающие"):
        la.append_routing("delegated", "critic", model="opus", task_id="t-001",
                          worker_ref="wr-critic-3",
                          replaces_worker="wr-critic-1", attempt=2)
    assert len(routing.read_text(encoding="utf-8").splitlines()) == 3


def test_b1_attempt_without_rejected_still_rejected_in_reopened_state(logs):
    # B1: --attempt без существующего (своего) rejected обязан отклоняться,
    # даже когда (д)-условие (настоящий reopen) выполнено -- (д) применяется
    # ТОЛЬКО когда --attempt вовсе не передан.
    routing, _ = logs
    _real_reopen_cycle(la, routing)
    with pytest.raises(SystemExit, match="дубль"):
        la.append_routing("delegated", "critic", model="opus", task_id="t-001",
                          worker_ref="wr-critic-3", attempt=7)
    assert len(routing.read_text(encoding="utf-8").splitlines()) == 3


def test_b2_real_reopen_task_marker_legalizes_second_delegated_same_agent(logs):
    # B2 позитив: после НАСТОЯЩЕГО --reopen-task (маркер "reopen: ..." в
    # notes какого-то delegated) повторный delegated того же agent легален
    # без attempt/rejected/replaces-worker -- изолированный минимальный
    # сценарий (без builder-диффа между), фокусирующийся именно на признаке.
    routing, _ = logs
    _real_reopen_cycle(la, routing)
    la.append_routing("delegated", "critic", model="opus", task_id="t-001",
                      worker_ref="wr-critic-3", category="diff-review")
    rec = json.loads(routing.read_text(encoding="utf-8").splitlines()[-1])
    assert rec["agent"] == "critic"
    assert "attempt" not in rec
    assert "replaces_worker" not in rec.get("notes", "")


def test_b2_accepted_without_real_reopen_task_does_not_legalize_via_branch_d(logs):
    # B2 регрессия: accepted БЕЗ настоящего --reopen-task (здесь -- поздний
    # rejected ПОСЛЕ accepted, признанный AO3-механизм переоткрытия, CLAUDE.md
    # «Журнал маршрутизации») НЕ должен легализовать повторный delegated
    # того же agent через ветку (д) -- старая посылка ("любой accepted
    # достаточен") была эмпирически ложной именно на этом сценарии.
    routing, _ = logs
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                      worker_ref="wr-1")
    la.append_routing("accepted", "builder", model="sonnet", by="opus",
                      task_id="t-001", witness="pytest -q -> passed")
    la.append_routing("rejected", "builder", model="sonnet", by="opus",
                      task_id="t-001", attempt=1, failure_class="capability")
    # задача снова "открыта" для гейта delegated (последнее событие --
    # rejected, не accepted), но БЕЗ настоящего --reopen-task -- обычный
    # повторный delegated builder без --attempt по-прежнему дубль-паттерн.
    with pytest.raises(SystemExit, match="дубль"):
        la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                          worker_ref="wr-2")
    assert len(routing.read_text(encoding="utf-8").splitlines()) == 3
    # обычный путь (в) по-прежнему работает: attempt>=2 + свой rejected.
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                      attempt=2, worker_ref="wr-2")
    assert len(routing.read_text(encoding="utf-8").splitlines()) == 4


def test_b6_review_round_second_critic_entry_after_executor_rework_passes(logs):
    # B6 (критик-вход раунда 2 по AT-BUG-033, 2026-07-31): ШТАТНЫЙ поток
    # фабрики -- критик review1 выносит вердикт ДОРАБОТАТЬ (rejected по
    # вердикту записывается на ИСПОЛНИТЕЛЯ; критик не ошибался, своего
    # rejected у него нет), исполнитель делает attempt 2, критику нужен
    # review2 на ТОМ ЖЕ открытом task_id. Проходит веткой (в) с --attempt N
    # на TASK-уровневом rejected. Реплей исторического
    # logs/routing-log.jsonl: 12 таких delegated (at-bug-025, TC-125,
    # TC-129, TC-131, TC-133, TC-134, CH-006 x2, CH-007 x3,
    # needs-design-tabs-deep-link) сужение _has_rejected до (task_id, agent)
    # переворачивало в BLOCKED -- регресс-пин отката сужения.
    # ИЗВЕСТНЫЙ ОСТАТОК (B3, bugs/AT-BUG-034.md): тем же основанием критик
    # формально может "занять" чужой rejected и вне честного раунда --
    # отличить раунд от заимствования сужением (в) НЕЛЬЗЯ (этот тест и
    # есть доказательство), нужен отдельный признак раунда.
    routing, _ = logs
    la.append_routing("delegated", "test-automator", model="sonnet",
                      task_id="t-001", worker_ref="wr-1")
    la.append_routing("delegated", "critic", model="opus", task_id="t-001",
                      worker_ref="wr-c1", category="diff-review")  # review1, (б)
    la.append_routing("rejected", "test-automator", model="sonnet", by="opus",
                      task_id="t-001", attempt=1, failure_class="spec")
    la.append_routing("delegated", "test-automator", model="sonnet",
                      task_id="t-001", attempt=2, worker_ref="wr-2")  # (в), свой rejected
    # review2 того же критика в том же открытом цикле -- обязан пройти.
    la.append_routing("delegated", "critic", model="opus", task_id="t-001",
                      attempt=2, worker_ref="wr-c2", category="diff-review")
    lines = routing.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 5
    rec = json.loads(lines[-1])
    assert rec["agent"] == "critic"
    assert rec["worker_ref"] == "wr-c2"
    assert rec["attempt"] == 2


def test_b6_task_level_rejected_alone_does_not_legalize_without_attempt(logs):
    # Граница отката (на границе и за ней): TASK-уровневый rejected сам по
    # себе НЕ легализует повторный delegated -- --attempt >=2 остаётся
    # обязательным (attempt отсутствует / attempt=1 -> дубль-паттерн).
    routing, _ = logs
    la.append_routing("delegated", "test-automator", model="sonnet",
                      task_id="t-001", worker_ref="wr-1")
    la.append_routing("delegated", "critic", model="opus", task_id="t-001",
                      worker_ref="wr-c1", category="diff-review")
    la.append_routing("rejected", "test-automator", model="sonnet", by="opus",
                      task_id="t-001", attempt=1, failure_class="spec")
    with pytest.raises(SystemExit, match="дубль"):
        la.append_routing("delegated", "critic", model="opus", task_id="t-001",
                          worker_ref="wr-c2")  # без --attempt
    assert len(routing.read_text(encoding="utf-8").splitlines()) == 3
    with pytest.raises(SystemExit, match="дубль"):
        la.append_routing("delegated", "critic", model="opus", task_id="t-001",
                          attempt=1, worker_ref="wr-c2")  # attempt=1 < 2
    assert len(routing.read_text(encoding="utf-8").splitlines()) == 3


# AT-BUG-034 (Добавление 8, 2026-07-31): B3 закрыт отдельным признаком
# поверх _has_rejected (_agent_has_own_rejected /
# _new_version_signal_since_agent_last_delegated), НЕ сужением самой
# _has_rejected (сужение доказанно ломает штатный поток -- B6, см. блок
# тестов выше). Позитив штатного раунда (сигнал 1: delegated исполнителя)
# уже пинится
# test_b6_review_round_second_critic_entry_after_executor_rework_passes;
# тесты ниже закрывают недостающее: негатив B3, границу анкера "последний
# delegated ИМЕННО этого agent" (не любая точка истории) и сигнал 2
# (rejected(agent='lead') -- Lead-tier rework без своего delegated,
# найден ОБЯЗАТЕЛЬНОЙ replay-гарантией на живом logs/routing-log.jsonl:
# CH-006/CH-007, критик-на-план).

def test_b3_second_critic_entry_without_executor_rework_between_is_dup_pattern(logs):
    # НЕЛЕГАЛЬНО (B3): critic review1 -> rejected ИСПОЛНИТЕЛЯ -> critic
    # снова с --attempt N СРАЗУ, БЕЗ нового delegated исполнителя между
    # первым и вторым входом критика -- никакой новой версии диффа не
    # появилось, это просто повторный вход в тот же цикл на тот же
    # артефакт. Ни own-rejected (rejected не критика), ни new-version
    # (нет delegated исполнителя после review1) не выполнены -- падает в
    # обычный дубль-паттерн, как и любой другой неоснованный повтор.
    routing, _ = logs
    la.append_routing("delegated", "test-automator", model="sonnet",
                      task_id="t-001", worker_ref="wr-1")
    la.append_routing("delegated", "critic", model="opus", task_id="t-001",
                      worker_ref="wr-c1", category="diff-review")  # review1
    la.append_routing("rejected", "test-automator", model="sonnet", by="opus",
                      task_id="t-001", attempt=1, failure_class="spec")
    with pytest.raises(SystemExit, match="дубль"):
        la.append_routing("delegated", "critic", model="opus", task_id="t-001",
                          attempt=2, worker_ref="wr-c2")  # review2 без rework -- B3
    assert len(routing.read_text(encoding="utf-8").splitlines()) == 3


def test_b3_stale_rework_signal_from_earlier_round_does_not_legalize_next_round(logs):
    # Граница анкера: new-version-сигнал ИЗ ПРЕДЫДУЩЕГО раунда не
    # переносится вперёд на следующий раунд без СВОЕГО нового rework.
    # Раунд 1 (легально, ЗА границей по счёту "новая версия есть"):
    # review1 -> rejected исполнителя -> исполнитель делает rework ->
    # review2 критика -- проходит (ровно признак этого фикса).
    # Раунд 2 (НА границе, недостаточно): ещё один rejected исполнителя
    # ПОСЛЕ review2, но БЕЗ нового delegated исполнителя между review2 и
    # review3 -- анкер "последний delegated ИМЕННО критика" сдвинулся на
    # review2, старый rework-сигнал (до review2) больше не считается --
    # review3 обязан упасть в дубль-паттерн.
    routing, _ = logs
    la.append_routing("delegated", "test-automator", model="sonnet",
                      task_id="t-001", worker_ref="wr-1")
    la.append_routing("delegated", "critic", model="opus", task_id="t-001",
                      worker_ref="wr-c1", category="diff-review")  # review1
    la.append_routing("rejected", "test-automator", model="sonnet", by="opus",
                      task_id="t-001", attempt=1, failure_class="spec")
    la.append_routing("delegated", "test-automator", model="sonnet",
                      task_id="t-001", attempt=2, worker_ref="wr-2")  # rework 1
    la.append_routing("delegated", "critic", model="opus", task_id="t-001",
                      attempt=2, worker_ref="wr-c2", category="diff-review")  # review2, легально
    la.append_routing("rejected", "test-automator", model="sonnet", by="opus",
                      task_id="t-001", attempt=2, failure_class="spec")  # ещё вердикт ДОРАБОТАТЬ
    # НЕТ нового delegated test-automator здесь -- rework 2 не произошёл.
    with pytest.raises(SystemExit, match="дубль"):
        la.append_routing("delegated", "critic", model="opus", task_id="t-001",
                          attempt=3, worker_ref="wr-c3")  # review3 без rework 2 -- B3
    assert len(routing.read_text(encoding="utf-8").splitlines()) == 6


def test_b3_self_retry_still_legal_without_any_other_agent_delegated_between(logs):
    # Не-регресс (в): классический self-retry (rejected и повторный
    # delegated -- ОДИН И ТОТ ЖЕ agent) остаётся легальным БЕЗ delegated
    # другого agent между -- own-rejected сам по себе достаточен, признак
    # AT-BUG-034 не требует rework-сигнала для этого пути (иначе обычный
    # ретрай builder/test-maintainer сломался бы).
    routing, _ = logs
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                      worker_ref="wr-1")
    la.append_routing("rejected", "builder", model="sonnet", by="opus",
                      task_id="t-001", attempt=1, failure_class="capability")
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                      attempt=2, worker_ref="wr-2")
    rec = json.loads(routing.read_text(encoding="utf-8").splitlines()[-1])
    assert rec["agent"] == "builder"
    assert rec["attempt"] == 2


def test_b3_new_delegated_of_different_agent_after_own_rejected_not_required(logs):
    # Не-регресс: свой rejected остаётся ДОСТАТОЧНЫМ основанием сам по
    # себе даже если между ним и повторным delegated того же agent
    # затесался delegated ТРЕТЬЕГО agent (напр. критик успел войти на
    # расследование чего-то ещё на этом task_id) -- own-rejected и
    # new-version -- это ИЛИ, не совместное условие.
    routing, _ = logs
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                      worker_ref="wr-1")
    la.append_routing("rejected", "builder", model="sonnet", by="opus",
                      task_id="t-001", attempt=1, failure_class="capability")
    la.append_routing("delegated", "critic", model="opus", task_id="t-001",
                      worker_ref="wr-c1", category="diff-review")
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                      attempt=2, worker_ref="wr-2")
    rec = json.loads(routing.read_text(encoding="utf-8").splitlines()[-1])
    assert rec["agent"] == "builder"
    assert rec["attempt"] == 2


def test_b3_lead_self_fix_rejected_signal_legalizes_review_round(logs):
    # Сигнал 2 признака AT-BUG-034 (найден replay-гарантией на живом
    # journal, живой прецедент CH-006/CH-007 «критик-на-план»): критик
    # отклоняет диф, автором которого выступает сам Lead (agent='lead') --
    # Lead правит немедленно БЕЗ отдельного delegated (правило 8
    # CLAUDE.md, Lead-tier работа событий пропуска не требует). rejected
    # на agent='lead' САМ ПО СЕБЕ легализует повторный critic-вход --
    # own-rejected здесь ложно (rejected не критика), но new-version-сигнал
    # (2) истинен без единой delegated-строки исполнителя между раундами.
    routing, _ = logs
    la.append_routing("delegated", "critic", model="opus", task_id="t-001",
                      worker_ref="wr-c1", category="qa-pipeline")  # review1
    la.append_routing("rejected", "lead", model="fable", by="fable",
                      task_id="t-001", attempt=1, failure_class="spec",
                      notes="critic review1: FAIL, правки внесены Lead немедленно")
    # НЕТ delegated lead/кого-либо между -- Lead исполнил правки сам,
    # без строки в журнале (Lead-tier работа, правило 8).
    la.append_routing("delegated", "critic", model="opus", task_id="t-001",
                      attempt=2, worker_ref="wr-c2", category="qa-pipeline")  # review2
    lines = routing.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    rec = json.loads(lines[-1])
    assert rec["agent"] == "critic"
    assert rec["attempt"] == 2


def test_b3_stale_lead_self_fix_signal_from_earlier_round_does_not_legalize_next_round(logs):
    # Граница анкера для сигнала 2 (симметрично сигналу 1): rejected(lead)
    # ИЗ ПРЕДЫДУЩЕГО раунда не легализует раунд N+2 без СВОЕГО нового
    # сигнала -- анкер "последний delegated ИМЕННО критика" сдвигается на
    # review2, старый rejected(lead) (до review2) больше не в окне.
    routing, _ = logs
    la.append_routing("delegated", "critic", model="opus", task_id="t-001",
                      worker_ref="wr-c1", category="qa-pipeline")  # review1
    la.append_routing("rejected", "lead", model="fable", by="fable",
                      task_id="t-001", attempt=1, failure_class="spec")
    la.append_routing("delegated", "critic", model="opus", task_id="t-001",
                      attempt=2, worker_ref="wr-c2", category="qa-pipeline")  # review2, легально
    # review2 тоже FAIL, но на этот раз БЕЗ нового rejected(lead) вовсе --
    # критик просто повторно ссылается на устаревший rejected(lead) раунда 1.
    with pytest.raises(SystemExit, match="дубль"):
        la.append_routing("delegated", "critic", model="opus", task_id="t-001",
                          attempt=3, worker_ref="wr-c3")  # review3 -- B3
    assert len(routing.read_text(encoding="utf-8").splitlines()) == 3


def test_b3_escalated_to_fable_signal_legalizes_review_round(logs):
    # Сигнал 3 (найден replay-гарантией, живой прецедент CH-007 attempt 3):
    # исполнитель (не reviewer) эскалирует НА ПОЛНОГО LEAD (model='fable',
    # правило 6 -- 2 rejected того же агента -> эскалация обязательна).
    # Lead чинит работу немедленно, БЕЗ delegated (правило 8). Критик
    # входит на ПЕРВУЮ проверку Lead-фикса -- ещё нет ни rejected(lead)
    # (Lead ещё не проверялся), ни delegated исполнителя, только
    # escalated(model=fable) -- этого достаточно для легализации.
    routing, _ = logs
    la.append_routing("delegated", "charter-designer", model="opus",
                      task_id="t-001", worker_ref="wr-cd1")
    la.append_routing("delegated", "critic", model="opus", task_id="t-001",
                      worker_ref="wr-c1", category="qa-pipeline")  # review1
    la.append_routing("rejected", "charter-designer", model="opus", by="sonnet",
                      task_id="t-001", attempt=1, failure_class="spec")
    la.append_routing("delegated", "charter-designer", model="opus",
                      task_id="t-001", attempt=2, worker_ref="wr-cd2")
    la.append_routing("delegated", "critic", model="opus", task_id="t-001",
                      attempt=2, worker_ref="wr-c2", category="qa-pipeline")  # review2
    la.append_routing("rejected", "charter-designer", model="opus", by="sonnet",
                      task_id="t-001", attempt=2, failure_class="spec")
    la.append_routing("escalated", "charter-designer", model="fable",
                      task_id="t-001", by="sonnet")  # правило 6: эскалация на Lead
    # Lead чинит немедленно, без delegated -- следующий вход критика
    # проверяет Lead-фикс НАПРЯМУЮ, без rejected(lead) вовсе.
    la.append_routing("delegated", "critic", model="opus", task_id="t-001",
                      attempt=3, worker_ref="wr-c3", category="qa-pipeline")  # review3
    lines = routing.read_text(encoding="utf-8").splitlines()
    rec = json.loads(lines[-1])
    assert rec["agent"] == "critic"
    assert rec["attempt"] == 3


def test_b3_stale_escalated_signal_from_earlier_round_does_not_legalize_next_round(logs):
    # Граница анкера для сигнала 3: escalated(model=fable) ИЗ ПРЕДЫДУЩЕГО
    # раунда не легализует раунд N+2 без СВОЕГО нового сигнала -- анкер
    # "последний delegated ИМЕННО критика" сдвигается на review, идущий
    # ПОСЛЕ escalated, старый escalated больше не в окне для review N+1.
    routing, _ = logs
    la.append_routing("delegated", "critic", model="opus", task_id="t-001",
                      worker_ref="wr-c1", category="qa-pipeline")  # review1
    la.append_routing("rejected", "test-automator", model="sonnet", by="opus",
                      task_id="t-001", attempt=1, failure_class="spec")
    la.append_routing("escalated", "test-automator", model="fable",
                      task_id="t-001", by="opus")
    la.append_routing("delegated", "critic", model="opus", task_id="t-001",
                      attempt=2, worker_ref="wr-c2", category="qa-pipeline")  # review2, легально
    # review2 тоже FAIL, но без НОВОГО escalated/rejected(lead)/delegated
    # исполнителя -- критик просто снова ссылается на старую эскалацию.
    with pytest.raises(SystemExit, match="дубль"):
        la.append_routing("delegated", "critic", model="opus", task_id="t-001",
                          attempt=3, worker_ref="wr-c3")  # review3 -- B3
    assert len(routing.read_text(encoding="utf-8").splitlines()) == 4


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


# Добавление 6 (task_id: open-dispatches-closes-token, 2026-07-20): токен
# closes-phantom:<task_id> в notes -- машиночитаемое закрытие фантома
# (CLAUDE.md «Журнал маршрутизации»: прежняя проза "фантом закрывается
# пометкой в notes следующего события" не читалась find_open_dispatches).
# Конвенция строгости зеркалит --replaces-worker.

def test_closes_phantom_token_closes_dangling_delegated(logs, capsys):
    routing, _ = logs
    la.append_routing("delegated", "critic", model="opus", task_id="t-001",
                      worker_ref="wr-dead")
    # Воркер фактически не был запущен -- фантом закрывается токеном в
    # notes следующего события (машиночитаемо, не прозой).
    la.append_routing("dispatch_skipped", "scout", category="recon",
                      notes="closes-phantom:t-001 воркер не был запущен")
    exit_code = la.main(["open-dispatches"])
    assert exit_code == 0
    assert capsys.readouterr().out == ""


def test_prose_phantom_note_does_not_close_dispatch(logs, capsys):
    # Старая (уже неактуальная в CLAUDE.md) конвенция -- прозаическая
    # пометка "фантом закрыт" без токена сканером НЕ читается.
    routing, _ = logs
    la.append_routing("delegated", "critic", model="opus", task_id="t-001",
                      worker_ref="wr-dead")
    la.append_routing("dispatch_skipped", "scout", category="recon",
                      notes="фантом закрыт: воркер не был запущен")
    exit_code = la.main(["open-dispatches"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "OPEN DISPATCH: t-001" in out


def test_closes_phantom_token_before_later_delegated_does_not_close_reopened_task(
        logs, capsys):
    # Токен, записанный ДО последнего delegated (переоткрытие/ретрай),
    # не закрывает -- новый delegated ПОСЛЕ токена вновь открывает задачу.
    routing, _ = logs
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                      worker_ref="wr-a")
    # Токен закрывает фантом ДО переоткрытия (на тот момент t-001 открыт --
    # валидатор пропускает запись).
    la.append_routing("escalated", "critic", model="opus", task_id="t-001",
                      notes="closes-phantom:t-001 ошибочно продиктованный "
                            "ранний фантом-статус")
    # continuation другим agent'ом (ветка "б") -- переоткрывает задачу
    # заново, без спецфлагов.
    la.append_routing("delegated", "critic", model="opus", task_id="t-001",
                      worker_ref="wr-b")
    exit_code = la.main(["open-dispatches"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "OPEN DISPATCH: t-001" in out


def test_closes_phantom_multiple_tokens_in_one_notes_close_both(logs, capsys):
    routing, _ = logs
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                      worker_ref="wr-a")
    la.append_routing("delegated", "critic", model="opus", task_id="t-002",
                      worker_ref="wr-b")
    la.append_routing("dispatch_skipped", "scout", category="recon",
                      notes="closes-phantom:t-001 closes-phantom:t-002 "
                            "оба воркера не были запущены")
    exit_code = la.main(["open-dispatches"])
    assert exit_code == 0
    assert capsys.readouterr().out == ""


def test_closes_phantom_validator_rejects_nonexistent_task_id(logs):
    routing, _ = logs
    with pytest.raises(SystemExit, match="closes-phantom"):
        la.append_routing("dispatch_skipped", "scout", category="recon",
                          notes="closes-phantom:t-999 опечатка")
    assert not routing.exists()


def test_closes_phantom_validator_rejects_already_closed_task_id(logs):
    routing, _ = logs
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                      worker_ref="wr")
    la.append_routing("accepted", "builder", model="sonnet", by="opus",
                      task_id="t-001", witness="pytest -q -> passed")
    with pytest.raises(SystemExit, match="closes-phantom"):
        la.append_routing("dispatch_skipped", "scout", category="recon",
                          notes="closes-phantom:t-001 задним числом")
    assert len(routing.read_text(encoding="utf-8").splitlines()) == 2


def test_closes_phantom_validator_rejects_trailing_punctuation(logs):
    # Та же самозащита, что у --replaces-worker: "closes-phantom:t-001."
    # захватывает "t-001." целиком, точное сравнение с "t-001" не проходит.
    routing, _ = logs
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                      worker_ref="wr")
    with pytest.raises(SystemExit, match="closes-phantom"):
        la.append_routing("dispatch_skipped", "scout", category="recon",
                          notes="closes-phantom:t-001.")
    assert len(routing.read_text(encoding="utf-8").splitlines()) == 1


def test_closes_phantom_happy_path_write_and_open_dispatches_empty(logs, capsys):
    routing, _ = logs
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                      worker_ref="wr")
    la.append_routing("dispatch_skipped", "scout", category="recon",
                      notes="closes-phantom:t-001 воркер не был запущен, "
                            "ре-диспатч не требуется")
    rec = json.loads(routing.read_text(encoding="utf-8").splitlines()[-1])
    assert "closes-phantom:t-001" in rec["notes"]
    exit_code = la.main(["open-dispatches"])
    assert exit_code == 0
    assert capsys.readouterr().out == ""


def test_closes_phantom_empty_token_is_harmless_literal_text(logs, capsys):
    # Граница: "closes-phantom:" без id -- \S+ требует хотя бы один
    # символ, а сразу за двоеточием конец notes -- токен не образуется,
    # проходит как обычный текст без валидации/закрытия.
    routing, _ = logs
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                      worker_ref="wr")
    la.append_routing("dispatch_skipped", "scout", category="recon",
                      notes="closes-phantom:")
    rec = json.loads(routing.read_text(encoding="utf-8").splitlines()[-1])
    assert rec["notes"] == "closes-phantom:"
    exit_code = la.main(["open-dispatches"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "OPEN DISPATCH: t-001" in out


def test_closes_phantom_duplicate_token_in_one_notes_closes_once_without_error(
        logs, capsys):
    # Граница: токен-дубль в одной notes -- легален, не ошибка.
    routing, _ = logs
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                      worker_ref="wr")
    la.append_routing("dispatch_skipped", "scout", category="recon",
                      notes="closes-phantom:t-001 closes-phantom:t-001 "
                            "задвоенный токен, не ошибка")
    exit_code = la.main(["open-dispatches"])
    assert exit_code == 0
    assert capsys.readouterr().out == ""


def test_closes_phantom_second_separate_record_with_same_token_is_idempotent(
        logs, capsys):
    # critic-находка (дивергенция сканер<->валидатор в безвредную сторону):
    # dispatch_skipped/decomposable/etc. НЕ входят в
    # _OPEN_DISPATCH_LIFECYCLE_CANDIDATES, поэтому _task_is_open_for_lifecycle
    # для t-001 остаётся True (последнее lifecycle-событие всё ещё
    # "delegated") даже ПОСЛЕ первой закрывающей записи. Валидатор поэтому
    # пропускает ВТОРУЮ отдельную запись с тем же closes-phantom:t-001
    # (не SystemExit, в отличие от test_closes_phantom_validator_rejects_
    # already_closed_task_id, где фантом закрыт через accepted -- lifecycle-
    # событие, которое validator видит). Сканер при этом всё равно не
    # выводит t-001 как открытый -- open-dispatches остаётся пустым.
    routing, _ = logs
    la.append_routing("delegated", "builder", model="sonnet", task_id="t-001",
                      worker_ref="wr")
    la.append_routing("dispatch_skipped", "scout", category="recon",
                      notes="closes-phantom:t-001 первое закрытие")
    # Вторая отдельная запись с тем же токеном -- не должна упасть.
    la.append_routing("dispatch_skipped", "scout", category="recon",
                      notes="closes-phantom:t-001 повторное закрытие, "
                            "идемпотентно")
    assert len(routing.read_text(encoding="utf-8").splitlines()) == 3
    exit_code = la.main(["open-dispatches"])
    assert exit_code == 0
    assert capsys.readouterr().out == ""


# =============================================================================
# D-0099-порт (2026-08-15): Lead-перепривязка Fable -> Opus 5.
# Матрица D-0058 несёт новую ветку lead-binding; escalated-сигнал (3)
# _new_version_signal_since_agent_last_delegated обобщён на семейство
# привязки вместо литерала "fable".
# =============================================================================

def _cfg_text(model: str) -> str:
    return f"roles:\n  lead:\n    subscription:\n      model: {model}\n"


@pytest.fixture()
def opus_config(monkeypatch, tmp_path):
    """Монкипатчит la.CONFIG_PATH на tmp-файл с roles.lead=claude-opus-5 и
    сбрасывает кэш _read_config_text() до и после теста (Б8: анти-мёртвая-
    фича пин — запись идёт через append_routing БЕЗ config_text, лениво
    читая ЭТОТ файл с диска)."""
    cfg = tmp_path / "delegation.config.yaml"
    cfg.write_text(_cfg_text("claude-opus-5"), encoding="utf-8")
    monkeypatch.setattr(la, "CONFIG_PATH", cfg, raising=True)
    la._reset_config_cache()
    yield cfg
    la._reset_config_cache()


def test_lead_binding_opus_by_opus_agent_critic_no_basis_passes_with_field(
        logs, opus_config):
    routing, _ = logs
    la.append_routing("accepted", "critic", model="opus", by="opus",
                      task_id="t-001")
    rec = json.loads(routing.read_text(encoding="utf-8"))
    assert rec["by"] == "opus"
    assert rec["lead_binding"] == "opus"
    assert "basis" not in rec


def test_lead_binding_opus_by_opus_basis_critic_still_rejected(logs, opus_config):
    # Пин :496 остаётся зелёным без правок -- непустой basis идёт по
    # ветке (6), не (5): критик не рецензирует равного себе.
    routing, _ = logs
    with pytest.raises(SystemExit, match="нелегален для пары"):
        la.append_routing("accepted", "critic", model="opus", by="opus",
                          basis="critic", task_id="t-001")
    assert not routing.exists()


def test_lead_binding_opus_by_sonnet_agent_critic_needs_queued_to_lead(
        logs, opus_config):
    routing, _ = logs
    # by=sonnet != семейство привязки "opus" -- ветка (5) не активна ни
    # при пустом, ни при заполненном basis; легализует только пара (6).
    with pytest.raises(SystemExit, match="D-0058"):
        la.append_routing("accepted", "critic", model="opus", by="sonnet",
                          task_id="t-001")
    la.append_routing("accepted", "critic", model="opus", by="sonnet",
                      basis="queued-to-lead", task_id="t-001")
    rec = json.loads(routing.read_text(encoding="utf-8"))
    assert rec["basis"] == "queued-to-lead"
    assert "lead_binding" not in rec


def test_lead_binding_opus_by_opus_agent_builder_still_strict_tier(
        logs, opus_config):
    # by=opus/agent=builder: строгий ярус (branch 2) уже легализует ДО
    # ветки (5) -- поведение то же, что было (штатная приёмка builder'а).
    routing, _ = logs
    la.append_routing("accepted", "builder", model="sonnet", by="opus",
                      task_id="t-001", witness="pytest -q -> passed")
    rec = json.loads(routing.read_text(encoding="utf-8"))
    assert "lead_binding" not in rec


def test_lead_binding_by_model_id_not_a_known_tier_rejected(logs, opus_config):
    # by несёт литеральный model-id, а не имя яруса -- матрица его не
    # знает вообще (ветка 3), привязка НЕ легализует.
    with pytest.raises(SystemExit, match="известным ярусом"):
        la.append_routing("accepted", "critic", model="opus",
                          by="claude-opus-5", task_id="t-001")


def test_lead_binding_by_case_sensitive_uppercase_not_normalized(logs, opus_config):
    # Р10: словарь by регистрозависим, нормализация НЕ вводится -- "OPUS"
    # не совпадает ни с одним known tier.
    with pytest.raises(SystemExit, match="известным ярусом"):
        la.append_routing("accepted", "critic", model="opus",
                          by="OPUS", task_id="t-001")


@pytest.fixture()
def config_with_model(monkeypatch, tmp_path):
    """Фабрика конфига с заданной model (Р15, критик-раунд 3): сброс кэша
    ГАРАНТИРОВАН через yield/finally-эквивалент фикстуры, не хвостовым
    оператором внутри теста -- падение ассерта ДО хвостового
    `_reset_config_cache()` иначе утекало бы tmp-конфиг (или его
    отсутствие) в последующие тесты того же прогона. Тот же образец, что
    `opus_config` выше."""
    def _make(model: str):
        cfg = tmp_path / "delegation.config.yaml"
        cfg.write_text(_cfg_text(model), encoding="utf-8")
        monkeypatch.setattr(la, "CONFIG_PATH", cfg, raising=True)
        la._reset_config_cache()
        return cfg
    yield _make
    la._reset_config_cache()


def test_lead_binding_floor_haiku_by_rejected_regardless_of_binding(
        logs, config_with_model):
    # ПОЛ: даже НИЗКОпривязанный (санитарно недопустимый) конфиг не
    # рескьюит by=haiku -- floor безусловен и проверяется ДО lead-binding
    # (ветка 4 раньше ветки 5), а resolve_lead_binding САМА санитарно
    # флорит такой конфиг в "fable".
    config_with_model("claude-haiku-4-5")
    routing, _ = logs
    with pytest.raises(SystemExit, match="D-0058"):
        la.append_routing("accepted", "scout", model="haiku", by="haiku",
                          task_id="t-001")


def test_lead_binding_sonnet_binding_config_sanitized_to_fable_no_rescue(
        logs, config_with_model):
    # ПОЛ: binding=sonnet в конфиге -> resolve_lead_binding санитарно
    # флорит в "fable" -- by=sonnet/agent=builder БЕЗ proper basis всё
    # равно отклонён (и с queued-to-lead тоже, т.к. by=sonnet никогда не
    # равен семейству "fable").
    config_with_model("claude-sonnet-5")
    routing, _ = logs
    with pytest.raises(SystemExit, match="D-0058"):
        la.append_routing("accepted", "builder", model="sonnet", by="sonnet",
                          task_id="t-001", witness="pytest -q -> passed")
    with pytest.raises(SystemExit, match="нелегален для пары"):
        la.append_routing("accepted", "builder", model="sonnet", by="sonnet",
                          basis="queued-to-lead", task_id="t-001",
                          witness="pytest -q -> passed")


# --- Б8: анти-мёртвая-фича пин ---------------------------------------------

def test_lead_binding_dead_feature_pin_real_lazy_read_without_config_text(
        logs, config_with_model):
    """Б8 (обязательный): вызов БЕЗ config_text (боевой путь), с
    монкипатченным CONFIG_PATH + сброшенным кэшем -- строка пишется и
    несёт lead_binding: opus. Тест, инжектирующий config_text напрямую,
    этот класс дефекта (мёртвая ветка (5) в бою) НЕ покрывает."""
    config_with_model("claude-opus-5")
    routing, _ = logs
    la.append_routing("accepted", "critic", by="opus", model="opus",
                      task_id="t-001")
    rec = json.loads(routing.read_text(encoding="utf-8"))
    assert rec["lead_binding"] == "opus"


# --- Б10б: негативный пин lead_binding --------------------------------------

def test_lead_binding_absent_on_strict_tier_legalized_line(logs, opus_config):
    routing, _ = logs
    la.append_routing("accepted", "builder", model="sonnet", by="opus",
                      task_id="t-001", witness="pytest -q -> passed")
    rec = json.loads(routing.read_text(encoding="utf-8"))
    assert "lead_binding" not in rec


def test_lead_binding_absent_on_basis_pair_legalized_line(logs, opus_config):
    routing, _ = logs
    la.append_routing("accepted", "critic", model="opus", by="sonnet",
                      basis="queued-to-lead", task_id="t-001")
    rec = json.loads(routing.read_text(encoding="utf-8"))
    assert "lead_binding" not in rec


# --- регресс-пин config_text=None: существующие матричные пин-кейсы ---------

_REGRESSION_MATRIX_CASES = [
    # (agent, by, basis, legal?) -- буквальные сценарии существующих 20+
    # тестов D-0058 выше, вызванные НАПРЯМУЮ через _matrix_violation с
    # config_text=None ("конфига нет" -> дефолт fable, поведение ДО
    # D-0099-порта). Дефолт None (не сентинел) здесь передаётся ЯВНО --
    # это и есть регресс-пин: если бы дефолт _matrix_violation тихо
    # деградировал в "боевой" сентинел-путь, эти сценарии перестали бы
    # быть детерминированными относительно реального файла на диске.
    ("builder", "opus", "", True),
    ("builder", "sonnet", "", False),
    ("builder", "haiku", "", False),
    ("builder", "sonnet", "critic", True),
    ("builder", "sonnet", "queued-to-lead", False),
    ("builder", "haiku", "critic", False),
    ("builder", "haiku", "queued-to-lead", False),
    ("scout", "haiku", "critic", False),
    ("scout", "haiku", "queued-to-lead", False),
    ("scout", "sonnet", "", True),
    ("critic", "sonnet", "queued-to-lead", True),
    ("critic", "opus", "queued-to-lead", True),
    ("critic", "sonnet", "critic", False),
    ("critic", "opus", "critic", False),
    ("critic", "fable", "", True),
    ("builder", "sonnet", "vibes", False),
    ("builder", "gpt-5", "critic", False),
    ("lead", "haiku", "", True),  # agent=lead -- матрица не применяется
    ("test-automator", "opus", "", True),
    ("test-automator", "sonnet", "", False),
    ("test-automator", "sonnet", "queued-to-lead", False),
    ("test-automator", "sonnet", "critic", True),
]


@pytest.mark.parametrize("agent,by,basis,legal", _REGRESSION_MATRIX_CASES)
def test_matrix_violation_regression_pin_config_text_none(agent, by, basis, legal):
    violation, lead_binding = la._matrix_violation(agent, by, basis, config_text=None)
    assert (violation is None) == legal, (agent, by, basis, violation)
    # config_text=None -> binding="fable"; ЕДИНСТВЕННЫЙ случай в списке с
    # by="fable" (critic/fable) легализуется branch(2) (strict tier,
    # tier(fable)=3 > tier(critic-opus)=2) РАНЬШЕ branch(5) -- lead_binding
    # поэтому None ВЕЗДЕ в этом регресс-наборе (ни один сценарий не
    # доходит до branch(5) в живой матрице).
    assert lead_binding is None, (agent, by, basis, lead_binding)


# --- escalated-сигнал (3), Б9б: обобщение на семейство привязки -------------

def test_escalated_signal_family_generalization(opus_config):
    assert la._escalated_to_lead_or_above("opus") is True   # = привязка
    assert la._escalated_to_lead_or_above("fable") is True  # выше привязки
    assert la._escalated_to_lead_or_above("sonnet") is False  # ниже
    assert la._escalated_to_lead_or_above("gpt-5") is False  # не-Claude
    assert la._escalated_to_lead_or_above(None) is False
    assert la._escalated_to_lead_or_above("") is False


def test_new_version_signal_escalated_opus_activates_with_opus_binding(opus_config):
    records = [
        {"task_id": "t-001", "event": "delegated", "agent": "critic"},
        {"task_id": "t-001", "event": "escalated", "agent": "critic", "model": "opus"},
    ]
    assert la._new_version_signal_since_agent_last_delegated(
        records, "t-001", "critic") is True


def test_new_version_signal_escalated_sonnet_does_not_activate(opus_config):
    records = [
        {"task_id": "t-001", "event": "delegated", "agent": "critic"},
        {"task_id": "t-001", "event": "escalated", "agent": "critic", "model": "sonnet"},
    ]
    assert la._new_version_signal_since_agent_last_delegated(
        records, "t-001", "critic") is False


# --- Б9а: replay-гарантия живого logs/routing-log.jsonl ---------------------

def _old_new_version_signal_pre_d0099(records, task_id, agent):
    """Точная копия ПРЕЖНЕЙ (до D-0099-порта) версии функции — эталон для
    replay-сравнения "до/после" (literal model == 'fable', единственная
    привязка, когда-либо существовавшая до этого порта)."""
    last_idx = None
    for i, r in enumerate(records):
        if (r.get("task_id") == task_id and r.get("event") == "delegated"
                and r.get("agent") == agent):
            last_idx = i
    if last_idx is None:
        return False
    for r in records[last_idx + 1:]:
        if r.get("task_id") != task_id:
            continue
        if r.get("event") == "delegated" and r.get("agent") != agent:
            return True
        if r.get("event") == "rejected" and r.get("agent") == "lead":
            return True
        if r.get("event") == "escalated" and r.get("model") == "fable":
            return True
    return False


# Б11 (критик-раунд 3): журнал append-only -- ПРЕФИКС длиной
# _REPLAY_FROZEN_N иммутабелен НАВСЕГДА, точное множество сырых флипов
# пинуется ТОЛЬКО на нём; хвост (индексы >= N) НЕ пинуется -- после
# перепривязки штатная эскалация правила 6 на opus даёт новые ЗАКОННЫЕ
# сырые флипы (16 из 23 исторических escalated несут model=opus), пин
# точного множества обучал бы дописывать в список вместо разбора.
_REPLAY_FROZEN_N = 1849  # len(logs/routing-log.jsonl) на момент D-0099-порта


def test_replay_live_routing_log_new_version_signal_no_regressions(opus_config):
    """Б9а (обязательная DoD): прогон ЖИВОГО logs/routing-log.jsonl через
    модифицированный _new_version_signal_since_agent_last_delegated
    до/после. Критерий: НИ ОДНОЙ записи OK -> BLOCKED; все BLOCKED -> OK
    перечисляются поимённо (task_id + индекс строки) и объяснены.

    opus_config (Б11): реплей судится по ФИКСИРОВАННОЙ (opus) привязке из
    тестовой фикстуры, а не по состоянию delegation.config.yaml на диске
    -- иначе в свежем клоне (или если Lead забудет закоммитить конфиг)
    _read_config_text() читает отсутствующий файл, resolve_lead_binding
    даёт "fable", и весь класс новых BLOCKED->OK флипов пропадает
    недетерминированно (критик-раунд 3, блокер Б11).

    "OK/BLOCKED" здесь -- ИТОГОВЫЙ вердикт `review_round_ok` из
    append_routing (`_agent_has_own_rejected(...) or
    _new_version_signal_since_agent_last_delegated(...)`), а НЕ сырое
    значение одной лишь сигнальной функции: own_rejected (self-retry,
    НЕ меняется этим портом вовсе) уже легализует запись независимо от
    сигнала (короткое замыкание `or` в РЕАЛЬНОМ коде append_routing) --
    сравнивать нужно то, что реально решает исход записи, а не сырой
    вывод одной из двух альтернатив. Разбор сырого флипа (AT-BUG-063,
    idx=1641) -- см. test_replay_live_routing_log_raw_signal_flip_is_
    named_and_explained ниже; own_rejected для этой строки уже True (2
    собственных rejected test-maintainer на этой задаче), поэтому на
    ИТОГОВЫЙ вердикт этот сырой флип не всплывает."""
    real_log = la.REPO / "logs" / "routing-log.jsonl"
    lines = [ln for ln in real_log.read_text(encoding="utf-8").splitlines() if ln.strip()]
    records = [json.loads(ln) for ln in lines]

    ok_to_blocked = []
    blocked_to_ok = []
    for idx, rec in enumerate(records):
        if rec.get("event") != "delegated":
            continue
        task_id = rec.get("task_id")
        agent = rec.get("agent")
        if not task_id or not agent:
            continue
        prefix = records[:idx]
        prior_agents = {r.get("agent") for r in prefix
                        if r.get("task_id") == task_id and r.get("event") == "delegated"}
        if agent not in prior_agents:
            continue  # не повторный delegated -- review_round_ok не участвует
        own_rejected = la._agent_has_own_rejected(prefix, task_id, agent)
        old_verdict = own_rejected or _old_new_version_signal_pre_d0099(prefix, task_id, agent)
        new_verdict = own_rejected or la._new_version_signal_since_agent_last_delegated(
            prefix, task_id, agent)
        if old_verdict and not new_verdict:
            ok_to_blocked.append((task_id, idx))
        if new_verdict and not old_verdict:
            blocked_to_ok.append((task_id, idx))

    assert ok_to_blocked == [], f"OK->BLOCKED переворотов быть не должно: {ok_to_blocked}"
    # Итоговый review_round_ok не меняется НИ ОДНОЙ реальной строкой этого
    # порта -- сырой флип сигнальной функции (см. тест ниже) поглощён
    # own_rejected и не всплывает на уровне реального решения append_routing.
    assert blocked_to_ok == [], f"BLOCKED->OK перевороты требуют разбора: {blocked_to_ok}"


def test_replay_live_routing_log_raw_signal_flip_is_named_and_explained(opus_config):
    """Дополнение к прогону выше: СЫРОЙ уровень (только сигнальная функция,
    без own_rejected). Критерий (Б9а): НИ ОДНОЙ OK->BLOCKED БЕЗ ГРАНИЦЫ
    (сужение легальности недопустимо на любой длине журнала -- если оно
    появится, ошибка обязана прерывать прогон немедленно, не после N).
    BLOCKED->OK допустимы, но пинуются ТОЛЬКО в пределах ЗАМОРОЖЕННОГО
    префикса _REPLAY_FROZEN_N (см. константу выше) -- хвост journal'а
    исключён из точного пина: после перепривязки штатные эскалации
    правила 6 на opus-воркеров легально дают НОВЫЕ сырые флипы, и пин
    точного множества на растущем журнале обучал бы дописывать элементы
    в список вместо разбора при каждом новом штатном срабатывании.

    opus_config (Б11): фиксирует привязку -- см. докстринг теста выше.

    Единственный именованный+объяснённый флип в пределах префикса:
    AT-BUG-063 idx=1641 -- штатная эскалация правила 6 (test-maintainer
    sonnet, 2 rejected -> attempt 3 на opus, строки 1634/1639/1640/1641),
    НЕ хэндоф полному Lead (критик-раунд 3, блокер Б12: прежняя версия
    докстринга ошибочно называла это "периодом Lead-деградации" --
    опровергнуто трейлом 1630-1644, это ЛЮБАЯ эскалация правилу 6 на
    opus-ярусного исполнителя). После перепривязки такие эскалации
    резолвятся сигналом (3) законно-по-форме (см. R-4, bugs/AT-BUG-034.md
    -- сигнал больше не отличает хэндоф Lead от эскалации воркера того же
    семейства). Итоговый вердикт СТРОКИ не меняется: own_rejected=True
    (см. тест выше) -- эффекта на реальное решение append_routing нет."""
    real_log = la.REPO / "logs" / "routing-log.jsonl"
    lines = [ln for ln in real_log.read_text(encoding="utf-8").splitlines() if ln.strip()]
    records = [json.loads(ln) for ln in lines]

    ok_to_blocked = []
    blocked_to_ok = []
    for idx, rec in enumerate(records):
        if rec.get("event") != "delegated":
            continue
        task_id = rec.get("task_id")
        agent = rec.get("agent")
        if not task_id or not agent:
            continue
        prefix = records[:idx]
        prior_agents = {r.get("agent") for r in prefix
                        if r.get("task_id") == task_id and r.get("event") == "delegated"}
        if agent not in prior_agents:
            continue
        old = _old_new_version_signal_pre_d0099(prefix, task_id, agent)
        new = la._new_version_signal_since_agent_last_delegated(prefix, task_id, agent)
        if old and not new:
            ok_to_blocked.append((task_id, idx))
        if new and not old:
            blocked_to_ok.append((task_id, idx))

    assert ok_to_blocked == [], f"OK->BLOCKED переворотов сырого сигнала быть не должно: {ok_to_blocked}"
    frozen = [f for f in blocked_to_ok if f[1] < _REPLAY_FROZEN_N]
    assert frozen == [("AT-BUG-063", 1641)], (
        f"ожидался РОВНО этот именованный+объяснённый флип сырого сигнала "
        f"в пределах замороженного префикса, получено: {frozen}")
