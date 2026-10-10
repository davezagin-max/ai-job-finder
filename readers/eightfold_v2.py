"""Eightfold, older API: a careers site that still answers /api/apply/v2/jobs, where the /api/pcsx/search the
"eightfold" kind reads says "PCSX is not enabled". The list is public JSON, ten jobs a request, newest first,
and is read to its end: no key, no cookie, no sign-in. The slug is "host|domain", the careers site's host and
the domain= in its own links. The list has every place and the posted date but only a summary of the text,
so each job that would be kept has its own record read for the full text and the application deadline."""
import sys, os, re, json, time, datetime, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import refresh as R

KIND = "eightfold_v2"
SLUG_HELP = ('"host|domain", the careers site\'s host and the domain= in its links: "searchjobs.libertymutualgroup.com|libertymutual.com" '
             '(a board too big to read whole takes the "eightfold" kind\'s searches after it: "|@Utah, United States")')
EMPLOYERS = {"Liberty Mutual": "searchjobs.libertymutualgroup.com|libertymutual.com"}
INSTITUTIONS = set()  # names from EMPLOYERS that are public bodies, schools or hospitals, whose titles use "University", "Campus" or "Graduate" as plain description
AGGREGATOR = False    # True when one slug returns the jobs of many employers

MAX_REQUESTS = 150    # list requests for one employer. The site gives ten jobs a request whatever is asked: 1,500 jobs
MAX_DETAILS = 60
LINK = re.compile(r"https://([^/?#]+)/careers/job/(\d+)")
_HOSTS = {s.split("|")[0].lower() for s in EMPLOYERS.values()}    # other systems use /careers/job/ too: only these sites are asked
_NAME = re.compile(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+")
_US = {"us", "usa", "united states", "united states of america"}
_STATES = {name.lower(): code for name, code in R.STATE_NAMES.items()}
_FAR = re.compile(r"(?:remote|virtual)\b", re.I)
_DATE_FORMS = ("%m/%d/%Y", "%B %d, %Y", "%b %d, %Y", "%Y-%m-%d")

def _place(text, remote):
    """One place of a job as the location rules read it: "Salt Lake City, Utah, United States" as "Salt Lake
    City, UT", "Remote, Remote, United States" as "Remote, US", and "Remote, Provo, UT" for a job the feed
    marks remote and ties to Provo. A place in another country is marked the way the Workday reader marks
    one ("Pune (India, abroad)"), because the rules do not know every country by name."""
    parts = [p.strip() for p in re.sub(r"[\s()]+", " ", str(text or "")).split(",") if p.strip()]
    remote, several = remote or any(_FAR.match(p) for p in parts), len(parts) > 1
    parts = [p for p in parts if not _FAR.match(p)]
    us = bool(parts) and parts[-1].lower() in _US
    if us: parts.pop()
    last = parts[-1] if parts else ""
    # The city is first and the state last: the feed also writes "Washington, Washington, DC" and "Richmond,
    # VA, Virginia". With no country after it, two letters are a state only in a plain "City, ST":
    # in "Bangalore, KA, IN" they are a country.
    state = _STATES.get(last.lower()) or (last if last in _STATES.values() and (us or len(parts) == 2) else "")
    if state: where = f"{parts[0]}, {state}" if len(parts) > 1 else state if remote else f"{last}, US"
    elif us: where = f"{parts[0]}, US" if parts else "US" if remote else "United States"
    elif len(parts) > 1: where = f"{parts[0]} ({last}, abroad)"
    elif last and several: where = f"({last}, abroad)"    # "Remote, Remote, India": what is left is the country
    else: where = last                                    # one word that is not a state: left as written
    return ", ".join(x for x in ("Remote" if remote else "", where) if x).replace(", (", " (")

def _page(host, domain, text, place, start):
    """One page of the job list."""
    ask = {"domain": domain, "start": start, "sort_by": "timestamp"}
    if text: ask["query"] = text
    if place: ask["location"] = place
    try: d = json.loads(R.curl_text(f"https://{host}/api/apply/v2/jobs?" + urllib.parse.urlencode(ask), timeout=45))
    except ValueError: raise RuntimeError("unexpected reply (not JSON: a sign-in page or a bot check?)")
    R.need(isinstance(d, dict) and isinstance(d.get("positions"), list) and isinstance(d.get("count"), int), "not a job list")
    # A domain the host does not serve answers 404. Asked with none at all it lists its own, so the reply
    # is checked for the domain it was asked for.
    R.need(d.get("domain") == domain, "the list is for another domain")
    if place and place.lower() != "remote":               # "Remote" is itself a place the site searches by
        # Every search by place also returns the remote jobs, so a place it cannot find looks like a place
        # with nothing but remote work. The reply tells them apart: it names the country of a place it
        # found ("remote,United States") and says only "remote" for one it did not.
        seen = d.get("location_user")
        R.need(isinstance(seen, list) and len(seen) == 2 and str(seen[1]).startswith("remote,"), f"the site does not know the place '{place}'")
    return d

def _listing(host, domain, text, place, limit):
    """({job id: job}, the site's own count, whether the end of the list was reached) for one search."""
    jobs, start, count = {}, 0, 0
    for _ in range(limit):
        d = R.patient(_page, host, domain, text, place, start)
        count = d["count"]
        for j in d["positions"]:
            R.need(isinstance(j, dict) and isinstance(j.get("id"), int) and j.get("name"), "a job without an id or a title")
            jobs.setdefault(j["id"], j)
        start += len(d["positions"])                      # by what arrived, should a site ever give larger pages
        if not d["positions"] or start >= count: return jobs, count, True
        if len(jobs) >= 6000: break
        time.sleep(0.3)
    return jobs, count, False

def _record(host, domain, pid):
    """One job's own record: the whole posting text and the fields the employer adds to its postings."""
    d = R.curl(f"https://{host}/api/apply/v2/jobs/{pid}?domain={urllib.parse.quote(domain)}", timeout=45)
    R.need(isinstance(d, dict) and d.get("id") == pid, "not this job's record")
    return d

def _day(stamp):
    """A Unix time in seconds as the local date, or None for anything else (a time in milliseconds, say)."""
    return datetime.date.fromtimestamp(stamp).isoformat() if isinstance(stamp, (int, float)) and 0 < stamp < 4e9 else None

def _deadline(record):
    """The application deadline a posting shows, as YYYY-MM-DD, or None."""
    # It is a field the employer adds (Liberty Mutual's is "ApplicationDeadline", typed "10/15/2026" on one
    # job and "July 27, 2026" on another). A date already past on a job that is still listed is stale:
    # passed on, it would hide an open job, so it is left out.
    added = record.get("custom_JD") if isinstance(record.get("custom_JD"), dict) else {}
    fields = added.get("data_fields") if isinstance(added.get("data_fields"), dict) else {}
    for key, value in fields.items():
        if not re.search(r"deadline|clos(?:e|ing)", str(key), re.I): continue
        said = " ".join(str(value[0] if isinstance(value, list) and value else value or "").split())
        for form in _DATE_FORMS:
            try: day = datetime.datetime.strptime(said, form).date().isoformat()
            except ValueError: continue
            return day if day >= datetime.date.today().isoformat() else None
    return None

def fetch(slug):
    """Return every open job as [(title, location, url, closes, degree, extra)]."""
    parts = [p.strip() for p in (slug or "").split("|")]
    if len(parts) not in (2, 3) or not all(_NAME.fullmatch(p.lower()) for p in parts[:2]):
        raise RuntimeError('the slug is not "host|domain" (like "searchjobs.libertymutualgroup.com|libertymutual.com")')
    host, domain = parts[0].lower(), parts[1].lower()
    searches = [("", "")]                                 # nothing after the domain: the whole board
    if len(parts) == 3:
        # "word@place;word@place" narrows a big board, as in the "eightfold" kind. A word that no posting
        # contains finds nothing, and that is an answer, not a mistake.
        searches = [tuple(x.strip() for x in q.partition("@")[::2]) for q in parts[2].split(";")]
        if not all(text or place for text, place in searches): raise RuntimeError('the searches in the slug are not "word@place;word@place"')
    jobs, notes = {}, []
    for n, (text, place) in enumerate(searches):
        if n: time.sleep(0.3)
        found, count, ended = _listing(host, domain, text, place, MAX_REQUESTS // len(searches))
        what = f' for "{text}@{place}"' if text or place else ""
        if not ended: notes.append(f"read the first {len(found)} of {count} jobs{what}")
        else:
            # A job that closes while the pages are read moves the rest up one, and one of them is never
            # seen. One or two missing are reported. More than that is a list that cannot be trusted.
            R.need(len(found) >= count * 0.9, f"read {len(found)} of {count} jobs{what}")
            if len(found) < count: notes.append(f"{len(found)} of {count} jobs read{what} (the list changed while it was read)")
        for pid, j in found.items(): jobs.setdefault(pid, j)
    listed = []
    for pid, j in jobs.items():
        title = re.sub(r"\s+", " ", R.html_unescape(re.sub(r"</?[A-Za-z][^<>]*>", " ", str(j["name"])))).strip()
        remote = str(j.get("work_location_option") or "").startswith("remote")     # "remote_local", "remote_global"
        spots = j.get("locations") if isinstance(j.get("locations"), list) and j["locations"] else [j.get("location")]
        places = list(dict.fromkeys(p for p in (_place(s, remote) for s in spots) if p))
        # A job open in twenty cities: the ones near home go first, the rest keep the feed's order.
        places.sort(key=lambda p: not R.HOME.search(p))
        url = str(j.get("canonicalPositionUrl") or "")
        if not url.startswith("https://"): url = f"https://{host}/careers/job/{pid}"
        listed.append((title, "; ".join(places), url, pid))
    # Only the roles that will be published are worth a second request each, one at a time, home ones first.
    kept = [x for x in listed if R.classify(x[0], x[1], KIND) or R.experienced(x[0], x[1], KIND)]
    kept.sort(key=lambda x: not R.HOME.search(x[1]))
    if len(kept) > MAX_DETAILS: notes.append(f"read details for the first {MAX_DETAILS} of {len(kept)} kept roles")
    records, failed, streak = {}, 0, 0
    for _, _, _, pid in kept[:MAX_DETAILS]:
        if streak >= 3: failed += 1; continue             # the site is refusing: stop asking rather than retry sixty jobs
        try: records[pid] = R.patient(_record, host, domain, pid, slots=R._DETAIL_SLOTS); streak = 0
        except R.OffLimits: raise
        except Exception: failed += 1; streak += 1        # the row is kept as listed rather than dropped
        time.sleep(0.2)
    if failed: notes.append(f"{failed} of {min(len(kept), MAX_DETAILS)} job records could not be read")
    if notes: R.PARTIAL[slug] = "; ".join(notes)
    rows = []
    for title, loc, url, pid in listed:
        j, record = jobs[pid], records.get(pid) or {}
        # Without its record a job is read from the list's summary of the text, which some jobs do not have.
        text = record.get("job_description") or j.get("job_description")
        if not isinstance(text, str): text = None
        # t_create is the day the job was first listed. The "datePosted" inside the posting page moves with
        # every later edit, so it is not that. isPrivate marks a job kept off the public search.
        rows.append((title, loc, url, _deadline(record), R.degree_flag(text),
                     {"posted": _day(j.get("t_create")), "yrs": R.min_years(text), "internal": bool(j.get("isPrivate")), "company": None}))
    return R._dedupe(rows)

def link_state(url):
    """'live', 'dead' or 'unknown' for one posting URL of this system. Return 'unknown' whenever unsure."""
    m = LINK.match(url or "")
    if not m or m.group(1).lower() not in _HOSTS: return "unknown"
    try: code, page = R.curl_resp(url, accept="text/html")
    except Exception: return "unknown"
    # The posting page is asked, not the API: a closed job's record still answers 200 there. The page of a
    # closed job answers 404 with the careers site around it, and a live one names its own link. In between,
    # a job that has just left the list still shows its page (HTTP 200) with a "noindex" mark on it: that
    # says the site no longer lists it, not that it is gone for good, so it is left as unknown.
    if 'id="smartApplyData"' not in page: return "unknown"       # not the careers site answering
    if code == "404": return "dead"
    named = re.search(r'rel="canonical" href="[^"]*/careers/job/%s\b' % m.group(2), page)
    return "live" if code == "200" and named and not re.search(r'<meta[^>]*name="robots"[^>]*noindex', page) else "unknown"

if __name__ == "__main__":
    for name, slug in EMPLOYERS.items():
        rows = fetch(slug)
        kept = [r for r in rows if R.classify(r[0], r[1], KIND) or R.experienced(r[0], r[1], KIND)]
        print(f"{name}: {len(rows)} jobs, {sum(1 for r in rows if R.HOME.search(r[1] or ''))} in Utah, {len(kept)} kept")
        for r in kept[:5]: print("   ", r[0], "|", r[1], "|", r[2], "|", r[3], "|", r[5])
