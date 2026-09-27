"""Website-specific discovery, separate from archive and search code."""
from urllib.parse import urlparse, urljoin
from html.parser import HTMLParser
import re

PRESETS = {
 'bristol': dict(id='bristol',name='Bristol City Council',system='moderngov',meetings_url='https://democracy.bristol.gov.uk/ieDocHome.aspx?bcr=1'),
 'birmingham': dict(id='birmingham',name='Birmingham City Council',system='cmis',meetings_url='https://birmingham.cmis.uk.com/birmingham/'),
 'sheffield': dict(id='sheffield',name='Sheffield City Council',system='moderngov',meetings_url='https://democracy.sheffield.gov.uk/ieDocHome.aspx?bcr=1'),
 'gloucester': dict(id='gloucester',name='Gloucester City Council',system='moderngov',meetings_url='https://democracy.gloucester.gov.uk/ieDocHome.aspx?bcr=1'),
 'gloucestershire': dict(id='gloucestershire',name='Gloucestershire County Council',system='moderngov',meetings_url='https://glostext.gloucestershire.gov.uk/ieDocHome.aspx?bcr=1'),
 'lambeth': dict(id='lambeth',name='Lambeth Council',system='moderngov',meetings_url='https://moderngov.lambeth.gov.uk/mgListCommittees.aspx?bcr=1')
}

class Links(HTMLParser):
    def __init__(self): super().__init__(); self.links=[]; self.href=None; self.words=[]
    def handle_starttag(self,tag,attrs):
        if tag=='a': self.href=dict(attrs).get('href'); self.words=[]
    def handle_data(self,data):
        if self.href is not None: self.words.append(data)
    def handle_endtag(self,tag):
        if tag=='a' and self.href is not None:
            self.links.append((self.href,' '.join(' '.join(self.words).split()))); self.href=None

def parse_links(html,base):
    p=Links();p.feed(html)
    result=[]
    for href,text in p.links:
        u=urljoin(base,href)
        if urlparse(u).scheme not in ('http','https'): continue
        if urlparse(base).scheme=='https' and urlparse(u).hostname==urlparse(base).hostname:
            u=re.sub(r'^http:', 'https:',u)
        result.append((u,text))
    return result

