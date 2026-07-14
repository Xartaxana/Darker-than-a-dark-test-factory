# Карта покрытия (генерируется, НЕ редактировать руками)

generated_at: 2026-07-14T12:39:17Z · генератор: `scripts/coverage_map.py`
Проекция из frontmatter test-cases/ и runs/ (принцип G1, как у `state/factory-status.md`). Рукописной модели покрытия не существует — этот файл не второй источник истины, а вывод.

прогоны без tc_results (поле ещё не внедрено): RUN-20260702-0300

## Сводка по областям

| Область | Кейсов | Automated | coverage_status |
|---|---|---|---|
| backup | 1 | 0 | none |
| browser | 8 | 6 | partial |
| downloads | 8 | 3 | partial |
| errors | 1 | 0 | none |
| filter-profiles | 3 | 0 | none |
| library | 8 | 2 | partial |
| rating | 10 | 2 | partial |
| settings | 7 | 3 | partial |
| smoke | 5 | 5 | designed-full |
| tabs | 5 | 0 | none |
| visibility | 3 | 0 | none |

## Риски (docs/01-test-strategy.md §5) → покрытие

| Риск | Категория | Покрывающие кейсы |
|---|---|---|
| R-01 | DATA | backup:TC-021, settings:TC-018, settings:TC-019, settings:TC-020, smoke:TC-004 |
| R-02 | TECH | риск не покрыт дизайном |
| R-03 | TECH | errors:TC-046, smoke:TC-001 |
| R-04 | DATA | library:TC-016, library:TC-017, rating:TC-007, rating:TC-008, rating:TC-009, rating:TC-010, rating:TC-011, rating:TC-012, smoke:TC-003 |
| R-05 | TECH | downloads:TC-032, downloads:TC-033, downloads:TC-034, downloads:TC-035, downloads:TC-036, downloads:TC-037, downloads:TC-038, downloads:TC-039 |
| R-06 | BUS | library:TC-027, library:TC-028, library:TC-029, library:TC-030, library:TC-031, visibility:TC-013, visibility:TC-014, visibility:TC-015 |
| R-07 | OPS | риск не покрыт дизайном |
| R-08 | TECH | tabs:TC-022, tabs:TC-023, tabs:TC-024, tabs:TC-025, tabs:TC-026 |
| R-11 | TECH | browser:TC-050, browser:TC-051, browser:TC-052, browser:TC-053, browser:TC-054, browser:TC-055, browser:TC-057, browser:TC-058, settings:TC-047, settings:TC-048, settings:TC-049, settings:TC-059 |
| R-09 | BUS | filter-profiles:TC-040, filter-profiles:TC-041, filter-profiles:TC-042 |
| R-10 | DATA | rating:TC-043, rating:TC-044, rating:TC-045, rating:TC-056 |
| R-12 | PERF | риск не покрыт дизайном |
| R-13 | A11Y | риск не покрыт дизайном |
| R-14 | COMPAT | риск не покрыт дизайном |
| R-15 | SEC | риск не покрыт дизайном |

## Области

### backup

- coverage_status: **none** (0/1 Automated)
- риски: R-01
- кейсы без risk: нет
- P0/P1 не в Automated: TC-021 [P0, Approved]
- автотесты (automated_by): framework/tests/test_backup_restore.py::test_backup_clear_restore_returns_original_data
- last_green_run: RUN-20260702-0300 (suite: smoke, status: Closed, updated: 2026-07-02T03:35:00Z) — деградировано до ГЛОБАЛЬНОГО прогона: схемы (test-case/run) не связывают run с конкретным TC ИЛИ с областью (нет поля run↔TC/area), см. отчёт builder'а

| Priority | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| P0 |  |  | 1 |  |  |
| P1 |  |  |  |  |  |
| P2 |  |  |  |  |  |
| P3 |  |  |  |  |  |

### browser

- coverage_status: **partial** (6/8 Automated)
- риски: R-11
- кейсы без risk: нет
- P0/P1 не в Automated: нет
- автотесты (automated_by): framework/tests/test_side_panel.py::test_font_buttons_disabled_at_range_boundaries, framework/tests/test_side_panel.py::test_font_size_increase_instant_and_persists, framework/tests/test_side_panel.py::test_pinch_spread_changes_font_size, framework/tests/test_side_panel.py::test_side_panel_and_settings_share_theme_and_font_state, framework/tests/test_side_panel.py::test_side_panel_contrast_toggles_theme_instantly, framework/tests/test_side_panel.py::test_two_finger_drag_changes_brightness
- last_green_run: RUN-20260702-0300 (suite: smoke, status: Closed, updated: 2026-07-02T03:35:00Z) — деградировано до ГЛОБАЛЬНОГО прогона: схемы (test-case/run) не связывают run с конкретным TC ИЛИ с областью (нет поля run↔TC/area), см. отчёт builder'а

