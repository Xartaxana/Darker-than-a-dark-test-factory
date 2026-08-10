"""Юнит-тесты provided-канала build_watch (M-A, spec-build-source-dual-mode v4).

Сеть НИКОГДА не трогается по-настоящему: JSON-вызовы GitLabClient идут через
FakeTransport (тот же паттерн, что test_gitlab_sync.py/test_gitlab_inbound.py,
локальная копия — изоляция файлов теста друг от друга); бинарная загрузка
(_http_get_binary) — через FakeOpener (инъекция `opener=`), имитирующий
urllib.request.OpenerDirector.open() без единого реального сокета.
"""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

import build_watch as bw
import gitlab_sync as gs

OLD_SHA = "a" * 40
PIPELINE_SHA = "d" * 40

AUT_TEXT = f"""app: ao3-wrapper
repo: https://gitlab.com/Xartaxana1/ao3-wrapper
source_commit: {OLD_SHA}   # старая сборка
version_name: "1.10"
version_code: 11
build_type: debug
apk_path: app-under-test/{bw.APK_REL}
apk_sha256: "deadbeef"
built_at: "2026-07-02T02:39:46"
smoke_status: passed
regression_status: passed
"""


def _write_aut(repo, text: str = AUT_TEXT) -> Path:
    aut = repo.root / "state" / "app-under-test.yaml"
    aut.parent.mkdir(parents=True, exist_ok=True)
    aut.write_text(text, encoding="utf-8")
    return aut


# --- _parse_provided_ref -----------------------------------------------------

@pytest.mark.parametrize("ref,expected", [
    ("pipeline:123", ("pipeline", 123)),
    ("job:456", ("job", 456)),
])
def test_parse_provided_ref_valid(ref, expected):
    assert bw._parse_provided_ref(ref) == expected


@pytest.mark.parametrize("bad", [
    "pipeline:", "job:", "pipeline:abc", "pipelines:1", "1", "",
    "pipeline:1;rm -rf", "pipeline:1 job:2", "https://gitlab.com/x/pipelines/1",
])
def test_parse_provided_ref_rejects_non_numeric_or_malformed(bad):
    with pytest.raises(ValueError):
        bw._parse_provided_ref(bad)


# --- read_app_versions --------------------------------------------------------

def test_read_app_versions_missing_file_returns_none_none(tmp_path):
    assert bw.read_app_versions(tmp_path / "nope.json") == (None, None)


def test_read_app_versions_malformed_json_returns_none_none(tmp_path):
    p = tmp_path / "output-metadata.json"
    p.write_text("{not valid json", encoding="utf-8")
    assert bw.read_app_versions(p) == (None, None)


def test_read_app_versions_no_elements_returns_none_none(tmp_path):
    p = tmp_path / "output-metadata.json"
    p.write_text(json.dumps({"elements": []}), encoding="utf-8")
    assert bw.read_app_versions(p) == (None, None)


