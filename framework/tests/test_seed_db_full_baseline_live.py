"""Живая device-верификация новых примитивов AT-BUG-046 —
`seed_db.seed_with_comment_and_download` (baseline A/C, CH-008) и
`seed_db.read_work_ratings_full()` — на реальном устройстве, без Appium-сессии
(чистое чтение/запись Room через run-as, тот же контракт, что
`downloaded_work_seeded`/`library_downloaded_only_seeded` в conftest.py, но
без driver/UI — сравнение полей идёт напрямую по словарю).

НЕ автоматизация TC-151/152/155/156 (те кейсы ведут пользователя через UI и
проверяют поведение приложения) — эта проба доказывает только сам механизм
сидинга/чтения фреймворка, дешёвый device-регресс на будущее (аналог
`test_seed_db_schema_race_unit.py`, но здесь необходим реальный adb/Room,
поэтому не device-free)."""
from __future__ import annotations

import json

import allure
import pytest

from framework.config import settings
from framework.data import seed_db
from framework.steps import app_steps
from framework.data.works import Work

_FIXTURE_HTML = settings.DATA_DIR / "fixtures" / "downloaded_work.html"

_BASELINE_A_WORK = Work("900046011", "AT-BUG-046 Live Baseline A", "seed_author_046_live_a",
                        "Fandom 046 Live A", 4200)
_BASELINE_C_WORK = Work("900046012", "AT-BUG-046 Live Baseline C", "seed_author_046_live_c",
                        "Fandom 046 Live C", 900)


@pytest.mark.p2
@allure.id("AT-BUG-046-live-baseline-a-and-c-seed-and-read-back")
@allure.title("Живой прогон: seed_with_comment_and_download сеет baseline A и C, read_work_ratings_full читает назад полностью")
def test_seed_with_comment_and_download_baseline_a_and_c_round_trip():
    # Given чистое состояние приложения
    app_steps.clean_state()

    tags_json = json.dumps(["tagA", "tagB"])
    rows = [
        # baseline A: rating не null, comment+tags+downloadPath одновременно
        (_BASELINE_A_WORK, "SAVE", "note A live", tags_json, _FIXTURE_HTML),
        # baseline C: rating=None + downloadPath (comment/tags опциональны, здесь непустой comment)
        (_BASELINE_C_WORK, None, "download-only live note", None, _FIXTURE_HTML),
    ]

    # When обе строки засеяны ОДНОЙ функцией (новый примитив AT-BUG-046)
    device_paths = seed_db.seed_with_comment_and_download(rows)

    # Then оба ao3Id получили непустой путь на устройстве
    assert device_paths[_BASELINE_A_WORK.ao3_id], "seed_with_comment_and_download не вернул путь baseline A"
    assert device_paths[_BASELINE_C_WORK.ao3_id], "seed_with_comment_and_download не вернул путь baseline C"

    # And read_work_ratings_full() читает НАЗАД ПОЛНЫЙ набор полей, включая
    # title/author/downloadPath (AT-BUG-046 п.1) — композиция comment+tags+
    # downloadPath (A) и rating=null+downloadPath (C) не разрушила друг друга
    full = seed_db.read_work_ratings_full()

    row_a = full[_BASELINE_A_WORK.ao3_id]
    assert row_a["rating"] == "SAVE"
    assert row_a["comment"] == "note A live"
    assert row_a["tags"] == ["tagA", "tagB"]
    assert row_a["downloadPath"] == device_paths[_BASELINE_A_WORK.ao3_id]
    assert row_a["title"] == _BASELINE_A_WORK.title
    assert row_a["author"] == _BASELINE_A_WORK.author
    assert row_a["fandom"] == _BASELINE_A_WORK.fandom
    assert row_a["word_count"] == _BASELINE_A_WORK.word_count

    row_c = full[_BASELINE_C_WORK.ao3_id]
    assert row_c["rating"] is None
    assert row_c["comment"] == "download-only live note"
    assert row_c["downloadPath"] == device_paths[_BASELINE_C_WORK.ao3_id]
    assert row_c["title"] == _BASELINE_C_WORK.title

    # And read_work_ratings() (старая функция, TC-021) НЕ несёт новые ключи —
    # сигнатура не расширена (проверка того, что старый потребитель не сломан)
    legacy = seed_db.read_work_ratings()
    assert set(legacy[_BASELINE_A_WORK.ao3_id]) == {"rating", "comment", "tags", "fandom", "word_count"}
