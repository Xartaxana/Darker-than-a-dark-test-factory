---
key: "AT-BUG-043"
project: "AO3"
issueType: "bug"
status: "bug-open"
priority: "p1"
summary: "core/mitm.py: гонка teardown/startup порта 8080 между соседними replay-тестами (WinError 10048, дважды подряд) — блокировала D1-верификацию AT-BUG-039"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "test_case:TC-124", "test_case:TC-125", "test_case:TC-126", "test_case:TC-127", "sev:major"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-03T10:11:25Z"
updated: "2026-08-03T10:11:25Z"
archived: false
resolution: null
---

# core/mitm.py: гонка teardown/startup порта 8080 между соседними replay-тестами (WinError 10048, дважды подряд) — блокировала D1-верификацию AT-BUG-039

_Спроецировано из `bugs/AT-BUG-043.md` (источник правды).
Статус в нашей машине: **Open**._

# AT-BUG-043 — гонка порта 8080 в core/mitm.py между соседними replay-тестами

## Окружение
Долг тестовой системы (`type: test_debt`, `debt_kind: broken_environment`) —
не зависит от сборки приложения. Обнаружен `fix-verifier` при D1-верификации
`bugs/AT-BUG-039.md` (2026-08-03), задокументирован `state/escalations.md`
`ESC-016`.

## Суть долга

Два прогона DoD-набора (`tests/test_reading_ux.py -k
"test_tap_zone_top_third_scrolls_up or test_tap_zone_bottom_third_scrolls_down
or test_tap_to_scroll_live_push_and_reload_persistence or
test_tap_to_scroll_survives_kill_and_relaunch"`) подряд дали идентичную
сигнатуру в setup replay-фикстуры (`mitmdump`) на РАЗНЫХ узлах каждого
прогона:

```
[Errno 10048] HTTP(S) proxy failed to listen on 0.0.0.0:8080 ...
address already in use
```

Раунд 1: узел TC-125 упал на этой сигнатуре. Раунд 2 (изолированный повтор,
допущенный протоколом fail-fast): TC-125 прошёл чисто, но TC-126 и TC-124
несли ТУ ЖЕ сигнатуру. Диагностика между прогонами — устройство/Appium/CA
здоровы (`Get-Device`→DEVICE, Appium `/status`→ready:true, cacerts store=134);
порт 8080 В ПОКОЕ свободен (`Get-NetTCPConnection -LocalPort 8080` пуст,
`Get-CimInstance Win32_Process` по `mitmdump|mitmproxy` — 0 совпадений) — то
есть в момент диагностики порт освобождён, но освобождение НЕ УСПЕВАЕТ до
старта следующего теста в потоке прогона. Похоже на гонку teardown
(`stop()`)/startup (`start_replay()`) соседних тестов в `framework/core/mitm.py`
на Windows (TIME_WAIT на закрытии сокета или асинхронный teardown, не
дождавшийся освобождения перед следующим `start_replay()`).

Дополнительно в тех же двух прогонах наблюдались ДРУГИЕ, вероятно
независимые transient-сбои (не входят в критерий этого бага, отмечены для
полноты): `BottomNav._find_pill` timeout (TC-126/TC-127, раунд 1),
`loved_work_seeded`/`adb run-as` ошибка (TC-124, раунд 1),
`sqlite3.OperationalError: no such table: work_ratings` (TC-127, раунд 2) —
последнее структурно совпадает с находкой критика при приёмке `AT-BUG-042`
этим же проходом (`seed_db.ensure_db_initialized` ждёт файл БД, не схему) —
возможный sibling, требует отдельного разбора, не смешивать с портовой
гонкой без подтверждения.

## Критерий готовности (Fixed)

- [ ] Диагностирован механизм гонки в `core/mitm.py::stop()`/`start_replay()`
  (или соседнем коде фикстуры `replay`) — почему освобождение порта 8080
  предыдущим тестом не гарантированно завершается до старта следующего.
- [ ] Фикс устраняет гонку (варианты на выбор диагностики: явное ожидание
  освобождения порта перед bind, SO_REUSEADDR, сериализация teardown/startup
  между тестами, retry с backoff на bind) — без ослабления таймаутов вслепую.
- [ ] Красная проба: воспроизведена гонка ДО фикса (например, форсированный
  быстрый teardown+startup двух replay-сессий подряд без устройства) и
  устранена ПОСЛЕ.
- [ ] DoD-набор `AT-BUG-039` (TC-124/125/126/127) проходит ОДНИМ чистым
  прогоном без WinError 10048.
- [ ] arch_check/validate_frontmatter — 0/0.
- [ ] Ни одно изменение не внесено в `app-under-test/`.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|

## Обсуждение

**2026-08-03T10:11:25Z — координатор (Sonnet), заведение по докладу fix-verifier
D1 AT-BUG-039:** `fix-verifier` предложил заведение (next_rules), но не завёл
сам (вне owns/non-goals своего диспатча — правило D-0037, не расширять scope).
Заведено координатором машиночитаемым артефактом (не оставлено только в
`state/escalations.md` `ESC-016` прозой) — иначе B4-сканер очереди его не
увидит (прецедент `ESC-004`→`AT-BUG-020`, тот же класс решения). `AT-BUG-039`
переведён `Fixed → Blocked` этим же диспатчем (`awaiting: dev`,
`blocked_reason: environment`) — держится на этом баге: чинить его раньше,
чем повторять D1-верификацию `AT-BUG-039` в третий раз вслепую.

## Чек-лист качества (заводящий проходит перед публикацией)
- [x] Проверены дубликаты среди открытых test_debt: не пересекается с
  AT-BUG-006/AT-BUG-009 (mitm-CA волатильность после ребута, другой
  механизм), AT-BUG-016/024/026 (qemu-краш 0xc0000005, другая сигнатура),
  ESC-009 (IPv6-транзит хоста, другая сигнатура) — эта запись про конкретно
  bind-гонку порта 8080 между соседними тестами одной сессии
- [x] Severity обоснована влиянием: major — блокирует D1-верификацию B4-фиксов
  на replay-наборах, затрагивает произвольные соседние тесты, не единичный
  кейс
- [x] Приложены материалы: дословный witness fix-verifier (2 прогона),
  диагностика Get-Device/Appium/CA/порт-в-покое, `state/escalations.md` ESC-016
- [x] Нет изменений кода приложения
