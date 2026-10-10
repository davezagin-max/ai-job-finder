# AI Job Finder

A single-page job board for new-grad roles at AI-forward companies, with a
button that re-tailors the entire board to any resume you upload, a second tab
that lists every entry-level opening its refresh script can read, and a search
that has Claude look for the ones it cannot.

The board itself is still hand-researched: about 80 employers, each with a verified
hiring status and, where they exist, links to openings that were confirmed live
on a stated date, with the closing date each posting gives. As shipped it is
curated for new-grad data, AI and fintech roles around Salt Lake City, plus the
structured new-grad programs elsewhere that are worth relocating for. That is the
starting point every uploaded resume gets re-scored against. The tailoring button sends a resume to Claude, which re-scores
every employer for that person, rewrites the reasoning on each card, and for a
candidate outside Salt Lake City adds employers in their own city.

A hand-picked board can only show what somebody thought to add, and tailoring
only re-scores that same list. So the page now looks past it in two ways:

- **All openings**, a second tab, lists every entry-level opening `refresh.py`
  reads from more than 300 employers' own job feeds, one row per job. It needs
  no API key.
- **Search deeper** has Claude rank that whole list for one person, then search
  the web for openings at employers the script cannot read. It needs a key.

No build step, no server, no dependencies to install. It is one HTML file that
also fetches `jobs.json`, the list of openings `refresh.py` publishes.

**Short on time? The one-page [QUICKSTART.md](QUICKSTART.md)** covers setup and
everyday use, and **[LOGIC.md](LOGIC.md)** explains every rule the board and the
refresh script follow, in plain language.

