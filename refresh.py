#!/usr/bin/env python3
"""
Job Finder weekly refresh.

    python3 refresh.py

Re-checks every company's job board, finds new entry-level roles, flags roles
that closed, and tests the links already on your dashboard. Writes a report to
refresh-report.txt and remembers this run in .refresh-state.json so the next
run can tell you what changed.

No installs needed - standard library, shells out to curl.
"""
import json, os, re, subprocess, sys, time, datetime, threading, concurrent.futures, urllib.parse, hashlib
from html import unescape as html_unescape

HERE  = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(HERE, "index.html")
STATE = os.path.join(HERE, ".refresh-state.json")
REPORT= os.path.join(HERE, "refresh-report.txt")
UA    = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"

# company -> where its jobs actually live. "manual" = no public API, check by hand.
BOARDS = {
  "greenhouse": {
    "MX Technologies":"mxtechnologiesinc", "Recursion Pharmaceuticals":"recursionpharmaceuticals",
    "Qualtrics":"qualtrics", "Sigma Computing":"sigmacomputing", "Lucid Software":"lucidsoftware",
    "Podium":"podium81", "BambooHR":"bamboohr17", "Nav Technologies":"navtechnologies",
    "Databricks":"databricks", "Stripe":"stripe", "Brex":"brex", "SoFi":"sofi",
    "Galileo Financial Technologies":"sofitechsolutions", "Anthropic":"anthropic",
    "Scale AI":"scaleai", "Robinhood":"robinhood", "DigiCert":"digicert", "Zscaler":"zscaler",
    "Okta":"okta", "Cloudflare":"cloudflare", "Wiz":"wizinc", "Tenable":"tenableinc",
    "Abnormal AI":"abnormalsecurity", "Huntress":"huntress", "Tanium":"tanium", "Cribl":"cribl",
    "Chainguard":"chainguard", "Axonius":"axonius", "Netskope":"netskope", "Expel":"expel",
    "Dragos":"dragos", "SecurityScorecard":"securityscorecard", "Coalition":"coalition",
    "Recorded Future":"recordedfuture", "Datadog":"datadog", "KnowBe4":"knowbe4",
    "Orca Security":"orcasecurity", "Torq":"torq", "Weave":"weave", "Verkada":"verkada",
    "iCapital":"icapitalnetwork", "Addepar":"addepar1",
    "Ivanti":"a3c41b8b71eff8c4",          # the board token is a hash; every name-like slug 404s
  },
  "lever":  {"Ataccama":"ataccama", "Filevine":"filevine", "Pattern":"pattern", "Entrata":"entrata"},
  "ashby":  {"Snowflake":"snowflake", "Plaid":"plaid", "Instructure (Canvas)":"instructure",
             "OpenAI":"openai", "Ramp":"ramp", "Perplexity AI":"perplexity", "Sardine":"sardine",
             "Vanta":"vanta", "Drata":"drata", "1Password":"1password", "Material Security":"materialsecurity",
             "Lumos":"lumos",
             "Weave (Ashby)":"weave"},   # Weave posts on both Greenhouse and Ashby; most roles are on Ashby
  "workable":{"Hugging Face":"huggingface"},
  "workday": {
    "Pluralsight":"pluralsight|wd1|Careers", "Proofpoint":"proofpoint|wd5|ProofpointCareers",
    "CrowdStrike":"crowdstrike|wd5|crowdstrikecareers", "Arctic Wolf":"arcticwolf|wd1|External",
    "Palo Alto Networks":"paloaltonetworks|wd5|panwexternalcareers",
    "Health Catalyst":"healthcatalyst|wd5|healthcatalystcareers", "Domo":"domo|wd12|DomoCareers",
    "Optiv":"optiv|wd5|Optiv_Careers", "SailPoint":"sailpoint|wd1|SailPoint",
    "WGU (Western Governors University)":"wgu|wd5|External",
    "Mastercard":"mastercard|wd1|Campus",                      # every Launch Program req lives on the Campus site
    "Mastercard (Salt Lake City)":"mastercard|wd1|CorporateCareers|Salt Lake City",
    # about 1,800 reqs, so search instead of paging: the campus programs are nowhere near the first pages
    "Capital One":"capitalone|wd12|Capital_One|2027;New Grad",
    "Adobe (Lehi Campus)":"adobe|wd5|external_experienced|Lehi;University Graduate",
    "Ancestry":"ancestry|wd501|Careers",
    # National new-grad programs, for a candidate willing to move. Small boards are read whole;
    # the large ones are searched for the words their campus reqs always carry.
    "Freddie Mac":"freddiemac|wd5|External",
    "Fannie Mae":"fanniemae|wd1|FannieMaeCareers",
    "USAA":"usaa|wd1|USAAJOBSWD",
    "Vanguard":"vanguard|wd5|vanguard_external",
    "Visa":"visa|wd5|Visa|New College Graduate;2027;University",
    "FIS":"fis|wd5|SearchJobs|University Program",
    "Citi":"citi|wd5|2|2027;Analyst Program",
    "Wells Fargo":"wf|wd1.myworkdaysite.com|WellsFargoJobs|2027;Development Program",
    "Fidelity Investments":"fmr|wd1.myworkdaysite.com|targeted",          # the campus site
    "Fidelity Investments (Salt Lake City)":"fmr|wd1|FidelityCareers|Salt Lake City",
    "PwC":"pwc|wd3|US_Entry_Level_Careers",                               # an entry-level-only site
    "Protiviti":"roberthalf|wd1|ProtivitiGraduate",
    "Accenture":"accenture|wd103|AccentureCareers|NAELFY27",               # North America entry level, FY27
  },
  # keyword@locationFacet pairs. 300000000289738 = United States, 300000020657212 = Utah
  "oracle_hcm": {"JPMorgan Chase":"jpmc.fa.oraclecloud.com|CX_1001|2027@300000000289738;@300000020657212",
                 # no facet: the location rules drop the London and Sussex programs
                 "American Express":"egug.fa.us2.oraclecloud.com|CX_1|2027@;Campus@"},
  "goldman":    {"Goldman Sachs (SLC Campus)":""},
  # host|location to assume, because an iCIMS sitemap lists titles and links but no locations
  "icims":      {"Cotiviti":"careers-cotiviti.icims.com|US remote or South Jordan, UT (check posting)",
                 "America First Credit Union":"careers-americafirst.icims.com|Northern Utah (check posting)"},
  "successfactors": {"Vivint Smart Home":"careers.nrgenergy.com|SMARTHOMES"},
  "jazzhr":     {"Cicero Group (MGT)":"cicero"},
  "selectminds":{"Zions Bancorporation":"growwithzions.zionsbancorp.com"},
  "eightfold":  {"Morgan Stanley":"morganstanley.eightfold.ai|morganstanley.com|@Utah, United States;2027@United States"},
  "oleeo":      {"Morgan Stanley (campus programs)":"https://morganstanley.tal.net/vx/lang-en-GB/mobile-0/brand-2/candidate/jobboard/vacancy/1/adv/?f_Item_Opportunity_17058_lk=133175"},
  "bamboohr":{"SecurityMetrics":"securitymetrics"},
  "avature":{"Bloomberg":"bloomberg.avature.net/careers"},
}
# no public API - the report just reminds you to look
# Deloitte's Avature search is rendered in the browser and its RSS feed ignores the search, KPMG's
# and EY's career sites have no public feed at all.
MANUAL = {
  "Deloitte":"https://apply.deloitte.com/en_US/careers/SearchJobs/?search=2027",
  "EY":"https://careers.ey.com/ey/search/?q=staff&locationsearch=united+states",
  "KPMG":"https://www.kpmguscareers.com/early-career/",
}

# ---------- who this search is for (edit this block to retarget the script) ----------
HOME_NAME = "Utah"
# Only place names that are unambiguous on their own. Towns that share a name with places elsewhere
# (Sandy, Riverdale, Murray, Layton, Farmington, Pleasant Grove) are left out on purpose: feeds that
# use them also say "UT" or "Utah", and that is what matches.
HOME    = re.compile(r"\b(?:UT|Utah)\b|salt lake|\blehi\b|\bprovo\b|\borem\b|south jordan|american fork|\blindon\b", re.I)
UTAH    = HOME   # older name, kept so nothing that imports this breaks
# A December graduate cannot use a summer internship, so those are dropped. Flip this if you want them.
DROP_INTERNSHIPS = True

# ---------- what counts as a role worth telling you about ----------
SENIOR  = re.compile(r"\b(senior|sr\.?|principal|lead|manager|director|head|vp|vice president|chief|"
                     r"architect|counsel|attorney|leader|snr\.?|account executive|customer success|"
                     r"ii|iii|iv|distinguished|avp|svp|evp|executive|intermediate|intmd)\b", re.I)
