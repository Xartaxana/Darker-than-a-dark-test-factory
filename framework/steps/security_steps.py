"""Бизнес-шаги области security (test-cases/security/, TC-100..105,
docs/01-test-strategy.md §9 «security/privacy smoke, E4→минимальный»).

Статическая часть (TC-100/101/104-static) — манифест-инспекция через
`framework/core/manifest.py` (`aapt dump xmltree`, misc-batch-0722, замечание
critic прохода (5) — НЕ `dumpsys package`, атрибуты exported/cleartextTraffic/
fullBackupContent там неполны/косвенны). Build-level факты, не требуют
Appium-сессии/устройства.

Поведенческая часть (TC-102/104-behavioral/105) — обычные Appium/adb примитивы,
композиция уже существующей инфраструктуры (`core/contexts`, `core/adb`).

E4-min — smoke, не полный аудит (§8): часть Then-проверок здесь ФИКСИРУЕТ факт
(через `allure.attach`), не выносит вердикт «баг»/«не баг» — это осознанное
решение дизайна кейсов TC-101/TC-102, не недосмотр автоматизации.
"""
from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path

import allure

from framework.config import settings
from framework.core import adb, contexts, manifest

_MAIN_ACTIVITY = f"{settings.APP_PACKAGE}.MainActivity"
_TRUSTED_HOST = "archiveofourown.org"


def _bool_attr(value: str | None) -> bool | None:
    """`aapt` типизированные boolean-атрибуты приходят как hex: `0xffffffff` (true)
    или `0x0` (false) — см. `manifest._parse_attr_value`."""
    if value is None:
        return None
    return value.lower() not in ("0x0", "0", "false")


# --- Дерево манифеста (общая точка входа для TC-100/101/104-static) ---

@allure.step("When манифест инспектируется статически (aapt dump xmltree AndroidManifest.xml)")
def dump_manifest_tree() -> manifest.Node:
    return manifest.parse_xmltree(manifest.dump_xmltree())


def _application_node(tree: manifest.Node) -> manifest.Node:
    apps = manifest.find_all(tree, "application")
    assert apps, "манифест не содержит <application>"
    return apps[0]


def _main_activity_node(tree: manifest.Node, activity: str = _MAIN_ACTIVITY) -> manifest.Node:
    for act in manifest.find_all(tree, "activity"):
        if act.attrs.get("android:name") == activity:
            return act
    raise AssertionError(f"<activity> {activity} не найдена в манифесте")


def _target_sdk_version(tree: manifest.Node) -> int:
    nodes = manifest.find_all(tree, "uses-sdk")
    assert nodes, "манифест не содержит <uses-sdk>"
    raw = nodes[0].attrs.get("android:targetSdkVersion")
    assert raw, "<uses-sdk> не содержит android:targetSdkVersion"
    return int(raw, 16) if raw.startswith("0x") else int(raw)


def _intent_filter_facts(intent_filter_node: manifest.Node) -> dict:
    actions = {a.attrs.get("android:name") for a in manifest.find_all(intent_filter_node, "action")}
    categories = {c.attrs.get("android:name") for c in manifest.find_all(intent_filter_node, "category")}
    datas = [
        (d.attrs.get("android:scheme"), d.attrs.get("android:host"))
        for d in manifest.find_all(intent_filter_node, "data")
    ]
    return {"actions": actions, "categories": categories, "datas": datas}


# --- TC-100: exported + VIEW/BROWSABLE intent-filter ---

@allure.step("Then {activity} отмечена exported=true с intent-filter VIEW/DEFAULT/BROWSABLE на {host}")
def assert_main_activity_exported_with_view_intent_filter(
    tree: manifest.Node, activity: str = _MAIN_ACTIVITY, host: str = _TRUSTED_HOST,
) -> list[dict]:
    act = _main_activity_node(tree, activity)
    exported = _bool_attr(act.attrs.get("android:exported"))
    assert exported is True, (
        f"{activity}: android:exported ожидался true, факт: {act.attrs.get('android:exported')!r}"
    )
    required_categories = {"android.intent.category.DEFAULT", "android.intent.category.BROWSABLE"}
    matching = []
    for f in manifest.find_all(act, "intent-filter"):
        facts = _intent_filter_facts(f)
        if (
            "android.intent.action.VIEW" in facts["actions"]
            and required_categories <= facts["categories"]
            and any(scheme in ("http", "https") and h == host for scheme, h in facts["datas"])
        ):
            matching.append(facts)
    assert matching, (
        f"{activity}: не найден intent-filter c action.VIEW + categories DEFAULT/BROWSABLE + "
        f"data scheme http/https host={host} среди intent-filter'ов активности"
    )
    return matching


