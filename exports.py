"""Readable names and bounded ZIP exports of existing, unchanged archive PDFs."""
import json, re
from pathlib import Path
from urllib.parse import quote
from zipfile import ZipFile, ZIP_STORED, ZIP_DEFLATED
from tempfile import TemporaryFile
from datetime import datetime

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

MEETING_README='''Meeting papers
==============

This folder was made by Council Archive. It contains:

  meeting.json    Committee, meeting date, the council's meeting page, and a record for
                  each paper: title, source address, file names, page count, text warnings,
                  and when the paper first appeared on the meeting page.
  papers.md       The same list as a readable table.
  papers/         The PDFs exactly as downloaded from the council.
  text/           The text of each PDF, one file per paper, with === PAGE n === markers.
  all-text.txt    Every paper's text in one file, in the order the meeting page lists them.

Using it
--------
Open papers.md for the list of papers and their timings, then read the PDFs. The text
files are for searching, copying quotations, or tools that work with plain text. Page
markers in the text files match the PDF page numbers, so any reference can be checked
against the original.

What the timings mean
---------------------
Council Archive records its own checks of the meeting page. "Appeared between A and B"
means the paper's link was absent when the page was checked at A and present at B.
"Present at first check" means the link was already there the first time the archive
read the page, so the archive cannot say when it was added. A failed check proves
nothing. These timings are observations, not a finding that any deadline was missed:
compare them with the agenda publication date and your council's rules yourself.

Text extracted from PDFs can contain errors, and pages that are scans or images may have
no text unless OCR was run. Check anything you rely on against the PDF.
'''

def timing(p):
    """Plain description of when a paper's link was first observed."""
    if not p.get('first_seen'):return 'Not observed on the meeting page'
    if p.get('previous_check'):return f"Appeared between {p['previous_check'][:16].replace('T',' ')} and {p['first_seen'][:16].replace('T',' ')} (UTC)"
    return f"Present at first check, {p['first_seen'][:16].replace('T',' ')} (UTC)"

def meeting_bundle(a,meeting_url):
    """Build one meeting's ZIP: PDFs, per-paper text, a combined text file and a manifest."""
    from planning import meeting_date
    papers=a.papers(meeting_urls=[meeting_url])
    if not papers:raise ValueError('No papers are recorded for this meeting. Check the meeting for papers first.')
    row=a.meeting_rows().get(meeting_url) or {}
    with a.connect() as db:
        checked=db.execute('SELECT checked FROM meeting_checks WHERE url=?',(meeting_url,)).fetchone()
    committee=row.get('committee') or papers[0]['committee'] or ''
    label=row.get('label') or papers[0]['meeting'] or ''
    info=dict(council=a.profile.get('name',''),committee=committee,meeting=label,date=row.get('date') or meeting_date(label),
        meeting_page=meeting_url,last_checked=checked['checked'] if checked else '',prepared=datetime.now().astimezone().isoformat(timespec='seconds'),
        timing_note='Timings are Council Archive\'s own observations of the meeting page, not publication dates stated by the council.',papers=[])
    ids=[p['doc_id'] for p in papers if p['doc_id']]
    chosen=dict(zip(dict.fromkeys(ids),files(a,list(dict.fromkeys(ids))))) if ids else {}
    tmp=TemporaryFile()
    try:
        with ZipFile(tmp,'w',ZIP_DEFLATED) as z:
            combined=[];table=[];written=set()
            for n,p in enumerate(papers,1):
                entry=dict(number=n,title=p['title'],source_url=p['url'],first_seen=p['first_seen'],previous_check=p['previous_check'],
                    timing=timing(p),in_archive=bool(p['doc_id']))
                if p['doc_id']:
                    path,pdf=chosen[p['doc_id']]
                    with a.connect() as db:
                        doc=db.execute('SELECT page_count,warning FROM docs WHERE id=?',(p['doc_id'],)).fetchone()
                        pages=db.execute('SELECT page,body FROM pages WHERE doc_id=? ORDER BY CAST(page AS INTEGER)',(p['doc_id'],)).fetchall()
                    txt=pdf[:-4]+'.txt'
                    body='\n'.join(f'=== PAGE {r["page"]} ===\n{r["body"]}' for r in pages)
                    if pdf not in written:
                        written.add(pdf);z.write(path,'papers/'+pdf,compress_type=ZIP_STORED);z.writestr('text/'+txt,body)
                    combined.append(f'##### PAPER {n}: {p["title"]}\n##### File: papers/{pdf}\n##### {entry["timing"]}\n\n{body}\n')
                    entry.update(pdf='papers/'+pdf,text='text/'+txt,pages=doc['page_count'],warning=doc['warning'] or '')
                else:
                    entry.update(pdf='',text='',pages=None,warning='Not in the archive: the paper could not be downloaded from the council.')
                info['papers'].append(entry)
                table.append(f"| {n} | {md(p['title'])} | {entry['pages'] if entry['pages'] is not None else '—'} | {md(entry['timing'])} | {md(entry['warning']) or ''} |")
            head=[f"# {committee or 'Meeting'}: {label}",'',f"Council: {info['council']}  ",f"Meeting page: {meeting_url}  ",
                f"Meeting page last checked: {info['last_checked'] or 'never'}  ",f"Prepared: {info['prepared']}",'',
                '| # | Paper | Pages | When it appeared | Notes |','|---|---|---|---|---|']
            z.writestr('papers.md','\n'.join(head+table+['',info['timing_note']])+'\n')
            z.writestr('all-text.txt','\n'.join(combined) or 'No papers from this meeting are in the archive yet.\n')
            z.writestr('meeting.json',json.dumps(info,indent=2,ensure_ascii=False))
            z.writestr('README.txt',MEETING_README)
        size=tmp.tell();tmp.seek(0)
        return tmp,size,info
    except Exception:
        tmp.close();raise

def md(text):
    return str(text or '').replace('|',r'\|').replace('\n',' ')
