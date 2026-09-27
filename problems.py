"""Unresolved source problems, retained across runs and separated by council."""
from datetime import datetime, timezone
from urllib.parse import urlparse, unquote
import json,re

def category(reason):
    if 'HTTP 404' in reason:return 'Not found (HTTP 404)'
    if 'HTTP 410' in reason:return 'Removed (HTTP 410)'
    if 'HTTP 403' in reason:return 'Access refused (HTTP 403)'
    if 'Empty response' in reason:return 'Empty response'
    if 'not a PDF' in reason:return 'Response not recognised as PDF'
    if 'timeout' in reason.lower() or 'timed out' in reason.lower():return 'Timed out'
    return 'Could not check or retrieve'

def initialise(a):
    with a.connect() as db:db.execute('CREATE TABLE IF NOT EXISTS source_problems(url TEXT PRIMARY KEY, payload TEXT NOT NULL)')
    marker=a.work/'problems-log-imported'
    if marker.exists():return
    log=a.work/'activity.log'
    if log.exists():
        # Import the latest update with a failure summary, not the union of all past runs.
        runs=re.split(r'(?m)^.*?  Starting (?:update|download|preview|discover)(?: for .*?)?\s*$',log.read_text(encoding='utf-8',errors='replace'))
        recent=next((part for part in reversed(runs) if 'Needs attention:' in part or 'Download check finished:' in part),'')
        for line in recent.splitlines():
            if 'Needs attention: ' not in line:continue
            timestamp=line.split('  ',1)[0]
            add_message(a,line.split('Needs attention: ',1)[1],timestamp=timestamp,imported=True)
    marker.write_text('Imported previous log once; subsequent records come from source checks.',encoding='utf-8')

def add_message(a,message,context=None,timestamp=None,imported=False):
    if not message.startswith(('https://','http://')) or ': ' not in message:return
    url,reason=message.split(': ',1)
    from archive import canonical
    url=canonical(url)
    info=dict(context or {})
    now=timestamp or datetime.now(timezone.utc).isoformat()
    with a.connect() as db:
        old=db.execute('SELECT payload FROM source_problems WHERE url=?',(url,)).fetchone()
        previous=json.loads(old['payload']) if old else {}
        if not info:
            row=db.execute('SELECT title,committee,meeting FROM downloads WHERE url=?',(url,)).fetchone()
            if not row:row=db.execute('SELECT title,committee,meeting FROM observations WHERE url=? OR meeting_url=? LIMIT 1',(url,url)).fetchone()
            if row:info=dict(row)
        meeting_page='ielistdocuments' in url.lower() or '/viewmeetingpublic/' in url.lower()
        title=info.get('title') if not meeting_page else ''
        if not title:title='Meeting page' if meeting_page else unquote(urlparse(url).path.rsplit('/',1)[-1])
        record=dict(url=url,title=title or 'Document link',committee=info.get('committee',''),meeting=info.get('meeting',''),
            meeting_url=info.get('meeting_url',''),category=category(reason),reason=reason,
            first_failed=previous.get('first_failed',now),last_failed=now,
            attempts=previous.get('attempts',0)+1,imported=imported,kind='Meeting page' if meeting_page else 'Document or source page')
        db.execute('INSERT OR REPLACE INTO source_problems VALUES(?,?)',(url,json.dumps(record)))

def resolve(a,url):
    from archive import canonical
    with a.connect() as db:db.execute('DELETE FROM source_problems WHERE url=?',(canonical(url),))

def items(a):
    with a.connect() as db:rows=[json.loads(r['payload']) for r in db.execute('SELECT payload FROM source_problems')]
    return sorted(rows,key=lambda r:r['last_failed'],reverse=True)

class IssueList(list):
    def __init__(self,a,existing=()):super().__init__(existing);self.archive=a;self.context={}
    def append(self,message):
        super().append(message)
        add_message(self.archive,message,self.context)
