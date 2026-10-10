"""EY careers (careers.ey.com, an SAP SuccessFactors career site): its server-rendered search page is read,
25 jobs a page, once for each place the slug names ("Salt Lake City, UT|United States"). The list prints only
a job's first office ("McLean, VA +70 more"), so a job also gets the place whose search found it. Its own
page names every office and has the date and the text; that page is read for the roles that will be kept.
Plain public pages: no sign-in, no key, no visitor token. This is EY's board for experienced hires; its
student and new-graduate requisitions are on a separate Yello board (eyglobal.yello.co), not read here."""
import sys, os, re, json, time, datetime, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import refresh as R

KIND = "ey"
SLUG_HELP = ('the places to search careers.ey.com for, joined with "|", each written "City, ST" or as a country: '
             '"Salt Lake City, UT|United States"')
EMPLOYERS = {"EY": "Salt Lake City, UT|United States"}
INSTITUTIONS = set()  # names from EMPLOYERS that are public bodies, schools or hospitals, whose titles use "University", "Campus" or "Graduate" as plain description
AGGREGATOR = False    # True when one slug returns the jobs of many employers

SITE = "https://careers.ey.com"
MAX_PAGES = 90        # list pages for one slug, all its searches together (the site gives 25 jobs a page)
MAX_DETAILS = 60
SHOWN = 4             # places written out in a location; a national role is open in eighty offices
LINK = re.compile(r"https://careers\.ey\.com/(?:ey/)?job/(?:[^/?#]+/)?(\d+)/?(?:[?#].*)?$")
_US = ("US", "PR", "GU", "VI")                  # US territories are not abroad
_US_NAMES = ("united states", "usa", "us")
_STATES = set(R.STATE_NAMES.values())

def _text(markup):
    return re.sub(r"\s+", " ", R.html_unescape(re.sub(r"<[^>]+>", " ", markup or ""))).strip()

def _place(city, region, code):
    """"Salt Lake City, UT" from a city, a state and a two-letter country code. A place in another country is
    marked the way the Workday reader marks it, or "Mumbai, MH, IN" would read as a town in Indiana."""
    if code not in _US: return f"{city or code} ({code}, abroad)" if code else city
    place = R.city_state(city, region if code == "US" else code)
    # A US city with no state gets "US", or "Dublin" would read as foreign. So does one in a territory
    # ("San Juan, PR, US"), which the location rules do not know as a state.
    return place if region in _STATES and code == "US" else ", ".join(x for x in (place, "US") if x)

def _office(cell):
    """(place, country code) for one office as the site writes it: "Chicago, IL, US, 60606", "Lima, PE, 15073"."""
    t = [x.strip() for x in cell.split(",")]
    # The country is the last two-letter code, so "Toronto, ON, CA, M5H 0B3" is Canada and not California.
    i = max((k for k, x in enumerate(t) if re.fullmatch(r"[A-Z]{2}", x)), default=-1)
    if i < 0: return cell, ""
    return _place(t[0] if i else "", t[i - 1] if i > 1 else "", t[i]), t[i]

def _joined(places, more=0):
    """The first few places, then a count of the rest."""
    more = max(more, 0) + max(len(places) - SHOWN, 0)
    return "; ".join(places[:SHOWN] + ([f"+{more} more"] if more else []))

def _for_years(text):
    """The posting text with EY's own wording put in the words the years reader knows. Its section headings
    are "To qualify for the role, you must have" and "Ideally, you'll also have" (a wish list, not a bar),
    and its "no less than 2 - 4 years" is a floor, which would be read as the upper bound "less than 2"."""
    if not text: return text
    text = re.sub(r"(?i)\bto\s+qualify(?:\s+for\s+the\s+role)?,?\s+you\s+must\s+have\b:?", "Required qualifications", R.html_unescape(text))
    text = re.sub(r"(?i)\bideally,?\s+you(?:['\u2019]ll|\s+will|['\u2019]d|\s+would)(?:\s+also)?\s+have\b:?", "Preferred qualifications", text)
    return re.sub(r"(?i)\bnot?\s+less\s+than\b", "at least", text)

