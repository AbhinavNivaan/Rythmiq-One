/**
 * useSessionGate
 *
 * Returns whether the user may access protected tab screens.
 * Today: delegates to isAuthenticated.
 * Future: add `const { verified } = useBiometric()` and return
 *   `{ ready: isAuthenticated && verified, isLoading }` — no change to callers.
 */

import { useAuth } from '../contexts/AuthContext';

export interface SessionGate {
  ready: boolean;
  isLoading: boolean;
}

export function useSessionGate(): SessionGate {
  const { isAuthenticated, isLoading } = useAuth();
  return { ready: isAuthenticated, isLoading };
}
