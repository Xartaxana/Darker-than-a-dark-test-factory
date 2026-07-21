# Эскалации (реестр активных варнингов)

Формат по docs/06-dark-factory.md §4: id, артефакт, причина, с какого времени,
что нужно от человека. Живёт до разрешения; запись не удаляется, а помечается
resolved при закрытии.

## ESC-001 — AT-BUG-006, ENV_ISSUE дважды подряд (`driver.get()` ReadTimeoutError на replay-навигации)

- Артефакт: `bugs/AT-BUG-006.md` (status: Reopened после этой сессии)
- С какого времени: 2026-07-16T21:48:52Z
- Канал: немедленный алерт (`env_issue_twice_in_a_row`, state/sla.yaml
  `immediate_alerts`)
- Причина: при верификации D1 (build 1.10) `tests/test_filter_profiles.py::
  test_delete_filter_profile` (TC-042) дважды подряд падал на
  `driver.get()` (`browser_steps.open_listing`) с `urllib3.exceptions.
  ReadTimeoutError` (Appium `:4723`, read timeout=120с). Дифференциальная
  проверка на ПРЕДсуществующем `tests/test_replay_infra_probe.py` (не
  относится к фиксу AT-BUG-006, та же `listing_basic.mitm`) даёт идентичный
  сбой — подтверждает, что причина в окружении, а не в фиксе. Ремедиум,
  задокументированный test-maintainer в AT-BUG-006 (инкремент 2, 2026-07-15:
  снять стэйл-лок `multiinstance.lock`/`hardware-qemu.ini.lock` в
  `tools/avd/ao3_test_api34.avd`, холодный ребут `-no-snapshot-load`) был
  применён fix-verifier в этой сессии (стэйл-лок `multiinstance.lock` найден
  и снят, полный холодный ребут выполнен, APK переустановлен, Appium поднят
  заново) — сбой воспроизвёлся идентично И ПОСЛЕ ремедиума. Это либо новый
  класс той же симптоматики (test-maintainer сам оговорил этот сценарий:
  «если симптом БЕЗ предшествующего параллельного запуска эмулятора — другой
  класс, заводить отдельно»), либо ремедиум неполон.
- Что нужно от человека: (а) решение — заводить ли отдельный test_debt/infra
  bug-артефакт на нестабильность `driver.get()`/replay-навигации (кандидат —
  сиблинг найденного в AT-BUG-006 класса, но НЕ объяснённый стэйл-локами в
  этот раз); (б) диагностика на живом окружении (chromedriver/mitmdump/сеть
  между WebView и mitm-прокси) — вне мандата fix-verifier; (в) после
  стабилизации среды — просто повторный прогон `Invoke-Pytest tests/
  test_filter_profiles.py -v` БЕЗ изменений в `seed_db.py`/
  `sort_filter_form.mitm`/локаторах AT-BUG-006 (грани 1/2 критерия готовности
  подтверждены фактически в этой сессии, менять их не нужно).
- ДИАГНОЗ (2026-07-17T00:45:00Z, critic, полный след — Обсуждение
  `bugs/AT-BUG-009.md` запись critic): корень (б) — **mitm-CA ОТСУТСТВУЕТ в
  системном сторе после ребута без переустановки**, не «новый класс
  деградации». Доказано A/B/A' на одном инстансе (меняется только CA):
  CA absent (`NOT_IN_APEX`, apex=34) → `test_replay_infra_probe` FAIL
  `ReadTimeoutError` (196s); `Install-MitmCA` → CA present (store=134) →
  PASS (27.6s); `adb reboot` без переустановки → CA absent снова → FAIL
  (196s). Ремедиум fix-verifier не помог, т.к. CA-mount ВОЛАТИЛЕН
  (`install-mitm-ca.sh` шапка: не переживает reboot), а `Install-MitmCA`
  идёт только из `Start-Emulator -WritableSystem` — холодный ребут БЕЗ
  `-writable-system`/переустановки CA стирает CA и не восстанавливает.
  Чинится ПРОЦЕДУРОЙ СРЕДЫ: поднимать replay только через
  `Start-Emulator -WritableSystem`; после любого ребута — заново
  `Install-MitmCA`. НЕ баг фикса AT-BUG-006 (грани 1/2 подтверждены) — по
  (в) достаточно поднять среду правильно и повторить прогон, ничего в коде
  не меняя. Рекомендация critic (решение Lead): (1) fail-fast проверка CA в
  фикстуре `replay` вместо 120-240с таймаута; (2) отдельный корень —
  позиционная деградация длинной сессии набл. №1/№4 AT-BUG-009 — ЭТИМ
  диагнозом НЕ закрыт (там CA присутствовала). Побочно: `Start-Emulator`
  крэшит на загрузке снапшота `default_boot` (кандидат в отдельный
  infra-долг).
