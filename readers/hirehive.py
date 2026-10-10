"""HireHive: every careers site answers COMPANY.hirehive.com/api/v1/jobs with its board as JSON,
descriptions and published dates included, so one request reads an employer (a long board links its next page).
The slug is the hirehive.com subdomain ("redo" for https://redo.hirehive.com)."""
import sys, os, re, json, time, datetime, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import refresh as R

KIND = "hirehive"
SLUG_HELP = 'the hirehive.com subdomain of the careers site: "redo" for https://redo.hirehive.com'
EMPLOYERS = {"Redo": "redo"}
INSTITUTION = False
AGGREGATOR = False

def _jobs(slug):
    """Every published job record of one employer."""
    home = f"https://{slug}.hirehive.com/api/v1/jobs"
    url, jobs, seen = home, [], set()
    for _ in range(100):
        try: d = json.loads(R.curl_text(url, timeout=60))
        except ValueError: raise RuntimeError(f"unexpected reply (not JSON) from {slug}.hirehive.com") from None
        R.need(isinstance(d, dict) and isinstance(d.get("jobs"), list), "no jobs list")
        R.need(all(isinstance(j, dict) and j.get("title") and j.get("hostedUrl") for j in d["jobs"]), "a job without a title or a link")
        fresh = [j for j in d["jobs"] if j["hostedUrl"] not in seen]
        seen.update(j["hostedUrl"] for j in fresh); jobs += fresh
        # A reply that is not the whole board links the rest in nextPage (".../api/v1/jobs?take=5&skip=5",
        # seen by asking Redo for five at a time; its 15 jobs come in one reply otherwise). A page that
        # adds nothing new ends the loop, so a link that leads nowhere cannot spin.
        nxt = d.get("nextPage")
        if not nxt or not fresh or len(jobs) >= 6000: break
        url = urllib.parse.urljoin(home, str(nxt))
        R.need(url.startswith(home), "nextPage points away from the jobs list")
        time.sleep(0.3)
    total = d.get("publishedJobsCount")
    if isinstance(total, int) and len(jobs) < total: R.PARTIAL[slug] = f"{len(jobs)} of {total} jobs read"
    return jobs[:6000]

def _place(j):
    """"City, ST" in the US ("Draper" + "UT"). A job in another country is marked the way the Workday reader
    marks one ("Utrecht, Netherlands (NL, abroad)"), so a province code such as Utrecht's "UT" is never read as Utah."""
    country = j.get("country") if isinstance(j.get("country"), dict) else {}
    code, land = (country.get("code") or "").strip().upper(), (country.get("name") or "").strip()
    # the city is typed by hand: a ";" in it ("Galway; Remote") would be read as a second location
    city, st = re.sub(r"\s*[;|]\s*", ", ", str(j.get("location") or "")).strip(), str(j.get("stateCode") or "").strip()
    if code == "US": return R.city_state(city, st or "US")
    if code in ("", "PR", "GU", "VI", "AS", "MP"): return ", ".join(p for p in (city, st, land) if p)     # a US territory is not abroad
    return ", ".join(p for p in (city, land or code) if p) + f" ({code}, abroad)"

def _day(stamp):
    """Seconds since 1970 (a number today, a string in older replies) as a UTC date."""
    try: return datetime.datetime.fromtimestamp(int(float(stamp)), datetime.timezone.utc).date().isoformat()
    except (TypeError, ValueError, OverflowError, OSError): return None

def fetch(slug):
    """Return every open job as [(title, location, url, closes, degree, extra)]."""
    rows = []
    for j in _jobs(slug):
        desc = j.get("description")
        if isinstance(desc, dict): desc = desc.get("html") or desc.get("text")     # the HTML keeps the list items apart, which the years rule needs
        text = desc if isinstance(desc, str) else None
        # publishedDate is the day the job last went up; the posting page's own "datePosted" is rolled
        # forward on an old posting (and its "validThrough" is made up from it), so neither is used.
        rows.append((re.sub(r"\s+", " ", j["title"]).strip(), _place(j), j["hostedUrl"],
                     None,                                   # HireHive has no closing date
                     R.degree_flag(text),
                     {"posted": _day(j.get("publishedDate") or j.get("createdDate")), "yrs": R.min_years(text), "internal": False, "company": None}))
    return R._dedupe(rows)

# A posting link ends in a six-character id ("product-analyst-draper-Jr5HUI"). Every id seen has a capital
# or a digit in it, which is asked for here so that a page like "/privacy-policy" is not taken for a posting.
HIREHIVE_LINK = re.compile(r"https://([\w-]+)\.hirehive\.com/[\w-]+-(?=[a-z]*[A-Z0-9])([A-Za-z0-9]{6})/?(?:[?#].*)?$")
def link_state(url):
    """'live', 'dead' or 'unknown' for one posting URL of this system. Return 'unknown' whenever unsure."""
    m = HIREHIVE_LINK.match(url or "")
    if not m: return "unknown"
    # A posting that is gone answers 302 to the careers front page, which is a 200 once followed, so
    # the status says nothing. The employer's own list does. The six characters that end the link are
    # the job's id; the words before them are its title and city, which an edit can change.
    try:
        if m.group(2) in {j["hostedUrl"].split("?")[0].rstrip("/")[-6:] for j in _jobs(m.group(1))}: return "live"
        # Off the list is not yet dead: the link may be to a posting kept off the careers site, or to a
        # page that is no posting at all. Its own page settles it, because the front page a dead link
        # lands on links only the open jobs and a posting's page links itself.
        code, page = R.curl_resp(url, accept="text/html")
    except Exception: return "unknown"
    return "dead" if code == "200" and "-" + m.group(2) not in page else "unknown"

if __name__ == "__main__":
    for name, slug in EMPLOYERS.items():
        rows = fetch(slug)
        kept = [r for r in rows if R.classify(r[0], r[1], KIND) or R.experienced(r[0], r[1], KIND)]
        print(f"{name}: {len(rows)} jobs, {sum(1 for r in rows if R.HOME.search(r[1] or ''))} in Utah, {len(kept)} kept")
        for r in kept[:5]: print("   ", r[0], "|", r[1], "|", r[2], "|", r[3], "|", r[5])
