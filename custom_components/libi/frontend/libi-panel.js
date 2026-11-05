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
 * v3.89.0
 */
// [ADDED v3.88.1 | 2026-11-05] Purpose: The Global tab is a table of the global variables - name, type, device, id - and
//   a row or New opens one editor; a save closes it (the user's request: the Save that stayed showed nothing happening).
// [ADDED v3.89.0 | 2026-11-05] Purpose: After a save, LIBI asks to replace the phone with the global variable wherever an
//   automation still sends straight to it (the user's request), and does it for those ticked (_globalMoveRun); the
//   message under the table no longer pushes the table down. One send to the config API for every save (_configApiSend).
import { LibiCore } from './libi-core.js?v=3.89.0';
import { getStyles } from './libi-css.js?v=3.89.0';
import { LIBI_ICONS, MDI } from './libi-svg.js?v=3.89.0';
import { LibiOnline } from './libi-online.js?v=3.89.0';
import { LibiAiChat } from './libi-ai.js?v=3.89.0';

// [ADDED v3.15.2] Printed once when the file loads. If the number in the console is not the number
// of the release you installed, the browser is running an older file and nothing else matters.
export const LIBI_BUILD = '3.89.0';
// [ADDED v3.35.0] Resolved against this module, so it follows the static path it is served from.
const LOGO_URL = new URL(`./libi-logo.png?v=${LIBI_BUILD}`, import.meta.url).href;

// [ADDED v3.16.0] Every helper Home Assistant can create from a stored collection, which is what a
// ladder programmer means by a local variable: a bit, a word, a timer, a counter. The other kind of
// helper in Home Assistant, a template sensor or a min max, is built by a config flow of its own and
// cannot be made from here, so it is not offered rather than offered and then failing.
// Each entry carries the defaults the create command demands, so a name and a type are enough.
export const HELPER_TYPES = [
    { domain: 'input_boolean',  label: 'Toggle  ·  input_boolean',   defaults: {} },
    { domain: 'input_number',   label: 'Number  ·  input_number',    defaults: { min: 0, max: 100, step: 1, mode: 'box' }, extra: 'number' },
    { domain: 'input_text',     label: 'Text  ·  input_text',        defaults: { min: 0, max: 100, mode: 'text' } },
    { domain: 'input_select',   label: 'Dropdown  ·  input_select',  defaults: { options: ['Option 1'] }, extra: 'options' },
    { domain: 'input_datetime', label: 'Date and time  ·  input_datetime', defaults: { has_date: true, has_time: true } },
    { domain: 'input_button',   label: 'Button  ·  input_button',    defaults: {} },
    { domain: 'counter',        label: 'Counter  ·  counter',        defaults: { initial: 0, step: 1, minimum: 0, restore: true } },
    { domain: 'timer',          label: 'Timer  ·  timer',            defaults: { duration: '00:01:00', restore: true }, extra: 'duration' },
    { domain: 'schedule',       label: 'Schedule  ·  schedule',      defaults: {} },
];
const HELPER_DOMAINS = HELPER_TYPES.map(h => h.domain);

// [ADDED v3.17.0] The ladder view of what a variable is. Home Assistant has no notion of a data
// type, it has domains, so this table is the bridge: a bit, a whole number, a real number, text and
// time. Anything that is not a helper at all is an ordinary Home Assistant entity.
export const VAR_TYPES = {
    BOOL:  { label: 'BOOL',  domain: 'input_boolean', title: 'A bit. On or off.' },
    INT:   { label: 'INT',   domain: 'input_number',  title: 'A whole number.',  defaults: { min: 0, max: 100, step: 1, mode: 'box' } },
    FLOAT: { label: 'FLOAT', domain: 'input_number',  title: 'A real number.',   defaults: { min: 0, max: 100, step: 0.1, mode: 'box' } },
    TEXT:  { label: 'TEXT',  domain: 'input_text',    title: 'A string.',        defaults: { min: 0, max: 100, mode: 'text' } },
    TIME:  { label: 'TIME',  domain: 'timer',         title: 'A timer or a date and time.', defaults: { duration: '00:01:00', restore: true } },
};
const VAR_TYPE_KEYS = Object.keys(VAR_TYPES);

// [ADDED v3.77.0] What IN1 of a CMP TIME and of a CMP DAY is, written the way the user reads it (as C#'s DateTime.Now):
// the clock now and the day now. The text only - the element keeps sourceA 'time' / 'weekday', which the compiler reads.
const CLOCK_IN1 = Object.freeze({ time: 'datetime.time.now', weekday: 'datetime.day.now' });
const clockIn1 = (side) => (side === 'time' || side === 'weekday') ? CLOCK_IN1[side] : '';

// Which of the five a given entity is. A counter and an input_number both hold a number, and the
// step is what says whether it counts in whole numbers or in fractions.
export function varTypeOf(entityId, hass) {
    const domain = String(entityId || '').split('.')[0];
    if (domain === 'input_boolean' || domain === 'input_button') return 'BOOL';
    if (domain === 'input_text' || domain === 'input_select') return 'TEXT';
    if (domain === 'input_datetime' || domain === 'timer' || domain === 'schedule') return 'TIME';
    if (domain === 'counter') return 'INT';
    if (domain === 'input_number') {
        const st = hass && hass.states && hass.states[entityId];
        const step = st && st.attributes ? Number(st.attributes.step) : 1;
        return (!isFinite(step) || step >= 1) ? 'INT' : 'FLOAT';
    }
    return 'HA';
}

class LibiPanel extends HTMLElement {
    constructor() {
        super(); 
        this.attachShadow({ mode: 'open' }); 
        this.core = new LibiCore();
        this.online = new LibiOnline();
        this.online.core = this.core;  // [ADDED v3.71.0] which rungs hang from a trigger, and from which
        // [ADDED v3.36.0] The AI chat keeps its own DOM, so a render of the panel never loses what
        // the user typed or ticked; it is only moved into the new sidebar.
        this.aiChat = new LibiAiChat(this);
        this._editMode = true; 
        this._initialized = false; 
        this._astLoaded = false;
        this._inspectedEl = null; 
        // [ADDED v3.12.0] The sidebar remembers how wide it was and whether it was closed. The 320
        // below is only the very first run, before anything has been saved.
        this.SIDEBAR_MIN = 260;
        this.SIDEBAR_MAX = 900;
        this._sidebarW = this._readNum('libi_sidebar_w', 320, this.SIDEBAR_MIN, this.SIDEBAR_MAX);
        this._sidebarH = this._readNum('libi_sidebar_h', 320, 160, 900);
        this._sidebarRail = this._readFlag('libi_sidebar_rail');
        this._inspectedNetYaml = null;
        this._netYamlKind = 'yaml';  // [ADDED v3.63.0] 'yaml' or 'card': what the YAML panel shows
        this._hdrMenu = false;
        // [ADDED v3.14.0] The workspace that is open. A project holds a set of nets, each one
        // remembering which automation it was loaded from, and it is stored as its own .libi file.
        // [ADDED v3.16.0] The drawer of local variables at the foot of the sidebar.
        // [CHANGED v3.17.0] The variables live in a bar of their own along the bottom, with the same
        // fold and resize behaviour as the sidebar and a remembered height.
        this._varsOpen = this._readFlag('libi_vars_open');
        this._varsH = this._readNum('libi_vars_h', 280, 120, 900);
        // [CHANGED v3.20.0] Helper comes first and is what the bar opens on. It is the helpers page
        // of Home Assistant itself, frame and all, so its own Create helper button is right there.
        this._varsTab = 'helper';      // helper | vars | search | global
        // [ADDED v3.88.0] LIBI Global: whether its list was read (loaded - only then is a recipient not in it gone), why
        // not, the changes not saved yet per recipient key ('+new' for a new one), the one being saved, and what to say.
        // [ADDED v3.88.1] editing: the one open in the editor ('' - the table); said['+table']: what the table says.
        this._global = { loaded: false, ok: true, errors: [], drafts: {}, busy: '', said: {}, editing: '' };
        // [ADDED v3.89.0] The question to replace a phone with a global variable: { key, picked, busy, said }, while it is open.
        this._globalMove = null;
        this._helperQuery = '';
        this._ctx = null;              // the right click menu on a block name
        this._ep = null;               // the entity chooser: what it is picking for
        this._epTab = 'target';        // target | type
        this._epQuery = '';
        this._epOpen = {};             // which groups are unfolded
        this._renameFor = '';          // the entity being renamed
        this._renameTo = '';
        this._renameFrom = 'label';    // [ADDED v3.86.0] label | pin: what the right click was on
        this._hkPick = null;           // the kind chosen in the Create helper dialog
        this._hkForm = {};
        this._hkQuery = '';
        this._varsScope = 'net';       // net | project | all
        // [ADDED v3.86.0] The NET whose variables the bar lists: its title or one of its elements clicked last.
        this._selectedNetId = null;
        this._varsFilter = 'ALL';      // ALL | BOOL | INT | FLOAT | TEXT | TIME | HA
        this._varsQuery = '';
        this._varsNewName = '';
        this._varsNewType = 'BOOL';
        this._helperIds = {};          // domain -> { objectId: collectionId }
        this._draggedVar = null;
        this._project = null;          // { slug, name }
        this._projectList = [];
        this._projectDirty = false;
        this._previewYamlContent = '';
        this._floatingMenu = null; 
        this._draggedEl = null; 
        this._modal = null; 
        this._automationList = []; 
        this._activeNetForLoad = null;
    }

    // [ADDED v3.45.0] Home Assistant tells every panel whether the screen is narrow (its sidebar is then
    // hidden); the hamburger in the header follows it.
    set narrow(value) {
        const narrow = !!value;
        if (narrow === this._narrow) return;
        this._narrow = narrow;
        this.toggleAttribute('narrow', narrow);
    }

    get narrow() { return !!this._narrow; }

