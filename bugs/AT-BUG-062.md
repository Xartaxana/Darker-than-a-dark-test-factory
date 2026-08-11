---
id: AT-BUG-062
title: "Нестабильный TC-085 (rename filter-profile): «профиль «My renamed search» не найден в списке Settings» в полном регрессе, 3/3 зелёный в изоляции; артефакт падения не содержит секцию Saved AO3 Filters (фолбэк swipe_up возвращает список наверх)"
type: test_debt
debt_kind: flaky_test
severity: major
status: Fixed
found_in: "source_commit cc201f789f0fb123722bbba7b29b8e0c6412dac1 (versionName dev-local, versionCode 12) — от сборки НЕ зависит, см. «Почему не сборка»"
fixed_in: "framework/screens/settings_screen.py, framework/screens/base_screen.py, framework/steps/settings_steps.py, framework/steps/saf_steps.py, framework/tests/test_rename_name_verification_unit.py, scripts/arch_check.py (тестовая обвязка, не app-under-test)"
last_seen_in: "RUN-20260811-0406 (2026-08-11)"
test_cases: ["TC-085"]
runs: ["RUN-20260811-0406"]
duplicates: []
regression_of: ""
status_since: "2026-08-11T16:53:33Z"
updated: "2026-08-11T17:13:00Z"
reopen_count: 0
dispute_count: 0
awaiting: none
resolution: ""
resolution_comment: ""
known_issue: "false"
blocked_reason: ""
lock: ""
gitlab_issue: ""
---

# AT-BUG-062 — карантин TC-085: после переименования профиль не найден в списке Settings; в изоляции не воспроизводится

## Окружение

Долг тестовой системы (`type: test_debt`, `debt_kind: flaky_test`). Поверхность:
`framework/tests/test_filter_profiles.py::test_rename_filter_profile_keeps_query_string`
(`@pytest.mark.p1`, `@pytest.mark.replay`, `listing_basic.mitm`),
`framework/steps/settings_steps.py:507` (`assert_filter_profile_listed`),
`framework/screens/settings_screen.py:224-233` (`_swipe_to_profile`/`has_filter_profile`),
`:279-293` (`enter_rename_name`/`confirm_rename`/`rename_filter_profile`),
`framework/screens/base_screen.py:120-183` (`_swipe_search`, AT-BUG-048).
Эмулятор `ao3_test_api34` (`emulator-5554`, API 34), Appium `:4723`, replay.

## Наблюдение

| Прогон | Дата | Исход | Сообщение |
|---|---|---|---|
| `RUN-20260811-0406` (regression, replay, сборка cc201f78) | 2026-08-11 | FAILED | `AssertionError: фильтр-профиль «My renamed search» не найден в списке Settings` (`steps/settings_steps.py:507`, тест — строка 107) |

Ключевые детали артефакта
(`runs/RUN-20260811-0406/allure/544709d4-31fe-419d-ae74-857cf09948b4-result.json`):

- Шаги ДО ассерта — зелёные, в т.ч. `When в Settings профиль «My saved search»
  переименован в «My renamed search»` (диалог открылся, поле заполнено,
  подтверждение нажато — 3.29с).
- Две diagnostic-аттачки `swipe_to_text` (AT-BUG-048), обе дословно:
  `«My renamed search»: КОНЕЦ СПИСКА (позиция не изменилась после свайпа) —
  строка не поймана, список исчерпан` — то есть и прямой (`swipe_to_text`),
  и обратный (`swipe_up_to_text`) проход упёрлись в границу списка.
- `page_source` момента падения
  (`d95ea445-623b-41da-b259-3dc4ecae3a84-attachment.xml`) содержит ВЕРХ Settings
  (`READER`/`Theme`/…/`CONTENT VISIBILITY`/`Hide Kudosed works`) — секции
  `SAVED AO3 FILTERS` в дампе НЕТ. Причина — не состояние приложения, а сам
  хелпер: `_swipe_to_profile` = `swipe_to_text(...) or swipe_up_to_text(...)`,
  и фолбэк возвращает список НАВЕРХ, поэтому снимок/скриншот делаются уже не на
  той секции, которую проверял ассерт.
- `logcat` (`e34e1362-…`) покрывает только последние ~6с (обратный проход):
  `Matched 0 elements using selector UiSelector[TEXT=My renamed search]` ×4
  (settle-окно `poll_for`), затем конец списка.

## Изолированные перепрогоны (failure-analyst, 2026-08-11, та же сборка cc201f789, `Get-Device` → `DEVICE: emulator-5554`, Appium `:4723` ready)

