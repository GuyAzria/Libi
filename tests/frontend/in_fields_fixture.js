// LIBI for Home Assistant - Copyright (C) 2026 Guy Azria - GPL-3.0-or-later
// Shared by test_panel_in_fields*.html.
// [ADDED v1.0.0 | 2026-11-18] Purpose: the user (2026-11-18): "every IN1 or IN2: a variable from a list - a HELPER or the
//   variables that make sense, not booleans, found easily by category - or a value typed, like 20; and IN3, 4, 5 added
//   with a button in the Inspector". Every IN pin is one field: a value, or Variable - the entity browser opens on the
//   helpers, with only what holds a value of the pin's kind - shown by its name, id and value now, × back to a value.
//   ADD, SUB, MUL and DIV take IN3 ... IN8; MOD and RAND keep two. A pin of a list (more.N, inputs.N) is read and written
//   as that input, by the Inspector, the browser and a variable dropped on it. Real panel, canned answers.

const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const until = async (cond, ms = 3000) => { const end = Date.now() + ms; while (!cond() && Date.now() < end) await sleep(10); return cond(); };

const START = (id) => ({ id, type: 'contact_no', isTrigger: true, label: 'binary_sensor.motion' });
const NETS = () => [{ id: 'n1', name: 'Calc', level: 'automation', collapsed: false, links: [], rungs: [
  { id: 'r1', comment: '', elements: [START('a0'), { id: 'a1', type: 'math_add', sourceA: '', sourceB: '', target: 'input_number.sum' }] },
  { id: 'r2', comment: '', elements: [START('b0'), { id: 'b1', type: 'cmp_gt', sourceA: '', sourceB: '' }, { id: 'b2', type: 'coil', label: 'light.hall' }] },
  { id: 'r3', comment: '', elements: [START('c0'), { id: 'c1', type: 'math_mod', sourceA: 'counter.step', sourceB: '4', target: 'counter.step' }] },
  { id: 'r4', comment: '', elements: [START('d0'), { id: 'd1', type: 'mux', sourceA: '0', inputs: ['red', 'blue'], target: 'light.hall', valueKey: 'color_name' }] },
  { id: 'r5', comment: '', elements: [START('e0'), { id: 'e1', type: 'cmp_rng', sourceA: 'sensor.temperature', sourceB: '18', sourceC: '' },
    { id: 'e2', type: 'coil', label: 'light.hall' }] }] }];

const S = (id, state, attrs = {}) => ({ entity_id: id, state, attributes: { friendly_name: id.split('.')[1], ...attrs } });
const STATES = {
  'input_number.dim': S('input_number.dim', '40.0', { friendly_name: 'Dim <b>x</b>', unit_of_measurement: '%' }),
  'input_number.sum': S('input_number.sum', '0.0'),
  'counter.step': S('counter.step', '3'),
  'input_select.colour': S('input_select.colour', 'red', { options: ['red', 'blue'] }),
  'input_text.note': S('input_text.note', 'hello'),
  'input_boolean.away': S('input_boolean.away', 'off'),
  'binary_sensor.motion': S('binary_sensor.motion', 'off'),
  'switch.pump': S('switch.pump', 'off'),
  'light.hall': S('light.hall', 'off'),
  'sensor.temperature': S('sensor.temperature', '21.5', { unit_of_measurement: '°C' }),
  'sensor.status': S('sensor.status', 'idle'),
  'number.valve_limit': S('number.valve_limit', '30'),
  'select.mode': S('select.mode', 'eco', { options: ['eco', 'boost'] }),
};

