

[CmdletBinding()]
param(

    [switch]$NoPause,

    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'runtime.ps1')

try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false) } catch { }
$env:PYTHONUTF8 = '1'

$env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
$env:PIP_NO_INPUT = '1'

$script:StepNumber = 0
$script:StepTitle = ''
$script:Hints = @()
$script:Warnings = New-Object System.Collections.Generic.List[string]
$script:Changes = New-Object System.Collections.Generic.List[string]

function Write-RemOk   { param([string]$m) Write-Host "      [就绪] $m" -ForegroundColor Green }
function Write-RemSkip { param([string]$m) Write-Host "      [跳过] $m" -ForegroundColor DarkGray }
function Write-RemDo   { param([string]$m) Write-Host "      [安装] $m" -ForegroundColor Yellow }
function Write-RemWarn { param([string]$m) Write-Host "      [注意] $m" -ForegroundColor Yellow }
function Write-RemInfo { param([string]$m) Write-Host "      $m" -ForegroundColor Gray }

function Start-RemStep {
    param([string]$Title)
    $script:StepNumber++
    $script:StepTitle = $Title
    $script:Hints = @()
    Write-Host ''
    Write-Host ("[{0}] {1}" -f $script:StepNumber, $Title) -ForegroundColor Cyan
}

function Fail-Rem {
    param([string]$Reason, [string[]]$Hints = @())
    $script:Hints = $Hints
    throw (New-Object System.Exception $Reason)
}

function Add-RemWarning {
    param([string]$Message)
    [void]$script:Warnings.Add($Message)
}

function Show-RemStatus {
    param($Status)
    foreach ($item in $Status) {
        $mark = '[缺失]'
        $color = 'Yellow'
        if ($item.Ok) { $mark = '[就绪]'; $color = 'Green' }
        elseif ($item.Tier -eq '必需') { $color = 'Red' }
        Write-Host ("      {0} {1}（{2}）  {3}" -f $mark, $item.Name, $item.Tier, $item.Detail) -ForegroundColor $color
    }
}

function Install-RemWingetPackage {
    param([string]$Title, [string[]]$Ids)
    $winget = Resolve-RemCommandPath -Name 'winget'
    if ([string]::IsNullOrWhiteSpace($winget)) {
        Fail-Rem -Reason "系统里没有 winget，无法自动安装 $Title。" -Hints @(
            '打开 Microsoft Store，搜索并安装或更新「应用安装程序」(App Installer)，然后重新运行 install_dependencies.cmd。',
            "或者手动安装 $Title，装好后重新运行本脚本。"
        )
    }
    foreach ($id in $Ids) {
        Write-RemDo ("winget 安装 {0}（{1}）" -f $Title, $id)
        $code = Invoke-RemNative -FilePath $winget -Arguments @(
            'install', '--id', $id, '--exact', '--source', 'winget',
            '--accept-package-agreements', '--accept-source-agreements', '--disable-interactivity'
        )

        Update-RemPath

        if ($code -eq 0 -or $code -eq -1978335189) { return $true }
        Write-RemInfo ("{0} 未成功（winget 退出码 {1}），尝试下一个候选" -f $id, $code)
    }
    return $false
}

function Install-RemPipPackage {
    param([string]$Python, [string]$Package, [switch]$Upgrade)

    $arguments = @('-m', 'pip', 'install',
        '--disable-pip-version-check', '--no-input', '--no-warn-script-location')
    if ($Upgrade) { $arguments += '--upgrade' }
    $arguments += $Package
    Write-RemDo ("pip 安装 {0}" -f $Package)
    return (Invoke-RemNative -FilePath $Python -Arguments $arguments)
}

