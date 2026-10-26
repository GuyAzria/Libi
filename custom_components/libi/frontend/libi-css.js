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
 * LIBI Panel - Styles
 * v3.36.0
 */
// [ADDED v3.35.0 | 2026-10-26] Purpose: Colour tokens with a dark set under :host([dark]), so no
//   light-only background sits under the theme's (light) text in dark mode; header logo styles.
// [ADDED v3.36.0 | 2026-10-26] Purpose: The AI chat section under the Inspector.
export const getStyles = () => `
:host { display: block; height: 100vh; overflow-y: hidden; background: var(--primary-background-color, #f5f5f5); color: var(--primary-text-color, #212121); font-family: var(--primary-font-family, sans-serif); box-sizing: border-box; direction: ltr !important; text-align: left; }
/* [ADDED v3.35.0] Colour tokens. The light values are the colours the panel always used; the
   dark set applies when Home Assistant itself is in dark mode (the panel sets [dark] on the host
   from hass.themes.darkMode, which follows the user's HA theme, not the operating system). */
:host { --libi-tint: rgba(0,0,0,.02); --libi-hover: rgba(0,0,0,.05); --libi-toolbar-bg: #fdfdfd; --libi-label-bg: #ffffff; --libi-pin-lbl: #333; --libi-pin-bg: #e3f2fd; --libi-pin-fg: #0277bd; --libi-pin-border: #03a9f4; --libi-pin-hover-bg: #b3e5fc; --libi-pin-hover-border: #0288d1; --libi-trig-bg: #fff8e1; --libi-trig-head: #d97706; --libi-trig-fg: #a16207; --libi-coe-bg: #fdecea; --libi-coe-fg: #c62828; --libi-err-bg: #ffebee; --libi-notice-bg: #fff8e1; --libi-notice-border: #ffcc80; --libi-notice-head: #e65100; --libi-notice-x: #a1887f; --libi-notice-list: #5d4037; --libi-link-bg: #ede7f6; --libi-link-fg: #5e35b1; --libi-link-border: #b39ddb; --libi-ok: #2e7d32; --libi-ok-strong: #1b5e20; --libi-ok-bg: #e8f5e9; --libi-ok-border: #a5d6a7; --libi-type-bool-bg: #e8f5e9; --libi-type-bool-fg: #2e7d32; --libi-type-int-bg: #e3f2fd; --libi-type-int-fg: #1565c0; --libi-type-float-bg: #ede7f6; --libi-type-float-fg: #5e35b1; --libi-type-text-bg: #fff8e1; --libi-type-text-fg: #ef6c00; --libi-type-time-bg: #fce4ec; --libi-type-time-fg: #ad1457; --libi-type-ha-bg: #eceff1; --libi-type-ha-fg: #546e7a; }
:host([dark]) { --libi-tint: rgba(255,255,255,.04); --libi-hover: rgba(255,255,255,.08); --libi-toolbar-bg: rgba(255,255,255,.03); --libi-label-bg: #2b2e33; --libi-pin-lbl: #e0e0e0; --libi-pin-bg: rgba(3,169,244,.16); --libi-pin-fg: #81d4fa; --libi-pin-border: #29b6f6; --libi-pin-hover-bg: rgba(3,169,244,.28); --libi-pin-hover-border: #4fc3f7; --libi-trig-bg: rgba(249,168,37,.14); --libi-trig-head: #ffca28; --libi-trig-fg: #ffd54f; --libi-coe-bg: rgba(244,67,54,.16); --libi-coe-fg: #ef9a9a; --libi-err-bg: rgba(244,67,54,.18); --libi-notice-bg: rgba(255,152,0,.12); --libi-notice-border: rgba(255,183,77,.5); --libi-notice-head: #ffb74d; --libi-notice-x: #bcaaa4; --libi-notice-list: #d7ccc8; --libi-link-bg: rgba(126,87,194,.22); --libi-link-fg: #d1c4e9; --libi-link-border: #9575cd; --libi-ok: #81c784; --libi-ok-strong: #a5d6a7; --libi-ok-bg: rgba(46,125,50,.22); --libi-ok-border: rgba(129,199,132,.5); --libi-type-bool-bg: rgba(46,125,50,.22); --libi-type-bool-fg: #81c784; --libi-type-int-bg: rgba(33,150,243,.2); --libi-type-int-fg: #90caf9; --libi-type-float-bg: rgba(126,87,194,.22); --libi-type-float-fg: #b39ddb; --libi-type-text-bg: rgba(255,152,0,.16); --libi-type-text-fg: #ffb74d; --libi-type-time-bg: rgba(233,30,99,.18); --libi-type-time-fg: #f48fb1; --libi-type-ha-bg: rgba(144,164,174,.2); --libi-type-ha-fg: #b0bec5; }
*, *::before, *::after { box-sizing: border-box; }

.panel-layout { display: flex; flex-direction: column; height: 100vh; }
.header { display: flex; justify-content: space-between; align-items: center; padding: 0 16px; min-height: 56px; background: var(--app-header-background-color, var(--primary-background-color, #fff)); border-bottom: 1px solid var(--divider-color, #e0e0e0); z-index: 200; direction: ltr; }
.header-title { font-size: 20px; font-weight: 500; }
/* [ADDED v3.35.0] The brand logo and the name, top left. */
.hdr-logo { height: 38px; width: auto; display: block; flex: 0 0 auto; }
.hdr-wordmark { margin-inline: 8px 12px; font-size: 22px; font-weight: 900; letter-spacing: 1px; line-height: 1; color: var(--app-header-text-color, var(--primary-text-color, #212121)); }
@media (max-width: 768px) { .hdr-logo { height: 32px; } .hdr-wordmark { font-size: 18px; margin-inline: 6px 8px; } }
.header-acts { display: flex; gap: 8px; align-items: center; }

/* [CHANGED v3.17.0] The bar at the bottom takes its share of the height, so the row above it just
   fills whatever is left rather than claiming the whole viewport. */
.main-content { display: flex; flex-direction: row; flex: 1 1 auto; min-height: 0; overflow: hidden; }
.canvas { flex: 1; overflow: auto; padding: 20px; display: flex; flex-direction: column; gap: 20px; -webkit-overflow-scrolling: touch; }
/* [CHANGED v3.12.0] The width is no longer written here. It lives in --libi-sidebar-w, which the
   panel sets from what was saved last, so there is no fixed width other than the first ever run. */
.sidebar { width: var(--libi-sidebar-w, 320px); flex: 0 0 var(--libi-sidebar-w, 320px); min-width: 40px; background: var(--card-background-color, #fff); border-left: 1px solid var(--divider-color, #e0e0e0); display: flex; flex-direction: column; box-shadow: -2px 0 8px rgba(0,0,0,0.05); z-index: 10; position: relative; }
.sidebar.rail { width: 40px !important; flex: 0 0 40px !important; overflow: hidden; }
.sidebar.dragging { transition: none; user-select: none; }

/* [ADDED v3.12.0] The grip that resizes the sidebar. It sits on the edge that faces the ladder and
   widens on hover so it is easy to grab without stealing pixels from the canvas when it is idle. */
.sidebar-grip { position: absolute; left: -3px; top: 0; bottom: 0; width: 7px; cursor: col-resize; z-index: 30; background: transparent; touch-action: none; }
.sidebar-grip:hover, .sidebar-grip.active { background: var(--primary-color, #03a9f4); opacity: .35; }
.sidebar.rail .sidebar-grip { display: none; }

/* [ADDED v3.12.0] The bar across the top of the sidebar: the title and the collapse button. */
.sidebar-top { display: flex; align-items: center; gap: 6px; padding: 6px 8px; border-bottom: 1px solid var(--divider-color, #eee); background: var(--libi-tint); min-height: 36px; box-sizing: border-box; }
.sidebar-top .grow { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; font-weight: 700; color: var(--secondary-text-color, #757575); text-transform: uppercase; letter-spacing: .3px; }
.sidebar-toggle { border: 1px solid var(--divider-color, #ddd); background: var(--card-background-color, #fff); color: var(--secondary-text-color, #757575); border-radius: 6px; width: 24px; height: 24px; line-height: 1; font-size: 13px; cursor: pointer; flex: 0 0 auto; padding: 0; }
.sidebar-toggle:hover { border-color: var(--primary-color, #03a9f4); color: var(--primary-color, #03a9f4); }
.sidebar.rail .sidebar-top { padding: 6px 7px; justify-content: center; }
.sidebar.rail .sidebar-top .grow { display: none; }
.sidebar-content { display: flex; flex-direction: column; flex: 1; min-height: 0; overflow: hidden; }
.sidebar.rail .sidebar-content { display: none; }
/* The word LIBI running up the closed rail, so the strip is not a blank column. */
.sidebar-rail-tag { writing-mode: vertical-rl; text-orientation: mixed; margin: 10px auto 0 auto; font-size: 10px; font-weight: 800; letter-spacing: 2px; color: var(--secondary-text-color, #9e9e9e); user-select: none; }
.sidebar:not(.rail) .sidebar-rail-tag { display: none; }

@media (max-width: 768px) {
    .main-content { flex-direction: column; }
    /* On a phone the sidebar is a sheet at the bottom, so the same saved number is a height and the
       grip drags up and down instead of sideways. */
    .sidebar { width: 100% !important; flex: 0 0 auto !important; border-left: none; border-top: 2px solid var(--primary-color, #03a9f4); height: var(--libi-sidebar-h, 40vh); max-height: 60vh; min-height: 40px; box-shadow: 0 -2px 8px rgba(0,0,0,0.1); }
    .sidebar.rail { width: 100% !important; height: 40px !important; flex: 0 0 40px !important; }
    .sidebar-grip { left: 0; right: 0; top: -3px; bottom: auto; width: auto; height: 7px; cursor: row-resize; }
    .sidebar-rail-tag { writing-mode: horizontal-tb; margin: 0 0 0 6px; }
    .header-acts .ha-text-btn { font-size: 11px; padding: 0 6px; }
    .canvas { padding: 10px; }
}

.sidebar-hdr { padding: 16px; border-bottom: 1px solid var(--divider-color, #eee); font-weight: bold; font-size: 16px; background: var(--libi-tint); }
.sidebar-body { padding: 16px; overflow-y: auto; flex: 1; display: flex; flex-direction: column; gap: 16px; }

.fgrp { display: flex; flex-direction: column; gap: 6px; margin-bottom: 12px; }
.fgrp label { font-size: 12px; color: var(--secondary-text-color,#757575); font-weight: 600; text-transform: uppercase; }
.fgrp input, .fgrp select, .fgrp textarea { padding: 10px 12px; border: 1.5px solid var(--divider-color,#ddd); border-radius: 7px; font-size: 14px; background: var(--secondary-background-color,#fafafa); color: var(--primary-text-color,#212121); outline: none; font-family: inherit; direction: ltr; }
.fgrp input[type="checkbox"] { width: 18px; height: 18px; cursor: pointer; }
.fgrp input:focus, .fgrp select:focus, .fgrp textarea:focus { border-color: var(--primary-color,#03a9f4); }
.checkbox-grp { flex-direction: row; align-items: center; gap: 10px; }

.net { background: var(--card-background-color,#fff); border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,.08); overflow: hidden; border-left: 6px solid var(--rc, var(--divider-color,#ddd)); transition: box-shadow 0.3s; flex: 0 0 auto; }
.net-hdr { display: flex; justify-content: space-between; align-items: center; padding: 13px 16px; background: var(--libi-tint); border-bottom: 1px solid var(--divider-color,#eee); cursor: pointer; user-select: none; }
.net-hdr-l { display: flex; align-items: center; gap: 8px; flex: 1; }
.net-hdr-r { display: flex; align-items: center; gap: 8px; }
.net-name { font-size: 15px; flex: 1; display:flex; align-items:center; gap:8px; flex-wrap: nowrap; overflow: hidden; }
.net-name span { white-space: nowrap; flex-shrink: 0; }
.net-name input { border:none; background:transparent; font-size:15px; font-weight:700; color:inherit; outline:none; width:100%; direction: ltr; min-width: 150px; }
.net-body { display: flex; flex-direction: column; align-items: stretch; overflow: hidden; max-height: 40000px; transition: max-height 0.3s ease; flex: 0 0 auto; }
.net.collapsed .net-body { max-height: 0 !important; border-bottom: none; }

.net-toolbar { display: flex; gap: 12px; padding: 8px 16px; background: var(--libi-toolbar-bg); border-bottom: 1px solid var(--divider-color,#eee); align-items: center; }
.rung-comment-input { width: 100%; margin-left: 16px; border: none; border-bottom: 1px dashed var(--divider-color,#ccc); background: transparent; font-size: 13px; font-style: italic; color: var(--secondary-text-color,#555); padding: 4px 8px; margin-bottom: 8px; outline: none; transition: border-color 0.2s; direction: ltr; }
.rung-comment-input:focus { border-bottom-color: var(--primary-color,#03a9f4); }

.net-menu-wrapper { position: relative; }
.net-kebab { background: none; border: none; cursor: pointer; color: var(--secondary-text-color, #757575); padding: 6px; border-radius: 50%; display: flex; align-items: center; justify-content: center; transition: background 0.2s; }
.net-kebab:hover { background: var(--libi-hover); color: var(--primary-text-color, #212121); }
.net-kebab svg { width: 24px; height: 24px; }
.net-menu-dropdown { position: absolute; right: 0; top: 100%; background: var(--card-background-color, #fff); box-shadow: 0 4px 12px rgba(0,0,0,0.15); border: 1px solid var(--divider-color, #e0e0e0); border-radius: 6px; min-width: 180px; z-index: 1000; display: none; flex-direction: column; overflow: hidden; }
.net-menu-dropdown.show { display: flex; }
.net-menu-item { padding: 12px 16px; cursor: pointer; font-size: 13px; font-weight: 500; color: var(--primary-text-color, #212121); display: flex; align-items: center; gap: 8px; background: transparent; border: none; border-bottom: 1px solid var(--divider-color, #f0f0f0); text-align: left; width: 100%; transition: background 0.2s; }
.net-menu-item:last-child { border-bottom: none; }
.net-menu-item:hover { background: var(--secondary-background-color, #f5f5f5); }
.net-menu-item.danger { color: var(--error-color, #f44336); }
.net-menu-item.danger:hover { background: rgba(244,67,54,0.08); }

.yaml-preview-box { width: 100%; flex: 1; min-height: 400px; font-family: monospace; font-size: 12px; background: #1e1e1e; color: #d4d4d4; border: none; border-radius: 6px; padding: 12px; outline: none; resize: vertical; box-sizing: border-box; direction: ltr; }

/* RUNG & WIRE BASE CSS */
.rail { width: 5px; flex-shrink: 0; background: var(--divider-color,#ddd); }
.rail-l { background: var(--rc, var(--divider-color,#ddd)); margin: 0 0 0 16px; }
.rail-r { margin: 0 16px 0 6px; }
.rungs { flex: 1; display: flex; flex-direction: column; gap: 10px; padding: 0 8px 0 0; min-width: 0; }
.rung { display: flex; flex-direction: column; width: 100%; padding-left: 0; padding-bottom: 40px; flex: 0 0 auto; }
.rung-scroll { cursor: grab; touch-action: pan-x pan-y; }
.rung-scroll.panning { cursor: grabbing; user-select: none; }
.rung-scroll::-webkit-scrollbar { display: none; }
.canvas-empty { display: flex; flex-direction: column; align-items: center; gap: 12px; padding: 48px 0; }
.canvas-empty-text { color: var(--secondary-text-color, #757575); font-size: 14px; }
.add-net-btn { align-self: flex-start; margin: 4px 0 8px 4px; }
.rung-scroll { overflow-x: auto; overflow-y: hidden; width: 100%; scrollbar-width: none; }
.rung-wire { display: block; position: relative; min-width: 100%; padding-top: 0; margin: 0; }
.rung-wire > .libi-el { position: absolute; margin: 0; }
.rung-wire > .wire-ins { position: absolute; margin: 0; }

/* MATHEMATICAL ALIGNMENT FOR Y=38px */
.libi-el { position: relative; z-index: 2; display: inline-flex; flex-direction: column; align-items: center; justify-content: flex-start; cursor: grab; padding: 0; margin: 0 24px; }
.libi-el:active { cursor: grabbing; }
.libi-el.selected .el-ico, .libi-el.selected .plc-block { outline: 2px solid var(--primary-color, #03a9f4); outline-offset: 2px; }

/* DOT */
.wire-ins { position: relative; z-index: 5; width: 16px; height: 16px; border-radius: 50%; background: var(--primary-color,#03a9f4); border: none; display: inline-flex; align-items: center; justify-content: center; margin: 30px 0 0 0; color: transparent; transition: transform .15s, background .15s, box-shadow .15s; cursor: pointer; touch-action: none; padding: 0; }
.wire-ins::after { content: ''; position: absolute; top: -14px; left: -14px; right: -14px; bottom: -14px; background: transparent; border-radius: 50%; }
.wire-ins:hover, .wire-ins.drag-over { transform: scale(1.6); color: white; background: var(--success-color, #4caf50); z-index: 15; }

/* VALID TARGET HIGHLIGHT (Smart UX Dragging) */
.wire-ins.valid-target { transform: scale(1.5); background: #9c27b0; box-shadow: 0 0 10px rgba(156, 39, 176, 0.7); z-index: 10; animation: pulseTarget 1.2s infinite; }
@keyframes pulseTarget { 0% { box-shadow: 0 0 0 0 rgba(156, 39, 176, 0.9); } 70% { box-shadow: 0 0 0 12px rgba(156, 39, 176, 0); } 100% { box-shadow: 0 0 0 0 rgba(156, 39, 176, 0); } }

/* CONTACT */
.el-ico { width: 56px; height: 36px; display: inline-flex; align-items: center; justify-content: center; background: var(--card-background-color, #fff); border-radius: 5px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); transition: all 0.2s; border: 1px solid transparent; cursor: pointer; z-index: 2; margin-top: 20px; }
.el-ico:hover { background: var(--secondary-background-color, #f5f5f5); transform: translateY(-2px); box-shadow: 0 4px 8px rgba(0,0,0,0.15); }
.el-ico svg { width: 100%; height: 100%; }

.el-lbl { position: absolute; bottom: calc(100% - 16px); left: 50%; transform: translateX(-50%); font-size: 11px; font-weight: 700; color: var(--primary-text-color, #111); background: var(--libi-label-bg); border: 1.5px solid var(--divider-color, #c0c0c0); border-radius: 5px; padding: 3px 6px; min-width: 40px; text-align: center; line-height: 1.2; white-space: normal; word-wrap: break-word; word-break: break-word; box-shadow: 0 2px 5px rgba(0,0,0,0.12); z-index: 4; cursor: pointer; direction: ltr; unicode-bidi: plaintext; }
.el-lbl:hover { background: var(--secondary-background-color, #f0f0f0); border-color: var(--primary-color, #03a9f4); }

/* VERTICAL EXPANDING PLC BLOCKS */
.plc-block { display: flex; flex-direction: column; width: 100%; background: var(--card-background-color, #f8f9fa); border: 1.5px solid var(--primary-text-color, #555); border-radius: 4px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); position: relative; align-items: stretch; cursor: default; z-index: 2; transition: all 0.2s; margin: 6px auto 0 auto; min-height: 60px; padding-bottom: 6px; }
.plc-block:hover { transform: translateY(-2px); box-shadow: 0 4px 8px rgba(0,0,0,0.15); }
.plc-header { height: 20px; line-height: 14px; font-weight: 900; font-size: 11px; text-align: center; border-bottom: 1px solid var(--divider-color, #ccc); background: var(--libi-hover); padding: 3px; box-sizing: border-box; cursor: pointer; }
.power-row { display: flex; justify-content: space-between; padding: 0 6px; height: 24px; align-items: center; box-sizing: border-box; font-size: 10px; font-weight: bold; }
.plc-row { display: flex; justify-content: space-between; padding: 4px 6px; box-sizing: border-box; }

.plc-col-l { display: flex; flex-direction: column; align-items: flex-start; max-width: 49%; gap: 3px; }
.plc-col-r { display: flex; flex-direction: column; align-items: flex-end; max-width: 48%; gap: 3px; }
.plc-col-l.empty, .plc-col-r.empty { width: 48%; }

.pin-lbl { font-size: 10px; font-weight: 800; color: var(--libi-pin-lbl); line-height: 1; pointer-events: none; }
.pin-val { background: var(--libi-pin-bg); color: var(--libi-pin-fg); border: 1px solid var(--libi-pin-border); border-radius: 4px; padding: 4px; font-size: 10px; font-family: monospace; white-space: normal; word-wrap: break-word; overflow-wrap: anywhere; word-break: normal; max-width: 100%; box-sizing: border-box; cursor: pointer; transition: all 0.2s; box-shadow: 0 1px 2px rgba(0,0,0,0.05); direction: ltr; unicode-bidi: plaintext; text-align: left; }
.pin-val:hover { background: var(--libi-pin-hover-bg); border-color: var(--libi-pin-hover-border); transform: translateY(-1px); box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
.plc-col-l .pin-val { text-align: left; }
.plc-col-r .pin-val { text-align: right; }

/* ⚡ IS_TRIGGER STYLES */
.libi-el.is-trigger .el-ico { background-color: var(--libi-trig-bg); border-color: #f9a825; box-shadow: 0 1px 4px rgba(249, 168, 37, 0.4); }
.libi-el.is-trigger .plc-block { background-color: var(--libi-trig-bg); border-color: #f9a825; }
.libi-el.is-trigger .plc-header { background-color: rgba(249, 168, 37, 0.18); color: var(--libi-trig-head); border-bottom-color: #f9a825; }
.trigger-bottom-lbl { position: absolute; top: calc(100% + 4px); left: 50%; transform: translateX(-50%); font-size: 10px; font-weight: 800; color: var(--libi-trig-fg); background: var(--libi-trig-bg); padding: 2px 6px; border-radius: 4px; border: 1px solid #f9a825; z-index: 5; pointer-events: none; }

/* [CHANGED v3.25.0] continue_on_error used to be a dashed bypass drawn over the rung. It sat on top
   of the labels of the blocks either side and hid them, so it is a badge under the block instead,
   in the same place and the same shape as the Trigger badge, in red. */
/* [ADDED v3.28.0] The little menu a right click on a block name opens. */
.ctx-menu { position: fixed; z-index: 900; min-width: 190px; background: var(--card-background-color, #fff); border: 1px solid var(--divider-color, #e0e0e0); border-radius: 8px; box-shadow: 0 4px 16px rgba(0,0,0,.2); padding: 5px 0; }
.ctx-item { display: flex; align-items: center; gap: 9px; width: 100%; background: none; border: none; text-align: left; padding: 9px 14px; font-size: 13px; color: var(--primary-text-color, #212121); cursor: pointer; font-family: inherit; }
.ctx-item:hover { background: var(--secondary-background-color, #f2f2f2); }
/* [ADDED v3.32.0] The entity chooser, laid out the way the Add condition dialog of Home Assistant
   lays it out: a search box, two tabs, and a list of groups that open. */
.ep-modal { width: min(940px, 94vw); max-height: 86vh; display: flex; flex-direction: column; }
.ep-top { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.ep-top input { flex: 1; }
.ep-tabs { display: flex; border-radius: 6px; overflow: hidden; border: 1px solid var(--divider-color, #e0e0e0); flex: 0 0 auto; margin-bottom: 10px; }
.ep-tab { flex: 1; border: none; background: var(--secondary-background-color, #eee); color: var(--secondary-text-color, #757575); padding: 10px 16px; font-size: 14px; font-weight: 600; cursor: pointer; font-family: inherit; }
.ep-tab.on { background: var(--primary-color, #03a9f4); color: var(--text-primary-color, #fff); }
.ep-body { flex: 1; min-height: 0; overflow: auto; border: 1px solid var(--divider-color, #eee); border-radius: 8px; }
.ep-sec { background: var(--secondary-background-color, #f4f4f4); padding: 7px 16px; font-size: 12px; font-weight: 800; color: var(--secondary-text-color, #757575); position: sticky; top: 0; z-index: 2; }
.ep-group { display: flex; align-items: center; gap: 12px; padding: 10px 16px; cursor: pointer; border-bottom: 1px solid var(--divider-color, #f4f4f4); }
.ep-group:hover { background: var(--secondary-background-color, #f7f7f7); }
.ep-group .chev { width: 12px; color: var(--secondary-text-color, #bdbdbd); font-size: 11px; transition: transform .15s; }
.ep-group.open .chev { transform: rotate(90deg); }
.ep-group .ico { width: 22px; text-align: center; font-size: 15px; color: var(--secondary-text-color, #616161); }
.ep-group .nm { flex: 1; font-size: 14px; }
.ep-group .ct { font-size: 12px; color: var(--secondary-text-color, #9e9e9e); }
.ep-item { display: flex; align-items: center; gap: 12px; padding: 8px 16px 8px 50px; cursor: pointer; border-bottom: 1px solid var(--divider-color, #f7f7f7); }
.ep-item:hover { background: rgba(3,169,244,.10); }
.ep-item.cur { background: rgba(3,169,244,.16); }
.ep-item .txt { flex: 1; min-width: 0; }
.ep-item .nm { font-size: 13.5px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ep-item .eid { font-family: monospace; font-size: 11px; color: var(--secondary-text-color, #9e9e9e); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ep-item .st { font-size: 11px; font-weight: 700; color: var(--secondary-text-color, #757575); }
.ep-empty { padding: 26px 16px; text-align: center; font-size: 13px; color: var(--secondary-text-color, #9e9e9e); }
.ep-cur { font-size: 12px; color: var(--secondary-text-color, #757575); margin: 0 0 8px 0; font-family: monospace; }
.el-lbl { cursor: pointer; }

.ctx-head { padding: 5px 14px 7px 14px; font-size: 11px; color: var(--secondary-text-color, #9e9e9e); border-bottom: 1px solid var(--divider-color, #eee); margin-bottom: 4px; font-family: monospace; word-break: break-all; }
.el-lbl { cursor: context-menu; }

.coe-bottom-lbl { position: absolute; top: calc(100% + 4px); left: 50%; transform: translateX(-50%); font-size: 10px; font-weight: 800; color: var(--libi-coe-fg); background: var(--libi-coe-bg); padding: 2px 6px; border-radius: 4px; border: 1px solid #e57373; z-index: 5; pointer-events: none; white-space: nowrap; }

/* ERROR LINTER STYLES */
.libi-el.has-error .plc-block { border-color: var(--error-color, #f44336) !important; box-shadow: 0 0 8px rgba(244,67,54,0.4) !important; }
.libi-el.has-error .el-ico { border-color: var(--error-color, #f44336) !important; box-shadow: 0 0 8px rgba(244,67,54,0.4) !important; }
.pin-val.has-error, .el-lbl.has-error { border-color: var(--error-color, #f44336) !important; color: var(--error-color, #f44336) !important; background: var(--libi-err-bg) !important; }
.err-tooltip { position: absolute; top: calc(100% + 24px); left: 50%; transform: translateX(-50%); background: var(--error-color, #f44336); color: white; font-size: 10px; padding: 4px 8px; border-radius: 4px; white-space: nowrap; z-index: 20; box-shadow: 0 2px 5px rgba(0,0,0,0.2); pointer-events: none; }
.err-tooltip::after { content: ''; position: absolute; bottom: 100%; left: 50%; transform: translateX(-50%); border-width: 4px; border-style: solid; border-color: transparent transparent var(--error-color, #f44336) transparent; }

/* Floating Menus */
.fm-overlay { position: fixed; inset: 0; z-index: 999; }
.palette { position: fixed; z-index: 1000; transform: translate(-50%, -100%); background: var(--card-background-color, #fff); border: 1px solid var(--divider-color, #e0e0e0); border-radius: 12px; box-shadow: 0 6px 20px rgba(0,0,0,.18); padding: 6px; max-width: min(360px, 92vw); }
.palette::after { content: ''; position: absolute; left: var(--arrow-x, 50%); bottom: -7px; width: 12px; height: 12px; background: inherit; border-right: 1px solid var(--divider-color, #e0e0e0); border-bottom: 1px solid var(--divider-color, #e0e0e0); transform: translateX(-50%) rotate(45deg); }
.palette-row { display: flex; gap: 4px; overflow-x: auto; scrollbar-width: thin; padding-bottom: 2px; }
.palette-row::-webkit-scrollbar { height: 6px; }
.palette-row::-webkit-scrollbar-thumb { background: var(--divider-color, #ddd); border-radius: 3px; }
.palette-sep { height: 1px; background: var(--divider-color, #eee); margin: 6px 2px; }
.pal-btn { flex: 0 0 auto; min-width: 42px; height: 40px; padding: 0 8px; background: var(--card-background-color, #fff); border: 1px solid var(--divider-color, #e8e8e8); border-radius: 9px; display: flex; align-items: center; justify-content: center; gap: 4px; cursor: pointer; color: var(--primary-text-color, #212121); font-size: 13px; font-weight: 700; }
.pal-btn:hover { background: var(--secondary-background-color, #f5f5f5); border-color: var(--primary-color, #03a9f4); }
.pal-btn.selected { border-color: var(--primary-color, #03a9f4); background: rgba(3,169,244,.08); }
.pal-btn.danger { color: var(--error-color, #f44336); }
.pal-btn.trigger-on { border-color: #f9a825; background: var(--libi-trig-bg); color: var(--libi-trig-fg); }
.pal-btn small { font-size: 10px; font-weight: 800; letter-spacing: .3px; }
.fan-menu-container { position: fixed; z-index: 1000; width: 0; height: 0; pointer-events: none; }
.fan-btn { position: absolute; width: 44px; height: 44px; background: var(--card-background-color, #fff); border: 1px solid var(--divider-color, #eee); border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.15); display: flex; align-items: center; justify-content: center; cursor: pointer; transform: translate(-50%, -50%); pointer-events: auto; transition: transform 0.15s, background 0.15s; color: var(--primary-text-color, #212121); padding: 0; }
.fan-btn:hover { transform: translate(-50%, -50%) scale(1.15); background: var(--secondary-background-color, #f5f5f5); }
.fan-btn.danger { color: var(--error-color, #f44336); }

/* Parallel branch layout */
.parallel-branch { display: inline-flex; align-items: flex-start; }
.repeat-sequence-wrapper { display:inline-flex; border-bottom: 2px dashed #9c27b0; padding-bottom: 12px; margin: 0 4px; border-radius:4px; background: rgba(156, 39, 176, 0.03); }

/* Absolute layout skins. */
.rung-wire > .libi-parallel { display: block; background: transparent; cursor: pointer; }
.rung-wire > .libi-parallel.selected { outline: 2px dashed var(--primary-color, #03a9f4); outline-offset: 4px; border-radius: 8px; }
.rung-wire > .repeat-sequence-wrapper { position: absolute; display: block; margin: 0; padding: 0; pointer-events: none; }

.net-notice { margin: 4px 16px 0 16px; border: 1px solid var(--libi-notice-border); background: var(--libi-notice-bg); border-radius: 8px; padding: 10px 12px; max-width: 900px; }
.net-notice-head { display: flex; justify-content: space-between; align-items: center; font-weight: 700; font-size: 13px; color: var(--libi-notice-head); }
.net-notice-x { border: none; background: transparent; cursor: pointer; font-size: 13px; color: var(--libi-notice-x); padding: 0 4px; }
.net-notice-x:hover { color: var(--libi-notice-head); }
.net-notice-body { font-size: 12px; color: var(--secondary-text-color, #616161); margin: 4px 0 6px 0; }
.net-notice-list { margin: 0; padding-inline-start: 18px; font-size: 12px; font-family: monospace; color: var(--libi-notice-list); max-height: 160px; overflow: auto; }
.net-notice-more { font-size: 11px; color: var(--libi-notice-x); margin-top: 4px; }

.link-cut { position: absolute; width: 18px; height: 18px; border-radius: 50%; border: 1px solid var(--libi-link-border); background: var(--libi-link-bg); color: var(--libi-link-fg); font-size: 10px; line-height: 1; cursor: pointer; z-index: 6; opacity: 0; transition: opacity .15s; padding: 0; }
.rung-wire:hover .link-cut { opacity: 1; }
.link-cut:hover { background: #7e57c2; color: #fff; border-color: #7e57c2; }

.wire-ins.join-target { background: #7e57c2; color: #fff; box-shadow: 0 0 0 4px rgba(126, 87, 194, .25); }

.rung-notes { display: flex; flex-direction: column; gap: 2px; padding: 6px 16px 2px 16px; border-bottom: 1px solid var(--divider-color, #f0f0f0); }
.rung-note { display: flex; align-items: center; gap: 8px; }
.rung-note-num { flex: 0 0 auto; width: 20px; height: 20px; border-radius: 50%; border: 1px solid var(--divider-color, #e0e0e0); background: var(--secondary-background-color, #fafafa); color: var(--secondary-text-color, #757575); font-size: 11px; font-weight: 800; cursor: pointer; line-height: 1; }
.rung-note-num:hover { border-color: var(--primary-color, #03a9f4); color: var(--primary-color, #03a9f4); }
.rung-notes .rung-comment-input { flex: 1; margin: 0; border: none; border-bottom: 1px dashed transparent; background: transparent; font-style: italic; font-size: 12px; color: var(--secondary-text-color, #616161); padding: 2px 0; }
.rung-notes .rung-comment-input:hover { border-bottom-color: var(--divider-color, #ddd); }
.rung-notes .rung-comment-input:focus { outline: none; border-bottom-color: var(--primary-color, #03a9f4); color: var(--primary-text-color, #212121); }
.rung.rung-flash { background: rgba(3, 169, 244, .07); border-radius: 8px; transition: background .3s; }

.ha-text-btn.online-on { color: var(--libi-ok); font-weight: 700; }

/* [ADDED v3.13.0] The save button is the one filled control in the header, the way Home Assistant
   marks the primary action of an editor. */
.ha-btn-primary { display: inline-flex; align-items: center; gap: 8px; background: var(--primary-color, #03a9f4); color: var(--text-primary-color, #fff); border: none; border-radius: 20px; height: 36px; padding: 0 18px 0 14px; font-size: 14px; font-weight: 500; cursor: pointer; transition: filter .15s, box-shadow .15s; box-shadow: 0 1px 3px rgba(0,0,0,.2); }
.ha-btn-primary:hover { filter: brightness(1.08); box-shadow: 0 2px 6px rgba(0,0,0,.28); }
.ha-btn-primary svg { width: 20px; height: 20px; fill: currentColor; }
.ha-icon-btn svg { fill: currentColor; }

/* [ADDED v3.13.0] The overflow menu of the header, drawn like the one in the automation editor. */
.hdr-menu-wrap { position: relative; }
.hdr-menu { position: absolute; right: 0; top: 46px; min-width: 232px; background: var(--card-background-color, #fff); border: 1px solid var(--divider-color, #e0e0e0); border-radius: 8px; box-shadow: 0 4px 16px rgba(0,0,0,.18); padding: 6px 0; z-index: 400; display: none; }
.hdr-menu.show { display: block; }
.hdr-menu-item { display: flex; align-items: center; gap: 10px; width: 100%; background: none; border: none; text-align: left; padding: 10px 16px; font-size: 14px; color: var(--primary-text-color, #212121); cursor: pointer; font-family: inherit; }
.hdr-menu-item:hover { background: var(--secondary-background-color, #f2f2f2); }
.hdr-menu-item.danger { color: var(--error-color, #db4437); }
.hdr-menu-item[disabled] { opacity: .45; cursor: default; }
.hdr-menu-item[disabled]:hover { background: none; }
.hdr-menu-sep { height: 1px; background: var(--divider-color, #e0e0e0); margin: 6px 0; }

/* [ADDED v3.13.0] The Home Assistant toggle, rebuilt so a net can show the very state that the
   automation list shows: on means the triggers are armed, off means they are disabled. */
.ha-switch { position: relative; display: inline-block; width: 36px; height: 20px; flex: 0 0 auto; }
.ha-switch input { position: absolute; opacity: 0; width: 0; height: 0; }
.ha-switch .track { position: absolute; inset: 0; border-radius: 20px; background: var(--switch-unchecked-track-color, #9e9e9e); opacity: .5; transition: background .2s, opacity .2s; }
.ha-switch .knob { position: absolute; top: 1px; left: 1px; width: 18px; height: 18px; border-radius: 50%; background: var(--switch-unchecked-button-color, #fafafa); box-shadow: 0 1px 3px rgba(0,0,0,.4); transition: transform .2s, background .2s; }
.ha-switch input:checked ~ .track { background: var(--switch-checked-track-color, var(--primary-color, #03a9f4)); opacity: .5; }
.ha-switch input:checked ~ .knob { transform: translateX(16px); background: var(--switch-checked-button-color, var(--primary-color, #03a9f4)); }
.ha-switch.disabled { opacity: .38; }
.ha-switch.disabled .knob, .ha-switch.disabled .track { cursor: default; }
.net-state-wrap { display: flex; align-items: center; gap: 6px; margin-right: 4px; }

/* [ADDED v3.14.0] The name of the open project, next to the logo. */
.project-chip { display: inline-flex; align-items: center; gap: 6px; margin-left: 14px; padding: 4px 10px; border-radius: 14px; background: var(--secondary-background-color, #f2f2f2); border: 1px solid var(--divider-color, #e0e0e0); font-size: 13px; font-weight: 600; color: var(--primary-text-color, #212121); max-width: 260px; }
.project-chip .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--primary-color, #03a9f4); flex: 0 0 auto; }
.project-chip .nm { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.project-chip.none { color: var(--secondary-text-color, #757575); font-weight: 500; }
.project-chip.none .dot { background: var(--secondary-text-color, #bdbdbd); }
.project-chip .dirty { color: var(--warning-color, #ffa600); font-weight: 800; }
@media (max-width: 768px) { .project-chip { max-width: 120px; margin-left: 6px; } }

/* [CHANGED v3.17.0] The variables moved out of the right sidebar into a bar of their own that runs
   the whole width of the screen along the bottom. It behaves like the sidebar: a grip to resize, a
   remembered size, and one button that folds it down to a rail. */
.vars-bar { display: flex; flex-direction: column; flex: 0 0 auto; height: var(--libi-vars-h, 280px); min-height: 40px; max-height: 78vh; background: var(--card-background-color, #fff); border-top: 1px solid var(--divider-color, #e0e0e0); box-shadow: 0 -2px 8px rgba(0,0,0,.06); position: relative; z-index: 12; }
.vars-bar.rail { height: 40px !important; }
.vars-bar.dragging { user-select: none; }
.vars-grip { position: absolute; left: 0; right: 0; top: -3px; height: 7px; cursor: row-resize; z-index: 30; touch-action: none; }
.vars-grip:hover, .vars-grip.active { background: var(--primary-color, #03a9f4); opacity: .35; }
.vars-bar.rail .vars-grip { display: none; }

/* The row that stays visible when the bar is folded: the title, the two tabs, the fold button. */
.vars-top { display: flex; align-items: center; gap: 8px; padding: 5px 10px; min-height: 40px; box-sizing: border-box; border-bottom: 1px solid var(--divider-color, #eee); background: var(--libi-tint); flex: 0 0 auto; }
.vars-title { font-size: 12px; font-weight: 800; letter-spacing: .3px; text-transform: uppercase; color: var(--secondary-text-color, #757575); flex: 0 0 auto; }
.vars-tabs { display: flex; gap: 4px; }
.vars-tab { border: 1px solid transparent; background: none; border-radius: 16px; padding: 5px 14px; font-size: 13px; font-weight: 600; color: var(--secondary-text-color, #757575); cursor: pointer; font-family: inherit; }
.vars-tab:hover { background: var(--libi-hover); }
.vars-tab.on { background: var(--primary-color, #03a9f4); color: var(--text-primary-color, #fff); }
.vars-tab .n { opacity: .75; font-weight: 700; margin-left: 5px; }
.vars-top .spacer { flex: 1; }
.vars-fold { border: 1px solid var(--divider-color, #ddd); background: var(--card-background-color, #fff); color: var(--secondary-text-color, #757575); border-radius: 6px; width: 26px; height: 26px; line-height: 1; font-size: 13px; cursor: pointer; flex: 0 0 auto; padding: 0; }
.vars-fold:hover { border-color: var(--primary-color, #03a9f4); color: var(--primary-color, #03a9f4); }
.vars-body { display: flex; flex-direction: column; flex: 1; min-height: 0; overflow: auto; padding: 10px 12px 12px 12px; gap: 8px; }
.vars-bar.rail .vars-body { display: none; }

/* [CHANGED v3.21.0] The Helper tab used to hold /config/helpers in a frame. That meant a second
   whole copy of the Home Assistant frontend inside the bar, with its own sidebar and its own
   WebSocket, which is why there were two sidebars and why everything crawled. The list is drawn
   here instead, from state the panel already holds, and every dialog it opens is Home Assistant's
   own, so nothing is reimplemented and nothing is loaded twice. */
.helper-view { display: flex; flex-direction: column; flex: 1; min-height: 0; gap: 8px; }
.helper-top { display: flex; align-items: center; gap: 8px; flex: 0 0 auto; flex-wrap: wrap; }
.helper-top input[type="text"] { flex: 1; min-width: 160px; }
.helper-count { font-size: 12px; color: var(--secondary-text-color, #9e9e9e); white-space: nowrap; }
.helper-scroll { flex: 1; min-height: 0; overflow: auto; }
.helper-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.helper-table th { text-align: left; font-size: 11px; text-transform: uppercase; letter-spacing: .3px; color: var(--secondary-text-color, #9e9e9e); font-weight: 800; padding: 6px 8px; border-bottom: 2px solid var(--divider-color, #e0e0e0); position: sticky; top: 0; background: var(--card-background-color, #fff); z-index: 2; }
.helper-table td { padding: 6px 8px; border-bottom: 1px solid var(--divider-color, #f4f4f4); vertical-align: middle; }
.helper-table tbody tr { cursor: pointer; }
.helper-table tbody tr:hover { background: var(--secondary-background-color, #f5f5f5); }
.helper-table .h-ico { width: 26px; text-align: center; font-size: 15px; color: var(--secondary-text-color, #757575); }
.helper-table .h-name { font-weight: 600; max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.helper-table .h-eid { font-family: monospace; font-size: 11px; color: var(--secondary-text-color, #9e9e9e); max-width: 320px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.helper-table .h-area, .helper-table .h-val { color: var(--secondary-text-color, #757575); white-space: nowrap; }
.helper-foot { display: flex; align-items: center; gap: 10px; flex: 0 0 auto; padding-top: 2px; border-top: 1px solid var(--divider-color, #f0f0f0); margin-top: 2px; padding-top: 8px; }
.helper-foot .note { font-size: 11px; color: var(--secondary-text-color, #9e9e9e); }

/* [ADDED v3.22.0] The Create helper dialog, laid out the way Home Assistant lays out its own: a
   search box over a scrolling list of kinds, each row an icon, a name and a chevron. */
.hk-list { max-height: 52vh; overflow: auto; margin: 4px -10px 0 -10px; }
.hk-item { display: flex; align-items: center; gap: 14px; padding: 11px 18px; cursor: pointer; }
.hk-item:hover { background: var(--secondary-background-color, #f2f2f2); }
.hk-item .i { width: 26px; text-align: center; font-size: 17px; color: var(--primary-color, #03a9f4); flex: 0 0 auto; }
.hk-item .n { flex: 1; font-size: 14px; }
.hk-item .c { color: var(--secondary-text-color, #bdbdbd); font-size: 18px; }
.hk-back { background: none; border: none; color: var(--primary-color, #03a9f4); font-size: 13px; cursor: pointer; padding: 0; margin-bottom: 6px; font-family: inherit; }
.hk-note { font-size: 12px; color: var(--secondary-text-color, #9e9e9e); margin: 10px 0 0 0; line-height: 1.5; }
.hk-note a { color: var(--primary-color, #03a9f4); cursor: pointer; text-decoration: underline; }
.hk-item.flow .i { color: var(--secondary-text-color, #9e9e9e); }
.hk-sec { font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: .3px; color: var(--secondary-text-color, #9e9e9e); padding: 10px 18px 4px 18px; }
.hk-form { max-height: 56vh; overflow: auto; margin-right: -6px; padding-right: 6px; }
.hk-row { display: flex; gap: 8px; }
.hk-row > * { flex: 1; min-width: 0; }

/* [ADDED v3.23.0] The week editor of a Schedule: a row per day, each with a switch and a span. */
.hk-days { display: flex; flex-direction: column; border: 1px solid var(--divider-color, #e0e0e0); border-radius: 6px; overflow: hidden; }
.hk-day { display: flex; align-items: center; gap: 10px; padding: 6px 10px; border-bottom: 1px solid var(--divider-color, #f2f2f2); }
.hk-day:last-child { border-bottom: none; }
.hk-day .d { width: 40px; font-size: 12px; font-weight: 700; color: var(--primary-text-color, #212121); }
.hk-day input[type="time"] { width: 104px; font-family: inherit; }
.hk-day.off input[type="time"] { opacity: .4; pointer-events: none; }
.hk-day .to { font-size: 12px; color: var(--secondary-text-color, #9e9e9e); }
.hk-flow { font-size: 13px; color: var(--primary-text-color, #212121); line-height: 1.6; }


/* The scope and type filters. */
.vars-filters { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; flex: 0 0 auto; }
.vars-chip { border: 1px solid var(--divider-color, #ddd); background: var(--card-background-color, #fff); border-radius: 14px; padding: 4px 11px; font-size: 12px; font-weight: 600; color: var(--secondary-text-color, #757575); cursor: pointer; font-family: inherit; }
.vars-chip:hover { border-color: var(--primary-color, #03a9f4); }
.vars-chip.on { background: var(--primary-color, #03a9f4); border-color: var(--primary-color, #03a9f4); color: var(--text-primary-color, #fff); }
.vars-sep { width: 1px; align-self: stretch; background: var(--divider-color, #e0e0e0); margin: 0 4px; }
.vars-filters input[type="text"] { flex: 1; min-width: 160px; }

/* The table itself. */
.vars-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.vars-table th { text-align: left; font-size: 11px; text-transform: uppercase; letter-spacing: .3px; color: var(--secondary-text-color, #9e9e9e); font-weight: 800; padding: 6px 8px; border-bottom: 2px solid var(--divider-color, #e0e0e0); position: sticky; top: 0; background: var(--card-background-color, #fff); z-index: 2; }
.vars-table td { padding: 5px 8px; border-bottom: 1px solid var(--divider-color, #f4f4f4); vertical-align: middle; }
.vars-table tbody tr { cursor: grab; }
.vars-table tbody tr:hover { background: var(--secondary-background-color, #f5f5f5); }
.vars-table tbody tr.dragging { opacity: .45; }
.vars-table .c-name { font-weight: 600; max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.vars-table .c-eid { font-family: monospace; font-size: 11px; color: var(--secondary-text-color, #9e9e9e); max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.vars-table .c-val { font-weight: 700; color: var(--primary-text-color, #212121); white-space: nowrap; }
.vars-table .c-act { text-align: right; white-space: nowrap; }
.vars-table select { font-size: 12px; padding: 2px 4px; }
.vars-table .grab { color: var(--disabled-text-color, #bdbdbd); cursor: grab; user-select: none; }
.type-tag { display: inline-block; font-size: 10px; font-weight: 800; letter-spacing: .4px; padding: 2px 7px; border-radius: 10px; }
.type-BOOL { background: var(--libi-type-bool-bg); color: var(--libi-type-bool-fg); }
.type-INT { background: var(--libi-type-int-bg); color: var(--libi-type-int-fg); }
.type-FLOAT { background: var(--libi-type-float-bg); color: var(--libi-type-float-fg); }
.type-TEXT { background: var(--libi-type-text-bg); color: var(--libi-type-text-fg); }
.type-TIME { background: var(--libi-type-time-bg); color: var(--libi-type-time-fg); }
.type-HA { background: var(--libi-type-ha-bg); color: var(--libi-type-ha-fg); }
.vars-del { border: none; background: none; color: var(--error-color, #db4437); cursor: pointer; font-size: 14px; padding: 2px 5px; border-radius: 4px; }
.vars-del:hover { background: var(--libi-coe-bg); }
.vars-del[disabled] { color: var(--disabled-text-color, #cfcfcf); cursor: default; }
.vars-del[disabled]:hover { background: none; }
.vars-empty { font-size: 12px; color: var(--secondary-text-color, #9e9e9e); padding: 14px 4px; }

/* Adding a variable, inline under the table. */
.vars-new { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; border: 1px dashed var(--divider-color, #ddd); border-radius: 6px; padding: 8px; flex: 0 0 auto; }
.vars-new input, .vars-new select { min-width: 0; }
.vars-new .name { flex: 1; min-width: 170px; }
.vars-new .note { font-size: 11px; color: var(--secondary-text-color, #9e9e9e); flex-basis: 100%; }

/* An element that a variable is being dragged over. */
.libi-el.var-drop, .pin-val.var-drop { outline: 2px dashed var(--primary-color, #03a9f4); outline-offset: 2px; background: rgba(3,169,244,.10); }

@media (max-width: 768px) {
    .vars-bar { max-height: 70vh; }
    .vars-title { display: none; }
    .vars-table .c-eid { display: none; }
}

.libi-el.live-on .el-ico { background: var(--libi-ok-bg); border-color: var(--libi-ok); box-shadow: 0 0 0 2px rgba(46,125,50,.18); }
.libi-el.live-on .plc-block { border-color: var(--libi-ok); box-shadow: 0 0 0 2px rgba(46,125,50,.15); }
.libi-el.live-on .plc-header { background: rgba(46,125,50,.16); color: var(--libi-ok-strong); border-bottom-color: var(--libi-ok); }
.libi-el.live-off .el-ico, .libi-el.live-off .plc-block { opacity: .78; }
.libi-el.live-unknown .el-ico, .libi-el.live-unknown .plc-block { border-style: dashed; opacity: .6; }
.libi-el.live-fresh .el-ico, .libi-el.live-fresh .plc-block { animation: livePulse 1.2s ease-out 2; }
@keyframes livePulse { 0% { box-shadow: 0 0 0 0 rgba(46,125,50,.55); } 100% { box-shadow: 0 0 0 12px rgba(46,125,50,0); } }
.live-val { position: absolute; top: calc(100% + 2px); left: 50%; transform: translateX(-50%); display: flex; gap: 6px; align-items: baseline; white-space: nowrap; pointer-events: none; z-index: 6; }
.live-now { font-size: 11px; font-weight: 800; color: var(--libi-ok-strong); background: var(--libi-ok-bg); border: 1px solid var(--libi-ok-border); border-radius: 4px; padding: 1px 5px; }
.live-prev { font-size: 10px; color: var(--secondary-text-color, #9e9e9e); background: var(--secondary-background-color, #f5f5f5); border: 1px solid var(--divider-color, #e0e0e0); border-radius: 4px; padding: 1px 5px; }

.rung.rung-live { background: rgba(46,125,50,.05); border-radius: 8px; }
.net-live-note { font-size: 11px; color: var(--libi-ok); background: var(--libi-ok-bg); border: 1px solid var(--libi-ok-border); border-radius: 10px; padding: 2px 8px; margin-left: 8px; }

.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.5); z-index: 2000; display: flex; align-items: center; justify-content: center; }
.modal { background: var(--card-background-color, #fff); padding: 24px; border-radius: 12px; box-shadow: 0 10px 30px rgba(0,0,0,0.3); width: 450px; max-width: 90vw; display: flex; flex-direction: column; gap: 16px; max-height: 80vh; direction: ltr; }
.modal-title { font-size: 18px; font-weight: bold; margin: 0; }
.auto-list { flex: 1; overflow-y: auto; border: 1px solid var(--divider-color, #e0e0e0); border-radius: 6px; display: flex; flex-direction: column; background: var(--secondary-background-color, #fafafa); }
.auto-item { padding: 12px; cursor: pointer; border-bottom: 1px solid var(--divider-color, #eee); transition: background 0.2s; display: flex; flex-direction: column; gap: 4px; }
.auto-item:hover { background: rgba(3, 169, 244, 0.1); }
.auto-item-name { font-weight: bold; font-size: 14px; color: var(--primary-text-color, #212121); }
.auto-item-id { font-size: 11px; color: var(--secondary-text-color, #888); font-family: monospace; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 8px; }
.btn { padding: 8px 16px; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 600; }
.btn-primary { background: var(--primary-color,#03a9f4); color: #fff; }
.btn-danger { background: var(--error-color,#f44336); color: #fff; }
.btn-ghost { background: transparent; border: 1px solid var(--divider-color, #e0e0e0); color: var(--primary-text-color, #212121); }
.ha-icon-btn { background: none; border: none; cursor: pointer; color: var(--app-header-text-color, var(--primary-text-color, #212121)); opacity: 0.7; width: 48px; height: 48px; border-radius: 50%; display: flex; align-items: center; justify-content: center; transition: background-color .15s, opacity .15s; padding: 0; }
.ha-icon-btn svg { width: 24px; height: 24px; }
.ha-icon-btn:hover { background-color: rgba(127, 127, 127, 0.15); opacity: 1; }
.ha-text-btn { background: none; border: none; cursor: pointer; color: var(--primary-color, #03a9f4); font-weight: 500; font-size: 14px; padding: 0 12px; height: 36px; transition: background 0.2s; border-radius: 4px; }
.ha-text-btn:hover { background: rgba(3, 169, 244, 0.1); }
.ha-text-btn.danger { color: var(--error-color, #f44336); }
.ha-text-btn.danger:hover { background: rgba(244, 67, 54, 0.1); }
/* [ADDED v3.36.0] AI chat, under the Inspector in the same sidebar. Open, it shares the height with
   the Inspector; closed, only its header shows. Every colour comes from the theme or the tokens. */
.ai-mount { flex: 0 0 auto; display: flex; flex-direction: column; min-height: 0; border-top: 2px solid var(--divider-color, #e0e0e0); }
.ai-mount.ai-open { flex: 1.2 1 0; }
.sidebar.rail .ai-mount { display: none; }
.ai-chat { display: flex; flex-direction: column; flex: 1; min-height: 0; }
.ai-head { display: flex; align-items: center; gap: 6px; padding: 6px 8px; background: var(--libi-tint); border-bottom: 1px solid var(--divider-color, #e0e0e0); min-height: 36px; box-sizing: border-box; }
.ai-head .grow { flex: 1; min-width: 0; font-size: 12px; font-weight: 700; color: var(--secondary-text-color, #757575); text-transform: uppercase; letter-spacing: .3px; }
.ai-model { font-size: 11px; color: var(--secondary-text-color, #757575); max-width: 40%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ai-new, .ai-all { font-size: 12px; padding: 4px 8px; min-height: 32px; }
.ai-body { display: flex; flex-direction: column; flex: 1; min-height: 0; }
.ai-log { flex: 1; min-height: 0; overflow-y: auto; padding: 10px; display: flex; flex-direction: column; gap: 8px; }
.ai-msg { padding: 8px 10px; border-radius: 10px; font-size: 13px; line-height: 1.45; white-space: pre-wrap; overflow-wrap: anywhere; max-width: 92%; }
.ai-msg.user { align-self: flex-end; background: var(--primary-color, #03a9f4); color: var(--text-primary-color, #fff); }
.ai-msg.ai { align-self: flex-start; background: var(--secondary-background-color, #f2f2f2); color: var(--primary-text-color, #212121); }
.ai-msg.error { align-self: stretch; max-width: none; background: var(--libi-coe-bg); color: var(--libi-coe-fg); }
.ai-msg.error ul { margin: 6px 0 0; padding-inline-start: 18px; }
.ai-hint, .ai-busy { font-size: 12px; color: var(--secondary-text-color, #757575); line-height: 1.45; }
.ai-busy { font-style: italic; }
.ai-compose { display: flex; gap: 6px; padding: 8px; border-top: 1px solid var(--divider-color, #e0e0e0); align-items: flex-end; }
.ai-input { flex: 1; resize: none; min-height: 40px; max-height: 120px; padding: 8px 10px; border: 1.5px solid var(--divider-color, #e0e0e0); border-radius: 8px; font: inherit; font-size: 13px; background: var(--card-background-color, #fff); color: var(--primary-text-color, #212121); box-sizing: border-box; }
.ai-input:focus, .ai-filter:focus { outline: none; border-color: var(--primary-color, #03a9f4); }
.ai-send, .ai-build, .ai-add { min-height: 40px; }
.ai-build, .ai-add { width: 100%; }
.ai-chat .btn:disabled { opacity: .55; cursor: default; }
.ai-plan { border: 1px solid var(--divider-color, #e0e0e0); border-radius: 10px; padding: 10px; display: flex; flex-direction: column; gap: 12px; background: var(--libi-tint); }
.ai-plan-title { font-weight: 700; font-size: 13px; }
.ai-level { font-size: 10px; text-transform: uppercase; padding: 2px 6px; border-radius: 4px; background: var(--libi-pin-bg); color: var(--libi-pin-fg); }
.ai-role { display: flex; flex-direction: column; gap: 4px; }
.ai-role-head { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; font-size: 13px; }
.ai-count { font-size: 11px; color: var(--secondary-text-color, #757575); flex: 0 0 auto; }
.ai-list { max-height: 180px; overflow-y: auto; border: 1px solid var(--divider-color, #e0e0e0); border-radius: 8px; background: var(--card-background-color, #fff); }
.ai-item { display: flex; align-items: center; gap: 8px; padding: 6px 8px; min-height: 40px; box-sizing: border-box; cursor: pointer; border-bottom: 1px solid var(--divider-color, #e0e0e0); }
.ai-item:last-child { border-bottom: none; }
.ai-item input { width: 18px; height: 18px; flex: 0 0 auto; margin: 0; }
.ai-item-text { display: flex; flex-direction: column; min-width: 0; }
.ai-item-name { font-size: 13px; color: var(--primary-text-color, #212121); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ai-item-id { font-size: 11px; font-family: monospace; color: var(--secondary-text-color, #757575); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ai-filter { width: 100%; padding: 6px 8px; min-height: 34px; border: 1.5px solid var(--divider-color, #e0e0e0); border-radius: 7px; font-size: 13px; background: var(--card-background-color, #fff); color: var(--primary-text-color, #212121); box-sizing: border-box; }
.ai-role-acts { display: flex; gap: 4px; }
.ai-note { font-size: 12px; color: var(--secondary-text-color, #757575); line-height: 1.4; }
.ai-note.warn { color: var(--libi-notice-head); }
.ai-note.danger { color: var(--libi-coe-fg); background: var(--libi-coe-bg); padding: 6px 8px; border-radius: 6px; font-weight: 600; }
.ai-question { display: flex; flex-direction: column; gap: 6px; }
.ai-q-text { font-size: 13px; font-weight: 600; }
.ai-choices { display: flex; flex-wrap: wrap; gap: 6px; }
.ai-chip { border: 1px solid var(--divider-color, #e0e0e0); background: var(--card-background-color, #fff); color: var(--primary-text-color, #212121); border-radius: 16px; padding: 6px 12px; font-size: 12px; cursor: pointer; min-height: 32px; }
.ai-chip.on { border-color: var(--primary-color, #03a9f4); background: var(--libi-pin-bg); color: var(--libi-pin-fg); }
.ai-result { display: flex; flex-direction: column; gap: 8px; }
.ai-yaml summary { cursor: pointer; font-size: 12px; color: var(--secondary-text-color, #757575); }
.ai-yaml pre, .ai-card pre { margin: 6px 0 0; padding: 8px; background: #1e1e1e; color: #d4d4d4; border-radius: 6px; font-size: 11px; overflow: auto; max-height: 220px; white-space: pre; direction: ltr; text-align: start; }
.ai-card { border: 1px dashed var(--divider-color, #e0e0e0); border-radius: 8px; padding: 8px; display: flex; flex-direction: column; gap: 4px; }
.ai-card-head { display: flex; justify-content: space-between; align-items: center; font-size: 13px; }
.ai-setup { padding: 12px; }
.ai-setup p { margin: 0 0 8px; font-size: 13px; }
.ai-path { font-family: monospace; font-size: 12px; }
.ai-copy-buffer { position: absolute; inset-inline-start: -9999px; }
@media (max-width: 768px) { .ai-list { max-height: 150px; } .ai-mount.ai-open { flex: 1 1 auto; } }
`;