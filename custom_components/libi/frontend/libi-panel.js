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
 * LIBI Panel - Main View
 * v3.5.0
 */
// [ADDED v3.5.0 | 2026-08-20] Purpose: Integrated the full SVG logo with the original house, electronic circuit traces, 3-rung ladder, and aligned text into the header title.
import { LibiCore } from './libi-core.js?v=3.11.0';
import { getStyles } from './libi-css.js?v=3.11.0';
import { LIBI_ICONS } from './libi-svg.js?v=3.11.0';
import { LibiOnline } from './libi-online.js?v=3.11.0';

class LibiPanel extends HTMLElement {
    constructor() {
        super(); 
        this.attachShadow({ mode: 'open' }); 
        this.core = new LibiCore();
        this.online = new LibiOnline();
        this._editMode = true; 
        this._initialized = false; 
        this._astLoaded = false;
        this._inspectedEl = null; 
        this._inspectedNetYaml = null; 
        this._previewYamlContent = '';
        this._floatingMenu = null; 
        this._draggedEl = null; 
        this._modal = null; 
        this._automationList = []; 
        this._activeNetForLoad = null;
    }

    set hass(hass) { 
        this._hass = hass; 
        // [ADDED v3.9.0] The core resolves names while it measures the label boxes, so it needs the
        // same hass the panel has.
        if (this.core) this.core.hass = hass; 
        if (!this._astLoaded && this._hass && this._hass.connection) { 
            this._astLoaded = true; 
            this._loadFromBackend(); 
        } 
        
        if (this._inspectedEl && this.shadowRoot) { 
            this.shadowRoot.querySelectorAll('ha-entity-picker, ha-selector, ha-device-picker, ha-area-picker').forEach(picker => { 
                picker.hass = this._hass; 
            }); 
        } 

        if (this.online && this.online.enabled && this._initialized) this._paintOnline();
    }

    connectedCallback() { 
        this.tabIndex = 0; 
        this._keyHandler = (e) => {
            if (e.ctrlKey && e.key.toLowerCase() === 'z') {
                e.preventDefault();
                if (e.shiftKey) { if (this.core.redo()) this._render(); }
                else { if (this.core.undo()) this._render(); }
            }
            if (e.ctrlKey && e.key.toLowerCase() === 'y') {
                e.preventDefault();
                if (this.core.redo()) this._render();
            }
        };
        window.addEventListener('keydown', this._keyHandler);
        
        if (typeof this._render !== 'function') {
            console.error("❌ CRITICAL ERROR: _render method is missing!");
            this.innerHTML = `<div style="padding:20px; color:red; font-size:18px;"><b>Error:</b> File libi-panel.js is incomplete.</div>`;
            return;
        }
        this._render(); 
    }

    disconnectedCallback() {
        clearInterval(this._onlineTimer);
        if (this._keyHandler) window.removeEventListener('keydown', this._keyHandler);
    }

    async _loadFromBackend() { 
        try { 
            const localDraft = localStorage.getItem('libi_draft');
            if (localDraft) {
                this.core.nets = JSON.parse(localDraft);
                this.core.syncCounters();
            } else {
                const response = await this._hass.connection.sendMessagePromise({ type: 'libi/load_automation' }); 
                if (response && response.nets && response.nets.length > 0) { 
                    this.core.nets = response.nets; 
                    this.core.syncCounters(); 
                } else if (this.core.nets.length === 0) { 
                    this.core.nets.push(this.core.mkNet('Net 1')); 
                } 
            }
        } catch (err) { 
            console.warn("Load error, falling back to default", err);
            if (this.core.nets.length === 0) { this.core.nets.push(this.core.mkNet('Net 1')); }
        } 
        this.core.repairAST();
        this._initialized = true; 
        this.core.history = [JSON.stringify(this.core.nets)]; 
        this.core.historyIdx = 0; 
        this._render(); 
    }
    
    _saveToBackend() {
        this.core.validateAST(); 
        this._render(); 
        
        if (!this._hass || !this._hass.connection) return;
        
        const hasErrors = this.shadowRoot.querySelectorAll('.has-error').length > 0;
        if (hasErrors) { 
            alert('Cannot compile: Syntax/Structural errors found (Missing Triggers, Missing Actions, or Missing Variables). Please fix red blocks.'); 
            return; 
        }
        
        this._hass.connection.sendMessagePromise({ 
            type: 'libi/save_automation', 
            nets: this.core.nets 
        })
        // [CHANGED v3.5.0] The backend now merges into Home Assistant's own automations.yaml,
        // scripts.yaml and scenes.yaml and reloads the domains it touched, so it reports what it
        // wrote and which files it had to leave alone. Show that instead of a fixed sentence.
        .then(res => {
            const r = res || {};
            const errs = r.errors || [];
            alert(r.message || 'AST Saved & Compiled successfully!');
            if (errs.length) console.warn('LIBI save reported problems', errs);
        })
        .catch(err => { console.error("Failed to save AST", err); alert('Save failed: ' + (err && err.message ? err.message : err)); });
    }

    async _fetchAutomationsList() {
        if (!this._hass || !this._hass.connection) return;
        try {
            const response = await this._hass.connection.sendMessagePromise({ type: 'libi/list_automations' });
            if (response && response.automations) { 
                this._automationList = response.automations; 
                this._modal = 'list_automations'; 
                this._render(); 
            }
        } catch (err) { alert("Failed to fetch automations from HA: " + err.message); }
    }

    async _importAutomation(haId) {
        if (!this._hass || !this._hass.connection) return;
        try {
            const response = await this._hass.connection.sendMessagePromise({ type: 'libi/get_automation', automation_id: haId });
            if (response && response.net) {
                const idx = this.core.nets.findIndex(n => n.id === this._activeNetForLoad);
                if (idx !== -1) {
                    const originalNetId = this.core.nets[idx].id;
                    this._verify = this._verify || {};
                    if (response.verify && response.verify.ok === false) this._verify[originalNetId] = response.verify;
                    else delete this._verify[originalNetId];
                    this.core.nets[idx] = response.net;
                    this.core.nets[idx].id = originalNetId;
                    this.core.syncCounters();
                    this.core.repairAST();
                    this.core.pushHistory();
                }
                this._modal = null; this._activeNetForLoad = null; this._render();
            }
        } catch (err) { alert("Failed to load automation AST: " + err.message); }
    }

    _netNoticeHtml(net) {
        const rep = (this._verify || {})[net.id];
        if (!rep || rep.ok) return '';
        const items = (rep.issues || []).slice(0, 10).map(i => `<li>${this._esc(i)}</li>`).join('');
        const more = (rep.count || 0) > 10 ? `<div class="net-notice-more">and ${rep.count - 10} more</div>` : '';
        return `
        <div class="net-notice" data-nid="${net.id}">
            <div class="net-notice-head">
                <span>⚠️ This automation does not compile back to itself yet</span>
                <button class="net-notice-x" data-nid="${net.id}" title="Hide">✕</button>
            </div>
            <div class="net-notice-body">It is safe to look at and to edit, but saving would change the parts listed here.</div>
            <ul class="net-notice-list">${items}</ul>
            ${more}
        </div>`;
    }

    _getFanIcon(type, badge = '') {
        if (type === 'delete' || type === 'delete_block') return `<svg viewBox="0 0 24 24" style="width:20px;height:20px;"><path fill="currentColor" d="M19,4H15.5L14.5,3H9.5L8.5,4H5V6H19M6,19A2,2 0 0,0 8,21H16A2,2 0 0,0 18,19V7H6V19Z"/></svg>`;
        if (type === 'parallel') return `<span style="font-weight:900;font-size:16px;">⮧</span>`;
        if (type === 'unclose') return `<span style="font-weight:900;font-size:16px;" title="Unlink / Open Branch">✂️</span>`;
        if (type === 'timer_ton') return `<span style="font-weight:800;font-size:12px;">TON</span>`;
        if (type === 'move') return `<span style="font-weight:800;font-size:12px;">MOV</span>`;
        if (type === 'repeat') return `<span style="font-weight:900;font-size:14px;color:#9c27b0;">[R]</span>`; 
        
        let svgKey = LIBI_ICONS[type] ? type
                   : (type.startsWith('contact') ? 'contact_no' : (type.startsWith('coil') ? 'coil' : 'custom'));
        const showBadge = badge && !LIBI_ICONS[type];
        return `<div style="width: 28px; height: 18px; position: relative; display: flex; align-items: center; justify-content: center;">${LIBI_ICONS[svgKey] || LIBI_ICONS.custom}${showBadge ? `<span style="position:absolute; font-size:8px; font-weight:900; color:var(--primary-text-color, #212121);">${badge}</span>` : ''}</div>`;
    }

    _palIcon(type) {
        const glyph = {
            cmp_eq: '=', cmp_ne: '≠', cmp_gt: '>', cmp_lt: '<', cmp_ge: '≥', cmp_le: '≤', cmp_rng: '↔',
            math_add: '+', math_sub: '−', math_mul: '×', math_div: '÷',
            timer_ton: 'TON', timer_toff: 'TOF', repeat: 'REP', parallel: '⑂', ctu: 'CTU', wait: 'WAIT',
            move: 'MOV', move_value: 'MOV', move_notify: 'MSG', move_tts: 'TTS', move_both: 'M+T'
        }[type];
        if (glyph) return `<small>${glyph}</small>`;
        return this._getFanIcon(type);
    }

    _palBtn(b) {
        const cls = ['pal-btn', b.danger ? 'danger' : '', b.selected ? 'selected' : '', b.cls || ''].join(' ').trim();
        return `<button class="${cls}" data-action="${b.action}" data-val="${b.val || ''}" title="${b.title || b.val || b.action}">${b.icon || this._palIcon(b.val)}</button>`;
    }

    _calculateMenuBounds(fm) {
        let yPos = fm.y - 10;
        let transformStyle = '';
        let arrowStyle = '';
        
        if (fm.y < 120 && fm.bottom) {
            yPos = fm.bottom + 10;
            transformStyle = 'transform: translate(-50%, 0);';
            arrowStyle = `
                <style>
                    #fmBox::after {
                        bottom: auto !important;
                        top: -7px !important;
                        border-right: none !important;
                        border-bottom: none !important;
                        border-left: 1px solid var(--divider-color, #e0e0e0) !important;
                        border-top: 1px solid var(--divider-color, #e0e0e0) !important;
                    }
                </style>
            `;
        }
        return { yPos, transformStyle, arrowStyle };
    }

    _renderFloatingMenu() {
        const fm = this._floatingMenu;
        if (!fm) return '';
        let choices = [];
        let actions = [];

        if (fm.type === 'dot') {
            ['contact_no', 'contact_nc', 'contact_p', 'cmp_eq', 'cmp_gt', 'cmp_lt', 'math_add', 'math_div',
             'move', 'coil', 'coil_s', 'coil_r', 'timer_ton', 'ctu', 'repeat', 'parallel']
                .forEach(v => choices.push({ action: 'add', val: v }));

            if (this.core.clipboard) actions.push({ action: 'paste', icon: '<small>PASTE</small>', title: 'Paste' });

            const match = fm.path.match(/^(.*)\.b(\d+)\.\d+$/);
            if (match) {
                const pInfo = this.core.getArrTarget(fm.netId, fm.rungId, match[1]);
                const par = pInfo && pInfo.arr[pInfo.idx];
                if (par && par.closed) actions.push({ action: 'unclose_block', icon: '<small>UNLINK</small>', title: 'Open this block again' });
                const bIdx = parseInt(match[2], 10);
                const emptyBranch = par && (par.branches[bIdx] || []).length === 0;
                if (bIdx > 0) actions.push({ action: 'delete_branch', icon: `<small>${emptyBranch ? 'DELETE DOT' : 'DELETE BRANCH'}</small>`, danger: true, title: 'Remove this branch' });
                else actions.push({ action: 'delete_block', icon: '<small>DELETE BLOCK</small>', danger: true, title: 'Remove the whole parallel block' });
            }
        } else if (fm.type === 'element') {
            const el = this.core.findEl(fm.netId, fm.rungId, fm.elId);
            if (!el) return '';
            const t = el.type;
            const pick = (list) => list.forEach(v => choices.push({ action: 'mod', val: v, selected: v === t }));

            if (t.startsWith('contact')) pick(['contact_no', 'contact_nc', 'contact_p', 'contact_n']);
            else if (t.startsWith('coil')) pick(['coil', 'coil_s', 'coil_r']);
            else if (t.startsWith('timer')) pick(['timer_ton', 'timer_toff']);
            else if (t.startsWith('cmp')) pick(['cmp_eq', 'cmp_ne', 'cmp_gt', 'cmp_lt', 'cmp_ge', 'cmp_le', 'cmp_rng']);
            else if (t.startsWith('math')) pick(['math_add', 'math_sub', 'math_mul', 'math_div']);
            else if (t === 'move') {
                ['value', 'notify', 'tts', 'both'].forEach(m => choices.push({
                    action: 'mode', val: m, selected: (el.mode || 'value') === m,
                    icon: this._palIcon('move_' + m), title: 'MOVE ' + m
                }));
            }

            const canTrigger = t.startsWith('contact') || t.startsWith('cmp');
            if (canTrigger) actions.push({ action: 'trigger', icon: '<small>TRIGGER</small>', cls: el.isTrigger ? 'trigger-on' : '', title: 'Use as the trigger of this rung' });
            actions.push({ action: 'cut', icon: '<small>CUT</small>' });
            actions.push({ action: 'copy', icon: '<small>COPY</small>' });
            actions.push({ action: 'delete', icon: '<small>DELETE</small>', danger: true });
        }

        const rows = [];
        if (choices.length) rows.push(`<div class="palette-row">${choices.map(b => this._palBtn(b)).join('')}</div>`);
        if (choices.length && actions.length) rows.push('<div class="palette-sep"></div>');
        if (actions.length) rows.push(`<div class="palette-row">${actions.map(b => this._palBtn(b)).join('')}</div>`);
        if (!rows.length) return '';

        const x = Math.min(Math.max(fm.x, 190), window.innerWidth - 190);
        const arrow = Math.max(12, Math.min(360, 180 + (fm.x - x)));
        
        const bounds = this._calculateMenuBounds(fm);
        
        return `<div class="fm-overlay" id="fmOverlay"></div>${bounds.arrowStyle}<div class="palette" style="left:${x}px; top:${bounds.yPos}px; --arrow-x:${arrow}px; ${bounds.transformStyle}" id="fmBox">${rows.join('')}</div>`;
    }

