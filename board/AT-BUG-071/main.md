---
key: "AT-BUG-071"
project: "AO3"
issueType: "bug"
status: "bug-verified"
priority: "p1"
summary: "Нет автоматизационных фикстур для EPUB-скачивания: seed_with_download хардкодит расширение .html, нет записанной .epub-транзакции и нет work-страницы БЕЗ epub-ссылки"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "test_case:TC-236", "test_case:TC-237", "test_case:TC-238", "test_case:TC-239", "test_case:TC-240", "sev:major"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-16T10:40:00Z"
updated: "2026-08-16T10:40:00Z"
archived: false
resolution: "done"
---

# Нет автоматизационных фикстур для EPUB-скачивания: seed_with_download хардкодит расширение .html, нет записанной .epub-транзакции и нет work-страницы БЕЗ epub-ссылки

_Спроецировано из `bugs/AT-BUG-071.md` (источник правды).
Статус в нашей машине: **Verified**._

# AT-BUG-071 — Автоматизация EPUB-скачивания заблокирована: нет расширяемого сидера «уже скачанного» файла и нет mitm-записи с EPUB-ссылкой

## Окружение
- Не зависит от сборки приложения: долг тестовой системы (`type: test_debt`,
  `debt_kind: missing_fixture`), тот же класс, что `AT-BUG-004` (replay-
  инфраструктура) — механизм скачивания уже доказан для HTML, но два
  конкретных примитива жёстко завязаны на HTML-расширение/разметку.

## Суть долга

Сборка 59be96c6 добавила формат загрузки EPUB
(`DownloadRepository.kt:52-55`, `application/epub+zip`, ссылка ищется
регуляркой `href="(/downloads/[^"]*\.epub[^"]*)"` на странице работы,
`:220`). MIME при открытии файла внешним приложением
(`MainActivity.kt:765`) определяется РАСШИРЕНИЕМ пути (`path.endsWith(".epub",
ignoreCase = true)`), не сохранённым в БД значением формата.

Два конкретных пробела во фреймворке блокируют автоматизацию:

1. `framework/data/seed_db.py::_push_download_fixture` (используется
   `seed_with_download`/`seed_with_comment_and_download`) ЖЁСТКО пишет
   `rel = f"{dir}/{work.ao3_id}.html"` — расширение `.html` захардкожено
   независимо от переданного локального файла. Сидинг «работа уже скачана
   как EPUB» (нужен TC-239/TC-240 для проверки открытия внешним ридером без
   реального скачивания) даёт файл с `.html`-расширением и получает
   `text/html` MIME вместо `application/epub+zip` — сценарий физически не
   воспроизводим этим сидером.
2. В `framework/data/recordings/` ЕСТЬ work-страницы с рабочей `.epub`-
   ссылкой (её кладёт `_download_list_html`, `recording_builder.py:477` —
   все четыре формата), но НЕТ записанной транзакции самого `.epub`-файла:
   во всех девяти записях единственный download-flow — `.html`
   (`/downloads/900000001/A_Loved_Test_Work.html`, `work_with_download.mitm`/
   `listing_basic.mitm`). Это ровно класс AT-BUG-029 («страница есть, файла
   транзакции нет»): без неё TC-236 уйдёт в живую сеть
   (`server_replay_extra=forward`). Зеркально: для TC-237 (ошибка «EPUB
   download link not found on page») нет страницы БЕЗ epub-пункта — этот
   кейс тоже заблокирован, а не свободен.

Заблокированные кейсы: TC-236 (P1, позитивное скачивание — нет записанной
`.epub`-транзакции), TC-237 (P1, нет страницы без epub-ссылки — регекс
найдёт существующую ссылку раньше ожидаемой ошибки), TC-238 (P1, зависит от
TC-236 как позитивной предпосылки «файл уже скачан в EPUB»), TC-239 (P1,
открытие EPUB внешним приложением — предпосылка «уже скачан как EPUB»
недостижима сидингом), TC-240 (P1, частично — ветка EPUB пункта «Open in
e-reader app»; HTML-ветка тем же кейсом уже воспроизводима существующим
сидером и блокером не считается).

## Критерий готовности (Fixed)

- `seed_with_download`/`seed_with_comment_and_download` (или их аналог)
  принимают/выводят целевое РАСШИРЕНИЕ пушимого файла (не хардкодят
  `.html`), позволяя засеять «уже скачанную EPUB-работу» с корректным
  путём `<ao3Id>.epub`.
- В `framework/data/recordings/` есть (а) запись work-страницы + транзакция
  самого `.epub`-файла для позитивного скачивания и (б) вариант страницы БЕЗ
  epub-пункта (флаг билдера) для ошибки TC-237.
- Хотя бы один из заблокированных кейсов доведён до зелёного прогона на
  этой инфраструктуре (доказательство пригодности); остальные
  разблокированы для test-automator.
- Smoke без регресса.

## Анализ

