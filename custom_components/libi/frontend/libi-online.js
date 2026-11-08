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
 * v3.94.0
 */
// [CHANGED v3.93.0 | 2026-11-06] Purpose: Online as a PLC's online view and tracer - the user's request. Everything is
//   kept per NET (two NETs opened from Home Assistant share the ids r1, e3: one was drawn with the other's states). A
//   block whose entity is unavailable, unknown or gone says so; a comparison shows IN1 and IN2 (the clock now and the
//   time it waits for); a TON counts down - the for of a trigger from the entity's last change, a delay from the step of
//   the run Home Assistant is in. The last real run, from Home Assistant's own trace, is drawn on each block (src: where
//   the block is in the YAML). Simulate: FORCE TRUE / FALSE on a block, and a forced trigger runs the NET in the panel
//   only - each condition, each action that would run, each TON counting down - nothing is sent to Home Assistant.
// [CHANGED v3.94.0 | 2026-11-07] Purpose: The user's screenshot (2026-11-07): the mark of the last run was a grey circle
//   half outside its block, read as a button that did nothing. It is a line under the block now, in words - RUN ✓ true,
//   RUN – not reached, SIM ⏳ 00:00:03 - below the Trigger label, which hid IN1. A run Home Assistant started with no
//   trigger says so. What a real run may reach is checked by LIBI's backend now (online.py), from Home Assistant.
const ON_STATES = new Set(['on', 'true', 'home', 'open', 'unlocked', 'active', 'detected', 'playing']);
const PULSE_MS = 4000;
const DAY_IDS = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat'];  // Date.getDay() order, written as a CMP DAY's days
const ENTITY_ID = /^[a-z_]+\.[a-z0-9_]+$/;

/** "hh:mm:ss", "mm:ss" or seconds as a number of seconds; NaN for what is not a fixed time (a template). */
export function secondsOf(text) {
    if (text && typeof text === 'object') {
        const n = (k) => Number(text[k] || 0);
        return n('days') * 86400 + n('hours') * 3600 + n('minutes') * 60 + n('seconds') + n('milliseconds') / 1000;
    }
    const t = String(text === undefined || text === null ? '' : text).trim();
    if (/^\d+(\.\d+)?$/.test(t)) return Number(t);
    const m = t.match(/^(\d+):(\d{1,2})(?::(\d{1,2}(?:\.\d+)?))?$/);
    if (!m) return NaN;
    return m[3] === undefined ? Number(m[1]) * 60 + Number(m[2]) : Number(m[1]) * 3600 + Number(m[2]) * 60 + Number(m[3]);
}

/** Seconds as "hh:mm:ss". */
export function clockOf(seconds) {
    const s = Math.max(0, Math.ceil(Number(seconds) || 0));
    const p = (n) => String(n).padStart(2, '0');
    return `${p(Math.floor(s / 3600))}:${p(Math.floor((s % 3600) / 60))}:${p(s % 60)}`;
}

/** [ADDED v3.93.0] Where a block is in Home Assistant's trace, from where the importer found it in the YAML (src) and
 *  the rung's choose or if: triggers[0] is trigger/0; actions[0].opt[1].seq[0] is action/0/choose/1/sequence/0, or
 *  action/0/default/0, action/0/then/0, action/0/else/0; .or[1] is /conditions/1; .parallel[1][0] is
 *  /parallel/1/sequence/0; .repeat[0] is /repeat/sequence/0. '' when it has none - a block drawn in LIBI. */
export function tracePath(src, rung) {
    const text = String(src || '');
    let m = text.match(/^actions\[(\d+)\]\.opt\[(\d+)\]\.(cond|seq)\[(\d+)\](.*)$/);
    let base = '';
    let rest = '';
    if (m) {
        const [, i, k, kind, j, tail] = m;
        const isIf = rung && rung.groupKind === 'if';
        const isDefault = !!(rung && rung.isDefault);
        if (kind === 'cond') base = isIf ? `action/${i}/if/condition/${j}` : `action/${i}/choose/${k}/conditions/${j}`;
        else if (isIf) base = isDefault ? `action/${i}/else/${j}` : `action/${i}/then/${j}`;
        else base = isDefault ? `action/${i}/default/${j}` : `action/${i}/choose/${k}/sequence/${j}`;
        rest = tail;
    } else {
        m = text.match(/^(triggers|conditions|actions)\[(\d+)\](.*)$/);
        if (!m) return '';
        base = `${{ triggers: 'trigger', conditions: 'condition', actions: 'action' }[m[1]]}/${m[2]}`;
        rest = m[3];
    }
    const parts = rest.match(/\.(and|or|not)\[\d+\]|\.parallel\[\d+\](\[\d+\])?|\.repeat\[\d+\]|\.wait_for_trigger\[\d+\]/g) || [];
    if (parts.join('') !== rest) return '';
    for (const part of parts) {
        let p = part.match(/^\.(and|or|not)\[(\d+)\]$/);
        if (p) { base += `/conditions/${p[2]}`; continue; }
        p = part.match(/^\.parallel\[(\d+)\](?:\[(\d+)\])?$/);
        if (p) { base += `/parallel/${p[1]}/sequence/${p[2] === undefined ? 0 : p[2]}`; continue; }
        p = part.match(/^\.repeat\[(\d+)\]$/);
        if (p) { base += `/repeat/sequence/${p[1]}`; continue; }
        p = part.match(/^\.wait_for_trigger\[(\d+)\]$/);
        if (p) base += `/wait_for_trigger/${p[1]}`;
    }
    return base;
}

