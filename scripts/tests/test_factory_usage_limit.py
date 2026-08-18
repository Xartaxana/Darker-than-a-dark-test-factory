"""Юнит-тесты класса «лимит подписки» (spec-factory-window v8, 2026-08-18).

Мотив — эпизод 2026-08-17: недельный лимит убил окно-фабрику, сторож
трактовал смерти ребёнка как ПОЛОМКУ, за окно лимита прилетело ~7 тостов
трёх классов (`stalled`/`fallback`/`child-death`), ни один не назвал
причину, а после возврата лимитов фабрика простояла ещё 5 часов на слепом
6-часовом probe-гейте.

Два слоя, как у соседних сьют:
  A) `heartbeat_wrap` — парсер строки вендора, чтение ХВОСТА лог-файла по
     смещению, переклассификация исхода и откат fastdeath-инкремента.
  B) `factory_watchdog.run_tick(..., reserve_runner=<fake>)` — гейт «в
     лимитном окне не спавним и молчим», возвратный тост, grace-окно
     приоритета живого окна, неначисление slowdeath.

Фикстуры окружения (`_paths`/`_write_state`/`_stalled_setup`/`_NoToast`)
переиспользуются из test_factory_watchdog_fallback — тот же контракт
tmp_path-изоляции, дублировать его копипастой смысла нет.
"""
from __future__ import annotations

import datetime

import pytest

import factory_watchdog as fw
import heartbeat_wrap as hw
from test_factory_watchdog_fallback import (      # noqa: F401 — _isolate_log_append autouse
    _NoToast, _isolate_log_append, _paths, _read_state, _stalled_setup, _write_state)
from test_heartbeat_wrap_fallback import FakeProc, _mono
from test_heartbeat_wrap_fallback import _paths as _hw_paths

NOW = datetime.datetime(2026, 8, 17, 14, 30, 0, tzinfo=datetime.timezone.utc)

# Дословная строка вендора из logs/fallback-20260817.log (эпизод 2026-08-17).
REAL_LINE = "You've hit your weekly limit · resets 2am (Europe/Paris)\n"


def _tz_available() -> bool:
    try:
        from zoneinfo import ZoneInfo
        ZoneInfo("Europe/Paris")
        return True
    except Exception:
        return False


needs_tz = pytest.mark.skipif(
    not _tz_available(),
    reason="нет tzdata — ветка «зона недоступна» проверяется отдельным тестом")


# ===========================================================================
# A1. Парсер строки вендора
# ===========================================================================

@needs_tz
def test_real_vendor_line_parsed_with_reset_in_utc():
    got = hw.parse_usage_limit(REAL_LINE, NOW)
    assert got is not None
    assert got["span"] == "weekly"
    # 02:00 Paris (CEST=UTC+2) следующих суток = 2026-08-18T00:00Z — ровно
    # тот момент, когда лимиты фактически вернулись в эпизоде.
    assert got["reset_ts"] == datetime.datetime(2026, 8, 18, 0, 0,
                                                tzinfo=datetime.timezone.utc)
    assert got["reset_hint"] == "2am (Europe/Paris)"


def test_non_limit_output_is_not_a_limit():
    assert hw.parse_usage_limit("Traceback: something exploded\nrc=1\n", NOW) is None
    assert hw.parse_usage_limit("", NOW) is None
    assert hw.parse_usage_limit(None, NOW) is None


def test_limit_without_resets_part_is_still_a_limit():
    """Класс распознан, время — нет: механизм обязан УМЕТЬ не знать время
    (формулировка вендора может смениться) и не притворяться, что знает."""
    got = hw.parse_usage_limit("You've hit your weekly limit\n", NOW)
    assert got is not None and got["reset_ts"] is None
    assert "resets" in got["note"]


@needs_tz
@pytest.mark.parametrize("hint,expect_hhmm", [
    ("2am (Europe/Paris)", (0, 0)),        # 02:00 CEST -> 00:00Z
    ("12am (Europe/Paris)", (22, 0)),      # полночь -> 22:00Z предыдущих суток
    ("12pm (Europe/Paris)", (10, 0)),      # полдень -> 10:00Z
    ("11:30pm (Europe/Paris)", (21, 30)),  # минуты
])
def test_clock_boundaries(hint, expect_hhmm):
    """M6-границы am/pm: 12am и 12pm — единственные точки, где наивная
    арифметика «pm => +12» даёт 24:00 и 24-часовой сдвиг соответственно."""
    got = hw.parse_usage_limit(f"You've hit your weekly limit · resets {hint}", NOW)
    assert got["reset_ts"] is not None
    assert (got["reset_ts"].hour, got["reset_ts"].minute) == expect_hhmm


