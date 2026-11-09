/*
 * LIBI for Home Assistant - Copyright (C) 2026 Guy Azria - GPL-3.0-or-later
 * What the Online pages share (test_panel_online*.html): a Home Assistant whose states, time and traces are those of a
 *   moment of trace_fixture.js - real runs of a real Home Assistant - whose trace/list and trace/get answer as Home
 *   Assistant's do, and which records every service call and config API call; and the panel on it, with the captured
 *   NETs, Online on. Not a test page itself: the runner runs test_*.html only. trace/list without an item answers every
 *   automation's runs (state.listAllFails: as a Home Assistant that wants the item).
 * [CHANGED v1.1.0 | 2026-11-07] Purpose: libi/online_fire answers as LIBI's backend does (tests/test_online_fire.py runs
 *   the real one): state.fire(message) - by default a run it would start, of the trigger asked for, and with fire set
 *   and the before it gave, started. The run's line under a block (.live-run) is what markOf reads; openMenu and
 *   menuText are a block's Online menu.
 * [CHANGED v1.2.0 | 2026-11-09] Purpose: roomChecks - the user's screenshot: under a time trigger in Traces, RUN and
 *   IN1 showed and IN2 was cut off by the end of the NET's drawing. Every line under every block inside the drawing and
 *   clear of every other block, with four lines under a trigger, in both directions; editing keeps its layout.
 */
import '../../custom_components/libi/frontend/libi-panel.js';
import { CAPTURE } from './trace_fixture.js';

export { CAPTURE };
export const sleep = (ms) => new Promise(r => setTimeout(r, ms));
export const until = async (cond, ms = 3000) => { const end = Date.now() + ms; while (!cond() && Date.now() < end) await sleep(10); return cond(); };
export const clockOf = (seconds) => {
  const s = Math.max(0, Math.ceil(Number(seconds) || 0));
  const p = (n) => String(n).padStart(2, '0');
  return `${p(Math.floor(s / 3600))}:${p(Math.floor((s % 3600) / 60))}:${p(s % 60)}`;
};

/** What LIBI's backend answers libi/online_fire with, for an automation it would run. */
export function firePlan(m) {
  const trigger = m.trigger !== undefined && m.trigger !== null ? { idx: m.trigger, id: m.trigger_id || String(m.trigger), kind: 'state', alias: '' }
    : m.trigger_id ? { idx: 0, id: m.trigger_id, kind: 'state', alias: '' }
    : m.element_id ? { idx: 0, id: '0', kind: 'time', alias: '' } : null;
  const plan = { ok: true, entity_id: m.entity_id, name: 'Garden', trigger, conditions: 1, drives: ['input_boolean.valve'], before: 'b1' };
  if (!m.fire) return plan;
  return m.before === plan.before ? { ...plan, fired: true }
    : { ok: false, stale: true, reason: 'The automation changed in Home Assistant since you were asked, so it was not run. Try again.' };
}

export function makeOnline() {
  const sent = [], services = [], api = [];
  const state = { moment: CAPTURE.moments[0], extra: {}, keys: {}, listAllFails: false, fire: firePlan };
  const hass = {
    states: {}, entities: {}, devices: {}, areas: {}, themes: { darkMode: false }, language: 'en', user: { is_admin: true },
    localize: (k) => k,
    callService: async (domain, service, data) => { services.push([domain, service, JSON.parse(JSON.stringify(data || {}))]); },
    callApi: async (method, path, body) => { api.push([method, path, body]); return {}; },
    connection: {
      sendMessagePromise: async (m) => {
        sent.push(JSON.parse(JSON.stringify(m)));
        if (m.type === 'libi/ai_status') return { configured: false };
        if (m.type === 'libi/project_list') return { projects: [] };
        if (m.type === 'libi/project_open') return { slug: m.slug, name: 'Q', nets: [], stats: {}, versions: {}, revision: 1, keys: {} };
        if (m.type === 'libi/online_fire') return state.fire(m);
        if (m.type === 'trace/list') {
          if (m.item_id === undefined) {
            if (state.listAllFails) throw Object.assign(new Error('some but not all values in the same group of inclusion'), { code: 'invalid_format' });
            return Object.values(state.moment.runs).map(run => JSON.parse(JSON.stringify(run.list)));
          }
          const run = state.moment.runs[m.item_id];
          return run ? [JSON.parse(JSON.stringify(run.list))] : [];
        }
        if (m.type === 'trace/get') {
          const run = state.moment.runs[m.item_id];
          if (!run || run.list.run_id !== m.run_id) throw new Error('not found');
          return JSON.parse(JSON.stringify(run.get));
        }
        return [];
      },
      subscribeEvents: async () => () => {}, subscribeMessage: async () => () => {},
    },
  };
  return { hass, sent, services, api, state };
}

