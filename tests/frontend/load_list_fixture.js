// LIBI for Home Assistant - Copyright (C) 2026 Guy Azria - GPL-3.0-or-later
// Shared by test_panel_load_list*.html.
// [ADDED v1.0.0 | 2026-11-10] Purpose: the user's rule (2026-11-10) - an automation belongs to one project. LOAD's window
//   offers only the automations no project holds; under the heading IN USE the others, each with the project that holds
//   it (or the NET of this page that shows it), which cannot be chosen. A load the backend refuses says why and lists
//   again; while a project cannot be read, nothing can be chosen. Run against the real panel, with canned answers.

const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const until = async (cond, ms = 3000) => { const end = Date.now() + ms; while (!cond() && Date.now() < end) await sleep(10); return cond(); };

const NET = (id, extra = {}) => ({ id, name: 'NET ' + id, level: 'automation', collapsed: false, links: [], rungs: [{ id: 'r1', comment: '', elements: [
  { id: 'e1', type: 'contact_no', isTrigger: true, label: 'binary_sensor.door' },
  { id: 'e2', type: 'coil_s', label: 'light.x' }] }], ...extra });

export const LIST = [
  { id: 'a1', name: 'Stairs', in_use: [] },
  { id: 'a2', name: 'Kitchen table', in_use: [{ slug: 'garden', name: 'Garden' }] },
  { id: 'a3', name: '<img src=x onerror="window.__xss=1">Lamp', in_use: [{ slug: 'p', name: '<b>Home</b>' }] },
  { id: 'a4', name: 'Shown by NET 2', in_use: [] },
  { id: 'a5', name: 'From an older backend' },
  { id: 'a6', name: 'Taken meanwhile', in_use: [] },
];

function makeHass({ list = LIST, unreadable = [], refuse = {} } = {}) {
  const sent = [];
  const hass = {
    states: {}, entities: {}, devices: {}, areas: {}, themes: { darkMode: false }, language: 'en',
    user: { is_admin: true }, localize: (k) => k, callService: async () => {}, callApi: async () => ({ result: 'ok' }),
    connection: {
      sendMessagePromise: async (m) => {
        sent.push(JSON.parse(JSON.stringify(m)));
        if (m.type === 'libi/ai_status') return { configured: false };
        if (m.type === 'libi/project_list') return { projects: [{ slug: 'p', name: 'Home Lights', nets: 2, revision: 3 }] };
        if (m.type === 'libi/project_open') {
          return { slug: 'p', name: 'Home Lights', revision: 3, stats: {}, versions: {},
                   nets: [NET('n1', { name: 'Empty' }), NET('n2', { ha_id: 'a4', name: 'Shown' })] };
        }
        if (m.type === 'libi/list_automations') return { automations: JSON.parse(JSON.stringify(list)), unreadable };
        if (m.type === 'libi/get_automation') {
          if (refuse[m.automation_id]) throw { code: 'in_use', message: refuse[m.automation_id] };
          return { net: NET('x', { name: 'Loaded ' + m.automation_id, ha_id: m.automation_id }), verify: { ok: true }, versions: {} };
        }
        if (m.type === 'libi/load_automation') return { nets: [] };
        return [];
      },
      subscribeEvents: async () => () => {}, subscribeMessage: async () => () => {},
    },
  };
  return { hass, sent };
}

async function start(opts) {
  localStorage.clear();
  const { hass, sent } = makeHass(opts);
  const panel = document.createElement('libi-panel');
  panel.style.height = '800px';
  document.body.appendChild(panel);
  panel.hass = hass;
  await until(() => panel._initialized && panel._project);
  await sleep(50);
  return { panel, sent };
}

async function openLoad(panel, nid = 'n1') {
  const btn = panel.shadowRoot.querySelector(`.load-net-btn[data-nid="${nid}"]`);
  if (btn) btn.click();
  await until(() => panel.shadowRoot.querySelector('.modal .auto-list'));
  await sleep(20);
  return panel.shadowRoot.querySelector('.modal');
}