export class LibiOnline {
    constructor() {
        this.enabled = false;
        // [ADDED v3.93.0] simulate: FORCE and a run in the panel only; real: Home Assistant's own runs, and Run.
        this.mode = 'simulate';
        this.forces = new Map();    // `${netId}|${elId}` -> true | false
        this.memory = new Map();    // `${netId}|${elId}` -> { value, prev, changedAt }
        this.netMemory = new Map(); // netId -> { lastTriggered, changedAt }
        this.result = new Map();    // `${netId}|${elId}` -> { power, value, prev, fresh, ... }
        this.rungPower = new Map(); // `${netId}|${rungId}` -> bool | null
        this.runs = new Map();      // netId -> { list, get }: the newest run in Home Assistant's trace
        this.sims = new Map();      // netId -> a simulated run
        this.now = () => Date.now();
    }

    key(netId, id) { return `${netId}|${id}`; }
    rungPowerOf(netId, rungId) { return this.rungPower.get(this.key(netId, rungId)); }
    resultOf(netId, elId) { return this.result.get(this.key(netId, elId)); }

    /** [ADDED v3.93.0] Online off, another project, Real: what was forced and simulated goes. */
    reset() {
        this.forces.clear();
        this.sims.clear();
        this.memory.clear();
        this.result.clear();
        this.rungPower.clear();
        this.netMemory.clear();
        this.runs.clear();
    }

    setMode(mode) {
        this.mode = mode === 'real' ? 'real' : 'simulate';
        // Nothing forced or simulated is left over Home Assistant's own runs.
        if (this.mode === 'real') { this.forces.clear(); this.sims.clear(); }
    }

    stateObj(hass, entityId) {
        if (!hass || !hass.states || !entityId) return null;
        return hass.states[entityId] || null;
    }

