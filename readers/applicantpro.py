"""ApplicantPro (isolved Talent Acquisition, SUB.applicantpro.com): the JSON list the site's own job page calls,
/core/jobs/{domainId}, holds every open job in one reply with its city, posted date and closing date. The posting
text comes from .../{jobId}/job-details, read for kept roles only. The slug is "subdomain|domainId"; the id is
printed in the source of SUB.applicantpro.com/jobs/ as "domainId : 601"."""
import sys, os, re, json, time, datetime, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import refresh as R

KIND = "applicantpro"
SLUG_HELP = 'subdomain|domainId, e.g. "ogdencity|601" (ogdencity.applicantpro.com/jobs/ prints "domainId : 601" in its page source)'
EMPLOYERS = {
    # public bodies
    "Lehi City": "lehiut|3950", "Ogden City Corporation": "ogdencity|601", "Utah State Courts": "utcourts|12791",
    "City of Logan": "loganutah|14380", "Davis County Government": "daviscountyutah|15156",
    "South Jordan City": "southjordancity|600", "Tooele County": "tooelecounty|10017", "Layton City": "laytoncity|14543",
    "Riverton City": "rivertoncity|9010", "Utah Housing Corporation": "utahhousingcorp|5380",
    "Unified Fire Authority": "unifiedfire|8365",
    # companies
    "Nature's Sunshine Products": "naturessunshine|2550", "Granger Medical Clinic": "grangermedical|7274",
    "DMBA (Deseret Mutual Benefit Administrators)": "dmba|3909", "Skullcandy": "skullcandy|7065",
    "Electric Power Systems (EPS)": "electricpowersystems|15827", "Utah First Credit Union": "utahfirst|3425",
    "Lifetime Products": "lifetime|5746",
}
# This system serves both kinds of employer, so the flag for the whole kind stays off and the public bodies
# are named one by one: refresh.py's load_readers() adds these names to its own INSTITUTIONS.
INSTITUTION = False
INSTITUTIONS = {"Lehi City", "Ogden City Corporation", "Utah State Courts", "City of Logan", "Davis County Government",
                "South Jordan City", "Tooele County", "Layton City", "Riverton City", "Utah Housing Corporation",
                "Unified Fire Authority"}
AGGREGATOR = False

_US = {"USA", "PRI", "GUM", "VIR", "ASM", "MNP"}      # US territories are not abroad

def _data(url):
    """The "data" of a JSON reply. The server reports its own errors as an HTML page with HTTP 200,
    so anything that is not a JSON success is a failure, never an empty board."""
    body = R.curl_text(url)
    try: d = json.loads(body)
    except ValueError: d = None
    R.need(isinstance(d, dict) and d.get("success") is True and isinstance(d.get("data"), dict), "not a JSON success reply")
    return d["data"]

def _date(text):
    """"Sep 28, 2026" as "2026-09-28", else None."""
    try: return datetime.datetime.strptime((text or "").strip(), "%b %d, %Y").date().isoformat()
    except ValueError: return None

def _place(j):
    """"City, ST" from the feed's own fields, with "Remote" in front for a fully remote job."""
    city, state = (j.get("city") or "").strip(), (j.get("abbreviation") or j.get("stateName") or "").strip()
    # A row missing its city or its state falls back to the address line, which names both.
    loc = R.city_state(city, state) if city and state else (j.get("jobLocation") or "").strip() or R.city_state(city, state)
    # workplaceType is the employer's own wording: "Onsite", "Fully remote", "Work from home flexibility".
    remote = re.search(r"\bremote\b", j.get("workplaceType") or "", re.I)
    if (j.get("iso3") or "USA") not in _US:
        # Kept as one part, so that a remote job abroad is not read as a remote job in the US.
        return (("Remote, " if remote else "") + f"{loc} ({j['iso3']}, abroad)").strip()
    if remote: return "Remote; " + loc if loc else "Remote"
    return loc

