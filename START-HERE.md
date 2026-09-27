# Council Archive: Bristol, Birmingham and other councils

A local browser app for downloading council papers, searching inside PDFs and recording when document links appear. The browser interface uses JavaScript and the local server uses Python.

## Finding your way around

The app has four tabs. A bar across the top always shows what is running, with progress and a **Stop** button, or when you last checked and what that check found.

**New papers** (the opening tab) is for keeping up to date. Choose committees (all, or tick several) and which meetings to look at: upcoming and the last 30 days is the default and takes a few minutes. Click **Check now**. The app reads each chosen committee's current page to spot newly listed meetings, then reads those meeting pages, records any paper links it has not seen before, and, if the box is ticked, downloads them into your archive and adds them to search. Below, **Recently found papers** lists what the latest check (or the last 7, 30 or 90 days) found, grouped by meeting. Each paper says whether it is in your archive and when it appeared: "Appeared between A and B" means the link was absent at one check and present at the next. A red number on the tab shows new papers from the latest check that are not yet downloaded. **Automatic checks** can run the default check every few hours while the app is open.

**Committees & meetings** is for working on particular committees or meetings. Pick a committee on the left (or All committees) and a date range. Each meeting shows how many papers are known and saved and when it was last checked. **Check** reads a meeting page for new links without downloading; **Download all** reads it and downloads anything not yet saved; **Show papers** lists the individual papers so you can tick some. Tick several meetings, or none to act on all shown, and use the buttons above the list.

**Search** looks inside papers already in your archive. Filter by one or several committees and by meeting date, and sort by best match or newest meetings.

**Tools** holds occasional tasks: refreshing the full meeting list (all older years), adding PDFs you copied in yourself, OCR for scanned pages, the website connection check, check history, unavailable papers (with **Try these papers again**) and replaced PDFs.

**Selecting several papers.** Tick papers in any tab; the selection stays as you move between tabs and appears in the bar at the bottom. **Download to archive** fetches the ticked papers you do not have yet. **Save as ZIP** saves copies of the ticked papers that are in your archive, named by meeting date, title and committee (up to 500 papers or 2 GB per ZIP; larger selections are split). Changing council clears the selection.

## If you already installed the Bristol version

Let any current OCR run finish before upgrading. Close the launcher, extract this ZIP, and copy the contents of council-archive-web into your existing Council Archive Web application folder beside app.py and Start-Archive.bat. Replace application files and merge the templates folder. Keep your settings, .venv and archive folders. Do not put the new application folder inside the old one. Run Setup-Windows.bat, then Start-Archive.bat and refresh the browser. Your downloaded PDFs, search index and completed OCR results are retained.

Double-click Start-Archive.bat. If the old settings.json is present and no new council configuration exists, the app imports your Bristol folder setting automatically. Otherwise use Add council, choose Bristol and paste the full path to your existing local-authority-tools folder. Select the folder containing data, scrapers and config. Existing PDFs, CSVs, search records and publication observations are retained. Your old scripts remain available and are not modified.

There is no need to download the Bristol archive again. Use Add saved PDFs to search to refresh its search if needed. The new app stores its council settings in councils-local.json next to app.py. Each archive also receives a small council-profile.json marker to prevent attaching it to the wrong council. The website address in the new profile is authoritative; editing the older councils.yaml does not change the new profile.

## Starting from scratch on Windows

1. Extract the ZIP into a normal folder, such as Documents\CouncilArchiveApp.
2. Install Python 3.10 or newer if needed. Double-click Setup-Windows.bat. Setup needs an internet connection and installs dependencies into a separate .venv.
3. Double-click Start-Archive.bat. Leave the launcher window open while using the app.
4. Choose a council in the setup form. Leave Archive folder blank to create its archive automatically under the app's archives folder. An existing toolkit is not required.
5. Click Save council. Open **Tools → Check website** and look at the result and Activity log.
6. For a new archive, open **Tools → Refresh full meeting list** to find meetings from every year. This downloads no papers.
7. Open **Committees & meetings**, choose committees and dates, and click **Download papers**. Or use **New papers → Check now** with the dates you want. Papers are downloaded and added to search automatically.
8. From then on, use **New papers → Check now**, or turn on **Automatic checks**, to keep up to date.

Later, open Start-Archive.bat and select the council from the dropdown. Avoid running two app copies against the same archive. If your PDFs are in OneDrive, make them available locally.

## Adding Birmingham

