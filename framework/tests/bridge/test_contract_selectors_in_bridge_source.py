"""N6 контракт-слой (Р2, `docs/tasks/p2-pyramid-bridge.md`), Requirement 1:
«каждый селектор реестра встречается в файле-носителе контракта кода» —
детектор переименования/удаления узла, который bridge (или его сателлит)
реально читает/пишет.

Lead-решение 2026-08-19 («гибрид (A)+(B), ОБА структурно, без потери
детекторной силы» — ответ на находку builder'а: 4/21 записей реестра не
проходили наивный `selector in ao3_bridge.js`, т.к. (1) getElementById-узлы
пишутся в реестре CSS-формой `#id`, а код зовёт `getElementById('id')` без
решётки, (2) `#kudo_submit` контрактно читается НЕ из `ao3_bridge.js`, а
инлайн-JS-строкой `evalJs(...)` из `BrowserViewModel.kt`, (3) поле
`work_search[words_from]` bridge не адресует литералом вовсе — матчит ЛЮБОЕ
поле формы regex-паттерном): контракт кода держат структурные поля
`BridgeSelectorEntry.source`/`.code_token` (`framework/data/
bridge_selectors.py`), не свободный текст `functions` и не исключения
по имени.

Алгоритм (по умолчанию, без `code_token`; ИСПРАВЛЕНО attempt 2 — критик-вход
Б2): если `selector` — ПРОСТОЙ id-селектор вида `#name` (без комбинаторов/
атрибутов/потомков), ищется ТОЛЬКО голый токен в кавычках (`'name'` или
`"name"`) — закрывает разрыв `getElementById(id)` (код без решётки). Сырой
`entry.selector` (с `#`) в поиск для id-селекторов НЕ включается — было (до
attempt 2) `(entry.selector, "'name'", '"name"')`, но сырой `#id` ГАСИТ
детектор в двух классах: (1) переименование `id` в коде при УСТАРЕВШЕМ
комментарии, всё ещё несущем старое имя с `#` (в текущем реестре ТРИ такие
записи несут `#id` в комментарии рядом с кодом — `#chapters`
(`ao3_bridge.js:1199`), `#selected_id` (`ao3_bridge.js:951`), `#work-filters`
(`ao3_bridge.js:974`/`1161`) — сырой токен сделал бы их зелёными ДАЖЕ если
реальный `getElementById(...)`-вызов переименован, комментарий один держал
бы тест); (2) надмножество-переименование (`#chapters` → `#chaptersV2`) —
сырой `#chapters` остаётся substring'ом `#chaptersV2`, тест 1 не заметил бы
переименования; кавычечная форма `'chapters'` НЕ матчит `'chaptersV2'`
(закрывающая кавычка граничит точный литерал) — детектирует. Для
НЕ-id-селекторов (составные/атрибутные, вроде `li[id^="work_"].work.blurb`)
по-прежнему ищется сам `selector` буквально (у них нет getElementById-разрыва
и нет короткого id-токена для нормализации). Явный `code_token` (когда
задан) ПОЛНОСТЬЮ заменяет автовывод — для узлов, которые код адресует ни
селектором, ни `getElementById`-литералом, а ПАТТЕРНОМ (`ao3_bridge.js:1002`/
`1009`, `injectSaveFilterButton`, матчит `form.elements` двумя regex'ами,
не именем конкретного поля). Пустой/пробельный `code_token` — `ValueError`
(не-блокер 1 критика: пустая строка `"" in text` истинна ВСЕГДА — вечнозелёная
запись без этой проверки).

ОГРАНИЧЕНИЯ (явные строки, Р2):
  (а) реестр ОДНОСТОРОННИЙ — НОВЫЙ селектор бриджа, никогда не попадавший в
      `REGISTRY`, этой проверкой НЕ ловится (детектор ловит переименование/
      удаление УЖЕ учтённого узла, не появление нового). Компенсация —
      `ao3_bridge.js` остаётся `wide_impact` в `state/impact-map.yaml` (Р5):
      любая правка бриджа = полная регрессия, а не точечный прогон реестра.
  (б) поиск ТЕКСТОВЫЙ по файлу ЦЕЛИКОМ — совпадение в КОММЕНТАРИИ засчиты-
      вается наравне с совпадением в коде (простая substring-проверка не
      различает контекст). Кавычечная нормализация (см. алгоритм выше)
      СНИМАЕТ конкретные три случая, найденные в ТЕКУЩЕМ реестре (комментарии
      там несут только `#id`-форму, не кавычечную `'id'`/`"id"` — сверено:
      ни один из шести id-based `getElementById`-матчей сегодня не опирается
      на комментарий, все шесть находятся РЕАЛЬНЫМ кодом), но НЕ снимает
      ограничение (б) КАК КЛАСС: если бы устаревший комментарий содержал
      кавычечную форму (`// legacy: getElementById('chapters')` рядом с уже
      переименованным реальным вызовом) — тест 1 всё ещё засчитал бы её как
      совпадение. Это остаётся заявленной слабостью текстового детектора, не
      закрытой полностью ни для одной из версий алгоритма."""
from __future__ import annotations

import re

import allure
import pytest

from framework.config import settings
from framework.data.bridge_selectors import REGISTRY, BridgeSelectorEntry

# Простой id-селектор: `#name`, без потомков/комбинаторов/атрибутов/классов
# рядом. Специально УЗКИЙ (не пытается разобрать CSS вообще) — расширять
# только под НОВЫЙ структурно объявленный случай, не для "почти подходящих"
# селекторов (те получают явный `code_token`, см. докстринг модуля/реестра).
_SIMPLE_ID_SELECTOR_RE = re.compile(r"^#[A-Za-z0-9_-]+$")