    _render() {
        if (!this._initialized) return;

        localStorage.setItem('libi_draft', JSON.stringify(this.core.nets));

        const netsHtml = this.core.nets.map((n, i) => this._netHtml(n, i)).join('');
        const sidebarHtml = this._renderSidebar();
        const fanMenuHtml = this._renderFloatingMenu();
        
        let modalHtml = '';
        if (this._modal === 'list_automations') {
            const items = this._automationList.map(a => `<div class="auto-item" data-id="${a.id}"><div class="auto-item-name">${a.name}</div><div class="auto-item-id">ID: ${a.id}</div></div>`).join('');
            modalHtml = `<div class="modal-overlay" id="modalOverlay"><div class="modal" style="width: 500px;"><h2 class="modal-title">Select HA Automation</h2><p style="font-size:13px; color:#757575; margin:0;">Choose an automation to load into this Net.</p><div class="auto-list" style="max-height:50vh;">${items || '<div style="padding:16px;text-align:center;">No automations found.</div>'}</div><div class="modal-actions"><button class="btn btn-ghost" id="closeModalBtn">Cancel</button></div></div></div>`;
        } else if (this._modal === 'pick_level') {
            // [ADDED v3.5.0] A new net says what kind of logic it is before it exists, because the kind
            // decides which rules the linter applies and which file the net is compiled into.
            const levels = [
                { id: 'automation', icon: '\u26A1', title: 'Automation', desc: 'Reactive logic. Listens to the house and answers on its own. Needs a trigger and an action.' },
                { id: 'script', icon: '\uD83D\uDCDC', title: 'Script', desc: 'A subroutine. Runs from start to end when something calls it. No triggers, timers and loops allowed.' },
                { id: 'scene', icon: '\uD83C\uDFAC', title: 'Scene', desc: 'A snapshot. Value assignments only, applied at once. No triggers, no timing, no conditions.' },
            ];
            const items = levels.map(l => `<div class="auto-item level-item" data-level="${l.id}"><div class="auto-item-name">${l.icon} ${l.title}</div><div class="auto-item-id">${l.desc}</div></div>`).join('');
            modalHtml = `<div class="modal-overlay" id="modalOverlay"><div class="modal" style="width: 540px;"><h2 class="modal-title">What kind of logic do you want to create?</h2><p style="font-size:13px; color:#757575; margin:0;">The kind cannot be guessed later, so LIBI asks for it now.</p><div class="auto-list" style="max-height:60vh;">${items}</div><div class="modal-actions"><button class="btn btn-ghost" id="closeModalBtn">Cancel</button></div></div></div>`;
        } else if (this._modal === 'logs') {
            modalHtml = `<div class="modal-overlay" id="modalOverlay"><div class="modal" style="width: 800px; max-width: 95vw;"><h2 class="modal-title">🐞 System Logs & AST Terminal</h2><textarea readonly rows="20" style="width:100%; font-family:monospace; font-size:12px; padding:12px; box-sizing:border-box; background:#1e1e1e; color:#00ff00; border:none; border-radius:4px; outline:none; resize:none;">${JSON.stringify(this.core.nets, null, 2)}</textarea><div class="modal-actions"><button class="btn btn-primary" id="closeModalBtn">Close Terminal</button></div></div></div>`;
        }

        this.shadowRoot.innerHTML = `
        <style>${getStyles()}</style>
        <div class="panel-layout">
            <div class="header">
                <div class="header-title" style="display: flex; align-items: center;">
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 350 110" style="height: 38px; width: auto;">
                        <defs>
                            <linearGradient id="logoBgGrad" x1="0%" y1="0%" x2="0%" y2="100%">
                                <stop offset="0%" stop-color="#11b3fa" />
                                <stop offset="100%" stop-color="#0050d2" />
                            </linearGradient>
                            <filter id="logoShadow" x="-20%" y="-20%" width="140%" height="140%">
                                <feDropShadow dx="0" dy="2" stdDeviation="2" flood-color="#001133" flood-opacity="0.3"/>
                            </filter>
                            <style>
                                .logo-text-main { fill: #212121; font-weight: 900; font-family: system-ui, -apple-system, sans-serif; }
                                .logo-text-sub { fill: #555555; font-weight: 800; font-family: system-ui, -apple-system, sans-serif; }
                                @media (prefers-color-scheme: dark) {
                                    .logo-text-main { fill: #ffffff; }
                                    .logo-text-sub { fill: #cccccc; }
                                }
                            </style>
                        </defs>
                        
                        <!-- House & Electronics Graphic -->
                        <g transform="translate(5, 5) scale(0.65)">
                            <path d="M 200 25 L 75 116 A 10 10 0 0 0 70 124 L 70 255 A 15 15 0 0 0 85 270 L 315 270 A 15 15 0 0 0 330 255 L 330 124 A 10 10 0 0 0 325 116 L 305 101 L 305 55 L 280 55 L 280 83 Z" fill="url(#logoBgGrad)" />
                            <g stroke="#001133" stroke-width="4.5" fill="transparent" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M 105 115 L 125 130 L 163 130" /><circle cx="105" cy="115" r="7" />
                                <path d="M 85 165 L 120 165 L 140 185 L 157 185" /><circle cx="85" cy="165" r="7" />
                                <path d="M 105 220 L 130 220 L 145 205 L 153 205" /><circle cx="105" cy="220" r="7" />
                                <path d="M 295 115 L 275 130 L 237 130" /><circle cx="295" cy="115" r="7" />
                                <path d="M 315 165 L 280 165 L 260 185 L 243 185" /><circle cx="315" cy="165" r="7" />
                                <path d="M 295 220 L 270 220 L 255 205 L 247 205" /><circle cx="295" cy="220" r="7" />
                            </g>
                            <g filter="url(#logoShadow)" fill="#ffffff">
                                <polygon points="178,50 148,270 160,270 190,50" />
                                <polygon points="222,50 252,270 240,270 210,50" />
                                <polygon points="171,100 229,100 227,110 169,110" />
                                <polygon points="163,160 237,160 235,170 161,170" />
                                <polygon points="155,220 245,220 243,230 153,230" />
                            </g>
                        </g>

                        <!-- LIBI Typography -->
                        <g transform="translate(130, 48)">
                            <!-- L -->
                            <path d="M 0 0 L 11 0 L 11 27 L 27 27 L 27 36 L 0 36 Z" class="logo-text-main" />
                            <!-- I -->
                            <rect x="35" y="0" width="11" height="36" class="logo-text-main" />
                            <!-- B -->
                            <path d="M 52 0 L 73 0 C 85 0 89 6 89 14 C 89 20 83 23 76 25 C 84 27 89 31 89 38 C 89 45 83 45 73 45 L 52 45 Z M 62 8 L 62 17 L 72 17 C 76 17 78 15 78 12 C 78 9 76 8 72 8 Z M 62 25 L 62 37 L 73 37 C 78 37 80 34 80 31 C 80 28 78 25 73 25 Z" class="logo-text-main" fill-rule="evenodd" />
                            <!-- i (body) -->
                            <rect x="97" y="14" width="11" height="22" class="logo-text-main" />
                            <!-- i (blue dot) -->
                            <rect x="97" y="0" width="11" height="9" rx="2" fill="#11b3fa" />
                            
                            <!-- Subtitle aligned precisely to the bottom baseline -->
                            <text x="0" y="47" font-size="7.5" letter-spacing="0.5" class="logo-text-sub">
                                LADDER INTERFACE <tspan fill="#11b3fa">&amp;</tspan> BUILDING INTELLIGENCE
                            </text>
                        </g>
                    </svg>
                </div>
                <div class="header-acts">
                    <button class="ha-icon-btn" id="undoBtn" title="Undo (Ctrl+Z)">↩️</button>
                    <button class="ha-icon-btn" id="redoBtn" title="Redo (Ctrl+Y)">↪️</button>
                    <button class="ha-icon-btn" id="logsBtn" title="Terminal / Logs">🐞</button>
                    <button class="ha-icon-btn" id="collapseAllBtn" title="${this.core.nets.every(n => n.collapsed) ? 'Expand every net' : 'Collapse every net'}">${this.core.nets.every(n => n.collapsed) && this.core.nets.length ? '⤢' : '⤡'}</button>
                    <button class="ha-text-btn ${this.online.enabled ? 'online-on' : ''}" id="onlineBtn" title="Watch the automations run">${this.online.enabled ? '🟢 ONLINE' : '⚪ ONLINE'}</button>
                    <button class="ha-text-btn danger" id="clearAllBtn">🗑️ CLEAR ALL NETS</button>
                    <button class="ha-text-btn" id="saveBtn" style="font-weight:bold;">💾 SAVE & COMPILE</button>
                </div>
            </div>
            <div class="main-content">
                <div class="canvas">${this.core.nets.length ? '' : `
                    <div class="canvas-empty">
                        <div class="canvas-empty-text">No automation on the canvas yet</div>
                        <button class="ha-text-btn add-net-btn" id="addNetTop">➕ ADD NET</button>
                    </div>`}${netsHtml}${this.core.nets.length ? `
                    <button class="ha-text-btn add-net-btn" id="addNetBottom">➕ ADD NET</button>` : ''}</div>
                <div class="sidebar" id="sidebarContainer">${sidebarHtml}</div>
            </div>
        </div>
        ${fanMenuHtml}
        ${modalHtml}
        <svg id="dragOverlay" style="position:fixed; top:0; left:0; width:100vw; height:100vh; pointer-events:none; z-index:9999; display:none;">
            <path id="dragPath" stroke="#03a9f4" stroke-width="3" fill="none" stroke-dasharray="4" />
        </svg>
        `;
        
        this._bindEvents();
        this._injectNativePickers(); 
        this._paintOnline();
    }

    _paintOnline() {
        if (!this.online) return;
        try {
            this.online.paint(this.shadowRoot, this.core.nets, this._hass);
        } catch (err) {
            console.warn('[libi] online paint failed', err);
        }
        if (this.online.enabled) {
            clearInterval(this._onlineTimer);
            this._onlineTimer = setInterval(() => this._paintOnline(), 1000);
        } else {
            clearInterval(this._onlineTimer);
            this._onlineTimer = null;
        }
    }

