"""Device-free квотирование `adb.run_as_file_or_raise`/`adb.push_app_file`
(AT-BUG-079) — симметричный B4-фикс класса AT-BUG-069 («Чини класс, а не
экземпляр»): критик-триаж AT-BUG-069 round2 (class_completeness audit) нашёл
ДВЕ функции в `framework/core/adb.py`, интерполирующие пути в remote
shell-команды БЕЗ кавычек — `run_as_file_or_raise` (line 378) и
`push_app_file` (line 556). Долг был latent (все текущие вызывающие передают
module-константы без пробелов/метасимволов), но класс дефекта требовал
симметричного лечения.

Обе функции квотируются РАЗНО, потому что удалённый транспорт у них разный
(докстринги самих функций в `adb.py` объясняют подробно):

- `run_as_file_or_raise` идёт через `shell()` — ОДНА pre-joined python-строка,
  отправляемая `adb shell <строка>` ОДНИМ argv-элементом. Удалённая сторона
  парсит её ДВАЖДЫ: implicit remote shell (извлекает аргумент `-c`) и затем
  явный ВНУТРЕННИЙ `sh -c` (парсит СВОЙ аргумент как отдельную команду). Нужны
  ОБА уровня защиты: одинарные кавычки вокруг `path` (внутренний уровень) +
  `shlex.quote()` всей `-c`-строки (внешний уровень).
- `push_app_file` эксекает `cp` НАПРЯМУЮ через `run-as` (без явного `sh -c`
  внутри) — единственный уровень удалённого shell-парсинга, одиночного
  квотирования одинарными кавычками достаточно (тот же приём, что
  `pull_app_file`, AT-BUG-069 rework attempt 2).

Тесты ниже верифицируют СТРОКОВУЮ/токенную структуру построенных команд (без
устройства — тот же приём, что `test_pull_app_file_fail_closed_unit.py`
argv-quoted тесты) и включают явную «красную пробу»: тот же
`shlex.split()`-приём двойного разбора, применённый к СТАРОЙ (до AT-BUG-079)
незаквоченной форме команды, реально расщепляет путь с пробелом на несколько
токенов — доказывая, что тест различает квотированную/неквотированную версию,
а не просто проверяет наличие кавычек где-то в строке."""
from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

import allure
import pytest

from framework.core import adb


@pytest.fixture(scope="session", autouse=True)
def _ensure_app_installed():
    yield


# --- run_as_file_or_raise ---------------------------------------------------

def _capture_cmd_for_path(path: str, monkeypatch) -> str:
    captured: list[str] = []

    def _fake_shell(cmd: str, timeout: float = 0) -> str:
        captured.append(cmd)
        return f"content\n{adb._RUN_AS_FILE_RC_SENTINEL}0"

    monkeypatch.setattr(adb, "shell", _fake_shell)
    adb.run_as_file_or_raise(path)
    assert captured, "adb.shell() не был вызван"
    return captured[0]


@pytest.mark.p1
@allure.id("AT-BUG-079-run-as-file-or-raise-argv-quoted-space-path")
@allure.title("adb.run_as_file_or_raise — path с пробелом остаётся ОДНИМ токеном через оба shell-слоя (AT-BUG-079)")
def test_run_as_file_or_raise_path_with_space_survives_both_shell_layers(monkeypatch):
    path = "shared_prefs/ao3 settings.xml"
    cmd = _capture_cmd_for_path(path, monkeypatch)

    # --- внешний слой: implicit remote shell, парсящий ВСЮ cmd-строку ---
    outer_tokens = shlex.split(cmd)
    assert outer_tokens[:4] == ["run-as", adb._PKG, "sh", "-c"], (
        f"неожиданная структура внешних токенов: {outer_tokens!r}"
    )
    assert len(outer_tokens) == 5, (
        "внешний shell-слой должен видеть РОВНО ОДИН аргумент -c (script), "
        f"получили {len(outer_tokens)} токенов: {outer_tokens!r} — значит "
        "path сломал внешнее квотирование (shlex.quote слой)"
    )
    inner_script = outer_tokens[4]

    # --- внутренний слой: явный `sh -c`, парсящий СВОЙ аргумент заново ---
    inner_tokens = shlex.split(inner_script)
    assert inner_tokens[0] == "cat"
    assert inner_tokens[1] == path, (
        f"path должен остаться ОДНИМ токеном для внутреннего sh -c, "
        f"получили {inner_tokens!r}"
    )


