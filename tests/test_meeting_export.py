import io,json,sys,tempfile,threading,unittest,urllib.request,urllib.parse
from pathlib import Path
from zipfile import ZipFile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from archive import Archive
import app,exports

MEETING='https://example.gov.uk/ieListDocuments.aspx?MId=1'

class MeetingExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.a=Archive(self.root);self.payload=b'%PDF-1.4\nunchanged test bytes'
        (self.root/'pack.pdf').write_bytes(self.payload)
        with self.a.connect() as db:
            db.execute('INSERT INTO docs(id,path,title,committee,meeting,url,page_count,warning) VALUES(1,?,?,?,?,?,2,?)',
                ('pack.pdf','Public reports pack','Harbour Committee','23 June 2026','https://example.gov.uk/pack.pdf',''))
            db.executemany('INSERT INTO pages VALUES(?,?,?,?)',[(1,1,'Public reports pack','Agenda'),(1,2,'Public reports pack','Item 5 | loan')])
            db.execute('INSERT INTO meeting_checks VALUES(?,?)',(MEETING,'2026-06-20T09:00:00+00:00'))
            rows=[('https://example.gov.uk/pack.pdf','Public reports pack','2026-06-10T09:00:00+00:00',''),
                  ('https://example.gov.uk/supp.pdf','Supplement 1','2026-06-19T09:00:00+00:00','2026-06-18T09:00:00+00:00')]
            for url,title,seen,prev in rows:
                db.execute('INSERT INTO observations VALUES(?,?,?,?,?,?,?)',(url,MEETING,title,'Harbour Committee','23 June 2026',seen,prev))
    def tearDown(self):self.tmp.cleanup()

    def read(self):
        tmp,size,info=exports.meeting_bundle(self.a,MEETING)
        with tmp:z=ZipFile(io.BytesIO(tmp.read()))
        return z,info

    def test_bundle_contents(self):
        z,info=self.read();names=z.namelist()
        for required in ('README.txt','meeting.json','papers.md','all-text.txt'):self.assertIn(required,names)
        pdfs=[n for n in names if n.startswith('papers/')];texts=[n for n in names if n.startswith('text/')]
        self.assertEqual(len(pdfs),1);self.assertEqual(z.read(pdfs[0]),self.payload)
        self.assertEqual(z.read(texts[0]).decode(),'=== PAGE 1 ===\nAgenda\n=== PAGE 2 ===\nItem 5 | loan')
        self.assertEqual((self.root/'pack.pdf').read_bytes(),self.payload)
        manifest=json.loads(z.read('meeting.json'))
        self.assertEqual(manifest['committee'],'Harbour Committee');self.assertEqual(manifest['date'],'2026-06-23')
        first,second=manifest['papers']
        self.assertTrue(first['in_archive']);self.assertEqual(first['pages'],2);self.assertTrue(first['timing'].startswith('Present at first check'))
        self.assertFalse(second['in_archive']);self.assertEqual(second['pdf'],'')
        self.assertEqual(second['timing'],'Appeared between 2026-06-18 09:00 and 2026-06-19 09:00 (UTC)')
        table=z.read('papers.md').decode()
        self.assertIn('Supplement 1',table);self.assertIn('Not in the archive',table)
        self.assertIn('##### PAPER 1: Public reports pack',z.read('all-text.txt').decode())

    def test_unknown_meeting(self):
        with self.assertRaisesRegex(ValueError,'No papers'):exports.meeting_bundle(self.a,'https://example.gov.uk/none')

    def test_http_route(self):
        old=app.archives.copy();app.archives['meeting-test']=self.a
        server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        base=f'http://127.0.0.1:{server.server_port}'
        try:
            check=urllib.request.Request(base+'/api/meetingcheck',data=json.dumps({'council':'meeting-test','meeting':MEETING}).encode(),
                headers={'X-Archive-Token':app.TOKEN,'Content-Type':'application/json'})
            with urllib.request.urlopen(check) as r:self.assertEqual(json.load(r),{'papers':2,'saved':1})
            form=urllib.parse.urlencode({'token':app.TOKEN,'council':'meeting-test','meeting':MEETING}).encode()
            with urllib.request.urlopen(urllib.request.Request(base+'/api/meetingzip',data=form,headers={'Content-Type':'application/x-www-form-urlencoded'})) as r:
                self.assertEqual(r.headers['Content-Type'],'application/zip')
                self.assertIn('Harbour Committee 2026-06-23.zip',urllib.parse.unquote(r.headers['Content-Disposition']))
                self.assertIn('meeting.json',ZipFile(io.BytesIO(r.read())).namelist())
        finally:
            server.shutdown();server.server_close();app.archives.clear();app.archives.update(old)

if __name__=='__main__':unittest.main()
