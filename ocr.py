import json,re,subprocess,sys,tempfile,time
from pathlib import Path
from datetime import datetime,timezone
from ocr_worker import engine

def initialise(a):
    with a.connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS ocr_pages(path TEXT, fingerprint TEXT, page INTEGER, body TEXT, status TEXT, error TEXT, checked TEXT, PRIMARY KEY(path,fingerprint,page))')

def fingerprint(p):
    s=p.stat();return f'{s.st_mtime_ns}:{s.st_size}'

def cached(a,path,fp):
    with a.connect() as db:return {r['page']:dict(r) for r in db.execute('SELECT * FROM ocr_pages WHERE path=? AND fingerprint=?',(path,fp))}

def details(a):
    with a.connect() as db:
        rows=[dict(r) for r in db.execute("SELECT o.*,d.id,d.title FROM ocr_pages o JOIN docs d ON d.path=o.path WHERE substr(d.stamp,1,length(o.fingerprint)+1)=o.fingerprint||':' ORDER BY o.checked DESC LIMIT 500")]
        count=db.execute("SELECT count(*) FROM pages p JOIN docs d ON d.id=p.doc_id WHERE trim(p.body)='' AND d.page_count>0").fetchone()[0]
        pending=db.execute("""SELECT count(*) FROM pages p JOIN docs d ON d.id=p.doc_id
            WHERE trim(p.body)='' AND d.page_count>0 AND NOT EXISTS
            (SELECT 1 FROM ocr_pages o WHERE o.path=d.path AND o.page=CAST(p.page AS INTEGER)
            AND substr(d.stamp,1,length(o.fingerprint)+1)=o.fingerprint||':' AND o.status IN ('done','blank'))""").fetchone()[0]
    return dict(engine_available=bool(engine()),empty_pages=count,pending_pages=pending,results=rows)

def refresh_warning(a,ident):
    with a.connect() as db:
        row=db.execute('SELECT warning FROM docs WHERE id=?',(ident,)).fetchone()
        if not row:return
        warning=re.sub(r'\s*\d+ page\(s\) have no extractable text; scanned pages need OCR\.','',row['warning'])
        warning=re.sub(r'\s*\d+ page\(s\) have no searchable text; these may be blank, images or scans\.','',warning)
        n=db.execute("SELECT count(*) FROM pages WHERE doc_id=? AND trim(body)=''",(ident,)).fetchone()[0]
        if n:warning+=f' {n} page(s) have no searchable text; these may be blank, images or scans.'
        db.execute('UPDATE docs SET warning=? WHERE id=?',(warning.strip(),ident))

def run(a,log,progress=None,should_stop=None):
    progress=progress or (lambda info:None)
    should_stop=should_stop or (lambda:False)
    exe=engine()
    if not exe:raise RuntimeError('Install Tesseract with English language data first; see the OCR section in START-HERE.md. Then restart the app.')
    import pypdfium2
    from PIL import Image
    r=subprocess.run([exe,'--list-langs'],capture_output=True,timeout=15)
    if r.returncode or 'eng' not in r.stdout.decode(errors='replace').split():raise RuntimeError('Tesseract English language data (eng) is missing.')
    with a.connect() as db:
        candidates=[dict(r) for r in db.execute("SELECT d.id,d.path,d.title,d.stamp,p.page FROM pages p JOIN docs d ON d.id=p.doc_id WHERE trim(p.body)='' AND d.page_count>0 ORDER BY d.path,CAST(p.page AS INTEGER)")]
    done=blank=failed=skipped=0
    last_completed=None
    stopped=False
    def report(current='',page=None):
        progress(dict(total=len(candidates),completed=done+blank+failed+skipped,done=done,blank=blank,failed=failed,skipped=skipped,current=current,page=page,last_completed=last_completed,stopped=stopped))
    report()
    for i,r in enumerate(candidates,1):
        if should_stop():
            stopped=True
            break
        report(r['title'],int(r['page']))
        path=(a.root/r['path']).resolve();page=int(r['page'])
        if not path.is_relative_to(a.root) or not path.is_file():skipped+=1;continue
        fp=fingerprint(path)
        if not r['stamp'].startswith(fp+':'):
            log('File changed; index it before OCR: '+r['title']);skipped+=1;continue
        previous=cached(a,r['path'],fp).get(page)
        if previous and previous['status'] in ('done','blank'):skipped+=1;continue
        log(f'OCR {i}/{len(candidates)}: {r["title"]}, PDF page {page}')
        with tempfile.TemporaryDirectory(prefix='council-ocr-result-') as tmp:
            out=Path(tmp)/'result.json'
            try:
                proc=subprocess.run([sys.executable,str(Path(__file__).with_name('ocr_worker.py')),str(path),str(page),str(out)],capture_output=True,timeout=150)
                if proc.returncode or not out.exists():raise RuntimeError('OCR worker failed: '+proc.stderr.decode(errors='replace')[-700:])
                result=json.loads(out.read_text());text=result['text'];error=result['error']
            except Exception as e:text='';error=str(e)
        if fingerprint(path)!=fp:log('File changed during OCR; result discarded. Index again.');skipped+=1;continue
        status='error' if error else ('done' if text.strip() else 'blank')
        with a.connect() as db:
            db.execute('INSERT OR REPLACE INTO ocr_pages VALUES(?,?,?,?,?,?,?)',(r['path'],fp,page,text,status,error,datetime.now(timezone.utc).isoformat()))
            if status=='done':
                db.execute('UPDATE pages SET body=? WHERE doc_id=? AND page=?',(text,r['id'],r['page']))
        refresh_warning(a,r['id'])
        if status=='done':done+=1
        elif status=='blank':blank+=1
        else:failed+=1;log(f'OCR failed on page {page}: {error}')
        last_completed=time.time()
        report()
    report()
    outcome='stopped; completed work saved' if stopped else 'complete'
    log(f'OCR {outcome}: {done} pages added to search, {blank} with no words recognised, {failed} failed, {skipped} skipped. Originals unchanged.')
