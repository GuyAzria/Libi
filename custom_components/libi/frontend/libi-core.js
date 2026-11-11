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
 * LIBI Panel - Core Engine
 * v3.95.5
 */
// [CHANGED v3.94.3 | 2026-11-09] Purpose: The user's screenshot: in Traces, IN2 under a time trigger was cut off by the
//   end of the NET's drawing. liveRoom - the room under every block for Traces' lines: a rung's pad under its blocks
//   when larger (layout), added between branches, which editing packs block to block (calcHeightPx), and the pad
//   under a parallel too, for its own line; 0 while editing, so the editing layout is as it was.
// [CHANGED v3.95.5 | 2026-11-11] Purpose: The virtual tests of 2026-11-11: a CMP = / not = whose IN2 is an entity Home
//   Assistant reads as plain text - its state is never "sensor.other" - is red, and the save refused (checkLiteral); so is
//   a CMP not = that starts an automation on a state, which has no form in Home Assistant - of several entities too - and a
//   person in a zone whose check has an option a zone has none of (for, attribute ...), and an IN2 emptied. Only where IN1
//   can never hold such a text (FIXED_STATE): a dropdown, a text or a sensor may hold an entity's id as its value, and so
//   may an attribute (a person's source is a tracker) - in a trigger too; IN2 0 is no empty IN2; a person in a zone with a
//   TON after it is refused, a zone has no for (the fourth pass of the review of the release). The fifth: only a TON that
//   is a for (isFor, forOf) counts - a plain one is a delay; a not = held for a time is refused, Home Assistant cannot
//   say it; a for in the node it was drawn from is the TON's, gone with it.
export class LibiCore {
    constructor() {
        this.nets = [];
        this.history = [];
        this.historyIdx = -1;
        this.isPerformingUndoRedo = false;
        this.clipboard = null;
        this.nid = 1; 
        this.rid = 1; 
        this.eid = 1;
        this.lid = 1;

        this.LAY = { DOT: 16, GAP: 24, SPLIT: 32, MERGE: 32, ANCHOR: 38, REP_W: 70, CAP: 8, BOTTOM_PAD: 44, LEAD: 24, LBL_PAD: 56, RUNG_GAP: 10 };
        // [ADDED v3.94.3] Room under each block for the lines Traces writes there; the panel sets it (LIVE_ROOM in
        // libi-online.js) while Traces is on and back to 0 for editing.
        this.liveRoom = 0;

        // [ADDED v3.5.0] The three kinds of logic a net can be.
        this.LEVELS = ['automation', 'script', 'scene'];
    }

    // [ADDED v3.7.0] The browser twin of the naming layer in the importer. When the user picks
    // targets in the native selector the pin has to be renamed immediately, and it follows exactly
    // the same rule: entity first, then device resolved to one of its entities, then area, label and
    // floor. It never returns a registry id and never returns an empty string.
    TARGET_KEYS() { return ['entity_id', 'device_id', 'area_id', 'label_id', 'floor_id']; }

    normSpec(spec) {
        const out = {};
        for (const key of this.TARGET_KEYS()) {
            const v = (spec || {})[key];
            const arr = (Array.isArray(v) ? v : (v === undefined || v === null || v === '' ? [] : [v]))
                .map(x => String(x)).filter(Boolean);
            if (arr.length) out[key] = arr;
        }
        return out;
    }

    specCount(spec) {
        return this.TARGET_KEYS().reduce((n, k) => n + ((this.normSpec(spec)[k] || []).length), 0);
    }

    targetLabel(spec, hass, domainHint = '') {
        const s = this.normSpec(spec);
        const slug = (t) => String(t || '').toLowerCase().trim().replace(/[^a-z0-9_]+/g, '_').replace(/^_+|_+$/g, '');
        const total = this.specCount(s);
        const suffix = total > 1 ? ` +${total - 1}` : '';

        if (s.entity_id) return { label: s.entity_id[0] + suffix, kind: 'entity' };

        if (s.device_id) {
            const id = s.device_id[0];
            const reg = (hass && hass.entities) || {};
            const owned = Object.keys(reg).filter(eid => reg[eid] && reg[eid].device_id === id);
            const hit = owned.find(eid => eid.split('.')[0] === domainHint)
                     || owned.find(eid => !(reg[eid] || {}).entity_category)
                     || owned[0];
            if (hit) return { label: hit + suffix, kind: 'device' };
            const dev = (hass && hass.devices && hass.devices[id]) || null;
            const nm = dev ? (dev.name_by_user || dev.name) : '';
            return { label: `${domainHint || 'device'}.${slug(nm) || 'device'}${suffix}`, kind: 'device' };
        }

        for (const [key, kind, reg] of [['area_id', 'area', 'areas'], ['label_id', 'label', 'labels'], ['floor_id', 'floor', 'floors']]) {
            if (!s[key]) continue;
            const id = s[key][0];
            const entry = (hass && hass[reg] && hass[reg][id]) || null;
            const nm = entry ? (entry.name || entry.label_id || '') : '';
            return { label: `${kind}.${slug(nm) || slug(id) || kind}${suffix}`, kind };
        }
        return { label: '', kind: 'entity' };
    }

    // [ADDED v3.8.0] The OUT pin of a MOVE ACTION, the same summary the importer writes. Several
    // targets read as a count, a single group reads as its kind and name, one entity reads as itself.
    targetSummary(spec, label, kind) {
        const total = this.specCount(spec);
        if (total > 1) return `${total} targets`;
        const clean = String(label || '').replace(/\s*\+\d+$/, '').trim();
        if (!clean) return 'no target';
        if (kind === 'entity') return clean;
        const name = clean.includes('.') ? clean.split('.').slice(1).join('.') : clean;
        return `${kind.charAt(0).toUpperCase()}${kind.slice(1)}: ${name}`;
    }

    // [ADDED v3.7.0] Applies a freshly picked target to an element: the block itself, the pin text
    // and the note of which kind of target produced that text.
    applyTargetSpec(el, spec, hass) {
        const s = this.normSpec(spec);
        const hint = String(el.service || el.source || el.label || el.target || '').split('.')[0] || '';
        el.targetSpec = s;
        const res = this.targetLabel(s, hass, hint);
        if (res.label) {
            const t = String(el.type || '');
            if (t.startsWith('coil') || t.startsWith('contact')) el.label = res.label;
            // [CHANGED v3.8.0] A MOVE ACTION shows the summary on OUT, not the name of the first target.
            else if (el.moveKind === 'action') el.target = this.targetSummary(s, res.label, res.kind);
            else el.target = res.label;
            el.targetKind = res.kind;
            el.targetLabel = res.label;
        }
        return el;
    }

    // [ADDED v3.24.0] The services Home Assistant offers for a domain that the ladder draws as a
    // coil. This is what the inspector lists, so a cover can be switched between closing, opening
    // and stopping without leaving the block.
    COIL_SERVICES() {
        return {
            cover:               ['close_cover', 'open_cover', 'stop_cover', 'toggle'],
            valve:               ['close_valve', 'open_valve', 'stop_valve', 'toggle'],
            lock:                ['lock', 'unlock', 'open'],
            light:               ['turn_on', 'turn_off', 'toggle'],
            switch:              ['turn_on', 'turn_off', 'toggle'],
            fan:                 ['turn_on', 'turn_off', 'toggle'],
            climate:             ['turn_on', 'turn_off', 'toggle'],
            media_player:        ['turn_on', 'turn_off', 'toggle', 'media_play', 'media_pause', 'media_stop'],
            vacuum:              ['start', 'stop', 'turn_on', 'turn_off'],
            humidifier:          ['turn_on', 'turn_off', 'toggle'],
            water_heater:        ['turn_on', 'turn_off'],
            siren:               ['turn_on', 'turn_off', 'toggle'],
            remote:              ['turn_on', 'turn_off', 'toggle'],
            automation:          ['turn_on', 'turn_off', 'toggle'],
            script:              ['turn_on', 'turn_off', 'toggle'],
            input_boolean:       ['turn_on', 'turn_off', 'toggle'],
            button:              ['press'],
            input_button:        ['press'],
            timer:               ['start', 'cancel', 'pause'],
            alarm_control_panel: ['alarm_arm_home', 'alarm_arm_away', 'alarm_arm_night', 'alarm_disarm'],
            homeassistant:       ['turn_on', 'turn_off', 'toggle'],
        };
    }

    // Which coil a service is drawn as. Closing a cover drives a motor exactly as opening it does,
    // so it latches and is (S). Only a service that takes something out of service is (R).
    coilForService(svc) {
        const full = String(svc || '');
        const name = full.split('.').pop();
        if (full === 'homeassistant.turn_off') return 'coil_r';
        if (full === 'homeassistant.turn_on') return 'coil_s';
        const RESET = ['turn_off', 'stop', 'stop_cover', 'stop_valve', 'media_pause', 'media_stop',
                       'cancel', 'disable', 'disarm', 'alarm_disarm', 'close', 'pause'];
        if (RESET.includes(name)) return 'coil_r';
        // [ADDED v3.30.0] A toggle flips the state rather than driving it to one, so it is (T).
        if (name === 'toggle') return 'coil_t';
        // [CHANGED v3.29.0] Only a button press is momentary. Everything else that switches
        // something on latches, because Home Assistant runs the rung once and walks away.
        if (name === 'press') return 'coil';
        return 'coil_s';
    }

