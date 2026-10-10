"""iCIMS classic career portals ("careers-<employer>.icims.com"): the server-rendered search page,
/jobs/search?pr=N&in_iframe=1, which carries the locations the sitemap lacks. The slug is the portal's
host, optionally followed by "|location to assume" for the rows a portal lists without a place.
Each kept role's own page is then read for its text, its dates and, where the list gave no place, the
place (the schema.org data the page embeds)."""
import sys, os, re, json, time, datetime, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import refresh as R

KIND = "icims_search"
SLUG_HELP = ('the portal\'s host, e.g. careersus-teleperformance.icims.com; add "|Ogden, UT (check posting)" '
             "to give rows the page lists without a location an assumed one")
# Cotiviti and America First Credit Union are on this system too. They have cards on the board, so they
# are listed in refresh.py's BOARDS under this kind.
EMPLOYERS = {"Teleperformance USA": "careersus-teleperformance.icims.com",
             "Odyssey Systems": "careers-odysseyconsult.icims.com",
             # Peraton (careers-peraton.icims.com) reads fine too, but it is 1,500 jobs for nine in Utah.
             # HealthEquity's list shows a title and nothing else, so every row starts from this place and
             # a kept row then takes the one its own page gives (most say Remote).
             "HealthEquity": "careers-healthequity.icims.com|Draper, UT or US remote (check posting)",
             "Utah State University": "careers-usu.icims.com",
             "Salt Lake County": "careers-slco.icims.com",
             "Utah Retirement Systems (URS and PEHP)": "careers-urs.icims.com"}
INSTITUTION = False   # most iCIMS employers are companies; the public bodies among them are named below
AGGREGATOR = False
# A university and a county title jobs "Graduate Program Coordinator" and "Campus Events Assistant".
# load_readers() adds these names to the script's own INSTITUTIONS, which is what scan() judges them by.
INSTITUTIONS = {"Utah State University", "Salt Lake County", "Utah Retirement Systems (URS and PEHP)"}

MAX_PAGES, MAX_DETAILS = 80, 60                              # keeps one employer under about 150 requests
_CARD  = re.compile(r'<li\b[^>]*\bclass="[^"]*\biCIMS_JobCardItem\b[^"]*"[^>]*>(.*?)</li>', re.S)
_LINK  = re.compile(r'<a\b[^>]*\bhref="(https://[^"/]+/jobs/\d+/[^"/?#]*/job)[^"]*"[^>]*>(.*?)</a>', re.S)
_HEAD  = re.compile(r'<span class="sr-only field-label">([^<]*)</span>\s*<span[^>]*>(.*?)</span>', re.S)
_TAG   = re.compile(r'<dt class="iCIMS_JobHeaderField">(.*?)</dt>\s*<dd class="iCIMS_JobHeaderData">(.*?)</dd>', re.S)
_PAGE  = re.compile(r"Page\s+(\d+)\s+of\s+(\d+)")
_DATA  = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
_DAY   = re.compile(r"(\d{4})-(\d\d-\d\d)T\d\d:00:00")       # a date the employer set, not the moment of the request
_STATE = set(R._STATES.split("|"))
_US    = ("US", "PR", "GU", "VI", "AS", "MP")                # US territories are not abroad
_ABBR  = R.STATE_NAMES.get(R.HOME_NAME, R.HOME_NAME)         # "UT"

def _text(html):
    return " ".join(R.html_unescape(re.sub(r"<[^>]+>", " ", html)).split())

def _rule_kind(slug):
    """The kind the title rules judge this slug's employer by, so the job pages read are those of kept rows."""
    for names in (EMPLOYERS, R.BOARDS.get(KIND, {}), R.MORE.get(KIND, {})):
        for name, s in names.items():
            if s == slug: return "institution" if name in INSTITUTIONS else R.rule_kind(name, KIND)
    return KIND

def _code(code):
    """"City, ST" from the way iCIMS writes a place: "US-UT-Salt Lake City", "US-UT", "US-Remote", "CA-ON-Toronto"."""
    if not re.match(r"[A-Z]{2}(?:-|$)", code): return code
    country, _, rest = code.partition("-")
    # A portal that leaves the country off ("UT-Lehi") must not have the home state read as a foreign country.
    if country == _ABBR and not re.match(r"[A-Z]{2,3}(?:-|$)", rest): country, rest = "US", code
    state, _, city = rest.partition("-")
    if country in _US and state not in _STATE: state, city = "", rest
    if city.isupper(): city = city.title()                   # Salt Lake County shouts: "US-UT-SALT LAKE CITY"
    if country not in _US: return f"{', '.join(x for x in (city, state) if x)} ({country}, abroad)".strip()
    return f"{city}, {state or 'US'}" if city else f"{state}, US" if state else "US"

