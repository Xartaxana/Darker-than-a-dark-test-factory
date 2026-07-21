# Карта покрытия (генерируется, НЕ редактировать руками)

generated_at: 2026-07-21T16:47:13Z · генератор: `scripts/coverage_map.py`
Проекция из frontmatter test-cases/ и runs/ (принцип G1, как у `state/factory-status.md`). Рукописной модели покрытия не существует — этот файл не второй источник истины, а вывод.

прогоны без tc_results (поле ещё не внедрено): RUN-20260702-0300

## Сводка по областям

| Область | Кейсов | Automated | coverage_status |
|---|---|---|---|
| backup | 1 | 1 | designed-full |
| browser | 9 | 9 | designed-full |
| canary | 18 | 17 | partial |
| downloads | 8 | 8 | designed-full |
| errors | 1 | 1 | designed-full |
| filter-profiles | 5 | 5 | designed-full |
| library | 15 | 15 | designed-full |
| performance | 4 | 0 | none |
| rating | 14 | 14 | designed-full |
| settings | 7 | 6 | partial |
| smoke | 5 | 5 | designed-full |
| tabs | 6 | 6 | designed-full |
| visibility | 6 | 6 | designed-full |

## Риски (docs/01-test-strategy.md §5) → покрытие

| Риск | Категория | Покрывающие кейсы |
|---|---|---|
| R-01 | DATA | backup:TC-021, settings:TC-018, settings:TC-019, settings:TC-020, smoke:TC-004 |
| R-02 | TECH | canary:TC-066, canary:TC-067, canary:TC-068, canary:TC-069, canary:TC-070, canary:TC-071, canary:TC-072, canary:TC-073, canary:TC-074, canary:TC-075, canary:TC-076, canary:TC-077, canary:TC-078, canary:TC-079, canary:TC-080, canary:TC-081, canary:TC-082, canary:TC-083 |
| R-03 | TECH | errors:TC-046, smoke:TC-001 |
| R-04 | DATA | canary:TC-072, canary:TC-073, canary:TC-074, canary:TC-075, canary:TC-076, canary:TC-077, library:TC-016, library:TC-017, rating:TC-007, rating:TC-008, rating:TC-009, rating:TC-010, rating:TC-011, rating:TC-012, smoke:TC-003 |
| R-05 | TECH | downloads:TC-032, downloads:TC-033, downloads:TC-034, downloads:TC-035, downloads:TC-036, downloads:TC-037, downloads:TC-038, downloads:TC-039 |
| R-06 | BUS | browser:TC-094, library:TC-027, library:TC-028, library:TC-029, library:TC-030, library:TC-031, library:TC-060, library:TC-061, library:TC-062, library:TC-063, library:TC-064, library:TC-065, visibility:TC-013, visibility:TC-014, visibility:TC-015, visibility:TC-092, visibility:TC-093, visibility:TC-095 |
| R-07 | OPS | риск не покрыт дизайном |
| R-08 | TECH | tabs:TC-022, tabs:TC-023, tabs:TC-024, tabs:TC-025, tabs:TC-026, tabs:TC-084 |
| R-11 | TECH | browser:TC-050, browser:TC-051, browser:TC-052, browser:TC-053, browser:TC-054, browser:TC-055, browser:TC-057, browser:TC-058, settings:TC-047, settings:TC-048, settings:TC-049, settings:TC-059 |
| R-09 | BUS | filter-profiles:TC-040, filter-profiles:TC-041, filter-profiles:TC-042, filter-profiles:TC-085, filter-profiles:TC-086 |
| R-10 | DATA | library:TC-089, rating:TC-043, rating:TC-044, rating:TC-045, rating:TC-056, rating:TC-087, rating:TC-088, rating:TC-090, rating:TC-091 |
| R-12 | PERF | performance:TC-096, performance:TC-097, performance:TC-098, performance:TC-099 |
| R-13 | A11Y | риск не покрыт дизайном |
| R-14 | COMPAT | риск не покрыт дизайном |
| R-15 | SEC | риск не покрыт дизайном |

## Фичи → покрытие

