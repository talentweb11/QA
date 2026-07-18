import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Plus, Trash2, Tag } from 'lucide-react';
import { api } from '../../lib/api';
import type { CategoryRecord, CategoryType } from '../../types';

const Categories: React.FC = () => {
  const [categories, setCategories] = useState<CategoryRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Add form.
  const [name, setName] = useState('');
  const [type, setType] = useState<CategoryType>('EXPENSE');
  const [adding, setAdding] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  // Duplicate-name popup.
  const [duplicate, setDuplicate] = useState<{ name: string; scope: 'default' | 'own' } | null>(null);

  // Delete confirmation.
  const [deleting, setDeleting] = useState<CategoryRecord | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await api('/api/categories');
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setError(body.error ?? 'Could not load categories.');
        return;
      }
      setError(null);
      setCategories(await res.json());
    } catch {
      setError('Connection error. Please try again.');
    } finally {
      setLoading(false);
    }
  }, []);

  // Scheduled as a microtask (not a direct call) so no setState runs synchronously
  // inside the effect body (react-hooks/set-state-in-effect).
  useEffect(() => { void Promise.resolve().then(load); }, [load]);

  const custom = useMemo(() => categories.filter(c => !c.is_global), [categories]);
  const global = useMemo(() => categories.filter(c => c.is_global), [categories]);

  const addCategory = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    const trimmed = name.trim();
    if (!trimmed) { setFormError('Name is required.'); return; }

    // Case-insensitive duplicate check against defaults AND own categories. The
    // backend only rejects duplicates of your own custom names, so this is what
    // catches a clash with a built-in default category.
    const clash = categories.find(c => c.name.trim().toLowerCase() === trimmed.toLowerCase());
    if (clash) {
      setDuplicate({ name: clash.name, scope: clash.is_global ? 'default' : 'own' });
      return;
    }

    setAdding(true);
    try {
      const res = await api('/api/categories', { method: 'POST', body: JSON.stringify({ name: trimmed, type }) });
      const data = await res.json();
      if (!res.ok) { setFormError(data.error ?? 'Could not create category.'); return; }
      setName('');
      setType('EXPENSE');
      await load();
    } catch {
      setFormError('Connection error. Please try again.');
    } finally {
      setAdding(false);
    }
  };

  const confirmDelete = async () => {
    if (!deleting) return;
    setDeleteBusy(true);
    try {
      const res = await api(`/api/categories/${deleting.id}`, { method: 'DELETE' });
      if (!res.ok && res.status !== 204) {
        const data = await res.json().catch(() => ({}));
        // 409 = still referenced by transactions.
        setError(data.error ?? 'Could not delete category.');
        return;
      }
      setError(null);
      setDeleting(null);
      await load();
    } catch {
      setError('Connection error. Please try again.');
    } finally {
      setDeleteBusy(false);
    }
  };

  const typeBadge = (t: CategoryType) => (
    <span style={{
      padding: '0.125rem 0.5rem', borderRadius: 'var(--radius-sm)', fontSize: '0.7rem', fontWeight: 600,
      color: t === 'INCOME' ? 'var(--success)' : 'var(--danger)',
      backgroundColor: t === 'INCOME' ? 'rgba(16,185,129,0.12)' : 'rgba(239,68,68,0.12)',
    }}>
      {t === 'INCOME' ? 'Income' : 'Expense'}
    </span>
  );

  const chip = (c: CategoryRecord, deletable: boolean) => (
    <div key={c.id} style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.75rem',
      padding: '0.625rem 0.875rem', backgroundColor: 'var(--bg-tertiary)', borderRadius: 'var(--radius-md)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', minWidth: 0 }}>
        <span style={{ fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.name}</span>
        {typeBadge(c.type)}
      </div>
      {deletable && (
        <button aria-label={`Delete ${c.name}`} onClick={() => { setError(null); setDeleting(c); }}
          style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--danger)', padding: '0.125rem', flexShrink: 0 }}>
          <Trash2 size={16} />
        </button>
      )}
    </div>
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <h1 style={{ fontSize: '1.5rem', margin: 0 }}>Categories</h1>

      {/* Add */}
      <div className="glass-panel" style={{ padding: '1.5rem' }}>
        <h3 style={{ marginTop: 0, marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Tag size={18} color="var(--accent-primary)" /> New category
        </h3>
        {formError && (
          <div style={{ padding: '0.75rem', backgroundColor: 'rgba(239,68,68,0.1)', color: 'var(--danger)', borderRadius: 'var(--radius-md)', fontSize: '0.875rem', marginBottom: '1rem' }}>
            {formError}
          </div>
        )}
        <form onSubmit={addCategory} style={{ display: 'flex', gap: '1rem', alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <div className="form-group" style={{ margin: 0, flex: '1 1 200px' }}>
            <label className="form-label" htmlFor="catName">Name</label>
            <input id="catName" type="text" className="form-input" maxLength={100} value={name}
              onChange={e => setName(e.target.value)} placeholder="e.g. Pet Care" />
          </div>
          <div className="form-group" style={{ margin: 0 }}>
            <label className="form-label">Type</label>
            <div style={{ display: 'flex', gap: '0.375rem' }}>
              {(['EXPENSE', 'INCOME'] as CategoryType[]).map(t => {
                const active = type === t;
                return (
                  <button key={t} type="button" onClick={() => setType(t)}
                    style={{
                      padding: '0.5rem 0.875rem', borderRadius: 'var(--radius-md)', cursor: 'pointer',
                      fontSize: '0.85rem', fontWeight: 600, fontFamily: 'var(--font-family)',
                      border: `1px solid ${active ? 'var(--accent-primary)' : 'var(--border-color)'}`,
                      background: active ? 'var(--accent-primary)' : 'transparent',
                      color: active ? 'white' : 'var(--text-secondary)',
                    }}>
                    {t === 'EXPENSE' ? 'Expense' : 'Income'}
                  </button>
                );
              })}
            </div>
          </div>
          <button type="submit" className="btn btn-primary" disabled={adding}
            style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Plus size={16} /> {adding ? 'Adding…' : 'Add category'}
          </button>
        </form>
      </div>

      {error && (
        <div style={{ padding: '0.75rem', backgroundColor: 'rgba(239,68,68,0.1)', color: 'var(--danger)', borderRadius: 'var(--radius-md)', fontSize: '0.875rem' }}>
          {error}
        </div>
      )}

      {loading ? (
        <p style={{ color: 'var(--text-secondary)', textAlign: 'center', padding: '2rem 0' }}>Loading…</p>
      ) : (
        <>
          {/* Custom */}
          <div className="glass-panel" style={{ padding: '1.5rem' }}>
            <h3 style={{ marginTop: 0, marginBottom: '1rem' }}>Your categories</h3>
            {custom.length === 0 ? (
              <p style={{ color: 'var(--text-muted)', margin: 0 }}>You haven't created any custom categories yet.</p>
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: '0.75rem' }}>
                {custom.map(c => chip(c, true))}
              </div>
            )}
          </div>

          {/* Global */}
          <div className="glass-panel" style={{ padding: '1.5rem' }}>
            <h3 style={{ marginTop: 0, marginBottom: '0.25rem' }}>Default categories</h3>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.8rem', marginTop: 0, marginBottom: '1rem' }}>
              Built-in categories shared by everyone. These can't be deleted.
            </p>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: '0.75rem' }}>
              {global.map(c => chip(c, false))}
            </div>
          </div>
        </>
      )}

      {/* Duplicate-name popup */}
      {duplicate && (
        <div onClick={() => setDuplicate(null)} style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 60, padding: '1rem' }}>
          <div className="glass-panel" onClick={e => e.stopPropagation()} style={{ padding: '1.5rem', width: '100%', maxWidth: '400px' }}>
            <h3 style={{ marginTop: 0, marginBottom: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Tag size={18} color="var(--danger)" /> Category already exists
            </h3>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '1.5rem' }}>
              "{duplicate.name}" is already {duplicate.scope === 'default' ? 'a default category' : 'one of your categories'}.
              Pick a different name.
            </p>
            <button onClick={() => setDuplicate(null)} className="btn btn-primary" style={{ alignSelf: 'flex-start' }}>
              OK
            </button>
          </div>
        </div>
      )}

      {/* Delete confirmation */}
      {deleting && (
        <div onClick={() => setDeleting(null)} style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 60, padding: '1rem' }}>
          <div className="glass-panel" onClick={e => e.stopPropagation()} style={{ padding: '1.5rem', width: '100%', maxWidth: '400px' }}>
            <h3 style={{ marginTop: 0, marginBottom: '0.75rem' }}>Delete category?</h3>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '1.5rem' }}>
              Delete "{deleting.name}"? A category still used by transactions can't be removed.
            </p>
            <div style={{ display: 'flex', gap: '0.75rem' }}>
              <button onClick={confirmDelete} disabled={deleteBusy}
                style={{ background: 'var(--danger)', border: 'none', color: 'white', padding: '0.5rem 1rem', borderRadius: 'var(--radius-md)', cursor: 'pointer', fontFamily: 'var(--font-family)', fontWeight: 500 }}>
                {deleteBusy ? 'Deleting…' : 'Delete'}
              </button>
              <button onClick={() => setDeleting(null)} disabled={deleteBusy}
                style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontFamily: 'var(--font-family)' }}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Categories;
