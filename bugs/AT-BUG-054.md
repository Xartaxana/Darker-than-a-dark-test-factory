---
id: AT-BUG-054
title: "Replay-фикстура listing_paginated.mitm несёт class=\"work blurp\" вместо \"work blurb\" — листинговая страница не опознаётся ни тестом, ни bridge'ем (TC-129/TC-130 broken)"
type: test_debt
debt_kind: missing_fixture
severity: major
status: Verified
found_in: "framework commit 2f26f8a (тестируемая сборка приложения 1.10 (versionCode 11), build 6455af0c — от сборки НЕ зависит)"
fixed_in: "350f852"
last_seen_in: "RUN-20260810-0146 (2026-08-10)"
test_cases: ["TC-129", "TC-130"]
runs: ["RUN-20260804-1624", "RUN-20260810-0146"]
duplicates: []
regression_of: ""
status_since: "2026-08-10T12:27:46Z"
updated: "2026-08-10T12:27:46Z"
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

# AT-BUG-054 — испорченный класс блёрба в `listing_paginated.mitm`

## Окружение

Долг тестовой системы (`type: test_debt`, `debt_kind: missing_fixture`),
поверхность — единственный файл replay-фикстуры
`framework/data/recordings/listing_paginated.mitm`. От сборки приложения не
зависит.

## Суть долга

Во всех 5 записанных страницах листинга (`page=1..5`) блёрб работы несёт

```html
<li id="work_9000000NN" class="work blurp group work-9000000NN" role="article">
```

вместо `class="work blurb group ..."`. Замена равной длины (5 байт на
страницу, 5 отличий на весь файл — сверено побайтовым диффом против копии
`scratchpad/rehearsal-backups/listing_paginated.mitm`: `blurb` 5→0,
`blurp` 0→5, длина файла не изменилась).

Следствие — двойное:

1. **Тест не видит страницу.** `browser_steps.open_listing` ждёт появления
   блёрбов по `li[id^="work_"].work.blurb`; оба теста уходят в `broken` на
   этом шаге: `TimeoutException: листинговая replay-страница не загрузилась
   (нет блёрбов работ)` (шаг `When открыта листинговая страница (replay-
   фикстура) '…ao3_companion_fixture=listing_paginated'`).
2. **Приложение тоже не видит страницу** — гейт infinite-scroll
   `ao3_bridge.js:530` и вся инъекция Rate-кнопок стоят на том же селекторе
   `li[id^="work_"].work.blurb`. То есть фикстура перестала быть валидной
   моделью листинга AO3 для проверяемого поведения в принципе, а не только
   для селектора теста.

## Почему это НЕ `SITE_CHANGED` (провенанс)

- Генератор самой записи (`framework/data/recording_builder.py:279`,
  `_blurb_html`) до сих пор выпускает `class="work blurb group work-{wid}"` —
  файл разошёлся со СВОИМ генератором, значит запись правили руками, а не
  перезаписывали с живого AO3.
- Токен `blurp` в разметке AO3 не существует; остальные записи
  (`listing_basic.mitm` — 10 вхождений `blurb`, `works_multi.mitm`,
  `listing_duplicate_work.mitm`) не тронуты, `blurp` в них 0.
- Файл изменён коммитом `2f26f8a` тестового репозитория; сессии
  перезаписи с живого AO3 в этом коммите нет.
- Живой AO3 в тот же день зелёный на листинговых кейсах
  (`RUN-20260804-1355`, canary 10/10 live) — расхождение односторонее и
  лежит в НАШЕЙ записи.

## Как чинить (для test-maintainer)

