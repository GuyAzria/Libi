# LADDER FOR HA - MASTER AGENT RULES

These rules are permanent and absolute. All agents must read and strictly adhere to these instructions in every interaction regarding this workspace.

## 1. Core Architecture & Backend Constraints
* **Immutable Schema:** The intermediate Pydantic schema is the absolute contract. Agents are strictly forbidden from altering the schema structure.
* **Backend Logic Only:** All parsing, normalization, and generation logic runs in Python on the server side (HA backend), never in the browser/frontend.
* **Zero Hallucination (A2 Rule):** If an automation or pattern is not recognized with 100% certainty, it must be wrapped in an 'opaque' fallback box. Never guess or invent configuration.

## 2. Frontend Roles & Responsibilities (Vanilla JS)
* **@SVG_Agent:** Strictly responsible for all graphics and icons. Manages `frontend/ladder-svg.js` exclusively. No business logic, just pure, optimized SVG rendering and generation.
* **@i18n_Agent:** Manages localization (e.g., `en.json`, translation keys). Every user-facing string must be dynamically mapped and never hardcoded in the JS.
* **@Responsive_Agent:** Ensures 100% compatibility across Desktop, Tablet, and Mobile phones. Manages cross-platform touch/pointer events, viewport scaling, and CSS media queries.
* **@UX_Agent:** Focuses on interaction design, drag-and-drop fluidity (e.g., 300ms long-press mechanics), visual feedback, and intuitive navigation.

## 3. Strict Coding Style (Additive-Only)
* Keep all existing code and structure intact. Never delete or overwrite functional code unless explicitly instructed.
* Increment the version number at the top of modified files (e.g., v1.5.0).
* Include a descriptive English comment for every new function or significant change using this exact format:
  * For Python: `# [ADDED vX.Y.Z | YYYY-MM-DD] Purpose: <explanation>`
  * For JavaScript: `// [ADDED vX.Y.Z | YYYY-MM-DD] Purpose: <explanation>`

## 4. Mandatory Reporting (Agent Action Summary)
* At the very end of every code generation response, the active agent MUST provide an "Agent Action Summary".
* This summary must explicitly state:
  1. Which specific agent performed the task.
  2. A bulleted list of exactly which files were modified/created.
  3. A brief description of the specific logic added to each file.

## 5. Temporary & Non-Project Files Management
If you need to generate any temporary files, utility scripts, debugging logs, recovery patches, or any files that are not strictly part of the core `HA_Ladder` project architecture, you MUST create a dedicated directory named `antigravityTemp` at the root of the workspace and place them ONLY there. Do NOT pollute the main project directories with temporary or side-task files.