    set hass(hass) { 
        this._hass = hass; 
        // [ADDED v3.35.0] The colour tokens in libi-css.js switch on [dark]. It follows the theme the
        // user picked in Home Assistant, which can differ from the operating system's setting.
        this.toggleAttribute('dark', !!(hass && hass.themes && hass.themes.darkMode));
        // [ADDED v3.9.0] The core resolves names while it measures the label boxes, so it needs the
        // same hass the panel has.
        if (this.core) this.core.hass = hass; 
        if (!this._astLoaded && this._hass && this._hass.connection) { 
            this._astLoaded = true; 
            this._loadFromBackend(); 
            this._loadSchedules();  // [ADDED v3.71.0] the days and hours the CMP DATETIME blocks show
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
        // [ADDED v3.85.0] Closing or reloading the browser tab with changes not saved: the browser's own warning. A page
        // that closes cannot save, so it cannot ask Yes or No.
        this._unloadHandler = (e) => { if (this._hasUnsavedChanges(true)) { e.preventDefault(); e.returnValue = ''; } };
        window.addEventListener('beforeunload', this._unloadHandler);
        
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
        if (this._unloadHandler) window.removeEventListener('beforeunload', this._unloadHandler);
        // [ADDED v3.85.0] Leaving the editor for another page of Home Assistant with changes not saved - the user's rule
        // (2026-11-04): asked Yes or No. Home Assistant has already moved on, so the browser's dialog asks (OK is Yes), and
        // the save runs from here. A panel only moved in the page is back at once and asks nothing.
        setTimeout(() => {
            if (this.isConnected || !this._initialized || !this._hasUnsavedChanges(true)) return;
            if (!window.confirm('LIBI: the changes were not saved. Save them now?\n\nOK saves them (SAVE & COMPILE). Cancel leaves them unsaved.')) return;
            this._saveProject().then(r => { if (!(r.complete && r.status === 'ok')) alert(this._saveResultText(r)); });
        }, 0);
    }

    async _loadFromBackend() { 
        // [ADDED v3.14.0] Come back to the workspace that was open last. Its nets return exactly as
        // they were left, so a half drawn rung is still half drawn.
        let remembered = null;
        try { remembered = JSON.parse(localStorage.getItem('libi_project') || 'null'); } catch (err) { remembered = null; }
        // [ADDED v3.86.0] The names given in LIBI only, before anything is drawn with a name.
        await this._loadLocalNames();
        // [ADDED v3.87.0] And the phones, whose two ids share one name.
        await this._loadPhones();
        // [ADDED v3.88.0] And LIBI Global's recipients, which a MOVE NOTIFY / TTS block shows by name.
        await this._loadGlobal();
        await this._projectRefreshList();
        if (remembered && (this._projectList || []).some(p => p.slug === remembered.slug)) {
            try {
                const res = await this._hass.connection.sendMessagePromise({ type: 'libi/project_open', slug: remembered.slug });
                this.core.nets = res.nets || [];
                this._project = { slug: res.slug, name: res.name };
                this._versions = res.versions || {};
                this.core.syncCounters();
                this.core.repairAST();
                this._initialized = true;
                this.core.history = [JSON.stringify(this.core.nets)];
                this.core.historyIdx = 0;
                this._markSaved();
                this._render();
                return;
            } catch (err) {
                console.warn('LIBI could not reopen the last project', err);
            }
        }
        if ((this._projectList || []).length === 1) {
            // Only one workspace exists, so there is nothing to choose between.
            this._project = { slug: this._projectList[0].slug, name: this._projectList[0].name };
            this._rememberProject();
        }
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
        this._markSaved();
        this._render(); 
    }
    
    // [CHANGED v3.67.0] SAVE & COMPILE is _saveProject, which returns what happened. The button shows it in an
    // alert as it always did; the AI chat shows it in the chat after adding a NET.
    _saveToBackend() {
        if (!this._hass || !this._hass.connection) {
            this.core.validateAST();
            this._render();
            return;
        }
        this._saveProject().then(r => {
            alert(this._saveResultText(r));
            if ((r.errors || []).length) console.warn('LIBI save reported problems', r.errors);
        });
    }

    /** [ADDED v3.85.0] What a save did, in words: the drawing's errors, why the compile did not hold, or the backend's
     *  own message. */
    _saveResultText(r) {
        if (r.refused) return 'Cannot compile: Syntax/Structural errors found (Missing Triggers, Missing Actions, or Missing Variables). Please fix red blocks.';
        if (r.compileErrors) return 'Not saved: the compile failed, so nothing was written.\n\n' + r.compileErrors.map(e => '• ' + e).join('\n');
        if (r.failed) return 'Save failed: ' + r.failed;
        return r.message || 'Saved.';
    }

    /** [ADDED v3.67.0] Validates the drawing and saves the project into Home Assistant. Returns the backend's
     *  answer (saved, written, reloaded, versions, errors, message), { refused } when the drawing has errors, or
     *  { failed } when the request did not get through. Only a save the backend confirms clears the unsaved mark.
     *  [CHANGED v3.85.0] Home Assistant's own config API writes - the HACS review: LIBI does not patch the user's YAML
     *  files. The user's rule (2026-11-04): compile first, save only when that holds. So: libi/compile_project compiles
     *  and checks every NET and writes nothing ({ compileErrors } when it does not hold); then each change goes to the
     *  config API, POST to save and DELETE to remove, as Home Assistant's editors make them, stopping at the first one it
     *  refuses; then libi/save_done records what reached Home Assistant and waits for each reload. */
    async _saveProject() {
        this.core.validateAST();
        this._render();
        if (!this._hass || !this._hass.connection) return { saved: false, failed: 'Not connected to Home Assistant.' };
        if (this.shadowRoot.querySelectorAll('.has-error').length > 0) return { saved: false, refused: true };
        // [CHANGED v3.14.0] The save belongs to the open project, so its ownership record is the
        // one that gets updated and no other workspace is touched.
        const slug = this._project ? this._project.slug : 'default';
        const name = this._project ? this._project.name : '';
        const nets = this.core.nets;
        const ws = (msg) => this._hass.connection.sendMessagePromise(msg);
        const said = (err) => this._staleBackend(err) || (err && err.message ? err.message : String(err));
        let plan;
        try {
            plan = (await ws({ type: 'libi/compile_project', slug, name, nets })) || {};
        } catch (err) {
            console.error('LIBI could not compile', err);
            return { saved: false, failed: said(err) };
        }
        if (!plan.ok) return { saved: false, compileErrors: (plan.errors || []).length ? plan.errors : ['the compile did not finish'] };
        const { done, failure } = await this._configApiSend([...(plan.upserts || []).map(op => ({ ...op, op: 'upsert' })),
            ...(plan.removals || []).map(op => ({ ...op, op: 'remove' }))]);
        let r;
        try {
            r = (await ws({ type: 'libi/save_done', slug, name, nets, done, failure, stamp: plan.stamp || '' })) || {};
        } catch (err) {
            console.error('LIBI could not record the save', err);
            return { saved: false, failed: said(err) };
        }
        // [CHANGED v3.34.0] Only a save the backend confirms makes the project match what is saved; [CHANGED v3.85.0] and
        // one in which Home Assistant refused nothing.
        r.complete = r.saved !== false && !failure;
        if (r.complete) this._markSaved();
        // [ADDED v3.47.0] The backend says which version of each net is the one now in Home Assistant.
        if (r.versions) this._versions = r.versions;
        if (!this._project && r.slug) {
            this._project = { slug: r.slug, name: 'Default' };
            this._rememberProject();
        }
        this._render();
        return r;
    }

    /** [ADDED v3.89.0] Each change to Home Assistant's config API, as its own editors send it - POST to save, DELETE to
     *  remove - stopping at the first one it refuses. SAVE & COMPILE, LIBI Global and the phone replaced with a global
     *  variable all send with it. Returns what was sent ({ domain, key, op }) and the refusal, if any. */
    async _configApiSend(ops) {
        const done = [];
        let failure = null;
        for (const [index, op] of ops.entries()) {
            const path = `config/${op.domain}/config/${encodeURIComponent(op.key)}`;
            try {
                if (op.op === 'upsert') await this._hass.callApi('POST', path, op.config);
                else await this._hass.callApi('DELETE', path);
                done.push({ domain: op.domain, key: op.key, op: op.op });
            } catch (err) {
                failure = { domain: op.domain, key: op.key, op: op.op, label: op.label || '', message: this._apiError(err),
                    not_sent: ops.length - index - 1 };
                break;
            }
        }
        return { done, failure };
    }

    /** [ADDED v3.85.0] A panel newer than the LIBI Home Assistant runs - copied in, Home Assistant not restarted (the
     *  JavaScript is new after a refresh, the Python only after a restart) - says so, instead of "Unknown command". */
    _staleBackend(err) {
        return err && err.code === 'unknown_command'
            ? 'LIBI was updated, but Home Assistant still runs the previous version. Restart Home Assistant (Settings ▸ System ▸ Restart), then try again.'
            : '';
    }

    /** [ADDED v3.85.0] Home Assistant's reason for refusing a call to its config API: the message it answered with. */
    _apiError(err) {
        const body = err && err.body;
        if (body && typeof body === 'object' && body.message) return String(body.message);
        if (typeof body === 'string' && body.trim()) return body.trim();
        if (err && (err.message || err.error)) return String(err.message || err.error);
        return String(err);
    }

    /** [ADDED v3.85.0] The NETs as they were last loaded or saved, to know whether anything is not saved - the user's rule
     *  (2026-11-04) asks before leaving with changes not saved. Only the logic counts: not the editor's own marks, nor a
     *  NET folded or unfolded. */
    _netsSnapshot() {
        const skip = new Set(['structuralError', 'collapsed', 'source', 'source_note']);
        return JSON.stringify(this.core.nets || [], (key, value) => (skip.has(key) ? undefined : value));
    }

    _markSaved() {
        try { this.core.validateAST(); } catch (err) { /* the snapshot is taken as it is */ }
        this._savedSnapshot = this._netsSnapshot();
        this._projectDirty = false;
    }

    /** [ADDED v3.85.0] Whether anything changed since the last load or save. checked: the drawing is checked first, as a
     *  save would check it, so its own marks are alike on both sides. */
    _hasUnsavedChanges(checked = false) {
        if (this._savedSnapshot === undefined) return !!this._projectDirty;
        if (checked) { try { this.core.validateAST(); } catch (err) { /* compared as it is */ } }
        return this._netsSnapshot() !== this._savedSnapshot;
    }

    /** [ADDED v3.85.0] A NET deleted and its project already letting go of it: the saved NETs no longer have it either. */
    _forgetSaved(nid) {
        if (this._savedSnapshot === undefined) return;
        try { this._savedSnapshot = JSON.stringify(JSON.parse(this._savedSnapshot).filter(n => !n || n.id !== nid)); }
        catch (err) { /* the next check compares with what it has */ }
    }

    /** [ADDED v3.85.0] A question with answers of its own - Yes and No, or the ways a NET can be deleted. Resolves to the
     *  id of the answer chosen. */
    _ask(title, text, answers) {
        return new Promise(resolve => {
            if (this._askState) this._askState.resolve(null);
            this._askState = { title, text, answers, resolve };
            this._modal = 'ask';
            this._render();
        });
    }

    _askDialogHtml() {
        const a = this._askState || { title: '', text: '', answers: [] };
        const notes = a.answers.filter(x => x.note)
            .map(x => `<p class="ask-note" dir="auto"><b>${this._esc(x.label)}</b>: ${this._esc(x.note)}</p>`).join('');
        const buttons = a.answers.map(x => `<button class="btn ${x.kind || 'btn-ghost'} ask-answer" data-answer="${this._esc(x.id)}">${this._esc(x.label)}</button>`).join('');
        return `<div class="modal-overlay" id="modalOverlay"><div class="modal ask-modal">
            <h2 class="modal-title" dir="auto">${this._esc(a.title)}</h2>
            <p class="ask-text" dir="auto">${this._esc(a.text)}</p>${notes}
            <div class="modal-actions ask-actions">${buttons}</div>
        </div></div>`;
    }

    _answerAsk(id) {
        const a = this._askState;
        this._askState = null;
        this._modal = null;
        this._render();
        if (a) a.resolve(id);
    }

    /** [ADDED v3.85.0] Leaving the editor - closing the project, opening another one, making a new one - with changes not
     *  saved asks whether to save them, the user's rule (2026-11-04). Yes runs SAVE & COMPILE and leaves only once that
     *  saved, saying why when it did not; No leaves them unsaved. Returns whether to go on. */
    async _leaveCheck() {
        if (!this._hasUnsavedChanges(true)) return true;
        const answer = await this._ask('The changes were not saved',
            'There are changes that are not saved in Home Assistant. Save them now?',
            [{ id: 'yes', label: 'Yes', kind: 'btn-primary' }, { id: 'no', label: 'No', kind: 'btn-ghost' }]);
        if (answer !== 'yes') return answer === 'no';
        const r = await this._saveProject();
        if (r.complete && r.status === 'ok') return true;
        alert(this._saveResultText(r));
        return !!r.complete;
    }

    /** [ADDED v3.85.0] Deleting a NET asks what becomes of it in Home Assistant - the user's rule (2026-11-04): deleted
     *  completely, or deleted and its automation put back as V1, the original it was before LIBI changed it; or removed
     *  from LIBI only, its automation left as it is now (what Remove from Net did). Home Assistant's config API makes the
     *  change; libi/net_removed lets the project go of the NET and waits for Home Assistant. Deleting completely still
     *  asks about the NET's local variables (v3.77.0). */
    async _deleteNet(nid) {
        const net = this.core.nets.find(n => n.id === nid);
        if (!net || !this._hass || !this._hass.connection) return;
        const ws = (msg) => this._hass.connection.sendMessagePromise(msg);
        const slug = this._project ? this._project.slug : 'default';
        let info;
        try {
            info = (await ws({ type: 'libi/net_delete_plan', slug, net_id: nid, nets: this.core.nets })) || {};
        } catch (err) {
            alert('Nothing was deleted: ' + (this._staleBackend(err) || 'LIBI could not check this NET - ' + (err && err.message ? err.message : err)));
            return;
        }
        if ((info.errors || []).length) {
            alert('Nothing was deleted: ' + info.errors.join('; '));
            return;
        }
        const kind = info.domain || 'automation';
        const answers = [{ id: 'delete', label: 'Delete completely', kind: 'btn-danger',
            note: info.in_ha ? `the NET goes, and its ${kind} is deleted from Home Assistant.` : 'the NET goes. It is not in Home Assistant.' }];
        if (info.in_ha && info.original) {
            answers.push({ id: 'restore', label: `Delete and go back to V${info.original.v}`, kind: 'btn-primary',
                note: `the NET goes, and its ${kind} goes back to V${info.original.v}, the original it was before LIBI changed it.` });
        }
        if (info.in_ha) answers.push({ id: 'keep', label: 'Remove from LIBI only', kind: 'btn-ghost', note: `the NET goes, and its ${kind} stays in Home Assistant as it is now.` });
        answers.push({ id: 'cancel', label: 'Cancel', kind: 'btn-ghost' });
        const number = this.core.nets.indexOf(net) + 1;
        const choice = await this._ask(`Delete NET ${number} "${net.name || ''}"?`,
            info.in_ha ? `What becomes of its ${kind} in Home Assistant?` : 'This NET is not in Home Assistant.', answers);
        if (!choice || choice === 'cancel') return;
        // [CHANGED v3.77.0] Its local variables go too when the user agrees - asked before anything is deleted, deleted
        // only once the NET and its automation are gone. A NET that stays in Home Assistant keeps them.
        let picked = [];
        if (choice === 'delete') {
            const runs = !info.in_ha && !!(net.ha_id && this.online.findAutomationEntity(this._hass, net));
            const local = runs ? null : await this._netHelpers(net, info.in_ha && kind === 'automation' ? info.key : '');
            const question = this._netHelpersQuestion(net, local);
            picked = question && confirm(question) ? local.helpers.map(h => h.entity_id) : [];
        }
        const path = `config/${info.domain}/config/${encodeURIComponent(info.key)}`;
        try {
            if (choice === 'delete' && info.in_ha) await this._hass.callApi('DELETE', path);
            if (choice === 'restore') await this._hass.callApi('POST', path, info.original.config);
        } catch (err) {
            alert('Nothing was deleted: Home Assistant refused it - ' + this._apiError(err));
            return;
        }
        let res;
        try {
            res = (await ws({ type: 'libi/net_removed', slug, net_id: nid, stamp: info.stamp || '',
                mode: { delete: 'deleted', restore: 'restored', keep: 'kept' }[choice],
                domain: info.in_ha ? info.domain : '', key: info.in_ha ? info.key : '' })) || {};
        } catch (err) {
            res = { ok: false, errors: [err && err.message ? err.message : String(err)] };
        }
        this.core.nets = this.core.nets.filter(n => n.id !== nid);
        this.core.pushHistory();
        this._forgetSaved(nid);
        this._inspectedEl = null;
        this._render();
        const errs = res.errors || [];
        let text = choice === 'restore' ? `NET ${number} was deleted, and its ${kind} is back to V${info.original.v}, the original.`
            : choice === 'keep' ? `NET ${number} was removed from LIBI. Its ${kind} stays in Home Assistant as it is now.`
            : info.in_ha ? `NET ${number} and its ${kind} were deleted.` : `NET ${number} was deleted.`;
        if (errs.length) text += '\n\nBut: ' + errs.join('; ');
        if (picked.length) {
            text += '\n\n' + (errs.length ? 'Its variables were kept: Home Assistant has not confirmed the automation is gone, so it may still run with them.'
                : await this._deleteNetHelpers(net, picked));
        }
        alert(text);
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
            // [CHANGED v3.85.0] The NET it goes into: the automation is recorded as it is, V1 the original and V2 its
            // copy - the user's rule (2026-11-04).
            const response = await this._hass.connection.sendMessagePromise({ type: 'libi/get_automation', automation_id: haId,
                slug: this._project ? this._project.slug : 'default', net_id: String(this._activeNetForLoad || '') });
            if (response && response.versions && Object.keys(response.versions).length) this._versions = response.versions;
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
             'move', 'coil', 'coil_s', 'coil_r', 'coil_t', 'timer_ton', 'ctu', 'repeat', 'parallel']
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
            else if (t.startsWith('coil')) pick(['coil', 'coil_s', 'coil_r', 'coil_t']);
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

    // [ADDED v3.86.1] A page that cannot be drawn says so on the screen. It stayed blank, with the error in the browser's
    // console only and nothing in Home Assistant's log (2026-11-04: the browser held an older libi-core.js under the
    // same ?v= as the new panel, and the first pin drawn threw).
    _render() {
        try {
            this._renderPage();
        } catch (err) {
            this._renderFailed(err);
        }
    }

    // [ADDED v3.86.1] Built with textContent: the error can carry text from the user's files. One box, on top of what
    // is on the screen; the next drawing that works replaces it with the rest.
    _renderFailed(err) {
        console.error(`[LIBI ${LIBI_BUILD}] the page could not be drawn:`, err);
        const sr = this.shadowRoot;
        if (!sr) return;
        let box = sr.getElementById('renderFail');
        if (!box) {
            box = document.createElement('div');
            box.id = 'renderFail';
            box.setAttribute('role', 'alert');
            box.style.cssText = 'margin:16px; padding:16px; max-width:720px; box-sizing:border-box; border:1px solid var(--error-color, #db4437); '
                + 'border-radius:8px; background:var(--card-background-color, #fff); color:var(--primary-text-color, #212121); '
                + 'font-family:var(--paper-font-body1_-_font-family, Roboto, sans-serif); font-size:14px; line-height:1.5;';
            const title = document.createElement('div');
            title.style.cssText = 'font-weight:700; font-size:16px; margin-block-end:8px;';
            title.textContent = 'LIBI could not draw this page';
            const help = document.createElement('div');
            help.textContent = 'If LIBI was just updated, the browser is most likely still using an older copy of one of its files. '
                + 'Reload the page without the cache: Ctrl+Shift+R (Cmd+Shift+R on a Mac). In the Home Assistant app, reset '
                + 'the frontend cache in the app settings.';
            const what = document.createElement('div');
            what.className = 'render-fail-error';
            what.style.cssText = 'margin-block-start:8px; font-family:monospace; font-size:12px; color:var(--secondary-text-color, #757575); overflow-wrap:anywhere;';
            const btn = document.createElement('button');
            btn.id = 'renderFailReload';
            btn.textContent = 'Reload the page';
            btn.style.cssText = 'margin-block-start:12px; min-height:40px; padding-inline:16px; border:0; border-radius:4px; '
                + 'background:var(--primary-color, #03a9f4); color:var(--text-primary-color, #fff); font-weight:600; cursor:pointer;';
            btn.addEventListener('click', () => location.reload());
            box.append(title, help, what, btn);
            sr.prepend(box);
        }
        box.querySelector('.render-fail-error').textContent = `LIBI ${LIBI_BUILD}: ${err && err.message ? err.message : String(err)}`;
    }

    _renderPage() {
        if (!this._initialized) return;

        localStorage.setItem('libi_draft', JSON.stringify(this.core.nets));

        const netsHtml = this.core.nets.map((n, i) => this._netHtml(n, i)).join('');
        const sidebarHtml = this._renderSidebar();
        const fanMenuHtml = this._renderFloatingMenu();
        
        let modalHtml = '';
        if (this._modal === 'list_automations') {
            const items = this._automationList.map(a => `<div class="auto-item" data-id="${this._esc(a.id)}"><div class="auto-item-name">${this._esc(a.name)}</div><div class="auto-item-id">ID: ${this._esc(a.id)}</div></div>`).join('');
            modalHtml = `<div class="modal-overlay" id="modalOverlay"><div class="modal" style="width: 500px;"><h2 class="modal-title">Select HA Automation</h2><p style="font-size:13px; color:var(--secondary-text-color, #757575); margin:0;">Choose an automation to load into this Net.</p><div class="auto-list" style="max-height:50vh;">${items || '<div style="padding:16px;text-align:center;">No automations found.</div>'}</div><div class="modal-actions"><button class="btn btn-ghost" id="closeModalBtn">Cancel</button></div></div></div>`;
        } else if (this._modal === 'project_new') {
            modalHtml = `<div class="modal-overlay" id="modalOverlay"><div class="modal" style="width:460px;">
                <h2 class="modal-title">New project</h2>
                <p style="font-size:13px; color:var(--secondary-text-color, #757575); margin:0 0 12px 0;">A project is a workspace of its own. It holds its nets and remembers which automation each one was loaded from, and it is stored as a .libi file in the configuration folder.</p>
                <div class="fgrp"><label>Project name</label><input type="text" id="projNewName" placeholder="Garden" dir="auto" /></div>
                <div class="modal-actions"><button class="btn btn-ghost" id="closeModalBtn">Cancel</button><button class="btn" id="projNewOk">Create</button></div>
            </div></div>`;
        } else if (this._modal === 'project_open') {
            const items = (this._projectList || []).map(p => `<div class="auto-item project-item" data-slug="${this._esc(p.slug)}">
                <div class="auto-item-name" dir="auto">${this._esc(p.name)}</div>
                <div class="auto-item-id">${this._esc(p.nets)} net${p.nets === 1 ? '' : 's'}${p.updated ? ' · saved ' + this._esc(String(p.updated).replace('T', ' ').replace('+00:00', ' UTC')) : ''}</div>
            </div>`).join('');
            modalHtml = `<div class="modal-overlay" id="modalOverlay"><div class="modal" style="width:520px;">
                <h2 class="modal-title">Open project</h2>
                ${items ? `<p style="font-size:13px; color:var(--secondary-text-color, #757575); margin:0;">Everything comes back as it was left, unfinished nets included.</p><div class="auto-list" style="max-height:60vh;">${items}</div>`
                        : `<p style="font-size:13px; color:var(--secondary-text-color, #757575);">There are no projects yet. Make one from New project.</p>`}
                <div class="modal-actions"><button class="btn btn-ghost" id="closeModalBtn">Cancel</button></div>
            </div></div>`;
        } else if (this._modal === 'project_delete') {
            const nm = this._project ? this._project.name : '';
            modalHtml = `<div class="modal-overlay" id="modalOverlay"><div class="modal" style="width:480px;">
                <h2 class="modal-title">Delete project</h2>
                <p style="font-size:14px; margin:0 0 8px 0;" dir="auto">This deletes <b>${this._esc(nm)}</b>, the drawing only.</p>
                <p style="font-size:13px; color:var(--secondary-text-color, #757575); margin:0;">The automations, scripts and scenes this project compiled stay exactly where they are in Home Assistant and keep running. Only the .libi file is removed, so the ladder is gone and the YAML is not.</p>
                <div class="modal-actions"><button class="btn btn-ghost" id="closeModalBtn">Cancel</button><button class="btn danger" id="projDeleteOk">Delete the drawing</button></div>
            </div></div>`;
        } else if (this._modal === 'net_versions') {
            modalHtml = this._versionsDialogHtml();
        } else if (this._modal === 'ask') {
            modalHtml = this._askDialogHtml();
        } else if (this._modal === 'global_move') {
            modalHtml = this._globalMoveDialogHtml();
        } else if (this._modal === 'entity_picker') {
            modalHtml = this._epDialogHtml();
        } else if (this._modal === 'rename_entity') {
            modalHtml = this._renameDialogHtml();
        } else if (this._modal === 'helper_new') {
            modalHtml = this._hkDialogHtml();
        } else if (this._modal === 'pick_level') {
            // [ADDED v3.5.0] A new net says what kind of logic it is before it exists, because the kind
            // decides which rules the linter applies and which file the net is compiled into.
            const levels = [
                { id: 'automation', icon: '\u26A1', title: 'Automation', desc: 'Reactive logic. Listens to the house and answers on its own. Needs a trigger and an action.' },
                { id: 'script', icon: '\uD83D\uDCDC', title: 'Script', desc: 'A subroutine. Runs from start to end when something calls it. No triggers, timers and loops allowed.' },
                { id: 'scene', icon: '\uD83C\uDFAC', title: 'Scene', desc: 'A snapshot. Value assignments only, applied at once. No triggers, no timing, no conditions.' },
            ];
            const items = levels.map(l => `<div class="auto-item level-item" data-level="${l.id}"><div class="auto-item-name">${l.icon} ${l.title}</div><div class="auto-item-id">${l.desc}</div></div>`).join('');
            modalHtml = `<div class="modal-overlay" id="modalOverlay"><div class="modal" style="width: 540px;"><h2 class="modal-title">What kind of logic do you want to create?</h2><p style="font-size:13px; color:var(--secondary-text-color, #757575); margin:0;">The kind cannot be guessed later, so LIBI asks for it now.</p><div class="auto-list" style="max-height:60vh;">${items}</div><div class="modal-actions"><button class="btn btn-ghost" id="closeModalBtn">Cancel</button></div></div></div>`;
        } else if (this._modal === 'logs') {
            modalHtml = `<div class="modal-overlay" id="modalOverlay"><div class="modal" style="width: 800px; max-width: 95vw;"><h2 class="modal-title">🐞 System Logs & AST Terminal</h2><textarea readonly rows="20" style="width:100%; font-family:monospace; font-size:12px; padding:12px; box-sizing:border-box; background:#1e1e1e; color:#00ff00; border:none; border-radius:4px; outline:none; resize:none;">${this._esc(JSON.stringify(this.core.nets, null, 2))}</textarea><div class="modal-actions"><button class="btn btn-primary" id="closeModalBtn">Close Terminal</button></div></div></div>`;
        }

        const allCollapsed = this.core.nets.length > 0 && this.core.nets.every(n => n.collapsed);
        // [ADDED v3.86.0] Where the ladder is scrolled to, put back after the redraw: every click on an element redraws
        // the panel, and the canvas went back to the top - so the right-click menu also opened where the block had been.
        const keep = this._scrollPlaces();
        this.shadowRoot.innerHTML = `
        <style>${getStyles()}</style>
        <div class="panel-layout">
            <div class="header">
                <!-- [ADDED v3.45.0] On a phone Home Assistant shows no bar of its own above a custom panel, so the
                     panel carries the button that opens HA's sidebar - the same hass-toggle-menu event HA's own
                     menu button fires. Shown when HA says the screen is narrow, or at phone width. -->
                <button class="ha-icon-btn hdr-ha-menu" id="haMenuBtn" title="Home Assistant menu"><svg viewBox="0 0 24 24"><path d="${MDI.menu}"></path></svg></button>
                <div class="header-title" style="display: flex; align-items: center;">
                    <!-- [CHANGED v3.35.0] The logo is the brand icon (brand/dark_icon@2x.png with its
                         background made transparent), so it reads on a light and a dark header alike. -->
                    <img class="hdr-logo" src="${LOGO_URL}" alt="" width="36" height="38" />
                    <span class="hdr-wordmark">LIBI</span>
                    ${this._projectChipHtml()}
                </div>
                <!-- [CHANGED v3.13.0] The header follows the automation editor of Home Assistant:
                     ghost icon buttons, one blue text action, one filled primary action, and an
                     overflow menu on the right for everything that is not used every minute. -->
                <div class="header-acts">
                    <!-- [CHANGED v3.45.0] On a phone these four live in the menu (hide-phone); the menu moves to
                         the left of the header and Save becomes a round icon, so nothing is wider than the screen. -->
                    ${this._iconBtn('undoBtn', MDI.undo, 'Undo (Ctrl+Z)', 'hide-phone')}
                    ${this._iconBtn('redoBtn', MDI.redo, 'Redo (Ctrl+Y)', 'hide-phone')}
                    ${this._iconBtn('collapseAllBtn', allCollapsed ? MDI.unfold : MDI.collapse, allCollapsed ? 'Expand every net' : 'Collapse every net', 'hide-phone')}
                    <button class="ha-text-btn hide-phone ${this.online.enabled ? 'online-on' : ''}" id="onlineBtn" title="Follow the automations as they run">${this.online.enabled ? '● Traces' : 'Traces'}</button>
                    <button class="ha-btn-primary" id="saveBtn" title="Save the drawing and compile it into Home Assistant">
                        <svg viewBox="0 0 24 24"><path d="${MDI.save}"></path></svg><span class="save-lbl">SAVE &amp; COMPILE</span>
                    </button>
                    <div class="hdr-menu-wrap">
                        ${this._iconBtn('hdrMenuBtn', MDI.dots, 'More')}
                        <div class="hdr-menu${this._hdrMenu ? ' show' : ''}" id="hdrMenu">
                            <button class="hdr-menu-item phone-only" id="mUndo"><svg viewBox="0 0 24 24" style="width:20px;height:20px;fill:currentColor;"><path d="${MDI.undo}"></path></svg>Undo</button>
                            <button class="hdr-menu-item phone-only" id="mRedo"><svg viewBox="0 0 24 24" style="width:20px;height:20px;fill:currentColor;"><path d="${MDI.redo}"></path></svg>Redo</button>
                            <button class="hdr-menu-item phone-only" id="mCollapse">${allCollapsed ? `<svg viewBox="0 0 24 24" style="width:20px;height:20px;fill:currentColor;"><path d="${MDI.unfold}"></path></svg>Expand every net` : `<svg viewBox="0 0 24 24" style="width:20px;height:20px;fill:currentColor;"><path d="${MDI.collapse}"></path></svg>Collapse every net`}</button>
                            <button class="hdr-menu-item phone-only${this.online.enabled ? ' online-on' : ''}" id="mOnline"><svg viewBox="0 0 24 24" style="width:20px;height:20px;fill:currentColor;"><path d="${MDI.pulse}"></path></svg>${this.online.enabled ? 'Traces: stop following' : 'Traces: follow the automations'}</button>
                            <div class="hdr-menu-sep phone-only"></div>
                            <button class="hdr-menu-item" id="projNewBtn"><svg viewBox="0 0 24 24" style="width:20px;height:20px;fill:currentColor;"><path d="${MDI.filePlus}"></path></svg>New project</button>
                            <button class="hdr-menu-item" id="projOpenBtn"><svg viewBox="0 0 24 24" style="width:20px;height:20px;fill:currentColor;"><path d="${MDI.folderOpen}"></path></svg>Open project</button>
                            <button class="hdr-menu-item" id="projCloseBtn" ${this._project ? '' : 'disabled'}><svg viewBox="0 0 24 24" style="width:20px;height:20px;fill:currentColor;"><path d="${MDI.close}"></path></svg>Close project</button>
                            <button class="hdr-menu-item danger" id="projDeleteBtn" ${this._project ? '' : 'disabled'}><svg viewBox="0 0 24 24" style="width:20px;height:20px;fill:currentColor;"><path d="${MDI.trashCan}"></path></svg>Delete project</button>
                            <div class="hdr-menu-sep"></div>
                            <button class="hdr-menu-item" id="logsBtn"><svg viewBox="0 0 24 24" style="width:20px;height:20px;fill:currentColor;"><path d="${MDI.bug}"></path></svg>Terminal / Logs</button>
                            <button class="hdr-menu-item danger" id="clearAllBtn"><svg viewBox="0 0 24 24" style="width:20px;height:20px;fill:currentColor;"><path d="${MDI.trashCan}"></path></svg>Clear all nets</button>
                        </div>
                    </div>
                </div>
            </div>
            <div class="main-content">
                <div class="canvas">${this.core.nets.length ? '' : `
                    <div class="canvas-empty">
                        <div class="canvas-empty-text">No automation on the canvas yet</div>
                        <button class="ha-text-btn add-net-btn" id="addNetTop">➕ ADD NET</button>
                    </div>`}${netsHtml}${this.core.nets.length ? `
                    <button class="ha-text-btn add-net-btn" id="addNetBottom">➕ ADD NET</button>` : ''}</div>
                <div class="sidebar${this._sidebarRail ? ' rail' : ''}" id="sidebarContainer">
                    <div class="sidebar-grip" id="sidebarGrip" title="Drag to resize. Double click to reset."></div>
                    <div class="sidebar-top">
                        <button class="sidebar-toggle" id="sidebarToggle" title="${this._sidebarRail ? `Open the sidebar (${this._sidebarW}px)` : 'Close the sidebar to a narrow rail'}">${this._sidebarRail ? '❮' : '❯'}</button>
                        <span class="grow">Inspector</span>
                    </div>
                    <div class="sidebar-rail-tag">LIBI</div>
                    <button class="sidebar-rail-ai" id="railAiBtn" title="Open the AI chat">CHAT AI</button>
                    <div class="sidebar-content">${sidebarHtml}</div>
                    <div class="ai-mount" id="aiChatMount"></div>
                </div>
            </div>
            ${this._varsBarHtml()}
        </div>
        ${this._ctxMenuHtml()}
        ${fanMenuHtml}
        ${modalHtml}
        <svg id="dragOverlay" style="position:fixed; top:0; left:0; width:100vw; height:100vh; pointer-events:none; z-index:9999; display:none;">
            <path id="dragPath" stroke="#03a9f4" stroke-width="3" fill="none" stroke-dasharray="4" />
        </svg>
        `;
        
        this._bindEvents();
        this._injectNativePickers(); 
        this._paintOnline();
        this.aiChat.attach(this.shadowRoot.getElementById('aiChatMount'));
        this._restoreScrollPlaces(keep);
        this._placeCtxMenu();
    }

    // [ADDED v3.86.0] The scroll of the canvas, and of the rungs of each NET by its id, in the project open now.
    _scrollPlaces() {
        const sr = this.shadowRoot;
        const canvas = sr && sr.querySelector('.canvas');
        if (!canvas) return null;
        const nets = {};
        sr.querySelectorAll('.rung-scroll[data-nid]').forEach(sc => { nets[sc.getAttribute('data-nid')] = sc.scrollLeft; });
        return { project: this._project ? this._project.slug : '', top: canvas.scrollTop, left: canvas.scrollLeft, nets };
    }

    _restoreScrollPlaces(keep) {
        // Another project starts at its top.
        if (!keep || keep.project !== (this._project ? this._project.slug : '')) return;
        const sr = this.shadowRoot;
        const canvas = sr.querySelector('.canvas');
        if (canvas) { canvas.scrollTop = keep.top; canvas.scrollLeft = keep.left; }
        sr.querySelectorAll('.rung-scroll[data-nid]').forEach(sc => {
            const left = keep.nets[sc.getAttribute('data-nid')];
            if (left) sc.scrollLeft = left;
        });
    }

    // [ADDED v3.86.0] The right-click menu opens where the click was, measured once it is drawn - a container of Home
    // Assistant that moves what is fixed inside it would put it elsewhere - and stays on the screen near an edge.
    _placeCtxMenu() {
        const menu = this.shadowRoot.getElementById('ctxMenu');
        if (!menu || !this._ctx) return;
        const r = menu.getBoundingClientRect();
        const x = Math.max(4, Math.min(this._ctx.x, window.innerWidth - r.width - 4));
        const y = Math.max(4, Math.min(this._ctx.y, window.innerHeight - r.height - 4));
        menu.style.left = `${parseFloat(menu.style.left) + (x - r.left)}px`;
        menu.style.top = `${parseFloat(menu.style.top) + (y - r.top)}px`;
    }

    // [ADDED v3.86.0] The user's choice (2026-11-04): the title of a NET shows the variables of that NET only in the bar
    // at the bottom, the title of the project the variables of all its NETs.
    _selectNet(nid) {
        this._selectedNetId = nid;
        this._varsScope = 'net';
        this._showVarsTab();
    }

    _selectProject() {
        this._varsScope = 'project';
        this._showVarsTab();
    }

    _showVarsTab() {
        this._varsTab = 'vars';
        this._varsOpen = true;
        this._saveVars();
        this._render();
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
            // [CHANGED v3.63.0] The same panel shows the NET's dashboard card, with where it goes and a Copy button.
            const card = this._netYamlKind === 'card';
            const hint = card ? `<div class="net-card-hint" style="padding:10px 16px 0; font-size:12px; line-height:1.4; color:#bdbdbd;">Open a dashboard, Edit ▸ Add card ▸ Manual, and paste this.</div>` : '';
            const copy = card ? `<button class="btn" id="copyNetCard" style="width:100%; margin-bottom:8px;">Copy</button>` : '';
            return `<div class="sidebar-hdr">${card ? 'Dashboard card' : 'Net YAML'}: ${this._esc(net.name)}</div><div class="sidebar-body" style="padding:0; display:flex; flex-direction:column; background:#1e1e1e;">${hint}<textarea class="yaml-preview-box" readonly>${this._esc(this._previewYamlContent)}</textarea><div style="padding: 16px;">${copy}<button class="btn btn-ghost" id="closeYamlSidebar" style="width:100%; color:white; border-color:var(--secondary-text-color, #555);">${card ? 'Close' : 'Close YAML Preview'}</button></div></div>`;
        }

        if (!this._inspectedEl) {
            return `<div class="sidebar-hdr">Inspector</div><div class="sidebar-body"><p style="color:var(--secondary-text-color, #757575);">Select any element on the canvas to view and edit its properties.</p></div>`;
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
                        <option value="coil_t" ${el.type === 'coil_t' ? 'selected' : ''}>Toggle Coil (T)</option>
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
                        ${el.type === 'wait' ? '<option value="wait" selected>Wait for Trigger (old drawing)</option>' : ''}
                        ${el.type === 'notify' ? '<option value="notify" selected>Send Notification (old drawing)</option>' : ''}
                    </select>
                </div>
                ${elLevel === 'automation' && !el.type.startsWith('coil') && !el.type.startsWith('math') && el.type !== 'move' && el.type !== 'notify' && el.type !== 'ctu' && el.type !== 'repeat' ? `
                <div class="fgrp checkbox-grp">
                    <input type="checkbox" id="propIsTrigger" ${el.isTrigger ? 'checked' : ''} />
                    <label style="margin:0; font-weight:800; color:var(--success-color, #4caf50);">[✔] Use as Trigger (Starts Flow)</label>
                </div>
                ` : ''}
                ${elLevel !== 'automation' ? `
                <div class="fgrp" style="font-size:12px; color:var(--secondary-text-color, #757575);">
                    A ${elLevel} is never started by the house, so there is no trigger to set here.
                </div>
                ` : ''}
                <div id="dynamicPickerSlot"></div>
                <div style="flex:1"></div>
                <button class="btn btn-danger" id="propDelete">🗑 Delete Element</button>
            </div>
        `;
    }

    // [ADDED v3.24.0] The service a coil calls. The list is the services of the entity's own domain,
    // so a cover offers closing, opening and stopping. Changing it also changes which coil is drawn,
    // because closing latches and stopping releases.
    _serviceField(el) {
        const wrap = document.createElement('div');
        wrap.className = 'fgrp';
        const entity = String(el.label || '').replace(/\s*\+\d+$/, '').trim();
        const domain = entity.includes('.') ? entity.split('.')[0] : '';
        const table = this.core.COIL_SERVICES();
        const list = (table[domain] || ['turn_on', 'turn_off', 'toggle']).slice();
        const current = String(el.service || '');
        if (current && !list.includes(current.split('.').pop())) list.unshift(current.split('.').pop());
        const dom = domain || (current.includes('.') ? current.split('.')[0] : 'homeassistant');
        wrap.innerHTML = `<label id="lbl_service">Action</label>
            <select id="inp_service">${list.map(s => {
                const full = `${dom}.${s}`;
                return `<option value="${this._esc(full)}" ${full === current ? 'selected' : ''}>${this._esc(full)}</option>`;
            }).join('')}</select>`;
        const sel = wrap.querySelector('#inp_service');
        sel.addEventListener('change', (e) => {
            el.service = e.target.value;
            // The symbol follows the verb, so close becomes (S) and stop becomes (R).
            const next = this.core.coilForService(el.service);
            if (next) el.type = next;
            this.core.pushHistory();
            this._render();
        });
        return wrap;
    }

    // [ADDED v3.24.0] continue_on_error, with the drawing it produces spelled out.
    _coeField(el) {
        const wrap = document.createElement('div');
        wrap.className = 'fgrp checkbox-grp';
        wrap.innerHTML = `<input type="checkbox" id="inp_coe" ${el.continueOnError ? 'checked' : ''} />
            <label style="margin:0;">Continue on error
                <span style="display:block; font-weight:400; font-size:11px; color:var(--secondary-text-color, #757575);">Draws a bypass around this block. The rung carries on to the next checks even if the action fails or the entity is unavailable.</span>
            </label>`;
        wrap.querySelector('#inp_coe').addEventListener('change', (e) => {
            el.continueOnError = e.target.checked;
            this.core.pushHistory();
            this._render();
        });
        return wrap;
    }

    // [ADDED v3.32.0] ------------------------------------------------------------------
    // The entity chooser. Home Assistant sorts the things you can point at two ways: where they
    // are, and what they are. Both are built here from the registries the panel already holds, so
    // choosing a variable never means remembering an entity id.

    EP_ICONS() {
        return {
            air_quality:'🜁', battery:'🔋', button:'⏻', calendar:'📅', climate:'🌡', counter:'#',
            cover:'🪟', door:'🚪', fan:'🌀', gate:'⛩', humidity:'💧', illuminance:'☀',
            blind:'🪟', curtain:'🪟', shade:'🪟', shutter:'🪟', awning:'🪟', garage:'🚗', window:'🪟',
            smoke:'🔥', gas:'☁', problem:'⚠', safety:'🛡', connectivity:'📶', presence:'🏠',
            energy:'⚡', voltage:'⚡', current:'⚡', pressure:'📉', signal_strength:'📶',
            light:'💡', lock:'🔒', media_player:'📺', moisture:'💦', motion:'🏃', occupancy:'🏠',
            power:'⚡', remote:'📱', scene:'🎬', schedule:'🗓', select:'☰', siren:'📢', sun:'☼',
            switch:'🔘', temperature:'🌡', text:'T', timer:'⏱', update:'⬆', vacuum:'🧹',
            valve:'🚰', water_heater:'♨', person:'👤', device_tracker:'📍', binary_sensor:'◐',
            sensor:'📈', automation:'⚡', script:'📜', input_boolean:'⏼', input_number:'↔',
            input_text:'T', input_select:'☰', input_datetime:'🕐', input_button:'⏻',
            number:'↔', device:'🔌', area:'▦', label:'🏷', helper:'🧩', entity:'◈',
            scene:'🎬', zone:'📍',
        };
    }

    EP_TYPE_NAMES() {
        return {
            air_quality:'Air Quality', battery:'Battery', button:'Button', calendar:'Calendar',
            climate:'Climate', counter:'Counter', cover:'Cover', door:'Door', fan:'Fan', gate:'Gate',
            humidity:'Humidity', illuminance:'Illuminance', light:'Light', lock:'Lock',
            media_player:'Media player', moisture:'Moisture', motion:'Motion', occupancy:'Occupancy',
            power:'Power', remote:'Remote', scene:'Scene', schedule:'Schedule', select:'Select',
            siren:'Siren', sun:'Sun', switch:'Switch', temperature:'Temperature', text:'Text',
            timer:'Timer', update:'Update', vacuum:'Vacuum', valve:'Valve',
            water_heater:'Water heater', person:'Person', device_tracker:'Device tracker',
            binary_sensor:'Binary sensor', sensor:'Sensor', automation:'Automation', script:'Script',
            number:'Number', input_boolean:'Toggle', input_number:'Number', input_text:'Text',
            input_select:'Dropdown', input_datetime:'Date and time', input_button:'Button',
            // The classes a cover or a valve declares, which Home Assistant lists in their own right.
            blind:'Blind', curtain:'Curtain', shade:'Shade', shutter:'Shutter', awning:'Awning',
            damper:'Damper', garage:'Garage', window:'Window',
            // And the ones a binary sensor declares.
            smoke:'Smoke', gas:'Gas', problem:'Problem', safety:'Safety', tamper:'Tamper',
            connectivity:'Connectivity', presence:'Presence', vibration:'Vibration', sound:'Sound',
            cold:'Cold', heat:'Heat', running:'Running', plug:'Plug', energy:'Energy',
            voltage:'Voltage', current:'Current', pressure:'Pressure', signal_strength:'Signal',
            carbon_dioxide:'Carbon dioxide', carbon_monoxide:'Carbon monoxide', pm25:'Particulates',
        };
    }

    // What kind a thing is: its device class when it declares one, otherwise its domain. That is
    // exactly the split the By type list of Home Assistant shows.
    _epTypeOf(entityId) {
        const st = (this._hass && this._hass.states && this._hass.states[entityId]) || null;
        const dc = st && st.attributes ? st.attributes.device_class : '';
        const domain = String(entityId).split('.')[0];
        if (dc && (domain === 'sensor' || domain === 'binary_sensor' || domain === 'cover' || domain === 'valve')) {
            return String(dc);
        }
        return domain;
    }

    _epMatches(entityId) {
        const q = String(this._epQuery || '').trim().toLowerCase();
        if (!q) return true;
        const nm = (this.core.friendlyName(entityId, this._hass) || '').toLowerCase();
        return entityId.toLowerCase().includes(q) || nm.includes(q);
    }

    _epAll() {
        const states = (this._hass && this._hass.states) || {};
        return Object.keys(states).filter(e => this._epMatches(e)).sort();
    }

    _epGroupHtml(key, icon, name, entities, current) {
        if (!entities.length) return '';
        const open = !!this._epOpen[key] || !!String(this._epQuery || '').trim();
        const rows = open ? entities.map(e => {
            const nm = this.core.friendlyName(e, this._hass) || e.split('.').slice(1).join('.');
            const st = (this._hass.states || {})[e];
            return `<div class="ep-item${e === current ? ' cur' : ''} ep-pick" data-eid="${this._esc(e)}">
                <span class="ico">${this.EP_ICONS()[this._epTypeOf(e)] || '◈'}</span>
                <span class="txt"><span class="nm" dir="auto">${this._esc(nm)}</span><span class="eid">${this._esc(e)}</span></span>
                <span class="st">${st ? this._esc(String(st.state).slice(0, 12)) : '—'}</span>
            </div>`;
        }).join('') : '';
        return `<div class="ep-group${open ? ' open' : ''} ep-fold" data-k="${this._esc(key)}">
                <span class="chev">▶</span><span class="ico">${icon}</span>
                <span class="nm" dir="auto">${this._esc(name)}</span><span class="ct">${entities.length}</span>
            </div>${rows}`;
    }

    // [ADDED v3.33.0] A group that holds other groups rather than entities, so Unassigned, Devices
    // and the rest fold away like everything else instead of being headings that cannot be closed.
    _epNestHtml(key, icon, name, count, inner) {
        if (!count) return '';
        const open = !!this._epOpen[key] || !!String(this._epQuery || '').trim();
        return `<div class="ep-group${open ? ' open' : ''} ep-fold" data-k="${this._esc(key)}">
                <span class="chev">▶</span><span class="ico">${icon}</span>
                <span class="nm">${this._esc(name)}</span><span class="ct">${count}</span>
            </div>${open ? `<div style="padding-left:14px;">${inner}</div>` : ''}`;
    }

    // Which integration brought an entity in. It is what tells a Zigbee light from a Wi-Fi one.
    _epPlatform(entityId) {
        const reg = (this._hass && this._hass.entities && this._hass.entities[entityId]) || null;
        return String((reg && reg.platform) || '');
    }

    _epByTargetHtml(current) {
        const h = this._hass || {};
        const all = this._epAll();
        const I = this.EP_ICONS();
        const HELPERS = ['input_boolean','input_number','input_text','input_select','input_datetime','input_button','counter','timer','schedule'];
        const ZIGBEE = ['zha', 'deconz', 'zigbee2mqtt', 'mqtt'];
        const WIFI = ['esphome', 'shelly', 'tasmota', 'tuya', 'wled', 'hue', 'tplink', 'yeelight'];

        const byArea = {};
        const noArea = [];
        all.forEach(e => {
            const a = this._areaOfForPicker(e);
            if (a) (byArea[a] = byArea[a] || []).push(e);
            else noArea.push(e);
        });

        let out = '';
        const areaIds = Object.keys(byArea).sort((a, b) =>
            String(((h.areas || {})[a] || {}).name || a).localeCompare(String(((h.areas || {})[b] || {}).name || b)));
        if (areaIds.length) {
            out += `<div class="ep-sec">Home</div>`;
            areaIds.forEach(a => {
                out += this._epGroupHtml(`area:${a}`, I.area, ((h.areas || {})[a] || {}).name || a, byArea[a], current);
            });
        }

        // Time and sun. Sun is an entity like any other, the rest are kinds of trigger and are
        // offered only where a trigger is what is being chosen.
        const timeItems = this.EP_TRIGGER_KINDS().filter(k => k.section === 'time');
        out += `<div class="ep-sec">Time and sun</div>`;
        out += timeItems.map(k => this._epTriggerRowHtml(k)).join('');

        const devIds = Object.keys(h.devices || {}).filter(d =>
            all.some(e => ((h.entities || {})[e] || {}).device_id === d))
            .sort((a, b) => String((h.devices[a] || {}).name || a).localeCompare(String((h.devices[b] || {}).name || b)));
        const labelIds = Object.keys(h.labels || {}).filter(l =>
            all.some(e => (((h.entities || {})[e] || {}).labels || []).includes(l)));

        const pick = (fn) => all.filter(fn);
        const helpers = pick(e => HELPERS.includes(e.split('.')[0]));
        const services = pick(e => ['script', 'scene', 'automation'].includes(e.split('.')[0]));
        const phones = pick(e => e.split('.')[0] === 'device_tracker' || this._epPlatform(e) === 'mobile_app');
        const users = pick(e => e.split('.')[0] === 'person');
        const zigbee = pick(e => ZIGBEE.includes(this._epPlatform(e)));
        const wifi = pick(e => WIFI.includes(this._epPlatform(e)));

        // Everything under one fold, the way Home Assistant groups what has no area.
        let inner = '';
        inner += this._epGroupHtml('all:entities', I.entity, 'Entities', noArea.length ? noArea : all, current);
        inner += this._epGroupHtml('all:helpers', I.helper, 'Helpers', helpers, current);
        inner += this._epNestHtml('nest:devices', I.device, 'Devices', devIds.length,
            devIds.map(d => {
                const own = all.filter(e => ((h.entities || {})[e] || {}).device_id === d);
                const dev = h.devices[d] || {};
                return this._epGroupHtml(`dev:${d}`, I.device, dev.name_by_user || dev.name || d, own, current);
            }).join(''));
        inner += this._epGroupHtml('all:services', I.script, 'Services', services, current);
        inner += this._epGroupHtml('all:phones', I.device_tracker, 'Mobile phones', phones, current);
        inner += this._epGroupHtml('all:users', I.person, 'Users', users, current);
        inner += this._epGroupHtml('all:zigbee', '🐝', 'Zigbee', zigbee, current);
        inner += this._epGroupHtml('all:wifi', '📶', 'Wi-Fi', wifi, current);

        out += this._epNestHtml('nest:unassigned', I.entity, 'Unassigned', all.length, inner);

        if (labelIds.length) {
            out += `<div class="ep-sec">Labels</div>`;
            labelIds.forEach(l => {
                const own = all.filter(e => (((h.entities || {})[e] || {}).labels || []).includes(l));
                out += this._epGroupHtml(`lab:${l}`, I.label, ((h.labels || {})[l] || {}).name || l, own, current);
            });
        }

        // The kinds of trigger that are not entities at all, offered on a block that is a trigger.
        const generic = this.EP_TRIGGER_KINDS().filter(k => k.section === 'generic');
        out += `<div class="ep-sec">Generic</div>`;
        out += generic.map(k => this._epTriggerRowHtml(k)).join('');

        return out || `<div class="ep-empty">Nothing matches that.</div>`;
    }

    // [ADDED v3.33.0] The entries of the Home Assistant list that are kinds of trigger rather than
    // things in the house. They are offered plainly, and a block that is not a trigger says so
    // rather than quietly doing nothing.
    EP_TRIGGER_KINDS() {
        return [
            { id: 'time',     name: 'Time',     icon: '🕐', section: 'time',    node: { trigger: 'time', at: '07:00:00' } },
            { id: 'sun',      name: 'Sun',      icon: '☼',  section: 'time',    node: { trigger: 'sun', event: 'sunset' } },
            { id: 'sentence', name: 'Sentence', icon: '🗣', section: 'generic', node: { trigger: 'conversation', command: 'good night' } },
            { id: 'template', name: 'Template', icon: '{}', section: 'generic', node: { trigger: 'template', value_template: '{{ true }}' } },
            { id: 'webhook',  name: 'Webhook',  icon: '🪝', section: 'generic', node: { trigger: 'webhook', webhook_id: 'libi_hook' } },
            { id: 'zone',     name: 'Zone',     icon: '📍', section: 'generic', node: { trigger: 'zone', entity_id: 'person.me', zone: 'zone.home', event: 'enter' } },
            { id: 'event',    name: 'Event',    icon: '👁', section: 'generic', node: { trigger: 'event', event_type: 'my_event' } },
        ];
    }

    _epTriggerRowHtml(kind) {
        const q = String(this._epQuery || '').trim().toLowerCase();
        if (q && !kind.name.toLowerCase().includes(q) && !kind.id.includes(q)) return '';
        return `<div class="ep-item ep-kind" data-k="${kind.id}" style="padding-left:16px;">
            <span class="ico">${kind.icon}</span>
            <span class="txt"><span class="nm">${this._esc(kind.name)}</span><span class="eid">a kind of trigger, not an entity</span></span>
        </div>`;
    }

    _applyTriggerKind(kindId) {
        const kind = this.EP_TRIGGER_KINDS().find(k => k.id === kindId);
        const p = this._ep;
        if (!kind || !p) return;
        const el = this.core.findEl(p.netId, p.rungId, p.elId);
        if (!el) return;
        if (!el.isTrigger) {
            alert(`${kind.name} is a kind of trigger. Mark this block as the trigger of the rung first, or pick an entity instead.`);
            return;
        }
        el.raw = JSON.parse(JSON.stringify(kind.node));
        el.eventKind = kind.node.trigger;
        el.type = 'contact_p';
        el.label = kind.id === 'sun' ? 'sun.sun' : `${kind.node.trigger}.${kind.id}`;
        delete el.service;
        delete el.targetSpec;
        this.core.pushHistory();
        this._ep = null;
        this._modal = null;
        this._render();
    }

    _epByTypeHtml(current) {
        const all = this._epAll();
        const I = this.EP_ICONS();
        const N = this.EP_TYPE_NAMES();
        const buckets = {};
        all.forEach(e => { const k = this._epTypeOf(e); (buckets[k] = buckets[k] || []).push(e); });
        const keys = Object.keys(buckets).sort((a, b) =>
            String(N[a] || a).localeCompare(String(N[b] || b)));
        if (!keys.length) return `<div class="ep-empty">Nothing matches that.</div>`;
        return keys.map(k => this._epGroupHtml(`type:${k}`, I[k] || '◈',
            N[k] || k.replace(/_/g, ' '), buckets[k], current)).join('');
    }

    _epDialogHtml() {
        const current = (this._ep && this._ep.current) || '';
        const body = this._epTab === 'type' ? this._epByTypeHtml(current) : this._epByTargetHtml(current);
        return `<div class="modal-overlay" id="modalOverlay"><div class="modal ep-modal">
            <h2 class="modal-title">Choose an entity</h2>
            ${current ? `<p class="ep-cur">replacing ${this._esc(current)}</p>` : ''}
            <div class="ep-top"><input type="text" id="epSearch" placeholder="Search" value="${this._esc(this._epQuery)}" dir="auto" /></div>
            <div class="ep-tabs">
                <button class="ep-tab${this._epTab === 'target' ? ' on' : ''}" id="epTabTarget">By target</button>
                <button class="ep-tab${this._epTab === 'type' ? ' on' : ''}" id="epTabType">By type</button>
            </div>
            <div class="ep-body">${body}</div>
            <div class="modal-actions"><button class="btn btn-ghost" id="closeModalBtn">Cancel</button></div>
        </div></div>`;
    }

    _areaOfForPicker(entityId) {
        const h = this._hass || {};
        const reg = (h.entities || {})[entityId] || null;
        if (reg && reg.area_id) return reg.area_id;
        const dev = reg && reg.device_id && h.devices ? h.devices[reg.device_id] : null;
        return (dev && dev.area_id) || '';
    }

    // Opened from the block, from the right click menu, or from the inspector.
    _openEntityPicker(netId, rungId, elId, prop) {
        const el = this.core.findEl(netId, rungId, elId);
        if (!el) return;
        const field = prop || (String(el.type || '').startsWith('cmp') ? 'sourceA'
                    : (el.type === 'move' ? 'target' : 'label'));
        this._ep = { netId, rungId, elId, prop: field,
                     current: String(el[field] || '').replace(/\s*\+\d+$/, '').trim() };
        this._epQuery = '';
        this._epOpen = {};
        this._modal = 'entity_picker';
        this._render();
    }

    _applyPickedEntity(entityId) {
        const p = this._ep;
        if (!p) return;
        const el = this.core.findEl(p.netId, p.rungId, p.elId);
        if (el) {
            // [CHANGED v3.87.0] A message's target is an action: a phone chosen by its notify entity sends with the
            // phone's action, as in the Inspector (_notifyTargetField). A message has no target spec.
            const message = p.prop === 'target' && this._sendsMessage(el);
            const phone = message ? this.core.phoneOf(entityId) : null;
            el[p.prop] = phone ? phone.service : entityId;
            if (!message && (p.prop === 'label' || p.prop === 'target')) {
                el.targetSpec = { entity_id: [entityId] };
                el.targetKind = 'entity';
                el.targetLabel = entityId;
            }
            this.core.pushHistory();
            this._projectDirty = true;
        }
        this._ep = null;
        this._modal = null;
        this._render();
    }

    // [ADDED v3.31.0] The device an entity sits on, and every entity that device offers. A name on
    // its own is never enough to know which physical thing a block drives, so the inspector shows
    // the device for every block and lets the entity be picked out of that device.
    _deviceOfEntity(entityId) {
        const reg = (this._hass && this._hass.entities && this._hass.entities[entityId]) || null;
        return (reg && reg.device_id) || '';
    }

    _entitiesOfDevice(deviceId) {
        const reg = (this._hass && this._hass.entities) || {};
        return Object.keys(reg).filter(e => reg[e] && reg[e].device_id === deviceId).sort();
    }

    // Shown above the entity on every coil, contact and wait: which device this is, and a list of
    // that device's own entities to choose between.
    _deviceContextFields(el, entityId) {
        const out = [];
        const deviceId = this._deviceOfEntity(entityId);

        out.push(this._picker('device', deviceId, v => {
            // Picking a different device moves the block to that device's first sensible entity.
            const list = this._entitiesOfDevice(v);
            const domain = String(entityId || '').split('.')[0];
            const next = list.find(e => e.split('.')[0] === domain) || list[0] || '';
            if (next) {
                el.label = next;
                el.targetSpec = { entity_id: [next] };
                el.targetKind = 'entity';
                el.targetLabel = next;
                this.core.pushHistory();
            }
            this._render();
        }, { label: 'Device', id: 'device' }));

        const siblings = this._entitiesOfDevice(deviceId);
        if (deviceId && siblings.length > 1) {
            const wrap = document.createElement('div');
            wrap.className = 'fgrp';
            wrap.innerHTML = `<label id="lbl_sibling">Entity of this device</label>
                <select id="inp_sibling">${siblings.map(e => {
                    const nm = this.core.friendlyName(e, this._hass) || e.split('.').slice(1).join('.');
                    return `<option value="${this._esc(e)}" ${e === entityId ? 'selected' : ''}>${this._esc(nm)} — ${this._esc(e)}</option>`;
                }).join('')}</select>`;
            wrap.querySelector('#inp_sibling').addEventListener('change', (e) => {
                el.label = e.target.value;
                el.targetSpec = { entity_id: [e.target.value] };
                el.targetKind = 'entity';
                el.targetLabel = e.target.value;
                this.core.pushHistory();
                this._render();
            });
            out.push(wrap);
        } else if (!deviceId) {
            const note = document.createElement('div');
            note.className = 'fgrp';
            note.innerHTML = `<div style="font-size:12px; color:var(--secondary-text-color, #9e9e9e); margin-top:-8px;">This entity does not belong to a device.</div>`;
            out.push(note);
        }
        return out;
    }

    // [ADDED v3.26.0] What Home Assistant calls this device trigger or action. The wording lives in
    // the translations of the integration behind the device, which is why a Zigbee button reads
    // "First button" pressed rather than remote_button_short_press.
    _deviceAutomationLabel(item) {
        const dom = item.domain || '';
        const L = (this._hass && this._hass.localize) ? this._hass.localize.bind(this._hass) : null;
        const kind = this._dnKind === 'action' ? 'action' : 'trigger';
        let subtype = item.subtype || '';
        if (L && subtype) {
            subtype = L(`component.${dom}.device_automation.${kind}_subtype.${item.subtype}`) || item.subtype;
        }
        let text = '';
        if (L) {
            text = L(`component.${dom}.device_automation.${kind}_type.${item.type}`,
                     { entity_name: '', subtype }) || '';
        }
        if (!text) {
            text = [item.type, item.subtype].filter(Boolean).join(' ').replace(/_/g, ' ');
        }
        return String(text).replace(/\s+/g, ' ').trim();
    }

    // The list is asked for once per device and kept, so redrawing the inspector costs nothing.
    _ensureDeviceAutomations(deviceId, kind) {
        this._devAuto = this._devAuto || {};
        const key = `${kind}:${deviceId}`;
        if (!deviceId || this._devAuto[key] !== undefined) return;
        this._devAuto[key] = null;   // asked for, still on its way
        if (!this._hass || !this._hass.connection) { this._devAuto[key] = []; return; }
        this._hass.connection.sendMessagePromise({
            type: `device_automation/${kind}/list`, device_id: deviceId,
        }).then(list => {
            this._devAuto[key] = Array.isArray(list) ? list : [];
            this._render();
        }).catch(() => { this._devAuto[key] = []; this._render(); });
    }

    // Two entries of the same device can look alike, so the value of an option is the whole node.
    _devSame(a, b) {
        const keys = ['domain', 'type', 'subtype', 'entity_id', 'discovery_id'];
        return keys.every(k => String((a || {})[k] || '') === String((b || {})[k] || ''));
    }

    _deviceFields(el) {
        const out = [];
        const kind = el.deviceNode === 'action' ? 'action' : 'trigger';
        this._dnKind = kind;
        const raw = (el.raw && typeof el.raw === 'object') ? el.raw : {};
        const deviceId = String(el.deviceId || raw.device_id || '');

        out.push(this._picker('device', deviceId, v => {
            // A different device means the old trigger no longer applies, so only the device is kept
            // and the list below is asked for again.
            el.deviceId = v || '';
            el.raw = Object.assign({}, raw, { device_id: v || '' });
            delete el.raw.type; delete el.raw.subtype; delete el.raw.domain;
            el.label = this._devLabelFor(el, null);
            this.core.pushHistory();
            this._render();
        }, { label: 'Device', id: 'device' }));

        this._ensureDeviceAutomations(deviceId, kind);
        const key = `${kind}:${deviceId}`;
        const list = (this._devAuto || {})[key];

        const wrap = document.createElement('div');
        wrap.className = 'fgrp';
        const title = kind === 'action' ? 'Action' : 'Trigger';
        if (!deviceId) {
            wrap.innerHTML = `<label>${title}</label><div style="font-size:12px; color:var(--secondary-text-color, #757575);">Pick a device first.</div>`;
            out.push(wrap);
            return out;
        }
        if (list === null || list === undefined) {
            wrap.innerHTML = `<label>${title}</label><div style="font-size:12px; color:var(--secondary-text-color, #757575);">Asking Home Assistant what this device offers.</div>`;
            out.push(wrap);
            return out;
        }
        if (!list.length) {
            wrap.innerHTML = `<label>${title}</label><div style="font-size:12px; color:var(--secondary-text-color, #757575);">This device offers no ${kind}s.</div>`;
            out.push(wrap);
            return out;
        }

        const current = list.findIndex(item => this._devSame(item, raw));
        const options = list.map((item, i) =>
            `<option value="${i}" ${i === current ? 'selected' : ''}>${this._esc(this._deviceAutomationLabel(item))}</option>`).join('');
        wrap.innerHTML = `<label id="lbl_devauto">${title}</label>
            <select id="inp_devauto">${current < 0 ? '<option value="-1" selected>— not in this list —</option>' : ''}${options}</select>`;
        wrap.querySelector('#inp_devauto').addEventListener('change', (e) => {
            const item = list[Number(e.target.value)];
            if (!item) return;
            // Keep whatever the node carried that the list does not speak for, the trigger id and
            // the for and the continue_on_error, and lay the chosen one over it.
            const keep = {};
            ['id', 'for', 'continue_on_error', 'enabled', 'alias', 'variables'].forEach(k => {
                if (raw[k] !== undefined) keep[k] = raw[k];
            });
            el.raw = Object.assign({ trigger: 'device' }, item, { device_id: deviceId }, keep);
            if (kind === 'action') { delete el.raw.trigger; el.raw.device_id = deviceId; }
            el.deviceId = deviceId;
            el.label = this._devLabelFor(el, item);
            // [FIXED v3.31.0] Choosing from the list used to leave the block looking exactly as it
            // was. The symbol follows the kind of action, and the second line follows the node, so
            // both are set here rather than left to a redraw that had nothing new to read.
            el.service = '';
            if (kind === 'action' && String(el.type || '').startsWith('coil')) {
                const type = String(item.type || '');
                el.type = type === 'toggle' ? 'coil_t'
                        : type === 'turn_off' ? 'coil_r'
                        : type === 'press' ? 'coil'
                        : 'coil_s';
            }
            this.core.pushHistory();
            this._render();
        });
        out.push(wrap);

        // What the node really says, under the two fields, the same as for an entity.
        const note = document.createElement('div');
        note.className = 'fgrp';
        const bits = [raw.domain, raw.type, raw.subtype].filter(Boolean).join(' · ');
        note.innerHTML = bits
            ? `<div style="font-size:12px; color:var(--secondary-text-color, #616161); margin-top:-10px; font-family:monospace; word-break:break-all;">${this._esc(bits)}</div>`
            : '';
        out.push(note);
        return out;
    }

    // The two lines drawn on the block: the device on top, what it does underneath.
    _devLabelFor(el, item) {
        return this._devLabelForImpl(el, item);
    }

    _devLabelForImpl(el, item) {
        const raw = (el.raw && typeof el.raw === 'object') ? el.raw : {};
        const dev = this.core.deviceName(String(el.deviceId || raw.device_id || ''), this._hass) || 'device';
        const slug = String(dev).toLowerCase().trim().replace(/[^a-z0-9_]+/g, '_').replace(/^_+|_+$/g, '') || 'device';
        const what = (item && (item.subtype || item.type)) || raw.subtype || raw.type || '';
        return what ? `${slug}.${what}` : slug;
    }

    // [ADDED v3.28.0] Right clicking the name of a block offers to rename what it points at. The
    // name lives in the entity registry of Home Assistant, so renaming here is the same rename as
    // renaming it anywhere else, and every card and every automation follows.
    _ctxMenuHtml() {
        if (!this._ctx) return '';
        const eid = this._ctx.entityId;
        const name = this.core.friendlyName(eid, this._hass) || '';
        return `<div class="ctx-menu" id="ctxMenu" style="left:${this._ctx.x}px; top:${this._ctx.y}px;">
            <div class="ctx-head">${this._esc(eid)}</div>
            <button class="ctx-item" id="ctxChange">◈&nbsp; Change the entity</button>
            <button class="ctx-item" id="ctxRename">✎&nbsp; Rename${name ? ` “${this._esc(name)}”` : ''}</button>
            <button class="ctx-item" id="ctxMoreInfo">☰&nbsp; Open in Home Assistant</button>
            <button class="ctx-item" id="ctxCopy">⧉&nbsp; Copy the entity id</button>
        </div>`;
    }

    // [CHANGED v3.86.0] Two ways to rename - the user's request (2026-11-04): in Home Assistant, when its entity registry
    // has the entity, or in LIBI only - Home Assistant is not changed, and LIBI shows the name wherever it shows the entity.
    // An entity Home Assistant cannot rename (no unique ID) has the second one only. From a pin, LIBI only comes first:
    // a pin shows the entity id, or its name in LIBI.
    _renameCanHa() {
        const h = this._hass;
        return !!(h && h.entities && h.entities[this._renameFor]);
    }

    _renameInHaFirst() {
        return this._renameCanHa() && this._renameFrom !== 'pin';
    }

    _renameDialogHtml() {
        const eid = this._renameFor;
        const canHa = this._renameCanHa();
        const haFirst = this._renameInHaFirst();
        const local = this.core.localName(eid);
        const note = canHa
            ? `<b>Rename in Home Assistant</b> changes the name Home Assistant shows for this entity everywhere; the entity id does not change, so nothing that points at it breaks. <b>In LIBI only</b> leaves Home Assistant as it is and shows your name wherever LIBI shows this entity${this._renameFrom === 'pin' ? ' - a pin shows the entity id, or the name it has in LIBI' : ''}.`
            : 'Home Assistant cannot rename this entity: it has no unique ID (it was written in YAML, for example). The name is kept in LIBI only and shown wherever LIBI shows this entity; Home Assistant keeps its own.';
        return `<div class="modal-overlay" id="modalOverlay"><div class="modal" style="width:460px;">
            <h2 class="modal-title">Rename</h2>
            <p style="font-size:12px; color:var(--secondary-text-color, #757575); margin:0 0 10px 0; font-family:monospace; word-break:break-all;">${this._esc(eid)}</p>
            <div class="fgrp"><label>Name</label>
                <input type="text" id="renameInput" value="${this._esc(this._renameTo)}" dir="auto" maxlength="100" placeholder="New name" /></div>
            <p class="rename-note" style="font-size:12px; color:var(--secondary-text-color, #757575); margin:0;">${note}</p>
            ${local ? `<p class="rename-local" style="font-size:12px; margin:10px 0 0 0;">In LIBI it is called <b dir="auto">${this._esc(local)}</b>. <button class="ha-text-btn" id="renameLocalClear">Remove the LIBI name</button></p>` : ''}
            <div class="modal-actions" style="flex-wrap:wrap;">
                <button class="btn btn-ghost" id="closeModalBtn">Cancel</button>
                <button class="btn${haFirst ? ' btn-ghost' : ''}" id="renameLocal">In LIBI only</button>
                ${canHa ? `<button class="btn${haFirst ? '' : ' btn-ghost'}" id="renameOk">Rename in Home Assistant</button>` : ''}
            </div>
        </div></div>`;
    }

    async _doRename() {
        const eid = this._renameFor;
        const name = String(this._renameTo || '').trim();
        if (!eid) return;
        try {
            await this._hass.connection.sendMessagePromise({
                type: 'config/entity_registry/update', entity_id: eid, name: name || null,
            });
            this._modal = null;
            this._renameFor = '';
            // [FIXED v3.28.1] The registry took the name, but the state object the panel holds is the
            // one Home Assistant handed over before the change. Drawing now would show the old name
            // until something else forced a redraw, which is why it needed a page refresh. The new
            // name is shown straight away and the drawing is repeated when the real one arrives.
            this.core.nameOverrides = this.core.nameOverrides || {};
            this.core.nameOverrides[eid] = name;
            // [ADDED v3.86.0] Renamed in Home Assistant, the name given in LIBI goes: it would hide the new one.
            if (this.core.localName(eid)) await this._setLocalName(eid, '');
            this._render();
            this._settleRename(eid, name);
        } catch (err) {
            // [CHANGED v3.86.0] What Home Assistant cannot rename is named in LIBI only - the user's rule (2026-11-04).
            const why = err && err.message ? err.message : String(err);
            if (name && await this._setLocalName(eid, name)) {
                this._modal = null;
                this._renameFor = '';
                this._render();
                alert(`Home Assistant could not rename it (${why}), so the name is kept in LIBI only: LIBI shows it wherever it shows this entity, and Home Assistant keeps its own.`);
                return;
            }
            alert('Could not rename it: ' + why);
        }
    }

    // [ADDED v3.86.0] The names given in LIBI only, from config/libi/local_names.json. Without them LIBI shows Home
    // Assistant's names, as before.
    async _loadLocalNames() {
        try {
            const res = await this._hass.connection.sendMessagePromise({ type: 'libi/local_names' });
            const names = res && res.names;
            this.core.localNames = names && typeof names === 'object' && !Array.isArray(names) ? names : {};
        } catch (err) {
            console.warn('LIBI could not read the names given in LIBI', err);
            this.core.localNames = {};
        }
    }

    // [ADDED v3.86.0] Gives an entity a name in LIBI only, or takes it away (''). True when LIBI kept it.
    // [CHANGED v3.87.0] A phone's name is kept under its action (core.nameKey), whichever of its two ids was renamed, and
    // one kept under its notify entity goes: the phone has one name.
    async _setLocalName(entityId, name) {
        const key = this.core.nameKey(entityId);
        const phone = this.core.phoneOf(entityId);
        const other = phone && phone.entity_id !== key
            && Object.prototype.hasOwnProperty.call(this.core.localNames || {}, phone.entity_id) ? phone.entity_id : '';
        try {
            let res = await this._hass.connection.sendMessagePromise({ type: 'libi/local_name_set', entity_id: key, name });
            if (other) res = await this._hass.connection.sendMessagePromise({ type: 'libi/local_name_set', entity_id: other, name: '' });
            const names = res && res.names;
            this.core.localNames = names && typeof names === 'object' && !Array.isArray(names) ? names : {};
            return true;
        } catch (err) {
            alert('Could not keep the name in LIBI: ' + (this._staleBackend(err) || (err && err.message ? err.message : err)));
            return false;
        }
    }

    // [ADDED v3.87.0] The phones the Companion app registered and the action that sends to each (libi/phones), for the
    // MOVE NOTIFY / TTS block and for the phones' names. Without them - a Home Assistant still running an older LIBI, an
    // error - the block offers Home Assistant's notify actions by their ids, as they are.
    async _loadPhones() {
        try {
            const res = await this._hass.connection.sendMessagePromise({ type: 'libi/phones' });
            const phones = res && Array.isArray(res.phones) ? res.phones : [];
            this.core.phones = phones.filter(p => p && typeof p.entity_id === 'string' && typeof p.service === 'string');
        } catch (err) {
            console.warn('LIBI could not read the phones', err);
            this.core.phones = [];
        }
    }

    // [ADDED v3.88.0] LIBI Global: the recipients of messages, each a script of Home Assistant's that sends to the phones
    // ticked for it (libi/global), with the phones. Not read - an error, a Home Assistant still running an older LIBI -
    // and a MOVE NOTIFY / TTS block lists no recipient and says nothing of one it sends to.
    async _loadGlobal() {
        try {
            this._applyGlobal(await this._hass.connection.sendMessagePromise({ type: 'libi/global' }));
        } catch (err) {
            console.warn('LIBI could not read LIBI Global', err);
            this.core.recipients = [];
            Object.assign(this._global, { loaded: false, ok: false,
                errors: [this._staleBackend(err) || (err && err.message ? err.message : String(err))] });
        }
    }

    // [ADDED v3.88.0] What libi/global (and libi/global_done) answered. A file that cannot be read lists nothing: ok false,
    // and why.
    _applyGlobal(res) {
        const ok = !!(res && res.ok);
        const list = res && Array.isArray(res.recipients) ? res.recipients : [];
        this.core.recipients = list.filter(r => r && typeof r.key === 'string' && typeof r.action === 'string'
            && typeof r.name === 'string' && Array.isArray(r.phones));
        if (res && Array.isArray(res.phones)) {
            this.core.phones = res.phones.filter(p => p && typeof p.entity_id === 'string' && typeof p.service === 'string');
        }
        Object.assign(this._global, { loaded: ok, ok,
            errors: !ok && res && Array.isArray(res.errors) ? res.errors.map(String) : [] });
    }

    // [ADDED v3.88.0] A recipient as it is being changed: its draft, else as Home Assistant holds it.
    _globalDraft(key) {
        const d = this._global.drafts[key];
        if (d) return d;
        const r = (this.core.recipients || []).find(x => x.key === key);
        return r ? { name: r.name, phones: [...r.phones] } : { name: '', phones: [] };
    }

    // [ADDED v3.88.0] The Global tab, read again as it opens: another page, or Home Assistant's script editor, may have
    // changed it since. [CHANGED v3.88.1] key: straight to that global variable's editor (Open Global in Send to).
    async _openGlobal(key = '') {
        this._varsTab = 'global';
        this._varsOpen = true;
        if (key) Object.assign(this._global, { editing: key, said: {} });
        this._saveVars();
        this._render();
        await this._loadGlobal();
        this._render();
    }

    // [ADDED v3.88.0] Whether a recipient can be saved now: a name, a phone, and something to save - a change, a new one,
    // or one changed outside LIBI, written again.
    _globalCanSave(key) {
        if (this._global.busy || !this._global.ok) return false;
        const d = this._globalDraft(key);
        const r = (this.core.recipients || []).find(x => x.key === key);
        return !!d.name.trim() && d.phones.length > 0 && (!r || r.edited || this._globalDirty(key));
    }

    // [ADDED v3.88.0] Whether a recipient has a change not saved yet.
    _globalDirty(key) {
        const d = this._global.drafts[key];
        if (!d) return false;
        const r = (this.core.recipients || []).find(x => x.key === key);
        if (!r) return true;
        return d.name.trim() !== r.name || [...d.phones].sort().join('|') !== [...r.phones].sort().join('|');
    }

    // [ADDED v3.88.0] A change to LIBI Global, made as SAVE & COMPILE makes one: libi/global_plan builds and checks the
    // recipient's script and writes nothing; Home Assistant's config API saves it (POST) or deletes it (DELETE), as its own
    // script editor does; libi/global_done reads scripts.yaml back and waits for the reload. The page gets LIBI Global as
    // it is then. Returns { ok, text, key }: saved and reloaded, or why not.
    async _globalRun(msg) {
        const ws = (m) => this._hass.connection.sendMessagePromise(m);
        const said = (err) => this._staleBackend(err) || (err && err.message ? err.message : String(err));
        let plan;
        try {
            plan = (await ws({ type: 'libi/global_plan', ...msg })) || {};
        } catch (err) {
            return { ok: false, text: 'Not saved: ' + said(err) };
        }
        if (!plan.ok) return { ok: false, text: (plan.errors || []).join(' ') || 'Not saved.' };
        if (plan.unchanged) return { ok: true, text: 'Nothing changed, so nothing was sent.', key: plan.key };
        const op = plan.op || {};
        const { failure } = await this._configApiSend([{ ...op, domain: 'script' }]);
        let done;
        try {
            done = (await ws({ type: 'libi/global_done', key: op.key, op: op.op, label: op.label || '', failure,
                stamp: plan.stamp || '' })) || {};
        } catch (err) {
            return { ok: false, text: 'Sent to Home Assistant, but LIBI could not read it back: ' + said(err), key: op.key };
        }
        this._applyGlobal(done);
        return { ok: done.status === 'ok' && !!done.saved, text: done.message || 'Not saved.', key: op.key };
    }

    // [CHANGED v3.88.1] Saved, the editor closes and the table says so - the user, 2026-11-05: "I expect the window to
    // disappear" and the table to show. Not saved, it stays open and says why.
    async _globalSave(key) {
        const g = this._global;
        if (g.busy) return;
        const known = (this.core.recipients || []).some(x => x.key === key);
        const d = this._globalDraft(key);
        g.busy = key;
        g.said = { [key]: { ok: true, text: 'Saving…' } };
        this._render();
        const res = await this._globalRun({ key: known ? key : '', name: d.name, phones: d.phones, remove: false });
        g.busy = '';
        if (res.ok) {
            delete g.drafts[key];
            g.editing = '';
            g.said = { '+table': { ok: true, text: res.text } };
            // [ADDED v3.89.0] The user (2026-11-05): after the save, ask to replace the phone with it wherever an
            // automation still sends straight to that phone.
            if (this._globalMoveItems(res.key).some(i => i.can)) {
                this._openGlobalMove(res.key);
                return;
            }
        } else {
            g.said = { [key]: { ok: false, text: res.text } };
        }
        this._render();
    }

    // [ADDED v3.89.0] The name of a device a global variable sends to: its name in LIBI, else in Home Assistant, else the
    // phone's own; the action when it is no phone of the list.
    _globalDeviceName(service) {
        const p = (this.core.phones || []).find(x => !x.shared && x.service === service);
        return this.core.localName(service) || (p ? (this.core.haName(p.entity_id, this._hass) || p.name) : '') || service;
    }

    // [ADDED v3.89.0] Every element of a NET, those in parallel branches and in a repeat too.
    _eachElement(net, fn) {
        const walk = (els) => (els || []).forEach(el => {
            fn(el);
            if (el.type === 'parallel') (el.branches || []).forEach(walk);
            if (el.type === 'repeat') walk(el.sequence);
        });
        ((net && net.rungs) || []).forEach(r => walk(r.elements));
    }

    // [ADDED v3.89.0] Where a global variable can take over from its phone - the user's request (2026-11-05): replace the
    // phone with it in every automation that still sends straight to it, once they confirm. Each item: a NET on this page
    // (changed on the page, then SAVE & COMPILE), or an automation or script of Home Assistant's (libi/global_move_plan),
    // with how many steps change (moves) and stay (stays); can: it can be ticked, else why not. Only a global variable of
    // one phone takes over: an automation that sends to one of several phones would then send to all of them.
    _globalMoveItems(key) {
        const r = (this.core.recipients || []).find(x => x.key === key);
        if (!r) return [];
        const phone = !r.move_why && r.phones.length === 1 ? r.phones[0] : '';
        const slug = this._project ? this._project.slug : 'default';
        const dirty = this._hasUnsavedChanges();
        const items = [];
        const onPage = new Set();
        for (const net of (phone ? this.core.nets || [] : [])) {
            let moves = 0;
            this._eachElement(net, el => { if (this._sendsMessage(el) && el.target === phone) moves += 1; });
            if (!moves) continue;
            onPage.add(String(net.ha_id || net.id));
            const why = dirty ? 'this page has changes that are not saved - save them (SAVE & COMPILE) or undo them first' : '';
            items.push({ id: `net:${net.id}`, kind: 'page', net: net.id, name: `NET "${net.name}" on this page`, what: 'NET',
                moves, stays: 0, why, can: !why });
        }
        for (const d of r.direct || []) {
            // One of this project's is changed on its NET above. A script's key is its NET's name as a slug, which is
            // only the backend's to make: a script of this project is left to its NET.
            const mine = d.owner && d.owner.slug === slug;
            if (mine && (onPage.has(String(d.key)) || d.domain !== 'automation')) continue;
            const why = mine ? `a NET of this project draws it - pick ${r.name} in Send to of its MOVE block` : (d.why || '');
            items.push({ id: `${d.domain}:${d.key}`, kind: 'ha', domain: d.domain, key: d.key, name: d.name, what: d.domain,
                moves: d.moves || 0, stays: d.stays || 0, why, can: !why && (d.moves || 0) > 0 });
        }
        return items;
    }

    _openGlobalMove(key) {
        this._globalMove = { key, picked: this._globalMoveItems(key).filter(i => i.can).map(i => i.id), busy: false, said: null };
        this._modal = 'global_move';
        this._render();
    }

    _closeGlobalMove() {
        if (this._globalMove && this._globalMove.busy) return;
        this._globalMove = null;
        this._modal = null;
        this._render();
    }

    // [ADDED v3.89.0] The ones ticked, replaced: Home Assistant's first - libi/global_move_plan changes only the steps that
    // send to the phone and writes nothing, its config API saves each, libi/global_move_done reads them back and waits for
    // each reload - then the NETs on this page, their MOVE blocks sending to the global variable, saved with SAVE &
    // COMPILE. Done, the dialog closes and the table says what changed; otherwise it stays open and says why.
    async _globalMoveRun() {
        const m = this._globalMove;
        if (!m || m.busy) return;
        const r = (this.core.recipients || []).find(x => x.key === m.key);
        const items = this._globalMoveItems(m.key).filter(i => i.can && m.picked.includes(i.id));
        if (!r || !items.length) return;
        const page = items.filter(i => i.kind === 'page');
        const ha = items.filter(i => i.kind === 'ha');
        if (page.length && this._hasUnsavedChanges(true)) {
            m.said = { ok: false, text: 'This page has changes that are not saved: save them (SAVE & COMPILE) or undo them first. Nothing was replaced.' };
            this._render();
            return;
        }
        const phone = r.phones[0];
        m.busy = true;
        m.said = { ok: true, text: 'Replacing…' };
        this._render();
        const texts = [];
        let ok = true;
        if (ha.length) {
            const res = await this._globalMoveSend(m.key, ha);
            texts.push(res.text);
            ok = res.ok;
        }
        if (ok && page.length) {
            for (const i of page) {
                this._eachElement(this.core.nets.find(n => n.id === i.net), el => {
                    if (this._sendsMessage(el) && el.target === phone) el.target = r.action;
                });
            }
            this.core.pushHistory();
            const s = await this._saveProject();
            ok = !!s.complete && s.status === 'ok';
            texts.push(ok ? `This page is saved: ${page.map(i => i.name).join(', ')} send${page.length === 1 ? 's' : ''} through ${r.name} now.`
                : `${page.map(i => i.name).join(', ')} send${page.length === 1 ? 's' : ''} to ${r.name} on this page, but: ${this._saveResultText(s)}`);
            await this._loadGlobal();
        }
        m.busy = false;
        if (ok) {
            this._globalMove = null;
            this._modal = null;
            this._global.said = { '+table': { ok: true, text: texts.join(' ') } };
        } else {
            m.said = { ok: false, text: texts.join(' ') };
            m.picked = m.picked.filter(id => this._globalMoveItems(m.key).some(i => i.can && i.id === id));
        }
        this._render();
    }

    // [ADDED v3.89.0] The automations and scripts of Home Assistant's: plan, config API, done. Returns { ok, text }.
    async _globalMoveSend(key, items) {
        const ws = (msg) => this._hass.connection.sendMessagePromise(msg);
        const said = (err) => this._staleBackend(err) || (err && err.message ? err.message : String(err));
        const slug = this._project ? this._project.slug : 'default';
        let plan;
        try {
            plan = (await ws({ type: 'libi/global_move_plan', key, slug, entries: items.map(i => ({ domain: i.domain, key: i.key })) })) || {};
        } catch (err) {
            return { ok: false, text: 'Nothing was replaced: ' + said(err) };
        }
        if (!plan.ok) return { ok: false, text: (plan.errors || []).join(' ') || 'Nothing was replaced.' };
        const { done, failure } = await this._configApiSend(plan.ops || []);
        let res;
        try {
            res = (await ws({ type: 'libi/global_move_done', key, done, failure, stamp: plan.stamp || '' })) || {};
        } catch (err) {
            return { ok: false, text: 'Sent to Home Assistant, but LIBI could not read it back: ' + said(err) };
        }
        this._applyGlobal(res);
        return { ok: res.status === 'ok', text: res.message || 'Nothing was replaced.' };
    }

    // [ADDED v3.89.0] The question, asked after a save and from the table: the ones that send straight to the phone, each to
    // tick, and those that are not replaced, with why. Every name from the user's files is escaped.
    _globalMoveDialogHtml() {
        const m = this._globalMove;
        const r = m && (this.core.recipients || []).find(x => x.key === m.key);
        if (!r) return '';
        const esc = (v) => this._esc(v === undefined || v === null ? '' : v);
        const items = this._globalMoveItems(m.key);
        const can = items.filter(i => i.can);
        const stay = items.filter(i => !i.can);
        const picked = can.filter(i => m.picked.includes(i.id)).length;
        const phone = r.phones.length === 1 ? this._globalDeviceName(r.phones[0]) : r.phones.map(s => this._globalDeviceName(s)).join(', ');
        const steps = (n) => `${n} step${n === 1 ? '' : 's'}`;
        const row = (i) => `<label class="gm-item">
                <input type="checkbox" class="gm-tick" data-id="${esc(i.id)}" ${m.picked.includes(i.id) ? 'checked' : ''} ${m.busy ? 'disabled' : ''} />
                <span class="nm" dir="auto">${esc(i.name)}</span>
                <span class="what">${esc(i.what)} · ${steps(i.moves)}${i.stays ? ` · ${steps(i.stays)} stay as they are` : ''}</span></label>`;
        const off = (i) => `<div class="gm-item off"><span class="nm" dir="auto">${esc(i.name)}</span><span class="why" dir="auto">${esc(i.why || 'nothing in it can be replaced')}</span></div>`;
        const intro = r.move_why
            ? `Nothing can be sent through ${esc(r.name)}: ${esc(r.move_why)}.`
            : can.length
                ? `These still send straight to ${esc(phone)}, not through ${esc(r.name)}. Replace ${esc(phone)} with ${esc(r.name)} in the ones ticked? Only that changes in them, and Home Assistant saves each one. From then on, a phone replaced in ${esc(r.name)} reaches them too.`
                : `Nothing sends straight to ${esc(phone)} that can be replaced now.`;
        return `<div class="modal-overlay" id="modalOverlay"><div class="modal gm-modal">
            <h2 class="modal-title" dir="auto">Send through ${esc(r.name)}?</h2>
            <p class="gm-text" dir="auto">${intro}</p>
            ${can.length || stay.length ? `<div class="gm-list">${can.map(row).join('')}
                ${stay.length ? `<div class="gm-sec">Not replaced</div>${stay.map(off).join('')}` : ''}</div>` : ''}
            ${m.said ? `<div class="gm-said ${m.said.ok ? 'ok' : 'err'}" dir="auto">${esc(m.said.text)}</div>` : ''}
            <div class="modal-actions">
                <button class="btn btn-ghost" id="gmCancel" ${m.busy ? 'disabled' : ''}>Not now</button>
                ${can.length ? `<button class="btn btn-primary" id="gmGo" ${picked && !m.busy ? '' : 'disabled'}>Replace in ${picked}</button>` : ''}
            </div>
        </div></div>`;
    }

    async _globalDelete(key) {
        const g = this._global;
        const r = (this.core.recipients || []).find(x => x.key === key);
        if (!r || g.busy) return;
        // [CHANGED v3.88.1] What it says goes where the user is: the editor of it, or the table.
        const where = g.editing === key ? key : '+table';
        // The backend checks Home Assistant's files and every project as saved; the NETs on this page may hold more.
        const whole = new RegExp(r.action.replace(/\./g, '\\.') + '(?![a-z0-9_])');
        const here = (this.core.nets || []).filter(n => whole.test(JSON.stringify(n))).map(n => `NET "${n.name}"`);
        if (here.length) {
            g.said = { [where]: { ok: false, text: `${r.name} is not deleted: ${here.join(', ')} on this page sends to it. Send it to another recipient or a phone first.` } };
            this._render();
            return;
        }
        if (!window.confirm(`Delete the global variable ${r.name}? Its script, ${r.action}, is deleted from Home Assistant.`)) return;
        g.busy = key;
        g.said = { [where]: { ok: true, text: 'Deleting…' } };
        this._render();
        const res = await this._globalRun({ key, remove: true });
        g.busy = '';
        const gone = !(this.core.recipients || []).some(x => x.key === key);
        if (gone) {
            delete g.drafts[key];
            if (g.editing === key) g.editing = '';
        }
        g.said = { [gone ? '+table' : where]: { ok: res.ok, text: res.text } };
        this._render();
    }

    // [ADDED v3.88.0] The Global tab of the bar. [CHANGED v3.88.1] The user's request (2026-11-05): a table of the global
    // variables, as the Variables tab is one, and the editor of one of them only while it is being made or changed - a
    // save closes it. Every value from the user's files and Home Assistant is escaped.
    _globalViewHtml() {
        const g = this._global;
        const list = this.core.recipients || [];
        const r = list.find(x => x.key === g.editing) || null;
        if (r || (g.editing === '+new' && g.drafts['+new'])) return this._globalEditorHtml(g.editing, r);
        return this._globalTableHtml();
    }

    // [ADDED v3.88.1] Each global variable on a row: its name, its type, the devices it sends to by name and their ids,
    // and how many automations and scripts send to it. A row opens it; 🗑 deletes it.
    _globalTableHtml() {
        const g = this._global;
        const esc = (v) => this._esc(v === undefined || v === null ? '' : v);
        const deviceName = (service) => this._globalDeviceName(service);
        // [ADDED v3.89.0] A line for each one that automations still pass by, sending straight to its phone.
        const moves = (this.core.recipients || []).map(r => {
            const n = this._globalMoveItems(r.key).filter(i => i.can).length;
            return n ? `<div class="glob-moves"><span dir="auto">${n} ${n === 1 ? 'automation or script still sends' : 'automations and scripts still send'} straight to ${esc(deviceName(r.phones[0]))}, not through <b>${esc(r.name)}</b>.</span>
                <button class="btn glob-move-open" data-key="${esc(r.key)}" ${g.busy || !g.ok ? 'disabled' : ''}>Replace…</button></div>` : '';
        }).join('');
        const rows = (this.core.recipients || []).map(r => {
            const missing = r.missing || [];
            const lines = (text) => r.phones.map(s => `<div class="${missing.includes(s) ? 'gone' : ''}" title="${esc(s)}">${esc(text(s))}</div>`).join('') || '—';
            const flags = (r.edited ? '<span class="glob-flag warn" title="Changed outside LIBI, in Home Assistant">edited</span>' : '')
                + (missing.length ? '<span class="glob-flag err" title="A device it sends to is no longer in Home Assistant: nothing reaches it">device gone</span>' : '');
            return `<tr class="glob-row" data-key="${esc(r.key)}" tabindex="0" title="${esc(r.action)} - click to change it">
                <td class="c-name" dir="auto">${esc(r.name)}${flags}</td>
                <td><span class="type-tag type-RCPT" title="A recipient: the phones a MOVE NOTIFY / TTS message goes to">RECIPIENT</span></td>
                <td class="glob-dev" dir="auto">${lines(deviceName)}</td>
                <td class="c-eid glob-dev">${lines(s => s)}</td>
                <td class="glob-used" title="How many automations and scripts send to it">${(r.used_by || []).length}</td>
                <td class="c-act"><button class="vars-del glob-row-del" data-key="${esc(r.key)}" title="Delete ${esc(r.name)}" ${g.busy || !g.ok ? 'disabled' : ''}>🗑</button></td>
            </tr>`;
        }).join('');
        const said = g.said['+table'];
        return `<div class="glob-view">
            <div class="glob-top">
                <span class="glob-title">Global variables</span>
                <span class="glob-note">One place for every project. A RECIPIENT is the phones a MOVE NOTIFY / TTS message goes to: pick it in the block's Send to, and when a phone is replaced, change it here once. Click a row to change it.</span>
            </div>
            ${g.ok ? '' : `<div class="glob-err">LIBI Global could not be read, so nothing can be changed here: ${esc(g.errors.join('; '))}</div>`}
            ${said ? `<div class="glob-said ${said.ok ? 'ok' : 'err'}" dir="auto">${esc(said.text)}</div>` : ''}
            ${moves}
            <div class="glob-scroll">${rows ? `<table class="vars-table glob-table"><thead><tr>
                    <th>Name</th><th style="width:100px;">Type</th><th>Device</th><th class="c-eid">ID</th>
                    <th class="glob-used" style="width:70px;" title="How many automations and scripts send to it">Used by</th><th style="width:48px;"></th>
                </tr></thead><tbody>${rows}</tbody></table>` : (g.ok ? '<div class="vars-empty">No global variable yet.</div>' : '')}</div>
            <div class="glob-new"><button class="btn" id="globAdd" ${g.ok && !g.busy ? '' : 'disabled'}>＋ New global variable</button></div>
        </div>`;
    }

    // [ADDED v3.88.1] One global variable being made or changed: its name, the phones to tick, who sends to it and who
    // still sends straight to its phones. Save, Cancel or Delete closes it. (The card of v3.88.0, one at a time.)
    _globalEditorHtml(key, r) {
        const g = this._global;
        const esc = (v) => this._esc(v === undefined || v === null ? '' : v);
        const phones = this.core.phones || [];
        const names = (list) => list.map(u => `<b dir="auto">${esc(u.name)}</b>`).join(', ');
        const d = this._globalDraft(key);
        const busy = g.busy === key;
        const ticked = new Set(d.phones);
        const missing = new Set((r && r.missing) || []);
        const listed = new Set(phones.filter(p => !p.shared).map(p => p.service));
        const chips = phones.map(p => {
            const on = !p.shared && ticked.has(p.service);
            const who = [p.owner, p.shared ? 'shares its name with another phone' : '', p.speaks ? '' : 'does not read aloud']
                .filter(Boolean).join(' · ');
            return `<label class="glob-phone${on ? ' on' : ''}${p.shared ? ' off' : ''}" title="${esc(p.shared ? 'Two phones are registered under this name in the Companion app: their one action reaches only one of them. Give one another name in the app.' : p.service)}">
                <input type="checkbox" class="glob-tick" data-key="${esc(key)}" data-svc="${esc(p.shared ? '' : p.service)}" ${on ? 'checked' : ''} ${p.shared || busy ? 'disabled' : ''} />
                <span class="nm" dir="auto">${esc(this.core.localName(p.service) || this.core.haName(p.entity_id, this._hass) || p.name)}</span>${who ? `<span class="who" dir="auto">${esc(who)}</span>` : ''}</label>`;
        }).join('');
        // A phone it sends to that is not in the list: gone from the Companion app, or ticked in Home Assistant.
        const gone = d.phones.filter(s => !listed.has(s)).map(s => `<label class="glob-phone on gone" title="${esc(s)}">
                <input type="checkbox" class="glob-tick" data-key="${esc(key)}" data-svc="${esc(s)}" checked ${busy ? 'disabled' : ''} />
                <span class="nm">${esc(s)}</span><span class="who">${missing.has(s) ? 'no longer in Home Assistant' : 'not a phone of the Companion app'}</span></label>`).join('');
        const notes = [];
        if (r && r.edited) notes.push('<div class="glob-warn">Changed outside LIBI, in Home Assistant. Save writes it again as LIBI writes it, with the phones ticked here.</div>');
        if (missing.size) notes.push('<div class="glob-err">A phone it sends to is no longer in Home Assistant: nothing reaches it. Untick it, tick the new phone, Save.</div>');
        const uses = !r ? '' : ((r.used_by || []).length
            ? `<div class="glob-uses">Sent to by ${(r.used_by || []).length}: ${names(r.used_by)}</div>`
            : '<div class="glob-uses">Nothing sends to it yet: pick it in Send to of a MOVE NOTIFY / TTS block.</div>');
        // [CHANGED v3.89.0] With Replace…, when the phone can be replaced with it in them now (the question after a save).
        const movable = r && !this._globalDirty(key) && this._globalMoveItems(key).some(i => i.can);
        const direct = r && (r.direct || []).length
            ? `<div class="glob-uses">Still sending straight to its phones, not through ${esc(r.name)}: ${names(r.direct)}. ${movable
                ? `<button class="btn glob-move-open" data-key="${esc(key)}" ${busy ? 'disabled' : ''}>Replace…</button>`
                : `Pick ${esc(r.name)} in their Send to, and a phone replaced here reaches them too.`}</div>` : '';
        const said = g.said[key];
        return `<div class="glob-view">
            <div class="glob-top">
                <span class="glob-title">Global variables ▸ <span dir="auto">${r ? esc(r.name) : 'New'}</span></span>
            </div>
            ${g.ok ? '' : `<div class="glob-err">LIBI Global could not be read, so nothing can be changed here: ${esc(g.errors.join('; '))}</div>`}
            <div class="glob-edit">
                <div class="glob-card${this._globalDirty(key) || !r ? ' dirty' : ''}" data-key="${esc(key)}">
                    <div class="glob-head">
                        <input type="text" class="glob-name" data-key="${esc(key)}" value="${esc(d.name)}" placeholder="Name, for example Guy or Everyone" maxlength="60" dir="auto" ${busy ? 'disabled' : ''} />
                        ${r ? `<span class="glob-id" title="The script in Home Assistant that sends to these phones">${esc(r.action)}</span>` : '<span class="glob-id">new - not saved yet</span>'}
                    </div>
                    ${notes.join('')}
                    <div class="glob-phones">${chips}${gone}${phones.length ? '' : '<span class="glob-note">No phone with the Home Assistant Companion app is registered.</span>'}</div>
                    ${uses}${direct}
                    <div class="glob-foot">
                        <button class="btn btn-primary glob-save" data-key="${esc(key)}" ${this._globalCanSave(key) ? '' : 'disabled'}>Save</button>
                        <button class="btn btn-ghost glob-cancel" data-key="${esc(key)}" ${busy ? 'disabled' : ''}>Cancel</button>
                        ${r ? `<button class="btn btn-ghost glob-del" data-key="${esc(key)}" ${busy ? 'disabled' : ''}>Delete</button>` : ''}
                        ${said ? `<span class="glob-said ${said.ok ? 'ok' : 'err'}" dir="auto">${esc(said.text)}</span>` : ''}
                    </div>
                </div>
            </div>
        </div>`;
    }

    async _doRenameLocal() {
        const eid = this._renameFor;
        if (!eid) return;
        if (!(await this._setLocalName(eid, String(this._renameTo || '').trim()))) return;
        this._modal = null;
        this._renameFor = '';
        this._render();
    }

    // Waits for Home Assistant to push the renamed entity, then draws once more with the real value
    // and lets the override go. It gives up after a couple of seconds so it can never spin.
    _settleRename(entityId, expected) {
        let tries = 0;
        const done = () => {
            if (this.core.nameOverrides) delete this.core.nameOverrides[entityId];
            this._render();
        };
        const tick = () => {
            const st = this._hass && this._hass.states && this._hass.states[entityId];
            const live = (st && st.attributes && st.attributes.friendly_name) ? String(st.attributes.friendly_name) : '';
            const arrived = expected ? live === expected : !!live;
            if (arrived || ++tries > 14) { done(); return; }
            setTimeout(tick, 150);
        };
        setTimeout(tick, 150);
    }

    // [ADDED v3.9.0] The entity id of the element, written under the picker that hides it.
    _idNote(el) {
        const wrap = document.createElement('div');
        wrap.className = 'fgrp';
        const id = String(el.label || '').replace(/\s*\+\d+$/, '').trim();
        const name = this.core.friendlyName(id, this._hass);
        wrap.innerHTML = id
            ? `<div style="font-size:12px; color:var(--secondary-text-color, #616161); margin-top:-10px; font-family:monospace; word-break:break-all;">`
              + `${this._esc(id)}${name ? ` <span style="font-family:inherit; color:var(--secondary-text-color, #9e9e9e);">&nbsp;·&nbsp;${this._esc(name)}</span>` : ''}</div>`
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
            + `<ul style="margin:0; padding-inline-start:18px; font-size:12px; color:var(--secondary-text-color, #616161); max-height:190px; overflow:auto;" dir="auto">${rows}</ul>`;
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
        wrap.innerHTML = `<label id="lbl_target_spec">Targets &nbsp;<span style="font-weight:600; color:var(--secondary-text-color, #757575);">`
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

    // [ADDED v3.87.0] A block whose target is where a message goes: MOVE NOTIFY, TTS or both, and the old notify block.
    _sendsMessage(el) {
        return !!el && (el.type === 'notify' || (el.type === 'move' && (el.mode || 'value') !== 'value'));
    }

    // [ADDED v3.87.0] Home Assistant's notify actions other than the phones' - those are listed by phone - and other than
    // notify.send_message, which needs the notify entity it sends with: the block does not write one.
    _notifyActions() {
        const services = this._hass && this._hass.services && this._hass.services.notify;
        if (!services || typeof services !== 'object') return [];
        const phones = new Set((this.core.phones || []).map(p => p.service));
        return Object.keys(services).map(s => `notify.${s}`)
            .filter(a => a !== 'notify.send_message' && !phones.has(a)).sort();
    }

    // [ADDED v3.87.0] What a MOVE NOTIFY / TTS target is: one of the choices of _notifyTargetField (listed), and when Home
    // Assistant cannot call it, why (problem) and the action that reaches the same phone (fix). A target outside the
    // notify domain - a speaker, for tts.speak - is neither; without Home Assistant's list of actions nothing is said.
    _notifyTarget(target) {
        const t = String(target || '').trim();
        const out = { listed: false, phone: null, recipient: null, problem: '', note: '', fix: '' };
        // [ADDED v3.88.0] A recipient of LIBI Global. One not in the list read from Home Assistant is gone - said only when
        // that list was read.
        out.recipient = this.core.recipientOf(t);
        if (out.recipient) {
            out.listed = true;
            if ((out.recipient.missing || []).length) out.note = `${out.recipient.name} sends to a phone Home Assistant no longer has (${out.recipient.missing.join(', ')}): nothing reaches it. Tick the new phone in Global.`;
            return out;
        }
        if (/^script\.libi_send_to_[a-z0-9_]+$/.test(t)) {
            if (this._global.loaded) out.problem = `${t} is a recipient of LIBI Global that is no longer there: nothing is sent to it. Pick another one.`;
            return out;
        }
        const phones = this.core.phones || [];
        out.phone = phones.find(p => !p.shared && p.service === t) || null;
        if (out.phone || this._notifyActions().includes(t)) { out.listed = true; return out; }
        const services = this._hass && this._hass.services && this._hass.services.notify;
        const m = t.match(/^notify\.([a-z0-9_]+)$/);
        if (!m || !services || typeof services !== 'object') return out;
        const exists = Object.prototype.hasOwnProperty.call(services, m[1]);
        const shared = phones.find(p => p.shared && (p.service === t || p.entity_id === t));
        const entityOf = phones.find(p => !p.shared && p.entity_id === t);
        if (shared) {
            const both = `Two phones are registered as ${shared.name} in the Companion app, so Home Assistant has one action for both, ${shared.service}, and it reaches only one of them. Give one of the phones another name in the app, then pick it here.`;
            if (exists) out.note = both;
            else out.problem = `${t} is the notify entity of a phone, not an action: Home Assistant cannot send with it. ${both}`;
        } else if (entityOf) {
            const name = this.core.localName(t) || this.core.haName(t, this._hass) || entityOf.name || t;
            out.problem = `${t} is the notify entity of the phone ${name}, not an action: Home Assistant cannot send with it, so nothing reaches the phone. The phone's action is ${entityOf.service}.`;
            out.fix = entityOf.service;
        } else if (!exists) {
            out.problem = `${t} is not an action in this Home Assistant - a phone no longer registered in the Companion app? Nothing is sent to it. Pick another one.`;
        }
        return out;
    }

