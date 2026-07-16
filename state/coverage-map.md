# Карта покрытия (генерируется, НЕ редактировать руками)

generated_at: 2026-07-16T22:35:46Z · генератор: `scripts/coverage_map.py`
Проекция из frontmatter test-cases/ и runs/ (принцип G1, как у `state/factory-status.md`). Рукописной модели покрытия не существует — этот файл не второй источник истины, а вывод.

прогоны без tc_results (поле ещё не внедрено): RUN-20260702-0300

## Сводка по областям

| Область | Кейсов | Automated | coverage_status |
|---|---|---|---|
| backup | 1 | 1 | designed-full |
| browser | 8 | 6 | partial |
| downloads | 8 | 5 | partial |
| errors | 1 | 0 | none |
| filter-profiles | 3 | 0 | none |
| library | 14 | 6 | partial |
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
| R-06 | BUS | library:TC-027, library:TC-028, library:TC-029, library:TC-030, library:TC-031, library:TC-060, library:TC-061, library:TC-062, library:TC-063, library:TC-064, library:TC-065, visibility:TC-013, visibility:TC-014, visibility:TC-015 |
| R-07 | OPS | риск не покрыт дизайном |
| R-08 | TECH | tabs:TC-022, tabs:TC-023, tabs:TC-024, tabs:TC-025, tabs:TC-026 |
| R-11 | TECH | browser:TC-050, browser:TC-051, browser:TC-052, browser:TC-053, browser:TC-054, browser:TC-055, browser:TC-057, browser:TC-058, settings:TC-047, settings:TC-048, settings:TC-049, settings:TC-059 |
| R-09 | BUS | filter-profiles:TC-040, filter-profiles:TC-041, filter-profiles:TC-042 |
| R-10 | DATA | rating:TC-043, rating:TC-044, rating:TC-045, rating:TC-056 |
| R-12 | PERF | риск не покрыт дизайном |
| R-13 | A11Y | риск не покрыт дизайном |
| R-14 | COMPAT | риск не покрыт дизайном |
| R-15 | SEC | риск не покрыт дизайном |

## Фичи → покрытие

