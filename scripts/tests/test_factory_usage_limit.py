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
# A1b. Дата в подсказке сброса (Н3, docs/HANDOFF.md §7а, 2026-08-19)
#
# Баг: `span` (имя регекс-группы дня/часа) захватывался, но не использовался,
# чтобы ОТЛИЧИТЬ день месяца от часа — «resets Aug 20 2am» читалось как
# «час=20» (взятый из «20» дня), дата пропадала БЕЗ следа: «Aug 20 2am» в
# 14:30 UTC 2026-08-17 превращалось в «сегодня в 20:00Z» вместо «через 3 дня
# в 02:00Z». Таблица «вход -> расчётный момент сброса» — в отчёте builder.
# ===========================================================================

def test_date_in_hint_is_recognized_not_swallowed_as_hour():
    """Пин основного бага: дата РАСПОЗНАНА и участвует в расчёте, не читается
    как час."""
    got = hw.parse_usage_limit(
        "You've hit your weekly limit · resets Aug 20 2am", NOW)
    assert got["reset_ts"] == datetime.datetime(2026, 8, 20, 2, 0,
                                                tzinfo=datetime.timezone.utc)
    # Старое (ошибочное) поведение дало бы 2026-08-17T20:00:00Z (сегодня,
    # час=20 из «20» дня месяца) — явный негативный контроль.
    assert got["reset_ts"] != datetime.datetime(2026, 8, 17, 20, 0,
                                                 tzinfo=datetime.timezone.utc)


def test_date_order_day_then_month_is_also_recognized():
    """«20 Aug 2am» (день перед месяцем) — тот же результат, что «Aug 20 2am»."""
    got = hw.parse_usage_limit(
        "You've hit your weekly limit · resets 20 Aug 2am", NOW)
    assert got["reset_ts"] == datetime.datetime(2026, 8, 20, 2, 0,
                                                tzinfo=datetime.timezone.utc)


@needs_tz
def test_date_with_timezone_crossing_midnight():
    """«за полночь»: полночь Парижа (CEST=UTC+2) 20 августа — это ЕЩЁ 19
    августа по UTC (календарная дата сдвигается зоной)."""
    got = hw.parse_usage_limit(
        "You've hit your weekly limit · resets Aug 20 12am (Europe/Paris)", NOW)
    assert got["reset_ts"] == datetime.datetime(2026, 8, 19, 22, 0,
                                                tzinfo=datetime.timezone.utc)


def test_hint_without_date_is_unchanged_by_the_fix():
    """Регресс-щит: подсказка БЕЗ даты (старый формат) даёт БАЙТ-В-БАЙТ
    прежний результат — фикс не должен трогать этот путь."""
    got = hw.parse_usage_limit(
        "You've hit your weekly limit · resets 2am (Europe/Paris)"
        if _tz_available() else "You've hit your weekly limit · resets 2am", NOW)
    assert got["reset_ts"] is not None
    assert got["reset_ts"] > NOW


def test_empty_reset_hint_is_conservative_not_a_crash():
    """Пустая строка (граница «за ней» самой строки) — не крашится, тот же
    консервативный «не распознано», что был всегда."""
    got = hw.parse_usage_limit("You've hit your weekly limit · resets ", NOW)
    assert got is not None
    assert got["reset_ts"] is None


@pytest.mark.parametrize("hint", [
    "Aug 20 2am (немного текста по-русски рядом)",
    "(сброс лимита скоро) Aug 20 2am",
])
def test_cyrillic_nearby_does_not_break_date_or_hour_parsing(hint):
    """«кириллица рядом»: посторонний текст на кириллице до/после токена не
    мешает найти ни дату, ни час (только IANA-зона `Region/City` в скобках
    матчит tz — кириллица без «/» её не изображает, трактуется как UTC)."""
    got = hw.parse_usage_limit(f"You've hit your weekly limit · resets {hint}", NOW)
    assert got["reset_ts"] == datetime.datetime(2026, 8, 20, 2, 0,
                                                tzinfo=datetime.timezone.utc)


@pytest.mark.parametrize("hint", [
    "Aug 32 2am",     # день вне 1-31 — дата-подобный токен невалиден
    "Feb 30 2am",     # день в 1-31, но календарно невозможен (нет 29/30 февраля)
])
def test_broken_date_falls_back_conservatively_hour_not_rescued(hint, capsys):
    """Б-1е: ОБА класса битой даты сведены к ОДНОМУ правилу — `reset_ts`
    ЦЕЛИКОМ `None`, час (2am) НЕ «спасает» результат отдельно от невалидной
    даты (раньше «Aug 32» теряло дату молча и «2am» из остатка строки
    правдоподобно, но ошибочно превращалось в «сегодня/завтра 2am»)."""
    got = hw.parse_usage_limit(f"You've hit your weekly limit · resets {hint}", NOW)
    assert got is not None                          # КЛАСС (лимит) всё равно распознан
    assert got["reset_ts"] is None                  # ВРЕМЯ — консервативный фолбэк, час не спасён
    out = capsys.readouterr().out
    assert "usage-limit:" in out                    # НЕ молча — строка в лог


def test_broken_date_without_any_hour_is_also_conservative(capsys):
    """Регресс-щит: дата без часа вообще (старый пин) — тот же консервативный
    фолбэк, НЕ крашится."""
    got = hw.parse_usage_limit("You've hit your weekly limit · resets Aug 32", NOW)
    assert got is not None and got["reset_ts"] is None
    out = capsys.readouterr().out
    assert "usage-limit:" in out


def test_reset_moment_boundary_at_the_instant_is_treated_as_passed(capsys):
    """M6-граница + Б-1а (критик rework attempt 2, 2026-08-19): дата+час
    РОВНО совпадает с `now` -> момент уже прошёл -> `reset_ts=None`
    (НЕ откат на следующий год, как было раньше)."""
    now_at_target = datetime.datetime(2026, 8, 20, 2, 0, 0, tzinfo=datetime.timezone.utc)
    got = hw.parse_usage_limit(
        "You've hit your weekly limit · resets Aug 20 2am", now_at_target)
    assert got["reset_ts"] is None
    assert "уже прошёл" in got["note"]
    out = capsys.readouterr().out
    assert "usage-limit:" in out


def test_reset_moment_boundary_one_second_before_is_valid_this_year():
    """Та же граница, на СЕКУНДУ раньше (момент ещё в будущем) — `reset_ts`
    валиден, остаётся ЭТОТ год."""
    just_before = datetime.datetime(2026, 8, 20, 1, 59, 59, tzinfo=datetime.timezone.utc)
    got = hw.parse_usage_limit(
        "You've hit your weekly limit · resets Aug 20 2am", just_before)
    assert got["reset_ts"] == datetime.datetime(2026, 8, 20, 2, 0,
                                                tzinfo=datetime.timezone.utc)


# ===========================================================================
# Б-1г (критик rework attempt 2, 2026-08-19): дата — только ДО часа / в той
# же клаузе, не первый дата-подобный токен всего хвоста
# ===========================================================================

