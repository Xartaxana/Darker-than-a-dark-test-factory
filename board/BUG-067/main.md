---
key: "BUG-067"
project: "AO3"
issueType: "bug"
status: "bug-verified"
priority: "p1"
summary: "auto-READ при дочитывании работы теряет downloadPath и перетирает метаданные у скачанной работы без рейтинга"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "test_case:TC-256", "sev:major"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-16T04:15:00Z"
updated: "2026-08-16T04:15:00Z"
archived: false
resolution: "done"
---

# auto-READ при дочитывании работы теряет downloadPath и перетирает метаданные у скачанной работы без рейтинга

_Спроецировано из `bugs/BUG-067.md` (источник правды).
Статус в нашей машине: **Verified**._

# BUG-067 — auto-READ (`onWorkFinished`) теряет downloadPath и метаданные скачанной работы без рейтинга

## Окружение
- Версия: 1.10+ (живой AO3, вне replay-корпуса; `#chapters` в разметке обязателен)
- Эмулятор: любой (логика UI-независима)
- Режим: **live** (не replay — фикстуры не содержат `<div id="chapters">`)
- Сценарий: автоматическая отметка READ при дочитывании работы (JS `onWorkFinished` →  Kotlin `Ao3JsBridge.onWorkFinished`)

## Шаги воспроизведения (Given-When-Then)

**Given**
- Работа скачана из карточки Library (ao3_id 900000001)
- Room содержит `downloadPath = "/data/…/ao3_Work_900000001.html"`
- Файл лежит на диске
- **Работа НЕ имеет рейтинга** (`rating = null`; допускается личная заметка/тег)
- Пользователь открывает работу на живом archiveofourown.org

**When**
- Пользователь прочитывает ВСЕ главы работы (доходит до конца)
- JavaScript-хук `onWorkFinished` срабатывает (скрейпит title/author/fandom/wordCount) и вызывает Kotlin `Ao3JsBridge.onWorkFinished`

**Then (ожидалось)**
- Рейтинг устанавливается в `Rating.READ` (красна дорожка + значок на карточке Library)
- **Связь с файлом сохраняется:** `downloadPath` остаётся `= "/data/…/ao3_Work_900000001.html"`
- Работа остаётся на вкладке Downloads в Library
- Метаданные (title, fandom, wordCount, author) либо **сохраняют локальные значения**, либо **обновляются видимым диалогом** («Метаданные обновлены со страницы»)

**Actual (фактически)**
- Рейтинг устанавливается в `Rating.READ` ✓
- **`downloadPath` обнулен** → `null` ✗
- Карточка исчезает с вкладки Downloads (следствие)
- Метаданные **молча перетираются скрейпом** (title/author/fandom/wordCount из живого AO3) — могут расходиться с локальными значениями:
  - `fandom` **может быть пустой** `""` (сырой скрейп без `ifBlank`) → `backfillMetadata` не исправит (`?:` ловит только `null`)
  - Сообщение об обновлении отсутствует

## Механизм (по коду BrowserViewModel.kt)

Метод `onWorkFinished` (`:1254-1274`) обрабатывает callback из JavaScript при дочитывании:

```kotlin
@JavascriptInterface
fun onWorkFinished(workId: String, title: String, author: String, fandom: String, wordCount: String) {
    viewModelScope.launch(Dispatchers.IO) {
        val existing = repo.getWorkRating(workId)
        if (existing?.rating != null) return@launch  // ← Условие: rating == null
        val comment = existing?.comment
        val existingTags = existing?.tags
        repo.upsertWorkRating(
            WorkRating(                               // ← КОНСТРУКТОР
                ao3Id = workId,
                title = title,
                author = author,
                url = "https://archiveofourown.org/works/$workId",
                rating = Rating.READ,
                timestamp = System.currentTimeMillis(),
                fandom = fandom,                      // ← Сырой скрейп, может быть ""
                wordCount = wordCount.toIntOrNull(),
                comment = comment,                    // ← Сохраняет
                tags = existingTags,                  // ← Сохраняет
                // ↑ downloadPath ОТСУТСТВУЕТ → дефолт null (WorkRating.kt:17)
            )
        )
        // ...
    }
}
```

**Два класса дефекта (идентичные BUG-021):**

1. **Потеря `downloadPath`**: Конструктор `WorkRating(…)` не принимает `downloadPath` → получает дефолт `null`. Room `upsert` на существующую запись **перезаписывает** все колонки, включая `downloadPath`.

2. **Молчаливая перезапись метаданных**:
   - `title/author/fandom/wordCount` берутся из аргументов (JS-скрейп текущей страницы) БЕЗ `backfillMetadata`
   - Локальные значения, отличающиеся от живой страницы, **затираются**
   - `fandom` пишется СЫРЫМ (без `ifBlank { null }`) → может стать пустой строкой `""`
   - `backfillMetadata` не исправит пустую строку (оператор `?:` ловит только `null`)

