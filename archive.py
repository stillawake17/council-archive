"""Local council archive: incremental page-level search, meeting checks and paper downloads."""
from pathlib import Path
from contextlib import contextmanager
from urllib.parse import urljoin, urlparse, parse_qsl, urlencode, urlunparse
import csv, hashlib, json, re, sqlite3, time
from datetime import datetime, timezone, timedelta, date
from pypdf import PdfReader


def canonical(url):
    p = urlparse(url)
    return urlunparse((p.scheme.lower(), p.netloc.lower(), p.path, '', urlencode(sorted(parse_qsl(p.query))), ''))


def is_pdf(path):
    with path.open('rb') as f: return f.read(5)==b'%PDF-'


def clean_filename(text):
    return re.sub(r'\s+', '_', re.sub(r'[^\w\s.-]', '', str(text)).strip())[:180]


def now():
    return datetime.now(timezone.utc).isoformat()


# A paper found on a meeting page, joined to its saved copy (if any) and search record (if indexed).
PAPERS = '''SELECT o.url, o.meeting_url, o.title, o.committee, o.meeting, o.first_seen, o.previous_check,
    dl.url IS NOT NULL AS downloaded,
    COALESCE((SELECT d.id FROM docs d WHERE d.path=dl.path),(SELECT d.id FROM docs d WHERE d.url=o.url LIMIT 1)) AS doc_id
    FROM observations o LEFT JOIN downloads dl ON dl.url=o.url'''