try {
    Update-RemPath

    Start-RemStep '环境检查'
    $edition = '64 位'
    if (-not [Environment]::Is64BitProcess) { $edition = '32 位' }
    Write-RemInfo ("PowerShell {0}（{1}）" -f $PSVersionTable.PSVersion, $edition)
    Write-RemInfo ("程序目录：{0}" -f $PSScriptRoot)

    $python = Find-RemPython
    if ($python) { Add-RemPythonScriptsToPath -Python $python }

    if ($CheckOnly) {
        $status = Get-RemRequirementStatus -Python $python
        Show-RemStatus -Status $status
        $missing = @($status | Where-Object { $_.Tier -eq '必需' -and -not $_.Ok })
        if ($missing.Count -eq 0) {
            Write-Host ''
            Write-Host '体检结果：必需组件齐全，可以直接运行 run.cmd。' -ForegroundColor Green
            exit 0
        }
        Write-Host ''
        Write-Host ("体检结果：缺少必需组件 -> {0}" -f (($missing | ForEach-Object { $_.Name }) -join '、')) -ForegroundColor Red
        exit 1
    }

    Start-RemStep 'Python 3.10+'
    $python = Find-RemPython
    if ($python) {
        Write-RemSkip ("已安装 {0}  {1}" -f (Get-RemPythonVersionText -Python $python), $python)
    }
    else {
        Write-RemDo '未找到可用的 Python，尝试用 winget 安装'

        $installed = Install-RemWingetPackage -Title 'Python' -Ids @(
            'Python.Python.3.13', 'Python.Python.3.12', 'Python.Python.3.11', 'Python.Python.3.10')
        Update-RemPath
        $python = Find-RemPython
        if (-not $installed -or -not $python) {
            Fail-Rem -Reason 'Python 安装后仍未被检测到。' -Hints @(
                '关闭本窗口后重新打开，再运行一次 install_dependencies.cmd（新装的程序需要新的 PATH）。',
                '也可以到 https://www.python.org/downloads/windows/ 手动安装 Python 3.10 或更高版本，安装时勾选 "Add python.exe to PATH"。',
                '如果电脑上已有 Python 但版本低于 3.10，请升级后再试。'
            )
        }
        Write-RemOk ("已安装 {0}  {1}" -f (Get-RemPythonVersionText -Python $python), $python)
        [void]$script:Changes.Add('Python')
    }
    Write-RemTextFile -Path (Join-Path $PSScriptRoot '.python-path') -Value $python
    Add-RemPythonScriptsToPath -Python $python

    Start-RemStep 'pip'
    $pip = Invoke-RemCapture -FilePath $python -Arguments @('-m', 'pip', '--version')
    if ($pip.Code -eq 0 -and $pip.Output) {
        Write-RemSkip $pip.Output
    }
    else {
        Write-RemDo 'pip 缺失，执行 ensurepip'
        $code = Invoke-RemNative -FilePath $python -Arguments @('-m', 'ensurepip', '--upgrade')
        if ($code -ne 0) {
            Fail-Rem -Reason 'ensurepip 执行失败。' -Hints @(
                '在「设置 → 应用」里找到 Python，选择「修改」→「修复」，然后重试。',
                '或手动执行：<Python路径> -m ensurepip --default-pip',
                '若使用 Microsoft Store 版 Python，请确认其已完成首次初始化。'
            )
        }
        $pip = Invoke-RemCapture -FilePath $python -Arguments @('-m', 'pip', '--version')
        if ($pip.Code -ne 0) {
            Fail-Rem -Reason 'pip 安装后仍不可用。' -Hints @(
                '关闭本窗口后重新打开，再运行一次 install_dependencies.cmd。',
                '仍失败时请修复 Python 安装（设置 → 应用 → Python → 修改 → 修复）。'
            )
        }
        Write-RemOk $pip.Output
        [void]$script:Changes.Add('pip')
    }

    Start-RemStep 'yt-dlp'
    $ytdlpPath = Resolve-RemCommandPath -Name 'yt-dlp'
    $ytdlpCliOk = (-not [string]::IsNullOrWhiteSpace($ytdlpPath)) -and
                  (Test-RemCommand -Name 'yt-dlp' -Arguments @('--version'))
    $ytdlpModuleOk = Test-RemPythonModule -Python $python -Modules @('yt_dlp')
    if ($ytdlpCliOk -and $ytdlpModuleOk) {
        Write-RemSkip ("已安装 {0}" -f (Invoke-RemCapture -FilePath $ytdlpPath -Arguments @('--version')).Output)
    }
    else {
        $reason = 'Python 模块 yt_dlp 缺失'
        if ($ytdlpModuleOk) { $reason = 'PATH 中缺少 yt-dlp.exe' }
        Write-RemDo $reason
        $code = Install-RemPipPackage -Python $python -Package 'yt-dlp[default]' -Upgrade
        if ($code -ne 0) {
            Fail-Rem -Reason ("pip 安装 yt-dlp 失败（退出码 {0}）。" -f $code) -Hints @(
                '检查网络或代理是否能访问 PyPI（https://pypi.org）。',
                '若公司网络有代理，可先设置环境变量 HTTPS_PROXY 后重试。',
                '也可以手动执行：<Python路径> -m pip install "yt-dlp[default]"'
            )
        }
        Add-RemPythonScriptsToPath -Python $python
        Update-RemPath
        if ([string]::IsNullOrWhiteSpace((Resolve-RemCommandPath -Name 'yt-dlp'))) {
            Fail-Rem -Reason 'yt-dlp 装好了，但找不到 yt-dlp.exe。' -Hints @(
                '关闭本窗口后重新打开，再运行一次 install_dependencies.cmd。',
                '若仍失败，请手动执行：<Python路径> -m pip install --force-reinstall "yt-dlp[default]"'
            )
        }
        Write-RemOk '已安装 yt-dlp'
        [void]$script:Changes.Add('yt-dlp')
    }

    Start-RemStep 'FFmpeg'
    if ((Test-RemCommand -Name 'ffmpeg' -Arguments @('-version')) -and
        (Test-RemCommand -Name 'ffprobe' -Arguments @('-version'))) {
        $ffmpegPath = Resolve-RemCommandPath -Name 'ffmpeg'
        $version = (Invoke-RemCapture -FilePath $ffmpegPath -Arguments @('-version')).Output
        Write-RemSkip ("已安装 {0}" -f (($version -replace '^ffmpeg version\s+', '').Split(' ')[0]))
    }
    else {
        Write-RemDo '未找到 ffmpeg / ffprobe，尝试用 winget 安装'
        $installed = Install-RemWingetPackage -Title 'FFmpeg' -Ids @('Gyan.FFmpeg')
        Update-RemPath
        if (-not $installed -or -not (Test-RemCommand -Name 'ffmpeg' -Arguments @('-version'))) {
            Fail-Rem -Reason 'FFmpeg 安装后仍未被检测到。' -Hints @(
                '关闭本窗口后重新打开，再运行一次 install_dependencies.cmd（新装的程序需要新的 PATH）。',
                '也可以手动下载 FFmpeg（https://www.gyan.dev/ffmpeg/builds/），解压后把 bin 目录加入 PATH。',
                '或在程序设置里手动指定 FFmpeg 所在目录。'
            )
        }
        Write-RemOk '已安装 FFmpeg'
        [void]$script:Changes.Add('FFmpeg')
    }

    Start-RemStep 'Node.js（推荐，YouTube 的 JS 运行时）'
    $nodePath = Resolve-RemCommandPath -Name 'node'
    if (-not [string]::IsNullOrWhiteSpace($nodePath)) {
        Write-RemSkip ("已安装 {0}" -f (Invoke-RemCapture -FilePath $nodePath -Arguments @('--version')).Output)
    }
    elseif (Install-RemWingetPackage -Title 'Node.js' -Ids @('OpenJS.NodeJS.LTS')) {
        Write-RemOk '已安装 Node.js'
        [void]$script:Changes.Add('Node.js')
    }
    else {
        $message = 'Node.js 未能自动安装；YouTube 部分高清格式可能受限，其余功能不受影响。'
        Write-RemWarn $message
        Write-RemInfo '可手动安装：https://nodejs.org/'
        Add-RemWarning $message
    }

    Start-RemStep 'Playwright（可选，抖音浏览器兜底）'
    if (Test-RemPythonModule -Python $python -Modules @('playwright.sync_api')) {
        Write-RemSkip '已安装'
    }
    elseif ((Install-RemPipPackage -Python $python -Package 'playwright') -eq 0) {
        Write-RemOk '已安装 Playwright'
        [void]$script:Changes.Add('Playwright')
    }
    else {
        $message = 'Playwright 未能自动安装；抖音链接的浏览器兜底下载将不可用，其余功能不受影响。'
        Write-RemWarn $message
        Add-RemWarning $message
    }

    Start-RemStep 'Chrome / Edge（可选，抖音浏览器兜底）'
    $browser = Get-RemBrowserPath
    if ($browser) {
        Write-RemSkip $browser
    }
    elseif (Install-RemWingetPackage -Title 'Google Chrome' -Ids @('Google.Chrome')) {
        Write-RemOk '已安装 Google Chrome'
        [void]$script:Changes.Add('Google Chrome')
    }
    else {
        $message = '未找到 Chrome / Edge，且自动安装失败；抖音兜底下载不可用，其余功能不受影响。'
        Write-RemWarn $message
        Add-RemWarning $message
    }

    Start-RemStep '最终校验'
    Update-RemPath
    $python = Find-RemPython
    if ($python) { Add-RemPythonScriptsToPath -Python $python }
    $status = Get-RemRequirementStatus -Python $python
    Show-RemStatus -Status $status

    $missing = @($status | Where-Object { $_.Tier -eq '必需' -and -not $_.Ok })
    if ($missing.Count -gt 0) {
        Fail-Rem -Reason ("仍有必需组件不可用：{0}" -f (($missing | ForEach-Object { $_.Name }) -join '、')) -Hints @(
            '关闭本窗口后重新打开，再运行一次 install_dependencies.cmd。',
            '若仍失败，请把上面每一条 [缺失] 的状态信息一并反馈。'
        )
    }

    Write-Host ''
    Write-Host '============================================================' -ForegroundColor Green
    if ($script:Changes.Count -gt 0) {
        Write-Host ("本次新装/修复：{0}" -f ($script:Changes -join '、')) -ForegroundColor Green
    }
    else {
        Write-Host '所有依赖本来就已就绪，未做任何改动。' -ForegroundColor Green
    }
    if ($script:Warnings.Count -gt 0) {
        Write-Host '以下为可选组件，不影响使用：' -ForegroundColor Yellow
        foreach ($warning in $script:Warnings) { Write-Host "  - $warning" -ForegroundColor Yellow }
    }
    Write-Host '依赖已就绪，双击 run.cmd 即可启动 Rem Downloader。' -ForegroundColor Green
    Write-Host '============================================================' -ForegroundColor Green
    exit 0
}
catch {
    Write-Host ''
    Write-Host '============================================================' -ForegroundColor Red
    Write-Host ("安装失败：第 {0} 步「{1}」" -f $script:StepNumber, $script:StepTitle) -ForegroundColor Red
    Write-Host ("原因：{0}" -f $_.Exception.Message) -ForegroundColor Red
    if ($script:Hints.Count -gt 0) {
        Write-Host ''
        Write-Host '可能的解决办法：' -ForegroundColor Yellow
        foreach ($hint in $script:Hints) { Write-Host ("  - {0}" -f $hint) -ForegroundColor Yellow }
    }
    Write-Host '============================================================' -ForegroundColor Red
    if (-not $NoPause) { Wait-RemKey }
    exit 1
}
