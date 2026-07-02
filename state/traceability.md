# Traceability-матрица

Генерируется из меток тестов (`@allure.id`, `@pytest.mark.pN`) и статусов тест-кейсов.
Ведётся test-automator/test-maintainer. Связывает: риск → тест-кейс → автотест → последний прогон.

| Риск | Тест-кейс | Приоритет | Автотест | Статус кейса | Последний прогон |
|---|---|---|---|---|---|
| R-04 | (P0 smoke: рейтинг→вкладка) | P0 | framework/tests/test_smoke.py::test_seeded_work_appears_in_correct_tab | Automated (де-факто) | 9/9 зелёные 2026-07-02 |
| R-01 | (P0 smoke: clear all) | P0 | test_smoke.py::test_clear_all_ratings | Automated (де-факто) | зелёный |
| R-06 | TC-013 (Disliked скрыт при фильтрации) | P0 | — | Review (Blocked) | не прогонялся — заблокирован отсутствием replay-фикстур листинга (см. заметку в TC-013.md) |
| R-06 | TC-014 (work без рейтинга/comment-only не скрывается) | P0 | — | Review (Blocked) | не прогонялся — тот же replay-блокер; `seed_db.seed_with_comment` добавлен заранее для разблокирования |
| R-06 | TC-015 (Enable filtering off → всё видно) | P0 | — | Review (Blocked) | не прогонялся — replay-блокер + расхождение PROJECT.md/код (нет глобального тумблера "Enable filtering", только per-rating), см. заметку в TC-015.md |

> Примечание: smoke Фазы 1 написан напрямую (до формального тест-дизайна). В Фазе 2
> test-designer оформит соответствующие TC-xxx и свяжет их обратными ссылками.