@needs_tz
def test_date_after_em_dash_is_not_used():
    """Витнес-кейс критика: «...2am (Europe/Paris) — plan renewed Aug 3» —
    «Aug 3» относится к СОСЕДНЕЙ мысли (после эм-даша), не к моменту сброса.
    Ожидание: время близко к 2am Paris (~9.5ч от NOW=14:30 UTC), НЕ 3 августа."""
    got = hw.parse_usage_limit(
        "You've hit your weekly limit · resets 2am (Europe/Paris) — "
        "plan renewed Aug 3", NOW)
    assert got["reset_ts"] is not None
    # 2am Paris следующих суток (CEST=UTC+2) = 2026-08-18T00:00Z — та же
    # арифметика, что REAL_LINE выше, дата "Aug 3" её не подменяет.
    assert got["reset_ts"] == datetime.datetime(2026, 8, 18, 0, 0,
                                                tzinfo=datetime.timezone.utc)
    assert got["reset_ts"].day != 3


def test_date_after_semicolon_is_not_used():
    """Витнес-кейс критика: «...2am; see changelog May 1 for details» —
    «May 1» после точки с запятой не относится к моменту сброса."""
    got = hw.parse_usage_limit(
        "You've hit your weekly limit · resets 2am; see changelog May 1 "
        "for details", NOW)
    assert got["reset_ts"] is not None
    assert not (got["reset_ts"].month == 5 and got["reset_ts"].day == 1)


@needs_tz
def test_date_after_square_bracket_is_not_used():
    """Витнес-кейс критика: «resets at 3pm (Europe/Paris) [ref 12 Mar
    incident]» — «12 Mar»/«Mar 12» из квадратной скобки не должна
    подставляться (круглые скобки зоны — НЕ разделитель клаузы, остаются
    рабочими)."""
    got = hw.parse_usage_limit(
        "You've hit your weekly limit · resets at 3pm (Europe/Paris) "
        "[ref 12 Mar incident]", NOW)
    assert got["reset_ts"] is not None
    assert not (got["reset_ts"].month == 3 and got["reset_ts"].day == 12)
    assert got["reset_ts"].hour == 13   # 15:00 CEST (Paris, UTC+2) -> 13:00Z


def test_date_before_hour_in_same_clause_is_still_used():
    """Регресс-щит: дата В ТОЙ ЖЕ клаузе (без разделителей) — по-прежнему
    используется (Б-1г не должен ломать штатный формат «Aug 20 2am»)."""
    got = hw.parse_usage_limit(
        "You've hit your weekly limit · resets Aug 20 2am", NOW)
    assert got["reset_ts"] == datetime.datetime(2026, 8, 20, 2, 0,
                                                tzinfo=datetime.timezone.utc)


# ===========================================================================
# Б-1б (критик rework attempt 2, 2026-08-19): горизонт вменяемости reset_ts
# ===========================================================================

def test_horizon_hours_mapping():
    assert hw._usage_limit_horizon_hours("weekly") == 8 * 24
    assert hw._usage_limit_horizon_hours("5-hour") == 24
    assert hw._usage_limit_horizon_hours("") == 8 * 24
    assert hw._usage_limit_horizon_hours("some-other-span") == 8 * 24


@pytest.mark.parametrize("span,horizon_h", [("weekly", 8 * 24.0), ("5-hour", 24.0)])
def test_reset_ts_exactly_at_horizon_is_kept(monkeypatch, span, horizon_h):
    """M6-граница: РОВНО на горизонте — ещё валиден (≤ 8/1 суток)."""
    at_boundary = NOW + datetime.timedelta(hours=horizon_h)
    monkeypatch.setattr(hw, "_parse_reset_ts", lambda text, now: (at_boundary, ""),
                        raising=True)
    got = hw.parse_usage_limit(f"You've hit your {span} limit · resets whatever", NOW)
    assert got["reset_ts"] == at_boundary


@pytest.mark.parametrize("span,horizon_h", [("weekly", 8 * 24.0), ("5-hour", 24.0)])
def test_reset_ts_one_second_past_horizon_is_rejected(monkeypatch, span, horizon_h, capsys):
    """M6-граница ЗА ней: на секунду дальше горизонта — консервативный
    фолбэк, момент дальше горизонта почти наверняка ошибка парсера."""
    beyond = NOW + datetime.timedelta(hours=horizon_h, seconds=1)
    monkeypatch.setattr(hw, "_parse_reset_ts", lambda text, now: (beyond, ""),
                        raising=True)
    got = hw.parse_usage_limit(f"You've hit your {span} limit · resets whatever", NOW)
    assert got["reset_ts"] is None
    assert "горизонт" in got["note"]
    out = capsys.readouterr().out
    assert "usage-limit:" in out


def test_reset_ts_unknown_span_uses_default_horizon(monkeypatch, capsys):
    beyond = NOW + datetime.timedelta(hours=8 * 24.0, seconds=1)
    monkeypatch.setattr(hw, "_parse_reset_ts", lambda text, now: (beyond, ""),
                        raising=True)
    got = hw.parse_usage_limit("usage limit reached · resets whatever", NOW)
    assert got["span"] == ""
    assert got["reset_ts"] is None


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


# --- критик-раунд v8.1: блокер Б1 (голова вместо хвоста) ------------------

@pytest.mark.parametrize("prefix_kb", [1, 8, 9, 64, 512])
def test_limit_after_large_output_is_still_detected(tmp_path, prefix_kb):
    """M6-граница окна чтения. Прежняя версия делала seek(offset)+read(8192),
    то есть читала ГОЛОВУ среза: замер критика — 8КБ вывода до строки лимита
    детектились, 9КБ уже НЕТ, молча. Реальный лог успешного прохода весит
    6580 байт (80% окна), stderr ребёнка слит в тот же дескриптор, так что
    «ребёнок поработал и упёрся в лимит» — рядовой сценарий, а не край."""
    log = tmp_path / "fallback.log"
    log.write_bytes(b"")
    offset = 0
    with log.open("ab") as fh:
        fh.write((("x" * 1023 + "\n") * prefix_kb).encode("utf-8"))
        fh.write(REAL_LINE.encode("utf-8"))

    got = hw.read_usage_limit(log, offset, NOW)
    assert got is not None, f"лимит после {prefix_kb}КБ вывода не распознан"
    assert got["span"] == "weekly"


def test_window_is_anchored_to_the_tail_not_the_head(tmp_path):
    """Решающий пин «хвост vs голова»: с ЗАДАННЫМ маленьким окном строка в
    КОНЦЕ обязана находиться, а такая же строка в НАЧАЛЕ того же файла —
    нет. Прежняя реализация (seek(offset)+read(N)) даёт ровно обратное, и
    именно этим тестом отличается починка от маскировки безлимитным чтением
    (первая версия этих тестов проходила при обеих реализациях — красная
    проба это вскрыла)."""
    tail = tmp_path / "tail.log"
    tail.write_bytes(b"noise\n" * 2000 + REAL_LINE.encode("utf-8"))
    assert hw.read_usage_limit(tail, 0, NOW, tail_bytes=200) is not None

    head = tmp_path / "head.log"
    head.write_bytes(REAL_LINE.encode("utf-8") + b"noise\n" * 2000)
    assert hw.read_usage_limit(head, 0, NOW, tail_bytes=200) is None


