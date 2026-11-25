"""Offline checks for officer decision notices, using saved Bristol pages in tests/pages/decisions."""
import json,sys,tempfile,unittest
from datetime import date
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import decisions
from archive import Archive

PAGES=Path(__file__).resolve().parent/'pages'/'decisions'
HOME='https://democracy.bristol.gov.uk/ieDocHome.aspx?bcr=1'
BASE='https://democracy.bristol.gov.uk/'
def page(name):return (PAGES/name).read_text(encoding='utf-8')
def notice_url(n):return BASE+f'ieDecisionDetails.aspx?ID={n}'

class ReadingTests(unittest.TestCase):
    def test_list_url(self):
        u=decisions.list_url(HOME,date(2026,9,1),date(2026,11,26))
        self.assertEqual(u,BASE+'mgListOfficerDecisions.aspx?FULL=1&BAM=0&K=0&DM=0&Next=true&DR=01%2f09%2f2026-26%2f11%2f2026')
    def test_register_list(self):
        html=page('bristol-officer-decisions.html')
        self.assertTrue(decisions.register(html))
        found=decisions.parse_list(html,BASE+'mgListOfficerDecisions.aspx')
        self.assertEqual(len(found),13)
        self.assertEqual(found[0],(notice_url(3530),'Funding for the Trading With Schools cyber incident: data theft response pending longer-term funding approval by the Strategy and Resources Committee on 14 December 2026.','2026-11-24'))
        by={u:(t,d) for u,t,d in found}
        self.assertEqual(by[notice_url(3509)][0],'Responsive Repairs & Void Refurbishment Works – Direct Award 4')
        self.assertEqual(by[notice_url(3408)][1],'2026-08-28')   # the date shown is the date of decision
        self.assertTrue(all(decisions.is_decision(u) for u in by))
        self.assertFalse(decisions.register(page('bristol-decision-3528.html')))
    def test_notice_without_documents(self):
        n=decisions.parse_notice(page('bristol-decision-3528.html'),notice_url(3528))
        self.assertTrue(n['recognised'])
        self.assertEqual(n['title'],'Supply of Topsoil for Bristol City Council Cemeteries')
        self.assertEqual((n['maker'],n['status'],n['key_decision'],n['call_in']),('Director: Management of Place','Recommendations Approved','No','No'))
        self.assertEqual((n['decided'],n['published']),('2026-11-19','2026-11-23'))
        self.assertTrue(n['decision'].startswith('Approval to award a contract to ETM Ltd following a Request to Quote process'))
        self.assertIn('Request to Quote',n['alternatives'])
        self.assertEqual(n['documents'],[]);self.assertEqual(n['other'],{})
    def test_notice_with_a_pdf(self):
        n=decisions.parse_notice(page('bristol-decision-3522.html'),notice_url(3522))
        self.assertEqual(n['maker'],'Director: Legal and Democratic Services (MO & SIRO)')
        self.assertEqual(len(n['documents']),1)
        self.assertTrue(n['documents'][0]['url'].startswith(BASE+'documents/s134356/'))
        self.assertIn('ODN Public Participation and Conduct Procedure',n['documents'][0]['title'])
    def test_key_decision_published_late(self):
        n=decisions.parse_notice(page('bristol-decision-3408.html'),notice_url(3408))
        self.assertEqual(n['key_decision'],'Yes')
        self.assertEqual(decisions.days_between(n['decided'],n['published']),24)
    def test_other_pages_are_not_notices(self):
        self.assertFalse(decisions.parse_notice('<html><p>Page not found</p></html>',notice_url(1))['recognised'])

class RecordingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.a=Archive(self.tmp.name)
        self.found=decisions.parse_list(page('bristol-officer-decisions.html'),BASE)
    def tearDown(self):self.tmp.cleanup()
    def read(self,n,checked):
        return decisions.record_notice(self.a,notice_url(n),decisions.parse_notice(page(f'bristol-decision-{n}.html'),notice_url(n)),page(f'bristol-decision-{n}.html'),checked)
    def test_first_read_is_a_baseline_then_new_notices_get_a_window(self):
        older=[x for x in self.found if x[0]!=notice_url(3528)]
        new,missing=decisions.record_list(self.a,older,'2026-11-20T09:00:00+00:00','2026-08-22','2026-12-20')
        self.assertEqual((len(new),missing),(12,0))
        self.assertEqual(self.read(3522,'2026-11-20T09:01:00+00:00'),'new')
        new,missing=decisions.record_list(self.a,self.found,'2026-11-24T09:00:00+00:00','2026-08-26','2026-12-24')
        self.assertEqual(new,[notice_url(3528)])
        self.assertEqual(self.read(3528,'2026-11-24T09:01:00+00:00'),'new')
        d={r['number']:r for r in decisions.listing(self.a)['decisions']}
        self.assertEqual(d[3522]['previous_check'],'')                              # there at the first read: no window
        self.assertEqual(d[3528]['previous_check'],'2026-11-20T09:00:00+00:00')     # absent on 20 Nov, present on 24 Nov
        self.assertTrue(d[3528]['is_new']);self.assertFalse(d[3528]['lag'])          # published 23 Nov, after the earlier check
        self.assertEqual(d[3528]['gap_days'],4)
        self.assertEqual(self.read(3528,'2026-11-25T09:01:00+00:00'),'same')
    def test_notice_missing_from_a_later_check_after_its_publication_date(self):
        # Published 21 September, but not on the register at a check on 1 October whose range covered that date.
        decisions.record_list(self.a,[],'2026-10-01T09:00:00+00:00','2026-07-01','2026-10-31')
        decisions.record_list(self.a,[x for x in self.found if x[0]==notice_url(3408)],'2026-10-08T09:00:00+00:00','2026-07-08','2026-11-07')
        self.read(3408,'2026-10-08T09:01:00+00:00')
        d=decisions.listing(self.a,slow_only=True,lag_only=True,key_only=True)['decisions']
        self.assertEqual([r['number'] for r in d],[3408])
        self.assertTrue(d[0]['lag']);self.assertEqual(d[0]['gap_days'],24)
    def test_a_check_that_could_not_have_listed_the_notice_is_no_evidence(self):
        decisions.record_list(self.a,[],'2026-10-01T09:00:00+00:00','2026-09-25','2026-10-31')   # range starts after 21 Sep
        decisions.record_list(self.a,[x for x in self.found if x[0]==notice_url(3408)],'2026-10-08T09:00:00+00:00','2026-07-08','2026-11-07')
        self.read(3408,'2026-10-08T09:01:00+00:00')
        self.assertEqual(decisions.listing(self.a)['decisions'][0]['previous_check'],'')
    def test_changes_and_removals(self):
        decisions.record_list(self.a,self.found,'2026-11-24T09:00:00+00:00','2026-08-26','2026-12-24')
        self.read(3528,'2026-11-24T09:01:00+00:00')
        edited=page('bristol-decision-3528.html').replace('Recommendations Approved','Recommendations Withdrawn')
        u=notice_url(3528)
        self.assertEqual(decisions.record_notice(self.a,u,decisions.parse_notice(edited,u),edited,'2026-11-25T09:01:00+00:00'),'changed')
        r=[x for x in decisions.listing(self.a)['decisions'] if x['url']==u][0]
        self.assertEqual((r['status'],r['changes'],r['changed']),('Recommendations Withdrawn','status','2026-11-25T09:01:00+00:00'))
        log=[json.loads(x) for x in (self.a.work/'decision_changes.jsonl').read_text(encoding='utf-8').splitlines()]
        self.assertEqual(log[0]['before']['status'],'Recommendations Approved')
        self.assertEqual(len(list((self.a.work/'decision_pages'/'3528').iterdir())),2)     # both versions kept
        # Gone from a later read whose range covers both its dates; 3408 (decided 28 Aug) is outside this range.
        _,missing=decisions.record_list(self.a,[x for x in self.found if x[0]!=u],'2026-11-26T09:00:00+00:00','2026-09-01','2026-12-26')
        self.assertEqual(missing,1)
        by={x['url']:x for x in decisions.listing(self.a)['decisions']}
        self.assertEqual(by[u]['missing_since'],'2026-11-26T09:00:00+00:00');self.assertEqual(by[notice_url(3408)]['missing_since'],'')
        decisions.record_list(self.a,self.found,'2026-11-27T09:00:00+00:00','2026-09-01','2026-12-27')
        self.assertEqual([x for x in decisions.listing(self.a)['decisions'] if x['url']==u][0]['missing_since'],'')
    def test_search_and_watch_words(self):
        decisions.record_list(self.a,self.found,'2026-11-24T09:00:00+00:00','2026-08-26','2026-12-24')
        for n in (3528,3522,3408):self.read(n,'2026-11-24T09:01:00+00:00')
        self.assertEqual([r['number'] for r in decisions.listing(self.a,query='"ETM Ltd"')['decisions']],[3528])
        self.assertEqual([r['number'] for r in decisions.listing(self.a,query='judicial review')['decisions']],[3522])
        d=decisions.listing(self.a,watch=['VxRail','Temple Quarter'],watched=True)
        self.assertEqual({r['number']:r['watch'] for r in d['decisions']},{3408:['VxRail'],3523:['Temple Quarter']})   # 3523 matched on its listed title
    def test_attached_pdfs_are_queued_until_saved(self):
        decisions.record_list(self.a,self.found,'2026-11-24T09:00:00+00:00','2026-08-26','2026-12-24')
        self.read(3522,'2026-11-24T09:01:00+00:00')
        docs=decisions.attachments(self.a)
        self.assertEqual(len(docs),1)
        m=list(docs.values())[0]
        self.assertEqual((m['committee'],m['meeting']),('Officer decisions','2026-11-18 decision 3522'))