# A numbered level above one ("Programmer Analyst 2") is not entry-level, unless the title also says it
# is for new graduates ("Software Engineer 2 - New College Grad"). "Analyst 2027" is unaffected, and so
# is a duration or a date: "Analyst 2-Year Rotational Program", "Consultant 3/1/2027 Start".
LEVEL_N = re.compile(r"\b(?:analyst|engineer|developer|programmer|specialist|associate|consultant|auditor)\s+[2-5]"
                     r"(?![-\s./]*(?:\d|yrs?\b|years?\b|months?\b|weeks?\b|days?\b))\b", re.I)
NEW_GRAD = re.compile(r"new[ -]?grad|new college grad|university grad|recent grad|early[- ]career|\bcampus\b", re.I)
# The entry rung of product and program management carries the word "manager" ("Associate Product
# Manager", "APM"), so it is taken out before the seniority test.
ENTRY_MANAGER = re.compile(r"\b(?:associate|junior|jr\.?)\s+(?:product|program|project)\s+manager\b|\bAPM\b", re.I)
# "Staff" means senior in engineering and is the FIRST rung in audit and accounting
# ("Staff Auditor", "IT Audit Staff", "Staff Consultant, Technology Risk").
STAFF     = re.compile(r"\bstaff\b", re.I)
AUDITLIKE = re.compile(r"audit|accountant|accounting|assurance|advisory|consult", re.I)
# Titles for a different cohort. A season plus a year is deliberately NOT here: "New Grad (Spring 2027
# Start)" and "Winter 2027 Cohort" are full-time start dates, exactly what a December graduate needs.
WRONG_COHORT = re.compile(r"\b(interns?|internship|c[o0]-?op|summer (?:analyst|associate)|seasonal|off-?cycle|"
                          r"sophomore|freshman|apprentice(?:ship)?|ph\.?d|postdoc(?:toral)?|fellow(?:ship)?|"
                          r"mba|master'?s|return to work|returnship|insight (?:day|program)|early insights?)\b", re.I)
# Strongest signal: the employer built the role for new graduates. Worth relocating for.
# A bare "program" is not enough ("Program Mentor", "Program Development Owner").
PROGRAM = re.compile(r"(new[ -]?grad|new college grad|\bgraduate\b|early[- ]career|early in career|"
                     r"\buniversity\b|\bcampus\b|rotational|class of|\b20(?:26|27)\b|"
                     r"\b(?:development|leadership|leaders|rotation|analyst|associate|launch|graduate|technology|"
                     r"banker|foundational|trainee|academy)\s+program\b)", re.I)
# Ordinary entry-level wording.
ENTRYWORD = re.compile(r"(entry[- ]level|junior|\bjr\.?\b|\bassociate\b|\banalyst\b|\blevel (?:i|1)\b|"
                       r"\b(?:engineer|developer|scientist|specialist|auditor|accountant|consultant|"
                       r"administrator|technician)[, ]+(?:i|1)\b|\bi\b$|\(i\))", re.I)
ENTRY   = re.compile(PROGRAM.pattern + "|" + ENTRYWORD.pattern, re.I)   # either kind
# A title with no level word at all is kept only near home, where there are few enough roles to
# read each one. Everywhere else the explicit signal is required, which keeps the report readable.
ONTOPIC = re.compile(r"\b(data|analytics?|ai|ml|machine learning|software|developer|engineer|product|"
                     r"risk|fraud|compliance|audit|auditor|security|cyber|business intelligence|"
                     r"operations|technology|onboarding|implementation|solutions|systems|automation|"
                     r"governance|quality|reporting|insights?)\b", re.I)
# Titles that match the above but are not the kind of work wanted. ("EDR" is deliberately absent:
# in security it means Endpoint Detection and Response.)
OFFTOPIC= re.compile(r"\b(sales|business development|development representative|bdr|sdr|"
                     r"account executive|account manager|partnerships?|marketing|investor relations|"
                     r"recruit\w*|talent|skillbridge|hackathon|general interest|"
                     r"clinical|nurse|physician|therapist|dental|teacher|instructor|faculty|"
                     r"real estate|collections|underwrit\w*|payroll|tax|legal|counsel|"
                     r"communications|public relations|brand|content|social media|"
                     r"customer success|deal desk|commissions?|total rewards|procurement|sourcing|facilities|"
                     r"data center|electrical|mechanical|hardware|warehouse|driver|"
                     r"teller|part[- ]time|\d+\s*hours?|hourly|banker(?!\s+development)|"
                     r"financial advis[eo]rs?|financial services representative|financial customer associate|"
                     r"wealth banking(?!\s+technology)|fiduciary\s+(?:trust|officer|specialist|administrator|associate|accountant)|"
                     r"adjuster|administrative\s+(?:assistant|associate|coordinator|support|specialist|business partner))\b", re.I)
REMOTE  = re.compile(r"\bremote\b|anywhere|distributed", re.I)
# Written by the Workday reader when a requisition's own country code is not the US. It is checked
# before everything else, because "Chennai, TN" would otherwise read as Tennessee.
ABROAD  = re.compile(r"\([^()]*,\s*abroad\)")
_STATES = ("AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|"
           "NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC")
# Evidence that a location is in the US. It wins over NONUS, so "Vienna, VA", "Melbourne, FL" and
# "Vancouver, WA" stay American. Case-sensitive on purpose: ", IN" is Indiana, ", in" is not.
US_HINT = re.compile(r"\b(?:United States|USA|U\.S\.A?\.?|US)\b|,\s*(?:" + _STATES + r")\b|\bUS-(?:" + _STATES + r")\b")
NONUS   = re.compile(r"\b(?:london|dublin|india|bangalore|bengaluru|hyderabad|pune|toronto|canada|"
                     r"singapore|tokyo|japan|sydney|australia|berlin|munich|germany|paris|france|"
                     r"amsterdam|netherlands|prague|czech|slovak|bulgaria|mexico|brazil|poland|warsaw|"
                     r"krakow|united kingdom|ireland|israel|tel aviv|switzerland|spain|italy|sweden|"
                     r"denmark|norway|finland|portugal|belgium|dubai|philippines|manila|vietnam|"
                     r"thailand|malaysia|indonesia|korea|seoul|china|beijing|shanghai|hong kong|"
                     r"taiwan|new zealand|argentina|colombia|chile|costa rica|nigeria|kenya|"
                     r"south africa|egypt|turkey|greece|romania|hungary|budapest|austria|serbia|"
                     r"belgrade|ukraine|emea|apac|latam|barcelona|madrid|bucharest|doha|qatar|riyadh|"
                     r"saudi|abu dhabi|lisbon|zurich|geneva|stockholm|copenhagen|oslo|helsinki|vienna|"
                     r"athens|istanbul|cairo|lagos|nairobi|johannesburg|cape town|sao paulo|são paulo|"
                     r"bogot[aá]|santiago|lima|buenos aires|guadalajara|monterrey|vancouver|montreal|"
                     r"ottawa|waterloo|calgary|melbourne|auckland|jakarta|kuala lumpur|bangkok|hanoi|"
                     r"ho chi minh|taipei|osaka|gurgaon|gurugram|noida|chennai|mumbai|delhi|kolkata|"
                     r"haifa|milan|rome|brussels|luxembourg|edinburgh|manchester|cork|belfast|uk|eu|abroad)\b", re.I)
# The version is derived from every rule above, so editing HOME or DROP_INTERNSHIPS re-baselines the
# next run automatically instead of reporting every no-longer-matching role as closed.
FILTER_VERSION = hashlib.sha1("\x1f".join([
    HOME.pattern, SENIOR.pattern, LEVEL_N.pattern, NEW_GRAD.pattern, ENTRY_MANAGER.pattern, STAFF.pattern, AUDITLIKE.pattern, WRONG_COHORT.pattern, PROGRAM.pattern,
    ENTRYWORD.pattern, ONTOPIC.pattern, OFFTOPIC.pattern, REMOTE.pattern, ABROAD.pattern, US_HINT.pattern, NONUS.pattern,
    str(DROP_INTERNSHIPS)]).encode()).hexdigest()[:12]

def _parts(loc):
    return [p.strip() for p in re.split(r"[;|]", loc or "") if p.strip()] or [""]

def where(loc):
    """home, remote or elsewhere for the most reachable location listed; None if every one is abroad.
    Multi-location strings are judged part by part, so "New York; Paris" is still a US job."""
    rank, best = {"home": 0, "remote": 1, "elsewhere": 2}, None
    for part in _parts(loc):
        if ABROAD.search(part): continue
        if HOME.search(part): g = "home"
        elif NONUS.search(part) and not US_HINT.search(part): continue
        elif REMOTE.search(part): g = "remote"
        else: g = "elsewhere"
        if best is None or rank[g] < rank[best]: best = g
    return best

def classify(title, loc):
    """Return {"signal", "geo"} for a role worth reporting, or None.

    signal is "program" (built for new graduates), "entry" (entry-level wording) or
    "unleveled" (no level word, kept only near home). geo is home, remote or elsewhere.
    """
    ok, _ = _classify(title, loc)
    return ok

def _classify(title, loc):
    if not title: return None, "no title"
    plain = ENTRY_MANAGER.sub(" associate ", title)   # "Associate Program Manager" is a job, not a program
    m = SENIOR.search(plain)
    if m: return None, f"seniority word '{m.group(0)}'"
    m = LEVEL_N.search(plain)
    if m and not NEW_GRAD.search(plain): return None, f"level above one '{m.group(0)}'"
    auditish = bool(STAFF.search(title) and AUDITLIKE.search(title))
    if STAFF.search(title) and not auditish: return None, "seniority word 'Staff'"
    if DROP_INTERNSHIPS:
        m = WRONG_COHORT.search(title)
        if m: return None, f"wrong cohort '{m.group(0)}'"
    m = OFFTOPIC.search(title)
    if m: return None, f"off-topic word '{m.group(0)}'"
    geo = where(loc)
    if geo is None: return None, "outside the US"
    if PROGRAM.search(plain):   return {"signal": "program", "geo": geo}, ""
    if ENTRYWORD.search(title) or auditish: return {"signal": "entry", "geo": geo}, ""
    if geo == "home" and ONTOPIC.search(title): return {"signal": "unleveled", "geo": geo}, ""
    return None, ("no entry-level wording" + ("" if geo == "home" else f" (and not in {HOME_NAME}, where unleveled titles are kept)"))

def interesting(title, loc):
    return classify(title, loc) is not None

# ---------- fetching ----------
def curl_resp(url, post=None, timeout=30, accept="application/json"):
    """(http status, body). Status is "000" when curl could not connect or timed out."""
    cmd = ["curl","-sS","-L","--max-time",str(timeout),"-A",UA,"-H",f"Accept: {accept}","-w","\n@@HTTP@@%{http_code}"]
    if post is not None:
        cmd += ["-H","Content-Type: application/json","-X","POST","--data",json.dumps(post)]
    out = subprocess.run(cmd+[url], capture_output=True, text=True).stdout
    body, sep, code = out.rpartition("\n@@HTTP@@")
    return (code.strip() or "000", body) if sep else ("000", out)

def curl_text(url, post=None, timeout=30, accept="application/json"):
    """The body of a successful reply. Anything else raises, because a timeout or an error page must
    never be read as "this board has no jobs": that would report every role on it as closed."""
    code, body = curl_resp(url, post, timeout, accept)
    host = urllib.parse.urlsplit(url).netloc
    if not code.startswith("2"): raise RuntimeError(f"HTTP {code} from {host}")
    if not body.strip(): raise RuntimeError(f"empty reply from {host}")
    return body

def curl(url, post=None, timeout=30):
    return json.loads(curl_text(url, post, timeout))

# Per-job detail reads, across every board at once. Workday throttles a host (HTTP 429) long before
# it would notice the list requests, so these are kept few and retried.
_DETAIL_SLOTS = threading.BoundedSemaphore(6)
def patient(fn, *args, tries=3, slots=None):
    """Call fn, retrying with a growing pause (for throttled career sites)."""
    for i in range(tries):
        try:
            if slots is None: return fn(*args)
            with slots: return fn(*args)
        except Exception:
            if i == tries - 1: raise
            time.sleep(2 * (i + 1))

# Boards read successfully but not completely, keyed by slug, for the report.
PARTIAL = {}

def need(ok, what):
    """Fail loudly when a reply parses but is not the shape a job list has."""
    if not ok: raise RuntimeError(f"unexpected reply ({what})")

def _dedupe(rows):
    seen, out = set(), []
    for r in rows:
        if r[2] in seen: continue
        seen.add(r[2]); out.append(r)
    return out

