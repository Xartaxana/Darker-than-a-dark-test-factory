"""AD HOC верификационный прогон BUG-078 (fix-verifier, mode=verify D1).

ВРЕМЕННЫЙ файл — не постоянный тест-кейс конвейера, удаляется после
верификации. Не привязан ни к одному TC (test_cases: [] в BUG-078.md,
carve-out fixVerifier §4б — фикс без замка, next_rules заведёт test-designer
постоянный кейс отдельно).

Цель: живой прогон "Send to my other devices" (app-under-test fdd3f72):
  - test_send_sets_request_and_handled_without_moving_timestamp — отправительская
    сторона (UI-действие, sendRequestedAt/sendHandledAt, timestamp неподвижен).
  - test_receiving_device_downloads_and_shows_snackbar — приёмная сторона,
    ветка "remote row wins" (SyncRepository.kt:181-198): ОДИН эмулятор играет
    роль "устройства B", "устройство A" полностью смоделировано HTTP-моком
    GitLab-снипета (framework/data/gitlab_snippet_mock.py, та же инфраструктура
    AT-BUG-073/TC-207..231) — снипет уже несёт чужую работу с проставленным
    sendRequestedAt, реальный SyncRepository.syncNow() мержит и качает файл
    через РЕАЛЬНЫЙ DownloadRepository.downloadWork на мокнутый
    (work_with_download.mitm) AO3-эндпойнт. Это НЕ суррогат: код приложения
    исполняется целиком (merge + fulfillSendRequests + скачивание + снекбар),
    только СЕТЬ замокана — тот же уровень истинности, что у остальных
    зелёных sync-тестов (TC-207 и др.), которые тоже никогда не поднимают
    второй физический эмулятор.
  - test_local_row_wins_but_send_request_still_merges — вторая, более
    рискованная ветка (SyncRepository.kt:168-179 `withNewerSendRequest`
    внутри "local wins"): локальная строка ПОБЕЖДАЕТ по timestamp (остаётся
    LIKE, не перезаписывается удалённым DISLIKE), но sendRequestedAt всё
    равно обязан замержиться полевым способом — иначе запрос на отправку,
    пришедший ПОЗЖЕ последней локальной правки, тихо терялся бы.

НЕ ПОКРЫТО этими тремя трайлами (критик-вход приёмки BUG-078, 2026-08-19/20,
блокер Б4) — достижимо ОДНИМ устройством, но не исполнено:
  - Сохранение sendHandledAt при remote-wins merge, когда lRow != null
    (SyncRepository.kt:191) — трайл 2 идёт по чистому устройству (lRow==null),
    это путь ВСТАВКИ, не путь СОХРАНЕНИЯ уже обработанного запроса.
  - Граница "Send again" на устройстве, которое уже отработало предыдущий
    запрос (sendHandledAt >= requestedAt, SyncRepository.kt:331).
  - Ретрай неудачной закачки на следующем проходе (SyncRepository.kt:342-346).
  - Обе ветки DownloadRepository.deleteDownload (:170-174) — только прочитаны,
    не прогнаны: hasOtherState=true -> scoped updateDownloadPath (sendHandledAt
    не тронут); hasOtherState=false -> deleteWorkRating целиком (sendHandledAt
    исчезает вместе со строкой, ставится тумбстон, работа удалится на ВСЕХ
    устройствах следующим синком) — другой механизм, тот же итоговый эффект
    "старый запрос не докачивает".
test-designer/test-automator: при заведении постоянных TC по образцу ниже —
покрыть и эти пункты, не только три исполненных ветки.
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from framework.config import settings
from framework.data import gitlab_snippet_mock as gsm
from framework.data import recording_builder as rb
from framework.data import seed_db
from framework.data import works as W
from framework.screens.base_screen import BaseScreen
from framework.screens.library_screen import LibraryScreen
from framework.steps import app_steps, library_steps, settings_steps

_SNIPPET_ID = "780078"
_TOKEN = "glpat-test-token-bug078"


def _pull_send_fields(tmp_dir: Path, ao3_id: str):
    tmp_dir.mkdir(exist_ok=True, parents=True)
    db = seed_db._pull_baseline(tmp_dir)
    con = sqlite3.connect(db)
    row = con.execute(
        "SELECT sendRequestedAt, sendHandledAt, timestamp, rating, downloadPath "
        "FROM work_ratings WHERE ao3Id=?",
        (ao3_id,),
    ).fetchone()
    con.close()
    return row


@pytest.fixture()
def loved_liked_seeded():
    """Сидинг ДО инстанцирования `driver` — `driver` фикстура запускает
    приложение при создании Appium-сессии; `seed_db.seed()` завершается
    `force_stop()` (см. `ensure_db_initialized`), поэтому сидинг обязан
    случиться РАНЬШЕ запуска, иначе `driver` стартует приложение, а
    следующий `force_stop()` внутри `seed()` его же и убивает — тот же
    порядок, что `sync_lww_work_replace_seeded` и другие фикстуры
    `test_sync.py` (сидирующая фикстура ПЕРЕД `driver` в сигнатуре теста)."""
    seed_db.seed([(W.LOVED, "LIKE")])
    return seed_db.read_work_ratings_full()[W.LOVED.ao3_id]


@pytest.mark.p1
def test_send_sets_request_and_handled_without_moving_timestamp(loved_liked_seeded, driver):
    before = loved_liked_seeded
    assert before["timestamp"] is not None  # sanity: строка реально засеяна

    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Library")
    library_steps.open_library_tab_for(driver, "LIKE")

    lib = LibraryScreen(driver)
    lib.long_press_work(W.LOVED.title)
    assert lib.is_present(lib.by_text("Send to my other devices"), timeout=8), (
        "пункт «Send to my other devices» не найден в long-press меню Library"
    )

    # When пользователь нажимает «Send to my other devices»
    lib.tap(lib.by_text("Send to my other devices"))

    # Then локальная строка несёт sendRequestedAt == sendHandledAt (недавние),
    # а timestamp рейтинга НЕ сдвинулся
    from framework.core.waits import wait_for

    tmp = Path(settings.RECORDINGS_DIR).parent / "_bug078_scratch_1"

    def _sent() -> bool:
        row = _pull_send_fields(tmp, W.LOVED.ao3_id)
        return row is not None and row[0] is not None

    wait_for(_sent, timeout=10, message="sendRequestedAt не проставился после тапа «Send to my other devices»")
    send_requested_at, send_handled_at, ts_after, _rating, _dp = _pull_send_fields(tmp, W.LOVED.ao3_id)

    print(f"BUG078_SEND_WITNESS sendRequestedAt={send_requested_at} sendHandledAt={send_handled_at} "
          f"timestamp_before={before['timestamp']} timestamp_after={ts_after}")

    assert send_requested_at is not None, "sendRequestedAt пуст после отправки"
    assert send_handled_at == send_requested_at, (
        f"sendHandledAt ({send_handled_at}) != sendRequestedAt ({send_requested_at}) — "
        f"отправитель должен пометить запрос обработанным для себя же"
    )
    assert ts_after == before["timestamp"], (
        f"timestamp сдвинулся отправкой ({before['timestamp']} -> {ts_after}) — "
        f"должен остаться неподвижным (send не является правкой рейтинга)"
    )


@pytest.fixture()
def cleaned_state():
    """`clean_state()` (`adb.clear_app_data()`) ДО инстанцирования `driver` —
    та же причина порядка, что у `loved_liked_seeded` выше: `driver` уже
    запускает приложение при создании Appium-сессии, `clear_app_data` ПОСЛЕ
    этого убил бы уже запущенный процесс."""
    app_steps.clean_state()


@pytest.mark.p1
@pytest.mark.replay
@pytest.mark.produces_download
def test_receiving_device_downloads_and_shows_snackbar(cleaned_state, driver, sync_replay, tmp_path):
    work = W.LOVED

    now = int(time.time() * 1000)
    remote_work = gsm.work_json(
        work.ao3_id, now, rating="LIKE",
        fandom=work.fandom, word_count=work.word_count,
        title=work.title, author=work.author, url=work.url,
    )
    # "Устройство A" уже отправило запрос — sendRequestedAt несёт мок-снимок
    remote_work["sendRequestedAt"] = now
    remote = gsm.remote_snapshot_content(works=[remote_work])

    download_flows = rb.read_flows(settings.RECORDINGS_DIR / rb.WORK_WITH_DOWNLOAD_FILENAME)
    flows = list(download_flows) + [
        gsm.make_snippet_get_flow(_SNIPPET_ID, remote),
        gsm.make_snippet_update_flow(_SNIPPET_ID),
    ]
    flows_path = tmp_path / "bug078_receive.mitm"
    rb.write_flows(flows_path, flows)

    sync_replay(flows_path)
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Settings")
    settings_steps.configure_sync(driver, token=_TOKEN, snippet_id=_SNIPPET_ID)

    # When «устройство B» синхронизируется и видит standing-запрос
    settings_steps.tap_sync_now(driver)

    # Then диалог результата синка подтверждает обновление
    settings_steps.assert_sync_result_dialog(driver, "Sync complete")
    settings_steps.assert_sync_result_dialog_contains(driver, "1 works updated")
    settings_steps.dismiss_sync_result_dialog(driver)

    # And снекбар "Downloaded N work(s) sent from another device" появляется
    screen = BaseScreen(driver)
    snackbar_seen = screen.is_present(screen.by_text_contains("sent from another device"), timeout=15)
    print(f"BUG078_RECEIVE_WITNESS snackbar_seen={snackbar_seen}")
    assert snackbar_seen, "снекбар прибытия («…sent from another device») не появился после синка"

    # And файл реально докачан (downloadPath заполнен) через РЕАЛЬНЫЙ DownloadRepository
    result = seed_db.read_work_ratings_full()[work.ao3_id]
    print(f"BUG078_RECEIVE_WITNESS downloadPath={result['downloadPath']!r}")
    assert result["downloadPath"], f"работа не докачалась после приёма запроса: {result}"

    tmp = tmp_path / "pulled"
    row = _pull_send_fields(tmp, work.ao3_id)
    print(f"BUG078_RECEIVE_WITNESS sendRequestedAt={row[0]} sendHandledAt={row[1]}")
    assert row[1] is not None and row[1] >= row[0], (
        f"sendHandledAt ({row[1]}) не проставлен/не догнал sendRequestedAt ({row[0]}) после скачивания"
    )


@pytest.fixture()
def loved_liked_seeded_for_merge():
    """Как `loved_liked_seeded`, но ДОПОЛНИТЕЛЬНО чистит состояние приложения
    ПЕРЕД сидингом (`app_steps.clean_state()`) — тот же порядок, что
    `sync_lww_work_replace_seeded`/`test_sync.py` (`clean_state()` первой
    строкой фикстуры). Нужно ИМЕННО здесь: предыдущий тест этого файла уже
    настроил sync (token/snippet_id) через UI — SharedPreferences НЕ чистятся
    `seed_db.seed()` (тот трогает только Room-файл), поэтому без `clean_state()`
    `isConfigured` был бы true уже к моменту первого `onResume`, и
    `MainActivity.kt:171-174` (`repeatOnLifecycle(RESUMED) { syncIfNeeded() }`)
    запустил бы автосинк ДО того, как `sync_replay(flows_path)` в теле теста
    поднимет прокси — тот автосинк ушёл бы live на реальный gitlab.com с
    протухшим тестовым токеном (реальный HTTP 401), что и наблюдалось живым
    прогоном (диалог «Sync failed... HTTP 401» дважды, «Last synced» не
    сдвигался — систематически, не транзиент)."""
    app_steps.clean_state()
    seed_db.seed([(W.LOVED, "LIKE")])
    return seed_db.read_work_ratings_full()[W.LOVED.ao3_id]


@pytest.mark.p1
@pytest.mark.replay
@pytest.mark.produces_download
def test_local_row_wins_but_send_request_still_merges(loved_liked_seeded_for_merge, driver, sync_replay, tmp_path):
    """SyncRepository.kt:168-179: `remoteTs <= localTs` -> ветка "local wins"
    берёт `lRow` как базу, НО всё равно прогоняет `withNewerSendRequest(lRow, rRow)`
    — sendRequestedAt обязан замержиться, даже когда remote проигрывает
    сравнение timestamp целиком (иначе запрос на отправку, пришедший ПОЗЖЕ
    последней локальной правки, тихо терялся бы)."""
    work = W.LOVED
    local_ts = loved_liked_seeded_for_merge["timestamp"]

    # Remote: СТАРШЕ по timestamp (проиграет сравнение строки), другой rating
    # (DISLIKE, чтобы отличить от локального LIKE — если бы remote вдруг
    # победил, это было бы видно), но НОВЫЙ sendRequestedAt.
    remote_work = gsm.work_json(
        work.ao3_id, local_ts - 60_000, rating="DISLIKE",
        fandom=work.fandom, word_count=work.word_count,
        title=work.title, author=work.author, url=work.url,
    )
    remote_work["sendRequestedAt"] = local_ts + 30_000
    remote = gsm.remote_snapshot_content(works=[remote_work])

    download_flows = rb.read_flows(settings.RECORDINGS_DIR / rb.WORK_WITH_DOWNLOAD_FILENAME)
    flows = list(download_flows) + [
        gsm.make_snippet_get_flow(_SNIPPET_ID, remote),
        gsm.make_snippet_update_flow(_SNIPPET_ID),
    ]
    flows_path = tmp_path / "bug078_local_wins.mitm"
    rb.write_flows(flows_path, flows)

    sync_replay(flows_path)
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Settings")
    settings_steps.configure_sync(driver, token=_TOKEN, snippet_id=_SNIPPET_ID)
    settings_steps.tap_sync_now(driver)
    settings_steps.assert_sync_result_dialog(driver, "Sync complete")
    settings_steps.dismiss_sync_result_dialog(driver)

    screen = BaseScreen(driver)
    snackbar_seen = screen.is_present(screen.by_text_contains("sent from another device"), timeout=15)
    print(f"BUG078_LOCALWINS_WITNESS snackbar_seen={snackbar_seen}")
    assert snackbar_seen, "снекбар прибытия не появился, хотя local-wins ветка обязана замержить sendRequestedAt"

    tmp = tmp_path / "pulled"
    row = _pull_send_fields(tmp, work.ao3_id)
    send_requested_at, send_handled_at, ts_after, rating_after, download_path_after = row
    print(f"BUG078_LOCALWINS_WITNESS sendRequestedAt={send_requested_at} sendHandledAt={send_handled_at} "
          f"rating={rating_after} downloadPath={download_path_after!r}")

    assert rating_after == "LIKE", (
        f"rating сменился на удалённый ({rating_after}) — local должен был победить сравнение timestamp"
    )
    assert send_requested_at == local_ts + 30_000, (
        f"sendRequestedAt НЕ замержился полевым способом при local-wins ({send_requested_at})"
    )
    assert send_handled_at is not None and send_handled_at >= send_requested_at, (
        f"sendHandledAt ({send_handled_at}) не догнал sendRequestedAt ({send_requested_at}) после скачивания"
    )
    assert download_path_after, "работа не докачалась, хотя sendRequestedAt замержился"
