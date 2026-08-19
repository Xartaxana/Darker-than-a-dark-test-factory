---
key: "BUG-079"
project: "AO3"
issueType: "bug"
status: "bug-open"
priority: "p1"
summary: "Приложение хранит персональный GitLab-токен в открытых SharedPreferences под android:allowBackup=true; backup_rules.xml пуст; выгрузка библиотеки не ограничена по хосту"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "sev:major"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-19T16:30:00Z"
updated: "2026-08-19T16:30:00Z"
archived: false
resolution: null
---

# Приложение хранит персональный GitLab-токен в открытых SharedPreferences под android:allowBackup=true; backup_rules.xml пуст; выгрузка библиотеки не ограничена по хосту

_Спроецировано из `bugs/BUG-079.md` (источник правды).
Статус в нашей машине: **Open**._

# BUG-079 — Персональный GitLab-токен подлежит Android Auto Backup и выгрузке на произвольный хост без ограничений

## Окружение
- Версия приложения: dev-local (versionCode 12)
- Сборка: debug, source_commit aa377e0e (2026-06-28)
- Тип анализа: code inspection исходников, чтение AndroidManifest.xml, SyncRepository.kt, backup_rules.xml

## Шаги воспроизведения (Given-When-Then)

**Given** приложение установлено на Android-устройство, пользователь ввёл персональный GitLab-токен с областью доступа `api` в Settings для синхронизации библиотеки

**When** 
1. Пользователь включает Android Auto Backup (облако Google Drive)
2. Или выполняет `adb backup -apk com.example.ao3_wrapper` (создаёт локальный бэкап приложения)
3. Или устанавливает пользовательский хост GitLab вместо gitlab.com

**Then (ожидалось)**
- Персональный токен НИКОГДА не попадает в резервную копию (шифруется, исключается из backup, или хранится в защищённом хранилище — Keystore)
- Библиотека выгружается ТОЛЬКО на HTTPS-хосты с ограничениями (например, gitlab.com или локальный Git)
- При попытке выгрузить на небезопасный хост пользователю показывается предупреждение

**Actual (фактически)**
Персональный GitLab-токен хранится в открытых SharedPreferences под `android:allowBackup="true"` и попадает в:
- Android Auto Backup (облако)
- `adb backup` (неуправляемые файлы на рабочей машине разработчика)
- Данные библиотеки выгружаются на ЛЮБОЙ хост, введённый пользователем, без валидации протокола или имени хоста

## Контекст: техническая цепочка уязвимости

1. **Хранилище токена в открытом виде** (SyncRepository.kt:47, SettingsScreen.kt:214, 277)
   ```
   app-under-test/app/src/main/java/com/example/ao3_wrapper/data/sync/SyncRepository.kt:47
   private const val PREF_TOKEN = "sync_gitlab_token"
   ```
   Токен сохраняется и читается через обычный `SharedPreferences.getString()` без шифрования.

2. **Android Auto Backup ВКЛЮЧЕН** (AndroidManifest.xml:9)
   ```
   app-under-test/app/src/main/AndroidManifest.xml:9
   android:allowBackup="true"
   ```

3. **Правила исключения пусты** (backup_rules.xml)
   ```
   app-under-test/app/src/main/res/xml/backup_rules.xml
   <full-backup-content>
       <!--
       <include domain="sharedpref" path="."/>
       <exclude domain="sharedpref" path="device.xml"/>
   -->
   </full-backup-content>
   ```
   Файл содержит только комментарии; все SharedPreferences (включая `sync_gitlab_token`) автоматически попадают в резервную копию.

   То же для API 31+: манифест указывает `android:dataExtractionRules="@xml/data_extraction_rules"` (AndroidManifest.xml:10), и `res/xml/data_extraction_rules.xml` тоже пуст (только TODO-комментарии в `<cloud-backup>`) — исключений нет ни на старом, ни на новом пути бэкапа. *(факт добавлен на приёмке Lead 2026-08-19)*

4. **Выгрузка на произвольный хост без ограничений** (SyncRepository.kt:62–63, 245, 270, 292)
   ```
   app-under-test/app/src/main/java/com/example/ao3_wrapper/data/sync/SyncRepository.kt:62–63
   private val instanceUrl: String
       get() = (prefs.getString(PREF_INSTANCE, null)?.takeIf { it.isNotBlank() } ?: DEFAULT_INSTANCE)
           .trim().trimEnd('/')
   ```
   Хост читается прямо из `SharedPreferences` без валидации. Используется в:
   - SyncRepository.kt:245 — `fetchRemote`: `"$instanceUrl/api/v4/snippets/$id/raw"`
   - SyncRepository.kt:270 — `createSnippet`: `"$instanceUrl/api/v4/snippets"`
   - SyncRepository.kt:292 — `updateSnippet`: `"$instanceUrl/api/v4/snippets/$id"`

   Пользователь может ввести `http://attacker.com` или `http://localhost:8080` — приложение не проверяет ни протокол, ни доменное имя.

## Последствия (CVSS 3.1 риск)

**Потенциальный поток атаки:**
1. Злоумышленник получает доступ к облачному аккаунту Google Drive пользователя → скачивает Auto Backup приложения
2. Или: разработчик делает `adb backup` на рабочей машине, файл резервной копии украден
3. Или: пользователь вводит хост злоумышленника вместо gitlab.com; приложение безопасно отправляет токен на неконтролируемый сервер

**Риск (по docs/01-test-strategy.md §5 R-19):**
- Персональный токен GitLab с областью доступа `api` может быть использован для:
  - Чтения/изменения любых приватных репозиториев пользователя в GitLab
  - Создания/удаления snippets на аккаунте пользователя
  - Утечки данных, стоящих на этом GitLab-инстансе

