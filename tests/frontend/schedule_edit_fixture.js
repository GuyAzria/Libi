// LIBI for Home Assistant - Copyright (C) 2026 Guy Azria - GPL-3.0-or-later
// Shared by test_panel_schedule_edit*.html.
// [ADDED v1.0.0 | 2026-11-11] Purpose: the user (2026-11-11) - "in the INSPECTOR, when I click the CMP, let me choose the
//   days and the time, and update the schedule - and if LIBI is deleted everything keeps working". The Inspector of a
//   CMP DATETIME on a schedule sets its days and hours and saves them in Home Assistant's own schedule (schedule/update),
//   which REPLACES the whole schedule: the name, the icon and all seven days are sent. Nothing is written when nothing
//   changed, when the user does not confirm, or when the schedule changed in Home Assistant since it was read. Run
//   against the real panel, with canned answers that act as Home Assistant does.

const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const until = async (cond, ms = 3000) => { const end = Date.now() + ms; while (!cond() && Date.now() < end) await sleep(10); return cond(); };
const SPAN = { from: '13:55:00', to: '14:00:00' };
const DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'];
const week = (marked, span = SPAN) => Object.fromEntries(DAYS.map(d => [d, marked.includes(d) ? [{ ...span }] : []]));

// The user's schedule as Home Assistant keeps it, and the others of the checks.
const ITEMS = () => ({
  train_home_reminder: { id: 'train_home_reminder', name: 'Train Home Reminder', icon: 'mdi:train',
                         ...week(['monday', 'tuesday', 'wednesday', 'thursday', 'sunday']) },
  mixed: { id: 'mixed', name: 'Mixed', ...week([]), monday: [{ from: '06:00:00', to: '06:30:00' }],
           tuesday: [{ from: '06:00:00', to: '06:30:00' }, { from: '18:00:00', to: '19:00:00' }] },
  with_data: { id: 'with_data', name: 'With data', ...week(['monday']), friday: [{ from: '08:00:00', to: '09:00:00', data: { mode: 'eco' } }] },
  // Its entity was renamed: its entity id is schedule.renamed, its helper id other_id.
  other_id: { id: 'other_id', name: 'Renamed', ...week(['saturday']) },
});
const REGISTRY = {
  'schedule.train_home_reminder': 'train_home_reminder', 'schedule.mixed': 'mixed', 'schedule.with_data': 'with_data',
  'schedule.renamed': 'other_id', 'schedule.in_yaml': 'in_yaml',
};

function makeHass(state) {
  const sent = [];
  const states = Object.fromEntries(Object.keys(REGISTRY).map(eid => [eid, { entity_id: eid, state: 'off', attributes: { friendly_name: eid } }]));
  const hass = {
    states, entities: {}, devices: {}, areas: {}, themes: { darkMode: false }, language: 'en',
    user: { is_admin: true }, localize: (k) => k, callService: async () => {},
    connection: {
      sendMessagePromise: async (m) => {
        sent.push(JSON.parse(JSON.stringify(m)));
        if (m.type === 'libi/ai_status') return { configured: false };
        if (m.type === 'libi/project_list') return { projects: [] };
        if (m.type === 'config/entity_registry/get') {
          if (!REGISTRY[m.entity_id]) throw { code: 'not_found', message: 'Entity not found' };
          return { entity_id: m.entity_id, platform: 'schedule', unique_id: REGISTRY[m.entity_id] };
        }
        if (m.type === 'schedule/list') {
          if (state.onList) { const f = state.onList; state.onList = null; f(state.items); }
          return JSON.parse(JSON.stringify(Object.values(state.items)));
        }
        if (m.type === 'schedule/update') {
          if (state.refuse) throw { code: 'invalid_format', message: state.refuse };
          if (!state.items[m.schedule_id]) throw { code: 'not_found', message: `Unable to find schedule_id ${m.schedule_id}` };
          // As Home Assistant does: the item is replaced by what was sent.
          const { type, schedule_id, id, ...data } = m;
          state.items[schedule_id] = { id: schedule_id, ...data };
          return JSON.parse(JSON.stringify(state.items[schedule_id]));
        }
        return [];
      },
      subscribeEvents: async () => () => {}, subscribeMessage: async () => () => {},
    },
  };
  return { hass, sent };
}

