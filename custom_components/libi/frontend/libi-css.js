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
 * v3.4.0
 */
// [ADDED v3.4.0 | 2026-08-20] Purpose: Renamed all .ladder-* CSS classes to .libi-* to match the rebranding.
export const getStyles = () => `
:host { display: block; height: 100vh; overflow-y: hidden; background: var(--primary-background-color, #f5f5f5); color: var(--primary-text-color, #212121); font-family: var(--primary-font-family, sans-serif); box-sizing: border-box; direction: ltr !important; text-align: left; }
*, *::before, *::after { box-sizing: border-box; }

.panel-layout { display: flex; flex-direction: column; height: 100vh; }
.header { display: flex; justify-content: space-between; align-items: center; padding: 0 16px; min-height: 56px; background: var(--app-header-background-color, var(--primary-background-color, #fff)); border-bottom: 1px solid var(--divider-color, #e0e0e0); z-index: 200; direction: ltr; }
.header-title { font-size: 20px; font-weight: 500; }
.header-acts { display: flex; gap: 8px; align-items: center; }

.main-content { display: flex; flex-direction: row; flex: 1; height: calc(100vh - 56px); overflow: hidden; }
.canvas { flex: 1; overflow: auto; padding: 20px; display: flex; flex-direction: column; gap: 20px; -webkit-overflow-scrolling: touch; }
.sidebar { width: 320px; background: var(--card-background-color, #fff); border-left: 1px solid var(--divider-color, #e0e0e0); display: flex; flex-direction: column; box-shadow: -2px 0 8px rgba(0,0,0,0.05); z-index: 10; }

@media (max-width: 768px) {
    .main-content { flex-direction: column; }
    .sidebar { width: 100%; border-left: none; border-top: 2px solid var(--primary-color, #03a9f4); flex-basis: 40%; max-height: 40vh; box-shadow: 0 -2px 8px rgba(0,0,0,0.1); }
    .header-acts .ha-text-btn { font-size: 11px; padding: 0 6px; }
    .canvas { padding: 10px; }
}

.sidebar-hdr { padding: 16px; border-bottom: 1px solid var(--divider-color, #eee); font-weight: bold; font-size: 16px; background: rgba(0,0,0,0.02); }
.sidebar-body { padding: 16px; overflow-y: auto; flex: 1; display: flex; flex-direction: column; gap: 16px; }

.fgrp { display: flex; flex-direction: column; gap: 6px; margin-bottom: 12px; }
.fgrp label { font-size: 12px; color: var(--secondary-text-color,#757575); font-weight: 600; text-transform: uppercase; }
.fgrp input, .fgrp select, .fgrp textarea { padding: 10px 12px; border: 1.5px solid var(--divider-color,#ddd); border-radius: 7px; font-size: 14px; background: var(--secondary-background-color,#fafafa); color: var(--primary-text-color,#212121); outline: none; font-family: inherit; direction: ltr; }
.fgrp input[type="checkbox"] { width: 18px; height: 18px; cursor: pointer; }
.fgrp input:focus, .fgrp select:focus, .fgrp textarea:focus { border-color: var(--primary-color,#03a9f4); }
.checkbox-grp { flex-direction: row; align-items: center; gap: 10px; }

.net { background: var(--card-background-color,#fff); border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,.08); overflow: hidden; border-left: 6px solid var(--rc, var(--divider-color,#ddd)); transition: box-shadow 0.3s; flex: 0 0 auto; }
.net-hdr { display: flex; justify-content: space-between; align-items: center; padding: 13px 16px; background: rgba(0,0,0,.02); border-bottom: 1px solid var(--divider-color,#eee); cursor: pointer; user-select: none; }
.net-hdr-l { display: flex; align-items: center; gap: 8px; flex: 1; }
.net-hdr-r { display: flex; align-items: center; gap: 8px; }
.net-name { font-size: 15px; flex: 1; display:flex; align-items:center; gap:8px; flex-wrap: nowrap; overflow: hidden; }
.net-name span { white-space: nowrap; flex-shrink: 0; }
.net-name input { border:none; background:transparent; font-size:15px; font-weight:700; color:inherit; outline:none; width:100%; direction: ltr; min-width: 150px; }
.net-body { display: flex; flex-direction: column; align-items: stretch; overflow: hidden; max-height: 40000px; transition: max-height 0.3s ease; flex: 0 0 auto; }
.net.collapsed .net-body { max-height: 0 !important; border-bottom: none; }

.net-toolbar { display: flex; gap: 12px; padding: 8px 16px; background: #fdfdfd; border-bottom: 1px solid var(--divider-color,#eee); align-items: center; }
.rung-comment-input { width: 100%; margin-left: 16px; border: none; border-bottom: 1px dashed var(--divider-color,#ccc); background: transparent; font-size: 13px; font-style: italic; color: var(--secondary-text-color,#555); padding: 4px 8px; margin-bottom: 8px; outline: none; transition: border-color 0.2s; direction: ltr; }
.rung-comment-input:focus { border-bottom-color: var(--primary-color,#03a9f4); }

.net-menu-wrapper { position: relative; }
.net-kebab { background: none; border: none; cursor: pointer; color: var(--secondary-text-color, #757575); padding: 6px; border-radius: 50%; display: flex; align-items: center; justify-content: center; transition: background 0.2s; }
.net-kebab:hover { background: rgba(0,0,0,0.05); color: var(--primary-text-color, #212121); }
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

.el-lbl { position: absolute; bottom: calc(100% - 16px); left: 50%; transform: translateX(-50%); font-size: 11px; font-weight: 700; color: var(--primary-text-color, #111); background: #ffffff; border: 1.5px solid var(--divider-color, #c0c0c0); border-radius: 5px; padding: 3px 6px; min-width: 40px; text-align: center; line-height: 1.2; white-space: normal; word-wrap: break-word; word-break: break-word; box-shadow: 0 2px 5px rgba(0,0,0,0.12); z-index: 4; cursor: pointer; direction: ltr; unicode-bidi: plaintext; }
.el-lbl:hover { background: var(--secondary-background-color, #f0f0f0); border-color: var(--primary-color, #03a9f4); }

/* VERTICAL EXPANDING PLC BLOCKS */
.plc-block { display: flex; flex-direction: column; width: 100%; background: var(--card-background-color, #f8f9fa); border: 1.5px solid var(--primary-text-color, #555); border-radius: 4px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); position: relative; align-items: stretch; cursor: default; z-index: 2; transition: all 0.2s; margin: 6px auto 0 auto; min-height: 60px; padding-bottom: 6px; }
.plc-block:hover { transform: translateY(-2px); box-shadow: 0 4px 8px rgba(0,0,0,0.15); }
.plc-header { height: 20px; line-height: 14px; font-weight: 900; font-size: 11px; text-align: center; border-bottom: 1px solid var(--divider-color, #ccc); background: rgba(0,0,0,0.05); padding: 3px; box-sizing: border-box; cursor: pointer; }
.power-row { display: flex; justify-content: space-between; padding: 0 6px; height: 24px; align-items: center; box-sizing: border-box; font-size: 10px; font-weight: bold; }
.plc-row { display: flex; justify-content: space-between; padding: 4px 6px; box-sizing: border-box; }

.plc-col-l { display: flex; flex-direction: column; align-items: flex-start; max-width: 49%; gap: 3px; }
.plc-col-r { display: flex; flex-direction: column; align-items: flex-end; max-width: 48%; gap: 3px; }
.plc-col-l.empty, .plc-col-r.empty { width: 48%; }

.pin-lbl { font-size: 10px; font-weight: 800; color: #333; line-height: 1; pointer-events: none; }
.pin-val { background: #e3f2fd; color: #0277bd; border: 1px solid #03a9f4; border-radius: 4px; padding: 4px; font-size: 10px; font-family: monospace; white-space: normal; word-wrap: break-word; overflow-wrap: anywhere; word-break: normal; max-width: 100%; box-sizing: border-box; cursor: pointer; transition: all 0.2s; box-shadow: 0 1px 2px rgba(0,0,0,0.05); direction: ltr; unicode-bidi: plaintext; text-align: left; }
.pin-val:hover { background: #b3e5fc; border-color: #0288d1; transform: translateY(-1px); box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
.plc-col-l .pin-val { text-align: left; }
.plc-col-r .pin-val { text-align: right; }

/* ⚡ IS_TRIGGER STYLES */
.libi-el.is-trigger .el-ico { background-color: #fff8e1; border-color: #f9a825; box-shadow: 0 1px 4px rgba(249, 168, 37, 0.4); }
.libi-el.is-trigger .plc-block { background-color: #fff8e1; border-color: #f9a825; }
.libi-el.is-trigger .plc-header { background-color: rgba(249, 168, 37, 0.18); color: #d97706; border-bottom-color: #f9a825; }
.trigger-bottom-lbl { position: absolute; top: calc(100% + 4px); left: 50%; transform: translateX(-50%); font-size: 10px; font-weight: 800; color: #a16207; background: #fff8e1; padding: 2px 6px; border-radius: 4px; border: 1px solid #f9a825; z-index: 5; pointer-events: none; }

/* ERROR LINTER STYLES */
.libi-el.has-error .plc-block { border-color: var(--error-color, #f44336) !important; box-shadow: 0 0 8px rgba(244,67,54,0.4) !important; }
.libi-el.has-error .el-ico { border-color: var(--error-color, #f44336) !important; box-shadow: 0 0 8px rgba(244,67,54,0.4) !important; }
.pin-val.has-error, .el-lbl.has-error { border-color: var(--error-color, #f44336) !important; color: var(--error-color, #f44336) !important; background: #ffebee !important; }
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
.pal-btn.trigger-on { border-color: #f9a825; background: #fff8e1; color: #a16207; }
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

.net-notice { margin: 4px 16px 0 16px; border: 1px solid #ffcc80; background: #fff8e1; border-radius: 8px; padding: 10px 12px; max-width: 900px; }
.net-notice-head { display: flex; justify-content: space-between; align-items: center; font-weight: 700; font-size: 13px; color: #e65100; }
.net-notice-x { border: none; background: transparent; cursor: pointer; font-size: 13px; color: #a1887f; padding: 0 4px; }
.net-notice-x:hover { color: #e65100; }
.net-notice-body { font-size: 12px; color: var(--secondary-text-color, #616161); margin: 4px 0 6px 0; }
.net-notice-list { margin: 0; padding-inline-start: 18px; font-size: 12px; font-family: monospace; color: #5d4037; max-height: 160px; overflow: auto; }
.net-notice-more { font-size: 11px; color: #8d6e63; margin-top: 4px; }

.link-cut { position: absolute; width: 18px; height: 18px; border-radius: 50%; border: 1px solid #b39ddb; background: #ede7f6; color: #5e35b1; font-size: 10px; line-height: 1; cursor: pointer; z-index: 6; opacity: 0; transition: opacity .15s; padding: 0; }
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

.ha-text-btn.online-on { color: #2e7d32; font-weight: 700; }
.libi-el.live-on .el-ico { background: #e8f5e9; border-color: #2e7d32; box-shadow: 0 0 0 2px rgba(46,125,50,.18); }
.libi-el.live-on .plc-block { border-color: #2e7d32; box-shadow: 0 0 0 2px rgba(46,125,50,.15); }
.libi-el.live-on .plc-header { background: rgba(46,125,50,.16); color: #1b5e20; border-bottom-color: #2e7d32; }
.libi-el.live-off .el-ico, .libi-el.live-off .plc-block { opacity: .78; }
.libi-el.live-unknown .el-ico, .libi-el.live-unknown .plc-block { border-style: dashed; opacity: .6; }
.libi-el.live-fresh .el-ico, .libi-el.live-fresh .plc-block { animation: livePulse 1.2s ease-out 2; }
@keyframes livePulse { 0% { box-shadow: 0 0 0 0 rgba(46,125,50,.55); } 100% { box-shadow: 0 0 0 12px rgba(46,125,50,0); } }
.live-val { position: absolute; top: calc(100% + 2px); left: 50%; transform: translateX(-50%); display: flex; gap: 6px; align-items: baseline; white-space: nowrap; pointer-events: none; z-index: 6; }
.live-now { font-size: 11px; font-weight: 800; color: #1b5e20; background: #e8f5e9; border: 1px solid #a5d6a7; border-radius: 4px; padding: 1px 5px; }
.live-prev { font-size: 10px; color: #9e9e9e; background: #f5f5f5; border: 1px solid #e0e0e0; border-radius: 4px; padding: 1px 5px; }

.rung.rung-live { background: rgba(46,125,50,.05); border-radius: 8px; }
.net-live-note { font-size: 11px; color: #2e7d32; background: #e8f5e9; border: 1px solid #a5d6a7; border-radius: 10px; padding: 2px 8px; margin-left: 8px; }

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
`;