**Класс идентичен:**
- **BUG-021** (ветка `:807-813`): `applyRating` overlay листинга при `rating == null` теряет `downloadPath`
- **BUG-048** (вариант А): overlay молча перетирает title/fandom/wordCount пересборщиком

## Достижимость

**ТОЛЬКО на живом AO3**, требует `<div id="chapters">` в разметке:
- `ao3_bridge.js` хук выходит на строке `:1121`, если `!document.getElementById("chapters")`
- Фикстурная work-страница НЕ содержит `#chapters` (строится `render_work_page_html` без этого узла; `:645` `id="chapters"` встречается только в `render_downloaded_work_html`)
- На replay-корпусе **недостижимо** (CH-008 G6: `#chapters=False`; `PERTURBATIONS.md:394`)

## Частота

**100%, гарантированно**, если условия met:
- Скачанная работа без рейтинга
- Дочитывание на живом AO3 (должна существовать хотя бы одна глава)
- JS-хук срабатывает при любом дочитывании

## Артефакты

- **Код якоря:** `app-under-test/app/src/main/java/com/example/ao3_wrapper/ui/browser/BrowserViewModel.kt:1254-1274` (`onWorkFinished`)
- **JS-хук:** `app-under-test/app/src/main/assets/ao3_bridge.js:1114-1147` (`onWorkFinished` вызов) + `:1121` (проверка `#chapters`)
- **Related charter:** `exploratory-charters/CH-008.md:129-147` — раздел Out, пункт про `onWorkFinished`; находка 4 (метаданные уносят фильтруемость); follow-up (а): запрос фикстуры с `#chapters`

## Анализ

### Почему это баг приложения, а не теста/окружения

1. **Воспроизведимо по коду:** Условие `existing?.rating == null` совпадает с ситуацией скачанной работы без рейтинга; конструктор WorkRating не содержит `downloadPath` — это ФАКТ кода, не окружения.

2. **Контрольное сравнение существует:** Панель work-страницы (`savePanelRating` `:698-705`, `:746-753`) использует `existing.copy(…)`, сохраняя `downloadPath` и не перетирая метаданные. Разница — в двух "дверях" одного механизма, обе в `BrowserViewModel`.

3. **Сценарий конечного пользователя:** Скачивание работы + дочитывание её на живом AO3 — штатный flow, не тестовая конструкция.

### Почему это не дубликат BUG-021 и BUG-048

- **BUG-021** закрывает потерю `downloadPath` и `tags` в overlay листинга (точечно — ветка `applyRating` при `rating == null`)
- **BUG-048** закрывает молчаливую перезапись title/fandom/wordCount overlay'ем (общий класс, но ветка overlay листинга)
- **BUG-067** — **`onWorkFinished` из JavaScript**, совсем другая дверь, фактически **не может быть протестирована текущим корпусом фикстур** (live-only)

Фиксы **могут пересечься** в одну правку (оба используют конструктор WorkRating, оба теряют `downloadPath`), но это отдельная находка, мандат критиков-входов при приёмке BUG-021 и BUG-048 не включал эту дверь (она live-only, недостижимая в эксплораторном чартере).

## Верификация (заполняет fix-verifier)

| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| 2026-08-15T23:05:57Z | source_commit `59be96c6398786d33c878dbce33cb1ecde269374` (built_at 2026-08-14T23:14:07Z, dev-local versionCode 12; `git log` подтверждает фикс `07805a9f` предком HEAD) | TC-256 (единственный связанный кейс) — **прогон невозможен**, `automated_by` пуст | Ни replay, ни live не исполнимы: replay заблокирован `bugs/AT-BUG-074.md` (Open, test_debt/missing_fixture — `render_work_page_html` не несёт `#chapters`/`.userstuff.module`/`dd.fandom a`/`dd.words`, JS-хук `onScroll` выходит на guard `ao3_bridge.js:1171`, `Android.onWorkFinished` не вызывается вовсе на текущей `listing_basic.mitm`); live недостижим — синтетический `ao3_id 900000001` даёт 404 на archiveofourown.org (класс `AT-BUG-029`). Structural-only: `git show 07805a9f --stat` подтверждает фикс в `BrowserViewModel.kt` (+27/-18), сообщение коммита описывает устранение ровно этого механизма — но чтение диффа НЕ витнесс исполнения, не заменяет прогон. | **Blocked (эскалация, статус бага не меняю)** — `Fixed → Blocked` отсутствует в `schemas/transitions.yaml` (прецедент ESC-020/BUG-049); подробности `state/escalations.md` ESC-033 |
| 2026-08-16T04:15:00Z | source_commit `27d5cfd193b3e0475b872d5c5c80daadcc299a79` (built_at 2026-08-16T01:01:26Z, dev-local versionCode 12, apk_sha256 `bf17f15f…738e7cd`; `git merge-base --is-ancestor cc201f789f0fb123722bbba7b29b8e0c6412dac1 27d5cfd193b3e0475b872d5c5c80daadcc299a79` → EXIT 0, `found_in` подтверждён предком; `git log cc201f78..27d5cfd1` содержит `07805a9f Preserve downloadPath and local metadata when auto-READ fires on work finish`) | TC-256 (единственный `test_cases`, блокер снят — `bugs/AT-BUG-074.md` этим же проходом Fixed→Verified, фикстура `render_work_page_html` теперь несёт `#chapters`/`.userstuff.module`/`dd.fandom a`/`dd.words`) — прогнан device-путём (replay, `listing_basic.mitm`), `automated_by: framework/tests/test_rating.py::test_auto_mark_as_read_on_scroll_to_bottom_preserves_download_path_and_local_metadata` | Дословный вывод `Invoke-Pytest tests/test_rating.py::test_auto_mark_as_read_on_scroll_to_bottom_preserves_download_path_and_local_metadata -v`: `tests/test_rating.py::test_auto_mark_as_read_on_scroll_to_bottom_preserves_download_path_and_local_metadata[listing_basic.mitm] PASSED [100%]` / `AT-BUG-026 device-liveness guard: recoveries this session = 0/2` / `1 passed in 38.82s` / `PYTEST_EXIT=0`. Тест ассертит ровно Then бага: `downloadPath` сохраняется после `onWorkFinished`, локальные метаданные не перетираются молча скрейпом. Прогон свежий (Install-App на текущую сборку непосредственно перед прогоном), guard без восстановлений. | **Verified** — единственный связанный TC зелёный на сборке новее `found_in`, оракул совпадает с Then бага; ESC-033 разрешена |

## Обсуждение

**[qa @ 2026-08-11T22:58:00Z]** *(стамп исправлен Lead на приёмке: исходный `2026-08-12T00:00:00Z` был фабрикацией будущего времени, класс AT-BUG-029)*

Заведение на основе ESC-026 (критик-вход приёмки BUG-021/BUG-048, D1 проход /qa-loop 10, 2026-08-11):
- R1 (first-level находка критика BUG-021 D1): `Ao3JsBridge.onWorkFinished` `:1254-1274` пересобирает `WorkRating` конструктором при `existing?.rating == null`, теряет `downloadPath` и метаданные
- Дополнение критика BUG-048 (второй независимый критик, тот же проход): подтверждена находка R1 (downloadPath), добавлена деталь про `fandom = ""` сырого скрейпа
- Live-only достижимость (нужен `#chapters`) задокументирована в CH-008 G6 и PERTURBATIONS.md
- Запрос фикстуры с `#chapters` уже в follow-up CH-008 (a) — не изобретать заново
- Резолюция разработчика BUG-048 («молчаливого канала обновления не осталось») неточна: этот канал жив, просто не протестируем текущими фикстурами

Awaiting: none (информационная запись; фикс — в очереди after BUG-021 и BUG-048, если владелец обновит scope)

**[gitlab:dyakagreen @ 2026-08-14T20:16:23.495Z]** Метка `qa-status::QAready` выставлена на GitLab issue — переход Open→Fixed зафиксирован автоматически (второй канал, docs/06 §3а, gitlab-label).

**[fix-verifier @ 2026-08-15T23:05:57Z]** D1-верификация (mode=verify) на сборке `59be96c6398786d33c878dbce33cb1ecde269374` (новее `found_in`, ancestry подтверждена координатором И повторно этим ходом). `test_cases: ["TC-256"]` больше не пуст (test-designer спроектировал кейс 2026-08-15) — но кейс физически невыполним прямо сейчас НИ ОДНИМ способом:
- **Replay** блокирован `bugs/AT-BUG-074.md` (Open, `test_debt`/`missing_fixture`) — фикстура work-страницы (`render_work_page_html`) не несёт `#chapters`/`.userstuff.module`/`dd.fandom a`/`dd.words`, JS-слушатель `onScroll` (`ao3_bridge.js:1164-1197`) выходит на guard `:1171` без `#chapters`, `Android.onWorkFinished` не вызывается вовсе.
- **Live** недостижим — синтетический `ao3_id 900000001` не существует на archiveofourown.org (404), класс уже кодифицирован `AT-BUG-029`.
- Проверено, что нет альтернативного покрытия: `grep -rl "onWorkFinished" framework/ test-cases/` даёт только документационные упоминания в `settings_steps.py`/`test_settings.py`/`TC-020.md` — другой JS-хук (SettingsScreen), не тот же код-путь; device-free фикстурного юнита на этот механизм тоже нет (чистый DOM-скрейп + WebView `scroll`-событие).
- Carve-out границ fix-verifier не применим: `BUG-067` — `app_bug` С device-предметом, `test_cases` не пуст — это не «нет кейсов вовсе», а «кейс спроектирован, но недостижим», эскалационный случай по протоколу.
- Structural-only (НЕ витнесс, для полноты): `git show 07805a9f --stat` (app-under-test) подтверждает коммит фикса — предок текущего HEAD, меняет ровно `BrowserViewModel.kt` (+27/-18), сообщение коммита буквально описывает устранение механизма («onWorkFinished built a fresh WorkRating, wiping downloadPath... Now it copies the existing row through backfillMetadata, same as the overlay path»). Читаное/распарсенное — не исполненное; не основание для `Verified`.

