"""Paylocity Recruiting (recruiting.paylocity.com): an employer's public job list page carries every open job as
one JSON object (window.pageData), so one request reads the board; the posting page is read for kept rows only.
The slug is the board's GUID from that page's address, then optionally "|location" to assume for rows with no state."""
import sys, os, re, json, time, datetime, threading, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import refresh as R

KIND = "paylocity"
SLUG_HELP = ('the GUID in the job list address recruiting.paylocity.com/recruiting/jobs/All/<GUID>/Company-Name, e.g. '
             '"05966b84-70eb-422a-887c-496fe8889638"; an older board\'s number (/jobs/List/4684) works too; '
             'optional "|Utah (check posting)" places the rows an employer left without a state')
EMPLOYERS = {
    "Autonomous Solutions Inc": "05966b84-70eb-422a-887c-496fe8889638",
    "Palladyne AI": "265fde3e-5bd7-4a32-8881-2f62c8f3d32e",
    # three of its postings cover several clinics and name none; every clinic it runs is in Utah
    "Tanner Clinic": "514c607a-f487-4b57-b074-c21af77369af|Utah (check posting)",
    "Biomerics": "8cb80942-3be2-46fd-ba98-f1e3442fc0ac",
    "Valley Behavioral Health": "1e901cf2-54f9-44fb-9dca-962f9d2b9996",
    "Angel Studios": "3af7f13c-9da0-431d-88ee-84db2b3aa074",
    "Solutionreach": "2a6c642f-3a99-4015-afe3-4c354f9edfd7",
    "West Valley City": "80b0e3c7-f435-4ae9-a01d-340dbfc95ec8",
    "Canyon View Credit Union": "3ba1106f-65b4-43ac-91cc-523ba9bded91",
    "Security National Financial": "9a4020ea-da6d-42ca-b6cc-969357f7c2f6",
    "Wheeler Machinery": "5ec73c71-4db2-40b7-a9c8-fd62d1426a34",
    "Bear River Mutual Insurance": "52dc4cce-fe09-4b7e-b8e5-21fcbc252b6c",
    "Haynie & Company": "2b405fc5-6c80-4c1b-9222-afe75bb3bc96",
}
INSTITUTION = False   # mostly companies; True would strip "Graduate" from a company's new-grad title
# The clinics and the city are the exception: in their titles "Graduate" and "Campus" are plain description.
# refresh.load_readers() reads this set by name.
INSTITUTIONS = {"Tanner Clinic", "Valley Behavioral Health", "West Valley City"}
AGGREGATOR = False

BASE = "https://recruiting.paylocity.com/Recruiting/Jobs"
LINK = re.compile(r"recruiting\.paylocity\.com/recruiting/jobs/details/(\d+)", re.I)

# Every employer here is on the same host and refresh.py scans eight employers at once, so each request
# waits its turn: one at a time, whichever board it is for.
_GATE = threading.Lock()
def _html(url):
    """One page from Paylocity. A failed request raises, as R.curl_text does."""
    with _GATE: return R.curl_text(url, accept="text/html")

_USA = re.compile(r"u\.?s\.?(?:a\.?)?|united states(?: of america)?", re.I)
_SAYS_REMOTE = re.compile(r"(?<!non[- ])(?<!not )(?<!no )\bremote\b", re.I)

def _place(job, assumed):
    """"City, ST" from the job's address, with "Remote" in front when the job is fully remote."""
    a = job.get("JobLocation") or {}
    city, state, country = [(a.get(k) or "").strip(" ,") for k in ("City", "State", "Country")]
    if city.isupper(): city = city.title()                       # "LAYTON", "MIDVALE"
    if len(state) == 2: state = state.upper()
    # LocationName is the employer's own label for an office ("Mendon Office", "CORE II", "Provo, UT"),
    # which the location rules mostly cannot read, so the address comes first.
    label = re.sub(r"\s+", " ", job.get("LocationName") or a.get("Name") or "").strip()
    says_remote = _SAYS_REMOTE.search(label)                     # some remote rows say it only here
    stated = lambda s: bool(R.HOME.search(s) or R.US_HINT.search(s))      # names Utah or a US state
    place = R.city_state(city, state)
    # Some addresses are saved without a state, or without a city either. The label is then used when
    # it names a state ("Layton, UT") or when it is all the feed says about the place.
    if not state and label and not says_remote and (stated(label) or not place): place = label
    # the same mark the Workday reader uses, in words the location rules read
    abroad = f" ({country}, abroad)" if country and not _USA.fullmatch(country) else ""
    # The page words IndeedRemoteType as 0 "Temporarily WFH", 1 "Hybrid Remote", 2 "Fully Remote". A hybrid
    # job keeps its office and is not called remote: a hybrid job in Boise is no use to someone in Utah.
    hybrid = job.get("IndeedRemoteType") in (0, 1) and place
    if says_remote or (job.get("IsRemote") and not hybrid):
        if abroad: return "Remote" + (", " + place if place else "") + abroad
        return "Remote; " + place if place else "Remote, US" if country else "Remote"
    if abroad: return (place + abroad).strip()
    # Still no state: the slug's assumed location, or at least the country, so that a bare "Athens"
    # (Biomerics has a plant in Athens, TX) is never read as Greece.
    if not stated(place): place = ", ".join(x for x in (place, assumed or ("US" if country and place else "")) if x)
    return place