```
Invoke-Pytest -k test_rename_filter_profile_keeps_query_string -q
  1 passed, 370 deselected in 85.08s   PYTEST_EXIT=0
  1 passed, 370 deselected in 84.02s   PYTEST_EXIT=0
  1 passed, 370 deselected in 85.57s   PYTEST_EXIT=0
```

3/3 зелёный — сигнатура падения не воспроизводится изолированно.

Две попытки файлового перепрогона (`Invoke-Pytest tests/test_filter_profiles.py -q`,
чтобы проверить зависимость от контекста файла) НЕ дали чистого замера — обе
деградировали по окружению, а не по ассерту:

- попытка 1: `3 failed, 2 passed in 354.95s`; TC-085 при этом ПРОШЁЛ строку 107
  (тот самый ассерт, что красный в прогоне) и упал ПОЗЖЕ, на строке 108, с
  `WebDriverException: Could not proxy command … connect ECONNREFUSED 127.0.0.1:8200`;
  в конце — `ENV_ISSUE (AT-BUG-026): device-liveness guard recoveries this session = 1/2`;
- попытка 2: `3 failed, 1 passed, 1 error in 178.46s`; TC-085 — `ERROR at setup`
  (device-liveness guard), остальные — `socket hang up` того же класса.

Итог замера: 3/3 зелёных изолированно + один проход мимо целевого ассерта в
файловом контексте; детерминированной поломки нет.

## Почему это НЕ сборка приложения и НЕ прежний долг AT-BUG-053

1. **Не сборка.** Диапазон `6f884d979..cc201f789` (`git -C app-under-test diff --stat`)
   трогает ровно 6 файлов: `.gitlab-ci.yml`, `PROJECT.md`,
   `app/src/main/assets/ao3_bridge.js`, `data/repository/DownloadRepository.kt`,
   `ui/browser/BottomBar.kt`, `ui/browser/BrowserViewModel.kt`. Ни
   `ui/settings/SettingsScreen.kt`, ни `SettingsViewModel` (`requestRenameFilter`/
   `confirmRenameFilter`), ни слой `FilterProfile`-репозитория не изменялись —
   путь переименования в приложении тот же, что на прошлой (зелёной для этого
   теста) проверке.
2. **В ТОМ ЖЕ прогоне зелёный TC-086** (`test_rename_filter_profile_to_duplicate_name`,
   тот же файл, тот же диалог «Rename filter», тот же
   `settings_screen.rename_filter_profile`, ассерт по UI-списку
   `assert_filter_profile_count(name_a, 2)`) — механизм переименования и
   отображения списка на этой сборке работает.
3. **Не AT-BUG-053** (`weak_locator`, `content-desc="Renam3"`, `Verified`
   2026-08-10 фиксом `d96eef9`): та сигнатура —
   `TimeoutException: не кликабелен ('xpath', '(//*[@text="My saved search"]/
   following::*[@content-desc="Renam3"])[1]')` на шаге ОТКРЫТИЯ диалога. Здесь
   шаг переименования зелёный, падение — на следующем ассерте, с другим
   сообщением. Совпадает только номер кейса.

## Почему причина не установлена (и почему это долг)

Артефакт падения не позволяет отличить две живые гипотезы, и обе — про тестовую
обвязку:

1. **Гонка ввода в диалоге.** `enter_rename_name` делает `field.clear()` +
   `field.send_keys(new_name)` без верификации фактического содержимого поля, а
   `confirm_rename` тапает `by_text("Rename")` без проверки, что кнопка активна
   (`enabled = dialogName.isNotBlank()` в приложении). Под нагрузкой полного
   регресса профиль мог быть сохранён под ДРУГИМ именем (частичный ввод/
   конкатенация) — тогда ассерт красный законно, но причина в шаге, а не в
   приложении.
2. **Промах поиска прокруткой.** Остаточный класс AT-BUG-048: строка есть, но
   settle-окно `poll_for` (1.2с/0.3с) её не застало ни в прямом, ни в обратном
   проходе.

Различить их по артефактам НЕЛЬЗЯ именно из-за диагностического пробела:
снимок/скриншот сделаны после фолбэк-свайпа наверх и не содержат секцию
`SAVED AO3 FILTERS` — то есть фактические имена профилей в момент падения
неизвестны. Тот же класс слепого наблюдения, что `AT-BUG-055`/`AT-BUG-057`
(«ассерт сообщает только факт отсутствия, не состояние экрана»).

