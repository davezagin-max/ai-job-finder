"""Kula: an employer's public careers page, careers.kula.ai/<slug>, is drawn from data that sits inside the page
itself: every job with its offices, its posted and closing dates and its posting text. One request, no key, no
sign-in, no token. The slug is the account name in that link. The page's own script reads the list 99 jobs at a
time from an API that robots.txt closes, so a board that fills the page is checked against the site map and
reported as partial when jobs are missing."""
import sys, os, re, json, time, datetime, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import refresh as R

KIND = "kula"
SLUG_HELP = 'the account name in the careers link careers.kula.ai/<slug>, for example "varo-money"'
EMPLOYERS = {"Varo Bank": "varo-money"}
INSTITUTIONS = set()  # names from EMPLOYERS that are public bodies, schools or hospitals, whose titles use "University", "Campus" or "Graduate" as plain description
AGGREGATOR = False    # True when one slug returns the jobs of many employers

SITE = "https://careers.kula.ai/"
LINK = re.compile(r"^https?://careers\.kula\.ai/([A-Za-z0-9][A-Za-z0-9_-]*)/(\d+)(?:[-/?#]|$)")
PAGE = 99             # jobs in one page of the list, as the careers page's own script asks for them
PUSH = re.compile(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)')
_US = ("US", "PR", "GU", "VI", "AS", "MP")      # US territories are not abroad

def _rows(page):
    """The data the page hands its own script: ({row id: a long text}, [every other row])."""
    # Next.js writes the data as JSON strings which, joined, are lines of "id:value". A long text (a posting)
    # is a row "id:T<its length in bytes, in hex>,<text>" with no line end after it, so the rows are walked
    # in order and by length, never split on line ends.
    try:
        data, texts, others, at = "".join(json.loads(s) for s in PUSH.findall(page)).encode(), {}, [], 0
        while at < len(data):
            colon = data.index(b":", at)
            rid = data[at:colon].decode()
            R.need(re.fullmatch(r"[0-9a-f]*", rid), "page data that is not in rows")
            if data[colon + 1:colon + 2] == b"T":
                comma = data.index(b",", colon)
                at = comma + 1 + int(data[colon + 2:comma], 16)
                texts[rid] = data[comma + 1:at].decode()
            else:
                end = data.find(b"\n", colon)
                end = len(data) if end < 0 else end
                others.append(data[colon + 1:end].decode()); at = end + 1
    except ValueError:
        raise RuntimeError("unexpected reply (page data that cannot be read)")
    return texts, others

def _find(node, key):
    """Every dict under node that has this key."""
    if isinstance(node, dict):
        if key in node: yield node
        for v in node.values(): yield from _find(v, key)
    elif isinstance(node, list):
        for v in node: yield from _find(v, key)

def _text(value, texts):
    """A string as it was before the page packed it: "$1b" points at long text 1b, "$$5k" is a plain "$5k"."""
    if not isinstance(value, str): return None
    if value.startswith("$$"): return value[1:]
    m = re.fullmatch(r"\$([0-9a-f]+)", value)
    if not m: return None if value.startswith("$") else value     # "$undefined" and the like are no text
    R.need(m.group(1) in texts, "a posting text the page points at and does not carry")
    return texts[m.group(1)]

def _day(stamp):
    """The local day of one of the page's UTC times ("2026-10-08T20:36:40.000Z"), or None."""
    try: return datetime.datetime.fromisoformat(re.sub(r"\.\d+", "", stamp).replace("Z", "+00:00")).astimezone().date().isoformat()
    except (TypeError, ValueError): return None

def _place(o, workplace):
    """One office of a job in the form the location rules read: "Salt Lake City, UT", "Remote, US",
    "Remote, San Francisco, CA" for a remote job tied to an office, "Chennai (India, abroad)"."""
    city, state, country = (re.sub(r"\s+", " ", o.get(k) or "").strip() for k in ("city", "state", "country"))
    # Remote is said in two places: on an office of its own ("Remote", United States) or on the whole job.
    remote = bool(o.get("remote")) or (o.get("workplace") or workplace) == "remote"
    code = (o.get("country_code") or "").upper()
    # No country given: the label ("Chennai, Tamil Nadu, India", or the office's name) is all there is.
    if not code: return re.sub(r"\s+", " ", o.get("location") or o.get("name") or "").strip()
    if code not in _US:
        # Marked in the words the location rules read, because they do not know every country by name:
        # "Chennai, Tamil Nadu" would be taken for a US town, and "Chennai, TN" for Tennessee.
        return f"{city or ('Remote' if remote else '')} ({re.sub(r'[()]', '', country) or code}, abroad)".strip()
    state = R.city_state("", state)                       # "Utah" becomes "UT"
    # A US place with no state gets "US", or "Dublin" and "Vienna" would read as foreign.
    place = ", ".join(x for x in (city, state if re.fullmatch(r"[A-Z]{2}", state) else "US") if x)
    return "Remote, " + place if remote else place

