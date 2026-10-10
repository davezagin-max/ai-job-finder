"""ADP Recruiting Management (myjobs.adp.com): the career site's own JSON API, read in two steps. The site
record hands every visitor an anonymous token (no sign-in; the public page gives it to every browser), and
the requisition list on my.adp.com wants it back as a header. The slug is the career site's name in its
address: myjobs.adp.com/<slug>/cx/job-listing. Not the WorkforceNow product, which is the "adp" kind."""
import sys, os, re, json, time, datetime, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import refresh as R

KIND = "adp_rm"
SLUG_HELP = 'the career site\'s name in its address, myjobs.adp.com/<slug>/cx/job-listing: "conservicecareers"'
EMPLOYERS = {"Conservice": "conservicecareers", "Select Portfolio Servicing": "spsservicing", "WebBank": "webbankcareers",
             "Albany International (Albany Engineered Composites)": "albanyjobs", "HEICO (Wencor)": "heico"}
INSTITUTION = False
AGGREGATOR = False

SITE = "https://myjobs.adp.com"
# The fields the site's own page asks for. postingDate has to be among them: only then does the list answer
# with the posted title. Without it jobTitle is the employer's internal job name ("Investor Rep Analyst
# I-7108" for "Investor Reporting Analyst I"). The two text fields save a request per job.
SELECT = ("reqId,jobTitle,publishedJobTitle,type,jobDescription,jobQualifications,workLocations,workLevelCode,"
          "clientRequisitionID,postingDate,requisitionLocations")
LINK = re.compile(r"myjobs\.adp\.com/([^/?#]+)/cx/job-details\?(?:[^#]*&)?reqId=(\d+)")
_SITES = {}

def _site(slug, reuse=False):
    """(requisition API, request headers, internal-only site?) for one career site."""
    if not (reuse and slug in _SITES):
        code, body = R.curl_resp(f"{SITE}/public/staffing/v1/career-site/{urllib.parse.quote(slug, safe='')}")
        if code == "400" and "not found" in body.lower(): raise RuntimeError(f"no ADP career site named '{slug}'")
        if code != "200": raise RuntimeError(f"HTTP {code} from myjobs.adp.com")
        try: d = json.loads(body)
        except ValueError: d = None                      # a path the site does not know gets its HTML shell
        R.need(isinstance(d, dict) and d.get("myJobsToken"), "no visitor token")
        base = ((d.get("properties") or {}).get("myadpUrl") or "https://my.adp.com").rstrip("/")
        R.need(re.match(r"https://[\w.-]+\.adp\.com$", base), "the API host is not ADP's")   # the token goes nowhere else
        _SITES[slug] = (base + "/myadp_prefix/mycareer/public/staffing/v1/job-requisitions", ["myjobstoken: " + d["myJobsToken"]],
                        str((d.get("settings") or {}).get("careerSiteType")).lower() == "internal")
    return _SITES[slug]

def _place(l):
    """One requisition location as "City, ST". A remote seat has no address, only a name that says so."""
    a = l.get("address") or {}
    name = ((l.get("nameCode") or {}).get("longName") or "").strip()
    city, state, country = (a.get("cityName") or "").strip(), a.get("countrySubdivisionLevel1") or {}, a.get("country") or {}
    us = country.get("codeValue") in ("USA", "US", None, "")
    if not city and R.REMOTE.search(name): return "Remote, US" if us else "Remote"
    place = R.city_state(city or name, state.get("codeValue") or state.get("longName"))
    # the mark the Workday reader uses, so "Chennai, TN" is not read as Tennessee
    return place if us or not place else f"{place} ({country.get('longName') or country['codeValue']}, abroad)"

def _day(stamp, back=0):
    """"YYYY-MM-DD" for a UTC timestamp, taken some hours earlier. None when there is no timestamp."""
    stamp = str(stamp or "")
    if re.match(r"\d{4}-\d\d-\d\d$", stamp): return stamp            # a bare date is already a day
    try: t = datetime.datetime.strptime(stamp[:19], "%Y-%m-%dT%H:%M:%S")
    except ValueError: return None
    return (t - datetime.timedelta(hours=back)).date().isoformat()

def _dates(api, hdrs, req_id):
    """(closes, last posted) from one job's own record, the one its posting page loads."""
    jobs = R.curl(f"{api}/search-meta/{req_id}", None, 30, hdrs).get("jobRequisitions")
    R.need(isinstance(jobs, list) and jobs and isinstance(jobs[0], dict), "no job record")
    post = next(iter(jobs[0].get("postingInstructions") or []), {})
    # expireDate is the instant the posting comes down: local midnight, sent in UTC ("2026-10-17T06:00:00Z"
    # for Logan). The last day to apply is the day before, and twelve hours back is that day in any US
    # time zone. timestampLastPosted moves when a recruiter re-posts, so it can be later than the first day.
    # Seven hours back is the day on a Utah clock, so a job posted in the evening is not dated tomorrow.
    return _day(post.get("expireDate"), back=12), _day(post.get("timestampLastPosted"), back=7)