def test_limit_phrase_outside_tail_lines_is_ignored(tmp_path):
    """Н4: сужение поверхности. Фраза вендора живёт и в самом репо; её эхо
    в НАЧАЛЕ вывода не должно открывать многочасовое окно тишины — уликой
    считается только причина смерти, то есть последние строки."""
    log = tmp_path / "fallback.log"
    log.write_bytes(REAL_LINE.encode("utf-8")
                    + b"".join(b"pass line %d\n" % i for i in range(200)))
    assert hw.read_usage_limit(log, 0, NOW) is None


def test_offset_still_bounds_the_read_from_below(tmp_path):
    """Хвост не должен «съесть» границу среза: строка ДО offset — чужая
    (вывод прошлого запуска), уликой этого прохода не является."""
    log = tmp_path / "fallback.log"
    log.write_bytes(REAL_LINE.encode("utf-8"))
    offset = log.stat().st_size
    with log.open("ab") as fh:
        fh.write(b"pass summary: triggered=1\n")
    assert hw.read_usage_limit(log, offset, NOW) is None


# --- критик-раунд v8.1: блокер Б2 (класс строки вендора) ------------------

@pytest.mark.parametrize("line,span", [
    ("You've hit your weekly limit · resets 2am (Europe/Paris)", "weekly"),
    ("You've hit your 5-hour limit · resets 3pm (Europe/Paris)", "5-hour"),
    ("Claude usage limit reached. Your limit will reset at 2pm (Europe/Paris)", ""),
    ("usage limit reached", ""),
])
def test_vendor_phrasings_are_recognized(line, span):
    """`\\w+` не матчил дефисный span — «5-hour limit» проваливался ЦЕЛИКОМ,
    хотя докстринг объявлял его поддержанным. Промах регекса не деградирует
    мягко: класс исчезает и возвращаются ложные тосты «поломка»."""
    got = hw.parse_usage_limit(line, NOW)
    assert got is not None, f"не распознано: {line!r}"
    assert got["span"] == span


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


def test_limit_death_rewrites_the_false_breakage_escalation(tmp_path, _isolate_log_append,
                                                            monkeypatch):
    """Н1: откат счётчика обязан откатывать и эскалацию, которую тот поднял.
    Замер критика: реестр возвращался к 2, а в escalations.md оставалась
    строка «3 быстрых смертей подряд» — человеку показывали поломку, которой
    нет."""
    p = _hw_paths(tmp_path)
    hw._write_fastdeath(p["fastdeath_path"],
                        {"count": 2, "first_ts": "2026-08-17T10:00:00Z",
                         "last_ts": "2026-08-17T12:00:00Z", "last_rc": 1})
    _limit_child(monkeypatch)

    hw.run_fallback_pass(log_path=tmp_path / "logs" / "f.log", now=NOW, **p)

    esc = p["escalations_path"].read_text(encoding="utf-8")
    assert "HEARTBEAT-CHILD-DEATH" in esc
    assert "ПЕРЕКЛАССИФИЦИРОВАНО" in esc, "ложная «поломка» осталась в escalations.md"
    assert hw._read_fastdeath(p["fastdeath_path"])["count"] == 2


def test_detector_tags_are_written_literally_to_orchestrator_log(tmp_path):
    """Б3: детектор F-11(в) грепает `[factory:limit-back]` по
    orchestrator-log. Счётный греп критика показал: этих строк код не писал
    НИКОГДА (`factory:stalled` = 0 при позитивном контроле `stalled` = 12),
    то есть механизм оставался без работающего детектора отказа."""
    p = _paths(tmp_path)
    after_reset = RESET + datetime.timedelta(minutes=1)
    _stalled_setup(p, stalled_since_minutes_ago=600,
                   extra_state={"usage_limit_until": fw._fmt_ts(RESET)})

    fw.run_tick(now=after_reset, toast_fn=_NoToast(),
                reserve_runner=_runner([], _limit_result()), **p)

    orch = p["orchestrator_log"].read_text(encoding="utf-8")
    assert f"[{fw.FACTORY_LIMIT_BACK_TAG}]" in orch
    esc = p["escalations_file"].read_text(encoding="utf-8")
    assert fw.GENERIC_RESOLVED_MARKER in esc, "лимитная эскалация не погашена (Н2)"


def test_limit_escalation_carries_current_ts(tmp_path):
    """Н2: «Факты п.8» той же спеки требуют текущий ts в singleton-строке —
    соседи (FACTORY-STALLED / FALLBACK-BROKEN) его несут."""
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=20)

    fw.run_tick(now=NOW, toast_fn=_NoToast(),
                reserve_runner=_runner([], _limit_result(RESET)), **p)

    esc = p["escalations_file"].read_text(encoding="utf-8")
    assert fw.FACTORY_LIMIT_KEY in esc
    assert fw._fmt_ts(RESET) in esc


def test_stale_limit_window_is_cleared_silently_without_return_toast(tmp_path):
    """Сброс наступил, пока фабрика стояла (окно закрыто оператором, хост
    спал): «лимиты вернулись» СУТКИ спустя — не новость, а шум того же
    класса, который механизм убирает."""
    p = _paths(tmp_path)
    stale = RESET + datetime.timedelta(hours=20)
    _stalled_setup(p, stalled_since_minutes_ago=600,
                   extra_state={"usage_limit_until": fw._fmt_ts(RESET)})
    calls, toast = [], _NoToast()

    fw.run_tick(now=stale, toast_fn=toast,
                reserve_runner=_runner(calls, {"outcome": "spawned", "child_rc": 0,
                                               "fast_death": False, "holder": "h",
                                               "mode_write": None, "usage_limit": None}), **p)

    assert [t for t, _ in toast.calls] == ["[factory:fallback]"]   # обычный ход, не лимитный
    st = _read_state(p)
    assert st["usage_limit_until"] is None and st["usage_limit_grace_until"] is None
    assert any("протухло" in n for n in st["notes"])


def test_return_toast_still_fires_at_the_lag_boundary(tmp_path):
    """M6-граница: РОВНО на пороге давности тост ещё звучит."""
    p = _paths(tmp_path)
    at_boundary = RESET + datetime.timedelta(hours=fw.LIMIT_RETURN_TOAST_MAX_LAG_H)
    _stalled_setup(p, stalled_since_minutes_ago=600,
                   extra_state={"usage_limit_until": fw._fmt_ts(RESET)})
    toast = _NoToast()

    fw.run_tick(now=at_boundary, toast_fn=toast,
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


# ===========================================================================
# Б-1в (критик rework attempt 2, 2026-08-19): пояс у ПОТРЕБИТЕЛЯ —
# usage_limit_until = min(reset_ts, now + MAX_LIMIT_SLEEP_H)
# ===========================================================================

def test_reset_ts_within_belt_is_kept_as_is(tmp_path):
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=20)
    within = NOW + datetime.timedelta(hours=fw.MAX_LIMIT_SLEEP_H)   # M6: РОВНО на поясе

    fw.run_tick(now=NOW, toast_fn=_NoToast(),
                reserve_runner=_runner([], _limit_result(within)), **p)

    st = _read_state(p)
    assert st["usage_limit_until"] == fw._fmt_ts(within)


