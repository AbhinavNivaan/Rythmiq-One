# Rythmiq Website — Visual Redesign Spec

_Created: 2026-03-30 (brainstorm session 9)_
_Updated: 2026-03-30 (brainstorm session 10 — all sections locked)_
_Status: COMPLETE — all sections locked_

---

## Reference

Visual direction inspired by [7 Seers Media](https://7seersmedia.com):
- Pure black background
- Large ambient gradient blobs as atmospheric light sources
- Full-width editorial nav
- Oversized display typography with italic accent word
- Bottom-corner metadata text in hero

---

## Global Decisions

| Element | Decision |
|---------|----------|
| Background | Pure `#000` throughout |
| Font | System stack (`-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif`) |
| Accent colours | Green `#34C759` (positive/CTA), Red `#FF3B30` (problem), Amber `#FF9F0A`, Blue `#2196f3` (vision) |
| Framework | **Next.js + Framer Motion** (static export) — chosen for animated bento requirement |
| Glow convention | Each section's ambient glow matches its emotional accent colour |

---

## Site Structure (6 sections — How It Works dropped)

Nav → Hero → Problem → Solution → Vision → Founder → Contact

**How It Works was removed** — the Solution bento already communicates the full flow visually.

---

## Nav

- **Layout:** Logo left (SVG spinner icon + RYTHMIQ wordmark), CTA button right
- **CTA style:** Dark bordered button — `border: 1px solid rgba(255,255,255,0.18)`, `background: rgba(255,255,255,0.05)`
- **Sticky:** Yes, frosted glass `backdrop-filter: blur(16px)`, `background: rgba(0,0,0,0.8)`
- **Height:** 58px, full-width 48px padding

---

## Section 01 — Hero

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

## Section 02 — Problem

**Layout:** Full-width section on black, 2-column grid `1fr 1.1fr`, 60px gap

**Left column:**
- Section pill: `The problem` — red tint border + text (`rgba(255,59,48,0.8)`)
- Headline: `Every form asks what your document already answers.` — 40px, weight 700
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

## Section 03 — Solution

**Layout:** Full-width section, 3-column bento grid (`1fr 1.15fr 1fr`, 16px gap)

**Animation:** Framer Motion particle stream, continuous loop, plays while section is in view
- Left → Centre: green particles `#34C759`, arc from right edge of Capture card into input nodes
- Centre → Right: amber particles `#FFB340`, arc from output nodes into left edge of Adapt card
- Particle count: ~20 per stream, staggered, size 2–4px, with trailing shadow

**Section header (above bento):**
- Pill: `The solution` — green
- Headline: `Prepare` *`once.`* `Let Rythmiq handle the rest.` — 42px, weight 800
- Sub: original spec copy, 16px, `rgba(255,255,255,0.45)`

### Card 01 — Capture (left)
- Label: `01 — Capture` (green)
- Title: `Once. That's it.`
- Desc: `Take a photo, scan a document, or sign on screen.`
- Visual: Phone mockup showing 3 upload items (Photo, Signature, Docs) appearing sequentially with staggered animation
- Border: `rgba(52,199,89,0.2)`
- Ambient glow: green blob, bottom-left corner

### Card 02 — Vault (centre)
- Label: `02 — Vault` (green)
- Title + desc: in footer overlay at bottom of card
- Visual: **SVG node graph** on a green dot-grid background
  - Input nodes (left): Photo, Signature, Docs — each colour-coded
  - Hub node (centre): **Vault** — larger, green highlight, `rgba(52,199,89,0.18)` background, glow
  - Output nodes (right): NEET (red), JEE (blue), CAT (amber)
  - Curved dashed SVG paths (`stroke-dasharray: 4 4`) connecting all nodes
  - Central green radial glow behind Vault node, pulsing
  - Lock label `🔒 AES-256` below Vault node
- Grid background: `background-image: linear-gradient(rgba(52,199,89,0.06) 1px, transparent 1px), linear-gradient(90deg, ...)` — 40px grid
- Border: `rgba(52,199,89,0.35)`

### Card 03 — Adapt (right)
- Label: `03 — Adapt` (amber)
- Title: `Any portal. Instantly.`
- Desc: `Masters adapted to exact portal specs — size, format, DPI.`
- Visual: 4-step numbered pipeline
  1. Select master — Pull from encrypted vault
  2. Resize + crop — Match portal pixel dimensions
  3. Set DPI + format — JPEG, PDF, exact DPI enforced
  4. Export — Portal-ready file, under size limit
- Below pipeline: 3 portal output badges (NEET/JEE/CAT) with spec summary
- Steps animate in sequentially on scroll (staggered, slide from right)
- Border: `rgba(255,159,10,0.2)`
- Ambient glow: amber blob, bottom-right corner

---

## Section 04 — Vision

**Layout:** Centred editorial column, `max-width: 620px`, text-align center

**Ambient glow:** Blue `#2196f3` — two radial blobs, top and bottom, slow breathing animation

**Elements (top to bottom):**
- Pill: `The vision` — blue border + text
- Headline: `Where we're` *`going.`* — 44px, weight 800, italic blue accent
- 3 body paragraphs at 17px, `rgba(255,255,255,0.52)`, key phrases bolded to `rgba(255,255,255,0.82)`
- Divider: 48px wide, 1px, `rgba(33,150,243,0.35)`, centred, `margin: 44px auto`
- Pull quote: 26px, italic, weight 700, `rgba(255,255,255,0.92)`
  - Left + right blue accent bars (3px wide, gradient fade in/out top+bottom)

**Copy:**
> "We're building the layer between every Indian student and every form they'll ever fill."

---

## Section 05 — Founder

**Layout:** Split horizontal, 2-column (`1fr 1.4fr`), 80px gap, vertically centred

**Ambient glow:** White/neutral — `rgba(255,255,255,0.06)`, left side, breathing animation

**Left column — Avatar:**
- Large circular avatar, 164px diameter
- Outer ambient glow orb (220px, white, pulsing)
- Border: conic-gradient ring (white → green accent), slow 12s rotation
- Initials `AP` inside — 48px, weight 800 (counter-rotates to stay upright)
- Name below: `Abhinav Prakash` — 18px, weight 700
- Title below: `Founder, Rythmiq` — 13px, `rgba(255,255,255,0.38)`
- **When real photo is available:** replace initials with `<img>` inside the same ring

**Right column — Bio:**
- Pill: `Founder` — neutral white border
- Bio text in 3 short paragraphs, 17px, `rgba(255,255,255,0.52)`
- Key phrases bolded: "I'm a student.", "this problem is too common and too solvable to still exist."
- Vertical accent line left of text: 2px, gradient fade top+bottom, `rgba(255,255,255,0.18)`

---

## Section 06 — Contact

**Layout:** Centred column, `max-width: 560px`

**Ambient glow:** Green `#34C759` — bottom, bookends with Hero

**Elements:**
- Pill: `Get in touch` — green
- Headline: `Let's` *`talk.`* — 48px, weight 800, italic grey accent (`rgba(255,255,255,0.35)`)
- Sub: `Investor, accelerator, or potential partner — reach out below.`

**Form (Formspree backend):**
- Row 1: Name + Email (2-column grid)
- Row 2: Message (textarea, min-height 120px)
- Row 3: Direct email left (`founder@rythmiq.in`) + Submit button right
- Field style: `background: rgba(255,255,255,0.04)`, `border: 1px solid rgba(255,255,255,0.1)`, border-radius 10px
- Focus state: `border-color: rgba(52,199,89,0.5)`, `background: rgba(52,199,89,0.04)`
- Submit button: dark bordered style (matches nav CTA), hover turns green-tinted

---

## Tech Stack (Updated)

| Concern | Choice | Reason |
|---------|--------|--------|
| Framework | **Next.js** (static export) | Needed for Framer Motion + component structure |
| Animation | **Framer Motion** | Declarative scroll triggers, particle streams, easy maintenance |
| Hosting | Firebase Hosting | Zero-config CDN, SSL, custom domain, free tier |
| Domain | rythmiq.in | Already owned |
| Form backend | Formspree | No server required, free tier sufficient |
| Analytics | Google Analytics 4 | Native Google integration |

---

## Source Files

- Brainstorm mockups: `.superpowers/brainstorm/3838-1774887417/content/`
  - `solution-bento-v2.html` — Section 03 final
  - `vision-v1.html` — Section 04 final
  - `founder-v1.html` — Section 05 final
  - `contact-v1.html` — Section 06 final
- Problem section mockup: `problem-v8.html` (session 9 brainstorm dir)
- Mark sheet asset: `marksheet.png` (move to `assets/` when building)
- Original content spec: `docs/specs/2026-03-29-website-design.md`
- Implementation plan (needs update): `docs/plans/2026-03-29-website.md`

---

## Open Questions (Resolved)

| # | Question | Answer |
|---|----------|--------|
| 1 | Glow colour convention? | Yes — matches section accent (green=hero/solution/contact, red=problem, blue=vision, white=founder) |
| 2 | Layout vary per section? | Yes — bento (solution), editorial centred (vision), split (founder), centred form (contact) |
| 3 | Formspree endpoint? | Pending — sign up at formspree.io with founder@rythmiq.in before Task 10 |
| 4 | Firebase project ID? | `rythmiq-website` |

---

## Implementation Notes

- Next.js replaces the original "static HTML/CSS/JS" option — update plan Task 01 accordingly
- Particle animation component should be isolated (`<ParticleStream />`) — reusable, takes `from`/`to` refs and colour props
- Node graph in Vault card: SVG-based, positions hardcoded, no external graph library needed
- Avatar ring rotation: CSS animation only, no JS
- All scroll triggers: Framer Motion `useInView` with `once: false` (stay active while in view)