const where = (row) => (row.querySelector('.auto-where') || {}).textContent || '';
const gets = (sent) => sent.filter(m => m.type === 'libi/get_automation');

export async function loadListChecks(check, { phone = false } = {}) {
  const alerts = [];
  window.alert = (m) => alerts.push(String(m));
  window.confirm = () => false;
  window.prompt = () => null;
  if (!customElements.get('ha-entity-picker')) customElements.define('ha-entity-picker', class extends HTMLElement {});

  // ---- The list: free ones to choose, then IN USE
  let { panel, sent } = await start({ refuse: { a6: 'This automation is already in the project Garden. An automation belongs to one project.' } });
  let modal = await openLoad(panel);
  check('LOAD opens the window', !!modal && /Select HA Automation/.test(modal.textContent));
  const free = [...modal.querySelectorAll('.auto-item[data-id]')].map(r => r.getAttribute('data-id'));
  check('only the automations no project holds can be chosen, in the file order', free.join() === 'a1,a5,a6', free.join());
  const sec = modal.querySelector('.auto-sec');
  check('under them the heading IN USE', !!sec && sec.textContent.trim() === 'IN USE', sec && sec.textContent);
  const firstFree = modal.querySelector('.auto-item[data-id]');
  check('IN USE comes after the ones to choose', !!sec && !!firstFree
        && !!(firstFree.compareDocumentPosition(sec) & Node.DOCUMENT_POSITION_FOLLOWING));
  const used = [...modal.querySelectorAll('.auto-used')];
  check('three are in use', used.length === 3, used.length);
  const row = (name) => used.find(r => (r.querySelector('.auto-item-name') || {}).textContent === name);
  check('one another project holds shows that project', where(row('Kitchen table') || modal) === 'Garden', where(row('Kitchen table') || modal));
  const own = row('<img src=x onerror="window.__xss=1">Lamp');
  check('one this project holds says so, its name and project as text', !!own && where(own) === '<b>Home</b> (this project)', own && where(own));
  check('nothing in a name or a project name becomes HTML', !modal.querySelector('img, b') && window.__xss === undefined);
  check('one another NET of this page shows, not saved yet, says which NET', where(row('Shown by NET 2') || modal) === 'NET 2 on this page');
  check('a row in use cannot be chosen: no id to load, no pointer', used.every(r => !r.hasAttribute('data-id')
        && !r.classList.contains('auto-item') && getComputedStyle(r).cursor === 'default'));
  for (const r of used) r.click();
  await sleep(50);
  check('a click on a row in use loads nothing, and the window stays', gets(sent).length === 0 && !!panel.shadowRoot.querySelector('.modal .auto-used'),
        JSON.stringify(gets(sent)));

  if (phone) {
    const box = modal.getBoundingClientRect();
    check('on a phone the window fits the screen', box.left >= -1 && box.right <= window.innerWidth + 1, JSON.stringify([box.left, box.right, window.innerWidth]));
    const list = modal.querySelector('.auto-list');
    check('and its list has no sideways scroll', list.scrollWidth <= list.clientWidth + 1, `${list.scrollWidth} > ${list.clientWidth}`);
    check('the project of a row in use is shown', used.every(r => r.querySelector('.auto-where').getBoundingClientRect().height > 0));
  }

  // ---- A refusal from the backend (another page took it meanwhile): said, and the list fetched again
  const lists = sent.filter(m => m.type === 'libi/list_automations').length;
  modal.querySelector('.auto-item[data-id="a6"]').click();
  await until(() => alerts.length > 0);
  await sleep(50);
  check('a load the backend refuses says why', alerts.length === 1 && alerts[0].startsWith('This automation is already in the project Garden'), alerts.join(' | '));
  check('and the list is fetched again', sent.filter(m => m.type === 'libi/list_automations').length === lists + 1);
  check('NET 1 is unchanged', panel.core.nets[0].name === 'Empty' && !panel.core.nets[0].ha_id, JSON.stringify(panel.core.nets[0].name));

  // ---- A free one loads into the NET LOAD was pressed on
  modal = panel.shadowRoot.querySelector('.modal');
  modal.querySelector('.auto-item[data-id="a1"]').click();
  await until(() => !panel.shadowRoot.querySelector('.modal .auto-list'));
  const got = gets(sent).at(-1) || {};
  check('a free one is loaded into that NET of this project', got.automation_id === 'a1' && got.slug === 'p' && got.net_id === 'n1', JSON.stringify(got));
  check('and is on the canvas there', panel.core.nets[0].id === 'n1' && panel.core.nets[0].name === 'Loaded a1', JSON.stringify(panel.core.nets[0].name));
  panel._markSaved(); panel.remove(); await sleep(50);

  // ---- Every one held: nothing to choose, said
  ({ panel, sent } = await start({ list: LIST.filter(a => a.in_use && a.in_use.length) }));
  modal = await openLoad(panel);
  check('when every automation is in a project, the window says so', (modal.querySelector('.auto-none') || {}).textContent === 'Every automation is in a project already.'
        && modal.querySelectorAll('.auto-item[data-id]').length === 0);
  panel._markSaved(); panel.remove(); await sleep(50);

  // ---- A project LIBI cannot read: it may hold any, so nothing can be chosen
  ({ panel, sent } = await start({ unreadable: ['broken'] }));
  modal = await openLoad(panel);
  const warn = modal.querySelector('.auto-warn');
  check('a project that cannot be read is named', !!warn && warn.textContent.includes('broken'), warn && warn.textContent);
  check('and nothing can be chosen', modal.querySelectorAll('.auto-item[data-id]').length === 0 && modal.querySelectorAll('.auto-used').length === LIST.length);
  check('and no heading or note pretends to know which project holds which', !modal.querySelector('.auto-sec')
        && !modal.querySelector('.auto-sec-note') && !modal.querySelector('.auto-none'));
  for (const r of modal.querySelectorAll('.auto-used')) r.click();
  await sleep(50);
  check('a click loads nothing', gets(sent).length === 0);
  panel._markSaved(); panel.remove(); await sleep(50);

  // ---- [v3.95.5] A NET may load its own automation again, as libi/get_automation allows (the review of the release)
  ({ panel, sent } = await start({ list: [
    { id: 'a7', name: 'Its own', in_use: [{ slug: 'p', name: 'Home Lights', nets: ['n1'] }] },
    { id: 'a8', name: 'Another NET of it', in_use: [{ slug: 'p', name: 'Home Lights', nets: ['n2'] }] },
    { id: 'a9', name: 'Made by this project', in_use: [{ slug: 'p', name: 'Home Lights', nets: [] }] },
    { id: 'a10', name: 'Also in another project', in_use: [{ slug: 'p', name: 'Home Lights', nets: ['n1'] }, { slug: 'q', name: 'Garden', nets: ['n5'] }] }] }));
  modal = await openLoad(panel);
  const mine = [...modal.querySelectorAll('.auto-item[data-id]')].map(r => r.getAttribute('data-id')).join();
  check('the NET LOAD was opened on is offered its own automation again, and one this project made', mine === 'a7,a9', mine);
  const others = [...modal.querySelectorAll('.auto-used')].map(r => (r.querySelector('.auto-where') || {}).textContent).join(' | ');
  check('one another NET of this project holds, or another project too, stays IN USE', others === 'Home Lights (this project) | Garden', others);
  // With no project open, the project is "default", as the backend has it (the third pass of the review).
  panel._project = null;
  panel._activeNetForLoad = 'n1';
  panel._automationList = [{ id: 'a11', name: 'In default', in_use: [{ slug: 'default', name: 'Default', nets: ['n1'] }] }];
  panel._automationUnreadable = [];
  const box = document.createElement('div');
  box.innerHTML = panel._loadListHtml();
  check('with no project open, a NET of "default" is offered its own automation', !!box.querySelector('.auto-item[data-id="a11"]'), box.textContent);
  panel._markSaved(); panel.remove(); await sleep(50);
}
