# Validation — 6 October 2026

## Passed

- 30 automated tests, using Python 3.12, Flask 3.1.3, yt-dlp 2026.08.19 and yt-dlp-ejs 0.8.0.
- Real local HTTP downloads and FFmpeg conversion of synthetic media to MP4, WebM, MP3, M4A, WAV and FLAC.
- Unauthenticated access blocked for queue, history, settings, metadata, search, progress streams, file download, diagnostics and updater.
- Username/password login, incorrect-password behavior, throttling, CSRF checks, logout, and invalidation after account reset.
- Correct file serving, invalid file index rejection, final-file tracking and prevention of unrelated-file selection.
- Regression checks for duplicate queued IDs and clearing a running task.
- Update endpoint requests default yt-dlp dependencies and reports that a restart is required.
- Input validation, template CSRF/logout controls, no-store response headers, and loading `.env` before configuration.
- Ruff code checks, JavaScript syntax checks and Python dependency consistency.

## Not verified here

- A live YouTube metadata request was attempted but failed with an outbound timeout/certificate-chain error in this execution environment. Live YouTube downloads, authentication cookies and platform-specific restrictions must be checked on the user's computer. No claim is made that every HTTP 403 is resolved.
- No live Instagram, X, Facebook, Dropbox or TeraBox downloads were tested; new integrations remain future work.
- Full browser rendering/interaction could not run: the Chromium executable was absent and the browser download returned invalid archives. Flask rendered-template checks and JavaScript parsing passed, but these are not a substitute for browser interaction testing.
- Tests ran on Linux, not the user's Windows machine. Windows commands are supplied in README.md.

## Preserved data

The supplied `data/app.db`, `data/settings.json`, existing downloaded media and original log were preserved in the ZIP. New account data, session secrets, test artifacts, bytecode and virtual environments are excluded. Existing persisted folder settings may refer to the old computer location; choose an existing folder in Settings if needed.

## Login session hotfix — 6 October 2026

Reproduced five failures in the previous code: an anonymous favicon request, an unmatched URL, a protected API poll, a protected page request, or a poll after an account reset cleared the login form's CSRF session. The authentication guard now preserves the session on access denial and lets Flask handle unmatched routes normally. Login/logout still rotate/clear the session; invalid account versions still cannot access protected routes.

All 27 authentication/API tests passed after this fix, including six added regression/security cases. The original media conversion code is unchanged. Missing and mismatched CSRF tokens are still rejected. Full browser interaction remains unverified as described above.
