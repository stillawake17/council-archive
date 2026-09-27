"""Offline regression checks: python -m unittest discover -s tests."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from readers import Reader

class WebsiteCheckTests(unittest.TestCase):
    def exercise(self,system):
        r=Reader(system);home='https://council.test/home'
        def listing(i):return f'https://council.test/ieListMeetings.aspx?CId={i}' if system=='moderngov' else f'https://council.test/Committee/ctl/ViewCMIS_CommitteeDetails/id/{i}'
        def meeting(i):return f'https://council.test/ieListDocuments.aspx?MId={i}' if system=='moderngov' else f'https://council.test/Meeting/ctl/ViewMeetingPublic/id/{i}'
        pages={home:[(listing(i),f'Committee {i}') for i in range(20)]}
        for i in range(20):pages[listing(i)]=[(listing(i)+'&page=2','Earlier meetings'),(meeting(i),'26 September 2026')]
        for i in range(20):pages[meeting(i)]=[('https://council.test/report.pdf','Report')]
        calls=[];logs=[]
        def fetch(url):
            calls.append(url)
            if url==meeting(0):raise RuntimeError('HTTP 403')
            return pages[url]
        result=r.check(home,fetch,logs.append)
        self.assertEqual(len(calls),9)
        self.assertEqual(result,dict(accessible=8,failed=1,meetings_checked=2,document_links=2))
        self.assertFalse(any('page=2' in u or u.endswith('.pdf') for u in calls))
        self.assertTrue(any('Access refused' in line and meeting(0) in line for line in logs))
        self.assertIn('Website check complete',logs[-1])
    def test_moderngov(self):self.exercise('moderngov')
    def test_cmis(self):self.exercise('cmis')
    def test_homepage_refusal(self):
        logs=[];calls=[]
        def fetch(u):calls.append(u);raise RuntimeError('HTTP 403')
        result=Reader('moderngov').check('https://council.test',fetch,logs.append)
        self.assertEqual(len(calls),1);self.assertEqual(result['failed'],1)
        self.assertIn('No meeting links',logs[-2]);self.assertIn('complete',logs[-1])
    def test_empty_meeting_and_timeout(self):
        home='https://council.test';a=home+'/ieListDocuments.aspx?MId=1';b=home+'/ieListDocuments.aspx?MId=2'
        def fetch(u):
            if u==home:return [(a,'First meeting'),(b,'Second meeting')]
            if u==a:raise TimeoutError('Timeout 15000ms')
            return []
        logs=[];result=Reader('moderngov').check(home,fetch,logs.append)
        self.assertEqual(result['meetings_checked'],1);self.assertEqual(result['document_links'],0)
        self.assertTrue(any('not yet published' in x for x in logs))
    def test_pagination_preserves_committee(self):
        home='https://council.test';first=home+'/ieListMeetings.aspx?CId=1';older=first+'&year=2020';meeting=home+'/ieListDocuments.aspx?MId=1'
        pages={home:[(first,'Transport Committee')],first:[(older,'Earlier meetings')],older:[(first,'Later meetings'),(meeting,'26 September 2020')]}
        logs=[];failures=[];found=Reader('moderngov').discover(home,pages.__getitem__,logs.append,failures)
        self.assertEqual(found[meeting][0],'Transport Committee')
        self.assertEqual(len(logs),3);self.assertIn('listing page 3',logs[-1]);self.assertIn('Transport Committee',logs[-1])
if __name__=='__main__':unittest.main()