/** The panel, the captured NETs on its canvas, Online on, at moment `index` of the capture. */
export async function makeOnlinePanel(env, { nets = null, height = '860px' } = {}) {
  localStorage.clear();
  const panel = document.createElement('libi-panel');
  panel.style.height = height;
  document.body.appendChild(panel);
  panel.hass = env.hass;
  await sleep(300);
  const core = panel.core;
  core.nets = JSON.parse(JSON.stringify(nets || CAPTURE.nets));
  core.syncCounters(); core.repairAST(); core.validateAST();
  panel._project = { slug: 'p', name: 'P' };
  panel._markSaved();
  if (panel.aiChat && panel.aiChat.setOpen) panel.aiChat.setOpen(false);
  panel.online.enabled = true;
  panel._render();
  return panel;
}

/** The moment `index` of the capture: its states (and any added), its time, its traces, painted. */
export async function at(env, panel, index, extra = {}) {
  env.state.moment = CAPTURE.moments[index];
  env.hass.states = { ...JSON.parse(JSON.stringify(env.state.moment.states)), ...JSON.parse(JSON.stringify(extra)) };
  panel.online.now = () => Date.parse(env.state.moment.now);
  await panel._pollTraces();
  panel._paintOnline();
  await sleep(20);
}

/** A block on the canvas, by NET and block id. */
export const block = (panel, nid, eid) => panel.shadowRoot.querySelector(`.libi-el[data-nid="${nid}"][data-eid="${eid}"]`);
/** The kind of the run's line under a block (run-fired, run-skip ...), '' when it has none. */
export const markOf = (panel, nid, eid) => { const m = block(panel, nid, eid); const t = m && m.querySelector('.live-run'); return t ? [...t.classList].find(c => c.startsWith('run-')) : ''; };
export const runLine = (panel, nid, eid) => { const m = block(panel, nid, eid); const t = m && m.querySelector('.live-run'); return t ? t.textContent : ''; };
export const badges = (panel, nid, eid) => { const m = block(panel, nid, eid); return m ? [...m.querySelectorAll('.live-val span')].map(s => s.textContent) : []; };
export const monitor = (panel, nid) => panel.shadowRoot.querySelector(`.net-monitor[data-nid="${nid}"]`);
export const chips = (panel, nid) => { const m = monitor(panel, nid); return m ? [...m.querySelectorAll('.mon-chip')].map(c => c.textContent) : []; };
/** A click on a block, as the user clicks it: in Online it opens the block's menu. */
export const openMenu = async (panel, nid, eid) => { block(panel, nid, eid).click(); await sleep(20); return panel.shadowRoot.querySelector('.online-menu'); };
export const menuText = (panel) => { const m = panel.shadowRoot.querySelector('.online-menu'); return m ? m.textContent.replace(/\s+/g, ' ').trim() : ''; };
export const menuButtons = (panel) => [...panel.shadowRoot.querySelectorAll('.online-menu .onl-btn')].map(b => b.getAttribute('data-onl'));
export const closeMenu = async (panel) => { const o = panel.shadowRoot.getElementById('fmOverlay'); if (o) o.click(); await sleep(20); };

/** RULE 36: the Online bar, a NET's monitor and a block's menu at the width of this page's window, in both directions:
 *  nothing past the screen, the buttons big enough to touch, a long name cut in its own chip, the run's lines under the
 *  Trigger label, not on it. */