- РЕШЕНИЕ LEAD (2026-07-16, проход /qa-loop 6): (а) заведены test_debt-
  артефакты — `bugs/AT-BUG-011.md` (fail-fast проверка CA в фикстуре
  replay, major) и `bugs/AT-BUG-012.md` (крэш снапшота default_boot,
  minor); (б) диагностика выполнена critic'ом (корень назван, см. ДИАГНОЗ
  выше); (в) повторная верификация AT-BUG-006 — следующим проходом с
  корректным подъёмом (`Start-Emulator -WritableSystem`); runbook-строка
  внесена в HANDOFF «Как поднять окружение». Карантин TC-013 отклонён
  (нелегитимен на этом корне); длинно-сессионная деградация остаётся
  предметом AT-BUG-009 (Open).
- Статус: **resolved 2026-07-16** (корень диагностирован, остаток работ
  отслеживается артефактами AT-BUG-011/012 и очередью B4)

## ESC-002 — AT-BUG-016, 2 неудачных ремедиационных захода test-maintainer подряд (qemu 0xc0000005, разные шаги)

- Артефакт: `bugs/AT-BUG-016.md` (status: Open, lock снят)
- С какого времени: 2026-07-19T01:19:51Z
- Причина: B4-починка (test_debt, major) — два самостоятельных фикса
  применены и прогнаны (см. `bugs/AT-BUG-016.md` «Обсуждение» за полным
  witness): (1) `browser_steps.py::save_filter_profile_as` теперь ждёт
  `document.readyState == 'complete'` пост-save навигации перед
  `open_tab("Settings")` — закрывает ИМЕННО ту гонку (tree-dump поверх
  mid-render), что диагностировал critic изначально; (2)
  `sort_filter_form.mitm` пересобран самодостаточным для ПЕРВОЙ живой
  страницы (`<link>/<script src>`/внешний `<img>` вырезаны из тела —
  форма/кнопка не зависят от site-JS/CSS, проверено по коду). Прогоны:
  1-й PASS (`PYTEST_EXIT=0`, 46.65s, только фикс 1) → 2-й FAIL (краш
  qemu 03:04:32 local, ДРУГОЙ шаг — первая загрузка формы, не Settings)
  → применён фикс 2 → 3-й FAIL (краш qemu 03:14:33 local, ТРЕТИЙ шаг —
  внутри самой пост-save навигации, которая по-прежнему форвардит живьём
  целиком, включая СВОИ `<link>/<script src>`, т.к. это ВТОРОЙ документ,
  не покрытый фиксом 2). 1 PASS из 3 прогонов TC-040; TC-041 (регрессия,
  не пересекается с фикстурой/шагами TC-040) зелёный все разы.
- Что нужно от человека/critic: (а) решение — завершать ли вариант 1
  полностью (записать/подготовить И post-save filtered-URL, детерминируем
  статическим разбором `ao3_bridge.js`-логики сборки `qs` + дефолтов
  формы, как второй `.mitm`-flow с тем же усечением) ИЛИ переходить к
  варианту 3 (env: `-gpu swiftshader_indirect` в параметрах эмулятора —
  правка `tasks.ps1`/AVD-конфига, инфраструктурный мехнизм шире мандата
  test-maintainer по `framework/`/`test-cases/`); (б) не исключено, что
  это НЕ специфика TC-040/`sort_filter_form.mitm`, а более общая хрупкость
  GPU-эмуляции (WHPX) под нагрузкой рендера ЛЮБОЙ тяжёлой live AO3-страницы
  — см. в bug-файле названную (не подтверждённую) ось `open_stable_tall_page`
  (`/tos`, AT-BUG-015) как сиблинг для точечной проверки, если решение (а)
  склонится к варианту 3.
