"""Тесты области `sync` (AT-BUG-073 закрытие test_debt — мок GitLab Snippet API,
сидер `sync_tombstones`, `id` фильтр-профиля из `seed_filter_profiles`, перехват
исходящего тела публикации).

Инфраструктура: `framework/data/gitlab_snippet_mock.py` (мок `/api/v4/snippets`,
интегрирован в СУЩЕСТВУЮЩИЙ mitm/replay-механизм — `SyncRepository.kt` бьёт по
нему через голый `OkHttpClient` на ТОТ ЖЕ device-wide прокси, что уже
перехватывает WebView и `DownloadRepository`, см. модульный докстринг
`gitlab_snippet_mock.py`), `conftest.py::sync_replay` (ДИНАМИЧЕСКИЙ аналог
`replay` — содержимое мока строится ВНУТРИ теста, зависит от реально
засеянного локального `timestamp`, не может быть статичным indirect-параметром
`@pytest.mark.parametrize`), `seed_db.seed_sync_tombstones`/`read_sync_tombstones`
(прямой сидинг/чтение таблицы надгробий, минуя UI), `framework/core/
capture_addon.py` + `mitm.read_captured_requests` (перехват тела ИСХОДЯЩЕГО
POST/PUT-запроса публикации).

Доказано ЭТИМ инкрементом (доказательство пригодности минимум одним
потребителем каждого из 4 пробелов — критерий готовности AT-BUG-073):
  - GitLab Snippet API мок (GET raw + PUT update) — ВСЕ шесть тестов ниже.
  - Сидер/чтение `sync_tombstones` — TC-211 (прямой сидинг Given + чтение Then).
  - `seed_filter_profiles` возвращает `id` — TC-213 (`id` профиля подставлен в
    надгробие мок-снимка, чтобы синк адресовал ТУ ЖЕ локальную строку).
  - Перехват исходящего тела публикации — TC-215 (`capture_addon.py` снимает
    PUT-тело, тест разбирает GitLab-конверт -> вложенный `content` -> JSON
    снимка библиотеки).

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
from framework.core import mitm
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
_WORK_215 = Work("900000215", "TC-215 Publish Full State Work", "seed_author_sync_215",
                 "Fandom Sync215", 1000)
_WORK_224 = Work("900000224", "TC-224 Sync Failure Baseline Work", "seed_author_sync_224",
                 "Fandom Sync224", 1000)


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


@pytest.fixture()
def sync_tombstone_removes_profile_seeded(tmp_path):
    """TC-213: локальный фильтр-профиль Q засеян через `app_steps.seed_filter_
    profiles` — сидер возвращает СГЕНЕРИРОВАННЫЙ `id` (AT-BUG-073 критерий
    готовности п.3, единственный потребитель этого возврата во всём
    фреймворке на момент написания), который подставляется в `id` надгробия
    удалённого мок-снимка: БЕЗ совпадения `id` синк не нашёл бы, какую
    локальную строку удалять (`SyncRepository.kt:181` матчит по `id` в
    объединении ключей local/remote карт).

    `t_delete` берётся ПОСЛЕ вызова `seed_filter_profiles` с запасом (60с) —
    `timestamp` профиля назначается ВНУТРИ сидера в момент вызова (`now =
    int(time.time()*1000)`), так что любое `t`, взятое строго позже с
    запасом, гарантированно больше — не требует читать `timestamp` обратно
    (`read_filter_profiles()` его вообще не отдаёт, см. её докстринг: сверка
    там идёт по (name, queryString), а не по `id`/`timestamp`).

    `.mitm` СЛИВАЕТ `listing_basic.mitm` (нужна для открытия листинга и
    фильтр-панели Browse в Then) с GitLab-моком — тот же приём, что TC-211."""
    app_steps.clean_state()
    name = "TC-213 profile Q"
    [profile_id] = app_steps.seed_filter_profiles([
        (name, "work_search%5Bquery%5D=tc213-query"),
    ])
    t_delete = int(time.time() * 1000) + 60_000
    remote = gsm.remote_snapshot_content(tombstones=[
        gsm.tombstone_json(seed_db.SYNC_TOMBSTONE_KIND_PROFILE, profile_id, t_delete),
    ])
    listing_flows = rb.read_flows(settings.RECORDINGS_DIR / rb.LISTING_BASIC_FILENAME)
    flows_path = _write_snippet_mock(tmp_path, "tc213.mitm", remote, extra_flows=listing_flows)
    return name, flows_path


@pytest.fixture()
def sync_failure_baseline_seeded():
    """TC-224 (поглощает TC-225): baseline — одна оценённая работа X, ОБЩИЙ
    для обоих вариантов сбоя (404 «Snippet not found» / 401 «token rejected»,
    `pytest.mark.parametrize` ниже — «Заметки для автоматизации» кейса
    предписывают ОДИН параметризованный тест, не два раздельных). Полный
    снимок строки `work_ratings` захвачен ЗДЕСЬ, ДО любого сетевого похода —
    второй Then («данные не изменились») сравнивает его с постфактум
    прочитанным тем же `read_work_ratings_full()` (приём тождественен обоим
    вариантам, см. заметки кейса)."""
    app_steps.clean_state()
    seed_db.seed([(_WORK_224, "LIKE")])
    before = seed_db.read_work_ratings_full()[_WORK_224.ao3_id]
    return _WORK_224, before


@pytest.fixture()
def sync_publish_seeded(tmp_path):
    """TC-215: локально есть 1 оценённая работа (`_WORK_215`) и 1 фильтр-профиль
    — удалённый снимок ПУСТ (`remote_snapshot_content()` без аргументов),
    заведомо отличается от локально рассчитанного `outText`
    (`SyncRepository.kt:218 outText != remoteRaw`), поэтому синк ОБЯЗАН
    опубликовать (PUT, снипет уже "существует" — `_SNIPPET_ID` преднастроен,
    сценарий create вне области этого инкремента, см. модульный комментарий
    у `_SNIPPET_ID`)."""
    app_steps.clean_state()
    seed_db.seed([(_WORK_215, "LIKE")])
    app_steps.seed_filter_profiles([
        ("TC-215 profile", "work_search%5Bquery%5D=tc215-query"),
    ])
    remote = gsm.remote_snapshot_content()
    flows_path = _write_snippet_mock(tmp_path, "tc215.mitm", remote)
    return flows_path


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


@pytest.mark.p2
@pytest.mark.replay
@allure.id("TC-213")
@allure.title("Входящее надгробие удаляет фильтр-профиль с обеих поверхностей")
def test_sync_tombstone_removes_filter_profile(sync_tombstone_removes_profile_seeded, driver, sync_replay):
    name, flows_path = sync_tombstone_removes_profile_seeded

    # Given синхронизация настроена; профиль Q сохранён локально (Settings
    # видит его ДО синка — иначе Then «исчез» ничего не доказывал бы)
    sync_replay(flows_path)
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Settings")
    settings_steps.assert_filter_profile_listed(driver, name)
    settings_steps.configure_sync(driver, token=_TOKEN, snippet_id=_SNIPPET_ID)

    # When пользователь запускает «Sync now» (удалённый снимок несёт более
    # свежее надгробие kind="profile" для ТОГО ЖЕ id, что реально получил Q)
    settings_steps.tap_sync_now(driver)
    settings_steps.assert_sync_result_dialog(driver, "Sync complete")
    settings_steps.dismiss_sync_result_dialog(driver)

    # Then профиль Q исчезает из списка Settings
    settings_steps.assert_filter_profile_not_listed(driver, name)

    # And профиль Q исчезает из выпадашки фильтра на листинге Browse (вторая
    # UI-поверхность — тот же инвариант распространения, что TC-042 для
    # УДАЛЕНИЯ ИЗ UI, здесь удаление пришло СИНКОМ, не прямым тапом)
    app_steps.open_tab(driver, "Browse")
    browser_steps.open_listing(driver, rb.LISTING_BASIC_URL)
    browser_steps.open_filter_dropdown(driver)
    browser_steps.assert_filter_not_offered(driver, name)


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-215")
@allure.title("После слияния устройство публикует полное состояние (works + filterProfiles + tombstones) в сниппет")
def test_sync_publish_full_state(sync_publish_seeded, driver, sync_replay, tmp_path):
    flows_path = sync_publish_seeded
    capture_path = tmp_path / "tc215_capture.jsonl"

    # Given локально есть работа + фильтр-профиль, удалённый снимок пуст
    # (заведомо отличается -> публикация обязана произойти); перехват
    # исходящего тела включён на URL-подстроке `/api/v4/snippets` (AT-BUG-073
    # критерий готовности п.4, `capture_addon.py`)
    sync_replay(flows_path, capture_out=capture_path, capture_url_substr="/api/v4/snippets")
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Settings")
    settings_steps.configure_sync(driver, token=_TOKEN, snippet_id=_SNIPPET_ID)

    # When пользователь запускает «Sync now»
    settings_steps.tap_sync_now(driver)
    settings_steps.assert_sync_result_dialog(driver, "Sync complete")
    settings_steps.dismiss_sync_result_dialog(driver)

    # Then перехвачен ХОТЯ БЫ один PUT/POST на /api/v4/snippets (updateSnippet
    # — снипет уже "существовал", createSnippet не вызывается)
    records = mitm.read_captured_requests(capture_path)
    publishes = [r for r in records if r["method"] in ("PUT", "POST")]
    assert publishes, (
        f"ни одного PUT/POST на /api/v4/snippets не перехвачено — "
        f"перехваченные записи: {records}"
    )

    # And тело запроса — GitLab-конверт `updateSnippet` ({"file_name":...,
    # "content": "<JSON снимка библиотеки СТРОКОЙ>"}, SyncRepository.kt:286-294:
    # `body.put("content", content)`, где `content` — СЕРИАЛИЗОВАННЫЙ текст, не
    # вложенный объект) — сначала разбираем внешний конверт, затем `content`
    # ВТОРЫМ проходом `json.loads`. Критик-вход (attempt 4, замечание 7):
    # каждый шаг разбора — диагностируемый `assert` ДО следующего обращения,
    # не голый `TypeError`/`KeyError`, который указывал бы на файл/строку
    # `json.loads`, а не на СУТЬ (что именно в перехваченной записи не так).
    raw_body = publishes[-1]["body"]
    assert raw_body is not None, (
        f"перехваченная публикация без тела (body=None) — "
        f"перехваченная запись целиком: {publishes[-1]}"
    )
    envelope = json.loads(raw_body)
    assert isinstance(envelope, dict) and "content" in envelope, (
        f"GitLab-конверт без поля content (ожидали {{'file_name':..., "
        f"'content':...}}): {envelope}"
    )
    raw_content = envelope["content"]
    assert isinstance(raw_content, str), (
        f"GitLab-конверт несёт content НЕ строкой (ожидали сериализованный "
        f"JSON-текст, SyncRepository.kt:286-294): {raw_content!r}"
    )
    snapshot = json.loads(raw_content)
    assert isinstance(snapshot, dict), f"content распарсился НЕ в объект: {snapshot!r}"

    # And сам снимок несёт version:3 и три массива, все локальные сущности
    # представлены (works/filterProfiles непусты, tombstones — список,
    # присутствует как ключ, даже если в этом сценарии пуст)
    assert snapshot.get("version") == 3, f"снимок без version:3: {snapshot}"
    assert isinstance(snapshot.get("tombstones"), list), (
        f"снимок без списка tombstones (ключ отсутствует/не список): {snapshot}"
    )
    works = snapshot.get("works")
    assert isinstance(works, list), f"снимок без списка works: {snapshot}"
    assert any(w.get("ao3Id") == _WORK_215.ao3_id for w in works), (
        f"опубликованный works не несёт {_WORK_215.ao3_id}: {works}"
    )
    profiles = snapshot.get("filterProfiles")
    assert isinstance(profiles, list), f"снимок без списка filterProfiles: {snapshot}"
    assert any(p.get("name") == "TC-215 profile" for p in profiles), (
        f"опубликованный filterProfiles не несёт «TC-215 profile»: {profiles}"
    )


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-224")
@allure.title("Ручной прогон sync с ошибкой (404/401) показывает дословный диалог, локальные данные не меняются")
@pytest.mark.parametrize(
    "status,expected_dialog_text",
    [
        pytest.param(
            404,
            f"Snippet {_SNIPPET_ID} not found. Check the snippet ID, or clear it to create a new one.",
            id="variant-A-404-snippet-not-found",
        ),
        pytest.param(
            # Вариант B (поглощает TC-225): достаточно ОДНОГО из 401/403 —
            # `SyncRepository.kt:364-366` обрабатывает оба кода идентично,
            # различие только в подставленном `<code>` (см. заметки кейса).
            401,
            "GitLab rejected the token (HTTP 401). It needs the 'api' scope.",
            id="variant-B-401-token-rejected",
        ),
    ],
)
def test_sync_failure_dialog_preserves_local_data(
    status, expected_dialog_text, sync_failure_baseline_seeded, driver, sync_replay, tmp_path,
):
    """TC-224 (поглощает TC-225). `fetchRemote` (`SyncRepository.kt:354-370`)
    бросает `IOException` с ДОСЛОВНЫМ текстом ПЕРЕД любым слиянием/записью в
    Room (`syncNow` вызывает `fetchRemote` первой строкой внутри `runCatching`,
    `SyncRepository.kt:120-125`) — ошибка всплывает как `SyncState.Error`
    (`SettingsScreen.kt:310`) БЕЗ единой мутации локальных данных, что бы ни
    случилось дальше. Точный дословный текст диалога (specific к HTTP-коду,
    не просто заголовок «Sync failed») сам служит позитивным доказательством,
    что мок реально ответил ИМЕННО этим кодом и код приложения дошёл до
    соответствующей ветки `fetchRemote` (класс 3 ложно-зелёных негативов,
    CLAUDE.md) — вакуумный «данные не изменились» здесь недостижим: диалог
    с чужим текстом (или его отсутствие) провалил бы assert раньше, чем
    дошли бы до сверки Room."""
    work, before = sync_failure_baseline_seeded

    # Given Snippet ID (вариант A — «указывает на несуществующий сниппет»,
    # вариант B — «валиден, но токен отклонён») — с точки зрения мока оба
    # различаются ТОЛЬКО кодом ответа GET .../raw (реальный ID нерелевантен,
    # семантику «несуществует»/«валиден, но токен плохой» задаёт код, не сам
    # id — сверено с `fetchRemote`, которая ветвится исключительно по
    # `response.code`); локально уже есть оценённая работа X (общий baseline)
    flows_path = tmp_path / f"tc224_{status}.mitm"
    rb.write_flows(flows_path, [gsm.make_snippet_get_flow(_SNIPPET_ID, "", status=status)])
    sync_replay(flows_path)
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Settings")
    settings_steps.configure_sync(driver, token=_TOKEN, snippet_id=_SNIPPET_ID)

    # When пользователь нажимает «Sync now»
    settings_steps.tap_sync_now(driver)

    # Then показан диалог «Sync failed» с ДОСЛОВНЫМ текстом причины сбоя
    settings_steps.assert_sync_result_dialog(driver, "Sync failed")
    settings_steps.assert_sync_result_dialog_contains(driver, expected_dialog_text)
    settings_steps.dismiss_sync_result_dialog(driver)

    # And локальные данные работы X НЕ изменились — полная строка Room (все
    # 11 полей, включая rating/timestamp) идентична baseline, захваченному ДО
    # запуска sync (инвариант атомарности сбоя относительно Room, общий для
    # обоих вариантов)
    after = seed_db.read_work_ratings_full()[work.ao3_id]
    assert after == before, (
        f"локальные данные работы {work.ao3_id} изменились после сбоя sync "
        f"(HTTP {status}) — ожидали полную неизменность строки: "
        f"before={before}, after={after}"
    )
