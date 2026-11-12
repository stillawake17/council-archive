"""The readers against saved examples of each built-in council's real pages (tests/pages).

These run offline. They prove a code change has not broken the reading of any council's page layout.
To find out whether a council has changed its website, run: python tests/council_pages.py check"""
import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from archive import canonical
from readers import PRESETS,Reader,parse_links
from council_pages import MANIFEST,PAGES,classify,counts

MANIFESTS=json.loads(MANIFEST.read_text(encoding='utf-8'))

class CouncilPageTests(unittest.TestCase):
    def pages(self,council):
        return {p['role']:dict(p,html=(PAGES/p['file']).read_text(encoding='utf-8')) for p in council['pages']}
    def test_every_built_in_council_has_saved_pages(self):
        self.assertEqual(set(MANIFESTS),set(PRESETS))
        for key,council in MANIFESTS.items():
            self.assertEqual(council['system'],PRESETS[key]['system'])
            self.assertEqual(canonical(PRESETS[key]['meetings_url']),council['pages'][0]['url'],key)
    def test_links_found_on_each_page(self):
        for key,council in MANIFESTS.items():
            reader=Reader(council['system'])
            for p in self.pages(council).values():
                with self.subTest(council=key,page=p['role']):
                    self.assertEqual(counts(classify(reader,p['base'],p['html'])),p['expect'])
    def test_meeting_pages_are_recognised_and_have_papers(self):
        for key,council in MANIFESTS.items():
            reader=Reader(council['system'])
            for role,p in self.pages(council).items():
                if 'meeting' not in role:continue
                with self.subTest(council=key,page=role):
                    self.assertTrue(reader.meeting(p['url']));self.assertTrue(reader.recognised(p['base'],p['html']))
                    self.assertGreaterEqual(p['expect']['documents'],1)
    def test_normal_check_finds_the_meeting_from_the_home_page(self):
        # The route a normal check takes: home page, committee pages, meeting. No older-years browsing.
        for key,council in MANIFESTS.items():
            reader=Reader(council['system']);saved={p['url']:p for p in self.pages(council).values()}
            def fetch(url):
                p=saved.get(canonical(url))
                return [(canonical(u),t) for u,t in parse_links(p['html'],p['base'])+reader.extra_links(p['html'],p['base'])] if p else []
            with self.subTest(council=key):
                found=reader.discover(council['pages'][0]['url'],fetch,lambda m:None,[],pagination=False)
                meeting=self.pages(council)['meeting']['url']
                self.assertIn(meeting,found);self.assertTrue(found[meeting][0],'committee name missing')
    def test_full_refresh_reaches_older_years(self):
        for key,council in MANIFESTS.items():
            listing=self.pages(council).get('listing')
            if not listing or not listing['expect'].get('years'):continue
            reader=Reader(council['system'])
            with self.subTest(council=key):
                years=reader.extra_links(listing['html'],listing['base'])
                self.assertTrue(all(reader.listing(u) and 'Year=' in u for u,t in years))
    def test_full_document_lists_hold_papers_missing_from_the_meeting_page(self):
        seen=0
        for key,council in MANIFESTS.items():
            pages=self.pages(council)
            if 'item' not in pages:continue
            reader=Reader(council['system']);seen+=1
            front={u for u,t in classify(reader,pages['meeting']['base'],pages['meeting']['html'])['documents']}
            link=classify(reader,pages['meeting']['base'],pages['meeting']['html'])['full_lists'][0][0]
            with self.subTest(council=key):
                self.assertEqual(canonical(link),pages['item']['url'])
                extra={u for u,t in classify(reader,pages['item']['base'],pages['item']['html'])['documents']}-front
                self.assertTrue(extra,'the full list added no papers')
        self.assertGreaterEqual(seen,1)

if __name__=='__main__':unittest.main()
