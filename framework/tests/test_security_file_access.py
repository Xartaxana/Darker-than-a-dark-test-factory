"""TC-103 (security/file-access): попытка выйти за пределы контента загрузки
через встроенную file:// ссылку внутри уже открытого скачанного файла.

∩ TC-034 (`test_downloads.py`) — переиспользует ТУ ЖЕ инфраструктуру сидинга
(`seed_db.seed_with_download` через `app_steps.seed_downloaded_work`) и открытия
файла (`library_steps.open_downloaded_file`), НЕ меняя её: HTML-фикстура здесь —
ОТДЕЛЬНЫЙ файл (не `data/fixtures/downloaded_work.html` TC-034), дополненный
одной тестовой ссылкой `#probe-link` на реально существующий internal-путь
приложения (Room DB, `databases/ao3_ratings.db` — тот же файл, что
`framework/data/seed_db.py::_DB_REL`), заведомо вне
`seed_db._DOWNLOAD_FIXTURE_REL_DIR`. Целевой путь лежит внутри песочницы ТОГО
ЖЕ приложения (тот же UID) — кейс проверяет поведение ПРИЛОЖЕНИЯ (не превращает
открытие скачанного контента в файловый браузер), не гарантию ОС/SAF (testability
gap, см. TC-103.md «Заметки для автоматизации»)."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import allure
import pytest

from framework.config import settings
from framework.data import works as W
from framework.steps import app_steps, browser_steps, library_steps

# Тот же относительный путь, что `seed_db._DB_REL` (Room DB приложения) —
# гарантированно существует к моменту теста: `seed_downloaded_work` вызывает
# `seed_db.seed_with_download`, которая сама вызывает `ensure_db_initialized()`
# (создаёт файл БД, если его ещё нет) ДО записи строки работы.
_PROBE_TARGET_REL_PATH = "databases/ao3_ratings.db"
_PROBE_TARGET_ABS_PATH = f"/data/user/0/{settings.APP_PACKAGE}/{_PROBE_TARGET_REL_PATH}"

_PROBE_HTML = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>TC-103 file access probe fixture</title>
</head>
<body>
  <div id="workskin">
    <h1 class="title heading">TC-103 File Access Probe Target</h1>
    <p>Fixture body for TC-103 (security/file-access) — same shape as TC-034's
    downloaded_work.html, extended with one additional in-page link pointing at
    a real internal file OUTSIDE the download-content directory (Room DB).</p>
    <a id="probe-link" href="file://{_PROBE_TARGET_ABS_PATH}">probe</a>
  </div>
</body>
</html>
"""


@pytest.fixture()
def file_access_probe_seeded():
    """Работа `W.FILE_ACCESS_PROBE_TARGET` засеяна с рейтингом SAVE и уже
    «скачанным» HTML-файлом (тот же механизм, что `downloaded_work_seeded` в
    `conftest.py`), но с ОТДЕЛЬНОЙ HTML-фикстурой (`_PROBE_HTML`), несущей
    дополнительную тестовую ссылку — не переиспользует и не меняет
    `data/fixtures/downloaded_work.html` (используется другими TC-034/035/036
    тестами)."""
    app_steps.clean_state()
    tmp_dir = Path(tempfile.mkdtemp(prefix="tc103_probe_"))
    try:
        local_html = tmp_dir / "tc103_probe.html"
        local_html.write_text(_PROBE_HTML, encoding="utf-8")
        app_steps.seed_downloaded_work(W.FILE_ACCESS_PROBE_TARGET, "SAVE", local_html)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    yield W.FILE_ACCESS_PROBE_TARGET


@pytest.mark.p1
@allure.id("TC-103")
@allure.title("file:// доступ: попытка выйти за пределы контента загрузки через встроенную ссылку")
def test_file_link_inside_downloaded_work_does_not_escape_download_content(
    file_access_probe_seeded, driver,
):
    # Given на вкладке FILES есть работа со связанным .html-файлом, содержащим
    # встроенную ссылку на file://-путь ВНЕ директории загрузок (реально
    # существующий internal-файл приложения — Room DB, не часть скачанного контента)
    work = file_access_probe_seeded
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Library")
    library_steps.assert_work_in_files_tab(driver, work.title)

    # When пользователь открывает работу (тап по карточке, как в TC-034)
    library_steps.open_downloaded_file(driver, work.title)
    browser_steps.close_other_tabs(driver)
    browser_steps.assert_local_file_opened(driver)
    original_url = browser_steps.get_active_tab_url(driver)

    # And внутри открывшейся страницы тапает по тестовой ссылке probe-link
    browser_steps.click_probe_link(driver)

    # Then WebView НЕ отображает содержимое целевого файла как успешно
    # загруженную страницу — либо навигация остаётся на прежнем URL, либо
    # показывается ошибка загрузки/пустой результат; открытие скачанного
    # контента не превращается в произвольный файловый браузер по внутреннему
    # хранилищу приложения по клику на встроенную в HTML ссылку
    browser_steps.assert_file_link_navigation_blocked_or_empty(driver, original_url)
