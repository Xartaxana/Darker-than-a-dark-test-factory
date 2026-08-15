---
key: "TC-232"
project: "AO3"
issueType: "test-case"
status: "tc-review"
priority: "p1"
summary: "Приватность синхронизации: токен GitLab хранится открытым текстом и попадает в авто-бэкап"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:security", "risk:R-15"]
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

# Приватность синхронизации: токен GitLab хранится открытым текстом и попадает в авто-бэкап

_Спроецировано из `test-cases/security/TC-232.md` (источник правды).
Статус в нашей машине: **Review**._

# TC-232 — Токен GitLab: открытый текст + попадание в авто-бэкап

## Предусловия
- APK установлен, синхронизация настроена (валидный непустой токен введён
  через Settings).

## Сценарий (Given-When-Then)

**Given** в Settings введён и сохранён токен GitLab

**When** (1) SharedPreferences приложения читаются напрямую (`adb shell
run-as com.example.ao3_wrapper cat
shared_prefs/<файл>.xml`) — тот же приём, что `nf-sec-backup-privacy`
**And** (2) манифест инспектируется статически (`aapt dump xmltree`) на
`android:allowBackup` и содержимое `res/xml/backup_rules.xml`

**Then** (1) значение `sync_gitlab_token` лежит в SharedPreferences ОТКРЫТЫМ
текстом (не хэш/не зашифровано)
**And** (2) `android:allowBackup="true"`, а `backup_rules.xml` не содержит НИ
ОДНОГО активного (не закомментированного) правила `<exclude>` для файла
SharedPreferences с токеном — то есть ничто не исключает его из авто-бэкапа

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Ключ prefs | `sync_gitlab_token` |
| Ожидаемая форма | plaintext |
| `allowBackup` | `true` |
| Активные exclude-правила для файла с токеном | 0 |

## Заметки для автоматизации
- Блокера нет: оба приёма (`run-as cat shared_prefs`, `aapt dump xmltree`)
  уже используются `nf-sec-backup-privacy`/`nf-sec-exported-components`
  (TC-100/TC-104) — переиспользование существующей инфраструктуры.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс
- [x] Given воспроизводим фикстурами
- [x] Then — наблюдаемое поведение (содержимое файла на устройстве + манифест)
- [x] Приоритет/область/источник указаны
- [x] Независим от порядка других кейсов
- [x] Область не комбинаторная — единичные статические факты
