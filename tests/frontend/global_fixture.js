/*
 * LIBI for Home Assistant - Copyright (C) 2026 Guy Azria - GPL-3.0-or-later
 * What the LIBI Global pages share (test_panel_global*.html): a Home Assistant whose libi/global, libi/global_plan and
 *   libi/global_done answer as the backend does, whose config API records each call, and the panel on it. Not a test page
 *   itself: the runner runs test_*.html only. layoutChecks checks the table of the Global tab and the editor of one
 *   global variable (LIBI 3.88.1). libi/global_move_plan and libi/global_move_done answer as the backend does, and
 *   SAVE & COMPILE saves; moveLayoutChecks checks the question to replace a phone with a global variable (LIBI 3.89.0).
 * [CHANGED v1.3.0 | 2026-11-06] Purpose: SAVE & COMPILE checks each change again first (libi/save_check): yes.
 * [CHANGED v1.4.0 | 2026-11-06] Purpose: The names given in LIBI only are kept as the backend keeps them (state.names,
 *   libi/local_name_set), and libi/global says who uses each (state.nameUsers); layoutChecks checks "Named in LIBI" too.
 */
import '../../custom_components/libi/frontend/libi-panel.js';

export const sleep = (ms) => new Promise(r => setTimeout(r, ms));

export const S23 = 'notify.mobile_app_sm_s918b';
export const S25 = 'notify.mobile_app_sm_s938b';
export const IPHONE = 'notify.mobile_app_guy_iphone';

// What libi/global answers for the phones (ai.phone_list): two of them share one action and cannot be ticked.
export const PHONES = [
  { entity_id: 'notify.guy_iphone', service: IPHONE, name: 'Guy iPhone', owner: 'Guy', device: 'Apple iPhone 15', speaks: false, shared: false },
  { entity_id: 'notify.sm_n985f', service: 'notify.mobile_app_sm_n985f', name: 'SM-N985F', owner: 'Guy', device: 'samsung SM-N985F', speaks: true, shared: true },
  { entity_id: 'notify.sm_n985f_2', service: 'notify.mobile_app_sm_n985f', name: 'SM-N985F', owner: 'Guy', device: 'samsung SM-N985F', speaks: true, shared: true },
  { entity_id: 'notify.sm_s918b', service: S23, name: 'SM-S918B', owner: 'Guy', device: 'samsung SM-S918B', speaks: true, shared: false },
  { entity_id: 'notify.sm_s938b', service: S25, name: 'SM-S938B', owner: 'Yulia', device: 'samsung SM-S938B', speaks: true, shared: false },
];

export const GUY = () => ({
  key: 'libi_send_to_guy', action: 'script.libi_send_to_guy', name: 'Guy', phones: [S23], edited: false, missing: [],
  used_by: [{ domain: 'automation', key: 'train', name: 'Train reminder' }],
  direct: [{ domain: 'automation', key: 'smoke', name: 'Smoke <b>alarm</b>', phones: [S23] }],
});
// Changed in Home Assistant's script editor, and one of its phones is gone. Its name tries to leave an attribute
// and run a script.
export const OLD = () => ({
  key: 'libi_send_to_old', action: 'script.libi_send_to_old', name: '"><img src=x onerror="window.__x=1">',
  phones: ['notify.mobile_app_mi_9t_pro'], edited: true, missing: ['notify.mobile_app_mi_9t_pro'], used_by: [], direct: [],
});

export const NET = () => ({ id: 'n1', name: 'Train', level: 'automation', collapsed: false, links: [], rungs: [{ id: 'r1', comment: '', elements: [
  { id: 'e0', type: 'contact_no', isTrigger: true, label: 'binary_sensor.door' },
  { id: 'e1', type: 'move', mode: 'tts', tts: 'Time to go', stream: 'alarm_stream', target: 'script.libi_send_to_guy' },
  { id: 'e2', type: 'move', mode: 'notify', source: 'Hi', target: 'script.libi_send_to_gone' },
  { id: 'e3', type: 'move', mode: 'notify', source: 'Old', target: 'script.libi_send_to_old' },
  { id: 'e4', type: 'move', mode: 'notify', source: 'Phone', target: S25 }] }] });

/** A Home Assistant for the panel. state.recipients is what Home Assistant's scripts.yaml holds; state.global answers
 *  libi/global (a function, so a test can make it fail); state.plan answers libi/global_plan; api records the calls to
 *  the config API, and state.apiFails makes the next one fail as Home Assistant refuses an entry. */
