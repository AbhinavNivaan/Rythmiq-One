# Rythmiq Website — Visual Redesign Spec

_Created: 2026-03-30 (brainstorm session 9)_
_Status: IN PROGRESS — Hero + Problem section locked. Sections 3–7 pending._

---

## Reference

Visual direction inspired by [7 Seers Media](https://7seersmedia.com):
- Pure black background
- Large ambient gradient blobs as atmospheric light sources
- Full-width editorial nav
- Oversized display typography with italic accent word
- Bottom-corner metadata text in hero

---

## Locked Decisions

### Global

| Element | Decision |
|---------|----------|
| Background | Pure `#000` throughout |
| Font | System stack (`-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif`) |
| Accent colours | Green `#34C759` (positive), Red `#FF3B30` (problem), Amber `#FF9F0A`, Blue `#2196f3` |

---

### Nav

- **Layout:** Logo left (SVG spinner icon + RYTHMIQ wordmark), CTA button right
- **CTA style:** Dark bordered button — `border: 1px solid rgba(255,255,255,0.18)`, `background: rgba(255,255,255,0.05)`
- **Sticky:** Yes, frosted glass `backdrop-filter: blur(16px)`, `background: rgba(0,0,0,0.8)`
- **Height:** 58px, full-width 48px padding

---

### Hero Section

- **Badge:** `Now in development · India` — pill with green dot, subtle border
- **Headline:** `Prepared once.` / `Accepted` *(italic)* `everywhere.` — 80px, weight 800, letter-spacing -0.04em
- **Sub-headline:** Original spec copy, 17px, `rgba(255,255,255,0.42)`
- **CTAs:** Ghost text (`Learn more ↓`) + dark bordered button (`Book a call`)
- **Bottom corners:** Left — "The layer between every Indian student and every form they'll ever fill." / Right — "Scroll to view more ↓" — both at `rgba(255,255,255,0.20)`
- **Ambient glow:** Two green radial blobs
  - Blob 1: 800×560px, `rgba(52,199,89,0.26)`, bottom-left, blur 90px
  - Blob 2: 520×400px, `rgba(52,199,89,0.14)`, bottom-right, blur 90px
  - Blob 3: 320×280px, `rgba(52,199,89,0.07)`, top-right, blur 70px

---

### Section 02 — Problem

**Layout:** Full-width section on black (no panel container), 2-column grid `1fr 1.1fr`, 60px gap

**Left column:**
- Section pill: `The problem` — red tint border + text (`rgba(255,59,48,0.8)`)
- Headline: `Every form asks what your document already answers.` — 40px, weight 700
- ~~Supporting text removed~~ (was: "The same mark sheet. Three portals...")
- Mark sheet image: actual CBSE mark sheet photo, 240px wide, `rotate(-2.5deg)`, drop shadow

**Right column — 3 cascaded portal spec cards:**
- Cards are 300px wide, absolute positioned with 150px vertical cascade
- Each card fully visible (no header buried behind another card)
- Positions: NEET `top:0 left:50 rotate(-3.5deg)`, JEE `top:150 left:10 rotate(2.5deg)`, CAT `top:300 left:60 rotate(-1.5deg)`
- Z-index: NEET=1 (back), JEE=2 (middle), CAT=3 (front)
- Each card shows: portal name + coloured dot, then 4 spec rows (Format, File size, DPI, Dimensions)

**Card styles:**
| Card | Background | Border | Text colour |
|------|------------|--------|-------------|
| NEET UG 2025 | `#1c1018` | `2px solid rgba(255,59,48,0.65)` | `#FF453A` |
| JEE Main 2025 | `#0c1220` | `2.5px solid #2196f3` + glow | `#5ac8fa` |
| CAT 2025 | `#18160c` | `2px solid rgba(255,159,10,0.7)` | `#FFB340` |

**Spec values (real portal data):**

| Spec | NEET | JEE | CAT |
|------|------|-----|-----|
| Format | PDF only | PDF only | PDF only |
| File size | Max 1 MB | Max 300 KB | 500 KB – 1 MB |
| DPI | 200 DPI | 150 DPI | 300 DPI |
| Dimensions | 600 × 800 px | 400 × 600 px | 800 × 1000 px |

**Ambient glow:** Two red radial blobs
- Blob 1: 760×520px, `rgba(255,59,48,0.22)`, bottom-left, blur 100px
- Blob 2: 460×360px, `rgba(255,59,48,0.11)`, top-right, blur 90px

---

## Sections Pending Design (Next Session)

The following sections need the same visual treatment brainstorm:

| # | Section | Content | Visual TBD |
|---|---------|---------|------------|
| 03 | Solution | "Prepare once. Let Rythmiq handle the rest." + 2 paragraphs | ❌ |
| 04 | How It Works | 3 steps: Capture → Enhance → Export | ❌ |
| 05 | Vision | 3 paragraphs + pull quote | ❌ |
| 06 | Founder | Avatar + bio | ❌ |
| 07 | Contact | Formspree form | ❌ |

**Pattern to follow:** Each section should have its own ambient glow colour matching its emotional tone, large section headline, and a visual element (not just text) that makes the point.

---

## Source Files

- Brainstorm mockups: `.superpowers/brainstorm/69802-1774865771/content/`
- Final problem section mockup: `problem-v8.html`
- Mark sheet asset: `marksheet.png` (in brainstorm dir — move to `assets/` when building)
- Original spec: `docs/specs/2026-03-29-website-design.md`
- Implementation plan (to be revised): `docs/plans/2026-03-29-website.md`

---

## Open Questions (Resolve Next Session)

1. Should the section glow colour always match the section label colour (red for problem, green for solution, etc.)?
2. Should sections 3–7 use the same split-panel layout as the problem, or vary per section?
3. Formspree endpoint URL — needed before Task 10 of implementation
4. Firebase project ID — confirm it's `rythmiq-website`
