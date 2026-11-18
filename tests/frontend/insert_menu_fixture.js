// LIBI for Home Assistant - Copyright (C) 2026 Guy Azria - GPL-3.0-or-later
// Shared by test_panel_insert_menu*.html.
// [CHANGED v1.1.0 | 2026-11-18] Purpose: the user (2026-11-18): "I cannot add a DIV - show the categories, MATH, COUNTER,
//   TIMER, MOVE ..., and after a tap every block of that category; the logic too, all its symbols; and back to the
//   categories, easily". The + point's menu: the categories with how many blocks each has; a tap shows every block of
//   it with its symbol and its name; Back and Escape go back; Escape again closes. Each block is reached, adds itself,
//   and the menu stays on the screen near the top and the bottom, with no sideways scroll. Run against the real panel.

const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const until = async (cond, ms = 3000) => { const end = Date.now() + ms; while (!cond() && Date.now() < end) await sleep(10); return cond(); };

const NETS = () => [{ id: 'n1', name: 'Hall', level: 'automation', collapsed: false, links: [], rungs: [
  { id: 'r1', comment: '', elements: [{ id: 'e1', type: 'contact_no', isTrigger: true, label: 'binary_sensor.door' },
    { id: 'e2', type: 'coil_s', label: 'light.hall' }] }] }];

const CATEGORIES = 'Contacts|Compare|Coils|MOVE|Timers|Counter|Math|Structure';
const COUNTS = '4|7|4|4|3|1|7|2';

