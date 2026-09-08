"""Dispatch an archived job into the visible NX bridge; never falls back to batch."""
import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from nx_remote import ROOT, REMOTE, HOST, powershell, scp


def status():
    response = powershell(f"Get-Content '{REMOTE}/bridge-status.json' -Raw", capture_output=True, text=True, check=True)
    return json.loads(response.stdout.lstrip('\ufeff'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['status', 'submit', 'stop'])
    parser.add_argument('--run')
    parser.add_argument('--wait', type=int, default=0, help='Seconds to wait; timeout does not cancel or resubmit')
    args = parser.parse_args()
    state = status()
    print(json.dumps(state, indent=2), flush=True)
    if args.action == 'status':
        return 0
    if args.action == 'stop':
        powershell(f"Set-Content '{REMOTE}/bridge-stop' 'stop'", check=True)
        return 0
    # An SSH round trip to the VM costs well under a second, so the tolerance is not
    # about latency: it only has to rule out a dispatcher whose timer has died.
    if state['state'] != 'ready' or state['session_id'] == 0 or abs(time.time()-state['heartbeat']) > 60:
        parser.error('Visible bridge not ready or heartbeat stale; no job submitted')
    if not args.run or Path(args.run).name != args.run:
        parser.error('--run must name a prepared run')
    local = ROOT/'runs/nx'/args.run
    manifest = json.loads((local/'request.json').read_text())
    remote = REMOTE+'/'+args.run
    if manifest['remote'] != remote or manifest['host'] != HOST:
        parser.error('Manifest target mismatch')
    sha = hashlib.sha256((local/'job.py').read_bytes()).hexdigest()
    if sha != manifest['sha256']:
        parser.error('Archived source was modified')
    if (local/'dispatch.json').exists():
        parser.error('Run already submitted or attempted; inspect its state, do not blindly replay')
    request = {'job': remote+'/job.py', 'sha256': sha}
    (local/'dispatch.json').write_text(json.dumps(request,indent=2))
    (local/'dispatch.request').write_text(remote.replace('/', '\\')+'\\job.py\n'+sha+'\n')
    upload = REMOTE+'/queue-dotnet/'+args.run+'.upload'
    scp([str(local/'dispatch.request'),HOST+':'+upload],check=True)
    powershell(f"$ErrorActionPreference='Stop'; Move-Item '{upload}' '{REMOTE}/queue-dotnet/{args.run}.ready'",check=True)
    print('Submitted once:',args.run,flush=True)
    deadline=time.monotonic()+args.wait
    while args.wait and time.monotonic()<deadline:
        check=powershell(f"Test-Path '{remote}/bridge-execution.json'",capture_output=True,text=True,check=True)
        if check.stdout.strip()=='True':
            return subprocess.run([sys.executable,str(ROOT/'01_host/nx_visible.py'),'collect','--run',args.run]).returncode
        time.sleep(1)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
