"""Dayforce candidate portal (jobs.dayforcehcm.com): the search call the board page itself makes returns
every posting with its text, posted date, closing date and locations, 25 a request, so no posting is
opened one by one. The slug is "namespace|boardCode", the two path parts of the employer's board URL.
The search wants the anonymous anti-forgery token the site hands every visitor (no account, no sign-in):
a token in the body of /api/auth/csrf and a matching cookie, both sent back with the search."""
import sys, os, re, json, time, datetime, threading, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import refresh as R

KIND = "dayforce"
SLUG_HELP = 'namespace|boardCode, the two path parts of the board URL: jobs.dayforcehcm.com/en-US/biofire/CANDIDATEPORTAL is "biofire|CANDIDATEPORTAL"'
# Harmons Grocery (harmons|CANDIDATEPORTAL) reads fine too; its ninety postings are store jobs.
EMPLOYERS = {"BioFire Defense": "biofire|CANDIDATEPORTAL", "C.R. England": "crengland|CANDIDATEPORTAL",
             "Swire Coca-Cola": "swirecc|CANDIDATEPORTAL", "Savage": "ssc|CANDIDATEPORTAL"}
INSTITUTION = False   # True for public bodies, schools and hospitals, whose titles use "University", "Campus" or "Graduate" as plain description
AGGREGATOR = False    # True when one slug returns the jobs of many employers

HOST = "https://jobs.dayforcehcm.com"
LINK = re.compile(r"https://jobs\.dayforcehcm\.com/[A-Za-z-]+/[^/]+/[^/]+/jobs/(\d+)$")
MAX_PAGES = 150       # 25 jobs a request, so 3,750 jobs: the most one employer is asked for
_VISITOR = []         # [X-CSRF-TOKEN header, Cookie header], asked for once a run and shared by every board
_ONE_BOARD = threading.Lock()   # every employer is on the one host, so their boards are read one after another

def _visitor(fresh=False):
    """The two headers a search must carry. The cookie holds a signature only the server can make, and it
    arrives in a Set-Cookie header, so this one request is made with R.curl_with_headers, which prints
    the reply's headers too. It is the token the site hands every visitor: no sign-in, no account."""
    if fresh: del _VISITOR[:]
    if not _VISITOR:
        url = HOST + "/api/auth/csrf"
        code, reply = R.curl_with_headers(url, 30)
        tok = re.search(r'"csrfToken"\s*:\s*"([^"]+)"', reply)
        cookie = re.search(r"(?im)^set-cookie:\s*([^=\s;]*csrf-token=[^;\s]+)", reply)
        R.need(code == "200" and tok and cookie, f"no visitor token, HTTP {code}")
        _VISITOR[:] = [f"X-CSRF-TOKEN: {tok.group(1)}", f"Cookie: {cookie.group(1)}"]
    return list(_VISITOR)

def _search(ns, board, start):
    post = {"clientNamespace": ns, "jobBoardCode": board, "cultureCode": "en-US", "distanceUnit": 0, "paginationStart": start}
    url = f"{HOST}/api/geo/{urllib.parse.quote(ns, safe='')}/jobposting/search"
    code, body = R.curl_resp(url, post, headers=_visitor())
    if code == "403":                                   # the token went stale: ask for a new one, once
        code, body = R.curl_resp(url, post, headers=_visitor(fresh=True))
    if code == "404": raise RuntimeError(f"no Dayforce board '{ns}|{board}' (HTTP 404)")
    if code != "200": raise RuntimeError(f"HTTP {code} from jobs.dayforcehcm.com")
    try: d = json.loads(body)
    except ValueError: raise RuntimeError("unexpected reply (not JSON)")
    R.need(isinstance(d, dict) and isinstance(d.get("jobPostings"), list) and isinstance(d.get("maxCount"), int), "no jobPostings list")
    return d

def _place(p):
    """"Salt Lake City, UT" from one postingLocations entry. A foreign one is marked the way the Workday
    reader marks it, so "Chennai, TN" is never read as Tennessee."""
    city, state = p.get("cityName"), p.get("stateCode")
    # a posting for a whole region has no city, and then the feed's own words say more than "UT" does
    loc = R.city_state(city, state) if city else (p.get("formattedAddress") or state or "").strip()
    cc = (p.get("isoCountryCode") or "US").upper()
    return loc if cc in ("US", "PR", "GU", "VI", "AS", "MP") or not loc else f"{loc} ({cc}, abroad)"

