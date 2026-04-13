# Rythmiq One — UI Design System Spec

**Created:** 2026-04-13  
**Status:** Approved — ready for implementation  
**Scope:** app-v2 only. All rules apply to new UI work and screen remediation.

---

## How to Use This Document

**Before writing any UI code or component:** read the relevant sections here first.  
**Before writing any AI prompt for UI work:** include a link to this file in your prompt.  
**New screens must comply on first write.** Existing screens are remediated incrementally (see checklist at the bottom).

---

## 1. Colour System

### 1.1 Primitive Tokens

These are the only raw colour values allowed in the codebase. All other values are derived via semantic aliases or opacity modifiers on these.

| Token | Value | Notes |
|-------|-------|-------|
| `neutral-0` | `#070712` | inkBlack — darkest surface |
| `neutral-100` | `#191B26` | shadowGrey — primary surface |
| `neutral-200` | `#23263a` | elevated surface + input focus background |
| `neutral-900` | `#FCFEFF` | near-white — primary text + button fill |
| `green` | `#4ADE80` | accent — the one brand colour |
| `blue` | `#60A5FA` | completed/success status only |
| `amber` | `#FF9500` | pending/warning + notification badge |
| `red` | `#EF4444` | error/failed — replaces both `#FF3B30` and prior `#EF4444` usages |

**Rule:** No hardcoded hex or `rgba(...)` values in screen or component files. All values — including opacity-derived ones — are defined once in `constants/Colors.ts` as named exports and referenced by name. Inline `rgba(...)` in a `StyleSheet` block is a violation. The `Colors.ts` file itself is the one place where raw values are permitted.

### 1.2 Semantic Aliases (Dark Theme)

| Alias | Maps To | Used For |
|-------|---------|----------|
| `background` | `neutral-0` | Screen background |
| `surface` | `neutral-100` | Cards, inputs, search bar |
| `surface-elevated` | `neutral-200` | Modals, bottom sheets, focused input bg |
| `border-subtle` | `rgba(255,255,255,0.05)` — named in Colors.ts | Resting container borders |
| `border-default` | `rgba(255,255,255,0.10)` — named in Colors.ts | Active/overlay borders |
| `border-focus` | `green` | Focused input ring |
| `border-error` | `red` | Error input ring |
| `text-primary` | `neutral-900` | All primary text |
| `text-secondary` | `#999999` | Subtitles, labels, muted info |
| `text-error` | `red` | Error messages |
| `text-link` | `green` | Tappable text links |
| `accent` | `green` | Active icons, dot indicators, focus rings |
| `status-pending` | `amber` | Pending job state |
| `status-processing` | `green` | Processing job state |
| `status-completed` | `blue` | Completed job state |
| `status-failed` | `red` | Failed job state |

**Light mode:** Dark theme only for v1. Light mode token tables and contrast audits are deferred to a separate design decision. Do not build theming infrastructure before that decision is made.

---

## 2. Typography

**Font family:** Satoshi (variable TTF — `Satoshi-Variable.ttf`)  
**Asset location:** `app-v2/assets/fonts/Satoshi-Variable.ttf` (copy from `/Users/abhinav/Downloads/Satoshi_Complete/Fonts/TTF/` during implementation — do not reference the Downloads path in code)  
**Loading:** via `expo-font` `useFonts` hook in `app/_layout.tsx`. Missing font at runtime must be treated as a hard error, not a silent fallback.  
**Shared constant:** a `Typography` object must be created at `app-v2/constants/Typography.ts` and imported wherever text styles are applied — no inline `fontSize` values in StyleSheet blocks.

### Type Scale

| Name | Size | Weight | Line Height | Used For |
|------|------|--------|-------------|----------|
| `nano` | 10px | Medium (500) | 14px | Badge counts ("9+"), tiny indicators |
| `caption` | 12px | Regular (400) | 16px | Error messages, divider labels, footer links |
| `label` | 14px | Medium (500) | 20px | Form labels, card subtitles, secondary info |
| `body` | 16px | Regular (400) | 24px | Primary body text, input text, placeholder |
| `button` | 16px | Bold (700) | — | All button labels |
| `title-sm` | 20px | Bold (700) | 28px | Section headings |
| `title-md` | 24px | Bold (700) | 32px | Screen titles ("Sign In") |
| `title-lg` | 32px | Black (900) | 40px | Hero/greeting text ("How can I help you today?") |

**Rules:**
- No `fontWeight: '600'` — Satoshi has no SemiBold. Map to Bold (700).
- No inline `fontSize` values — always reference the scale by name via a shared `Typography` constant.
- Letter spacing: `0.3` on button text only.

