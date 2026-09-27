"""Patch the original or updated archive app without replacing its settings."""
from pathlib import Path
from datetime import datetime
import shutil

OLD="texts.append((num, page.extract_text() or ''))"
NEW="texts.append((num, (page.extract_text() or '').encode('utf-8', errors='replace').decode('utf-8')))"

def repair(folder):
    path=Path(folder)/'archive.py'
    if not path.exists():raise RuntimeError('Copy BOTH repair files beside archive.py in your existing app folder.')
    original=path.read_text(encoding='utf-8')
    if NEW in original:
        print('This repair is already installed.');return
    if original.count(OLD)!=1:raise RuntimeError('This archive.py differs from the expected version. No files have been changed.')
    fixed=original.replace(OLD,NEW)
    compile(fixed,str(path),'exec')
    backup=path.with_name('archive.py.before-unicode-repair-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    shutil.copy2(path,backup)
    temp=path.with_suffix('.repair.tmp');temp.write_text(fixed,encoding='utf-8');temp.replace(path)
    print('Repair installed. Your PDFs, settings and database have not been changed.')
    print('Original code backed up as '+backup.name)

if __name__=='__main__':
    try:repair(Path(__file__).resolve().parent)
    except Exception as e:
        print('Repair stopped: '+str(e));raise SystemExit(1)
