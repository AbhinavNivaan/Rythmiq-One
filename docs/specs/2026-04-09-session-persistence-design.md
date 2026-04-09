# Session Persistence — Design Spec

**Date:** 2026-04-09
**Status:** Approved (red-team reviewed 2026-04-09)
**Approach:** B + C (Supabase native session management + layout-level auth guards)

---

## Problem

The app logs users out every time they close and reopen it. The access and refresh tokens are persisted in `expo-secure-store`, and `AuthContext.refreshSession()` correctly restores them on mount — but `index.tsx` unconditionally redirects to `/onboarding`, discarding the restored session before it can influence routing.

A secondary problem: the manual token management layer in `api.ts` (`storeAuthTokens`, `tryRefreshToken`, `AUTH_TOKEN_KEY`, `REFRESH_TOKEN_KEY`) reimplements behaviour that Supabase already handles natively and correctly. Left in place, it is a source of future edge cases around token rotation and session invalidation events.

---

## Goals

- A user with a valid session opens the app and lands on the dashboard — no login, no onboarding.
- A first-time user sees onboarding, then login.
- A returning user with no valid session sees login directly (no onboarding again).
- Any navigation to any tab screen from any entry point (deep link, push notification, background resume) is caught and redirected to login if unauthenticated.
- The architecture accommodates biometric re-auth in the future without changing routing logic.

---

## Architecture

### Layer 1 — Storage (Supabase native, SecureStore-backed)

**File:** `app-v2/services/api.ts`

Replace the manual token storage layer with an `ExpoSecureStoreAdapter` that implements Supabase's `SupportedStorage` interface using `expo-secure-store`.

```
ExpoSecureStoreAdapter = {
  getItem(key): Promise<string | null>  → SecureStore.getItemAsync(key)
  setItem(key, value): Promise<void>    → SecureStore.setItemAsync(key, value)
  removeItem(key): Promise<void>        → SecureStore.deleteItemAsync(key)
}
```

The Supabase client is initialised with this adapter:

```ts
createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
  auth: {
    storage: ExpoSecureStoreAdapter,
    autoRefreshToken: true,
    persistSession: true,
    detectSessionInUrl: false,
  }
})
```

**Removed from `api.ts`:**
- `AUTH_TOKEN_KEY`, `REFRESH_TOKEN_KEY` constants
- `storeAuthTokens()`
- `tryRefreshToken()`
- Manual SecureStore read/write in `getAuthToken()` and `clearAuthTokens()`

**Replaced with:**
- `getAuthToken()` → `(await supabase.auth.getSession()).data.session?.access_token ?? null`
- `clearAuthTokens()` → `supabase.auth.signOut({ scope: 'local' })` — clears local session only, no network call; global invalidation is handled by `authApi.logout()` calling the backend

#### 401 retry in `apiRequest()`

`apiRequest()` currently calls `tryRefreshToken()` on 401 to retry once with a fresh token. `tryRefreshToken()` is being removed. The 401 retry path is updated to call `supabase.auth.refreshSession()` directly instead. With `autoRefreshToken: true` on the Supabase client, proactive refreshes happen before expiry — the 401 retry becomes a last-resort safety net only.

The web platform path (localStorage / in-memory fallback) is preserved as-is — the adapter only applies on native.

#### Session hydration after email/password login

`authApi.login()` and `authApi.signup()` call the FastAPI backend, which returns `access_token` and `refresh_token`. The Supabase client in-memory session is never set by this flow — so `supabase.auth.getSession()` would return null after email/password login unless explicitly hydrated.

Fix: after a successful backend login or signup response, call:
```ts
await supabase.auth.setSession({
  access_token: response.access_token,
  refresh_token: response.refresh_token,
})
```
This stores the tokens via the SecureStore adapter and sets the in-memory session, making `getSession()` work correctly for all subsequent API calls.

#### Removing the parallel token system in `security.ts`

