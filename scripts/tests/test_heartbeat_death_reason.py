"""Юнит-тесты классификатора причины быстрой смерти резерва — auth/network/
limit/unknown (собрат критик-хвоста v8, docs/HANDOFF.md §7а, D-0043,
2026-08-19).

Мотив (то же наблюдение, что заводило v8-детектор лимита подписки, только
классом шире): «внешняя невозможность, трактованная как поломка
исполнителя». Прецедент `HEARTBEAT-AUTH` (закрыт перелогином оператора
2026-08-15) — протухший refresh-токен CLI, реальная строка вывода —
`logs/heartbeat.log:146` "Failed to authenticate: OAuth session expired and
could not be refreshed". Обрыв сети/5xx даёт ту же немую жалобу «N быстрых
смертей подряд — см. logs/fallback-*.log». Механизм чтения хвоста лога
(`heartbeat_wrap._read_log_tail`) уже стоит на пути исполнения (v8) —
здесь распознавание расширено классом причины.

Два слоя, как у соседних сьют:
  A) `heartbeat_wrap.classify_death_reason` — чистый распознаватель по
     тексту хвоста (auth/network/unknown; `limit` — отдельная ветка,
     проверяется `parse_usage_limit` ПЕРЕД этим распознавателем).
  B) `heartbeat_wrap.run_fallback_pass` — сквозной провод: реестр
     `state/heartbeat-fastdeath.json` получает `last_reason`, эскалация
     `HEARTBEAT-CHILD-DEATH` называет класс, `factory_watchdog.run_tick`
     называет класс в тосте/notes (Б-слой).
"""
from __future__ import annotations

import datetime

import pytest

import factory_watchdog as fw
import heartbeat_wrap as hw
from test_factory_watchdog_fallback import (      # noqa: F401 — _isolate_log_append autouse
    _NoToast, _isolate_log_append, _paths, _read_esc, _read_state, _stalled_setup, _write_state)
from test_heartbeat_wrap_fallback import FakeProc, _mono
from test_heartbeat_wrap_fallback import _paths as _hw_paths

NOW = datetime.datetime(2026, 8, 19, 14, 30, 0, tzinfo=datetime.timezone.utc)

# Дословная строка вендора из logs/heartbeat.log:146 (эпизод HEARTBEAT-AUTH,
# 2026-08-15).
REAL_AUTH_LINE = "Failed to authenticate: OAuth session expired and could not be refreshed\n"


# ===========================================================================
# A. classify_death_reason — распознаватели по тексту хвоста
# ===========================================================================

@pytest.mark.parametrize("tail", [
    REAL_AUTH_LINE,
    "Error: unauthorized (401)\n",
    "invalid api key\n",
    "please log in again\n",
    "Please sign in to continue.\n",
    "API token expired, re-authenticate\n",
])
def test_auth_reason_is_recognized(tail):
    assert hw.classify_death_reason(tail) == hw.DEATH_REASON_AUTH


@pytest.mark.parametrize("tail", [
    "Error: connect ECONNREFUSED 127.0.0.1:443\n",
    "FetchError: request to https://api.anthropic.com/v1 failed, reason: "
    "getaddrinfo ENOTFOUND api.anthropic.com\n",
    "502 Bad Gateway\n",
    "503 Service Unavailable\n",
    "socket hang up\n",
    "Internal Server Error\n",
])
def test_network_reason_is_recognized(tail):
    assert hw.classify_death_reason(tail) == hw.DEATH_REASON_NETWORK


@pytest.mark.parametrize("tail", [
    "Traceback (most recent call last):\n  ...\nZeroDivisionError: boom\n",
    "",
    None,
    "случайный текст без известных маркеров",
])
def test_unknown_reason_is_the_honest_fallback(tail):
    """unknown — «канал/причина не распознана», НЕ равносильно молчанию:
    пустой/None/нераспознанный хвост тоже даёт ЭТОТ класс, не исключение и
    не ложный auth/network."""
    assert hw.classify_death_reason(tail) == hw.DEATH_REASON_UNKNOWN


def test_auth_pattern_does_not_false_positive_on_network_text():
    """Негативный контроль: сетевой хвост не матчит auth-распознаватель
    (классы дизъюнктны в этом слое — порядок проверки в run_fallback_pass
    их не путает)."""
    assert hw.classify_death_reason("ECONNRESET\n") != hw.DEATH_REASON_AUTH


# ===========================================================================
# А-bis. Н-2 (критик rework attempt 2, 2026-08-19): сужение регексов
# ===========================================================================

@pytest.mark.parametrize("tail", [
    "HTTP request failed: 401 Unauthorized\n",
    "GET /v1/messages -> status 401\n",
])
def test_bare_401_in_http_context_is_auth(tail):
    assert hw.classify_death_reason(tail) == hw.DEATH_REASON_AUTH


