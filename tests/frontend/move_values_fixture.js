// LIBI for Home Assistant - Copyright (C) 2026 Guy Azria - GPL-3.0-or-later
// Shared by test_panel_move_values*.html.
// [ADDED v1.0.0 | 2026-11-17] Purpose: the user (2026-11-17) - "dimming with MOVE and through a variable; a colour for an
//   LED strip - do I get a palette?". A MOVE to a light says what it sets and shows its colour on the block; the
//   Inspector sets it with a slider, a palette and swatches, or a variable (Value from a variable), and says why a MOVE
//   is red (a switch takes no value; a word is no brightness), which SAVE refuses. A MOVE of 0 is a value. A scene's
//   colour has the palette too, but no variable. Run against the real panel, with canned answers.
// [CHANGED v1.0.1 | 2026-11-18] Purpose: the review of the release (RULE 41) - a value read from Home Assistant that
//   is the words of an entity id (literal) is a value, not a variable; a variable chosen for it is one again.

const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const until = async (cond, ms = 3000) => { const end = Date.now() + ms; while (!cond() && Date.now() < end) await sleep(10); return cond(); };

const MOVE = (id, source, target, valueKey) => ({ id, type: 'move', mode: 'value', source, target, ...(valueKey ? { valueKey } : {}) });
const START = (id) => ({ id, type: 'contact_no', isTrigger: true, label: 'binary_sensor.motion' });

const NETS = () => [
  { id: 'n1', name: 'Lights', level: 'automation', collapsed: false, links: [], rungs: [
    { id: 'r1', comment: '', elements: [START('e1'), MOVE('e2', '50', 'light.kitchen'), MOVE('e3', '[255, 136, 0]', 'light.led', 'rgb_color'),
      MOVE('e4', 'input_number.dim', 'light.kitchen')] },
    { id: 'r2', comment: '', elements: [START('e5'), MOVE('e6', '5', 'switch.pump'), MOVE('e7', 0, 'cover.blind'), MOVE('e8', 'bright', 'light.kitchen')] },
    { id: 'r3', comment: '', elements: [START('e9'), MOVE('e10', '1', 'input_number.a'),
      MOVE('e11', '<img src=x onerror="window.__xss=1">', 'input_text.note')] }] },
  { id: 'n2', name: 'Movie', level: 'scene', collapsed: false, links: [], rungs: [
    { id: 's0', comment: '', elements: [MOVE('s1', '[255, 180, 120]', 'light.sofa', 'rgb_color'), MOVE('s2', 80, 'light.sofa', 'brightness'),
      MOVE('s3', 'mode.night', 'input_text.mode'), MOVE('s4', 'heat', 'climate.ac')] }] },
];

function makeHass() {
  const hass = {
    // [CHANGED 2026-11-18] The helpers a variable is chosen from in the entity browser (the IN field).
    states: {
      'input_text.led_color': { entity_id: 'input_text.led_color', state: '#ff8800', attributes: { friendly_name: 'LED color' } },
      'input_number.dim': { entity_id: 'input_number.dim', state: '40.0', attributes: { friendly_name: 'Dim' } },
      'input_select.mode': { entity_id: 'input_select.mode', state: 'day', attributes: { friendly_name: 'Mode', options: ['day', 'night'] } },
      'input_boolean.away': { entity_id: 'input_boolean.away', state: 'off', attributes: { friendly_name: 'Away' } },
    },
    entities: {}, devices: {}, areas: {}, themes: { darkMode: false }, language: 'en',
    user: { is_admin: true }, localize: (k) => k, callService: async () => {}, callApi: async () => ({ result: 'ok' }),
    connection: {
      sendMessagePromise: async (m) => {
        if (m.type === 'libi/ai_status') return { configured: false };
        if (m.type === 'libi/project_list') return { projects: [{ slug: 'p', name: 'Home', nets: 2, revision: 1 }] };
        if (m.type === 'libi/project_open') return { slug: 'p', name: 'Home', revision: 1, stats: {}, versions: {}, nets: NETS() };
        return [];
      },
      subscribeEvents: async () => () => {}, subscribeMessage: async () => () => {},
    },
  };
  return hass;
}

