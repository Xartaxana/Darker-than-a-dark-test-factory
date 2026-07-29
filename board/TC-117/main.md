---
key: "TC-117"
project: "AO3"
issueType: "test-case"
status: "tc-approved"
priority: "p2"
summary: "Снятие рейтинга Favorite (deselect) не запускает скачивание"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:downloads", "risk:R-05"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-28T22:03:58Z"
updated: "2026-07-28T22:03:58Z"
archived: false
resolution: null
---

# Снятие рейтинга Favorite (deselect) не запускает скачивание

_Спроецировано из `test-cases/downloads/TC-117.md` (источник правды).
Статус в нашей машине: **Approved**._

# TC-117 — Снятие рейтинга Favorite повторным тапом не скачивает файл

## Предусловия
- Работа W засеяна с рейтингом SAVE (Favorite), `downloadPath=null`; тумблер
  Auto-download включён.
- Открыта страница работы W `/works/{id}`, панель показывает Favorite выбранным.

## Сценарий (Given-When-Then)

**Given** работа W имеет рейтинг Favorite; тумблер Auto-download включён; панель
показывает Favorite выбранным

**When** пользователь повторно нажимает уже выбранную кнопку «Favorite» на панели
(deselect — `rating-deselect-on-tap`)

**Then** рейтинг снят — работа W исчезает из вкладки FAVORITE экрана Library (при
отсутствии комментария/тегов/файла строка удаляется целиком, `RatingRepository.
removeRating`)
**And** скачивание НЕ запускается ни на каком этапе — в download-директории
приложения не появляется ни одного нового файла (`download_oracle`, без
`@pytest.mark.produces_download`)

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Работа W | rating=SAVE → null (deselect), downloadPath=null |
| Тумблер Auto-download | ON |

## Заметки для автоматизации
- Replay не требуется — ветка `rating == null` (`savePanelRating`, строки 691-737) не
  содержит НИ ОДНОГО вызова `downloadWork` ни в одной из своих под-веток; сетевого
  вызова в сценарии структурно нет.
- Отличать от TC-116 (смена рейтинга на ДРУГОЙ, не null) — разные код-ветки
  (`rating != null` vs `rating == null` в `savePanelRating`), оба входа группы 4
  §9 обязаны быть покрыты по отдельности (один сценарий — один кейс).
- Шаги (исправлено 2026-07-28, critic-вход — прежняя версия ошибочно требовала ДВА
  тапа): работа W засеяна напрямую с rating=SAVE (см. Предусловия, НЕ через UI) —
  панель `RatingMenu` уже показывает Favorite выбранным при открытии страницы.
  Единственный вызов `rating_steps.rate_current_work(driver, "SAVE")` по уже
  выбранной кнопке — это и есть деселект (`rating-deselect-on-tap`, общий toggle
  `RatingOverlay.kt`/`RatingMenu`, тот же механизм, что и для group 3/панели —
  тап по УЖЕ выбранному рейтингу снимает его, а не переотправляет тот же SAVE).
  ВТОРОЙ тап здесь НЕДОПУСТИМ: он снова выбрал бы SAVE на уже удалённой строке
  (`existing == null` после деселекта) → путь `pendingPanelSave`/`:1057` → реальное
  скачивание при тумблере ON — прямо противоположно заявленному Then. Приём
  идентичен TC-008 (`framework/tests/test_rating.py:73`, фикстура
  `loved_work_seeded` — `conftest.py:75-83`: `clean_state()` +
  `seed_library([(W.LOVED, "SAVE")])`, работа УЖЕ предзаполнена SAVE ДО старта
  сессии Appium): единственный тап по уже выбранной кнопке и есть деселект;
  фикстура `loved_work_seeded` переиспользуется без изменений.
- **Батарея правил-реакций:** закрывает вторую половину группы 4 §9 («снятие
  рейтинга не скачивает»); первая половина — TC-116.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов
