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
 * LIBI - days row
 * v3.85.0
 */
//
// The days of the week an 8-bit helper holds, on a dashboard card - the user's design (2026-10-31): bit 1 is Sunday,
// bit 2 Monday ... bit 7 Saturday. A row of an entities card:
//     - type: custom:libi-days-row
//       entity: input_number.watering_days
//       name: Watering days          (optional)
//       icon: mdi:calendar-week      (optional)
// A day flips its bit with input_number.set_value (number.set_value for a number entity); the CMP DAY of the logic
// reads the same bits (DAY_BITS_TEMPLATE in yaml_to_libi.py). The names of the days come from the browser in Home
// Assistant's language (Intl), so no language is written in here. LIBI loads this file on every dashboard
// (frontend.add_extra_js_url in __init__.py).
//
// [ADDED v3.79.1 | 2026-11-01] Purpose: The row is defined where Home Assistant looks for it (defineIn): its frontend
//   (2026.x) puts a scoped registry in the place of window.customElements while it starts, and this file, an extra
//   module, may run before that - the row was then in the browser's registry only, and the user's card said
//   "Configuration error" ("Custom element doesn't exist"). Still in the browser's registry, the row is defined again
//   in the one that replaces it.
// [ADDED v3.85.0 | 2026-11-04] Purpose: The row on the browsers Home Assistant serves its legacy build to - Samsung
//   Internet up to 27, a Chrome or a WebView older than 131, Safari older than 18.1: that build loads only the scripts
//   registered for it, as classic scripts, so the user's train card said "Configuration error" there. LIBI registers
//   this file for that build too (__init__.py), and its code is in a block of its own: as a classic script its names
//   are no globals that could meet another script's, and a second load is harmless.
//
// SECURITY: the names shown are text (textContent), never HTML.

