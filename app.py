from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote
from pathlib import Path
import argparse, json, secrets, threading, webbrowser, shutil, re, time
from datetime import datetime, date, timedelta
from archive import Archive
from readers import PRESETS
from exports import pdf_name, disposition, source, bundle

TOKEN=secrets.token_urlsafe(32)
BASE=Path(__file__).parent.resolve()
settings=BASE/'councils-local.json'
profiles={}; archives={}
state={'running':False,'council':'','messages':[]}
lock=threading.Lock()
stop_requested=threading.Event()
AUTO_HOURS=(0,3,6,12,24)
LABELS={'check':'Checking for new papers','fetch':'Downloading papers','rescan':'Refreshing the full meeting list',
        'index':'Adding saved PDFs to search','ocr':'Reading scanned pages','sitecheck':'Checking website connection'}

def progress(info):
    with lock:state['progress']=dict(info)


def save():
    tmp=settings.with_suffix('.tmp');tmp.write_text(json.dumps(profiles,indent=2),encoding='utf-8');tmp.replace(settings)

def slug(text):
    """'Lambeth Council' -> 'lambeth-council'; keeps identifiers valid however they are typed."""
    return re.sub(r'[^a-z0-9]+','-',str(text).lower()).strip('-')[:50]

def add_profile(data):
    preset=data.get('preset','')
    p=dict(PRESETS[preset]) if preset in PRESETS else {k:str(data.get(k,'')).strip() for k in ['id','name','system','meetings_url']}
    p['id']=slug(p['id'] or p['name'])
    if not re.fullmatch(r'[a-z][a-z0-9_-]{1,49}',p['id']): raise ValueError('Use a short identifier made of letters, such as leeds or north-somerset.')
    if p['id'] in profiles: raise ValueError('This council is already configured.')
    if not p['name'] or p['system'] not in ('cmis','moderngov'): raise ValueError('Enter a name and supported website system.')
    url=urlparse(p['meetings_url'])
    if url.scheme not in ('http','https') or not url.hostname or url.username or url.password: raise ValueError('Enter a valid council committee website address.')
    p['root']=str(Path(data.get('root') or BASE/'archives'/p['id']).expanduser().resolve())
    root=Path(p['root'])
    for other in profiles.values():
        existing=Path(other['root']).resolve()
        if root==existing or root.is_relative_to(existing):
            raise ValueError(f"That folder is inside {other['name']}'s archive ({existing}). Choose a folder next to it instead, for example {existing.parent/p['id']}, or leave the box blank.")
        if existing.is_relative_to(root):
            raise ValueError(f"That folder contains {other['name']}'s archive. Choose a separate folder for {p['name']}, or leave the box blank.")
    marker=root/'data'/'archive_web'/'council-profile.json'
    if marker.exists():
        owner=json.loads(marker.read_text())
        if owner['id']!=p['id']: raise ValueError('That archive belongs to another council.')
    elif (root/'data'/'archive_web'/'search.sqlite3').exists() and p['id']!='bristol':
        raise ValueError('This appears to be an existing Bristol archive. Choose an empty folder for this council.')
    elif (root/'data'/'raw_documents').exists() and p['id']!='bristol' and any((root/'data'/'raw_documents').iterdir()):
        raise ValueError('For a new council, choose an empty folder; you can copy its PDFs into data/raw_documents afterwards.')
    (root/'data'/'raw_documents').mkdir(parents=True,exist_ok=True)
    a=Archive(root,p)
    marker.write_text(json.dumps(p,indent=2),encoding='utf-8')
    profiles[p['id']]=p;archives[p['id']]=a;save()
    return p

def log(message):
    line=datetime.now().astimezone().isoformat(timespec='seconds')+'  '+message
    with lock:
        state['messages'].append(line);state['messages']=state['messages'][-200:]
        key=state['council']
    if key in archives:
        with (archives[key].work/'activity.log').open('a',encoding='utf-8') as f:f.write(line+'\n')

