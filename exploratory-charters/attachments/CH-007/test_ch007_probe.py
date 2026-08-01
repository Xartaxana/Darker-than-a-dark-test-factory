"""CH-007 — драйвер exploratory-сессии (вложение чартера, НЕ scripted-кейс).

Запуск (каноническая форма):
  powershell -NoProfile -ExecutionPolicy Bypass -Command
  ". D:\\AO3_tests\\scripts\\tasks.ps1; Invoke-Pytest
   ../exploratory-charters/attachments/CH-007/test_ch007_probe.py -k seed1 -s -q -p no:randomly"

Файл живёт ВНЕ framework/tests (роль exploratory-tester пишет только в свой
чартер и его вложения), поэтому conftest.py конвейера сюда НЕ подтягивается:
драйвер/replay/сидинг поднимаются здесь явно. Это протокольный инструмент
сессии, а не кейс регрессии — ассертов почти нет, есть ЛОГ наблюдений.
"""
from __future__ import annotations

import json
import re
import sys
import time
import traceback
import uuid
from pathlib import Path

# Файл лежит вне framework/ — корень репо в sys.path кладём сами (в штатном
# прогоне это делает rootdir-вставка pytest для framework/tests).
sys.path.insert(0, r"D:\AO3_tests")

from framework.config import settings  # noqa: E402
from framework.core import adb, driver_factory, mitm
from framework.data import recording_builder as rb
from framework.data import seed_db
from framework.data import works as W
from framework.steps import (
    app_steps,
    browser_steps,
    library_steps,
    rating_steps,
    saf_steps,
    settings_steps,
)

ATT = Path(r"D:\AO3_tests\exploratory-charters\attachments\CH-007")
DL = "/sdcard/Download"
_shot_n = [0]


_LOGF = open(ATT / "session-log.txt", "a", encoding="utf-8")  # noqa: SIM115


def log(*a):
    line = f"[{time.strftime('%H:%M:%S')}] " + " ".join(str(x) for x in a)
    # stdout консоли Windows — cp1251, кириллица/эмодзи в нём мусорятся;
    # дословный протокол пишем в UTF-8 файл рядом с чартером
    _LOGF.write(line + "\n")
    _LOGF.flush()
    print(line.encode("ascii", "replace").decode("ascii"), flush=True)


def shot(driver, name: str) -> str:
    _shot_n[0] += 1
    p = ATT / f"{_shot_n[0]:02d}_{name}.png"
    try:
        driver.get_screenshot_as_file(str(p))
        log(f"SHOT {p.name}")
    except Exception as exc:  # noqa: BLE001
        log(f"SHOT FAILED {name}: {exc}")
    return p.name


def step(label, fn, *a, **kw):
    """Шаг протокола: логируем действие, ловим отказ, продолжаем сессию."""
    log(f"--- STEP: {label}")
    try:
        r = fn(*a, **kw)
        log(f"    OK: {label}")
        return r
    except Exception as exc:  # noqa: BLE001
        log(f"    FAIL: {label}: {type(exc).__name__}: {str(exc)[:400]}")
        log("    " + traceback.format_exc().splitlines()[-3])
        return None


_TXT = re.compile(r'(?:text|content-desc)="([^"]+)"')


def dialog_texts(driver, tag: str = ""):
    """Дословный текст видимого диалога/экрана — все непустые text/content-desc."""
    try:
        src = driver.page_source
    except Exception as exc:  # noqa: BLE001
        log(f"    page_source FAILED: {exc}")
        return []
    seen, out = set(), []
    for m in _TXT.finditer(src):
        t = m.group(1)
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    log(f"    TEXTS{('[' + tag + ']') if tag else ''}: {out}")
    return out


def room(tag: str):
    r = seed_db.read_work_ratings()
    log(f"    ROOM[{tag}] n={len(r)}: {json.dumps(r, ensure_ascii=False, sort_keys=True)}")
    return r


def profiles(tag: str):
    p = seed_db.read_filter_profiles()
    log(f"    PROFILES[{tag}]: {json.dumps(p, ensure_ascii=False)}")
    return p


