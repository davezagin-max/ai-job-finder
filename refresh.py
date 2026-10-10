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
import io, json, os, re, subprocess, sys, time, datetime, threading, concurrent.futures, urllib.parse, hashlib
from html import unescape as html_unescape

HERE  = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(HERE, "index.html")
STATE = os.path.join(HERE, ".refresh-state.json")
REPORT= os.path.join(HERE, "refresh-report.txt")
READERS_DIR = os.path.join(HERE, "readers")   # one small file per further hiring system (see load_readers)
DB    = os.path.join(HERE, "jobs.db")       # every row every feed has returned, with its history (git-ignored)
EXPORT= os.path.join(HERE, "jobs.json")     # the live entry-level rows, published for the page's All openings view
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
  # ADP WorkforceNow: the value is the career-center id (cid) in the employer's recruitment.html link
  "adp":     {"Sunwest Bank":"f9e1fc49-57c2-48ad-998b-5652b70d3889"},
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
  # iCIMS portals, read by readers/icims_search.py from the search page, which names each job's place.
  # (The built-in "icims" kind reads the sitemap instead: titles and links, no places, so its slug is
  # "host|location to assume". It is kept for a portal whose search page cannot be read.)
  "icims_search": {"Cotiviti":"careers-cotiviti.icims.com", "America First Credit Union":"careers-americafirst.icims.com"},
  "successfactors": {"Vivint Smart Home":"careers.nrgenergy.com|SMARTHOMES"},
  "jazzhr":     {"Cicero Group (MGT)":"cicero"},
  "selectminds":{"Zions Bancorporation":"growwithzions.zionsbancorp.com"},
  "eightfold":  {"Morgan Stanley":"morganstanley.eightfold.ai|morganstanley.com|@Utah, United States;2027@United States"},
  "oleeo":      {"Morgan Stanley (campus programs)":"https://morganstanley.tal.net/vx/lang-en-GB/mobile-0/brand-2/candidate/jobboard/vacancy/1/adv/?f_Item_Opportunity_17058_lk=133175"},
  "bamboohr":{"SecurityMetrics":"securitymetrics"},
  "avature":{"Bloomberg":"bloomberg.avature.net/careers"},
  # DirectEmployers career sites, read through the search service their own pages call. The value is the
  # site's host. The University of Utah is the largest employer in Salt Lake City and was missing from this
  # script until October 2026: its 1,300 postings, University of Utah Health included, are all on this site.
  "directemployers": {"University of Utah":"employment.utah.edu"},
}
# Employers read for the job database only: they have no hand-written card on the board, but every
# entry-level role they post lands in jobs.json and the page's All openings view. Same kinds and slug
# formats as BOARDS. Add an employer here the moment you find a job this script could not see
# (python3 refresh.py --why "job title" says why a job was missed).
MORE = {
  "greenhouse": {
    "1-800 Contacts":"1800contacts", "AdvancedMD":"advancedmd", "Awardco":"awardco", "BILL (Divvy)":"billcom",
    "Brevium":"brevium", "Canopy":"canopytax", "Carta":"carta", "Clearlink":"clearlinktechnologiesllc",
    "Cottonwood Residential":"cottonwoodresidential", "Degreed":"degreed", "JobNimbus":"jobnimbus",
    "MasterControl":"mastercontrol", "NICE":"nice", "Rocket Lawyer":"rocketlawyer", "Route":"route",
    "TaxBit":"taxbit", "Traeger":"traegergrills", "Twilio":"twilio",
  },
  "lever": {
    "Backcountry (CSC Generation)":"cscgeneration-2", "BrainStorm":"brainstorminc", "Clozd":"Clozd",
    "Crumbl":"crumbl", "Gabb":"gabbwireless", "Neighbor":"neighbor", "Nomi Health":"nomihealth",
    "PointClickCare (Collective Medical)":"pointclickcare", "RainFocus":"rainfocus",
  },
  "ashby": {
    "Jump":"jump-app", "Leavitt Group":"leavitt", "Limble":"limble",
    "LiveView Technologies (LVT)":"liveview-technologies", "Strider Technologies":"strider-technologies",
    "Tava Health":"tavahealth", "Thumbtack":"thumbtack",
  },
  "workable": {
    "Boostability":"boostability-1", "Celtic Bank":"celtic-bank", "KIHOMAC":"kihomac", "Owlet":"owlet-baby-care-1",
    "Vasion (PrinterLogic)":"vasion",
  },
  "bamboohr": {
    "Draper City":"drapercity", "Kiln":"kiln", "Medallion Bank":"medallionbank", "Mojo AI":"safetymojo",
    "ObservePoint":"observepoint", "Remi":"remi", "Revere Health":"reverehealth", "UAMPS":"uamps",
  },
  "jazzhr": {
    "Henry Schein One":"henryscheinone", "Malouf":"maloufsleep", "Pura":"pura",
    "Space Dynamics Laboratory":"spacedynamicslaboratory", "Tanner LLC":"tannerllc",
    "The Buckner Company":"thebucknercompany",
  },
  "adp": {
    "Alianza":"b9308c6a-f674-4974-a737-404060e6c39b", "KLAS Research":"a670083c-06c1-4384-81c6-516aa161864a",
    "Squire & Company":"ec3aaeb0-4105-4821-8351-4ab5d56d0067",
    "Westminster University":"8b104a38-45ac-4682-9e01-117585322eb0",
  },
  "workday": {
    "Acima (Upbound)":"upbound|wd501|Acima", "Ally Financial":"ally|wd1|Ally",
    "Alterra Mountain Company":"alterra|wd1|AlterraMountainCompany",
    "Amentum":"pae|wd1|amentum_careers|Ogden;Salt Lake City;Hill AFB", "Aptive Environmental":"aptive|wd1|Aptive",
    "Baker Tilly":"bakertilly|wd5|BTCareers|Salt Lake City;Lehi;Utah",
    "Bank of America":"ghr|wd1|Lateral-US|Utah;Salt Lake City;Lehi;Ogden;Draper",
    "BD (Becton Dickinson)":"bdx|wd1|EXTERNAL_CAREER_SITE_USA|Utah",
    "Better Being Co.":"nutraceutical|wd501|BetterBeingExternalCareerSite",
    "Beyond (Overstock)":"overstock|wd5|BedBathandBeyond_Careers", "Boeing":"boeing|wd1|EXTERNAL_CAREERS|Utah",
    "Boncom":"deseretmanagement|wd1|Boncom", "Bonneville Salt Lake (KSL)":"deseretmanagement|wd1|BonSaltLake",
    "Booz Allen Hamilton":"bah|wd1|BAH_Jobs|Utah;Hill AFB;Clearfield",
    "Bread Financial":"alliancedata|wd5|ComenityBanks", "Breeze Airways":"flybreeze|wd503|Breeze_Airways",
    "Bridge Investment Group":"bridgeigp|wd1|BIGC", "Brigham Young University":"byu|wd1|byu-careers",
    "CACI":"caci|wd1|External|Hill AFB;Bluffdale;Draper;Salt Lake City;Utah",
    "Cambia Health Solutions (Regence)":"cambiahealth|wd504|External",
    "Capital One (Salt Lake City)":"capitalone|wd12|Capital_One|Salt Lake City;Utah",
    "CHG Healthcare":"chghealthcare|wd1|External", "Cisco":"cisco|wd5|Cisco_Careers|Utah;Salt Lake City",
    "CLA (CliftonLarsonAllen)":"cliftonlarsonallen|wd115|CLA|Salt Lake City;Utah",
    "Concentrix":"cnx|wd1|external_global|USA Work at Home",
    "Cox Automotive":"cox|wd1|Cox_External_Career_Site_1|Draper;Utah",
    "Cushman & Wakefield":"cw|wd1|External|Salt Lake City;Utah",
    "CVS Health (Aetna)":"cvshealth|wd1|CVS_Health_Careers|Utah", "Cytiva (Danaher)":"danaher|wd1|DanaherJobs|Utah",
    "Deer Valley Resort":"alterra|wd1|DeerValleyResort", "Deseret Book":"deseretmanagement|wd1|DeseretBook",
    "Deseret Digital Media (KSL.com)":"deseretmanagement|wd1|DeseretDigitalMedia",
    "Deseret News":"deseretmanagement|wd1|DeseretNews", "doTERRA":"doterra|wd1|doTERRACareers",
    "eBay":"ebay|wd5|apply|Utah;Salt Lake City", "Edwards Lifesciences":"edwards|wd5|EdwardsCareers|Utah",
    "Enbridge Gas Utah":"enbridge|wd3|enbridge_careers",
    "Ensign College":"ensigncollege|wd501.myworkdaysite.com|EnsignCollege",
    "Epicor (Grow.com)":"epicorsoftware|wd5|epicorjobs",
    "Extra Space Storage":"extraspace|wd5|ESS_External|Salt Lake City;Utah", "F5":"ffive|wd5|f5jobs|Utah",
    "Fresenius Medical Care":"freseniusmedicalcare|wd3|fme|Utah",
    "GE HealthCare":"gehc|wd5|GEHC_ExternalSite|Salt Lake City;Utah",
    "General Dynamics Information Technology (GDIT)":"gdit|wd5|External_Career_Site|Utah",
    "Hexcel":"hexcel|wd5|HexcelCareers", "Highmark Health":"highmarkhealth|wd1|highmark|Utah;Remote",
    "InMoment (Press Ganey)":"pressganey|wd1|Careers",
    "Intermountain Health":"imh|wd108|IntermountainCareers||locationRegionStateProvince=9bf006cfb5a44c51b84138e1a0e7d805",
    "JLL":"jll|wd1|jllcareers|Salt Lake City;Provo;Utah", "KBR":"kbr|wd5|KBR_Careers|Utah",
    "Ken Garff Automotive Group":"kengarff|wd1|external_site",
    "KeyBank":"keybank|wd5|External_Career_Site|Utah;Salt Lake City", "Kimberly-Clark":"kimberlyclark|wd1|GLOBAL",
    "Leidos":"leidos|wd5|External|Utah", "LendingClub":"lendingclub|wd1|External", "Lendio":"lendio|wd1|lendio",
    "Marathon Petroleum":"mpc|wd1|MPCCareers", "MarketStar":"wasatchproperty|wd1|MarketStarCareers",
    "Marsh McLennan":"mmc|wd1|MMC|Salt Lake City;Utah", "Merit Medical Systems":"merit|wd503|Merit",
    "Merrick Bank":"cardworks|wd12|Merrick_Bank_External", "Moog":"moog|wd5|MOOG_External_Career_Site",
    "Motorola Solutions":"motorolasolutions|wd5|Careers|Utah;Salt Lake City",
    "Mountain America Credit Union":"macu|wd5|MACU_Careers", "Nelnet":"nelnet|wd1|MyNelnet",
    "Nelson Labs (Sotera Health)":"soterahealth|wd501|External",
    "Newfold Digital (Bluehost)":"web|wd1|ExternalCareerSite",
    "Northrop Grumman":"ngc|wd1|Northrop_Grumman_External_Site|Utah-Roy;Clearfield;Corinne;Layton;Magna;Ogden;Salt Lake City;Hill AFB",
    "Nu Skin Enterprises":"nuskin|wd5|nuskin", "NVIDIA":"nvidia|wd5|NVIDIAExternalCareerSite|Utah;Salt Lake City",
    "O.C. Tanner":"octanner|wd501|O_C_Tanner", "Orion Advisor Solutions":"orionadvisor|wd1|Orion_Careers",
    "Packsize":"packsize|wd108|Packsize_Careers", "PayPal":"paypal|wd1|jobs",
    "PROG Holdings (Progressive Leasing)":"progleasing|wd5|progleasingcareers",
    "Provo City":"provo|wd1|ProvoCityExternalCareerSite", "Purple":"purple|wd1|purplecareers",
    "R1 RCM":"r1rcm|wd1|R1RCM|Utah", "Regions Bank":"regions|wd5|Regions_Careers|Salt Lake City;Utah",
    "Rio Tinto Kennecott":"riotinto|wd3.myworkdaysite.com|RioTinto_Careers",
    "RSM US":"rsm|wd1|RSMCareers|Salt Lake City;Utah",
    "RTX (Collins Aerospace)":"globalhr|wd5|REC_RTX_Ext_Gateway|West Valley City;Salt Lake City",
    "Sallie Mae":"sallie_mae|sallie-mae.wd5.myworkdayjobs.com|Careers", "Salt Lake City Corporation":"slcgov|wd1|SLC",
    "Sandy City":"sandy|wd12|Sandy_City", "Sedgwick":"sedgwick|wd1|Sedgwick|Salt Lake City;Utah",
    "Snap Finance":"snapfinance|wd1|Snap_External_Careers",
    "Solitude Mountain Resort":"alterra|wd1|SolitudeMountainResort", "Solventum":"healthcare|wd1|Search|Utah;Murray",
    "Stryker":"stryker|wd1|StrykerCareers|Utah", "Synchrony":"synchronyfinancial|wd5|careers",
    "T.D. Williamson":"tdwilliamson|wd1|TDWCareers", "Tempus AI":"tempus|wd5|Tempus_Careers",
    "Thermo Fisher Scientific":"thermofisher|wd5|ThermoFisherCareers|Utah",
    "U.S. Bank":"usbank|wd1|US_Bank_Careers|Utah;Salt Lake City", "Ultradent Products":"ultradent|wd1|careers",
    "Unisys":"unisys|wd5|External|Utah;Salt Lake City", "Utah County Government":"utahcounty|wd1|Utah_County_Careers",
    "Varex Imaging":"vareximaging|wd103|External_Career_Site", "Waystar":"waystar|wd1|Waystar",
    "WB Games Avalanche":"warnerbros|wd5|global|Salt Lake City;Utah",
    "WCF Insurance":"osv_wcf|osv-wcf.wd501.myworkdayjobs.com|External",
    "Wells Fargo (Utah)":"wf|wd1.myworkdaysite.com|WellsFargoJobs|Salt Lake City;Utah",
    "West Jordan City":"westjordan|wd108|WestJordan", "WEX":"wexinc|wd5|WEXInc",
    "Williams Companies":"williams|wd5|External", "Workday":"workday|wd5|Workday|Salt Lake City",
  },
  "oracle_hcm": {
    "BDO USA":"ebqb.fa.us2.oraclecloud.com|CX_1|@", "BDO USA (campus)":"ebqb.fa.us2.oraclecloud.com|CX_1001|@",
    "CBIZ":"ebez.fa.us2.oraclecloud.com|CX_1|@",
    "Dell Technologies":"enterpriseplatform.dell.com|CX_1001|@100000001804034",
    "Grant Thornton":"ehzq.fa.us2.oraclecloud.com|CX_1|@", "ICU Medical":"eduu.fa.us2.oraclecloud.com|CX_1|@",
    "Layton Construction":"fa-exrr-saasfaprod1.fa.ocs.oraclecloud.com|CX_8|@",
    "Molina Healthcare":"hckd.fa.us2.oraclecloud.com|CX_1|@300000001243045;Analyst@",
    "Myriad Genetics":"ekgn.fa.us6.oraclecloud.com|CX_2001|@",
    "Oracle":"eeho.fa.us2.oraclecloud.com|CX_45001|@100000000686064",
    "Snap One (Control4)":"ehtl.fa.us6.oraclecloud.com|CX_2|@",
    "Texas Instruments":"edbz.fa.us2.oraclecloud.com|CX|@300000056252121",
    "The Church of Jesus Christ of Latter-day Saints":"epej.fa.us2.oraclecloud.com|CX_2001|@",
    "Verisk":"fa-ewmy-saasfaprod1.fa.ocs.oraclecloud.com|CX_1|@",
    "Weber County":"fa-etrb-saasfaprod1.fa.ocs.oraclecloud.com|CX_3001|@",
  },
  "eightfold": {
    "Lockheed Martin":"lockheedmartin.eightfold.ai|lockheedmartin.com|Hill AFB@;Utah@;Clearfield@",
  },
  "successfactors": {
    "PacifiCorp (Rocky Mountain Power)":"careers.pacificorp.com|",
  },
}
# An employer that works in one place and whose feed names buildings, not cities ("City Hall", "Plaza 349").
# The place given here is added to any row that does not say where it is.
ASSUMED_PLACE = {
  "Salt Lake City Corporation":"Salt Lake City, UT", "Sandy City":"Sandy, UT", "West Jordan City":"West Jordan, UT",
  "Provo City":"Provo, UT", "Utah County Government":"Utah County, UT", "Ensign College":"Salt Lake City, UT",
  "Deseret Digital Media (KSL.com)":"Salt Lake City, UT", "Bonneville Salt Lake (KSL)":"Salt Lake City, UT",
  "Deseret News":"Salt Lake City, UT", "Boncom":"Salt Lake City, UT", "WCF Insurance":"Sandy, UT",
}
# Universities, governments and hospitals use "University", "Campus", "Graduate" and "Academic" as plain
# description ("Campus Events Assistant"), where a company's feed uses them to mean a new-grad program.
# For these sources those words are not read as program words (see INSTITUTION_KINDS).
INSTITUTIONS = {
  "University of Utah", "Brigham Young University", "Utah State University", "Westminster University", "Ensign College",
  "Space Dynamics Laboratory", "Salt Lake County", "Salt Lake City Corporation", "Utah County Government", "Weber County",
  "Provo City", "Sandy City", "West Jordan City", "Draper City", "Intermountain Health",
  "The Church of Jesus Christ of Latter-day Saints", "Utah Retirement Systems (URS and PEHP)",
}
def rule_kind(company, kind):
    """The kind the title rules should see: "institution" for the sources named above."""
    return "institution" if company in INSTITUTIONS else kind