// [ADDED v3.85.0] One block: a module and a classic script alike keep every name of this file to themselves.
{
    const DOMAINS = ['input_number', 'number'];
    const SUNDAY = Date.UTC(2023, 0, 1);  // 1 January 2023 was a Sunday
    const DAY_MS = 86400000;
    // [ADDED v3.79.0] The icon of a row whose helper has none.
    const ICON = 'mdi:calendar-week';
    // [ADDED v3.79.0] How long the days just tapped are shown while Home Assistant holds other bits.
    const PENDING_MS = 5000;

    class LibiDaysRow extends HTMLElement {
        setConfig(config) {
            const domain = String((config && config.entity) || '').split('.')[0];
            if (!DOMAINS.includes(domain)) throw new Error('libi-days-row: entity must be an input_number or a number');
            this._config = { ...config };
            this._pending = null;
            this._render();
        }

        set hass(hass) {
            this._hass = hass;
            this._render();
        }

        getCardSize() {
            return 2;
        }

        _state() {
            return this._hass && this._hass.states ? this._hass.states[this._config.entity] : undefined;
        }

        /** The bits the helper holds now, 0-255, or null when it holds no number (unavailable, unknown). */
        _held() {
            const state = this._state();
            const text = state ? String(state.state).trim() : '';
            const value = text === '' ? NaN : Number(text);  // Number('') is 0, which is no number of the helper's
            return Number.isFinite(value) ? (Math.round(value) & 255) : null;
        }

        /** [ADDED v3.79.0] The bits to show and to tap on: the ones the taps asked for, until the helper holds them - or,
         *  with every call answered, until it holds bits that came after the answer (someone else set it); or the helper
         *  holds no number, or PENDING_MS passed. Else the helper's own. */
        _bits() {
            const held = this._held();
            const pending = this._pending;
            if (pending && (held === null || Date.now() > pending.until
                    || (!pending.calls && (held === pending.bits || (pending.answered !== undefined && held !== pending.answered))))) {
                this._pending = null;
            }
            return this._pending ? this._pending.bits : held;
        }

        /** The names of the days, Sunday first, in Home Assistant's language: short ones, or the narrow ones when a short
         *  name would not fit a button (more than three characters). The long name is the tooltip. */
        _names() {
            const hass = this._hass || {};
            const lang = (hass.locale && hass.locale.language) || hass.language || 'en';
            if (this._cache && this._cache.lang === lang) return this._cache;
            const format = (style) => {
                try { return new Intl.DateTimeFormat(lang, { weekday: style, timeZone: 'UTC' }); }
                catch (e) { return new Intl.DateTimeFormat('en', { weekday: style, timeZone: 'UTC' }); }
            };
            const week = (style) => { const f = format(style); return [0, 1, 2, 3, 4, 5, 6].map(i => f.format(new Date(SUNDAY + i * DAY_MS))); };
            const short = week('short');
            const narrow = short.some(s => s.length > 3);
            this._cache = { lang, narrow, label: narrow ? week('narrow') : short, long: week('long') };
            return this._cache;
        }

        /** [ADDED v3.79.0] What the row says under its name: nothing while the days can be tapped; the helper's state while it
         *  holds no number; that it is gone, in Home Assistant's words. */
        _note(state, bits) {
            const hass = this._hass;
            if (!hass || !hass.states || bits !== null) return '';
            if (!state) {
                let said = '';
                try { said = typeof hass.localize === 'function' ? hass.localize('ui.panel.lovelace.warning.entity_not_found', { entity: this._config.entity }) : ''; }
                catch (e) { said = ''; }
                return said || `Entity not available: ${this._config.entity}`;
            }
            try { if (typeof hass.formatEntityState === 'function') return String(hass.formatEntityState(state)); }
            catch (e) { /* the state as it is, below */ }
            return String(state.state);
        }

        _render() {
            if (!this._config) return;
            if (!this.shadowRoot) this._build();
            const root = this.shadowRoot;
            const state = this._state();
            const attrs = (state && state.attributes) || {};
            const name = this._config.name || attrs.friendly_name || this._config.entity;
            const names = this._names();
            const bits = this._bits();
            root.querySelector('.name').textContent = name;
            root.querySelector('.info').title = name;
            root.querySelector('ha-icon').setAttribute('icon', this._config.icon || attrs.icon || ICON);
            const note = root.querySelector('.note');
            note.textContent = this._note(state, bits);
            note.classList.toggle('warn', !!this._hass && !state);
            const days = root.querySelector('.days');
            days.setAttribute('aria-label', name);
            days.classList.toggle('narrow', names.narrow);
            days.querySelectorAll('button.day').forEach((button, i) => {
                const on = bits !== null && ((bits >> i) & 1) === 1;
                button.disabled = bits === null;
                button.classList.toggle('on', on);
                button.setAttribute('aria-pressed', String(on));
                button.setAttribute('aria-label', names.long[i]);
                button.title = names.long[i];
                button.textContent = names.label[i];
            });
        }

        _build() {
            const root = this.attachShadow({ mode: 'open' });
            const style = document.createElement('style');
            // As a row of Home Assistant's entities card: a 40 px icon, the name 16 px after it, the control at the end.
            // Narrower than 520 px - a phone, a narrow column - the days take a line of their own under the name; a browser
            // without container queries wraps them there too, at the end of the row (margin-inline-start: auto).
            style.textContent = `
                :host { display: block; container-type: inline-size; --libi-day-size: 36px; }
                .row { display: flex; flex-wrap: wrap; align-items: center; row-gap: 8px; min-height: 40px; }
                .icon { flex: 0 0 40px; height: 40px; display: flex; align-items: center; justify-content: center;
                    color: var(--state-icon-color, #44739e); }
                .info { flex: 1 1 30%; min-width: 0; padding-inline: 16px 8px; }
                .name, .note { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
                .name { color: var(--primary-text-color); }
                .note { color: var(--secondary-text-color); }
                .note.warn { color: var(--warning-color, #ffa600); }
                .note:empty { display: none; }
                .days { display: flex; align-items: center; gap: 4px; margin-inline-start: auto; }
                .day { flex: 0 1 var(--libi-day-size); inline-size: var(--libi-day-size); min-inline-size: 30px;
                    aspect-ratio: 1; box-sizing: border-box; margin: 0; padding: 0; border-radius: 50%;
                    border: 1px solid var(--divider-color, rgba(127, 127, 127, 0.3));
                    background: var(--secondary-background-color, transparent);
                    background: color-mix(in srgb, var(--primary-text-color, #212121) 6%, transparent);
                    color: var(--primary-text-color); font: inherit; font-size: 12px; font-weight: 500; line-height: 1;
                    cursor: pointer; user-select: none; -webkit-tap-highlight-color: transparent; touch-action: manipulation;
                    transition: background-color 120ms, border-color 120ms, color 120ms, transform 80ms; }
                .days.narrow .day { font-size: 14px; }
                .day.on { background: var(--primary-color); border-color: var(--primary-color);
                    color: var(--text-primary-color, #fff); }
                .day:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
                .day:active:not(:disabled) { transform: scale(0.92); }
                .day:disabled { cursor: default; opacity: 0.38; }
                @media (hover: hover) {
                    .day:not(:disabled):not(.on):hover { background: color-mix(in srgb, var(--primary-color) 14%, transparent); }
                    .day.on:not(:disabled):hover { filter: brightness(1.08); }
                }
                @media (pointer: coarse) { :host { --libi-day-size: 40px; } }
                @media (prefers-reduced-motion: reduce) {
                    .day { transition: none; }
                    .day:active:not(:disabled) { transform: none; }
                }
                @container (max-width: 519px) {
                    .days { flex: 1 1 100%; justify-content: space-between; margin-inline-start: 0; }
                }`;
            const row = document.createElement('div');
            row.className = 'row';
            const icon = document.createElement('div');
            icon.className = 'icon';
            icon.appendChild(document.createElement('ha-icon'));
            const info = document.createElement('div');
            info.className = 'info';
            const name = document.createElement('div');
            name.className = 'name';
            const note = document.createElement('div');
            note.className = 'note';
            info.append(name, note);
            const days = document.createElement('div');
            days.className = 'days';
            days.setAttribute('role', 'group');
            for (let i = 0; i < 7; i++) {
                const button = document.createElement('button');
                button.type = 'button';
                button.className = 'day';
                button.addEventListener('click', () => this._flip(i));
                days.appendChild(button);
            }
            row.append(icon, info, days);
            root.append(style, row);
        }

        /** Turns a day on or off: its bit flipped, the other bits (an eighth one too) kept as they are.
         *  [CHANGED v3.79.0] On the bits the taps before asked for, shown at once (_bits). A call that fails drops them. */
        _flip(day) {
            const bits = this._bits();
            if (bits === null || !this._hass) return;
            const value = bits ^ (1 << day);
            const domain = this._config.entity.split('.')[0];
            const pending = this._pending || { calls: 0 };
            pending.bits = value;
            pending.until = Date.now() + PENDING_MS;
            pending.calls += 1;
            delete pending.answered;
            this._pending = pending;
            this._render();
            const settle = (failed) => {
                pending.calls -= 1;
                if (failed) {
                    if (this._pending === pending) this._pending = null;
                } else if (!pending.calls) {
                    pending.answered = this._held();
                }
                this._render();
            };
            let call;
            try { call = this._hass.callService(domain, 'set_value', { entity_id: this._config.entity, value }); }
            catch (err) { call = Promise.reject(err); }
            Promise.resolve(call).then(() => settle(false), () => settle(true));
            clearTimeout(this._timer);
            this._timer = setTimeout(() => this._render(), PENDING_MS + 50);
        }
    }

    // [ADDED v3.79.1] Home Assistant's frontend (2026.x) replaces window.customElements with a scoped registry
    // (@webcomponents/scoped-custom-element-registry) while it starts, and loads this extra module at the same time: a row
    // defined before the swap is in the browser's registry only, and the new one - where the cards look - does not know it.
    // So the row is defined in the registry there is now and, while that is still the first one, again in the one that
    // takes its place. The watch ends with the swap, once Home Assistant's own root element is defined (it is defined
    // after the swap), or after SWAP_WAIT_MS.
    const TAG = 'libi-days-row';
    const SWAP_WAIT_MS = 60000;
    const SWAP_POLL_MS = 100;

    // [CHANGED v3.85.0] A constant: a function declared in a block of a classic script would still be a global.
    const defineIn = (registry) => {
        try {
            if (registry && !registry.get(TAG)) registry.define(TAG, LibiDaysRow);
        } catch (err) {
            console.error(`[LIBI] ${TAG} could not be defined:`, err);
        }
    };

    const firstRegistry = window.customElements;
    defineIn(firstRegistry);
    const watchSince = Date.now();
    const watch = setInterval(() => {
        const registry = window.customElements;
        if (registry !== firstRegistry) {
            defineIn(registry);
            clearInterval(watch);
        } else if (firstRegistry.get('home-assistant') || Date.now() - watchSince > SWAP_WAIT_MS) {
            clearInterval(watch);
        }
    }, SWAP_POLL_MS);
}