def strings(value,limit,name):
    if not isinstance(value,list) or len(value)>limit or any(not isinstance(x,str) for x in value):
        raise ValueError(f'Invalid {name} list.')
    return value

def valid_date(value):
    if value:date.fromisoformat(value)
    return value or ''

def scope_text(data):
    committees=data.get('committees') or []
    who='all committees' if not committees else (committees[0] if len(committees)==1 else f'{len(committees)} committees')
    if data.get('urls'):return f"{len(data['urls'])} chosen paper(s)"
    if data.get('meetings'):return f"{len(data['meetings'])} chosen meeting(s)"
    when=' from '+data['date_from'] if data.get('date_from') else ''
    when+=' to '+data['date_to'] if data.get('date_to') else ''
    return who+(when or ', all dates')

def work(action,key,data=None,auto=False):
    data=data or {}
    try:
        log('Starting: '+LABELS.get(action,action)+' for '+profiles[key]['name']+('' if not auto else ' (automatic check)'))
        a=archives[key]
        if action=='index':a.index(log)
        elif action=='ocr':
            import ocr
            ocr.run(a,log,progress,stop_requested.is_set)
        elif action=='sitecheck':a.site_check(log)
        elif action=='rescan':a.rescan(log)
        else:
            a.collect(log,progress,stop_requested.is_set,committees=data.get('committees') or [],
                date_from=data.get('date_from',''),date_to=data.get('date_to',''),meetings=data.get('meetings') or [],
                urls=data.get('urls') or [],download=bool(data.get('download',action=='fetch')),
                refresh=bool(data.get('refresh',True)),recheck=bool(data.get('recheck',False)),auto=auto,scope=scope_text(data))
    except Exception as e:log('Stopped: '+str(e))
    finally:
        with lock:state['running']=False

def start(action,key,data,auto=False):
    """Caller holds the lock and has checked nothing is running."""
    stop_requested.clear()
    state.update(running=True,council=key,messages=[],action=action,progress={},started=time.time(),auto=auto)
    threading.Thread(target=work,args=(action,key,data,auto),daemon=True).start()

def validate_job(action,data):
    if action in ('check','fetch'):
        data['committees']=strings(data.get('committees') or [],500,'committee')
        data['meetings']=strings(data.get('meetings') or [],3000,'meeting')
        data['urls']=strings(data.get('urls') or [],2000,'paper')
        data['date_from']=valid_date(data.get('date_from'));data['date_to']=valid_date(data.get('date_to'))
        if data['date_from'] and data['date_to'] and data['date_from']>data['date_to']:raise ValueError('The end date must follow the start date.')
        if action=='fetch' and not (data['urls'] or data['meetings'] or data['committees'] or data['date_from'] or data['date_to']):
            raise ValueError('Choose papers, meetings or committees to download.')
    return data