    stateOf(hass, entityId) {
        const st = this.stateObj(hass, entityId);
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

    /** [ADDED v3.93.0] The entities a block reads or drives - what is offline when they are. */
    entitiesOf(el) {
        const t = el.type || '';
        const out = [];
        const add = (v) => { const s = String(v || '').trim(); if (ENTITY_ID.test(s)) out.push(s); };
        if (t.startsWith('contact') || t.startsWith('coil')) add(el.label);
        else if (t.startsWith('cmp')) { add(el.sourceA); add(el.sourceB); add(el.sourceC); }
        else if (t === 'move' || t === 'notify') add(el.target);
        else if (t.startsWith('math')) { add(el.sourceA); add(el.sourceB); add(el.target); }
        else if (t === 'ctu') add(el.source);
        return out;
    }

    /** [ADDED v3.93.0] 'offline' (unavailable), 'unknown', 'missing' (Home Assistant has no such entity), or '' for a
     *  block whose entities all answer. A phone's action is looked up by its phone; another action has no state. */
    availability(el, hass) {
        let worst = '';
        const rank = { '': 0, unknown: 1, offline: 2, missing: 3 };
        for (const id of this.entitiesOf(el)) {
            let eid = id;
            const domain = id.split('.')[0];
            if (domain === 'notify') {
                const phone = this.core && this.core.phoneOf ? this.core.phoneOf(id) : null;
                if (!phone) continue;
                eid = phone.entity_id;
            }
            const st = this.stateObj(hass, eid);
            const now = !st ? 'missing' : st.state === 'unavailable' ? 'offline' : st.state === 'unknown' ? 'unknown' : '';
            if (rank[now] > rank[worst]) worst = now;
        }
        return worst;
    }

    /** [ADDED v3.93.0] The time of day of a value - "06:00", "06:00:00" or a time helper - as seconds, or NaN. */
    timeOfDay(hass, value) {
        const v = this.valueOf(hass, value);
        return secondsOf(v === undefined ? '' : String(v).split(' ').pop());
    }

    nowSeconds() {
        const d = new Date(this.now());
        return d.getHours() * 3600 + d.getMinutes() * 60 + d.getSeconds();
    }

    evaluate(el, hass, now, netId = '') {
        const t = el.type || '';
        let power = null;
        let value;
        let in1;
        let in2;

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
            in1 = value;
            in2 = `${this.valueOf(hass, el.sourceB) ?? '?'} … ${this.valueOf(hass, el.sourceC) ?? '?'}`;
            if (!isNaN(a) && !isNaN(min) && !isNaN(max)) power = a > min && a < max;
        } else if (t.startsWith('cmp')) {
            const left = String(el.sourceA || '');
            const schedule = left === 'datetime' && String(el.sourceB || '').startsWith('schedule.');
            if (schedule && (t === 'cmp_eq' || t === 'cmp_ne')) {
                // [ADDED v3.70.0] The date and time = schedule.x: on while the clock is inside the schedule.
                const st = this.stateOf(hass, el.sourceB);
                value = st;
                in1 = 'now';
                in2 = st;
                if (st !== null) power = (st === 'on') === (t === 'cmp_eq');
            } else if (left === 'time') {
                // [CHANGED v3.93.0] IN1 is the clock now, IN2 the time it waits for - a helper's value, or written in.
                const nowS = this.nowSeconds();
                const want = this.timeOfDay(hass, el.sourceB);
                value = clockOf(nowS);
                in1 = value;
                in2 = isNaN(want) ? this.valueOf(hass, el.sourceB) : clockOf(want);
                if (!isNaN(want)) {
                    if (t === 'cmp_gt') power = nowS > want;
                    else if (t === 'cmp_lt') power = nowS < want;
                    else if (t === 'cmp_ge') power = nowS >= want;
                    else if (t === 'cmp_le') power = nowS <= want;
                    else if (t === 'cmp_eq') power = Math.floor(nowS / 60) === Math.floor(want / 60);
                    else if (t === 'cmp_ne') power = Math.floor(nowS / 60) !== Math.floor(want / 60);
                }
            } else if (left === 'weekday' || left === 'datetime' || left === 'sun') {
                // [CHANGED v3.77.0] IN1 is the day now (datetime.day.now).
                value = left === 'weekday' ? DAY_IDS[new Date(this.now()).getDay()] : left;
                in1 = value;
                in2 = this.valueOf(hass, el.sourceB);
            } else {
                const a = this.numberOf(hass, el.sourceA);
                const b = this.numberOf(hass, el.sourceB);
                const av = this.valueOf(hass, el.sourceA);
                const bv = this.valueOf(hass, el.sourceB);
                value = av;
                in1 = av;
                in2 = bv;
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

        const key = this.key(netId, el.id);
        // [ADDED v3.93.0] Forced in Simulate: the block gives what was forced, whatever Home Assistant has.
        const forced = this.mode === 'simulate' && this.forces.has(key) ? this.forces.get(key) : null;
        if (forced !== null) power = forced;
        this.remember(key, value, now);
        return { power, value, in1, in2, forced };
    }

    remember(key, value, now) {
        const cell = this.memory.get(key);
        if (!cell) {
            this.memory.set(key, { value, prev: undefined, changedAt: 0 });
            return;
        }
        if (value !== undefined && String(cell.value) !== String(value)) {
            this.memory.set(key, { value, prev: cell.value, changedAt: now });
        }
    }

    /** [ADDED v3.93.0] The TON of a for: done once the block before it has been on for its time, counting down from the
     *  last change of that block's entity, as Home Assistant counts it. */
    forTimer(el, before, beforeRes, hass, now) {
        const preset = secondsOf(el.forValue || el.label);
        const st = before ? this.stateObj(hass, before.label) : null;
        if (!(beforeRes && beforeRes.power === true) || isNaN(preset)) return { power: beforeRes && beforeRes.power === false ? false : null };
        if (beforeRes.forced !== null && beforeRes.forced !== undefined) return { power: null, preset };
        const since = st && st.last_changed ? Date.parse(st.last_changed) : NaN;
        if (isNaN(since)) return { power: null, preset };
        const remaining = preset - (now - since) / 1000;
        return { power: remaining <= 0, preset, remaining: Math.max(0, remaining) };
    }

    evaluateSeries(elements, hass, now, netId = '') {
        let flow = true;
        let known = true;
        let before = null;
        let beforeRes = null;
        for (const el of elements || []) {
            let res;
            if (el.type === 'parallel') {
                res = { power: this.evaluateParallel(el, hass, now, netId) };
            } else if (el.type === 'repeat') {
                (el.sequence || []).forEach(child => this.evaluateSeries([child], hass, now, netId));
                res = { power: true };
            } else if (el.type === 'timer_ton' && (el.isFor || el.forOf)) {
                res = this.forTimer(el, before, beforeRes, hass, now);
            } else {
                res = this.evaluate(el, hass, now, netId);
            }
            const key = this.key(netId, el.id);
            const mem = this.memory.get(key) || {};
            this.result.set(key, {
                power: res.power,
                value: mem.value,
                prev: mem.prev,
                in1: res.in1,
                in2: res.in2,
                forced: res.forced === undefined ? null : res.forced,
                remaining: res.remaining,
                preset: res.preset,
                fresh: mem.changedAt ? (now - mem.changedAt) < PULSE_MS : false,
                state: el.type === 'parallel' || el.type === 'repeat' ? '' : this.availability(el, hass),
            });
            if (res.power === null || res.power === undefined) known = false;
            else if (res.power === false) flow = false;
            before = el;
            beforeRes = res;
        }
        return flow && known ? true : (known ? false : null);
    }

    evaluateParallel(el, hass, now, netId = '') {
        let any = false;
        let known = true;
        for (const branch of el.branches || []) {
            const res = this.evaluateSeries(branch, hass, now, netId);
            if (res === null) known = false;
            else if (res === true) any = true;
        }
        if (any) return true;
        return known ? false : null;
    }

    update(nets, hass) {
        const now = this.now();
        this.result.clear();
        this.rungPower.clear();
        for (const net of nets || []) {
            let netLive = false;
            // [ADDED v3.71.0] The power at the trigger the rungs below hang from: the trigger of the last rung that does
            // not hang, OR the triggers of the rungs linked to it (an OR of triggers is one rung per trigger).
            const core = this.core;
            let head = null;
            let headRung = null;
            for (const rung of net.rungs || []) {
                let flow = this.evaluateSeries(rung.elements, hass, now, net.id);
                if (core && core.hangs(rung)) {
                    flow = (head === false || flow === false) ? false : (head === true && flow === true ? true : null);
                } else if (core) {
                    const trig = core.triggerHead(rung);
                    const tres = trig ? this.resultOf(net.id, trig.id) : null;
                    const own = tres ? tres.power : null;
                    const joined = headRung !== null && (net.links || []).some(l =>
                        (l.aRung === headRung && l.bRung === rung.id) || (l.bRung === headRung && l.aRung === rung.id));
                    if (!trig) { head = null; headRung = null; }
                    else if (joined) head = (head === true || own === true) ? true : (head === false && own === false ? false : null);
                    else { head = own; headRung = rung.id; }
                }
                this.rungPower.set(this.key(net.id, rung.id), flow);
                if (flow === true) netLive = true;
            }
            const ent = this.findAutomationEntity(hass, net);
            if (ent) {
                const last = ent.attributes && ent.attributes.last_triggered;
                const cell = this.netMemory.get(net.id) || {};
                if (last && cell.lastTriggered !== last) this.netMemory.set(net.id, { lastTriggered: last, changedAt: now });
            }
            this.netMemory.set(net.id + ':live', { live: netLive });
            this.simAdvance(net, hass, now);
        }
    }

    /** The automation of a NET in Home Assistant: the one with its id (ha_id, or the key LIBI saved it under). */
    findAutomationEntity(hass, net) {
        if (!hass || !hass.states || !net) return null;
        const id = String(net.ha_id || (this.keys && this.keys[net.id]) || '');
        if (!id) return null;
        for (const key of Object.keys(hass.states)) {
            if (!key.startsWith('automation.')) continue;
            const st = hass.states[key];
            if (st.attributes && String(st.attributes.id) === id) return st;
        }
        return null;
    }

    /** [ADDED v3.93.0] The id of a NET's automation in Home Assistant's trace (its item_id), or ''. */
    traceItemOf(net) {
        return String((net && (net.ha_id || (this.keys && this.keys[net.id]))) || '');
    }

    lastRunText(netId) {
        const cell = this.netMemory.get(netId);
        if (!cell || !cell.lastTriggered) return '';
        const then = new Date(cell.lastTriggered);
        if (isNaN(then.getTime())) return '';
        const secs = Math.max(0, Math.round((this.now() - then.getTime()) / 1000));
        if (secs < 60) return `last run ${secs}s ago`;
        if (secs < 3600) return `last run ${Math.round(secs / 60)}m ago`;
        if (secs < 86400) return `last run ${Math.round(secs / 3600)}h ago`;
        return `last run ${then.toLocaleDateString()}`;
    }

    // ------------------------------------------------------------------ the real run, from Home Assistant's trace

    /** [ADDED v3.93.0] The newest run of a NET's automation, as trace/list and trace/get answered. */
    setRun(netId, run) {
        if (run && run.list) this.runs.set(netId, run);
        else this.runs.delete(netId);
    }

    /** [ADDED v3.93.0] The run as one line: when it started, and how it ended or where it is. */
    runSummary(netId, now = this.now()) {
        const run = this.runs.get(netId);
        if (!run || !run.list) return null;
        const list = run.list;
        const get = run.get || {};
        const start = list.timestamp && list.timestamp.start ? Date.parse(list.timestamp.start) : NaN;
        const at = isNaN(start) ? '' : new Date(start).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        const running = list.state === 'running';
        const exec = list.script_execution || get.script_execution || '';
        const error = get.error || list.error || '';
        let kind = 'ok';
        let text;
        if (running) { kind = 'active'; text = `running since ${at}`; }
        else if (error || exec === 'error') { kind = 'error'; text = `${at} error: ${error || 'see its trace in Home Assistant'}`; }
        else if (exec === 'failed_conditions') { kind = 'false'; text = `${at} triggered, stopped: a condition was false`; }
        else if (exec === 'finished') { text = `${at} finished`; }
        else if (exec) { kind = 'false'; text = `${at} ${exec.replace(/_/g, ' ')}`; }
        else { text = at; }
        // [ADDED v3.94.0] Started with no trigger (Home Assistant's own Run, or Run without a trigger): a rung that runs
        // for its own trigger did not run - what the user saw, 2026-11-07, every block "not reached".
        const traced = get.trace && typeof get.trace === 'object' ? Object.keys(get.trace) : null;
        if (traced && traced.length && !traced.some(p => /^trigger\/\d+$/.test(p))) text += ' - started with no trigger';
        return { kind, text, running, error, trigger: list.trigger || '', lastStep: list.last_step || '', start };
    }

    /** [ADDED v3.93.0] What the last real run did at a block: fired (its trigger started the run), true or false (a
     *  condition), done, error (with Home Assistant's reason), active (the step it is in - a delay with the time left),
     *  or not reached. null when the block has no place in the trace. */
    elementRun(net, rung, el, now = this.now()) {
        const run = this.runs.get(net.id);
        if (!run || !run.get || !run.get.trace) return null;
        const trace = run.get.trace;
        const triggers = ((run.get.config || {}).triggers || (run.get.config || {}).trigger || []);
        const fired = Object.keys(trace).map(p => p.match(/^trigger\/(\d+)$/)).find(Boolean);
        const firedIdx = fired ? Number(fired[1]) : -1;
        const firedId = firedIdx >= 0 && triggers[firedIdx] ? String(triggers[firedIdx].id || '') : '';
        if (el.isTrigger || ((el.isFor || el.forOf) && /^triggers\[/.test(String(el.src || '')))) {
            const own = String(el.src || '').match(/^triggers\[(\d+)\]/);
            const isThis = own ? Number(own[1]) === firedIdx : (el.trigId !== undefined && String(el.trigId) === firedId);
            if (own || el.trigId !== undefined) return isThis ? { kind: 'fired', text: 'started this run' } : { kind: 'idle', text: 'not this run' };
        }
        const path = tracePath(el.src, rung);
        if (!path) return null;
        const steps = trace[path];
        if (!steps || !steps.length) return { kind: 'skip', text: 'not reached in this run' };
        const last = steps[steps.length - 1];
        if (last.error) return { kind: 'error', text: String(last.error) };
        const result = last.result || {};
        if (Object.prototype.hasOwnProperty.call(result, 'delay')) {
            const startedAt = Date.parse(last.timestamp);
            const running = run.list.state === 'running' && run.list.last_step === path && !result.done;
            const remaining = Number(result.delay) - (now - startedAt) / 1000;
            if (running) return { kind: 'active', text: `TON ${clockOf(remaining)} left`, remaining: Math.max(0, remaining) };
            return { kind: 'done', text: `waited ${clockOf(result.delay)}` };
        }
        if (Object.prototype.hasOwnProperty.call(result, 'result') && typeof result.result === 'boolean') {
            return result.result ? { kind: 'true', text: 'true in this run' } : { kind: 'false', text: 'false: the run stopped here' };
        }
        if (run.list.state === 'running' && run.list.last_step === path) return { kind: 'active', text: 'running now' };
        return { kind: 'done', text: steps.length > 1 ? `ran ${steps.length} times` : 'ran' };
    }

    // ------------------------------------------------------------------ Simulate: FORCE and a run in the panel only

    force(netId, elId, value) {
        const key = this.key(netId, elId);
        if (value === true || value === false) this.forces.set(key, value);
        else this.forces.delete(key);
    }

    forcedOf(netId, elId) {
        const key = this.key(netId, elId);
        return this.forces.has(key) ? this.forces.get(key) : null;
    }

    forceCount() { return this.forces.size; }

    /** [ADDED v3.93.0] What a block is in a simulated run: a condition (a test), a TON, a WAIT, or an action. */
    kindOf(el) {
        const t = el.type || '';
        if (t === 'parallel') {
            const conds = (el.branches || []).every(b => (b || []).every(x => this.kindOf(x) === 'cond'));
            return conds ? 'cond' : 'par';
        }
        if (t === 'repeat') return 'repeat';
        if (t.startsWith('timer')) return 'timer';
        if (t === 'wait') return 'wait';
        if (t.startsWith('contact') || t.startsWith('cmp') || t === 'schedule' || t === 'ctu') return 'cond';
        return 'act';
    }

    /** [ADDED v3.93.0] The steps of a rung in a simulated run, the blocks of a parallel and of a repeat in order. */
    simSteps(elements, rungId) {
        const out = [];
        for (const el of elements || []) {
            const kind = this.kindOf(el);
            if (kind === 'par') {
                for (const branch of el.branches || []) out.push(...this.simSteps(branch, rungId));
                out.push({ el, rungId, kind: 'container' });
            } else if (kind === 'repeat') {
                out.push(...this.simSteps(el.sequence, rungId));
                out.push({ el, rungId, kind: 'container', note: 'a repeat runs once in a simulation' });
            } else {
                out.push({ el, rungId, kind });
            }
        }
        return out;
    }

    /** [ADDED v3.93.0] A simulated run of a NET, from the rung whose trigger was forced: that rung and the rungs that
     *  hang from its trigger, a choose or an if as Home Assistant runs it - the first option whose conditions hold, the
     *  else (default) when none does. Nothing is sent to Home Assistant. */
    startSim(net, rungId, hass, now = this.now()) {
        const core = this.core;
        const rungs = net.rungs || [];
        const at = rungs.findIndex(r => r.id === rungId);
        if (at < 0) return null;
        const members = [rungs[at]];
        for (let i = at + 1; i < rungs.length && core && core.hangs(rungs[i]); i++) members.push(rungs[i]);
        const plan = members.map(r => {
            const head = core ? core.headLength(r) : 0;
            const forTon = head === 2 ? [{ el: r.elements[1], rungId: r.id, kind: 'timer', isFor: true }] : [];
            return { rung: r, steps: [...forTon, ...this.simSteps(r.elements.slice(head), r.id)] };
        });
        const trig = core ? core.triggerHead(rungs[at]) : null;
        const sim = { netId: net.id, plan, rungAt: 0, stepAt: 0, status: 'running', marks: new Map(), log: [], startedAt: now,
            chosen: new Set(), states: new Map(), timerStart: 0, waitingSkip: false };
        sim.log.push({ at: now, text: `FORCE TRUE ${trig ? this.describe(trig) : 'the trigger'}: the run starts (simulated, nothing is sent)` });
        if (trig) sim.marks.set(trig.id, { kind: 'fired', text: 'started this simulated run' });
        this.sims.set(net.id, sim);
        this.simAdvance(net, hass, now);
        return sim;
    }

    stopSim(netId) { this.sims.delete(netId); }

    /** [ADDED v3.93.0] ⏭ - the TON or WAIT the simulated run is in is over now. */
    skipSim(net, hass, now = this.now()) {
        const sim = this.sims.get(net.id);
        if (!sim || sim.status !== 'running') return;
        sim.skip = true;
        this.simAdvance(net, hass, now);
    }

    describe(el) {
        const t = el.type || '';
        const what = el.label || el.target || el.sourceA || el.source || '';
        const kind = t.startsWith('contact') ? 'contact' : t.startsWith('coil') ? 'coil' : t.startsWith('cmp') ? 'CMP'
            : t.startsWith('timer') ? 'TON' : t.toUpperCase();
        return `${kind}${what ? ' ' + what : ''}`;
    }

    simAdvance(net, hass, now) {
        const sim = this.sims.get(net.id);
        if (!sim || sim.status !== 'running') return;
        let guard = 0;
        while (sim.status === 'running' && guard++ < 500) {
            const member = sim.plan[sim.rungAt];
            if (!member) { sim.status = 'done'; sim.log.push({ at: now, text: 'the run finished' }); break; }
            const rung = member.rung;
            // A choose or an if runs one option: once one ran, the other options of its group are not run.
            if (rung.group && sim.chosen.has(rung.group)) { this.simNextRung(sim); continue; }
            const step = member.steps[sim.stepAt];
            if (!step) {
                if (rung.group) sim.chosen.add(rung.group);
                this.simNextRung(sim);
                continue;
            }
            const el = step.el;
            if (step.kind === 'cond') {
                const res = el.type === 'parallel' ? { power: this.evaluateParallel(el, hass, now, net.id) } : this.evaluate(el, hass, now, net.id);
                if (res.power === true) {
                    sim.marks.set(el.id, { kind: 'true', text: 'true' });
                    sim.stepAt++;
                } else {
                    sim.marks.set(el.id, { kind: 'false', text: res.power === false ? 'false: this rung stops here' : 'unknown: this rung stops here' });
                    sim.stopped = `${this.describe(el)} is ${res.power === false ? 'false' : 'unknown'}`;
                    sim.log.push({ at: now, text: `${sim.stopped}: rung ${this.rungNo(net, rung)} stops` });
                    this.simNextRung(sim);
                }
            } else if (step.kind === 'timer' || step.kind === 'wait') {
                const preset = step.kind === 'timer' ? secondsOf(el.forValue || el.label) : NaN;
                if (!sim.timerStart) {
                    sim.timerStart = now;
                    sim.log.push({ at: now, text: step.kind === 'timer'
                        ? `${step.isFor ? 'the for of the trigger' : 'TON'} ${isNaN(preset) ? '(its time is a template: ⏭ goes on)' : clockOf(preset)} starts`
                        : 'WAIT: ⏭ goes on' });
                }
                const remaining = isNaN(preset) ? Infinity : preset - (now - sim.timerStart) / 1000;
                if (sim.skip || remaining <= 0) {
                    sim.marks.set(el.id, { kind: 'done', text: sim.skip ? 'skipped (⏭)' : `done after ${clockOf(preset)}` });
                    sim.skip = false;
                    sim.timerStart = 0;
                    sim.stepAt++;
                } else {
                    sim.marks.set(el.id, { kind: 'active', text: isFinite(remaining) ? `TON ${clockOf(remaining)} left` : 'waiting - ⏭ to go on',
                        remaining: isFinite(remaining) ? remaining : undefined });
                    break;
                }
            } else if (step.kind === 'container') {
                sim.marks.set(el.id, { kind: 'done', text: step.note || 'done' });
                sim.stepAt++;
            } else {
                const t = el.type || '';
                let text = 'would run (not sent)';
                if (t.startsWith('coil') && el.label) {
                    const was = sim.states.has(el.label) ? sim.states.get(el.label) : this.stateOf(hass, el.label);
                    const to = t === 'coil_r' ? 'off' : t === 'coil_t' ? (ON_STATES.has(String(was).toLowerCase()) ? 'off' : 'on') : 'on';
                    sim.states.set(el.label, to);
                    text = `${el.label} would turn ${to} (not sent)`;
                } else if (t === 'move' || t === 'notify') {
                    text = `would send to ${el.target || 'its action'} (not sent)`;
                }
                sim.marks.set(el.id, { kind: 'done', text });
                sim.log.push({ at: now, text });
                sim.ranAction = true;
                sim.stepAt++;
            }
        }
    }

    simNextRung(sim) {
        sim.rungAt++;
        sim.stepAt = 0;
        sim.timerStart = 0;
        sim.skip = false;
    }

    rungNo(net, rung) {
        return (net.rungs || []).indexOf(rung) + 1;
    }

    simSummary(netId) {
        const sim = this.sims.get(netId);
        if (!sim) return null;
        const active = [...sim.marks.values()].find(m => m.kind === 'active');
        const last = sim.log[sim.log.length - 1];
        const done = sim.stopped && !sim.ranAction ? `stopped: ${sim.stopped}` : 'finished';
        return { status: sim.status, active, text: sim.status === 'done' ? done : active ? active.text : (last ? last.text : 'running'),
            log: sim.log };
    }

    // ------------------------------------------------------------------ painting

    paint(root, nets, hass) {
        if (!root) return;
        root.querySelectorAll('.libi-el').forEach(node => {
            node.classList.remove('live-on', 'live-off', 'live-unknown', 'live-fresh', 'live-offline', 'live-missing', 'live-forced',
                'run-fired', 'run-true', 'run-false', 'run-done', 'run-error', 'run-active', 'run-skip', 'run-idle');
            node.querySelectorAll('.live-val').forEach(b => b.remove());
        });
        root.querySelectorAll('.rung').forEach(node => node.classList.remove('rung-live'));
        root.querySelectorAll('.net-live-note').forEach(node => node.remove());

        if (!this.enabled) return;
        this.update(nets, hass);
        const now = this.now();

        for (const net of nets || []) {
            const sim = this.mode === 'simulate' ? this.sims.get(net.id) : null;
            const marks = new Map();
            for (const rung of net.rungs || []) {
                const walk = (els) => (els || []).forEach(el => {
                    const mark = this.markOf(net, rung, el, now);
                    if (mark) marks.set(el.id, mark);
                    (el.branches || []).forEach(walk);
                    walk(el.sequence);
                });
                walk(rung.elements);
            }
            root.querySelectorAll(`.libi-el[data-nid="${CSS.escape(net.id)}"]`).forEach(node => {
                const id = node.getAttribute('data-eid');
                const res = id ? this.resultOf(net.id, id) : null;
                const mark = id ? marks.get(id) : null;
                const lines = [];
                // [CHANGED v3.94.0] What the run did here is the first line, in words (it was a circle on the corner).
                if (mark) {
                    node.classList.add(`run-${mark.kind}`);
                    lines.push([`live-run run-${mark.kind}`, this.markLine(mark, !!sim)]);
                }
                if (res) {
                    node.classList.add(res.power === true ? 'live-on' : res.power === false ? 'live-off' : 'live-unknown');
                    if (res.fresh) node.classList.add('live-fresh');
                    if (res.state === 'offline' || res.state === 'unknown') node.classList.add('live-offline');
                    if (res.state === 'missing') node.classList.add('live-missing');
                    if (res.forced !== null && res.forced !== undefined) node.classList.add('live-forced');
                    lines.push(...this.badgeLines(res, sim ? sim.states : null, id, net, mark));
                }
                if (lines.length) {
                    const badge = document.createElement('div');
                    // Under the Trigger (or continue if error) label of the block, not on it.
                    badge.className = node.querySelector(':scope > .trigger-bottom-lbl, :scope > .coe-bottom-lbl') ? 'live-val below-tag' : 'live-val';
                    for (const [cls, text] of lines) {
                        const span = document.createElement('span');
                        span.className = cls;
                        span.textContent = text;
                        badge.appendChild(span);
                    }
                    node.appendChild(badge);
                }
            });
            for (const rung of net.rungs || []) {
                if (this.rungPowerOf(net.id, rung.id) !== true) continue;
                const rungNode = root.querySelector(`.rung[data-nid="${CSS.escape(net.id)}"][data-rid="${CSS.escape(rung.id)}"]`);
                if (rungNode) rungNode.classList.add('rung-live');
            }
            this.paintMonitor(root, net, hass, now, marks);
        }
    }

    /** [ADDED v3.93.0] The lines under a block: what is forced, offline, the TON's time left, IN1 and IN2, the value. */
    badgeLines(res, simStates, elId, net, mark = null) {
        const lines = [];
        if (res.forced !== null && res.forced !== undefined) lines.push(['live-force', `F ${res.forced ? 'TRUE' : 'FALSE'}`]);
        if (res.state === 'offline') lines.push(['live-state', 'OFFLINE']);
        else if (res.state === 'unknown') lines.push(['live-state', 'UNKNOWN']);
        else if (res.state === 'missing') lines.push(['live-state', 'NOT IN HA']);
        // The TON a run is in - Home Assistant's, or the simulated one - counts down on the run's own line (markLine).
        if (!(mark && mark.kind === 'active' && mark.remaining !== undefined) && res.remaining !== undefined) {
            lines.push(['live-timer', res.remaining > 0 ? `⏳ ${clockOf(res.remaining)}` : 'Q ✓']);
        }
        if (res.in1 !== undefined || res.in2 !== undefined) {
            lines.push(['live-now', `IN1 ${res.in1 === undefined || res.in1 === null ? '?' : res.in1}`]);
            lines.push(['live-now', `IN2 ${res.in2 === undefined || res.in2 === null ? '?' : res.in2}`]);
        } else if (res.value !== undefined && res.value !== null && String(res.value) !== '') {
            lines.push(['live-now', String(res.value)]);
            if (res.prev !== undefined && res.prev !== null && String(res.prev) !== String(res.value)) lines.push(['live-prev', `was ${res.prev}`]);
        }
        const el = this.findEl(net, elId);
        if (simStates && el && el.label && simStates.has(el.label)) lines.push(['live-sim', `SIM → ${simStates.get(el.label)}`]);
        return lines;
    }

    /** [ADDED v3.94.0] What the run did at a block: the simulated run's in Simulate, else Home Assistant's last run. */
    markOf(net, rung, el, now = this.now()) {
        const sim = this.mode === 'simulate' ? this.sims.get(net.id) : null;
        if (sim) return sim.marks.get(el.id) || null;
        return this.elementRun(net, rung, el, now);
    }

    /** [ADDED v3.94.0] The run's line under a block, in words: RUN (Home Assistant's) or SIM (the simulated one). */
    markLine(mark, simulated) {
        const who = simulated ? 'SIM' : 'RUN';
        if (mark.kind === 'active') return `${who} ⏳ ${mark.remaining !== undefined ? clockOf(mark.remaining) : 'now'}`;
        if (mark.kind === 'false') return `${who} ✗ ${String(mark.text || '').startsWith('unknown') ? 'unknown' : 'false'}: stopped here`;
        const words = { fired: '▶ started the run', idle: '· another trigger', true: '✓ true', done: '✓ done', error: '⚠ error',
            skip: '– not reached' }[mark.kind];
        return `${who} ${words || mark.text}`;
    }

    findEl(net, elId) {
        let found = null;
        const walk = (els) => (els || []).forEach(el => {
            if (found) return;
            if (el.id === elId) found = el;
            (el.branches || []).forEach(walk);
            walk(el.sequence);
        });
        (net.rungs || []).forEach(r => walk(r.elements));
        return found;
    }

    /** [ADDED v3.93.0] The NET's monitor, over its rungs: the clock, the automation in Home Assistant (on, off, running,
     *  its last run), the simulated run, and the value of every variable it uses. Written again only when it changed, so
     *  its buttons stay where they are. Every value is text (textContent), never HTML. */
    paintMonitor(root, net, hass, now, marks) {
        const box = root.querySelector(`.net-monitor[data-nid="${CSS.escape(net.id)}"]`);
        if (!box) return;
        const d = new Date(now);
        const chips = [['mon-clock', `NOW ${clockOf(d.getHours() * 3600 + d.getMinutes() * 60 + d.getSeconds())} ${DAY_IDS[d.getDay()]}`]];
        const level = this.core && this.core.netLevel ? this.core.netLevel(net) : 'automation';
        const ent = level === 'automation' ? this.findAutomationEntity(hass, net) : null;
        if (level !== 'automation') chips.push(['mon-muted', `${level}: no trace`]);
        else if (!ent) chips.push(['mon-muted', 'not in Home Assistant yet']);
        else {
            chips.push(ent.state === 'on' ? ['mon-ok', 'ON in Home Assistant'] : ['mon-err', 'OFF in Home Assistant: it does not run']);
            if (Number((ent.attributes || {}).current) > 0) chips.push(['mon-active', 'running']);
        }
        const run = this.runSummary(net.id, now);
        if (run) chips.push([`mon-run run-${run.kind}`, `last run: ${run.text}`]);
        const hasSrc = (net.rungs || []).some(r => (r.elements || []).some(e => e.src));
        if (run && !hasSrc) chips.push(['mon-muted', 'drawn in LIBI: the run is shown here, not on each block']);
        const sim = this.mode === 'simulate' ? this.simSummary(net.id) : null;
        const vars = [];
        const seen = new Set();
        const walk = (els) => (els || []).forEach(el => {
            for (const id of this.entitiesOf(el)) {
                if (seen.has(id) || id.startsWith('notify.') || id.startsWith('script.')) continue;
                seen.add(id);
                const st = this.stateObj(hass, id);
                const name = (this.core && this.core.friendlyName ? this.core.friendlyName(id, hass) : '') || id;
                const value = !st ? 'NOT IN HA' : st.state === 'unavailable' ? 'OFFLINE' : st.state;
                vars.push([!st || st.state === 'unavailable' || st.state === 'unknown' ? 'mon-var bad' : 'mon-var', `${name} = ${value}`, id]);
            }
            (el.branches || []).forEach(walk);
            walk(el.sequence);
        });
        (net.rungs || []).forEach(r => walk(r.elements));
        const buttons = [];
        if (this.mode === 'simulate') {
            if (sim && sim.status === 'running' && sim.active) buttons.push(['skip', '⏭ Skip']);
            if (sim) buttons.push(['stop', '⏹ Clear the simulation']);
        } else if (level === 'automation') {
            buttons.push(['run', '▶ Run without a trigger']);
        }
        const sig = JSON.stringify([chips, sim && [sim.status, sim.text, sim.log.length], vars, buttons]);
        if (box.dataset.sig === sig) return;
        box.dataset.sig = sig;
        box.textContent = '';
        const line = (cls) => { const div = document.createElement('div'); div.className = cls; box.appendChild(div); return div; };
        const chip = (parent, cls, text, title) => {
            const span = document.createElement('span');
            span.className = `mon-chip ${cls}`;
            span.textContent = text;
            span.dir = 'auto';
            if (title) span.title = title;
            parent.appendChild(span);
        };
        const top = line('mon-line');
        chips.forEach(([cls, text]) => chip(top, cls, text));
        if (sim) {
            const s = line('mon-line mon-sim');
            chip(s, `mon-simstate sim-${sim.status}`, `SIMULATION: ${sim.text}`, sim.log.map(l => `${new Date(l.at).toLocaleTimeString()} ${l.text}`).join('\n'));
        }
        if (vars.length) {
            const v = line('mon-line mon-vars');
            vars.forEach(([cls, text, id]) => chip(v, cls, text, id));
        }
        if (buttons.length) {
            const b = line('mon-line mon-acts');
            for (const [act, text] of buttons) {
                const btn = document.createElement('button');
                btn.className = 'btn mon-btn';
                btn.setAttribute('data-online', act);
                btn.setAttribute('data-nid', net.id);
                btn.textContent = text;
                b.appendChild(btn);
            }
        }
    }

    _esc(v) {
        return String(v === undefined || v === null ? '' : v)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }
}
