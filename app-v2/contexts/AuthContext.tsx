/**
 * Authentication Context Provider
 * 
 * Manages global authentication state and provides auth methods.
 */

import React, { createContext, useContext, useEffect, useState, useCallback, ReactNode } from 'react';
import { authApi, getAuthToken, clearAuthTokens } from '../services/api';
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

  /**
   * Check existing session on mount
   */
  const refreshSession = useCallback(async () => {
    try {
      const token = await getAuthToken();
      if (!token) {
        setUser(null);
        setIsAuthenticated(false);
        return;
      }

      const session = await authApi.getSession();
      if (session.user_id) {
        setUser({
          id: session.user_id,
          email: session.email ?? '',
          name: session.name ?? undefined,
          created_at: '',
        });
        setIsAuthenticated(true);
      } else {
        await clearAuthTokens();
        setUser(null);
        setIsAuthenticated(false);
      }
    } catch (error) {
      console.error('Session refresh failed:', error);
      await clearAuthTokens();
      setUser(null);
      setIsAuthenticated(false);
    }
  }, []);

  useEffect(() => {
    const init = async () => {
      setIsLoading(true);
      await refreshSession();
      setIsLoading(false);
    };
    init();
  }, [refreshSession]);

  /**
   * Login with email and password
   */
  const login = useCallback(async (email: string, password: string) => {
    const response = await authApi.login(email, password);
    setUser(response.user);
    setIsAuthenticated(true);
  }, []);

  /**
   * Sign up with email and password
   */
  const signup = useCallback(async (email: string, password: string, name?: string) => {
    const response = await authApi.signup(email, password, name);

    if (!response.access_token) {
      setUser(null);
      setIsAuthenticated(false);
      throw new Error('Account created. Please check your email and verify your account before signing in.');
    }

    setUser(response.user);
    setIsAuthenticated(true);
  }, []);

  /**
   * Login with Google OAuth
   */
  const loginWithGoogle = useCallback(async () => {
    const response = await authApi.loginWithOAuth('google');
    setUser(response.user);
    setIsAuthenticated(true);
  }, []);

  /**
   * Login with Apple OAuth
   */
  const loginWithApple = useCallback(async () => {
    const response = await authApi.loginWithOAuth('apple');
    setUser(response.user);
    setIsAuthenticated(true);
  }, []);

  /**
   * Logout current session
   */
  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } catch (error) {
      console.error('Logout error:', error);
    } finally {
      setUser(null);
      setIsAuthenticated(false);
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

/**
 * Hook to access auth context
 */
export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}

export default AuthContext;