def _page(place, start=0):
    """One page of the search for a place (None: the whole site):
    (the site's count, [(job id, title, link, office, country, how many more offices)])."""
    query = {"q": "", "startrow": start}
    if place: query["locationsearch"] = f'"{place}"'       # in quotes, or "Salt Lake City" also finds "Cebu City"
    page = R.patient(R.curl_text, f"{SITE}/ey/search/?" + urllib.parse.urlencode(query), None, 60, "text/html")
    # The body class tells the results page from the home page, an error page or a bot check.
    R.need('class="coreCSB search-page' in page, "not a search results page")
    count, none = re.search(r"Results <b>[^<]*</b> of <b>([\d,]+)</b>", page), 'id="noresults"' in page
    R.need(count or none, "no result count")
    total = int(count.group(1).replace(",", "")) if count else 0
    # Under "no open positions matching" the site can list its most recent jobs instead. They are not results.
    if none: return total, []
    rows = []
    for tr in re.findall(r'<tr class="data-row.*?</tr>', page, re.S):
        a = re.search(r'<a\b(?=[^>]*class="jobTitle-link")[^>]*href="([^"]+)"[^>]*>(.*?)</a>', tr, re.S)
        R.need(a, "a job row without a title link")
        href = R.html_unescape(a.group(1))
        m = re.fullmatch(r"/ey/job/[^/?#]+/(\d+)/", href)
        R.need(m, "a job link that is not under /ey/job/")
        cell = re.search(r'<span class="jobLocation">(.*?)</span>', tr, re.S)
        office, _, rest = (cell.group(1) if cell else "").partition("<small")      # the rest is "+70 more"
        more = re.search(r"\+\s*(\d+)\s+more", rest)
        rows.append((m.group(1), _text(a.group(2)), SITE + href) + _office(_text(office)) + (int(more.group(1)) if more else 0,))
    return total, rows

def _open(page, jid):
    """True when a page is this job's own and still carries the posting."""
    # A job that has just closed keeps its page, with "The Job is no longer available." where the posting
    # was. One that is long gone is answered with the site's home page.
    return bool('class="coreCSB job-page' in page and 'itemprop="title"' in page
                and re.search(r'rel="canonical" href="[^"]*/%s/"' % jid, page))

def _posting(page, jid):
    """(every office, the date shown, the posting text) from one job's own page."""
    R.need(_open(page, jid), "not this job's posting")
    places = []
    for block in re.findall(r'<span itemprop="address"[^>]*>(.*?)</span>', page, re.S):
        f = {k: R.html_unescape(v).strip() for k, v in re.findall(r'<meta itemprop="(\w+)" content="([^"]*)"', block)}
        # An office abroad comes as one line, written as the list writes it ("London, GB, SE1 2AF").
        if f.get("addressCountry"): places.append(_place(f.get("addressLocality", ""), f.get("addressRegion", ""), f["addressCountry"]))
        elif f.get("streetAddress"): places.append(_office(f["streetAddress"])[0])
    # The date as the page shows it to a visitor ("Oct 8, 2026"), not the UTC timestamp in its metadata.
    m = re.search(r'data-careersite-propertyid="date"[^>]*>\s*([^<]+?)\s*<', page)
    try: posted = datetime.datetime.strptime(m.group(1), "%b %d, %Y").strftime("%Y-%m-%d") if m else None
    except ValueError: posted = None
    m = re.search(r'<span class="jobdescription">(.*?)(?:<div class="customPlugin|<p class="job-location"|<div class="clear clearfix">)', page, re.S)
    return [p for p in dict.fromkeys(places) if p], posted, m.group(1) if m else None

