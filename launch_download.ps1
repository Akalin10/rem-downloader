$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$env:PYTHONUTF8 = '1'
$taskScript = Join-Path $PSScriptRoot 'download_cli.py'
$taskPythonCandidates = @(
    (Join-Path $env:USERPROFILE '.agent-reach-venv\Scripts\python.exe'),
    (Join-Path $env:LOCALAPPDATA 'Python\pythoncore-3.14-64\python.exe')
)
$taskPythonCommand = Get-Command python -ErrorAction SilentlyContinue
if ($taskPythonCommand) { $taskPythonCandidates += $taskPythonCommand.Source }
foreach ($taskPython in ($taskPythonCandidates | Select-Object -Unique)) {
    if (Test-Path -LiteralPath $taskPython) {
        try {
            & $taskPython -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>$null
            if ($LASTEXITCODE -eq 0) {
                & $taskPython $taskScript @args
                exit $LASTEXITCODE
            }
        } catch { }
    }
}
Write-Host '未找到可运行的 Python 3.10+。请安装 Python 后重试。' -ForegroundColor Red
exit 1