def test_reset_ts_beyond_belt_is_capped(tmp_path):
    """M6-граница ЗА поясом: дальше `MAX_LIMIT_SLEEP_H` — срезается ровно до
    пояса, а НЕ до сырого (ошибочного) значения парсера. Это ВТОРАЯ,
    независимая линия обороны — работает даже если бы Б-1а/б почему-то не
    сработали (напр. будущая ошибка парсера, которую эти правила не ловят)."""
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=20)
    way_beyond = NOW + datetime.timedelta(hours=fw.MAX_LIMIT_SLEEP_H, seconds=1)
    cap = NOW + datetime.timedelta(hours=fw.MAX_LIMIT_SLEEP_H)

    fw.run_tick(now=NOW, toast_fn=_NoToast(),
                reserve_runner=_runner([], _limit_result(way_beyond)), **p)

    st = _read_state(p)
    assert st["usage_limit_until"] == fw._fmt_ts(cap)
    assert any("срезано поясом" in n for n in st["notes"])


def test_toast_names_the_computed_moment_not_the_raw_hint(tmp_path):
    """Б-1д: тост несёт ВЫЧИСЛЕННЫЙ момент (ISO UTC), не сырой `reset_hint` —
    показательно на СРЕЗАННОМ поясом случае, где сырой reset_hint («2am
    (Europe/Paris)», см. `_limit_result` дефолт) и реально применённый
    момент (срезанный) РАСХОДЯТСЯ."""
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=20)
    way_beyond = NOW + datetime.timedelta(hours=fw.MAX_LIMIT_SLEEP_H, seconds=1)
    cap = NOW + datetime.timedelta(hours=fw.MAX_LIMIT_SLEEP_H)
    toast = _NoToast()

    fw.run_tick(now=NOW, toast_fn=toast,
                reserve_runner=_runner([], _limit_result(way_beyond)), **p)

    msg = dict(toast.calls)["[factory:usage-limit]"]
    assert fw._fmt_ts(cap) in msg
    assert "2am (Europe/Paris)" not in msg


# ===========================================================================
# v8.2 (критик-вердикт по диффу v8, приёмка Lead 2026-08-20)
# ===========================================================================
#
# Б1: `_fastdeath_revert_one` откатывал только `count` — `first_ts`/
# `last_ts`/`last_rc`/`last_reason` оставались СВЕЖИМИ (от лимитной
# смерти, которая поломкой не была), эскалация могла остаться раздутой
# числом инкремента, которого больше нет в реестре.
# ===========================================================================

def test_fastdeath_revert_from_4_to_3_keeps_escalation_synced_with_registry(
        tmp_path, _isolate_log_append, monkeypatch):
    """Б1(а): реестр УЖЕ эскалирован (3, порог 3) настоящими прежними
    отказами; лимитная смерть этого прохода поднимает его до 4, и
    `_fastdeath_increment` переписывает эскалацию на «4». Откат обязан
    вернуть реестр к 3 И синхронизировать ТЕКСТ эскалации — не оставить
    заявление про 4, когда факт — 3."""
    p = _hw_paths(tmp_path)
    hw._write_fastdeath(p["fastdeath_path"],
                        {"count": 3, "first_ts": "2026-08-17T08:00:00Z",
                         "last_ts": "2026-08-17T09:00:00Z", "last_rc": 1,
                         "last_reason": "auth"})
    _limit_child(monkeypatch)

    hw.run_fallback_pass(log_path=tmp_path / "logs" / "f.log", now=NOW, **p)

    reg = hw._read_fastdeath(p["fastdeath_path"])
    assert reg["count"] == 3
    esc = p["escalations_path"].read_text(encoding="utf-8")
    assert "HEARTBEAT-CHILD-DEATH" in esc
    assert "4 быстрых смертей" not in esc         # раздутая инкрементом цифра ушла
    assert "3" in esc                              # синхронизировано с реестром


def test_fastdeath_revert_preserves_last_reason_annotation(
        tmp_path, _isolate_log_append, monkeypatch):
    """Б1(б): `last_reason='auth'` (от НАСТОЯЩЕГО прежнего отказа) обязан
    пережить откат — `_fastdeath_increment` пишет реестр БЕЗ ключа
    `last_reason` (теряет его), полный снимок ДО инкремента восстанавливает
    его вместе со счётчиком."""
    p = _hw_paths(tmp_path)
    hw._write_fastdeath(p["fastdeath_path"],
                        {"count": 2, "first_ts": "2026-08-17T08:00:00Z",
                         "last_ts": "2026-08-17T09:00:00Z", "last_rc": 1,
                         "last_reason": "auth"})
    _limit_child(monkeypatch)

    hw.run_fallback_pass(log_path=tmp_path / "logs" / "f.log", now=NOW, **p)

    reg = hw._read_fastdeath(p["fastdeath_path"])
    assert reg["count"] == 2
    assert reg["last_reason"] == "auth"


def test_series_blocked_not_triggered_by_stale_last_ts_after_limit_revert(
        tmp_path, _isolate_log_append, monkeypatch):
    """Б1(в): `last_ts`, оставшийся в реестре ПОСЛЕ отката, — момент
    СТАРОГО настоящего отказа (снимок ДО инкремента), не «сейчас» лимитной
    смерти. `_series_blocked` не должен считать серию свежей из-за одной
    лишь лимитной смерти (старая редакция сохраняла ФРЕШ `last_ts` от
    инкремента даже после отката count)."""
    p = _hw_paths(tmp_path)
    old_last_ts = "2026-08-10T00:00:00Z"          # >> FALLBACK_BLOCK_PROBE_HOURS от NOW
    hw._write_fastdeath(p["fastdeath_path"],
                        {"count": 3, "first_ts": "2026-08-09T00:00:00Z",
                         "last_ts": old_last_ts, "last_rc": 1})
    _limit_child(monkeypatch)

    hw.run_fallback_pass(log_path=tmp_path / "logs" / "f.log", now=NOW, **p)

    reg = hw._read_fastdeath(p["fastdeath_path"])
    assert reg["count"] == 3
    assert reg["last_ts"] == old_last_ts           # НЕ подменён на "сейчас" лимитной смерти
    last_ts_dt = fw._parse_ts(reg["last_ts"])
    assert fw._series_blocked(reg["count"], last_ts_dt, NOW, 3,
                              fw.FALLBACK_BLOCK_PROBE_HOURS) is False


def test_fastdeath_revert_without_snapshot_falls_back_to_count_only(tmp_path):
    """Регресс-щит: вызывающий БЕЗ `prev_snapshot` (устаревший вызов) —
    прежнее поведение (откат `count`-1, best-effort по остальным полям из
    ПОСТ-состояния файла) — функция не требует снимок обязательным
    аргументом."""
    fastdeath_path = tmp_path / "heartbeat-fastdeath.json"
    hw._write_fastdeath(fastdeath_path, {"count": 2, "first_ts": "t1",
                                         "last_ts": "t2", "last_rc": 1})
    suffix = hw._fastdeath_revert_one(fastdeath_path, None, NOW)
    assert suffix == " fastdeath-откат=1"
    assert hw._read_fastdeath(fastdeath_path)["count"] == 1


