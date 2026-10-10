"""Sportsman's Warehouse: its own careers site (careers.sportsmans.com) prints the openings as an HTML table of
schema.org JobPosting rows, two hundred to a request, each with its store, the day it was posted and the day it
expires. The table carries a posting's duties but not its requirements, so the years and the degree are read
from the posting's own page, for the kept roles only. The slug is the careers site's host name."""
import sys, os, re, json, time, datetime, urllib.parse
from html import unescape
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import refresh as R

KIND = "sportsmans"
SLUG_HELP = 'the host name of the careers site: "careers.sportsmans.com"'
EMPLOYERS = {"Sportsman's Warehouse": "careers.sportsmans.com"}
INSTITUTIONS = set()  # names from EMPLOYERS that are public bodies, schools or hospitals, whose titles use "University", "Campus" or "Graduate" as plain description
AGGREGATOR = False    # True when one slug returns the jobs of many employers

PAGE = 200            # rows asked for in one request (the site's own pages are ten rows long)
MAX_DETAILS = 60
ROW = re.compile(r'<tr\b[^>]*\sitemtype="https?://schema\.org/JobPosting"[^>]*>(.*?)</tr>', re.S)
COUNT = re.compile(r"\(Results\s+(\d+)\s*-\s*(\d+)\s+of\s+(\d+)\)")
LINK = re.compile(r"careers\.sportsmans\.com/career/([^/?#]+)/(\d+)")
# The site names two of its own buildings where the town should be: the head office and the warehouse.
BUILDINGS = {"Corporate": "West Jordan", "Dist. Center (SLC)": "Salt Lake City"}

def _text(markup):
    """Markup as plain text: tags out, entities decoded, whitespace collapsed."""
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", markup or ""))).strip()

def _prop(row, name):
    """The text of one schema.org property of a row."""
    m = re.search(r'\sitemprop="%s"[^>]*>(.*?)</span>' % name, row, re.S)
    return _text(m.group(1)) if m else ""

def _day(text):
    """The site's "10/09/2026" as "2026-10-09"."""
    try: return datetime.datetime.strptime(text, "%m/%d/%Y").strftime("%Y-%m-%d")
    except ValueError: return None

def _row(host, row):
    """(title, location, url, closes, posted) for one row of the table."""
    a = re.search(r'<a\b[^>]*\shref="(/career/[^"/]+/\d+/)"[^>]*>(.*?)</a>', row, re.S)
    R.need(a and _text(a.group(2)), "a job without a title or a link")
    city, state = _prop(row, "addressLocality"), _prop(row, "addressRegion")
    if state == "UT": city = BUILDINGS.get(city, city)
    # Every store is in the US, so a row that ever came without its state says "US" rather than nothing.
    return (_text(a.group(2)), R.city_state(city, state or "US"), f"https://{host}{a.group(1)}",
            _day(_prop(row, "validThrough")), _day(_prop(row, "datePosted")))

def _page(host, n):
    """One page of the list: (its rows, the first and last row numbers it says it shows, the total it counts)."""
    body = R.curl_text(f"https://{host}/career/page/{n}/rows/{PAGE}/keywords/All/site/100/state/", accept="text/html", timeout=90)
    found, m = ROW.findall(body), COUNT.search(body)
    if m: return (found,) + tuple(int(x) for x in m.groups())
    # With nothing open the site prints this sentence in place of the count and the table. A page with
    # neither is an error page, a bot check or another site, never "no jobs".
    R.need(not found and "There are no records." in body and 'id="queryCareer"' in body, "not the careers list")
    return [], 1, 0, 0

def _posting(url):
    """The text of one posting, read from its own page: the duties, then the requirements."""
    body = R.curl_text(url, accept="text/html", timeout=60)
    m = re.search(r'<span itemprop="description">(.*?)<button\b', body, re.S)   # up to the Apply button under the text
    # A posting that has just gone, an error page and a bot check all lack the posting's own number.
    R.need(m and re.search(r"<strong>ID:</strong>\s*%s\b" % url.rstrip("/").rsplit("/", 1)[1], body), "not this job's page")
    return m.group(1)

