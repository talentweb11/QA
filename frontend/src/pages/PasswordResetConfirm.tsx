import React, { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { CheckCircle, ShieldAlert, Wallet } from 'lucide-react';
import { api } from '../lib/api';

const PasswordResetConfirm: React.FC = () => {
  const [searchParams] = useSearchParams();
  const [newPassword, setNewPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const token = searchParams.get('token') ?? '';

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (!newPassword || !confirm) {
      setError('Both fields are required.');
      return;
    }
    if (newPassword !== confirm) {
      setError('Passwords do not match.');
      return;
    }
    if (!token) {
      setError('Reset token is missing. Please use the link from your email.');
      return;
    }

    setIsLoading(true);
    try {
      const res = await api('/api/auth/password-reset/confirm', {
        method: 'POST',
        body: JSON.stringify({ token, new_password: newPassword }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error ?? 'Failed to reset password. The link may have expired.');
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
              <Wallet size={32} color="var(--accent-primary)" />
            </div>
          </div>
          <h2>New Password</h2>
          <p style={{ color: 'var(--text-secondary)' }}>Choose a strong password</p>
        </div>

        {done ? (
          <div style={{ textAlign: 'center' }}>
            <CheckCircle size={48} color="var(--success)" style={{ marginBottom: '1rem' }} />
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
              Your password has been updated. Please sign in with your new password.
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
                <label className="form-label" htmlFor="newPassword">New Password</label>
                <input id="newPassword" type="password" className="form-input" value={newPassword}
                  onChange={e => setNewPassword(e.target.value)} placeholder="••••••••" autoComplete="new-password" />
              </div>
              <div className="form-group" style={{ marginBottom: '1.5rem' }}>
                <label className="form-label" htmlFor="confirm">Confirm New Password</label>
                <input id="confirm" type="password" className="form-input" value={confirm}
                  onChange={e => setConfirm(e.target.value)} placeholder="••••••••" autoComplete="new-password" />
              </div>
              <button type="submit" className="btn btn-primary" style={{ width: '100%' }} disabled={isLoading || !token}>
                {isLoading ? 'Updating…' : 'Update Password'}
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  );
};

export default PasswordResetConfirm;
