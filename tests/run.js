// Tester för Värdskärm. Kör:  node tests/run.js   (kräver Playwright med Chromium)
// Öppnar index.html som lokal fil, precis som appen används, och kontrollerar hela flödet.
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path'), http = require('http');
const APP = 'file://' + path.resolve(__dirname, '..', 'index.html');
const MANUS = fs.readFileSync(path.join(__dirname, 'manus-exempel.txt'), 'utf8');
let pass = 0; const fails = [];
const ok = (cond, name, extra) => { if (cond) pass++; else { fails.push(name + (extra !== undefined ? ' → ' + JSON.stringify(extra) : '')); console.log('  ✗', name, extra !== undefined ? JSON.stringify(extra) : ''); } };
const eq = (a, b, name) => ok(JSON.stringify(a) === JSON.stringify(b), name, { fick: a, väntade: b });

// Manuset som Google Docs-HTML, med de formateringsfel som har ställt till det:
// "BLOCK 2" som mjuk radbrytning i samma stycke som Background, och rubriker som vanlig text.
function docsHtml(txt) {
  const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;');
  const L = txt.split('\n').map(s => s.trim()).filter(Boolean), out = []; let i = 0, first = true;
  while (i < L.length) {
    const t = L[i];
    if (first) { out.push(`<h1><span>${esc(t)}</span></h1>`); first = false; i++; continue; }
    if (/^(\*|\d+\.)\s/.test(t)) { const it = []; while (i < L.length && /^(\*|\d+\.)\s/.test(L[i])) it.push(`<li><p><span>${esc(L[i].replace(/^(\*|\d+\.)\s+/, ''))}</span></p></li>`), i++; out.push(`<ul>${it.join('')}</ul>`); continue; }
    if (t.startsWith('Background:') && L[i + 1] === 'BLOCK 2') { out.push(`<p><span>${esc(t)}<br><br><br>BLOCK 2</span></p>`); i += 2; continue; }
    if (t === 'BLOCK 3') { out.push(`<p><span><br><br>${t}</span></p>`); i++; continue; }           // rubrik som vanlig text
    if (/^(BLOCK|MOMENT|OUTRO)/.test(t)) { out.push(`<h2><span>${esc(t)}</span></h2>`); i++; continue; }
    if (/^(Core|Guest) questions$/.test(t)) { out.push(`<h3><span>${esc(t)}</span></h3>`); i++; continue; }
    out.push(`<p><span>${esc(t)}</span></p>`); i++;
  }
  return '<meta charset="utf-8"><b id="docs-internal-guid-x" style="font-weight:normal">' + out.join('') + '</b>';
}

// Lokal kopia av relätjänsten ntfy.sh: samma adresser och samma meddelandeformat, plus en strömbrytare för dagsgränsen (429)
function fakeRelay() {
  const topics = {}, subs = {}, state = { posts: 0, deny: false }; let seq = 0;
  const H = { 'access-control-allow-origin': '*' };
  const srv = http.createServer((req, res) => {
    const [, topic, tail] = req.url.split('?')[0].split('/');
    if (req.method === 'OPTIONS') { res.writeHead(204, { ...H, 'access-control-allow-methods': 'GET, POST', 'access-control-allow-headers': '*' }); return res.end(); }
    if (req.method === 'POST') {
      let body = ''; req.on('data', d => body += d); req.on('end', () => {
        state.posts++;
        if (state.deny) { res.writeHead(429, { ...H, 'content-type': 'application/json' }); return res.end('{"code":42908,"http":429,"error":"limit reached: daily message quota reached"}'); }
        const m = { id: 'm' + (++seq), time: Math.floor(Date.now() / 1000), event: 'message', topic, message: body };
        (topics[topic] = topics[topic] || []).push({ m, at: Date.now() });
        (subs[topic] || []).forEach(r => r.write(`data: ${JSON.stringify(m)}\n\n`));
        res.writeHead(200, { ...H, 'content-type': 'application/json' }); res.end(JSON.stringify(m));
      }); return;
    }
    if (tail === 'sse') {
      res.writeHead(200, { ...H, 'content-type': 'text/event-stream', 'cache-control': 'no-cache' });
      res.write(`event: open\ndata: ${JSON.stringify({ id: 'o' + seq, event: 'open', topic })}\n\n`);
      (topics[topic] || []).filter(x => Date.now() - x.at < 20000).forEach(x => res.write(`data: ${JSON.stringify(x.m)}\n\n`));
      (subs[topic] = subs[topic] || []).push(res); req.on('close', () => { subs[topic] = subs[topic].filter(r => r !== res); }); return;
    }
    res.writeHead(404, H); res.end();
  });
  return new Promise(ok => srv.listen(0, '127.0.0.1', () => ok({ url: 'http://127.0.0.1:' + srv.address().port, state, close: () => { Object.values(subs).flat().forEach(r => r.destroy()); srv.close(); } })));
}

