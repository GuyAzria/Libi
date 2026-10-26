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
 * v3.36.0
 */
// [ADDED v3.36.0 | 2026-10-26] Purpose: The AI chat under the Inspector. The user describes the
//   logic, picks the devices from lists LIBI found in Home Assistant (several per role), answers the
//   questions, and gets a DRAFT net to add to the canvas. Nothing here writes to Home Assistant; the
//   net is saved by the ordinary SAVE & COMPILE.
//
// SECURITY: every text in here - the model's replies, device names, YAML - is untrusted and is put
// on the page with textContent or as a text node, never as HTML (CLAUDE.md RULE 15).

const OPEN_KEY = 'libi_ai_open';

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
        this.messages = [];      // what the model sees: {role, content}
        this.log = [];           // what the user sees
        this.plan = null;
        this.candidates = {};
        this.selections = {};    // role id -> Set of entity ids
        this.answers = {};
        this.filters = {};
        this.draft = '';
        this.busy = '';
        this.render();
    }

    _readOpen() {
        try { return localStorage.getItem(OPEN_KEY) !== '0'; } catch (e) { return true; }
    }

    get hass() { return this.panel._hass; }

    /** Called after every render of the panel: the chat keeps its own DOM and is moved, not rebuilt. */
    attach(mount) {
        if (!mount) return;
        if (this.root.parentNode !== mount) mount.appendChild(this.root);
        mount.classList.toggle('ai-open', this.open);
        if (!this.statusAsked && this.hass && this.hass.connection) {
            this.statusAsked = true;
            this._ws({ type: 'libi/ai_status' })
                .then(s => { this.status = s; this.render(); })
                .catch(() => { this.status = { configured: false }; this.render(); });
        }
    }

    _ws(msg) { return this.hass.connection.sendMessagePromise(msg); }

    _toggle() {
        this.open = !this.open;
        try { localStorage.setItem(OPEN_KEY, this.open ? '1' : '0'); } catch (e) { /* not stored */ }
        this.render();
    }

    _reset() {
        this.messages = []; this.log = []; this.plan = null; this.candidates = {};
        this.selections = {}; this.answers = {}; this.filters = {}; this.busy = '';
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
            const res = await this._ws({ type: 'libi/ai_plan', messages: this.messages });
            const plan = res.plan;
            const kept = {};
            for (const role of plan.roles) {
                const old = this.selections[role.id];
                const items = ((res.candidates || {})[role.id] || {}).items || [];
                const ids = new Set(items.map(i => i.entity_id));
                kept[role.id] = new Set(old ? [...old].filter(e => ids.has(e)) : []);
                // One exact match is almost certainly the one; it is ticked but can be unticked.
                const cand = (res.candidates || {})[role.id] || {};
                if (!kept[role.id].size && cand.exact && items.length === 1) kept[role.id].add(items[0].entity_id);
            }
            this.selections = kept;
            this.plan = plan;
            this.candidates = res.candidates || {};
            this.answers = Object.fromEntries((plan.questions || [])
                .filter(q => q.id in this.answers).map(q => [q.id, this.answers[q.id]]));
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
        this.busy = 'Writing the logic…';
        this.render();
        const selections = Object.fromEntries(Object.entries(this.selections).map(([k, v]) => [k, [...v]]));
        try {
            const res = await this._ws({
                type: 'libi/ai_build', messages: this.messages, plan: this.plan,
                selections, answers: this.answers,
            });
            if (res.ok) {
                this.messages.push({ role: 'assistant', content: res.reply || 'Built.' });
                this.log.push({ kind: 'result', res, added: false });
                this.plan = null;
            } else {
                this.log.push({ kind: 'error', text: 'The draft was not accepted:', list: res.errors || [] });
            }
        } catch (err) {
            this.log.push({ kind: 'error', text: this._errText(err) });
        }
        this.busy = '';
        this.render();
    }

    _errText(err) {
        if (err && err.code === 'not_configured') return 'AI is not set up yet.';
        return (err && err.message) ? err.message : String(err);
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
        // The panel's render only moves this DOM, so the chat redraws itself: the button must show
        // at once that the net is on the canvas, or it could be added twice.
        this.render(true);
        this.panel._render();
        const el = this.panel.shadowRoot && this.panel.shadowRoot.querySelector(`[data-nid="${CSS.escape(net.id)}"]`);
        if (el && el.scrollIntoView) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
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
        if (this.root.parentNode) this.root.parentNode.classList.toggle('ai-open', this.open);
        this.root.replaceChildren(head, ...(body ? [body] : []));
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
                text: 'Describe what should happen, for example: "pressing a button turns the living room light on for 10 minutes". LIBI shows you the matching devices to pick; nothing is saved until you press SAVE & COMPILE.' }));
        }
        for (const entry of this.log) log.appendChild(this._entry(entry));
        if (this.plan) log.appendChild(this._planView());
        if (this.busy) log.appendChild(h('div', { class: 'ai-busy', text: this.busy }));

        const input = h('textarea', {
            class: 'ai-input', rows: 2, dir: 'auto', placeholder: 'What should LIBI build?',
            disabled: !!this.busy,
            oninput: e => { this.draft = e.target.value; },
            onkeydown: e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); this.send(); } },
        });
        input.value = this.draft;
        const send = h('button', { class: 'btn btn-primary ai-send', text: 'Send', disabled: !!this.busy,
            onclick: () => this.send() });
        return h('div', { class: 'ai-body' }, log, h('div', { class: 'ai-compose' }, input, send));
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
            h('span', { class: 'ai-level', text: this.plan.level }), ' ', this.plan.name));
        for (const role of this.plan.roles) box.appendChild(this._roleView(role));
        for (const q of this.plan.questions || []) box.appendChild(this._questionView(q));
        const missing = this.plan.roles.filter(r => !(this.selections[r.id] && this.selections[r.id].size));
        box.appendChild(h('button', {
            class: 'btn btn-primary ai-build', disabled: !!this.busy || missing.length > 0,
            title: missing.length ? `Pick: ${missing.map(r => r.label).join(', ')}` : 'Write the logic',
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
            h('span', { class: 'ai-count', text: `${sel.size} / ${cand.items.length}` })));
        if (!cand.items.length) {
            wrap.appendChild(h('div', { class: 'ai-note', text: `Nothing of type ${role.domains.join(', ') || '?'} was found in Home Assistant.` }));
            return wrap;
        }
        if (!cand.exact) wrap.appendChild(h('div', { class: 'ai-note warn', text: 'No exact match. These are the closest devices.' }));
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
                    h('span', { class: 'ai-item-name', dir: 'auto', text: item.name || item.entity_id }),
                    h('span', { class: 'ai-item-id', text: `${item.entity_id}${item.area ? ' · ' + item.area : ''}` }))));
        }
    }

    _questionView(q) {
        const wrap = h('div', { class: 'ai-question' }, h('div', { class: 'ai-q-text', dir: 'auto', text: q.text }));
        if (q.choices && q.choices.length) {
            const row = h('div', { class: 'ai-choices' });
            for (const c of q.choices) {
                row.appendChild(h('button', { class: `ai-chip${this.answers[q.id] === c ? ' on' : ''}`, dir: 'auto', text: c,
                    onclick: () => { this.answers[q.id] = c; this.render(true); } }));
            }
            wrap.appendChild(row);
        }
        const free = h('input', { class: 'ai-filter', type: 'text', dir: 'auto',
            placeholder: q.choices && q.choices.length ? 'Or write your own answer' : 'Your answer',
            onchange: e => { if (e.target.value.trim()) this.answers[q.id] = e.target.value.trim(); else delete this.answers[q.id]; } });
        if (this.answers[q.id] && !(q.choices || []).includes(this.answers[q.id])) free.value = this.answers[q.id];
        wrap.appendChild(free);
        return wrap;
    }

    _resultView(entry) {
        const res = entry.res;
        const box = h('div', { class: 'ai-result' });
        if (res.reply) box.appendChild(h('div', { class: 'ai-msg ai', dir: 'auto', text: res.reply }));
        if (res.sensitive && res.sensitive.length) {
            box.appendChild(h('div', { class: 'ai-note danger', dir: 'auto',
                text: `This draft controls security-sensitive devices: ${res.sensitive.join(', ')}. Review every rung before you save it.` }));
        }
        if (res.round_trip && !res.round_trip.ok) {
            box.appendChild(h('div', { class: 'ai-note warn', text: 'Part of this logic cannot be drawn exactly as ladder. It is kept as it is and saved unchanged.' }));
        }
        for (const n of res.notes || []) box.appendChild(h('div', { class: 'ai-note', dir: 'auto', text: n }));
        const yamlBox = h('details', { class: 'ai-yaml' }, h('summary', { text: 'YAML' }), h('pre', { text: res.yaml || '' }));
        box.appendChild(yamlBox);
        box.appendChild(h('button', {
            class: 'btn btn-primary ai-add', disabled: entry.added,
            text: entry.added ? 'Added to the canvas - press SAVE & COMPILE to write it' : 'Add to the canvas as a new NET',
            onclick: () => this._addToCanvas(entry),
        }));
        if (res.card_yaml) {
            const copy = h('button', { class: 'ha-text-btn', text: 'Copy' });
            copy.addEventListener('click', () => this._copy(res.card_yaml, copy));
            box.appendChild(h('div', { class: 'ai-card' },
                h('div', { class: 'ai-card-head' }, h('strong', { text: 'Dashboard card' }), copy),
                h('div', { class: 'ai-note', text: 'Open a dashboard, Edit ▸ Add card ▸ Manual, and paste this.' }),
                h('pre', { text: res.card_yaml })));
        }
        return box;
    }
}
