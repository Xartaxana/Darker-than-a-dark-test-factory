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
