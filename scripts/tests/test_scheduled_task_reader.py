"""Юнит-тесты scripts/scheduled_task_reader.py — единый локале-независимый
ридер State/LastRunTime задачи планировщика (spec-factory-window v6
К5а/К5в, 2026-08-16). Пин-тест на ФИКСТУРЕ вывода `ConvertTo-Json`
(subprocess подменён — живой powershell.exe трогать не нужно, реальная
проба — witness прогона builder'а/N6)."""
from __future__ import annotations

import subprocess

import scheduled_task_reader as str_reader


class _FakeCompleted:
    """Мок CompletedProcess. Н-9: реальный вызов теперь БЕЗ text=True —
    stdout/stderr это bytes (stdout утилита декодирует utf-8, stderr —
    oem/cp866). Мок принимает str для удобства фикстур и кодирует сам."""
    def __init__(self, returncode, stdout="", stderr="", stderr_encoding="cp866"):
        self.returncode = returncode
        self.stdout = stdout.encode("utf-8") if isinstance(stdout, str) else stdout
        self.stderr = (stderr.encode(stderr_encoding)
                       if isinstance(stderr, str) else stderr)


def test_ok_state_and_last_run_parsed_from_json_fixture(monkeypatch):
    """Фикстура — ДОСЛОВНЫЙ вид вывода живой пробы (см. witness builder'а):
    {"State":"Disabled","LastRunTime":"2026-08-16T12:30:01.0000000+02:00"}"""
    def fake_run(args, **kwargs):
        assert args[0] == str_reader.POWERSHELL
        assert "-Command" in args
        return _FakeCompleted(
            0, stdout='{"State":"Disabled","LastRunTime":'
                      '"2026-08-16T12:30:01.0000000+02:00"}\n')
    monkeypatch.setattr(subprocess, "run", fake_run)

    result = str_reader.read_task_state("AO3-QA-Heartbeat")

    assert result.ok
    assert result.state == "Disabled"
    assert result.last_run is not None
    assert result.last_run.year == 2026 and result.last_run.month == 8


def test_stderr_cyrillic_is_decoded_readable(monkeypatch):
    """Н-9 (пин критика r3, дословно): stderr powershell.exe — OEM (cp866);
    utf-8-декод давал mojibake. Тест дискриминирует: падает на откате
    oem->utf-8 (проверено критиком исключающим прогоном), проходит на
    поставляемом модуле. Все прочие stderr-фикстуры ASCII — без этого
    пина откат фикса проходил зелёным."""
    def fake_run(args, **kwargs):
        return _FakeCompleted(1, stderr="Не найдены объекты MSFT_ScheduledTask")
    monkeypatch.setattr(subprocess, "run", fake_run)
    result = str_reader.read_task_state("No-Such-Task")
    assert not result.ok
    assert "Не найдены объекты" in result.error


def test_ok_state_ready_no_last_run_yet(monkeypatch):
    """Критик-фикс Н-1 (2026-08-16, эмпирика критика: 0 из 200 задач дают
    null): «никогда не запускалась» PowerShell кодирует OLE-эпохи
    сентинелом (живая форма, не `null` — `if ($i.LastRunTime)` для
    DateTime всегда truthy). Фикстура несёт РЕАЛЬНО НАБЛЮДАЕМУЮ форму —
    last_run обязан распознаться как «нет» (None), не как настоящая дата."""
    def fake_run(args, **kwargs):
        return _FakeCompleted(
            0, stdout='{"State":"Ready","LastRunTime":'
                      '"1999-11-30T00:00:00.0000000+02:00"}\n')
    monkeypatch.setattr(subprocess, "run", fake_run)

    result = str_reader.read_task_state("AO3-QA-Heartbeat")

    assert result.ok
    assert result.state == "Ready"
    assert result.last_run is None


def test_null_last_run_still_handled_as_none(monkeypatch):
    """Буквальный `null` (если PowerShell когда-нибудь его всё же отдаст)
    остаётся легальным путём к last_run=None — не единственный, но не
    удалён."""
    def fake_run(args, **kwargs):
        return _FakeCompleted(0, stdout='{"State":"Ready","LastRunTime":null}\n')
    monkeypatch.setattr(subprocess, "run", fake_run)

    result = str_reader.read_task_state("AO3-QA-Heartbeat")

    assert result.ok
    assert result.last_run is None


