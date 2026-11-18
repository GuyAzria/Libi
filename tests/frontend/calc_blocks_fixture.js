// LIBI for Home Assistant - Copyright (C) 2026 Guy Azria - GPL-3.0-or-later
// Shared by test_panel_calc_blocks*.html.
// [ADDED v1.0.0 | 2026-11-18] Purpose: the user (2026-11-18) - "RAND, a random whole number between IN1 and IN2; MOD, the
//   remainder; MUX, input number K - under Math, with ADD, SUB and DIV; min and max may be variables, and the value goes
//   into a variable". The + menu's Math group has them by name; a RAND is placed with its range, each pin a number or
//   a variable, OUT a number helper, and "never the one OUT holds"; a MUX has its inputs - colors with a swatch - and
//   sets a light as a MOVE does. What cannot compile is red and says why, and SAVE is refused. Real panel, canned
//   answers. EVERY, a time pattern, is a block of its own - how often, edited as a number and a unit; it was a CMP shown as
//   a fixed time, and opening it turned it into one.
// [CHANGED v1.0.1 | 2026-11-18] Purpose: the review of the release (RULE 41) - RAND of a fraction, RAND of one number
//   never the one OUT holds, and a MUX's K a fraction are red, and the Inspector says why.

const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const until = async (cond, ms = 3000) => { const end = Date.now() + ms; while (!cond() && Date.now() < end) await sleep(10); return cond(); };

const START = (id) => ({ id, type: 'contact_no', isTrigger: true, label: 'binary_sensor.motion' });
const NETS = () => [{ id: 'n1', name: 'Colours', level: 'automation', collapsed: false, links: [], rungs: [
  { id: 'r1', comment: '', elements: [START('a0'), { id: 'a1', type: 'math_rand', sourceA: '0', sourceB: '9', target: 'counter.index', notSame: true },
    { id: 'a2', type: 'mux', sourceA: 'counter.index', inputs: ['red', 'lime', 'input_select.colour_3', '"><img src=x onerror="window.__xss=1"><b>x</b>'], target: 'light.strip', valueKey: 'color_name' }] },
  { id: 'r2', comment: '', elements: [START('b0'), { id: 'b1', type: 'ctu', source: 'counter.step', value: '1' },
    { id: 'b2', type: 'math_mod', sourceA: 'counter.step', sourceB: '4', target: 'counter.step' }] },
  { id: 'r3', comment: '', elements: [START('c0'), { id: 'c1', type: 'math_rand', sourceA: '9', sourceB: '0', target: 'counter.index' },
    { id: 'c2', type: 'math_mod', sourceA: 'counter.step', sourceB: '0', target: 'counter.step' },
    { id: 'c3', type: 'math_rand', sourceA: '0', sourceB: '9', target: 'light.strip' }] },
  { id: 'r4', comment: '', elements: [START('d0'), { id: 'd1', type: 'mux', sourceA: '5', inputs: ['red', 'blue'], target: 'light.strip' },
    { id: 'd2', type: 'mux', sourceA: '0', inputs: ['red'], target: 'input_select.mode' },
    { id: 'd3', type: 'mux', sourceA: '0', inputs: ['10', '20'], target: 'switch.pump' }] },
  { id: 'r5', comment: '', elements: [{ id: 'p1', type: 'cmp_eq', sourceA: 'time pattern', sourceB: 'seconds=/10', isTrigger: true,
      raw: { trigger: 'time_pattern', seconds: '/10', id: 'tick' }, src: 'triggers[0]' }, { id: 'p2', type: 'coil', label: 'light.strip' }] },
  { id: 'r6', comment: '', elements: [{ id: 'q1', type: 'cmp_eq', sourceA: 'time pattern', sourceB: 'seconds=/60', isTrigger: true },
    { id: 'q2', type: 'coil', label: 'light.strip' }] },
  { id: 'r7', comment: '', elements: [START('s0'), { id: 's1', type: 'cmp_eq', sourceA: 'time pattern', sourceB: 'minutes=/5' },
    { id: 's2', type: 'coil', label: 'light.strip' }] }] }];

