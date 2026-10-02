

$ErrorActionPreference = 'Stop'

try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false) } catch { }

$env:PYTHONUTF8 = '1'

. (Join-Path $PSScriptRoot 'runtime.ps1')

function Show-RemLaunchStatus {
    param($Status)
    foreach ($item in $Status) {
        $mark = '[缺失]'
        $color = 'Yellow'
        if ($item.Ok) { $mark = '[就绪]'; $color = 'DarkGray' }
        elseif ($item.Tier -eq '必需') { $color = 'Red' }
        Write-Host ("    {0} {1}（{2}）  {3}" -f $mark, $item.Name, $item.Tier, $item.Detail) -ForegroundColor $color
    }
}

$appEntry = Join-Path $PSScriptRoot 'download_cli.py'
$exitCode = 0

try {
    if (-not (Test-Path -LiteralPath $appEntry)) {
        throw (New-Object System.Exception "缺少主程序文件：$appEntry")
    }

    Update-RemPath
    $python = Find-RemPython
    if ($python) { Add-RemPythonScriptsToPath -Python $python }

    if (-not (Test-RemReady -Python $python)) {

        Write-Host ''
        Write-Host '正在检查运行依赖…' -ForegroundColor Cyan
        $status = Get-RemRequirementStatus -Python $python

        $missingRequired = @($status | Where-Object { $_.Tier -eq '必需' -and -not $_.Ok })
        $missingOptional = @($status | Where-Object { $_.Tier -ne '必需' -and -not $_.Ok })

        if ($missingRequired.Count -gt 0) {
            Write-Host ''
            Write-Host ("缺少必需组件：{0}" -f (($missingRequired | ForEach-Object { $_.Name }) -join '、')) -ForegroundColor Yellow
            Write-Host '正在自动安装，可能需要几分钟，请勿关闭窗口…' -ForegroundColor Yellow

            $installer = Join-Path $PSScriptRoot 'install_dependencies.ps1'
            if (-not (Test-Path -LiteralPath $installer)) {
                throw (New-Object System.Exception "缺少依赖安装脚本：$installer")
            }
            $installerHost = Resolve-RemCommandPath -Name 'powershell'
            if ([string]::IsNullOrWhiteSpace($installerHost)) {
                $installerHost = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
            }

            [void](Invoke-RemNative -FilePath $installerHost -Arguments @(
                '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $installer, '-NoPause'))

            Update-RemPath
            $python = Find-RemPython
            if ($python) { Add-RemPythonScriptsToPath -Python $python }
            $status = Get-RemRequirementStatus -Python $python
            $missingRequired = @($status | Where-Object { $_.Tier -eq '必需' -and -not $_.Ok })
        }

        if ($missingRequired.Count -gt 0) {
            Write-Host ''
            Write-Host '依赖仍未就绪，无法启动。当前状态：' -ForegroundColor Red
            Show-RemLaunchStatus -Status $status
            throw (New-Object System.Exception '必需依赖缺失')
        }

        if ($missingOptional.Count -gt 0) {
            Write-Host ''
            Write-Host '以下可选组件未就绪，不影响正常使用：' -ForegroundColor Yellow
            foreach ($item in $missingOptional) {
                Write-Host ("    - {0}：{1}" -f $item.Name, $item.Detail) -ForegroundColor Yellow
            }
            Write-Host ''
        }
    }

    & $python $appEntry @args
    $exitCode = $LASTEXITCODE
    if ($null -eq $exitCode) { $exitCode = 0 }
}
catch {
    Write-Host ''
    Write-Host '============================================================' -ForegroundColor Red
    Write-Host 'Rem Downloader 启动失败' -ForegroundColor Red
    Write-Host ("原因：{0}" -f $_.Exception.Message) -ForegroundColor Red
    Write-Host ''
    Write-Host '可以尝试：' -ForegroundColor Yellow
    Write-Host '  1. 双击 install_dependencies.cmd 重新安装依赖，再双击 run.cmd。' -ForegroundColor Yellow
    Write-Host '  2. 确认 Rem Downloader 的所有文件都在同一个文件夹内，没有被单独移动。' -ForegroundColor Yellow
    Write-Host '  3. 若提示 Python 缺失，请安装 Python 3.10 或更高版本，安装时勾选 "Add python.exe to PATH"。' -ForegroundColor Yellow
    Write-Host '============================================================' -ForegroundColor Red
    $exitCode = 1
}
finally {

    if ($exitCode -ne 0 -and $exitCode -ne 130) { Wait-RemKey }
}

exit $exitCode