## Что сделать (test-maintainer)

1. **Диагностика на месте падения.** `settings_steps.assert_filter_profile_listed`
   при провале обязан сообщать ФАКТИЧЕСКИЙ список имён профилей (например,
   `_scroll_fingerprint`-подобный сбор текстов на секции или чтение
   `seed_db.read_filter_profiles()` host-side, как уже делает
   `assert_filter_profiles_have_query_strings`) — тогда следующее падение само
   различит «имя другое» от «строка не поймана прокруткой».
2. **Снимок ПЕРЕД фолбэком.** Класс, а не экземпляр: `_swipe_to_profile`
   (`swipe_to_text(...) or swipe_up_to_text(...)`) — общий приём для
   `has_filter_profile`/`delete_filter_profile`/`count_filter_profile_occurrences`/
   `open_rename_dialog`; в случае неуспеха он всегда оставляет список НАВЕРХУ, и
   любой из этих ассертов даёт бесполезный page source. Прикладывать снимок
   состояния до фолбэка (или явно фиксировать позицию, где искомого нет).
3. **Верификация ввода в `enter_rename_name`**: после `clear()`+`send_keys`
   сверить `get_attribute("text")` поля с ожидаемым именем до подтверждения
   (устраняет гипотезу 1 навсегда и делает падение говорящим).
4. Снять карантин (`automation_status: quarantined → active`) после серии из 3
   зелёных прогонов на исправленном тесте (и, желательно, одного зелёного
   `tests/test_filter_profiles.py` целиком на здоровом окружении).

## Карантин

`test-cases/filter-profiles/TC-085.md`: `automation_status: active → quarantined`
(переход `active → quarantined`, машина `automation`, `schemas/transitions.yaml`,
`by: failure-analyst`), `quarantine_reason` — сигнатура падения,
`quarantine_since: 2026-08-11T02:40:00Z`, `quarantine_owner: test-maintainer`,
`quarantine_expiry` не задан (действует `sla.quarantine_max`).

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| 2026-08-11 | dev-local (versionCode 12, та же сборка cc201f789) | `test_rename_filter_profile_keeps_query_string` ×3 подряд + `tests/test_filter_profiles.py` целиком | `1 passed, 373 deselected in 84.66s`; `1 passed, 373 deselected in 83.19s`; `1 passed, 373 deselected in 81.27s`; файловый прогон: `5 passed in 285.34s` — все PYTEST_EXIT=0 | test-maintainer (fix), D1-верификация fix-verifier — отдельным проходом (B4, сборку ждать не нужно) |

**Условие критика раунда 2, обязательное для будущего D1:** D1 fix-verifier
обязан захватить TC-085 + негативный ассерт TC-042 (`expect_absent`-ветка) +
один rescroll-кейс TC-021 — верификационная таблица attempt 1 сделана ДО
правок `enter_rename_name`/`expect_absent`/`_scroll_settings_to` (rework
attempt 2, non-blockers (а)/(б) выше) и текущий device-код ими не покрыт.

## Обсуждение

**[test-maintainer @ 2026-08-11T17:13:00Z, rework attempt 2 — критик-вход opus
вернул ДОРАБОТАТЬ].** Три блокера критика закрыты, все правки device-free
(эмулятор в этом окне занят параллельной задачей, не потребовался):

1. **Честность корпуса (TC-085.md).** Формулировки «фикс — диагностический
   (устраняет причину...)» и «точный диагноз... — bugs/AT-BUG-062.md»
   противоречили этому же файлу (причина НЕ установлена эмпирически, все 4
   контрольных прогона зелёные). `test-cases/filter-profiles/TC-085.md`
   переформулирован: «гонка ввода исключена как класс (устранена
   возможность, не подтверждена как причина)», «причина исходного падения НЕ
   установлена эмпирически, остаётся открытым вопросом — см.
   bugs/AT-BUG-062.md». Перепрогона не требовало.
