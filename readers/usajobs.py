"""USAJOBS (federal jobs): the search call the website's own results page makes, POST
www.usajobs.gov/Search/ExecuteSearch, with no key, token or sign-in. The slug is the state to search, by its
full name ("Utah"); one slug returns the announcements of every agency that the site lists for that state and
that are open to the public or to recent graduates. The list names one duty station and a count, so each kept
role's own page is read for its stations and its text. "Location negotiable" notices are nationwide, not local."""
import sys, os, re, json, time, datetime, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import refresh as R

KIND = "usajobs"
SLUG_HELP = 'the state to search, by its full name as usajobs.gov spells it: "Utah" ("UT", a city or a misspelling is refused)'
EMPLOYERS = {"USAJOBS": "Utah"}
INSTITUTION = False   # federal titles do not use those words as description: "Recent Graduate" in one names the hiring program
AGGREGATOR = True     # True when one slug returns the jobs of many employers

# The documented API (data.usajobs.gov) needs a key and its robots.txt closes that whole host, so this
# is the search the results page itself makes, on a path the site's robots.txt leaves open.
SEARCH = "https://www.usajobs.gov/Search/ExecuteSearch"
LINK   = re.compile(r"usajobs\.gov(?::443)?/job/(\d+)")
# "public" leaves out announcements open only to current federal staff, veterans and the like (236 of
# Utah's 626 on 2026-10-09), and "graduates" adds the Recent Graduates program. Asked for together, the
# site returns either.
PATHS  = ["public", "graduates"]
PAGE   = 500          # the site's own page asks for 25; 500 was accepted and is all of Utah in one request
MAX_DETAILS = 60
# An announcement whose duty station is agreed after the offer. The site files every one of them under twenty
# stand-in places, the first of which is Salt Lake City, so a search for Utah returns them all (182 of 389
# rows on 2026-10-09; a search for Idaho returned none) although their own pages name no station in Utah:
# "1 vacancy in the following location: Location Negotiable After Selection". They are jobs anywhere in the
# country, and are written that way instead of as jobs in Salt Lake City.
NEGOTIABLE = "Location Negotiable After Selection"
ANYWHERE   = "Location negotiable after selection, US"

def _search(place, paths, page):
    """One page of the site's search for a place. A filter left out of the body is not applied."""
    # "Recently posted" order, newest first: paging over a fixed order skips nothing, and when the detail
    # cap cuts the reading short it cuts the notices that have been open for a year, not this week's.
    body = {"LocationName": [place], "HiringPath": paths, "SortField": "startdate", "SortDirection": "desc",
            "Page": str(page), "ResultsPerPage": str(PAGE)}
    try:
        d = R.curl(SEARCH, body, timeout=60)
    except ValueError:        # an error page is not a job list (this site sends its error pages compressed)
        raise RuntimeError("usajobs.gov did not answer the search in JSON")
    R.need(isinstance(d, dict) and isinstance(d.get("Jobs"), list) and isinstance(d.get("Pager"), dict)
           and str(d.get("Total", "")).isdigit(), "not a search result")
    return d

def _posting(url):
    """The data block every announcement page carries: its text and, where the page lists them, its duty
    stations. "negotiable" is added: whether the page's own list of locations has a negotiable entry,
    which the data block leaves out."""
    page = R.curl_text(url, timeout=45, accept="text/html")
    m = re.search(r'<script type="application/ld[^"]*json"[^>]*>(.*?)</script>', page, re.S)
    R.need(m, "an announcement page without its data block")
    d = json.loads(m.group(1))
    R.need(isinstance(d, dict) and d.get("@type") == "JobPosting", "not an announcement's data block")
    d["negotiable"] = bool(re.search(r'data-location-text="[^"]*' + NEGOTIABLE, page, re.I))
    return d

def _spot(name):
    """"Hill AFB, Utah" as "Hill AFB, UT". A territory or a country is left as the feed writes it."""
    name = " ".join((name or "").split())
    if name.startswith("Anywhere in the U.S."): return "Remote, US"       # "Anywhere in the U.S. (remote job), United States"
    city, _, state = name.rpartition(", ")
    return f"{city}, {R.STATE_NAMES[state]}" if city and state in R.STATE_NAMES else name