    _renderSidebar() {
        if (this._inspectedNetYaml) {
            const net = this.core.nets.find(n => n.id === this._inspectedNetYaml);
            if (!net) return '';
            return `<div class="sidebar-hdr">Net YAML: ${net.name}</div><div class="sidebar-body" style="padding:0; display:flex; flex-direction:column; background:#1e1e1e;"><textarea class="yaml-preview-box" readonly>${this._previewYamlContent}</textarea><div style="padding: 16px;"><button class="btn btn-ghost" id="closeYamlSidebar" style="width:100%; color:white; border-color:#555;">Close YAML Preview</button></div></div>`;
        }

        if (!this._inspectedEl) {
            return `<div class="sidebar-hdr">Inspector</div><div class="sidebar-body"><p style="color:#757575;">Select any element on the canvas to view and edit its properties.</p></div>`;
        }
        
        const el = this.core.findEl(this._inspectedEl.netId, this._inspectedEl.rungId, this._inspectedEl.elId);
        if (!el) return '';

        // [ADDED v3.5.0] The inspector needs the level of the net the element sits in, because a
        // script and a scene have no trigger to offer.
        const elLevel = this.core.netLevel(this.core.nets.find(n => n.id === this._inspectedEl.netId));

        return `
            <div class="sidebar-hdr">Element Properties</div>
            <div class="sidebar-body" id="inspectorBody">
                <div class="fgrp">
                    <label>Block Type</label>
                    <select id="propType">
                        <option value="contact_no" ${el.type === 'contact_no' ? 'selected' : ''}>Contact (NO)</option>
                        <option value="contact_nc" ${el.type === 'contact_nc' ? 'selected' : ''}>Contact (NC)</option>
                        <option value="contact_p" ${el.type === 'contact_p' ? 'selected' : ''}>Positive Edge (P)</option>
                        <option value="contact_n" ${el.type === 'contact_n' ? 'selected' : ''}>Negative Edge (N)</option>
                        <option value="coil" ${el.type === 'coil' ? 'selected' : ''}>Coil (Output)</option>
                        <option value="coil_s" ${el.type === 'coil_s' ? 'selected' : ''}>Set Coil (S)</option>
                        <option value="coil_r" ${el.type === 'coil_r' ? 'selected' : ''}>Reset Coil (R)</option>
                        <option value="timer_ton" ${el.type === 'timer_ton' ? 'selected' : ''}>Timer (TON)</option>
                        <option value="timer_toff" ${el.type === 'timer_toff' ? 'selected' : ''}>Timer (TOF)</option>
                        <option value="ctu" ${el.type === 'ctu' ? 'selected' : ''}>Counter Up (CTU)</option>
                        <option value="repeat" ${el.type === 'repeat' ? 'selected' : ''}>Repeat Loop</option>
                        <option value="move" ${el.type === 'move' ? 'selected' : ''}>Assign / Exec (MOVE)</option>
                        <option value="math_add" ${el.type === 'math_add' ? 'selected' : ''}>Math (ADD +)</option>
                        <option value="math_sub" ${el.type === 'math_sub' ? 'selected' : ''}>Math (SUB −)</option>
                        <option value="math_mul" ${el.type === 'math_mul' ? 'selected' : ''}>Math (MUL ×)</option>
                        <option value="math_div" ${el.type === 'math_div' ? 'selected' : ''}>Math (DIV ÷)</option>
                        <option value="cmp_gt" ${el.type === 'cmp_gt' ? 'selected' : ''}>Compare (GT >)</option>
                        <option value="cmp_lt" ${el.type === 'cmp_lt' ? 'selected' : ''}>Compare (LT <)</option>
                        <option value="cmp_ge" ${el.type === 'cmp_ge' ? 'selected' : ''}>Compare (GE ≥)</option>
                        <option value="cmp_le" ${el.type === 'cmp_le' ? 'selected' : ''}>Compare (LE ≤)</option>
                        <option value="cmp_eq" ${el.type === 'cmp_eq' ? 'selected' : ''}>Compare (EQ =)</option>
                        <option value="cmp_ne" ${el.type === 'cmp_ne' ? 'selected' : ''}>Compare (NE ≠)</option>
                        <option value="cmp_rng" ${el.type === 'cmp_rng' ? 'selected' : ''}>Compare (RANGE)</option>
                        <option value="wait" ${el.type === 'wait' ? 'selected' : ''}>Wait for Trigger</option>
                        <option value="notify" ${el.type === 'notify' ? 'selected' : ''}>Send Notification</option>
                    </select>
                </div>
                ${elLevel === 'automation' && !el.type.startsWith('coil') && !el.type.startsWith('math') && el.type !== 'move' && el.type !== 'notify' && el.type !== 'ctu' && el.type !== 'repeat' ? `
                <div class="fgrp checkbox-grp">
                    <input type="checkbox" id="propIsTrigger" ${el.isTrigger ? 'checked' : ''} />
                    <label style="margin:0; font-weight:800; color:var(--success-color, #4caf50);">[✔] Use as Trigger (Starts Flow)</label>
                </div>
                ` : ''}
                ${elLevel !== 'automation' ? `
                <div class="fgrp" style="font-size:12px; color:#757575;">
                    A ${elLevel} is never started by the house, so there is no trigger to set here.
                </div>
                ` : ''}
                <div id="dynamicPickerSlot"></div>
                <div style="flex:1"></div>
                <button class="btn btn-danger" id="propDelete">🗑 Delete Element</button>
            </div>
        `;
    }

    // [ADDED v3.9.0] The entity id of the element, written under the picker that hides it.
    _idNote(el) {
        const wrap = document.createElement('div');
        wrap.className = 'fgrp';
        const id = String(el.label || '').replace(/\s*\+\d+$/, '').trim();
        const name = this.core.friendlyName(id, this._hass);
        wrap.innerHTML = id
            ? `<div style="font-size:12px; color:#616161; margin-top:-10px; font-family:monospace; word-break:break-all;">`
              + `${this._esc(id)}${name ? ` <span style="font-family:inherit; color:#9e9e9e;">&nbsp;·&nbsp;${this._esc(name)}</span>` : ''}</div>`
            : '';
        return wrap;
    }

    // [ADDED v3.9.0] Every target written out by name, so a block that points at seventeen devices
    // can be read without opening each pill.
    _targetNote(el) {
        const wrap = document.createElement('div');
        wrap.className = 'fgrp';
        const names = this.core.targetNameList(el.targetSpec, this._hass);
        if (!names.length) { wrap.innerHTML = ''; return wrap; }
        const rows = names.map(n => `<li style="margin:1px 0;">${this._esc(n)}</li>`).join('');
        wrap.innerHTML = `<label>Resolved targets (${names.length})</label>`
            + `<ul style="margin:0; padding-inline-start:18px; font-size:12px; color:#616161; max-height:190px; overflow:auto;" dir="auto">${rows}</ul>`;
        return wrap;
    }

    // [ADDED v3.7.0] The very control Home Assistant uses in its own action editor. One field that
    // accepts entities, devices, areas and labels together, with the entity count on each pill. If
    // this Home Assistant build does not ship the component, the field is skipped rather than left
    // as an empty box, and the entity picker above it still works.
    _targetPicker(el) {
        if (typeof customElements === 'undefined' || !customElements.get('ha-selector')) return null;
        const wrap = document.createElement('div');
        wrap.className = 'fgrp';
        const count = this.core.specCount(el.targetSpec);
        wrap.innerHTML = `<label id="lbl_target_spec">Targets &nbsp;<span style="font-weight:600; color:#757575;">`
            + `${count ? count + ' selected' : 'entities, devices, areas, labels'}</span></label>`;
        const node = document.createElement('ha-selector');
        node.hass = this._hass;
        node.selector = { target: {} };
        node.value = this.core.normSpec(el.targetSpec);
        node.id = 'inp_target_spec';
        node.addEventListener('value-changed', (e) => {
            const picked = (e.detail && e.detail.value) || {};
            this.core.applyTargetSpec(el, picked, this._hass);
            this.core.pushHistory();
            this._render();
        });
        wrap.appendChild(node);
        return wrap;
    }

    _picker(kind, value, onValue, opts = {}) {
        const wrap = document.createElement('div');
        wrap.className = 'fgrp';
        if (opts.label) wrap.innerHTML = `<label id="lbl_${opts.id || kind}">${opts.label}</label>`;
        let node;
        if (kind === 'device') {
            node = document.createElement('ha-device-picker');
            if (opts.domain) node.includeDomains = [opts.domain];
        } else if (kind === 'area') {
            node = document.createElement('ha-area-picker');
        } else {
            node = document.createElement('ha-entity-picker');
            node.allowCustomEntity = opts.allowCustom !== false;
            if (kind === 'person') node.includeDomains = ['person', 'device_tracker'];
            else if (kind === 'zone') node.includeDomains = ['zone'];
            else if (kind === 'notify') node.includeDomains = ['notify'];
            else if (kind === 'counter') node.includeDomains = ['counter'];
            else if (opts.domains) node.includeDomains = opts.domains;
        }
        node.hass = this._hass;
        node.value = value || '';
        if (opts.id) node.id = `inp_${opts.id}`;
        node.addEventListener('value-changed', (e) => {
            onValue((e.detail && e.detail.value !== undefined) ? e.detail.value : (e.target.value || ''));
        });
        wrap.appendChild(node);
        return wrap;
    }

    _cmpKind(el) {
        if (el.kind) return el.kind;
        const a = String(el.sourceA || '');
        const b = String(el.sourceB || '');
        if (a === 'time' || a === 'time pattern') return 'time';
        if (a === 'weekday') return 'date';
        if (a === 'datetime') return 'datetime';
        if (a === 'sun') return 'sun';
        if (b.startsWith('zone.') || a.startsWith('person.') || a.startsWith('device_tracker.')) return 'zone';
        return 'entity';
    }