2. **Новые ветки отказа исполнены.** Все 4 верификационных прогона attempt 1
   были зелёными — новый код (`enter_rename_name` verification poll,
   `assert_filter_profile_listed` DB-truth) ни разу не сработал по красной
   ветке. Добавлен device-free `framework/tests/test_rename_name_verification_unit.py`
   (фейковый driver/фейковые часы, по образцу
   `test_swipe_to_text_settle_unit.py`, AT-BUG-048) — 4 пробы: (а) поле весь
   бюджет 1.5с показывает ДРУГОЙ текст -> диагностический `AssertionError`,
   не таймаут; (б) поле догоняет в пределах бюджета -> зелёный; (в)
   `assert_filter_profile_listed` на провале несёт фактические имена из БД
   (`seed_db.read_filter_profiles` мокнута); (г) попутный дефект — защищённое
   чтение `_field_text()` не протекает `NoSuchElementException` при
   stale-поле (`IMPLICIT_WAIT=0`, `framework/config/settings.py:50`) —
   `settings_screen.py::enter_rename_name` дочитан try/except-хелпером,
   значение читается ОДИН раз в переменную перед подстановкой в сообщение
   (было: незащищённый повторный вызов прямо в f-string). Красная проба
   (временно снята защита try/except — байтовая копия файла в scratchpad,
   сверка порчи/отката по `CLAUDE.md` permission-hygiene п.8): проба 3
   упала ОСМЫСЛЕННО — `NoSuchElementException` протёк вместо
   `AssertionError`, сигнатура падения ровно на строке незащищённого чтения;
   откачено байтовой копией, `git diff --stat` после отката снова показывает
   только намеренные правки. 3/3 зелёных прогона нового файла (вместе с
   `test_swipe_to_text_settle_unit.py`, регресса на сиблинге нет) после
   отката.
3. **`saf_steps.py:84` — переклассифицирован, не отфутболен повторно.**
   Критик прав: класс DoD п.2 — «фолбэк `swipe_to_text or swipe_up_to_text`
   теряет ПОЗИЦИЮ ОТКАЗА до снимка», а не «качество текста сообщения»; моя
   прошлая формулировка («честный AssertionError, класс не применяется»)
   переопределяла класс вместо того чтобы его оценить.
   `_scroll_settings_to` несёт ТОТ ЖЕ паттерн `swipe_to_text(...) or
   swipe_up_to_text(...)` — применил вариант (а): снимок `page_source` ДО
   фолбэка. Общий хелпер `_attach_pre_fallback_snapshot` поднят из
   `SettingsScreen` в `BaseScreen` (класс, не экземпляр — правило 9;
   единственная точка теперь используется обоими сиблингами:
   `settings_screen.py::_swipe_to_profile` и `saf_steps.py::_scroll_settings_to`).

Non-blockers критика (оба закрыты попутно):
(а) `assert_filter_profile_not_listed`/`_swipe_to_profile`/`has_filter_profile`
получили параметр `expect_absent: bool = False` — негативный ассерт
(TC-085/TC-042, ожидает профиль ОТСУТСТВУЮЩИМ) передаёт `expect_absent=True`
и больше не пишет шумную pre-fallback XML-аттачку в Allure на каждом
зелёном прогоне (снимок нужен только когда «не нашли» — это ОТКАЗ, не
ожидаемый успешный исход).
(б) **Остаточный риск.** Бюджет верификации `enter_rename_name`
(`timeout=1.5s, interval=0.3s`) подобран по прогонам изолированного теста;
под нагрузкой ПОЛНОГО регресса (тот самый контекст, где случилось исходное
падение `RUN-20260811-0406`) recomposition/событийная очередь Compose могут
быть медленнее — бюджет НЕ проверен под такой нагрузкой (изолированные
прогоны — не то же самое, что 70-минутный full regression). Если
`enter_rename_name` начнёт падать НОВЫМ диагностическим сообщением
(«поле содержит X, ожидали Y») именно в full regression — это будет
означать, что 1.5с недостаточно под нагрузкой, не гонку ввода как баг
приложения; тогда бюджет стоит расширить, а не считать находку новым
багом.

Изменённые файлы этим rework: `framework/screens/settings_screen.py`,
`framework/screens/base_screen.py`, `framework/steps/settings_steps.py`,
`framework/steps/saf_steps.py`, `framework/tests/test_rename_name_verification_unit.py`
(новый), `scripts/arch_check.py` (ALLOWLIST-запись для нового device-free
теста — тот же класс исключения, что AT-BUG-059), `test-cases/filter-profiles/TC-085.md`.
`bugs/AT-BUG-062.md`/`test-cases/filter-profiles/TC-085.md` locks сняты.
`python scripts/validate_frontmatter.py` и `python scripts/arch_check.py` —
оба чисто (0 ошибок).

**[test-maintainer @ 2026-08-11T16:53:33Z]** Долг устранён на уровне тестовой
обвязки (диагностика + защита от гонки), `automation_status: quarantined → active`
(`test-cases/filter-profiles/TC-085.md`). Изменения — только `framework/`:

