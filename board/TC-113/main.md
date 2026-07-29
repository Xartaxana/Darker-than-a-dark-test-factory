---
key: "TC-113"
project: "AO3"
issueType: "test-case"
status: "tc-approved"
priority: "p1"
summary: "Включение тумблера Auto-download не скачивает задним числом ранее отмеченные Favorite-работы"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:downloads", "risk:R-05"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-28T22:03:45Z"
updated: "2026-07-28T22:03:45Z"
archived: false
resolution: null
---

# Включение тумблера Auto-download не скачивает задним числом ранее отмеченные Favorite-работы

_Спроецировано из `test-cases/downloads/TC-113.md` (источник правды).
Статус в нашей машине: **Approved**._

# TC-113 — Ретроактивность: включение тумблера не скачивает старые Favorite

## Предусловия
- Работа W засеяна НАПРЯМУЮ в Room (не через UI) с рейтингом SAVE (Favorite) и
  `downloadPath=null` — имитирует «работа была отмечена Favorite ДО того, как
  пользователь включил тумблер» (`app_steps.seed_library([(W.LOVED, "SAVE")])`,
  тот же приём, что `loved_work_seeded`).
- Тумблер «Auto-download favorite works» на момент сидинга выключен (дефолт).

## Сценарий (Given-When-Then)

**Given** работа W уже имеет рейтинг Favorite (SAVE) и не скачана; тумблер
«Auto-download favorite works» выключен

**When** пользователь открывает Settings и включает тумблер «Auto-download saved
works»

**Then** работа W остаётся БЕЗ файла — карточка на вкладке FAVORITE экрана Library
по-прежнему показывает download-иконку (не open-иконку), `downloadPath` не
выставлен
**And** работа W не появляется во вкладке FILES экрана Library
**And** в download-директории приложения не появляется ни одного нового файла —
`download_oracle` не фиксирует скачивание (тест без `@pytest.mark.produces_download`)

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Работа W | `W.LOVED`, засеяна с rating=SAVE, downloadPath=null (`seed_library`) |
| Тумблер Auto-download | OFF → ON (переключается в сценарии) |

## Заметки для автоматизации
- Регрессионный замок инварианта, не ловля известного дефекта — `setAutoDownloadSaved`
  (BrowserViewModel.kt:522) синхронно и единолично присваивает `autoDownloadSaved`,
  никакого пересканирования существующих `SAVE`-записей код не делает; владелец уже
  подтвердил это поведение как корректное при репро BUG-014 (см. «Actual»: «При
  включении тумблера: существующие Favorite-работы НЕ скачиваются (корректно)»).
- Шаги: `app_steps.seed_library` (уже существует) → `settings_steps.
  enable_auto_download` (уже существует, используется в TC-032) → переход в Library
  → `library_steps.assert_work_in_tab("SAVE", ...)`/`assert_download_icon_shown`/
  `assert_work_not_in_files_tab` (все уже существуют).
- Replay не требуется — тумблер включается ПОСЛЕ сидинга, никакого сетевого вызова в
  сценарии нет (`downloadWork` не вызывается вообще: само включение тумблера не
  триггерит ни одну из трёх точек предиката — нужен явный `applyRating`/
  `savePanelRating`/`onRateWorkRequested`, которого в сценарии нет).
- **Батарея правил-реакций:** это кейс «ретроактивность» (CLAUDE.md, калибровка №4).

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов
- [x] Область содержит правило-реакцию — батарея: этот кейс закрывает пункт
      «ретроактивность»
