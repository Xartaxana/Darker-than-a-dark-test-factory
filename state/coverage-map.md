# Карта покрытия (генерируется, НЕ редактировать руками)

generated_at: 2026-08-05T09:58:22Z · генератор: `scripts/coverage_map.py`
Проекция из frontmatter test-cases/ и runs/ (принцип G1, как у `state/factory-status.md`). Рукописной модели покрытия не существует — этот файл не второй источник истины, а вывод.

⚠ реестр фич протух: сборка bfc8f41a21812f12cd790ebfc7121586844468ca, реестр инвентаризован против 63f6aac3b1ea1dfad82f68b8196aa6cf56f41853

## Сводка по областям

| Область | Кейсов | Automated | coverage_status |
|---|---|---|---|
| accessibility | 6 | 3 | partial |
| backup | 7 | 1 | partial |
| browser | 19 | 13 | partial |
| canary | 23 | 23 | designed-full |
| compatibility | 3 | 3 | designed-full |
| downloads | 18 | 14 | partial |
| errors | 1 | 1 | designed-full |
| filter-profiles | 5 | 5 | designed-full |
| library | 17 | 17 | designed-full |
| performance | 4 | 4 | designed-full |
| rating | 24 | 20 | partial |
| security | 6 | 6 | designed-full |
| settings | 17 | 11 | partial |
| smoke | 5 | 5 | designed-full |
| tabs | 11 | 11 | designed-full |
| visibility | 6 | 6 | designed-full |

## Риски (docs/01-test-strategy.md §5) → покрытие

| Риск | Категория | Покрывающие кейсы |
|---|---|---|
| R-01 | DATA | backup:TC-021, backup:TC-165, backup:TC-167, backup:TC-168, backup:TC-171, backup:TC-172, rating:TC-151, rating:TC-152, rating:TC-155, settings:TC-018, settings:TC-019, settings:TC-020, smoke:TC-004 |
| R-02 | TECH | canary:TC-066, canary:TC-067, canary:TC-068, canary:TC-069, canary:TC-070, canary:TC-071, canary:TC-072, canary:TC-073, canary:TC-074, canary:TC-075, canary:TC-076, canary:TC-077, canary:TC-078, canary:TC-079, canary:TC-080, canary:TC-081, canary:TC-082, canary:TC-083, canary:TC-118, canary:TC-119, canary:TC-120, canary:TC-121, canary:TC-122 |
| R-03 | TECH | errors:TC-046, smoke:TC-001 |
| R-04 | DATA | canary:TC-072, canary:TC-073, canary:TC-074, canary:TC-075, canary:TC-076, canary:TC-077, library:TC-016, library:TC-017, rating:TC-007, rating:TC-008, rating:TC-009, rating:TC-010, rating:TC-011, rating:TC-012, smoke:TC-003 |
| R-05 | TECH | downloads:TC-032, downloads:TC-033, downloads:TC-034, downloads:TC-035, downloads:TC-036, downloads:TC-037, downloads:TC-038, downloads:TC-039, downloads:TC-112, downloads:TC-113, downloads:TC-114, downloads:TC-115, downloads:TC-116, downloads:TC-117, downloads:TC-153, downloads:TC-154, downloads:TC-164 |
| R-06 | BUS | browser:TC-094, library:TC-027, library:TC-028, library:TC-029, library:TC-030, library:TC-031, library:TC-060, library:TC-061, library:TC-062, library:TC-063, library:TC-064, library:TC-065, visibility:TC-013, visibility:TC-014, visibility:TC-015, visibility:TC-092, visibility:TC-093, visibility:TC-095 |
| R-07 | OPS | риск не покрыт дизайном |
| R-08 | TECH | library:TC-136, library:TC-137, tabs:TC-022, tabs:TC-023, tabs:TC-024, tabs:TC-025, tabs:TC-026, tabs:TC-084, tabs:TC-131, tabs:TC-132, tabs:TC-133, tabs:TC-134, tabs:TC-135 |
| R-11 | TECH | accessibility:TC-108, browser:TC-050, browser:TC-051, browser:TC-052, browser:TC-053, browser:TC-054, browser:TC-055, browser:TC-057, browser:TC-058, browser:TC-126, browser:TC-127, browser:TC-128, browser:TC-130, browser:TC-157, browser:TC-158, browser:TC-159, browser:TC-160, browser:TC-161, settings:TC-047, settings:TC-048, settings:TC-049, settings:TC-059, settings:TC-123, settings:TC-124, settings:TC-125, settings:TC-129, settings:TC-145, settings:TC-146, settings:TC-147, settings:TC-163, settings:TC-169, settings:TC-170 |
| R-09 | BUS | backup:TC-166, filter-profiles:TC-040, filter-profiles:TC-041, filter-profiles:TC-042, filter-profiles:TC-085, filter-profiles:TC-086 |
| R-10 | DATA | library:TC-089, rating:TC-043, rating:TC-044, rating:TC-045, rating:TC-056, rating:TC-087, rating:TC-088, rating:TC-090, rating:TC-091 |
| R-12 | PERF | performance:TC-096, performance:TC-097, performance:TC-098, performance:TC-099 |
| R-13 | A11Y | accessibility:TC-106, accessibility:TC-107, accessibility:TC-148, accessibility:TC-149, accessibility:TC-150 |
| R-14 | COMPAT | compatibility:TC-109, compatibility:TC-110, compatibility:TC-111 |
| R-15 | SEC | security:TC-100, security:TC-101, security:TC-102, security:TC-103, security:TC-104, security:TC-105 |
| R-16 | BUS | browser:TC-162, downloads:TC-156 |
| R-17 | BUS | rating:TC-138, rating:TC-139, rating:TC-140, rating:TC-141, rating:TC-142, rating:TC-143, rating:TC-144 |

## Фичи → покрытие

