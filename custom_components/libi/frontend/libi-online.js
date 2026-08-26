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
 * LIBI - Online Engine
 * v3.4.0
 */
// [ADDED v3.4.0 | 2026-08-20] Purpose: Renamed LadderOnline to LibiOnline.
const ON_STATES = new Set(['on', 'true', 'home', 'open', 'unlocked', 'active', 'detected', 'playing']);
const PULSE_MS = 4000;

export class LibiOnline {
    constructor() {
        this.enabled = false;
        this.memory = new Map();   // elId -> { value, prev, changedAt }
        this.netMemory = new Map(); // netId -> { lastTriggered, changedAt }
        this.result = new Map();   // elId -> { power, value, prev, fresh }
        this.rungPower = new Map(); // rungId -> bool
    }

    stateOf(hass, entityId) {
        if (!hass || !entityId) return null;
        const st = hass.states ? hass.states[entityId] : null;
        return st ? st.state : null;
    }

    numberOf(hass, value) {
        if (value === undefined || value === null || value === '') return NaN;
        const asText = String(value);
        if (asText.includes('.') && !asText.match(/^-?\d+(\.\d+)?$/)) {
            const st = this.stateOf(hass, asText);
            return st === null ? NaN : parseFloat(st);
        }
        return parseFloat(asText);
    }

    valueOf(hass, value) {
        const asText = String(value === undefined || value === null ? '' : value);
        if (asText.includes('.') && !asText.includes(' ') && isNaN(Number(asText))) {
            const st = this.stateOf(hass, asText);
            return st === null ? undefined : st;
        }
        return asText;
    }

    evaluate(el, hass, now) {
        const t = el.type || '';
        let power = null;
        let value;

        if (t.startsWith('contact')) {
            const st = this.stateOf(hass, el.label);
            value = st;
            if (st !== null) {
                const on = ON_STATES.has(String(st).toLowerCase());
                power = (t === 'contact_nc' || t === 'contact_n') ? !on : on;
            }
        } else if (t.startsWith('coil')) {
            const st = this.stateOf(hass, el.label);
            value = st;
            if (st !== null) power = ON_STATES.has(String(st).toLowerCase());
        } else if (t === 'cmp_rng') {
            const a = this.numberOf(hass, el.sourceA);
            const min = this.numberOf(hass, el.sourceB);
            const max = this.numberOf(hass, el.sourceC);
            value = isNaN(a) ? this.valueOf(hass, el.sourceA) : a;
            if (!isNaN(a) && !isNaN(min) && !isNaN(max)) power = a > min && a < max;
        } else if (t.startsWith('cmp')) {
            const left = String(el.sourceA || '');
            if (left === 'time' || left === 'weekday' || left === 'datetime' || left === 'sun') {
                value = left === 'time' ? new Date().toTimeString().slice(0, 8) : left;
            } else {
                const a = this.numberOf(hass, el.sourceA);
                const b = this.numberOf(hass, el.sourceB);
                const av = this.valueOf(hass, el.sourceA);
                const bv = this.valueOf(hass, el.sourceB);
                value = av;
                if (!isNaN(a) && !isNaN(b)) {
                    if (t === 'cmp_gt') power = a > b;
                    else if (t === 'cmp_lt') power = a < b;
                    else if (t === 'cmp_ge') power = a >= b;
                    else if (t === 'cmp_le') power = a <= b;
                    else if (t === 'cmp_eq') power = a === b;
                    else if (t === 'cmp_ne') power = a !== b;
                } else if (av !== undefined && bv !== undefined) {
                    if (t === 'cmp_eq') power = String(av) === String(bv);
                    else if (t === 'cmp_ne') power = String(av) !== String(bv);
                }
            }
        } else if (t === 'move' || t === 'notify' || t.startsWith('math') || t === 'ctu') {
            const st = this.stateOf(hass, el.target || el.source);
            value = st === null ? undefined : st;
            power = true; 
        } else if (t === 'timer_ton' || t === 'timer_toff' || t === 'wait') {
            power = true;
        }

        this.remember(el.id, value, now);
        return { power, value };
    }

    remember(elId, value, now) {
        const cell = this.memory.get(elId);
        if (!cell) {
            this.memory.set(elId, { value, prev: undefined, changedAt: 0 });
            return;
        }
        if (value !== undefined && String(cell.value) !== String(value)) {
            this.memory.set(elId, { value, prev: cell.value, changedAt: now });
        }
    }

