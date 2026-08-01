"""Юнит-тесты gitlab_sync (scripts/gitlab_sync.py).

Device-free и network-free: сетевой транспорт GitLabClient подменяется
FakeTransport (см. ниже) — ни один тест не обращается к реальной сети/
gitlab.com. Артефакты — во временном bugs_dir (tmp_path), реальные bugs/*.md
репозитория НЕ читаются и НЕ пишутся.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import gitlab_sync as gs


# --- Фикстуры -----------------------------------------------------------

def _write_bug(dir_: Path, bug_id: str, *, title="Заголовок бага",
               severity="major", status="Open", extra: str = "",
               body: str = "\n# Заголовок\n\nТело описания бага.\n") -> Path:
    text = (
        f"---\n"
        f"id: {bug_id}\n"
        f'title: "{title}"\n'
        f"severity: {severity}\n"
        f"status: {status}\n"
        f"{extra}"
        f'updated: "2026-08-01T00:00:00Z"\n'
        f"---\n"
        f"{body}"
    )
    p = dir_ / f"{bug_id}.md"
    p.write_text(text, encoding="utf-8")
    return p


@pytest.fixture()
def bugs_dir(tmp_path, monkeypatch):
    d = tmp_path / "bugs"
    d.mkdir()
    monkeypatch.setattr(gs, "BUGS_DIR", d, raising=True)
    aut = tmp_path / "state" / "app-under-test.yaml"
    aut.parent.mkdir(parents=True, exist_ok=True)
    aut.write_text(
        "app: ao3-wrapper\nrepo: https://gitlab.com/Xartaxana1/ao3-wrapper\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(gs, "AUT_PATH", aut, raising=True)
    return d


class FakeTransport:
    """Заменяет сетевой вызов GitLabClient. responses — список
    (status, body) в порядке ожидаемых вызовов; body — dict/list (сериализуется
    в JSON) либо bytes/str."""

    def __init__(self, responses):
        self.calls: list[dict] = []
        self._responses = list(responses)

    def __call__(self, method, url, headers, data):
        self.calls.append({
            "method": method, "url": url, "headers": dict(headers),
            "json": json.loads(data) if data else None,
        })
        if not self._responses:
            raise AssertionError(f"FakeTransport: неожиданный вызов {method} {url}")
        status, body = self._responses.pop(0)
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        return status, body


def _client(responses) -> tuple[gs.GitLabClient, FakeTransport]:
    transport = FakeTransport(responses)
    client = gs.GitLabClient(
        "https://gitlab.com/api/v4/projects/Xartaxana1%2Fao3-wrapper",
        "tok-123", transport=transport)
    return client, transport


# --- Фильтрация: AT-BUG-* / test_debt не попадают в план -------------------

def test_at_bug_and_test_debt_excluded_from_plan(bugs_dir, capsys):
    _write_bug(bugs_dir, "BUG-001", status="Open")
    (bugs_dir / "AT-BUG-002.md").write_text(
        '---\nid: AT-BUG-002\ntitle: "долг фабрики"\nseverity: minor\n'
        'status: Open\ntype: test_debt\nupdated: "2026-08-01T00:00:00Z"\n---\n\nтело\n',
        encoding="utf-8",
    )
    _write_bug(bugs_dir, "BUG-003", status="Open", extra="type: test_debt\n")

    code = gs.main(["--dry-run"])
    out = capsys.readouterr().out

    assert code == 0
    assert "BUG-001" in out
    assert "AT-BUG-002" not in out
    assert "BUG-003" not in out


# --- Маппинг status -> GitLab state: весь enum + неизвестный -------------

@pytest.mark.parametrize("status,expected", [
    ("Open", "opened"), ("Reopened", "opened"), ("Fixed", "opened"),
    ("Blocked", "opened"), ("Verified", "closed"), ("Rejected", "closed"),
    ("Intended", "closed"),
])
def test_desired_gitlab_state_covers_full_enum(status, expected):
    assert gs.desired_gitlab_state(status) == expected


def test_desired_gitlab_state_unknown_raises():
    with pytest.raises(gs.BugSyncError, match="неизвестный status"):
        gs.desired_gitlab_state("NotAStatus")


# --- create-payload: title-префикс, labels, description ------------------

def test_create_payload_title_labels_description(bugs_dir):
    p = _write_bug(bugs_dir, "BUG-011", title="Что-то сломалось",
                   severity="major", status="Open",
                   extra='found_in: "1.10"\ntest_cases: [TC-020]\nruns: []\n',
                   body="\n# BUG-011\n\nШаги репро.\n")
    meta, body = gs.load_bug(p)

    client, transport = _client([
        (200, []),                                  # GET /issues (adopt search)
        (201, {"iid": 42, "title": "x"}),            # POST /issues
    ])

    result = gs.sync_bug(client, p, meta, body)

    assert result == "created"
    post_call = transport.calls[1]
    assert post_call["method"] == "POST"
    payload = post_call["json"]
    assert payload["title"] == "BUG-011: Что-то сломалось"
    assert "qa-factory" in payload["labels"]
    assert "severity::major" in payload["labels"]
    assert "qa-status::Open" in payload["labels"]
    assert "Шаги репро." in payload["description"]
    assert "Экспортировано из тест-фабрики" in payload["description"]
    assert "bugs/BUG-011.md" in payload["description"]
    assert "TC-020" in payload["description"]


# --- закрытый баг: create + немедленный close -----------------------------

def test_closed_status_creates_then_closes(bugs_dir):
    p = _write_bug(bugs_dir, "BUG-050", status="Verified")
    meta, body = gs.load_bug(p)

    client, transport = _client([
        (200, []),
        (201, {"iid": 7}),
        (200, {"iid": 7, "state": "closed"}),        # PUT state_event=close
    ])

    result = gs.sync_bug(client, p, meta, body)

    assert result == "created"
    assert len(transport.calls) == 3
    put_call = transport.calls[2]
    assert put_call["method"] == "PUT"
    assert put_call["json"] == {"state_event": "close"}


# --- writeback: БАЙТОВАЯ вставка, EOL файла не тронут (блокер 1 критик-ревью) --
#
# read_text/write_text (newline=None) переписывают ОКОНЧАНИЯ СТРОК ВСЕГО файла
# на запись (universal-newlines перевод) — воспроизведено критиком на
# BUG-013 (вставка 18 байт -> рост файла на 161: 8 из 11 целевых bugs/*.md LF,
# 3 CRLF). Фикстуры ниже пишутся через write_bytes НАПРЯМУЮ (в обход
# text-режима, который сам по себе на Windows транслирует '\n' -> os.linesep
# при записи и замаскировал бы баг) — только так тест реально ловит класс.

@pytest.mark.parametrize("eol", ["\n", "\r\n"], ids=["LF", "CRLF"])
def test_writeback_is_byte_exact_insert_lf_and_crlf(bugs_dir, eol):
    lines = [
        "---",
        "id: BUG-160",
        'title: "Заголовок"',
        "severity: major",
        "status: Open",
        'updated: "2026-08-01T00:00:00Z"',
        "---",
        "",
        "# Тело",
        "",
        "Текст перед горизонтальной линией.",
        "",
        "---",
        "",
        "Текст после горизонтальной линии в теле.",
        "",
    ]
    raw_text = eol.join(lines)
    p = bugs_dir / "BUG-160.md"
    p.write_bytes(raw_text.encode("utf-8"))
    before = p.read_bytes()

    gs.writeback_gitlab_issue(p, 777)
    after = p.read_bytes()

    text = before.decode("utf-8")
    m = gs.FRONTMATTER_RE.match(text)
    assert m is not None
    insert_at_bytes = len(text[:m.end(1)].encode("utf-8"))
    inserted = f"{eol}gitlab_issue: 777".encode("utf-8")

    assert after == before[:insert_at_bytes] + inserted + before[insert_at_bytes:]
    # никакого "перегона" EOL по всему файлу: LF-фикстура остаётся чисто LF
    # (кроме собственно вставленного eol), CRLF-фикстура — чисто CRLF.
    if eol == "\n":
        assert b"\r" not in after
    else:
        assert after.replace(b"\r\n", b"").count(b"\n") == 0


# --- writeback: поле УЖЕ есть в frontmatter (шаблонный плейсхолдер
# 'gitlab_issue: ""' с 2026-08-01, docs/templates/bug-report.md) -> REPLACE,
# не INSERT второй строки (BUG-021 живьём: до фикса получалось 2 ключа
# 'gitlab_issue:' -> невалидный YAML, PyYAML.safe_load молча брал последнее
# значение без ошибки -- баг маскировался, но порча данных росла с каждым
# новым багом).

@pytest.mark.parametrize("eol", ["\n", "\r\n"], ids=["LF", "CRLF"])
@pytest.mark.parametrize("existing_value", ['""', "5"],
                         ids=["placeholder-empty", "old-iid"])
def test_writeback_replaces_existing_field_no_duplicate(bugs_dir, eol, existing_value):
    lines = [
        "---",
        "id: BUG-160",
        'title: "Заголовок"',
        "severity: major",
        "status: Open",
        f"gitlab_issue: {existing_value}",
        'updated: "2026-08-01T00:00:00Z"',
        "---",
        "",
        "# Тело",
        "",
        "Текст перед горизонтальной линией.",
        "",
        "---",
        "",
        "Текст после горизонтальной линии в теле.",
        "",
    ]
    raw_text = eol.join(lines)
    p = bugs_dir / "BUG-160.md"
    p.write_bytes(raw_text.encode("utf-8"))
    before = p.read_bytes()

    gs.writeback_gitlab_issue(p, 12)
    after = p.read_bytes()

    text = before.decode("utf-8")
    m = gs.FRONTMATTER_RE.match(text)
    assert m is not None
    field_match = gs.GITLAB_ISSUE_LINE_RE.search(text[m.start(1):m.end(1)])
    assert field_match is not None
    abs_start_bytes = len(text[:m.start(1) + field_match.start()].encode("utf-8"))
    abs_end_bytes = len(text[:m.start(1) + field_match.end()].encode("utf-8"))

    assert after == before[:abs_start_bytes] + b"gitlab_issue: 12" + before[abs_end_bytes:]

    after_text = after.decode("utf-8")
    m2 = gs.FRONTMATTER_RE.match(after_text)
    assert m2.group(1).count("gitlab_issue:") == 1   # ровно одно поле -- нет дубля

    meta, _body = gs.load_bug(p)
    assert meta.get("gitlab_issue") == 12


def test_writeback_repro_bug021_double_field_before_fix(bugs_dir):
    """Живой репро BUG-021.md (заведён bug-reporter'ом ПОСЛЕ правки шаблона
    2026-08-01): frontmatter уже несёт пустой плейсхолдер 'gitlab_issue: ""'.
    До фикса writeback слепо вставляла ВТОРУЮ строку 'gitlab_issue: <iid>'
    перед закрывающим '---' -> 2 ключа в frontmatter. После фикса -- ровно
    один, со значением iid."""
    text = (
        "---\n"
        "id: BUG-021\n"
        'title: "Правка заметки скачанной работы через overlay листинга '
        'обнуляет downloadPath в Room"\n'
        "type: app_bug\n"
        "severity: major\n"
        "status: Open\n"
        'gitlab_issue: ""\n'
        'updated: "2026-08-02T00:00:00Z"\n'
        "---\n"
        "\n# BUG-021 — Правка заметки скачанной работы\n"
    )
    p = bugs_dir / "BUG-021.md"
    p.write_bytes(text.encode("utf-8"))

    gs.writeback_gitlab_issue(p, 12)

    after_text = p.read_bytes().decode("utf-8")
    m = gs.FRONTMATTER_RE.match(after_text)
    assert m is not None
    assert m.group(1).count("gitlab_issue:") == 1
    assert "gitlab_issue: 12" in m.group(1)

    meta, _body = gs.load_bug(p)
    assert meta.get("gitlab_issue") == 12


def test_second_run_is_idempotent_zero_create(bugs_dir):
    p = _write_bug(bugs_dir, "BUG-061", status="Open")
    meta, body = gs.load_bug(p)
    client, _t = _client([(200, []), (201, {"iid": 5})])
    gs.sync_bug(client, p, meta, body)   # первый прогон -> created, writeback

    meta2, body2 = gs.load_bug(p)
    assert meta2.get("gitlab_issue") == 5

    issue_snapshot = {
        "iid": 5, "title": gs.build_title("BUG-061", meta2.get("title", "")),
        "description": gs.build_description(meta2, body2),
        "labels": gs.desired_labels(meta2), "state": "opened",
    }
    client2, transport2 = _client([(200, issue_snapshot)])
    result = gs.sync_bug(client2, p, meta2, body2)

    assert result == "unchanged"
    assert not any(c["method"] == "POST" for c in transport2.calls)


# --- adopt-путь: search находит issue -> create НЕ вызывается ------------

def test_adopt_prefix_rejects_longer_bug_id_number(bugs_dir):
    """BUG-100 не обязан 'усыновлять' issue заголовка 'BUG-1000: ...' —
    startswith(bug_id) один даёт ложное совпадение по числовому префиксу
    (рекомендация 2 критик-ревью). Decoy отвергается -> create, не adopt."""
    p = _write_bug(bugs_dir, "BUG-100", title="Заголовок", status="Open")
    meta, body = gs.load_bug(p)

    decoy_issue = {"iid": 999, "title": "BUG-1000: другой, непричастный баг"}
    client, transport = _client([
        (200, [decoy_issue]),        # GET search — decoy НЕ должен матчиться
        (201, {"iid": 55}),          # POST create — раз adopt не сработал
    ])

    result = gs.sync_bug(client, p, meta, body)

    assert result == "created"
    post_calls = [c for c in transport.calls if c["method"] == "POST"]
    assert len(post_calls) == 1
    assert post_calls[0]["json"]["title"] == "BUG-100: Заголовок"


def test_adopt_path_skips_create_and_writes_back_iid(bugs_dir):
    p = _write_bug(bugs_dir, "BUG-070", title="Заголовок", status="Open")
    meta, body = gs.load_bug(p)

    existing_issue = {
        "iid": 321, "title": "BUG-070: Заголовок",
        "description": gs.build_description(meta, body),
        "labels": gs.desired_labels(meta), "state": "opened",
    }
    client, transport = _client([(200, [existing_issue])])   # GET search only

    result = gs.sync_bug(client, p, meta, body)

    assert result == "adopted:unchanged"
    assert not any(c["method"] == "POST" for c in transport.calls)
    meta_after, _ = gs.load_bug(p)
    assert meta_after.get("gitlab_issue") == 321


# --- update-путь: аддитивные labels (add_labels/remove_labels), не PUT labels
# (изменение спеки Lead 2026-08-01: полный PUT labels стирал бы ручные метки
# разработчика — GitLab issue считается label-синхронным, когда желаемые
# метки ⊆ текущих И нет СВОИХ устаревших severity::*/qa-status::*).

def test_update_path_foreign_label_survives(bugs_dir):
    """Чужая метка ('workflow::doing', поставленная разработчиком вручную)
    переживает sync нетронутой — sync владеет только qa-factory/severity::*/
    qa-status::*."""
    p = _write_bug(bugs_dir, "BUG-080", status="Open", severity="major",
                   title="Новый заголовок", extra="gitlab_issue: 900\n")
    meta, body = gs.load_bug(p)
    desired_title = gs.build_title("BUG-080", meta.get("title", ""))
    description = gs.build_description(meta, body)

    remote_issue = {
        "iid": 900,
        "title": "старый заголовок issue (расходится -> форсирует PUT)",
        "description": description,
        "labels": ["qa-factory", "severity::major", "qa-status::Open", "workflow::doing"],
        "state": "opened",
    }
    client, transport = _client([
        (200, remote_issue),   # GET /issues/900
        (200, {}),             # PUT (title only — labels уже синхронны)
    ])

    result = gs.sync_bug(client, p, meta, body)

    assert result == "updated"
    put_calls = [c for c in transport.calls if c["method"] == "PUT"]
    assert len(put_calls) == 1
    put_json = put_calls[0]["json"]
    assert put_json.get("title") == desired_title
    assert "add_labels" not in put_json
    assert "remove_labels" not in put_json
    # чужая метка нигде не упомянута в исходящем запросе
    assert "workflow::doing" not in json.dumps(put_json)


def test_update_path_severity_change_adds_and_removes_own_label(bugs_dir):
    """severity minor -> major в артефакте: add_labels=[severity::major],
    remove_labels=[severity::minor] (свой устаревший label снимается,
    новый — добавляется; title/description не трогаются)."""
    p = _write_bug(bugs_dir, "BUG-081", status="Open", severity="major",
                   extra="gitlab_issue: 901\n")
    meta, body = gs.load_bug(p)
    title = gs.build_title("BUG-081", meta.get("title", ""))
    description = gs.build_description(meta, body)

    remote_issue = {
        "iid": 901, "title": title, "description": description,
        "labels": ["qa-factory", "severity::minor", "qa-status::Open"],
        "state": "opened",
    }
    client, transport = _client([
        (200, remote_issue),   # GET /issues/901
        (200, {}),             # PUT add_labels/remove_labels
    ])

    result = gs.sync_bug(client, p, meta, body)

    assert result == "updated"
    put_calls = [c for c in transport.calls if c["method"] == "PUT"]
    assert len(put_calls) == 1
    put_json = put_calls[0]["json"]
    assert "title" not in put_json
    assert "description" not in put_json
    assert put_json["add_labels"] == "severity::major"
    assert put_json["remove_labels"] == "severity::minor"


def test_label_changes_helper_add_and_remove_multiple():
    current = {"qa-factory", "severity::minor", "qa-status::Fixed", "workflow::doing"}
    desired = ["qa-factory", "severity::major", "qa-status::Open"]
    add, remove = gs._label_changes(current, desired)
    assert add == ["severity::major", "qa-status::Open"]
    assert remove == ["qa-status::Fixed", "severity::minor"]  # sorted, foreign untouched


def test_label_changes_helper_in_sync_returns_empty():
    current = {"qa-factory", "severity::major", "qa-status::Open", "workflow::doing"}
    desired = ["qa-factory", "severity::major", "qa-status::Open"]
    add, remove = gs._label_changes(current, desired)
    assert add == []
    assert remove == []


# --- Адверсариальная батарея -----------------------------------------------

def test_title_with_cyrillic_quotes_markdown(bugs_dir):
    p = _write_bug(bugs_dir, "BUG-090",
                   title='Кавычки «ёлки», markdown **bold** и `code`')
    meta, _body = gs.load_bug(p)
    title = gs.build_title("BUG-090", meta["title"])
    assert title == 'BUG-090: Кавычки «ёлки», markdown **bold** и `code`'


def test_title_exactly_255_chars_not_truncated():
    long_title = "x" * (255 - len("BUG-100: "))
    title = gs.build_title("BUG-100", long_title)
    assert len(title) == 255
    assert title == f"BUG-100: {long_title}"


def test_title_256_chars_truncated_to_255():
    long_title = "x" * (256 - len("BUG-100: "))
    title = gs.build_title("BUG-100", long_title)
    assert len(title) == 255


def test_empty_body_description_still_valid(bugs_dir):
    p = _write_bug(bugs_dir, "BUG-101", status="Open", body="")
    meta, body = gs.load_bug(p)
    assert body == ""
    description = gs.build_description(meta, body)
    assert "Экспортировано из тест-фабрики" in description
    assert "| Поле | Значение |" in description


def test_broken_frontmatter_one_file_others_processed(bugs_dir, capsys):
    good = _write_bug(bugs_dir, "BUG-110", status="Open")
    broken = bugs_dir / "BUG-111.md"
    broken.write_text("---\nid: BUG-111\ntitle: без закрывающего маркера\n",
                       encoding="utf-8")

    bugs = gs.discover_bugs()
    code = gs.run_dry_run(bugs)
    captured = capsys.readouterr()

    assert code == 1
    assert "create BUG-110" in captured.out
    # ошибки — унифицированно в stderr (рекомендация 4 критик-ревью: run_dry_run
    # и run_sync используют один и тот же поток ошибок, не stdout)
    assert "[ERROR]" in captured.err
    assert "BUG-111" in captured.err


def test_401_error_mentions_gitlab_token(bugs_dir):
    p = _write_bug(bugs_dir, "BUG-120", status="Open")
    meta, body = gs.load_bug(p)
    client, _t = _client([(401, {"message": "401 Unauthorized"})])

    with pytest.raises(gs.GitLabHTTPError) as exc_info:
        gs.sync_bug(client, p, meta, body)

    assert "GITLAB_TOKEN" in str(exc_info.value)


# --- Блокер 2 критик-ревью: один плохой артефакт/ответ не валит батч --------

def test_invalid_gitlab_issue_field_raises_bugsyncerror(bugs_dir):
    p = _write_bug(bugs_dir, "BUG-199", status="Open", extra="gitlab_issue: abc\n")
    meta, body = gs.load_bug(p)
    client, _t = _client([])   # ни один сетевой вызов не должен произойти

    with pytest.raises(gs.BugSyncError, match="gitlab_issue"):
        gs.sync_bug(client, p, meta, body)


def test_invalid_gitlab_issue_field_does_not_kill_batch(bugs_dir, capsys):
    """Батч из 3 файлов: первый с 'gitlab_issue: abc' -> остальные два
    обработаны нормально (create), exit 1 (первый упал)."""
    _write_bug(bugs_dir, "BUG-200", status="Open", extra="gitlab_issue: abc\n")
    _write_bug(bugs_dir, "BUG-201", status="Open")
    _write_bug(bugs_dir, "BUG-202", status="Open")

    client, transport = _client([
        (200, []), (201, {"iid": 77}),   # BUG-201: adopt search + create
        (200, []), (201, {"iid": 78}),   # BUG-202: adopt search + create
    ])

    bugs = gs.discover_bugs()
    code = gs.run_sync(client, bugs)
    err = capsys.readouterr().err

    assert code == 1
    assert "BUG-200" in err
    post_calls = [c for c in transport.calls if c["method"] == "POST"]
    assert len(post_calls) == 2


def test_post_response_without_iid_raises_bugsyncerror(bugs_dir):
    p = _write_bug(bugs_dir, "BUG-210", status="Open")
    meta, body = gs.load_bug(p)
    client, _t = _client([(200, []), (201, {"id": 55})])   # нет 'iid'

    with pytest.raises(gs.BugSyncError, match="iid"):
        gs.sync_bug(client, p, meta, body)


def test_post_without_iid_does_not_kill_batch(bugs_dir, capsys):
    """POST вернул {'id': 55} (без 'iid') для одного бага -> ошибка ПО
    ЭТОМУ багу, батч жив: следующий баг обрабатывается нормально."""
    _write_bug(bugs_dir, "BUG-211", status="Open")
    _write_bug(bugs_dir, "BUG-212", status="Open")

    client, transport = _client([
        (200, []), (201, {"id": 55}),     # BUG-211: POST без iid
        (200, []), (201, {"iid": 88}),    # BUG-212: нормальный
    ])

    bugs = gs.discover_bugs()
    code = gs.run_sync(client, bugs)
    err = capsys.readouterr().err

    assert code == 1
    assert "BUG-211" in err
    post_calls = [c for c in transport.calls if c["method"] == "POST"]
    assert len(post_calls) == 2


def test_run_sync_batch_broken_frontmatter_and_401_and_good(bugs_dir):
    """Батч: битый frontmatter + 401 + нормальный баг -> exit 1, нормальный
    баг создан и writeback выполнен (критик проверял это только вручную —
    закреплено тестом)."""
    broken = bugs_dir / "BUG-220.md"
    broken.write_text("---\nid: BUG-220\ntitle: без закрывающего маркера\n",
                       encoding="utf-8")
    _write_bug(bugs_dir, "BUG-221", status="Open")   # получит 401 на adopt-поиске
    good = _write_bug(bugs_dir, "BUG-222", status="Open")

    client, transport = _client([
        (401, {"message": "401 Unauthorized"}),   # BUG-221: adopt search -> 401
        (200, []),                                 # BUG-222: adopt search
        (201, {"iid": 900}),                       # BUG-222: create
    ])

    bugs = gs.discover_bugs()
    code = gs.run_sync(client, bugs)

    assert code == 1
    meta_good, _ = gs.load_bug(good)
    assert meta_good.get("gitlab_issue") == 900
    post_calls = [c for c in transport.calls if c["method"] == "POST"]
    assert len(post_calls) == 1


def test_dry_run_without_token_works_offline(bugs_dir, monkeypatch, capsys):
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)

    def _boom(*_a, **_kw):
        raise AssertionError("транспорт не должен вызываться в --dry-run")
    monkeypatch.setattr(gs, "_default_transport", _boom, raising=True)

    _write_bug(bugs_dir, "BUG-130", status="Open")
    code = gs.main(["--dry-run"])
    out = capsys.readouterr().out

    assert code == 0
    assert "create BUG-130" in out


def test_missing_token_on_real_sync_exits_2(bugs_dir, monkeypatch):
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)
    _write_bug(bugs_dir, "BUG-131", status="Open")

    code = gs.main([])

    assert code == 2


# --- --check: оба исхода ----------------------------------------------------

def test_check_all_synced_exit_0(bugs_dir, capsys):
    _write_bug(bugs_dir, "BUG-140", status="Open", extra="gitlab_issue: 1\n")
    _write_bug(bugs_dir, "BUG-141", status="Open", extra="gitlab_issue: 2\n")

    code = gs.main(["--check"])
    out = capsys.readouterr().out

    assert code == 0
    assert "все BUG-* синхронизированы" in out


def test_check_missing_ones_exit_1(bugs_dir, capsys):
    _write_bug(bugs_dir, "BUG-150", status="Open", extra="gitlab_issue: 3\n")
    _write_bug(bugs_dir, "BUG-151", status="Open")

    code = gs.main(["--check"])
    out = capsys.readouterr().out

    assert code == 1
    assert "BUG-151" in out
    assert "BUG-150" not in out.split("не синхронизированы:")[-1]


# --- Разбор repo URL ---------------------------------------------------------

def test_parse_project_and_api_base():
    host, path = gs.parse_project("https://gitlab.com/Xartaxana1/ao3-wrapper")
    assert host == "gitlab.com"
    assert path == "Xartaxana1/ao3-wrapper"
    base = gs.api_base("https://gitlab.com/Xartaxana1/ao3-wrapper")
    assert base == "https://gitlab.com/api/v4/projects/Xartaxana1%2Fao3-wrapper"


def test_parse_project_strips_userinfo_from_host(bugs_dir):
    """Рекомендация 3 критик-ревью: parsed.hostname (+ порт), не netloc —
    userinfo из repo URL не должен утекать в host/api_base/тексты ошибок."""
    host, path = gs.parse_project("https://user:s3cr3t@gitlab.example.com:8443/Org/Repo")
    assert host == "gitlab.example.com:8443"
    assert "s3cr3t" not in host
    assert path == "Org/Repo"
    base = gs.api_base("https://user:s3cr3t@gitlab.example.com:8443/Org/Repo")
    assert "s3cr3t" not in base
    assert base == "https://gitlab.example.com:8443/api/v4/projects/Org%2FRepo"


# --- --bug: валидация формата (рекомендация 1 критик-ревью) -----------------

def test_validate_bug_arg_accepts_valid_bug_id():
    gs.validate_bug_arg("BUG-011")   # не должно кидать


def test_validate_bug_arg_rejects_at_bug_prefix_explicitly():
    with pytest.raises(SystemExit, match="AT-BUG"):
        gs.validate_bug_arg("AT-BUG-005")


def test_validate_bug_arg_rejects_garbage_format():
    with pytest.raises(SystemExit, match="не похож"):
        gs.validate_bug_arg("foobar")


def test_main_bug_at_bug_gives_explicit_error_not_empty_output(bugs_dir, capsys):
    """До фикса: --bug AT-BUG-NNN на существующий файл тихо не находил
    app-багов (пустой вывод, exit 0) — is_app_bug фильтровал молча."""
    (bugs_dir / "AT-BUG-005.md").write_text(
        '---\nid: AT-BUG-005\ntitle: "долг фабрики"\nseverity: minor\n'
        'status: Open\ntype: test_debt\nupdated: "2026-08-01T00:00:00Z"\n---\n\nтело\n',
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="AT-BUG"):
        gs.main(["--dry-run", "--bug", "AT-BUG-005"])