1. `settings_screen.py::enter_rename_name` — после `clear()`+`send_keys` опрашивает
   `get_attribute("text")` поля (poll_for, таймаут 1.5с) до совпадения с ожидаемым
   именем ДО `confirm_rename` — расхождение теперь падает здесь, с точным
   диагнозом, а не молча уходит на ассерт списка Settings под чужим сообщением
   (устраняет гипотезу 1 навсегда, DoD п.3).
2. `settings_screen.py::_swipe_to_profile` (единственная точка `swipe_to_text(...) or
   swipe_up_to_text(...)` для профилей — покрывает разом `has_filter_profile`,
   `delete_filter_profile`, `count_filter_profile_occurrences`, `open_rename_dialog`)
   — перед фолбэком `swipe_up_to_text` прикладывает `page_source` к Allure на
   позиции, где прямой проход не поймал профиль, ДО того как фолбэк вернёт список
   наверх (DoD п.2).
3. `settings_steps.py::assert_filter_profile_listed` — на провале дочитывает
   фактический список имён из БД (`seed_db.read_filter_profiles()`, host-side, без
   остановки приложения — тот же контракт, что уже использует
   `assert_filter_profiles_have_query_strings`) — следующее падение само отличит
   «имя другое» (гипотеза 1) от «строка не поймана прокруткой» (гипотеза 2, DoD п.1).

**Расхождение с диагнозом failure-analyst — явно фиксирую.** Все 4 контрольных
прогона (3× целевой тест + 1× файл) прошли ЗЕЛЁНЫМ на здоровом окружении
(`Get-Device` → `emulator-5554`, Appium `:4723` ready) — исходная сигнатура
падения НЕ воспроизвелась ни разу, симметрично изолированным 3/3 зелёным
failure-analyst. Значит, эмпирически подтвердить, какая из двух гипотез стреляла
в `RUN-20260811-0406`, я НЕ смог — это по-прежнему открытый вопрос для
следующего падения (если оно случится, теперь оно само укажет причину через
пп. 1-3 выше). Не заявляю «починил гонку ввода» как доказанную причину — заявляю
«гонка ввода как класс исключена превентивной проверкой, а диагностический
пробел закрыт для обеих гипотез» (калибровка №3: без исключающего прогона не
пишу «причина установлена»).

**Дефекты-собратья (доклад по правилу 9, scope не расширяю, новых test_debt не
завожу):** тот же паттерн `swipe_to_text(...) or swipe_up_to_text(...)` есть в
`framework/steps/saf_steps.py:84` (`_scroll_settings_to`) — НЕ фиксировал: это
Given-шаг докрутки (setup), а не Then-ассерт с неоднозначным сообщением о
состоянии профиля; при неуспехе там честный `AssertionError` без апелляции к
«найден/не найден» конкретного бизнес-объекта — класс диагностического пробела
AT-BUG-062/AT-BUG-048 к нему не применим впрямую. `AT-BUG-043`/`AT-BUG-026`,
отмеченные failure-analyst как шумящие рядом, не трогал — вне скоупа этого долга,
уже свои открытые долги.

**[failure-analyst @ 2026-08-11T02:40:00Z]** Заведён по вердикту `FLAKY` падения
TC-085 в `runs/RUN-20260811-0406.md` (таблица «Падения и триаж»). Дедуп проверен:
`AT-BUG-053` (тот же TC, другая сигнатура, `Verified`) — не дубликат, см. раздел
«Почему это НЕ …»; `AT-BUG-048` — родственный класс (устойчивость
`swipe_to_text`), но там фикс уже `Verified`, а здесь под вопросом ОСТАТОК класса
плюс отдельный пробел диагностики; заводить как reopen AT-BUG-048 не стал —
поверхность падения другая (шаг rename + ассерт списка), связь отмечена ссылкой.

**Дефекты-собратья (доклад по правилу 9, scope не расширяю):**
`AT-BUG-043` (bind-race порта 8080 mitmdump) снова в teardown этого же теста
(`stderr`-аттачка: «порт 8080 освободился после 2 попыток bind() за 0.10s») и в
smoke `RUN-20260811-0405` (TC-009) — долг заведён, продолжает шуметь.
`AT-BUG-026` (device-liveness guard) сработал в моих файловых перепрогонах
(recoveries 1/2, затем `socket hang up`/`ERROR at setup`) — окружение после
70-минутного регресса деградировало; это наблюдение среды, не причина падения
прогона.