Класс идентичен `AT-BUG-004` («механизм есть, продукта нет для НОВОЙ
разметки/формата») — расширение уже доказанного EPUB-варианта тех же
приёмов (`recording_builder.py`, `_push_download_fixture`), не новая
техника. Чинит фабрика по правилу «Устранить test debt» (B4). Fixed не
ждёт сборку приложения.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| 2026-08-16 | test_debt, framework-only (не зависит от сборки приложения); app-under-test @ `27d5cfd1` (versionName `dev-local`, versionCode `12`) установлена на `emulator-5554` для прогона | TC-236 (`test_downloads.py::test_epub_download_saves_epub_file_and_shows_on_files_tab[work_with_download_epub.mitm]`) — прогнан живьём. TC-237/238/239/240 — не прогнаны этим проходом (инфраструктурой разблокированы, но их device-автоматизация — задача test-automator вне мандата этого фикса, DoD-задания на подтверждающий witness-прогон явно ограничило проверку TC-236; полный `test_downloads.py` 17/17 уже трижды чисто прогнан исполнителем/критиком в этом тикете — см. «Обсуждение» выше, повторную полную регрессию модуля этот проход не дублировал) | `1 passed in 82.55s (0:01:22)`, `PYTEST_EXIT=0`, device-liveness guard `recoveries this session = 0/2` | Verified |

## Обсуждение

**2026-08-15T00:10:14Z — test-designer (заведение при дизайне области
«downloads/library: формат EPUB»):** блокер найден при проектировании
TC-236..240 (сверка существующих сидеров `framework/data/seed_db.py`
против нужд Given этих кейсов) — заведён тем же ходом, что и сами кейсы,
по правилу test-designer (шаг 4 воркфлоу). Кейсы оставлены в `status:
Review` (не `Blocked`) — блокер касается АВТОМАТИЗАЦИИ, не дизайна: Given/
Then сформулированы полно и воспроизводимо, ограничение только
инструментальное.

**2026-08-16T08:02:56Z — test-maintainer (B4, устранение долга; продолжение
прерванной heartbeat-таймаутом сессии — код был уже написан, эта итерация
только прогнала и задокументировала):**

Проверен и доведён до зелёного уже написанный (незакоммиченный) прогресс —
переписывать с нуля не понадобилось, код оказался корректным:

- `framework/data/seed_db.py::_push_download_fixture` — расширение
  устройственного пути выводится из `local_file.suffix` (не хардкод
  `.html`); `seed_with_download`/`seed_with_comment_and_download` уже
  принимают `Path` третьим/пятым элементом строки без изменения сигнатуры —
  вызывающая сторона просто передаёт файл с нужным расширением
  (`framework/data/fixtures/downloaded_work.epub` для EPUB-сценариев).
- `framework/data/recording_builder.py` — новые `WORK_WITH_DOWNLOAD_EPUB_FILENAME`/
  `WORK_NO_EPUB_LINK_FILENAME` константы, `_download_list_html`/
  `render_work_page_html` получили `include_epub` (default `True`, байт-в-
  байт совместимо со всеми существующими вызовами).
- `scripts/build_replay_recordings.py` — `build_work_with_download_epub()`/
  `build_work_no_epub_link()` подключены в `main()`. **Верификация записей:**
  сделана байтовая копия untracked `work_with_download_epub.mitm`/
  `work_no_epub_link.mitm` ДО перегенерации, затем `python
  scripts/build_replay_recordings.py` (venv `framework/.venv`) перегенерировал
  ВСЕ 9 записей — `git status --porcelain -- framework/data/recordings/`
  после прогона показал только эти же два файла untracked (ни один
  ОТСЛЕЖИВАЕМЫЙ `.mitm` не изменился) и побайтовое сравнение (`xxd`+`diff`)
  новых файлов с копией «до» дало пустой diff — регенерация детерминирована,
  записи актуальны относительно текущего кода билдера.
- `framework/screens/settings_screen.py`/`framework/steps/settings_steps.py`
  — `tap_download_format`/`select_download_format("EPUB")`: локатор
  `//*[@text="{label}"]/..` сверен с местом рендера
  `SettingsScreen.kt:969-1003` (`TextButton` с `Text("HTML"/"EPUB",
  labelMedium)`, клик на кликабельном родителе TextButton) — тот же приём,
  что у соседних `_display_mode_button_locator`.
- `framework/tests/test_downloads.py::test_epub_download_saves_epub_file_and_shows_on_files_tab`
  (TC-236) — EPUB-зеркало TC-032/033, проверяет `downloadPath` через
  `seed_db.read_work_ratings_full()` (MIME определяется расширением пути,
  `MainActivity.kt:765`).

**Witness (живой прогон, устройство `emulator-5554`):**

