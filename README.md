# Council Archive

A free Windows tool for council scrutineers. It keeps your own searchable copy of a council's committee papers, tells you when new papers appear, and records when each paper first showed up on the council website.

- **Keep up with new papers.** One click checks every committee for papers added since last time, or it can check automatically every few hours.
- **See when papers appeared.** Each paper records the two checks it appeared between, which helps when reports are published late.
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

1. Install [Python](https://www.python.org/downloads/) 3.10 or newer, ticking "Add Python to PATH".
2. Download this repository: click the green **Code** button above, then **Download ZIP**, and unzip it.
3. Double-click `Setup-Windows.bat` (once only; needs an internet connection).
4. Double-click `Start-Archive.bat`. The app opens in your browser. Keep the launcher window open while you use it.
5. Add your council, then go to **Tools → Refresh full meeting list**.

Full instructions, including OCR for scanned papers and how the publication times work, are in [START-HERE.md](START-HERE.md).

## What the publication times mean

The app records its own checks of each meeting page. "Appeared between A and B" means a paper's link was absent at check A and present at check B. The first check of a meeting is only a baseline, and a failed check proves nothing. The app keeps a copy of every meeting page it reads, but it does not work out legal deadlines or decide whether a rule was broken.

## Running the tests

```
.venv\Scripts\python.exe -m unittest discover -s tests
```

## Licence

MIT. See [LICENSE](LICENSE).
