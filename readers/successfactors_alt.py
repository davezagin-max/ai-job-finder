"""SuccessFactors career sites, read from /sitemal.xml (that spelling): one public Google-Base RSS file, no key,
listing every open job with its title, location, link and whole posting text. On these sites /sitemap.xml is a
plain list of links, which is why the built-in "successfactors" kind cannot read them. The slug is the site's
host name ("jobs.nucor.com"). Posted and closing dates are only on a job's own page, read for the kept roles."""
import sys, os, re, json, time, datetime, urllib.parse
from html import unescape
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import refresh as R

KIND = "successfactors_alt"
SLUG_HELP = 'the host name of the career site, as its job links write it: "jobs.nucor.com"'
EMPLOYERS = {"Nucor": "jobs.nucor.com", "HF Sinclair": "careers.hfsinclair.com", "Union Pacific": "up.jobs"}
INSTITUTIONS = set()  # names from EMPLOYERS that are public bodies, schools or hospitals, whose titles use "University", "Campus" or "Graduate" as plain description
AGGREGATOR = False    # True when one slug returns the jobs of many employers

MAX_ROWS, MAX_DETAILS = 6000, 60
# A job link: the id is what the site goes by and the words before it are for show, but they have to be
# there: "/job/<id>/" alone is answered with the home page, exactly as a job that never existed is.
# A site that keeps several brands puts the brand's name before "/job/".
JOB = r"https://(?:%s)/(?:[\w-]+/)?job/[^/?#]+/(\d+)/?$"
# Only the sites named above are answered for: a job link here looks like many other systems' links.
LINK = re.compile(JOB % "|".join(re.escape(h) for h in EMPLOYERS.values()))
CANONICAL = r'<link rel="canonical" href="[^"]*/%s/"'      # a job page names its own id here, open or closed
_US = ("US", "PR", "GU", "VI", "AS", "MP")      # US territories are not abroad
_STATES = set(R.STATE_NAMES.values())
# Named so the row reads well. Six of these codes are also US states (CA, IN, DE, AR, CO, IL): standing where
# the feed writes the country, they are the country.
_COUNTRY = {"CA": "Canada", "MX": "Mexico", "GB": "United Kingdom", "IE": "Ireland", "DE": "Germany", "FR": "France",
            "NL": "Netherlands", "ES": "Spain", "IT": "Italy", "CH": "Switzerland", "SE": "Sweden", "PL": "Poland",
            "IN": "India", "CN": "China", "JP": "Japan", "KR": "South Korea", "SG": "Singapore", "PH": "Philippines",
            "AU": "Australia", "NZ": "New Zealand", "BR": "Brazil", "AR": "Argentina", "CO": "Colombia", "IL": "Israel",
            "AE": "United Arab Emirates", "ZA": "South Africa"}
_REMOTE = re.compile(r"\b(?:remote|virtual|work from home)\b", re.I)
_MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()

