"""Teamtailor: every Teamtailor career site publishes its open jobs as RSS at https://<host>/jobs.rss, public and
with no key, a hundred jobs a request, each with its posting text, the day it was posted and its locations. A
closing date is stated only on the posting's own page, so that page is opened for the roles the filters keep.
The slug is the career site's own host ("careerunitedstates.autoliv.com"). A location gives a city, a ZIP code
and a country but no state, so the state of a US job is read from its ZIP code."""
import sys, os, re, json, time, datetime, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import refresh as R

KIND = "teamtailor"
SLUG_HELP = 'the host of the career site, the part of its address before /jobs: "careerunitedstates.autoliv.com"'
EMPLOYERS = {"Autoliv": "careerunitedstates.autoliv.com"}   # the US site; career.autoliv.com is the worldwide one
INSTITUTIONS = set()  # names from EMPLOYERS that are public bodies, schools or hospitals, whose titles use "University", "Campus" or "Graduate" as plain description
AGGREGATOR = False    # True when one slug returns the jobs of many employers

PAGE = 100            # the feed's own page size, asked for by name in case the default ever changes
MAX_DETAILS = 60      # posting pages opened for one employer
# The first three digits of a ZIP code say which state it is in (the Postal Service's prefix table).
_ZIP3 = [(int(lo), int(hi or lo), st) for lo, hi, st in re.findall(r"(\d{3})(?:-(\d{3}))? ([A-Z]{2})",
    "005 NY 006-007 PR 008 VI 009 PR 010-027 MA 028-029 RI 030-038 NH 039-049 ME 050-054 VT 055 MA 056-059 VT "
    "060-069 CT 070-089 NJ 100-149 NY 150-196 PA 197-199 DE 200 DC 201 VA 202-205 DC 206-219 MD 220-246 VA "
    "247-268 WV 270-289 NC 290-299 SC 300-319 GA 320-339 FL 341-349 FL 350-369 AL 370-385 TN 386-397 MS "
    "398-399 GA 400-427 KY 430-459 OH 460-479 IN 480-499 MI 500-528 IA 530-549 WI 550-567 MN 570-577 SD "
    "580-588 ND 590-599 MT 600-629 IL 630-658 MO 660-679 KS 680-693 NE 700-714 LA 716-729 AR 730-732 OK 733 TX "
    "734-749 OK 750-799 TX 800-816 CO 820-831 WY 832-838 ID 840-847 UT 850-865 AZ 870-884 NM 885 TX 889-898 NV "
    "900-961 CA 967-968 HI 969 GU 970-979 OR 980-994 WA 995-999 AK")]
# Territories are named as countries of their own in the feed. They are not abroad, and their ZIP codes are US ones.
_US = {"united states", "united states of america", "usa", "us", "puerto rico", "guam", "u.s. virgin islands"}
_MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()

def _raw(block, tag):
    """What one element of the feed holds, with the XML escaping undone. "" when it is missing or empty."""
    m = re.search(rf"<{tag}>(.*?)</{tag}>", block, re.S)
    return R.html_unescape(m.group(1)) if m else ""

def _text(block, tag):
    return re.sub(r"\s+", " ", _raw(block, tag)).strip()

def _state(block):
    """The state of a US location, from its ZIP code. Without one, from a city, label or address that
    ends in a state ("Lehi, UT", "2600 Executive Pkwy, Lehi, Utah 84043"). "" when nothing says."""
    m = re.search(r"(?<!\d)(\d{3})\d{2}(?!\d)", _text(block, "tt:zip"))
    st = next((st for lo, hi, st in _ZIP3 if m and lo <= int(m.group(1)) <= hi), "")
    for tag in ("tt:city", "tt:name", "tt:address"):
        if st: break
        # Only the end of the line is read: "1200 Washington Ave" is a street, not a state.
        m = re.search(r",\s*([A-Za-z ]+?)(?:\s+\d{5}(?:-\d{4})?)?$", _text(block, tag))
        word = m.group(1) if m else ""
        st = word if word in R.STATE_NAMES.values() else R.STATE_NAMES.get(word.title(), "")
    return st

