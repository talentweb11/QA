import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { Wallet, ShieldAlert, CheckCircle } from 'lucide-react';
import { api } from '../lib/api';

const Register: React.FC = () => {
  const [email, setEmail] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (!email || !displayName || !password || !confirm) {
      setError('All fields are required.');
      return;
    }
    if (password !== confirm) {
      setError('Passwords do not match.');
      return;
    }

    setIsLoading(true);
    try {
      const res = await api('/api/auth/register', {
        method: 'POST',
        body: JSON.stringify({ email, display_name: displayName, password }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error ?? 'Registration failed.');
        return;
      }
      setSubmitted(true);
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
          <h2>Create Account</h2>
          <p style={{ color: 'var(--text-secondary)' }}>Join FinTrack to manage your finances</p>
        </div>

        {submitted ? (
          <div style={{ textAlign: 'center' }}>
            <CheckCircle size={48} color="var(--success)" style={{ marginBottom: '1rem' }} />
            <h3 style={{ marginBottom: '0.5rem' }}>Check your email</h3>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
              If this email is not already registered, a verification link has been sent. Click it to activate your account.
            </p>
            <Link to="/login" style={{ display: 'block', marginTop: '1.5rem' }}>Back to sign in</Link>
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
                <label className="form-label" htmlFor="email">Email Address</label>
                <input id="email" type="email" className="form-input" value={email}
                  onChange={e => setEmail(e.target.value)} placeholder="you@example.com" autoComplete="email" />
              </div>
              <div className="form-group">
                <label className="form-label" htmlFor="displayName">Display Name</label>
                <input id="displayName" type="text" className="form-input" value={displayName}
                  onChange={e => setDisplayName(e.target.value)} placeholder="Your name" autoComplete="name" />
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
              <button type="submit" className="btn btn-primary" style={{ width: '100%' }} disabled={isLoading}>
                {isLoading ? 'Creating account…' : 'Create Account'}
              </button>
            </form>
            <p style={{ marginTop: '1.5rem', textAlign: 'center', fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: 0 }}>
              Already have an account? <Link to="/login">Sign in</Link>
            </p>
          </>
        )}
      </div>
    </div>
  );
};

export default Register;