export function makeHass() {
  const states = {};
  const st = (id, name) => { states[id] = { entity_id: id, state: 'unknown', attributes: { friendly_name: name } }; };
  st('binary_sensor.door', 'Door');
  st('notify.sm_s918b', 'SM-S918B'); st('notify.sm_s938b', 'SM-S938B'); st('notify.guy_iphone', 'Guy iPhone');
  st('script.libi_send_to_guy', 'LIBI Global: Guy');
  const sent = [];
  const api = [];
  const state = { recipients: [GUY(), OLD()], apiFails: null, plan: null, global: null, move: null,
    names: { [S23]: 'S23 guy' }, nameUsers: { [S23]: [{ domain: 'automation', key: 'smoke', name: 'Smoke alarm' }] } };
  const listing = () => ({ ok: true, errors: [], recipients: JSON.parse(JSON.stringify(state.recipients)), phones: PHONES });
  const slug = (name) => 'libi_send_to_' + String(name).toLowerCase().replace(/[^a-z0-9]+/g, '_');
  const hass = {
    states, entities: {}, devices: {}, areas: {}, themes: { darkMode: false }, language: 'en', user: { is_admin: true },
    services: { notify: { mobile_app_sm_s918b: {}, mobile_app_sm_s938b: {}, mobile_app_guy_iphone: {}, mobile_app_sm_n985f: {} } },
    localize: (k) => k, callService: async () => {},
    callApi: async (method, path, body) => {
      api.push({ method, path, body: body ? JSON.parse(JSON.stringify(body)) : undefined });
      if (state.apiFails) { const err = state.apiFails; state.apiFails = null; throw err; }
      return {};
    },
    connection: {
      sendMessagePromise: async (m) => {
        sent.push(JSON.parse(JSON.stringify(m)));
        if (m.type === 'libi/ai_status') return { configured: false };
        if (m.type === 'libi/project_list') return { projects: [] };
        if (m.type === 'libi/phones') return { phones: PHONES };
        if (m.type === 'libi/local_names') return { names: { ...state.names } };
        if (m.type === 'libi/local_name_set') {
          if (m.name) state.names[m.entity_id] = m.name; else delete state.names[m.entity_id];
          return { names: { ...state.names } };
        }
        if (m.type === 'libi/global') return state.global ? state.global() : { ...listing(), name_users: JSON.parse(JSON.stringify(state.nameUsers)) };
        if (m.type === 'libi/global_plan') {
          if (state.plan) return state.plan(m);
          const key = m.key || slug(m.name);
          // As the backend: a delete is labelled with the recipient's name as Home Assistant holds it.
          const held = state.recipients.find(r => r.key === key);
          return { ok: true, unchanged: false, key, stamp: 'STAMP',
                   op: { domain: 'script', key, op: m.remove ? 'remove' : 'upsert', label: m.remove && held ? held.name : (m.name || key),
                         config: m.remove ? undefined : { alias: 'LIBI Global: ' + m.name, phones: m.phones } } };
        }
        if (m.type === 'libi/global_done') {
          if (m.failure) return { ...listing(), status: 'error', saved: false, reloaded: false, errors: ['refused'],
                                  message: 'Not saved: Home Assistant refused it: ' + m.failure.message };
          const last = api[api.length - 1];
          if (m.op === 'remove') state.recipients = state.recipients.filter(r => r.key !== m.key);
          else {
            const body = last.body;
            const was = state.recipients.find(r => r.key === m.key);
            // As the backend: what sends to its phones straight is listed again after the save.
            const now = { key: m.key, action: 'script.' + m.key, name: body.alias.replace('LIBI Global: ', ''), phones: body.phones,
                          edited: false, missing: [], used_by: was ? was.used_by : [], direct: was ? was.direct : [],
                          move_why: was ? (was.move_why || '') : '' };
            state.recipients = was ? state.recipients.map(r => (r.key === m.key ? now : r)) : [...state.recipients, now];
          }
          return { ...listing(), status: 'ok', saved: true, reloaded: true, errors: [],
                   message: m.op === 'remove' ? `Deleted: ${m.label}.` : 'Saved. Every NET that sends to it sends to these phones from now on.' };
        }
        // [ADDED v1.2.0] The phone replaced with a global variable, as the backend does it: each entry ticked that it lists
        // as movable, then each read back - moved, it sends to the global variable and is no longer listed.
        if (m.type === 'libi/global_move_plan') {
          if (state.move) return state.move(m);
          const r = state.recipients.find(x => x.key === m.key);
          const ops = (m.entries || []).map(e => {
            const d = r.direct.find(x => x.domain === e.domain && x.key === e.key);
            return { domain: e.domain, key: e.key, op: 'upsert', label: d.name, config: { id: e.key, moved_to: r.action } };
          });
          return { ok: true, key: m.key, ops, stamp: 'MOVE' };
        }
        if (m.type === 'libi/global_move_done') {
          const r = state.recipients.find(x => x.key === m.key);
          const moved = (m.done || []).map(op => r.direct.find(x => x.domain === op.domain && x.key === op.key)).filter(Boolean);
          r.direct = r.direct.filter(d => !moved.includes(d));
          r.used_by = [...r.used_by, ...moved.map(d => ({ domain: d.domain, key: d.key, name: d.name }))];
          const names = moved.map(d => d.name).join(', ');
          const errors = m.failure ? [`${m.failure.label}: Home Assistant refused it: ${m.failure.message}`] : [];
          const message = moved.length && !errors.length ? `Replaced in ${moved.length}: ${names}. They send through ${r.name} from now on.`
            : moved.length ? `Replaced in ${moved.length}: ${names}. But: ${errors.join('; ')}` : `Nothing was replaced: ${errors.join('; ')}`;
          return { ...listing(), status: errors.length ? 'error' : 'ok', moved: moved.map(d => d.name), reloaded: !!moved.length,
                   message, errors, key: m.key };
        }
        if (m.type === 'libi/compile_project') {
          return { ok: true, errors: [], stamp: 'SAVE', removals: [],
                   upserts: m.nets.map((n, i) => ({ domain: 'automation', key: n.id, label: `NET ${i + 1} "${n.name}"`, config: { id: n.id } })) };
        }
        if (m.type === 'libi/save_check') return { ok: true, token: '' };
        if (m.type === 'libi/save_done') {
          return { status: 'ok', saved: true, message: 'Saved.', slug: m.slug, written: ['automation'], reloaded: ['automation'],
                   versions: {}, errors: [] };
        }
        return [];
      },
      subscribeEvents: async () => () => {}, subscribeMessage: async () => () => {},
    },
  };
  return { hass, sent, api, state };
}

