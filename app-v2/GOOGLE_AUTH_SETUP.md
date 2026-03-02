# Google Auth Setup (Phase 2)

This guide enables **Google sign-in** for the mobile app using Supabase OAuth.

## 1) Current app redirect URI

Google OAuth in app now uses:

- `rythmiq://auth/callback`

## 2) Configure Supabase Auth URLs

In Supabase Dashboard:

1. Go to **Authentication → URL Configuration**
2. Ensure you are in project ref: `qpixafvazayfjamgywbb`
3. Set **Site URL** to a valid HTTPS URL (not localhost), for example:
  - `https://app.rythmiq.one`
4. Add this to **Additional Redirect URLs**:
  - `rythmiq://**` (recommended for native deep links)
  - `rythmiq://auth/callback` (optional explicit entry)

## 2.1 Runtime requirement

Google OAuth can work in Expo Go or development builds, but redirect URLs must match runtime exactly.

- Expo Go uses `exp://...`
- Development/production app uses `rythmiq://...`

For Android native runtime, app uses implicit OAuth callback handling to avoid PKCE verifier loss when returning from browser.

## 3) Create Google OAuth credentials

In Google Cloud Console:

1. Open **APIs & Services → Credentials**
2. Create or use an OAuth Client ID (Web application)
3. In **Authorized redirect URIs**, add:
   - `https://qpixafvazayfjamgywbb.supabase.co/auth/v1/callback`

## 4) Enable Google provider in Supabase

In Supabase Dashboard:

1. Go to **Authentication → Providers → Google**
2. Toggle Google provider **ON**
3. Paste Google **Client ID** and **Client Secret**
4. Save

## 5) Verify provider is active

Auth settings endpoint should include `"google": true`:

- `GET https://qpixafvazayfjamgywbb.supabase.co/auth/v1/settings`

## 6) Test flow

1. Open app login screen
2. Tap Google button
3. Complete Google consent
4. Confirm return to app and dashboard login success

## Troubleshooting

- Error: **Google sign-in is not enabled in Supabase yet**
  - Google provider is still off in Supabase

- Error: **redirect is not configured**
  - Missing `rythmiq://**` in Supabase redirect URLs

- Browser opens but does not return to app
  - Confirm app scheme is `rythmiq` in `app.json`
  - If using Expo Go, add the exact `exp://.../--/auth/callback` URL shown in app
  - Rebuild/restart app after auth config changes

- Error mentions missing code verifier on Android
  - Restart the app and retry (flow now uses implicit callback on native)
  - Ensure Supabase redirect allow-list includes the exact `exp://.../--/auth/callback` value shown in app

- Redirect goes to `http://localhost:3000` after Google consent
  - This means Supabase did not apply the mobile `redirect_to`
  - Most common cause: Site URL still points to localhost
  - Recheck **Authentication → URL Configuration → Additional Redirect URLs**
  - Ensure this wildcard entry exists exactly:
    - `rythmiq://**`
  - Optionally also keep this explicit entry:
    - `rythmiq://auth/callback`
  - Set **Site URL** to a non-localhost HTTPS URL
  - Ensure there is no typo like `rythmq://...`
