import io,json,sys,tempfile,threading,unittest,urllib.request,urllib.error
from pathlib import Path
from zipfile import ZipFile
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from archive import Archive
import app,exports

class ExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.a=Archive(self.root);self.payload=b'%PDF-1.4\nunchanged test bytes'
        (self.root/'paper.pdf').write_bytes(self.payload)
        with self.a.connect() as db:
            for i in (1,2):
                db.execute('INSERT INTO docs(id,path,title,committee,meeting) VALUES(?,?,?,?,?)',(i,'paper.pdf' if i==1 else 'second.pdf','Café: Community / Meals','Adult Social Care','26 September 2026'))
        (self.root/'second.pdf').write_bytes(self.payload)
    def tearDown(self):self.tmp.cleanup()
    def test_names_bytes_and_duplicates(self):
        tmp,size=exports.bundle(self.a,[1,2,1])
        with tmp,ZipFile(tmp) as z:
            names=z.namelist();self.assertEqual(len(names),2)
            for name in names:
                self.assertTrue(name.startswith('2026-09-26 - Café Community Meals'))
                self.assertNotIn('/',name);self.assertEqual(z.read(name),self.payload)
            self.assertNotEqual(names[0],names[1])
        self.assertEqual((self.root/'paper.pdf').read_bytes(),self.payload)
    def test_validation(self):
        for ids in ([],[True],['1'],[0],[999],list(range(1,502))):
            with self.assertRaises(ValueError):exports.bundle(self.a,ids)
        with patch.object(exports,'MAX_BYTES',1):
            with self.assertRaisesRegex(ValueError,'exceed'):exports.bundle(self.a,[1])
        (self.root/'paper.pdf').unlink()
        with self.assertRaisesRegex(ValueError,'unavailable'):exports.bundle(self.a,[1])
    def test_path_escape(self):
        with self.a.connect() as db:db.execute("UPDATE docs SET path='../outside.pdf' WHERE id=1")
        with self.assertRaisesRegex(ValueError,'unavailable'):exports.bundle(self.a,[1])
    def test_http_names_attachment_and_zip(self):
        old=app.archives.copy();app.archives['export-test']=self.a
        server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{server.server_port}'
        try:
            for suffix,mode in [('', 'inline'),('?download=1','attachment')]:
                with urllib.request.urlopen(base+'/pdf/export-test/1'+suffix) as r:
                    self.assertEqual(r.read(),self.payload)
                    self.assertIn('Community',r.url)
                    header=r.headers['Content-Disposition'];self.assertTrue(header.startswith(mode))
                    self.assertIn('filename*=UTF-8',header);self.assertIn('Caf%C3%A9',header)
            data=json.dumps({'council':'export-test','ids':[1,2]}).encode()
            for token,code in [('wrong',403),(app.TOKEN,200)]:
                request=urllib.request.Request(base+'/api/export',data=data,headers={'X-Archive-Token':token,'Content-Type':'application/json'})
                if code==403:
                    with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(request)
                    self.assertEqual(error.exception.code,403)
                else:
                    with urllib.request.urlopen(request) as r:
                        self.assertEqual(r.headers['Content-Type'],'application/zip')
                        with ZipFile(io.BytesIO(r.read())) as z:self.assertEqual(len(z.namelist()),2)
        finally:
            server.shutdown();server.server_close();app.archives.clear();app.archives.update(old)
if __name__=='__main__':unittest.main()
