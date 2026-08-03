"""validate_frontmatter — preflight-валидация артефактов по schemas/*.schema.yaml (G3).

Битый frontmatter (опечатка в статусе, потерянное поле, дубль id) раньше всплывал
только в момент, когда правило /qa-loop или скрипт спотыкались об артефакт.
Теперь ловим до диспетчеризации: /qa-loop запускает валидатор в preflight.

Проверки:
- frontmatter присутствует и парсится;
- required-поля есть и непусты;
- id соответствует id_pattern своего типа;
- enum/pattern полей из схемы (PyYAML-коэрция дат учитывается: datetime → ISO);
- id уникален в пределах репозитория;
- поле не из схемы — [WARN], не ошибка (шаблоны эволюционируют).

Запуск: python scripts/validate_frontmatter.py
Коды выхода: 0 — чисто (WARN допустимы); 1 — есть ошибки (список в stdout).
"""
from __future__ import annotations

import argparse
import datetime
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

import board_sync as bs

REPO = bs.REPO
SCHEMAS = REPO / "schemas"
FEATURE_REGISTRY = REPO / "docs" / "feature-registry.yaml"
AREAS = (("test-cases", "test-case"), ("bugs", "bug"), ("runs", "run"),
         ("exploratory-charters", "charter"))


def load_schema(itype: str) -> dict:
    p = SCHEMAS / f"{itype}.schema.yaml"
    if not p.exists():
        return {}
    import yaml
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def load_feature_registry() -> set[str] | None:
    """Id-ы docs/feature-registry.yaml. None — реестр отсутствует (WARN на
    вызывающей стороне, не ERROR: реестр — диспатч 1 trace-matrix, его
    отсутствие в чужом клоне/до миграции не должно ронять весь конвейер)."""
    if not FEATURE_REGISTRY.exists():
        return None
    import yaml
    data = yaml.safe_load(FEATURE_REGISTRY.read_text(encoding="utf-8")) or {}
    return {str(f.get("id")) for f in data.get("features", []) or [] if f.get("id")}


def _frontmatter_raw(text: str) -> str | None:
    """Сырое тело frontmatter (между `---` и `---`), ДО yaml.safe_load —
    нужно проверкам, которые обязаны видеть исходные строки (дубль ключа
    PyYAML молча схлопывает при парсинге, см. check_duplicate_keys). Границы
    зеркалят board_sync._parse_frontmatter (тот модуль не в owns этой
    задачи — переиспользовать импортом raw нельзя, он его не возвращает;
    здесь дублируется только определение границ, не парсинг)."""
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    return text[3:end].strip("\n")


_TOP_LEVEL_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:")


def check_duplicate_keys(raw: str, rel: str) -> list[str]:
    """Дублирующийся ключ ВЕРХНЕГО уровня в теле frontmatter — ERROR.
    PyYAML.safe_load молча берёт последнее значение (не падает), но это
    невалидный YAML и порча данных без сигнала (BUG-021, 2026-08-02: два
    `gitlab_issue:` в одном файле, обнаружено вручную postfactum).

    Строка считается ключом верхнего уровня, только если regex матчится с
    НУЛЕВОГО отступа (`^` на re.match без re.MULTILINE — работает построчно
    через splitlines, так что `^` = начало КОНКРЕТНОЙ строки): вложенные
    поля и элементы списков всегда идут с отступом в наших артефактах,
    строка внутри folded/literal-блока (`|`/`>`) с двоеточием на нулевом
    отступе теоретически невозможна — контент такого блока YAML обязан
    иметь больший отступ, чем сам ключ-блок, иначе это уже не часть блока.
    Проверено на живом корпусе (bugs/test-cases/runs/exploratory-charters,
    2026-08-02) — многострочных значений с этим риском не найдено.

    Три и более повторения одного ключа — ОДИН ERROR с точным числом
    повторов (не N ошибок): решение задачи (граница спеки, п. «ТЕСТЫ») —
    один дубль ключа это одна причина порчи данных этого файла, отдельная
    ошибка на каждое лишнее вхождение не добавляет диагностической
    ценности и раздувает вывод для файла с случайно повторённым ключом
    3+ раза."""
    counts: dict[str, int] = {}
    for line in raw.splitlines():
        m = _TOP_LEVEL_KEY_RE.match(line)
        if m:
            key = m.group(1)
            counts[key] = counts.get(key, 0) + 1
    errors: list[str] = []
    for key, n in counts.items():
        if n > 1:
            errors.append(
                f"{rel}: дублирующийся ключ `{key}` во frontmatter ({n}x) — "
                f"PyYAML молча берёт последнее значение, данные остальных теряются")
    return errors