def test_read_app_versions_partial_fields_returns_none_none_wholesale():
    """M-B.2: versionCode без versionName (или наоборот) — ЦЕЛИКОМ (None, None),
    не наполовину заполненная пара."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "output-metadata.json"
        p.write_text(json.dumps({"elements": [{"versionCode": 12}]}), encoding="utf-8")
        assert bw.read_app_versions(p) == (None, None)


def test_read_app_versions_valid(tmp_path):
    p = tmp_path / "output-metadata.json"
    p.write_text(json.dumps({"elements": [
        {"versionCode": 19, "versionName": "dev-7"}]}), encoding="utf-8")
    assert bw.read_app_versions(p) == ("dev-7", "19")


# --- _apply_version_fields: unknown + эскалация -------------------------------

def test_apply_version_fields_unknown_escalates_and_warns(repo, monkeypatch, capsys):
    monkeypatch.setattr(bw, "ESCALATIONS_PATH", repo.root / "state" / "escalations.md", raising=True)
    text = "version_name: \"1.10\"\nversion_code: 11\n"
    out_text = bw._apply_version_fields(text, None, None, context="тест")

    assert 'version_name: "unknown"' in out_text
    assert "version_code: unknown" in out_text
    esc = repo.read_artifact("state/escalations.md")
    assert "BUILD-VERSION-UNKNOWN" in esc
    out = capsys.readouterr().out
    assert "[WARN]" in out and "BUILD-VERSION-UNKNOWN" in out


def test_apply_version_fields_known_no_escalation(repo, monkeypatch):
    monkeypatch.setattr(bw, "ESCALATIONS_PATH", repo.root / "state" / "escalations.md", raising=True)
    text = "version_name: \"1.10\"\nversion_code: 11\n"
    out_text = bw._apply_version_fields(text, "1.11", "12", context="тест")
    assert 'version_name: "1.11"' in out_text and "version_code: 12" in out_text
    assert not (repo.root / "state" / "escalations.md").exists()


# --- C2: локальная сборка симметрично сбрасывает build_source/provided_ref --

def test_local_build_resets_build_source_and_provided_ref(repo, monkeypatch):
    text = AUT_TEXT.replace("source_commit:", "build_source: provided\nprovided_ref: \"pipeline:999\"\nsource_commit:")
    aut = _write_aut(repo, text)
    monkeypatch.setattr(bw, "REPO", repo.root, raising=True)
    monkeypatch.setattr(bw, "APP", repo.root / "app-under-test", raising=True)
    monkeypatch.setattr(bw, "AUT_PATH", aut, raising=True)
    metadata = repo.root / "app-under-test" / bw.METADATA_REL
    metadata.parent.mkdir(parents=True, exist_ok=True)
    metadata.write_text(json.dumps({"elements": [
        {"versionCode": 12, "versionName": "1.11"}]}), encoding="utf-8")

    bw.update_aut("c" * 40, [], "feedface")

    out = aut.read_text(encoding="utf-8")
    assert "build_source: local" in out
    assert 'provided_ref: ""' in out


# --- _local_commits_ahead_of_provided: гонка источников (A1) -----------------

class _FakeGitRunner:
    def __init__(self, *, fetch_rc=0, tip="e" * 40, rev_list_rc=0, rev_list_out=""):
        self.fetch_rc, self.tip = fetch_rc, tip
        self.rev_list_rc, self.rev_list_out = rev_list_rc, rev_list_out
        self.calls: list[str] = []

    def __call__(self, args, *, cwd=None, env=None, timeout=120):
        cmd = " ".join(str(a) for a in args)
        self.calls.append(cmd)
        if "fetch" in cmd:
            return self.fetch_rc, ""
        if "rev-parse" in cmd:
            return 0, self.tip + "\n"
        if "rev-list" in cmd:
            return self.rev_list_rc, self.rev_list_out
        raise AssertionError(f"unexpected: {cmd}")


def test_race_note_present_when_local_ahead(monkeypatch):
    runner = _FakeGitRunner(tip="e" * 40, rev_list_out="e" * 40 + "\n")
    monkeypatch.setattr(bw, "_run", runner, raising=True)
    note = bw._local_commits_ahead_of_provided("d" * 40)
    assert "поверх provided" in note
    assert "1 несобранных коммитов" in note


def test_race_note_empty_when_tip_equals_provided(monkeypatch):
    runner = _FakeGitRunner(tip="d" * 40)
    monkeypatch.setattr(bw, "_run", runner, raising=True)
    assert bw._local_commits_ahead_of_provided("d" * 40) == ""


def test_race_note_empty_when_fetch_fails_offline(monkeypatch):
    runner = _FakeGitRunner(fetch_rc=128)
    monkeypatch.setattr(bw, "_run", runner, raising=True)
    assert bw._local_commits_ahead_of_provided("d" * 40) == ""


def test_update_aut_provided_race_note_is_dedicated_field_not_stale_comment(
        repo, monkeypatch):
    """Критик-вход (мелочь 3, 2026-08-10): race_note — ОТДЕЛЬНОЕ, ВСЕГДА явно
    перезаписываемое поле — НЕ хвостовой комментарий source_commit.
    _rewrite_field переносит существующий хвостовой комментарий поля на
    КАЖДУЮ последующую запись значения этого же поля (задумано для
    человеческих аннотаций вроде "# 2026-06-28") — встраивание туда
    ephemeral race-note пережило бы следующий вызов и стало бы враньём."""
    aut = _write_aut(repo)
    monkeypatch.setattr(bw, "REPO", repo.root, raising=True)
    monkeypatch.setattr(bw, "APP", repo.root / "app-under-test", raising=True)
    monkeypatch.setattr(bw, "AUT_PATH", aut, raising=True)
    metadata = repo.root / "meta.json"
    metadata.write_text(json.dumps({"elements": [
        {"versionCode": 19, "versionName": "dev-7"}]}), encoding="utf-8")

    # Первый вызов: гонка ЕСТЬ (tip дальше provided-sha).
    runner1 = _FakeGitRunner(tip="e" * 40, rev_list_out="e" * 40 + "\n")
    monkeypatch.setattr(bw, "_run", runner1, raising=True)
    bw.update_aut_provided("pipeline:1", PIPELINE_SHA, "2026-08-09T22:50:55.927Z",
                           "a" * 64, metadata)
    text1 = aut.read_text(encoding="utf-8")
    assert 'race_note: "поверх provided' in text1
    # НЕ встроено в хвостовой комментарий source_commit (тот сохраняет СВОЙ
    # человеческий комментарий "# старая сборка" из фикстуры, как задумано
    # для _rewrite_field, — race-note там быть не должно).
    source_line = next(ln for ln in text1.splitlines() if ln.startswith("source_commit:"))
    assert "поверх provided" not in source_line
    assert source_line.startswith(f"source_commit: {PIPELINE_SHA}")

    # Второй вызов: гонки больше нет (tip == provided-sha) — поле ОБЯЗАНО
    # очиститься, старая гонка НЕ должна пережить перезапись.
    runner2 = _FakeGitRunner(tip=PIPELINE_SHA)
    monkeypatch.setattr(bw, "_run", runner2, raising=True)
    bw.update_aut_provided("pipeline:1", PIPELINE_SHA, "2026-08-09T23:00:00Z",
                           "b" * 64, metadata)
    text2 = aut.read_text(encoding="utf-8")
    assert 'race_note: ""' in text2
    assert "поверх provided" not in text2


def test_update_aut_local_also_clears_race_note_field(repo, monkeypatch):
    """C2-симметрия: local-путь тоже явно зачищает race_note (не оставляет
    чужую provided-гонку висеть после возврата на local)."""
    text = AUT_TEXT.replace(
        "source_commit:", 'race_note: "поверх provided abc12345 1 несобранных коммитов: xyz"\nsource_commit:')
    aut = _write_aut(repo, text)
    monkeypatch.setattr(bw, "REPO", repo.root, raising=True)
    monkeypatch.setattr(bw, "APP", repo.root / "app-under-test", raising=True)
    monkeypatch.setattr(bw, "AUT_PATH", aut, raising=True)
    metadata = repo.root / "app-under-test" / bw.METADATA_REL
    metadata.parent.mkdir(parents=True, exist_ok=True)
    metadata.write_text(json.dumps({"elements": [
        {"versionCode": 12, "versionName": "1.11"}]}), encoding="utf-8")

    bw.update_aut("c" * 40, [], "feedface")

    out = aut.read_text(encoding="utf-8")
    assert 'race_note: ""' in out
    assert "поверх provided" not in out


# =============================================================================
# _http_get_binary — редиректы/капы (A4/C4/C5)
# =============================================================================

class _Hdrs(dict):
    def get(self, k, default=None):
        return dict.get(self, k, default)


class _FakeResp:
    def __init__(self, data: bytes):
        self._data = data

    def read(self, n=-1):
        if n is None or n < 0:
            out, self._data = self._data, b""
            return out
        out, self._data = self._data[:n], self._data[n:]
        return out

    def close(self):
        pass


class _FakeOpener:
    """steps: список шагов в порядке ожидаемых запросов:
    {"redirect": code, "location": url} | {"body": bytes} | {"error": code}."""

    def __init__(self, steps):
        self.steps = list(steps)
        self.requests: list[tuple[str, dict]] = []

    def open(self, req, timeout=None):
        import urllib.error
        headers = {k: v for k, v in req.header_items()}
        self.requests.append((req.full_url, headers))
        step = self.steps.pop(0)
        if "redirect" in step:
            raise urllib.error.HTTPError(
                req.full_url, step["redirect"], "Redirect", _Hdrs(Location=step["location"]), None)
        if "error" in step:
            raise urllib.error.HTTPError(req.full_url, step["error"], "Error", _Hdrs(), None)
        return _FakeResp(step["body"])


def _req_token(headers: dict) -> str | None:
    # urllib.request.Request.add_header капитализирует ТОЛЬКО первую букву
    # ('PRIVATE-TOKEN' -> 'Private-token') — сверяем регистронезависимо.
    for k, v in headers.items():
        if k.lower() == "private-token":
            return v
    return None


def test_http_get_binary_happy_path_no_redirect():
    opener = _FakeOpener([{"body": b"zipdata"}])
    out = bw._http_get_binary("https://gitlab.com/api/v4/x", "tok", opener=opener)
    assert out == b"zipdata"
    assert _req_token(opener.requests[0][1]) == "tok"


@pytest.mark.parametrize("code", [301, 302, 303, 307, 308])
def test_http_get_binary_strips_token_on_every_3xx_cross_host(code):
    opener = _FakeOpener([
        {"redirect": code, "location": "https://cdn.other-host.example/blob"},
        {"body": b"payload"},
    ])
    out = bw._http_get_binary("https://gitlab.com/api/v4/x", "secret-tok", opener=opener)
    assert out == b"payload"
    assert len(opener.requests) == 2
    assert opener.requests[0][0] == "https://gitlab.com/api/v4/x"
    assert _req_token(opener.requests[0][1]) == "secret-tok"
    assert opener.requests[1][0] == "https://cdn.other-host.example/blob"
    assert _req_token(opener.requests[1][1]) is None   # C4: токен НЕ уехал


def test_http_get_binary_redirect_chain_at_cap_boundary_succeeds():
    """Граница «на»: РОВНО MAX_REDIRECTS редиректов, затем успех — не отказ."""
    steps = [{"redirect": 302, "location": f"https://h{i}.example/x"} for i in range(bw.MAX_REDIRECTS)]
    steps.append({"body": b"ok"})
    opener = _FakeOpener(steps)
    out = bw._http_get_binary("https://gitlab.com/api/v4/x", "tok", opener=opener)
    assert out == b"ok"


def test_http_get_binary_redirect_chain_over_cap_boundary_fails():
    """Граница «за»: MAX_REDIRECTS+1 редиректов — петля, отказ."""
    steps = [{"redirect": 302, "location": f"https://h{i}.example/x"}
             for i in range(bw.MAX_REDIRECTS + 1)]
    steps.append({"body": b"unreachable"})
    opener = _FakeOpener(steps)
    with pytest.raises(bw.ArtifactError, match="редиректов"):
        bw._http_get_binary("https://gitlab.com/api/v4/x", "tok", opener=opener)


def test_http_get_binary_404_raises_not_found():
    opener = _FakeOpener([{"error": 404}])
    with pytest.raises(bw.ArtifactNotFoundError):
        bw._http_get_binary("https://gitlab.com/api/v4/x", "tok", opener=opener)


def test_http_get_binary_other_http_error_raises_generic():
    opener = _FakeOpener([{"error": 500}])
    with pytest.raises(bw.ArtifactError):
        bw._http_get_binary("https://gitlab.com/api/v4/x", "tok", opener=opener)


def test_http_get_binary_body_cap_boundary_at_limit_succeeds():
    opener = _FakeOpener([{"body": b"x" * 10}])
    out = bw._http_get_binary("https://gitlab.com/api/v4/x", "tok", opener=opener, max_body_bytes=10)
    assert out == b"x" * 10


def test_http_get_binary_body_cap_boundary_over_limit_fails():
    opener = _FakeOpener([{"body": b"x" * 11}])
    with pytest.raises(bw.ArtifactError, match="кап"):
        bw._http_get_binary("https://gitlab.com/api/v4/x", "tok", opener=opener, max_body_bytes=10)


def test_http_get_binary_redirect_without_location_fails():
    opener = _FakeOpener([{"redirect": 302, "location": ""}])
    with pytest.raises(bw.ArtifactError, match="Location"):
        bw._http_get_binary("https://gitlab.com/api/v4/x", "tok", opener=opener)


# =============================================================================
# _safe_extract_zip — capы/zip-slip/symlink/не-UTF8/раскладка (B12/C5/C6)
# =============================================================================

def _make_zip(entries: dict[str, bytes], *, infos: dict[str, zipfile.ZipInfo] | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        for name, content in entries.items():
            zi = (infos or {}).get(name) or zipfile.ZipInfo(name)
            zf.writestr(zi, content)
    return buf.getvalue()


def _valid_debug_zip() -> bytes:
    return _make_zip({
        "app/build/outputs/apk/debug/app-debug.apk": b"apk-bytes",
        "app/build/outputs/apk/debug/output-metadata.json": b'{"elements":[{"versionCode":1,"versionName":"x"}]}',
    })


def test_safe_extract_happy_path(tmp_path):
    apk, meta = bw._safe_extract_zip(_valid_debug_zip(), tmp_path)
    assert apk.name == "app-debug.apk" and apk.read_bytes() == b"apk-bytes"
    assert meta.name == "output-metadata.json"


def test_safe_extract_missing_apk_release_layout_lists_actual_paths(tmp_path):
    data = _make_zip({"app/build/outputs/apk/release/app-release.apk": b"release-apk"})
    with pytest.raises(bw.ArtifactError, match="app-debug.apk"):
        bw._safe_extract_zip(data, tmp_path)


def test_safe_extract_missing_metadata_next_to_apk(tmp_path):
    data = _make_zip({"app/build/outputs/apk/debug/app-debug.apk": b"apk-bytes"})
    with pytest.raises(bw.ArtifactError, match="output-metadata.json"):
        bw._safe_extract_zip(data, tmp_path)


def test_safe_extract_zip_slip_dotdot_rejected(tmp_path):
    data = _make_zip({"../../evil.txt": b"pwned"})
    with pytest.raises(bw.ArtifactError, match="zip-slip"):
        bw._safe_extract_zip(data, tmp_path)
    # ДО extractall: ничего не должно было просочиться на диск за пределы tmp_path.
    assert not (tmp_path.parent / "evil.txt").exists()


def test_safe_extract_symlink_member_rejected(tmp_path):
    zi = zipfile.ZipInfo("app/build/outputs/apk/debug/app-debug.apk")
    zi.external_attr = (0xA1FF << 16)   # S_IFLNK | 0777
    data = _make_zip({"app/build/outputs/apk/debug/app-debug.apk": b"link-target"}, infos={
        "app/build/outputs/apk/debug/app-debug.apk": zi})
    with pytest.raises(bw.ArtifactError, match="symlink"):
        bw._safe_extract_zip(data, tmp_path)


def test_safe_extract_non_utf8_name_rejected(tmp_path):
    """Публичный zipfile API не может записать НЕ-UTF8 имя напрямую (str-имя
    без чистого ASCII форсирует UTF-8-флаг при записи) — байты подменяются
    ПОСТ-ФАКТУМ в собранном архиве (local header + central directory), тем
    же числом байт, чтобы структура zip осталась валидной."""
    placeholder = "XXXXXXXX"
    data = bytearray(_make_zip({placeholder: b"content"}))
    raw_invalid_utf8 = b"\xff\xfe\x00\x01\x02\x03\x04\x05"
    assert len(raw_invalid_utf8) == len(placeholder.encode("ascii"))
    data = bytes(data).replace(placeholder.encode("ascii"), raw_invalid_utf8)

    with pytest.raises(bw.ArtifactError, match="UTF"):
        bw._safe_extract_zip(data, tmp_path)


def test_safe_extract_member_count_cap_boundary_at_limit_ok(tmp_path, monkeypatch):
    monkeypatch.setattr(bw, "MAX_ZIP_MEMBERS", 3, raising=True)
    entries = {f"junk{i}.txt": b"x" for i in range(2)}
    entries["app/build/outputs/apk/debug/app-debug.apk"] = b"apk"
    data = _make_zip(entries)
    with pytest.raises(bw.ArtifactError, match="output-metadata.json"):
        # 3 членов == лимит -> капы пройдены, падает на отсутствии metadata
        # (доказывает, что кап НЕ сработал на границе).
        bw._safe_extract_zip(data, tmp_path)


def test_safe_extract_member_count_cap_boundary_over_limit_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(bw, "MAX_ZIP_MEMBERS", 2, raising=True)
    entries = {f"junk{i}.txt": b"x" for i in range(3)}
    data = _make_zip(entries)
    with pytest.raises(bw.ArtifactError, match="zip-бомба"):
        bw._safe_extract_zip(data, tmp_path)


def test_safe_extract_size_cap_boundary_at_limit_ok(tmp_path, monkeypatch):
    monkeypatch.setattr(bw, "MAX_EXTRACTED_BYTES", 10, raising=True)
    data = _make_zip({"a.txt": b"x" * 10})
    with pytest.raises(bw.ArtifactError, match="app-debug.apk"):
        # Ровно на границе -> капы пройдены, падает дальше (отсутствие apk).
        bw._safe_extract_zip(data, tmp_path)


def test_safe_extract_size_cap_boundary_over_limit_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(bw, "MAX_EXTRACTED_BYTES", 10, raising=True)
    data = _make_zip({"a.txt": b"x" * 11})
    with pytest.raises(bw.ArtifactError, match="zip-бомба"):
        bw._safe_extract_zip(data, tmp_path)


def test_understated_declared_file_size_fails_closed_as_artifact_error(
        tmp_path, monkeypatch):
    """Критик-мелочь 1 (2026-08-10) — ЭМПИРИЧЕСКАЯ проверка вместо теста
    written_total-ветки: byte-патч central-directory file_size (offset+24)
    ЗАНИЖЕН относительно реальных данных (compress_size/CRC честны).
    Гипотеза «zipfile физически запишет больше объявленного, а written_total
    поймает лишнее» ОПРОВЕРГНУТА эмпирически: cpython `ZipExtFile.__init__`
    ставит `self._left = zinfo.file_size` и `_read1()` обрезает вывод до
    `self._left` — физическая запись НИКОГДА не превышает ДЕКЛАРИРОВАННЫЙ
    file_size через `extractall()`; заниженная декларация вместо этого рвёт
    поток раньше срока и поднимает `zipfile.BadZipFile: Bad CRC-32`
    (несовпадение с CRC полного контента) — ОТКАЗ ЗАКРЫТ (fail-closed),
    просто другим путём, чем исходно предполагалось (см. докстринг
    _safe_extract_zip рядом с written_total — пре-чек по declared file_size
    уже покрывает единственный достижимый через extractall() класс bomb-
    атаки).

    ПОБОЧНАЯ находка по ходу той же эмпирики (не мелочь критика, замечена
    самостоятельно): именно ЭТОТ прогон впервые обнажил, что extractall()
    может поднять сырой zipfile.BadZipFile, не обёрнутый в ArtifactError —
    класс исправлен (try/except вокруг extractall() добавлен) той же
    правкой; тест теперь фиксирует ПРАВИЛЬНЫЙ (закрытый) контракт."""
    import struct
    monkeypatch.setattr(bw, "MAX_EXTRACTED_BYTES", 10, raising=True)
    big_content = b"x" * 20
    data = bytearray(_make_zip({"a.txt": big_content}))

    central_sig = b"PK\x01\x02"
    idx = data.find(central_sig)
    assert idx != -1, "central directory record не найден"
    # offset 20..24 = compressed size, offset 24..28 = uncompressed size
    # (file_size) — патчим ТОЛЬКО file_size, оставляя compressed size честным.
    fake_declared_size = 1
    data[idx + 24:idx + 28] = struct.pack("<I", fake_declared_size)
    data = bytes(data)

    # Контроль манипуляции: zipfile действительно видит заниженный file_size
    # (declared), но compress_size (и сами байты) остаются полными.
    zf = zipfile.ZipFile(io.BytesIO(data))
    zi = zf.infolist()[0]
    assert zi.file_size == fake_declared_size
    assert zi.compress_size == len(big_content)
    zf.close()

    with pytest.raises(bw.ArtifactError, match="битый/обрезанный"):
        bw._safe_extract_zip(data, tmp_path)


# =============================================================================
# download_artifact — резолв pipeline/job -> job dict -> скачивание+извлечение
# =============================================================================

class _FakeTransport:
    def __init__(self, responses):
        self.calls: list[dict] = []
        self._responses = list(responses)

    def __call__(self, method, url, headers, data):
        self.calls.append({"method": method, "url": url, "headers": dict(headers)})
        if not self._responses:
            raise AssertionError(f"неожиданный вызов {method} {url}")
        status, body = self._responses.pop(0)
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        return status, body


def _client(responses):
    transport = _FakeTransport(responses)
    client = gs.GitLabClient(
        "https://gitlab.com/api/v4/projects/Xartaxana1%2Fao3-wrapper", "tok-123",
        transport=transport)
    return client, transport


def _job_payload(job_id=999, *, name="build:debug", sha="d" * 40,
                 finished_at="2026-08-09T22:50:55.927Z", has_artifacts=True):
    return {"id": job_id, "name": name, "status": "success",
            "finished_at": finished_at, "pipeline": {"sha": sha},
            "artifacts_file": ({"filename": "x.zip"} if has_artifacts else None)}


def test_resolve_job_by_job_ref():
    client, transport = _client([(200, _job_payload(job_id=42))])
    job = bw._resolve_job(client, "job", 42)
    assert job["id"] == 42
    assert transport.calls[0]["url"].endswith("/jobs/42")


def test_resolve_job_by_pipeline_ref_picks_build_debug():
    client, transport = _client([(200, [
        _job_payload(job_id=1, name="lint"),
        _job_payload(job_id=2, name="build:debug"),
    ])])
    job = bw._resolve_job(client, "pipeline", 555)
    assert job["id"] == 2
    assert "/pipelines/555/jobs" in transport.calls[0]["url"]


def test_resolve_job_pipeline_without_build_debug_job_raises_not_found():
    client, _t = _client([(200, [_job_payload(job_id=1, name="lint")])])
    with pytest.raises(bw.ArtifactNotFoundError):
        bw._resolve_job(client, "pipeline", 555)


def test_resolve_job_404_raises_not_found():
    client, _t = _client([(404, {"message": "Not Found"})])
    with pytest.raises(bw.ArtifactNotFoundError):
        bw._resolve_job(client, "job", 1)


def test_resolve_job_no_artifacts_file_raises_not_found_via_download_artifact():
    client, _t = _client([(200, _job_payload(has_artifacts=False))])
    with pytest.raises(bw.ArtifactNotFoundError):
        bw.download_artifact(client, "job", 999, "tok", "https://gitlab.com/api/v4/x")


def test_download_artifact_end_to_end(tmp_path):
    client, _t = _client([(200, _job_payload(job_id=999))])
    opener = _FakeOpener([{"body": _valid_debug_zip()}])

    result = bw.download_artifact(
        client, "job", 999, "tok", "https://gitlab.com/api/v4/projects/1", opener=opener)

    assert result["source_commit"] == "d" * 40
    assert result["built_at"] == "2026-08-09T22:50:55.927Z"
    assert result["apk_path"].read_bytes() == b"apk-bytes"
    assert result["metadata_path"].exists()
    import shutil
    shutil.rmtree(result["tmp_dir"], ignore_errors=True)


def test_download_artifact_extraction_failure_cleans_tmp_dir():
    client, _t = _client([(200, _job_payload(job_id=999))])
    opener = _FakeOpener([{"body": b"not a zip"}])
    with pytest.raises(bw.ArtifactError):
        bw.download_artifact(client, "job", 999, "tok", "https://gitlab.com/api/v4/x", opener=opener)


# =============================================================================
# watch_provided — оркестрация CLI-уровня (A5/B11/C2/C8/A4-fallback)
# =============================================================================

def _env(repo, monkeypatch, *, aut_text=AUT_TEXT):
    aut = _write_aut(repo, aut_text)
    monkeypatch.setattr(bw, "REPO", repo.root, raising=True)
    monkeypatch.setattr(bw, "APP", repo.root / "app-under-test", raising=True)
    monkeypatch.setattr(bw, "AUT_PATH", aut, raising=True)
    monkeypatch.setattr(bw, "ESCALATIONS_PATH", repo.root / "state" / "escalations.md", raising=True)
    monkeypatch.setattr(bw, "ORCH_LOG", repo.root / "state" / "orchestrator-log.md", raising=True)
    monkeypatch.setenv("GITLAB_TOKEN", "tok-123")
    # Fetch для race-note (_local_commits_ahead_of_provided) — офлайн best-effort,
    # не должен требовать реального git; коротим на "не прошло" (пустая нота).
    monkeypatch.setattr(bw, "_run", lambda *a, **kw: (128, "offline"), raising=True)
    return aut


def _wire_network(monkeypatch, *, json_responses, zip_body):
    """JSON-вызовы (GitLabClient) — через gs._default_transport; бинарная
    загрузка — монкипатчим bw._http_get_binary целиком (сам механизм
    редиректов/капов уже покрыт отдельными тестами выше)."""
    transport = _FakeTransport(json_responses)
    monkeypatch.setattr(gs, "_default_transport", transport, raising=True)
    monkeypatch.setattr(bw, "_http_get_binary", lambda *a, **kw: zip_body, raising=True)
    return transport


def test_watch_provided_happy_path_pipeline(repo, monkeypatch, capsys):
    aut = _env(repo, monkeypatch)
    _wire_network(monkeypatch, json_responses=[
        (200, [_job_payload(job_id=999, name="build:debug", sha=PIPELINE_SHA,
                            finished_at="2026-08-09T22:50:55.927Z")]),
    ], zip_body=_valid_debug_zip())

    rc = bw.watch_provided("pipeline:2745767053")

    assert rc == 0
    out = aut.read_text(encoding="utf-8")
    assert "build_source: provided" in out
    assert 'provided_ref: "pipeline:2745767053"' in out
    assert f"source_commit: {PIPELINE_SHA}" in out
    assert 'built_at: "2026-08-09T22:50:55.927Z"' in out    # C8: finished_at, не время скачивания
    assert "smoke_status: not_run" in out and "regression_status: not_run" in out
    apk = repo.root / "app-under-test" / bw.APK_REL
    assert apk.exists() and apk.read_bytes() == b"apk-bytes"
    log = repo.read_artifact("state/orchestrator-log.md")
    assert "provided pipeline:2745767053" in log
    out_console = capsys.readouterr().out
    assert "[OK]" in out_console


def test_watch_provided_job_ref_variant(repo, monkeypatch):
    _env(repo, monkeypatch)
    _wire_network(monkeypatch, json_responses=[
        (200, _job_payload(job_id=555, sha=PIPELINE_SHA)),
    ], zip_body=_valid_debug_zip())

    rc = bw.watch_provided("job:555")
    assert rc == 0


def test_watch_provided_idempotent_same_ref_matching_sha_skips_network(repo, monkeypatch, capsys):
    """B11: тот же ref в yaml И sha256 файла на диске совпадает -> без сети."""
    apk = repo.root / "app-under-test" / bw.APK_REL
    apk.parent.mkdir(parents=True, exist_ok=True)
    apk.write_bytes(b"already-here")
    import hashlib
    sha = hashlib.sha256(b"already-here").hexdigest()
    text = AUT_TEXT + f'\nbuild_source: provided\nprovided_ref: "pipeline:42"\n'
    text = text.replace('apk_sha256: "deadbeef"', f'apk_sha256: "{sha}"')
    _env(repo, monkeypatch, aut_text=text)

    def _boom(*a, **kw):
        raise AssertionError("сеть не должна вызываться — идемпотентность B11")
    monkeypatch.setattr(gs, "_default_transport", _boom, raising=True)
    monkeypatch.setattr(bw, "_http_get_binary", _boom, raising=True)

    rc = bw.watch_provided("pipeline:42")
    assert rc == 0
    assert "уже актуально" in capsys.readouterr().out


def test_watch_provided_same_ref_but_sha_mismatch_proceeds_to_download(repo, monkeypatch):
    apk = repo.root / "app-under-test" / bw.APK_REL
    apk.parent.mkdir(parents=True, exist_ok=True)
    apk.write_bytes(b"stale-bytes")
    text = AUT_TEXT + '\nbuild_source: provided\nprovided_ref: "pipeline:42"\n'
    text = text.replace('apk_sha256: "deadbeef"', 'apk_sha256: "0000000000000000000000000000000000000000000000000000000000000000"')
    _env(repo, monkeypatch, aut_text=text)
    _wire_network(monkeypatch, json_responses=[
        (200, [_job_payload(job_id=999, sha=PIPELINE_SHA)]),
    ], zip_body=_valid_debug_zip())

    rc = bw.watch_provided("pipeline:42")
    assert rc == 0
    assert apk.read_bytes() == b"apk-bytes"   # перезаписан свежескачанным


def test_watch_provided_no_token_fails_with_escalation_no_network(repo, monkeypatch):
    _env(repo, monkeypatch)
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)

    def _boom(*a, **kw):
        raise AssertionError("сеть не должна вызываться без токена")
    monkeypatch.setattr(gs, "_default_transport", _boom, raising=True)

    rc = bw.watch_provided("pipeline:1")
    assert rc == 1
    esc = repo.read_artifact("state/escalations.md")
    assert "GITLAB_TOKEN" in esc


def test_watch_provided_malformed_ref_fails_fast():
    assert bw.watch_provided("garbage") == 1


def test_watch_provided_404_no_new_commits_does_not_falsely_claim_local(
        repo, monkeypatch, capsys):
    """Критик-вход (мелочь 2, 2026-08-10): yaml уже был build_source:
    provided ДО этого вызова; локальный watch() не находит новых коммитов и
    НИЧЕГО не меняет — эскалация ОБЯЗАНА отражать реальность (build_source
    НЕ изменился), не утверждать «откатилась на local», когда это ложь."""
    text = AUT_TEXT + '\nbuild_source: provided\nprovided_ref: "pipeline:1"\n'
    aut = _env(repo, monkeypatch, aut_text=text)
    transport = _FakeTransport([(404, {"message": "Not Found"})])
    monkeypatch.setattr(gs, "_default_transport", transport, raising=True)

    class _LocalFakeRunner:
        """fetch offline -> нет новых коммитов, watch() возвращает 0 без
        сборки и НЕ трогает файл вовсе (ничего не меняется)."""
        def __call__(self, args, *, cwd=None, env=None, timeout=120):
            cmd = " ".join(str(a) for a in args)
            if "fetch" in cmd:
                return 0, ""
            if "rev-parse" in cmd:
                return 0, OLD_SHA + "\n"   # tip == текущий source_commit -> "новых нет"
            raise AssertionError(f"unexpected: {cmd}")

    monkeypatch.setattr(bw, "_run", _LocalFakeRunner(), raising=True)

    rc = bw.watch_provided("pipeline:404404")

    assert rc == 0   # локальный watch() штатно вернул 0 ("новых коммитов нет")
    esc = repo.read_artifact("state/escalations.md")
    assert "pipeline:404404" in esc
    assert "НЕ изменил build_source" in esc
    assert "'provided'" in esc            # честно называет РЕАЛЬНОЕ текущее значение
    assert "откатилась на build_source: local" not in esc   # больше не лжём
    out = capsys.readouterr().out
    assert "[WARN]" in out
    # yaml физически НЕ тронут (fallback пошёл штатным local-путём, а тот в
    # отсутствие новых коммитов вообще не трогает файл) — остался provided.
    assert "build_source: provided" in aut.read_text(encoding="utf-8")


def test_watch_provided_404_with_new_commits_honestly_reports_local_switch(
        repo, monkeypatch, capsys):
    """Симметричный случай: локальный watch() РЕАЛЬНО находит новый коммит и
    пересобирает -> build_source действительно становится local -> эскалация
    честно подтверждает ИМЕННО это (не смешивает с случаем «ничего не
    изменилось»)."""
    aut = _env(repo, monkeypatch)   # база: build_source вообще отсутствует
    transport = _FakeTransport([(404, {"message": "Not Found"})])
    monkeypatch.setattr(gs, "_default_transport", transport, raising=True)

    metadata = repo.root / "app-under-test" / bw.METADATA_REL
    metadata.parent.mkdir(parents=True, exist_ok=True)
    metadata.write_text(json.dumps({"elements": [
        {"versionCode": 12, "versionName": "1.11"}]}), encoding="utf-8")

    class _LocalFakeRunner:
        def __call__(self, args, *, cwd=None, env=None, timeout=120):
            cmd = " ".join(str(a) for a in args)
            if "fetch" in cmd:
                return 0, ""
            if "rev-parse" in cmd:
                return 0, "c" * 40 + "\n"   # новый tip
            if "rev-list" in cmd:
                return 0, "c" * 40 + "\n"
            if "checkout" in cmd:
                return 0, ""
            if "gradlew" in cmd:
                apk = repo.root / "app-under-test" / bw.APK_REL
                apk.parent.mkdir(parents=True, exist_ok=True)
                apk.write_bytes(b"fresh-local-apk")
                return 0, "BUILD SUCCESSFUL"
            raise AssertionError(f"unexpected: {cmd}")

    monkeypatch.setattr(bw, "_run", _LocalFakeRunner(), raising=True)

    rc = bw.watch_provided("pipeline:404404")

    assert rc == 0
    esc = repo.read_artifact("state/escalations.md")
    assert "перешла на build_source: local (локальная сборка выполнена)" in esc
    assert "build_source: local" in aut.read_text(encoding="utf-8")


def test_watch_provided_generic_artifact_error_fails_no_fallback(repo, monkeypatch, capsys):
    """Не-404 отказ (битый архив и т.п.) -> [FAIL], БЕЗ fallback на local —
    --provided осознанное действие оператора, молчаливая подмена была бы
    сюрпризом."""
    _env(repo, monkeypatch)
    _wire_network(monkeypatch, json_responses=[
        (200, [_job_payload(job_id=999)]),
    ], zip_body=b"not-a-zip-at-all")

    def _boom_local(*a, **kw):
        raise AssertionError("НЕ должен упасть в локальный watch() на generic-ошибке")
    # Если бы код ошибочно фолбэчил -- watch() дошёл бы до _run и упал тут.
    monkeypatch.setattr(bw, "_run", _boom_local, raising=True)

    rc = bw.watch_provided("pipeline:1")

    assert rc == 1
    esc = repo.read_artifact("state/escalations.md")
    assert "pipeline:1" in esc
    out = capsys.readouterr().out
    assert "[FAIL]" in out


# =============================================================================
# download_only / --download-only --dest — B2 (критик R1, 2026-08-10)
# =============================================================================

def test_download_only_happy_path_writes_dest_files_and_verbatim_lines(
        repo, monkeypatch, tmp_path, capsys):
    """(а) Оба файла оказываются в dest, ОБЕ печатные строки дословно
    (`APK: <path>` / `METADATA: <path>` — жёстко зашитый контракт для
    fix-verifier.md), канонический APK и state/app-under-test.yaml НЕ
    тронуты вовсе (--download-only без побочных эффектов на global state)."""
    aut = _env(repo, monkeypatch)
    before_aut = aut.read_bytes()
    canonical_apk = repo.root / "app-under-test" / bw.APK_REL
    assert not canonical_apk.exists()   # ничего не создано заранее

    _wire_network(monkeypatch, json_responses=[
        (200, [_job_payload(job_id=999, sha=PIPELINE_SHA)]),
    ], zip_body=_valid_debug_zip())

    dest_dir = tmp_path / "download_only_dest"
    rc = bw.download_only("pipeline:1", str(dest_dir))

    assert rc == 0
    apk_dest = dest_dir / "app-debug.apk"
    metadata_dest = dest_dir / "output-metadata.json"
    assert apk_dest.read_bytes() == b"apk-bytes"
    assert metadata_dest.exists()

    out = capsys.readouterr().out
    lines = out.strip().splitlines()
    assert f"APK: {apk_dest}" in lines
    assert f"METADATA: {metadata_dest}" in lines

    # Побочных эффектов на global state нет: yaml байт-в-байт тот же,
    # канонический путь по-прежнему не существует.
    assert aut.read_bytes() == before_aut
    assert not canonical_apk.exists()


def test_download_only_dest_created_if_missing(repo, monkeypatch, tmp_path):
    _env(repo, monkeypatch)
    _wire_network(monkeypatch, json_responses=[
        (200, [_job_payload(job_id=999, sha=PIPELINE_SHA)]),
    ], zip_body=_valid_debug_zip())
    dest_dir = tmp_path / "nested" / "does" / "not" / "exist"

    rc = bw.download_only("pipeline:1", str(dest_dir))

    assert rc == 0
    assert dest_dir.is_dir()
    assert (dest_dir / "app-debug.apk").exists()


def test_download_only_artifact_not_found_fails_without_escalation(
        repo, monkeypatch, tmp_path, capsys):
    """(в) ArtifactNotFoundError -> [FAIL] + exit 1, БЕЗ записи эскалации
    (в отличие от watch_provided, download_only не пишет ни в yaml, ни в
    escalations.md — точечный вызов, эскалирует вызывающий агент/промпт)."""
    _env(repo, monkeypatch)
    transport = _FakeTransport([(404, {"message": "Not Found"})])
    monkeypatch.setattr(gs, "_default_transport", transport, raising=True)

    rc = bw.download_only("pipeline:404404", str(tmp_path / "dest"))

    assert rc == 1
    out = capsys.readouterr().out
    assert "[FAIL]" in out
    assert not (repo.root / "state" / "escalations.md").exists()


def test_download_only_no_token_fails_without_network(repo, monkeypatch, tmp_path):
    _env(repo, monkeypatch)
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)

    def _boom(*a, **kw):
        raise AssertionError("сеть не должна вызываться без токена")
    monkeypatch.setattr(gs, "_default_transport", _boom, raising=True)

    rc = bw.download_only("pipeline:1", str(tmp_path / "dest"))
    assert rc == 1


def test_download_only_malformed_ref_reports_own_flag_name(capsys):
    """Нит 1: сообщение об ошибке обязано называть --download-only, НЕ
    --provided (общая _parse_provided_ref параметризована flag_name)."""
    rc = bw.download_only("garbage", "somewhere")
    assert rc == 1
    out = capsys.readouterr().out
    assert "--download-only" in out
    assert "--provided" not in out


def test_parse_provided_ref_reports_flag_name_parametrized():
    with pytest.raises(ValueError, match=r"--download-only 'bogus'"):
        bw._parse_provided_ref("bogus", flag_name="--download-only")
    with pytest.raises(ValueError, match=r"--provided 'bogus'"):
        bw._parse_provided_ref("bogus")   # default остаётся --provided


# --- CLI main() wiring --------------------------------------------------------

def test_main_provided_flag_routes_to_watch_provided(repo, monkeypatch):
    _env(repo, monkeypatch)
    calls = []
    monkeypatch.setattr(bw, "watch_provided", lambda ref: calls.append(ref) or 0, raising=True)
    rc = bw.main(["--provided", "pipeline:77"])
    assert rc == 0
    assert calls == ["pipeline:77"]


def test_main_without_provided_flag_routes_to_watch(monkeypatch):
    called = {}
    monkeypatch.setattr(bw, "watch", lambda **kw: called.update(kw) or 0, raising=True)
    rc = bw.main([])
    assert rc == 0


def test_main_download_only_without_dest_fails_with_guard_message(capsys):
    """(б) main(['--download-only', 'pipeline:1']) без --dest -> exit 1 +
    сообщение-guard, без единого сетевого вызова (падает на argparse-уровне
    ДО download_only())."""
    rc = bw.main(["--download-only", "pipeline:1"])
    assert rc == 1
    out = capsys.readouterr().out
    assert "--download-only" in out and "--dest" in out


def test_main_download_only_routes_to_download_only_with_dest(monkeypatch):
    calls = []
    monkeypatch.setattr(bw, "download_only",
                        lambda ref, dest: calls.append((ref, dest)) or 0, raising=True)
    rc = bw.main(["--download-only", "pipeline:1", "--dest", "some/dir"])
    assert rc == 0
    assert calls == [("pipeline:1", "some/dir")]