| Фича | Экран | Кейсы |
|---|---|---|
| browse-tab-limit-max | browse | tabs:TC-022[Automated] |
| browse-tab-close-undo | browse | tabs:TC-023[Automated] |
| browse-tab-undo-history-limit | browse | tabs:TC-024[Automated] |
| browse-tab-list-persistence | browse | tabs:TC-025[Automated] |
| browse-tab-open-background-link | browse | tabs:TC-026[Automated] |
| browse-tab-switch-active | browse | tabs:TC-084[Automated] |
| browse-deep-link-new-tab | browse | tabs:TC-131[Automated], tabs:TC-133[Automated], tabs:TC-134[Automated] |
| browse-deep-link-reuse-home-tab | browse | tabs:TC-132[Automated], tabs:TC-135[Automated] |
| browse-scroll-restore | browse | tabs:TC-025[Automated] |
| browse-infinite-scroll | browse | browser:TC-130[Automated], browser:TC-157[Review], browser:TC-158[Review], browser:TC-159[Review], browser:TC-160[Review], browser:TC-162[Review] |
| browse-tap-to-scroll | browse | browser:TC-126[Automated], browser:TC-127[Automated] |
| browse-tap-fullscreen | browse | browser:TC-128[Automated] |
| browse-pinch-font | browse | browser:TC-053[Automated] |
| browse-two-finger-brightness | browse | browser:TC-055[Automated] |
| browse-bridge-injection | browse | canary:TC-066[Automated], canary:TC-067[Automated], canary:TC-068[Automated], canary:TC-069[Automated] |
| browse-tabstrip-indicators | browse | нет кейсов |
| browse-bottombar-nav | browse | smoke:TC-002[Automated] |
| sidepanel-home | side-panel | browser:TC-057[Automated] |
| sidepanel-theme-toggle | side-panel | browser:TC-050[Automated] |
| sidepanel-font-size | side-panel | browser:TC-051[Automated], browser:TC-052[Automated] |
| sidepanel-fullscreen-toggle | side-panel | browser:TC-058[Automated] |
| sidepanel-rating-filters | side-panel | browser:TC-094[Automated], visibility:TC-095[Automated] |
| sidepanel-settings-sync-theme-font | side-panel | browser:TC-054[Automated] |
| sidepanel-settings-sync-hidden-ratings | side-panel | browser:TC-094[Automated] |
| library-tabs-six | library | smoke:TC-003[Automated], library:TC-006[Automated], library:TC-016[Automated], library:TC-017[Automated], rating:TC-043[Automated], downloads:TC-156[Review] |
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
| library-card-open-work | library | library:TC-136[Automated], library:TC-137[Automated] |
| library-card-download | library | downloads:TC-033[Automated] |
| library-card-open-file | library | downloads:TC-034[Automated], downloads:TC-156[Review] |
| library-card-delete-file | library | downloads:TC-035[Automated], downloads:TC-154[Review] |
| library-card-delete-work | library | downloads:TC-036[Automated] |
| library-card-comment-tags | library | library:TC-089[Automated] |
| settings-theme-mode | settings | smoke:TC-005[Automated], settings:TC-047[Automated], settings:TC-049[Automated], settings:TC-059[Automated] |
| settings-webview-dark-mode | settings | settings:TC-048[Automated], browser:TC-050[Automated], settings:TC-059[Automated] |
| settings-font-slider | settings | settings:TC-145[Review] |
| settings-brightness-slider | settings | settings:TC-146[Review] |
| settings-brightness-reset-on-start | settings | settings:TC-169[Review], settings:TC-170[Review] |
| settings-rating-visibility-filter | settings | visibility:TC-015[Automated], visibility:TC-095[Automated] |
| settings-filter-display-mode | settings | visibility:TC-093[Automated] |
| settings-panel-side | settings | settings:TC-147[Review] |
| settings-tap-to-scroll-toggle | settings | settings:TC-123[Automated], settings:TC-124[Automated], settings:TC-125[Automated], settings:TC-163[Review] |
| settings-infinite-scroll-toggle | settings | settings:TC-129[Automated], browser:TC-130[Automated], browser:TC-157[Review], browser:TC-158[Review], browser:TC-161[Review] |
| settings-auto-download-favorite | settings | downloads:TC-112[Automated], downloads:TC-113[Automated] |
| settings-download-folder-saf | settings | downloads:TC-038[Automated] |
| settings-backup-export | settings | backup:TC-021[Automated], backup:TC-165[Review] |
| settings-restore-merge | settings | backup:TC-021[Automated], downloads:TC-164[Review], backup:TC-166[Review], backup:TC-167[Review], backup:TC-168[Review] |
| settings-restore-merge-skip-existing | settings | backup:TC-171[Review], backup:TC-172[Review] |
| settings-orphan-scan-silent | settings | downloads:TC-038[Automated] |
| settings-orphan-scan-restore-dialog | settings | downloads:TC-039[Automated], downloads:TC-164[Review], backup:TC-172[Review] |
| settings-scan-downloads-manual | settings | downloads:TC-037[Automated], downloads:TC-153[Review], downloads:TC-154[Review] |
| settings-filter-profiles-list | settings | backup:TC-166[Review] |
| settings-filter-profiles-delete | settings | filter-profiles:TC-042[Automated] |
| settings-filter-profiles-rename | settings | filter-profiles:TC-085[Automated], filter-profiles:TC-086[Automated] |
| browser-filter-profile-save | ao3-bridge | filter-profiles:TC-040[Automated], canary:TC-082[Automated], canary:TC-083[Automated] |
| browser-filter-profile-apply | browse | filter-profiles:TC-041[Automated] |
| browser-error-page | browse | errors:TC-046[Automated] |
| bridge-tag-highlight | ao3-bridge | rating:TC-056[Automated] |
| browse-initial-load | browse | smoke:TC-001[Automated] |
| rating-overlay-five-options | rating-notes | rating:TC-007[Automated], rating:TC-009[Automated] |
| rating-deselect-on-tap | rating-notes | rating:TC-008[Automated], rating:TC-151[Review], rating:TC-152[Review] |
| rating-comment-save | rating-notes | rating:TC-087[Automated] |
| rating-comment-clear | rating-notes | rating:TC-088[Automated] |
| rating-tags-chip-add | rating-notes | rating:TC-090[Automated], rating:TC-155[Review] |
| rating-tags-chip-remove | rating-notes | rating:TC-091[Automated] |
| rating-entry-work-panel | rating-notes | rating:TC-007[Automated], rating:TC-008[Automated], rating:TC-010[Automated], rating:TC-151[Review], rating:TC-155[Review] |
| rating-entry-listing-overlay | rating-notes | rating:TC-009[Automated], rating:TC-011[Automated], rating:TC-152[Review] |
| rating-note-button-listing | rating-notes | rating:TC-044[Automated] |
| bridge-rate-note-tag-buttons | ao3-bridge | canary:TC-068[Automated], canary:TC-069[Automated], canary:TC-070[Automated], canary:TC-071[Automated], canary:TC-072[Automated], canary:TC-073[Automated], canary:TC-074[Automated], canary:TC-075[Automated], canary:TC-076[Automated], canary:TC-077[Automated] |
| bridge-badge-sync-multi | ao3-bridge | rating:TC-012[Automated] |
| bridge-hide-filter | ao3-bridge | visibility:TC-013[Automated], visibility:TC-014[Automated], visibility:TC-015[Automated], rating:TC-043[Automated], rating:TC-045[Automated], browser:TC-159[Review], browser:TC-160[Review], browser:TC-161[Review] |
| bridge-dim-filter | ao3-bridge | visibility:TC-092[Automated] |
| bridge-main-pairing-filter | ao3-bridge | canary:TC-078[Automated], canary:TC-079[Automated] |
| bridge-exclude-main-pairing-filter | ao3-bridge | canary:TC-080[Automated], canary:TC-081[Automated] |
| bridge-dark-css | ao3-bridge | нет кейсов |
| bridge-scroll-reporting | ao3-bridge | нет кейсов |
| bridge-tap-zone-guard | ao3-bridge | canary:TC-118[Automated], canary:TC-119[Automated], canary:TC-120[Automated], canary:TC-121[Automated], canary:TC-122[Automated] |
| data-workrating-model | data | нет кейсов |
| data-filterprofile-model | data | нет кейсов |
| data-clear-all-ratings | data | smoke:TC-004[Automated], settings:TC-018[Automated], settings:TC-019[Automated], settings:TC-020[Automated] |
| background-download-repository | background | downloads:TC-032[Automated], downloads:TC-033[Automated] |
| background-auto-download-trigger | background | downloads:TC-032[Automated], downloads:TC-112[Automated], downloads:TC-114[Automated], downloads:TC-115[Automated], downloads:TC-116[Automated], downloads:TC-117[Automated] |
| background-auto-kudos-trigger | background | rating:TC-138[Automated], rating:TC-139[Approved], rating:TC-140[Automated], rating:TC-141[Automated], rating:TC-142[Automated], rating:TC-143[Automated], rating:TC-144[Automated] |
| nf-perf-cold-start-budget | non-functional | performance:TC-096[Automated] |
| nf-perf-webview-first-load-budget | non-functional | performance:TC-097[Automated] |
| nf-stability-no-crash-anr | non-functional | performance:TC-098[Automated] |
| nf-perf-memory-trend | non-functional | performance:TC-099[Automated] |
| nf-sec-exported-components | non-functional | security:TC-100[Automated] |
| nf-sec-cleartext-traffic | non-functional | security:TC-101[Automated] |
| nf-sec-js-bridge-exposure | non-functional | security:TC-102[Automated] |
| nf-sec-file-access | non-functional | security:TC-103[Automated] |
| nf-sec-backup-privacy | non-functional | security:TC-104[Automated] |
| nf-sec-logcat-leak | non-functional | security:TC-105[Automated] |
| nf-a11y-content-labels | non-functional | accessibility:TC-106[Automated] |
| nf-a11y-font-scaling | non-functional | accessibility:TC-107[Automated] |
| nf-a11y-contrast-sanity | non-functional | accessibility:TC-108[Automated] |
| nf-a11y-touch-target-size | non-functional | accessibility:TC-148[Approved] |
| nf-a11y-contrast-computed | non-functional | accessibility:TC-149[Review] |
| nf-a11y-interactive-overlap | non-functional | accessibility:TC-150[Review] |
| nf-compat-api-level | non-functional | compatibility:TC-109[Automated] |
| nf-compat-dark-light-matrix | non-functional | compatibility:TC-110[Automated] |
| nf-compat-orientation | non-functional | compatibility:TC-111[Automated] |

