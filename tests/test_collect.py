"""Offline checks for meeting selection, new-paper rules and quick meeting-list refresh."""
import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from archive import Archive,is_news
from planning import meeting_date
from readers import Reader

class CollectTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.a=Archive(self.tmp.name)
        m='https://council.test/ieListDocuments.aspx?MId='
        self.a.write_json('meeting_catalog.json',dict(created='',issues=[],meetings=[
            dict(url=m+'1',committee='Cabinet',label='1 Sep 2026',date='2026-09-01'),
            dict(url=m+'2',committee='Cabinet',label='1 Mar 2020',date='2020-03-01'),
            dict(url=m+'3',committee='Audit',label='Date to be confirmed',date='')]))
        self.m=m
    def tearDown(self):self.tmp.cleanup()
    def test_select_meetings(self):
        rows,unknown=self.a.select_meetings(['Cabinet'],'2026-01-01')
        self.assertEqual([r['url'] for r in rows],[self.m+'1']);self.assertEqual(unknown,0)
        rows,unknown=self.a.select_meetings([],'2020-01-01','2026-12-31')
        self.assertEqual(len(rows),2);self.assertEqual(unknown,1)
        self.assertEqual(rows[0]['date'],'2026-09-01')  # newest first
        self.assertEqual(len(self.a.select_meetings()[0]),3)
    def test_observations_and_news(self):
        added,first=self.a.record_observation(self.m+'1','Cabinet','1 Sep 2026',[('https://council.test/a.pdf','A')],'<html></html>','2026-09-20T10:00:00+00:00')
        self.assertEqual((added,first),(1,True))
        added,first=self.a.record_observation(self.m+'1','Cabinet','1 Sep 2026',[('https://council.test/a.pdf','A'),('https://council.test/b.pdf','B')],'<html></html>','2026-09-21T10:00:00+00:00')
        self.assertEqual((added,first),(1,False))
        papers={p['url']:p for p in self.a.papers(meeting_urls=[self.m+'1'])}
        self.assertEqual(papers['https://council.test/b.pdf']['previous_check'],'2026-09-20T10:00:00+00:00')
        self.assertFalse(papers['https://council.test/a.pdf']['downloaded'])
        stats=self.a.meetings(['Cabinet'])['meetings'][0]
        self.assertEqual((stats['papers'],stats['saved']),(2,0))
    def test_is_news(self):
        p=dict(previous_check='',meeting='1 Mar 2020',first_seen='2026-09-20T10:00:00+00:00')
        self.assertFalse(is_news(p,meeting_date))  # old meeting seen for the first time: baseline
        self.assertTrue(is_news(dict(p,meeting='1 Oct 2026'),meeting_date))  # upcoming meeting
        self.assertTrue(is_news(dict(p,previous_check='2026-09-19'),meeting_date))
    def test_quick_discovery_skips_pagination_and_unwanted_committees(self):
        home='https://council.test/home';a='https://council.test/ieListMeetings.aspx?CId=1';b='https://council.test/ieListMeetings.aspx?CId=2'
        pages={home:[(a,'Cabinet'),(b,'Audit')],a:[(a+'&page=2','Earlier meetings'),(self.m+'9','9 Oct 2026')],b:[(self.m+'8','8 Oct 2026')]}
        calls=[]
        def fetch(u):calls.append(u);return pages[u]
        found=Reader('moderngov').discover(home,fetch,lambda s:None,[],skip=lambda n:n=='Audit',pagination=False)
        self.assertEqual(found,{self.m+'9':('Cabinet','9 Oct 2026')})
        self.assertEqual(calls,[home,a])
    def test_repairs_papers_saved_without_extension(self):
        folder=Path(self.tmp.name)/'data'/'raw_documents'/'web_downloads';folder.mkdir(parents=True)
        (folder/'abc_Long_title_PDF_2').write_bytes(b'%PDF-1.4 test')
        with self.a.connect() as db:db.execute("INSERT INTO downloads VALUES('https://council.test/x.pdf','data/raw_documents/web_downloads/abc_Long_title_PDF_2','T','Cabinet','1 Sep 2026','')")
        self.a.repair_names()
        self.assertTrue((folder/'abc_Long_title_PDF_2.pdf').is_file())
        self.assertEqual(self.a.unindexed(),['data/raw_documents/web_downloads/abc_Long_title_PDF_2.pdf'])
    def test_committee_details_pages(self):
        # Lambeth-style: list -> mgCommitteeDetails -> "Browse meetings" -> meetings.
        home='https://council.test/mgListCommittees.aspx';det='https://council.test/mgCommitteeDetails.aspx?ID=5'
        lst='https://council.test/ieListMeetings.aspx?CommitteeId=5'
        pages={home:[(det,'Planning Committee')],det:[(lst,'Browse meetings and agendas for this committee'),(det,'Planning Committee')],
               lst:[(self.m+'7','7 Oct 2026'),(det,'Committee details')]}
        calls=[]
        def fetch(u):calls.append(u);return pages[u]
        for quick in (False,True):
            calls.clear()
            found=Reader('moderngov').discover(home,fetch,lambda s:None,[],pagination=not quick)
            self.assertEqual(found,{self.m+'7':('Planning Committee','7 Oct 2026')})
            self.assertEqual(calls,[home,det,lst])
if __name__=='__main__':unittest.main()