- Текущее состояние теста: `test_save_filter_profile` (TC-040) снова под
  `@pytest.mark.skip(reason="AT-BUG-016...")` — guard от повторных крашей
  эмулятора в regression/p1 до решения выше. Окружение оставлено здоровым
  (`Start-Emulator -WritableSystem` → `Get-Device: DEVICE` → `Install-App:
  Success` → `Start-Appium: ready`) для следующего агента.
- Статус: **resolved 2026-07-19** — критик дал явную директиву (закрыть
  последнюю live-forward точку вариантом 1 полностью + проверить глубину
  усечения), test-maintainer выполнил буквально в 3-м заходе: записан
  второй self-contained flow для пост-save навигации (URL выведен
  статическим разбором формы, подтверждён диагностическим mitm-addon
  логом — `is_replay=response`, ни одного forward), краш qemu пропал
  полностью. Вскрылась и закрыта вторая причина (не входившая в исходный
  диагноз): усечение `<link>` сняло CSS-скрытие `.narrow-hidden`/
  `.dropdown .menu`, из-за чего `navigation.py::_find_pill` мискликал
  ссылку внутри WebView — восстановлено минимальным inline `<style>`.
  TC-040 3 зелёных подряд, TC-041 регрессия зелёная, `automated_by`
  заполнен, skip снят. Гипотеза systemic SwiftShader-хрупкости — снята
  (полная изоляция убрала краш без env-митигации, стоп-гейт варианта 3
  не потребовался). Полный след — `bugs/AT-BUG-016.md` «Обсуждение»
  запись 2026-07-19T01:52:53Z.

## ESC-003 — AT-BUG-018, TC-026 long-press поверх WebView — механизм недостижим 5-м/6-м независимым способом подряд

- Артефакт: `bugs/AT-BUG-018.md` (status: Open, lock снят)
- С какого времени: 2026-07-19T02:09:49Z
- Причина: B4-починка (test_debt, major, `debt_kind: broken_environment`).
  Прочитан `app-under-test/.../ui/browser/BrowserScreen.kt` целиком (READ-ONLY,
  критерий готовности п.(в)) — блокирующего `setOnTouchListener`/программного
  запрета `longClickable` НЕ найдено; найдена анцесторная Compose
  `pointerInput` на `Box`, оборачивающем `AndroidView(WebView)` (kt:254-312) —
  правдоподобная, НО НЕ эмпирически подтверждённая гипотеза дополнительного
  источника нестабильности (не consume'ит однопальцевые события, но участвует
  в диспетчеризации). Опробованы 2 НОВЫХ направления инъекции (не входили в
  исходные 3 механизма): (a) `mobile: longClickGesture` с `elementId`
  нативного WebView-контейнера + офсет, (b) сырые W3C Actions с micro-jitter
  между `pointer_down`/`pointer_up`. Координата ре-валидирована контрольным
  коротким тапом в этом прогоне (навигация подтверждена). Результат: 0/8 на
  обоих новых направлениях (живой прогон, witness в `bugs/AT-BUG-018.md`
  «Обсуждение» 2026-07-19) — хуже исходных 12 попыток (1/12). Суммарно 1/20
  (5%) по 5 независимым механизмам инъекции. Правило 6 (эскалация после 1-2
  разумных попыток) применено — форсированное закрытие НЕ делалось.