def test_fastdeath_revert_does_not_resurrect_count_after_concurrent_reset(tmp_path):
    """О1 (критик v8.2, второй раунд, probe9(2)): реестр МЕНЯЕТСЯ между
    снимком (до `_run_child`) и вызовом отката — параллельный тик/процесс
    обнулил `count` НЕЗАВИСИМО от нашей серии. Слепая запись СТАРОГО
    снимка (2) поверх текущего (0) "воскресила" бы поломку, которой
    конкурентный тик уже избавился — щит обязан деградировать на
    арифметику ПОВЕРХ факта, не поверх протухшего снимка."""
    fastdeath_path = tmp_path / "heartbeat-fastdeath.json"
    escalations_path = tmp_path / "escalations.md"
    prev_snapshot = {"count": 2, "first_ts": "2026-08-17T08:00:00Z",
                     "last_ts": "2026-08-17T09:00:00Z", "last_rc": 1,
                     "last_reason": "auth"}
    # конкурентный тик УЖЕ переписал реестр (обнулил count) ПОСЛЕ снимка,
    # но ДО того, как наш вызывающий добрался до отката.
    hw._write_fastdeath(fastdeath_path, {"count": 0, "first_ts": None,
                                         "last_ts": None, "last_rc": None,
                                         "last_reason": None})

    suffix = hw._fastdeath_revert_one(fastdeath_path, escalations_path, NOW,
                                      prev_snapshot=prev_snapshot)

    reg = hw._read_fastdeath(fastdeath_path)
    assert reg["count"] == 0                       # НЕ воскрешён к 2
    assert reg["last_reason"] is None               # не "воскрешён" auth от протухшего снимка
    assert "конкурентная-правка" in suffix


def test_fastdeath_revert_no_concurrent_change_uses_full_snapshot_unaffected(tmp_path):
    """Регресс-щит О1: КОГДА расхождения нет (наш собственный, единственный
    инкремент) — щит НЕ мешает штатному полному восстановлению снимка."""
    fastdeath_path = tmp_path / "heartbeat-fastdeath.json"
    escalations_path = tmp_path / "escalations.md"
    prev_snapshot = {"count": 2, "first_ts": "2026-08-17T08:00:00Z",
                     "last_ts": "2026-08-17T09:00:00Z", "last_rc": 1,
                     "last_reason": "auth"}
    # ИМЕННО ожидаемый post-инкремент (никакой конкурентной правки).
    hw._write_fastdeath(fastdeath_path, {"count": 3, "first_ts": "2026-08-17T08:00:00Z",
                                         "last_ts": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                         "last_rc": 1, "last_reason": None})

    suffix = hw._fastdeath_revert_one(fastdeath_path, escalations_path, NOW,
                                      prev_snapshot=prev_snapshot)

    reg = hw._read_fastdeath(fastdeath_path)
    assert reg["count"] == 2
    assert reg["last_reason"] == "auth"             # снимок применён целиком
    assert "конкурентная-правка" not in suffix


def test_fastdeath_revert_handles_corrupt_registry_file_without_crash(tmp_path):
    """Адверсариально (DoD): реестр-файл БИТЫЙ JSON в момент отката — НЕ
    падать. Битый файл читается `_read_fastdeath` как `count=0` (её
    собственная гарантия) — это НЕ совпадает с ожидаемым `prev_count+1`
    (О1-щит расхождения: снимок ДО инкремента протух/недостоверен), поэтому
    откат деградирует на арифметику ПОВЕРХ факта (0), а не слепо
    "воскрешает" переданный снимок — тот же щит, что и для настоящей
    конкурентной правки, не падает в обоих случаях."""
    fastdeath_path = tmp_path / "heartbeat-fastdeath.json"
    fastdeath_path.write_bytes(b"{not json at all!!")
    escalations_path = tmp_path / "escalations.md"
    prev_snapshot = {"count": 1, "first_ts": "2026-08-17T08:00:00Z",
                     "last_ts": "2026-08-17T08:00:00Z", "last_rc": 1,
                     "last_reason": None}

    suffix = hw._fastdeath_revert_one(fastdeath_path, escalations_path, NOW,
                                      prev_snapshot=prev_snapshot)

    assert "конкурентная-правка" in suffix
    assert hw._read_fastdeath(fastdeath_path)["count"] == 0


# ===========================================================================
# Б2: входной тост `[factory:usage-limit]` ронял `toast_fn`-detail без
# следа — в лимитном окне прочие тосты подавлены, отказ ИМЕННО этого тоста
# означал полное молчание сторожа до возврата лимитов (до 8 суток). Класс
# (решение Lead) — та же трассировка на [factory:fallback]/[factory:child-
# death]/[factory:fallback-broken]/[factory:fallback-channel].
# ===========================================================================

def test_toast_with_trace_logs_failure_detail(tmp_path):
    """Юнит DoD: `toast_fn` возвращает `(False, 'detail-text')` -> след
    появляется (нота + orchestrator-log строка)."""
    def fake_toast(title, message):
        return False, "detail-text"
    notes: list[str] = []
    orch_log = tmp_path / "orchestrator-log.md"

    shown, detail = fw._toast_with_trace(
        fake_toast, "[factory:usage-limit]", "msg text",
        orchestrator_log=orch_log, artifact="state/factory-watchdog.json",
        now=NOW, notes_list=notes)

    assert shown is False
    assert detail == "detail-text"
    assert any("detail-text" in n for n in notes)
    assert "detail-text" in orch_log.read_text(encoding="utf-8")


def test_toast_with_trace_survives_toast_fn_exception(tmp_path):
    """Адверсариально (DoD): `toast_fn` кидает исключение — не падать,
    отказ всё равно трассируется."""
    def raising_toast(title, message):
        raise RuntimeError("toast API unavailable")
    notes: list[str] = []
    orch_log = tmp_path / "orchestrator-log.md"

    shown, detail = fw._toast_with_trace(
        raising_toast, "[factory:fallback]", "msg text",
        orchestrator_log=orch_log, artifact="x", now=NOW, notes_list=notes)

    assert shown is False
    assert "toast API unavailable" in detail
    assert "toast API unavailable" in orch_log.read_text(encoding="utf-8")


def test_toast_with_trace_failure_line_does_not_carry_bare_bracketed_tag(tmp_path):
    """О4(1) (критик v8.2, второй раунд): строка следа отказа НЕ несёт
    голый бракетный литерал тега — грep по `[factory:usage-limit]` КАК
    СОБЫТИЮ ВХОДА не должен ловить строку отказа тоста."""
    def fake_toast(title, message):
        return False, "boom"
    notes: list[str] = []
    orch_log = tmp_path / "orchestrator-log.md"

    fw._toast_with_trace(
        fake_toast, "[factory:usage-limit]", "msg text",
        orchestrator_log=orch_log, artifact="x", now=NOW, notes_list=notes)

    assert "[factory:usage-limit]" not in orch_log.read_text(encoding="utf-8")
    assert not any("[factory:usage-limit]" in n for n in notes)
    assert "factory:usage-limit" in orch_log.read_text(encoding="utf-8")   # тег БЕЗ скобок остаётся