def prefs(tag: str):
    out = adb.run_as("cat shared_prefs/ao3_settings.xml")
    log(f"    PREFS[{tag}]: {out.strip()}")
    return out


def ls(path: str, tag: str = ""):
    out = adb.shell(f'ls -l "{path}"')
    log(f"    LS[{tag}] {path}: {out.strip()}")
    return out


def start_replay(flow: str):
    mitm.set_device_proxy()
    mitm.start_replay(settings.RECORDINGS_DIR / flow)
    mitm.wait_device_proxy_reachable()


def stop_replay():
    try:
        mitm.stop()
    finally:
        mitm.clear_device_proxy()


def new_driver():
    return driver_factory.create_driver(no_reset=True)


def _tap_download_icon_any(driver):
    from framework.screens.base_screen import BaseScreen

    b = BaseScreen(driver)
    b.tap(b.by_desc("Download"))


def _tap_download_icon_fast(driver, n: int):
    """Г7б′: N быстрых тапов по ОДНОЙ download-иконке."""
    from framework.screens.base_screen import BaseScreen

    b = BaseScreen(driver)
    el = b.find(b.by_desc("Download"))
    for i in range(n):
        try:
            el.click()
            log(f"    fast tap {i + 1} ok")
        except Exception as exc:  # noqa: BLE001
            log(f"    fast tap {i + 1} -> {type(exc).__name__}: {str(exc)[:120]}")


def _save_note_series(driver, i: int):
    from framework.screens.rating_overlay import RatingOverlay

    ov = RatingOverlay(driver)
    if ov.is_present(ov.by_text("Add a note"), timeout=2):
        ov.toggle_comment()
    ov.enter_comment(f"series note {i}")
    ov.save_note()


def _delete_downloaded_file_any(driver, title: str):
    from framework.screens.library_screen import LibraryScreen

    lib = LibraryScreen(driver)
    lib.long_press_work(title)
    assert lib.delete_overlay_visible(), "overlay удаления не появился"
    lib.tap_delete_downloaded_file()


def _edit_note(driver, text: str):
    from framework.screens.rating_overlay import RatingOverlay

    ov = RatingOverlay(driver)
    ov.enter_comment(text)
    ov.save_note()


# ---------------------------------------------------------------- seed 1 ----
S1_FILE = "ch007_seed1.json"
S1_P1 = ("CH007 winter search", "work_search%5Bquery%5D=winter")
S1_P2 = ("CH007 fluff search", "work_search%5Bquery%5D=fluff")


