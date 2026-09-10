# AI Job Finder

A single-page job board for new-grad roles at AI-forward companies, with a
button that re-tailors the entire board to any resume you upload.

The board itself is hand-researched: about 60 employers, each with a verified
hiring status and, where they exist, links to openings that were confirmed live
on a stated date. As shipped it is curated for new-grad data, AI and fintech
roles around Salt Lake City, which is the starting point every uploaded resume
gets re-scored against. The tailoring button sends a resume to Claude, which re-scores
every employer for that person, rewrites the reasoning on each card, and for a
candidate outside Salt Lake City adds employers in their own city.

No build step, no server, no dependencies to install. It is one HTML file.

**New here? Read the [visual guide](guide.html)** ([live version](https://davezagin-max.github.io/ai-job-finder/guide.html)),
which explains the board and the tailoring logic in plain language with a diagram.
This README is the technical reference.

A six-page PDF of that guide is committed as
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
python3 -m http.server 8765
```

Then open http://localhost:8765/index.html

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

## Keeping the job data fresh

`refresh.py` re-checks every job board and reports what changed.

```bash
python3 refresh.py
```

It takes about eleven seconds, uses only the Python standard library, and
queries roughly 74 employer job boards directly through their applicant tracking
systems (Greenhouse, Lever, Ashby, Workable, Workday and BambooHR). It filters
to entry-level roles reachable from Utah, compares against the previous run,
tests every opening link already on the dashboard, and writes
`refresh-report.txt` grouped into Utah, remote and elsewhere.

Thirteen employers have no public API and are listed under "check by hand".

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

### Data model

```js
COMPANIES[]      // name, location, locType, industry[], roles[], score, tier,
                 // badges[], why, careers, linkedin, and optional alumni signals
APPLY_STATUS{}   // per company: status, note, openings[{title, loc, url}]
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