@pytest.mark.parametrize("tail", [
    "processed batch 401 of 900 items\n",
    "queue depth reached 401 pending tasks\n",
])
def test_bare_401_without_http_context_is_not_auth(tail):
    """Н-2(а): голый `401` (номер батча/произвольный счётчик) без
    HTTP-контекста в ТОЙ ЖЕ строке — не auth (было ложное срабатывание на
    ЛЮБОЕ число 401)."""
    assert hw.classify_death_reason(tail) != hw.DEATH_REASON_AUTH


def test_internal_server_error_bare_is_still_network():
    """Регресс-щит: голая (без трейсбека) фраза остаётся network — Н-2(б) не
    ослабляет прежний позитивный случай."""
    assert hw.classify_death_reason("500 Internal Server Error\n") == hw.DEATH_REASON_NETWORK


def test_internal_server_error_inside_traceback_is_not_network():
    """Н-2(б): «Internal Server Error» ВНУТРИ Python-трейсбека — часто имя
    исключения приложения, не сетевой отказ."""
    tail = ("Traceback (most recent call last):\n"
           "  File \"app.py\", line 10, in handler\n"
           "InternalServerError: Internal Server Error\n")
    assert hw.classify_death_reason(tail) != hw.DEATH_REASON_NETWORK


def test_429_too_many_requests_is_not_network():
    """Н-2(в): rate-limit API — НЕ network (выбор — unknown, задокументирован
    в докстринге classify_death_reason: без потребителя, влияния на поток
    управления нет)."""
    assert hw.classify_death_reason("429 Too Many Requests\n") == hw.DEATH_REASON_UNKNOWN


def test_network_pattern_does_not_false_positive_on_auth_text():
    assert hw.classify_death_reason(REAL_AUTH_LINE) != hw.DEATH_REASON_NETWORK


# ===========================================================================
# B. run_fallback_pass — сквозной провод (реестр + эскалация)
# ===========================================================================

def _child(monkeypatch, log_line, runtime=8.2, rc=1):
    def fake_popen(args, **kw):
        stdout = kw.get("stdout")               # None, если log_path=None (без файла)
        if stdout is not None and log_line:
            stdout.write(log_line.encode("utf-8"))
        return FakeProc(pid=1, wait_plan=[rc])
    monkeypatch.setattr(hw, "_popen", fake_popen, raising=True)
    monkeypatch.setattr(hw.time, "monotonic", _mono([0.0, runtime]), raising=True)


def test_auth_death_reason_is_returned_and_named_in_escalation(
        tmp_path, _isolate_log_append, monkeypatch):
    p = _hw_paths(tmp_path)
    hw._write_fastdeath(p["fastdeath_path"],
                        {"count": 2, "first_ts": "2026-08-19T10:00:00Z",
                         "last_ts": "2026-08-19T12:00:00Z", "last_rc": 1})
    _child(monkeypatch, REAL_AUTH_LINE)

    r = hw.run_fallback_pass(log_path=tmp_path / "logs" / "f.log", now=NOW, **p)

    assert r["usage_limit"] is None
    assert r["death_reason"] == "auth"
    assert r["fast_death"] is True
    assert hw._read_fastdeath(p["fastdeath_path"])["count"] == 3
    assert hw._read_fastdeath(p["fastdeath_path"])["last_reason"] == "auth"
    esc = p["escalations_path"].read_text(encoding="utf-8")
    assert "HEARTBEAT-CHILD-DEATH" in esc
    assert "[auth]" in esc
    assert "логин/авторизация" in esc


def test_network_death_reason_is_returned(tmp_path, _isolate_log_append, monkeypatch):
    p = _hw_paths(tmp_path)
    _child(monkeypatch, "502 Bad Gateway\n")

    r = hw.run_fallback_pass(log_path=tmp_path / "logs" / "f.log", now=NOW, **p)

    assert r["death_reason"] == "network"
    assert hw._read_fastdeath(p["fastdeath_path"])["last_reason"] == "network"


def test_unrecognized_death_falls_back_to_unknown_reason(
        tmp_path, _isolate_log_append, monkeypatch):
    """unknown-фолбэк сквозь весь провод: обычная (не auth/network/limit)
    поломка по-прежнему считается серией, но класс называется честно —
    «не распознана», не выдумывается."""
    p = _hw_paths(tmp_path)
    _child(monkeypatch, "Traceback: boom\n")

    r = hw.run_fallback_pass(log_path=tmp_path / "logs" / "f.log", now=NOW, **p)

    assert r["death_reason"] == "unknown"
    assert r["fast_death"] is True
    assert hw._read_fastdeath(p["fastdeath_path"])["count"] == 1


