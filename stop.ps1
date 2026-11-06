$ErrorActionPreference = 'Stop'
$recordPath = Join-Path $PSScriptRoot 'work\server-processes.json'
if (-not (Test-Path -LiteralPath $recordPath)) { Write-Output '没有本项目启动的服务记录。'; return }
$record = Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json
if ($record.project_root -ne $PSScriptRoot) { throw '服务记录不属于当前项目，未停止任何进程。' }
foreach ($item in $record.processes) {
    $process = Get-Process -Id $item.id -ErrorAction SilentlyContinue
    if ($process -and $process.StartTime.ToUniversalTime().ToString('o') -eq $item.started_at -and $process.Path -eq $item.executable) {
        & "$env:SystemRoot\System32\taskkill.exe" /PID $process.Id /T /F | Out-Null
        if ($LASTEXITCODE -ne 0) { throw ('停止进程失败：' + $process.Id) }
        Write-Output ('已停止本项目进程 ' + $process.Id)
    }
}
