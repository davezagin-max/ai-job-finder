"""Avature career site read through its keyword search (the Siemens layout, which the "avature" kind does
not parse): the server-rendered result pages are read, six jobs a page. The slug is "host/portal|keyword",
the keyword being what a person would type in the site's search box ("Utah" finds every posting that
names Utah). A job listed as "Multiple Locations" names its places only on its own page, which is also
where the posted date, the work mode ("Remote only") and the text are, so that page is read for the roles
that would be kept."""
import sys, os, re, json, time, datetime, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import refresh as R

KIND = "avature_search"
SLUG_HELP = '"host/portal|keyword": the address before /SearchJobs, then the search word, for example "jobs.siemens.com/en_US/externaljobs|Utah"'
EMPLOYERS = {"Siemens": "jobs.siemens.com/en_US/externaljobs|Utah"}
INSTITUTION = False   # True for public bodies, schools and hospitals, whose titles use "University", "Campus" or "Graduate" as plain description
AGGREGATOR = False    # True when one slug returns the jobs of many employers

PER_PAGE = 6          # the site's own page size; asking for more is ignored
MAX_PAGES = 40        # 240 jobs: a keyword that finds more should be narrowed, not walked
MAX_DETAILS = 60
LINK = re.compile(r"https://[^/]+/.*/JobDetail/[^?#]*\d+/?$")
_US = {"us", "usa", "united states", "united states of america"}
_MONTHS = {m: i + 1 for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}
_HIDDEN = re.compile(r"\s*(?:multiple locations?)?\s*$", re.I)

def _text(markup):
    return re.sub(r"\s+", " ", R.html_unescape(re.sub(r"<[^>]+>", " ", markup or ""))).strip()

def _place(city, state, country):
    """"Salt Lake City, UT" from a city, a state and a country. A place in another country is marked the
    way the Workday reader marks it, so the location rules never take it for a US one."""
    loc = R.city_state(city, state)
    if country.lower() in _US: return loc if re.search(r", [A-Z]{2}$", loc) else ", ".join(x for x in (loc, "US") if x)
    return f"{loc or country} ({country}, abroad)" if country else loc

def _site(line):
    """One line of a job page's location list: "Boise - Idaho - United States of America" as "Boise, ID"."""
    p = [x.strip() for x in line.split(" - ")]
    if len(p) > 2: return _place(" - ".join(p[:-2]), p[-2], p[-1])
    if len(p) == 2 and p[1].lower() in _US: return _place(p[0], "", p[1])
    return ", ".join(p)                                   # two words do not say which is the country: left as written

def _rows(page):
    """[(title, location, url)] for the jobs on one result page."""
    out = []
    for art in re.findall(r'<article class="article article--result.*?</article>', page, re.S):
        a = re.search(r'<a class="link" href="([^"]+/JobDetail/[^"]+)"[^>]*>(.*?)</a>', art, re.S)
        if not a: continue
        part = lambda name: _text((re.search(r'<span class="list-item-job%s">(.*?)</span>' % name, art, re.S) or [None, ""])[1])
        loc = _place(part("City"), part("State"), part("Country"))
        if not loc: loc = _text((re.search(r'<span class="list-item-location">(.*?)</span>', art, re.S) or [None, ""])[1])
        out.append((_text(a.group(2)), loc, R.html_unescape(a.group(1)).strip()))
    return out

def _field(head, label):
    """One labelled value from the top of a job page: "Work mode" gives "Remote only"."""
    m = re.search(r'field__label"[^>]*>\s*%s\s*</div>\s*<div[^>]*>(.*?)</div>' % re.escape(label), head, re.S)
    return _text(m.group(1)) if m else ""

def _detail(url):
    """(places, posted date, posting text) from one job's own page."""
    page = R.curl_text(url, accept="text/html", timeout=60)
    arts = re.findall(r'<article class="article article--details.*?</article>', page, re.S)
    R.need(arts, "not a job page")
    block = re.search(r'<ul class="[^"]*list--locations[^"]*">(.*?)</ul>', arts[0], re.S)
    places = [_site(_text(li)) for li in re.findall(r"<li[^>]*>(.*?)</li>", block.group(1), re.S)] if block else []
    places = [p for p in dict.fromkeys(places) if p]
    R.need(places, "no locations on the job page")       # a page read without them must not pass for a job with no place
    # "Remote only" is a work mode of its own on these pages, and such a job gives the whole country as
    # its place: "Any Siemens location in United States of America".
    if re.match(r"remote\b", _field(arts[0], "Work mode"), re.I):
        anywhere = [p for p in places if p.lower() in _US]
        places = [p for p in places if p.lower() not in _US]
        if anywhere: places.append("Remote, US")
        elif R.where("; ".join(places)): places.append("Remote")
    m = re.match(r"(\d{1,2})-([A-Za-z]{3})-(\d{4})$", _field(arts[0], "Posted since"))
    posted = f"{m.group(3)}-{_MONTHS[m.group(2).lower()]:02d}-{int(m.group(1)):02d}" if m and m.group(2).lower() in _MONTHS else None
    return places, posted, " ".join(arts[1:]) or None

