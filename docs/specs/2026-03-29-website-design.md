# Rythmiq Website — Design Spec

_Created: 2026-03-29_

---

## Overview

A minimal, dark, single-page marketing website for Rythmiq One hosted on Google Cloud (Firebase Hosting). Primary goal: establish credibility with investors, accelerators, and B2B partners. Single CTA: book a call / reach out directly.

**Stage:** Pre-launch. No active users yet. The site tells the story of what's being built and why.

**Audience:** Mix of early-stage investors, accelerators (YC, Antler, etc.), and B2B partners (coaching institutes, exam prep platforms).

---

## Visual Direction

- **Theme:** Dark & Premium — full dark background, white text. Inspired by Linear, Vercel.
- **Palette:** App palette from `app-v2/constants/Colors.ts`
  - Background: `#070712` (inkBlack)
  - Surface: `#191B26` (shadowGrey)
  - Text: `#FCFEFF` (white)
  - Accent / positive: `#34C759` (green)
  - Destructive / warning: `#FF3B30` (red)
- **Logo:** White spinner icon on dark background (from `Downloads/Group 2.png`)
- **Wordmark:** RYTHMIQ — all caps, tight letter-spacing
- **Typography:** System font stack (`-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif`)
- **Design TBD:** Specific layout, spacing, component design to be decided in a separate session.

---

## Site Structure

Single-page, 7 sections, linear scroll. Sticky nav throughout.

### Nav
- Logo (icon + wordmark) — left
- "Book a call" button — right
- Sticky on scroll, frosted glass background

---

### Section 01 — Hero

**Tagline:**
> Your documents, prepared once. Accepted everywhere.

**Sub-headline:**
> Rythmiq One auto-prepares your photo, signature, and documents to meet any portal's exact requirements — so you never reformat again.

**CTA:** "Book a call" (primary button) + "Learn more ↓" (ghost link)

**Badge:** "Now in development · India" (subtle, above the headline)

---

### Section 02 — Problem

**Section label:** THE PROBLEM

**Headline:**
> Every form asks what your document already answers.

**4 pain point cards:**

1. **You never know what you'll get**
   Adjust the DPI, the quality drops. Compress the size, the DPI is off. Convert the format, the compression breaks. Each step undoes the last — and you don't find out until you try to upload.

2. **The tools work against each other**
   There's no single tool that handles size, DPI, format, and quality together. You stitch together three random websites and hope the output is acceptable.

3. **30 seconds or 10 minutes — you won't know**
   That's not a time problem. That's an ambiguity problem. Document prep for a high-stakes form can go either way, and you have no control over which.

4. **Correction windows exist for a reason**
   NEET, JEE, and CAT all build official correction windows into their process because the failure rate is that high. This isn't user error — it's a broken system.

---

### Section 03 — Solution

**Section label:** THE SOLUTION

**Headline:**
> Prepare once. Let Rythmiq handle the rest.

**Body:**
> You capture your photo, signature, and documents once inside the app. Rythmiq One enhances them into high-quality masters — then adapts each one to any portal's exact size, format, and DPI requirements, instantly, on demand.
>
> No reformatting. No unsafe online tools. No doing it again for the next exam.

---

### Section 04 — How It Works

**Section label:** HOW IT WORKS

**3 steps:**

| Step | Label | Headline | Body |
|------|-------|----------|------|
| 01 | CAPTURE | Once. | Take a photo, scan a document, or sign on screen. That's the last time you'll need to. |
| 02 | ENHANCE | Perfected automatically. | Rythmiq auto-corrects, crops, and optimises everything into a high-quality master stored in your vault. |
| 03 | EXPORT | Any portal. Instantly. | Select your exam. Get a file that meets its exact specs — right size, right format, right DPI. |

---

### Section 05 — Vision

**Section label:** THE VISION

**Headline:**
> Where we're going.

**Body:**
> Documents are just the beginning.
>
> Every form you fill — NEET, JEE, CAT, government applications, corporate onboarding — asks for information your documents already contain. Name, date of birth, address, ID numbers. You type it in, every single time.
>
> The vision for Rythmiq is one tap. Open a form, and it's already filled — pulled directly from your verified documents, formatted to the portal's exact requirements. No typing. No uploading. No reformatting. Just submit.

**Pull quote:**
> We're building the layer between every Indian student and every form they'll ever fill.

---

### Section 06 — Founder

**Section label:** FOUNDER

**Name:** Abhinav Prakash
**Title:** Founder, Rythmiq

**Bio:**
> I'm a student. I've filled out exam forms for myself and for every member of my family when they needed it.
>
> I know exactly what it feels like to spend time reformatting the same documents, juggling random online tools, hoping the portal accepts the upload before the deadline closes.
>
> I built Rythmiq because this problem is too common and too solvable to still exist.

---

### Section 07 — Contact

**Section label:** GET IN TOUCH

**Headline:** Let's talk.

**Sub-headline:** Investor, accelerator, or potential partner — reach out below.

**Form fields:**
- Name (text input)
- Email (email input)
- Message (textarea)
- Submit button: "Send message"

**Also display:** Direct email address (abhinav@rythmiq.in)

---

## Tech Stack

| Concern | Choice | Reason |
|---------|--------|--------|
| Framework | Static HTML/CSS/JS or Next.js (static export) | No server needed for a marketing site |
| Hosting | Firebase Hosting (Google Cloud) | Zero-config CDN, SSL, custom domain, free tier |
| Domain | rythmiq.in | Already owned |
| Form backend | Formspree | No server required, handles form submissions to email, free tier sufficient |
| Analytics | Google Analytics 4 | Native Google Cloud integration |

---

## Out of Scope (This Version)

- App screenshots or product demo
- Pricing page
- Blog or content section
- Multi-language support
- Dark/light mode toggle
- Traction metrics or social proof (none yet)
- Detailed component design / spacing / animations — to be decided separately

---

## Open Questions

- What email address should form submissions go to?
- Is `abhinav@rythmiq.in` the correct contact email to display publicly?
- Does Abhinav have a photo for the Founder section, or should it use initials (AP)?
- Calendly link for the "Book a call" nav CTA, or does it scroll to the contact form?
