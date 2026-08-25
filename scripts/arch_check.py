"""arch_check — статические проверки архитектуры тест-фреймворка (docs/08 §4 C1).

Конвенция слоёв (framework/README.md, docs/02): tests -> steps -> screens/web ->
core. Слой tests/ — только шаги (steps) + assert, маркеры p0/p1/.../live/replay и
@allure.title. Локаторы (AppiumBy/UiSelector/By/EC) и прямой driver (driver_factory,
низкоуровневые find_element(s)) живут только в screens//web/. До сих пор это была
конвенция из README/докстрингов — здесь она превращается в исполняемую проверку
(docs/08 §4 C1: "Документы требуют tests -> steps -> screens/web -> core, но это
пока конвенция").

Проверяются все framework/tests/**/test_*.py (то же, что видит pytest — python_files
= test_*.py из framework/pytest.ini; conftest.py и __init__.py не тест-модули и не
сканируются, как и в самом pytest).

Правило 1 — NO-LOCATORS-IN-TESTS: тест-модуль не должен:
  - импортировать framework.screens.*, framework.web.*, framework.core.driver_factory,
    framework.core.waits, либо локаторные модули appium/selenium
    (AppiumBy/MobileBy/By/expected_conditions/ui.WebDriverWait);
  - вызывать методы-локаторы напрямую (find_element, find_elements, by_text,
    by_desc, by_text_contains — последние три объявлены в screens/base_screen.py);
  - содержать литеральную строку с "UiSelector(" (скопированный локатор мимо
    screens/), кроме docstring/комментария-строки.

Правило 2 — ALLURE-ID + SUITE MARKER: каждая тест-функция (def test_*, как задаёт
python_functions = test_*/python_classes = Test* в pytest.ini) обязана иметь:
  - декоратор @allure.id(...) (по нему тест-кейс TC-xxx привязывается к автотесту,
    см. test_rating.py/test_library.py);
  - хотя бы один suite-маркер уровня приоритета. Набор suite-маркеров выводится
    динамически из framework/pytest.ini (секция `markers`, имена вида p<N>: p0
    smoke, p1 регрессия, p2 расширенное покрытие, p3 косметика). Маркеры live/
    replay/quarantine — это режим прогона, а не suite, и не считаются.

test_smoke.py устранён (AT-BUG-002, test-debt/B4): импорты screens вынесены за
steps/, все 5 тестов имеют @allure.id. ALLOWLIST ниже содержит известные
исключения ОДНОГО легального класса — «device-free юнит-проба САМОГО
screens-класса» (категория установлена AT-BUG-059; C1 писан против
tests->локаторы мимо steps в ПРОДУКТОВЫХ тестах, а не против тестирования
самого screens-слоя). Каждая запись обязана называть тикет-источник и
обоснование; исключение ВНЕ этого класса — только с отдельным test-debt
тикетом, чей предмет и есть это исключение (решение Lead 2026-08-11 при
добавлении второй записи, AT-BUG-062).

Правило 3 — CASE-RECORDING-CONSISTENCY (mech-case-recording-check,
scratchpad/spec-case-recording-check.md v3): ВТОРАЯ ветвь обхода — test-cases/,
не framework/tests/. Сверяет replay-записи (`.mitm`), названные в секциях
Предусловий/Сценария кейса, с записями, которые реально берёт его
`automated_by`-тест (объединение значений `@pytest.mark.parametrize`, чей
argnames содержит `replay`). Отдельный WARNS-канал (см. `run_recording_rule`/
`run`) — находки не влияют на exit-код, до отдельного решения Lead о промоции
в ERROR по evidence.

Правило 4 — NEGATIVE-THEN-WITHOUT-SETTLE (спека D v2, критик-раунд D2): ТРЕТЬЯ
ветвь обхода — framework/steps/*.py (плоско, без рекурсии). Матчер — AST, не
регекс (критик доказал: регекс слеп к receiver-вызовам конструктора вида
`Screen(driver).method()`), И ограничен ПРЕДИКАТОМ ИМЕНИ ВЫЗЫВАЕМОГО МЕТОДА
(`NEGATIVE_THEN_METHOD_PATTERN` — `is_.*|has_.*|.*_has_.*|.*_visible|
.*_present|.*_expanded|.*_highlighted`; критик-вход D2-B1: без предиката
голый `ast.Call(func=ast.Attribute)` даёт 10 ЛОЖНЫХ попаданий в
framework/tests — `Path(...).exists()` x7, `.issubset()`, `.endswith()` — для
которых WARN-текст про presence-примитив бессмыслен):

    ast.Assert(test=ast.UnaryOp(op=ast.Not, operand=ast.Call(func=ast.Attribute)))
    # + operand.func.attr матчит NEGATIVE_THEN_METHOD_PATTERN

т.е. `assert not <получатель>.<presence-метод>(...)`, получатель — любое
выражение (имя, цепочка атрибутов, вызов конструктора). Замер ФОРМЫ 1
предикат-фильтрованной на этом репо: 18 попаданий в framework/steps/, 0 в
framework/tests/screens/web/core/data (критик-раунд round3, замечание 3:
раньше здесь стояло «19» — число старше ровно на один снятый экземпляр,
AT-BUG-090 `assert_chip_absent`, и вдобавок смешивало формы; 19 — это
популяция ОБЕИХ форм, см. NEGATIVE_THEN_SETTLE_BASELINE). Дефект: presence-примитив
(`is_visible`/`is_present`/`chip_visible`/...) читает состояние ОДИН РАЗ и
возвращает немедленно, пока элемент/чип/оверлей ещё может быть на экране —
негативный Then обязан ЖДАТЬ исчезновения (`wait_absent`/settle-hold-полл,
см. `base_screen.wait_absent:85`), а не читать примитив присутствия сразу
после действия. Отдельный WARNS-канал, ярус WARN (не ERROR): каждое
попадание обязано иметь запись-вердикт в `NEGATIVE_THEN_SETTLE_BASELINE`
(тикет-источник + вердикт, см. докстринг словаря) — запись без вердикта
недопустима, промоция части попаданий в ERROR/фикс — отдельное решение Lead
по конкретному тикету, не этим правилом. Ключ бейзлайна —
`(rel_от_framework, func_name, method_name)` — НЕ lineno (критик-вход D2-F1:
lineno дрейфует за рефакторингом, 7 из 19 строк сместились за ~20 коммитов;
`func_name`/`method_name` устойчивы к сдвигу строк, коллизий на живом репо
нет); lineno остаётся в тексте самого WARN для навигации.

Дельта 16 (число спеки, пересчитанное на сегодня) -> 18 — НЕ "мощность
AST против регекса" (критик-вход D2-B2): исходный предикат спеки давал
РОВНО 16; предикат расширен ДВУМЯ паттернами (`.*_has_.*`, `.*_highlighted`)
по факту — они ловят 2 истинных члена того же класса дефекта
(`browser_steps.py::assert_filter_not_offered` -> `filter_dropdown_has_
option`, `browser_steps.py::assert_tag_not_highlighted` -> `tag_link_
highlighted`, докстринг последнего сам называет проверку «мгновенной, не
опросом») — осознанная девиация от узкого предиката спеки, не техническая
случайность. ЧИСЛА (критик-раунд round3, замечание 3): 17 -> 19 в прежней
редакции этого абзаца были старше ровно на один снятый экземпляр (AT-BUG-090
`assert_chip_absent`, починен 2026-08-20 — форма 1 перестала матчиться, запись
из бейзлайна СНЯТА); фактическая популяция формы 1 сегодня 16 -> 18. Само
число 19 в NEGATIVE_THEN_SETTLE_BASELINE ТОЧНО и относится к ОБЕИМ формам:
18 формы 1 + 1 формы 3, 0 фантомов.

Нечитаемый steps-файл (SyntaxError/UnicodeDecodeError) НЕ даёт находки НИ
ОДНОГО правила модуля — правила 1-2 обходят только TESTS_DIR
(framework/tests/), framework/steps/ вне их обхода (критик-вход D2-F2,
исправлена ложная докстринг-ссылка на их ERROR-канал); правило 4 кладёт
собственную WARN-находку `rule="negative_then_settle_parse"` («steps-файл не
разобран — правило 4 по нему не применялось») вместо тихого пропуска.

ОСТАТОЧНАЯ ДЫРА (правило 4, признана и НЕ закрыта в этом ходе): двухшаговая
форма `present = screen.is_visible(...); assert not present` AST-матчу
невидима — `operand` внутри `ast.UnaryOp(Not)` в этом случае `ast.Name`, не
`ast.Call`, и правило намеренно НЕ обобщает до datflow-анализа (пришлось бы
резолвить произвольное присваивание переменной — источник ложных
срабатываний). Закрытие — по evidence новых экземпляров этой формы, не
заранее (F-11 (в), CLAUDE.md).

Правило 4, ВТОРАЯ ФОРМА (живой пропуск TC-197, разбор 2026-08-20/25): та же
латентность presence-примитива, другой синтаксис — `wait_until(driver, lambda
d: <получатель>.<метод>(...) is None)` / `is False`. `wait_until` возвращается
на ПЕРВОМ True (`framework/core/waits.py:23-27`, `WebDriverWait(...).until`) —
опрос до первого «отсутствует» так же не доказывает удержания негатива весь
бюджет, как и одноразовое чтение `assert not X.method()`; правильная форма для
негативного Then — `assert_holds_for` (держит ВЕСЬ бюджет, падает на первом
нарушении, см. `framework/steps/browser_steps.py::assert_hidden_banner_absent`
— живой фикс TC-197 варианта D, критик-гейт 2026-08-20). Матчер — тот же
рекурсивный AST-обход `check_negative_then_settle`, узел — `ast.Call` с
`func` `wait_until`/`*.wait_until`, чей ПРЕДИКАТНЫЙ аргумент (позиционный №1
либо `condition=` — `_wait_until_predicate_arg`, критик-раунд round3,
замечание 1(б): раньше сканировались ВСЕ args/keywords, и лямбда в
`message=`/`timeout=` давала структурно ложную находку) — `ast.Lambda`,
В ТЕЛЕ которой (на ЛЮБОЙ глубине — `_iter_compare_nodes`, критик-раунд round2
Б2: голая проверка ВЕРХНЕГО узла `isinstance(arg.body, ast.Compare)` слепа к
`BoolOp` (`X.a() is None and X.b() is None` — живая идиома, 7 экземпляров в
framework/steps), обёртке `bool(...)` и немедленно вызванной вложенной лямбде
`(lambda e: P(e).x() is None)(d)`; фикс — DFS по всему поддереву `arg.body`)
находится `ast.Compare(ops=[ast.Is], ...)`, где ОДНА сторона — константа
`None`/`False` (идентичность, не `==`), другая — произвольное выражение
(предпочтительно вызов `<получатель>.<метод>()`, откуда берётся `method_name`
для ключа бейзлайна — сквозь `ast.NamedExpr`/walrus тоже: `(v := P(d).x())
is None` даёт `method_name="x"`, ТОТ ЖЕ ключ, что и без walrus, — устойчиво к
переименованию временной переменной, живая идиома, см. `browser_steps.py`
строки со `:=`; иначе — `ast.unparse` этой стороны, обрезанный). Первое
совпадение внутри лямбды по порядку DFS (форма 2 или форма 3, что раньше по
DFS) — находка; лямбда без совпадения (BoolOp целиком позитивный/нет
`is None`/`is False`/`not <presence-метод>()`) — не находка. DFS НЕ спускается
в comprehension/генератор (`_COMPREHENSION_NODES`, критик-раунд round3,
замечание 1(а)): ни условие включения, ни его элемент не являются телом
предиката — раньше `[x for x in P(d).items() if x is None]` давал находку с
`method_name='x'` (имя переменной цикла!).

Правило 4, ТРЕТЬЯ ФОРМА (Р3, критик-раунд round2, 2026-08-25 — round1
сознательно НЕ распознавал: «булева инверсия, не is None/False-идентичность,
замечена, не реализована»; критик-раунд round2 признал отказ неверным):
`wait_until(driver, lambda d: not <получатель>.<presence-метод>(...), ...)` —
булева инверсия presence-примитива внутри `wait_until`. Та же неоднозначность,
что форма 1 (может быть легитимным ПОЗИТИВНЫМ Then «дождаться обратного
появления» — живой образец `browser_steps.py::assert_blurb_visible`,
`not ListingPage(d).is_hidden(work_id)`, ждёт, пока блёрб СТАНЕТ видимым — ИЛИ
негативным Then без settle-hold), уже штатно поглощается тем же механизмом,
что форма 1 — записью в NEGATIVE_THEN_SETTLE_BASELINE с по-экземплярным
вердиктом (ключ — тот же `(rel, func_name, method_name)`, `method_name` —
`.attr` вызова под `not`, тот же предикат `NEGATIVE_THEN_METHOD_PATTERN`, что
форма 1). Матчер — тот же `_iter_negative_wait_candidates`/`_match_wait_
until_lambda`, узел — `ast.UnaryOp(op=ast.Not, operand=ast.Call(func=ast.
Attribute))` на любой глубине тела лямбды (та же DFS, что форма 2).

ИЗВЕСТНЫЙ ПРОБЕЛ (Р4, критик-раунд round2, признан и НЕ закрыт в этом ходе):
сравнение с sentinel-строкой, не идентичность-с-None/False — `wait_until(driver,
lambda d: <получатель>.<метод>(...) == "<sentinel>", ...)`, живой экземпляр
`framework/steps/browser_steps.py:2879` (`assert_copy_url_button_hidden`:
`wait_until(driver, lambda d: _copy_url_button_display(d) == "none", ...)`) —
тот же класс латентности (первое True роняет опрос), но форма `==` НЕ
реализована сознательно: риск ложных попаданий на легитимных позитивных
сравнениях (`== 0`, `== "complete"`) выше выгоды от закрытия одного известного
экземпляра. Смягчение здесь ЧАСТИЧНОЕ: `_copy_url_button_display` отличает
`"absent"` (элемент не в DOM) от `"none"` (display:none, элемент есть) — гонка
«элемент ещё не отрендерился» этим уже закрыта на уровне функции, открыта
только гонка «CSS ещё не применился». Закрытие правилом — по evidence новых
экземпляров той же `==`-формы, не заранее (F-11 (в), CLAUDE.md).

Правило 5 — PRIORITY-MARKER-CONSISTENCY (живой пропуск TC-257, критик-раунд
2026-08-2x — оба прежних гейта, arch_check и test-reviewer, прошли зелёными
при `priority: P1` кейса и марке́ре `@pytest.mark.p0` теста): ЧЕТВЁРТАЯ ветвь
обхода — framework/tests/**/test_*.py (тот же обход, что правила 1-2),
плюс frontmatter test-cases/**/*.md (`id:`/`priority:`, через общий загрузчик
`load_case_frontmatter()`, используемый и правилом 6). Для каждой тест-функции
с ОДНОВРЕМЕННО `@allure.id("TC-xxx")` и РОВНО ОДНИМ suite-маркером (`p<N>`) —
сверка `N` с числом из `priority: P<N>` кейса `TC-xxx` (если кейс найден и
`priority` разбирается). Отсутствие кейса/priority/неоднозначный маркер (0 или
>1 suite-маркеров у теста) — молчание (сверка невозможна либо уже покрыта
ERROR правила 2 — отсутствие маркера вовсе).

ЖИЗНЕННЫЙ СТАТУС КЕЙСА (критик-раунд round3, Б2): ERROR-правила 5 и 6-А
МОЛЧАТ по кейсам вне рабочих статусов — `Merged` (терминал, поля окаменели) и
`Draft` (поля ещё не ратифицированы); `Review`/`Approved`/`Automated`/`Blocked`
— рабочие, молчания нет. Полный разбор критерия и довод по каждому статусу —
комментарий к `_NON_WORKING_CASE_STATUSES`. До Б2 `load_case_frontmatter` не
читал `status` вовсе, и ERROR выводился из полей кейса, для теста не
авторитетных (живой корпус был в ОДНОМ редактировании от такого ERROR по
СЛИТОМУ кейсу — TC-034/035/036).

ЯРУС (решение Lead, критик-раунд round2, Р1, 2026-08-25): ERROR (свой канал
`rule5:` в тексте самого ERROR — не отдельный WARNS-канал). Изначально WARN —
единственное живое расхождение TC-039 (`framework/tests/test_downloads.py`
`test_restore_folds_orphan_scan_into_single_dialog`: маркер `p2` при
`priority: P3` кейса) починено маркером ДО промоции яруса (Р2, тем же ходом);
поверхностей ложных попаданий критик не нашёл ни одной. Ключ ALLOWLIST для
`rule_id="priority_marker"` — ТРЁХэлементный `(rel, rule, func_name)` (rel —
ОТ FRAMEWORK), НЕ двухэлементный `(rel, rule)` как у правил 1-2: связь
тест-файл -> находка у правила 5 1:N (несколько тест-функций одного файла) —
двухэлементный ключ гасил бы ВЕСЬ файл одной записью (декоративный ALLOWLIST,
критик-раунд round2, замечание).

Правило 6 — AUTOMATED-BY-ALLURE-ID-LINK (6 кейсов-сирот TC-207/208/211/213/
215/252, разбор вручную 2026-08-20 — заполненный `automated_by` кейса при
пустом/расходящемся `allure.id` резолвленного теста): ПЯТАЯ ветвь обхода,
обе стороны связки кейс<->тест, общий загрузчик `load_case_frontmatter()`.
Направление А (кейс -> тест, `check_automated_by_link_case_side`): у КАЖДОГО
кейса с непустым `automated_by` тест обязан резолвиться (см. `_resolve_test_
function`, как в правиле 3) И нести `@allure.id("<id_кейса>")` — иначе
находка «не разрешается» либо «несёт другой/пустой allure.id». Направление Б
(тест -> кейс, `check_automated_by_link_test_side`, «и наоборот» спеки): у
КАЖДОГО теста с `@allure.id("TC-xxx")`, ДЛЯ КОТОРОГО кейс TC-xxx существует в
корпусе, `automated_by` этого кейса обязан резолвиться РОВНО К ЭТОМУ тесту —
иначе WARN «automated_by кейса пуст» либо «указывает на другой тест». Тест без
кейса (allure.id кейса TC-xxx нет в корпусе) — вне скоупа, молчание (не
изобретаем требование «каждый allure.id обязан существовать в корпусе» — не
названо спекой).

Направление А молчит по кейсам вне рабочих статусов (`_NON_WORKING_CASE_
STATUSES`, критик-раунд round3 Б2 — та же ветвь, что у правила 5).
Направление Б статусом НЕ гасится: оно WARN, и его real-repo-пин держит ровно
СЛИТЫЕ TC-034/035/036 как детектор дрейфа — гашение стёрло бы детектор.

ФОРМА `automated_by` (критик-раунд round3, замечание 2): читается ТАК ЖЕ, как
механизмом-собратом `scripts/tests/test_automated_by_parity.py` — строгие
формы `<путь>::<функция>` и `<путь>::<Класс>::<метод>`, а при их неудаче
послабление по ПОСЛЕДНЕМУ сегменту (`_resolve_by_last_segment`): собрат берёт
`parts[-1]` и ищет по всему файлу, поэтому схемо-легальные
`x.py::Outer::Inner::method` и `x.py::НеТотКласс::func` он принимает, а
arch_check до починки давал по ним ERROR — два гейта по ОДНОМУ полю обязаны
читать его одинаково. Паритет держится и на границе: ДВА+ определения одного
имени — неоднозначность, послабление не применяется (у собрата это MISMATCH
класса shadowing).

ЯРУС по направлениям — РАЗНЫЙ (решение Lead, критик-раунд round2, Р1,
2026-08-25): направление А — ERROR (`rule_id="automated_by_orphan"`, свой
канал `rule6:` в тексте самого ERROR); живых находок на реальном репо — 0
(6 кейсов-сирот из спеки уже исправлены до этой задачи), поверхностей ложных
попаданий критик не нашёл. Направление Б остаётся WARN
(`rule_id="allure_id_orphan"`, канал `rule6:`, см. `test_real_repo_
automated_by_allure_id_link_test_side_baseline`) — из 9 живых находок 2
структурно ложные (split-паттерн: один `id:` кейса, несколько тест-функций с
тем же `@allure.id`, каноничен только `automated_by` — легитимный паттерн, не
дефект), правилом сегодня не выразимо; промоция в ERROR/фикс конкретных
находок — отдельное решение Lead по evidence, не этим правилом. Ключ ALLOWLIST
для `rule_id="automated_by_orphan"` (направление А) — двухэлементный
`(rel, rule)`, rel — case-файл ОТ КОРНЯ РЕПО: связь кейс -> находка у
направления А 1:1 (максимум одна находка на кейс, см.
`check_automated_by_link_case_side`), декоративный дефект правила 5 здесь
структурно невозможен, но сам ALLOWLIST-гейт починен на реально исключающий
(критик-раунд round2, замечание — раньше обе ветки клали находку в warns
независимо от попадания в ALLOWLIST).

НЕЧИТАЕМЫЙ ФАЙЛ (критик-раунд round3, Б1) — инвариант ВСЕХ четырёх точек
чтения файла по пути, пришедшему из данных (`_resolve_test_function`,
`load_case_frontmatter`, `_parse_framework_file`, `_read_case_text`): гейт
даёт НАХОДКУ, никогда трассировку. Схема допускает `automated_by` на КАТАЛОГ
(`^framework/tests/.+::.+$` матчит `framework/tests/canary::test_x`), а
`rglob`-обходы подхватывают каталоги с именами `*.md`/`test_*.py` — до
починки любой такой вход ронял `run()` PermissionError, и `run()` не
возвращал ни 0, ни 1, роняя ВЕСЬ канонический `python -m pytest scripts/tests`
через `test_real_repo_framework_passes`. Ярусы: файл framework/ — parse-ERROR
правил 1-2 (fail-closed), файл test-cases/ — WARN канала `cases:`.

Запуск:      python scripts/arch_check.py
Коды выхода: 0 — чисто (WARN/известные исключения допустимы), 1 — есть ERROR.
Только чтение framework/ + test-cases/ — файлы не изменяются, идемпотентен.
"""
from __future__ import annotations

