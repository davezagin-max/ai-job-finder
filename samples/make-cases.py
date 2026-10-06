#!/usr/bin/env python3
"""
Build the mock tailoring responses in samples/cases/ from the board itself.

    python3 samples/make-cases.py

Each case is what Claude would return for one of the fictional candidates whose
resumes sit in samples/resumes/, written in the shape of OUTPUT_FORMAT in index.html, so the page can replay it with no API key
(see samples/README.md). The scores are made up by simple rules, and the suggested
employers are real companies with invented notes. Nothing here is career advice.

The cases are generated rather than hand-written so that they cover every employer
on the board. Hand-written fixtures fell behind the first time the board grew:
sixty companies out of eighty-one is under the page's 80% rule, and every case was
rejected. Re-run this script after adding employers.
"""
import hashlib, json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(HERE, "..", "index.html")
OUT = os.path.join(HERE, "cases")

# ---------- read the board ----------
def read_board():
    s = open(INDEX, encoding="utf-8").read()
    a, b = s.index("const COMPANIES = ["), s.index("const APPLY_STATUS")
    companies = []
    for m in re.finditer(r'\n  \{\n(.*?)\n  \},?', s[a:b], re.S):
        body = m.group(1)
        g = lambda k: (re.search(r'\b%s: "([^"]*)"' % k, body) or [None, ""])[1]
        arr = lambda k: re.findall(r'"([^"]+)"', (re.search(r'\b%s: \[([^\]]*)\]' % k, body) or [None, ""])[1])
        companies.append({"name": g("name"), "location": g("location"), "locType": g("locType"),
                          "industry": arr("industry"), "roles": arr("roles"), "badges": arr("badges"),
                          "alumni": g("alumni")})
    a = s.index("const APPLY_STATUS = {")
    b = s.index("\n};", a)
    status = {}
    for co, body in re.findall(r'\n  "([^"]+)": \{(.*?)\n  \}', s[a:b], re.S):
        st = re.search(r'status: "([^"]+)"', body).group(1)
        opens = []
        for o in re.findall(r'\{ title: .*?\}', body):
            yrs = re.search(r'yrs: (\d+)', o)
            opens.append({"title": re.search(r'title: "((?:[^"\\]|\\.)*)"', o).group(1),
                          "yrs": int(yrs.group(1)) if yrs else None,
                          "closes": (re.search(r'closes: "([^"]+)"', o) or [None, None])[1],
                          "program": bool(re.search(r'program: true', o)),
                          "degree": (re.search(r'degree: "([^"]+)"', o) or [None, None])[1]})
        status[co] = {"status": st, "openings": opens}
    for c in companies:
        c.update(status.get(c["name"], {"status": "watch", "openings": []}))
    return companies

def spread(name, lo, hi):
    """A stable pseudo-random integer in [lo, hi] from the company name, so scores vary but never change between runs."""
    h = int(hashlib.sha1(name.encode()).hexdigest(), 16)
    return lo + h % (hi - lo + 1)

def city_of(location):
    return location.split(",")[0].strip().lower()