const STATES = {
  'light.strip': { entity_id: 'light.strip', state: 'on', attributes: { friendly_name: 'Strip', supported_color_modes: ['color_temp', 'xy'], supported_features: 40 } },
  'counter.index': { entity_id: 'counter.index', state: '3', attributes: { friendly_name: 'Index' } },
  'counter.step': { entity_id: 'counter.step', state: '0', attributes: { friendly_name: 'Step' } },
  'input_select.colour_3': { entity_id: 'input_select.colour_3', state: 'blue', attributes: { friendly_name: 'Colour 3', options: ['red', 'blue'] } },
  'input_number.low': { entity_id: 'input_number.low', state: '2.0', attributes: { friendly_name: 'Low', min: 0, max: 10 } },
};

export async function calcBlockChecks(check, { size = 'desktop' } = {}) {
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
  const core = panel.core;
  const el = (rid, id) => core.findEl('n1', rid, id);
  const block = (id) => sr.querySelector(`.libi-el[data-eid="${id}"]`);
  const red = (id) => !!block(id) && block(id).classList.contains('has-error');
  const inspect = async (rid, id) => {
    panel._inspectedEl = { netId: 'n1', rungId: rid, elId: id };
    panel._wakeSidebar();
    panel._render();
    await sleep(30);
    return sr.querySelector('#inspectorBody');
  };
  const fire = async (node, type) => { node.dispatchEvent(new Event(type, { bubbles: true })); await sleep(30); };
  const text = (root, sel) => ((root && root.querySelector(sel)) || {}).textContent || '';
  const pins = (id) => [...block(id).querySelectorAll('.plc-row .pin-lbl')].map(p => p.textContent.trim()).filter(Boolean);

  // ---- the + menu
  const dot = sr.querySelector('.wire-ins[data-nid="n1"][data-rid="r1"]');
  const r = dot.getBoundingClientRect();
  panel._floatingMenu = { type: 'dot', netId: 'n1', rungId: 'r1', path: dot.getAttribute('data-path'), x: r.left + r.width / 2, y: window.innerHeight / 2, bottom: window.innerHeight / 2 + r.height };
  panel._render();
  await sleep(30);
  sr.querySelector('#fmBox .pal-cat[data-val="math"]').click();
  await sleep(30);
  const box = sr.querySelector('#fmBox');
  const vals = [...box.querySelectorAll('.pal-item[data-action="add"]')].map(b => b.dataset.val);
  check('the Math category has ADD, SUB, MUL, DIV, MOD, RAND and MUX', vals.join() === 'math_add,math_sub,math_mul,math_div,math_mod,math_rand,mux', vals.join());
  const rand = box.querySelector('.pal-item[data-val="math_rand"]');
  check('RAND says what it is', !!rand && rand.title === 'RAND - a random whole number from IN1 to IN2', rand && rand.title);
  const fmBox = box.getBoundingClientRect();
  check(`on a ${size} the menu is on the screen`, fmBox.top >= 0 && fmBox.bottom <= window.innerHeight + 0.5 && fmBox.right <= window.innerWidth + 0.5);
  const before = core.nets[0].rungs[0].elements.length;
  rand.click();
  await sleep(40);
  const added = core.nets[0].rungs[0].elements.find(e => e.type === 'math_rand' && e.id !== 'a1');
  check('a RAND is placed with a range, 0 to 9, and an OUT to pick', !!added && added.sourceA === '0' && added.sourceB === '9' && added.target === ''
        && core.nets[0].rungs[0].elements.length === before + 1, JSON.stringify(added));
  if (added) { core.nets[0].rungs[0].elements = core.nets[0].rungs[0].elements.filter(e => e !== added); panel._render(); await sleep(30); }

  // ---- on the blocks
  check('a RAND shows MIN, MAX and OUT, and its tick', text(block('a1'), '.plc-header') === 'RAND' && pins('a1').join() === 'MIN,OUT,MAX'
        && text(block('a1'), '.calc-tag') === 'never the one OUT holds', pins('a1').join());
  check('a MOD is MATH MOD', text(block('b2'), '.plc-header') === 'MATH MOD' && !red('b2'));
  check('a MUX shows K, OUT and a row for each input, with what it sets', text(block('a2'), '.plc-header') === 'MUX'
        && pins('a2').join() === 'K,OUT,IN0,IN1,IN2,IN3' && text(block('a2'), '.move-key') === 'Color by name', pins('a2').join());
  const sw = [...block('a2').querySelectorAll('.pin-swatch')].map(s => getComputedStyle(s).backgroundColor);
  check('a color by name shows its color', sw[0] === 'rgb(255, 0, 0)' && sw[1] === 'rgb(0, 255, 0)', sw.join());
  check('an input with markup is text', !block('a2').querySelector('.pin-val b') && window.__xss === undefined);
  check('blocks that can compile are not red', !red('a1') && !red('a2') && !red('b1'));
  check('RAND from 9 to 0 is red', red('c1'));
  check('MOD of 0 is red', red('c2'));
  check('RAND into a light is red', red('c3'));
  check('MUX with K 5 of two inputs is red', red('d1'));
  check('MUX of one input is red', red('d2'));
  check('MUX into a switch is red', red('d3'));
  const refused = await panel._saveProject();
  check('SAVE is refused while one is red', !!refused && refused.refused === true, JSON.stringify(refused));

  // ---- opening the Inspector changes nothing
  const ids = [['r1', 'a1'], ['r1', 'a2'], ['r2', 'b2'], ['r3', 'c1'], ['r4', 'd2'], ['r5', 'p1'], ['r6', 'q1']];
  const changed = [];
  for (const [rid, id] of ids) {
    const was = JSON.stringify(el(rid, id));
    await inspect(rid, id);
    if (JSON.stringify(el(rid, id)) !== was) changed.push(id);
  }
  check('opening the Inspector on them changes nothing', changed.length === 0, changed.join());

  // ---- RAND in the Inspector: each pin a value typed or a variable (the IN field), OUT a number helper
  const pick = async (fieldId, entityId) => {
    sr.querySelector(`#inspectorBody #inp_${fieldId}`).closest('.in-field').querySelector('.in-pick').click();
    await sleep(40);
    const row = sr.querySelector(`.ep-modal .ep-pick[data-eid="${entityId}"]`);
    if (row) row.click();
    await sleep(40);
    return row;
  };
  let body = await inspect('r1', 'a1');
  const labels = [...body.querySelectorAll('label')].map(l => l.textContent.trim());
  check('RAND: smallest and largest, each a value or a variable, and OUT', labels.includes('Smallest (IN1)') && labels.includes('Largest (IN2)')
        && body.querySelectorAll('.in-field .in-pick').length === 3 && labels.includes('Into the variable (OUT)'), labels.join('|'));
  // [CHANGED 2026-11-18] OUT is chosen as an IN is: the browser offers what can take the number - never a light, a list.
  body.querySelector('#inp_target').closest('.in-field').querySelector('.in-pick').click();
  await sleep(40);
  panel._epQuery = '.'; panel._render(); await sleep(30);
  const outs = [...sr.querySelectorAll('.ep-modal .ep-pick')].map(r => r.dataset.eid).sort();
  check('OUT offers the number helpers', panel._ep.out === true && JSON.stringify(panel._ep.domains) === '["input_number","number","counter","input_text","text"]'
        && outs.join() === 'counter.index,counter.step,input_number.low', outs.join());
  panel._modal = null; panel._ep = null; panel._epQuery = ''; panel._render(); await sleep(20);
  body = sr.querySelector('#inspectorBody');
  const max = body.querySelector('#inp_sourceB');
  max.value = ' 5 ';
  await fire(max, 'change');
  check('typing a number sets it, as a number', el('r1', 'a1').sourceB === '5', JSON.stringify(el('r1', 'a1').sourceB));
  const picked = await pick('sourceA', 'input_number.low');
  check('a variable picked in the browser is IN1', !!picked && el('r1', 'a1').sourceA === 'input_number.low' && pins('a1').length === 3);
  body = sr.querySelector('#inspectorBody');
  check('the variable shows by its name, its id and its value now', text(body, '#inp_sourceA b') === 'Low' && text(body, '#inp_sourceA .in-eid') === 'input_number.low'
        && text(body, '#inp_sourceA .in-now') === '2.0', text(body, '#inp_sourceA'));
  const tick = body.querySelector('#inp_notSame');
  tick.checked = false;
  await fire(tick, 'change');
  check('the tick off: the block no longer says it', el('r1', 'a1').notSame === false && !block('a1').querySelector('.calc-tag'));
  body = await inspect('r3', 'c1');
  check('and why it is red', /IN1 is the smallest number and IN2 the largest: 9 is more than 0/.test(text(body, '.calc-why')), text(body, '.calc-why'));
  body = await inspect('r3', 'c3');
  check('RAND into a light: why', /OUT is an input_number, a counter or a number/.test(text(body, '.calc-why')), text(body, '.calc-why'));
  check('RAND takes two inputs: no button to add one', !body.querySelector('#inAdd'));

  // ---- MUX in the Inspector: K and an IN field for each input
  body = await inspect('r1', 'a2');
  const rows = [...body.querySelectorAll('.in-field')].map(f => (f.querySelector('input') || {}).value || (f.querySelector('.in-eid') || {}).textContent || '');
  check('MUX: K, then a field for each input, as it holds it', rows.slice(0, 5).join('|') === 'counter.index|red|lime|input_select.colour_3|"><img src=x onerror="window.__xss=1"><b>x</b>', rows.join('|'));
  check('an input with a quote and markup stays text in the Inspector', !body.querySelector('.in-field img') && window.__xss === undefined);
  check('the colors are offered by name', body.querySelectorAll('#libiMuxColors option').length >= 10 && body.querySelector('#inp_inputs1').getAttribute('list') === 'libiMuxColors');
  check('what it sets on the light: Color by name', body.querySelector('#propMuxKey').value === 'color_name');
  body.querySelector('#inp_inputs3').closest('.in-field').querySelector('.in-del').click();
  await sleep(30);
  check('an input is removed', JSON.stringify(el('r1', 'a2').inputs) === '["red","lime","input_select.colour_3"]');
  sr.querySelector('#inspectorBody #inAdd').click();
  await sleep(30);
  check('an input is added, empty - and the block is red until it has a value', el('r1', 'a2').inputs.length === 4 && red('a2'));
  body = sr.querySelector('#inspectorBody');
  const last = body.querySelector('#inp_inputs3');
  last.value = 'orange';
  await fire(last, 'change');
  check('typed, it is the value', el('r1', 'a2').inputs[3] === 'orange' && !red('a2'));
  await pick('inputs0', 'input_select.colour_3');
  check('a variable picked for an input is that input', el('r1', 'a2').inputs[0] === 'input_select.colour_3' && el('r1', 'a2').input0 === undefined,
        JSON.stringify(el('r1', 'a2')));
  body = await inspect('r4', 'd1');
  check('MUX with K out of range: why', text(body, '.calc-why') === 'K is 5, and the inputs are 0 to 1.', text(body, '.calc-why'));
  body = await inspect('r4', 'd3');
  check('MUX into a switch: why', /A switch has no value a MUX can set/.test(text(body, '.calc-why')), text(body, '.calc-why'));

  // ---- [ADDED 2026-11-18] The review of the release: what Home Assistant would refuse only when it runs is red, as
  // the compiler refuses it (libi_to_yaml._math_action, _mux_action). Each block is put back as it was after.
  el('r4', 'd1').sourceA = '1.5';
  body = await inspect('r4', 'd1');
  check('MUX with K a fraction: red, and why', red('d1') && text(body, '.calc-why') === 'K is the number of an input, a whole number: not 1.5.',
        text(body, '.calc-why'));
  el('r4', 'd1').sourceA = '5';
  const randBlock = el('r3', 'c1');
  Object.assign(randBlock, { sourceA: '0.5', sourceB: '9' });
  body = await inspect('r3', 'c1');
  check('RAND of a fraction: red, and why', red('c1') && text(body, '.calc-why') === 'RAND gives whole numbers: 0.5 is no whole number.',
        text(body, '.calc-why'));
  Object.assign(randBlock, { sourceA: '3', sourceB: '3', notSame: true });
  body = await inspect('r3', 'c1');
  check('RAND of one number, never the one OUT holds: red, and why', red('c1')
        && /^From 3 to 3 there is one number: never the one OUT holds leaves none\./.test(text(body, '.calc-why')), text(body, '.calc-why'));
  randBlock.notSame = false;
  body = await inspect('r3', 'c1');
  check('the same without the tick is always 3: not red', !red('c1') && !body.querySelector('.calc-why'), text(body, '.calc-why'));
  Object.assign(randBlock, { sourceA: '9', sourceB: '0' });
  delete randBlock.notSame;

  // ---- EVERY, a time pattern
  check('EVERY is a block of its own: how often on one pin', text(block('p1'), '.plc-header') === 'EVERY' && pins('p1').join() === 'PT'
        && text(block('p1'), '.pin-val') === '10 s' && !red('p1'), text(block('p1'), '.pin-val'));
  check('seconds=/60 never comes: red', red('q1'));
  check('an EVERY that is no trigger is red', red('s1'));
  body = await inspect('r5', 'p1');
  check('the Inspector says every 10 seconds', body.querySelector('#inp_everyN').value === '10' && body.querySelector('#inp_everyUnit').value === 'seconds'
        && body.querySelector('#propCmpKind').value === 'pattern' && !/Fixed time/.test(body.textContent));
  const everyN = body.querySelector('#inp_everyN');
  everyN.value = '5';
  await fire(everyN, 'change');
  check('5 is every 5 seconds', el('r5', 'p1').sourceB === 'seconds=/5' && text(block('p1'), '.pin-val') === '5 s');
  body = sr.querySelector('#inspectorBody');
  const unit = body.querySelector('#inp_everyUnit');
  unit.value = 'minutes';
  await fire(unit, 'change');
  check('minutes: every 5 minutes', el('r5', 'p1').sourceB === 'minutes=/5' && text(block('p1'), '.pin-val') === '5 min');
  body = await inspect('r6', 'q1');
  check('why seconds=/60 is red', text(body, '.pattern-why') === 'seconds go up to 59: /60 never comes.', text(body, '.pattern-why'));
  body = await inspect('r7', 's1');
  check('why an EVERY that is no trigger is red', text(body, '.pattern-why') === 'EVERY starts the rung: tick Use as Trigger.', text(body, '.pattern-why'));

  // ---- the screen
  for (const [rid, id] of [['r1', 'a1'], ['r1', 'a2']]) {
    body = await inspect(rid, id);
    const side = body.closest('.sidebar, .inspector, aside') || body;
    check(`on a ${size} the Inspector of ${id} has no sideways scroll`, body.scrollWidth <= body.clientWidth + 1 && side.scrollWidth <= side.clientWidth + 1,
          `${body.scrollWidth} > ${body.clientWidth}`);
  }
  const del = sr.querySelector('#inspectorBody .in-del').getBoundingClientRect();
  check('the remove button is a target to hit', del.width >= 32 && del.height >= 32, `${del.width}x${del.height}`);
  panel._markSaved && panel._markSaved();
  panel.remove();
}