| Фича | Экран | Кейсы |
|---|---|---|
| browse-tab-limit-max | browse | tabs:TC-022[Automated], performance:TC-099[Approved] |
| browse-tab-close-undo | browse | tabs:TC-023[Automated], performance:TC-099[Approved] |
| browse-tab-undo-history-limit | browse | tabs:TC-024[Automated] |
| browse-tab-list-persistence | browse | tabs:TC-025[Automated] |
| browse-tab-open-background-link | browse | tabs:TC-026[Automated] |
| browse-tab-switch-active | browse | tabs:TC-084[Automated] |
| browse-deep-link-new-tab | browse | нет кейсов |
| browse-deep-link-reuse-home-tab | browse | нет кейсов |
| browse-scroll-restore | browse | tabs:TC-025[Automated] |
| browse-infinite-scroll | browse | нет кейсов |
| browse-tap-to-scroll | browse | нет кейсов |
| browse-tap-fullscreen | browse | нет кейсов |
| browse-pinch-font | browse | browser:TC-053[Automated] |
| browse-two-finger-brightness | browse | browser:TC-055[Automated] |
| browse-bridge-injection | browse | canary:TC-066[Automated], canary:TC-067[Automated], canary:TC-068[Automated], canary:TC-069[Automated] |
| browse-tabstrip-indicators | browse | нет кейсов |
| browse-bottombar-nav | browse | smoke:TC-002[Automated], performance:TC-098[Approved] |
| sidepanel-home | side-panel | browser:TC-057[Automated] |
| sidepanel-theme-toggle | side-panel | browser:TC-050[Automated] |
| sidepanel-font-size | side-panel | browser:TC-051[Automated], browser:TC-052[Automated] |
| sidepanel-fullscreen-toggle | side-panel | browser:TC-058[Automated] |
| sidepanel-rating-filters | side-panel | browser:TC-094[Automated], visibility:TC-095[Automated] |
| sidepanel-settings-sync-theme-font | side-panel | browser:TC-054[Automated] |
| sidepanel-settings-sync-hidden-ratings | side-panel | browser:TC-094[Automated] |
| library-tabs-six | library | smoke:TC-003[Automated], library:TC-006[Automated], library:TC-016[Automated], library:TC-017[Automated], rating:TC-043[Automated] |
| library-filter-wordcount | library | library:TC-027[Automated] |
| library-filter-fandom | library | library:TC-029[Automated] |
| library-filter-downloaded-only | library | library:TC-028[Automated] |
| library-filter-freetext | library | library:TC-061[Automated] |
| library-filter-tags-and | library | library:TC-060[Automated] |
| library-sort-last-read | library | library:TC-062[Automated] |
| library-sort-wordcount | library | library:TC-030[Automated], library:TC-031[Automated], library:TC-063[Automated] |
| library-sort-author | library | library:TC-064[Automated] |
| library-sort-rating-files | library | library:TC-065[Automated] |
| library-sort-scroll-reset | library | library:TC-030[Automated], library:TC-063[Automated] |
| library-card-open-work | library | нет кейсов |
| library-card-download | library | downloads:TC-033[Automated] |
| library-card-open-file | library | downloads:TC-034[Automated] |
| library-card-delete-file | library | downloads:TC-035[Automated] |
| library-card-delete-work | library | downloads:TC-036[Automated] |
| library-card-comment-tags | library | library:TC-089[Automated] |
| settings-theme-mode | settings | smoke:TC-005[Automated], settings:TC-047[Automated], settings:TC-049[Automated], settings:TC-059[Automated] |
| settings-webview-dark-mode | settings | settings:TC-048[Automated], browser:TC-050[Automated], settings:TC-059[Automated] |
| settings-font-slider | settings | нет кейсов |
| settings-brightness-slider | settings | нет кейсов |
| settings-rating-visibility-filter | settings | visibility:TC-015[Automated], visibility:TC-095[Automated] |
| settings-filter-display-mode | settings | visibility:TC-093[Automated] |
| settings-panel-side | settings | нет кейсов |
| settings-tap-to-scroll-toggle | settings | нет кейсов |
| settings-infinite-scroll-toggle | settings | нет кейсов |
| settings-auto-download-favorite | settings | нет кейсов |
| settings-download-folder-saf | settings | downloads:TC-038[Automated] |
| settings-backup-export | settings | backup:TC-021[Automated] |
| settings-restore-merge | settings | backup:TC-021[Automated] |
| settings-orphan-scan-silent | settings | downloads:TC-038[Automated] |
| settings-orphan-scan-restore-dialog | settings | downloads:TC-039[Automated] |
| settings-scan-downloads-manual | settings | downloads:TC-037[Automated] |
| settings-filter-profiles-list | settings | нет кейсов |
| settings-filter-profiles-delete | settings | filter-profiles:TC-042[Automated] |
| settings-filter-profiles-rename | settings | filter-profiles:TC-085[Automated], filter-profiles:TC-086[Automated] |
| browser-filter-profile-save | ao3-bridge | filter-profiles:TC-040[Automated], canary:TC-082[Automated], canary:TC-083[Automated] |
| browser-filter-profile-apply | browse | filter-profiles:TC-041[Automated] |
| browser-error-page | browse | errors:TC-046[Automated] |
| bridge-tag-highlight | ao3-bridge | rating:TC-056[Automated] |
| browse-initial-load | browse | smoke:TC-001[Automated], performance:TC-096[Approved], performance:TC-097[Approved], performance:TC-098[Approved] |
| rating-overlay-five-options | rating-notes | rating:TC-007[Automated], rating:TC-009[Automated], performance:TC-098[Approved] |
| rating-deselect-on-tap | rating-notes | rating:TC-008[Automated] |
| rating-comment-save | rating-notes | rating:TC-087[Automated] |
| rating-comment-clear | rating-notes | rating:TC-088[Automated] |
| rating-tags-chip-add | rating-notes | rating:TC-090[Automated] |
| rating-tags-chip-remove | rating-notes | rating:TC-091[Automated] |
| rating-entry-work-panel | rating-notes | rating:TC-007[Automated], rating:TC-008[Automated], rating:TC-010[Automated] |
| rating-entry-listing-overlay | rating-notes | rating:TC-009[Automated], rating:TC-011[Automated] |
| rating-note-button-listing | rating-notes | rating:TC-044[Automated] |
| bridge-rate-note-tag-buttons | ao3-bridge | canary:TC-068[Automated], canary:TC-069[Automated], canary:TC-070[Automated], canary:TC-071[Automated], canary:TC-072[Automated], canary:TC-073[Automated], canary:TC-074[Automated], canary:TC-075[Automated], canary:TC-076[Automated], canary:TC-077[Automated] |
| bridge-badge-sync-multi | ao3-bridge | rating:TC-012[Automated] |
| bridge-hide-filter | ao3-bridge | visibility:TC-013[Automated], visibility:TC-014[Automated], visibility:TC-015[Automated], rating:TC-043[Automated], rating:TC-045[Automated] |
| bridge-dim-filter | ao3-bridge | visibility:TC-092[Automated] |
| bridge-main-pairing-filter | ao3-bridge | canary:TC-078[Automated], canary:TC-079[Approved] |
| bridge-exclude-main-pairing-filter | ao3-bridge | canary:TC-080[Automated], canary:TC-081[Automated] |
| bridge-dark-css | ao3-bridge | нет кейсов |
| bridge-scroll-reporting | ao3-bridge | нет кейсов |
| data-workrating-model | data | нет кейсов |
| data-filterprofile-model | data | нет кейсов |
| data-clear-all-ratings | data | smoke:TC-004[Automated], settings:TC-018[Automated], settings:TC-019[Automated], settings:TC-020[Blocked] |
| background-download-repository | background | downloads:TC-032[Automated], downloads:TC-033[Automated] |
| background-auto-download-trigger | background | downloads:TC-032[Automated] |