def test_sentinel_cutoff_boundary_exactly_2000_is_real_date(monkeypatch):
    """Граница НА пороге сентинела (ровно 2000-01-01 UTC) — считается
    РЕАЛЬНОЙ датой (`<`, не `<=`)."""
    def fake_run(args, **kwargs):
        return _FakeCompleted(0, stdout='{"State":"Ready","LastRunTime":'
                              '"2000-01-01T00:00:00.0000000+00:00"}\n')
    monkeypatch.setattr(subprocess, "run", fake_run)

    result = str_reader.read_task_state("AO3-QA-Heartbeat")

    assert result.ok
    assert result.last_run is not None
    assert result.last_run.year == 2000


def test_sentinel_cutoff_boundary_just_before_2000_is_sentinel(monkeypatch):
    """Граница ЗА порогом (1999-12-31 23:59:59 UTC) — сентинел -> None."""
    def fake_run(args, **kwargs):
        return _FakeCompleted(0, stdout='{"State":"Ready","LastRunTime":'
                              '"1999-12-31T23:59:59.0000000+00:00"}\n')
    monkeypatch.setattr(subprocess, "run", fake_run)

    result = str_reader.read_task_state("AO3-QA-Heartbeat")

    assert result.ok
    assert result.last_run is None


def test_task_not_found_is_not_ok(monkeypatch):
    """Запрос не удался (rc!=0, задача не существует) -> ok=False, «н/п»,
    НЕ факт отсутствия задачи (F-30 CLAUDE.md)."""
    def fake_run(args, **kwargs):
        return _FakeCompleted(1, stdout="", stderr="Cannot find scheduled task 'X'.")
    monkeypatch.setattr(subprocess, "run", fake_run)

    result = str_reader.read_task_state("No-Such-Task")

    assert not result.ok
    assert result.error


def test_powershell_binary_missing_is_not_ok(monkeypatch):
    def fake_run(args, **kwargs):
        raise OSError("powershell.exe not found")
    monkeypatch.setattr(subprocess, "run", fake_run)

    result = str_reader.read_task_state("AO3-QA-Heartbeat")

    assert not result.ok
    assert "не удался" in result.error


def test_timeout_is_not_ok(monkeypatch):
    def fake_run(args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args, timeout=kwargs.get("timeout", 30))
    monkeypatch.setattr(subprocess, "run", fake_run)

    result = str_reader.read_task_state("AO3-QA-Heartbeat")

    assert not result.ok


def test_unparseable_output_is_not_ok(monkeypatch):
    def fake_run(args, **kwargs):
        return _FakeCompleted(0, stdout="not json at all")
    monkeypatch.setattr(subprocess, "run", fake_run)

    result = str_reader.read_task_state("AO3-QA-Heartbeat")

    assert not result.ok
    assert "не парсится" in result.error


def test_unparseable_last_run_is_not_ok(monkeypatch):
    def fake_run(args, **kwargs):
        return _FakeCompleted(0, stdout='{"State":"Ready","LastRunTime":"garbage"}\n')
    monkeypatch.setattr(subprocess, "run", fake_run)

    result = str_reader.read_task_state("AO3-QA-Heartbeat")

    assert not result.ok
    assert result.state == "Ready"          # State успел распарситься до отказа на дате


def test_task_name_is_single_quote_escaped_in_command():
    """Инъекция через имя задачи с одинарной кавычкой не ломает команду
    (удвоение кавычки — стандартное PowerShell-экранирование)."""
    assert str_reader._ps_escape("O'Brien") == "'O''Brien'"


def test_cli_ok_prints_state_and_exit_0(monkeypatch, capsys):
    def fake_run(args, **kwargs):
        return _FakeCompleted(0, stdout='{"State":"Ready","LastRunTime":null}\n')
    monkeypatch.setattr(subprocess, "run", fake_run)

    code = str_reader.main(["AO3-QA-Heartbeat"])

    assert code == 0
    out = capsys.readouterr().out
    assert "state=Ready" in out and "last_run=None" in out


def test_cli_error_prints_error_and_exit_1(monkeypatch, capsys):
    def fake_run(args, **kwargs):
        return _FakeCompleted(1, stderr="boom")
    monkeypatch.setattr(subprocess, "run", fake_run)

    code = str_reader.main(["No-Such-Task"])

    assert code == 1
    out = capsys.readouterr().out
    assert "error=" in out
