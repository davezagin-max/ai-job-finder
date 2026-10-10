"""Cornerstone OnDemand (csod.com) career sites. The public career page hands every visitor an anonymous
token (no sign-in: any browser gets one), and the search service that page calls takes it as a Bearer
header, fifty jobs a request. The slug is "corp|career site id|API host", as in "utdgohcm|4|us.api.csod.com"
for the State of Utah, whose statejobs.utah.gov redirects there. The site asks for ten seconds between
requests, so a full read (the list, then the job ad of each role worth keeping) takes five or six minutes."""
import sys, os, re, json, time, datetime, threading, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import refresh as R

KIND = "cornerstone"
SLUG_HELP = ('"corp|career site id|API host": the csod.com subdomain, the number after /careersite/ in the career page '
             'link, and the host of endpoints.cloud in that page\'s source, e.g. "utdgohcm|4|us.api.csod.com"')
EMPLOYERS = {"State of Utah": "utdgohcm|4|us.api.csod.com"}
INSTITUTION = True    # state government: "Campus", "University" and "Graduate" in a title are plain description
AGGREGATOR = False

# utdgohcm.csod.com/robots.txt closes nothing and states "Crawl-delay: 10", which R's helpers keep for
# the career site's own host. The search is on a second host that has no robots.txt, and it is the same
# site's back end, so the ten seconds are kept here between any two requests to either. Waiting here
# also means a shared detail slot is held for the request alone, never for the wait before it.
CRAWL_DELAY = 10
PAGE = 50
MAX_ROWS = 4500       # ninety list requests: with sixty job ads that keeps one employer to about 150 requests
MAX_ADS = 60          # a job ad is one more request each, so ten more seconds
_GATE, _LAST = threading.Lock(), [0.0]
_TOKENS = {}          # (corp, site) -> (token, API host, when read). A token lasts four hours.
_DEGREE = re.compile(r"bachelor|associate.s? degree", re.I)
CSOD_LINK = re.compile(r"https://([\w-]+)\.csod\.com/ux/ats/careersite/(\d+)/home/requisition/(\d+)")
# "This recruitment is open to current employees of the Business Taxes section only."
INTERNAL = re.compile(r"\b(?:open|limited|restricted)\s+(?:only\s+)?to\s+(?:all\s+)?current\b[^.]{0,90}?\bemployees\b(?!\s+(?:and|or|as well as)\b)|"
                      r"\bcurrent\b[^.]{0,90}?\bemployees\s+only\b|\bonly\s+current\b[^.]{0,90}?\bemployees\b|"
                      r"\b(?:internal|in-house)\s+(?:recruitment|posting|only)\b", re.I)

def _paced(fn, *args, slots=None):
    """One request to Cornerstone, no sooner than CRAWL_DELAY after the last one. A failure is tried once more."""
    for attempt in (1, 2):
        with _GATE:
            time.sleep(max(0.0, _LAST[0] + CRAWL_DELAY - time.time()))
            try: return R.patient(fn, *args, tries=1, slots=slots)
            except R.OffLimits: raise
            except Exception:
                if attempt == 2: raise
            finally: _LAST[0] = time.time()

def _json(url, post, token):
    body = R.curl_text(url, post, 45, headers=["Authorization: Bearer " + token])
    try: return json.loads(body)
    except ValueError: raise RuntimeError(f"unexpected reply (not JSON from {urllib.parse.urlsplit(url).netloc})")

def _token(corp, site):
    """(the anonymous visitor token in the public career page, the API host that page names). A career
    site id that does not exist answers with an error page that carries no token, which is how a wrong
    slug is caught before anything is searched."""
    hit = _TOKENS.get((corp, site))
    if hit and time.time() - hit[2] < 3600: return hit[:2]
    page = _paced(R.curl_text, f"https://{corp}.csod.com/ux/ats/careersite/{site}/home?c={corp}", None, 30, "text/html")
    m = re.search(r'"token":"([\w.-]{100,})"', page)
    R.need(m, "the career page hands out no visitor token: is the corp or the career site id wrong?")
    api = re.search(r'"cloud":"https?://([^/"]+)', page)
    _TOKENS[(corp, site)] = (m.group(1), api.group(1) if api else "", time.time())
    return _TOKENS[(corp, site)][:2]