# --- TC-101: cleartext-трафик, сверка с http-схемой TC-100 ---

@allure.step("Then эффективная политика cleartext-трафика зафиксирована как факт и сверена с http-схемой intent-filter (TC-100)")
def assert_cleartext_policy_documented(tree: manifest.Node, http_scheme_present: bool) -> dict:
    app = _application_node(tree)
    raw = app.attrs.get("android:usesCleartextTraffic")
    nsc_ref = app.attrs.get("android:networkSecurityConfig")
    if raw is not None:
        effective: bool | None = _bool_attr(raw)
        source = f"явный android:usesCleartextTraffic={raw!r} (<application>)"
    elif nsc_ref is not None:
        # Содержимое network-security-config НЕ читается этим E4-min кейсом
        # (testability gap §9) — присутствие ресурса фиксируется как факт.
        effective = None
        source = (
            f"android:networkSecurityConfig={nsc_ref!r} присутствует — содержимое не "
            f"читается этим кейсом (testability gap §9)"
        )
    else:
        target_sdk = _target_sdk_version(tree)
        effective = target_sdk < 28
        source = f"атрибут отсутствует, вычислено по умолчанию: targetSdkVersion={target_sdk} -> {effective}"
    allure.attach(
        source, name="cleartext-traffic-policy-source",
        attachment_type=allure.attachment_type.TEXT,
    )
    assert raw is not None or nsc_ref is not None or effective is not None, (
        "не удалось зафиксировать политику cleartext-трафика ни одним из трёх источников "
        "(usesCleartextTraffic / networkSecurityConfig / targetSdkVersion default)"
    )
    if effective is False and http_scheme_present:
        allure.attach(
            "intent-filter рекламирует http://archiveofourown.org (зафиксировано TC-100), "
            "но эффективная политика cleartext-трафика зафиксирована как false — расхождение "
            "зафиксировано как наблюдение для триажа, не вердикт (E4-min не выносит "
            "«баг»/«не баг», §8)",
            name="cleartext-vs-intent-filter-observation",
            attachment_type=allure.attachment_type.TEXT,
        )
    return {"effective": effective, "source": source, "networkSecurityConfig_present": nsc_ref is not None}


# --- TC-104 (static half): allowBackup сопровождён явным ограничением области ---

@allure.step("Then android:allowBackup=true сопровождён явным ограничивающим механизмом (fullBackupContent/dataExtractionRules)")
def assert_backup_scope_declared(tree: manifest.Node) -> dict:
    app = _application_node(tree)
    allow_backup = _bool_attr(app.attrs.get("android:allowBackup"))
    assert allow_backup is True, (
        f"android:allowBackup ожидался true, факт: {app.attrs.get('android:allowBackup')!r}"
    )
    has_full_backup_content = "android:fullBackupContent" in app.attrs
    has_data_extraction_rules = "android:dataExtractionRules" in app.attrs
    assert has_full_backup_content or has_data_extraction_rules, (
        "android:allowBackup=true без android:fullBackupContent И без "
        "android:dataExtractionRules — область бэкапа не ограничена явно"
    )
    return {
        "fullBackupContent": has_full_backup_content,
        "dataExtractionRules": has_data_extraction_rules,
    }


# --- TC-102: JS-bridge (window.Android) exposure — доверенный origin vs не-AO3 ---

@allure.step("When в WebView-контексте активной вкладки выполнена JS-проба `typeof window.Android`")
def probe_window_android(driver) -> str:
    with contexts.in_webview(driver):
        return driver.execute_script("return typeof window.Android;")


@allure.step("Then window.Android доступен на доверенном AO3-origin (typeof !== 'undefined')")
def assert_js_bridge_available(driver) -> str:
    result = probe_window_android(driver)
    assert result != "undefined", (
        f"typeof window.Android == {result!r} на доверенном AO3-origin — ожидали доступный "
        f"нативный @JavascriptInterface bridge (штатная функциональная интеграция)"
    )
    return result


@allure.step("Then доступность window.Android на {context_label} зафиксирована как наблюдаемый факт (не вердикт, E4-min)")
def record_js_bridge_observation(driver, context_label: str) -> str:
    result = probe_window_android(driver)
    allure.attach(
        f"typeof window.Android на {context_label}: {result!r}",
        name=f"js-bridge-observation-{context_label}",
        attachment_type=allure.attachment_type.TEXT,
    )
    assert result in ("object", "function", "undefined"), (
        f"typeof window.Android вернул значение вне ожидаемого набора typeof JS: {result!r} "
        f"(проба, похоже, не выполнилась корректно)"
    )
    return result