| Фича | Экран | Кейсы |
|---|---|---|
| browse-tabs-lifecycle | browse | нет кейсов |
| browse-deep-links | browse | нет кейсов |
| browse-scroll-restore | browse | нет кейсов |
| browse-infinite-scroll | browse | нет кейсов |
| browse-tap-to-scroll | browse | нет кейсов |
| browse-pinch-font | browse | нет кейсов |
| browse-two-finger-brightness | browse | нет кейсов |
| browse-bridge-injection | browse | нет кейсов |
| browse-tabstrip-indicators | browse | нет кейсов |
| browse-bottombar-nav | browse | нет кейсов |
| sidepanel-home | side-panel | нет кейсов |
| sidepanel-theme-toggle | side-panel | нет кейсов |
| sidepanel-font-size | side-panel | нет кейсов |
| sidepanel-fullscreen-toggle | side-panel | нет кейсов |
| sidepanel-rating-filters | side-panel | нет кейсов |
| sidepanel-settings-sync | side-panel | нет кейсов |
| library-tabs-six | library | нет кейсов |
| library-filter-wordcount | library | нет кейсов |
| library-filter-fandom | library | нет кейсов |
| library-filter-downloaded-only | library | нет кейсов |
| library-filter-freetext | library | нет кейсов |
| library-filter-tags-and | library | нет кейсов |
| library-sort-last-read | library | нет кейсов |
| library-sort-wordcount | library | нет кейсов |
| library-sort-author | library | нет кейсов |
| library-sort-rating-files | library | нет кейсов |
| library-sort-scroll-reset | library | нет кейсов |
| library-card-actions | library | нет кейсов |
| library-card-comment-tags | library | нет кейсов |
| settings-theme-mode | settings | нет кейсов |
| settings-webview-dark-mode | settings | нет кейсов |
| settings-font-slider | settings | нет кейсов |
| settings-brightness-slider | settings | нет кейсов |
| settings-rating-visibility-filter | settings | нет кейсов |
| settings-panel-side | settings | нет кейсов |
| settings-tap-to-scroll-toggle | settings | нет кейсов |
| settings-infinite-scroll-toggle | settings | нет кейсов |
| settings-auto-download-favorite | settings | нет кейсов |
| settings-download-folder-saf | settings | нет кейсов |
| settings-backup-export | settings | нет кейсов |
| settings-restore-merge | settings | нет кейсов |
| settings-orphan-scan-silent | settings | нет кейсов |
| settings-orphan-scan-restore-dialog | settings | нет кейсов |
| settings-scan-downloads-manual | settings | нет кейсов |
| settings-filter-profiles-list | settings | нет кейсов |
| settings-filter-profiles-delete | settings | нет кейсов |
| settings-filter-profiles-rename | settings | нет кейсов |
| browser-filter-profile-save | browser | нет кейсов |
| browser-filter-profile-apply | browser | нет кейсов |
| rating-overlay-five-options | rating-notes | нет кейсов |
| rating-deselect-on-tap | rating-notes | нет кейсов |
| rating-comment-field | rating-notes | нет кейсов |
| rating-tags-chips | rating-notes | нет кейсов |
| rating-entry-work-panel | rating-notes | нет кейсов |
| rating-entry-listing-overlay | rating-notes | нет кейсов |
| rating-note-button-listing | rating-notes | нет кейсов |
| bridge-rate-note-tag-buttons | ao3-bridge | нет кейсов |
| bridge-badge-sync-multi | ao3-bridge | нет кейсов |
| bridge-hide-dim-filter | ao3-bridge | нет кейсов |
| bridge-main-pairing-filter | ao3-bridge | нет кейсов |
| bridge-exclude-main-pairing-filter | ao3-bridge | нет кейсов |
| bridge-dark-css | ao3-bridge | нет кейсов |
| bridge-scroll-reporting | ao3-bridge | нет кейсов |
| data-workrating-model | data | нет кейсов |
| data-filterprofile-model | data | нет кейсов |
| data-clear-all-ratings | data | нет кейсов |
| background-download-repository | background | нет кейсов |
| background-auto-download-trigger | background | нет кейсов |

## Фичи без единого кейса

