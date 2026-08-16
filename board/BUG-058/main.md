---
key: "BUG-058"
project: "AO3"
issueType: "bug"
status: "bug-fixed"
priority: "p2"
summary: "PROJECT.md ложно отрицает сетевые запросы из приложения; сетевые вызовы присутствуют в SettingsScreen и DownloadRepository"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "sev:minor"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-16T00:23:59Z"
updated: "2026-08-16T00:23:59Z"
archived: false
resolution: null
---

# PROJECT.md ложно отрицает сетевые запросы из приложения; сетевые вызовы присутствуют в SettingsScreen и DownloadRepository

_Спроецировано из `bugs/BUG-058.md` (источник правды).
Статус в нашей машине: **Fixed**._

# BUG-058 — PROJECT.md ложно отрицает сетевые запросы из приложения

Класс бага: второй пример расхождения PROJECT.md с кодом (как BUG-001, но в противоположном направлении — документация опровергает существующие функции, а не неправильно их называет).

## Окружение
- Версия приложения: dev-local (versionCode 12) — фактические значения APK (output-metadata.json)
- Сборка: debug, source_commit 6f884d97 (2026-06-28)
- Тип анализа: code inspection (без эмулятора — статический факт исходника)

## Проблема
`app-under-test/PROJECT.md:194` содержит утверждение:
> "No network calls from the app itself; all AO3 traffic goes through the WebView"

Это утверждение опровергается кодом приложения, где присутствуют прямые сетевые запросы, не проходящие через WebView.

## Шаги воспроизведения (Given-When-Then)

**Given** открыт исходный код приложения на commit 6f884d97

**When** инспектируем файлы SettingsScreen.kt и DownloadRepository.kt

**Then (ожидалось по PROJECT.md)** все сетевые запросы проходят через WebView, приложение не делает прямых вызовов к archiveofourown.org

**Actual (факт по коду)** найдены два прямых сетевых вызова:
1. **SettingsScreen.kt:259-262** — `HttpURLConnection` к `https://archiveofourown.org/works/{ao3Id}?view_adult=true` с cookie (фича "Fetch missing metadata", загрузка отсутствующих метаданных работ)
   ```kotlin
   private suspend fun fetchAo3WorkPage(ao3Id: String, cookie: String): WorkMeta? {
       val url = URL("https://archiveofourown.org/works/$ao3Id?view_adult=true")
       for (attempt in 1..3) {
           val conn = url.openConnection() as HttpURLConnection
           // ... устанавливает Cookie, User-Agent ...
   ```
2. **DownloadRepository.kt:34** — `OkHttpClient` для прямого скачивания файлов работ
   ```kotlin
   private val httpClient = OkHttpClient.Builder()
       .connectTimeout(15, TimeUnit.SECONDS)
       .readTimeout(60, TimeUnit.SECONDS)
       .followRedirects(true)
       .build()
   ```

## Частота
100% — статический факт исходника, не зависит от сборки или окружения.

## Анализ
PROJECT.md делает глобальное архитектурное утверждение о том, что приложение не инициирует сетевые запросы, но код содержит два чётких исключения из этого принципа:

1. Фича метаданных (SettingsScreen) — позволяет пользователю загружать отсутствующие в локальной БД данные работ напрямую из AO3.
2. Скачивание файлов (DownloadRepository) — позволяет сохранять работы локально через прямой HTTP-запрос.

Оба вызова — сетевые запросы ИЗ приложения к archiveofourown.org, минуя WebView.

Это расхождение требует разрешения:
- **Вариант A:** PROJECT.md устарел — требует обновления с описанием обоих сетевых каналов и их назначения.
- **Вариант B:** Архитектурное отступление намеренно — есть явное решение оставить оба вызова; тогда PROJECT.md должен это объяснить.
- **Вариант C:** Код требует переделки — обе фичи должны быть переданы WebView; тогда это архитектурное решение, а не дефект документации.

## Связь с BUG-001
Второй экземпляр класса D-0043 (документационное расхождение) из этого проекта:
- **BUG-001:** PROJECT.md неправильно НАЗЫВАЕТ существующие элементы (Loved вместо Favorite в UI-вкладках)
- **BUG-058:** PROJECT.md ОТРИЦАЕТ существующие функции (ложно утверждает отсутствие сетевых запросов)

BUG-001 открыт как коллекция класса; BUG-058 — третий пример после примера 1 и примера 2 (Enable filtering) в BUG-001. Решение 2026-07-17 указало, что это баги ДОКУМЕНТАЦИИ, не приложения.