# ---------- the personas ----------
# Each persona scores the board by rules: industry and role fit, geography relative to the candidate's
# home base, and whether the candidate's tools overlap. The header text is written by hand.
PERSONAS = {
    "nurse-slc": {
        "profile": {
            "name": "Kendra Villalobos", "initials": "KV",
            "subline": "Nursing roles for an ICU nurse with two years at the bedside · Tailored to your resume · Board assumes Salt Lake City",
            "status": "RN, BSN · 2 years ICU", "recentRole": "Intermountain Medical Center — Staff Nurse, Medical ICU (2024–2026)",
            "stack": "ICU care, Epic charting, charge coverage, ACLS, rapid response, patient education",
            "target": "Staff or charge nurse · Salt Lake City · acute care or clinical informatics",
            "yearsExperience": 2, "uofu": False, "city": "Salt Lake City, UT", "geoLabel": "SLC Area", "cohortLabel": "experienced nurse",
            "linkedin": "https://www.linkedin.com/in/kendra-villalobos-rn",
            "summary": "This board hires data, software and fintech people, and your resume is a clinical one, so the useful half of this page is the suggested hospitals and health systems below. The board's health-tech employers are a stretch unless you want to move into clinical informatics.",
            "searchLinks": [{"label": "ICU nurse, Salt Lake City", "keywords": "ICU registered nurse", "location": "Salt Lake City, Utah", "remoteOnly": False, "entryLevel": False},
                            {"label": "Clinical informatics, Utah", "keywords": "clinical informatics nurse", "location": "Salt Lake City, Utah", "remoteOnly": False, "entryLevel": False}],
            "applyNow": "Start with the suggested health systems; every one of them hires ICU nurses year-round. On this board, only Recursion and Health Catalyst are even adjacent to your field.",
            "watchLater": "If clinical informatics appeals, an Epic analyst certification would open the health-tech cards here.",
        },
        "industry": {"fintech": -6, "data": -8, "ai-lab": -10, "health": 6, "cyber": -10, "other": -4},
        "roles": {"ml": -4, "swe": -4, "data": -2, "product": 0},
        "home": "salt lake city", "remap": False, "tools": set(),
        "status": lambda c: "keep",
        "suggested": [
            ("Intermountain Health", "Salt Lake City, UT", "local", ["health"], [], 96, "high", "Utah's largest health system, with ICU and step-down units across the valley and a nurse residency for anyone changing specialty.", "Search 'ICU RN' and 'Registered Nurse' on their careers site; openings post weekly."),
            ("University of Utah Health", "Salt Lake City, UT", "local", ["health"], [], 94, "high", "Academic medical center with multiple ICUs, a nurse residency and a clinical informatics group that hires RNs.", "Look for 'Staff Nurse' and 'Nurse Informaticist' postings."),
            ("HCA Healthcare MountainStar", "Salt Lake City, UT", "local", ["health"], [], 85, "high", "Six Wasatch Front hospitals with ICU openings most weeks.", "Search 'RN ICU' on HCA's careers site and filter to Utah."),
            ("Steward Health Care Utah", "Salt Lake City, UT", "local", ["health"], [], 78, "medium", "Community hospitals in the valley that hire experienced critical-care nurses.", "Check each hospital's own careers page."),
            ("VA Salt Lake City Health Care", "Salt Lake City, UT", "local", ["health"], [], 82, "high", "Federal hospital with ICU seats and strong benefits; applications go through USAJOBS.", "Search 'Nurse ICU Salt Lake City' on USAJOBS."),
            ("Epic Systems", "Verona, WI (remote)", "remote", ["health"], ["data"], 70, "medium", "The charting system you use every shift; Epic hires clinicians into implementation and analyst roles.", "Search 'Clinical Informatics' and 'Implementation' on Epic's careers site."),
        ],
    },
    "austin-cs-ms": {
        "profile": {
            "name": "Tobias Marchetti", "initials": "TM",
            "subline": "New-grad machine-learning and software roles for a May 2027 CS master's graduate · Tailored to your resume · Board re-mapped to Austin",
            "status": "MS Computer Science · Grad May 2027", "recentRole": "Meta — Machine Learning Engineer Intern, Ads Ranking (Summer 2026)",
            "stack": "PyTorch, CUDA, distributed training, Python, C++, two publications, Spark",
            "target": "New-grad ML or software engineer · Austin, TX · remote welcome",
            "yearsExperience": 0, "uofu": False, "city": "Austin, TX", "geoLabel": "Austin Area", "cohortLabel": "May 2027 master's grad",
            "linkedin": "https://www.linkedin.com/in/tobias-marchetti-ml",
            "summary": "You are a strong new-grad ML candidate, and the degree bars that stop information-systems applicants on this board are no obstacle for a CS master's. The board is Salt Lake-centric, so Utah employers read as relocation; Austin employers are added below.",
            "searchLinks": [{"label": "ML engineer new grad, Austin", "keywords": "machine learning engineer new grad", "location": "Austin, Texas", "remoteOnly": False, "entryLevel": True},
                            {"label": "Remote new-grad ML", "keywords": "machine learning engineer new grad", "location": "", "remoteOnly": True, "entryLevel": True}],
            "applyNow": "Scale AI, Adobe's University Graduate ML Engineer and Stripe's New Grad SWE are the live doors that fit; Cloudflare's Austin data team is the local one.",
            "watchLater": "Snowflake and Databricks post new-grad ML reqs in waves through the fall.",
        },
        "industry": {"fintech": 2, "data": 6, "ai-lab": 12, "health": -2, "cyber": 0, "other": 0},
        "roles": {"ml": 10, "swe": 6, "data": 2, "product": -2},
        "home": "austin", "remap": True, "tools": {"ml", "swe"},
        "status": lambda c: "keep",
        "suggested": [
            ("Oracle", "Austin, TX", "local", ["data"], ["swe", "data"], 84, "high", "Headquartered in Austin, with a large new-college-grad engineering intake every year.", "Search 'New College Grad' on Oracle's careers site."),
            ("Dell Technologies", "Round Rock, TX", "local", ["other"], ["swe", "data", "ml"], 82, "high", "Round Rock HQ hires new grads into software and data roles each spring.", "Look for 'Software Engineer 1' and 'Data Scientist 1' reqs."),
            ("Apple", "Austin, TX", "local", ["other"], ["swe", "ml"], 80, "medium", "Austin campus is Apple's second largest; ML hiring is mostly experienced.", "Filter Apple's jobs page to Austin and 'Machine Learning'."),
            ("Indeed", "Austin, TX", "local", ["data"], ["swe", "ml", "data"], 83, "high", "Austin-based, with a University Grad software engineer program.", "Search 'University Grad' on Indeed's own careers site."),
            ("Applied Materials", "Austin, TX", "local", ["other"], ["ml", "swe"], 72, "medium", "Semiconductor equipment maker with a large Austin site that hires ML engineers for process control.", "Search 'Machine Learning' and 'New College Graduate'."),
            ("Tesla", "Austin, TX", "local", ["other"], ["swe", "ml"], 76, "medium", "Gigafactory Texas and the autopilot teams hire new-grad engineers, usually without a formal program.", "Search 'Software Engineer, New Grad' on Tesla's site."),
            ("Arm", "Austin, TX", "local", ["other"], ["swe"], 70, "medium", "Austin design center with a graduate engineering intake.", "Look for 'Graduate Software Engineer' postings."),
        ],
    },
    "denver-career-changer": {
        "profile": {
            "name": "Caleb Montenegro", "initials": "CM",
            "subline": "Data analyst roles for a career changer with six years of teaching and a 2026 analytics master's · Tailored to your resume · Board re-mapped to Denver",
            "status": "MS Analytics (OMSA) · Grad Aug 2026", "recentRole": "Jeffco Public Schools — High School Mathematics Teacher (2018–2024)",
            "stack": "SQL, Tableau, Python (pandas), R, regression and forecasting, stakeholder communication",
            "target": "Data analyst · Denver, CO · open to relocating to Salt Lake City",
            "yearsExperience": 6, "uofu": False, "city": "Denver, CO", "geoLabel": "Denver Area", "cohortLabel": "career changer",
            "linkedin": "https://www.linkedin.com/in/caleb-montenegro-analytics",
            "summary": "Six years of professional work plus a fresh analytics master's puts you past the new-grad programs and into the ordinary analyst reqs, which is better news than it sounds: roles asking two or three years are within reach. Denver employers are added below, and the Salt Lake roles are flagged as a move you said you would make.",
            "searchLinks": [{"label": "Data analyst, Denver", "keywords": "data analyst", "location": "Denver, Colorado", "remoteOnly": False, "entryLevel": False},
                            {"label": "Data analyst, Salt Lake City", "keywords": "data analyst", "location": "Salt Lake City, Utah", "remoteOnly": False, "entryLevel": False}],
            "applyNow": "Qualtrics' GTM Data Analyst in Provo and Fidelity's Salt Lake Analytics associate are written for exactly your years; EY's Assurance Data analyst lists Denver.",
            "watchLater": "The 2027 new-grad classes are the wrong cohort for you; ignore them rather than apply.",
        },
        "industry": {"fintech": 2, "data": 8, "ai-lab": -4, "health": 2, "cyber": -4, "other": 0},
        "roles": {"ml": -4, "swe": -8, "data": 10, "product": 0},
        "home": "denver", "remap": True, "tools": {"data"},
        # a six-year professional is the wrong cohort for an employer whose only openings are new-grad programs
        "status": lambda c: "wrong-cohort" if c["openings"] and all(o["program"] for o in c["openings"]) else "keep",
        "suggested": [
            ("Ibotta", "Denver, CO", "local", ["fintech", "data"], ["data", "product"], 86, "high", "Denver fintech with a large analytics organisation that hires analysts from non-traditional backgrounds.", "Search 'Analyst' on Ibotta's careers site."),
            ("Gusto", "Denver, CO", "local", ["fintech"], ["data", "swe"], 80, "high", "Payroll fintech with a big Denver office and regular data-analyst reqs.", "Filter Gusto's jobs to Denver and 'Data'."),
            ("Guild", "Denver, CO", "local", ["other"], ["data"], 82, "medium", "Education-benefits company; a former teacher's domain knowledge is a genuine edge here.", "Look for 'Analyst' and 'Business Intelligence' roles."),
            ("Western Union", "Denver, CO", "local", ["fintech"], ["data"], 74, "high", "Denver HQ with analytics and risk analyst roles.", "Search 'Analyst' and filter to Denver."),
            ("DaVita", "Denver, CO", "local", ["health"], ["data"], 76, "high", "Denver HQ; healthcare analytics teams hire SQL-first analysts.", "Search 'Data Analyst' on DaVita's careers site."),
            ("Arrow Electronics", "Centennial, CO", "local", ["other"], ["data"], 70, "medium", "Large Denver-area employer with supply-chain analytics roles.", "Search 'Analyst' on Arrow's careers site."),
        ],
    },
    "byu-accounting-it-audit": {
        "profile": {
            "name": "Camille Thorsby", "initials": "CT",
            "subline": "IT-audit and technology-risk roles for an April 2027 accounting graduate · Tailored to your resume",
            "status": "Senior · Grad Apr 2027", "recentRole": "KPMG — Technology Risk Intern, Salt Lake City (Summer 2026)",
            "stack": "Audit, SOX testing, Alteryx, ACL, Excel, information-systems minor, CPA-track",
            "target": "IT audit or technology-risk associate · Salt Lake City · Big Four or bank",
            "yearsExperience": 0, "uofu": False, "city": "Provo, UT", "geoLabel": "SLC Area", "cohortLabel": "Apr 2027 grad",
            "linkedin": "https://www.linkedin.com/in/camille-thorsby-byu",
            "summary": "An accounting degree with an IS minor and two Big Four internships is the exact profile the technology-assurance classes on this board recruit. You graduate in April, so programs that want a December 2026 finish are the wrong cohort; most summer/fall 2027 classes fit.",
            "searchLinks": [{"label": "IT audit associate, Salt Lake City", "keywords": "IT audit associate 2027", "location": "Salt Lake City, Utah", "remoteOnly": False, "entryLevel": True}],
            "applyNow": "Deloitte's Technology Controls Advisory, KPMG Technology Assurance, PwC's DAT Data class and Goldman's Internal Audit analyst seat are the live doors; Zions' GRC analyst is the local one.",
            "watchLater": "Wells Fargo's Audit Analyst Development Program reposts in the spring.",
        },
        "industry": {"fintech": 8, "data": 0, "ai-lab": -8, "health": -4, "cyber": 4, "other": 0},
        "roles": {"ml": -8, "swe": -6, "data": 4, "product": -2},
        "home": "salt lake city", "remap": False, "tools": set(),
        # programs written for a December 2026 finish are the wrong cohort for an April graduate
        "status": lambda c: "wrong-cohort" if c["name"] in ("Capital One", "Cicero Group (MGT)") else "keep",
        "suggested": [],
    },
    "bootcamp-remote": {
        "profile": {
            "name": "Tessa Marquardt", "initials": "TM",
            "subline": "Remote data-analyst roles for a bootcamp graduate · Tailored to your resume · Board assumes remote-only",
            "status": "Bootcamp grad · available now", "recentRole": "Sweetgrass Grill — General Manager, Dillon MT (2021–2026)",
            "stack": "Python, SQL, Power BI, Excel, forecasting projects, P&L management",
            "target": "Remote data or operations analyst · anywhere in the US",
            "yearsExperience": 0, "uofu": False, "city": "", "geoLabel": "Remote", "cohortLabel": "bootcamp graduate",
            "linkedin": "https://www.linkedin.com/in/tessa-marquardt-data",
            "summary": "With no degree and no office nearby, the realistic doors are remote analyst and operations roles that hire on portfolio and work history. The new-grad programs on this board want a bachelor's, so they are out; the remote roles and the suggested remote-first employers are the list.",
            "searchLinks": [{"label": "Remote data analyst", "keywords": "data analyst", "location": "", "remoteOnly": True, "entryLevel": True}],
            "applyNow": "Stripe's Fraud Patterns Analyst and CrowdStrike's Falcon Complete Analyst I are remote and do not name a degree; everything in Utah would mean moving.",
            "watchLater": "Keep building the portfolio; a Microsoft PL-300 certification would help with the Power BI roles.",
        },
        "industry": {"fintech": 2, "data": 4, "ai-lab": -10, "health": 0, "cyber": 2, "other": 0},
        "roles": {"ml": -8, "swe": -8, "data": 6, "product": 0},
        "home": None, "remap": True, "tools": {"data"},
        "status": lambda c: "keep",
        "suggested": [
            ("Automattic", "San Francisco, CA (remote)", "remote", ["other"], ["data", "product"], 78, "high", "Fully distributed company that hires on trial projects rather than degrees.", "Search 'Data' on automattic.com/work-with-us."),
            ("GitLab", "San Francisco, CA (remote)", "remote", ["other"], ["data"], 76, "high", "All-remote; its data team publishes its handbook and hires analysts.", "Look for 'Data Analyst' on GitLab's jobs page."),
            ("Toast", "Boston, MA (remote)", "remote", ["fintech"], ["data"], 80, "medium", "Restaurant-software company where a restaurant GM's experience is domain expertise.", "Search 'Analyst' and 'Remote'."),
            ("Zapier", "San Francisco, CA (remote)", "remote", ["other"], ["data"], 74, "medium", "Remote-first automation company with operations analyst roles.", "Search 'Operations' on Zapier's careers site."),
            ("Olo", "New York, NY (remote)", "remote", ["other"], ["data"], 72, "medium", "Restaurant ordering platform, remote-friendly.", "Search 'Analyst'."),
        ],
    },
    "experienced-de-slc": {
        "profile": {
            "name": "Bronwyn Castellanos", "initials": "BC",
            "subline": "Senior data-engineering roles for a five-year Snowflake and Spark engineer · Tailored to your resume",
            "status": "5 yrs · open to senior and lead", "recentRole": "Galileo Financial Technologies — Data Engineer II, Salt Lake City (2023–2026)",
            "stack": "Spark, Airflow, dbt, Snowflake, AWS, Python, Kafka, data modeling",
            "target": "Senior or lead data engineer · Salt Lake City · fintech or data tooling",
            "yearsExperience": 5, "uofu": True, "city": "Salt Lake City, UT", "geoLabel": "SLC Area", "cohortLabel": "five-year engineer",
            "linkedin": "https://www.linkedin.com/in/bronwyn-castellanos-data",
            "summary": "This is a new-grad board and you are five years past it: every program here is the wrong cohort, and the ordinary reqs that ask for two or three years are easily within reach. The useful signal is which Salt Lake employers have real data teams.",
            "searchLinks": [{"label": "Senior data engineer, Salt Lake City", "keywords": "senior data engineer", "location": "Salt Lake City, Utah", "remoteOnly": False, "entryLevel": False}],
            "applyNow": "Skip the programs. iCapital's and Fidelity's Salt Lake data roles, and Snowflake's and Databricks' experienced reqs, are where your resume lands.",
            "watchLater": "Nothing on this board is worth waiting for at your level; use the All Jobs buttons.",
        },
        "industry": {"fintech": 6, "data": 10, "ai-lab": 2, "health": 0, "cyber": -2, "other": 0},
        "roles": {"ml": 2, "swe": 4, "data": 10, "product": -2},
        "home": "salt lake city", "remap": False, "tools": {"data", "swe"},
        "status": lambda c: "wrong-cohort" if c["openings"] and all(o["program"] for o in c["openings"]) else "keep",
        "suggested": [],
    },
    # ---- other industries: for most of these the researched board is the wrong board ----
    "mech-engineer-logan": {
        "profile": {
            "name": "Caleb R. Hadfield", "initials": "CH",
            "subline": "Mechanical design and manufacturing engineering roles for a May 2027 graduate · Tailored to your resume · Board assumes your move to Salt Lake City",
            "status": "Senior · Grad May 2027", "recentRole": "Northrop Grumman — Mechanical Engineering Intern, Magna UT (Summer 2026)",
            "stack": "SolidWorks, ANSYS, GD&T, FE exam, MATLAB, design for manufacturing, senior design lead",
            "target": "Mechanical or manufacturing engineer · Wasatch Front · aerospace and defense",
            "yearsExperience": 0, "uofu": False, "city": "Salt Lake City, UT", "geoLabel": "SLC Area", "cohortLabel": "May 2027 grad",
            "linkedin": "https://www.linkedin.com/in/caleb-hadfield-me",
            "summary": "This board hires data, software and fintech people and your resume is a mechanical one, so the suggested aerospace, defense and manufacturing employers are the list that matters. Nothing on the researched board hires mechanical engineers.",
            "searchLinks": [{"label": "Mechanical engineer entry level, Salt Lake City", "keywords": "mechanical engineer entry level", "location": "Salt Lake City, Utah", "remoteOnly": False, "entryLevel": True}],
            "applyNow": "Start with the suggested employers: Northrop Grumman's and L3Harris's new-grad engineering intakes open in the fall, and Hill Air Force Base hires through USAJOBS year-round.",
            "watchLater": "Nothing on the researched board is worth waiting for in your field.",
        },
        "industry": {"fintech": -10, "data": -10, "ai-lab": -12, "health": -8, "cyber": -10, "other": -6},
        "roles": {"ml": -4, "swe": -4, "data": -4, "product": -2},
        "home": "salt lake city", "remap": False, "tools": set(),
        "status": lambda c: "keep",
        "suggested": "SUGGESTED_MECH",
    },
    "chemistry-lab-slc": {
        "profile": {
            "name": "Nadia Castellanos", "initials": "NC",
            "subline": "Laboratory scientist and research associate roles for a December 2026 chemistry graduate · Tailored to your resume",
            "status": "Senior · Grad Dec 2026", "recentRole": "ARUP Laboratories — Laboratory Assistant Intern, Salt Lake City (Summer 2026)",
            "stack": "HPLC, GC-MS, wet chemistry, LIMS, method validation, lab notebooks, Excel",
            "target": "Lab scientist or research associate · Salt Lake City · diagnostics or biotech",
            "yearsExperience": 0, "uofu": True, "city": "Salt Lake City, UT", "geoLabel": "SLC Area", "cohortLabel": "Dec 2026 grad",
            "linkedin": "https://www.linkedin.com/in/nadia-castellanos-chem",
            "summary": "You are a bench scientist, and this board is built for data and software hiring, so the suggested clinical labs, diagnostics companies and biotech firms in Salt Lake City are where your applications go. Recursion and Health Catalyst are the only researched employers in a neighbouring field.",
            "searchLinks": [{"label": "Laboratory scientist, Salt Lake City", "keywords": "laboratory scientist", "location": "Salt Lake City, Utah", "remoteOnly": False, "entryLevel": True}],
            "applyNow": "ARUP's and Myriad's lab-scientist postings take December graduates; apply before finals.",
            "watchLater": "Recursion's wet-lab research associate reqs post a few times a year.",
        },
        "industry": {"fintech": -10, "data": -10, "ai-lab": -8, "health": 4, "cyber": -12, "other": -6},
        "roles": {"ml": -4, "swe": -6, "data": -2, "product": -4},
        "home": "salt lake city", "remap": False, "tools": set(),
        "status": lambda c: "keep",
        "suggested": "SUGGESTED_CHEM",
    },
    "journalism-denver": {
        "profile": {
            "name": "Marisol Quintero-Hale", "initials": "MQ",
            "subline": "Reporter, producer and communications roles for a May 2026 journalism graduate · Tailored to your resume · Board re-mapped to Denver",
            "status": "BA Journalism · Grad May 2026", "recentRole": "Colorado Public Radio — Newsroom Intern (Spring 2026)",
            "stack": "Reporting, AP style, audio production, Datawrapper, FOIA requests, social video, spreadsheets",
            "target": "Reporter, producer or communications coordinator · Denver, CO",
            "yearsExperience": 0, "uofu": False, "city": "Denver, CO", "geoLabel": "Denver Area", "cohortLabel": "May 2026 grad",
            "linkedin": "https://www.linkedin.com/in/marisol-quintero-hale",
            "summary": "A newsroom resume on a data and software board: almost every researched employer is a mismatch, so the suggested Denver newsrooms, public media and communications teams are the real list. Utah employers read as a relocation you have not said you would make.",
            "searchLinks": [{"label": "Reporter, Denver", "keywords": "reporter", "location": "Denver, Colorado", "remoteOnly": False, "entryLevel": True},
                            {"label": "Communications coordinator, Denver", "keywords": "communications coordinator", "location": "Denver, Colorado", "remoteOnly": False, "entryLevel": True}],
            "applyNow": "The Denver Post and Colorado Public Radio post fellowships and associate producer roles each spring and fall; the communications teams at the suggested employers hire year-round.",
            "watchLater": "Nothing on the researched board is worth waiting for.",
        },
        "industry": {"fintech": -12, "data": -10, "ai-lab": -10, "health": -10, "cyber": -14, "other": -6},
        "roles": {"ml": -6, "swe": -6, "data": -4, "product": 0},
        "home": "denver", "remap": True, "tools": set(),
        "status": lambda c: "keep",
        "suggested": "SUGGESTED_JOUR",
    },
    "ux-designer-slc": {
        "profile": {
            "name": "Rowan Halverson", "initials": "RH",
            "subline": "Product and UX design roles for a December 2026 BFA graduate · Tailored to your resume",
            "status": "Senior · Grad Dec 2026", "recentRole": "Lehi SaaS company — Product Design Intern (Summer 2026)",
            "stack": "Figma, user research, prototyping, design systems, usability testing, HTML/CSS basics",
            "target": "Product or UX designer · Salt Lake City · SaaS",
            "yearsExperience": 0, "uofu": False, "city": "Ogden, UT", "geoLabel": "SLC Area", "cohortLabel": "Dec 2026 grad",
            "linkedin": "https://www.linkedin.com/in/rowan-halverson-ux",
            "summary": "A product designer is adjacent to this board rather than on it: the software companies here (Qualtrics, Lucid, Podium, BambooHR, Filevine) all employ designers, but their listed openings are data and analyst roles. The suggested Utah design employers fill the gap.",
            "searchLinks": [{"label": "Product designer, Salt Lake City", "keywords": "product designer", "location": "Salt Lake City, Utah", "remoteOnly": False, "entryLevel": True}],
            "applyNow": "Apply to the product-design openings at Lucid, Podium and Qualtrics directly from their careers pages; the listed analyst roles here are not for you.",
            "watchLater": "Design-intern-to-hire pipelines at the Lehi SaaS companies convert in the spring.",
        },
        "industry": {"fintech": -4, "data": 2, "ai-lab": -4, "health": -6, "cyber": -8, "other": 0},
        "roles": {"ml": -6, "swe": -2, "data": -4, "product": 12},
        "home": "salt lake city", "remap": False, "tools": {"product"},
        "status": lambda c: "keep",
        "suggested": "SUGGESTED_UX",
    },
    "marketing-analytics-boise": {
        "profile": {
            "name": "Brooke Lindqvist", "initials": "BL",
            "subline": "Marketing-analytics roles for a marketing coordinator with one year on the job · Tailored to your resume · Board re-mapped to Boise",
            "status": "1 yr · Marketing coordinator", "recentRole": "Boise credit union — Marketing Coordinator (2025–2026)",
            "stack": "HubSpot, Google Analytics, Excel, campaign reporting, SQL basics, copywriting",
            "target": "Marketing analyst · Boise, ID · remote or Salt Lake City welcome",
            "yearsExperience": 1, "uofu": False, "city": "Boise, ID", "geoLabel": "Boise Area", "cohortLabel": "early-career marketer",
            "linkedin": "https://www.linkedin.com/in/brooke-lindqvist-mktg",
            "summary": "Marketing analytics sits between this board's data roles and your marketing work: the analyst reqs that want SQL are a stretch, the ones that want campaign reporting are a fit. Boise employers and remote-friendly ones are added; Salt Lake roles read as a move you said you would consider.",
            "searchLinks": [{"label": "Marketing analyst, Boise", "keywords": "marketing analyst", "location": "Boise, Idaho", "remoteOnly": False, "entryLevel": True},
                            {"label": "Remote marketing analyst", "keywords": "marketing analyst", "location": "", "remoteOnly": True, "entryLevel": True}],
            "applyNow": "Stripe's and Datadog's GTM operations analyst roles are the board's closest fit; the suggested Boise employers are the local list.",
            "watchLater": "Qualtrics' Provo GTM analytics team hires again once the current req fills.",
        },
        "industry": {"fintech": 0, "data": 4, "ai-lab": -8, "health": -4, "cyber": -8, "other": 0},
        "roles": {"ml": -8, "swe": -8, "data": 4, "product": 2},
        "home": "boise", "remap": True, "tools": {"data"},
        "status": lambda c: "keep",
        "suggested": "SUGGESTED_MKT",
    },
    "civil-engineer-intl-phoenix": {
        "profile": {
            "name": "Nikhil Venkataraman", "initials": "NV",
            "subline": "Transportation and structural engineering roles for a May 2027 MS graduate who needs visa sponsorship · Tailored to your resume · Board re-mapped to Phoenix",
            "status": "MS Civil Engineering · Grad May 2027", "recentRole": "Phoenix engineering consultancy — Transportation Engineering Intern (Summer 2026)",
            "stack": "AutoCAD Civil 3D, transportation modelling, Python for traffic data, structural analysis, EIT",
            "target": "Transportation or structural engineer · Phoenix, AZ · needs H-1B sponsorship",
            "yearsExperience": 2, "uofu": False, "city": "Phoenix, AZ", "geoLabel": "Phoenix Area", "cohortLabel": "May 2027 master's grad",
            "linkedin": "https://www.linkedin.com/in/nikhil-venkataraman-civil",
            "summary": "A civil engineer on a software board: the researched employers are a mismatch, and several of their programs state no visa sponsorship, which rules them out twice over. The suggested Phoenix engineering consultancies and public agencies are the list, and your two years of practice before the master's count as experience.",
            "searchLinks": [{"label": "Transportation engineer EIT, Phoenix", "keywords": "transportation engineer EIT", "location": "Phoenix, Arizona", "remoteOnly": False, "entryLevel": True}],
            "applyNow": "The large consultancies (Kimley-Horn, HDR, AECOM) sponsor engineers routinely; apply to their Phoenix EIT postings first.",
            "watchLater": "ADOT and the City of Phoenix post engineer-in-training roles but rarely sponsor.",
        },
        "industry": {"fintech": -12, "data": -8, "ai-lab": -10, "health": -10, "cyber": -12, "other": -6},
        "roles": {"ml": -4, "swe": -4, "data": -2, "product": -4},
        "home": "phoenix", "remap": True, "tools": set(),
        # programs that say no visa sponsorship are the wrong cohort for an F-1 student
        "status": lambda c: "wrong-cohort" if c["name"] in ("Vanguard", "Mastercard", "Fidelity Investments", "Capital One") else "keep",
        "suggested": "SUGGESTED_CIVIL",
    },
}

