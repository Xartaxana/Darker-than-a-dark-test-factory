"""Тесты компактной ref-проекции живого UI-дерева (scripts/ui_snapshot.py).

Экономия токенов воркеров (test-automator/test-maintainer): вместо полного
uiautomator/page_source XML — короткий пронумерованный список значимых узлов
и локаторы-кандидаты по ref (--ref eN), вставляемые прямо в screens (см.
framework/screens/base_screen.py: by_desc/by_text — тот же приоритет
content-desc > text > XPath).

Фикстура scripts/tests/data/sample_uiautomator_dump.xml — синтетический дамп
формата uiautomator dump (7 значимых узлов из 11 в дереве):
  e1 ImageButton content-desc="Open side panel"   clickable          -> content-desc-кандидат
  e2 TextView    text="AO3 Reader"                (только подпись)
  e3 ImageButton content-desc="Toggle dark mode"  checkable, enabled=false -> флаг enabled=false
  e4 WebView     (без подписи)                    scrollable         -> флаг scroll
  e5 Button      text="Sign in"                   clickable          -> text-кандидат
  e6 EditText    (без подписи)                    clickable          -> включён по clickable
  e7 EditText    (без подписи)                    focusable, НЕ clickable -> включён по
                                                   focusable-input; без content-desc/text ->
                                                   XPath-кандидат через ближайшего подписанного
                                                   родителя (resource-id корня)

Живой adb в тестах НЕ дёргается — только --file/--stdin через внутренние функции
и main(). Запуск: python -m pytest scripts/tests -q
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import ui_snapshot as us

FIXTURE = Path(__file__).resolve().parent / "data" / "sample_uiautomator_dump.xml"


def _tree():
    root = ET.fromstring(FIXTURE.read_text(encoding="utf-8"))
    nodes = us._walk(root)
    ref_map = us._assign_refs(nodes)
    return nodes, ref_map


# --- фильтрация значимых узлов -----------------------------------------------

def test_significant_node_count_and_order():
    nodes, ref_map = _tree()
    assert len(ref_map) == 7
    # Контейнеры без подписи и без интерактивности (root FrameLayout, toolbar
    # LinearLayout, внутренний FrameLayout вокруг кнопки) отфильтрованы.
    labels = [us._short_class(n.elem.get("class", "")) for n in nodes if n.ref is not None]
    assert labels == ["ImageButton", "TextView", "ImageButton", "WebView",
                       "Button", "EditText", "EditText"]


def test_ref_numbering_matches_document_order():
    _, ref_map = _tree()
    assert ref_map["e1"].elem.get("content-desc") == "Open side panel"
    assert ref_map["e2"].elem.get("text") == "AO3 Reader"
    assert ref_map["e5"].elem.get("text") == "Sign in"


def test_ref_numbering_is_deterministic_across_reparse():
    _, ref_map1 = _tree()
    _, ref_map2 = _tree()
    assert list(ref_map1.keys()) == list(ref_map2.keys())
    for key in ref_map1:
        assert ref_map1[key].elem.attrib == ref_map2[key].elem.attrib


def test_clickable_edittext_included():
    _, ref_map = _tree()
    assert ref_map["e6"].elem.get("class") == "android.widget.EditText"


def test_focusable_only_edittext_included_without_clickable():
    """focusable-input (§2): включён даже при clickable=false."""
    _, ref_map = _tree()
    node = ref_map["e7"]
    assert node.elem.get("class") == "android.widget.EditText"
    assert node.elem.get("clickable") == "false"
    assert node.elem.get("focusable") == "true"


def test_plain_container_without_label_or_interaction_excluded():
    nodes, _ = _tree()
    frame_layouts = [n for n in nodes if n.elem.get("class") == "android.widget.FrameLayout"]
    assert frame_layouts  # есть в дереве (root + обёртка вокруг кнопки)
    assert all(n.ref is None for n in frame_layouts)


# --- формат компактной строки -------------------------------------------------

def test_compact_line_format_content_desc_and_click_flag():
    nodes, _ = _tree()
    text = us.render_compact(nodes)
    assert '[e1] ImageButton "Open side panel" click bounds=0,32..136,136' in text


def test_compact_line_format_text_only_no_flags():
    nodes, _ = _tree()
    text = us.render_compact(nodes)
    assert '[e2] TextView "AO3 Reader" bounds=160,40..500,128' in text


def test_compact_line_format_checkable_disabled_flags():
    """checkable+enabled=false, но checked=false -> флаги "click enabled=false",
    БЕЗ "checked" (checked — это состояние, а не сама возможность)."""
    nodes, _ = _tree()
    text = us.render_compact(nodes)
    assert '[e3] ImageButton "Toggle dark mode" click enabled=false bounds=944,32..1080,136' in text


def test_compact_line_format_scroll_flag_no_label():
    nodes, _ = _tree()
    text = us.render_compact(nodes)
    assert '[e4] WebView "" scroll bounds=0,168..1080,2100' in text


def test_checked_flag_shown_when_actually_checked():
    """checked flag появляется только когда checked="true" — синтетическая проверка
    напрямую через render_compact на модифицированном узле."""
    nodes, ref_map = _tree()
    node = ref_map["e3"]
    node.elem.set("checked", "true")
    text = us.render_compact(nodes)
    assert '[e3] ImageButton "Toggle dark mode" click enabled=false checked bounds=944,32..1080,136' in text


# --- локаторы-кандидаты (--ref) -----------------------------------------------

def test_candidates_content_desc_priority_first():
    _, ref_map = _tree()
    cands = us._candidates_for(ref_map["e1"])
    assert cands[0].startswith('content-desc -> self.by_desc("Open side panel")')
    assert "AppiumBy.ACCESSIBILITY_ID" in cands[0]
    assert any("tap-фолбэк" in c for c in cands)


def test_candidates_text_when_no_content_desc():
    _, ref_map = _tree()
    cands = us._candidates_for(ref_map["e5"])
    assert cands[0].startswith('text -> self.by_text("Sign in")')
    assert "UiSelector" in cands[0]


def test_candidates_xpath_fallback_via_labeled_ancestor():
    """e7: нет content-desc/text -> XPath минимальной глубины через ближайшего
    подписанного предка (корень с resource-id), с верным индексом среди
    EditText-сиблингов (e6 и e7 оба EditText под корнем -> e7 второй)."""
    _, ref_map = _tree()
    cands = us._candidates_for(ref_map["e7"])
    xpath_cand = next(c for c in cands if c.startswith("XPath"))
    assert 'resource-id="com.ao3.wrapper:id/root"' in xpath_cand
    assert "android.widget.EditText[2]" in xpath_cand
    assert "AppiumBy.XPATH" in xpath_cand


def test_candidates_tap_fallback_center_bounds():
    _, ref_map = _tree()
    cands = us._candidates_for(ref_map["e5"])
    tap_cand = next(c for c in cands if "tap-фолбэк" in c)
    assert "self.driver.tap([(540, 1040)])" in tap_cand  # центр 440,1000..640,1080


def test_render_ref_detail_includes_header_and_candidates():
    _, ref_map = _tree()
    out = us.render_ref_detail(ref_map["e1"])
    assert out.startswith('[e1] ImageButton "Open side panel" bounds=0,32..136,136')
    assert "1. content-desc" in out


# --- CLI: --file/--stdin/--full/--ref, без обращения к живому adb ------------

def test_cli_compact_from_file(capsys):
    rc = us.main(["--file", str(FIXTURE)])
    assert rc == 0
    out = capsys.readouterr().out
    assert '[e1] ImageButton "Open side panel" click bounds=0,32..136,136' in out
    assert '[e7]' in out


def test_cli_ref_content_desc(capsys):
    rc = us.main(["--file", str(FIXTURE), "--ref", "e1"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "self.by_desc(\"Open side panel\")" in out


def test_cli_ref_accepts_bare_number(capsys):
    """--ref 1 (без префикса e) — то же самое, что --ref e1."""
    rc = us.main(["--file", str(FIXTURE), "--ref", "1"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "self.by_desc(\"Open side panel\")" in out


def test_cli_ref_unknown_reports_error(capsys):
    rc = us.main(["--file", str(FIXTURE), "--ref", "e999"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "не найден" in err


def test_cli_full_mode_prints_raw_xml(capsys):
    rc = us.main(["--file", str(FIXTURE), "--full"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "<hierarchy" in out
    assert "</hierarchy>" in out
    # компактная проекция в --full НЕ применяется — сырой XML содержит и
    # отфильтрованные контейнеры тоже.
    assert 'resource-id="com.ao3.wrapper:id/root"' in out


def test_cli_stdin_mode(capsys, monkeypatch):
    import io
    monkeypatch.setattr("sys.stdin", io.StringIO(FIXTURE.read_text(encoding="utf-8")))
    rc = us.main(["--stdin"])
    assert rc == 0
    out = capsys.readouterr().out
    assert '[e5] Button "Sign in" click bounds=440,1000..640,1080' in out


def test_live_dump_not_invoked_when_file_given(monkeypatch):
    """Регрессия: --file не должен трогать _live_dump/adb вообще."""
    def _boom():
        raise AssertionError("_live_dump не должен вызываться при --file")
    monkeypatch.setattr(us, "_live_dump", _boom)
    rc = us.main(["--file", str(FIXTURE)])
    assert rc == 0


# --- вспомогательные функции напрямую -----------------------------------------

def test_short_class_strips_package():
    assert us._short_class("android.widget.ImageButton") == "ImageButton"
    assert us._short_class("") == "?"


def test_parse_bounds_and_center():
    b = us._parse_bounds("[100,200][300,400]")
    assert b == (100, 200, 300, 400)
    assert us._bounds_center(b) == (200, 300)
    assert us._parse_bounds("") is None
    assert us._parse_bounds(None) is None


def test_extract_xml_strips_adb_noise_lines():
    noisy = "UI hierarchy dumped to: /dev/tty\n<?xml version='1.0'?><hierarchy></hierarchy>\n"
    assert us._extract_xml(noisy) == "<?xml version='1.0'?><hierarchy></hierarchy>"
    assert us._extract_xml("garbage, no xml here") == ""