export async function onlineLayoutChecks(check, panel, phone) {
  const sr = panel.shadowRoot;
  const inside = (el, box) => { const r = el.getBoundingClientRect(), b = box.getBoundingClientRect(); return r.left >= b.left - 0.5 && r.right <= b.right + 0.5; };
  for (const dir of ['ltr', 'rtl']) {
    document.documentElement.setAttribute('dir', dir);
    panel._render(); panel._paintOnline();
    await sleep(40);
    const vw = window.innerWidth;
    const bar = sr.querySelector('.online-bar');
    check(`${dir}: the Online bar is on the screen, nothing past it`, !!bar && bar.getBoundingClientRect().right <= vw + 0.5
          && bar.getBoundingClientRect().left >= -0.5 && document.documentElement.scrollWidth <= vw,
          bar && JSON.stringify([bar.getBoundingClientRect().left, bar.getBoundingClientRect().right, vw, document.documentElement.scrollWidth]));
    const buttons = [...bar.querySelectorAll('button')].filter(b => b.offsetParent);
    check(`${dir}: its buttons are big enough to touch and inside it`, buttons.length >= 2 && buttons.every(b => b.getBoundingClientRect().height >= 34 && inside(b, bar)),
          buttons.map(b => `${b.textContent}:${Math.round(b.getBoundingClientRect().height)}`).join());
    const mon = sr.querySelector('.net-monitor[data-nid="n1"]');
    const all = [...mon.querySelectorAll('.mon-chip, .mon-btn')];
    check(`${dir}: a NET's monitor keeps its chips and buttons inside it`, all.length > 3 && all.every(c => inside(c, mon)) && inside(mon, sr.querySelector('.canvas')),
          all.filter(c => !inside(c, mon)).map(c => c.textContent).join(' | '));
    const long = [...mon.querySelectorAll('.mon-var')].find(c => c.textContent.includes('the garden and the parking lot'));
    check(`${dir}: a long variable name is cut in its own chip`, !!long && long.scrollWidth > long.clientWidth + 1 && inside(long, mon),
          long ? `${long.scrollWidth} / ${long.clientWidth}` : 'no long chip');
    const lines = [...sr.querySelectorAll('.libi-el[data-nid="n1"] .live-run')];
    check(`${dir}: what the last run did is a line under each block`, lines.length >= 4 && lines.every(l => l.textContent.startsWith('RUN ')), lines.length);
    const trig = block(panel, 'n1', 'e3');
    const tag = trig.querySelector('.trigger-bottom-lbl');
    const val = trig.querySelector('.live-val');
    check(`${dir}: the lines of a trigger start below its Trigger label, not on it`, !!tag && !!val
          && val.getBoundingClientRect().top >= tag.getBoundingClientRect().bottom - 0.5,
          tag && val && JSON.stringify([tag.getBoundingClientRect().bottom, val.getBoundingClientRect().top]));
    // Rung 1's lines end above rung 2 (its block and the name over it), and every line is inside the NET's drawing.
    const bottoms = (rid) => [...sr.querySelectorAll(`.libi-el[data-nid="n1"][data-rid="${rid}"] .live-val`)].map(v => v.getBoundingClientRect().bottom);
    const next = block(panel, 'n1', 'e8');
    const nextTop = Math.min(...[next, ...next.querySelectorAll('*')].map(x => x.getBoundingClientRect()).filter(r => r.width > 0 && r.height > 0).map(r => r.top));
    const wire = next.closest('.rung-wire');
    const every = [...bottoms('r1'), ...bottoms('r2')];
    check(`${dir}: there is room for them: rung 1's lines end above rung 2, and none goes past the NET's drawing`,
          bottoms('r1').length >= 4 && Math.max(...bottoms('r1')) <= nextTop + 0.5 && !!wire && Math.max(...every) <= wire.getBoundingClientRect().bottom + 0.5,
          JSON.stringify([Math.max(...bottoms('r1')), nextTop, Math.max(...every), wire && wire.getBoundingClientRect().bottom]));
    // A block's menu, opened by a click on it: on the screen, its buttons big enough to touch.
    trig.scrollIntoView({ block: 'center' });
    await sleep(20);
    const menu = await openMenu(panel, 'n1', 'e3');
    const r = menu && menu.getBoundingClientRect();
    const mb = menu ? [...menu.querySelectorAll('.onl-btn')] : [];
    check(`${dir}: a block's menu is on the screen, its buttons big enough to touch`, !!menu && r.left >= -0.5 && r.right <= vw + 0.5
          && r.top >= -0.5 && r.bottom <= window.innerHeight + 0.5 && mb.length >= 2 && mb.every(b => b.getBoundingClientRect().height >= 38 && inside(b, menu)),
          menu && JSON.stringify([r.left, r.right, r.top, r.bottom, vw, window.innerHeight, mb.map(b => Math.round(b.getBoundingClientRect().height))]));
    await closeMenu(panel);
  }
  document.documentElement.setAttribute('dir', 'ltr');
}

/** [ADDED v1.2.0] The user's train reminder (2026-11-09) as their screenshot had it, a NET of one rung: a time trigger,
 *  the days, a message - IN2 under the trigger was cut off by the end of the drawing. */
