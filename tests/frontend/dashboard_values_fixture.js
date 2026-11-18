// LIBI for Home Assistant - Copyright (C) 2026 Guy Azria - GPL-3.0-or-later
// Shared by test_panel_dashboard_values*.html.
// [ADDED v1.0.0 | 2026-11-17] Purpose: the user (2026-11-17) - "how can you check that a device that has this works, and
//   that I can control the colour from the dashboard?". A contact drawn on a dashboard helper (an input_number, a list,
//   a text) waits for on or off, which a value never is: red, and the Inspector says to make it a P contact, which
//   starts the rung the moment the value changes. A list with on among its options may be on: not red; nor a check read
//   from Home Assistant, which is saved as it was. A MOVE says what the light does with the value: the house's wall
//   switches only turn on and off, its floodlights only dim. Run against the real panel, with canned answers.
// [CHANGED v1.0.1 | 2026-11-18] Purpose: the review of the release (RULE 41) - a P contact on a list that may be on
//   says it starts on any change, off too, and that a CMP = on waits for the moment it turns on.

const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const until = async (cond, ms = 3000) => { const end = Date.now() + ms; while (!cond() && Date.now() < end) await sleep(10); return cond(); };

const WHEN = (id, type, label, extra = {}) => ({ id, type, label, isTrigger: true, ...extra });
const MOVE = (id, source, target, valueKey) => ({ id, type: 'move', mode: 'value', source, target, ...(valueKey ? { valueKey } : {}) });
const COIL = (id, label) => ({ id, type: 'coil', label });

const NETS = () => [
  { id: 'n1', name: 'Dashboard', level: 'automation', collapsed: false, links: [], rungs: [
    { id: 'r1', comment: '', elements: [WHEN('a1', 'contact_p', 'input_select.strip_color'), MOVE('a2', 'input_select.strip_color', 'light.strip', 'color_name')] },
    { id: 'r2', comment: '', elements: [WHEN('b1', 'contact_no', 'input_number.dim'), MOVE('b2', 'input_number.dim', 'light.flood')] },
    { id: 'r3', comment: '', elements: [WHEN('c1', 'contact_no', 'input_select.heater_mode'), COIL('c2', 'switch.heater')] },
    { id: 'r4', comment: '', elements: [WHEN('d1', 'contact_no', 'input_select.strip_color'), COIL('d2', 'switch.heater')] },
    { id: 'r5', comment: '', elements: [WHEN('f1', 'contact_no', 'binary_sensor.motion'), MOVE('f2', '40', 'light.relay'),
      MOVE('f3', '[255, 0, 0]', 'light.flood', 'rgb_color'), MOVE('f4', '2700', 'light.strip', 'color_temp_kelvin'),
      MOVE('f5', 'rainbow', 'light.strip', 'effect'), MOVE('f6', '[0, 0, 255]', 'light.strip', 'rgb_color'), MOVE('f7', '60', 'light.flood')] },
    { id: 'r6', comment: '', elements: [WHEN('g1', 'contact_no', 'input_select.mode', { raw: { trigger: 'state', entity_id: 'input_select.mode', to: 'on' }, src: 'triggers[0]' }),
      COIL('g2', 'switch.heater')] },
    { id: 'r7', comment: '', elements: [WHEN('h1', 'contact_p', 'input_button.doorbell'), COIL('h2', 'switch.heater')] }] },
];

