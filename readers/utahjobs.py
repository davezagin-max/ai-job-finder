"""Utah's state job bank (jobs.utah.gov, Department of Workforce Services): one public search that
lists jobs from thousands of Utah employers, including many whose own career sites cannot be read by
a script. The slug is "zip|miles|keyword;keyword;...": each keyword is one search around that zip code.
A row is a lead, not a posting: it has the employer, title, city and dates, but its link opens the job
bank, which asks for a free UtahID sign-in before it shows the details."""
import sys, os, re, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import refresh as R

KIND = "utahjobs"
SLUG_HELP = '"zip|miles|keyword;keyword", for example "84101|50|analyst;data;software"'
EMPLOYERS = {"Utah state job bank": "84101|50|analyst;data;business intelligence;information systems;security;audit;software;"
                                    "developer;engineer;product;risk;compliance;accounting;scientist"}
AGGREGATOR = True     # one slug, many employers: every row names its own in extra["company"]
LEADS = True          # a row links to the job bank, not to the employer, so the page shows it as a lead

SEARCH = "https://jobs.utah.gov/jsp/utjobs/rest/seeker/search/basic-job-search.json"
ROWS = 3000           # the search has no pages; it returns as many rows as it is asked for
_SMALL = {"and", "of", "the", "for", "at", "in", "on", "an", "a", "de", "la"}
_KEEP = {"llc", "llp", "lp", "usa", "us", "it", "hr", "ey", "kpmg", "ibm", "sap", "hca", "ups", "pwc", "byu", "arup", "wgu", "ge", "bd", "bae", "caci", "kbr", "saic", "rtx"}

CUT = 40              # the job bank cuts a longer title off at this many characters, sometimes mid-word
_LEVEL_WORDS = ("manager", "director", "principal", "senior", "architect", "supervisor", "leader")

def _title(raw):
    """A title as listed, marked with an ellipsis when it was cut. A cut-off last word that can only be
    the start of a level word ("Strategy Manag") is completed, because the title rules read whole words
    and would otherwise take a manager's job for an entry-level one."""
    t = re.sub(r"\s+", " ", re.sub(r",(?=\S)", ", ", raw or "")).strip()
    if len(raw or "") < CUT: return t
    m = re.search(r"([A-Za-z]{4,})$", t)
    if m:
        full = next((w for w in _LEVEL_WORDS if w.startswith(m.group(1).lower()) and w != m.group(1).lower()), None)
        if full: t = t[:m.start()] + (full.title() if m.group(1)[0].isupper() else full)
    return t + "\u2026"

def _name(raw):
    """The job bank types many employers in capitals ("COTIVITI, INC."); set those in ordinary case."""
    s = re.sub(r"\s+", " ", re.sub(r",(?=\S)", ", ", raw or "")).strip()
    m = re.match(r"(.*), the$", s, re.I)
    if m: return "The " + _name(m.group(1))           # "HASKELL COMPANY, THE"
    if not s or s != s.upper() or (" " not in s and len(s) <= 5): return s
    words = []
    for i, w in enumerate(s.split(" ")):
        bare = re.sub(r"[^a-z0-9]", "", w.lower())
        if bare in _KEEP or (len(bare) <= 4 and re.search(r"\d", bare)): words.append(w)
        elif i and bare in _SMALL: words.append(w.lower())
        else: words.append(w.capitalize() if "'" in w else w.title())
    return " ".join(words)

# The job bank shortens a city to 17 characters and abbreviates a few.
_CITY = {"Hill Air Force Ba": "Hill Air Force Base", "Cottonwood Height": "Cottonwood Heights", "Salt Lake Cty": "Salt Lake City",
         "North Salt Lake C": "North Salt Lake", "South Salt Lake C": "South Salt Lake", "West Valley Cty": "West Valley City"}

def _place(city, state, telework):
    city = re.sub(r"\s+", " ", (city or "").title()).strip()
    city = _CITY.get(city, re.sub(r"\bCty\b", "City", city))
    loc = ", ".join(x for x in (city, (state or "").upper()) if x)
    return (loc + "; " if loc and telework else loc) + ("Remote" if telework else "")

def fetch(slug):
    """Return every listed job as [(title, location, url, closes, degree, extra)]."""
    parts = slug.split("|")
    R.need(len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit() and parts[2].strip(), "slug is not zip|miles|keywords")
    zip_code, miles, keywords = parts[0], int(parts[1]), [k.strip() for k in parts[2].split(";") if k.strip()]
    seen, cut = {}, []
    for n, kw in enumerate(keywords):
        if n: time.sleep(1.5)                     # a dozen large replies: leave the server room between them
        d = R.curl(f"{SEARCH}?rowsToFetch={ROWS}", {"search": {"keywords": kw, "zip": zip_code, "radius": miles,
                   "keywordsAndOr": "A", "filter": ""}, "page": 1}, 120, method="PUT")
        R.need(isinstance(d, dict) and isinstance(d.get("jobs"), list), "no jobs list")
        if len(d["jobs"]) > ROWS: cut.append(kw)   # one row more than asked for means there were more still
        for j in d["jobs"]:
            if j.get("jadrId") and j.get("jobTitle") and j.get("url"): seen.setdefault(j["jadrId"], j)
    if cut: R.PARTIAL[slug] = f"more than {ROWS:,} jobs matched " + ", ".join(repr(k) for k in cut) + ", so those searches were cut short"
    rows = []
    for j in seen.values():
        if (j.get("state") or "").upper() != "UT" and j.get("telecommuteFlag") != "Y": continue     # the radius reaches into Idaho and Nevada
        named = j.get("suppressEmprName") != "Y" and (j.get("employerName") or "").strip()
        date = lambda v: v if re.match(r"\d{4}-\d{2}-\d{2}$", str(v or "")) else None
        rows.append((_title(j["jobTitle"]),
                     _place(j.get("city"), j.get("state"), j.get("telecommuteFlag") == "Y"), j["url"], date(j.get("closeDate")), None,
                     {"posted": date(j.get("openDate")), "yrs": None, "internal": False,
                      "company": _name(named) if named else "Employer not named (Utah job bank)"}))
    return R._dedupe(rows)

if __name__ == "__main__":
    for name, slug in EMPLOYERS.items():
        rows = fetch(slug)
        kept = [r for r in rows if R.classify(r[0], r[1], KIND) or R.experienced(r[0], r[1], KIND)]
        print(f"{name}: {len(rows)} jobs, {sum(1 for r in rows if R.HOME.search(r[1] or ''))} in Utah, {len(kept)} kept, {len({r[5]['company'] for r in rows})} employers")
        for r in kept[:8]: print("   ", r[0], "|", r[1], "|", r[2], "|", r[3], "|", r[5])
        print("    partial:", R.PARTIAL.get(slug))