def fetch(kind, slug):
    """Return [(title, location, url)] for one company."""
    if kind == "greenhouse":
        d = curl(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")
        need(isinstance(d.get("jobs"), list), "no jobs list")
        return [(j["title"], (j.get("location") or {}).get("name",""), j["absolute_url"])
                for j in d.get("jobs", [])]
    if kind == "lever":
        d = curl(f"https://api.lever.co/v0/postings/{slug}?mode=json")
        need(isinstance(d, list), "not a list")
        return [(j["text"], (j.get("categories") or {}).get("location",""), j["hostedUrl"]) for j in d]
    if kind == "ashby":
        d = curl(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
        need(isinstance(d.get("jobs"), list), "no jobs list")
        return [(j["title"], j.get("location",""), j.get("jobUrl","")) for j in d["jobs"]]
    if kind == "workable":
        # One row per location, so a remote job repeats once per listed city: fold those together.
        # The state and the telecommuting flag matter: without them a remote role that also lists
        # Salt Lake City reads as just "United States".
        d = curl(f"https://apply.workable.com/api/v1/widget/accounts/{slug}")
        need(isinstance(d.get("jobs"), list), "no jobs list")
        by = {}
        for j in d.get("jobs", []):
            place = ", ".join(filter(None, [j.get("city"), j.get("state"), j.get("country")]))
            e = by.setdefault(j.get("shortcode") or j.get("url"), [j["title"], [], j.get("url","")])
            if place and place not in e[1]: e[1].append(place)
            if j.get("telecommuting") and "Remote" not in e[1]: e[1].insert(0, "Remote")
        return [(t, "; ".join(locs), u) for t, locs, u in by.values()]
    if kind == "bamboohr":
        d = curl(f"https://{slug}.bamboohr.com/careers/list")
        res = d.get("result", d)
        jobs = res if isinstance(res, list) else res.get("jobs", [])
        out = []
        for j in jobs:
            l = j.get("location") or {}
            city = l.get("city","") if isinstance(l, dict) else str(l)
            out.append((j.get("jobOpeningName",""), city,
                        f"https://{slug}.bamboohr.com/careers/{j.get('id','')}"))
        return out
    if kind == "workday":
        # "tenant|wdN|site" or "tenant|wdN|site|search one;search two". A tenant with thousands of
        # requisitions (Capital One has about 1,800) is searched by keyword instead of paged, because
        # its campus programs sit far past any sane page limit. Some employers use the shared
        # myworkdaysite.com host instead of their own subdomain: give that host in place of wdN
        # ("fmr|wd1.myworkdaysite.com|targeted").
        parts = slug.split("|")
        tenant, wd, site = parts[:3]
        searches = parts[3].split(";") if len(parts) > 3 else [""]
        if "." in wd:
            base, page_base = f"https://{wd}", f"https://{wd}/en-US/recruiting/{tenant}/{site}"
        else:
            base = f"https://{tenant}.{wd}.myworkdayjobs.com"
            page_base = f"{base}/en-US/{site}"
        api = f"{base}/wday/cxs/{tenant}/{site}"
        out, paths = [], {}
        for text in searches:
            off, total = 0, None
            while off < 600:
                d = patient(curl, f"{api}/jobs", {"appliedFacets":{},"limit":20,"offset":off,"searchText":text})
                need(isinstance(d.get("jobPostings"), list), "no jobPostings")
                posts = d["jobPostings"]
                # Some tenants report "total" on the first page only and 0 afterwards, so remember it.
                if total is None: total = d.get("total", 0)
                for j in posts:
                    url = page_base + j.get("externalPath","")
                    paths[url] = j.get("externalPath","")
                    out.append((j.get("title",""), j.get("locationsText",""), url))
                off += 20
                if len(posts) < 20 or off >= total: break
        out = _dedupe(out)
        # The list says "3 Locations" for a multi-city job, which hides a Salt Lake City seat, and it
        # never gives the closing date. Each job's own record has both, so it is read for every row
        # that passes the filters as listed, and for every multi-city row that could pass them at home
        # (the most permissive test). A failed read keeps the row as listed rather than dropping it.
        hidden = re.compile(r"^\s*(?:\d+ Locations?)?\s*$", re.I)
        failed = []
        def detail(row):
            title, loc, url = row
            try:
                info = patient(curl, api + paths[url], slots=_DETAIL_SLOTS).get("jobPostingInfo") or {}
            except Exception:
                if hidden.match(loc or ""): failed.append(title)
                return row
            # Some tenants name a building, not a city ("TAURUS" is in Frankfurt), so trust the
            # requisition's country code and mark a foreign one in words the location rules read.
            # US territories are not abroad. Extra cities are marked too unless they name a US state.
            country = (info.get("jobRequisitionLocation") or {}).get("country") or info.get("country") or {}
            code = country.get("alpha2Code", "US")
            mark = "" if code in ("US", "PR", "GU", "VI", "AS", "MP") else f" ({country.get('descriptor') or code}, abroad)"
            first = (info.get("location") or "") + (mark if info.get("location") else "")
            extra = [c if (not mark or HOME.search(c) or US_HINT.search(c)) else c + mark
                     for c in info.get("additionalLocations") or [] if c]
            cities = [c for c in [first] + extra if c]
            return (title, "; ".join(cities) or loc, url, (info.get("endDate") or "")[:10] or None)
        wanted = lambda r: classify(r[0], r[1]) or (hidden.match(r[1] or "") and classify(r[0], HOME_NAME))
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            rows = list(ex.map(lambda r: detail(r) if wanted(r) else r, out))
        # Without its record, a "2 Locations" row cannot be placed, and guessing would make it look
        # closed one week and new the next. Treat the board as unread today instead.
        if failed:
            raise RuntimeError(f"{len(failed)} job record(s) could not be read (throttled?), e.g. '{failed[0][:40]}'")
        return rows
    if kind == "oracle_hcm":
        # "host|site|keyword@locationFacet;keyword@locationFacet". Campus programs put one city in
        # PrimaryLocation and the rest in secondaryLocations, so both are read.
        host, site, queries = slug.split("|")
        out = []
        for q in queries.split(";"):
            kw, _, facet = q.partition("@")
            offset, total = 0, None
            while offset < 2000:
                finder = f"findReqs;siteNumber={site}" + (f",keyword=%22{kw}%22" if kw else "") + \
                         (f",selectedLocationsFacet={facet}" if facet else "") + f",limit=200,offset={offset},sortBy=POSTING_DATES_DESC"
                d = curl(f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
                         f"?onlyData=true&expand=requisitionList.secondaryLocations&finder={finder}", timeout=60)
                need(isinstance(d.get("items"), list) and d["items"], "no items")
                page = d["items"][0].get("requisitionList") or []
                if total is None: total = int(d["items"][0].get("TotalJobsCount") or 0)
                for j in page:
                    locs = [j.get("PrimaryLocation","")] + [x.get("Name","") for x in j.get("secondaryLocations") or []]
                    out.append((j.get("Title",""), "; ".join(filter(None, locs)),
                                f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{j.get('Id')}"))
                offset += 200
                if not page or offset >= total: break
        out = _dedupe(out)
        # The list has no closing date; each requisition's own record does, as a UTC timestamp
        # ("2026-10-31T03:55Z" is the evening of Oct 30 in the US), so convert it to a local date.
        def detail(row):
            try:
                d = patient(curl, f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails?onlyData=true"
                                  f"&finder=ById;Id=%22{row[2].rsplit('/', 1)[-1]}%22,siteNumber={site}", slots=_DETAIL_SLOTS)
                end = ((d.get("items") or [{}])[0].get("ExternalPostedEndDate") or "").replace("Z", "+00:00")
                return row + (datetime.datetime.fromisoformat(end).astimezone().date().isoformat() if end else None,)
            except Exception:
                return row
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            return list(ex.map(lambda r: detail(r) if classify(r[0], HOME_NAME) else r, out))
    if kind == "goldman":
        # higher.gs.com is a GraphQL front end. Two passes: US campus programs, then every
        # early-career and professional role in Utah (Goldman files Utah under both "UT" and "Utah").
        def ask(op, experiences, loc_filters, extra=""):
            rows, page = [], 0
            while page < 5:
                body = {"operationName": op, "variables": {"searchQueryInput": {
                            "page": {"pageSize": 100, "pageNumber": page},
                            "sort": {"sortStrategy": "POSTED_DATE", "sortOrder": "DESC"},
                            "filters": [{"filterCategoryType": "LOCATION", "filters": loc_filters}],
                            "experiences": experiences, "searchTerm": ""}},
                        "query": "query %s($searchQueryInput: RoleSearchQueryInput!) { roleSearch(searchQueryInput: $searchQueryInput) "
                                 "{ totalCount items { roleId corporateTitle jobTitle status locations { primary city state country } "
                                 "externalSource { sourceId } } } }" % op}
                reply = curl("https://api-higher.gs.com/gateway/api/v1/graphql", body)
                need(not reply.get("errors") and isinstance(((reply.get("data") or {}).get("roleSearch") or {}).get("items"), list),
                     "GraphQL error")
                items = reply["data"]["roleSearch"]["items"]
                for j in items:
                    if j.get("status") != "POSTED": continue
                    locs = [", ".join(filter(None, [l.get("city"), l.get("state")])) for l in j.get("locations") or []]
                    title = j.get("jobTitle","")
                    if j.get("corporateTitle") and j["corporateTitle"].lower().startswith(("summer", "seasonal")):
                        title += " (Summer Internship)"   # so the cohort rule drops it
                    rows.append((title, "; ".join(locs), "https://higher.gs.com/roles/" + str((j.get("externalSource") or {}).get("sourceId",""))))
                if len(items) < 100: break
                page += 1
            return rows
        us   = [{"filter": "United States", "subFilters": []}]
        utah = [{"filter": "United States", "subFilters": [{"filter": "UT", "subFilters": []}, {"filter": "Utah", "subFilters": []}]}]
        return _dedupe(ask("GetCampusRoles", ["CAMPUS"], us) + ask("GetRoles", ["EARLY_CAREER", "PROFESSIONAL"], utah))
    if kind == "icims":
        # "host|assumed location". iCIMS has no JSON list, but its sitemap is complete. The sitemap
        # carries no location, so the one given here is applied to every row (and said so).
        host, _, assumed = slug.partition("|")
        xml = curl_text(f"https://{host}/sitemap.xml", accept="text/xml")
        need("<urlset" in xml, "not a sitemap")
        out = []
        for url, jid, sl in re.findall(r"<loc>(https://%s/jobs/(\d+)/([^/<]+)/job)</loc>" % re.escape(host), xml):
            title = re.sub(r"\s+", " ", urllib.parse.unquote(sl).replace("-", " ")).strip().title()
            out.append((title, assumed, url))
        return out
    if kind == "successfactors":
        # "host|brand". The "sitemap.xml" of a SuccessFactors career site is really a Google-Base RSS
        # feed, and it covers every brand on the site: NRG's lists power-trading jobs in Houston
        # alongside Vivint's. Keep the brand's own postings plus anything located in Utah.
        host, _, brand = slug.partition("|")
        xml = curl_text(f"https://{host}/sitemap.xml", accept="text/xml", timeout=90)
        need("<channel" in xml, "not an RSS feed")
        out = []
        for item in re.findall(r"<item>(.*?)</item>", xml, re.S):
            t = re.search(r"<title>(.*?)</title>", item, re.S)
            l = re.search(r"<g:location>(.*?)</g:location>", item, re.S)
            u = re.search(r"<link>(.*?)</link>", item, re.S)
            if not (t and u): continue
            title = re.sub(r"\s*\([^()]*\)\s*$", "", html_unescape(t.group(1))).strip()
            place, link = (html_unescape(l.group(1)) if l else ""), u.group(1).strip()
            if brand and f"/{brand}/" not in link and not HOME.search(place): continue
            out.append((title, place, link))
        return out
    if kind == "jazzhr":
        xml = curl_text(f"https://app.jazz.co/feeds/export/jobs/{slug}", accept="text/xml")
        need("<jobs" in xml, "not a JazzHR feed")
        out = []
        for job in re.findall(r"<job>(.*?)</job>", xml, re.S):
            g = lambda tag: html_unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", (re.search(rf"<{tag}>(.*?)</{tag}>", job, re.S) or [None, ""])[1])).strip()
            if g("status") and g("status").lower() != "open": continue
            out.append((g("title"), g("city"), g("url").replace("http://", "https://")))
        return out
    if kind == "selectminds":
        # Oracle Taleo behind SelectMinds: no feed of any kind, only server-rendered pages of ten.
        # The first request redirects to a per-request search id, which the page URLs then need.
        first = subprocess.run(["curl","-sS","-L","--max-time","30","-A",UA,"-o","/dev/null","-w","%{url_effective}",
                                f"https://{slug}/jobs/search/"], capture_output=True, text=True).stdout
        sid = (re.search(r"(\d+)/?$", first) or [None, ""])[1]
        if not sid: raise ValueError("no search id")
        def page(n):
            return curl_text(f"https://{slug}/jobs/search/{sid}/page{n}", accept="text/html")
        one = page(1)
        m = re.search(r'class="total_results">(\d+)<', one)
        need(m, "no result count")
        total = int(m.group(1))
        pages = [one]
        if total > 10:
            with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
                pages += list(ex.map(page, range(2, min(60, (total + 9) // 10) + 1)))
        out = []
        for body in pages:
            for block in re.split(r'<div id="job_list_\d+"', body)[1:]:
                a = re.search(r'<a href="([^"]+)" class="job_link font_bold">([^<]+)</a>', block)
                l = re.search(r'<span class="location">(.*?)</span>', block, re.S)
                if not a: continue
                jid = (re.search(r"(\d+)/?$", a.group(1)) or [None, ""])[1]
                loc = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", l.group(1))).strip() if l else ""
                out.append((html_unescape(a.group(2)).strip(), loc, f"https://careers.zionsbancorp.com/jobs/x-{jid}"))
        return _dedupe(out)
    if kind == "eightfold":
        # "host|domain|query@location;query@location". Ten rows a page and no way to ask for more,
        # so it is queried narrowly rather than walked end to end.
        host, domain, queries = slug.split("|")
        out = []
        for q in queries.split(";"):
            text, _, place = q.partition("@")
            start, count = 0, None
            while start < 200:
                reply = curl(f"https://{host}/api/pcsx/search?domain={domain}&query={urllib.parse.quote(text)}"
                             f"&location={urllib.parse.quote(place)}&start={start}&sort_by=timestamp")
                need(isinstance(reply.get("data"), dict), "no data")
                d = reply["data"]
                rows = d.get("positions") or []
                if count is None: count = d.get("count", 0)
                for j in rows:
                    out.append((j.get("name",""), "; ".join(j.get("standardizedLocations") or j.get("locations") or []),
                                f"https://{host}" + j.get("positionUrl","")))
                start += 10
                if len(rows) < 10 or start >= count: break
        return _dedupe(out)
    if kind == "oleeo":
        # tal.net campus board: HTML only, fifty rows a page. slug is the full listing URL without &start=.
        out, start = [], 0
        while start < 300:
            body = curl_text(f"{slug}&start={start}", accept="text/html")
            # Oleeo sometimes answers scripts with a CAPTCHA page. Never try to get past it: report it,
            # so an unreadable board is not mistaken for one whose jobs have all closed.
            if re.search(r"Quick Check Needed|oleeoProtect|altcha", body, re.I):
                raise RuntimeError("bot check (CAPTCHA) shown, so check this board by hand")
            rows = re.findall(r'data-title="([^"]+)".*?<a class="subject" href="([^"]+)".*?<td class="comm_list_tbody">\s*(.*?)\s*</td>', body, re.S)
            need(rows or start > 0, "no rows on the first page (layout changed?)")
            for title, href, city in rows:
                out.append((html_unescape(title), re.sub(r"<[^>]+>", "", html_unescape(city)).strip(),
                            re.sub(r"/xf-[0-9a-f]+/", "/", href)))
            if len(rows) < 50: break
            start += 50
        return _dedupe(out)
    if kind == "avature":
        # "host/portal". Avature has no JSON API and its RSS feed carries no locations, but the
        # search page is server-rendered: twelve results a page, with title, city and link.
        base = f"https://{slug}/SearchJobs/?jobRecordsPerPage=12&jobOffset="
        first = curl_text(base + "0", accept="text/html")
        m = re.search(r"(\d[\d,]*)\s+results", first)
        need(m, "no result count")
        total = int(m.group(1).replace(",", ""))
        pages = [first]
        if total > 12:
            with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
                pages += list(ex.map(lambda o: curl_text(base + str(o), accept="text/html"), range(12, min(total, 1200), 12)))
        out = []
        for body in pages:
            for art in re.findall(r'<article class="article article--result".*?</article>', body, re.S):
                a = re.search(r'<a class="link" href="([^"]+/JobDetail/[^"]+)">\s*(.*?)\s*</a>', art, re.S)
                l = re.search(r'list-item-location">(.*?)</span>', art, re.S)
                if a: out.append((html_unescape(a.group(2)).strip(), html_unescape(l.group(1)).strip() if l else "", a.group(1)))
        need(out, "no jobs on the search pages (layout changed?)")
        out = _dedupe(out)
        # The search sorts ties unstably, so paging returns some jobs twice and skips others.
        # Say so in the report rather than implying the board was read in full.
        if len(out) < total:
            PARTIAL[slug] = f"{len(out)} of {total} jobs read (the site's paging skips some)"
        return out
    return []

def scan(item):
    kind, company, slug = item
    try:
        rows = fetch(kind, slug)
    except Exception as e:
        msg = str(e).strip()
        return company, None, None, (msg if isinstance(e, RuntimeError) and msg else f"{type(e).__name__}")[:120]
    hits = []
    for r in rows:
        t, l, u = r[:3]
        c = classify(t, l)
        if c: hits.append({"title": t.strip(), "loc": (l or "").strip(), "url": u,
                           "closes": r[3] if len(r) > 3 else None, **c})
    raw = [((r[0] or "").strip(), (r[1] or "").strip(), r[2]) for r in rows]
    return company, hits, raw, None

# ---------- is a link on the board still a live posting? ----------
# A 200 proves nothing: career sites are single-page apps that return a shell for dead job ids.
# So wherever the link belongs to a system that can be asked directly, ask it. Each branch
# returns "live", "dead" or "unknown"; only "dead" is ever reported, so a site that blocks
# scripts (lucid.co, openai.com, linkedin.com) can never be flagged by mistake.
GH_LINK     = re.compile(r"greenhouse\.io/(?:embed/job_app\?for=)?([^/?&]+)/jobs/(\d+)")
LEVER_LINK  = re.compile(r"jobs\.lever\.co/([^/]+)/([0-9a-f-]{36})")
ASHBY_LINK  = re.compile(r"jobs\.ashbyhq\.com/([^/]+)/([0-9a-f-]{36})")
WD_LINK     = re.compile(r"https://([^.]+)\.(wd\d+)\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?([^/]+)(/job/.+)$")
MWS_LINK    = re.compile(r"https://(wd\d+\.myworkdaysite\.com)/(?:[a-z]{2}-[A-Z]{2}/)?recruiting/([^/]+)/([^/]+)(/job/.+)$")
GS_LINK     = re.compile(r"higher\.gs\.com/roles/(\d+)")
ORACLE_LINK = re.compile(r"https://([^/]+\.oraclecloud\.com)/hcmUI/CandidateExperience/[^/]+/sites/([^/]+)/job/(\d+)")
ZIONS_LINK  = re.compile(r"careers\.zionsbancorp\.com/jobs/")
OLEEO_LINK  = re.compile(r"\.tal\.net/.+/opp/\d+")
WORKABLE_LINK = re.compile(r"apply\.workable\.com/(?:([^/]+)/)?j/([0-9A-F]{8,})")
DELOITTE_LINK = re.compile(r"apply\.deloitte\.com/.*/JobDetail/")
KPMG_LINK   = re.compile(r"kpmguscareers\.com/jobdetail/\?jobId=\d+")
YELLO_LINK  = re.compile(r"\.yello\.co/jobs/[\w-]+$")

def _status(url, *extra):
    return subprocess.run(["curl","-sS","-o","/dev/null","--max-time","25","-A",UA,"-w","%{http_code}",*extra,url],
                          capture_output=True, text=True).stdout.strip()

def _verdict(code, dead=("404",)):
    return "dead" if code in dead else "live" if code == "200" else "unknown"

def link_state(url):
    m = GH_LINK.search(url)
    if m: return _verdict(_status(f"https://boards-api.greenhouse.io/v1/boards/{m.group(1)}/jobs/{m.group(2)}"))
    m = LEVER_LINK.search(url)
    if m: return _verdict(_status(f"https://api.lever.co/v0/postings/{m.group(1)}/{m.group(2)}"))
    m = ASHBY_LINK.search(url)
    if m:
        try: d = curl(f"https://api.ashbyhq.com/posting-api/job-board/{m.group(1)}")
        except Exception: return "unknown"
        if not isinstance(d.get("jobs"), list): return "unknown"
        return "live" if m.group(2) in {j.get("jobUrl","").rstrip("/").split("/")[-1] for j in d["jobs"]} else "dead"
    m = WD_LINK.search(url)
    if m:   # Workday answers 403 ("permission denied") for a taken-down requisition and 404 for a bad id
        return _verdict(_status(f"https://{m.group(1)}.{m.group(2)}.myworkdayjobs.com/wday/cxs/{m.group(1)}/{m.group(3)}{m.group(4)}",
                                "-H", "Accept: application/json"), dead=("403", "404", "410"))
    m = MWS_LINK.search(url)
    if m:
        return _verdict(_status(f"https://{m.group(1)}/wday/cxs/{m.group(2)}/{m.group(3)}{m.group(4)}",
                                "-H", "Accept: application/json"), dead=("403", "404", "410"))
    m = GS_LINK.search(url)
    if m:   # higher.gs.com returns 200 for ids that never existed, so ask the GraphQL gateway
        code, body = curl_resp("https://api-higher.gs.com/gateway/api/v1/graphql", {"operationName":"GetRoleById",
                     "variables":{"externalSourceId":m.group(1),"externalSourceFetch":True},
                     "query":"query GetRoleById($externalSourceId: String!, $externalSourceFetch: Boolean) { role(externalSourceId: $externalSourceId, externalSourceFetch: $externalSourceFetch) { status applyActive } }"})
        if code != "200": return "unknown"
        try: d = json.loads(body)
        except Exception: return "unknown"
        role = (d.get("data") or {}).get("role")
        if role: return "live" if role.get("status") == "POSTED" else "dead"
        # A removed or unknown id comes back as role=null with an INTERNAL_ERROR. Any other error
        # (rate limit, outage) says nothing about the job.
        kinds = {((e.get("extensions") or {}).get("classification")) for e in d.get("errors") or []}
        return "dead" if kinds == {"INTERNAL_ERROR"} else "unknown"
    m = ORACLE_LINK.search(url)
    if m:
        code, body = curl_resp(f"https://{m.group(1)}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails?onlyData=true"
                               f"&finder=ById;Id=%22{m.group(3)}%22,siteNumber={m.group(2)}")
        if code != "200": return "unknown"
        try: d = json.loads(body)
        except Exception: return "unknown"
        if not isinstance(d.get("items"), list): return "unknown"
        return "live" if d["items"] else "dead"
    m = WORKABLE_LINK.search(url)
    if m and m.group(1):
        return _verdict(_status(f"https://apply.workable.com/api/v2/accounts/{m.group(1)}/jobs/{m.group(2)}"))
    if DELOITTE_LINK.search(url) or KPMG_LINK.search(url):   # 200 either way; the page title tells
        code, body = curl_resp(url, accept="text/html")
        title = (re.search(r"<title>(.*?)</title>", body, re.S) or [None, ""])[1].strip()
        if code == "404": return "dead"
        if code != "200" or not title: return "unknown"
        return "dead" if re.match(r"Error\b|Job Posting Not Found", title) else "live"
    if YELLO_LINK.search(url):   # a job that is gone redirects to the company's job board
        code, _, target = _status(url, "-w", "%{http_code} %{redirect_url}").partition(" ")
        if code == "302" and "/job_boards/" in target: return "dead"
        return _verdict(code, dead=())
    if ZIONS_LINK.search(url) or OLEEO_LINK.search(url):   # both answer 200 either way; the page text tells
        code, body = curl_resp(url, accept="text/html")
        if re.search(r"Quick Check Needed|oleeoProtect", body): return "unknown"   # a CAPTCHA, not an answer
        if re.search(r"position has been closed|no longer active", body, re.I): return "dead"
        if code == "404" and "Invalid Request" in body: return "dead"
        return "live" if code == "200" and re.search(r"Apply for Job|apply-form", body) else "unknown"
    return _verdict(_status(url, "-L"), dead=("404", "410"))

def check_link(url):
    try: return url, link_state(url)
    except Exception: return url, "unknown"

# ---------- your own applications (optional, never committed) ----------
# Put a file named applications.json next to this script and the report gains a section that
# says, for every job you applied to, whether this script could have found it and if not, why.
# That file is listed in .gitignore: it is personal, and this repository is public.
APPS = os.path.join(HERE, "applications.json")
def _norm(x):
    x = re.sub(r"&[a-z]+;|&#\d+;", " ", (x or "").lower().replace("&amp;", "&"))   # "&ndash;" is not a word
    return re.sub(r"[^a-z0-9]+", " ", re.sub(r"\bn\.\s?a\.?(?=\W|$)", "na", x)).strip()
# Words that can follow a company's name without making it a different company.
_SUFFIX = {"inc","incorporated","corp","corporation","co","company","llc","llp","lp","ltd","plc","us","usa","group","holdings",
           "bancorporation","bancorp","bank","financial","software","technologies","technology","labs",
           "services","pharmaceuticals","na","the"}
# Other names people use for an employer on the board. Keys are the board name without its parenthetical.
ALIASES = {
    "cicero group": {"mgt", "cicero", "mgt consulting"},
    "wgu": {"western governors university", "western governors"},
    "zions bancorporation": {"zions", "zions bank"},
    "jpmorgan chase": {"jpmorganchase", "jp morgan", "j p morgan", "jpmorgan", "jp morgan chase", "chase", "neovest"},
    "morgan stanley": {"parametric", "e trade", "etrade"},
    "america first credit union": {"america first", "afcu"},
    "vivint smart home": {"vivint", "nrg", "nrg energy"},
    "instructure": {"canvas lms"},
    "ey": {"ernst young", "ernst and young"},
    "pwc": {"pricewaterhousecoopers", "pricewaterhouse coopers"},
    "deloitte": {"deloitte touche", "deloitte and touche", "deloitte consulting", "deloitte advisory"},
    "citi": {"citigroup", "citibank"},
    "american express": {"amex"},
    "fidelity investments": {"fidelity", "fmr"},
    "fis": {"fis global", "fidelity national information services"},
    "vanguard": {"the vanguard group", "vanguard group"},
    "freddie mac": {"federal home loan mortgage corporation"},
    "fannie mae": {"federal national mortgage association"},
}
def _variants(name):
    base = _norm(re.sub(r"\(.*?\)", " ", name or ""))
    out = {base}
    for canon, names in ALIASES.items():
        if base == canon or base in names: out |= {canon} | names
    return {v for v in out if v}
def _close(a, b):
    if a == b: return True
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    return long_.startswith(short + " ") and all(w in _SUFFIX for w in long_[len(short):].split())
def same_company(a, b):
    """'Zions' matches 'Zions Bancorporation' and 'MGT' matches 'Cicero Group (MGT)', but
    'Pattern Energy' is not Pattern, 'Canvas Credit Union' is not Instructure (Canvas), and
    'Capital One' is not iCapital."""
    return any(_close(x, y) for x in _variants(a) for y in _variants(b))

_MONTHS = {"jan":"january","feb":"february","mar":"march","apr":"april","jun":"june","jul":"july","aug":"august",
           "sep":"september","sept":"september","oct":"october","nov":"november","dec":"december"}
def _title_tokens(t):   # no company stopwords here: "AI" and "Group" carry meaning in a job title
    words = re.sub(r"[^a-z0-9]+", " ", re.sub(r"&[a-z]+;|&#\d+;|<[^>]+>", " ", (t or "").lower())).split()
    return {_MONTHS.get(w, w) for w in words if w not in {"2026", "2027", "the", "of", "and"}}
def title_overlap(a, b):
    """0..1 Jaccard, so 'Senior Technical Support Engineer' does not outrank the exact title."""
    A, B = _title_tokens(a), _title_tokens(b)
    if not A or not B: return 0.0
    return len(A & B) / len(A | B)
def is_posting_for(applied, posted):
    """Is this live posting the job that was applied to? Nearly every word of the applied title must
    appear, and the posting may add words (a city, a program name) but no seniority. So
    'Security Analyst II' is not the 'Security Analyst' job, and a closed job is not mistaken for its
    senior sibling and then blamed on the filter."""
    A, B = _title_tokens(applied), _title_tokens(posted)
    if not A or len(A & B) / len(A) < 0.8: return False
    extra = " ".join(sorted(B - A))
    return not (SENIOR.search(extra) or (STAFF.search(extra) and not AUDITLIKE.search(posted)))

def load_applications():
    """Rows from applications.json with a company and a title; anything malformed is skipped, so a
    hand-edited file can never abort a run after every board has already been fetched."""
    if not os.path.exists(APPS): return [], None
    try: data = json.load(open(APPS, encoding="utf-8"))
    except Exception as e: return [], f"could not read applications.json: {e}"
    if not isinstance(data, list): return [], "applications.json should be a JSON list of applications"
    txt = lambda v: v.strip() if isinstance(v, str) else ""
    rows = [{"company": txt(a.get("company")), "title": txt(a.get("title")), "location": txt(a.get("location")),
             "applied": txt(a.get("applied")), "status": txt(a.get("status")) or "pending", "note": txt(a.get("note"))}
            for a in data if isinstance(a, dict)]
    rows = [r for r in rows if r["company"] and r["title"]]
    skipped = len(data) - len(rows)
    return rows, (f"skipped {skipped} malformed row(s) in applications.json" if skipped else None)

def audit_applications(apps, found, raw, tracked_api, tracked_manual, errors=None):
    """For each application: could this script have surfaced it, and if not, exactly why not."""
    errors = errors or {}
    rows, blind = [], {"untracked": 0, "manual": 0, "filtered": 0}
    for a in apps:
        co, title = a.get("company", ""), a.get("title", "")
        feeds = [c for c in tracked_api if same_company(c, co)]
        api = feeds[0] if feeds else None
        man = next((c for c in tracked_manual if same_company(c, co)), None)
        if api:
            rows_all = [r for c in feeds for r in raw.get(c, [])]
            ranked = sorted((r for r in rows_all if is_posting_for(title, r[0])),
                            key=lambda r: title_overlap(r[0], title), reverse=True)
            posted = ranked[0] if ranked else None
            if posted:
                ok, why = _classify(posted[0], posted[1])
                verdict = "still posted, and the script reports it" if ok else f"still posted, but FILTERED OUT: {why}"
                if not ok: blind["filtered"] += 1
            else:
                down = [f"{c}: {errors[c]}" for c in feeds if c in errors]
                empty = [c for c in feeds if c not in errors and not raw.get(c)]
                if down or empty:
                    verdict = ("COULD NOT CHECK today (" + "; ".join(down + [f"{c}: returned no jobs" for c in empty]) +
                               "), so this says nothing about whether the job is still open")
                else:
                    verdict = "no longer on the employer's feed (filled, closed or renamed)"
        elif man:
            verdict = "BLIND SPOT: employer is tracked but has no readable feed, so its roles are never listed"
            blind["manual"] += 1
        else:
            verdict = "BLIND SPOT: employer is not tracked at all"
            blind["untracked"] += 1
        rows.append(f"{a.get('applied',''):11} {co[:22]:24} {title[:44]:46} [{a.get('status','pending')}]\n"
                    f"              -> {verdict}")
    return rows, blind

def selftest():
    """Offline checks of the rules. Every title here is synthetic: this file is public, so it must never
    carry anyone's real application history. The second half of each list reproduces a mistake an
    earlier version of these rules made."""
    must_keep = [
        ("Staff Auditor", "Salt Lake City, UT"), ("IT Audit Staff", "Salt Lake City, UT"),
        ("Implementation Specialist", "Lehi, UT"), ("Machine Learning Engineer", "Provo, UT"),
        ("Technology Leadership Program, Data Analyst", "Charlotte, NC"),
        ("Rotational Analyst, 2027 Class", "Salt Lake City, UT"), ("Data Analyst (New Grad)", "Austin, TX"),
        ("Risk Analyst I", "Columbus, OH"), ("Internal Auditor I", "Salt Lake City, UT"),
        ("Associate Credit Analyst - Banker Development Program", "Salt Lake City, UT"),
        # regressions
        ("Software Engineer, New Grad (Spring 2027 Start)", "Seattle, WA"),
        ("Operations Analyst Cohort, Winter 2027 (Recent Grads)", "Boston, MA"),
        ("Security Analyst - EDR", "Remote, US"), ("Data Analyst I", "Vienna, VA"),
        ("Data Analyst I", "Melbourne, FL"), ("Data Analyst I", "Vancouver, WA"),
        ("Machine Learning Engineer, New Grad", "New York, United States; Paris, France"),
        ("Staff Consultant, Technology Risk", "Salt Lake City, UT"),
        ("Full-Time Analyst, 2027", "New York, NY"), ("Analyst 2027 Program", "Charlotte, NC"),
        ("Data Analyst, New Grad", "TAURUS (Germany, abroad); Salt Lake City, UT"),
        ("Associate Product Manager (APM), New College Graduate Rotational Program", "Foster City, CA"),
        ("Technology Analyst 2-Year Rotational Program", "Charlotte, NC"), ("Consultant 3/1/2027 Start", "Chicago, IL"),
        ("Software Engineer 2 - New College Grad", "Redmond, WA"),
        ("Fiduciary Risk Analyst", "Salt Lake City, UT"), ("Administrative Systems Analyst", "Salt Lake City, UT"),
        ("Data Analyst, New Grad", "San Juan (Puerto Rico); Salt Lake City, UT"),
        ("Future Leaders Program Rotation - Data and Analytics Track", "San Antonio, TX"),
    ]
    must_drop = [
        ("Staff Software Engineer", "Lehi, UT"), ("Senior Data Analyst", "Lehi, UT"),
        ("Risk Analyst Intern (Summer 2027)", "Menlo Park, CA"), ("Implementation Specialist", "Austin, TX"),
        ("Program Manager, AI", "Lehi, UT"), ("Customer Support Rep", "Orem, UT"),
        ("Data Analyst", "Bengaluru, India"), ("International Tax Analyst", "Salt Lake City, UT"),
        # regressions
        ("Software Engineer, New Grad", "Bucharest"), ("Software Engineer - New Grad", "Doha, Qatar"),
        ("University Recruiter", "San Francisco, CA"), ("Global Sourcing Specialist (Winter  C0-Op 2027)", "San Mateo, CA"),
        ("Program Specialist, M&A", "San Francisco, CA"), ("Snr. Commissions Analyst (Remote)", "Remote"),
        ("Enterprise Development Representative (December 2026 Grads)", "Austin, TX"),
        ("National Security Hackathon 2026 - General Interest", "San Francisco, CA"),
        ("Go-To-Market (GTM) Digital Natives Program Leader", "San Francisco, California"),
        ("Operations Summer Analyst Program", "South Jordan, UT"), ("MBA, Investment Banking Associate - 2027", "McLean, VA"),
        ("Return To Work - Central Review Risk Officer", "South Jordan, UT, US"),
        ("Master's - Data Science Internship 2027", "McLean, VA"),
        ("Software Engineer", "Clayton, MO"), ("Data Engineer", "Lehigh Valley, PA"),
        ("Program Mentor - School of Health", "Salt Lake City, UT"),
        ("Part-time Client Service Associate - Teller (20 hours)", "Mesa, AZ"),
        ("Associate Banker, 20 Hours", "Park City, UT"), ("Small Business Underwriter I", "Richmond, VA"),
        ("Program Mgmt Intmd Analyst", "Tampa, FL"), ("Apps Dev Programmer Analyst 2", "Irving, TX"),
        ("Cloud Security Analyst – Intermediate Level", "Charlotte, NC"), ("Associate Financial Advisor", "Bend, OR"),
        ("Financial Services Representative, College Graduate", "Boston, MA"),
        ("Placement Analyst 2027", "TAURUS (Germany, abroad)"), ("Senior Product Manager", "Lehi, UT"),
        ("Associate Director, Product Manager", "Lehi, UT"),
        ("Data Analyst, New Grad", "Chennai, TN (India, abroad)"), ("Summer Fiduciary Associate", "New York, NY"),
        ("Administrative Associate", "Malvern, PA"), ("Associate Wealth Banking Specialist", "Scottsdale, AZ"), ("Strategy Consulting Analyst", "Riga (Latvia, abroad)"),
    ]
    bad = [f"should KEEP: {t} ({l}) -> {_classify(t,l)[1]}" for t, l in must_keep if not classify(t, l)]
    bad += [f"should DROP: {t} ({l})" for t, l in must_drop if classify(t, l)]
    checks = [
        (where("Sandy Springs, GA") == "elsewhere", "Sandy Springs, GA is not Utah"),
        (where("Remote - EMEA") is None, "Remote EMEA is not reachable"),
        (where("Remote; Paris, France") == "remote", "a remote US option survives a foreign city"),
        (classify("Technology Risk Analyst I, Launch Program 2027", "O'Fallon, MO") == {"signal": "program", "geo": "elsewhere"}, "program elsewhere"),
        (classify("Associate Program Manager, Operations", "Seattle, WA") == {"signal": "entry", "geo": "elsewhere"}, "APgM is a job, not a program"),
        (where("TAURUS (Germany, abroad); ORION (Germany, abroad)") is None, "a foreign requisition's extra cities are foreign too"),
        (same_company("Zions", "Zions Bancorporation"), "Zions"), (same_company("MGT", "Cicero Group (MGT)"), "MGT alias"),
        (same_company("JPMorganChase", "JPMorgan Chase"), "JPMorganChase"), (same_company("Galileo", "Galileo Financial Technologies"), "suffixes"),
        (not same_company("Capital One", "iCapital"), "Capital One vs iCapital"),
        (not same_company("Pattern Energy", "Pattern"), "Pattern Energy"), (not same_company("Weave Grid", "Weave"), "Weave Grid"),
        (not same_company("Canvas Credit Union", "Instructure (Canvas)"), "Canvas Credit Union"),
        (not same_company("Salt Lake City Corporation", "Mastercard (Salt Lake City)"), "parenthetical is not a company"),
        (not same_company("First Credit Union", "America First Credit Union"), "First Credit Union"),
        (is_posting_for("Business Analyst, Jan 2027", "Business Analyst (January 2027)"), "month abbreviations"),
        (is_posting_for("Risk Analyst I, Launch 2027", "Risk Analyst I, Launch 2027 - St. Louis, MO, US"), "city suffix"),
        (not is_posting_for("Data Analyst", "Senior Data Analyst"), "senior sibling is a different job"),
        (not is_posting_for("Security Analyst", "Security Analyst II"), "level II is a different job"),
    ]
    bad += [f"check failed: {why}" for ok, why in checks if not ok]
    print("\n".join(bad) if bad else f"selftest passed: {len(must_keep)} kept, {len(must_drop)} dropped, {len(checks)} checks")
    return 1 if bad else 0

# ---------- run ----------
def main():
    if "--selftest" in sys.argv: return selftest()
    today = datetime.date.today().isoformat()
    jobs = [(kind, co, slug) for kind, d in BOARDS.items() for co, slug in d.items()]
    print(f"Checking {len(jobs)} job boards…")

    found, raw, errors = {}, {}, {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        for company, hits, rows, err in ex.map(scan, jobs):
            if err: errors[company] = err
            else:   found[company], raw[company] = hits, rows

    # links currently on the dashboard
    html = open(INDEX, encoding="utf-8").read() if os.path.exists(INDEX) else ""
    board_links = re.findall(r'openings: \[(.*?)\]\n', html, re.S)
    urls = sorted(set(re.findall(r'url: "([^"]+)"', " ".join(board_links))))
    print(f"Testing {len(urls)} links already on your board…")
    dead = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        for url, state in ex.map(check_link, urls):
            if state == "dead": dead.append(("gone", url))

    prev = json.load(open(STATE)) if os.path.exists(STATE) else {}
    rebaseline = bool(prev) and prev.get("filter_version") != FILTER_VERSION
    prev_roles = {} if rebaseline else prev.get("roles", {})
    # A board that answers with nothing at all, when it had several roles last time, almost always
    # failed rather than closed every job at once. Treat it as unreadable today.
    for co in list(found):
        if not raw.get(co) and len(prev_roles.get(co, [])) >= 3:
            errors[co] = f"returned no jobs at all (it had {len(prev_roles[co])} last run), so treated as a failed fetch"
            del found[co]

    apps, apps_problem = load_applications()
    if apps_problem: print(f"({apps_problem})")
    applied = lambda co, title: any(same_company(a["company"], co) and is_posting_for(a["title"], title) for a in apps)

    new_roles, gone_roles = {}, {}
    for co, hits in found.items():
        now  = {h["title"]: h for h in hits}
        was  = set(prev_roles.get(co, []))
        if prev_roles:
            fresh = [h for t, h in now.items() if t not in was]
            if fresh: new_roles[co] = fresh
            closed = [t for t in was if t not in now]
            if closed: gone_roles[co] = closed
        else:
            if hits: new_roles[co] = hits

    # ---------- report ----------
    L = []
    add = L.append
    live = [h for hits in found.values() for h in hits]
    add(f"JOB FINDER REFRESH — {today}")
    add("=" * 60)
    add(f"{len(found)} boards checked · {len(live)} entry-level roles live "
        f"({sum(h['geo']=='home' for h in live)} in {HOME_NAME}, {sum(h['geo']=='remote' for h in live)} remote, "
        f"{sum(h['geo']=='elsewhere' and h['signal']=='program' for h in live)} new-grad programs elsewhere) "
        f"· {len(MANUAL)} to check by hand")
    if rebaseline:
        add("(the filter rules changed since the last run, so this run is a fresh baseline: everything is listed as new)")
    elif not prev_roles:
        add("(first run — everything below is listed as new)")

    def block(title, rows):
        add(""); add(title); add("-" * len(title))
        if not rows: add("  none")
        for r in rows: add("  " + r)

    def line(co, h):
        mark = " (you applied)" if applied(co, h["title"]) else (" ?years" if h["signal"] == "unleveled" else "")
        closes = f" closes {h['closes']}" if h.get("closes") else ""
        return f"{co[:26]:28} {(h['title'][:50] + mark)[:64]:66} {h['loc'][:26]:28} {h['url']}{closes}"

    groups = {"home": [], "remote": [], "program": [], "other": []}
    for co in sorted(new_roles):
        for h in new_roles[co]:
            key = h["geo"] if h["geo"] in ("home", "remote") else ("program" if h["signal"] == "program" else "other")
            groups[key].append((h["loc"], line(co, h)))
    add(""); add(f"NEW ENTRY-LEVEL ROLES ({sum(len(v) for v in groups.values())})   '?years' = no level in the title, so read the posting")
    block(f"  In {HOME_NAME} ({len(groups['home'])})", [r for _, r in sorted(groups["home"], key=lambda x: x[1])])
    block(f"  Remote ({len(groups['remote'])})", [r for _, r in sorted(groups["remote"], key=lambda x: x[1])])
    # Every row is printed. An earlier version capped this list at fifteen, which silently hid
    # exactly the structured new-grad programs a candidate would move for.
    block(f"  New-grad programs elsewhere — worth relocating for ({len(groups['program'])})",
          [r for _, r in sorted(groups["program"])])
    block(f"  Other entry-level roles elsewhere ({len(groups['other'])})", [r for _, r in sorted(groups["other"])])

    # Every live role with a published closing date in the next two weeks, new or not.
    soon = (datetime.date.today() + datetime.timedelta(days=14)).isoformat()
    rows = sorted(f"{h['closes']}  {line(co, h)}" for co, hits in found.items() for h in hits
                  if h.get("closes") and today <= h["closes"] <= soon)
    block(f"CLOSING IN THE NEXT 14 DAYS ({len(rows)})   the employer's scheduled end date; some mean the day after, so apply early", rows)

    rows = [f"{co:34} {t}" + ("   <-- you applied to this one" if applied(co, t) else "")
            for co in sorted(gone_roles) for t in sorted(gone_roles[co])]
    block(f"CLOSED SINCE LAST RUN ({len(rows)})", rows)

    rows = [f"{code}  {u}" for code, u in dead]
    block(f"DEAD LINKS ON YOUR BOARD ({len(dead)})", rows)

    # Openings on the board carry the closing date they were published with. Once it passes, the card
    # shows the opening struck through, and this list says which ones to take off.
    past = sorted((c, u) for u, c in re.findall(r'\{[^{}]*?url: "([^"]+)"[^{}]*?closes: "(\d{4}-\d{2}-\d{2})"', " ".join(board_links))
                  if c < today)
    block(f"PAST THEIR CLOSING DATE ON YOUR BOARD ({len(past)})", [f"{c}  {u}" for c, u in past])

    if apps:
        rows, blind = audit_applications(apps, found, raw, list(found) + list(errors), list(MANUAL), errors)
        block(f"YOUR APPLICATIONS ({len(apps)}) — could this script have found each one?", rows)
        add("")
        add(f"  Blind spots: {blind['untracked']} at employers not tracked, {blind['manual']} at employers with no readable "
            f"feed, {blind['filtered']} filtered out by the title rules.")
        if blind["untracked"] or blind["manual"]:
            add("  Fix: add the employer to BOARDS (or MANUAL) above. A job you applied to that this script cannot see")
            add("  means the next one like it will be missed too.")

    rows = [f"{co:34} {url}" for co, url in sorted(MANUAL.items())]
    block("CHECK THESE BY HAND (no readable job feed)", rows)

    if errors:
        block(f"BOARDS THAT DID NOT RESPOND ({len(errors)})",
              [f"{co:34} {e}" for co, e in sorted(errors.items())])
    partial = {co: PARTIAL[slug] for co, slug in ((co, sl) for d in BOARDS.values() for co, sl in d.items()) if slug in PARTIAL}
    if partial:
        block(f"BOARDS READ ONLY IN PART ({len(partial)})", [f"{co:34} {why}" for co, why in sorted(partial.items())])

    text = "\n".join(L)
    print("\n" + text)
    open(REPORT, "w", encoding="utf-8").write(text + "\n")
    roles = {co: [h["title"] for h in hits] for co, hits in found.items()}
    for co in errors:   # carry forward, so its next good run is compared against the last good one
        if co in prev_roles: roles[co] = prev_roles[co]
    json.dump({"date": today, "filter_version": FILTER_VERSION, "roles": roles}, open(STATE, "w"), indent=1)
    print(f"\nSaved to {os.path.basename(REPORT)}")

if __name__ == "__main__":
    sys.exit(main())