**New here? Read the [visual guide](guide.html)** ([live version](https://davezagin-max.github.io/ai-job-finder/guide.html)),
which explains the board and the tailoring logic in plain language with a diagram.
This README is the technical reference.

A seven-page PDF of that guide is committed as
[AI-Job-Finder-Guide.pdf](AI-Job-Finder-Guide.pdf) for reading offline or
sharing. It is a snapshot, so after changing anything the guide describes,
regenerate it:

```bash
./make-guide-pdf.sh
```

The guide switches to a light print theme on its own, so your browser's own
Save as PDF produces the same document if you would rather not run the script.

## Contents

- [Quick start](#quick-start)
- [All openings](#all-openings)
- [Using the resume upload](#using-the-resume-upload)
- [What a tailoring run changes](#what-a-tailoring-run-changes)
- [Search deeper](#search-deeper)
- [Cost](#cost)
- [Where your data goes](#where-your-data-goes)
- [Tracking your applications](#tracking-your-applications)
- [Keeping the job data fresh](#keeping-the-job-data-fresh)
- [Printing](#printing)
- [How it works](#how-it-works)
- [Editing the board by hand](#editing-the-board-by-hand)
- [Testing](#testing)
- [Deploying](#deploying)
- [Limitations](#limitations)

The default board carries no real person's details. It is scored for a
**fictional sample candidate, Jordan Kim** (a Salt Lake City finance senior with
an information-systems minor; the made-up resume is `samples/sample-resume-jordan-kim.pdf`),
and every card explains the employer rather than any particular person. Upload a
resume and the whole thing rewrites itself around that person, in that person's
browser only; the sample board is always one click away in the profile menu.

## Quick start

Open `index.html` in a browser. That is the whole install for the board.

Some browsers restrict `file://` pages. The upload button needs to load a
library from a CDN, and the All openings tab needs to fetch `jobs.json`, which a
page opened straight from disk is often not allowed to do. When that fetch is
blocked the tab still works, shows only the board's own openings, and says why.
Serve the folder to get everything:

```bash
python3 -m http.server 8765 --bind 127.0.0.1
```

Then open http://localhost:8765/index.html

Keep the `--bind 127.0.0.1`. Without it Python serves the folder to every device on
your network, and if you track applications (below) that includes your
`applications.json` and `refresh-report.txt`.

## All openings

Two tabs sit above the filters. **Employers** is the board, one card per
employer. **All openings** is one row per job, and it needs no API key.

It is one list, built from three places:

- `jobs.json`, every opening `refresh.py` kept from the job feeds it reads
  (see [Keeping the job data fresh](#keeping-the-job-data-fresh));
- the board's own hand-read openings. Where the same posting is in both, it is
  listed once and the hand-read years, degree bar and closing date win, because
  a person read those off the posting;
- anything Claude found on the web for the profile on screen
  (see [Search deeper](#search-deeper)).

Without a key the rows are ordered by a plain keyword match: words from the
profile on screen against each title, adjusted for place, level, field and the
years the posting asks for. Once Claude has ranked the list, a ranked row shows
its score and one sentence of reasoning, and ranked rows sort above unranked
ones.

| Filter row | What it offers |
| --- | --- |
| Show | New this week; Closing soon (the posting's own closing date is within 14 days); Internal only; and a chip naming the employer when you arrived from its card |
| Where | Utah, Remote, Elsewhere |
| Level | New-grad programs, Entry-level titles, No level stated, Experienced |
| Field | Data & analytics, Software & IT, Security, Risk, audit & compliance, Finance, Product & projects, Business & operations, Engineering, Research & lab, Other |
| Source | On the board, Feeds only, State job bank, Found on the web |
| Hide | Out of reach (the posting asks for two or more years beyond what this person has), Weak fits, Applied |
| Sort | Best match, Newest, Closing soonest, Employer A–Z, and a Reset button |

The search box searches title, employer, place and field. A chip with nothing
behind it is hidden: Found on the web, for example, appears only once a search
has saved something. The list shows 60 rows at a time.

**Two kinds of posting are real but left out of the list unless you ask.** A
posting open only to the employer's current staff appears only with the
**Internal only** chip on. An **Experienced** title (senior, lead, architect, a
numbered level above one) appears with that Level chip on, when you type in the
search box, or when the profile on screen has two or more years of experience.
Neither is an entry-level opening, so neither belongs in the default list, but
both are published so that a real posting never looks as if the page missed it.

**New this week** in this list means posted, or first seen on its employer's
feed, in the seven days before the database was refreshed. It is measured from
the refresh date in `jobs.json`, not from today's clock, so a copy that has not
been refreshed for a month does not go on calling the same jobs new.

**Read the tags before you trust a row.** Every row was read by a program, not
by a person, unless it is one of the board's own openings. Three tags say how
far to trust it (the full list is under [Opening tags](#opening-tags)):

- **~3+ yrs**: the tilde means a program read the number out of the posting
  text. Open the posting to confirm. A number with no tilde was read by hand.
- **state job bank lead**: a lead, not a posting. Its link opens Utah's job
  bank, which asks for a free UtahID sign-in, so the row also has a **find the
  employer's posting** link that runs a web search for the title and employer.
- **found on the web**: saved by Search deeper for this profile, in this
  browser. `refresh.py` never re-checks it.

The two tabs are linked. A card on the Employers tab whose employer's feed lists
more than the hand-read openings ends with a button such as "+ 12 more openings
on their job feed · 3 new", which opens All openings on that employer alone.

## Using the resume upload

1. Click **Upload a resume**.
2. Paste an Anthropic API key. Create one at
   [console.anthropic.com](https://console.anthropic.com/settings/keys).
3. Choose a model and a thinking effort, or keep the defaults.
4. Drop in a PDF, a Word file or a text file, or paste the resume text.
5. Under **How far to look**, decide whether the run should carry on after the
   tailoring: rank every opening in the database for this person, and search
   the web for openings the database does not have. Both are ticked by default
   and the search depth starts at Deep, which is the slowest and most
   expensive setting, so untick them when you only want the board tailored.
   The dialog remembers what you last chose. They are the two steps of
   [Search deeper](#search-deeper).
6. Click the run button. It reads **Tailor the board** with both steps unticked
   and **Tailor, then search deeper** otherwise.

Tailoring alone takes a few minutes on the default settings (Claude Sonnet 5.5
at high effort). The two extra steps add to that, and the dialog itself warns
that a Deep web search can run ten minutes or more. Claude's reasoning streams
into the panel while it works, a timer shows the elapsed time, and a Stop button
cancels at any time. Each step saves its own work as it finishes, so a Stop or a
failure part-way loses only the step that was running.

When it finishes, the board is rewritten for that person and saved as a profile.
A dropdown appears in the header to switch between saved profiles and the
original board. Profiles live in your browser only.

**Accepted resume formats:** PDF, `.docx`, `.txt`, `.md`, or pasted text. Old
`.doc` files are not supported; save them as PDF first. PDFs go to Claude as
native documents, so layout and columns are read correctly.

## What a tailoring run changes

| Part of the page | What happens |
| --- | --- |
| Header | Name, initials, status, most recent role, stack and target are rewritten from the resume |
| Positioning line | Two or three sentences on how to present this candidate |
| Every company card | New match score, tier, badges, and a rewritten explanation tied to the person's real experience |
| Timing notes | Rewritten wherever the original referenced the sample audience's graduation window |
| Where filters | Relabeled to the candidate's metro; the "Needs relocation" filter, which the default board also shows, then means a move from that metro |
| Suggested employers | Up to fifteen in the candidate's own metro and field (the page keeps at most twenty), whenever the board's geography or its subject matter does not fit them |
| Footer | Which live roles to apply to first, and what to watch for later in the season |
| Career fair strip | Hidden by default; appears only for a University of Utah student |
| All openings tab | Re-ordered for the new profile: by a keyword match against its skills, target and most recent role, or by Claude's scores when the ranking step ran. Experienced titles join the list for a profile with two or more years |

### About the suggested employers

They appear whenever this board is the wrong board for the person: they live
somewhere else, or they work in a field it does not cover. Since nearly every
employer on the board hires data, analytics or software people, a candidate in another
profession gets suggestions even if they live in Salt Lake City, and those
suggestions lead the page while the board drops below them.

These come from Claude's own knowledge, not from the researched board. They are
drawn as dashed purple cards under a heading that names the city, each labeled
**not verified**, and their button runs a web search for that company's careers
page rather than linking to a job posting that may not exist.

Treat them as leads to check, not as confirmed openings. Everything on the
original board was verified by hand on the date shown in the footer.

### Candidates already in Utah

If the resume shows a home base anywhere on the Wasatch Front, or says the
person is moving to Salt Lake City, the board stays in local mode: the location
filters keep their original meaning. Suggested employers are added only when the
person's field is outside what the board covers (a nurse or a mechanical engineer
in Salt Lake City still gets them). This is deliberate: for a local data or
software candidate the researched board is already the right answer. Local mode
itself is decided by the employers' location types coming back unchanged, not by
the city string.

The career fair strip and the alumni filter are gated on the school rather than
the city, so they never appear on the default board and show up only when a
resume identifies a University of Utah student.

## Search deeper

Search deeper has Claude rank every listed opening for one person, then search
the web for openings the database does not have. It needs an Anthropic API key.
It exists because tailoring re-scores a fixed list of employers, so on its own
it can never show a job at an employer nobody added.

There are two ways in:

- **The Search deeper button** on the All openings tab. It opens the upload
  dialog in its second mode, which you can also choose there yourself. On the
  sample board that option reads "Search deeper for the sample candidate (no
  resume needed)"; on a tailored board it names the profile instead. That mode
  works from the profile on screen, or from the fictional sample candidate when
  no profile has been tailored, and it sends no resume. Its run button reads
  **Search deeper**, and at least one of the two steps has to be ticked.
- **A tailoring run.** In the dialog's first mode the same two steps sit under
  How far to look. They run straight after the tailoring, in one go. The
  resume is sent with the tailoring and the ranking; the web search never
  receives it and works from the brief of the profile just made.

Each step is optional. The model and effort are the ones chosen in the dialog:
the same three models as tailoring, Sonnet 5.5 at high effort by default.

### Step 1: rank the openings

**What it sends.** One request holding the brief (see
[Where your data goes](#where-your-data-goes)), today's date, and one line per
listed opening: title, employer, place, level, the years and degree bar where
they are known, whether it is a software-engineering ladder, and the closing
date. Closed postings, internal-only postings, web finds and experienced titles
two or more years out of reach are not sent. Up to 2,500 openings go; when there
are more, the 2,500 that do best on the keyword match are the ones sent.

**What comes back.** Up to 80 openings worth this person's time, each with a
score and one sentence. The reply is treated as untrusted, like everything else
Claude returns: an id must be one the page sent, a job counts once, at most 120
are kept, scores are clamped to 60-100 and the sentence is capped at 300
characters. The seniority ceiling the board applies to an employer applies to a
single job too: a posting two years beyond the candidate tops out at 80, and
three or more at 70.

**What it saves, and where.** The scores and sentences, in this browser's
`localStorage` under `jf.jobRank`, per profile. A ranking is a snapshot: an
opening that arrives in a later refresh stays unranked until you run the step
again.

### Step 2: search the web

**What it sends.** The brief, today's date, the names of the employers whose
feeds are already in the database (so the budget is not spent on them), and two
lists the database supplies as starting points:

- the employers `refresh.py` knows about and cannot read (the `unread` list in
  `jobs.json`). Those with no feed are given with their careers pages to open.
  Those whose sites turn automated readers away are given by name only, with
  the instruction to search for their postings, because a page read there
  would be refused and wasted;
- up to forty state job bank leads that suit this person, as title, employer
  and place. The real posting behind a lead is exactly what is worth finding.

Claude is given three tools: Anthropic's web search, Anthropic's page reader,
and one tool of the page's own, `save_jobs`. The searching and the page reading
run on Anthropic's servers. The page itself never contacts a careers site.

**What is rejected.** `save_jobs` trusts nothing it is handed. A job is saved
only when all of these hold:

- it has a title and an employer;
- its link is a full http(s) link;
- the link is not on a listing site. LinkedIn, Indeed, Glassdoor, ZipRecruiter
  and about thirty similar hosts are turned away, because they repackage other
  employers' postings; Claude is told to use them as leads and save the
  employer's own link;
- the link appeared in this session's search results or page reads. That is the
  difference between a posting found and a posting recalled. What Claude itself
  typed into a search, or asked to open, does not count; neither does a page
  read that failed or was refused; and reading a careers listing does not vouch
  for every link under it, only for that page (and its own `/apply` or
  `/details` step);
- the board does not already have the job. A state job bank lead does not count
  as already having it, and the saved posting replaces the lead in the list.

Each reply tells Claude which jobs were saved, which were already known and
which were rejected and why, so it can steer. Text on a web page is treated as
information about jobs, never as instructions: the prompt says so, and whatever
Claude then tries to save still has to pass the rules above.

**What it saves, and where.** Each find goes into the browser's own database
(IndexedDB, database `jobfinder`), one record per profile and posting: title,
employer, place, link, Claude's score and one-sentence reason, a sentence of
evidence from the page, the years and degree bar where the posting stated them,
its posted and closing dates where given, the day it was found and the model.
In a private window with no IndexedDB the finds last for that page view only.
Finds are saved as the run goes, so a Stop keeps what was already found.

In All openings a find is tagged **found on the web**, and **not opened** is
added when Claude saved a link it had seen in search results but no page read
of it is on record. The run ends with Claude's short summary of where it
looked. The page keeps that summary in `localStorage` under `jf.searchNotes`
but does not display it yet; the completion toast gives the counts.

### Depth and cost

| Depth | Budget for the whole session |
| --- | --- |
| Quick | about 12 searches and 16 page reads |
| Standard | about 30 searches and 40 page reads |
| Deep (the default) | about 60 searches and 80 page reads |

The run stops when the leads or the budget run out. Once it is a quarter over
either number Claude is told to save what it has verified and write its
summary, and the page ends the run if it carries on. There is also a limit of
40 round trips.

Anthropic bills each web search at $0.01 on top of tokens, and every page read
is input tokens, capped at 6,000 tokens a read. Rough figures are under
[Cost](#cost).

**None of this has been run against the live API here.** The ranking and the
search were tested with `samples/jobs-harness.js`, which replays a scripted
stand-in for the API. That covers the request shapes, the save rules and the
loop. It says nothing about what Claude actually finds, how long a run takes or
what it costs, so every cost figure for these two steps is an estimate and the
completion toast is the real number.

Web search has to be switched on for your organization in the Anthropic
Console. When the API rejects a request for that reason the page says so, and
you can untick the web step to run the ranking alone.

## Cost

Each run bills the API key you paste. Rough cost of tailoring the board:

| Model and effort | Typical cost | Basis |
| --- | --- | --- |
| Sonnet 5.5, high (default) | about $0.30 | Measured on this board: 19,000 output tokens, 7,900 of them thinking |
| Sonnet 5.5, medium or low | less | Fewer thinking tokens; normally enough for this board |
| Opus 5.5, high | roughly $0.60 to $1.20 | Estimate: twice Sonnet 5.5's price per token, and it thinks longer |
| Fable 5.1 | $1.50 and up | Estimate: five times Sonnet 5.5's price per token, and the slowest |

Only the first row is measured, so trust the completion toast over this table:
it reports what the run you just made actually cost, priced at the model that
served it.

The two [Search deeper](#search-deeper) steps are billed on top of that. Rough
cost of each on Sonnet 5.5 at high effort:

| Step | Rough cost | Basis |
| --- | --- | --- |
| Rank the openings | about $0.50 | Estimate, not measured: up to 2,500 one-line openings in, up to 80 scored openings out, plus thinking |
| Search the web, Deep (default) | a few dollars | Estimate, not measured: about 60 searches at $0.01 each, and about 80 page reads of up to 6,000 input tokens each, which stay in the conversation for the rest of the run |
| Search the web, Quick or Standard | less | Estimate, not measured: about 12 or 30 searches, and 16 or 40 page reads |

No row of this second table is measured. Those steps were tested against a
scripted stand-in for the API, which bills nothing, so no real run stands behind
the numbers. Opus 5.5 and Fable 5.1 cost twice and five times as much per token,
as they do for tailoring. The completion toast adds up every step of the run,
tokens and search fees together, from what the API reports, so it is the number
to trust.

Effort matters as much as the model. Thinking is billed as output, so much of
the cost of a high-effort run is reasoning rather than the answer. Opus 5.5 at
medium effort is close to its high-effort quality for this task and noticeably
cheaper.

The model is asked for one score and one boolean per employer. Tiers and badges
are derived in the page from those scores and the board's own data, which removes
the most expensive per-company deliberation and makes the results reproducible.

The board data is sent with a cache marker, so repeated runs in the same session
cost noticeably less on input tokens. The list of openings sent for ranking
carries one too. The completion toast reports the actual cost of the run you
just made.

## Where your data goes

- The API key is stored in your browser's `localStorage` and sent only to
  `api.anthropic.com`. There is no server in this project to send it to.
- **The resume is never stored.** It is read in the browser, included in the
  tailoring request, and in the ranking request when that step is ticked in the
  same run, and discarded. The web search never receives it: a resume holds a
  name, a phone number and an address, and the search step writes search
  queries and reads pages off the open web. Only Claude's responses are saved.
- **Search deeper on its own sends no resume.** It sends a short brief built
  from the saved profile: status, most recent role, skills, target, years of
  full-time experience, home city and the positioning line. The profile's name
  is not put in the brief, on purpose, so that it does not end up in a search
  query. The positioning line was written by Claude when the board was
  tailored and may use the name, so the page replaces each word of the name
  there with "the candidate" before the brief is sent. On the sample board the
  brief describes the fictional sample candidate.
- The web search step also passes the profile's home city to Anthropic's search
  tool as an approximate location, so that results are local.
- **Web searches and page reads are run by Anthropic's own tools**, on
  Anthropic's servers. The page itself sends your data only to
  `api.anthropic.com`. It does not contact a careers site until you click a
  posting's link.
- **Claude's ranking is kept in `localStorage`, and web finds in IndexedDB**,
  both per profile and both in that one browser only.
- Saved profiles stay in `localStorage` on that one browser. They are not synced
  and never leave the machine.
- `jobs.json` is public data about job postings. It is fetched from wherever
  the page is served and holds nothing about any reader.
- Clearing site data removes the key, every saved profile, every ranking and
  every web find. Removing one saved profile from the menu removes that
  profile's ranking, its search summary and its web finds with it, and the page
  asks first. Tailoring the same person again replaces the profile and keeps
  its ranking and web finds.

Because the key sits in the browser, treat any machine where you paste it as
trusted. If you publish this page for other people, each person uses their own
key and pays for their own runs.

## Tracking your applications

The **My applications** button keeps a list of where you have applied: company,
role, date and status (pending, interview, offer, rejected, withdrawn). It lives
in your browser's `localStorage` and nowhere else. It is never written into the
page, so a published copy of this board carries no one's job search.

Once you have entries, the board uses them:

- A card for an employer you applied to shows what you applied for and its status.
- The specific opening you applied to is tagged **applied** with the date. When an
  employer posts the same title in two cities (Visa's APM in Foster City and
  Austin), the location you recorded decides which one.
- Company names are matched loosely enough for how people write them: legal
  suffixes are ignored ("KPMG LLP", "Wells Fargo Bank, N.A."), and common other
  names count ("Ernst & Young" for EY, "Citibank" for Citi, "Amex"), while a
  different company with a similar name does not ("Fidelity National Financial"
  is not Fidelity Investments).
- A **Mine** filter shows only employers you applied to, or only employers with a
  live role you have not applied to yet.
- On the All openings tab a row you applied to carries the same **applied** tag,
  and the **Applied** chip in its Hide row takes those rows out of the list.
- The dialog lists every application at an employer this board does not cover.
  Those are the most useful signal for what to add next: a job you found that
  the board could not show means the next one like it will be missed too.

**Import a file** reads the tracker you already keep, not just this board's own
format: an Excel `.xlsx`, a CSV or TSV, a JSON export, or rows pasted straight
out of a spreadsheet. Columns are matched by header name in any order &mdash;
`Company` and `Job` (or `Title`) are required, and `Date`, `Location` and
`Result` are used when present:

```
Date,Company,Job,Experience,Result,Location
13-Sep,Example Bank,Data Analyst I,entry level,"Denied, experience","Salt Lake City, UT"
not yet,Example Bank,Banker Development Program,entry level,,
```

A `Result` of "Denied, experience" becomes a rejected status with that text kept
as the note; "HireVue" or "interview" becomes interview. `13-Sep` with no year
means the most recent September 13 that has passed, and an Excel date column
works as it is. The second row above is skipped rather than counted as applied,
because its date says it has not been sent yet. Importing the same sheet twice
changes nothing.

**Export JSON** moves the list between browsers. When the page is served from
your own machine (`localhost`), it also loads an `applications.json` sitting next
to `index.html`. `refresh.py` reads the same list for its audit, and takes the
spreadsheet directly: name it `applications.csv`, `applications.tsv` or
`applications.xlsx` and drop it beside the script. Every one of those names is in
`.gitignore` and must stay there, because this repository is public. The format:

```json
[
  { "company": "Example Bank", "title": "Data Analyst I",
    "location": "Salt Lake City, UT", "applied": "2026-09-01",
    "status": "pending", "note": "Recruiter screen booked" }
]
```

## Keeping the job data fresh

`refresh.py` reads about 360 job feeds, records every row they return in a
database, publishes the slice of it the page lists, re-checks the links on the
board, and reports what changed.

```bash
python3 refresh.py                      # everything
python3 refresh.py --skip utahjobs      # leave one kind of feed out (here, the state job bank)
python3 refresh.py --only greenhouse    # read only that kind of feed
python3 refresh.py --why "business intelligence analyst"   # what the database knows about a job; no network
python3 refresh.py --selftest           # the rules, checked against made-up titles; no network
```

A full run takes several minutes. On 2026-10-09, with about 360 feeds, one
took a little over seven. Timed earlier with about 300 feeds it took about
six, about four of them the state job bank, and about two and a half with
`--skip utahjobs`. It took about a minute when the script read only the
board's own employers. It uses only the Python standard library and shells out
to `curl`.

A run writes four files. `jobs.json` is the one the page reads and the one to
commit. `jobs.db`, `refresh-report.txt` and `.refresh-state.json` are
git-ignored.

### The three source lists

| List | What is in it | What the page shows |
| --- | --- | --- |
| `BOARDS`, at the top of `refresh.py` | The employers that have a hand-written card: about 100 feeds, because some employers need two (Mastercard's campus site and its Salt Lake City search, for one) | Rows tagged **on the board**, and the "more openings" button on the employer's card |
| `MORE`, just below it | Employers read for the database only: about 180 feeds, mostly Utah employers and the Utah offices of national ones | No card, but every entry-level role they post is a row in All openings |
| `readers/` | One small plug-in file per further hiring system, each naming its own employers: 28 files and about 90 feeds today, not counting two parked files whose names start with an underscore | The same as `MORE` |

The hiring systems built into `refresh.py` are Greenhouse, Lever, Ashby,
Workable, Workday (about 135 of the feeds, including employers on the shared
`myworkdaysite.com` host, such as Fidelity and Wells Fargo), BambooHR, Oracle
Recruiting Cloud (JPMorgan, American Express), Avature (Bloomberg), iCIMS
sitemaps (kept for a portal whose search page cannot be read), SuccessFactors
feeds (Vivint), JazzHR (Cicero), Taleo behind SelectMinds (Zions), Eightfold
and Oleeo (Morgan Stanley), ADP WorkforceNow (Sunwest Bank), the GraphQL
service behind Goldman's campus site, and the search service behind the
University of Utah's careers site. The University is the largest employer in
Salt Lake City, with about 1,300 postings, and was not a source at all until
October 2026.

The files in `readers/` add ADP Recruiting Management, Amazon, ApplicantPro,
Avature sites of the Siemens layout, Breezy, Comeet, Kula, Cornerstone (the
State of Utah), Dayforce, an older Eightfold API
(Liberty Mutual), HireHive, two kinds of iCIMS site, Jobvite, the Larry H.
Miller careers page, Paylocity, Phenom, Pinpoint, Radancy, Rippling,
Sportsman's Warehouse, a second SuccessFactors layout (Nucor, HF Sinclair,
Union Pacific), Teamtailor (Autoliv), USAJOBS, Utah's state job bank, and one
each for Deloitte, EY and KPMG, whose own search pages are read directly.
Eleven of these (Cornerstone, Deloitte, EY, KPMG, Teamtailor, Comeet,
Kula, the Larry H. Miller page, Sportsman's Warehouse, the older Eightfold
API and the second SuccessFactors layout) were written and run against the
live sites but did not get the independent review the others had, so read
their rows with that in mind. iCIMS portals such as
Cotiviti's and America First's are now read from the portal's search page,
which names each job's place where the sitemap does not.

**To add a source**, start with `python3 refresh.py --why "job title"` for a
job you expected to see. It says whether a rule dropped the job or no feed ever
returned it, and the second answer means the employer is not a source. Then:

- **If the employer uses a hiring system the script already reads**, add one
  line to `MORE` (or to `BOARDS` if it has a card), in the form the other
  entries of that kind use: `"Employer": "slug"`. The comments in `BOARDS` and
  in `fetch()` explain the slug for each kind that needs explaining.
- **If it is a new hiring system**, drop a file into `readers/`. It is read on
  the next run and nothing else has to be registered. The file needs `KIND`,
  `EMPLOYERS = {"Name": "slug"}` and `fetch(slug)`, which returns one
  `(title, location, url, closes, degree, extra)` row per job, where `extra`
  carries `posted`, `yrs`, `internal` and `company`. It may add
  `link_state(url)` to answer for its own links, `INSTITUTIONS` (or
  `INSTITUTION = True` for every employer in the file) and `ASSUMED_PLACE`,
  both explained below, and `AGGREGATOR = True` when one slug returns many
  employers' jobs, with `LEADS = True` as well when its rows link to the
  relisting site and not to the employer. A file whose name starts with an
  underscore is not loaded. Fetch through `refresh.curl()`,
  `refresh.curl_text()` or `refresh.curl_resp()`, as the existing readers do,
  so that the robots.txt rule applies to your reader too. Each reader also
  runs on its own for a quick look at what it returns, for example
  `python3 readers/rippling.py`.

### It asks first: robots.txt

Every host is asked once a run for its robots.txt, and a path closed to all
crawlers is not read. The source is then reported as not read, with the reason.
Only the rules addressed to every crawler are read, the longest matching rule
wins, Allow wins a tie, and a stated crawl delay is kept, up to 15 seconds
between requests. A host whose robots.txt cannot be fetched at all is treated
as closed for that run; a host that has none has nothing closed. The reason is
simple: a site that asks scripts to stay out of a path has said no, even where
a browser would be served.

This rule has costs, and they are deliberate:

- **The University of Utah is read the slow way.** Its site has a bulk feed
  that would take three requests, and its robots.txt asks scripts not to fetch
  it. So the script uses the search service the site's own pages call, about
  ninety small requests.
- **Whole hiring systems are ruled out.** NEOGOV (governmentjobs.com and
  schooljobs.com), PeopleAdmin, UKG, Paycom, Paycor and Getro all close their
  job lists to scripts, so employers on them are not read at all.
- **The link checks obey it too.** A board link on a closed path is reported as
  unknown, never as dead.

`DOCUMENTED_APIS` is the one exemption list, and it ships empty. It is for an
API whose vendor documents it as public for this use while the robots.txt on
the API's host turns every crawler away. SmartRecruiters is the case in point,
and a finished reader for it is parked as `readers/_smartrecruiters.py`, where
the underscore keeps it from loading. To use it, add the host to
`DOCUMENTED_APIS` and drop the underscore. That is your call to make, not the
script's default.

### Employers it cannot read

`MANUAL` lists about 40 employers the script knows about and does not read,
each with its careers page, and `MANUAL_WHY` says why: the hiring system's
robots.txt asks scripts to stay out, the careers site answers scripts with a
bot check or an access-denied page, or there is no feed at all. One of them
is on the board: Datafy, which lists openings on its own site and takes
resumes by email. (Deloitte, EY and KPMG were on this list until October 2026.
Their search pages turned out to be readable and open to scripts, and each
now has a reader in `readers/`.)

They are not forgotten:

- the report lists them under **Check these by hand**, with the reason;
- `jobs.json` publishes them as `unread`, which is the first list
  [Search deeper](#search-deeper) works through;
- links to their postings on the board are still verified.

### The state job bank

`readers/utahjobs.py` reads Utah's Department of Workforce Services job bank
(jobs.utah.gov) with about fifteen keyword searches around Salt Lake City. It
lists jobs at hundreds of employers, including ones this script cannot read
directly.

**Its rows are leads, not postings.** The link opens the job bank, which asks
for a free UtahID sign-in before it shows the details. A long title arrives cut
at 40 characters, and the row ends in an ellipsis to say so. No years or degree
bar is read, because the search returns no posting text.

So a lead is published only for an employer this script does not read itself.
Where an employer's own feed was read, that feed is the truth about its jobs
and the job bank's copies are left out: a relisting source never owns a job.
The page tags each lead **state job bank lead** and puts a **find the
employer's posting** link beside it.

`readers/usajobs.py` is the other relisting source: one search of USAJOBS
returns every federal agency's announcements for Utah. The same ownership rule
applies to it, but its rows are not leads, because each link opens the
announcement itself. Only a reader that sets `LEADS = True`, which today is
the state job bank alone, has its rows marked `agg` in `jobs.json`, and `agg`
is what the page's State job bank chip and lead tag go by.

### The database: jobs.db and jobs.json

**`jobs.db` holds everything.** It is a SQLite file, git-ignored and rebuilt
from the feeds. Every row every feed returns is recorded: kept or dropped, and
if dropped, why; the day it was first seen, the day it was last seen, and the
day it disappeared. A job whose link changes while its title and place stay the
same keeps its history. A feed that fails on a given day is left exactly as it
was, so a timeout is never read as every job closing.

**`python3 refresh.py --why "title"` reads it back.** It needs a `jobs.db`, so
run a refresh once first. It matches on title, employer or link, prints up to
60 rows, and says, for each row, one of: kept and published (with the level, the place, and the years
and degree bar where known); on the feed but dropped by the title rules, with
the rule; published as an experienced-level role; open to internal applicants
only; or no longer on the feed. When nothing matches, no feed has ever returned
the job, which means its employer is not a source.

**`--skip` and `--only` leave feeds out of a run.** `--skip utahjobs` skips one
kind of feed and `--only greenhouse` reads just that kind; separate several
kinds with commas. What the database holds for the feeds left out is not
touched, and the report says how many were left out.

**`jobs.json` is the published slice.** It is committed, about 1 MB, and
fetched by the page. It holds every live row the title rules keep, plus the two
classes described below, each marked as its own class. Rows past their closing
date are left out. On 2026-10-09 it held about 3,500 rows at about 600
employers: about 2,300 entry-level, about 1,200 experienced-level and 2
internal-only. About four rows in ten were state job bank leads.

| Top-level field | Meaning |
| --- | --- |
| `date`, `prev` | The day of this refresh and of the one before it. "New" in All openings is measured from `date` |
| `sources`, `employers` | Feeds read on `date`, and distinct employers among the rows |
| `entry`, `senior`, `internal`, `leads` | Row counts: entry-level, experienced-level, internal-only, state job bank leads |
| `dead` | Links on the board that failed this run's check |
| `unread` | Employers known but not read, each as `{co, url, why}` |
| `jobs` | The rows |

| Field of a job | Meaning |
| --- | --- |
| `co`, `title`, `loc`, `url` | Employer, title, place and link, as the feed gave them |
| `geo` | `home` (Utah), `remote` or `elsewhere` |
| `sig` | `program`, `entry`, `unleveled` or `senior` |
| `field` | One of ten fields, from the title |
| `src`, `card` | The source it was read from when that is not the employer's own name, and the source's name when the source is one of the board's |
| `swe`, `deg` | A software-engineering ladder; the posting's own degree bar |
| `yrs` | Years of experience, read by a program from the posting text |
| `closes`, `posted`, `seen` | The posting's closing and posting dates, and the day the row was first seen on its feed |
| `int`, `agg` | Internal applicants only; a lead, which is a row from the state job bank whose link opens the job bank and not the employer's posting |

Everything after `field` is present only where it is known or true. `seen` is
left out for a row recorded on the first run that read its source, because that
date says when the script arrived, not when the job did.

### What counts as a role worth reporting

The same title rules decide what the report lists and what `jobs.json`
publishes. A title is kept when it names a
new-grad program (new grad, university, rotational, a 2026 or 2027 class, a named
program), or uses entry-level wording (analyst, associate, junior, "I", staff
auditor, and the "Associate Product Manager" or APM rung, whose title says
"manager"). Near home, a title with no level word at all ("AI Onboarding
Specialist") is kept too, marked `?years` so you read the posting; everywhere
else that would flood the report. Internships, co-ops, summer analyst programs,
MBA, Master's and PhD tracks are dropped, because a December graduate cannot use
them, and so are intermediate levels ("Intmd Analyst", "Programmer Analyst 2")
and retail advice and branch roles.

Reading three times as many feeds, universities, governments and hospitals
among them, needed four more rules:

- **Plurals and job families.** "Analysts" and "Associates" count as
  entry-level words, and "Managers", "Architects", "Directors" and
  "Supervisors" as seniority words, because a public employer titles a
  requisition by its job family ("Business Intelligence Analysts"). A clinical
  or research "data manager" manages data, not people, and is kept.
- **Institutions.** At a university, a government or a hospital, "University",
  "Campus", "Graduate" and "Academic" are plain description, not a new-grad
  program ("Campus Events Assistant"). `INSTITUTIONS` names the sources this
  applies to. Academic ranks, clinical jobs, trades, hourly plant and shift
  work, temporary and recreation jobs are dropped.
- **Places.** A feed that names a building ("City Hall", "Park City Hospital")
  or a bare city is placed using the state the feed carries elsewhere, the
  posting's own address, or, for an employer that works in one place, the place
  given in `ASSUMED_PLACE`. Ashby postings the employer has left unlisted are
  skipped.
- **Field.** Every row gets one of ten fields from its title, and the first
  match wins: security, risk, data, engineering, research, software, finance,
  product, business, other. That is what the Field chips filter on.

**Two classes are published but are not entry-level openings.** Neither is
listed by the page unless you ask for it (see [All openings](#all-openings)).

- **Experienced.** A senior, lead, architect or numbered-level role in Utah
  that the title rules drop only for its level is published with `sig` set to
  `senior`. It never appears in the report. Managers and executives are not
  published, and neither are experienced roles outside Utah.
- **Internal only.** A posting its employer opens only to current staff is
  published with `int` set, not as an ordinary opening. The feed has to say so:
  the University of Utah's does, in each posting's Type of Recruitment field.

**Years of experience are read from the posting text wherever a feed supplies
it.** That covers Greenhouse, Lever, Ashby and JazzHR, the Workday and Oracle
jobs that are read in full, the University of Utah, and the readers that fetch
each kept job's text. A feed that gives only a title and a place (Workable,
BambooHR, ADP WorkforceNow and the state job bank among them) gives no number.
On 2026-10-09 about one row in four in `jobs.json` had one. The reading goes
like this:

- the text is cut into sentences and list items, so one bullet is never read
  together with the next;
- a Preferred or Nice-to-have section is skipped whole;
- a soft word softens a number only in its own clause: "2+ years in a
  customer-facing role, ideally in SaaS" is a firm two;
- an upper bound ("up to 2 years") is no bar;
- an exchange rate ("one year of experience for one year of education") is not
  a requirement;
- somebody else's experience ("leaders with 20+ years") is ignored;
- the first requirement after the requirements heading wins, because a posting
  states its main bar first.

A posting that states nothing is recorded as unknown, never as zero. The number
is a reading aid, which is why the page prints it with a tilde and tells you to
open the posting.

**Workday and Oracle jobs are read in full.** Their job lists say "3 Locations"
for a multi-city job, which hides a Salt Lake City seat, and never give a closing
date. So every row that passes the filters, and every multi-city row that could
pass them at home, is looked up individually for its full list of cities, its
country, its scheduled end date and its posting text, which is where the years
and the degree bar come from. A job whose requisition is abroad is marked
that way even when its location is a building name ("TAURUS" is in Frankfurt).
Those lookups are retried with a pause and capped at six at a time across
all boards, because Workday answers bursts with HTTP 429. If a multi-city row
still cannot be read, the whole board is reported as unread for the day rather
than guessed at, so a role never shows up as closed one week and new the next.
A board read successfully but not completely (Bloomberg's search pages skip a few
jobs) is listed under **Boards read only in part**.

### The report

**The report is grouped by what you would do about it:** roles in Utah, remote
roles, **new-grad programs elsewhere** (the ones worth relocating for), and other
entry-level roles elsewhere. Every row is printed; an earlier version capped the
out-of-state list at fifteen and silently hid exactly the programs a candidate
would move for. After those come every live role **closing in the next 14 days**,
by date, and any opening on the board **past its closing date**. Employers differ
on whether a scheduled end date is the last day or the day after (Wells Fargo's is
the day after), so apply a day early.

The report covers entry-level roles only, so experienced-level roles are never
in it. A line near the top, starting `Database:`, counts what went into
`jobs.json`. A source read for the first time is listed under **Sources read
for the first time** with a count, and its roles are not listed as new, because
a whole board arriving at once would bury the roles that really opened this
week.

**A dead link is not always a closed role.** When the same title is still on
the employer's feed, the report marks the link `moved` and gives the new one,
so the opening is re-pointed rather than dropped. Zions re-indexed its whole
careers site in October 2026 and every link changed; Fidelity reposts its Leap
and FidYOU classes under new requisition numbers.

**Dead links are judged by the hiring system, not by the page.** For Greenhouse,
Lever, Ashby, Workday, Workable, Oracle, ADP, Goldman and University of Utah
links, and for any link a file in `readers/` can answer for, the script asks the
system itself whether the job still exists; Deloitte and KPMG pages are judged by
their title ("Error", "Job Posting Not Found") and EY's Yello links by whether
they redirect to the job board. A link is reported only when the
answer is a definite no, so sites that block scripts are never flagged by mistake.

**The page strikes dead links out by itself.** Every board link that fails the
check is published in `jobs.json` as `dead`. As soon as the page loads that
file, the opening is struck out on its card, tagged **no longer posted**, and
left out of All openings. It no longer waits for a hand edit. A `moved` link is
in that list too, so it stays struck out until you re-point it.

**If `applications.json` exists**, the report ends with a section that takes each
application and says whether this script could have found it, and if not, why:
the employer is not tracked, its board has no readable feed, the title rules
dropped it, or it has since closed. A board that could not be read that day is
reported as "could not check", never as "closed".

### After a refresh

Commit the new `jobs.json`. That is all the All openings tab needs.

The board is still edited by hand. Update the openings in `index.html` and change `REFRESH_DATE`
plus the footer date to match. Give every opening that first appeared in this
run `added: "<the new REFRESH_DATE>"` (and a new employer the same field in
`COMPANIES`); that is all the **New this week** flag needs. Check the posting
date first: a role that was live before the previous refresh but missing from
the board, or a repost of a program already listed, gets no `added`.

On the board, "new" means added within the six days up to `REFRESH_DATE`. So a
mid-week refresh keeps the tags the last one set, and a refresh a week later
clears them, with nothing to clean up by hand.

## Printing

The page has a print stylesheet that keeps the dark theme, drops to two columns,
avoids splitting cards across pages, and starts each timing section on a fresh
page. The upload button, profile switcher and dialogs are hidden.

Use your browser's print dialog with **Background graphics** turned on. The
current board comes to about eighteen pages.

Printing from the All openings tab prints the rows on screen, which is 60 until
you ask for more. The tabs, that tab's filters and the "more openings" buttons
on the cards are left out of the print.

## How it works

The page lives in `index.html`: markup, styles and script in one file, with no
framework and no build step. The one file it needs beside it is `jobs.json`,
fetched when the page loads, because that file is rebuilt on every refresh and
is too large to edit by hand.

### Seniority caps

Each opening listed on a card carries the years of experience its live posting demands,
read from the employer's own hiring system. The page enforces the ceiling in
code rather than trusting the model, which proved inconsistent about it: a role
requiring three to five years was scored 94 for a graduating undergraduate in
testing, while a comparable one was correctly demoted. A gap of three years or
more caps an employer at 70, two years caps it at 80, and a company whose
easiest opening is still out of reach drops to the watch list. Openings with no
stated requirement count as reachable, so one genuine new-grad role keeps the
employer scoring on its merits.

The same ceiling applies to a single job on the All openings tab. A score from
Claude is shown at 80 at most when the posting asks for two years more than the
person has, and at 70 at most for three or more. An Experienced title with no
number read from its posting is taken to ask for four years.

### Opening tags

Each opening on a card can carry a few small tags, all read from the opening itself
rather than from the company:

| Tag | Meaning |
| --- | --- |
| new | The opening was added to the board within the six days up to the latest refresh (its `added` date, measured against `REFRESH_DATE`) |
| new-grad program | The title names a structured program or an explicitly new-grad requisition |
| relocate | The opening is neither in the Salt Lake area nor remote, even if the company has a Salt Lake office |
| closes Sep 25 | The posting's own closing date. It turns red within a week, and once the date has passed (by this browser's clock) it reads "closed" and is struck through |
| no longer posted | The employer's own system no longer recognized the link when `refresh.py` last asked. The opening is struck through and treated as closed |
| leans SWE | The title is a software-engineering ladder, where an information-systems resume is judged against computer-science graduates |
| wants a CS degree | The posting's own degree bar: only technical majors, or a master's or PhD |
| N+ yrs | The live posting asks for that many years, so it is not entry-level. Read off the posting by hand |
| applied | You applied to it (from My applications) |

A row on the All openings tab carries the same kinds of tag, read from
`jobs.json` where the row came from a feed, plus a few of its own:

| Tag on a job row | Meaning |
| --- | --- |
| new | Posted, or first seen on its employer's feed, in the seven days before the database was refreshed. Measured from the refresh date, not from today's clock |
| new-grad program | The title rules read it as a structured program or an explicitly new-grad requisition |
| closes Oct 25 | The posting's own closing date, as on a card. A row past its closing date leaves the list |
| ~N+ yrs | Shown from two years up. The tilde means a program read the number from the posting text, so open the posting to confirm. No tilde means it was read by hand |
| leans SWE | As on a card |
| wants a technical major, wants an MS or PhD | The posting's own degree bar, read by a program for a feed row. A board opening or a web find shows the bar in the words it was recorded in |
| level not stated | No level word in the title. Such titles are kept in Utah only, and the posting may ask for experience |
| experienced | A senior, lead, architect or numbered-level title. Not an entry-level opening |
| internal applicants only | The posting says it is open only to people who already work for the employer |
| applied Oct 2 | You applied to it (from My applications) |
| found on the web | Saved by Search deeper for this profile and never checked by `refresh.py`. With "not opened" when no page read of the link is on record |
| on the board | The employer has a hand-researched card on the Employers tab |
| state job bank lead | A lead from Utah's job bank, not a posting read from the employer. Its link opens the job bank, which asks for a free UtahID sign-in |

**Weak fits are flagged, not hidden.** Two kinds of opening are a stretch for an
information-systems resume: a software-engineering ladder (Software Engineer,
SDE, backend, SRE, DevOps, embedded, ML or AI engineer &mdash; data engineering is
deliberately excluded), and a posting whose own degree bar names only technical
majors or demands a master's. `refresh.py` marks both in its report, `[SWE]` and
`[technical majors]` or `[MS/PhD]`, reading the degree line out of the posting
where it can see one. The **Hide weak fits** chip takes them off the board, and
**Hide applied** does the same for openings you have already applied to; each
card says how many of its openings are hidden.

**New this week.** An opening that the employer posted since the previous
refresh carries an amber **new** tag, and an employer added in the latest
refresh carries a **New on the board** badge. A role the board had merely
overlooked, or a program reposted under a new requisition number, is not new,
because the tag is meant to say "this just opened, move", not "this is new to
the page". The **New this week** chip, first in the Timing row, shows only the
employers that have something new and, on each card, only its new openings; the
number on the chip is how many new openings and employers there are. Nothing has
to be cleaned up later: the tag shows for anything whose `added` date falls in
the six days up to `REFRESH_DATE`. So a mid-week refresh keeps the tags the last
one set, and a refresh a week later clears them. An
opening that passes its closing date stops counting as new.

The All openings tab has its own New this week chip, and it does not use
`added` or `REFRESH_DATE` for rows from a feed. It reads the posting date, or
the day the row was first seen on its feed, and measures seven days back from
the `date` in `jobs.json`. One of the board's own openings is also new there
whenever it is new on its card, and a web find is never tagged new.

The **New-grad programs elsewhere** filter shows employers with at least one
program outside the Salt Lake area. It and the relocate tag are Salt Lake-relative,
so they are hidden once a tailoring run re-maps the board to another city.

### Saved profiles and a re-verified board

A tailored profile records each employer's timing on the day it was made. Timing
is a fact about the board rather than the candidate, so once the board has been
re-verified (a later `REFRESH_DATE`), the board's own status wins for every
employer; the tailored note is kept as long as that employer's facts (status and
openings) are unchanged, and the board's note replaces it when they are not. Only a candidate-specific "wrong cohort" verdict
survives, and the seniority cap is re-applied against the openings as they stand
now. The footer then says the profile's Apply now and Watch later advice predates
the re-verification. Employers added to the board after a profile was made are
hidden from it, and listed in the footer, until the tailoring is re-run.

**Closing dates are applied by the page itself.** An opening past its closing
date (by the browser's clock) is struck through, stops counting toward the
New-grad programs elsewhere and Live, not applied yet filters, and is no longer
sent to Claude or used for the seniority cap. Once every entry-level opening an
employer lists has closed, it drops from Live role now to the watch list, so a
board that has not been refreshed for a few weeks does not keep urging you to
apply to programs that have ended.

**So are dead links.** An opening whose link is in the `dead` list of
`jobs.json` is treated like one past its closing date from the moment the page
loads that file. Nobody has to edit `index.html` first.

### Data model

```js
COMPANIES[]      // name, location, locType, industry[], roles[], score, tier,
                 // badges[], why, careers, linkedin, and optional alumni signals
APPLY_STATUS{}   // per company: status, note, openings[{title, loc, url, yrs?, closes?, program?,
                 //   degree?, swe?, added?}]   added = the REFRESH_DATE it first appeared on
FAIRS[]          // University of Utah career fairs, rendered with live countdowns
REFRESH_DATE     // drives the "Verified live" label on every card, and what "new" means on the board
```

Those four are written in `index.html` by hand. The openings database is not:

```js
jobs.json        // written by refresh.py, fetched when the page loads:
                 //   date, prev, sources, employers, entry, senior, internal, leads,
                 //   dead[]    links on the board that failed the last check
                 //   unread[]  {co, url, why} for employers refresh.py knows about and cannot read
                 //   jobs[]    {co, title, loc, url, geo, sig, field, src?, card?, swe?, deg?, yrs?,
                 //              closes?, posted?, seen?, int?, agg?}
```

The fields are explained under
[The database: jobs.db and jobs.json](#the-database-jobsdb-and-jobsjson). The
page matches a board opening to a feed row by the id inside the link, not by
the whole link, because the same posting is linked in more than one form. In
the browser, Claude's rankings sit in `localStorage` under `jf.jobRank` and web
finds in the IndexedDB database `jobfinder`, both keyed by profile.

`locType` is relative to wherever the candidate is: `local`, `hybrid`, `remote`,
or `far` meaning it would require relocation. On the original board it is
relative to Salt Lake City.

Statuses sort in a fixed order: live roles, suggested employers, opening later,
watch list, wrong cohort. A Timing, Where or Industry chip that would match
nothing is hidden; the other chips and the search box can still produce "No
matches".

### The tailoring module

The code after the `// === RESUME TAILORING ===` comment is self-contained. It
loads the Anthropic SDK from a CDN only when you first run a tailoring pass, so
the page stays fast for everyone who never uses the button.

Notable choices:

- **Structured outputs.** The response is constrained by a JSON schema, so the
  shape is guaranteed rather than parsed hopefully.
- **Adaptive thinking**, streamed with summaries visible in the panel.
- **Prompt caching** on the board data, which is the large, stable part of the
  request.
- **Server-side fallback** on all three models, so a request declined by a
  safety classifier is retried automatically on another model instead of
  failing. Not every decline is routed (Sonnet 5.5 keeps `bio`,
  `reasoning_extraction` and `general_harms`), so the error message names the
  category and says whether a backup model was tried.
- **Everything Claude returns is treated as untrusted.** Scores are clamped,
  unknown enum values are dropped, unknown companies are ignored, duplicates are
  removed, the short fields are length-capped (initials, labels, city, suggested
  names), and anything rendered as HTML is escaped.
  A run that returns fewer than 80% of the companies is rejected rather than
  applied.

The All openings tab is the code after the `// === ALL OPENINGS ===` comment,
and the two Search deeper steps are the `LOOKING FURTHER` part of the tailoring
module. They make the same choices: a JSON schema for the ranking and a strict
schema for `save_jobs`, adaptive thinking, prompt caching, server-side fallback,
and the same distrust of whatever comes back.

### Debug handle

`window.JobFinderTailor` exposes `applyProfile`, `buildProfile`, `buildParams`,
`profiles()` and `OUTPUT_FORMAT` for console use and testing. For Search deeper
it also exposes `candidateBrief`, `jobsForPrompt`, `buildRankParams`,
`applyRank`, `buildSearchParams`, `handleSave`, `deepSearch`, `harvestUrls`,
`DEPTHS`, `SAVE_TOOL` and `RANK_FORMAT`, so that the request shapes and the
search loop can be tested without a key.
`window.JobFinderApps` exposes `list()`, `merge()`, `clear()` and the spreadsheet
readers `parseText()`, `parseXlsx()` and `importRows()`.

`window.JobFinderJobs` is the handle for the All openings tab:

| Member | What it is |
| --- | --- |
| `all()`, `data()` | The merged list of jobs, and `jobs.json` as loaded |
| `key(url)` | The key a posting is matched on |
| `isNew(job)`, `closed(job)`, `source(job)`, `passes(job, query)` | The facts and the filter test behind a row |
| `score(job)`, `ranked(job)` | The keyword-match score, and Claude's score after the seniority ceiling (or null) |
| `feedExtras(employer)`, `openEmployer(name)` | What a card's "more openings" button counts, and what clicking it does |
| `state`, `setView(v)`, `refresh()` | The filter state, the tab switch, and a redraw |
| `found()`, `FoundDB`, `loadFound()`, `saveRank()` | The web finds on screen, the IndexedDB store behind them, a reload of it, and the write of a ranking |
| `guessField(title)` | The field given to a row that did not come from a feed |
| `setData(d)`, `reload()` | Swap in another database, and fetch `jobs.json` again |

The page has no button for deleting one web find. Removing a saved profile
from the menu deletes that profile's finds; the sample board cannot be
removed, so from the console
`await JobFinderJobs.FoundDB.clear('default'); await JobFinderJobs.loadFound();`
clears them for the sample board, whose profile id is `default`. A tailored
profile's id is in `JobFinderTailor.profiles()`.

## Editing the board by hand

Add or change a company inside the `COMPANIES` array, and its hiring status
inside `APPLY_STATUS` keyed by the exact same name. A company with no
`APPLY_STATUS` entry falls back to the watch list.

Two things to know:

- **A 200 response does not mean a job link is alive.** Career sites render in
  the browser, so a dead posting still returns a page. Verify against the
  applicant tracking system API instead, where a removed job returns 404.
- **Some sites block scripted requests** and are fine in a real browser. Do not
  "fix" links for lucid.co, openai.com, perplexity.ai, or any linkedin.com URL
  based on a failed command-line fetch.

## Testing

Three sets of checks, none of which needs an API key or spends credits, and a
folder of resumes for real runs:

- **`samples/harness.js`** replays fifteen mock responses through the page and
  checks every rule in LOGIC.md, plus what each scenario demands (511 checks on
  today's board). Run it from the browser console:
  `await import('/samples/harness.js'); await JobFinderHarness.run();`
- **`samples/jobs-harness.js`** checks the All openings list, the ranking and
  the web search (about 85 checks). Run it the same way:
  `await import('/samples/jobs-harness.js'); await JobFinderJobsHarness.run();`
  It swaps a small invented database in for `jobs.json`, replays a scripted
  stand-in for the API, and puts the real database back when it finishes. That
  stand-in is the only "API" the two Search deeper steps have been run against,
  so this harness proves the request shapes, the save rules and the search
  loop, and nothing about what a live run finds or costs.
- **`python3 refresh.py --selftest`** runs offline and checks the refresh rules:
  30 made-up titles that must be kept, 45 that must be dropped, and about 65
  further checks of the years reading, the places, the robots.txt rule and the
  rest. Its last line prints the exact counts.
- **`samples/resumes/`** holds twelve fictional candidates who are nothing like
  the sample candidate: a nurse, a mechanical engineer, a chemist, a journalist, a
  product designer, a marketer, an international civil engineer, a CS master's
  student in Austin, a career-changing teacher, a BYU accounting senior, a
  bootcamp graduate with no degree and a five-year data engineer. They are for
  real runs against the API when a prompt change needs judging rather than
  checking.

The mock responses are generated from the board by `samples/make-cases.py`, so
they cover every employer; re-run it after adding one. See
[`samples/README.md`](samples/README.md).

The current build was checked across roughly 190 assertions covering: every
filter and search field, sort order and grouping, the career fair countdown,
modal behavior, key masking and persistence, all four resume input formats and
their failure modes, the exact request shape, all nine API failure paths,
streaming, the Stop button, storage exhaustion, profile save, switch, delete and
reload, hostile model output, mobile layout, and the print stylesheet.

## Deploying

**Live at https://davezagin-max.github.io/ai-job-finder/**

The page is static, so any static host works. This copy is served from GitHub
Pages off the `main` branch. To deploy your own fork:

```bash
git init
git add .
git commit -m "AI Job Finder"
git branch -M main
git remote add origin https://github.com/<you>/<repo>.git
git push -u origin main
```

Then in the repository settings, enable Pages from the `main` branch. The site
appears at `https://<you>.github.io/<repo>/`.

`jobs.json` and the `readers/` folder belong in the repository, so commit
them. The page needs `jobs.json` beside `index.html`, or its All openings
tab has only the board's own openings to show. `refresh.py` loads about 80 of
its feeds from the files in `readers/`. `jobs.db` is not committed: it is
about 16 MB, it is rebuilt from the feeds, and `.gitignore` lists it.

Deploy from git, not by uploading the folder. `applications.json`,
`refresh-report.txt` and `.refresh-state.json` are git-ignored and personal; a
drag-and-drop upload of the folder to a static host would publish them, and
`jobs.db` with them.

No license file is included, which means default copyright applies and nobody
else may reuse the code. Add one if you want them to.

Nothing in the repository contains an API key or personal contact details, and
`.gitignore` excludes local Claude Code settings, the job database and the
generated refresh state and reports. `jobs.json` is public data about job
postings and carries nothing about any reader.

## Limitations

- **Three levels of checking, and only one is by hand.** A card on the
  Employers tab exists because somebody wrote it and read its openings. A row
  on the All openings tab was read from a feed by a program. A web find was
  read by Claude, once. Web finds and job bank leads are tagged as such, and a
  tilde marks a years figure that a program read.
- **Coverage still has an edge.** The board cannot show an employer nobody
  added. All openings widens that to the employers whose feeds `refresh.py`
  reads, more than 300, and Search deeper to whatever a web search turns up. An
  employer on no list, whose postings no search finds, is still invisible.
  `python3 refresh.py --why "job title"` says which case a missing job is.
- **All openings is built around Utah.** The extra sources are mostly Utah
  employers, many large feeds are searched for Utah only, titles with no level
  word and experienced titles are kept in Utah only, and the Where chips read
  Utah, Remote and Elsewhere whatever city the profile on screen lives in.
- **An entry-level title is not an entry-level requirement.** Many analyst
  titles at public employers ask for two or more years, and the University of
  Utah's Business Intelligence Analysts posting is one of them. That is what
  the years tag and the Out of reach chip are for.
- **A years figure with a tilde was read by a program.** Open the posting. No
  years tag is not a promise of none: about three rows in four carry no
  number, because their feed supplies no posting text or the text states none.
- **State job bank rows are leads.** They have no link to the employer, the
  job bank asks for a sign-in, some titles are cut short, and no years or
  degree bar is read for them.
- **Web finds are not re-checked by `refresh.py`.** A find stays in the list
  until its closing date passes, where the posting gave one, until an
  employer's own feed lists the same job, or until you delete it. One tagged
  "not opened" was never read at all.
- **Search deeper was tested against a scripted stand-in, not the live API.**
  Its cost figures are estimates and the completion toast is the real number.
  Web search also has to be switched on for your organization in the Anthropic
  Console.
- **A ranking is a snapshot.** Openings that arrive in a later refresh are
  unranked until you run the ranking again.
- **The page is no longer strictly one file.** It fetches `jobs.json`. Opened
  straight from disk (`file://`), some browsers block that fetch, and the All
  openings tab then shows only the board's own openings and says why.
- **It asks before it reads, so some employers stay unread.** Employers on
  NEOGOV, PeopleAdmin, UKG, Paycom, Paycor and Getro, and ones whose careers
  sites turn scripts away, are listed to check by hand and handed to Search
  deeper. Nothing of theirs is in the database unless the state job bank
  happens to list it.
- **It is a snapshot.** Companies on the watch list will quietly start hiring
  after the refresh date. Rerun `refresh.py`.
- **Openings are verified by hand for the original board only.** A tailoring run
  re-scores and re-explains, but does not re-check which jobs are live, and
  suggested employers are never verified at all.
- **The API key lives in the browser**, which is the tradeoff for having no
  backend.
- **Some boards defend against scripts.** Morgan Stanley's campus board (Oleeo)
  shows a CAPTCHA after repeated automated requests. The script reports that as a
  board it could not read, and never tries to get past the check.
