# Council Archive

A free Windows tool for council scrutineers. It keeps your own searchable copy of a council's committee papers, tells you when new papers appear, and records when each paper first showed up on the council website.

- **Keep up with new papers.** One click checks every committee for papers added since last time, or it can check automatically every few hours.
- **See when papers appeared.** Each paper records the two checks it appeared between, which helps when reports are published late.
- **Watch for what matters to you.** Set watch-words such as a place, a project or "exempt", and new papers that mention them are flagged with a link to the page.
- **Spot late papers.** A Late papers tab lists papers that appeared after the usual deadline of five clear working days before the meeting, with the evidence, and saves the list as a spreadsheet.
- **Notice removed papers.** If a paper disappears from a meeting page, the app records when, and keeps the copy you already saved.
- **Search across years.** Find a word or phrase inside thousands of PDFs, across one committee or several, and open the exact page.
- **Download in bulk.** Save a whole meeting, a committee, or any papers you tick as one ZIP file. A single meeting's ZIP also lists when each paper appeared and includes the text of each paper.

Everything runs on your own computer. Nothing is uploaded and no account is needed. It works with council committee websites that use **ModernGov** or **CMIS**. These councils are built in, so you can pick them from a list:

| Council | System |
|---|---|
| Bristol City Council | ModernGov |
| Sheffield City Council | ModernGov |
| Gloucester City Council | ModernGov |
| Gloucestershire County Council | ModernGov |
| Birmingham City Council | CMIS |
| Lambeth Council | ModernGov |

Other ModernGov and CMIS councils can be added by pasting their committee homepage address. Some council websites block automated tools (the West of England Combined Authority's does); for those, save papers by hand into committee and date folders and the app will still make them searchable. See [START-HERE.md](START-HERE.md).

## Getting started

### The easy way: the installer

1. Go to the [latest release](https://github.com/stillawake17/council-archive/releases/latest) and download `Council-Archive-Setup-….exe`.
2. Run it. Windows may show a blue "Windows protected your PC" box, because the installer is not signed with a paid certificate. Choose **More info**, then **Run anyway**.
3. Open **Council Archive** from the Start menu or the desktop shortcut. The app opens in your browser. Keep its window open while you use it.
4. Add your council, then go to **Tools → Refresh full meeting list**.

The installer needs no administrator rights and includes everything the app needs, except the optional Tesseract program for reading scanned pages. Your papers are kept in `Documents\Council Archive` and are never removed by uninstalling or updating. To update, download and run the newest installer.

### From the source code

1. Install [Python](https://www.python.org/downloads/) 3.10 or newer, ticking "Add Python to PATH".
2. Download this repository: click the green **Code** button above, then **Download ZIP**, and unzip it.
3. Double-click `Setup-Windows.bat` (once only; needs an internet connection).
4. Double-click `Start-Archive.bat`. The app opens in your browser. Keep the launcher window open while you use it.
5. Add your council, then go to **Tools → Refresh full meeting list**.

Full instructions, including OCR for scanned papers and how the publication times work, are in [START-HERE.md](START-HERE.md).

## What the publication times mean

The app records its own checks of each meeting page. "Appeared between A and B" means a paper's link was absent at check A and present at check B. The first check of a meeting is only a baseline, and a failed check proves nothing. The app keeps a copy of every meeting page it reads.

The Late papers tab compares those times with a deadline of five clear working days before each meeting (weekends and England and Wales bank holidays are not counted). "Late" means a check made after the deadline did not find the paper, and a later check before the meeting did. The app does not decide whether a rule was broken: urgent items, reports marked "to follow" and public forum papers can lawfully arrive later, and your council's constitution may set a different rule.

## Reliability

- If a council website starts refusing downloads, the app slows down, stops asking after three refusals in a row, and tries those papers again at later checks.
- If your archive folder is inside OneDrive, Dropbox, Google Drive or iCloud, the search database is kept outside it (in `%LOCALAPPDATA%\CouncilArchive`), because sync tools can corrupt a database that is in use. A backup copy is saved into the archive folder once a day while the app is open, and is restored automatically on a new computer.

## Building the installer

Pushing a tag such as `v1.0.0` (matching the `VERSION` file) makes GitHub build the installer and attach it to a release. The recipes are in `packaging/` and `.github/workflows/release.yml`.

## Running the tests

```
.venv\Scripts\python.exe -m unittest discover -s tests
```

The tests run offline. They include saved examples of each built-in council's pages (`tests/pages`), so a code change cannot quietly break the reading of one council's layout. The examples hold only the links the app uses, with paper names replaced.

Council websites change. To find out whether one has, double-click `Check-Council-Websites.bat`. It reads about 25 pages across the built-in councils and compares them with the saved examples. If a page is reported as changed, the app may be missing meetings or papers for that council.

## Licence

MIT. See [LICENSE](LICENSE).
