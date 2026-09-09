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
  // [ADDED v3.30.0] A capital T, drawn on the same 68 to 89 by 31 to 69 box the other marks use.
  T: `<path d="M67 31L90 31M78.5 31L78.5 69" stroke="currentColor" stroke-width="5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>`,
};

const SDW = `<defs><filter id="sdw"><feDropShadow dx="1" dy="2" stdDeviation="1.5" flood-opacity="0.3"/></filter></defs>`;
const CONTACT_BASE = `<path d="M0 50L60 50M95 50L155 50" stroke="currentColor" stroke-width="5" fill="none" stroke-linecap="round"/><path d="M60 15L60 85M95 15L95 85" stroke="currentColor" stroke-width="7" fill="none" stroke-linecap="round" filter="url(#sdw)"/>`;
const COIL_BASE = `<path d="M0 50L45 50M110 50L155 50" stroke="currentColor" stroke-width="5" fill="none" stroke-linecap="round"/><path d="M60 15Q35 50 60 85M95 15Q120 50 95 85" stroke="currentColor" stroke-width="7" fill="none" stroke-linecap="round" filter="url(#sdw)"/>`;

// [ADDED v3.13.0] The same Material Design Icons the Home Assistant frontend draws, so the header
// of LIBI reads as part of Home Assistant rather than as a different application.
export const MDI = {
    save: 'M15,9H5V5H15M12,19A3,3 0 0,1 9,16A3,3 0 0,1 12,13A3,3 0 0,1 15,16A3,3 0 0,1 12,19M17,3H5C3.89,3 3,3.9 3,5V19A2,2 0 0,0 5,21H19A2,2 0 0,0 21,19V7L17,3Z',
    undo: 'M12.5,8C9.85,8 7.45,9 5.6,10.6L2,7V16H11L7.38,12.38C8.77,11.22 10.54,10.5 12.5,10.5C16.04,10.5 19.05,12.81 20.1,16L22.47,15.22C21.08,11.03 17.15,8 12.5,8Z',
    redo: 'M18.4,10.6C16.55,9 14.15,8 11.5,8C6.85,8 2.92,11.03 1.54,15.22L3.9,16C4.95,12.81 7.95,10.5 11.5,10.5C13.45,10.5 15.23,11.22 16.62,12.38L13,16H22V7L18.4,10.6Z',
    dots: 'M12,16A2,2 0 0,1 14,18A2,2 0 0,1 12,20A2,2 0 0,1 10,18A2,2 0 0,1 12,16M12,10A2,2 0 0,1 14,12A2,2 0 0,1 12,14A2,2 0 0,1 10,12A2,2 0 0,1 12,10M12,4A2,2 0 0,1 14,6A2,2 0 0,1 12,8A2,2 0 0,1 10,6A2,2 0 0,1 12,4Z',
    bug: 'M14,12H10V10H14M14,16H10V14H14M20,8H17.19C16.74,7.22 16.12,6.55 15.37,6.04L17,4.41L15.59,3L13.42,5.17C12.96,5.06 12.5,5 12,5C11.5,5 11.04,5.06 10.59,5.17L8.41,3L7,4.41L8.62,6.04C7.88,6.55 7.26,7.22 6.81,8H4V10H6.09C6.04,10.33 6,10.66 6,11V12H4V14H6V15C6,15.34 6.04,15.67 6.09,16H4V18H6.81C7.85,19.79 9.78,21 12,21C14.22,21 16.15,19.79 17.19,18H20V16H17.91C17.96,15.67 18,15.34 18,15V14H20V12H18V11C18,10.66 17.96,10.33 17.91,10H20V8Z',
    trashCan: 'M19,4H15.5L14.5,3H9.5L8.5,4H5V6H19M6,19A2,2 0 0,0 8,21H16A2,2 0 0,0 18,19V7H6V19Z',
    unfold: 'M12,18.17L8.83,15L7.42,16.41L12,21L16.59,16.41L15.17,15M12,5.83L15.17,9L16.58,7.59L12,3L7.41,7.59L8.83,9L12,5.83Z',
    filePlus: 'M13,9H18.5L13,3.5V9M6,2H14L20,8V20A2,2 0 0,1 18,22H6C4.89,22 4,21.1 4,20V4C4,2.89 4.89,2 6,2M11,15V18H13V15H16V13H13V10H11V13H8V15H11Z',
    folderOpen: 'M6.1,10L4,18V8H21A2,2 0 0,0 19,6H12L10,4H4A2,2 0 0,0 2,6V18A2,2 0 0,0 4,20H19C19.9,20 20.7,19.4 20.9,18.5L23.2,10H6.1M19,18H6L7.6,12H20.6L19,18Z',
    close: 'M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z',
    collapse: 'M4,2H6V4C6,4.44 6.45,5 7,5H17C17.55,5 18,4.44 18,4V2H20V4A3,3 0 0,1 17,7H7A3,3 0 0,1 4,4V2M4,22V20A3,3 0 0,1 7,17H17A3,3 0 0,1 20,20V22H18V20C18,19.56 17.55,19 17,19H7C6.45,19 6,19.56 6,20V22H4Z',
};

export const LIBI_ICONS = {
  contact_no: `<svg viewBox="0 0 155 100">${SDW}${CONTACT_BASE}</svg>`,
  contact_nc: `<svg viewBox="0 0 155 100">${SDW}${CONTACT_BASE}<path d="M50 85L105 15" stroke="currentColor" stroke-width="6" fill="none" stroke-linecap="round" filter="url(#sdw)"/></svg>`,
  contact_p:  `<svg viewBox="0 0 155 100">${SDW}${CONTACT_BASE}${MARK.P}</svg>`,
  contact_n:  `<svg viewBox="0 0 155 100">${SDW}${CONTACT_BASE}${MARK.N}</svg>`,
  coil:       `<svg viewBox="0 0 155 100">${SDW}${COIL_BASE}</svg>`,
  coil_s:     `<svg viewBox="0 0 155 100">${SDW}${COIL_BASE}${MARK.S}</svg>`,
  coil_r:     `<svg viewBox="0 0 155 100">${SDW}${COIL_BASE}${MARK.R}</svg>`,
  // [ADDED v3.30.0] The toggle coil. It does not drive the output to a state, it flips whatever
  // state the thing is in, so the letter sits between the two arcs like S and R do.
  coil_t:     `<svg viewBox="0 0 155 100">${SDW}${COIL_BASE}${MARK.T}</svg>`,
  timer:      `<svg viewBox="0 0 155 100">${SDW}<path d="M0 50L45 50M110 50L155 50" stroke="currentColor" stroke-width="5" fill="none" stroke-linecap="round"/><rect x="45" y="15" width="65" height="70" stroke="currentColor" stroke-width="6" fill="var(--card-background-color, #fff)" rx="8" filter="url(#sdw)"/><text x="77.5" y="58" font-family="sans-serif" font-size="22" text-anchor="middle" font-weight="800" fill="currentColor">TMR</text></svg>`,
  custom:     `<svg viewBox="0 0 155 100">${SDW}<path d="M0 50L45 50M110 50L155 50" stroke="currentColor" stroke-width="5" fill="none" stroke-linecap="round"/><rect x="45" y="15" width="65" height="70" stroke="currentColor" stroke-width="6" fill="var(--card-background-color, #fff)" rx="12" filter="url(#sdw)"/><text x="77.5" y="58" font-family="sans-serif" font-size="22" text-anchor="middle" font-weight="800" fill="currentColor">FB</text></svg>`,
};