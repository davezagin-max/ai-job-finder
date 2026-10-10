"""Rippling ATS: the list a Rippling careers page itself loads (ats.rippling.com/api/v2/board/<slug>/jobs),
public JSON with no key and no sign-in, read page by page. The slug is the board name in the careers link
ats.rippling.com/<slug>/jobs. Each location comes with its own city, state and country fields. The posted
date and the posting text are not in the list, so they are read from each kept job's own record."""
import sys, os, re, json, time, datetime, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import refresh as R

KIND = "rippling"
SLUG_HELP = 'the board name in the careers link ats.rippling.com/<slug>/jobs, for example "whistic-careers"'
EMPLOYERS = {"Torus": "torus", "PDQ": "pdq", "Tech9": "tech9", "Whistic": "whistic-careers", "Rivet": "rivet",
             # The board is titled "Chatbooks Careers" and is empty today. chatbooks.com answered HTTP 429,
             # so it is not confirmed that their own careers page still points here: check by hand once.
             "Chatbooks": "chatbooks",
             "Les Olson IT": "les-olson-it", "Opiniion": "opiniion", "UHIN (Utah Health Information Network)": "uhin-careers"}
INSTITUTION = False   # True for public bodies, schools and hospitals, whose titles use "University", "Campus" or "Graduate" as plain description
AGGREGATOR = False    # True when one slug returns the jobs of many employers

API = "https://ats.rippling.com/api/v2/board/"
LINK = re.compile(r"ats\.rippling\.com/(?:[a-z]{2}-[A-Z]{2}/)?([^/?#]+)/jobs/([0-9a-f-]{36})")
PAGE = 1000           # the largest page the careers page's own script asks for, so most boards are one request
MAX_DETAILS = 60
_US = ("US", "PR", "GU", "VI", "AS", "MP")      # US territories are not abroad

def _place(l):
    """One location of a job in the form the location rules read: "Salt Lake City, UT", "Remote, US",
    "Remote, UT" for a remote job tied to a state, "Ljubljana (Slovenia, abroad)" for one outside the US."""
    # The label ("name") is free text: boards write "WEST JORDAN, UT", "Hybrid (Lehi, Utah, US)", "Berlin"
    # or a bare "AR". The fields beside it say where the place is, so the string is built from them.
    name, city = (re.sub(r"\s+", " ", l.get(k) or "").strip() for k in ("name", "city"))
    if city.lower() == "remote": city = ""               # one board typed "Remote" as the city
    if len(city) > 3 and city in (city.upper(), city.lower()): city = city.title()
    remote = l.get("workplaceType") == "REMOTE"
    code = (l.get("countryCode") or "").upper()
    if not code: return name                               # no country given: the label is all there is
    if code not in _US:
        # Marked in the words the location rules read, because they do not know every country by
        # name: "Ljubljana, Slovenia" on its own would be taken for a US town.
        country = re.sub(r"[()]", "", l.get("country") or code)
        return f"{city or ('Remote' if remote else '')} ({country}, abroad)".strip()
    state = l.get("stateCode") or ""
    if not re.fullmatch(r"[A-Z]{2}", state): state = R.STATE_NAMES.get((l.get("state") or "").title(), "")
    # A US city with no state gets "US", or "Dublin" and "Vienna" would read as foreign.
    place = ", ".join(x for x in (city, state or "US") if x)
    return "Remote, " + place if remote else place

def _record(board, uid):
    """One job's own record: its text and the day it was posted."""
    d = R.curl(f"{board}/jobs/{urllib.parse.quote(uid, safe='')}")
    R.need(isinstance(d, dict) and d.get("uuid") == uid, "not this job's record")
    return d