## Фичи без единого кейса

- browse-tabstrip-indicators (browse): TabStrip: индикация активной вкладки, закрытие свайпом вверх, кнопка New tab
- bridge-dark-css (ao3-bridge): CSS-переопределения тёмной темы на AO3-страницах (window.__ao3AppDark)
- bridge-scroll-reporting (ao3-bridge): Отчёт позиции скролла и прогресса чтения (глава/%) в Kotlin
- data-workrating-model (data): Room-сущность WorkRating (rating/comment/tags/fandom/author/wordCount/downloadPath)
- data-filterprofile-model (data): Room-сущность FilterProfile (name/queryString)

## Области

### accessibility

- coverage_status: **partial** (3/6 Automated)
- риски: R-11, R-13
- кейсы без risk: нет
- P0/P1 не в Automated: нет
- автотесты (automated_by): framework/tests/test_accessibility.py::test_contrast_sanity_dark_and_light, framework/tests/test_accessibility.py::test_font_scale_1_3_no_crash_key_controls_present, framework/tests/test_accessibility.py::test_key_controls_have_accessible_label_or_text
- last_green_run: RUN-20260702-0300 (suite: smoke, status: Closed, updated: 2026-07-02T03:35:00Z) — деградировано до ГЛОБАЛЬНОГО прогона: схемы (test-case/run) не связывают run с конкретным TC ИЛИ с областью (нет поля run↔TC/area), см. отчёт builder'а
- per-TC last green:
  - TC-106: нет зелёного per-TC
  - TC-107: нет зелёного per-TC
  - TC-108: нет зелёного per-TC

| Priority | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| P0 |  |  |  |  |  |
| P1 |  |  |  |  |  |
| P2 |  | 2 | 1 | 3 |  |
| P3 |  |  |  |  |  |

