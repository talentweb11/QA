import React, { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { CheckCircle, XCircle, Loader } from 'lucide-react';
import { api } from '../lib/api';

const VerifyEmail: React.FC = () => {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>(token ? 'loading' : 'error');
  const [message, setMessage] = useState(token ? '' : 'No verification token found in the link.');
  const called = useRef(false);
  const navigate = useNavigate();

  useEffect(() => {
    if (called.current || !token) return;
    called.current = true;

    api(`/api/auth/verify-email?token=${encodeURIComponent(token)}`, { skipUnauth: true } as RequestInit & { skipUnauth: boolean })
      .then(async res => {
        const data = await res.json();
        if (res.ok) {
          setStatus('success');
          setMessage(data.message ?? 'Email verified successfully.');
          setTimeout(() => navigate('/login', { replace: true }), 3000);
        } else {
          setStatus('error');
          setMessage(data.error ?? 'This verification link is invalid or has expired.');
        }
      })
      .catch(() => {
        setStatus('error');
        setMessage('Connection error. Please try again.');
      });
  }, [token, navigate]);

  return (
    <div style={{ display: 'flex', minHeight: '100vh', alignItems: 'center', justifyContent: 'center', padding: '1rem' }}>
      <div className="glass-panel" style={{ width: '100%', maxWidth: '400px', padding: '2rem', textAlign: 'center' }}>
        {status === 'loading' && (
          <>
            <Loader size={48} color="var(--accent-primary)" style={{ marginBottom: '1rem', animation: 'spin 1s linear infinite' }} />
            <h2>Verifying your email…</h2>
          </>
        )}
        {status === 'success' && (
          <>
            <CheckCircle size={48} color="var(--success)" style={{ marginBottom: '1rem' }} />
            <h2>Email Verified</h2>
            <p style={{ color: 'var(--text-secondary)', marginTop: '0.5rem' }}>{message}</p>
            <Link to="/login" className="btn btn-primary" style={{ display: 'inline-block', marginTop: '1.5rem' }}>
              Sign In
            </Link>
          </>
        )}
        {status === 'error' && (
          <>
            <XCircle size={48} color="var(--danger)" style={{ marginBottom: '1rem' }} />
            <h2>Verification Failed</h2>
            <p style={{ color: 'var(--text-secondary)', marginTop: '0.5rem' }}>{message}</p>
            <Link to="/login" style={{ display: 'block', marginTop: '1.5rem' }}>Back to sign in</Link>
          </>
        )}
      </div>
    </div>
  );
};

export default VerifyEmail;