def fetch(slug):
    """Return every open job as [(title, location, url, closes, degree, extra)]."""
    sub, _, did = slug.partition("|")
    sub, did = sub.strip().lower(), did.strip()
    if not (re.fullmatch(r"[a-z0-9-]+", sub) and did.isdigit()): raise RuntimeError('slug is not "subdomain|domainId"')
    did = str(int(did))
    base = f"https://{sub}.applicantpro.com"
    # isInternal 0 is what the public page sends. Without getParams the server answers with an error page.
    data = _data(f"{base}/core/jobs/{did}?getParams=" + urllib.parse.quote(json.dumps({"isInternal": 0})))
    jobs = data.get("jobs")
    R.need(isinstance(jobs, list), "no jobs list")
    # The id alone picks the board and the host is ignored: another employer's id returns that employer's
    # jobs, and an id nobody has returns an empty list that looks just like a board with no openings.
    R.need(all(isinstance(j, dict) and (j.get("subdomain") or "").lower() == sub for j in jobs), f"site {did} is not {sub}")
    if not jobs:
        page = R.curl_text(f"{base}/jobs/", accept="text/html")
        R.need(re.search(r"domainId\s*:\s*%s\b" % did, page), f"{sub} is not site {did}")
    # No paging: the site's own page asks once and draws whatever comes back (checked on a board of 120,
    # whose sitemap listed the same 120). jobCount is the tripwire should the server ever cut a list short.
    notes = []
    try: total = int(data.get("jobCount") or 0)
    except (TypeError, ValueError): total = 0
    if total > len(jobs) or len(jobs) > 6000: notes.append(f"read {min(len(jobs), 6000)} of {max(total, len(jobs))} jobs")
    far = (datetime.date.today() + datetime.timedelta(days=730)).isoformat()
    rows, ids, undated = [], [], 0
    for j in jobs[:6000]:
        title = re.sub(r"\s+", " ", R.html_unescape(j.get("title") or "")).strip()
        R.need(title and j.get("id"), "a job with no title or id")
        posted = _date(j.get("startDateRef"))
        # An open-ended posting carries a placeholder end date five years after its start, and the site's
        # own page prints "Until Filled" for it in place of that date.
        closes = None if j.get("untilFilled") else _date(j.get("endDateRef"))
        undated += bool((j.get("startDateRef") and not posted) or (not j.get("untilFilled") and j.get("endDateRef") and not closes))
        if closes and closes > far: closes = None
        # Built from the slug, not jobUrl: the feed spells the host as the employer typed it ("Ogdencity").
        rows.append((title, _place(j), f"{base}/jobs/{j['id']}", closes, None,
                     {"posted": posted, "yrs": None, "internal": False, "company": None}))
        ids.append(j["id"])
    if undated: notes.append(f"could not read a date on {undated} of {len(rows)} jobs")    # the feed changed how it writes them

    def text(jid):
        d = _data(f"{base}/core/jobs/{did}/{jid}/job-details")
        R.need(str(d.get("id")) == str(jid), "details of another job")
        return d.get("description") or ""      # advertisingDescription is not shown on the page and can be stale
    kept = [i for i, r in enumerate(rows) if R.classify(r[0], r[1], KIND) or R.experienced(r[0], r[1], KIND)]
    read = failed = 0
    for i in kept[:60]:
        if failed == 3: break                  # the endpoint is down or closed, so stop asking
        try: body = R.patient(text, ids[i], slots=R._DETAIL_SLOTS)
        except Exception: failed += 1; continue    # a failed read keeps the row as listed
        t, loc, url, closes, _, extra = rows[i]
        rows[i] = (t, loc, url, closes, R.degree_flag(body), dict(extra, yrs=R.min_years(body) or None))
        read += 1; time.sleep(0.3)
    if failed: notes.append(f"read details for {read} of {len(kept)} kept roles")
    elif len(kept) > 60: notes.append(f"read details for the first 60 of {len(kept)} kept roles")
    if notes: R.PARTIAL[slug] = "; ".join(notes)
    return R._dedupe(rows)

LINK = re.compile(r"https://[\w-]+\.applicantpro\.com/jobs/\d+", re.I)
def link_state(url):
    """'live', 'dead' or 'unknown' for one posting URL of this system. Return 'unknown' whenever unsure."""
    if not LINK.match(url or ""): return "unknown"
    try: code, body = R.curl_resp(url, accept="text/html")
    except Exception: return "unknown"
    # An id the site does not have answers 404. A closed posting keeps its page, HTTP 200, with a notice
    # in place of the apply box and without the JobPosting markup an open one carries.
    if code == "404" and "Job Not Found" in body: return "dead"
    if code != "200": return "unknown"
    if '"JobPosting"' in body: return "live"
    return "dead" if "POSITION HAS BEEN CLOSED" in body.upper() else "unknown"

if __name__ == "__main__":
    for name, slug in EMPLOYERS.items():
        rows = fetch(slug)
        kept = [r for r in rows if R.classify(r[0], r[1], KIND) or R.experienced(r[0], r[1], KIND)]
        print(f"{name}: {len(rows)} jobs, {sum(1 for r in rows if R.HOME.search(r[1] or ''))} in Utah, {len(kept)} kept")
        for r in kept[:5]: print("   ", r[0], "|", r[1], "|", r[2], "|", r[3], "|", r[5])