| Priority | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| P0 |  |  |  |  |  |
| P1 |  |  |  | 6 |  |
| P2 |  |  |  |  |  |
| P3 |  | 2 |  |  |  |

### downloads

- coverage_status: **partial** (3/8 Automated)
- риски: R-05
- кейсы без risk: нет
- P0/P1 не в Automated: TC-032 [P1, Review], TC-033 [P1, Review]
- автотесты (automated_by): framework/tests/test_downloads.py::test_delete_downloaded_file_keeps_rating_row, framework/tests/test_downloads.py::test_delete_work_removes_row_and_file, framework/tests/test_downloads.py::test_open_downloaded_file_applies_viewport_and_reader_css
- last_green_run: RUN-20260702-0300 (suite: smoke, status: Closed, updated: 2026-07-02T03:35:00Z) — деградировано до ГЛОБАЛЬНОГО прогона: схемы (test-case/run) не связывают run с конкретным TC ИЛИ с областью (нет поля run↔TC/area), см. отчёт builder'а

| Priority | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| P0 |  |  |  |  |  |
| P1 |  | 2 |  | 3 |  |
| P2 |  |  | 2 |  |  |
| P3 |  | 1 |  |  |  |

### errors

- coverage_status: **none** (0/1 Automated)
- риски: R-03 (частично, TECH)
- кейсы без risk: нет
- P0/P1 не в Automated: нет
- автотесты (automated_by): —
- last_green_run: RUN-20260702-0300 (suite: smoke, status: Closed, updated: 2026-07-02T03:35:00Z) — деградировано до ГЛОБАЛЬНОГО прогона: схемы (test-case/run) не связывают run с конкретным TC ИЛИ с областью (нет поля run↔TC/area), см. отчёт builder'а

| Priority | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| P0 |  |  |  |  |  |
| P1 |  |  |  |  |  |
| P2 |  |  | 1 |  |  |
| P3 |  |  |  |  |  |

### filter-profiles

- coverage_status: **none** (0/3 Automated)
- риски: R-09 (proposed, не утверждён в §5)
- кейсы без risk: нет
- P0/P1 не в Automated: TC-040 [P1, Approved], TC-041 [P1, Approved], TC-042 [P1, Approved]
- автотесты (automated_by): —
- last_green_run: RUN-20260702-0300 (suite: smoke, status: Closed, updated: 2026-07-02T03:35:00Z) — деградировано до ГЛОБАЛЬНОГО прогона: схемы (test-case/run) не связывают run с конкретным TC ИЛИ с областью (нет поля run↔TC/area), см. отчёт builder'а

| Priority | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| P0 |  |  |  |  |  |
| P1 |  |  | 3 |  |  |
| P2 |  |  |  |  |  |
| P3 |  |  |  |  |  |

### library

- coverage_status: **partial** (2/8 Automated)
- риски: R-04, R-06
- кейсы без risk: TC-006
- P0/P1 не в Automated: TC-027 [P1, Approved], TC-028 [P1, Approved], TC-029 [P1, Approved], TC-030 [P1, Approved]
- автотесты (automated_by): framework/tests/test_library.py::test_change_rating_moves_work_between_tabs, framework/tests/test_library.py::test_comment_only_not_in_any_rating_tab, framework/tests/test_library_filters.py::test_library_filter_by_fandom, framework/tests/test_library_filters.py::test_library_filter_downloaded_only, framework/tests/test_library_filters.py::test_library_filter_word_count_range, framework/tests/test_library_filters.py::test_library_sort_wordcount_desc_resets_scroll
- last_green_run: RUN-20260702-0300 (suite: smoke, status: Closed, updated: 2026-07-02T03:35:00Z) — деградировано до ГЛОБАЛЬНОГО прогона: схемы (test-case/run) не связывают run с конкретным TC ИЛИ с областью (нет поля run↔TC/area), см. отчёт builder'а

| Priority | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| P0 |  |  |  | 2 |  |
| P1 |  |  | 4 |  |  |
| P2 | 1 |  |  |  |  |
| P3 |  | 1 |  |  |  |

### rating