def test_seed1_archivarius():
    """Seed 1 «Архивариус»: merge-restore в ИЗМЕНЁННУЮ базу (Г1), содержимое
    JSON vs prefs (Г2), профили (Г8), повторный Restore (Г7в)."""
    adb.shell(f'rm -f "{DL}/ch007_*"')
    adb.shell(f'rm -f "{DL}/{S1_FILE}"')
    app_steps.clean_state()
    rows = [
        (W.LOVED, "SAVE", "note A original", json.dumps(["fluff", "тег с пробелом"])),
        (W.KUDOSED, "LIKE", "note B original", json.dumps(["angst"])),
        (W.READ, "READ", None, None),
        (W.PENDING, "PENDING", None, None),
    ]
    app_steps.seed_with_comment(rows)
    app_steps.seed_filter_profiles([S1_P1, S1_P2])
    log("=== SEED1 setup done")
    room("t0 seeded")
    profiles("t0 seeded")
    prefs("t0 after clean_state")

    start_replay(rb.LISTING_BASIC_FILENAME)
    driver = new_driver()
    try:
        step("wait_app_ready", app_steps.wait_app_ready, driver)

        # --- экспорт бэкапа (ПЕРВЫМ шагом: open_settings_scrolled_to зовёт
        # wait_ui_ready, требующий WebView — он есть только пока активна Browse)
        step("Settings -> Back up", saf_steps.open_settings_scrolled_to, driver, "Back up")
        step("tap Back up", saf_steps.tap_settings_action, driver, "Back up")
        step(
            "SAF save",
            saf_steps.saf_save_document,
            driver,
            filename=S1_FILE,
            before_dismiss=lambda d: (dialog_texts(d, "Backup created"), shot(d, "s1_backup_created")),
        )
        ls(f"{DL}/{S1_FILE}", "backup")
        raw = adb.shell(f'cat "{DL}/{S1_FILE}"')
        log(f"    BACKUP JSON RAW: {raw.strip()}")
        try:
            data = json.loads(raw)
            log(f"    BACKUP TOP KEYS: {sorted(data.keys())}")
            log(f"    BACKUP works[0] keys: {sorted(data['works'][0].keys())}")
            log(f"    BACKUP works ids: {[w['ao3Id'] for w in data['works']]}")
            log(f"    BACKUP profiles: {data['filterProfiles']}")
        except Exception as exc:  # noqa: BLE001
            log(f"    BACKUP JSON parse failed: {exc}")

        # --- жизнь после бэкапа
        step("open Browse", app_steps.open_tab, driver, "Browse")
        step("open listing", browser_steps.open_listing, driver, rb.LISTING_BASIC_URL)
        shot(driver, "s1_listing_before")
        # (а) работа A изменена после бэкапа: рейтинг SAVE->LIKE и другая заметка
        step("tap rate A", browser_steps.tap_rate_button, driver, W.LOVED.ao3_id)
        step("A: rating -> Kudosed", rating_steps.rate_via_listing_overlay, driver, "LIKE")
        dialog_texts(driver, "s1 overlay A open")
        # у A уже есть комментарий -> overlay показывает СВЁРНУТОЕ превью, а не
        # тоггл «Add a note» (наблюдение прогона 1)
        step("A: раскрыть превью заметки", rating_steps.tap_comment_preview, driver, "note A original")
        step("A: note -> changed", _edit_note, driver, "note A CHANGED after backup")
        shot(driver, "s1_overlay_A_changed")
        step("dismiss overlay", rating_steps.dismiss_rating_overlay, driver)
        # (в) работа E появилась ПОСЛЕ бэкапа (в файле её нет)
        step("tap rate E", browser_steps.tap_rate_button, driver, W.DISLIKED.ao3_id)
        step("E: rating -> Pending", rating_steps.rate_via_listing_overlay, driver, "PENDING")
        step("dismiss overlay", rating_steps.dismiss_rating_overlay, driver)
        room("t1 after listing edits")

        # (б) работа B удалена из Library после бэкапа
        step("open Library", app_steps.open_tab, driver, "Library")
        step("open LIKE tab", library_steps.open_library_tab_for, driver, "LIKE")
        shot(driver, "s1_library_like_tab")
        step("delete work B", library_steps.delete_via_overlay, driver, W.KUDOSED.title, "Delete work")
        room("t2 after delete B")

        # профили: P1 переименован, P2 удалён
        step("Settings -> profiles", saf_steps.rescroll_settings_to, driver, S1_P1[0])
        step("rename P1", settings_steps.rename_filter_profile, driver, S1_P1[0], "P1 RENAMED locally")
        step("delete P2", settings_steps.delete_filter_profile, driver, S1_P2[0])
        profiles("t3 after profile edits")
        shot(driver, "s1_profiles_after_edit")

        # 3 настройки (rescroll перед каждой: swipe_to_text из шагов ищет только
        # ВНИЗ, а после секции профилей экран проскроллен ниже — наблюдение прогона 1)
        step("scroll to Theme", saf_steps.rescroll_settings_to, driver, "Theme")
        step("theme DARK", settings_steps.select_theme, driver, "DARK")
        step("scroll to tap-to-scroll", saf_steps.rescroll_settings_to, driver,
             "Tap to scroll (work pages)")
        step("tap_to_scroll ON", settings_steps.enable_tap_to_scroll, driver)
        step("scroll to infinite scroll", saf_steps.rescroll_settings_to, driver,
             "Infinite scroll (listing pages)")
        step("infinite scroll OFF", settings_steps.disable_infinite_scroll, driver)
        prefs("t4 before restore")

        before = room("t4 BEFORE restore")
        profiles("t4 BEFORE restore")

        # --- merge-restore
        step("Settings -> Restore", saf_steps.rescroll_settings_to, driver, "Restore")
        step("tap Restore", saf_steps.tap_settings_action, driver, "Restore")
        step(
            "SAF pick file (restore #1)",
            saf_steps.saf_pick_file,
            driver,
            S1_FILE,
            before_dismiss=lambda d: (dialog_texts(d, "Backup restored #1"), shot(d, "s1_restore1_dialog")),
        )
        after = room("t5 AFTER restore #1")
        profiles("t5 AFTER restore #1")
        prefs("t5 AFTER restore #1")

        # --- повторный Restore (Г7в)
        step("Settings -> Restore (2)", saf_steps.rescroll_settings_to, driver, "Restore")
        step("tap Restore (2)", saf_steps.tap_settings_action, driver, "Restore")
        step(
            "SAF pick file (restore #2)",
            saf_steps.saf_pick_file,
            driver,
            S1_FILE,
            before_dismiss=lambda d: (dialog_texts(d, "Backup restored #2"), shot(d, "s1_restore2_dialog")),
        )
        room("t6 AFTER restore #2")
        profiles("t6 AFTER restore #2")

        step("open Library", app_steps.open_tab, driver, "Library")
        shot(driver, "s1_library_after_restore")
        log(f"=== SEED1 diff before/after keys: before={sorted(before)} after={sorted(after)}")
    finally:
        driver_factory.quit_driver(driver)
        stop_replay()


