# Rythmiq One — Claude Code Instructions

## FIRST THING EVERY SESSION
Before doing anything else, you must:
1. Read /Users/abhinav/AI Brain/Rythmiq OS/CLAUDE.md
2. Read all files in /Users/abhinav/AI Brain/Rythmiq OS/projects/rythmiq-one/
3. Give Abhinav a structured briefing:
   - Current pipeline status
   - Last session's decisions
   - Uncommitted/undeployed work
   - What to focus on today
4. Ask: "Are these priorities still accurate, or has anything changed?"

Do not write a single line of code until this briefing is complete.

## UI DEVELOPMENT RULE
Before writing any new component or screen, read `app-v2/docs/DESIGN_SYSTEM.md` in full.

- All colour references must use `Colors.semantic.*` or `Colors.palette.*` tokens — no hardcoded hex values
- All font sizes and weights must use `Typography.*` spread syntax — no inline `fontSize` or `fontWeight`
- No `fontWeight: '600'` anywhere — Satoshi has no SemiBold; use `'700'` (Bold) or `'500'` (Medium)
- Status colours must come from `StatusConfig` (once created) — never hardcode processing/completed colours
- Button variants must use the `Button` component with a named `variant` prop — no one-off button styles
