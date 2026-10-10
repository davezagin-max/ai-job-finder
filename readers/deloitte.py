"""Deloitte US (apply.deloitte.com, an Avature portal): the careers site's own keyword search, whose result
pages come ready-made from the server, ten jobs a page. The slug is the searches to run, joined with ";"
("Salt Lake City;2027"): each is what a person would type in the search box, and a search that finds nothing
raises, because the site answers a misspelt word and a dead one alike. Most rows say "Multiple Locations":
the places, the dates and the text are on the job's own page, read for the roles that would be kept."""
import sys, os, re, json, time, datetime, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import refresh as R

KIND = "deloitte"
SLUG_HELP = 'the searches to run on apply.deloitte.com, joined with ";", each as typed in its search box: "Salt Lake City;2027"'
EMPLOYERS = {"Deloitte": "Salt Lake City;2027"}
INSTITUTIONS = set()  # names from EMPLOYERS that are public bodies, schools or hospitals, whose titles use "University", "Campus" or "Graduate" as plain description
AGGREGATOR = False    # True when one slug returns the jobs of many employers

SEARCH = "https://apply.deloitte.com/en_US/careers/SearchJobs/"
PER_PAGE = 10         # the site's own page size; asking for more is ignored
MAX_PAGES = 40        # result pages for one search. 400 jobs: a search that finds more ("Associate" finds about a thousand) should be narrowed, not walked
MAX_LIST = 90         # result pages for one slug, which with the job pages keeps a run to about 150 requests
MAX_DETAILS = 60
_HIDDEN = re.compile(r"\s*(?:multiple locations?)?\s*$", re.I)
_US = {"united states", "united states of america", "usa", "us"}
_MONTHS = "jan feb mar apr may jun jul aug sep oct nov dec".split()
# "Recruiting for this role ends on October 11, 2026", "... on 10/25/2026", "... on 12/07/26", "... on Thursday, December 31st, 2026"
_ENDS = re.compile(r"Recruiting\s*for\s*this\s*role\s*ends\s*on\W*(?:[a-z]+day\W*)?"
                   r"(?:(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*(\d{4}|\d{2})(?!\d)|([a-z]{3})[a-z]*\.?\s*(\d{1,2})(?:st|nd|rd|th)?\W*(\d{4}))", re.I)

def _text(markup):
    return re.sub(r"\s+", " ", R.html_unescape(re.sub(r"<[^>]+>", " ", markup or ""))).strip()

def _meta(page, name):
    """What an Avature page says about itself in its head: which page it is, and the search it ran."""
    m = re.search(r'<meta name="avature\.%s" content="([^"]*)"' % re.escape(name), page)
    return _text(m.group(1)) if m else ""

def _place(s):
    """"Salt Lake City, Utah, United States" as "Salt Lake City, UT". A place in another country is marked the
    way the Workday reader marks it, so the location rules never take it for a US one."""
    p = [x.strip() for x in s.split(",")]
    if len(p) != 3: return s                              # "Multiple Locations": only the job's own page names them
    city, state, country = p
    if country.lower() not in _US: return f"{city} ({country}, abroad)"
    state = R.STATE_NAMES.get(state, state)               # looked up as written: "District of Columbia"
    return R.city_state(city, state) if re.fullmatch(r"[A-Z]{2}", state) else f"{city}, {state}, US"   # "San Juan, Puerto Rico, US"

def _page(word, off):
    """One page of one search: ([(title, location, url)], the site's count of matches, whether that count is "999+")."""
    page = R.curl_text(f"{SEARCH}{urllib.parse.quote(word, safe='')}/?jobOffset={off}", accept="text/html", timeout=60)
    # The page repeats the search it ran. An error page, a sign-in page or a bot check does not, and neither
    # would a site that had stopped reading the word from the address and listed every job it has.
    R.need(_meta(page, "portal.page") == "SearchJobs" and _meta(page, "portallist.search").lower() == word.lower(),
           "not the results of this search")
    count = re.search(r"jobListTotalRecords['\"]>\s*(\d+)(\+?)", page)
    R.need(count, "no job count")
    rows = []
    for art in re.findall(r'<article class="article--result.*?</article>', page, re.S):
        a = re.search(r'<a\b[^>]*href="([^"]+/JobDetail/[^"]+)"[^>]*>(.*?)</a>', art, re.S)
        R.need(a and _text(a.group(2)), "a result without a title or a link")
        # Under the title: member firm | legal entity | place. Anything last that is not a place is not taken for one.
        spans = [_text(x) for x in re.findall(r"<span>(.*?)</span>", art, re.S)]
        loc = spans[-1] if spans and ("," in spans[-1] or _HIDDEN.match(spans[-1])) else ""
        rows.append((_text(a.group(2)), _place(loc), R.html_unescape(a.group(1)).strip()))
    return rows, int(count.group(1)), bool(count.group(2))