# --- TC-104 (behavioral half): права SAF-экспортного файла ---

def _permission_string(ls_output: str) -> str:
    for line in ls_output.strip().splitlines():
        parts = line.split()
        if parts:
            return parts[0]
    raise AssertionError(f"'ls -l' вернул пустой вывод: {ls_output!r}")


@allure.step("Then права экспортного SAF-файла {exported_filename} не шире прав контрольного файла в той же директории")
def assert_saf_export_permissions_not_widened(
    remote_dir: str, exported_filename: str, control_filename: str = "tc104_perm_control.txt",
) -> dict:
    """Сверяет права экспортного файла (`ls -l`, первое поле) с КОНТРОЛЬНЫМ файлом,
    положенным этой же функцией в ТУ ЖЕ директорию тем же путём (`adb push`, как и
    остальные файлы фреймворка в `/sdcard/Download`) — не абсолютный хардкод ожидаемой
    permission-строки (FUSE-эмуляция `/sdcard` может представлять её нестандартно), а
    относительное «не шире дефолта места», как сформулировано в Then кейса."""
    control_path = f"{remote_dir}/{control_filename}"
    tmp_dir = Path(tempfile.mkdtemp(prefix="tc104_perm_"))
    try:
        local = tmp_dir / control_filename
        local.write_text("tc104 permission control file\n", encoding="utf-8")
        adb.push_external(local, control_path)
        control_perm = _permission_string(adb.shell(f"ls -l '{control_path}'"))
        export_perm = _permission_string(adb.shell(f"ls -l '{remote_dir}/{exported_filename}'"))
    finally:
        adb.shell(f"rm -f '{control_path}'")
        shutil.rmtree(tmp_dir, ignore_errors=True)
    allure.attach(
        f"control={control_perm!r} export={export_perm!r}",
        name="saf-export-file-permissions",
        attachment_type=allure.attachment_type.TEXT,
    )
    assert export_perm == control_perm, (
        f"права экспортного файла ({export_perm}) отличаются от контрольного файла, "
        f"положенного в ту же директорию ({control_perm}) — приложение могло вручную "
        f"расширить права экспортного файла сверх дефолта места"
    )
    return {"control": control_perm, "export": export_perm}


# --- TC-105: скан logcat на утечку чувствительных данных при smoke ---

_SENSITIVE_PATTERNS = ("Cookie:", "Set-Cookie:", "session_id=", "token=", "Authorization:")
_INTERNAL_PATH_PATTERNS = (
    f"/data/data/{settings.APP_PACKAGE}/",
    f"/data/user/0/{settings.APP_PACKAGE}/",
)

# Калибровка на живом прогоне (misc-batch-0722, emulator-5554, 2026-07-22) —
# полнотекстовый скан ВСЕГО буфера ловил два класса штатного системного шума,
# не прикладной утечки:
# 1. `token=` совпадал со строками WindowManager/WindowManagerShell ДРУГОГО
#    процесса (`system_server`, PID != PID приложения) — `Transition requested:
#    ... token=WCT{...}` (Android WindowContainerToken, не сессионный токен) —
#    закрыто скоупингом по PID приложения (`--pid=<pid>`, `adb logcat` уже
#    поддерживает нативно, тот же примитив `adb.shell`, доп. инфраструктуры не
#    требует).
# 2. Даже В ПРЕДЕЛАХ PID приложения `/data/user/0/<pkg>/...` совпадал с ДВУМЯ
#    отдельными Chromium/WebView-внутренними тегами (не код приложения — см.
#    `Log.d(TAG, ...)` в app-under-test: единственные прикладные теги
#    `DownloadRepo`/`Converters`, ни один из них не совпадает ни с одним
#    исключённым ниже):
#    (a) `cr_VariationsUtils: Failed reading seed file
#        "/data/user/0/<pkg>/app_webview/variations_seed..."` — тег с префиксом
#        `cr_`, стандартная конвенция Chromium-логов, про СОБСТВЕННЫЙ служебный
#        файл WebView (variations seed — публичная A/B-конфигурация Chromium,
#        не пользовательские данные);
#    (b) `chromium: [ERROR:simple_file_enumerator.cc(21)] opendir
#        /data/user/0/<pkg>/cache/WebView/Default/HTTP Cache/Code Cache/...:
#        No such file or directory` — тег буквально `chromium` (другая
#        конвенция того же движка — сырой C++ `LOG(ERROR)`, перенаправленный
#        в logcat), тоже про СОБСТВЕННУЮ кэш-директорию WebView (HTTP Cache/
#        Code Cache — служебный дисковый кэш браузерного движка), не
#        пользовательские данные.
# Решение операционализации (test-automator, задокументировано в TC-105.md):
# сузить матчер до строк {PID приложения} \ {Chromium-внутренние теги: префикс
# `cr_` ИЛИ буквально `chromium`} вместо полнотекстового скана всего буфера —
# все найденные классы шума были системными (движок WebView про себя же), не
# прикладными; список sensitive-паттернов не сужен (testability gap остаётся
# на классе «неотличимая прикладная утечка под тегом приложения», не на
# конкретных паттернах).
_CHROMIUM_INTERNAL_TAG_PREFIX = "cr_"
_CHROMIUM_INTERNAL_TAGS = frozenset({"chromium"})
_LOGCAT_LINE_RE = re.compile(r"^\S+\s+\S+\s+(\d+)\s+(\d+)\s+\S\s+([^:]+):")


