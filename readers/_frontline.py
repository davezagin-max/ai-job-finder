"""Frontline Recruiting and Hiring (AppliTrack): a school district's board at applitrack.com/<district>/onlineapp.
The board page names the district's Position Types with their counts; each wanted type's postings come from the
script that page loads (jobpostings/Output.asp, Condensed View). The slug is "district|location to assume"."""
import sys, os, re, json, time, datetime, threading, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import refresh as R

KIND = "frontline"
SLUG_HELP = 'the district id in applitrack.com/<id>/onlineapp, "|", the location to assume: "jordandistrict|West Jordan, UT (check posting)"'
EMPLOYERS = {
    "Jordan School District":  "jordandistrict|West Jordan, UT (check posting)",
    "Alpine School District":  "alpineschools|American Fork, UT (check posting)",
    "Granite School District": "graniteschools|Salt Lake City, UT (check posting)",
}
INSTITUTION = True    # "Campus Monitor", "Graduate" and the like are plain description here
AGGREGATOR = False

# NOT every open job: a district's board is mostly teaching, aide, custodial and volunteer work, and the title
# rules would keep some of it ("2026-2027 Volunteer Application" reads as a new-graduate program). So whole
# Position Types are left out by name and the rest are read. Each district names its own types, and a type
# these lists have never seen is read. A posting names a school or department, never a city: hence the slug.
_CLASSROOM = re.compile(r"teach|instruct|classroom|paraeducator|paraprofessional|\baides?\b|tutor|\bsp\.?\s?ed\b|special ed|substitut", re.I)
# Licensed, student-support, trades and unpaid work
_OTHER_TYPE = re.compile(r"certified|certificated|licensed|coach|athletic|volunteer|\bstudents?\b|\bintern(?:s|ship)?\b|"
                         r"custod|nutrition|food|transport|\bbus\b|maintenance|nurs", re.I)
# The work wanted. A type or title that names it is kept whatever else it says ("Instructional Technology").
_KEEP = re.compile(r"technolog|information|comput|network|\bdata\b|assess|business|financ|account|purchas|district|office", re.I)
# Classroom jobs filed under a type that does not say so (Alpine's "Support Staff" holds "ML Instructional
# Paraprofessional", which the title rules read as machine learning). Job nouns only, so that an office job
# described by its department ("Instructional Systems Analyst", "Special Education Compliance Analyst") stays.
_AIDE = re.compile(r"paraeducator|paraprofessional|\bparas?\b|\baides?\b|\btutors?\b|\bteachers?\b|\bsubstitutes?\b|"
                   r"\b(?:teaching|classroom|instructional) assistant", re.I)
_INTERNAL = re.compile(r"\binternal\b|\bcurrent (?:\w+ )?(?:employees?|administrators?|staff)\b", re.I)
# One row of the Condensed View: title, job id, then the date cells, which the table's own header names
_ROW = re.compile(r"<span class='title'>(.*?)\s*<a href='[^']*AppliTrackJobId%3D(\d+)[^']*'[^>]*>view</a></span></td>(.*?)</tr>", re.S)
_ALL = "https://www.applitrack.com/%s/onlineapp/jobpostings/Output.asp?all=1&AppliTrackLayoutMode=condensed"
LINK = re.compile(r"applitrack\.com/([^/]+)/onlineapp/[^?]*\?(?:[^#]*&)?AppliTrackJobId=(\d+)", re.I)

class _NotUtf8(RuntimeError):
    """The reply is Windows-1252 text that R's curl helpers, which decode strictly as UTF-8, cannot read."""

def _date(text):
    m = re.match(r"\s*(\d{1,2})/(\d{1,2})/(\d{4})", text or "")
    return f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}" if m else None

def _script(url):
    """Output.asp is a script of document.write('...') calls. Return the HTML they write."""
    try: js = R.curl_text(url, timeout=60, accept="*/*")
    except UnicodeDecodeError:
        # Every list read so far was plain ASCII, so in practice this is a posting's own text, where a dash
        # or curly quote pasted from Word is sent as a raw Windows-1252 byte.
        raise _NotUtf8("AppliTrack sent Windows-1252 text, which is not readable as UTF-8")
    # Every reply closes its form after the list, so one cut short by a timeout is never read as a short list
    R.need("</form>" in js.partition("AppliTrackListContent")[2], "not a whole AppliTrack list of postings")
    return re.sub(r"'\);\s*document\.write\('", "", js).replace("\\'", "'")

def _rows(html):
    """[(title, job id, posted, closes)] for a Condensed View list."""
    # The date columns are found by their headings (Posted On, Available, Closes), not by position, so a
    # district that shows other columns gets no dates instead of the wrong ones
    heads = [re.sub(r"<[^>]+>|&\w+;", "", h).strip().lower() for h in re.findall(r"<th[^>]*>(.*?)</th>", html, re.S)][1:]
    out = []
    for title, jid, rest in _ROW.findall(html):
        cells = dict(zip(heads, re.findall(r"<td[^>]*>(.*?)</td>", rest, re.S)))
        # AppliTrack adds its own markup to some titles ("<font color=red>(Internal Only)</font>")
        title = re.sub(r"\s+", " ", R.html_unescape(re.sub(r"<[^>]+>", " ", title))).strip()
        out.append((title, jid, _date(cells.get("posted on")), _date(cells.get("closes"))))
    return out

