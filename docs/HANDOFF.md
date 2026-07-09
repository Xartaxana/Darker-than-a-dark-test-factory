# HANDOFF — точка возобновления

Обновлено: 2026-07-09 ~16:20 (закрытие сессии перед перезагрузкой хоста —
владелец включает WHPX). Сессия: возврат полного Lead (Fable), четвёртый
проход /qa-loop — закрыт ДОСРОЧНО из-за BSOD хоста. Читать первым при старте.

Здесь ТОЛЬКО resume-заметки и критичный контекст (правило G1, docs/08 →
docs/09). Всё остальное живёт в своих местах:

| Что | Где |
|---|---|
| Очередь, счётчики, локи, эскалации | `state/factory-status.md` — **генерируется** `scripts/queue_snapshot.py`; ручные числа запрещены (A4) |
| План текущих работ | [09-improvement-plan.md](09-improvement-plan.md) |
| Спецификация фабрики (события, D1–D12, SLA) | [06-dark-factory.md](06-dark-factory.md) |
| Runtime-модель оркестрации | [03-agent-system.md](03-agent-system.md) §1 |
| Окружение, спайки A/B/C, инцидент aehd | [environment-setup.md](environment-setup.md) |
| История сессий | git log (подробные итоги — в сообщениях коммитов) |

## Где мы (2026-07-09, сессия полного Lead, обрыв по BSOD)

**Ярус: сессия шла на Fable (полный Lead).** Деградационное окно предыдущей
сессии (Sonnet, с 2026-07-09T10:13:38) принято по D-0044 и закрыто
`lead_restored` (2026-07-09T11:56:39, нарушений окна не найдено). Следующая
сессия — штатный preflight шаг 0: сверить свою модель с ярусом Fable; ниже →
`lead_degraded` до первого Lead-действия.

**Механизменное решение полного Lead ПРИНЯТО и закоммичено (`6809e22`)** —
находка третьего прохода про блокеры-прозу закрыта:
- test-designer обязан заводить `test_debt`-баг о блокере автоматизации в том
  же ходе, до перевода кейса в Review (промпт: шаг 4 воркфлоу, carve-out из
  границы «не заводишь баги» только для test_debt);
- guard на входе правила «Автоматизировать Approved-кейс» (rules.yaml):
  (а) кейс, покрытый Open|Reopened test_debt-багом по `test_cases`, не
  диспатчится; (б) маркеры блокера в «Заметках для автоматизации» без
  покрывающего бага → сперва завести баг. Проверка (б) — детектор отказа
  обязанности test-designer.
Под-ось внесена в SIBLING_MAP OS-репо прямым коммитом (`4fc3fe9`).
**Очередь Lead OS-репо:** строка в WEEKLY_CALIBRATION_PROTOCOL — чек на отказ
самого guard'а (из AO3-сессии не вносится).

**Четвёртый проход /qa-loop — сделано до обрыва:**
- **B4 AT-BUG-004 инкремент 3 (финальный): принят, статус Fixed** (коммиты
  `ca6301b` код, `0b9d7b1` статус; приёмка `69379a7`). test-maintainer:
  download-flow запись `work_with_download.mitm` (TC-032/033),
  `listing_duplicate_work.mitm` (TC-012, двойной блёрб одного ao3_id),
  зелёная TC-009-проба `test_replay_infra_probe.py` (это доказательство
  пригодности фикстуры, НЕ автоматизация кейса). critic ACCEPT с независимым
  воспроизведением (контракт сверен с DownloadRepository.fetchDownloadUrl,
  детерминизм — нулевой diff при перегенерации). Попутный class-fix: мёртвый
  `[data-ao3-badge]`-локатор заменён проверкой background-color Rate-кнопки
  (атрибут никогда не создавался ao3_bridge.js); `.gitattributes` `*.mitm
  binary`. Некритичные замечания critic В ОЧЕРЕДИ: устаревший докстринг
  `browser_steps.py::assert_rating_badge_visible`; `ListingPage.badge_for`
  смотрит только первое вхождение — будущему TC-012 нужен вариант по всем.
