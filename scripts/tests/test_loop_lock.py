"""Юнит-тесты scripts/loop_lock.py — анти-наложение проходов /qa-loop +
детектор «фабрика систематически умирает» (docs/06 §5, docs/11 §1).

Изоляция: все пути (лок, reaps-json, escalations.md, sla.yaml) — под
tmp_path этого теста, никакой repo-фикстуры/монкипатча модульных
глобалов не требуется (loop_lock принимает пути аргументами).
Время инжектится через now=... — тесты детерминированы.
"""
from __future__ import annotations

import datetime
import json

import loop_lock as ll

NOW = datetime.datetime(2026, 7, 17, 12, 0, 0, tzinfo=datetime.timezone.utc)


def _sla(tmp_path, lock_stale=2):
    p = tmp_path / "state" / "sla.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"version: 1\nthresholds:\n  lock_stale: {lock_stale}\n", encoding="utf-8")
    return p


def _paths(tmp_path):
    return {
        "lock_file": tmp_path / "state" / "loop.lock",
        "reaps_path": tmp_path / "state" / "loop-lock-reaps.json",
        "escalations_path": tmp_path / "state" / "escalations.md",
        "sla_path": _sla(tmp_path),
    }


def test_acquire_on_empty_is_acquired(tmp_path):
    p = _paths(tmp_path)

    code, lines = ll.acquire(holder="qa-loop:t1", now=NOW, **p)

    assert code == 0
    assert any(l.startswith("ACQUIRED:") for l in lines)
    payload = json.loads(p["lock_file"].read_text(encoding="utf-8"))
    assert payload["holder"] == "qa-loop:t1"
    assert payload["ts"] == "2026-07-17T12:00:00Z"


def test_acquire_on_live_lock_is_busy(tmp_path):
    p = _paths(tmp_path)
    ll.acquire(holder="qa-loop:first", now=NOW, **p)

    later = NOW + datetime.timedelta(minutes=30)  # 0.5ч < порога 2ч
    code, lines = ll.acquire(holder="qa-loop:second", now=later, **p)

    assert code == 1
    assert any(l.startswith("BUSY:") and "qa-loop:first" in l for l in lines)
    # лок не тронут — второй holder не записан
    payload = json.loads(p["lock_file"].read_text(encoding="utf-8"))
    assert payload["holder"] == "qa-loop:first"


def test_acquire_on_stale_lock_reaps_and_counts(tmp_path):
    p = _paths(tmp_path)
    ll.acquire(holder="qa-loop:dead", now=NOW, **p)

    later = NOW + datetime.timedelta(hours=3)  # 3ч > порога 2ч
    code, lines = ll.acquire(holder="qa-loop:new", now=later, **p)

    assert code == 0
    assert any(l.startswith("REAPED:") and "qa-loop:dead" in l for l in lines)
    assert any(l.startswith("ACQUIRED:") and "qa-loop:new" in l for l in lines)
    reaps = json.loads(p["reaps_path"].read_text(encoding="utf-8"))
    assert reaps["count"] == 1
    assert reaps["holders"] == ["qa-loop:dead"]
    # новый лок реально записан
    payload = json.loads(p["lock_file"].read_text(encoding="utf-8"))
    assert payload["holder"] == "qa-loop:new"


def test_two_reaps_in_a_row_escalate_third_no_duplicate(tmp_path):
    p = _paths(tmp_path)
    t0 = NOW
    t1 = t0 + datetime.timedelta(hours=3)
    t2 = t1 + datetime.timedelta(hours=3)
    t3 = t2 + datetime.timedelta(hours=3)

    ll.acquire(holder="h0", now=t0, **p)                    # ACQUIRED (пусто)
    ll.acquire(holder="h1", now=t1, **p)                     # REAPED h0, streak=1, эскалации нет
    assert not p["escalations_path"].exists()

    code, lines = ll.acquire(holder="h2", now=t2, **p)       # REAPED h1, streak=2, эскалация
    assert code == 0
    assert any(l.startswith("ESCALATION:") and "LOOP-1" in l for l in lines)
    esc_text = p["escalations_path"].read_text(encoding="utf-8")
    assert esc_text.count("LOOP-1") == 1
    assert "2 проход" in esc_text

    code, lines = ll.acquire(holder="h3", now=t3, **p)       # REAPED h2, streak=3, апдейт на месте
    assert code == 0
    assert any(l.startswith("ESCALATION:") and "LOOP-1" in l for l in lines)
    esc_text = p["escalations_path"].read_text(encoding="utf-8")
    assert esc_text.count("LOOP-1") == 1          # не задублировалась
    assert esc_text.count("[loop:reaped]") == 1
    assert "3 проход" in esc_text


