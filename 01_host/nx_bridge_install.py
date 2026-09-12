"""Build the NX dispatcher and start visible NX with it loaded automatically.

NX loads libraries found in the `startup` folder of a directory listed in the
custom directory file (UGII_CUSTOM_DIRECTORY_FILE). Unlike USER_STARTUP, which
requires a native `ufsta` export, this path accepts managed NX Open assemblies.
Nothing outside the project directory and one scheduled task is modified.
"""
import subprocess
import sys
from nx_remote import ROOT, CODE, HOST, REMOTE, powershell

NXBIN = r'C:\Program Files\Siemens\NX2506\NXBIN'
BRIDGE = REMOTE + '/bridge'

powershell(f"New-Item -ItemType Directory -Force '{BRIDGE}','{BRIDGE}/startup' | Out-Null", check=True)
for name in ['VisibleBridge.cs', 'start-visible.cmd']:
    subprocess.run(['scp', '-q', str(CODE / '02_bridge' / name), HOST + ':' + BRIDGE + '/' + name], check=True)

powershell(rf"""
$ErrorActionPreference='Stop'
$bridge='{BRIDGE}'.Replace('/','\')
Set-Content -Encoding ASCII -Path "$bridge\custom_dirs.dat" -Value $bridge
& 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe' /nologo /target:library `
  "/out:$bridge\startup\VisibleBridge.dll" `
  '/reference:{NXBIN}\managed\NXOpen.dll' `
  '/reference:{NXBIN}\managed\NXOpen.Utilities.dll' `
  /reference:System.Windows.Forms.dll `
  "$bridge\VisibleBridge.cs"
if($LASTEXITCODE -ne 0) {{ exit $LASTEXITCODE }}
Remove-Item "$bridge\..\bridge-loaded.log","$bridge\..\bridge-status.json" -ErrorAction SilentlyContinue
$action=New-ScheduledTaskAction -Execute 'cmd.exe' -Argument "/c `"$bridge\start-visible.cmd`""
$principal=New-ScheduledTaskPrincipal -UserId 'hanne' -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'OnlineMachining-NX-Bridge' -Action $action -Principal $principal `
  -Description 'Visible NX with the project dispatcher loaded from a custom startup directory' -Force | Out-Null
Start-ScheduledTask -TaskName 'OnlineMachining-NX-Bridge'
'build ok; visible NX requested'
""", check=True)
