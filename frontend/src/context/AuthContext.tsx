import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import type { ReactNode } from 'react';
import type { User, AuthContextType, LoginResult } from '../types';
import { api, setUnauthHandler, setCsrfToken } from '../lib/api';

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  // undefined = not yet initialized (loading); null = loaded, no session; User = authenticated
  const [user, setUser] = useState<User | null | undefined>(undefined);
  const [sessionExpired, setSessionExpired] = useState(false);
  const loading = user === undefined;

  const clearSessionExpired = useCallback(() => setSessionExpired(false), []);

  // Called by the session-expired handler inside api.ts
  useEffect(() => {
    setUnauthHandler(() => {
      setUser(null);
      setCsrfToken(null);
      setSessionExpired(true);
    });
  }, []);

  const refreshUser = useCallback(async () => {
    try {
      const res = await api('/api/auth/me', { skipUnauth: true } as RequestInit & { skipUnauth: boolean });
      if (res.ok) {
        setUser(await res.json());
      } else {
        setUser(null);
      }
    } catch {
      setUser(null);
    }
  }, []);

  // Restore session on mount — setState only in async callbacks, satisfying react-hooks/set-state-in-effect
  useEffect(() => {
    api('/api/auth/me', { skipUnauth: true } as RequestInit & { skipUnauth: boolean })
      .then(res => res.ok ? res.json() : null)
      .then((userData: User | null) => setUser(userData))
      .catch(() => setUser(null));
  }, []);

  const login = useCallback(async (email: string, password: string): Promise<LoginResult> => {
    try {
      const res = await api('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password }),
        skipUnauth: true,
      } as RequestInit & { skipUnauth: boolean });

      const data = await res.json();

      if (res.status === 403) {
        return { success: false, error: data.error ?? 'Account temporarily locked. Try again later.' };
      }
      if (!res.ok) {
        return { success: false, error: data.error ?? 'Invalid email or password.' };
      }
      if (data.mfa_required) {
        return { success: true, mfaRequired: true, challengeToken: data.session_challenge };
      }

      await refreshUser();
      return { success: true };
    } catch {
      return { success: false, error: 'Connection error. Please try again.' };
    }
  }, [refreshUser]);

  const loginMfa = useCallback(async (challengeToken: string, totpCode: string) => {
    try {
      const res = await api('/api/auth/login/mfa', {
        method: 'POST',
        body: JSON.stringify({ session_challenge: challengeToken, totp_code: totpCode }),
        skipUnauth: true,
      } as RequestInit & { skipUnauth: boolean });

      const data = await res.json();
      if (!res.ok) {
        return { success: false, error: data.error ?? 'Invalid TOTP code.' };
      }

      await refreshUser();
      return { success: true };
    } catch {
      return { success: false, error: 'Connection error. Please try again.' };
    }
  }, [refreshUser]);

  const logout = useCallback(async () => {
    try {
      await api('/api/auth/logout', { method: 'POST' });
    } finally {
      setUser(null);
      setCsrfToken(null);
    }
  }, []);

  if (loading) return null;

  return (
    <AuthContext.Provider value={{
      user: user as User | null,
      isAuthenticated: !!user,
      sessionExpired,
      clearSessionExpired,
      refreshUser,
      login,
      loginMfa,
      logout,
    }}>
      {children}
    </AuthContext.Provider>
  );
};

// eslint-disable-next-line react-refresh/only-export-components
export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