# Hiring systems beyond the ones built into fetch() live in readers/, one file each. A reader file has
#   KIND = "name"; EMPLOYERS = {"Employer": "slug"}; def fetch(slug) -> [(title, location, url, closes, degree, extra)]
# and may add link_state(url), INSTITUTIONS = {employer names} (or INSTITUTION = True for all of them),
# ASSUMED_PLACE = {employer: "City, ST"}, AGGREGATOR = True (one slug, many employers, each row naming
# its own in extra["company"]) and, with that, LEADS = True (its rows link to the relisting board, not
# to the employer, so the page shows them as leads). Drop a new file in and it is read on the next run;
# a file whose name starts with an underscore is left alone.
READERS = {}
def load_readers():
    if READERS or not os.path.isdir(READERS_DIR): return READERS
    # A reader's "import refresh" must get THIS running module, not a second copy with its own caches.
    sys.modules.setdefault("refresh", sys.modules[__name__])
    import importlib.util
    for fn in sorted(os.listdir(READERS_DIR)):
        if not fn.endswith(".py") or fn.startswith("_"): continue
        try:
            spec = importlib.util.spec_from_file_location("refresh_reader_" + fn[:-3], os.path.join(READERS_DIR, fn))
            mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        except Exception as e:
            print(f"(readers/{fn} could not be loaded: {type(e).__name__}: {e})"); continue
        if getattr(mod, "KIND", None) and callable(getattr(mod, "fetch", None)):
            READERS[mod.KIND] = mod
            INSTITUTIONS.update(getattr(mod, "INSTITUTIONS", ()))
            if getattr(mod, "INSTITUTION", False): INSTITUTIONS.update(getattr(mod, "EMPLOYERS", {}))     # every employer of the kind
            ASSUMED_PLACE.update(getattr(mod, "ASSUMED_PLACE", {}))
    return READERS
# A source whose one slug returns many employers' jobs. Its rows never take over a job that an employer's
# own feed also lists.
def aggregator(kind): return bool(getattr(READERS.get(kind), "AGGREGATOR", False))
# An aggregator whose rows are leads rather than postings: they name the job and the employer but link
# to the relisting board, not to the employer (LEADS = True in the reader: the state job bank).
def lead_source(kind): return bool(getattr(READERS.get(kind), "LEADS", False))
def all_sources():
    """(kind, company, slug, has_card) for every feed this script reads. Employers' own feeds come first
    and aggregators last, so that when both list a job the employer's own row is the one kept."""
    for kind, d in BOARDS.items():
        for co, slug in d.items(): yield kind, co, slug, True
    for kind, d in MORE.items():
        for co, slug in d.items(): yield kind, co, slug, False
    for last in (False, True):
        for kind, mod in READERS.items():
            if aggregator(kind) != last: continue
            for co, slug in getattr(mod, "EMPLOYERS", {}).items(): yield kind, co, slug, False
# Employers this script knows about and does not read. Each is listed in the report to check by hand
# and published in jobs.json, so the page's own web search (Search deeper) starts with their careers pages.
# MANUAL_WHY says why; anything not named there has no public feed at all.
#   robots  the hiring system's robots.txt asks scripts to stay out (NEOGOV, PeopleAdmin, UKG, Paycom, Paycor)
#   wall    the careers site answers scripts with a bot check or an access-denied page
# (Deloitte, EY and KPMG were on this list until October 2026. Their search pages turned out to be readable
# and open to scripts: see readers/deloitte.py, readers/ey.py and readers/kpmg.py.)
MANUAL = {
  "Datafy":"https://www.datafy.com/careers",
  # hiring systems whose robots.txt closes the job list to scripts
  "Salt Lake Community College":"https://www.schooljobs.com/careers/slcc",
  "Utah Valley University":"https://www.schooljobs.com/careers/uvu",
  "Weber State University":"https://jobs.weber.edu/postings/search",
  "Southern Utah University":"https://www.schooljobs.com/careers/suu",
  "Utah Tech University":"https://www.schooljobs.com/careers/utahtech",
  "Davis Technical College":"https://www.governmentjobs.com/careers/davistech",
  "City of St. George":"https://www.governmentjobs.com/careers/sgcity",
  "ARUP Laboratories":"https://recruiting2.ultipro.com/ARU1000ARUP/JobBoard/62cc791d-612e-42e6-909f-0de27efe2038",
  "Ogden Clinic":"https://recruiting2.ultipro.com/OGD1000OGD/JobBoard/c2ba6b06-f004-464f-880a-7238bcfdafd8",
  "Sorenson Communications":"https://sorenson.com/company/careers/",
  "Goldenwest Credit Union":"https://www.gwcu.org/careers",
  "TAB Bank":"https://www.tabbank.com/careers/",
  "Bank of Utah":"https://recruitingbypaycor.com/career/CareerHome.action?clientId=8a7883d09881baf30198ab02b0f34247",
  "FinWise Bank":"https://www.paycomonline.net/v4/ats/web.php/portal/6897E5BB605A9248CCAC55282BE01379/career-page",
  "Black Diamond Equipment":"https://blackdiamondequipment.com/pages/careers",
  "Waterford.org":"https://www.waterford.org/careers/",
  "ZAGG":"https://www.zagg.com/careers/",
  "Campbell Scientific":"https://www.campbellsci.com/open-positions",
  "Cricut":"https://jobs.smartrecruiters.com/Cricut",
  "Nearmap":"https://jobs.smartrecruiters.com/Nearmap",
  "HireVue":"https://jobs.smartrecruiters.com/HireVue",
  "Pelion Venture Partners portfolio companies":"https://jobs.pelionvp.com/jobs",
  "Album VC portfolio companies":"https://jobs.album.vc/jobs",
  "Peterson Partners portfolio companies":"https://jobs.petersonpartners.com/jobs",
  "Sorenson Capital portfolio companies":"https://careers.sorensoncap.com/jobs",
  # career sites that answer a script with a bot check or an access-denied page
  "HCA Healthcare (MountainStar hospitals)":"https://careers.hcahealthcare.com/",
  "Utah Community Credit Union":"https://www.uccu.com/careers/",
  "Utah Transit Authority":"https://careers.rideuta.com/",
  "Delta Air Lines (Salt Lake City hub)":"https://delta.avature.net/en_US/careers",
  "Parker Hannifin":"https://parkercareers.ttcportals.com/",
  "Young Living":"https://www.youngliving.com/us/en/company/careers",
  "GoTo":"https://www.goto.com/company/careers",
  "Tesla":"https://www.tesla.com/careers/search/",
  # no feed of any kind: a page someone edits by hand, or an app with no list behind it
  "Orem City":"https://jobs.orem.gov/tabs/joblist",
  "Utah State Legislature":"https://le.utah.gov/jobs/jobs.htm",
  "Canyons School District":"https://jobs.canyonsdistrict.org/hr/home.cfm",
  "Zonos":"https://zonos.com/careers",
  "First Utah Bank":"https://firstutahbank.atsondemand.com/",
  "Boart Longyear":"https://careers.boartlongyear.com/jobs?country=US",
}
MANUAL_WHY = {co: "robots" for co in (
    "Salt Lake Community College", "Utah Valley University", "Weber State University", "Southern Utah University", "Utah Tech University",
    "Davis Technical College", "City of St. George", "ARUP Laboratories", "Ogden Clinic", "Sorenson Communications", "Goldenwest Credit Union",
    "TAB Bank", "Bank of Utah", "FinWise Bank", "Black Diamond Equipment", "Waterford.org", "ZAGG", "Campbell Scientific", "Cricut", "Nearmap", "HireVue",
    "Pelion Venture Partners portfolio companies", "Album VC portfolio companies", "Peterson Partners portfolio companies")}
MANUAL_WHY.update({co: "wall" for co in (
    "HCA Healthcare (MountainStar hospitals)", "Utah Community Credit Union", "Utah Transit Authority", "Delta Air Lines (Salt Lake City hub)",
    "Parker Hannifin", "Young Living", "GoTo", "Tesla")})
def unread():
    """[{co, url, why}] for jobs.json."""
    words = {"robots": "its hiring system asks scripts to stay out", "wall": "its careers site turns scripts away"}
    return [{"co": co, "url": url, "why": words.get(MANUAL_WHY.get(co), "it has no public job feed")} for co, url in sorted(MANUAL.items())]

# ---------- who this search is for (edit this block to retarget the script) ----------
HOME_NAME = "Utah"
# Only place names that are unambiguous on their own. Towns that share a name with places elsewhere
# (Sandy, Riverdale, Murray, Layton, Farmington, Pleasant Grove) are left out on purpose: feeds that
# use them also say "UT" or "Utah", and that is what matches.
HOME    = re.compile(r"\b(?:UT|Utah)\b|salt lake|\bSLC\b|\blehi\b|\bprovo\b|\borem\b|south jordan|american fork|\blindon\b", re.I)
UTAH    = HOME   # older name, kept so nothing that imports this breaks
# A December graduate cannot use a summer internship, so those are dropped. Flip this if you want them.
DROP_INTERNSHIPS = True

# ---------- what counts as a role worth telling you about ----------
# Plurals count here too: a job-family requisition reads "Data Architects" or "Operations Program Managers".
SENIOR  = re.compile(r"\b(senior|sr\.?|principals?|leads?|managers?|directors?|dir\.?|head|vp|vice president|chief|"
                     r"architects?|counsel|attorneys?|leader|supervisors?|superintendent|snr\.?|account executive|customer success|"
                     r"ii|iii|iv|distinguished|avp|svp|evp|executives?|intermediate|intmd)\b", re.I)
# A numbered level above one ("Programmer Analyst 2") is not entry-level, unless the title also says it
# is for new graduates ("Software Engineer 2 - New College Grad"). "Analyst 2027" is unaffected, and so
# is a duration or a date: "Analyst 2-Year Rotational Program", "Consultant 3/1/2027 Start".
LEVEL_N = re.compile(r"\b(?:analyst|engineer|developer|programmer|specialist|associate|consultant|auditor)\s+[2-5]"
                     r"(?![-\s./]*(?:\d|yrs?\b|years?\b|months?\b|weeks?\b|days?\b))\b", re.I)
NEW_GRAD = re.compile(r"new[ -]?grad|new college grad|university grad|recent grad|early[- ]career|\bcampus\b", re.I)
# The entry rung of product and program management carries the word "manager" ("Associate Product
# Manager", "APM"), so it is taken out before the seniority test.
ENTRY_MANAGER = re.compile(r"\b(?:associate|junior|jr\.?)\s+(?:product|program|project)\s+manager\b|\bAPM\b", re.I)
# In clinical research a "data manager" manages data, not people ("Clinical Data Managers").
DATA_MANAGER  = re.compile(r"\b((?:clinical|research|study|trials?)\s+data)\s+managers?\b", re.I)
# "Staff" means senior in engineering and is the FIRST rung in audit and accounting
# ("Staff Auditor", "IT Audit Staff", "Staff Consultant, Technology Risk").
STAFF     = re.compile(r"\bstaff\b", re.I)
AUDITLIKE = re.compile(r"audit|accountant|accounting|assurance|advisory|consult", re.I)
# Titles for a different cohort. A season plus a year is deliberately NOT here: "New Grad (Spring 2027
# Start)" and "Winter 2027 Cohort" are full-time start dates, exactly what a December graduate needs.
WRONG_COHORT = re.compile(r"\b(interns?|internships?|c[o0]-?op|summer (?:analyst|associate)|seasonal|off-?cycle|"
                          r"sophomore|freshman|apprentice(?:ship)?|ph\.?d|postdoc(?:toral)?|fellow(?:ship)?|"
                          r"mba|master'?s|return to work|returnship|insight (?:day|program)|early insights?|"
                          # academic ranks, which a university's feed is full of ("Assistant/Associate Professor")
                          r"professors?|lecturers?|adjunct|dean|provost|post[- ]?doc\w*|work[- ]study|graduate (?:student|assistant|teaching)|"
                          r"teaching ass(?:istan)?t|resident physician|residency)\b", re.I)
# Strongest signal: the employer built the role for new graduates. Worth relocating for.
# A bare "program" is not enough ("Program Mentor", "Program Development Owner").
PROGRAM = re.compile(r"(new[ -]?grad|new college grad|\bgraduate\b|early[- ]career|early in career|talent pipeline|"
                     r"\buniversity\b|\bcampus\b|rotational|class of|\b20(?:26|27)\b|"
                     r"\b(?:development|leadership|leaders|rotation|analyst|associate|launch|graduate|technology|"
                     r"banker|foundational|trainee|academy)\s+program\b)", re.I)