- coverage_status: **partial** (2/10 Automated)
- риски: R-04, R-10 (proposed, не утверждён в §5)
- кейсы без risk: нет
- P0/P1 не в Automated: TC-009 [P0, Review], TC-012 [P1, Review], TC-043 [P1, Review], TC-044 [P1, Review], TC-045 [P1, Review]
- автотесты (automated_by): framework/tests/test_rating.py::test_deselect_rating_on_work_page_panel, framework/tests/test_rating.py::test_rate_work_from_work_page_panel
- last_green_run: RUN-20260702-0300 (suite: smoke, status: Closed, updated: 2026-07-02T03:35:00Z) — деградировано до ГЛОБАЛЬНОГО прогона: схемы (test-case/run) не связывают run с конкретным TC ИЛИ с областью (нет поля run↔TC/area), см. отчёт builder'а

| Priority | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| P0 |  | 1 |  | 2 |  |
| P1 |  | 4 |  |  |  |
| P2 |  |  | 2 |  |  |
| P3 |  | 1 |  |  |  |

### settings

- coverage_status: **partial** (3/7 Automated)
- риски: R-01, R-11
- кейсы без risk: нет
- P0/P1 не в Automated: нет
- автотесты (automated_by): framework/tests/test_settings.py::test_system_theme_follows_os_dark_mode, framework/tests/test_settings.py::test_theme_dark_applies_instantly_without_recreating_activity, framework/tests/test_settings.py::test_webview_dark_mode_applies_instantly
- last_green_run: RUN-20260702-0300 (suite: smoke, status: Closed, updated: 2026-07-02T03:35:00Z) — деградировано до ГЛОБАЛЬНОГО прогона: схемы (test-case/run) не связывают run с конкретным TC ИЛИ с областью (нет поля run↔TC/area), см. отчёт builder'а

| Priority | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| P0 |  |  |  |  |  |
| P1 |  |  |  | 3 |  |
| P2 |  |  | 3 |  |  |
| P3 |  | 1 |  |  |  |

### smoke

- coverage_status: **designed-full** (5/5 Automated)
- риски: R-01, R-03, R-04
- кейсы без risk: TC-002, TC-005
- P0/P1 не в Automated: нет
- автотесты (automated_by): framework/tests/test_smoke.py::test_app_launches_and_loads_ao3, framework/tests/test_smoke.py::test_bottom_nav_switches_screens, framework/tests/test_smoke.py::test_clear_all_ratings, framework/tests/test_smoke.py::test_seeded_work_appears_in_correct_tab, framework/tests/test_smoke.py::test_theme_toggle_stable
- last_green_run: RUN-20260702-0300 (suite: smoke, status: Closed, updated: 2026-07-02T03:35:00Z) — деградировано до ГЛОБАЛЬНОГО прогона: схемы (test-case/run) не связывают run с конкретным TC ИЛИ с областью (нет поля run↔TC/area), см. отчёт builder'а

| Priority | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| P0 |  |  |  | 5 |  |
| P1 |  |  |  |  |  |
| P2 |  |  |  |  |  |
| P3 |  |  |  |  |  |

### tabs

- coverage_status: **none** (0/5 Automated)
- риски: R-08
- кейсы без risk: нет
- P0/P1 не в Automated: TC-022 [P1, Approved], TC-023 [P1, Approved], TC-025 [P1, Approved], TC-026 [P1, Approved]
- автотесты (automated_by): —
- last_green_run: RUN-20260702-0300 (suite: smoke, status: Closed, updated: 2026-07-02T03:35:00Z) — деградировано до ГЛОБАЛЬНОГО прогона: схемы (test-case/run) не связывают run с конкретным TC ИЛИ с областью (нет поля run↔TC/area), см. отчёт builder'а

| Priority | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| P0 |  |  |  |  |  |
| P1 |  |  | 4 |  |  |
| P2 |  |  |  |  |  |
| P3 |  | 1 |  |  |  |

### visibility

- coverage_status: **none** (0/3 Automated)
- риски: R-06
- кейсы без risk: нет
- P0/P1 не в Automated: TC-013 [P0, Review], TC-014 [P0, Review], TC-015 [P0, Review]
- автотесты (automated_by): —
- last_green_run: RUN-20260702-0300 (suite: smoke, status: Closed, updated: 2026-07-02T03:35:00Z) — деградировано до ГЛОБАЛЬНОГО прогона: схемы (test-case/run) не связывают run с конкретным TC ИЛИ с областью (нет поля run↔TC/area), см. отчёт builder'а

| Priority | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| P0 |  | 3 |  |  |  |
| P1 |  |  |  |  |  |
| P2 |  |  |  |  |  |
| P3 |  |  |  |  |  |