def _place(block, remote):
    """One location of a job in the form the location rules read: "Ogden, UT", "Remote, Ogden, UT" for a
    remote job tied to a place, "Chicago, US" when nothing says the state, "Brasov (Romania, abroad)"."""
    # The label ("Ogden - Assembly (AOA)") names a building, so the string is built from the fields beside it.
    city, country = _text(block, "tt:city") or _text(block, "tt:name"), _text(block, "tt:country")
    # ";" and "|" are what the location rules split a list of places on: a city typed "Lyon; Bron" would be
    # read as two places, and the first of them, with no country beside it, taken for a US town.
    city = re.sub(r"\s*[;|]\s*", ", ", city)
    if country and country.lower() not in _US:
        # Marked in the words the location rules read, because they do not know every country by name:
        # "Sopronkovesd, Hungary" is caught, "Sousse, Tunisia" would be taken for a US town.
        return f"{city} ({re.sub(r'[()]', '', country)}, abroad)".strip()
    # With no country named the place is left as written. A US city typed as "Lehi, UT" gives its state once.
    place = R.city_state(city.split(",")[0], _state(block) or "US") if country else city
    # A board that names a location "Remote" has said it already ("Remote, US", not "Remote, Remote, US").
    return "Remote, " + place if remote and place and not place.lower().startswith("remote") else place

def _day(stamp):
    """"Tue, 22 Sep 2026 10:21:38 -0400" as "2026-09-22"."""
    # The time is written in the career site's own zone, so the date in it is the local day as posted.
    m = re.search(r"(\d{1,2}) ([A-Z][a-z]{2}) (\d{4})", stamp)
    try: return datetime.date(int(m.group(3)), _MONTHS.index(m.group(2)) + 1, int(m.group(1))).isoformat()
    except (AttributeError, ValueError): return None

def _page(host, off):
    """The jobs on one page of the feed, each as its own block of XML. None when the host has no such feed."""
    code, xml = R.curl_resp(f"https://{host}/jobs.rss?per_page={PAGE}&offset={off}", accept="application/rss+xml, application/xml", timeout=90)
    if code == "404": return None                 # a plain no, which asking twice more would not change
    if not code.startswith("2"): raise RuntimeError(f"HTTP {code} from {host}")
    # Teamtailor's feed declares its own namespace, which an error page or another system's feed does not.
    # The closing tag shows the reply arrived whole: one cut off by a timeout would read as a shorter board.
    R.need(re.search(r"<rss\b[^>]*teamtailor\.com", xml[:600]) and xml.rstrip().endswith("</rss>"), "not a whole Teamtailor job feed")
    # The feed names the site it belongs to. A career site that has moved redirects to wherever it went,
    # and that can be another employer's board.
    home = re.search(r"<link>\s*https?://([^/<\s]+)", xml.split("<item>", 1)[0])
    R.need(home and home.group(1).lower() == host, f"this feed belongs to {home.group(1) if home else 'no named site'}, not {host}")
    items = re.findall(r"<item>(.*?)</item>", xml, re.S)
    # A job written any other way would be passed over, and a board of them would read as empty.
    R.need(len(items) == len(re.findall(r"<item\b", xml)), "jobs written in a way this reader does not know")
    return items

def _closing(link):
    """The day a posting stops taking applications, from the schema.org record on its own page. None when
    the employer set no end, which is the usual case."""
    page = R.curl_text(link, accept="text/html", timeout=60)       # a posting that has closed answers 410, which raises
    jid = re.search(r"/jobs/(\d+)", link).group(1)
    for rec in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', page, re.S):
        try: d = json.loads(rec)
        except ValueError: continue
        ident = d.get("identifier") if isinstance(d, dict) else None
        if isinstance(ident, dict) and d.get("@type") == "JobPosting" and str(ident.get("value")) == jid:
            # "2026-11-13 23:59:59 +0100": the day as the employer set it, in the career site's own zone.
            m = re.match(r"\d{4}-\d\d-\d\d", str(d.get("validThrough") or ""))
            return m.group(0) if m else None
    # A bot check or a sign-in page carries no such record, and must not read as "no closing date".
    raise RuntimeError("unexpected reply (no record of this posting on its page)")