def _search_tokens(entry: BridgeSelectorEntry) -> tuple[str, ...]:
    """Какие текстовые токены считаются "селектор найден в source" для
    ДАННОЙ записи реестра — см. алгоритм в докстринге модуля.

    attempt 2 (критик-вход Б2): для простого id-селектора возвращаются
    ТОЛЬКО кавычечные формы (`'name'`/`"name"`) — сырой `entry.selector`
    (с `#`) больше НЕ входит в токены (гасил детектор на устаревшем
    комментарии/надмножество-переименовании, см. докстринг модуля)."""
    if entry.code_token is not None:
        if not entry.code_token.strip():
            raise ValueError(
                f"BridgeSelectorEntry.code_token не может быть пустым/пробельным "
                f"(запись selector={entry.selector!r}) -- пустая строка была бы "
                "substring'ом ЛЮБОГО текста, тест 1 стал бы вечнозелёным "
                "(не-блокер 1 критика, attempt 2)"
            )
        return (entry.code_token,)
    if _SIMPLE_ID_SELECTOR_RE.match(entry.selector):
        bare_id = entry.selector[1:]
        return (f"'{bare_id}'", f'"{bare_id}"')
    return (entry.selector,)


def _source_text(source: str) -> str:
    return (settings.REPO_ROOT / source).read_text(encoding="utf-8")


def _token_found(entry: BridgeSelectorEntry, text: str) -> bool:
    return any(token in text for token in _search_tokens(entry))


@pytest.mark.bridge
@pytest.mark.p1
@allure.id("bridge-contract-selector-found-in-source")
@allure.title("N6 контракт: КАЖДЫЙ селектор/code_token реестра встречается в СВОЁМ source-файле")
@pytest.mark.parametrize(
    "entry", REGISTRY, ids=[f"{e.source}__{e.selector}" for e in REGISTRY]
)
def test_selector_found_in_source(entry: BridgeSelectorEntry):
    text = _source_text(entry.source)
    tokens = _search_tokens(entry)
    assert _token_found(entry, text), (
        f"реестр (framework/data/bridge_selectors.py) заявляет узел {entry.selector!r} "
        f"(source={entry.source!r}"
        + (f", code_token={entry.code_token!r}" if entry.code_token is not None else "")
        + f") — ни один из искомых токенов {tokens!r} не найден в файле целиком. "
        "Либо узел переименован/удалён в коде (регресс класса AT-BUG-074), "
        "либо запись реестра рассинхронизировалась с source."
    )


@pytest.mark.bridge
@pytest.mark.p1
@allure.id("bridge-contract-selector-search-catches-renamed-token")
@allure.title("N6 контракт, красная проба: поиск токена в source ловит ПЕРЕИМЕНОВАННЫЙ/удалённый узел")
def test_selector_search_catches_absent_token():
    """Красная проба (CLAUDE.md builder п.4/6а, тот же приём, что red-proof
    теста 2 в `test_contract_pages_carry_declared_selectors.py`): фиктивная
    ЗАПИСЬ реестра (не трогает `REGISTRY`) с заведомо несуществующим id —
    доказывает, что `_token_found` умеет возвращать `False`, а не всегда
    `True` (позитив выше не вакуумно-истинен)."""
    fake_entry = BridgeSelectorEntry(
        selector="#definitely-not-a-real-bridge-node-xyz123",
        functions=("synthetic red-proof entry, not a real contract",),
        pages=(),
    )
    text = _source_text(fake_entry.source)
    assert not _token_found(fake_entry, text), (
        "красная проба провалена: заведомо несуществующий id-токен помечен "
        "как найденный -- поиск вакуумно-истинен, не различает "
        "присутствие/отсутствие узла в коде"
    )

    # То же самое для code_token-варианта (words_from-класс) — доказывает,
    # что явный code_token тоже реально ищется, не просто игнорируется.
    fake_pattern_entry = BridgeSelectorEntry(
        selector="input[name=\"work_search[definitely_not_a_real_field]\"]",
        functions=("synthetic red-proof entry, not a real contract",),
        pages=(),
        code_token="definitely_not_a_real_regex_prefix_xyz123[",
    )
    assert not _token_found(fake_pattern_entry, _source_text(fake_pattern_entry.source))

    # sanity: тот же source, тот же helper, но РЕАЛЬНЫЙ селектор реестра —
    # доказывает, что False выше НЕ из-за сломанного чтения файла вообще.
    real_entry = REGISTRY[0]
    assert _token_found(real_entry, _source_text(real_entry.source)) is True


@pytest.mark.bridge
@pytest.mark.p1
@allure.id("bridge-contract-code-token-rejects-empty-or-whitespace")
@allure.title("N6 контракт, граница: пустой/пробельный code_token отвергается (не вечнозелёная запись)")
@pytest.mark.parametrize("bad_token", ["", "   ", "\t\n"], ids=["empty", "spaces", "tab-newline"])
def test_search_tokens_rejects_empty_or_whitespace_code_token(bad_token: str):
    """Не-блокер 1 критика (attempt 2, взят решением Lead): без этой проверки
    `code_token=""` был бы substring'ом ЛЮБОГО текста (`"" in text` всегда
    `True`) — запись реестра, случайно/ошибочно получившая пустой
    `code_token`, никогда не поймала бы переименование/удаление узла.
    Параметризовано НА границе (`""`) и ЗА ней (пробелы/таб/перевод строки —
    непусто по `len()`, но пусто по смыслу, CLAUDE.md builder п.6а)."""
    entry = BridgeSelectorEntry(
        selector="#irrelevant-for-this-test",
        functions=("synthetic red-proof entry, not a real contract",),
        pages=(),
        code_token=bad_token,
    )
    with pytest.raises(ValueError):
        _search_tokens(entry)
