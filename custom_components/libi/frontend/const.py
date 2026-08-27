# -*- coding: utf-8 -*-
# LIBI for Home Assistant
# Copyright (C) 2026 Guy Azria
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for
# more details. <https://www.gnu.org/licenses/>.
"""Constants for the LIBI integration."""
# v3.3.0
# [ADDED v3.3.0 | 2026-08-20] Purpose: Updated domain and panel URL constants for libi rebranding.

DOMAIN = "libi"
PANEL_URL = "libi"
PANEL_TITLE = "LIBI"
PANEL_ICON = "mdi:ladder"

CONF_AI_MODE = "ai_mode"
AI_MODE_NONE = "No AI"
AI_MODE_LOCAL = "Local AI"
AI_MODE_CLOUD = "Cloud API"

AI_MODES = [
    AI_MODE_NONE,
    AI_MODE_LOCAL,
    AI_MODE_CLOUD,
]

# [ADDED v1.5.1 | 2026-08-10] Purpose: Field keys for the two-step config flow (Local and Cloud branches).
CONF_LOCAL_URL = "local_url"
CONF_LOCAL_MODEL = "local_model"
CONF_CLOUD_API_KEY = "cloud_api_key"
CONF_CLOUD_MODEL = "cloud_model"