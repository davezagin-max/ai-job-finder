"""Comeet (now Spark Hire Recruit): an employer's public careers page, www.comeet.com/jobs/<name>/<uid>, carries
every open position as JSON inside the page, posting text included, so one request reads the whole board. No key,
no sign-in, no token. The slug is the "<name>/<uid>" pair from that link. Comeet says when a position was last
changed, never when it was posted or when it closes, so both dates are left empty."""
import sys, os, re, json, time, datetime, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import refresh as R

KIND = "comeet"
SLUG_HELP = 'the "<name>/<uid>" pair in the careers link www.comeet.com/jobs/<name>/<uid>, for example "dfcu/B9.005"'
EMPLOYERS = {"Deseret First Credit Union": "dfcu/B9.005"}
INSTITUTIONS = set()  # names from EMPLOYERS that are public bodies, schools or hospitals, whose titles use "University", "Campus" or "Graduate" as plain description
AGGREGATOR = False    # True when one slug returns the jobs of many employers

SITE = "https://www.comeet.com/jobs/"
UID = r"[0-9A-Z]+\.[0-9A-Z]+"                    # "B9.005" names a company, "C8.378" a position
LINK = re.compile(r"^https?://(www\.comeet\.com/jobs/[A-Za-z0-9_-]+/(" + UID + r")/[^/?#]+/(" + UID + r"))(?![\w.])")
_US = ("US", "USA", "UNITED STATES", "PR", "GU", "VI", "AS", "MP")   # US territories are not abroad
# Comeet gives a country as its two-letter code only. The ones its boards mostly use are written out.
_COUNTRY = {"IL": "Israel", "GB": "United Kingdom", "CA": "Canada", "IN": "India", "DE": "Germany"}

def _var(page, name):
    """The value the page's own script gives one of its variables ("COMPANY_DATA = {...};")."""
    m = re.search(r"\b" + name + r"\s*=(?!=)\s*", page)
    # A link that names no company is answered with Comeet's own home page (HTTP 200), which has none of these.
    R.need(m, f"no {name} in the page: not a Comeet careers page, or a wrong slug")
    try: return json.JSONDecoder().raw_decode(page, m.end())[0]
    except ValueError: raise RuntimeError(f"unexpected reply ({name} is not JSON)")

def _place(l, workplace):
    """A position's location in the form the location rules read: "Salt Lake City, UT", "Remote, Boise, ID",
    "Tel Aviv (Israel, abroad)"."""
    # The label ("name") is free text: "City Creek Branch", "Operations Center", "Gilbert, AZ". The fields
    # beside it say where the place is, so the string is built from them.
    name, city, state, code = (re.sub(r"\s+", " ", str(l.get(k) or "")).strip() for k in ("name", "city", "state", "country"))
    code = code.upper()
    state = R.city_state("", state.upper() if len(state) == 2 else state)    # "Utah" becomes "UT"
    # The position's own workplace type says whether it is remote. The location's is_remote flag is set on
    # hybrid positions too, so it is read only when the position gives no type.
    remote = workplace.strip().lower() == "remote" if isinstance(workplace, str) and workplace.strip() else bool(l.get("is_remote"))
    # No country given: a US state still places it, and failing that the label is all there is.
    if not code and state not in R.STATE_NAMES.values(): return name or city
    if code and code not in _US:
        # Marked in the words the location rules read: "Haifa, IL" on its own would be taken for Illinois.
        return f"{city or ('Remote' if remote else name)} ({_COUNTRY.get(code, code)}, abroad)".strip()
    # A US city with no state gets "US", or "Dublin" and "Vienna" would read as foreign.
    place = ", ".join(x for x in (city, state if re.fullmatch(r"[A-Z]{2}", state) else "US") if x)
    return "Remote, " + place if remote else place

def fetch(slug):
    """Return every open job as [(title, location, url, closes, degree, extra)]."""
    # A pasted link or a path is refused here, before anything is asked.
    m = re.fullmatch(r"[A-Za-z0-9_-]+/(" + UID + ")", slug if isinstance(slug, str) else "")
    if not m: raise RuntimeError('comeet: the slug is the "<name>/<uid>" of the careers link, like "dfcu/B9.005"')
    page = R.curl_text(SITE + slug, accept="text/html", timeout=60)
    company, positions = _var(page, "COMPANY_DATA"), _var(page, "COMPANY_POSITIONS_DATA")
    # The uid is the employer. It is checked so that a link the site sends elsewhere is never read as this one.
    R.need(isinstance(company, dict) and company.get("company_uid") == m.group(1), "another company's page")
    R.need(isinstance(positions, list), "no list of positions")
    if len(positions) > 6000:
        R.PARTIAL[slug] = f"read the first 6,000 of {len(positions):,} positions"; positions = positions[:6000]
    rows = []
    for j in positions:
        R.need(isinstance(j, dict) and isinstance(j.get("name"), str) and j["name"].strip() and LINK.match(str(j.get("url_comeet_hosted_page") or "")),
               "a position without a title or a link")
        loc = j.get("location") if isinstance(j.get("location"), dict) else {}
        parts = j["custom_fields"].get("details") if isinstance(j.get("custom_fields"), dict) else None
        # The posting comes in named parts ("Description", "Requirements", "Salary"). Each name is put back as
        # a heading, because min_years reads a number of years under "Requirements" as the bar.
        text = "".join(f"<h3>{d.get('name') or ''}</h3>{d['value']}" for d in (parts if isinstance(parts, list) else [])
                       if isinstance(d, dict) and d.get("value"))
        rows.append((re.sub(r"\s+", " ", j["name"]).strip(), _place(loc, j.get("workplace_type")),
                     j["url_comeet_hosted_page"], None, R.degree_flag(text),
                     # time_updated is the day of the last edit, not of the posting, so it is not passed off
                     # as the posted date.
                     {"posted": None, "yrs": R.min_years(text), "internal": bool(j.get("is_internal")), "company": None}))
    return R._dedupe(rows)

def link_state(url):
    """'live', 'dead' or 'unknown' for one posting URL of this system. Return 'unknown' whenever unsure."""
    m = LINK.match(url or "")
    if not m: return "unknown"
    cuid, uid = m.group(2), m.group(3)
    try:
        page = R.curl_text("https://" + m.group(1), accept="text/html")
        company, position, listed = (_var(page, n) for n in ("COMPANY_DATA", "POSITION_DATA", "COMPANY_POSITIONS_DATA"))
    except Exception:
        return "unknown"
    if not isinstance(company, dict) or company.get("company_uid") != cuid: return "unknown"
    # An open position's page carries the position itself.
    if isinstance(position, dict): return "live" if position.get("uid") == uid else "unknown"
    # For one that is gone the site answers HTTP 200 with the company's list of openings instead. Dead only
    # when that list is there and does not name it.
    if position is None and isinstance(listed, list) and all(isinstance(j, dict) and j.get("uid") for j in listed):
        return "unknown" if uid in {j["uid"] for j in listed} else "dead"
    return "unknown"

if __name__ == "__main__":
    for name, slug in EMPLOYERS.items():
        rows = fetch(slug)
        kept = [r for r in rows if R.classify(r[0], r[1], KIND) or R.experienced(r[0], r[1], KIND)]
        print(f"{name}: {len(rows)} jobs, {sum(1 for r in rows if R.HOME.search(r[1] or ''))} in Utah, {len(kept)} kept")
        for r in kept[:5]: print("   ", r[0], "|", r[1], "|", r[2], "|", r[3], "|", r[5])