def _said(text):
    """The day the posting's own sentence gives as the end of recruiting, or None."""
    # Tags go without leaving a space behind: the date is often split across them ("1<b>0</b>/25/2026").
    m = _ENDS.search(R.html_unescape(re.sub(r"<[^>]+>", "", text or "")))
    if not m: return None
    try:
        if m.group(1): month, day, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        else: month, day, year = _MONTHS.index(m.group(4).lower()) + 1, int(m.group(5)), int(m.group(6))
        return datetime.date(year + 2000 if year < 100 else year, month, day).isoformat()
    except ValueError: return None

def _closes(text, valid):
    """The last day to apply: the posting's own sentence, else the day before the site takes the posting down."""
    # validThrough is midnight as that day begins: the campus postings that say "ends on October 11, 2026"
    # carry 2026-10-12T00:00. So without the sentence, the day before it is the last day.
    try: last = (datetime.date.fromisoformat(valid) - datetime.timedelta(days=1)).isoformat() if valid else None
    except ValueError: last = None
    # Either day counts only while it is still ahead and inside the posting's life. A posting is extended
    # without its text being touched ("ends on 09/30/2026", still open in October), and a date that has
    # passed on a job the site still lists would hide an open job.
    today = datetime.date.today().isoformat()
    return next((d for d in (_said(text), last) if d and today <= d <= (valid or d)), None)

def _detail(url):
    """(places, posted date, closing date, posting text) from one job's own page, or None for a job that is gone."""
    code, page = R.curl_resp(url, accept="text/html", timeout=60)
    # A job taken down while the search still lists it answers 404 on the site's own error page.
    if code == "404" and _meta(page, "portal.page") == "Error": return None
    if code != "200": raise RuntimeError(f"HTTP {code} from apply.deloitte.com")
    head = re.search(r'<article class="article article--details.*?</article>', page, re.S)
    R.need(head and _meta(page, "portal.page") == "JobDetail", "not a job page")
    places = [_place(_text(p)) for p in re.findall(r'<p class="paragraph">(.*?)</p>', head.group(0), re.S)]
    R.need(places, "a job page without its places")
    # The dates and the text are in the record the page carries for search engines. It carries two, one
    # from the site's template and one from Avature itself; whichever parses is read.
    ld = {}
    for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S):
        try: d = json.loads(block)
        except ValueError: continue
        if isinstance(d, dict) and d.get("@type") == "JobPosting":
            for k, v in d.items(): ld.setdefault(k, v)
    day = lambda v: (re.match(r"\d{4}-\d{2}-\d{2}", str(v or "")) or [None])[0]     # the site's own calendar day
    text = ld.get("description") if isinstance(ld.get("description"), str) else None
    return list(dict.fromkeys(places)), day(ld.get("datePosted")), _closes(text, day(ld.get("validThrough"))), text