def test_release_matching_holder_resets_counter(tmp_path):
    p = _paths(tmp_path)
    t0 = NOW
    t1 = t0 + datetime.timedelta(hours=3)
    ll.acquire(holder="h0", now=t0, **p)
    ll.acquire(holder="h1", now=t1, **p)   # REAPED -> streak=1
    reaps = json.loads(p["reaps_path"].read_text(encoding="utf-8"))
    assert reaps["count"] == 1

    code, lines = ll.release(lock_file=p["lock_file"], holder="h1", reaps_path=p["reaps_path"])

    assert code == 0
    assert any(l.startswith("RELEASED:") for l in lines)
    assert not p["lock_file"].exists()
    reaps = json.loads(p["reaps_path"].read_text(encoding="utf-8"))
    assert reaps["count"] == 0


def test_release_noop_when_no_lock(tmp_path):
    p = _paths(tmp_path)

    code, lines = ll.release(lock_file=p["lock_file"], holder="anyone", reaps_path=p["reaps_path"])

    assert code == 0
    assert any(l.startswith("RELEASED:") and "noop" in l for l in lines)


def test_release_foreign_holder_refused_without_force(tmp_path):
    p = _paths(tmp_path)
    ll.acquire(holder="owner", now=NOW, **p)

    code, lines = ll.release(lock_file=p["lock_file"], holder="someone-else",
                              reaps_path=p["reaps_path"])

    assert code == 1
    assert any(l.startswith("REFUSED:") for l in lines)
    assert p["lock_file"].exists()   # лок не тронут


def test_release_foreign_holder_with_force_succeeds(tmp_path):
    p = _paths(tmp_path)
    ll.acquire(holder="owner", now=NOW, **p)

    code, lines = ll.release(lock_file=p["lock_file"], holder="someone-else",
                              reaps_path=p["reaps_path"], force=True)

    assert code == 0
    assert any(l.startswith("RELEASED:") for l in lines)
    assert not p["lock_file"].exists()


def test_status_reports_none_when_no_lock(tmp_path):
    p = _paths(tmp_path)

    code, lines = ll.status(lock_file=p["lock_file"], reaps_path=p["reaps_path"],
                             sla_path=p["sla_path"], now=NOW)

    assert code == 0
    assert any(l.startswith("NONE:") for l in lines)


def test_status_reports_live(tmp_path):
    p = _paths(tmp_path)
    ll.acquire(holder="h0", now=NOW, **p)

    code, lines = ll.status(lock_file=p["lock_file"], reaps_path=p["reaps_path"],
                             sla_path=p["sla_path"], now=NOW + datetime.timedelta(minutes=10))

    assert code == 0
    assert any(l.startswith("LIVE:") and "h0" in l for l in lines)


def test_status_reports_stale(tmp_path):
    p = _paths(tmp_path)
    ll.acquire(holder="h0", now=NOW, **p)

    code, lines = ll.status(lock_file=p["lock_file"], reaps_path=p["reaps_path"],
                             sla_path=p["sla_path"], now=NOW + datetime.timedelta(hours=5))

    assert code == 0
    assert any(l.startswith("STALE:") and "h0" in l for l in lines)
    # status не мутирует ничего
    assert p["lock_file"].exists()


def test_status_never_fails_on_corrupt_lock(tmp_path):
    p = _paths(tmp_path)
    p["lock_file"].parent.mkdir(parents=True, exist_ok=True)
    p["lock_file"].write_text("не json вообще", encoding="utf-8")

    code, lines = ll.status(lock_file=p["lock_file"], reaps_path=p["reaps_path"],
                             sla_path=p["sla_path"], now=NOW)

    assert code == 0
    assert any(l.startswith("CORRUPT:") for l in lines)


