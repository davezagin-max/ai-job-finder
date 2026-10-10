"""Jobvite hosted career sites (jobs.jobvite.com/COMPANY): server-rendered HTML with no JSON list, read from
the board's own /search pages, 50 jobs a page. A job in several places shows only "3 Locations", so the board's
location filter, or failing that the posting, says which are in Utah. The slug is the company's name in the address ("usana")."""
import sys, os, re, json, time, datetime, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import refresh as R

KIND = "jobvite"
SLUG_HELP = 'the company name in the board\'s address, jobs.jobvite.com/<slug>/jobs, exactly as written there: "usana"'
EMPLOYERS = {"bioMerieux (BioFire Diagnostics)": "biofiredx", "USANA Health Sciences": "usana",
             "Laborie Medical Technologies": "laborie", "Imagine Learning": "imagine-learning",
             "Egnyte": "egnyte", "Maverik": "maverikcareers"}          # an office in Draper, filed as "Office- Draper"
INSTITUTION = False
AGGREGATOR = False

_SITE = "https://jobs.jobvite.com"
# Three templates are in use: a table (USANA, bioMerieux), a list of divs (Laborie) and a list of spans
# (Imagine Learning). All of them put the link first and mark the two cells with the same class names.
_ROW  = r'href="(/%s/job/[^"/?#]+)(?:[?#][^"]*)?"[^>]*>(.*?)<[^<>]*jv-job-list-location[^>]*>(.*?)</(?:td|a|li)>'
_MANY = re.compile(r"\b(\d+) Locations\b")
_LINK = re.compile(r"jobs\.jobvite\.com/([^/]+)/job/[^/?#]+")
_IN_TITLE = re.compile(r" - ([^-]+, [A-Z]{2})$")
_CAP = 60          # posting pages read for one employer

def _text(html):
    return re.sub(r"\s+", " ", R.html_unescape(re.sub(r"<[^>]+>", " ", html))).strip()

def _place(html):
    """One location cell as "City, ST". The board writes "Hybrid Remote , Salt Lake City, Utah" over several lines."""
    loc = re.sub(r"\s+,", ",", _text(html)).replace("United States", "US")
    city, _, state = loc.rpartition(", ")
    return R.city_state(city, state) if city else loc

def _vague(label):
    """True for a location filter name that leaves its state out ("Office- Draper", "US Headquarters").
    The bare country is not one: a job filed under "United States" is shown as exactly that."""
    rest = re.sub(r"\b(?:USA|US)\b", " ", _place(label))
    return bool(re.search(r"\w", rest)) and not (R.placed(rest) or any(s in rest for s in R.STATE_NAMES))

def _gone(html):
    """True when a posting's address shows the company's list of open jobs instead: the posting has closed.
    Most templates print "The job listing no longer exists." over the list; bioMerieux's shows the list alone."""
    return "job listing no longer exists" in html or bool(re.search(r'<body class="[^"]*\bjv-page-jobs\b', html))

def _list(slug, **query):
    """Every row of one search on the board, [(title, location, url)]. No query is the whole board."""
    rows, seen, page = [], set(), 0
    while len(rows) < 6000:
        html = R.curl_text(f"{_SITE}/{slug}/search?" + urllib.parse.urlencode(dict(query, p=page)), accept="text/html")
        # An unknown company is answered with HTTP 200 and Jobvite's own support page.
        R.need(f"baseUrl: '/{slug}'" in html, "not this company's Jobvite career site")
        got = re.findall(_ROW % re.escape(slug), html, re.S)
        if not got:
            R.need("No results found" in html, "neither job rows nor 'No results found'")
            break
        fresh = [(_text(t), _place(l), _SITE + href) for href, t, l in got if _SITE + href not in seen]
        if not fresh: break                       # the same page again: stop rather than go round
        rows += fresh; seen.update(r[2] for r in fresh)
        # The page counts its own rows ("51-69 of 69"), which catches a template this pattern half reads.
        m = re.search(r"jv-pagination-text[^>]*>\s*(\d+)\s*-\s*(\d+)\s+of\s+(\d+)", html)
        if m: R.need(int(m.group(2)) - int(m.group(1)) + 1 == len(got), f"read {len(got)} rows of a page that says {m.group(1)}-{m.group(2)}")
        last = int(m.group(2)) >= int(m.group(3)) if m else len(got) < 50   # no count on the page: stop on a short one
        if last: break
        page += 1; time.sleep(0.3)
    return rows

def _posting(url):
    """(posting text, date posted, [places], foreign country) from one posting page, or None when it closed a moment ago."""
    html = R.curl_text(url, accept="text/html")
    body = re.search(r'class="jv-job-detail-description[^>]*>(.*?)(?:<div class="jv-job-detail-bottom-actions|</article>)', html, re.S)
    if not body and _gone(html): return None
    R.need(body, "not a posting page")
    # Most templates carry schema.org data. It has the posting date, and the country, which the list
    # leaves out ("Hybrid Remote, Cebu City, Cebu" would read as a remote job in the US). Imagine Learning's has none.
    posted = re.search(r'"datePosted"\s*:\s*"(\d{4}-\d\d-\d\d)', html)
    lands = set(re.findall(r'"addressCountry"\s*:\s*"([^"()]+)"', html))
    abroad = "/".join(sorted(lands)) if lands and not any(R.US_HINT.search(c) for c in lands) else None
    # The line under the title reads "Category | Place | Place", then on some boards the salary on a new line.
    meta = re.search(r'<p class="jv-job-detail-meta">(.*?)</p>', html, re.S)
    places = re.split(r"<span class=.jv-inline-separator.>\s*</span>", meta.group(1).split("<br")[0])[1:] if meta else []
    return body.group(1), posted.group(1) if posted else None, [_place(p) for p in places], abroad

