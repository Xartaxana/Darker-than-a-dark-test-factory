---
key: "TC-265"
project: "AO3"
issueType: "test-case"
status: "tc-review"
priority: "p2"
summary: "Copy URL на странице без Clipboard API не молчит — срабатывает execCommand-фолбэк с видимой подписью Copied!/Copy failed"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:browser", "risk:R-02"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-19T13:26:00Z"
updated: "2026-08-19T13:26:00Z"
archived: false
resolution: null
---

# Copy URL на странице без Clipboard API не молчит — срабатывает execCommand-фолбэк с видимой подписью Copied!/Copy failed

_Спроецировано из `test-cases/browser/TC-265.md` (источник правды).
Статус в нашей машине: **Review**._

# TC-265 — execCommand-фолбэк Copy URL: reject Clipboard API не оставляет кнопку немой

## Предусловия
- L2 bridge-harness, любая replay work/listing-страница с включённым флагом
  `ao3DebugCopyUrl: true` (кнопка видима — предусловие TC-188 про
  видимость здесь не переассертится).
- **Оговорка нормы (унаследована от `docs/tasks/p2-pyramid-bridge.md` Р3):**
  этот кейс проверяет JS-ФОЛБЭК бриджа — какую ветку `ao3_bridge.js`
  выбирает и что она реально пишет в стаб clipboard/execCommand — а НЕ
  поведение системного clipboard-провайдера реального Android/WebView.
  Device-покрытие класса BUG-071 (реальный `ClipboardManager`/permission-
  слой Blink) остаётся L3/L4 — этот кейс его не снимает и не заменяет (тот
  же явный водораздел, что уже принят в `TC-188.md` про `bugs/AT-BUG-068.md`).

## Сценарий (Given-When-Then)

**Given** страница с видимой DEBUG copy-URL кнопкой, `navigator.clipboard.
writeText` управляемо настроен на успешный resolve

**When** пользователь тапает по кнопке

**Then** `writeText` вызван с `location.href`, `execCommand` НЕ вызван —
успешный путь остаётся успешным (Then контроля, не регресс от фикса
BUG-071)

**When** (тот же класс страницы, `navigator.clipboard.writeText` теперь
настроен на reject — origin БЕЗ Clipboard API, штатная конфигурация для
`file://` страницы скачанной работы) пользователь тапает по кнопке

**Then** кнопка НЕ остаётся немой: срабатывает `execCommandFallback` —
`document.execCommand` вызван РОВНО ОДИН РАЗ, реальный текст (`location.href`)
записан во временный `<textarea>` непосредственно перед вызовом (проверено
чтением значения textarea/аргумента стаба, не только фактом вызова)

**Инвариант:** независимо от того, отклонён `writeText` рантаймом или API
отсутствует вовсе (оба случая ведут в одну и ту же `.catch`-ветку), кнопка
Copy URL ВСЕГДА даёт пользователю обратную связь через один из двух каналов
(Clipboard API либо execCommand-фолбэк) — молчаливого отказа (класс
BUG-069/BUG-071, «ДВА фикса подряд в одной кнопке») не остаётся ни в одной
из веток.

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Clipboard API resolve | `writeText` вызван, `execCommand` НЕ вызван |
| Clipboard API reject | `writeText` вызван И `execCommand` вызван (фолбэк) |

## Заметки для автоматизации
- **Дефект-собрат / находка дедупа (D-0043, докладываю, не расширяю
  scope).** Автоматизация для ЭТОГО СЦЕНАРИЯ уже СУЩЕСТВУЕТ и принята
  конвейером ДО дизайна этого TC:
  `framework/tests/bridge/test_clipboard.py` (`docs/tasks/p2-pyramid-
  bridge.md`, узел N5, `journal task_id p2-n5-bridge-harness`, accepted
  2026-08-19) несёt ровно три теста, покрывающие Then этого кейса
  дословно: `test_clipboard_write_text_resolves_with_location_href`
  (resolve-ветка), `test_clipboard_write_text_rejection_falls_back_to_
  exec_command` (reject→execCommand-фолбэк), плюс третий тест про клик по
  СКРЫТОЙ кнопке (флаг OFF), который выходит за границы Then ЭТОГО кейса
  (видимость — предмет TC-188, не этого кейса) и сюда не включён. **Я
  (test-designer) НЕ заполняю `automated_by`** — это поле заполняет
  test-automator по конвенции (`schemas/test-case.schema.yaml` комментарий
  `automated_by`), а сам файл `framework/tests/bridge/**` — вне owns
  test-designer в этом ходе (non-goals диспатча: не трогать `framework/**`).
  **Рекомендация координатору:** следующий диспатч test-automator/
  test-reviewer для этого TC — почти нулевой по объёму (проверить
  соответствие УЖЕ существующих тестов Then этого кейса, проставить
  `automated_by`/пройти F1), не писать тесты с нуля.
- Живой (не device-free) канал реального `ClipboardManager`/Blink-
  permission-слоя — уже отдельно закрыт `TC-188.md` (grep `DOMException:
  Write permission denied` в browser log) и заблокирован `bugs/AT-BUG-
  068.md` для продуктового контракта «Copied!»/буфер на текущей тестовой
  среде — этот кейс его не переоткрывает.
- Блокера автоматизации нет (инфраструктура и даже сами тесты уже
  существуют).

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...» (контроль-ветка +
      фолбэк-ветка — контраст одного правила, не два сценария)
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение (вызов/аргумент API), а не
      реализацию
- [x] Заголовок сформулирован от ожидаемого поведения
- [x] Указаны приоритет (P2), область (browser) и источник требования (R-02)
- [x] Кейс независим от порядка выполнения других кейсов
- [x] Блокер автоматизации из заметок — блокера нет; автоматизация уже
      существует (см. находку дедупа выше)
- [x] Не C4-семьи в узком смысле (единичная кнопка), но батарея
      правил-реакций частично применима: off-инвариант — н-п (кнопка
      видима по построению Given, невидимость — предмет TC-188);
      идемпотентность/edge-vs-level/ретроактивность/propagation — н-п
      (однократный клик, без сохраняемого состояния между вызовами;
      строка `Инвариант:` дана для полноты — оба канала обратной связи
      симметрично покрыты)