def fetch(slug):
    """Return every open job as [(title, location, url, closes, degree, extra)]."""
    base, _, word = (x.strip() for x in slug.partition("|"))
    R.need(base and word, 'slug is "host/portal|keyword"')
    search = f"https://{base}/SearchJobs/{urllib.parse.quote(word, safe='')}/?folderRecordsPerPage={PER_PAGE}&folderOffset="
    found, total = {}, None
    # The search sorts ties unstably, so paging can list one job twice and skip another: a short read
    # is swept once more before it is called short.
    for sweep in range(2):
        off = 0
        while off < PER_PAGE * MAX_PAGES:
            page = R.curl_text(search + str(off), accept="text/html", timeout=45)
            m = re.search(r'aria-label="(\d[\d,]*) results"', page)
            R.need(m or "No results match your search" in page, "no result count")      # an error page has neither
            if total is None: total = int(m.group(1).replace(",", "")) if m else 0
            got = _rows(page)
            R.need(got or not total or off, "no jobs on the first results page (layout changed?)")
            for title, loc, url in got: found.setdefault(url, (title, loc))
            off += PER_PAGE
            if not got or off >= total: break
            time.sleep(0.3)
        if len(found) >= min(total, PER_PAGE * MAX_PAGES): break
        time.sleep(0.3)
    if total > PER_PAGE * MAX_PAGES: R.PARTIAL[slug] = f"read {len(found)} of {total} jobs (narrow the keyword)"
    elif len(found) < total:
        R.need(len(found) >= total * 0.9, f"read {len(found)} of {total} jobs")         # a short read must never look like closures
        R.PARTIAL[slug] = f"{len(found)} of {total} jobs read (the site's paging skips some)"
    # A "Multiple Locations" row is tested as if it were at home, the most permissive reading, because
    # only its own page says whether one of its places is.
    keep = lambda t, l: R.classify(t, l, KIND) or R.experienced(t, l, KIND)
    wanted = [u for u, (t, l) in found.items() if keep(t, R.HOME_NAME if _HIDDEN.match(l) else l)]
    # No more than sixty pages are read: first the rows that cannot be placed without theirs, then nearest home.
    near = {"home": 0, "remote": 1, "elsewhere": 2}
    wanted.sort(key=lambda u: -1 if _HIDDEN.match(found[u][1]) else near.get(R.where(found[u][1]), 3))
    if len(wanted) > MAX_DETAILS:
        R.PARTIAL[slug] = f"read details for the first {MAX_DETAILS} of {len(wanted)} kept roles"
    info, unplaced, failed = {}, [], 0
    for url in wanted[:MAX_DETAILS]:
        try: info[url] = R.patient(_detail, url, slots=R._DETAIL_SLOTS)
        except R.OffLimits: raise
        except Exception:
            failed += 1                                   # a located row is kept as listed rather than dropped
            if _HIDDEN.match(found[url][1]): unplaced.append(found[url][0])
        time.sleep(0.3)
    # Without its page a "Multiple Locations" row cannot be placed, and guessing would make it look closed
    # one week and new the next. Treat the board as unread today instead, as the Workday reader does.
    if unplaced: raise RuntimeError(f"{len(unplaced)} job page(s) could not be read, e.g. '{unplaced[0][:40]}'")
    if failed: R.PARTIAL[slug] = f"{failed} of {min(len(wanted), MAX_DETAILS)} job pages could not be read"
    rows = []
    for url, (title, loc) in found.items():
        places, posted, text = info.get(url) or ([], None, None)
        rows.append((title, "; ".join(places) or loc, url, None, R.degree_flag(text),      # no closing date is stated
                     {"posted": posted, "yrs": R.min_years(text), "internal": False, "company": None}))
    return R._dedupe(rows)

def link_state(url):
    """'live', 'dead' or 'unknown' for one posting URL of this system. Return 'unknown' whenever unsure."""
    # Only the sites read here: other Avature sites (Bloomberg, Deloitte) have their own checks in refresh.py
    if not LINK.match(url or "") or urllib.parse.urlsplit(url).netloc not in {s.split("/")[0] for s in EMPLOYERS.values()}: return "unknown"
    try: code, page = R.curl_resp(url, accept="text/html", timeout=60)
    except Exception: return "unknown"
    if code == "404": return "dead"                       # a job that is gone answers 404 "Page not found"
    return "live" if code == "200" and "article--details" in page else "unknown"

if __name__ == "__main__":
    for name, slug in EMPLOYERS.items():
        rows = fetch(slug)
        kept = [r for r in rows if R.classify(r[0], r[1], KIND) or R.experienced(r[0], r[1], KIND)]
        print(f"{name}: {len(rows)} jobs, {sum(1 for r in rows if R.HOME.search(r[1] or ''))} in Utah, {len(kept)} kept")
        for r in kept[:5]: print("   ", r[0], "|", r[1], "|", r[2], "|", r[3], "|", r[5])
