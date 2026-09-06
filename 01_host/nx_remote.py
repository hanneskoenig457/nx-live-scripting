"""Run a saved NX Python journal in the Windows VM; archive inputs and outputs."""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[1]
HOST = 'ansys-mechanical-vm'
REMOTE = 'C:/Users/hanne/Documents/OnlineMachiningNX'
NX = r'C:\Program Files\Siemens\NX2506\NXBIN\run_journal.exe'

def powershell(script, **kwargs):
    encoded = base64.b64encode(("$ProgressPreference='SilentlyContinue'; " + script).encode('utf-16le')).decode()
    return subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10',HOST,'powershell.exe -NoProfile -EncodedCommand '+encoded], **kwargs)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('job')
    parser.add_argument('--parameters', type=Path)
    parser.add_argument('--prepare-only', action='store_true', help='Upload only; play the printed journal path in visible NX')
    args=parser.parse_args()
    job=(ROOT/'03_jobs'/args.job).resolve()
    if not job.is_relative_to(ROOT/'03_jobs') or not job.is_file():
        parser.error('Job must exist inside 03_jobs')
    source=job.read_bytes()
    if job.suffix == '.py':
        compile(source,str(job),'exec')
    elif job.suffix != '.cs':
        parser.error('Expected .py or .cs journal')
    archived_name = 'job' + job.suffix
    params=json.loads(args.parameters.read_text()) if args.parameters else {}
    key=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]
    local=ROOT/'runs/nx'/key
    local.mkdir(parents=True)
    remote=REMOTE+'/'+key
    (local/archived_name).write_bytes(source)
    (local/'parameters.json').write_text(json.dumps(params,indent=2))
    (local/'request.json').write_text(json.dumps({'host':HOST,'remote':remote,'job':str(job.relative_to(ROOT)),'sha256':hashlib.sha256(source).hexdigest(),'parameters':params},indent=2))
    print('Run:',local,flush=True)
    powershell(f"New-Item -ItemType Directory -Force -Path '{remote}' | Out-Null",check=True)
    subprocess.run(['scp','-q',str(local/archived_name),str(local/'parameters.json'),HOST+':'+remote+'/'],check=True)
    if args.prepare_only:
        (local/'outcome.json').write_text(json.dumps({'status':'prepared','execution':'interactive journal pending'},indent=2))
        print('Play this journal in visible NX:', remote+'/'+archived_name,flush=True)
        return 0
    with (local/'transport.log').open('wb') as log:
        result=powershell(f"Set-Location '{remote}'; & '{NX}' -nx '{remote}/{archived_name}' > '{remote}/stdout.txt' 2> '{remote}/stderr.txt'; $code=$LASTEXITCODE; Set-Content -Path '{remote}/exit-code.txt' -Value $code; exit $code",stdout=log,stderr=subprocess.STDOUT)
    fetch=subprocess.run(['scp','-q','-r',HOST+':'+remote,str(local/'remote')])
    ok=False
    report=local/'remote/result.json'
    if report.exists():
        # NX' embedded Python writes text in the Windows ANSI code page unless the
        # job asks for UTF-8, so a job that reports German text lands as cp1252.
        raw=report.read_bytes()
        for encoding in ('utf-8-sig','cp1252'):
            try:
                data=json.loads(raw.decode(encoding))
                break
            except UnicodeDecodeError:
                continue
        print(json.dumps(data,indent=2))
        ok=data.get('ok') is True
    (local/'outcome.json').write_text(json.dumps({'ok':ok and result.returncode==0 and fetch.returncode==0,'ssh_exit':result.returncode,'fetch_exit':fetch.returncode},indent=2))
    if not ok:
        for name in ('stdout.txt','stderr.txt'):
            p=local/'remote'/name
            if p.exists():
                b=p.read_bytes()
                print(b.decode('utf-16' if b.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8',errors='replace')[-5000:])
    return 0 if ok and result.returncode==0 and fetch.returncode==0 else 1

if __name__=='__main__':
    raise SystemExit(main())
