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
  signup: (email: string, password: string) => Promise<void>;
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
      if (session.valid && session.user) {
        setUser({
          id: session.user.id,
          email: session.user.email,
          created_at: '', // Session doesn't return this
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
  const signup = useCallback(async (email: string, password: string) => {
    const response = await authApi.signup(email, password);
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