class Archive:
    def __init__(self, root, profile=None):
        self.root = Path(root).expanduser().resolve()
        from readers import PRESETS
        self.profile = dict(profile or PRESETS["bristol"])
        if not self.root.is_dir():
            raise ValueError('The toolkit folder does not exist.')
        self.work = self.root / 'data' / 'archive_web'
        self.work.mkdir(parents=True, exist_ok=True)
        self.dbpath = self.work / 'search.sqlite3'
        self._news_cache = (None, None)
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS docs(id INTEGER PRIMARY KEY, path TEXT UNIQUE, title TEXT,
                committee TEXT, meeting TEXT, url TEXT, stamp TEXT, page_count INTEGER, warning TEXT);
            CREATE VIRTUAL TABLE IF NOT EXISTS pages USING fts5(doc_id UNINDEXED, page UNINDEXED, title, body);
            CREATE TABLE IF NOT EXISTS meeting_checks(url TEXT PRIMARY KEY, checked TEXT);
            CREATE TABLE IF NOT EXISTS observations(url TEXT, meeting_url TEXT, title TEXT,
                committee TEXT, meeting TEXT, first_seen TEXT, previous_check TEXT,
                PRIMARY KEY(url, meeting_url));
            CREATE TABLE IF NOT EXISTS downloads(url TEXT PRIMARY KEY, path TEXT, title TEXT,
                committee TEXT, meeting TEXT, downloaded TEXT);
            CREATE TABLE IF NOT EXISTS check_runs(id INTEGER PRIMARY KEY, started TEXT, finished TEXT,
                kind TEXT, scope TEXT, auto INTEGER DEFAULT 0, meetings INTEGER DEFAULT 0, added INTEGER DEFAULT 0,
                baseline INTEGER DEFAULT 0, downloaded INTEGER DEFAULT 0, failed INTEGER DEFAULT 0, note TEXT DEFAULT '');
            CREATE INDEX IF NOT EXISTS observations_meeting ON observations(meeting_url);
            CREATE INDEX IF NOT EXISTS observations_seen ON observations(first_seen);
            CREATE INDEX IF NOT EXISTS docs_url ON docs(url);
            ''')

        from problems import initialise
        initialise(self)
        import ocr
        ocr.initialise(self)
        self.repair_names()

    def repair_names(self):
        """Older versions could save long-titled papers without '.pdf', which kept them out of search."""
        with self.connect() as db:
            for r in db.execute("SELECT url,path FROM downloads WHERE lower(path) NOT LIKE '%.pdf'").fetchall():
                old=self.root/r['path'];new=old.with_name(old.name+'.pdf')
                if old.is_file() and not new.exists() and is_pdf(old):old.replace(new)
                if new.is_file():db.execute('UPDATE downloads SET path=? WHERE url=?',(new.relative_to(self.root).as_posix(),r['url']))

    def unindexed(self):
        """Saved papers that are not yet in search."""
        with self.connect() as db:
            paths=[r['path'] for r in db.execute('SELECT path FROM downloads dl WHERE NOT EXISTS(SELECT 1 FROM docs d WHERE d.path=dl.path)')]
        return [p for p in paths if p.lower().endswith('.pdf') and (self.root/p).is_file()]

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.dbpath, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA journal_mode=WAL')
        try:
            with db: yield db
        finally:
            db.close()

    def metadata(self):
        candidates = {}
        md = self.root / 'data' / 'metadata'
        for name in [self.profile['id']+'_document_links.csv', 'download_manifest.csv', 'documents_metadata.csv', 'documents_metadata_normalised.csv']:
            path = md / name
            if not path.exists():
                continue
            with path.open(encoding='utf-8-sig', newline='') as f:
                for r in csv.DictReader(f):
                    title = r.get('document_title') or r.get('title') or ''
                    fn = r.get('filename') or re.split(r'[/\\]', r.get('local_file',''))[-1]
                    if not fn and title:
                        fn = clean_filename(title)
                        if not fn.lower().endswith('.pdf'): fn += '.pdf'
                    if fn:
                        candidates.setdefault(fn, []).append(dict(title=title, committee=r.get('committee',''),
                            meeting=r.get('meeting_date') or r.get('meeting_date_text',''), url=r.get('document_url','')))
        result = {}
        for fn, records in candidates.items():
            urls = {canonical(r['url']) for r in records if r['url']}
            if len(urls) <= 1:
                result[fn] = records[-1]
            else:
                result[fn] = dict(title=fn, committee='', meeting='', url='', ambiguous=True)
        with self.connect() as db:
            for r in db.execute('SELECT * FROM downloads'):
                result[r['path']] = dict(r)
        return result

    def index(self, log, only=None):
        """Add PDFs to search. With `only` (archive-relative paths), index just those files."""
        meta = self.metadata()
        if only is not None:
            files = sorted(self.root/p for p in only if (self.root/p).is_file())
        else:
            files = sorted(p for folder in ['raw_documents','raw_constitutions']
                           for p in (self.root/'data'/folder).rglob('*') if p.is_file() and p.suffix.lower()=='.pdf')
        changed = errors = 0
        seen = set()
        for i,p in enumerate(files, 1):
            if not p.resolve().is_relative_to(self.root): continue
            rel = p.relative_to(self.root).as_posix()
            seen.add(rel)
            m = meta.get(rel, meta.get(p.name, {}))
            st = p.stat()
            stamp = f'{st.st_mtime_ns}:{st.st_size}:' + json.dumps(m, sort_keys=True)
            with self.connect() as db:
                old = db.execute('SELECT * FROM docs WHERE path=?', (rel,)).fetchone()
                if old and old['stamp'] == stamp:
                    if i % 20 == 0: log(f'Checked {i:,} of {len(files):,} PDFs; unchanged files skipped.')
                    continue
            warning = 'Metadata ambiguous: several source URLs share this old filename.' if m.get('ambiguous') else ''
            title = m.get('title') or p.stem.replace('_',' ')
            import ocr
            ocr_cache=ocr.cached(self,rel,f'{st.st_mtime_ns}:{st.st_size}')
            texts = []
            log(f'Reading PDF {i:,} of {len(files):,}: {p.name}')
            try:
                reader = PdfReader(str(p))
                for num, page in enumerate(reader.pages,1):
                    if num == 1 or num % 10 == 0:
                        log(f'{p.name}: reading page {num:,} of {len(reader.pages):,}')
                    texts.append((num, (page.extract_text() or '').encode('utf-8', errors='replace').decode('utf-8')))
                texts=[(n,t if t.strip() else ocr_cache.get(n,{}).get('body','')) for n,t in texts]
                empty = sum(not t.strip() for _,t in texts)
                if empty:
                    warning += f' {empty} page(s) have no searchable text; these may be blank, images or scans.'
            except Exception as e:
                errors += 1
                warning += f' Could not read PDF: {e}'
            with self.connect() as db:
                if old:
                    ident = old['id']
                    db.execute('DELETE FROM pages WHERE doc_id=?',(ident,))
                    db.execute('DELETE FROM docs WHERE id=?',(ident,))
                else: ident = None
                cur = db.execute('INSERT INTO docs VALUES(?,?,?,?,?,?,?,?,?)',
                    (ident,rel,title,m.get('committee',''),m.get('meeting',''),m.get('url',''),stamp,len(texts),warning.strip()))
                ident = cur.lastrowid
                db.executemany('INSERT INTO pages VALUES(?,?,?,?)',
                    [(ident,n,title,t) for n,t in texts] or [(ident,1,title,'')])
            changed += 1
            if i % 20 == 0: log(f'Indexed {i:,} of {len(files):,} PDFs…')
        if only is None:
            with self.connect() as db:
                for row in db.execute('SELECT id,path FROM docs').fetchall():
                    if row['path'] not in seen:
                        db.execute('DELETE FROM pages WHERE doc_id=?',(row['id'],))
                        db.execute('DELETE FROM docs WHERE id=?',(row['id'],))
        log(f'Search updated: {len(seen):,} PDFs checked, {changed:,} added or refreshed, {errors} unreadable.')

    def stats(self):
        with self.connect() as db:
            return dict(documents=db.execute('SELECT count(*) FROM docs').fetchone()[0],
                        warnings=db.execute("SELECT count(*) FROM docs WHERE warning<>''").fetchone()[0],
                        committees=[r[0] for r in db.execute("SELECT DISTINCT committee FROM docs WHERE committee<>'' ORDER BY committee")])

    def search(self, query='', committees=(), offset=0, issues=False, date_from='', date_to='', sort='relevance'):
        from planning import meeting_date
        for value in (date_from,date_to):
            if value:date.fromisoformat(value)
        if date_from and date_to and date_from>date_to:raise ValueError('The end date must follow the start date.')
        if isinstance(committees,str):committees=[committees] if committees else []
        committees=[c for c in committees if c]
        args=[]; where=[]
        if date_from or date_to:where.append("meeting_date(d.meeting)<>''")
        if date_from:where.append('meeting_date(d.meeting)>=?');args.append(date_from)
        if date_to:where.append('meeting_date(d.meeting)<=?');args.append(date_to)
        if committees: where.append('d.committee IN ('+','.join('?'*len(committees))+')'); args.extend(committees)
        if issues: where.append("d.warning<>''")
        if query.strip():
            # Quoted phrases and plain words; no raw SQL or FTS expressions.
            tokens=re.findall(r'"([^"]+)"|(\S+)', query[:1000])
            match=' AND '.join('"'+(a or b).replace('"','""')+'"' for a,b in tokens)
            where.insert(0,'pages MATCH ?'); args.insert(0,match)
            source='pages JOIN docs d ON d.id=pages.doc_id'
            fields="d.*, pages.page, snippet(pages,3,'','', ' … ',40) AS extract"
            order='bm25(pages)'
        else:
            source='docs d'; fields="d.*, 1 AS page, '' AS extract"; order='d.title COLLATE NOCASE'
        if sort=='newest':order="meeting_date(d.meeting) DESC, "+order
        elif sort=='oldest':order="meeting_date(d.meeting)='', meeting_date(d.meeting) ASC, "+order
        clause=(' WHERE '+' AND '.join(where)) if where else ''
        with self.connect() as db:
            db.create_function('meeting_date',1,meeting_date,deterministic=True)
            total=db.execute('SELECT count(*) FROM '+source+clause,args).fetchone()[0]
            rows=db.execute(f'SELECT {fields} FROM {source}{clause} ORDER BY {order} LIMIT 30 OFFSET ?',args+[offset]).fetchall()
        results=[dict(r) for r in rows]
        import ocr
        for r in results:
            fp=(r['stamp'] or '').split(':',2);fp=':'.join(fp[:2])
            record=ocr.cached(self,r['path'],fp).get(int(r['page']))
            r['ocr']=bool(record and record['status']=='done')
        return dict(total=total, results=results)

    # ---- Meetings, committees and papers known to the archive ----

    def catalog(self):
        path=self.work/'meeting_catalog.json'
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else None

    def write_json(self,name,data):
        path=self.work/name
        tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8');tmp.replace(path)

    def meeting_rows(self):
        """Meetings from the latest meeting list plus any meeting page checked before."""
        from planning import meeting_date
        rows={r['url']:dict(r) for r in (self.catalog() or {}).get('meetings',[])}
        with self.connect() as db:
            for r in db.execute('SELECT meeting_url,committee,meeting FROM observations GROUP BY meeting_url'):
                rows.setdefault(r['meeting_url'],dict(url=r['meeting_url'],committee=r['committee'],label=r['meeting'],date=meeting_date(r['meeting'])))
        return rows

    def meeting_stats(self):
        with self.connect() as db:
            checks={r['url']:r['checked'] for r in db.execute('SELECT url,checked FROM meeting_checks')}
            counts={r['meeting_url']:dict(r) for r in db.execute('''SELECT o.meeting_url, count(*) AS papers,
                sum(dl.url IS NOT NULL OR EXISTS(SELECT 1 FROM docs d WHERE d.url=o.url)) AS saved,
                max(o.first_seen) AS latest_seen
                FROM observations o LEFT JOIN downloads dl ON dl.url=o.url GROUP BY o.meeting_url''')}
        return checks,counts

    def committees(self):
        today=date.today().isoformat()
        checks,counts=self.meeting_stats()
        result={}
        for r in self.meeting_rows().values():
            name=r['committee'] or ''
            c=result.setdefault(name,dict(name=name,meetings=0,upcoming=0,latest='',papers=0,saved=0,last_checked=''))
            c['meetings']+=1
            if r['date'] and r['date']>=today:c['upcoming']+=1
            if r['date'] and r['date']<=today and r['date']>c['latest']:c['latest']=r['date']
            n=counts.get(r['url'],{})
            c['papers']+=n.get('papers',0);c['saved']+=n.get('saved',0) or 0
            c['last_checked']=max(c['last_checked'],checks.get(r['url'],''))
        return sorted(result.values(),key=lambda c:(not c['name'],c['name'].lower()))

    def meetings(self, committees=(), date_from='', date_to=''):
        checks,counts=self.meeting_stats()
        rows,unknown=self.select_meetings(committees,date_from,date_to)
        for r in rows:
            n=counts.get(r['url'],{})
            r.update(papers=n.get('papers',0),saved=n.get('saved',0) or 0,latest_seen=n.get('latest_seen',''),last_checked=checks.get(r['url'],''))
        return dict(meetings=rows,unknown_dates=unknown)

    def select_meetings(self, committees=(), date_from='', date_to='', urls=()):
        """Meetings matching committee and date choices, newest first. Undated meetings are excluded by date filters."""
        rows=self.meeting_rows()
        if urls:
            return [dict(rows.get(u) or dict(url=u,committee='',label='',date='')) for u in dict.fromkeys(urls)],0
        committees=set(c for c in committees if c is not None)
        chosen=[];unknown=0
        for r in rows.values():
            if committees and (r['committee'] or '') not in committees:continue
            if date_from or date_to:
                if not r['date']:unknown+=1;continue
                if date_from and r['date']<date_from:continue
                if date_to and r['date']>date_to:continue
            chosen.append(dict(r))
        chosen.sort(key=lambda r:(r['date'] or '',r['committee'] or ''),reverse=True)
        return chosen,unknown

    def papers(self, meeting_urls=(), urls=()):
        where=[];args=[]
        if meeting_urls:where.append('o.meeting_url IN ('+','.join('?'*len(meeting_urls))+')');args+=list(meeting_urls)
        if urls:where.append('o.url IN ('+','.join('?'*len(urls))+')');args+=list(urls)
        with self.connect() as db:
            rows=[dict(r) for r in db.execute(PAPERS+(' WHERE '+' AND '.join(where) if where else '')+' ORDER BY o.rowid',args)]
        return rows

    def lookup(self, urls):
        with self.connect() as db:
            return {u:(db.execute('SELECT d.id FROM downloads dl JOIN docs d ON d.path=dl.path WHERE dl.url=?',(u,)).fetchone()
                       or db.execute('SELECT id FROM docs WHERE url=?',(u,)).fetchone() or [None])[0] for u in urls}

    def runs(self, limit=20):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM check_runs ORDER BY id DESC LIMIT ?',(limit,))]

    def latest_check(self):
        with self.connect() as db:
            r=db.execute("SELECT * FROM check_runs WHERE kind IN ('check','fetch') AND meetings>0 ORDER BY id DESC LIMIT 1").fetchone()
        return dict(r) if r else None

    def news(self, window='latest', committees=(), unsaved=False, baseline=False):
        """Papers first seen recently. Links present at the first check of an older meeting are baseline, not news."""
        from planning import meeting_date
        run=self.latest_check()
        if window=='latest':
            if not run:return dict(papers=[],hidden=0,since='',until='',run=None)
            since,until=run['started'],run['finished'] or now()
        else:
            days={'7d':7,'30d':30,'90d':90}.get(window)
            if not days:raise ValueError('Choose a time window.')
            since,until=(datetime.now(timezone.utc)-timedelta(days=days)).isoformat(),now()
        where=['o.first_seen>=?','o.first_seen<=?'];args=[since,until]
        committees=[c for c in committees if c]
        if committees:where.append('o.committee IN ('+','.join('?'*len(committees))+')');args+=committees
        with self.connect() as db:
            rows=[dict(r) for r in db.execute(PAPERS+' WHERE '+' AND '.join(where)+' ORDER BY o.first_seen DESC LIMIT 20000',args)]
        papers=[];hidden=0
        for r in rows:
            r['saved']=bool(r['downloaded'] or r['doc_id'])
            if unsaved and r['saved']:continue
            r['is_new']=is_news(r,meeting_date)
            if not r['is_new'] and not baseline:hidden+=1;continue
            papers.append(r)
        return dict(papers=papers[:2000],total=len(papers),hidden=hidden,since=since,until=until,run=run)

    def news_count(self):
        """New papers from the latest check that are not yet in the archive (cached per check)."""
        run=self.latest_check()
        key=run and (run['id'],run['finished'])
        if key and self._news_cache[0]==key:return self._news_cache[1]
        count=len(self.news('latest',unsaved=True)['papers']) if run else 0
        if key and run['finished']:self._news_cache=(key,count)
        return count

    def observations(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM observations ORDER BY first_seen DESC LIMIT 500')]

    def record_observation(self, meeting_url, committee, meeting, found, html, checked):
        """Archive the page, then record links. Returns (links first seen now, whether this was the first check)."""
        folder=self.work/'page_snapshots'/hashlib.sha256(meeting_url.encode()).hexdigest()[:20]
        folder.mkdir(parents=True,exist_ok=True)
        snapshot=folder/(checked.replace(':','-')+'.html')
        snapshot.write_text(html,encoding='utf-8')
        added=0
        with self.connect() as db:
            old=db.execute('SELECT checked FROM meeting_checks WHERE url=?',(meeting_url,)).fetchone()
            for url,title in found:
                cur=db.execute('INSERT OR IGNORE INTO observations VALUES(?,?,?,?,?,?,?)',
                    (url,meeting_url,title,committee,meeting,checked,old['checked'] if old else ''))
                added+=cur.rowcount
            db.execute('INSERT OR REPLACE INTO meeting_checks VALUES(?,?)',(meeting_url,checked))
        with (self.work/'page_checks.jsonl').open('a',encoding='utf-8') as f:
            f.write(json.dumps(dict(meeting_url=meeting_url,checked=checked,
                snapshot=str(snapshot.relative_to(self.root)),sha256=hashlib.sha256(html.encode()).hexdigest(),
                document_links=found))+'\n')
        return added,not old

    # ---- Website work: one browser session per job ----

    @contextmanager
    def browser(self, timeout=60000):
        from playwright.sync_api import sync_playwright
        from readers import Reader, parse_links
        from problems import resolve
        reader=Reader(self.profile['system'])
        home=self.profile['meetings_url'];host=urlparse(home).hostname
        def allowed(url):
            p=urlparse(url)
            return p.scheme in ('https','http') and p.hostname==host
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True)
            try:
                page=browser.new_page()
                def links(url):
                    if not allowed(url): raise ValueError('Council link points outside configured committee site.')
                    response=page.goto(url,wait_until='domcontentloaded',timeout=timeout)
                    if response and response.status>=400: raise RuntimeError(f'HTTP {response.status}')
                    html=page.content(); time.sleep(.25)
                    if not reader.meeting(page.url):resolve(self,url)
                    return [(canonical(u),t) for u,t in parse_links(html,page.url) if allowed(u)]
                yield page,links,allowed
            finally:
                browser.close()

    def site_check(self, log):
        from readers import Reader
        with self.browser(timeout=15000) as (page,links,allowed):
            return Reader(self.profile['system']).check(self.profile['meetings_url'],links,log)

    def refresh_meetings(self, log, links, failures, committees=(), full=False):
        """Update the meeting list. Quick mode reads each committee's current listing page only."""
        from readers import Reader
        from planning import meeting_date
        reader=Reader(self.profile['system'])
        catalog=self.catalog() or dict(meetings=[],issues=[])
        known={r['committee'] for r in catalog['meetings']}
        chosen=set(committees)
        skip=(lambda name:name in known and name not in chosen) if chosen else None
        log('Refreshing the meeting list'+(' (all years; this can take a while)' if full else ' from current committee pages')+'…')
        try:
            found=reader.discover(self.profile['meetings_url'],links,log,failures,skip=skip,pagination=full)
        except RuntimeError as e:
            failures.append(str(e));found={}
        if full:
            with self.connect() as db:
                for row in db.execute('SELECT meeting_url,committee,meeting FROM observations'):
                    found.setdefault(row['meeting_url'],(row['committee'],row['meeting']))
            old=self.root/'data'/'metadata'/(self.profile['id']+'_meetings.csv')
            if old.exists():
                with old.open(encoding='utf-8-sig',newline='') as f:
                    for r in csv.DictReader(f):
                        u=canonical(r.get('meeting_documents_url',''))
                        if u:found.setdefault(u,(r.get('committee',''),r.get('meeting_date_text','')))
        rows={r['url']:r for r in catalog['meetings']}
        added=0
        for u,(c,d) in found.items():
            if u not in rows:added+=1
            if u not in rows or c:rows[u]=dict(url=u,committee=c or rows.get(u,{}).get('committee',''),label=d,date=meeting_date(d))
        catalog=dict(created=now(),meetings=list(rows.values()),issues=list(failures) if full else catalog.get('issues',[]),
            coverage='Only discovered meeting pages are included. Unlinked years, separate decision registers and inaccessible pages may be missing.')
        self.write_json('meeting_catalog.json',catalog)
        log(f'Meeting list updated: {len(rows):,} meetings known, {added} newly listed.')
        return added

    def rescan(self, log, progress=None, should_stop=None):
        from problems import IssueList
        failures=IssueList(self)
        with self.browser() as (page,links,allowed):
            self.refresh_meetings(log,links,failures,full=True)
        for issue in failures:log('Coverage issue: '+issue)

    def collect(self, log, progress=None, should_stop=None, committees=(), date_from='', date_to='',
                meetings=(), urls=(), download=True, refresh=True, recheck=False, auto=False, scope=''):
        """Check meeting pages for papers and optionally download any not yet in the archive.

        urls: download these known papers without reading meeting pages.
        meetings: read these meeting pages. Otherwise choose meetings by committee and date."""
        from readers import Reader
        from problems import IssueList, resolve
        progress=progress or (lambda info:None);should_stop=should_stop or (lambda:False)
        reader=Reader(self.profile['system'])
        failures=IssueList(self)
        kind='fetch' if urls else 'check'
        summary=dict(meetings=0,added=0,baseline=0,downloaded=0,failed=0,note='')
        with self.connect() as db:
            run=db.execute('INSERT INTO check_runs(started,kind,scope,auto) VALUES(?,?,?,?)',(now(),kind,scope,int(auto))).lastrowid
        stopped=False
        try:
            with self.browser() as (page,links,allowed):
                docs={}
                if urls:
                    for p in self.papers(urls=[u for u in urls if allowed(u)]):
                        docs.setdefault(p['url'],dict(title=p['title'],committee=p['committee'],meeting=p['meeting'],meeting_url=p['meeting_url']))
                    missing=len(set(urls)-set(docs))
                    if missing:failures.append(f'{missing} selected link(s) were not recognised. Check their meetings first.')
                else:
                    if refresh and not meetings:self.refresh_meetings(log,links,failures,committees)
                    chosen,unknown=self.select_meetings(committees,date_from,date_to,meetings)
                    chosen=[m for m in chosen if allowed(m['url']) and reader.meeting(m['url'])]
                    if unknown:log(f'{unknown} meeting(s) have unreadable dates and were left out of the date range.')
                    if not chosen:raise ValueError('No meetings match these choices. Widen the dates or choose other committees.')
                    log(f'Checking {len(chosen)} meeting page(s) for papers…')
                    for i,m in enumerate(chosen,1):
                        if should_stop():stopped=True;break
                        progress(dict(phase='Checking meeting pages',total=len(chosen),completed=i-1,current=f"{m['committee']} · {m['label']}"))
                        failures.context=dict(committee=m['committee'],meeting=m['label'],meeting_url=m['url'])
                        try:
                            found=[(u,t) for u,t in links(m['url']) if reader.document(u)]
                            html=page.content()
                            if not reader.recognised(page.url,html):
                                raise RuntimeError('Meeting page was not recognised; no publication observation recorded.')
                            resolve(self,m['url'])
                            added,first=self.record_observation(m['url'],m['committee'],m['label'],found,html,now())
                            summary['meetings']+=1
                            if first:summary['baseline']+=added
                            else:
                                summary['added']+=added
                                if added:log(f"{added} new paper(s) since the previous check: {m['committee']} · {m['label']}")
                            for u,t in found:
                                docs.setdefault(u,dict(title=t or 'Council paper',committee=m['committee'],meeting=m['label'],meeting_url=m['url']))
                        except Exception as e:failures.append(f"{m['url']}: {e}")
                    progress(dict(phase='Checking meeting pages',total=len(chosen),completed=summary['meetings']))
                if download and docs and not stopped:
                    saved=self.lookup_saved(docs)
                    todo={u:m for u,m in docs.items() if recheck or u not in saved}
                    if todo:
                        log(f'Downloading {len(todo)} paper(s) not yet in your archive…')
                        counts,paths,stopped=self.download(page,todo,recheck,log,failures,progress,should_stop)
                        summary['downloaded']=counts['new']+counts['changed'];summary['failed']=counts['failed']
                        if paths:
                            progress({});self.index(log,only=paths)
                    else:log('Every paper found is already in your archive.')
                pending=[] if stopped else self.unindexed()
                if pending:
                    log(f'Adding {len(pending)} saved paper(s) that were missing from search…')
                    progress({});self.index(log,only=pending)
        except Exception as e:
            summary['note']=str(e);raise
        finally:
            if stopped:summary['note']='Stopped early; completed work saved.'
            with self.connect() as db:
                db.execute('UPDATE check_runs SET finished=?,meetings=?,added=?,baseline=?,downloaded=?,failed=?,note=? WHERE id=?',
                    (now(),summary['meetings'],summary['added'],summary['baseline'],summary['downloaded'],len(failures),summary['note'],run))
        for failure in failures:log('Needs attention: '+failure)
        parts=[]
        if summary['meetings']:parts.append(f"checked {summary['meetings']} meeting page(s)")
        if kind=='check':parts.append(f"{summary['added']} new paper(s) since previous checks"+(f", {summary['baseline']} seen for the first time on newly checked meetings" if summary['baseline'] else ''))
        parts.append(f"{summary['downloaded']} downloaded")
        if failures:parts.append(f'{len(failures)} problem(s) – see Tools › Unavailable papers')
        log(('Stopped: ' if stopped else 'Finished: ')+'; '.join(parts)+'.')
        return summary

    def lookup_saved(self, docs):
        saved=set()
        with self.connect() as db:
            for u in docs:
                row=db.execute('SELECT path FROM downloads WHERE url=?',(u,)).fetchone()
                if row and (self.root/row['path']).is_file():saved.add(u)
        return saved

    def download(self, page, discovered, recheck, log, failures, progress, should_stop):
        from problems import resolve
        counts=dict(new=0,existing=0,changed=0,failed=0)
        paths=[];stopped=False
        out=self.root/'data'/'raw_documents'/'web_downloads'; out.mkdir(parents=True,exist_ok=True)
        # Only trust old filename associations when a title maps to one distinct URL.
        legacy={}
        old=self.root/'data'/'metadata'/(self.profile['id']+'_document_links.csv')
        if old.exists():
            with old.open(encoding='utf-8-sig',newline='') as f:
                for r in csv.DictReader(f):
                    fn=clean_filename(r.get('document_title',''))
                    if not fn.lower().endswith('.pdf'): fn+='.pdf'
                    legacy.setdefault(fn,set()).add(canonical(r.get('document_url','')))
        for u,m in discovered.items():
            fn=clean_filename(m['title'])
            if not fn.lower().endswith('.pdf'): fn+='.pdf'
            legacy.setdefault(fn,set()).add(u)
        for i,(url,m) in enumerate(discovered.items(),1):
            if should_stop():stopped=True;break
            progress(dict(phase='Downloading papers',total=len(discovered),completed=i-1,current=m['title']))
            failures.context=m
            try:
                with self.connect() as db: known=db.execute('SELECT path FROM downloads WHERE url=?',(url,)).fetchone()
                if known and (self.root/known['path']).is_file() and not recheck: counts['existing']+=1; continue
                fn=clean_filename(m['title'])
                if not fn.lower().endswith('.pdf'): fn+='.pdf'
                oldfile=self.root/'data'/'raw_documents'/fn
                if not recheck and legacy.get(fn)=={url} and oldfile.exists() and is_pdf(oldfile):
                    target=oldfile; counts['existing']+=1
                else:
                    # Keep the full path within Windows' 260-character limit.
                    room=max(20,min(100,240-len(str(out))-26))
                    target=out/(hashlib.sha256(url.encode()).hexdigest()[:20]+'_'+fn[:-4][:room]+'.pdf')
                    response=page.request.get(url,timeout=60000)
                    if not response.ok: raise RuntimeError(f'HTTP {response.status}')
                    body=response.body()
                    if not body: raise RuntimeError('Empty response from council document link')
                    if not body.startswith(b'%PDF-'): raise RuntimeError('Response was not a PDF')
                    if known and (self.root/known['path']).is_file():
                        target=self.root/known['path']
                    oldhash=hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else ''
                    newhash=hashlib.sha256(body).hexdigest()
                    if oldhash==newhash:
                        counts['existing']+=1
                    else:
                        if oldhash:
                            versions=self.work/'versions'; versions.mkdir(exist_ok=True)
                            saved=versions/(oldhash+'.pdf')
                            if not saved.exists(): saved.write_bytes(target.read_bytes())
                            with (self.work/'replacements.jsonl').open('a',encoding='utf-8') as f:
                                f.write(json.dumps(dict(url=url,detected=now(),
                                    old_sha256=oldhash,new_sha256=newhash,old_copy=str(saved.relative_to(self.root))))+'\n')
                        temp=target.with_suffix('.part'); temp.write_bytes(body); temp.replace(target)
                        if oldhash:
                            counts['changed']+=1
                            log('Replaced PDF detected; old copy preserved: '+m['title'])
                        else: counts['new']+=1
                    time.sleep(.2)
                resolve(self,url)
                rel=target.relative_to(self.root).as_posix();paths.append(rel)
                with self.connect() as db:
                    db.execute('INSERT OR REPLACE INTO downloads VALUES(?,?,?,?,?,?)',
                        (url,rel,m['title'],m['committee'],m['meeting'],datetime.now().isoformat()))
                if i%10==0: log(f'Downloads: {counts["new"]} new, {counts["existing"]} already saved.')
            except Exception as e:
                counts['failed']+=1; failures.append(f'{url}: {e}')
        progress(dict(phase='Downloading papers',total=len(discovered),completed=len(discovered)))
        log(f'Downloads: {counts["new"]} new, {counts["existing"]} already saved, {counts["changed"]} replaced, {counts["failed"]} failed.')
        return counts,paths,stopped


def is_news(paper, meeting_date):
    """Added since an earlier check, or first seen on a meeting that was recent or upcoming at the time."""
    if paper['previous_check']:return True
    held=meeting_date(paper['meeting'])
    if not held:return False
    seen=paper['first_seen'][:10]
    return held>=(date.fromisoformat(seen)-timedelta(days=30)).isoformat()