export const ONE_NET = { id: 'n_one', name: 'Train reminder', level: 'automation', collapsed: false, links: [], rungs: [
  { id: 'r1', comment: 'When the time is the train reminder, if the day is ticked', elements: [
    { id: 'e1', type: 'cmp_eq', isTrigger: true, sourceA: 'time', sourceB: 'input_datetime.sh_t_tzkvrt_lrkbt' },
    { id: 'e2', type: 'cmp_eq', isTrigger: false, sourceA: 'weekday', sourceB: 'input_number.days' },
    { id: 'e3', type: 'move', isTrigger: false, mode: 'value', source: 'Train', target: 'input_text.message' }] },
] };

/** [ADDED v1.2.0] More of what a NET holds: that rung, a rung of two branches, a rung that starts with a trigger, and a
 *  last rung of two triggers, either one (OR). Rung 2 hangs from the train reminder, as an imported NET does. */
export const ROOM_NET = { id: 'n_r', name: 'Train', level: 'automation', collapsed: false, links: [], rungs: [
  { id: 'r1', comment: 'When the time is the train reminder, if the day is ticked', elements: [
    { id: 'e1', type: 'cmp_eq', isTrigger: true, sourceA: 'time', sourceB: 'input_datetime.sh_t_tzkvrt_lrkbt' },
    { id: 'e2', type: 'cmp_eq', isTrigger: false, sourceA: 'weekday', sourceB: 'input_number.days' },
    { id: 'e3', type: 'move', isTrigger: false, mode: 'value', source: 'Train', target: 'input_text.message' }] },
  { id: 'r2', comment: '', sharesHead: true, elements: [
    { id: 'p1', type: 'parallel', closed: true, branches: [
      [{ id: 'e4', type: 'cmp_gt', isTrigger: false, sourceA: 'sensor.temperature', sourceB: '20' }],
      [{ id: 'e5', type: 'contact_no', isTrigger: false, label: 'binary_sensor.door' }]] },
    { id: 'e6', type: 'coil_s', isTrigger: false, label: 'light.lamp' }] },
  { id: 'r3', comment: '', elements: [
    { id: 'e7', type: 'cmp_eq', isTrigger: true, sourceA: 'time', sourceB: 'input_datetime.other_reminder' },
    { id: 'e8', type: 'cmp_ne', isTrigger: false, sourceA: 'weather.home', sourceB: 'rainy, pouring, hail' },
    { id: 'e9', type: 'coil_s', isTrigger: false, label: 'switch.valve' }] },
  { id: 'r4', comment: 'Two triggers, either one', elements: [
    { id: 'p2', type: 'parallel', closed: true, branches: [
      [{ id: 'e10', type: 'cmp_eq', isTrigger: true, sourceA: 'time', sourceB: 'input_datetime.other_reminder' }],
      [{ id: 'e11', type: 'contact_no', isTrigger: true, label: 'binary_sensor.door' }]] },
    { id: 'e12', type: 'coil_s', isTrigger: false, label: 'light.lamp' }] },
] };

/** [ADDED v1.2.0] ONE_NET and ROOM_NET in Traces: under each block up to four lines (the run, FORCE, OFFLINE, IN1, IN2),
 *  none cut by the end of its NET's drawing or lying over another block, in both directions; editing keeps its layout. */
