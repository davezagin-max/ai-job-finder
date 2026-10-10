"""KPMG US careers (kpmguscareers.com): the job search page fills itself from the site's own get-jobs.php, JSON
that carries the result cards as HTML, twelve to a request, with no sign-in and no token. The slug is one search
or several joined by "|", each a filter of that page as its address bar names it once it is picked
("location-filter=Salt Lake City, UT", "career-level-parents=Early Career") or keyword=words, and what they find
is merged. A card has no posting text, so each kept role's own page is read for it. The site states no dates."""
import sys, os, re, json, time, datetime, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import refresh as R

KIND = "kpmg"
SLUG_HELP = 'searches joined by "|", each one filter of kpmguscareers.com/job-search as its address bar names it (or keyword=words, in double quotes for an exact phrase): "location-filter=Salt Lake City, UT|career-level-parents=Early Career"'
EMPLOYERS = {"KPMG": "location-filter=Salt Lake City, UT|career-level-parents=Early Career"}
INSTITUTIONS = set()  # names from EMPLOYERS that are public bodies, schools or hospitals, whose titles use "University", "Campus" or "Graduate" as plain description
AGGREGATOR = False    # True when one slug returns the jobs of many employers

SITE = "https://www.kpmguscareers.com"
SEARCH = SITE + "/wp-content/themes/understrap-child-main/page-templates/google/get-jobs.php?"
POSTING = SITE + "/jobdetail/?jobId="
LINK = re.compile(r"https?://(?:www\.)?kpmguscareers\.com/jobdetail/\?jobId=(\d+)")
# The filters a slug may use, each taking a choice from the search page's checkboxes. The page has two more,
# season and clearance, but get-jobs.php ignores them when they come alone and answers with the whole board.
FILTERS = ("location-filter", "career-level-parents", "career-level", "practice-areas-parents", "practice-areas")
MAX_PAGES = 90        # list requests for one slug (1,080 jobs): with the filter page and sixty postings, about 150 in all
MAX_DETAILS = 60

def _text(markup):
    return re.sub(r"\s+", " ", R.html_unescape(re.sub(r"<[^>]+>", " ", markup or ""))).strip()

def _places(line):
    """"Austin, TX; Salt Lake City, UT" as a list. The site writes every office as "City, ST"."""
    out = []
    for p in (x.strip() for x in line.split(";")):
        # This is the firm's US site, so a place that named no state would still be a US one.
        if p and not re.search(r", [A-Z]{2}$", p) and not R.placed(p): p += ", US"
        if p and p not in out: out.append(p)
    return out

def _home_first(places):
    return "; ".join(sorted(places, key=lambda p: not R.HOME.search(p)))    # a stable sort: the rest keep the site's order

def _offered():
    """{filter name: the choices its checkboxes on the search page offer}."""
    page = R.curl_text(SITE + "/job-search/", accept="text/html", timeout=60)
    offered = {}
    for box in re.findall(r"<input\b[^>]*\bdata-menu=[^>]*>", page):
        menu, value = re.search(r'data-menu="([^"]+)"', box), re.search(r'\bvalue="([^"]*)"', box)
        if not (menu and value): continue
        # A ticked heading ("Early Career", with Internship under it) is sent under a name of its own.
        name = menu.group(1) + ("-parents" if "form-check-input-parent" in box else "")
        offered.setdefault(name, set()).add(R.html_unescape(value.group(1)).strip())
    R.need(offered.get("location-filter") and offered.get("career-level"), "the search page shows no filters")
    return offered

