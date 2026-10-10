"""Larry H. Miller Company: the careers page on www.lhm.com carries every open job of its companies in one page of
HTML, and that page is all this reader asks for. Megaplex, Real Salt Lake, the Salt Lake Bees, LHM Real Estate,
Prestige Financial and the rest are printed as cards that link to the posting on UKG, with no date and no posting
text. The Senior Health tab's jobs sit in the same page as JSON, with their posted date and text, and link to
Paylocity. Neither system is asked for anything (UKG's robots.txt closes its job lists). The slug is the page's
address, host and path."""
import sys, os, re, json, time, datetime, urllib.parse
from html import unescape
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import refresh as R

KIND = "lhm"
SLUG_HELP = 'the address of the page that carries the jobs, host and path: "www.lhm.com/careers/"'
EMPLOYERS = {"Larry H. Miller Company": "www.lhm.com/careers/"}
INSTITUTIONS = set()  # names from EMPLOYERS that are public bodies, schools or hospitals, whose titles use "University", "Campus" or "Graduate" as plain description
AGGREGATOR = True     # one page, many companies: each row names its own in extra["company"]

SECTION = re.compile(r"<section\b[^>]*\sdata-lhm-ukg-jobs[\s>].*?</section>", re.S)   # one per group of companies
CARD = re.compile(r"<li\b[^>]*\sdata-lhm-ukg-job[\s>].*?</li>", re.S)                  # one per job
FEED = re.compile(r'<script\b[^>]*\sclass="ahc-paylocity-config"[^>]*>(.*?)</script>', re.S)   # the Senior Health tab's settings and jobs
APPLY = re.compile(r"recruiting\.paylocity\.com/recruiting/jobs/Apply/(\d+)", re.I)
# The page links each Senior Health job's application form. The posting it belongs to is at this address,
# the one the Paylocity reader uses, so that reader's link check answers for these rows too.
POSTING = "https://recruiting.paylocity.com/Recruiting/Jobs/Details/"
# Its jobs are filed under some forty care centers ("Advanced Health Care of St. George", "ASC OF FINCASTLE
# LLC"). The company is the one the tab is named for.
SENIOR_HEALTH = "Larry H. Miller Senior Health"

def _text(markup):
    """Markup as plain text: tags out, entities decoded, whitespace collapsed."""
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", str(markup or "")))).strip()

def _attr(tag, name):
    m = re.search(r'\sdata-%s="([^"]*)"' % name, tag)
    return _text(m.group(1)) if m else ""

def _place(loc, state=""):
    """A row's "Draper, UT" in the form the location rules read. A town with no state takes the state the
    row names beside it, or ", US": every company here works in the US."""
    city, sep, tail = loc.rpartition(", ")
    if not sep: city, tail = ("", loc) if loc == state else (loc, state)   # four Senior Health rows say "UT" and no town
    if city.islower(): city = city.title()                                # "waco, TX"
    loc = R.city_state(city, tail)                                        # abbreviates a state that is spelled out
    return loc if not loc or R.placed(loc) else loc + ", US"

def _day(text):
    """The page's "October 9, 2026" as "2026-10-09"."""
    try: return datetime.datetime.strptime(_text(text), "%B %d, %Y").strftime("%Y-%m-%d")
    except ValueError: return None

