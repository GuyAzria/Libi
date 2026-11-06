/*
 * LIBI for Home Assistant - Copyright (C) 2026 Guy Azria - GPL-3.0-or-later
 * [ADDED v1.0.0 | 2026-11-06] Purpose: What the Online pages share (test_panel_online*.html): a Home Assistant whose
 *   states, time and traces are those of a moment of trace_fixture.js - real runs of a real Home Assistant - whose
 *   trace/list and trace/get answer as Home Assistant's do, and which records every service call and config API call;
 *   and the panel on it, with the captured NETs, Online on. Not a test page itself: the runner runs test_*.html only.
 *   trace/list without an item answers every automation's runs (state.listAllFails: as a Home Assistant that wants the
 *   item); the config API's GET answers the automation's config as the capture has it, or state.configs[path] (an Error
 *   is thrown, as Home Assistant answers one it does not have).
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

export function makeOnline() {
  const sent = [], services = [], api = [];
  const configs = {};
  for (const m of CAPTURE.moments) for (const [item, run] of Object.entries(m.runs)) configs[`config/automation/config/${item}`] = run.get.config;
  const state = { moment: CAPTURE.moments[0], extra: {}, keys: {}, listAllFails: false, configs };
  const hass = {
    states: {}, entities: {}, devices: {}, areas: {}, themes: { darkMode: false }, language: 'en', user: { is_admin: true },
    localize: (k) => k,
    callService: async (domain, service, data) => { services.push([domain, service, JSON.parse(JSON.stringify(data || {}))]); },
    callApi: async (method, path, body) => {
      api.push([method, path, body]);
      if (method !== 'GET') return {};
      const found = state.configs[path];
      if (!found || found instanceof Error) throw (found || new Error('Resource not found'));
      return JSON.parse(JSON.stringify(found));
    },
    connection: {
      sendMessagePromise: async (m) => {
        sent.push(JSON.parse(JSON.stringify(m)));
        if (m.type === 'libi/ai_status') return { configured: false };
        if (m.type === 'libi/project_list') return { projects: [] };
        if (m.type === 'libi/project_open') return { slug: m.slug, name: 'Q', nets: [], stats: {}, versions: {}, revision: 1, keys: {} };
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
export const markOf = (panel, nid, eid) => { const m = block(panel, nid, eid); const t = m && m.querySelector('.run-mark'); return t ? [...t.classList].find(c => c.startsWith('run-') && c !== 'run-mark') : ''; };
export const badges = (panel, nid, eid) => { const m = block(panel, nid, eid); return m ? [...m.querySelectorAll('.live-val span')].map(s => s.textContent) : []; };
export const monitor = (panel, nid) => panel.shadowRoot.querySelector(`.net-monitor[data-nid="${nid}"]`);
export const chips = (panel, nid) => { const m = monitor(panel, nid); return m ? [...m.querySelectorAll('.mon-chip')].map(c => c.textContent) : []; };

/** RULE 36: the Online bar and a NET's monitor at the width of this page's window, in both directions: nothing past the
 *  screen, the buttons big enough to touch, a long name cut in its own chip. */
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
    const marks = [...sr.querySelectorAll('.libi-el[data-nid="n1"] .run-mark')];
    check(`${dir}: the marks of the last run are drawn on their blocks`, marks.length >= 4, marks.length);
  }
  document.documentElement.setAttribute('dir', 'ltr');
}
