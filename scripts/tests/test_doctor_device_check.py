"""Юнит-тесты _device_package_check + парсеров pm path/sha256sum
(scripts/doctor.py) — mech-device-build-check, spec-device-build-check.md v3.

Третье звено цепочки идентичности сборки: устройство vs yaml (сборка->yaml
уже закрыт build_watch/M-B, yaml->файл — `_apk_sha256_check`/A2-C1, тесты в
test_doctor.py). Ветки тестируются напрямую вызовом чистой функции
`_device_package_check` (без run_checks/env-фикстуры) — сигнатура спеки:
`_device_package_check(adb_available, serial, dumpsys_out, installed_sha,
aut_text) -> Check`.
"""
from __future__ import annotations

import doctor as dr

CHECK_NAME = "пакет на устройстве соответствует yaml"

AUT_VALID = (
    'apk_path: app-under-test/app/build/outputs/apk/debug/app-debug.apk\n'
    'apk_sha256: "b60476475098e9194036450cda82d90051d6e5e9edc0d2b39c3758ffd86bbd71"\n'
    'version_name: "dev-local"\nversion_code: 12\n'
)

DUMPSYS_MATCH = (
    "Packages:\n"
    "  Package [com.example.ao3_wrapper] (789xyz):\n"
    "    userId=10123\n"
    "    pkg=Package{abc123 com.example.ao3_wrapper}\n"
    "    versionCode=12 minSdk=24 targetSdk=34\n"
    "    versionName=dev-local\n"
    "    codePath=/data/app/~~xxx/com.example.ao3_wrapper-yyy\n"
)

DUMPSYS_MISMATCH = DUMPSYS_MATCH.replace("versionCode=12", "versionCode=7")

YAML_SHA = "b60476475098e9194036450cda82d90051d6e5e9edc0d2b39c3758ffd86bbd71"


def _chk(**kwargs) -> dr.Check:
    args = dict(adb_available=True, serial="emulator-5554",
                dumpsys_out=DUMPSYS_MATCH, installed_sha=YAML_SHA,
                aut_text=AUT_VALID)
    args.update(kwargs)
    return dr._device_package_check(**args)


# ---------------------------------------------------------------------------
# Ветка 1-2: adb/serial отсутствуют
# ---------------------------------------------------------------------------

def test_branch1_adb_unavailable_is_ok_not_applicable():
    chk = _chk(adb_available=False)
    assert chk.ok and not chk.warn
    assert chk.name == CHECK_NAME
    assert "adb недоступен" in chk.detail


def test_branch2_no_serial_is_ok_not_applicable():
    chk = _chk(serial=None)
    assert chk.ok and not chk.warn
    assert "устройства нет" in chk.detail


# ---------------------------------------------------------------------------
# Ветка 3: yaml version_code пуст/unknown -> WARN (паритет с
# test_doctor.py::test_apk_sha256_check_unknown_versions_is_warn — тот же
# конструктор Check(name, "run", False, ..., warn=True)).
# ---------------------------------------------------------------------------

def test_branch3_yaml_version_code_missing_is_warn():
    aut = 'apk_path: x\napk_sha256: "aaa"\nversion_name: "1.0"\n'  # без version_code
    chk = _chk(aut_text=aut)
    assert not chk.ok and chk.warn
    assert "сверка невозможна" in chk.detail


def test_branch3_yaml_version_code_unknown_is_warn():
    aut = 'apk_path: x\napk_sha256: "aaa"\nversion_name: "unknown"\nversion_code: unknown\n'
    chk = _chk(aut_text=aut)
    assert not chk.ok and chk.warn
    assert "сверка невозможна" in chk.detail


def test_branch3_empty_apk_sha256_with_valid_vc_runs_vc_line_with_disclaimer():
    """Пуст ТОЛЬКО apk_sha256 при валидном version_code -> vc-линия
    выполняется (совпадение vc -> ok=True), sha-линия помечена недоступной
    оговоркой в detail."""
    aut = 'apk_path: x\napk_sha256: ""\nversion_name: "dev-local"\nversion_code: 12\n'
    chk = _chk(aut_text=aut)
    assert chk.ok and not chk.warn
    assert "vc=12" in chk.detail
    assert "apk_sha256 в yaml пуст/unknown" in chk.detail


