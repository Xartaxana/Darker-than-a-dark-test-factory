# Traceability-матрица

Генерируется из меток тестов (`@allure.id`, `@pytest.mark.pN`) и статусов тест-кейсов.
Ведётся test-automator/test-maintainer. Связывает: риск → тест-кейс → автотест → последний прогон.

| Риск | Тест-кейс | Приоритет | Автотест | Статус кейса | Последний прогон |
|---|---|---|---|---|---|
| R-04 | (P0 smoke: рейтинг→вкладка) | P0 | framework/tests/test_smoke.py::test_seeded_work_appears_in_correct_tab | Automated (де-факто) | 9/9 зелёные 2026-07-02 |
| R-01 | (P0 smoke: clear all) | P0 | test_smoke.py::test_clear_all_ratings | Automated (де-факто) | зелёный |

> Примечание: smoke Фазы 1 написан напрямую (до формального тест-дизайна). В Фазе 2
> test-designer оформит соответствующие TC-xxx и свяжет их обратными ссылками.