- browse-tabs-lifecycle (browse): Вкладки: открыть/закрыть/переключить (лимит MAX_TABS=10)
- browse-deep-links (browse): Deep link (intent data) открывает/переключает вкладку на URL
- browse-scroll-restore (browse): Восстановление позиции скролла вкладки после рестарта приложения
- browse-infinite-scroll (browse): Бесконечная подгрузка следующих страниц листинга при скролле
- browse-tap-to-scroll (browse): Тап по верхней/нижней трети страницы работы скроллит вверх/вниз, средняя треть — fullscreen toggle
- browse-pinch-font (browse): Pinch/spread двумя пальцами меняет размер шрифта (fontSizeStep)
- browse-two-finger-brightness (browse): Вертикальный двухпальцевый драг меняет яркость
- browse-bridge-injection (browse): Инжекция ao3_bridge.js в каждую загруженную AO3-страницу (onPageFinished)
- browse-tabstrip-indicators (browse): TabStrip: индикация активной вкладки, закрытие свайпом вверх, кнопка New tab
- browse-bottombar-nav (browse): BottomBar: навигация между экранами Browse/Library/Settings
- sidepanel-home (side-panel): Кнопка Home в side panel переводит активную вкладку на AO3 root
- sidepanel-theme-toggle (side-panel): Кнопка переключения темы Light/Dark в side panel
- sidepanel-font-size (side-panel): Кнопки A-/A+ в side panel, disabled на границах диапазона (шаги 0..6)
- sidepanel-fullscreen-toggle (side-panel): Кнопка fullscreen toggle в side panel
- sidepanel-rating-filters (side-panel): Чекбоксы скрытия рейтингов (hidden ratings) в side panel
- sidepanel-settings-sync (side-panel): Side panel отражает общий стейт темы/шрифта/скрытых рейтингов с Settings
- library-tabs-six (library): 6 вкладок библиотеки (Favorite/Kudosed/Read/Pending/Disliked/Files)
- library-filter-wordcount (library): Фильтр word count min/max
- library-filter-fandom (library): Фильтр по фандому
- library-filter-downloaded-only (library): Чекбокс downloaded-only
- library-filter-freetext (library): Свободный текстовый поиск (title/author/fandom/tags/comment)
- library-filter-tags-and (library): Фильтр по личным тегам, логика AND (все выбранные теги должны совпасть)
- library-sort-last-read (library): Сортировка Last read (дефолт, по убыванию timestamp)
- library-sort-wordcount (library): Сортировка Word count ASC/DESC
- library-sort-author (library): Сортировка Author A-Z (пустой author в конце)
- library-sort-rating-files (library): Сортировка Rating, доступна только на вкладке Files
- library-sort-scroll-reset (library): Сброс скролла списка на верх при смене сортировки
- library-card-actions (library): Действия карточки: открыть/скачать/удалить файл/удалить работу целиком
- library-card-comment-tags (library): Индикатор комментария (note-иконка) и личных тегов на карточке
- settings-theme-mode (settings): Тема Light/Dark/System без пересоздания Activity
- settings-webview-dark-mode (settings): WebView dark mode (FORCE_DARK / ALGORITHMIC_DARKENING)
- settings-font-slider (settings): Слайдер размера шрифта (7 ступеней, 100–190%)
- settings-brightness-slider (settings): Слайдер яркости (overlay при v<0, reset-on-start)
- settings-rating-visibility-filter (settings): Фильтр видимости рейтингов, режим отображения hide/dim
- settings-panel-side (settings): Позиция side panel Left/Right
- settings-tap-to-scroll-toggle (settings): Тумблер Tap to scroll (work pages)
- settings-infinite-scroll-toggle (settings): Тумблер Infinite scroll (listing pages)
- settings-auto-download-favorite (settings): Тумблер авто-скачивания HTML при рейтинге Favorite (SAVE)
- settings-download-folder-saf (settings): Выбор папки загрузок через SAF (Storage Access Framework)
- settings-backup-export (settings): Экспорт бэкапа JSON (works + filterProfiles)
- settings-restore-merge (settings): Восстановление из бэкапа с merge (пропуск уже существующих id)
- settings-orphan-scan-silent (settings): Тихий orphan-скан загрузок при смене папки (без диалога, если пусто)
- settings-orphan-scan-restore-dialog (settings): Orphan-скан свёрнут в единый диалог результата при restore из бэкапа
- settings-scan-downloads-manual (settings): Ручная кнопка Scan for downloads — relink .html-файлов, потерянных базой
- settings-filter-profiles-list (settings): Список сохранённых AO3-фильтр-профилей
- settings-filter-profiles-delete (settings): Удаление фильтр-профиля из списка Settings и из активной панели
- settings-filter-profiles-rename (settings): Переименование фильтр-профиля
- browser-filter-profile-save (browser): Кнопка Save filter в форме AO3 Sort&Filter — сохранение текущего запроса профилем (инжекция bridge)
- browser-filter-profile-apply (browser): Применение сохранённого фильтр-профиля из FilterPanel листинга
- rating-overlay-five-options (rating-notes): Overlay/панель с 5 рейтингами (Favorite/Kudosed/Read/Pending/Dislike)
- rating-deselect-on-tap (rating-notes): Deselect рейтинга повторным тапом на уже выбранной кнопке
- rating-comment-field (rating-notes): Поле комментария: добавить/изменить/очистить (Save note / Clear note)
- rating-tags-chips (rating-notes): Chip-теги: добавление (suggested/custom) и удаление
- rating-entry-work-panel (rating-notes): Вход в рейтинг: встроенная панель страницы работы (bottom bar)
- rating-entry-listing-overlay (rating-notes): Вход в рейтинг: bottom-sheet-подобный overlay с Rate-кнопки листинга
- rating-note-button-listing (rating-notes): Note-кнопка на карточке листинга открывает overlay с развёрнутым комментарием
- bridge-rate-note-tag-buttons (ao3-bridge): Инжекция Rate/Note/Tag-индикаторов в карточки листинга AO3
- bridge-badge-sync-multi (ao3-bridge): Синхронизация бейджа рейтинга по нескольким вхождениям работы на листинге/вкладках
- bridge-hide-dim-filter (ao3-bridge): hide/dim-фильтрация карточек листинга по скрытым рейтингам
- bridge-main-pairing-filter (ao3-bridge): Чекбокс 'Main pairing only' в форме include-фильтра AO3 (Sort & Filter)
- bridge-exclude-main-pairing-filter (ao3-bridge): Чекбокс исключения main pairing в форме exclude-фильтра AO3
- bridge-dark-css (ao3-bridge): CSS-переопределения тёмной темы на AO3-страницах (window.__ao3AppDark)
- bridge-scroll-reporting (ao3-bridge): Отчёт позиции скролла и прогресса чтения (глава/%) в Kotlin
- data-workrating-model (data): Room-сущность WorkRating (rating/comment/tags/fandom/author/wordCount/downloadPath)
- data-filterprofile-model (data): Room-сущность FilterProfile (name/queryString)
- data-clear-all-ratings (data): Clear all ratings — полное необратимое удаление всех рейтингов
- background-download-repository (background): DownloadRepository: скачивание HTML работы через OkHttp в SAF-папку или app storage
- background-auto-download-trigger (background): Автозапуск скачивания при простановке рейтинга Favorite (SAVE), если тумблер включён

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

