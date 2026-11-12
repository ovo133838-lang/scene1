$ErrorActionPreference = 'Stop'
$sceneRoot = Split-Path -Parent $PSScriptRoot
$scenePidFile = Join-Path $sceneRoot 'bin/local-pids.json'
if (Test-Path -LiteralPath $scenePidFile) {
    foreach ($sceneSaved in (Get-Content -Raw -LiteralPath $scenePidFile | ConvertFrom-Json)) {
        $sceneProc = Get-Process -Id $sceneSaved.pid -ErrorAction SilentlyContinue
        if ($sceneProc -and $sceneProc.Path -eq [IO.Path]::GetFullPath($sceneSaved.executable)) { Stop-Process -Id $sceneProc.Id }
    }
}
Write-Output '仅停止本脚本记录且路径匹配的题1进程；数据库和Redis保持运行。'