def _searches(slug):
    """[(filter name, value)] for the searches a slug asks for. A slug that is not one raises."""
    out, offered = [], None
    for part in (p.strip() for p in (slug or "").split("|")):
        if not part: continue                              # the site's own links end each value with a bar
        name, eq, value = (x.strip() for x in part.partition("="))
        if not (name and eq and value):
            raise RuntimeError(f"kpmg: '{part}' is not a search (write it like 'location-filter=Salt Lake City, UT')")
        if name != "keyword":
            # The search answers a value it does not know with no jobs at all, exactly like an office with
            # no openings, and a misspelt place with the jobs of whatever place it takes it for ("Utah" and
            # "Salt Lake Cty, UT" both work today). So a value must be one the page's own filter offers.
            if name not in FILTERS:
                raise RuntimeError(f"kpmg: the job search has no filter '{name}' (it has keyword, {', '.join(FILTERS)})")
            offered = offered or _offered()
            if value not in offered.get(name, ()):
                raise RuntimeError(f"kpmg: '{value}' is not a choice of the {name} filter on the job search page")
        # A keyword cannot be checked like that, and it is a loose net: words without quotes are searched
        # either-or through the whole posting ("audit" finds 531 of 879 jobs today), a bare number is a job id.
        out.append((name, value))
    if not out: raise RuntimeError("kpmg: the slug names no search")
    return out

def _card(card):
    """(job id, title, [places]) from one result card."""
    link = re.search(r'href="/jobdetail/\?jobId=(\d+)"', card)
    title = re.search(r'<div class="h4[^"]*">(.*?)</div>', card, re.S)
    # The list view's second line reads "Advisory | Austin, TX; Salt Lake City, UT".
    line = re.search(r'<div class="h5[^"]*">.*?</div>\s*<div class="text-xs[^"]*">(.*?)</div>', card, re.S)
    _, bar, places = _text(line.group(1)).partition("|") if line else ("", "", "")
    R.need(link and title and _text(title.group(1)) and bar, "a result card without a link, a title or its places")
    return link.group(1), _text(title.group(1)), _places(places)

def _page(name, value, n):
    """(the cards on page n of one search, how many results the search counts)."""
    # A filter's value is sent with a bar after it, as the page's own script sends it. Newest first is
    # asked for because it is a fixed order: "most relevant" has no reason to stay put between two pages.
    query = {"ajax": 1, name: value if name == "keyword" else value + "|", "order": "posted", "spage": n}
    try: d = json.loads(R.curl_text(SEARCH + urllib.parse.urlencode(query), timeout=60))
    except ValueError: raise RuntimeError("kpmguscareers.com did not answer in JSON") from None
    post = d.get("postings") if isinstance(d, dict) else None
    R.need(isinstance(post, dict) and isinstance(post.get("jobs"), str) and isinstance(post.get("size"), int), "no result list")
    cards = re.split(r'(?=<div class="search--item)', post["jobs"])[1:]
    # A page without cards has to say so in the site's own words. Anything else is a layout that changed.
    R.need(cards or "no jobs matched" in post["jobs"], "a results page with neither jobs nor the no-jobs notice")
    return [_card(c) for c in cards], post["size"]

def _posting(jid):
    """(the posting's text, every place it lists) from one job's own page."""
    page = R.curl_text(POSTING + jid, accept="text/html", timeout=60)
    # A job that is gone still answers 200, with a "Job Posting Not Found" page. A live page names its id.
    R.need(re.search(r'id="jd-jobid"[^>]*>\s*%s\s*<' % jid, page), "not this job's page")
    text = re.search(r'<div class="[^"]*\bjob-description\b[^"]*">(.*?)</div>\s*<div class="pb-4">', page, re.S)
    R.need(text and _text(text.group(1)), "no posting text")
    where = re.search(r'id="jd-location"[^>]*>(.*?)</p>', page, re.S)
    return text.group(1), _places(_text(where.group(1))) if where else []

def fetch(slug):
    """Return every open job as [(title, location, url, closes, degree, extra)]."""
    jobs, asked, notes = {}, 0, []
    for name, value in _searches(slug):
        cards, n, tries = [], 1, 1
        while asked < MAX_PAGES:
            if asked: time.sleep(0.3)
            got, size = R.patient(_page, name, value, n); asked += 1
            cards += got; n += 1
            if got and len(cards) < size: continue         # by the site's count, whatever its page size is
            # The search is read to its end. A job that is posted, closed or re-sorted meanwhile moves the
            # rest by one, so a card is read twice or not at all (seen today: 106 of 107, and all 107 two
            # seconds later). Fewer distinct cards than the site counts means one was missed, and a missed
            # job would be reported as closed: the search is read again, twice at most, and then it fails.
            distinct = len({(jid, tuple(places)) for jid, _, places in cards})
            if distinct == size: break
            R.need(tries < 3, f"read {distinct} of {size} results for {name}={value}")
            cards, n, tries = [], 1, tries + 1
        else:                                              # the requests ran out before the search ended
            notes.append(f"stopped at {MAX_PAGES} list requests with {len(cards)} results read for {name}={value}")
        if name == "location-filter":
            # The filter also finds a few jobs near the place, so not every card names it, but most do. A
            # filter the site no longer understood would be ignored, and then the whole board comes back.
            R.need(sum(value in places for _, _, places in cards) * 2 >= len(cards), f"jobs that are not in {value}")
        for jid, title, places in cards:
            # A job open in more than 49 offices is listed as two cards with half the offices on each, and
            # a search by place returns only the half that names it. The halves are put back together.
            known = jobs.setdefault(jid, (title, []))[1]
            known += [p for p in places if p not in known]
    # Every job here is at a US office, so one whose card named no place at all would still be "US".
    listed = [(jid, title, _home_first(places) or "US") for jid, (title, places) in jobs.items()]
    # Only the roles that will be published are worth a second request each, the ones near home first.
    kept = [x for x in listed if R.classify(x[1], x[2], KIND) or R.experienced(x[1], x[2], KIND)]
    kept.sort(key=lambda x: not R.HOME.search(x[2]))
    if len(kept) > MAX_DETAILS: notes.append(f"read details for the first {MAX_DETAILS} of {len(kept)} kept roles")
    pages, failed, streak = {}, 0, 0
    for jid, _, _ in kept[:MAX_DETAILS]:
        if streak >= 3: failed += 1; continue             # the site is refusing: stop asking rather than retry sixty jobs
        try: pages[jid] = R.patient(_posting, jid, slots=R._DETAIL_SLOTS); streak = 0
        except R.OffLimits: raise
        except Exception: failed += 1; streak += 1         # the row is kept as listed rather than dropped
        time.sleep(0.2)
    if failed: notes.append(f"{failed} of {min(len(kept), MAX_DETAILS)} posting pages could not be read")
    if notes: R.PARTIAL[slug] = "; ".join(notes)
    rows = []
    for jid, title, loc in listed:
        text, places = pages.get(jid) or (None, [])
        # No dates. The site shows none, and the posting page's structured data gives every job the first
        # and the last day of the current month ("Oct 1, 2026" to "Oct 31, 2026"), which says nothing.
        rows.append((title, _home_first(places) or loc, POSTING + jid, None, R.degree_flag(text),
                     {"posted": None, "yrs": R.min_years(text), "internal": False, "company": None}))
    return R._dedupe(rows)

def link_state(url):
    """'live', 'dead' or 'unknown' for one posting URL of this system. Return 'unknown' whenever unsure."""
    m = LINK.match(url or "")
    if not m: return "unknown"
    try: code, page = R.curl_resp(POSTING + m.group(1), accept="text/html", timeout=60)
    except Exception: return "unknown"
    if code != "200": return "unknown"
    # A posting that is gone answers 200 under the title "Job Posting Not Found". A live one names its id,
    # which a 200 from anything else (an error page, a bot check) does not.
    title = re.search(r"<title>(.*?)</title>", page, re.S)
    if title and "Job Posting Not Found" in title.group(1): return "dead"
    return "live" if re.search(r'id="jd-jobid"[^>]*>\s*%s\s*<' % m.group(1), page) else "unknown"

if __name__ == "__main__":
    for name, slug in EMPLOYERS.items():
        rows = fetch(slug)
        kept = [r for r in rows if R.classify(r[0], r[1], KIND) or R.experienced(r[0], r[1], KIND)]
        print(f"{name}: {len(rows)} jobs, {sum(1 for r in rows if R.HOME.search(r[1] or ''))} in Utah, {len(kept)} kept")
        for r in kept[:5]: print("   ", r[0], "|", r[1], "|", r[2], "|", r[3], "|", r[5])
