"""Тесты области `sync` (AT-BUG-073 закрытие test_debt — мок GitLab Snippet API,
сидер `sync_tombstones`, `id` фильтр-профиля из `seed_filter_profiles`).

Инфраструктура: `framework/data/gitlab_snippet_mock.py` (мок `/api/v4/snippets`,
интегрирован в СУЩЕСТВУЮЩИЙ mitm/replay-механизм — `SyncRepository.kt` бьёт по
нему через голый `OkHttpClient` на ТОТ ЖЕ device-wide прокси, что уже
перехватывает WebView и `DownloadRepository`, см. модульный докстринг
`gitlab_snippet_mock.py`), `conftest.py::sync_replay` (ДИНАМИЧЕСКИЙ аналог
`replay` — содержимое мока строится ВНУТРИ теста, зависит от реально
засеянного локального `timestamp`, не может быть статичным indirect-параметром
`@pytest.mark.parametrize`), `seed_db.seed_sync_tombstones`/`read_sync_tombstones`
(прямой сидинг/чтение таблицы надгробий, минуя UI).

Доказано ЭТИМ инкрементом (доказательство пригодности минимум одним
потребителем — критерий готовности AT-BUG-073):
  - GitLab Snippet API мок (GET raw + PUT update) — ВСЕ три теста ниже.
  - Сидер/чтение `sync_tombstones` — TC-211 (прямой сидинг Given + чтение Then).

НЕ доказано этим инкрементом (остаток — см. `bugs/AT-BUG-073.md` «Обсуждение»):
  - `seed_filter_profiles` возвращает `id` (код готов, TC-212/213 не
    реализованы — нет потребителя).
  - Перехват исходящего тела запроса публикации (не реализовано вовсе).

Настройка синхронизации — через РЕАЛЬНЫЙ UI (`SettingsScreen.set_sync_config`/
`settings_steps.configure_sync`), не прямой сидинг SharedPreferences: три поля
секции Sync пишут в prefs НЕМЕДЛЕННО на каждый `onValueChange`
(`SettingsViewModel.setSyncInstanceUrl/setSyncToken/setSyncSnippetId`), отдельной
кнопки «Save» нет — UI-путь дешевле и ближе к реальному пользовательскому вводу,
чем сборка `shared_prefs/ao3_settings.xml` руками."""
from __future__ import annotations

import json
import time
from pathlib import Path

import allure
import pytest

from framework.config import settings
from framework.data import gitlab_snippet_mock as gsm
from framework.data import recording_builder as rb
from framework.data import seed_db
from framework.data import works as W
from framework.data.works import Work
from framework.steps import app_steps, browser_steps, rating_steps, settings_steps

# Снипет уже "существует" (сценарий первого создания — вне области этого
# инкремента, см. критерий готовности AT-BUG-073 п.1 «минимум GET/POST/PATCH» —
# GET/PUT покрыты, POST-create код готов в `gitlab_snippet_mock.make_snippet_
# create_flow`, но ни один из выбранных ниже кейсов его не потребляет).
_SNIPPET_ID = "424242"
_TOKEN = "glpat-test-token"

# ao3_id 900000207/208 — синтетический диапазон по конвенции works.py (номер
# TC-кейса, тот же приём, что `WORD_COUNT_MIN/MAX_BOUNDARY` (900000271/272) и
# `FILE_ACCESS_PROBE_TARGET` (900000103)) — сверено НЕ пересекающимся ни с
# одним зарезервированным id (`grep -n 'Work("900000' framework/` перед
# началом работы).
_WORK_207 = Work("900000207", "TC-207 LWW Full Replace Work", "seed_author_sync_207",
                 "Fandom Sync207", 1000)
_WORK_208 = Work("900000208", "TC-208 LWW Tie Work", "seed_author_sync_208",
                 "Fandom Sync208", 1000)


def _write_snippet_mock(tmp_path: Path, name: str, remote_content: str,
                        extra_flows: list | None = None) -> Path:
    """Собирает `.mitm` (GET raw + PUT update, snippet_id=`_SNIPPET_ID`),
    опционально сливая с `extra_flows` (например, уже существующая WebView-
    фикстура листинга — `rb.read_flows(...)`) — один mitmdump-процесс на тест,
    оба класса трафика (WebView-навигация И GitLab API) обязаны лежать в ОДНОМ
    `.mitm`-файле."""
    flows = list(extra_flows or []) + [
        gsm.make_snippet_get_flow(_SNIPPET_ID, remote_content),
        gsm.make_snippet_update_flow(_SNIPPET_ID),
    ]
    path = tmp_path / name
    rb.write_flows(path, flows)
    return path