- Что нужно от человека (Lead/test-strategist): решение по критерию
  готовности п.2 — рекомендация test-maintainer: TC-026 остаётся ПОСТОЯННО НЕ
  автоматизированным (ручной/exploratory regression), заметка кейса дополняется
  явным «ограничение инструментария, не test_debt конкретного теста».
  Альтернатива через Library→open work (уже используется TC-058-подобно,
  `framework/tests/test_side_panel.py:233-238`) даёт тот же наблюдаемый эффект
  «2 вкладки, активная не переключилась», но идёт ДРУГИМ код-путём (не
  `WebView.setOnLongClickListener`+`HitTestResult`) — НЕ покрывает риск R-08
  как есть; принятие такой замены требует явного решения test-designer/
  test-strategist о пересмотре скоупа TC-026, не решения test-maintainer.
  Опционально: оценить целесообразность запроса продуктовой команде на
  debug-хук (broadcast/instrumentation) для `openTab(background=true)` —
  правка `app-under-test/`, вне мандата test-maintainer.
- Статус: **resolved 2026-07-19T10:40:00Z** — финальная разведка (решение
  оператора, 2 новых направления) нашла рабочий механизм: `mobile:
  longClickGesture` по `elementId` native a11y-узла ссылки внутри WebView
  (находка `bugs/AT-BUG-019.md` — ссылки экспонируются UiAutomator2 как
  отдельные native-узлы, не часть контейнера WebView). TC-026 автоматизирован
  (`framework/tests/test_tabs.py::
  test_long_press_link_opens_background_tab_without_switching`), 3+1 зелёных
  прогона подряд, `automated_by` заполнен, `bugs/AT-BUG-018.md` переведён
  `Open → Fixed`. Полный след — `bugs/AT-BUG-018.md` «Обсуждение» запись
  2026-07-19T10:40:00Z.

## ESC-004 — TC-009[READ-work2] детерминированно падает на open_tab("Library") после dismiss_rating_overlay, не связано с batch B canary

- Артефакт: `framework/tests/test_rating_listing.py::test_rate_work_from_listing_overlay[listing_basic.mitm-READ-work2]` (TC-009, p0, уже Automated до этой сессии)
- С какого времени: 2026-07-19T05:21:48Z (первый прогон полного p0-регресса после batch B)
- Причина: полный p0-регресс (38 тестов, `Invoke-Pytest -m p0`, PYTEST_EXIT=1,
  35 passed / 3 failed) после автоматизации batch B (TC-072..077, канарейка
  bridge-rate-note-tag-buttons R-02/R-04) дал 3 падения: `TC-007[READ]`
  (chromedriver `no such execution context: loader has changed while
  resolving nodes` при создании сессии), `TC-015` (`swipe_to_text` не нашёл
  "Hide Disliked works" в Settings), `TC-009[READ-work2]` (`TimeoutException`
  на `BottomNav.open("Library")` после `dismiss_rating_overlay`). Повторный
  прогон ЭТИХ ЖЕ 11 тестов (все параметризации TC-007/TC-009 + TC-015) БЕЗ
  конкурентной нагрузки: TC-007 и TC-015 прошли ВСЕМИ вариантами (не
  воспроизвелись — похоже на конкуренцию за хост-ресурсы во время
  18-минутного марафона, не код), но `TC-009[READ-work2]` упал СНОВА на том
  же месте. Изолированный прогон именно этого узла (`pytest
  tests/test_rating_listing.py::test_rate_work_from_listing_overlay[listing_basic.mitm-READ-work2]`)
  ЕЩЁ 3 раза подряд — 3/3 FAIL, идентичная точка и трасса
  (`NoSuchElementError` на `UiSelector().text("Library")` сразу после
  `dismiss_rating_overlay`). ДЕТЕРМИНИРОВАННО, не флейк.
- Почему НЕ регрессия batch B (доказано, не предположение): `git diff`
  против HEAD показывает `framework/screens/navigation.py` и
  `framework/steps/app_steps.py` (весь код-путь `open_tab`/`BottomNav.open`)
  БЕЗ единого изменения; `framework/screens/rating_overlay.py` и
  `framework/steps/rating_steps.py` — только ДОБАВЛЕННЫЕ новые
  методы/функции (TC-074/076 live-ввод note/tag), ни одна существующая
  строка (`dismiss()`, `choose()`, `is_visible()`, `rate_via_listing_overlay`,
  `assert_rating_button_selected`, `dismiss_rating_overlay`) не тронута.
  Единственная модификация в самом коде-пути этого теста —
  `browser_steps.tap_rate_button` (Selenium `.click()` → JS
  `element.click()`, чинит `ElementNotInteractableException` от
  `div#tos_prompt` на живом archiveofourown.org, TC-072/074/076) — она
  успешно отрабатывает РАНЬШЕ падения (доказано: `assert_rating_button_
  selected`/`assert_rating_badge_visible` дальше по тому же тесту проходят).
  Падает код, идентичный уже закоммиченному состоянию, специфично для
  комбинации READ/work2 — похоже на существующий test debt (test-maintainer
  область), не связанный с batch B.
