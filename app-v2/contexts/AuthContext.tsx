/**
 * Authentication Context Provider
 *
 * Uses supabase.auth.onAuthStateChange for reactive, event-driven auth state.
 * INITIAL_SESSION fires from local SecureStore in milliseconds on startup.
 */

import React, { createContext, useContext, useEffect, useRef, useState, useCallback, ReactNode } from 'react';
import { authApi, clearAuthTokens, supabase } from '../services/api';
import type { User, AuthState } from '../types';

interface AuthContextType extends AuthState {
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string, name?: string) => Promise<void>;
  loginWithGoogle: () => Promise<void>;
  loginWithApple: () => Promise<void>;
  logout: () => Promise<void>;
  refreshSession: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

interface AuthProviderProps {
  children: ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!supabase) {
      setIsLoading(false);
      return;
    }

    // Fallback: if INITIAL_SESSION never fires (storage/SDK failure), unblock
    // routing after 10 seconds. Does NOT sign the user out.
    timeoutRef.current = setTimeout(() => {
      setIsLoading(false);
    }, 10_000);

    const { data: { subscription } } = supabase.auth.onAuthStateChange((event, session) => {
      if (event === 'INITIAL_SESSION' || event === 'SIGNED_IN' || event === 'TOKEN_REFRESHED') {
        if (session?.user) {
          setUser({
            id: session.user.id,
            email: session.user.email ?? '',
            name: (session.user.user_metadata?.name as string | undefined) ?? undefined,
            created_at: session.user.created_at ?? '',
          });
          setIsAuthenticated(true);
        } else {
          setUser(null);
          setIsAuthenticated(false);
        }
        if (event === 'INITIAL_SESSION') {
          clearTimeout(timeoutRef.current!);
          setIsLoading(false);
        }
      }

      if (event === 'SIGNED_OUT') {
        setUser(null);
        setIsAuthenticated(false);
        clearTimeout(timeoutRef.current!);
        setIsLoading(false);
      }
    });

    return () => {
      subscription.unsubscribe();
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, []);

  /** No-op: Supabase handles refresh automatically via autoRefreshToken. */
  const refreshSession = useCallback(async () => {
    await supabase?.auth.getSession();
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    await authApi.login(email, password);
    // onAuthStateChange fires SIGNED_IN and updates state automatically.
  }, []);

  const signup = useCallback(async (email: string, password: string, name?: string) => {
    const response = await authApi.signup(email, password, name);
    if (!response.access_token) {
      throw new Error('Account created. Please check your email and verify your account before signing in.');
    }
    // onAuthStateChange fires SIGNED_IN and updates state automatically.
  }, []);

  const loginWithGoogle = useCallback(async () => {
    await authApi.loginWithOAuth('google');
    // onAuthStateChange fires SIGNED_IN and updates state automatically.
  }, []);

  const loginWithApple = useCallback(async () => {
    await authApi.loginWithOAuth('apple');
    // onAuthStateChange fires SIGNED_IN and updates state automatically.
  }, []);

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } catch {
      // swallow — clearAuthTokens below guarantees local session is cleared
    } finally {
      await clearAuthTokens();
      // onAuthStateChange fires SIGNED_OUT and clears user/isAuthenticated.
    }
  }, []);

  const value: AuthContextType = {
    user,
    isLoading,
    isAuthenticated,
    login,
    signup,
    loginWithGoogle,
    loginWithApple,
    logout,
    refreshSession,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}

export default AuthContext;