- **Scout-разведка под AT-BUG-005 принята** (журнал 12:43:54, след сверен):
  приложение использует `ActivityResultContracts` —
  `CreateDocument("application/json")` (экспорт, SettingsScreen.kt:617,
  имя `ao3_backup_$date.json`), `GetContent()` (импорт, :613),
  `OpenDocumentTree()` (папка загрузок, :597, с takePersistableUriPermission).
  Готовых обходов SAF и кросс-пакетных хелперов во framework/ НЕТ.
  TC-038 — тот же класс блокера (OpenDocumentTree).
- **D1 fix-verifier по AT-BUG-004: диспатч VOID.** Событие `delegated`
  (12:52:46, task_id `at-bug-004-verify`) записано, воркер НЕ стартовал —
  хост упал раньше. Лок снят, void зафиксирован в orchestrator-log.
  Переделегирование ТЕМ ЖЕ task_id легально (accepted по нему не было).

**Инцидент хоста:** BSOD `SYSTEM_SERVICE_EXCEPTION (0x3B)` в `aehd.sys`
2026-07-09 15:02:41 (эмулятор конвейера простаивал поднятым; параллельно —
вторая сессия с node/litellm/GPU-инференсом). Разбор и правило — в
environment-setup.md «Стабильность хоста»: **эмулятор и локальный
GPU-инференс не совмещать**; между эмуляторными воркерами эмулятор теперь
ГАСИТЬ, если очередь эмуляторных работ пуста. Обновление aehd проверено:
2.2 — последний релиз, проект sunset 31.12.2026, миграция = WHPX.
**Владелец перезагружает машину, включая WHPX** (HypervisorPlatform +
VirtualMachinePlatform; до этой перезагрузки были Disabled).

## СЛЕДУЮЩИЙ ШАГ: закрыть хвост четвёртого прохода, затем пятый

0. Preflight шаг 0 (ярус) как обычно. Помнить: CLAUDE.md и rules.yaml
   изменились этой сессией (guard R14) — не полагаться на кэш.
1. **Проверить эмулятор после включения WHPX** (первый старт после
   перезагрузки): `. tasks.ps1; Get-Device` → `Start-Emulator -WritableSystem`
   → `emulator -accel-check` (ожидаем WHPX вместо AEHD; если эмулятор не
   стартует/тормозит на WHPX — задокументировать и откатиться на aehd, он
   ещё работает) → `bash scripts/install-mitm-ca.sh` (обязателен после
   КАЖДОГО старта эмулятора).
2. **Переделегировать fix-verifier** (D1, AT-BUG-004 Fixed→Verified?,
   mode=verify, task_id `at-bug-004-verify`): независимая перепроверка
   критерия готовности; фикстуры/пробы уже в дереве, сборка приложения
   не нужна.
3. **B4 AT-BUG-006 инкремент 1** → test-maintainer: поддержка таблицы
   `filter_profiles` в `seed_db.py` (схема — FilterProfileDao.kt/
   AppDatabase.kt), по образцу work_ratings. Инкремент 2 (replay-запись
   формы Sort&Filter, реальный DOM) — ОТДЕЛЬНЫЙ диспатч, не смешивать.
4. **B4 AT-BUG-005** → следующий шаг после scout-разведки: спека для
   test-maintainer — фикстура/степы автоматизации SAF-пикеров через
   UiAutomator2 по DocumentsUI (`com.android.documentsui` на AOSP API 34;
   кросс-пакетные локаторы, activate_app-паттерн уже есть в app_steps.py
   для своего пакета). Интент-подмена без правок приложения невозможна
   (запрет на изменение app-under-test) — путь через системный UI.