def _iso(text):
    """'10/18/2026' -> '2026-10-18'. An open-ended posting says '-'."""
    m = re.match(r"\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*$", text or "")
    try: return datetime.date(int(m.group(3)), int(m.group(1)), int(m.group(2))).isoformat() if m else None
    except ValueError: return None

def _place(l):
    place, country = R.city_state(l.get("city"), l.get("state")), (l.get("country") or "US").strip().upper()
    # the mark the Workday reader writes, so that ", CA" for Canada is never read as California
    return place if country in ("US", "PR", "GU", "VI", "AS", "MP") else f"{place} ({country}, abroad)".strip()

def _bar(ad):
    """The ad without experience that is offered in place of a degree. The State writes "Bachelor's degree
    in ...;" then "OR" then "3-5 years of experience in ...": a second way in for someone without the
    degree, which refresh.min_years would otherwise report as the years this candidate needs."""
    lines = re.sub(r"(?i)•[^\w•]*(or)[^\w•]*•", r"• \1 ", " • ".join(R._items(ad))).split(" • ")
    return "\n".join(l for n, l in enumerate(lines) if not (n and re.match(r"or\b", l, re.I) and R._YEARS.search(l)
                                                           and not _DEGREE.search(l) and _DEGREE.search(lines[n - 1])))