### backup

- coverage_status: **partial** (1/7 Automated)
- риски: R-01, R-09
- кейсы без risk: нет
- P0/P1 не в Automated: TC-166 [P1, Review], TC-171 [P1, Review]
- автотесты (automated_by): framework/tests/test_backup_restore.py::test_backup_clear_restore_returns_original_data
- last_green_run: RUN-20260702-0300 (suite: smoke, status: Closed, updated: 2026-07-02T03:35:00Z) — деградировано до ГЛОБАЛЬНОГО прогона: схемы (test-case/run) не связывают run с конкретным TC ИЛИ с областью (нет поля run↔TC/area), см. отчёт builder'а
- per-TC last green:
  - TC-021: RUN-20260805-0432 (updated: 2026-08-05T03:20:00Z)

| Priority | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| P0 |  |  |  | 1 |  |
| P1 |  | 2 |  |  |  |
| P2 |  | 4 |  |  |  |
| P3 |  |  |  |  |  |

### browser

- coverage_status: **partial** (13/19 Automated)
- риски: R-06, R-11, R-16
- кейсы без risk: нет
- P0/P1 не в Automated: TC-157 [P1, Review], TC-158 [P1, Review], TC-159 [P1, Review], TC-161 [P1, Review]
- автотесты (automated_by): framework/tests/test_infinite_scroll.py::test_infinite_scroll_on_loads_next_page_in_background, framework/tests/test_reading_ux.py::test_tap_zone_bottom_third_scrolls_down, framework/tests/test_reading_ux.py::test_tap_zone_middle_third_toggles_fullscreen, framework/tests/test_reading_ux.py::test_tap_zone_top_third_scrolls_up, framework/tests/test_side_panel.py::test_font_buttons_disabled_at_range_boundaries, framework/tests/test_side_panel.py::test_font_size_increase_instant_and_persists, framework/tests/test_side_panel.py::test_pinch_spread_changes_font_size, framework/tests/test_side_panel.py::test_side_panel_and_settings_share_theme_and_font_state, framework/tests/test_side_panel.py::test_side_panel_contrast_toggles_theme_instantly, framework/tests/test_side_panel.py::test_side_panel_fullscreen_hides_tabstrip_and_toggles_label, framework/tests/test_side_panel.py::test_side_panel_home_navigates_active_tab_to_ao3_root, framework/tests/test_side_panel.py::test_side_panel_toggle_kudosed_hides_and_syncs_settings, framework/tests/test_side_panel.py::test_two_finger_drag_changes_brightness
- last_green_run: RUN-20260702-0300 (suite: smoke, status: Closed, updated: 2026-07-02T03:35:00Z) — деградировано до ГЛОБАЛЬНОГО прогона: схемы (test-case/run) не связывают run с конкретным TC ИЛИ с областью (нет поля run↔TC/area), см. отчёт builder'а
- per-TC last green:
  - TC-050: нет зелёного per-TC
  - TC-051: нет зелёного per-TC
  - TC-052: нет зелёного per-TC
  - TC-053: нет зелёного per-TC
  - TC-054: нет зелёного per-TC
  - TC-055: нет зелёного per-TC
  - TC-057: нет зелёного per-TC
  - TC-058: нет зелёного per-TC
  - TC-094: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-126: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-127: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-128: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-130: RUN-20260803-2012 (updated: 2026-08-03T20:40:00Z)

| Priority | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| P0 |  |  |  |  |  |
| P1 |  | 4 |  | 11 |  |
| P2 |  | 2 |  |  |  |
| P3 |  |  |  | 2 |  |

### canary