def test_out_of_range_clock_is_rejected_not_crashed():
    got = hw.parse_usage_limit("You've hit your weekly limit · resets 99am (Europe/Paris)", NOW)
    assert got is not None and got["reset_ts"] is None
    assert "вне диапазона" in got["note"] or "не распознано" in got["note"]


def test_unknown_timezone_degrades_to_unknown_time_not_to_unknown_class():
    got = hw.parse_usage_limit(
        "You've hit your weekly limit · resets 2am (Nowhere/Nothing)", NOW)
    assert got is not None                      # КЛАСС распознан
    assert got["reset_ts"] is None              # ВРЕМЯ — нет
    assert "Nowhere/Nothing" in got["note"]


def test_reset_ts_is_always_in_the_future():
    """«resets 11pm» в 14:30 UTC — сегодня; «resets 2am» — уже завтра.
    Обе ветки обязаны дать БУДУЩЕЕ (иначе окно сна схлопнется в ноль)."""
    for hint in ("2am", "11pm", "1pm"):
        got = hw.parse_usage_limit(f"You've hit your weekly limit · resets {hint}", NOW)
        assert got["reset_ts"] > NOW, hint


# ===========================================================================
# A2. Чтение хвоста лога по смещению
# ===========================================================================

def test_read_usage_limit_reads_only_tail_after_offset(tmp_path):
    """Ключевой пин: в logs/fallback-YYYYMMDD.log копится ВЕСЬ день. Строка
    лимита ОТ ПРОШЛОГО запуска не смеет считаться уликой текущего —
    иначе один утренний лимит усыпил бы сторожа на весь день."""
    log = tmp_path / "fallback.log"
    log.write_bytes(REAL_LINE.encode("utf-8"))
    offset = log.stat().st_size
    with log.open("ab") as fh:
        fh.write(b"pass summary: triggered=1\n")

    assert hw.read_usage_limit(log, offset, NOW) is None          # хвост чист
    assert hw.read_usage_limit(log, 0, NOW) is not None           # с нуля — виден


def test_read_usage_limit_missing_file_is_non_throwing(tmp_path):
    assert hw.read_usage_limit(tmp_path / "нет.log", 0, NOW) is None
    assert hw.read_usage_limit(None, 0, NOW) is None


# ===========================================================================
# A3. run_fallback_pass — переклассификация исхода
# ===========================================================================

def _limit_child(monkeypatch, log_line=REAL_LINE, runtime=8.2):
    def fake_popen(args, **kw):
        kw["stdout"].write(log_line.encode("utf-8"))
        return FakeProc(pid=1, wait_plan=[1])                     # rc=1
    monkeypatch.setattr(hw, "_popen", fake_popen, raising=True)
    monkeypatch.setattr(hw.time, "monotonic", _mono([0.0, runtime]), raising=True)


def test_limit_death_is_reported_and_not_counted_as_fastdeath(
        tmp_path, _isolate_log_append, monkeypatch):
    p = _hw_paths(tmp_path)
    _limit_child(monkeypatch)

    r = hw.run_fallback_pass(log_path=tmp_path / "logs" / "f.log", now=NOW, **p)

    assert r["usage_limit"] is not None
    assert r["usage_limit"]["span"] == "weekly"
    assert r["fast_death"] is False                    # НЕ поломка
    # реестр поломок вернулся в исходное состояние — инкремент этого
    # вызова откачен ровно один раз
    assert hw._read_fastdeath(p["fastdeath_path"])["count"] == 0


def test_limit_death_m4_line_names_the_reason(tmp_path, _isolate_log_append, monkeypatch):
    p = _hw_paths(tmp_path)
    _limit_child(monkeypatch)

    hw.run_fallback_pass(log_path=tmp_path / "logs" / "f.log", now=NOW, **p)

    m4 = _isolate_log_append.read_text(encoding="utf-8")
    assert "usage-limit" in m4
    assert "exit=1" not in m4                          # прежняя немая формулировка ушла