import argparse
import ast
import configparser
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

REPO = Path(__file__).resolve().parents[1]
FRAMEWORK = REPO / "framework"
TESTS_DIR = FRAMEWORK / "tests"
STEPS_DIR = FRAMEWORK / "steps"
PYTEST_INI = FRAMEWORK / "pytest.ini"
CASES_DIR = REPO / "test-cases"
RECORDING_BUILDER = FRAMEWORK / "data/recording_builder.py"

# --- Правило 1: запрещённые импорты слоя tests/ (см. докстринг модуля) ---
FORBIDDEN_IMPORT_PREFIXES = (
    "framework.screens",
    "framework.web",
    "framework.core.driver_factory",
    "framework.core.waits",
    "appium.webdriver.common.appiumby",
    "appium.webdriver.common.mobileby",
    "selenium.webdriver.common.by",
    "selenium.webdriver.support.expected_conditions",
    "selenium.webdriver.support.ui",
)

# Методы-локаторы: низкоуровневые (driver.find_element(s)) и фабрики screens/base_screen.py.
FORBIDDEN_CALL_ATTRS = {"find_element", "find_elements", "by_text", "by_desc", "by_text_contains"}

LOCATOR_LITERAL_NEEDLE = "UiSelector("

# Известные исключения (test debt, см. докстринг). Ключ: (rel_posix_из_framework, rule_id).
# rule_id — фактические значения Finding.rule по правилам 1-2-3-5-6: "locators" |
# "allure_id" | "marker" | "parse" | "recording" | "priority_marker" |
# "automated_by_orphan" | "allure_id_orphan" (правило 4 в ALLOWLIST не участвует —
# у него свой механизм гашения, NEGATIVE_THEN_SETTLE_BASELINE, см. ниже;
# "case_frontmatter_read" — тоже НЕ участвует, гасить отказ чтения записью
# «известное исключение» заведомо неверная форма, см. `run`). Пусто —
# устраняй причину, не добавляй сюда.
#
# ОТЛИЧИЕ ключа для rule_id="recording"/"priority_marker"/"automated_by_orphan"/
# "allure_id_orphan" (правила 3/5/6):
# "recording"/"automated_by_orphan" — первый элемент кортежа ОТ КОРНЯ РЕПО (кейс
# test-cases/...), "priority_marker"/"allure_id_orphan" — ОТ FRAMEWORK (тест
# framework/tests/...), см. соответствующий `run_*` для точного места ключа.
#
# ОТЛИЧИЕ ключа для rule_id="recording" (правило 3, CASE-RECORDING-CONSISTENCY):
# первый элемент кортежа — путь ОТ КОРНЯ РЕПО (например "test-cases/tabs/TC-176.md"),
# НЕ от framework/, как у "locators"/"allure_id" выше (см. спека
# scratchpad/spec-case-recording-check.md v3, раздел ALLOWLIST) — правило 3 обходит
# test-cases/, а не framework/tests/.
#
# ОТЛИЧИЕ АРНОСТИ ключа для rule_id="priority_marker" (правило 5, критик-раунд
# round2, Р1): ТРИ элемента — (rel, rule, func_name), НЕ два, как у всех
# остальных rule_id выше. Связь тест-файл -> находка у правила 5 1:N
# (несколько тест-функций одного файла с расхождением приоритета) —
# двухэлементный ключ (rel, rule) гасил бы ВЕСЬ файл одной ALLOWLIST-записью
# (декоративный ALLOWLIST, найдено критик-раундом round2). Python допускает
# кортежи разной длины в одном `set`, аннотация типа ниже — best-effort
# документация, не enforced рантаймом.
#
# КРАЙ КЛЮЧА правила 5 (критик-раунд round3, замечание 4; живых экземпляров 0):
# `func_name` — ИМЯ, не квалифицированное имя, поэтому ДВЕ одноимённые
# тест-функции в одном файле (`def test_x` на модульном уровне и `test_x` в
# `Test*`-классе — обе собираются pytest'ом и обе видны `_test_functions`)
# гасятся ОДНОЙ ALLOWLIST-записью. Закрытие (переход на квалифицированное имя
# `_test_functions_with_qualname`) — по evidence первого живого экземпляра, не
# заранее (F-11 (в), CLAUDE.md).
ALLOWLIST: set[tuple[str, str] | tuple[str, str, str]] = {
    # AT-BUG-059 (Lead 2026-08-10): юнит-проба САМОГО BaseScreen (регресс-гвард
    # AT-BUG-048) — импорт screens по существу необходим для тестирования класса
    # screens-слоя; это НЕ обход layering продуктовым тестом (C1 писан против
    # tests->локаторы мимо steps). Перенос невозможен: сканер зеркалит
    # pytest testpaths (инвариант докстринга) — вне tests/ файл выпал бы из
    # штатного прогона.
    ("tests/test_swipe_to_text_settle_unit.py", "locators"),
    # AT-BUG-062 (test-maintainer rework attempt 2, критик-вход opus,
    # 2026-08-11): device-free юнит-проба verification-веток самого
    # `SettingsScreen.enter_rename_name`/`settings_steps.assert_filter_profile_listed`
    # (блокер «новые ветки отказа не исполнены ни разу» — импорт `SettingsScreen`
    # по существу необходим для тестирования конкретно ЭТОГО класса screens-слоя,
    # тот же случай, что AT-BUG-059/test_swipe_to_text_settle_unit.py выше;
    # перенос вне tests/ выпал бы из штатного прогона — тот же инвариант).
    ("tests/test_rename_name_verification_unit.py", "locators"),
    # AT-BUG-082 (test-maintainer rework attempt 2, критик-вход opus,
    # 2026-08-17): device-free юнит-проба `library_steps._poll_files_tab_absent`/
    # `assert_work_not_in_files_tab` мокает `LibraryScreen.has_work` НА УРОВНЕ
    # КЛАССА (не сам новый хелпер) — импорт `LibraryScreen` по существу
    # необходим для мока конкретно ЭТОГО класса screens-слоя, тот же случай,
    # что AT-BUG-059/AT-BUG-062 выше; перенос вне tests/ выпал бы из штатного
    # прогона (тот же инвариант — сканер зеркалит pytest testpaths).
    ("tests/test_library_files_tab_settle_unit.py", "locators"),
    # AT-BUG-083 (test-maintainer, 2026-08-19): прямой аналог записи выше —
    # device-free юнит-проба `library_steps._poll_tab_absent`/`assert_work_
    # not_in_tab` (обобщение `_poll_files_tab_absent` на произвольную
    # rating-вкладку) мокает `LibraryScreen.has_work` НА УРОВНЕ КЛАССА — тот
    # же case, тот же инвариант (сканер зеркалит pytest testpaths, перенос
    # вне tests/ выпал бы из штатного прогона).
    ("tests/test_library_tab_settle_unit.py", "locators"),
    # AT-BUG-085 (test-maintainer, 2026-08-20): прямой аналог двух записей
    # выше, ДРУГОЙ модуль/screens-класс — device-free юнит-проба
    # `rating_steps._poll_comment_collapsed`/`assert_comment_collapsed_
    # with_text` мокает `RatingOverlay.comment_expanded` НА УРОВНЕ КЛАССА —
    # тот же case, тот же инвариант (сканер зеркалит pytest testpaths,
    # перенос вне tests/ выпал бы из штатного прогона).
    ("tests/test_rating_comment_collapse_settle_unit.py", "locators"),
    # AT-BUG-090 (test-maintainer, 2026-08-20): прямой аналог записи выше,
    # ДРУГОЙ примитив ТОГО ЖЕ screens-класса — device-free юнит-проба
    # `rating_steps._poll_chip_absent`/`assert_chip_absent` мокает
    # `RatingOverlay.chip_visible` НА УРОВНЕ КЛАССА — тот же case, тот же
    # инвариант (сканер зеркалит pytest testpaths, перенос вне tests/ выпал
    # бы из штатного прогона).
    ("tests/test_rating_chip_absent_settle_unit.py", "locators"),
}