    // [ADDED v3.5.0] Every read of the level goes through here, so a net saved before this
    // version, or one with a value nobody recognises, is treated as an automation.
    netLevel(net) {
        const lvl = String((net && net.level) || 'automation').toLowerCase();
        return this.LEVELS.includes(lvl) ? lvl : 'automation';
    }

    pushHistory() {
        if (this.isPerformingUndoRedo) return;
        this.validateAST(); 
        const currentState = JSON.stringify(this.nets);
        if (this.historyIdx >= 0 && this.history[this.historyIdx] === currentState) return;
        this.history = this.history.slice(0, this.historyIdx + 1);
        if (this.history.length >= 10) this.history.shift(); else this.historyIdx++;
        this.history.push(currentState);
    }

    undo() {
        if (this.historyIdx > 0) {
            this.isPerformingUndoRedo = true; 
            this.historyIdx--;
            this.nets = JSON.parse(this.history[this.historyIdx]);
            this.syncCounters(); 
            this.isPerformingUndoRedo = false; 
            return true;
        }
        return false;
    }

    redo() {
        if (this.historyIdx < this.history.length - 1) {
            this.isPerformingUndoRedo = true; 
            this.historyIdx++;
            this.nets = JSON.parse(this.history[this.historyIdx]);
            this.syncCounters(); 
            this.isPerformingUndoRedo = false; 
            return true;
        }
        return false;
    }

    syncCounters() {
        let maxNid = 0, maxRid = 0, maxEid = 0;
        const scanElements = (elements) => {
            for (let el of elements) {
                let eNum = parseInt(el.id.substring(1), 10);
                if (eNum > maxEid) maxEid = eNum;
                if (el.type === 'parallel') for (let b of el.branches) scanElements(b);
                if (el.type === 'repeat') scanElements(el.sequence);
            }
        };
        for (let net of this.nets) {
            let nNum = parseInt(net.id.substring(1), 10);
            if (nNum > maxNid) maxNid = nNum;
            for (let rung of net.rungs) {
                let rNum = parseInt(rung.id.substring(1), 10);
                if (rNum > maxRid) maxRid = rNum;
                scanElements(rung.elements);
            }
        }
        this.nid = maxNid + 1; this.rid = maxRid + 1; this.eid = maxEid + 1;
    }

    // [CHANGED v3.5.0] A new net says which of the three kinds of logic it is. The argument has a
    // default, so any existing call that passes only a name still creates an automation.
    mkNet(name, description = '', level = 'automation') { return { id: `n${this.nid++}`, name, description, level: this.netLevel({ level }), collapsed: false, rungs: [this.mkRung()] }; }

    duplicateNet(src) {
        const copy = JSON.parse(JSON.stringify(src));
        copy.id = `n${this.nid++}`;
        const rungMap = {};
        copy.name = `${src.name || 'Automation'} COPY`;
        // [CHANGED v3.91.0] A copy names no automation of Home Assistant's: it is saved as a new one, under its own NET id.
        // The callers that put a version or the AI chat's change in a NET's place give it that NET's ha_id themselves.
        delete copy.ha_id;
        copy.collapsed = false;
        const reid = (arr) => {
            for (let el of arr || []) {
                el.id = `e${this.eid++}`;
                if (el.type === 'parallel') (el.branches || []).forEach(reid);
                if (el.type === 'repeat') reid(el.sequence);
            }
        };
        for (let i = 0; i < (copy.rungs || []).length; i++) {
            const rung = copy.rungs[i];
            rungMap[(src.rungs[i] || {}).id] = rung.id = `r${this.rid++}`;
            reid(rung.elements);
        }
        copy.links = (copy.links || []).map(l => Object.assign({}, l, {
            id: `k${this.lid++}`, aRung: rungMap[l.aRung] || l.aRung, bRung: rungMap[l.bRung] || l.bRung
        }));
        return copy;
    }
    mkRung() { return { id: `r${this.rid++}`, comment: '', elements: [] }; }

    // [ADDED v3.71.0] The trigger block a rung starts with - a trigger, or an OR of triggers - or null.
    triggerHead(rung) {
        const first = rung && rung.elements && rung.elements[0];
        if (!first) return null;
        if (first.isTrigger) return first;
        const branches = first.type === 'parallel' ? (first.branches || []) : [];
        return branches.length && branches.every(b => b && b[0] && b[0].isTrigger) ? first : null;
    }

    // [ADDED v3.71.0] A rung drawn below the trigger of the rung above it (sharesHead): it has no trigger of its own.
    // The compiler gives it that trigger again (expand_shared_heads), so the YAML is what it was with the trigger
    // drawn on every rung.
    hangs(rung) { return !!(rung && rung.sharesHead) && !this.triggerHead(rung); }

    // [ADDED v3.71.0] The index of the rung a hanging rung comes down from: the nearest one above that does not hang,
    // when it starts with a trigger. -1 otherwise.
    headIndex(net, i) {
        const rungs = (net && net.rungs) || [];
        let j = i - 1;
        while (j >= 0 && this.hangs(rungs[j])) j--;
        return j >= 0 && this.triggerHead(rungs[j]) ? j : -1;
    }

    // [ADDED v3.72.0] How many blocks a rung's trigger head takes: the trigger, and the TON of its for after it.
    headLength(rung) {
        if (!this.triggerHead(rung)) return 0;
        const next = rung.elements[1];
        return next && next.type === 'timer_ton' && (next.isFor || next.forOf) ? 2 : 1;
    }
    
    mkEl(type, label = '') {
        if (type === 'parallel') return { id: `e${this.eid++}`, type, branches: [[], []], closed: false };
        if (type === 'repeat') return { id: `e${this.eid++}`, type: 'repeat', loopType: 'count', value: '3', sequence: [] };
        if (type.startsWith('timer')) return { id: `e${this.eid++}`, type, label: label || '00:00:01' };
        if (type === 'move') return { id: `e${this.eid++}`, type: 'move', source: '', target: '' };
        if (type.startsWith('cmp')) return { id: `e${this.eid++}`, type, sourceA: label || '', sourceB: '' };
        if (type === 'notify') return { id: `e${this.eid++}`, type: 'notify', source: 'Message...', target: '' };
        if (type === 'ctu') return { id: `e${this.eid++}`, type: 'ctu', source: '', value: '5' };
        if (type === 'schedule') return { id: `e${this.eid++}`, type: 'schedule', sourceA: '08:00', sourceB: '17:00' };
        if (type === 'math_div') return { id: `e${this.eid++}`, type, sourceA: '', sourceB: '', target: '', precision: 2, fallback: 0 };
        if (type.startsWith('math')) return { id: `e${this.eid++}`, type, sourceA: '', sourceB: '', target: '' };
        if (type === 'move') return { id: `e${this.eid++}`, type, mode: 'value', source: '', target: '', title: '', tts: '' };
        if (type === 'cmp_rng') return { id: `e${this.eid++}`, type, sourceA: '', sourceB: '', sourceC: '' };
        
        return { id: `e${this.eid++}`, type, label, isTrigger: false };
    }

    getElW(el) { 
        if (el.type.startsWith('contact') || el.type.startsWith('coil') || el.type === 'wait') return 56; 
        if (el.type.startsWith('cmp') || el.type === 'move' || el.type.startsWith('math')) return 208;
        return 160; 
    }

    getElH(el) {
        if (el.type.startsWith('contact') || el.type.startsWith('coil') || el.type === 'wait') return 100; 
        if (el.type === 'move' && el.mode === 'both') return 180;
        
        let baseH = 140; 
        if (el.type.startsWith('cmp') || el.type.startsWith('math') || el.type === 'schedule') baseH = 160; 
        
        const checkLen = (str) => {
            if (!str) return 0;
            let s = String(str);
            if (s.includes('.') && !s.includes(' ') && isNaN(s)) {
                s = s.split('.').slice(1).join('.');
            }
            return s.length > 15 ? 20 : 0; 
        };
        
        let extraH = 0;
        extraH += checkLen(el.label);
        extraH += checkLen(el.source);
        extraH += checkLen(el.target);
        extraH += checkLen(el.sourceA);
        extraH += checkLen(el.sourceB);
        extraH += checkLen(el.value);
        
        // [ADDED v3.71.0] CMP DATETIME against a schedule has one line more: the days and hours of that schedule.
        const week = String(el.sourceA) === 'datetime' && String(el.sourceB || '').startsWith('schedule.') ? 20 : 0;
        return baseH + Math.min(extraH, 60) + week;
    }

    calcHeightPx(elements) {
        if (!elements || elements.length === 0) return 100; 
        let maxH = 100;
        for (let el of elements) {
            if (el.type === 'parallel') {
                let pHeight = 0;
                for (let b of el.branches) pHeight += this.calcHeightPx(b);
                maxH = Math.max(maxH, pHeight);
            } else if (el.type === 'repeat') {
                maxH = Math.max(maxH, this.calcHeightPx(el.sequence));
            } else {
                maxH = Math.max(maxH, this.getElH(el) + (el.isTrigger ? 24 : 0) + this.liveRoom);
            }
        }
        return maxH;
    }

