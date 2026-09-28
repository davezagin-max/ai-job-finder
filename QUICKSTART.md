# AI Job Finder: Quick Start

A job board for new-grad roles at about 80 AI-forward employers, focused on
data, AI and fintech jobs around Salt Lake City. It is one HTML file with no
install and no server.

**Live:** https://davezagin-max.github.io/ai-job-finder/

## Open it

Open `index.html` in a browser. If the upload button acts up, serve the folder
instead:

```bash
python3 -m http.server 8765 --bind 127.0.0.1
```

Then go to http://localhost:8765/index.html

## What you can do

**Browse the board.** Each card is one employer, with a match score, its hiring
status, and links to openings that were checked live. Use the filter chips to
narrow by status, role, location or industry.

| Status | Meaning |
| --- | --- |
| 🟢 Live role now | A matching opening is posted today |
| 🟡 Opens later this fall | Expected to post soon |
| 🔵 Watch list | Nothing open yet |
| 🔴 Wrong cohort | Hiring, but not for new grads |

**Tailor it to a resume.**

1. Click **Upload a resume**.
2. Paste an Anthropic API key (from [console.anthropic.com](https://console.anthropic.com/settings/keys)).
3. Drop in a PDF, `.docx` or `.txt` resume, or paste the text.
4. Click **Tailor the board**.

Claude re-scores every employer for that person and rewrites each card. It
takes about a minute and costs about $0.15 on the default settings. The result
is saved as a profile you can switch to from the header.

**Track applications.** Click **My applications** to log where you applied.
Cards then show what you applied for, and the **Applied** and **Live, not
applied yet** filters appear.

## Keep the jobs current

```bash
python3 refresh.py
```

This re-checks every employer's job board in about a minute and writes what
changed to `refresh-report.txt`. Copy any new openings into `index.html`, then
update `REFRESH_DATE` and the footer date.

## Your data

- Your API key, saved profiles and application list stay in your browser.
- Your resume is never saved. It goes to Claude once and is discarded.
- `applications.json` and `refresh-report.txt` are git-ignored. Keep them that
  way, because this repository is public.

## Files

| File | What it is |
| --- | --- |
| `index.html` | The whole app |
| `refresh.py` | Re-checks job boards and writes a report |
| `guide.html` | Plain-language visual guide |
| `AI-Job-Finder-Guide.pdf` | PDF copy of the guide (rebuild with `./make-guide-pdf.sh`) |
| `samples/` | Fake resumes and mock responses for testing without an API key |

## More detail

- [LOGIC.md](LOGIC.md): the rules behind scores, statuses, tailoring and the refresh
- [README.md](README.md): full technical reference
- [guide.html](guide.html): visual walkthrough of how scoring and tailoring work
