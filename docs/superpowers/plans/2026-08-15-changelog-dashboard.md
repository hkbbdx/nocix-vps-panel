# Changelog Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a GitHub-synced `CHANGELOG.md`, a bilingual local update data module, a recent-updates dashboard card, and a complete `/updates` page.

**Architecture:** Keep release notes in root `CHANGELOG.md` for repository readers and mirror the same safe, curated entries into a typed frontend module. The dashboard consumes the first five entries; the updates route consumes all entries. No runtime GitHub request is introduced, so the authenticated panel remains independent of external GitHub availability.

**Tech Stack:** Markdown, React, TypeScript, React Router, existing bilingual i18n context, Vitest and React Testing Library.

---

## Files

- Create: `CHANGELOG.md` - bilingual human-readable release notes.
- Create: `frontend/src/lib/updates.ts` - typed local update entries.
- Create: `frontend/src/pages/Updates.tsx` - complete updates page.
- Modify: `frontend/src/pages/Dashboard.tsx` - recent five updates card.
- Modify: `frontend/src/components/Layout.tsx` - updates navigation link.
- Modify: `frontend/src/main.tsx` - `/updates` route.
- Modify: `frontend/src/i18n.tsx` - update page/card labels and type names.
- Modify: `frontend/src/styles.css` - update timeline/card styles.
- Create/modify: `frontend/src/__tests__/Updates.test.tsx` - data, dashboard and page tests.
- Modify: `frontend/src/__tests__/i18n.test.tsx` - language switching coverage.
- Modify: `README.md` - explain how to maintain CHANGELOG and update frontend data.

## Task 1: Data and Markdown

- [ ] Add `CHANGELOG.md` with recent safe entries for the panel, bilingual UI, logs/timezone, proxy support, and two-stage login.
- [ ] Add typed `UpdateEntry` records with date, commit, type, and zh/en title/items.
- [ ] Add tests validating date/type/hash and absence of sensitive key patterns.

## Task 2: Dashboard and Updates Route

- [ ] Add recent updates card showing five entries and a link to `/updates`.
- [ ] Add `/updates` route and full reverse-chronological timeline.
- [ ] Add navigation label and bilingual translations.
- [ ] Add responsive styling and accessible headings/landmarks.
- [ ] Add tests for recent limit, full page, language switching and navigation.

## Task 3: Verification and Release

- [ ] Run Python tests and compile checks to ensure no backend regression.
- [ ] Run all frontend tests and production build.
- [ ] Run `git diff --check`.
- [ ] Commit `CHANGELOG.md`, frontend update UI, docs and tests.
- [ ] Push to GitHub and verify `origin/main` points to the new commit.