    opSymbol(type) {
        const map = {
            cmp_eq: '=', cmp_ne: '≠', cmp_gt: '>', cmp_lt: '<', cmp_ge: '≥', cmp_le: '≤',
            math_add: '+', math_sub: '−', math_mul: '×', math_div: '÷'
        };
        return map[type] || String(type || '').split('_').slice(1).join(' ').toUpperCase();
    }

    hasTopLabel(el) {
        const t = el.type || '';
        return t.startsWith('contact') || t.startsWith('coil') || t === 'wait';
    }

    labelWidth(el) {
        return this.getElW(el) + this.LAY.LBL_PAD;
    }

    // [ADDED v3.9.0] The name a person gave a thing in Home Assistant. An entity id is a slug and a
    // transliteration, climate.pynt_vkl for what the house calls its dining corner, so the ladder shows the
    // name and keeps the id one hover away.
    friendlyName(entityId, hass) {
        const h = hass || this.hass;
        const id = String(entityId || '').replace(/\s*\+\d+$/, '').trim();
        // [ADDED v3.28.1] A name just typed in the rename dialog is shown at once. Home Assistant
        // pushes the new state a moment later, and the override is dropped as soon as it lands.
        if (this.nameOverrides && Object.prototype.hasOwnProperty.call(this.nameOverrides, id)) {
            return this.nameOverrides[id];
        }
        // [ADDED v3.86.0] Then the name the user gave it in LIBI only (the user's request, 2026-11-04).
        // [CHANGED v3.87.0] A phone's action has no name in Home Assistant: the phone's is shown.
        const phone = this.phoneOf(id);
        // [CHANGED v3.88.0] A recipient of LIBI Global by its own name: its script's alias is "LIBI Global: <name>".
        const recipient = this.recipientOf(id);
        return this.localName(id) || (recipient ? recipient.name : '') || this.haName(id, h)
            || (phone && phone.entity_id !== id ? this.haName(phone.entity_id, h) : '');
    }

    // [ADDED v3.86.0] The name the user gave an entity in LIBI only, or ''. Home Assistant does not know it.
    // [CHANGED v3.87.0] A phone's name, whichever of its two ids it was given to (phoneOf).
    localName(entityId) {
        const id = String(entityId || '').replace(/\s*\+\d+$/, '').trim();
        const names = this.localNames || {};
        const phone = this.phoneOf(id);
        for (const key of phone ? [phone.service, phone.entity_id] : [id]) {
            if (Object.prototype.hasOwnProperty.call(names, key) && names[key]) return String(names[key]);
        }
        return '';
    }

    // [ADDED v3.87.0] A phone has two ids in Home Assistant: its notify entity (notify.sm_s938b), which Home Assistant
    // cannot call as an action, and the action that sends to it (notify.mobile_app_sm_s938b) - phones, from libi/phones.
    // The phone with either id, or null. Two phones the Companion app registered under one name share one action, and
    // neither is the phone of it.
    phoneOf(entityId) {
        const id = String(entityId || '').replace(/\s*\+\d+$/, '').trim();
        if (!id) return null;
        return (this.phones || []).find(p => p && !p.shared && (p.service === id || p.entity_id === id)) || null;
    }

    // [ADDED v3.88.0] A recipient of LIBI Global, by the action that sends to it (script.libi_send_to_<name>), or null -
    // recipients, from libi/global.
    recipientOf(entityId) {
        const id = String(entityId || '').replace(/\s*\+\d+$/, '').trim();
        if (!id.startsWith('script.libi_send_to_')) return null;
        return (this.recipients || []).find(r => r && r.action === id) || null;
    }

    // [ADDED v3.87.0] The id a name in LIBI is kept under: a phone's action, for either of its ids, so the phone has one
    // name whichever id a pin holds - in every project, as every name in LIBI.
    nameKey(entityId) {
        const id = String(entityId || '').replace(/\s*\+\d+$/, '').trim();
        const phone = this.phoneOf(id);
        return phone ? phone.service : id;
    }

    // [ADDED v3.86.0] Home Assistant's own name for an entity, whatever LIBI shows - for what is sent to Home Assistant.
    haName(entityId, hass) {
        const h = hass || this.hass;
        const id = String(entityId || '').replace(/\s*\+\d+$/, '').trim();
        if (!h || !id.includes('.')) return '';
        const st = h.states && h.states[id];
        if (st && st.attributes && st.attributes.friendly_name) return String(st.attributes.friendly_name);
        const reg = h.entities && h.entities[id];
        if (reg && (reg.name || reg.original_name)) return String(reg.name || reg.original_name);
        return '';
    }

    deviceName(deviceId, hass) {
        const h = hass || this.hass;
        const dev = h && h.devices && h.devices[deviceId];
        if (dev && (dev.name_by_user || dev.name)) return String(dev.name_by_user || dev.name);
        // No device row, so try any entity that belongs to it before giving up.
        const reg = (h && h.entities) || {};
        const owned = Object.keys(reg).find(eid => reg[eid] && reg[eid].device_id === deviceId);
        if (owned) return this.friendlyName(owned, h) || owned;
        return '';
    }

    registryName(kind, id, hass) {
        const h = hass || this.hass;
        const map = { area: 'areas', label: 'labels', floor: 'floors' }[kind];
        const entry = map && h && h[map] && h[map][id];
        return entry && entry.name ? String(entry.name) : '';
    }

    // [ADDED v3.9.0] Everything a target block points at, written out by name. This is what the hover
    // shows on a MOVE ACTION that carries seventeen devices.
    targetNameList(spec, hass) {
        const h = hass || this.hass;
        const s = this.normSpec(spec);
        const out = [];
        for (const id of (s.entity_id || [])) {
            const nm = this.friendlyName(id, h);
            out.push(nm ? `${nm}  (${id})` : id);
        }
        for (const id of (s.device_id || [])) {
            const nm = this.deviceName(id, h);
            out.push(nm ? `${nm}  (device)` : `device not in the registry  (${String(id).slice(0, 8)}…)`);
        }
        for (const [key, kind] of [['area_id', 'area'], ['label_id', 'label'], ['floor_id', 'floor']]) {
            for (const id of (s[key] || [])) {
                const nm = this.registryName(kind, id, h);
                out.push(nm ? `${nm}  (${kind})` : `${id}  (${kind})`);
            }
        }
        return out;
    }

    // [ADDED v3.9.0] What is written above an element: the name if the thing has one, the entity id
    // if it does not. The id itself is never lost, it moves into the hover text below.
    displayLabel(el, hass) {
        const rawId = (el.raw_trigger && el.raw_trigger.type) ? el.raw_trigger.type : (el.label || '');
        const id = String(rawId || '');
        const suffix = (id.match(/\s*\+\d+$/) || [''])[0];
        const bare = id.replace(/\s*\+\d+$/, '').trim();
        const kind = el.targetKind || 'entity';

        // [ADDED v3.10.0] An event trigger already says its kind on the second line, so the name
        // line drops the prefix: Good night over conversation, not conversation.Good night twice.
        const evKinds = ['conversation', 'event', 'webhook', 'mqtt', 'tag', 'homeassistant', 'persistent_notification'];
        const ev = el.eventKind || (evKinds.includes(bare.split('.')[0]) ? bare.split('.')[0] : '');
        if (ev && bare.startsWith(ev + '.')) return bare.slice(ev.length + 1) + suffix;

        let name = '';
        if (kind === 'entity' || kind === 'device') name = this.friendlyName(bare, hass);
        if (!name && bare.includes('.')) {
            const [pre, ...rest] = bare.split('.');
            if (['area', 'label', 'floor'].includes(pre)) {
                const ids = this.normSpec(el.targetSpec)[`${pre}_id`] || [];
                name = ids.length ? this.registryName(pre, ids[0], hass) : '';
            }
        }
        return name ? name + suffix : '';
    }

    // [ADDED v3.9.0] The hover text of a block. The entity id always, the full target list when the
    // block points at more than one thing.
    elementTooltip(el, hass) {
        const lines = [];
        const id = String((el.label || '')).replace(/\s*\+\d+$/, '').trim();
        const name = this.displayLabel(el, hass);
        if (name && id) lines.push(`${name}\n${id}`);
        else if (id) lines.push(id);
        const spec = this.normSpec(el.targetSpec);
        const total = this.specCount(spec);
        if (total) {
            const names = this.targetNameList(spec, hass);
            if (total > 1 || !id) {
                lines.push(`${total} target${total === 1 ? '' : 's'}:`);
                lines.push(names.map(n => '  • ' + n).join('\n'));
            }
        }
        if (el.service && !lines.length) lines.push(String(el.service));
        if (el.structuralError) lines.push('⚠ ' + el.structuralError);
        return lines.filter(Boolean).join('\n');
    }