    evaluateSeries(elements, hass, now) {
        let flow = true;
        let known = true;
        for (const el of elements || []) {
            let res;
            if (el.type === 'parallel') {
                res = { power: this.evaluateParallel(el, hass, now) };
            } else if (el.type === 'repeat') {
                (el.sequence || []).forEach(child => this.evaluateSeries([child], hass, now));
                res = { power: true };
            } else {
                res = this.evaluate(el, hass, now);
            }
            const mem = this.memory.get(el.id) || {};
            this.result.set(el.id, {
                power: res.power,
                value: mem.value,
                prev: mem.prev,
                fresh: mem.changedAt ? (now - mem.changedAt) < PULSE_MS : false
            });
            if (res.power === null) known = false;
            else if (res.power === false) flow = false;
        }
        return flow && known ? true : (known ? false : null);
    }

    evaluateParallel(el, hass, now) {
        let any = false;
        let known = true;
        for (const branch of el.branches || []) {
            const res = this.evaluateSeries(branch, hass, now);
            if (res === null) known = false;
            else if (res === true) any = true;
        }
        if (any) return true;
        return known ? false : null;
    }

    update(nets, hass) {
        const now = Date.now();
        this.result.clear();
        this.rungPower.clear();
        for (const net of nets || []) {
            let netLive = false;
            for (const rung of net.rungs || []) {
                const flow = this.evaluateSeries(rung.elements, hass, now);
                this.rungPower.set(rung.id, flow);
                if (flow === true) netLive = true;
            }
            const ent = net.ha_id ? this.findAutomationEntity(hass, net) : null;
            if (ent) {
                const last = ent.attributes && ent.attributes.last_triggered;
                const cell = this.netMemory.get(net.id) || {};
                if (last && cell.lastTriggered !== last) this.netMemory.set(net.id, { lastTriggered: last, changedAt: now });
            }
            this.netMemory.set(net.id + ':live', { live: netLive });
        }
    }

    findAutomationEntity(hass, net) {
        if (!hass || !hass.states) return null;
        for (const key of Object.keys(hass.states)) {
            if (!key.startsWith('automation.')) continue;
            const st = hass.states[key];
            if (st.attributes && String(st.attributes.id) === String(net.ha_id)) return st;
        }
        return null;
    }

    lastRunText(netId) {
        const cell = this.netMemory.get(netId);
        if (!cell || !cell.lastTriggered) return '';
        const then = new Date(cell.lastTriggered);
        if (isNaN(then.getTime())) return '';
        const secs = Math.max(0, Math.round((Date.now() - then.getTime()) / 1000));
        if (secs < 60) return `last run ${secs}s ago`;
        if (secs < 3600) return `last run ${Math.round(secs / 60)}m ago`;
        if (secs < 86400) return `last run ${Math.round(secs / 3600)}h ago`;
        return `last run ${then.toLocaleDateString()}`;
    }

    paint(root, nets, hass) {
        if (!root) return;
        root.querySelectorAll('.libi-el').forEach(node => {
            node.classList.remove('live-on', 'live-off', 'live-unknown', 'live-fresh');
            const badge = node.querySelector('.live-val');
            if (badge) badge.remove();
        });
        root.querySelectorAll('.rung').forEach(node => node.classList.remove('rung-live'));
        root.querySelectorAll('.net-live-note').forEach(node => node.remove());

        if (!this.enabled) return;
        this.update(nets, hass);

        root.querySelectorAll('.libi-el').forEach(node => {
            const id = node.getAttribute('data-eid');
            const res = id ? this.result.get(id) : null;
            if (!res) return;
            node.classList.add(res.power === true ? 'live-on' : res.power === false ? 'live-off' : 'live-unknown');
            if (res.fresh) node.classList.add('live-fresh');
            if (res.value !== undefined && res.value !== null && String(res.value) !== '') {
                const badge = document.createElement('div');
                badge.className = 'live-val';
                badge.innerHTML = `<span class="live-now">${this._esc(res.value)}</span>` +
                    (res.prev !== undefined && res.prev !== null && String(res.prev) !== String(res.value)
                        ? `<span class="live-prev">was ${this._esc(res.prev)}</span>` : '');
                node.appendChild(badge);
            }
        });

        for (const net of nets || []) {
            for (const rung of net.rungs || []) {
                if (this.rungPower.get(rung.id) !== true) continue;
                const rungNode = root.querySelector(`.rung[data-rid="${rung.id}"]`);
                if (rungNode) rungNode.classList.add('rung-live');
            }
            const text = this.lastRunText(net.id);
            if (!text) continue;
            const netNode = root.querySelector(`.net[data-nid="${net.id}"]`);
            const wrap = netNode ? netNode.querySelector('.net-hdr-l') : null;
            if (wrap) {
                const note = document.createElement('span');
                note.className = 'net-live-note';
                note.textContent = text;
                wrap.appendChild(note);
            }
        }
    }

    _esc(v) {
        return String(v === undefined || v === null ? '' : v)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }
}