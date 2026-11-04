/*
 * LIBI for Home Assistant
 * Copyright (C) 2026 Guy Azria
 *
 * This program is free software: you can redistribute it and/or modify it
 * under the terms of the GNU General Public License as published by the Free
 * Software Foundation, either version 3 of the License, or (at your option)
 * any later version.
 *
 * This program is distributed in the hope that it will be useful, but WITHOUT
 * ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
 * FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for
 * more details. <https://www.gnu.org/licenses/>.
 */
/**
 * LIBI Panel - AI chat
 * v3.85.0
 */
//
// [ADDED v3.84.0 | 2026-11-02] Purpose: The zone chosen on the dashboard card says what it is: a dropdown of the user's
//   zones, "home" for the Home zone, and who must be there is in it when their state is the zone chosen.
// [ADDED v3.85.0 | 2026-11-04] Purpose: Adding a NET says why it was not saved when the compile failed - SAVE & COMPILE
//   compiles first and saves nothing then - and that Home Assistant wrote what was saved.
//
// The AI chat under the Inspector: the user describes the logic, picks the devices from lists LIBI found
// in Home Assistant (several per role), answers the questions, and gets a DRAFT net to add to the
// canvas. Nothing here writes to Home Assistant; the net is saved by the ordinary SAVE & COMPILE.
//
// SECURITY: every text in here - the model's replies, device names, YAML - is untrusted and is put
// on the page with textContent or as a text node, never as HTML (CLAUDE.md RULE 15).

const OPEN_KEY = 'libi_ai_open';
const SHARE_KEY = 'libi_ai_share';

function h(tag, props = {}, ...children) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(props || {})) {
        if (v === undefined || v === null || v === false) continue;
        if (k === 'class') el.className = v;
        else if (k === 'text') el.textContent = v;
        else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
        else if (k in el && typeof v !== 'string') el[k] = v;
        else el.setAttribute(k, v === true ? '' : String(v));
    }
    for (const c of children.flat()) {
        if (c === null || c === undefined || c === false) continue;
        el.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
    }
    return el;
}

export class LibiAiChat {
    /** @param panel the LibiPanel; used for hass and to add a net to the canvas */
    constructor(panel) {
        this.panel = panel;
        this.root = h('div', { class: 'ai-chat' });
        this.status = null;
        this.statusAsked = false;
        this.open = this._readOpen();
        this.shareNets = this._readShare();
        this.messages = [];      // what the model sees: {role, content}
        this.log = [];           // what the user sees
        this.plan = null;
        this.candidates = {};
        this.selections = {};    // role id -> Set of entity ids
        this.answers = {};
        this.filters = {};
        this.newHelpers = [];  // [ADDED v3.43.0] helpers the AI proposed, created only on the user's click
        this.vars = {};        // [ADDED v3.82.0] role id -> {mode: existing|new|none, pick}: each local variable
        this.loadWaitMs = 5000;  // [ADDED v3.67.0] how long a saved automation may take to show up in Home Assistant
        this.draft = '';
        this.busy = '';
        this.render();
        this._watchSize();
    }

    _readOpen() {
        try { return localStorage.getItem(OPEN_KEY) !== '0'; } catch (e) { return true; }
    }

    _readShare() {
        try { return localStorage.getItem(SHARE_KEY) !== '0'; } catch (e) { return true; }
    }

    _setShare(on) {
        this.shareNets = !!on;
        try { localStorage.setItem(SHARE_KEY, this.shareNets ? '1' : '0'); } catch (e) { /* not stored */ }
        this.render(true);
    }

    /** [ADDED v3.40.0] The nets the model may read: what is on the canvas, when the user shares it. */
    _nets() {
        return this.shareNets ? (this.panel.core.nets || []) : [];
    }

    _netName(id) {
        const n = (this.panel.core.nets || []).find(x => x.id === id);
        return n ? (n.name || n.id) : id;
    }

    /** [ADDED v3.59.0] "NET 3 · Garden": the number the canvas shows, which is how the user names a net. */
    _netLabel(id) {
        const nets = this.panel.core.nets || [];
        const i = nets.findIndex(x => x.id === id);
        return i < 0 ? String(id) : `NET ${i + 1} · ${nets[i].name || nets[i].id}`;
    }

    get hass() { return this.panel._hass; }

    /** Called after every render of the panel: the chat keeps its own DOM and is moved, not rebuilt. */
    attach(mount) {
        if (!mount) return;
        if (this.root.parentNode !== mount) mount.appendChild(this.root);
        this._markLayout();
        if (!this.statusAsked && this.hass && this.hass.connection) {
            this.statusAsked = true;
            this._ws({ type: 'libi/ai_status' })
                .then(s => { this.status = s; this.render(); })
                .catch(() => { this.status = { configured: false }; this.render(); });
        }
    }

    _ws(msg) { return this.hass.connection.sendMessagePromise(msg); }

    _toggle() { this.setOpen(!this.open); }

    /** Opens or closes the chat and remembers it. The rail's CHAT AI button calls this. */
    setOpen(open) {
        this.open = !!open;
        try { localStorage.setItem(OPEN_KEY, this.open ? '1' : '0'); } catch (e) { /* not stored */ }
        this.render();
    }

    /** [ADDED v3.39.0] The open chat takes the whole sidebar: the mount grows and the sidebar hides the
     *  inspector. Both are re-marked after every panel render, because the sidebar is rebuilt. */
    _markLayout() {
        const mount = this.root.parentNode;
        if (!mount || !mount.classList) return;
        mount.classList.toggle('ai-open', this.open);
        const bar = mount.closest ? mount.closest('.sidebar') : null;
        if (bar) bar.classList.toggle('ai-full', this.open);
    }

    _reset() {
        this.messages = []; this.log = []; this.plan = null; this.candidates = {};
        this.selections = {}; this.answers = {}; this.filters = {}; this.newHelpers = []; this.vars = {}; this.busy = '';
        this.render();
    }

    // ------------------------------------------------------------------ conversation

    async send() {
        const text = this.draft.trim();
        if (!text || this.busy) return;
        this.draft = '';
        this.messages.push({ role: 'user', content: text });
        this.log.push({ kind: 'user', text });
        this.busy = 'Reading your request…';
        this.render();
        try {
            const res = await this._ws({ type: 'libi/ai_plan', messages: this.messages, nets: this._nets(), share: this.shareNets });
            const plan = res.plan;
            // [ADDED v3.40.0] A question is answered in the chat; there is nothing to pick or build.
            if (plan.intent === 'answer') {
                this.messages.push({ role: 'assistant', content: plan.reply });
                this.log.push({ kind: 'ai', text: plan.reply });
                this.plan = null;
                this.busy = '';
                this.render();
                return;
            }
            const pre = res.preselect || {};
            const kept = {};
            for (const role of plan.roles) {
                // [ADDED v3.75.0] A schedule that gave way to the alarm clock is not used: no tick, not even an earlier one.
                if (role.replaced) { kept[role.id] = new Set(); continue; }
                const old = this.selections[role.id];
                const items = ((res.candidates || {})[role.id] || {}).items || [];
                const ids = new Set(items.map(i => i.entity_id));
                kept[role.id] = new Set(old ? [...old].filter(e => ids.has(e)) : []);
                // For a change, the devices the net already uses start ticked; [v3.60.0] so do the helpers the
                // user's message names.
                (pre[role.id] || []).forEach(e => { if (ids.has(e)) kept[role.id].add(e); });
                // One exact match is almost certainly the one; it is ticked but can be unticked. [CHANGED v3.62.0] Not
                // in an optional role: a phone there would get every message twice, so it is picked only on purpose.
                const cand = (res.candidates || {})[role.id] || {};
                if (!kept[role.id].size && !role.optional && cand.exact && items.length === 1) kept[role.id].add(items[0].entity_id);
            }
            this.selections = kept;
            this.plan = plan;
            // [CHANGED v3.82.0] And the helpers a variable can be made as where a free one of the user's fits: made only
            // when the user switches that variable to New.
            this.newHelpers = [...(plan.new_helpers || []).map(x => ({ ...x, keep: true, created: '', error: '' })),
                ...(plan.alternatives || []).map(x => ({ ...x, keep: false, created: '', error: '', alternative: true }))];
            this.candidates = res.candidates || {};
            this.answers = Object.fromEntries((plan.questions || [])
                .filter(q => q.id in this.answers).map(q => [q.id, this.answers[q.id]]));
            // [ADDED v3.82.0] Each local variable starts with the free helper that fits, else with the new one - or as the
            // user left it in the plan before.
            const before = this.vars || {};
            this.vars = {};
            for (const role of plan.roles) if (role.variable) this._initVar(role, before[role.id]);
            // [ADDED v3.80.0] A yes kept from the plan before adds again what it adds to this one.
            for (const q of plan.questions || []) this._applyAnswer(q);
            const summary = plan.roles.map(r => r.label).join(', ');
            this.messages.push({ role: 'assistant', content: `${plan.reply}${summary ? ` [to pick: ${summary}]` : ''}` });
            this.log.push({ kind: 'ai', text: plan.reply || 'Pick the devices below.' });
        } catch (err) {
            this.log.push({ kind: 'error', text: this._errText(err) });
        }
        this.busy = '';
        this.render();
    }