def fetch(slug):
    """Return every open job as [(title, location, url, closes, degree, extra)]."""
    jobs = _list(slug)
    # A job in several places says only "3 Locations". The board's location filter knows which jobs are in
    # Utah: one request for the filter's names, then one search for each name that is a Utah place.
    home, unsure = {}, False
    if any(_MANY.search(loc) for _, loc, _ in jobs):
        try: names = [f.get("name") or "" for f in R.curl(f"{_SITE}/{slug}/search/facets?nl=1")["facets"]["locations"]]
        except Exception: names = None            # no filter to ask: the postings are asked instead, below
        # The names are the employer's own labels. Egnyte's Utah office is "Office- Draper", which a search
        # for Utah names cannot find, so a label that leaves its state out means the filter has not settled it.
        near = [n for n in names or [] if R.HOME.search(n)]
        unsure = names is None or len(near) > 25 or any(_vague(n) for n in names)
        for name in near[:25]:
            time.sleep(0.3)
            there = _list(slug, l=name)
            single = [loc for _, loc, _ in there if not _MANY.search(loc)]
            # A name the filter does not know is ignored and the whole board comes back, so the answer is
            # believed only when it is part of the board and every job in it that names its place names a Utah one.
            if len(there) < len(jobs) and all(R.HOME.search(loc) for loc in single):
                place = single[0] if len(set(single)) == 1 else name   # "Salt Lake City, UT" for the label "Salt Lake City"
                for _, _, url in there: home.setdefault(url, []).append(place)
            else: unsure = True
    rows, kept, lost = [], 0, 0
    for title, loc, url in jobs:
        many = _MANY.search(loc)
        if many and url in home: loc = "; ".join(dict.fromkeys(home[url])) + f" (one of {many.group(1)} locations)"
        # bioMerieux files its field jobs under "United States" and names the city in the title.
        named = _IN_TITLE.search(title) if loc == "US" else None
        if named and R.US_HINT.search(named.group(1)): loc = named.group(1).strip() + " (from the title)"
        # Where the filter could not settle it, a job in several places is judged as a Utah one until its
        # posting has been read, as the Workday reader does: an unleveled title is only kept near home.
        guess = many and unsure and url not in home
        judged = R.HOME_NAME if guess else loc
        text = posted = None
        if R.classify(title, judged, KIND) or R.experienced(title, judged, KIND):   # only read what will be published
            kept += 1
            if kept <= _CAP:
                time.sleep(0.3)
                seen = R.patient(_posting, url, slots=R._DETAIL_SLOTS)
                if seen is None: continue
                text, posted, places, abroad = seen
                # The posting names every place. It replaces the count when it agrees with it, and never
                # at the cost of the Utah place the filter found.
                if many and len(places) == int(many.group(1)) and (url not in home or R.HOME.search("; ".join(places))):
                    loc = "; ".join(dict.fromkeys(places))
                elif guess: lost += 1
                # the mark where() reads. A place in Utah is never marked, whatever the country field says.
                if abroad: loc = "; ".join(p if R.HOME.search(p) else f"{p} ({abroad}, abroad)" for p in loc.split("; "))
        rows.append((title, loc, url, None, R.degree_flag(text),
                     {"posted": posted, "yrs": R.min_years(text), "internal": False, "company": None}))
    notes = [f"could not tell where {lost} multi-location job(s) are"] if lost else []
    if kept > _CAP: notes.append(f"read details for the first {_CAP} of {kept} kept roles")
    if notes: R.PARTIAL[slug] = "; ".join(notes)
    return R._dedupe(rows)

def link_state(url):
    """'live', 'dead' or 'unknown' for one posting URL of this system. Return 'unknown' whenever unsure."""
    m = _LINK.search(url)
    if not m: return "unknown"
    try: code, html = R.curl_resp(url, accept="text/html")
    except Exception: return "unknown"
    if code != "200": return "unknown"
    if 'class="jv-job-detail-description' in html: return "live"
    # A closed posting answers 200 too, with this company's job list in its place.
    return "dead" if f"baseUrl: '/{m.group(1)}'" in html and _gone(html) else "unknown"

if __name__ == "__main__":
    for name, slug in EMPLOYERS.items():
        rows = fetch(slug)
        kept = [r for r in rows if R.classify(r[0], r[1], KIND) or R.experienced(r[0], r[1], KIND)]
        print(f"{name}: {len(rows)} jobs, {sum(1 for r in rows if R.HOME.search(r[1] or ''))} in Utah, {len(kept)} kept")
        for r in kept[:5]: print("   ", r[0], "|", r[1], "|", r[2], "|", r[3], "|", r[5])