@pytest.mark.p1
@allure.id("AT-BUG-079-run-as-file-or-raise-red-probe-unquoted-would-split")
@allure.title("Красная проба: старая незаквоченная форма реально разбивает path с пробелом на токены (AT-BUG-079)")
def test_unquoted_form_would_split_space_path_into_two_tokens():
    """Строит СТАРУЮ (до AT-BUG-079) незаквоченную форму команды напрямую по
    тексту докстринга бага/git-истории — без монки-патча, без похода в
    текущий код — и применяет ТОТ ЖЕ приём двойного `shlex.split()`, которым
    верифицирован фикс выше. На НЕзаквоченной path с пробелом путь реально
    расщепляется на ДВА токена внутреннего sh -c вместо одного: это и есть
    регресс, который AT-BUG-079 закрывает, и доказательство, что тест выше
    различает квотированную/неквотированную версию, а не просто ищет
    подстроку."""
    path = "shared_prefs/ao3 settings.xml"
    sentinel = adb._RUN_AS_FILE_RC_SENTINEL
    old_unquoted_cmd = (
        f"run-as {adb._PKG} sh -c 'cat {path} 2>/dev/null; echo {sentinel}$?'"
    )
    outer_tokens = shlex.split(old_unquoted_cmd)
    inner_script = outer_tokens[4]
    inner_tokens = shlex.split(inner_script)
    assert inner_tokens[1] != path, (
        "красная проба ожидала РЕГРЕСС старой незаквоченной формы (path "
        f"расколот на 2 токена), получили ОДИН токен {inner_tokens!r} — "
        "проба перестала что-либо различать"
    )
    assert inner_tokens[1] == "shared_prefs/ao3"
    assert inner_tokens[2] == "settings.xml"


@pytest.mark.p1
@allure.id("AT-BUG-079-run-as-file-or-raise-single-quote-rejected")
@allure.title("adb.run_as_file_or_raise — path с одинарной кавычкой отклоняется ValueError fail-closed (AT-BUG-079)")
def test_run_as_file_or_raise_path_with_single_quote_rejected(monkeypatch):
    called: list[str] = []
    monkeypatch.setattr(adb, "shell", lambda cmd, timeout=0: called.append(cmd))
    with pytest.raises(ValueError):
        adb.run_as_file_or_raise("shared_prefs/evil'; rm -rf /data; echo '.xml")
    assert not called, "adb.shell() НЕ должен вызываться при отклонённом path"


# --- push_app_file -----------------------------------------------------------

def _push_with_fake_run(src: Path, rel_path: str, monkeypatch, returncode: int = 0):
    calls: list[list[str]] = []

    def _fake_run(args, timeout=None, **kw):
        calls.append(args)
        return subprocess.CompletedProcess(args=args, returncode=returncode, stdout="", stderr="")

    monkeypatch.setattr(adb, "_run", _fake_run)
    adb.push_app_file(src, rel_path)
    return calls