(async () => {
  const relay = await fakeRelay();
  const browser = await chromium.launch({ args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'] });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, permissions: ['camera', 'clipboard-read', 'clipboard-write'] });
  await ctx.route(/ntfy\.sh|jsdelivr/, r => r.abort());           // testerna ska inte gå ut på nätet
  const page = await ctx.newPage(); const errs = [];
  page.on('pageerror', e => errs.push('operatör: ' + e.message));
  page.on('dialog', d => d.accept());
  // Nollställ lagringen från värdskärmsläget: operatörsläget sparar sin data när sidan lämnas och skulle skriva tillbaka den
  const fresh = async (settings = {}) => {
    await page.goto('about:blank'); await page.goto(APP + '#display');
    await page.evaluate(([s, r]) => { localStorage.clear(); localStorage.setItem('vh.settings.v1', JSON.stringify(s)); localStorage.setItem('vh.relay', r); }, [{ syncOnRec: false, ...settings }, relay.url]);
    await page.goto('about:blank'); await page.goto(APP); await page.waitForTimeout(250);
  };
  const S = (fn, arg) => page.evaluate(fn, arg);
  const section = n => console.log('• ' + n);

  // ---------------------------------------------------------------- start
  section('Start och navigering');
  await fresh();
  eq(await S(() => activeEp().sections.map(s => s.cards.length)), [3, 1, 1], 'exempelmanuset laddas');
  ok(/Vad gjorde du/.test(await page.textContent('#pvStage .fit-inner')), 'första frågan visas i förhandsvisningen');
  for (let i = 0; i < 2; i++) await page.keyboard.press('ArrowRight');
  await page.keyboard.press('ArrowRight');                         // följdfrågan blir stor
  eq(await S(() => [findCard(live.cardId).card.kind, live.reveal]), ['guest', 1], '→ visar följdfrågan som eget steg');
  ok(await page.$('#pvStage .q-ctx') !== null, 'huvudfrågan tonas ner när följdfrågan visas');
  await page.keyboard.press('ArrowRight');
  for (let i = 0; i < 4; i++) await page.keyboard.press('ArrowRight');
  eq(await S(() => [findCard(live.cardId).card.kind, live.reveal]), ['moment', 4], 'momentet visar ett alternativ i taget');
  await page.keyboard.press('ArrowRight'); await page.keyboard.press('ArrowRight');
  eq(await S(() => findCard(live.cardId).card.kind), 'script', 'stannar på sista kortet');
  await page.keyboard.press('ArrowLeft');
  eq(await S(() => [findCard(live.cardId).card.kind, live.reveal]), ['moment', 4], '← går ett steg bakåt');
  await page.keyboard.press('Home');
  await page.locator('.rd-card .rd-skip').nth(1).click({ force: true });
  await page.keyboard.press('ArrowRight');
  ok(/Du har bytt bransch/.test(await S(() => findCard(live.cardId).card.text)), 'överhoppat kort hoppas över');
  await page.locator('.rd-card .rd-skip').nth(1).click({ force: true });
  await page.keyboard.press('-');
  eq(await S(() => findCard(live.cardId).card.scale), 0.9, '− minskar textstorleken för kortet');
  await page.keyboard.press('b'); ok(await page.$('#pvStage .st-black') !== null, 'B ger standby'); await page.keyboard.press('b');

  // ---------------------------------------------------------------- värdskärm
  section('Värdskärmen');
  const [disp] = await Promise.all([page.waitForEvent('popup'), page.click('#conn')]);
  disp.on('pageerror', e => errs.push('värdskärm: ' + e.message));
  await disp.waitForTimeout(700);
  eq(await page.textContent('#conn span'), 'Värdskärm ansluten', 'operatören ser att värdskärmen är ansluten');
  await disp.evaluate(() => { window._n = 0; const set = Object.getOwnPropertyDescriptor(Element.prototype, 'innerHTML').set; Object.defineProperty(document.querySelector('#dStage .st-c'), 'innerHTML', { set(v) { window._n++; set.call(this, v); }, get() { return ''; } }); });
  await page.bringToFront(); await page.keyboard.press('End'); await disp.waitForTimeout(600);
  await disp.evaluate(() => { window._n = 0; }); await page.keyboard.press('Home'); await disp.waitForTimeout(120);
  const r = await disp.evaluate(() => ({ n: window._n, w: document.querySelectorAll('#dStage .st-c:not(.st-out) .w').length }));
  eq(r.n, 1, 'värdskärmen ritas om exakt en gång per steg (annars bryts animationen)');
  ok(r.w > 3, 'orden animeras in på värdskärmen', r.w);
  await disp.keyboard.press('ArrowRight'); await page.waitForTimeout(200);
  ok(/Vilken regel/.test(await S(() => findCard(live.cardId).card.text)), 'tangenter i värdskärmens fönster styr operatören');
  await page.keyboard.press('3'); await disp.waitForTimeout(150);
  eq(await disp.textContent('.cue'), 'Avrunda', 'meddelande till programledaren visas på värdskärmen');
  await page.keyboard.press('Escape');
  // två sändningar inom samma millisekund ska komma fram i rätt ordning
  await S(() => { for (let i = 0; i < 30; i++) { live.cue = { text: 'x' + i, ts: Date.now(), ttl: 0 }; broadcast(); } }); await disp.waitForTimeout(200);
  eq(await disp.textContent('.cue'), 'x29', 'sista sändningen vinner även när många skickas samtidigt');
  await S(() => clearCue());
  await disp.close();

  // ---------------------------------------------------------------- redigering
  section('Redigering');
  await page.click('[data-view=edit]');
  await page.fill('[data-card] textarea[data-f=text]', 'Ändrad första fråga?');
  await page.waitForTimeout(350);
  eq(await S(() => JSON.parse(localStorage.getItem('vh.data.v1')).episodes[0].sections[0].cards[0].text), 'Ändrad första fråga?', 'ändringar sparas automatiskt');
  const before = await S(() => allCards().length);
  await S(() => go(allCards()[1].id, 0));
  await page.click(`[data-card="${await S(() => live.cardId)}"] [data-a=card-del]`);
  eq(await S(() => allCards().length), before - 1, 'kort kan tas bort');
  ok(/Du har bytt bransch/.test(await S(() => findCard(live.cardId).card.text)), 'när aktuellt kort tas bort går appen till nästa kort, inte till början');
  await page.click('#toast [data-a=undo]');
  eq(await S(() => allCards().length), before, 'Ångra återställer kortet');
  for (let i = 0; i < 3; i++) { await page.click('[data-a=settings]'); await page.click('[data-a=modal-close]'); }
  await page.click('[data-a=settings]');
  await S(() => { window._b = 0; const o = broadcast; window.broadcast = function () { window._b++; return o.apply(this, arguments); }; });
  await page.click('[data-s=showNext]');
  ok(await S(() => window._b) <= 2, 'inställningarnas lyssnare dubbleras inte när fönstret öppnas flera gånger', await S(() => window._b));
  await S(() => { settings.tcSync = { t0: Date.now(), baseFrames: 0, fps: '25', method: 'manuellt', at: Date.now() }; settings.phoneSession = 'abc'; saveSettings(); });
  await page.click('[data-a=settings-reset]');
  eq(await S(() => [!!settings.tcSync, settings.phoneSession, settings.showNext]), [true, 'abc', true], '"Återställ standard" behåller synk och parning');

  // ---------------------------------------------------------------- import
  section('Import från Google Docs');
  const want = [['BLOCK 1 (WARM-UP)', 4], ['BLOCK 2', 3], ['MOMENT – Blind rank', 1], ['BLOCK 3', 2], ['OUTRO', 1]];
  for (const [label, html] of [['formaterad text', docsHtml(MANUS)], ['ren text', null]]) {
    await page.click('[data-view=edit]'); await page.click('[data-a=import]');
    if (html) await S(([h, t]) => { const dt = new DataTransfer(); dt.setData('text/html', h); dt.setData('text/plain', t); document.querySelector('#impText').dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true })); }, [html, MANUS]);
    else await page.fill('#impText', MANUS);
    await page.click('[data-a=imp-new]'); await page.waitForTimeout(150);
    const ep = await S(() => activeEp());
    eq(ep.sections.map(s => [s.title, s.cards.length]), want, `${label}: alla block hittas med rätt antal kort`);
    eq([ep.title, ep.guest, ep.guestTitle], ['Testprogrammet S1-EP01', 'Anna Exempel', 'VD, Exempelbolaget'], `${label}: titel och gäst`);
    const c = ep.sections[0].cards;
    eq([c[0].recurring, c[2].kind, c[2].followUp], [true, 'guest', 'What would you do differently?'], `${label}: ↻ och följdfråga`);
    eq([c[3].text, c[3].followUp, /2016/.test(c[3].background), /BLOCK/.test(c[3].background)], ['You moved here ten years ago.\nWhat surprised you the most?', 'And what still does?', true, false], `${label}: inledning + fråga blir ett kort, bakgrunden sväljer inte nästa rubrik`);
    eq([ep.sections[2].cards[0].kind, ep.sections[2].cards[0].list], ['moment', ['Cash', 'Card', 'A check']], `${label}: moment med lista`);
    eq([ep.sections[3].cards[1].kind, ep.sections[4].cards[0].kind], ['core', 'script'], `${label}: avslutningsfrågan är en kärnfråga, outrot är manus`);
  }

  // ---------------------------------------------------------------- tidskod
  section('Tidskodsmatte');
  const tc = await S(() => {
    const out = { rt: true, code: [], bad: [] };
    for (const fps of Object.keys(FPS)) {
      const [nom, real] = FPS[fps];
      for (const s of ['00:00:00:00', '09:59:59:' + String(nom - 1).padStart(2, '0'), '23:59:59:00']) if (framesToTC(parseTC(s, nom), nom) !== s) out.rt = false;
      let worst = 0;
      for (let i = 0; i < 400; i++) {
        const t = 1.7e12 + Math.random() * 4e10, F = Math.floor(Math.random() * nom * 86400), later = t + Math.random() * 3 * 3600e3;
        const r = readSyncCode(makeSyncCode(t, F, fps)); if (!r || r.fps !== fps) { out.bad.push(fps); break; }
        const D = tcDayMs(fps), got = ((later % D) + r.dms) / 1000 * real, exp = F + (later - t) / 1000 * real, day = nom * 86400;
        let d = ((got - exp) % day + day) % day; if (d > day / 2) d -= day; worst = Math.max(worst, Math.abs(d));
      }
      out.code.push([fps, +worst.toFixed(2)]);
    }
    out.typo = readSyncCode('ABC-DEFG') === null && readSyncCode('') === null;
    out.parse = [parseTC('10:32:18:12', 25), parseTC('10321812', 25), parseTC('10:32:18:25', 25), parseTC('25:00:00:00', 25)];
    return out;
  });
  ok(tc.rt, 'tidskod ↔ rutor går jämnt upp för alla bildfrekvenser');
  ok(tc.bad.length === 0 && tc.code.every(([, w]) => w < 0.1), 'synkkoden från mobilen ger rätt tidskod för alla bildfrekvenser (även 23.976/29.97/59.94)', tc.code);
  ok(tc.typo, 'felskriven synkkod avvisas');
  eq(tc.parse, [948462, 948462, null, null], 'inmatad tidskod tolkas och orimliga värden avvisas');

  // ---------------------------------------------------------------- logg
  section('Logg och export');
  await fresh();
  await page.click('[data-view=edit]'); await page.click('[data-a=import]'); await page.fill('#impText', MANUS); await page.click('[data-a=imp-new]');
  await page.click('[data-view=live]'); await page.keyboard.press('Home');
  const T0 = Date.now();
  // Kör loggen med styrd klocka så att tiderna blir förutsägbara
  await S(t0 => { window._now = t0; const real = Date.now; Date.now = () => window._now; window._tick = s => { window._now += s * 1000; }; }, T0);
  await S(() => applySyncFrames(Date.now(), parseTC('10:00:00:00', 25), '25', 'manuellt', true));
  await S(() => { toggleRec(); _tick(20); next(); _tick(1); next(); _tick(30); logTag(0); _tick(40); next(); _tick(25); });   // F1 20 s, F2 1 s (förbi), F3 30 s + tagg …
  await S(() => { next(); _tick(3); logTag(0); _tick(50); addEntry({ kind: 'note', text: '=SUMMA(A1) rolig | historia' }); sendCue('Ta om frågan'); _tick(10); toggleRec(); });
  await S(() => { _tick(60); logTag(3); _tick(5); toggleRec(); _tick(15); toggleRec(); });                                   // tagg utanför REC, sedan klipp 2
  const L = await S(() => epLog());
  eq(L.clips.map(c => [c.n, c.startTc, c.endTc, !!c.sync]), [[1, '10:00:00:00', '10:02:59:00', true], [2, '10:04:04:00', '10:04:19:00', true]], 'klipp får start- och sluttidskod');
  const md = await S(() => buildMarkdown('12 minuter'));
  const has = (re, name) => ok(re.test(md), name);
  has(/\*\*F1\. When did you last change your mind\?\*\* _\(Kärnfråga\)_\n- På skärm `10:00:00:00` → `10:00:20:00` \(K1 \+0:00, 0:20\)/, 'export: fråga med tid på skärm, relativ tid och längd');
  has(/\*\*F2\.[^\n]*\n- _Ingen loggad tid/, 'export: fråga som bara passerades (1 s) räknas inte som ställd');
  has(/- På skärm `10:00:21:00` → `10:01:56:00` \(K1 \+0:21, 1:35\)\n- `10:00:51:00` \(K1 \+0:51\) \*\*Bra svar\*\*\n- `10:01:31:00` \(K1 \+1:31\) Följdfråga: What would you do differently\?/, 'export: tagg och följdfråga under rätt fråga');
  has(/`10:01:59:00` \(K1 \+1:59\) \*\*Bra svar\*\* ⚠ 3 s efter byte från F3 – kan gälla F3/, 'export: tagg strax efter frågebyte flaggas mot föregående fråga');
  has(/Kommentar: =SUMMA\(A1\) rolig \| historia/, 'export: kommentar med');
  has(/Till värden: Ta om frågan/, 'export: meddelanden till värden med');
  has(/`10:03:59:00` \(–\) \*\*Klipp bort\*\*/, 'export: rader utanför REC saknar relativ tid');
  has(/\| K1 \| 10:00:00:00 \| 10:02:59:00 \| 2:59 \| K1 \+0:00 = 10:00:00:00 \|/, 'export: klipptabell');
  has(/- \*\*Mållängd:\*\* 12 minuter/, 'export: mållängden står med');
  has(/\*\*Steg 5 – Premiere-struktur\.\*\*[\s\S]*`Anna Exempel` > `BLOCK 1 \(WARM-UP\)`, `BLOCK 2`/, 'export: Premiere-strukturen byggs av gäst och sektioner');
  has(/\| 10:02:49:00 \| K1 \+2:49 \| F4 \| Kommentar: =SUMMA\(A1\) rolig \\\| historia \|/, 'export: tidslinjen tål lodstreck i text');
  const J = (() => { try { return JSON.parse(md.split('```json\n')[1].split('\n```')[0]); } catch (e) { return null; } })();
  ok(J && J.log.length === L.entries.length && J.script[0].cards[0].f === 'F1' && J.clips.length === 2, 'export: JSON-blocket går att läsa och innehåller hela loggen');
  ok(!/undefined|NaN|\[object/.test(md), 'export: inga trasiga värden');
  await S(() => { const L = epLog(); L.notes = 'Värden bad om nästa fråga tidigt.'; L.transcript = { id: 't', fps: 25, sources: [{ path: '/vol/A001.MXF', start_tc: '10:00:00:00' }], turns: [{ tc: '10:00:22:10', speaker: 'Värd', text: 'You have run three companies.' }, { tc: '10:00:55:00', speaker: 'Anna', text: 'The first one taught me patience.' }] }; });
  const md2 = await S(() => buildMarkdown(''));
  ok(/## Inspelningsnoteringar[^\n]*\n\nVärden bad om nästa fråga tidigt\./.test(md2), 'export: inspelningsnoteringar med');
  ok(/## Transkript med logg[\s\S]*`10:00:21:00` ▸ _På skärm: F3_  \n`10:00:22:10` \*\*Värd:\*\* You have run three companies\.  \n`10:00:51:00` ⟡ \*\*\[Bra svar\]\*\* _\(loggad på F3\)_  \n`10:00:55:00` \*\*Anna:\*\*/.test(md2), 'export: transkriptet flätas ihop med loggen i tidsordning');
  ok(/Synk behövs inte/.test(md2) && !/Synk behövs inte/.test(md), 'export: instruktionen anpassas efter om transkript finns');
  await S(() => { const L = epLog(); delete L.transcript; L.notes = ''; });
  const csv = await S(() => buildCsv());
  ok(/"'=SUMMA\(A1\) rolig \| historia"/.test(csv) && csv.startsWith('﻿"Tidskod";"Klipp";"Tid in i klippet"'), 'csv: formler oskadliggörs, rubriker stämmer');
  // synk under REC räknar om hela det pågående klippet, tidigare klipp rörs inte
  await S(() => { toggleRec(); _tick(10); logTag(1); _tick(5); applySyncFrames(Date.now(), parseTC('01:00:15:00', 25), '25', 'mobil', true); _tick(5); toggleRec(); });
  const L2 = await S(() => epLog());
  eq([L2.clips[2].startTc, L2.clips[2].endTc, L2.clips[2].sync.own, L2.clips[0].startTc, L2.entries.filter(e => e.clip === 3 && e.kind === 'tag')[0].tc],
    ['01:00:00:00', '01:00:20:00', true, '10:00:00:00', '01:00:10:00'], 'synk under REC räknar om pågående klipp och lämnar tidigare klipp orörda');
  // kort som tas bort: loggraderna försvinner inte ur exporten
  await S(() => { const f = findCard(epLog().entries.find(e => e.kind === 'note').cardId); f.sec.cards = f.sec.cards.filter(c => c !== f.card); });
  ok(/## Övriga anteckningar[\s\S]*=SUMMA\(A1\)/.test(await S(() => buildMarkdown(''))), 'export: rader för borttagna kort hamnar under Övriga anteckningar');
  await S(() => { Date.now = () => window._now; });
  // gränssnittet: REC-knapp, taggknapp, kommentar med tidskod från när man började skriva
  await fresh();
  await page.keyboard.press('r'); await page.keyboard.press('Shift+Digit2'); await page.keyboard.press('c'); await page.keyboard.type('Bra anekdot'); await page.keyboard.press('Enter'); await page.keyboard.press('r');
  eq(await S(() => epLog().entries.map(e => e.kind + (e.tag ? ':' + e.tag : ''))), ['rec', 'card', 'tag:Bra tagning', 'note', 'stop'], 'R, Shift+siffra och C loggar rätt rader');
  await page.click('.lg-row.k-tag .lg-text'); await page.keyboard.type('andra halvan'); await S(() => renderLog()); await page.keyboard.type(' bäst'); await page.keyboard.press('Enter');
  eq(await S(() => epLog().entries.find(e => e.kind === 'tag').note), 'andra halvan bäst', 'notering som skrivs försvinner inte när listan ritas om');
  await page.click('[data-a=log-export]');
  ok((await page.textContent('#exPre')).includes('## Manus med logg'), 'exportfönstret visar underlaget');
  await page.click('[data-a=ex-copy]'); await page.waitForTimeout(200);
  ok((await S(() => navigator.clipboard.readText())).startsWith('# Grovklippsunderlag'), 'Kopiera lägger underlaget i urklipp');
  await page.click('[data-a=modal-close]');

  // ---------------------------------------------------------------- backup, typsnitt, omstart
  section('Backup, typsnitt och omstart');
  const font = ['/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', '/System/Library/Fonts/Supplemental/Arial Bold.ttf'].find(f => fs.existsSync(f));
  if (font) {
    await page.click('[data-a=settings]');
    const [fc] = await Promise.all([page.waitForEvent('filechooser'), page.click('[data-a=font-add]')]);
    await fc.setFiles(font); await page.waitForTimeout(400);
    eq(await S(() => getFonts().faces.map(f => f.weight)), [700], 'typsnittsfil läses in och vikten känns igen');
    ok(await S(() => document.fonts.check('700 20px "VH Custom"')), 'typsnittet används på sidan');
    await page.click('[data-a=modal-close]');
  } else console.log('  (hoppar över typsnittstestet: ingen typsnittsfil hittad)');
  await page.click('[data-view=edit]');
  const [dlf] = await Promise.all([page.waitForEvent('download'), page.click('[data-a=export]')]);
  const backup = JSON.parse(fs.readFileSync(await dlf.path(), 'utf8'));
  ok(backup.data.episodes.length === 1 && !!backup.logs && Array.isArray(backup.fonts.faces), 'backupen innehåller manus, logg och typsnitt', { ep: backup.data.episodes.length, keys: Object.keys(backup) });
  const snap = await S(() => JSON.stringify([data, logs]));
  await fresh({ phoneSession: 'egen', hostName: 'X' }); await page.click('[data-view=edit]');
  backup.settings.phoneSession = 'annan'; backup.settings.tcSync = { t0: 1, baseFrames: 0, fps: '25', method: 'manuellt', at: 1 };
  const tmp = path.join(require('os').tmpdir(), 'vh-backup-test.json'); fs.writeFileSync(tmp, JSON.stringify(backup));
  const [fc2] = await Promise.all([page.waitForEvent('filechooser'), page.click('[data-a=import-json]')]);
  await fc2.setFiles(tmp); await page.waitForTimeout(400); fs.unlinkSync(tmp);
  eq(await S(() => JSON.stringify([data, logs])), snap, 'backup som läses in ger exakt samma manus och logg');
  eq(await S(() => [settings.phoneSession, settings.tcSync]), ['egen', null], 'backupen skriver inte över den här datorns synk och parning');
  if (font) eq(await S(() => getFonts().faces.length), 1, 'typsnittet följer med backupen');
  await S(() => go(allCards()[2].id, 1)); await page.reload(); await page.waitForTimeout(250);
  eq(await S(() => [allCards().indexOf(findCard(live.cardId).card), live.reveal]), [2, 1], 'läget finns kvar efter omstart');
  // REC som blivit kvar sedan i går avslutas vid start
  await S(() => { const L = epLog(); L.entries = []; L.clips.push({ n: 9, startMs: Date.now() - 30 * 3600e3, startTc: '00:00:00:00', endMs: null, endTc: '' }); live.rec = { on: true, clip: 9, lastKey: null }; saveLog(); saveLive(); });
  await page.reload(); await page.waitForTimeout(250);
  eq(await S(() => [live.rec.on, !!epLog().clips.find(c => c.n === 9).endMs]), [false, true], 'REC som blivit kvar från ett tidigare pass avslutas vid start');

  // ---------------------------------------------------------------- mobilsidan
  section('Mobilsidan');
  const ph = await ctx.newPage(); ph.on('pageerror', e => errs.push('mobil: ' + e.message));
  await ph.setViewportSize({ width: 390, height: 844 });
  await ph.goto(APP + '#phone&s=testkanal&f=25'); await ph.waitForTimeout(900);
  ok(await ph.$('#syAutoBtn') !== null && await ph.evaluate(() => document.querySelector('#syVid').videoWidth > 0), 'mobilsidan startar med kameran igång');
  await ph.close();

  // ---------------------------------------------------------------- mobilsynk via relä
  section('Mobilsynk via relätjänsten');
  await fresh({ syncOnRec: true });
  await page.click('#syncBtn'); await page.click('[data-sy=phone]'); await page.waitForTimeout(300);
  const sess = await S(() => settings.phoneSession);
  ok(/^[0-9a-z]{12}$/.test(sess), 'datorn skapar en slumpad kanal för parningen', sess);
  const mob = await ctx.newPage(); mob.on('pageerror', e => errs.push('mobil: ' + e.message));
  await mob.goto(APP + '#phone&s=' + sess + '&f=25');
  await page.waitForFunction(() => /Mobilen är parad/.test(document.querySelector('#phConnL').textContent), null, { timeout: 8000 }).catch(() => {});
  ok(/Mobilen är parad/.test(await page.textContent('#phConnL')), 'mobilen hör av sig och datorn visar att den är parad');
  eq(await mob.textContent('#phConn'), '● Ansluten', 'mobilen visar att den har kontakt');
  // Avläsningen ersätts av ett fast värde: kameran visar 05:00:00:00 just nu
  await mob.evaluate(() => { syncAuto = () => applySyncFrames(Date.now(), parseTC('05:00:00:00', 25), '25', 'automatisk avläsning'); });
  await page.click('[data-a=modal-close]');
  relay.state.posts = 0;
  await page.keyboard.press('r');                                   // REC → datorn ber mobilen synka
  await page.waitForFunction(() => document.querySelector('#modal').hidden && settings.tcSync && settings.tcSync.method === 'mobil', null, { timeout: 8000 }).catch(() => {});
  eq(await S(() => [settings.tcSync && settings.tcSync.method, tcAt(Date.now()).slice(0, 7), epLog().clips[0].sync.own, document.querySelector('#modal').hidden]), ['mobil', '05:00:0', true, true], 'REC på datorn → mobilen läser av → datorn synkas och fönstret stängs');
  await mob.waitForFunction(() => /tagit emot/.test((document.querySelector('#phAck') || {}).textContent || ''), null, { timeout: 5000 }).catch(() => {});
  ok(/tagit emot/.test(await mob.textContent('#phAck')), 'mobilen får kvittens från datorn');
  eq(relay.state.posts, 4, 'en synk kostar fyra meddelanden (inga pingar som äter upp dagsgränsen)');
  await mob.waitForTimeout(1200); eq(relay.state.posts, 4, 'inga meddelanden skickas mellan synkarna');
  // dagsgränsen nådd: båda sidor säger till, och koden fungerar för hand
  relay.state.deny = true;
  await page.keyboard.press('r'); await S(() => setSync(null));
  await page.click('#syncBtn'); await page.click('[data-sy=phone]'); await page.click('[data-a=ph-req]'); await page.waitForTimeout(500);
  ok(/dagsgränsen/.test(await page.textContent('#phConnL')), 'datorn säger till när relätjänsten avvisar meddelandet');
  await mob.evaluate(() => syncAuto()); await mob.waitForTimeout(500);
  ok(/Skriv in koden/.test(await mob.textContent('#phAck')), 'mobilen säger till och visar koden att skriva in');
  await page.fill('#phCode', (await mob.textContent('.ph-code')).toLowerCase()); await page.click('[data-a=ph-code]');
  eq(await S(() => [settings.tcSync && settings.tcSync.method, tcAt(Date.now()).slice(0, 6)]), ['kod från mobilen', '05:00:'], 'koden från mobilen kan skrivas in för hand');
  relay.state.deny = false; await mob.close();

  eq(errs, [], 'inga skriptfel i något fönster');
  await browser.close(); relay.close();
  console.log(`\n${pass} kontroller godkända, ${fails.length} underkända`);
  if (fails.length) { console.log(fails.map(f => ' - ' + f).join('\n')); process.exit(1); }
})().catch(e => { console.error('Testkörningen avbröts:', e); process.exit(2); });
