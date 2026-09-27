"""Readable names and bounded ZIP exports of existing, unchanged archive PDFs."""
import re
from pathlib import Path
from urllib.parse import quote
from zipfile import ZipFile, ZIP_STORED
from tempfile import TemporaryFile

MAX_FILES=500
MAX_BYTES=2*1024*1024*1024

def pdf_name(row):
    from planning import meeting_date
    title=str(row['title'] or Path(row['path']).stem)
    title=re.sub(r'\.pdf$','',title,flags=re.I)
    parts=[meeting_date(row['meeting']),title,row['committee'] or '']
    name=' - '.join(str(p) for p in parts if p)
    name=re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]',' ',name)
    name=re.sub(r'\s+',' ',name).strip(' .')[:160].rstrip(' .') or 'Council paper'
    return f'{name} - {row["id"]}.pdf'

def disposition(name,attachment=False):
    fallback=name.encode('ascii','ignore').decode() or 'Council paper.pdf'
    fallback=re.sub(r'[^\w .()-]','_',fallback)
    return ('attachment' if attachment else 'inline')+f'; filename="{fallback}"; filename*=UTF-8\'\''+quote(name,safe='')

def source(a,row):
    path=(a.root/row['path']).resolve()
    if not path.is_relative_to(a.root) or not path.is_file():
        raise ValueError('PDF unavailable: '+str(row['title']))
    return path

def files(a,ids):
    if not isinstance(ids,list) or not ids or len(ids)>MAX_FILES or any(type(i) is not int or i<1 for i in ids):
        raise ValueError(f'Select between 1 and {MAX_FILES} papers.')
    ids=list(dict.fromkeys(ids))
    with a.connect() as db:
        rows={r['id']:dict(r) for r in db.execute('SELECT * FROM docs WHERE id IN ('+','.join('?' for _ in ids)+')',ids)}
    if len(rows)!=len(ids):raise ValueError('A selected paper is no longer in this archive. Refresh the search results.')
    result=[(source(a,rows[i]),pdf_name(rows[i])) for i in ids]
    if sum(p.stat().st_size for p,n in result)>MAX_BYTES:
        raise ValueError(f'These papers exceed {MAX_BYTES//2**20:,} MB. Select fewer papers and download in smaller batches.')
    return result

def bundle(a,ids):
    chosen=files(a,ids)
    tmp=TemporaryFile()
    try:
        with ZipFile(tmp,'w',ZIP_STORED) as z:
            for path,name in chosen:z.write(path,name)
        size=tmp.tell();tmp.seek(0)
        return tmp,size
    except Exception:
        tmp.close();raise
