$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw '请先按 README 创建项目独立环境。' }
$env:PYTHONUTF8 = '1'
$logDirectory = Join-Path $projectRoot 'work'
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
$recordPath = Join-Path $logDirectory 'server-processes.json'
if (Test-Path -LiteralPath $recordPath) {
    $existing = Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json
    $running = @($existing.processes | Where-Object { $p = Get-Process -Id $_.id -ErrorAction SilentlyContinue; $p -and $p.StartTime.ToUniversalTime().ToString('o') -eq $_.started_at -and $p.Path -eq $_.executable })
    if ($running.Count -gt 0) {
        Write-Output '已有启动记录中的进程仍在运行。页面：http://127.0.0.1:8501；重启前请先运行 stop.ps1。'
        return
    }
}
foreach ($port in @(8000,8501)) {
    $probe = [System.Net.Sockets.TcpClient]::new()
    try { $probe.Connect('127.0.0.1',$port); throw "本机端口 $port 已被占用，请先关闭占用该端口的服务。" }
    catch [System.Net.Sockets.SocketException] { if ($_.Exception.GetBaseException().SocketErrorCode -ne [System.Net.Sockets.SocketError]::ConnectionRefused) { throw } }
    finally { $probe.Dispose() }
}
$started = @()
try {
    $started += Start-Process -FilePath $pythonPath -ArgumentList @('-m','data_agent.cli','serve') -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDirectory 'api.log') -RedirectStandardError (Join-Path $logDirectory 'api-error.log')
    $started += Start-Process -FilePath $pythonPath -ArgumentList @('-m','streamlit','run','src/data_agent/ui.py','--server.address','127.0.0.1','--server.port','8501','--server.headless','true','--browser.gatherUsageStats','false') -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDirectory 'ui.log') -RedirectStandardError (Join-Path $logDirectory 'ui-error.log')
    $record = @{ project_root=$projectRoot; processes=@($started | ForEach-Object { @{ id=$_.Id; started_at=$_.StartTime.ToUniversalTime().ToString('o'); executable=$pythonPath } }) }
    $record | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $recordPath -Encoding utf8
    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        if (@($started | Where-Object HasExited).Count -gt 0) { throw '服务启动失败，请检查 work 中的日志。' }
        try {
            $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 1
            $uiHealth = Invoke-WebRequest -Uri 'http://127.0.0.1:8501/_stcore/health' -UseBasicParsing -TimeoutSec 1
            if ($health.status -eq 'ok' -and $uiHealth.StatusCode -eq 200) { $ready = $true; break }
        }
        catch { Start-Sleep -Milliseconds 200 }
    }
    if (-not $ready) { throw '服务未能通过启动检查，请查看 work 中的日志。' }
    Write-Output '已在后台启动。页面：http://127.0.0.1:8501；接口：http://127.0.0.1:8000/docs'
    Write-Output '可以关闭此终端。结束演示时运行：powershell -ExecutionPolicy Bypass -File .\stop.ps1'
}
catch {
    foreach ($startedProcess in $started) {
        if (-not $startedProcess.HasExited) { & "$env:SystemRoot\System32\taskkill.exe" /PID $startedProcess.Id /T /F | Out-Null }
    }
    throw
}