    async build() {
        if (!this.plan || this.busy) return;
        // [CHANGED v3.62.0] LIBI checks every answer and has the AI correct what does not hold, up to three answers.
        this.busy = 'Writing the logic… LIBI checks every draft and has the AI correct what does not hold, which can take a minute.';
        this.render();
        const selections = Object.fromEntries(Object.entries(this.selections).map(([k, v]) => [k, [...v]]));
        try {
            const res = await this._ws({
                type: 'libi/ai_build', messages: this.messages, plan: this.plan,
                selections, answers: this.answers, nets: this._nets(), share: this.shareNets,
            });
            if (res.ok) {
                this.messages.push({ role: 'assistant', content: res.reply || 'Built.' });
                this.log.push({ kind: 'result', res, added: false });
                this.plan = null;
            } else {
                // [CHANGED v3.62.0] Said with how many answers LIBI checked before giving up.
                const tries = Number(res.tries) || 1;
                this.log.push({ kind: 'error', list: res.errors || [], text: tries > 1
                    ? `The draft was not accepted, also after ${tries - 1} correction${tries === 2 ? '' : 's'} by the AI:`
                    : 'The draft was not accepted:' });
            }
        } catch (err) {
            this.log.push({ kind: 'error', text: this._errText(err) });
        }
        this.busy = '';
        this.render();
    }

    _privacyText() {
        const s = this.status || {};
        const names = { gemini: 'Google Gemini', openai: 'OpenAI', custom: 'your AI service', ollama: 'your AI server' };
        const where = names[s.provider] || 'the AI service';
        if (this.shareNets) {
            return `Your messages, the nets open on this page, your helpers and the devices that match your request (name, state, unit) are sent to ${where}. `
                + 'Your other automations and the rest of your devices are not.';
        }
        return `Your messages and the names of the devices you pick are sent to ${where}. `
            + 'Your automations, device states and the full list of your devices are not.';
    }

    _errText(err) {
        if (err && err.code === 'not_configured') return 'AI is not set up yet.';
        return (err && err.message) ? err.message : String(err);
    }

    /** [ADDED v3.43.0] Creates the helpers the user kept, with the same <domain>/create call the
     *  Helper tab makes. Each new helper becomes the pick for its role. Nothing runs without this click. */
    async createHelpers() {
        const todo = this.newHelpers.filter(x => x.keep && !x.created);
        if (!todo.length || this.busy) return;
        this.busy = `Creating ${todo.length} helper${todo.length === 1 ? '' : 's'}…`;
        this.render(true);
        for (const item of todo) {
            const name = String(item.name || '').trim();
            if (!name) { item.error = 'A helper needs a name.'; continue; }
            try {
                const res = await this._ws({ type: `${item.domain}/create`, name, ...(item.settings || {}) });
                const objectId = res && (res.id || res.object_id);
                if (!objectId) throw new Error('Home Assistant did not return the new helper.');
                const eid = `${item.domain}.${objectId}`;
                await this._waitForState(eid);
                item.created = eid;
                item.error = '';
                if (this.vars[item.role]) this.vars[item.role].mode = 'new';
                this.selections[item.role] = new Set([eid]);
                const cand = this.candidates[item.role] || (this.candidates[item.role] = { items: [], exact: true });
                if (!cand.items.some(i => i.entity_id === eid)) {
                    cand.items.unshift({ entity_id: eid, name, area: '', state: '', created: true });
                }
                cand.exact = true;
            } catch (err) {
                item.error = (err && err.message) ? err.message : String(err);
            }
        }
        if (typeof this.panel._varsRefreshIds === 'function') {
            try { await this.panel._varsRefreshIds(); } catch (e) { /* the helper list refreshes later */ }
        }
        this.busy = '';
        this.render(true);
    }

    async _waitForState(eid, ms = 5000) {
        const end = Date.now() + ms;
        while (Date.now() < end) {
            if (this.hass && this.hass.states && this.hass.states[eid]) return true;
            await new Promise(r => setTimeout(r, 200));
        }
        return false;
    }

    _helperSummary(item) {
        const kinds = { input_boolean: 'Toggle', input_number: 'Number', input_datetime: 'Date / time',
            input_select: 'Dropdown', input_text: 'Text', input_button: 'Button', counter: 'Counter', timer: 'Timer',
            schedule: 'Schedule (weekly calendar)' };
        const st = item.settings || {};
        const parts = [];
        if (item.domain === 'input_number' && !item.days_bits) parts.push(`${st.min ?? 0}–${st.max ?? 100}${st.unit_of_measurement ? ' ' + st.unit_of_measurement : ''}`);
        if (item.domain === 'input_datetime') parts.push([st.has_date ? 'date' : '', st.has_time ? 'time' : ''].filter(Boolean).join(' + '));
        if (item.domain === 'input_select') parts.push((st.options || []).join(' / '));
        if (item.domain === 'timer' && st.duration) parts.push(st.duration);
        // [CHANGED v3.76.0] The days helper of an alarm clock: its 8 bits are the days (no switch for each day any more).
        if (item.days_bits) parts.push('8 bits: bit 1 Sun … bit 7 Sat');
        if (item.domain === 'schedule') {
            // [ADDED v3.53.0] The days marked, Mon first as Home Assistant shows the week.
            const days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
                .filter(d => Array.isArray(st[d]) && st[d].length)
                .map(d => `${d.slice(0, 3)} ${st[d].map(r => `${String(r.from).slice(0, 5)}–${String(r.to).slice(0, 5)}`).join(', ')}`);
            parts.push(days.length ? days.join(' · ') : 'mark the days and hours in Settings ▸ Helpers after creating it');
        }
        return `${kinds[item.domain] || item.domain}${parts.length ? ' · ' + parts.join(' · ') : ''}`;
    }

    /** [ADDED v3.82.0] The helper a variable can be made as: the one LIBI proposes, or the alternative of a free one. */
    _helperOf(rid) {
        return this.newHelpers.find(x => x.role === rid);
    }

    /** [ADDED v3.82.0] Where a variable starts: the free helper of the user's that fits ("pick", or the one ticked for it),
     *  else the new one - or, from the plan before, as the user left it while that still holds. */
    _initVar(role, old) {
        const helper = this._helperOf(role.id);
        const items = ((this.candidates[role.id] || {}).items || []).map(i => i.entity_id);
        const ticked = [...(this.selections[role.id] || [])].find(e => items.includes(e)) || '';
        let pick = (helper && helper.pick) || ticked;
        let mode = helper && !helper.alternative ? 'new' : 'existing';
        if (old && (old.mode === 'new' ? !!helper : old.mode === 'none' ? !!role.optional : items.includes(old.pick))) {
            ({ mode, pick } = old);
        }
        if (mode === 'existing' && !pick && helper) mode = 'new';
        this.vars[role.id] = { mode, pick: pick || '' };
        this._syncVar(role.id);
    }