    // [ADDED v3.87.0] Where a MOVE NOTIFY / TTS block sends: the user's phones by name - the name given in LIBI, in any
    // project, else Home Assistant's - and Home Assistant's other notify actions. Every choice is an action Home
    // Assistant can call. The entity picker this replaces listed each phone by its notify entity (notify.sm_s938b), and
    // that went into the automation as its action: Home Assistant could not call it, and the user's train reminder said
    // nothing at its time (2026-11-04). A target that is none of these is kept until another one is chosen, and is
    // said. Built with DOM calls and textContent: the names come from the user's Home Assistant and from LIBI.
    _notifyTargetField(el, mode) {
        const target = String(el.target || '').trim();
        const info = this._notifyTarget(target);
        const wrap = document.createElement('div');
        wrap.className = 'fgrp notify-target';
        const label = document.createElement('label');
        label.id = 'lbl_target';
        label.textContent = 'Send to';
        const select = document.createElement('select');
        select.id = 'inp_target';
        select.setAttribute('dir', 'auto');
        const option = (parent, value, text, disabled = false) => {
            const o = document.createElement('option');
            o.value = value;
            o.textContent = text;
            o.disabled = disabled;
            parent.appendChild(o);
        };
        if (!target) option(select, '', 'Pick a phone or a notify action');
        else if (!info.listed) option(select, target, info.problem ? `${target} - not an action` : target);
        // [ADDED v3.88.0] LIBI Global's recipients first: their phones are changed in one place, for every project.
        const recipients = this.core.recipients || [];
        if (recipients.length) {
            const group = document.createElement('optgroup');
            group.label = 'Global';
            for (const r of recipients) {
                const n = r.phones.length;
                option(group, r.action, `${r.name} · ${n} phone${n === 1 ? '' : 's'}`);
            }
            select.appendChild(group);
        }
        const phones = this.core.phones || [];
        if (phones.length) {
            const group = document.createElement('optgroup');
            group.label = 'Phones';
            for (const p of phones) {
                const name = this.core.localName(p.service) || this.core.haName(p.entity_id, this._hass) || p.name || p.entity_id;
                const owner = String(p.owner || '');
                const what = [owner && !name.toLowerCase().includes(owner.toLowerCase()) ? owner : '',
                    p.shared ? 'shares its name with another phone' : '',
                    mode !== 'notify' && !p.shared && !p.speaks ? 'does not read aloud' : ''].filter(Boolean);
                option(group, p.shared ? `-shared-${p.entity_id}` : p.service, what.length ? `${name} · ${what.join(' · ')}` : name, !!p.shared);
            }
            select.appendChild(group);
        }
        const actions = this._notifyActions();
        if (actions.length) {
            const group = document.createElement('optgroup');
            group.label = 'Other notify actions';
            for (const a of actions) {
                const local = this.core.localName(a);
                option(group, a, local ? `${local} · ${a}` : a);
            }
            select.appendChild(group);
        }
        select.value = target;
        select.addEventListener('change', () => {
            el.target = select.value;
            this.core.pushHistory();
            this._render();
        });
        wrap.append(label, select);
        const say = (cls, text, color) => {
            const d = document.createElement('div');
            d.className = cls;
            d.setAttribute('dir', 'auto');
            d.style.cssText = `font-size:12px; color:${color}; overflow-wrap:anywhere;`;
            d.textContent = text;
            wrap.appendChild(d);
        };
        if (info.recipient) {
            const to = info.recipient.phones.map(s => this.core.friendlyName(s, this._hass) || s).join(', ');
            say('notify-target-action', `Global recipient: ${target}`, 'var(--secondary-text-color, #616161); font-family:monospace');
            say('notify-target-phones', `Sends to ${to || 'no phone'}. Change its phones in Global.`, 'var(--secondary-text-color, #616161)');
        } else if (info.listed) say('notify-target-action', `Home Assistant action: ${target}`, 'var(--secondary-text-color, #616161); font-family:monospace');
        if (info.note) say('notify-target-note', info.note, 'var(--warning-color, #b26a00)');
        if (info.problem) say('notify-target-warn', info.problem, 'var(--error-color, #db4437)');
        if (info.fix) {
            const btn = document.createElement('button');
            btn.id = 'notifyTargetFix';
            btn.className = 'btn';
            btn.style.cssText = 'min-height:40px; align-self:flex-start; max-width:100%; overflow-wrap:anywhere;';
            btn.textContent = `Send with ${info.fix}`;
            btn.addEventListener('click', () => {
                el.target = info.fix;
                this.core.pushHistory();
                this._render();
            });
            wrap.appendChild(btn);
        }
        // [ADDED v3.88.0] The way to LIBI Global: to change the phones of the recipient picked, or to make the first one.
        if (info.recipient || (this._global.loaded && !recipients.length)) {
            if (!recipients.length) say('notify-target-hint', 'Global: make a global variable - the phones of Guy, of everyone - and send to it from every project. A phone replaced is then changed in one place.', 'var(--secondary-text-color, #616161)');
            const open = document.createElement('button');
            open.id = 'notifyOpenGlobal';
            open.className = 'btn btn-ghost';
            open.style.cssText = 'min-height:40px; align-self:flex-start;';
            open.textContent = 'Open Global';
            // [CHANGED v3.88.1] Straight to the editor of the one picked.
            open.addEventListener('click', (e) => { e.stopPropagation(); this._openGlobal(info.recipient ? info.recipient.key : ''); });
            wrap.appendChild(open);
        }
        return wrap;
    }