SLC_TOWNS = ("salt lake city", "lehi", "provo", "orem", "south jordan", "draper", "midvale", "sandy", "riverdale", "ogden", "american fork", "lindon", "pleasant grove", "cottonwood heights", "silicon slopes")

def loc_type_for(persona, c):
    """The company's location relative to the candidate. 'keep' when the board stays Salt Lake-relative."""
    if not persona["remap"]: return "keep"
    base = c["locType"]
    if base == "remote": return "remote"
    city = city_of(c["location"])
    if persona["home"] is None: return "remote" if base == "remote" else "far"
    if persona["home"] in city: return "local"
    if persona["home"] in c["location"].lower(): return "hybrid"
    return "far"

def score_for(persona, c, loc_type):
    s = 68 + spread(c["name"], -6, 6)
    s += sum(persona["industry"].get(i, 0) for i in c["industry"]) // max(1, len(c["industry"]))
    s += sum(persona["roles"].get(r, 0) for r in c["roles"]) // max(1, len(c["roles"]))
    eff = c["locType"] if loc_type == "keep" else loc_type
    s += {"local": 8, "hybrid": 5, "remote": 2, "far": -6}.get(eff, 0)
    if c["status"] == "open-now": s += 4
    elif c["status"] == "watch": s -= 3
    return max(60, min(100, s))