def _cards(sec):
    """The rows of one section of UKG job cards."""
    head = sec[:sec.index(">")]
    name, state, cards = _attr(head, "profile") or "a section", _attr(head, "state"), CARD.findall(sec)
    # The site fills each section itself and says how that went. Only "ready" has been seen; "empty" is
    # taken at its word. Any other state is a feed that did not load, and nothing is concluded from it.
    R.need(state in ("ready", "empty"), f"the {name} jobs are '{state}', not ready")
    # Each section states its own count. A card this reader cannot see fails here, so it is never read
    # as a job that closed.
    shown = re.search(r"lhm-ukg-jobs__status\b[^>]*>\s*(\d+)\s+openings?\s+shown", sec)
    R.need(int(shown.group(1)) == len(cards) if shown else not cards,
           f"{name}: {len(cards)} cards read where the page counts {shown.group(1) if shown else 'none'}")
    # The stylesheet has a notice box that today's page never shows. A section with a notice and no
    # card is taken for a feed that failed, not for companies with nothing open.
    note = re.search(r"lhm-ukg-jobs__notice\b[^>]*>(.*?)</", sec, re.S)
    R.need(cards or not note, f"{name}: {_text(note.group(1))[:60] if note else ''}")
    rows = []
    for card in cards:
        tag = card[:card.index(">")]
        title = re.search(r'class="lhm-ukg-jobs__title"[^>]*>(.*?)</span>', card, re.S)
        href = re.search(r'<a\b[^>]*\shref="([^"]+)"', card)
        title, url = _text(title.group(1)) if title else "", unescape(href.group(1)).strip() if href else ""
        R.need(title and url.startswith("https://"), "a card without a title or a link")
        rows.append((title, _place(_attr(tag, "location")), url, None, None,
                     {"posted": None, "yrs": None, "internal": False, "company": _attr(tag, "company") or None}))
    return rows

def _senior_health(page):
    """The rows of the Senior Health tab. The page carries its jobs as JSON, for its own script to print."""
    m = FEED.search(page)
    try: jobs = json.loads(m.group(1)).get("initialJobs") if m else None
    except (ValueError, AttributeError): jobs = None
    # When the page carries none, its script asks /wp-json/ for the list, and robots.txt closes that. Forty
    # care centers are never all without an opening, so no jobs here is a list this reader cannot see.
    R.need(isinstance(jobs, list) and jobs, "the Senior Health jobs are not in the page")
    rows = []
    for j in jobs:
        R.need(isinstance(j, dict), "a Senior Health job that is not a record")
        title, link = _text(j.get("title")), APPLY.search(str(j.get("applyUrl") or ""))
        R.need(title and link, "a Senior Health job without a title or a link")
        # The requirements arrive without the heading the page prints over them, so it is put back: under
        # it min_years reads a bare "2 years in home health" as the bar.
        duties, asks = str(j.get("descriptionDetails") or ""), str(j.get("requirements") or "")
        text = duties + ("<p>Job Requirements:</p>" + asks if asks else "") or None
        rows.append((title, _place(_text(j.get("location")), _text(j.get("state"))), POSTING + link.group(1), None,
                     R.degree_flag(text), {"posted": _day(j.get("createdDate")), "yrs": R.min_years(text),
                                           "internal": False, "company": SENIOR_HEALTH}))
    return rows

def _read(url):
    """Every row of the page. A page without the job sections is an error page or some other page, never
    "no jobs". Either half failing fails the read: half a page would report the other half's jobs as closed."""
    page = R.curl_text(url, accept="text/html", timeout=60)
    sections = SECTION.findall(page)
    R.need(sections, "no job sections on the page")
    return [row for sec in sections for row in _cards(sec)] + _senior_health(page)

def fetch(slug):
    """Return every open job as [(title, location, url, closes, degree, extra)]."""
    # The slug becomes the request as it stands, so anything but a plain host and path is refused.
    if not re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)+(/[\w/-]*)?", slug or ""):
        raise RuntimeError("the slug is not a page address like www.lhm.com/careers/")
    return R._dedupe(R.patient(_read, "https://" + slug))

# No link_state here. UKG is not asked, and the careers page is served from a cache that runs hours behind,
# so a posting missing from it is not proof that the posting is gone. The Senior Health links are
# Paylocity's, and the Paylocity reader answers for those.

if __name__ == "__main__":
    for name, slug in EMPLOYERS.items():
        rows = fetch(slug)
        kept = [r for r in rows if R.classify(r[0], r[1], KIND) or R.experienced(r[0], r[1], KIND)]
        print(f"{name}: {len(rows)} jobs, {sum(1 for r in rows if R.HOME.search(r[1] or ''))} in Utah, {len(kept)} kept")
        for r in kept[:5]: print("   ", r[0], "|", r[1], "|", r[2], "|", r[3], "|", r[5])