def fetch(slug):
    """Return every open job as [(title, location, url, closes, degree, extra)]."""
    places = [p.strip().strip('"') for p in (slug or "").split("|")]
    if not all(places): raise RuntimeError('ey: the slug is the places to search for, like "Salt Lake City, UT|United States"')
    jobs, asked, notes = {}, 0, []
    for place in places:
        if asked >= MAX_PAGES: notes.append(f'"{place}" was not searched (the {MAX_PAGES}-page limit was reached)'); continue
        found, total = {}, 0
        # A job that closes while the pages are read moves the rest up one and hides a row, so a short
        # read is swept once more before it is called short.
        for sweep in range(2):
            start = 0
            while asked < MAX_PAGES:
                total, rows = _page(place, start); asked += 1
                time.sleep(0.3)
                R.need(rows or start >= total, "no jobs on a results page")
                # A filter the site stopped understanding is ignored, and then jobs from everywhere come back.
                if R.US_HINT.search(place): R.need(sum(r[4] in _US for r in rows) * 2 >= len(rows), f'jobs that are not in "{place}"')
                for r in rows: found.setdefault(r[0], r[1:])
                start += len(rows)                       # by what arrived, whatever size the site's pages are
                if start >= total: break
            if len(found) >= total or asked >= MAX_PAGES: break
        if not total:
            # The site answers a misspelt place exactly as it does a place with no openings. While it lists
            # jobs elsewhere, nothing here is taken for a wrong place: an error, not every role reported closed.
            everywhere, _ = _page(None)
            if everywhere: raise RuntimeError(f'ey: no jobs for "{place}" while the site lists {everywhere:,} (is the place spelt as the site spells it?)')
        if len(found) < total:
            R.need(asked >= MAX_PAGES or len(found) >= total * 0.9, f'read {len(found)} of {total} jobs for "{place}"')   # a short read must never look like closures
            notes.append(f'{len(found)} of {total:,} jobs read for "{place}"')
        for jid, (title, url, office, code, more) in found.items():
            near = jobs.setdefault(jid, (title, url, office, more, []))[4]
            # The search vouches for its place whenever the one office printed does not already show it.
            if place != office and not (code in _US and place.lower() in _US_NAMES): near.append(place)
    # The place searched for is one of the offices the list only counts ("+70 more"), so it comes off the count.
    listed = [(title, _joined(list(dict.fromkeys(near + [office])), more - bool(near)), url, jid)
              for jid, (title, url, office, more, near) in jobs.items()]
    # Only the roles that will be published are worth a second request each, one at a time, home rows first.
    kept = [x for x in listed if R.classify(x[0], x[1], KIND) or R.experienced(x[0], x[1], KIND)]
    kept.sort(key=lambda x: not R.HOME.search(x[1]))
    if len(kept) > MAX_DETAILS: notes.append(f"read details for the first {MAX_DETAILS} of {len(kept)} kept roles")
    info, failed, streak = {}, 0, 0
    for _, _, url, jid in kept[:MAX_DETAILS]:
        if streak >= 3: failed += 1; continue    # the site is refusing: stop asking rather than retry sixty jobs
        try: info[jid] = _posting(R.patient(R.curl_text, url, None, 60, "text/html", slots=R._DETAIL_SLOTS), jid); streak = 0
        except R.OffLimits: raise
        except Exception: failed += 1; streak += 1   # the row is kept as listed rather than dropped
        time.sleep(0.2)
    if failed: notes.append(f"{failed} of {min(len(kept), MAX_DETAILS)} job pages could not be read")
    if notes: R.PARTIAL[slug] = "; ".join(notes)
    rows, unnamed = [], 0
    for title, loc, url, jid in listed:
        offices, posted, text = info.get(jid) or ([], None, None)
        if offices:
            # The page is also a check on the search: a job found by asking for "City, ST" must name it.
            unnamed += any(p not in offices for p in jobs[jid][4] if re.search(r", [A-Z]{2}$", p))
            # Home first, then the office the list printed, then the rest by name: the same string every week.
            # A national role near home is written as its list row is ("Salt Lake City, UT; Chicago, IL; +78 more").
            home = [p for p in offices if R.HOME.search(p)]
            rest = sorted((p for p in offices if p not in home), key=lambda p: (p != jobs[jid][2], p))
            loc = _joined(home + rest[:1], len(rest) - 1) if home and len(offices) > SHOWN else _joined(home + rest)
        rows.append((title, loc, url, None, R.degree_flag(text),          # the site states no closing date
                     {"posted": posted, "yrs": R.min_years(_for_years(text)), "internal": False, "company": None}))
    R.need(unnamed * 2 <= len(info), "job pages that do not name the place their search was for")
    return R._dedupe(rows)

def link_state(url):
    """'live', 'dead' or 'unknown' for one posting URL of this system. Return 'unknown' whenever unsure."""
    m = LINK.match(url or "")
    if not m: return "unknown"
    try: code, page = R.curl_resp(url, accept="text/html", timeout=60)
    except Exception: return "unknown"
    if code != "200": return "unknown"
    if _open(page, m.group(1)): return "live"
    # Both ways the site says a job is gone come with HTTP 200: its own page without the posting, or the home page.
    gone = "The Job is no longer available" in page if 'class="coreCSB job-page' in page else 'class="coreCSB home-page' in page
    return "dead" if gone else "unknown"

if __name__ == "__main__":
    for name, slug in EMPLOYERS.items():
        rows = fetch(slug)
        kept = [r for r in rows if R.classify(r[0], r[1], KIND) or R.experienced(r[0], r[1], KIND)]
        print(f"{name}: {len(rows)} jobs, {sum(1 for r in rows if R.HOME.search(r[1] or ''))} in Utah, {len(kept)} kept")
        for r in kept[:5]: print("   ", r[0], "|", r[1], "|", r[2], "|", r[3], "|", r[5])