# Suggested employers for the other-industry personas, taken from each fictional resume's own field and city.
# Real companies; the one-line descriptions and notes are fabricated for testing.
SUGGESTED = {
    "SUGGESTED_MECH": [
        ("Northrop Grumman", "Salt Lake City, UT", "local", ["other"], [], 90, "high", "Synthetic fixture: a aerospace, defense or manufacturing employer along the Wasatch Front.", "Search \"mechanical engineer\" and \"new grad\" on their careers site."),
        ("L3Harris Technologies", "Salt Lake City, UT", "local", ["other"], [], 87, "high", "Synthetic fixture: a aerospace, defense or manufacturing employer along the Wasatch Front.", "Search \"mechanical engineer\" and \"new grad\" on their careers site."),
        ("Space Dynamics Laboratory", "Salt Lake City, UT", "local", ["other"], [], 84, "high", "Synthetic fixture: a aerospace, defense or manufacturing employer along the Wasatch Front.", "Search \"mechanical engineer\" and \"new grad\" on their careers site."),
        ("Hill Air Force Base (Ogden Air Logistics Complex)", "Salt Lake City, UT", "local", ["other"], [], 81, "high", "Synthetic fixture: a aerospace, defense or manufacturing employer along the Wasatch Front.", "Search \"mechanical engineer\" and \"new grad\" on their careers site."),
        ("Boeing Salt Lake City", "Salt Lake City, UT", "local", ["other"], [], 78, "medium", "Synthetic fixture: a aerospace, defense or manufacturing employer along the Wasatch Front.", "Search \"mechanical engineer\" and \"new grad\" on their careers site."),
        ("Hexcel", "Salt Lake City, UT", "local", ["other"], [], 75, "medium", "Synthetic fixture: a aerospace, defense or manufacturing employer along the Wasatch Front.", "Search \"mechanical engineer\" and \"new grad\" on their careers site."),
        ("Williams International", "Salt Lake City, UT", "local", ["other"], [], 72, "medium", "Synthetic fixture: a aerospace, defense or manufacturing employer along the Wasatch Front.", "Search \"mechanical engineer\" and \"new grad\" on their careers site."),
        ("Parker Hannifin Aerospace", "Salt Lake City, UT", "local", ["other"], [], 69, "medium", "Synthetic fixture: a aerospace, defense or manufacturing employer along the Wasatch Front.", "Search \"mechanical engineer\" and \"new grad\" on their careers site."),
        ("Albany Engineered Composites", "Salt Lake City, UT", "local", ["other"], [], 66, "medium", "Synthetic fixture: a aerospace, defense or manufacturing employer along the Wasatch Front.", "Search \"mechanical engineer\" and \"new grad\" on their careers site."),
        ("Autoliv", "Salt Lake City, UT", "local", ["other"], [], 63, "medium", "Synthetic fixture: a aerospace, defense or manufacturing employer along the Wasatch Front.", "Search \"mechanical engineer\" and \"new grad\" on their careers site."),
    ],
    "SUGGESTED_CHEM": [
        ("ARUP Laboratories", "Salt Lake City, UT", "local", ["health"], [], 90, "high", "Synthetic fixture: a clinical laboratory, diagnostics or biotech employer in Salt Lake City.", "Search \"laboratory scientist\", \"research associate\" and \"lab technician\"."),
        ("Myriad Genetics", "Salt Lake City, UT", "local", ["health"], [], 87, "high", "Synthetic fixture: a clinical laboratory, diagnostics or biotech employer in Salt Lake City.", "Search \"laboratory scientist\", \"research associate\" and \"lab technician\"."),
        ("BioFire Diagnostics (bioMerieux)", "Salt Lake City, UT", "local", ["health"], [], 84, "high", "Synthetic fixture: a clinical laboratory, diagnostics or biotech employer in Salt Lake City.", "Search \"laboratory scientist\", \"research associate\" and \"lab technician\"."),
        ("Nelson Laboratories (Sotera Health)", "Salt Lake City, UT", "local", ["health"], [], 81, "high", "Synthetic fixture: a clinical laboratory, diagnostics or biotech employer in Salt Lake City.", "Search \"laboratory scientist\", \"research associate\" and \"lab technician\"."),
        ("USANA Health Sciences", "Salt Lake City, UT", "local", ["health"], [], 78, "medium", "Synthetic fixture: a clinical laboratory, diagnostics or biotech employer in Salt Lake City.", "Search \"laboratory scientist\", \"research associate\" and \"lab technician\"."),
        ("Intermountain Health Central Laboratory", "Salt Lake City, UT", "local", ["health"], [], 75, "medium", "Synthetic fixture: a clinical laboratory, diagnostics or biotech employer in Salt Lake City.", "Search \"laboratory scientist\", \"research associate\" and \"lab technician\"."),
        ("University of Utah Health / Huntsman Cancer Institute", "Salt Lake City, UT", "local", ["health"], [], 72, "medium", "Synthetic fixture: a clinical laboratory, diagnostics or biotech employer in Salt Lake City.", "Search \"laboratory scientist\", \"research associate\" and \"lab technician\"."),
        ("Chemtech-Ford Laboratories", "Salt Lake City, UT", "local", ["health"], [], 69, "medium", "Synthetic fixture: a clinical laboratory, diagnostics or biotech employer in Salt Lake City.", "Search \"laboratory scientist\", \"research associate\" and \"lab technician\"."),
        ("Utah Public Health Laboratory", "Salt Lake City, UT", "local", ["health"], [], 66, "medium", "Synthetic fixture: a clinical laboratory, diagnostics or biotech employer in Salt Lake City.", "Search \"laboratory scientist\", \"research associate\" and \"lab technician\"."),
        ("Merit Medical Systems", "Salt Lake City, UT", "local", ["health"], [], 63, "medium", "Synthetic fixture: a clinical laboratory, diagnostics or biotech employer in Salt Lake City.", "Search \"laboratory scientist\", \"research associate\" and \"lab technician\"."),
    ],
    "SUGGESTED_JOUR": [
        ("The Denver Post", "Denver, CO", "local", ["other"], [], 90, "high", "Synthetic fixture: a newsroom, public-media or communications employer in Denver.", "Search \"reporter\", \"producer\" and \"communications coordinator\"."),
        ("Colorado Public Radio (CPR News)", "Denver, CO", "local", ["other"], [], 87, "high", "Synthetic fixture: a newsroom, public-media or communications employer in Denver.", "Search \"reporter\", \"producer\" and \"communications coordinator\"."),
        ("The Colorado Sun", "Denver, CO", "local", ["other"], [], 84, "high", "Synthetic fixture: a newsroom, public-media or communications employer in Denver.", "Search \"reporter\", \"producer\" and \"communications coordinator\"."),
        ("9NEWS (KUSA)", "Denver, CO", "local", ["other"], [], 81, "high", "Synthetic fixture: a newsroom, public-media or communications employer in Denver.", "Search \"reporter\", \"producer\" and \"communications coordinator\"."),
        ("Denver7 (KMGH)", "Denver, CO", "local", ["other"], [], 78, "medium", "Synthetic fixture: a newsroom, public-media or communications employer in Denver.", "Search \"reporter\", \"producer\" and \"communications coordinator\"."),
        ("Rocky Mountain PBS", "Denver, CO", "local", ["other"], [], 75, "medium", "Synthetic fixture: a newsroom, public-media or communications employer in Denver.", "Search \"reporter\", \"producer\" and \"communications coordinator\"."),
        ("Denverite", "Denver, CO", "local", ["other"], [], 72, "medium", "Synthetic fixture: a newsroom, public-media or communications employer in Denver.", "Search \"reporter\", \"producer\" and \"communications coordinator\"."),
        ("Westword", "Denver, CO", "local", ["other"], [], 69, "medium", "Synthetic fixture: a newsroom, public-media or communications employer in Denver.", "Search \"reporter\", \"producer\" and \"communications coordinator\"."),
        ("Axios Denver", "Denver, CO", "local", ["other"], [], 66, "medium", "Synthetic fixture: a newsroom, public-media or communications employer in Denver.", "Search \"reporter\", \"producer\" and \"communications coordinator\"."),
        ("Denver Business Journal", "Denver, CO", "local", ["other"], [], 63, "medium", "Synthetic fixture: a newsroom, public-media or communications employer in Denver.", "Search \"reporter\", \"producer\" and \"communications coordinator\"."),
    ],
    "SUGGESTED_UX": [
        ("O.C. Tanner", "Ogden, UT", "local", ["data"], ["product"], 90, "high", "Synthetic fixture: a Utah software company with a product-design team.", "Search \"product designer\" and \"UX designer\"."),
        ("Underbelly", "Ogden, UT", "local", ["data"], ["product"], 87, "high", "Synthetic fixture: a Utah software company with a product-design team.", "Search \"product designer\" and \"UX designer\"."),
        ("BILL (Divvy)", "Ogden, UT", "local", ["data"], ["product"], 84, "high", "Synthetic fixture: a Utah software company with a product-design team.", "Search \"product designer\" and \"UX designer\"."),
        ("Traeger", "Ogden, UT", "local", ["data"], ["product"], 81, "high", "Synthetic fixture: a Utah software company with a product-design team.", "Search \"product designer\" and \"UX designer\"."),
        ("Owlet", "Ogden, UT", "local", ["data"], ["product"], 78, "medium", "Synthetic fixture: a Utah software company with a product-design team.", "Search \"product designer\" and \"UX designer\"."),
        ("Canopy", "Ogden, UT", "local", ["data"], ["product"], 75, "medium", "Synthetic fixture: a Utah software company with a product-design team.", "Search \"product designer\" and \"UX designer\"."),
        ("Struck", "Ogden, UT", "local", ["data"], ["product"], 72, "medium", "Synthetic fixture: a Utah software company with a product-design team.", "Search \"product designer\" and \"UX designer\"."),
        ("Super Top Secret", "Ogden, UT", "local", ["data"], ["product"], 69, "medium", "Synthetic fixture: a Utah software company with a product-design team.", "Search \"product designer\" and \"UX designer\"."),
        ("Cotopaxi", "Ogden, UT", "local", ["data"], ["product"], 66, "medium", "Synthetic fixture: a Utah software company with a product-design team.", "Search \"product designer\" and \"UX designer\"."),
        ("Clearlink", "Ogden, UT", "local", ["data"], ["product"], 63, "medium", "Synthetic fixture: a Utah software company with a product-design team.", "Search \"product designer\" and \"UX designer\"."),
    ],
    "SUGGESTED_MKT": [
        ("Albertsons Companies", "Boise, ID", "local", ["other"], ["data"], 90, "high", "Synthetic fixture: a Boise or remote-friendly employer with a marketing-analytics team.", "Search \"marketing analyst\" and \"marketing operations\"."),
        ("Scentsy", "Boise, ID", "local", ["other"], ["data"], 87, "high", "Synthetic fixture: a Boise or remote-friendly employer with a marketing-analytics team.", "Search \"marketing analyst\" and \"marketing operations\"."),
        ("Clearwater Analytics", "Boise, ID", "local", ["other"], ["data"], 84, "high", "Synthetic fixture: a Boise or remote-friendly employer with a marketing-analytics team.", "Search \"marketing analyst\" and \"marketing operations\"."),
        ("Idaho Central Credit Union", "Boise, ID", "local", ["other"], ["data"], 81, "high", "Synthetic fixture: a Boise or remote-friendly employer with a marketing-analytics team.", "Search \"marketing analyst\" and \"marketing operations\"."),
        ("Blue Cross of Idaho", "Boise, ID", "local", ["other"], ["data"], 78, "medium", "Synthetic fixture: a Boise or remote-friendly employer with a marketing-analytics team.", "Search \"marketing analyst\" and \"marketing operations\"."),
        ("St. Luke's Health System", "Boise, ID", "local", ["other"], ["data"], 75, "medium", "Synthetic fixture: a Boise or remote-friendly employer with a marketing-analytics team.", "Search \"marketing analyst\" and \"marketing operations\"."),
        ("J.R. Simplot Company", "Boise, ID", "local", ["other"], ["data"], 72, "medium", "Synthetic fixture: a Boise or remote-friendly employer with a marketing-analytics team.", "Search \"marketing analyst\" and \"marketing operations\"."),
        ("Drake Cooper", "Boise, ID", "local", ["other"], ["data"], 69, "medium", "Synthetic fixture: a Boise or remote-friendly employer with a marketing-analytics team.", "Search \"marketing analyst\" and \"marketing operations\"."),
        ("Micron Technology", "Boise, ID", "local", ["other"], ["data"], 66, "medium", "Synthetic fixture: a Boise or remote-friendly employer with a marketing-analytics team.", "Search \"marketing analyst\" and \"marketing operations\"."),
        ("Boise Cascade", "Boise, ID", "local", ["other"], ["data"], 63, "medium", "Synthetic fixture: a Boise or remote-friendly employer with a marketing-analytics team.", "Search \"marketing analyst\" and \"marketing operations\"."),
    ],
    "SUGGESTED_CIVIL": [
        ("Kimley-Horn", "Phoenix, AZ", "local", ["other"], [], 90, "high", "Synthetic fixture: a engineering consultancy or public agency in Phoenix.", "Search \"EIT\", \"transportation engineer\" and \"structural engineer\"."),
        ("HDR", "Phoenix, AZ", "local", ["other"], [], 87, "high", "Synthetic fixture: a engineering consultancy or public agency in Phoenix.", "Search \"EIT\", \"transportation engineer\" and \"structural engineer\"."),
        ("AECOM", "Phoenix, AZ", "local", ["other"], [], 84, "high", "Synthetic fixture: a engineering consultancy or public agency in Phoenix.", "Search \"EIT\", \"transportation engineer\" and \"structural engineer\"."),
        ("Jacobs", "Phoenix, AZ", "local", ["other"], [], 81, "high", "Synthetic fixture: a engineering consultancy or public agency in Phoenix.", "Search \"EIT\", \"transportation engineer\" and \"structural engineer\"."),
        ("WSP", "Phoenix, AZ", "local", ["other"], [], 78, "medium", "Synthetic fixture: a engineering consultancy or public agency in Phoenix.", "Search \"EIT\", \"transportation engineer\" and \"structural engineer\"."),
        ("Stantec", "Phoenix, AZ", "local", ["other"], [], 75, "medium", "Synthetic fixture: a engineering consultancy or public agency in Phoenix.", "Search \"EIT\", \"transportation engineer\" and \"structural engineer\"."),
        ("Dibble", "Phoenix, AZ", "local", ["other"], [], 72, "medium", "Synthetic fixture: a engineering consultancy or public agency in Phoenix.", "Search \"EIT\", \"transportation engineer\" and \"structural engineer\"."),
        ("Arizona Department of Transportation", "Phoenix, AZ", "local", ["other"], [], 69, "medium", "Synthetic fixture: a engineering consultancy or public agency in Phoenix.", "Search \"EIT\", \"transportation engineer\" and \"structural engineer\"."),
        ("City of Phoenix Street Transportation Department", "Phoenix, AZ", "local", ["other"], [], 66, "medium", "Synthetic fixture: a engineering consultancy or public agency in Phoenix.", "Search \"EIT\", \"transportation engineer\" and \"structural engineer\"."),
        ("Maricopa County Department of Transportation", "Phoenix, AZ", "local", ["other"], [], 63, "medium", "Synthetic fixture: a engineering consultancy or public agency in Phoenix.", "Search \"EIT\", \"transportation engineer\" and \"structural engineer\"."),
    ],
}