- coverage_status: **designed-full** (23/23 Automated)
- риски: R-02, R-02/R-04
- кейсы без risk: нет
- P0/P1 не в Automated: нет
- автотесты (automated_by): framework/tests/canary/test_ao3_selectors.py::test_bridge_marker_present_live, framework/tests/canary/test_ao3_selectors.py::test_bridge_marker_present_replay, framework/tests/canary/test_ao3_selectors.py::test_exclude_main_pairing_checkbox_availability_live, framework/tests/canary/test_ao3_selectors.py::test_exclude_main_pairing_checkbox_availability_replay, framework/tests/canary/test_ao3_selectors.py::test_main_pairing_checkbox_availability_live, framework/tests/canary/test_ao3_selectors.py::test_main_pairing_checkbox_availability_replay, framework/tests/canary/test_ao3_selectors.py::test_no_non_whitelisted_onclick_candidates_on_live_work_page, framework/tests/canary/test_ao3_selectors.py::test_note_button_present_iff_comment_live, framework/tests/canary/test_ao3_selectors.py::test_note_button_present_iff_comment_replay, framework/tests/canary/test_ao3_selectors.py::test_rate_button_badge_opaque_color_live, framework/tests/canary/test_ao3_selectors.py::test_rate_button_badge_opaque_color_replay, framework/tests/canary/test_ao3_selectors.py::test_rate_button_injected_on_live_listing, framework/tests/canary/test_ao3_selectors.py::test_rate_button_injected_on_replay_listing, framework/tests/canary/test_ao3_selectors.py::test_save_filter_button_idempotent_live, framework/tests/canary/test_ao3_selectors.py::test_save_filter_button_idempotent_replay, framework/tests/canary/test_ao3_selectors.py::test_tag_button_present_iff_custom_tag_live, framework/tests/canary/test_ao3_selectors.py::test_tag_button_present_iff_custom_tag_replay, framework/tests/canary/test_ao3_selectors.py::test_work_blurb_selector_matches_live_listing, framework/tests/canary/test_ao3_selectors.py::test_work_blurb_selector_matches_replay_listing, framework/tests/canary/test_tap_zone_guard.py::test_tap_zone_guard_blocks_whitelisted_button, framework/tests/canary/test_tap_zone_guard.py::test_tap_zone_guard_closest_semantics_on_descendant, framework/tests/canary/test_tap_zone_guard.py::test_tap_zone_guard_pierced_by_non_whitelisted_div, framework/tests/canary/test_tap_zone_guard.py::test_tap_zone_guard_whitelisted_link_without_own_handler
- last_green_run: RUN-20260702-0300 (suite: smoke, status: Closed, updated: 2026-07-02T03:35:00Z) — деградировано до ГЛОБАЛЬНОГО прогона: схемы (test-case/run) не связывают run с конкретным TC ИЛИ с областью (нет поля run↔TC/area), см. отчёт builder'а
- per-TC last green:
  - TC-066: RUN-20260804-1317 (updated: 2026-08-04T11:44:09Z)
  - TC-067: RUN-20260804-1624 (updated: 2026-08-04T22:20:45Z)
  - TC-068: RUN-20260804-1317 (updated: 2026-08-04T11:44:09Z)
  - TC-069: RUN-20260804-1624 (updated: 2026-08-04T22:20:45Z)
  - TC-070: RUN-20260804-1317 (updated: 2026-08-04T11:44:09Z)
  - TC-071: RUN-20260804-1624 (updated: 2026-08-04T22:20:45Z)
  - TC-072: RUN-20260804-1317 (updated: 2026-08-04T11:44:09Z)
  - TC-073: RUN-20260804-1624 (updated: 2026-08-04T22:20:45Z)
  - TC-074: RUN-20260804-1317 (updated: 2026-08-04T11:44:09Z)
  - TC-075: RUN-20260804-1624 (updated: 2026-08-04T22:20:45Z)
  - TC-076: RUN-20260804-1317 (updated: 2026-08-04T11:44:09Z)
  - TC-077: RUN-20260804-1624 (updated: 2026-08-04T22:20:45Z)
  - TC-078: RUN-20260804-1355 (updated: None)
  - TC-079: RUN-20260804-1624 (updated: 2026-08-04T22:20:45Z)
  - TC-080: RUN-20260804-1317 (updated: 2026-08-04T11:44:09Z)
  - TC-081: RUN-20260804-1624 (updated: 2026-08-04T22:20:45Z)
  - TC-082: RUN-20260804-1317 (updated: 2026-08-04T11:44:09Z)
  - TC-083: RUN-20260804-1624 (updated: 2026-08-04T22:20:45Z)
  - TC-118: RUN-20260804-1317 (updated: 2026-08-04T11:44:09Z)
  - TC-119: RUN-20260804-1624 (updated: 2026-08-04T22:20:45Z)
  - TC-120: RUN-20260804-1624 (updated: 2026-08-04T22:20:45Z)
  - TC-121: RUN-20260804-1624 (updated: 2026-08-04T22:20:45Z)
  - TC-122: RUN-20260804-1624 (updated: 2026-08-04T22:20:45Z)

| Priority | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| P0 |  |  |  | 21 |  |
| P1 |  |  |  | 1 |  |
| P2 |  |  |  | 1 |  |
| P3 |  |  |  |  |  |

### compatibility

- coverage_status: **designed-full** (3/3 Automated)
- риски: R-14
- кейсы без risk: нет
- P0/P1 не в Automated: нет
- автотесты (automated_by): framework/tests/test_compatibility.py::test_orientation_rotation_preserves_tab_state, framework/tests/test_compatibility.py::test_smoke_path_in_system_dark_and_light_modes, framework/tests/test_compatibility.py::test_smoke_path_on_api26_no_regression
- last_green_run: RUN-20260702-0300 (suite: smoke, status: Closed, updated: 2026-07-02T03:35:00Z) — деградировано до ГЛОБАЛЬНОГО прогона: схемы (test-case/run) не связывают run с конкретным TC ИЛИ с областью (нет поля run↔TC/area), см. отчёт builder'а
- per-TC last green:
  - TC-109: нет зелёного per-TC
  - TC-110: нет зелёного per-TC
  - TC-111: нет зелёного per-TC

| Priority | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| P0 |  |  |  |  |  |
| P1 |  |  |  |  |  |
| P2 |  |  |  | 3 |  |
| P3 |  |  |  |  |  |

### downloads

- coverage_status: **partial** (14/18 Automated)
- риски: R-05, R-16
- кейсы без risk: нет
- P0/P1 не в Automated: TC-153 [P1, Review], TC-154 [P1, Review], TC-164 [P1, Review]
- автотесты (automated_by): framework/tests/test_downloads.py::test_auto_download_triggers_on_loved_rating, framework/tests/test_downloads.py::test_change_download_folder_triggers_silent_scan_and_relinks_orphan_file, framework/tests/test_downloads.py::test_delete_downloaded_file_keeps_rating_row, framework/tests/test_downloads.py::test_delete_work_removes_row_and_file, framework/tests/test_downloads.py::test_deselecting_favorite_rating_does_not_download, framework/tests/test_downloads.py::test_edit_note_on_already_saved_work_via_listing_overlay_does_not_redownload, framework/tests/test_downloads.py::test_edit_tag_on_already_saved_work_via_panel_does_not_redownload, framework/tests/test_downloads.py::test_enabling_auto_download_does_not_retroactively_download_favorites, framework/tests/test_downloads.py::test_favorite_rating_does_not_download_when_auto_download_off, framework/tests/test_downloads.py::test_manual_download_from_library_adds_local_file, framework/tests/test_downloads.py::test_manual_scan_for_downloads_shows_dialog_on_zero_files, framework/tests/test_downloads.py::test_open_downloaded_file_applies_viewport_and_reader_css, framework/tests/test_downloads.py::test_rating_change_from_favorite_to_kudosed_does_not_download, framework/tests/test_downloads.py::test_restore_folds_orphan_scan_into_single_dialog
- last_green_run: RUN-20260702-0300 (suite: smoke, status: Closed, updated: 2026-07-02T03:35:00Z) — деградировано до ГЛОБАЛЬНОГО прогона: схемы (test-case/run) не связывают run с конкретным TC ИЛИ с областью (нет поля run↔TC/area), см. отчёт builder'а
- per-TC last green:
  - TC-032: RUN-20260804-1624 (updated: 2026-08-04T22:20:45Z)
  - TC-033: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-034: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-035: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-036: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-037: нет зелёного per-TC
  - TC-038: нет зелёного per-TC
  - TC-039: нет зелёного per-TC
  - TC-112: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-113: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-114: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-115: нет зелёного per-TC
  - TC-116: нет зелёного per-TC
  - TC-117: нет зелёного per-TC