def fetch(slug):
    """Return every open job as [(title, location, url, closes, degree, extra)]."""
    # A pasted link or a path is refused here: "torus/../pdq" would otherwise be answered with PDQ's board.
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", slug or ""): raise RuntimeError("the slug is not a Rippling board name")
    board = API + slug
    listed, page, total, notes = [], 0, 0, []
    while True:
        # A board that does not exist answers 404, which raises. Grouped, a job open in several
        # places is one row that carries all of them.
        d = R.curl(f"{board}/jobs?groupJobsByLocation=true&page={page}&pageSize={PAGE}", timeout=60)
        R.need(isinstance(d, dict) and isinstance(d.get("items"), list) and isinstance(d.get("totalItems"), int), "not a job list")
        listed += d["items"]; total = d["totalItems"]
        # The reply says how big its pages really are, in case the site ever caps them lower than asked.
        if len(d["items"]) < (d.get("pageSize") or PAGE) or len(listed) >= 6000: break
        page += 1; time.sleep(0.3)
    if len(listed) >= 6000:
        listed = listed[:6000]
        if total > 6000: notes.append(f"read the first 6,000 of {total:,} jobs")
    else:
        # Rows that tie in the site's ordering can swap between two pages, which repeats one and hides
        # another. Fewer distinct rows than the site counts means a job was missed: fail, do not guess.
        distinct = len({json.dumps(j, sort_keys=True) for j in listed})
        R.need(distinct == total, f"read {distinct} of {total} jobs")
    jobs = {}
    for j in listed:
        R.need(isinstance(j, dict) and j.get("name") and j.get("url") and j.get("id"), "a job without a title, link or id")
        _, places, _ = jobs.setdefault(j["url"], (re.sub(r"\s+", " ", j["name"]).strip(), [], j["id"]))
        for l in j.get("locations") or []:
            place = _place(l) if isinstance(l, dict) else ""
            if place and place not in places: places.append(place)
    listed = [(title, "; ".join(places), url, uid) for url, (title, places, uid) in jobs.items()]
    # Only the roles that will be published are worth a second request each, one at a time.
    kept = [x for x in listed if R.classify(x[0], x[1], KIND) or R.experienced(x[0], x[1], KIND)]
    if len(kept) > MAX_DETAILS: notes.append(f"read details for the first {MAX_DETAILS} of {len(kept)} kept roles")
    records, failed, streak = {}, 0, 0
    for _, _, url, uid in kept[:MAX_DETAILS]:
        if streak >= 3: failed += 1; continue    # the site is refusing: stop asking rather than retry sixty jobs
        try: records[url] = R.patient(_record, board, uid, slots=R._DETAIL_SLOTS); streak = 0
        except R.OffLimits: raise
        except Exception: failed += 1; streak += 1   # the row is kept as listed rather than dropped
        time.sleep(0.3)
    if failed: notes.append(f"{failed} of {min(len(kept), MAX_DETAILS)} job records could not be read")
    if notes: R.PARTIAL[slug] = "; ".join(notes)
    rows = []
    for title, loc, url, _ in listed:
        info = records.get(url) or {}
        # "role" is the posting itself. "company" is the employer's About text, the same on every
        # job, so it is left out of the years and degree reading.
        text = (info.get("description") or {}).get("role")
        # createdOn carries the site's own UTC offset, so its first ten characters are the day as posted.
        rows.append((title, loc, url, None, R.degree_flag(text),      # Rippling states no closing date
                     {"posted": (info.get("createdOn") or "")[:10] or None, "yrs": R.min_years(text),
                      "internal": False, "company": None}))
    return R._dedupe(rows)

def link_state(url):
    """'live', 'dead' or 'unknown' for one posting URL of this system. Return 'unknown' whenever unsure."""
    # The posting page shows the board (HTTP 200) for a job that is gone, so ask for the job's record.
    # A job that is gone and a board that is gone both answer 404 with their own JSON error; a 404
    # that is not that JSON is the service itself being away, which says nothing about the job.
    m = LINK.search(url or "")
    if not m: return "unknown"
    try:
        code, body = R.curl_resp(f"{API}{m.group(1)}/jobs/{m.group(2)}")
        d = json.loads(body)
    except Exception:
        return "unknown"
    if not isinstance(d, dict): return "unknown"
    if code == "200" and d.get("uuid") == m.group(2): return "live"
    if code == "404" and (d.get("ok") is False or d.get("error_code") == "RESOURCE_NOT_FOUND"): return "dead"
    return "unknown"

if __name__ == "__main__":
    for name, slug in EMPLOYERS.items():
        rows = fetch(slug)
        kept = [r for r in rows if R.classify(r[0], r[1], KIND) or R.experienced(r[0], r[1], KIND)]
        print(f"{name}: {len(rows)} jobs, {sum(1 for r in rows if R.HOME.search(r[1] or ''))} in Utah, {len(kept)} kept")
        for r in kept[:5]: print("   ", r[0], "|", r[1], "|", r[2], "|", r[3], "|", r[5])