    // [ADDED v3.10.0] The kind of thing an element points at, written on a second line under the
    // name. A name alone does not say what it is: Dining corner could be a thermostat, a light or a
    // sensor, and Sony XR-85X95L could be a media player or a switch. The domain settles it.
    // [CHANGED v3.24.0] On a coil the line underneath the name is the service, written the way Home
    // Assistant writes it. cover on its own never said whether the rung closes the blind or opens it.
    domainText(el, hass) {
        const t = String(el.type || '');
        if (!(t.startsWith('contact') || t.startsWith('coil'))) return '';
        if (t.startsWith('coil') && el.service) return String(el.service);
        // [ADDED v3.31.0] A block built from a device node has no service of its own, so the line
        // underneath names the integration behind the device and what it is being asked to do.
        if (el.deviceNode) {
            const raw = (el.raw && typeof el.raw === 'object') ? el.raw : {};
            const bits = [raw.domain, raw.subtype || raw.type].filter(Boolean);
            if (bits.length) return bits.join(' · ');
        }
        if (el.eventKind) return String(el.eventKind);
        // [ADDED v3.27.0] A friendly name on its own does not say which thing it is. Windows could be
        // any of several lights, so the line underneath names the device the entity belongs to as
        // well as the domain, exactly the two things the Home Assistant entity picker shows.
        {
            const id = String((el.raw_trigger && el.raw_trigger.type) || el.label || '')
                .replace(/\s*\+\d+$/, '').trim();
            if (id.includes('.')) {
                const dom = id.split('.')[0];
                const h = hass || this.hass;
                const reg = (h && h.entities && h.entities[id]) || null;
                const dev = reg && reg.device_id && h.devices ? h.devices[reg.device_id] : null;
                const devName = dev ? (dev.name_by_user || dev.name) : '';
                if (devName) return `${dom} · ${devName}`;
            }
        }
        const evKinds = ['conversation', 'event', 'webhook', 'mqtt', 'tag', 'homeassistant', 'persistent_notification'];
        const head = String(el.label || '').split('.')[0];
        if (evKinds.includes(head)) return head;
        const id = String((el.raw_trigger && el.raw_trigger.type) || el.label || '')
            .replace(/\s*\+\d+$/, '').trim();
        if (!id.includes('.')) return '';
        const prefix = id.split('.')[0];
        if (!/^[a-z_][a-z0-9_]*$/.test(prefix)) return '';
        // A device that could not be resolved shows up as light.device and so on. What matters
        // there is that it is a device, not which domain the service belonged to.
        if (el.targetKind && el.targetKind !== 'entity' && id.split('.').slice(1).join('.') === 'device') {
            return 'device';
        }
        return prefix;
    }

    labelText(el, hass) {
        // [CHANGED v3.9.0] The name wins over the id, so the box above a coil reads Living room shutter rather
        // than unknown_cover. Falls back to the old behaviour when nothing has a name.
        const named = this.displayLabel(el, hass);
        if (named) return named;
        let s = (el.raw_trigger && el.raw_trigger.type) ? el.raw_trigger.type : (el.label || '');
        if (!String(s || '').trim()) return '...';
        s = String(s);
        if (s.includes('.') && !s.includes(' ') && isNaN(s)) s = s.split('.').slice(1).join('.');
        return s;
    }

    estLabelH(el, hass) {
        if (!this.hasTopLabel(el)) return 0;
        const s = this.labelText(el, hass);
        const perLine = Math.max(5, Math.floor((this.labelWidth(el) - 16) / 6.1));
        const lines = Math.min(4, Math.max(1, Math.ceil(s.length / perLine)));
        // [CHANGED v3.10.0] Room for the domain line underneath the name.
        const domainH = this.domainText(el, hass) ? 12 : 0;
        return lines * 14 + 12 + domainH;
    }

    topLineLabelH(elements) {
        let m = 0;
        for (const el of (elements || [])) {
            if (!el) continue;
            if (el.type === 'parallel') m = Math.max(m, this.topLineLabelH((el.branches && el.branches[0]) || []));
            else if (el.type === 'repeat') m = Math.max(m, this.topLineLabelH(el.sequence || []));
            else m = Math.max(m, this.estLabelH(el));
        }
        return m;
    }

    _newLayoutCtx() {
        return { nodes: [], dots: [], lines: [], par: '', bidx: -1, maxX: 0, maxBottom: 0, railX: this.LAY.LEAD };
    }

    _layoutLevel(elements, x0, y, prefix, ctx, opts = {}) {
        const L = this.LAY;
        const list = elements || [];
        let cur = x0;

        const addDot = (path, x) => {
            ctx.dots.push({ path, x, y, par: ctx.par, bidx: ctx.bidx });
            ctx.maxX = Math.max(ctx.maxX, x + L.DOT);
            ctx.maxBottom = Math.max(ctx.maxBottom, y + 40);
        };

        // [CHANGED v3.71.0] A rung that hangs from a trigger starts at the drop under it, not at the rail.
        const opensWithBlock = !ctx.hang && prefix === '' && list.length && list[0] && list[0].type === 'parallel';
        if (!opts.noLeadDot && !opensWithBlock) {
            cur += (ctx.gaps && ctx.gaps[`${prefix}0`]) || 0;
            addDot(`${prefix}0`, cur);
            cur += L.DOT;
        }

        for (let i = 0; i < list.length; i++) {
            const el = list[i];
            const path = `${prefix}${i}`;

            if (el.type === 'parallel') {
                cur = this._layoutParallel(el, cur, y, path, ctx, (!ctx.hang && prefix === '' && i === 0));
                if (el.closed) { addDot(`${prefix}${i + 1}`, cur); cur += L.DOT; }
            } else if (el.type === 'repeat') {
                cur = this._layoutRepeat(el, cur, y, path, ctx);
                cur += (ctx.gaps && ctx.gaps[`${prefix}${i + 1}`]) || 0;
                addDot(`${prefix}${i + 1}`, cur); cur += L.DOT;
            } else {
                const w = this.getElW(el);
                const ex = cur + L.GAP;
                ctx.nodes.push({ kind: 'el', el, path, x: ex, y, w, par: ctx.par, bidx: ctx.bidx });
                ctx.maxX = Math.max(ctx.maxX, ex + w);
                ctx.maxBottom = Math.max(ctx.maxBottom, y - L.ANCHOR + this.getElH(el) + Math.max(L.BOTTOM_PAD, this.liveRoom));
                cur = ex + w + L.GAP;
                cur += (ctx.gaps && ctx.gaps[`${prefix}${i + 1}`]) || 0;
                addDot(`${prefix}${i + 1}`, cur); cur += L.DOT;
            }
        }

        const lineStart = (opts.lineStart !== undefined) ? opts.lineStart : x0;
        ctx.lines.push({ x1: lineStart, y1: y, x2: cur, y2: y, w: 2.5 });
        ctx.maxX = Math.max(ctx.maxX, cur);
        return cur;
    }

    _layoutParallel(el, cur, y, path, ctx, railStart = false) {
        const L = this.LAY;
        if (!el.branches || el.branches.length === 0) return cur;

        const bx = railStart ? cur + 8 : cur + L.SPLIT;
        const dropX = railStart ? bx + Math.round(L.DOT / 2) : cur + Math.round(L.SPLIT / 2);
        const ends = [];
        let by = y;

        const prevPar = ctx.par, prevBidx = ctx.bidx;
        for (let i = 0; i < el.branches.length; i++) {
            const b = el.branches[i] || [];
            const carriesLine = (i === 0 && b.length > 0) && !railStart;
            let originX = carriesLine ? cur : bx;
            let levelOpts = { noLeadDot: carriesLine };
            if (railStart) {
                originX = bx;
                levelOpts = { noLeadDot: false };
            } else if (i > 0) {
                ctx.lines.push({ x1: dropX, y1: y, x2: dropX, y2: by, w: 2.5 });
                ctx.lines.push({ x1: dropX, y1: by, x2: bx, y2: by, w: 2.5 });
            }
            ctx.par = el.id; ctx.bidx = i;
            const endX = this._layoutLevel(b, originX, by, `${path}.b${i}.`, ctx, levelOpts);
            ends.push({ x: endX, y: by });
            const next = el.branches[i + 1];
            const labelRoom = next ? Math.max(0, this.topLineLabelH(next) - 30) : 0;
            by += this.calcHeightPx(b) + labelRoom;
        }
        ctx.par = prevPar; ctx.bidx = prevBidx;

        if (railStart && ends.length > 1) {
            ctx.lines.push({ x1: dropX, y1: y, x2: dropX, y2: ends[ends.length - 1].y, w: 2.5 });
        }

        const rightMost = ends.reduce((m, e) => Math.max(m, e.x), bx);
        let after;
        if (el.closed) {
            const mergeX = rightMost + L.MERGE;
            for (let i = 0; i < ends.length; i++) {
                ctx.lines.push({ x1: ends[i].x, y1: ends[i].y, x2: mergeX, y2: ends[i].y, w: 2.5 });
                if (i > 0) ctx.lines.push({ x1: mergeX, y1: ends[i].y, x2: mergeX, y2: y, w: 2.5 });
            }
            ctx.maxX = Math.max(ctx.maxX, mergeX);
            after = mergeX;
        } else {
            for (let i = 1; i < ends.length; i++) {
                const capX = ends[i].x + L.CAP;
                ctx.lines.push({ x1: ends[i].x, y1: ends[i].y, x2: capX, y2: ends[i].y, w: 2.5 });
                ctx.lines.push({ x1: capX, y1: ends[i].y - 12, x2: capX, y2: ends[i].y + 12, w: 2.5 });
                ctx.maxX = Math.max(ctx.maxX, capX + L.CAP);
            }
            after = ends[0].x;
        }

        const boxRight = Math.max(after, rightMost);
        ctx.nodes.push({ kind: 'parallel', el, path, x: cur, y, w: Math.max(boxRight - cur, L.SPLIT), h: (by - y), par: ctx.par, bidx: ctx.bidx });
        const lastY = ends.length ? ends[ends.length - 1].y : y;
        ctx.maxBottom = Math.max(ctx.maxBottom, lastY + 40);
        // [ADDED v3.94.3] In Traces the run's line of the whole parallel is under it (at by): the rung's pad under it too.
        if (this.liveRoom) ctx.maxBottom = Math.max(ctx.maxBottom, by + L.BOTTOM_PAD);
        return after;
    }

