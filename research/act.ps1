# act.ps1 "label" "cmd1;cmd2;..." [shotName]  -> sends commands to clicker, logs label w/ timestamp, optional window screenshot
param([string]$label, [string]$cmds, [string]$shot = "")
$t = Join-Path $PSScriptRoot 'cmd.txt'
$ack = Join-Path $PSScriptRoot 'ack.txt'
$before = Get-Content $ack -ErrorAction SilentlyContinue
"focus;sleep 300;$cmds" -split ';' | Set-Content $t
for ($i = 0; $i -lt 100; $i++) { Start-Sleep -m 100; if (-not (Test-Path $t) -and (Get-Content $ack) -ne $before) { break } }
"$(Get-Date -f HH:mm:ss) ACTION $label" | Add-Content (Join-Path (Split-Path $PSScriptRoot) 'actions.log')
Start-Sleep -m 1500
if ($shot) { & (Join-Path $PSScriptRoot 'shot.ps1') $shot 790 376 980 640 | Out-Null }
"ok $label"