## Фичи без единого кейса

- browse-deep-link-new-tab (browse): Deep link открывает URL в НОВОЙ вкладке, если уже есть вкладки помимо одинокой AO3 root
- browse-deep-link-reuse-home-tab (browse): Deep link переиспользует единственную вкладку на AO3 root (HOME_URL), навигируя её на URL вместо создания новой
- browse-infinite-scroll (browse): Бесконечная подгрузка следующих страниц листинга при скролле
- browse-tap-to-scroll (browse): Тап по верхней/нижней трети страницы работы скроллит вверх/вниз
- browse-tap-fullscreen (browse): Тап по средней трети страницы работы переключает fullscreen (toggleFullscreen)
- browse-tabstrip-indicators (browse): TabStrip: индикация активной вкладки, закрытие свайпом вверх, кнопка New tab
- library-card-open-work (library): Тап по телу карточки Library открывает работу (URL) в браузерной вкладке
- settings-font-slider (settings): Слайдер размера шрифта (7 ступеней, 100–190%)
- settings-brightness-slider (settings): Слайдер яркости (overlay при v<0, reset-on-start)
- settings-panel-side (settings): Позиция side panel Left/Right
- settings-tap-to-scroll-toggle (settings): Тумблер Tap to scroll (work pages)
- settings-infinite-scroll-toggle (settings): Тумблер Infinite scroll (listing pages)
- settings-auto-download-favorite (settings): Тумблер авто-скачивания HTML при рейтинге Favorite (SAVE)
- settings-filter-profiles-list (settings): Список сохранённых AO3-фильтр-профилей
- bridge-dark-css (ao3-bridge): CSS-переопределения тёмной темы на AO3-страницах (window.__ao3AppDark)
- bridge-scroll-reporting (ao3-bridge): Отчёт позиции скролла и прогресса чтения (глава/%) в Kotlin
- data-workrating-model (data): Room-сущность WorkRating (rating/comment/tags/fandom/author/wordCount/downloadPath)
- data-filterprofile-model (data): Room-сущность FilterProfile (name/queryString)