def _is_chromium_internal_tag(tag: str) -> bool:
    return tag.startswith(_CHROMIUM_INTERNAL_TAG_PREFIX) or tag in _CHROMIUM_INTERNAL_TAGS


def _app_scoped_logcat_lines(text: str, pid: str | None) -> list[str]:
    """Фильтрует сырой вывод `logcat -d` до строк, реально относящихся к процессу
    приложения (по PID) и НЕ являющихся собственной диагностикой Chromium/WebView
    engine (см. `_is_chromium_internal_tag`/калибровку выше). Строки без
    распознанного заголовка (`threadtime`-формат) пропускаются (не участвуют ни в
    фильтрации, ни в скане) — редкие continuation-строки многострочных сообщений,
    не несущие собственного PID/тега."""
    result = []
    for line in text.splitlines():
        m = _LOGCAT_LINE_RE.match(line)
        if not m:
            continue
        line_pid, _tid, tag = m.group(1), m.group(2), m.group(3).strip()
        if pid is not None and line_pid != pid:
            continue
        if _is_chromium_internal_tag(tag):
            continue
        result.append(line)
    return result


@allure.step("Then захваченный logcat не содержит cookie/session/токенов/локальных путей приложения (best-effort, E4-min)")
def assert_logcat_has_no_sensitive_data(lines: int = 4000) -> None:
    """Testability gap (best-effort — см. TC-105.md «Заметки для автоматизации»):
    отличение ПРИКЛАДНОЙ утечки от ШТАТНОГО системного шума — вопрос калибровки
    на реальном прогоне; список паттернов — стартовая гипотеза, не окончательный
    набор (тот же класс оговорки, что testability gap ANR-детекции TC-098,
    `perf_steps.assert_no_crash_or_anr`). Матчер сужен до строк процесса
    приложения без Chromium-внутренних тегов `cr_*` (см. калибровку выше) —
    отсутствие совпадений здесь доказывает «не замечено СРЕДИ строк приложения
    в ЭТОМ прогоне», не «приложение никогда не логирует чувствительные данные»."""
    raw = adb.shell(f"logcat -d -t {lines}", timeout=settings.ADB_SHELL_TIMEOUT)
    pid = adb.shell(f"pidof {settings.APP_PACKAGE}").strip() or None
    app_lines = _app_scoped_logcat_lines(raw, pid)
    scoped_text = "\n".join(app_lines)
    allure.attach(
        f"pid={pid!r} total_lines={len(raw.splitlines())} app_scoped_lines={len(app_lines)}",
        name="tc105-logcat-scope",
        attachment_type=allure.attachment_type.TEXT,
    )
    cookie_token_hits = [p for p in _SENSITIVE_PATTERNS if p in scoped_text]
    assert not cookie_token_hits, (
        f"logcat (в пределах процесса приложения) содержит паттерн(ы) cookie/сессии/"
        f"токена: {cookie_token_hits}"
    )
    path_hits = [p for p in _INTERNAL_PATH_PATTERNS if p in scoped_text]
    assert not path_hits, (
        f"logcat (в пределах процесса приложения, без Chromium-внутренних тегов "
        f"cr_*) содержит полный локальный путь приложения: {path_hits} — возможная "
        f"утечка внутреннего пути приложения в прикладной (не системной) строке"
    )