def _here(spot, state):
    """True for a station written "City, ST" in the state searched."""
    return spot.endswith(", " + R.STATE_NAMES[state])

def _joined(shown, n):
    """The places named, then a count of the rest: one Air Force notice has sixty bases, the FAA's 1,176."""
    return "; ".join(shown + ([f"+{n - len(shown)} more"] if n > len(shown) else []))

def _listed(j, state):
    """The location as the list gives it: one duty station and how many there are. A multi-site
    announcement names its first station only, which is rarely the one in the state searched. The search
    matched it all the same, so the state goes first and says where it came from. That keeps the role
    among those whose pages are read, and the page then names the station (or shows there is none)."""
    first, label = _spot(j.get("LocationName")), " ".join((j.get("Location") or "").split())
    if label.lower().startswith(NEGOTIABLE.lower()): return ANYWHERE     # its "Salt Lake City, Utah" is a stand-in, not a station
    n = int(j["PositionLocationCount"]) if str(j.get("PositionLocationCount")).isdigit() else 1
    if n <= 1: return first or label
    here = _here(first, state)
    # The agency-wide notices ("May be filled in various FAA duty locations") do not list their stations,
    # not even on their own page, so the label is kept.
    if label != "Multiple Locations": return f"{first if here else state} ({label}, {n} locations)"
    return _joined([first] if here else [f"{state} (per the site's search)", first], n)

def _stations(d, state):
    """The duty stations an announcement's page names, those in the state searched first."""
    out, spots = [], d.get("jobLocation") or []
    for p in spots if isinstance(spots, list) else [spots]:
        a = (p.get("address") or {}) if isinstance(p, dict) else {}
        s = ", ".join(x.strip() for x in (str(a.get("addressLocality") or ""), str(a.get("addressRegion") or a.get("addressCountry") or "")) if x.strip())
        if s and s not in out: out.append(s)
    return sorted(out, key=lambda s: not _here(s, state))

def _text(d):
    """The announcement's own words under the headings its page uses."""
    parts = (("Summary", "description"), ("Duties", "responsibilities"), ("Qualifications", "qualifications"), ("Education", "educationRequirements"))
    return "\n".join(f"<h3>{h}</h3>\n{d[k]}" for h, k in parts if isinstance(d.get(k), str) and d[k].strip()) or None

def _day(stamp):
    """"2026-10-22T23:59:59.9970" as the day."""
    return stamp[:10] if isinstance(stamp, str) and re.match(r"\d{4}-\d\d-\d\d", stamp) else None