Click Add council, choose Birmingham City Council and leave the archive folder blank, or supply a new empty folder. Save, check the website, refresh the full meeting list and download from Committees & meetings. Its archive is kept separate from Bristol. The preset uses https://birmingham.cmis.uk.com/birmingham/ and the CMIS reader.

The CMIS reader follows committee categories, committee detail pages, their linked pagination pages and meeting pages. It recognises Document.ashx links, checks the returned content is a PDF, and stores URLs with each download.

## Adding another local authority

Choose Another council and enter its name, a short identifier such as leeds, its website system (ModernGov or CMIS) and the committee homepage URL. Use the council's committee portal rather than its general homepage. Leave the archive folder blank for a new archive, save and run Check website.

The supported readers recognise these families of URL patterns:

- ModernGov: ieListMeetings.aspx committee pages, ieListDocuments.aspx meeting pages, PDF and mgconvert2pdf links.
- CMIS: committee category pages, ViewCMIS_CommitteeDetails, ViewMeetingPublic and Document.ashx links.

A matching system is a starting point, not a guarantee that every council's variant works. Check website checks at most 6 listing pages and 3 meeting pages, with a 15-second timeout per page. It skips Earlier/Later pagination during this sample, reports accessible and refused pages separately with their addresses, and continues after individual failures. It does not download PDFs, change the saved meeting catalogue or preview, or record publication observations. Use Tools → Refresh full meeting list for full discovery. A future meeting may have no documents. Review the log before a full download. Unsupported systems require another reader in readers.py; changing the council name will not make them work.

To correct a profile's URL or folder, close the app and edit its entry in councils-local.json. Do not change a council identifier or point it at another council's archive. A profile-editing screen is not included yet.

## Sharing the tool

Point people to the GitHub page, https://github.com/stillawake17/council-archive, where Code → Download ZIP gives a clean copy with no archive PDFs, personal folder paths or saved settings. Each recipient runs setup and adds their council. Do not zip your working installation, which can contain your own archives, histories and local settings.

Other councils using ModernGov or CMIS can use the same code and create a profile in the form. Have the first user of a new council check a few downloaded papers against the council's website. A complete Windows installer and automatic application updates are not included.

## Searching

Select a council and enter a word or quoted phrase, such as Newton or "Families First". Results show PDF page numbers, extracts and links to local PDFs and council sources. Use the committee filter where metadata is available. This version searches one council at a time.

Search covers PDFs under data/raw_documents and data/raw_constitutions, recursively. For papers you save by hand (for example from a council website that blocks automated tools), put each PDF in data/raw_documents/<committee name>/<meeting date, e.g. 2026-03-23>/ and choose Tools → Add saved PDFs to search; the committee and meeting date are then taken from the folder names, so committee and date filters work. A date at the start of the file name also works in place of the date folder. Add saved PDFs to search scans local files without accessing the council website. Changed and new files are indexed; missing files are removed from search, without deleting their source records.

Quoted phrases match adjacent words. Separate terms must occur on the same PDF page. This is keyword search, not AI question answering. Scanned pages may need OCR; use Check for problems → Make archive searchable after the one-time setup below. Warnings identify unreadable files and pages with no extractable text, but cannot identify every partially scanned page. Printed page numbers may differ from PDF page numbers. Existing metadata is only attached where filename matching is unambiguous.

## Checking publication and replacement dates

Every check (New papers, or Check / Download all in Committees & meetings) records the first time each PDF link appears on each successfully checked meeting page. It preserves the meeting-page HTML, check time and checksum. The first check is a baseline, not a historical publication date. Subsequent new links are shown with the interval between the previous successful check and discovery.

An interval means the link appeared on that monitored page between two checks. The PDF may have existed elsewhere earlier, and a link can appear before its download succeeds. Network failures and unrecognised meeting pages do not establish absence. Review download failures in the Activity log.

To investigate late papers, check shortly before the relevant deadline and again afterwards. An interval spanning the deadline cannot establish which side of it the link appeared. Council-stated publication dates, urgency explanations and applicable rules need separate examination. The app does not calculate legal deadlines or declare breaches. PDF creation dates and server modification dates are not substituted for publication dates.

Checking for replaced PDFs means downloading saved papers again (the recheck option of a check; not yet offered as a button). It compares their SHA-256 hashes with saved copies. Changed copies replace the current local version; the previous copy is preserved under data/archive_web/versions. Tools → Replaced PDFs shows replacement detection times. These are detection times, not exact edit times. This operation transfers more data than an ordinary update. Normal downloads skip existing registered files.