---

## 3. Spacing

**Base unit:** 8px grid.

| Token | Value | Used For |
|-------|-------|----------|
| `space-1` | 8px | Gaps between inline elements, icon padding |
| `space-2` | 16px | Internal component padding, small gaps |
| `space-3` | 24px | Screen horizontal padding, section gaps |
| `space-4` | 32px | Between major sections |
| `space-5` | 40px | Large section separation |
| `space-6` | 48px | Screen-level vertical rhythm |

**Rule:** No arbitrary spacing values in screen or component `StyleSheet` blocks. Use the nearest token. Exempted from the 8pt grid: border widths (1px, 1.5px), indicator thicknesses (3–4px), handle heights (4px), and dot sizes (7–8px) — these are sub-pixel design details, not layout spacing.

---

## 4. Shape (Border Radius)

| Token | Value | Used For |
|-------|-------|----------|
| `radius-sm` | 8px | Badges, status pills, notification dot |
| `radius-md` | 12px | Buttons, icon wraps, action cards, social buttons |
| `radius-lg` | 16px | Inputs |
| `radius-xl` | 24px | Cards, modals, bottom sheets, result lists |
| `radius-full` | 9999px | Search bar, fully-rounded pill shapes |

---

## 5. Component Rules

### 5.1 Buttons

**General rules:**
- Minimum tap target: `minHeight: 52px`
- Full-width: pass `width: '100%'` via `style` prop — never baked into the component
- Press animation: `scale(0.96)` spring on all variants except Icon Round and disabled
- One Primary button per screen maximum
- `fontWeight: '600'` in existing code → replace with Bold (700) / Satoshi-Bold

#### Variants

| Variant | Fill | Border | Text | When to Use |
|---------|------|--------|------|-------------|
| **Primary (White)** | `neutral-900` | — | `neutral-0` | Default main CTA. Auth flows, general confirmations. One per screen. |
| **Primary (Green)** | `green` | — | `neutral-0` | Positive confirmations that complete a meaningful step. "Confirm Crop", "Start Export". One per screen. |
| **Secondary** | `green` 12% | — | `green` | Second-tier actions alongside a Primary. "Download", "Share", "View Details". |
| **Soft Danger** | `red` 12% | — | `red` | Feedback, flagging, reporting. "Report Issue", "Something looks wrong". |
| **Ghost** | — | — | `neutral-900` 80% | Dismissal where a border adds noise. Inside modals, below a Primary, "Skip" on onboarding. |
| **Ghost Outline** | — | `neutral-900` 20%, 1.5px | `neutral-900` 80% | Dismissal that needs a visible tap boundary. Standalone, beside Soft Danger. |
| **Danger** | — | `red` 1.5px | `red` | Irreversible destructive actions only. Always behind an `Alert` confirmation. |
| **Icon Round** | `surface` | `border-subtle`, 1px | — | Header icon actions (Bell, User), back nav, FABs. Always 46×46px. Never resize. |

#### Disabled State (all variants)
- Fill: `Colors.disabled.fill` — defined as `rgba(255,255,255,0.10)` in Colors.ts
- Text: `Colors.disabled.text` — defined as `rgba(255,255,255,0.25)` in Colors.ts
- No press animation (`activeOpacity: 1`)
- `pointerEvents: 'none'`

### 5.2 Cards