    /** [ADDED v3.82.0] A variable's pick, from how it is set: the helper chosen, the new one once it is made, or none. */
    _syncVar(rid) {
        const v = this.vars[rid];
        if (!v) return;
        const helper = this._helperOf(rid);
        if (helper && !helper.created) helper.keep = v.mode === 'new';
        this.selections[rid] = new Set(v.mode === 'new' ? (helper && helper.created ? [helper.created] : [])
            : v.mode === 'existing' && v.pick ? [v.pick] : []);
    }

    /** [ADDED v3.82.0] The variable that uses a helper already, but this one: no helper is two variables at once. */
    _pickedElsewhere(eid, rid) {
        const other = Object.entries(this.vars).find(([id, v]) => id !== rid && v.mode === 'existing' && v.pick === eid);
        return other ? ((this.plan.roles.find(r => r.id === other[0]) || {}).label || other[0]) : '';
    }

    /** [ADDED v3.82.0] The local variables of the NET in one window, first in the plan - the user: "all the local variables at
     *  the start, in the same window; always the option to create them all new; and if a variable is free, choose it instead
     *  of creating a new one". One row each, "All new" for every one, and one button that creates the new ones. */
    _variablesView(roles) {
        const ready = roles.filter(r => r.replaced || (this.selections[r.id] && this.selections[r.id].size)).length;
        const box = h('div', { class: 'ai-vars' },
            h('div', { class: 'ai-role-head' }, h('strong', { text: 'Local variables' }),
                h('span', { class: 'ai-count', text: `${ready} / ${roles.length}` })),
            h('div', { class: 'ai-note', text: 'The helpers this NET reads and sets, all in one place. A free helper that fits is chosen at the start; pick another one, or make a new one - LIBI creates the new ones when you press the button.' }));
        // [CHANGED v3.76.0] An alarm clock: the days are the bits of ONE helper, ticked as checkboxes on the card.
        // [CHANGED v3.79.0] Seven round buttons on the card (libi-days-row.js).
        if (this.newHelpers.some(x => x.days_bits && roles.some(r => r.id === x.role))) {
            box.appendChild(h('div', { class: 'ai-note ai-alarm-note', text: 'The days are ONE helper: its 8 bits are the days, bit 1 Sunday to bit 7 Saturday. On the dashboard card they are seven round buttons under the time you set there, as on an alarm clock: tap a day to turn it on or off. It starts at 0, so nothing runs until you turn a day on.' }));
        }
        for (const role of roles) box.appendChild(this._variableRow(role));
        const acts = h('div', { class: 'ai-var-acts' });
        const todo = roles.map(r => this._helperOf(r.id)).filter(x => x && x.keep && !x.created).length;
        if (todo) {
            acts.appendChild(h('button', { class: 'btn btn-primary ai-create-helpers', disabled: !!this.busy,
                text: `Create the ${todo} new variable${todo === 1 ? '' : 's'}`, onclick: () => this.createHelpers() }));
        }
        const other = roles.filter(r => !r.replaced && this._helperOf(r.id) && this.vars[r.id] && this.vars[r.id].mode !== 'new');
        if (other.length) {
            acts.appendChild(h('button', { class: 'ha-text-btn ai-all-new', text: 'All new', onclick: () => {
                for (const r of other) { this.vars[r.id].mode = 'new'; this._syncVar(r.id); }
                this.render(true);
            } }));
        }
        if (acts.children.length) box.appendChild(acts);
        return box;
    }

    /** [ADDED v3.82.0] One local variable: Use a helper that exists - a free one that fits is chosen - or New, made under
     *  the name in the field; an optional one can be left out. What was said of its role is said here. */
    _variableRow(role) {
        const v = this.vars[role.id] || (this.vars[role.id] = { mode: 'existing', pick: '' });
        const helper = this._helperOf(role.id);
        const cand = this.candidates[role.id] || { items: [], exact: false };
        const items = cand.items || [];
        const row = h('div', { class: 'ai-var', 'data-role': role.id },
            h('div', { class: 'ai-role-head', dir: 'auto' }, h('strong', { text: role.label }),
                role.replaced ? h('span', { class: 'ai-current ai-optional', text: 'not used' })
                    : role.optional ? h('span', { class: 'ai-current ai-optional', text: 'optional' }) : null));
        // [ADDED v3.74.0] A schedule the message names that gave way to the alarm clock: a card cannot set it.
        // [CHANGED v3.75.0] Nor is it used - the user's choice - so there is nothing to pick: picked, it started the user's
        // NET 3 in place of the time set on the card.
        // [CHANGED v3.78.0] Or one the message names that this Home Assistant does not have, or one nothing of the user's fits.
        if (role.replaced) {
            const named = role.named || items.some(i => i.named);
            row.appendChild(h('div', { class: 'ai-note warn ai-replaced', dir: 'auto', text: role.missing
                ? `Your message names the schedule "${role.missing}", but this Home Assistant has no schedule by that name. So the days and the start time are set as on an alarm clock, with the variables here - a dashboard card cannot set the days and hours of a schedule anyway.`
                : named ? 'Your message names this schedule, but a dashboard card cannot set the days and hours of a schedule - only its own settings can. So the days and the start time are set as on an alarm clock, with the variables here, and this schedule is not used.'
                : 'No schedule of yours fits, and a dashboard card cannot set the days and hours of a schedule - only its own settings can. So the days and the start time are set as on an alarm clock, with the variables here, and no schedule is used.' }));
            return row;
        }
        // [ADDED v3.78.0] A helper the message names that is gone - deleted with a NET, for example - until it is made again.
        if (role.missing && !(helper && helper.created)) {
            row.appendChild(h('div', { class: 'ai-note warn ai-missing', dir: 'auto', text: `Your message names "${role.missing}", but no helper in this Home Assistant has that name.${helper && v.mode === 'new' ? ' The new one gets that name.' : ''}` }));
        }
        // [ADDED v3.84.0] The zone chosen on the card: a dropdown of the user's zones, as a person's state names them.
        if (role.zone_choice) {
            row.appendChild(h('div', { class: 'ai-note ai-zone-choice', text: 'The zone is chosen on the dashboard card, from a list of your zones - "home" is your Home zone. Who must be there is in it when their state is the zone chosen. When you add or rename a zone later, change this list too, in the helper\'s settings (Settings ▸ Helpers).' }));
        }
        const group = `ai-var-${role.id}`;
        const choose = (mode) => { v.mode = mode; this._syncVar(role.id); this.render(true); };
        if (items.length) {
            const select = h('select', { class: 'ai-var-pick', dir: 'auto', onchange: e => { v.pick = e.target.value; choose('existing'); } });
            if (!v.pick) select.appendChild(h('option', { value: '', text: 'Pick one' }));
            // The name and what it is, as a narrow phone shows them; the entity id of the one chosen is said under the list,
            // and that of a name two helpers share in the list itself.
            const names = items.map(i => i.name || i.entity_id);
            for (const item of items) {
                const elsewhere = this._pickedElsewhere(item.entity_id, role.id);
                const tags = [item.named ? 'named' : '', item.exists ? 'free' : '', item.current ? 'current' : '',
                    item.created ? 'new' : '', item.on_canvas ? item.on_canvas.split(' · ')[0] : '',
                    elsewhere ? `chosen for ${elsewhere}` : ''].filter(Boolean);
                const name = item.name || item.entity_id;
                const twice = names.filter(n => n === name).length > 1;
                select.appendChild(h('option', { value: item.entity_id, disabled: !!elsewhere,
                    text: `${name}${twice ? ` · ${item.entity_id}` : ''}${tags.length ? ` (${tags.join(', ')})` : ''}` }));
            }
            select.value = v.pick || '';
            row.appendChild(h('label', { class: 'ai-var-opt' },
                h('input', { type: 'radio', name: group, value: 'existing', checked: v.mode === 'existing', onchange: () => choose('existing') }),
                h('span', { class: 'ai-var-kind', text: 'Use' }), select));
            if (v.pick) row.appendChild(h('div', { class: 'ai-item-id ai-var-what ai-var-id', text: v.pick }));
            const picked = items.find(i => i.entity_id === v.pick);
            // [ADDED v3.60.0] A named helper is listed although others use it; the user is told who.
            if (v.mode === 'existing' && picked && picked.used_by && picked.used_by.length) {
                row.appendChild(h('div', { class: 'ai-note warn', dir: 'auto', text: `Also used by ${picked.used_by.join(', ')}: setting it changes it there too.` }));
            }
            if (v.mode === 'existing' && !cand.exact) row.appendChild(h('div', { class: 'ai-note warn', text: 'No exact match. These are the closest helpers.' }));
        }
        if (helper) {
            const field = h('input', { class: 'ai-filter ai-var-name', type: 'text', dir: 'auto', disabled: !!helper.created,
                oninput: e => { helper.name = e.target.value; } });
            field.value = helper.name;
            row.appendChild(h('label', { class: 'ai-var-opt' },
                h('input', { type: 'radio', name: group, value: 'new', checked: v.mode === 'new', onchange: () => choose('new') }),
                h('span', { class: 'ai-var-kind', text: 'New' }), field));
            row.appendChild(h('div', { class: 'ai-item-id ai-var-what', text: helper.created ? `created: ${helper.created}` : this._helperSummary(helper) }));
            if (helper.error) row.appendChild(h('div', { class: 'ai-note warn', text: helper.error }));
        }
        if (role.optional) {
            row.appendChild(h('label', { class: 'ai-var-opt' },
                h('input', { type: 'radio', name: group, value: 'none', checked: v.mode === 'none', onchange: () => choose('none') }),
                h('span', { class: 'ai-var-kind', text: role.named ? 'Not used - your message names it, but leave it out' : 'Not used' })));
        }
        if (cand.hidden_used) row.appendChild(h('div', { class: 'ai-note', text: `${cand.hidden_used} helper${cand.hidden_used === 1 ? '' : 's'} used by other automations or scripts ${cand.hidden_used === 1 ? 'is' : 'are'} not listed.` }));
        if (!items.length && !helper) row.appendChild(h('div', { class: 'ai-note', text: `Nothing of type ${role.domains.join(', ') || '?'} was found in Home Assistant.` }));
        return row;
    }

