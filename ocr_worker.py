"""One isolated page render and local Tesseract invocation; originals are read-only."""
import json,math,os,shutil,subprocess,sys,tempfile
from pathlib import Path

def engine():
    candidates=[os.environ.get('TESSERACT_CMD',''),shutil.which('tesseract')]
    for base in [os.environ.get('ProgramFiles',''),os.environ.get('LOCALAPPDATA','')]:
        if base:candidates.extend([str(Path(base)/'Tesseract-OCR/tesseract.exe'),str(Path(base)/'Programs/Tesseract-OCR/tesseract.exe')])
    return next((x for x in candidates if x and Path(x).is_file()),None)

def recognise(pdf_path,page_number):
    import pypdfium2 as pdfium
    exe=engine()
    if not exe:raise RuntimeError('Tesseract is not installed. Follow the OCR setup instructions in START-HERE.md.')
    with tempfile.TemporaryDirectory(prefix='council-ocr-') as tmp:
        doc=pdfium.PdfDocument(pdf_path)
        try:
            page=doc[page_number-1]
            try:
                w,h=page.get_size();scale=min(300/72,math.sqrt(20000000/max(w*h,1)))
                bitmap=page.render(scale=scale)
                try:
                    image=bitmap.to_pil();image.save(Path(tmp)/'page.png');image.close()
                finally:bitmap.close()
            finally:page.close()
        finally:doc.close()
        r=subprocess.run([exe,str(Path(tmp)/'page.png'),'stdout','-l','eng','--psm','3'],capture_output=True,timeout=90)
        if r.returncode:raise RuntimeError(r.stderr.decode('utf-8',errors='replace')[-1500:])
        return r.stdout.decode('utf-8',errors='replace').strip()

if __name__=='__main__':
    try:result=dict(text=recognise(sys.argv[1],int(sys.argv[2])),error='')
    except Exception as e:result=dict(text='',error=str(e))
    Path(sys.argv[3]).write_text(json.dumps(result),encoding='utf-8')