export async function inFieldChecks(check, { size = 'desktop' } = {}) {
  window.alert = () => {};
  window.confirm = () => false;
  window.prompt = () => null;
  if (!customElements.get('ha-entity-picker')) customElements.define('ha-entity-picker', class extends HTMLElement {});
  localStorage.clear();
  const panel = document.createElement('libi-panel');
  panel.style.height = '800px';
  document.body.appendChild(panel);
  panel.hass = {
    states: JSON.parse(JSON.stringify(STATES)), entities: {}, devices: {}, areas: {}, themes: { darkMode: false }, language: 'en',
    user: { is_admin: true }, localize: (k) => k, callService: async () => {}, callApi: async () => ({ result: 'ok' }),
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
  await until(() => panel._initialized && panel._project && panel.core.nets.length === 1);
  await sleep(80);
  const sr = panel.shadowRoot;
  const el = (rid, id) => panel.core.findEl('n1', rid, id);
  const block = (id) => sr.querySelector(`.libi-el[data-eid="${id}"]`);
  const red = (id) => !!block(id) && block(id).classList.contains('has-error');
  const pins = (id) => [...block(id).querySelectorAll('.plc-row .pin-lbl')].map(p => p.textContent.trim()).filter(Boolean);
  const inspect = async (rid, id) => {
    panel._inspectedEl = { netId: 'n1', rungId: rid, elId: id };
    panel._wakeSidebar();
    panel._render();
    await sleep(30);
    return sr.querySelector('#inspectorBody');
  };
  const fire = async (node, type) => { node.dispatchEvent(new Event(type, { bubbles: true })); await sleep(30); };
  const field = (id) => sr.querySelector(`#inspectorBody #inp_${id}`).closest('.in-field');
  const openVar = async (id) => { field(id).querySelector('.in-pick').click(); await sleep(40); return sr.querySelector('.ep-modal'); };
  const offered = () => [...sr.querySelectorAll('.ep-modal .ep-pick')].map(r => r.dataset.eid).sort();
  const tab = async (id) => { sr.querySelector(`#${id}`).click(); await sleep(30); };
  // The groups of a tab open with a tap - or all of them with a search: '.' is in every entity's id.
  const all = async () => { panel._epQuery = '.'; panel._render(); await sleep(30); };
  const closeModal = async () => { panel._modal = null; panel._ep = null; panel._render(); await sleep(20); };

  // ---- an IN pin: a value typed, or a variable
  let body = await inspect('r1', 'a1');
  check('ADD: IN1 and IN2, each a value with a Variable button - and OUT', !!body.querySelector('#inp_sourceA') && !!body.querySelector('#inp_sourceB')
        && body.querySelectorAll('.in-field .in-pick').length === 3 && !!body.querySelector('#inp_target'));
  const in1 = body.querySelector('#inp_sourceA');
  in1.value = ' 20 ';
  await fire(in1, 'change');
  check('20 typed is IN1', el('r1', 'a1').sourceA === '20' && pins('a1').join() === 'IN1,OUT,IN2');
  let modal = await openVar('sourceB');
  check('Variable opens the browser on the helpers', !!modal && /Choose a variable/.test(modal.textContent) && !!sr.querySelector('#epTabHelpers.on')
        && [...modal.querySelectorAll('.ep-group .nm')].map(n => n.textContent).join('|') === 'Number helpers|Counters', [...modal.querySelectorAll('.ep-group .nm')].map(n => n.textContent).join('|'));
  check('a number pin is offered numbers - never on or off', offered().join() === 'counter.step,input_number.dim,input_number.sum', offered().join());
  await tab('epTabType');
  check('by type, the categories start folded: a tap opens one', offered().length === 0 && sr.querySelectorAll('.ep-modal .ep-group').length >= 4);
  await all();
  check('by type, the sensors that hold a number and the settings of devices - no boolean, no word', offered().join() ===
        'counter.step,input_number.dim,input_number.sum,number.valve_limit,sensor.temperature', offered().join());
  panel._epQuery = '';
  await tab('epTabHelpers');
  sr.querySelector('.ep-modal .ep-pick[data-eid="input_number.dim"]').click();
  await sleep(40);
  body = sr.querySelector('#inspectorBody');
  check('the variable picked is IN2, shown by name, id and value now', el('r1', 'a1').sourceB === 'input_number.dim'
        && (body.querySelector('#inp_sourceB .in-eid') || {}).textContent === 'input_number.dim'
        && (body.querySelector('#inp_sourceB .in-now') || {}).textContent === '40.0 %');
  check('a name with markup is text', !body.querySelector('#inp_sourceB b b') && (body.querySelector('#inp_sourceB b') || {}).textContent === 'Dim <b>x</b>');
  field('sourceB').querySelector('.in-clear').click();
  await sleep(30);
  check('× goes back to a value', el('r1', 'a1').sourceB === '' && !!sr.querySelector('#inspectorBody input#inp_sourceB'));

  // ---- IN3, IN4 ... of ADD
  sr.querySelector('#inspectorBody #inAdd').click();
  await sleep(30);
  check('+ Add an input gives IN3, empty - the block red until it has one', JSON.stringify(el('r1', 'a1').more) === '[""]' && red('a1')
        && pins('a1').join() === 'IN1,OUT,IN2,IN3');
  body = sr.querySelector('#inspectorBody');
  const in3 = body.querySelector('#inp_more0');
  in3.value = '5';
  await fire(in3, 'change');
  check('typed, IN3 is 5', JSON.stringify(el('r1', 'a1').more) === '["5"]');
  modal = await openVar('more0');
  sr.querySelector('.ep-modal .ep-pick[data-eid="counter.step"]').click();
  await sleep(40);
  check('a variable for IN3 is IN3', JSON.stringify(el('r1', 'a1').more) === '["counter.step"]' && el('r1', 'a1')['more.0'] === undefined);
  for (let i = 0; i < 10; i++) { const add = sr.querySelector('#inspectorBody #inAdd'); if (!add) break; add.click(); await sleep(20); }
  check('up to IN8: then no button', (el('r1', 'a1').more || []).length === 6 && !sr.querySelector('#inspectorBody #inAdd'));
  for (let i = 0; i < 10; i++) {
    const del = sr.querySelectorAll('#inspectorBody .in-field .in-del');
    if (!del.length) break;
    del[del.length - 1].click();
    await sleep(20);
  }
  check('removing them all leaves the block as it was: no more', !('more' in el('r1', 'a1')) && pins('a1').join() === 'IN1,OUT,IN2');

  // ---- MOD and RAND keep two; MUX's inputs; a compare
  body = await inspect('r3', 'c1');
  check('MOD: two inputs and OUT, no button to add one', !body.querySelector('#inAdd') && body.querySelectorAll('.in-field').length === 3);
  check('its variable shows: counter.step = 3', (body.querySelector('#inp_sourceA .in-now') || {}).textContent === '3');
  el('r3', 'c1').more = ['2'];
  panel._render();
  await sleep(30);
  body = await inspect('r3', 'c1');
  check('a MOD given IN3 - its kind changed from ADD - is red, and says why', red('c1')
        && /MOD takes two inputs, IN1 and IN2: remove IN3/.test((body.querySelector('.calc-why') || {}).textContent || ''));
  delete el('r3', 'c1').more;
  body = await inspect('r4', 'd1');
  modal = await openVar('inputs1');
  check('a MUX input of a color by name is offered words: lists, texts, device lists', offered().join() === 'input_select.colour,input_text.note', offered().join());
  sr.querySelector('.ep-modal .ep-pick[data-eid="input_select.colour"]').click();
  await sleep(40);
  check('picked, it is that input - not a field of its own', JSON.stringify(el('r4', 'd1').inputs) === '["red","input_select.colour"]' && el('r4', 'd1').input1 === undefined);
  body = await inspect('r2', 'b1');
  check('a compare: IN1 a variable only, IN2 a value or a variable', !!body.querySelector('#inp_sourceA.in-empty') && !body.querySelector('input#inp_sourceA')
        && !!body.querySelector('input#inp_sourceB'));
  modal = await openVar('sourceA');
  await tab('epTabType');
  await all();
  check('what a compare reads: never on or off', !offered().some(e => /^(input_boolean|binary_sensor|switch|light)\./.test(e))
        && offered().includes('sensor.status') && offered().includes('select.mode'), offered().join());
  await closeModal();
  body = await inspect('r5', 'e1');
  check('a range: what is measured, MIN and MAX - a value or a variable each', !!body.querySelector('#inp_sourceA .in-eid') && !!body.querySelector('input#inp_sourceB')
        && !!body.querySelector('input#inp_sourceC') && body.querySelectorAll('.in-field .in-pick').length === 3);

  // ---- OUT, chosen as an IN is: what can TAKE the result
  body = await inspect('r1', 'a1');
  check('ADD: OUT is its variable, shown by name, id and value now', (body.querySelector('#inp_target .in-eid') || {}).textContent === 'input_number.sum'
        && (body.querySelector('#inp_target .in-now') || {}).textContent === '0.0' && !body.querySelector('input#inp_target'));
  modal = await openVar('target');
  check('its browser says where the result goes, on the helpers', /Where the result goes/.test(modal.textContent) && !!sr.querySelector('#epTabHelpers.on')
        && [...modal.querySelectorAll('.ep-group .nm')].map(n => n.textContent).join('|') === 'Number helpers|Counters|Texts',
        [...modal.querySelectorAll('.ep-group .nm')].map(n => n.textContent).join('|'));
  await tab('epTabType');
  await all();
  check('what can take a number: helpers, counters, texts, a device\'s number - never a sensor, a list, a light', offered().join() ===
        'counter.step,input_number.dim,input_number.sum,input_text.note,number.valve_limit', offered().join());
  sr.querySelector('.ep-modal .ep-pick[data-eid="number.valve_limit"]').click();
  panel._epQuery = '';
  await sleep(40);
  check('picked, it is OUT - and what it is drawn as', el('r1', 'a1').target === 'number.valve_limit'
        && JSON.stringify(el('r1', 'a1').targetSpec) === '{"entity_id":["number.valve_limit"]}');
  field('target').querySelector('.in-clear').click();
  await sleep(30);
  check('× clears OUT, and what it was drawn as; the block is red until one is chosen', el('r1', 'a1').target === ''
        && JSON.stringify(el('r1', 'a1').targetSpec) === '{}' && red('a1') && !!sr.querySelector('#inspectorBody #inp_target.in-empty'));
  el('r1', 'a1').target = 'input_number.sum';
  delete el('r1', 'a1').targetSpec;
  body = await inspect('r4', 'd1');
  modal = await openVar('target');
  await tab('epTabType');
  await all();
  check('MUX: OUT is a helper or a device that takes a value - never a sensor, a switch', offered().join() ===
        'counter.step,input_number.dim,input_number.sum,input_select.colour,input_text.note,light.hall,number.valve_limit,select.mode', offered().join());
  await closeModal();
  panel._openEntityPicker('n1', 'r1', 'a1', 'target');
  await sleep(40);
  check('opened from the canvas, OUT\'s browser is the same', panel._ep.out === true && JSON.stringify(panel._ep.domains) === '["input_number","number","counter","input_text","text"]');
  await closeModal();

  // ---- a pin of a list from the canvas: the browser and a variable dropped
  panel._openEntityPicker('n1', 'r4', 'd1', 'inputs.0');
  await sleep(40);
  check('the browser opened from a pin of a MUX offers what that input takes', panel._ep.kind === 'word' && offered().join() === 'input_select.colour,input_text.note');
  await closeModal();
  check('a variable dropped on a MUX input is that input', panel._applyDroppedVar('input_text.note', 'n1', 'r4', 'd1', 'inputs.0')
        && JSON.stringify(el('r4', 'd1').inputs) === '["input_text.note","input_select.colour"]' && el('r4', 'd1')['inputs.0'] === undefined);

  // ---- opening the Inspector changes nothing
  const ids = [['r1', 'a1'], ['r2', 'b1'], ['r3', 'c1'], ['r4', 'd1'], ['r5', 'e1']];
  const changed = [];
  for (const [rid, id] of ids) {
    const was = JSON.stringify(el(rid, id));
    await inspect(rid, id);
    if (JSON.stringify(el(rid, id)) !== was) changed.push(id);
  }
  check('opening the Inspector on them changes nothing', changed.length === 0, changed.join());

  // ---- the screen
  el('r1', 'a1').more = ['1', 'counter.step'];
  body = await inspect('r1', 'a1');
  const side = body.closest('.sidebar, .inspector, aside') || body;
  check(`on a ${size} the IN fields fit, no sideways scroll`, body.scrollWidth <= body.clientWidth + 1 && side.scrollWidth <= side.clientWidth + 1,
        `${body.scrollWidth} > ${body.clientWidth}`);
  const btn = body.querySelector('.in-field .in-pick').getBoundingClientRect();
  const del = body.querySelector('.in-field .in-del').getBoundingClientRect();
  check('Variable and − are targets to hit', btn.height >= 36 && del.width >= 36 && del.height >= 36, `${btn.height} ${del.width}x${del.height}`);
  modal = await openVar('sourceA');
  const box = sr.querySelector('.ep-modal').getBoundingClientRect();
  check(`on a ${size} the browser is on the screen`, box.left >= 0 && box.right <= window.innerWidth + 0.5 && box.top >= 0, JSON.stringify(box));
  await closeModal();
  panel._markSaved && panel._markSaved();
  panel.remove();
}
