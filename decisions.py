"""Officer decision notices, read from a ModernGov council's officer decisions register.

The register lists notices by date (mgListOfficerDecisions.aspx). Each notice is a web page
(ieDecisionDetails.aspx?ID=n) giving the decision maker, the decision, its date and its publication date.
Few notices have a PDF attached, so the notice's own text is saved and made searchable here.
Attached PDFs are saved into the archive like any other paper, under the committee name 'Officer decisions'.

Times work as they do for papers. "Appeared between A and B" means the notice was absent from the register
at check A and present at check B. A check only counts as A if its date range covered the notice's
publication date, so the notice would have been listed had it been there."""
import hashlib, html as entities, json, re
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse, parse_qsl, quote

WINDOW_DAYS = 90     # normal checks read notices published in the last 90 days
AHEAD_DAYS = 30      # and up to 30 days ahead, in case a notice carries a future date
REREAD_DAYS = 14     # notices published this recently are read again at each check, to catch edits and status changes
SLOW_DAYS = 7        # the tab can show notices published this many days or more after the decision
EARLIEST = date(2000, 1, 1)
COMMITTEE = 'Officer decisions'
NOT_MODERNGOV = 'Officer decisions can only be read from ModernGov websites.'
NO_REGISTER = ("This council's website did not show an officer decisions register at {url}. "
               'Not every ModernGov council publishes one.')
REFUSAL_LIMIT = 3

LABELS = {'decision maker': 'maker', 'decision status': 'status', 'is key decision?': 'key_decision',
          'is subject to call in?': 'call_in', 'publication date': 'published', 'date of decision': 'decided'}
SECTIONS = {'purpose': 'purpose', 'decision': 'decision', 'alternative options considered': 'alternatives'}
FIELDS = ('title', 'maker', 'status', 'key_decision', 'call_in', 'decided', 'published', 'purpose', 'decision', 'alternatives')