## Области

### backup

- coverage_status: **designed-full** (1/1 Automated)
- риски: R-01
- кейсы без risk: нет
- P0/P1 не в Automated: нет
- автотесты (automated_by): framework/tests/test_backup_restore.py::test_backup_clear_restore_returns_original_data
- last_green_run: RUN-20260702-0300 (suite: smoke, status: Closed, updated: 2026-07-02T03:35:00Z) — деградировано до ГЛОБАЛЬНОГО прогона: схемы (test-case/run) не связывают run с конкретным TC ИЛИ с областью (нет поля run↔TC/area), см. отчёт builder'а

| Priority | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| P0 |  |  |  | 1 |  |
| P1 |  |  |  |  |  |
| P2 |  |  |  |  |  |
| P3 |  |  |  |  |  |

### browser

- coverage_status: **designed-full** (9/9 Automated)
- риски: R-06, R-11
- кейсы без risk: нет
- P0/P1 не в Automated: нет
- автотесты (automated_by): framework/tests/test_side_panel.py::test_font_buttons_disabled_at_range_boundaries, framework/tests/test_side_panel.py::test_font_size_increase_instant_and_persists, framework/tests/test_side_panel.py::test_pinch_spread_changes_font_size, framework/tests/test_side_panel.py::test_side_panel_and_settings_share_theme_and_font_state, framework/tests/test_side_panel.py::test_side_panel_contrast_toggles_theme_instantly, framework/tests/test_side_panel.py::test_side_panel_fullscreen_hides_tabstrip_and_toggles_label, framework/tests/test_side_panel.py::test_side_panel_home_navigates_active_tab_to_ao3_root, framework/tests/test_side_panel.py::test_side_panel_toggle_kudosed_hides_and_syncs_settings, framework/tests/test_side_panel.py::test_two_finger_drag_changes_brightness
- last_green_run: RUN-20260702-0300 (suite: smoke, status: Closed, updated: 2026-07-02T03:35:00Z) — деградировано до ГЛОБАЛЬНОГО прогона: схемы (test-case/run) не связывают run с конкретным TC ИЛИ с областью (нет поля run↔TC/area), см. отчёт builder'а

| Priority | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| P0 |  |  |  |  |  |
| P1 |  |  |  | 7 |  |
| P2 |  |  |  |  |  |
| P3 |  |  |  | 2 |  |

### canary