def fetch(slug):
    """Return every open job as [(title, location, url, closes, degree, extra)]."""
    host = (slug or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)+", host): raise RuntimeError("the slug is not a host name like careers.sportsmans.com")
    listed, n, total, notes = [], 1, None, []
    while True:
        found, first, last, count = R.patient(_page, host, n)
        # The page says which rows it shows. They must follow on from the rows already read, and the total
        # must not move while reading: a job posted or closed in between shifts every later row by one.
        R.need(first == len(listed) + 1 and last - first + 1 == len(found) and total in (None, count), "the pages do not line up")
        listed += [_row(host, r) for r in found]; total = count
        if last >= total or not found or len(listed) >= 6000 or n >= 150: break
        n += 1; time.sleep(0.3)
    if len(listed) < total: notes.append(f"read the first {len(listed):,} of {total:,} jobs")
    # Only the roles that will be published are worth a request each, one at a time, the ones near home first.
    kept = sorted((x for x in listed if R.classify(x[0], x[1], KIND) or R.experienced(x[0], x[1], KIND)),
                  key=lambda x: not R.HOME.search(x[1]))
    if len(kept) > MAX_DETAILS: notes.append(f"read details for the first {MAX_DETAILS} of {len(kept)} kept roles")
    texts, failed, streak = {}, 0, 0
    for x in kept[:MAX_DETAILS]:
        if streak >= 3: failed += 1; continue    # the site is refusing: stop asking rather than retry sixty jobs
        try: texts[x[2]] = R.patient(_posting, x[2], slots=R._DETAIL_SLOTS); streak = 0
        except R.OffLimits: raise
        except Exception: failed += 1; streak += 1   # the row is kept as listed rather than dropped
        time.sleep(0.2)
    if failed: notes.append(f"{failed} of {min(len(kept), MAX_DETAILS)} postings could not be read")
    if notes: R.PARTIAL[slug] = "; ".join(notes)
    return R._dedupe([(title, loc, url, closes, R.degree_flag(texts.get(url)),
                       {"posted": posted, "yrs": R.min_years(texts.get(url)), "internal": False, "company": None})
                      for title, loc, url, closes, posted in listed])

def link_state(url):
    """'live', 'dead' or 'unknown' for one posting URL of this system. Return 'unknown' whenever unsure."""
    m = LINK.search(url or "")
    if not m: return "unknown"
    # The closing slash matters: without it the site answers with its front page.
    try: code, body = R.curl_resp(f"https://careers.sportsmans.com/career/{m.group(1)}/{m.group(2)}/", accept="text/html")
    except Exception: return "unknown"
    # A live posting prints its own number. One that is gone answers 200 with the careers page's frame around
    # an empty posting, which leaves the page title as " - , Careers & Jobs". Anything else (an error page,
    # a bot check, the front page) is no answer.
    if code != "200" or 'id="smwhHTagLink"' not in body: return "unknown"
    if re.search(r"<strong>ID:</strong>\s*%s\b" % m.group(2), body): return "live"
    return "dead" if re.search(r"<title>\s*-\s*,\s+Careers\b", body) and "schema.org/JobPosting" not in body else "unknown"

if __name__ == "__main__":
    for name, slug in EMPLOYERS.items():
        rows = fetch(slug)
        kept = [r for r in rows if R.classify(r[0], r[1], KIND) or R.experienced(r[0], r[1], KIND)]
        print(f"{name}: {len(rows)} jobs, {sum(1 for r in rows if R.HOME.search(r[1] or ''))} in Utah, {len(kept)} kept")
        for r in kept[:5]: print("   ", r[0], "|", r[1], "|", r[2], "|", r[3], "|", r[5])
