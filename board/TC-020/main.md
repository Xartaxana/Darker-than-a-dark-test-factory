---
key: "TC-020"
project: "AO3"
issueType: "test-case"
status: "tc-approved"
priority: "p3"
summary: "Clear all ratings сбрасывает бейджи на открытых страницах AO3 без перезагрузки"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:settings", "risk:R-01"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-15T14:43:10Z"
updated: "2026-07-15T14:43:10Z"
archived: false
resolution: null
---

# Clear all ratings сбрасывает бейджи на открытых страницах AO3 без перезагрузки

_Спроецировано из `test-cases/settings/TC-020.md` (источник правды).
Статус в нашей машине: **Approved**._

# TC-020 — Сброс бейджей на открытой странице AO3 после Clear all ratings

## Предусловия
- Приложение запущено, в Room засеяна работа W с `rating=SAVE` (Loved).
- Открыта работа W на странице `/works/{id}` в одной вкладке браузера (бейдж
  «Loved» виден в панели), Settings открыт во второй вкладке/экране (навигация
  между Browse и Settings не закрывает открытую WebView-вкладку — мультитаб
  сохраняет состояние).

## Сценарий (Given-When-Then)

**Given** приложение запущено, работа W засеяна с рейтингом Loved и её страница
`/works/{id}` открыта в браузере с видимым бейджем «Loved»

**When** пользователь переходит в Settings и подтверждает диалог «Clear all ratings»

**Then** при возврате на вкладку с открытой страницей работы W бейдж «Loved» исчез
(панель показывает отсутствие рейтинга), без ручной перезагрузки страницы
пользователем

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Работа W | `LOVED` из `framework/data/works.py`, засеяна с `rating=SAVE` |

## Заметки для автоматизации
- Уточнить с разработчиком/по коду: сброс "без reload" зависит от того, вызывает ли
  `Clear all ratings` broadcast `applyRatings` на все открытые WebView-вкладки, или
  бейдж обновится только при следующей навигации/reload той вкладки. Если по факту
  требуется reload — это расхождение с PROJECT.md/§9, эскалировать через
  bug-reporter, не подгонять Then под предположение.
- Если механизм broadcast к открытым вкладкам не подтверждён кодом, при обнаружении
  расхождения на реальном UI кейс остаётся в этой формулировке (Review), а
  фактический результат прогона триажируется как APP_BUG или TEST_BUG в зависимости
  от вердикта — не блокирует дизайн, т.к. поведение однозначно заявлено в §9
  тест-стратегии ("бейджи на открытых страницах AO3 сбрасываются").

- **Находка test-automator (2026-07-18, witness device emulator-5554, `bugs/BUG-012.md`):** механизм
  broadcast к открытым вкладкам ПОДТВЕРЖДЁН КОДОМ КАК ОТСУТСТВУЮЩИЙ.
  `SettingsViewModel.confirmClearAll()` (`SettingsScreen.kt:501-504`) вызывает
  ТОЛЬКО `repo.clearAllRatings()` — не зовёт `BrowserViewModel.refreshActiveTabRating`/
  `broadcastRatingChange` (эти два вызываются исключительно из `applyRating`/
  `savePanelRating`, см. `BrowserViewModel.kt:767-789,868-878`). `currentPageRating`
  открытой work-страницы (источник цвета кнопки в `WorkRatingPanel`/`RatingMenu`,
  `BottomBar.kt:106-119,223-237`) перечитывается из Room только в `onPageLoaded`
  (`BrowserViewModel.kt:463-509`, срабатывает на навигацию/reload) — Clear all
  ratings его не триггерит. Тест написан по формулировке кейса
  (`framework/tests/test_settings.py::test_clear_all_ratings_resets_open_work_page_badge`,
  использует тот же luma-прокси, что TC-009/TC-010) и эмпирически подтверждает
  разрыв: baseline(selected)=134.2, luma после Clear all + возврата на Browse (без
  reload) не поднялась выше порога деселекта 178.9 за 10с — кнопка «Favorite»
  осталась в выбранном виде. Тест оставлен в файле с `@pytest.mark.skip` (полный
  citation-текст причины — в самом декораторе) как witness находки; `automated_by`
  НЕ заполнен (test-automator продуктовые баги не заводит, CLAUDE.md) — кейс
  остаётся `Approved`, требует триажа (test-runner/bug-reporter решают APP_BUG vs
  TEST_BUG; альтернативно test-designer может пересмотреть Then, если поведение
  "без reload" окажется ошибочным ожиданием).

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов
