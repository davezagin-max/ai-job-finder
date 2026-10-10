"""SmartRecruiters: the vendor's Posting API (api.smartrecruiters.com/v1/companies/ID/postings), which its documentation
lists under "No authentication" as public data, so no key or visitor token is sent. The list carries no posting text, so
the record of each role worth publishing is read too. The slug is the company identifier in the employer's posting links."""
import sys, os, re, json, time, datetime, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import refresh as R

KIND = "smartrecruiters"
SLUG_HELP = "the company identifier in the employer's posting links: jobs.smartrecruiters.com/Cricut/7440001... gives Cricut"
EMPLOYERS = {"Cricut": "Cricut", "Nearmap": "Nearmap", "HireVue": "HireVue"}
INSTITUTION = False
AGGREGATOR = False

API  = "https://api.smartrecruiters.com/v1/companies/"
LINK = re.compile(r"jobs\.smartrecruiters\.com/([^/?#]+)/(\d+)")
_US  = {"us", "pr", "gu", "vi", "as", "mp"}      # US territories are not abroad
# Employers with no office to name type the country where the city and state go ("United States, UNITED STATES")
_NATION = re.compile(r"^(?:u\.?s\.?(?:a\.?)?|united stat.*)$", re.I)
_MAX_DETAILS = 60

def _json(url):
    """One reply from the API. A reply that is not JSON (an error page, a bot check) is a failure."""
    body = R.curl_text(url)
    try: return json.loads(body)
    except ValueError: raise RuntimeError("api.smartrecruiters.com did not answer in JSON")

def _place(l):
    """"City, ST" for a US posting. A foreign one is marked in the words the location rules read,
    because "Senai, Johor" or "Alliston, ON" on its own would pass for a place in the US."""
    city, region, cc = [(l.get(k) or "").strip() for k in ("city", "region", "country")]
    if cc and cc.lower() not in _US:
        # fullLocation is "City, Region, Country name", and the name reads better than the two-letter code.
        # Brackets are taken out of it: the rules look for one "(..., abroad)" with none inside.
        full = (l.get("fullLocation") or "").split(",", 2)
        country = re.sub(r"[()]", "", full[2]).strip() if len(full) == 3 and full[2].strip() else cc.upper()
        # A ";" or "|" typed into the city would split the place in two, and only the last half would be marked
        place = re.sub(r"\s*[;|]\s*", " / ", ", ".join(p for p in (city, region) if p))
        return f"{place} ({'remote, ' if l.get('remote') else ''}{country}, abroad)".strip()
    city, region = ["" if _NATION.match(p) else p for p in (city, region)]
    # city_state turns a spelled-out state into its code ("Lehi, Utah"). A city with no state gets the
    # country instead, so that "Melbourne" or "Vienna" alone is not taken for a place abroad.
    place = R.city_state(city, region or (cc.upper() if city else ""))
    # A remote role still names a city (the office it belongs to), so both are kept
    if l.get("remote"): return "; ".join(dict.fromkeys(p for p in ("Remote, US" if cc else "Remote", place) if p))
    return place or cc.upper()

def _day(stamp):
    """The local date of the API's UTC timestamp: "2026-10-09T05:53:59.222Z" is still the 8th in Utah,
    and a role released this evening must not be dated tomorrow."""
    m = re.match(r"\d{4}-\d\d-\d\d", str(stamp or ""))
    if not m: return None
    # The fraction is dropped first: Python 3.9 reads three or six digits of it and nothing else
    try: return datetime.datetime.fromisoformat(re.sub(r"\.\d+", "", stamp).replace("Z", "+00:00")).astimezone().date().isoformat()
    except ValueError: return m.group(0)

def _text(d):
    """The posting's own words, each section under its heading. The company description is left out:
    it is the same on every posting and talks about the employer, not the role."""
    s = (d.get("jobAd") or {}).get("sections") or {}
    return "\n".join(f"<h3>{s[k].get('title') or ''}</h3>\n{s[k].get('text') or ''}"
                     for k in ("jobDescription", "qualifications", "additionalInformation") if isinstance(s.get(k), dict))

