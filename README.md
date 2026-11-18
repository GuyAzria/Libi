<div align="center">
  <img src="image/icon2.png" alt="LIBI Logo" width="115" />
</div>

# **LIBI (Ladder Interface & Building Intelligence)**

<p align="center">
  <a href="https://github.com/GuyAzria/Libi/releases"><img src="https://img.shields.io/github/v/release/GuyAzria/Libi?style=flat-square" alt="Release"></a>
  <a href="https://github.com/GuyAzria/Libi/blob/main/LICENSE"><img src="https://img.shields.io/github/license/GuyAzria/Libi?style=flat-square&cacheSeconds=3600" alt="License"></a>
  <a href="https://hacs.xyz/docs/faq/custom_repositories/"><img src="https://img.shields.io/badge/HACS-Custom-orange.svg?style=flat-square" alt="HACS Custom"></a>
</p>
<p align="center">
  <img src="https://img.shields.io/badge/Cloud_AI-Google_Gemini-blue.svg?style=flat-square" alt="Google Gemini">
  <img src="https://img.shields.io/badge/Cloud_AI-OpenAI-412991.svg?style=flat-square" alt="OpenAI">
  <img src="https://img.shields.io/badge/Cloud_AI-OpenAI--compatible-555555.svg?style=flat-square" alt="OpenAI-compatible">
  <img src="https://img.shields.io/badge/Local_AI-Ollama-black.svg?style=flat-square" alt="Ollama">
</p>

![LIBI Interface](image/LIBI2.png)
![LIBI Interface](image/LIBI1.png)

## **Why LIBI**

I have been a PLC programmer and IT professional for 25 years, writing control software for large, well-known industrial companies.

**Ladder Diagram (LD)** is the language of industrial control. It is one of the programming languages of **IEC 61131-3**, the international standard for PLCs, and every major PLC maker supports it - Siemens, Rockwell Automation (Allen-Bradley), Mitsubishi Electric, Omron and Schneider Electric among them - as do controllers made for buildings, such as the Siemens LOGO!. It is drawn like the wiring of a control panel: contacts on the left, coils on the right, one rung for each piece of logic. An electrician or a PLC technician reads it at a glance.

When I moved my home to Home Assistant, that was the one thing missing. Home Assistant has YAML, the visual editor and Node-RED, but no Ladder. So I built LIBI.

## **The way industry writes control logic**

LIBI is not another flow chart. It brings the way machines, production lines and buildings are programmed to your home:

* **The industry standard:** Ladder Diagram as IEC 61131-3 defines it, the language electricians and PLC programmers work in every day.
* **The online view of a PLC:** press **Traces** and every block shows its state live, and you follow the last real run from Home Assistant's own trace - as in the online mode of a PLC programming tool.
* **Native Home Assistant automations:** what you draw is saved as ordinary Home Assistant automations, scripts and scenes, which Home Assistant runs itself. There is no second engine and nothing to run beside Home Assistant.

If you have programmed PLCs, you will feel at home. If you have not, Ladder is a good language to learn: you read what an automation does from left to right, rung by rung.

## **What is LIBI?**

LIBI is a graphical editor that takes your existing Home Assistant automations and automatically translates them into a LADDER logic representation. It allows you to:

* Add and modify automation logic using a visual interface.  
* Save the resulting logic back to Home Assistant's standard automation, script and scene files - through the same editor API Home Assistant's own automation, script and scene editors use.  
* Execute the automations natively within Home Assistant, just like any standard automation.

### **IEC 61131-3 Compliance**

The software is built upon the **IEC 61131-3** standard, the international standard defining programming languages for PLCs. Specifically, LIBI utilizes:

* **LD (Ladder Diagram):** The classic ladder logic format, adapted with minor deviations to ensure seamless compatibility with Home Assistant's native entities and execution models.

## **Key Features**

