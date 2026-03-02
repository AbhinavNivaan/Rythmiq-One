# Supabase Setup (Phase 1)

This document covers only the baseline Supabase setup for Rythmiq mobile + API.
Google and Apple provider setup is intentionally deferred to the next phase.

## 1) Mobile environment

Set these in `app-v2/.env`:

- `EXPO_PUBLIC_SUPABASE_URL`
- `EXPO_PUBLIC_SUPABASE_ANON_KEY`
- `EXPO_PUBLIC_DEV_SANDBOX=false`

## 2) Backend environment

Set these in the API `.env` (workspace root):

- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_JWT_SECRET`

## 3) Supabase Auth core settings

In Supabase Dashboard → Authentication → URL Configuration:

- Add redirect URL: `rythmiq://auth/callback`

In Supabase Dashboard → Authentication → Providers:

- Keep Email enabled
- Google/Apple can remain disabled for now (next phase)

## 4) App-side callback route

The app callback route is implemented at:

- `app-v2/app/auth/callback.tsx`

OAuth flow uses this redirect path:

- `auth/callback`

## 5) Quick verification

1. Confirm Supabase auth settings endpoint returns `200` with anon key.
2. Launch app and verify email signup/login works.
3. Confirm API auth routes are mounted (`/auth/signup`, `/auth/login`, `/auth/session`).

## Next phase

For Google provider setup, continue with:

- `app-v2/GOOGLE_AUTH_SETUP.md`