    _picker(kind, value, onValue, opts = {}) {
        const wrap = document.createElement('div');
        wrap.className = 'fgrp';
        if (opts.label) wrap.innerHTML = `<label id="lbl_${this._esc(opts.id || kind)}">${this._esc(opts.label)}</label>`;

        // [ADDED v3.31.0] Home Assistant loads its pickers lazily, so one of them can be missing from
        // the browser tab a panel is opened in. Creating it anyway produced an element that renders
        // nothing, which is why the DEVICE field was an empty gap with no way to change anything.
        const TAG = { device: 'ha-device-picker', area: 'ha-area-picker' }[kind] || 'ha-entity-picker';
        if (typeof customElements !== 'undefined' && !customElements.get(TAG)) {
            const box = document.createElement('input');
            box.type = 'text';
            box.value = value || '';
            box.setAttribute('dir', 'auto');
            box.placeholder = kind === 'device' ? 'device id' : 'domain.entity';
            if (opts.id) box.id = `inp_${opts.id}`;
            box.addEventListener('change', () => onValue(box.value.trim()));
            wrap.appendChild(box);
            const note = document.createElement('div');
            note.style.cssText = 'font-size:11px;color:var(--secondary-text-color, #9e9e9e);margin-top:3px;';
            note.textContent = `Home Assistant has not loaded ${TAG} in this browser tab, so this is a plain field.`;
            wrap.appendChild(note);
            return wrap;
        }

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

        // [ADDED v3.26.0] A block built from a device node is not an entity, so it gets the two
        // fields Home Assistant offers for one: the device, and which of its triggers or actions.
        if (el.deviceNode) {
            this._deviceFields(el).forEach(node => slot.appendChild(node));
        } else if (['contact_no', 'contact_nc', 'contact_p', 'contact_n', 'coil', 'coil_s', 'coil_r', 'coil_t', 'wait'].includes(el.type)) {
            // [ADDED v3.31.0] The device comes first, then which of its entities, then the entity
            // field itself for anything outside that device.
            const entityId = String(el.label || '').replace(/\s*\+\d+$/, '').trim();
            if (/^[a-z_][a-z0-9_]*\.[a-z0-9_]+$/.test(entityId)) {
                this._deviceContextFields(el, entityId).forEach(n => slot.appendChild(n));
            }
            slot.appendChild(this._picker('entity', el.label, v => {
                el.label = v;
                el.targetSpec = v ? { entity_id: [v] } : {};
                el.targetKind = 'entity';
                el.targetLabel = v;
                this.core.pushHistory();
                this._render();
            }, { label: el.type.startsWith('coil') ? 'Controlled Entity' : 'Entity / Sensor', id: 'label' }));
            const browse = document.createElement('div');
            browse.className = 'fgrp';
            browse.innerHTML = `<button class="btn btn-ghost" id="inp_browse" style="width:100%;">◈ Browse by area, device or type</button>`;
            browse.querySelector('#inp_browse').addEventListener('click', () => {
                this._openEntityPicker(this._inspectedEl.netId, this._inspectedEl.rungId, this._inspectedEl.elId, 'label');
            });
            slot.appendChild(browse);
            // [ADDED v3.9.0] The Home Assistant picker shows only the friendly name, which is not
            // enough to tell which entity or which device is behind it. The id goes right under it.
            slot.appendChild(this._idNote(el));
            // [ADDED v3.24.0] Which service the coil calls, and whether the rung carries on when it
            // fails. Neither could be seen or changed before.
            if (el.type.startsWith('coil')) {
                slot.appendChild(this._serviceField(el));
                slot.appendChild(this._coeField(el));
            }
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
            slot.insertAdjacentHTML('beforeend', `<div class="fgrp"><label>Mode</label><select id="propMoveMode">
                <option value="value" ${mode === 'value' ? 'selected' : ''}>MOVE (assign a value)</option>
                <option value="notify" ${mode === 'notify' ? 'selected' : ''}>MOVE NOTIFY (alert)</option>
                <option value="tts" ${mode === 'tts' ? 'selected' : ''}>MOVE TTS (speak)</option>
                <option value="both" ${mode === 'both' ? 'selected' : ''}>MOVE NOTIFY/TTS (alert and speak)</option>
            </select></div>`);

            if (mode === 'value') {
                // [CHANGED v3.8.0] On a MOVE ACTION the IN pin is the Home Assistant service name, so
                // the field says so rather than calling it a value.
                const isAction = el.moveKind === 'action';
                slot.insertAdjacentHTML('beforeend', `<div class="fgrp"><label id="lbl_source">${isAction ? 'Action (Home Assistant service)' : 'Value or Template'}</label><textarea id="inp_source" rows="${isAction ? 1 : 3}" style="font-family:monospace;">${this._esc(el.source || '')}</textarea></div>`);
                if (isAction) slot.insertAdjacentHTML('beforeend', `<div class="fgrp" style="font-size:12px; color:var(--secondary-text-color, #757575); margin-top:-6px;">OUT is a summary of the targets below. It is not read back, the targets are.</div>`);
            } else {
                if (mode !== 'tts') {
                    slot.insertAdjacentHTML('beforeend', `<div class="fgrp"><label id="lbl_source">Message</label><textarea id="inp_source" rows="2">${this._esc(el.source || '')}</textarea></div>`);
                    slot.insertAdjacentHTML('beforeend', `<div class="fgrp"><label id="lbl_title">Title</label><input type="text" id="inp_title" value="${this._esc(el.title || '')}" /></div>`);
                }
                if (mode !== 'notify') {
                    slot.insertAdjacentHTML('beforeend', `<div class="fgrp"><label id="lbl_tts">Spoken text${mode === 'both' ? ' (leave empty to speak the message)' : ''}</label><textarea id="inp_tts" rows="2">${this._esc(el.tts || '')}</textarea></div>`);
                    slot.insertAdjacentHTML('beforeend', `<div class="fgrp"><label id="lbl_stream">Media stream</label><input type="text" id="inp_stream" value="${this._esc(el.stream || 'alarm_stream')}" /></div>`);
                }
            }

            // [CHANGED v3.87.0] A message goes to a phone or a notify action from LIBI's own list (_notifyTargetField).
            slot.appendChild(mode === 'value'
                ? this._picker('entity', el.target, v => { el.target = v; this.core.pushHistory(); this._render(); },
                    { label: 'Target Entity / Helper', id: 'target' })
                : this._notifyTargetField(el, mode));
            if (mode === 'value') {
                // [CHANGED v3.7.0] A value assignment targets things the same way an action does.
                const tpm = this._targetPicker(el);
                if (tpm) slot.appendChild(tpm);
                // [ADDED v3.24.0] Every action can carry on after an error, not only a coil.
                slot.appendChild(this._coeField(el));
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
            slot.insertAdjacentHTML('beforeend', `<div class="fgrp"><label id="lbl_sourceB">Above (MIN)</label><input type="text" id="inp_sourceB" value="${this._esc(el.sourceB === undefined ? '' : el.sourceB)}" /></div>`);
            slot.insertAdjacentHTML('beforeend', `<div class="fgrp"><label id="lbl_sourceC">Below (MAX)</label><input type="text" id="inp_sourceC" value="${this._esc(el.sourceC === undefined ? '' : el.sourceC)}" /></div>`);
            ['sourceB', 'sourceC'].forEach(prop => {
                const f = slot.querySelector(`#inp_${prop}`);
                if (f) f.addEventListener('change', e => { el[prop] = e.target.value; this.core.pushHistory(); this._render(); });
            });

        } else if (el.type === 'ctu') {
            const fgrpSrc = document.createElement('div'); fgrpSrc.className = 'fgrp'; fgrpSrc.innerHTML = `<label id="lbl_source">Counter Entity</label>`;
            const picker = document.createElement('ha-entity-picker'); picker.hass = this._hass; picker.value = el.source || ''; picker.includeDomains = ['counter'];
            picker.id = "inp_source";
            picker.addEventListener('value-changed', onChange('source')); fgrpSrc.appendChild(picker); slot.appendChild(fgrpSrc);
            slot.insertAdjacentHTML('beforeend', `<div class="fgrp"><label id="lbl_value">Preset Value (Limit)</label><input type="text" id="inp_value" value="${this._esc(el.value || '')}" /></div>`);

        } else if (el.type === 'notify') {
            const fgrpSrc = document.createElement('div'); fgrpSrc.className = 'fgrp'; fgrpSrc.innerHTML = `<label id="lbl_source">Message Text</label><textarea id="inp_source" rows="3">${this._esc(el.source || '')}</textarea>`; slot.appendChild(fgrpSrc);
            // [CHANGED v3.87.0] The same list as MOVE NOTIFY: the entity picker wrote a phone's notify entity here too.
            slot.appendChild(this._notifyTargetField(el, 'notify'));

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
                slot.insertAdjacentHTML('beforeend', `<div class="fgrp"><label id="lbl_sourceB">Value (IN2)</label><input type="text" id="inp_sourceB" value="${this._esc(el.sourceB === undefined ? '' : el.sourceB)}" /></div>`);
            } else if (kind === 'time') {
                el.sourceA = 'time';
                slot.insertAdjacentHTML('beforeend', `<div class="fgrp"><label>Left side (IN1)</label><input type="text" value="${CLOCK_IN1.time}" disabled /></div>`);
                slot.insertAdjacentHTML('beforeend', `<div class="fgrp"><label id="lbl_sourceB">Fixed time (HH:MM:SS)</label><input type="text" id="inp_sourceB" value="${this._esc(el.sourceB || '')}" placeholder="08:00:00" /></div>`);
                slot.appendChild(this._picker('entity', el.sourceB, v => { el.sourceB = v; this.core.pushHistory(); this._render(); },
                    { label: 'or a time helper', id: 'sourceBhelper', domains: ['input_datetime', 'sensor'] }));
                if (el.type === 'cmp_rng') {
                    slot.insertAdjacentHTML('beforeend', `<div class="fgrp"><label id="lbl_sourceC">Until (HH:MM:SS)</label><input type="text" id="inp_sourceC" value="${this._esc(el.sourceC || '')}" /></div>`);
                    const fc = slot.querySelector('#inp_sourceC');
                    if (fc) fc.addEventListener('change', e => { el.sourceC = e.target.value; this.core.pushHistory(); this._render(); });
                }
            } else if (kind === 'date') {
                el.sourceA = 'weekday';
                slot.insertAdjacentHTML('beforeend', `<div class="fgrp"><label>Left side (IN1)</label><input type="text" value="${CLOCK_IN1.weekday}" disabled /></div>`);
                // [ADDED v3.76.0] Or the days an 8-bit helper holds - bit 1 Sunday ... bit 7 Saturday, ticked on the
                // dashboard with LIBI's days row (the user's design); while a helper is chosen, the fixed days are off.
                const helper = /^(input_number|number)\./.test(String(el.sourceB || '')) ? String(el.sourceB) : '';
                const days = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'];
                const picked = helper ? [] : String(el.sourceB || '').split(',').map(d => d.trim()).filter(Boolean);
                const wrap = document.createElement('div');
                wrap.className = 'fgrp';
                wrap.innerHTML = `<label>Days of the week</label><div style="display:flex;flex-wrap:wrap;gap:6px;">${
                    days.map(d => `<label style="display:flex;align-items:center;gap:3px;font-size:12px;">
                        <input type="checkbox" data-day="${d}" ${picked.includes(d) ? 'checked' : ''} ${helper ? 'disabled' : ''}/>${d}</label>`).join('')}</div>`;
                slot.appendChild(wrap);
                wrap.querySelectorAll('input[type=checkbox]').forEach(cb => cb.addEventListener('change', () => {
                    const sel = [...wrap.querySelectorAll('input[type=checkbox]')].filter(x => x.checked).map(x => x.dataset.day);
                    el.sourceB = sel.join(', ');
                    this.core.pushHistory(); this._render();
                }));
                slot.appendChild(this._picker('entity', helper, v => { el.sourceB = v || ''; this.core.pushHistory(); this._render(); },
                    { label: 'or the days of a helper (8 bits: bit 1 Sunday ... bit 7 Saturday)', id: 'sourceBdays', domains: ['input_number', 'number'] }));
            } else if (kind === 'datetime') {
                el.sourceA = 'datetime';
                // [CHANGED v3.70.0] A schedule as well: the importer draws schedule.x on as the date and time = schedule.x.
                slot.appendChild(this._picker('entity', el.sourceB, v => { el.sourceB = v; this.core.pushHistory(); this._render(); },
                    { label: 'Date and time helper or schedule', id: 'sourceB', domains: ['input_datetime', 'sensor', 'schedule'] }));
                // [ADDED v3.71.0] What the schedule holds, and where its days and hours are set.
                const week = String(el.sourceB || '').startsWith('schedule.') ? this._scheduleText(el.sourceB) : '';
                if (week) {
                    slot.insertAdjacentHTML('beforeend', `<div class="fgrp"><label>Days and hours</label>
                        <div class="insp-note" dir="ltr">${this._esc(week)}</div>
                        <div class="insp-note">Set in the schedule itself: Settings ▸ Devices &amp; services ▸ Helpers.</div></div>`);
                }
            } else if (kind === 'sun') {
                el.sourceA = 'sun';
                slot.insertAdjacentHTML('beforeend', `<div class="fgrp"><label id="lbl_sourceB">Event</label><select id="inp_sourceB">
                    <option value="sunrise" ${el.sourceB === 'sunrise' ? 'selected' : ''}>sunrise</option>
                    <option value="sunset" ${el.sourceB === 'sunset' ? 'selected' : ''}>sunset</option></select></div>`);
            } else {
                slot.appendChild(this._picker('entity', el.sourceA, v => { el.sourceA = v; this.core.pushHistory(); this._render(); },
                    { label: isCmp ? 'Entity (IN1)' : 'Variable A (IN1)', id: 'sourceA' }));
                slot.insertAdjacentHTML('beforeend', `<div class="fgrp"><label id="lbl_sourceB">${isCmp ? 'Value or entity (IN2)' : 'Variable B (IN2)'}</label><input type="text" id="inp_sourceB" value="${this._esc(el.sourceB === undefined ? '' : el.sourceB)}" /></div>`);
            }
            
            const inpB = slot.querySelector('#inp_sourceB');
            if (inpB) inpB.addEventListener('change', e => { el.sourceB = e.target.value; this.core.pushHistory(); this._render(); });

            if (el.type === 'math_div') {
                slot.insertAdjacentHTML('beforeend', `<div class="fgrp"><label>Decimals</label><input type="number" id="inp_precision" value="${this._esc(el.precision === undefined ? 2 : el.precision)}" min="0" max="6" /></div>`);
                slot.insertAdjacentHTML('beforeend', `<div class="fgrp"><label>Result when dividing by zero</label><input type="text" id="inp_fallback" value="${this._esc(el.fallback === undefined ? 0 : el.fallback)}" /></div>`);
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
            slot.insertAdjacentHTML('beforeend', `<div class="fgrp"><label>Loop Type</label><select id="propLoopType"><option value="count" ${el.loopType === 'count' ? 'selected' : ''}>Count</option><option value="while" ${el.loopType === 'while' ? 'selected' : ''}>While</option></select></div><div class="fgrp"><label id="lbl_value">Value/Condition</label><input type="text" id="inp_value" value="${this._esc(el.value || '')}" /></div>`);
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
        
        if (['contact_no', 'contact_nc', 'contact_p', 'contact_n', 'coil', 'coil_s', 'coil_r', 'coil_t', 'wait'].includes(el.type)) { 
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
        // [ADDED v3.87.0] A notify target Home Assistant cannot call is red: Home Assistant saves it, and nothing is sent.
        if (this._sendsMessage(el) && !errs.tgt && this._notifyTarget(el.target).problem) { errs.tgt = true; errs.el = true; }
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
        const syncBadge = net.ha_id ? `<span style="font-size:11px; background:#e3f2fd; color:#0288d1; padding:2px 6px; border-radius:4px; margin-left:8px;" title="Linked to HA ID: ${this._esc(net.ha_id)}">🔗 Linked</span>` : '';
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
        <div class="net ${isCol}${this._selectedNetId === net.id && this._varsScope === 'net' ? ' net-selected' : ''}" data-nid="${net.id}">
            <div class="net-hdr" data-tog="${net.id}">
                <div class="net-hdr-l">
                    <span style="color:var(--success-color,#4caf50);">●</span>
                    <div class="net-name" data-sel="${this._esc(net.id)}" title="Click to show the variables of this NET">
                        <span style="font-weight:900; margin-right:4px;">NET&nbsp;${index + 1}</span>
                        <input type="text" class="net-name-input" data-nid="${this._esc(net.id)}" value="${this._esc(net.name)}" title="Click to rename" placeholder="Automation Name" />
                        ${levelBadge}
                        ${net.source === 'orphan' ? `<span style="font-size:11px; font-weight:700; background:#fdecea; color:#c62828; padding:2px 6px; border-radius:4px; margin-left:8px;" title="${this._esc(net.source_note || '')}">⚠ Orphan</span>` : ''}
                        ${syncBadge}
                        ${this._versionBadgeHtml(net)}
                    </div>
                </div>
                <div class="net-hdr-r net-fold" title="${net.collapsed ? 'Unfold this NET' : 'Fold this NET'}">
                    <span class="chevron" style="font-size:12px; color:var(--secondary-text-color, #888);">${net.collapsed ? '▼' : '▲'}</span>
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
                    ${this._netStateHtml(net)}
                    <div class="net-menu-wrapper">
                        <button class="net-kebab" data-menu-id="${net.id}">
                            <svg viewBox="0 0 24 24"><path fill="currentColor" d="M12,16A2,2 0 0,1 14,18A2,2 0 0,1 12,20A2,2 0 0,1 10,18A2,2 0 0,1 12,16M12,10A2,2 0 0,1 14,12A2,2 0 0,1 12,14A2,2 0 0,1 10,12A2,2 0 0,1 12,10M12,4A2,2 0 0,1 14,6A2,2 0 0,1 12,8A2,2 0 0,1 10,6A2,2 0 0,1 12,4Z"/></svg>
                        </button>
                        <div class="net-menu-dropdown" id="dropdown-${net.id}">
                            <button class="net-menu-item show-yaml-btn" data-nid="${net.id}">📄 Show as YAML</button>
                            <button class="net-menu-item card-net-btn" data-nid="${this._esc(net.id)}">📊 Dashboard card</button>
                            <button class="net-menu-item versions-net-btn" data-nid="${this._esc(net.id)}">🕘 Versions</button>
                            <button class="net-menu-item duplicate-net-btn" data-nid="${net.id}">⧉ Duplicate Net</button>
                            <button class="net-menu-item danger delete-net-btn" data-nid="${this._esc(net.id)}">🗑️ Delete NET…</button>
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

    // [ADDED v3.47.0] The version of this net that runs in Home Assistant. When an earlier version was
    // chosen, the newest one is named next to it, so it is clear that the newest is not the one running.
    _versionBadgeHtml(net) {
        const v = (this._versions || {})[net.id];
        if (!v || !v.active) return '';
        const older = v.latest && v.active !== v.latest;
        const text = older ? `V${v.active} · newest V${v.latest}` : `V${v.active}`;
        const tip = older ? `Version ${v.active} runs in Home Assistant. Version ${v.latest} is newer. Click to choose a version.`
                          : `Version ${v.active} runs in Home Assistant. Click to see the earlier versions.`;
        return `<button class="ver-badge${older ? ' older' : ''}" data-nid="${this._esc(net.id)}" title="${this._esc(tip)}">${this._esc(text)}</button>`;
    }

    _versionsDialogHtml() {
        const vm = this._verModal || {};
        const net = this.core.nets.find(n => n.id === vm.nid);
        // [CHANGED v3.85.0] V1 of an automation opened in LIBI is the original as Home Assistant had it, V2 its copy.
        const reasons = { opened: 'Recorded when the project was opened', saved: 'Saved from LIBI', external: 'Changed outside LIBI',
            original: 'The original, as it was in Home Assistant when it was first opened in LIBI', copy: 'A copy of the original, to work on' };
        const muted = 'font-size:13px; color:var(--secondary-text-color, #757575); margin:0;';
        let body;
        if (vm.loading) body = `<p style="${muted}">Loading the versions…</p>`;
        else if (vm.error) body = `<p class="ver-error">${this._esc(vm.error)}</p>`;
        else if (!(vm.versions || []).length) body = `<p style="${muted}">No versions yet. The first one is recorded when this net is saved and compiled.</p>`;
        else body = `<div class="auto-list ver-list">${vm.versions.map(v => {
            const running = v.v === vm.active;
            let when = String(v.saved || '');
            try { when = new Date(v.saved).toLocaleString(); } catch (err) { /* keep the stored text */ }
            return `<div class="ver-item${running ? ' running' : ''}">
                <div class="ver-row">
                    <span class="ver-num">V${this._esc(v.v)}</span>
                    ${v.original ? '<span class="ver-original">Original</span>' : ''}
                    <span class="ver-when">${this._esc(when)}</span>
                    ${running ? '<span class="ver-run">● Runs in Home Assistant</span>' : ''}
                    <span style="flex:1"></span>
                    <button class="btn ver-use" data-v="${this._esc(v.v)}">Put on the canvas</button>
                </div>
                <div class="ver-why">${this._esc(reasons[v.reason] || v.reason || '')}${v.name ? ' · ' + this._esc(v.name) : ''}</div>
                <details class="ver-yaml"><summary>YAML</summary><pre dir="ltr">${this._esc(v.yaml || '')}</pre></details>
            </div>`;
        }).join('')}</div>`;
        return `<div class="modal-overlay" id="modalOverlay"><div class="modal ver-modal">
            <h2 class="modal-title" dir="auto">Versions · ${this._esc(net ? net.name : '')}</h2>
            <p style="${muted}">Every save that changes this net keeps the version before it. Putting a version on the canvas does not change Home Assistant yet: SAVE &amp; COMPILE makes it the version that runs. When no version is chosen, the newest saved version is the one that runs.</p>
            ${body}
            <div class="modal-actions"><button class="btn btn-ghost" id="closeModalBtn">Close</button></div>
        </div></div>`;
    }

    async _openVersions(nid) {
        this.shadowRoot.querySelectorAll('.net-menu-dropdown.show').forEach(d => d.classList.remove('show'));
        this._verModal = { nid, loading: true, versions: [], active: 0 };
        this._modal = 'net_versions';
        this._render();
        if (!this._project || !this._hass || !this._hass.connection) {
            this._verModal = { nid, versions: [], active: 0, error: 'Versions belong to a project. Save the project first.' };
        } else {
            try {
                const res = await this._hass.connection.sendMessagePromise({ type: 'libi/net_versions', slug: this._project.slug, net_id: nid });
                this._verModal = { nid, versions: (res && res.versions) || [], active: (res && res.active) || 0 };
            } catch (err) {
                // An updated panel talking to a Home Assistant that still runs the previous LIBI: the
                // JavaScript is new after a refresh, the Python only after a restart.
                const stale = err && err.code === 'unknown_command';
                this._verModal = { nid, versions: [], active: 0, error: stale
                    ? 'LIBI was updated, but Home Assistant still runs the previous version. Restart Home Assistant (Settings ▸ System ▸ Restart); opening the project afterwards records V1 of every net.'
                    : 'The versions could not be read: ' + (err && err.message ? err.message : err) };
            }
        }
        if (this._modal === 'net_versions' && this._verModal && this._verModal.nid === nid) this._render();
    }

    // Replaces the net on the canvas with the chosen version. The net keeps its place, its id and the
    // automation it is linked to, so the save that follows overwrites the same automation in Home
    // Assistant and the backend recognises the YAML as that earlier version instead of a new one.
    _useVersion(number) {
        const vm = this._verModal || {};
        const at = this.core.nets.findIndex(n => n.id === vm.nid);
        const ver = (vm.versions || []).find(x => Number(x.v) === number);
        if (at < 0 || !ver || !ver.net) return;
        const cur = this.core.nets[at];
        const copy = this.core.duplicateNet(ver.net);
        copy.id = cur.id;
        copy.name = ver.net.name || cur.name;
        const haId = cur.ha_id || ver.net.ha_id;
        if (haId) copy.ha_id = haId; else delete copy.ha_id;
        delete copy.source;
        delete copy.source_note;
        this.core.nets[at] = copy;
        this.core.repairAST();
        this.core.pushHistory();
        this._projectDirty = true;
        this._inspectedEl = null;
        this._modal = null;
        this._verModal = null;
        this._render();
        alert(`V${number} is on the canvas. Press SAVE & COMPILE to make it the version that runs in Home Assistant.`);
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
        
        const errTooltip = hasStructErr ? `<div class="err-tooltip">⚠️ ${this._esc(el.structuralError)}</div>` : '';
        // [CHANGED v3.25.0] Both badges sit under the block. A trigger and a continue on error can
        // never be the same block, so they never collide.
        const triggerLabelHtml = el.isTrigger ? `<div class="trigger-bottom-lbl">Trigger</div>`
            : (el.continueOnError ? `<div class="coe-bottom-lbl" title="continue_on_error: the rung carries on to the next checks even if this fails or the entity is unavailable">continue if error</div>` : '');

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

    // [ADDED v3.12.0] Reads a saved number, clamped, and never throws when storage is unavailable.
    // [ADDED v3.16.0] Every entity a drawing points at. With no net given it is the whole project,
    // with one it is just that net, which is what the default view of the bar shows.
    _netEntities(net) {
        const found = new Set();
        const add = (v) => {
            const s = String(v == null ? '' : v).replace(/\s*\+\d+$/, '').trim();
            if (/^[a-z_][a-z0-9_]*\.[a-z0-9_]+$/.test(s)) found.add(s);
        };
        this._eachElement(net, el => {
            ['label', 'target', 'source', 'sourceA', 'sourceB'].forEach(k => add(el[k]));
            const spec = (el.targetSpec || {}).entity_id;
            (Array.isArray(spec) ? spec : (spec ? [spec] : [])).forEach(add);
        });
        // Variables made for this net but not yet placed on a rung still belong to it.
        (net.vars || []).forEach(add);
        return found;
    }

    _projectEntities() {
        const all = new Set();
        (this.core.nets || []).forEach(n => this._netEntities(n).forEach(e => all.add(e)));
        return all;
    }

    // The net the bar is scoped to: the one holding the selected element, else the first one.
    // [CHANGED v3.86.0] The NET chosen last - its title or one of its elements clicked - comes first.
    _currentNet() {
        if (this._selectedNetId) {
            const n = this.core.nets.find(x => x.id === this._selectedNetId);
            if (n) return n;
        }
        if (this._inspectedEl) {
            const n = this.core.nets.find(x => x.id === this._inspectedEl.netId);
            if (n) return n;
        }
        if (this._inspectedNetYaml) {
            const n = this.core.nets.find(x => x.id === this._inspectedNetYaml);
            if (n) return n;
        }
        return (this.core.nets || [])[0] || null;
    }

    _varsRows() {
        const states = (this._hass && this._hass.states) || {};
        const net = this._currentNet();
        // [CHANGED v3.86.0] Or every NET of the project, when its name was clicked.
        const scoped = this._varsScope === 'project' ? this._projectEntities()
            : (this._varsScope === 'net' && net ? this._netEntities(net) : null);
        const q = String(this._varsQuery || '').trim().toLowerCase();

        let ids = scoped ? [...scoped] : Object.keys(states);
        if (!scoped && this._varsFilter === 'ALL') {
            // Showing the whole house with no filter would be thousands of rows, so only the
            // helpers are listed until a filter or a search narrows it.
            ids = ids.filter(e => HELPER_DOMAINS.includes(e.split('.')[0]));
        }
        return ids
            .filter(e => this._varsFilter === 'ALL' || varTypeOf(e, this._hass) === this._varsFilter)
            .filter(e => {
                if (!q) return true;
                const nm = (this.core.friendlyName(e, this._hass) || '').toLowerCase();
                return e.toLowerCase().includes(q) || nm.includes(q);
            })
            .sort();
    }

    _varsRowHtml(entityId) {
        const st = (this._hass && this._hass.states && this._hass.states[entityId]) || null;
        const name = this.core.friendlyName(entityId, this._hass) || entityId.split('.').slice(1).join('.');
        const domain = entityId.split('.')[0];
        const type = varTypeOf(entityId, this._hass);
        const objectId = entityId.split('.').slice(1).join('.');
        const stored = HELPER_DOMAINS.includes(domain) && this._helperIds[domain] && this._helperIds[domain][objectId];
        const typeCell = type === 'HA'
            ? `<span class="type-tag type-HA" title="An ordinary Home Assistant entity, not a variable LIBI can change">HA</span>`
            : `<select class="vars-type" data-eid="${this._esc(entityId)}" ${stored ? '' : 'disabled'} title="${stored ? 'Change the type of this variable' : 'Written in YAML, so LIBI cannot change it'}">
                    ${VAR_TYPE_KEYS.map(k => `<option value="${k}" ${k === type ? 'selected' : ''}>${k}</option>`).join('')}
               </select>`;
        return `<tr class="vars-drag" draggable="true" data-eid="${this._esc(entityId)}" title="Drag onto a pin or a block to use it there">
            <td class="grab">⠿</td>
            <td class="c-name" dir="auto">${this._esc(name)}</td>
            <td class="c-eid">${this._esc(entityId)}</td>
            <td>${typeCell}</td>
            <td class="c-val">${st ? this._esc(String(st.state).slice(0, 16)) : '—'}</td>
            <td class="c-act"><button class="vars-del" data-eid="${this._esc(entityId)}" ${stored ? '' : 'disabled'} title="${stored ? 'Delete this variable' : 'Written in YAML, so it cannot be removed from here'}">🗑</button></td>
        </tr>`;
    }

    _varsBarHtml() {
        const net = this._currentNet();
        const rows = this._varsRows();
        const projectCount = this._projectEntities().size;

        const chip = (id, label, on, title) =>
            `<button class="vars-chip${on ? ' on' : ''}" id="${id}" title="${this._esc(title || '')}">${this._esc(label)}</button>`;
        const filterChips = ['ALL', ...VAR_TYPE_KEYS, 'HA']
            .map(k => `<button class="vars-chip vars-filter${this._varsFilter === k ? ' on' : ''}" data-f="${k}" title="${this._esc(k === 'ALL' ? 'Every type' : (VAR_TYPES[k] ? VAR_TYPES[k].title : 'Entities of Home Assistant that are not LIBI variables'))}">${k}</button>`)
            .join('');

        const table = rows.length
            ? `<table class="vars-table"><thead><tr>
                    <th style="width:22px;"></th><th>Name</th><th>Entity</th><th style="width:110px;">Type</th><th style="width:110px;">Value</th><th style="width:44px;"></th>
               </tr></thead><tbody>${rows.map(e => this._varsRowHtml(e)).join('')}</tbody></table>`
            : `<div class="vars-empty">${this._varsScope === 'net'
                    ? (net ? `This net uses no variables yet. Make one below and it is added to ${this._esc(net.name)}.` : 'There is no net to scope to yet.')
                    : this._varsScope === 'project' && !projectCount
                        ? 'The NETs of this project use no variables yet.'
                        : 'Nothing matches. Try another filter or another word.'}</div>`;

        const body = this._varsTab === 'search'
            ? `<div class="vars-filters">
                    <input type="text" id="varsQuery" placeholder="Search this project and all of Home Assistant" value="${this._esc(this._varsQuery)}" dir="auto" />
                    ${this._varsQuery ? '<button class="vars-chip" id="varsClear">Clear</button>' : ''}
                    <div class="vars-sep"></div>${filterChips}
               </div>
               ${(() => {
                    const q = String(this._varsQuery || '').trim().toLowerCase();
                    const states = (this._hass && this._hass.states) || {};
                    const inProj = this._projectEntities();
                    const match = (e) => {
                        if (this._varsFilter !== 'ALL' && varTypeOf(e, this._hass) !== this._varsFilter) return false;
                        if (!q) return true;
                        const nm = (this.core.friendlyName(e, this._hass) || '').toLowerCase();
                        return e.toLowerCase().includes(q) || nm.includes(q);
                    };
                    const mine = [...inProj].filter(match).sort();
                    const rest = Object.keys(states).filter(e => !inProj.has(e) && match(e)).sort().slice(0, 120);
                    const sect = (title, list) => list.length
                        ? `<div class="vars-group-title" style="font-size:11px;font-weight:800;text-transform:uppercase;color:var(--secondary-text-color, #9e9e9e);margin:8px 0 2px;">${this._esc(title)} · ${list.length}</div>
                           <table class="vars-table"><tbody>${list.map(e => this._varsRowHtml(e)).join('')}</tbody></table>` : '';
                    if (!mine.length && !rest.length) return '<div class="vars-empty">Nothing matches that.</div>';
                    return sect('In this project', mine) + sect('Everywhere in Home Assistant', rest);
               })()}`
            : `<div class="vars-filters">
                    ${chip('varsScopeNet', net ? `Net · ${net.name}` : 'This net', this._varsScope === 'net', 'Only the variables this net uses')}
                    ${chip('varsScopeProject', this._project ? `Project · ${this._project.name}` : 'All NETs', this._varsScope === 'project', 'The variables of every NET of this project')}
                    ${chip('varsScopeAll', `All of Home Assistant`, this._varsScope === 'all', 'Every variable in the house')}
                    <div class="vars-sep"></div>${filterChips}
               </div>
               ${table}
               <div class="vars-new">
                    <input type="text" class="name" id="varsNewName" placeholder="New variable name" value="${this._esc(this._varsNewName)}" dir="auto" />
                    <select id="varsNewType">${VAR_TYPE_KEYS.map(k => `<option value="${k}" ${this._varsNewType === k ? 'selected' : ''}>${k} · ${VAR_TYPES[k].domain}</option>`).join('')}</select>
                    <button class="btn" id="varsCreate">Add variable</button>
                    <div class="note">${net ? `It is created in Home Assistant and listed under ${this._esc(net.name)} straight away.` : 'Make a net first so the variable has somewhere to belong.'}</div>
               </div>`;


        return `<div class="vars-bar${this._varsOpen ? '' : ' rail'}" id="varsBar">
            <div class="vars-grip" id="varsGrip" title="Drag to resize. Double click to reset."></div>
            <div class="vars-top">
                <span class="vars-title">Variables</span>
                <div class="vars-tabs">
                    <button class="vars-tab${this._varsTab === 'helper' ? ' on' : ''}" id="varsTabHelper">Helper</button>
                    <button class="vars-tab${this._varsTab === 'vars' ? ' on' : ''}" id="varsTabVars">Variables<span class="n">${rows.length}</span></button>
                    <button class="vars-tab${this._varsTab === 'search' ? ' on' : ''}" id="varsTabSearch">Search<span class="n">${projectCount}</span></button>
                    <button class="vars-tab${this._varsTab === 'global' ? ' on' : ''}" id="varsTabGlobal" title="LIBI Global: the recipients of messages, for every project">Global<span class="n">${(this.core.recipients || []).length}</span></button>
                </div>
                <div class="spacer"></div>
                <button class="vars-fold" id="varsFold" title="${this._varsOpen ? 'Fold the bar down' : 'Open the bar'}">${this._varsOpen ? '▼' : '▲'}</button>
            </div>
            <div class="vars-body">${this._varsTab === 'helper' ? this._helperViewHtml() : (this._varsTab === 'global' ? this._globalViewHtml() : body)}</div>
        </div>`;
    }

    // [ADDED v3.21.0] The same rows the helpers page of Home Assistant shows, drawn from state the
    // panel already has. Nothing is fetched and nothing is loaded, so opening the tab is instant.
    HELPER_ICONS() {
        return { input_boolean: '⏼', input_button: '⏻', input_number: '↔', input_text: 'T',
                 input_select: '☰', input_datetime: '🕐', counter: '#', timer: '⏱', schedule: '📅' };
    }

    _helperRows() {
        const states = (this._hass && this._hass.states) || {};
        const q = String(this._helperQuery || '').trim().toLowerCase();
        return Object.keys(states)
            .filter(e => HELPER_DOMAINS.includes(e.split('.')[0]))
            .filter(e => {
                if (!q) return true;
                const nm = (this.core.friendlyName(e, this._hass) || '').toLowerCase();
                return e.toLowerCase().includes(q) || nm.includes(q);
            })
            .sort((a, b) => (this.core.friendlyName(a, this._hass) || a)
                .localeCompare(this.core.friendlyName(b, this._hass) || b));
    }

    _helperAreaName(entityId) {
        const h = this._hass || {};
        const reg = (h.entities || {})[entityId] || null;
        let areaId = reg && reg.area_id;
        if (!areaId && reg && reg.device_id && h.devices) {
            const dev = h.devices[reg.device_id];
            areaId = dev && dev.area_id;
        }
        const area = areaId && h.areas ? h.areas[areaId] : null;
        return (area && area.name) || '';
    }

    _helperViewHtml() {
        const icons = this.HELPER_ICONS();
        const rows = this._helperRows();
        const body = rows.length
            ? `<table class="helper-table"><thead><tr>
                    <th style="width:30px;"></th><th>Name</th><th style="width:150px;">Type</th>
                    <th style="width:150px;">Area</th><th>Entity</th><th style="width:110px;">Value</th>
               </tr></thead><tbody>${rows.map(e => {
                    const domain = e.split('.')[0];
                    const st = (this._hass.states || {})[e];
                    return `<tr class="helper-row" data-eid="${this._esc(e)}" title="Open the Home Assistant settings for this helper">
                        <td class="h-ico">${icons[domain] || '•'}</td>
                        <td class="h-name" dir="auto">${this._esc(this.core.friendlyName(e, this._hass) || e.split('.').slice(1).join('.'))}</td>
                        <td>${domain}</td>
                        <td class="h-area" dir="auto">${this._esc(this._helperAreaName(e) || '—')}</td>
                        <td class="h-eid">${this._esc(e)}</td>
                        <td class="h-val">${st ? this._esc(String(st.state).slice(0, 16)) : '—'}</td>
                    </tr>`;
               }).join('')}</tbody></table>`
            : `<div class="vars-empty">${this._helperQuery ? 'No helper matches that.' : 'There are no helpers yet.'}</div>`;

        return `<div class="helper-view">
            <div class="helper-top">
                <input type="text" id="helperSearch" placeholder="Search helpers" value="${this._esc(this._helperQuery)}" dir="auto" />
                ${this._helperQuery ? '<button class="vars-chip" id="helperClear">Clear</button>' : ''}
                <span class="helper-count">${rows.length} helper${rows.length === 1 ? '' : 's'}</span>
            </div>
            <div class="helper-scroll">${body}</div>
            <div class="helper-foot">
                <button class="btn" id="helperCreate">＋ Create helper</button>
                <span class="note">Opens the dialog of Home Assistant. Clicking a row opens its settings, also the dialog of Home Assistant.</span>
            </div>
        </div>`;
    }

    // Clicking a helper opens the settings dialog of Home Assistant for it. hass-more-info is a
    // first class event of the frontend: the root element listens for it and loads the dialog
    // itself, so this works from a custom panel with nothing embedded and nothing duplicated.
    _openHelperSettings(entityId) {
        this.dispatchEvent(new CustomEvent('hass-more-info', {
            bubbles: true, composed: true, detail: { entityId },
        }));
    }

    // [CHANGED v3.22.0] Home Assistant's own dialog first, always. It is registered as
    // dialog-helper-detail, and when it has been loaded in this browser tab that is what opens.
    // Its module sits behind a file name carrying a build hash, so nothing outside its frontend can
    // import it on demand, and a panel opened straight at /libi will usually not have it. Rather
    // than throw the user out of LIBI to press the same button again on another page, the dialog
    // below is LIBI's own, built to the same shape.
    _openCreateHelper() {
        const TAG = 'dialog-helper-detail';
        if (typeof customElements !== 'undefined' && customElements.get(TAG)) {
            this.dispatchEvent(new CustomEvent('show-dialog', {
                bubbles: true, composed: true,
                detail: {
                    dialogTag: TAG,
                    dialogImport: () => Promise.resolve(),
                    dialogParams: { dialogClosedCallback: () => this._render() },
                },
            }));
            return;
        }
        this._hkPick = null;
        this._hkForm = {};
        this._hkQuery = '';
        this._modal = 'helper_new';
        this._render();
    }

    // [CHANGED v3.23.0] The whole Create helper list of Home Assistant, in its own order. The first
    // nine are kept in a stored collection and any client can create them, so LIBI builds them here
    // with the settings each one really takes. The rest are built by a setup flow of their own and
    // cannot be created from outside the Home Assistant frontend, so they are listed and handed over
    // rather than half made.
    HELPER_KINDS() {
        return [
            { domain: 'input_button',   name: 'Button',           icon: '⏻', fields: ['icon'] },
            { domain: 'switch_as_x',    name: 'Change device type of a switch', icon: '⇄', flow: true },
            { domain: 'min_max',        name: 'Combine the state of several sensors', icon: '±', flow: true },
            { domain: 'counter',        name: 'Counter',          icon: '#',  fields: ['icon', 'initial', 'minimum', 'maximum', 'step', 'restore'] },
            { domain: 'input_datetime', name: 'Date and/or time', icon: '🕐', fields: ['icon', 'has_date', 'has_time'] },
            { domain: 'derivative',     name: 'Derivative sensor', icon: 'ƒ', flow: true },
            { domain: 'input_select',   name: 'Dropdown',         icon: '☰',  fields: ['icon', 'options', 'initial_option'] },
            { domain: 'filter',         name: 'Filter',           icon: '⏷', flow: true },
            { domain: 'generic_hygrostat', name: 'Generic hygrostat', icon: '💧', flow: true },
            { domain: 'generic_thermostat', name: 'Generic thermostat', icon: '🌡', flow: true },
            { domain: 'group',          name: 'Group',            icon: '◎', flow: true },
            { domain: 'history_stats',  name: 'History Stats',    icon: '📈', flow: true },
            { domain: 'integration',    name: 'Integral sensor',  icon: '∫', flow: true },
            { domain: 'mold_indicator', name: 'Mold Indicator',   icon: '☂', flow: true },
            { domain: 'input_number',   name: 'Number',           icon: '↔',  fields: ['icon', 'min', 'max', 'initial', 'step', 'mode_number', 'unit_of_measurement'] },
            { domain: 'totp',           name: 'One-Time Password (OTP)', icon: '🔐', flow: true },
            { domain: 'random',         name: 'Random',           icon: '🎲', flow: true },
            { domain: 'schedule',       name: 'Schedule',         icon: '📅', fields: ['icon', 'week'] },
            { domain: 'statistics',     name: 'Statistics',       icon: '📊', flow: true },
            { domain: 'template',       name: 'Template',         icon: '{}', flow: true },
            { domain: 'input_text',     name: 'Text',             icon: 'T',  fields: ['icon', 'min', 'max', 'initial_text', 'pattern', 'mode_text'] },
            { domain: 'threshold',      name: 'Threshold Sensor', icon: '⚖', flow: true },
            { domain: 'timer',          name: 'Timer',            icon: '⏱', fields: ['icon', 'duration', 'restore'] },
            { domain: 'tod',            name: 'Times of the Day Sensor', icon: '🕓', flow: true },
            { domain: 'input_boolean',  name: 'Toggle',           icon: '⏼', fields: ['icon'] },
            { domain: 'trend',          name: 'Trend',            icon: '📉', flow: true },
            { domain: 'utility_meter',  name: 'Utility Meter',    icon: '⏲', flow: true },
        ];
    }

    // What each setting is called, what it looks like and what it starts as. The key that is sent to
    // Home Assistant is the key here, except where a suffix keeps two different fields apart.
    HELPER_FIELD_SPEC() {
        return {
            icon:                { label: 'Icon', type: 'text', def: '', hint: 'mdi:lightbulb', optional: true },
            min:                 { label: 'Minimum', type: 'number', def: 0 },
            max:                 { label: 'Maximum', type: 'number', def: 100 },
            step:                { label: 'Step size', type: 'number', def: 1 },
            minimum:             { label: 'Minimum', type: 'number', def: 0 },
            maximum:             { label: 'Maximum', type: 'number', def: 100 },
            initial:             { label: 'Initial value', type: 'number', def: 0 },
            initial_text:        { label: 'Initial value', type: 'text', def: '', key: 'initial', optional: true },
            initial_option:      { label: 'Initial option', type: 'text', def: '', key: 'initial', optional: true },
            restore:             { label: 'Restore the value after a restart', type: 'bool', def: true },
            has_date:            { label: 'Has date', type: 'bool', def: true },
            has_time:            { label: 'Has time', type: 'bool', def: true },
            options:             { label: 'Options, one per line', type: 'lines', def: 'Option 1' },
            duration:            { label: 'Duration', type: 'text', def: '00:01:00', hint: 'hh:mm:ss' },
            pattern:             { label: 'Regex pattern', type: 'text', def: '', optional: true },
            unit_of_measurement: { label: 'Unit of measurement', type: 'text', def: '', hint: '°C, %, kWh', optional: true },
            mode_number:         { label: 'Display mode', type: 'select', def: 'box', key: 'mode',
                                   choices: [['box', 'Input field'], ['slider', 'Slider']] },
            mode_text:           { label: 'Display mode', type: 'select', def: 'text', key: 'mode',
                                   choices: [['text', 'Text'], ['password', 'Password']] },
            week:                { label: 'Days', type: 'week', def: null },
        };
    }

    WEEK_DAYS() {
        return [['monday', 'Mon'], ['tuesday', 'Tue'], ['wednesday', 'Wed'], ['thursday', 'Thu'],
                ['friday', 'Fri'], ['saturday', 'Sat'], ['sunday', 'Sun']];
    }

    // [ADDED v3.71.0] Every schedule helper with its days and hours, by object id, for the CMP DATETIME block that
    // compares the clock with one. Read when the panel opens and whenever the variables are read again.
    async _loadSchedules(render = true) {
        if (!this._hass || !this._hass.connection) return;
        const next = {};
        try {
            const res = await this._hass.connection.sendMessagePromise({ type: 'schedule/list' });
            (Array.isArray(res) ? res : (res && res.items) || []).forEach(it => { if (it && it.id) next[String(it.id)] = it; });
        } catch (err) { /* no schedule integration in this installation */ }
        this._schedules = next;
        if (render && this._initialized) this._render();
    }

    // [ADDED v3.71.0] The days and hours a schedule holds, short: "Tue Thu Sun 06:00–06:30", or day by day when the
    // hours differ. '' when they are not known.
    _scheduleText(entityId) {
        const item = (this._schedules || {})[String(entityId || '').split('.').slice(1).join('.')];
        if (!item) return '';
        const hm = (t) => String(t || '').replace(/^(\d{1,2}:\d{2}):00$/, '$1');
        const spans = (day) => (Array.isArray(item[day]) ? item[day] : []).map(s => `${hm(s.from)}–${hm(s.to)}`).join(', ');
        const marked = this.WEEK_DAYS().filter(([day]) => spans(day));
        if (!marked.length) return 'no days marked yet';
        const first = spans(marked[0][0]);
        if (marked.every(([day]) => spans(day) === first)) return `${marked.map(([, name]) => name).join(' ')} ${first}`;
        return marked.map(([day, name]) => `${name} ${spans(day)}`).join(' · ');
    }

    _hkPickKind(domain) {
        const kind = this.HELPER_KINDS().find(k => k.domain === domain);
        if (!kind) return;
        this._hkPick = domain;
        this._hkForm = { name: '' };
        if (kind.flow) {
            // A setup flow of its own. If Home Assistant has its flow dialog loaded, start it there
            // and nothing more is needed from LIBI.
            if (this._startConfigFlow(domain)) { this._modal = null; this._hkPick = null; this._render(); return; }
            this._render();
            return;
        }
        const spec = this.HELPER_FIELD_SPEC();
        (kind.fields || []).forEach(f => { this._hkForm[f] = spec[f].def; });
        if ((kind.fields || []).includes('week')) {
            // Every day off to begin with, the same as a new schedule in Home Assistant.
            this._hkForm.week = {};
            this.WEEK_DAYS().forEach(([d]) => { this._hkForm.week[d] = { on: false, from: '08:00', to: '17:00' }; });
        }
        this._render();
    }

    // The very call the Create helper dialog of Home Assistant makes for a helper that has a setup
    // flow. It works whenever that dialog has been loaded in this browser tab.
    _startConfigFlow(handler) {
        const TAG = 'dialog-data-entry-flow';
        if (typeof customElements === 'undefined' || !customElements.get(TAG)) return false;
        this.dispatchEvent(new CustomEvent('show-dialog', {
            bubbles: true, composed: true,
            detail: {
                dialogTag: TAG,
                dialogImport: () => Promise.resolve(),
                dialogParams: { startFlowHandler: handler, showAdvanced: false,
                                dialogClosedCallback: () => this._render() },
            },
        }));
        return true;
    }

    async _hkCreate() {
        const kind = this.HELPER_KINDS().find(k => k.domain === this._hkPick);
        if (!kind || kind.flow) return;
        const name = String(this._hkForm.name || '').trim();
        if (!name) { alert('A helper needs a name.'); return; }
        const spec = this.HELPER_FIELD_SPEC();
        const msg = { type: `${kind.domain}/create`, name };

        for (const f of (kind.fields || [])) {
            const s = spec[f];
            const key = s.key || f;
            let v = this._hkForm[f];
            if (s.type === 'week') {
                this.WEEK_DAYS().forEach(([d]) => {
                    const row = (v || {})[d] || {};
                    msg[d] = row.on ? [{ from: `${row.from}:00`, to: `${row.to}:00` }] : [];
                });
                continue;
            }
            if (s.type === 'number') v = Number(v);
            else if (s.type === 'bool') v = !!v;
            else if (s.type === 'lines') {
                v = String(v || '').split('\n').map(x => x.trim()).filter(Boolean);
                if (!v.length) v = ['Option 1'];
            } else v = String(v == null ? '' : v).trim();
            // An optional field that was left blank is not sent at all, because Home Assistant
            // treats an empty string as a value and would store it.
            if (s.optional && (v === '' || (Array.isArray(v) && !v.length))) continue;
            msg[key] = v;
        }

        if (kind.domain === 'input_number') {
            if (!(msg.max > msg.min)) { alert('The maximum has to be above the minimum.'); return; }
            if (msg.initial !== undefined && (msg.initial < msg.min || msg.initial > msg.max)) {
                alert('The initial value has to sit between the minimum and the maximum.'); return;
            }
        }
        if (kind.domain === 'counter' && !(msg.maximum > msg.minimum)) {
            alert('The maximum has to be above the minimum.'); return;
        }
        if (kind.domain === 'input_text' && msg.max === undefined) msg.max = 100;
        if (kind.domain === 'input_select' && msg.initial && !(msg.options || []).includes(msg.initial)) {
            alert('The initial option has to be one of the options.'); return;
        }

        try {
            await this._hass.connection.sendMessagePromise(msg);
            this._modal = null;
            this._hkPick = null;
            this._hkForm = {};
            this._render();
        } catch (err) {
            alert('Could not create the helper: ' + (err && err.message ? err.message : err));
        }
    }

    _hkDialogHtml() {
        const spec = this.HELPER_FIELD_SPEC();

        // Step two: the settings for the kind that was picked.
        if (this._hkPick) {
            const kind = this.HELPER_KINDS().find(k => k.domain === this._hkPick);

            if (kind.flow) {
                return `<div class="modal-overlay" id="modalOverlay"><div class="modal" style="width:460px;">
                    <button class="hk-back" id="hkBack">‹ All helpers</button>
                    <h2 class="modal-title">${kind.icon}&nbsp; ${this._esc(kind.name)}</h2>
                    <p class="hk-flow">This one is not stored as a simple helper. Home Assistant builds it with a setup flow of its own, which asks for entities, templates or ranges and validates each answer against the integration behind it. That flow only exists inside the Home Assistant frontend, so LIBI cannot run it and will not pretend to.</p>
                    <p class="hk-note">Open the helpers page once and press Create helper there. From then on this button opens the real dialog of Home Assistant inside LIBI, for this kind and every other.</p>
                    <div class="modal-actions">
                        <button class="btn btn-ghost" id="closeModalBtn">Cancel</button>
                        <button class="btn" id="hkMore">Open the helpers page</button>
                    </div>
                </div></div>`;
            }

            const field = (f) => {
                const s = spec[f];
                const v = this._hkForm[f];
                if (s.type === 'week') return this._hkWeekHtml();
                if (s.type === 'bool') {
                    return `<div class="fgrp checkbox-grp"><input type="checkbox" class="hk-f" data-k="${f}" ${v ? 'checked' : ''} />
                            <label style="margin:0;">${s.label}</label></div>`;
                }
                if (s.type === 'lines') {
                    return `<div class="fgrp"><label>${s.label}</label>
                            <textarea class="hk-f" data-k="${f}" rows="4" dir="auto">${this._esc(v)}</textarea></div>`;
                }
                if (s.type === 'select') {
                    return `<div class="fgrp"><label>${s.label}</label><select class="hk-f" data-k="${f}">
                            ${s.choices.map(([val, lab]) => `<option value="${val}" ${v === val ? 'selected' : ''}>${lab}</option>`).join('')}
                            </select></div>`;
                }
                return `<div class="fgrp"><label>${s.label}${s.optional ? ' <span style="font-weight:400;color:var(--secondary-text-color, #9e9e9e);">optional</span>' : ''}</label>
                        <input type="${s.type === 'number' ? 'number' : 'text'}" class="hk-f" data-k="${f}" value="${this._esc(v)}" placeholder="${this._esc(s.hint || '')}" dir="auto" /></div>`;
            };

            // Two numbers that belong together sit on one line, the way the dialog of Home Assistant
            // lays them out.
            const fields = (kind.fields || []).slice();
            const out = [];
            while (fields.length) {
                const f = fields.shift();
                const pair = { min: 'max', minimum: 'maximum' }[f];
                if (pair && fields[0] === pair) {
                    fields.shift();
                    out.push(`<div class="hk-row">${field(f)}${field(pair)}</div>`);
                } else out.push(field(f));
            }

            return `<div class="modal-overlay" id="modalOverlay"><div class="modal" style="width:470px;">
                <button class="hk-back" id="hkBack">‹ All helpers</button>
                <h2 class="modal-title">${kind.icon}&nbsp; ${this._esc(kind.name)}</h2>
                <div class="hk-form">
                    <div class="fgrp"><label>Name</label><input type="text" id="hkName" value="${this._esc(this._hkForm.name || '')}" dir="auto" placeholder="Boiler on" /></div>
                    ${out.join('')}
                </div>
                <div class="modal-actions">
                    <button class="btn btn-ghost" id="closeModalBtn">Cancel</button>
                    <button class="btn" id="hkCreate">Create</button>
                </div>
            </div></div>`;
        }

        // Step one: the list, in the order Home Assistant lists them.
        const q = String(this._hkQuery || '').trim().toLowerCase();
        const all = this.HELPER_KINDS().filter(k => !q || k.name.toLowerCase().includes(q) || k.domain.includes(q));
        const items = all.map(k => `<div class="hk-item hk-kind${k.flow ? ' flow' : ''}" data-d="${k.domain}" title="${k.flow ? 'Built by a setup flow of Home Assistant' : 'Created straight away'}">
                <span class="i">${k.icon}</span><span class="n">${this._esc(k.name)}</span><span class="c">›</span>
            </div>`).join('');
        return `<div class="modal-overlay" id="modalOverlay"><div class="modal" style="width:470px;">
            <h2 class="modal-title">Create helper</h2>
            <div class="fgrp"><input type="text" id="hkSearch" placeholder="Search for a helper" value="${this._esc(this._hkQuery)}" dir="auto" /></div>
            <div class="hk-list">${items || '<div class="vars-empty" style="padding:16px;">Nothing matches that.</div>'}</div>
            <div class="modal-actions"><button class="btn btn-ghost" id="closeModalBtn">Close</button></div>
        </div></div>`;
    }

    // [ADDED v3.23.0] The week of a Schedule: a row per day with a switch and a span of time.
    _hkWeekHtml() {
        const week = this._hkForm.week || {};
        return `<div class="fgrp"><label>Days</label><div class="hk-days">
            ${this.WEEK_DAYS().map(([key, label]) => {
                const row = week[key] || { on: false, from: '08:00', to: '17:00' };
                return `<div class="hk-day${row.on ? '' : ' off'}">
                    <input type="checkbox" class="hk-day-on" data-d="${key}" ${row.on ? 'checked' : ''} />
                    <span class="d">${this._esc(label)}</span>
                    <input type="time" class="hk-day-t" data-d="${key}" data-e="from" value="${this._esc(row.from)}" />
                    <span class="to">to</span>
                    <input type="time" class="hk-day-t" data-d="${key}" data-e="to" value="${this._esc(row.to)}" />
                </div>`;
            }).join('')}
        </div></div>`;
    }

    _applyVarsSize() {
        const host = this.shadowRoot && this.shadowRoot.querySelector('.panel-layout');
        if (host) host.style.setProperty('--libi-vars-h', this._varsH + 'px');
        const bar = this.shadowRoot && this.shadowRoot.getElementById('varsBar');
        if (bar) bar.classList.toggle('rail', !this._varsOpen);
    }

    _saveVars() {
        try {
            localStorage.setItem('libi_vars_h', String(this._varsH));
            localStorage.setItem('libi_vars_open', this._varsOpen ? '1' : '0');
        } catch (err) { /* storage unavailable */ }
    }

    // The grip sits on the top edge, so dragging up makes the bar taller.
    _bindVarsGrip() {
        const sr = this.shadowRoot;
        const grip = sr.getElementById('varsGrip');
        const bar = sr.getElementById('varsBar');
        if (!grip || !bar) return;
        let startY = 0, startH = 0;
        const move = (ev) => {
            const next = startH + (startY - ev.clientY);
            this._varsH = Math.min(Math.round(window.innerHeight * 0.78), Math.max(120, Math.round(next)));
            this._applyVarsSize();
        };
        const up = (ev) => {
            grip.classList.remove('active');
            bar.classList.remove('dragging');
            try { grip.releasePointerCapture(ev.pointerId); } catch (err) { /* already released */ }
            grip.removeEventListener('pointermove', move);
            grip.removeEventListener('pointerup', up);
            grip.removeEventListener('pointercancel', up);
            this._saveVars();
        };
        grip.addEventListener('pointerdown', (ev) => {
            if (!this._varsOpen) return;
            ev.preventDefault();
            startY = ev.clientY; startH = this._varsH;
            grip.classList.add('active');
            bar.classList.add('dragging');
            try { grip.setPointerCapture(ev.pointerId); } catch (err) { /* fall back to bubbling */ }
            grip.addEventListener('pointermove', move);
            grip.addEventListener('pointerup', up);
            grip.addEventListener('pointercancel', up);
        });
        grip.addEventListener('dblclick', () => { this._varsH = 280; this._saveVars(); this._applyVarsSize(); });
    }

    async _varsRefreshIds() {
        if (!this._hass || !this._hass.connection) return;
        const next = {};
        await Promise.all(HELPER_DOMAINS.map(async (domain) => {
            next[domain] = {};
            try {
                const res = await this._hass.connection.sendMessagePromise({ type: `${domain}/list` });
                const items = Array.isArray(res) ? res : (res && res.items) || [];
                items.forEach(it => { if (it && it.id) next[domain][String(it.id)] = String(it.id); });
            } catch (err) { /* the domain is not loaded in this installation */ }
        }));
        this._helperIds = next;
        await this._loadSchedules(false);  // [ADDED v3.71.0] a schedule changed here shows its new days and hours
    }

    async _varsCreate() {
        const name = String(this._varsNewName || '').trim();
        if (!name) { alert('A variable needs a name.'); return; }
        const spec = VAR_TYPES[this._varsNewType] || VAR_TYPES.BOOL;
        try {
            await this._hass.connection.sendMessagePromise({ type: `${spec.domain}/create`, name, ...(spec.defaults || {}) });
            // Remember it against the net that is open, so it is listed there before it is placed.
            const net = this._currentNet();
            const guessed = `${spec.domain}.${name.toLowerCase().trim().replace(/[^a-z0-9_]+/g, '_').replace(/^_+|_+$/g, '')}`;
            if (net) { net.vars = net.vars || []; if (!net.vars.includes(guessed)) net.vars.push(guessed); this._projectDirty = true; }
            this._varsNewName = '';
            await this._varsRefreshIds();
            this._render();
        } catch (err) {
            alert('Could not create the variable: ' + (err && err.message ? err.message : err));
        }
    }

    // Changing the type. Within one domain this is a real update and the entity keeps its id and its
    // history. Across domains Home Assistant has no such thing as a conversion, so the only way is to
    // remove and remake, which gives a new entity id and breaks whatever pointed at the old one. That
    // is said plainly before anything happens rather than discovered afterwards.
    async _varsChangeType(entityId, nextKey) {
        const current = varTypeOf(entityId, this._hass);
        if (current === nextKey) return;
        const spec = VAR_TYPES[nextKey];
        const domain = entityId.split('.')[0];
        const objectId = entityId.split('.').slice(1).join('.');
        // [CHANGED v3.86.0] Home Assistant's own name: a name given in LIBI only is never sent to Home Assistant.
        const name = this.core.haName(entityId, this._hass) || objectId;

        if (spec.domain === domain) {
            try {
                await this._hass.connection.sendMessagePromise({
                    type: `${domain}/update`, [`${domain}_id`]: objectId, name, ...(spec.defaults || {}),
                });
                this._render();
                return;
            } catch (err) {
                alert('Could not change the type: ' + (err && err.message ? err.message : err));
                this._render();
                return;
            }
        }

        const ok = confirm(
            `${name} is a ${current} and you are asking for a ${nextKey}.\n\n` +
            `Home Assistant cannot convert one kind of helper into another. LIBI would have to delete ` +
            `${entityId} and create a new one, which means a new entity id, no history, and every ` +
            `rung or automation still pointing at the old id would break.\n\nDo it anyway?`);
        if (!ok) { this._render(); return; }
        try {
            await this._deleteHelperItem(domain, objectId);  // [CHANGED v3.77.0] the one copy of the delete
            await this._hass.connection.sendMessagePromise({ type: `${spec.domain}/create`, name, ...(spec.defaults || {}) });
            await this._varsRefreshIds();
            this._render();
        } catch (err) {
            alert('The change did not finish: ' + (err && err.message ? err.message : err));
            await this._varsRefreshIds();
            this._render();
        }
    }

    async _varsDelete(entityId) {
        const domain = entityId.split('.')[0];
        const objectId = entityId.split('.').slice(1).join('.');
        const nm = this.core.friendlyName(entityId, this._hass) || entityId;
        if (!confirm(`Delete ${nm}?\n\nThis removes the variable from Home Assistant. Anything still pointing at it will break.`)) return;
        try {
            await this._deleteHelperItem(domain, objectId);
        } catch (err) {
            alert('Could not delete the variable: ' + (err && err.message ? err.message : err));
            return;
        }
        (this.core.nets || []).forEach(n => { if (n.vars) n.vars = n.vars.filter(v => v !== entityId); });
        await this._varsRefreshIds();
        this._render();
    }

    // [CHANGED v3.77.0] One helper deleted with Home Assistant's own command (admin only), for the variables bar (a delete,
    // a change of type) and for the variables of a NET. Every helper LIBI lists takes ${domain}_id; the other two keys are what earlier versions
    // tried as well. The first error is the one that says why.
    async _deleteHelperItem(domain, itemId) {
        let firstErr = null;
        for (const key of [`${domain}_id`, 'item_id', 'id']) {
            try { await this._hass.connection.sendMessagePromise({ type: `${domain}/delete`, [key]: itemId }); return; }
            catch (err) { if (!firstErr) firstErr = err; }
        }
        throw firstErr;
    }

    // [ADDED v3.77.0] The local variables of a NET - the helpers it uses that nothing else uses (libi/net_helpers) -
    // which deleting the NET offers to delete too, the user's request. deleting: the id of its automation being
    // deleted, the one user that does not count. null when the check could not be made: then nothing is offered.
    async _netHelpers(net, deleting = '') {
        if (!net || !this._hass || !this._hass.connection) return null;
        try {
            const res = await this._hass.connection.sendMessagePromise({
                type: 'libi/net_helpers', net, nets: (this.core.nets || []).filter(n => n !== net),
                slug: this._project ? this._project.slug : 'default', automation_id: deleting || '' });
            return res && !res.error ? res : null;
        } catch (err) {
            return null;
        }
    }

    // [ADDED v3.77.0] The question about them, or '' when there is none to delete. Plain text (a confirm), so the names
    // from Home Assistant need no escaping.
    _netHelpersQuestion(net, local) {
        const helpers = (local && local.helpers) || [];
        if (!net || !helpers.length) return '';
        const line = h => `  • ${h.name || h.entity_id} (${h.entity_id})`;
        let text = `Also delete the local variables of NET ${(this.core.nets || []).indexOf(net) + 1} "${net.name || ''}"?\n\n`
            + `No other automation, script, scene, group or NET uses them, so they are removed from Home Assistant's helpers:\n`
            + helpers.map(line).join('\n');
        if ((local.kept || []).length) text += `\n\nKept:\n${local.kept.map(h => `${line(h)} - ${h.reason}`).join('\n')}`;
        return text + '\n\nNot checked: dashboard cards and template entities that show them - they will show them as unavailable.'
            + '\nOK deletes them. Cancel keeps them.';
    }

    // [ADDED v3.77.0] Deletes the variables the user agreed to, once the NET is gone: asked again now, the NET's own
    // automation no longer left out, so each one goes only if nothing - that automation included - uses it any more.
    async _deleteNetHelpers(net, picked) {
        const now = await this._netHelpers(net);
        if (!now) return 'Its variables were kept: LIBI could not check that nothing else uses them.';
        const done = [], kept = [], failed = [];
        for (const id of picked) {
            const helper = (now.helpers || []).find(h => h.entity_id === id);
            if (!helper) {
                const used = (now.kept || []).find(h => h.entity_id === id);
                kept.push(`${id} (${used ? used.reason : 'no longer in Home Assistant'})`);
                continue;
            }
            try { await this._deleteHelperItem(helper.domain, helper.item_id); done.push(helper.name || id); }
            catch (err) { failed.push(`${id} (${err && err.message ? err.message : err})`); }
        }
        await this._varsRefreshIds();
        this._render();
        return [done.length ? `Deleted ${done.length} variable${done.length === 1 ? '' : 's'}: ${done.join(', ')}.` : '',
            kept.length ? `Kept: ${kept.join(', ')}.` : '',
            failed.length ? `Could not delete: ${failed.join(', ')}.` : ''].filter(Boolean).join('\n');
    }

    // Dropping a variable onto a block. A pin takes it in that pin's own field, and the block itself
    // takes it wherever that kind of block keeps its entity.
    _applyDroppedVar(entityId, netId, rungId, elId, prop) {
        const el = this.core.findEl(netId, rungId, elId);
        if (!el) return false;
        const type = String(el.type || '');
        let field = prop;
        if (!field) {
            if (type.startsWith('coil') || type.startsWith('contact') || type === 'wait') field = 'label';
            else if (type.startsWith('cmp')) field = 'sourceA';
            else if (type === 'move') field = (el.mode || 'value') === 'value' ? 'target' : 'target';
            else if (type === 'ctu') field = 'source';
            else field = 'label';
        }
        el[field] = entityId;
        if (field === 'label' || field === 'target') {
            el.targetSpec = { entity_id: [entityId] };
            el.targetKind = 'entity';
            el.targetLabel = entityId;
        }
        this.core.pushHistory();
        this._projectDirty = true;
        return true;
    }

    // [ADDED v3.14.0] The name of the open workspace, or a note that none is open.
    _projectChipHtml() {
        if (!this._project) {
            return `<span class="project-chip none${this._varsScope === 'project' ? ' on' : ''}" id="projectChip" role="button" tabindex="0" title="No project is open. Open one, or make a new one, from the menu on the right. Click to show the variables of every NET on the canvas."><span class="dot"></span><span class="nm">No project</span></span>`;
        }
        const dirty = this._hasUnsavedChanges() ? '<span class="dirty" title="There are unsaved changes">●</span>' : '';
        return `<span class="project-chip${this._varsScope === 'project' ? ' on' : ''}" id="projectChip" role="button" tabindex="0" title="Project ${this._esc(this._project.name)} — stored as ${this._esc(this._project.slug)}.libi. Click to show the variables of all its NETs."><span class="dot"></span><span class="nm">${this._esc(this._project.name)}</span>${dirty}</span>`;
    }

    _rememberProject() {
        try {
            if (this._project) localStorage.setItem('libi_project', JSON.stringify(this._project));
            else localStorage.removeItem('libi_project');
        } catch (err) { /* storage is unavailable, the session still works */ }
    }

    async _projectRefreshList() {
        if (!this._hass || !this._hass.connection) return [];
        try {
            const res = await this._hass.connection.sendMessagePromise({ type: 'libi/project_list' });
            this._projectList = (res && res.projects) || [];
        } catch (err) {
            console.error('LIBI could not list projects', err);
            this._projectList = [];
        }
        return this._projectList;
    }

    // Opening a project replaces the canvas wholesale. Every net comes back exactly as it was left,
    // unfinished logic included, together with the automation each one was loaded from.
    async _projectOpen(slug) {
        // [CHANGED v3.85.0] Leaving a workspace with changes not saved asks Yes or No (the user's rule, 2026-11-04).
        if (!(await this._leaveCheck())) return;
        try {
            const res = await this._hass.connection.sendMessagePromise({ type: 'libi/project_open', slug });
            this.core.nets = res.nets || [];
            this.core.repairAST();
            this.core.resetHistory ? this.core.resetHistory() : this.core.pushHistory();
            this._project = { slug: res.slug, name: res.name };
            this._versions = res.versions || {};
            this._markSaved();
            this._inspectedEl = null;
            this._selectedNetId = null;
            this._modal = null;
            this._rememberProject();
            // [ADDED v3.87.0] A name given in LIBI from another page since this one started is shown here too.
            await this._loadLocalNames();
            await this._loadPhones();
            await this._loadGlobal();
            this._render();
            const s = res.stats || {};
            if (s.orphan) {
                alert(`${s.orphan} net${s.orphan === 1 ? '' : 's'} in this project point at an automation that is no longer in Home Assistant. The saved drawing is shown for ${s.orphan === 1 ? 'it' : 'them'} instead.`);
            }
        } catch (err) {
            alert('Could not open the project: ' + (err && err.message ? err.message : err));
        }
    }

    async _projectCreate(name) {
        // [ADDED v3.85.0] A new project leaves the one open: changes not saved are asked about first.
        if (!(await this._leaveCheck())) return;
        try {
            const res = await this._hass.connection.sendMessagePromise({ type: 'libi/project_create', name });
            this.core.nets = [];
            this.core.pushHistory();
            this._project = { slug: res.slug, name: res.name };
            this._versions = {};
            this._markSaved();
            this._selectedNetId = null;
            this._modal = null;
            this._rememberProject();
            this._render();
        } catch (err) {
            alert('Could not create the project: ' + (err && err.message ? err.message : err));
        }
    }

    async _projectDelete(slug) {
        try {
            const res = await this._hass.connection.sendMessagePromise({ type: 'libi/project_delete', slug });
            if (this._project && this._project.slug === slug) {
                this._project = null;
                this.core.nets = [];
                this.core.pushHistory();
                this._rememberProject();
                this._markSaved();
            }
            this._modal = null;
            this._render();
            alert(res.message || 'The project file was deleted.');
        } catch (err) {
            alert('Could not delete the project: ' + (err && err.message ? err.message : err));
        }
    }

    // [CHANGED v3.85.0] Closing with changes not saved asks Yes or No - the user's rule (2026-11-04). Until 3.84.0 closing
    // wrote the workspace out, and Home Assistant's files with it, without a word.
    async _projectClose() {
        if (!(await this._leaveCheck())) return;
        this._project = null;
        this.core.nets = [];
        this.core.pushHistory();
        this._markSaved();
        this._inspectedEl = null;
        this._selectedNetId = null;
        this._rememberProject();
        this._render();
    }

    // [ADDED v3.13.0] A ghost icon button in the Home Assistant shape.
    _iconBtn(id, path, title, cls = '') {
        return `<button class="ha-icon-btn${cls ? ' ' + cls : ''}" id="${id}" title="${this._esc(title)}"><svg viewBox="0 0 24 24"><path d="${path}"></path></svg></button>`;
    }

    // [ADDED v3.13.0] The automation entity that belongs to a net. The link is the id, not the
    // entity_id, because Home Assistant builds the entity_id from the alias and it drifts when the
    // net is renamed, while the id written into automations.yaml stays put.
    _automationOf(net) {
        const h = this._hass;
        const id = String((net && net.ha_id) || '');
        if (!h || !h.states || !id) return null;
        for (const eid of Object.keys(h.states)) {
            if (!eid.startsWith('automation.')) continue;
            const st = h.states[eid];
            if (st && st.attributes && String(st.attributes.id || '') === id) return st;
        }
        return null;
    }

    _netHasTrigger(net) {
        const walk = (els) => (els || []).some(el =>
            el.isTrigger || (el.type === 'parallel' && (el.branches || []).some(walk)));
        return (net.rungs || []).some(r => walk(r.elements));
    }

    // [ADDED v3.13.0] The state of a net, in the terms Home Assistant uses. on means the triggers
    // are armed, off means they are disabled. A script and a scene have no such state, and neither
    // does an automation that was never compiled, so those get no switch at all.
    // [ADDED v3.15.0] Does any block of this net carry a structural error right now.
    _netHasErrors(net) {
        const walk = (els) => (els || []).some(el => el.structuralError
            || (el.type === 'parallel' && (el.branches || []).some(walk))
            || (el.type === 'repeat' && walk(el.sequence)));
        return (net.rungs || []).some(r => walk(r.elements));
    }

    _netState(net) {
        if (this.core.netLevel(net) !== 'automation') return { show: false };
        if (!this._netHasTrigger(net)) return { show: false };
        const st = this._automationOf(net);
        if (!st) {
            return { show: true, on: false, ready: false, entity: '',
                     tip: 'Save and compile first. Home Assistant creates the automation entity, and only then can its triggers be armed or disabled.' };
        }
        if (st.state === 'unavailable' || st.state === 'unknown') {
            return { show: true, on: false, ready: false, entity: st.entity_id,
                     tip: `${st.entity_id} is ${st.state} right now.` };
        }
        const on = st.state === 'on';
        // [ADDED v3.15.0] An automation that does not lint cannot be armed. Disabling one is always
        // allowed, because switching off something broken should never be blocked.
        const broken = this._netHasErrors(net);
        if (broken && !on) {
            return { show: true, on: false, ready: false, entity: st.entity_id, broken: true,
                     tip: 'This net has errors, so its triggers cannot be armed. Fix the red blocks first.' };
        }
        return { show: true, on, ready: true, entity: st.entity_id, broken,
                 tip: broken
                    ? `Armed, but this net has errors. ${st.entity_id}`
                    : (on ? `Triggers armed. ${st.entity_id}` : `Triggers disabled, the automation will not run. ${st.entity_id}`) };
    }

    _netStateHtml(net) {
        const s = this._netState(net);
        if (!s.show) return '';
        const cls = s.ready ? 'ha-switch' : 'ha-switch disabled';
        return `<div class="net-state-wrap" title="${this._esc(s.tip)}">
            <label class="${cls}" data-nid="${net.id}" data-entity="${this._esc(s.entity)}">
                <input type="checkbox" class="net-state-toggle" data-nid="${net.id}" data-entity="${this._esc(s.entity)}" data-broken="${s.broken ? '1' : '0'}" ${s.on ? 'checked' : ''} ${s.ready ? '' : 'disabled'} />
                <span class="track"></span><span class="knob"></span>
            </label>
        </div>`;
    }

    _readFlag(key) {
        try { return localStorage.getItem(key) === '1'; }
        catch (err) { return false; }
    }

    _readNum(key, fallback, lo, hi) {
        try {
            const raw = parseInt(localStorage.getItem(key), 10);
            if (!isNaN(raw)) return Math.min(hi, Math.max(lo, raw));
        } catch (err) { /* private mode, or storage disabled */ }
        return fallback;
    }

    _saveSidebar() {
        try {
            localStorage.setItem('libi_sidebar_w', String(this._sidebarW));
            localStorage.setItem('libi_sidebar_h', String(this._sidebarH));
            localStorage.setItem('libi_sidebar_rail', this._sidebarRail ? '1' : '0');
        } catch (err) { /* nothing to do, the session still works */ }
    }

    // [ADDED v3.12.0] Anything that puts new content in the sidebar calls this. A closed sidebar
    // opens back to the width that was saved, not to some default, so clicking an element always
    // shows it at the size the user last chose.
    _wakeSidebar() {
        // [ADDED v3.46.0] The open AI chat fills the whole sidebar and hides the Inspector, so new
        // Inspector content (a clicked element, a net's YAML) closes the chat and shows it.
        if (this.aiChat && this.aiChat.open) this.aiChat.setOpen(false);
        if (!this._sidebarRail) return;
        this._sidebarRail = false;
        this._saveSidebar();
    }

    _applySidebarSize() {
        const host = this.shadowRoot && this.shadowRoot.querySelector('.panel-layout');
        if (host) {
            host.style.setProperty('--libi-sidebar-w', this._sidebarW + 'px');
            host.style.setProperty('--libi-sidebar-h', this._sidebarH + 'px');
        }
        const bar = this.shadowRoot && this.shadowRoot.getElementById('sidebarContainer');
        if (bar) bar.classList.toggle('rail', this._sidebarRail);
    }

    // [ADDED v3.12.0] Pointer events rather than mouse events, so the grip works with a finger and
    // with a pen as well as with a mouse, and a single capture keeps the drag alive over the canvas.
    _bindSidebarGrip() {
        const sr = this.shadowRoot;
        const grip = sr.getElementById('sidebarGrip');
        const bar = sr.getElementById('sidebarContainer');
        if (!grip || !bar) return;

        const vertical = () => window.innerWidth <= 768;
        let startPos = 0, startSize = 0;

        const move = (ev) => {
            if (vertical()) {
                const next = startSize + (startPos - ev.clientY);
                this._sidebarH = Math.min(Math.round(window.innerHeight * 0.8), Math.max(160, Math.round(next)));
            } else {
                const next = startSize + (startPos - ev.clientX);
                this._sidebarW = Math.min(this.SIDEBAR_MAX, Math.max(this.SIDEBAR_MIN, Math.round(next)));
            }
            this._applySidebarSize();
        };
        const up = (ev) => {
            grip.classList.remove('active');
            bar.classList.remove('dragging');
            try { grip.releasePointerCapture(ev.pointerId); } catch (err) { /* already released */ }
            grip.removeEventListener('pointermove', move);
            grip.removeEventListener('pointerup', up);
            grip.removeEventListener('pointercancel', up);
            this._saveSidebar();
        };

        grip.addEventListener('pointerdown', (ev) => {
            if (this._sidebarRail) return;
            ev.preventDefault();
            startPos = vertical() ? ev.clientY : ev.clientX;
            startSize = vertical() ? this._sidebarH : this._sidebarW;
            grip.classList.add('active');
            bar.classList.add('dragging');
            try { grip.setPointerCapture(ev.pointerId); } catch (err) { /* fall back to bubbling */ }
            grip.addEventListener('pointermove', move);
            grip.addEventListener('pointerup', up);
            grip.addEventListener('pointercancel', up);
        });

        // A double click on the grip goes back to the width the panel ships with.
        grip.addEventListener('dblclick', () => {
            this._sidebarW = 320;
            this._sidebarH = 320;
            this._saveSidebar();
            this._applySidebarSize();
        });
    }

    _lblStyle(el) {
        const w = this.core.labelWidth(el);
        return `width:${w}px;max-width:${w}px;`;
    }

    _elBody(el, errs) {
        // [ADDED v3.86.0] A pin shows the entity id, or the name the user gave it in LIBI; the hover keeps the id.
        // [CHANGED v3.88.0] A recipient of LIBI Global by its name there: its script's id says nothing of whose it is.
        const pinShown = (v) => {
            if (typeof v !== 'string') return v;
            const recipient = this.core.recipientOf(v);
            const local = this.core.localName(v) || (recipient ? recipient.name : '');
            return local ? local + ((v.match(/\s*\+\d+$/) || [''])[0]) : v;
        };
        const varPin = (side, name, val, errClass, propName, extra = '') => {
            if (!name && val === null) return `<div class="plc-col-${side} empty"></div>`;
            return `
                <div class="plc-col-${side} ${extra} ${errClass ? 'has-error' : ''}">
                    ${name ? `<span class="pin-lbl">${this._esc(name)}</span>` : ''}
                    ${val !== null ? `<div class="pin-val ${errClass ? 'has-error' : ''}" data-prop="${propName}" title="${this._esc(val)}" dir="auto">${this._formatDisplayVal(pinShown(val))}</div>` : ''}
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
                    ${varPin('l', 'IN', clockIn1(String(el.sourceA || '')) || el.sourceA || '?', errs.srcA, 'sourceA', clockIn1(String(el.sourceA || '')) ? 'clock' : '')}
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
            // [ADDED v3.71.0] A schedule on IN2: the days and hours it holds, which the clock is compared with.
            const week = aSide === 'datetime' && String(el.sourceB || '').startsWith('schedule.') ? this._scheduleText(el.sourceB) : '';
            const clock = clockIn1(aSide);  // [ADDED v3.77.0] datetime.time.now / datetime.day.now
            innerBody = `
            <div class="plc-block">
                <div class="plc-header">${heading === `CMP ${op}` ? heading : heading + ' ' + op}</div>
                <div class="power-row"><div class="pin-lbl">EN</div><div class="pin-lbl">ENO</div></div>
                <div class="plc-row">
                    ${varPin('l', 'IN1', clock || el.sourceA || '?', errs.srcA, 'sourceA', clock ? 'clock' : '')}
                    ${varPin('r', '', null, false, '')}
                </div>
                <div class="plc-row">
                    ${varPin('l', 'IN2', el.sourceB || '?', errs.srcB, 'sourceB')}
                    ${varPin('r', '', null, false, '')}
                </div>
                ${week ? `<div class="plc-note" dir="ltr" title="${this._esc(week)}">${this._esc(week)}</div>` : ''}
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
            // [CHANGED v3.68.0] el.type: there is no `type` here, so a block with no icon of its own (an old Send
            // Notification) threw and stopped the whole canvas from drawing.
            let svgKey = LIBI_ICONS[el.type] ? el.type
                       : (el.type.startsWith('contact') ? 'contact_no' : (el.type.startsWith('coil') ? 'coil' : 'custom'));
            
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

    // [CHANGED v3.15.2] Every group of bindings is wrapped. One failure used to abort the method
    // and leave the whole panel dead with nothing in the console pointing at the cause. Now the
    // failure is named and everything after it still gets wired.
    _bindEvents() {
        const groups = [];
        this._bindGroup = (label, fn) => {
            try { fn(); } catch (err) {
                console.error(`[LIBI ${LIBI_BUILD}] the "${label}" bindings failed and those controls will not respond:`, err);
                groups.push(label);
            }
        };
        try { this._bindEventsInner(); } catch (err) {
            console.error(`[LIBI ${LIBI_BUILD}] _bindEvents stopped early, controls after this point are dead:`, err);
        }
        if (groups.length) console.error(`[LIBI ${LIBI_BUILD}] broken binding groups:`, groups.join(', '));
    }

    _bindEventsInner() {
        const sr = this.shadowRoot;

        // [FIXED v3.15.1] These two helpers are declared first and nowhere else. They used to sit in
        // the middle of this method, so any binding added above them threw a temporal dead zone
        // ReferenceError on the first call, which aborted the whole method and left every single
        // button in the panel dead. Declaring them at the top makes that impossible.
        const on = (id, ev, fn) => { 
            const el = sr.getElementById(id); 
            if (el) el.addEventListener(ev, fn); 
        };
        
        const all = (sel, ev, fn) => {
            sr.querySelectorAll(sel).forEach(el => el.addEventListener(ev, fn));
        };
        

        // [ADDED v3.12.0] The size is applied from state on every render, so a resize survives a
        // redraw, and the button flips between the saved width and the 40 pixel rail.
        this._applySidebarSize();
        this._bindSidebarGrip();
        this._applyVarsSize();
        this._bindVarsGrip();
        // [CHANGED v3.17.0] The bar of variables along the bottom: two tabs, the scope and type
        // filters, editing a type in the table, and dragging a row onto a block.
        // [ADDED v3.32.0] The entity chooser.
        this._bindGroup('entity picker', () => {
            on('epTabTarget', 'click', (e) => { e.stopPropagation(); this._epTab = 'target'; this._render(); });
            on('epTabType', 'click', (e) => { e.stopPropagation(); this._epTab = 'type'; this._render(); });
            all('.ep-fold', 'click', e => {
                e.stopPropagation();
                const k = e.currentTarget.getAttribute('data-k');
                this._epOpen[k] = !this._epOpen[k];
                // [FIXED v3.33.0] Opening a group rebuilt the list and threw the view back to the
                // top, so the group that had just been opened was off screen and had to be scrolled
                // back to. The position is carried across the redraw.
                const body = sr.querySelector('.ep-body');
                this._epScroll = body ? body.scrollTop : 0;
                this._render();
            });
            all('.ep-pick', 'click', e => {
                e.stopPropagation();
                this._applyPickedEntity(e.currentTarget.getAttribute('data-eid'));
            });
            all('.ep-kind', 'click', e => {
                e.stopPropagation();
                this._applyTriggerKind(e.currentTarget.getAttribute('data-k'));
            });
            // Put the view back where it was before the redraw.
            const epBody = sr.querySelector('.ep-body');
            if (epBody && this._epScroll) { epBody.scrollTop = this._epScroll; this._epScroll = 0; }

            const es = sr.getElementById('epSearch');
            if (es) {
                es.addEventListener('click', e => e.stopPropagation());
                es.addEventListener('input', (e) => {
                    this._epQuery = e.target.value;
                    clearTimeout(this._epTimer);
                    this._epTimer = setTimeout(() => {
                        this._render();
                        const box = this.shadowRoot.getElementById('epSearch');
                        if (box) { box.focus(); box.setSelectionRange(box.value.length, box.value.length); }
                    }, 200);
                });
                es.focus();
            }
            // Clicking the name written above a block opens the chooser for that block.
            all('.el-lbl', 'click', e => {
                const block = e.currentTarget.closest('.libi-el');
                if (!block) return;
                e.stopPropagation();
                this._openEntityPicker(block.getAttribute('data-nid'),
                    block.getAttribute('data-rid'), block.getAttribute('data-eid'), null);
            });
        });

        // [ADDED v3.28.0] The right click menu on the name of a block.
        this._bindGroup('rename menu', () => {
            // [CHANGED v3.86.0] The same menu on a pin that holds an entity (IN1, IN2, OUT, ...): the variables inside a
            // block had none, so they could not be renamed - the user's report (2026-11-04).
            const openCtx = (e, block, eid, prop) => {
                if (!/^[a-z_][a-z0-9_]*\.[a-z0-9_]+$/.test(eid)) return;  // nothing to rename
                e.preventDefault();
                e.stopPropagation();
                // [CHANGED v3.86.0] Where the click was; _placeCtxMenu keeps it on the screen by its real size.
                this._ctx = { entityId: eid, x: e.clientX, y: e.clientY, prop,
                              netId: block.getAttribute('data-nid'), rungId: block.getAttribute('data-rid'),
                              elId: block.getAttribute('data-eid') };
                this._render();
            };
            const elOf = (block) => this.core.findEl(block.getAttribute('data-nid'),
                block.getAttribute('data-rid'), block.getAttribute('data-eid'));
            all('.el-lbl', 'contextmenu', e => {
                const block = e.currentTarget.closest('.libi-el');
                if (!block) return;
                const el = elOf(block);
                openCtx(e, block, String((el && (el.label || el.target)) || '').replace(/\s*\+\d+$/, '').trim(), null);
            });
            all('.pin-val[data-prop]', 'contextmenu', e => {
                const block = e.currentTarget.closest('.libi-el');
                const prop = e.currentTarget.getAttribute('data-prop');
                if (!block || !prop || prop === 'null') return;
                const el = elOf(block);
                const val = el ? el[prop] : '';
                openCtx(e, block, typeof val === 'string' ? val.replace(/\s*\+\d+$/, '').trim() : '', prop);
            });
            on('ctxChange', 'click', (e) => {
                e.stopPropagation();
                const c = this._ctx;
                this._ctx = null;
                if (c) this._openEntityPicker(c.netId, c.rungId, c.elId, c.prop || null);
            });
            on('ctxRename', 'click', (e) => {
                e.stopPropagation();
                this._renameFor = this._ctx ? this._ctx.entityId : '';
                this._renameFrom = this._ctx && this._ctx.prop ? 'pin' : 'label';
                this._renameTo = this.core.friendlyName(this._renameFor, this._hass) || '';
                this._ctx = null;
                this._modal = 'rename_entity';
                this._render();
            });
            on('ctxMoreInfo', 'click', (e) => {
                e.stopPropagation();
                const eid = this._ctx ? this._ctx.entityId : '';
                this._ctx = null;
                this._render();
                if (eid) this.dispatchEvent(new CustomEvent('hass-more-info', {
                    bubbles: true, composed: true, detail: { entityId: eid } }));
            });
            on('ctxCopy', 'click', (e) => {
                e.stopPropagation();
                try { navigator.clipboard.writeText(this._ctx.entityId); } catch (err) { /* refused */ }
                this._ctx = null;
                this._render();
            });
            const ri = sr.getElementById('renameInput');
            if (ri) {
                ri.addEventListener('input', ev => { this._renameTo = ev.target.value; });
                // [CHANGED v3.86.0] Enter is the dialog's first choice: in Home Assistant, or in LIBI only.
                ri.addEventListener('keydown', ev => {
                    if (ev.key !== 'Enter') return;
                    if (this._renameInHaFirst()) this._doRename();
                    else this._doRenameLocal();
                });
                ri.focus();
            }
            on('renameOk', 'click', (e) => { e.stopPropagation(); this._doRename(); });
            // [ADDED v3.86.0] A name in LIBI only, and taking it away again.
            on('renameLocal', 'click', (e) => { e.stopPropagation(); this._doRenameLocal(); });
            on('renameLocalClear', 'click', (e) => { e.stopPropagation(); this._renameTo = ''; this._doRenameLocal(); });
        });

        this._bindGroup('variables bar', () => {
            on('varsFold', 'click', (e) => {
                e.stopPropagation();
                this._varsOpen = !this._varsOpen;
                this._saveVars();
                if (this._varsOpen) this._varsRefreshIds().then(() => this._render());
                else this._render();
            });
            on('varsTabHelper', 'click', (e) => { e.stopPropagation(); this._varsTab = 'helper'; this._varsOpen = true; this._saveVars(); this._render(); });
            on('varsTabVars', 'click', (e) => { e.stopPropagation(); this._varsTab = 'vars'; this._varsOpen = true; this._saveVars(); this._render(); });
            on('varsTabSearch', 'click', (e) => { e.stopPropagation(); this._varsTab = 'search'; this._varsOpen = true; this._saveVars(); this._render(); });
            // [ADDED v3.88.0] LIBI Global. A name typed is kept as it is typed, without drawing the page again (the box
            // keeps its focus); a phone ticked draws the card again.
            on('varsTabGlobal', 'click', (e) => { e.stopPropagation(); this._openGlobal(); });
            const keyOf = (e) => e.currentTarget.getAttribute('data-key');
            all('.glob-name', 'click', e => e.stopPropagation());
            all('.glob-name', 'input', e => {
                const key = keyOf(e);
                this._global.drafts[key] = { name: e.currentTarget.value, phones: [...this._globalDraft(key).phones] };
                const btn = [...sr.querySelectorAll('.glob-save')].find(b => b.getAttribute('data-key') === key);
                if (btn) btn.disabled = !this._globalCanSave(key);
            });
            all('.glob-name', 'keydown', e => {
                if (e.key !== 'Enter') return;
                e.preventDefault();
                if (this._globalCanSave(keyOf(e))) this._globalSave(keyOf(e));
            });
            all('.glob-tick', 'click', e => e.stopPropagation());
            all('.glob-tick', 'change', e => {
                const key = keyOf(e);
                const svc = e.currentTarget.getAttribute('data-svc');
                if (!svc) return;
                const base = this._globalDraft(key);
                const phones = base.phones.filter(s => s !== svc);
                if (e.currentTarget.checked) phones.push(svc);
                this._global.drafts[key] = { name: base.name, phones };
                this._render();
            });
            all('.glob-save', 'click', e => { e.stopPropagation(); this._globalSave(keyOf(e)); });
            // [CHANGED v3.88.1] Cancel closes the editor and drops what was not saved; a row of the table opens one.
            all('.glob-cancel', 'click', e => {
                e.stopPropagation();
                delete this._global.drafts[keyOf(e)];
                Object.assign(this._global, { editing: '', said: {} });
                this._render();
            });
            const openRow = (e) => {
                Object.assign(this._global, { editing: keyOf(e), said: {} });
                this._render();
            };
            all('.glob-row', 'click', e => { e.stopPropagation(); openRow(e); });
            all('.glob-row', 'keydown', e => {
                if (e.key !== 'Enter' && e.key !== ' ') return;
                e.preventDefault();
                openRow(e);
            });
            all('.glob-row-del', 'click', e => { e.stopPropagation(); this._globalDelete(keyOf(e)); });
            all('.glob-move-open', 'click', e => { e.stopPropagation(); this._openGlobalMove(keyOf(e)); });
            all('.glob-del', 'click', e => { e.stopPropagation(); this._globalDelete(keyOf(e)); });
            on('globAdd', 'click', (e) => {
                e.stopPropagation();
                this._global.drafts['+new'] = { name: '', phones: [] };
                Object.assign(this._global, { editing: '+new', said: {} });
                this._render();
                const box = this.shadowRoot.querySelector('.glob-name[data-key="+new"]');
                if (box) box.focus();
            });
            on('varsScopeNet', 'click', (e) => { e.stopPropagation(); this._varsScope = 'net'; this._render(); });
            on('varsScopeAll', 'click', (e) => { e.stopPropagation(); this._varsScope = 'all'; this._render(); });
            // [ADDED v3.86.0] Every NET of the project, from the chip in the bar or from the project's name in the header.
            on('varsScopeProject', 'click', (e) => { e.stopPropagation(); this._varsScope = 'project'; this._render(); });
            on('projectChip', 'click', (e) => { e.stopPropagation(); this._selectProject(); });
            on('projectChip', 'keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); this._selectProject(); }
            });
            all('.vars-filter', 'click', e => {
                e.stopPropagation();
                this._varsFilter = e.currentTarget.getAttribute('data-f');
                this._render();
            });
            on('varsClear', 'click', (e) => { e.stopPropagation(); this._varsQuery = ''; this._render(); });

            const q = sr.getElementById('varsQuery');
            if (q) {
                q.addEventListener('click', e => e.stopPropagation());
                q.addEventListener('input', (e) => {
                    this._varsQuery = e.target.value;
                    clearTimeout(this._varsTimer);
                    this._varsTimer = setTimeout(() => {
                        this._render();
                        const box = this.shadowRoot.getElementById('varsQuery');
                        if (box) { box.focus(); box.setSelectionRange(box.value.length, box.value.length); }
                    }, 220);
                });
            }
            const nameBox = sr.getElementById('varsNewName');
            if (nameBox) {
                nameBox.addEventListener('click', e => e.stopPropagation());
                nameBox.addEventListener('input', e => { this._varsNewName = e.target.value; });
                nameBox.addEventListener('keydown', e => { if (e.key === 'Enter') this._varsCreate(); });
            }
            const typeBox = sr.getElementById('varsNewType');
            if (typeBox) {
                typeBox.addEventListener('click', e => e.stopPropagation());
                typeBox.addEventListener('change', e => { this._varsNewType = e.target.value; });
            }
            on('varsCreate', 'click', (e) => { e.stopPropagation(); this._varsCreate(); });
            on('helperCreate', 'click', (e) => { e.stopPropagation(); this._openCreateHelper(); });

            // The Create helper dialog of LIBI, shown only when Home Assistant's own is not loaded.
            all('.hk-kind', 'click', e => { e.stopPropagation(); this._hkPickKind(e.currentTarget.getAttribute('data-d')); });
            on('hkBack', 'click', (e) => { e.stopPropagation(); this._hkPick = null; this._render(); });
            on('hkCreate', 'click', (e) => { e.stopPropagation(); this._hkCreate(); });
            on('hkMore', 'click', (e) => {
                e.stopPropagation();
                try { window.open('/config/helpers', '_blank'); } catch (err) { /* popup blocked */ }
            });
            const hkq = sr.getElementById('hkSearch');
            if (hkq) hkq.addEventListener('input', (e) => {
                this._hkQuery = e.target.value;
                clearTimeout(this._hkTimer);
                this._hkTimer = setTimeout(() => {
                    this._render();
                    const box = this.shadowRoot.getElementById('hkSearch');
                    if (box) { box.focus(); box.setSelectionRange(box.value.length, box.value.length); }
                }, 200);
            });
            const hkn = sr.getElementById('hkName');
            if (hkn) {
                hkn.addEventListener('input', e => { this._hkForm.name = e.target.value; });
                hkn.addEventListener('keydown', e => { if (e.key === 'Enter') this._hkCreate(); });
            }
            all('.hk-f', 'input', e => {
                const k = e.currentTarget.getAttribute('data-k');
                if (e.currentTarget.type !== 'checkbox') this._hkForm[k] = e.currentTarget.value;
            });
            all('.hk-f', 'change', e => {
                const k = e.currentTarget.getAttribute('data-k');
                this._hkForm[k] = e.currentTarget.type === 'checkbox' ? e.currentTarget.checked : e.currentTarget.value;
            });
            all('.hk-day-on', 'change', e => {
                const d = e.currentTarget.getAttribute('data-d');
                this._hkForm.week = this._hkForm.week || {};
                this._hkForm.week[d] = this._hkForm.week[d] || { from: '08:00', to: '17:00' };
                this._hkForm.week[d].on = e.currentTarget.checked;
                this._render();
            });
            all('.hk-day-t', 'change', e => {
                const d = e.currentTarget.getAttribute('data-d');
                const edge = e.currentTarget.getAttribute('data-e');
                this._hkForm.week = this._hkForm.week || {};
                this._hkForm.week[d] = this._hkForm.week[d] || { on: false, from: '08:00', to: '17:00' };
                this._hkForm.week[d][edge] = e.currentTarget.value;
            });
            on('helperClear', 'click', (e) => { e.stopPropagation(); this._helperQuery = ''; this._render(); });
            all('.helper-row', 'click', e => {
                e.stopPropagation();
                this._openHelperSettings(e.currentTarget.getAttribute('data-eid'));
            });
            const hs = sr.getElementById('helperSearch');
            if (hs) {
                hs.addEventListener('click', e => e.stopPropagation());
                hs.addEventListener('input', (e) => {
                    this._helperQuery = e.target.value;
                    clearTimeout(this._helperTimer);
                    this._helperTimer = setTimeout(() => {
                        this._render();
                        const box = this.shadowRoot.getElementById('helperSearch');
                        if (box) { box.focus(); box.setSelectionRange(box.value.length, box.value.length); }
                    }, 200);
                });
            }

            all('.vars-type', 'click', e => e.stopPropagation());
            all('.vars-type', 'change', e => {
                e.stopPropagation();
                this._varsChangeType(e.currentTarget.getAttribute('data-eid'), e.currentTarget.value);
            });
            all('.vars-del', 'click', e => {
                e.stopPropagation();
                if (e.currentTarget.hasAttribute('disabled')) return;
                this._varsDelete(e.currentTarget.getAttribute('data-eid'));
            });

            // Dragging a row out of the table and onto the ladder.
            all('.vars-drag', 'dragstart', e => {
                this._draggedVar = e.currentTarget.getAttribute('data-eid');
                this._draggedEl = null;
                e.currentTarget.classList.add('dragging');
                if (e.dataTransfer) {
                    e.dataTransfer.effectAllowed = 'copy';
                    e.dataTransfer.setData('text/plain', this._draggedVar);
                }
            });
            all('.vars-drag', 'dragend', e => {
                e.currentTarget.classList.remove('dragging');
                this._draggedVar = null;
            });
        });

        // The blocks accept a dropped variable. A pin takes it in its own field, the block itself
        // takes it wherever that kind of block keeps its entity.
        this._bindGroup('variable drop targets', () => {
            const over = (e) => {
                if (!this._draggedVar) return;
                e.preventDefault();
                e.stopPropagation();
                if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy';
                e.currentTarget.classList.add('var-drop');
            };
            const leave = (e) => e.currentTarget.classList.remove('var-drop');

            all('.pin-val', 'dragover', over);
            all('.pin-val', 'dragleave', leave);
            all('.pin-val', 'drop', e => {
                e.currentTarget.classList.remove('var-drop');
                if (!this._draggedVar) return;
                e.preventDefault();
                e.stopPropagation();
                const block = e.currentTarget.closest('.libi-el');
                if (!block) return;
                const done = this._applyDroppedVar(this._draggedVar,
                    block.getAttribute('data-nid'), block.getAttribute('data-rid'),
                    block.getAttribute('data-eid'), e.currentTarget.getAttribute('data-prop'));
                this._draggedVar = null;
                if (done) this._render();
            });

            all('.libi-el', 'dragover', over);
            all('.libi-el', 'dragleave', leave);
            all('.libi-el', 'drop', e => {
                e.currentTarget.classList.remove('var-drop');
                if (!this._draggedVar) return;
                e.preventDefault();
                const done = this._applyDroppedVar(this._draggedVar,
                    e.currentTarget.getAttribute('data-nid'), e.currentTarget.getAttribute('data-rid'),
                    e.currentTarget.getAttribute('data-eid'), null);
                this._draggedVar = null;
                if (done) this._render();
            });
        });

        // [ADDED v3.14.0] The four project actions.
        on('projNewBtn', 'click', () => { this._hdrMenu = false; this._modal = 'project_new'; this._render(); });
        on('projOpenBtn', 'click', async () => {
            this._hdrMenu = false;
            await this._projectRefreshList();
            this._modal = 'project_open';
            this._render();
        });
        on('projCloseBtn', 'click', () => { this._hdrMenu = false; this._projectClose(); });
        on('projDeleteBtn', 'click', () => { this._hdrMenu = false; this._modal = 'project_delete'; this._render(); });

        on('projNewOk', 'click', () => {
            const box = sr.getElementById('projNewName');
            const name = box ? String(box.value || '').trim() : '';
            if (!name) { alert('A project needs a name.'); return; }
            this._projectCreate(name);
        });
        all('.project-item', 'click', e => this._projectOpen(e.currentTarget.getAttribute('data-slug')));
        on('projDeleteOk', 'click', () => { if (this._project) this._projectDelete(this._project.slug); });

        // [ADDED v3.13.0] The overflow menu of the header.
        const hdrBtn = sr.getElementById('hdrMenuBtn');
        if (hdrBtn) hdrBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            this._hdrMenu = !this._hdrMenu;
            const menu = sr.getElementById('hdrMenu');
            if (menu) menu.classList.toggle('show', this._hdrMenu);
        });

        // [ADDED v3.13.0] The switch calls automation.toggle, which is the very action the Home
        // Assistant automation list calls, so the two stay in step with no state of our own.
        all('.net-state-toggle', 'click', e => e.stopPropagation());
        all('.net-state-toggle', 'change', async e => {
            const input = e.currentTarget;
            const entity = input.getAttribute('data-entity');
            if (!entity || !this._hass) return;
            const wanted = input.checked;
            // A net with errors may be switched off but never on.
            if (wanted && input.getAttribute('data-broken') === '1') {
                input.checked = false;
                alert('This net has errors, so its triggers cannot be armed. Fix the red blocks first.');
                return;
            }
            try {
                await this._hass.callService('automation', 'toggle', { entity_id: entity });
            } catch (err) {
                console.error('LIBI could not toggle', entity, err);
                input.checked = !wanted;   // Home Assistant refused, so put the switch back
                alert('Could not change the state of ' + entity + ': ' + (err && err.message ? err.message : err));
            }
        });

        // [ADDED v3.39.0] On the collapsed rail, CHAT AI opens the sidebar straight into the chat.
        const railAi = sr.getElementById('railAiBtn');
        if (railAi) railAi.addEventListener('click', (e) => {
            e.stopPropagation();
            this._sidebarRail = false;
            this._saveSidebar();
            this.aiChat.setOpen(true);
            this._render();
        });

        const sbToggle = sr.getElementById('sidebarToggle');
        if (sbToggle) sbToggle.addEventListener('click', (e) => {
            e.stopPropagation();
            this._sidebarRail = !this._sidebarRail;
            this._saveSidebar();
            this._render();
        });
        
        sr.addEventListener('click', () => { 
            if (this._ctx) { this._ctx = null; this._render(); return; }
            sr.querySelectorAll('.net-menu-dropdown.show').forEach(d => d.classList.remove('show')); 
            // [ADDED v3.13.0] The overflow menu of the header closes the same way the net menus do.
            if (this._hdrMenu) {
                this._hdrMenu = false;
                const hm = sr.getElementById('hdrMenu');
                if (hm) hm.classList.remove('show');
            }
        });

        // [CHANGED v3.45.0] The same four actions from the header and, on a phone, from the menu.
        const doUndo = () => { this._hdrMenu = false; if (this.core.undo()) this._render(); else this._render(); };
        const doRedo = () => { this._hdrMenu = false; if (this.core.redo()) this._render(); else this._render(); };
        on('undoBtn', 'click', doUndo);
        on('redoBtn', 'click', doRedo);
        on('mUndo', 'click', (e) => { e.stopPropagation(); doUndo(); });
        // Opens Home Assistant's sidebar. Where nothing listens for the event, the press does nothing.
        on('haMenuBtn', 'click', (e) => {
            e.stopPropagation();
            this.dispatchEvent(new CustomEvent('hass-toggle-menu', { bubbles: true, composed: true }));
        });
        on('mRedo', 'click', (e) => { e.stopPropagation(); doRedo(); });

        // [CHANGED v3.5.0] ADD NET asks which kind of logic to create instead of always producing
        // an automation. The net itself is created by the level picker below.
        const addNet = () => { 
            this._modal = 'pick_level'; 
            this._render(); 
        };
        on('addNetTop', 'click', addNet);
        on('addNetBottom', 'click', addNet);
        
        const doCollapse = () => {
            this._hdrMenu = false;
            const allClosed = this.core.nets.length > 0 && this.core.nets.every(n => n.collapsed);
            this.core.nets.forEach(n => { n.collapsed = !allClosed; });
            this._render();
        };
        on('collapseAllBtn', 'click', doCollapse);
        on('mCollapse', 'click', (e) => { e.stopPropagation(); doCollapse(); });

        const doOnline = () => {
            this._hdrMenu = false;
            this.online.enabled = !this.online.enabled;
            this._render();
            this._paintOnline();
        };
        on('onlineBtn', 'click', doOnline);
        on('mOnline', 'click', (e) => { e.stopPropagation(); doOnline(); });

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

        // [ADDED v3.86.0] The title of a NET chooses it, the bar at the bottom lists its variables; folding is the arrow.
        all('.net-name[data-sel]', 'click', e => {
            if (e.target.closest('button, select, .net-name-input')) return;
            e.stopPropagation();
            this._selectNet(e.currentTarget.getAttribute('data-sel'));
        });

        // [CHANGED v3.86.0] Clicking into the name chooses the NET too; the redraw gives the caret back where it was.
        all('.net-name-input', 'click', e => {
            e.stopPropagation();
            const nid = e.target.getAttribute('data-nid');
            if (this._selectedNetId === nid && this._varsScope === 'net' && this._varsTab === 'vars' && this._varsOpen) return;
            const at = [e.target.selectionStart, e.target.selectionEnd];
            this._selectNet(nid);
            const box = [...this.shadowRoot.querySelectorAll('.net-name-input')].find(b => b.getAttribute('data-nid') === nid);
            if (box) {
                box.focus({ preventScroll: true });
                try { box.setSelectionRange(at[0], at[1]); } catch (err) { /* no caret to give back */ }
            }
        });
        
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

        // [ADDED v3.47.0] The badge and the menu item open the same list.
        all('.ver-badge, .versions-net-btn', 'click', e => {
            e.stopPropagation();
            this._openVersions(e.currentTarget.getAttribute('data-nid'));
        });
        all('.ver-use', 'click', e => {
            e.stopPropagation();
            this._useVersion(Number(e.currentTarget.getAttribute('data-v')));
        });

        all('.show-yaml-btn', 'click', async e => {
            e.stopPropagation(); 
            const nid = e.currentTarget.getAttribute('data-nid'); 
            this._inspectedEl = null; 
            this._inspectedNetYaml = nid;
            this._selectedNetId = nid;
            this._netYamlKind = 'yaml';
            this._wakeSidebar();
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

        // [ADDED v3.63.0] The dashboard card of a NET, built by LIBI from what the NET compiles to: the settings it
        // reads and the devices it switches. The card the AI chat showed was gone once the chat was.
        all('.card-net-btn', 'click', async e => {
            e.stopPropagation();
            const nid = e.currentTarget.getAttribute('data-nid');
            this._inspectedEl = null;
            this._inspectedNetYaml = nid;
            this._selectedNetId = nid;
            this._netYamlKind = 'card';
            this._wakeSidebar();
            this._previewYamlContent = 'Building the card...';
            sr.querySelectorAll('.net-menu-dropdown.show').forEach(d => d.classList.remove('show'));
            this._render();
            const net = this.core.nets.find(n => n.id === nid);
            if (net && this._hass && this._hass.connection) {
                try {
                    const res = await this._hass.connection.sendMessagePromise({ type: 'libi/net_card', net: net });
                    this._previewYamlContent = (res && res.yaml) || 'This NET reads no setting and switches no device, so there is nothing to put on a card.';
                } catch (err) {
                    this._previewYamlContent = 'Error: ' + err.message;
                }
                if (this._inspectedNetYaml === nid && this._netYamlKind === 'card') this._render();
            }
        });
        on('copyNetCard', 'click', e => {
            const btn = e.currentTarget;
            const done = () => { btn.textContent = 'Copied'; setTimeout(() => { btn.textContent = 'Copy'; }, 1500); };
            const byHand = () => {
                const box = sr.querySelector('.yaml-preview-box');
                if (!box) return;
                box.select();
                try { if (document.execCommand('copy')) done(); } catch (err) { /* selected: the user copies it */ }
            };
            if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(this._previewYamlContent || '').then(done, byHand);
            else byHand();
        });

        // [CHANGED v3.77.0] Removing or deleting a NET asks whether its local variables go too, the user's request: the
        // helpers it uses that nothing else uses. Asked before anything is removed, deleted only once the NET is gone
        // and nothing runs with them - a NET whose automation stays in Home Assistant keeps them.
        // [CHANGED v3.85.0] One way to delete a NET, which asks what becomes of its entry in Home Assistant (_deleteNet) - it
        // took the place of Remove from Net and Delete File. The answers of a question of the panel's own (_ask).
        all('.delete-net-btn', 'click', e => {
            e.stopPropagation();
            this.shadowRoot.querySelectorAll('.net-menu-dropdown.show').forEach(d => d.classList.remove('show'));
            this._deleteNet(e.currentTarget.getAttribute('data-nid'));
        });
        all('.ask-answer', 'click', e => this._answerAsk(e.currentTarget.getAttribute('data-answer')));
        // [ADDED v3.89.0] The question to replace a phone with a global variable: a tick is kept without drawing the dialog
        // again; Replace in N follows the ticks.
        all('.gm-tick', 'change', e => {
            const m = this._globalMove;
            if (!m) return;
            const id = e.currentTarget.getAttribute('data-id');
            m.picked = m.picked.filter(x => x !== id);
            if (e.currentTarget.checked) m.picked.push(id);
            const go = this.shadowRoot.getElementById('gmGo');
            const can = this._globalMoveItems(m.key).filter(i => i.can && m.picked.includes(i.id)).length;
            if (go) { go.textContent = `Replace in ${can}`; go.disabled = !can || m.busy; }
        });
        on('gmGo', 'click', () => this._globalMoveRun());
        on('gmCancel', 'click', () => this._closeGlobalMove());

        all('.load-net-btn', 'click', e => { 
            e.stopPropagation(); 
            this._activeNetForLoad = e.currentTarget.getAttribute('data-nid'); 
            this._fetchAutomationsList(); 
        });
        
        all('[data-tog]', 'click', e => { 
            // [CHANGED v3.86.0] Not the title either: it chooses the NET (below).
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'BUTTON' || e.target.closest('.net-menu-wrapper') || e.target.closest('.net-name')) return; 
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

            // [ADDED v3.86.0] And its NET, for the variables bar.
            this._selectedNetId = parent.getAttribute('data-nid');
            this._inspectedEl = { 
                netId: parent.getAttribute('data-nid'), 
                rungId: parent.getAttribute('data-rid'), 
                elId: parent.getAttribute('data-eid'),
                focusProp: focusProp 
            }; 
            this._inspectedNetYaml = null; 
            // [ADDED v3.12.0] New content in the sidebar means the sidebar should be showing.
            this._wakeSidebar();
            
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
            this._draggedVar = null;
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

console.info(`%c⚡ LIBI ${LIBI_BUILD} loaded`, 'background:#03a9f4;color:#fff;padding:2px 8px;border-radius:4px;font-weight:700;');
customElements.define('libi-panel', LibiPanel);