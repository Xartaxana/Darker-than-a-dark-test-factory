"""Device-free матрица веток `adb.pull_app_file` (AT-BUG-069) — различение
«WAL/SHM легитимно отсутствуют» от «run-as/транспорт реально не удался».

Живой сверкой на emulator-5554 (5 сценариев: реальный файл, синтетически
отсутствующий путь, легитимно-пустой WAL, несуществующий пакет для `run-as`,
несуществующая серийка устройства — см. докстринг `pull_app_file`)
подтверждено, что `adb exec-out` сливает remote stdout+stderr в ОДИН
локальный `cp.stdout` с `cp.returncode == 0` независимо от того, было ли
это реальное содержимое файла или текст ошибки `cat`/`run-as` — старая
проверка `cp.returncode != 0 or not cp.stdout` была готова записать текст
ошибки `cat` в `dest`, как будто это байты файла (на синтетически
отсутствующем пути, где `cat` не выводит пустую строку, а печатает
`No such file or directory` — непустой `stdout`, `returncode == 0`).

Мокает `subprocess.run` НА УРОВНЕ МОДУЛЯ `framework.core.adb` (тот же приём,
что `test_subprocess_timeout_unit.py`/AT-BUG-009,
`test_adb_run_as_file_or_raise_unit.py`/AT-BUG-055) — тест ловит регресс в
РЕАЛЬНОМ коде `pull_app_file`, не в подменённой обёртке.
"""
from __future__ import annotations

import subprocess

import allure
import pytest

from framework.core import adb

_SENTINEL = adb._PULL_RC_SENTINEL  # b"\nAT_BUG_069_PULL_RC="


@pytest.fixture(scope="session", autouse=True)
def _ensure_app_installed():
    yield


def _completed(stdout: bytes, stderr: bytes = b"", returncode: int = 0):
    return subprocess.CompletedProcess(args=["adb"], returncode=returncode,
                                        stdout=stdout, stderr=stderr)


def _pull_with_fake_output(cp: subprocess.CompletedProcess, monkeypatch, tmp_path):
    captured_args: list[list[str]] = []

    def _fake_run(args, **kw):
        captured_args.append(args)
        return cp

    monkeypatch.setattr(subprocess, "run", _fake_run)
    dest = tmp_path / "pulled.bin"
    try:
        ok = adb.pull_app_file("databases/ao3_ratings.db-wal", dest)
    except RuntimeError as e:
        return "runtime", str(e), captured_args
    finally:
        assert captured_args, "subprocess.run не был вызван"
        assert "run-as" in captured_args[0] and "exec-out" in captured_args[0]
    return "ok", ok, dest.read_bytes() if dest.exists() else None


CASES = [
    # --- маркер найден, rc==0, контент непуст: cat реально прочитал файл ---
    pytest.param(
        _completed(b"SQLite format 3\x00binary\xff" + _SENTINEL + b"0"),
        "ok", (True, b"SQLite format 3\x00binary\xff"),
        id="rc0-real-binary-content",
    ),
    # --- маркер найден, rc==0, контент пуст: легитимно пустой файл (0 байт) ---
    pytest.param(
        _completed(_SENTINEL + b"0"),
        "ok", (False, None),
        id="rc0-empty-content-legit",
    ),
    # --- маркер найден, rc!=0: cat сам не смог прочитать (типично ENOENT) ---
    # ЭТО САМ БЛОКЕР AT-BUG-069: до фикса непустой stdout (текст ошибки cat)
    # с returncode==0 (уровня adb-клиента) писался в dest как будто содержимое.
    pytest.param(
        _completed(b"cat: databases/ao3_ratings.db-wal: No such file or directory\n" + _SENTINEL + b"1"),
        "ok", (False, None),
        id="rc1-cat-error-text-not-written-as-content",
    ),
    pytest.param(
        _completed(_SENTINEL + b"1"),
        "ok", (False, None),
        id="rc1-no-content-legit-missing",
    ),
    pytest.param(
        _completed(_SENTINEL + b"2"),
        "ok", (False, None),
        id="rc2-no-content-legit-missing",
    ),
    # --- маркер отсутствует вовсе: run-as/remote-shell не выполнились ---
    pytest.param(
        _completed(b"run-as: unknown package: com.example.ao3_wrapper\n"),
        "runtime", None,
        id="run-as-unknown-package-no-sentinel",
    ),
    pytest.param(
        _completed(b"", stderr=b"error: device 'emulator-9999' not found\r\n", returncode=-1),
        "runtime", None,
        id="adb-client-device-not-found-no-sentinel",
    ),
    pytest.param(
        _completed(b""),
        "runtime", None,
        id="transport-fully-empty-no-sentinel",
    ),
    # --- код возврата не распознан (мусор после sentinel): маркер САМ по себе
    # найден (значит remote sh дошёл до printf), только цифры повреждены —
    # это НЕ тот же класс, что «маркер отсутствует вовсе»; трактуется как
    # rc=None (!= 0) -> False, тем же путём, что легитимно-нечитаемый rc ---
    pytest.param(
        _completed(_SENTINEL + b"abc"),
        "ok", (False, None),
        id="malformed-rc-not-numeric-treated-as-not-ok",
    ),
]