class Reader:
    def __init__(self,system):
        if system not in ('moderngov','cmis'): raise ValueError('Supported systems: ModernGov and CMIS.')
        self.system=system
    def meeting(self,url):
        return ('ielistdocuments.aspx' in url.lower() if self.system=='moderngov' else '/ctl/viewmeetingpublic/' in url.lower())
    def document(self,url):
        return '.pdf' in url.lower() or 'mgconvert2pdf' in url.lower() or (self.system=='cmis' and '/document.ashx?' in url.lower())
    def recognised(self,url,html):
        lower=html.lower()
        if not self.meeting(url): return False
        return ('agenda' in lower and ('mg' in lower or 'minutes' in lower)) if self.system=='moderngov' else ('viewmeetingpublic' in lower and 'meeting' in lower and ('agenda' in lower or 'meetingdetails' in lower))
    def listing(self,url):
        lo=url.lower()
        if self.system=='moderngov':return 'ielistmeetings.aspx' in lo
        return ('viewcmis_committeedetails' in lo or
                (('/committee/' in lo or '/committees-old' in lo) and '/ctl/' not in lo and 'venue' not in lo))

    def details(self,url):
        """ModernGov committee details page, used by some councils (e.g. Lambeth) between the committee list and its meetings."""
        return self.system=='moderngov' and 'mgcommitteedetails.aspx' in url.lower()

    def pagination(self,url,title):
        text=' '.join(title.lower().split())
        return ('changepage=' in url.lower() or text.isdigit() or
                bool(re.search(r'\b(earlier|later|previous|next|older|newer)\b',text)))

    def check(self,home,get_links,log):
        """Bounded diagnostic; no full discovery, PDFs or publication observations."""
        queue=[(home,'Council committee homepage')];queued={home};visited=set()
        samples={};preferred=[];ok=failed=checked=documents=0
        log('Checking a small sample: up to 6 listing pages and 3 meeting pages. No PDFs will be downloaded.')
        def fetch(url,title):
            nonlocal ok,failed
            log('Checking '+title+': '+url)
            try:links=get_links(url)
            except Exception as e:
                failed+=1
                reason='Access refused by the council website (HTTP 403)' if 'HTTP 403' in str(e) else str(e)
                log('Could not check '+title+': '+reason+'. Page: '+url)
                return None
            ok+=1
            log('Page accessible: '+title)
            return links
        while queue and len(visited)<6:
            url,title=queue.pop(0);visited.add(url)
            links=fetch(url,title)
            if links is None:continue
            first=None
            for u,t in links:
                if self.meeting(u):
                    if u not in samples:
                        samples[u]=(title+' / '+(t or 'Meeting'))
                        if first is None:first=u
                elif self.listing(u) and u not in queued and not self.pagination(u,t):
                    queued.add(u);queue.append((u,t or title))
            if first:preferred.append(first)
        # Take one meeting per sampled listing first, then fill any spare slots.
        choices=list(dict.fromkeys(preferred+list(samples)))[:3]
        for url in choices:
            links=fetch(url,samples[url])
            if links is None:continue
            checked+=1
            n=len({u for u,t in links if self.document(u)})
            documents+=n
            log(f'Sample meeting has {n} document links. '+('No links can mean papers are not yet published.' if not n else 'PDF contents have not been checked.'))
        if not choices:log('No meeting links found within this small sample. Use Find meetings for a wider scan; check the configured website address and reader if that also finds none.')
        elif not checked:log('No sampled meeting page could be checked. Try its link in your browser; you can try the check again later.')
        log(f'Website check complete: {ok} pages accessible, {failed} could not be checked; {checked} meeting pages checked, {documents} document links found. This is a sample only. Saved papers are unchanged. See the activity log for page addresses and details.')
        return dict(accessible=ok,failed=failed,meetings_checked=checked,document_links=documents)

    def discover(self,home,get_links,log,failures,skip=None,pagination=True):
        """Crawl committee listings. pagination=False reads current listing pages only;
        skip(name) leaves out committees that are not wanted."""
        meetings={}; queue=[(home,'',0)]; visited=set()
        while queue and len(visited)<2000:
            url,title,depth=queue.pop(0)
            if url in visited: continue
            visited.add(url);log(f'Finding meetings: listing page {len(visited)}; {len(meetings)} meeting links found; '+(title or 'Council committee homepage')+' | '+url)
            try: links=get_links(url)
            except Exception as e: failures.append(f'{url}: {e}');continue
            for u,t in links:
                lo=u.lower()
                if self.meeting(u):
                    # A committee page names the meeting better than a homepage link does.
                    if u not in meetings or (title and not meetings[u][0]): meetings[u]=(title,t)
                    continue
                if self.details(u):
                    # Only from the committee list: committee pages also link back to their own details page.
                    if url==home and u not in visited and not (skip and skip(t)):queue.append((u,t,depth))
                    continue
                follow=self.listing(u)
                if follow and u not in visited:
                    if not pagination and depth+1>(1 if self.system=='moderngov' else 2): continue
                    paged=self.pagination(u,t)
                    if paged and not pagination: continue
                    # Keep the committee name across pagination and generic "browse meetings" links.
                    generic=paged or not t or bool(re.search(r'browse meetings|meetings and agendas|for this committee',t,re.I))
                    name=title if generic and title else (t or title)
                    if skip and skip(name): continue
                    queue.append((u,name,depth+1))
        if queue: failures.append('Discovery stopped at 2,000 pages; some older pages may not have been checked.')
        if not meetings: raise RuntimeError('No meetings found. Use Check website and confirm the committee homepage and website system.')
        return meetings