def _s(value) -> str:
    """Значение frontmatter → строка для pattern-проверок (учёт коэрции PyYAML)."""
    if value is None:
        return ""
    if isinstance(value, datetime.datetime):
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, datetime.date):
        return value.isoformat()
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def check_meta(meta: dict, schema: dict, rel: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warns: list[str] = []

    for f in schema.get("required", []):
        if _s(meta.get(f)).strip() == "":
            errors.append(f"{rel}: required-поле `{f}` отсутствует или пусто")

    idp = schema.get("id_pattern")
    if idp and meta.get("id") is not None and not re.match(idp, _s(meta["id"])):
        errors.append(f"{rel}: id `{_s(meta['id'])}` не соответствует `{idp}`")

    fields = schema.get("fields", {}) or {}
    for name, value in meta.items():
        if name in ("id",):
            continue
        spec = fields.get(name)
        if spec is None:
            if name not in schema.get("required", []):
                warns.append(f"{rel}: поле `{name}` не описано в схеме {schema.get('type')}")
            continue
        sval = _s(value)
        if "enum" in spec and sval and sval not in [str(e) for e in spec["enum"]]:
            errors.append(f"{rel}: `{name}: {sval}` вне enum {spec['enum']}")
        if "pattern" in spec and sval and not re.match(spec["pattern"], sval):
            errors.append(f"{rel}: `{name}: {sval}` не соответствует `{spec['pattern']}`")
    errors += check_cross_field(meta, schema, rel)
    return errors, warns


def check_cross_field(meta: dict, schema: dict, rel: str) -> list[str]:
    """Проверки, затрагивающие больше одного поля (B1/B3/B5, docs/09 Этап 2)."""
    errors: list[str] = []
    fields = schema.get("fields", {}) or {}
    # B1: resolution (accepted_risk/wontfix) требует зафиксированного человеком
    # обоснования — без него это неотличимо от произвольной пометки в frontmatter.
    if "resolution" in fields and _s(meta.get("resolution")).strip():
        if not _s(meta.get("resolution_comment")).strip():
            errors.append(
                f"{rel}: `resolution: {_s(meta.get('resolution'))}` без `resolution_comment` "
                f"(B1 требует обоснование)")
    # B3: карантин без причины/времени — слепое пятно SLA-надзора (quarantine_expired).
    if _s(meta.get("automation_status")) == "quarantined":
        for f in ("quarantine_reason", "quarantine_since"):
            if not _s(meta.get(f)).strip():
                errors.append(
                    f"{rel}: automation_status quarantined без `{f}` "
                    f"(B3: карантин не бывает бесконечным и безымянным)")
    # Конвенция ID (2026-07-08): AT-BUG-xxx <-> type: test_debt — префикс и тип
    # должны совпадать в обе стороны, иначе баг попадает не в ту очередь
    # (внешняя команда разработки vs фабрика).
    if schema.get("type") == "bug":
        bug_id = _s(meta.get("id"))
        is_test_debt = _s(meta.get("type")) == "test_debt"
        is_at_prefixed = bug_id.startswith("AT-BUG-")
        if is_test_debt and not is_at_prefixed:
            errors.append(
                f"{rel}: `type: test_debt` требует id с префиксом `AT-BUG-` "
                f"(получено `{bug_id}`) — иначе баг ошибочно уйдёт внешней команде")
        if is_at_prefixed and not is_test_debt:
            errors.append(
                f"{rel}: id `{bug_id}` с префиксом `AT-BUG-` требует "
                f"`type: test_debt` (получено `{_s(meta.get('type')) or '(нет)'}`)")
    # Красный замок (Lead 2026-08-03, прецедент TC-139/BUG-015): red_lock
    # указывает баг, до фикса которого автотест намеренно красный — guard
    # правила F1 в rules.yaml читает это поле; здесь держим целостность.
    if schema.get("type") == "test-case" and _s(meta.get("red_lock")).strip():
        lock_id = _s(meta.get("red_lock")).strip()
        if not _s(meta.get("automated_by")).strip():
            errors.append(
                f"{rel}: `red_lock: {lock_id}` без `automated_by` — красный замок "
                f"и есть намеренно-красный автотест, без теста поле бессмысленно")
        if not (REPO / "bugs" / f"{lock_id}.md").exists():
            errors.append(
                f"{rel}: `red_lock: {lock_id}` ссылается на несуществующий "
                f"bugs/{lock_id}.md — битая ссылка замка")
    return errors


def check_cross_field_warn(meta: dict, schema: dict, rel: str) -> list[str]:
    """WARN-уровень: недозаполненность, не ломающая конвейер (B2/B3/B4/B5)."""
    warns: list[str] = []
    fields = schema.get("fields", {}) or {}
    # B5: переход с борды может не нести причину сразу.
    if "blocked_reason" in fields and _s(meta.get("status")) == "Blocked" \
            and not _s(meta.get("blocked_reason")).strip():
        warns.append(f"{rel}: status Blocked без `blocked_reason` — заполнить причину (B5)")
    # B3: lifecycle автотеста имеет смысл только у Automated-кейса.
    if _s(meta.get("automation_status")).strip() and _s(meta.get("status")) != "Automated":
        warns.append(
            f"{rel}: automation_status `{_s(meta.get('automation_status'))}` при "
            f"status `{_s(meta.get('status'))}` — поле живёт только у Automated (B3)")
    # B4: test_debt без категории хуже виден в digest.
    if _s(meta.get("type")) == "test_debt" and not _s(meta.get("debt_kind")).strip():
        warns.append(f"{rel}: type test_debt без `debt_kind` — указать категорию долга (B4)")
    return warns


def check_feature_ids(meta: dict, schema: dict, rel: str,
                       registry_ids: set[str] | None) -> tuple[list[str], list[str]]:
    """Кросс-файловая проверка (Z3/спека trace-matrix v2 §1b): test-case.features
    сверяется с docs/feature-registry.yaml. Неизвестный id — ERROR (кейс
    ссылается на фичу, которой нет в реестре — опечатка либо реестр не
    актуализирован). Отсутствующее/пустое `features` — тоже ERROR: error-flip
    выполнен 2026-07-17 после ПОЛНОГО backfill 65/65 (B2 спеки; до него было
    WARNING). Новый кейс обязан привязываться к реестру фич."""
    errors: list[str] = []
    warns: list[str] = []
    if schema.get("type") != "test-case":
        return errors, warns
    if registry_ids is None:
        warns.append(f"{rel}: docs/feature-registry.yaml не найден — `features` не проверены")
        return errors, warns
    features = meta.get("features")
    if features is None or features == "" or features == []:
        errors.append(f"{rel}: `features` отсутствует или пусто — кейс не привязан к реестру фич")
        return errors, warns
    if not isinstance(features, list):
        errors.append(f"{rel}: `features` должен быть списком id, получено {type(features).__name__}")
        return errors, warns
    for fid in features:
        if _s(fid) not in registry_ids:
            errors.append(f"{rel}: `features` содержит id `{_s(fid)}` ∉ docs/feature-registry.yaml")
    return errors, warns


def validate() -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warns: list[str] = []
    seen_ids: dict[str, str] = {}
    registry_ids = load_feature_registry()

    for area, itype in AREAS:
        base = REPO / area
        if not base.exists():
            continue
        schema = load_schema(itype)
        if not schema:
            warns.append(f"schemas/{itype}.schema.yaml не найдена — тип {itype} не проверен")
            continue
        # E4 (critic N3): charter'ы — ТОЛЬКО верхний уровень (не-рекурсивный
        # glob "*.md"), не rglob — exploratory-charters/attachments/ несёт
        # скриншоты/.xml дампы UI-дерева сессий exploratory-tester'а, это не
        # артефакты для валидации frontmatter. НЕ фильтр по имени "CH-*.md":
        # это исключило бы из скана charter с некорректным id/именем файла —
        # именно такой файл и должен долететь до id_pattern-проверки ниже
        # (эмпирически сломало test_charter_bad_id_pattern_is_error при
        # первой попытке). Точечное исключение для одной области — остальные
        # типы (test-cases/bugs/runs) сканируются как раньше, rglob'ом (у
        # них нет аналога attachments/).
        files = sorted(base.glob("*.md")) if itype == "charter" else sorted(base.rglob("*.md"))
        for md in files:
            # Служебные файлы области, не артефакты: README (все области),
            # PERTURBATIONS (библиотека возмущений charter-designer,
            # 2026-07-21) — без frontmatter намеренно.
            if md.name.upper() in ("README.MD", "PERTURBATIONS.MD"):
                continue
            rel = md.relative_to(REPO).as_posix()
            text = md.read_text(encoding="utf-8", errors="replace")
            meta, _body = bs._parse_frontmatter(text)
            if not meta:
                errors.append(f"{rel}: frontmatter отсутствует или не парсится")
                continue
            raw_fm = _frontmatter_raw(text)
            if raw_fm is not None:
                errors += check_duplicate_keys(raw_fm, rel)
            key = _s(meta.get("id"))
            if key:
                if key in seen_ids:
                    errors.append(f"{rel}: дубль id `{key}` (уже в {seen_ids[key]})")
                else:
                    seen_ids[key] = rel
            e, w = check_meta(meta, schema, rel)
            errors += e
            warns += w
            warns += check_cross_field_warn(meta, schema, rel)
            fe, fw = check_feature_ids(meta, schema, rel, registry_ids)
            errors += fe
            warns += fw
    return errors, warns


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Валидация frontmatter по schemas/")
    parser.add_argument("--no-warns", action="store_true", help="не печатать WARN")
    args = parser.parse_args(argv)

    errors, warns = validate()
    for e in errors:
        print(f"  [ERROR] {e}")
    if not args.no_warns:
        for w in warns:
            print(f"  [WARN] {w}")
    print(f"validate_frontmatter: ошибок {len(errors)}, предупреждений {len(warns)}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