def test_acquire_reaps_unreadable_lock_file(tmp_path):
    """Битый (не-JSON) лок нельзя проверить на свежесть — трактуется как
    протухший, тем же принципом, что «нечитаемый лок» у stale_locks.py."""
    p = _paths(tmp_path)
    p["lock_file"].parent.mkdir(parents=True, exist_ok=True)
    p["lock_file"].write_text("garbage, not json", encoding="utf-8")

    code, lines = ll.acquire(holder="fresh", now=NOW, **p)

    assert code == 0
    assert any(l.startswith("REAPED:") and "нечитаем" in l for l in lines)
    assert any(l.startswith("ACQUIRED:") and "fresh" in l for l in lines)


def test_n2_corrupt_lock_reap_does_not_bump_death_streak(tmp_path):
    """N2 (docs/09 «Мелкое хозяйство» п.5): битый лок снимается (REAPED),
    но НЕ инкрементирует death-streak — мусорный файл не свидетельствует
    об умершем проходе. Ни строки REAP-STREAK, ни файла reaps не должно
    появиться (счётчик остаётся на дефолте 0, ничего не записано)."""
    p = _paths(tmp_path)
    p["lock_file"].parent.mkdir(parents=True, exist_ok=True)
    p["lock_file"].write_text("garbage, not json", encoding="utf-8")

    code, lines = ll.acquire(holder="fresh", now=NOW, **p)

    assert code == 0
    assert not any(l.startswith("REAP-STREAK:") for l in lines)
    assert not any(l.startswith("ESCALATION:") for l in lines)
    assert not p["reaps_path"].exists()


def test_n2_corrupt_lock_valid_json_missing_ts_also_not_counted(tmp_path):
    """Тот же N2, но для другого «битого» случая: JSON валиден, но без
    поля ts (свежесть тоже не проверить) — тоже не должен считаться."""
    p = _paths(tmp_path)
    p["lock_file"].parent.mkdir(parents=True, exist_ok=True)
    p["lock_file"].write_text('{"holder": "ghost"}', encoding="utf-8")

    code, lines = ll.acquire(holder="fresh", now=NOW, **p)

    assert code == 0
    assert any(l.startswith("REAPED:") and "ghost" in l for l in lines)
    assert not any(l.startswith("REAP-STREAK:") for l in lines)
    assert not p["reaps_path"].exists()


def test_n2_mixed_corrupt_then_genuine_stale_streak_counts_only_genuine(tmp_path):
    """Смешанная последовательность: битый лок не идёт в счёт, следующий
    генуинно протухший — идёт. Порог эскалации (2 подряд) не должен
    сработать от одного лишь битого + одного генуинного (streak=1, не 2)."""
    p = _paths(tmp_path)
    p["lock_file"].parent.mkdir(parents=True, exist_ok=True)
    p["lock_file"].write_text("not json at all", encoding="utf-8")
    t1 = NOW

    code, lines = ll.acquire(holder="h1", now=t1, **p)     # REAPED битый, streak НЕ растёт
    assert code == 0
    assert not any(l.startswith("REAP-STREAK:") for l in lines)

    t2 = t1 + datetime.timedelta(hours=3)                  # h1 сам генуинно протухнет
    code, lines = ll.acquire(holder="h2", now=t2, **p)      # REAPED h1 (стал старым), streak=1

    assert code == 0
    assert any(l.startswith("REAP-STREAK: подряд снятых=1") for l in lines)
    assert not any(l.startswith("ESCALATION:") for l in lines)   # порог 2 не достигнут


def test_idempotent_release_after_release_is_noop(tmp_path):
    p = _paths(tmp_path)
    ll.acquire(holder="h0", now=NOW, **p)
    ll.release(lock_file=p["lock_file"], holder="h0", reaps_path=p["reaps_path"])

    code, lines = ll.release(lock_file=p["lock_file"], holder="h0", reaps_path=p["reaps_path"])

    assert code == 0
    assert any("noop" in l for l in lines)