    _layoutRepeat(el, cur, y, path, ctx) {
        const L = this.LAY;
        const headX = cur + L.GAP;
        ctx.nodes.push({ kind: 'repeat', el, path, x: headX, y, w: L.REP_W, par: ctx.par, bidx: ctx.bidx });
        ctx.maxBottom = Math.max(ctx.maxBottom, y - L.ANCHOR + 100 + L.BOTTOM_PAD);
        cur = headX + L.REP_W + L.GAP;

        const seqStart = cur;
        const seqEnd = this._layoutLevel(el.sequence || [], cur, y, `${path}.seq.`, ctx);
        const frameH = this.calcHeightPx(el.sequence || []);
        ctx.nodes.push({ kind: 'repeat-frame', el, x: seqStart - 4, y, w: (seqEnd - seqStart) + 8, h: frameH, par: ctx.par, bidx: ctx.bidx });
        cur = seqEnd;

        const endX = cur + L.GAP;
        ctx.nodes.push({ kind: 'repeat-end', el, path, x: endX, y, w: L.REP_W, par: ctx.par, bidx: ctx.bidx });
        ctx.maxX = Math.max(ctx.maxX, endX + L.REP_W);
        cur = endX + L.REP_W + L.GAP;
        return cur;
    }

    layoutRung(elements, x0 = null, y0 = null, gaps = null, opts = {}) {
        const L = this.LAY;
        const startX = (x0 === null) ? L.LEAD : x0;
        const startY = (y0 === null) ? Math.max(L.ANCHOR, this.topLineLabelH(elements) + 22) : y0;
        const ctx = this._newLayoutCtx();
        ctx.railX = startX;
        ctx.gaps = gaps || null;
        // [ADDED v3.71.0] opts.hang: the rung comes down from a trigger above it, so its line starts at that drop.
        ctx.hang = !!opts.hang;
        const lineStart = ctx.hang ? startX + Math.round(L.DOT / 2) : 0;
        const endX = this._layoutLevel(elements || [], startX, startY, '', ctx, { lineStart });

        const capX = endX + L.CAP;
        ctx.lines.push({ x1: endX, y1: startY, x2: capX, y2: startY, w: 2.5 });
        ctx.lines.push({ x1: capX, y1: startY - 12, x2: capX, y2: startY + 12, w: 2.5 });
        ctx.maxX = Math.max(ctx.maxX, capX + L.CAP);

        return {
            nodes: ctx.nodes,
            dots: ctx.dots,
            lines: ctx.lines,
            endX,
            baseY: startY,
            width: Math.ceil(ctx.maxX + 40),
            height: Math.ceil(Math.max(ctx.maxBottom, startY + 70))
        };
    }

    layoutNet(net) {
        const L = this.LAY;
        const rungs = (net && net.rungs) || [];
        const links = (net && net.links) || [];
        const gapsByRung = {};
        let out = null;

        for (let pass = 0; pass < 3; pass++) {
            out = this._layoutNetPass(rungs, gapsByRung);
            let changed = false;
            for (const link of links) {
                const a = out.dotIndex[`${link.aRung}|${link.aPath}`];
                const b = out.dotIndex[`${link.bRung}|${link.bPath}`];
                if (!a || !b) continue;
                const delta = Math.round(Math.abs(a.x - b.x));
                if (delta < 1) continue;
                const behind = a.x < b.x ? { rung: link.aRung, path: link.aPath } : { rung: link.bRung, path: link.bPath };
                gapsByRung[behind.rung] = gapsByRung[behind.rung] || {};
                gapsByRung[behind.rung][behind.path] = (gapsByRung[behind.rung][behind.path] || 0) + delta;
                changed = true;
            }
            if (!changed) break;
        }

        for (const link of links) {
            const a = out.dotIndex[`${link.aRung}|${link.aPath}`];
            const b = out.dotIndex[`${link.bRung}|${link.bPath}`];
            if (!a || !b) continue;
            const x = Math.max(a.x, b.x) + Math.round(L.DOT / 2);
            const y1 = Math.min(a.y, b.y), y2 = Math.max(a.y, b.y);
            out.lines.push({ x1: x, y1, x2: x, y2, w: 2.5, link: link.id });
            out.linkHandles.push({ id: link.id, x, y: Math.round((y1 + y2) / 2) });
            out.maxX = Math.max(out.maxX, x + 8);
        }

        out.width = Math.ceil(out.maxX + 40);
        return out;
    }

    _layoutNetPass(rungs, gapsByRung) {
        const L = this.LAY;
        const res = { rungs: [], nodes: [], dots: [], lines: [], linkHandles: [], dotIndex: {}, maxX: 0, height: 0 };
        let offsetY = 0;
        // [ADDED v3.71.0] Where the rungs that hang from a trigger come down from: the dot after the trigger of the last
        // rung that does not hang, and how far down the drop goes so far.
        let drop = null;

        for (const rung of rungs) {
            const hanging = this.hangs(rung) && drop;
            const one = this.layoutRung(rung.elements, hanging ? drop.x : null, null, gapsByRung[rung.id] || null, { hang: !!hanging });
            const top = offsetY;

            for (const n of one.nodes) res.nodes.push(Object.assign({}, n, { y: n.y + top, rungId: rung.id }));
            for (const d of one.dots) {
                const moved = Object.assign({}, d, { y: d.y + top, rungId: rung.id });
                res.dots.push(moved);
                res.dotIndex[`${rung.id}|${d.path}`] = moved;
            }
            for (const l of one.lines) res.lines.push({ x1: l.x1, y1: l.y1 + top, x2: l.x2, y2: l.y2 + top, w: l.w });
            if (hanging) {
                const x = drop.x + Math.round(L.DOT / 2);
                res.lines.push({ x1: x, y1: drop.y, x2: x, y2: one.baseY + top, w: 2.5 });
                drop.y = one.baseY + top;
            } else if (!this.hangs(rung)) {
                const n = this.headLength(rung);
                const after = n ? res.dotIndex[`${rung.id}|${n}`] : null;
                drop = after ? { x: after.x, y: after.y } : null;
            }

            res.rungs.push({ id: rung.id, top, height: one.height, baseY: one.baseY + top });
            res.maxX = Math.max(res.maxX, one.width - 40);
            offsetY += one.height + L.RUNG_GAP;
        }

        res.height = Math.max(offsetY, 120);
        return res;
    }

    calcWidthPx(elements) {
        const ctx = this._newLayoutCtx();
        return this._layoutLevel(elements || [], 0, this.LAY.ANCHOR, '', ctx);
    }

    buildSvgLines(elements, startX = 0, startY = 38, isMain = true, isClosed = false) {
        const res = this.layoutRung(elements, startX, startY);
        return { lines: res.lines, maxX: res.endX, width: res.width, height: res.height };
    }

    pathInfo(pathStr) {
        const parts = String(pathStr).split('.');
        const steps = [];
        for (let i = 0; i < parts.length - 1; i += 2) {
            const kind = parts[i + 1] === 'seq' ? 'seq' : 'b';
            steps.push({
                idx: parseInt(parts[i], 10),
                kind,
                bidx: kind === 'seq' ? -1 : parseInt(String(parts[i + 1]).substring(1), 10)
            });
        }
        return { steps, idx: parseInt(parts[parts.length - 1], 10), prefix: parts.slice(0, parts.length - 1).join('.') };
    }

    getArrBySteps(netId, rungId, steps) {
        const rung = this.findRung(netId, rungId);
        if (!rung) return null;
        let cur = rung.elements;
        for (const s of steps) {
            const el = cur[s.idx];
            if (!el) return null;
            cur = s.kind === 'seq' ? el.sequence : (el.branches ? el.branches[s.bidx] : null);
            if (!cur) return null;
        }
        return cur;
    }

