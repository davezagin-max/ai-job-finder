"""Amazon Jobs: the search behind amazon.jobs answers in JSON (/en/search.json), a hundred jobs a request, each
with its sites, posting date and basic qualifications, so no posting page is ever opened. The slug is a US state
name as the site's own state filter spells it ("Utah"): every job with a site in that state comes back, the
national ones that merely list it included. Roles open to work from home anywhere in the US name no state, so
they are in no state's list."""
import sys, os, re, json, time, datetime, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import refresh as R

KIND = "amazon"
SLUG_HELP = 'a US state name exactly as the state filter on amazon.jobs spells it, capitals included: "Utah"'
EMPLOYERS = {"Amazon": "Utah"}
INSTITUTION = False
AGGREGATOR = False

AMAZON_SEARCH = "https://www.amazon.jobs/en/search.json?"
AMAZON_PAGE = 100          # jobs asked for in one request
AMAZON_LINK = re.compile(r"amazon\.jobs/(?:[a-z]{2}(?:-[a-z]{2})?/)?jobs/(\d+)")

def _amazon_search(query):
    """One reply of the search. A page of HTML here is an error or a bot check, never a job list."""
    try: d = json.loads(R.curl_text(AMAZON_SEARCH + urllib.parse.urlencode(query), timeout=60))
    except ValueError: raise RuntimeError("amazon.jobs did not answer in JSON")
    R.need(isinstance(d, dict) and not d.get("error") and isinstance(d.get("hits"), int)
           and isinstance(d.get("jobs"), list), "no job list in the search reply")
    return d

def _amazon_place(site):
    """One site of a job as "City, ST". A work-from-home site reads "Remote, ST": the feed ties it to a state."""
    city = "Remote" if site.get("type") == "VIRTUAL" else re.sub(r"\s+", " ", site.get("city") or "").strip()
    if city.isupper(): city = city.title()             # a few arrive in capitals ("COLUMBUS")
    if site.get("countryIso2a") == "US" or site.get("normalizedCountryCode") == "USA":
        # The region is the state's code. Were it ever blank, the state's name still says which state.
        tail = site.get("region") or R.STATE_NAMES.get(site.get("normalizedStateName") or "") or "US"
    else: tail = site.get("normalizedCountryName") or ""   # no region code abroad: "Chennai, TN" would read as Tennessee
    return ", ".join(x for x in (city, tail.strip()) if x)

def _amazon_row(j, state):
    """(the row, whether its location names the state)."""
    R.need(isinstance(j, dict) and j.get("title") and str(j.get("job_path") or "").startswith("/"), "a job without a title or a link")
    places = []
    for s in j.get("locations") or []:                 # each entry is itself a JSON string
        try: s = json.loads(s) if isinstance(s, str) else s
        except ValueError: continue
        if isinstance(s, dict): places.append(_amazon_place(s))
    places = [p for p in dict.fromkeys(places) if p] or [R.city_state(j.get("city"), j.get("state")) or j.get("normalized_location") or ""]
    # The state asked for goes first: a national role lists up to ten sites, and the one here is the point.
    here = ", " + R.STATE_NAMES[state]
    places.sort(key=lambda p: not p.endswith(here))    # a stable sort, so the other sites keep the feed's order
    loc = "; ".join(places)
    try: posted = datetime.datetime.strptime(" ".join((j.get("posted_date") or "").split()), "%B %d, %Y").strftime("%Y-%m-%d")
    except ValueError: posted = None
    # Only the basic qualifications are read, never the preferred ones. They arrive without their heading,
    # so it is put back: under it min_years counts a bare "5+ years designing production lines" as the bar.
    quals = j.get("basic_qualifications") or ""
    title = re.sub(r"\s+", " ", re.sub(r"\s+,", ",", j["title"])).strip()   # the feed joins title and team as "Title , Team"
    row = (title, loc, "https://www.amazon.jobs" + j["job_path"], None, R.degree_flag(quals),
           {"posted": posted, "yrs": R.min_years("Basic qualifications<br/>" + quals) if quals else None,
            "internal": False, "company": None})       # the search only returns externally posted jobs
    # Judged on the location as written, so a feed that changes shape cannot pass as jobs in the state.
    return row, any(p.endswith(here) for p in places) or state in loc

def fetch(slug):
    """Return every open job as [(title, location, url, closes, degree, extra)]."""
    # The search answers a misspelt state ("utah", "Utahh") with an empty list, exactly as it would a state
    # with no openings. So the slug is checked against the names before anything is asked.
    state = slug.strip()
    if state not in R.STATE_NAMES:
        raise RuntimeError(f"amazon: '{slug}' is not a US state as amazon.jobs spells it (like 'Utah')")
    query = {"normalized_country_code[]": "USA", "normalized_state_name[]": state, "sort": "recent", "result_limit": AMAZON_PAGE}
    rows, off, hits, asked = [], 0, 0, 0
    while off < 6000 and asked < 150:                  # 150: were the site ever to hand out a few jobs a request
        if off: time.sleep(0.3)
        d = R.patient(_amazon_search, dict(query, offset=off)); asked += 1
        hits = d["hits"]
        page = [_amazon_row(j, state) for j in d["jobs"]]
        # A filter the site stopped understanding is ignored, and then every US job comes back.
        R.need(sum(named for _, named in page) * 2 >= len(page), f"jobs that are not in {state}")
        rows += [row for row, _ in page]
        off += len(page)                               # by what arrived, in case a reply is ever capped lower
        if not page or off >= hits: break
    R.need(rows or not hits, f"{hits} jobs counted and none listed")
    if off < hits: R.PARTIAL[slug] = f"{off} of {hits} jobs read"
    if not hits:
        # Nothing at all is either true or a state name the site no longer uses. Its own count of jobs
        # per state tells the two apart: it must still speak in these names, and leave this one out.
        d = R.patient(_amazon_search, {"normalized_country_code[]": "USA", "facets[]": "normalized_state_name", "result_limit": 1})
        counts = (d.get("facets") or {}).get("normalized_state_name_facet") or []
        counted = {name for c in counts if isinstance(c, dict) for name in c}
        R.need(counted & set(R.STATE_NAMES) and state not in counted, f"no jobs for {state}, which the site's own count per state does not bear out")
    return R._dedupe(rows)

def link_state(url):
    """'live', 'dead' or 'unknown' for one posting URL of this system. Return 'unknown' whenever unsure."""
    m = AMAZON_LINK.search(url)
    if not m: return "unknown"
    try: code, body = R.curl_resp(url, accept="text/html")
    except Exception: return "unknown"
    # A posting that is gone answers 404 with the site's own apology. A live one names its id in the page
    # title, which a 200 from anything else (a bot check, the search page) does not.
    if code == "404" and re.search(r"job you.{1,6}re looking for isn.{1,6}t available", body): return "dead"
    return "live" if code == "200" and f"Job ID: {m.group(1)}" in body else "unknown"

if __name__ == "__main__":
    for name, slug in EMPLOYERS.items():
        rows = fetch(slug)
        kept = [r for r in rows if R.classify(r[0], r[1], KIND) or R.experienced(r[0], r[1], KIND)]
        print(f"{name}: {len(rows)} jobs, {sum(1 for r in rows if R.HOME.search(r[1] or ''))} in Utah, {len(kept)} kept")
        for r in kept[:5]: print("   ", r[0], "|", r[1], "|", r[2], "|", r[3], "|", r[5])
