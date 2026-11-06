/*
 * LIBI for Home Assistant - Copyright (C) 2026 Guy Azria - GPL-3.0-or-later
 * [ADDED v1.0.0 | 2026-11-05] Purpose: What the pages of the question before a save deletes share
 *   (test_panel_save_removals*.html) - the HACS review of 2026-11-05: SAVE & COMPILE lists what it would delete from Home
 *   Assistant and asks first. A Home Assistant whose libi/compile_project and libi/save_done answer as the backend does,
 *   whose config API records each call, and the panel on it. Not a test page itself: the runner runs test_*.html only.
 * [CHANGED v1.1.0 | 2026-11-06] Purpose: libi/save_check answers as the backend does when nothing changed since the plan
 *   (state.check): yes, and a create with its token.
 */
import '../../custom_components/libi/frontend/libi-panel.js';

export const sleep = (ms) => new Promise(r => setTimeout(r, ms));
export const until = async (cond, ms = 3000) => { const end = Date.now() + ms; while (!cond() && Date.now() < end) await sleep(10); return cond(); };

// Two entries LIBI made for the project and the canvas no longer has. The name of the second comes from the user's YAML
// and tries to be HTML.
export const REMOVALS = () => [
  { domain: 'scene', key: 'old', label: 'scene "Old evening" (old)' },
  { domain: 'automation', key: 'n7', label: 'automation "<b>Hall</b> light" (n7)' }];

export const LAMP = () => ({ id: 'n1', ha_id: 'a1', name: 'Lamp', level: 'automation', collapsed: false, links: [], rungs: [{ id: 'r1', comment: '', elements: [
  { id: 'e1', type: 'contact_no', isTrigger: true, label: 'binary_sensor.door' },
  { id: 'e2', type: 'coil_s', label: 'light.x' }] }] });

/** A Home Assistant for the panel: state.plan answers libi/compile_project, state.saved libi/save_done; sent and api
 *  record the websocket messages and the calls to the config API. */
export function makeSaveHass() {
  const sent = [], api = [];
  const state = { plan: null, saved: null };
  state.reset = (removals = REMOVALS()) => {
    sent.length = 0; api.length = 0;
    state.plan = { ok: true, errors: [], unchanged: 0, stamp: '2026-11-05T05:00:00+00:00', released: [],
      upserts: [{ domain: 'automation', key: 'a1', config: { id: 'a1', alias: 'Lamp' }, label: 'NET 1 "Lamp"', new: false },
                { domain: 'script', key: 'good_night_2', config: { alias: 'Good night', sequence: [] }, label: 'NET 2 "Good night"', new: true }],
      removals };
    state.saved = { status: 'ok', saved: true, message: 'Saved.', written: ['automation', 'script'], reloaded: ['automation', 'script'],
      errors: [], versions: {}, released: [] };
    state.check = (m) => ({ ok: true, token: m.new ? `tk-${m.key}` : '' });
  };
  state.reset();
  const hass = {
    states: {}, entities: {}, devices: {}, areas: {}, themes: { darkMode: false }, language: 'en',
    user: { is_admin: true }, localize: (k) => k, callService: async () => {},
    callApi: async (method, path, body) => { api.push([method, path, body === undefined ? null : JSON.parse(JSON.stringify(body))]); return { result: 'ok' }; },
    connection: {
      sendMessagePromise: async (m) => {
        sent.push(JSON.parse(JSON.stringify(m)));
        if (m.type === 'libi/ai_status') return { configured: false };
        if (m.type === 'libi/project_list') return { projects: [] };
        if (m.type === 'libi/compile_project') return JSON.parse(JSON.stringify(state.plan));
        if (m.type === 'libi/save_check') return state.check(m);
        if (m.type === 'libi/save_done') return JSON.parse(JSON.stringify(state.saved));
        if (m.type === 'libi/project_open') return { slug: m.slug, name: 'Q', nets: [], stats: {}, versions: {} };
        return [];
      },
      subscribeEvents: async () => () => {}, subscribeMessage: async () => () => {},
    },
  };
  return { hass, sent, api, state };
}

export async function makeSavePanel(hass, height = '800px') {
  localStorage.clear();
  const panel = document.createElement('libi-panel');
  panel.style.height = height;
  document.body.appendChild(panel);
  panel.hass = hass;
  await sleep(300);
  return panel;
}

/** The project open with one NET changed and not saved. */
export function changedCanvas(panel) {
  const core = panel.core;
  core.nets = [LAMP()];
  core.syncCounters(); core.repairAST(); core.validateAST();
  panel._project = { slug: 'p', name: 'P' };
  panel._markSaved();
  core.nets[0].rungs[0].elements[1].label = 'light.y';
  core.pushHistory();
  panel._render();
}

/** The question on the screen, LTR and RTL: in the screen, its list scrolling inside it, a long name cut in its line, the
 *  answers big enough to touch and in view. */
export async function removalLayoutChecks(check, panel, state) {
  const sr = panel.shadowRoot;
  const long = 'The smoke alarm of the second floor, the kitchen and the parking lot, and then some more of it';
  state.reset(Array.from({ length: 25 }, (_, i) => ({ domain: 'automation', key: 'n' + (i + 10),
    label: `automation "${i ? 'Automation ' + i : long}" (n${i + 10})` })));
  const inside = (el, box) => { const r = el.getBoundingClientRect(), b = box.getBoundingClientRect(); return r.left >= b.left - 0.5 && r.right <= b.right + 0.5; };
  for (const dir of ['ltr', 'rtl']) {
    document.documentElement.setAttribute('dir', dir);
    const vw = window.innerWidth, vh = window.innerHeight;
    changedCanvas(panel);
    const saving = panel._saveProject();
    await until(() => sr.querySelector('.ask-modal .ask-list'));
    const modal = sr.querySelector('.ask-modal');
    const m = modal.getBoundingClientRect();
    check(`${dir}: the question is in the screen`, m.left >= -0.5 && m.right <= vw + 0.5 && m.top >= -0.5 && m.bottom <= vh + 0.5
          && document.documentElement.scrollWidth <= vw, JSON.stringify([m.left, m.right, m.top, m.bottom, vw, vh]));
    const list = modal.querySelector('.ask-list');
    check(`${dir}: its list of 25 scrolls inside it`, list.querySelectorAll('li').length === 25 && list.scrollHeight > list.clientHeight
          && list.scrollWidth <= list.clientWidth + 1 && inside(list, modal), `${list.scrollHeight}/${list.clientHeight} ${list.scrollWidth}/${list.clientWidth}`);
    const first = list.querySelector('li');
    check(`${dir}: a long name is cut in its line, and the whole name is its title`, first.scrollWidth > first.clientWidth && inside(first, list)
          && first.title === `automation "${long}" (n10)`, `${first.scrollWidth}/${first.clientWidth}`);
    const buttons = [...modal.querySelectorAll('.ask-answer')];
    check(`${dir}: the three answers are big enough to touch, inside the question and in view`, buttons.length === 3
          && buttons.every(b => { const r = b.getBoundingClientRect(); return r.height >= 40 && inside(b, modal) && r.bottom <= vh + 0.5 && r.top >= -0.5; }),
          buttons.map(b => JSON.stringify(b.getBoundingClientRect())).join());
    sr.querySelector('.ask-answer[data-answer="cancel"]').click();
    const r = await saving;
    check(`${dir}: Cancel closes it`, r.cancelled === true && !sr.querySelector('.ask-modal'));
  }
  document.documentElement.removeAttribute('dir');
  state.reset();
}