export async function moveValueChecks(check, { phone = false } = {}) {
  window.alert = () => {};
  window.confirm = () => false;
  window.prompt = () => null;
  if (!customElements.get('ha-entity-picker')) customElements.define('ha-entity-picker', class extends HTMLElement {});
  localStorage.clear();
  const panel = document.createElement('libi-panel');
  panel.style.height = '800px';
  document.body.appendChild(panel);
  panel.hass = makeHass();
  await until(() => panel._initialized && panel._project && panel.core.nets.length === 2);
  await sleep(80);
  const sr = panel.shadowRoot;
  const core = panel.core;
  const el = (netId, rungId, id) => core.findEl(netId, rungId, id);
  const block = (id) => sr.querySelector(`.libi-el[data-eid="${id}"]`);
  const inspect = async (netId, rungId, id) => {
    panel._inspectedEl = { netId, rungId, elId: id };
    panel._wakeSidebar();
    panel._render();
    await sleep(30);
    return sr.querySelector('#inspectorBody');
  };
  const fire = async (node, type) => { node.dispatchEvent(new Event(type, { bubbles: true })); await sleep(30); };

  // ---- on the blocks
  const swatch = block('e3') && block('e3').querySelector('.pin-swatch');
  check('a colour shows its colour on the block', !!swatch && getComputedStyle(swatch).backgroundColor === 'rgb(255, 136, 0)',
        swatch && getComputedStyle(swatch).backgroundColor);
  const key = (id) => ((block(id) || document.body).querySelector('.move-key') || {}).textContent || '';
  check('what a MOVE sets on a light is written under it', key('e2') === 'Brightness (%)' && key('e3') === 'Color' && key('e4') === 'Brightness (%)',
        [key('e2'), key('e3'), key('e4')].join('|'));
  check('a MOVE to a helper needs no such line', key('e10') === '' && !block('e10').classList.contains('has-error'));
  check('a MOVE to a switch is red', block('e6').classList.contains('has-error'));
  check('a word for a brightness is red', block('e8').classList.contains('has-error'));
  const zero = block('e7');
  check('a MOVE of 0 is a value: not red, and it shows 0', !zero.classList.contains('has-error')
        && [...zero.querySelectorAll('.pin-val')].map(p => p.textContent.trim())[0] === '0');
  check('the blocks are drawn with no script in them', !sr.querySelector('.libi-el img') && window.__xss === undefined);
  const refused = await panel._saveProject();
  check('SAVE is refused while a MOVE is red', !!refused && refused.refused === true, JSON.stringify(refused));

  // ---- why it is red
  let body = await inspect('n1', 'r2', 'e6');
  check('the Inspector says why a MOVE to a switch is red', /A switch has no value a MOVE can set/.test((body.querySelector('.move-why') || {}).textContent || ''));
  body = await inspect('n1', 'r2', 'e8');
  check('and why a word is no brightness', ((body.querySelector('.move-why') || {}).textContent || '') === 'Brightness (%) takes a number.');

  // ---- opening the Inspector changes nothing
  const ids = [['n1', 'r1', 'e2'], ['n1', 'r1', 'e3'], ['n1', 'r1', 'e4'], ['n1', 'r2', 'e7'], ['n1', 'r3', 'e10'], ['n2', 's0', 's1'], ['n2', 's0', 's2'],
               ['n2', 's0', 's3'], ['n2', 's0', 's4']];
  let changed = [];
  for (const [n, r, id] of ids) {
    const before = JSON.stringify(el(n, r, id));
    await inspect(n, r, id);
    if (JSON.stringify(el(n, r, id)) !== before) changed.push(id);
  }
  check('opening the Inspector on a MOVE changes nothing', changed.length === 0, changed.join());

  // ---- dimming: what it sets, and a slider
  body = await inspect('n1', 'r1', 'e2');
  const setSel = body.querySelector('#propMoveKey');
  const offered = setSel ? [...setSel.options].map(o => o.textContent) : [];
  check('a light offers what a MOVE can set on it', offered.join('|') === 'Brightness (%)|Brightness (0-255)|Dim up or down by (%)|Color temperature (K)|Color|Color by name|Effect'
        && setSel.value === 'brightness_pct', offered.join('|'));
  const range = body.querySelector('#inp_moveRange');
  check('a brightness is a slider from 0 to 100, at its value', !!range && range.min === '0' && range.max === '100' && range.value === '50'
        && body.querySelector('#inp_moveNum').value === '50');
  range.value = '30';
  await fire(range, 'change');
  check('moving the slider sets the value', el('n1', 'r1', 'e2').source === '30' && el('n1', 'r1', 'e2').valueKey === undefined);
  body = sr.querySelector('#inspectorBody');
  const num = body.querySelector('#inp_moveNum');
  num.value = '75';
  await fire(num, 'change');
  check('so does typing it', el('n1', 'r1', 'e2').source === '75');

  // ---- a colour: the palette and the swatches
  body = sr.querySelector('#inspectorBody');
  const sel = body.querySelector('#propMoveKey');
  sel.value = 'rgb_color';
  await fire(sel, 'change');
  check('Color is set; 75 is no colour, so it is cleared', el('n1', 'r1', 'e2').valueKey === 'rgb_color' && el('n1', 'r1', 'e2').source === '');
  body = sr.querySelector('#inspectorBody');
  const palette = body.querySelector('input[type="color"]#inp_color');
  const swatches = [...body.querySelectorAll('.move-color .swatch')];
  check('a colour is picked from a palette, with swatches beside it', !!palette && swatches.length === 10
        && swatches.map(s => s.title).join(',') === 'Warm white,White,Red,Orange,Yellow,Green,Cyan,Blue,Purple,Pink');
  check('no colour yet: the block is red until one is picked', block('e2').classList.contains('has-error'));
  swatches[2].click();
  await sleep(30);
  check('a swatch sets its colour', el('n1', 'r1', 'e2').source === '[255, 0, 0]' && !block('e2').classList.contains('has-error'));
  body = sr.querySelector('#inspectorBody');
  check('and is marked as the one chosen', (body.querySelector('.move-color .swatch.on') || {}).title === 'Red');
  const pal = body.querySelector('#inp_color');
  pal.value = '#00ff00';
  await fire(pal, 'change');
  check('the palette sets the colour it picks', el('n1', 'r1', 'e2').source === '[0, 255, 0]'
        && getComputedStyle(block('e2').querySelector('.pin-swatch')).backgroundColor === 'rgb(0, 255, 0)');

  // ---- a variable
  body = sr.querySelector('#inspectorBody');
  const varPick = body.querySelector('#moveVarPick');
  check('or the value of a variable', !!varPick && /Or the value of a variable/.test(body.textContent));
  varPick.click();
  await sleep(40);
  const varOffered = [...sr.querySelectorAll('.ep-modal .ep-pick')].map(r => r.dataset.eid);
  check('the browser offers the kinds that hold a colour, never on or off', JSON.stringify(panel._ep.domains) === '["input_text","text","light"]'
        && varOffered.join() === 'input_text.led_color', varOffered.join());
  sr.querySelector('.ep-modal .ep-pick[data-eid="input_text.led_color"]').click();
  await sleep(40);
  check('a variable picked is the value', el('n1', 'r1', 'e2').source === 'input_text.led_color');
  body = sr.querySelector('#inspectorBody');
  check('it is shown as the variable, with the way back to a fixed value', /Value from a variable/.test(body.textContent)
        && !!body.querySelector('#moveFixed') && !body.querySelector('#inp_color') && (body.querySelector('#inp_source .in-eid') || {}).textContent === 'input_text.led_color');
  check('the dashboard note says what a variable is there', /an input_number is a slider there/.test((body.querySelector('.move-vars') || {}).textContent || ''));
  body.querySelector('#moveFixed').click();
  await sleep(30);
  check('a fixed value again', el('n1', 'r1', 'e2').source === '' && !!sr.querySelector('#inspectorBody #inp_color'));
  body = await inspect('n1', 'r1', 'e4');
  check('a helper on IN is a variable: no slider over it', !body.querySelector('#inp_moveRange') && /Value from a variable/.test(body.textContent));
  body.querySelector('#inp_source').closest('.in-field').querySelector('.in-pick').click();
  await sleep(40);
  check('its browser offers what holds a number', JSON.stringify(panel._ep.domains) === '["input_number","number","sensor","light"]'
        && [...sr.querySelectorAll('.ep-modal .ep-pick')].map(r => r.dataset.eid).join() === 'input_number.dim');
  panel._modal = null; panel._ep = null; panel._render(); await sleep(20);

  // ---- a helper, and a scene
  body = await inspect('n1', 'r3', 'e10');
  check('a helper: no Set, its value or a template as before, and a variable', !body.querySelector('#propMoveKey') && !!body.querySelector('textarea#inp_source')
        && !!body.querySelector('#moveVarPick'));
  body = await inspect('n1', 'r3', 'e11');
  check('a value with markup is text in the Inspector', (body.querySelector('textarea#inp_source') || {}).value === '<img src=x onerror="window.__xss=1">'
        && !sr.querySelector('#inspectorBody img') && window.__xss === undefined);
  body = await inspect('n2', 's0', 's1');
  check('a scene\'s colour has the palette', !!body.querySelector('#inp_color') && (body.querySelector('.move-color .color-text') || {}).textContent === '[255, 180, 120]');
  check('but no variable and no Set: a scene reads no template', !body.querySelector('#moveVarPick') && !body.querySelector('#inp_source.in-var') && !body.querySelector('#propMoveKey'));
  // [ADDED 2026-11-18] OUT is chosen as an IN is; in a scene it is any entity - a scene sets the state of anything.
  body.querySelector('#inp_target').closest('.in-field').querySelector('.in-pick').click();
  await sleep(40);
  check('the OUT of a scene is chosen from any entity', !!panel._ep && !panel._ep.domains && !panel._ep.kind && panel._ep.prop === 'target');
  panel._modal = null; panel._ep = null; panel._render(); await sleep(20);
  body = await inspect('n2', 's0', 's1');
  body = await inspect('n2', 's0', 's2');
  const sceneRange = body.querySelector('#inp_moveRange');
  check('a scene\'s brightness is a slider from 0 to 255', !!sceneRange && sceneRange.max === '255' && sceneRange.value === '80');
  check('in a scene a MOVE sets a state: heat for a thermostat is not red', !block('s4').classList.contains('has-error'));
  body = await inspect('n2', 's0', 's3');
  check('in a scene a value that looks like an entity is that value, not a variable', !body.querySelector('#moveVarPick') && !body.querySelector('#inp_source.in-var')
        && !/Value from a variable/.test(body.textContent) && (body.querySelector('textarea#inp_source') || {}).value === 'mode.night');

  // ---- [ADDED 2026-11-18] The review of the release: a value read from Home Assistant that is the words of an entity id
  // (literal) - a speaker's name given to a text helper - is that value, not the variable; a variable chosen is one again.
  Object.assign(el('n1', 'r3', 'e10'), { source: 'media_player.living_room', literal: true });
  body = await inspect('n1', 'r3', 'e10');
  check('the words of an entity id read from Home Assistant are a value, not a variable', !/Value from a variable/.test(body.textContent)
        && (body.querySelector('textarea#inp_source') || {}).value === 'media_player.living_room' && !body.querySelector('#inp_source .in-eid'),
        body.textContent.slice(0, 160));
  body.querySelector('#moveVarPick').click();
  await sleep(40);
  const dim = sr.querySelector('.ep-modal .ep-pick[data-eid="input_number.dim"]');
  if (dim) dim.click();
  await sleep(40);
  check('a variable chosen for it is a variable again', !!dim && el('n1', 'r3', 'e10').source === 'input_number.dim'
        && !('literal' in el('n1', 'r3', 'e10')) && /Value from a variable/.test(sr.querySelector('#inspectorBody').textContent),
        JSON.stringify(el('n1', 'r3', 'e10')));
  Object.assign(el('n1', 'r3', 'e10'), { source: '1' });

  // ---- the screen
  body = await inspect('n1', 'r1', 'e3');
  const side = body.closest('.sidebar, .inspector, aside') || body;
  check(phone ? 'on a phone the palette and the swatches fit, no sideways scroll' : 'the palette and the swatches fit the Inspector',
        body.scrollWidth <= body.clientWidth + 1 && side.scrollWidth <= side.clientWidth + 1, `${body.scrollWidth} > ${body.clientWidth}`);
  const sw = body.querySelector('.move-color .swatch').getBoundingClientRect();
  check('a swatch is a target a finger can hit', sw.width >= 30 && sw.height >= 30, `${sw.width}x${sw.height}`);
  panel._markSaved && panel._markSaved();
  panel.remove();
}