def fetch(slug):
    """Return every open job as [(title, location, url, closes, degree, extra)]."""
    # A state, because the stations of that state are what the reading below looks for.
    place = {name.lower(): name for name in R.STATE_NAMES}.get(" ".join(slug.split()).lower())
    if not place: raise RuntimeError(f"the usajobs slug is a state's full name such as 'Utah', not '{slug}'")
    jobs, page, total = [], 1, 0
    while True:
        d = R.patient(_search, place, PATHS, page)
        # A place the site does not know by that name is quietly read as the nearest one it does ("Utahh"
        # became a circle around a point in Utah, 21 jobs), which would pass for a short list.
        read_as = [str(x) for x in d.get("ResolvedLocations") or []]
        R.need([x.lower() for x in read_as] == [place.lower()], f"usajobs.gov read the place '{place}' as {read_as}")
        got, pager, total = d["Jobs"], d["Pager"], int(d["Total"])
        jobs += got
        if not got or len(got) < int(pager.get("ItemsPerPage") or 0) or page >= int(pager.get("NumberOfPages") or 0) or len(jobs) >= 6000: break
        page += 1
        time.sleep(0.3)
    if not jobs:
        # A place the site does not know and a place with nothing open answer alike: no rows, and the
        # name echoed back. Asked again without the hiring-path filter, a real state always has
        # announcements, and a name the site does not know still has none.
        R.need(int(_search(place, [], 1)["Total"]) > 0, f"usajobs.gov has no announcements at all for '{place}': check the spelling")
        return []
    listed = {}
    for j in jobs[:6000]:
        m, title = LINK.search(j.get("PositionURI") or ""), " ".join((j.get("Title") or "").split())
        R.need(m and title, "an announcement without a title or link")
        url = "https://www.usajobs.gov/job/" + m.group(1)        # the feed writes the port into its links
        listed.setdefault(url, (title, _listed(j, place), url, j))
    listed = list(listed.values())
    # Only the roles that will be published are worth a page each, one at a time.
    kept = [x for x in listed if R.classify(x[0], x[1], KIND) or R.experienced(x[0], x[1], KIND)]
    if len(kept) > MAX_DETAILS: R.PARTIAL[slug] = f"read details for the first {MAX_DETAILS} of {len(kept)} kept roles"
    pages, failed = {}, 0
    for _, _, url, _ in kept[:MAX_DETAILS]:
        try: pages[url] = R.patient(_posting, url, slots=R._DETAIL_SLOTS)
        except R.OffLimits: raise
        except Exception:
            failed += 1                            # the row is kept as listed rather than dropped
            if failed == 5: break                  # the page has changed or the site is away: stop asking
        time.sleep(0.3)
    if failed: R.PARTIAL[slug] = f"read details for {len(pages)} of {len(kept)} kept roles ({failed} announcement pages could not be read)"
    if len(listed) < total: R.PARTIAL[slug] = f"{len(listed)} of {total} announcements read"      # the gap that matters most is said last
    rows = []
    for title, loc, url, j in listed:
        info = pages.get(url) or {}
        stations = _stations(info, place)
        home = [s for s in stations if _here(s, place)]
        # The page is the better witness. It names a station here, or it names stations elsewhere plus a
        # negotiable entry, and then the search matched that entry's stand-ins and this is not a job in the
        # state. A page that settles nothing (no stations in its data, or stations elsewhere and no
        # negotiable entry to explain the match) leaves the list's wording alone.
        if home or (stations and info.get("negotiable")):
            loc = "; ".join([_joined(stations if len(stations) <= 4 else home or stations[:4], len(stations))] + [ANYWHERE] * bool(info.get("negotiable")))
        paths = {h.get("Code") for h in j.get("HiringPath") or [] if isinstance(h, dict)}
        # No years are read. A federal announcement states experience grade by grade ("one year equivalent
        # to GS-12") and lets education stand in for it, so the years reader finds the wrong numbers: it
        # read a Recent Graduates posting as four years (a veterans' service clause) and another as two
        # (years of graduate study), either of which would hide the job from a new graduate.
        rows.append((title, loc, url, _day(j.get("PositionEndDate")), R.degree_flag(_text(info)),
                     {"posted": _day(j.get("PositionStartDate")), "yrs": None,
                      "internal": bool(paths) and not (paths & set(PATHS)),
                      "company": (j.get("Agency") or j.get("Department") or "").strip() or None}))
    return R._dedupe(rows)

def link_state(url):
    """'live', 'dead' or 'unknown' for one posting URL of this system. Return 'unknown' whenever unsure."""
    # A closed announcement keeps its page (HTTP 200) for years, so the page's own status is read: the
    # badge says "Accepting applications" while it is open, and the banner says when it has closed.
    # An id the site does not have answers 404 with its Not Found page.
    m = LINK.search(url or "")
    if not m: return "unknown"
    try: code, page = R.curl_resp("https://www.usajobs.gov/job/" + m.group(1), timeout=45, accept="text/html")
    except Exception: return "unknown"
    if code == "404" and "USAJOBS - Not Found" in page: return "dead"
    if code != "200" or "USAJOBS - Job Announcement" not in page: return "unknown"
    if re.search(r'class="[^"]*\bbadge-success\b[^"]*">\s*Accepting applications\s*<', page): return "live"
    if "This job announcement has closed" in page: return "dead"
    return "unknown"

if __name__ == "__main__":
    for name, slug in EMPLOYERS.items():
        rows = fetch(slug)
        kept = [r for r in rows if R.classify(r[0], r[1], KIND) or R.experienced(r[0], r[1], KIND)]
        print(f"{name}: {len(rows)} jobs, {sum(1 for r in rows if R.HOME.search(r[1] or ''))} in Utah, {len(kept)} kept")
        for r in kept[:5]: print("   ", r[0], "|", r[1], "|", r[2], "|", r[3], "|", r[5])
