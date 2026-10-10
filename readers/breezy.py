"""Breezy HR: every careers portal answers COMPANY.breezy.hr/json with its whole board in one JSON array,
and ?verbose=true adds each posting's description, so one request reads an employer.
The slug is the breezy.hr subdomain ("kenect" for https://kenect.breezy.hr)."""
import sys, os, re, json, time, datetime, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import refresh as R

KIND = "breezy"
SLUG_HELP = 'the breezy.hr subdomain of the careers portal: "kenect" for https://kenect.breezy.hr'
EMPLOYERS = {"Kenect": "kenect", "Motivosity": "motivosity", "SalesRabbit": "salesrabbit", "Wavetronix": "wavetronix"}
INSTITUTION = False
AGGREGATOR = False

def _board(slug, verbose=False):
    """The portal's position list. There is no paging: one array holds the whole board (106 on the largest seen)."""
    url = f"https://{slug}.breezy.hr/json" + ("?verbose=true" if verbose else "")
    try: d = json.loads(R.curl_text(url, timeout=60))
    except ValueError: raise RuntimeError(f"unexpected reply (not JSON) from {slug}.breezy.hr") from None
    R.need(isinstance(d, list) and all(isinstance(j, dict) and j.get("id") and j.get("name") for j in d), "not a list of positions")
    return d

def _state(l):
    """The state of a US office saved without one, from the street address kept in the same record.
    Kenect has such an office: two of its rows read "Pleasant Grove, US" beside "..., Pleasant Grove, UT 84062, USA"."""
    a = l.get("streetAddress") if isinstance(l.get("streetAddress"), dict) else {}
    parts = [c.get("short_name") for c in a.get("components") or [] if isinstance(c, dict) and "administrative_area_level_1" in (c.get("types") or [])]
    m = re.search(r",\s*([A-Z]{2})\s+\d{5}", a.get("location") or "")
    st = (parts[0] if parts else m.group(1) if m else "") or ""
    return st if re.fullmatch(R._STATES, st) else ""

def _place(l):
    """One location record as "City, ST", with "Remote, " in front of a remote one. A location in another
    country is marked the way the Workday reader marks one ("Utrecht, Netherlands (NL, abroad)"), so a
    province code such as Utrecht's "UT" is never read as Utah."""
    country = l.get("country") if isinstance(l.get("country"), dict) else {}
    state = l.get("state") if isinstance(l.get("state"), dict) else {}
    code, land = (country.get("id") or "").strip(), (country.get("name") or "").strip()
    city, st = (l.get("city") or "").strip(), (state.get("id") or "").strip()
    if code == "US": place = ", ".join(p for p in (city, st or _state(l) or "US") if p)
    # "worldwide" is a country id of its own, and a US territory is not abroad. A record with no country
    # (none seen) keeps its state only when the feed spells out a US one beside the code.
    elif code in ("", "worldwide", "PR", "GU", "VI", "AS", "MP"):
        us = st if not code and R.STATE_NAMES.get(state.get("name")) == st else ""
        place = ", ".join(p for p in (city, us, land) if p) or (l.get("name") or "").strip()
    else: place = ", ".join(p for p in (city, land or code) if p) + f" ({code}, abroad)"
    # is_remote is also set on "Hybrid (Some remote, some in person)", which is an office job
    if l.get("is_remote") and "hybrid" not in json.dumps(l.get("remote_details") or "").lower():
        place = "Remote, " + place if place else "Remote"
    return re.sub(r"\s*[;|]\s*", ", ", place)       # a ";" typed into a city would be read as a second location

def fetch(slug):
    """Return every open job as [(title, location, url, closes, degree, extra)]."""
    rows = []
    for j in _board(slug, verbose=True)[:6000]:
        # "locations" lists every site of a multi-site posting; an older posting has only "location"
        places = [_place(l) for l in (j.get("locations") or [j.get("location") or {}]) if isinstance(l, dict)]
        text = j.get("description")
        day = re.match(r"\d{4}-\d\d-\d\d", str(j.get("published_date") or ""))     # "2026-09-23T17:57:53.192Z"
        rows.append((re.sub(r"\s+", " ", j["name"]).strip(), "; ".join(dict.fromkeys(p for p in places if p)),
                     j.get("url") or f"https://{slug}.breezy.hr/p/{j.get('friendly_id') or j['id']}",
                     None,                                   # Breezy has no closing date
                     R.degree_flag(text),
                     {"posted": day.group(0) if day else None, "yrs": R.min_years(text), "internal": False, "company": None}))
    return R._dedupe(rows)

BREEZY_LINK = re.compile(r"https://([\w-]+)\.breezy\.hr/p/([0-9a-f]{8,})")
def link_state(url):
    """'live', 'dead' or 'unknown' for one posting URL of this system. Return 'unknown' whenever unsure."""
    m = BREEZY_LINK.match(url or "")
    if not m: return "unknown"
    # A posting that is gone answers 302 to the portal's front page, which is a 200 once followed, so
    # the status says nothing. The portal's own list does: a posting on it is open.
    try:
        if m.group(2) in {j["id"] for j in _board(m.group(1))}: return "live"
        # Off the list is not yet dead: an employer can keep a posting off its portal and still take
        # applications by direct link. Its own page settles it, because the front page a dead link
        # lands on does not carry the posting's id and a posting's page does.
        code, page = R.curl_resp(url, accept="text/html")
    except Exception: return "unknown"
    return "dead" if code == "200" and m.group(2) not in page else "unknown"

if __name__ == "__main__":
    for name, slug in EMPLOYERS.items():
        rows = fetch(slug)
        kept = [r for r in rows if R.classify(r[0], r[1], KIND) or R.experienced(r[0], r[1], KIND)]
        print(f"{name}: {len(rows)} jobs, {sum(1 for r in rows if R.HOME.search(r[1] or ''))} in Utah, {len(kept)} kept")
        for r in kept[:5]: print("   ", r[0], "|", r[1], "|", r[2], "|", r[3], "|", r[5])