`app-v2/services/security.ts` contains a duplicate auth layer with its own `getAuthToken()`, `storeAuthTokens()`, `clearAuthTokens()`, and a 30-minute `SESSION_EXPIRY` check using the same SecureStore keys (`rythmiq_auth_token`, `rythmiq_refresh_token`). It is not wired into the current auth flow (nothing imports its auth functions), but the conflicting keys make it a landmine for future confusion.

**Action:** Remove the auth-related functions from `security.ts` (`storeAuthTokens`, `getAuthToken`, `getRefreshToken`, `clearAuthTokens`, `isSessionValid`, `updateLastActivity`, `getSessionTimeRemaining`, `SESSION_EXPIRY` key, `SESSION_TIMEOUT_MS`). Retain everything else in `security.ts`: `secureStore`, `secureRetrieve`, `secureDelete`, the crypto utilities, and `BIOMETRIC_ENABLED` storage (needed for future biometric feature).

`app-v2/hooks/useSessionTimeout.ts` imports `isSessionValid`, `updateLastActivity`, `getSessionTimeRemaining`, `clearAuthTokens`, and `SESSION_TIMEOUT_MS` from `security.ts`. Nothing in the codebase imports `useSessionTimeout` — it is dead code. Remove it entirely alongside the `security.ts` auth functions to avoid a build break.

---

### Layer 2 — AuthContext (reactive, event-driven)

**File:** `app-v2/contexts/AuthContext.tsx`

Replace the `useEffect` + `refreshSession()` mount pattern with a `supabase.auth.onAuthStateChange()` subscription.

**Lifecycle:**
1. On mount: subscribe to `onAuthStateChange`. Set `isLoading = true`.
2. Supabase v2 fires `INITIAL_SESSION` on startup (from local SecureStore, not the network — fires in milliseconds). This event carries either a valid session or null. When it fires: set `isLoading = false`, update `user` and `isAuthenticated` from the session payload.
3. Subsequent events (`SIGNED_IN`, `SIGNED_OUT`, `TOKEN_REFRESHED`, etc.) update state automatically.
4. On unmount: unsubscribe.

**Auth methods** (`login`, `signup`, `loginWithGoogle`, `loginWithApple`, `logout`) trigger Supabase operations. Manual `setUser` / `setIsAuthenticated` calls after each operation are removed — `onAuthStateChange` handles state propagation automatically. `setSession()` is NOT called from `AuthContext` — it is called inside `api.ts`'s `authApi.login/signup` (Layer 1 only). Single authority.

**`refreshSession()`** is kept on the public interface but its body becomes `supabase.auth.getSession()` — a no-op since Supabase auto-refreshes.

---

### Layer 3 — Routing (layout-level guards)

#### `app-v2/app/_layout.tsx` — Splash screen lifecycle

The current implementation hides the splash when fonts load, independently of auth. This would cause a blank frame while auth resolves.

Fix: `SplashScreen.hideAsync()` is called only when **both** fonts are loaded **and** `isLoading === false` (auth has resolved). Both conditions must be met before the splash is dismissed.

#### `app-v2/app/index.tsx` — Cold start gate

Reads `isLoading` and `isAuthenticated` from `AuthContext`. Also reads an `onboarding_seen` flag from SecureStore.

| State | Route |
|---|---|
| `isLoading === true` | Render null (splash held open — see `_layout.tsx` fix above) |
| `isAuthenticated === true` | `/(tabs)/dashboard` |
| `isAuthenticated === false` + onboarding not seen | `/onboarding` |
| `isAuthenticated === false` + onboarding seen | `/(auth)/login` |

**`onboarding_seen` flag:**
- Written to SecureStore when the user taps "Get Started" on the onboarding screen, before `router.replace('/(auth)/login')`
- **Migration for existing installs:** on startup, before reading the flag, check if a Supabase session exists in SecureStore. If yes, backfill `onboarding_seen = true`. This prevents existing users (v4/v5) who have no flag from being routed back through onboarding.

#### `app-v2/app/(auth)/_layout.tsx` — Auth screen guard