def fetch(slug):
    """Return every open job as [(title, location, url, closes, degree, extra)]."""
    host = (slug or "").strip().lower()
    # A pasted link or a path is refused: only a bare host can be asked for its own /jobs.rss.
    if not re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)+", host): raise RuntimeError("the slug is not a career site host (like careers.example.com)")
    rows, written, off, asked, twice, notes = [], {}, 0, 0, 0, []
    while True:
        items = R.patient(_page, host, off); asked += 1
        if items is None: raise RuntimeError(f"HTTP 404 from {host} (no Teamtailor job feed at this address)")
        # The feed never says how many jobs there are, so it is read until a page comes back empty: a
        # short page would also be what a lowered page size looks like.
        if not items: break
        fresh = 0
        for it in items:
            # A title pasted in from a web page can carry its own "&amp;", which the feed then escapes again.
            title = re.sub(r"\s+", " ", R.html_unescape(_raw(it, "title"))).strip()
            link = re.match(r"(https://[^/\s]+/(?:[\w-]+/)?jobs/\d+)\S*$", _text(it, "link"))
            R.need(title and link, "a job without a title or a posting link")
            # The words after the number follow the title, and employers reword titles (Autoliv's
            # ".../2157038-database-systems-engineer" became "...-scada-systems-engineer"). The link is kept
            # up to the number, which stays the same posting and is sent on to the current wording.
            url = link.group(1)
            if url in written: twice += 1; continue
            written[url] = link.group(0); fresh += 1
            remote = _text(it, "remoteStatus") == "fully"      # "hybrid" and "temporary" still come to the place named
            places = [_place(b, remote) for b in re.findall(r"<tt:location>(.*?)</tt:location>", it, re.S)]
            loc = "; ".join(p for p in dict.fromkeys(places) if p) or ("Remote" if remote else "")
            text = _raw(it, "description")                     # the whole posting, as HTML
            # The feed lists public postings only: the internal board is a separate address that robots.txt closes.
            rows.append((title, loc, url, None, R.degree_flag(text),
                         {"posted": _day(_text(it, "pubDate")), "yrs": R.min_years(text), "internal": False, "company": None}))
        # A page of nothing but jobs already read means the offset was ignored, and asking on would never end.
        R.need(fresh, "the feed repeated a page")
        off += len(items)                                      # by what arrived, whatever size the page was
        if len(rows) >= 6000 or asked >= 150:
            notes.append(f"stopped after {len(rows):,} jobs in {asked} requests; the feed may hold more")
            break
        time.sleep(0.3)
    # With no count to check against, a job met twice is the one sign that the list moved while it was read.
    if twice: notes.append(f"{twice} jobs came twice as the pages were read, so the list shifted and one may be missing")
    rows = rows[:6000]
    # Only the roles that will be published are worth a second request each, one at a time.
    kept = [i for i, r in enumerate(rows) if R.classify(r[0], r[1], KIND) or R.experienced(r[0], r[1], KIND)]
    kept.sort(key=lambda i: R.where(rows[i][1]) != "home")     # if the cap cuts the reads short, it cuts roles away from home
    if len(kept) > MAX_DETAILS: notes.append(f"closing dates read for the first {MAX_DETAILS} of {len(kept)} kept roles")
    missed, streak = 0, 0
    for i in kept[:MAX_DETAILS]:
        page = written[rows[i][2]]                             # the link as the feed wrote it, which needs no redirect
        try:
            # A page robots.txt closes is not asked for, and three failures in a row is the site refusing.
            if streak >= 3 or not R.robots(page)[0]: raise RuntimeError("not asked")
            closes = R.patient(_closing, page, slots=R._DETAIL_SLOTS); streak = 0
            rows[i] = rows[i][:3] + (closes,) + rows[i][4:]
        except Exception: missed += 1; streak += 1             # the row is kept as listed, without a closing date
        if streak < 3: time.sleep(0.2)                         # a pause after a page that failed too, none once the asking has stopped
    if missed: notes.append(f"posting page not read for {missed} of {min(len(kept), MAX_DETAILS)} kept roles, so a closing date may be missing")
    if notes: R.PARTIAL[slug] = "; ".join(notes)
    return R._dedupe(rows)

# No link_state here: a posting that is closed answers HTTP 410 and a live one 200, which is what
# refresh.link_state() already asks of any link no reader claims.

if __name__ == "__main__":
    for name, slug in EMPLOYERS.items():
        rows = fetch(slug)
        kept = [r for r in rows if R.classify(r[0], r[1], KIND) or R.experienced(r[0], r[1], KIND)]
        print(f"{name}: {len(rows)} jobs, {sum(1 for r in rows if R.HOME.search(r[1] or ''))} in Utah, {len(kept)} kept")
        for r in kept[:5]: print("   ", r[0], "|", r[1], "|", r[2], "|", r[3], "|", r[5])