const NET = { id: 'n1', name: 'Train home reminder', level: 'automation', collapsed: false, links: [], rungs: [{ id: 'r1', comment: '', elements: [
  { id: 'e1', type: 'cmp_eq', isTrigger: true, sourceA: 'datetime', sourceB: 'schedule.train_home_reminder', kind: 'datetime',
    raw: { trigger: 'state', entity_id: 'schedule.train_home_reminder', to: 'on', id: 'start' }, trigId: 'start' },
  { id: 'e2', type: 'move', mode: 'notify', source: 'Time to leave', target: 'notify.mobile_app_x' }] }] };

export async function scheduleEditChecks(check, { phone = false } = {}) {
  const asked = [];
  let answer = true;
  window.alert = () => {};
  window.confirm = (q) => { asked.push(String(q)); return answer; };
  window.prompt = () => null;
  if (!customElements.get('ha-entity-picker')) customElements.define('ha-entity-picker', class extends HTMLElement {});

  localStorage.clear();
  const state = { items: ITEMS(), onList: null, refuse: '' };
  const { hass, sent } = makeHass(state);
  const panel = document.createElement('libi-panel');
  panel.style.height = '800px';
  document.body.appendChild(panel);
  panel.hass = hass;
  await until(() => panel._initialized);
  await sleep(100);
  const sr = panel.shadowRoot;
  panel.core.nets = [JSON.parse(JSON.stringify(NET))];
  panel.core.syncCounters(); panel.core.repairAST(); panel.core.validateAST();
  panel._project = { slug: 'p', name: 'P' };
  panel._render(); await sleep(50);
  const el = () => panel.core.nets[0].rungs[0].elements[0];
  const updates = () => sent.filter(m => m.type === 'schedule/update');
  const editor = () => sr.querySelector('.sched-edit');
  const on = () => [...sr.querySelectorAll('.sched-day')].filter(b => b.classList.contains('on')).map(b => b.dataset.day);
  const now = () => (sr.querySelector('.sched-now') || {}).textContent || '';
  const said = () => [...sr.querySelectorAll('.sched-edit .insp-note')].map(n => n.textContent).join(' | ');
  const open = async (eid) => {
    el().sourceB = eid;
    // A click on a block gives a new _inspectedEl, as the canvas does.
    panel._inspectedEl = { netId: 'n1', rungId: 'r1', elId: 'e1' };
    panel._wakeSidebar();
    panel._render();
    await until(() => editor() && !/Reading the schedule/.test(editor().textContent));
    await sleep(20);
  };
  const setTime = async (cls, value) => {
    const input = sr.querySelector(`.sched-edit .${cls}`);
    input.value = value;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
  };
  const day = async (d) => { sr.querySelector(`.sched-day[data-day="${d}"]`).click(); await sleep(20); };
  const save = async () => { sr.querySelector('.sched-save').click(); await until(() => !(sr.querySelector('.sched-save') || {}).disabled); await sleep(30); };

  // ---- What the schedule holds, read from Home Assistant
  await open('schedule.train_home_reminder');
  check('the Inspector of the CMP DATETIME shows the editor of its schedule', !!editor());
  check('the helper is found by the entity registry', sent.some(m => m.type === 'config/entity_registry/get' && m.entity_id === 'schedule.train_home_reminder'));
  check('it shows the days and hours the schedule holds now', now() === 'Now: Mon Tue Wed Thu Sun 13:55–14:00', now());
  check('its days are ticked, in week order, Monday first', on().join() === 'monday,tuesday,wednesday,thursday,sunday'
        && [...sr.querySelectorAll('.sched-day')].map(b => b.textContent).join(' ') === 'Mon Tue Wed Thu Fri Sat Sun', on().join());
  check('each day says whether it is ticked', [...sr.querySelectorAll('.sched-day')].every(b => b.getAttribute('aria-pressed') === (b.classList.contains('on') ? 'true' : 'false')));
  check('its hours are in the two time fields', sr.querySelector('.sched-from').value === '13:55' && sr.querySelector('.sched-to').value === '14:00',
        `${sr.querySelector('.sched-from').value} ${sr.querySelector('.sched-to').value}`);
  check('it says the save is at once, not with SAVE & COMPILE, and that it works without LIBI', /saved at once in Home Assistant's own schedule, not with SAVE & COMPILE/.test(said())
        && /Without LIBI it stays as it is/.test(said()), said());

  // ---- Nothing changed: nothing written, nothing asked
  await save();
  check('Save with nothing changed writes nothing and asks nothing', updates().length === 0 && asked.length === 0
        && /Nothing changed/.test((sr.querySelector('.sched-status') || {}).textContent || ''), said());

  // ---- A draft survives a redraw
  await day('friday'); await day('sunday');
  panel._render(); await sleep(20);
  check('a day ticked stays ticked when the panel redraws', on().join() === 'monday,tuesday,wednesday,thursday,friday', on().join());

  // ---- Wrong hours are not sent
  await setTime('sched-from', '07:05'); await setTime('sched-to', '07:00');
  await save();
  check('an end before the start is refused, nothing written', updates().length === 0 && /It must end after it starts/.test(said()), said());
  await setTime('sched-from', ''); await save();
  check('a missing time is refused, nothing written', updates().length === 0 && /Set the time it starts and the time it ends/.test(said()), said());

  // ---- The user declines: nothing written
  await setTime('sched-from', '07:00'); await setTime('sched-to', '07:05');
  answer = false;
  await save();
  check('LIBI asks first, naming the schedule, now and new', asked.length === 1 && asked[0].includes('"Train Home Reminder"')
        && asked[0].includes('Now: Mon Tue Wed Thu Sun 13:55–14:00') && asked[0].includes('New: Mon Tue Wed Thu Fri 07:00–07:05')
        && asked[0].includes('not with SAVE & COMPILE'), asked[0]);
  check('declined, nothing is written', updates().length === 0);

  // ---- Saved: the whole schedule, as Home Assistant replaces it
  answer = true;
  await save();
  const up = updates()[0] || {};
  check('confirmed, one update is sent', updates().length === 1, updates().length);
  check('it sends the name, the icon and all seven days, the days not ticked empty', JSON.stringify(up) === JSON.stringify({
    type: 'schedule/update', schedule_id: 'train_home_reminder', name: 'Train Home Reminder',
    monday: [{ from: '07:00:00', to: '07:05:00' }], tuesday: [{ from: '07:00:00', to: '07:05:00' }],
    wednesday: [{ from: '07:00:00', to: '07:05:00' }], thursday: [{ from: '07:00:00', to: '07:05:00' }],
    friday: [{ from: '07:00:00', to: '07:05:00' }], saturday: [], sunday: [], icon: 'mdi:train' }), JSON.stringify(up));
  check('the schedule is read again right before the write', (() => {
    const i = sent.indexOf(sent.find(m => m.type === 'schedule/update'));
    return i > 0 && sent[i - 1].type === 'schedule/list';
  })());
  check('it says it was saved, with what Home Assistant has now', ((sr.querySelector('.sched-status') || {}).textContent || '') === 'Saved in Home Assistant: Mon Tue Wed Thu Fri 07:00–07:05.'
        && now() === 'Now: Mon Tue Wed Thu Fri 07:00–07:05', said());
  await until(() => /07:00–07:05/.test((sr.querySelector('.libi-el[data-eid="e1"] .plc-note') || {}).textContent || ''));
  check('the block on the canvas shows the new days and hours', ((sr.querySelector('.libi-el[data-eid="e1"] .plc-note') || {}).textContent || '') === 'Mon Tue Wed Thu Fri 07:00–07:05',
        (sr.querySelector('.libi-el[data-eid="e1"] .plc-note') || {}).textContent);
  check('the NET itself is not changed: nothing to save with SAVE & COMPILE', el().sourceB === 'schedule.train_home_reminder');

  // ---- To 00:00 is midnight
  await setTime('sched-from', '22:00'); await setTime('sched-to', '00:00');
  await save();
  check('To 00:00 is sent as 24:00:00, the end of the day', (updates()[1] || {}).monday && updates()[1].monday[0].to === '24:00:00'
        && updates()[1].monday[0].from === '22:00:00', JSON.stringify(updates()[1]));

  // ---- Changed in Home Assistant meanwhile: never overwritten
  await open('schedule.train_home_reminder');
  await day('saturday');
  state.onList = (items) => { items.train_home_reminder.wednesday = []; };  // the user's other window, before the write
  await save();
  check('changed in Home Assistant since it was read: nothing is written', updates().length === 2, updates().length);
  check('and LIBI says so and shows it as it is now', /changed in Home Assistant since LIBI showed it/.test(said()) && now() === 'Now: Mon Tue Thu Fri 22:00–24:00', said());

  // ---- Home Assistant refuses: shown as not saved
  await day('saturday');
  state.refuse = 'Invalid time range';
  await save();
  check('an error of Home Assistant is shown as not saved', /Not saved: Invalid time range/.test(said()) && !/Saved in Home Assistant/.test(said()), said());
  state.refuse = '';

  // ---- Days with different hours: one set of hours for all, said first
  await open('schedule.mixed');
  check('days with different hours: the days ticked, the hours to set again, and a warning', on().join() === 'monday,tuesday'
        && sr.querySelector('.sched-from').value === '' && /different hours now/.test(said())
        && now() === 'Now: Mon 06:00–06:30 · Tue 06:00–06:30, 18:00–19:00', said());
  await setTime('sched-from', '06:00'); await setTime('sched-to', '06:30');
  await save();
  const mixed = updates()[updates().length - 1];
  check('saved, every day ticked gets the same one block', mixed.schedule_id === 'mixed' && JSON.stringify(mixed.tuesday) === '[{"from":"06:00:00","to":"06:30:00"}]'
        && !('icon' in mixed), JSON.stringify(mixed));

  // ---- Not LIBI's to change
  const before = updates().length;
  await open('schedule.with_data');
  check('a schedule whose blocks carry data is shown, not edited', !sr.querySelector('.sched-day') && /extra data/.test(said()), said());
  await open('schedule.in_yaml');
  check('a schedule that is no helper of the settings (YAML) is not edited', !sr.querySelector('.sched-day') && /LIBI cannot change this schedule/.test(said()), said());
  await open('schedule.gone');
  check('a schedule Home Assistant does not have says so', !sr.querySelector('.sched-day') && /is not in Home Assistant/.test(said()), said());
  check('none of them is written', updates().length === before);

  // ---- A renamed entity: its helper by the registry, never by the entity id
  await open('schedule.renamed');
  await day('sunday');
  await save();
  const renamed = updates()[updates().length - 1];
  check('a renamed schedule is saved to its own helper (the registry\'s unique id)', renamed.schedule_id === 'other_id' && renamed.name === 'Renamed', JSON.stringify(renamed));

  // ---- Traces is read only
  await open('schedule.train_home_reminder');
  const ed = panel._schedEdit;
  panel.online.enabled = true;
  panel._render(); await sleep(20);
  check('while Traces is on, the Inspector shows no editor', !editor() && /Traces is on/.test(sr.querySelector('.sidebar-body').textContent));
  const n = updates().length;
  ed.days.add('saturday');
  await panel._saveScheduleEdit(ed);
  check('and nothing can be saved', updates().length === n);
  panel.online.enabled = false;
  panel._render(); await sleep(20);

  // ---- Fits the sidebar: desktop 320px wide, a phone the whole width
  await open('schedule.train_home_reminder');
  const body = sr.querySelector('#inspectorBody');
  const box = body.getBoundingClientRect();
  const buttons = [...sr.querySelectorAll('.sched-day')].map(b => b.getBoundingClientRect());
  const fields = [...sr.querySelectorAll('.sched-edit input[type=time]')].map(i => i.getBoundingClientRect());
  check(`${phone ? 'on a phone' : 'on a desktop'} the editor fits the Inspector: no sideways scroll, nothing outside it`,
        body.scrollWidth <= body.clientWidth + 1 && [...buttons, ...fields].every(r => r.left >= box.left - 1 && r.right <= box.right + 1),
        JSON.stringify([body.scrollWidth, body.clientWidth, box.left, box.right, buttons.map(r => [r.left, r.right])]));
  check('each day is a target at least 36px high and wide', buttons.length === 7 && buttons.every(r => r.height >= 36 && r.width >= 36),
        JSON.stringify(buttons.map(r => [r.width, r.height])));
  if (phone) {
    check('on a phone the Inspector is the whole width of the screen', box.width >= window.innerWidth - 40, JSON.stringify([box.width, window.innerWidth]));
  }

  // ---- [v3.95.5] Deleted in Home Assistant between showing it and the save: nothing written, and it says so
  await open('schedule.train_home_reminder');
  await day('saturday');
  const beforeGone = updates().length;
  state.onList = (items) => { delete items.train_home_reminder; };
  await save();
  check('a schedule deleted meanwhile: nothing written, and the editor says so', updates().length === beforeGone
        && /The schedule is no longer in Home Assistant\. Nothing was saved\./.test(said()), said());
}
