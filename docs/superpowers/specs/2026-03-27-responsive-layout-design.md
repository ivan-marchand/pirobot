# Responsive Layout Design

**Date:** 2026-03-27
**Scope:** `react/pirobot/src/` — `home.js`, `VideoStreamControl.js`, `ArmControl.js`, `DirectionCross.js`

## Problem

The current UI computes all element sizes in JavaScript using `window.innerWidth` and `window.innerHeight`, then passes pixel values as props. This approach:

- Breaks on portrait mobile (3-column layout collapses to unusable widths)
- Overflows on small screens (toolbar has up to 15 icons in a single row)
- Requires a manual resize listener just to do what CSS handles natively
- Hardcodes sizes that drift as the app evolves

## Goal

The app should render well on all screen sizes — portrait phone, landscape phone, tablet, and desktop — without any JavaScript-based size calculations.

## Breakpoints (MUI defaults)

| Name | Width | Layout |
|------|-------|--------|
| xs / portrait mobile | < 600px | Full-screen video, floating overlays |
| sm–md / tablet + landscape phone | 600–960px | 3-column, toolbar collapses to primary + overflow |
| md+ / desktop | ≥ 960px | Current 3-column, full toolbar |

## Layout by Breakpoint

### Desktop (≥ 960px) — unchanged

- Toolbar: full row of icons, `flex-wrap: wrap` so it wraps gracefully if the window is narrow
- Body: 3 columns — joystick/dpad (left), video (center, flex-grow), camera slider (right, conditional)
- Status bar: below the body row
- No changes to the visual structure from what exists today

### Tablet / Landscape phone (600–960px)

- Toolbar: show primary icons only; remaining icons collapse behind a `⋯` IconButton that toggles a `Collapse` panel beneath the toolbar
- Body: same 3-column structure, joystick sized with `vw` units via `useMediaQuery`
- Camera slider: visible but narrower

### Portrait mobile (< 600px)

- Container: `position: fixed; inset: 0` — fills the full viewport, no scroll
- Video: `width: 100%; height: 100%; object-fit: contain` — fills the container
- Floating toolbar: `position: absolute; top: 8px; left: 8px; right: 8px` — semi-transparent pill (`rgba` background + `backdrop-filter: blur`) containing: Stop (prominent, red), Record, Photo, Control toggle, `⋯` overflow button
- Floating joystick/dpad: `position: absolute; bottom: 16px; left: 16px`
- FPS badge: `position: absolute; bottom: 12px; right: 12px`
- Camera slider (if present): `position: absolute; right: 8px; top: 48px; bottom: 80px` — vertical slider on the right edge

## Toolbar: Primary vs Overflow

**Always visible (primary):**
- Stop robot (red, prominent)
- Record video / Stop recording
- Take photo
- Control toggle (joystick ↔ dpad)
- Arm control toggle (if robot has arm)
- `⋯` button

**In overflow (behind `⋯`):**
- Photo gallery link
- Video gallery link
- Settings link
- Switch camera (if back camera present)
- Picture-in-picture overlay (if back camera present)
- Front lights toggle (if robot has lights)
- Arm lights toggle (if robot has arm + lights)
- Face recognition toggle
- Patrol

On desktop (≥ 960px), all icons are shown directly — no overflow menu needed.

## Component Changes

### `home.js`

- Remove `window_width`, `window_height` from state
- Remove `handleWindowResize` and the `window.addEventListener('resize', ...)` / `removeEventListener` calls
- Add `overflowOpen` boolean to state for the `⋯` menu
- Replace the outer `<div style={{display: ...}}>` with `<Box sx={{ position: { xs: 'fixed', md: 'relative' }, inset: { xs: 0 }, display: 'flex', flexDirection: 'column' }}>`
- Replace manual `xs={2}` / `xs={8}` Grid columns with responsive values: `xs={12}` stacked on mobile, `md={2}` / `md={8}` / `md={2}` on desktop
- Joystick size: extract a small functional `ResponsiveJoystick` wrapper component that uses `useMediaQuery` + `useTheme` to pick a pixel size from breakpoints (e.g. xs → 80, sm → 100, md+ → 120) and passes it to `<Joystick size={...} stickSize={...}>`. This keeps `Home` as a class component while using hooks where needed.
- Pass no `max_height` / `max_width` to `VideoStreamControl` — the component sizes itself via CSS
- Split toolbar icons into `primaryIcons` and `overflowIcons` arrays; render overflow in a `Collapse` controlled by `overflowOpen`

### `VideoStreamControl.js`

- Remove `max_height` and `max_width` props
- Change the `<img>` style to `{ width: '100%', height: '100%', objectFit: 'contain', display: 'block' }`
- The component fills whatever container it's placed in

### `ArmControl.js`

- Replace `style={{width: 150}}` on all sliders with `sx={{ width: '100%' }}`

### `DirectionCross.js`

- Replace `style={{"background-color": "grey"}}` (invalid React inline style key) with `sx={{ bgcolor: 'grey' }}` on the `IconButton`
- No size changes needed — the Grid layout already adapts

## What Does Not Change

- `settings.js` and `gallery.js` — these pages are not used while actively controlling the robot; their current layout is acceptable
- WebSocket logic — no changes to connection or message handling
- All server-side code

## Constraints

- Stay within the existing MUI v5 component set — no new libraries
- Do not convert class components to functional components (out of scope)
- The `useMediaQuery` hook requires a functional component wrapper or `withTheme` HOC since `Home` is a class component — use `withTheme` or wrap the joystick size in a small functional helper component