def test_branch3_unknown_apk_sha256_with_valid_vc_mismatch_still_warns():
    """Тот же пустой/unknown apk_sha256, но vc НЕ совпадает -> WARN ветки 6
    (vc-mismatch приоритетнее недоступной sha-линии)."""
    aut = 'apk_path: x\napk_sha256: unknown\nversion_name: "dev-local"\nversion_code: 999\n'
    chk = _chk(aut_text=aut)
    assert not chk.ok and chk.warn
    assert "vc=12, yaml vc=999" in chk.detail


# ---------------------------------------------------------------------------
# Ветка 4: вызов dumpsys не удался (rc!=0/timeout/пустой вывод) -> н/п
# ---------------------------------------------------------------------------

def test_branch4_dumpsys_call_failed_none_is_ok_not_applicable():
    chk = _chk(dumpsys_out=None)
    assert chk.ok and not chk.warn
    assert "вызов adb не удался" in chk.detail


def test_branch4_dumpsys_empty_output_is_ok_not_applicable():
    chk = _chk(dumpsys_out="   \n")
    assert chk.ok and not chk.warn
    assert "вызов adb не удался" in chk.detail


# ---------------------------------------------------------------------------
# Ветка 5: якорь БЛОКОМ пакета — мультиблочный dumpsys, пакет отсутствует
# ---------------------------------------------------------------------------

def test_branch5_package_absent_is_ok_not_applicable():
    dumpsys = "Package [com.other.app] (111):\n  versionCode=1\n"
    chk = _chk(dumpsys_out=dumpsys)
    assert chk.ok and not chk.warn
    assert "пакет не установлен" in chk.detail


def test_branch5_multiblock_test_package_first_anchors_correct_block():
    """androidTest-пакет <PACKAGE_ID>.test первым блоком с ДРУГИМ
    versionCode — якорь обязан взять правильный (второй) блок, не спутать
    префикс с целевым пакетом."""
    dumpsys = (
        "Packages:\n"
        "  Package [com.example.ao3_wrapper.test] (abc):\n"
        "    versionCode=1 minSdk=24 targetSdk=34\n"
        "    versionName=1.0\n"
        + DUMPSYS_MATCH.replace("Packages:\n", "")
    )
    chk = _chk(dumpsys_out=dumpsys)
    assert chk.ok and not chk.warn
    assert "vc=12" in chk.detail  # взят блок целевого пакета, не .test (vc=1)


def test_branch5_multiblock_test_package_after_main_block_still_anchors_correct():
    """То же расхождение, но .test-блок ПОСЛЕ целевого — next-Package
    граница обязана остановить чтение блока до .test, не унести versionCode
    из чужого блока (в этой раскладке versionCode целевого блока читается
    первым — граница проверяется тем, что .test-блок не портит результат)."""
    dumpsys = (
        DUMPSYS_MATCH
        + "  Package [com.example.ao3_wrapper.test] (abc):\n"
        "    versionCode=1 minSdk=24 targetSdk=34\n"
    )
    chk = _chk(dumpsys_out=dumpsys)
    assert chk.ok and not chk.warn
    assert "vc=12" in chk.detail


def test_branch5_block_without_version_code_does_not_borrow_from_next_block():
    """Целевой блок без versionCode + отступленный .test-блок следом: граница
    обязана остановить чтение — иначе versionCode чужого блока даёт ЛОЖНЫЙ
    WARN вместо честного н/п (Б2а критик-входа приёмки; на прежней
    не-отступ-толерантной границе этот тест падал)."""
    dumpsys = (
        "Packages:\n"
        "  Package [com.example.ao3_wrapper] (789xyz):\n"
        "    userId=10123\n"
        "  Package [com.example.ao3_wrapper.test] (abc):\n"
        "    versionCode=1 minSdk=24 targetSdk=34\n"
    )
    chk = _chk(dumpsys_out=dumpsys)
    assert chk.ok and not chk.warn
    assert "versionCode не найден" in chk.detail


# ---------------------------------------------------------------------------
# Ветка 6: versionCode устройства != yaml -> WARN
# ---------------------------------------------------------------------------

def test_branch6_version_code_mismatch_is_warn():
    chk = _chk(dumpsys_out=DUMPSYS_MISMATCH)
    assert not chk.ok and chk.warn
    assert "vc=7, yaml vc=12" in chk.detail
    assert "Install-App" in chk.detail