def _place(raw):
    """A feed location in the form the location rules read. The feed writes city, state, country code and
    postcode, and leaves out whichever a job lacks: "Brigham City, UT, US, 84302" becomes "Brigham City, UT",
    "Remote US, US" becomes "Remote, US", and a bare "CA" (anywhere in Canada) becomes "(Canada, abroad)"."""
    parts = [p.strip() for p in raw.replace("_", " ").split(",") if p.strip()]    # one city arrives as "West_Hazleton"
    if len(parts) > 1 and re.search(r"\d", parts[-1]): parts.pop()               # the postcode
    remote = any(_REMOTE.search(p) for p in parts)
    # One site writes "Virtual" where the country goes ("Indianapolis, IN, Virtual, 46201"). The state
    # before it says the job is American: without this, IN would be read as the country.
    code = "US" if len(parts) > 1 and _REMOTE.fullmatch(parts[-1]) and parts[-2] in _STATES else ""
    parts = [p for p in parts if not _REMOTE.search(p)]
    if not code:
        if not (parts and re.fullmatch(r"[A-Z]{2}", parts[-1])):
            return "Remote" if remote and not parts else " ".join(raw.split())    # no country code: passed on as written
        code = parts.pop()
        # A state code that is no country and has no state before it ("Lehi, UT") is a site that leaves
        # the country out. Reading it as a country would mark a job at home as one abroad.
        if code in _STATES and code not in _COUNTRY and not (parts and re.fullmatch(r"[A-Z]{2,3}", parts[-1])):
            parts.append(code); code = "US"
    state = parts.pop() if code in _US and parts and parts[-1] in _STATES else ""
    city = ", ".join(parts)
    if len(city) > 3 and city == city.upper(): city = city.title()                # one railroad writes "SALT LAKE"
    if code not in _US:
        # Marked in the words the location rules read: "Mississauga, ON, CA" would be taken for California.
        return f"{city or ('Remote' if remote else '')} ({_COUNTRY.get(code, code)}, abroad)".strip()
    place = ", ".join(x for x in (city, state or code) if x)                      # a US place with no state says "US"
    return "Remote, " + place if remote else place

def _tag(item, name):
    """The text of one element of a feed item, with its CDATA wrapper and entities undone."""
    m = re.search(rf"<{name}>(.*?)</{name}>", item, re.S)
    return unescape(re.sub(r"^<!\[CDATA\[|\]\]>$", "", m.group(1).strip())).strip() if m else ""

def _day(stamp):
    """The local calendar day of a stamp on a job page ("Thu Sep 24 07:00:00 UTC 2026"), or None."""
    m = re.fullmatch(r"\w{3} (\w{3}) (\d{1,2}) (\d\d):\d\d:\d\d UTC (\d{4})", (stamp or "").strip())
    if not m or m.group(1) not in _MONTHS: return None
    day = datetime.date(int(m.group(4)), _MONTHS.index(m.group(1)) + 1, int(m.group(2)))
    # The stamp is a bare date (00:00) or a midnight somewhere in the US written in UTC (04:00 to 08:00),
    # so the day it names is already the local one. Past noon it would be a midnight east of Greenwich,
    # which is the next day.
    return day + datetime.timedelta(days=1) if int(m.group(3)) >= 12 else day

def _dates(url, jid):
    """(posted, closes) from a job's own page, or None when the page is no longer an open posting."""
    page = R.curl_text(url, accept="text/html", timeout=40)
    # A job that closed since the feed was written still answers 200, with a page that carries no dates.
    if not re.search(CANONICAL % jid, page) or 'itemprop="datePosted"' not in page: return None
    meta = lambda prop: _day((re.search(r'<meta itemprop="%s" content="([^"]*)"' % prop, page) or [None, ""])[1])
    # datePosted is the "Date" the page shows. Every one read on 2026-10-09 fell in the four weeks before,
    # on old requisition numbers too, so the site appears to move it forward when a posting is renewed.
    posted, ends = meta("datePosted"), meta("validThrough")
    # validThrough is the midnight at which the posting comes down ("Fri Jan 01 05:00:00 UTC 2027" on the
    # 2027 academy jobs: New Year's midnight in the east). The last day it is up is the day before.
    return posted and posted.isoformat(), ends and (ends - datetime.timedelta(days=1)).isoformat()

