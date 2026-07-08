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
| R-11 (proposed) | TC-050 (Contrast side panel → тема мгновенно) | P1 | framework/tests/test_side_panel.py::test_side_panel_contrast_toggles_theme_instantly | Approved (ожидает review) | 3/3 зелёные 2026-07-08 |
| R-11 (proposed) | TC-054 (side panel и Settings — общий стейт темы/шрифта) | P1 | framework/tests/test_side_panel.py::test_side_panel_and_settings_share_theme_and_font_state | Approved (ожидает review) | 3/3 зелёные 2026-07-08 |
| R-11 (proposed) | TC-051 (A+ side panel: мгновенно + переживает рестарт) | P1 | framework/tests/test_side_panel.py::test_font_size_increase_instant_and_persists | Approved (ожидает review) | 3/3 зелёные 2026-07-08 |
| R-11 (proposed) | TC-052 (кнопки шрифта disabled на границах диапазона) | P1 | framework/tests/test_side_panel.py::test_font_buttons_disabled_at_range_boundaries | Approved (ожидает review) | 3/3 зелёные 2026-07-08 (потребовался фикс локатора: enabled читается с кликабельного родителя TextView, а не с самого текстового узла) |
| R-11 (proposed) | TC-053 (pinch/spread меняет fontSizeStep) | P1 | framework/tests/test_side_panel.py::test_pinch_spread_changes_font_size | Approved (ожидает review) | 3/3 зелёные 2026-07-08 (жест через `mobile: pinchOpenGesture`/`pinchCloseGesture`; HUD-индикатор не проверяется — известное ограничение, нет contentDescription/testTag, см. заметку в TC-053.md) |
| R-11 (proposed) | TC-055 (двухпальцевый драг → яркость + overlay) | P1 | framework/tests/test_side_panel.py::test_two_finger_drag_changes_brightness | Approved (ожидает review) | 3/3 зелёные 2026-07-08 (прокси: средняя яркость скриншота через Pillow, добавлен в requirements.txt; сырые W3C multi-touch actions; фазы v≥0/v<0 не различаются раздельно — известное ограничение, см. заметку в TC-055.md) |

> Примечание: smoke Фазы 1 написан напрямую (до формального тест-дизайна). В Фазе 2
> test-designer оформит соответствующие TC-xxx и свяжет их обратными ссылками.
