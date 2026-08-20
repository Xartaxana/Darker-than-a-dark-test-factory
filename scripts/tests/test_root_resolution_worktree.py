# -*- coding: utf-8 -*-
"""$root в scripts/tasks.ps1 / scripts/env.ps1 резолвится от местоположения
файла, а не литералом D:\\AO3_tests.

Класс-дефект (найден builder'ом N1 программы П3): литеральный $root заставлял
копию обвязки из git-worktree молча исполнять ГЛАВНЫЙ чекаут (Push-Location в
чужой framework\\) — witness любого worktree-воркера был недействителен.
Тесты копируют реальные скрипты во временное дерево-«worktree» и проверяют,
что $root указывает на НЕГО; плюс пин обратной совместимости главного чекаута.
"""
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_PS = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command"]


def _dot_source_and_print_root(ps1_path: Path) -> str:
    # Дот-сорсим и печатаем $root маркером, чтобы отсечь баннеры скриптов.
    cmd = _PS + [f". '{ps1_path}' | Out-Null; Write-Output ('ROOT=' + $root)"]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, f"dot-source failed: {out.stdout}\n{out.stderr}"
    lines = [l for l in out.stdout.splitlines() if l.startswith("ROOT=")]
    assert lines, f"no ROOT= marker in output: {out.stdout!r}"
    return lines[-1][len("ROOT="):].strip()


def _make_fake_worktree(tmp_path: Path) -> Path:
    wt = tmp_path / "fake-worktree"
    (wt / "scripts").mkdir(parents=True)
    for name in ("tasks.ps1", "env.ps1"):
        shutil.copy2(REPO_ROOT / "scripts" / name, wt / "scripts" / name)
    return wt


def test_env_ps1_root_points_to_containing_tree(tmp_path):
    wt = _make_fake_worktree(tmp_path)
    root = _dot_source_and_print_root(wt / "scripts" / "env.ps1")
    assert Path(root) == wt, f"env.ps1 $root={root!r}, ожидался worktree {wt}"


def test_tasks_ps1_root_points_to_containing_tree(tmp_path):
    wt = _make_fake_worktree(tmp_path)
    root = _dot_source_and_print_root(wt / "scripts" / "tasks.ps1")
    assert Path(root) == wt, f"tasks.ps1 $root={root!r}, ожидался worktree {wt}"


def test_main_checkout_root_unchanged():
    # Обратная совместимость: из главного чекаута $root — прежний корень репо.
    root = _dot_source_and_print_root(REPO_ROOT / "scripts" / "tasks.ps1")
    assert Path(root) == REPO_ROOT


def test_no_root_literal_assignment_left():
    # Детектор регресса: прямое присваивание литерала без $PSScriptRoot-ветки.
    for name in ("tasks.ps1", "env.ps1"):
        text = (REPO_ROOT / "scripts" / name).read_text(encoding="utf-8-sig")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("$root =") or stripped.startswith("$root="):
                assert "$PSScriptRoot" in stripped, (
                    f"{name}: присваивание $root без $PSScriptRoot-резолюции: "
                    f"{stripped!r}"
                )