    connectRelation(pathA, pathB) {
        const A = this.pathInfo(pathA);
        const B = this.pathInfo(pathB);
        let k = 0;
        while (k < A.steps.length && k < B.steps.length &&
               A.steps[k].idx === B.steps[k].idx &&
               A.steps[k].kind === B.steps[k].kind &&
               A.steps[k].bidx === B.steps[k].bidx) k++;

        if (k === A.steps.length && k === B.steps.length) {
            if (A.idx === B.idx) return null;
            return { type: 'same-array', steps: A.steps, from: Math.min(A.idx, B.idx), to: Math.max(A.idx, B.idx) };
        }

        if (k < A.steps.length) {
            const s = A.steps[k];
            if (s.kind === 'b' && s.bidx > 0) {
                if (k === B.steps.length) {
                    if (B.idx > s.idx) return { type: 'close-outer', steps: A.steps.slice(0, k), parIdx: s.idx, upto: B.idx };
                } else if (B.steps[k].idx === s.idx && B.steps[k].kind === 'b' && B.steps[k].bidx === 0) {
                    const cut = (k + 1 === B.steps.length) ? B.idx : (B.steps[k + 1].idx + 1);
                    return { type: 'close-inner', steps: A.steps.slice(0, k), parIdx: s.idx, cut };
                }
            }
        }
        return null;
    }

    openBranchAt(netId, rungId, pathStr) {
        const info = this.pathInfo(pathStr);
        const arr = this.getArrBySteps(netId, rungId, info.steps);
        if (!arr) return false;

        if (info.steps.length === 0 && info.idx === 0) {
            const net = this.nets.find(n => n.id === netId);
            if (!net) return false;
            const at = net.rungs.findIndex(r => r.id === rungId);
            // [CHANGED v3.71.0] Opened from a rung that hangs from a trigger, or right above one, the new rung hangs from
            // that trigger too, so the rungs below it keep theirs.
            const rung = this.mkRung();
            if (at >= 0 && this.netLevel(net) === 'automation' && (this.hangs(net.rungs[at]) || this.hangs(net.rungs[at + 1]))) {
                rung.sharesHead = true;
            }
            net.rungs.splice(at < 0 ? net.rungs.length : at + 1, 0, rung);
            return true;
        }

        const i = Math.max(0, Math.min(isNaN(info.idx) ? arr.length : info.idx, arr.length));
        const at = arr[i];
        const prev = arr[i - 1];

        if (at && at.type === 'parallel') { at.branches.push([]); return true; }
        if (i === arr.length && prev && prev.type === 'parallel' && !prev.closed) { prev.branches.push([]); return true; }

        const tail = arr.splice(i);
        const par = this.mkEl('parallel');
        par.branches[0] = tail;
        par.branches[1] = [];
        par.closed = false;
        arr.push(par);
        return true;
    }

    closeBranchAt(netId, rungId, rel) {
        if (!rel) return false;
        const arr = this.getArrBySteps(netId, rungId, rel.steps);
        if (!arr) return false;
        const par = arr[rel.parIdx];
        if (!par || par.type !== 'parallel') return false;
        if (!par.branches[0]) par.branches[0] = [];

        if (rel.type === 'close-inner') {
            const moved = par.branches[0].splice(rel.cut);
            par.closed = true;
            if (moved.length) arr.splice(rel.parIdx + 1, 0, ...moved);
            return true;
        }
        if (rel.type === 'close-outer') {
            const count = rel.upto - rel.parIdx - 1;
            const swallowed = count > 0 ? arr.splice(rel.parIdx + 1, count) : [];
            par.branches[0].push(...swallowed);
            par.closed = true;
            return true;
        }
        return false;
    }

    wrapRange(netId, rungId, rel) {
        if (!rel || rel.type !== 'same-array') return false;
        const arr = this.getArrBySteps(netId, rungId, rel.steps);
        if (!arr || rel.from === rel.to) return false;
        const wrapped = arr.splice(rel.from, rel.to - rel.from);
        const par = this.mkEl('parallel');
        par.branches[0] = wrapped;
        par.branches[1] = [];
        par.closed = true;
        arr.splice(rel.from, 0, par);
        return true;
    }

    linkRungs(netId, aRung, aPath, bRung, bPath) {
        const net = this.nets.find(n => n.id === netId);
        if (!net || aRung === bRung) return false;
        if (!net.rungs.some(r => r.id === aRung) || !net.rungs.some(r => r.id === bRung)) return false;

        if (this.pathInfo(aPath).idx === 0 || this.pathInfo(bPath).idx === 0) return false;
        if (!this.getArrBySteps(netId, aRung, this.pathInfo(aPath).steps)) return false;
        if (!this.getArrBySteps(netId, bRung, this.pathInfo(bPath).steps)) return false;

        net.links = net.links || [];
        const same = (l) => (l.aRung === aRung && l.aPath === aPath && l.bRung === bRung && l.bPath === bPath) ||
                            (l.aRung === bRung && l.aPath === bPath && l.bRung === aRung && l.bPath === aPath);
        if (net.links.some(same)) return false;

        const order = net.rungs.map(r => r.id);
        const flip = order.indexOf(aRung) > order.indexOf(bRung);
        net.links.push({
            id: `k${this.lid++}`,
            aRung: flip ? bRung : aRung, aPath: flip ? bPath : aPath,
            bRung: flip ? aRung : bRung, bPath: flip ? aPath : bPath
        });
        return true;
    }

    removeLink(netId, linkId) {
        const net = this.nets.find(n => n.id === netId);
        if (!net || !net.links) return false;
        const before = net.links.length;
        net.links = net.links.filter(l => l.id !== linkId);
        return net.links.length !== before;
    }

    linkGroups(net) {
        const groups = [];
        const seen = {};
        const links = (net && net.links) || [];
        for (const rung of (net.rungs || [])) {
            if (seen[rung.id]) continue;
            const stack = [rung.id];
            const group = [];
            while (stack.length) {
                const id = stack.pop();
                if (seen[id]) continue;
                seen[id] = true;
                group.push(id);
                for (const l of links) {
                    if (l.aRung === id && !seen[l.bRung]) stack.push(l.bRung);
                    if (l.bRung === id && !seen[l.aRung]) stack.push(l.aRung);
                }
            }
            groups.push(group);
        }
        return groups;
    }

    mergeRungs(netId, upperRungId, upperPath, lowerRungId, lowerPath) {
        const net = this.nets.find(n => n.id === netId);
        if (!net || upperRungId === lowerRungId) return false;

        const upInfo = this.pathInfo(upperPath);
        const loInfo = this.pathInfo(lowerPath);
        const upArr = this.getArrBySteps(netId, upperRungId, upInfo.steps);
        const loArr = this.getArrBySteps(netId, lowerRungId, loInfo.steps);
        if (!upArr || !loArr) return false;

        const i = Math.max(0, Math.min(isNaN(upInfo.idx) ? upArr.length : upInfo.idx, upArr.length));
        const j = Math.max(0, Math.min(isNaN(loInfo.idx) ? loArr.length : loInfo.idx, loArr.length));

        if (i === 0) return false;

        const upHead = upArr.slice(0, i), upTail = upArr.slice(i);
        const loHead = loArr.slice(0, j), loTail = loArr.slice(j);
        if (!loHead.length && !loTail.length) return false;

        const merged = [];

        if (loHead.length) {
            const head = this.mkEl('parallel');
            head.branches[0] = upHead;
            head.branches[1] = loHead;
            head.closed = true;
            merged.push(head);
        } else {
            merged.push(...upHead);
        }

        if (loTail.length) {
            const tail = this.mkEl('parallel');
            tail.branches[0] = upTail;
            tail.branches[1] = loTail;
            tail.closed = false;
            merged.push(tail);
        } else {
            merged.push(...upTail);
        }

        upArr.length = 0;
        upArr.push(...merged);
        loArr.length = 0;

        const lowerRung = net.rungs.find(r => r.id === lowerRungId);
        if (lowerRung && (lowerRung.elements || []).length === 0 && net.rungs.length > 1) {
            const upperRung = net.rungs.find(r => r.id === upperRungId);
            if (upperRung && lowerRung.comment) {
                upperRung.comment = upperRung.comment
                    ? `${upperRung.comment}, or ${lowerRung.comment}`
                    : lowerRung.comment;
            }
            net.rungs = net.rungs.filter(r => r.id !== lowerRungId);
        }
        this.repairAST();
        return true;
    }