- coverage_status: **partial** (17/18 Automated)
- риски: R-02, R-02/R-04
- кейсы без risk: нет
- P0/P1 не в Automated: TC-079 [P0, Approved]
- автотесты (automated_by): framework/tests/canary/test_ao3_selectors.py::test_bridge_marker_present_live, framework/tests/canary/test_ao3_selectors.py::test_bridge_marker_present_replay, framework/tests/canary/test_ao3_selectors.py::test_exclude_main_pairing_checkbox_availability_live, framework/tests/canary/test_ao3_selectors.py::test_exclude_main_pairing_checkbox_availability_replay, framework/tests/canary/test_ao3_selectors.py::test_main_pairing_checkbox_availability_live, framework/tests/canary/test_ao3_selectors.py::test_main_pairing_checkbox_availability_replay, framework/tests/canary/test_ao3_selectors.py::test_note_button_present_iff_comment_live, framework/tests/canary/test_ao3_selectors.py::test_note_button_present_iff_comment_replay, framework/tests/canary/test_ao3_selectors.py::test_rate_button_badge_opaque_color_live, framework/tests/canary/test_ao3_selectors.py::test_rate_button_badge_opaque_color_replay, framework/tests/canary/test_ao3_selectors.py::test_rate_button_injected_on_live_listing, framework/tests/canary/test_ao3_selectors.py::test_rate_button_injected_on_replay_listing, framework/tests/canary/test_ao3_selectors.py::test_save_filter_button_idempotent_live, framework/tests/canary/test_ao3_selectors.py::test_save_filter_button_idempotent_replay, framework/tests/canary/test_ao3_selectors.py::test_tag_button_present_iff_custom_tag_live, framework/tests/canary/test_ao3_selectors.py::test_tag_button_present_iff_custom_tag_replay, framework/tests/canary/test_ao3_selectors.py::test_work_blurb_selector_matches_live_listing, framework/tests/canary/test_ao3_selectors.py::test_work_blurb_selector_matches_replay_listing
- last_green_run: RUN-20260702-0300 (suite: smoke, status: Closed, updated: 2026-07-02T03:35:00Z) — деградировано до ГЛОБАЛЬНОГО прогона: схемы (test-case/run) не связывают run с конкретным TC ИЛИ с областью (нет поля run↔TC/area), см. отчёт builder'а

| Priority | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| P0 |  |  | 1 | 17 |  |
| P1 |  |  |  |  |  |
| P2 |  |  |  |  |  |
| P3 |  |  |  |  |  |

### downloads

- coverage_status: **designed-full** (8/8 Automated)
- риски: R-05
- кейсы без risk: нет
- P0/P1 не в Automated: нет
- автотесты (automated_by): framework/tests/test_downloads.py::test_auto_download_triggers_on_loved_rating, framework/tests/test_downloads.py::test_change_download_folder_triggers_silent_scan_and_relinks_orphan_file, framework/tests/test_downloads.py::test_delete_downloaded_file_keeps_rating_row, framework/tests/test_downloads.py::test_delete_work_removes_row_and_file, framework/tests/test_downloads.py::test_manual_download_from_library_adds_local_file, framework/tests/test_downloads.py::test_manual_scan_for_downloads_shows_dialog_on_zero_files, framework/tests/test_downloads.py::test_open_downloaded_file_applies_viewport_and_reader_css, framework/tests/test_downloads.py::test_restore_folds_orphan_scan_into_single_dialog
- last_green_run: RUN-20260702-0300 (suite: smoke, status: Closed, updated: 2026-07-02T03:35:00Z) — деградировано до ГЛОБАЛЬНОГО прогона: схемы (test-case/run) не связывают run с конкретным TC ИЛИ с областью (нет поля run↔TC/area), см. отчёт builder'а

| Priority | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| P0 |  |  |  |  |  |
| P1 |  |  |  | 5 |  |
| P2 |  |  |  | 2 |  |
| P3 |  |  |  | 1 |  |

### errors

- coverage_status: **designed-full** (1/1 Automated)
- риски: R-03 (частично, TECH)
- кейсы без risk: нет
- P0/P1 не в Automated: нет
- автотесты (automated_by): framework/tests/test_errors.py::test_main_frame_load_error_shows_custom_error_page_with_retry
- last_green_run: RUN-20260702-0300 (suite: smoke, status: Closed, updated: 2026-07-02T03:35:00Z) — деградировано до ГЛОБАЛЬНОГО прогона: схемы (test-case/run) не связывают run с конкретным TC ИЛИ с областью (нет поля run↔TC/area), см. отчёт builder'а

| Priority | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| P0 |  |  |  |  |  |
| P1 |  |  |  |  |  |
| P2 |  |  |  | 1 |  |
| P3 |  |  |  |  |  |

### filter-profiles

- coverage_status: **designed-full** (5/5 Automated)
- риски: R-09
- кейсы без risk: нет
- P0/P1 не в Automated: нет
- автотесты (automated_by): framework/tests/test_filter_profiles.py::test_apply_filter_profile, framework/tests/test_filter_profiles.py::test_delete_filter_profile, framework/tests/test_filter_profiles.py::test_rename_filter_profile_keeps_query_string, framework/tests/test_filter_profiles.py::test_rename_filter_profile_to_duplicate_name, framework/tests/test_filter_profiles.py::test_save_filter_profile
- last_green_run: RUN-20260702-0300 (suite: smoke, status: Closed, updated: 2026-07-02T03:35:00Z) — деградировано до ГЛОБАЛЬНОГО прогона: схемы (test-case/run) не связывают run с конкретным TC ИЛИ с областью (нет поля run↔TC/area), см. отчёт builder'а

