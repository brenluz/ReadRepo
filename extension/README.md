# ReadRepo browser extension

A thin UI that injects a chat panel on GitHub repository pages and talks to
the local ReadRepo server.

## Prerequisites

The ReadRepo server must be running locally on `http://localhost:8000`:

```bash
uvicorn app.main:app --reload
```

(and Ollama running with the configured model pulled — see the project README).

## Load it in Zen / Firefox

1. Open `about:debugging#/runtime/this-firefox`.
2. Click **Load Temporary Add-on…**.
3. Select this folder's `manifest.json`.
4. Open any public GitHub repository page — e.g. `https://github.com/psf/requests`.
5. Click the **Ask ReadRepo** button (bottom-right) and ask a question.

Temporary add-ons are removed when the browser restarts, so re-load it per
session during development.

## Load it in Chrome / Edge

1. Go to `chrome://extensions`.
2. Enable **Developer mode** (top-right).
3. Click **Load unpacked** and select this `extension/` folder.
4. Open a repository page and use the **Ask ReadRepo** button.

The manifest declares both a Firefox background script and a Chrome service
worker, so the same folder loads in either browser.

The first question about a repository triggers a one-time indexing step and
can take a few minutes; later questions about the same repo are faster
(cached). Answers stream in and list the source files they draw from.

## How it fits together

- `content.js` — detects the repo from the page URL, renders the chat panel.
- `background.js` — service worker; makes the actual request to the local
  server (a content script can't call `http://localhost` from an HTTPS page)
  and relays the streamed response back.
- `manifest.json` — Manifest V3; `host_permissions` scope the extension to
  `http://localhost:8000` only.

## Limitations

- Expects the server at `http://localhost:8000` (not yet configurable in the UI).
- SPA navigation within GitHub is handled on `popstate`; a hard reload always
  re-detects the current repo.
