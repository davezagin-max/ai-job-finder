"""iCIMS Jibe career sites: an employer's own careers site ("jobs.echostar.com") in front of iCIMS.
Its search box calls a public JSON API, /api/jobs, 100 jobs a page, and every row already carries the
description, the posted date and (when one is set) the day the posting expires, so no job page is read.
The slug is the career site's host."""
import sys, os, re, json, time, datetime, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import refresh as R

KIND = "icims_jibe"
SLUG_HELP = "the career site's host, the one whose job search calls /api/jobs, e.g. careers.rivian.com"
# The whole board is read, five seconds a page where the site asks for that, so this list is kept to
# employers whose jobs are largely in Utah. EchoStar (jobs.echostar.com), Rivian (careers.rivian.com),
# Gallagher (jobs.ajg.com) and Aon (jobs.aon.com) read fine too, at six to thirteen pages for a handful of Utah rows.
EMPLOYERS = {"Glacier Bancorp (Altabank)": "www.gbcijobs.com", "SkyWest Airlines": "jobs.skywest.com",
             "Eide Bailly": "careers.eidebailly.com", "Clyde Companies": "careers.clydeinc.com"}
INSTITUTION = False
AGGREGATOR = False

PAGE = 100                                    # the most the API accepts: a larger limit answers HTTP 422
_US = ("US", "PR", "GU", "VI", "AS", "MP")    # US territories are not abroad
# A tag that marks the posting itself as internal ("Internal", "Internal / Pathfinder Only"). A category
# tag such as "Internal Audit" is a department, and those jobs are open to everyone.
_INTERNAL = re.compile(r"\s*internal(?:\s+(?:only|applicants?|candidates?|employees?|posting))*\s*(?:$|[/|(,;:-])", re.I)

def _day(stamp):
    """The local date of one of the feed's UTC timestamps: "2026-10-10T03:03:00+0000" is the evening of
    the 9th in Utah, so a posting that comes down then closes on the 9th, not the 10th."""
    s = re.sub(r"\.\d+", "", str(stamp or "").strip())
    try: return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z").astimezone().date().isoformat()
    except ValueError: pass
    try: return datetime.date.fromisoformat(s[:10]).isoformat()      # a bare date, or a time with no zone
    except ValueError: return None

def _place(p):
    """"City, ST" for one of a job's locations. A foreign one is marked in the words the location rules read."""
    city, state, country = [(p.get(k) or "").strip() for k in ("city", "state", "country")]
    code = (p.get("country_code") or ("US" if country in ("", "United States") else "")).upper()
    if code in _US:
        if state.endswith(", DC"): state = "DC"          # Rivian files the District under the state "Washington, DC"
        return R.city_state(city, state)
    land = re.sub(r"[()]", "", country or code)   # "Korea (Republic of)" would hide the mark from the location rules
    return f"{', '.join(x for x in (city, state) if x)} ({land}, abroad)".strip()

def _where(j):
    places = [j] + [a for a in j.get("additional_locations") or [] if isinstance(a, dict)]
    parts = list(dict.fromkeys(p for p in map(_place, places) if p))
    # location_type "ANY" is how Jibe marks a work-from-home job. The city stays in the row: it is where
    # the hire has to live. A remote job in another country must not read as a remote US one.
    remote = j.get("location_type") == "ANY" or re.search(r"\bremote\b", j.get("location_name") or "", re.I)
    if remote and not (parts and all(R.ABROAD.search(p) for p in parts)): parts.insert(0, "Remote")
    return "; ".join(parts)

def fetch(slug):
    """Return every open job as [(title, location, url, closes, degree, extra)]."""
    host = slug.strip().lower()
    jobs, page = [], 1
    while len(jobs) < 6000:
        body = R.curl_text(f"https://{host}/api/jobs?limit={PAGE}&page={page}", timeout=60)
        try: d = json.loads(body)
        except ValueError: raise RuntimeError(f"unexpected reply (not JSON from {host}/api/jobs: is this a Jibe career site?)")
        R.need(isinstance(d, dict) and isinstance(d.get("jobs"), list) and isinstance(d.get("totalCount"), int), "no jobs list")
        batch = [j.get("data") for j in d["jobs"] if isinstance(j, dict) and isinstance(j.get("data"), dict)]
        R.need(len(batch) == len(d["jobs"]), "a job without its data")
        jobs += batch
        if len(batch) < PAGE or len(jobs) >= d["totalCount"]: break
        page += 1
        time.sleep(0.3)
    # A short page is the end of the list only if the count agrees. Jobs open and close while the pages
    # are read, so a few either way is normal. A site that ignored page= would send the first page again
    # and again, which the count alone cannot tell from a full read.
    total, different = d["totalCount"], len({j.get("slug") for j in jobs})
    R.need(len(jobs) >= 6000 or abs(total - len(jobs)) <= max(5, total // 50), f"read {len(jobs)} of {total} jobs")
    R.need(len(jobs) - different <= max(5, total // 50), f"the pages repeat each other: {different} jobs in {len(jobs)} rows")
    if total > len(jobs) + 5: R.PARTIAL[slug] = f"read the first {len(jobs)} of {total} jobs"
    rows = []
    for j in jobs:
        title, loc = " ".join(str(j.get("title") or "").split()), _where(j)
        if not (title and j.get("slug")): continue
        keep = R.classify(title, loc, KIND) or R.experienced(title, loc, KIND)
        text = j.get("description") if keep else None        # the description repeats the qualifications field
        tags = [str(t) for k, v in j.items() if k.startswith("tags") and isinstance(v, list) for t in v]
        rows.append((title, loc, f"https://{host}/jobs/{j['slug']}",
                     _day(j.get("posting_expiry_date")), R.degree_flag(text),
                     {"posted": _day(j.get("posted_date")), "yrs": R.min_years(text),
                      # EchoStar tags a posting "Internal / Pathfinder Only" and still shows it to everyone
                      "internal": bool(j.get("internal")) or any(_INTERNAL.match(t) for t in tags),
                      "company": None}))
    return R._dedupe(rows)

if __name__ == "__main__":
    for name, slug in EMPLOYERS.items():
        rows = fetch(slug)
        kept = [r for r in rows if R.classify(r[0], r[1], KIND) or R.experienced(r[0], r[1], KIND)]
        print(f"{name}: {len(rows)} jobs, {sum(1 for r in rows if R.HOME.search(r[1] or ''))} in Utah, {len(kept)} kept")
        for r in kept[:5]: print("   ", r[0], "|", r[1], "|", r[2], "|", r[3], "|", r[5])