# Ordinary entry-level wording.
# Plurals count: universities and public employers title a requisition by its job family
# ("Business Intelligence Analysts", "Data / Reporting Analysts").
ENTRYWORD = re.compile(r"(entry[- ]level|junior|\bjr\.?\b|\bassociates?\b|\banalysts?\b|\blevel (?:i|1)\b|"
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
                     r"recruit\w*|talent(?!\s+pipeline)|skillbridge|hackathon|general interest|"
                     # "Clinical Data Manager" and "Clinical Informatics Analyst" are data jobs; a clinician is not
                     r"clinical(?!\s+(?:data|informatics|research data|trials? data|systems|applications?|analytics|analysts?))|"
                     r"nurse|nursing|rn|lpn|cna|aprn|physician|therapist|dental|teacher|instructor|faculty|"
                     r"radiolog\w+|psychiatr\w+|psycholog\w+|patholog\w+|\w*sonographer|pharmac\w+|surgeon|surgical|"
                     r"medical assistant|emt|paramedic|phlebotom\w+|respiratory|dietitian|hygienist|veterinar\w+|"
                     r"animal care|patient(?!\s+data)|psychometrist|counselor|social worker|chaplain|"
                     r"(?:laboratory|lab|vascular|transplant|mri|ct|cardiovascular|medical)\b[\w ]{0,24}technologist|"
                     r"hous\w*keeper|custodia\w+|janitor\w*|groundskeeper|landscap\w+|vehicle operator|shuttle|courier|"
                     r"cook|chef|dishwasher|barista|cashier|food service|dining|nutrition care|retail associate|stocker|"
                     r"police officer|security (?:officer|guard)|parking|lifeguard|mechanic|electrician|plumber|carpenter|hvac|"
                     r"painter|locksmith|maintenance (?:worker|technician|engineer|specialist)|building (?:systems )?operator|"
                     # hourly plant, shift and recreation work, which a manufacturer's or a city's feed is full of
                     r"production(?!\s+(?:support|engineer\w*|systems?|analysts?|planner|planning|control|scheduler|data))|assembl(?:er|y)|material handler|inspector|outfitter|"
                     r"(?:machine|equipment|forklift|press|plant|water system|wastewater) operator|"
                     r"(?:process|molding|equipment|production|manufacturing|formulation|fab|wafer|field service) tech(?:nician)?s?|"
                     r"(?:1st|2nd|3rd|first|second|third|swing|graveyard|night|weekend) shift|temporary|temp|prn|per diem|time[- ]limited|"
                     r"caregiver|child ?care|coach(?:es)?|referee|scorekeepers?|officials?|umpires?|recreation|aquatics?|camp|crossing guard|fleet|nutrition|"
                     r"firefighter|fire marshal|prosecutor|paralegal|"
                     r"(?:shipping|delivery|receiving) (?:assistant|clerk|driver|associate)|building, shipping|"
                     r"real estate|collections|underwrit\w*|payroll|tax|legal|counsel|"
                     r"communications|public relations|brand|content|social media|"
                     r"customer success|deal desk|commissions?|total rewards|procurement|sourcing|facilities|"
                     r"data center|electrical|mechanical|hardware|warehouse|driver|"
                     r"teller|part[- ]time|\d+\s*hours?|hourly|banker(?!\s+development)|"
                     r"financial advis[eo]rs?|financial services representative|financial customer associate|"
                     r"wealth banking(?!\s+technology)|fiduciary\s+(?:trust|officer|specialist|administrator|associate|accountant)|"
                     r"adjuster|administrative\s+(?:assistant|associate|coordinator|support|specialist|business partner))\b", re.I)
# A technician is a trade (composite, lighting, rental, HVAC) far more often than an office job. The
# ones kept are those a graduate applies for: the lab, the help desk, and data, network or engineering work.
TECHNICIAN = re.compile(r"\btechnicians?\b|\btech\b(?=\s*(?:[ivx]{1,3}|\d)?\s*(?:$|[-,(/]))", re.I)
TECH_OK    = re.compile(r"\b(?:lab|laboratory|research|science|it|information technology|help ?desk|service desk|desktop|support|network|"
                        r"systems?|data|software|computer|engineering|electronics?|qa|quality assurance|audio[- ]?visual|av)\b", re.I)
# The same goes for an operator: of a water system, a crane or a camera far more often than of a computer.
OPERATOR    = re.compile(r"\boperators?\b", re.I)
OPERATOR_OK = re.compile(r"\b(?:computer|network|data|security|soc|noc|it)\b", re.I)
def offtopic(title):
    """The word that makes a title not the kind of work wanted, or None."""
    m = OFFTOPIC.search(title)
    if m: return m.group(0)
    m = TECHNICIAN.search(title)
    if m and not TECH_OK.search(title): return m.group(0)
    m = OPERATOR.search(title)
    return m.group(0) if m and not OPERATOR_OK.search(title) else None
REMOTE  = re.compile(r"\bremote\b|anywhere|distributed", re.I)
# ---------- roles this candidate is a weak fit for ----------
# Flagged and still reported, not dropped: a software-engineering ladder is a real job, just not one an
# information-systems resume wins against computer-science graduates. Data engineering is deliberately
# absent, since SQL and Python work is the candidate's own ground.
SWE_LEAN = re.compile(r"\b(?:software (?:engineer|developer|development engineer)|sde\b|swe\b|back-?end|front-?end|"
                      r"full[ -]?stack|site reliability|\bsre\b|devops|platform engineer|embedded|firmware|"
                      r"mobile (?:engineer|developer)|ios (?:engineer|developer)|android (?:engineer|developer)|"
                      r"compiler|kernel|graphics engineer|research engineer|machine learning engineer|ml engineer|"
                      r"\bai engineer)\b", re.I)
# Read from the posting text where there is one: a required graduate degree, or a majors list naming
# only technical fields. A bare "Bachelor's degree" says nothing and is not flagged.
ADV_DEGREE  = re.compile(r"\b(?:ph\.?\s?d|master'?s|m\.?s\.?)\b[^.]{0,80}\brequired\b|"
                         r"\b(?:ph\.?\s?d|m\.?s\.?)\s+or\s+(?:m\.?s\.?|ph\.?\s?d)\b", re.I)
DEGREE_IN   = re.compile(r"degree in ([^.;]{0,160})", re.I)
# A bar only counts when the posting names hard-technical majors and offers no way in for this degree.
# "a related discipline" or "a relevant field of study" on their own are an open door, not a bar.
TECH_MAJOR  = re.compile(r"computer science|computer engineering|electrical engineering|software engineering|"
                         r"\beecs\b|\bmathematics\b|\bstatistics\b|\bphysics\b|data science|applied math", re.I)
DEGREE_OPEN = re.compile(r"information systems|management information|business analytics|business administration|"
                         r"informatics|information technology|data analytics|any major|any discipline|"
                         r"quantitative field|\bbusiness\b|finance|accounting|economics", re.I)

def degree_flag(text):
    """"MS/PhD" or "technical majors" when the posting sets that bar, else None."""
    if not text: return None
    t = re.sub(r"\s+", " ", html_unescape(re.sub(r"<[^>]+>", " ", text)))
    # "degree in a technical discipline (e.g., Computer Science...)": the period in "e.g." would end
    # the majors list before the majors.
    t = re.sub(r"\b(?:e\.g\.|i\.e\.),?", "such as", t, flags=re.I)
    if ADV_DEGREE.search(t): return "MS/PhD"
    for field in DEGREE_IN.findall(t):
        if TECH_MAJOR.search(field) and not DEGREE_OPEN.search(field): return "technical majors"
    return None
# Years of experience a posting requires, read from its text where a feed supplies it. The board treats
# two or more years as out of reach for a new graduate, so a wrong number hides a real job. The text is
# cut into sentences and list items first, so one bullet is never read together with the next. Then:
# a "Preferred" or "Nice to have" section is skipped whole; a soft word ("ideally", "a plus") softens
# a number only in its own clause; an upper bound ("up to 2 years") is no bar at all; an exchange rate
# ("one year of experience for one year of education") is not a requirement; and the FIRST requirement
# after the posting's requirements heading wins, because a posting lists its main bar first and one that
# hires at several levels lists the junior level first. Nothing stated returns None (unknown), never 0.
# It is a reading aid: the page marks these numbers as read by machine.
_DASH   = "-‐‑‒–—−"
_WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_NUM    = r"(?:\d{1,2}|" + "|".join(_WORDNUM) + r")"
# "3 years", "3+ years", "3-5 years", "two (2) years", "five or more years"
_YEARS  = re.compile(r"(?<![\d$.,/])\b(" + _NUM + r")\s*(?:\(\d{1,2}\)\s*)?(?:\+|\s*(?:[" + _DASH + r"]|to)\s*" + _NUM + r"\s*(?:\(\d{1,2}\)\s*)?)?\s*\+?\s*"
                     r"(?:or more\s+|plus\s+)?(?:years?|yrs?)\b", re.I)
_SOFT   = re.compile(r"prefer|a plus|is a plus|nice to have|bonus|ideal|desired|helpful|advantage|\bor more is\b", re.I)
_UPPER  = re.compile(r"(?:no more than|not more than|up to|less than|fewer than|under|at most|maximum of|within)\s*$", re.I)
_NOT_EXPERIENCE = re.compile(r"years? (?:old|of age)|\byear[- ]over[- ]year|years? in a row|over the (?:past|last)|"
                             r"for (?:over|more than|nearly|the past|the last)|\bfounded\b|anniversar|warranty|\bterm\b|"
                             r"-year\b|year (?:program|rotation|contract|term)|years? (?:degree|college|university|accredited)|every \d|"
                             r"\b(?:past|last|next|first|prior|previous)\s+(?:\d{1,2}|one|two|three|four|five|six|ten)\b", re.I)
# Somebody else's experience: "a team with 15 years of experience", "learn from leaders with 20+ years"
_THIRD_PARTY = re.compile(r"(?:\b(?:team|company|firm|organi[sz]ation|leaders?|experts?|professionals|colleagues|mentors|veterans|founders|partners)"
                          r"\s+(?:\w+\s+){0,3}?(?:with|has|have|having|of)|\bour|\bwe(?:'ve|\u2019ve| have))\s+"
                          r"(?:over |more than |nearly |about |a combined )?$", re.I)
# What follows a bare number of years when it is a requirement ("2-4 years in sales operations") rather
# than a window ("2 years within receiving your bachelor's")
_BARE_OK = re.compile(r"^['\u2019]?\s*(?:of |in |as |working|conducting|designing|building|doing|performing|supporting|managing|leading|developing|writing)", re.I)
# "one year of experience for one year of education" states an exchange rate, not a requirement
_EQUIV_BEFORE = re.compile(r"substitut\w*[^.]{0,45}$|equivalent to[^.]{0,20}$|defined as[^.]{0,20}$|in lieu of[^.]{0,30}$|"
                           r"generally\s*$|\bper\s*$|\bfor (?:each|every)\s*$|(?:years?|yrs?)[^.]{0,25}\b(?:for|per|equals?|=)\s*$|"
                           r"(?:degree|diploma|education)\s*(?:=|equals?)\s*$", re.I)
_EQUIV_AFTER  = re.compile(r"^\s*(?:of\s+)?(?:(?:directly |relevant |related |work |professional |additional )*experience\s+)?"
                           r"(?:per\b|for (?:each|every|one|1|a)\b|of (?:education|college|school|study|coursework|higher education)|"
                           r"(?:can|may) (?:be )?substitut|equals?\b|=)", re.I)
_REQ_HEAD = re.compile(r"minimum qualifications|basic qualifications|required qualifications|requirements|qualifications|"
                       r"what you(?:.ll)? (?:bring|need|have)|who you are|you have\b|about you|must have|what we(?:.re| are) looking for", re.I)
# Section headings. A posting's "Preferred Qualifications" list is not a bar, whatever number is in it.
_SOFT_HEADING = re.compile(r"^\W*(?:preferred|desired|nice[- ]to[- ]haves?|bonus|pluses|plus points|preferences|extra credit|"
                           r"what would be (?:great|nice)|good to have|it.s a plus|even better|additional (?:qualifications|skills))\b[^.]{0,50}$|"
                           r"^\W*(?:qualifications?|skills|requirements?|experience|education)\W*\(?(?:preferred|desired)\)?\W*$", re.I)
_HARD_HEADING = re.compile(r"^\W*(?:minimum|basic|required|requirements?|qualifications?|must[- ]haves?|what you|who you are|about you|"
                           r"you have|(?:key |job |essential )?(?:responsibilit\w+|duties|functions)|what we(?:.re| are) looking for|"
                           r"(?:education|experience|skills)(?:\s*(?:and|&|/)\s*(?:education|experience|skills))*\W*$)", re.I)
_BLOCK  = re.compile(r"(?i)<\s*/?\s*(?:li|p|div|br|h[1-6]|tr|ul|ol|dt|dd)\b[^>]*>")
def _items(text):
    """A posting's text as a list of sentences and list items, so one bullet is never read with the next."""
    raw = _BLOCK.sub(" • ", html_unescape(text))          # Greenhouse sends its HTML entity-escaped
    raw = html_unescape(re.sub(r"<[^>]+>", " ", raw))
    raw = re.sub(r"\s*[\r\n]+\s*", " • ", raw)
    raw = re.sub(r"[ \t ​]+", " ", raw)
    return [p.strip() for p in re.split(r"(?<=[.;!?])\s+|\s*[•·▪●◦]\s*|\s\*\s", raw) if p and p.strip()]

def min_years(text):
    """Years of experience the posting asks for, 0 for an explicit "no experience required" or an upper
    bound, or None when the text does not say."""
    if not text: return None
    items = _items(text)
    if re.search(r"no (?:prior |previous )?(?:work )?experience (?:is )?(?:required|necessary|needed)|little to no (?:related )?experience", " ".join(items), re.I):
        return 0
    start = next((i for i, it in enumerate(items) if _REQ_HEAD.search(it)), None)
    # Under a requirements heading a bare "2-4 years in sales operations" is a requirement; anywhere else
    # in the posting a number of years only counts when the sentence is about experience.
    for scope, strict in ([(items[start:], False), (items, True)] if start is not None else [(items, True)]):
        soft = False
        for it in scope:
            if len(it) <= 70 and not _YEARS.search(it):
                if _SOFT_HEADING.search(it): soft = True; continue
                if _HARD_HEADING.search(it): soft = False; continue
            if soft: continue
            about_experience = bool(re.search(r"experience|background in|track record", it, re.I))
            if strict and not about_experience: continue
            for m in _YEARS.finditer(it):
                before, after = it[max(0, m.start() - 60): m.start()], it[m.end(): m.end() + 60]
                around = it[max(0, m.start() - 40): m.end() + 30]
                if _NOT_EXPERIENCE.search(around) or _THIRD_PARTY.search(before) or _EQUIV_BEFORE.search(before) or _EQUIV_AFTER.search(after): continue
                if not about_experience and not _BARE_OK.search(after): continue
                # "2+ years in a customer-facing role, ideally in SaaS" is a firm two years: a soft word only
                # softens the number when it sits in the same clause.
                if _SOFT.search(before) or _SOFT.search(re.split(r"[,;(]", it[m.end(): m.end() + 120], 1)[0]): continue
                g = m.group(1).lower()
                n = _WORDNUM.get(g) or int(g)
                if n > 20: continue
                return 0 if _UPPER.search(before[-40:]) else n
    return None

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
# A university, hospital or government feed uses "University", "Campus", "Graduate" and "Academic" as
# plain description ("Campus Events Assistant", "... - University of Utah Hospital"), where a company's
# feed uses them to mean a new-grad program. For these kinds they are not read as program words.
INSTITUTION_KINDS = {"institution", "directemployers"}
_PLACE_WORDS = re.compile(r"\b(?:university|campus|graduate|academic)\b", re.I)

