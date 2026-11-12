# PyInstaller recipe for the installed Windows program. Build from the repository root:
#   set PLAYWRIGHT_BROWSERS_PATH=0
#   python -m playwright install --only-shell chromium
#   pyinstaller packaging/council-archive.spec --noconfirm
# The browser is installed inside the playwright package first, so it is bundled with the program.
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

root = Path(SPECPATH).parent
datas = [(str(root/'templates'), 'templates'), (str(root/'VERSION'), '.'),
         (str(root/'START-HERE.md'), '.'), (str(root/'LICENSE'), '.')]
binaries = []; hiddenimports = []
for package in ('playwright', 'pypdfium2', 'pypdfium2_raw'):
    d, b, h = collect_all(package)
    datas += d; binaries += b; hiddenimports += h

a = Analysis([str(root/'app.py')], pathex=[str(root)], binaries=binaries, datas=datas,
             hiddenimports=hiddenimports + ['ocr', 'ocr_worker', 'late', 'problems', 'exports', 'planning', 'readers'],
             excludes=['tkinter', 'tests'])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='Council Archive', console=True,
          icon=str(root/'packaging'/'icon.ico'))
coll = COLLECT(exe, a.binaries, a.datas, name='Council Archive')
