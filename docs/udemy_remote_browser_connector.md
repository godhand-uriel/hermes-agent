# Udemy Remote Browser Connector

Hermes can read Udemy My Learning from a Chrome or Edge session that is already running on your Windows machine. This is useful when Hermes runs on a headless VPS over SSH: Hermes connects through Playwright CDP instead of launching Chromium on the VPS.

## Security model

- Hermes does not ask for, read, or store your Udemy password.
- Hermes does not log cookies or session tokens.
- Hermes does not scrape billing, payment, or account settings pages.
- Hermes does not save screenshots.
- Remote mode stores only Learning Registry results. It does not write Playwright storage state.
- Local/non-remote mode is unchanged. If local mode saves browser storage state, it is written under the active Hermes profile outside Git and chmodded to `0600` where the filesystem supports POSIX modes.

## Windows setup

Open PowerShell and launch Chrome with remote debugging:

```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="$env:TEMP\hermes-chrome"
```

Or launch Edge:

```powershell
& "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=9222 --user-data-dir="$env:TEMP\hermes-edge"
```

A dedicated `--user-data-dir` keeps this debug-enabled browser profile separate from your normal browser profile.

## SSH tunnel from the VPS

If Hermes runs on a VPS, forward the local Windows CDP port to the VPS session:

```bash
ssh -L 9222:127.0.0.1:9222 yuu@<VPS_IP>
```

Keep that SSH tunnel open while running the Hermes learning commands.

## Commands

Default CDP URL is `http://127.0.0.1:9222`.

```bash
hermes learning browser-connect udemy --remote
hermes learning browser-sync udemy --remote
hermes learning browser-status udemy --remote
```

Use a different CDP endpoint if needed:

```bash
hermes learning browser-sync udemy --remote --cdp-url http://127.0.0.1:9222
```

## Workflow

1. Start Chrome or Edge on Windows with `--remote-debugging-port=9222`.
2. If Hermes is on a VPS, open the SSH tunnel.
3. In the Windows browser, log into Udemy normally.
4. Run:

   ```bash
   hermes learning browser-sync udemy --remote
   ```

5. Hermes connects through Playwright `connect_over_cdp()`, opens Udemy My Learning in the active browser session, reads course progress, and imports it into the Learning Registry.
6. The Learning Registry projection updates the Career Registry `learning_summary`, so Career Command can display registry-backed Udemy/AWS SAA progress.

## Troubleshooting

If the CDP endpoint is missing or the tunnel is not open, Hermes returns a friendly `cdp_connection_failed` error with the setup command to run. It does not include cookies, session tokens, or raw browser storage in output.

To check status without connecting to Udemy:

```bash
hermes learning browser-status udemy --remote
```

Local desktop/Linux GUI behavior is preserved. Omit `--remote` to use the existing local browser connector.