const STATES = {
  'light.strip': { entity_id: 'light.strip', state: 'on', attributes: { friendly_name: 'Outdoor kitchen strip', supported_color_modes: ['color_temp', 'xy'], supported_features: 40 } },
  'light.flood': { entity_id: 'light.flood', state: 'off', attributes: { friendly_name: 'Salon floodlight', supported_color_modes: ['brightness'], supported_features: 0 } },
  'light.relay': { entity_id: 'light.relay', state: 'off', attributes: { friendly_name: 'Kitchen <b>light</b>', supported_color_modes: ['onoff'], supported_features: 0 } },
  'input_select.strip_color': { entity_id: 'input_select.strip_color', state: 'red', attributes: { friendly_name: 'Strip color', options: ['red', 'orange', 'blue'] } },
  'input_select.heater_mode': { entity_id: 'input_select.heater_mode', state: 'auto', attributes: { friendly_name: 'Heater mode', options: ['on', 'off', 'auto'] } },
  'input_select.mode': { entity_id: 'input_select.mode', state: 'day', attributes: { friendly_name: 'Mode', options: ['day', 'night'] } },
  'input_number.dim': { entity_id: 'input_number.dim', state: '40.0', attributes: { friendly_name: 'Dim', min: 0, max: 100 } },
  'input_button.doorbell': { entity_id: 'input_button.doorbell', state: '2026-11-17T08:00:00+00:00', attributes: { friendly_name: 'Doorbell' } },
  'binary_sensor.motion': { entity_id: 'binary_sensor.motion', state: 'off', attributes: { friendly_name: 'Motion' } },
  'switch.heater': { entity_id: 'switch.heater', state: 'off', attributes: { friendly_name: 'Heater' } },
};