def _where(f):
    """(location, whether the page cut the list short). Portals choose their own fields: most show
    "Job Locations" in the iCIMS form, a few show a city and a state, and a row can have neither."""
    codes = f.get("job locations") or next((v for k, v in f.items() if "location" in k and re.match(r"[A-Z]{2}-", v)), "")
    if codes:
        parts = [c.strip() for c in codes.split("|") if c.strip()]
        return "; ".join(dict.fromkeys(_code(c) for c in parts if c != "...")), "..." in parts
    city  = next((v for k, v in f.items() if re.search(r"\bcity\b", k)), "")
    state = next((v for k, v in f.items() if re.search(r"\bstate\b", k)), "")
    return R.city_state(city.title() if city.isupper() else city, state), False

def _search(host, query=""):
    """(every job card of one search, the first page as read)."""
    cards, first, pr, last, per = [], "", 0, 1, 0
    while pr < last:
        body = R.curl_text(f"https://{host}/jobs/search?pr={pr}&in_iframe=1{query}", accept="text/html", timeout=60)
        # Anything else is the employer's own wrapper page, a sign-in page or a hand-off to a newer site.
        R.need("iCIMS_MainWrapper" in body and 'name="searchForm"' in body, "not an iCIMS search page")
        R.need("</html>" in body[-300:], "the page was cut short")           # a read that timed out still says 200
        got, m = _CARD.findall(body), _PAGE.search(body)
        if pr == 0:
            first, per = body, len(got)
            R.need((got and m) or "no jobs were found" in body, "no job cards and no page count (layout changed?)")
        # Each page says which one it is, and all but the last are full. A portal that ignored pr= would
        # hand back page 1 every time, and a short page in the middle is a list read short.
        R.need(not got or (m and int(m.group(1)) == pr + 1), f"asked for page {pr + 1} and got another")
        if m: last = min(int(m.group(2)), MAX_PAGES)
        R.need(len(got) == per or pr >= last - 1, f"page {pr + 1} of {last} came back short")
        cards += got
        pr += 1
        if pr < last: time.sleep(0.3)
    return cards, first

def _jobs(host, query=""):
    """One search as [(title, url, labelled fields)], and its first page."""
    cards, first = _search(host, query)
    out = []
    for card in cards:
        a = _LINK.search(card)
        R.need(a, "a job card without its link (layout changed?)")
        h3 = re.search(r"<h3[^>]*>(.*?)</h3>", a.group(2), re.S)
        f = {k.strip().lower(): _text(v) for k, v in _HEAD.findall(card)}
        f.update({_text(k).lower(): _text(v) for k, v in _TAG.findall(card)})
        out.append((_text(h3.group(1) if h3 else a.group(2)), a.group(1), f))
    return out, first

def _places(d):
    """"City, ST; ..." from the job page's own data. iCIMS writes "UNAVAILABLE" in a field it has nothing for."""
    spots, out = d.get("jobLocation") or [], []
    for p in spots if isinstance(spots, list) else [spots]:
        a = p.get("address") if isinstance(p, dict) else None
        if not isinstance(a, dict): continue
        city, state, country = [re.sub(r"^UNAVAILABLE$", "", str(a.get(k) or "").strip())
                                for k in ("addressLocality", "addressRegion", "addressCountry")]
        spot = R.city_state(city, state)
        home = not country or country.upper() in _US + ("USA", "UNITED STATES")
        out.append(spot if home else f"{spot} ({country}, abroad)".strip())
    return "; ".join(dict.fromkeys(x for x in out if x))

def _posting(url):
    """(text, posted, closes, places) from a job's own page. None where there is nothing to read: the job
    closed a moment ago, the page carries no posting data, or robots.txt closes it (the portals close every
    address containing "login", "candidate" or "referral", which catches a few job titles). Only a request
    that failed raises, because only that is worth asking again."""
    try: code, body = R.curl_resp(url + "?in_iframe=1", accept="text/html", timeout=40)
    except R.OffLimits: return None
    if code in ("404", "410"): return None
    if not code.startswith("2") or not body.strip(): raise RuntimeError(f"HTTP {code} from a job page")
    m = _DATA.search(body)
    try: d = json.loads(m.group(1), strict=False) if m else None
    except ValueError: d = None
    if not isinstance(d, dict): return None
    # A portal that keeps no posted date fills in the moment of the request minus two years, and one
    # with no end date fills in the posted date plus a year. Neither is a date anyone chose, and neither
    # is an end date most of a year away when the page gives no posted date to compare it with.
    p, e = _DAY.match(str(d.get("datePosted") or "")), _DAY.match(str(d.get("validThrough") or ""))
    default = bool(p and e and e.group(2) == p.group(2) and int(e.group(1)) == int(p.group(1)) + 1)
    far = (datetime.date.today() + datetime.timedelta(days=330)).isoformat()
    closes = e.group(0)[:10] if e and not default and e.group(0)[:10] < far else None
    return str(d.get("description") or ""), p.group(0)[:10] if p else None, closes, _places(d)