## Частота
100% (архитектурная проблема хранения, не флаки; воспроизводится на любом устройстве с включённым Auto Backup).

## Артефакты
- Хранилище: `app-under-test/app/src/main/java/com/example/ao3_wrapper/data/sync/SyncRepository.kt:47` (PREF_TOKEN)
- Чтение/запись: `app-under-test/app/src/main/java/com/example/ao3_wrapper/ui/settings/SettingsScreen.kt:214, 277`
- Манифест: `app-under-test/app/src/main/AndroidManifest.xml:9, 11` (allowBackup, fullBackupContent)
- Правила backup: `app-under-test/app/src/main/res/xml/backup_rules.xml` (пусто)
- Построение URL: `app-under-test/app/src/main/java/com/example/ao3_wrapper/data/sync/SyncRepository.kt:62–63` (instanceUrl)
- Использование в запросах: `app-under-test/app/src/main/java/com/example/ao3_wrapper/data/sync/SyncRepository.kt:245, 270, 292`
- Контекст риска: `docs/01-test-strategy.md §5 R-19, §10(щ) п.2`

## Анализ

Класс дефекта: **Security — неправильное хранение и передача критичного секрета**

Компоненты уязвимости:
1. **Отсутствие шифрования** — токен лежит в открытом текстовом виде в SharedPreferences
2. **Неправильная настройка backup** — android:allowBackup="true" без исключений означает, что ВСЕ SharedPreferences (включая токен) попадают в:
   - Android Auto Backup (Google Cloud)
   - `adb backup` (локальный файл на рабочей машине)
3. **Отсутствие валидации хоста** — пользователь может задать произвольный хост; нет проверки на HTTPS, не проверяется имя хоста, не показывается предупреждение

**Минимум дефект:** токен не исключён из Auto Backup.

**Полный спектр дефектов:**
1. Токен должен храниться в EncryptedSharedPreferences (при API ≥24) или Android Keystore
2. Или: backup_rules.xml должен иметь `<exclude domain="sharedpref" path="default.xml"/>` и явное исключение токена
3. Валидация URL: только HTTPS, предупреждение при вводе нестандартного хоста
4. Возможно: PIN/биометрия для доступа к токену в Settings

## Вопросы разработчику

1. **Как планируете защищать токен?** Выбор подхода:
   - EncryptedSharedPreferences (androidx.security:security-crypto) с API ≥24 fallback на SharedPreferences
   - Android KeyStore (PrivateKey-based encryption)
   - Другой способ?
   Временная мера (если не успеть в ближайший релиз): явное исключение токена в backup_rules.xml + документирование в PROJECT.md

2. **Выгрузка на произвольный хост:** планируются ли ограничения?
   - HTTPS-only (валидация URL при вводе)?
   - Whitelist известных GitLab-инстансов (gitlab.com + локальные)?
   - Предупреждение при вводе нестандартного хоста?
   - Требование авторизации для синка (Keystore PIN)?

3. **Android Auto Backup:** нужно ли отключать явно (android:allowBackup="false"), или достаточно исключения токена в backup_rules.xml?

---

## Дубликат-чек

Поиск по `bugs/`:
- Ключевое слово `gitlab_token` / `sync_gitlab_token` / `token.*SharedPreferences` → найдено только в BUG-058.md (документационный дефект про PROJECT.md, не про безопасность)
- Ключевое слово `allowBackup` / `android:allowBackup` / `backup_rules` → ничего в открытых app_bug
- Ключевое слово `secret` / `password` / `encrypt` / `security` → BUG-012 (про broadcast бейджей, не про криптографию), AT-BUG-082/055/026/024 (test_debt)
- Ключевое слово `sync` + `хост` / `URL` / `arbitrary` → BUG-074/077/078 про синк (но не про уязвимость), AT-BUG-073 (test_debt)

**Вывод:** это новый баг, дубликатов не найдено. BUG-058 — про документацию, не про дефект приложения.

## Чек-лист качества
- [x] Проверены дубликаты среди открытых app_bug; новый баг, уникален
- [x] Все четыре факта дефекта подтверждены кодом (file:line указаны):
  - [x] Токен в SharedPreferences (SyncRepository.kt:47)
  - [x] allowBackup="true" (AndroidManifest.xml:9)
  - [x] backup_rules.xml пуст (только комментарии)
  - [x] Произвольный хост без валидации (SyncRepository.kt:62–63)
- [x] Severity (major) обоснована: персональный токен с API-доступом может скомпрометировать аккаунт GitLab пользователя
- [x] Секция вопросов разработчику присутствует (3 вопроса: способ защиты, валидация хоста, backup-стратегия)
- [x] Ссылка на риск: R-19 (docs/01-test-strategy.md §5, §10(щ) п.2)
- [x] Указана точная версия сборки (dev-local, versionCode 12, source_commit aa377e0e)
- [x] Ни одного изменения не внесено в app-under-test/ или docs/

## Обсуждение

**[qa @ 2026-08-19T16:30:00Z]** Обнаружена цепочка уязвимости SEC (R-19 из docs/01-test-strategy.md):
1. Персональный GitLab-токен хранится в открытых SharedPreferences (SyncRepository.kt:47) — БЕЗ шифрования
2. android:allowBackup="true" (AndroidManifest.xml:9) включен, backup_rules.xml пуст (только комментарии)
3. Все SharedPreferences, включая токен, попадают в Android Auto Backup и adb-backup
4. Библиотека выгружается на ЛЮБОЙ хост, введённый пользователем (SyncRepository.kt:62–63), без валидации URL

Последствие: персональный токен GitLab может быть украден через облако или неконтролируемый сервер. Требуется решение по защите (EncryptedSharedPreferences/Keystore, исключение из backup_rules, валидация URL).
awaiting: dev
