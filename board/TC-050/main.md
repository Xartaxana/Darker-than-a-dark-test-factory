---
key: "TC-050"
project: "AO3"
issueType: "test-case"
status: "tc-automated"
priority: "p1"
summary: "Contrast-иконка в side panel переключает тему мгновенно во всём UI (WebView + нативный)"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:browser", "risk:R-11", "automation:active"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-08T17:35:00Z"
updated: "2026-07-08T17:35:00Z"
archived: false
resolution: "done"
---

# Contrast-иконка в side panel переключает тему мгновенно во всём UI (WebView + нативный)

_Спроецировано из `test-cases/browser/TC-050.md` (источник правды).
Статус в нашей машине: **Automated**._

# TC-050 — Side panel Contrast переключает тему мгновенно (вход через панель)

## Предусловия
- Приложение запущено с чистыми данными, тема = Light, вкладка Browse активна,
  открыта страница AO3 (WebView отображается светлым, нативный UI светлый).
- Side panel развёрнут (тап по handle-«гамбургеру» у края экрана).
- Режим прогона: replay (детерминированная страница AO3) либо live-smoke.

## Сценарий (Given-When-Then)

**Given** приложение в светлой теме, на Browse видна светлая страница AO3, side panel
развёрнут и показывает иконку Contrast с contentDescription «Switch to dark mode»

**When** пользователь нажимает иконку Contrast в side panel

**Then** и содержимое WebView (веб-страница AO3), и окружающий нативный Compose-UI
немедленно переходят в тёмную цветовую схему — без перезапуска приложения; иконка
Contrast теперь имеет contentDescription «Switch to light mode»

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Исходная тема | Light |
| Вход переключения | Contrast-иконка side panel (не Settings) |
| Ожидаемый contentDescription после | «Switch to light mode» |

## Заметки для автоматизации
- Отличие от TC-047/TC-048: тот же наблюдаемый результат (мгновенное затемнение
  нативного UI и WebView), но **вход — side panel**, а не экран Settings. Не
  дублировать проверку самих цветов детально — фокус на том, что панельный вход
  срабатывает и даёт тот же мгновенный эффект.
- Ожидаемый результат по умолчанию — PASS (регрессия на хрупкую зону, CLAUDE.md:
  «Dark mode has broken four times»); реальный pass/fail решает триаж.
- Локатор Contrast-кнопки — по contentDescription («Switch to dark mode» в светлой
  теме / «Switch to light mode» в тёмной); он же служит наблюдаемым признаком
  переключённого состояния панели.
- Тайминг: тема применяется через программный `wv.reload()` — дать ожиданию время
  на перерисовку WebView после завершения загрузки; нативная часть перекрашивается
  без reload.
- Эквивалентность стейта Settings↔side panel проверяется отдельно (TC-054) —
  здесь только факт срабатывания входа через панель.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов
