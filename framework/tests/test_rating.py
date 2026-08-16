"""Тесты области rating: простановка/снятие рейтинга через встроенную панель
работы (`RatingMenu` в `WorkRatingPanel`, см. app-under-test ui/browser/BottomBar.kt).

Дизайн следует test_library.py: точечные live-сценарии (открытие /works/{id})
неизбежны для панели работы — сеть AO3 не проверяется по содержимому, только
что приложение достигло страницы работы (onWorkPageLoaded) и панель реагирует.

Важная особенность `savePanelRating` (BrowserViewModel.kt): если для `workId` ещё
нет строки в Room, панель СНАЧАЛА скрейпит title/author/fandom/wordCount из живого
DOM страницы работы (`workInfoJs`, селекторы `h2.title.heading` и т.д.) и только
затем сохраняет рейтинг. Наши `ao3_id` из `framework/data/works.py` синтетические
(не существуют на archiveofourown.org) — на реальном сайте такая страница отдаёт
404, скрейп возвращает пустые строки, и запись сохраняется с рейтингом, но БЕЗ
title/author (проверено на живом прогоне: "0 words", без имени). Поэтому здесь
предварительно сеется placeholder-строка (`rating=None`, но с полными
title/author/fandom/wordCount) — тогда `savePanelRating` идёт по ветке
`existing != null` (просто обновляет rating на уже существующей строке, без
обращения к DOM), и тест проверяет именно способность панели проставить/сохранить
рейтинг, а не сетевой скрейп (не являющийся предметом TC-007).
"""
from __future__ import annotations

import allure
import pytest

from framework.data import recording_builder as rb
from framework.data import seed_db
from framework.data import works as W
from framework.steps import app_steps, browser_steps, library_steps, rating_steps


@pytest.mark.p0
@pytest.mark.live
@allure.id("TC-007")
@allure.title("Простановка рейтинга {rating} со страницы работы (панель)")
@pytest.mark.parametrize(
    "rating,placeholder_seeded_work",
    [
        ("SAVE", W.LOVED), ("LIKE", W.KUDOSED), ("READ", W.READ),
        ("PENDING", W.PENDING), ("DISLIKE", W.DISLIKED),
    ],
    indirect=["placeholder_seeded_work"],
)
def test_rate_work_from_work_page_panel(placeholder_seeded_work, driver, rating):
    # Given приложение с чистыми данными и placeholder-строкой работы W без
    # рейтинга (rating=None, но title/author/fandom/wordCount заполнены — см.
    # docstring модуля и фикстуру `placeholder_seeded_work`), ни один из 5
    # рейтингов ещё не выбран. Сидинг выполнен фикстурой ДО старта сессии Appium.
    work = placeholder_seeded_work
    # wait_app_ready (не wait_ui_ready) - тот же паттерн, что закрыл гонку в
    # TC-057 (см. test_side_panel.py, critic-вход tc057-rework accepted
    # 23:03:32, docs/HANDOFF.md queue-пункт 3): open_work_page навигирует
    # WebView (driver.get) СРАЗУ следом - если стартовая live-загрузка Home ещё
    # в полёте, chromedriver теряет цель ("cannot determine loading status from
    # no such window"). wait_ui_ready проверяет только наличие нативной
    # WebView-оболочки, не оседание стартовой загрузки.
    app_steps.wait_app_ready(driver)

    # When пользователь открывает страницу работы и через панель RatingMenu
    # выставляет рейтинг R
    rating_steps.open_work_page(driver, work.ao3_id)
    rating_steps.rate_current_work(driver, rating)

    # Then работа W появляется в соответствующей вкладке Library — наблюдаемое
    # подтверждение того, что панель проставила рейтинг и он сохранён в Room
    # (без перезагрузки WebView, без прямого обращения к БД из UI-теста)
    app_steps.open_tab(driver, "Library")
    library_steps.assert_work_in_tab(driver, rating, work.title)


@pytest.mark.p0
@pytest.mark.live
@allure.id("TC-008")
@allure.title("Повторный тап по выбранному рейтингу снимает его (deselect, панель работы)")
def test_deselect_rating_on_work_page_panel(loved_work_seeded, driver):
    # Given работа W засеяна с рейтингом Loved (SAVE) и присутствует во вкладке FAVORITE
    # (сидинг выполнен фикстурой `loved_work_seeded` ДО старта сессии Appium)
    work = loved_work_seeded
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Library")
    library_steps.assert_work_in_tab(driver, "SAVE", work.title)

    # When пользователь открывает страницу работы W и повторно нажимает уже
    # выбранную кнопку «Favorite» (Loved) на панели RatingMenu
    rating_steps.open_work_page(driver, work.ao3_id)
    # Панель RatingMenu рендерится только на вкладке Browse (isWorkPage) — после
    # проверки Library (см. Given выше) возвращаемся на нативную вкладку Browse,
    # иначе она остаётся скрыта за AnimatedVisibility (BottomBar.kt) на Library.
    app_steps.open_tab(driver, "Browse")
    rating_steps.rate_current_work(driver, "SAVE")

    # Then работа W больше не отображается во вкладке FAVORITE экрана Library —
    # наблюдаемое подтверждение deselect (rating сброшен в null)
    app_steps.open_tab(driver, "Library")
    library_steps.assert_work_not_in_tab(driver, "SAVE", work.title)


# --- TC-141/144: rating/bridge — авто-клик kudos через ВСТРОЕННУЮ панель
# work-страницы (`RatingMenu`), в отличие от листингового bottom-sheet
# (`test_rating_listing.py::TC-138..143`). `BrowserViewModel.kt` несёт ДВЕ
# отдельные ветки панельного механизма сохранения:
# - `savePanelRating`, `existing != null` (`:743-758`, запись УЖЕ в Room) —
#   структурно НЕ содержит вызова с kudos (TC-141, асимметрия путей, ядро
#   `bugs/BUG-015.md`);
# - `onRateWorkRequested`/`pendingPanelSave` (`:1053-1054`, запись ЕЩЁ НЕ в
#   Room, первое сохранение) — кликает kudos (TC-144, позитивный контроль
#   негатива TC-141, без него зелёный TC-141 неотличим от «панель физически не
#   может кликнуть узел»).
# Обе используют `rb.WORK_WITH_DOWNLOAD_FILENAME` (та же запись, что TC-032/033/
# 114/115) — единственная work-страница остаётся вкладкой-0/единственной живой
# WebView на протяжении сценария, sticky-context блокер `AT-BUG-022`
# (см. `test_rating_listing.py`) здесь не возникает по построению.


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-141")
@allure.title("Правка личного тега уже-Favorite работы через панель work-страницы не отправляет kudos (асимметрия путей)")
@pytest.mark.parametrize("replay", [rb.WORK_WITH_DOWNLOAD_FILENAME], indirect=True)
def test_edit_tag_on_already_saved_work_via_panel_does_not_click_kudos(replay, loved_work_seeded, driver):
    # Given работа W (LOVED) уже имеет рейтинг Favorite (SAVE), засеяна напрямую
    # в Room, без личных тегов; открыта её work-страница, встроенная панель
    # RatingMenu уже показывает Favorite выбранным (рейтинг прочитан из Room при
    # загрузке); узел #kudo_submit на той же странице без data-kudo-clicked
    # (baseline инструментированного узла фикстуры)
    work = loved_work_seeded
    app_steps.wait_app_ready(driver)
    rating_steps.open_work_page(driver, work.ao3_id)

    # When пользователь раскрывает раздел тегов ВСТРОЕННОЙ панели (не bottom-sheet
    # листинга) и добавляет личный тег «panel-kudos-probe» (правка метаданных,
    # рейтинг НЕ меняется, остаётся Favorite) — идёт веткой savePanelRating,
    # existing != null (`:743-758`), тот же вход, что TC-114 для авто-скачивания
    rating_steps.add_tag_via_panel(driver, "panel-kudos-probe")

    # Then тег «panel-kudos-probe» сохраняется среди выбранных
    rating_steps.assert_chip_visible(driver, "panel-kudos-probe")

    # And узел #kudo_submit на ТОЙ ЖЕ (единственной открытой) work-вкладке НЕ
    # получает data-kudo-clicked — ветка `:743-758` структурно не содержит
    # вызова с kudos (асимметрия путей КАК ЕСТЬ, не решение — то же по смыслу
    # действие через листинг, TC-139, кликает: баг, ядро BUG-015). Держим
    # отсутствие клика весь бюджет, не читаем один раз (негатив защищает от
    # гипотетического бага смешения веток panel/listing)
    browser_steps.assert_kudo_submit_click_count_holds(driver, 0)


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-144")
@allure.title("Первое сохранение LIKE/SAVE через встроенную панель work-страницы (запись ещё не в Room) отправляет kudos ровно один раз")
@pytest.mark.parametrize("replay", [rb.WORK_WITH_DOWNLOAD_FILENAME], indirect=True)
def test_first_panel_save_clicks_kudos_once(clean_app, replay, driver):
    # Given приложение с чистыми данными; в Room НЕТ ни одной записи для W —
    # первое касание этой работы (критично: НЕ сидить заранее — любой сидинг
    # создал бы строку WorkRating и увёл бы сценарий в ветку savePanelRating/
    # existing != null, TC-141, а не pendingPanelSave, предмет ЭТОГО кейса).
    # Открыта единственная вкладка — work-страница W (IN-PLACE); узел
    # #kudo_submit ещё без data-kudo-clicked (baseline)
    work = W.LOVED
    app_steps.wait_app_ready(driver)
    rating_steps.open_work_page(driver, work.ao3_id)

    # When пользователь раскрывает встроенную панель RatingMenu и выбирает
    # рейтинг «Kudosed» (LIKE) — первое в жизни работы сохранение через панель
    # (ветка onRateWorkRequested/pendingPanelSave, `:1053-1054`, НЕ savePanelRating)
    rating_steps.rate_current_work(driver, "LIKE")

    # Then рейтинг сохранён: панель показывает «Kudosed» выбранным без
    # перезагрузки страницы, работа появляется на вкладке Kudosed экрана Library
    # (новая строка WorkRating создана — переход «записи не было -> запись
    # появилась», отличающий эту ветку от TC-141)
    app_steps.open_tab(driver, "Library")
    library_steps.assert_work_in_tab(driver, "LIKE", work.title)

    # And на ТОЙ ЖЕ (единственной) work-вкладке узел #kudo_submit получает
    # data-kudo-clicked="1" — ровно один клик; повторное чтение после паузы
    # даёт то же «1», не «2» (инкрементный счётчик, та же механика, что TC-138)
    app_steps.open_tab(driver, "Browse")
    browser_steps.assert_kudo_submit_click_count(driver, 1)
    browser_steps.assert_kudo_submit_click_count_holds(driver, 1)


