import React, { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { CheckCircle, ShieldAlert, Home } from 'lucide-react';
import { api } from '../lib/api';

const AcceptInvite: React.FC = () => {
  const [searchParams] = useSearchParams();
  const [displayName, setDisplayName] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const token = searchParams.get('token') ?? '';

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (!displayName.trim()) { setError('Please enter your name.'); return; }
    if (!password || !confirm) { setError('Both password fields are required.'); return; }
    if (password !== confirm) { setError('Passwords do not match.'); return; }
    if (!token) { setError('Invitation token is missing. Please use the link from your email.'); return; }

    setIsLoading(true);
    try {
      const res = await api('/api/auth/accept-invite', {
        method: 'POST',
        body: JSON.stringify({ token, password, display_name: displayName.trim() }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error ?? 'Failed to create your account. The invitation may have expired.');
        return;
      }
      setDone(true);
    } catch {
      setError('Connection error. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div style={{ display: 'flex', minHeight: '100vh', alignItems: 'center', justifyContent: 'center', padding: '1rem' }}>
      <div className="glass-panel" style={{ width: '100%', maxWidth: '400px', padding: '2rem' }}>
        <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
          <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '1rem' }}>
            <div style={{ backgroundColor: 'var(--accent-light)', padding: '1rem', borderRadius: '50%' }}>
              <Home size={32} color="var(--accent-primary)" />
            </div>
          </div>
          <h2>Join FinTrack</h2>
          <p style={{ color: 'var(--text-secondary)' }}>Accept your household invitation</p>
        </div>

        {done ? (
          <div style={{ textAlign: 'center' }}>
            <CheckCircle size={48} color="var(--success)" style={{ marginBottom: '1rem' }} />
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
              Your account is ready. Sign in to see what's been shared with you.
            </p>
            <Link to="/login" className="btn btn-primary" style={{ display: 'inline-block', marginTop: '1.5rem' }}>
              Sign In
            </Link>
          </div>
        ) : (
          <>
            {error && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.75rem', backgroundColor: 'rgba(239, 68, 68, 0.1)', color: 'var(--danger)', borderRadius: 'var(--radius-md)', marginBottom: '1rem', fontSize: '0.875rem' }}>
                <ShieldAlert size={18} />
                <span>{error}</span>
              </div>
            )}
            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label className="form-label" htmlFor="displayName">Your Name</label>
                <input id="displayName" type="text" className="form-input" value={displayName}
                  onChange={e => setDisplayName(e.target.value)} maxLength={100} placeholder="Jane Doe" autoComplete="name" />
              </div>
              <div className="form-group">
                <label className="form-label" htmlFor="password">Password</label>
                <input id="password" type="password" className="form-input" value={password}
                  onChange={e => setPassword(e.target.value)} placeholder="••••••••" autoComplete="new-password" />
              </div>
              <div className="form-group" style={{ marginBottom: '1.5rem' }}>
                <label className="form-label" htmlFor="confirm">Confirm Password</label>
                <input id="confirm" type="password" className="form-input" value={confirm}
                  onChange={e => setConfirm(e.target.value)} placeholder="••••••••" autoComplete="new-password" />
              </div>
              <button type="submit" className="btn btn-primary" style={{ width: '100%' }} disabled={isLoading || !token}>
                {isLoading ? 'Creating account…' : 'Create Account'}
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  );
};

export default AcceptInvite;