# Предикат имени вызываемого presence-метода (критик-вход D2-B1) — БЕЗ него голый
# `ast.Call(func=ast.Attribute)` матчит и непрезентные вызовы (`Path(...).exists()`,
# `.issubset()`, `.endswith()`), для которых WARN-текст правила 4 бессмыслен (10 ложных
# попаданий в framework/tests замерено критиком). Расширен спекового узкого набора
# (`.*_has_.*`, `.*_highlighted`) по факту двух истинных членов класса — см. докстринг
# модуля "Дельта 17 -> 19".
NEGATIVE_THEN_METHOD_PATTERN = re.compile(
    r"^(is_.*|has_.*|.*_has_.*|.*_visible|.*_present|.*_expanded|.*_highlighted)$"
)

# NEGATIVE_THEN_SETTLE_BASELINE — бейзлайн правила 4 (NEGATIVE-THEN-WITHOUT-SETTLE,
# см. докстринг модуля). Образец формы: scripts/dedup_check.py BASELINE (пара -> вердикт)
# и ALLOWLIST выше (тикет-источник обязателен в комментарии). В отличие от ALLOWLIST
# (гасит ERROR до WARN по (путь, rule_id) — правила 1-2), это правило ВСЕГДА WARN;
# словарь не гасит находку, а несёт ОБЯЗАТЕЛЬНЫЙ вердикт к КАЖДОМУ попаданию. Ключ —
# (rel_от_framework, func_name_объемлющей_функции, method_name) — НЕ lineno
# (критик-вход D2-F1: lineno дрейфует за рефакторингом, 7 из 19 строк сместились за
# ~20 коммитов истории steps/; func_name/method_name устойчивы к сдвигу строк,
# коллизий на живом репо нет — проверено критиком). lineno остаётся в тексте самого
# WARN для навигации (не участвует в ключе). Находка с ключом ВНЕ словаря — не
# ошибка (правило не падает), но печатается как «без вердикта — НОВАЯ находка» (см. `run`)
# и ломает test_real_repo_negative_then_settle_baseline (real-repo пин, детектор дрейфа
# множества/рецидива, образец test_arch_check.py:933 у правила 3).
#
# Список получен прямым прогоном правила (с предикатом) на этом репо: 19 попаданий
# ОБЕИХ форм — 18 формы 1 (`assert not X.method()`) + 1 формы 3 (`wait_until(...,
# lambda d: not X.method())`, `assert_blurb_visible` ниже); форма 2 на реальном
# репо сегодня даёт 0 находок, отдельных от формы 1. Замер после починки DFS
# (критик-раунд round3, замечание 1) — те же 19, множество ключей не изменилось.
#
# ЧИСЛА (критик-раунд round3, замечание 3 — прежняя редакция этого блока и
# докстринга модуля были рассогласованы): «17 -> 19» относилось к ФОРМЕ 1 и было
# старше ровно на один снятый экземпляр (AT-BUG-090 `assert_chip_absent`
# починен — форма 1 перестала матчиться, запись СНЯТА, см. первый комментарий
# словаря). Фактическая популяция формы 1: 16 (узкий предикат спеки) -> 18
# (предикат, расширенный `.*_has_.*`/`.*_highlighted` — browser_steps.py
# filter_dropdown_has_option, tag_link_highlighted, оба истинные члены класса
# дефекта, осознанная девиация, не случайность). Сам БЕЙЗЛАЙН при этом всегда
# был точен: 19 записей = 19 живых находок, 0 фантомов.
#
# КРАЙ КЛЮЧА (критик-раунд round3, замечание 5; живых экземпляров 0, чинить
# дорого — lineno в ключе отвергнут D2-F1 как дрейфующий): ДВА вложенных
# `wait_until` в ОДНОЙ функции с ОДНИМ и тем же `method_name` дают две находки
# с одним ключом `(rel, func_name, method_name)` — словарь схлопнет их в одну
# запись, а `test_real_repo_negative_then_settle_baseline` (сверка МНОЖЕСТВ)
# второй экземпляр не увидит. Тот же класс лоссовости, что Б1 round2 у пина
# по id; закрытие — по evidence, не заранее (F-11 (в), CLAUDE.md).
NEGATIVE_THEN_SETTLE_BASELINE: dict[tuple[str, str, str], str] = {
    # AT-BUG-090 (test-maintainer, 2026-08-20): экземпляр ПОЧИНЕН —
    # `assert_chip_absent` больше не делает `assert not chip_visible(...)`
    # напрямую (settle+hold через `_poll_chip_absent`, зеркало AT-BUG-085
    # `_poll_comment_collapsed`) — прежняя запись
    # `("steps/rating_steps.py", "assert_chip_absent", "chip_visible")`
    # СНЯТА: rule4 больше не матчит эту функцию (паттерн `assert not
    # X.method()` ушёл из AST), запись в бейзлайне стала бы фантомной.
    # Given TC-148: докстринг вызывающего кода явно называет это guard'ом
    # предусловия (is_visible/is_expanded), а не негативным Then-ассертом факта —
    # подтверждённое легитимное исключение из дефекта правила 4.
    ("steps/a11y_steps.py", "measure_bottom_bar_handle", "is_visible"): (
        "подтверждённый Given-guard (докстринг: явный guard is_visible, Given TC-148)"
    ),
    ("steps/a11y_steps.py", "measure_side_panel_collapsed_handle", "is_expanded"): (
        "подтверждённый Given-guard (докстринг: явный guard is_visible, Given TC-148)"
    ),
    # Остальные 16 — честный вердикт «не разобран» (НЕ «легитимный»): очередь Lead,
    # промоция в фикс/легитимация — по конкретному тикету на попадание, не этим ходом.
    ("steps/app_steps.py", "assert_bottom_nav_collapsed", "is_visible"): "не разобран, очередь Lead",
    ("steps/browser_steps.py", "assert_tab_strip_not_visible", "is_tab_strip_visible"): "не разобран, очередь Lead",
    # Р3 (критик-раунд round2, 2026-08-25): форма 3 (`wait_until(..., lambda d:
    # not <получатель>.<метод>())`) — единственная живая находка на реальном
    # репо. Подтверждено вердиктом Lead (спека Р3): легитимный ПОЗИТИВНЫЙ Then,
    # НЕ дефект — `wait_until` ждёт, пока `is_hidden(work_id)` станет False
    # (работа ПОЯВИТСЯ на листинге), а не читает presence-примитив один раз;
    # латентность-класса-4 (одноразовое чтение вместо ожидания settle) здесь
    # нет — это и есть settle-полл. См. `assert_blurb_hidden` рядом (тот же
    # приём в обратную сторону — `wait_until(..., lambda d: X.is_hidden())`,
    # форма 2, легитимный негативный Then, не матчится правилом по построению).
    ("steps/browser_steps.py", "assert_blurb_visible", "is_hidden"): (
        "легитимный позитивный Then (ждёт появления, а не исчезновения)"
    ),
    ("steps/browser_steps.py", "assert_note_button_absent", "has_note_button"): "не разобран, очередь Lead",
    ("steps/browser_steps.py", "assert_tag_button_absent", "has_tag_button"): "не разобран, очередь Lead",
    ("steps/browser_steps.py", "assert_tag_not_highlighted", "tag_link_highlighted"): "не разобран, очередь Lead",
    ("steps/browser_steps.py", "assert_filter_not_offered", "filter_dropdown_has_option"): "не разобран, очередь Lead",
    ("steps/browser_steps.py", "assert_tab_limit_dialog_not_shown", "tab_limit_dialog_visible"): "не разобран, очередь Lead",
    ("steps/browser_steps.py", "assert_opened_in_background_snackbar_not_shown", "opened_in_background_snackbar_visible"): "не разобран, очередь Lead",
    ("steps/browser_steps.py", "assert_tab_title_not_visible", "tab_title_visible"): "не разобран, очередь Lead",
    ("steps/library_steps.py", "assert_actions_overlay_closed", "delete_overlay_visible"): "не разобран, очередь Lead",
    ("steps/library_steps.py", "assert_download_icon_not_shown", "has_download_icon"): "не разобран, очередь Lead",
    ("steps/library_steps.py", "assert_open_icon_not_shown", "has_open_icon"): "не разобран, очередь Lead",
    ("steps/library_steps.py", "assert_sort_option_unavailable", "is_present"): "не разобран, очередь Lead",
    ("steps/settings_steps.py", "assert_clear_all_dialog_closed", "is_present"): "не разобран, очередь Lead",
    ("steps/settings_steps.py", "assert_filter_profile_not_listed", "has_filter_profile"): "не разобран, очередь Lead",
    ("steps/settings_steps.py", "assert_no_scan_complete_dialog", "is_present"): "не разобран, очередь Lead",
}