| Priority | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| P0 |  |  |  |  |  |
| P1 |  |  |  | 5 |  |
| P2 |  |  |  |  |  |
| P3 |  |  |  |  |  |

### library

- coverage_status: **designed-full** (15/15 Automated)
- риски: R-04, R-06, R-10
- кейсы без risk: TC-006
- P0/P1 не в Automated: нет
- автотесты (automated_by): framework/tests/test_library.py::test_change_rating_moves_work_between_tabs, framework/tests/test_library.py::test_comment_only_not_in_any_rating_tab, framework/tests/test_library.py::test_library_card_shows_note_icon_and_tags, framework/tests/test_library.py::test_library_tab_labels, framework/tests/test_library_filters.py::test_library_filter_by_fandom, framework/tests/test_library_filters.py::test_library_filter_downloaded_only, framework/tests/test_library_filters.py::test_library_filter_freetext_search, framework/tests/test_library_filters.py::test_library_filter_tags_and_semantics, framework/tests/test_library_filters.py::test_library_filter_word_count_range, framework/tests/test_library_filters.py::test_library_sort_author_asc_blank_last, framework/tests/test_library_filters.py::test_library_sort_last_read_default, framework/tests/test_library_filters.py::test_library_sort_rating_files_tab_only, framework/tests/test_library_filters.py::test_library_sort_wordcount_asc_resets_scroll, framework/tests/test_library_filters.py::test_library_sort_wordcount_desc_resets_scroll, framework/tests/test_library_filters.py::test_library_sort_wordcount_null_last
- last_green_run: RUN-20260702-0300 (suite: smoke, status: Closed, updated: 2026-07-02T03:35:00Z) — деградировано до ГЛОБАЛЬНОГО прогона: схемы (test-case/run) не связывают run с конкретным TC ИЛИ с областью (нет поля run↔TC/area), см. отчёт builder'а

| Priority | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| P0 |  |  |  | 2 |  |
| P1 |  |  |  | 10 |  |
| P2 |  |  |  | 2 |  |
| P3 |  |  |  | 1 |  |

### performance

- coverage_status: **none** (0/4 Automated)
- риски: R-12
- кейсы без risk: нет
- P0/P1 не в Automated: TC-096 [P1, Approved], TC-097 [P1, Approved], TC-098 [P0, Approved], TC-099 [P0, Approved]
- автотесты (automated_by): —
- last_green_run: RUN-20260702-0300 (suite: smoke, status: Closed, updated: 2026-07-02T03:35:00Z) — деградировано до ГЛОБАЛЬНОГО прогона: схемы (test-case/run) не связывают run с конкретным TC ИЛИ с областью (нет поля run↔TC/area), см. отчёт builder'а

| Priority | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| P0 |  |  | 2 |  |  |
| P1 |  |  | 2 |  |  |
| P2 |  |  |  |  |  |
| P3 |  |  |  |  |  |

### rating

- coverage_status: **designed-full** (14/14 Automated)
- риски: R-04, R-10
- кейсы без risk: нет
- P0/P1 не в Automated: нет
- автотесты (automated_by): framework/tests/test_rating.py::test_deselect_rating_on_work_page_panel, framework/tests/test_rating.py::test_rate_work_from_work_page_panel, framework/tests/test_rating_listing.py::test_add_freeform_tag_persists, framework/tests/test_rating_listing.py::test_apply_ratings_syncs_duplicate_blurbs, framework/tests/test_rating_listing.py::test_clear_note_removes_comment, framework/tests/test_rating_listing.py::test_comment_only_visible_on_listing_and_absent_from_rating_tabs, framework/tests/test_rating_listing.py::test_listing_rate_button_updates_without_reload, framework/tests/test_rating_listing.py::test_matching_personal_tag_highlighted_on_listing, framework/tests/test_rating_listing.py::test_note_button_opens_overlay_with_expanded_comment, framework/tests/test_rating_listing.py::test_panel_rating_updates_without_reload, framework/tests/test_rating_listing.py::test_personal_tags_do_not_affect_visibility, framework/tests/test_rating_listing.py::test_rate_work_from_listing_overlay, framework/tests/test_rating_listing.py::test_save_note_persists_comment, framework/tests/test_rating_listing.py::test_tap_selected_chip_removes_tag
- last_green_run: RUN-20260702-0300 (suite: smoke, status: Closed, updated: 2026-07-02T03:35:00Z) — деградировано до ГЛОБАЛЬНОГО прогона: схемы (test-case/run) не связывают run с конкретным TC ИЛИ с областью (нет поля run↔TC/area), см. отчёт builder'а