5. **R14 следующие батчи** (с новым guard'ом — он теперь в rules.yaml):
   library TC-027/028/029/030, затем tabs TC-022/023/025/026; затем P2
   (settings 018/019, rating 010/011, downloads 038/039, errors 046).
   TC-021 и TC-040/041/042 отсечёт guard (Open test_debt).
6. **Решение человека/test-designer (НЕ конвейера):** перевод Review→Approved
   разблокированных AT-BUG-004 кейсов — TC-009/012/013/014/015/032/033/043/
   044/045 (фикстуры готовы, транзишен P0/P1 — только human).
7. §9 стратегии: живой `needs-design` остаток по library-фильтрам (личные
   теги AND, free-text search, прочие сортировки) — правило 15, диспатч
   test-designer, когда пройдут более приоритетные (у него теперь новая
   обязанность из `6809e22`).

## Как поднять окружение (в новом окне)

```powershell
. D:\AO3_tests\scripts\env.ps1     # JAVA_HOME/ANDROID_HOME/PATH
. D:\AO3_tests\scripts\tasks.ps1   # Start-Emulator, Start-Appium, Install-App, Get-Device...
. D:\AO3_tests\scripts\board.ps1   # Show-Board (живая доска)
```

Эмулятор `ao3_test_api34` (API 34). Replay-режим: `Start-Emulator -WritableSystem`
→ boot → `bash scripts/install-mitm-ca.sh` (после КАЖДОГО старта эмулятора) →
`Install-App` → mitmdump → прокси гостя `10.0.2.2:8080`. После включения WHPX
первый старт — с проверкой `emulator -accel-check` (см. СЛЕДУЮЩИЙ ШАГ п.1).

## Критичные факты (беречь токены)

- **Истина = код приложения.** PROJECT.md устарел. CLAUDE.md точнее.
- **Локаторы**: код (место рендера!) → живое дерево (`python scripts/ui_snapshot.py`)
  → скриншот. Ловушки Compose: `tab.label.uppercase()`, `AnimatedVisibility`
  (нижняя навигация скрыта за пилюлей на Browse; RatingMenu только на Browse),
  клик на родителе текстового узла, `UiScrollable` не видит Compose-скролл.
- **Порядок фикстур критичен**: сидинг строго ДО создания Appium-сессии.
  Фикстуры: `seeded_library`/`comment_only_work`/`loved_work_seeded`/
  `placeholder_seeded_work` + `replay` (mitm) — `framework/tests/conftest.py`.
- **Рейтинг-бейдж на листинге** = background-color самой `[data-ao3-rate-btn]`
  (красит `updateRateButton`); `[data-ao3-badge]` МЁРТВ — не возвращать его в
  локаторы (class-fix инкремента 3 AT-BUG-004).
- **`savePanelRating`**: несуществующий синтетический `ao3_id` → скрейп 404 →
  пустые поля; обход — `placeholder_seeded_work`.
- **Env-негатив ≠ отсутствие объекта** (CLAUDE.md «Дисциплина команд» п.6):
  присутствие устройства — только `Get-Device`; env-тулы — только с env.ps1.
- **Эмулятор + GPU-инференс не совмещать** (environment-setup.md, BSOD
  2026-07-09); эмулятор гасить, когда эмуляторная очередь пуста.
- Cloudflare bot-check на старте (R-03); Git Bash: `MSYS_NO_PATHCONV=1`
  (предпочитай PowerShell-форму).
- Не гонять сканирование файлов bash-циклом; правка `.claude/settings.json`
  спрашивает всегда.

## Открытые хвосты (вне текущей очереди)

- Некритичные замечания critic по инкременту 3 (в очередь при следующем
  касании файлов): докстринг `browser_steps.py::assert_rating_badge_visible`
  (упоминает мёртвый атрибут); `ListingPage.badge_for` по всем вхождениям —
  понадобится автоматизации TC-012.
- Встроить `install-mitm-ca.sh` в test-runner (mount не переживает reboot).
- Ось 3 из осевого блока `6809e22` — В ОЧЕРЕДИ: проверить промпты
  test-automator/test-maintainer на симметричную обязанность «обнаружил
  НОВЫЙ блокер в ходе работы → test_debt-баг, не заметка».
- Очередь Lead OS-репо: чек калибровки на отказ guard'а R14 (см. коммит
  `4fc3fe9` SIBLING_MAP).
- 4 кейса P3 в Review (TC-020/024/031/037) + TC-006 Draft (ждёт решения
  BUG-001); R-09 (filter-profiles), R-10 (notes/tags) — proposed.
- Минорные пробелы покрытия (решение за человеком, §9 «отложенный минорный
  остаток»): подсветка совпадающих AO3-тегов; Home и Fullscreen в side panel.
- `settings.local.json` разрастается — периодически `/permission-audit`;
  владельцу — allowlist для легитимных скриптов (список в сводке аудита
  2026-07-08).
- AEHD sunset 31.12.2026: после стабилизации на WHPX — удалить aehd
  (владелец); если WHPX проблемен, откат на aehd временно допустим.