def _posting_text(url):
    """The posting's sections (Job Type, Description, Requirements, Salary) as HTML, or "" when the page has none."""
    html = _html(url)                                            # a failed request raises, and R.patient asks again
    m = re.search(r'class="job-preview-details">(.*?)(?:<div class="preview-bottom-apply-btn"|<footer\b|\Z)', html, re.S)
    # A posting that closed since the list was read is a 200 "Job Not Found" page. That is an answer,
    # not a failure: asking twice more would not change it.
    return m.group(1) if m else ""

def fetch(slug):
    """Return every open job as [(title, location, url, closes, degree, extra)]."""
    board, _, assumed = [x.strip() for x in slug.partition("|")]
    # A board answers to its GUID under /All/ and, if it is an old one, to its number under /List/. Neither
    # form works on the other path.
    html = _html(f"{BASE}/{'List' if board.isdigit() else 'All'}/{board}")
    m = re.search(r"window\.pageData\s*=\s*(?=\{)", html)
    # An unknown board is a 200 "Job Not Found" page. It must not read as an employer with no openings.
    R.need(m, "no job list on the page, check the board id")
    try: data = json.JSONDecoder().raw_decode(html, m.end())[0]
    except ValueError: data = {}
    jobs = data.get("Jobs")
    R.need(isinstance(jobs, list), "pageData has no Jobs list")
    rows, notes = [], []
    if len(jobs) > 6000: notes.append(f"read the first 6000 of {len(jobs)} jobs")
    for j in jobs[:6000]:
        R.need(isinstance(j, dict) and j.get("JobId") and j.get("JobTitle"), "a job without an id or a title")
        # PublishedDate is the page's own "Post Date" column: the day the employer last published the job,
        # stamped in Central time. The date is taken as stamped.
        posted = re.match(r"\d{4}-\d\d-\d\d", j.get("PublishedDate") or "")
        rows.append([re.sub(r"\s+", " ", j["JobTitle"]).strip(), _place(j, assumed), f"{BASE}/Details/{j['JobId']}", None, None,
                     {"posted": posted.group(0) if posted else None, "yrs": None,
                      "internal": bool(j.get("IsInternal")), "company": None}])
    # Paylocity states no closing date anywhere. The degree and the years come from the posting page,
    # read one at a time. A failed read keeps the row as listed rather than dropping it.
    kept = [r for r in rows if R.classify(r[0], r[1], KIND) or R.experienced(r[0], r[1], KIND)]
    unread = failed = 0
    for n, r in enumerate(kept[:60]):
        if n: time.sleep(0.3)
        try: text = R.patient(_posting_text, r[2], slots=R._DETAIL_SLOTS); failed = 0
        except R.OffLimits: unread += len(kept[:60]) - n; break  # no use asking for the rest
        except Exception:
            text, failed = "", failed + 1
            # Three postings in a row that would not load, three tries each: the site is down or is
            # turning the script away, and asking for fifty more would only press it.
            if failed == 3: unread += len(kept[:60]) - n; break
        if not text: unread += 1; continue
        r[4], r[5]["yrs"] = R.degree_flag(text), R.min_years(text)
    if len(kept) > 60: notes.append(f"read details for the first 60 of {len(kept)} kept roles")
    if unread: notes.append(f"could not read the posting page of {unread} of {min(len(kept), 60)} kept roles")
    if notes: R.PARTIAL[slug] = "; ".join(notes)
    return R._dedupe([tuple(r) for r in rows])

def link_state(url):
    """'live', 'dead' or 'unknown' for one posting URL of this system. Return 'unknown' whenever unsure."""
    m = LINK.search(url)
    if not m: return "unknown"
    try:
        with _GATE: code, body = R.curl_resp(f"{BASE}/Details/{m.group(1)}", accept="text/html")
    except Exception: return "unknown"
    if code != "200": return "unknown"
    # A closed posting and an id that never existed both answer 200 with the same "Job Not Found" page.
    if "that job does not exist or is not currently active" in body: return "dead"
    return "live" if f"/Jobs/Apply/{m.group(1)}" in body else "unknown"

if __name__ == "__main__":
    for name, slug in EMPLOYERS.items():
        rows = fetch(slug)
        kept = [r for r in rows if R.classify(r[0], r[1], KIND) or R.experienced(r[0], r[1], KIND)]
        print(f"{name}: {len(rows)} jobs, {sum(1 for r in rows if R.HOME.search(r[1] or ''))} in Utah, {len(kept)} kept")
        for r in kept[:5]: print("   ", r[0], "|", r[1], "|", r[2], "|", r[3], "|", r[5])