def test_fastdeath_revert_keeps_earlier_real_failures(tmp_path, _isolate_log_append, monkeypatch):
    """Откат — РОВНО ОДИН инкремент, не сброс в ноль: настоящие прежние
    отказы (например, протухший OAuth) остаются в серии."""
    p = _hw_paths(tmp_path)
    hw._write_fastdeath(p["fastdeath_path"],
                        {"count": 2, "first_ts": "2026-08-17T10:00:00Z",
                         "last_ts": "2026-08-17T12:00:00Z", "last_rc": 1})
    _limit_child(monkeypatch)

    hw.run_fallback_pass(log_path=tmp_path / "logs" / "f.log", now=NOW, **p)

    assert hw._read_fastdeath(p["fastdeath_path"])["count"] == 2   # 2 -> 3 -> откат 2


def test_ordinary_fast_death_is_untouched_by_v8(tmp_path, _isolate_log_append, monkeypatch):
    """Негативный контроль: обычная быстрая смерть (не лимит) по-прежнему
    копит серию — механизм не ослабил детектор поломок."""
    p = _hw_paths(tmp_path)
    _limit_child(monkeypatch, log_line="Traceback: boom\n")

    r = hw.run_fallback_pass(log_path=tmp_path / "logs" / "f.log", now=NOW, **p)

    assert r["usage_limit"] is None
    assert r["fast_death"] is True
    assert hw._read_fastdeath(p["fastdeath_path"])["count"] == 1


# ===========================================================================
# B. Сторож: гейт лимитного окна, тосты, grace
# ===========================================================================

def _limit_result(reset_ts=None, reset_hint="2am (Europe/Paris)"):
    return {"outcome": "spawned", "child_rc": 1, "fast_death": False,
            "holder": "heartbeat:x:aaaa0000", "mode_write": None,
            "usage_limit": {"raw": "You've hit your weekly limit", "span": "weekly",
                            "reset_ts": reset_ts, "reset_hint": reset_hint,
                            "note": ""}}


def _runner(calls, result):
    def _run(**kwargs):
        calls.append(kwargs)
        return {"result": result, "classification": None, "cas_ok": None,
                "wrote_two_empty": False, "telemetry_delta": 1}
    return _run


RESET = datetime.datetime(2026, 8, 18, 0, 0, tzinfo=datetime.timezone.utc)


def test_detected_limit_opens_sleep_window_with_exactly_one_toast(tmp_path):
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=20)
    calls, toast = [], _NoToast()

    fw.run_tick(now=NOW, toast_fn=toast, reserve_runner=_runner(calls, _limit_result(RESET)), **p)

    assert len(calls) == 1                                  # один пробный запуск — цена детекта
    titles = [t for t, _ in toast.calls]
    assert titles == ["[factory:usage-limit]"]              # и РОВНО один тост
    st = _read_state(p)
    assert st["usage_limit_until"] == "2026-08-18T00:00:00Z"


def test_inside_limit_window_reserve_does_not_spawn_and_nothing_toasts(tmp_path):
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=200,
                   extra_state={"usage_limit_until": fw._fmt_ts(RESET),
                                "usage_limit_raw": "You've hit your weekly limit"})
    calls, toast = [], _NoToast()

    fw.run_tick(now=NOW, toast_fn=toast, reserve_runner=_runner(calls, _limit_result(RESET)), **p)

    assert calls == []                                      # запускать нечего
    assert toast.calls == []                                # и будить некого
    assert any("лимиты подписки исчерпаны" in n for n in _read_state(p)["notes"])


def test_stalled_alarm_toast_is_suppressed_inside_limit_window(tmp_path):
    """Тревога «фабрика стоит» в лимитном окне — ровно тот шум, от которого
    механизм заводится. След в escalations.md при этом ОСТАЁТСЯ."""
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=200,
                   extra_state={"usage_limit_until": fw._fmt_ts(RESET),
                                "last_state": "ok", "last_alert_ts": None})
    toast = _NoToast()

    fw.run_tick(now=NOW, toast_fn=toast, reserve_runner=_runner([], _limit_result(RESET)), **p)

    assert [t for t, _ in toast.calls] == []
    assert "FACTORY-STALLED" in p["escalations_file"].read_text(encoding="utf-8")


