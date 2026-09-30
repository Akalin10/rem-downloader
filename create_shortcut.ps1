param(
    [string]$Destination = [Environment]::GetFolderPath('Desktop')
)

$ErrorActionPreference = 'Stop'
$taskLauncher = Join-Path $PSScriptRoot 'run.cmd'
$taskIcon = Join-Path $PSScriptRoot 'assets\rem-downloader.ico'
if (!(Test-Path -LiteralPath $taskLauncher) -or !(Test-Path -LiteralPath $taskIcon)) {
    throw 'Missing run.cmd or assets/rem-downloader.ico. Keep the project files together.'
}
if (!(Test-Path -LiteralPath $Destination -PathType Container)) {
    throw 'The shortcut destination must be an existing folder.'
}
$taskShortcutPath = Join-Path $Destination 'Rem Downloader.lnk'
$taskShell = New-Object -ComObject WScript.Shell
$taskShortcut = $taskShell.CreateShortcut($taskShortcutPath)
if ((Test-Path -LiteralPath $taskShortcutPath) -and
    $taskShortcut.WorkingDirectory -ne $PSScriptRoot) {
    throw 'A shortcut for another installation already exists. Choose another destination.'
}
$taskShortcut.TargetPath = Join-Path $env:SystemRoot 'System32\cmd.exe'
$taskShortcut.Arguments = '/c ""' + $taskLauncher + '""'
$taskShortcut.WorkingDirectory = $PSScriptRoot
$taskShortcut.IconLocation = $taskIcon + ',0'
$taskShortcut.Description = 'Rem Downloader - terminal video downloader'
$taskShortcut.Save()
Write-Host "Created shortcut: $taskShortcutPath"
