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
        pages={'https://council.test/ieDocHome.aspx?XXR=0&Year=-1':[],home:[(det,'Planning Committee')],det:[(lst,'Browse meetings and agendas for this committee'),(det,'Planning Committee')],
               lst:[(self.m+'7','7 Oct 2026'),(det,'Committee details')]}
        calls=[]
        def fetch(u):calls.append(u);return pages[u]
        for quick in (False,True):
            calls.clear()
            found=Reader('moderngov').discover(home,fetch,lambda s:None,[],pagination=not quick)
            self.assertEqual(found,{self.m+'7':('Planning Committee','7 Oct 2026')})
            everything='https://council.test/ieDocHome.aspx?XXR=0&Year=-1'  # full refresh also opens "All committees"
            self.assertEqual(calls,[home,det,lst] if quick else [home,everything,det,lst])
    def test_folder_meta_for_papers_saved_by_hand(self):
        from archive import folder_meta
        self.assertEqual(folder_meta('data/raw_documents/Audit Committee/2026-03-23/Agenda.pdf'),dict(committee='Audit Committee',meeting='2026-03-23'))
        self.assertEqual(folder_meta('data/raw_documents/Audit Committee/23 Mar 2026 Minutes.pdf'),dict(committee='Audit Committee',meeting='23 Mar 2026 Minutes'))
        self.assertEqual(folder_meta('data/raw_documents/Audit Committee/Minutes.pdf'),dict(committee='Audit Committee'))
        self.assertEqual(folder_meta('data/raw_documents/web_downloads/x.pdf'),{})
        self.assertEqual(folder_meta('data/raw_documents/x.pdf'),{})
    def test_full_refresh_includes_all_committees(self):
        home='https://council.test/ieDocHome.aspx?bcr=1';everything='https://council.test/ieDocHome.aspx?XXR=0&Year=-1'
        old='https://council.test/ieListMeetings.aspx?CId=9&Year=-1';later='https://council.test/ieListMeetings.aspx?Act=later&CId=9&D=2015'
        pages={home:[],everything:[(old,'Old Scrutiny Commission')],old:[(later,'Later meetings')],later:[(self.m+'15','12 Mar 2015')]}
        found=Reader('moderngov').discover(home,pages.__getitem__,lambda s:None,[],pagination=True)
        self.assertEqual(found,{self.m+'15':('Old Scrutiny Commission','12 Mar 2015')})
        calls=[]
        def fetch(u):calls.append(u);return [(self.m+'1','1 Oct 2026')]
        Reader('moderngov').discover(home,fetch,lambda s:None,[],pagination=False)
        self.assertEqual(calls,[home])  # quick checks stay on current committees
    def test_older_years_and_meeting_format(self):
        r=Reader('moderngov')
        self.assertTrue(r.meeting('https://council.test/CeListDocuments.aspx?CommitteeId=134&MeetingId=434&DF=16%2f01%2f2015&Ver=2'))
        html='<select size="1" id="YearSelect" name="YearSelect"><option value="0"> </option><option value="2014">2014</option><option value="2015">2015</option></select>'
        lst='https://council.test/ieListMeetings.aspx?CId=134&Year=0'
        self.assertEqual(r.extra_links(html,lst),[('https://council.test/ieListMeetings.aspx?CId=134&Year=2014','2014'),('https://council.test/ieListMeetings.aspx?CId=134&Year=2015','2015')])
        self.assertEqual(r.extra_links(html,'https://council.test/ieDocHome.aspx?bcr=1'),[])
        # Full refresh follows year pages and skips the overlapping Earlier/Later links.
        home='https://council.test/home';y15='https://council.test/ieListMeetings.aspx?CId=134&Year=2015';older=lst+'&Act=earlier'
        old_meeting='https://council.test/CeListDocuments.aspx?CommitteeId=134&MeetingId=434'
        pages={home:[(lst,'Audit Committee')],lst:[(y15,'2015'),(older,'Earlier meetings')],y15:[(old_meeting,'16 Jan 2015 10.30 am')]}
        calls=[]
        def fetch(u):calls.append(u);return pages.get(u,[])
        found=r.discover(home,fetch,lambda s:None,[],pagination=True)
        self.assertEqual(found,{old_meeting:('Audit Committee','16 Jan 2015 10.30 am')})
        self.assertNotIn(older,calls)
    def test_full_list_of_documents_links(self):
        r=Reader('moderngov')
        self.assertTrue(r.more_documents('https://council.test/mgAi.aspx?ID=46917','View the full list of documents for item 12.'))
        self.assertFalse(r.more_documents('https://council.test/mgAi.aspx?ID=46917','Item 12: Housing delivery'))
        self.assertFalse(Reader('cmis').more_documents('https://council.test/mgAi.aspx?ID=1','View the full list of documents'))
if __name__=='__main__':unittest.main()