def fetch(slug):
    """Return every open job as [(title, location, url, closes, degree, extra)]."""
    # A pasted link or a path is refused here, before anything is asked of anyone.
    host = slug or ""
    if not re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+", host): raise RuntimeError("the slug is not a career site's host name")
    xml = R.curl_text(f"https://{host}/sitemal.xml", accept="text/xml", timeout=90)   # one file, up to a few megabytes
    R.need(re.match(r"\s*(?:<\?xml[^>]*\?>\s*)*<rss\b", xml) and "<channel>" in xml, "not an RSS feed")
    R.need(xml.rstrip().endswith("</rss>"), "the feed was cut short")
    items, notes = re.findall(r"<item>(.*?)</item>", xml, re.S), []
    if len(items) > MAX_ROWS:
        notes.append(f"read the first {MAX_ROWS:,} of {len(items):,} jobs"); items = items[:MAX_ROWS]
    listed = []
    for item in items:
        title, raw, url = _tag(item, "title"), _tag(item, "g:location"), _tag(item, "link")
        m = re.match(JOB % re.escape(host), url)
        # Links on another host mean the name given is not the site's own, or the reply is some other site's.
        R.need(title and m, "a job without a title, or with a link that is not on this site")
        if raw and title.endswith(f"({raw})"): title = title[:-len(raw) - 2]      # every title repeats its location
        listed.append((" ".join(title.split()), _place(raw), url, m.group(1), _tag(item, "description")))
    # Only the roles that will be published are worth a second request each, one at a time, home first.
    kept = [x for x in listed if R.classify(x[0], x[1], KIND) or R.experienced(x[0], x[1], KIND)]
    kept.sort(key=lambda x: not R.HOME.search(x[1]))
    if len(kept) > MAX_DETAILS: notes.append(f"read dates for the first {MAX_DETAILS} of {len(kept)} kept roles")
    dates, failed, streak = {}, 0, 0
    for _, _, url, jid, _ in kept[:MAX_DETAILS]:
        if streak >= 3: failed += 1; continue    # the site is refusing: stop asking rather than retry sixty jobs
        try: found = R.patient(_dates, url, jid, slots=R._DETAIL_SLOTS)
        except R.OffLimits: raise
        except Exception: found = None; streak += 1
        else: streak = 0
        if found: dates[url] = found
        else: failed += 1                        # the row is kept as listed rather than dropped
        time.sleep(0.2)
    if failed: notes.append(f"{failed} of {min(len(kept), MAX_DETAILS)} job pages could not be read for their dates")
    if notes: R.PARTIAL[slug] = "; ".join(notes)
    rows = []
    for title, loc, url, _, text in listed:
        posted, closes = dates.get(url) or (None, None)
        # The feed's own g:expiration_date is the same day on every job (thirty days from today), so it is
        # not read as a closing date.
        rows.append((title, loc, url, closes, R.degree_flag(text),
                     {"posted": posted, "yrs": R.min_years(text), "internal": False, "company": None}))
    return R._dedupe(rows)

def link_state(url):
    """'live', 'dead' or 'unknown' for one posting URL of this system. Return 'unknown' whenever unsure."""
    m = LINK.match(url or "")
    if not m: return "unknown"
    try: code, page = R.curl_resp(url, accept="text/html", timeout=40)
    except Exception: return "unknown"
    if code != "200": return "unknown"
    mine = re.search(CANONICAL % m.group(1), page)
    # An open posting carries the day it was posted, for search engines to read.
    if 'itemprop="datePosted"' in page: return "live" if mine else "unknown"
    # A closed one keeps its page and its 200: the text is replaced by one line saying the position has
    # been filled, and the page asks not to be indexed. An id the site has never had is answered, also
    # with a 200, by the home page. Anything else is not an answer.
    if mine and '<meta name="robots" content="noindex"' in page: return "dead"
    return "dead" if re.search(r'<body class="[^"]*\bhome-page\b', page) else "unknown"

if __name__ == "__main__":
    for name, slug in EMPLOYERS.items():
        rows = fetch(slug)
        kept = [r for r in rows if R.classify(r[0], r[1], KIND) or R.experienced(r[0], r[1], KIND)]
        print(f"{name}: {len(rows)} jobs, {sum(1 for r in rows if R.HOME.search(r[1] or ''))} in Utah, {len(kept)} kept")
        for r in kept[:5]: print("   ", r[0], "|", r[1], "|", r[2], "|", r[3], "|", r[5])
