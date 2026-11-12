"""Saved examples of each built-in council's pages, and a live check that the real pages still look the same.

    python tests/council_pages.py check      compare the live websites with the saved examples (about 2 minutes)
    python tests/council_pages.py capture    save fresh examples (maintainers; then review and commit tests/pages)
    python tests/council_pages.py capture lambeth    refresh one council only

The saved examples are skeletons: only the links the app's readers use. Paper names are replaced, so no
document titles or personal names are stored. They let the offline tests (test_council_pages.py) prove the
readers against each council's real page layout. The live check is what notices a council changing its website."""
import json,re,sys,time
from datetime import date
from html import escape
from pathlib import Path
from urllib.parse import urlparse,urlunparse
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from archive import canonical
from planning import meeting_date
from readers import PRESETS,Reader,parse_links

PAGES=Path(__file__).with_name('pages')
MANIFEST=PAGES/'manifest.json'
# Page layouts the automatic choice would not reach: Bristol's pre-2016 meeting format.
EXTRA={'bristol':[('old_meeting','https://democracy.bristol.gov.uk/CeListDocuments.aspx?CommitteeId=279&DF=14%2F12%2F2015&MeetingId=1396&Ver=2')]}
KINDS=('listings','details','meetings','documents','full_lists','years')

def classify(reader,url,html):
    """Every link the reader would act on, by kind. Year pages come from the listing's drop-down."""
    kinds={k:[] for k in KINDS}
    for u,t in parse_links(html,url):
        if urlparse(u).hostname!=urlparse(url).hostname:continue
        if reader.meeting(u):kinds['meetings'].append((u,t))
        elif reader.document(u):kinds['documents'].append((u,t))
        elif reader.more_documents(u,t):kinds['full_lists'].append((u,t))
        elif reader.details(u):kinds['details'].append((u,t))
        elif reader.listing(u):kinds['listings'].append((u,t))
    kinds['years']=reader.extra_links(html,url)
    return {k:list(dict.fromkeys(v)) for k,v in kinds.items()}

def counts(kinds):return {k:len(v) for k,v in kinds.items() if v}

def anonymous(url):
    """Keep the address shape the reader relies on; drop the paper's file name."""
    p=urlparse(url)
    path=re.sub(r'[^/]+\.pdf$','paper.pdf',p.path,flags=re.I)
    return urlunparse(p._replace(path=path))

def skeleton(reader,url,html,captured):
    kinds=classify(reader,url,html)
    lines=[f'<!-- Skeleton of {url} captured {captured}. Links the reader uses only; paper names replaced. -->','<html><body>']
    if reader.meeting(url) and reader.recognised(url,html):
        lines.append('<h1>Agenda</h1><div class="mgContent viewmeetingpublic meetingdetails">Meeting</div>')
    if kinds['years']:
        lines.append('<select name="YearSelect">'+''.join(f'<option value="{t}">{t}</option>' for u,t in kinds['years'])+'</select>')
    for kind in ('listings','details','meetings','full_lists'):
        lines+=[f'<a href="{escape(u)}">{escape(t)}</a>' for u,t in kinds[kind][:80]]
    lines+=[f'<a href="{escape(anonymous(u))}">Paper {i} PDF 100 KB</a>' for i,(u,t) in enumerate(kinds['documents'][:80],1)]
    return '\n'.join(lines+['</body></html>',''])

class Site:
    """One polite browser session: a second between pages, one retry after a refusal."""
    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self.pw=sync_playwright().start();self.browser=self.pw.chromium.launch(headless=True);self.page=self.browser.new_page();return self
    def __exit__(self,*a):self.browser.close();self.pw.stop()
    def get(self,url):
        response=self.page.goto(url,wait_until='domcontentloaded',timeout=60000)
        if response and response.status in (403,429):
            time.sleep(30);response=self.page.goto(url,wait_until='domcontentloaded',timeout=60000)
        if response and response.status>=400:raise RuntimeError(f'HTTP {response.status}')
        html=self.page.content();time.sleep(1)
        return self.page.url,html

