"""Run a saved NX Python journal in the Windows VM; archive inputs and outputs."""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

from nx_lint import check as lint_check

CODE = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ['NX_PROJECT_ROOT']) if os.environ.get('NX_PROJECT_ROOT') else CODE
if not (ROOT / '03_jobs').is_dir():
    raise RuntimeError(
        f'NX_PROJECT_ROOT={ROOT} has no 03_jobs/ — point it at a project '
        'directory holding 03_jobs/ (jobs) and runs/ (evidence), or unset '
        'it to work directly in the toolkit.')
HOST = 'ansys-mechanical-vm'
REMOTE = 'C:/Users/hanne/Documents/OnlineMachiningNX'
NX = r'C:\Program Files\Siemens\NX2506\NXBIN\run_journal.exe'

# ssh/scp reserve exit code 255 for a connection/auth failure that never reached
# the remote side (vs. a remote command's own exit code, forwarded as-is) — so
# retrying on 255 specifically is safe even for a non-idempotent remote command:
# a 255 means it never ran. Observed transient 2026-09-07 ("Permission denied",
# "Connection closed") mid-session against this VM; both were exit 255.
SSH_CONNECTION_FAILURE = 255


def run_ssh(cmd, retries=2, backoff=2.0, **kwargs):
    """subprocess.run for an ssh/scp command, retrying only a connection-level
    (exit 255) failure. A command that reached the remote side and failed there
    keeps its own exit code and is never retried here."""
    for attempt in range(retries + 1):
        last_attempt = attempt == retries
        try:
            result = subprocess.run(cmd, **kwargs)
        except subprocess.CalledProcessError as error:
            if error.returncode != SSH_CONNECTION_FAILURE or last_attempt:
                raise
        else:
            if result.returncode != SSH_CONNECTION_FAILURE or last_attempt:
                return result
        time.sleep(backoff * (attempt + 1))


def powershell(script, **kwargs):
    encoded = base64.b64encode(("$ProgressPreference='SilentlyContinue'; " + script).encode('utf-16le')).decode()
    return run_ssh(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10',HOST,'powershell.exe -NoProfile -EncodedCommand '+encoded], **kwargs)


def scp(args, **kwargs):
    return run_ssh(['scp', '-q'] + args, **kwargs)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('job')
    parser.add_argument('--parameters', type=Path)
    parser.add_argument('--prepare-only', action='store_true', help='Upload only; play the printed journal path in visible NX')
    parser.add_argument(
        '--toolkit-job',
        action='store_true',
        help='Resolve the job below the toolkit 03_jobs/ even when NX_PROJECT_ROOT points at a thin project',
    )
    parser.add_argument('--no-lint', action='store_true', help='Skip nx_lint.py static checks (escape hatch for a false positive)')
    args=parser.parse_args()
    job_root = CODE / '03_jobs' if args.toolkit_job else ROOT / '03_jobs'
    job=(job_root/args.job).resolve()
    if not job.is_relative_to(job_root) or not job.is_file():
        parser.error(f'Job must exist inside {job_root}')
    source=job.read_bytes()
    if job.suffix == '.py':
        compile(source,str(job),'exec')
        if not args.no_lint:
            errors, warnings = lint_check(source.decode('utf-8'))
            for w in warnings:
                print('LINT WARNING:', w, flush=True)
            if errors:
                for e in errors:
                    print('LINT ERROR:', e, flush=True)
                parser.error(f'{len(errors)} lint error(s) — fix, or pass --no-lint to force upload anyway')
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
    job_label = str(job.relative_to(CODE if args.toolkit_job else ROOT))
    (local/'request.json').write_text(json.dumps({'host':HOST,'remote':remote,'job':job_label,'job_source':'toolkit' if args.toolkit_job else 'project','sha256':hashlib.sha256(source).hexdigest(),'parameters':params},indent=2))
    print('Run:',local,flush=True)
    powershell(f"New-Item -ItemType Directory -Force -Path '{remote}' | Out-Null",check=True)
    scp([str(local/archived_name),str(local/'parameters.json'),HOST+':'+remote+'/'],check=True)
    if args.prepare_only:
        (local/'outcome.json').write_text(json.dumps({'status':'prepared','execution':'interactive journal pending'},indent=2))
        print('Play this journal in visible NX:', remote+'/'+archived_name,flush=True)
        return 0
    with (local/'transport.log').open('wb') as log:
        result=powershell(f"Set-Location '{remote}'; & '{NX}' -nx '{remote}/{archived_name}' > '{remote}/stdout.txt' 2> '{remote}/stderr.txt'; $code=$LASTEXITCODE; Set-Content -Path '{remote}/exit-code.txt' -Value $code; exit $code",stdout=log,stderr=subprocess.STDOUT)
    fetch=scp(['-r',HOST+':'+remote,str(local/'remote')])
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