## Верификация
| Дата | Версия сборки | Метод | Результат | Вердикт |
|---|---|---|---|---|
| 2026-08-10 | 1.10 (versionCode 11), commit 6f884d97 | Code inspection: чтение исходников + git log | Оба файла (SettingsScreen.kt, DownloadRepository.kt) содержат прямые сетевые запросы; git log подтверждает: файлы не менялись после 2026-07-17 (дата решения по BUG-001) | Расхождение подтверждено, статический факт |

## Обсуждение

**[qa @ 2026-08-10T14:30:00Z]** Обнаружено документационное расхождение: `PROJECT.md:194` утверждает "No network calls from the app itself", но код содержит прямые вызовы:
- `SettingsScreen.kt:259–262` — `HttpURLConnection` к archiveofourown.org/works (Fetch missing metadata)
- `DownloadRepository.kt:34` — `OkHttpClient` для скачивания файлов

Это второй экземпляр класса из BUG-001 (документационное расхождение). Требуется решение: 
1. Обновить PROJECT.md с описанием этих двух сетевых каналов, или
2. Принять решение, что эти вызовы — намеренное архитектурное исключение (и обновить документацию с обоснованием), или
3. Рассмотреть переделку обеих фич под WebView (требует архитектурного решения).

awaiting: dev

**[gitlab:dyakagreen @ 2026-08-15T23:08:39.624Z]** > **[dev @ 2026-08-16] Исправлено — вариант A (правка документации)**
> 
> Расхождение подтверждено, и на актуальном `main` оно было **шире, чем в отчёте**: прямых сетевых клиентов не два, а три. Третий (`SyncRepository.kt:76`, `OkHttpClient` к GitLab snippets API для синхронизации библиотеки) появился в коммите `59be96c`, уже после заведения бага, и это единственный вызов, идущий не на AO3.
> 
> Полный список, внесённый в `PROJECT.md`:
> 
> | Вызывающий код | Клиент | Назначение |
> |---|---|---|
> | `SettingsScreen.kt:342` (`fetchAo3WorkPage`) | `HttpURLConnection` | Fetch missing metadata |
> | `DownloadRepository.kt:38` | `OkHttpClient` | Скачивание файла работы |
> | `SyncRepository.kt:76` | `OkHttpClient` | Sync библиотеки через GitLab snippet |
> 
> Вариант C (переделка обеих фич под WebView) отклонён: обе принципиально не рендерят страницы, им нужен сырой ответ (HTML под парсер и файл под запись на диск), гонять это через WebView — усложнение без выигрыша.
> 
> Что именно изменено в `PROJECT.md`:
> 
> 1. Ложное утверждение «No network calls from the app itself» заменено на реальный инвариант: через WebView идёт весь **браузинг** AO3, приложение само страницы не рендерит — плюс перечислены все три исключения с назначением каждого.
> 2. Добавлен пункт про то, что оба AO3-вызова не логинятся отдельно, а переиспользуют сессию WebView: читают куку из `CookieManager.getInstance().getCookie("https://archiveofourown.org")` и шлют её заголовком `Cookie` (`DownloadRepository.kt:49`, `SettingsScreen.kt:1142`). Это важно как предупреждение: любая правка обработки кук в WebView задевает и их.
> 3. Заодно уточнён соседний пункт про креденшелы — он утверждал «no credentials stored in app» без оговорок, тогда как GitLab access token для sync действительно persist-ится в `SharedPreferences`. Теперь claim сужен до AO3, а токен назван явно.
> 
> Коммит: `27d5cfd` на `main`.
> 
> awaiting: qa

**[gitlab:dyakagreen @ 2026-08-15T23:08:49.299Z]** Метка `qa-status::QAready` выставлена на GitLab issue — переход Open→Fixed зафиксирован автоматически (второй канал, docs/06 §3а, gitlab-label).

## Чек-лист качества
- [x] Проверены дубликаты — не совпадает с BUG-001 (другой класс расхождения: отрицание вместо неправильного названия)
- [x] Репро воспроизводится на code inspection (статический факт, не требует эмулятора)
- [x] Severity обоснована как minor (как и BUG-001 — документационный класс, не функциональный дефект самого приложения)
- [x] Приложены пути и строки кода (app-under-test/ read-only)
- [x] Ни одного изменения не внесено в код приложения