def auto_checker():
    """While the app is open, run the default check (all committees, upcoming and last 30 days) on schedule."""
    attempted={}
    while True:
        time.sleep(60)
        for key,p in list(profiles.items()):
            hours=p.get('auto_check_hours',0)
            if not hours or key not in archives:continue
            last=archives[key].latest_check()
            last_time=datetime.fromisoformat(last['started']).timestamp() if last else 0
            last_time=max(last_time,attempted.get(key,0))
            if time.time()-last_time<hours*3600:continue
            with lock:
                if state['running']:break
                attempted[key]=time.time()
                start('check',key,dict(committees=[],date_from=(date.today()-timedelta(days=30)).isoformat(),
                    download=p.get('auto_download',True)),auto=True)
            break

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def respond(self,obj,status=200):
        content=json.dumps(obj).encode();self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(content)))
        self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(content)
    def valid_host(self):
        return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}')
    def do_GET(self):
        if not self.valid_host():return self.respond({'error':'Invalid host'},403)
        p=urlparse(self.path);q=parse_qs(p.query)
        one=lambda name,default='':q.get(name,[default])[0]
        try:
            if p.path=='/':
                body=(BASE/'templates/index.html').read_text(encoding='utf-8').replace('__TOKEN__',TOKEN).encode()
                self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Cache-Control','no-store')
                self.end_headers();self.wfile.write(body);return
            if p.path=='/api/councils':return self.respond({'profiles':list(profiles.values()),'presets':list(PRESETS.values())})
            key=one('council')
            if p.path.startswith('/pdf/'):
                parts=p.path.split('/')
                if len(parts) not in (4,5):raise ValueError('Invalid PDF address.')
                key,ident=parts[2:4]
            a=archives.get(key)
            if not a:raise ValueError('Choose or add a council first.')
            if p.path=='/api/status':
                with lock:result=dict(running=state['running'],job_council=state['council'],messages=list(state['messages']),action=state.get('action',''),label=LABELS.get(state.get('action',''),''),auto=state.get('auto',False),progress=dict(state.get('progress',{})),started=state.get('started'),stop_requested=stop_requested.is_set())
                result.update(a.stats());result['root']=str(a.root);result['name']=profiles[key]['name']
                result.update(latest_check=a.latest_check(),new_unsaved=a.news_count(),
                    auto_check_hours=profiles[key].get('auto_check_hours',0),auto_download=profiles[key].get('auto_download',True))
                self.respond(result)
            elif p.path=='/api/search':self.respond(a.search(one('q'),q.get('committee',[]),max(0,int(one('offset','0'))),one('issues')=='1',one('date_from'),one('date_to'),one('sort','relevance')))
            elif p.path=='/api/committees':self.respond(a.committees())
            elif p.path=='/api/meetings':self.respond(a.meetings(q.get('committee',[]),valid_date(one('date_from')),valid_date(one('date_to'))))
            elif p.path=='/api/papers':self.respond(a.papers(meeting_urls=q.get('meeting',[])[:500]))
            elif p.path=='/api/news':self.respond(a.news(one('window','latest'),q.get('committee',[]),one('unsaved')=='1',one('baseline')=='1'))
            elif p.path=='/api/runs':self.respond(a.runs())
            elif p.path=='/api/ocr':
                import ocr
                self.respond(ocr.details(a))
            elif p.path=='/api/problems':
                from problems import items
                self.respond(items(a))
            elif p.path=='/api/replacements':
                f=a.work/'replacements.jsonl'
                self.respond([json.loads(x) for x in f.read_text().splitlines()][-500:][::-1] if f.exists() else [])
            elif p.path.startswith('/pdf/'):
                with a.connect() as db:row=db.execute('SELECT * FROM docs WHERE id=?',(int(ident),)).fetchone()
                if not row:return self.respond({'error':'Document not found'},404)
                file=source(a,row);name=pdf_name(row)
                if len(parts)==4:
                    target='/pdf/'+quote(key,safe='')+'/'+str(row['id'])+'/'+quote(name,safe='')
                    if p.query:target+='?'+p.query
                    self.send_response(302);self.send_header('Location',target);self.end_headers();return
                self.send_response(200);self.send_header('Content-Type','application/pdf');self.send_header('Content-Disposition',disposition(name,one('download')=='1'));self.send_header('Content-Length',str(file.stat().st_size));self.end_headers()
                with file.open('rb') as f:shutil.copyfileobj(f,self.wfile)
            else:self.respond({'error':'Not found'},404)
        except (BrokenPipeError,ConnectionResetError):pass
        except Exception as e:self.respond({'error':str(e)},400)
    def do_POST(self):
        if not self.valid_host():return self.respond({'error':'Invalid host'},403)
        try:
            length=int(self.headers.get('Content-Length','0'))
            if length>2_000_000:raise ValueError('Request too large.')
            body=self.rfile.read(length)
            action=self.path.removeprefix('/api/')
            # ZIP downloads are posted as a form so the browser saves the file itself, however large.
            form=action=='export' and self.headers.get('Content-Type','').startswith('application/x-www-form-urlencoded')
            if form:
                fields=parse_qs(body.decode())
                token=fields.get('token',[''])[0]
                data=dict(council=fields.get('council',[''])[0],name=fields.get('name',[''])[0],ids=[int(x) for x in fields.get('ids',[''])[0].split(',') if x.isdigit()])
            else:
                token=self.headers.get('X-Archive-Token');data=json.loads(body or '{}')
            if token!=TOKEN:return self.respond({'error':'Refresh the page before trying again.'},403)
            if action=='exportcheck':
                from exports import files
                a=archives.get(data.get('council',''))
                if not a:raise ValueError('Choose a council first.')
                chosen=files(a,data.get('ids'))
                return self.respond(dict(files=len(chosen),bytes=sum(f.stat().st_size for f,n in chosen)))
            if action=='export':
                a=archives.get(data.get('council',''))
                if not a:raise ValueError('Choose a council first.')
                tmp,size=bundle(a,data.get('ids'))
                name=re.sub(r'[<>:"/\\|?*\x00-\x1f]',' ',str(data.get('name') or ''))[:120].strip(' .') or profiles.get(data['council'],{}).get('name','Council')+' papers '+date.today().isoformat()
                name+='.zip'
                with tmp:
                    self.send_response(200)
                    self.send_header('Content-Type','application/zip')
                    self.send_header('Content-Disposition',disposition(name,True))
                    self.send_header('Content-Length',str(size));self.end_headers()
                    shutil.copyfileobj(tmp,self.wfile)
                return
            if action=='lookup':
                a=archives.get(data.get('council',''))
                if not a:raise ValueError('Choose a council first.')
                return self.respond(a.lookup(strings(data.get('urls') or [],5000,'paper')))
            with lock:
                if action=='stop':
                    if not state['running'] or data.get('council')!=state['council'] or state.get('action') not in ('ocr','check','fetch'):
                        return self.respond({'error':'Nothing that can be stopped is running for this council.'},409)
                    stop_requested.set()
                    return self.respond({'stopping':True})
                if action=='settings':
                    key=data.get('council','')
                    if key not in profiles:raise ValueError('Choose a council first.')
                    hours=int(data.get('auto_check_hours',0))
                    if hours not in AUTO_HOURS:raise ValueError('Choose a supported check interval.')
                    profiles[key].update(auto_check_hours=hours,auto_download=bool(data.get('auto_download',True)));save()
                    return self.respond(profiles[key])
                if action=='add':
                    if state['running']:return self.respond({'error':'Wait for the current task to finish.'},409)
                    return self.respond(add_profile(data))
                if action not in LABELS:raise ValueError('Unknown action.')
                if state['running']:return self.respond({'error':'Wait for the current task to finish, or stop it.'},409)
                key=data.get('council','')
                if key not in archives:raise ValueError('Choose a council first.')
                start(action,key,validate_job(action,data))
            self.respond({'started':True})
        except Exception as e:self.respond({'error':str(e)},400)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root');parser.add_argument('--port',type=int,default=8765);parser.add_argument('--no-browser',action='store_true')
    args=parser.parse_args()
    # Bind first: a second launcher must not rewrite configuration while another runs.
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    if settings.exists():
        profiles.update(json.loads(settings.read_text(encoding='utf-8')))
        for key,p in profiles.items():archives[key]=Archive(p['root'],p)
    if not profiles:
        old=BASE/'settings.json'
        root=args.root or (json.loads(old.read_text())['root'] if old.exists() else '')
        if root:add_profile({'preset':'bristol','root':root})
    threading.Thread(target=auto_checker,daemon=True).start()
    url=f'http://127.0.0.1:{server.server_port}'
    print('Council archive: '+url+'\nKeep this window open. Press Ctrl+C to stop.')
    if not args.no_browser:webbrowser.open(url)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()

if __name__=='__main__':main()