@pytest.mark.p1
@allure.id("AT-BUG-069-pull-app-file-branch-matrix")
@allure.title("adb.pull_app_file — fail-closed матрица (реальный контент/легитимно отсутствует/транспорт не удался)")
@pytest.mark.parametrize("cp,expected_kind,expected_value", CASES)
def test_branch(cp, expected_kind, expected_value, monkeypatch, tmp_path):
    kind, value, extra = _pull_with_fake_output(cp, monkeypatch, tmp_path)
    assert kind == expected_kind, (
        f"на вход stdout={cp.stdout!r}: ожидали {expected_kind}, получили {kind} ({value})"
    )
    if expected_kind == "ok":
        expected_ok, expected_content = expected_value
        assert value == expected_ok, f"на вход stdout={cp.stdout!r}: ok={value} != {expected_ok}"
        if expected_ok:
            assert extra == expected_content, f"записанный контент {extra!r} != {expected_content!r}"
        else:
            assert extra is None, f"не должно быть записанного файла, получили {extra!r}"


@pytest.mark.p1
@allure.id("AT-BUG-069-pull-app-file-regression-lock-no-error-text-as-content")
@allure.title("Регресс-замок: текст ошибки cat/run-as НЕ пишется в dest как содержимое файла (AT-BUG-069 сам блокер)")
def test_run_as_failure_does_not_write_error_text_as_file_content(monkeypatch, tmp_path):
    """До фикса: `run-as: unknown package: ...` (непустой stdout, returncode==0
    уровня adb-клиента) прошёл бы условие `cp.returncode != 0 or not cp.stdout`
    как False и был бы молча записан в `dest` как будто это байты файла,
    вернув `True` — вызывающий код (`_pull_baseline`) считал бы файл успешно
    снятым. Явный регресс-замок: тот же вход теперь обязан кидать
    `RuntimeError`, не молчаливый `True` с мусором в `dest`."""
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **kw: _completed(b"run-as: unknown package: com.example.ao3_wrapper\n"),
    )
    dest = tmp_path / "pulled.bin"
    with pytest.raises(RuntimeError, match="AT-BUG-069"):
        adb.pull_app_file("databases/ao3_ratings.db-wal", dest)
    assert not dest.exists(), "файл НЕ должен быть создан на transport/run-as-failure ветке"


# --- AT-BUG-069 rework attempt 2 (критик-вход): регресс attempt1 —
# незаквоченная интерполяция `rel_path` в remote `sh -c '...'`-строку.
# Старые 10 кейсов выше мокают `subprocess.run` и целиком подставляют
# готовый CompletedProcess — они НЕ смотрят на СОСТАВ построенной команды,
# поэтому не видят класс «argv не заквотирован». Кейсы ниже проверяют
# именно argv/rel_path-обработку, а не только ветвление по rc/маркеру.