# ---------------------------------------------------------------- seed 2 ----
EXTREME_TITLES = {
    "a": "Зимняя песнь 🙂🎧 " + "длинный-заголовок-" * 5 + "хвост ✂️ конец",
    "b": 'Bad \\ / : * ? " < > | Chars',
    "c": "   Trailing spaces and dot.   ",
}


def _seed2_round(driver_holder, key: str, run_downloads: bool = True, branch_b: bool = False):
    """Один круг seed 2. driver_holder — список из одного элемента (драйвер)."""
    title = EXTREME_TITLES[key]
    sub = f"ch007_dl_{key}_{uuid.uuid4().hex[:8]}"
    remote_dir = f"{DL}/{sub}"
    bkp = f"ch007_seed2_{key}.json"
    log(f"=== SEED2 round {key}: title={title!r} subdir={sub}")
    adb.shell(f'rm -f "{DL}/{bkp}"')
    adb.shell(f'mkdir -p "{remote_dir}"')
    app_steps.clean_state()
    import dataclasses

    target = dataclasses.replace(W.LOVED, title=title)
    bg1 = dataclasses.replace(W.KUDOSED, title="Фон 🎈 работа с эмодзи")
    bg2 = dataclasses.replace(W.READ, title="B" * 120)
    app_steps.seed_with_comment([
        (target, "SAVE", "многострочная\nзаметка 🙂\nтретья строка", json.dumps(["тег с пробелом", "🙂", ""])),
        (bg1, "LIKE", None, json.dumps(["fluff"])),
        (bg2, "READ", None, None),
    ])
    room(f"s2{key} t0 seeded")

    driver = new_driver()
    driver_holder[0] = driver
    try:
        step("wait_app_ready", app_steps.wait_app_ready, driver)
        # нулевой шаг круга: своя папка загрузок
        step("Settings -> Pick", saf_steps.open_settings_scrolled_to, driver, "Pick")
        step("tap Pick", saf_steps.tap_settings_action, driver, "Pick")
        step("SAF pick folder", saf_steps.saf_pick_folder, driver, f"Download/{sub}")
        dialog_texts(driver, f"s2{key} after folder pick")
        shot(driver, f"s2{key}_after_folder_pick")

        step("open Library", app_steps.open_tab, driver, "Library")
        shot(driver, f"s2{key}_library_light")
        step("open FAVORITE tab", library_steps.open_library_tab_for, driver, "SAVE")
        dialog_texts(driver, f"s2{key} library card")

        if run_downloads:
            # Тап по download-иконке БЕЗ title-скоупа: заголовок круга (b) несёт
            # символ `"`, который ломает и UiSelector.text(), и XPath @text=...
            # (инструментальное ограничение, не поведение приложения). На вкладке
            # FAVORITE одна карточка — скоуп не нужен.
            step("download via card icon", _tap_download_icon_any, driver)
            time.sleep(6)
            ls(remote_dir, f"s2{key} after download")
            out = adb.shell(f'ls "{remote_dir}"')
            log(f"    FILENAMES: {out.strip()!r}")
            body = adb.shell(f'cat "{remote_dir}"/*_900000001.html')
            log(f"    FILE BODY (first 400): {body[:400]!r}")
            log(f"    FILE BODY len={len(body)}")
            shot(driver, f"s2{key}_after_download")
            dialog_texts(driver, f"s2{key} after download")

        # экспорт бэкапа
        step("Settings -> Back up", saf_steps.rescroll_settings_to, driver, "Back up")
        step("tap Back up", saf_steps.tap_settings_action, driver, "Back up")
        step("SAF save", saf_steps.saf_save_document, driver, filename=bkp,
             before_dismiss=lambda d: dialog_texts(d, f"s2{key} Backup created"))
        raw = adb.shell(f'cat "{DL}/{bkp}"')
        log(f"    BACKUP JSON: {raw.strip()[:1500]}")

        # Clear all ratings — файл в SAF-папке остаётся
        step("Clear all ratings", settings_steps.clear_all_ratings, driver)
        room(f"s2{key} after clear all")
        ls(remote_dir, f"s2{key} after clear all")

        # вернуть базе непустоту: рейтинг фон-работе из UI
        step("open Browse", app_steps.open_tab, driver, "Browse")
        step("open listing", browser_steps.open_listing, driver, rb.LISTING_BASIC_URL)
        step("tap rate bg1", browser_steps.tap_rate_button, driver, W.KUDOSED.ao3_id)
        step("bg1 -> Kudosed", rating_steps.rate_via_listing_overlay, driver, "LIKE")
        step("dismiss", rating_steps.dismiss_rating_overlay, driver)
        if branch_b:
            step("tap rate target", browser_steps.tap_rate_button, driver, W.LOVED.ao3_id)
            step("target -> Favorite (ветка Б)", rating_steps.rate_via_listing_overlay, driver, "SAVE")
            step("dismiss", rating_steps.dismiss_rating_overlay, driver)
        room(f"s2{key} BEFORE restore (branch_b={branch_b})")

        step("Settings -> Restore", saf_steps.rescroll_settings_to, driver, "Restore")
        step("tap Restore", saf_steps.tap_settings_action, driver, "Restore")
        step("SAF pick file", saf_steps.saf_pick_file, driver, bkp,
             before_dismiss=lambda d: (dialog_texts(d, f"s2{key} Backup restored"),
                                       shot(d, f"s2{key}_restore_dialog")))
        room(f"s2{key} AFTER restore")

        step("open Library", app_steps.open_tab, driver, "Library")
        step("open FAVORITE tab", library_steps.open_library_tab_for, driver, "SAVE")
        shot(driver, f"s2{key}_library_after_restore")
        dialog_texts(driver, f"s2{key} library after restore")
        step("open FILES tab", library_steps.open_files_tab, driver)
        shot(driver, f"s2{key}_files_tab")
        dialog_texts(driver, f"s2{key} files tab")
        ls(remote_dir, f"s2{key} end")

        if key == "a":
            # Г7а: серия «Save note» x5 по одной работе (через overlay листинга)
            step("open Browse", app_steps.open_tab, driver, "Browse")
            step("tap rate target", browser_steps.tap_rate_button, driver, W.LOVED.ao3_id)
            for i in range(5):
                step(f"Save note #{i + 1}", _save_note_series, driver, i)
            dialog_texts(driver, "s2a after 5x save note")
            shot(driver, "s2a_after_5x_save_note")
            step("dismiss", rating_steps.dismiss_rating_overlay, driver)
            room("s2a after 5x save note")

            # Г7б′: 4 быстрых тапа по ОДНОЙ download-иконке. Чтобы иконка снова
            # была (после релинка карточка показывает open-иконку) — сначала
            # удаляем файл через overlay карточки (TC-035: строка остаётся).
            step("open Library", app_steps.open_tab, driver, "Library")
            step("open FAVORITE tab", library_steps.open_library_tab_for, driver, "SAVE")
            step("delete downloaded file", _delete_downloaded_file_any, driver, title)
            ls(remote_dir, "s2a after delete file")
            step("4 fast taps on Download", _tap_download_icon_fast, driver, 4)
            time.sleep(10)
            ls(remote_dir, "s2a after 4 fast taps")
            out = adb.shell(f'ls "{remote_dir}"')
            log(f"    FILENAMES after fast taps: {out.strip()!r}")
            shot(driver, "s2a_after_fast_taps")
            room("s2a end")
    finally:
        driver_factory.quit_driver(driver)


