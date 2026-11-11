param([string]$PythonExe)
$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
$taskPython = Join-Path $taskRoot 'work\venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { $taskPython = 'python' }
if ($PythonExe) { $taskPython = $PythonExe }
Set-Location -LiteralPath $taskRoot
$taskBuild = Join-Path ([System.IO.Path]::GetTempPath()) ('KP_MU_Build_' + [Guid]::NewGuid().ToString('N'))
$taskLicenses = Join-Path $taskBuild 'licenses'
& $taskPython "$taskRoot\work\collect_licenses.py" --destination $taskLicenses
if ($LASTEXITCODE -ne 0) { throw 'License collection failed' }
$taskDataFiles = @('catalog.json','i18n_en.json','mu500_defaults.json','check.svg','check_lcd.svg','down.svg','down_dark.svg','up.svg','up_dark.svg')
$taskDataArgs = foreach ($taskDataFile in $taskDataFiles) {
    '--add-data'
    "$taskRoot\kp_mu_editor\data\${taskDataFile};kp_mu_editor/data"
}
& $taskPython -m PyInstaller --noconfirm --windowed --name KP_YAMAHA_MUeditor `
  --distpath "$taskBuild\dist" --workpath "$taskBuild\work" --specpath "$taskBuild" `
  @taskDataArgs `
  --copy-metadata mido --copy-metadata PySide6 `
  --exclude-module PyQt6 --exclude-module PyQt5 --exclude-module tkinter `
  --exclude-module numpy --exclude-module scipy --exclude-module matplotlib --exclude-module pymupdf `
  "$taskRoot\run_editor.pyw"
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed' }
$taskFresh = Join-Path $taskBuild 'dist\KP_YAMAHA_MUeditor'
# Qt on Windows 11 uses the Windows ICU API. PyInstaller can pick an
# incompatible, version-suffixed ICU from another application on PATH.
foreach ($taskName in @('icuuc.dll','icudt78.dll')) {
    $taskUnwanted = Join-Path $taskFresh "_internal\$taskName"
  if (Test-Path -LiteralPath $taskUnwanted) { Remove-Item -LiteralPath $taskUnwanted -Force }
}
Copy-Item -LiteralPath "$taskRoot\README.md", "$taskRoot\README_EN.md", "$taskRoot\THIRD_PARTY_NOTICES.md", "$taskRoot\LICENSE" -Destination $taskFresh -Force
Copy-Item -LiteralPath "$taskRoot\docs", $taskLicenses -Destination $taskFresh -Recurse -Force
$taskImages = Join-Path $taskFresh 'images'
New-Item -ItemType Directory -Path $taskImages -Force | Out-Null
Copy-Item -LiteralPath "$taskRoot\images\kp_yamaha_mu_editor.jpg" -Destination $taskImages -Force
& $taskPython "$taskRoot\work\package_release.py" --app-dir $taskFresh
if ($LASTEXITCODE -ne 0) { throw 'Release packaging failed' }
$taskOutput = Join-Path $taskRoot 'outputs'
$taskDist = Join-Path $taskOutput 'KP_YAMAHA_MUeditor'
$taskBackup = Join-Path $taskRoot ('work\before_build_' + (Get-Date -Format 'yyyyMMdd_HHmmss') + '_' + [Guid]::NewGuid().ToString('N'))
foreach ($taskPath in @($taskDist,$taskBackup)) {
    $taskAbsolute = [System.IO.Path]::GetFullPath($taskPath)
    if (-not $taskAbsolute.StartsWith($taskRoot + [System.IO.Path]::DirectorySeparatorChar,[System.StringComparison]::OrdinalIgnoreCase)) { throw 'Build target escaped project directory' }
}
if (Test-Path -LiteralPath $taskDist) { Move-Item -LiteralPath $taskDist -Destination $taskBackup }
try {
    New-Item -ItemType Directory -Path $taskOutput -Force | Out-Null
    Copy-Item -LiteralPath $taskFresh -Destination $taskOutput -Recurse -Force
    if (Test-Path -LiteralPath "$taskBackup\userdata") {
        Copy-Item -LiteralPath "$taskBackup\userdata" -Destination $taskDist -Recurse -Force
    }
} catch {
    if (Test-Path -LiteralPath $taskDist) {
        $taskFailed = $taskBackup + '_failed'
        if (-not ([System.IO.Path]::GetFullPath($taskFailed)).StartsWith($taskRoot + [System.IO.Path]::DirectorySeparatorChar,[System.StringComparison]::OrdinalIgnoreCase)) { throw 'Rollback target escaped project directory' }
        Move-Item -LiteralPath $taskDist -Destination $taskFailed
    }
    if (Test-Path -LiteralPath $taskBackup) { Move-Item -LiteralPath $taskBackup -Destination $taskDist }
    throw
}