- coverage_status: **partial** (6/8 Automated)
- риски: R-11
- кейсы без risk: нет
- P0/P1 не в Automated: нет
- автотесты (automated_by): framework/tests/test_side_panel.py::test_font_buttons_disabled_at_range_boundaries, framework/tests/test_side_panel.py::test_font_size_increase_instant_and_persists, framework/tests/test_side_panel.py::test_pinch_spread_changes_font_size, framework/tests/test_side_panel.py::test_side_panel_and_settings_share_theme_and_font_state, framework/tests/test_side_panel.py::test_side_panel_contrast_toggles_theme_instantly, framework/tests/test_side_panel.py::test_side_panel_home_navigates_active_tab_to_ao3_root, framework/tests/test_side_panel.py::test_two_finger_drag_changes_brightness
- last_green_run: RUN-20260702-0300 (suite: smoke, status: Closed, updated: 2026-07-02T03:35:00Z) — деградировано до ГЛОБАЛЬНОГО прогона: схемы (test-case/run) не связывают run с конкретным TC ИЛИ с областью (нет поля run↔TC/area), см. отчёт builder'а

| Priority | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| P0 |  |  |  |  |  |
| P1 |  |  |  | 6 |  |
| P2 |  |  |  |  |  |
| P3 |  |  | 2 |  |  |

### downloads

- coverage_status: **partial** (5/8 Automated)
- риски: R-05
- кейсы без risk: нет
- P0/P1 не в Automated: TC-032 [P1, Approved], TC-033 [P1, Approved]
- автотесты (automated_by): framework/tests/test_downloads.py::test_change_download_folder_triggers_silent_scan_and_relinks_orphan_file, framework/tests/test_downloads.py::test_delete_downloaded_file_keeps_rating_row, framework/tests/test_downloads.py::test_delete_work_removes_row_and_file, framework/tests/test_downloads.py::test_open_downloaded_file_applies_viewport_and_reader_css, framework/tests/test_downloads.py::test_restore_folds_orphan_scan_into_single_dialog
- last_green_run: RUN-20260702-0300 (suite: smoke, status: Closed, updated: 2026-07-02T03:35:00Z) — деградировано до ГЛОБАЛЬНОГО прогона: схемы (test-case/run) не связывают run с конкретным TC ИЛИ с областью (нет поля run↔TC/area), см. отчёт builder'а