function makeHass() {
  return {
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
}

export async function dashboardValueChecks(check, { size = 'desktop' } = {}) {
  window.alert = () => {};
  window.confirm = () => false;
  window.prompt = () => null;
  if (!customElements.get('ha-entity-picker')) customElements.define('ha-entity-picker', class extends HTMLElement {});
  localStorage.clear();
  const panel = document.createElement('libi-panel');
  panel.style.height = '800px';
  document.body.appendChild(panel);
  panel.hass = makeHass();
  await until(() => panel._initialized && panel._project && panel.core.nets.length === 1);
  await sleep(80);
  const sr = panel.shadowRoot;
  const core = panel.core;
  const el = (rungId, id) => core.findEl('n1', rungId, id);
  const block = (id) => sr.querySelector(`.libi-el[data-eid="${id}"]`);
  const red = (id) => !!block(id) && block(id).classList.contains('has-error');
  const inspect = async (rungId, id) => {
    panel._inspectedEl = { netId: 'n1', rungId, elId: id };
    panel._wakeSidebar();
    panel._render();
    await sleep(30);
    return sr.querySelector('#inspectorBody');
  };
  const text = (body, sel) => ((body && body.querySelector(sel)) || {}).textContent || '';

  // ---- a contact on what the dashboard sets
  check('a P contact on a list of colors is not red', !red('a1'));
  let body = await inspect('r1', 'a1');
  check('and says it starts the rung the moment the value changes', /Starts the rung the moment its value changes/.test(text(body, '.contact-note'))
        && !body.querySelector('.contact-why'), text(body, '.insp-note'));
  check('a NO contact on a number is red', red('b1'));
  body = await inspect('r2', 'b1');
  check('the Inspector says why, and what to draw instead', /input_number\.dim is never on or off/.test(text(body, '.contact-why'))
        && /make it a P contact/.test(text(body, '.contact-why')), text(body, '.insp-note'));
  check('a list with on among its options may be on: not red', !red('c1'));
  check('a list of colors is never on: red', red('d1'));
  check('a check read from Home Assistant is never red, so SAVE is not stopped by it', !red('g1'));
  body = await inspect('r6', 'g1');
  check('the Inspector says it never holds, and that it is saved as it is', /never holds\. It is saved as it is\./.test(text(body, '.contact-note')),
        text(body, '.insp-note'));
  body = await inspect('r7', 'h1');
  check('a P contact on a button starts the rung the moment it is pressed', text(body, '.contact-note') === 'Starts the rung the moment it is pressed.');
  check('a contact on a motion sensor is as before: no note', (await inspect('r5', 'f1')) && !sr.querySelector('#inspectorBody .contact-note, #inspectorBody .contact-why'));

  const refused = await panel._saveProject();
  check('SAVE is refused while a contact on a value is red', !!refused && refused.refused === true, JSON.stringify(refused));

  // ---- made a P contact, it is the moment the value changes
  body = await inspect('r2', 'b1');
  const kind = body.querySelector('#propType');
  kind.value = 'contact_p';
  kind.dispatchEvent(new Event('change', { bubbles: true }));
  await sleep(40);
  check('made a P contact, the number starts the rung when it changes: not red', el('r2', 'b1').type === 'contact_p' && !red('b1'));
  check('and the Inspector says so', /moment its value changes/.test(text(sr.querySelector('#inspectorBody'), '.contact-note')));

  // ---- what each light does with a value
  body = await inspect('r5', 'f2');
  check('a MOVE of a brightness to a light that only turns on and off says so', /only turns on and off: Home Assistant turns it on and leaves the brightness out/.test(text(body, '.light-note')),
        text(body, '.light-note'));
  check('the light\'s name is text, not markup', !body.querySelector('.light-note b') && /Kitchen <b>light<\/b>/.test(text(body, '.light-note')));
  body = await inspect('r5', 'f3');
  check('a color to a light that only dims says it has no color', /Salon floodlight has no color/.test(text(body, '.light-note')), text(body, '.light-note'));
  body = await inspect('r5', 'f4');
  check('a color temperature to the strip that has one: no note', !body.querySelector('.light-note'));
  body = await inspect('r5', 'f5');
  check('an effect to a light with none says so', /has no effects/.test(text(body, '.light-note')), text(body, '.light-note'));
  body = await inspect('r5', 'f6');
  check('a color to the strip: no note', !body.querySelector('.light-note'));
  body = await inspect('r5', 'f7');
  check('dimming the floodlight: no note', !body.querySelector('.light-note'));
  check('a note is no error: the MOVE is not red', !red('f2') && !red('f3') && !red('f5'));

  // ---- opening the Inspector changes nothing
  const ids = [['r1', 'a1'], ['r3', 'c1'], ['r4', 'd1'], ['r6', 'g1'], ['r7', 'h1'], ['r5', 'f2'], ['r5', 'f3'], ['r5', 'f5']];
  const changed = [];
  for (const [r, id] of ids) {
    const before = JSON.stringify(el(r, id));
    await inspect(r, id);
    if (JSON.stringify(el(r, id)) !== before) changed.push(id);
  }
  check('opening the Inspector on them changes nothing', changed.length === 0, changed.join());

  // ---- [ADDED 2026-11-18] The review of the release: a P contact on a list that may be on starts the rung on ANY
  // change - to off as well (libi_to_yaml._change_trigger) - and the Inspector says so, and how to wait for on.
  check('a P contact on a list of colors says when it starts, as before',
        /picked on a dashboard, typed or measured/.test(text(await inspect('r1', 'a1'), '.contact-note')));
  body = await inspect('r3', 'c1');
  const heater = body.querySelector('#propType');
  heater.value = 'contact_p';
  heater.dispatchEvent(new Event('change', { bubbles: true }));
  await sleep(40);
  const said = text(sr.querySelector('#inspectorBody'), '.contact-note');
  check('a P contact on a list with on among its options: any change, off too - and a CMP = on for the moment it turns on',
        el('r3', 'c1').type === 'contact_p' && !red('c1')
        && said === 'Starts the rung the moment its value changes - to any value, off too. For the moment it turns on, use a CMP = on.', said);

  // ---- the screen
  for (const [r, id, sel] of [['r4', 'd1', '.contact-why'], ['r5', 'f2', '.light-note']]) {
    body = await inspect(r, id);
    const note = body.querySelector(sel);
    const side = body.closest('.sidebar, .inspector, aside') || body;
    check(`on a ${size} the ${sel.slice(1)} fits the Inspector, no sideways scroll`, !!note && note.getBoundingClientRect().width > 0
          && body.scrollWidth <= body.clientWidth + 1 && side.scrollWidth <= side.clientWidth + 1, `${body.scrollWidth} > ${body.clientWidth}`);
  }
  panel._markSaved && panel._markSaved();
  panel.remove();
}