/** The panel on that Home Assistant, the AI chat closed (it opens over the Inspector), one NET on the canvas. */
export async function makePanel(hass, height = '860px') {
  localStorage.clear();
  const panel = document.createElement('libi-panel');
  panel.style.height = height;
  document.body.appendChild(panel);
  panel.hass = hass;
  await sleep(300);
  const core = panel.core;
  core.nets = [NET()];
  core.syncCounters(); core.repairAST(); core.validateAST();
  panel._project = { slug: 'p', name: 'P' };
  panel._markSaved();
  panel.aiChat.setOpen(false);
  panel._render();
  await sleep(30);
  return panel;
}

/** RULE 36: the Global tab at the width of this page's window, in both directions - the table, and the editor of one
 *  global variable: nothing past the screen, a long name cut in its own box, targets to touch, the tab reachable in the
 *  bar. phone: the ID column is hidden there, as in the Variables table. */
export async function layoutChecks(check, panel, phone) {
  const sr = panel.shadowRoot;
  const long = 'Everyone in the house, the garden and the parking lot too';
  panel.core.recipients = [...panel.core.recipients, { key: 'libi_send_to_everyone', action: 'script.libi_send_to_everyone',
    name: long, phones: [S23, S25, IPHONE], edited: false, missing: [], used_by: [], direct: [] }];
  const inside = (el, box) => { const r = el.getBoundingClientRect(), b = box.getBoundingClientRect(); return r.left >= b.left - 0.5 && r.right <= b.right + 0.5; };
  for (const dir of ['ltr', 'rtl']) {
    document.documentElement.setAttribute('dir', dir);
    const vw = window.innerWidth;
    // The table
    Object.assign(panel._global, { editing: '', drafts: {}, said: {} });
    panel._varsTab = 'global'; panel._varsOpen = true;
    // [ADDED v1.4.0] And a long name given in LIBI only, under Named in LIBI.
    panel.core.localNames = { [S23]: 'S23 guy', 'light.hall': `${long} - the hall light` };
    panel._render();
    await sleep(40);
    const scroll = sr.querySelector('.glob-scroll');
    const tagRows = [...sr.querySelectorAll('.glob-tag-row')];
    check(`${dir} named in LIBI: a row for each name, under the global variables`, tagRows.length === 2
          && sr.querySelector('.glob-tags').getBoundingClientRect().top >= sr.querySelector('.glob-table:not(.glob-tags)').getBoundingClientRect().bottom - 0.5,
          tagRows.length);
    const tagName = sr.querySelector('.glob-tag-row[data-eid="light.hall"] .c-name');
    check(`${dir} named in LIBI: a long name is cut in its cell, and every row fits`, tagName.scrollWidth > tagName.clientWidth
          && tagRows.every(r => inside(r, scroll)) && scroll.scrollWidth <= scroll.clientWidth + 1, `${tagName.scrollWidth} / ${tagName.clientWidth}`);
    const tagDels = [...sr.querySelectorAll('.glob-tag-del')];
    check(`${dir} named in LIBI: 🗑 is big enough to touch and on the screen`, tagDels.length === 2
          && tagDels.every(b => b.getBoundingClientRect().height >= 36 && inside(b, scroll)), tagDels.map(b => b.getBoundingClientRect().height).join());
    const tagId = sr.querySelector('.glob-tags th.c-eid');
    check(`${dir} named in LIBI: the ID column ${phone ? 'is hidden on a phone' : 'is shown'}`, (getComputedStyle(tagId).display === 'none') === phone,
          getComputedStyle(tagId).display);
    check(`${dir} table: a row for each global variable`, sr.querySelectorAll('.glob-row').length === 3, sr.querySelectorAll('.glob-row').length);
    check(`${dir} table: no horizontal page scroll`, document.documentElement.scrollWidth <= vw, document.documentElement.scrollWidth + ' > ' + vw);
    check(`${dir} table: it fits the screen`, scroll.getBoundingClientRect().right <= vw + 0.5 && scroll.getBoundingClientRect().left >= -0.5
          && scroll.scrollWidth <= scroll.clientWidth + 1, `${scroll.scrollWidth} > ${scroll.clientWidth}`);
    const idHead = sr.querySelector('.glob-table th.c-eid');
    check(`${dir} table: the ID column ${phone ? 'is hidden on a phone, as in Variables' : 'is shown'}`,
          (getComputedStyle(idHead).display === 'none') === phone, getComputedStyle(idHead).display);
    const nameCell = sr.querySelector('.glob-row[data-key="libi_send_to_everyone"] .c-name');
    check(`${dir} table: a long name is cut in its cell`, nameCell.scrollWidth > nameCell.clientWidth && inside(nameCell, scroll),
          `${nameCell.scrollWidth} / ${nameCell.clientWidth}`);
    const dels = [...sr.querySelectorAll('.glob-row-del')];
    check(`${dir} table: 🗑 is big enough to touch and on the screen`, dels.every(b => b.getBoundingClientRect().height >= 36 && inside(b, scroll)),
          dels.map(b => b.getBoundingClientRect().height).join());
    const tab = sr.getElementById('varsTabGlobal');
    const strip = tab.parentElement.getBoundingClientRect();
    tab.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    await sleep(10);
    const t = tab.getBoundingClientRect();
    check(`${dir}: the Global tab can be reached in the bar`, t.width > 0 && t.left >= strip.left - 0.5 && t.right <= strip.right + 0.5 && t.right <= vw + 0.5,
          JSON.stringify({ t: [t.left, t.right], strip: [strip.left, strip.right] }));
    // The editor of the one with the long name
    sr.querySelector('.glob-row[data-key="libi_send_to_everyone"]').click();
    await sleep(40);
    const card = sr.querySelector('.glob-card');
    check(`${dir} editor: it opens alone`, !!card && !sr.querySelector('.glob-table'));
    check(`${dir} editor: no horizontal page scroll`, document.documentElement.scrollWidth <= vw, document.documentElement.scrollWidth + ' > ' + vw);
    const r = card.getBoundingClientRect();
    check(`${dir} editor: it fits the screen, nothing sticks out of it`, r.left >= -0.5 && r.right <= vw + 0.5 && card.scrollWidth <= card.clientWidth + 1,
          JSON.stringify([r.left, r.right, card.scrollWidth, card.clientWidth]));
    const chips = [...card.querySelectorAll('.glob-phone')];
    const bad = chips.filter(ch => ch.getBoundingClientRect().height < 36 || !inside(ch, card));
    check(`${dir} editor: each phone is a chip to touch, inside the editor`, chips.length > 0 && bad.length === 0, bad.map(b => b.textContent.trim()).join(' | '));
    const buttons = [...card.querySelectorAll('.glob-foot .btn')];
    check(`${dir} editor: Save, Cancel and Delete are big enough to touch`, buttons.length === 3 && buttons.every(b => b.getBoundingClientRect().height >= 36 && inside(b, card)),
          buttons.map(b => b.getBoundingClientRect().height).join());
    const box = card.querySelector('.glob-name');
    check(`${dir} editor: a long name stays in its box`, box.value === long && inside(box, card));
  }
  document.documentElement.removeAttribute('dir');
  Object.assign(panel._global, { editing: '' });
}