def _day(stamp, back=0):
    """The calendar day of one of the feed's UTC timestamps, read `back` hours earlier."""
    m = re.match(r"(\d{4})-(\d\d)-(\d\d)T(\d\d):(\d\d)", stamp or "")
    if not m: return None
    return (datetime.datetime(*map(int, m.groups())) - datetime.timedelta(hours=back)).strftime("%Y-%m-%d")

def fetch(slug):
    """Return every open job as [(title, location, url, closes, degree, extra)]."""
    ns, _, board = (x.strip() for x in slug.partition("|"))
    R.need(ns and board, 'slug is "namespace|boardCode"')
    rows, start, total, cut = [], 0, 0, False
    with _ONE_BOARD:
        for page in range(MAX_PAGES):
            d = _search(ns, board, start)
            posts, total = d["jobPostings"], d["maxCount"]
            for j in posts:
                title = re.sub(r"\s+", " ", j.get("jobTitle") or "").strip()
                if not title or j.get("jobPostingId") is None: continue
                places = [_place(p) for p in j.get("postingLocations") or [] if isinstance(p, dict)]
                if j.get("hasVirtualLocation"): places.append("Remote")
                loc = "; ".join(dict.fromkeys(p for p in places if p))
                # the list carries the whole posting, but only what will be published is read for flags
                text = j.get("jobDescription") if (R.classify(title, loc, KIND) or R.experienced(title, loc, KIND)) else None
                # A posting starts at the beginning of a day and expires a minute before the end of one, as the
                # employer's clock has it: 05:59 UTC on the 26th is 11:59 pm on the 25th in Utah, and Harmons'
                # 07:59 UTC on the 17th is 1:59 am there. So the closing date is read twelve hours back: the
                # last whole day the posting is open, not the UTC date, which is a day late.
                rows.append((title, loc, f"{HOST}/en-US/{ns}/{board}/jobs/{j['jobPostingId']}",
                             _day(j.get("postingExpiryTimestampUTC"), back=12), R.degree_flag(text),
                             {"posted": _day(j.get("postingStartTimestampUTC")), "yrs": R.min_years(text),
                              "internal": False, "company": None}))
            start += len(posts)
            if not posts or start >= total: break
            cut = page == MAX_PAGES - 1
            time.sleep(0.3)
    rows = R._dedupe(rows)
    if cut: R.PARTIAL[slug] = f"read {len(rows)} of {total} jobs"
    else: R.need(len(rows) >= total * 0.9, f"read {len(rows)} of {total} jobs")     # a short read must never look like closures
    return rows

def link_state(url):
    """'live', 'dead' or 'unknown' for one posting URL of this system. Return 'unknown' whenever unsure."""
    m = LINK.match(url or "")
    if not m: return "unknown"
    try: code, page = R.curl_resp(url, accept="text/html")
    except Exception: return "unknown"
    if code == "404": return "dead"                     # a posting taken down, or an id that never was one
    # An expired posting still answers 200 and still shows the job, so the page's own data is what tells.
    data = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page, re.S)
    try: job = json.loads(data.group(1))["props"]["pageProps"]["jobData"]
    except Exception: return "unknown"
    if code != "200" or not isinstance(job, dict) or str(job.get("jobPostingId")) != m.group(1): return "unknown"
    ends = (job.get("postingExpiryTimestampUTC") or "")[:16]
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M")
    if job.get("postingStatus") == 2 or (ends and ends < now): return "dead"     # 2 is what an expired posting carries
    return "live" if job.get("postingStatus") == 1 else "unknown"

if __name__ == "__main__":
    for name, slug in EMPLOYERS.items():
        rows = fetch(slug)
        kept = [r for r in rows if R.classify(r[0], r[1], KIND) or R.experienced(r[0], r[1], KIND)]
        print(f"{name}: {len(rows)} jobs, {sum(1 for r in rows if R.HOME.search(r[1] or ''))} in Utah, {len(kept)} kept")
        for r in kept[:5]: print("   ", r[0], "|", r[1], "|", r[2], "|", r[3], "|", r[5])