def test_limit_death_reason_is_limit_not_auth_or_network(
        tmp_path, _isolate_log_append, monkeypatch):
    """Лимит подписки распознаётся ПЕРВЫМ (специфичнее — несёт момент
    сброса); auth/network-распознаватель на этот хвост даже не зовётся."""
    p = _hw_paths(tmp_path)
    _child(monkeypatch, "You've hit your weekly limit · resets 2am (Europe/Paris)\n")

    r = hw.run_fallback_pass(log_path=tmp_path / "logs" / "f.log", now=NOW, **p)

    assert r["usage_limit"] is not None
    assert r["death_reason"] == "limit"


def test_death_reason_is_none_when_no_log_path(tmp_path, _isolate_log_append, monkeypatch):
    """Без `log_path` (тестовый/CLI-вызов без файла) хвост нечитаем —
    классификация НЕ выдумывает причину: fast_death продолжает считаться,
    но `death_reason` — честный `unknown` (хвоста физически не было)."""
    p = _hw_paths(tmp_path)
    _child(monkeypatch, "Traceback: boom\n")

    r = hw.run_fallback_pass(log_path=None, now=NOW, **p)

    assert r["fast_death"] is True
    assert r["death_reason"] == "unknown"


def test_healthy_pass_has_no_death_reason(tmp_path, _isolate_log_append, monkeypatch):
    """rc==0 — не смерть вовсе, `death_reason` остаётся `None` (не
    «unknown»: unknown означает «смерть была, причина не ясна», а не
    «смерти не было»)."""
    p = _hw_paths(tmp_path)
    _child(monkeypatch, "ok\n", rc=0)

    r = hw.run_fallback_pass(log_path=tmp_path / "logs" / "f.log", now=NOW, **p)

    assert r["fast_death"] is False
    assert r["death_reason"] is None


# ===========================================================================
# C. factory_watchdog.run_tick — тост/notes называют класс (Б-слой)
#
# `hw._read_fastdeath(fastdeath_file)` ПОСЛЕ вызова резерва — АВТОРИТЕТНЫЙ
# источник для гейта тоста (`fd_count_after >= fallback_block_threshold`) в
# run_tick, поэтому фейковый `reserve_runner` обязан САМ дописать реестр
# (count 2->3 + last_reason) КАК ПОБОЧНЫЙ ЭФФЕКТ вызова — ровно то, что в
# production делает реальный `hw.run_fallback_pass` через
# `_fastdeath_after_spawn`/`_fastdeath_annotate_reason`. Предзаписанный
# count=3 ДО тика самопротиворечив: тот же счётчик блокирует сам триггер
# резерва (`_series_blocked`, count>=threshold И age<=6ч) — резерв тогда
# вообще не вызывается, `calls` пуст.
# ===========================================================================

def _runner_bumping_fastdeath(calls, result, fastdeath_file, bumped_data):
    """calls.append + побочный эффект «резерв дописал реестр» + возврат
    `result` — имитирует то, что в production делает реальный
    `hw.run_fallback_pass` внутри `fw._run_reserve_pass`."""
    def _run(**kwargs):
        calls.append(kwargs)
        hw._write_fastdeath(fastdeath_file, bumped_data)
        return {"result": result, "classification": None, "cas_ok": None,
                "wrote_two_empty": False, "telemetry_delta": 1}
    return _run


def test_child_death_toast_and_notes_name_the_reason(tmp_path):
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=20)
    # count=2, НЕ достигает fallback_block_threshold(3) — резерв триггерится
    # штатно (не заблокирован серией).
    hw._write_fastdeath(p["fastdeath_file"],
                        {"count": 2, "first_ts": fw._fmt_ts(NOW - datetime.timedelta(hours=1)),
                         "last_ts": fw._fmt_ts(NOW - datetime.timedelta(hours=1)), "last_rc": 1})
    toast = _NoToast()
    result = {"outcome": "spawned", "child_rc": 1, "fast_death": True,
             "holder": "heartbeat:x:aaaa0000", "mode_write": None,
             "usage_limit": None, "death_reason": "auth"}
    bumped = {"count": 3, "first_ts": fw._fmt_ts(NOW - datetime.timedelta(hours=1)),
             "last_ts": fw._fmt_ts(NOW), "last_rc": 1, "last_reason": "auth"}
    calls = []

    fw.run_tick(now=NOW, toast_fn=toast,
               reserve_runner=_runner_bumping_fastdeath(calls, result, p["fastdeath_file"], bumped),
               **p)

    assert len(calls) == 1                                  # резерв реально дёрнулся
    titles = [t for t, _ in toast.calls]
    assert "[factory:child-death]" in titles
    msg = dict(toast.calls)["[factory:child-death]"]
    assert "auth" in msg or "логин" in msg
    st = _read_state(p)
    assert any("auth" in n for n in st["notes"])


