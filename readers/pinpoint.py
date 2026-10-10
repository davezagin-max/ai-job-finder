"""Pinpoint: every careers site answers COMPANY.pinpointhq.com/postings.json with its whole board as JSON,
descriptions and deadlines included. The list has no posted date and no country, so those two are read from
the posting page of each role the filters keep. The slug is the pinpointhq.com subdomain ("eptura")."""
import sys, os, re, json, time, datetime, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import refresh as R

KIND = "pinpoint"
SLUG_HELP = 'the pinpointhq.com subdomain of the careers site: "eptura" for https://eptura.pinpointhq.com'
EMPLOYERS = {"Eptura (Teem)": "eptura"}
INSTITUTION = False
AGGREGATOR = False

def _postings(slug):
    """The site's posting list, the one its own careers page loads. Nothing in it is paged (36 on the
    largest seen); a reply that says otherwise fails rather than reading as complete."""
    try: d = json.loads(R.curl_text(f"https://{slug}.pinpointhq.com/postings.json", timeout=60))
    except ValueError: raise RuntimeError(f"unexpected reply (not JSON) from {slug}.pinpointhq.com") from None
    R.need(isinstance(d, dict) and isinstance(d.get("data"), list), "no data list")
    R.need(all(isinstance(j, dict) and j.get("title") and j.get("url") for j in d["data"]), "a posting without a title or a link")
    R.need(not (d.get("links") or {}).get("next"), "the list is paged, which this reader has never seen")
    return d["data"][:6000]

def _place(j):
    """"City, ST" in the US ("Atlanta" + "Georgia"), "Remote, " in front of a fully remote role. The list has
    no country: outside the US "province" holds the country, a region or nothing ("London" + "United Kingdom",
    "Poole" + "England", "Dundee" + ""), so the office's own label is added when the rest does not say where it is."""
    l = j.get("location") if isinstance(j.get("location"), dict) else {}
    # One employer fills the fields it has no use for with ".". All three are typed by hand, and a ";"
    # in one would be read as a second location.
    city, prov, name = [re.sub(r"\s*[;|]\s*", ", ", x).strip() if isinstance(x, str) and re.search(r"\w", x) else ""
                        for x in (l.get("city"), l.get("province"), l.get("name"))]
    place = R.city_state(city, prov)
    if not R.placed(place) and name and name.lower() not in place.lower():
        # "Cardiff" under the label "Cardiff (Spa Store)" is the label alone; "Dartford" under "Bluewater" is both
        place = name if place.lower() in name.lower() else f"{place} ({name})"
    if j.get("workplace_type") == "remote" and not R.REMOTE.search(place): place = "Remote, " + place if place else "Remote"
    return place

def _day(text):
    m = re.match(r"\d{4}-\d\d-\d\d", text or "")          # "2026-10-11T23:59:59+01:00": the day as the employer wrote it
    return m.group(0) if m else None

def _closed(url):
    """True when robots.txt closes this posting. It names single postings by their bare path
    ("/postings/<id>"), and the list links the "/en/postings/<id>" form of the same page."""
    bare = re.sub(r"\.com/[a-z]{2}(?:-[A-Z]{2})?/postings/", ".com/postings/", url)
    return not (R.robots(url)[0] and R.robots(bare)[0])

def _detail(url):
    """(day posted, country code) from the schema.org record a posting's own page carries."""
    page = R.curl_text(url, accept="text/html")
    recs = [b for b in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', page, re.S)
            if re.search(r'"@type"\s*:\s*"JobPosting"', b)]
    # a sign-in or bot-check page has no such record, and must not read as "no date, country unknown"
    pid = re.search(r"/postings/([0-9a-f-]{36})", url)
    R.need(recs and pid and pid.group(1) in recs[0], "no record of this posting on its page")
    day = re.search(r'"datePosted"\s*:\s*"(\d{4}-\d\d-\d\d)', recs[0])      # "2026-09-24T13:26:06+01:00": the day as the employer wrote it
    land = re.search(r'"addressCountry"\s*:\s*"([A-Za-z]{2})"', recs[0])
    return (day.group(1) if day else None), (land.group(1).upper() if land else None)