export async function roomChecks(check) {
  const env = makeOnline();
  const panel = await makeOnlinePanel(env, { nets: [ONE_NET, ROOM_NET] });
  const sr = panel.shadowRoot;
  const st = (state, attributes = {}) => ({ state, attributes, last_changed: '2026-11-09T03:00:00+00:00' });
  env.hass.states = {
    'input_datetime.sh_t_tzkvrt_lrkbt': st('14:01:00', { has_date: false, has_time: true, friendly_name: 'Train reminder' }),
    'input_datetime.other_reminder': st('unavailable', { has_date: false, has_time: true }),
    'input_number.days': st('31.0'), 'input_text.message': st(''), 'sensor.temperature': st('unavailable'),
    'binary_sensor.door': st('unavailable'), 'light.lamp': st('off'), 'weather.home': st('sunny'), 'switch.valve': st('off') };
  let now = new Date(2026, 10, 9, 5, 49, 36).getTime();
  panel.online.now = () => now;
  panel.online.setMode('simulate');
  panel._render(); panel._paintOnline(); await sleep(20);
  const force = async (nid, eid) => {
    await openMenu(panel, nid, eid);
    const b = sr.querySelector('.online-menu .onl-btn[data-onl="force-true"]');
    if (!b) throw new Error(`no FORCE TRUE on ${nid}/${eid}: ${menuText(panel)}`);
    b.click(); await sleep(20);
  };
  // Each run starts at the train reminder (forced last); three blocks also say OFFLINE: four lines under each.
  for (const eid of ['e4', 'e8', 'e7', 'e10', 'e11', 'e1']) await force('n_r', eid);
  await force('n_one', 'e1');
  for (let i = 0; i < 3; i++) { now += 1000; panel._paintOnline(); await sleep(20); }
  clearInterval(panel._onlineTimer);

  const lines = (nid, eid) => badges(panel, nid, eid);
  check('the train reminder\'s trigger has its four lines, IN2 the time it starts at: 14:01:00',
        ['n_one', 'n_r'].every(nid => lines(nid, 'e1').length >= 4 && lines(nid, 'e1').includes('IN2 14:01:00')
          && lines(nid, 'e1').some(l => l.startsWith('IN1 05:49:'))), JSON.stringify([lines('n_one', 'e1'), lines('n_r', 'e1')]));
  check('a block in a branch, a trigger in a rung below and a trigger in a branch have four lines too',
        ['e4', 'e7', 'e10'].every(id => lines('n_r', id).length >= 4), JSON.stringify(['e4', 'e7', 'e10'].map(id => lines('n_r', id))));

  const meets = (a, b) => a.left < b.right - 0.5 && b.left < a.right - 0.5 && a.top < b.bottom - 0.5 && b.top < a.bottom - 0.5;
  const named = (x) => { const b = x.closest('.libi-el'); return `${b ? `${b.getAttribute('data-nid')}/${b.getAttribute('data-eid')}` : '?'}:${x.textContent}`; };
  for (const dir of ['ltr', 'rtl']) {
    document.documentElement.setAttribute('dir', dir);
    panel._render(); panel._paintOnline(); await sleep(30);
    clearInterval(panel._onlineTimer);
    const cut = [], over = [];
    let count = 0;
    for (const nid of ['n_one', 'n_r']) {
      const box = sr.querySelector(`.rung-scroll[data-nid="${nid}"]`).getBoundingClientRect();
      const spans = [...sr.querySelectorAll(`.libi-el[data-nid="${nid}"] .live-val > span`)];
      count += spans.length;
      for (const s of spans) {
        const r = s.getBoundingClientRect();
        if (r.bottom > box.bottom + 0.5 || r.top < box.top - 0.5) cut.push(`${named(s)} ${Math.round(r.bottom)} > ${Math.round(box.bottom)}`);
      }
      // Another block: its own box and everything drawn for it (the name over it, the Trigger label), not its lines.
      const blocks = [...sr.querySelectorAll(`.libi-el[data-nid="${nid}"]:not(.libi-parallel)`)];
      for (const s of spans) {
        const r = s.getBoundingClientRect();
        const own = s.closest('.libi-el');
        for (const other of blocks) {
          if (other === own) continue;
          const parts = [other, ...other.querySelectorAll('*')].filter(x => !x.closest('.live-val'))
            .map(x => x.getBoundingClientRect()).filter(q => q.width > 0 && q.height > 0);
          if (parts.some(q => meets(r, q))) over.push(`${named(s)} over ${other.getAttribute('data-eid')}`);
        }
      }
    }
    check(`${dir}: no line under a block is cut by the end of its NET's drawing - IN2 under the train reminder neither`,
          count >= 24 && cut.length === 0, JSON.stringify([count, cut]));
    check(`${dir}: no line under a block lies over another block - the rung below, the branch below`, over.length === 0, JSON.stringify(over));
  }
  document.documentElement.setAttribute('dir', 'ltr');

  // Editing keeps its drawing: the room is there in Traces only.
  const tall = sr.querySelector('.rung-scroll[data-nid="n_r"] .rung-wire').getBoundingClientRect().height;
  panel.online.enabled = false;
  panel._render(); await sleep(20);
  const wire = sr.querySelector('.rung-scroll[data-nid="n_r"] .rung-wire');
  const editing = wire ? wire.getBoundingClientRect().height : 0;
  check('editing (Traces off) draws the NET as before, without the room for the lines',
        panel.core.liveRoom === 0 && editing > 0 && editing < tall && editing === panel.core.layoutNet(panel.core.nets[1]).height,
        JSON.stringify([panel.core.liveRoom, editing, tall]));
  return { env, panel };
}
