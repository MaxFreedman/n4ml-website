# Max Freedman — Projects

Max Freedman's personal radio website, prepared for a small Debian VPS. This repository preserves the full history of `MaxFreedman/MaxFreedman.github.io`; GitHub Pages publishing is retired. The homepage, MB4X Radio Archive, and ExpeditionOps remain in the static build.

## Routes

- `/` — personal home and projects
- `/projects/expeditionops/` — browser-local logistics demo with JSON import/export
- `/projects/mb4x-radio-archive/` — interactive MB4X IARU HF 2026 log and synchronized stereo recording

The archive contains 4,606 contacts and eight browser-ready MP3 segments. Audio-activity correlation identified Radio 0 on the right channel and Radio 1 on the left. The player can solo either radio, preserve stereo, or mix both channels.

## Develop locally

```bash
npm install
npm run dev
```

## Rebuild the archive

Generate the contact index and audio manifest from the Cabrillo log:

```bash
node scripts/prepare-data.mjs /path/to/mb4x.txt
```

Prepare the eight MP3 segments from the source ZIP archives:

```bash
./scripts/prepare-audio.sh /path/to/download-folder
```

Generate audio-derived timing estimates:

```bash
python3 scripts/analyze-audio.py
```

The analysis measures half-second activity independently on each stereo channel. Contacts in the same logged radio/minute are distributed across detected activity, with four seconds of pre-roll for CW and seven seconds for SSB. These are estimates because Cabrillo records minutes, not seconds.

## Deploy to Debian

See [DEPLOY.md](DEPLOY.md) for server setup, DNS/HTTPS, installation, and rollback. The VPS serves static files with Nginx; builds happen off the server. Three retained releases use roughly 1.5 GiB for the current archive.

```bash
npm run lint
npm test
npm run test:deploy
npm run package
```

## ExpeditionOps demo

The static edition runs entirely in the browser. It stores expedition plans in IndexedDB on the current device; JSON exports provide backups and transfers between devices. It supports the original `expeditionops-v1` backup envelope and validated plain expedition JSON. Imports replace the current plan only after confirmation, or create the first plan in an empty browser.

The demo preserves equipment manifests, bag and freight assignments, traveler arrivals and baggage limits, readiness tasks, planning alerts, CSV exports, and printable field packs. It does not require sign-in or provide shared invitations or online synchronization. The original Sites app and its database remain unchanged.

The static app lives in `public/projects/expeditionops/`. `domain.js` preserves the original planning calculations; `storage.js` provides transactional local saving, validation, backup compatibility, and revision checks between browser tabs. Only the fictional seed expedition is included in the published files.
