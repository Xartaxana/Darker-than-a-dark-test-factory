"""Device-free юнит-проба `mitm.read_captured_requests()` (AT-BUG-073,
критерий готовности п.4 — критик-вход attempt 4, класс-пробел «новый
примитив без device-free юнит-пробы», собратья: `test_mitm_port_race_unit.py`/
`test_mitm_proxy_reachable_unit.py`/`test_mitm_upstream_guard_unit.py`).

Три границы (замечания 4/5 критик-входа):
  - файла нет -> `[]` (после опроса до `timeout`, не мгновенный голый провал);
  - файл пуст -> `[]` (та же ветка опроса, не различимо для вызывающего кода
    от «файла нет» — оба «пока нечего вернуть»);
  - валидные строки парсятся; ПОСЛЕДНЯЯ строка битая/оборванная (гонка чтения
    ровно в момент, когда addon ещё не завершил запись) — ПРОПУСКАЕТСЯ с
    предупреждением в stderr, не роняет всю функцию голым `JSONDecodeError`
    (см. докстринг функции, замечание 5 критик-входа).

Устройство/mitmdump/порт 8080 НЕ трогаются — `read_captured_requests()` читает
обычный локальный файл, addon и процесс mitmdump в этой пробе не участвуют.
"""
from __future__ import annotations

import allure
import pytest

from framework.core import mitm


@pytest.fixture(scope="session", autouse=True)
def _ensure_app_installed():
    """Переопределяет device-фикстуру conftest.py — эта проба чисто
    локальная, устройство не трогаем (тот же приём, что соседние
    `test_mitm_*_unit.py`)."""
    yield


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    """Опрос внутри `read_captured_requests` не должен ждать реальные секунды
    в юнит-пробе (тот же приём, что `test_mitm_port_race_unit.py`)."""
    calls = {"n": 0}
    monkeypatch.setattr(mitm.time, "sleep", lambda s: calls.__setitem__("n", calls["n"] + 1))
    return calls


@pytest.mark.p1
@allure.id("AT-BUG-073-read-captured-requests-no-file")
@allure.title("Проба: read_captured_requests() возвращает [] когда файла нет, после опроса до timeout, без исключения (device-free)")
def test_read_captured_requests_no_file_returns_empty_list(tmp_path, _no_real_sleep):
    missing = tmp_path / "does_not_exist.jsonl"

    result = mitm.read_captured_requests(missing, timeout=0.05)

    assert result == []
    assert _no_real_sleep["n"] >= 1  # реально опрашивал, не мгновенный голый возврат


@pytest.mark.p1
@allure.id("AT-BUG-073-read-captured-requests-empty-file")
@allure.title("Проба: read_captured_requests() возвращает [] для СУЩЕСТВУЮЩЕГО, но пустого файла (device-free)")
def test_read_captured_requests_empty_file_returns_empty_list(tmp_path, _no_real_sleep):
    empty = tmp_path / "capture.jsonl"
    empty.write_text("", encoding="utf-8")

    result = mitm.read_captured_requests(empty, timeout=0.05)

    assert result == []


@pytest.mark.p1
@allure.id("AT-BUG-073-read-captured-requests-valid-lines")
@allure.title("Проба: read_captured_requests() парсит все валидные JSONL-строки в списке словарей, в порядке файла (device-free)")
def test_read_captured_requests_parses_valid_lines(tmp_path, _no_real_sleep):
    path = tmp_path / "capture.jsonl"
    path.write_text(
        '{"method": "PUT", "url": "https://gitlab.com/api/v4/snippets/1", "body": "{}"}\n'
        '{"method": "POST", "url": "https://gitlab.com/api/v4/snippets", "body": "{}"}\n',
        encoding="utf-8",
    )

    result = mitm.read_captured_requests(path, timeout=1.0)

    assert result == [
        {"method": "PUT", "url": "https://gitlab.com/api/v4/snippets/1", "body": "{}"},
        {"method": "POST", "url": "https://gitlab.com/api/v4/snippets", "body": "{}"},
    ]
    assert _no_real_sleep["n"] == 0  # файл сразу непуст -- ни одного опроса не понадобилось


@pytest.mark.p1
@allure.id("AT-BUG-073-read-captured-requests-skips-broken-last-line")
@allure.title("Проба: битая/оборванная ПОСЛЕДНЯЯ строка ПРОПУСКАЕТСЯ (предупреждение в stderr), валидные строки перед ней всё равно возвращены — НЕ голый JSONDecodeError (критик-вход attempt 4, замечание 5) (device-free)")
def test_read_captured_requests_skips_broken_trailing_line(tmp_path, _no_real_sleep, capsys):
    path = tmp_path / "capture.jsonl"
    path.write_text(
        '{"method": "PUT", "url": "https://gitlab.com/api/v4/snippets/1", "body": "{}"}\n'
        '{"method": "POST", "url": "https://gitlab.com/api/v4/sn',  # оборвана на середине записи
        encoding="utf-8",
    )

    result = mitm.read_captured_requests(path, timeout=1.0)

    assert result == [
        {"method": "PUT", "url": "https://gitlab.com/api/v4/snippets/1", "body": "{}"},
    ]
    captured = capsys.readouterr()
    assert "AT-BUG-073" in captured.err
    assert "WARNING" in captured.err
