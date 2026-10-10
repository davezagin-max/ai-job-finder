# AI Job Finder: Quick Start

A job board for new-grad roles around Salt Lake City, focused on data, AI and
fintech jobs. It has two views: a hand-researched board of about 80 AI-forward
employers, and a list of every entry-level opening `refresh.py` found on the
job feeds it reads. Its source list names more than 300 employers. It is one
HTML page plus one data file (`jobs.json`), with no install. The default board
is scored for a fictional sample candidate, Jordan Kim.

**Live:** https://davezagin-max.github.io/ai-job-finder/

## Open it

Open `index.html` in a browser. If the upload button acts up, or the All
openings tab says the openings database could not be loaded, serve the folder
instead:

```bash
python3 -m http.server 8765 --bind 127.0.0.1
```

Then go to http://localhost:8765/index.html

## What you can do

**Browse the board.** Each card is one employer, with a match score, its hiring
status, and links to openings that were checked live. Use the filter chips to
narrow by status, role, location or industry. A card can end with a button such
as "+ 12 more openings on their job feed": those were read by `refresh.py`, not
by hand, and the button opens them in the All openings list.

| Status | Meaning |
| --- | --- |
| 🟢 Live role now | A matching opening is posted today |
| 🟡 Opens later this fall | Expected to post soon |
| 🔵 Watch list | Nothing open yet |
| 🔴 Wrong cohort | Hiring, but not for new grads |

**See every opening.** Click the **All openings** tab. It lists one row per
job: the board's own openings, everything `refresh.py` read from employers' job
feeds, leads from Utah's state job bank, and anything Search deeper found on the
web. It needs no API key. Filter by Where, Level, Field and Source, hide what is
out of reach, and sort by best match, newest, closing date or employer. Until
Claude has ranked the list, "Best match" is a plain keyword match against the
profile on screen.

| Tag | Meaning |
| --- | --- |
| new | Posted, or first seen on the employer's feed, in the seven days before the database was refreshed |
| ~3+ yrs | The posting asks for that many years. The `~` means the number was read automatically from the posting text, so open the posting to confirm. No `~` means it was read by hand |
| level not stated | No level word in the title, so the posting may ask for experience. Kept in Utah only |
| experienced | A senior, lead, architect or numbered-level title in Utah. Left out unless you pick the Experienced chip, type a search, or the profile has two or more years of experience |
| internal applicants only | Open to current employees only. Shown only with the Internal only chip on |
| on the board | The employer has a hand-researched card |
| state job bank lead | Listed by the state job bank (jobs.utah.gov), not read from the employer. Its link asks for a free UtahID sign-in, so use the "find the employer's posting" link beside it |
| found on the web | Saved by Search deeper, in this browser only, and never re-checked by `refresh.py`. "not opened" means Claude saved the link without reading the page |

The other tags (new-grad program, closes, leans SWE, applied, and the degree
bar) mean what they mean on the board. On a row read from a feed the degree bar
reads "wants a technical major" or "wants an MS or PhD".

**Tailor it to a resume.**

