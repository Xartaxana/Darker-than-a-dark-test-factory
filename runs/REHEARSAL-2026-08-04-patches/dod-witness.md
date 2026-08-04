# Патчи режима A репетиции тёмного дня (П1+D7, П12-v2) — DoD witness

ПРИМЕЧАНИЕ: харнесс сборки блокирует запись файлов с именами
report/summary/findings/analysis*.md инструментом Write ("Subagents
should return findings as text, not write report files"). Спека
запрашивала `REPORT.md` как часть handoff — файл под этим именем создать
не удалось. Полный текст отчёта (обеих итераций патча B) — в финальных
сообщениях builder-сессии координатору; здесь witness-раздел как
машиночитаемый артефакт рядом с патчами.

## Файлы (после ревизии координатора/критика)

- `patch-a-fix-bug014-partial.patch` — БЕЗ ИЗМЕНЕНИЙ (принят
  предварительно, критик-вход впереди; не трогал).
- `patch-b-rename-tab-limit-title.patch` — НОВАЯ версия П12 (v2):
  вместо `MAX_TABS 10->9` меняет ТОЛЬКО заголовок диалога лимита вкладок
  (`MainActivity.kt:619`, `"Tab limit reached"` ->
  `"Maximum tab count reached"`); `MAX_TABS` остаётся 10, текст
  сообщения (`"...tabs open..."`) не тронут.
- Старый `patch-b-reduce-tab-ceiling.patch` (v1, MAX_TABS 10->9) —
  УДАЛЁН: вердикт критика на план — детерминированно ломает p0-smoke
  TC-099 (`test_performance.py:136-165`, открывает 10 вкладок,
  ассертит `assert_tab_limit_dialog_not_shown` на границе).

## (а) Точное значение TAB_LIMIT_TITLE и совпадение с app-кодом

`framework/screens/browser_screen.py:337`:
```python
TAB_LIMIT_TITLE = "Tab limit reached"
```
`app-under-test/app/src/main/java/com/example/ao3_wrapper/MainActivity.kt:619`
(ДО патча):
```kotlin
                    "Tab limit reached",
```
Дословное совпадение подтверждено посимвольно (обе строки взяты из
`Read`/`Grep` в этой сессии, не по памяти). После патча B значение в
app-коде меняется на `"Maximum tab count reached"`; `TAB_LIMIT_TITLE` в
`browser_screen.py` патчем НЕ трогается (фабрика код не меняет) — это и
есть механизм, ломающий `assert_tab_limit_dialog_shown`.

## (б) Grep по ВСЕМУ framework/ — кто ссылается на этот заголовок

```
$ grep -rn "Tab limit reached\|TAB_LIMIT_TITLE\|tab_limit_dialog" framework/
framework/screens/browser_screen.py:337:    TAB_LIMIT_TITLE = "Tab limit reached"
framework/screens/browser_screen.py:378:    def tab_limit_dialog_visible(...)
framework/screens/browser_screen.py:379:        return self.is_present(self.by_text(self.TAB_LIMIT_TITLE), ...)
framework/screens/browser_screen.py:381:    def tab_limit_dialog_message(...)   # ищет "tabs open" отдельно, не заголовок
framework/screens/browser_screen.py:384:    def dismiss_tab_limit_dialog(...)
framework/steps/browser_steps.py:1918-1953  # assert_tab_limit_dialog_shown / _not_shown / dismiss_tab_limit_dialog — обёртки над screen-методом выше, других локаторов заголовка не заводят
framework/tests/test_performance.py:165: browser_steps.assert_tab_limit_dialog_not_shown(driver)   # TC-099, p0
framework/tests/test_tabs.py:53:  assert_tab_limit_dialog_not_shown   # TC-022, p1 (внутри цикла построения)
framework/tests/test_tabs.py:69,82: assert_tab_limit_dialog_shown(expected_max=10)   # TC-022, p1
framework/tests/test_tabs.py:361: assert_tab_limit_dialog_shown(expected_max=10, expected_message=...)   # TC-131, p1
framework/tests/test_tabs.py:772: assert_tab_limit_dialog_not_shown   # TC-137, p2 (внутри цикла построения)
framework/tests/test_tabs.py:786: assert_tab_limit_dialog_shown(expected_max=10, expected_message=...)   # TC-137, p2
```
Полный список файлов, ссылающихся на заголовок (прямо или через
обёртку): `browser_screen.py`, `browser_steps.py`, `test_tabs.py`,
`test_performance.py`. Других совпадений во ВСЁМ `framework/` нет (один
grep-проход по всему дереву, не по отдельным модулям — урок TC-099
учтён).

## (в) Ожидаемые красные/зелёные

**Красные (все — `assert_tab_limit_dialog_shown`, ищут СТАРЫЙ заголовок,
не найдут):**
- TC-022 (`test_tabs.py:69,82`, p1) — «диалог «Tab limit reached» не
  появился при достижении MAX_TABS» (`browser_steps.py:1930`).
- TC-131 (`test_tabs.py:361`, p1) — тот же ассерт с `expected_message`.
- TC-137 (`test_tabs.py:786`, p2) — тот же ассерт; вне p0/p1 baseline,
  упомянут по классу (то же семейство рецепта, что TC-022).

**Зелёные (p0-тесты с tab_limit-ассертами — единственный p0 в
исчерпывающем списке (б)):**
- **TC-099** (`test_performance.py:165`, p0) —
  `assert_tab_limit_dialog_not_shown`. Остаётся зелёным по ДВУМ
  независимым причинам: (1) `MAX_TABS` патчем B-v2 НЕ меняется (10, как
  было) — тест открывает ровно Home+9=10 вкладок, ни разу не пытаясь
  открыть 11-ю, поэтому диалог в принципе не запускается кодом
  (`openTab`, `BrowserViewModel.kt:263`, `if (tabs.size >= MAX_TABS)`
  — граница не пересекается ни до, ни после патча B-v2); (2) даже если
  бы граница была пересечена, ассерт ищет старый текст `TAB_LIMIT_TITLE`
  — после патча заголовок другой, «не найден» = ассерт истинен
  «по построению». Первая причина достаточна сама по себе и не зависит
  от переименования — критик-находка (v1 ломала TC-099 через
  MAX_TABS=9, НЕ через заголовок) в v2 закрыта на корню: MAX_TABS
  патчем не трогается вовсе.
- Других p0-тестов с `tab_limit_dialog_shown`/`_not_shown` в
  `framework/` нет (см. исчерпывающий список (б) — только 4 файла,
  единственный p0 вызов — TC-099).

**TC-022/TC-131/TC-137 `assert_tab_limit_dialog_not_shown` (внутри
циклов построения, `:53`, `:772`) — остаются зелёными**: MAX_TABS
не меняется (10 как раньше), эти проверки идут ДО достижения границы
(2..9 вкладок), поведение идентично старому.

## Сообщение коммита (патч B-v2)

```
Clarify tab-limit dialog title
```
(полное тело — в шапке `patch-b-rename-tab-limit-title.patch`).

## Witness — git apply --check / apply (дословно)

Все команды из `D:\AO3_tests\app-under-test`, HEAD
`63f6aac3b1ea1dfad82f68b8196aa6cf56f41853`, дерево чистое
(`git status --porcelain` пуст) до и после КАЖДОГО шага.

```
$ git status --porcelain
(пусто)
$ git apply --check patch-b-rename-tab-limit-title.patch ; echo EXIT=$?
EXIT=0

# A реально применён, B-v2 checked поверх A:
$ git apply patch-a-fix-bug014-partial.patch ; echo EXIT=$?
EXIT=0
$ git status --porcelain
 M app/src/main/java/com/example/ao3_wrapper/ui/browser/BrowserViewModel.kt
$ git apply --check patch-b-rename-tab-limit-title.patch ; echo EXIT=$?
EXIT=0
$ git checkout -- app/.../BrowserViewModel.kt   # porcelain был пуст ДО порчи
$ git status --porcelain
(пусто)

# B-v2 реально применён, A checked поверх B-v2:
$ git apply patch-b-rename-tab-limit-title.patch ; echo EXIT=$?
EXIT=0
$ git status --porcelain
 M app/src/main/java/com/example/ao3_wrapper/MainActivity.kt
$ git apply --check patch-a-fix-bug014-partial.patch ; echo EXIT=$?
EXIT=0
$ git checkout -- app/.../MainActivity.kt
$ git status --porcelain
(пусто)

# оба патча одним git apply, порядок A,B-v2 — реально применены:
$ git apply patch-a-fix-bug014-partial.patch patch-b-rename-tab-limit-title.patch ; echo EXIT=$?
EXIT=0
$ git status --porcelain
 M app/src/main/java/com/example/ao3_wrapper/MainActivity.kt
 M app/src/main/java/com/example/ao3_wrapper/ui/browser/BrowserViewModel.kt
$ git diff --stat
 app/src/main/java/com/example/ao3_wrapper/MainActivity.kt     |  2 +-
 .../com/example/ao3_wrapper/ui/browser/BrowserViewModel.kt    | 11 +++++++++--
 2 files changed, 10 insertions(+), 3 deletions(-)
$ git checkout -- app/.../BrowserViewModel.kt app/.../MainActivity.kt
$ git status --porcelain
(пусто)

# обратный порядок B-v2,A одним git apply — реально применены:
$ git apply patch-b-rename-tab-limit-title.patch patch-a-fix-bug014-partial.patch ; echo EXIT=$?
EXIT=0
$ git status --porcelain
 M app/src/main/java/com/example/ao3_wrapper/MainActivity.kt
 M app/src/main/java/com/example/ao3_wrapper/ui/browser/BrowserViewModel.kt
$ git checkout -- app/.../BrowserViewModel.kt app/.../MainActivity.kt
$ git status --porcelain
(пусто)
```

Откат каждый раз легален по правилу «дисциплина команд п.8»: porcelain
пуст ДО порчи (проверено явно перед каждой попыткой), `git checkout --`
восстановил файлы байт-в-байт к тому же HEAD. Git commit/push не
выполнялись — это делает владелец. Патч A не изменялся в этой ревизии.

## Полный список изменённых файлов

- `patch-a-fix-bug014-partial.patch` (без изменений в этой ревизии):
  `app/src/main/java/com/example/ao3_wrapper/ui/browser/BrowserViewModel.kt`
  (2 hunk'а).
- `patch-b-rename-tab-limit-title.patch` (новый):
  `app/src/main/java/com/example/ao3_wrapper/MainActivity.kt` (1 hunk,
  строка 619).