    _injectNativePickers() {
        const slot = this.shadowRoot.getElementById('dynamicPickerSlot');
        if (!slot || !this._inspectedEl) return;
        
        const el = this.core.findEl(this._inspectedEl.netId, this._inspectedEl.rungId, this._inspectedEl.elId);
        if (!el) return;
        slot.innerHTML = '';

        const onChange = (prop) => (e) => { 
            el[prop] = e.target.value || e.detail.value || ''; 
            this.core.pushHistory(); 
            this._render(); 
        };

        if (['contact_no', 'contact_nc', 'contact_p', 'contact_n', 'coil', 'coil_s', 'coil_r', 'wait'].includes(el.type)) {
            slot.appendChild(this._picker('entity', el.label, v => { el.label = v; this.core.pushHistory(); this._render(); },
                { label: el.type.startsWith('coil') ? 'Controlled Entity' : 'Entity / Sensor', id: 'label' }));
            // [ADDED v3.9.0] The Home Assistant picker shows only the friendly name, which is not
            // enough to tell which entity or which device is behind it. The id goes right under it.
            slot.appendChild(this._idNote(el));
            // [CHANGED v3.7.0] The single device field and the single area field are replaced by the
            // native target selector, which is what Home Assistant itself shows and is the only way
            // to express a mixed list such as seventeen targets across devices and entities.
            const tp = this._targetPicker(el);
            if (tp) slot.appendChild(tp);
            slot.appendChild(this._targetNote(el));

        } else if (el.type.startsWith('timer')) {
            const fgrp = document.createElement('div'); fgrp.className = 'fgrp'; fgrp.innerHTML = `<label id="lbl_label">Delay Duration (PT)</label>`;
            let h = 0, m = 0, s = 1; 
            if (el.label && el.label.includes(':')) { 
                const p = el.label.split(':'); h = parseInt(p[0], 10) || 0; m = parseInt(p[1], 10) || 0; s = parseInt(p[2], 10) || 0; 
            }
            const selector = document.createElement('ha-selector'); selector.hass = this._hass; selector.selector = { duration: { enable_day: false } }; selector.value = { hours: h, minutes: m, seconds: s };
            selector.id = "inp_label";
            selector.addEventListener('value-changed', e => { 
                const val = e.detail.value || {}; 
                const nh = String(val.hours || 0).padStart(2, '0'); const nm = String(val.minutes || 0).padStart(2, '0'); const ns = String(val.seconds || 0).padStart(2, '0'); 
                el.label = `${nh}:${nm}:${ns}`; this.core.pushHistory(); this._render(); 
            });
            fgrp.appendChild(selector); slot.appendChild(fgrp);

        } else if (el.type === 'move') {
            const mode = el.mode || 'value';
            slot.innerHTML += `<div class="fgrp"><label>Mode</label><select id="propMoveMode">
                <option value="value" ${mode === 'value' ? 'selected' : ''}>MOVE (assign a value)</option>
                <option value="notify" ${mode === 'notify' ? 'selected' : ''}>MOVE NOTIFY (alert)</option>
                <option value="tts" ${mode === 'tts' ? 'selected' : ''}>MOVE TTS (speak)</option>
                <option value="both" ${mode === 'both' ? 'selected' : ''}>MOVE NOTIFY/TTS (alert and speak)</option>
            </select></div>`;

            if (mode === 'value') {
                // [CHANGED v3.8.0] On a MOVE ACTION the IN pin is the Home Assistant service name, so
                // the field says so rather than calling it a value.
                const isAction = el.moveKind === 'action';
                slot.innerHTML += `<div class="fgrp"><label id="lbl_source">${isAction ? 'Action (Home Assistant service)' : 'Value or Template'}</label><textarea id="inp_source" rows="${isAction ? 1 : 3}" style="font-family:monospace;">${this._esc(el.source || '')}</textarea></div>`;
                if (isAction) slot.innerHTML += `<div class="fgrp" style="font-size:12px; color:#757575; margin-top:-6px;">OUT is a summary of the targets below. It is not read back, the targets are.</div>`;
            } else {
                if (mode !== 'tts') {
                    slot.innerHTML += `<div class="fgrp"><label id="lbl_source">Message</label><textarea id="inp_source" rows="2">${this._esc(el.source || '')}</textarea></div>`;
                    slot.innerHTML += `<div class="fgrp"><label id="lbl_title">Title</label><input type="text" id="inp_title" value="${this._esc(el.title || '')}" /></div>`;
                }
                if (mode !== 'notify') {
                    slot.innerHTML += `<div class="fgrp"><label id="lbl_tts">Spoken text${mode === 'both' ? ' (leave empty to speak the message)' : ''}</label><textarea id="inp_tts" rows="2">${this._esc(el.tts || '')}</textarea></div>`;
                    slot.innerHTML += `<div class="fgrp"><label id="lbl_stream">Media stream</label><input type="text" id="inp_stream" value="${this._esc(el.stream || 'alarm_stream')}" /></div>`;
                }
            }

            slot.appendChild(this._picker(mode === 'value' ? 'entity' : 'notify', el.target,
                v => { el.target = v; this.core.pushHistory(); this._render(); },
                { label: mode === 'value' ? 'Target Entity / Helper' : 'Notify Service / Speaker', id: 'target' }));
            if (mode === 'value') {
                // [CHANGED v3.7.0] A value assignment targets things the same way an action does.
                const tpm = this._targetPicker(el);
                if (tpm) slot.appendChild(tpm);
                slot.appendChild(this._targetNote(el));
            }

            const modeSel = slot.querySelector('#propMoveMode');
            if (modeSel) modeSel.addEventListener('change', e => { el.mode = e.target.value; this.core.pushHistory(); this._render(); });
            ['source', 'title', 'tts', 'stream'].forEach(prop => {
                const f = slot.querySelector(`#inp_${prop}`);
                if (f) f.addEventListener('change', e => { el[prop] = e.target.value; this.core.pushHistory(); this._render(); });
            });

        } else if (el.type === 'cmp_rng') {
            const fgrpA = document.createElement('div'); fgrpA.className = 'fgrp';
            fgrpA.innerHTML = `<label id="lbl_sourceA">Measured Entity (IN)</label>`;
            const pickerA = document.createElement('ha-entity-picker'); pickerA.hass = this._hass;
            pickerA.value = el.sourceA || ''; pickerA.allowCustomEntity = true; pickerA.id = "inp_sourceA";
            pickerA.addEventListener('value-changed', onChange('sourceA'));
            fgrpA.appendChild(pickerA); slot.appendChild(fgrpA);
            slot.innerHTML += `<div class="fgrp"><label id="lbl_sourceB">Above (MIN)</label><input type="text" id="inp_sourceB" value="${this._esc(el.sourceB === undefined ? '' : el.sourceB)}" /></div>`;
            slot.innerHTML += `<div class="fgrp"><label id="lbl_sourceC">Below (MAX)</label><input type="text" id="inp_sourceC" value="${this._esc(el.sourceC === undefined ? '' : el.sourceC)}" /></div>`;
            ['sourceB', 'sourceC'].forEach(prop => {
                const f = slot.querySelector(`#inp_${prop}`);
                if (f) f.addEventListener('change', e => { el[prop] = e.target.value; this.core.pushHistory(); this._render(); });
            });

        } else if (el.type === 'ctu') {
            const fgrpSrc = document.createElement('div'); fgrpSrc.className = 'fgrp'; fgrpSrc.innerHTML = `<label id="lbl_source">Counter Entity</label>`;
            const picker = document.createElement('ha-entity-picker'); picker.hass = this._hass; picker.value = el.source || ''; picker.includeDomains = ['counter'];
            picker.id = "inp_source";
            picker.addEventListener('value-changed', onChange('source')); fgrpSrc.appendChild(picker); slot.appendChild(fgrpSrc);
            slot.innerHTML += `<div class="fgrp"><label id="lbl_value">Preset Value (Limit)</label><input type="text" id="inp_value" value="${el.value || ''}" /></div>`;

        } else if (el.type === 'notify') {
            const fgrpSrc = document.createElement('div'); fgrpSrc.className = 'fgrp'; fgrpSrc.innerHTML = `<label id="lbl_source">Message Text</label><textarea id="inp_source" rows="3">${el.source || ''}</textarea>`; slot.appendChild(fgrpSrc);
            const fgrpTgt = document.createElement('div'); fgrpTgt.className = 'fgrp'; fgrpTgt.innerHTML = `<label id="lbl_target">Notify Target</label>`;
            const picker = document.createElement('ha-entity-picker'); picker.hass = this._hass; picker.value = el.target || ''; picker.includeDomains = ['notify'];
            picker.id = "inp_target";
            picker.addEventListener('value-changed', onChange('target')); fgrpTgt.appendChild(picker); slot.appendChild(fgrpTgt);

        } else if (el.type.startsWith('cmp') || el.type.startsWith('math')) {
            const isCmp = el.type.startsWith('cmp');
            const kind = isCmp ? this._cmpKind(el) : 'entity';

            if (isCmp) {
                const kindWrap = document.createElement('div');
                kindWrap.className = 'fgrp';
                kindWrap.innerHTML = `<label>What do you compare</label><select id="propCmpKind">
                    <option value="entity" ${kind === 'entity' ? 'selected' : ''}>A value (any entity that is not a boolean)</option>
                    <option value="time" ${kind === 'time' ? 'selected' : ''}>Time of day</option>
                    <option value="date" ${kind === 'date' ? 'selected' : ''}>Date (days of the week)</option>
                    <option value="datetime" ${kind === 'datetime' ? 'selected' : ''}>Date and time</option>
                    <option value="zone" ${kind === 'zone' ? 'selected' : ''}>A person against a zone</option>
                    <option value="device" ${kind === 'device' ? 'selected' : ''}>A device sensor</option>
                    <option value="sun" ${kind === 'sun' ? 'selected' : ''}>The sun</option>
                </select>`;
                slot.appendChild(kindWrap);
                kindWrap.querySelector('#propCmpKind').addEventListener('change', e => {
                    el.kind = e.target.value;
                    if (el.kind === 'time') el.sourceA = 'time';
                    if (el.kind === 'date') { el.sourceA = 'weekday'; el.type = 'cmp_eq'; }
                    if (el.kind === 'datetime') el.sourceA = 'datetime';
                    if (el.kind === 'sun') { el.sourceA = 'sun'; el.sourceB = el.sourceB || 'sunset'; }
                    if (el.kind === 'entity' && ['time', 'weekday', 'datetime', 'sun'].includes(String(el.sourceA))) el.sourceA = '';
                    this.core.pushHistory(); this._render();
                });
            }

            if (kind === 'zone') {
                slot.appendChild(this._picker('person', el.sourceA, v => { el.sourceA = v; this.core.pushHistory(); this._render(); },
                    { label: 'Person', id: 'sourceA' }));
                slot.appendChild(this._picker('zone', el.sourceB, v => { el.sourceB = v; this.core.pushHistory(); this._render(); },
                    { label: 'Zone', id: 'sourceB' }));
            } else if (kind === 'device') {
                slot.appendChild(this._picker('device', el.deviceId, v => {
                    el.deviceId = v; this.core.pushHistory(); this._render();
                }, { label: 'Device', id: 'device' }));
                slot.appendChild(this._picker('entity', el.sourceA, v => { el.sourceA = v; this.core.pushHistory(); this._render(); },
                    { label: 'Sensor of that device', id: 'sourceA' }));
                slot.innerHTML += `<div class="fgrp"><label id="lbl_sourceB">Value (IN2)</label><input type="text" id="inp_sourceB" value="${this._esc(el.sourceB === undefined ? '' : el.sourceB)}" /></div>`;
            } else if (kind === 'time') {
                el.sourceA = 'time';
                slot.innerHTML += `<div class="fgrp"><label>Left side</label><input type="text" value="the clock" disabled /></div>`;
                slot.innerHTML += `<div class="fgrp"><label id="lbl_sourceB">Fixed time (HH:MM:SS)</label><input type="text" id="inp_sourceB" value="${this._esc(el.sourceB || '')}" placeholder="08:00:00" /></div>`;
                slot.appendChild(this._picker('entity', el.sourceB, v => { el.sourceB = v; this.core.pushHistory(); this._render(); },
                    { label: 'or a time helper', id: 'sourceBhelper', domains: ['input_datetime', 'sensor'] }));
                if (el.type === 'cmp_rng') {
                    slot.innerHTML += `<div class="fgrp"><label id="lbl_sourceC">Until (HH:MM:SS)</label><input type="text" id="inp_sourceC" value="${this._esc(el.sourceC || '')}" /></div>`;
                    const fc = slot.querySelector('#inp_sourceC');
                    if (fc) fc.addEventListener('change', e => { el.sourceC = e.target.value; this.core.pushHistory(); this._render(); });
                }
            } else if (kind === 'date') {
                el.sourceA = 'weekday';
                const days = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'];
                const picked = String(el.sourceB || '').split(',').map(d => d.trim()).filter(Boolean);
                const wrap = document.createElement('div');
                wrap.className = 'fgrp';
                wrap.innerHTML = `<label>Days of the week</label><div style="display:flex;flex-wrap:wrap;gap:6px;">${
                    days.map(d => `<label style="display:flex;align-items:center;gap:3px;font-size:12px;">
                        <input type="checkbox" data-day="${d}" ${picked.includes(d) ? 'checked' : ''}/>${d}</label>`).join('')}</div>`;
                slot.appendChild(wrap);
                wrap.querySelectorAll('input[type=checkbox]').forEach(cb => cb.addEventListener('change', () => {
                    const sel = [...wrap.querySelectorAll('input[type=checkbox]')].filter(x => x.checked).map(x => x.dataset.day);
                    el.sourceB = sel.join(', ');
                    this.core.pushHistory(); this._render();
                }));
            } else if (kind === 'datetime') {
                el.sourceA = 'datetime';
                slot.appendChild(this._picker('entity', el.sourceB, v => { el.sourceB = v; this.core.pushHistory(); this._render(); },
                    { label: 'Date and time helper', id: 'sourceB', domains: ['input_datetime', 'sensor'] }));
            } else if (kind === 'sun') {
                el.sourceA = 'sun';
                slot.innerHTML += `<div class="fgrp"><label id="lbl_sourceB">Event</label><select id="inp_sourceB">
                    <option value="sunrise" ${el.sourceB === 'sunrise' ? 'selected' : ''}>sunrise</option>
                    <option value="sunset" ${el.sourceB === 'sunset' ? 'selected' : ''}>sunset</option></select></div>`;
            } else {
                slot.appendChild(this._picker('entity', el.sourceA, v => { el.sourceA = v; this.core.pushHistory(); this._render(); },
                    { label: isCmp ? 'Entity (IN1)' : 'Variable A (IN1)', id: 'sourceA' }));
                slot.innerHTML += `<div class="fgrp"><label id="lbl_sourceB">${isCmp ? 'Value or entity (IN2)' : 'Variable B (IN2)'}</label><input type="text" id="inp_sourceB" value="${this._esc(el.sourceB === undefined ? '' : el.sourceB)}" /></div>`;
            }
            
            const inpB = slot.querySelector('#inp_sourceB');
            if (inpB) inpB.addEventListener('change', e => { el.sourceB = e.target.value; this.core.pushHistory(); this._render(); });

            if (el.type === 'math_div') {
                slot.innerHTML += `<div class="fgrp"><label>Decimals</label><input type="number" id="inp_precision" value="${el.precision === undefined ? 2 : el.precision}" min="0" max="6" /></div>`;
                slot.innerHTML += `<div class="fgrp"><label>Result when dividing by zero</label><input type="text" id="inp_fallback" value="${el.fallback === undefined ? 0 : el.fallback}" /></div>`;
                ['precision', 'fallback'].forEach(prop => {
                    const f = slot.querySelector(`#inp_${prop}`);
                    if (f) f.addEventListener('change', e => { el[prop] = prop === 'precision' ? parseInt(e.target.value, 10) || 0 : e.target.value; this.core.pushHistory(); this._render(); });
                });
            }
            if (el.type.startsWith('math')) {
                const fgrpTgt = document.createElement('div'); fgrpTgt.className = 'fgrp'; fgrpTgt.innerHTML = `<label id="lbl_target">Target Entity (OUT)</label>`;
                const pickerTgt = document.createElement('ha-entity-picker'); pickerTgt.hass = this._hass; pickerTgt.value = el.target || ''; pickerTgt.allowCustomEntity = true;
                pickerTgt.id = "inp_target";
                pickerTgt.addEventListener('value-changed', onChange('target')); fgrpTgt.appendChild(pickerTgt); slot.appendChild(fgrpTgt);
            }
        } else if (el.type === 'repeat') {
            slot.innerHTML += `<div class="fgrp"><label>Loop Type</label><select id="propLoopType"><option value="count" ${el.loopType === 'count' ? 'selected' : ''}>Count</option><option value="while" ${el.loopType === 'while' ? 'selected' : ''}>While</option></select></div><div class="fgrp"><label id="lbl_value">Value/Condition</label><input type="text" id="inp_value" value="${el.value || ''}" /></div>`;
        }

        if (this._inspectedEl && this._inspectedEl.focusProp) {
            setTimeout(() => {
                const fTarget = this.shadowRoot.getElementById(`inp_${this._inspectedEl.focusProp}`);
                if (fTarget) {
                    if (fTarget.focus) fTarget.focus();
                    const lbl = this.shadowRoot.getElementById(`lbl_${this._inspectedEl.focusProp}`);
                    if (lbl) lbl.style.color = 'var(--primary-color)';
                }
            }, 100);
        }
    }