def fetch(slug):
    """Return every open job as [(title, location, url, closes, degree, extra)]."""
    # A pasted link or a path is refused here. The site reads account names without regard to case, so the
    # name is lowered: one job, one link.
    name = slug.strip().lower() if isinstance(slug, str) else ""
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", name): raise RuntimeError('kula: the slug is the account name in the careers link, like "varo-money"')
    # An account that does not exist answers 404, which raises.
    texts, others = _rows(R.curl_text(SITE + name, accept="text/html", timeout=60))
    lists = []
    for row in others:
        if '"jobs"' not in row: continue                  # most rows are script names and page furniture
        try: node = json.loads(row)
        except ValueError: continue
        lists += [d for d in _find(node, "jobs") if isinstance(d["jobs"], list) and str(d.get("accountName") or "").lower() == name]
    R.need(lists, "no job list in the page")
    jobs = [j for d in lists for j in d["jobs"]]
    rows = []
    for j in jobs:
        title = re.sub(r"\s+", " ", _text(j.get("title"), texts) or "").strip() if isinstance(j, dict) else ""
        R.need(title and re.fullmatch(r"\d+", str(j.get("id") or "")), "a job without a title or an id")
        a = j.get("ats_job") if isinstance(j.get("ats_job"), dict) else {}
        places = [_place(o, a.get("workplace")) for o in a.get("offices") or [] if isinstance(o, dict)]
        text = _text(a.get("job_description"), texts)
        # The posting's own page answers at this short link whatever its title becomes.
        rows.append((title, "; ".join(p for p in dict.fromkeys(places) if p), f"{SITE}{name}/{j['id']}", _day(j.get("end_at")),
                     R.degree_flag(text), {"posted": _day(j.get("launch_at")), "yrs": R.min_years(text),
                                           "internal": j.get("kind") == "internal", "company": None}))
    rows, notes = R._dedupe(rows), []
    if len(rows) > 6000: notes.append(f"read the first 6,000 of the {len(rows):,} jobs on the page"); rows = rows[:6000]
    if len(rows) >= PAGE:
        # A full page may not be the whole board, and the next page is not ours to ask for. The site map
        # names every posting, so it says how many this one page left out.
        mine, named = {r[2].rsplit("/", 1)[1] for r in rows}, set()
        time.sleep(0.3)
        try: named = set(re.findall(r"<loc>\s*" + re.escape(SITE + name) + r"/(\d+)", R.curl_text(f"{SITE}{name}/sitemap.xml", accept="application/xml"), re.I))
        except RuntimeError: pass                         # the list still stands, and the note says what is not known
        if not named: notes.append(f"read the {len(rows)} jobs on the page, a full page: there may be more behind an API that robots.txt closes")
        elif named - mine: notes.append(f"read {len(rows)} of {len(named | mine)} jobs: the rest are behind an API that robots.txt closes")
    if notes: R.PARTIAL[slug] = "; ".join(notes)
    return rows

def link_state(url):
    """'live', 'dead' or 'unknown' for one posting URL of this system. Return 'unknown' whenever unsure."""
    m = LINK.match(url or "")
    if not m: return "unknown"
    try: code, body = R.curl_resp(f"{SITE}{m.group(1)}/{m.group(2)}", accept="text/html")
    except Exception: return "unknown"
    # A live posting describes itself to search engines as a JobPosting that carries its own id. One that is
    # gone, like an account that is gone, answers 404 with the site's own not-found page, which says so in
    # its data; a 404 without that is the service being away and says nothing about the job.
    if code == "200" and '"@type":"JobPosting"' in body and f'"value":"{m.group(2)}"' in body: return "live"
    if code == "404" and "NEXT_HTTP_ERROR_FALLBACK;404" in body: return "dead"
    return "unknown"

if __name__ == "__main__":
    for name, slug in EMPLOYERS.items():
        rows = fetch(slug)
        kept = [r for r in rows if R.classify(r[0], r[1], KIND) or R.experienced(r[0], r[1], KIND)]
        print(f"{name}: {len(rows)} jobs, {sum(1 for r in rows if R.HOME.search(r[1] or ''))} in Utah, {len(kept)} kept")
        for r in kept[:5]: print("   ", r[0], "|", r[1], "|", r[2], "|", r[3], "|", r[5])
