---
key: "TC-100"
project: "AO3"
issueType: "test-case"
status: "tc-review"
priority: "p1"
summary: "Exported-компоненты: MainActivity exported=true с VIEW/BROWSABLE intent-filter на archiveofourown.org (статическая инспекция манифеста)"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:security", "risk:R-15"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-22T02:00:00Z"
updated: "2026-07-22T02:00:00Z"
archived: false
resolution: null
---

# Exported-компоненты: MainActivity exported=true с VIEW/BROWSABLE intent-filter на archiveofourown.org (статическая инспекция манифеста)

_Спроецировано из `test-cases/security/TC-100.md` (источник правды).
Статус в нашей машине: **Review**._

# TC-100 — Exported-компоненты: MainActivity + intent-filter (build-level)

## Предусловия
- APK тестируемой сборки установлен на устройстве (`com.example.ao3_wrapper`).
- Проверка НЕ UI-драйвима через UiAutomator2 (build-level факт) — не требует
  запущенного Appium-сеанса, только установленный пакет на устройстве/доступный
  APK-файл.

## Сценарий (Given-When-Then)

**Given** APK тестируемой сборки установлен на устройстве

**When** манифест инспектируется статически: `adb shell dumpsys package
com.example.ao3_wrapper` (секция Activity Resolver Table / атрибуты компонента)
либо, если `aapt` доступен в тестовом окружении, `aapt dump badging <apk>` /
`aapt dump xmltree <apk> AndroidManifest.xml`

**Then** `com.example.ao3_wrapper/.MainActivity` отмечена `exported=true`
**And** у неё присутствует intent-filter с `action.VIEW`, категориями
`DEFAULT`/`BROWSABLE`, data-схемой `http`/`https` и host `archiveofourown.org` —
экспорт объясним (deep-link на AO3 работает по замыслу), а не случайно
расширенная поверхность атаки

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Пакет | `com.example.ao3_wrapper` |
| Компонент | `com.example.ao3_wrapper.MainActivity` |
| Ожидаемое `exported` | `true` |
| Ожидаемый intent-filter | action=`VIEW`, categories ⊇ {`DEFAULT`,`BROWSABLE`}, scheme ∈ {`http`,`https`}, host=`archiveofourown.org` |

## Заметки для автоматизации
- Блокера нет: `adb.shell(...)` — существующий примитив (`framework/core/adb.py`),
  `dumpsys package <pkg>` не требует новой инфраструктуры/фикстур — парсинг
  текстового вывода на факт `exported=true` и состав intent-filter — рутинная
  автоматизация. Если парсинг `dumpsys package` окажется слишком хрупким,
  альтернатива — `aapt dump badging`/`xmltree` по пути APK (`adb shell pm path
  <pkg>` + `adb pull`); выбор конкретного инструмента — решение test-automator
  при кодировании, задокументировать в тесте.
- Тест НЕ требует Appium-сессии/WebView — чистая build-level инспекция;
  штатно можно запускать до/без поднятия драйвера.
- **Решение о гранулярности (не объединять со смежным TC-101):** оба кейса
  читают тот же `AndroidManifest.xml` тем же инструментом (`aapt`/`dumpsys`), но
  проверяют РАЗНЫЕ факты с разными Then (exported+intent-filter vs
  cleartext-политика) — реестр (`docs/feature-registry.yaml`) уже развёл их на
  отдельные записи `nf-sec-exported-components`/`nf-sec-cleartext-traffic` по
  тому же правилу гранулярности (одна запись = одно наблюдаемо различимое
  свойство); объединение в один тест-кейс замаскировало бы независимый провал
  одного из двух фактов под общим «прошёл/не прошёл».

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами (установленный APK — детерминированный build-артефакт)
- [x] Then проверяет наблюдаемое поведение, а не реализацию (собранный манифест — наблюдаемый build-level факт, не внутренняя деталь кода)
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов
- [x] Область НЕ комбинаторная (единичный статический факт манифеста) — строка `Инвариант:` не требуется