# --- TC-256 (AT-BUG-074): auto-mark-as-read (`Ao3JsBridge.onWorkFinished`,
# `BrowserViewModel.kt:1292-1326`, фикс `bugs/BUG-067.md` commit `07805a9f`,
# сборка 59be96c6) — скролл work-страницы до конца `#chapters` при
# `rating=null` проставляет `READ`, сохраняя `downloadPath` и НЕ перезаписывая
# непустые локальные метаданные (`backfillMetadata` дозаполняет только ПУСТЫЕ
# поля). Регресс-замок BUG-067 для двери `onWorkFinished` — companion TC-151/
# TC-152 закрывают ТОТ ЖЕ класс дефекта («пересборка WorkRating конструктором
# теряет downloadPath/метаданные»), но для дверей панели/overlay листинга;
# ESC-026 (R1, `state/escalations.md`) явно называет дверь `onWorkFinished` НЕ
# закрытой той партией — этот кейс закрывает именно её.
#
# `rb.LISTING_BASIC_FILENAME` — ТА ЖЕ запись, что несёт Given TC-151/TC-152
# (`W.LOVED.ao3_id`, потребитель фикстуры, чинившейся `bugs/AT-BUG-074.md`:
# `#chapters`/`.userstuff.module` + `dd.fandom a`/`dd.words`, узлы, которые
# скрейпит `onScroll`, ao3_bridge.js:1184-1194).
_TC256_READ_WAIT_TIMEOUT = 20  # асинхронный upsert через viewModelScope.launch


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-256")
@allure.title(
    "Дочитывание скачанной работы без рейтинга проставляет READ, сохраняя "
    "downloadPath и локальные метаданные (auto-mark-as-read, AT-BUG-074)"
)
@pytest.mark.parametrize("replay", [rb.LISTING_BASIC_FILENAME], indirect=True)
def test_auto_mark_as_read_on_scroll_to_bottom_preserves_download_path_and_local_metadata(
    tc256_auto_read_baseline, replay, driver
):
    # Given работа W (`ao3_id` = `W.LOVED.ao3_id`, тот же ao3_id, что TC-151/152)
    # скачана (`downloadPath` на реальный файл), рейтинг НЕ выставлен, личная
    # заметка "note A" и тег "tagA" присутствуют, локальные title/fandom/
    # wordCount ("ЛОКАЛЬНЫЙ заголовок"/"Мой фандом"/777777) ОТЛИЧАЮТСЯ от
    # канонической work-страницы фикстуры ("A Loved Test Work"/"Fandom
    # Alpha"/4200) — сидинг ДО старта сессии Appium (`tc256_auto_read_baseline`)
    work, device_path = tc256_auto_read_baseline
    baseline = seed_db.read_work_ratings_full()[work.ao3_id]
    assert baseline["rating"] is None, (
        f"Given TC-256 не выполнен: rating={baseline['rating']!r}, ожидался None"
    )
    baseline_timestamp = baseline["timestamp"]

    app_steps.wait_app_ready(driver)
    rating_steps.open_work_page(driver, work.ao3_id)

    # When пользователь скроллит страницу работы до конца — последний
    # .userstuff.module внутри #chapters целиком попадает в вьюпорт, ссылки
    # «Next Chapter →» на странице нет (одностраничная работа) — onScroll
    # (ao3_bridge.js:1184-1194) скрейпит title/author/fandom/wordCount со
    # страницы и вызывает Ao3JsBridge.onWorkFinished
    browser_steps.scroll_work_page_to_bottom(driver)

    # Then рейтинг работы W становится READ. Различающий оракул timestamp
    # (не инвариантный "поле осталось тем же значением") — если onScroll/upsert
    # вообще не сработал (например, геометрия фикстуры не привела нижнюю
    # границу .userstuff.module в вьюпорт), timestamp остался бы baseline-значением
    # (тот же приём, что TC-152.md требование [2]/O1)
    row = rating_steps.wait_for_rating(work.ao3_id, "READ", timeout=_TC256_READ_WAIT_TIMEOUT)
    assert row["timestamp"] != baseline_timestamp, (
        "timestamp не изменился относительно baseline — upsert-путь onWorkFinished "
        "не сработал вовсе (различающий оракул CH-008/TC-152 [2]), rating=READ "
        "выше ложно-позитивен"
    )

    # And downloadPath остаётся НЕИЗМЕННЫМ — тем же путём на тот же файл на диске
    # (связь строка↔файл не рвётся операцией, которая файла не касается)
    assert row["downloadPath"] == device_path

    # And личная заметка "note A" и тег "tagA" остаются без изменений
    assert row["comment"] == "note A"
    assert row["tags"] == ["tagA"]

    # And title/fandom/wordCount остаются ЛОКАЛЬНЫМИ значениями — скрейп со
    # страницы их НЕ перезаписывает (backfillMetadata дозаполняет только ПУСТЫЕ
    # поля; у этой строки все три уже непустые, канонические фикстурные
    # значения "A Loved Test Work"/"Fandom Alpha"/4200 сюда НЕ попадают)
    assert row["title"] == work.title
    assert row["fandom"] == work.fandom
    assert row["word_count"] == work.word_count

    # And работа продолжает быть видна на вкладке FILES Library (файл цел,
    # downloadPath жив) И появляется на вкладке READ (новый рейтинг)
    app_steps.open_tab(driver, "Library")
    library_steps.assert_work_in_tab(driver, "READ", work.title)
    library_steps.assert_work_in_files_tab(driver, work.title)
