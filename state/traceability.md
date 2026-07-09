# Traceability-матрица

Генерируется из меток тестов (`@allure.id`, `@pytest.mark.pN`) и статусов тест-кейсов.
Ведётся test-automator/test-maintainer. Связывает: риск → тест-кейс → автотест → последний прогон.

| Риск | Тест-кейс | Приоритет | Автотест | Статус кейса | Последний прогон |
|---|---|---|---|---|---|
| R-04 | (P0 smoke: рейтинг→вкладка) | P0 | framework/tests/test_smoke.py::test_seeded_work_appears_in_correct_tab | Automated (де-факто) | 9/9 зелёные 2026-07-02 |
| R-01 | (P0 smoke: clear all) | P0 | test_smoke.py::test_clear_all_ratings | Automated (де-факто) | зелёный |
| R-04 | TC-007 (5 рейтингов со страницы работы, панель) | P0 | framework/tests/test_rating.py::test_rate_work_from_work_page_panel | Automated | 3/3 зелёные 2026-07-03 (+ полный P0 smoke 17/17) |
| R-04 | TC-008 (deselect повторным тапом, панель работы) | P0 | framework/tests/test_rating.py::test_deselect_rating_on_work_page_panel | Automated | 3/3 зелёные 2026-07-03 (+ полный P0 smoke 17/17) |
| R-04 | TC-016 (смена рейтинга между вкладками Library) | P0 | framework/tests/test_library.py::test_change_rating_moves_work_between_tabs | Automated | 3/3 зелёные 2026-07-03 (+ полный P0 smoke 17/17) |
| R-04 | TC-017 (comment-only не в рейтинговых вкладках) | P0 | framework/tests/test_library.py::test_comment_only_not_in_any_rating_tab | Automated | 3/3 зелёные 2026-07-03 (+ полный P0 smoke 17/17) |
| R-06 | TC-013 (Disliked скрыт при фильтрации) | P0 | — | Review (Blocked) | не прогонялся — заблокирован отсутствием replay-фикстур листинга (см. заметку в TC-013.md) |
| R-06 | TC-014 (work без рейтинга/comment-only не скрывается) | P0 | — | Review (Blocked) | не прогонялся — тот же replay-блокер; `seed_db.seed_with_comment` добавлен заранее для разблокирования |
| R-06 | TC-015 (Enable filtering off → всё видно) | P0 | — | Review (Blocked) | не прогонялся — replay-блокер + расхождение PROJECT.md/код (нет глобального тумблера "Enable filtering", только per-rating), см. заметку в TC-015.md |
| R-04 | TC-009 (5 рейтингов из листинга, bottom-sheet) | P0 | — | Review (Blocked) | не прогонялся — тот же replay-блокер (нужен детерминированный листинг с блёрбом синтетической работы), см. заметку в TC-009.md |
| R-11 (proposed) | TC-050 (Contrast side panel → тема мгновенно) | P1 | framework/tests/test_side_panel.py::test_side_panel_contrast_toggles_theme_instantly | Automated (active) | review OK 2026-07-08 (test-reviewer 6/6 зелёные) |
| R-11 (proposed) | TC-054 (side panel и Settings — общий стейт темы/шрифта) | P1 | framework/tests/test_side_panel.py::test_side_panel_and_settings_share_theme_and_font_state | Automated (active) | review OK 2026-07-08 (test-reviewer 6/6 зелёные) |
| R-11 (proposed) | TC-051 (A+ side panel: мгновенно + переживает рестарт) | P1 | framework/tests/test_side_panel.py::test_font_size_increase_instant_and_persists | Automated (active) | review OK 2026-07-08 (test-reviewer 6/6 зелёные) |
| R-11 (proposed) | TC-052 (кнопки шрифта disabled на границах диапазона) | P1 | framework/tests/test_side_panel.py::test_font_buttons_disabled_at_range_boundaries | Automated (active) | review OK 2026-07-08 (test-reviewer 6/6 зелёные; enabled читается с кликабельного родителя TextView) |
| R-11 (proposed) | TC-053 (pinch/spread меняет fontSizeStep) | P1 | framework/tests/test_side_panel.py::test_pinch_spread_changes_font_size | Automated (active) | review OK 2026-07-08 (test-reviewer 6/6 зелёные; жест через `mobile: pinchOpenGesture`/`pinchCloseGesture`; HUD не проверяется — известное ограничение, см. TC-053.md) |
| R-11 (proposed) | TC-055 (двухпальцевый драг → яркость + overlay) | P1 | framework/tests/test_side_panel.py::test_two_finger_drag_changes_brightness | Automated (active) | review OK 2026-07-08 (test-reviewer 6/6 зелёные; прокси luma скриншота через Pillow; фазы v≥0/v<0 не различаются раздельно — известное ограничение, см. TC-055.md) |
| R-05 | TC-034 (открытие скачанного файла → viewport+reader.css) | P1 | framework/tests/test_downloads.py::test_open_downloaded_file_applies_viewport_and_reader_css | Automated (active) | review OK 2026-07-09 (test-reviewer: arch_check чист, независимый прогон 1 passed 33.39s / PYTEST_EXIT=0) |
| R-05 | TC-035 (Delete downloaded file сохраняет WorkRating) | P1 | framework/tests/test_downloads.py::test_delete_downloaded_file_keeps_rating_row | Automated (active) | review OK 2026-07-09 (test-reviewer: arch_check чист, локатор «Delete downloaded file» сверен с LibraryScreen.kt:360 — не путается с «Delete work», независимый прогон 1 passed 36.65s / PYTEST_EXIT=0) |
| R-05 | TC-036 (Delete work удаляет файл и запись целиком) | P1 | framework/tests/test_downloads.py::test_delete_work_removes_row_and_file | Automated (active) | review OK 2026-07-09 (test-reviewer: arch_check чист, локатор «Delete work» сверен с LibraryScreen.kt:354 → deleteWork/hasOtherState=false, проверка отсутствия по обеим вкладкам SAVE+FILES; независимый прогон 1 passed 41.16s / PYTEST_EXIT=0) |
| R-05 | TC-032 (авто-скачивание при Loved + Auto-download) | P1 | — | Review (Blocked) | не прогонялся — требует replay-запись страницы работы с `li.download a[href*=".html"]` (DownloadRepository ходит по сети через OkHttp, не WebView) + подключение `framework/core/mitm.py` к conftest; в `recordings/` пока только `ao3_home_smoke.mitm`; тот же класс блокера, что у TC-009/013/014/015, см. заметку в TC-032.md |
| R-05 | TC-033 (ручное скачивание из Library) | P1 | — | Review (Blocked) | не прогонялся — тот же replay-блокер, что TC-032, см. заметку в TC-033.md |
| R-04 | TC-012 (applyRatings синхронизирует бейдж по 2 вхождениям работы на листинге) | P1 | — | Review (Blocked) | не прогонялся — тот же класс блокера AT-BUG-004: нужна replay-фикстура листинга с ДВУМЯ `<li id="work_{id}">` одного `ao3_id` (доп. требование сверх базовой листинговой записи), см. заметку в TC-012.md |
| R-10 (proposed) | TC-043 (comment-only не в рейтинговых вкладках и не скрыт фильтрацией) | P1 | — | Review (Blocked) | не прогонялся — половина сценария (видимость на листинге despite фильтрация) требует ту же replay-фикстуру листинга, что TC-013/014/015 (класс AT-BUG-004); вторая половина (не в вкладках Library) уже покрыта TC-017/test_library.py, см. заметку в TC-043.md |
| R-10 (proposed) | TC-044 (Note-кнопка на листинге открывает overlay с развёрнутым комментарием) | P1 | — | Review (Blocked) | не прогонялся — Note-кнопка существует только внутри блёрба листинга, тот же класс блокера AT-BUG-004, см. заметку в TC-044.md |
| R-10 (proposed) | TC-045 (личные теги не влияют на видимость) | P1 | — | Review (Blocked) | не прогонялся — механически идентичен TC-013/014/015 (`applyAllFilters` не читает `tags`), тот же класс блокера AT-BUG-004 + доработка seed_db.py под `tags` (не самостоятельный блокер), см. заметку в TC-045.md |

> Примечание: smoke Фазы 1 написан напрямую (до формального тест-дизайна). В Фазе 2
> test-designer оформит соответствующие TC-xxx и свяжет их обратными ссылками.