| Priority | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| P0 |  |  |  |  |  |
| P1 |  |  | 2 | 3 |  |
| P2 |  |  |  | 2 |  |
| P3 |  |  | 1 |  |  |

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
- автотесты (automated_by): framework/tests/test_filter_profiles.py::test_delete_filter_profile
- last_green_run: RUN-20260702-0300 (suite: smoke, status: Closed, updated: 2026-07-02T03:35:00Z) — деградировано до ГЛОБАЛЬНОГО прогона: схемы (test-case/run) не связывают run с конкретным TC ИЛИ с областью (нет поля run↔TC/area), см. отчёт builder'а

| Priority | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| P0 |  |  |  |  |  |
| P1 |  |  | 3 |  |  |
| P2 |  |  |  |  |  |
| P3 |  |  |  |  |  |

### library

- coverage_status: **partial** (6/14 Automated)
- риски: R-04, R-06
- кейсы без risk: TC-006
- P0/P1 не в Automated: TC-060 [P1, Approved], TC-061 [P1, Approved], TC-062 [P1, Approved], TC-063 [P1, Approved], TC-064 [P1, Approved], TC-065 [P1, Approved]
- автотесты (automated_by): framework/tests/test_library.py::test_change_rating_moves_work_between_tabs, framework/tests/test_library.py::test_comment_only_not_in_any_rating_tab, framework/tests/test_library_filters.py::test_library_filter_by_fandom, framework/tests/test_library_filters.py::test_library_filter_downloaded_only, framework/tests/test_library_filters.py::test_library_filter_word_count_range, framework/tests/test_library_filters.py::test_library_sort_wordcount_desc_resets_scroll
- last_green_run: RUN-20260702-0300 (suite: smoke, status: Closed, updated: 2026-07-02T03:35:00Z) — деградировано до ГЛОБАЛЬНОГО прогона: схемы (test-case/run) не связывают run с конкретным TC ИЛИ с областью (нет поля run↔TC/area), см. отчёт builder'а

| Priority | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| P0 |  |  |  | 2 |  |
| P1 |  |  | 6 | 4 |  |
| P2 | 1 |  |  |  |  |
| P3 |  |  | 1 |  |  |

### rating

- coverage_status: **partial** (2/10 Automated)
- риски: R-04, R-10 (proposed, не утверждён в §5)
- кейсы без risk: нет
- P0/P1 не в Automated: TC-009 [P0, Approved], TC-043 [P1, Approved], TC-044 [P1, Approved], TC-045 [P1, Approved]
- автотесты (automated_by): framework/tests/test_rating.py::test_deselect_rating_on_work_page_panel, framework/tests/test_rating.py::test_rate_work_from_work_page_panel
- last_green_run: RUN-20260702-0300 (suite: smoke, status: Closed, updated: 2026-07-02T03:35:00Z) — деградировано до ГЛОБАЛЬНОГО прогона: схемы (test-case/run) не связывают run с конкретным TC ИЛИ с областью (нет поля run↔TC/area), см. отчёт builder'а

| Priority | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| P0 |  |  | 1 | 2 |  |
| P1 |  |  | 3 |  |  |
| P2 |  |  | 3 |  |  |
| P3 |  |  | 1 |  |  |

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
| P3 |  |  | 1 |  |  |

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
| P3 |  |  | 1 |  |  |

### visibility

- coverage_status: **none** (0/3 Automated)
- риски: R-06
- кейсы без risk: нет
- P0/P1 не в Automated: TC-013 [P0, Approved], TC-014 [P0, Approved], TC-015 [P0, Review]
- автотесты (automated_by): —
- last_green_run: RUN-20260702-0300 (suite: smoke, status: Closed, updated: 2026-07-02T03:35:00Z) — деградировано до ГЛОБАЛЬНОГО прогона: схемы (test-case/run) не связывают run с конкретным TC ИЛИ с областью (нет поля run↔TC/area), см. отчёт builder'а

| Priority | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| P0 |  | 1 | 2 |  |  |
| P1 |  |  |  |  |  |
| P2 |  |  |  |  |  |
| P3 |  |  |  |  |  |

