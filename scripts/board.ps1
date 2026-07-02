# Борда TrackState. Использование: . D:\AO3_tests\scripts\board.ps1 ; Sync-Board ; Open-Board
# ВАЖНО: локальный провайдер TrackState читает ЗАКОММИЧЕННЫЙ HEAD, поэтому Sync-Board
# после генерации делает git commit — иначе приложение не увидит изменения.
$root = "D:\AO3_tests"
$py = "$root\framework\.venv\Scripts\python.exe"

function Sync-Board {
    Push-Location $root
    & $py "$root\scripts\board_sync.py"
    git add board
    $changed = git status --porcelain board
    if ($changed) {
        git -c user.email="qa@ao3tests.local" -c user.name="AO3 QA" commit -q -m "board: sync проекции из артефактов"
        Write-Host "board/ пересобрана и закоммичена." -ForegroundColor Green
    } else {
        Write-Host "board/ без изменений." -ForegroundColor Yellow
    }
    Pop-Location
}

function Open-Board {
    # Десктоп-приложение TrackState. В приложении выбрать Local target и папку D:\AO3_tests.
    Start-Process "$root\tools\trackstate\trackstate.exe"
    Write-Host "TrackState запущен. Выберите: Local repository -> $root" -ForegroundColor Cyan
}

function Show-BoardCli {
    # Быстрый headless-просмотр без GUI (JQL-поиск через CLI).
    & "$root\tools\ts-cli\trackstate.exe" search --target local --jql "project = AO3 ORDER BY key ASC"
}

Write-Host "Board loaded: Sync-Board (пересобрать+commit), Open-Board (GUI), Show-BoardCli (JQL)" -ForegroundColor Green