- Что нужно от человека/test-maintainer: диагностика, почему именно
  READ-вариант TC-009 детерминированно не находит вкладку "Library" после
  `dismiss_rating_overlay` (гипотеза — тайминг scrim-тапа/анимации закрытия
  bottom-sheet специфичен для этой комбинации рейтинга/работы, не
  проверялась глубже — вне мандата test-automator). batch B (TC-072..077)
  этой находкой НЕ блокирован — все 6 новых кейсов прошли 3/3 изолированно
  и присутствуют/зелёные в этом же полном регрессе.
- ПОПРАВКА critic (2026-07-19, ревью приёмки batch B): исходная формулировка
  «доказано, не регрессия batch B» переоценена — доказано только, что
  падающая строка не отредактирована; вклад ЕДИНСТВЕННОЙ реальной правки
  код-пути (`tap_rate_button`: JS-клик + `scrollIntoView`) через побочный
  эффект (сдвиг раскладки → `dismiss_rating_overlay` промахивается по scrim)
  НЕ исключён. Согласовать с видимым противоречием: `bugs/AT-BUG-017.md`
  несёт witness ОТ ТОГО ЖЕ ДНЯ с 12/12 passed (до правки `scrollIntoView`).
- Статус: **resolved 2026-07-19** — регресс вынесен из этой чисто
  информационной записи в машиночитаемый артефакт `bugs/AT-BUG-020.md`
  (test_debt, flaky_test, major, Open; `defect_found` в routing-log,
  ref=TC-009), т.к. B4-сканер очереди читает `bugs/*.md`, не
  `escalations.md` — здесь долг был бы невидим конвейеру. Дальнейшее
  ведение — в AT-BUG-020.md.

## ESC-005 — TC-020 Blocked до фикса BUG-012 (эффект перехода *→Blocked, матрица transitions)

- Артефакт: `test-cases/settings/TC-020.md` (status: Blocked,
  blocked_reason: product_decision), `bugs/BUG-012.md` (Open,
  awaiting: dev, known_issue: true)
- С какого времени: 2026-07-19T09:55:00Z
- Причина: РЕШЕНИЕ ОПЕРАТОРА (триаж, 2026-07-19): BUG-012 подтверждён
  как APP_BUG с низким приоритетом — Clear all ratings обязан обновлять
  бейджи открытых вкладок без reload (PROJECT.md §9 корректен, Then
  TC-020 не переформулируется). До фикса приложения автоматизация TC-020
  детерминированно красная — кейс выведен из очереди правила 14
  переходом в Blocked (иначе холостые диспатчи test-automator каждый
  проход). Это НЕ деградация и НЕ нерешённый вопрос — запись
  информационная, по эффекту перехода `*→Blocked` (матрица требует
  строку эскалации).
- Что нужно от человека: ничего сейчас; фикс BUG-012 разработчиком в
  своём темпе (приоритет низкий). При переводе BUG-012 в Fixed —
  вернуть TC-020 в Approved (D1-верификация включит снятие
  @pytest.mark.skip и прогон готового теста).
- Статус: **open** (закрывается верификацией фикса BUG-012; контроль
  «не ухудшился» на новых сборках держит known_issue: true → правило D3)
- [2026-07-21T08:57:20Z] **BUG-012** [sla:question_unanswered] — ждёт ответа разработчика (awaiting: dev) с 2026-07-18T12:00:00Z | нужно: ответить в ## Обсуждение
- [2026-07-21T08:57:20Z] **TC-020** [sla:blocked_any] — в Blocked с 2026-07-19T09:55:00Z (причина: product_decision) | нужно: разобрать причину и вывести из Blocked