def test_child_death_toast_falls_back_to_registry_when_result_omits_reason(tmp_path):
    """Старый/тестовый `reserve_runner`, не заполняющий `death_reason` в
    возврате, — тост всё равно называет класс, читая его из реестра
    (`heartbeat-fastdeath.json.last_reason`), не проваливается в
    `KeyError`/пустую строку."""
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=20)
    hw._write_fastdeath(p["fastdeath_file"],
                        {"count": 2, "first_ts": fw._fmt_ts(NOW - datetime.timedelta(hours=1)),
                         "last_ts": fw._fmt_ts(NOW - datetime.timedelta(hours=1)), "last_rc": 1})
    toast = _NoToast()
    result = {"outcome": "spawned", "child_rc": 1, "fast_death": True,
             "holder": "heartbeat:x:aaaa0000", "mode_write": None, "usage_limit": None}
    bumped = {"count": 3, "first_ts": fw._fmt_ts(NOW - datetime.timedelta(hours=1)),
             "last_ts": fw._fmt_ts(NOW), "last_rc": 1, "last_reason": "network"}
    calls = []

    fw.run_tick(now=NOW, toast_fn=toast,
               reserve_runner=_runner_bumping_fastdeath(calls, result, p["fastdeath_file"], bumped),
               **p)

    msg = dict(toast.calls)["[factory:child-death]"]
    assert "network" in msg or "сеть" in msg


# ===========================================================================
# D. Д-2 (критик rework attempt 2, 2026-08-19): классификация ЛЮБОГО rc != 0
# (не только fastdeath), проброс в slowdeath-ноту/тост сторожа
# ===========================================================================

def test_classify_runs_for_slow_death_too_not_only_fast_death(tmp_path, _isolate_log_append,
                                                               monkeypatch):
    """Слой A: `run_fallback_pass` классифицирует причину и для МЕДЛЕННОЙ
    смерти (runtime >= FAST_DEATH_SEC, fast_death=False) — раньше
    классификация жила ТОЛЬКО под `if fast_death:`, `death_reason`
    оставался `None` для медленных отказов."""
    p = _hw_paths(tmp_path)
    _child(monkeypatch, "502 Bad Gateway\n", runtime=200.0)   # >= FAST_DEATH_SEC (120с)

    r = hw.run_fallback_pass(log_path=tmp_path / "logs" / "f.log", now=NOW, **p)

    assert r["fast_death"] is False                 # медленная смерть, не серия fastdeath
    assert r["death_reason"] == "network"            # но причина всё равно классифицирована


def test_slowdeath_note_and_toast_name_network_reason(tmp_path):
    """Слой B (Д-2, юнит из DoD): «медленная смерть с сетевым хвостом → тост/
    нота называют network» — `factory_watchdog.run_tick` пробрасывает
    `rr["death_reason"]` в slowdeath-стоп-ноту/эскалацию/тост."""
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=20,
                   extra_state={"slowdeath_streak": 2, "slowdeath_stopped": False})
    calls = []
    result = {"outcome": "timeout_kill", "child_rc": None, "fast_death": False,
             "holder": "heartbeat:x:aaaa0000", "mode_write": None,
             "usage_limit": None, "death_reason": "network"}

    def _run(**kwargs):
        calls.append(kwargs)
        return {"result": result, "classification": None, "cas_ok": None,
                "wrote_two_empty": False, "telemetry_delta": 1}

    toast = _NoToast()
    fw.run_tick(now=NOW, toast_fn=toast, reserve_runner=_run, **p)

    assert len(calls) == 1
    state = _read_state(p)
    assert state["slowdeath_streak"] == 3
    assert any("network" in n for n in state["notes"])
    esc = _read_esc(p)
    assert "FACTORY-FALLBACK-BROKEN" in esc and "network" in esc
    msg = dict(toast.calls)["[factory:fallback-broken]"]
    assert "network" in msg or "сеть" in msg


def test_slowdeath_without_reason_falls_back_to_unknown_label(tmp_path):
    """`timeout_kill` не несёт rc вовсе -> `death_reason=None` по построению
    (тестовый `reserve_runner` его тоже не заполняет) -> честный
    unknown-фолбэк в ноте/тосте, не KeyError/пустая строка."""
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=20,
                   extra_state={"slowdeath_streak": 2, "slowdeath_stopped": False})
    result = {"outcome": "timeout_kill", "child_rc": None, "fast_death": False,
             "holder": "x", "mode_write": None}

    def _run(**kwargs):
        return {"result": result, "classification": None, "cas_ok": None,
                "wrote_two_empty": False, "telemetry_delta": 1}

    toast = _NoToast()
    fw.run_tick(now=NOW, toast_fn=toast, reserve_runner=_run, **p)

    msg = dict(toast.calls)["[factory:fallback-broken]"]
    assert "unknown" in msg or "не распознана" in msg
