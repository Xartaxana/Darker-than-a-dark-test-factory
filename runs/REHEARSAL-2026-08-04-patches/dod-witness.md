# Патчи режима A репетиции тёмного дня (П1+D7+versionBump, П12-v2) — DoD witness

ПРИМЕЧАНИЕ: харнесс сборки блокирует запись файлов с именами
report/summary/findings/analysis*.md инструментом Write ("Subagents
should return findings as text, not write report files"). Спека
запрашивала `REPORT.md` как часть handoff — файл под этим именем создать
не удалось. Полный текст отчёта (всех трёх раундов) — в финальных
сообщениях builder-сессии координатору; здесь witness-раздел как
машиночитаемый артефакт рядом с патчами.

## Файлы (после критик-раунда 2, подтверждён)

- `patch-a-fix-bug014-partial.patch` — ОБНОВЛЁН в этом раунде: теперь
  3 hunk'а / 2 файла — (1) `app/build.gradle.kts` `versionCode 11->12`,
  `versionName "1.10"->"1.11"` (новое, по требованию Б3 критика раунда
  2: без бампа версии rule 6/D1 по BUG-014 и гейт APP_CHANGED
  аналитика не могут отличить «новее found_in»); (2)+(3) прежние два
  hunk'а BrowserViewModel.kt (частичный фикс П1 + D7-регресс) —
  содержимое не менялось, только позиция в объединённом патче.
- `patch-b-rename-tab-limit-title.patch` — БЕЗ ИЗМЕНЕНИЙ в этом раунде
  (координатор явно просил не трогать — версию бампает A, tip
  унаследует).

## Требование 1 — versionCode/versionName в патче A

`app/build.gradle.kts` (HEAD, до патча):
```kotlin
        versionCode = 11
        versionName = "1.10"
```
Патч меняет на `versionCode = 12`, `versionName = "1.11"` (hunk
`@@ -16,8 +16,8 @@ android {`, применяется первым, до двух
kotlin-хunk'ов). Патч B не тронут — применяется вторым (порядок из
спеки репетиции §3: «владелец применяет... коммиты + push»), tip
после обоих коммитов несёt versionCode=12.

## Требование 2 — сборочный witness

Обе проверки (git apply --check по отдельности/вместе и реальная
сборка) выполнены на чистом дереве `D:\AO3_tests\app-under-test`, HEAD
`63f6aac3b1ea1dfad82f68b8196aa6cf56f41853`.

### git apply --check — A, B, A+B, B+A (дословно)

```
$ git status --porcelain
(пусто)

$ git apply --check patch-a-fix-bug014-partial.patch ; echo EXIT=$?
EXIT=0

$ git apply --check patch-b-rename-tab-limit-title.patch ; echo EXIT=$?
EXIT=0

$ git apply patch-a-fix-bug014-partial.patch patch-b-rename-tab-limit-title.patch ; echo "A+B applied EXIT=$?"
A+B applied EXIT=0
$ git status --porcelain
 M app/build.gradle.kts
 M app/src/main/java/com/example/ao3_wrapper/MainActivity.kt
 M app/src/main/java/com/example/ao3_wrapper/ui/browser/BrowserViewModel.kt
$ git diff --stat
 app/build.gradle.kts                                          |  4 ++--
 app/src/main/java/com/example/ao3_wrapper/MainActivity.kt     |  2 +-
 .../com/example/ao3_wrapper/ui/browser/BrowserViewModel.kt    | 11 +++++++++--
 3 files changed, 12 insertions(+), 5 deletions(-)
$ git checkout -- app/build.gradle.kts app/src/main/java/com/example/ao3_wrapper/ui/browser/BrowserViewModel.kt app/src/main/java/com/example/ao3_wrapper/MainActivity.kt
$ git status --porcelain
(пусто)

$ git apply patch-b-rename-tab-limit-title.patch patch-a-fix-bug014-partial.patch ; echo "B+A applied EXIT=$?"
B+A applied EXIT=0
$ git status --porcelain
 M app/build.gradle.kts
 M app/src/main/java/com/example/ao3_wrapper/MainActivity.kt
 M app/src/main/java/com/example/ao3_wrapper/ui/browser/BrowserViewModel.kt
$ git checkout -- app/build.gradle.kts app/src/main/java/com/example/ao3_wrapper/ui/browser/BrowserViewModel.kt app/src/main/java/com/example/ao3_wrapper/MainActivity.kt
$ git status --porcelain
(пусто)
```

### Сборка (канонической формой) — оба патча применены реально

Канон: `. D:\AO3_tests\scripts\env.ps1; Build-Ao3Apk` — `env.ps1`
кладёт `JAVA_HOME = D:\AO3_tests\tools\jdk-21.0.11+10` в окружение,
`Build-Ao3Apk` делает `Push-Location app-under-test;
.\gradlew.bat assembleDebug`.

```
$ git status --porcelain
(пусто)
$ git apply patch-a-fix-bug014-partial.patch patch-b-rename-tab-limit-title.patch
$ git status --porcelain
 M app/build.gradle.kts
 M app/src/main/java/com/example/ao3_wrapper/MainActivity.kt
 M app/src/main/java/com/example/ao3_wrapper/ui/browser/BrowserViewModel.kt

$ powershell -NoProfile -ExecutionPolicy Bypass -Command ". D:\AO3_tests\scripts\env.ps1; Build-Ao3Apk"
AO3 test env ready: JAVA_HOME, ANDROID_HOME, adb/emulator in PATH
Starting a Gradle Daemon (subsequent builds will be faster)

> Configure project :app
WARNING: The option setting 'android.disallowKotlinSourceSets=false' is experimental.
The current default is 'true'.
> Task :app:preBuild UP-TO-DATE
... (36 actionable tasks, включая :app:kspDebugKotlin, :app:compileDebugKotlin,
    :app:dexBuilderDebug, :app:packageDebug, :app:assembleDebug)

BUILD SUCCESSFUL in 1m 11s
36 actionable tasks: 11 executed, 25 up-to-date
```
(полный лог — 55 строк, сохранён в
`C:\Users\user\AppData\Local\Temp\claude\D--AO3-tests\0444b51e-f7ae-47a5-a6ba-8b624f58e564\tasks\b4i17drbx.output`
на время сессии; воспроизведён здесь дословно кроме списка UP-TO-DATE
тасков, сокращённого для читаемости — сама строка BUILD SUCCESSFUL и
время сборки не тронуты).

APK собран: `app-under-test/app/build/outputs/apk/debug/app-debug.apk`
(гитигнорен, `find` подтвердил присутствие файла — НЕ чистился).

### Откат после сборки

```
$ git status --porcelain
 M app/build.gradle.kts
 M app/src/main/java/com/example/ao3_wrapper/MainActivity.kt
 M app/src/main/java/com/example/ao3_wrapper/ui/browser/BrowserViewModel.kt
$ git checkout -- .
$ git status --porcelain
(пусто)
$ git rev-parse HEAD
63f6aac3b1ea1dfad82f68b8196aa6cf56f41853
```
Откат легален (правило 8 дисциплины команд): porcelain пуст ДО порчи
(зафиксировано explicit-выводом непосредственно перед `git apply` для
сборки), после сборки изменены только 3 файла (те же, что патчи
трогают) — `git checkout -- .` восстановил их байт-в-байт к HEAD;
`build/` (гитигнорен) не затронут checkout'ом и не чистился. Git
commit/push не выполнялись — это делает владелец.

## (а) Точное значение TAB_LIMIT_TITLE и совпадение с app-кодом

`framework/screens/browser_screen.py:337`:
```python
TAB_LIMIT_TITLE = "Tab limit reached"
```
`app-under-test/.../MainActivity.kt:619` (до патча B): `"Tab limit reached"`
— дословное посимвольное совпадение подтверждено чтением обоих файлов.
После патча B — `"Maximum tab count reached"`; `TAB_LIMIT_TITLE` в
`browser_screen.py` не трогается (фабрика код не меняет).

## (б) Grep по ВСЕМУ framework/ — кто ссылается на этот заголовок

```
$ grep -rn "Tab limit reached\|TAB_LIMIT_TITLE\|tab_limit_dialog" framework/
framework/screens/browser_screen.py:337,378,379,381,384
framework/steps/browser_steps.py:1918-1953
framework/tests/test_performance.py:165   # TC-099, p0
framework/tests/test_tabs.py:53,69,82,355,357,361,772,782,785,786   # TC-022 (p1), TC-131 (p1), TC-137 (p2)
```
Ровно 4 файла во всём дереве `framework/` — исчерпывающий проход, не по
отдельному модулю (урок TC-099 учтён).

## (в) Ожидаемые красные/зелёные (патч B)

**Красные:** TC-022 (`test_tabs.py:69,82`, p1), TC-131 (`:361`, p1),
TC-137 (`:786`, p2, вне p0/p1 baseline) — все через
`assert_tab_limit_dialog_shown`, ищущий старый заголовок.

**Зелёные, p0:** TC-099 (`test_performance.py:165`) — единственный
p0-тест с tab_limit-ассертом во всём `framework/`. Остаётся зелёным по
двум независимым причинам: (1) `MAX_TABS` не менялся (10) — тест
открывает ровно 10 вкладок, границу никогда не пересекает, диалог не
вызывается кодом вовсе; (2) даже гипотетически — ассерт ищет старый
текст, «не найден» = assert true by construction.

TC-022/TC-137 внутренние `assert_tab_limit_dialog_not_shown` (`:53`,
`:772`, до достижения границы) — не задеты, MAX_TABS не менялся.

## Сообщения коммитов

Патч A (тело — в шапке файла):
```
Fix BUG-014: only auto-download Favorite on rating transition, not every panel save
```
Патч B (тело — в шапке файла):
```
Clarify tab-limit dialog title
```

## Полный список изменённых файлов

- `patch-a-fix-bug014-partial.patch`: `app/build.gradle.kts` (1 hunk),
  `app/src/main/java/com/example/ao3_wrapper/ui/browser/BrowserViewModel.kt`
  (2 hunk'а).
- `patch-b-rename-tab-limit-title.patch`:
  `app/src/main/java/com/example/ao3_wrapper/MainActivity.kt` (1 hunk).