@pytest.fixture()
def sync_lww_work_replace_seeded(tmp_path):
    """TC-207: локальная работа W_207 (LIKE / "local note" / ["localtag"], T1,
    реально существующий на устройстве downloadPath). Удалённый снимок несёт
    более свежую версию (T2=T1+10000 > T1): SAVE / "remote note" / ["remotetag"],
    БЕЗ downloadPath (протокол никогда его не публикует, см. `LibraryJson.
    workToJson(includeDownloadFile=false)` в `syncNow`)."""
    app_steps.clean_state()
    local_html = settings.DATA_DIR / "fixtures" / "downloaded_work.html"
    device_paths = seed_db.seed_with_comment_and_download([
        (_WORK_207, "LIKE", "local note", json.dumps(["localtag"]), local_html),
    ])
    t1 = seed_db.read_work_ratings_full()[_WORK_207.ao3_id]["timestamp"]
    remote = gsm.remote_snapshot_content(works=[
        gsm.work_json(
            _WORK_207.ao3_id, t1 + 10_000, rating="SAVE", comment="remote note",
            fandom=_WORK_207.fandom, word_count=_WORK_207.word_count, tags=["remotetag"],
        ),
    ])
    flows_path = _write_snippet_mock(tmp_path, "tc207.mitm", remote)
    return _WORK_207, device_paths[_WORK_207.ao3_id], flows_path


@pytest.fixture()
def sync_lww_work_tie_seeded(tmp_path):
    """TC-208: локальная работа W_208 (LIKE, T) — удалённый снимок несёт СТРОКУ
    С РОВНО ТЕМ ЖЕ `timestamp` (T), но другим рейтингом (DISLIKE). `remoteTs <=
    localTs` — сравнение НЕстрогое (`SyncRepository.kt:155`), поэтому равенство
    обязано ОТБРОСИТЬ удалённую версию (граница TC-208, парная к TC-207)."""
    app_steps.clean_state()
    seed_db.seed([(_WORK_208, "LIKE")])
    t = seed_db.read_work_ratings_full()[_WORK_208.ao3_id]["timestamp"]
    remote = gsm.remote_snapshot_content(works=[
        gsm.work_json(
            _WORK_208.ao3_id, t, rating="DISLIKE",
            fandom=_WORK_208.fandom, word_count=_WORK_208.word_count,
        ),
    ])
    flows_path = _write_snippet_mock(tmp_path, "tc208.mitm", remote)
    return _WORK_208, flows_path


@pytest.fixture()
def sync_tombstone_undelete_seeded(tmp_path):
    """TC-211: работа Z (переиспользует `W.LOVED` — идентичность блёрба листинга,
    НЕ идентичность продукта: только `ao3_id`/`title`/`fandom` берутся из блёрба
    `listing_basic.mitm`, само значение рейтинга не связано с другими фикстурами
    этого имени в остальных тестах — каждый прогон стартует с `pm clear`) несёт
    ТОЛЬКО надгробие `sync_tombstones` (deletedAt=T_delete) — ПРЯМОЙ сидинг,
    минуя UI (`seed_db.seed_sync_tombstones`), таблица `work_ratings` для Z
    ПУСТА (симулирует «работа была удалена ранее»). Удалённый снимок несёт
    СТАРУЮ строку Z (`timestamp=T_row < T_delete`) — без переоценки надгробие
    победило бы её (TC-210), здесь Given готовит именно ЭТОТ контраст.

    `.mitm` СЛИВАЕТ существующую `listing_basic.mitm` (нужна для тапа Rate-
    кнопки блёрба Z) с GitLab-моком — один mitmdump-процесс на тест."""
    app_steps.clean_state()
    t_delete = int(time.time() * 1000)
    seed_db.seed_sync_tombstones([
        (seed_db.SYNC_TOMBSTONE_KIND_WORK, W.LOVED.ao3_id, t_delete),
    ])
    t_row = t_delete - 60_000
    remote = gsm.remote_snapshot_content(works=[
        gsm.work_json(
            W.LOVED.ao3_id, t_row, rating="DISLIKE",
            fandom=W.LOVED.fandom, word_count=W.LOVED.word_count,
        ),
    ])
    listing_flows = rb.read_flows(settings.RECORDINGS_DIR / rb.LISTING_BASIC_FILENAME)
    flows_path = _write_snippet_mock(tmp_path, "tc211.mitm", remote, extra_flows=listing_flows)
    return W.LOVED, flows_path


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-207")
@allure.title("LWW-слияние: более свежая удалённая версия работы замещает локальную целиком, кроме downloadPath")
def test_sync_lww_work_remote_wins(sync_lww_work_replace_seeded, driver, sync_replay):
    work, local_download_path, flows_path = sync_lww_work_replace_seeded

    # Given синхронизация настроена (instance по умолчанию, token, snippet_id
    # существующего снимка) — remote-снимок (мок) с более свежей версией работы
    # уже поднят ПЕРЕД настройкой UI
    sync_replay(flows_path)
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Settings")
    settings_steps.configure_sync(driver, token=_TOKEN, snippet_id=_SNIPPET_ID)

    # When пользователь запускает «Sync now»
    settings_steps.tap_sync_now(driver)

    # Then диалог подтверждает ровно одно обновление работы
    settings_steps.assert_sync_result_dialog(driver, "Sync complete")
    settings_steps.assert_sync_result_dialog_contains(driver, "1 works updated")
    settings_steps.dismiss_sync_result_dialog(driver)

    # And локальная строка X теперь показывает удалённую версию целиком (rating/
    # comment/tags), КРОМЕ downloadPath — тот остаётся локальным (никогда не
    # публикуется, `LibraryJson.workToJson(includeDownloadFile=false)`)
    result = seed_db.read_work_ratings_full()[work.ao3_id]
    assert result["rating"] == "SAVE", f"rating не заменился удалённой версией: {result}"
    assert result["comment"] == "remote note", f"comment не заменился удалённой версией: {result}"
    assert result["tags"] == ["remotetag"], f"tags не заменились удалённой версией: {result}"
    assert result["downloadPath"] == local_download_path, (
        f"downloadPath изменился слиянием (не должен — device-local поле): "
        f"ожидали {local_download_path!r}, реально {result['downloadPath']!r}"
    )


