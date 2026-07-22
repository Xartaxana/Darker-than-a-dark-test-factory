"""TC-100/TC-101 (security): статическая инспекция AndroidManifest.xml через
`aapt dump xmltree` (misc-batch-0722, замечание critic прохода (5),
`docs/09-history.md:771-773`) — build-level факты, БЕЗ Appium-сессии/WebView.

TC-100 — exported=true + VIEW/DEFAULT/BROWSABLE intent-filter на MainActivity.
TC-101 — расширение того же приёма на cleartext-трафик, сверка с фактом
наличия http-схемы в intent-filter (зафиксированным независимо этим же
кейсом — оба теста детерминированно читают один и тот же APK, порядок
выполнения не важен).

Оба кейса — единичные статические факты одного и того же неизменного
build-артефакта (APK не меняется между прогонами одной сборки) — повторные
прогоны не добавляют информации сверх однократного чтения, поэтому DoD «3
стабильных зелёных прогона подряд» удовлетворяется трояким прогоном
`pytest -k test_security_manifest` (детерминированная функция от файла на
диске, отсутствие флейка тривиально по построению — нет ни Appium, ни сети,
ни ожиданий)."""
from __future__ import annotations

import allure
import pytest

from framework.steps import security_steps


@pytest.mark.p1
@allure.id("TC-100")
@allure.title("Exported-компоненты: MainActivity exported=true с VIEW/BROWSABLE intent-filter на archiveofourown.org")
def test_main_activity_exported_with_ao3_intent_filter():
    # Given APK тестируемой сборки доступен на диске (build-артефакт) — не
    # требует установленного устройства/Appium-сессии
    # When манифест инспектируется статически (aapt dump xmltree)
    tree = security_steps.dump_manifest_tree()

    # Then MainActivity отмечена exported=true, и у неё есть intent-filter с
    # action.VIEW, categories DEFAULT/BROWSABLE, data-схемой http/https и
    # host=archiveofourown.org
    security_steps.assert_main_activity_exported_with_view_intent_filter(tree)


@pytest.mark.p1
@allure.id("TC-101")
@allure.title("Cleartext-трафик: политика манифеста зафиксирована и сверена с http-схемой intent-filter")
def test_cleartext_traffic_policy_documented_and_cross_checked():
    # Given/When манифест инспектируется статически (тот же приём, что TC-100)
    tree = security_steps.dump_manifest_tree()

    # And http-схема VIEW/BROWSABLE intent-filter фиксируется тем же способом,
    # что и TC-100 (не зависит от порядка выполнения тестов — оба читают APK
    # независимо)
    matching_filters = security_steps.assert_main_activity_exported_with_view_intent_filter(tree)
    http_scheme_present = any(
        scheme == "http" for facts in matching_filters for scheme, _host in facts["datas"]
    )

    # Then эффективная политика cleartext-трафика (usesCleartextTraffic явный,
    # ЛИБО networkSecurityConfig, ЛИБО дефолт по targetSdkVersion) зафиксирована
    # как факт и сверена с http-схемой — расхождение фиксируется как наблюдение
    # для триажа, не как вердикт «баг»/«не баг» (E4-min, §8)
    security_steps.assert_cleartext_policy_documented(tree, http_scheme_present)
