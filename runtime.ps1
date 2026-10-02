

function Update-RemPath {
    $collected = New-Object System.Collections.Generic.List[string]
    $sources = @(
        [Environment]::GetEnvironmentVariable('Path', 'Machine'),
        [Environment]::GetEnvironmentVariable('Path', 'User'),
        $env:Path,
        (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links')
    )
    foreach ($source in $sources) {
        if ([string]::IsNullOrWhiteSpace($source)) { continue }
        foreach ($piece in ($source -split ';')) {
            $clean = $piece.Trim().Trim('"')
            if ($clean -and ($collected -notcontains $clean)) { [void]$collected.Add($clean) }
        }
    }
    $env:Path = ($collected -join ';')
}

function Read-RemTextFile {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path -LiteralPath $Path)) { return '' }
    try {
        $bytes = [System.IO.File]::ReadAllBytes($Path)
        return ([System.Text.Encoding]::UTF8.GetString($bytes)).TrimStart([char]0xFEFF).Trim()
    }
    catch { return '' }
}

function Write-RemTextFile {
    param([string]$Path, [string]$Value)

    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Value, $encoding)
}

function Invoke-RemCapture {
    param(
        [string]$FilePath,
        [string[]]$Arguments = @()
    )
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = & $FilePath @Arguments 2>&1
        $first = ''
        if ($null -ne $output) {
            $line = @($output | Where-Object { $_ -ne $null } | Select-Object -First 1)
            if ($line.Count -gt 0) { $first = [string]$line[0] }
        }
        return [pscustomobject]@{ Code = $LASTEXITCODE; Output = $first.Trim() }
    }
    catch {
        return [pscustomobject]@{ Code = -1; Output = '' }
    }
    finally {
        $ErrorActionPreference = $previous
    }
}

function Invoke-RemNative {
    param(
        [string]$FilePath,
        [string[]]$Arguments = @()
    )
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $FilePath @Arguments
        return $LASTEXITCODE
    }
    catch { return -1 }
    finally { $ErrorActionPreference = $previous }
}

function Resolve-RemCommandPath {
    param([string]$Name)
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($command -and $command.Source) { return $command.Source }
    $bases = @(
        (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links'),
        (Join-Path $env:ProgramFiles 'nodejs')
    )
    foreach ($base in $bases) {
        if ([string]::IsNullOrWhiteSpace($base) -or -not (Test-Path -LiteralPath $base)) { continue }
        foreach ($extension in '.exe', '.cmd', '.bat') {
            $candidate = Join-Path $base ($Name + $extension)
            if (Test-Path -LiteralPath $candidate) { return $candidate }
        }
    }
    return ''
}

function Test-RemCommand {
    param([string]$Name, [string[]]$Arguments = @('--version'))
    $resolved = Resolve-RemCommandPath -Name $Name
    if ([string]::IsNullOrWhiteSpace($resolved)) { return $false }
    return ((Invoke-RemCapture -FilePath $resolved -Arguments $Arguments).Code -eq 0)
}

function Test-RemPythonModule {
    param([string]$Python, [string[]]$Modules = @())
    if ([string]::IsNullOrWhiteSpace($Python) -or $Modules.Count -eq 0) { return $false }
    $code = (($Modules | ForEach-Object { "import $_" }) -join '; ')
    return ((Invoke-RemCapture -FilePath $Python -Arguments @('-c', $code)).Code -eq 0)
}

function Test-RemPythonVersion {
    param([string]$Python, [int]$Major = 3, [int]$Minor = 10)
    if ([string]::IsNullOrWhiteSpace($Python)) { return $false }
    $code = 'import sys; raise SystemExit(0 if sys.version_info >= ({0}, {1}) else 1)' -f $Major, $Minor
    return ((Invoke-RemCapture -FilePath $Python -Arguments @('-c', $code)).Code -eq 0)
}

function Get-RemPythonVersionText {
    param([string]$Python)
    if ([string]::IsNullOrWhiteSpace($Python)) { return '' }

    $code = "import sys; print('.'.join(map(str, sys.version_info[:3])))"
    return (Invoke-RemCapture -FilePath $Python -Arguments @('-c', $code)).Output
}

function Get-RemPythonCandidates {
    $candidates = New-Object System.Collections.Generic.List[string]

    $recorded = Read-RemTextFile (Join-Path $PSScriptRoot '.python-path')
    if ($recorded) { [void]$candidates.Add($recorded) }

    foreach ($name in 'python', 'python3') {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command -and $command.Source) { [void]$candidates.Add($command.Source) }
    }

    $launcher = Get-Command 'py' -ErrorAction SilentlyContinue
    if ($launcher -and $launcher.Source) {
        foreach ($flag in '-3.14', '-3.13', '-3.12', '-3.11', '-3.10', '-3') {
            $found = Invoke-RemCapture -FilePath $launcher.Source -Arguments @($flag, '-c', 'import sys; print(sys.executable)')
            if ($found.Code -eq 0 -and $found.Output) { [void]$candidates.Add($found.Output) }
        }
    }

    $searchRoots = New-Object System.Collections.Generic.List[string]
    [void]$searchRoots.Add((Join-Path $env:LOCALAPPDATA 'Programs\Python'))
    [void]$searchRoots.Add((Join-Path $env:LOCALAPPDATA 'Python'))
    [void]$searchRoots.Add((Join-Path $env:ProgramFiles 'Python'))
    if (${env:ProgramFiles(x86)}) { [void]$searchRoots.Add((Join-Path ${env:ProgramFiles(x86)} 'Python')) }

    foreach ($root in $searchRoots) {
        if (-not (Test-Path -LiteralPath $root)) { continue }
        $directories = @(Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue | Sort-Object Name -Descending)
        $directories += @(Get-Item -LiteralPath $root -ErrorAction SilentlyContinue)
        foreach ($directory in $directories) {
            if ($null -eq $directory) { continue }
            $executable = Join-Path $directory.FullName 'python.exe'
            if (Test-Path -LiteralPath $executable) { [void]$candidates.Add($executable) }
        }
    }

    $unique = New-Object System.Collections.Generic.List[string]
    foreach ($candidate in $candidates) {
        if ([string]::IsNullOrWhiteSpace($candidate)) { continue }
        if ($unique -notcontains $candidate) { [void]$unique.Add($candidate) }
    }
    return $unique
}