# Employers list roles open to their own staff beside the public ones and say so in the title
# ("Talent Pool - *Internal only*", "... **internal applications only**"). Nothing else in the list marks them.
_INTERNAL = re.compile(r"\binternal\W+(?:(?:applica\w+|candidates?|employees?|staff|hires?)\W+)?only\b", re.I)

def fetch(slug):
    """Return every open job as [(title, location, url, closes, degree, extra)]."""
    rows = []
    for j in _postings(slug):
        # each section goes in under its own heading ("About You"), which is what the years rule looks for
        text = "".join(f"<h3>{j.get(k + '_header') or ''}</h3>{j.get(k) or ''}"
                       for k in ("description", "key_responsibilities", "skills_knowledge_expertise"))
        title = re.sub(r"\s+", " ", j["title"]).strip()
        rows.append((title, _place(j), j["url"], _day(j.get("deadline_at")), R.degree_flag(text),
                     {"posted": None, "yrs": R.min_years(text), "internal": bool(_INTERNAL.search(title)), "company": None}))
    rows = R._dedupe(rows)
    kept = [i for i, r in enumerate(rows) if R.classify(r[0], r[1], KIND) or R.experienced(r[0], r[1], KIND)]
    kept.sort(key=lambda i: R.where(rows[i][1]) != "home")      # if the cap cuts the reads short, it cuts roles away from home
    missed = 0
    for i in kept[:60]:
        title, place, url, closes, degree, extra = rows[i]
        if _closed(url): missed += 1; continue
        try: extra["posted"], land = R.patient(_detail, url, slots=R._DETAIL_SLOTS)
        except Exception: missed += 1; continue          # a failed read keeps the row as listed, without its date
        # The page knows the country the list leaves out. A kept role that turns out to be in another one is
        # marked the way the Workday reader marks it, which is what drops "Remote, Leeds (Head Office)".
        if land and land not in ("US", "PR", "GU", "VI", "AS", "MP"): rows[i] = (title, f"{place} ({land}, abroad)", url, closes, degree, extra)
        time.sleep(0.3)
    if len(kept) > 60: R.PARTIAL[slug] = f"read details for the first 60 of {len(kept)} kept roles"
    elif missed: R.PARTIAL[slug] = f"posting page not read for {missed} of {len(kept)} kept roles"
    return rows

PINPOINT_LINK = re.compile(r"https://([\w-]+)\.pinpointhq\.com/(?:[a-z]{2}(?:-[A-Z]{2})?/)?postings/([0-9a-f-]{36})")
def link_state(url):
    """'live', 'dead' or 'unknown' for one posting URL of this system. Return 'unknown' whenever unsure."""
    m = PINPOINT_LINK.match(url or "")
    if not m: return "unknown"
    # The posting's own page answers, not the list: an employer can keep a posting off its careers site
    # and still take applications by direct link (robots.txt names such postings, and they are left
    # alone). A posting that is gone is a plain 404; one that is open carries its schema.org record.
    # The bare path is asked, because a language the site does not offer ("/fr/postings/<id>") is a
    # 404 for an open posting too.
    bare = f"https://{m.group(1)}.pinpointhq.com/postings/{m.group(2)}"
    try:
        if _closed(bare): return "unknown"
        code, page = R.curl_resp(bare, accept="text/html")
    except Exception: return "unknown"
    if code in ("404", "410"): return "dead"
    return "live" if code == "200" and '"JobPosting"' in page and m.group(2) in page else "unknown"

if __name__ == "__main__":
    for name, slug in EMPLOYERS.items():
        rows = fetch(slug)
        kept = [r for r in rows if R.classify(r[0], r[1], KIND) or R.experienced(r[0], r[1], KIND)]
        print(f"{name}: {len(rows)} jobs, {sum(1 for r in rows if R.HOME.search(r[1] or ''))} in Utah, {len(kept)} kept")
        for r in kept[:5]: print("   ", r[0], "|", r[1], "|", r[2], "|", r[3], "|", r[5])
