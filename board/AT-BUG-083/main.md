---
key: "AT-BUG-083"
project: "AO3"
issueType: "bug"
status: "bug-open"
priority: "p2"
summary: "assert_work_not_in_tab гонится с анимацией HorizontalPager Library (тот же класс, что AT-BUG-082, но на ЛЮБОЙ вкладке, не только FILES) — не почин, только заведён (D-0043 queued follow-up)"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "sev:minor"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-17T08:25:19Z"
updated: "2026-08-17T08:25:19Z"
archived: false
resolution: null
---

# assert_work_not_in_tab гонится с анимацией HorizontalPager Library (тот же класс, что AT-BUG-082, но на ЛЮБОЙ вкладке, не только FILES) — не почин, только заведён (D-0043 queued follow-up)

_Спроецировано из `bugs/AT-BUG-083.md` (источник правды).
Статус в нашей машине: **Open**._

# AT-BUG-083 — `assert_work_not_in_tab` разделяет класс гонки AT-BUG-082, не почин в этом проходе

## Окружение

Долг тестовой системы (`type: test_debt`, `debt_kind: flaky_test`), поверхность —
`framework/steps/library_steps.py::assert_work_not_in_tab` (строки 46-51 на момент
находки).

## Обнаружено

ПОПУТНО при локализации/фиксе `AT-BUG-082`
(`assert_work_not_in_files_tab` — гонка с анимацией `HorizontalPager` вкладок
Library, `LibraryScreen.kt:238`; см. `bugs/AT-BUG-082.md`). `assert_work_not_in_tab`
— СТРУКТУРНО ИДЕНТИЧНАЯ функция (`framework/steps/library_steps.py`):

```python
def assert_work_not_in_tab(driver, rating: str, title: str):
    lib = LibraryScreen(driver).open_tab_for_rating(rating)
    assert not lib.has_work(title, timeout=4), (...)
```

Тот же паттерн, что был у `assert_work_not_in_files_tab` ДО фикса AT-BUG-082:
таплю по вкладке того же `HorizontalPager` (`open_tab_for_rating` → `open_tab`),
затем ОДИН `is_present(timeout=4)` сразу после тапа — во время анимации перехода
исходная (ещё не ушедшая) страница временно сосуществует с целевой в
accessibility-дереве, и одноразовое чтение может поймать заголовок работы,
реально принадлежащий СТАРОЙ вкладке. Это ЛЮБАЯ вкладка Library
(`LibTab.entries` — FAVORITE/KUDOSED/READ/PENDING/DISLIKED/FILES), не только
FILES — `assert_work_not_in_files_tab` была лишь ОДНИМ из нескольких мест этого
класса.

## Почему НЕ почин здесь (D-0043 «класс, не экземпляр» — явный queued follow-up)

`assert_work_not_in_tab` используется в 6+ тестовых файлах далеко за пределами
`test_downloads.py` (мандат `AT-BUG-082`):
`test_downloads.py` (TC-036/TC-116/TC-117), `test_library_filters.py` (5+ мест),
`test_library.py`, `test_rating.py`, `test_rating_listing.py`, `test_smoke.py`.
Полная классовая правка потребовала бы регресс-прогона ВСЕХ этих файлов
(на порядок больше времени, чем ~30-60 минут, заложенных на `test_downloads.py`
2x зелёный в `AT-BUG-082`) — расширение scope без отдельного диспетчерского
решения. Заведён ОТДЕЛЬНЫМ багом (не заметкой в AT-BUG-082 — правило «новый
блокер = test_debt-баг, не заметка»), т.к. это НОВЫЙ (не воспроизведённый живым
прогоном) латентный дефект, отличный экземпляр того же класса.

**НЕ красный прогон** — этот баг заведён по СТРУКТУРНОМУ анализу кода
(идентичный паттерн `open_tab*` + одноразовый `has_work(timeout=4)` негатив),
не по наблюдаемому живому падению. Приоритет `minor` (не `major`, как
AT-BUG-082) именно поэтому — латентный риск, не подтверждённая флакейность.

## Критерий готовности (Fixed)

- [ ] Применить ТОТ ЖЕ settle-poll паттерн, что `AT-BUG-082`
      (`library_steps._poll_files_tab_absent`, `_poll_ratings_marker` из
      AT-BUG-081 как общий прообраз) к `assert_work_not_in_tab` — либо
      обобщить в один общий helper, принимающий `open_tab_for_rating`/
      `open_tab(FILES_TAB)` результат и `title`.
- [ ] Красная проба/регресс: device-free unit-проба по образцу
      `test_library_files_tab_settle_unit.py` (транзитный стейл-позитив не
      маскирует реальную регрессию).
- [ ] Живой регресс — ВСЕ файлы-потребители (`test_downloads.py`,
      `test_library_filters.py`, `test_library.py`, `test_rating.py`,
      `test_rating_listing.py`, `test_smoke.py`) зелёные после правки (класс,
      не только точечные вызовы).

## Обсуждение

**[test-maintainer @ 2026-08-17T05:14:45Z]** Заведён ПОПУТНО при фиксе
`AT-BUG-082` — структурно идентичный паттерн гонки, другой набор вызывающих
тестов и файлов (не расширяю scope AT-BUG-082, доклад+баг). Диспетчеризация
фикса — за Lead/очередь B4.

**[test-maintainer @ 2026-08-17T08:25:19Z]** Побочный эффект AT-BUG-082
rework'а (критик-вход Б3): корневая причина, которую называет ЭТОТ баг
(`open_tab`/`open_tab_for_rating` таплю по вкладке `HorizontalPager` БЕЗ
ожидания settle анимации), теперь устранена НА ИСТОЧНИКЕ —
`LibraryScreen.open_tab` (`framework/screens/library_screen.py`) сам ждёт
устаканивания Pager'а (`_settle_tab_switch`/`poll_until_stable`,
`framework/core/waits.py`) ПЕРЕД возвратом, а `assert_work_not_in_tab`
вызывает `open_tab_for_rating` → `open_tab` — получает settle «бесплатно»,
как и остальные 4 читателя, перечисленные в этом баге. **НЕ закрываю
(status остаётся `Open`)**: критерий готовности ЭТОГО бага требует живого
регресса ИМЕННО перечисленных файлов-потребителей (`test_library_filters.py`,
`test_library.py`, `test_rating.py`, `test_rating_listing.py`,
`test_smoke.py`) — AT-BUG-082 rework прогонял регресс только
`test_downloads.py` (свой мандат), эти файлы НЕ перепрогонялись в этом
проходе. Правило 14: «вклад устранён» здесь — по структурному анализу (та
же причина, тот же примитив), НЕ по исключающему живому прогону ЭТИХ
конкретных файлов; статус меняет только тот, кто фактически прогонит
критерий этого бага.