Checks run when you click Check now, or on schedule if Automatic checks are on. The computer must be on and the app open during a check. On-screen observation and replacement lists show at most 500 records; complete histories remain on disk. Keep the computer clock correct and back up these histories.

## Coverage limits

Discovery follows the linked committee pages, up to 2,000 discovery pages, including recognised linked pagination and archive-category pages. A warning appears if the page cap is reached. It does not guarantee every historical year or JavaScript-only pagination path is covered. Previously observed meeting URLs are revisited, as are meeting URLs in data/metadata/COUNCIL_ID_meetings.csv. Finding meetings can be substantial and take time. The full refresh downloads no PDFs.

Committee documents are the supported source. Separate officer-decision registers, procurement portals, constitutions and other council systems are not automatically downloaded. Existing constitution PDFs are searchable. Download selection uses meeting dates. The separate committee filter in the search panel still applies only to search results. Document types other than PDF are reported as failed PDF downloads and not indexed.

The first two presets are Bristol and Birmingham. Other ModernGov and CMIS councils need their own checks. No complete historical Birmingham archive has been downloaded as part of creating this app.

## Files and backups

Each council uses its own root folder. Under that root:

- data/raw_documents/web_downloads: new PDFs, with URL-based identifiers in filenames.
- data/archive_web/search.sqlite3: search, download registry and first-seen observations.
- data/archive_web/page_snapshots and page_checks.jsonl: meeting-page evidence.
- data/archive_web/versions and replacements.jsonl: replaced PDF evidence.
- data/archive_web/activity.log: complete activity and failure log.
- data/archive_web/last_update.json: latest completed update counts.

Do not delete search.sqlite3 as a way to refresh search; it also holds monitoring history. Use Add saved PDFs to search. Snapshots and old versions accumulate. Back up the full archive folder and councils-local.json. Archive folders must be separate and must not be nested inside one another.

## Validation

Birmingham's live site was checked on 25 September 2026: nine committee links were extracted from its overview-and-scrutiny category, ten meeting links from a committee page and eleven document links from a meeting page. A real three-page agenda PDF was downloaded and its text extracted.

Controlled tests exercised the CMIS download pipeline using captured real meeting HTML and sample PDF responses, plus Bristol's discovery pattern, incremental search, phrase matching, duplicate titles, long filenames, publication baselines and intervals, council isolation, unchanged/changed PDF rechecks, preserved old versions, HTTP endpoints and protection of action endpoints.

The complete app has not been tested on your Windows machine or across every Birmingham committee. Check website and your first download are the local integration checks. If something stops, copy the Activity log or launcher error. Do not interpret a failed or partial scan as a complete council archive.

## Manual launch and development

Use Python 3.10 or newer. Install requirements.txt and Playwright Chromium in your environment, then run python app.py. Optional arguments: --no-browser, --port 8766, or --root PATH to attach Bristol on first setup. The server only listens on 127.0.0.1 and is not designed for public hosting.

app.py handles the local service and council registry. readers.py contains website-specific discovery. archive.py handles PDF indexing, monitoring and downloads. templates/index.html contains the browser interface. This separation allows another website reader to be added while reusing the archive and interface.

## Repair for repeated fontTools warnings in the original app

The original setup omitted the optional fontTools dependency used for some PDF fonts. A repeating warning about CFF Type1 fonts is not itself proof that indexing has crashed. A large or complex PDF can also take time, and the original progress message only updated every 20 documents.

If you want to keep using the original app, stop its launcher with Ctrl+C. Copy Repair-PDF-Indexing.bat from this package into your original app folder, beside Start-Archive.bat and the .venv folder, then double-click the repair file. It installs fontTools into that app's own environment. Start the original app again and click Add saved PDFs to search. Completed, unchanged PDFs are skipped; an interrupted PDF is processed again. Do not delete the database or archive.

The updated app includes fontTools in setup and reports the current filename and progress every ten PDF pages. Rerun Setup-Windows.bat if updating an existing environment. A single difficult page can still take time; this patch does not impose an extraction timeout. If it remains on one file, send the filename and latest activity message so that file can be investigated. Previously indexed text is not automatically re-extracted just because fontTools was installed.

## Choosing committees and dates

Dates are meeting dates, not PDF creation or publication dates. Date ranges include both boundary dates. With a date filter, meetings whose date could not be read are left out and their number is reported; with no date filter they are included. Zero matching meetings does not prove there were no meetings.

The meeting list is kept in data/archive_web/meeting_catalog.json. Ordinary checks add newly listed meetings from each committee's current page; **Tools → Refresh full meeting list** also follows Earlier/Later links through older years, up to 2,000 pages, and warns if that limit is reached. Neither guarantees every historical year: dropdown-only or unlinked years and separate officer-decision registers can remain missing.

