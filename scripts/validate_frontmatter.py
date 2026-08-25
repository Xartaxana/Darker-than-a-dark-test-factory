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
- поле не из схемы — [WARN], не ошибка (шаблоны эволюционируют);
- C1: title/H1 бага в терминальном статусе с додиагностическим маркером
  без снятия — [WARN] (state/escalations.md CLASS-MECHANISM-STALE-TEXT-
  AFTER-STATUS-TRANSITION);
- C3: state/app-under-test.yaml <-> runs/ — заявленный passed/failed без
  подтверждающего Closed-прогона того же suite/source_commit — [WARN];
- untracked test-case со status: Approved — [WARN]-информатор (гейт —
  scripts/new_case_status_gate.py, pre-commit).

Запуск: python scripts/validate_frontmatter.py
Коды выхода: 0 — чисто (WARN допустимы); 1 — есть ошибки (список в stdout).
"""
from __future__ import annotations

import argparse
import datetime
import re
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

import board_sync as bs
import sla_utils  # parse_ts — единый дом разбора ISO-штампа (Б10)

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
    errors += check_future_timestamps(meta, rel)
    return errors, warns


# --- AT-BUG-029 (2 инцидента 2026-08-11): будущий timestamp во frontmatter ---
# haiku-агенты фабриковали `updated` на +4..11ч в будущее (не сверяли настоящее
# время), валидатор молчал — поле проходило только pattern-проверку формата,
# не смысловую. `updated`/`status_since` — единственные поля, где frontmatter
# несёт ISO-таймстамп СОБЫТИЯ (не диапазон/оценку) во всех трёх схемах,
# парсящих их как дату (test-case/bug/run; charter incident-поля вне скоупа
# этой задачи).

FUTURE_TIMESTAMP_FIELDS = ("updated", "status_since")
# Допуск на clock skew между машиной агента и часами проверки (см. дисциплину
# команд CLAUDE.md п.6: env-негатив требует сверки, а не веры собственным часам).
FUTURE_TIMESTAMP_SLACK = datetime.timedelta(minutes=10)


def _parse_iso_dt(value) -> datetime.datetime | None:
    """ISO-таймстамп frontmatter → aware datetime (UTC). None — не парсится
    (форматную валидность уже проверяет `pattern` схемы отдельно; здесь только
    парсинг для сравнения с now(), тихий отказ — не ошибка этой функции).

    Б10 (критик-раунд 3, 2026-08-25): тело вынесено в ОБЩИЙ дом
    `sla_utils.parse_ts` — эта функция была независимой копией
    `sla_sweep._parse_ts`, а coverage_map вовсе сравнивал те же штампы
    СТРОКАМИ. Имя оставлено тонкой обёрткой (на него завязаны
    `check_future_timestamps` и `_run_date` этого модуля)."""
    return sla_utils.parse_ts(value)


def _fmt_delta(delta: datetime.timedelta) -> str:
    total = int(delta.total_seconds())
    m, s = divmod(total, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h{m:02d}m{s:02d}s"
    return f"{m}m{s:02d}s"


def check_future_timestamps(meta: dict, rel: str) -> list[str]:
    """`updated`/`status_since` строго в будущем (за вычетом допуска на clock
    skew, `FUTURE_TIMESTAMP_SLACK`) — ERROR: событие не могло ещё произойти."""
    errors: list[str] = []
    now = datetime.datetime.now(datetime.timezone.utc)
    threshold = now + FUTURE_TIMESTAMP_SLACK
    for name in FUTURE_TIMESTAMP_FIELDS:
        if name not in meta:
            continue
        dt = _parse_iso_dt(meta.get(name))
        if dt is None:
            continue
        if dt > threshold:
            delta = dt - now
            errors.append(
                f"{rel}: `{name}: {_s(meta[name])}` в будущем на +{_fmt_delta(delta)} "
                f"относительно now(UTC) (допуск {int(FUTURE_TIMESTAMP_SLACK.total_seconds() // 60)}м)")
    return errors


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
    # П1 Р0 п.1 (spec-p1-dedup v7): двустороннее правило Merged <-> merged_into.
    # Merged ⇒ automated_by пуст И automation_status пуст И merged_into непуст
    # (обратный путь automation-машины через retired НЕ используется для
    # поглощённых — второй, более прямой путь смерти автотеста, docs/03 §2);
    # merged_into непуст ⇒ status == Merged (иначе поле бессмысленно/протухло).
    if schema.get("type") == "test-case":
        status = _s(meta.get("status"))
        merged_into = _s(meta.get("merged_into")).strip()
        if status == "Merged":
            if _s(meta.get("automated_by")).strip():
                errors.append(
                    f"{rel}: `status: Merged` требует пустой `automated_by` "
                    f"(дубль-кейс поглощён journey — automated_by держит journey, не он)")
            if _s(meta.get("automation_status")).strip():
                errors.append(
                    f"{rel}: `status: Merged` требует пустой `automation_status` "
                    f"(обнуляется при слиянии — второй путь смерти автотеста мимо retired)")
            if not merged_into:
                errors.append(
                    f"{rel}: `status: Merged` требует непустой `merged_into` "
                    f"(TC-id кейса, поглотившего этот дубль)")
        if merged_into and status != "Merged":
            errors.append(
                f"{rel}: `merged_into: {merged_into}` требует `status: Merged` "
                f"(получено `{status}`)")
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


def check_merged_into_referential(tc_status_by_id: dict[str, str],
                                   merged_refs: list[tuple[str, str, str]]) -> list[str]:
    """Батч мелочей п.2: `merged_into` — WARN-ярус referential-проверка,
    ПОСЛЕ полного скана test-cases/ (цель может быть выше/ниже по файлам).
    Цель обязана существовать в test-cases/ И сама не быть `Merged` (цепочка
    Merged->Merged протухает — дубль слился на уже поглощённого дубля).
    `merged_refs`: (rel, own_id, target_id) для кейсов со `status: Merged`
    и непустым `merged_into` (ERROR-ярус check_cross_field уже гарантирует
    их совместность, здесь — только referential-часть по КАРТЕ всех id)."""
    warns: list[str] = []
    for rel, own_id, target_id in merged_refs:
        target_status = tc_status_by_id.get(target_id)
        if target_status is None:
            warns.append(
                f"{rel}: `merged_into: {target_id}` ссылается на несуществующий "
                f"test-case (цель не найдена в test-cases/)")
        elif target_status == "Merged":
            warns.append(
                f"{rel}: `merged_into: {target_id}` ссылается на кейс, который "
                f"сам `status: Merged` (цепочка слияний — цель протухла)")
    return warns


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
    # D14-Intended (ESC-029, решение Lead 2026-08-12): Intended-баг держит
    # known_issue "true" НАВСЕГДА — это единственный флаг, по которому D3
    # still-repro перепрогоняет регресс-замок ПРИНЯТОГО поведения на новых
    # сборках (P3-кейсы вроде TC-020 отсечены фильтром `(p0 or p1)` штатного
    # регресса). Сброс поля = молчаливое выключение единственного гарда;
    # правило fix-verifier «сбросить known_issue при Verified» к Intended не
    # применяется (перехода Intended->Verified в transitions.yaml нет).
    if "known_issue" in fields and _s(meta.get("status")) == "Intended" \
            and _s(meta.get("known_issue")) != "true":
        warns.append(
            f"{rel}: status Intended с known_issue `{_s(meta.get('known_issue'))}` — "
            "Intended держит known_issue \"true\" (гард D3 still-repro, ESC-029)")
    # Б6 (критик-раунд 2, каденция compatibility, 2026-08-25): поля, от которых
    # зависит зачёт каденции (sla_sweep._compatibility_run_wanted), молча
    # пустовали — ни схема, ни агент их не гарантировали. WARN ставит их на
    # путь исполнения (не ERROR — цель не ронять гейт, только не дать отчёту
    # уехать молча). suite/mode/device_avd — только для suite: compatibility
    # (на прочих suites device_avd/mode факультативны по схеме); штамп — для
    # ЛЮБОГО RUN (живой пример дефекта — RUN-20260814-0605, suite: canary,
    # без status_since/updated вовсе).
    if schema.get("type") == "run":
        suite = _s(meta.get("suite")).strip()
        if suite == "compatibility" and not _s(meta.get("device_avd")).strip():
            warns.append(
                f"{rel}: suite compatibility без `device_avd` — детектор каденции "
                f"(sla_sweep.compatibility_run_stale) не засчитает прогон")
        if suite == "compatibility" and _s(meta.get("mode")).strip() != "live":
            warns.append(
                f"{rel}: suite compatibility с `mode: {_s(meta.get('mode')).strip() or '?'}` "
                f"— каденция требует mode: live (replay/пусто не засчитывается)")
    # З8 (критик-раунд 3, 2026-08-25): проверка была УЖЕ класса, который сама
    # декларирует. Возраст артефакта читает `sla_sweep._since` (status_since,
    # фолбэк updated) — и он применяется НЕ только к прогонам: blocked_any
    # ловит ЛЮБОЙ тип в Blocked, severity-правила и question_unanswered —
    # баги, quarantine_expired — test-cases. Недатированный артефакт любого из
    # этих типов так же невидим для SLA-надзора, как недатированный прогон,
    # поэтому условие по типу снято.
    # ИСКЛЮЧЕНИЕ — `exploratory-charters`: их возраст считается ДРУГИМ путём
    # (charter_utils + поле `executed_at`, см. sla_sweep._charter_queue_wanted),
    # status_since/updated у них не заведены по построению — замер критика на
    # живом корпусе: 11 чартеров дали бы 11 ложных предупреждений (нарушителей
    # bugs 0, test-cases 0, runs 5).
    if schema.get("type") != "charter":
        if not _s(meta.get("status_since")).strip() and not _s(meta.get("updated")).strip():
            warns.append(
                f"{rel}: ни `status_since`, ни `updated` не заполнены — артефакт "
                f"недатирован, SLA-детекторы (sla_sweep._since) не смогут "
                f"определить его возраст")
    return warns


# --- C1 (spec-C-v2, state/escalations.md CLASS-MECHANISM-STALE-TEXT-AFTER-
# STATUS-TRANSITION, ~строка 2594): додиагностическая формулировка в
# title/H1 бага, дожившая до терминального статуса — WARN. Единственный
# вариант из трёх, рассмотренных планом и утверждённый критик-раундом
# Lead («словарь маркеров»); варианты «имя чужого статуса» и «чекбоксы»
# ОТКЛОНЕНЫ решением Lead — измеренная точность 0 (рецидив 6/AT-BUG-088:
# додиагностическая формулировка шла через ПРЕДИКАТ настоящего времени, не
# через слово чужого статуса/незакрытый чекбокс — см. запись эскалации
# «критик round1... N5»).
#
# ОХВАТ (намеренно узкий, докстринг обязателен по спеке): title/H1
# ТОЛЬКО. Секции тела («## Обнаружено» и т.п.), докстринги кода рядом с
# фиксом и свободнотекстовые frontmatter-поля (`last_seen_in`) — НЕ
# покрыты (рецидивы 7/8 эскалации жили именно там) — очередь Lead, не
# эта задача.
STALE_TEXT_MARKERS = (
    "слепы к",
    "не разделено",
    "читают через",
    "не решаю",
    "живой remnant",
)  # расширяемый словарь-константа — новые маркеры добавляются сюда по
   # мере находок (та же дисциплина, что STALE_TEXT_BASELINE ниже).
   # Критик-раунд C v2 восстановил полный словарь спеки (был молча сужен
   # до трёх маркеров в первой реализации — F-33/п.1 нарушение: спека НЕ
   # авторизовала сужение) и расширил «читают через голый» до «читают
   # через» (без сужения на слово «голый»): замер критика — полный
   # словарь по-прежнему даёт 0 срабатываний на живом корпусе.
# Спека C v2 называет три статуса буквально ("Fixed/Verified/Closed").
# "Closed" НЕ входит в enum machines.bug schemas/bug.schema.yaml (реальные
# статусы бага: Open/Reopened/Fixed/Verified/Rejected/Intended/Blocked) —
# для bugs/ это недостижимая ветка. Оставлена дословно по требованию
# спеки (расхождение спека/схема — см. отчёт задачи C v2, builder не
# сузил список без слова координатора).
STALE_TEXT_STATUSES = {"Fixed", "Verified", "Closed"}
# Критик-фикс C2-F2/F3: регистронезависимо (re.I — «были слепы к» строчными
# был ложным срабатыванием: исходный `БЫЛИ` матчил только заглавную форму),
# расширенный словарь снятия («был»/«была»/«было»/«были» одним классом
# `был[аои]?`, плюс «устранено»/«исправлено»/«пофикшено»). Голая дата БЕЗ
# слова снятия УБРАНА как самостоятельный квалификатор (C2-F3, «дата в
# поле — не снятие»): слова снято/закрыто уже матчатся регистронезависимо
# И БЕЗ требования даты рядом — добавлять отдельную ветку «дата рядом со
# СНЯТО/ЗАКРЫТО» было бы функционально недостижимо (словесная ветка уже
# покрывает любой текст с этими словами независимо от даты), поэтому
# сужение реализовано как ПОЛНОЕ удаление голой даты из альтернатив, а не
# как избыточная date-proximity-ветка. `\b`-границы вокруг альтернатив:
# без них короткое «был» матчилось бы ВНУТРИ несвязанных слов (например
# «приБЫЛ», «заБЫЛа») — то самое ложное срабатывание, которого правило
# обязано избегать (builder-находка при доработке, до коммита).
_STALE_TEXT_CLEAR_RE = re.compile(
    r"\b(?:снято|закрыто|был[аои]?|устранено|исправлено|пофикшено)\b",
    re.IGNORECASE,
)
_H1_RE = re.compile(r"(?m)^#\s+(.+)$")

# Бейзлайн-вердикт (образец scripts/dedup_check.py:72-90 BASELINE): ключ
# несёт НОРМАЛИЗОВАННЫЙ ФРАГМЕНТ текста (не только файл) — переписанный
# заголовок того же файла на НОВУЮ формулировку обязан зажечься заново,
# а не молчать под старой записью (AT-BUG-087 рецидивировал так 3 раза,
# AT-BUG-088 — 2, см. эскалацию). На момент задачи корпус/git-история не
# содержат ни одного истинного экземпляра (все чинились ДО коммита) —
# словарь пуст; легитимные исключения (если найдутся) добавляются сюда
# вердиктом, как в dedup_check.BASELINE.
STALE_TEXT_BASELINE: dict[tuple[str, str, str], str] = {}


def _stale_text_normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())


def check_stale_text(meta: dict, schema: dict, body: str, rel: str) -> list[str]:
    """C1: title/H1 бага в терминальном статусе несёт додиагностическую
    формулировку БЕЗ соседнего маркера снятия (снято/закрыто/был|-а|-о|-и/
    устранено/исправлено/пофикшено, регистронезависимо) В ТОЙ ЖЕ строке/
    заголовке — квалификатор снятия обязателен как часть правила, снятие
    в другом месте файла не считается. Голая дата БЕЗ слова снятия — НЕ
    квалификатор (C2-F3)."""
    if schema.get("type") != "bug":
        return []
    status = _s(meta.get("status"))
    if status not in STALE_TEXT_STATUSES:
        return []
    warns: list[str] = []
    h1_match = _H1_RE.search(body)
    fields = (
        ("title", _s(meta.get("title"))),
        ("H1", h1_match.group(1) if h1_match else ""),
    )
    for label, text in fields:
        if not text or _STALE_TEXT_CLEAR_RE.search(text):
            continue
        for marker in STALE_TEXT_MARKERS:
            if marker not in text:
                continue
            key = (rel, "stale_text", _stale_text_normalize(text))
            if key in STALE_TEXT_BASELINE:
                break
            warns.append(
                f"{rel}: `{label}` несёт додиагностический маркер `{marker}` при "
                f"status `{status}` без соседнего маркера снятия (снято/закрыто/"
                f"был-а-о-и/устранено/исправлено/пофикшено) — возможен stale-text "
                f"рецидив (state/escalations.md "
                f"CLASS-MECHANISM-STALE-TEXT-AFTER-STATUS-TRANSITION): `{text}`")
            break
    return warns


# --- П1 Р3 (spec-p1-dedup v7): машинный детектор проб на journey-чекпойнты ---
#
# Машинная форма (r3/r4, Н1 критик-диффа: ПРЕФИКС-матч обоих заголовков —
# симметрия; суффиксы вида «(journey)» не выключают гейт молча): чекпойнты —
# пункты НУМЕРОВАННОГО списка раздела `## Чекпойнты*`; записи проб — строки,
# начинающиеся `- проба:`, в разделе, чей заголовок начинается С ПРЕФИКСА
# `## Красная проба` (существующие 16 секций несут суффикс «(red_probe,
# ретрофит — …)» — прочный матч только по префиксу). Раздел = от заголовка до
# СЛЕДУЮЩЕГО `## ` или до конца файла. Статус-гард: ERROR только при
# `status: Automated` (до Automated пробы ещё не ставились — F1 впереди,
# правило молчит на Review/Approved).
_CHECKPOINTS_HEADER_RE = re.compile(r"(?m)^## Чекпойнты")
_RED_PROBE_HEADER_RE = re.compile(r"(?m)^## Красная проба")
_NEXT_H2_RE = re.compile(r"(?m)^## ")
_NUMBERED_ITEM_RE = re.compile(r"(?m)^[ \t]*\d+[.)][ \t]+\S")
_PROBE_LINE_RE = re.compile(r"(?m)^-[ \t]*проба:")


def _section_body(body: str, header_re: re.Pattern) -> str | None:
    """Текст секции ПОСЛЕ заголовка (по header_re) до следующего `## ` (или EOF).
    None — секция отсутствует."""
    m = header_re.search(body)
    if m is None:
        return None
    start = m.end()
    nxt = _NEXT_H2_RE.search(body, start)
    return body[start:nxt.start() if nxt else len(body)]


def check_checkpoint_probes(meta: dict, schema: dict, body: str, rel: str) -> list[str]:
    """Journey-TC (П1 Р1): у `status: Automated` число `- проба:` в разделе
    `## Красная проба*` обязано быть >= числу пунктов раздела `## Чекпойнты*`
    (проба на КАЖДЫЙ чекпойнт). Кейс без раздела `## Чекпойнты` — не journey,
    правило не применяется. Н1 критик-диффа: секция ЕСТЬ, но нумерованных
    пунктов 0 — гейт не выключается молча, а даёт ERROR (fail-closed:
    защита объявлена тотальной — реализована тотальной)."""
    if schema.get("type") != "test-case":
        return []
    if _s(meta.get("status")) != "Automated":
        return []
    section = _section_body(body, _CHECKPOINTS_HEADER_RE)
    if section is None:
        return []
    checkpoints = len(_NUMBERED_ITEM_RE.findall(section))
    if checkpoints == 0:
        return [
            f"{rel}: раздел «## Чекпойнты» есть, но нумерованных пунктов 0 — "
            "битая форма journey-кейса (нумерованный список обязателен, П1 Р3; "
            "гейт fail-closed)"
        ]
    probe_section = _section_body(body, _RED_PROBE_HEADER_RE)
    probes = len(_PROBE_LINE_RE.findall(probe_section)) if probe_section else 0
    if probes < checkpoints:
        return [
            f"{rel}: раздел «## Чекпойнты» несёт {checkpoints} пункт(ов), а «## "
            f"Красная проба…» — только {probes} строк(и) «- проба:» (Automated "
            f"требует пробу на КАЖДЫЙ чекпойнт, П1 Р3)"
        ]
    return []


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


# --- C3 (spec-C-v2, ESC APP-UNDER-TEST-YAML-COHERENCE-GATE): когерентность
# state/app-under-test.yaml <-> runs/. Мотив — блокер прошёл мимо ВСЕХ
# преflight-гейтов и был пойман только человеком (критик-вход
# critic-review-build-fdd3f728): smoke_status/regression_status оставлены
# not_run при существующем Closed зелёном прогоне того же source_commit.
#
# Цена (критик замерил 2.5s на прогон validate_frontmatter): НИКАКИХ
# git-вызовов внутри цикла по файлам — (source_commit, suite, status,
# updated) собираются ОДНИМ проходом по runs/ основного цикла validate()
# (см. `run_records` в validate()), не вторым rglob.
#
# C2-B2 (критик-раунд): canary_status ИСКЛЮЧЁН из source_commit-оракула
# ниже (`_confirm_by_commit`) — структурная причина, не вкусовщина.
# `grep smoke_status\|regression_status\|canary_status
# scripts/build_watch.py` даёт 4 совпадения, ВСЕ на smoke/regression
# (`_rewrite_field(text, "smoke_status", "not_run")` /
# `_rewrite_field(text, "regression_status", "not_run")`,
# build_watch.py:435-436 и :849-850) — 0 совпадений на canary_status:
# новая сборка (смена source_commit) НЕ сбрасывает canary_status вовсе,
# он живёт по своей каденции (проверка внешнего live-сайта, не билда).
# Git-история (12 коммитов app-under-test.yaml) подтверждает: canary_status
# пережил 8 смен source_commit без изменений. Оракул «тот же
# source_commit» на canary систематически горел бы на КАЖДОЙ новой
# сборке НАВСЕГДА (structural false positive, не единичный случай) —
# вместо него для canary отдельный оракул СВЕЖЕСТИ
# (`_check_canary_freshness`): WARN, если новейший Closed canary-прогон
# старше `CANARY_FRESHNESS_DAYS`.
COMMIT_MATCHED_SUITES = ("smoke", "regression")  # canary — freshness-оракул, не commit-оракул
# Порог по каденции canary в rules.yaml — уточняется по evidence (пока нет
# отдельного SLA-поля под canary; 14д — консервативная стартовая оценка,
# критик-раунд C v2).
CANARY_FRESHNESS_DAYS = 14
# C2-F5 (критик-раунд): короче 7 символов — не хэш-префикс, а шум
# (случайное совпадение первых N символов двух разных коммитов на таком
# коротком префиксе статистически вероятно; git по умолчанию печатает
# короткие SHA от 7 символов — та же граница).
MIN_COMMIT_PREFIX_LEN = 7


def _strip_yaml_comment(value: str) -> str:
    """Хвостовой `# ...` комментарий. PyYAML сам режет комментарий из
    НЕкавыченного скаляра при штатном `safe_load` (проверено эмпирически:
    `source_commit: fdd3f728... # 2026-06-28` парсится в чистую строку без
    хвоста) — эта функция только страхует форму значения на входе, лишней
    не будет."""
    return value.split("#", 1)[0].strip()


def _commit_prefix_match(a: str, b: str) -> bool:
    """Полный/короткий хэш коммита — совпадение по ПРЕФИКСУ (короче —
    префикс длиннее), регистронезависимо. Пустая строка ни с чем не
    матчится. C2-F5: короче `MIN_COMMIT_PREFIX_LEN` (7) — тоже НЕ матч
    (подозрительно короткий префикс, WARN о нём — на вызывающей стороне,
    см. `check_aut_runs_coherence`)."""
    a = a.strip().lower()
    b = b.strip().lower()
    if not a or not b:
        return False
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    if len(shorter) < MIN_COMMIT_PREFIX_LEN:
        return False
    return longer.startswith(shorter)


def load_app_under_test() -> dict | None:
    """None — файла нет (репозиторий без построенного билда — не пробел
    этой задачи) ИЛИ YAML не парсится (fail-quiet, битый файл ловится
    другими механизмами, не этим WARN-правилом)."""
    p = REPO / "state" / "app-under-test.yaml"
    if not p.exists():
        return None
    import yaml
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None
    return data or {}


# `updated`/`status_since` НЕ в `required` схемы run (schemas/run.schema.yaml)
# — легаси-прогоны до 2026-08-10ish (в т.ч. позитивный контроль
# RUN-20260814-0605, канарейка) физически не несут этих полей (эмпирически
# проверено на живом репо: 0 полей `updated`/`status_since` в этом файле).
# Единственное ВСЕГДА присутствующее машинно-читаемое время — сам id
# (`RUN-YYYYMMDD-HHMM`, конвенция имени, required-поле схемы) — фолбэк.
_RUN_ID_DATE_RE = re.compile(r"^RUN-(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})$")


def _run_date(run_id, updated_raw) -> datetime.datetime | None:
    """`updated` если парсится (свежее/точное), иначе дата из id-конвенции
    `RUN-YYYYMMDD-HHMM` (легаси-прогоны без `updated` — большинство canary-
    прогонов на момент задачи)."""
    dt = _parse_iso_dt(updated_raw)
    if dt is not None:
        return dt
    m = _RUN_ID_DATE_RE.match(_s(run_id))
    if not m:
        return None
    y, mo, d, h, mi = (int(g) for g in m.groups())
    try:
        return datetime.datetime(y, mo, d, h, mi, tzinfo=datetime.timezone.utc)
    except ValueError:
        return None


def _check_canary_freshness(run_records: list[tuple], claimed: str) -> list[str]:
    """C2-B2: canary не привязан к source_commit (см. докстринг блока выше)
    — вместо commit-матча оракул СВЕЖЕСТИ: берём самый свежий `updated`
    (фолбэк — дата из id) среди Closed canary-прогонов, WARN если старше
    `CANARY_FRESHNESS_DAYS` либо такого прогона нет вовсе (0 Closed
    canary-записей с распознанной датой — тоже недоказанная свежесть)."""
    now = datetime.datetime.now(datetime.timezone.utc)
    newest: datetime.datetime | None = None
    for (_r_commit, r_suite, r_status, r_updated, r_id) in run_records:
        if _s(r_suite) != "canary" or _s(r_status) != "Closed":
            continue
        dt = _run_date(r_id, r_updated)
        if dt is None:
            continue
        if newest is None or dt > newest:
            newest = dt
    if newest is None:
        return [
            f"state/app-under-test.yaml: `canary_status: {claimed}` — ни один "
            f"Closed canary-прогон в runs/ не несёт распознаваемой даты "
            f"`updated` — свежесть не подтверждена (когерентность AUT<->runs, "
            f"ESC APP-UNDER-TEST-YAML-COHERENCE-GATE)"]
    age_days = (now - newest).days
    if age_days > CANARY_FRESHNESS_DAYS:
        return [
            f"state/app-under-test.yaml: `canary_status: {claimed}` — новейший "
            f"Closed canary-прогон ({newest.date().isoformat()}) старше "
            f"{CANARY_FRESHNESS_DAYS}д (возраст {age_days}д) — свежесть не "
            f"подтверждена (когерентность AUT<->runs, ESC "
            f"APP-UNDER-TEST-YAML-COHERENCE-GATE)"]
    return []


def check_aut_runs_coherence(run_records: list[tuple]) -> list[str]:
    """smoke_status/regression_status/canary_status app-under-test.yaml
    заявляют passed/failed. smoke/regression обязаны иметь подтверждающий
    Closed-прогон СВОЕГО suite с ТЕМ ЖЕ source_commit (полный/короткий
    хэш — сравнение по префиксу, минимум `MIN_COMMIT_PREFIX_LEN` символов);
    canary сверяется ОТДЕЛЬНЫМ оракулом свежести (`_check_canary_freshness`,
    C2-B2 — canary НЕ привязан к source_commit структурно, см. докстринг
    блока выше). `run_records`: (source_commit, suite, status, updated, id)
    каждого run-файла, собранные ОДНИМ проходом validate() по runs/
    (включая записи БЕЗ source_commit — передаются как None/пустая строка
    и естественно не матчатся ни с чем, это и есть требуемое «пропускать
    явно, не считать совпавшими» — 8 таких прогонов в корпусе на момент
    задачи).

    `not_run`/отсутствующее значение поля — нечего сверять, не WARN."""
    aut = load_app_under_test()
    if not aut:
        return []

    warns: list[str] = []
    canary_claimed = _s(aut.get("canary_status")).strip()
    if canary_claimed in ("passed", "failed"):
        warns += _check_canary_freshness(run_records, canary_claimed)

    aut_commit_raw = aut.get("source_commit")
    if aut_commit_raw is None:
        return warns
    aut_commit = _strip_yaml_comment(str(aut_commit_raw))
    if not aut_commit:
        return warns
    if len(aut_commit) < MIN_COMMIT_PREFIX_LEN:
        warns.append(
            f"state/app-under-test.yaml: `source_commit: {aut_commit}` короче "
            f"{MIN_COMMIT_PREFIX_LEN} символов — подозрительно короткий хэш, "
            f"C3-сверка по префиксу для smoke/regression пропущена (ложные "
            f"совпадения на слишком коротком префиксе)")
        return warns

    for suite in COMMIT_MATCHED_SUITES:
        field = f"{suite}_status"
        claimed = _s(aut.get(field)).strip()
        if claimed not in ("passed", "failed"):
            continue
        confirmed = any(
            _s(r_suite) == suite and _s(r_status) == "Closed" and r_commit
            and _commit_prefix_match(aut_commit, str(r_commit))
            for (r_commit, r_suite, r_status, _r_updated, _r_id) in run_records
        )
        if not confirmed:
            warns.append(
                f"state/app-under-test.yaml: `{field}: {claimed}` для source_commit "
                f"`{aut_commit}` не подтверждён Closed-прогоном suite={suite} с тем же "
                f"source_commit в runs/ (когерентность AUT<->runs, ESC "
                f"APP-UNDER-TEST-YAML-COHERENCE-GATE)")
    return warns


# --- Батч C v2 (критик C-B5): validate_frontmatter НЕ становится вторым
# гейтом на нелегальную инициализацию статуса (то окно закрыто
# new_case_status_gate.py в pre-commit) — здесь только WARN-информатор
# для файла, который на диске уже несёт status: Approved, но ЕЩЁ НЕ
# закоммичен (untracked/новый) — pre-commit-гейт его пока физически не
# видел. Один git-вызов (`ls-tree`), деградация отказа git — в тишину
# (вторичный информатор, основной гейт живёт в pre-commit).
def check_untracked_approved_test_cases() -> list[str]:
    base = REPO / "test-cases"
    if not base.exists():
        return []
    try:
        proc = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", "HEAD", "--", "test-cases"],
            cwd=REPO, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=10,
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        return []
    if proc.returncode != 0:
        return []
    tracked = set(proc.stdout.splitlines())

    warns: list[str] = []
    for md in sorted(base.rglob("*.md")):
        rel = md.relative_to(REPO).as_posix()
        if rel in tracked:
            continue
        text = md.read_text(encoding="utf-8", errors="replace")
        meta, _body = bs._parse_frontmatter(text)
        if not meta:
            continue
        if _s(meta.get("status")) == "Approved":
            warns.append(
                f"{rel}: untracked test-case со status: Approved — нелегальная "
                f"инициализация статуса (гейт — pre-commit, "
                f"scripts/new_case_status_gate.py)")
    return warns


def validate() -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warns: list[str] = []
    seen_ids: dict[str, str] = {}
    registry_ids = load_feature_registry()
    # Батч мелочей п.2: карта id->status test-case'ов + список merged_into-ссылок,
    # собираются в основном проходе, referential-проверка — постфактум (цель
    # может физически идти позже ссылающегося файла в порядке скана).
    tc_status_by_id: dict[str, str] = {}
    merged_refs: list[tuple[str, str, str]] = []
    # C3: (source_commit, suite, status, updated, id) каждого run-файла —
    # ОДИН проход (этот же основной цикл), не второй rglob по runs/.
    run_records: list[tuple] = []

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
            # Отчёт репетиции тёмного дня и его вложения (runs/REHEARSAL-*,
            # спека docs/11 §5) — свободная форма, НЕ RUN-артефакт конвейера:
            # frontmatter не требуется намеренно. Узкое исключение только
            # области runs (шов вскрыт preflight'ом /qa-loop 2026-08-04:
            # спека кладёт отчёт в runs/, схема требует run-frontmatter).
            if itype == "run" and (md.name.upper().startswith("REHEARSAL-")
                                   or md.parent.name.upper().startswith("REHEARSAL-")):
                continue
            # Протоколы узлов программы П3 (runs/N<n>-p3-*.md, DAG
            # docs/tasks/p3-second-emulator.md) — тот же класс, что
            # REHEARSAL-*: свободная форма эмпирической пробы, НЕ
            # RUN-артефакт конвейера (нет suite/totals — принуждение к
            # run-схеме дало бы фиктивные значения). Решение Lead
            # 2026-08-20 (эскалация RUNS-N0-P3-MISSING-FRONTMATTER);
            # первый экземпляр — N0-p3-two-device-probe-2026-08-20.md
            # (коммит 380fb637). Узость паттерна намеренна (D-0063).
            if itype == "run" and re.match(r"(?i)N\d+-p3-", md.name):
                continue
            rel = md.relative_to(REPO).as_posix()
            text = md.read_text(encoding="utf-8", errors="replace")
            meta, body = bs._parse_frontmatter(text)
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
            if itype == "test-case" and key:
                tc_status_by_id[key] = _s(meta.get("status"))
                merged_into_val = _s(meta.get("merged_into")).strip()
                if _s(meta.get("status")) == "Merged" and merged_into_val:
                    merged_refs.append((rel, key, merged_into_val))
            e, w = check_meta(meta, schema, rel)
            errors += e
            warns += w
            errors += check_checkpoint_probes(meta, schema, body, rel)
            warns += check_cross_field_warn(meta, schema, rel)
            warns += check_stale_text(meta, schema, body, rel)
            fe, fw = check_feature_ids(meta, schema, rel, registry_ids)
            errors += fe
            warns += fw
            if itype == "run":
                run_records.append((meta.get("source_commit"), meta.get("suite"),
                                     _s(meta.get("status")), meta.get("updated"),
                                     meta.get("id")))
    warns += check_merged_into_referential(tc_status_by_id, merged_refs)
    warns += check_aut_runs_coherence(run_records)
    warns += check_untracked_approved_test_cases()
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
