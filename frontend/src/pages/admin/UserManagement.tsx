import React, { useEffect, useMemo, useState } from 'react';
import { Search, Trash2, ShieldAlert, CheckCircle, RefreshCw } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { api } from '../../lib/api';
import type { UserRole } from '../../types';

interface AdminUser {
  id: string;
  email: string;
  display_name: string;
  roles: UserRole[];
  status: string;
  created_at: string;
}

const ALL_ROLES: UserRole[] = ['INDIVIDUAL', 'HOUSEHOLD', 'ADVISOR', 'ADMIN'];

const roleLabel: Record<UserRole, string> = {
  INDIVIDUAL: 'Individual',
  HOUSEHOLD: 'Household',
  ADVISOR: 'Advisor',
  ADMIN: 'Admin',
};

const sameRoles = (a: UserRole[], b: UserRole[]) =>
  a.length === b.length && [...a].sort().join(',') === [...b].sort().join(',');

const statusColor = (status: string) =>
  status === 'ACTIVE' ? 'var(--success)' : status === 'SUSPENDED' ? 'var(--danger)' : 'var(--text-muted)';

const UserManagement: React.FC = () => {
  const { user: currentUser } = useAuth();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [banner, setBanner] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [roleDrafts, setRoleDrafts] = useState<Record<string, UserRole[]>>({});

  const loadUsers = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api('/api/admin/users');
      const data = await res.json();
      if (!res.ok) { setError(data.error ?? 'Failed to load users.'); return; }
      setUsers(data);
      setRoleDrafts({});
    } catch {
      setError('Connection error.');
    } finally {
      setLoading(false);
    }
  };

  // Initial load. Inlined (rather than calling loadUsers) so no setState runs
  // synchronously inside the effect — loading already starts true.
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const res = await api('/api/admin/users');
        const data = await res.json();
        if (!active) return;
        if (!res.ok) { setError(data.error ?? 'Failed to load users.'); return; }
        setUsers(data);
        setRoleDrafts({});
      } catch {
        if (active) setError('Connection error.');
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => { active = false; };
  }, []);

  const filteredUsers = useMemo(
    () => users.filter(u =>
      u.display_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      u.email.toLowerCase().includes(searchTerm.toLowerCase()),
    ),
    [users, searchTerm],
  );

  const draftFor = (u: AdminUser): UserRole[] => roleDrafts[u.id] ?? u.roles;

  const toggleRole = (u: AdminUser, role: UserRole) => {
    const current = draftFor(u);
    const next = current.includes(role) ? current.filter(r => r !== role) : [...current, role];
    setRoleDrafts(prev => ({ ...prev, [u.id]: next }));
  };

  const replaceUser = (updated: AdminUser) =>
    setUsers(prev => prev.map(u => (u.id === updated.id ? updated : u)));

  const clearDraft = (id: string) =>
    setRoleDrafts(prev => { const next = { ...prev }; delete next[id]; return next; });

  const saveRoles = async (u: AdminUser) => {
    const draft = draftFor(u);
    if (draft.length === 0) { setBanner({ type: 'error', text: 'A user must keep at least one role.' }); return; }
    setBusyId(u.id); setBanner(null);
    try {
      const res = await api(`/api/admin/users/${u.id}/roles`, {
        method: 'PATCH', body: JSON.stringify({ roles: draft }),
      });
      const data = await res.json();
      if (!res.ok) { setBanner({ type: 'error', text: data.error ?? 'Failed to update roles.' }); return; }
      replaceUser(data);
      clearDraft(u.id);
      setBanner({ type: 'success', text: `Roles updated for ${u.display_name}.` });
    } catch {
      setBanner({ type: 'error', text: 'Connection error.' });
    } finally {
      setBusyId(null);
    }
  };

  const setStatus = async (u: AdminUser, status: 'ACTIVE' | 'SUSPENDED') => {
    setBusyId(u.id); setBanner(null);
    try {
      const res = await api(`/api/admin/users/${u.id}/status`, {
        method: 'PATCH', body: JSON.stringify({ status }),
      });
      const data = await res.json();
      if (!res.ok) { setBanner({ type: 'error', text: data.error ?? 'Failed to update status.' }); return; }
      replaceUser(data);
      setBanner({ type: 'success', text: `${u.display_name} ${status === 'ACTIVE' ? 'activated' : 'suspended'}.` });
    } catch {
      setBanner({ type: 'error', text: 'Connection error.' });
    } finally {
      setBusyId(null);
    }
  };

  const deleteUser = async (u: AdminUser) => {
    if (!window.confirm(`Permanently delete ${u.display_name} (${u.email})? This cannot be undone.`)) return;
    setBusyId(u.id); setBanner(null);
    try {
      const res = await api(`/api/admin/users/${u.id}`, { method: 'DELETE' });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setBanner({ type: 'error', text: data.error ?? 'Failed to delete user.' });
        return;
      }
      setUsers(prev => prev.filter(x => x.id !== u.id));
      clearDraft(u.id);
      setBanner({ type: 'success', text: `${u.display_name} deleted.` });
    } catch {
      setBanner({ type: 'error', text: 'Connection error.' });
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h1 style={{ fontSize: '1.5rem', marginBottom: '0.5rem' }}>User Management</h1>
          <p style={{ color: 'var(--text-secondary)' }}>
            Manage platform users, roles, and access. Financial data is inaccessible from this view.
          </p>
        </div>
        <button className="btn" onClick={loadUsers} disabled={loading}
          style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', color: 'var(--text-secondary)' }}>
          <RefreshCw size={16} /> Refresh
        </button>
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
        <div style={{ marginBottom: '1.5rem', position: 'relative', maxWidth: '400px' }}>
          <Search size={18} color="var(--text-muted)" style={{ position: 'absolute', left: '1rem', top: '50%', transform: 'translateY(-50%)' }} />
          <input
            type="text"
            className="form-input"
            placeholder="Search users by name or email..."
            style={{ paddingLeft: '2.5rem' }}
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>

        {loading ? (
          <p style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>Loading users…</p>
        ) : error ? (
          <p style={{ padding: '2rem', textAlign: 'center', color: 'var(--danger)' }}>{error}</p>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border-color)', color: 'var(--text-secondary)' }}>
                  <th style={{ padding: '0.75rem 1rem' }}>Name</th>
                  <th style={{ padding: '0.75rem 1rem' }}>Email</th>
                  <th style={{ padding: '0.75rem 1rem' }}>Roles</th>
                  <th style={{ padding: '0.75rem 1rem' }}>Status</th>
                  <th style={{ padding: '0.75rem 1rem' }}>Joined</th>
                  <th style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredUsers.map((u) => {
                  const isSelf = currentUser?.id === u.id;
                  const draft = draftFor(u);
                  const dirty = !!roleDrafts[u.id] && !sameRoles(draft, u.roles);
                  const busy = busyId === u.id;
                  const disabled = isSelf || busy;

                  return (
                    <tr key={u.id} style={{ borderBottom: '1px solid var(--border-color)' }}>
                      <td style={{ padding: '1rem', fontWeight: 500 }}>
                        {u.display_name}
                        {isSelf && <span style={{ marginLeft: '0.4rem', fontSize: '0.75rem', color: 'var(--text-muted)' }}>(you)</span>}
                      </td>
                      <td style={{ padding: '1rem', color: 'var(--text-secondary)' }}>{u.email}</td>
                      <td style={{ padding: '1rem' }}>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem 0.9rem', alignItems: 'center' }}>
                          {ALL_ROLES.map(role => (
                            <label key={role} style={{
                              display: 'flex', alignItems: 'center', gap: '0.3rem',
                              fontSize: '0.8rem', color: 'var(--text-secondary)',
                              cursor: disabled ? 'not-allowed' : 'pointer', opacity: disabled ? 0.6 : 1,
                            }}>
                              <input
                                type="checkbox"
                                checked={draft.includes(role)}
                                disabled={disabled}
                                onChange={() => toggleRole(u, role)}
                              />
                              {roleLabel[role]}
                            </label>
                          ))}
                          {dirty && (
                            <button className="btn btn-primary" disabled={busy}
                              style={{ padding: '0.2rem 0.6rem', fontSize: '0.75rem' }}
                              onClick={() => saveRoles(u)}>
                              {busy ? 'Saving…' : 'Save'}
                            </button>
                          )}
                        </div>
                      </td>
                      <td style={{ padding: '1rem' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                          <div style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: statusColor(u.status) }} />
                          <span style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', textTransform: 'capitalize' }}>
                            {u.status.toLowerCase()}
                          </span>
                        </div>
                      </td>
                      <td style={{ padding: '1rem', color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
                        {new Date(u.created_at).toLocaleDateString()}
                      </td>
                      <td style={{ padding: '1rem' }}>
                        <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end', alignItems: 'center' }}>
                          {u.status === 'ACTIVE' ? (
                            <button className="btn" disabled={disabled}
                              style={{ padding: '0.25rem 0.6rem', fontSize: '0.8rem', border: '1px solid var(--danger)', color: 'var(--danger)', background: 'transparent' }}
                              onClick={() => setStatus(u, 'SUSPENDED')}>
                              Suspend
                            </button>
                          ) : (
                            <button className="btn" disabled={disabled}
                              style={{ padding: '0.25rem 0.6rem', fontSize: '0.8rem', border: '1px solid var(--success)', color: 'var(--success)', background: 'transparent' }}
                              onClick={() => setStatus(u, 'ACTIVE')}>
                              Activate
                            </button>
                          )}
                          <button className="btn" disabled={disabled} title={isSelf ? 'You cannot delete your own account' : 'Delete user'}
                            style={{ padding: '0.25rem', background: 'transparent', color: disabled ? 'var(--text-muted)' : 'var(--danger)' }}
                            onClick={() => deleteUser(u)}>
                            <Trash2 size={18} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}

                {filteredUsers.length === 0 && (
                  <tr>
                    <td colSpan={6} style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                      No users found matching your search.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default UserManagement;