def test_toast_with_trace_does_not_log_deliberate_no_toast_suppression(tmp_path):
    """О4(2) (критик v8.2, второй раунд): `--no-toast`/`AO3_FACTORY_NO_TOAST`
    подавляет тосты ПРЕДНАМЕРЕННО (смок-режим/CLI-отладка) — это НЕ отказ
    канала; `_toast_with_trace` не должен писать эту тишину в БОЕВОЙ
    orchestrator-log/notes как будто это поломка (иначе КАЖДЫЙ тик
    смок-режима засорял бы реальный журнал одинаковыми "отказами")."""
    def suppressed_toast(title, message):
        return False, fw.NO_TOAST_SUPPRESSED_PREFIX + " подавлен"
    notes: list[str] = []
    orch_log = tmp_path / "orchestrator-log.md"

    shown, detail = fw._toast_with_trace(
        suppressed_toast, "[factory:usage-limit]", "msg text",
        orchestrator_log=orch_log, artifact="x", now=NOW, notes_list=notes)

    assert shown is False
    assert notes == []
    assert not orch_log.exists()


def test_no_toast_suppression_via_run_tick_does_not_pollute_orchestrator_log(tmp_path):
    """О4(2), сквозной прогон: тот же сентинел через полный `run_tick`."""
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=20)

    def no_toast_stub(title, message):
        return False, fw.NO_TOAST_SUPPRESSED_PREFIX + " подавлен"

    fw.run_tick(now=NOW, toast_fn=no_toast_stub,
                reserve_runner=_runner([], _limit_result(RESET)), **p)

    orch = p["orchestrator_log"].read_text(encoding="utf-8")
    assert "тост не показан" not in orch
    st = _read_state(p)
    assert not any("тост не показан" in n for n in st["notes"])


def test_usage_limit_toast_failure_leaves_trace_via_run_tick(tmp_path):
    """Б2 (блокер): сквозной прогон через `run_tick` — отказ входного тоста
    `[factory:usage-limit]` оставляет след и в notes state-файла, и в
    orchestrator-log (не молчание до возврата лимитов)."""
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=20)

    def fail_toast(title, message):
        return False, "detail-text"

    fw.run_tick(now=NOW, toast_fn=fail_toast,
                reserve_runner=_runner([], _limit_result(RESET)), **p)

    orch = p["orchestrator_log"].read_text(encoding="utf-8")
    assert "тост не показан (factory:usage-limit): detail-text" in orch
    # О4 (критик v8.2, второй раунд): строка ОТКАЗА тоста не несёт голый
    # бракетный литерал РЯДОМ с самим следом отказа — грep по
    # `[factory:usage-limit]` как СОБЫТИЮ ВХОДА не должен путать реальный
    # entry-event (пишется note'ой "резерв умер от лимита подписки" -
    # легитимно несёт тег в бракетах) со строкой отказа тоста.
    assert "[factory:usage-limit] тост" not in orch
    st = _read_state(p)
    assert any("detail-text" in n for n in st["notes"])


class _RaisingToast:
    """Адверсариальный toast_fn: ЛЮБОЙ вызов бросает исключение."""

    def __init__(self):
        self.calls = []

    def __call__(self, title, message):
        self.calls.append((title, message))
        raise RuntimeError("toast API unavailable")


def test_usage_limit_toast_exception_does_not_crash_run_tick(tmp_path):
    """Адверсариально (DoD): `toast_fn` кидает исключение внутри `run_tick`
    (не только в изолированном юните) — тик обязан завершиться (return 0),
    не падать наружу, И state ОБЯЗАН быть ЗАПИСАН ПОСЛЕ исключения (окно
    закрывается штатно — иначе usage_limit_until замерзает в прошлом и
    СЛЕДУЮЩИЙ тик падает на ТОЙ ЖЕ точке, сторож окирпичен, probe7 C/D)."""
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=20)
    toast = _RaisingToast()

    rc = fw.run_tick(now=NOW, toast_fn=toast,
                     reserve_runner=_runner([], _limit_result(RESET)), **p)

    assert rc == 0
    orch = p["orchestrator_log"].read_text(encoding="utf-8")
    assert "тост не показан (factory:usage-limit)" in orch
    assert "toast API unavailable" in orch
    # state ЗАПИСАН после исключения: усвоенное лимитное окно РЕАЛЬНО
    # отражено в state-файле (не заморожено на пред-тиковом значении).
    st = _read_state(p)
    assert st["usage_limit_until"] == fw._fmt_ts(RESET)


def test_limit_back_toast_exception_does_not_crash_run_tick(tmp_path):
    """БЛОКЕР (критик v8.2, второй раунд): `[factory:limit-back]` звало
    `toast_fn` СЫРЫМ (не через `_toast_with_trace`) — исключение уходило
    наружу `run_tick` ДО финального `_write_state`, `usage_limit_until`
    замерзал в ПРОШЛОМ навсегда -> КАЖДЫЙ следующий тик падал на ТОЙ ЖЕ
    точке (сторож окирпичен, probe7 C/D критика). Проверка на площадке
    ВОЗВРАТНОГО тоста (не только входного, как в тесте выше)."""
    p = _paths(tmp_path)
    after_reset = RESET + datetime.timedelta(minutes=1)
    _stalled_setup(p, stalled_since_minutes_ago=600,
                   extra_state={"usage_limit_until": fw._fmt_ts(RESET)})
    toast = _RaisingToast()

    rc = fw.run_tick(now=after_reset, toast_fn=toast,
                     reserve_runner=_runner([], _limit_result(RESET)), **p)

    assert rc == 0
    orch = p["orchestrator_log"].read_text(encoding="utf-8")
    assert "тост не показан (factory:limit-back)" in orch
    assert "toast API unavailable" in orch
    # state ЗАПИСАН после исключения: окно закрылось штатно (grace открыт,
    # usage_limit_until снят) — НЕ заморожено на пред-тиковом значении.
    st = _read_state(p)
    assert st["usage_limit_until"] is None
    assert st["usage_limit_grace_until"] is not None


def test_stalled_toast_exception_does_not_crash_run_tick(tmp_path):
    """БЛОКЕР (критик v8.2, второй раунд): `[factory:stalled]` тоже звало
    `toast_fn` СЫРЫМ на транзиции ok->stalled — та же экспозиция, что
    `[factory:limit-back]`."""
    from test_factory_watchdog_fallback import _mode_snap_dict, _write_mode, _write_sla
    p = _paths(tmp_path)
    _write_sla(p)
    started = NOW - datetime.timedelta(minutes=61)
    _write_state(p, last_state="ok", last_progress_ts=fw._fmt_ts(started),
                last_mode_snapshot=_mode_snap_dict("active", fw._fmt_ts(started)), notes=[])
    _write_mode(p, mode="active", updated_ts=fw._fmt_ts(started))
    toast = _RaisingToast()

    rc = fw.run_tick(now=NOW, toast_fn=toast, stall_no_lock_min=60, **p)

    assert rc == 0
    orch = p["orchestrator_log"].read_text(encoding="utf-8")
    assert "тост не показан (factory:stalled)" in orch
    assert "toast API unavailable" in orch
    # state ЗАПИСАН после исключения: транзиция ok->stalled реально
    # зафиксирована — НЕ заморожена на пред-тиковом "ok".
    st = _read_state(p)
    assert st["last_state"] == "stalled"