    repairAST() {
        const fixArr = (arr) => {
            if (!arr) return;
            for (let i = 0; i < arr.length; i++) {
                const el = arr[i];
                if (!el) continue;
                if (el.type === 'cmp_tpl') {
                    el.type = 'cmp_eq';
                    el.sourceA = String(el.sourceA || '').replace(/[{}]/g, '').trim().slice(0, 46);
                    el.sourceB = 'true';
                }
                // [ADDED v3.68.0] The TOF of "was on lately" was drawn as timer_tof, a type the palette does not have.
                if (el.type === 'timer_tof') el.type = 'timer_toff';
                if (el.type === 'schedule') {
                    const days = (el.weekdays || []).join(', ');
                    if (el.sourceA && el.sourceB) { el.type = 'cmp_rng'; el.sourceC = el.sourceB; el.sourceB = el.sourceA; el.sourceA = 'time'; el.kind = 'time'; }
                    else if (days) { el.type = 'cmp_eq'; el.sourceA = 'weekday'; el.sourceB = days; el.kind = 'date'; }
                    else { el.type = 'cmp_ge'; el.sourceB = el.sourceA || ''; el.sourceA = 'time'; el.kind = 'time'; }
                    delete el.weekdays;
                }
                if (el.type === 'native' || el.type === 'device') {
                    el.type = 'move';
                    el.mode = 'value';
                    el.service = el.service || el.title || '';
                    el.source = el.source || el.subtitle || '';
                    el.target = el.target || el.subtitle || '';
                    delete el.title; delete el.subtitle;
                }
                if (el.type === 'parallel') {
                    if (!el.branches) el.branches = [[], []];
                    if (!el.branches[0]) el.branches[0] = [];
                    if (!el.closed && i < arr.length - 1) {
                        const tail = arr.splice(i + 1);
                        el.branches[0].push(...tail);
                    }
                    for (let b of el.branches) fixArr(b);
                } else if (el.type === 'repeat') {
                    fixArr(el.sequence);
                }
            }
        };
        for (let net of this.nets) {
            // [ADDED v3.5.0] A net drawn before this version has no level. It gets one here, so the
            // rest of the editor never has to guess and the saved file says what it is.
            if (!net.level) net.level = 'automation';
            for (let rung of net.rungs) fixArr(rung.elements);
            if (net.links && net.links.length) {
                const ids = {};
                net.rungs.forEach(r => { ids[r.id] = true; });
                net.links = net.links.filter(l => ids[l.aRung] && ids[l.bRung] &&
                    this.getArrBySteps(net.id, l.aRung, this.pathInfo(l.aPath).steps) &&
                    this.getArrBySteps(net.id, l.bRung, this.pathInfo(l.bPath).steps));
            }
        }
    }

    findRung(netId, rungId) { const net = this.nets.find(n => n.id === netId); return net ? net.rungs.find(r => r.id === rungId) : null; }
    
    findElNode(elements, elId) {
        for (let el of elements) {
            if (el.id === elId) return el;
            if (el.type === 'parallel') { for (let b of el.branches) { let f = this.findElNode(b, elId); if (f) return f; } }
            if (el.type === 'repeat') { let f = this.findElNode(el.sequence, elId); if (f) return f; }
        }
        return null;
    }
    
    findEl(netId, rungId, elId) { return this.findElNode(this.findRung(netId, rungId)?.elements || [], elId); }

    getArrTarget(netId, rungId, pathStr) {
        const rung = this.findRung(netId, rungId);
        if (!rung) return null; let parts = String(pathStr).split('.'); let curList = rung.elements;
        for (let i = 0; i < parts.length - 1; i += 2) {
           let idx = parseInt(parts[i], 10);
           if (parts[i+1] === 'seq') curList = curList[idx].sequence;
           else { let bIdx = parseInt(parts[i+1].substring(1), 10); curList = curList[idx].branches[bIdx]; }
        }
        let finalIdx = parseInt(parts[parts.length - 1], 10);
        return { arr: curList, idx: finalIdx };
    }

    insertElement(netId, rungId, pathStr, type) {
        if (type === 'parallel') return this.openBranchAt(netId, rungId, pathStr);
        let tInfo = this.getArrTarget(netId, rungId, pathStr); if (!tInfo) return;
        tInfo.arr.splice(tInfo.idx, 0, this.mkEl(type));
    }

    copyElement(netId, rungId, elId) {
        const el = this.findEl(netId, rungId, elId);
        if (el) this.clipboard = JSON.parse(JSON.stringify(el));
        return !!el;
    }

    cutElement(netId, rungId, elId) {
        const el = this.findEl(netId, rungId, elId);
        if (el) { this.clipboard = JSON.parse(JSON.stringify(el)); this.removeElement(netId, rungId, elId); }
    }

    pasteElement(netId, rungId, pathStr) {
        if (!this.clipboard) return false;
        const newEl = JSON.parse(JSON.stringify(this.clipboard)); this._regenerateIds(newEl);
        let tInfo = this.getArrTarget(netId, rungId, pathStr);
        if (tInfo) { tInfo.arr.splice(tInfo.idx, 0, newEl); return true; }
        return false;
    }

    removeElement(netId, rungId, elId) {
        const rung = this.findRung(netId, rungId);
        if(rung) {
            const delRec = (arr) => {
                for(let i=0; i<arr.length; i++) {
                    if(arr[i].id === elId) { arr.splice(i,1); return true; }
                    if(arr[i].type === 'parallel') {
                        for(let b=0; b<arr[i].branches.length; b++) {
                            if(delRec(arr[i].branches[b])) {
                                if (arr[i].branches[b].length === 0) {
                                    arr[i].branches.splice(b, 1);
                                    if (arr[i].branches.length === 1) arr.splice(i, 1, ...arr[i].branches[0]);
                                    else if (arr[i].branches.length === 0) arr.splice(i, 1);
                                }
                                return true;
                            }
                        }
                    }
                    if(arr[i].type === 'repeat') { if(delRec(arr[i].sequence)) return true; }
                }
                return false;
            };
            delRec(rung.elements);
        }
    }

    _regenerateIds(el) {
        el.id = `e${this.eid++}`;
        if (el.type === 'parallel') el.branches.forEach(b => b.forEach(child => this._regenerateIds(child)));
        if (el.type === 'repeat') el.sequence.forEach(child => this._regenerateIds(child));
    }