    /** [ADDED v3.80.0] Whether the answer to a question is its yes (LIBI's questions say which choice is). */
    _yes(q) {
        return (q.yes || []).includes(this.answers[q.id]);
    }

    /** [ADDED v3.80.0] A yes to a question of LIBI's that adds something - the on/off switch - puts its role in the plan
     *  and its helper among the ones to create, or ticks the one that exists; any other answer takes them out again. A
     *  helper already created stays: answered yes again, it is the pick.
     *  [CHANGED v3.82.0] The switch is a local variable like the others: it starts with a free switch that fits (the
     *  helper's "pick"), else with the new one, and the user chooses between them in the variables window. */
    _applyAnswer(q) {
        const adds = q && q.adds;
        if (!adds || !adds.role || !this.plan) return;
        const rid = adds.role.id;
        const has = this.plan.roles.some(r => r.id === rid);
        if (this._yes(q)) {
            if (!has) this.plan.roles.push({ ...adds.role, variable: true });
            if (!this.candidates[rid]) this.candidates[rid] = JSON.parse(JSON.stringify(adds.candidates || { items: [], exact: false }));
            if (!this._helperOf(rid) && adds.helper) {
                this.newHelpers.push({ ...adds.helper, keep: false, created: '', error: '', alternative: !!adds.helper.pick, from: q.id });
            }
            if (!this.vars[rid]) {
                const made = this._helperOf(rid);
                this.vars[rid] = made && made.created ? { mode: 'new', pick: '' }
                    : made && made.pick ? { mode: 'existing', pick: made.pick } : { mode: made ? 'new' : 'existing', pick: '' };
            }
            this._syncVar(rid);
        } else if (has) {
            this.plan.roles = this.plan.roles.filter(r => r.id !== rid);
            this.newHelpers = this.newHelpers.filter(x => x.role !== rid || x.created);
            delete this.vars[rid];
            delete this.selections[rid];
        }
    }

    /** [ADDED v3.40.0] A change replaces the net it was made for. It keeps that net's id and its
     *  automation id, so SAVE & COMPILE updates the same automation instead of adding a second one. */
    _replaceOnCanvas(entry, version) {
        // [ADDED v3.59.0] Only over a net whose version that runs now is kept, so the user can go back to it.
        if (!version) return;
        const core = this.panel.core;
        const idx = (core.nets || []).findIndex(n => n.id === entry.res.target_net);
        if (idx < 0) { this._addToCanvas(entry); return; }
        const old = core.nets[idx];
        const net = core.duplicateNet(entry.res.net);
        net.id = old.id;
        net.ha_id = old.ha_id || entry.res.net.ha_id;
        net.name = entry.res.net.name || old.name;
        net.collapsed = false;
        core.nets[idx] = net;
        core.syncCounters();
        core.pushHistory();
        this.panel._projectDirty = true;
        entry.added = 'replaced';
        entry.version = version;
        entry.haId = net.ha_id;
        this.render(true);
        this.panel._render();
    }