| Priority | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| P0 |  |  |  |  |  |
| P1 |  | 3 |  | 9 |  |
| P2 |  | 1 |  | 4 |  |
| P3 |  |  |  | 1 |  |

### errors

- coverage_status: **designed-full** (1/1 Automated)
- риски: R-03 (частично, TECH)
- кейсы без risk: нет
- P0/P1 не в Automated: нет
- автотесты (automated_by): framework/tests/test_errors.py::test_main_frame_load_error_shows_custom_error_page_with_retry
- last_green_run: RUN-20260702-0300 (suite: smoke, status: Closed, updated: 2026-07-02T03:35:00Z) — деградировано до ГЛОБАЛЬНОГО прогона: схемы (test-case/run) не связывают run с конкретным TC ИЛИ с областью (нет поля run↔TC/area), см. отчёт builder'а
- per-TC last green:
  - TC-046: нет зелёного per-TC

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
- per-TC last green:
  - TC-040: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-041: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-042: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-085: RUN-20260803-2012 (updated: 2026-08-03T20:40:00Z)
  - TC-086: RUN-20260803-2012 (updated: 2026-08-03T20:40:00Z)

| Priority | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| P0 |  |  |  |  |  |
| P1 |  |  |  | 5 |  |
| P2 |  |  |  |  |  |
| P3 |  |  |  |  |  |

### library

- coverage_status: **designed-full** (17/17 Automated)
- риски: R-04, R-06, R-08, R-10
- кейсы без risk: TC-006
- P0/P1 не в Automated: нет
- автотесты (automated_by): framework/tests/test_library.py::test_change_rating_moves_work_between_tabs, framework/tests/test_library.py::test_comment_only_not_in_any_rating_tab, framework/tests/test_library.py::test_library_card_shows_note_icon_and_tags, framework/tests/test_library.py::test_library_tab_labels, framework/tests/test_library_filters.py::test_library_filter_by_fandom, framework/tests/test_library_filters.py::test_library_filter_downloaded_only, framework/tests/test_library_filters.py::test_library_filter_freetext_search, framework/tests/test_library_filters.py::test_library_filter_tags_and_semantics, framework/tests/test_library_filters.py::test_library_filter_word_count_range, framework/tests/test_library_filters.py::test_library_sort_author_asc_blank_last, framework/tests/test_library_filters.py::test_library_sort_last_read_default, framework/tests/test_library_filters.py::test_library_sort_rating_files_tab_only, framework/tests/test_library_filters.py::test_library_sort_wordcount_asc_resets_scroll, framework/tests/test_library_filters.py::test_library_sort_wordcount_desc_resets_scroll, framework/tests/test_library_filters.py::test_library_sort_wordcount_null_last, framework/tests/test_tabs.py::test_library_card_open_at_tab_limit_shows_dialog_and_switches_screen, framework/tests/test_tabs.py::test_library_card_open_work_opens_new_active_browse_tab
- last_green_run: RUN-20260702-0300 (suite: smoke, status: Closed, updated: 2026-07-02T03:35:00Z) — деградировано до ГЛОБАЛЬНОГО прогона: схемы (test-case/run) не связывают run с конкретным TC ИЛИ с областью (нет поля run↔TC/area), см. отчёт builder'а
- per-TC last green:
  - TC-006: нет зелёного per-TC
  - TC-016: нет зелёного per-TC
  - TC-017: RUN-20260805-0432 (updated: 2026-08-05T03:20:00Z)
  - TC-027: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-028: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-029: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-030: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-031: нет зелёного per-TC
  - TC-060: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-061: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-062: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-063: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-064: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-065: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-089: нет зелёного per-TC
  - TC-136: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-137: нет зелёного per-TC

| Priority | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| P0 |  |  |  | 2 |  |
| P1 |  |  |  | 11 |  |
| P2 |  |  |  | 3 |  |
| P3 |  |  |  | 1 |  |

### performance

- coverage_status: **designed-full** (4/4 Automated)
- риски: R-12
- кейсы без risk: нет
- P0/P1 не в Automated: нет
- автотесты (automated_by): framework/tests/test_performance.py::test_cold_start_within_relative_budget, framework/tests/test_performance.py::test_memory_trend_recovers_after_closing_tabs, framework/tests/test_performance.py::test_no_crash_or_anr_during_smoke_path, framework/tests/test_performance.py::test_webview_first_load_within_relative_budget
- last_green_run: RUN-20260702-0300 (suite: smoke, status: Closed, updated: 2026-07-02T03:35:00Z) — деградировано до ГЛОБАЛЬНОГО прогона: схемы (test-case/run) не связывают run с конкретным TC ИЛИ с областью (нет поля run↔TC/area), см. отчёт builder'а
- per-TC last green:
  - TC-096: RUN-20260804-1624 (updated: 2026-08-04T22:20:45Z)
  - TC-097: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-098: RUN-20260805-0432 (updated: 2026-08-05T03:20:00Z)
  - TC-099: RUN-20260805-0432 (updated: 2026-08-05T03:20:00Z)

| Priority | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| P0 |  |  |  | 2 |  |
| P1 |  |  |  | 2 |  |
| P2 |  |  |  |  |  |
| P3 |  |  |  |  |  |

### rating