| Variant | Fill | Border | When to Use |
|---------|------|--------|-------------|
| **Default** | `surface` (#191B26) | `border-subtle` | Standard content containers — dashboard action cards, job list items, settings rows |
| **Elevated** | `surface-elevated` (#23263a) | `border-subtle` + 7% | Selected states, cards inside modals needing separation |
| **Glass** | `surface` 70% opacity + blur | — | Overlays on image/camera content only — crop overlay controls |

**All cards:** `borderRadius: radius-xl (24px)` · `padding: space-3 (24px)` · shadow: `black 30%, offset 0 4px, blur 8px`

### 5.3 Inputs

| State | Fill | Border | Icon | Text |
|-------|------|--------|------|------|
| **Resting** | `surface` | `border-subtle` 1px | `neutral-900` 30% | `text-secondary` (placeholder) |
| **Focused** | `surface-elevated` | `border-focus` (green) 1.5px | `accent` (green) | `text-primary` |
| **Error** | `surface` | `border-error` (red) 1.5px | `red` | `text-primary` + error message below |
| **Disabled** | `neutral-0` | dashed, `neutral-900` 12%, 1.5px | `neutral-900` 15% | `neutral-900` 20% |

**All inputs:** `height: 56px` · `borderRadius: radius-lg (16px)` · icon left at `space-2 (16px)` · text padding `space-2 (16px)` · error message: `caption` / `text-error` below the field

### 5.4 Badges and Pills

**Status pills** (job states):
- Shape: `borderRadius: radius-sm (8px)` · `paddingHorizontal: 10px` · `paddingVertical: 4px`
- Style: status colour at 15% opacity fill + status colour text + 7px dot
- Font: `label` (14px) / Bold

| Status | Dot + Text Colour |
|--------|-------------------|
| Pending | `amber` (#FF9500) |
| Processing | `green` (#4ADE80) |
| Completed | `blue` (#60A5FA) |
| Failed | `red` (#EF4444) |

**Notification count badge:** `amber` fill · `neutral-0` text · `nano` (10px) / Bold · `radius-sm` · on Bell icon top-right  
**Neutral count:** `surface` fill · `text-secondary` · `caption` / Medium · `radius-sm`  
**Type label:** `blue` 12% tint · `blue` text · `caption` / Medium · `radius-sm`

### 5.5 Modal / Bottom Sheet

- **Background:** `surface-elevated` (#23263a)
- **Top corners:** `radius-xl` (24px) · bottom corners: 0
- **Handle:** 36×4px · `neutral-900` 15% · centered · 14px margin from top edge
- **Backdrop:** `Colors.backdrop` — defined as `rgba(0,0,0,0.75)` in Colors.ts
- **Title:** `title-sm` (20px) / Bold
- **Body text:** `body` (16px) / Regular / `text-secondary`
- **Actions:** always at bottom · standard pairings: Primary + Ghost, Primary + Ghost Outline, Soft Danger + Ghost Outline
- **Max height:** 80% of screen — content scrollable inside if taller

### 5.6 Skeleton Loader

- Shimmer animation between `surface` (neutral-100) and `surface-elevated` (neutral-200)
- Shape matches the real content exactly — same border radius, same dimensions
- Never use a spinner in place of a skeleton for list or card content

### 5.7 Toast

Three variants — all: `borderRadius: radius-xl (24px)` · tinted background + coloured left border 1px · 8px dot + message text · anchored to bottom of screen with `space-3 (24px)` margin · auto-dismiss after 3s · one toast at a time (queue if multiple)

| Variant | Fill | Border | Dot + Text |
|---------|------|--------|------------|
| **Success** | `green` 10% | `green` 20% | `green` |
| **Error** | `red` 10% | `red` 20% | `red` |
| **Info** | `blue` 10% | `blue` 20% | `blue` |

---

## 6. Interaction States

| State | Rule |
|-------|-------|
| **Press (buttons)** | `scale(0.96)` spring via `react-native-reanimated`. |
| **Press (cards/rows)** | `activeOpacity: 0.75`. No scale. |
| **Loading (button)** | `ActivityIndicator` in button text colour. Button stays full size. |
| **Loading (list/screen)** | Skeleton shimmer. Never a full-screen spinner for content with known shape. |
| **Error (input)** | Red border + red icon + error message below. |
| **Error (screen)** | `ErrorState` component — centred message + `text-secondary` descriptor + Ghost Outline or Secondary retry button. |
| **Empty state** | `text-secondary` label + descriptor + optional action button. No illustrations for v1. |
| **Disabled** | `activeOpacity: 1`. No press animation. `pointerEvents: 'none'`. |

---

## 7. Navigation Model

The app uses a **stack-based navigator** (`expo-router` Stack). Navigation model:

- **Dashboard is the hub** — all primary actions originate from dashboard action cards
- **No bottom tab bar** — do not add one without a separate design decision
- **Back navigation** — via Icon Round button (top-left) or hardware back. Always present on non-dashboard screens.
- **Modals** — presented as bottom sheets, not full-screen stacks, where the context is confirmatory or supplemental

---

## 8. Screen Remediation Checklist

Priority order: HIGH = fix next sprint · MEDIUM = fix as you touch the screen · LOW = cosmetic, fix last

### Components to Fix First (before screen work)

| File | Action | Priority |
|------|--------|----------|
| `components/ui/Button.tsx` | Add 6 new variants (Primary Green, Secondary, Soft Danger, Ghost Outline, Icon Round). Remove `dark` and `outline` variants. Update disabled state. Replace `fontWeight: '600'` with `700`. | HIGH |
| `components/ui/Input.tsx` | Update focus border from `#1A2595` to `green`. Update focus bg from `#1E202E` to `neutral-200`. Add disabled state (dark fill + dashed border). | HIGH |
| `constants/Colors.ts` | Add all primitive tokens (`green`, `blue`, `amber`, `red` with new values, `neutral-200`). Add semantic alias map. | HIGH |
| `components/ui/CustomTabBar.tsx` | **DELETE** — orphaned, not wired to any navigator. | HIGH |
| `components/ui/Toast.tsx` | Update to 3-variant system (success/error/info) using new colour tokens. | MEDIUM |
| `components/ui/Card.tsx` | Update colour references to semantic tokens. | MEDIUM |
| `components/ui/Skeleton.tsx` | Verify shimmer uses neutral-100 ↔ neutral-200. | LOW |

### Screens

| Screen | Issues | Priority |
|--------|--------|----------|
| `app/onboarding.tsx` | MAYA_BLUE `#89C7FE` hardcoded in dot indicators and scan line — replace with `accent` (green). Button on slide 2 uses `primary` (white) — stays. | HIGH |
| `app/(auth)/login.tsx` | `#999` text-secondary hardcoded 4× · `#666` divider text · social button TouchableOpacity → Icon Round variant · `fontSize: 12` subtitle not from scale · `fontSize: 24` title not from scale | HIGH |
| `app/(auth)/signup.tsx` | Same issues as login.tsx — apply same fixes. | HIGH |
| `app/(tabs)/dashboard.tsx` | `#999` hardcoded · `#666` hardcoded · `#555` hardcoded · `#444` hardcoded · `#FF6B00` badge colour → `amber` · search bar `borderRadius: 28` → `radius-full` · greeting `fontSize: 32` / `fontWeight: bold` → `title-lg` / Black | HIGH |
| `app/(tabs)/upload.tsx` | Audit for hardcoded colours and spacing. Button variants to be verified against new system. | MEDIUM |
| `app/(tabs)/capture.tsx` | Audit for hardcoded colours. Any overlay controls → Glass card. | MEDIUM |
| `app/(tabs)/crop-preview.tsx` | Primary confirm button → Primary (Green). Any "report/feedback" button → Soft Danger. Overlay controls → Glass card. | HIGH |
| `app/(tabs)/job-detail.tsx` | Download/share buttons → Secondary. Delete button → Danger. Hardcoded colours audit. | MEDIUM |
| `app/(tabs)/adapt-status.tsx` | Feedback button → Soft Danger. Dismiss button → Ghost Outline. Hardcoded colours audit. | HIGH |
| `app/(tabs)/portal-selector.tsx` | Confirm action → Primary (Green). Hardcoded colours audit. | MEDIUM |
| `app/(tabs)/jobs.tsx` | Status pills → new badge system. Hardcoded colours audit. | MEDIUM |
| `app/(tabs)/profile.tsx` | "Delete Account" row → Danger button. "Log Out" → Ghost Outline. Hardcoded colours audit. | MEDIUM |
| `app/(tabs)/document-viewer.tsx` | Type badge → blue tinted. Hardcoded colours audit. `aspectRatio: 16/9` — note as tech debt for portrait docs. | LOW |
| `app/(tabs)/error-report.tsx` | Primary action → Primary (White). Retry → Ghost Outline. Hardcoded colours audit. | LOW |

### Global
- Replace all `#999`, `#666`, `#555`, `#444` with `text-secondary` token
- Replace all `rgba(255,255,255,0.1)` border values with `border-subtle` or `border-default` tokens
- Replace `#FF3B30` and `#EF4444` usages — unify to `red` token (`#EF4444`)
- Replace `#89C7FE` (MAYA_BLUE) — replace with `accent` (green `#4ADE80`)
- Load Satoshi variable font in `app/_layout.tsx` and apply globally via root stylesheet

---

## 9. Accessibility (Deferred)

Reduced motion, minimum contrast ratios (WCAG AA), and dynamic type handling are not in scope for v1. These will be addressed in a separate accessibility pass before public launch. Do not design around them now, but do not actively break them either — use the specified colour pairings which were chosen with sufficient contrast on dark backgrounds.

---

## 10. What Not to Do

- Do not add new colour values outside the 8 primitive tokens
- Do not use `fontWeight: '600'` — Satoshi has no SemiBold
- Do not use a spinner for list content — use Skeleton
- Do not place two Primary buttons on one screen
- Do not use Ghost for destructive actions — use Danger or Soft Danger
- Do not add a bottom tab bar without a separate design decision
- Do not hardcode spacing values — use the 8pt scale tokens
