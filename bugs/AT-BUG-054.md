---
id: AT-BUG-054
title: "Replay-фикстура listing_paginated.mitm несёт class=\"work blurp\" вместо \"work blurb\" — листинговая страница не опознаётся ни тестом, ни bridge'ем (TC-129/TC-130 broken)"
type: test_debt
debt_kind: missing_fixture
severity: major
status: Open
found_in: "framework commit 2f26f8a (тестируемая сборка приложения 1.10 (versionCode 11), build 6455af0c — от сборки НЕ зависит)"
fixed_in: ""
last_seen_in: "RUN-20260804-1624 (2026-08-04)"
test_cases: ["TC-129", "TC-130"]
runs: ["RUN-20260804-1624"]
duplicates: []
regression_of: ""
status_since: "2026-08-04T22:20:45Z"
updated: "2026-08-04T22:20:45Z"
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

## Ссылки

- Прогон: `runs/RUN-20260804-1624.md` (раздел «Падения и триаж», вердикт `TEST_BUG`)
- Артефакты: `runs/RUN-20260804-1624/allure/dd15f724-aaea-4981-8269-96e52e3c1793-result.json` (TC-129),
  `runs/RUN-20260804-1624/allure/47d6e46e-0d54-49a6-bf67-9ea3db7a68c9-result.json` (TC-130)
- Кейсы: `test-cases/settings/TC-129.md`, `test-cases/browser/TC-130.md`
