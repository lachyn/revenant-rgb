# Screenshot of the whole virtual screen (or a region) -> PNG. Usage: shot.ps1 out.png [x y w h]
param([string]$out, [int]$x = -1, [int]$y = 0, [int]$w = 0, [int]$h = 0)
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
Add-Type 'using System.Runtime.InteropServices; public static class D { [DllImport("user32.dll")] public static extern bool SetProcessDPIAware(); }'
[D]::SetProcessDPIAware() | Out-Null
if ($x -lt 0) { $b = [System.Windows.Forms.SystemInformation]::VirtualScreen; $x=$b.X; $y=$b.Y; $w=$b.Width; $h=$b.Height }
$bmp = New-Object System.Drawing.Bitmap $w, $h
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($x, $y, 0, 0, $bmp.Size)
$bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
"$out ${w}x${h} at $x,$y"
