"""Phenom career sites: the search-results page asks the site's own /widgets endpoint for the job list as
JSON, and so does this, 500 jobs a request, with every site of a multi-location job and the posted date.
The slug is the career site's host, plus /country/language when the site's own links do not say /us/en
("jobs.baesystems.com/global/en"). The list has no posting text, so each kept job's record is read from
the same endpoint (ddoKey "jobDetail"). No key, no cookie and no sign-in."""
import sys, os, re, json, time, datetime, ast, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import refresh as R

KIND = "phenom"
SLUG_HELP = 'the career site\'s address before /search-results, with /us/en left off: "careers.opentext.com", or "jobs.baesystems.com/global/en"'
# The whole board is read, so the list is kept to an employer with a real Utah presence (Hill Air Force
# Base and Clearfield). OpenText (careers.opentext.com), Conduent (careers.conduent.com) and Procter &
# Gamble (www.pgcareers.com/global/en) read fine too: hundreds of jobs each for two to six in Utah.
EMPLOYERS = {"BAE Systems": "jobs.baesystems.com/global/en"}
INSTITUTION = False   # True for public bodies, schools and hospitals, whose titles use "University", "Campus" or "Graduate" as plain description
AGGREGATOR = False    # True when one slug returns the jobs of many employers

PAGE = 500            # the most a request is given; a site that gives fewer is paged by what it returned
MAX_ROWS = 6000
MAX_DETAILS = 60
LINK = re.compile(r"https://[^/]+/[a-z]{2,6}/[a-z]{2}/job/([^/?#]+)")
_US = {"us", "usa", "u.s.", "u.s.a.", "united states", "united states of america"}
# Left to itself the search returns jobs in no order at all, and a second request for the next 500 can
# repeat some and skip others (139 of BAE's 1,942 in one pass). Newest first is an order it keeps.
_NEWEST = {"order": "desc", "field": "dateCreated"}

def _widgets(host, locale, key, **ask):
    """One answer from the endpoint the site's own pages call. A site ignores a locale it does not have and
    answers in its own, so every row's own locale is what its link is built from."""
    post = dict({"ddoKey": key, "lang": locale, "country": locale.partition("_")[2], "siteType": "external", "deviceType": "desktop"}, **ask)
    try: d = json.loads(R.curl_text(f"https://{host}/widgets", post, 60))
    except ValueError: raise RuntimeError("unexpected reply (not JSON)")
    d = d.get(key) if isinstance(d, dict) else None
    R.need(isinstance(d, dict) and d.get("status") == 200 and isinstance(d.get("data"), dict), f"no {key} data")
    return d

def _record(host, locale, seq):
    """One job's own record, which is where the posting text is."""
    job = _widgets(host, locale, "jobDetail", pageName="job", jobSeqNo=seq)["data"].get("job")
    R.need(isinstance(job, dict) and job.get("jobSeqNo") == seq, "not this job's record")
    return job

def _search(host, locale, chosen, sort):
    """({job id: job}, how many the site says there are, {facet: {value: count}}) for one search."""
    jobs, total, facets = {}, 0, {}
    for sweep in range(3):                                # a job taken down mid-read shifts the rest up a row: look again
        start = 0
        while start < MAX_ROWS:
            ask = dict(pageName="search-results", keywords="", selected_fields=chosen, jobs=True, counts=True,
                       all_fields=["country", "remote"], size=PAGE, **{"from": start})
            if sort: ask.update(sortBy="Most recent", sort=sort)
            d = _widgets(host, locale, "refineSearch", **ask)
            page = d["data"].get("jobs")
            R.need(isinstance(page, list) and isinstance(d.get("totalHits"), int), "no jobs list")
            if start == 0: total = d["totalHits"]         # a request past the end reports a total of 0
            for f in d["data"].get("aggregations") or []:
                if isinstance(f, dict) and isinstance(f.get("value"), dict): facets.setdefault(f.get("field"), {}).update(f["value"])
            for j in page:
                if isinstance(j, dict) and j.get("jobId"): jobs.setdefault(str(j["jobId"]), j)
            start += len(page)
            if not page or start >= total: break
            time.sleep(0.3)
        if len(jobs) >= min(total, MAX_ROWS): break
        time.sleep(0.3)
    return jobs, total, facets

def _listing(host, locale, chosen):
    """A search read newest first. A site that cannot sort that way says it has no jobs at all, which is
    never taken at its word: the search is asked again as it comes."""
    jobs, total, facets = _search(host, locale, chosen, _NEWEST)
    if not total: jobs, total, facets = _search(host, locale, chosen, None)
    return jobs, total, facets

def _sites(j):
    """Every place a job is offered at. Some sites send the list as text: "['Mehoopany, Pennsylvania, ...', ...]"."""
    v = j.get("multi_location")
    if isinstance(v, str) and v.lstrip().startswith("["):
        try: v = ast.literal_eval(v)
        except (ValueError, SyntaxError): v = None
    return [s for s in v if isinstance(s, str)] if isinstance(v, list) else []

def _place(text, countries):
    """"Provo, Utah, USA, 84606" as "Provo, UT", "Remote US, United States" and "Virtual, USA" as
    "Remote, US". A place in another country is marked the way the Workday reader marks it, because the
    location rules know "Bangalore" but not "Richmond Hill, Ontario, CAN"."""
    parts = [p.strip() for p in (text or "").split(",") if p.strip()]
    while parts and re.search(r"\d", parts[-1]): parts.pop()                 # the postcode
    if not parts: return ""
    last, rest = parts[-1], parts[:-1]
    if last.lower() in _US:
        if not rest: return "United States"
        if re.match(r"(?:remote|virtual)\b", rest[-1], re.I): return "Remote, US"
        if len(rest) == 1: return rest[0] + ", US"                            # a state, or a city, on its own
        loc = R.city_state(", ".join(rest[:-1]), rest[-1])
        return loc if re.search(r", [A-Z]{2}$", loc) else loc + ", US"
    # Only a word the feed itself uses as a country, or a three-letter country code, says "abroad".
    # Anything else is left as written.
    if last in countries or re.match(r"[A-Z]{3}$", last): return f"{', '.join(rest) or last} ({last}, abroad)"
    return ", ".join(parts)