A check reads meeting pages and records links before downloading, so papers that fail to download are still listed (marked Not downloaded) and appear under Tools → Unavailable papers.

## Repair: UTF-8 error saying surrogates not allowed

This error can happen when PDF extraction returns an invalid Unicode character. The updated indexer replaces invalid characters with a question mark in the search text; the original PDF is untouched.

To repair the original installed app without upgrading its interface, close its launcher. Copy only Repair-Unicode-Indexing.bat and repair_unicode_indexing.py from this package into the original app folder beside Start-Archive.bat and archive.py. Double-click Repair-Unicode-Indexing.bat. It backs up archive.py and patches the text-extraction line. Restart with Start-Archive.bat and click Add saved PDFs to search. Completed unchanged PDFs are skipped; the interrupted document is retried. Do not delete the database or archive. This is separate from the fontTools dependency repair.

## Unavailable papers and Democratic Services queries

Open the **Unavailable papers** tab for the selected council. It lists unresolved document and meeting-page problems, with council links, available titles and meeting details, the type of problem and the last recorded failure. **Copy list** copies the report for a message to Democratic Services; **Save list (.txt)** downloads the same report. Nothing is sent automatically. If clipboard access fails, the app shows selected report text for Ctrl+C.

Access refusals (403), not-found responses (404), removed responses (410), empty responses, non-PDF responses and other failures have separate labels. An empty response or access refusal does not prove a document does not exist. Meeting-page failures can prevent discovery of documents that are therefore not individually listed.

On first use of this feature for an existing archive, it imports failures from the latest update summary in that archive's activity.log. These records are labelled as imported, with current availability unverified; the older log does not reliably identify every subsequent recovery. The source_problems table in search.sqlite3 stores the list. Successful source checks or downloads in this version remove resolved entries. Sources outside a later selected scope remain on the list until successfully checked. Ordinary skips of existing PDFs do not count as a fresh successful source check. Use Refresh list after a job to see current records.

The list is stable while you select text. The activity log also avoids replacing unchanged text and pauses its text replacement while text in it is selected.

To install from the original app: close its launcher, copy the updated package contents into its app folder, keeping your existing settings.json, .venv and archive folders, then run Setup-Windows.bat and Start-Archive.bat. The Bristol archive setting imports automatically if no councils-local.json exists. No new indexing run is required just to view the unavailable list.

## OCR: make scanned pages searchable

Close the app before copying this update into its existing application folder. Keep settings.json, councils-local.json, .venv and your archive folders. Run Setup-Windows.bat again to install pypdfium2 and Pillow, which render pages locally. This does not delete your index.

Install Tesseract OCR with English language data. Tesseract's documentation links to the Windows installer maintained by UB Mannheim:
https://tesseract-ocr.github.io/tessdoc/Installation.html
https://github.com/UB-Mannheim/tesseract/wiki

After installing, restart Start-Archive.bat. The application checks PATH, C:\Program Files\Tesseract-OCR, and common per-user installation folders. For a custom installation set the TESSERACT_CMD environment variable to the full tesseract.exe path before launching. The Windows Tesseract installer is a separate installation; Setup-Windows.bat does not install it. OCR runs locally, with no cloud upload or per-page charge.

Select a council, open **Check for problems → Make archive searchable**, then click **Read scanned pages / retry failures**. Your existing search index supplies the candidate pages, so no complete reindex is required if the archive is already indexed. New PDFs must be indexed before OCR. Each successful page is added to search immediately and saved independently, so stopping and rerunning does not repeat completed unchanged pages. Failed pages are retried on the next OCR run. Pages where OCR found no words are recorded and skipped on later runs unless the source file changes.

Search results on processed pages are labelled **OCR text: verify against the original PDF**. Links continue to open the original PDF. The OCR tab lists up to 500 recent page results, showing exact PDF page numbers and whether text was recognised, no words were found, or processing failed. Its blank-page total includes pages already attempted without recognised words.

The original PDFs are never rewritten. Text and processing records are stored in the ocr_pages table in data/archive_web/search.sqlite3. Ordinary reindexing reuses OCR for an unchanged source, including when metadata changes. A changed source (identified by file size and modification time) must be indexed again and does not inherit the old OCR text. Back up the database with your archive.

The first version targets pages with no extracted text. A page with a text header and an image of a report can be missed. It also does not OCR PDFs that the indexer could not open at all. Blank pages, photographs and maps may yield no useful text. Recognition can misread numbers, tables, handwriting and poor scans, so check quotations and figures against the original. OCR cannot recover information removed by genuine redaction.

Rendering is normally at 300 dpi, reduced on very large pages to limit memory. Recognition has a 90-second timeout per page; the whole worker has a 150-second timeout. These failures are recorded and the job proceeds. Rendering runs in a separate process to isolate problematic PDF pages. Large archives can still take hours. The app runs one job at a time, so finish OCR before downloading or indexing.

Validation used a real image-only test PDF and the local Tesseract engine: recognised words became searchable; a blank page was reported separately; original file bytes were unchanged; completed pages were skipped on a rerun; reindexing kept cached OCR; changing the PDF invalidated its old OCR. The Windows installer and your particular scans still need verification on your machine.


## Interface update validation

Checks covered the opening search view, navigation between the three tasks and review sections, download-scope controls, date-filter requests, automatically refreshed OCR results and counters, and stop-button states using a JavaScript DOM environment. Python checks covered actual Tesseract recognition, stopping after a completed page, resuming, blank-page counts, retained search results, unchanged PDF bytes, inclusive date boundaries, unknown-date exclusion, and stop-endpoint token/council checks. Existing archive search, download and publication-observation regression checks passed. A full visual browser check could not run because the test browser download failed. Windows display and launcher behaviour still need checking on the user's machine.


## Build 2026-09-26b: website check fix

This build includes the redesigned interface and bounded website check. The header shows the build identifier so you can confirm the update loaded. Full discovery now reports listing-page counts, meeting-link counts and page addresses, and preserves committee names across Earlier/Later links. Existing catalogue labels from earlier versions are refreshed on the next Find meetings run. Tests use controlled ModernGov and CMIS pages, including 403 responses and pagination loops; a live council can still refuse access.


## Build 2026-09-26c: saving named PDFs and multiple papers

Open PDF links now use a readable filename and send that filename to the browser. Names use the meeting date, archive title and committee where known, followed by the archive ID to distinguish similarly titled papers. Existing numbered PDF links continue to work and redirect to the named address. Reopen papers from the app to use the updated links; tabs already open may retain the earlier name. Some PDF viewers display an embedded PDF title in the tab, such as Agenda Template, even when the suggested saved filename is descriptive. The PDF itself is not rewritten. Title quality depends on the archive metadata.

Search results now have Select this paper checkboxes and a Save PDF link. Select papers on this page selects the currently displayed results. Selections persist across search pages and searches, and the Selected papers list lets you inspect or remove them. Changing council clears the selection. Download selected as ZIP exports each whole PDF once, even if multiple matching pages were selected. The ZIP contains copies of papers already in your archive; Collect papers continues to download new papers from the council. Select at most 100 papers and 250 MB per ZIP. Missing files produce an error so you can correct the selection. The existing archive files, search index and OCR records are preserved; no reindex is needed for this update.

Validation: HTTP checks confirmed readable Unicode filenames, legacy-link redirects, individual attachments and protected ZIP exports; ZIP contents matched the original source bytes. Tests covered duplicate selections, missing files, size/count limits and path containment. JavaScript DOM checks covered selection across search pages, repeated page matches, save links, ZIP requests and clearing selections on council changes. Windows browser save dialogues still need checking on your machine.


## Build 2026-09-27: new papers, committees and bulk downloads

The three-step Find meetings → Preview → Download process is replaced by single actions: **Check now** on the New papers tab, and **Check** / **Download all** for committees and meetings. The New papers tab lists what each check found and when links appeared, with a count on the tab and in the browser title, and optional automatic checks while the app is open. Committees & meetings lets you browse every known meeting and its papers. Search filters by several committees at once and can sort newest first. Selections work across tabs; the bottom bar downloads missing papers into the archive or saves papers as a ZIP, which the browser now saves directly, so larger ZIPs work. Long jobs can be stopped.

Other fixes: database connections are closed after use (this stopped the export tests failing on Windows), downloaded filenames are shortened when needed to stay within the Windows path limit, and download counts only include files actually written.

Existing archives, search index, OCR results and publication history are kept. A check_runs table is added to search.sqlite3 to record check history. The old download_plan.json is no longer used. The files replaced by this build are kept in backup-before-redesign.

Validation: 13 offline tests (including new ones for meeting selection, new-paper rules and quick discovery) and live checks against a copy of the Bristol archive. A committee check, a single-meeting check that detected newly linked papers, downloading chosen papers, retrying failed papers and ZIP export all worked.