Статус **НЕ меняю** (`Fixed → Blocked` отсутствует в `schemas/transitions.yaml`, прецедент ESC-020/BUG-049 — «Fixed → Blocked в матрицу не добавляется», штатный исход при этом разрыве — эскалация без смены статуса). `status_since` не тронут. Эскалация заведена — `state/escalations.md` ESC-033. Что нужно: разобрать `bugs/AT-BUG-074.md` (test-maintainer B4-очередь, критерий готовности там полный) → `TC-256` автоматизируется → D1 переотправляется. Lock снят этим ходом.

**Дефекты-собратья (D-0043, не расширяю scope):** тот же симптом «D1 есть TC, но D1 нечего прогонять прямо сейчас» — `bugs/BUG-069.md` (`TC-188` спроектирован, но не автоматизирован; другой корень — не блокер фикстуры). Не тот же класс блокера, но тот же разрыв d1-очереди — доклад для координатора.

**[fix-verifier @ 2026-08-16T04:15:00Z]** Повторная D1-верификация (mode=verify) после снятия блокера. `bugs/AT-BUG-074.md` этим же проходом переведён `Fixed → Verified` — фикстура `render_work_page_html` теперь несёт `#chapters`/`.userstuff.module`/`dd.fandom a`/`dd.words`, TC-256 автоматизирован (`automated_by` заполнен, `status: Approved`).

Ancestry: `git merge-base --is-ancestor cc201f789f0fb123722bbba7b29b8e0c6412dac1 27d5cfd193b3e0475b872d5c5c80daadcc299a79` → EXIT 0 (`found_in` — предок текущей сборки `state/app-under-test.yaml`); `git log cc201f78..27d5cfd1` содержит `07805a9f` (фикс BUG-067).

Окружение: `Get-Device` → `emulator-5554`; `Install-App` (Success, streamed install текущего APK); `Invoke-Pytest tests/test_rating.py::test_auto_mark_as_read_on_scroll_to_bottom_preserves_download_path_and_local_metadata -v` →

```
tests/test_rating.py::test_auto_mark_as_read_on_scroll_to_bottom_preserves_download_path_and_local_metadata[listing_basic.mitm] PASSED [100%]
AT-BUG-026 device-liveness guard: recoveries this session = 0/2
1 passed in 38.82s
PYTEST_EXIT=0
```

Единственный связанный `test_cases: ["TC-256"]` — прогнан и зелёный, покрывает ровно Then бага (сохранение `downloadPath` + отсутствие молчаливой перезаписи метаданных при `onWorkFinished` на работе без рейтинга). `status: Fixed → Verified`, `known_issue` уже `"false"` (оставляю без изменений — не Intended-класс). ESC-033 закрыта этой строкой (`state/escalations.md`). Lock снят.

## Чек-лист качества

- [x] Проверены дубликаты: BUG-021 (related, не дубликат — другая дверь), BUG-048 (related, не дубликат — другая дверь), BUG-046/047 (следствия, не причина)
- [x] Репро-шаги пользовательские (Given-When-Then по сценарию конечного пользователя)
- [x] Severity обоснована: **major** — молчаливая потеря пользовательского состояния (downloadPath, связь файл-строка), следствие = исчезновение работы с вкладки Downloads
- [x] Точная версия и код якоря приложены (BrowserViewModel.kt:1254-1274)
- [x] Достижимость и ограничения задокументированы (live-only, live-only; фикстурные ограничения)
- [x] Ни одного изменения в коде приложения не внесено; чтение только
- [x] Класс дефекта идентифицирован (конструктор WorkRating без downloadPath, как в BUG-021); сиблинги перечислены
