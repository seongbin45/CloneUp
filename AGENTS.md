# CloneUp — Agent Rules

## Build & Release — ALWAYS ASK FIRST (mandatory)

**Never build or release without the user's explicit approval in the current conversation.**

Applies to all of the following (and equivalents):

- PyInstaller / `scripts/build_exe.ps1` / `scripts/build_update_manager.ps1`
- Inno Setup / `scripts/build_installer.ps1` / compiling `installer/CloneUp.iss`
- Creating or uploading GitHub Releases / tags / Setup artifacts
- Bumping `VERSION` for a shippable build
- Publishing installers (`CloneUp-Setup.exe`, zips) to any remote

### Required workflow

1. Finish code/docs/tests as needed.
2. **Stop and ask** the user, e.g.  
   “빌드할까요? / 릴리스(Setup·GitHub Release)까지 진행할까요?”
3. Proceed **only** after a clear yes for that step.
4. One approval is **not** a blank check: ask again for a later build or a separate release.
5. “코드만 고치세요 / 검증만” ≠ build or release permission.

### Do without asking (unless destructive)

- Read/edit source, run pytest and verify scripts, local diagnose, smoke exploration that does not produce ship artifacts.
- Do **not** treat “fix and push” as license to build Setup or cut a release.

### Where this is duplicated

- Project: `.grok/rules/ask-before-build-release.md`
- User-wide: `~/.grok/rules/ask-before-build-release.md`