def fetch(slug):
    """Return every open job as [(title, location, url, closes, degree, extra)]."""
    api = API + urllib.parse.quote(slug, safe="")
    posts, total, notes = [], 0, []
    for off in range(0, 6000, 100):                  # 100 is the largest page the API gives; hard cap 6,000 rows
        d = R.patient(_json, f"{api}/postings?limit=100&offset={off}")
        R.need(isinstance(d, dict) and isinstance(d.get("content"), list) and isinstance(d.get("totalFound"), int), "not a posting list")
        posts += d["content"]; total = d["totalFound"]
        if len(d["content"]) < 100 or off + 100 >= total: break
        time.sleep(0.3)
    R.need(len(posts) >= min(total, 6000), f"only {len(posts)} of {total} postings came back")
    if total > 6000: notes.append(f"the first 6,000 of {total} jobs read")
    if not posts:
        # A name the API does not know answers exactly like an employer with no openings (HTTP 200 and
        # an empty list). The company's department list, a public endpoint on the same API, tells them
        # apart: it answers 404 for an unknown company.
        code, _ = R.curl_resp(f"{api}/departments")
        if code == "404": raise RuntimeError(f"SmartRecruiters has no company named '{slug}'")
        if code != "200": raise RuntimeError(f"HTTP {code} from api.smartrecruiters.com")
        return []
    rows = []
    for j in posts:
        R.need(isinstance(j, dict) and j.get("id") and j.get("name"), "a posting without an id or a name")
        co = (j.get("company") or {}).get("identifier") or slug
        rows.append([re.sub(r"\s+", " ", j["name"]).strip(), _place(j.get("location") or {}),
                     f"https://jobs.smartrecruiters.com/{co}/{j['id']}", None, None,   # the API states no closing date
                     {"posted": _day(j.get("releasedDate")), "yrs": None,
                      # without a key only public postings come back, so this is a guard, not a filter
                      "internal": (j.get("visibility") or "PUBLIC").upper() != "PUBLIC", "company": None}])
    rows = R._dedupe(rows)
    # Years and degree are in the posting text, which only the per-posting record has. Roles near home
    # are read first, so the cap, when it bites, falls on the ones furthest away. One at a time with a
    # short pause: the vendor's stated limits are 10 requests a second and 8 at once, and several of
    # its boards are read side by side.
    kept = [r for r in rows if R.classify(r[0], r[1], KIND) or R.experienced(r[0], r[1], KIND)]
    kept.sort(key=lambda r: {"home": 0, "remote": 1}.get(R.where(r[1]), 2))
    todo, missed, streak = kept[:_MAX_DETAILS], 0, 0
    for i, r in enumerate(todo):
        try:
            d = R.patient(_json, f"{api}/postings/{r[2].rsplit('/', 1)[-1]}", slots=R._DETAIL_SLOTS)
            R.need(isinstance(d, dict) and isinstance(d.get("jobAd"), dict), "a posting record without a job ad")
        except Exception:
            # A failed read keeps the row as listed, as the Workday reader does: the job is real and only its
            # years and degree stay unknown. Losing the whole board over one record would hide this week's new
            # roles. Three failures in a row mean the API is turning the script away, so it stops asking.
            missed, streak = missed + 1, streak + 1
            if streak == 3: missed += len(todo) - i - 1; break
            continue
        streak, text = 0, _text(d)
        r[4], r[5]["yrs"] = R.degree_flag(text), R.min_years(text)
        time.sleep(0.2)
    if len(kept) > _MAX_DETAILS: notes.append(f"read details for the first {_MAX_DETAILS} of {len(kept)} kept roles")
    if missed: notes.append(f"the posting text of {missed} kept role{'s' if missed > 1 else ''} could not be read")
    if notes: R.PARTIAL[slug] = "; ".join(notes)
    return R._dedupe([tuple(r) for r in rows])

def link_state(url):
    """'live', 'dead' or 'unknown' for one posting URL of this system. Return 'unknown' whenever unsure."""
    m = LINK.search(url)
    if not m: return "unknown"
    try: code, body = R.curl_resp(f"{API}{m.group(1)}/postings/{m.group(2)}")
    except Exception: return "unknown"
    # An id the API never had is a 404 in its own JSON; any other 404 is a problem with the request
    if code == "404": return "dead" if '"RESOURCE_NOT_FOUND"' in body else "unknown"
    if code != "200": return "unknown"
    # A posting taken down keeps answering 200, with "active": false (and its public page keeps answering 200 too)
    try: active = json.loads(body).get("active")
    except (ValueError, AttributeError): return "unknown"
    return "live" if active is True else "dead" if active is False else "unknown"

if __name__ == "__main__":
    for name, slug in EMPLOYERS.items():
        rows = fetch(slug)
        kept = [r for r in rows if R.classify(r[0], r[1], KIND) or R.experienced(r[0], r[1], KIND)]
        print(f"{name}: {len(rows)} jobs, {sum(1 for r in rows if R.HOME.search(r[1] or ''))} in Utah, {len(kept)} kept")
        for r in kept[:5]: print("   ", r[0], "|", r[1], "|", r[2], "|", r[3], "|", r[5])