    _validateEl(el) {
        const errs = { el: false, lbl: false, src: false, tgt: false, srcA: false, srcB: false };
        const isEmpty = (v) => !v || v === '?' || String(v).trim() === '';
        
        if (['contact_no', 'contact_nc', 'contact_p', 'contact_n', 'coil', 'coil_s', 'coil_r', 'wait'].includes(el.type)) { 
            if (isEmpty(el.label) && !el.raw_trigger) { errs.lbl = true; errs.el = true; } 
        } else if (el.type === 'move') { 
            const mode = el.mode || 'value';
            if (mode === 'tts') { if (isEmpty(el.tts)) { errs.src = true; errs.el = true; } }
            else if (isEmpty(el.source)) { errs.src = true; errs.el = true; }
            if (isEmpty(el.target)) { errs.tgt = true; errs.el = true; } 
        } else if (el.type === 'notify') { 
            if (isEmpty(el.source)) { errs.src = true; errs.el = true; } 
            if (isEmpty(el.target)) { errs.tgt = true; errs.el = true; } 
        } else if (el.type === 'cmp_rng') {
            if (isEmpty(el.sourceA)) { errs.srcA = true; errs.el = true; }
        } else if (['ctu'].includes(el.type)) { 
            if (isEmpty(el.source)) { errs.src = true; errs.el = true; } 
            if (isEmpty(el.value)) { errs.lbl = true; errs.el = true; } 
        } else if (el.type.startsWith('cmp') || el.type.startsWith('math')) { 
            if (el.tplId && isEmpty(el.sourceB)) return errs;
            if (['time', 'weekday', 'datetime', 'sun'].includes(String(el.sourceA)) && !isEmpty(el.sourceB)) return errs;
            if (isEmpty(el.sourceA) && !el.raw_trigger && !el.raw) { errs.srcA = true; errs.el = true; } 
            if (isEmpty(el.sourceB) && !el.raw_trigger && !el.raw) { errs.srcB = true; errs.el = true; } 
            if (el.type.startsWith('math') && isEmpty(el.target)) { errs.tgt = true; errs.el = true; } 
        } else if (el.type.startsWith('timer')) { 
            if (isEmpty(el.label)) { errs.lbl = true; errs.el = true; } 
        }
        return errs;
    }

    _formatDisplayVal(val, stripDomain = false) {
        if (val === 0) return '0';
        if (!val) return '?';
        if (Array.isArray(val)) return this._esc(val.join(' '));
        if (typeof val === 'object') return '…';
        let str = String(val).replace(/\s+/g, ' ').trim();
        if (stripDomain && str.includes('.') && !str.includes(' ') && isNaN(str) && !str.includes('{')) {
            str = str.split('.').slice(1).join('.');
        }
        const LIMIT = 46;
        if (str.length > LIMIT) str = str.slice(0, LIMIT - 1) + '…';
        return this._esc(str);
    }

