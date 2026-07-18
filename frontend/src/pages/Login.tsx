import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation, Link } from 'react-router-dom';
import { Wallet, ShieldAlert, Info } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

const Login: React.FC = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  // MFA step 2 state
  const [mfaRequired, setMfaRequired] = useState(false);
  const [challengeToken, setChallengeToken] = useState('');
  const [totpCode, setTotpCode] = useState('');

  const { login, loginMfa, isAuthenticated, sessionExpired, clearSessionExpired } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  // If already logged in, redirect away — '/' lets RoleRedirect pick the
  // correct landing per role (admin → /admin/users, advisor → /advisor/clients…).
  useEffect(() => {
    if (isAuthenticated) {
      navigate('/', { replace: true });
    }
  }, [isAuthenticated, navigate]);

  // Clear session-expired flag when user lands on login
  useEffect(() => {
    return () => clearSessionExpired();
  }, [clearSessionExpired]);

  const handleStep1 = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (!email || !password) {
      setError('Please enter both email and password.');
      return;
    }
    setIsLoading(true);
    try {
      const result = await login(email, password);
      if (!result.success) {
        setError(result.error ?? 'Login failed.');
        return;
      }
      if (result.mfaRequired && result.challengeToken) {
        setChallengeToken(result.challengeToken);
        setMfaRequired(true);
        return;
      }
      redirectAfterLogin();
    } finally {
      setIsLoading(false);
    }
  };

  const handleStep2 = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (!totpCode) {
      setError('Please enter your authenticator code.');
      return;
    }
    setIsLoading(true);
    try {
      const result = await loginMfa(challengeToken, totpCode);
      if (!result.success) {
        setError(result.error ?? 'Invalid code.');
        return;
      }
      redirectAfterLogin();
    } finally {
      setIsLoading(false);
    }
  };

  const redirectAfterLogin = () => {
    const from = (location.state as { from?: string })?.from;
    // Default to '/' so RoleRedirect routes each role to its correct landing.
    navigate(from ?? '/', { replace: true });
  };

  return (
    <div style={{ display: 'flex', minHeight: '100vh', alignItems: 'center', justifyContent: 'center', padding: '1rem' }}>
      <div className="glass-panel" style={{ width: '100%', maxWidth: '400px', padding: '2rem' }}>
        <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
          <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '1rem' }}>
            <div style={{ backgroundColor: 'var(--accent-light)', padding: '1rem', borderRadius: '50%' }}>
              <Wallet size={32} color="var(--accent-primary)" />
            </div>
          </div>
          <h2>FinTrack</h2>
          <p style={{ color: 'var(--text-secondary)' }}>
            {mfaRequired ? 'Enter your authenticator code' : 'Sign in to your account'}
          </p>
        </div>

        {sessionExpired && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.75rem', backgroundColor: 'rgba(245, 158, 11, 0.1)', color: 'var(--warning)', borderRadius: 'var(--radius-md)', marginBottom: '1rem', fontSize: '0.875rem' }}>
            <Info size={18} />
            <span>Your session expired. Please sign in again.</span>
          </div>
        )}

        {error && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.75rem', backgroundColor: 'rgba(239, 68, 68, 0.1)', color: 'var(--danger)', borderRadius: 'var(--radius-md)', marginBottom: '1rem', fontSize: '0.875rem' }}>
            <ShieldAlert size={18} />
            <span>{error}</span>
          </div>
        )}

        {!mfaRequired ? (
          <form onSubmit={handleStep1}>
            <div className="form-group">
              <label className="form-label" htmlFor="email">Email Address</label>
              <input id="email" type="email" className="form-input" value={email}
                onChange={e => setEmail(e.target.value)} placeholder="you@example.com" autoComplete="email" />
            </div>
            <div className="form-group" style={{ marginBottom: '0.5rem' }}>
              <label className="form-label" htmlFor="password">Password</label>
              <input id="password" type="password" className="form-input" value={password}
                onChange={e => setPassword(e.target.value)} placeholder="••••••••" autoComplete="current-password" />
            </div>
            <div style={{ textAlign: 'right', marginBottom: '1.5rem' }}>
              <Link to="/password-reset" style={{ fontSize: '0.8125rem' }}>Forgot password?</Link>
            </div>
            <button type="submit" className="btn btn-primary" style={{ width: '100%' }} disabled={isLoading}>
              {isLoading ? 'Signing in…' : 'Sign In'}
            </button>
          </form>
        ) : (
          <form onSubmit={handleStep2}>
            <div className="form-group" style={{ marginBottom: '1.5rem' }}>
              <label className="form-label" htmlFor="totp">Authenticator Code</label>
              <input id="totp" type="text" inputMode="numeric" className="form-input" value={totpCode}
                onChange={e => setTotpCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                placeholder="000000" autoComplete="one-time-code" maxLength={6} />
            </div>
            <button type="submit" className="btn btn-primary" style={{ width: '100%' }} disabled={isLoading || totpCode.length !== 6}>
              {isLoading ? 'Verifying…' : 'Verify'}
            </button>
            <button type="button" style={{ width: '100%', marginTop: '0.5rem', background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: '0.875rem', padding: '0.5rem' }}
              onClick={() => { setMfaRequired(false); setChallengeToken(''); setTotpCode(''); setError(''); }}>
              ← Back to sign in
            </button>
          </form>
        )}

        {!mfaRequired && (
          <p style={{ marginTop: '1.5rem', textAlign: 'center', fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: 0 }}>
            Don't have an account?{' '}
            <Link to="/register">Create one</Link>
          </p>
        )}
      </div>
    </div>
  );
};

export default Login;