@pytest.mark.p1
@allure.id("AT-BUG-079-push-app-file-argv-quoted-space-paths")
@allure.title("adb.push_app_file — tmp/rel_path с пробелом остаются целыми токенами remote cp-команды (AT-BUG-079)")
def test_push_app_file_paths_with_space_survive_single_shell_layer(monkeypatch):
    src = Path("fixtures/db space.db")
    rel_path = "files/dst rel.db"
    calls = _push_with_fake_run(src, rel_path, monkeypatch)

    tmp = f"/data/local/tmp/{src.name}"
    push_calls = [a for a in calls if len(a) >= 3 and a[2] == "push"]
    assert push_calls, f"ожидали adb push вызов, получили {calls!r}"
    assert push_calls[0][3] == str(src) and push_calls[0][4] == tmp

    shell_calls = [a for a in calls if len(a) >= 3 and a[2] == "shell"]
    assert len(shell_calls) == 2, (
        f"ожидали 2 shell-вызова (cp + rm -f), получили {len(shell_calls)}: {calls!r}"
    )

    cp_cmd = shell_calls[0][-1]
    cp_tokens = shlex.split(cp_cmd)
    assert cp_tokens == ["run-as", adb._PKG, "cp", tmp, rel_path], (
        f"tmp/rel_path должны остаться ЦЕЛЫМИ токенами cp-команды, "
        f"получили {cp_tokens!r} из {cp_cmd!r}"
    )

    rm_cmd = shell_calls[1][-1]
    rm_tokens = shlex.split(rm_cmd)
    assert rm_tokens == ["rm", "-f", tmp], (
        f"tmp должен остаться ЦЕЛЫМ токеном rm-команды, получили {rm_tokens!r}"
    )


@pytest.mark.p1
@allure.id("AT-BUG-079-push-app-file-red-probe-unquoted-would-split")
@allure.title("Красная проба: старая незаквоченная cp-команда реально разбивает rel_path с пробелом на токены (AT-BUG-079)")
def test_push_app_file_unquoted_form_would_split_space_path():
    """Тот же приём, что для `run_as_file_or_raise` выше: строит СТАРУЮ (до
    AT-BUG-079) незаквоченную форму `run-as PKG cp tmp rel_path` напрямую и
    показывает, что `shlex.split()` реально расщепляет `rel_path` с пробелом
    на два токена — доказательство, что тест выше действительно различает
    квотированную/неквотированную версию."""
    tmp = "/data/local/tmp/db.db"
    rel_path = "files/dst rel.db"
    old_unquoted_cmd = f"run-as {adb._PKG} cp {tmp} {rel_path}"
    tokens = shlex.split(old_unquoted_cmd)
    assert tokens != ["run-as", adb._PKG, "cp", tmp, rel_path], (
        "красная проба ожидала РЕГРЕСС старой незаквоченной формы "
        f"(rel_path расколот), получили {tokens!r} нетронутым"
    )
    assert tokens[-2:] == ["files/dst", "rel.db"]


@pytest.mark.p1
@allure.id("AT-BUG-079-push-app-file-single-quote-rejected")
@allure.title("adb.push_app_file — rel_path с одинарной кавычкой отклоняется ValueError fail-closed ДО первого _run (AT-BUG-079)")
def test_push_app_file_rel_path_with_single_quote_rejected(monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(
        adb, "_run",
        lambda args, timeout=None, **kw: (calls.append(args), subprocess.CompletedProcess(args, 0))[1],
    )
    src = Path("fixtures/db.db")
    with pytest.raises(ValueError):
        adb.push_app_file(src, "files/evil'; rm -rf /data; echo '.db")
    assert not calls, "_run() НЕ должен вызываться при отклонённом rel_path (ни push, ни shell)"


@pytest.mark.p1
@allure.id("AT-BUG-079-push-app-file-tmp-single-quote-rejected")
@allure.title("adb.push_app_file — tmp (из src.name) с одинарной кавычкой отклоняется ValueError fail-closed (AT-BUG-079)")
def test_push_app_file_tmp_with_single_quote_rejected(monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(
        adb, "_run",
        lambda args, timeout=None, **kw: (calls.append(args), subprocess.CompletedProcess(args, 0))[1],
    )
    src = Path("fixtures/evil'db.db")
    with pytest.raises(ValueError):
        adb.push_app_file(src, "files/dst.db")
    assert not calls, "_run() НЕ должен вызываться при отклонённом tmp (src.name с кавычкой)"