# The version is derived from every rule above, so editing HOME or DROP_INTERNSHIPS re-baselines the
# next run automatically instead of reporting every no-longer-matching role as closed.
FILTER_VERSION = hashlib.sha1("\x1f".join([
    HOME.pattern, SENIOR.pattern, LEVEL_N.pattern, NEW_GRAD.pattern, ENTRY_MANAGER.pattern, DATA_MANAGER.pattern, STAFF.pattern,
    SWE_LEAN.pattern, ADV_DEGREE.pattern, DEGREE_IN.pattern, TECH_MAJOR.pattern, DEGREE_OPEN.pattern, AUDITLIKE.pattern, WRONG_COHORT.pattern, PROGRAM.pattern,
    ENTRYWORD.pattern, ONTOPIC.pattern, OFFTOPIC.pattern, TECHNICIAN.pattern, TECH_OK.pattern, OPERATOR.pattern, OPERATOR_OK.pattern, REMOTE.pattern, ABROAD.pattern, US_HINT.pattern, NONUS.pattern,
    _PLACE_WORDS.pattern, ",".join(sorted(INSTITUTION_KINDS)), str(DROP_INTERNSHIPS)]).encode()).hexdigest()[:12]
# (MANAGEMENT is not part of the version: it decides what the database publishes as "experienced", never
# what the report calls a new entry-level role.)

def _parts(loc):
    return [p.strip() for p in re.split(r"[;|]", loc or "") if p.strip()] or [""]

# Feeds that spell a state out ("Park City, Utah", "Manhattan Beach, California") are turned into the
# "City, ST" form the rules above read.
STATE_NAMES = {"Alabama":"AL","Alaska":"AK","Arizona":"AZ","Arkansas":"AR","California":"CA","Colorado":"CO","Connecticut":"CT","Delaware":"DE",
    "District of Columbia":"DC","Florida":"FL","Georgia":"GA","Hawaii":"HI","Idaho":"ID","Illinois":"IL","Indiana":"IN","Iowa":"IA","Kansas":"KS",
    "Kentucky":"KY","Louisiana":"LA","Maine":"ME","Maryland":"MD","Massachusetts":"MA","Michigan":"MI","Minnesota":"MN","Mississippi":"MS",
    "Missouri":"MO","Montana":"MT","Nebraska":"NE","Nevada":"NV","New Hampshire":"NH","New Jersey":"NJ","New Mexico":"NM","New York":"NY",
    "North Carolina":"NC","North Dakota":"ND","Ohio":"OH","Oklahoma":"OK","Oregon":"OR","Pennsylvania":"PA","Rhode Island":"RI",
    "South Carolina":"SC","South Dakota":"SD","Tennessee":"TN","Texas":"TX","Utah":"UT","Vermont":"VT","Virginia":"VA","Washington":"WA",
    "West Virginia":"WV","Wisconsin":"WI","Wyoming":"WY"}
def city_state(city, state):
    """"City, ST" from a feed's separate fields, whichever way it writes the state."""
    city, state = (city or "").strip(), (state or "").strip()
    state = STATE_NAMES.get(state.title(), state)
    return ", ".join(x for x in (city, state) if x)
def placed(loc):
    """True when a location string says where it is: a US state, a country, or remote. "City Hall" and
    "HQ" do not, and neither does a bare city."""
    return bool(loc and (HOME.search(loc) or US_HINT.search(loc) or REMOTE.search(loc) or NONUS.search(loc) or ABROAD.search(loc)))

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

def classify(title, loc, kind=None):
    """Return {"signal", "geo"} for a role worth reporting, or None.

    signal is "program" (built for new graduates), "entry" (entry-level wording) or
    "unleveled" (no level word, kept only near home). geo is home, remote or elsewhere.
    """
    ok, _ = _classify(title, loc, kind)
    return ok

def _classify(title, loc, kind=None):
    if not title: return None, "no title"
    plain = ENTRY_MANAGER.sub(" associate ", title)   # "Associate Program Manager" is a job, not a program
    plain = DATA_MANAGER.sub(r"\1 specialist", plain)
    if kind in INSTITUTION_KINDS: plain = _PLACE_WORDS.sub(" ", plain)
    m = SENIOR.search(plain)
    if m: return None, f"seniority word '{m.group(0)}'"
    m = LEVEL_N.search(plain)
    if m and not NEW_GRAD.search(plain): return None, f"level above one '{m.group(0)}'"
    auditish = bool(STAFF.search(title) and AUDITLIKE.search(title))
    if STAFF.search(title) and not auditish: return None, "seniority word 'Staff'"
    if DROP_INTERNSHIPS:
        m = WRONG_COHORT.search(title)
        if m: return None, f"wrong cohort '{m.group(0)}'"
    word = offtopic(title)
    if word: return None, f"off-topic word '{word}'"
    geo = where(loc)
    if geo is None: return None, "outside the US"
    if PROGRAM.search(plain):   return {"signal": "program", "geo": geo}, ""
    if ENTRYWORD.search(title) or auditish: return {"signal": "entry", "geo": geo}, ""
    if geo == "home" and ONTOPIC.search(title): return {"signal": "unleveled", "geo": geo}, ""
    return None, ("no entry-level wording" + ("" if geo == "home" else f" (and not in {HOME_NAME}, where unleveled titles are kept)"))

# Experienced individual-contributor titles near home ("Senior Data Analyst", "Data Cloud Architect").
# They are not entry-level, so the report never lists them. The database still publishes them, as their
# own level: someone with a few years behind them uses the same page, and a new graduate can ask to see
# what the next rung looks like. Managers and executives are left out.
MANAGEMENT = re.compile(r"\b(managers?|mgr|directors?|dir\.?|head|vp|vice president|chief|counsel|attorneys?|leader|supervisors?|"
                        r"superintendent|account executive|customer success|avp|svp|evp|executives?|president|officer)\b", re.I)
def experienced(title, loc, kind=None, why=None):
    """True for a senior individual-contributor role in the home area that the title rules drop only for its level."""
    if why is None:
        kept, why = _classify(title, loc, kind)
        if kept: return False
    if not (why.startswith("seniority word") or why.startswith("level above one")): return False
    if where(loc) != "home": return False
    plain = DATA_MANAGER.sub(r"\1 specialist", ENTRY_MANAGER.sub(" associate ", title))
    if MANAGEMENT.search(plain) or offtopic(title) or (DROP_INTERNSHIPS and WRONG_COHORT.search(title)): return False
    return bool(ONTOPIC.search(title) or ENTRYWORD.search(title))

# What kind of work a title is, for the page's Field filter. First match wins, so the order is the
# rule: "Data Privacy Analyst" is risk, "Financial Data Analyst" is data, "Civil Engineer" is engineering.
FIELDS = [
    ("security",    r"cyber|security|infosec|\bsoc\b|threat|vulnerab|penetration|incident response|identity (?:and|&) access|\biam\b"),
    ("risk",        r"\brisk\b|audit|complian|privacy|fraud|governance|\bgrc\b|regulatory|\baml\b|\bkyc\b|investigat|export control"),
    ("data",        r"\bdata\b|analytics|business intelligence|\bbi\b|statistic|biostat|reporting|insights?\b|informatics|machine learning|"
                    r"\bml\b|\bai\b|tableau|\bsql\b|quantitative|research analyst|decision science"),
    ("engineering", r"civil|mechanical|electrical|biomedical|chemical|manufactur|structural|aerospace|industrial|hardware|materials|"
                    r"semiconductor|optical|electromagnetic|\brf\b|telecom|voip|flood control|thin film|\betch\b|\bepi\b|wafer|\bdevice\b|"
                    r"process (?:integration|development)|(?:process|quality|test|supplier|facilities|field|field service|project|equipment|"
                    r"failure analysis|design(?: assurance)?|yield|alignment|packaging|molding) engineer"),
    ("research",    r"research|laborator|\blab\b|scientist"),
    ("software",    r"software|developer|engineer|devops|\bsre\b|full[ -]?stack|front[ -]?end|back[ -]?end|programmer|\bqa\b|quality assurance|"
                    r"systems? (?:admin\w*|analysts?|engineers?|architects?)|information (?:systems|technology)|\bit\b|help ?desk|"
                    r"technical support|salesforce|workday|sharepoint|servicenow|network|cloud|database|\bweb\b|applications?|e-?learning"),
    ("finance",     r"financ|account|treasury|credit|investment|investing|banking|banker|actuar|\btax\b|budget|payroll|loan|underwrit|wealth|"
                    r"equity|capital markets|portfolio|pricing|billing"),
    ("product",     r"product|project|program manag|\bux\b|design|scrum|implementation|onboarding|solutions?|consult"),
    ("business",    r"analysts?|associates?|operations|strategy|business|coordinator|specialist|administrator|supply chain|procurement|"
                    r"\bhr\b|human resources|people"),
    ("research",    r"technician|technologist|microbiolog|chemist|biolog"),
]
_FIELD_RE = [(name, re.compile(pat, re.I)) for name, pat in FIELDS]
def field_of(title):
    """One of security, risk, data, engineering, research, software, finance, product, business, other."""
    for name, rx in _FIELD_RE:
        if rx.search(title or ""): return name
    return "other"

def interesting(title, loc):
    return classify(title, loc) is not None

# ---------- asking first: robots.txt ----------
# Every host this script reads is asked, once a run, whether scripts may read that path and how fast.
# A path its robots.txt closes to everyone is not read: the source is reported as off-limits, and the
# page's own web search is the way to cover that employer. A stated crawl delay is kept.
# DOCUMENTED_APIS is the one way round it, and it ships empty. It is for an API whose vendor documents
# it as public for exactly this use while the robots.txt on the API host turns every crawler away: name
# the host and the page that says so. SmartRecruiters is the case in point (its Posting API is listed
# under "No authentication" at developers.smartrecruiters.com/docs/authentication, and
# api.smartrecruiters.com/robots.txt says "Disallow: /"). readers/_smartrecruiters.py is written and
# tested; to use it, add the host here and drop the underscore from the file name. That is your call.
DOCUMENTED_APIS = {
}
class OffLimits(RuntimeError):
    """The site's robots.txt asks scripts not to read this path."""
_ROBOTS, _ROBOTS_LOCK = {}, threading.Lock()
_PACE, _PACE_LOCK = {}, threading.Lock()
def _curl_raw(args, url, timeout):
    raw = subprocess.run(["curl","-sS","-L","--max-time",str(timeout),"-A",UA,*args,"-w","\n@@HTTP@@%{http_code}",url],
                         capture_output=True).stdout
    # Most of the web is UTF-8. A page that is not (school districts still serve Windows-1252) must still
    # be read rather than raise, so it is decoded the way a browser would fall back.
    try: out = raw.decode("utf-8")
    except UnicodeDecodeError: out = raw.decode("cp1252", "replace")
    body, sep, code = out.rpartition("\n@@HTTP@@")
    return (code.strip() or "000", body) if sep else ("000", out)
def parse_robots(text):
    """([(allow?, pattern)], crawl delay) for the rules addressed to every user agent."""
    groups, fresh = [], False
    for line in (text or "").lstrip("\ufeff").splitlines():      # a byte-order mark would hide the first "User-agent" line
        line = line.split("#", 1)[0].strip()
        if ":" not in line: continue
        k, v = [x.strip() for x in line.split(":", 1)]; k = k.lower()
        if k == "user-agent":
            if not fresh: groups.append(([], []))       # consecutive User-agent lines share one group
            groups[-1][0].append(v.lower()); fresh = True
        elif k in ("allow", "disallow", "crawl-delay") and groups:
            fresh = False; groups[-1][1].append((k, v))
    rules, delay = [], None
    for agents, lines in groups:
        if "*" not in agents: continue
        for k, v in lines:
            if k == "crawl-delay":
                try: delay = float(v)
                except ValueError: pass
            elif v: rules.append((k == "allow", v))
    return rules, delay
def robots_verdict(rules, path):
    """True when the path may be read. The longest matching rule wins and Allow wins a tie (RFC 9309)."""
    best = (-1, True)
    for allow, pat in rules:
        rx = "".join(".*" if ch == "*" else re.escape(ch) for ch in pat.rstrip("$")) + ("$" if pat.endswith("$") else "")
        if re.match(rx, path) and (len(pat) > best[0] or (len(pat) == best[0] and allow)): best = (len(pat), allow)
    return best[1]
def robots(url):
    """(may this URL be read, the host's crawl delay in seconds or None)."""
    u = urllib.parse.urlsplit(url)
    host = u.netloc.lower()
    if host in DOCUMENTED_APIS or not host: return True, None
    with _ROBOTS_LOCK:
        if host not in _ROBOTS:
            code, body = _curl_raw([], f"{u.scheme or 'https'}://{host}/robots.txt", 15)
            if code[:1] == "5" or code == "000":                 # one more try before giving up on the host
                time.sleep(2); code, body = _curl_raw([], f"{u.scheme or 'https'}://{host}/robots.txt", 15)
            if code.startswith("2") and "<html" not in body[:400].lower(): _ROBOTS[host] = parse_robots(body)
            elif code[:1] == "5" or code == "000": _ROBOTS[host] = None   # unreachable: RFC 9309 says assume closed
            else: _ROBOTS[host] = ([], None)                               # no robots.txt: nothing is closed
        known = _ROBOTS[host]
    if known is None: raise RuntimeError(f"could not read robots.txt on {host}, so nothing on it was read")
    rules, delay = known
    return robots_verdict(rules, (u.path or "/") + ("?" + u.query if u.query else "")), delay
def _ask(url):
    """Raise OffLimits for a closed path; otherwise wait out the host's crawl delay."""
    ok, delay = robots(url)
    host = urllib.parse.urlsplit(url).netloc.lower()
    if not ok: raise OffLimits(f"robots.txt on {host} asks scripts not to read this, so it was not read")
    if delay:
        with _PACE_LOCK: lock = _PACE.setdefault(host, [threading.Lock(), 0.0])
        with lock[0]:
            wait = lock[1] - time.time()
            if wait > 0: time.sleep(wait)
            lock[1] = time.time() + min(delay, 15)

# ---------- fetching ----------
def curl_resp(url, post=None, timeout=30, accept="application/json", headers=None, method=None):
    """(http status, body). Status is "000" when curl could not connect or timed out. headers is an
    optional list of extra "Name: value" request headers; method overrides POST for a search endpoint
    that wants PUT. Raises OffLimits for a path robots.txt closes."""
    _ask(url)
    args = ["-H", f"Accept: {accept}"]
    for h in headers or []: args += ["-H", h]
    if post is not None:
        if not any(h.lower().startswith("content-type:") for h in headers or []): args += ["-H", "Content-Type: application/json"]
        args += ["-X", method or "POST", "--data", post if isinstance(post, str) else json.dumps(post)]
    return _curl_raw(args, url, timeout)

def curl_with_headers(url, timeout=30, accept="application/json", headers=None):
    """(http status, the reply with its response headers in front of the body). For the few career sites
    whose public page hands every visitor a token in a Set-Cookie header rather than in the page."""
    _ask(url)
    args = ["-H", f"Accept: {accept}", "-D", "-"]
    for h in headers or []: args += ["-H", h]
    return _curl_raw(args, url, timeout)

def curl_text(url, post=None, timeout=30, accept="application/json", headers=None, method=None):
    """The body of a successful reply. Anything else raises, because a timeout or an error page must
    never be read as "this board has no jobs": that would report every role on it as closed."""
    code, body = curl_resp(url, post, timeout, accept, headers, method)
    host = urllib.parse.urlsplit(url).netloc
    if not code.startswith("2"): raise RuntimeError(f"HTTP {code} from {host}")
    if not body.strip(): raise RuntimeError(f"empty reply from {host}")
    return body

