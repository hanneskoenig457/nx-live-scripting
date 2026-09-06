"""Read-only NX batch execution probe. No model is opened or modified."""
import json
import sys
import traceback
from pathlib import Path

def main():
    result={}
    try:
        import NXOpen
        import NXOpen.UF
        import NXOpen.Drawings
        session=NXOpen.Session.GetSession()
        result={'ok':True,'python':sys.version,'work_part':str(session.Parts.Work),'nxopen_file':getattr(NXOpen,'__file__',None),'drawing_manager':hasattr(NXOpen,'Drawings'),'session_methods':[x for x in dir(session) if 'Version' in x]}
    except Exception:
        result={'ok':False,'error':traceback.format_exc()}
    Path('result.json').write_text(json.dumps(result,indent=2))

if __name__=='__main__':
    main()
