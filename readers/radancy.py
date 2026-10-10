"""Radancy TalentBrew career sites: the site's own "jobs in Utah" location page, plain server-rendered
HTML, read page by page. The slug is "host|organisation id", the number in every /job/ link on the site;
"host|organisation id|remote" reads the site's Remote page as well. The list gives title, first location
and link; each kept role's posting page says every place it is posted to, the posted date and the text.
No sign-in and no visitor token are involved."""
import sys, os, re, json, time, datetime, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import refresh as R

KIND = "radancy"
SLUG_HELP = ('host|organisation id, the number in every /job/ link on the site ("careers.unitedhealthgroup.com|34088"); '
             'add "|remote" to read the site\'s Remote page too')
EMPLOYERS = {
    # Adding "|remote" to a slug also reads the site's Remote list. For UnitedHealth that is fifty more
    # pages of two megabytes each, so it is left off: these two are read for their Utah jobs only.
    "UnitedHealth Group (Optum)": "careers.unitedhealthgroup.com|34088",
    "CommonSpirit Health (Holy Cross Hospitals)": "www.commonspirit.careers|35300",
}
INSTITUTION = False
# A hospital system: "Graduate" and "Campus" in its titles are plain description, not a new-grad program.
INSTITUTIONS = {"CommonSpirit Health (Holy Cross Hospitals)"}
AGGREGATOR = False

# A location page's key. PLACE is the GeoNames ids of the United States and of Utah, then the kind of
# place (3 is a state); REMOTE is the country Radancy made up for remote jobs, the same id on every site.
# Robots.txt on these sites closes the keyword search, so these pages are the only lists a script may
# read: a role that is neither in Utah nor remote is never seen.
# Retargeting the script means changing PLACE together with R.HOME_NAME (geonames.org has the ids).
PLACE, REMOTE = "6252001-5549030/3", "1000000000100/2"
MAX_PAGES, MAX_DETAILS = 90, 60      # together they keep one employer to about 150 requests
LINK = re.compile(r"^https://[^/]+/job/[^/]+/[^/]+/\d+/\d+/?$")   # /job/<city>/<title>/<organisation>/<job id>
_NAME = {code: name for name, code in R.STATE_NAMES.items()}
_US = ("United States", "US", "USA")
_TERRITORIES = ("Puerto Rico", "Guam", "U.S. Virgin Islands", "American Samoa", "Northern Mariana Islands")   # not abroad

def _text(html):
    return re.sub(r"\s+", " ", R.html_unescape(re.sub(r"<[^>]+>", " ", html or ""))).strip()

def _place(text, country=""):
    """Both 'Draper, Utah' and 'Midvale, UT, United States' become 'City, UT'. A state on its own is spelled out.
    country is a posting's own country field. A place in another country is marked the way the Workday
    reader marks one, in words the location rules read: 'Makati City, Metro Manila (Philippines, abroad)'."""
    bits = [b.strip() for b in text.split(",") if b.strip()]
    if country and country not in _US + _TERRITORIES + ("Remote",):
        return f"{', '.join(bits[:-1]) or country} ({country}, abroad)"
    if len(bits) > 1 and bits[-1] in _US: bits.pop()
    if len(bits) == 1: return _NAME.get(bits[0], bits[0])
    if bits: bits[-1] = R.STATE_NAMES.get(bits[-1], bits[-1])
    return ", ".join(bits)

def _where(places, tag):
    """One location string: "Remote" first when it is among the places, then each place as "City, ST".
    tag is what the page a job was listed on says of every job on it: the state's name, or "Remote"."""
    places = list(dict.fromkeys(p for p in places if p))
    # The list shows only a job's first location ("Denver, Colorado" for a Denver or Salt Lake City
    # role), and the Utah page lists nothing without a location in Utah. So say so when no place does.
    if not any(p == tag if tag == "Remote" else R.HOME.search(p) for p in places): places.append(tag)
    # The Remote page also lists remote work in Canada and the Philippines. When every place a job
    # names is abroad its "Remote" is marked abroad too, or the location rules would read it as US remote.
    named = [p for p in places if p != "Remote"]
    marks = [m.group(0) for m in map(R.ABROAD.search, named) if m]
    if named and len(marks) == len(named): places = [p if p != "Remote" else "Remote " + marks[0] for p in places]
    return "; ".join(sorted(places, key=lambda p: not p.startswith("Remote")))

def _day(text):
    try: return datetime.datetime.strptime(text.strip(), "%m/%d/%Y").date().isoformat()
    except ValueError: return None