- coverage_status: **partial** (20/24 Automated)
- риски: R-01, R-04, R-10, R-17
- кейсы без risk: нет
- P0/P1 не в Automated: TC-139 [P1, Approved], TC-151 [P1, Review], TC-152 [P1, Review], TC-155 [P1, Review]
- автотесты (automated_by): framework/tests/test_rating.py::test_deselect_rating_on_work_page_panel, framework/tests/test_rating.py::test_edit_tag_on_already_saved_work_via_panel_does_not_click_kudos, framework/tests/test_rating.py::test_first_panel_save_clicks_kudos_once, framework/tests/test_rating.py::test_rate_work_from_work_page_panel, framework/tests/test_rating_listing.py::test_add_freeform_tag_persists, framework/tests/test_rating_listing.py::test_apply_ratings_syncs_duplicate_blurbs, framework/tests/test_rating_listing.py::test_change_rating_kudosed_to_read_via_listing_does_not_click_kudos, framework/tests/test_rating_listing.py::test_clear_note_removes_comment, framework/tests/test_rating_listing.py::test_comment_only_visible_on_listing_and_absent_from_rating_tabs, framework/tests/test_rating_listing.py::test_deselect_kudosed_via_listing_does_not_click_kudos, framework/tests/test_rating_listing.py::test_edit_tag_on_already_kudosed_work_via_listing_does_not_reclick_kudos, framework/tests/test_rating_listing.py::test_first_kudosed_via_listing_with_open_work_tab_clicks_kudos_once, framework/tests/test_rating_listing.py::test_listing_rate_button_updates_without_reload, framework/tests/test_rating_listing.py::test_matching_personal_tag_highlighted_on_listing, framework/tests/test_rating_listing.py::test_note_button_opens_overlay_with_expanded_comment, framework/tests/test_rating_listing.py::test_panel_rating_updates_without_reload, framework/tests/test_rating_listing.py::test_personal_tags_do_not_affect_visibility, framework/tests/test_rating_listing.py::test_rate_kudosed_via_listing_without_open_work_tab_does_not_click_kudos, framework/tests/test_rating_listing.py::test_rate_work_from_listing_overlay, framework/tests/test_rating_listing.py::test_save_note_persists_comment, framework/tests/test_rating_listing.py::test_tap_selected_chip_removes_tag
- last_green_run: RUN-20260702-0300 (suite: smoke, status: Closed, updated: 2026-07-02T03:35:00Z) — деградировано до ГЛОБАЛЬНОГО прогона: схемы (test-case/run) не связывают run с конкретным TC ИЛИ с областью (нет поля run↔TC/area), см. отчёт builder'а
- per-TC last green:
  - TC-007: RUN-20260805-0432 (updated: 2026-08-05T03:20:00Z)
  - TC-008: RUN-20260805-0432 (updated: 2026-08-05T03:20:00Z)
  - TC-009: RUN-20260805-0432 (updated: 2026-08-05T03:20:00Z)
  - TC-010: нет зелёного per-TC
  - TC-011: нет зелёного per-TC
  - TC-012: нет зелёного per-TC
  - TC-043: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-044: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-045: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-056: нет зелёного per-TC
  - TC-087: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-088: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-090: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-091: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-138: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-140: нет зелёного per-TC
  - TC-141: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-142: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-143: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-144: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)

| Priority | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| P0 |  |  |  | 3 |  |
| P1 |  | 3 | 1 | 12 |  |
| P2 |  |  |  | 3 |  |
| P3 |  |  |  | 2 |  |

### security

- coverage_status: **designed-full** (6/6 Automated)
- риски: R-15
- кейсы без risk: нет
- P0/P1 не в Automated: нет
- автотесты (automated_by): framework/tests/test_security_backup_privacy.py::test_backup_privacy_manifest_scope_declared, framework/tests/test_security_file_access.py::test_file_link_inside_downloaded_work_does_not_escape_download_content, framework/tests/test_security_js_bridge.py::test_js_bridge_exposure_baseline_vs_non_ao3_error_page, framework/tests/test_security_logcat.py::test_logcat_has_no_sensitive_data_during_smoke_path, framework/tests/test_security_manifest.py::test_cleartext_traffic_policy_documented_and_cross_checked, framework/tests/test_security_manifest.py::test_main_activity_exported_with_ao3_intent_filter
- last_green_run: RUN-20260702-0300 (suite: smoke, status: Closed, updated: 2026-07-02T03:35:00Z) — деградировано до ГЛОБАЛЬНОГО прогона: схемы (test-case/run) не связывают run с конкретным TC ИЛИ с областью (нет поля run↔TC/area), см. отчёт builder'а
- per-TC last green:
  - TC-100: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-101: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-102: нет зелёного per-TC
  - TC-103: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-104: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-105: нет зелёного per-TC

| Priority | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| P0 |  |  |  |  |  |
| P1 |  |  |  | 6 |  |
| P2 |  |  |  |  |  |
| P3 |  |  |  |  |  |

### settings

- coverage_status: **partial** (11/17 Automated)
- риски: R-01, R-11
- кейсы без risk: нет
- P0/P1 не в Automated: TC-145 [P1, Review], TC-146 [P1, Review], TC-147 [P1, Review], TC-163 [P1, Review], TC-169 [P1, Review], TC-170 [P1, Review]
- автотесты (automated_by): framework/tests/test_infinite_scroll.py::test_infinite_scroll_off_keeps_native_pagination, framework/tests/test_reading_ux.py::test_tap_to_scroll_live_push_and_reload_persistence, framework/tests/test_reading_ux.py::test_tap_to_scroll_survives_kill_and_relaunch, framework/tests/test_reading_ux.py::test_tap_zone_disabled_no_effect_in_any_third, framework/tests/test_settings.py::test_cancel_clear_all_dialog_keeps_data, framework/tests/test_settings.py::test_clear_all_ratings_badge_persists_without_reload, framework/tests/test_settings.py::test_clear_all_ratings_shows_confirmation_dialog, framework/tests/test_settings.py::test_system_theme_follows_os_dark_mode, framework/tests/test_settings.py::test_theme_dark_applies_instantly_without_recreating_activity, framework/tests/test_settings.py::test_webview_dark_mode_applies_instantly, framework/tests/test_settings.py::test_webview_follows_system_theme_without_in_app_toggle
- last_green_run: RUN-20260702-0300 (suite: smoke, status: Closed, updated: 2026-07-02T03:35:00Z) — деградировано до ГЛОБАЛЬНОГО прогона: схемы (test-case/run) не связывают run с конкретным TC ИЛИ с областью (нет поля run↔TC/area), см. отчёт builder'а
- per-TC last green:
  - TC-018: нет зелёного per-TC
  - TC-019: нет зелёного per-TC
  - TC-020: нет зелёного per-TC
  - TC-047: нет зелёного per-TC
  - TC-048: нет зелёного per-TC
  - TC-049: нет зелёного per-TC
  - TC-059: нет зелёного per-TC
  - TC-123: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-124: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-125: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-129: RUN-20260803-2012 (updated: 2026-08-03T20:40:00Z)