class Finding:
    __slots__ = ("rel", "rule", "message", "lineno", "func_name", "method_name")

    def __init__(self, rel: str, rule: str, message: str, lineno: int | None = None,
                 func_name: str | None = None, method_name: str | None = None):
        self.rel = rel
        self.rule = rule
        self.message = message
        self.lineno = lineno
        self.func_name = func_name
        self.method_name = method_name


def load_suite_markers(pytest_ini: Path = PYTEST_INI) -> set[str]:
    """Suite-маркеры (p0/p1/...) из framework/pytest.ini — динамически, а не хардкодом.

    live/replay/quarantine и т.п. — режим прогона, не suite, и в набор не входят.
    """
    if not pytest_ini.exists():
        return {"p0", "p1", "p2", "p3"}
    parser = configparser.ConfigParser()
    try:
        parser.read(pytest_ini, encoding="utf-8")
        raw = parser.get("pytest", "markers", fallback="")
    except configparser.Error:
        return {"p0", "p1", "p2", "p3"}
    markers = set()
    for line in raw.splitlines():
        name = line.strip().split(":", 1)[0].strip()
        if re.fullmatch(r"p\d+", name):
            markers.add(name)
    return markers or {"p0", "p1", "p2", "p3"}


def _decorator_dotted(dec: ast.expr) -> str:
    """`@allure.id(...)` -> "allure.id"; `@pytest.mark.p0` -> "pytest.mark.p0"."""
    node = dec
    if isinstance(node, ast.Call):
        node = node.func
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _allure_id_value(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    """Строковый аргумент `@allure.id("TC-xxx")`, если декоратор есть и аргумент —
    строковый литерал; `None` иначе (декоратора нет / аргумент не строка/отсутствует —
    правило 2 уже кладёт ERROR за отсутствие декоратора, здесь просто нет значения)."""
    for dec in fn.decorator_list:
        if isinstance(dec, ast.Call) and _decorator_dotted(dec) == "allure.id":
            if dec.args and isinstance(dec.args[0], ast.Constant) and isinstance(dec.args[0].value, str):
                return dec.args[0].value
    return None


def _test_functions_with_qualname(tree: ast.Module) -> list[tuple[str, ast.FunctionDef]]:
    """Как `_test_functions`, но с квалифицированным именем — `func_name` для
    тестов верхнего уровня, `ClassName::func_name` для методов `Test*`-классов
    (та же форма `::`, что `automated_by`, см. `_resolve_test_function` — нужна
    правилу 6 для сверки идентичности "этот тест" == "тест из automated_by")."""
    out: list[tuple[str, ast.FunctionDef]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            out.append((node.name, node))
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub.name.startswith("test_"):
                    out.append((f"{node.name}::{sub.name}", sub))
    return out


def _test_functions(tree: ast.Module) -> list[ast.FunctionDef]:
    """Тест-функции верхнего уровня (`def test_*`) и методы `Test*`-классов —
    то же, что подхватит pytest при python_functions=test_*/python_classes=Test*.
    """
    out: list[ast.FunctionDef] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            out.append(node)
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub.name.startswith("test_"):
                    out.append(sub)
    return out


def _is_docstring_expr(node: ast.stmt) -> bool:
    return isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)


def _iter_non_docstring_string_constants(tree: ast.Module):
    """ast.Constant(str) по всему модулю, исключая докстринги модуля/функций/классов
    (первый Expr(Constant(str)) в теле блока) — чтобы прозе в докстрингах не триггерить
    LOCATOR_LITERAL_NEEDLE.
    """
    docstring_ids = set()
    blocks = [tree] + [n for n in ast.walk(tree)
                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
    for block in blocks:
        body = getattr(block, "body", None)
        if body and _is_docstring_expr(body[0]):
            docstring_ids.add(id(body[0].value))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstring_ids:
            yield node


def check_locators(tree: ast.Module, rel: str) -> list[Finding]:
    findings: list[Finding] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if any(alias.name == p or alias.name.startswith(p + ".") for p in FORBIDDEN_IMPORT_PREFIXES):
                    findings.append(Finding(rel, "locators",
                        f"framework/{rel}:{node.lineno}: запрещённый импорт `{alias.name}` в tests/ "
                        f"(локаторы/driver — только в screens/web, см. docs/08 C1)"))
        elif isinstance(node, ast.ImportFrom) and node.module:
            if any(node.module == p or node.module.startswith(p + ".") for p in FORBIDDEN_IMPORT_PREFIXES):
                findings.append(Finding(rel, "locators",
                    f"framework/{rel}:{node.lineno}: запрещённый импорт `from {node.module} import ...` "
                    f"в tests/ (локаторы/driver — только в screens/web, см. docs/08 C1)"))
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in FORBIDDEN_CALL_ATTRS:
                findings.append(Finding(rel, "locators",
                    f"framework/{rel}:{node.lineno}: вызов `.{node.func.attr}(...)` — локатор/driver-примитив "
                    f"в tests/, должен быть скрыт за steps/screens (см. docs/08 C1)"))

    for node in _iter_non_docstring_string_constants(tree):
        if LOCATOR_LITERAL_NEEDLE in node.value:
            findings.append(Finding(rel, "locators",
                f"framework/{rel}:{node.lineno}: литеральная строка локатора "
                f"(`{LOCATOR_LITERAL_NEEDLE}...`) в tests/ (см. docs/08 C1)"))

    return findings


def check_allure_and_markers(tree: ast.Module, rel: str, suite_markers: set[str]) -> list[Finding]:
    findings: list[Finding] = []
    for fn in _test_functions(tree):
        dotted = [_decorator_dotted(d) for d in fn.decorator_list]
        if "allure.id" not in dotted:
            findings.append(Finding(rel, "allure_id",
                f"framework/{rel}:{fn.lineno}: тест `{fn.name}` без @allure.id(...) "
                f"— не привязан к тест-кейсу TC-xxx"))
        hit_markers = {d.rsplit(".", 1)[-1] for d in dotted if d.startswith("pytest.mark.")}
        if not (hit_markers & suite_markers):
            findings.append(Finding(rel, "marker",
                f"framework/{rel}:{fn.lineno}: тест `{fn.name}` без suite-маркера "
                f"({'/'.join(sorted(suite_markers))})"))
    return findings


def _parse_framework_file(path: Path) -> tuple[ast.Module | None, Finding | None]:
    """Общий парсер для файлов framework/ (используется правилами 1-2 и 4) —
    `rel` считается ОТ FRAMEWORK в обоих случаях. `(tree, None)` при успехе,
    `(None, Finding(rule="parse"))` при SyntaxError/UnicodeDecodeError/OSError.

    `OSError` (критик-раунд round3, Б1) — ТРЕТЬЯ точка чтения файла по пути,
    пришедшему из данных; путь берётся из `rglob`, а `rglob("test_*.py")`
    подхватывает и КАТАЛОГ с таким именем — `read_text` каталога роняет
    PermissionError (Windows, errno 13). Гейт обязан давать НАХОДКУ, а не
    трассировку: `run()` без обработки не возвращает ни 0, ни 1, и красит
    ВЕСЬ канонический `python -m pytest scripts/tests` через
    `test_real_repo_framework_passes`. Тот же приём — в
    `_resolve_test_function` и `_read_case_text` (одна поверхность)."""
    rel = path.relative_to(FRAMEWORK).as_posix()
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, UnicodeDecodeError, OSError) as exc:
        return None, Finding(rel, "parse", f"framework/{rel}: не удалось разобрать файл ({exc})")
    return tree, None


def check_file(path: Path) -> list[Finding]:
    tree, err = _parse_framework_file(path)
    if err is not None:
        return [err]
    rel = path.relative_to(FRAMEWORK).as_posix()
    findings = check_locators(tree, rel)
    findings += check_allure_and_markers(tree, rel, load_suite_markers())
    return findings


# --- Правило 4: NEGATIVE-THEN-WITHOUT-SETTLE (см. докстринг модуля). ТРЕТЬЯ
# ветвь обхода — framework/steps/*.py, отдельный WARNS-канал (см. `run`). ---


def _is_wait_until_call(node: ast.Call) -> bool:
    """`wait_until(...)` голым именем ИЛИ `<получатель>.wait_until(...)` —
    вторая форма (rule 4, докстринг модуля, "ВТОРАЯ ФОРМА")."""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "wait_until"
    if isinstance(func, ast.Attribute):
        return func.attr == "wait_until"
    return False


def _wait_until_predicate_arg(node: ast.Call) -> ast.expr | None:
    """ЕДИНСТВЕННЫЙ предикатный аргумент вызова `wait_until` — позиционный №1
    либо именованный `condition=` (сигнатура `def wait_until(driver, condition,
    timeout=None, message="")`, framework/core/waits.py:23). `None` — предикат
    не вычислим позиционно.

    Критик-раунд round3, замечание 1(б), решение Lead: до починки сканировались
    ВСЕ `args`/`keywords`, поэтому лямбда в НЕ-предикатном аргументе
    (`wait_until(d, EC.x(), message=lambda d: P(d).a() is None)`) давала
    находку — структурно неверно: предикат `wait_until` это ОДИН конкретный
    аргумент, а не «любая лямбда рядом». Живых экземпляров 0, но по новому
    тексту шага 3 /qa-loop каждый дал бы ложный пункт очереди.

    `*args` перед позицией предиката (`wait_until(*args, lambda d: ...)`) —
    `None`: позиция не вычислима, правило молчит вместо догадки по индексу."""
    for kw in node.keywords:
        if kw.arg == "condition":
            return kw.value
    if any(isinstance(a, ast.Starred) for a in node.args[:2]):
        return None
    if len(node.args) >= 2:
        return node.args[1]
    return None


def _is_none_or_false_constant(node: ast.expr) -> bool:
    """`is None`/`is False` — ИДЕНТИЧНОСТЬ с этими двумя константами, не `==`
    (`node.value is False` — не `== False`, чтобы `0`/`""` не считались)."""
    return isinstance(node, ast.Constant) and (node.value is None or node.value is False)


def _wait_until_identity_negative_other_side(node: ast.Compare) -> ast.expr | None:
    """Для `body` вида `X is None`/`X is False`/`None is X`/`False is X` (РОВНО один
    оператор `is`, РОВНО одна сторона — None/False-константа, другая — нет) —
    возвращает сторону-НЕ-константу (`X`). `None` — форма не подходит (оба
    операнда константы/оба не константы/не `is`/цепочка сравнений)."""
    if len(node.ops) != 1 or not isinstance(node.ops[0], ast.Is):
        return None
    left, right = node.left, node.comparators[0]
    left_const, right_const = _is_none_or_false_constant(left), _is_none_or_false_constant(right)
    if left_const and not right_const:
        return right
    if right_const and not left_const:
        return left
    return None


# Узлы-включения (comprehension/генератор) — DFS правила 4 в них НЕ спускается
# (критик-раунд round3, замечание 1(а), решение Lead «чинить, а не заявлять»).
# Структурный довод: ни условие включения (`... if x is None`), ни его элемент
# (`any(P(d).cell(i) is None for i in r)`) НЕ являются телом предиката — это
# внутренний шаг построения коллекции. До починки оба давали находку с
# бессмысленным `method_name` (`'x'` — имя переменной цикла; `'cell'` —
# аксессор ячейки), т.е. бессмысленный ключ NEGATIVE_THEN_SETTLE_BASELINE.
# Живых экземпляров ни того, ни другого класса на репо 0 — но по НОВОМУ тексту
# шага 3 /qa-loop каждый дал бы ложный пункт очереди («без вердикта — НОВАЯ
# находка»). ЦЕНА (признанный пробел, закрытие — по evidence, F-11 (в)):
# честный `wait_until(d, lambda d: all(P(d).is_x() is None for x in xs))` тоже
# останется невидимым правилу.
_COMPREHENSION_NODES = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


def _iter_negative_wait_candidates(node: ast.expr):
    """DFS preorder по ЛЮБОЙ глубине тела лямбды `wait_until` (критик-раунд
    round2, Б2/Р3) — возвращает узлы-кандидаты негативного Then по порядку:
    `ast.Compare` (форма 2 — идентичность с None/False) и `ast.UnaryOp`
    (форма 3 — булева инверсия `not <получатель>.<метод>()`, Р3). Спускается
    СКВОЗЬ `BoolOp` (`X.a() is None and X.b() is None` — живая идиома, 7
    экземпляров в framework/steps), `bool(...)`-обёртку и немедленно
    вызванную вложенную лямбду (`(lambda e: P(e).x() is None)(d)`) —
    `ast.iter_child_nodes` спускается в аргументы `Call`/операнды `BoolOp`
    одинаково. Голая проверка ВЕРХНЕГО узла (`isinstance(arg.body, ast.
    Compare)`, round1) слепа к этим формам — критик-раунд round2 замерил 3
    адверсариальных примера, пропущенных структурно. Различение типа узла и
    фильтр предиката/константы — у вызывающего кода (`_match_wait_until_
    lambda`).

    НЕ спускается в comprehension/генератор (`_COMPREHENSION_NODES`,
    критик-раунд round3, замечание 1(а)) — см. комментарий к константе."""
    if isinstance(node, _COMPREHENSION_NODES):
        return
    if isinstance(node, (ast.Compare, ast.UnaryOp)):
        yield node
    for child in ast.iter_child_nodes(node):
        yield from _iter_negative_wait_candidates(child)


def _wait_until_other_side_method_name(other: ast.expr) -> tuple[str, bool]:
    """`(method_name, is_call)` для не-константной стороны сравнения формы 2.
    Разворачивает `ast.NamedExpr` (walrus — критик-раунд round2, замечание:
    `(v := P(d).x()) is None` без разворота даёт ключ бейзлайна
    `"(v := P(d).x())"`, дрейфующий от переименования временной переменной;
    живая идиома, см. `:=` в `browser_steps.py`) ДО проверки на `Call` —
    `(v := P(d).x())` даёт `method_name="x"`, `is_call=True`, ТОТ ЖЕ ключ, что
    и без walrus. `is_call=False` — печатать `method_name` БЕЗ хвоста `(...)`
    (критик-раунд round2, замечание arch_check.py:618 старого кода: хвост
    подставлялся безусловно, печатая несуществующий вызов для не-Call сторон
    вида `P(d).attrname is None`)."""
    target = other.value if isinstance(other, ast.NamedExpr) else other
    if isinstance(target, ast.Call) and isinstance(target.func, ast.Attribute):
        return target.func.attr, True
    try:
        return ast.unparse(other), False
    except Exception:  # noqa: BLE001 — запасной вариант, не падаем
        return "<выражение>", False


def _match_wait_until_lambda(arg: ast.Lambda, rel: str, call_lineno: int, func_name: str) -> Finding | None:
    """Один `Finding` на лямбду `wait_until(..., lambda ...)` — первое (по DFS
    `_iter_negative_wait_candidates`) совпадение формы 2 (`ast.Compare`
    идентичности с None/False) либо формы 3 (`ast.UnaryOp(Not)` над вызовом
    presence-метода — Р3, критик-раунд round2, тот же предикат имени метода
    `NEGATIVE_THEN_METHOD_PATTERN`, что форма 1); `None`, если совпадений нет."""
    for candidate in _iter_negative_wait_candidates(arg.body):
        if isinstance(candidate, ast.Compare):
            other = _wait_until_identity_negative_other_side(candidate)
            if other is None:
                continue
            const_repr = "None" if any(
                _is_none_or_false_constant(s) and s.value is None
                for s in (candidate.left, candidate.comparators[0])
            ) else "False"
            method_name, is_call = _wait_until_other_side_method_name(other)
            call_suffix = "(...)" if is_call else ""
            return Finding(
                rel, "negative_then_settle",
                f"framework/{rel}:{call_lineno}: `wait_until(..., lambda ...: "
                f"{method_name}{call_suffix} is {const_repr})` — возвращается на ПЕРВОМ чтении, "
                f"когда предикат стал {const_repr} — исчезновения весь бюджет не дожидается; "
                f"для негативного Then нужен assert_holds_for (framework/core/waits.py), "
                f"не одноразовый wait_until (см. TC-197 assert_hidden_banner_absent)",
                lineno=call_lineno, func_name=func_name, method_name=method_name,
            )
        if isinstance(candidate, ast.UnaryOp) and isinstance(candidate.op, ast.Not):
            operand = candidate.operand
            if not (isinstance(operand, ast.Call) and isinstance(operand.func, ast.Attribute)):
                continue
            attr = operand.func.attr
            if not NEGATIVE_THEN_METHOD_PATTERN.match(attr):
                continue
            return Finding(
                rel, "negative_then_settle",
                f"framework/{rel}:{call_lineno}: `wait_until(..., lambda ...: "
                f"not <получатель>.{attr}(...))` — булева инверсия presence-примитива "
                f"внутри wait_until; неоднозначно (позитивный Then \"дождаться "
                f"обратного появления\" ИЛИ негативный Then без settle-hold, форма 3, "
                f"Р3 критик-раунда round2) — каждое попадание несёт вердикт в "
                f"NEGATIVE_THEN_SETTLE_BASELINE, как форма 1 (`assert not X.method()`)",
                lineno=call_lineno, func_name=func_name, method_name=attr,
            )
    return None


def check_negative_then_settle(tree: ast.Module, rel: str) -> list[Finding]:
    """AST-матч `assert not <получатель>.<presence-метод>(...)` (форма 1, см.
    докстринг модуля для точной формы, предиката имени метода и обоснования
    AST vs регекс). Получатель — ЛЮБОЕ выражение (Name/Attribute-цепочка/вызов
    конструктора) — receiver-цепочки вида `Screen(driver).method().other()`
    матчатся тем же узлом, что и голое `screen.method()`, потому что матч идёт
    по `operand.func`, не по `operand.func.value`. `func_name` каждой находки —
    имя БЛИЖАЙШЕЙ объемлющей функции/метода (ключ NEGATIVE_THEN_SETTLE_
    BASELINE, критик-вход D2-F1); ходим рекурсивным спуском (не плоским
    `ast.walk`), чтобы отслеживать смену области видимости при входе во
    вложенные `def`, без двойного счёта.

    ФОРМЫ 2 и 3 (докстринг модуля) — `wait_until(driver, lambda d: ...)`,
    обе делегируют в `_match_wait_until_lambda`/`_iter_negative_wait_
    candidates` (DFS по ЛЮБОЙ глубине тела лямбды — критик-раунд round2, Б2).
    """
    findings: list[Finding] = []

    def visit(node: ast.AST, func_name: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                visit(child, child.name)
                continue
            if (isinstance(child, ast.Assert)
                    and isinstance(child.test, ast.UnaryOp)
                    and isinstance(child.test.op, ast.Not)
                    and isinstance(child.test.operand, ast.Call)
                    and isinstance(child.test.operand.func, ast.Attribute)):
                attr = child.test.operand.func.attr
                if NEGATIVE_THEN_METHOD_PATTERN.match(attr):
                    findings.append(Finding(
                        rel, "negative_then_settle",
                        f"framework/{rel}:{child.lineno}: `assert not <получатель>.{attr}(...)` — "
                        f"presence-примитив возвращается немедленно, пока элемент ещё присутствует "
                        f"— исчезновения не дожидается; для негативного Then нужен "
                        f"wait_absent/settle-hold-полл (base_screen.wait_absent:85)",
                        lineno=child.lineno, func_name=func_name, method_name=attr,
                    ))
            if isinstance(child, ast.Call) and _is_wait_until_call(child):
                # ТОЛЬКО предикатный аргумент (критик-раунд round3, замечание
                # 1(б)) — не все args/keywords; см. `_wait_until_predicate_arg`.
                # Один wait_until -> максимум одна находка по построению.
                predicate = _wait_until_predicate_arg(child)
                if isinstance(predicate, ast.Lambda):
                    finding = _match_wait_until_lambda(predicate, rel, child.lineno, func_name)
                    if finding is not None:
                        findings.append(finding)
            visit(child, func_name)

    visit(tree, "<module>")
    return findings


def run_negative_then_settle_rule() -> list[Finding]:
    """Правило 4 по framework/steps/*.py (см. докстринг блока выше). Всегда WARNS
    (см. `run`). Нечитаемый файл (SyntaxError/UnicodeDecodeError) НЕ падает (Ф1) —
    но и НЕ пропускается молча (критик-вход D2-F2): правила 1-2 обходят только
    TESTS_DIR (framework/tests/), их "parse"-ERROR framework/steps/ не касается —
    тихий пропуск здесь оставил бы файл БЕЗ единой находки ЛЮБОГО правила модуля.
    Кладём собственную WARN-находку `rule="negative_then_settle_parse"` вместо
    обычной "negative_then_settle" (её никто не сверяет с NEGATIVE_THEN_SETTLE_
    BASELINE — это не попадание правила, а отчёт о неприменимости)."""
    if not STEPS_DIR.exists():
        return []
    findings: list[Finding] = []
    for path in sorted(STEPS_DIR.glob("*.py")):
        tree, err = _parse_framework_file(path)
        if err is not None:
            findings.append(Finding(
                err.rel, "negative_then_settle_parse",
                f"framework/{err.rel}: steps-файл не разобран — правило 4 по нему "
                f"не применялось (см. {err.message})",
            ))
            continue
        rel = path.relative_to(FRAMEWORK).as_posix()
        findings.extend(check_negative_then_settle(tree, rel))
    return findings


# --- Правило 3: CASE-RECORDING-CONSISTENCY (см. докстринг модуля + спека
# scratchpad/spec-case-recording-check.md v3). Обход test-cases/, отдельный
# WARNS-канал (см. `run`). ---

_AUTOMATED_BY_RE = re.compile(r'^automated_by:\s*"?(.*?)"?\s*$', re.M)
_MITM_TOKEN_RE = re.compile(r"[\w.-]+\.mitm")
_RB_CONST_TOKEN_RE = re.compile(r"\brb\.([A-Za-z_][A-Za-z0-9_]*)\b")
_BARE_CONST_TOKEN_RE = re.compile(r"\b([A-Z][A-Z0-9_]*_FILENAME)\b")
_SECTION_PREFIXES = ("## Предусловия", "## Сценарий")

# Возвращается `_resolve_test_function`, когда файл automated_by существует, но
# не разбирается (SyntaxError/UnicodeDecodeError) — правило 3 в этом случае молчит:
# ошибку парсинга уже несёт существующий Finding класса "parse" правил 1-2 (тот же
# framework/tests/**/test_*.py обходится обоими правилами) — не дублируем.
#
# ОСТАТОЧНАЯ ДЫРА (Ф1, критик-вход attempt 2, признана и НЕ закрыта в этом ходе):
# если automated_by указывает НА ФАЙЛ ВНЕ глоба test_*.py, который обходят правила
# 1-2 (`TESTS_DIR.rglob("test_*.py")` — например `framework/tests/conftest.py::x`,
# схема test-case.schema.yaml такую форму automated_by не запрещает), то при
# SyntaxError ЭТОГО файла ни правило 1-2 (файл не в их обходе), ни правило 3 (эта
# ветка, молчит намеренно) находки не дадут — молчаливый провал без ERROR/WARN. В
# корпусе такой automated_by не встречается (единственная живая форма — путь на
# test_*.py, см. докстринг модуля/спеку); закрытие — по evidence, не заранее
# (F-11 (в), CLAUDE.md).
_PARSE_ERROR = object()


def _module_string_consts(tree: ast.Module) -> dict[str, str]:
    """Модульные присваивания вида `NAME = "литерал"` — тот же приём для
    framework/data/recording_builder.py и для самого тест-файла (голый `<CONST>`
    резолвится по константам файла, где записан тест — см. спеку)."""
    out: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    out[target.id] = node.value.value
    return out


def _load_recording_builder_consts() -> dict[str, str]:
    """Константы `framework/data/recording_builder.py` для правила 3.

    ПЯТАЯ точка чтения файла по пути (критик-раунд round3 attempt 2, Б1;
    прошлый ход обошёл класс не до конца — были починены четыре, эта осталась
    с прежней идиомой `exists()` + перехват без `OSError`). Каталог с именем
    `recording_builder.py` роняет здесь PermissionError РАНЬШЕ всех правил:
    `run()` -> `run_recording_rule()` -> сюда, то есть до первой находки
    правила 3. `is_file()` + `OSError` — та же охрана, что у
    `_resolve_test_function` / `_parse_framework_file` / `_read_case_text`.
    Отсутствие/нечитаемость констант — пустой словарь, а не находка: правило 3
    без `rb.`-констант деградирует штатно (голые `rb.X` просто не резолвятся и
    попадают в `unresolved` конкретного кейса).

    `load_suite_markers` (шестая кандидатура того же класса) НЕ трогается —
    `configparser.read` глотает OSError сам, проверено позитивным прогоном
    критика."""
    if not RECORDING_BUILDER.is_file():
        return {}
    try:
        tree = ast.parse(RECORDING_BUILDER.read_text(encoding="utf-8"), filename=str(RECORDING_BUILDER))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return {}
    return _module_string_consts(tree)


def _scoped_lines(text: str) -> list[tuple[int, str]]:
    """Строки секций `## Предусловия`/`## Сценарий` (префиксное совпадение
    заголовка — суффиксы вроде `## Предусловия — БЛОКЕР (…)` тоже считаются).
    Секция обрывается СЛЕДУЮЩИМ заголовком `## ` (ровно 2 `#`); `### `-подсекции
    (3+ `#`) заголовком верхнего уровня не являются и секцию не обрывают."""
    out: list[tuple[int, str]] = []
    keep = False
    for lineno, line in enumerate(text.splitlines(), start=1):
        if line.startswith("## "):
            keep = line.startswith(_SECTION_PREFIXES)
            continue
        if keep:
            out.append((lineno, line))
    return out


def _case_mentions(text: str, rb_consts: dict[str, str]) -> tuple[set[str], int | None]:
    """`mentions` кейса + номер строки ПЕРВОГО упоминания (любого вида), только
    из секций Предусловий/Сценария (нарратив прочих секций не сверяется)."""
    mentions: set[str] = set()
    first_line: int | None = None
    for lineno, line in _scoped_lines(text):
        hit = False
        for tok in _MITM_TOKEN_RE.findall(line):
            norm = tok.lstrip(".-")
            if len(norm) > len(".mitm"):  # пустое/голое имя (напр. голый `.mitm`) отбрасывается
                mentions.add(norm)
                hit = True
        for name in _RB_CONST_TOKEN_RE.findall(line):
            if name in rb_consts:
                mentions.add(rb_consts[name])
                hit = True
        for name in _BARE_CONST_TOKEN_RE.findall(line):
            if name in rb_consts:
                mentions.add(rb_consts[name])
                hit = True
        if hit and first_line is None:
            first_line = lineno
    return mentions, first_line


def _split_automated_by(automated_by: str) -> tuple[str, list[str]] | None:
    """`<путь>::<функция>` (единственная живая форма) и `<путь>::Class::method`/
    `...[param]`-суффикс (на вырост, спекуляция — см. спеку). Число сегментов
    имени НЕ ограничено: вложенные формы разрешает `_resolve_test_function`
    последним сегментом (критик-раунд round3, замечание 2)."""
    without_param = automated_by.split("[", 1)[0]
    parts = without_param.split("::")
    if len(parts) < 2 or not parts[0] or not all(parts[1:]):
        return None
    return parts[0], parts[1:]


def _resolve_by_last_segment(tree: ast.Module, func_name: str):
    """Послабление формы `automated_by` до трактовки МЕХАНИЗМА-СОБРАТА
    (`scripts/tests/test_automated_by_parity.py::resolve_automated_by` —
    берёт `parts[-1]` и ищет `def <func>` по ВСЕМУ файлу, независимо от
    промежуточных сегментов): единственное определение `func_name` НА ЛЮБОЙ
    ГЛУБИНЕ дерева. Решение Lead (критик-раунд round3, замечание 2): два гейта
    по ОДНОМУ полю обязаны читать его одинаково — иначе схемо-легальная и
    собратом принимаемая форма (`x.py::Outer::Inner::method`, `x.py::
    НеТотКласс::func`) даёт ERROR только у одного из них.

    ДВА+ определения одного имени — `None` (неоднозначно), паритет с
    shadowing-веткой собрата (там это MISMATCH, не тихий OK: в Python
    побеждает ПОСЛЕДНЕЕ определение, и какое именно исполняется — из
    `automated_by` не видно)."""
    matches = [node for node in ast.walk(tree)
               if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name]
    if len(matches) != 1:
        return None
    return matches[0], tree


def _resolve_test_function(rel_path: str, name_parts: list[str]):
    """`(fn, tree)` тест-функции; `None` — automated_by не разрешается;
    `_PARSE_ERROR` — файл есть, но не разбирается (см. докстринг `_PARSE_ERROR`).

    `is_file()`, НЕ `exists()` (критик-раунд round3, Б1): схема допускает
    `automated_by` на КАТАЛОГ (`schemas/test-case.schema.yaml:26`, pattern
    `^$|^framework/tests/.+::.+$` матчит `framework/tests/canary::test_x`) —
    `exists()` каталог проходит, а `read_text` роняет PermissionError.
    Поверхность расширил именно правило 6-А: правило 3 доходило сюда только
    для кейсов с непустыми `mentions`, 6-А резолвит КАЖДЫЙ кейс с непустым
    `automated_by` (151 Automated + прочие). Механизм-собрат ту же поверхность
    держит правильно (`test_automated_by_parity.py:92` — `is_file()`, чистый
    MISMATCH вместо падения). `OSError` в перехвате — остаток той же
    поверхности: файл ЕСТЬ, но не читается (права, блокировка, IO) —
    `_PARSE_ERROR`, как и нечитаемая кодировка.

    Порядок резолюции: строгая форма (модульная функция / метод
    Class::method верхнего уровня), затем послабление
    `_resolve_by_last_segment` (паритет с собратом, замечание 2). Строгая ветка
    `<путь>::<функция>` СЧИТАЕТ совпадения верхнего уровня и при 2+ отдаёт
    резолюцию послаблению (то есть `None`) — иначе паритет по shadowing не
    держался бы в самой частой форме (критик-раунд round3 attempt 2, Б3).

    ОСТАТОК КЛАССА (доложен, НЕ починен по границе scope этого хода): ветка
    `<путь>::<Класс>::<метод>` ниже всё ещё возвращает ПЕРВОЕ совпадение —
    два одноимённых `Test*`-класса верхнего уровня либо два одноимённых метода
    в одном классе дадут ту же асимметрию с собратом. Живых экземпляров 0."""
    fpath = REPO / rel_path
    if not fpath.is_file():
        return None
    try:
        tree = ast.parse(fpath.read_text(encoding="utf-8"), filename=str(fpath))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return _PARSE_ERROR

    if len(name_parts) == 1:
        # СЧЁТ, не «первое совпадение» (критик-раунд round3 attempt 2, Б3):
        # прежний `return` на первом же `def` доходил до стража «2+ -> None»
        # только когда строгая ветка промахивалась, т.е. паритет с собратом по
        # shadowing НЕ держался в самой частой форме `<путь>::<функция>`.
        # Хуже молчания: arch_check валидировал `allure.id` ПЕРВОГО
        # определения, тогда как Python исполняет ПОСЛЕДНЕЕ — неверный ответ на
        # вопрос «какой тест стоит за этим automated_by». Ноль совпадений —
        # проваливаемся в послабление; два+ — тоже (там тот же вердикт `None`).
        (func_name,) = name_parts
        top_level = [node for node in tree.body
                     if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name]
        if len(top_level) == 1:
            return top_level[0], tree
    elif len(name_parts) == 2:
        class_name, func_name = name_parts
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub.name == func_name:
                        return sub, tree
    return _resolve_by_last_segment(tree, name_parts[-1])


def _resolve_param_value(node: ast.expr, module_consts: dict[str, str], rb_consts: dict[str, str]) -> tuple[str | None, str | None]:
    """`(значение, None)` при успехе, `(None, причина)` при неразрешимом узле —
    НИКОГДА не бросает исключение (Ф1: произвольный узел -> находка, не падение)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value, None
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "rb":
        if node.attr in rb_consts:
            return rb_consts[node.attr], None
        return None, f"rb.{node.attr} не резолвится по recording_builder.py"
    if isinstance(node, ast.Name):
        if node.id in module_consts:
            return module_consts[node.id], None
        return None, f"{node.id} не резолвится по модульным константам тест-файла"
    return None, "неразрешимый узел параметризации"


def _collect_recordings(fn, module_consts: dict[str, str], rb_consts: dict[str, str]) -> tuple[set[str], list[str]]:
    """Объединение значений replay из ВСЕХ `@pytest.mark.parametrize`, чей
    argnames содержит `replay` (позиционный резолв мульти-argnames и
    `pytest.param`, `indirect=` на резолв не влияет — см. спеку)."""
    recordings: set[str] = set()
    unresolved: list[str] = []
    for dec in fn.decorator_list:
        if not isinstance(dec, ast.Call) or _decorator_dotted(dec) != "pytest.mark.parametrize":
            continue
        if not dec.args:
            # Ф5 (fail-closed, критик-вход attempt 2, Lead: kwargs не резолвим —
            # формы `parametrize(argnames=..., argvalues=...)` в корпусе нет):
            # позиционных args нет, argnames переданы именованно — не знаем, содержит
            # ли он "replay", молчаливый пропуск был бы дырой, кладём находку.
            unresolved.append("parametrize вызван с именованными аргументами (argnames=/argvalues=) — не резолвится")
            continue
        argnames_node = dec.args[0]
        names: list[str] | None = None
        if isinstance(argnames_node, ast.Constant) and isinstance(argnames_node.value, str):
            names = [n.strip() for n in argnames_node.value.split(",")]
        elif isinstance(argnames_node, (ast.List, ast.Tuple)):
            collected: list[str] = []
            for el in argnames_node.elts:
                if isinstance(el, ast.Constant) and isinstance(el.value, str):
                    collected.append(el.value.strip())
                else:
                    collected = []
                    break
            names = collected or None
        if not names or "replay" not in names:
            continue
        idx = names.index("replay")
        if len(dec.args) < 2 or not isinstance(dec.args[1], (ast.List, ast.Tuple)):
            unresolved.append("значения parametrize не литерал списка/кортежа")
            continue
        for row in dec.args[1].elts:
            if isinstance(row, ast.Call) and _decorator_dotted(row) == "pytest.param":
                if idx >= len(row.args):
                    unresolved.append("pytest.param без позиционного аргумента replay")
                    continue
                value_node = row.args[idx]
            elif len(names) == 1:
                value_node = row
            elif isinstance(row, (ast.Tuple, ast.List)):
                if idx >= len(row.elts):
                    unresolved.append("индекс replay вне диапазона строки параметризации")
                    continue
                value_node = row.elts[idx]
            else:
                unresolved.append("строка параметризации не кортеж/список/pytest.param")
                continue
            value, err = _resolve_param_value(value_node, module_consts, rb_consts)
            if err:
                unresolved.append(err)
            else:
                recordings.add(value)
    return recordings, unresolved


def _read_case_text(path: Path) -> str | None:
    """ЕДИНСТВЕННАЯ точка чтения файла test-cases/ (правила 3/5/6) — текст либо
    `None`, если файл нечитаем: каталог с именем `*.md` (его подхватывает
    `CASES_DIR.rglob("*.md")`, а `read_text` роняет PermissionError), отказ
    прав, битая кодировка. Критик-раунд round3, Б1 + обход класса по правилу 9
    CLAUDE.md: критик назвал ТРИ незащищённые точки чтения
    (`_resolve_test_function`, `load_case_frontmatter`, `_parse_framework_file`)
    — `_process_case` был ЧЕТВЁРТОЙ (тот же `path.read_text` без охраны, тот же
    обход `CASES_DIR.rglob`), поэтому обе точки по test-cases/ сведены сюда.

    BOM-толерантно (`utf-8-sig`, критик-раунд round2, замечание). `None` НЕ
    означает молчание гейта: доклад о нечитаемом файле кейса кладёт общий
    загрузчик `load_case_frontmatter` (канал `cases:`, один доклад на файл —
    оба обхода идут по одному и тому же `CASES_DIR.rglob("*.md")`)."""
    try:
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return None


def _process_case(path: Path, rb_consts: dict[str, str]) -> Finding | None:
    """Один вердикт на кейс (ветви — см. спеку, порядок явный): нечитаемый файл
    -> молчание (доклад за `load_case_frontmatter`, см. `_read_case_text`);
    mentions=∅ -> молчание ВСЕГДА (веха 1, до любых прочих проверок); иначе
    automated_by не разрешается / неразрешимая параметризация /
    recordings⊄mentions (лишние записи) / mentions без recordings без live
    (кейс называет, тест не берёт) / чисто."""
    rel = path.relative_to(REPO).as_posix()
    text = _read_case_text(path)
    if text is None:
        return None
    m = _AUTOMATED_BY_RE.search(text)
    automated_by = m.group(1).strip() if m else ""
    if not automated_by:
        return None
    ab_line = text[: m.start()].count("\n") + 1

    mentions, mention_line = _case_mentions(text, rb_consts)
    if not mentions:
        return None  # ветвь 1: правило молчит всегда

    split = _split_automated_by(automated_by)
    resolved = _resolve_test_function(*split) if split else None
    if split is None or resolved is None:
        return Finding(rel, "recording",
            f"{rel}:{ab_line}: automated_by `{automated_by}` не разрешается — "
            f"сверка невозможна (кейс называет {sorted(mentions)})")
    if resolved is _PARSE_ERROR:
        return None  # существующий Finding класса parse правил 1-2 уже покрывает файл

    fn, tree = resolved
    module_consts = _module_string_consts(tree)
    recordings, unresolved = _collect_recordings(fn, module_consts, rb_consts)
    func_label = automated_by.split("[", 1)[0]

    if unresolved:
        return Finding(rel, "recording",
            f"{rel}:{ab_line}: неразрешимая параметризация replay в `{func_label}` "
            f"({'; '.join(unresolved)}) — кейс называет {sorted(mentions)}")

    if recordings and not recordings <= mentions:
        return Finding(rel, "recording",
            f"{rel}:{ab_line}: тест `{func_label}` берёт записи {sorted(recordings)}, "
            f"кейс их не называет (кейс называет {sorted(mentions)})")

    is_live = any(_decorator_dotted(d) == "pytest.mark.live" for d in fn.decorator_list)
    if not recordings and not is_live:
        line = mention_line if mention_line is not None else ab_line
        return Finding(rel, "recording",
            f"{rel}:{line}: кейс называет replay-записи {sorted(mentions)}, "
            f"тест `{func_label}` replay не берёт")

    return None  # ветвь 4: чисто (в т.ч. надмножество mentions)


def run_recording_rule() -> list[Finding]:
    """Правило 3 по test-cases/ (см. докстринг блока выше). Всегда WARNS —
    вызывающая сторона (`run`) не кладёт находки в errors."""
    if not CASES_DIR.exists():
        return []
    rb_consts = _load_recording_builder_consts()
    findings: list[Finding] = []
    for path in sorted(CASES_DIR.rglob("*.md")):
        finding = _process_case(path, rb_consts)
        if finding is not None:
            findings.append(finding)
    return findings


# --- Общий загрузчик frontmatter test-cases/ для правил 5 и 6 (см. докстринг
# модуля) — id/priority/automated_by ОДНИМ проходом по CASES_DIR, вместо
# двух отдельных обходов. ---

_CASE_ID_RE = re.compile(r'^id:\s*"?(.*?)"?\s*$', re.M)
_CASE_PRIORITY_RE = re.compile(r'^priority:\s*"?(.*?)"?\s*$', re.M)
_CASE_STATUS_RE = re.compile(r'^status:\s*"?(.*?)"?\s*$', re.M)

# Служебные файлы test-cases/ без frontmatter — тот же приём, что _SKIP_NAMES в
# scripts/tests/test_automated_by_parity.py (критик-раунд round2, замечание).
_CASE_FRONTMATTER_SKIP_NAMES = {"README.MD", "PERTURBATIONS.MD"}

# Статусы кейса (schemas/test-case.schema.yaml:8, enum [Draft, Review, Approved,
# Automated, Blocked, Merged]), по которым ERROR-правила 5 и 6-А МОЛЧАТ
# (критик-раунд round3, Б2). Критерий один: frontmatter кейса не является
# АВТОРИТЕТНЫМ источником требования к связанному тесту.
#   - `Merged` — ТЕРМИНАЛ (schemas/transitions.yaml:124), кейс поглощён
#     `merged_into`; его `priority`/`automated_by` — окаменелость (авторитетен
#     кейс-поглотитель, прецедент TC-257). Живой корпус в ОДНОМ редактировании
#     от ложного ERROR: 10 кейсов Merged, три из них (TC-034/035/036) несут
#     живые тесты, совпадение P1<->p1 там СЕГОДНЯ случайно, а сами тесты стоят
#     в очереди на удаление (docs/tasks/p1-e2e-dedup.md, шаг Р4 п.2) — шаг
#     «пометить p3, покрыто journey» уронил бы канонический набор ERROR'ом,
#     названным по СЛИТОМУ кейсу.
#   - `Draft` — начальный статус «спорные требования»
#     (schemas/transitions.yaml:119); поля ЕЩЁ не ратифицированы (Draft ->
#     Approved только `by: [human]`), выводить из них ERROR = краснеть на
#     значениях, которых никто не утверждал. Зеркало довода про Merged на
#     до-ратификационную сторону.
# НЕ молчим по `Blocked` (решение исполнителя, критик-раунд round3): Blocked —
# состояние ЭСКАЛАЦИИ, входимое из `"*"` фабрикой (transitions.yaml:164), оно
# описывает остановку РАБОТЫ, а не недействительность полей; кейс уже
# ратифицирован и вернётся к тем же полям. Молчание по Blocked открыло бы дыру
# «пометь кейс Blocked — и расхождение маркера/связки исчезнет из гейта».
# `Review`/`Approved`/`Automated` — рабочие по прямому требованию спеки.
# Кейс БЕЗ `status:` (или с пустым) — трактуется как рабочий (fail-closed).
_NON_WORKING_CASE_STATUSES = frozenset({"Merged", "Draft"})


def load_case_frontmatter() -> tuple[dict[str, dict], list[Finding]]:
    """`id кейса -> {"rel", "automated_by", "ab_line", "priority", "status"}` из frontmatter
    test-cases/**/*.md (regex по всему тексту, тот же приём, что `_AUTOMATED_BY_RE`
    у правила 3 — frontmatter-поля вида "заголовок: значение" в теле кейсов
    практически не повторяются). Файл без `id:` — пропускается (не наш случай,
    правило 5/6 не может сверить кейс без id). Дублирующийся `id:` в корпусе —
    не наш случай (кейсы уникальны по конструкции репозитория), но НЕ падаем:
    последний по сортированному обходу побеждает (детерминированно).
    Служебные `README.MD`/`PERTURBATIONS.MD` (без frontmatter) — пропускаются
    по имени (регистронезависимо), тот же приём, что `_SKIP_NAMES` в
    `scripts/tests/test_automated_by_parity.py` (критик-раунд round2,
    замечание — конвенция была рассинхронизирована с сиблингом; живого вреда
    не было: единственный такой файл и без фильтра отсеивался сам, у него нет
    `id:`). BOM в начале файла — не роняет `^id:`/`^priority:` (`re.M`,
    `encoding="utf-8-sig"` — критик-раунд round2, замечание: с голым `"utf-8"`
    декодер НЕ снимает BOM-байты, `﻿` остаётся первым символом строки и
    ломает `^`-якорь регекса, если BOM-символ оказывается ПЕРЕД самой строкой
    `id:` — см. `test_load_case_frontmatter_bom_prefix_before_id_line_does_
    not_break_id_regex`).

    ВОЗВРАТ — ПАРА `(кейсы, находки)` (критик-раунд round3, Б1; та же идиома,
    что `_parse_framework_file` -> `(tree, err)`): нечитаемый файл кейса
    (каталог с именем `*.md`, отказ прав, битая кодировка — см.
    `_read_case_text`) даёт находку `rule="case_frontmatter_read"`, а не
    трассировку и не тихий пропуск (тихий пропуск оставил бы файл БЕЗ единой
    находки ЛЮБОГО правила — тот же довод, что D2-F2 у нечитаемого
    steps-файла). Канал в `run()` — `cases:`, ярус WARN: нечитаемость файла
    кейса не есть нарушение архитектуры фреймворка, а красить весь
    канонический прогон транзиентным отказом ФС — цена выше пользы.

    `status` (Б2) читается наравне с `priority`/`automated_by` — по нему
    правила 5 и 6-А молчат на не-рабочих статусах, см.
    `_NON_WORKING_CASE_STATUSES`."""
    if not CASES_DIR.exists():
        return {}, []
    out: dict[str, dict] = {}
    read_errors: list[Finding] = []
    for path in sorted(CASES_DIR.rglob("*.md")):
        if path.name.upper() in _CASE_FRONTMATTER_SKIP_NAMES:
            continue
        rel = path.relative_to(REPO).as_posix()
        text = _read_case_text(path)
        if text is None:
            read_errors.append(Finding(
                rel, "case_frontmatter_read",
                f"{rel}: файл кейса не прочитан (каталог с именем *.md, отказ прав "
                f"или битая кодировка) — правила 3/5/6 по нему не применялись"))
            continue
        m_id = _CASE_ID_RE.search(text)
        if not m_id:
            continue
        case_id = m_id.group(1).strip()
        if not case_id:
            continue
        m_ab = _AUTOMATED_BY_RE.search(text)
        m_pri = _CASE_PRIORITY_RE.search(text)
        m_status = _CASE_STATUS_RE.search(text)
        out[case_id] = {
            "rel": rel,
            "automated_by": m_ab.group(1).strip() if m_ab else "",
            "ab_line": (text[: m_ab.start()].count("\n") + 1) if m_ab else 1,
            "priority": m_pri.group(1).strip() if m_pri else "",
            "status": m_status.group(1).strip() if m_status else "",
        }
    return out, read_errors


# --- Правило 5: PRIORITY-MARKER-CONSISTENCY (см. докстринг модуля). ЧЕТВЁРТАЯ
# ветвь обхода — framework/tests/**/test_*.py (тот же обход, что правила 1-2) +
# frontmatter test-cases/. Отдельный WARNS-канал (см. `run`). ---

_PRIORITY_LEVEL_RE = re.compile(r"^[Pp](\d+)$")


def check_priority_marker(tree: ast.Module, rel: str, suite_markers: set[str],
                           case_frontmatter: dict[str, dict]) -> list[Finding]:
    """Для каждой тест-функции с `@allure.id("TC-xxx")` И РОВНО ОДНИМ suite-маркером
    (`p<N>`) — сверка `N` с `priority: P<N>` кейса TC-xxx. Молчание (не находка),
    если: allure.id отсутствует (ERROR правила 2), suite-маркеров 0 (ERROR правила 2)
    или >1 (неоднозначно, вне скоупа), кейс TC-xxx не найден в корпусе, `priority`
    кейса пуст/не разбирается по форме `P<N>`, ЛИБО `status` кейса вне рабочих
    (`_NON_WORKING_CASE_STATUSES` — `Merged`/`Draft`, критик-раунд round3 Б2:
    ERROR не выводится из полей кейса, которые не авторитетны для теста)."""
    findings: list[Finding] = []
    for fn in _test_functions(tree):
        allure_id = _allure_id_value(fn)
        if allure_id is None:
            continue
        dotted = [_decorator_dotted(d) for d in fn.decorator_list]
        hit_markers = {d.rsplit(".", 1)[-1] for d in dotted if d.startswith("pytest.mark.")} & suite_markers
        if len(hit_markers) != 1:
            continue
        marker = next(iter(hit_markers))
        marker_m = re.fullmatch(r"p(\d+)", marker)
        if not marker_m:
            continue
        case = case_frontmatter.get(allure_id)
        if case is None:
            continue
        if case.get("status", "") in _NON_WORKING_CASE_STATUSES:
            continue
        priority_m = _PRIORITY_LEVEL_RE.match(case["priority"])
        if not priority_m:
            continue
        if marker_m.group(1) != priority_m.group(1):
            findings.append(Finding(
                rel, "priority_marker",
                f"framework/{rel}:{fn.lineno}: тест `{fn.name}` (allure.id \"{allure_id}\") несёт "
                f"suite-маркер `{marker}`, но приоритет кейса {allure_id} — `{case['priority']}` "
                f"({case['rel']}) — ожидался маркер `p{priority_m.group(1)}`",
                lineno=fn.lineno, func_name=fn.name, method_name=allure_id,
            ))
    return findings


def run_priority_marker_rule(case_frontmatter: dict[str, dict] | None = None) -> list[Finding]:
    """Правило 5 по framework/tests/**/test_*.py (см. докстринг блока выше). Всегда
    WARNS — нечитаемый файл пропускается (уже покрыт "parse"-ERROR правил 1-2).

    `case_frontmatter` — уже загруженный корпус (`run()` грузит его ОДИН раз на
    оба правила 5/6 и сам докладывает нечитаемые файлы, критик-раунд round3 Б1);
    `None` — загрузить самому (прямой вызов из тестов/скриптов)."""
    if not TESTS_DIR.exists():
        return []
    suite_markers = load_suite_markers()
    if case_frontmatter is None:
        case_frontmatter, _read_errors = load_case_frontmatter()
    findings: list[Finding] = []
    for path in sorted(TESTS_DIR.rglob("test_*.py")):
        tree, err = _parse_framework_file(path)
        if err is not None:
            continue
        rel = path.relative_to(FRAMEWORK).as_posix()
        findings.extend(check_priority_marker(tree, rel, suite_markers, case_frontmatter))
    return findings


# --- Правило 6: AUTOMATED-BY-ALLURE-ID-LINK (см. докстринг модуля). ПЯТАЯ ветвь
# обхода — обе стороны связки кейс<->тест. Отдельный WARNS-канал (см. `run`). ---


def check_automated_by_link_case_side(case_frontmatter: dict[str, dict]) -> list[Finding]:
    """Направление А (кейс -> тест): у КАЖДОГО кейса с непустым `automated_by` тест
    обязан резолвиться И нести `@allure.id("<id_кейса>")`. `_resolve_test_function`/
    `_split_automated_by`/`_PARSE_ERROR` — общие с правилом 3 (тот же приём резолва
    "путь::функция", тот же fail-closed на неразбираемую форму).

    Молчание по `status` вне рабочих (`_NON_WORKING_CASE_STATUSES` —
    `Merged`/`Draft`, критик-раунд round3 Б2): та же ветвь, что у правила 5, тот
    же довод. Направление Б (`check_automated_by_link_test_side`) статусом НЕ
    гасится — оно WARN, и его real-repo-пин держит ровно СЛИТЫЕ TC-034/035/036
    как детектор дрейфа."""
    findings: list[Finding] = []
    for case_id, case in case_frontmatter.items():
        automated_by = case["automated_by"]
        if not automated_by:
            continue
        if case.get("status", "") in _NON_WORKING_CASE_STATUSES:
            continue
        split = _split_automated_by(automated_by)
        resolved = _resolve_test_function(*split) if split else None
        if split is None or resolved is None:
            findings.append(Finding(
                case["rel"], "automated_by_orphan",
                f"{case['rel']}:{case['ab_line']}: automated_by `{automated_by}` не разрешается "
                f"— кейс {case_id} ссылается на несуществующий тест"))
            continue
        if resolved is _PARSE_ERROR:
            continue  # покрыто ERROR правил 1-2 (parse) — не дублируем
        fn, _tree = resolved
        actual_id = _allure_id_value(fn)
        func_label = automated_by.split("[", 1)[0]
        if actual_id != case_id:
            if actual_id is None:
                mismatch = "тест не несёт @allure.id(...) вовсе"
            else:
                mismatch = f"тест несёт allure.id(\"{actual_id}\")"
            findings.append(Finding(
                case["rel"], "automated_by_orphan",
                f"{case['rel']}:{case['ab_line']}: automated_by кейса {case_id} указывает на "
                f"`{func_label}`, но {mismatch} вместо ожидаемого allure.id(\"{case_id}\")"))
    return findings


def check_automated_by_link_test_side(case_frontmatter: dict[str, dict]) -> list[Finding]:
    """Направление Б ("и наоборот" спеки, тест -> кейс): у КАЖДОГО теста с
    `@allure.id("TC-xxx")`, для которого кейс TC-xxx существует в корпусе,
    `automated_by` этого кейса обязан резолвиться РОВНО К ЭТОМУ тесту. Тест без
    кейса в корпусе (allure.id не найден среди `case_frontmatter`) — вне скоупа
    правила (см. докстринг модуля), молчание."""
    if not TESTS_DIR.exists():
        return []
    findings: list[Finding] = []
    for path in sorted(TESTS_DIR.rglob("test_*.py")):
        tree, err = _parse_framework_file(path)
        if err is not None:
            continue
        rel = path.relative_to(FRAMEWORK).as_posix()
        rel_from_repo = path.relative_to(REPO).as_posix()
        for qualname, fn in _test_functions_with_qualname(tree):
            allure_id = _allure_id_value(fn)
            if allure_id is None:
                continue
            case = case_frontmatter.get(allure_id)
            if case is None:
                continue  # тест без кейса — вне скоупа правила 6 (докстринг модуля)
            automated_by = case["automated_by"]
            this_identity = f"{rel_from_repo}::{qualname}"
            if not automated_by:
                findings.append(Finding(
                    rel, "allure_id_orphan",
                    f"framework/{rel}:{fn.lineno}: тест `{qualname}` несёт "
                    f"allure.id(\"{allure_id}\"), но automated_by кейса {allure_id} "
                    f"({case['rel']}) пуст",
                    lineno=fn.lineno, func_name=qualname, method_name=allure_id,
                ))
                continue
            func_label = automated_by.split("[", 1)[0]
            if func_label != this_identity:
                findings.append(Finding(
                    rel, "allure_id_orphan",
                    f"framework/{rel}:{fn.lineno}: тест `{qualname}` несёт "
                    f"allure.id(\"{allure_id}\"), но automated_by кейса {allure_id} "
                    f"({case['rel']}) указывает на другой тест: `{func_label}`",
                    lineno=fn.lineno, func_name=qualname, method_name=allure_id,
                ))
    return findings


def run_automated_by_link_rule(case_frontmatter: dict[str, dict] | None = None) -> list[Finding]:
    """Правило 6 — оба направления (см. докстринг блока выше). Ярус — по
    направлениям, см. `run()`. `case_frontmatter` — см. `run_priority_marker_rule`."""
    if case_frontmatter is None:
        case_frontmatter, _read_errors = load_case_frontmatter()
    return check_automated_by_link_case_side(case_frontmatter) + check_automated_by_link_test_side(case_frontmatter)


def run() -> tuple[list[str], list[str]]:
    """Возвращает (errors, warns). ЯРУС по правилам (Р1, критик-раунд round2,
    2026-08-25):
    - правила 1-2 (locators/allure_id/marker) — ERROR, ALLOWLIST (rel, rule)
      гасит до WARN;
    - правило 3 (recording) — ВСЕГДА WARN, канал `rule3:`;
    - правило 4 (negative_then_settle) — ВСЕГДА WARN, канал `rule4:`, гейт —
      NEGATIVE_THEN_SETTLE_BASELINE (не ALLOWLIST);
    - правило 5 (priority_marker) — ERROR, канал `rule5:` в тексте самого
      ERROR; ALLOWLIST-ключ ТРЁХэлементный `(rel, rule, func_name)` (1:N —
      несколько тест-функций одного файла, см. докстринг модуля);
    - правило 6, направление А (automated_by_orphan) — ERROR, канал `rule6:`
      в тексте самого ERROR, ALLOWLIST-ключ (rel, rule) (1:1, см. докстринг
      модуля); направление Б (allure_id_orphan) — ВСЕГДА WARN, канал `rule6:`;
    - нечитаемый файл test-cases/ (case_frontmatter_read, критик-раунд round3
      Б1) — ВСЕГДА WARN, канал `cases:`.

    Корпус кейсов грузится ОДИН раз на правила 5 и 6 (критик-раунд round3, Б1:
    раньше `run_priority_marker_rule` и `run_automated_by_link_rule` читали все
    ~290 md-файлов КАЖДЫЙ свой раз — а доклад о нечитаемом файле в двух обходах
    был бы двойным).
    """
    errors: list[str] = []
    warns: list[str] = []
    case_frontmatter, case_read_errors = load_case_frontmatter()
    if not TESTS_DIR.exists():
        errors.append(f"framework/tests не найден по пути {TESTS_DIR}")
    else:
        for path in sorted(TESTS_DIR.rglob("test_*.py")):
            for finding in check_file(path):
                key = (finding.rel, finding.rule)
                if key in ALLOWLIST:
                    warns.append(f"{finding.message} [известное исключение — test-debt, см. ALLOWLIST]")
                else:
                    errors.append(finding.message)

    # Правило 3 (ВТОРАЯ ветвь обхода, test-cases/) — независима от TESTS_DIR;
    # ВСЕГДА warns, никогда errors (Б7).
    for finding in run_recording_rule():
        key = (finding.rel, finding.rule)
        message = f"rule3: {finding.message}"
        if key in ALLOWLIST:
            warns.append(f"{message} [известное исключение — см. ALLOWLIST]")
        else:
            warns.append(message)

    # Правило 4 (ТРЕТЬЯ ветвь обхода, framework/steps/*.py) — независима от TESTS_DIR;
    # ВСЕГДА warns, никогда errors (см. докстринг модуля). Каждое попадание несёт
    # вердикт из NEGATIVE_THEN_SETTLE_BASELINE (ключ — (rel, func_name, method_name),
    # НЕ lineno, критик-вход D2-F1); отсутствие ключа — НЕ гашение находки (в отличие
    # от ALLOWLIST у правил 1-2/3) — это НОВАЯ находка, дрейф бейзлайна. Находки типа
    # "negative_then_settle_parse" (нечитаемый steps-файл, D2-F2) — не попадание
    # правила, с бейзлайном не сверяются, печатаются как есть.
    for finding in run_negative_then_settle_rule():
        if finding.rule == "negative_then_settle_parse":
            warns.append(f"rule4: {finding.message}")
            continue
        key = (finding.rel, finding.func_name, finding.method_name)
        if key in NEGATIVE_THEN_SETTLE_BASELINE:
            verdict = NEGATIVE_THEN_SETTLE_BASELINE[key]
            warns.append(f"rule4: {finding.message} [вердикт: {verdict}]")
        else:
            warns.append(f"rule4: {finding.message} [без вердикта — НОВАЯ находка, не в бейзлайне]")

    # Правило 5 (ЧЕТВЁРТАЯ ветвь обхода, PRIORITY-MARKER-CONSISTENCY) — ERROR
    # (Р1, критик-раунд round2, 2026-08-25; было WARN — единственное живое
    # расхождение TC-039 починено маркером Р2 ДО этого хода). Ключ ALLOWLIST —
    # ТРЁХэлементный (rel, rule, func_name): связь тест-файл -> находка 1:N
    # (несколько тест-функций одного файла), двухэлементный ключ гасил бы
    # ВЕСЬ файл одной записью (декоративный ALLOWLIST, критик-раунд round2,
    # замечание — здесь исправлено на реально исключающий).
    for finding in run_priority_marker_rule(case_frontmatter):
        key = (finding.rel, finding.rule, finding.func_name)
        message = f"rule5: {finding.message}"
        if key in ALLOWLIST:
            warns.append(f"{message} [известное исключение — см. ALLOWLIST]")
        else:
            errors.append(message)

    # Правило 6 (ПЯТАЯ ветвь обхода, AUTOMATED-BY-ALLURE-ID-LINK) — ЯРУС ПО
    # НАПРАВЛЕНИЯМ РАЗНЫЙ (Р1, критик-раунд round2, 2026-08-25): направление А
    # (automated_by_orphan, кейс -> тест) — ERROR, 0 живых находок; направление
    # Б (allure_id_orphan, тест -> кейс) — ВСЕГДА WARN (2 из 9 живых находок —
    # структурно ложные, split-паттерн, см. докстринг модуля). Ключ ALLOWLIST
    # для обоих направлений — (rel, rule) (для А это уже точно 1:1, см.
    # докстринг модуля; для Б — декоративный тег, тот же случай, что правило 3,
    # т.к. направление Б навсегда WARN); критик-раунд round2 (замечание): гейт
    # направления А был декоративным (обе ветки клали находку в warns
    # НЕЗАВИСИМО от ALLOWLIST) — исправлено на реально исключающий.
    for finding in run_automated_by_link_rule(case_frontmatter):
        key = (finding.rel, finding.rule)
        message = f"rule6: {finding.message}"
        if finding.rule == "automated_by_orphan":
            if key in ALLOWLIST:
                warns.append(f"{message} [известное исключение — см. ALLOWLIST]")
            else:
                errors.append(message)
        else:
            if key in ALLOWLIST:
                warns.append(f"{message} [известное исключение — см. ALLOWLIST]")
            else:
                warns.append(message)

    # Нечитаемые файлы test-cases/ (критик-раунд round3, Б1) — собственный канал
    # `cases:`, ярус WARN. Не молчание (файл иначе остался бы без единой находки
    # ЛЮБОГО правила) и не ERROR (нечитаемость файла кейса — не нарушение
    # архитектуры фреймворка; красить весь канонический прогон транзиентным
    # отказом ФС дороже пользы). ALLOWLIST здесь не применяется: гасить отказ
    # чтения записью «известное исключение» — заведомо неверная форма.
    for finding in case_read_errors:
        warns.append(f"cases: {finding.message}")

    return errors, warns


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Статический чек архитектуры тест-фреймворка (docs/08 C1): "
                    "запрет driver/локаторов в tests/, обязательные allure.id и suite-маркер")
    parser.add_argument("--no-warns", action="store_true", help="не печатать WARN")
    args = parser.parse_args(argv)

    errors, warns = run()
    for e in errors:
        print(f"  [ERROR] {e}")
    if not args.no_warns:
        for w in warns:
            print(f"  [WARN] {w}")
    print(f"arch_check: ошибок {len(errors)}, предупреждений {len(warns)}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