def set_suggested(persona):
    v = persona["suggested"]
    if isinstance(v, str): persona["suggested"] = SUGGESTED.get(v, [])

def build(key, persona, board):
    set_suggested(persona)
    companies = []
    for c in board:
        lt = loc_type_for(persona, c)
        tools = bool(persona["tools"] & set(c["roles"]))
        companies.append({"name": c["name"], "score": score_for(persona, c, lt), "toolsMatch": tools,
                          "status": persona["status"](c), "locType": lt, "note": "",
                          "why": f"**Synthetic fixture.** A made-up fit explanation for {persona['profile']['name'].split()[0]} at {c['name']}: {c['industry'][0] if c['industry'] else 'other'} employer, {'local to' if lt in ('local','hybrid','keep') and c['locType'] in ('local','hybrid') else 'away from'} the candidate."})
    suggested = [{"name": n, "location": loc, "locType": lt, "industry": ind, "roles": roles, "score": sc,
                  "badges": (["fintech"] if "fintech" in ind else []) + (["tools-match"] if roles and persona["tools"] & set(roles) else []),
                  "why": why, "note": note, "confidence": conf}
                 for (n, loc, lt, ind, roles, sc, conf, why, note) in persona["suggested"]]
    return {"profile": persona["profile"], "companies": companies, "suggested": suggested}

