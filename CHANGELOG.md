# LIBI changelog

All source files carry the GPL v3 header. JSON files are left without one, because JSON has no
comment syntax and Home Assistant and HACS parse `manifest.json`, `hacs.json` and the locale files
strictly.

## 3.11.0 — the project is called libi

**This release changes the Home Assistant domain and is not a drop in upgrade.** See RENAME.md.

* Domain `ha_libi` becomes `libi`. The integration directory becomes `custom_components/libi`.
* The sidebar panel moves from `/ha_libi` to `/libi` and the frontend is served from `/local/libi`.
* The WebSocket namespace becomes `libi/save_automation` and so on, changed on both sides together.
* The log prefix becomes `[libi]`, the browser draft key becomes `libi_draft`, and the config flow
  classes drop the `Ha` prefix.
* `manifest.json` gets a real documentation url, an issue tracker and a codeowner, which were
  placeholders that HACS warns about.
* Your drawings are safe. They live in `libi_ast.json` in the configuration folder and that file
  name did not change.

## 3.10.0 — what it is called, and what it is

* Every contact and every coil carries two lines. The name on top, the kind underneath in a
  quieter, smaller type: **פינת אוכל** over `climate`, **Sony XR-85X95L** over `media_player`,
  **תריס סלון** over `cover`.
* The same applies to conditions and to actions, since both are drawn as contacts and coils.
* An event trigger no longer repeats itself. It reads **לילה טוב** over `conversation`.
* A target that is an area, a label or a floor says so on the kind line.

## 3.9.0 — names, not slugs

* The box above an element shows the name the house uses, not the entity id slug.
* The id moved one hover away, together with every target written out by name.
* The inspector prints the entity id under the Home Assistant picker and lists every resolved
  target under the target picker.

## 3.8.0 — the wrapper rule, applied properly

* A coil stays a coil only when the action names exactly one thing that resolves to an entity.
  Several targets, or a group such as a label or an area, is a `MOVE ACTION`.
* `MOVE ACTION` carries the service name on IN and a summary on OUT.
* Titles are generic: `MOVE ACTION`, `MOVE TTS`, `MOVE NOTIFY`, `MOVE NOTIFY/TTS`.

## 3.7.0 — pick devices, areas and labels the way Home Assistant does

* The inspector injects `ha-selector` with a `target` selector, the same control HA uses.
* The whole target block travels on the element as `targetSpec`.

## 3.6.0 — a perfect drawing from YAML

* No pin is ever empty and no registry id is ever shown.
* A trigger is a boolean contact or a comparison. Never a MOVE.
* Any service that switches one thing between two states is a coil.
* A level dropdown sits next to the LOAD YAML button on every net.

## 3.5.0 — three execution levels, and no YAML for the user

* A net is an automation, a script or a scene, each with its own linter rules and schema.
* Output is merged into `automations.yaml`, `scripts.yaml` and `scenes.yaml`.
