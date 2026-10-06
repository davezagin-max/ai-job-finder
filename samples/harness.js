// Replays every case in samples/cases/ through the page and checks the rules LOGIC.md promises.
//
// Serve the folder, open the page, then in the console:
//   await import('/samples/harness.js'); await JobFinderHarness.run();
//
// The checks are written from LOGIC.md, not from the code, so a change that breaks a documented rule
// fails here even if the code is internally consistent. It needs no API key and spends nothing.
(function () {
  const T = () => window.JobFinderTailor;
  const esc = s => String(s ?? '').replace(/&amp;/g, '&');
  const $ = id => document.getElementById(id);
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  // The built-in board as it stands before any profile is applied, captured by the harness itself
  // rather than borrowed from the page's own bookkeeping.
  let BASE = {};
  async function snapshotBoard() {
    T().applyProfile(null); await sleep(120);
    BASE = Object.fromEntries(COMPANIES.map(c => [c.name, { status: c.apply.status, badges: c.badges.slice(), locType: c.locType, openings: c.apply.openings.slice(), score: c.score }]));
  }

  // LOGIC.md, section 3, step 4: the seniority cap, re-implemented from the table.
  function expectedCap(c, years) {
    const opens = c.apply.openings.filter(o => !isClosed(o));
    if (!opens.length) return { cap: 100, demote: false };
    const easiest = Math.min(...opens.map(o => (typeof o.yrs === 'number' ? o.yrs : 0)));
    const gap = easiest - years;
    return { cap: gap >= 3 ? 70 : gap >= 2 ? 80 : 100, demote: gap >= 2 };
  }

  async function load(name) {
    const r = await fetch(`/samples/cases/${name}.json`, { cache: 'no-store' });
    if (!r.ok) throw new Error(`${name}: HTTP ${r.status}`);
    return r.json();
  }
  const META = { model: 'claude-sonnet-5-5', effort: 'high', usage: { input_tokens: 3000, output_tokens: 20000 }, servedBy: 'claude-sonnet-5-5' };

  function checkProfile(name, data, p, results) {
    const ok = (id, cond, detail) => results.push({ case: name, id, ok: !!cond, detail: cond ? '' : String(detail ?? '') });
    const years = p.yearsExperience;
    const shown = COMPANIES.filter(c => !c.untailored);
    const byName = Object.fromEntries(data.companies.map(r => [r.name, r]));
    const first = p.name.split(/\s+/)[0];

    ok('header: title carries the first name', document.title === `${first}'s AI Job Finder`, document.title);
    ok('header: results count equals shown employers', $('results-count').textContent.startsWith(`${shown.length + SUGGESTED.length} of ${shown.length + SUGGESTED.length}`), $('results-count').textContent);

    // --- seniority cap and model statuses ---
    let capBad = [], statusBad = [], badgeBad = [];
    shown.forEach(c => {
      const row = byName[c.name]; if (!row) return;
      const { cap, demote } = expectedCap(c, years);
      const raw = Math.max(60, Math.min(100, Math.round(row.score)));
      const want = Math.min(raw, cap);
      if (c.score !== want) capBad.push(`${c.name}: page ${c.score}, want min(${raw}, cap ${cap})`);
      // a status the model set survives on a fresh profile; a live role beyond reach drops to watch
      let wantStatus = ['open-now', 'opens-later', 'watch', 'wrong-cohort'].includes(row.status) ? row.status : c.apply.status;
      if (row.status === 'keep') wantStatus = BASE[c.name].status;
      if (demote && wantStatus === 'open-now') wantStatus = 'watch';
      if (c.apply.status !== wantStatus) statusBad.push(`${c.name}: page ${c.apply.status}, want ${wantStatus} (model said ${row.status})`);
      const eff = row.locType === 'keep' || !['local', 'hybrid', 'remote', 'far'].includes(row.locType) ? BASE[c.name].locType : row.locType;
      const wantBadges = (eff === 'local' || eff === 'hybrid' ? ['local'] : []).concat(BASE[c.name].badges.filter(b => b === 'fintech' || b === 'ai-native')).concat(row.toolsMatch ? ['tools-match'] : []);
      if (JSON.stringify(c.badges) !== JSON.stringify(wantBadges)) badgeBad.push(`${c.name}: ${c.badges} vs ${wantBadges}`);
    });
    ok('rule: score = min(model score, seniority cap from the easiest open opening)', !capBad.length, capBad.slice(0, 5).join(' | '));
    ok('rule: statuses (model verdict survives; out-of-reach live role becomes watch)', !statusBad.length, statusBad.slice(0, 5).join(' | '));
    ok('rule: badges = location + board fintech/ai-native + tools-match', !badgeBad.length, badgeBad.slice(0, 5).join(' | '));

    // --- tiers ---
    const all = shown.concat(SUGGESTED);
    const tier1 = all.filter(c => c.tier === 1);
    const eighth = all.map(c => c.score).sort((a, b) => b - a)[7];
    ok('rule: exactly eight Tier 1 cards, the eight highest scores', tier1.length === 8 && tier1.every(c => c.score >= eighth), `${tier1.length} tier-1, 8th score ${eighth}`);

    // --- suggested employers ---
    const sugIn = Array.isArray(data.suggested) ? data.suggested : [];
    ok('rule: suggested employers never duplicate a board employer', !SUGGESTED.some(s => COMPANIES.some(c => sameCompany(c.name, s.name))), SUGGESTED.map(s => s.name).join(', '));
    ok('rule: at most twenty suggested employers', SUGGESTED.length <= 20 && SUGGESTED.length <= sugIn.length, `${SUGGESTED.length} of ${sugIn.length}`);
    const bestBoard = Math.max(...shown.map(shownScore)), bestSug = SUGGESTED.length ? Math.max(...SUGGESTED.map(shownScore)) : -1;
    const firstGroup = ($('grid').querySelector('.group-head') || {}).className || '';
    const wantFirst = bestSug >= bestBoard + 8 ? 'suggested' : null;
    ok('rule: suggested group leads only when its best score beats the board by 8+', wantFirst ? /\bsuggested\b/.test(firstGroup) : !/\bsuggested\b/.test(firstGroup), `best board ${bestBoard}, best suggested ${bestSug}, first group "${firstGroup}"`);
    SUGGESTED.forEach(s => { if (!s.apply.openings.length && s.apply.status !== 'suggested') ok('suggested status', false, s.name); });
    ok('rule: suggested cards link to a search, not a posting', SUGGESTED.every(s => /google\.com\/search/.test(s.careers)));

    // --- geography ---
    const remapped = COMPANIES.some(c => c.locType !== BASE[c.name].locType);
    const localChip = document.querySelector('.chip[data-filter="loc"][data-value="local"]').textContent.trim();
    const hybridChip = document.querySelector('.chip[data-filter="loc"][data-value="hybrid"]').textContent.trim();
    const cityShort = (p.city || '').split(',')[0].trim();
    const remoteFirst = !cityShort && /remote/i.test(p.geoLabel);
    if (remapped) {
      ok('rule: re-mapped board relabels the Where chips to the candidate', localChip === (remoteFirst ? 'Near you' : p.geoLabel) && hybridChip === (cityShort ? `Has ${cityShort} office` : 'Office near you'), `${localChip} / ${hybridChip}`);
      ok('rule: relocate tags are hidden once geography is re-mapped', !document.querySelector('.otag.move'));
      ok('rule: the relocation chip is hidden once geography is re-mapped', document.querySelector('.chip[data-filter="prog"]').hidden);
    } else {
      ok('rule: local mode keeps the Salt Lake chip labels', localChip === 'SLC Area' && hybridChip === 'Has SLC Office', `${localChip} / ${hybridChip}`);
      ok('rule: local mode keeps relocate tags on out-of-state openings', !!document.querySelector('.otag.move'));
    }

    // --- University of Utah extras ---
    ok('rule: career-fair strip and Utes chip only for a University of Utah resume', $('fairs').hidden === !p.uofu && document.querySelector('.chip[data-filter="alumni"]').closest('.filter-group').hidden === !p.uofu);
    const bonusBad = shown.filter(c => c.alumni && shownScore(c) !== Math.min(100, c.score + (p.uofu ? ({ strong: 3, some: 1 })[c.alumni] : 0)));
    ok('rule: +3 / +1 alumni bonus applies only for a University of Utah resume', !bonusBad.length, bonusBad.map(c => c.name).slice(0, 3).join(', '));

    // --- filters ---
    const emptyChipShown = [...document.querySelectorAll('#filters .chip[data-filter="apply"], #filters .chip[data-filter="loc"], #filters .chip[data-filter="ind"]')]
      .filter(ch => !ch.hidden && !all.some(c => ch.dataset.filter === 'apply' ? c.apply.status === ch.dataset.value : ch.dataset.filter === 'ind' ? c.industry.includes(ch.dataset.value) : c.locType === ch.dataset.value));
    ok('rule: a chip that would match nothing is hidden', !emptyChipShown.length, emptyChipShown.map(c => c.textContent.trim()).join(', '));

    // --- new this week ---
    const wantNew = shown.reduce((k, c) => k + c.apply.openings.filter(isNewOpening).length + (c.added === REFRESH_DATE ? 1 : 0), 0);
    const chipText = $('new-chip').innerText.replace(/\s+/g, ' ');
    ok('rule: the New this week count covers only shown employers', (wantNew ? chipText.includes(`(${wantNew})`) : $('new-chip').hidden), `${chipText} vs ${wantNew}`);
    ok('rule: NEW tags render for every new opening on shown employers', document.querySelectorAll('.otag.new').length === shown.reduce((k, c) => k + c.apply.openings.filter(isNewOpening).length, 0));

    // --- untailored employers ---
    const hidden = COMPANIES.filter(c => c.untailored).map(c => c.name);
    const wantHidden = COMPANIES.filter(c => !byName[c.name] && !data.companies.some(r => r.name.trim().toLowerCase() === c.name.toLowerCase())).map(c => c.name);
    ok('rule: employers the profile never scored are hidden, not shown with the owner\'s text', JSON.stringify(hidden) === JSON.stringify(wantHidden), `${hidden} vs ${wantHidden}`);
    if (hidden.length) ok('rule: the footer names the hidden employers', hidden.every(h => document.querySelector('footer').innerText.includes(h)));

    // --- rendering details ---
    const groupsInOrder = [...$('grid').querySelectorAll('.group-head, .card')];
    let order = [], cur = null, sortedBad = false;
    groupsInOrder.forEach(el => { if (el.classList.contains('group-head')) { cur = []; order.push(cur); } else cur.push(+el.querySelector('.score span').textContent); });
    order.forEach(g => { for (let i = 1; i < g.length; i++) if (g[i] > g[i - 1]) sortedBad = true; });
    ok('rule: within each group, cards are sorted by displayed score, highest first', !sortedBad);
    const wrongStrip = document.querySelector('.apply-strip.wrong-cohort strong');
    if (wrongStrip) ok('rule: the wrong-cohort label reads naturally with the profile\'s cohort label', /^Wrong cohort for a (?!a |an |the )\S/.test(wrongStrip.textContent), wrongStrip.textContent);
    ok('rule: tiers use the score before the alumni bonus', all.filter(c => c.tier === 1).every(c => c.score >= eighth));
    const labels = [...document.querySelectorAll('.profile-strip .stat .label, .stat .label')].map(l => l.textContent);
    ok('rule: the header strip is relabeled Status / Most Recent Role / Skills / Target', labels.join() === 'Status,Most Recent Role,Skills,Target', labels.join());
    ok('rule: at most five search links plus the LinkedIn pill', document.querySelectorAll('#quick-links a').length <= 6);
    ok('rule: an active Where filter is dropped when a profile is applied', state.loc === null);
    ok('rule: the active profile id is stored', localStorage.getItem('jf.activeProfile') === p.id);

    // --- applications are independent of the profile ---
    ok('rule: applied tags do not depend on the profile', document.querySelectorAll('.otag.applied').length === shown.reduce((k, c) => k + c.apply.openings.filter(o => appliedTo(c, o)).length, 0));
  }

  async function run() {
    const results = [];
    const ok = (name, id, cond, detail) => results.push({ case: name, id, ok: !!cond, detail: cond ? '' : String(detail ?? '') });
    // What each persona's scenario demands, beyond the generic rules: whether the board must be re-mapped
    // to another metro, whether the person is outside the board's fields (so suggested employers must
    // exist and lead the page), and whether the University of Utah extras may appear.
    const SCENARIOS = {
      'nurse-slc':                 { remap: false, uofu: false, mismatch: true },
      'austin-cs-ms':              { remap: true,  uofu: false, mismatch: false, suggested: true },
      'denver-career-changer':     { remap: true,  uofu: false, mismatch: false, suggested: true, years: 6 },
      'byu-accounting-it-audit':   { remap: false, uofu: false, mismatch: false, suggested: false },
      'bootcamp-remote':           { remap: true,  uofu: false, mismatch: false, suggested: true, remoteFirst: true },
      'experienced-de-slc':        { remap: false, uofu: true,  mismatch: false, suggested: false, years: 5 },
      'profile-predates-employers':{ remap: false, uofu: false, mismatch: true },
      'mech-engineer-logan':       { remap: false, uofu: false, mismatch: true },
      'chemistry-lab-slc':         { remap: false, uofu: true,  mismatch: true },
      'journalism-denver':         { remap: true,  uofu: false, mismatch: true },
      'ux-designer-slc':           { remap: false, uofu: false, mismatch: false, suggested: true },   // adjacent to the board's product roles, not outside them
      'marketing-analytics-boise': { remap: true,  uofu: false, mismatch: false, suggested: true, years: 1 },
      'civil-engineer-intl-phoenix':{ remap: true, uofu: false, mismatch: true, years: 2 },
    };
    const personas = Object.keys(SCENARIOS);
    const activeBefore = localStorage.getItem('jf.activeProfile');
    await snapshotBoard();
    for (const name of personas) {
      const data = await load(name);
      let p;
      try { p = T().buildProfile(data, META); } catch (e) { ok(name, 'buildProfile accepts the case', false, e.message); continue; }
      ok(name, 'buildProfile accepts the case', true);
      ok(name, 'profile: header fields read from the response', p.name === data.profile.name.trim() && p.city === data.profile.city && p.uofu === data.profile.uofu && p.yearsExperience === Math.max(0, data.profile.yearsExperience), JSON.stringify([p.name, p.city, p.uofu, p.yearsExperience]));
      T().applyProfile(p); await sleep(120);
      checkProfile(name, data, p, results);
      // a note survives a newer board while the employer's facts are unchanged; a model 'open-now' on an
      // employer with no openings is accepted on a same-day profile and demoted once the board is newer
      const noOpen = COMPANIES.find(c => !c.untailored && !BASE[c.name].openings.length && p.companies[c.name]);
      if (noOpen) {
        const probe = JSON.parse(JSON.stringify(p));
        probe.companies[noOpen.name].status = 'open-now'; probe.companies[noOpen.name].note = 'TAILORED NOTE PROBE';
        T().applyProfile(probe); await sleep(80);
        ok(name, 'rule: a same-day model verdict of open-now is accepted even with no openings', noOpen.apply.status === 'open-now', noOpen.apply.status);
        probe.boardDate = '2000-01-01';
        T().applyProfile(probe); await sleep(80);
        ok(name, 'rule: once the board is newer, an employer with no openings cannot be a live role', noOpen.apply.status === 'watch', noOpen.apply.status);
        ok(name, 'rule: the tailored note survives a newer board while the employer\'s facts are unchanged', /TAILORED NOTE PROBE/.test(noOpen.apply.note));
        probe.companies[noOpen.name].factSig = 'changed'; T().applyProfile(probe); await sleep(80);
        ok(name, 'rule: the tailored note gives way once the employer\'s facts change', !/TAILORED NOTE PROBE/.test(noOpen.apply.note));
      }
      // a cap can lift: a capped score recovers when the capping opening disappears from the board
      const cappedCo = COMPANIES.find(c => !c.untailored && p.companies[c.name] && p.companies[c.name].capped !== undefined);
      if (cappedCo) {
        const probe = JSON.parse(JSON.stringify(p));
        probe.companies[cappedCo.name].rawScore = 99; probe.companies[cappedCo.name].score = 70;
        T().applyProfile(probe); await sleep(80);
        const { cap } = expectedCap(cappedCo, p.yearsExperience);
        ok(name, 'rule: the re-cap starts from the raw score, so a cap can loosen as well as tighten', cappedCo.score === Math.min(99, cap), `${cappedCo.name}: ${cappedCo.score}, cap ${cap}`);
      }
      T().applyProfile(p); await sleep(100);
      // scenario expectations
      const sc = SCENARIOS[name];
      const remapped = COMPANIES.some(c => c.locType !== BASE[c.name].locType);
      ok(name, `scenario: board ${sc.remap ? 'is' : 'is not'} re-mapped to another metro`, remapped === sc.remap);
      ok(name, `scenario: University of Utah extras ${sc.uofu ? 'shown' : 'absent'}`, $('fairs').hidden === !sc.uofu);
      if (sc.years !== undefined) ok(name, `scenario: ${sc.years} years of experience read from the profile`, p.yearsExperience === sc.years, p.yearsExperience);
      if (sc.mismatch || sc.suggested) ok(name, 'scenario: suggested employers present for a candidate the board does not serve', SUGGESTED.length >= 3, SUGGESTED.length);
      if (sc.suggested === false) ok(name, 'scenario: no suggested employers for a Salt Lake candidate inside the board\'s fields', SUGGESTED.length === 0, SUGGESTED.length);
      if (sc.mismatch) {
        const firstGroup = ($('grid').querySelector('.group-head') || {}).className || '';
        ok(name, 'scenario: field mismatch puts the suggested employers first', /\bsuggested\b/.test(firstGroup), firstGroup);
        const bestBoard = Math.max(...COMPANIES.filter(c => !c.untailored).map(shownScore));
        ok(name, 'scenario: nothing on the researched board scores as a strong fit (85+)', bestBoard < 85, `best board score ${bestBoard}`);
      }
      if (sc.remoteFirst) ok(name, 'scenario: remote-first candidate gets "Near you" / "Office near you" chips', document.querySelector('.chip[data-filter="loc"][data-value="local"]').textContent.trim() === 'Near you');
      if (sc.years >= 2) {
        const capped = COMPANIES.filter(c => !c.untailored && p.companies[c.name] && p.companies[c.name].capped !== undefined && expectedCap(c, 0).cap < 100 && c.score < p.companies[c.name].rawScore);
        ok(name, 'scenario: an experienced candidate is not capped by 2-year openings', !capped.some(c => expectedCap(c, sc.years).cap === 100), capped.map(c => c.name).join(', '));
      }
      // a stale profile: once the board is newer, the board's status wins except wrong-cohort
      const stale = { ...p, boardDate: '2000-01-01' };
      T().applyProfile(stale); await sleep(120);
      const wrong = COMPANIES.filter(c => !c.untailored && c.apply.status !== (p.companies[c.name].status === 'wrong-cohort' ? 'wrong-cohort' : (p.companies[c.name].status === 'open-now' && !BASE[c.name].openings.length ? 'watch' : BASE[c.name].status)) && !(BASE[c.name].openings.length && expectedCap(c, p.yearsExperience).demote));
      ok(name, 'rule: after a newer refresh the board status wins, only wrong-cohort survives', !wrong.length, wrong.map(c => `${c.name}: ${c.apply.status}`).slice(0, 4).join(' | '));
      ok(name, 'rule: the footer warns that the profile predates the re-verification', /re-verified/.test(document.querySelector('footer').innerText));
    }

    // --- hostile output ---
    {
      const data = await load('hostile-output');
      let p;
      try { p = T().buildProfile(data, META); ok('hostile-output', 'buildProfile survives hostile output', true); } catch (e) { ok('hostile-output', 'buildProfile survives hostile output', false, e.message); }
      if (p) {
        const names = data.companies.map(r => r.name);
        ok('hostile-output', 'rule: scores clamped to 60-100', p.companies[names[0]].rawScore === 100 && p.companies[names[1]].rawScore === 60, JSON.stringify([p.companies[names[0]].rawScore, p.companies[names[1]].rawScore]));
        ok('hostile-output', 'rule: unknown enum values fall back to keep', p.companies[names[2]].status === 'keep' && p.companies[names[2]].locType === 'keep');
        ok('hostile-output', 'rule: unknown employers are ignored', !Object.keys(p.companies).some(k => /Totally Fake/.test(k)));
        ok('hostile-output', 'rule: duplicate and loosely spelled names count once', p.matched === new Set(Object.keys(p.companies)).size && p.matched === COMPANIES.length, `${p.matched}`);
        ok('hostile-output', 'rule: a suggestion that is really a board employer is dropped', !p.suggested.some(s => /zions/i.test(s.name)));
        ok('hostile-output', 'rule: at most twenty suggestions, names capped at 80 characters, badges filtered', p.suggested.length === 20 && p.suggested.every(s => s.name.length <= 80 && !s.badges.includes('gold') && s.confidence === 'medium'));
        ok('hostile-output', 'rule: name trimmed, initials capped, bad LinkedIn URL dropped, negative years become 0', p.name === 'Hostile   Output' && p.initials.length <= 3 && p.linkedin === '' && p.yearsExperience === 0, JSON.stringify([p.name, p.initials, p.linkedin, p.yearsExperience]));
        T().applyProfile(p); await sleep(120);
        ok('hostile-output', 'page renders hostile output without script injection', !document.querySelector('#grid script') && document.querySelectorAll('#grid .card').length > 0);
      }
    }
    // --- too few companies ---
    {
      const data = await load('too-few-companies');
      let threw = false, msg = '';
      try { T().buildProfile(data, META); } catch (e) { threw = true; msg = e.message; }
      ok('too-few-companies', 'rule: a run with under 80% of the employers is rejected', threw && /only returned/.test(msg), msg);
    }
    // --- restore ---
    T().applyProfile(null); await sleep(120);
    ok('restore', 'applyProfile(null) restores the built-in board', document.title === 'AI Job Finder' && $('results-count').textContent.startsWith(`${COMPANIES.length} of ${COMPANIES.length}`) && !COMPANIES.some(c => c.untailored));
    if (activeBefore && activeBefore !== 'default') {
      const prev = T().profiles().find(x => x.id === activeBefore);
      if (prev) T().applyProfile(prev);
    }
    const failed = results.filter(r => !r.ok);
    console.table(results.map(r => ({ case: r.case, check: r.id, ok: r.ok ? '✓' : '✗', detail: r.detail })));
    console.log(`${results.length - failed.length} of ${results.length} checks passed${failed.length ? ', ' + failed.length + ' FAILED' : ''}`);
    return { passed: results.length - failed.length, total: results.length, failed };
  }

  window.JobFinderHarness = { run };
})();