def fetch(slug):
    """Return every open job as [(title, location, url, closes, degree, extra)]."""
    words = list(dict.fromkeys(w for w in (re.sub(r"\s+", " ", x).strip() for x in (slug or "").split(";")) if w))
    if not words: raise RuntimeError('deloitte: the slug is the searches to run, like "Salt Lake City;2027"')
    # Each search gets an even share of the result pages, so a long slug stays inside the request budget.
    limit = min(MAX_PAGES, MAX_LIST // len(words))
    if not limit: raise RuntimeError(f"deloitte: {len(words)} searches in the slug is more than one run can read")
    found, near, notes = {}, set(), []
    for word in words:
        hits, total, more, asked = {}, 0, False, 0
        # The search sorts ties unstably, so paging can list one job twice and skip another: a short read
        # is swept once more before it is called short.
        for _ in range(2):
            off = 0
            while asked < limit:
                if found or hits: time.sleep(0.3)
                rows, total, more = R.patient(_page, word, off); asked += 1
                # Nothing found is a wrong slug as far as anyone can tell: a misspelt word gets the same answer,
                # and Deloitte always has postings for a live one. Raising also keeps last week's rows from
                # being reported as closed.
                if not total: raise RuntimeError(f'deloitte: the search "{word}" finds no jobs (misspelt, or out of season?)')
                R.need(rows or off, f"{total} jobs counted and none listed")
                for title, loc, url in rows: hits.setdefault(url, (title, loc))
                off += PER_PAGE
                if len(rows) < PER_PAGE or (not more and off >= total): break
            if more or len(hits) >= total or asked >= limit: break
        if more or (asked >= limit and len(hits) < total):
            notes.append(f'read the first {len(hits)} of {"1,000 or more" if more else total} jobs for "{word}" (narrow the search)')
        elif len(hits) < total:
            R.need(len(hits) >= total * 0.9, f'read {len(hits)} of {total} jobs for "{word}"')    # a short read must never look like closures
            notes.append(f'{len(hits)} of {total} jobs read for "{word}" (the site\'s paging skips some)')
        for url, row in hits.items(): found.setdefault(url, row)
        if R.HOME.search(word): near.update(hits)         # a search for a place near home: its rows are read first
    # A "Multiple Locations" row is tested as if it were at home, the most permissive reading, because only
    # its own page says whether one of its places is.
    keep = lambda t, l: R.classify(t, l, KIND) or R.experienced(t, l, KIND)
    wanted = [u for u, (t, l) in found.items() if keep(t, R.HOME_NAME if _HIDDEN.match(l) else l)]
    # When the cap cuts the reading short: the home search's rows first, then the roles kept wherever they
    # are, the newest requisition first (its number ends the link), so the same rows are read every week.
    # Being found by the home search only decides the order. It is never written down as a place: the
    # search also matches things no page shows ("Utah" finds jobs whose pages name no place in Utah).
    number = lambda u: int((re.search(r"(\d+)/?$", u) or [0, 0])[1])
    wanted.sort(key=lambda u: (u not in near and not R.HOME.search(found[u][1]), not keep(*found[u]), -number(u)))
    if len(wanted) > MAX_DETAILS: notes.append(f"read details for the first {MAX_DETAILS} of {len(wanted)} kept roles")
    info, failed = {}, 0
    for url in wanted[:MAX_DETAILS]:
        try: info[url] = R.patient(_detail, url, slots=R._DETAIL_SLOTS)
        except R.OffLimits: raise
        except Exception:
            # Without its page a "Multiple Locations" row cannot be placed, and guessing would make it look
            # closed one week and new the next. Treat the board as unread today instead, as the Workday
            # reader does, and stop asking a site that is not answering.
            if _HIDDEN.match(found[url][1]): raise RuntimeError(f"a job page could not be read ('{found[url][0][:40]}')")
            failed += 1                                   # a located row is kept as listed rather than dropped
        time.sleep(0.2)
    if failed: notes.append(f"{failed} of {min(len(wanted), MAX_DETAILS)} job pages could not be read")
    # Every page read today names the day it was posted. None doing so is the pages changing shape, which
    # would otherwise pass as rows that simply have no dates and no text.
    if any(info.values()) and not any(got[1] for got in info.values() if got): notes.append("the job pages no longer give their dates")
    # A job or two can close between the list and its page. Many at once is the site changing its links,
    # and dropping them all would report every kept role as closed.
    gone = {u for u, got in info.items() if got is None}
    R.need(len(gone) <= max(2, len(info) // 10), f"{len(gone)} of {len(info)} job pages answer 404")
    if notes: R.PARTIAL[slug] = "; ".join(notes)
    rows = []
    for url, (title, loc) in found.items():
        if url in gone: continue
        places, posted, closes, text = info.get(url) or ([], None, None, None)
        places.sort(key=lambda p: not R.HOME.search(p))   # a stable sort: a national role lists up to eighty offices, and the one here is the point
        # A row whose page was not read stays as the site lists it, "Multiple Locations" included.
        rows.append((title, "; ".join(places) or loc, url, closes, R.degree_flag(text),
                     {"posted": posted, "yrs": R.min_years(text), "internal": False, "company": None}))
    return R._dedupe(rows)

# No link_state here: refresh.py already checks these links itself (DELOITTE_LINK). A posting that is gone
# answers 404 with the title "Error", a live one 200 with its own title, and that is what it reads.

if __name__ == "__main__":
    for name, slug in EMPLOYERS.items():
        rows = fetch(slug)
        kept = [r for r in rows if R.classify(r[0], r[1], KIND) or R.experienced(r[0], r[1], KIND)]
        print(f"{name}: {len(rows)} jobs, {sum(1 for r in rows if R.HOME.search(r[1] or ''))} in Utah, {len(kept)} kept")
        for r in kept[:5]: print("   ", r[0], "|", r[1], "|", r[2], "|", r[3], "|", r[5])