def hostile(board):
    """Everything the page must survive: unknown and duplicate names, out-of-range scores, bad enums,
    a suggestion that is really a board company, too many suggestions, over-long strings."""
    base = build("hostile", PERSONAS["byu-accounting-it-audit"], board)
    rows = base["companies"]
    rows[0] = dict(rows[0], score=140)                      # clamps to 100
    rows[1] = dict(rows[1], score=10)                       # clamps to 60
    rows[2] = dict(rows[2], status="hired", locType="moon") # unknown enums -> keep
    rows.append(dict(rows[3]))                              # duplicate -> ignored
    rows.append(dict(rows[4], name="Totally Fake Corp"))   # unknown -> ignored
    rows.append(dict(rows[5], name=rows[5]["name"].upper() + "  "))  # loose name match
    sug = base["suggested"] = []
    sug.append({"name": "Zions Bank", "location": "Salt Lake City, UT", "locType": "local", "industry": ["fintech"], "roles": ["data"], "score": 99, "badges": ["fintech"], "why": "a board company in disguise", "note": "must be dropped", "confidence": "high"})
    for i in range(24):
        sug.append({"name": f"Synthetic Employer {i:02d} " + "x" * 100, "location": "Provo, UT", "locType": "local", "industry": ["other"], "roles": [], "score": 61 + i, "badges": ["gold"], "why": "filler", "note": "filler", "confidence": "low"})
    base["profile"] = dict(base["profile"], name="  Hostile   Output  ", initials="hostile", linkedin="javascript:alert(1)", yearsExperience=-3)
    return base

def too_few(board):
    """Below the 80% rule: the page must reject it."""
    base = build("too-few", PERSONAS["austin-cs-ms"], board)
    base["companies"] = base["companies"][: int(len(board) * 0.7)]
    return base

def partial(board):
    """A profile made before the two newest employers existed: they must be hidden, not shown with the owner's text."""
    base = build("partial", PERSONAS["nurse-slc"], board)
    base["companies"] = [r for r in base["companies"] if r["name"] not in ("Sunwest Bank", "Datafy")]
    return base

if __name__ == "__main__":
    board = read_board()
    os.makedirs(OUT, exist_ok=True)
    written = []
    for key, persona in PERSONAS.items():
        path = os.path.join(OUT, f"{key}.json")
        json.dump(build(key, persona, board), open(path, "w"), indent=1, ensure_ascii=False)
        written.append(path)
    for key, fn in (("hostile-output", hostile), ("too-few-companies", too_few), ("profile-predates-employers", partial)):
        path = os.path.join(OUT, f"{key}.json")
        json.dump(fn(board), open(path, "w"), indent=1, ensure_ascii=False)
        written.append(path)
    print(f"{len(board)} employers on the board; wrote {len(written)} cases to samples/cases/")