def initialise(a):
    with a.connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS decisions(url TEXT PRIMARY KEY, number INTEGER, title TEXT, listed_date TEXT,
            maker TEXT DEFAULT '', status TEXT DEFAULT '', key_decision TEXT DEFAULT '', call_in TEXT DEFAULT '',
            decided TEXT DEFAULT '', published TEXT DEFAULT '', purpose TEXT DEFAULT '', decision TEXT DEFAULT '',
            alternatives TEXT DEFAULT '', other TEXT DEFAULT '{}', documents TEXT DEFAULT '[]',
            first_seen TEXT, previous_check TEXT DEFAULT '', read TEXT DEFAULT '', fingerprint TEXT DEFAULT '',
            changed TEXT DEFAULT '', changes TEXT DEFAULT '', missing_since TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS decision_lists(checked TEXT, date_from TEXT, date_to TEXT, listed INTEGER);
        CREATE VIRTUAL TABLE IF NOT EXISTS decision_text USING fts5(url UNINDEXED, title, body);
        CREATE INDEX IF NOT EXISTS decisions_seen ON decisions(first_seen);
        ''')
        if 'loaded' not in [r[1] for r in db.execute('PRAGMA table_info(decisions)')]:
            # When a notice came from a page saved by hand rather than from a check of the website.
            db.execute("ALTER TABLE decisions ADD COLUMN loaded TEXT DEFAULT ''")
    saved_folder(a).mkdir(parents=True, exist_ok=True)


# ---- Reading the council's pages ----

def list_url(home, start, end):
    """The register for notices published between two dates. ModernGov shows any range on one page."""
    span = quote(f'{start:%d/%m/%Y}-{end:%d/%m/%Y}', safe='-').lower()
    return urljoin(home, f'mgListOfficerDecisions.aspx?FULL=1&BAM=0&K=0&DM=0&Next=true&DR={span}')


def is_decision(url):
    p = urlparse(url)
    return p.path.lower().endswith('/iedecisiondetails.aspx') and any(k.lower() == 'id' for k, _ in parse_qsl(p.query))


def number(url):
    q = {k.lower(): v for k, v in parse_qsl(urlparse(url).query)}
    return int(q['id']) if q.get('id', '').isdigit() else None


def text(fragment):
    """Readable text from an HTML fragment: line breaks kept, tags and extra spaces dropped."""
    fragment = re.sub(r'(?is)<(script|style)\b.*?</\1>', '', fragment)
    fragment = re.sub(r'\s+', ' ', fragment)          # line breaks in the page source are not line breaks on screen
    fragment = re.sub(r'(?i)<br\s*/?>|</p>|</li>|</div>', '\n', fragment)
    fragment = entities.unescape(re.sub(r'<[^>]+>', '', fragment)).replace('\xa0', ' ')
    lines = [' '.join(line.split()) for line in fragment.splitlines()]
    return '\n'.join(line for line in lines if line).strip()


def uk_date(value):
    """'19/11/2026' -> '2026-11-19'; '' if it is not a date."""
    m = re.search(r'\b(\d{1,2})/(\d{1,2})/(\d{4})\b', value or '')
    if not m: return ''
    try: return date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
    except ValueError: return ''


def register(html):
    """True if the page is an officer decisions register (even an empty one)."""
    lower = html.lower()
    return 'officer decisions' in lower and ('mgtabtable' in lower or 'iedecisiondetails.aspx' in lower or 'no decisions' in lower)


def parse_list(html, base):
    """[(notice url, title, date shown)] in the order listed. The date shown is the date of decision."""
    from archive import canonical
    found = {}
    for row in re.findall(r'(?is)<tr\b.*?</tr>', html):
        link = re.search(r'(?is)<a\b[^>]*href\s*=\s*"([^"]*iedecisiondetails\.aspx[^"]*)"[^>]*>(.*?)</a>', row)
        if not link: continue
        url = canonical(urljoin(base, entities.unescape(link.group(1))))
        if url in found: continue
        rest = row[link.end():]
        found[url] = (url, text(link.group(2)), uk_date(text(rest)))
    return list(found.values())


def parse_notice(html, base):
    """The fields of one decision notice. 'recognised' is False if the page does not look like one."""
    from readers import parse_links, Reader
    from archive import canonical
    body = html
    m = re.search(r'(?is)<div[^>]*class="mgContent"[^>]*>', html)
    if m: body = html[m.start():]
    notice = dict(title='', other={}, documents=[], recognised=False, **{k: '' for k in LABELS.values()}, **{k: '' for k in SECTIONS.values()})
    title = re.search(r'(?is)<h2[^>]*class="mgSubTitleTxt"[^>]*>(.*?)</h2>', html)
    if title: notice['title'] = text(title.group(1))
    for label, value in re.findall(r'(?is)<span[^>]*class="mgLabel"[^>]*>(.*?)</span>(.*?)</p>', body):
        name = ' '.join(text(label).rstrip(': ').split()).lower()
        value = text(value)
        if name in LABELS: notice[LABELS[name]] = value
        elif name and value: notice['other'][text(label).rstrip(': ')] = value
    for heading, value in re.findall(r'(?is)<h3[^>]*class="mgSubSubTitleTxt"[^>]*>(.*?)</h3>\s*<div[^>]*class="mgWordPara"[^>]*>(.*?)</div>', body):
        name = text(heading).rstrip(': ').strip()
        if name.lower() in SECTIONS: notice[SECTIONS[name.lower()]] = text(value)
        elif name: notice['other'][name] = text(value)
    for key in ('published', 'decided'): notice[key] = uk_date(notice[key]) or notice[key]
    reader = Reader('moderngov')
    docs = {}
    for u, t in parse_links(body, base):
        if reader.document(u): docs.setdefault(canonical(u), t or 'Decision document')
    notice['documents'] = [dict(url=u, title=t) for u, t in docs.items()]
    notice['recognised'] = bool(notice['maker'] or notice['decided'] or notice['published']) and 'decision' in html.lower()
    return notice


def fingerprint(notice):
    data = {k: notice.get(k, '') for k in FIELDS}
    data.update(other=notice.get('other', {}), documents=sorted(d['url'] for d in notice.get('documents', [])))
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


# ---- Recording what was seen ----

def tracked(a):
    """True once this archive has read the register at least once."""
    with a.connect() as db: return bool(db.execute('SELECT 1 FROM decision_lists LIMIT 1').fetchone())


def record_list(a, found, checked, date_from, date_to, html=''):
    """Record one complete read of the register. Returns (new notice urls, number newly missing)."""
    if html:
        folder = a.work / 'decision_pages' / 'register'; folder.mkdir(parents=True, exist_ok=True)
        (folder / (checked.replace(':', '-') + '.html')).write_text(html, encoding='utf-8')
    new = []; missing = 0; present = {u for u, _, _ in found}
    with a.connect() as db:
        for url, title, shown in found:
            cur = db.execute("INSERT OR IGNORE INTO decisions(url,number,title,listed_date,first_seen) VALUES(?,?,?,?,?)",
                             (url, number(url), title, shown, checked))
            if cur.rowcount: new.append(url)
            else: db.execute("UPDATE decisions SET missing_since='' WHERE url=? AND missing_since<>''", (url,))
        # A notice is only counted as gone if the range read must have included it, whichever date the register filters on.
        for r in db.execute("SELECT url,listed_date,published FROM decisions WHERE missing_since=''").fetchall():
            if r['url'] in present: continue
            dates = [d for d in (r['listed_date'], r['published']) if d]
            if dates and all(date_from <= d <= date_to for d in dates):
                db.execute('UPDATE decisions SET missing_since=? WHERE url=?', (checked, r['url'])); missing += 1
        db.execute('INSERT INTO decision_lists VALUES(?,?,?,?)', (checked, date_from, date_to, len(found)))
    return new, missing


def previous_check(db, first_seen, published):
    """The latest earlier register read whose range covered this publication date, or ''."""
    if not published: return ''
    r = db.execute('SELECT max(checked) FROM decision_lists WHERE checked<? AND date_from<=? AND date_to>=?',
                   (first_seen, published, published)).fetchone()
    return r[0] or ''


def record_notice(a, url, notice, html, checked):
    """Save a notice that was read. Returns 'new', 'changed' or 'same'."""
    fp = fingerprint(notice)
    with a.connect() as db:
        old = db.execute('SELECT * FROM decisions WHERE url=?', (url,)).fetchone()
        if not old:
            db.execute('INSERT INTO decisions(url,number,title,listed_date,first_seen) VALUES(?,?,?,?,?)',
                       (url, number(url), notice['title'], notice['decided'], checked))
            old = db.execute('SELECT * FROM decisions WHERE url=?', (url,)).fetchone()
        result = 'new' if not old['fingerprint'] else 'changed' if old['fingerprint'] != fp else 'same'
        if result != 'same':
            folder = a.work / 'decision_pages' / str(number(url) or hashlib.sha256(url.encode()).hexdigest()[:20])
            folder.mkdir(parents=True, exist_ok=True)
            snapshot = folder / (checked.replace(':', '-') + '.html'); snapshot.write_text(html, encoding='utf-8')
            changes = old['changes']
            if result == 'changed':
                before = {k: old[k] for k in FIELDS}
                fields = [k for k in FIELDS if (before[k] or '') != (notice.get(k) or '')]
                if json.loads(old['documents'] or '[]') != notice['documents']: fields.append('documents')
                if json.loads(old['other'] or '{}') != notice['other']: fields.append('other details')
                changes = ', '.join(f.replace('_', ' ') for f in fields)
                with (a.work / 'decision_changes.jsonl').open('a', encoding='utf-8') as f:
                    f.write(json.dumps(dict(url=url, detected=checked, fields=fields, before=before,
                                            after={k: notice.get(k, '') for k in FIELDS},
                                            snapshot=str(snapshot.relative_to(a.root))), ensure_ascii=False) + '\n')
            previous = old['previous_check'] if old['read'] else previous_check(db, old['first_seen'], notice['published'] or old['listed_date'])
            db.execute('''UPDATE decisions SET title=?,maker=?,status=?,key_decision=?,call_in=?,decided=?,published=?,purpose=?,
                decision=?,alternatives=?,other=?,documents=?,previous_check=?,read=?,fingerprint=?,changed=?,changes=? WHERE url=?''',
                (notice['title'] or old['title'], notice['maker'], notice['status'], notice['key_decision'], notice['call_in'],
                 notice['decided'], notice['published'], notice['purpose'], notice['decision'], notice['alternatives'],
                 json.dumps(notice['other'], ensure_ascii=False), json.dumps(notice['documents'], ensure_ascii=False),
                 previous, checked, fp, checked if result == 'changed' else old['changed'], changes, url))
            body = '\n'.join([notice['maker'], notice['purpose'], notice['decision'], notice['alternatives']]
                             + [f'{k}: {v}' for k, v in notice['other'].items()])
            db.execute('DELETE FROM decision_text WHERE url=?', (url,))
            db.execute('INSERT INTO decision_text VALUES(?,?,?)', (url, notice['title'] or old['title'], body))
        else:
            db.execute('UPDATE decisions SET read=? WHERE url=?', (checked, url))
    return result


def paper(r):
    """How an attached PDF is labelled in the archive and in Search."""
    when = r['decided'] or r['listed_date'] or ''
    return dict(committee=COMMITTEE, meeting=' '.join(x for x in [when, f"decision {r['number']}" if r['number'] else ''] if x),
                meeting_url=r['url'])


# ---- The check ----

def check(a, log, progress=None, should_stop=None, full=False, auto=False, download=True):
    """Read the register, then each notice not yet read and each recent one, then save attached PDFs."""
    from archive import now, blocked, plain_error
    from problems import IssueList, resolve
    if a.profile.get('system') != 'moderngov': raise ValueError(NOT_MODERNGOV)
    progress = progress or (lambda info: None); should_stop = should_stop or (lambda: False)
    failures = IssueList(a)
    today = date.today()
    start = EARLIEST if full else today - timedelta(days=WINDOW_DAYS)
    end = today + timedelta(days=AHEAD_DAYS)
    scope = 'Officer decisions, ' + ('all dates' if full else f'published in the last {WINDOW_DAYS} days')
    summary = dict(read=0, added=0, changed=0, missing=0, downloaded=0, baseline=False, note='')
    with a.connect() as db:
        run = db.execute('INSERT INTO check_runs(started,kind,scope,auto) VALUES(?,?,?,?)', (now(), 'decisions', scope, int(auto))).lastrowid
    stopped = False
    try:
        with a.browser(delay=1.0 if full else .25) as (page, links, allowed):
            url = list_url(a.profile['meetings_url'], start, end)
            log('Reading the officer decisions register: ' + url)
            failures.context = dict(title='Officer decisions register', committee=COMMITTEE)
            try:
                links(url); html = page.content()
            except Exception as e:
                failures.append(f'{url}: {plain_error(e)}'); raise RuntimeError('Could not read the officer decisions register: ' + plain_error(e)
                    + '. If the register opens in your own browser, save its pages yourself and use "Add pages you saved yourself" on the Officer decisions tab.') from None
            if not register(html): raise RuntimeError(NO_REGISTER.format(url=url))
            resolve(a, url)
            found = [x for x in parse_list(html, page.url) if allowed(x[0])]
            summary['baseline'] = not tracked(a)
            new, summary['missing'] = record_list(a, found, now(), start.isoformat(), end.isoformat(), html)
            log(f'{len(found)} notice(s) listed; {len(new)} not seen before'
                + (' (first check: these are a baseline, not news)' if summary['baseline'] and new else '') + '.')
            if summary['missing']: log(f"{summary['missing']} notice(s) seen before are no longer listed.")
            summary['added'] = 0 if summary['baseline'] else len(new)
            recent = (today - timedelta(days=REREAD_DAYS)).isoformat()
            with a.connect() as db:
                todo = [dict(r) for r in db.execute(
                    "SELECT url,title,number,listed_date,decided FROM decisions WHERE missing_since='' AND (read='' OR read IS NULL OR published>=?) ORDER BY number DESC", (recent,))]
            if todo: log(f'Reading {len(todo)} notice page(s)…')
            refused = 0
            for i, r in enumerate(todo, 1):
                if should_stop(): stopped = True; break
                if refused >= REFUSAL_LIMIT:
                    summary['note'] = f'The council website refused {refused} notice pages in a row, so the rest were left for a later check.'
                    log(summary['note']); break
                progress(dict(phase='Reading officer decision notices', total=len(todo), completed=i - 1, current=r['title']))
                failures.context = dict(title=r['title'], committee=COMMITTEE, meeting=r['decided'] or r['listed_date'])
                try:
                    links(r['url']); h = page.content()
                    notice = parse_notice(h, page.url)
                    if not notice['recognised']: raise RuntimeError('Decision page was not recognised; nothing recorded.')
                    result = record_notice(a, r['url'], notice, h, now())
                    resolve(a, r['url']); summary['read'] += 1; refused = 0
                    if result == 'changed':
                        summary['changed'] += 1; log('Notice changed since it was last read: ' + notice['title'])
                except Exception as e:
                    failures.append(f"{r['url']}: {plain_error(e)}")
                    refused = refused + 1 if blocked([str(e)]) else 0
            progress(dict(phase='Reading officer decision notices', total=len(todo), completed=summary['read']))
            if download and not stopped:
                docs = attachments(a)
                if docs:
                    log(f'Downloading {len(docs)} PDF(s) attached to notices…')
                    counts, paths, stopped = a.download(page, docs, False, log, failures, progress, should_stop)
                    summary['downloaded'] = counts['new'] + counts['changed']
                    if paths: progress({}); a.index(log, only=paths)
    except Exception as e:
        summary['note'] = str(e); raise
    finally:
        if stopped: summary['note'] = 'Stopped early; completed work saved.'
        with a.connect() as db:
            db.execute('UPDATE check_runs SET finished=?,meetings=?,added=?,downloaded=?,failed=?,note=? WHERE id=?',
                       (now(), summary['read'], summary['added'], summary['downloaded'], len(failures), summary['note'], run))
    for failure in failures: log('Needs attention: ' + failure)
    parts = [f"read {summary['read']} notice page(s)", f"{summary['added']} new notice(s)"]
    if summary['changed']: parts.append(f"{summary['changed']} changed")
    if summary['missing']: parts.append(f"{summary['missing']} no longer listed")
    parts.append(f"{summary['downloaded']} PDF(s) downloaded")
    if failures: parts.append(f'{len(failures)} problem(s) – see Tools › Unavailable papers')
    log(('Stopped: ' if stopped else 'Officer decisions finished: ') + '; '.join(parts) + '.')
    return summary


def attachments(a):
    """PDFs attached to notices that are not yet in the archive. Earlier failures are tried again at each check."""
    with a.connect() as db:
        rows = [dict(r) for r in db.execute("SELECT url,number,title,decided,listed_date,documents FROM decisions WHERE documents<>'[]'")]
    docs = {}
    for r in rows:
        for d in json.loads(r['documents']):
            docs.setdefault(d['url'], dict(title=d['title'] or r['title'], **paper(r)))
    saved = a.lookup_saved(docs)
    return {u: m for u, m in docs.items() if u not in saved}


# ---- Pages saved by hand ----

SAVED_FROM = re.compile(r'<!--\s*saved from url=\(\d+\)(\S+?)\s*-->', re.I)


def saved_folder(a):
    """Where to put officer decision pages and PDFs saved from your own browser."""
    return a.root / 'data' / 'saved_decisions'


def read_saved(path):
    raw = path.read_bytes()
    for encoding in ('utf-8-sig', 'cp1252'):
        try: return raw.decode(encoding)
        except UnicodeDecodeError: pass
    return raw.decode('utf-8', errors='replace')


def saved_url(html, path, home, titles):
    """The council address of a saved notice: from the browser's 'saved from' note, the file name, or the title
    on a saved register page. '' if none of these identifies it."""
    from archive import canonical
    m = SAVED_FROM.search(html[:3000])
    if m and is_decision(m.group(1)): return canonical(m.group(1))
    n = re.fullmatch(r'(?:.*\bID[=_ -]?)?(\d{2,7})', path.stem.strip(), re.I)   # '3528' or '... ID=3528'
    if n: return canonical(urljoin(home, f'ieDecisionDetails.aspx?ID={n.group(1)}'))
    title = re.search(r'(?is)<h2[^>]*class="mgSubTitleTxt"[^>]*>(.*?)</h2>', html)
    key = ' '.join(text(title.group(1)).lower().split()) if title else ''
    return titles.get(key, '') if key else ''


def load_saved(a, log, progress=None, should_stop=None):
    """Read officer decision pages and PDFs saved by hand into data/saved_decisions (any sub-folders).

    Register pages add the notices they list. Notice pages are read as a check would read them. A PDF is added
    when its file name matches a document linked from a notice. Nothing is fetched from the council website.
    Pages saved by hand carry no 'appeared between' evidence: the app did not see when they appeared."""
    from archive import now, canonical, clean_filename
    from urllib.parse import unquote
    progress = progress or (lambda info: None); should_stop = should_stop or (lambda: False)
    folder = saved_folder(a); folder.mkdir(parents=True, exist_ok=True)
    home = a.profile['meetings_url']
    files = sorted(p for p in folder.rglob('*') if p.is_file())
    pages = [p for p in files if p.suffix.lower() in ('.html', '.htm', '.mhtml', '.mht')]
    pdfs = [p for p in files if p.suffix.lower() == '.pdf']
    summary = dict(listed=0, read=0, changed=0, pdfs=0, skipped=[])
    if not pages and not pdfs:
        log(f'No saved pages found. Save officer decision pages from your browser into {folder}, then try again.')
        return summary
    loaded = now()
    with a.connect() as db:
        run = db.execute('INSERT INTO check_runs(started,kind,scope) VALUES(?,?,?)', (loaded, 'decisions', 'Officer decisions, pages saved by hand')).lastrowid
    texts = {}
    for p in pages:
        if p.suffix.lower() in ('.mhtml', '.mht'):
            summary['skipped'].append(f'{p.name}: saved as a single file (.mhtml). Save as "Webpage, HTML only" instead.'); continue
        texts[p] = read_saved(p)
    # Register pages first, so notice pages can be matched to them by title.
    for p, html in texts.items():
        if not register(html): continue
        m = SAVED_FROM.search(html[:3000])
        found = parse_list(html, m.group(1) if m else home)
        with a.connect() as db:
            for url, title, shown in found:
                cur = db.execute("INSERT OR IGNORE INTO decisions(url,number,title,listed_date,first_seen,loaded) VALUES(?,?,?,?,?,?)",
                                 (url, number(url), title, shown, loaded, loaded))
                summary['listed'] += cur.rowcount
        log(f'{p.name}: register page listing {len(found)} notice(s).')
    with a.connect() as db:
        titles = {' '.join((r['title'] or '').lower().split()): r['url'] for r in db.execute('SELECT url,title FROM decisions')}
    notices = [(p, html) for p, html in texts.items() if not register(html)]
    for i, (p, html) in enumerate(notices, 1):
        if should_stop(): break
        progress(dict(phase='Reading saved notice pages', total=len(notices), completed=i - 1, current=p.name))
        url = saved_url(html, p, home, titles)
        notice = parse_notice(html, url or home)
        if not notice['recognised']:
            summary['skipped'].append(f'{p.name}: not an officer decision notice or register page.'); continue
        if not url:
            summary['skipped'].append(f'{p.name}: could not tell which notice this is. Save the register page that lists it into the same folder, or put the decision number in the file name, for example 3528.html.'); continue
        with a.connect() as db:
            db.execute("INSERT OR IGNORE INTO decisions(url,number,title,listed_date,first_seen,loaded) VALUES(?,?,?,?,?,?)",
                       (url, number(url), notice['title'], notice['decided'], loaded, loaded))
        result = record_notice(a, url, notice, html, loaded)
        summary['read'] += 1; summary['changed'] += result == 'changed'
    # PDFs: match on the file name in the document's address, as a browser names a downloaded file.
    if pdfs:
        wanted = {}
        with a.connect() as db:
            for r in db.execute("SELECT url,number,title,decided,listed_date,documents FROM decisions WHERE documents<>'[]'"):
                for d in json.loads(r['documents']):
                    name = unquote(urlparse(d['url']).path.rsplit('/', 1)[-1]).lower()
                    wanted.setdefault(name, (d, dict(r)))
        out = a.root / 'data' / 'raw_documents' / 'web_downloads'; out.mkdir(parents=True, exist_ok=True)
        paths = []
        for p in pdfs:
            match = wanted.get(p.name.lower())
            if not match:
                summary['skipped'].append(f'{p.name}: no saved notice links to a PDF with this name, so it was left alone.'); continue
            d, r = match
            if not p.read_bytes()[:5] == b'%PDF-':
                summary['skipped'].append(f'{p.name}: not a PDF file.'); continue
            label = paper(r); title = d['title'] or r['title']
            target = out / (hashlib.sha256(d['url'].encode()).hexdigest()[:20] + '_' + clean_filename(title)[:80] + '.pdf')
            target.write_bytes(p.read_bytes())
            rel = target.relative_to(a.root).as_posix(); paths.append(rel)
            with a.connect() as db:
                db.execute('INSERT OR REPLACE INTO downloads VALUES(?,?,?,?,?,?)',
                           (d['url'], rel, title, label['committee'], label['meeting'], datetime.now().isoformat()))
            summary['pdfs'] += 1
        if paths: progress({}); a.index(log, only=paths)
    with a.connect() as db:
        db.execute('UPDATE check_runs SET finished=?,meetings=?,added=?,downloaded=?,failed=?,note=? WHERE id=?',
                   (now(), summary['read'], summary['listed'], summary['pdfs'], len(summary['skipped']), 'Loaded from saved pages', run))
    for s in summary['skipped']: log('Not loaded: ' + s)
    log(f"Saved pages loaded: {summary['listed']} notice(s) added from register pages, {summary['read']} notice page(s) read"
        + (f", {summary['changed']} changed" if summary['changed'] else '') + f", {summary['pdfs']} PDF(s) added to your archive"
        + (f"; {len(summary['skipped'])} file(s) not loaded (see above)" if summary['skipped'] else '') + '.')
    return summary


# ---- What the tab shows ----

def days_between(first, second):
    try: return (date.fromisoformat(second) - date.fromisoformat(first)).days
    except (TypeError, ValueError): return None


def latest_run(a):
    with a.connect() as db:
        r = db.execute("SELECT * FROM check_runs WHERE kind='decisions' AND finished IS NOT NULL ORDER BY id DESC LIMIT 1").fetchone()
    return dict(r) if r else None


def matches(db, query, urls=None):
    """Notice urls whose text matches the words or quoted phrases in query."""
    tokens = re.findall(r'"([^"]+)"|(\S+)', query[:1000])
    match = ' AND '.join('"' + (x or y).replace('"', '""') + '"' for x, y in tokens)
    if not match: return set()
    try: return {r[0] for r in db.execute('SELECT url FROM decision_text WHERE decision_text MATCH ?', (match,))}
    except Exception: return set()


def listing(a, window='all', query='', watch=(), watched=False, key_only=False, slow_only=False, lag_only=False, limit=1000):
    """Notices for the Officer decisions tab, newest first, with the evidence for each."""
    from late import local_day
    run = latest_run(a)
    where = []; args = []
    if window == 'latest':
        if not run: return dict(decisions=[], total=0, run=None, tracked=tracked(a), mentions=0, folder=str(saved_folder(a)), register=urljoin(a.profile['meetings_url'], 'mgListOfficerDecisions.aspx?bcr=1&BAM=0'))
        where.append('first_seen>=? AND first_seen<=?'); args += [run['started'], run['finished']]
    elif window in ('7d', '30d', '90d'):
        days = int(window[:-1]); where.append('first_seen>=?')
        args.append((datetime.now(timezone.utc) - timedelta(days=days)).isoformat())
    elif window != 'all': raise ValueError('Choose a time window.')
    with a.connect() as db:
        rows = [dict(r) for r in db.execute('SELECT * FROM decisions' + (' WHERE ' + ' AND '.join(where) if where else '')
                                             + " ORDER BY COALESCE(NULLIF(published,''),listed_date) DESC, number DESC", args)]
        if query.strip():
            hits = matches(db, query); rows = [r for r in rows if r['url'] in hits]
        flagged = {t: matches(db, t) for t in watch}
    lookup = a.lookup([d['url'] for r in rows for d in json.loads(r['documents'] or '[]')])
    result = []
    for r in rows:
        r['documents'] = [dict(d, doc_id=lookup.get(d['url'])) for d in json.loads(r['documents'] or '[]')]
        r['other'] = json.loads(r['other'] or '{}')
        r['gap_days'] = days_between(r['decided'], r['published'])
        r['is_new'] = bool(r['previous_check']) if r['read'] else None   # unknown until the notice is read
        # Not on the register at a check made after the day the notice says it was published.
        r['lag'] = bool(r['previous_check'] and r['published'] and local_day(r['previous_check']) > r['published'])
        r['watch'] = [t for t in watch if r['url'] in flagged[t] or t.lower() in (r['title'] or '').lower()]
        r.pop('fingerprint', None)
        if watched and not r['watch']: continue
        if key_only and r['key_decision'].lower() != 'yes': continue
        if slow_only and not (r['gap_days'] is not None and r['gap_days'] >= SLOW_DAYS): continue
        if lag_only and not r['lag']: continue
        result.append(r)
    with a.connect() as db: known = bool(db.execute('SELECT 1 FROM decisions LIMIT 1').fetchone())
    return dict(decisions=result[:limit], total=len(result), run=run, tracked=tracked(a) or known, folder=str(saved_folder(a)),
                register=urljoin(a.profile['meetings_url'], 'mgListOfficerDecisions.aspx?bcr=1&BAM=0'),
                mentions=sum(bool(r['watch']) for r in result), slow_days=SLOW_DAYS,
                unread=sum(1 for r in rows if not r['read']))
