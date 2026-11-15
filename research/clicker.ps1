# Elevated helper: executes mouse/keyboard commands written to cmd.txt, one per line.
# Commands:  click X Y | dclick X Y | move X Y | drag X1 Y1 X2 Y2 | key TEXT | focus | quit
$dir = Split-Path $MyInvocation.MyCommand.Path
$cmdFile = Join-Path $dir 'cmd.txt'
$ackFile = Join-Path $dir 'ack.txt'
Add-Type @'
using System; using System.Runtime.InteropServices;
public static class M {
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint x, uint y, uint d, IntPtr e);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  public static void Down(){ mouse_event(2,0,0,0,IntPtr.Zero);} public static void Up(){ mouse_event(4,0,0,0,IntPtr.Zero);}
}
'@
[M]::SetProcessDPIAware() | Out-Null
Add-Type -AssemblyName System.Windows.Forms
Remove-Item $cmdFile -ErrorAction SilentlyContinue
"ready" | Set-Content $ackFile
while ($true) {
  if (Test-Path $cmdFile) {
    $lines = Get-Content $cmdFile; Remove-Item $cmdFile
    foreach ($l in $lines) {
      $a = $l -split ' '
      switch ($a[0]) {
        'click'  { [M]::SetCursorPos([int]$a[1],[int]$a[2]); Start-Sleep -m 80; [M]::Down(); Start-Sleep -m 60; [M]::Up() }
        'dclick' { [M]::SetCursorPos([int]$a[1],[int]$a[2]); 1..2 | % { [M]::Down(); Start-Sleep -m 40; [M]::Up(); Start-Sleep -m 60 } }
        'move'   { [M]::SetCursorPos([int]$a[1],[int]$a[2]) }
        'drag'   { [M]::SetCursorPos([int]$a[1],[int]$a[2]); Start-Sleep -m 80; [M]::Down(); Start-Sleep -m 100
                   1..10 | % { [M]::SetCursorPos([int]$a[1] + ([int]$a[3]-[int]$a[1])*$_/10, [int]$a[2] + ([int]$a[4]-[int]$a[2])*$_/10); Start-Sleep -m 30 }
                   [M]::Up() }
        'key'    { [System.Windows.Forms.SendKeys]::SendWait(($a[1..($a.Count-1)] -join ' ')) }
        'focus'  { $p = Get-Process | ? { $_.ProcessName -like '*Revenant*' -and $_.MainWindowHandle -ne 0 } | select -First 1
                   if ($p) { [M]::ShowWindow($p.MainWindowHandle, 9) | Out-Null; [M]::SetForegroundWindow($p.MainWindowHandle) | Out-Null } }
        'sleep'  { Start-Sleep -m ([int]$a[1]) }
        'quit'   { "bye" | Set-Content $ackFile; exit }
      }
      Start-Sleep -m 150
    }
    "done $(Get-Date -f HH:mm:ss.fff)" | Set-Content $ackFile
  }
  Start-Sleep -m 100
}