function Find-RemPython {
    foreach ($candidate in (Get-RemPythonCandidates)) {
        if (Test-RemPythonVersion -Python $candidate -Major 3 -Minor 10) { return $candidate }
    }
    return $null
}

function Add-RemPythonScriptsToPath {
    param([string]$Python)
    if ([string]::IsNullOrWhiteSpace($Python)) { return }
    $scripts = (Invoke-RemCapture -FilePath $Python -Arguments @('-c', "import sysconfig; print(sysconfig.get_path('scripts'))")).Output
    foreach ($directory in @($scripts, (Split-Path -Parent $Python))) {
        if ([string]::IsNullOrWhiteSpace($directory)) { continue }
        if (-not (Test-Path -LiteralPath $directory)) { continue }
        if (($env:Path -split ';') -notcontains $directory) { $env:Path = "$directory;$env:Path" }
    }
}

function Get-RemBrowserPath {
    $paths = @(
        (Join-Path $env:ProgramFiles 'Google\Chrome\Application\chrome.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'Google\Chrome\Application\chrome.exe'),
        (Join-Path $env:LOCALAPPDATA 'Google\Chrome\Application\chrome.exe'),
        (Join-Path $env:ProgramFiles 'Microsoft\Edge\Application\msedge.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'Microsoft\Edge\Application\msedge.exe')
    )
    foreach ($path in $paths) {
        if ($path -and (Test-Path -LiteralPath $path)) { return $path }
    }
    return ''
}

function Get-RemRequirementStatus {
    param([string]$Python)

    $results = New-Object System.Collections.Generic.List[object]

    if (Test-RemPythonVersion -Python $Python -Major 3 -Minor 10) {
        [void]$results.Add([pscustomobject]@{
            Key = 'python'; Name = 'Python 3.10+'; Tier = '必需'; Ok = $true
            Detail = "$(Get-RemPythonVersionText -Python $Python)  $Python"
        })
    }
    else {
        [void]$results.Add([pscustomobject]@{
            Key = 'python'; Name = 'Python 3.10+'; Tier = '必需'; Ok = $false; Detail = '未找到'
        })
    }

    $pipOk = $false
    $pipDetail = '未安装'
    if ($Python) {
        $pip = Invoke-RemCapture -FilePath $Python -Arguments @('-m', 'pip', '--version')
        $pipOk = ($pip.Code -eq 0 -and $pip.Output)
        if ($pipOk) { $pipDetail = $pip.Output }
    }
    [void]$results.Add([pscustomobject]@{
        Key = 'pip'; Name = 'pip'; Tier = '必需'; Ok = $pipOk; Detail = $pipDetail
    })

    $ytdlpPath = Resolve-RemCommandPath -Name 'yt-dlp'
    $ytdlpCli = (-not [string]::IsNullOrWhiteSpace($ytdlpPath)) -and
                (Test-RemCommand -Name 'yt-dlp' -Arguments @('--version'))
    $ytdlpModule = Test-RemPythonModule -Python $Python -Modules @('yt_dlp')
    $ytdlpOk = ($ytdlpCli -and $ytdlpModule)
    $ytdlpDetail = '不可用'
    if ($ytdlpOk) {
        $ytdlpDetail = (Invoke-RemCapture -FilePath $ytdlpPath -Arguments @('--version')).Output
    }
    elseif (-not $ytdlpModule) { $ytdlpDetail = 'Python 模块 yt_dlp 缺失' }
    elseif (-not $ytdlpCli) { $ytdlpDetail = 'PATH 中未找到 yt-dlp.exe' }
    [void]$results.Add([pscustomobject]@{
        Key = 'ytdlp'; Name = 'yt-dlp'; Tier = '必需'; Ok = $ytdlpOk; Detail = $ytdlpDetail
    })

    $ffmpegPath = Resolve-RemCommandPath -Name 'ffmpeg'
    $ffmpegOk = (Test-RemCommand -Name 'ffmpeg' -Arguments @('-version')) -and
                (Test-RemCommand -Name 'ffprobe' -Arguments @('-version'))
    $ffmpegDetail = '未找到 ffmpeg / ffprobe'
    if ($ffmpegOk) {
        $ffmpegDetail = (Invoke-RemCapture -FilePath $ffmpegPath -Arguments @('-version')).Output
        $ffmpegDetail = ($ffmpegDetail -replace '^ffmpeg version\s+', '').Split(' ')[0]
    }
    [void]$results.Add([pscustomobject]@{
        Key = 'ffmpeg'; Name = 'FFmpeg'; Tier = '必需'; Ok = $ffmpegOk; Detail = $ffmpegDetail
    })

    $nodePath = Resolve-RemCommandPath -Name 'node'
    $nodeOk = -not [string]::IsNullOrWhiteSpace($nodePath)
    $nodeDetail = '未找到（YouTube 部分格式可能受限）'
    if ($nodeOk) { $nodeDetail = (Invoke-RemCapture -FilePath $nodePath -Arguments @('--version')).Output }
    [void]$results.Add([pscustomobject]@{
        Key = 'node'; Name = 'Node.js'; Tier = '推荐'; Ok = $nodeOk; Detail = $nodeDetail
    })

    $playwrightOk = Test-RemPythonModule -Python $Python -Modules @('playwright.sync_api')
    $playwrightDetail = '未安装（抖音兜底不可用）'
    if ($playwrightOk) { $playwrightDetail = '已安装' }
    [void]$results.Add([pscustomobject]@{
        Key = 'playwright'; Name = 'Playwright'; Tier = '可选'; Ok = $playwrightOk; Detail = $playwrightDetail
    })

    $browser = Get-RemBrowserPath
    $browserOk = -not [string]::IsNullOrWhiteSpace($browser)
    $browserDetail = '未找到（抖音兜底不可用）'
    if ($browserOk) { $browserDetail = $browser }
    [void]$results.Add([pscustomobject]@{
        Key = 'browser'; Name = 'Chrome / Edge'; Tier = '可选'; Ok = $browserOk; Detail = $browserDetail
    })

    return $results
}

function Test-RemReady {
    param([string]$Python)
    if (-not (Test-RemPythonVersion -Python $Python -Major 3 -Minor 10)) { return $false }
    foreach ($tool in 'yt-dlp', 'ffmpeg', 'ffprobe') {
        if ([string]::IsNullOrWhiteSpace((Resolve-RemCommandPath -Name $tool))) { return $false }
    }
    return $true
}

function Wait-RemKey {
    param([string]$Message = '按任意键关闭窗口…')
    try {
        if ([Console]::IsInputRedirected) { return }
        Write-Host ''
        Write-Host $Message -ForegroundColor Yellow
        [void][Console]::ReadKey($true)
    }
    catch { }
}
