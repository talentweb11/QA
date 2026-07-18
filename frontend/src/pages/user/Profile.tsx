import React, { useState } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import { User, Lock, Shield, ShieldOff, ShieldAlert, CheckCircle } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { api } from '../../lib/api';

type Section = 'profile' | 'password' | 'mfa';
type MfaStep = 'idle' | 'setup_pending' | 'disabling';

const Profile: React.FC = () => {
  const { user, refreshUser } = useAuth();
  const [activeSection, setActiveSection] = useState<Section>('profile');

  // Profile section
  const [displayName, setDisplayName] = useState(user?.display_name ?? '');
  const [profileMsg, setProfileMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [profileLoading, setProfileLoading] = useState(false);

  // Password section
  const [currentPw, setCurrentPw] = useState('');
  const [newPw, setNewPw] = useState('');
  const [confirmPw, setConfirmPw] = useState('');
  const [pwMsg, setPwMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [pwLoading, setPwLoading] = useState(false);

  // MFA section
  const [mfaStep, setMfaStep] = useState<MfaStep>('idle');
  const [qrUri, setQrUri] = useState('');
  const [totpCode, setTotpCode] = useState('');
  const [mfaMsg, setMfaMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [mfaLoading, setMfaLoading] = useState(false);

  if (!user) return null;

  // --- Profile ---
  const handleProfileSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setProfileMsg(null);
    if (!displayName.trim()) { setProfileMsg({ type: 'error', text: 'Display name cannot be empty.' }); return; }
    setProfileLoading(true);
    try {
      const res = await api('/api/users/me', { method: 'PATCH', body: JSON.stringify({ display_name: displayName.trim() }) });
      const data = await res.json();
      if (!res.ok) { setProfileMsg({ type: 'error', text: data.error ?? 'Failed to update profile.' }); return; }
      await refreshUser();
      setProfileMsg({ type: 'success', text: 'Display name updated.' });
    } catch {
      setProfileMsg({ type: 'error', text: 'Connection error.' });
    } finally {
      setProfileLoading(false);
    }
  };

  // --- Password ---
  const handlePasswordChange = async (e: React.FormEvent) => {
    e.preventDefault();
    setPwMsg(null);
    if (!currentPw || !newPw || !confirmPw) { setPwMsg({ type: 'error', text: 'All fields are required.' }); return; }
    if (newPw !== confirmPw) { setPwMsg({ type: 'error', text: 'New passwords do not match.' }); return; }
    setPwLoading(true);
    try {
      const res = await api('/api/users/me/password', { method: 'PATCH', body: JSON.stringify({ current_password: currentPw, new_password: newPw }) });
      const data = await res.json();
      if (!res.ok) { setPwMsg({ type: 'error', text: data.error ?? 'Failed to change password.' }); return; }
      setCurrentPw(''); setNewPw(''); setConfirmPw('');
      setPwMsg({ type: 'success', text: 'Password changed. Other sessions have been signed out.' });
    } catch {
      setPwMsg({ type: 'error', text: 'Connection error.' });
    } finally {
      setPwLoading(false);
    }
  };

  // --- MFA ---
  const handleMfaSetup = async () => {
    setMfaMsg(null);
    setMfaLoading(true);
    try {
      const res = await api('/api/auth/mfa/setup', { method: 'POST' });
      const data = await res.json();
      if (!res.ok) { setMfaMsg({ type: 'error', text: data.error ?? 'Setup failed.' }); return; }
      setQrUri(data.qr_uri);
      setMfaStep('setup_pending');
    } catch {
      setMfaMsg({ type: 'error', text: 'Connection error.' });
    } finally {
      setMfaLoading(false);
    }
  };

  const handleMfaEnable = async (e: React.FormEvent) => {
    e.preventDefault();
    setMfaMsg(null);
    setMfaLoading(true);
    try {
      const res = await api('/api/auth/mfa/enable', { method: 'POST', body: JSON.stringify({ totp_code: totpCode }) });
      const data = await res.json();
      if (!res.ok) { setMfaMsg({ type: 'error', text: data.error ?? 'Invalid code.' }); return; }
      await refreshUser();
      setMfaStep('idle'); setTotpCode(''); setQrUri('');
      setMfaMsg({ type: 'success', text: 'MFA enabled.' });
    } catch {
      setMfaMsg({ type: 'error', text: 'Connection error.' });
    } finally {
      setMfaLoading(false);
    }
  };

  const handleMfaDisable = async (e: React.FormEvent) => {
    e.preventDefault();
    setMfaMsg(null);
    setMfaLoading(true);
    try {
      const res = await api('/api/auth/mfa/disable', { method: 'POST', body: JSON.stringify({ totp_code: totpCode }) });
      const data = await res.json();
      if (!res.ok) { setMfaMsg({ type: 'error', text: data.error ?? 'Invalid code.' }); return; }
      await refreshUser();
      setMfaStep('idle'); setTotpCode('');
      setMfaMsg({ type: 'success', text: 'MFA disabled.' });
    } catch {
      setMfaMsg({ type: 'error', text: 'Connection error.' });
    } finally {
      setMfaLoading(false);
    }
  };

  const navStyle = (s: Section): React.CSSProperties => ({
    display: 'flex', alignItems: 'center', gap: '0.5rem',
    padding: '0.625rem 1rem', borderRadius: 'var(--radius-md)',
    cursor: 'pointer', border: 'none', width: '100%', textAlign: 'left',
    fontFamily: 'var(--font-family)', fontSize: '0.9rem', fontWeight: 500,
    background: activeSection === s ? 'var(--accent-light)' : 'transparent',
    color: activeSection === s ? 'var(--accent-primary)' : 'var(--text-secondary)',
    transition: 'all 0.15s',
  });

  const msgBox = (msg: { type: 'success' | 'error'; text: string }) => (
    <div style={{
      display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.75rem',
      backgroundColor: msg.type === 'success' ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)',
      color: msg.type === 'success' ? 'var(--success)' : 'var(--danger)',
      borderRadius: 'var(--radius-md)', marginBottom: '1rem', fontSize: '0.875rem',
    }}>
      {msg.type === 'success' ? <CheckCircle size={16} /> : <ShieldAlert size={16} />}
      <span>{msg.text}</span>
    </div>
  );

  return (
    <div>
      <h1 style={{ marginBottom: '1.5rem' }}>Account Settings</h1>
      <div style={{ display: 'flex', gap: '1.5rem', alignItems: 'flex-start', flexWrap: 'wrap' }}>

        {/* Sidebar nav */}
        <div className="glass-panel" style={{ padding: '0.75rem', minWidth: '180px', flexShrink: 0 }}>
          <button style={navStyle('profile')} onClick={() => setActiveSection('profile')}>
            <User size={16} /> Profile
          </button>
          <button style={navStyle('password')} onClick={() => setActiveSection('password')}>
            <Lock size={16} /> Password
          </button>
          <button style={navStyle('mfa')} onClick={() => setActiveSection('mfa')}>
            <Shield size={16} /> Two-Factor Auth
          </button>
        </div>

        {/* Content */}
        <div className="glass-panel" style={{ padding: '1.5rem', flex: 1, minWidth: '280px' }}>

          {activeSection === 'profile' && (
            <>
              <h3 style={{ marginBottom: '1rem' }}>Profile</h3>
              <div style={{ marginBottom: '1rem', padding: '0.75rem', backgroundColor: 'var(--bg-tertiary)', borderRadius: 'var(--radius-md)', fontSize: '0.875rem' }}>
                <span style={{ color: 'var(--text-muted)' }}>Email: </span>
                <span>{user.email}</span>
                <span style={{ marginLeft: '1rem', color: 'var(--text-muted)' }}>Roles: </span>
                <span>{user.roles.join(', ')}</span>
              </div>
              {profileMsg && msgBox(profileMsg)}
              <form onSubmit={handleProfileSave}>
                <div className="form-group" style={{ marginBottom: '1.5rem' }}>
                  <label className="form-label" htmlFor="displayName">Display Name</label>
                  <input id="displayName" type="text" className="form-input" value={displayName}
                    onChange={e => setDisplayName(e.target.value)} maxLength={100} />
                </div>
                <button type="submit" className="btn btn-primary" disabled={profileLoading}>
                  {profileLoading ? 'Saving…' : 'Save Changes'}
                </button>
              </form>
            </>
          )}

          {activeSection === 'password' && (
            <>
              <h3 style={{ marginBottom: '1rem' }}>Change Password</h3>
              {pwMsg && msgBox(pwMsg)}
              <form onSubmit={handlePasswordChange}>
                <div className="form-group">
                  <label className="form-label" htmlFor="currentPw">Current Password</label>
                  <input id="currentPw" type="password" className="form-input" value={currentPw}
                    onChange={e => setCurrentPw(e.target.value)} autoComplete="current-password" />
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="newPw">New Password</label>
                  <input id="newPw" type="password" className="form-input" value={newPw}
                    onChange={e => setNewPw(e.target.value)} autoComplete="new-password" />
                </div>
                <div className="form-group" style={{ marginBottom: '1.5rem' }}>
                  <label className="form-label" htmlFor="confirmPw">Confirm New Password</label>
                  <input id="confirmPw" type="password" className="form-input" value={confirmPw}
                    onChange={e => setConfirmPw(e.target.value)} autoComplete="new-password" />
                </div>
                <button type="submit" className="btn btn-primary" disabled={pwLoading}>
                  {pwLoading ? 'Updating…' : 'Change Password'}
                </button>
              </form>
            </>
          )}

          {activeSection === 'mfa' && (
            <>
              <h3 style={{ marginBottom: '0.5rem' }}>Two-Factor Authentication</h3>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem', marginBottom: '1rem' }}>
                Use an authenticator app (Google Authenticator, Authy, etc.) for an extra layer of security.
              </p>

              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.5rem' }}>
                {user.mfa_enabled
                  ? <><Shield size={18} color="var(--success)" /><span style={{ color: 'var(--success)', fontWeight: 500 }}>Enabled</span></>
                  : <><ShieldOff size={18} color="var(--text-muted)" /><span style={{ color: 'var(--text-muted)' }}>Not enabled</span></>
                }
              </div>

              {mfaMsg && msgBox(mfaMsg)}

              {!user.mfa_enabled && mfaStep === 'idle' && (
                <button className="btn btn-primary" onClick={handleMfaSetup} disabled={mfaLoading}>
                  {mfaLoading ? 'Setting up…' : 'Enable MFA'}
                </button>
              )}

              {mfaStep === 'setup_pending' && (
                <>
                  <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', marginBottom: '0.75rem' }}>
                    Scan the QR code with your authenticator app (Google Authenticator, Authy, etc.):
                  </p>
                  <div style={{ display: 'inline-block', padding: '0.75rem', backgroundColor: '#ffffff', borderRadius: 'var(--radius-md)', marginBottom: '1.25rem' }}>
                    <QRCodeSVG value={qrUri} size={180} />
                  </div>
                  <form onSubmit={handleMfaEnable}>
                    <div className="form-group" style={{ marginBottom: '1rem' }}>
                      <label className="form-label" htmlFor="mfaCode">Enter the 6-digit code from your app to confirm</label>
                      <input id="mfaCode" type="text" inputMode="numeric" className="form-input" value={totpCode}
                        onChange={e => setTotpCode(e.target.value.replace(/\D/g, '').slice(0, 6))} maxLength={6} placeholder="000000" />
                    </div>
                    <div style={{ display: 'flex', gap: '0.75rem' }}>
                      <button type="submit" className="btn btn-primary" disabled={mfaLoading || totpCode.length !== 6}>
                        {mfaLoading ? 'Verifying…' : 'Confirm & Enable'}
                      </button>
                      <button type="button" style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontFamily: 'var(--font-family)' }}
                        onClick={() => { setMfaStep('idle'); setQrUri(''); setTotpCode(''); }}>
                        Cancel
                      </button>
                    </div>
                  </form>
                </>
              )}

              {user.mfa_enabled && mfaStep === 'idle' && (
                <button style={{ background: 'none', border: '1px solid var(--danger)', color: 'var(--danger)', padding: '0.5rem 1rem', borderRadius: 'var(--radius-md)', cursor: 'pointer', fontFamily: 'var(--font-family)', fontWeight: 500 }}
                  onClick={() => { setMfaStep('disabling'); setMfaMsg(null); }}>
                  Disable MFA
                </button>
              )}

              {user.mfa_enabled && mfaStep === 'disabling' && (
                <form onSubmit={handleMfaDisable}>
                  <div className="form-group" style={{ marginBottom: '1rem' }}>
                    <label className="form-label" htmlFor="disableCode">Enter your authenticator code to confirm</label>
                    <input id="disableCode" type="text" inputMode="numeric" className="form-input" value={totpCode}
                      onChange={e => setTotpCode(e.target.value.replace(/\D/g, '').slice(0, 6))} maxLength={6} placeholder="000000" />
                  </div>
                  <div style={{ display: 'flex', gap: '0.75rem' }}>
                    <button type="submit" style={{ background: 'var(--danger)', border: 'none', color: 'white', padding: '0.5rem 1rem', borderRadius: 'var(--radius-md)', cursor: 'pointer', fontFamily: 'var(--font-family)', fontWeight: 500 }}
                      disabled={mfaLoading || totpCode.length !== 6}>
                      {mfaLoading ? 'Disabling…' : 'Confirm Disable'}
                    </button>
                    <button type="button" style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontFamily: 'var(--font-family)' }}
                      onClick={() => { setMfaStep('idle'); setTotpCode(''); }}>
                      Cancel
                    </button>
                  </div>
                </form>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default Profile;