@pytest.mark.p2
@pytest.mark.replay
@allure.id("TC-208")
@allure.title("LWW-слияние: граница равенства timestamp — при РОВНО равном timestamp побеждает локальная версия")
def test_sync_lww_work_tie_keeps_local(sync_lww_work_tie_seeded, driver, sync_replay):
    work, flows_path = sync_lww_work_tie_seeded

    # Given синхронизация настроена, remote-снимок несёт СТРОКУ с РОВНО тем же
    # timestamp, что и локальная (но другим рейтингом)
    sync_replay(flows_path)
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Settings")
    settings_steps.configure_sync(driver, token=_TOKEN, snippet_id=_SNIPPET_ID)

    # When пользователь запускает «Sync now»
    settings_steps.tap_sync_now(driver)
    settings_steps.assert_sync_result_dialog(driver, "Sync complete")
    settings_steps.dismiss_sync_result_dialog(driver)

    # Then локальная строка X остаётся rating=LIKE — удалённая версия ОТБРОШЕНА
    # (код: `remoteTs <= localTs` → `continue`, сравнение НЕстрогое)
    result = seed_db.read_work_ratings_full()[work.ao3_id]
    assert result["rating"] == "LIKE", (
        f"локальный rating изменился при РАВНОМ timestamp (ожидали отбрасывание "
        f"удалённой версии): {result}"
    )


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-211")
@allure.title("Повторная оценка ранее удалённой работы снимает надгробие и защищает от повторного удаления синком")
def test_sync_rerate_clears_tombstone(sync_tombstone_undelete_seeded, driver, sync_replay):
    work, flows_path = sync_tombstone_undelete_seeded

    # Given синхронизация настроена; работа Z несёт ТОЛЬКО надгробие (прямой
    # сидинг, минуя UI); удалённый снимок несёт более старую строку Z
    sync_replay(flows_path)
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Settings")
    settings_steps.configure_sync(driver, token=_TOKEN, snippet_id=_SNIPPET_ID)

    # When пользователь заново оценивает работу Z из листинга (любой рейтинг)
    app_steps.open_tab(driver, "Browse")
    browser_steps.open_listing(driver, rb.LISTING_BASIC_URL)
    browser_steps.tap_rate_button(driver, work.ao3_id)
    rating_steps.rate_via_listing_overlay(driver, "LIKE")
    rating_steps.dismiss_rating_overlay(driver)
    rating_steps.wait_for_rating(work.ao3_id, "LIKE")

    # Then надгробие Z ФИЗИЧЕСКИ снято (различающий оракул — прямое чтение
    # sync_tombstones, ДО запуска Sync now: без этого Then ниже прошёл бы даже
    # при сломанном снятии, если бы local timestamp просто оказался новее)
    settings_steps.assert_no_sync_tombstone(seed_db.SYNC_TOMBSTONE_KIND_WORK, work.ao3_id)

    # When пользователь запускает «Sync now» с ТЕМ ЖЕ старым удалённым снимком Z
    app_steps.open_tab(driver, "Settings")
    settings_steps.tap_sync_now(driver)
    settings_steps.assert_sync_result_dialog(driver, "Sync complete")
    settings_steps.dismiss_sync_result_dialog(driver)

    # Then работа Z присутствует (СИНК НЕ удалил её повторно — в отличие от
    # TC-210, где БЕЗ переоценки надгробие победило бы более старую входящую
    # строку и Z осталась бы отсутствующей)
    after = seed_db.read_work_ratings_full()
    assert work.ao3_id in after, (
        f"работа {work.ao3_id} исчезла после Sync now — надгробие сработало "
        f"повторно, хотя было снято переоценкой"
    )
    assert after[work.ao3_id]["rating"] == "LIKE"

    # And надгробие Z по-прежнему отсутствует ПОСЛЕ синка
    settings_steps.assert_no_sync_tombstone(seed_db.SYNC_TOMBSTONE_KIND_WORK, work.ao3_id)
