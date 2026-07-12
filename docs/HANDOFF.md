# HANDOFF — точка возобновления

Обновлено: 2026-07-12 ~03:00 (порт-проход OS-сессии, полный Lead
Fable; журнал прохода — OS-репо, t-071/t-072). Читать первым при
старте.

## Порт-проход 2026-07-12 (итоги валидаций 5а/5б OS-репо)

Накопленный порт-лист OS-репо перенесён целиком: scout правила 3
(ЗАПРЕЩЕНО-форма с дословной строкой отказа) и 4 (позитивный
контроль пустого поиска + F-34 «форма контроля = форма вызова»,
case-insensitive негатив; прогон golden set по триггеру 1 — 6/7
PASS, строка в его Runs log); builder «изобретать требования
ЗАПРЕЩЕНО, даже если уверен»; critic — «вердикт — вход приёмки, не
приёмка» (F-33) и новое правило 11 «независимое воспроизведение
утверждений сдающего»; гигиена п.6 — класс «ложно-пустой поиск»;
словарная развязка defect_found (журнал маршрутизации ≠ bugs/
конвейера) + model обязателен и на rejected (док догнал
log_append); ретро-пара для пропущенных событий журнала;
scripts/mechanism_gate.py — tier-декларация D-0072 (механизменный
коммит требует строку `tier:` уровня lead-привязки, иначе reject с
инструкцией очереди сюда, в HANDOFF; builder t-071 + critic ПРИНЯТЬ,
поставлен Lead'ом по D-0069). ОСТАТКИ (записаны, не сделаны):
(а) тестовый близнец их гейта (рекомендация critic t-071; детектор
пока — чеки 3/13/8 OS-калибровки, логика байт-идентична
протестированной OS-версии); (б) MECHANISM_PREFIXES их гейта не
включает enforcement-цепочку (scripts/mechanism_gate.py,
log_append.py, .githooks/) — невод уже OS-версии (D-0065-класс),
расширение — решением их следующей Lead-сессии.

**Session Start (детектор пропуска handoff, .claude/skills/session-handoff/):**
первым действием новой сессии — `git status --short` и
`git log origin/master..master --oneline`. Грязное дерево или
неотправленные коммиты = прошлая сессия закрылась без
handoff-проверки — зафиксировать находкой в журнале (`log_append`),
не поглощать молча. Затем — preflight шаг 0 (сверка яруса).

Здесь ТОЛЬКО resume-заметки и критичный контекст (правило G1, docs/08 →
docs/09). Всё остальное живёт в своих местах:

| Что | Где |
|---|---|
| Очередь, счётчики, локи, эскалации | `state/factory-status.md` — **генерируется** `scripts/queue_snapshot.py`; ручные числа запрещены (A4) |
| План текущих работ | [09-improvement-plan.md](09-improvement-plan.md) |
| Спецификация фабрики (события, D1–D12, SLA) | [06-dark-factory.md](06-dark-factory.md) |
| Runtime-модель оркестрации | [03-agent-system.md](03-agent-system.md) §1 |
| Окружение, спайки A/B/C, инциденты WHPX/снапшот | [environment-setup.md](environment-setup.md) |
| История сессий | git log (подробные итоги — в сообщениях коммитов) |

## Где мы (2026-07-10, штатное закрытие)

**Ярус: закрыта на Fable (полный Lead), окон деградации не было.**
Следующая сессия — штатный preflight шаг 0.

**НОВОЕ ПРАВИЛО (фидбек оператора, CLAUDE.md «Ярусы», коммит 6073f46):
очередь фабрики (when-условия rules.yaml) диспатчится ТОЛЬКО проходом
/qa-loop.** Ручные диспатчи Lead — для не-конвейерной работы. Детектор
— чек 15(в) калибровки OS-репо.

**Сделано этой сессией (все циклы приёмки замкнуты, всё закоммичено
и запушено; witness'ы — в журнале):**
- **AT-BUG-007 Fixed** (B4, test-maintainer, critic REJECT → attempt 2
  принят): client read-timeout на command_executor (retries=False,
  штатный параметр) + `--reruns 1 --only-rerun
  ReadTimeoutError|MaxRetryError`. Висящий Appium-вызов = fail за
  ≤240с вместо вечного клина. Ждёт D1 fix-verifier (конвейер).
  Детектор механизма — чек 17 калибровки OS-репо.
- **R14 library-батч TC-027/028/029/030 автоматизирован**
  (test-automator, принят; ручной диспатч ДО введения правила
  qa-loop-only — прецедент в правиле). Кейсы Approved + automated_by →
  ждут F1 test-reviewer (конвейер).
- **Порт by/basis (D-0058) + continuation/retry в log_append.py**
  (builder + critic ACCEPT): `--by` обязателен для accepted/rejected,
  матрица ярусов enforce'ится на записи. Ось 1 SIBLING_MAP закрыта
  (OS-репо 3cd2909). Описание — CLAUDE.md «Журнал маршрутизации».
- **Авто-CA: `Start-Emulator -WritableSystem` сам ставит CA mitmproxy**
  (Install-MitmCA в tasks.ps1; промпт test-runner и environment-setup
  обновлены). Принят с оговоркой: интегрированный прогон отложен из-за
  битого quickboot-снапшота (ловушка+лечение — environment-setup.md).
  tasks.ps1 теперь UTF-8 BOM; правило «.ps1 с кириллицей — только с
  BOM» — CLAUDE.md, дисциплина команд п.7.
- **Ось 3 блока 6809e22 закрыта**: «новый блокер → test_debt-баг» у
  test-automator и test-maintainer (промпты, c50cb2f).
- **TC-056/057/058 созданы** (test-designer; минорные остатки §9
  дозакрыты по решению оператора) — в Review, ждут апрува человека.
- **Классовая чистка мет**: R-11-ярлык в 9 кейсах, «Снято» в 9
  разблокированных AT-BUG-004 кейсах; TC-015 намеренно не помечен.
- **BUG-001 расширен до коллекции «PROJECT.md расходится с кодом»**:
  пример 2 — несуществующий глобальный «Enable filtering» (блокер №2
  TC-015); test_cases: [TC-006, TC-015].
- **AT-BUG-006 грань 2 — решение Lead в баг-файле**: реальная запись
  формы Sort&Filter первично, recording_builder — только фолбэк.
- **AEHD удалён владельцем** (sc delete OK, WHPX жив; ловушка
  деинсталлятора — environment-setup.md).

## СЛЕДУЮЩИЙ ШАГ

1. **По команде оператора — проход /qa-loop**: в очереди фабрики
   F1-ревью library-батча (test-reviewer, 4 кейса) и D1-верификация
   AT-BUG-007 (fix-verifier). Вручную НЕ диспатчить (правило выше).
2. **Решения человека (не конвейера):**
   - Review→Approved с борды: 10 разблокированных AT-BUG-004 кейсов
     (TC-009/012/013/014/015/032/033/043/044/045) + 3 новых
     (TC-056/057/058) + 4 старых P3 (TC-020/024/031/037).
     Развилка TC-015 — BUG-001 пример 2 (переформулировать кейс под
     реальный per-rating тумблер или счесть дублем TC-013).
   - Риски R-09/R-10 (proposed) — утвердить/отклонить в §5.
   - TC-006 Draft — ждёт решения по BUG-001.
   - Дать/не дать добро на test_debt-баг по классу «subprocess без
     таймаута» (adb.py::_run, mitm.py:97,103 — очередь в Обсуждении
     AT-BUG-007); заведение бага уведёт их в очередь фабрики.
3. **AT-BUG-006 грань 2** (replay-запись формы) — конвейер B4, когда
   qa-loop до него дойдёт; решение и порядок уже в баг-файле.
4. **Lead, не-фабричное:** первая еженедельная калибровка
   маршрутизации ~2026-07-14 (журналы обоих репо; первый прогон
   чеков 15(в) и 17).

## Как поднять окружение (в новом окне)

```powershell
. D:\AO3_tests\scripts\env.ps1     # JAVA_HOME/ANDROID_HOME/PATH
. D:\AO3_tests\scripts\tasks.ps1   # Start-Emulator, Start-Appium, Install-App, Get-Device...
. D:\AO3_tests\scripts\board.ps1   # Show-Board (живая доска)
```

Эмулятор `ao3_test_api34` (API 34, WHPX). Replay-режим:
`Start-Emulator -WritableSystem` — **CA mitmproxy ставится
автоматически внутри** (признак успеха в выводе: «CA visible in apex
store: OK»); затем `Install-App` (после pm clear/wipe — заново) →
mitmdump → прокси гостя `10.0.2.2:8080`. Ручной фолбэк CA:
`Install-MitmCA` (tasks.ps1). **Ловушка: quickboot-снапшот может быть
битым** — эмулятор тихо гаснет, Start-Emulator висит на
wait-for-device; диагностика/лечение (`-no-snapshot-load`) —
environment-setup.md.

## Критичные факты (беречь токены)

- **Истина = код приложения.** PROJECT.md устарел (BUG-001 — коллекция
  расхождений). CLAUDE.md точнее.
- **Локаторы**: код (место рендера!) → живое дерево (`python scripts/ui_snapshot.py`)
  → скриншот. Ловушки Compose: `tab.label.uppercase()`, `AnimatedVisibility`,
  клик на родителе текстового узла, `UiScrollable` не видит Compose-скролл.
  DocumentsUI — НЕ Compose, классические View (documents_ui.py).
- **Порядок фикстур критичен**: сидинг строго ДО создания Appium-сессии.
  Фикстуры: `seeded_library`/`comment_only_work`/`loved_work_seeded`/
  `placeholder_seeded_work`/`library_*_seeded` + `replay` (mitm) —
  `framework/tests/conftest.py`; сидинг профилей — `seed_filter_profiles`.
- **Teardown-класс:** ВЕСЬ device-setup фикстуры + yield — в одном try,
  finally чистит безусловно и идемпотентно. Critic проверяет всегда.
- **Журнал**: accepted/rejected теперь ТОЛЬКО с `--by` (матрица ярусов
  enforce'ится log_append.py); continuation/retry — CLAUDE.md.
- **Рейтинг-бейдж на листинге** = background-color `[data-ao3-rate-btn]`;
  `[data-ao3-badge]` МЁРТВ — не возвращать.
- **`savePanelRating`**: несуществующий синтетический `ao3_id` → скрейп 404 →
  пустые поля; обход — `placeholder_seeded_work`.
- **Env-негатив ≠ отсутствие объекта** (CLAUDE.md «Дисциплина команд» п.6):
  присутствие устройства — только `Get-Device`; несущие утверждения о
  среде — только после сверки измерением (F-30).
- **Зависание suite**: постмортем до kill; таймаут-гейт AT-BUG-007 теперь
  превращает клин в retriable-fail за ≤240с. Известный флаки — AT-BUG-008
  (не заводить дубли).
- **Эмулятор + GPU-инференс не совмещать**; эмулятор гасить при пустой
  эмуляторной очереди (сейчас — ПОГАШЕН, Appium тоже).
- Cloudflare bot-check на старте (R-03); Git Bash: `MSYS_NO_PATHCONV=1`
  (предпочитай PowerShell-форму).
- `.ps1` с кириллицей — только UTF-8 BOM (CLAUDE.md п.7).

## Открытые хвосты (вне текущей очереди)

- **Перепрогнать интегрированный авто-CA** («один вызов
  `Start-Emulator -WritableSystem` → CA сам встал») при следующем
  здоровом replay-подъёме — отложенный witness mitm-ca-autoinstall.
- Журнал (некритичные critic по порту): 2 недостающих теста
  (rejected-после-accepted как документируемое поведение; frontmatter
  с нераспознанным model), data-quality basis при проходящем tier,
  кириллические `SystemExit` в log_append.py (класс кодировок).
- Некритичные замечания critic по AT-BUG-004 инкр.3 (при касании
  файлов): докстринг `browser_steps.py::assert_rating_badge_visible`;
  `ListingPage.badge_for` по вхождениям (нужен автоматизации TC-012).
- Устаревшая заметка в TC-028 про эскалацию seed_db (уже неактуальна)
  — почистит test-reviewer при F1.
- Минорные пробелы §9 — ЗАКРЫТЫ этой сессией (TC-056/057/058).
- `settings.local.json` разрастается — периодически `/permission-audit`
  (в эту сессию не гонялся).
- Опционально (владелец): `del C:\Windows\System32\drivers\aehd.sys`
  (мёртвый файл, служба удалена).
