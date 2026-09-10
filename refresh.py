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
import json, os, re, subprocess, sys, datetime, concurrent.futures

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
    "iCapital":"icapitalnetwork",
  },
  "lever":  {"Ataccama":"ataccama", "Filevine":"filevine", "Pattern":"pattern", "Entrata":"entrata"},
  "ashby":  {"Snowflake":"snowflake", "Plaid":"plaid", "Instructure (Canvas)":"instructure",
             "OpenAI":"openai", "Ramp":"ramp", "Perplexity AI":"perplexity", "Sardine":"sardine",
             "Vanta":"vanta", "Drata":"drata", "1Password":"1password", "Material Security":"material",
             "Lumos":"lumos"},
  "workable":{"Hugging Face":"huggingface"},
  "workday": {
    "Pluralsight":"pluralsight|wd1|Careers", "Proofpoint":"proofpoint|wd5|ProofpointCareers",
    "CrowdStrike":"crowdstrike|wd5|crowdstrikecareers", "Arctic Wolf":"arcticwolf|wd1|External",
    "Palo Alto Networks":"paloaltonetworks|wd5|panwexternalcareers",
    "Health Catalyst":"healthcatalyst|wd5|healthcatalystcareers", "Domo":"domo|wd12|DomoCareers",
    "Optiv":"optiv|wd5|Optiv_Careers", "SailPoint":"sailpoint|wd1|SailPoint",
  },
  "bamboohr":{"SecurityMetrics":"securitymetrics"},
}
# no public API - the report just reminds you to look
MANUAL = {
  "Goldman Sachs (SLC Campus)":"https://higher.gs.com/campus",
  "JPMorgan Chase":"https://www.jpmorganchase.com/careers/explore-opportunities/programs",
  "Capital One":"https://www.capitalonecareers.com/full-time-programs",
  "Mastercard":"https://careers.mastercard.com/us/en/early-careers/launch",
  "Bloomberg":"https://bloomberg.avature.net/careers",
  "Adobe (Lehi Campus)":"https://careers.adobe.com/us/en/university",
  "Ancestry":"https://careers.ancestry.com/",
  "Cotiviti":"https://careers-cotiviti.icims.com/jobs/intro",
  "Vivint Smart Home":"https://careers.nrgenergy.com/SMARTHOMES/",
  "Ivanti":"https://www.ivanti.com/company/careers/find",
  "WGU (Western Governors University)":"https://jobs.wgu.edu/jobs",
  "Zions Bancorporation":"https://careers.zionsbancorp.com/jobs/search/",
  "America First Credit Union":"https://www.americafirst.com/about/careers.html",
}

# ---------- what counts as a role worth telling you about ----------
SENIOR  = re.compile(r"\b(senior|sr\.?|staff|principal|lead|manager|director|head|vp|vice president|"
                     r"chief|architect|fellow|counsel|attorney|recruit|account executive|"
                     r"customer success|ii|iii|iv|distinguished|apprentice)\b", re.I)
ENTRY   = re.compile(r"(new ?grad|graduate|early[- ]career|university|campus|entry[- ]level|junior|"
                     r"\bassociate\b|rotational|2027|\banalyst\b|engineer[, ]+i\b|\bi\b$|\(i\))", re.I)
# titles that match ENTRY but are not the kind of work you want
OFFTOPIC= re.compile(r"\b(sales|business development|bdr|sdr|account executive|account manager|"
                     r"partnership|marketing|investor relations|recruit|talent|skillbridge|"
                     r"clinical|nurse|physician|therapist|dental|teacher|instructor|faculty|"
                     r"real estate|collections|underwriting|payroll|tax|legal|counsel|"
                     r"communications|public relations|brand|content|social media|"
                     r"customer success|deal desk|commission|procurement|facilities|"
                     r"data center|electrical|mechanical|hardware|warehouse|driver)\b", re.I)
UTAH    = re.compile(r"utah|\but\b|salt lake|lehi|provo|draper|south jordan|american fork|lindon|"
                     r"cottonwood|orem|ogden|riverdale|sandy", re.I)
REMOTE  = re.compile(r"remote|anywhere|distributed", re.I)
NONUS   = re.compile(r"london|dublin(?!,? ca)|india|bangalore|bengaluru|hyderabad|pune|toronto|canada|"
                     r"singapore|tokyo|japan|sydney|australia|berlin|munich|germany|paris|france|"
                     r"amsterdam|netherlands|prague|czech|slovak|bulgaria|mexico|brazil|poland|warsaw|"
                     r"krakow|united kingdom|ireland|israel|tel aviv|switzerland|spain|italy|sweden|"
                     r"denmark|norway|finland|portugal|belgium|dubai|philippines|manila|vietnam|"
                     r"thailand|malaysia|indonesia|korea|seoul|china|beijing|shanghai|hong kong|"
                     r"taiwan|new zealand|argentina|colombia|chile|costa rica|nigeria|kenya|"
                     r"south africa|egypt|turkey|greece|romania|hungary|budapest|austria|serbia|"
                     r"belgrade|ukraine|emea|apac|latam", re.I)

def interesting(title, loc):
    """Entry-level signal in the title, on-topic work, and reachable from Utah."""
    if not title or SENIOR.search(title) or OFFTOPIC.search(title): return False
    if not ENTRY.search(title): return False
    loc = loc or ""
    if NONUS.search(loc) and not UTAH.search(loc): return False
    return True

def where(loc):
    loc = loc or ""
    if UTAH.search(loc):   return "UTAH"
    if REMOTE.search(loc): return "remote"
    return "US"