    validateAST() {
        this.repairAST();
        const isAction = (el) => ['coil', 'coil_s', 'coil_r', 'coil_t', 'move', 'ctu', 'notify', 'repeat'].includes(el.type) || el.type.startsWith('math_');
        const isTriggerBlock = (el) => el.isTrigger;
        // [ADDED v3.5.0] The only thing a scene may hold: a coil that sets a switch, or a MOVE in
        // value mode that puts a number or a string on an entity. A MOVE that calls a service is a
        // sequence step, so it does not belong in a snapshot.
        // [CHANGED v3.30.0] A scene is a snapshot of end states. A toggle has no end state of its
        // own, it depends on what the thing happened to be, so it cannot belong to one.
        const isSceneAssign = (el) => ['coil', 'coil_s', 'coil_r'].includes(el.type) || (el.type === 'move' && (el.mode || 'value') === 'value');

        const checkPathStart = (elements) => {
             if (elements.length === 0) return;
             let firstEl = elements[0];
             if (firstEl.type === 'parallel') { firstEl.branches.forEach(b => checkPathStart(b)); } 
             else if (!isTriggerBlock(firstEl)) { firstEl.structuralError = 'Missing Trigger (First block must be set as Trigger)'; }
        };

        // [ADDED v3.5.0] A script and a scene are never started by the house, only by something that
        // calls them, so a block marked as a trigger is an error rather than a missing requirement.
        const checkNoTriggers = (elements, levelName) => {
            for (let el of elements || []) {
                if (el.type === 'parallel') { el.branches.forEach(b => checkNoTriggers(b, levelName)); continue; }
                if (el.type === 'repeat') checkNoTriggers(el.sequence, levelName);
                if (el.isTrigger) el.structuralError = `A ${levelName} cannot listen to events. Clear "Use as Trigger" on this block.`;
            }
        };

        // [ADDED v3.5.0] A scene has no flow and no time, so branches, loops, timers, waits,
        // contacts and comparisons all have no meaning inside one.
        const checkSceneOnly = (elements) => {
            for (let el of elements || []) {
                if (el.type === 'parallel') {
                    el.structuralError = 'A scene has no power flow, so branches are not allowed. Put the assignments on one rung.';
                    el.branches.forEach(b => checkSceneOnly(b));
                    continue;
                }
                if (el.type === 'repeat') {
                    el.structuralError = 'A scene has no order in time, so loops are not allowed.';
                    checkSceneOnly(el.sequence);
                    continue;
                }
                if (!isSceneAssign(el) && !el.structuralError) {
                    el.structuralError = 'A scene holds value assignments only (Coil or MOVE in value mode). Triggers, timers and comparisons are not allowed.';
                }
            }
        };

        const checkPathEnd = (elements) => {
            if (elements.length === 0) return;
            let lastEl = elements[elements.length - 1];
            // [ADDED v3.71.0] A wait is a step: the automation goes on with the next rung once it is over.
            if (lastEl.waitFor) return;

            if (lastEl.type === 'parallel') {
                if (!lastEl.closed) {
                    lastEl.branches.forEach(b => checkPathEnd(b));
                } else {
                    lastEl.structuralError = 'Missing Output Action after merged branch';
                }
            } else if (lastEl.type === 'repeat') {
                checkPathEnd(lastEl.sequence);
            } else if (!isAction(lastEl)) {
                lastEl.structuralError = 'Terminal Cap Error: Path must end with an Action block (Coil/Move/etc.)';
            }
        };

        // [ADDED v3.68.0] A wait is drawn with what it waits for, one block per branch, and the TON of its time
        // limit. Anything else inside one has no Home Assistant form, so it is marked and the save is refused.
        const checkWaits = (elements) => {
            for (const el of elements || []) {
                if (el.waitFor && el.type === 'parallel' && !el.waitOne) {
                    el.branches.forEach(b => b.forEach((x, i) => {
                        const fits = /^(contact_|cmp_|timer_)/.test(x.type) || x.type === 'parallel';
                        if (i > 0) x.structuralError = 'A wait goes on when ONE of these happens: give each its own branch, and put the next steps after the wait.';
                        else if (!fits) x.structuralError = 'Only what the wait waits for goes inside it: a contact, a CMP or the TON of its time limit.';
                    }));
                } else if (el.type === 'parallel') el.branches.forEach(checkWaits);
                else if (el.type === 'repeat') checkWaits(el.sequence);
            }
        };

        // [ADDED v3.95.5] A CMP = / not = against an entity Home Assistant reads as plain text: a sensor's state is never
        // "sensor.other", a person's never "zone.work" - the check would never hold, and nothing would say so (the user's
        // train reminder was saved with state: zone.work). In a condition an input helper is read as its value, and a
        // person in a zone is a zone condition; a trigger reads no helper, only a zone. And a CMP not = that starts an
        // automation on a state has no Home Assistant form.
        const SPECIAL_IN1 = new Set(['time', 'weekday', 'datetime', 'sun', 'time pattern']);
        const ENTITY_ID = /^[a-z_]+\.[a-z0-9_]+$/;
        // IN1 of several entities reads "binary_sensor.a +1": its first one says what it is.
        const ENTITY_FIRST = /^[a-z_]+\.[a-z0-9_]+/;
        const INPUT_HELPER = /^input_(select|text|number|boolean|datetime)\./;
        // [ADDED v3.95.5] What can never hold an entity's id as its state: a person or a tracker (home, a zone's name), on
        // and off, open and closed, a number, a date. A dropdown, a text, a select or a sensor may - "which speaker" is
        // media_player.kitchen - and is never checked (the second pass of the review of the release, RULE 41).
        const FIXED_STATE = new Set(['person', 'device_tracker', 'binary_sensor', 'switch', 'light', 'fan', 'cover', 'lock',
            'climate', 'media_player', 'vacuum', 'alarm_control_panel', 'input_boolean', 'sun', 'weather', 'water_heater',
            'humidifier', 'valve', 'siren', 'update', 'timer', 'schedule', 'automation', 'script', 'remote', 'lawn_mower',
            'input_number', 'number', 'counter', 'input_datetime', 'date', 'time', 'datetime', 'zone']);
        // [ADDED v3.95.5] The keys a zone check has: a person's state check with another (for, attribute ...) cannot be
        // one without losing it - the review of the release (RULE 41).
        // A for is the TON drawn after the block (forTon below), gone when the TON is.
        const ZONE_CONDITION_KEYS = new Set(['condition', 'entity_id', 'state', 'alias', 'enabled', 'for']);
        const ZONE_TRIGGER_KEYS = new Set(['trigger', 'platform', 'entity_id', 'to', 'id', 'alias', 'enabled', 'for']);
        // [ADDED v3.95.5] The TON that is a block's for - as headLength and the compiler's _is_for_timer read it. A TON
        // without the marker is a delay.
        const forTon = (x) => !!x && x.type === 'timer_ton' && !!(x.isFor || x.forOf);
        const ZONE_OPTIONS = 'A person in a zone: Home Assistant\'s zone check has no "for" and no other option of this one. Compare with the zone\'s name as the person\'s state says it (for example home), or take the option away.';
        const stateCheckOf = (raw) => {
            if (!raw || typeof raw !== 'object') return null;
            const kids = raw.condition === 'not' ? raw.conditions : (raw.condition === undefined ? raw.not : null);
            const node = Array.isArray(kids) && kids.length === 1 ? kids[0] : raw;
            return node && typeof node === 'object' && (node.condition === 'state' || node.trigger === 'state' || node.platform === 'state') ? node : null;
        };
        const otherKeys = (node, allowed) => !!node && Object.keys(node).some(k => !allowed.has(k));
        const checkLiteral = (elements) => {
            (elements || []).forEach((el, i) => {
                if (el.type === 'parallel') { (el.branches || []).forEach(checkLiteral); return; }
                if (el.type === 'repeat') { checkLiteral(el.sequence); return; }
                if (!['cmp_eq', 'cmp_ne'].includes(el.type) || el.tplId || el.deviceNode || el.structuralError) return;
                // [CHANGED v3.95.5] 0 is a value: only no value at all is an empty IN2 (RULE 33a.4).
                const a = String(el.sourceA || ''), b = el.sourceB === undefined || el.sourceB === null ? '' : String(el.sourceB).trim();
                if (SPECIAL_IN1.has(a) || !ENTITY_FIRST.test(a)) return;
                const zone = b.startsWith('zone.') && /^(person|device_tracker)\./.test(a);
                const fixed = FIXED_STATE.has(a.split('.')[0]);
                // [ADDED v3.95.5] IN2 emptied: the check it was drawn from had a state - an empty one never holds.
                const drawnFrom = stateCheckOf(el.raw);
                const had = drawnFrom ? (drawnFrom.condition === 'state' ? drawnFrom.state : drawnFrom.to) : undefined;
                if (!b && had !== undefined && had !== null && String(had) !== '') {
                    el.structuralError = 'IN2 is empty: say the state it compares with.';
                    return;
                }
                const ofAttribute = !!drawnFrom && drawnFrom.attribute !== undefined;
                const held = forTon(elements[i + 1]);
                if (el.isTrigger) {
                    if (zone) {
                        if (held || otherKeys(stateCheckOf(el.raw), ZONE_TRIGGER_KEYS)) el.structuralError = ZONE_OPTIONS;
                        return;
                    }
                    if (el.type === 'cmp_ne') el.structuralError = 'LIBI does not write a CMP ≠ that starts an automation on a state. Say the state it changes to (CMP =), or use a P contact for any change.';
                    else if (fixed && ENTITY_ID.test(b) && !ofAttribute) el.structuralError = `IN2 is ${b}: a trigger compares the new state with that text, which it never is. Use a value.`;
                } else if (zone && el.type === 'cmp_eq') {
                    // Its TON is its for, and a zone check has none.
                    if (otherKeys(stateCheckOf(el.raw), ZONE_CONDITION_KEYS) || held) el.structuralError = ZONE_OPTIONS;
                } else if (el.type === 'cmp_ne' && held) {
                    el.structuralError = 'A CMP ≠ held for a time has no form in Home Assistant: its check would say "not (that state for that time)". Use CMP = with the states it may be, or take the TON away.';
                } else if (zone) {
                    if (otherKeys(stateCheckOf(el.raw), ZONE_CONDITION_KEYS)) el.structuralError = ZONE_OPTIONS;
                } else if (fixed && ENTITY_ID.test(b) && !INPUT_HELPER.test(b) && !ofAttribute) {
                    el.structuralError = `IN2 is ${b}: Home Assistant compares the state with that text, which it never is. Use a value, or a helper (input_select, input_number, input_text, input_boolean, input_datetime).`;
                }
            });
        };

        this.nets.forEach(net => {
            const level = this.netLevel(net);
            const linked = {};
            (net.links || []).forEach(l => { linked[l.aRung] = true; linked[l.bRung] = true; });
            const groups = this.linkGroups(net);
            const groupEndsWell = {};
            groups.forEach(g => {
                const ok = g.some(rid => {
                    const r = net.rungs.find(x => x.id === rid);
                    if (!r || !r.elements.length) return false;
                    const last = r.elements[r.elements.length - 1];
                    return isAction(last) || !!last.waitFor || (last.type === 'parallel' && !last.closed);
                });
                g.forEach(rid => { groupEndsWell[rid] = ok; });
            });

            net.rungs.forEach((rung, idx) => {
                const clearErrs = (arr) => {
                    arr.forEach(e => {
                        e.structuralError = null;
                        if (e.type === 'parallel') e.branches.forEach(clearErrs);
                        if (e.type === 'repeat') clearErrs(e.sequence);
                    });
                };
                clearErrs(rung.elements);
                // [CHANGED v3.5.0] The level of the net chooses the rule set. An automation keeps the
                // rules it always had, a script drops the trigger requirement and forbids triggers,
                // and a scene forbids everything that is not a value assignment.
                if (level === 'automation') {
                    // [CHANGED v3.71.0] A rung that hangs from the trigger above starts with no trigger of its own.
                    if (!this.hangs(rung)) checkPathStart(rung.elements);
                    else if (this.headIndex(net, idx) < 0 && rung.elements.length) {
                        rung.elements[0].structuralError = 'This rung hangs from the trigger above it, and no rung above starts with one: make its first block the trigger.';
                    }
                } else {
                    checkNoTriggers(rung.elements, level);
                    if (level === 'scene') checkSceneOnly(rung.elements);
                }
                checkWaits(rung.elements);
                if (level !== 'scene') checkLiteral(rung.elements);
                if (!linked[rung.id]) {
                    checkPathEnd(rung.elements);
                } else if (!groupEndsWell[rung.id] && rung.elements.length) {
                    const last = rung.elements[rung.elements.length - 1];
                    last.structuralError = 'Terminal Cap Error: none of the connected rungs ends with an Action block';
                }
            });
        });
    }
}