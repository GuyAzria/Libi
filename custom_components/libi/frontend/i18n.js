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
class I18nManager {
  constructor(defaultLang = 'en') {
    this.currentLang = defaultLang;
    this.translations = {};
  }

  async loadLanguage(lang) {
    try {
      const response = await fetch(`./locales/${lang}.json`);
      if (!response.ok) {
        throw new Error(`Could not fetch ${lang}.json`);
      }
      const data = await response.json();
      this.translations[lang] = data;
      this.currentLang = lang;
    } catch (error) {
      console.error(`Error loading language ${lang}:`, error);
      // Fallback to 'en' if not already trying 'en'
      if (lang !== 'en') {
        console.log("Falling back to 'en'");
        await this.loadLanguage('en');
      }
    }
  }

  t(key, params = {}) {
    const dict = this.translations[this.currentLang] || {};
    let text = dict[key] || key;

    // Basic placeholder replacement (e.g., {name})
    for (const [paramKey, paramValue] of Object.entries(params)) {
      text = text.replace(new RegExp(`{${paramKey}}`, 'g'), paramValue);
    }

    return text;
  }
}

export const i18n = new I18nManager();
