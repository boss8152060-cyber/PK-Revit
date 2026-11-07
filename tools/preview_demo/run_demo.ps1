# เดโม 3D preview: รัน revotech.preview3d จริงด้วย IronPython 2.7 ของ pyRevit แล้ว render เป็น PNG
# ใช้: powershell -STA -File tools\preview_demo\run_demo.ps1 [-Out <โฟลเดอร์>] [-Script demo_scenes.py]
# ไม่ต้องมี Revit (WPF ล้วน) — ต้องมี pyRevit ติดตั้งที่ %APPDATA%\pyRevit-Master
param(
    [string]$Out = (Join-Path $PSScriptRoot "out"),
    [string]$Script = "demo_scenes.py"
)
$ErrorActionPreference = "Stop"
if ([System.Threading.Thread]::CurrentThread.GetApartmentState() -ne "STA") {
    & powershell.exe -STA -NoProfile -File $PSCommandPath -Out $Out -Script $Script
    exit $LASTEXITCODE
}
$eng = Join-Path $env:APPDATA "pyRevit-Master\bin\netfx\engines\IPY2712PR"
foreach ($n in "pyRevitLabs.Microsoft.Scripting", "pyRevitLabs.Microsoft.Dynamic",
              "pyRevitLabs.IronPython", "pyRevitLabs.IronPython.Modules") {
    [System.Reflection.Assembly]::LoadFrom((Join-Path $eng "$n.dll")) | Out-Null
}
$ext = (Resolve-Path (Join-Path $PSScriptRoot "..\..\src\PKRevit.extension")).Path
New-Item -ItemType Directory -Force $Out | Out-Null
$py = [IronPython.Hosting.Python]
$engine = $py::CreateEngine()
$scope = $engine.CreateScope()
$scope.SetVariable("EXT_ROOT", $ext)
$scope.SetVariable("OUT_DIR", (Resolve-Path $Out).Path)
$scope.SetVariable("DEMO_DIR", $PSScriptRoot)
$paths = $engine.GetSearchPaths()
$paths.Add((Join-Path $ext "lib"))
$paths.Add((Join-Path $PSScriptRoot "shims"))   # os/io จิ๋ว (engine ไม่มี stdlib)
$engine.SetSearchPaths($paths)
try {
    $engine.ExecuteFile((Join-Path $PSScriptRoot $Script), $scope) | Out-Null
} catch {
    $ex = $_.Exception
    while ($ex.InnerException) { $ex = $ex.InnerException }
    $eo = $engine.GetType().GetMethod("GetService").MakeGenericMethod([Microsoft.Scripting.Hosting.ExceptionOperations]).Invoke($engine, @(,[object[]]@()))
    Write-Host ($eo.FormatException($ex))
    exit 1
}