def _listed(host, section, tag):
    """The rows of one results page. The markup around a result differs per employer, so the list is
    cut at every job link and each field is found by the class name all the templates share."""
    out = []
    for chunk in re.split(r'(?=<a [^>]*href="/job/)', section)[1:]:
        a = re.match(r'<a [^>]*href="(/job/[^"]+)"[^>]*>(.*?)</a>', chunk, re.S)
        R.need(a, "a job link that could not be read")
        h2 = re.search(r"<h\d[^>]*>(.*?)</h\d>", a.group(2), re.S)    # the title is the link's heading, or the link itself
        field = lambda name: _text((re.search(r'class="(?:[^"]* )?%s(?: [^"]*)?"[^>]*>(.*?)</(?:span|li|div|p)>' % name, chunk, re.S) or [0, ""])[1])
        title = _text(h2.group(1) if h2 else a.group(2))
        R.need(title and LINK.match(f"https://{host}{a.group(1)}"), "a result without a title or a job link")
        places = [_place(p) for p in re.sub(r"\s*\+\s*\d+ Other Locations?\s*$", "", field("job-location"), flags=re.I).split(";")]
        if re.match(r"remote\b", field("job-worksetting"), re.I): places.append("Remote")
        out.append((title, _where(places, tag), f"https://{host}{a.group(1)}", None, None,
                    {"posted": _day(field("job-date-posted")), "yrs": None, "internal": False, "company": None}))
    return out

def _results(html, host, org, place, page, tag):
    """(rows, the site's count of all results, its count of pages) from one page of a location list."""
    head = re.search(r'<section[^>]*\bid="search-results"[^>]*>', html)
    R.need(head, "no job search results on the page")
    at = dict(re.findall(r'data-([\w-]+)="([^"]*)"', head.group(0)))
    # The site answers a wrong organisation id with its own jobs, and curl follows a redirect
    # without saying so. So check that this is the page that was asked for.
    R.need(org in at.get("organization-ids", "").split(","), f"the site's organisation id is {at.get('organization-ids')!r}, not {org}")
    R.need(f"{at.get('facet-term')}/{at.get('facet-type')}" == place and at.get("current-page") == str(page),
           f"not page {page} of the {tag} location page")
    R.need(at.get("total-results", "").isdigit() and at.get("total-pages", "").isdigit(), "no result count")
    total, pages = int(at["total-results"]), int(at["total-pages"])
    per = int(at["records-per-page"]) if at.get("records-per-page", "").isdigit() else 1
    body = re.search(r'<section[^>]*\bid="search-results-list".*?</section>', html, re.S)
    found = _listed(host, body.group(0) if body else "", tag)
    # The page says how many results it holds, so a result this code cannot read fails here instead
    # of going missing. A page past the end (a job closed while paging) holds none and counts none.
    R.need(len(found) >= min(per, total - per * (page - 1)), f"{total} results counted but only {len(found)} found on page {page}")
    return found, total, pages

def _posting(url):
    """(places, posted, text) from a posting page: its location tag and its JSON-LD record."""
    html = R.curl_text(url, accept="text/html", timeout=60)
    for raw in re.findall(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S):
        try: d = json.loads(raw, strict=False)
        except ValueError: continue
        if isinstance(d, dict) and d.get("@type") == "JobPosting": break
    else:
        raise RuntimeError("no JobPosting record on the posting page")
    # Every place a job is posted to is in one tag, as "City~State~Country" with "Remote" as a country of
    # its own. The record has them too, but it leaves out a place that is only a country ("Canada"), so a
    # job that is remote within Canada would read as plain remote. It is the fallback.
    tag = re.search(r'<meta[^>]*\bname="gtm_tbcn_location"[^>]*\bcontent="([^"]*)"', html)
    if tag: spots = [s.split("~") for s in R.html_unescape(tag.group(1)).split("|")]
    else:
        spots = d.get("jobLocation") or []
        spots = [[((s or {}).get("address") or {}).get(k) for k in ("addressLocality", "addressRegion", "addressCountry")]
                 for s in (spots if isinstance(spots, list) else [spots])]
    places = ["Remote"] if d.get("jobLocationType") == "TELECOMMUTE" else []
    for spot in spots:
        spot = [x.strip() for x in spot if isinstance(x, str) and x.strip()]
        if spot: places.append(_place(", ".join(spot), spot[-1]))
    # The record's date and the "Date posted" a person reads on the page often differ, either way round
    # (a job that is posted again keeps one of them). The earlier one is how long the job has been open.
    shown = re.findall(r"<b>\s*(?:Date Posted|Post(?:ing|ed)? Date|Posted(?: On)?)\s*:?\s*</b>\s*:?\s*(\d{1,2}/\d{1,2}/\d{4})", html, re.I)
    days = [x for x in [str(d.get("datePosted") or "")[:10]] + [_day(x) for x in shown] if x and re.match(r"\d{4}-\d\d-\d\d$", x)]
    # CommonSpirit keeps its requirements in a field of their own, outside the description
    text = (d.get("description") or "") + ("<p>Qualifications:</p>" + d["qualifications"] if d.get("qualifications") else "")
    return places, min(days, default=None), text

