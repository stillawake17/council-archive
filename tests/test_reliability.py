"""Offline checks for refused downloads, the retry list, the database move out of synced folders, and late papers."""
import os,sqlite3,sys,tempfile,unittest
from datetime import date
from pathlib import Path
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import archive
from archive import Archive
from problems import IssueList,items
import late

class Response:
    def __init__(self,status,body=b'%PDF-1.4 test'):
        self.status=status;self.ok=status<400;self._body=b'<title>Azure WAF</title>' if status==499 else body
        if status==499:self.status=403   # 499 in a test script stands for a bot-protection challenge page
    def body(self):return self._body

class Page:
    """Stands in for the browser: answers each address with its queued status codes (last one repeats)."""
    def __init__(self,answers):self.answers={u:list(v) for u,v in answers.items()};self.calls=[];self.request=self
    def get(self,url,timeout=0):
        self.calls.append(url);codes=self.answers[url]
        return Response(codes.pop(0) if len(codes)>1 else codes[0])

def doc(n):return dict(title=f'Paper {n}',committee='Cabinet',meeting='1 Sep 2026',meeting_url='https://council.test/ieListDocuments.aspx?MId=1')

class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.a=Archive(self.tmp.name)
        self.patch=mock.patch.multiple(archive,PAUSE=0,REFUSAL_WAIT=0);self.patch.start()
        self.urls=[f'https://council.test/{n}.pdf' for n in range(6)]
    def tearDown(self):self.patch.stop();self.tmp.cleanup()
    def run_download(self,page,urls):
        failures=IssueList(self.a)
        counts,paths,stopped=self.a.download(page,{u:doc(i) for i,u in enumerate(urls)},False,lambda m:None,failures,lambda i:None,lambda:False)
        return counts,failures
    def test_refused_once_then_served(self):
        page=Page({self.urls[0]:[403,200],self.urls[1]:[200]})
        counts,failures=self.run_download(page,self.urls[:2])
        self.assertEqual((counts['new'],counts['failed'],counts['postponed'],counts['refused']),(2,0,0,False))
        self.assertEqual(page.calls,[self.urls[0],self.urls[0],self.urls[1]])
    def test_stops_asking_when_site_keeps_refusing(self):
        page=Page({u:[403] for u in self.urls})
        counts,failures=self.run_download(page,self.urls)
        self.assertEqual((counts['failed'],counts['postponed'],counts['refused']),(3,3,True))
        self.assertEqual(len(page.calls),6)            # three papers, two attempts each; the rest untouched
        self.assertEqual(len(failures),3)              # postponed papers are not counted as problems
        by={r['url']:r for r in items(self.a)}
        self.assertEqual(by[self.urls[5]]['category'],'Waiting to try again')
        self.assertEqual(by[self.urls[5]]['attempts'],0)
    def test_bot_protection_challenge_is_not_retried_or_attempted(self):
        page=Page({u:[499] for u in self.urls})
        counts,failures=self.run_download(page,self.urls)
        self.assertEqual(len(page.calls),3)            # one request each, no second attempts, then stop asking
        self.assertEqual((counts['failed'],counts['postponed'],counts['refused']),(3,3,True))
        self.assertIn('bot protection',items(self.a)[-1]['reason']+' '.join(r['reason'] for r in items(self.a)))
    def test_retry_list(self):
        m=doc(0)['meeting_url']
        self.a.record_observation(m,'Cabinet','1 Sep 2026',[(u,'Paper') for u in self.urls[:3]],'<html></html>','2026-09-01T10:00:00+00:00')
        failures=IssueList(self.a)
        failures.append(self.urls[0]+': HTTP 403');failures.append(self.urls[1]+': HTTP 404');failures.append(m+': HTTP 403')
        self.assertEqual(list(self.a.retry_queue()),[self.urls[0]])           # not the missing paper or the meeting page
        self.assertEqual(self.a.retry_queue(skip={self.urls[0]}),{})
        for _ in range(archive.RETRY_LIMIT):failures.append(self.urls[0]+': HTTP 403')
        self.assertEqual(self.a.retry_queue(),{})                             # given up after repeated attempts
    def test_retry_list_rests_while_site_refuses(self):
        m=doc(0)['meeting_url']
        self.a.record_observation(m,'Cabinet','1 Sep 2026',[(self.urls[0],'Paper')],'<html></html>','2026-09-01T10:00:00+00:00')
        IssueList(self.a).append(self.urls[0]+': HTTP 403')
        self.a.retry_pause(True);self.assertEqual(self.a.retry_queue(),{})
        self.a.retry_pause(False);self.assertEqual(list(self.a.retry_queue()),[self.urls[0]])

