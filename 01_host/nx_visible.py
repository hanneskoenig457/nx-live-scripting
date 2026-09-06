"""Start NX on the logged-in Windows desktop, or collect a prepared journal run."""
import argparse
import json
import subprocess
from pathlib import Path

from nx_remote import HOST, REMOTE, ROOT, powershell


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['start', 'collect', 'status'])
    parser.add_argument('--run', help='Directory name under runs/nx, required for collect')
    args = parser.parse_args()
    if args.action == 'start':
        return powershell(r"""
$ErrorActionPreference='Stop'
$existing=Get-Process ugraf -ErrorAction SilentlyContinue | Where-Object {$_.SessionId -gt 0}
if (-not $existing) {
  $action=New-ScheduledTaskAction -Execute 'C:\Program Files\Siemens\NX2506\NXBIN\ugraf.exe' -Argument '-nx'
  $principal=New-ScheduledTaskPrincipal -UserId 'hanne' -LogonType Interactive -RunLevel Limited
  Register-ScheduledTask -TaskName 'OnlineMachining-NX-Interactive' -Action $action -Principal $principal -Description 'On-demand visible NX for Online Machining' -Force | Out-Null
  Start-ScheduledTask -TaskName 'OnlineMachining-NX-Interactive'
}
Get-Process ugraf -ErrorAction SilentlyContinue | Select-Object Id,SessionId,Responding | ConvertTo-Json
""").returncode
    if args.action == 'status':
        return powershell("Get-Process ugraf -ErrorAction SilentlyContinue | Select-Object Id,SessionId,Responding | ConvertTo-Json").returncode
    if not args.run or Path(args.run).name != args.run:
        parser.error('--run must be a single run-directory name')
    local = ROOT / 'runs/nx' / args.run
    request = json.loads((local / 'request.json').read_text())
    remote = REMOTE + '/' + args.run
    if request['remote'] != remote or request['host'] != HOST:
        parser.error('Run manifest does not match configured VM')
    destination = local / 'remote'
    destination.mkdir(exist_ok=True)
    # Copy the contents, so repeated collection never introduces a nested directory.
    subprocess.run(['scp', '-q', '-r', HOST + ':' + remote + '/.', str(destination)], check=True)
    report = destination / 'result.json'
    if not report.exists():
        print('Journal has not written a result yet; no successful execution claimed.')
        return 1
    data = json.loads(report.read_text(encoding='utf-8-sig'))
    execution_file = destination / 'bridge-execution.json'
    execution = json.loads(execution_file.read_text()) if execution_file.exists() else None
    if execution is not None and execution.get('execution_ok') is not True:
        print(json.dumps(execution, indent=2))
        return 1
    print(json.dumps(data, indent=2))
    (local / 'outcome.json').write_text(json.dumps({
        'execution': 'interactive journal', 'api_ok': data.get('ok') is True,
        'visual_validation': 'pending',
    }, indent=2))
    return 0 if data.get('ok') is True else 1


if __name__ == '__main__':
    raise SystemExit(main())
