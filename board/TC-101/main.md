---
key: "TC-101"
project: "AO3"
issueType: "test-case"
status: "tc-automated"
priority: "p1"
summary: "Cleartext-трафик: политика манифеста/network-security-config зафиксирована и сверена с http-схемой intent-filter (статическая инспекция)"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:security", "risk:R-15", "automation:active"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-22T22:54:43Z"
updated: "2026-07-22T22:54:43Z"
archived: false
resolution: "done"
---

# Cleartext-трафик: политика манифеста/network-security-config зафиксирована и сверена с http-схемой intent-filter (статическая инспекция)

_Спроецировано из `test-cases/security/TC-101.md` (источник правды).
Статус в нашей машине: **Automated**._

# TC-101 — Cleartext-трафик: манифест-факт (build-level)

## Предусловия
- APK тестируемой сборки установлен на устройстве.
- Проверка НЕ UI-драйвима (build-level факт) — не требует Appium-сеанса.

## Сценарий (Given-When-Then)

**Given** APK тестируемой сборки установлен на устройстве

**When** манифест инспектируется статически (тот же приём, что TC-100):
атрибут `android:usesCleartextTraffic` в `<application>` (`aapt dump
xmltree`/`dumpsys package`) и, если объявлен, ресурс
`android:networkSecurityConfig`; дополнительно сверяется data-схема
VIEW/BROWSABLE intent-filter, уже зафиксированная TC-100 (`http`/`https` на
`archiveofourown.org`)

**Then** эффективная политика cleartext-трафика зафиксирована как факт:
явное значение `usesCleartextTraffic`, ЛИБО, если атрибут отсутствует —
вычисленное умолчание по `targetSdkVersion` (`false` при targetSdk≥28, `true`
при targetSdk<28), ЛИБО значение, читаемое из `network-security-config`, если
он объявлен
**And** зафиксированное значение сверено с фактом наличия `http://`-схемы в
intent-filter (TC-100): расхождение (напр. intent-filter рекламирует `http://`,
но cleartext-трафик приложением фактически запрещён политикой, или наоборот)
фиксируется как наблюдение для триажа — кейс документирует факт, не выносит
сам вердикт «баг»/«не баг» (E4-min — smoke, не полный аудит, §8)

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Пакет | `com.example.ao3_wrapper` |
| Атрибут | `android:usesCleartextTraffic` (значение как есть в манифесте) |
| network-security-config | наличие/отсутствие ресурса, домены в нём, если есть |
| Сверяемый факт | наличие `http://archiveofourown.org` в intent-filter (TC-100) |

## Заметки для автоматизации
- Блокера нет: то же расширение статической инспекции манифеста, что TC-100
  (`adb.shell`/`aapt`), новых фикстур не требует.
- **Решение о гранулярности** (см. TC-100): кейс НЕ объединён с TC-100, хотя
  метод чтения тот же файл — Then разный (exported/intent-filter vs
  cleartext-политика), реестр фич уже развёл это на отдельные записи.
- Кейс намеренно не судит «cleartext — это плохо» (это НЕ security-аудит,
  §8) — задача smoke-минимума: зафиксировать факт и его согласованность с уже
  задекларированной http-схемой, не вынести решение о серьёзности.
- **Инструмент статической инспекции манифеста (misc-batch-0722, замечание
  critic прохода (5), `docs/09-history.md:771-773`):** вести через `aapt dump
  xmltree <apk>` (`aapt` из build-tools SDK,
  `tools/android-sdk/build-tools/36.0.0`), НЕ `dumpsys package` — атрибут
  `cleartextTraffic` в `dumpsys` неполон/косвенен для надёжной автоматизации.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами (установленный APK)
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов
- [x] Область НЕ комбинаторная (единичный статический факт + сверка с TC-100) — строка `Инвариант:` не требуется

## Ревью автотеста (F1, test-reviewer, 2026-07-22)

Вердикт: **Пройдено** (Approved → Automated, `automation_status: active`).
- **Архитектура (C1):** `arch_check.py` 0/0, ALLOWLIST пуст; статическая инспекция через
  `core/manifest.py`, `sleep` нет.
- **Traceability:** `@allure.id("TC-101")` == id; маркер `p1` == priority P1; `automated_by`
  резолвится.
- **Смысл:** тест фиксирует эффективную политику cleartext одним из трёх источников
  (`usesCleartextTraffic` / `networkSecurityConfig` / дефолт по `targetSdkVersion`) и сверяет
  с http-схемой intent-filter — это осознанно E4-min «документирует факт, не выносит вердикт»
  (§8), как и задано в Then кейса. Область не комбинаторная — строка инварианта не нужна.
- **Наблюдение (не блокер):** на реальном манифесте (нет `usesCleartextTraffic`, нет
  `networkSecurityConfig` → ветвь дефолта `targetSdk`) охранный assert
  `raw is not None or nsc_ref is not None or effective is not None` истинен по построению —
  сам ЗНАЧЕНИЕ cleartext-политики не ассертится (по дизайну non-verdict). Failable-условия
  теста: разрешимость политики (охранный assert) и совместный intent-filter-assert (TC-100).
  Соответствует явному дизайну кейса, прошедшему 2 круга critic; сигналом «баг/не-баг» служит
  allure-attachment для триажа.
- **Независимый зелёный прогон:** `Invoke-Pytest -k test_security_manifest` → 2 passed; в батче
  — 7 passed.
- **Красная проба (2026-07-22T22:54:43Z):** временно в ветви дефолта `effective = None`
  (`security_steps.py`) → `test_cleartext_traffic_policy_documented_and_cross_checked` FAILED,
  осмысленно: «не удалось зафиксировать политику cleartext-трафика ни одним из трёх источников».
  Порча откачена (Edit-revert), финальный прогон зелёный. Проба подтверждает: охранный assert
  cleartext НЕ мёртв — падает, когда политика действительно неразрешима.
