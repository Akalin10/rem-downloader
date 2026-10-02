

[CmdletBinding(SupportsShouldProcess = $true)]
param(

    [string]$Destination,

    [string]$Name = 'Rem Downloader'
)

$ErrorActionPreference = 'Stop'

function Write-Status {
    param([string]$Message, [string]$Color = 'Gray')
    Write-Host $Message -ForegroundColor $Color
}

$projectRoot = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($projectRoot) -and $MyInvocation.MyCommand.Path) {
    $projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
}
if ([string]::IsNullOrWhiteSpace($projectRoot)) {
    throw 'Unable to determine the project directory. Run this script from a file instead of from stdin.'
}

$projectRoot = $projectRoot.TrimEnd('\', '/')
try {
    $projectRoot = [System.IO.Path]::GetFullPath($projectRoot).TrimEnd('\', '/')
}
catch {

}

$launcher = Join-Path $projectRoot 'run.cmd'
if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
    throw "Missing run.cmd next to this script: $launcher  Keep the project files together."
}

$icon = Join-Path $projectRoot 'assets\rem-downloader.ico'
$hasIcon = Test-Path -LiteralPath $icon -PathType Leaf

$cmdPath = $env:ComSpec
if ([string]::IsNullOrWhiteSpace($cmdPath) -or -not (Test-Path -LiteralPath $cmdPath -PathType Leaf)) {
    $cmdPath = Join-Path $env:SystemRoot 'System32\cmd.exe'
}

if ([string]::IsNullOrWhiteSpace($Destination)) {
    $Destination = [Environment]::GetFolderPath('Desktop')
}
if ([string]::IsNullOrWhiteSpace($Destination)) {
    $Destination = Join-Path $env:USERPROFILE 'Desktop'
}
if ([string]::IsNullOrWhiteSpace($Destination)) {
    throw 'Unable to locate a destination folder. Pass one explicitly with -Destination.'
}
if (-not (Test-Path -LiteralPath $Destination -PathType Container)) {
    Write-Status "Destination folder does not exist, creating it: $Destination" 'Yellow'
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
}

$shortcutPath = Join-Path $Destination ($Name + '.lnk')

$expectedArguments = '/c ""' + $launcher + '""'

$shell = New-Object -ComObject WScript.Shell
$existing = $null
if (Test-Path -LiteralPath $shortcutPath) {
    try {
        $old = $shell.CreateShortcut($shortcutPath)
        $existing = [pscustomobject]@{
            TargetPath       = [string]$old.TargetPath
            Arguments        = [string]$old.Arguments
            WorkingDirectory = [string]$old.WorkingDirectory
        }
    }
    catch {
        $existing = [pscustomobject]@{ TargetPath = ''; Arguments = ''; WorkingDirectory = '' }
        Write-Status 'Existing shortcut could not be read; it will be replaced.' 'Yellow'
    }
}

$isUpToDate = $false
if ($null -ne $existing) {
    if (($existing.WorkingDirectory -eq $projectRoot) -and ($existing.Arguments -eq $expectedArguments)) {
        $isUpToDate = $true
        Write-Status "Existing shortcut already points here: $shortcutPath" 'DarkGray'
    }
    else {
        $oldLocation = $existing.WorkingDirectory
        if ([string]::IsNullOrWhiteSpace($oldLocation)) { $oldLocation = $existing.TargetPath }
        if ([string]::IsNullOrWhiteSpace($oldLocation)) {
            Write-Status 'Existing shortcut has no usable target; it will be rebuilt.' 'Yellow'
        }
        elseif (-not (Test-Path -LiteralPath $oldLocation)) {
            Write-Status "Existing shortcut is stale; its old location no longer exists: $oldLocation" 'Yellow'
        }
        else {
            Write-Status "Existing shortcut points elsewhere: $oldLocation" 'Yellow'
        }
        Write-Status 'Repairing it in place instead of failing.' 'Yellow'
    }
}

if (-not $isUpToDate) {
    if (-not $PSCmdlet.ShouldProcess($shortcutPath, 'Create or update shortcut')) {
        Write-Status 'WhatIf: nothing was written.' 'DarkGray'
        exit 0
    }
    try {
        $shortcut = $shell.CreateShortcut($shortcutPath)
        $shortcut.TargetPath = $cmdPath
        $shortcut.Arguments = $expectedArguments
        $shortcut.WorkingDirectory = $projectRoot
        $shortcut.Description = 'Rem Downloader - terminal video downloader'
        if ($hasIcon) {
            $shortcut.IconLocation = $icon + ',0'
        }
        else {
            $shortcut.IconLocation = $cmdPath + ',0'
            Write-Status 'assets\rem-downloader.ico not found; falling back to the default console icon.' 'Yellow'
        }
        $shortcut.Save()
    }
    catch {
        throw "Failed to write the shortcut: $shortcutPath  $($_.Exception.Message)"
    }
}

$problems = @()
try {
    $check = $shell.CreateShortcut($shortcutPath)
    if ($check.TargetPath -ne $cmdPath) {
        $problems += "TargetPath is '$($check.TargetPath)', expected '$cmdPath'"
    }
    if ($check.WorkingDirectory -ne $projectRoot) {
        $problems += "WorkingDirectory is '$($check.WorkingDirectory)', expected '$projectRoot'"
    }
    if ($check.Arguments -ne $expectedArguments) {
        $problems += "Arguments are '$($check.Arguments)', expected '$expectedArguments'"
    }
}
catch {
    $problems += "Shortcut could not be re-read: $($_.Exception.Message)"
}

try { [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($shell) } catch { }

if ($problems.Count -gt 0) {
    Write-Status 'Shortcut verification failed:' 'Red'
    foreach ($problem in $problems) { Write-Status "  $problem" 'Red' }
    exit 1
}

Write-Status ''
Write-Status 'Rem Downloader shortcut is ready.' 'Green'
Write-Status "  Shortcut : $shortcutPath"
Write-Status "  Target   : $cmdPath"
Write-Status "  Launcher : $launcher"
Write-Status "  WorkDir  : $projectRoot"
if ($hasIcon) { Write-Status "  Icon     : $icon" }
Write-Status 'You can move the whole folder at any time, then run this script again to repoint the shortcut.' 'DarkGray'
exit 0
