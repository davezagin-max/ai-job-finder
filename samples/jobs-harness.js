// Checks the parts of the page that look past the hand-picked board: the All openings list, Claude's
// ranking of the openings database, and the web search that saves what it finds.
//
// Serve the folder, open the page, then in the console:
//   await import('/samples/jobs-harness.js'); await JobFinderJobsHarness.run();
//
// Every employer and posting here is invented, and the "API" is a stand-in that replays a script, so
// this needs no key and spends nothing. It swaps a small made-up database in for jobs.json while it
// runs and puts the real one back when it finishes.
(function () {
  const J = () => window.JobFinderJobs;
  const T = () => window.JobFinderTailor;
  const $ = id => document.getElementById(id);
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const plain = s => String(s || '').replace(/<[^>]+>/g, '').replace(/&amp;/g, '&').replace(/&ndash;|&mdash;/g, '-').replace(/&[a-z]+;|&#\d+;/g, ' ').replace(/\s+/g, ' ').trim();
  const DAY = '2031-03-10';   // the made-up database's refresh date; "new" is measured from it, not from the clock

  // A scripted stand-in for client.beta.messages.stream(): each call returns the next reply.
  function fakeClient(script) {
    const calls = [];
    return {
      calls,
      beta: { messages: { stream(params) {
        calls.push(JSON.parse(JSON.stringify(params)));
        const step = script[calls.length - 1];
        if (!step) throw Object.assign(new Error('script ran out'), { status: 500 });
        if (step.throws) throw step.throws;
        const msg = Object.assign({ model: params.model, usage: { input_tokens: 10, output_tokens: 10 } }, step);
        return {
          async *[Symbol.asyncIterator]() {
            let i = 0;
            for (const b of msg.content || []) {
              if (b.type === 'tool_use' || b.type === 'server_tool_use') {
                yield { type: 'content_block_start', index: i, content_block: { type: b.type, name: b.name } };
                yield { type: 'content_block_delta', index: i, delta: { type: 'input_json_delta', partial_json: JSON.stringify(b.input || {}) } };
                yield { type: 'content_block_stop', index: i };
              }
              i++;
            }
          },
          finalMessage: async () => msg,
          abort() {},
        };
      } } },
    };
  }

  async function run() {
    const results = [];
    const ok = (group, id, cond, detail) => results.push({ group, id, ok: !!cond, detail: cond ? '' : String(detail ?? '') });
    if (!J() || !T()) throw new Error('Open the page first: JobFinderJobs and JobFinderTailor are not defined here.');

    // ---------- keep what the page had, so it can be put back ----------
    const before = { view: localStorage.getItem('jf.view'), rank: localStorage.getItem('jf.jobRank'), state: Object.assign({}, J().state),
      active: T().activeId ? T().activeId() : null };
    T().applyProfile(null); await sleep(150);

    // ---------- jobKey: one posting, however it is linked ----------
    const k = J().key;
    ok('key', 'a Greenhouse posting has one key however it is linked', k('https://job-boards.greenhouse.io/acme/jobs/8123456') === k('https://www.acme.test/careers/8123456?gh_jid=8123456') && k('https://boards.greenhouse.io/embed/job_app?for=acme&token=1') !== k('https://job-boards.greenhouse.io/acme/jobs/8123456'));
    ok('key', 'a Workday requisition is keyed on its id, with or without a locale or a repost suffix', k('https://acme.wd5.myworkdayjobs.com/en-US/External/job/Salt-Lake-City-UT/Data-Analyst_JR-0042') === k('https://acme.wd5.myworkdayjobs.com/External/job/Salt-Lake-City-UT/Data-Analyst_JR-0042-1'));
    ok('key', 'an id-bearing link is keyed on the id', k('https://jobs.lever.co/acme/0a1b2c3d-1111-2222-3333-444455556666/apply') === k('https://jobs.lever.co/acme/0A1B2C3D-1111-2222-3333-444455556666'));
    ok('key', 'any other link is keyed on host and path, ignoring tracking parameters and a trailing slash', k('https://www.acme.test/jobs/77/?utm=x') === k('http://acme.test/jobs/77') && k('https://acme.test/jobs/77') !== k('https://acme.test/jobs/78'));
    ok('key', 'a link whose job id is in its query string keeps it', k('https://bank.test/single-job?j=11') !== k('https://bank.test/single-job?j=12') && k('https://bank.test/single-job?utm_source=a&j=11') === k('https://bank.test/single-job?j=11'));

    // ---------- a made-up database ----------
    const withOpening = COMPANIES.filter(c => !c.suggested && c.apply.openings.some(o => !isClosed(o)));
    const c0 = withOpening[0], o0 = c0.apply.openings.find(o => !isClosed(o));
    const c1 = withOpening.find(c => c !== c0), o1 = c1.apply.openings.find(o => !isClosed(o));
    const row = (n, extra) => Object.assign({ co: 'Wasatch Ledger Co-op', title: `Fixture Analyst ${n}`, loc: 'Salt Lake City, UT', url: `https://jobs.example.test/ledger/${n}`, geo: 'home', sig: 'entry', field: 'data' }, extra);
    const fixture = {
      date: DAY, prev: '2031-03-03', employers: 3, dead: [o1.url],
      unread: [{ co: 'Granite Peak College', url: 'https://jobs.example.test/granite', why: 'it has no public job feed' },
        { co: 'Shut Gate University', url: 'https://jobs.example.test/shut', why: 'its hiring system asks scripts to stay out' }, { co: 'No Link College', url: 'javascript:alert(1)' }],
      jobs: [
        { co: c0.name, card: c0.name, title: plain(o0.title).toUpperCase(), loc: plain(o0.loc), url: o0.url, geo: 'home', sig: 'entry', field: 'data', yrs: 9 },
        { co: c0.name, card: `${c0.name.replace(/\s*\(.*?\)\s*/g, ' ').trim()} (Fixture Office)`, title: 'Fixture Quality Zebra Coordinator', loc: 'Lehi, UT', url: 'https://jobs.example.test/board/extra-1', geo: 'home', sig: 'entry', field: 'business', posted: '2031-03-08' },
        row(1, { sig: 'program', field: 'finance', posted: '2031-03-07', closes: '2099-01-01' }),
        row(2, { posted: '2031-02-01' }),
        row(3, { seen: DAY, geo: 'remote', loc: 'Remote, US' }),
        row(4, { posted: '2031-03-12' }),
        row(5, { geo: 'remote', loc: 'Remote, US', yrs: 3 }),
        row(6, { geo: 'remote', loc: 'Remote, US' }),
        row(7, { closes: '2000-01-01' }),
        row(8, { geo: 'elsewhere', loc: 'Boise, ID', sig: 'unleveled', swe: 1, field: 'software', title: 'Fixture Software Engineer 8' }),
        row(9, { geo: 'elsewhere', loc: 'Denver, CO', deg: 'MS/PhD', field: 'research', yrs: 2 }),
        row(10, { sig: 'senior', title: 'Fixture Senior Data Architect 10', posted: '2031-03-09' }),
        row(11, { int: 1, title: 'Fixture Reporting Analysts 11' }),
        row(12, { agg: 1, co: 'Canyon Grid Power', src: 'Fixture job bank', title: 'Harness Data Analyst 700', url: 'https://jobbank.example.test/single-job?j=12' }),
        { co: 'No Link Inc', title: 'Missing url' }, null,
      ],
    };
    J().setData(fixture); await sleep(60);
    const all = () => J().all();
    const find = n => all().find(j => j.url === `https://jobs.example.test/ledger/${n}`);

    // ---------- one list from the feeds and the board ----------
    const merged = all().filter(j => j.key === k(o0.url));
    ok('merge', 'a posting on both the board and a feed is listed once', merged.length === 1, merged.length);
    ok('merge', 'the hand-read facts win where both have them', merged[0] && merged[0].hand === true && merged[0].card === c0.name && merged[0].yrs === (typeof o0.yrs === 'number' ? o0.yrs : 9), JSON.stringify(merged[0]));
    const extra = all().find(j => j.url === 'https://jobs.example.test/board/extra-1');
    ok('merge', 'a feed row from a differently named source of the same employer lands on that employer\'s card', extra && extra.card === c0.name && J().source(extra) === 'board', extra && extra.card);
    ok('merge', 'rows with no link or no title are ignored', !all().some(j => j.co === 'No Link Inc'));
    ok('merge', 'an employer with no card is a feed-only source', J().source(find(1)) === 'feed' && !find(1).card);
    ok('merge', 'feedExtras lists what the feed has beyond the hand-read openings', J().feedExtras(c0.name).length === 1 && J().feedExtras(c0.name)[0].url === extra.url, J().feedExtras(c0.name).map(j => j.title).join(' | '));

    // ---------- dead links ----------
    ok('dead', 'a board link the feeds report dead is marked gone and treated as closed', o1.gone === true && isClosed(o1) && o0.gone === false);
    ok('dead', 'a dead board opening is left out of the list', !all().some(j => j.key === k(o1.url)));
    J().setView('employers', false); await sleep(60);
    ok('dead', 'the card says so instead of linking a dead posting as live', ($('grid').innerHTML.match(/no longer posted/g) || []).length === 1);
    const btn = Array.from(document.querySelectorAll('#grid .feed-more')).find(b => b.dataset.co === c0.name);
    ok('cards', 'a card offers the rest of its employer\'s feed', btn && /1 more opening on their job feed/.test(btn.textContent) && /1 new/.test(btn.textContent), btn && btn.textContent);

    // ---------- new, closed, filters ----------
    ok('new', 'posted within seven days of the refresh date is new', J().isNew(find(1)) && J().isNew(find(3)));
    ok('new', 'posted long before the refresh, or dated after it, is not new', !J().isNew(find(2)) && !J().isNew(find(4)));
    ok('new', 'a posting past its closing date is closed, never new', J().closed(find(7)) && !J().isNew(find(7)));
    const st = J().state, count = set => { Object.keys(st).forEach(x => { if (x !== 'sort' && x !== 'shown') st[x] = null; }); Object.assign(st, set); return all().filter(j => J().passes(j, '')).length; };
    const live = count({});
    ok('filter', 'closed postings never pass', live === all().filter(j => !J().closed(j) && !j.int && j.sig !== 'senior').length && !J().passes(find(7), ''));
    ok('filter', 'Where narrows to remote', count({ where: 'remote' }) === all().filter(j => !J().closed(j) && j.geo === 'remote').length && count({ where: 'remote' }) >= 3);
    ok('filter', 'Level narrows to new-grad programs', all().filter(j => J().passes(j, '')).length >= 0 && count({ level: 'program' }) === all().filter(j => !J().closed(j) && j.sig === 'program').length);
    ok('filter', 'Field narrows to one field', count({ field: 'research' }) === 1);
    ok('filter', 'Source separates feed-only employers from the board\'s', count({ source: 'feed' }) === 8 && count({ source: 'bank' }) === 1 && count({ source: 'board' }) === live - 9, `${count({ source: 'feed' })} feed, ${count({ source: 'bank' })} bank, ${live} live`);
    ok('filter', 'Out of reach hides a posting two or more years beyond the candidate', count({ reach: 'on' }) < live && (() => { count({ reach: 'on' }); return !J().passes(find(5), '') && !J().passes(find(9), '') && J().passes(find(6), ''); })());
    ok('filter', 'Weak fits hides software ladders and degree bars', (() => { count({ hideWeak: 'on' }); return !J().passes(find(8), '') && !J().passes(find(9), '') && J().passes(find(1), ''); })());
    ok('filter', 'New this week keeps only new postings', (() => { count({ fresh: 'on' }); return J().passes(find(1), '') && !J().passes(find(2), ''); })());
    ok('filter', 'the search box matches title, employer and place', (() => { count({}); return J().passes(find(8), 'boise') && J().passes(find(8), 'wasatch ledger') && !J().passes(find(8), 'zzzz'); })());
    // ---------- postings that are real but not for most readers ----------
    ok('classes', 'experienced-level titles and internal-only postings are left out of the default list', (() => { count({}); return !J().passes(find(10), '') && !J().passes(find(11), ''); })());
    ok('classes', 'the Experienced chip lists experienced titles alone', (() => { const n = count({ level: 'senior' }); return n === 1 && J().passes(find(10), ''); })());
    ok('classes', 'a search reaches experienced titles too', (() => { count({}); return J().passes(find(10), 'architect') && !J().passes(find(11), 'reporting'); })());
    ok('classes', 'the Internal only chip lists those postings and nothing else', (() => { const n = count({ internal: 'on' }); return n === 1 && J().passes(find(11), '') && !J().passes(find(1), ''); })());
    ok('classes', 'an experienced title with no years stated counts as four years away', (() => { count({ level: 'senior', reach: 'on' }); return !J().passes(find(10), ''); })());
    count({});
    ok('classes', 'neither class is sent to Claude for a new graduate', !T().jobsForPrompt().some(j => j.url === find(10).url || j.url === find(11).url));

    // ---------- leads from a relisting job bank ----------
    const lead = () => all().find(j => j.url === 'https://jobbank.example.test/single-job?j=12');
    ok('leads', 'a job bank row is its own source, not an employer feed', lead() && J().source(lead()) === 'bank' && J().passes(lead(), ''));
    J().setView('jobs', false); count({ source: 'bank' }); J().refresh(); await sleep(60);
    const leadRow = document.querySelector('#joblist .jrow');
    ok('leads', 'it is tagged as a lead and offers a search for the employer\'s own posting', leadRow && /state job bank lead/.test(leadRow.textContent) && !!leadRow.querySelector('a.jfind[href^="https://www.google.com/search?q="]') && /Canyon%20Grid%20Power/.test(leadRow.querySelector('a.jfind').getAttribute('href')), leadRow && leadRow.textContent.slice(0, 200));
    count({});
    const webId = 'default|' + k('https://careers.example.test/jobs/700');
    await J().FoundDB.put([{ id: webId, profile: 'default', key: k('https://careers.example.test/jobs/700'), title: 'Harness Data Analyst 700', co: 'Canyon Grid Power', loc: 'Salt Lake City, UT',
      url: 'https://careers.example.test/jobs/700', geo: 'home', score: 88, why: 'w', evidence: 'e', read: true, foundAt: DAY }]);
    await J().loadFound(); await sleep(40);
    ok('leads', 'once the real posting is found on the web, the lead gives way to it', !lead() && all().some(j => j.web && j.url === 'https://careers.example.test/jobs/700'));
    await J().FoundDB.remove([webId]); await J().loadFound(); await sleep(40);
    ok('leads', 'and comes back when that find is removed', !!lead() && !all().some(j => j.web && /example\.test\/jobs\/700/.test(j.url)));
    J().setView('employers', false);

    // ---------- order: a plain keyword match until Claude ranks ----------
    ok('order', 'the same job scores lower when its posting asks for three more years', J().score(find(5)) < J().score(find(6)), `${J().score(find(5))} vs ${J().score(find(6))}`);
    ok('order', 'a local job outranks the same job far away', J().score(find(2)) > J().score(Object.assign({}, find(2), { geo: 'elsewhere', loc: 'Boise, ID' })));
    ok('order', 'nothing is scored by Claude until it has ranked', J().ranked(find(1)) === null);

    // ---------- one employer's openings, from its card ----------
    // the grid has been redrawn since, so the button is found again rather than reused
    const btn2 = Array.from(document.querySelectorAll('#grid .feed-more')).find(b => b.dataset.co === c0.name);
    if (btn2) btn2.click(); await sleep(80);
    const shownCount = parseInt(($('results-count').textContent.match(/^([\d,]+) of/) || [])[1] || '-1', 10);
    const wantCo = all().filter(j => j.card === c0.name && !J().closed(j)).length;
    ok('cards', 'clicking it opens All openings on that employer alone', J().state.co === c0.name && !$('joblist').hidden && shownCount === wantCo && !$('jco-chip').hidden, `${shownCount} shown, want ${wantCo}`);
    $('jco-chip').click(); await sleep(40);
    ok('cards', 'the employer chip clears the filter', J().state.co === null && $('jco-chip').hidden);

    // ---------- Claude's ranking is checked like everything else it returns ----------
    const list = T().jobsForPrompt();
    ok('rank', 'the list sent to Claude is every listed opening, closed ones left out, in a fixed order', list.length === all().filter(j => !J().closed(j) && !j.web && !j.int && j.sig !== 'senior').length && list.every((j, i) => i === 0 || list[i - 1].key <= j.key));
    const brief = T().candidateBrief(null);
    const rp = T().buildRankParams('claude-sonnet-5-5', 'high', brief, null, list);
    ok('rank', 'the request asks for structured output with adaptive thinking and caches the list', rp.model === 'claude-sonnet-5-5' && rp.thinking.type === 'adaptive' && rp.output_config.effort === 'high' && rp.output_config.format.type === 'json_schema' && rp.system[1].cache_control && !('temperature' in rp) && !('tool_choice' in rp));
    ok('rank', 'each opening is one JSON line carrying what the judgement needs', rp.system[1].text.split('\n').length === list.length + 1 && /"lvl":"program"/.test(rp.system[1].text) && /"yrs":3/.test(rp.system[1].text));
    const i5 = list.findIndex(j => j.url === find(5).url), i9 = list.findIndex(j => j.url === find(9).url), i1 = list.findIndex(j => j.url === find(1).url);
    const items = T().applyRank({ ranked: [{ id: i5, score: 150, why: 'x'.repeat(400) }, { id: i5, score: 61, why: 'duplicate' }, { id: 9999, score: 90, why: 'no such id' },
      { id: 1.5, score: 90, why: 'not an integer' }, { id: i9, score: 97, why: 'two short' }, { id: i1, score: 12, why: 'low' }, null, 'junk'] }, list);
    ok('rank', 'unknown ids, repeats and junk are dropped; scores are clamped to 60-100 and text is capped', Object.keys(items).length === 3 && items[find(5).key].s === 100 && items[find(5).key].why.length === 300 && items[find(1).key].s === 60, JSON.stringify(Object.keys(items)));
    ok('rank', 'a reply that is not a ranking yields nothing rather than an error', Object.keys(T().applyRank(null, list)).length === 0 && Object.keys(T().applyRank({ ranked: 'no' }, list)).length === 0);
    J().saveRank('default', items, { date: DAY }); J().refresh(); await sleep(40);
    ok('rank', 'the seniority ceiling applies to a single job: three years short tops out at 70, two at 80', J().ranked(find(5)).s === 70 && J().ranked(find(9)).s === 80 && J().ranked(find(1)).s === 60, JSON.stringify([J().ranked(find(5)), J().ranked(find(9))]));
    J().setView('jobs', false); await sleep(60);
    const firstRow = document.querySelector('#joblist .jrow .jtitle a');
    ok('rank', 'ranked openings sort above unranked ones', firstRow && [find(9).url, find(5).url].includes(firstRow.getAttribute('href')), firstRow && firstRow.getAttribute('href'));

    // ---------- the web search request ----------
    const D = T().DEPTHS;
    const sp = T().buildSearchParams('claude-sonnet-5-5', 'high', brief, null, D.deep);
    const tool = n => sp.tools.find(t => t.name === n);
    ok('search', 'the request carries web search, page reading and the save tool, capped at the chosen depth', tool('web_search').type === 'web_search_20260209' && tool('web_search').max_uses === D.deep.searches && tool('web_fetch').type === 'web_fetch_20260209' && tool('web_fetch').max_uses === D.deep.reads && tool('save_jobs').strict === true && sp.tools.length === 3);
    ok('search', 'searches are biased to the candidate\'s city, and the brief carries no name', tool('web_search').user_location.city === 'Salt Lake City' && !/Jordan|Kim/.test(JSON.stringify(sp.messages)));
    ok('search', 'Claude is told which employers the database already reads, and a job bank lead does not count as read', /Wasatch Ledger Co-op/.test(sp.system[1].text) && !/Canyon Grid Power/.test(sp.system[1].text));
    const ask = sp.messages[0].content.map(b => b.text || '').join('\n');
    ok('search', 'the search starts from the employers the board could not read, links included, and never passes on a link that is not http', /Not read/.test(ask) && /- Granite Peak College: https:\/\/jobs\.example\.test\/granite/.test(ask) && !/javascript:/.test(ask) && !/No Link College/.test(ask), ask.slice(0, 600));
    ok('search', 'an employer whose site turns automated readers away is named for searching, without a link to spend a page read on', /closed to automated page reads/.test(ask) && /- Shut Gate University(\n|$)/.test(ask) && !/example\.test\/shut/.test(ask), ask.slice(0, 900));
    ok('search', 'and from the job bank leads that suit the candidate', /Leads/.test(ask) && /- Harness Data Analyst 700 \| Canyon Grid Power \| Salt Lake City, UT/.test(ask));
    const b2 = T().candidateBrief({ name: "Sam O'Neil-Park", strip: { status: 'Graduating May 2027', recentRole: 'Analyst intern', stack: 'SQL', target: 'Data roles' }, yearsExperience: 1, city: 'Provo, UT',
      summary: "Present Sam as a data person. Sam's SQL is strong, and O'Neil-Park led a team. Samantha is someone else." });
    ok('search', 'the brief does not carry the person\'s name, even where Claude wrote it into the positioning line', !/\bSam\b/.test(b2) && !/O'Neil/.test(b2) && /the candidate's SQL/.test(b2) && /Samantha/.test(b2) && /May 2027/.test(b2), b2);
    const b3 = T().candidateBrief({ name: 'Morgan Wells', strip: {}, summary: 'Aim Morgan at Morgan Stanley and Wells Fargo analyst programs; Morgan Wells finishes in May 2027.' });
    ok('search', 'a name word that is part of something else is left alone', /Aim the candidate at Morgan Stanley and Wells Fargo/.test(b3) && /; the candidate finishes/.test(b3), b3);
    const b4 = T().candidateBrief({ name: 'Uploaded resume', strip: {}, summary: 'Lead the resume with the SQL project.' });
    ok('search', 'a resume with no name costs the brief no words', /Lead the resume with the SQL project/.test(b4), b4);
    ok('search', 'a tailoring run never hands the resume to the web search', /await searchStage\(client, model, effort, brief, null,/.test(document.documentElement.innerHTML) && !/await searchStage\(client, model, effort, brief, resumeBlock/.test(document.documentElement.innerHTML));
    const far = (() => { const was = PROFILE.city; PROFILE.city = 'Toronto, Canada'; const x = T().buildSearchParams('claude-sonnet-5-5', 'high', brief, null, D.quick).tools[0].user_location; PROFILE.city = was; return x; })();
    ok('search', 'a candidate outside the US is not searched as if in the US', far && far.city === 'Toronto' && !('country' in far), JSON.stringify(far));
    ok('search', 'the save tool refuses extra fields and requires every field', tool('save_jobs').input_schema.additionalProperties === false && tool('save_jobs').input_schema.properties.jobs.items.required.length === 12);
    ok('search', 'depths scale the budget', D.quick.searches < D.standard.searches && D.standard.searches < D.deep.searches);

    // ---------- what may be saved ----------
    const ctx = () => ({ seen: new Set(), read: new Set(), asked: new Set(), keys: new Set(), profile: 'harness', model: 'claude-sonnet-5-5' });
    const c = ctx();
    T().harvestUrls([
      { type: 'text', text: 'recalled, not found: https://careers.example.test/jobs/999' },
      { type: 'web_search_tool_result', content: [{ type: 'web_search_result', url: 'https://careers.example.test/jobs/123', title: 'x' }, { type: 'web_search_result', url: 'https://www.linkedin.com/jobs/view/55', title: 'y' },
        { type: 'web_search_result', url: 'https://careers.example.test/jobs/321', title: 'z' }] },
      { type: 'web_fetch_tool_result', content: { type: 'web_fetch_result', url: 'https://careers.example.test/jobs/456?src=feed' } },
      { type: 'web_fetch_tool_result', content: { type: 'web_fetch_result', url: 'https://careers.example.test/view?id=555' } },
      { type: 'server_tool_use', name: 'web_fetch', input: { url: 'https://careers.example.test/jobs/789' } },
    ], c);
    const job = (url, extra) => Object.assign({ title: 'Harness Data Analyst ' + url.slice(-3), employer: 'Canyon Grid Power', location: 'Salt Lake City, UT', url, work_mode: 'onsite', years_required: -1, degree_bar: '', closes: '', posted: '', score: 88, why: 'w', evidence: 'e' }, extra);
    const sv = T().handleSave({ jobs: [
      job('https://careers.example.test/jobs/123', { score: 150, years_required: 3, closes: '2099-01-01', posted: 'last week', degree_bar: 'Bachelor\'s' }),
      job('https://careers.example.test/jobs/456', { work_mode: 'remote', location: 'Anywhere' }),
      job('https://careers.example.test/jobs/789', { location: 'Portland, OR', score: 3 }),
      job('ftp://careers.example.test/jobs/123'),
      job('https://www.linkedin.com/jobs/view/55'),
      job('https://careers.example.test/jobs/999'),
      job('https://careers.example.test/jobs/321', { title: '' }),
      job('https://careers.example.test/jobs/456', { title: 'Same link again' }),
      job('https://careers.example.test/jobs/321', { title: plain(o0.title), employer: c0.name }),
    ] }, c);
    const rec = u => sv.records.find(r => r.url === u);
    ok('save', 'a posting found or opened in the session is saved', !sv.is_error && sv.records.length === 2 && sv.out.saved.length === 2, JSON.stringify(sv.out));
    ok('save', 'a link Claude only asked to open, a link that is not http, a listing site, a link never seen, and a missing title are rejected with reasons', sv.out.rejected.length === 5 && /has not appeared/.test(sv.out.rejected[0].reason) && /http/.test(sv.out.rejected[1].reason) && /listing site/.test(sv.out.rejected[2].reason) && /has not appeared/.test(sv.out.rejected[3].reason) && /required/.test(sv.out.rejected[4].reason), JSON.stringify(sv.out.rejected));
    ok('save', 'a repeat, and a job the board already has, are turned away as known', sv.out.already_known.length === 2, JSON.stringify(sv.out.already_known));
    ok('save', 'a link seen in results but never opened is saved and flagged as unread', rec('https://careers.example.test/jobs/123').read === false && /no page read/.test(sv.out.saved[0]) && rec('https://careers.example.test/jobs/456').read === true && !rec('https://careers.example.test/jobs/789'));
    ok('save', 'numbers are clamped and only well-formed dates are kept', rec('https://careers.example.test/jobs/123').score === 100 && rec('https://careers.example.test/jobs/456').score === 88 && rec('https://careers.example.test/jobs/123').yrs === 3 && !('yrs' in rec('https://careers.example.test/jobs/456')) && rec('https://careers.example.test/jobs/123').closes === '2099-01-01' && !('posted' in rec('https://careers.example.test/jobs/123')));
    ok('save', 'place is read from the posting: home, remote or elsewhere', rec('https://careers.example.test/jobs/123').geo === 'home' && rec('https://careers.example.test/jobs/456').geo === 'remote');
    const q = T().handleSave({ jobs: [job('https://careers.example.test/view?id=556', { title: 'Query Analyst 556' }), job('https://careers.example.test/view?id=555&utm_source=x', { title: 'Query Analyst 555' }),
      job('https://careers.example.test/jobs/456/apply', { title: 'Longer Path Analyst' })] }, (() => { const c2 = ctx(); c.seen.forEach(x => c2.seen.add(x)); c.read.forEach(x => c2.read.add(x)); return c2; })());
    ok('save', 'a link identified by its query string must match the one that was seen; a longer path to the same page is fine', q.out.saved.length === 2 && q.out.rejected.length === 1 && /556/.test(q.out.rejected[0].title), JSON.stringify(q.out));
    const c3 = ctx();
    T().harvestUrls([
      { type: 'web_fetch_tool_result', content: { type: 'web_fetch_result', url: 'https://boards.example.test/acme' } },
      { type: 'web_fetch_tool_result', content: { type: 'web_fetch_tool_result_error', error_code: 'url_not_allowed' } },
      { type: 'server_tool_use', name: 'web_search', input: { query: 'https://boards.example.test/other/jobs/5' } },
    ], c3);
    const l3 = T().handleSave({ jobs: [job('https://boards.example.test/acme/jobs/4000000001', { title: 'Listing Analyst A' }), job('https://boards.example.test/other/jobs/5', { title: 'Typed Analyst B' })] }, c3);
    ok('save', 'reading a careers listing does not vouch for the postings under it, and a link Claude typed into a search is not a find', l3.out.saved.length === 0 && l3.out.rejected.length === 2, JSON.stringify(l3.out));
    const k2 = J().key;
    ok('key', 'a board id shared by every job on a board is not the job\'s identity', k2('https://ukg.example.test/ACM1/JobBoard/0a1b2c3d-1111-2222-3333-444455556666/OpportunityDetail?opportunityId=7') !== k2('https://ukg.example.test/ACM1/JobBoard/0a1b2c3d-1111-2222-3333-444455556666/OpportunityDetail?opportunityId=8'));
    ok('save', 'a malformed call is answered with an error, not a crash', T().handleSave(null, ctx()).is_error === true && T().handleSave({ jobs: 'x' }, ctx()).is_error === true);

    // ---------- the search loop, against a scripted stand-in for the API ----------
    await J().FoundDB.clear('harness');
    const found = { type: 'web_search_tool_result', tool_use_id: 'srv1', content: [{ type: 'web_search_result', url: 'https://careers.example.test/jobs/700', title: 'Harness posting' }] };
    const paused = [{ type: 'server_tool_use', id: 'srv1', name: 'web_search', input: { query: 'analyst jobs salt lake city' } }, found];
    const save = { type: 'tool_use', id: 'tu1', name: 'save_jobs', input: { jobs: [job('https://careers.example.test/jobs/700'), job('https://careers.example.test/jobs/404')] } };
    const phases = [];
    const good = fakeClient([
      { stop_reason: 'pause_turn', content: paused, usage: { input_tokens: 10, output_tokens: 10, server_tool_use: { web_search_requests: 2, web_fetch_requests: 0 } } },
      { stop_reason: 'tool_use', content: [{ type: 'web_fetch_tool_result', tool_use_id: 'srv2', content: { type: 'web_fetch_result', url: 'https://careers.example.test/jobs/700' } }, save,
        { type: 'tool_use', id: 'tu2', name: 'delete_everything', input: {} }], usage: { input_tokens: 10, output_tokens: 10, server_tool_use: { web_search_requests: 1, web_fetch_requests: 1 } } },
      { stop_reason: 'end_turn', content: [{ type: 'text', text: 'Looked at utilities and credit unions.' }] },
    ]);
    const base = { model: 'claude-sonnet-5-5', effort: 'high', brief, resumeBlock: null, depth: 'quick', profile: 'harness' };
    const t1 = await T().deepSearch(Object.assign({ client: good, hooks: { phase: p => phases.push(p) } }, base));
    ok('loop', 'a paused turn is sent back as it is, with nothing added', good.calls.length === 3 && good.calls[1].messages.length === 2 && good.calls[1].messages[1].role === 'assistant' && good.calls[1].messages[1].content.length === 2);
    const reply = (((good.calls[2] || {}).messages || []).slice(-1)[0] || {}).content || [];
    const body = reply[0] && !reply[0].is_error ? JSON.parse(reply[0].content) : {};
    ok('loop', 'each save call is answered with what was saved and what was rejected', reply.length === 2 && reply[0].tool_use_id === 'tu1' && body.saved.length === 1 && body.rejected.length === 1 && body.session.saved_so_far === 1);
    ok('loop', 'a tool that does not exist is refused', reply[1] && reply[1].tool_use_id === 'tu2' && reply[1].is_error === true);
    ok('loop', 'the tally counts saves, searches and page reads, and keeps the closing summary', t1.saved === 1 && t1.rejected === 1 && t1.searches === 3 && t1.reads === 1 && /utilities/.test(t1.summary) && t1.stopped === '' && t1.cost > 0, JSON.stringify(t1));
    ok('loop', 'progress is reported in plain words', phases.some(p => /^Searching: analyst jobs/.test(p)) && phases.some(p => /Saving/.test(p)), phases.join(' | '));
    const kept = await J().FoundDB.all('harness');
    ok('loop', 'what was saved is in the browser\'s own database, under its profile', kept.length === 1 && kept[0].url === 'https://careers.example.test/jobs/700' && kept[0].read === true && (await J().FoundDB.all('someone-else')).length === 0);
    const refuse = fakeClient([{ stop_reason: 'refusal', content: [], stop_details: { explanation: 'no' } }]);
    ok('loop', 'a refusal ends the run and says so', /declined/.test((await T().deepSearch(Object.assign({ client: refuse }, base))).stopped));
    const cut = fakeClient([{ stop_reason: 'max_tokens', content: [found, save] }]);
    const t3 = await T().deepSearch(Object.assign({ client: cut }, base));
    ok('loop', 'a cut-off reply is never acted on', /cut off/.test(t3.stopped) && t3.saved === 0 && cut.calls.length === 1);
    const greedy = fakeClient(Array.from({ length: 6 }, () => ({ stop_reason: 'pause_turn', content: paused, usage: { input_tokens: 1, output_tokens: 1, server_tool_use: { web_search_requests: 40 } } })));
    const t4 = await T().deepSearch(Object.assign({ client: greedy }, base));
    ok('loop', 'a run that overshoots its budget is stopped', /budget/.test(t4.stopped) && greedy.calls.length === 1, `${greedy.calls.length} calls, ${t4.stopped}`);
    let passed = false;
    try { await T().deepSearch(Object.assign({ client: fakeClient([{ throws: Object.assign(new Error('overloaded'), { status: 529 }) }]) }, base)); } catch (e) { passed = e.status === 529; }
    ok('loop', 'an API error is passed to the caller, not swallowed', passed);
    await J().FoundDB.clear('harness');
    ok('loop', 'clearing a profile\'s finds empties it', (await J().FoundDB.all('harness')).length === 0);

    // ---------- put the page back ----------
    if (before.rank === null) localStorage.removeItem('jf.jobRank'); else localStorage.setItem('jf.jobRank', before.rank);
    Object.assign(J().state, before.state);
    await J().reload(); await sleep(150);
    ok('restore', 'the real database is back and nothing is marked gone that the feeds did not report', J().data().date !== DAY && J().data().loaded === true && !all().some(j => /example\.test/.test(j.url)) && J().ranked(all()[0] || {}) === null || before.rank !== null);
    J().setView(before.view === 'jobs' ? 'jobs' : 'employers', false);
    if (before.active && before.active !== 'default' && T().profiles) { const prev = T().profiles().find(x => x.id === before.active); if (prev) T().applyProfile(prev); }

    const failed = results.filter(r => !r.ok);
    console.table(results.map(r => ({ group: r.group, check: r.id, ok: r.ok ? '✓' : '✗', detail: r.detail })));
    console.log(`${results.length - failed.length} of ${results.length} checks passed${failed.length ? ', ' + failed.length + ' FAILED' : ''}`);
    return { passed: results.length - failed.length, total: results.length, failed };
  }

  window.JobFinderJobsHarness = { run };
})();