def choose(site,reader,home):
    """The pages from the home page down to one committee's meetings, one past meeting with papers,
    and an agenda item's full list if there is one. Councils differ in how many steps that takes."""
    today=date.today().isoformat();seen={canonical(home)};queue=[(home,[])];read=tried=0
    def page(role,url):
        final,html=site.get(url)
        return dict(role=role,url=canonical(url),base=final,html=html),classify(reader,final,html)
    while queue and read<12:
        url,chain=queue.pop(0);read+=1
        role='home' if not chain else 'details' if reader.details(url) else 'listing'
        role+=str(sum(c['role'].startswith(role) for c in chain)+1) if any(c['role'].startswith(role) for c in chain) else ''
        entry,kinds=page(role,url);chain=chain+[entry]
        if len(chain)>1 and kinds['meetings']:
            past=[(u,t) for u,t in kinds['meetings'] if not meeting_date(t) or meeting_date(t)<today]
            best=None
            for u,t in past[:4]:
                if tried>=12:break
                tried+=1;meeting,k=page('meeting',u)
                if not reader.recognised(meeting['base'],meeting['html']) or not k['documents']:continue
                if best is None or len(k['documents'])>len(best[1]['documents']):best=(meeting,k)
                if k['full_lists'] or len(k['documents'])>=3:break
            if best:
                chain.append(best[0])
                if best[1]['full_lists']:chain.append(page('item',best[1]['full_lists'][0][0])[0])
                return chain
        if len(chain)<=3:
            # Follow a committee's own pages before trying the next committee.
            new=[(u,chain) for u,t in kinds['details'][:2]+kinds['listings'][:3] if canonical(u) not in seen and not reader.pagination(u,t)]
            seen.update(canonical(u) for u,c in new);queue[:0]=new
    raise RuntimeError('No committee with a past meeting that has papers was found.')

def capture(only=()):
    PAGES.mkdir(exist_ok=True);captured=date.today().isoformat()
    manifest=json.loads(MANIFEST.read_text(encoding='utf-8')) if only and MANIFEST.exists() else {}
    with Site() as site:
        for key,preset in PRESETS.items():
            if only and key not in only:continue
            reader=Reader(preset['system']);print('Capturing',preset['name'],flush=True)
            pages=choose(site,reader,preset['meetings_url'])
            for role,url in EXTRA.get(key,[]):
                final,html=site.get(url);pages.append(dict(role=role,url=canonical(url),base=final,html=html))
            entries=[]
            for p in pages:
                text=skeleton(reader,p['base'],p['html'],captured);name=f"{key}-{p['role']}.html"
                (PAGES/name).write_text(text,encoding='utf-8',newline='\n')
                entries.append(dict(role=p['role'],file=name,url=p['url'],base=p['base'],expect=counts(classify(reader,p['base'],text))))
                print('  ',p['role'],entries[-1]['expect'],flush=True)
            manifest[key]=dict(name=preset['name'],system=preset['system'],captured=captured,pages=entries)
    MANIFEST.write_text(json.dumps(manifest,indent=1),encoding='utf-8',newline='\n')
    print('Saved',MANIFEST)

def check():
    """Each kind of link the saved example has must still be found on the live page."""
    manifest=json.loads(MANIFEST.read_text(encoding='utf-8'));changed=0
    with Site() as site:
        for key,council in manifest.items():
            reader=Reader(council['system']);print(council['name'],flush=True)
            for p in council['pages']:
                live={}
                try:
                    final,html=site.get(p['url']);live=counts(classify(reader,final,html))
                    lost=[k for k in p['expect'] if not live.get(k)]
                    if p['role'] in ('meeting','old_meeting') and not reader.recognised(final,html):lost.append('meeting page not recognised')
                    note='ok' if not lost else 'CHANGED: no longer found: '+', '.join(lost)
                except Exception as e:
                    lost=['error'];note=f'COULD NOT READ: {e}'
                changed+=bool(lost)
                print(f"   {p['role']:<12}{note}   saved {p['expect']}  live {live}",flush=True)
    print('\nAll saved page layouts still match the live websites.' if not changed else
          f'\n{changed} page(s) differ. If the council changed its website, the reader in readers.py may need updating; '
          'a refusal (HTTP 403) or an expired meeting only needs a fresh capture.')
    return changed

if __name__=='__main__':
    mode=sys.argv[1] if len(sys.argv)>1 else ''
    if mode=='capture':capture(sys.argv[2:])
    elif mode=='check':sys.exit(1 if check() else 0)
    else:print(__doc__)