def fetch(slug):
    """Return every open job as [(title, location, url, closes, degree, extra)]."""
    api, hdrs, internal = _site(slug)
    jobs, skip = [], 0
    while skip < 6000:
        d = R.patient(R.curl, f"{api}/apply-custom-filters?$select={SELECT}&$top=100&$skip={skip}&$orderby=postingDate%20desc", None, 60, hdrs)
        items = d.get("jobRequisitions") if isinstance(d, dict) else None
        R.need(isinstance(items, list) and isinstance(d.get("count"), int), "no jobRequisitions list")
        jobs += items
        skip += 100
        if len(items) < 100 or skip >= d["count"]: break
        time.sleep(0.3)
    total = d["count"]
    # a short read must never look like closures, and an internal job name must never pass for a posted title
    R.need(len({j.get("reqId") for j in jobs}) >= min(total, 6000) * 0.9, f"read {len(jobs)} of {total} jobs")
    R.need(not jobs or any(j.get("publishedJobTitle") for j in jobs), "the list sent no posted titles")
    if total > 6000: R.PARTIAL[slug] = f"read the first 6000 of {total} jobs"
    rows, kept, dated, missed = [], 0, 0, 0
    for j in jobs:
        title = re.sub(r"\s+", " ", j.get("publishedJobTitle") or j.get("jobTitle") or "").strip()
        if not (j.get("reqId") and title): continue
        places = [_place(l) for l in sorted(j.get("requisitionLocations") or [], key=lambda l: not l.get("primaryIndicator"))]
        loc = "; ".join(dict.fromkeys(p for p in places if p))
        # The page prints the qualifications under a "Requirements" heading. The feed sends them as a
        # field of their own, so the heading is put back for min_years to find.
        text = (j.get("jobDescription") or "") + "\n<p>Requirements</p>\n" + (j.get("jobQualifications") or "")
        # A site that shows how long each job has been up sends the posting date in the list. The others
        # leave it out, and no list has the closing date: those are in each job's own record.
        closes, posted = None, _day(j.get("postingDate"), back=7)
        if R.classify(title, loc, KIND) or R.experienced(title, loc, KIND):       # only read what will be published
            kept += 1
            # A failed read leaves the row as listed, and after three of them the rest are not asked for.
            if kept <= 60 and missed < 3:
                try:
                    closes, reposted = R.patient(_dates, api, hdrs, j["reqId"], slots=R._DETAIL_SLOTS); dated += 1
                    posted = posted or reposted
                except Exception: missed += 1
                time.sleep(0.3)
        rows.append((title, loc, f"{SITE}/{slug}/cx/job-details?reqId={j['reqId']}", closes, R.degree_flag(text),
                     {"posted": posted, "yrs": R.min_years(text), "internal": internal, "company": None}))
    if dated < kept:
        note = f"read details for the first 60 of {kept} kept roles" if not missed else f"read details for {dated} of {kept} kept roles"
        R.PARTIAL[slug] = f"{R.PARTIAL[slug]}; {note}" if total > 6000 else note       # a cut-short list stays in the note
    return R._dedupe(rows)

def link_state(url):
    """'live', 'dead' or 'unknown' for one posting URL of this system. Return 'unknown' whenever unsure."""
    m = LINK.search(url)
    if not m: return "unknown"
    # The posting page is a shell that answers 200 for any id, so the job's own record is asked. It
    # answers 404 "Not Found" for an id that is not posted; a wrong path or a refused token answers 403 or 400.
    try:
        api, hdrs, _ = _site(m.group(1), reuse=True)
        code, body = R.curl_resp(f"{api}/{m.group(2)}", headers=hdrs)
        if code == "404": return "dead" if "Not Found" in body else "unknown"
        job = json.loads(body)["jobRequisitions"][0] if code == "200" else {}
    except Exception: return "unknown"
    return "live" if str(job.get("reqId")) == m.group(2) and job.get("canApply") is not False else "unknown"

if __name__ == "__main__":
    for name, slug in EMPLOYERS.items():
        rows = fetch(slug)
        kept = [r for r in rows if R.classify(r[0], r[1], KIND) or R.experienced(r[0], r[1], KIND)]
        print(f"{name}: {len(rows)} jobs, {sum(1 for r in rows if R.HOME.search(r[1] or ''))} in Utah, {len(kept)} kept")
        for r in kept[:5]: print("   ", r[0], "|", r[1], "|", r[2], "|", r[3], "|", r[5])
