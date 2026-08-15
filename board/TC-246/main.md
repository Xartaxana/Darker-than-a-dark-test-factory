---
key: "TC-246"
project: "AO3"
issueType: "test-case"
status: "tc-review"
priority: "p1"
summary: "Тумблер E-ink mode: персистентность, и пока выключен — вложенная строка «Show page-turn buttons» отсутствует, но её значение сохраняется"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:settings", "risk:R-11"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-15T00:10:14Z"
updated: "2026-08-15T00:10:14Z"
archived: false
resolution: null
---

# Тумблер E-ink mode: персистентность, и пока выключен — вложенная строка «Show page-turn buttons» отсутствует, но её значение сохраняется

_Спроецировано из `test-cases/settings/TC-246.md` (источник правды).
Статус в нашей машине: **Review**._

# TC-246 — E-ink mode: вложенность и переживание рестарта

## Предусловия
- Приложение запущено с чистыми данными (эталонный AVD — дефолт E-ink OFF,
  `Build.MANUFACTURER != "ONYX"`, граница чёрного ящика называется явно —
  ONYX-дефолт здесь не проверяется). «Show page-turn buttons» включена
  (значение ON сохранено в prefs явным включением при E-ink ON).

## Сценарий (Given-When-Then)

**Given** E-ink mode ON, «Show page-turn buttons» ON (видна и включена)

**When** пользователь выключает E-ink mode, открывает Settings заново
(строка «Show page-turn buttons» при этом должна отсутствовать), затем
включает E-ink mode обратно и, наконец, перезапускает приложение
(kill+relaunch)

**Then** пока E-ink mode OFF — строка «Show page-turn buttons» ПОЛНОСТЬЮ
ОТСУТСТВУЕТ на экране (не disabled, а не отрендерена вовсе)
**And** после возврата E-ink mode в ON строка снова видна и по-прежнему
показывает ON — сохранённое значение НЕ сбросилось скрытием
**And** после kill+relaunch оба тумблера (E-ink mode ON, page-turn-buttons
ON) сохранили значения

## Проверяемые данные
| Параметр | Значение |
|---|---|
| E-ink mode | ON → OFF → ON → рестарт |
| Show page-turn buttons | ON на всём протяжении (только скрывается/показывается) |

## Заметки для автоматизации
- Граница чёрного ящика (не блокер, называется явно): ONYX-дефолт (E-ink ON
  из коробки) не воспроизводим на эталонном AVD.
- Блокера нет — стандартная Compose-проверка присутствия/отсутствия
  элемента + persistence-паттерн (kill+relaunch), уже применяется другими
  settings-кейсами.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс
- [x] Given воспроизводим фикстурами
- [x] Then — наблюдаемое поведение (присутствие/отсутствие строки + значения)
- [x] Приоритет/область/источник указаны
- [x] Независим от порядка других кейсов
- [x] Область не комбинаторная для этого кейса