1. Click **Upload a resume**.
2. Paste an Anthropic API key (from [console.anthropic.com](https://console.anthropic.com/settings/keys)).
3. Drop in a PDF, `.docx` or `.txt` resume, or paste the text.
4. Click **Tailor, then search deeper**. Two boxes under *How far to look* are
   ticked by default, so the two Search deeper steps (next) run straight after
   the tailoring. Untick both to tailor the board only: the button then reads
   **Tailor the board**.

Claude re-scores every employer for that person and rewrites each card. Tailoring
alone takes a few minutes and costs about $0.30 on the default settings (Claude
Sonnet 5.5, high effort). The result is saved as a profile you can switch to from
the header.

**Search deeper.** The board holds what somebody added and the database holds
what the feeds carry. Search deeper has Claude look past both for the profile on
screen. It needs the same API key and takes two steps, each optional:

1. **Rank the openings.** Claude reads the openings in the database and scores up
   to 80 that are worth this person's time, with one sentence each.
2. **Search the web.** Claude searches employers' own careers sites, starting
   with the employers `refresh.py` cannot read, and saves the postings it finds.
   Pick Quick, Standard or Deep (the default).

To run it, click **Search deeper** on the All openings tab, then **Search
deeper** again in the dialog that opens. Run this way it sends no resume, only a
short brief built from the saved profile. Web search has to be switched on for
your organization in the Anthropic Console.

The cost is shown in the message that appears when a run finishes. Neither step
has been run against the live API, only against a scripted stand-in, so the
figures here are estimates: roughly $0.50 for the ranking and a few dollars for a
Deep search on the default model.

**Track applications.** Click **My applications** to log where you applied, or
import the tracker you already keep: an Excel file, a CSV, or rows pasted
straight out of a spreadsheet. Columns are matched by header name, a Result
column such as "Denied, experience" becomes the status, and a row dated "not
yet" is skipped rather than counted as applied. Cards then show what you applied
for, and the **Applied**, **Live, not applied yet** and **Hide applied** filters
appear.

**See what changed this week.** On the board, an opening added in the six days
up to the latest refresh carries an amber **new** tag. All openings measures
**new** from the feeds instead (see the table above). Each view has a **New this
week** chip that shows only those.

**Skip the roles that are not for you.** Openings on a software-engineering
ladder are tagged *leans SWE*, and openings whose posting demands a
computer-science degree or a master's are tagged with that requirement. The
**Hide weak fits** chip takes both off the board. All openings has a **Weak
fits** chip in its Hide row that does the same, beside **Out of reach** and
**Applied**.

## Keep the jobs current

```bash
python3 refresh.py
```

This reads every employer's job feed, asking each site's robots.txt first. It
rebuilds `jobs.json`, which the All openings tab loads, and writes what changed
to `refresh-report.txt`. A full run takes several minutes. The state job bank
is the slowest part, and you can leave it out:

```bash
python3 refresh.py --skip utahjobs
```

What the database already holds for a feed you leave out is kept as it was.

Reload the page and All openings shows the new `jobs.json`. A link on the board
that the employer no longer recognises is struck out by itself. The cards are
still edited by hand: copy any new openings worth a card into `index.html` with
`added: "<today's date>"` on each, then update `REFRESH_DATE` and the footer date
to that same date. A **new** tag on the board shows while `REFRESH_DATE` is
within six days of the opening's `added` date, so last week's clear themselves.

To ask why a job is or is not listed:

```bash
python3 refresh.py --why "business intelligence analyst"
```

It says whether the database kept the job, dropped it and by which title rule,
published it as experienced or internal-only, saw it leave the feed, or never
saw it at all. Never seen means its employer is not a source yet.

## Your data

- Your API key, saved profiles, application list, rankings and web finds stay in
  your browser.
- Your resume is never saved. It goes to Claude for the run you start and is
  discarded. Search deeper on its own sends a short brief built from the saved
  profile, without the name, and no resume.
- `applications.json` and `refresh-report.txt` are git-ignored. Keep them that
  way, because this repository is public. `jobs.json` is committed on purpose:
  it holds only public job postings.

## Files

| File | What it is |
| --- | --- |
| `index.html` | The whole app |
| `jobs.json` | The openings database the page loads: every live opening the title rules keep. Rebuilt by `refresh.py` and committed |
| `refresh.py` | Reads employers' job feeds, builds `jobs.json` and writes a report |
| `readers/` | One small file per extra hiring system `refresh.py` can read. A file whose name starts with `_` is not loaded |
| `jobs.db` | The full history behind `jobs.json` and `--why` (SQLite). Built by `refresh.py`, git-ignored |
| `guide.html` | Plain-language visual guide |
| `AI-Job-Finder-Guide.pdf` | PDF copy of the guide (rebuild with `./make-guide-pdf.sh`) |
| `samples/` | Fake resumes and mock responses for testing without an API key |

## More detail

- [LOGIC.md](LOGIC.md): the rules behind scores, statuses, tailoring, the refresh,
  the All openings list and Search deeper
- [README.md](README.md): full technical reference
- [guide.html](guide.html): visual walkthrough of how scoring and tailoring work