| Priority | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| P0 |  |  |  | 3 |  |
| P1 |  |  |  | 7 |  |
| P2 |  |  |  | 3 |  |
| P3 |  |  |  | 1 |  |

### settings

- coverage_status: **partial** (6/7 Automated)
- риски: R-01, R-11
- кейсы без risk: нет
- P0/P1 не в Automated: нет
- автотесты (automated_by): framework/tests/test_settings.py::test_cancel_clear_all_dialog_keeps_data, framework/tests/test_settings.py::test_clear_all_ratings_shows_confirmation_dialog, framework/tests/test_settings.py::test_system_theme_follows_os_dark_mode, framework/tests/test_settings.py::test_theme_dark_applies_instantly_without_recreating_activity, framework/tests/test_settings.py::test_webview_dark_mode_applies_instantly, framework/tests/test_settings.py::test_webview_follows_system_theme_without_in_app_toggle
- last_green_run: RUN-20260702-0300 (suite: smoke, status: Closed, updated: 2026-07-02T03:35:00Z) — деградировано до ГЛОБАЛЬНОГО прогона: схемы (test-case/run) не связывают run с конкретным TC ИЛИ с областью (нет поля run↔TC/area), см. отчёт builder'а

| Priority | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| P0 |  |  |  |  |  |
| P1 |  |  |  | 3 |  |
| P2 |  |  |  | 3 |  |
| P3 |  |  |  |  | 1 |

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

- coverage_status: **designed-full** (6/6 Automated)
- риски: R-08
- кейсы без risk: нет
- P0/P1 не в Automated: нет
- автотесты (automated_by): framework/tests/test_tabs.py::test_long_press_link_opens_background_tab_without_switching, framework/tests/test_tabs.py::test_max_tabs_limit_blocks_11th_tab, framework/tests/test_tabs.py::test_swipe_close_undo_restores_position, framework/tests/test_tabs.py::test_tabs_persist_url_and_scroll_after_restart, framework/tests/test_tabs.py::test_tap_inactive_tab_chip_activates_it, framework/tests/test_tabs.py::test_undo_history_evicts_oldest_after_six_closes
- last_green_run: RUN-20260702-0300 (suite: smoke, status: Closed, updated: 2026-07-02T03:35:00Z) — деградировано до ГЛОБАЛЬНОГО прогона: схемы (test-case/run) не связывают run с конкретным TC ИЛИ с областью (нет поля run↔TC/area), см. отчёт builder'а

| Priority | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| P0 |  |  |  |  |  |
| P1 |  |  |  | 5 |  |
| P2 |  |  |  |  |  |
| P3 |  |  |  | 1 |  |

### visibility

- coverage_status: **designed-full** (6/6 Automated)
- риски: R-06
- кейсы без risk: нет
- P0/P1 не в Automated: нет
- автотесты (automated_by): framework/tests/test_visibility.py::test_dim_mode_dims_hidden_rating_blurb, framework/tests/test_visibility.py::test_disliked_hidden_on_listing, framework/tests/test_visibility.py::test_disliked_visible_after_hide_toggle_off, framework/tests/test_visibility.py::test_display_mode_hide_to_dim_live_push, framework/tests/test_visibility.py::test_hide_kudosed_only_excludes_kudosed, framework/tests/test_visibility.py::test_no_rating_or_comment_only_never_hidden
- last_green_run: RUN-20260702-0300 (suite: smoke, status: Closed, updated: 2026-07-02T03:35:00Z) — деградировано до ГЛОБАЛЬНОГО прогона: схемы (test-case/run) не связывают run с конкретным TC ИЛИ с областью (нет поля run↔TC/area), см. отчёт builder'а

| Priority | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| P0 |  |  |  | 3 |  |
| P1 |  |  |  | 3 |  |
| P2 |  |  |  |  |  |
| P3 |  |  |  |  |  |

