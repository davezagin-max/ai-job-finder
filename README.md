# AI Job Finder

A single-page job board for new-grad roles at AI-forward companies, with a
button that re-tailors the entire board to any resume you upload.

The board itself is hand-researched: about 80 employers, each with a verified
hiring status and, where they exist, links to openings that were confirmed live
on a stated date, with the closing date each posting gives. As shipped it is
curated for new-grad data, AI and fintech roles around Salt Lake City, plus the
structured new-grad programs elsewhere that are worth relocating for. That is the
starting point every uploaded resume gets re-scored against. The tailoring button sends a resume to Claude, which re-scores
every employer for that person, rewrites the reasoning on each card, and for a
candidate outside Salt Lake City adds employers in their own city.

No build step, no server, no dependencies to install. It is one HTML file.

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
- [Using the resume upload](#using-the-resume-upload)
- [What a tailoring run changes](#what-a-tailoring-run-changes)
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

The default board is a template. It carries no one's personal details: the
header describes who the list was curated for, and every card explains the
employer rather than any particular candidate. Upload a resume and the whole
thing rewrites itself around that person, in that person's browser only.

## Quick start

Open `index.html` in a browser. That is the whole install.

Some browsers restrict `file://` pages, and the upload button needs to load a
library from a CDN, so serve the folder instead if the button misbehaves:

```bash
python3 -m http.server 8765 --bind 127.0.0.1
```

Then open http://localhost:8765/index.html

Keep the `--bind 127.0.0.1`. Without it Python serves the folder to every device on
your network, and if you track applications (below) that includes your
`applications.json` and `refresh-report.txt`.

## Using the resume upload

1. Click **Upload a resume**.
2. Paste an Anthropic API key. Create one at
   [console.anthropic.com](https://console.anthropic.com/settings/keys).
3. Choose a model and a thinking effort, or keep the defaults.
4. Drop in a PDF, a Word file or a text file, or paste the resume text.
5. Click **Tailor the board**.

The run takes one to three minutes on the default settings. Claude's reasoning
streams into the panel while it works, and a Stop button cancels at any time.

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
| Timing notes | Rewritten wherever the original referenced the board owner's school or graduation date |
| Where filters | Relabeled to the candidate's metro, with a "Needs relocation" filter for employers that would require a move |
| Suggested employers | Up to fifteen in the candidate's own metro and field, whenever the board's geography or its subject matter does not fit them |
| Footer | Which live roles to apply to first, and what to watch for later in the season |
| Career fair strip | Hidden by default; appears only for a University of Utah student |

### About the suggested employers

They appear whenever this board is the wrong board for the person: they live
somewhere else, or they work in a field it does not cover. Since 57 of the 60
employers hire data, analytics or software people, a candidate in another
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
filters keep their original meaning and no suggested employers are added. This is
deliberate. The researched board is already correct for those candidates.

The career fair strip and the alumni filter are gated on the school rather than
the city, so they never appear on the default board and show up only when a
resume identifies a University of Utah student.

## Cost

Each run bills the API key you paste. Rough cost per run:

| Model and effort | Typical cost | Typical time |
| --- | --- | --- |
| Sonnet 5, medium (default) | about $0.15 | about a minute |
| Sonnet 5, low | under $0.10 | well under a minute |
| Opus 5, high | $0.50 to $1.50 | several minutes |
| Fable 5.1 | $1.00 to $3.00 | slowest |

Effort matters more than the model. Thinking is billed as output, so most of the
cost of a high-effort run is reasoning rather than the answer. Opus 5 at high
effort was only a third of the way through the board after four minutes, which is
why the defaults are Sonnet 5 at medium effort.

The model is asked for one score and one boolean per employer. Tiers and badges
are derived in the page from those scores and the board's own data, which removes
the most expensive per-company deliberation and makes the results reproducible.

The board data is sent with a cache marker, so repeated runs in the same session
cost noticeably less on input tokens. The completion toast reports the actual
cost of the run you just made.

## Where your data goes

- The API key is stored in your browser's `localStorage` and sent only to
  `api.anthropic.com`. There is no server in this project to send it to.
- **The resume is never stored.** It is read in the browser, included in the one
  API request, and discarded. Only Claude's response is saved.
- Saved profiles stay in `localStorage` on that one browser. They are not synced
  and never leave the machine.
- Clearing site data removes the key and every saved profile.

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
- The dialog lists every application at an employer this board does not cover.
  Those are the most useful signal for what to add next: a job you found that
  the board could not show means the next one like it will be missed too.

**Import JSON** and **Export JSON** move the list between browsers. When the page
is served from your own machine (`localhost`), it also loads an
`applications.json` sitting next to `index.html`. That file is in `.gitignore`
and must stay there, because this repository is public. The format:

```json
[
  { "company": "Example Bank", "title": "Data Analyst I",
    "location": "Salt Lake City, UT", "applied": "2026-09-01",
    "status": "pending", "note": "Recruiter screen booked" }
]
```

## Keeping the job data fresh

`refresh.py` re-checks every job board and reports what changed.

```bash
python3 refresh.py
python3 refresh.py --selftest   # the title rules, checked against real titles; no network
```

It takes about a minute, uses only the Python standard library, and reads 101
feeds directly: Greenhouse, Lever, Ashby, Workable, Workday (including employers
on the shared `myworkdaysite.com` host, such as Fidelity and Wells Fargo),
BambooHR, Oracle Recruiting Cloud (JPMorgan, American Express), Avature
(Bloomberg), iCIMS sitemaps (Cotiviti, America First), a SuccessFactors feed
(Vivint), JazzHR (Cicero), Taleo behind SelectMinds (Zions), Eightfold and Oleeo
(Morgan Stanley), and the GraphQL service behind Goldman's campus site. Three
employers still have to be checked by hand: Deloitte, whose search is rendered in
the browser and whose RSS feed ignores the search, and EY and KPMG, which publish
no feed. Links to their postings are still verified.

**Workday and Oracle jobs are read in full.** Their job lists say "3 Locations"
for a multi-city job, which hides a Salt Lake City seat, and never give a closing
date. So every row that passes the filters, and every multi-city row that could
pass them at home, is looked up individually for its full list of cities, its
country and its scheduled end date. A job whose requisition is abroad is marked
that way even when its location is a building name ("TAURUS" is in Frankfurt).
Those lookups are few, retried with a pause, and capped at six at a time across
all boards, because Workday answers bursts with HTTP 429. If a multi-city row
still cannot be read, the whole board is reported as unread for the day rather
than guessed at, so a role never shows up as closed one week and new the next.
A board read successfully but not completely (Bloomberg's search pages skip a few
jobs) is listed under **Boards read only in part**.

**What counts as a role worth reporting.** A title is kept when it names a
new-grad program (new grad, university, rotational, a 2026 or 2027 class, a named
program), or uses entry-level wording (analyst, associate, junior, "I", staff
auditor, and the "Associate Product Manager" or APM rung, whose title says
"manager"). Near home, a title with no level word at all ("AI Onboarding
Specialist") is kept too, marked `?years` so you read the posting; everywhere
else that would flood the report. Internships, co-ops, summer analyst programs,
MBA, Master's and PhD tracks are dropped, because a December graduate cannot use
them, and so are intermediate levels ("Intmd Analyst", "Programmer Analyst 2")
and retail advice and branch roles.

**The report is grouped by what you would do about it:** roles in Utah, remote
roles, **new-grad programs elsewhere** (the ones worth relocating for), and other
entry-level roles elsewhere. Every row is printed; an earlier version capped the
out-of-state list at fifteen and silently hid exactly the programs a candidate
would move for. After those come every live role **closing in the next 14 days**,
by date, and any opening on the board **past its closing date**. Employers differ
on whether a scheduled end date is the last day or the day after (Wells Fargo's is
the day after), so apply a day early.

**Dead links are judged by the hiring system, not by the page.** For Greenhouse,
Lever, Ashby, Workday, Workable, Oracle and Goldman links the script asks the
system itself whether the job still exists; Deloitte and KPMG pages are judged by
their title ("Error", "Job Posting Not Found") and EY's Yello links by whether
they redirect to the job board. A link is reported only when the
answer is a definite no, so sites that block scripts are never flagged by mistake.

**If `applications.json` exists**, the report ends with a section that takes each
application and says whether this script could have found it, and if not, why:
the employer is not tracked, its board has no readable feed, the title rules
dropped it, or it has since closed. A board that could not be read that day is
reported as "could not check", never as "closed".

After a refresh, update the openings in `index.html` and change `REFRESH_DATE`
plus the footer date to match.

## Printing

The page has a print stylesheet that keeps the dark theme, drops to two columns,
avoids splitting cards across pages, and starts each timing section on a fresh
page. The upload button, profile switcher and dialogs are hidden.

Use your browser's print dialog with **Background graphics** turned on. The
current board comes to about eighteen pages.

## How it works

Everything lives in `index.html`: markup, styles and script in one file, with no
framework and no build step.

### Seniority caps

Each listed opening carries the years of experience its live posting demands,
read from the employer's own hiring system. The page enforces the ceiling in
code rather than trusting the model, which proved inconsistent about it: a role
requiring three to five years was scored 94 for a graduating undergraduate in
testing, while a comparable one was correctly demoted. A gap of three years or
more caps an employer at 70, two years caps it at 80, and a company whose
easiest opening is still out of reach drops to the watch list. Openings with no
stated requirement count as reachable, so one genuine new-grad role keeps the
employer scoring on its merits.

### Opening tags

Each listed opening can carry up to five small tags, all read from the opening
itself rather than from the company:

| Tag | Meaning |
| --- | --- |
| new-grad program | The title names a structured program or an explicitly new-grad requisition |
| relocate | The opening is neither in the Salt Lake area nor remote, even if the company has a Salt Lake office |
| closes Sep 25 | The posting's own closing date. It turns red within a week, and once the date has passed (by this browser's clock) it reads "closed" and is struck through |
| N+ yrs | The live posting asks for that many years, so it is not entry-level |
| applied | You applied to it (from My applications) |

The **New-grad programs elsewhere** filter shows employers with at least one
program outside the Salt Lake area. It and the relocate tag are Salt Lake-relative,
so they are hidden once a tailoring run re-maps the board to another city.

### Saved profiles and a re-verified board

A tailored profile records each employer's timing on the day it was made. Timing
is a fact about the board rather than the candidate, so once the board has been
re-verified (a later `REFRESH_DATE`), or an employer's status or openings have
changed since the profile was made (even on the same day), the board's own status
and note win for that employer. Only a candidate-specific "wrong cohort" verdict
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

### Data model

```js
COMPANIES[]      // name, location, locType, industry[], roles[], score, tier,
                 // badges[], why, careers, linkedin, and optional alumni signals
APPLY_STATUS{}   // per company: status, note, openings[{title, loc, url, yrs?, closes?, program?}]
FAIRS[]          // University of Utah career fairs, rendered with live countdowns
REFRESH_DATE     // drives the "Verified live" label on every card
```

`locType` is relative to wherever the candidate is: `local`, `hybrid`, `remote`,
or `far` meaning it would require relocation. On the original board it is
relative to Salt Lake City.

Statuses sort in a fixed order: live roles, suggested employers, opening later,
watch list, wrong cohort. Any filter chip that would match nothing is hidden, so
you can never land on an empty board.

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
- **Server-side fallback**, so a request declined by a safety classifier is
  retried automatically on another model instead of failing.
- **Everything Claude returns is treated as untrusted.** Scores are clamped,
  unknown enum values are dropped, unknown companies are ignored, duplicates are
  removed, strings are length-capped, and anything rendered as HTML is escaped.
  A run that returns fewer than 80% of the companies is rejected rather than
  applied.

### Debug handle

`window.JobFinderTailor` exposes `applyProfile`, `buildProfile`, `buildParams`,
`profiles()` and `OUTPUT_FORMAT` for console use and testing.

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

There is no test runner. Verification is done in the browser against the mock
responses in `samples/cases/`, which exercise the full path with no API key and
no cost. See [`samples/README.md`](samples/README.md) for how to replay one.

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

Deploy from git, not by uploading the folder. `applications.json`,
`refresh-report.txt` and `.refresh-state.json` are git-ignored and personal; a
drag-and-drop upload of the folder to a static host would publish them.

No license file is included, which means default copyright applies and nobody
else may reuse the code. Add one if you want them to.

Nothing in the repository contains an API key or personal contact details, and
`.gitignore` excludes local Claude Code settings and the generated refresh state
and reports.

## Limitations

- **The board is a hand-picked list**, so it cannot surface an employer nobody
  thought to add. Job aggregators sweep far more listings; this trades breadth
  for a verified, opinionated shortlist.
- **It is a snapshot.** Companies on the watch list will quietly start hiring
  after the refresh date. Rerun `refresh.py`.
- **Openings are verified for the original board only.** A tailoring run
  re-scores and re-explains, but does not re-check which jobs are live, and
  suggested employers are never verified at all.
- **The API key lives in the browser**, which is the tradeoff for having no
  backend.
- **Some boards defend against scripts.** Morgan Stanley's campus board (Oleeo)
  shows a CAPTCHA after repeated automated requests. The script reports that as a
  board it could not read, and never tries to get past the check.