def _posting(base, jid):
    """One posting's own text as HTML, or None when it cannot be decoded (the same bytes would come back)."""
    try: html = _script(f"{base}/jobpostings/Output.asp?AppliTrackJobId={jid}")
    except _NotUtf8: return None
    R.need(f"id='p{jid}_'>" in html, "the posting is not in its own reply")
    text = re.split(r"'\);\s*function |<div class=\"addthis_toolbox|Email To A Friend", html.split(f"id='p{jid}_'>", 1)[1], maxsplit=1)[0]
    # Drop the title, the labelled fields (dates would read as numbers) and inline base64 images
    return re.sub(r"<table class='title'.*?</table>|<li><span class=['\"]label['\"]\s*>.*?</li>|<img[^>]*>", " ", text, flags=re.S)

def fetch(slug):
    """Return the open jobs of every Position Type that is not left out, as [(title, location, url, closes, degree, extra)]."""
    district, _, assumed = slug.partition("|")
    if not assumed.strip(): raise RuntimeError('a frontline slug is "district|location to assume"')
    base = f"https://www.applitrack.com/{district}/onlineapp"
    page = R.curl_text(f"{base}/default.aspx", accept="text/html")
    # The All Jobs link comes after the menu of Position Types, so a page that has it has the whole menu
    R.need('id="HrefAllJob"' in page, "not an AppliTrack board")
    types = re.findall(r'href="default\.aspx\?(Category=[^"]+)"[^>]*>([^<]+?)\s*\((\d+)\)</a>', page)
    if not types:
        # An empty menu is believed only when the list itself says there are no openings
        html = _script(_ALL % district)
        R.need("do not have any openings" in html and not _ROW.search(html), "no Position Types in the menu")
        return []
    rows = []
    for query, name, count in types:
        name = R.html_unescape(name)
        if (_CLASSROOM.search(name) or _OTHER_TYPE.search(name)) and not _KEEP.search(name): continue
        time.sleep(0.3)
        # all=cat: without it a type with many postings answers with a menu of its sub-types instead
        found = _rows(_script(f"{base}/jobpostings/Output.asp?{R.html_unescape(query)}&all=cat&AppliTrackLayoutMode=condensed"))
        R.need(len(found) >= int(count), f"read {len(found)} of {count} {name} postings")   # a short read must not look like closures
        for title, jid, posted, closes in found:
            if _AIDE.search(title) and not _KEEP.search(title): continue
            internal = bool(_INTERNAL.search(f"{title} {name}")) and not re.search(r"\bexternal\b", title, re.I)
            rows.append((title, assumed, f"{base}/default.aspx?AppliTrackJobId={jid}", closes, None,
                         {"posted": posted, "yrs": None, "internal": internal, "company": None}))
    rows = R._dedupe(rows)[:6000]
    # The list has no posting text. Read it for the rows worth showing; a failed read keeps the row as listed.
    kept = [i for i, r in enumerate(rows) if R.classify(r[0], r[1], KIND) or R.experienced(r[0], r[1], KIND)]
    unread = 0
    for i in kept[:60]:
        title, loc, url, closes, _, extra = rows[i]
        time.sleep(0.3)
        try: text = R.patient(_posting, base, url.rsplit("=", 1)[1], tries=2, slots=R._DETAIL_SLOTS)   # two tries keep a bad day under 150 requests
        except Exception: text = None
        if text is None: unread += 1; continue
        rows[i] = (title, loc, url, closes, R.degree_flag(text), dict(extra, yrs=R.min_years(text)))
    notes = [f"read details for the first 60 of {len(kept)} kept roles"] if len(kept) > 60 else []
    if unread: notes.append(f"could not read the posting text of {unread} of {min(len(kept), 60)} kept roles")
    if notes: R.PARTIAL[slug] = "; ".join(notes)
    return rows

# district -> the job ids on its public list (None when it could not be read), read once a run
_LISTED, _LISTED_LOCK = {}, threading.Lock()
def link_state(url):
    """'live', 'dead' or 'unknown' for one posting URL of this system. Return 'unknown' whenever unsure."""
    m = LINK.search(url)
    if not m: return "unknown"
    district, jid = m.group(1).lower(), m.group(2)
    # Asking for the one job proves nothing: its page and Output.asp?AppliTrackJobId= show a posting, Apply
    # button and all, months after it closed. A posting is open while the district's whole list carries it.
    with _LISTED_LOCK:   # links are checked several at a time; the list is read once, by one of them
        if district not in _LISTED:
            try:
                html = _script(_ALL % district)
                ids = {j for _, j, _ in _ROW.findall(html)}
                _LISTED[district] = ids if ids or "do not have any openings" in html else None
            except Exception: _LISTED[district] = None
        ids = _LISTED[district]
    if ids is None: return "unknown"
    return "live" if jid in ids else "dead"

if __name__ == "__main__":
    for name, slug in EMPLOYERS.items():
        rows = fetch(slug)
        kept = [r for r in rows if R.classify(r[0], r[1], KIND) or R.experienced(r[0], r[1], KIND)]
        print(f"{name}: {len(rows)} jobs, {sum(1 for r in rows if R.HOME.search(r[1] or ''))} in Utah, {len(kept)} kept")
        for r in kept[:5]: print("   ", r[0], "|", r[1], "|", r[2], "|", r[3], "|", r[5])