* **Integrated Helper Management:** Search for, manage, and insert variables (Helpers) directly from within the graphical editor.  
* **Project and File Grouping:** Save and manage groups of YAML files collectively. In LIBI, every **NET** functions as an individual YAML file. This allows you to open a single project and view all related ladders (e.g., "Garden Automations", "Security Automations") in one unified workspace.
* **One project per automation, script or scene:** **LOAD** (*Load from Home Assistant*) lists the automations, scripts and scenes that are in no project yet, each kind under its own heading, with a filter by name when the list is long. A script opens as a NET of the *Script* kind, a scene as a NET of the *Scene* kind - one rung for each of its entities - and both are saved back to `scripts.yaml` and `scenes.yaml` as automations are. Under **IN USE** LOAD shows the others, each with the project it is in, and they cannot be chosen. To move one to another project, take it out of its project first (**Delete NET… ▸ Remove from LIBI only**).
* **Dimming, colors and other values - MOVE:** a **MOVE** to a light sets what you choose under **Set**: its brightness (a slider), color temperature, color (a palette with ready colors beside it) or effect; a MOVE to a fan sets its speed, to a cover or a valve its position, to a thermostat its temperature, to a media player its volume. **IN** is a fixed value or a variable read when the automation runs: a helper such as an `input_number` (a slider on your dashboard), another light (its brightness or color), a text helper holding `#rrggbb`, or an `input_select` of color names. A value written in Home Assistant that only looks like an entity - a speaker's id given to a text helper as words - stays those words; it is a variable only when you choose it with **Variable**. The color shows on the block. A MOVE to something that has no value to set - a switch is turned on and off by a coil - is red, says why, and is not saved. An automation made in Home Assistant that sets one value of a light opens as such a MOVE. The Inspector also says what the light does with the value: a light that only turns on and off is turned on and the brightness is left out, a light with no color is turned on and the color is left out.
* **Adding a block - the + menu:** a tap on a point of a rung shows the categories: Contacts, Compare, Coils, MOVE, Timers, Counter, Math and Structure, each with how many blocks it has. A tap on one shows every block of it, each with its symbol and its name - the four contacts `| |`, `|/|`, `|P|`, `|N|`; ADD, SUB, MUL, DIV, MOD, RAND, MUX - and **Back** (or Escape) returns to the categories.
* **Every input - a value or a variable:** each IN of a block (IN1, IN2, MIN, MAX, K ...) takes a value typed, such as `20`, or **Variable**: a list that opens on your helpers, by kind, and also offers by target and by type the sensors and the settings of devices - only what holds a value, never an on/off. A variable shows by its name, its id and what it holds now; **×** goes back to a value. **OUT** is chosen the same way, from what can take the result: a number helper, a counter or a text for MATH, MOD and RAND (never a sensor, which cannot be set), a helper or a device that takes a value for MUX and MOVE (in a scene, any entity). **ADD, SUB, MUL and DIV** take more inputs: **+ Add an input** gives IN3, IN4 ... up to IN8 (A + B + C, A ÷ B ÷ C), and **−** removes one.
* **Math: ADD, SUB, MUL, DIV, MOD, RAND and MUX:** the Math category of the **+** menu has every operation. **MOD** is the remainder of IN1 divided by IN2 - a step that counts up, MOD 4, goes 0, 1, 2, 3 and again. **RAND** puts a random whole number from IN1 to IN2 into the variable on OUT (an `input_number` or a `counter`); IN1 and IN2 are whole numbers or variables, and with *Never the number OUT holds now* ticked it never gives the same number twice in a row - so from IN1 to IN2 there must be two numbers or more. **MUX** chooses input number K of its list (K a whole number, from 0) and sets it on OUT - a helper, or a device as a MOVE sets it: four colors from the dashboard, one after another, or a random one. Each block is written as a standard Home Assistant template, so the automation runs without LIBI, and it opens again as the same block.
* **Every N seconds, minutes or hours - EVERY:** a time pattern is a block of its own: how often, a number and a unit. It starts the rung on the clock (every 10 seconds is at :00, :10, :20 ...). A time pattern from Home Assistant opens as EVERY, and a change to it is saved.
* **When a value on the dashboard changes - the P contact:** to run a rung when you pick another color in an `input_select`, move an `input_number` slider or type in a text helper, start the rung with a **P contact** on that helper. It fires the moment the value changes, not when the device drops off or comes back. On a list that may be *on* - with `on`, `off` and `auto` among its options - it fires on any change, to *off* too: for the moment it turns on, start the rung with **CMP =** `on`, and the Inspector says so. A normal (NO/NC) contact on such a helper waits for *on* or *off*, which a number or a list of colors never is: it is red, says to use a P contact or a CMP block, and is not saved.
* **Compare - above, below, between:** a check of two bounds - Home Assistant's *between*, above 20 and below 30 - opens as one **CMP RANGE** block, IN2 to IN3. Change a bound of any compare - **>**, **<**, **≥**, **≤** or a range - and only that bound changes: the rest of the check stays as it was, a device's check keeps its device. A **TON** after a check holds it for a time, which Home Assistant can do only for a state - a contact or **CMP =**: after a **>** or **<**, a range, a template, a zone or the time, it is not saved, and LIBI says why. One that was already in your automation stays as it is until you change it.
* **Nothing the ladder cannot draw is lost:** a condition of a kind LIBI has no block for - a newer Home Assistant condition, an `and` or `or` that is turned off, a `not` the ladder cannot turn round - is one block marked *kept as it is*. The Inspector shows it as Home Assistant has it, and it is written back unchanged.
* **Net Versions:** Every NET keeps its earlier versions. When an existing automation is opened in LIBI for the first time, LIBI keeps a copy of it in the version history exactly as it was in Home Assistant - **V1, the original** - and another one as **V2**, the version you work on; a NET you draw from scratch starts at V1. Every **SAVE & COMPILE** that changes a NET records the next version. The **V** badge on a NET shows the version that runs in Home Assistant; click it to see every version with its date and YAML, put an earlier one back on the canvas, and **SAVE & COMPILE** to make it the one that runs. The original is never dropped from the history. A change made in Home Assistant's own editor is recorded as a version the next time the project is opened.
* **SAVE & COMPILE:** LIBI compiles every NET first and checks it with Home Assistant's own validator. When anything does not hold, nothing is saved and LIBI says which NET and why. Otherwise each change goes to Home Assistant, which writes and reloads it, and LIBI waits until Home Assistant has reloaded it before it says it is saved.
* **Deleting a NET** asks what becomes of its automation: **Delete completely** (the automation is deleted from Home Assistant too), **Delete and go back to V1** (the original logic is put back; Home Assistant writes it in its own format, as it does with every save), or **Remove from LIBI only** (the automation stays in Home Assistant as it is now).
* **A save never deletes what you did not ask it to.** An automation you opened from Home Assistant is never deleted by **SAVE & COMPILE**: when it leaves the canvas any other way than **Delete NET** (**Clear all nets**, undo, another automation loaded into its NET, the AI Chat's **Replace**), it stays in Home Assistant as it is and leaves the project, and LIBI says so after the save. Only an automation, script or scene that LIBI itself created for the project can be deleted by a save, and only after LIBI lists it and you choose **Delete** - **Keep in Home Assistant** leaves it there, and **Cancel** saves nothing.
* **A NET you did not change is never written again.** SAVE & COMPILE sends only the NETs you changed in LIBI. An automation you changed in Home Assistant's own editor is left as you changed it, and so is everything in it that the ladder cannot draw. Before a save would do any of the following, LIBI says which automation and asks:
  * put back an automation that was deleted in Home Assistant since LIBI saved it (**Remove its NET** or **Save it again**);
  * replace a change made in Home Assistant since LIBI last saw it (**Replace with my NET**);
  * change a part of an automation that the ladder cannot draw (**Save anyway**).

  **Cancel** saves nothing.
* **A NET never takes another one's place:** a NET whose name or id is already used in Home Assistant by a script or an automation that is not this project's - one of yours, or another LIBI project's - is saved under the next free one (`script.good_night_2`), and the other one is left exactly as it is. The NET keeps that name from then on, even after the other one is gone. A copy of a NET (**Duplicate**) is a new automation of its own, and two NETs can never save to the same automation: LIBI says which two and saves nothing.
* **Nothing is written over a change made while you decide.** Just before each change goes to Home Assistant, LIBI checks it again. If that automation, script or scene changed in the meantime - in Home Assistant's own editor, or from another LIBI page - it is not sent, nor anything after it, and LIBI says so: press **SAVE & COMPILE** again. A LIBI page opened before another page saved the same project saves nothing, and asks you to open the project again, so it never writes over that save.
* **Changes not saved:** closing a project, opening another one or leaving LIBI with changes that are not saved asks whether to save them first.
* **Traces - the online view of a PLC:** press **Traces** in the header (on a phone, in the menu); the **ONLINE** bar opens over the NETs.
  * **Read only:** while Traces is on, a click only follows the run or FORCEs a block. Nothing can be edited - no element added, changed, moved or deleted, no Inspector, no undo, no save, no project opened, no AI draft - and a click on one of those says so. Turn Traces off to edit. The automation's on/off switch still works.
  * **Over each NET**, a monitor shows:
    * the clock now
    * whether its automation is on or off in Home Assistant, and whether it is running
    * its last run
    * the value of every variable it uses; one that is offline is red
  * **Each block** shows:
    * its state: green when it is TRUE - an action, while what it drives is on - and grey when it is not
    * **OFFLINE** or **NOT IN HA** when its entity is unavailable or gone
    * for a comparison, **IN1** and **IN2**, for example the clock now and the time it waits for, or the day now and the days ticked on the card (**IN2 sun mon tue wed thu**). Against a list of states (**IN2 rainy, pouring, hail**), **=** is TRUE when IN1 is one of them and **≠** when it is none of them; against a zone, IN1 is compared with the zone's name, as Home Assistant names a person's place
    * for a TON, the time left, counting down: the *for* of a trigger, or the delay a run is in
  * **The last real run**, from Home Assistant's own trace, is written under each block: **RUN ▶ started the run** (the trigger that started it), **RUN ✓ true** / **RUN ✓ done**, **RUN ✗ false: stopped here**, **RUN ⚠ error**, **RUN ⏳ 00:01:20** (the step it is in, counting down), **RUN – not reached**. A run started with no trigger says so in the monitor. For a NET you drew in LIBI, the run is shown in its monitor rather than on each block.
  * **Click a block** to open its menu, next to the block: what it gives now, what the run did there (with Home Assistant's reason for an error), and what you can do with it.
  * **Simulate** (the default):
    * In the block's menu, **FORCE TRUE** or **FORCE FALSE**; **Release** frees it, and **Release all** in the **ONLINE** bar frees every block.
    * A trigger forced TRUE runs its rung inside LIBI only: each condition, each action it *would* run, each TON counting down (⏭ ends one at once). Lines under the blocks start with **SIM**.
    * Nothing is sent to Home Assistant, and no device moves.
  * **Real:**
    * Click a trigger, then **FORCE TRUE ▶ run it in Home Assistant**: Home Assistant runs the saved automation for real, as if that trigger happened now, so the rung of that trigger runs. You are asked first; when the automation has conditions of its own, you can also skip them. The result appears under each block, from Home Assistant's trace.
    * Home Assistant checks the conditions of each rung itself. To force one, use Simulate (a condition's menu has **Switch to Simulate**).
    * LIBI does not run an automation for real when it can reach a lock, an alarm or a cover - named in it, in a script it calls, or in an area, device, floor or label it targets - or when it picks what it switches with a template. Nor one with changes not saved, or one that is turned off.
    * What the trigger itself would tell (`trigger.to_state` and the like) is empty in such a run.
    * Another automation that starts because of what the run switched is not checked: it runs as it would if you had switched that yourself.
    * **Run without a trigger**, over each NET, is Home Assistant's own Run: a rung that runs only for its own trigger does not run.
* **The variables of a NET, or of the whole project:** click the title of a NET and the **Variables** bar at the bottom lists only the variables that NET uses; click the project's name in the header and it lists the variables of every NET in the project. Clicking an element chooses its NET too.
* **The days and hours of a schedule, in the Inspector:** click a **CMP DATETIME** block that compares the time with a schedule, and its Inspector shows the schedule's days and hours: tick the days, set the time it starts and the time it ends, and press **Save to the schedule**. LIBI asks first, then saves them at once in the schedule itself, through Home Assistant's own API - not with **SAVE & COMPILE** - and every automation that reads the schedule follows. LIBI keeps no copy: without LIBI the schedule works as it is, and its own settings in Home Assistant change it. A schedule whose days have different hours can be set to one set of hours for all its days; a schedule whose blocks carry extra data, or one written in YAML, is changed only in Home Assistant.
* **Global - the phones a message goes to, in one place:** the **Global** tab of the **Variables** bar holds your *global variables*: a recipient such as "Guy's phone" or "Yulia and Guy", made of the phones you tick (one, or several - a message then goes to all of them at once). A **MOVE NOTIFY / TTS** block sends to the recipient picked in its **Send to**, where global variables are listed first. When you replace a phone, change it once in Global - untick the old phone, tick the new one, **Save** - and every NET of every project sends to the new phone, without saving any NET again. A message read aloud is read aloud by Android phones; an iPhone shows the spoken text. The **AI chat**'s list of phones offers your global variables too, first, tagged **Global**: tick one, and the message goes to every phone it holds.
* **Replace a phone with its global variable:** after you save a global variable, LIBI lists every automation and script that still sends straight to its phone - those made in Home Assistant's editor too - and asks before it changes any. Untick the ones to keep and press **Replace**: only the action of those steps changes, from the phone to the global variable; the message, title and data stay as they are. A step that sends more than a message, a title and data, a NET drawn in another LIBI project, and a global variable of several phones are not replaced, and LIBI says why.
* **Phones by name:** **Send to** in a MOVE NOTIFY / TTS block lists your phones by name, each with the action that reaches it. A phone that cannot be reached is shown in red, with a button that picks the right action, and **SAVE & COMPILE** does not save a changed NET that sends to a notify action Home Assistant does not have.
* **Rename - in Home Assistant, or in LIBI only:** right-click an entity's name above a block, or a variable inside the block, and choose **Rename**. **Rename in Home Assistant** changes the name Home Assistant shows everywhere (the entity id stays the same, so nothing that points at it breaks). **In LIBI only** leaves Home Assistant as it is and shows your name wherever LIBI shows that entity: above the block, inside it, in the Variables bar and in the list of entities. An entity Home Assistant cannot rename - it has no unique ID, for example because it was written in YAML - gets its name in LIBI only, and LIBI tells you so. **Remove the LIBI name** brings Home Assistant's name back. Every entity you named in LIBI only is also listed in the **Global** tab, under **Named in LIBI**: its name in LIBI, its type, Home Assistant's name, its id, and how many automations, scripts and scenes use it. A row opens **Rename**, and 🗑 takes the name in LIBI away; nothing changes in Home Assistant either way. The names are the same in every project.

## **Installation**

**Requirements:** Home Assistant 2025.1 or newer, [HACS](https://hacs.xyz/), and an administrator account. LIBI edits your automations, so like Home Assistant's own automation editor it is available to administrators only.

> [!TIP]
> **No YAML configuration is needed.** LIBI is set up entirely from the Home Assistant UI. You do not add anything to `configuration.yaml`, and there is no `!include` line to write: LIBI works with the `automations.yaml`, `scripts.yaml` and `scenes.yaml` that every Home Assistant installation already has.

### With HACS (recommended)

The quickest way is the two buttons below. Each one opens the right page in your own Home Assistant:

[![Open LIBI in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=GuyAzria&repository=Libi&category=integration)
[![Add the LIBI integration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=libi)

Or step by step:

1. **Find LIBI in HACS.** Open **HACS** in the sidebar and search for **LIBI**.
   - Not listed yet? Until LIBI is in the HACS default store, add it once as a custom repository: open the menu (**⋮**, top right), choose **Custom repositories**, enter `https://github.com/GuyAzria/Libi` in **Repository**, choose **Integration** in **Type**, and click **Add**. Then search for **LIBI** again.
2. **Download LIBI.**
   - Open **LIBI** in HACS.
   - Click **Download** (bottom right), keep the latest version, and click **Download** again.
3. **Restart Home Assistant.** Go to **Settings ▸ System**, click the power icon (top right), and choose **Restart Home Assistant**. HACS also shows a *Restart required* notice under **Settings**.
4. **Add the integration.**
   - Go to **Settings ▸ Devices & services**, click **Add integration**, and search for **LIBI**.
   - When asked for the **AI mode**, choose **No AI**. The AI features are not released yet; this can be changed later.

**LIBI** now appears in the sidebar. Open it, and your existing automations are ready to be loaded as ladder diagrams.

### Updating

When a new version is released, HACS shows it under **Settings** as an available update. Install it there and restart Home Assistant. Your projects in `config/libi/` and your automations are kept.

After the restart, reload the LIBI page once. If LIBI says it could not draw the page, the browser is still using an older copy of one of its files: reload the page without the cache (**Ctrl+Shift+R**, or **Cmd+Shift+R** on a Mac). In the Home Assistant app, reset the frontend cache in the app's settings.

### Manually

Download `libi.zip` from the [latest release](https://github.com/GuyAzria/Libi/releases/latest), unpack it into `config/custom_components/libi/`, restart Home Assistant, and add the integration as in step 4. With a manual install, HACS does not tell you about updates.

## **What LIBI changes in your configuration**

* LIBI reads the same `automations.yaml`, `scripts.yaml` and `scenes.yaml` that Home Assistant's own editors use, and never writes them itself. A save goes through Home Assistant's own config API - the one its automation, script and scene editors use - so Home Assistant checks each automation, writes the file and reloads it. Nothing has to be added to `configuration.yaml`.
* LIBI sends only the automations, scripts and scenes it changed; an unchanged save sends nothing. It deletes only what it created itself, and only after you confirm. Each project records which of its entries LIBI created (`made` in the `.libi` file) - only those LIBI checked were not there just before it created them; what a LIBI older than 2026.11.05 saved has no such record, so a save never deletes it - delete such a NET with **Delete NET… ▸ Delete completely**, which names the automation and says whether LIBI made it. The `.libi` file also keeps the key of each NET in Home Assistant (`keys`) and how many times LIBI saved the project (`revision`). When Home Assistant writes one of those files it writes the whole file in its own format, exactly as its own editor does: comments in the file are not kept, and an entry without an `id` gets one.
* If one of those files cannot be read (for example because it contains a syntax error), LIBI saves nothing and tells you why.
* `libi_automations.yaml`, the file LIBI used before version 3.5.0, is left alone: if it still holds automations, the log says so.
* The blocks of the **Math** category are written as standard Home Assistant templates, so the automation runs without LIBI, and LIBI reads each one back as the same block: ADD `{{ (states('input_number.a') | float(0)) + (5) }}`, MOD `{{ (states('counter.step') | int(0)) % 4 }}`, RAND `{{ range(0, 9 + 1) | random }}` (with *Never the number OUT holds now*: `| reject('eq', states('counter.index') | int(None)) | list` before `| random`), MUX `{{ ['red', 'blue'][(states('counter.index') | int(0))] }}`. **EVERY** is Home Assistant's own `time_pattern` trigger.
* Home Assistant has no "at least" or "at most" of its own: a **CMP ≥** is written as a `not` of `below`, a **CMP ≤** as a `not` of `above`, and a **CMP RANGE** as one `numeric_state` with both. A compare you change keeps the rest of its condition - its alias, its attribute, a device condition's `device_id`, `domain` and `type`.
* A **P contact** on a value - an `input_select`, an `input_number`, a text, a sensor, a button - is written as a state trigger with `not_from` and `not_to` `[unavailable, unknown]`: it fires when the value changes, not when its device drops off or comes back. An automation made in Home Assistant is written back as it was until you change its block.
* Projects are stored as `.libi` files in `config/libi/`, so they are part of your Home Assistant backup.
* The version history of each project is stored next to it, as `<project>.versions.json` (up to 30 versions per NET; the one that runs is always kept). Deleting a project deletes its history; the automations stay in Home Assistant.
* Each **global variable** (LIBI ▸ Global) is a script in `scripts.yaml`, `script.libi_send_to_<name>`, named `LIBI Global: <name>` in Home Assistant, and saved through the same config API. Its phones are kept only there; LIBI keeps no copy. If you change it in Home Assistant's script editor, LIBI shows it as edited, and **Save** in LIBI writes it again as LIBI writes it. A global variable that an automation still sends to is not deleted.
* **Replace** (in Global) changes only the automations and scripts you tick, after you confirm, and in them only the action of the steps that sent straight to the phone. Home Assistant writes the old `service:` key of those steps as `action:`, as its own editor does.
* **Traces** writes nothing. Its **Real** mode runs a saved automation in Home Assistant only after you confirm, and never one that can reach a lock, an alarm or a cover. The run is in that automation's trace in Home Assistant, which says *LIBI: FORCE TRUE*.
* A name you give an entity **in LIBI only** (Rename ▸ *In LIBI only*, for example for an entity Home Assistant cannot rename because it has no unique ID) is stored in `config/libi/local_names.json`, one file for every project. LIBI shows it wherever it shows that entity; Home Assistant never sees it.

## **🤖 AI Chat (beta)**

Under the Inspector, the **AI Chat** builds ladder logic from a sentence, in your own language — for example *"pressing a button turns the living room light on for 10 minutes"*.

You can also ask about the nets on the page ("what does the garden net do?") or ask to change one ("water on Sunday, Tuesday, Thursday and Saturday at 5:00 instead of the button"). A change is drawn as a new version that you can put in place of the old net with **Replace NET**.

1. LIBI asks the AI what the logic needs, then **searches your Home Assistant itself** and shows you the matching devices — every button, every light in the living room. You pick them, several at once if you like. The settings the logic reads — the NET's **local variables** (the start time, the days, the litres, the on/off switch) — are in one window at the top: each one uses a free helper of yours that fits, or a new one that LIBI creates when you press the button; **All new** makes every one of them new. Being at a place takes who and where - a person or a phone, and one of your zones, every one of them listed; a zone you choose on the dashboard card is a dropdown of your zones, and the logic checks that the person is in the one chosen.
2. You answer the few questions it asks (how long, which days, whether you want a dashboard card). For an automation that switches a device, **LIBI asks questions of its own**, the same every time: an on/off switch for the whole automation on the dashboard card (off stops it at once, and nothing starts until it is on again), a message when it starts and when it ends - a notification, spoken by your phone (the Home Assistant app on Android reads it aloud) or both - what to do when the device is offline (its battery ran out, for example), and a message when a battery of its devices runs low (LIBI finds the battery on the device itself). Your answers are written into the logic and checked in the draft. **Days and a time you set on the dashboard:** LIBI asks how - a switch for each day and one start time (a row of day buttons on the card), or a schedule: the days and, for each day, its own hours, a block's start turning it on and its end turning it off (tap it on the card, then its settings). Both are Home Assistant's own helpers, so the card and the automation keep working without LIBI. A schedule you name in your request is used as it is.
3. You get a **draft NET** to add to the canvas, plus a dashboard card to copy if you asked for one.

**Values in turn, or at random:** ask for colors on a light every 10 seconds - the colors chosen in lists on the card, one after another, or a random one that is never the color lit now - and the draft is drawn with **EVERY**, **MUX**, **CTU**, **MOD** and **RAND** blocks, the step and the index kept in counters the card does not show. A color given by name must be one Home Assistant knows, in English (`red`, `orange`, `lime`, `turquoise` ...): the chat corrects a name it does not know, and says when a list on the card holds one - a light given such a name turns white. Names that differ only in brightness (`green` and `lime`, `purple` and `magenta`) are one color on most lights.

> [!WARNING]
> **The AI can make mistakes.** A draft can do something other than what you meant: the wrong time or day, a condition the wrong way round, or a device that is never switched off again. Check the automation well before it runs:
> * Before you add a draft, read its rungs and **Your request, line by line** under it. A draft in which LIBI finds nothing wrong is saved as soon as you press **Add as NET …, save and compile**.
> * After the save, press **Traces** and watch it run once: each block shows what held, where the run stopped, and an action that failed. To see every step before anything really runs, use **Simulate** and **FORCE** the trigger.

**The AI never chooses or controls a device on its own.** It only ever sees roles like "the buttons" and "the lights"; the entities are the ones *you* ticked. LIBI rejects any draft that names another entity, a device or area id, or a service outside a safe list, and Home Assistant's own validator checks it too. Nothing is written until you press **SAVE & COMPILE**, or the chat's **Add as NET …, save and compile**, and drafts that control locks, alarms, covers, valves or sirens are flagged.

**Privacy:** what you type in the chat and the *names* of the devices you pick are sent to the AI model you choose. While **Share the nets on this page and my helpers** is on (it is by default), the chat also sends the nets open in the LIBI page (as YAML), your helpers, and the devices that match the request with their state and unit, so it can answer questions about those nets, change them and reuse what you already have. Your other automations - the rest of `automations.yaml`, `scripts.yaml` and `scenes.yaml` - and the rest of your devices are never sent. With **Local AI**, everything stays on your own server.

**Setup:** Settings ▸ Devices & services ▸ LIBI ▸ **Configure**, then choose:

* **Local AI** — an [Ollama](https://ollama.com) server address and model; nothing leaves your home.
* **Cloud API** — Google Gemini, OpenAI, or any OpenAI-compatible service, with its API key and model.

<p align="center">Made with ❤️ for the Home Assistant community by Guy Azria</p>