| Priority | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| P0 |  |  |  |  |  |
| P1 |  | 6 |  | 7 |  |
| P2 |  |  |  | 3 |  |
| P3 |  |  |  | 1 |  |

### smoke

- coverage_status: **designed-full** (5/5 Automated)
- риски: R-01, R-03, R-04
- кейсы без risk: TC-002, TC-005
- P0/P1 не в Automated: нет
- автотесты (automated_by): framework/tests/test_smoke.py::test_app_launches_and_loads_ao3, framework/tests/test_smoke.py::test_bottom_nav_switches_screens, framework/tests/test_smoke.py::test_clear_all_ratings, framework/tests/test_smoke.py::test_seeded_work_appears_in_correct_tab, framework/tests/test_smoke.py::test_theme_toggle_stable
- last_green_run: RUN-20260702-0300 (suite: smoke, status: Closed, updated: 2026-07-02T03:35:00Z) — деградировано до ГЛОБАЛЬНОГО прогона: схемы (test-case/run) не связывают run с конкретным TC ИЛИ с областью (нет поля run↔TC/area), см. отчёт builder'а
- per-TC last green:
  - TC-001: RUN-20260805-0432 (updated: 2026-08-05T03:20:00Z)
  - TC-002: RUN-20260805-0432 (updated: 2026-08-05T03:20:00Z)
  - TC-003: RUN-20260805-0432 (updated: 2026-08-05T03:20:00Z)
  - TC-004: RUN-20260805-0432 (updated: 2026-08-05T03:20:00Z)
  - TC-005: RUN-20260805-0432 (updated: 2026-08-05T03:20:00Z)

| Priority | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| P0 |  |  |  | 5 |  |
| P1 |  |  |  |  |  |
| P2 |  |  |  |  |  |
| P3 |  |  |  |  |  |

### tabs

- coverage_status: **designed-full** (11/11 Automated)
- риски: R-08
- кейсы без risk: нет
- P0/P1 не в Automated: нет
- автотесты (automated_by): framework/tests/test_tabs.py::test_background_resume_without_deep_link_keeps_tabs_unchanged, framework/tests/test_tabs.py::test_cold_start_deep_link_reuses_single_home_tab, framework/tests/test_tabs.py::test_deep_link_after_home_loaded_creates_second_tab_not_reuse, framework/tests/test_tabs.py::test_deep_link_at_tab_limit_shows_dialog_and_drops_url, framework/tests/test_tabs.py::test_kill_relaunch_without_deep_link_keeps_tabs_unchanged, framework/tests/test_tabs.py::test_long_press_link_opens_background_tab_without_switching, framework/tests/test_tabs.py::test_max_tabs_limit_blocks_11th_tab, framework/tests/test_tabs.py::test_swipe_close_undo_restores_position, framework/tests/test_tabs.py::test_tabs_persist_url_and_scroll_after_restart, framework/tests/test_tabs.py::test_tap_inactive_tab_chip_activates_it, framework/tests/test_tabs.py::test_undo_history_evicts_oldest_after_six_closes
- last_green_run: RUN-20260702-0300 (suite: smoke, status: Closed, updated: 2026-07-02T03:35:00Z) — деградировано до ГЛОБАЛЬНОГО прогона: схемы (test-case/run) не связывают run с конкретным TC ИЛИ с областью (нет поля run↔TC/area), см. отчёт builder'а
- per-TC last green:
  - TC-022: RUN-20260804-1624 (updated: 2026-08-04T22:20:45Z)
  - TC-023: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-024: нет зелёного per-TC
  - TC-025: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-026: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-084: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-131: RUN-20260804-1624 (updated: 2026-08-04T22:20:45Z)
  - TC-132: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-133: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-134: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-135: RUN-20260803-2012 (updated: 2026-08-03T20:40:00Z)

| Priority | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| P0 |  |  |  |  |  |
| P1 |  |  |  | 10 |  |
| P2 |  |  |  |  |  |
| P3 |  |  |  | 1 |  |

### visibility

- coverage_status: **designed-full** (6/6 Automated)
- риски: R-06
- кейсы без risk: нет
- P0/P1 не в Automated: нет
- автотесты (automated_by): framework/tests/test_visibility.py::test_dim_mode_dims_hidden_rating_blurb, framework/tests/test_visibility.py::test_disliked_hidden_on_listing, framework/tests/test_visibility.py::test_disliked_visible_after_hide_toggle_off, framework/tests/test_visibility.py::test_display_mode_hide_to_dim_live_push, framework/tests/test_visibility.py::test_hide_kudosed_only_excludes_kudosed, framework/tests/test_visibility.py::test_no_rating_or_comment_only_never_hidden
- last_green_run: RUN-20260702-0300 (suite: smoke, status: Closed, updated: 2026-07-02T03:35:00Z) — деградировано до ГЛОБАЛЬНОГО прогона: схемы (test-case/run) не связывают run с конкретным TC ИЛИ с областью (нет поля run↔TC/area), см. отчёт builder'а
- per-TC last green:
  - TC-013: RUN-20260805-0432 (updated: 2026-08-05T03:20:00Z)
  - TC-014: RUN-20260805-0432 (updated: 2026-08-05T03:20:00Z)
  - TC-015: RUN-20260805-0432 (updated: 2026-08-05T03:20:00Z)
  - TC-092: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-093: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)
  - TC-095: RUN-20260805-0437 (updated: 2026-08-05T03:20:00Z)

| Priority | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| P0 |  |  |  | 3 |  |
| P1 |  |  |  | 3 |  |
| P2 |  |  |  |  |  |
| P3 |  |  |  |  |  |