    _addToCanvas(entry) {
        const core = this.panel.core;
        const net = core.duplicateNet(entry.res.net);
        net.name = entry.res.net.name;
        net.ha_id = entry.res.net.ha_id;
        core.nets.push(net);
        core.syncCounters();
        core.pushHistory();
        this.panel._projectDirty = true;
        entry.added = true;
        entry.addedAs = core.nets.length;
        entry.haId = net.ha_id;
        // The panel's render only moves this DOM, so the chat redraws itself: the button must show
        // at once that the net is on the canvas, or it could be added twice.
        this.render(true);
        this.panel._render();
        const el = this.panel.shadowRoot && this.panel.shadowRoot.querySelector(`[data-nid="${CSS.escape(net.id)}"]`);
        if (el && el.scrollIntoView) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    /** [ADDED v3.67.0] A draft the ladder would change is not saved on its own: the user checks it first.
     *  [CHANGED v3.73.0] Nor one that misses a line of the request. */
    _autoSaves(res) {
        return !this._holdReason(res);
    }

    /** [ADDED v3.73.0] Why a draft goes onto the canvas without being saved, or '' when it is saved at once. */
    _holdReason(res) {
        if (res && res.round_trip && res.round_trip.ok === false) return 'Not saved: the ladder would change this draft. Check the YAML, then press SAVE & COMPILE.';
        if (res && (res.checklist || []).some(i => i.ok === false)) return 'Not saved: the draft does not do every line of your request (✗ above). Check it, then press SAVE & COMPILE.';
        // [ADDED v3.75.0] Home Assistant runs only the first of two rungs of one trigger that holds - not what the ladder shows.
        if (res && (res.shared_rungs || []).length) return 'Not saved: two rungs start with the same trigger, and Home Assistant runs only the first one that holds (see the notes). Check it, then press SAVE & COMPILE.';
        return '';
    }

    /** [ADDED v3.67.0] The user's click on Add or Replace. The NET goes onto the canvas and - the user's choice,
     *  2026-10-29 - is saved and compiled at once and checked, so the chat says whether it runs as built. Not when
     *  the ladder would change the draft; and only after asking when other unsaved changes on the canvas would be
     *  saved with it, or when the NET drives a security-sensitive device (CLAUDE.md RULE 9). */
    async _place(entry, how, version) {
        const res = entry.res;
        // [CHANGED v3.85.0] Other changes not saved, as the panel itself knows them: every change of the logic, not only the
        // ones that marked the project.
        const others = typeof this.panel._hasUnsavedChanges === 'function' ? this.panel._hasUnsavedChanges(true) : !!this.panel._projectDirty;
        if (how === 'replace') this._replaceOnCanvas(entry, version); else this._addToCanvas(entry);
        if (!entry.added) return;
        const hold = (text) => { entry.save = { state: 'held', lines: [{ ok: false, text }] }; this.render(true); };
        if (!this._autoSaves(res)) return hold(this._holdReason(res));
        if (others && !window.confirm('Other changes on the canvas are not saved yet. Saving this NET saves them too. Save everything now?')) {
            return hold('Not saved: press SAVE & COMPILE when the other changes are ready.');
        }
        if ((res.sensitive || []).length && !window.confirm(`This NET controls ${res.sensitive.join(', ')}. Save it to Home Assistant now?`)) {
            return hold('Not saved: press SAVE & COMPILE after checking it.');
        }
        await this._saveAndCheck(entry);
    }

    /** [ADDED v3.67.0] SAVE & COMPILE - the very save of the panel's button - and then a check of what it did, said
     *  line by line (RULE 10): written into which file, reloaded or not, the automation running in Home
     *  Assistant or not accepted, and the automation read back from the file drawn by the ladder exactly as built.
     *  Only a write and a reload the backend confirms is reported as saved. */
    async _saveAndCheck(entry) {
        entry.save = { state: 'saving', lines: [] };
        this.render(true);
        const r = typeof this.panel._saveProject === 'function' ? await this.panel._saveProject() : { failed: 'This panel cannot save.' };
        if (r.refused || r.failed || r.compileErrors || r.saved === false) {
            // [CHANGED v3.85.0] SAVE & COMPILE compiles first and saves nothing when that does not hold.
            const why = r.refused ? 'the drawing has errors (red blocks). Fix them, then press SAVE & COMPILE.'
                : r.compileErrors ? `the compile failed, so nothing was written: ${r.compileErrors.join('; ')}`
                : (r.failed || (r.errors || []).join('; ') || 'Home Assistant refused it.');
            entry.save = { state: 'failed', lines: [{ ok: false, text: `Not saved: ${why}` }] };
            this.render(true);
            return;
        }
        const files = { automation: 'automations.yaml', script: 'scripts.yaml', scene: 'scenes.yaml' };
        const written = r.written || [], reloaded = r.reloaded || [], errors = r.errors || [];
        // [CHANGED v3.85.0] Home Assistant writes them now, through its own config API.
        const lines = [written.length
            ? { ok: true, text: `Home Assistant wrote ${written.map(d => files[d] || d).join(', ')}.` }
            : { ok: true, text: "Saved. Home Assistant's files already held it." }];
        for (const d of written) {
            lines.push(reloaded.includes(d) ? { ok: true, text: `Reloaded in Home Assistant (${d}).` }
                : { ok: false, text: errors.find(e => e.startsWith(`${d} reload`)) || `${d} was not reloaded.` });
        }
        for (const e of errors) if (!written.some(d => e.startsWith(`${d} reload`))) lines.push({ ok: false, text: e });
        if ((entry.res.level || 'automation') === 'automation' && entry.haId) {
            let check = null;
            try { check = await this._ws({ type: 'libi/verify_automation', automation_id: String(entry.haId) }); } catch (err) { check = null; }
            const found = check && (check.results || [])[0];
            if (!found) lines.push({ ok: false, text: 'The automation is not in automations.yaml.' });
            else if (found.ok) lines.push({ ok: true, text: 'Read back from automations.yaml, the ladder draws it exactly as built.' });
            else lines.push({ ok: false, text: `Read back, the ladder would change it: ${(found.issues || []).slice(0, 3).join('; ')}` });
            const st = await this._automationState(entry.haId);
            if (!st) lines.push({ ok: false, text: 'Home Assistant has not loaded the automation yet - see Settings ▸ System ▸ Logs.' });
            else if (st.state === 'unavailable') lines.push({ ok: false, text: `${st.entity_id} is unavailable: Home Assistant did not accept it - see Settings ▸ System ▸ Logs.` });
            else lines.push({ ok: true, text: `${st.entity_id} is ${st.state} in Home Assistant.` });
        }
        const version = entry.res.intent === 'modify' ? ((r.versions || {})[entry.res.target_net] || {}).latest : 0;
        if (version) lines.push({ ok: true, text: `Saved as version ${version}; the one before stays in 🕘 Versions.` });
        entry.save = { state: lines.every(l => l.ok) ? 'saved' : 'problem', lines };
        this.render(true);
    }

    /** [ADDED v3.67.0] The automation Home Assistant runs for this id, once it shows up after the reload. */
    async _automationState(haId) {
        const end = Date.now() + this.loadWaitMs;
        for (;;) {
            const states = (this.hass && this.hass.states) || {};
            const st = Object.values(states).find(s => s && String(s.entity_id || '').startsWith('automation.')
                && String((s.attributes || {}).id) === String(haId));
            if (st || Date.now() >= end) return st || null;
            await new Promise(r => setTimeout(r, 250));
        }
    }

    _copy(text, btn) {
        const done = () => { btn.textContent = 'Copied'; setTimeout(() => { btn.textContent = 'Copy'; }, 1500); };
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text).then(done, () => this._copyFallback(text, done));
        } else {
            this._copyFallback(text, done);
        }
    }

    _copyFallback(text, done) {
        const ta = h('textarea', { class: 'ai-copy-buffer' });
        ta.value = text;
        this.root.appendChild(ta);
        ta.select();
        try { document.execCommand('copy'); done(); } catch (e) { /* the user can select the text by hand */ }
        ta.remove();
    }

    // ------------------------------------------------------------------ view

    /** @param keep true for an update in place (a tick, a chip): the scroll positions stay. */
    render(keep = false) {
        const oldLog = this.root.querySelector('.ai-log');
        const scroll = { log: oldLog ? oldLog.scrollTop : 0, lists: {} };
        this.root.querySelectorAll('.ai-list[data-role]').forEach(l => { scroll.lists[l.dataset.role] = l.scrollTop; });
        const head = h('div', { class: 'ai-head' },
            h('button', { class: 'sidebar-toggle', title: this.open ? 'Close the AI chat' : 'Open the AI chat',
                onclick: () => this._toggle(), text: this.open ? '▾' : '▸' }),
            h('span', { class: 'grow', text: 'AI Chat' }),
            this.status && this.status.configured
                ? h('span', { class: 'ai-model', title: `${this.status.provider} · ${this.status.model}`,
                    text: this.status.model || this.status.provider }) : null,
            this.open && this.log.length
                ? h('button', { class: 'ha-text-btn ai-new', onclick: () => this._reset(), text: 'New chat' }) : null,
        );
        const body = this.open ? this._body() : null;
        this.root.classList.toggle('open', this.open);
        this._markLayout();
        this.root.replaceChildren(head, ...(body ? [body] : []));
        // [ADDED v3.61.0] Before the log's scroll is set: the room the box takes is the log's.
        this._fitInput(this.root.querySelector('.ai-input'));
        const log = this.root.querySelector('.ai-log');
        if (!log) return;
        if (keep) {
            log.scrollTop = scroll.log;
            this.root.querySelectorAll('.ai-list[data-role]').forEach(l => {
                if (l.dataset.role in scroll.lists) l.scrollTop = scroll.lists[l.dataset.role];
            });
        } else {
            log.scrollTop = log.scrollHeight;
        }
    }

    /** [ADDED v3.61.0] The message box is as tall as what is written, so a long request can be read whole: at
     *  most half the chat (never less than 120px), and beyond that it scrolls. A log that was at its end stays
     *  there. A box that is not laid out yet is left alone; _watchSize fits it once it is. */
    _fitInput(input, pin = false) {
        if (!input || !input.isConnected) return;
        const log = this.root.querySelector('.ai-log');
        const atEnd = pin && log && log.scrollHeight - log.scrollTop - log.clientHeight < 4;
        const body = this.root.querySelector('.ai-body');
        const cap = Math.max(120, Math.floor((body ? body.clientHeight : 0) / 2));
        input.style.height = 'auto';
        if (!input.scrollHeight) { input.style.height = ''; return; }
        const want = input.scrollHeight + input.offsetHeight - input.clientHeight;
        input.style.maxHeight = `${cap}px`;
        input.style.height = `${Math.min(want, cap)}px`;
        input.style.overflowY = want > cap ? 'auto' : 'hidden';
        if (atEnd) log.scrollTop = log.scrollHeight;
    }

    /** [ADDED v3.61.0] A narrower sidebar wraps the text into more lines, and a taller phone sheet gives the box
     *  more room: the box is fitted again whenever the chat changes size. Without ResizeObserver it is still
     *  fitted when the user types and when the chat is drawn. */
    _watchSize() {
        if (typeof ResizeObserver === 'undefined') return;
        let last = '';
        new ResizeObserver(() => {
            const size = `${this.root.clientWidth}x${this.root.clientHeight}`;
            if (size === last) return;
            last = size;
            this._fitInput(this.root.querySelector('.ai-input'), true);
        }).observe(this.root);
    }

    _body() {
        if (this.status && !this.status.configured) {
            return h('div', { class: 'ai-body' }, h('div', { class: 'ai-setup' },
                h('p', { text: 'The AI chat needs a model. Choose one in the LIBI settings:' }),
                h('p', { class: 'ai-path', text: 'Settings ▸ Devices & services ▸ LIBI ▸ Configure' }),
                h('p', { text: 'Local AI (for example Ollama) or a cloud service (Google Gemini, OpenAI).' }),
                h('button', { class: 'ha-text-btn', text: 'Check again',
                    onclick: () => { this.statusAsked = false; this.status = null; this.attach(this.root.parentNode); } }),
            ));
        }
        const log = h('div', { class: 'ai-log' });
        if (!this.log.length) {
            log.appendChild(h('div', { class: 'ai-hint', dir: 'auto',
                text: 'Describe what should happen, for example: "pressing a button turns the living room light on for 10 minutes". You can also ask about the nets on this page, or ask to change one. LIBI shows you the matching devices to pick; nothing is saved until you press SAVE & COMPILE.' }));
            // [ADDED v3.37.0] Privacy: say where the request goes before the first one is sent.
            log.appendChild(h('div', { class: 'ai-note ai-privacy', dir: 'auto', text: this._privacyText() }));
        }
        for (const entry of this.log) log.appendChild(this._entry(entry));
        if (this.plan) log.appendChild(this._planView());
        if (this.busy) log.appendChild(h('div', { class: 'ai-busy', text: this.busy }));

        const input = h('textarea', {
            class: 'ai-input', rows: 2, dir: 'auto', placeholder: 'What should LIBI build?',
            disabled: !!this.busy,
            oninput: e => { this.draft = e.target.value; this._fitInput(e.target, true); },
            onkeydown: e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); this.send(); } },
        });
        input.value = this.draft;
        const send = h('button', { class: 'btn btn-primary ai-send', text: 'Send', disabled: !!this.busy,
            onclick: () => this.send() });
        const share = h('input', { type: 'checkbox', id: 'aiShareNets', checked: this.shareNets,
            onchange: e => this._setShare(e.target.checked) });
        const shareRow = h('label', { class: 'ai-share', for: 'aiShareNets' }, share,
            h('span', { text: 'Share the nets on this page and my helpers with the AI' }));
        return h('div', { class: 'ai-body' }, log, shareRow, h('div', { class: 'ai-compose' }, input, send));
    }

    _entry(entry) {
        if (entry.kind === 'user') return h('div', { class: 'ai-msg user', dir: 'auto', text: entry.text });
        if (entry.kind === 'ai') return h('div', { class: 'ai-msg ai', dir: 'auto', text: entry.text });
        if (entry.kind === 'error') {
            return h('div', { class: 'ai-msg error', dir: 'auto' }, entry.text,
                entry.list && entry.list.length ? h('ul', {}, entry.list.map(t => h('li', { text: t }))) : null);
        }
        return this._resultView(entry);
    }

    _planView() {
        const box = h('div', { class: 'ai-plan' });
        box.appendChild(h('div', { class: 'ai-plan-title', dir: 'auto' },
            h('span', { class: 'ai-level', text: this.plan.level }), ' ',
            this.plan.intent === 'modify' ? `Change: ${this._netLabel(this.plan.target_net)}` : this.plan.name));
        // [ADDED v3.59.0] The model wanted to change a net the user did not name; LIBI made it new logic.
        if (this.plan.forced_new) {
            box.appendChild(h('div', { class: 'ai-note', text: 'This becomes a new NET: a NET is changed only when you name it by its number, for example "update NET 3".' }));
        }
        // [ADDED v3.62.0] A message service the user named that this Home Assistant does not have is said here,
        // before Build, instead of failing every draft that sends to it.
        const gone = this.plan.missing_services || [];
        // [CHANGED v3.66.0] With a phones list, the note is said there, next to the phones to tick instead.
        if (gone.length && !this.plan.roles.some(r => r.phones)) {
            box.appendChild(h('div', { class: 'ai-note warn', dir: 'auto', text: `${gone.join(', ')} ${gone.length === 1 ? 'does' : 'do'} not exist in this Home Assistant, so no message can go there - for example a phone that is no longer registered in the Companion app. The logic leaves ${gone.length === 1 ? 'it' : 'them'} out.` }));
        }
        // [ADDED v3.73.0] The request as LIBI checks the draft against it, one line each.
        const reqs = this.plan.requirements || [];
        if (reqs.length) {
            box.appendChild(h('div', { class: 'ai-reqs' },
                h('div', { class: 'ai-note', text: 'Your request, line by line - LIBI checks the draft against it:' }),
                h('ul', {}, reqs.map(r => h('li', { dir: 'auto', text: r.text })))));
        }
        // [CHANGED v3.82.0] The local variables in one window, first; then the devices, each in its list.
        const variables = this.plan.roles.filter(r => r.variable);
        if (variables.length) box.appendChild(this._variablesView(variables));
        for (const role of this.plan.roles.filter(r => !r.variable)) box.appendChild(this._roleView(role));
        const questions = this.plan.questions || [];
        for (const q of questions.filter(x => !x.libi)) box.appendChild(this._questionView(q));
        // [ADDED v3.80.0] LIBI's own questions, asked for every automation that switches a device, answered by its choices.
        const own = questions.filter(x => x.libi);
        if (own.length) {
            box.appendChild(h('div', { class: 'ai-libi-asks' },
                h('div', { class: 'ai-role-head' }, h('strong', { text: 'LIBI asks' })),
                h('div', { class: 'ai-note', text: 'For every automation that switches a device. LIBI writes what you answer into the logic and checks it in the draft.' }),
                own.map(q => this._questionView(q))));
        }
        const unanswered = own.filter(q => !(q.choices || []).includes(this.answers[q.id]));
        const missing = this.plan.roles.filter(r => !r.optional && !(this.selections[r.id] && this.selections[r.id].size));
        if (unanswered.length) box.appendChild(h('div', { class: 'ai-note warn ai-unanswered', text: `Answer LIBI's ${unanswered.length === 1 ? 'question' : `${unanswered.length} questions`} above to build.` }));
        // [ADDED v3.82.0] A variable with nothing chosen holds Build back, and the chat says what to do.
        if (missing.some(r => r.variable)) box.appendChild(h('div', { class: 'ai-note warn ai-vars-unset', text: 'Create the new local variables above, or pick a helper for each, to build.' }));
        box.appendChild(h('button', {
            class: 'btn btn-primary ai-build', disabled: !!this.busy || missing.length > 0 || unanswered.length > 0,
            title: missing.length ? `Pick: ${missing.map(r => r.label).join(', ')}` : unanswered.length ? "Answer LIBI's questions first" : 'Write the logic',
            text: 'Build', onclick: () => this.build(),
        }));
        return box;
    }

    _roleView(role) {
        const cand = this.candidates[role.id] || { items: [], exact: false };
        const sel = this.selections[role.id] || (this.selections[role.id] = new Set());
        const filter = (this.filters[role.id] || '').toLowerCase();
        const wrap = h('div', { class: 'ai-role' });
        wrap.appendChild(h('div', { class: 'ai-role-head', dir: 'auto' },
            h('strong', { text: role.label }),
            role.optional ? h('span', { class: 'ai-current ai-optional', text: 'optional' }) : null,
            h('span', { class: 'ai-count', text: `${sel.size} / ${cand.items.length}` })));
        // [CHANGED v3.60.0] A helper the user's message names has an optional role of its own too.
        // [CHANGED v3.62.0] And a phone role when the message already names the notify services to use.
        // [ADDED v3.64.0] The phones LIBI offers when the message names notify services.
        if (role.phones) {
            // [CHANGED v3.81.0] Or the phones LIBI offers for its own messages, when the plan has none.
            // [CHANGED v3.83.0] Or the phones a request whose point is a message goes to, when it names none.
            wrap.appendChild(h('div', { class: `ai-note${role.offered ? ' ai-phones-offered' : role.for_message ? ' ai-phones-message' : ''}`, text: role.offered
                ? "Optional: the phones LIBI's own messages go to - when it starts, when it ends, a device offline, a low battery. With none ticked they go to Home Assistant's notifications, and nothing is spoken."
                : role.for_message ? 'Tick the phones the message goes to. A spoken message is read aloud by the phone - the Home Assistant app on Android.'
                : 'The phones your message names are ticked. Tick another phone in place of one that does not exist.' }));
            // [ADDED v3.66.0] A named phone that does not exist, said here where the replacement is ticked.
            const gone = this.plan.missing_services || [];
            if (gone.length) {
                wrap.appendChild(h('div', { class: 'ai-note warn ai-phones-missing', dir: 'auto', text: `${gone.join(', ')} ${gone.length === 1 ? 'does' : 'do'} not exist in this Home Assistant - ${gone.length === 1 ? 'a phone' : 'phones'} no longer in the Companion app? Tick the phone that should get the message instead.` }));
            }
        }
        // [CHANGED v3.82.0] A schedule that gave way, a helper the message names that is gone, and a helper to make are
        // local variables, said in their window (_variableRow); a role here is a device.
        if (role.optional && !role.offered) wrap.appendChild(h('div', { class: 'ai-note', text: role.message
            ? 'Optional: your message names the notify services to use. Pick a phone here only to add one.'
            : 'A device of the NET you named. Pick it if the new logic should use it.' }));
        if (!cand.items.length) {
            wrap.appendChild(h('div', { class: 'ai-note', text: `Nothing of type ${role.domains.join(', ') || '?'} was found in Home Assistant.` }));
            return wrap;
        }
        if (!cand.exact) wrap.appendChild(h('div', { class: 'ai-note warn', text: 'No exact match. These are the closest devices.' }));
        if (cand.hidden_used) wrap.appendChild(h('div', { class: 'ai-note', text: `${cand.hidden_used} helper${cand.hidden_used === 1 ? '' : 's'} used by other automations or scripts ${cand.hidden_used === 1 ? 'is' : 'are'} not listed.` }));
        if (cand.items.length > 8) {
            const f = h('input', { class: 'ai-filter', type: 'search', placeholder: 'Filter', dir: 'auto',
                oninput: e => { this.filters[role.id] = e.target.value; this._refreshList(role, list); } });
            f.value = this.filters[role.id] || '';
            wrap.appendChild(f);
        }
        const list = h('div', { class: 'ai-list', 'data-role': role.id });
        wrap.appendChild(list);
        this._fillList(role, list, filter);
        const all = h('button', { class: 'ha-text-btn ai-all', text: 'Select all shown', onclick: () => {
            list.querySelectorAll('input[type=checkbox]').forEach(cb => { cb.checked = true; sel.add(cb.value); });
            this.render(true);
        } });
        const none = h('button', { class: 'ha-text-btn ai-all', text: 'Clear', onclick: () => { sel.clear(); this.render(true); } });
        wrap.appendChild(h('div', { class: 'ai-role-acts' }, all, none));
        return wrap;
    }

    _refreshList(role, list) {
        list.replaceChildren();
        this._fillList(role, list, (this.filters[role.id] || '').toLowerCase());
    }

    _fillList(role, list, filter) {
        const cand = this.candidates[role.id] || { items: [] };
        const sel = this.selections[role.id];
        for (const item of cand.items) {
            const hay = `${item.name} ${item.entity_id} ${item.area}`.toLowerCase();
            if (filter && !hay.includes(filter)) continue;
            const cb = h('input', { type: 'checkbox', value: item.entity_id, checked: sel.has(item.entity_id),
                onchange: e => {
                    if (e.target.checked) sel.add(item.entity_id); else sel.delete(item.entity_id);
                    this.render(true);
                } });
            list.appendChild(h('label', { class: 'ai-item' }, cb,
                h('span', { class: 'ai-item-text' },
                    h('span', { class: 'ai-item-name', dir: 'auto' }, item.name || item.entity_id,
                        item.current ? h('span', { class: 'ai-current', text: 'current' }) : null,
                        item.exists ? h('span', { class: 'ai-current ai-on-canvas', text: 'exists', title: 'This helper already exists and nothing else uses it' }) : null,
                        // [ADDED v3.49.0] Used by a net on this page: "NET 1 · Valve garden".
                        item.on_canvas ? h('span', { class: 'ai-current ai-on-canvas', text: item.on_canvas.split(' · ')[0], title: `Used in ${item.on_canvas}` }) : null,
                        // [ADDED v3.60.0] The user's message names this helper.
                        item.named ? h('span', { class: 'ai-current ai-on-canvas', text: 'named', title: role.phones ? 'Your message names this phone' : 'Your message names this helper' }) : null,
                        // [ADDED v3.66.0] Whose phone it is.
                        item.owner ? h('span', { class: 'ai-current ai-on-canvas ai-owner', text: item.owner, title: `Belongs to ${item.owner}` }) : null,
                        item.created ? h('span', { class: 'ai-current', text: 'new' }) : null),
                    h('span', { class: 'ai-item-id', text: `${item.entity_id}${item.device ? ' · ' + item.device : ''}${item.area ? ' · ' + item.area : ''}` }),
                    // [ADDED v3.60.0] A named helper is listed although others use it; the user is told who.
                    item.used_by && item.used_by.length ? h('span', { class: 'ai-note warn', dir: 'auto',
                        text: `Also used by ${item.used_by.join(', ')}: setting it changes it there too.` }) : null)));
        }
    }

    _questionView(q) {
        const wrap = h('div', { class: `ai-question${q.libi ? ' ai-libi-question' : ''}`, 'data-question': q.id },
            h('div', { class: 'ai-q-text', dir: 'auto', text: q.text }));
        // [ADDED v3.80.0] LIBI's own questions say what their answer does.
        if (q.note) wrap.appendChild(h('div', { class: 'ai-note ai-q-note', dir: 'auto', text: q.note }));
        if (q.choices && q.choices.length) {
            const row = h('div', { class: 'ai-choices' });
            for (const c of q.choices) {
                row.appendChild(h('button', { class: `ai-chip${this.answers[q.id] === c ? ' on' : ''}`, dir: 'auto', text: c,
                    onclick: () => { this.answers[q.id] = c; this._applyAnswer(q); this.render(true); } }));
            }
            wrap.appendChild(row);
        }
        // [CHANGED v3.80.0] Not for LIBI's own questions: LIBI reads their answer by its choices.
        if (q.libi) return wrap;
        const free = h('input', { class: 'ai-filter', type: 'text', dir: 'auto',
            placeholder: q.choices && q.choices.length ? 'Or write your own answer' : 'Your answer',
            onchange: e => { if (e.target.value.trim()) this.answers[q.id] = e.target.value.trim(); else delete this.answers[q.id]; } });
        if (this.answers[q.id] && !(q.choices || []).includes(this.answers[q.id])) free.value = this.answers[q.id];
        wrap.appendChild(free);
        return wrap;
    }

    /** [ADDED v3.73.0] Each line of the request: ✓ where LIBI saw it in the logic, ✗ where the logic does not do it, and
     *  • for a line only the AI's own word places, with what the AI says - each with the rung that does it. A line
     *  takes the direction of its text, so the mark stands where a Hebrew line starts too, and the notes under it
     *  keep that side: their English is isolated (bdi), not a paragraph of its own direction. */
    _checklistView(res) {
        const items = res.checklist || [];
        if (!items.length) return null;
        const missing = items.filter(i => i.ok === false).length;
        const list = h('ul', { class: 'ai-check-list' });
        for (const item of items) {
            const state = item.ok === false ? 'missing' : item.ok === true ? 'ok' : 'unchecked';
            const where = item.kind === 'card' ? 'the card below' : item.rung ? `rung ${item.rung}` : '';
            const tail = state === 'missing' ? `missing: ${item.missing || 'not in the logic'}`
                : [where, state === 'ok' ? 'checked by LIBI' : 'not checked by LIBI'].filter(Boolean).join(' · ');
            list.appendChild(h('li', { class: `ai-check ${state}`, dir: 'auto' },
                h('span', { class: 'ai-check-mark', text: { missing: '✗', ok: '✓' }[state] || '•' }),
                h('span', { class: 'ai-check-text' },
                    h('span', { text: item.text }),
                    state === 'unchecked' && item.how ? h('span', { class: 'ai-check-how' }, h('bdi', { text: `the AI: ${item.how}` })) : null,
                    h('span', { class: 'ai-check-where' }, h('bdi', { text: tail })))));
        }
        return h('div', { class: `ai-checklist${missing ? ' missing' : ''}` },
            h('div', { class: 'ai-checklist-head', text: missing
                ? `Your request, line by line: ${missing} of ${items.length} lines ${missing === 1 ? 'is' : 'are'} not in the logic`
                : 'Your request, line by line' }), list);
    }

    _resultView(entry) {
        const res = entry.res;
        const box = h('div', { class: 'ai-result' });
        if (res.reply) box.appendChild(h('div', { class: 'ai-msg ai', dir: 'auto', text: res.reply }));
        // [ADDED v3.73.0] The request line by line, each with the rung that does it.
        const checklist = this._checklistView(res);
        if (checklist) box.appendChild(checklist);
        if (res.sensitive && res.sensitive.length) {
            box.appendChild(h('div', { class: 'ai-note danger', dir: 'auto',
                text: `This draft controls security-sensitive devices: ${res.sensitive.join(', ')}. Review every rung before you save it.` }));
        }
        if (res.round_trip && !res.round_trip.ok) {
            // [CHANGED v3.40.0] Said before that such a draft is saved unchanged, which was not true: the
            // ladder drawing is what is saved. The user is told so and the issues are listed.
            box.appendChild(h('div', { class: 'ai-note danger', dir: 'auto' },
                'The ladder drawing cannot hold all of this logic, so saving it would change it. Check the YAML, or copy it into the Home Assistant automation editor instead.',
                h('ul', {}, (res.round_trip.issues || []).slice(0, 5).map(t => h('li', { text: t })))));
        }
        for (const n of res.notes || []) box.appendChild(h('div', { class: 'ai-note', dir: 'auto', text: n }));
        // [ADDED v3.62.0] What LIBI's check found in the AI's earlier answers, which the AI then corrected.
        if (res.repaired && res.repaired.length) {
            box.appendChild(h('div', { class: 'ai-note ai-repaired', dir: 'auto' },
                `LIBI checked the AI's draft and had it corrected (${res.tries} answers):`,
                h('ul', {}, res.repaired.slice(0, 5).map(t => h('li', { text: t })))));
        }
        const yamlBox = h('details', { class: 'ai-yaml' }, h('summary', { text: 'YAML' }), h('pre', { text: res.yaml || '' }));
        box.appendChild(yamlBox);
        if (res.intent === 'modify' && res.target_net) {
            const label = this._netLabel(res.target_net);
            // [CHANGED v3.59.0] A change is a new version of the net, and the version that runs now stays in
            // Versions. A net with no saved version could not be brought back, so it is not replaced.
            const ver = (this.panel._versions || {})[res.target_net];
            const next = ver && ver.count ? (Number(ver.latest) || 0) + 1 : 0;
            // [CHANGED v3.67.0] Replacing saves and compiles the new version at once (see _place).
            box.appendChild(h('button', {
                class: 'btn btn-primary ai-replace', disabled: !!entry.added || !next,
                text: entry.added === 'replaced' ? `${label} was replaced with version ${entry.version}`
                    : next ? `Replace ${label} - becomes version ${next}${this._autoSaves(res) ? ', saved and compiled' : ''}` : `Replace ${label}`,
                onclick: () => this._place(entry, 'replace', next),
            }));
            box.appendChild(next
                ? h('div', { class: 'ai-note ai-version-note', text: `Version ${ver.active} stays in 🕘 Versions, so you can go back to it.` })
                : h('div', { class: 'ai-note warn ai-version-note', text: `${label} has no saved version yet, so it could not be brought back after a replace. Save the project first, or add this as a new NET.` }));
        }
        // [CHANGED v3.59.0] New logic goes into the next NET, after the last one; the button says which.
        const position = entry.addedAs || (this.panel.core.nets || []).length + 1;
        // [CHANGED v3.67.0] Adding saves and compiles the NET at once and checks it (see _place).
        box.appendChild(h('button', {
            class: `btn ${res.intent === 'modify' ? 'btn-ghost' : 'btn-primary'} ai-add`, disabled: !!entry.added,
            text: entry.added === true ? `Added as NET ${position}`
                : `Add as NET ${position}${this._autoSaves(res) ? ', save and compile' : ' to the canvas'}`,
            onclick: () => this._place(entry, 'add'),
        }));
        // [ADDED v3.67.0] What the save did, line by line: written, reloaded, running, read back - or why it was not.
        if (entry.save) {
            const status = h('div', { class: `ai-save ai-save-${entry.save.state}`, dir: 'auto' });
            if (entry.save.state === 'saving') status.appendChild(h('div', { class: 'ai-note', text: 'Saving and compiling…' }));
            for (const line of entry.save.lines || []) {
                status.appendChild(h('div', { class: `ai-note ${line.ok ? 'ok' : entry.save.state === 'failed' ? 'danger' : 'warn'}`,
                    text: `${line.ok ? '✓' : '⚠'} ${line.text}` }));
            }
            box.appendChild(status);
        }
        if (res.card_yaml) {
            const copy = h('button', { class: 'ha-text-btn', text: 'Copy' });
            copy.addEventListener('click', () => this._copy(res.card_yaml, copy));
            box.appendChild(h('div', { class: 'ai-card' },
                h('div', { class: 'ai-card-head' }, h('strong', { text: 'Dashboard card' }), copy),
                h('div', { class: 'ai-note', text: 'Open a dashboard, Edit ▸ Add card ▸ Manual, and paste this. Later too: ⋮ ▸ Dashboard card on the NET.' }),
                h('pre', { text: res.card_yaml })));
        }
        return box;
    }
}