def fetch(slug):
    """Return every open job as [(title, location, url, closes, degree, extra)]."""
    m = re.match(r"([a-z0-9.-]+\.[a-z]+)(?:/([a-z]{2,6})/([a-z]{2}))?/?$", slug.strip().lower())
    R.need(m, 'slug is the career site\'s host, or "host/country/language"')
    host, locale = m.group(1), f"{m.group(3) or 'en'}_{m.group(2) or 'us'}"
    jobs, total, facets = _listing(host, locale, {})
    notes = []
    if total > MAX_ROWS: notes.append(f"read {len(jobs)} of {total} jobs")
    elif len(jobs) < total:
        R.need(len(jobs) >= total * 0.9, f"read {len(jobs)} of {total} jobs")     # a short read must never look like closures
        notes.append(f"{len(jobs)} of {total} jobs read (the site's paging skips some)")
    countries = set(facets.get("country") or {}) | {(j.get("country") or "").strip() for j in jobs.values()}
    # Whether a job can be done from home is a filter on the site, not a field of the row. So the remote
    # jobs are asked for by themselves, and a US job among them says "Remote" after its place.
    yes = [k for k, n in (facets.get("remote") or {}).items() if n and re.match(r"(?:yes|remote)\b", k, re.I)]
    remote = set(_listing(host, locale, {"remote": yes})[0]) if yes else set()
    listed = {}
    for jid, j in jobs.items():
        title = re.sub(r"\s+", " ", j.get("title") or "").strip()
        if not title: continue
        places = [_place(s, countries) for s in _sites(j)]
        if not any(places): places = [_place(j.get("location") or j.get("cityStateCountry"), countries)]   # some rows list only a postcode
        loc = "; ".join(dict.fromkeys(p for p in places if p))
        if jid in remote and R.where(loc) and not R.REMOTE.search(loc): loc = "; ".join(x for x in (loc, "Remote") if x)
        own = (j.get("locale") or locale).lower()                          # "en_us", "en_global"
        lang, _, country = own.partition("_")
        listed[f"https://{host}/{country}/{lang}/job/{urllib.parse.quote(jid, safe='')}"] = (title, loc, j, own)
    # Only the roles that will be published are worth a second request each, one at a time, and the ones
    # nearest home first, because no more than sixty are read.
    near = {"home": 0, "remote": 1, "elsewhere": 2}
    kept = [(url, j.get("jobSeqNo"), own) for url, (title, loc, j, own) in listed.items()
            if j.get("jobSeqNo") and (R.classify(title, loc, KIND) or R.experienced(title, loc, KIND))]
    kept.sort(key=lambda k: near.get(R.where(listed[k[0]][1]), 3))
    if len(kept) > MAX_DETAILS: notes.append(f"read details for the first {MAX_DETAILS} of {len(kept)} kept roles")
    records, failed = {}, 0
    for url, seq, own in kept[:MAX_DETAILS]:
        try: records[url] = R.patient(_record, host, own, seq, slots=R._DETAIL_SLOTS)
        except R.OffLimits: raise
        except Exception: failed += 1                     # the row is kept as listed rather than dropped
        time.sleep(0.3)
    if failed: notes.append(f"{failed} of {min(len(kept), MAX_DETAILS)} job records could not be read")
    if notes: R.PARTIAL[slug] = "; ".join(notes)
    rows = []
    for url, (title, loc, j, own) in listed.items():
        text = (records.get(url) or {}).get("description")
        seen_by = [str(v).lower() for v in j.get("jobVisibility") or []] if isinstance(j.get("jobVisibility"), list) else []
        rows.append((title, loc, url, None, R.degree_flag(text),      # Phenom states no closing date
                     {"posted": (re.match(r"\d{4}-\d\d-\d\d", j.get("postedDate") or "") or [None])[0], "yrs": R.min_years(text),
                      "internal": bool(seen_by) and "external" not in seen_by, "company": None}))
    return R._dedupe(rows)

def link_state(url):
    """'live', 'dead' or 'unknown' for one posting URL of this system. Return 'unknown' whenever unsure."""
    m = LINK.match(url or "")
    if not m: return "unknown"
    try: code, page = R.curl_resp(url, accept="text/html", timeout=60)
    except Exception: return "unknown"
    if code in ("404", "410"): return "dead"              # a posting that is gone answers 410
    # 200 alone could be any site's page: a Phenom posting carries its own id in the page's data
    return "live" if code == "200" and re.search(r'"jobId"\s*:\s*"%s"' % re.escape(urllib.parse.unquote(m.group(1))), page) else "unknown"

if __name__ == "__main__":
    for name, slug in EMPLOYERS.items():
        rows = fetch(slug)
        kept = [r for r in rows if R.classify(r[0], r[1], KIND) or R.experienced(r[0], r[1], KIND)]
        print(f"{name}: {len(rows)} jobs, {sum(1 for r in rows if R.HOME.search(r[1] or ''))} in Utah, {len(kept)} kept")
        for r in kept[:5]: print("   ", r[0], "|", r[1], "|", r[2], "|", r[3], "|", r[5])