# ---------- fetching ----------
def curl(url, post=None, timeout=25):
    cmd = ["curl","-sS","-L","--max-time",str(timeout),"-A",UA,"-H","Accept: application/json"]
    if post is not None:
        cmd += ["-H","Content-Type: application/json","-X","POST","--data",json.dumps(post)]
    out = subprocess.run(cmd+[url], capture_output=True, text=True).stdout
    return json.loads(out)

def fetch(kind, slug):
    """Return [(title, location, url)] for one company."""
    if kind == "greenhouse":
        d = curl(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")
        return [(j["title"], (j.get("location") or {}).get("name",""), j["absolute_url"])
                for j in d.get("jobs", [])]
    if kind == "lever":
        d = curl(f"https://api.lever.co/v0/postings/{slug}?mode=json")
        return [(j["text"], (j.get("categories") or {}).get("location",""), j["hostedUrl"]) for j in d]
    if kind == "ashby":
        d = curl(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
        return [(j["title"], j.get("location",""), j.get("jobUrl","")) for j in d.get("jobs", [])]
    if kind == "workable":
        d = curl(f"https://apply.workable.com/api/v1/widget/accounts/{slug}")
        return [(j["title"], ", ".join(filter(None,[j.get("city"),j.get("country")])), j.get("url",""))
                for j in d.get("jobs", [])]
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
        tenant, wd, site = slug.split("|")
        base = f"https://{tenant}.{wd}.myworkdayjobs.com"
        out, off = [], 0
        while off < 400:
            d = curl(f"{base}/wday/cxs/{tenant}/{site}/jobs",
                     {"appliedFacets":{},"limit":20,"offset":off,"searchText":""})
            posts = d.get("jobPostings", [])
            if not posts: break
            for j in posts:
                out.append((j.get("title",""), j.get("locationsText",""),
                            base + "/en-US/" + site + j.get("externalPath","")))
            off += 20
            if off >= d.get("total", 0): break
        return out
    return []

def scan(item):
    kind, company, slug = item
    try:
        rows = fetch(kind, slug)
    except Exception as e:
        return company, None, f"{type(e).__name__}"
    hits = [{"title":t.strip(), "loc":(l or "").strip(), "url":u, "geo":where(l)}
            for t, l, u in rows if interesting(t, l)]
    return company, hits, None

def check_link(url):
    code = subprocess.run(["curl","-sS","-o","/dev/null","-L","--max-time","20","-A",UA,
                           "-w","%{http_code}", url], capture_output=True, text=True).stdout.strip()
    return url, code

# ---------- run ----------
def main():
    today = datetime.date.today().isoformat()
    jobs = [(kind, co, slug) for kind, d in BOARDS.items() for co, slug in d.items()]
    print(f"Checking {len(jobs)} job boards…")

    found, errors = {}, {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        for company, hits, err in ex.map(scan, jobs):
            if err: errors[company] = err
            else:   found[company] = hits

    # links currently on the dashboard
    html = open(INDEX, encoding="utf-8").read() if os.path.exists(INDEX) else ""
    board_links = re.findall(r'openings: \[(.*?)\]\n', html, re.S)
    urls = sorted(set(re.findall(r'url: "([^"]+)"', " ".join(board_links))))
    print(f"Testing {len(urls)} links already on your board…")
    dead = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        for url, code in ex.map(check_link, urls):
            if code in ("404","410","000"): dead.append((code, url))

    prev = json.load(open(STATE)) if os.path.exists(STATE) else {}
    prev_roles = prev.get("roles", {})

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
    add(f"JOB FINDER REFRESH — {today}")
    add("=" * 60)
    add(f"{len(found)} boards checked · {sum(len(v) for v in found.values())} entry-level roles live "
        f"· {len(MANUAL)} to check by hand")
    if not prev_roles:
        add("(first run — everything below is listed as new)")

    def block(title, rows):
        add(""); add(title); add("-" * len(title))
        if not rows: add("  none")
        for r in rows: add("  " + r)

    by_geo = {"UTAH": [], "remote": [], "US": []}
    for co in sorted(new_roles):
        for h in new_roles[co]:
            by_geo[h["geo"]].append(f"{co:30} {h['title'][:46]:48} {h['url']}")
    total_new = sum(len(v) for v in by_geo.values())
    add(""); add(f"NEW ENTRY-LEVEL ROLES ({total_new})")
    block(f"  In Utah ({len(by_geo['UTAH'])})", sorted(by_geo["UTAH"]))
    block(f"  Remote ({len(by_geo['remote'])})", sorted(by_geo["remote"]))
    tail = sorted(by_geo["US"])
    block(f"  Elsewhere in the US ({len(tail)})", tail[:15] +
          ([f"... and {len(tail)-15} more"] if len(tail) > 15 else []))

    rows = [f"{co:34} {t}" for co in sorted(gone_roles) for t in sorted(gone_roles[co])]
    block(f"CLOSED SINCE LAST RUN ({len(rows)})", rows)

    rows = [f"{code}  {u}" for code, u in dead]
    block(f"DEAD LINKS ON YOUR BOARD ({len(dead)})", rows)

    rows = [f"{co:34} {url}" for co, url in sorted(MANUAL.items())]
    block("CHECK THESE BY HAND (no public job board)", rows)

    if errors:
        block(f"BOARDS THAT DID NOT RESPOND ({len(errors)})",
              [f"{co:34} {e}" for co, e in sorted(errors.items())])

    text = "\n".join(L)
    print("\n" + text)
    open(REPORT, "w", encoding="utf-8").write(text + "\n")
    json.dump({"date": today, "roles": {co: [h["title"] for h in hits] for co, hits in found.items()}},
              open(STATE, "w"), indent=1)
    print(f"\nSaved to {os.path.basename(REPORT)}")

if __name__ == "__main__":
    sys.exit(main())
