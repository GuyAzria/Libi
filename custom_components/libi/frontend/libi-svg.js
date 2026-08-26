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
 * LIBI SVG Icon Library
 * LIBI - LIBI for Home Assistant
 * v3.4.0
 * LIBI_ICONS: Core ladder diagram element icons (Monochrome / currentColor)
 *   - All icons use viewBox="0 0 100 100" and inherit color via currentColor.
 *   - Import and inject the SVG string directly into innerHTML where needed.
 */

// [ADDED v3.4.0 | 2026-08-20] Purpose: Renamed LADDER_ICONS to LIBI_ICONS to complete rebranding.
// [ADDED v1.5.1 | 2026-08-10] Purpose: Centralised inline SVG library replacing the
//   external icons/ directory — no file serving or HACS subdirectory copy required.
// [ADDED v1.74.0 | 2026-08-17] Purpose: Every contact and coil variant is now a drawing of its own.

// Letter strokes, drawn between the contact bars / inside the coil parentheses.
const MARK = {
  P: `<path d="M68 69L68 31L80 31Q89 31 89 40.5Q89 50 80 50L68 50" stroke="currentColor" stroke-width="5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>`,
  N: `<path d="M68 69L68 31L88 69L88 31" stroke="currentColor" stroke-width="5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>`,
  S: `<path d="M88 38Q88 31 78 31Q68 31 68 40Q68 48 78 50Q88 52 88 60Q88 69 78 69Q68 69 68 62" stroke="currentColor" stroke-width="5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>`,
  R: `<path d="M68 69L68 31L80 31Q89 31 89 40.5Q89 50 80 50L68 50L89 69" stroke="currentColor" stroke-width="5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>`,
};

const SDW = `<defs><filter id="sdw"><feDropShadow dx="1" dy="2" stdDeviation="1.5" flood-opacity="0.3"/></filter></defs>`;
const CONTACT_BASE = `<path d="M0 50L60 50M95 50L155 50" stroke="currentColor" stroke-width="5" fill="none" stroke-linecap="round"/><path d="M60 15L60 85M95 15L95 85" stroke="currentColor" stroke-width="7" fill="none" stroke-linecap="round" filter="url(#sdw)"/>`;
const COIL_BASE = `<path d="M0 50L45 50M110 50L155 50" stroke="currentColor" stroke-width="5" fill="none" stroke-linecap="round"/><path d="M60 15Q35 50 60 85M95 15Q120 50 95 85" stroke="currentColor" stroke-width="7" fill="none" stroke-linecap="round" filter="url(#sdw)"/>`;

export const LIBI_ICONS = {
  contact_no: `<svg viewBox="0 0 155 100">${SDW}${CONTACT_BASE}</svg>`,
  contact_nc: `<svg viewBox="0 0 155 100">${SDW}${CONTACT_BASE}<path d="M50 85L105 15" stroke="currentColor" stroke-width="6" fill="none" stroke-linecap="round" filter="url(#sdw)"/></svg>`,
  contact_p:  `<svg viewBox="0 0 155 100">${SDW}${CONTACT_BASE}${MARK.P}</svg>`,
  contact_n:  `<svg viewBox="0 0 155 100">${SDW}${CONTACT_BASE}${MARK.N}</svg>`,
  coil:       `<svg viewBox="0 0 155 100">${SDW}${COIL_BASE}</svg>`,
  coil_s:     `<svg viewBox="0 0 155 100">${SDW}${COIL_BASE}${MARK.S}</svg>`,
  coil_r:     `<svg viewBox="0 0 155 100">${SDW}${COIL_BASE}${MARK.R}</svg>`,
  timer:      `<svg viewBox="0 0 155 100">${SDW}<path d="M0 50L45 50M110 50L155 50" stroke="currentColor" stroke-width="5" fill="none" stroke-linecap="round"/><rect x="45" y="15" width="65" height="70" stroke="currentColor" stroke-width="6" fill="var(--card-background-color, #fff)" rx="8" filter="url(#sdw)"/><text x="77.5" y="58" font-family="sans-serif" font-size="22" text-anchor="middle" font-weight="800" fill="currentColor">TMR</text></svg>`,
  custom:     `<svg viewBox="0 0 155 100">${SDW}<path d="M0 50L45 50M110 50L155 50" stroke="currentColor" stroke-width="5" fill="none" stroke-linecap="round"/><rect x="45" y="15" width="65" height="70" stroke="currentColor" stroke-width="6" fill="var(--card-background-color, #fff)" rx="12" filter="url(#sdw)"/><text x="77.5" y="58" font-family="sans-serif" font-size="22" text-anchor="middle" font-weight="800" fill="currentColor">FB</text></svg>`,
};