class CheckTests(unittest.TestCase):
    """The whole check against a fake website, as the app runs it."""
    def test_check_reads_register_and_new_notices(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=Archive(tmp)
            site={notice_url(n):page(f'bristol-decision-{n}.html') for n in (3528,3522,3408)}
            calls=[]
            class Page:
                url='';content=lambda s:s.html
            p=Page()
            def links(url):
                calls.append(url);p.url=url
                if 'mgListOfficerDecisions' in url:p.html=page('bristol-officer-decisions.html');return []
                if url in site:p.html=site[url];return []
                raise RuntimeError('HTTP 404')
            class FakeBrowser:
                def __enter__(s):return p,links,lambda u:True
                def __exit__(s,*e):pass
            a.browser=lambda *x,**k:FakeBrowser()
            s=decisions.check(a,lambda m:None,download=False)
            self.assertTrue(s['baseline']);self.assertEqual((s['read'],s['added']),(3,0))
            self.assertIn('DR=',calls[0])
            self.assertEqual(len(calls),14)                     # the register, then all 13 notices; 10 are missing from the fake site
            self.assertEqual(decisions.latest_run(a)['failed'],10)
            calls.clear();s=decisions.check(a,lambda m:None,download=False)
            self.assertFalse(s['baseline'])
            missing={u for u,_,_ in decisions.parse_list(page('bristol-officer-decisions.html'),BASE)}-set(site)
            self.assertTrue(missing<=set(calls))                # notices that could not be read are tried again
            self.assertNotIn(notice_url(3408),calls)            # read, and published more than two weeks ago: not read again
    def test_cmis_councils_are_refused_plainly(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=Archive(tmp,dict(id='b',name='B',system='cmis',meetings_url='https://x.test/'))
            with self.assertRaises(ValueError) as e:decisions.check(a,lambda m:None)
            self.assertEqual(str(e.exception),decisions.NOT_MODERNGOV)
    def test_a_council_without_a_register(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=Archive(tmp)
            class Page:url='';content=lambda s:'<html><h1>Page not found</h1></html>'
            class FakeBrowser:
                def __enter__(s):return Page(),lambda u:[],lambda u:True
                def __exit__(s,*e):pass
            a.browser=lambda *x,**k:FakeBrowser()
            with self.assertRaises(RuntimeError) as e:decisions.check(a,lambda m:None)
            self.assertIn('did not show an officer decisions register',str(e.exception))
            self.assertFalse(decisions.tracked(a))

if __name__=='__main__':unittest.main()
