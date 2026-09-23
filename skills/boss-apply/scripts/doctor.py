#!/usr/bin/env python3
"""Read-only local readiness report; no installation, browser access or sending."""
import json, os, platform, socket, sqlite3, sys
from pathlib import Path

def report():
    with socket.socket() as s:
        try:
            s.bind(('127.0.0.1',18764)); port=18764
        except OSError:
            s.bind(('127.0.0.1',0)); port=s.getsockname()[1]
    base=Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData/Local')) if os.name=='nt' else Path.home()/'.local/share'
    return {'python':sys.executable,'pythonVersion':platform.python_version(),'sqliteVersion':sqlite3.sqlite_version,'suggestedPort':port,'suggestedDataRoot':str(base/'boss-apply'),'browserAndLogin':'must_check_with_computer_use','fallback':'computer_use_only','mutationsPerformed':False}
if __name__=='__main__': print(json.dumps(report(),ensure_ascii=False,indent=2))