def test_reset_moment_gives_one_return_toast_and_holds_reserve(tmp_path):
    p = _paths(tmp_path)
    after_reset = RESET + datetime.timedelta(minutes=1)
    _stalled_setup(p, stalled_since_minutes_ago=600,
                   extra_state={"usage_limit_until": fw._fmt_ts(RESET)})
    calls, toast = [], _NoToast()

    fw.run_tick(now=after_reset, toast_fn=toast,
                reserve_runner=_runner(calls, _limit_result(RESET)), **p)

    assert [t for t, _ in toast.calls] == ["[factory:limit-back]"]
    assert "толкни окно" in toast.calls[0][1]
    assert calls == []                                      # приоритет живому окну
    assert _read_state(p)["usage_limit_grace_until"] is not None
    assert _read_state(p)["usage_limit_until"] is None


def test_return_toast_fires_once_not_every_tick(tmp_path):
    p = _paths(tmp_path)
    after_reset = RESET + datetime.timedelta(minutes=1)
    _stalled_setup(p, stalled_since_minutes_ago=600,
                   extra_state={"usage_limit_until": fw._fmt_ts(RESET)})
    toast = _NoToast()

    fw.run_tick(now=after_reset, toast_fn=toast, reserve_runner=_runner([], _limit_result()), **p)
    fw.run_tick(now=after_reset + datetime.timedelta(minutes=30), toast_fn=toast,
                reserve_runner=_runner([], _limit_result()), **p)

    assert [t for t, _ in toast.calls] == ["[factory:limit-back]"]


def test_after_grace_expires_reserve_resumes(tmp_path):
    """Оператор не пришёл — прежние правила ночного резерва возвращаются."""
    p = _paths(tmp_path)
    grace_end = RESET + datetime.timedelta(minutes=45)
    _stalled_setup(p, stalled_since_minutes_ago=600,
                   extra_state={"usage_limit_grace_until": fw._fmt_ts(grace_end)})
    calls, toast = [], _NoToast()

    fw.run_tick(now=grace_end + datetime.timedelta(seconds=1), toast_fn=toast,
                reserve_runner=_runner(calls, {"outcome": "spawned", "child_rc": 0,
                                               "fast_death": False, "holder": "h",
                                               "mode_write": None, "usage_limit": None}), **p)

    assert len(calls) == 1
    assert _read_state(p)["usage_limit_grace_until"] is None


def test_limit_death_does_not_grow_slowdeath_series(tmp_path):
    """Смерть от лимита приходит с fast_death=False — без явного исключения
    она копила бы slowdeath-серию, то есть ту же ложную «поломку», только
    другим счётчиком."""
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=20)

    fw.run_tick(now=NOW, toast_fn=_NoToast(),
                reserve_runner=_runner([], _limit_result(RESET)), **p)

    assert _read_state(p)["slowdeath_streak"] == 0


def test_window_progress_clears_limit_state(tmp_path):
    """Окно поехало (оператор толкнул) — протухшее лимитное окно не смеет
    продолжать глушить резерв."""
    p = _paths(tmp_path)
    fresh = NOW - datetime.timedelta(minutes=1)
    _write_state(p, last_state="stalled", stalled_since=fw._fmt_ts(NOW - datetime.timedelta(hours=3)),
                 last_progress_ts=fw._fmt_ts(fresh),
                 usage_limit_until=fw._fmt_ts(RESET), usage_limit_raw="weekly")
    from test_factory_watchdog_fallback import _write_mode, _write_sla
    _write_sla(p)
    _write_mode(p, mode="active", updated_ts=fw._fmt_ts(fresh))

    fw.run_tick(now=NOW, toast_fn=_NoToast(), reserve_runner=_runner([], _limit_result()), **p)

    st = _read_state(p)
    assert st["usage_limit_until"] is None and st["usage_limit_grace_until"] is None


def test_unparsed_reset_falls_back_to_conservative_sleep(tmp_path):
    """Время не распознано — окно сна всё равно открывается (на дефолтные
    6ч), потому что КЛАСС исхода известен: запускать бессмысленно."""
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=20)
    toast = _NoToast()

    fw.run_tick(now=NOW, toast_fn=toast,
                reserve_runner=_runner([], _limit_result(reset_ts=None, reset_hint=None)), **p)

    st = _read_state(p)
    expected = fw._fmt_ts(NOW + datetime.timedelta(hours=hw.USAGE_LIMIT_DEFAULT_SLEEP_H))
    assert st["usage_limit_until"] == expected
    assert [t for t, _ in toast.calls] == ["[factory:usage-limit]"]