def _list(host, site, token):
    """(every requisition by id, the count the service states, whether the list held still while it was read).
    The list is newest first and paged by number, so a job posted or closed between two pages moves every
    later row by one place: one row is then seen twice, or one is never seen at all."""
    found, counts, total = {}, set(), 0
    for page in range(1, MAX_ROWS // PAGE + 1):
        d = _paced(_json, f"https://{host}/rec-job-search/external/jobs",
                   {"careerSiteId": int(site), "careerSitePageId": int(site), "pageNumber": page, "pageSize": PAGE, "cultureId": 1,
                    "searchText": "", "cultureName": "en-US", "states": [], "countryCodes": [], "cities": [], "placeID": "",
                    "radius": None, "postingsWithinDays": None, "customFieldCheckboxKeys": [], "customFieldDropdowns": [],
                    "customFieldRadios": []}, token)
        data = d.get("data") if isinstance(d, dict) else None
        R.need(isinstance(data, dict) and d.get("status") == "Success" and isinstance(data.get("requisitions"), list), "no requisitions list")
        total, before = data.get("totalCount") or 0, len(found)
        counts.add(total)
        for j in data["requisitions"]:
            if isinstance(j, dict) and j.get("requisitionId"): found.setdefault(j["requisitionId"], j)
        # The stated count ends the read, or a page with nothing new on it. A short page alone does not: a
        # site that hands out smaller pages than it was asked for must still be read to its end.
        if len(found) == before or 0 < total <= len(found): break
    return found, total, len(counts) == 1 and len(found) >= min(total, MAX_ROWS)

def fetch(slug):
    """Return every open job as [(title, location, url, closes, degree, extra)]."""
    m = re.match(r"([\w-]+)\|(\d+)\|([\w.-]+)$", slug)
    R.need(m, 'the slug is not "corp|career site id|API host"')
    corp, site, host = m.groups()
    token, named = _token(corp, site)
    R.need(named == host, f"the career page's API host is {named or 'not stated'}, not {host}")   # the token goes nowhere else
    found, total, steady = _list(host, site, token)
    # A list that moved while it was read is read once more: the second read nearly always holds still.
    # (Small lists only, which keeps a large employer near 150 requests.)
    if not steady and len(found) <= 20 * PAGE: found, total, steady = _list(host, site, token)
    R.need(len(found) >= min(total, MAX_ROWS) * 0.9, f"read {len(found)} of {total} jobs")   # a short read must never look like closures
    notes = [f"read {len(found)} of {total} jobs"] if total > len(found) else [] if steady else ["the list changed while it was read, so a job may be missing"]
    jobs = []
    for rid, j in found.items():
        title = re.sub(r"\s+", " ", j.get("displayJobTitle") or "").strip()
        if not title: continue
        loc = "; ".join(dict.fromkeys(p for p in map(_place, j.get("locations") or []) if p))
        jobs.append({"id": rid, "title": title, "loc": loc, "text": j.get("externalDescription") or "", "ad": "",
                     "closes": _iso(j.get("postingExpirationDate")), "posted": _iso(j.get("postingEffectiveDate")),
                     "url": f"https://{corp}.csod.com/ux/ats/careersite/{site}/home/requisition/{rid}?c={corp}"})
    # The list carries both dates and a summary of the duties. The qualifications (degree, years) are only
    # in the job ad, one more request each, so the ad is read for the roles worth keeping and no others.
    kept = [j for j in jobs if R.classify(j["title"], j["loc"], KIND) or R.experienced(j["title"], j["loc"], KIND)]
    failed = 0
    for j in kept[:MAX_ADS]:
        if failed >= 3: break                                                   # the ad service is down: stop asking
        try:
            d = _paced(_json, f"https://{corp}.csod.com/Services/API/ATS/CareerSite/{site}/JobRequisitions/{j['id']}"
                              f"?useMobileAd=false&cultureId=1", None, token, slots=R._DETAIL_SLOTS)
            j["ad"] = d["data"][0]["items"][0]["fields"]["ad"] or ""
        except Exception: failed += 1                                           # the row is kept as listed
    if failed: notes.append(f"read details for {sum(1 for j in kept if j['ad'])} of {len(kept)} kept roles")
    elif len(kept) > MAX_ADS: notes.append(f"read details for the first {MAX_ADS} of {len(kept)} kept roles")
    if notes: R.PARTIAL[slug] = "; ".join(notes)
    rows = []
    for j in jobs:
        text = j["ad"] or j["text"]
        said = R.html_unescape(re.sub(r"<[^>]+>", " ", " . ".join((j["title"], j["text"], j["ad"]))))
        rows.append((j["title"], j["loc"], j["url"], j["closes"], R.degree_flag(text),
                     {"posted": j["posted"], "yrs": R.min_years(_bar(text)), "internal": bool(INTERNAL.search(said)), "company": None}))
    return R._dedupe(rows)

def link_state(url):
    """'live', 'dead' or 'unknown' for one posting URL of this system. Return 'unknown' whenever unsure.
    The posting page is a shell that answers 200 for any id, so this asks the service the page itself asks
    before it shows "Apply Now" or "This job is not currently available": one request a link, ten seconds
    apart, plus the career page once an hour for the visitor token."""
    m = CSOD_LINK.search(url or "")
    if not m: return "unknown"
    corp, site, rid = m.groups()
    try:
        d = _paced(_json, f"https://{corp}.csod.com/Services/API/ATS/CareerSite/{site}/JobRequisition/{rid}/GetRequisitionApplyStatus",
                   None, _token(corp, site)[0])
        status = str(d["data"][0]["items"][0]["fields"]["applyStatus"])
    except Exception: return "unknown"      # an id that never existed answers with no data, and so would an outage
    return "dead" if status == "0" else "live" if status == "2" else "unknown"   # 0 not available, 2 apply now

if __name__ == "__main__":
    for name, slug in EMPLOYERS.items():
        rows = fetch(slug)
        kept = [r for r in rows if R.classify(r[0], r[1], KIND) or R.experienced(r[0], r[1], KIND)]
        print(f"{name}: {len(rows)} jobs, {sum(1 for r in rows if R.HOME.search(r[1] or ''))} in Utah, {len(kept)} kept")
        for r in kept[:5]: print("   ", r[0], "|", r[1], "|", r[2], "|", r[3], "|", r[5])
