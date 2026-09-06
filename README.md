# Renaming from ha_libi to libi

The Home Assistant domain changed. A domain is an identity, not a label, so this is a real
migration and not a silent upgrade. It takes about two minutes.

## What your Home Assistant needs

**1. Remove the old integration first, while it is still installed.**
Settings → Devices & Services → LIBI → the three dots → Delete. The config entry in
`.storage` records the domain `ha_libi`, and once that folder is gone the entry has nothing to
attach to and sits there broken.

**2. Delete the old folder.**
`custom_components/ha_libi/` — the whole thing. If you installed through HACS, remove LIBI in
HACS as well, otherwise HACS keeps tracking a folder that no longer matches the domain.

**3. Put the new folder in place.**
`custom_components/libi/` from this archive.

**4. Restart Home Assistant, then add the integration again.**
Settings → Devices & Services → Add integration → LIBI.

**5. Hard refresh the browser once.** Ctrl+Shift+R. The panel now loads from `/local/libi/`
instead of `/local/ha_libi/`, and the sidebar link is `/libi`. An old bookmark will not work.

### Your drawings are safe

The ladder itself lives in `libi_ast.json` in the configuration folder, and that file name did not
change. Neither did `automations.yaml`, `scripts.yaml` or `scenes.yaml`. Nothing you drew is lost.

---

## What GitHub needs

Your repository is `GuyAzria/HA_LIBI` on the `main` branch.

**1. Rename the repository.**
On github.com: the repo → Settings → General → Repository name → `Libi` → Rename.
GitHub keeps a redirect from the old URL, so nothing breaks immediately, but update the remote
anyway so the redirect is not doing the work forever.

**2. Point your local clone at the new name.**

```bash
cd /path/to/HA_LIBI
git remote set-url origin https://github.com/GuyAzria/Libi.git
git remote -v          # confirm both lines say Libi.git
```

**3. Record the folder rename as a rename, not as a delete and an add.**
Do this before copying the new files in, so git can follow the history of each file.

```bash
git mv custom_components/ha_libi custom_components/libi
```

**4. Copy the contents of this archive over your working tree**, letting it overwrite. Then:

```bash
git status             # read it before committing
git add -A
git commit -m "Rename integration domain from ha_libi to libi (v3.11.0)"
git push
```

**5. Rename the local folder too if you like.** Git does not care what the working directory is
called, so this is only for your own tidiness.

**6. Tag the release.**

```bash
git tag -a v3.11.0 -m "LIBI 3.11.0"
git push origin v3.11.0
```

### For HACS

`hacs.json` asks for a zip release asset named `libi.zip`, so a plain tag is not enough. On the
release page, create a release from the `v3.11.0` tag and attach the `libi.zip` that came with this
archive. That zip holds the contents of `custom_components/libi/` at its root, which is what HACS
expects to unpack into the integration folder.

`manifest.json` now points at `https://github.com/GuyAzria/Libi` for documentation and issues.
If you pick a different repository name, change those two lines.