def test_ordinary_fallback_toast_failure_leaves_trace(tmp_path):
    """Класс: [factory:fallback] (обычный резервный запуск, БЕЗ лимита) —
    та же трассировка отказа тоста."""
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=20)

    def fail_toast(title, message):
        return False, "no display"

    fw.run_tick(now=NOW, toast_fn=fail_toast,
                reserve_runner=_runner([], {"outcome": "spawned", "child_rc": 0,
                                            "fast_death": False, "holder": "h",
                                            "mode_write": None, "usage_limit": None}), **p)

    orch = p["orchestrator_log"].read_text(encoding="utf-8")
    assert "тост не показан (factory:fallback): no display" in orch


def test_fallback_broken_toast_failure_leaves_trace(tmp_path):
    """Класс: [factory:fallback-broken] (slowdeath-стоп) — та же
    трассировка отказа тоста, что усилена для [factory:usage-limit]."""
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=30, extra_state={
        "slowdeath_streak": 2, "slowdeath_stopped": False})

    def fail_toast(title, message):
        return False, "broken-detail"

    fw.run_tick(now=NOW, toast_fn=fail_toast,
                reserve_runner=_runner([], {"outcome": "timeout_kill", "child_rc": None,
                                            "fast_death": False, "holder": "x",
                                            "mode_write": None}), **p)

    orch = p["orchestrator_log"].read_text(encoding="utf-8")
    assert "тост не показан (factory:fallback-broken): broken-detail" in orch


def test_child_death_toast_failure_leaves_trace(tmp_path):
    """Класс: [factory:child-death] (fastdeath-стоп) — та же трассировка."""
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=30)
    from test_factory_watchdog_fallback import _runner_bumping_fastdeath_to
    from test_factory_watchdog_fallback import _write_fastdeath as _fw_write_fastdeath
    _fw_write_fastdeath(p, count=2, last_ts=fw._fmt_ts(NOW - datetime.timedelta(minutes=5)))

    def fail_toast(title, message):
        return False, "child-detail"

    fw.run_tick(now=NOW, toast_fn=fail_toast,
                reserve_runner=_runner_bumping_fastdeath_to(p, 3), **p)

    orch = p["orchestrator_log"].read_text(encoding="utf-8")
    assert "тост не показан (factory:child-death): child-detail" in orch


def test_fallback_channel_toast_return_value_is_accepted_and_failure_logged(tmp_path):
    """Б2: `[factory:fallback-channel]` (:1233 в ревьюченной версии) ронял
    `toast_fn`-возврат целиком — теперь принят и отказ логируется."""
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=20,
                   extra_state={"unknown_streak": fw.UNKNOWN_STREAK_TOAST - 1})

    def fail_toast(title, message):
        return False, "channel-detail"

    fw.run_tick(now=NOW, toast_fn=fail_toast,
                reserve_runner=_runner([], {"outcome": "spawned", "child_rc": 0,
                                            "fast_death": False, "holder": "h",
                                            "mode_write": None, "usage_limit": None,
                                            }), **p)

    orch = p["orchestrator_log"].read_text(encoding="utf-8")
    assert "тост не показан (factory:fallback-channel): channel-detail" in orch


# ===========================================================================
# Н1: `episode_closed_by_window` истинно и при нечитаемом mode-файле
# (mode_missing -> alarm=False by construction) — это НЕ улика возврата
# лимитов (лимит — свойство аккаунта, не mode-файла).
# ===========================================================================

def test_corrupt_mode_file_mid_window_does_not_clear_usage_limit(tmp_path):
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=200,
                   extra_state={"usage_limit_until": fw._fmt_ts(RESET),
                                "usage_limit_raw": "weekly"})
    # порти mode-файл ПОСЛЕ _stalled_setup (которая пишет валидный mode.json
    # и соответствующий last_mode_snapshot в state) — симулирует порчу
    # ПОСРЕДИ окна, а не с самого начала.
    p["mode_file"].write_bytes(b"{not valid json at all")

    fw.run_tick(now=NOW, toast_fn=_NoToast(),
                reserve_runner=_runner([], _limit_result()), **p)

    st = _read_state(p)
    assert st["usage_limit_until"] == fw._fmt_ts(RESET)


def test_window_progress_still_clears_limit_state_with_readable_mode(tmp_path):
    """Регресс-щит: Н1 не должен ломать существующий позитивный путь
    (`test_window_progress_clears_limit_state`) — читаемый mode-файл с
    реальным прогрессом по-прежнему снимает лимитное окно."""
    p = _paths(tmp_path)
    fresh = NOW - datetime.timedelta(minutes=1)
    _write_state(p, last_state="stalled",
                stalled_since=fw._fmt_ts(NOW - datetime.timedelta(hours=3)),
                last_progress_ts=fw._fmt_ts(fresh),
                usage_limit_until=fw._fmt_ts(RESET), usage_limit_raw="weekly")
    from test_factory_watchdog_fallback import _write_mode, _write_sla
    _write_sla(p)
    _write_mode(p, mode="active", updated_ts=fw._fmt_ts(fresh))

    fw.run_tick(now=NOW, toast_fn=_NoToast(), reserve_runner=_runner([], _limit_result()), **p)

    st = _read_state(p)
    assert st["usage_limit_until"] is None and st["usage_limit_grace_until"] is None


def test_mode_stopped_mid_window_does_not_clear_usage_limit(tmp_path):
    """О2 (решение Lead, критик v8.2, второй раунд): `mode=stopped` — НЕ
    прогресс окна и НЕ снимает `usage_limit_until` (лимит — свойство
    аккаунта; при stopped резерв всё равно гейтится, а после рестарта
    фабрика корректно спит до сброса). Читаемый И ИЗМЕНИВШИЙСЯ mode-снимок
    (active->stopped) раньше засчитывался как «прогресс» — ложно."""
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=200,
                   extra_state={"usage_limit_until": fw._fmt_ts(RESET),
                                "usage_limit_raw": "weekly"})
    from test_factory_watchdog_fallback import _write_mode
    _write_mode(p, mode="stopped")            # читаемый, ВАЛИДНЫЙ JSON, отличается от "active"

    fw.run_tick(now=NOW, toast_fn=_NoToast(),
                reserve_runner=_runner([], _limit_result()), **p)

    st = _read_state(p)
    assert st["usage_limit_until"] == fw._fmt_ts(RESET)


# ===========================================================================
# Н2: щит на мис-распознанные формы подсказки сброса.
# ===========================================================================

def test_relative_in_hours_hint_is_not_computed_as_clock_hour():
    """«resets in 3 hours» — число раньше читалось как ЧАС («03:00»), не
    как «через 3 часа». Момент считается неизвестным (консервативный
    фолбэк), НЕ вычисляется правдоподобной, но ошибочной цифрой."""
    got = hw.parse_usage_limit("You've hit your weekly limit · resets in 3 hours", NOW)
    assert got is not None
    assert got["reset_ts"] is None