export async function insertMenuChecks(check, { phone = false } = {}) {
  window.alert = () => {};
  window.confirm = () => false;
  localStorage.clear();
  const hass = {
    states: {}, entities: {}, devices: {}, areas: {}, themes: { darkMode: false }, language: 'en',
    user: { is_admin: true }, localize: (k) => k, callService: async () => {},
    connection: {
      sendMessagePromise: async (m) => {
        if (m.type === 'libi/ai_status') return { configured: false };
        if (m.type === 'libi/project_list') return { projects: [{ slug: 'p', name: 'Home', nets: 1, revision: 1 }] };
        if (m.type === 'libi/project_open') return { slug: 'p', name: 'Home', revision: 1, stats: {}, versions: {}, nets: NETS() };
        return [];
      },
      subscribeEvents: async () => () => {}, subscribeMessage: async () => () => {},
    },
  };
  const panel = document.createElement('libi-panel');
  panel.style.height = '800px';
  document.body.appendChild(panel);
  panel.hass = hass;
  await until(() => panel._initialized && panel._project && panel.core.nets.length === 1);
  await sleep(80);
  const sr = panel.shadowRoot;
  const elements = () => panel.core.nets[0].rungs[0].elements;
  const open = async (y) => {
    const dot = sr.querySelector('.wire-ins[data-nid="n1"][data-rid="r1"]');
    const r = dot.getBoundingClientRect();
    panel._floatingMenu = { type: 'dot', netId: 'n1', rungId: 'r1', path: dot.getAttribute('data-path'), x: r.left + r.width / 2, y, bottom: y + r.height };
    panel._render();
    await sleep(30);
    return sr.querySelector('#fmBox');
  };
  const tap = async (node) => { node.click(); await sleep(30); return sr.querySelector('#fmBox'); };
  const key = async (k) => { window.dispatchEvent(new KeyboardEvent('keydown', { key: k })); await sleep(30); return sr.querySelector('#fmBox'); };
  const onScreen = (box) => {
    const r = box.getBoundingClientRect();
    return r.top >= 0 && r.left >= 0 && r.bottom <= window.innerHeight + 0.5 && r.right <= window.innerWidth + 0.5;
  };
  const fits = (box) => [...box.querySelectorAll('.pal-btn')].every(b => {
    const r = b.getBoundingClientRect(); const p = box.getBoundingClientRect();
    return r.left >= p.left - 0.5 && r.right <= p.right + 0.5;
  }) && box.querySelector('.palette-body').scrollWidth <= box.querySelector('.palette-body').clientWidth + 1;
  const names = (box) => [...box.querySelectorAll('.pal-item')].map(b => b.querySelector('b').textContent);

  // ---- step 1: the categories
  let box = await open(window.innerHeight / 2);
  const cats = [...box.querySelectorAll('.pal-cat')];
  check('a tap on a point shows the categories', cats.map(c => c.querySelector('.pal-cat-name').textContent).join('|') === CATEGORIES,
        cats.map(c => c.textContent).join('|'));
  check('each says how many blocks it has', cats.map(c => c.querySelector('.pal-cat-count').textContent).join('|') === COUNTS);
  check('and what it is, in words', cats.every(c => /^\w[\w ]*: \d+ blocks?$/.test(c.title) && c.getAttribute('aria-label') === c.title));
  check('no block yet: only the categories', !box.querySelector('.pal-item') && !box.querySelector('.pal-back'));
  check('the categories fit, no sideways scroll', fits(box) && onScreen(box), JSON.stringify(box.getBoundingClientRect()));

  // ---- step 2: Math, and a DIV
  box = await tap(box.querySelector('.pal-cat[data-val="math"]'));
  check('Math shows every block of it, by name', names(box).join('|') === 'ADD|SUB|MUL|DIV|MOD|RAND|MUX', names(box).join('|'));
  const div = box.querySelector('.pal-item[data-val="math_div"]');
  check('each with what it does', div.querySelector('.pal-item-more').textContent === 'IN1 divided by IN2' && div.title === 'DIV - IN1 divided by IN2');
  check('with Back to the categories, and the category named', !!box.querySelector('.pal-back') && box.querySelector('.palette-title').textContent === 'Math');
  check('the first block is ready for the keyboard', sr.activeElement === box.querySelector('.pal-item'));
  check('the blocks fit, no sideways scroll, on the screen', fits(box) && onScreen(box), JSON.stringify(box.getBoundingClientRect()));
  await tap(div);
  check('DIV is added, and the menu closes', elements().map(e => e.type).join() === 'math_div,contact_no,coil_s' && !sr.querySelector('#fmBox'),
        elements().map(e => e.type).join());
  panel.core.nets[0].rungs[0].elements = elements().filter(e => e.type !== 'math_div');
  panel._render();
  await sleep(30);

  // ---- the logic: all the symbols of a contact
  box = await open(window.innerHeight / 2);
  box = await tap(box.querySelector('.pal-cat[data-val="contacts"]'));
  check('Contacts: NO, NC, P and N, each with its symbol', names(box).join('|') === 'Contact NO|Contact NC|Rising edge (P)|Falling edge (N)'
        && box.querySelectorAll('.pal-item .pal-cat-icon svg, .pal-item .pal-cat-icon div').length >= 4, names(box).join('|'));

  // ---- back, easily
  box = await tap(box.querySelector('.pal-back'));
  check('Back shows the categories again, the menu still open', !!box && box.querySelectorAll('.pal-cat').length === 8 && !box.querySelector('.pal-item'));
  check('the category it came from is ready for the keyboard', sr.activeElement === box.querySelector('.pal-cat[data-val="contacts"]'));
  box = await tap(box.querySelector('.pal-cat[data-val="timers"]'));
  box = await key('Escape');
  check('Escape in a category goes back to the categories', !!box && box.querySelectorAll('.pal-cat').length === 8);
  box = await key('Escape');
  check('Escape again closes the menu', !box && panel._floatingMenu === null);

  // ---- every block is reached, named, and adds itself
  box = await open(window.innerHeight / 2);
  const all = [];
  for (const id of [...box.querySelectorAll('.pal-cat')].map(c => c.dataset.val)) {
    box = await tap(sr.querySelector(`#fmBox .pal-cat[data-val="${id}"]`));
    all.push(...[...box.querySelectorAll('.pal-item')].map(b => ({ val: b.dataset.val, title: b.title, label: b.getAttribute('aria-label') })));
    box = await tap(box.querySelector('.pal-back'));
  }
  check('all thirty-two blocks are there, once each', all.length === 32 && new Set(all.map(b => b.val)).size === 32, all.length);
  check('every block says in words what it is', all.every(b => b.title && b.title !== b.val && b.label === b.title), all.filter(b => !b.title || b.title === b.val).map(b => b.val).join());
  box = await tap(box.querySelector('.pal-cat[data-val="move"]'));
  check('MOVE: a value, a message, a voice, both', names(box).join('|') === 'MOVE|MESSAGE|TTS|MESSAGE + TTS', names(box).join('|'));
  await tap(box.querySelector('.pal-item[data-val="move_notify"]'));
  const msg = elements().find(e => e.type === 'move');
  check('MESSAGE adds a MOVE that sends a message', !!msg && msg.mode === 'notify', JSON.stringify(msg));
  box = await open(window.innerHeight / 2);
  box = await tap(box.querySelector('.pal-cat[data-val="timers"]'));
  check('Timers: TON, TOF and EVERY', names(box).join('|') === 'Timer TON|Timer TOF|EVERY', names(box).join('|'));
  await tap(box.querySelector('.pal-item[data-val="every"]'));
  const every = elements().find(e => e.sourceA === 'time pattern');
  check('EVERY adds a time pattern that starts the rung, every 10 seconds', !!every && every.type === 'cmp_eq' && every.sourceB === 'seconds=/10' && every.isTrigger === true,
        JSON.stringify(every));
  panel.core.nets[0].rungs[0].elements = NETS()[0].rungs[0].elements;
  panel._render();
  await sleep(30);

  // ---- on the screen, near the top and the bottom, at both steps
  for (const step of ['categories', 'compare']) {
    const show = async (y) => { let b = await open(y); if (step !== 'categories') b = await tap(b.querySelector(`.pal-cat[data-val="${step}"]`)); return b; };
    box = await show(70);
    check(`near the top the ${step} open under the point, on the screen`, onScreen(box) && box.getBoundingClientRect().top > 70, JSON.stringify(box.getBoundingClientRect()));
    box = await show(window.innerHeight - 50);
    check(`near the bottom the ${step} open above the point, on the screen`, onScreen(box) && box.getBoundingClientRect().bottom <= window.innerHeight - 50,
          JSON.stringify(box.getBoundingClientRect()));
    box = await show(70);
    const body0 = box.querySelector('.palette-body');
    const whole = body0.scrollHeight + (box.offsetHeight - body0.clientHeight);
    const squeezed = [];
    for (let y = 100; y < window.innerHeight - 40; y += 20) {
      box = await show(y);
      const body = box.querySelector('.palette-body');
      const room = Math.max(y - 10, window.innerHeight - (y + 16 + 10)) - 12;
      if (room >= whole && body.scrollHeight > body.clientHeight + 1) squeezed.push(y);
    }
    check(`with room for them on one side, the ${step} are whole there`, squeezed.length === 0, `menu ${whole}px, squeezed at y = ${squeezed.join(', ')}`);
    // With room on neither side, they open on the side with more room (a long category on a short screen).
    const smaller = [];
    for (let y = 130; y < window.innerHeight - 40; y += 20) {
      box = await show(y);
      const above = y - 18, below = window.innerHeight - (y + 16) - 18;
      const isBelow = box.getBoundingClientRect().top > y;
      if (whole > above && whole > below && Math.abs(above - below) > 24 && isBelow !== (below > above)) smaller.push(y);
    }
    check(`with room on neither side, the ${step} open on the side with more`, smaller.length === 0, `at y = ${smaller.join(', ')}`);
    if (phone) {
      const btn = box.querySelector(step === 'categories' ? '.pal-cat' : '.pal-item').getBoundingClientRect();
      check(`on a phone a button of the ${step} is a target a finger can hit`, btn.height >= 40 && btn.width >= 40, `${btn.width}x${btn.height}`);
    }
  }

  // ---- paste at the categories, and the menu of a block
  panel.core.clipboard = { id: 'c1', type: 'coil', label: 'light.hall' };
  box = await open(window.innerHeight / 2);
  check('with a block copied, Paste is there with the categories', !!box.querySelector('.pal-btn[data-action="paste"]'));
  box = await tap(box.querySelector('.pal-cat[data-val="coils"]'));
  check('and not among the blocks of a category', !box.querySelector('.pal-btn[data-action="paste"]'));
  panel.core.clipboard = null;
  panel._floatingMenu = null;
  const r = sr.querySelector('.libi-el[data-eid="e1"]').getBoundingClientRect();
  panel._floatingMenu = { type: 'element', netId: 'n1', rungId: 'r1', elId: 'e1', x: r.left + r.width / 2, y: r.top, bottom: r.bottom };
  panel._render();
  await sleep(30);
  const kinds = [...sr.querySelectorAll('#fmBox .pal-btn[data-action="mod"]')].map(b => b.title);
  check('a block\'s menu names its other kinds', kinds.join('|') === 'Contact NO - true while it is on|Contact NC - true while it is off|Rising edge (P) - the moment it turns on, or a value changes|Falling edge (N) - the moment it turns off',
        kinds.join('|'));
  panel._floatingMenu = null;
  panel._markSaved && panel._markSaved();
  panel.remove();
}