    _esc(v) {
        return String(v === undefined || v === null ? '' : v)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    _rungNotesHtml(net) {
        if (!net.rungs || !net.rungs.length) return '';
        const rows = net.rungs.map((r, i) => `
            <div class="rung-note">
                <button class="rung-note-num" data-nid="${net.id}" data-rid="${r.id}" title="Show this rung">${i + 1}</button>
                <input type="text" class="rung-comment-input" data-nid="${net.id}" data-rid="${r.id}"
                       value="${this._esc(r.comment || '')}" placeholder="Describe this rung's logic..." />
            </div>`).join('');
        return `<div class="rung-notes">${rows}</div>`;
    }

    _netHtml(net, index) {
        const isCol = net.collapsed ? 'collapsed' : '';
        const rungsHtml = this._netCanvasHtml(net);
        const syncBadge = net.ha_id ? `<span style="font-size:11px; background:#e3f2fd; color:#0288d1; padding:2px 6px; border-radius:4px; margin-left:8px;" title="Linked to HA ID: ${net.ha_id}">🔗 Linked</span>` : '';
        // [ADDED v3.5.0] The kind of logic is written next to the name, because the same drawing means
        // different things in an automation, in a script and in a scene.
        const level = this.core.netLevel(net);
        const levelStyles = {
            automation: { text: 'Automation', bg: '#e8f5e9', fg: '#2e7d32', tip: 'Reactive logic. Needs a trigger. Compiled into libi_automations.yaml' },
            script: { text: 'Script', bg: '#fff8e1', fg: '#ef6c00', tip: 'A subroutine. No triggers. Compiled into libi_scripts.yaml' },
            scene: { text: 'Scene', bg: '#f3e5f5', fg: '#6a1b9a', tip: 'A snapshot. Value assignments only. Compiled into libi_scenes.yaml' },
        };
        const lv = levelStyles[level] || levelStyles.automation;
        const levelBadge = `<span style="font-size:11px; font-weight:800; background:${lv.bg}; color:${lv.fg}; padding:2px 6px; border-radius:4px; margin-left:8px;" title="${lv.tip}">[${lv.text}]</span>`;
        
        return `
        <div class="net ${isCol}" data-nid="${net.id}">
            <div class="net-hdr" data-tog="${net.id}">
                <div class="net-hdr-l">
                    <span style="color:var(--success-color,#4caf50);">●</span>
                    <div class="net-name">
                        <span style="font-weight:900; margin-right:4px;">NET&nbsp;${index + 1}</span>
                        <input type="text" class="net-name-input" data-nid="${net.id}" value="${net.name}" title="Click to rename" placeholder="Automation Name" />
                        ${levelBadge}
                        ${syncBadge}
                    </div>
                </div>
                <div class="net-hdr-r">
                    <span class="chevron" style="font-size:12px; color:#888;">${net.collapsed ? '▼' : '▲'}</span>
                </div>
            </div>
            <div class="net-body" style="flex-direction:column;">
                <div class="net-toolbar">
                    <button class="ha-text-btn load-net-btn" data-nid="${net.id}" title="Load HA Automation">📥 LOAD YAML / AUTO</button>
                    <!-- [ADDED v3.6.0] The kind of logic sits next to the load button, because it is the
                         first decision about a net and it changes which rules the linter applies. -->
                    <select class="net-level-select" data-nid="${net.id}" title="${lv.tip}"
                            style="margin-left:8px; padding:5px 8px; border-radius:6px; font-size:12px; font-weight:700;
                                   border:1px solid ${lv.fg}44; background:${lv.bg}; color:${lv.fg}; cursor:pointer;">
                        <option value="automation" ${level === 'automation' ? 'selected' : ''}>⚡ Automation</option>
                        <option value="script" ${level === 'script' ? 'selected' : ''}>📜 Script</option>
                        <option value="scene" ${level === 'scene' ? 'selected' : ''}>🎬 Scene</option>
                    </select>
                    <div style="flex:1"></div>
                    <div class="net-menu-wrapper">
                        <button class="net-kebab" data-menu-id="${net.id}">
                            <svg viewBox="0 0 24 24"><path fill="currentColor" d="M12,16A2,2 0 0,1 14,18A2,2 0 0,1 12,20A2,2 0 0,1 10,18A2,2 0 0,1 12,16M12,10A2,2 0 0,1 14,12A2,2 0 0,1 12,14A2,2 0 0,1 10,12A2,2 0 0,1 12,10M12,4A2,2 0 0,1 14,6A2,2 0 0,1 12,8A2,2 0 0,1 10,6A2,2 0 0,1 12,4Z"/></svg>
                        </button>
                        <div class="net-menu-dropdown" id="dropdown-${net.id}">
                            <button class="net-menu-item show-yaml-btn" data-nid="${net.id}">📄 Show as YAML</button>
                            <button class="net-menu-item duplicate-net-btn" data-nid="${net.id}">⧉ Duplicate Net</button>
                            <button class="net-menu-item danger remove-net-btn" data-nid="${net.id}">✖ Remove from Net</button>
                            ${net.ha_id ? `<button class="net-menu-item danger delete-auto-btn" data-nid="${net.id}" data-haid="${net.ha_id}">🗑️ Delete File</button>` : ''}
                        </div>
                    </div>
                </div>
                ${this._rungNotesHtml(net)}
                <div style="display:flex; align-items:stretch; padding:16px 0;">
                    <div class="rail rail-l"></div>
                    <div class="rungs">
                        ${rungsHtml}
                        <button class="ha-text-btn" id="addRungBtn" data-nid="${net.id}" style="align-self:flex-start; margin-left:16px;">➕ Add Rung</button>
                        ${this._netNoticeHtml(net)}
                    </div>
                    <div class="rail rail-r"></div>
                </div>
            </div>
        </div>`;
    }

    _netCanvasHtml(net) {
        const L = this.core.layoutNet(net);
        this._netLayout = this._netLayout || {};
        this._netLayout[net.id] = L;

        const svgPaths = L.lines.map(l => l.link
            ? `<line x1="${l.x1}" y1="${l.y1}" x2="${l.x2}" y2="${l.y2}" stroke="#7e57c2" stroke-width="${l.w}"/>`
            : `<line x1="${l.x1}" y1="${l.y1}" x2="${l.x2}" y2="${l.y2}" stroke="#d0d0d0" stroke-width="${l.w}"/>`).join('');
        const svgWire = `<svg class="rung-wire-svg" width="${L.width}" height="${L.height}" style="position:absolute;left:0;top:0;pointer-events:none;z-index:1;">${svgPaths}</svg>`;

        const bands = L.rungs.map(r => `<div class="rung" data-nid="${net.id}" data-rid="${r.id}"
            style="position:absolute; left:0; top:${r.top}px; width:100%; height:${r.height}px; pointer-events:none;"></div>`).join('');

        const handles = L.linkHandles.map(h => `<button class="link-cut" data-nid="${net.id}" data-lid="${h.id}"
            title="Remove this connection" style="left:${h.x - 9}px; top:${h.y - 9}px;">✕</button>`).join('');

        return `
        <div class="rung-scroll net-canvas" data-nid="${net.id}">
            <div class="rung-wire" style="height:${L.height}px;min-height:${L.height}px;min-width:${L.width}px;">
                ${svgWire}
                ${bands}
                ${this._netLayoutHtml(L, net.id)}
                ${handles}
            </div>
        </div>`;
    }

    _netLayoutHtml(L, netId) {
        let html = '';
        for (const n of L.nodes) {
            if (n.kind === 'repeat-frame') {
                html += `<div class="repeat-sequence-wrapper" style="left:${n.x}px; top:${n.y - 20}px; width:${n.w}px; height:${Math.max(n.h - 20, 40)}px; z-index:0;"></div>`;
            } else if (n.kind === 'parallel') {
                html += this._elHtml(n.el, netId, n.rungId, n.path, { x: n.x, y: n.y, w: n.w, h: n.h, kind: 'parallel' });
            }
        }
        for (const n of L.nodes) {
            if (n.kind === 'el' || n.kind === 'repeat' || n.kind === 'repeat-end') {
                html += this._elHtml(n.el, netId, n.rungId, n.path, { x: n.x, y: n.y, w: n.w, kind: n.kind });
            }
        }
        for (const d of L.dots) {
            html += `<button class="wire-ins" data-nid="${netId}" data-rid="${d.rungId}" data-path="${d.path}" data-par="${d.par || ''}" data-bidx="${d.bidx >= 0 ? d.bidx : ''}" style="left:${d.x}px; top:${d.y - 8}px;">+</button>`;
        }
        return html;
    }

    _layoutHtml(L, netId, rungId) {
        let html = '';

        for (const n of L.nodes) {
            if (n.kind === 'repeat-frame') {
                html += `<div class="repeat-sequence-wrapper" style="left:${n.x}px; top:${n.y - 20}px; width:${n.w}px; height:${Math.max(n.h - 20, 40)}px; z-index:0;"></div>`;
            } else if (n.kind === 'parallel') {
                html += this._elHtml(n.el, netId, rungId, n.path, { x: n.x, y: n.y, w: n.w, h: n.h, kind: 'parallel' });
            }
        }

        for (const n of L.nodes) {
            if (n.kind === 'el') {
                html += this._elHtml(n.el, netId, rungId, n.path, { x: n.x, y: n.y, w: n.w, kind: 'el' });
            } else if (n.kind === 'repeat') {
                html += this._elHtml(n.el, netId, rungId, n.path, { x: n.x, y: n.y, w: n.w, kind: 'repeat' });
            } else if (n.kind === 'repeat-end') {
                html += this._elHtml(n.el, netId, rungId, n.path, { x: n.x, y: n.y, w: n.w, kind: 'repeat-end' });
            }
        }

        for (const d of L.dots) {
            html += `<button class="wire-ins" data-nid="${netId}" data-rid="${rungId}" data-path="${d.path}" data-par="${d.par || ''}" data-bidx="${d.bidx >= 0 ? d.bidx : ''}" style="left:${d.x}px; top:${d.y - 8}px;">+</button>`;
        }

        return html;
    }

    _rungElementsHtml(elements, pathPrefix, netId, rungId, isRoot = false) {
        const dotStyle = !isRoot ? 'style="margin-left: 16px;"' : '';
        let inner = `<button class="wire-ins" data-nid="${netId}" data-rid="${rungId}" data-path="${pathPrefix}0" ${dotStyle}>+</button>`;
        elements.forEach((el, i) => {
            inner += this._elHtml(el, netId, rungId, `${pathPrefix}${i}`);
            inner += `<button class="wire-ins" data-nid="${netId}" data-rid="${rungId}" data-path="${pathPrefix}${i + 1}">+</button>`;
        });
        return inner;
    }

    _elHtml(el, netId, rungId, path, pos = null) {
        const isSelected = this._inspectedEl && this._inspectedEl.elId === el.id;
        const errs = this._validateEl(el);
        const hasStructErr = el.structuralError ? true : false;
        const isTriggerClass = el.isTrigger ? 'is-trigger ' : '';
        const selClass = (isSelected ? 'selected ' : '') + (errs.el || hasStructErr ? 'has-error ' : '') + isTriggerClass;
        
        const errTooltip = hasStructErr ? `<div class="err-tooltip">⚠️ ${el.structuralError}</div>` : '';
        const triggerLabelHtml = el.isTrigger ? `<div class="trigger-bottom-lbl">Trigger</div>` : '';

        const ANCHOR = this.core.LAY.ANCHOR;
        const posStyle = pos ? `position:absolute; left:${pos.x}px; top:${pos.y - ANCHOR}px; margin:0; ` : '';

        const elWidth = this.core.getElW(el);

        if (pos && pos.kind === 'parallel') {
            return `<div class="libi-el libi-parallel ${selClass} ${el.closed ? 'closed' : 'open'}" data-nid="${netId}" data-rid="${rungId}" data-eid="${el.id}" style="position:absolute; left:${pos.x}px; top:${pos.y - ANCHOR}px; margin:0; width:${pos.w}px; height:${pos.h + ANCHOR}px; z-index:1; overflow:visible;">${errTooltip}</div>`;
        }

        if (pos && pos.kind === 'repeat') {
            return `
            <div class="libi-el ${selClass}" style="${posStyle} width: 70px;" draggable="true" data-nid="${netId}" data-rid="${rungId}" data-eid="${el.id}">
                <div class="el-ico" style="border-color:#9c27b0;color:#9c27b0;">
                    <span style="font-weight:900;font-size:12px;">[ REP</span>
                </div>
                ${errTooltip}
            </div>`;
        }

        if (pos && pos.kind === 'repeat-end') {
            return `
            <div class="libi-el" style="${posStyle} width: 70px;" data-nid="${netId}" data-rid="${rungId}" data-eid="${el.id}-end">
                <div class="el-ico" style="border-color:#9c27b0;color:#9c27b0;">
                    <span style="font-weight:900;font-size:12px;">] END</span>
                </div>
            </div>`;
        }

        if (pos) {
            const innerBody = this._elBody(el, errs);
            return `<div class="libi-el ${selClass}" style="${posStyle} width: ${elWidth}px;" draggable="true" title="${this._esc(this.core.elementTooltip(el, this._hass))}" data-nid="${netId}" data-rid="${rungId}" data-eid="${el.id}">${innerBody}${triggerLabelHtml}${errTooltip}</div>`;
        }

        if (el.type === 'repeat') {
            const innerHtml = this._rungElementsHtml(el.sequence, `${path}.seq.`, netId, rungId);
            return `
            <div class="libi-el ${selClass}" style="width: 70px;" draggable="true" data-nid="${netId}" data-rid="${rungId}" data-eid="${el.id}">
                <div class="el-ico" style="border-color:#9c27b0;color:#9c27b0;">
                    <span style="font-weight:900;font-size:12px;">[ REP</span>
                </div>
                ${errTooltip}
            </div>
            <div class="repeat-sequence-wrapper">${innerHtml}</div>
            <div class="libi-el" style="width: 70px;" data-nid="${netId}" data-rid="${rungId}" data-eid="${el.id}-end">
                <div class="el-ico" style="border-color:#9c27b0;color:#9c27b0;">
                    <span style="font-weight:900;font-size:12px;">] END</span>
                </div>
            </div>`;
        }
        
        if (el.type === 'parallel') {
            let maxW = 16; 
            if (el.closed) {
                for (let j = 0; j < el.branches.length; j++) maxW = Math.max(maxW, this.core.calcWidthPx(el.branches[j]));
            } else {
                for (let j = 0; j < el.branches.length; j++) maxW = Math.max(maxW, this.core.calcWidthPx(el.branches[j]));
            }
            
            let branchesHtml = ''; 
            let currentDepth = 0;
            
            for (let bIdx = 0; bIdx < el.branches.length; bIdx++) {
                let b = el.branches[bIdx]; 
                let bHtml = this._rungElementsHtml(b, `${path}.b${bIdx}.`, netId, rungId, false);
                
                branchesHtml += `
                <div class="parallel-branch" data-branch="${bIdx}" style="position: absolute; top: ${currentDepth}px; left: 0; display: inline-flex; align-items: flex-start; min-width: 16px;">
                    ${bHtml}
                </div>`;
                currentDepth += this.core.calcHeightPx(b);
            }
            return `<div class="libi-el libi-parallel ${selClass} ${el.closed ? 'closed' : 'open'}" data-eid="${el.id}" style="position: relative; width: ${maxW}px; height: ${currentDepth}px; z-index: 10; overflow: visible;">${branchesHtml}${errTooltip}</div>`;
        }

        const innerBody = this._elBody(el, errs);

        // [ADDED v3.9.0] The hover sits on the block itself too, so a MOVE ACTION with many targets
        // lists them all by name from anywhere on it, not only over the little label box.
        const blockTip = this._esc(this.core.elementTooltip(el, this._hass));
        return `<div class="libi-el ${selClass}" style="width: ${elWidth}px;" draggable="true" title="${blockTip}" data-nid="${netId}" data-rid="${rungId}" data-eid="${el.id}">${innerBody}${triggerLabelHtml}${errTooltip}</div>`;
    }

    _lblStyle(el) {
        const w = this.core.labelWidth(el);
        return `width:${w}px;max-width:${w}px;`;
    }

    _elBody(el, errs) {
        const varPin = (side, name, val, errClass, propName) => {
            if (!name && val === null) return `<div class="plc-col-${side} empty"></div>`;
            return `
                <div class="plc-col-${side} ${errClass ? 'has-error' : ''}">
                    ${name ? `<span class="pin-lbl">${name}</span>` : ''}
                    ${val !== null ? `<div class="pin-val ${errClass ? 'has-error' : ''}" data-prop="${propName}" title="${this._esc(val)}" dir="auto">${this._formatDisplayVal(val)}</div>` : ''}
                </div>
            `;
        };

        let innerBody = '';
        if (el.type === 'cmp_rng') {
            innerBody = `
            <div class="plc-block">
                <div class="plc-header">${String(el.sourceA || '') === 'time' ? 'CMP TIME RANGE' : 'CMP RANGE'}</div>
                <div class="power-row"><div class="pin-lbl">EN</div><div class="pin-lbl">ENO</div></div>
                <div class="plc-row">
                    ${varPin('l', 'IN', el.sourceA || '?', errs.srcA, 'sourceA')}
                    ${varPin('r', '', null, false, '')}
                </div>
                <div class="plc-row">
                    ${varPin('l', 'MIN', el.sourceB === undefined || el.sourceB === '' ? '?' : el.sourceB, false, 'sourceB')}
                    ${varPin('r', 'MAX', el.sourceC === undefined || el.sourceC === '' ? '?' : el.sourceC, false, 'sourceC')}
                </div>
            </div>`;
        } else if (el.type === 'move') {
            const mode = el.mode || 'value';
            // [CHANGED v3.8.0] One generic title per mode. A title built from the service verb
            // invented a new kind of block for every domain, which is exactly what the standard
            // forbids: MOVE ACTION sits alongside MOVE TTS and MOVE NOTIFY and nothing else.
            const head = mode === 'notify' ? 'MOVE NOTIFY'
                       : mode === 'tts' ? 'MOVE TTS'
                       : mode === 'both' ? 'MOVE NOTIFY/TTS'
                       : (el.moveKind === 'action' || el.service ? 'MOVE ACTION' : 'MOVE');
            let rows = '';
            if (mode === 'value') {
                rows = `<div class="plc-row">
                    ${varPin('l', 'IN', el.source || '?', errs.src, 'source')}
                    ${varPin('r', 'OUT', el.target || '?', errs.tgt, el.moveKind === 'action' ? null : 'target')}
                </div>`;
            } else if (mode === 'tts') {
                rows = `<div class="plc-row">
                    ${varPin('l', 'TTS', el.tts || '?', errs.src, 'tts')}
                    ${varPin('r', 'TGT', el.target || '?', errs.tgt, 'target')}
                </div>`;
            } else {
                rows = `<div class="plc-row">
                    ${varPin('l', 'MSG', el.source || '?', errs.src, 'source')}
                    ${varPin('r', 'TGT', el.target || '?', errs.tgt, 'target')}
                </div>`;
                if (mode === 'both') {
                    rows += `<div class="plc-row">
                        ${varPin('l', 'TTS', el.tts || el.source || '?', false, 'tts')}
                        ${varPin('r', '', null, false, '')}
                    </div>`;
                }
            }
            innerBody = `
            <div class="plc-block">
                <div class="plc-header">${head}</div>
                <div class="power-row"><div class="pin-lbl">EN</div><div class="pin-lbl">ENO</div></div>
                ${rows}
            </div>`;
        } else if (el.type.startsWith('cmp')) {
            const op = this.core.opSymbol(el.type);
            const aSide = String(el.sourceA || '');
            const heading = aSide === 'time' ? 'CMP TIME' : aSide === 'weekday' ? 'CMP DAY'
                          : aSide === 'datetime' ? 'CMP DATETIME' : aSide === 'sun' ? 'CMP SUN' : `CMP ${op}`;
            innerBody = `
            <div class="plc-block">
                <div class="plc-header">${heading === `CMP ${op}` ? heading : heading + ' ' + op}</div>
                <div class="power-row"><div class="pin-lbl">EN</div><div class="pin-lbl">ENO</div></div>
                <div class="plc-row">
                    ${varPin('l', 'IN1', el.sourceA || '?', errs.srcA, 'sourceA')}
                    ${varPin('r', '', null, false, '')}
                </div>
                <div class="plc-row">
                    ${varPin('l', 'IN2', el.sourceB || '?', errs.srcB, 'sourceB')}
                    ${varPin('r', '', null, false, '')}
                </div>
            </div>`;
        } else if (el.type.startsWith('math')) {
            let op = this.core.opSymbol(el.type);
            innerBody = `
            <div class="plc-block">
                <div class="plc-header">MATH ${op}</div>
                <div class="power-row"><div class="pin-lbl">EN</div><div class="pin-lbl">ENO</div></div>
                <div class="plc-row">
                    ${varPin('l', 'IN1', el.sourceA || '?', errs.srcA, 'sourceA')}
                    ${varPin('r', 'OUT', el.target || '?', errs.tgt, 'target')}
                </div>
                <div class="plc-row">
                    ${varPin('l', 'IN2', el.sourceB || '?', errs.srcB, 'sourceB')}
                    ${varPin('r', '', null, false, '')}
                </div>
            </div>`;
        } else if (el.type.startsWith('timer')) {
            let tName = el.type === 'timer_ton' ? 'TON' : 'TOF';
            innerBody = `
            <div class="plc-block">
                <div class="plc-header">${tName}</div>
                <div class="power-row"><div class="pin-lbl">IN</div><div class="pin-lbl">Q</div></div>
                <div class="plc-row">
                    ${varPin('l', 'PT', el.label || '1s', errs.lbl, 'label')}
                    ${varPin('r', 'ET', '0s', false, '')}
                </div>
            </div>`;
        } else if (el.type === 'ctu') {
            innerBody = `
            <div class="plc-block">
                <div class="plc-header">CTU</div>
                <div class="power-row"><div class="pin-lbl">CU</div><div class="pin-lbl">Q</div></div>
                <div class="plc-row">
                    ${varPin('l', 'PV', el.value || '?', errs.lbl, 'value')}
                    ${varPin('r', 'CV', el.source || '?', errs.src, 'source')}
                </div>
            </div>`;
        } else if (el.type === 'wait') {
            innerBody = `<div class="el-lbl ${errs.lbl?'has-error':''}" style="${this._lblStyle(el)}" title="${this._esc(el.label || '')}" dir="auto">${this._formatDisplayVal(el.label, true) || '...'}</div><div class="el-ico"><span style="font-weight:900;font-size:12px;">WAIT</span></div>`;
        } else {
            let svgKey = LIBI_ICONS[el.type] ? el.type
                       : (type.startsWith('contact') ? 'contact_no' : (type.startsWith('coil') ? 'coil' : 'custom'));
            
            // [CHANGED v3.9.0] The name the house uses goes above the element, and the hover carries
            // the entity id plus every target by name.
            const named = this.core.displayLabel(el, this._hass);
            let displayLbl = named || (el.raw_trigger && el.raw_trigger.type ? el.raw_trigger.type : el.label);
            const tip = this.core.elementTooltip(el, this._hass) || String(el.label || '');
            // [ADDED v3.10.0] The domain sits on its own line under the name, quieter and smaller,
            // so the block says both what it is called and what kind of thing it is.
            const dom = this.core.domainText(el, this._hass);
            const domHtml = dom
                ? `<div style="font-size:9px; font-weight:600; color:#78909c; letter-spacing:.2px; line-height:1.1; margin-top:1px; direction:ltr;">${this._esc(dom)}</div>`
                : '';

            innerBody = `<div class="el-lbl ${errs.lbl?'has-error':''}" style="${this._lblStyle(el)}" title="${this._esc(tip)}" dir="auto"><div>${this._formatDisplayVal(displayLbl, !named) || '...'}</div>${domHtml}</div><div class="el-ico">${LIBI_ICONS[svgKey] || LIBI_ICONS.custom}</div>`;
        }

        return innerBody;
    }

    _bindEvents() {
        const sr = this.shadowRoot;
        
        const on = (id, ev, fn) => { 
            const el = sr.getElementById(id); 
            if (el) el.addEventListener(ev, fn); 
        };
        
        const all = (sel, ev, fn) => {
            sr.querySelectorAll(sel).forEach(el => el.addEventListener(ev, fn));
        };
        
        sr.addEventListener('click', () => { 
            sr.querySelectorAll('.net-menu-dropdown.show').forEach(d => d.classList.remove('show')); 
        });

        on('undoBtn', 'click', () => { if (this.core.undo()) this._render(); });
        on('redoBtn', 'click', () => { if (this.core.redo()) this._render(); });

        // [CHANGED v3.5.0] ADD NET asks which kind of logic to create instead of always producing
        // an automation. The net itself is created by the level picker below.
        const addNet = () => { 
            this._modal = 'pick_level'; 
            this._render(); 
        };
        on('addNetTop', 'click', addNet);
        on('addNetBottom', 'click', addNet);
        
        on('collapseAllBtn', 'click', () => {
            const allClosed = this.core.nets.length > 0 && this.core.nets.every(n => n.collapsed);
            this.core.nets.forEach(n => { n.collapsed = !allClosed; });
            this._render();
        });

        on('onlineBtn', 'click', () => {
            this.online.enabled = !this.online.enabled;
            this._render();
            this._paintOnline();
        });

        on('saveBtn', 'click', () => { 
            this._saveToBackend(); 
        });
        
        on('clearAllBtn', 'click', () => { 
            if(confirm('Are you sure you want to clear all Nets from the editor?')) { 
                this.core.nets = []; 
                this.core.pushHistory(); 
                this._render(); 
            } 
        });
        
        on('logsBtn', 'click', () => { 
            this._modal = 'logs'; 
            this._render(); 
        });

        on('closeModalBtn', 'click', () => { 
            this._modal = null; 
            this._activeNetForLoad = null; 
            this._render(); 
        });
        
        all('.auto-item', 'click', e => { 
            const haId = e.currentTarget.getAttribute('data-id'); 
            // [ADDED v3.5.0] The level picker reuses the auto-item styling but carries no data-id,
            // so it must not be mistaken for an automation to import.
            if (!haId) return; 
            this._importAutomation(haId); 
        });

        // [ADDED v3.5.0] Choosing a kind in the ADD NET dialog is what actually creates the net.
        all('.level-item', 'click', e => { 
            const lvl = e.currentTarget.getAttribute('data-level'); 
            const names = { automation: 'Automation Name', script: 'Script Name', scene: 'Scene Name' }; 
            this.core.nets.push(this.core.mkNet(names[lvl] || 'Automation Name', '', lvl)); 
            this._modal = null; 
            this.core.pushHistory(); 
            this._render(); 
        });

        // [ADDED v3.6.0] Changing the kind revalidates straight away, so the red blocks appear or
        // clear the moment the net becomes a script or a scene.
        all('.net-level-select', 'click', e => e.stopPropagation());
        all('.net-level-select', 'change', e => {
            const net = this.core.nets.find(n => n.id === e.target.getAttribute('data-nid'));
            if (!net) return;
            net.level = this.core.netLevel({ level: e.target.value });
            this.core.pushHistory();
            this._render();
        });

        all('.net-name-input', 'click', e => e.stopPropagation());
        
        all('.net-name-input', 'change', e => { 
            const net = this.core.nets.find(n => n.id === e.target.getAttribute('data-nid')); 
            if (net) { 
                net.name = e.target.value; 
                this.core.pushHistory(); 
            } 
        });
        
        all('.net-kebab', 'click', e => {
            e.stopPropagation(); 
            const nid = e.currentTarget.getAttribute('data-menu-id'); 
            const dropdown = sr.getElementById(`dropdown-${nid}`);
            const isShowing = dropdown.classList.contains('show'); 
            
            sr.querySelectorAll('.net-menu-dropdown.show').forEach(d => d.classList.remove('show'));
            if (!isShowing) dropdown.classList.add('show');
        });

        all('.duplicate-net-btn', 'click', e => {
            e.stopPropagation();
            const nid = e.currentTarget.getAttribute('data-nid');
            const src = this.core.nets.find(n => n.id === nid);
            if (!src) return;
            const copy = this.core.duplicateNet(src);
            const at = this.core.nets.findIndex(n => n.id === nid);
            this.core.nets.splice(at + 1, 0, copy);
            this.core.pushHistory();
            this._render();
        });

        all('.show-yaml-btn', 'click', async e => {
            e.stopPropagation(); 
            const nid = e.currentTarget.getAttribute('data-nid'); 
            this._inspectedEl = null; 
            this._inspectedNetYaml = nid; 
            this._previewYamlContent = 'Generating YAML...';
            
            sr.querySelectorAll('.net-menu-dropdown.show').forEach(d => d.classList.remove('show')); 
            this._render(); 
            
            const net = this.core.nets.find(n => n.id === nid);
            if (net && this._hass && this._hass.connection) {
                try { 
                    const response = await this._hass.connection.sendMessagePromise({ type: 'libi/preview_yaml', net: net }); 
                    this._previewYamlContent = response.yaml || 'Error generating YAML.'; 
                } catch(err) { 
                    this._previewYamlContent = 'Error: ' + err.message; 
                }
                if (this._inspectedNetYaml === nid) this._render();
            }
        });
        
        on('closeYamlSidebar', 'click', () => { 
            this._inspectedNetYaml = null; 
            this._render(); 
        });

        all('.remove-net-btn', 'click', e => { 
            e.stopPropagation(); 
            if(confirm('Remove this Net from the editor? (File will not be deleted)')) { 
                this.core.nets = this.core.nets.filter(n => n.id !== e.target.getAttribute('data-nid')); 
                this.core.pushHistory(); 
                this._render(); 
            } 
        });
        
        all('.delete-auto-btn', 'click', async e => { 
            e.stopPropagation(); 
            if(confirm('WARNING: This will permanently delete the automation file from HA! Are you sure?')) { 
                const haId = e.target.getAttribute('data-haid'); 
                const nid = e.target.getAttribute('data-nid'); 
                try { 
                    await this._hass.connection.sendMessagePromise({ type: 'libi/delete_automation', automation_id: haId }); 
                    this.core.nets = this.core.nets.filter(n => n.id !== nid); 
                    this.core.pushHistory(); 
                    this._render(); 
                    alert('Automation deleted successfully.'); 
                } catch (err) { 
                    alert('Error deleting automation: ' + err.message); 
                } 
            } 
        });
        
        all('.load-net-btn', 'click', e => { 
            e.stopPropagation(); 
            this._activeNetForLoad = e.currentTarget.getAttribute('data-nid'); 
            this._fetchAutomationsList(); 
        });
        
        all('[data-tog]', 'click', e => { 
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'BUTTON' || e.target.closest('.net-menu-wrapper')) return; 
            const net = this.core.nets.find(n => n.id === e.currentTarget.getAttribute('data-tog')); 
            if (net) { 
                net.collapsed = !net.collapsed; 
                this._render(); 
            } 
        });

        all('.link-cut', 'click', e => {
            e.stopPropagation();
            if (this.core.removeLink(e.currentTarget.getAttribute('data-nid'), e.currentTarget.getAttribute('data-lid'))) {
                this.core.pushHistory();
                this._render();
            }
        });

        all('.rung-note-num', 'click', e => {
            const rid = e.currentTarget.getAttribute('data-rid');
            const rung = sr.querySelector(`.rung[data-rid="${rid}"]`);
            if (!rung) return;
            rung.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
            rung.classList.add('rung-flash');
            setTimeout(() => rung.classList.remove('rung-flash'), 900);
        });

        all('.net-notice-x', 'click', e => {
            const nid = e.currentTarget.getAttribute('data-nid');
            if (this._verify) delete this._verify[nid];
            this._render();
        });

        let panCtx = null;
        const syncPan = () => {};

        all('.rung-scroll', 'pointerdown', e => {
            if (e.button !== 0 && e.pointerType === 'mouse') return;
            if (e.target.closest('.wire-ins, .libi-el, input, textarea, button, select')) return;
            const sc = e.currentTarget;
            if (sc.scrollWidth <= sc.clientWidth + 2) return;
            panCtx = { sc, startX: e.clientX, startLeft: sc.scrollLeft, moved: false };
            sc.classList.add('panning');
        });

        all('.rung-scroll', 'pointermove', e => {
            if (!panCtx) return;
            const dx = e.clientX - panCtx.startX;
            if (Math.abs(dx) > 2) panCtx.moved = true;
            const left = Math.max(0, panCtx.startLeft - dx);
            panCtx.sc.scrollLeft = left;
            e.preventDefault();
        });

        const endPan = () => { if (panCtx) { panCtx.sc.classList.remove('panning'); panCtx = null; } };
        all('.rung-scroll', 'pointerup', endPan);
        all('.rung-scroll', 'pointercancel', endPan);
        all('.rung-scroll', 'pointerleave', endPan);

        all('.rung-scroll', 'wheel', e => {
            const sc = e.currentTarget;
            if (sc.scrollWidth <= sc.clientWidth + 2) return;
            if (!e.shiftKey && Math.abs(e.deltaX) < Math.abs(e.deltaY)) return;
            sc.scrollLeft += (e.deltaX || e.deltaY);
            e.preventDefault();
        });

        all('#addRungBtn', 'click', e => { 
            const net = this.core.nets.find(n => n.id === e.target.getAttribute('data-nid')); 
            net.rungs.push(this.core.mkRung()); 
            this.core.pushHistory(); 
            this._render(); 
        });
        
        all('.rung-comment-input', 'change', e => { 
            const net = this.core.nets.find(n => n.id === e.target.getAttribute('data-nid')); 
            if (net) { 
                const rung = net.rungs.find(r => r.id === e.target.getAttribute('data-rid')); 
                if (rung) { 
                    rung.comment = e.target.value; 
                    this.core.pushHistory(); 
                } 
            } 
        });

        all('.libi-el', 'click', e => {
            e.stopPropagation(); 
            const parent = e.currentTarget;
            if (!parent || parent.getAttribute('data-eid').endsWith('-end')) return; 
            
            let focusProp = null;
            if (e.target.closest('.pin-val')) {
                focusProp = e.target.closest('.pin-val').getAttribute('data-prop');
            }

            this._inspectedEl = { 
                netId: parent.getAttribute('data-nid'), 
                rungId: parent.getAttribute('data-rid'), 
                elId: parent.getAttribute('data-eid'),
                focusProp: focusProp 
            }; 
            this._inspectedNetYaml = null; 
            
            if (e.target.closest('.el-ico') || e.target.closest('.plc-block')) { 
                const rect = parent.getBoundingClientRect(); 
                this._floatingMenu = { 
                    type: 'element', 
                    netId: parent.getAttribute('data-nid'), 
                    rungId: parent.getAttribute('data-rid'), 
                    elId: parent.getAttribute('data-eid'), 
                    x: rect.left + rect.width/2, 
                    y: rect.top,
                    bottom: rect.bottom
                }; 
            } else { 
                this._floatingMenu = null; 
            }
            this._render();
        });

        on('fmOverlay', 'click', () => { 
            this._floatingMenu = null; 
            this._render(); 
        });
        
        all('.pal-btn', 'click', e => {
            e.stopPropagation(); 
            const action = e.currentTarget.getAttribute('data-action'); 
            const val = e.currentTarget.getAttribute('data-val'); 
            const fm = this._floatingMenu;
            
            if (action === 'add') { 
                this.core.insertElement(fm.netId, fm.rungId, fm.path, val); 
            } else if (action === 'mod') { 
                let el = this.core.findEl(fm.netId, fm.rungId, fm.elId); 
                if (el) el.type = val; 
            } else if (action === 'mode') { 
                let el = this.core.findEl(fm.netId, fm.rungId, fm.elId); 
                if (el) el.mode = val; 
            } else if (action === 'trigger') { 
                let el = this.core.findEl(fm.netId, fm.rungId, fm.elId); 
                if (el) el.isTrigger = !el.isTrigger; 
            } else if (action === 'cut') { 
                this.core.cutElement(fm.netId, fm.rungId, fm.elId); 
                if (this._inspectedEl && this._inspectedEl.elId === fm.elId) this._inspectedEl = null; 
            } else if (action === 'copy') { 
                this.core.copyElement(fm.netId, fm.rungId, fm.elId); 
            } else if (action === 'paste') { 
                this.core.pasteElement(fm.netId, fm.rungId, fm.path); 
            } else if (action === 'delete') { 
                this.core.removeElement(fm.netId, fm.rungId, fm.elId); 
                if (this._inspectedEl && this._inspectedEl.elId === fm.elId) this._inspectedEl = null; 
            } else if (action === 'unclose_block') { 
                const match = fm.path.match(/^(.*)\.b(\d+)\.\d+$/); 
                if (match) { 
                    let pInfo = this.core.getArrTarget(fm.netId, fm.rungId, match[1]); 
                    if (pInfo && pInfo.arr[pInfo.idx]) pInfo.arr[pInfo.idx].closed = false; 
                } 
            } else if (action === 'delete_branch' || action === 'delete_block') { 
                const match = fm.path.match(/^(.*)\.b(\d+)\.\d+$/); 
                if (match) { 
                    let pInfo = this.core.getArrTarget(fm.netId, fm.rungId, match[1]); 
                    if (pInfo && pInfo.arr[pInfo.idx]) { 
                        if (action === 'delete_block') { 
                            this.core.removeElement(fm.netId, fm.rungId, pInfo.arr[pInfo.idx].id); 
                        } else { 
                            let pEl = pInfo.arr[pInfo.idx]; 
                            pEl.branches.splice(parseInt(match[2],10), 1); 
                            if (pEl.branches.length === 1) pInfo.arr.splice(pInfo.idx, 1, ...pEl.branches[0]); 
                        } 
                    } 
                } 
            }
            this._floatingMenu = null; 
            this.core.pushHistory(); 
            this._render();
        });

        let dragCtx = null;
        
        all('.wire-ins', 'pointerdown', e => { 
            e.stopPropagation(); 
            const rect = e.currentTarget.getBoundingClientRect(); 
            dragCtx = { 
                el: e.currentTarget, 
                netId: e.currentTarget.getAttribute('data-nid'), 
                rungId: e.currentTarget.getAttribute('data-rid'), 
                path: e.currentTarget.getAttribute('data-path'), 
                startX: rect.left + rect.width/2, 
                startY: rect.top + rect.height/2, 
                pointerX: e.clientX, 
                pointerY: e.clientY, 
                active: false, 
                targetIns: null 
            }; 
            e.currentTarget.setPointerCapture(e.pointerId); 
        });
        
        all('.wire-ins', 'pointermove', e => { 
            if (!dragCtx) return; 
            const dx = e.clientX - dragCtx.pointerX; 
            const dy = e.clientY - dragCtx.pointerY; 
            
            if (!dragCtx.active && (Math.abs(dx) > 10 || Math.abs(dy) > 10)) { 
                dragCtx.active = true; 
                const overlay = sr.getElementById('dragOverlay'); 
                if (overlay) overlay.style.display = 'block'; 
                
                sr.querySelectorAll('.wire-ins').forEach(dot => { 
                    if (dot === dragCtx.el) return; 
                    if (dot.getAttribute('data-nid') !== dragCtx.netId) return;

                    if (dot.getAttribute('data-rid') !== dragCtx.rungId) {
                        const info = this.core.pathInfo(dot.getAttribute('data-path'));
                        if (info.idx > 0) dot.classList.add('valid-target', 'join-target');
                        return;
                    }

                    const dRect = dot.getBoundingClientRect(); 
                    const cx = dRect.left + dRect.width / 2; 
                    if (cx <= dragCtx.startX + 24) return;
                    
                    const rel = this.core.connectRelation(dragCtx.path, dot.getAttribute('data-path'));
                    if (rel) dot.classList.add('valid-target'); 
                });
            } 
            
            if (dragCtx.active) { 
                const path = sr.getElementById('dragPath'); 
                if (path) { 
                    let targetX = e.clientX; 
                    let targetY = e.clientY; 
                    let closestDot = null; 
                    let minDist = 30; 
                    
                    sr.querySelectorAll('.wire-ins.valid-target').forEach(dot => { 
                        const dRect = dot.getBoundingClientRect(); 
                        const cx = dRect.left + dRect.width / 2; 
                        const cy = dRect.top + dRect.height / 2; 
                        
                        const dist = Math.sqrt(Math.pow(cx - e.clientX, 2) + Math.pow(cy - e.clientY, 2)); 
                        if (dist < minDist) { 
                            minDist = dist; 
                            closestDot = dot; 
                        } 
                    }); 
                    
                    if (closestDot) { 
                        const tRect = closestDot.getBoundingClientRect(); 
                        targetX = tRect.left + tRect.width / 2; 
                        targetY = tRect.top + tRect.height / 2; 
                        path.setAttribute('stroke', '#9c27b0'); 
                        dragCtx.targetIns = closestDot; 
                    } else { 
                        path.setAttribute('stroke', '#03a9f4'); 
                        dragCtx.targetIns = null; 
                    } 
                    path.setAttribute('d', `M ${dragCtx.startX} ${dragCtx.startY} L ${dragCtx.startX} ${targetY} L ${targetX} ${targetY}`); 
                } 
            } 
        });
        
        all('.wire-ins', 'pointerup', e => { 
            if (!dragCtx) return; 
            e.currentTarget.releasePointerCapture(e.pointerId); 
            const overlay = sr.getElementById('dragOverlay'); 
            if (overlay) overlay.style.display = 'none'; 
            
            sr.querySelectorAll('.wire-ins.valid-target').forEach(dot => dot.classList.remove('valid-target'));
            
            const netId = e.currentTarget.getAttribute('data-nid'); 
            const rungId = e.currentTarget.getAttribute('data-rid'); 
            const originPath = e.currentTarget.getAttribute('data-path'); 
            
            if (!dragCtx.active) { 
                const rect = e.currentTarget.getBoundingClientRect(); 
                this._floatingMenu = { 
                    type: 'dot', 
                    netId, 
                    rungId, 
                    path: originPath, 
                    x: rect.left + rect.width/2, 
                    y: rect.top,
                    bottom: rect.bottom
                }; 
                this._render(); 
            } else { 
                if (dragCtx.targetIns) { 
                    const tNet = dragCtx.targetIns.getAttribute('data-nid');
                    const tRung = dragCtx.targetIns.getAttribute('data-rid');
                    if (tNet !== dragCtx.netId) {
                        dragCtx = null;
                        sr.querySelectorAll('.wire-ins').forEach(d => d.classList.remove('valid-target', 'join-target', 'drag-over'));
                        const ov = sr.getElementById('dragOverlay');
                        if (ov) ov.style.display = 'none';
                        return;
                    }
                    if (tRung !== dragCtx.rungId) {
                        if (this.core.linkRungs(netId, dragCtx.rungId, originPath, tRung,
                                                dragCtx.targetIns.getAttribute('data-path'))) {
                            this.core.pushHistory();
                            this._render();
                        }
                        dragCtx = null;
                        return;
                    }
                    const endPath = dragCtx.targetIns.getAttribute('data-path');
                    const rel = this.core.connectRelation(originPath, endPath);
                    let changed = false;
                    
                    if (rel && rel.type === 'same-array') {
                        changed = this.core.wrapRange(netId, rungId, rel);
                    } else if (rel) {
                        changed = this.core.closeBranchAt(netId, rungId, rel);
                    }
                    
                    if (changed) { 
                        this.core.pushHistory(); 
                        this._render(); 
                    }
                } else if (e.clientY > dragCtx.startY + 30) { 
                    this.core.openBranchAt(netId, rungId, originPath); 
                    this.core.pushHistory(); 
                    this._render(); 
                } 
            } 
            dragCtx = null; 
        });

        all('.libi-el', 'dragstart', e => { 
            this._draggedEl = { 
                netId: e.currentTarget.getAttribute('data-nid'), 
                rungId: e.currentTarget.getAttribute('data-rid'), 
                elId: e.currentTarget.getAttribute('data-eid') 
            }; 
            e.dataTransfer.effectAllowed = 'move'; 
            e.dataTransfer.setData('text/plain', this._draggedEl.elId); 
        });
        
        all('.wire-ins', 'dragover', e => { 
            e.preventDefault(); 
            e.currentTarget.classList.add('drag-over'); 
        });
        
        all('.wire-ins', 'dragleave', e => { 
            e.currentTarget.classList.remove('drag-over'); 
        });
        
        all('.wire-ins', 'drop', e => { 
            e.preventDefault(); 
            e.currentTarget.classList.remove('drag-over'); 
            if (!this._draggedEl) return; 
            
            this.core.cutElement(this._draggedEl.netId, this._draggedEl.rungId, this._draggedEl.elId); 
            this.core.pasteElement(e.currentTarget.getAttribute('data-nid'), e.currentTarget.getAttribute('data-rid'), e.currentTarget.getAttribute('data-path')); 
            
            this._draggedEl = null; 
            this.core.pushHistory(); 
            this._render(); 
        });

        const bindProp = (id, prop, isCheckbox = false) => { 
            on(id, 'change', e => { 
                let el = this.core.findEl(this._inspectedEl.netId, this._inspectedEl.rungId, this._inspectedEl.elId); 
                if (el) { 
                    el[prop] = isCheckbox ? e.target.checked : (e.target.value || e.detail?.value); 
                    this.core.pushHistory(); 
                    this._render(); 
                } 
            }); 
        };
        
        bindProp('propType', 'type'); 
        bindProp('propSource', 'source'); 
        bindProp('propSourceA', 'sourceA'); 
        bindProp('propSourceB', 'sourceB'); 
        bindProp('propTarget', 'target'); 
        bindProp('propValue', 'value'); 
        bindProp('propLabel', 'label');
        bindProp('propIsTrigger', 'isTrigger', true);

        on('propDelete', 'click', () => { 
            this.core.removeEntity ? null : this.core.removeElement(this._inspectedEl.netId, this._inspectedEl.rungId, this._inspectedEl.elId); 
            this._inspectedEl = null; 
            this.core.pushHistory(); 
            this._render(); 
        });
    }
}

console.log("⚡ LIBI Panel JS Loaded successfully.");
customElements.define('libi-panel', LibiPanel);