def test_seed2_round_a():
    start_replay(rb.LISTING_BASIC_FILENAME)
    holder = [None]
    try:
        _seed2_round(holder, "a", run_downloads=True, branch_b=True)
    finally:
        stop_replay()


def test_seed2_round_b():
    start_replay(rb.LISTING_BASIC_FILENAME)
    holder = [None]
    try:
        _seed2_round(holder, "b", run_downloads=True, branch_b=False)
    finally:
        stop_replay()


def test_seed2_round_c():
    start_replay(rb.LISTING_BASIC_FILENAME)
    holder = [None]
    try:
        _seed2_round(holder, "c", run_downloads=True, branch_b=False)
    finally:
        stop_replay()


# --------------------------------------------- проба R1 (репро находки) ----
def read_download_paths(tag: str) -> dict:
    """Прямое чтение downloadPath/title из Room — своя проба, НЕ правка
    `seed_db.read_work_ratings` (граница наблюдаемости чартера: расширение
    фреймворка — не задача сессии)."""
    import shutil
    import sqlite3
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="ch007read_"))
    try:
        db = seed_db._pull_baseline(tmp)
        con = sqlite3.connect(db)
        con.row_factory = sqlite3.Row
        rows = {
            r["ao3Id"]: {"title": r["title"], "downloadPath": r["downloadPath"],
                         "rating": r["rating"], "comment": r["comment"]}
            for r in con.execute("SELECT ao3Id,title,rating,comment,downloadPath FROM work_ratings")
        }
        con.close()
        log(f"    DLPATH[{tag}]: {json.dumps(rows, ensure_ascii=False)}")
        return rows
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_r1_save_note_vs_downloadpath():
    """Репро подозрения из круга seed2-a: правка заметки/тега через overlay
    листинга у уже СКАЧАННОЙ работы теряет связь с файлом (downloadPath)."""
    sub = f"ch007_r1_{uuid.uuid4().hex[:8]}"
    remote_dir = f"{DL}/{sub}"
    adb.shell(f'mkdir -p "{remote_dir}"')
    app_steps.clean_state()
    app_steps.seed_with_comment([(W.LOVED, "SAVE", None, None)])
    start_replay(rb.LISTING_BASIC_FILENAME)
    driver = new_driver()
    try:
        step("wait_app_ready", app_steps.wait_app_ready, driver)
        step("Settings -> Pick", saf_steps.open_settings_scrolled_to, driver, "Pick")
        step("tap Pick", saf_steps.tap_settings_action, driver, "Pick")
        step("SAF pick folder", saf_steps.saf_pick_folder, driver, f"Download/{sub}")
        step("open Library", app_steps.open_tab, driver, "Library")
        step("open FAVORITE", library_steps.open_library_tab_for, driver, "SAVE")
        step("download via card", _tap_download_icon_any, driver)
        time.sleep(8)
        ls(remote_dir, "r1 after download")
        read_download_paths("r1 after download")
        dialog_texts(driver, "r1 card after download")

        for cycle in (1, 2):
            log(f"=== R1 cycle {cycle}: правка заметки через overlay листинга")
            step("open Browse", app_steps.open_tab, driver, "Browse")
            step("open listing", browser_steps.open_listing, driver, rb.LISTING_BASIC_URL)
            step("tap rate", browser_steps.tap_rate_button, driver, W.LOVED.ao3_id)
            dialog_texts(driver, f"r1 c{cycle} overlay before save")
            step("save note", _save_note_series, driver, cycle)
            dialog_texts(driver, f"r1 c{cycle} overlay after save")
            shot(driver, f"r1_c{cycle}_overlay_after_save")
            step("dismiss", rating_steps.dismiss_rating_overlay, driver)
            read_download_paths(f"r1 c{cycle} after save note")
            step("open Library", app_steps.open_tab, driver, "Library")
            step("open FAVORITE", library_steps.open_library_tab_for, driver, "SAVE")
            dialog_texts(driver, f"r1 c{cycle} card after save note")
            shot(driver, f"r1_c{cycle}_card_after_save_note")
            ls(remote_dir, f"r1 c{cycle} folder")

        # контроль: правка ТЕГА той же работы (вторая дверь той же поверхности)
        step("open Browse", app_steps.open_tab, driver, "Browse")
        step("tap rate", browser_steps.tap_rate_button, driver, W.LOVED.ao3_id)
        step("add tag", rating_steps.add_tag_via_listing_overlay, driver, "r1-tag")
        step("dismiss", rating_steps.dismiss_rating_overlay, driver)
        read_download_paths("r1 after add tag")
        step("open Library", app_steps.open_tab, driver, "Library")
        step("open FAVORITE", library_steps.open_library_tab_for, driver, "SAVE")
        dialog_texts(driver, "r1 card after add tag")
        shot(driver, "r1_card_after_add_tag")
        ls(remote_dir, "r1 end")
    finally:
        driver_factory.quit_driver(driver)
        stop_replay()
        adb.shell(f'rm -rf "{remote_dir}"')