```
tests/test_downloads.py::test_epub_download_saves_epub_file_and_shows_on_files_tab[work_with_download_epub.mitm] PASSED [100%]
AT-BUG-026 device-liveness guard: recoveries this session = 0/2
1 passed in 122.36s (0:02:02)
PYTEST_EXIT=0
```
Повторено ЕЩЁ 2 раза подряд зелёным (3 зелёных подряд на новой
инфраструктуре): `1 passed in 62.72s`, `1 passed in 63.58s`, оба
`PYTEST_EXIT=0`.

**Регресс HTML-пути — полный модуль `tests/test_downloads.py` (17 тестов,
включая TC-032/033/112 и весь остальной набор download-сценариев):**

```
17 passed in 1355.78s (0:22:35)
PYTEST_EXIT=0
```
Ни один HTML-путь (`work_with_download.mitm`,
`test_auto_download_triggers_on_loved_rating`,
`test_manual_download_from_library_adds_local_file` и остальные 15) не
регрессировал.

**Критерий готовности (Fixed) — сверка по пунктам:**
1. `seed_with_download`/`seed_with_comment_and_download` выводят целевое
   расширение из переданного файла, EPUB-путь `<ao3Id>.epub` достижим —
   выполнено (см. diff `_push_download_fixture` выше).
2. `work_with_download_epub.mitm` (позитивная EPUB-транзакция) и
   `work_no_epub_link.mitm` (страница без EPUB-пункта, TC-237) есть и
   верифицированы регенерацией — выполнено.
3. Хотя бы один заблокированный кейс доведён до зелёного — TC-236 зелёный
   3/3 — выполнено; TC-237/238/239/240 разблокированы инфраструктурой
   (`work_no_epub_link.mitm` для TC-237, `.epub`-сидинг для TC-239/240-E),
   их автоматизация — задача test-automator (вне мандата этого фикса).
4. Smoke без регресса — полный `test_downloads.py` (включающий все
   ранее зелёные TC этой области) зелёный 17/17, отдельного прогона smoke
   не потребовалось (долг локализован в этом модуле, изменения в
   `seed_db.py`/`recording_builder.py` byte-compatible для всех прочих
   вызовов — см. докстринги).

`TC-236.md` — `automated_by` заполнен
(`framework/tests/test_downloads.py::test_epub_download_saves_epub_file_and_shows_on_files_tab`),
статус кейса намеренно ОСТАВЛЕН `Approved` (не `Automated`) — в `Automated`
переводит только test-reviewer (F1, `schemas/transitions.yaml:118`), не
test-maintainer.

Статус переведён `Open -> Fixed` (`schemas/transitions.yaml:96-98`, guard
`type: test_debt`, актор `test-maintainer` легален). Ждёт верификации
fix-verifier (сборку приложения ждать не нужно — фикс целиком во
фреймворке).

Новых блокеров/test_debt в ходе работы не обнаружено — весь
незакоммиченный прогресс предыдущей сессии оказался корректным и
достаточным для критерия готовности.

**2026-08-16T10:40:00Z — fix-verifier (D1, штатная верификация):** долг
`test_debt`, фикс целиком во фреймворке (не завязан на сборку приложения) —
carve-out по границам роли не применён, поскольку связанные `test_cases`
СУЩЕСТВУЮТ и как минимум один (TC-236) реально автоматизирован и исполним;
верификация — обычный живой device-прогон, не документная сверка.

Живой прогон TC-236 повторён этим проходом на текущей сборке
(`app-under-test @ 27d5cfd1`, `emulator-5554`):
```
tests/test_downloads.py::test_epub_download_saves_epub_file_and_shows_on_files_tab[work_with_download_epub.mitm] PASSED [100%]
AT-BUG-026 device-liveness guard: recoveries this session = 0/2
1 passed in 82.55s (0:01:22)
PYTEST_EXIT=0
```
Это четвёртый зелёный прогон TC-236 на этой инфраструктуре подряд (три —
исполнителем в предыдущей итерации, см. «Обсуждение» выше, плюс этот) и
третий чистый прогон полного `test_downloads.py` (17/17) уже задокументирован
исполнителем/критиком — повторную полную регрессию модуля этот проход не
дублировал (DoD задания прямо разрешило ограничиться witness-прогоном TC-236).
TC-237/238/239/240 не прогнаны device-прогоном (их автоматизация — вне
мандата этого фикса, критерий готовности требовал разблокировки, не
исполнения; инфраструктурная разблокировка подтверждена регенерацией
`.mitm`-записей в предыдущей итерации).

Критик-вход по диффу уже пройден (два блокера закрыты координатором тем же
ходом, см. записи выше) — до этой верификации оставался только фактический
прогон.

`status: Fixed → Verified` (`schemas/transitions.yaml`, guard `type:
test_debt`, актор `fix-verifier` легален). `known_issue` в этом файле не
заведено (поле отсутствует у AT-BUG-071 с момента создания) — расширять
frontmatter вне мандата верификации не стал. Lock снят.

Аналогов/собратьев по D-0043 не замечено — класс дефекта (недостающая
фикстура для нового формата) уже закрыт этим же тикетом целиком (позитивный
+ негативный `.mitm`, сидер расширения).