def fetch(slug):
    """Return every open job as [(title, location, url, closes, degree, extra)]."""
    host, org, also = (slug.split("|") + ["", ""])[:3]
    R.need(host and org.isdigit() and also in ("", "remote") and slug.count("|") < 3, "the slug is host|organisation id, or host|organisation id|remote")
    lists = [(R.HOME_NAME.lower().replace(" ", "-"), PLACE, R.HOME_NAME)] + ([("remote", REMOTE, "Remote")] if also else [])
    rows, tags, asked, notes = [], {}, 0, []
    for name, place, tag in lists:
        base, page, count, mine = f"https://{host}/location/{name}-jobs/{org}/{place}", 1, None, set()
        while asked < MAX_PAGES and len(rows) < 6000:
            if asked: time.sleep(0.3)
            asked += 1
            # one slow reply in fifty pages must not lose the whole read, so a page is asked for up to three times
            html = R.patient(R.curl_text, base if page == 1 else f"{base}/{page}", None, 60, "text/html")
            found, count, pages = _results(html, host, org, place, page, tag)
            rows += found
            for r in found: mine.add(r[2]); tags.setdefault(r[2], tag)     # a job on both pages keeps the first one's row
            if not found or page >= pages: break
            page += 1
        else:
            notes.append(f"the {tag} page was cut short at {len(mine)} jobs" + (f" of {count}" if count else ""))
            continue
        # Jobs that open or close while paging move the rest by one, so a few can be missed. More than
        # a few means the paging itself is off, and a short read must never look like closures.
        R.need(len(mine) >= count * 0.9, f"read {len(mine)} of {count} jobs on the {tag} page")
        if len(mine) < count: notes.append(f"{len(mine)} of {count} jobs read on the {tag} page")
    rows = R._dedupe(rows)[:6000]
    # The posting page is read only for the roles the title rules keep. It is the one place that has
    # every location, the posted date and the text. Neither it nor the list states a closing date.
    kept = [i for i, r in enumerate(rows) if R.classify(r[0], r[1], KIND) or R.experienced(r[0], r[1], KIND)]
    if len(kept) > MAX_DETAILS: notes.append(f"read details for the first {MAX_DETAILS} of {len(kept)} kept roles")
    unread = 0
    for n, i in enumerate(kept[:MAX_DETAILS]):
        title, loc, url, closes, _, extra = rows[i]
        if n: time.sleep(0.3)
        try: places, posted, text = R.patient(_posting, url, slots=R._DETAIL_SLOTS)
        except R.OffLimits: unread += len(kept[:MAX_DETAILS]) - n; break    # closed to scripts: stop asking
        except Exception: unread += 1; continue          # a failed read keeps the row as listed
        if places and loc.startswith("Remote"): places.append("Remote")     # the list's work-setting flag still holds
        days = [x for x in (posted, extra["posted"]) if x]
        rows[i] = (title, _where(places, tags[url]) if places else loc, url, closes,
                   R.degree_flag(text), dict(extra, posted=min(days, default=None), yrs=R.min_years(text) or None))
    if unread: notes.append(f"{unread} posting page(s) could not be read, so their years and degree are unknown")
    if notes: R.PARTIAL[slug] = "; ".join(notes)
    return R._dedupe(rows)

def link_state(url):
    """'live', 'dead' or 'unknown' for one posting URL of this system. Return 'unknown' whenever unsure."""
    if not LINK.match(url or ""): return "unknown"
    try: code, body = R.curl_resp(url, accept="text/html")
    except Exception: return "unknown"
    # A job that is gone answers 404 with the site's "Custom Job Error" page; a live one carries its record.
    if code in ("404", "410") and "Custom Job Error" in body: return "dead"
    return "live" if code == "200" and '"JobPosting"' in body else "unknown"

if __name__ == "__main__":
    for name, slug in EMPLOYERS.items():
        rows = fetch(slug)
        kept = [r for r in rows if R.classify(r[0], r[1], KIND) or R.experienced(r[0], r[1], KIND)]
        print(f"{name}: {len(rows)} jobs, {sum(1 for r in rows if R.HOME.search(r[1] or ''))} in Utah, {len(kept)} kept")
        for r in kept[:5]: print("   ", r[0], "|", r[1], "|", r[2], "|", r[3], "|", r[5])