def test_relative_in_minutes_hint_is_not_computed():
    got = hw.parse_usage_limit("You've hit your weekly limit · resets in 30 min", NOW)
    assert got is not None
    assert got["reset_ts"] is None


@needs_tz
def test_tomorrow_hint_is_not_computed_as_today():
    """«tomorrow at 9am (America/Los_Angeles)» — слово 'tomorrow' раньше
    игнорировалось молча, час+зона давали момент СЕГОДНЯ (на СУТКИ раньше
    настоящего). Момент считается неизвестным."""
    got = hw.parse_usage_limit(
        "You've hit your weekly limit · resets tomorrow at 9am "
        "(America/Los_Angeles)", NOW)
    assert got is not None
    assert got["reset_ts"] is None
    # Регресс-щит: старое поведение — СЕГОДНЯ 9am LA (PDT=UTC-7) = 16:00Z,
    # на сутки раньше настоящего значения.
    assert got["reset_ts"] != datetime.datetime(2026, 8, 17, 16, 0,
                                                tzinfo=datetime.timezone.utc)


def test_bare_hour_without_ampm_or_tz_is_not_guessed():
    """Час БЕЗ am/pm И БЕЗ зоны — неоднозначная форма (не отличить от
    постороннего числа/относительной формы регулярным выражением).
    Момент неизвестен, тот же консервативный фолбэк."""
    got = hw.parse_usage_limit("You've hit your weekly limit · resets 14", NOW)
    assert got is not None
    assert got["reset_ts"] is None


@needs_tz
def test_square_bracket_zone_is_recognized():
    """Н2: квадратная скобка — НОСИТЕЛЬ зоны, не безусловный разделитель
    клаузы. «resets 2am [Europe/Paris]» раньше была НЕДОСТИЖИМА:
    `_clause_text` обрезал бы клаузу ДО зоны."""
    got = hw.parse_usage_limit(
        "You've hit your weekly limit · resets 2am [Europe/Paris]", NOW)
    assert got is not None
    # 02:00 CEST (Paris, UTC+2) следующих суток = 2026-08-18T00:00Z — та же
    # арифметика, что REAL_LINE (круглые скобки), просто зона в квадратных.
    assert got["reset_ts"] == datetime.datetime(2026, 8, 18, 0, 0,
                                                tzinfo=datetime.timezone.utc)


# ===========================================================================
# Н3: `usage_limit_until` дефолтный (не замер) — флаг «момент угадан»
# переживает окно, возвратный тост хеджирует формулировку.
# ===========================================================================

def test_return_toast_is_hedged_when_reset_moment_was_estimated(tmp_path):
    p = _paths(tmp_path)
    after_reset = RESET + datetime.timedelta(minutes=1)
    _stalled_setup(p, stalled_since_minutes_ago=600,
                   extra_state={"usage_limit_until": fw._fmt_ts(RESET),
                                "usage_limit_estimated": True})
    toast = _NoToast()

    fw.run_tick(now=after_reset, toast_fn=toast,
                reserve_runner=_runner([], _limit_result(RESET)), **p)

    msg = dict(toast.calls)["[factory:limit-back]"]
    assert "оценкой" in msg or "вероятно" in msg


def test_return_toast_is_not_hedged_when_reset_moment_was_measured(tmp_path):
    """Регресс-щит: `usage_limit_estimated=False` (замер, не дефолт) —
    прежняя формулировка БЕЗ хеджа."""
    p = _paths(tmp_path)
    after_reset = RESET + datetime.timedelta(minutes=1)
    _stalled_setup(p, stalled_since_minutes_ago=600,
                   extra_state={"usage_limit_until": fw._fmt_ts(RESET),
                                "usage_limit_estimated": False})
    toast = _NoToast()

    fw.run_tick(now=after_reset, toast_fn=toast,
                reserve_runner=_runner([], _limit_result(RESET)), **p)

    msg = dict(toast.calls)["[factory:limit-back]"]
    assert "оценкой" not in msg and "вероятно" not in msg
    assert "толкни окно" in msg


# ===========================================================================
# О5 (критик v8.2, второй раунд): хеджировать и ВХОДНОЙ тост при
# usage_limit_estimated («фабрика спит примерно до ... (момент — оценка)»);
# пометка estimated — тоже при срезании поясом MAX_LIMIT_SLEEP_H.
# ===========================================================================

def test_input_toast_is_hedged_when_reset_moment_is_estimated(tmp_path):
    """О5: reset_ts не распознан парсером -> дефолтный сон -> входной тост
    ОБЯЗАН хеджировать («примерно», «оценка»), симметрично Н3."""
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=20)
    toast = _NoToast()

    fw.run_tick(now=NOW, toast_fn=toast,
                reserve_runner=_runner([], _limit_result(reset_ts=None, reset_hint=None)), **p)

    msg = dict(toast.calls)["[factory:usage-limit]"]
    assert "оценка" in msg


def test_input_toast_is_not_hedged_when_reset_moment_is_measured(tmp_path):
    """Регресс-щит: reset_ts РЕАЛЬНО измерен парсером — прежняя
    формулировка БЕЗ хеджа."""
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=20)
    toast = _NoToast()

    fw.run_tick(now=NOW, toast_fn=toast,
                reserve_runner=_runner([], _limit_result(RESET)), **p)

    msg = dict(toast.calls)["[factory:usage-limit]"]
    assert "оценка" not in msg
    assert "лимиты подписки кончились — фабрика спит до" in msg


def test_belt_capped_reset_marks_estimated_and_hedges_input_toast(tmp_path):
    """О5: срез поясом `MAX_LIMIT_SLEEP_H` — тоже "оценка", не замер
    (ПРИМЕНЁННЫЙ момент отличается от ИЗМЕРЕННОГО вендором, даже если
    парсер сам отработал безошибочно) — флаг `usage_limit_estimated`
    переживает окно, входной тост хеджирует."""
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=20)
    way_beyond = NOW + datetime.timedelta(hours=fw.MAX_LIMIT_SLEEP_H, seconds=1)
    toast = _NoToast()

    fw.run_tick(now=NOW, toast_fn=toast,
                reserve_runner=_runner([], _limit_result(way_beyond)), **p)

    msg = dict(toast.calls)["[factory:usage-limit]"]
    assert "оценка" in msg
    st = _read_state(p)
    assert st["usage_limit_estimated"] is True


def test_reset_ts_within_belt_is_not_marked_estimated(tmp_path):
    """Регресс-щит: reset_ts В ПРЕДЕЛАХ пояса (не срезан) и РЕАЛЬНО
    измерен — НЕ помечается estimated, входной тост БЕЗ хеджа."""
    p = _paths(tmp_path)
    _stalled_setup(p, stalled_since_minutes_ago=20)
    toast = _NoToast()

    fw.run_tick(now=NOW, toast_fn=toast,
                reserve_runner=_runner([], _limit_result(RESET)), **p)

    st = _read_state(p)
    assert st["usage_limit_estimated"] is False