def fetch(slug):
    """Return every open job as [(title, location, url, closes, degree, extra)]."""
    host, _, assumed = slug.partition("|")
    host, assumed, kind = host.strip().lower(), assumed.strip(), _rule_kind(slug)
    jobs, first = _jobs(host)
    pages = _PAGE.search(first)
    if pages and int(pages.group(2)) > MAX_PAGES: R.PARTIAL[slug] = f"read the first {MAX_PAGES} of {pages.group(2)} pages"
    rows, cut, unplaced = [], set(), set()
    for title, url, f in jobs:
        loc, short = _where(f)
        if short: cut.add(url)
        if not R.placed(loc):
            # no place, or a bare city or building: the slug's assumed place stands in until the job page is read
            unplaced.add(url)
            if assumed: loc = f"{loc} ({assumed})" if loc else assumed
        day = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", f.get("posted date", ""))      # "3 hours ago (10/9/2026 2:24 PM)"
        posted = f"{day.group(3)}-{int(day.group(1)):02d}-{int(day.group(2)):02d}" if day else None
        rows.append([title, loc, url, None, None, {"posted": posted, "yrs": None, "internal": False, "company": None}])
    if cut:
        # A job open in a dozen states shows the first eleven and "...", which hides the home state: of the
        # 37 jobs Teleperformance's own search lists for Utah, 34 do not say so on the page. So ask the
        # portal's search for that state and add it to the cut rows it returns. The search box names the
        # state on its own ("UT", "US-UT") or with a city ("Utah-Ogden"); either gives the state's id.
        sel = re.search(r'<select[^>]*name="searchLocation".*?</select>', first, re.S)
        opt = sel and re.search(r'<option value="(\d*-\d+-)[^"]*"[^>]*>\s*(?:US-)?(?:%s|%s)\s*(?:[-,][^<]*)?</option>'
                                % (re.escape(_ABBR), re.escape(R.HOME_NAME)), sel.group(0))
        if opt:
            time.sleep(0.3)
            home = {j[1] for j in _jobs(host, "&searchLocation=" + urllib.parse.quote(opt.group(1)))[0]}
            for r in rows:
                if r[2] in cut and r[2] in home and not R.HOME.search(r[1]): r[1] += f"; {_ABBR}, US"
        elif not sel:
            R.PARTIAL[slug] = f"{len(cut)} jobs list more places than the page shows, and the portal has no search by place to ask"
    kept = [r for r in rows if R.classify(r[0], r[1], kind) or R.experienced(r[0], r[1], kind)]
    if len(kept) > MAX_DETAILS: R.PARTIAL[slug] = f"read details for the first {MAX_DETAILS} of {len(kept)} kept roles"
    failed = 0
    for n, r in enumerate(kept[:MAX_DETAILS]):
        time.sleep(0.3)
        try: got = R.patient(_posting, r[2], slots=R._DETAIL_SLOTS)
        except Exception:
            # A failed read keeps the row as listed. A portal that has stopped answering is left alone.
            failed += 1
            if failed == 3:
                R.PARTIAL[slug] = f"job pages stopped answering: read details for {n - 2} of {len(kept)} kept roles"
                break
            continue
        failed = 0
        if not got: continue
        text, posted, closes, places = got
        r[3], r[4] = closes, R.degree_flag(text)
        r[5]["posted"], r[5]["yrs"] = r[5]["posted"] or posted, R.min_years(text)
        if r[2] in unplaced and R.placed(places): r[1] = places      # the page says where; the assumption is dropped
    return R._dedupe([tuple(r) for r in rows])

if __name__ == "__main__":
    for name, slug in EMPLOYERS.items():
        rows, kind = fetch(slug), _rule_kind(slug)           # scan() judges the public bodies as institutions
        kept = [r for r in rows if R.classify(r[0], r[1], kind) or R.experienced(r[0], r[1], kind)]
        print(f"{name}: {len(rows)} jobs, {sum(1 for r in rows if R.HOME.search(r[1] or ''))} in Utah, {len(kept)} kept")
        for r in kept[:5]: print("   ", r[0], "|", r[1], "|", r[2], "|", r[3], "|", r[5])