@pytest.mark.p1
@allure.id("AT-BUG-069-pull-app-file-argv-quoted-space-path")
@allure.title("adb.pull_app_file — rel_path с пробелом заквочен одинарными кавычками в remote-команде (attempt2-регресс)")
def test_rel_path_with_space_is_single_quoted_in_remote_command(monkeypatch, tmp_path):
    """Критик живьём подтвердил на emulator-5554: путь с пробелом
    (`files/critic_sp ace.bin`, существующий читаемый файл) с НЕзаквоченной
    attempt1-командой ломался на два `cat`-аргумента -> `False` вместо
    `True`+байты (регресс той же путаницы «легитимно нет» vs «сбой»,
    которую весь фикс должен устранять). Здесь без устройства: проверяем,
    что построенная remote-команда действительно содержит путь ЗАКВОЧЕННЫМ
    одинарными кавычками — `'files/critic_sp ace.bin'`, а не голым
    `files/critic_sp ace.bin`, который `sh -c` разбил бы по пробелу."""
    rel_path = "files/critic_sp ace.bin"
    captured_args: list[list[str]] = []

    def _fake_run(args, **kw):
        captured_args.append(args)
        return _completed(b"real bytes" + _SENTINEL + b"0")

    monkeypatch.setattr(subprocess, "run", _fake_run)
    dest = tmp_path / "pulled.bin"
    ok = adb.pull_app_file(rel_path, dest)

    assert ok is True
    assert dest.read_bytes() == b"real bytes"
    assert captured_args, "subprocess.run не был вызван"
    remote_cmd = captured_args[0][-1]  # последний элемент argv — строка для sh -c
    assert f"'{rel_path}'" in remote_cmd, (
        f"путь должен быть заквочен одинарными кавычками в remote-команде, "
        f"получили: {remote_cmd!r}"
    )
    # незаквоченная форма (attempt1-регресс) НЕ должна встречаться отдельно
    assert f"cat {rel_path};" not in remote_cmd


@pytest.mark.p1
@allure.id("AT-BUG-069-pull-app-file-empty-rel-path-quoted-not-stdin")
@allure.title("adb.pull_app_file — пустой rel_path остаётся явным `''`, не голым cat-без-операнда (attempt2-регресс, hang)")
def test_empty_rel_path_is_quoted_not_left_bare_for_stdin_cat(monkeypatch, tmp_path):
    """Критик живьём подтвердил: attempt1 на пустой/пробельный `rel_path` давал
    `cat` БЕЗ операнда -> `cat` читает STDIN -> вызов ВИСИТ до
    `ADB_TRANSFER_TIMEOUT` (120s) вместо мгновенной ошибки (критик получил
    мгновенную ошибку ~0.1s после фикса). Здесь без устройства (мок не
    зависает по определению) — проверяем, что построенная remote-команда
    для пустого `rel_path` содержит явную пару кавычек `''` (валидный,
    хоть и пустой, операнд `cat`), а НЕ голое `cat ;` (что и есть форма,
    дающая чтение STDIN)."""
    captured_args: list[list[str]] = []

    def _fake_run(args, **kw):
        captured_args.append(args)
        return _completed(b"cat: '': No such file or directory\n" + _SENTINEL + b"1")

    monkeypatch.setattr(subprocess, "run", _fake_run)
    dest = tmp_path / "pulled.bin"
    ok = adb.pull_app_file("", dest)

    assert ok is False
    assert not dest.exists()
    assert captured_args, "subprocess.run не был вызван"
    remote_cmd = captured_args[0][-1]
    assert "cat '';" in remote_cmd, (
        f"пустой rel_path должен остаться явным пустым операндом `''`, "
        f"а не голым `cat ;` (stdin-чтение/hang), получили: {remote_cmd!r}"
    )
    assert "cat ;" not in remote_cmd


@pytest.mark.p1
@allure.id("AT-BUG-069-pull-app-file-rel-path-single-quote-rejected")
@allure.title("adb.pull_app_file — rel_path с одинарной кавычкой отклоняется ValueError fail-closed (attempt2)")
def test_rel_path_with_single_quote_rejected_fail_closed_before_subprocess(monkeypatch, tmp_path):
    """`rel_path` — всегда module-level константа (`seed_db._DB_REL`/`_WAL`/
    `_SHM`), не пользовательский ввод, но одинарная кавычка ВНУТРИ пути
    сломала бы само квотирование remote-команды (закрыла бы кавычку раньше
    срока, открыв путь для инъекции метасимволов) — fail-closed: явный
    `ValueError` ДО похода на устройство, subprocess.run вообще не
    вызывается."""
    called = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: called.append(1))
    dest = tmp_path / "pulled.bin"
    with pytest.raises(ValueError):
        adb.pull_app_file("databases/evil'; rm -rf /data; echo '.db", dest)
    assert not called, "subprocess.run НЕ должен вызываться при отклонённом rel_path"
    assert not dest.exists()
