# Quick Capture Audit

Audit timestamp: 2026-06-19T16:11:32Z
Repository: `/home/yuu/.hermes/hermes-agent`

## Scope

Audited buttons:

- New Task
- New Research
- New Venture
- New Note
- Capture Idea

## Frontend implementation

Source file: `/home/yuu/.hermes/hermes-agent/web/src/pages/ReportsPage.tsx`

Relevant code:

- `type QuickCaptureAction = "New Task" | "New Research" | "New Venture" | "New Note" | "Capture Idea";`
- `quickCaptureActions` contains exactly the five requested actions.
- `QuickCaptureBar` opens a dashboard drawer with the selected action.
- `submitLocalCapture()` only sets React component state:
  - `setSavedMessage(`${title} captured locally. Source write integration is not wired yet.`)`
- The `Write to source` button is disabled and has title `Not wired yet`.

## Backend/API audit

No write endpoint is called by the current quick-capture form.

Observed behavior:

- No `fetch()` call in the quick-capture submit path.
- No API endpoint is associated with the five buttons.
- No database/file destination is selected by the submit handler.
- The success message is a local UI state message only.

## Button-by-button write verification

| Button | Destination source | File/database written | API endpoint | Success/failure status | Classification |
|---|---|---|---|---|---|
| New Task | None | None | None | Does not write; local message only | Decorative / not wired |
| New Research | None | None | None | Does not write; local message only | Decorative / not wired |
| New Venture | None | None | None | Does not write; local message only | Decorative / not wired |
| New Note | None | None | None | Does not write; local message only | Decorative / not wired |
| Capture Idea | None | None | None | Does not write; local message only | Decorative / not wired |

## Important UI text

The drawer explicitly states the integration is not wired through behavior:

- The active capture button label is `Capture locally`.
- The message after clicking it says the item was captured locally and source write integration is not wired yet.
- The actual source-write button is disabled.

Because the local capture state is not persisted outside the React component, it does not survive refresh/navigation and should not be treated as a real capture.

## Operational assessment

The quick-capture bar is currently a UI prototype. It is not operational. It does not create Kanban tasks, Obsidian notes, venture registry rows, research files, or idea notes. It does not call the Hermes backend.

## Repair recommendation

Do not redesign the UI. Wire the existing buttons to explicit write contracts:

1. New Task -> Kanban task creation endpoint/database.
2. New Research -> Obsidian research note or research registry/report source.
3. New Venture -> existing venture registry update path only after approval; must not create unapproved ventures silently.
4. New Note -> Obsidian note path with template selection.
5. Capture Idea -> explicit inbox/capture note or Kanban backlog source.

Each write path should return source path/id and update the dashboard only after a real write succeeds.