/** [ADDED v1.2.0] RULE 36: the question to replace a phone with a global variable at the width of this page's window, in
 *  both directions - in the screen, its list scrolling inside it, each row and button big enough to touch, a long name
 *  cut in its row - and the line over the table that offers it. */
export async function moveLayoutChecks(check, panel) {
  const sr = panel.shadowRoot;
  const long = 'The smoke alarm of the second floor, the kitchen and the parking lot, and then some more';
  const direct = Array.from({ length: 14 }, (_, i) => ({ domain: 'automation', key: 'a' + i, name: i ? `Automation ${i}` : long,
    phones: [S23], moves: 1, stays: i % 3 ? 0 : 1, why: '', owner: null }));
  direct.push({ domain: 'automation', key: 'drawn', name: long, phones: [S23], moves: 1, stays: 0,
    owner: { slug: 'g', name: 'Garden', drawn: true }, why: 'a NET of LIBI project "Garden" draws it: open that project, and replace it there' });
  const before = panel.core.recipients;
  panel.core.recipients = [{ key: 'libi_send_to_gm', action: 'script.libi_send_to_gm', name: 'Guy My Phone', phones: [S23],
    edited: false, missing: [], used_by: [], direct, move_why: '' }];
  const inside = (el, box) => { const r = el.getBoundingClientRect(), b = box.getBoundingClientRect(); return r.left >= b.left - 0.5 && r.right <= b.right + 0.5; };
  for (const dir of ['ltr', 'rtl']) {
    document.documentElement.setAttribute('dir', dir);
    const vw = window.innerWidth, vh = window.innerHeight;
    Object.assign(panel._global, { editing: '', drafts: {}, said: {} });
    panel._varsTab = 'global'; panel._varsOpen = true; panel._modal = null;
    panel._render();
    await sleep(30);
    const line = sr.querySelector('.glob-moves');
    const open = line && line.querySelector('.glob-move-open');
    check(`${dir}: the line that offers Replace fits the screen, its button big enough to touch`, !!open
          && line.getBoundingClientRect().right <= vw + 0.5 && line.getBoundingClientRect().left >= -0.5
          && open.getBoundingClientRect().height >= 36 && inside(open, line), line ? line.textContent.trim() : 'no line');
    open.click();
    await sleep(30);
    const modal = sr.querySelector('.gm-modal');
    const m = modal.getBoundingClientRect();
    check(`${dir}: the question is in the screen`, m.left >= -0.5 && m.right <= vw + 0.5 && m.top >= -0.5 && m.bottom <= vh + 0.5
          && document.documentElement.scrollWidth <= vw, JSON.stringify([m.left, m.right, m.top, m.bottom, vw, vh]));
    const list = modal.querySelector('.gm-list');
    check(`${dir}: its list scrolls inside it`, list.scrollHeight > list.clientHeight && list.scrollWidth <= list.clientWidth + 1,
          `${list.scrollHeight}/${list.clientHeight} ${list.scrollWidth}/${list.clientWidth}`);
    const rows = [...modal.querySelectorAll('.gm-item')];
    const bad = rows.filter(r => r.getBoundingClientRect().height < 36 || !inside(r, list));
    check(`${dir}: each row is big enough to touch, inside the list`, rows.length === 15 && bad.length === 0,
          rows.length + ' ' + bad.map(b => b.textContent.trim().slice(0, 40)).join(' | '));
    const nm = modal.querySelector('.gm-item .nm');
    check(`${dir}: a long name is cut in its row`, nm.scrollWidth > nm.clientWidth && inside(nm, list), `${nm.scrollWidth}/${nm.clientWidth}`);
    const why = modal.querySelector('.gm-item.off .why');
    check(`${dir}: why one is not replaced wraps inside its row`, inside(why, list) && why.scrollWidth <= why.clientWidth + 1,
          `${why.scrollWidth}/${why.clientWidth}`);
    const buttons = [...modal.querySelectorAll('.modal-actions .btn')];
    check(`${dir}: Not now and Replace are big enough to touch, inside the question`, buttons.length === 2
          && buttons.every(b => b.getBoundingClientRect().height >= 36 && inside(b, modal)), buttons.map(b => b.getBoundingClientRect().height).join());
    sr.getElementById('gmCancel').click();
    await sleep(20);
    check(`${dir}: Not now closes it`, !sr.querySelector('.gm-modal') && panel._modal === null);
  }
  document.documentElement.removeAttribute('dir');
  panel.core.recipients = before;
}