| State | Behaviour |
|---|---|
| `isLoading === true` | Render null — no flash of login screen |
| `isAuthenticated && !isLoading` | Redirect to `/(tabs)/dashboard` |
| `!isAuthenticated && !isLoading` | Render auth screens normally |

Prevents a logged-in user reaching login or signup via stale navigation or back-stack.

#### `app-v2/app/(tabs)/_layout.tsx` — Protected route guard

Calls `useSessionGate()` hook. If `!gate.ready && !isLoading`: redirect to `/(auth)/login`.

This is the catch-all for all tab screens: any navigation to any tab screen from any entry point is intercepted here. Note: `app/auth/callback.tsx` is intentionally outside this guard — it is the OAuth redirect handler and must remain unprotected.

---

### Biometric Hook Point

**File:** `app-v2/hooks/useSessionGate.ts` (new file)

Today:
```ts
export function useSessionGate() {
  const { isAuthenticated, isLoading } = useAuth();
  return { ready: isAuthenticated, isLoading };
}
```

When biometric is added later, this becomes:
```ts
export function useSessionGate() {
  const { isAuthenticated, isLoading } = useAuth();
  const { verified } = useBiometric(); // future hook
  return { ready: isAuthenticated && verified, isLoading };
}
```

The `(tabs)/_layout.tsx` guard does not change. Only `useSessionGate` changes internally.

---

## Files Changed

| File | Change |
|---|---|
| `app-v2/services/api.ts` | Add `ExpoSecureStoreAdapter`; replace manual token functions; update Supabase client init; add `setSession()` after email/password login; update 401 retry to use `supabase.auth.refreshSession()` |
| `app-v2/services/security.ts` | Remove auth-related functions (see Layer 1); retain crypto utilities and biometric flag storage |
| `app-v2/hooks/useSessionTimeout.ts` | **Delete** — dead code; imports the security.ts auth functions being removed |
| `app-v2/contexts/AuthContext.tsx` | Replace mount logic with `onAuthStateChange` subscription; simplify auth methods; remove manual setUser/setIsAuthenticated calls |
| `app-v2/app/_layout.tsx` | Tie `SplashScreen.hideAsync()` to both fonts loaded AND auth resolved |
| `app-v2/app/index.tsx` | Replace `<Redirect>` with session gate logic + onboarding migration |
| `app-v2/app/onboarding.tsx` | Write `onboarding_seen` flag to SecureStore on "Get Started" |
| `app-v2/app/(auth)/_layout.tsx` | Add authenticated-user redirect guard |
| `app-v2/app/(tabs)/_layout.tsx` | Add `useSessionGate()` guard |
| `app-v2/hooks/useSessionGate.ts` | New file — biometric hook point |

---

## Error Handling

- If SecureStore read fails inside the adapter, return `null` (treats as no session → login).
- `INITIAL_SESSION` fires from local SecureStore in milliseconds — it does not wait for a network round-trip. In practice, auth resolves before the splash would be visible.
- If `INITIAL_SESSION` never fires (pathological SDK or storage failure): after 10 seconds, `isLoading` is forced false and a graceful error view is rendered ("Something went wrong — tap to restart") instead of routing to login. This preserves session integrity (no forced sign-out), gives the user a recovery action, and is operationally visible. It does NOT route to login — that would destroy a potentially valid session.
- Session expiry with no refresh token: Supabase fires `SIGNED_OUT`, `isAuthenticated` becomes false, layout guard catches it and redirects to login.
- `clearAuthTokens()` uses `{ scope: 'local' }` — guaranteed to clear local session even if offline or if the backend call in `authApi.logout()` fails.

---

## What Is Not Changed

- `apiRequest()` structure is unchanged except the 401 retry: `tryRefreshToken()` call is replaced with `supabase.auth.refreshSession()`. All other request logic is untouched.
- The `authApi` object and all its methods — same signatures, same call sites.
- OAuth flow (`loginWithGoogle`, `loginWithApple`) — same WebBrowser flow, same callback handling.
- Web platform storage fallback (localStorage / in-memory).
- `auth/callback.tsx` — intentionally unprotected OAuth redirect handler, unchanged.
