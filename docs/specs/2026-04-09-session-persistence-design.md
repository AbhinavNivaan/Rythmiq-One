# Session Persistence — Design Spec

**Date:** 2026-04-09
**Status:** Approved
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
- Any navigation to a protected screen from any entry point (deep link, push notification, background resume) is caught and redirected to login if unauthenticated.
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
- `clearAuthTokens()` → `supabase.auth.signOut()`

The web platform path (localStorage / in-memory fallback) is preserved as-is — the adapter only applies on native.

---

### Layer 2 — AuthContext (reactive, event-driven)

**File:** `app-v2/contexts/AuthContext.tsx`

Replace the `useEffect` + `refreshSession()` mount pattern with a `supabase.auth.onAuthStateChange()` subscription.

**Lifecycle:**
1. On mount: subscribe to `onAuthStateChange`. Set `isLoading = true`.
2. First event fires (either `SIGNED_IN` with a restored session, or `SIGNED_OUT` with null): set `isLoading = false`, update `user` and `isAuthenticated` from the session payload.
3. Subsequent events (token refresh, sign-out, etc.) update state automatically.
4. On unmount: unsubscribe.

**Auth methods** (`login`, `signup`, `loginWithGoogle`, `loginWithApple`, `logout`) continue to call Supabase operations as before. Manual `setUser` / `setIsAuthenticated` calls after each operation are removed — `onAuthStateChange` handles state propagation automatically.

**`refreshSession()`** is kept on the public interface (existing callers) but its body becomes `supabase.auth.getSession()` — a no-op in practice since Supabase auto-refreshes.

---

### Layer 3 — Routing (layout-level guards)

#### `app-v2/app/index.tsx` — Cold start gate

Reads `isLoading` and `isAuthenticated` from `AuthContext`. Also reads an `onboarding_seen` flag from SecureStore.

| State | Route |
|---|---|
| `isLoading === true` | Render null (splash held open by font loader) |
| `isAuthenticated === true` | `/(tabs)/dashboard` |
| `isAuthenticated === false` + onboarding not seen | `/onboarding` |
| `isAuthenticated === false` + onboarding seen | `/(auth)/login` |

The `onboarding_seen` flag is written to SecureStore when the user taps "Get Started" on the onboarding screen (`app-v2/app/onboarding.tsx`), before `router.replace('/(auth)/login')`.

#### `app-v2/app/(auth)/_layout.tsx` — Auth screen guard

| State | Behaviour |
|---|---|
| `isLoading === true` | Render null — no flash of login screen |
| `isAuthenticated && !isLoading` | Redirect to `/(tabs)/dashboard` |
| `!isAuthenticated && !isLoading` | Render auth screens normally |

Prevents a logged-in user reaching login or signup via stale navigation or back-stack.

#### `app-v2/app/(tabs)/_layout.tsx` — Protected route guard

Calls `useSessionGate()` hook. If `!gate.ready && !isLoading`: redirect to `/(auth)/login`.

This is the permanent catch-all: any navigation to any tab screen from any entry point (deep link, push notification, cold start with expired session) is intercepted here.

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
| `app-v2/services/api.ts` | Add `ExpoSecureStoreAdapter`; replace manual token functions; update Supabase client init |
| `app-v2/contexts/AuthContext.tsx` | Replace mount logic with `onAuthStateChange` subscription; simplify auth methods |
| `app-v2/app/index.tsx` | Replace `<Redirect>` with session gate logic |
| `app-v2/app/onboarding.tsx` | Write `onboarding_seen` flag to SecureStore on "Get Started" |
| `app-v2/app/(auth)/_layout.tsx` | Add authenticated-user redirect guard |
| `app-v2/app/(tabs)/_layout.tsx` | Add `useSessionGate()` guard |
| `app-v2/hooks/useSessionGate.ts` | New file — biometric hook point |

---

## Error Handling

- If SecureStore read fails inside the adapter, return `null` (treats as no session → login).
- If `onAuthStateChange` never fires (network issue, Supabase unreachable): `isLoading` stays true and splash stays visible. A timeout of 8 seconds forces `isLoading = false` and routes to login as a fallback.
- Session expiry with no refresh token: Supabase fires `SIGNED_OUT`, `isAuthenticated` becomes false, layout guard catches it and redirects to login.

---

## What Is Not Changed

- All API request logic in `apiRequest()` — only `getAuthToken()` changes internally.
- The `authApi` object and all its methods — same signatures, same call sites.
- OAuth flow (`loginWithGoogle`, `loginWithApple`) — same WebBrowser flow, same callback handling.
- Web platform storage fallback (localStorage / in-memory).