Восстановить `blurb` в `framework/data/recordings/listing_paginated.mitm`
(перегенерация записи штатным путём — `scripts/build_replay_recordings.py` /
`recording_builder`, а не точечная правка байтов), прогнать TC-129/TC-130.
Класс, а не экземпляр: у фабрики нет ни одной проверки, что содержимое
`.mitm`-записи соответствует своему генератору — рядом с починкой
завести/усилить device-free юнит (`framework/tests/test_recording_builder_unit.py`
уже читает эти flow'ы), который сверяет разметку блёрбов записи с
`_blurb_html`; тогда порча записи ловится юнитом за секунды, а не 40-минутным
device-прогоном.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| 2026-08-10 | 1.10 (11), сборка приложения не тронута (test_debt в обвязке) | `Invoke-Pytest -k test_infinite_scroll -v` (TC-129 `test_infinite_scroll_on_loads_next_page_in_background`, TC-130 `test_infinite_scroll_off_keeps_native_pagination`) — 3 прогона подряд | run1 `2 passed, 320 deselected in 84.05s (0:01:24)`, run2 `2 passed, 320 deselected in 84.44s (0:01:24)`, run3 `2 passed, 320 deselected in 85.35s (0:01:25)`, все три `PYTEST_EXIT=0` | Fixed (test-maintainer; таблица верификации D1 — за fix-verifier следующим проходом) |
| 2026-08-10T12:27:46Z | source_commit 6f884d97, APK versionCode 12/dev-local (test_debt в обвязке фреймворка, сборка приложения не тронута фиксом) | fix-verifier, независимый прогон: `Invoke-Pytest -k test_infinite_scroll -v` — TC-129/TC-130 (оба); device-free юнит-слайс `Invoke-Pytest tests/test_recording_builder_unit.py -v` (52 кейса, включая guard-параметризацию всех сиблингов) | device: `2 passed, 338 deselected in 87.03s (0:01:27)` `PYTEST_EXIT=0`; юнит: 52 из 52 passed в составе объединённого прогона (см. «Обсуждение») `PYTEST_EXIT=0` | **Verified** — fix-verifier, D1 mode=verify, независимое подтверждение поверх 3x-серии maintainer'а |

## Обсуждение

**2026-08-10T09:52:00Z — test-maintainer, фикс (B4):**

Причина устранена по месту (не замаскирована), не байтовой правкой:
перегенерирована `framework/data/recordings/listing_paginated.mitm`
штатным путём (`framework/.venv/Scripts/python.exe
scripts/build_replay_recordings.py`) — генератор (`_blurb_html`) уже
выпускал корректный `class="work blurb ..."`, порча была только в
записанном бинарном файле. `git status --porcelain --
framework/data/recordings/` после перегенерации показал изменённым
ТОЛЬКО `listing_paginated.mitm` — остальные 5 записей байт-в-байт не
изменились (детерминированный генератор), подтверждая триаж бага, что
`listing_basic.mitm`/`works_multi.mitm`/`listing_duplicate_work.mitm` и
т.д. порчей не затронуты.

**Класс, не экземпляр — device-free юнит на дрейф записи от
генератора:** у фабрики не было ни одной проверки, что содержимое
`.mitm`-записи соответствует своему генератору. Добавлено в
`framework/tests/test_recording_builder_unit.py`:
`test_listing_paginated_blurb_markup_matches_generator` (параметризован
по всем 5 страницам) плюс тот же приём для СИБЛИНГОВ, несущих блёрб
через `render_listing_html`/`_blurb_html` — `listing_basic.mitm`
(`test_listing_basic_blurb_markup_matches_generator`),
`listing_duplicate_work.mitm`
(`test_listing_duplicate_work_blurb_markup_matches_generator`, новая
фикстура `listing_duplicate_work_flows` — файл раньше не читался ни
одним device-free юнитом) и `works_multi.mitm`
(`test_works_multi_blurb_markup_matches_generator`). Каждый тест
сверяет РЕАЛЬНУЮ разметку блёрба, прочитанную из собранного `.mitm`,
побайтово (`expected in body`) со СВЕЖИМ выводом `rb._blurb_html(work)`
— ловит будущий дрейф ЛЮБОЙ из этих записей от генератора за секунды
device-free юнитом, не 40-минутным device-прогоном.

Красная проба (ДО перегенерации, снята против текущего испорченного
состояния дерева — байтовая копия снята в
`scratchpad/.../at-bug-054/listing_paginated.mitm.orig` до правки,
CLAUDE.md п.8): `Invoke-Pytest tests/test_recording_builder_unit.py -k
blurb_markup_matches_generator -v` → `5 failed, 3 passed` — все 5
`test_listing_paginated_blurb_markup_matches_generator[1..5]` упали
(diff явно показывает `class="work blurp ..."` в записи против
`class="work blurb ..."` в `expected`), три сиблинг-теста
(`listing_basic`/`listing_duplicate_work`/`works_multi`) уже были
зелёными — подтверждает, что порча была изолирована в
`listing_paginated.mitm`. После перегенерации — тот же прогон:
`52 passed in 0.30s`, `PYTEST_EXIT=0`.

Прогон `Invoke-Pytest -k test_infinite_scroll -v` — 3 раза подряд, все
зелёные (см. таблица верификации выше), `Get-Device` →
`DEVICE: emulator-5554` перед прогонами.

`git status --porcelain -- app-under-test/` — пустой вывод (ни одна
правка приложения не затронута); дифф целиком в
`framework/data/recordings/listing_paginated.mitm` (regenerated) и
`framework/tests/test_recording_builder_unit.py` (новые юниты), коммит
`350f852`.

Новых блокеров/долгов в ходе работы не найдено.

Статус: `Open` → `Fixed`. Лок снят.

**2026-08-10T12:27:46Z — fix-verifier (D1, mode=verify):** независимый
прогон на актуальном HEAD (фикс `350f852` в дереве). Device-free юнит-слайс
`Invoke-Pytest tests/test_recording_builder_unit.py tests/test_adb_run_as_file_or_raise_unit.py
tests/test_parse_persisted_tabs_unit.py -v` (объединённый прогон трёх
файлов, засчитан и для AT-BUG-055) — `70 passed in 0.37s`, `PYTEST_EXIT=0`;
из них 52 принадлежат `test_recording_builder_unit.py`, включая все 5
параметризаций `test_listing_paginated_blurb_markup_matches_generator` и
сиблинг-гарды `listing_basic`/`listing_duplicate_work`/`works_multi`.
Device-прогон `Invoke-Pytest -k test_infinite_scroll -v` на `emulator-5554`
(`Get-Device` → `DEVICE`) — TC-129/TC-130 оба зелёные: `2 passed, 338
deselected in 87.03s (0:01:27)`, `PYTEST_EXIT=0`. Сборка приложения —
`source_commit 6f884d97`, установленный APK `versionCode 12`/`dev-local`
(`output-metadata.json`), долг в обвязке (фикстура), от сборки не зависит.
`Fixed` → `Verified`, лок снят.

## Ссылки

- Прогон: `runs/RUN-20260804-1624.md` (раздел «Падения и триаж», вердикт `TEST_BUG`)
- Артефакты: `runs/RUN-20260804-1624/allure/dd15f724-aaea-4981-8269-96e52e3c1793-result.json` (TC-129),
  `runs/RUN-20260804-1624/allure/47d6e46e-0d54-49a6-bf67-9ea3db7a68c9-result.json` (TC-130)
- Кейсы: `test-cases/settings/TC-129.md`, `test-cases/browser/TC-130.md`
