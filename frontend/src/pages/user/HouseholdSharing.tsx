import React, { useEffect, useState } from 'react';
import { UserPlus, Trash2, ShieldAlert, CheckCircle, Users, Clock } from 'lucide-react';
import { api } from '../../lib/api';
import type { HouseholdShare } from '../../types';

const HouseholdSharing: React.FC = () => {
  const [shares, setShares] = useState<HouseholdShare[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [email, setEmail] = useState('');
  const [inviting, setInviting] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [banner, setBanner] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Initial load — inlined so no setState runs synchronously in the effect.
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const res = await api('/api/consents/household');
        const data = await res.json();
        if (!active) return;
        if (!res.ok) { setError(data.error ?? 'Failed to load shares.'); return; }
        setShares(data.shares);
      } catch {
        if (active) setError('Connection error.');
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => { active = false; };
  }, []);

  const reload = async () => {
    try {
      const res = await api('/api/consents/household');
      const data = await res.json();
      if (res.ok) setShares(data.shares);
    } catch { /* keep existing list on a transient error */ }
  };

  const invite = async (e: React.FormEvent) => {
    e.preventDefault();
    const target = email.trim().toLowerCase();
    if (!target) return;
    setInviting(true); setBanner(null);
    try {
      const res = await api('/api/consents/household/invite', {
        method: 'POST', body: JSON.stringify({ grantee_email: target }),
      });
      const data = await res.json();
      if (!res.ok) { setBanner({ type: 'error', text: data.error ?? 'Failed to send invite.' }); return; }
      setEmail('');
      setBanner({
        type: 'success',
        text: data.status === 'INVITED'
          ? `Invitation sent to ${target}. They'll get an email to create their account.`
          : `Summary access shared with ${target}.`,
      });
      await reload();
    } catch {
      setBanner({ type: 'error', text: 'Connection error.' });
    } finally {
      setInviting(false);
    }
  };

  const revoke = async (share: HouseholdShare) => {
    const who = share.grantee_display_name ?? share.grantee_email ?? 'this member';
    if (!window.confirm(`Revoke ${who}'s access to your financial summary?`)) return;
    setBusyId(share.id); setBanner(null);
    try {
      const res = await api(`/api/consents/household/${share.id}`, { method: 'DELETE' });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setBanner({ type: 'error', text: data.error ?? 'Failed to revoke.' });
        return;
      }
      setShares(prev => prev.filter(s => s.id !== share.id));
      setBanner({ type: 'success', text: 'Access revoked.' });
    } catch {
      setBanner({ type: 'error', text: 'Connection error.' });
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', maxWidth: '640px' }}>
      <div>
        <h1 style={{ fontSize: '1.5rem', marginBottom: '0.5rem' }}>Household Sharing</h1>
        <p style={{ color: 'var(--text-secondary)' }}>
          Invite a household member to see a read-only view of your spending summary. They only
          ever see aggregated totals — never individual transactions — and you can revoke access
          at any time.
        </p>
      </div>

      {banner && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.75rem 1rem',
          backgroundColor: banner.type === 'success' ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)',
          color: banner.type === 'success' ? 'var(--success)' : 'var(--danger)',
          borderRadius: 'var(--radius-md)', fontSize: '0.875rem',
        }}>
          {banner.type === 'success' ? <CheckCircle size={16} /> : <ShieldAlert size={16} />}
          <span>{banner.text}</span>
        </div>
      )}

      <div className="glass-panel" style={{ padding: '1.5rem' }}>
        <h3 style={{ marginBottom: '1rem' }}>Invite a household member</h3>
        <form onSubmit={invite} style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <div className="form-group" style={{ flex: 1, minWidth: '220px', margin: 0 }}>
            <label className="form-label" htmlFor="granteeEmail">Their email address</label>
            <input
              id="granteeEmail"
              type="email"
              className="form-input"
              placeholder="member@example.com"
              value={email}
              onChange={e => setEmail(e.target.value)}
              autoComplete="off"
            />
          </div>
          <button type="submit" className="btn btn-primary" disabled={inviting || !email.trim()}
            style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
            <UserPlus size={18} /> {inviting ? 'Sending…' : 'Invite'}
          </button>
        </form>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.8rem', marginTop: '0.75rem' }}>
          If they don't have an account yet, they'll receive an email link to create one. If they
          already have an account, access is shared immediately.
        </p>
      </div>

      <div className="glass-panel" style={{ padding: '1.5rem' }}>
        <h3 style={{ marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Users size={18} /> People with access
        </h3>

        {loading ? (
          <p style={{ color: 'var(--text-muted)' }}>Loading…</p>
        ) : error ? (
          <p style={{ color: 'var(--danger)' }}>{error}</p>
        ) : shares.length === 0 ? (
          <p style={{ color: 'var(--text-muted)' }}>You haven't invited anyone yet.</p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {shares.map(share => {
              const pending = share.grantee_status !== 'ACTIVE';
              return (
                <div key={share.id} style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem',
                  padding: '0.75rem 1rem', backgroundColor: 'var(--bg-tertiary)', borderRadius: 'var(--radius-md)',
                }}>
                  <div>
                    <div style={{ fontWeight: 500, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      {pending ? share.grantee_email : (share.grantee_display_name ?? share.grantee_email)}
                      {pending ? (
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem', fontSize: '0.7rem', fontWeight: 600, color: 'var(--warning, #b45309)', backgroundColor: 'rgba(245,158,11,0.15)', padding: '0.1rem 0.45rem', borderRadius: '999px' }}>
                          <Clock size={11} /> Pending
                        </span>
                      ) : (
                        <span style={{ fontSize: '0.7rem', fontWeight: 600, color: 'var(--success)', backgroundColor: 'rgba(16,185,129,0.15)', padding: '0.1rem 0.45rem', borderRadius: '999px' }}>
                          Active
                        </span>
                      )}
                    </div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                      {pending ? 'Awaiting sign-up' : share.grantee_email} · invited {new Date(share.created_at).toLocaleDateString()}
                    </div>
                  </div>
                  <button className="btn" disabled={busyId === share.id} title="Revoke access"
                    style={{ display: 'flex', gap: '0.4rem', alignItems: 'center', padding: '0.35rem 0.75rem', fontSize: '0.8rem', border: '1px solid var(--danger)', color: 'var(--danger)', background: 'transparent' }}
                    onClick={() => revoke(share)}>
                    <Trash2 size={16} /> {busyId === share.id ? 'Revoking…' : 'Revoke'}
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};

export default HouseholdSharing;