class UncoveredPaperTests(unittest.TestCase):
    """Papers uncovered when the app learned to read full item lists were not newly published."""
    def test_no_window_for_uncovered_papers(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=Archive(tmp);m='https://council.test/ieListDocuments.aspx?MId=1';x='https://council.test/'
            a.record_observation(m,'Cabinet','16 Nov 2026',[(x+'a.pdf','Agenda')],'<html></html>','2026-11-06T12:00:00+00:00')
            # First check able to read item pages: the hidden paper gets no window, the front-page paper does.
            a.record_observation(m,'Cabinet','16 Nov 2026',[(x+'b.pdf','Supplement'),(x+'c.pdf','Appendix, item 7.')],'<html></html>','2026-11-12T12:00:00+00:00',{x+'c.pdf'})
            a.full_lists='2026-11-12T12:00:00+00:00'
            a.record_observation(m,'Cabinet','16 Nov 2026',[(x+'d.pdf','Appendix 2, item 7.')],'<html></html>','2026-11-13T12:00:00+00:00',{x+'d.pdf'})
            by={p['url']:p['previous_check'] for p in a.papers()}
            self.assertEqual(by[x+'b.pdf'],'2026-11-06T12:00:00+00:00');self.assertEqual(by[x+'c.pdf'],'')
            self.assertEqual(by[x+'d.pdf'],'2026-11-12T12:00:00+00:00')
    def test_existing_archive_is_corrected_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=Archive(tmp);m='https://council.test/ieListDocuments.aspx?MId=1';x='https://council.test/'
            a.record_observation(m,'Cabinet','16 Nov 2026',[(x+'a.pdf','Agenda')],'<html></html>','2026-11-06T12:00:00+00:00')
            a.record_observation(m,'Cabinet','16 Nov 2026',[(x+'b.pdf','Supplement'),(x+'c.pdf','Appendix , item 7. PDF 3 KB')],'<html></html>','2026-11-12T05:30:00+00:00')
            (a.work/'reader_changes.json').unlink()              # as left by the version before this one
            b=Archive(tmp);by={p['url']:p['previous_check'] for p in b.papers()}
            self.assertEqual(by[x+'c.pdf'],'');self.assertEqual(by[x+'b.pdf'],'2026-11-06T12:00:00+00:00')
            self.assertIn('c.pdf',(b.work/'reader_changes.jsonl').read_text(encoding='utf-8'))

class WatchWordTests(unittest.TestCase):
    def test_new_papers_are_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=Archive(tmp);m='https://council.test/ieListDocuments.aspx?MId=1';x='https://council.test/'
            a.record_observation(m,'Cabinet','1 Jan 2099',[(x+'a.pdf','Lease report'),(x+'b.pdf','Ashton Court update'),(x+'c.pdf','Minutes')],'<html></html>',archive.now())
            with a.connect() as db:
                db.execute("INSERT INTO docs VALUES(7,'a.pdf','Lease report','Cabinet','1 Jan 2099',?,'',2,'')",(x+'a.pdf',))
                db.executemany('INSERT INTO pages VALUES(7,?,?,?)',[(1,'Lease report','Introduction'),(2,'Lease report','The Ashton  Court mansion lease')])
            d=a.news('7d',watch=['ashton court','"','zebra'])
            by={p['url']:p['watch'] for p in d['papers']}
            self.assertEqual(by[x+'a.pdf'],[dict(term='ashton court',page=2)])       # found inside a saved paper
            self.assertEqual(by[x+'b.pdf'],[dict(term='ashton court',page=0)])       # not downloaded: matched on its title
            self.assertEqual(by[x+'c.pdf'],[]);self.assertEqual(d['mentions'],2)
            self.assertEqual(len(a.news('7d',watch=['ashton court'],watched=True)['papers']),2)
            self.assertNotIn('watch',a.news('7d')['papers'][0])

class RemovedPaperTests(unittest.TestCase):
    def test_removed_and_listed_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=Archive(tmp);m='https://council.test/ieListDocuments.aspx?MId=1';x='https://council.test/'
            A=(x+'documents/s1/a.pdf','Report');B=(x+'documents/s2/b.pdf','Appendix');P=(x+'documents/g9/pack.pdf?T=10','Agenda reports pack')
            t=lambda d:f'2026-10-{d:02d}T12:00:00+00:00'
            a.record_observation(m,'Cabinet','20 Oct 2026',[A,B,P],'<html></html>',t(1));self.assertEqual(a.removed,0)
            a.record_observation(m,'Cabinet','20 Oct 2026',[A,B,P],'<html></html>',t(2))
            a.record_observation(m,'Cabinet','20 Oct 2026',[A],'<html></html>',t(3),complete=False)
            self.assertEqual((a.removed,a.removals()),(0,[]))                      # a page could not be read: prove nothing
            a.record_observation(m,'Cabinet','20 Oct 2026',[A],'<html></html>',t(4));self.assertEqual(a.removed,2)
            a.record_observation(m,'Cabinet','20 Oct 2026',[A],'<html></html>',t(5));self.assertEqual(a.removed,0)   # not reported twice
            rows={r['url']:r for r in a.removals()}
            self.assertEqual((rows[B[0]]['last_listed'],rows[B[0]]['missing_since'],rows[B[0]]['routine']),(t(2),t(4),False))
            self.assertTrue(rows[P[0]]['routine'])
            by={p['url']:p['removed'] for p in a.papers()}
            self.assertEqual((by[A[0]],by[B[0]]),(None,t(4)))
            a.record_observation(m,'Cabinet','20 Oct 2026',[A,B],'<html></html>',t(6))
            rows={r['url']:r for r in a.removals()}
            self.assertEqual((rows[B[0]]['returned'],rows[B[0]]['removed']),(t(6),''))
            self.assertIsNone({p['url']:p['removed'] for p in a.papers()}[B[0]])

class DatabaseLocationTests(unittest.TestCase):
    def test_database_moves_out_of_synced_folder_and_is_backed_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'OneDrive'/'Archive';root.mkdir(parents=True)
            self.assertTrue(archive.synced_folder(root));self.assertFalse(archive.synced_folder(Path(tmp)/'Archive'))
            with mock.patch.object(archive,'synced_folder',lambda p:False):
                a=Archive(root)                                  # as an older version left it: database in the archive folder
            with a.connect() as db:db.execute("INSERT INTO meeting_checks VALUES('https://council.test/m','2026-01-01')")
            inplace=root/'data'/'archive_web'/'search.sqlite3';self.assertTrue(inplace.exists())
            with mock.patch.dict(os.environ,{'COUNCIL_ARCHIVE_LOCAL':str(Path(tmp)/'local')}):
                b=Archive(root)
                self.assertTrue(b.dbpath.is_relative_to(Path(tmp)/'local'));self.assertFalse(inplace.exists())
                self.assertTrue(b.backup_path.exists())          # the old file became the first backup
                with b.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM meeting_checks').fetchone()[0],1)
                with b.connect() as db:db.execute("INSERT INTO meeting_checks VALUES('https://council.test/n','2026-01-02')")
                self.assertFalse(b.backup())                     # too soon after the last copy
                self.assertTrue(b.backup(max_age_hours=0))
                copy=sqlite3.connect(b.backup_path);n=copy.execute('SELECT count(*) FROM meeting_checks').fetchone()[0];copy.close()
                self.assertEqual(n,2)
                b.dbpath.unlink()                                # a new computer: only the synced folder arrives
                for s in ('-wal','-shm'):Path(str(b.dbpath)+s).unlink(missing_ok=True)
                c=Archive(root)
                with c.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM meeting_checks').fetchone()[0],2)
    def test_ordinary_folder_keeps_database_in_place(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=Archive(tmp);self.assertEqual(a.dbpath.parent,a.work);self.assertFalse(a.backup());self.assertEqual(a.storage()['database'],'')

class LateTests(unittest.TestCase):
    def test_bank_holidays(self):
        self.assertEqual(late.easter(2026),date(2026,4,5));self.assertEqual(late.easter(2024),date(2024,3,31))
        self.assertEqual(late.bank_holidays(2026),{date(2026,1,1),date(2026,4,3),date(2026,4,6),date(2026,5,4),date(2026,5,25),date(2026,8,31),date(2026,12,25),date(2026,12,28)})
        self.assertIn(date(2022,1,3),late.bank_holidays(2022));self.assertIn(date(2022,6,2),late.bank_holidays(2022))
        self.assertEqual({d for d in late.bank_holidays(2021) if d.month==12},{date(2021,12,27),date(2021,12,28)})
    def test_deadline(self):
        self.assertEqual(late.deadline('2026-11-16'),'2026-11-06')   # Monday meeting: papers due the Friday of the week before last
        self.assertEqual(late.deadline('2026-04-09'),'2026-03-30')   # Easter: Good Friday and Easter Monday do not count
    def test_assess(self):
        t=lambda d:d+'T12:00:00+00:00'
        self.assertIsNone(late.assess('2026-11-16',t('2026-11-05'),t('2026-11-06')))             # on time
        self.assertEqual(late.assess('2026-11-16',t('2026-11-09'),t('2026-11-12'))[0],'late')
        self.assertEqual(late.assess('2026-11-16',t('2026-11-05'),t('2026-11-10'))[0],'unclear') # deadline fell between checks
        self.assertEqual(late.assess('2026-11-16',t('2026-11-10'),t('2026-11-20'))[0],'unclear') # could be minutes
        self.assertIsNone(late.assess('2026-11-16',t('2026-11-17'),t('2026-11-20')))             # after the meeting
    def test_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=Archive(tmp);m='https://council.test/ieListDocuments.aspx?MId=1'
            a.record_observation(m,'Cabinet','16 Nov 2026 2.00 pm',[('https://council.test/a.pdf','Agenda')],'<html></html>','2026-11-06T12:00:00+00:00')
            a.record_observation(m,'Cabinet','16 Nov 2026 2.00 pm',[('https://council.test/a.pdf','Agenda')],'<html></html>','2026-11-10T12:00:00+00:00')
            a.record_observation(m,'Cabinet','16 Nov 2026 2.00 pm',[('https://council.test/a.pdf','Agenda'),('https://council.test/b.pdf','Late report')],'<html></html>','2026-11-12T12:00:00+00:00')
            r=late.report(a)
            self.assertEqual((r['late'],r['unclear'],len(r['meetings'])),(1,0,1))
            self.assertEqual(r['meetings'][0]['deadline'],'2026-11-06');self.assertEqual(r['meetings'][0]['papers'][0]['title'],'Late report')
            self.assertEqual(late.report(a,committees=['Audit'])['late'],0);self.assertEqual(late.report(a,date_from='2026-12-01')['late'],0)

if __name__=='__main__':unittest.main()