def curl(url, post=None, timeout=30, headers=None, method=None):
    return json.loads(curl_text(url, post, timeout, headers=headers, method=method))

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
    if kind in READERS: return READERS[kind].fetch(slug)
    if kind == "greenhouse":
        # content=true returns every posting's text in the same call, which is what the years and
        # degree flags are read from; a board that refuses it is read without.
        try:
            d = curl(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true", timeout=90)
            need(isinstance(d.get("jobs"), list), "no jobs list")
        except Exception:
            d = curl(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")
            need(isinstance(d.get("jobs"), list), "no jobs list")
        rows = []
        for j in d.get("jobs", []):
            loc = (j.get("location") or {}).get("name", "")
            text = j.get("content") if (classify(j["title"], loc) or experienced(j["title"], loc)) else None   # only read what will be published
            rows.append((j["title"], loc, j["absolute_url"], None, degree_flag(text),
                         {"posted": (j.get("first_published") or j.get("updated_at") or "")[:10] or None, "yrs": min_years(text)}))
        return rows
    if kind == "lever":
        d = curl(f"https://api.lever.co/v0/postings/{slug}?mode=json")
        need(isinstance(d, list), "not a list")
        rows = []
        for j in d:
            loc = (j.get("categories") or {}).get("location", "")
            text = None
            if classify(j["text"], loc) or experienced(j["text"], loc):
                text = "\n".join([j.get("descriptionPlain") or ""] + [f"{l.get('text','')}:\n{l.get('content','')}" for l in j.get("lists") or []])
            posted = datetime.date.fromtimestamp(j["createdAt"] / 1000).isoformat() if isinstance(j.get("createdAt"), (int, float)) else None
            rows.append((j["text"], loc, j["hostedUrl"], None, degree_flag(text), {"posted": posted, "yrs": min_years(text)}))
        return rows
    if kind == "ashby":
        d = curl(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
        need(isinstance(d.get("jobs"), list), "no jobs list")
        rows = []
        for j in d["jobs"]:
            if j.get("isListed") is False: continue          # reachable by link only: the employer is not advertising it
            def named(x):
                """An office name such as "HQ" says nothing, so the posting's own address is added."""
                name, a = (x.get("location") or x.get("locationName") or "").strip(), ((x.get("address") or {}).get("postalAddress") or {})
                if placed(name): return name
                at = city_state(a.get("addressLocality"), a.get("addressRegion"))
                return f"{name} ({at})" if name and at else (at or name)
            loc = "; ".join(x for x in [named(j)] + [named(s) for s in j.get("secondaryLocations") or [] if isinstance(s, dict)] if x)
            if j.get("workplaceType") == "Remote" and not REMOTE.search(loc): loc = (loc + "; " if loc else "") + "Remote"
            text = (j.get("descriptionPlain") or j.get("descriptionHtml")) if (classify(j["title"], loc) or experienced(j["title"], loc)) else None
            rows.append((j["title"], loc, j.get("jobUrl", ""), None, degree_flag(text),
                         {"posted": (j.get("publishedAt") or "")[:10] or None, "yrs": min_years(text)}))
        return rows
    if kind == "directemployers":
        return _directemployers(slug)
    if kind == "adp":
        # ADP WorkforceNow career centers share one public API; the posting link needs the
        # requisition's ExternalJobID, not its itemID. postDate is unreliable (Sunwest's all say 2022).
        rows, skip = [], 0
        while True:
            d = curl(f"https://workforcenow.adp.com/mascsr/default/careercenter/public/events/staffing/v1/job-requisitions"
                     f"?cid={slug}&lang=en_US&locale=en_US&$top=100&$skip={skip}")
            items = d.get("jobRequisitions")
            need(isinstance(items, list), "no jobRequisitions list")
            for j in items:
                ext = next((f.get("stringValue") for f in (j.get("customFieldGroup") or {}).get("stringFields", [])
                            if (f.get("nameCode") or {}).get("codeValue") == "ExternalJobID"), None)
                if not ext: continue
                loc = "; ".join(sorted({(l.get("nameCode") or {}).get("shortName", "").strip() for l in j.get("requisitionLocations", [])} - {""}))
                rows.append((j.get("requisitionTitle", "").strip(), loc,
                             f"https://workforcenow.adp.com/mascsr/default/mdf/recruitment/recruitment.html?cid={slug}&selectedMenuKey=CurrentOpenings&jobId={ext}"))
            if len(items) < 100: break
            skip += 100
        return rows
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
            loc = city_state(l.get("city"), l.get("state")) if isinstance(l, dict) else str(l)
            if j.get("isRemote") or str(j.get("locationType")) == "1": loc = (loc + "; " if loc else "") + "Remote"
            out.append((j.get("jobOpeningName",""), loc,
                        f"https://{slug}.bamboohr.com/careers/{j.get('id','')}"))
        return out
    if kind == "workday":
        # "tenant|wdN|site", "tenant|wdN|site|search one;search two" or "tenant|wdN|site||facet=id".
        # A tenant with thousands of requisitions (Capital One has about 1,800) is searched by keyword
        # instead of paged, because its campus programs sit far past any sane page limit, or narrowed
        # with one of the board's own filters (Intermountain's State filter: the id is in the "facets"
        # of the board's /jobs reply). Some employers use the shared myworkdaysite.com host instead of
        # their own subdomain: give that host in place of wdN ("fmr|wd1.myworkdaysite.com|targeted").
        parts = slug.split("|")
        tenant, wd, site = parts[:3]
        searches = parts[3].split(";") if len(parts) > 3 and parts[3] else [""]
        facets = {k: v.split(",") for k, _, v in (f.partition("=") for f in (parts[4].split("&") if len(parts) > 4 and parts[4] else []))}
        if "." in wd:
            base, page_base = f"https://{wd}", f"https://{wd}/en-US/recruiting/{tenant}/{site}"
        else:
            base = f"https://{tenant}.{wd}.myworkdayjobs.com"
            page_base = f"{base}/en-US/{site}"
        api = f"{base}/wday/cxs/{tenant}/{site}"
        out, paths, where_hint = [], {}, {}
        for text in searches:
            off, total = 0, None
            while off < 1000:
                d = patient(curl, f"{api}/jobs", {"appliedFacets":facets,"limit":20,"offset":off,"searchText":text})
                need(isinstance(d.get("jobPostings"), list), "no jobPostings")
                posts = d["jobPostings"]
                # Some tenants report "total" on the first page only and 0 afterwards, so remember it.
                if total is None: total = d.get("total", 0)
                for j in posts:
                    url = page_base + j.get("externalPath","")
                    paths[url] = j.get("externalPath","")
                    loc = j.get("locationsText","")
                    # Hospitals and city governments name a building ("Park City Hospital", "City Hall").
                    # Where the row's summary fields carry the state and city, add them.
                    bullets = [b for b in j.get("bulletFields") or [] if isinstance(b, str)]
                    state = next((b for b in bullets if b in STATE_NAMES), None)
                    if state and not placed(loc):
                        city = next((b for b in bullets if b != state and not re.search(r"\d", b)), "")
                        where_hint[url] = city_state(city, state)
                        loc = f"{loc} ({where_hint[url]})" if loc else where_hint[url]
                    out.append((j.get("title",""), loc, url))
                off += 20
                if len(posts) < 20 or off >= total: break
            if total and off < total and len(posts) == 20: PARTIAL[slug] = f"read the first {off} of {total} jobs" + (f' for "{text}"' if text else "")
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
            if url in where_hint and not any(placed(c) for c in cities): cities = [f"{c} ({where_hint[url]})" for c in cities] or [where_hint[url]]
            return (title, "; ".join(cities) or loc, url, (info.get("endDate") or "")[:10] or None,
                    degree_flag(info.get("jobDescription")),
                    {"posted": (info.get("startDate") or "")[:10] or None, "yrs": min_years(info.get("jobDescription"))})
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
                it = (d.get("items") or [{}])[0]
                end = (it.get("ExternalPostedEndDate") or "").replace("Z", "+00:00")
                text = " ".join(str(it.get(k) or "") for k in ("ExternalDescriptionStr", "ExternalQualificationsStr"))
                return row + (datetime.datetime.fromisoformat(end).astimezone().date().isoformat() if end else None,
                              degree_flag(text),
                              {"posted": (it.get("ExternalPostedStartDate") or "")[:10] or None, "yrs": min_years(text)})
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
            title, loc = g("title"), city_state(g("city"), g("state"))
            text = g("description") if (classify(title, loc) or experienced(title, loc)) else None
            out.append((title, loc, g("url").replace("http://", "https://"), None, degree_flag(text), {"posted": None, "yrs": min_years(text)}))
        return out
    if kind == "selectminds":
        # Oracle Taleo behind SelectMinds: no feed of any kind, only server-rendered pages of ten.
        # The first request redirects to a per-request search id, which the page URLs then need.
        _ask(f"https://{slug}/jobs/search/")
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

_DE_CACHE = {}
def _de_date(text):
    m = re.match(r"\s*(\d{1,2})/(\d{1,2})/(\d{4})", text or "")
    return f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}" if m else None
def _directemployers(slug):
    """Every job on a DirectEmployers career site, read through the search service the site's own pages
    call: 15 jobs a request, so about ninety requests for the University of Utah. (The site also has a
    bulk feed that would take three, but its robots.txt asks scripts not to fetch it.) The slug is the
    site's host, optionally followed by "|" and extra search filters ("dejobs.org|location=Utah&company=...").
    The University's postings carry a fixed block of fields (Open Date, Close Date, Type of Recruitment,
    Minimum Qualifications), which is where the closing date, the internal-only flag and the years of
    experience come from."""
    if slug in _DE_CACHE: return _DE_CACHE[slug]
    host, _, filt = slug.partition("|")
    rows, off = [], 0
    while off < 9000:
        d = patient(curl, f"https://prod-search-api.jobsyn.org/api/v1/solr/search?num_items=15&offset={off}" + ("&" + filt if filt else ""),
                    None, 45, [f"x-origin: {host}"])
        need(isinstance(d.get("jobs"), list) and isinstance(d.get("pagination"), dict), "no jobs list")
        for j in d["jobs"]:
            if not j.get("guid") or not j.get("title_exact"): continue
            desc = j.get("description") or ""
            field = lambda name: (re.search(r"\*\*" + name + r"\*\*\s*([^*\n]{1,80})", desc) or [None, ""])[1].strip()
            flat = re.sub(r"[*\s]+", " ", desc)
            quals = flat[flat.find("Minimum Qualifications"):][:1500].split(" Preferences ")[0] if "Minimum Qualifications" in flat else ""
            yrs = None
            if quals:
                nums = [int(n) for n in re.findall(r"(?:bachelor.s|degree)[^.]{0,60}?\+\s*(\d{1,2})\s+years?", quals)]
                nums += [int(n) for n in re.findall(r"(?:at least|Requires|and)\s+(\d{1,2})\+?\s*(?:-\s*\d{1,2}\s*)?years?", quals)]
                if re.search(r"little to no|with up to \d|no (?:related )?experience", quals, re.I): nums.append(0)
                yrs = min(nums) if nums else min_years(quals)
            else:
                # University of Utah Health postings are a markdown list: keep the line breaks, drop the markers
                yrs = min_years(re.sub(r"[*_]+|^\s*\+\s+", "", desc, flags=re.M))
            loc = j.get("location_exact") or ", ".join(x for x in (j.get("city_exact"), j.get("state_short")) if x)
            # date_new is when the listing was last synced, not when the job opened, so only a stated Open Date counts
            extra = {"posted": _de_date(field("Open Date")), "yrs": yrs,
                     "internal": field("Type of Recruitment").lower().startswith("internal"),
                     "company": j.get("company_exact") or None}
            rows.append((re.sub(r"\s+", " ", j["title_exact"]).strip(), loc, f"https://{host}/{j['guid']}/job/",
                         _de_date(field("Close Date")), degree_flag(quals or None), extra))
        page = d["pagination"]
        if not d["jobs"] or not page.get("has_more_pages"): break
        off += 15
        time.sleep(0.1)
    total = int((d.get("pagination") or {}).get("total") or 0)
    need(not total or len(rows) >= total * 0.9, f"read {len(rows)} of {total} jobs")     # a short read must never look like closures
    _DE_CACHE[slug] = rows = _dedupe(rows)
    return rows

def scan(item):
    kind, company, slug = item[:3]
    try:
        rows = fetch(kind, slug)
    except Exception as e:
        msg = str(e).strip()
        return company, None, None, (msg if isinstance(e, RuntimeError) and msg else f"{type(e).__name__}")[:120]
    if company in ASSUMED_PLACE:
        rows = [r if placed(r[1]) else (r[0], f"{r[1]} ({ASSUMED_PLACE[company]})" if r[1] else ASSUMED_PLACE[company]) + tuple(r[2:]) for r in rows]
    hits = []
    for r in rows:
        t, l, u = r[:3]
        c = classify(t, l, rule_kind(company, kind))
        x = r[5] if len(r) > 5 and isinstance(r[5], dict) else {}
        if c: hits.append({"title": t.strip(), "loc": (l or "").strip(), "url": u,
                           "closes": r[3] if len(r) > 3 else None,
                           "degree": r[4] if len(r) > 4 else None,
                           "posted": x.get("posted"), "yrs": x.get("yrs"), "internal": bool(x.get("internal")),
                           "company": x.get("company"), "field": field_of(t),
                           "swe": bool(SWE_LEAN.search(t)), **c})
    # raw keeps every row the feed returned, kept or not: the database records why each one was dropped
    raw = [((r[0] or "").strip(), (r[1] or "").strip(), r[2]) + tuple(r[3:6]) for r in rows]
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
DE_LINK     = re.compile(r"https://(employment\.utah\.edu)/(?:[^/]+/[^/]+/)?([0-9A-F]{32})(?:\d\d)?(?:/job)?/?$")
ADP_LINK    = re.compile(r"workforcenow\.adp\.com/.*[?&]cid=([0-9a-f-]{36}).*[?&]jobId=(\d+)")

def _status(url, *extra):
    try: _ask(url)
    except RuntimeError: return "000"          # not ours to probe: the link is reported as unknown, never dead
    return subprocess.run(["curl","-sS","-o","/dev/null","--max-time","25","-A",UA,"-w","%{http_code}",*extra,url],
                          capture_output=True, text=True).stdout.strip()

def _verdict(code, dead=("404",)):
    return "dead" if code in dead else "live" if code == "200" else "unknown"

def link_state(url):
    for mod in READERS.values():          # a reader that knows its own links answers for them
        if callable(getattr(mod, "link_state", None)):
            try: state = mod.link_state(url)
            except Exception: state = "unknown"
            if state in ("live", "dead"): return state
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
    m = DE_LINK.search(url)
    if m:   # the site answers 200 for any id, so ask its feed whether the job is still listed
        try: live = {u.split("/")[3] for _, _, u, *_ in _directemployers(m.group(1))}
        except Exception: return "unknown"
        return "live" if m.group(2) in live else "dead"
    m = ADP_LINK.search(url)
    if m:   # the recruitment page is a shell; the career center's own listing says whether the id is still posted
        try: live_ids = {u.rsplit("jobId=", 1)[1] for _, _, u in fetch("adp", m.group(1))}
        except Exception: return "unknown"
        return "live" if m.group(2) in live_ids else "dead"
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

def board_openings(html):
    """[(company, title, url)] for every opening on the board, read from APPLY_STATUS in index.html."""
    out = []
    for co, body in re.findall(r'\n  "([^"]+)": \{.*?openings: \[(.*?)\]\n', html, re.S):
        for t, u in re.findall(r'title: "((?:[^"\\]|\\.)*)".*?url: "([^"]+)"', body):
            out.append((co, html_unescape(t.replace('\\"', '"')), u))
    return out

def moved_links(dead_urls, openings, raw):
    """Some careers sites re-index and hand every posting a new link (Zions did this in October 2026),
    and employers repost a program under a new requisition. A dead link whose title is still on the
    employer's feed is reported as moved, with the new link, rather than as a closed role."""
    moved = {}
    for co, title, url in openings:
        if url not in dead_urls or url in moved: continue
        rows = [r for feed, rs in raw.items() if same_company(co, feed) for r in rs]
        hit = next((r for r in rows if _norm(r[0]) == _norm(title)), None) or \
              next((r for r in rows if is_posting_for(title, r[0]) and r[2] != url), None)
        if hit: moved[url] = (title, hit[2])
    return moved

def check_link(url):
    try: return url, link_state(url)
    except Exception: return url, "unknown"

# ---------- your own applications (optional, never committed) ----------
# Put a file named applications.json next to this script and the report gains a section that
# says, for every job you applied to, whether this script could have found it and if not, why.
# That file is listed in .gitignore: it is personal, and this repository is public.
APPS = os.path.join(HERE, "applications.json")
# The same list, kept the way most people keep it. Whichever exists is read, in this order.
APP_SHEETS = [APPS] + [os.path.join(HERE, "applications" + e) for e in (".csv", ".tsv", ".xlsx")]
def _norm(x):
    x = re.sub(r"&[a-z]+;|&#\d+;", " ", (x or "").lower().replace("&amp;", "&"))   # "&ndash;" is not a word
    return re.sub(r"[^a-z0-9]+", " ", re.sub(r"\bn\.\s?a\.?(?=\W|$)", "na", x)).strip()
# Words that can follow a company's name without making it a different company.
_SUFFIX = {"inc","incorporated","corp","corporation","co","company","llc","llp","lp","ltd","plc","us","usa","group","holdings",
           "bancorporation","bancorp","bank","financial","software","technologies","technology","labs",
           "services","pharmaceuticals","na","the"}
# Other names people use for an employer on the board. Keys are the board name without its parenthetical.
ALIASES = {
    "cicero group": {"mgt", "cicero", "mgt consulting", "mgt cicero"},
    "wgu": {"western governors university", "western governors"},
    "zions bancorporation": {"zions", "zions bank"},
    "jpmorgan chase": {"jpmorganchase", "jp morgan", "j p morgan", "jpmorgan", "jp morgan chase", "chase", "neovest"},
    "morgan stanley": {"parametric", "e trade", "etrade"},
    "goldman sachs": {"goldman"},
    "motorola solutions": {"motorola"},
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
    "freddie mac": {"federal home loan mortgage corporation", "freddiemac", "fhlmc"},
    "fannie mae": {"federal national mortgage association", "fanniemae", "fnma"},
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

# ---------- reading the tracker people actually keep ----------
APP_HEADS = [("company", r"^(company|employer|organi[sz]ation|firm)$"),
             ("title",   r"^(job|title|role|position|job title|job role)$"),
             ("applied", r"^(date|applied|date applied|applied on|submitted)$"),
             ("location", r"^(location|city|where|office|site)$"),
             ("note",    r"^(result|status|outcome|stage|notes?|comments?)$")]
_MONTH_N = {m: i + 1 for i, m in enumerate(["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"])}

def sheet_date(text, today=None):
    """A spreadsheet date, however it is written. No year means the most recent one already past."""
    t = str(text or "").strip()
    today = today or datetime.date.today()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", t): return t
    if re.fullmatch(r"\d{4,5}(\.\d+)?", t):        # an Excel serial number
        return (datetime.date(1899, 12, 30) + datetime.timedelta(days=round(float(t)))).isoformat()
    m = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", t)
    if m:
        y = int(m.group(3)); y += 2000 if y < 100 else 0
        try: return datetime.date(y, int(m.group(1)), int(m.group(2))).isoformat()
        except ValueError: return ""
    m = re.fullmatch(r"(\d{1,2})[- ]([A-Za-z]{3,})\.?", t) or re.fullmatch(r"([A-Za-z]{3,})\.?[- ](\d{1,2})", t)
    if m:
        day_first = m.group(1)[0].isdigit()
        day = int(m.group(1) if day_first else m.group(2))
        mon = _MONTH_N.get((m.group(2) if day_first else m.group(1))[:3].lower())
        if not mon: return ""
        try: d = datetime.date(today.year, mon, day)
        except ValueError: return ""
        return (d if d <= today else datetime.date(today.year - 1, mon, day)).isoformat()
    return ""

def sheet_status(text):
    t = str(text or "").lower()
    if "offer" in t: return "offer"
    if re.search(r"withdrew|withdrawn", t): return "withdrawn"
    if re.search(r"denied|rejected|reject|no thank|not selected|turned down", t): return "rejected"
    if re.search(r"interview|hirevue|hireview|hire view|screen|assessment|onsite|final round", t): return "interview"
    return "pending"

def sheet_rows(path):
    """[[cell, ...], ...] from a .csv, .tsv or .xlsx, using only the standard library."""
    if path.endswith(".xlsx"):
        import zipfile, xml.etree.ElementTree as ET
        ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            shared = []
            if "xl/sharedStrings.xml" in names:
                for si in ET.fromstring(z.read("xl/sharedStrings.xml")):
                    shared.append("".join(t.text or "" for t in si.iter(ns + "t")))
            sheet = sorted(n for n in names if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n))[0]
            rows = []
            for row in ET.fromstring(z.read(sheet)).iter(ns + "row"):
                cells = {}
                for c in row.iter(ns + "c"):
                    ref = re.match(r"([A-Z]+)", c.get("r") or "A")
                    col = 0
                    for ch in (ref.group(1) if ref else "A"): col = col * 26 + ord(ch) - 64
                    v = c.find(ns + "v")
                    if c.get("t") == "s" and v is not None and v.text and v.text.isdigit():
                        val = shared[int(v.text)] if int(v.text) < len(shared) else ""
                    elif c.get("t") == "inlineStr":
                        val = "".join(t.text or "" for t in c.iter(ns + "t"))
                    else:
                        val = (v.text or "") if v is not None else ""
                    cells[col - 1] = val.strip()
                rows.append([cells.get(i, "") for i in range(max(cells) + 1)] if cells else [])
            return rows
    text = open(path, encoding="utf-8-sig", newline="").read()
    first = text.split("\n")[0]
    import csv as _csv
    delim = "\t" if first.count("\t") > first.count(",") else ","
    return [[c.strip() for c in r] for r in _csv.reader(io.StringIO(text), delimiter=delim)]

def apps_from_sheet(path):
    """Applications from a spreadsheet, plus the rows skipped because they are not applications yet."""
    rows = [r for r in sheet_rows(path) if any(c for c in r)]
    head, cols = -1, {}
    for i, row in enumerate(rows[:10]):
        found = {}
        for j, cell in enumerate(row):
            for key, pat in APP_HEADS:
                if key not in found and re.fullmatch(pat, cell.strip(), re.I): found[key] = j
        if "company" in found and "title" in found:
            head, cols = i, found
            break
    if head < 0: return None, f"{os.path.basename(path)} has no header row with a Company column and a Job column"
    out, skipped = [], 0
    for row in rows[head + 1:]:
        get = lambda k: (row[cols[k]].strip() if k in cols and cols[k] < len(row) else "")
        company, title = get("company"), get("title")
        if not company or not title: continue
        when = get("applied")
        if when and not sheet_date(when):      # "not yet" means a shortlist entry, not an application
            skipped += 1
            continue
        result = get("note")
        out.append({"company": company, "title": title, "location": get("location"),
                    "applied": sheet_date(when), "status": sheet_status(result), "note": result})
    return out, (f"{skipped} row(s) in {os.path.basename(path)} are not applied to yet, so they were skipped" if skipped else None)

def load_applications():
    """Rows with a company and a title, from applications.json or the same list as a spreadsheet.
    Anything malformed is skipped, so a hand-edited file can never abort a run after every board has
    already been fetched."""
    path = next((p for p in APP_SHEETS if os.path.exists(p)), None)
    if path is None: return [], None
    if path != APPS:
        try: return apps_from_sheet(path)
        except Exception as e: return [], f"could not read {os.path.basename(path)}: {e}"
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
        ("Technology Early Talent Pipeline", "Atlanta, GA"),   # an employer renamed its program postings to this
    ]
    must_drop = [
        ("Staff Software Engineer", "Lehi, UT"), ("Senior Data Analyst", "Lehi, UT"),
        ("Data Architects", "Salt Lake City, UT"), ("Operations Program Managers", "Salt Lake City, UT"),
        ("Information Technology Supervisor", "Salt Lake City, UT"),
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
        ("Early Talent Recruiter", "Lehi, UT"), ("Talent Analyst", "Lehi, UT"),
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
        (is_posting_for("Operations Analyst, Mar 2027", "Operations Analyst (March 2027)"), "month abbreviations"),
        (is_posting_for("Risk Analyst I, Launch 2027", "Risk Analyst I, Launch 2027 - St. Louis, MO, US"), "city suffix"),
        (not is_posting_for("Data Analyst", "Senior Data Analyst"), "senior sibling is a different job"),
        (not is_posting_for("Security Analyst", "Security Analyst II"), "level II is a different job"),
        (bool(SWE_LEAN.search("Software Engineer, New Grad")) and bool(SWE_LEAN.search("Site Reliability Engineer I")), "SWE ladders are flagged"),
        (not SWE_LEAN.search("Data Engineer I") and not SWE_LEAN.search("Business Analyst"), "data work is not flagged as SWE"),
        (degree_flag("PhD or MS in Computer Science, Statistics or equivalent") == "MS/PhD", "graduate degree bar"),
        (degree_flag("Bachelor's degree in Computer Science, Computer Engineering, or a related technical field") == "technical majors", "technical-majors bar"),
        (degree_flag("Bachelor's degree in Information Systems, Business Analytics or a related field") is None, "an IS-friendly majors list is not a bar"),
        (degree_flag("Bachelor's degree in a related discipline") is None, "'a related discipline' is an open door"),
        (degree_flag("Bachelor's degree in a relevant field of study, proficiency in Excel") is None, "'a relevant field of study' is an open door"),
        (degree_flag("degree in a relevant field (Computer Science, EECS, Statistics)") == "technical majors", "named technical majors are a bar even after 'relevant field'"),
        (degree_flag("degree in Computer Science, Information Technology, or related field") is None, "IT counts as a way in"),
        (sheet_date("2026-09-13") == "2026-09-13" and sheet_date("9/13/2026") == "2026-09-13", "spreadsheet date formats"),
        (sheet_date("13-Sep", datetime.date(2026, 9, 28)) == "2026-09-13", "a day and month with no year"),
        (sheet_date("15-Dec", datetime.date(2026, 9, 28)) == "2025-12-15", "a month still to come means last year"),
        (sheet_date("46278") == "2026-09-13", "an Excel serial date"),
        (sheet_date("not yet") == "" and sheet_date("") == "", "a note in the date column is not a date"),
        (sheet_status("Denied, experience") == "rejected" and sheet_status("HireView done") == "interview"
         and sheet_status("") == "pending", "a Result column becomes a status"),
        (degree_flag("Currently enrolled in a Bachelor's or accelerated Master's degree") is None, "a bare degree line is not a bar"),
        (degree_flag("degree in a quantitative or technical discipline (e.g., Computer Science, Data Science, Mathematics or Statistics)") == "technical majors",
         "'e.g.' inside the majors list does not end it"),
        (moved_links({"https://x/jobs/1"}, [("Zions Bancorporation", "Cybersecurity Analyst - GRC", "https://x/jobs/1")],
                     {"Zions Bancorporation": [("Cybersecurity Analyst - GRC", "Midvale, UT", "https://x/jobs/9")]}) == {"https://x/jobs/1": ("Cybersecurity Analyst - GRC", "https://x/jobs/9")},
         "a dead link whose title is still on the feed is a moved link"),
        (moved_links({"https://x/jobs/1"}, [("Zions Bancorporation", "Cybersecurity Analyst", "https://x/jobs/1")],
                     {"Zions Bancorporation": [("Senior Cybersecurity Analyst", "Midvale, UT", "https://x/jobs/9")]}) == {},
         "a senior sibling does not make a dead link a moved link"),
        (classify("Business Intelligence Analysts", "Salt Lake City, UT") == {"signal": "entry", "geo": "home"}, "a plural job-family title is entry-level wording"),
        (classify("Clinical Data Managers", "Salt Lake City, UT") == {"signal": "unleveled", "geo": "home"} and not classify("Clinical Nurse Coordinator", "Salt Lake City, UT"),
         "clinical data work is data work; clinical care is not"),
        (not classify("Assistant/Associate Professor in the Department of Finance", "Salt Lake City, UT") and not classify("Housekeeper I", "Salt Lake City, UT")
         and not classify("Medical Assistant I", "Salt Lake City, UT"), "academic ranks, trades and clinical jobs are not entry-level office roles"),
        (classify("Campus Undergraduate Full-Time Analyst - 2027 Data & Analytics", "Phoenix, AZ")["signal"] == "program"
         and not classify("Campus Events Assistant", "Salt Lake City, UT", "directemployers")
         and classify("Financial Analyst - University Hospital", "Salt Lake City, UT", "directemployers")["signal"] == "entry",
         "'Campus' and 'University' mean a program at a company and a place at a university"),
        (classify("Client Delivery Advocate - Analyst", "Salt Lake City, UT") and classify("USA - Assurance - Data and Intelligence Delivery - Analyst", "Salt Lake City, UT"),
         "'delivery' in an analyst title is not a delivery job"),
        ([field_of(t) for t in ("Data Privacy Analyst", "Financial Data Analyst", "Civil Engineer", "Staff Auditor", "Information Systems Architects",
                                "Associate Credit Analyst", "Cybersecurity Analyst", "Research Associate", "Associate Product Manager", "Operations Coordinator", "Barista")]
         == ["risk", "data", "engineering", "risk", "software", "finance", "security", "research", "product", "business", "other"], "field tags"),
        (min_years("Requirements: 2+ years of experience in a customer-facing role. Bonus: 5 years of SQL.") == 2, "years are read from the requirement, not the bonus"),
        (min_years("3-5 years of experience in analytics; 7+ years preferred") == 3 and min_years("We have grown for 10 years. Bachelor's degree.") is None, "ranges take the low end; a company's age is not experience"),
        (min_years("No prior experience required. Paid training.") == 0 and min_years("A 2-year rotational program for new graduates") is None, "an explicit no-experience line is 0; a program length is not experience"),
        (min_years("Requirements 3+ years of experience in a fraud or risk role 1+ year of experience leading projects") == 3, "the first requirement is the bar, not the smallest number"),
        (min_years("Join a team with 15 years of experience. What you bring: 2 \u2013 5 years of outbound sales experience.") == 2, "the requirements heading wins, and an en dash is a range"),
        (min_years("Required: no more than two years of work experience. Up to 2 years of experience in audit.") == 0, "an upper bound is not a bar"),
        (min_years("<p>Reporting tools, preferably Tableau</p><p>Minimum Qualifications</p><ul><li>Bachelor's degree</li><li>2 years of experience in data engineering</li>"
                   "<li>Generally, equivalent experience is defined as 1 year of experience for 1 year of education.</li></ul><p>Preferred Qualifications</p><ul><li>5+ years of Python</li></ul>") == 2,
         "one list item is never read with the next, an exchange rate is not a requirement, and a Preferred list is not a bar"),
        (min_years("Qualifications\n2+ years of experience in a customer-facing role, ideally within a SaaS company") == 2 and
         min_years("Qualifications\nA degree\n5 years of experience building pipelines is preferred") is None, "a soft word only softens the number in its own clause"),
        (min_years("Who you are:\nAt least 2 - 4 years in sales operations or consulting") == 2 and min_years("Qualifications\nTwo (2) years of experience in accounting") == 2
         and min_years("Requirements:\nA 4 year degree\nGraduated within the last 2 years") is None, "under a requirements heading a bare number of years counts; a degree length and a graduation window do not"),
        (min_years("Qualifications\nLearn from industry leaders with 20+ years of experience in consulting.") is None and
         min_years("Requirements\nIf pursuing a master's, it must be 2 years within receiving your bachelor's.") is None and
         min_years("About you\nWe are looking for someone with 3 years of experience in audit.") == 3, "somebody else's experience and a graduation window are not a bar"),
        (min_years("Minimum Qualifications\nEquivalency: 1 year of higher education can be substituted for 1 year of directly related work experience "
                   "(Example: bachelor's degree = 4 years of directly related work experience).\nRequires at least 1 year of related experience.") == 1 and
         min_years("Qualifications\nRequired\nBachelor's degree\nTwo years of related experience, or equivalency.\nQualifications (Preferred)\nFive years of experience in Epic") == 2,
         "a public employer's equivalency example is not the requirement, and its Preferred block is skipped"),
        (experienced("Senior Data Analyst", "Lehi, UT") and experienced("Data Cloud Architect", "Salt Lake City, UT") and experienced("Programmer Analyst 3", "Provo, UT")
         and not experienced("Senior Data Analyst", "Austin, TX") and not experienced("Director of Data Analytics", "Lehi, UT")
         and not experienced("Senior Account Executive", "Lehi, UT") and not experienced("Data Analyst I", "Lehi, UT") and not experienced("Senior Nurse Analyst", "Lehi, UT")
         and classify("Senior Data Analyst", "Lehi, UT") is None,
         "an experienced role near home is published as its own level, never as entry-level; managers, sales and far-away roles are not"),
        (not classify("Production Associate I - 2nd Shift", "Salt Lake City, UT") and not classify("Entry Level Machine Operator", "Salt Lake City, UT")
         and not classify("Quality Inspector I", "Salt Lake City, UT") and not classify("Molding Process Technician I", "Salt Lake City, UT")
         and not classify("Recreation Worker I", "Draper, UT") and not classify("Wrestling Coaches Winter 2027", "Provo, UT")
         and not classify("Junior Art Coordinator (TEMP)", "Salt Lake City, UT")
         and classify("Lab Technician I", "Salt Lake City, UT") and classify("Service Desk Technician I", "Salt Lake City, UT")
         and classify("Quality Engineer I", "Salt Lake City, UT") and classify("Manufacturing Engineer", "Logan, UT"),
         "hourly plant, shift, temporary and recreation work is dropped; lab, IT and engineering roles are kept"),
        (not classify("Composite Technician I", "Salt Lake City, UT") and not classify("Rental Technician 1", "Salt Lake City, UT")
         and not classify("Lighting Technician I - Aviation", "Salt Lake City, UT") and not classify("Formulation Tech I", "Salt Lake City, UT")
         and classify("Lab Technician I", "Salt Lake City, UT") and classify("IT Support / Help Desk Tech I", "Salt Lake City, UT")
         and classify("Data & Voice Technician", "Logan, UT") and classify("Engineering Technician I", "Ogden, UT")
         and classify("SAP Finance - Tech Consulting - Analyst", "Salt Lake City, UT"),
         "a trade technician is dropped; lab, help-desk, data and engineering technicians are kept, and 'Tech Consulting' is not a technician"),
        (not classify("Water Systems Operator 1/2/3/4 - Leak Crew", "Lehi, UT") and not classify("Jr. Sports Officials/Scorekeepers", "Lehi, UT")
         and classify("Computer Operator I", "Salt Lake City, UT") and classify("Security Operations Center Operator", "Lehi, UT"),
         "an operator of anything but a computer, a network or a security desk is dropped"),
        (not classify("Entry Level Production - Job Pool", "Brigham City, UT") and not classify("Customer Service Associate / Outfitter", "West Jordan, UT")
         and classify("Production Support Analyst", "Lehi, UT") and classify("Production Engineer I", "Ogden, UT"),
         "production-line and store-floor work is dropped; production support and production engineering are kept"),
        (field_of("Device and Process Integration Engineer") == "engineering" and field_of("Software Engineer") == "software" and field_of("Data Engineer") == "data"
         and field_of("Lab Technician I") == "research" and field_of("Systems Engineer") == "software", "a non-software engineer is engineering"),
        (job_key("https://job-boards.greenhouse.io/acme/jobs/8123456") == job_key("https://www.acme.test/careers/8123456?gh_jid=8123456")
         and job_key("https://acme.wd5.myworkdayjobs.com/en-US/External/job/Salt-Lake-City-UT/Data-Analyst_JR-0042") == job_key("https://acme.wd5.myworkdayjobs.com/External/job/Salt-Lake-City-UT/Data-Analyst_JR-0042-1")
         and job_key("https://www.acme.test/jobs/77/?utm=x") == job_key("http://acme.test/jobs/77") != job_key("https://acme.test/jobs/78")
         and job_key("https://bank.test/single-job?j=11") != job_key("https://bank.test/single-job?j=12")
         and job_key("https://bank.test/single-job?utm_source=a&j=11") == job_key("https://bank.test/single-job?j=11")
         and job_key("https://jobs.lever.co/acme/0a1b2c3d-1111-2222-3333-444455556666/apply") == job_key("https://jobs.lever.co/acme/0A1B2C3D-1111-2222-3333-444455556666")
         and job_key("https://ukg.test/ACM1000/JobBoard/0a1b2c3d-1111-2222-3333-444455556666/OpportunityDetail?opportunityId=7") != job_key("https://ukg.test/ACM1000/JobBoard/0a1b2c3d-1111-2222-3333-444455556666/OpportunityDetail?opportunityId=8"),
         "one posting has one key however it is linked"),
        (robots_verdict(*[parse_robots("User-agent: Googlebot\nUser-agent: bingbot\nAllow: /\n\nUser-agent: *\nDisallow: /\n")[0]], "/careers/x") is False
         and robots_verdict(parse_robots("User-agent: *\nDisallow: /*feed/\nAllow: /\n")[0], "/jobs/feed/json") is False
         and robots_verdict(parse_robots("User-agent: *\nDisallow: /*feed/\nAllow: /\n")[0], "/jobs/") is True
         and parse_robots("User-agent: *\nCrawl-delay: 5\nDisallow: /admin\n") == ([(False, "/admin")], 5.0)
         and robots_verdict(parse_robots("User-agent: SomeBot\nDisallow: /\n")[0], "/jobs") is True
         and robots_verdict(parse_robots("\ufeffUser-agent: *\nDisallow: /private\n")[0], "/private/x") is False,
         "robots.txt: rules for everyone are kept, a longer rule beats a shorter one, and rules for a named crawler are not ours"),
        (placed("Draper, UT") and placed("Remote") and placed("SLC Downtown") and not placed("City Hall") and not placed("HQ") and not placed("Seattle")
         and city_state("Park City", "Utah") == "Park City, UT" and city_state("Logan", "UT") == "Logan, UT" and city_state("", "Utah") == "UT",
         "a building or a bare city is not a place; a spelled-out state is abbreviated"),
        (classify("Dir, Software Development", "Lehi, UT") is None, "an abbreviated Director is senior"),
        (board_openings('\n  "Acme": {\n    status: "open-now",\n    note: "x",\n    openings: [{ title: "Data &amp; AI Analyst", loc: "Lehi, UT", url: "https://x/1" }]\n  },\n')
         == [("Acme", "Data & AI Analyst", "https://x/1")], "board openings are read with their company"),
    ]
    bad += [f"check failed: {why}" for ok, why in checks if not ok]
    print("\n".join(bad) if bad else f"selftest passed: {len(must_keep)} kept, {len(must_drop)} dropped, {len(checks)} checks")
    return 1 if bad else 0

# ---------- the job database ----------
# Every row every feed returns goes into jobs.db, kept or not, with the day it was first and last seen.
# That is what lets the page say "new this week" for a job rather than for a hand-edited card, what
# keeps a job's history when its link changes, and what answers "why did the board not show me this?"
# (python3 refresh.py --why "title"). jobs.json is the published slice: live rows the title rules keep.
import sqlite3
def db_open(path=None):
    con = sqlite3.connect(path or DB)
    con.executescript("""
      CREATE TABLE IF NOT EXISTS jobs(
        url TEXT PRIMARY KEY, source TEXT, company TEXT, title TEXT, loc TEXT,
        geo TEXT, signal TEXT, dropped TEXT, field TEXT, swe INTEGER, degree TEXT, yrs INTEGER, internal INTEGER,
        closes TEXT, posted TEXT, first_seen TEXT, last_seen TEXT, gone_on TEXT, seeded INTEGER);
      CREATE INDEX IF NOT EXISTS jobs_source ON jobs(source);
      CREATE TABLE IF NOT EXISTS sources(
        source TEXT PRIMARY KEY, kind TEXT, slug TEXT, card INTEGER, first_read TEXT, last_read TEXT,
        last_count INTEGER, last_error TEXT);
      CREATE TABLE IF NOT EXISTS runs(date TEXT PRIMARY KEY, sources INTEGER, rows INTEGER, live_kept INTEGER);
    """)
    return con

_TRACKING_PARAM = re.compile(r"(?:utm.*|mc_.*|_hs.*|source|src|ref|referrer|gh_src|lever-source|trk|trackingid|fbclid|gclid|cmp|icid)$", re.I)
def _job_query(u):
    query = sorted(p for p in u.split("#")[0].partition("?")[2].split("&") if p and not _TRACKING_PARAM.match(p.split("=")[0]))
    return "?" + "&".join(query) if query else ""
def job_key(url):
    """One posting has one key however it is linked. Kept in step with jobKey() in index.html."""
    u = url or ""
    m = re.search(r"[?&]gh_jid=(\d+)", u) or re.search(r"greenhouse\.io/(?:embed/job_app\?for=)?[^/?]+/jobs/(\d+)", u)
    if m: return "gh:" + m.group(1)
    # A UUID is the job's identity where the link ends with it (Lever, Ashby). Elsewhere it is the board's or
    # the employer's id (UKG, ADP), shared by every job there, and the job's own id is in the query.
    m = re.search(r"/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})(?:/(?:apply|application))?/?(?:[?#].*)?$", u, re.I)
    if m and not _job_query(u): return "id:" + m.group(1).lower()
    m = re.search(r"myworkday(?:jobs|site)\.com/.*/job/.*_([A-Za-z0-9-]+?)(?:-\d)?(?:[/?#].*)?$", u)
    if m: return "wd:" + m.group(1).lower()
    m = re.search(r"oraclecloud\.com/.*/job/(\d+)", u)
    if m: return "ora:" + m.group(1)
    m = re.search(r"employment\.utah\.edu/(?:[^/]+/[^/]+/)?([0-9A-F]{32})", u, re.I)
    if m: return "de:" + m.group(1).upper()
    # What follows the "?" can be the job's whole identity (single-job?j=11133604) or pure tracking, so the
    # tracking parameters are dropped and the rest kept, in a fixed order.
    return "url:" + re.sub(r"/+$", "", re.sub(r"[?#].*$", "", re.sub(r"^https?://(www\.)?", "", u, flags=re.I))).lower() + _job_query(u)

def db_sync(con, today, sources, raw, errors, prev_state=None):
    """Record one run. sources = [(kind, company, slug, has_card)], raw = {company: rows as scan() returns them}.
    A source that failed today is left exactly as it was. Returns {"new": n, "gone": n, "moved": n}."""
    prev_state = prev_state or {}
    first_build = con.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0
    seed_date, seed_roles = prev_state.get("date"), prev_state.get("roles") or {}
    stats = {"new": 0, "gone": 0, "moved": 0}
    agg_sources = {src for k, src, _, _ in sources if aggregator(k)}
    for kind, source, slug, card in sources:
        known = con.execute("SELECT first_read FROM sources WHERE source=?", (source,)).fetchone()
        if source in errors or source not in raw:
            con.execute("INSERT INTO sources(source, kind, slug, card, last_error) VALUES(?,?,?,?,?) "
                        "ON CONFLICT(source) DO UPDATE SET kind=excluded.kind, slug=excluded.slug, card=excluded.card, last_error=excluded.last_error",
                        (source, kind, slug, int(card), errors.get(source, "not read")))
            continue
        # The very first build has no history of its own, so it borrows the previous run's state file:
        # a source that file knew about was already being read on that date.
        first_read = known[0] if known and known[0] else (seed_date if first_build and source in seed_roles and seed_date else today)
        first_time = first_read == today
        # compared without case or punctuation: a feed read by a better reader spells the same title differently
        seeded_titles = {_norm(t) for t in seed_roles.get(source, [])} if first_build else set()
        con.execute("INSERT INTO sources(source, kind, slug, card, first_read, last_read, last_count, last_error) VALUES(?,?,?,?,?,?,?,NULL) "
                    "ON CONFLICT(source) DO UPDATE SET kind=excluded.kind, slug=excluded.slug, card=excluded.card, "
                    "first_read=COALESCE(sources.first_read, excluded.first_read), last_read=excluded.last_read, "
                    "last_count=excluded.last_count, last_error=NULL",
                    (source, kind, slug, int(card), first_read, today, len(raw[source])))
        before = {r[0]: r for r in con.execute("SELECT url, title, loc, first_seen, seeded, posted FROM jobs WHERE source=? AND gone_on IS NULL", (source,))}
        seen_now = {r[2] for r in raw[source] if r[2]}
        # A careers site that re-indexes hands every posting a new link. A row that vanishes today while
        # the same title and place appears under a new link is one job that moved, so its history follows it.
        leaving = {}
        for url, (u, title, loc, first_seen, seeded, posted) in before.items():
            if url not in seen_now: leaving.setdefault((_norm(title), _norm(loc)), []).append((first_seen, seeded, posted))
        for r in raw[source]:
            title, loc, url = r[0], r[1], r[2]
            if not url: continue
            if source in agg_sources:
                # An employer's own feed owns its jobs: a board that merely relists them never takes a row over.
                owner = con.execute("SELECT source FROM jobs WHERE url=? AND gone_on IS NULL", (url,)).fetchone()
                if owner and owner[0] != source and owner[0] not in agg_sources: continue
            x = r[5] if len(r) > 5 and isinstance(r[5], dict) else {}
            kept, why = _classify(title, loc, rule_kind(source, kind))
            senior = not kept and experienced(title, loc, rule_kind(source, kind), why)
            fields = dict(source=source, company=x.get("company") or source, title=title, loc=loc,
                          geo=kept["geo"] if kept else ("home" if senior else None),
                          signal=kept["signal"] if kept else ("senior" if senior else None), dropped=None if kept else why,
                          field=field_of(title),
                          swe=int(bool(SWE_LEAN.search(title))), degree=r[4] if len(r) > 4 else None, yrs=x.get("yrs"),
                          internal=int(bool(x.get("internal"))), closes=r[3] if len(r) > 3 else None, posted=x.get("posted"))
            if url in before or con.execute("SELECT 1 FROM jobs WHERE url=?", (url,)).fetchone():
                con.execute("UPDATE jobs SET " + ", ".join(f"{k}=COALESCE(:{k}, {k})" if k in ("posted", "degree", "closes") else f"{k}=:{k}" for k in fields) +
                            ", last_seen=:today, gone_on=NULL WHERE url=:url", dict(fields, today=today, url=url))
                continue
            moved = leaving.get((_norm(title), _norm(loc)))
            if moved:
                first_seen, seeded, posted = moved.pop(0); stats["moved"] += 1
                fields["posted"] = fields["posted"] or posted
            elif _norm(title) in seeded_titles:
                first_seen, seeded = seed_date, 1
            else:
                first_seen, seeded = today, int(first_time)
                if kept and not first_time: stats["new"] += 1
            con.execute("INSERT INTO jobs(url, " + ", ".join(fields) + ", first_seen, last_seen, seeded) VALUES(:url, " +
                        ", ".join(":" + k for k in fields) + ", :first_seen, :today, :seeded)",
                        dict(fields, url=url, first_seen=first_seen, today=today, seeded=seeded))
        gone = [u for u in before if u not in seen_now]
        con.executemany("UPDATE jobs SET gone_on=? WHERE url=?", [(today, u) for u in gone])
        stats["gone"] += len(gone)
    live_kept = con.execute("SELECT COUNT(*) FROM jobs WHERE gone_on IS NULL AND signal IS NOT NULL AND signal != 'senior'").fetchone()[0]
    con.execute("INSERT OR REPLACE INTO runs(date, sources, rows, live_kept) VALUES(?,?,?,?)",
                (today, len([1 for _, src, _, _ in sources if src in raw and src not in errors]),
                 con.execute("SELECT COUNT(*) FROM jobs WHERE gone_on IS NULL").fetchone()[0], live_kept))
    con.commit()
    return stats

def db_export(con, today, path=None, dead=()):
    """Write the published slice: every live row the title rules keep, plus experienced-level roles near
    home (sig "senior") and internal-only postings (int 1), which the page keeps behind their own chips.
    Rows past their closing date are left out. "seen" is omitted when the row was recorded on the run that
    first read its source, because that says when this script arrived, not when the job did. "dead" is the
    board's own links that failed today's check, so the page can strike them out without a hand edit."""
    prev = con.execute("SELECT MAX(date) FROM runs WHERE date < ?", (today,)).fetchone()[0]
    cols = "url, source, company, title, loc, geo, signal, field, swe, degree, yrs, closes, posted, first_seen, seeded, internal"
    jobs = []
    cards = {r[0] for r in con.execute("SELECT source FROM sources WHERE card=1")}
    for (url, source, company, title, loc, geo, signal, field, swe, degree, yrs, closes, posted, first_seen, seeded, internal) in con.execute(
            f"SELECT {cols} FROM jobs WHERE gone_on IS NULL AND signal IS NOT NULL "
            "AND (closes IS NULL OR closes >= ?) ORDER BY company, title, loc", (today,)):
        j = {"co": company, "title": title, "loc": loc, "url": url, "geo": geo, "sig": signal, "field": field}
        if source != company: j["src"] = source
        if source in cards: j["card"] = source
        if internal: j["int"] = 1
        if swe: j["swe"] = 1
        if degree: j["deg"] = degree
        if yrs is not None: j["yrs"] = yrs
        if closes: j["closes"] = closes
        if posted: j["posted"] = posted
        if first_seen and not seeded: j["seen"] = first_seen
        jobs.append(j)
    # A relisting board (the state job bank) is there for the employers this script does not read itself.
    # Where an employer's own feed was read today, that feed is the truth about its jobs and the board's
    # copies are left out: they are the same jobs under a second link, or ones the employer has taken down.
    agg = {src for src, kind in con.execute("SELECT source, kind FROM sources") if aggregator(kind)}
    own = [j for j in jobs if j.get("src", j["co"]) not in agg]
    direct = {src for (src,) in con.execute("SELECT source FROM sources WHERE last_read IS NOT NULL") if src not in agg} | {j["co"] for j in own}
    keys, covered = {job_key(j["url"]) for j in own}, {}
    def read_directly(co):
        if co not in covered: covered[co] = any(same_company(co, d) for d in direct)
        return covered[co]
    leads = {src for src, kind in con.execute("SELECT source, kind FROM sources") if lead_source(kind)}
    extra = [dict(j, agg=1) if j.get("src", j["co"]) in leads else j
             for j in jobs if j.get("src", j["co"]) in agg and job_key(j["url"]) not in keys and not read_directly(j["co"])]
    # A job bank often lists one job several times. One lead is enough: the newest.
    newest = {}
    for j in extra:
        k = (_norm(j["co"]), _norm(j["title"]), _norm(j["loc"])) if j.get("agg") else ("", j["url"], "")
        if k not in newest or (j.get("posted") or "") > (newest[k].get("posted") or ""): newest[k] = j
    jobs = own + list(newest.values())
    jobs.sort(key=lambda j: (j["co"].lower(), j["title"].lower(), j["loc"]))
    entry = [j for j in jobs if j["sig"] != "senior" and not j.get("int")]
    out = {"date": today, "prev": prev, "sources": con.execute("SELECT COUNT(*) FROM sources WHERE last_read=?", (today,)).fetchone()[0],
           "employers": len({j["co"] for j in jobs}), "entry": len(entry), "senior": sum(j["sig"] == "senior" and not j.get("int") for j in jobs),
           "leads": sum(1 for j in jobs if j.get("agg")),
           "internal": sum(1 for j in jobs if j.get("int")), "dead": sorted(set(dead)), "unread": unread(), "jobs": jobs}
    json.dump(out, open(path or EXPORT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    return out

def why(query):
    """Explain what the database knows about a job: python3 refresh.py --why "business intelligence analyst"."""
    if not os.path.exists(DB):
        print("No jobs.db yet. Run python3 refresh.py once to build it."); return 1
    con = db_open()
    q = f"%{query.strip()}%"
    rows = con.execute("SELECT company, title, loc, url, signal, geo, dropped, yrs, degree, internal, closes, posted, first_seen, last_seen, gone_on, source "
                       "FROM jobs WHERE title LIKE ? OR url LIKE ? OR company LIKE ? ORDER BY gone_on IS NOT NULL, company, title LIMIT 60", (q, q, q)).fetchall()
    agg = {src for src, kind in con.execute("SELECT source, kind FROM sources") if aggregator(kind)}
    # The employers this script reads itself, as db_export() works them out: every source that is not a
    # relisting board, and every employer name those sources' own rows carry.
    direct = {src for (src,) in con.execute("SELECT source FROM sources WHERE last_read IS NOT NULL") if src not in agg}
    direct |= {co for co, src in con.execute("SELECT DISTINCT company, source FROM jobs WHERE gone_on IS NULL") if co and src not in agg}
    n_src = con.execute("SELECT COUNT(*) FROM sources WHERE last_read IS NOT NULL").fetchone()[0]
    if not rows:
        print(f'Nothing matching "{query}" has ever been returned by the {n_src} feeds this script reads.')
        print("That means the employer is not a source. Find its careers page, work out which hiring system it uses,")
        print("and add it to MORE (or BOARDS) at the top of refresh.py; the kinds and their slug formats are listed there.")
        return 0
    for (company, title, loc, url, signal, geo, dropped, yrs, degree, internal, closes, posted, first_seen, last_seen, gone_on, source) in rows:
        if gone_on: verdict = f"no longer on the feed (last seen {last_seen})"
        elif source in agg and signal and any(same_company(company, d) for d in direct):
            verdict = f"a copy listed on {source}: NOT published, because this employer's own feed is read and is the truth about its jobs"
        elif internal and signal: verdict = "on the feed and published, but open to internal applicants only: the page lists it under its Internal only chip"
        elif signal == "senior": verdict = f"on the feed and published as an experienced-level role ({dropped}): the page lists it under Level > Experienced" + (f", asks {yrs}+ years" if yrs else "")
        elif signal: verdict = f"KEPT and published as {signal}, {geo}" + (f", asks {yrs}+ years" if yrs else "") + (f", degree bar: {degree}" if degree else "")
        else: verdict = f"on the feed but DROPPED by the title rules: {dropped}"
        print(f"{company[:28]:30} {title[:58]:60} {loc[:24]:26}\n    {verdict}" + (f" · posted {posted}" if posted else "") + (f" · closes {closes}" if closes else "") + f"\n    {url}")
    print(f"\n{len(rows)} row(s). The title rules are near the top of refresh.py (SENIOR, WRONG_COHORT, OFFTOPIC, ENTRYWORD, ONTOPIC).")
    return 0

# ---------- run ----------
def main():
    if "--selftest" in sys.argv: return selftest()
    if "--why" in sys.argv:
        return why(" ".join(sys.argv[sys.argv.index("--why") + 1:]))
    today = datetime.date.today().isoformat()
    sources = list(all_sources())
    # --skip kind,kind and --only kind,kind leave some feeds out of this run (the state job bank alone
    # takes four minutes). What the database holds for them is left exactly as it was.
    flag = lambda name: set(sys.argv[sys.argv.index(name) + 1].split(",")) if name in sys.argv[:-1] else set()
    skip, only = flag("--skip"), flag("--only")
    jobs = [(kind, co, slug) for kind, co, slug, _ in sources if kind not in skip and (not only or kind in only)]
    skipped = [co for kind, co, slug, _ in sources if (kind, co, slug) not in set(jobs)]
    print(f"Checking {len(jobs)} job boards…" + (f" ({len(skipped)} left out on request)" if skipped else ""))

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
    moved = moved_links({u for _, u in dead}, board_openings(html), raw)
    dead = [("moved" if u in moved else code, u) for code, u in dead]

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

    new_roles, gone_roles, first_read = {}, {}, {}
    for co, hits in found.items():
        now  = {h["title"]: h for h in hits}
        was  = set(prev_roles.get(co, []))
        if prev_roles and co not in prev_roles:
            # A source read for the first time has no "last run" to compare with. Listing its whole
            # board as new would bury the roles that really did open this week.
            first_read[co] = hits
        elif prev_roles:
            # Titles are compared without case or punctuation, so a feed that starts writing "DRG" where it
            # wrote "Drg" has not closed one job and opened another.
            was_n, now_n = {_norm(t) for t in was}, {_norm(t) for t in now}
            fresh = [h for t, h in now.items() if _norm(t) not in was_n]
            if fresh: new_roles[co] = fresh
            # A title that is still on the feed but that the rules no longer keep has not closed: the rules changed.
            on_feed = {_norm(r[0]) for r in raw.get(co, [])}
            closed = [t for t in was if _norm(t) not in now_n and _norm(t) not in on_feed]
            if closed: gone_roles[co] = closed
        else:
            if hits: new_roles[co] = hits

    # ---------- database ----------
    con = db_open()
    db_stats = db_sync(con, today, sources, raw, errors, prev_state=prev)
    exported = db_export(con, today, dead=[u for _, u in dead])
    con.close()

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
    add(f"Database: {exported['entry']} live entry-level openings published to jobs.json, plus {exported['senior']} experienced-level roles in "
        f"{HOME_NAME} and {exported['internal']} internal-only postings, {exported['employers']} employers in all "
        f"({exported['leads']} of the rows are state job bank leads at employers not read directly) "
        f"· {db_stats['new']} new since the last run, {db_stats['gone']} gone, {db_stats['moved']} moved to a new link")
    if skipped:
        add(f"({len(skipped)} sources were left out of this run on request; their rows in the database were not touched)")
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
        weak = " [SWE]" if h.get("swe") else ""
        weak += f" [{h['degree']}]" if h.get("degree") else ""
        closes = f" closes {h['closes']}" if h.get("closes") else ""
        return f"{co[:26]:28} {(h['title'][:50] + mark + weak)[:64]:66} {h['loc'][:26]:28} {h['url']}{closes}"

    groups = {"home": [], "remote": [], "program": [], "other": []}
    for co in sorted(new_roles):
        for h in new_roles[co]:
            key = h["geo"] if h["geo"] in ("home", "remote") else ("program" if h["signal"] == "program" else "other")
            groups[key].append((h["loc"], line(co, h)))
    add(""); add(f"NEW ENTRY-LEVEL ROLES ({sum(len(v) for v in groups.values())})   '?years' = no level in the title, so read the posting")
    add("  [SWE] = a software-engineering ladder; [technical majors] and [MS/PhD] are the posting's own degree bar. Weak fits, still listed.")
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

    if first_read:
        rows = [f"{co:34} {len(hits):4} entry-level roles, {sum(h['geo'] == 'home' for h in hits)} in {HOME_NAME}" for co, hits in sorted(first_read.items())]
        block(f"SOURCES READ FOR THE FIRST TIME ({len(first_read)})   their roles are in jobs.json but are not listed above as new", rows)

    rows = [f"{code:5}  {u}" + (f"\n         same title is still posted at  {moved[u][1]}" if code == "moved" else "") for code, u in dead]
    block(f"DEAD LINKS ON YOUR BOARD ({len(dead)})" + ("   'moved' = the title is still on the feed under a new link; re-point it rather than dropping it" if moved else ""), rows)

    # Openings on the board carry the closing date they were published with. Once it passes, the card
    # shows the opening struck through, and this list says which ones to take off.
    past = sorted((c, u) for u, c in re.findall(r'\{[^{}]*?url: "([^"]+)"[^{}]*?closes: "(\d{4}-\d{2}-\d{2})"', " ".join(board_links))
                  if c < today)
    block(f"PAST THEIR CLOSING DATE ON YOUR BOARD ({len(past)})", [f"{c}  {u}" for c, u in past])

    weak = [h for hits in found.values() for h in hits if h.get("swe") or h.get("degree")]
    add(""); add(f"  Of the {len(live)} live roles, {len(weak)} are flagged a weak fit for this resume: "
                 f"{sum(1 for h in weak if h.get('swe'))} software-engineering ladders and "
                 f"{sum(1 for h in weak if h.get('degree'))} whose posting sets a degree bar.")

    if apps:
        rows, blind = audit_applications(apps, found, raw, list(found) + list(errors), list(MANUAL), errors)
        block(f"YOUR APPLICATIONS ({len(apps)}) — could this script have found each one?", rows)
        add("")
        add(f"  Blind spots: {blind['untracked']} at employers not tracked, {blind['manual']} at employers with no readable "
            f"feed, {blind['filtered']} filtered out by the title rules.")
        if blind["untracked"] or blind["manual"]:
            add("  Fix: add the employer to BOARDS (or MANUAL) above. A job you applied to that this script cannot see")
            add("  means the next one like it will be missed too.")

    rows = [f"{co:34} {u['url']}   ({u['why']})" for u in unread() for co in [u["co"]]]
    block("CHECK THESE BY HAND (not read by this script; the page's Search deeper starts with them)", rows)

    if errors:
        block(f"BOARDS THAT DID NOT RESPOND ({len(errors)})",
              [f"{co:34} {e}" for co, e in sorted(errors.items())])
    partial = {co: PARTIAL[slug] for _, co, slug, _ in sources if slug in PARTIAL}
    if partial:
        block(f"BOARDS READ ONLY IN PART ({len(partial)})", [f"{co:34} {why}" for co, why in sorted(partial.items())])

    text = "\n".join(L)
    print("\n" + text)
    open(REPORT, "w", encoding="utf-8").write(text + "\n")
    roles = {co: [h["title"] for h in hits] for co, hits in found.items()}
    for co in list(errors) + skipped:   # carry forward, so its next good run is compared against the last good one
        if co in prev_roles: roles[co] = prev_roles[co]
    json.dump({"date": today, "filter_version": FILTER_VERSION, "roles": roles}, open(STATE, "w"), indent=1)
    print(f"\nSaved to {os.path.basename(REPORT)}")

load_readers()
if __name__ == "__main__":
    sys.exit(main())