# ---------------------------------------------------------------- seed 4 ----
def test_seed4_negative_import():
    """Г9: Restore не-JSON и пустого файла."""
    adb.shell(f'rm -f "{DL}/ch007_probe_bad.html" "{DL}/ch007_probe_empty.json"')
    app_steps.clean_state()
    app_steps.seed_with_comment([(W.LOVED, "SAVE", "seed4 note", None)])
    tmp = Path(settings.REPO_ROOT) / "framework" / "data" / "fixtures" / "downloaded_work.html"
    adb.push_external(tmp, f"{DL}/ch007_probe_bad.html")
    adb.shell(f'touch "{DL}/ch007_probe_empty.json"')
    ls(f"{DL}/ch007_probe_bad.html", "bad")
    ls(f"{DL}/ch007_probe_empty.json", "empty")
    before = room("s4 before")
    driver = new_driver()
    try:
        step("wait_app_ready", app_steps.wait_app_ready, driver)
        step("Settings -> Restore", saf_steps.open_settings_scrolled_to, driver, "Restore")
        step("tap Restore", saf_steps.tap_settings_action, driver, "Restore")
        step("SAF pick bad html", saf_steps.saf_pick_file, driver, "ch007_probe_bad.html",
             before_dismiss=lambda d: (dialog_texts(d, "restore BAD html"), shot(d, "s4_bad_html")))
        shot(driver, "s4_after_bad")
        dialog_texts(driver, "after bad html dismiss")
        room("s4 after bad html")

        step("Settings -> Restore (2)", saf_steps.rescroll_settings_to, driver, "Restore")
        step("tap Restore (2)", saf_steps.tap_settings_action, driver, "Restore")
        step("SAF pick empty json", saf_steps.saf_pick_file, driver, "ch007_probe_empty.json",
             before_dismiss=lambda d: (dialog_texts(d, "restore EMPTY json"), shot(d, "s4_empty_json")))
        shot(driver, "s4_after_empty")
        dialog_texts(driver, "after empty json dismiss")
        after = room("s4 after empty json")
        log(f"=== SEED4 room unchanged: {before == after}")
    finally:
        driver_factory.quit_driver(driver)
        adb.shell(f'rm -f "{DL}/ch007_probe_bad.html" "{DL}/ch007_probe_empty.json"')
