$ErrorActionPreference = 'Stop'
$sceneRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $sceneRoot
if (-not (Test-Path -LiteralPath '.env.local')) { throw '请先按 README 配置 .env.local' }
if (-not (Test-Path -LiteralPath 'bin/scene1.exe')) { & go build -o bin/scene1.exe ./cmd/scene1; if ($LASTEXITCODE -ne 0) { throw 'build failed' } }
$scenePids = @()
foreach ($sceneMode in @('shop', 'mock')) {
    $sceneProc = Start-Process -FilePath "$sceneRoot/bin/scene1.exe" -ArgumentList @('-mode', $sceneMode, '-env', '.env.local') -WorkingDirectory $sceneRoot -WindowStyle Hidden -RedirectStandardOutput "$sceneRoot/bin/local-$sceneMode.log" -RedirectStandardError "$sceneRoot/bin/local-$sceneMode-error.log" -PassThru
    $scenePids += @{ mode = $sceneMode; pid = $sceneProc.Id; executable = "$sceneRoot/bin/scene1.exe" }
}
$scenePids | ConvertTo-Json | Set-Content -LiteralPath "$sceneRoot/bin/local-pids.json" -Encoding utf8
Write-Output '已启动本地教学预览；商城 http://127.0.0.1:18080 ，模拟渠道18081。登录密码取自 .env.local 的 SCENE1_PASSWORD。'