# ---------------------------------------------------------------------------
# Ветка 7: vc совпал -> сверка sha (pm path / sha256sum уже разрешены
# вызывающим кодом в installed_sha)
# ---------------------------------------------------------------------------

def test_branch7_base_apk_path_unresolved_is_ok_not_applicable():
    chk = _chk(installed_sha=None)
    assert chk.ok and not chk.warn
    assert "путь base.apk не получен" in chk.detail


def test_branch7_sha_mismatch_is_warn_naming_sha_not_equal_vc():
    """WARN sha-линии обязан НАЗЫВАТЬ sha (vc на этой ветке заведомо равны —
    печатать их как улику расхождения нельзя: строка читается как ложный
    позитив и провоцирует утечку WARN, ответ (в) спеки)."""
    chk = _chk(installed_sha="0" * 64)
    assert not chk.ok and chk.warn
    assert "sha установленного base.apk НЕ совпадает" in chk.detail
    assert "000000000000" in chk.detail and YAML_SHA[:12] in chk.detail
    assert "Install-App" in chk.detail
    assert "yaml vc=" not in chk.detail


def test_branch7_full_match_is_ok():
    chk = _chk(installed_sha=YAML_SHA)
    assert chk.ok and not chk.warn
    assert "vc=12" in chk.detail
    assert YAML_SHA[:12] in chk.detail


def test_branch7_sha_comparison_case_insensitive():
    chk = _chk(installed_sha=YAML_SHA.upper())
    assert chk.ok and not chk.warn


# ---------------------------------------------------------------------------
# Парс pm path (`adb shell pm path <pkg>`)
# ---------------------------------------------------------------------------

def test_parse_pm_path_single_base_apk():
    out = "package:/data/app/~~xxx/com.example.ao3_wrapper-yyy/base.apk\n"
    assert dr._parse_pm_path_base_apk(out) == \
        "/data/app/~~xxx/com.example.ao3_wrapper-yyy/base.apk"


def test_parse_pm_path_multiline_with_split_config_ignored():
    out = (
        "package:/data/app/~~xxx/com.example.ao3_wrapper-yyy/base.apk\n"
        "package:/data/app/~~xxx/com.example.ao3_wrapper-yyy/split_config.arm64_v8a.apk\n"
        "package:/data/app/~~xxx/com.example.ao3_wrapper-yyy/split_config.xxhdpi.apk\n"
    )
    assert dr._parse_pm_path_base_apk(out) == \
        "/data/app/~~xxx/com.example.ao3_wrapper-yyy/base.apk"


def test_parse_pm_path_no_base_apk_line_returns_none():
    out = "package:/data/app/~~xxx/com.example.ao3_wrapper-yyy/split_config.arm64_v8a.apk\n"
    assert dr._parse_pm_path_base_apk(out) is None


def test_parse_pm_path_empty_output_returns_none():
    assert dr._parse_pm_path_base_apk("") is None
    assert dr._parse_pm_path_base_apk(None) is None


# ---------------------------------------------------------------------------
# Парс sha256sum (`adb shell sha256sum <path>`)
# ---------------------------------------------------------------------------

def test_parse_sha256sum_first_token_lowered():
    # 64 hex (валидная форма sha256) — прежняя 63-символьная фикстура не
    # пережила бы валидацию формы токена (Б2б).
    out = ("C3AB8FF13720E8AD9047DD39466B3C8974E592C2FA383D4A3960714CAEF0C4F0  "
           "/data/app/~~xxx/com.example.ao3_wrapper-yyy/base.apk\n")
    assert dr._parse_sha256sum_hex(out) == \
        "c3ab8ff13720e8ad9047dd39466b3c8974e592c2fa383d4a3960714caef0c4f0"


def test_parse_sha256sum_empty_output_returns_none():
    assert dr._parse_sha256sum_hex("") is None
    assert dr._parse_sha256sum_hex(None) is None
    assert dr._parse_sha256sum_hex("   \n") is None


def test_parse_sha256sum_non_hex_first_token_returns_none():
    """Б2б: `_run` склеивает stdout+stderr — диагностический текст при rc=0
    не должен становиться «хэшем» (ошибка инструмента ≠ сигнал, ветка 4)."""
    assert dr._parse_sha256sum_hex("sha256sum: /x/base.apk: No such file\n") is None
