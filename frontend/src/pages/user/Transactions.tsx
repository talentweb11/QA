import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Plus, Pencil, Trash2, Download, X } from 'lucide-react';
import { api } from '../../lib/api';
import type { CategoryRecord, CategoryType, TransactionRecord } from '../../types';

const today = () => new Date().toISOString().slice(0, 10);

const formatSGD = (amount: number) =>
  new Intl.NumberFormat('en-SG', { style: 'currency', currency: 'SGD' }).format(amount);

interface FormState {
  transaction_date: string;
  amount: string;
  category_id: string;
  merchant_name: string;
  description: string;
}

const emptyForm = (categoryId: string): FormState => ({
  transaction_date: today(),
  amount: '',
  category_id: categoryId,
  merchant_name: '',
  description: '',
});

const Transactions: React.FC = () => {
  const [transactions, setTransactions] = useState<TransactionRecord[]>([]);
  const [categories, setCategories] = useState<CategoryRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters — from/to hit the backend; category/type filter client-side.
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [typeFilter, setTypeFilter] = useState<'' | CategoryType>('');

  // Add/edit modal.
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<TransactionRecord | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm(''));
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Delete confirmation.
  const [deleting, setDeleting] = useState<TransactionRecord | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  const [exporting, setExporting] = useState(false);

  // Bulk clear.
  const [deleteAllOpen, setDeleteAllOpen] = useState(false);
  const [deleteAllBusy, setDeleteAllBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (from) params.set('from', from);
      if (to) params.set('to', to);
      const qs = params.toString();
      const [txRes, catRes] = await Promise.all([
        api(`/api/transactions${qs ? `?${qs}` : ''}`),
        api('/api/categories'),
      ]);
      if (!txRes.ok) {
        const body = await txRes.json().catch(() => ({}));
        setError(body.error ?? 'Could not load transactions.');
        return;
      }
      setError(null);
      setTransactions(await txRes.json());
      if (catRes.ok) setCategories(await catRes.json());
    } catch {
      setError('Connection error. Please try again.');
    } finally {
      setLoading(false);
    }
  }, [from, to]);

  // Scheduled as a microtask (not a direct call) so no setState runs synchronously
  // inside the effect body (react-hooks/set-state-in-effect).
  useEffect(() => { void Promise.resolve().then(load); }, [load]);

  const visible = useMemo(
    () => transactions.filter(t =>
      (!categoryFilter || t.category_id === categoryFilter) &&
      (!typeFilter || t.type === typeFilter)),
    [transactions, categoryFilter, typeFilter],
  );

  const openAdd = () => {
    setEditing(null);
    setForm(emptyForm(categories[0]?.id ?? ''));
    setFormError(null);
    setModalOpen(true);
  };

  const openEdit = (t: TransactionRecord) => {
    setEditing(t);
    setForm({
      transaction_date: t.transaction_date,
      amount: t.amount,
      category_id: t.category_id,
      merchant_name: t.merchant_name ?? '',
      description: t.description ?? '',
    });
    setFormError(null);
    setModalOpen(true);
  };

  const closeModal = () => { setModalOpen(false); setEditing(null); };

  const saveForm = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    if (!form.transaction_date) { setFormError('Date is required.'); return; }
    if (!form.category_id) { setFormError('Category is required.'); return; }
    const amountNum = Number(form.amount);
    if (!form.amount || !Number.isFinite(amountNum) || amountNum <= 0) {
      setFormError('Amount must be a positive number.'); return;
    }

    const payload = {
      transaction_date: form.transaction_date,
      amount: form.amount.trim(),          // backend requires amount as a string
      category_id: form.category_id,
      merchant_name: form.merchant_name.trim() || null,
      description: form.description.trim() || null,
    };

    setSaving(true);
    try {
      const res = editing
        ? await api(`/api/transactions/${editing.id}`, { method: 'PATCH', body: JSON.stringify(payload) })
        : await api('/api/transactions', { method: 'POST', body: JSON.stringify(payload) });
      const data = await res.json();
      if (!res.ok) { setFormError(data.error ?? 'Could not save transaction.'); return; }
      closeModal();
      await load();
    } catch {
      setFormError('Connection error. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  const confirmDelete = async () => {
    if (!deleting) return;
    setDeleteBusy(true);
    try {
      const res = await api(`/api/transactions/${deleting.id}`, { method: 'DELETE' });
      if (!res.ok && res.status !== 204) {
        const data = await res.json().catch(() => ({}));
        setError(data.error ?? 'Could not delete transaction.');
        return;
      }
      setDeleting(null);
      await load();
    } catch {
      setError('Connection error. Please try again.');
    } finally {
      setDeleteBusy(false);
    }
  };

  const confirmDeleteAll = async () => {
    setDeleteAllBusy(true);
    try {
      const res = await api('/api/transactions', { method: 'DELETE' });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setError(data.error ?? 'Could not clear transactions.');
        return;
      }
      setDeleteAllOpen(false);
      await load();
    } catch {
      setError('Connection error. Please try again.');
    } finally {
      setDeleteAllBusy(false);
    }
  };

  const exportCsv = async () => {
    setExporting(true);
    try {
      const res = await api('/api/transactions/export');
      if (!res.ok) { setError('Export failed.'); return; }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'transactions.csv';
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      setError('Connection error. Please try again.');
    } finally {
      setExporting(false);
    }
  };

  const inputStyle: React.CSSProperties = { minWidth: 0 };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <h1 style={{ fontSize: '1.5rem', margin: 0 }}>Transactions</h1>
        <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
          <button onClick={() => { setError(null); setDeleteAllOpen(true); }} disabled={transactions.length === 0}
            style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', border: '1px solid var(--danger)', background: 'transparent', color: 'var(--danger)', padding: '0.5rem 1rem', borderRadius: 'var(--radius-md)', cursor: transactions.length === 0 ? 'not-allowed' : 'pointer', opacity: transactions.length === 0 ? 0.5 : 1, fontFamily: 'var(--font-family)', fontWeight: 500 }}>
            <Trash2 size={16} /> Delete all
          </button>
          <button className="btn" onClick={exportCsv} disabled={exporting}
            style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', border: '1px solid var(--border-color)', background: 'transparent', color: 'var(--text-primary)', padding: '0.5rem 1rem', borderRadius: 'var(--radius-md)', cursor: 'pointer', fontFamily: 'var(--font-family)', fontWeight: 500 }}>
            <Download size={16} /> {exporting ? 'Exporting…' : 'Export CSV'}
          </button>
          <button className="btn btn-primary" onClick={openAdd}
            style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Plus size={16} /> Add transaction
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="glass-panel" style={{ padding: '1rem 1.5rem', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '1rem', alignItems: 'end' }}>
        <div className="form-group" style={{ margin: 0 }}>
          <label className="form-label" htmlFor="from">From</label>
          <input id="from" type="date" className="form-input" style={inputStyle} value={from} onChange={e => setFrom(e.target.value)} />
        </div>
        <div className="form-group" style={{ margin: 0 }}>
          <label className="form-label" htmlFor="to">To</label>
          <input id="to" type="date" className="form-input" style={inputStyle} value={to} onChange={e => setTo(e.target.value)} />
        </div>
        <div className="form-group" style={{ margin: 0 }}>
          <label className="form-label" htmlFor="catFilter">Category</label>
          <select id="catFilter" className="form-input" style={inputStyle} value={categoryFilter} onChange={e => setCategoryFilter(e.target.value)}>
            <option value="">All categories</option>
            {categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
        <div className="form-group" style={{ margin: 0 }}>
          <label className="form-label" htmlFor="typeFilter">Type</label>
          <select id="typeFilter" className="form-input" style={inputStyle} value={typeFilter} onChange={e => setTypeFilter(e.target.value as '' | CategoryType)}>
            <option value="">All types</option>
            <option value="EXPENSE">Expense</option>
            <option value="INCOME">Income</option>
          </select>
        </div>
      </div>

      {error && (
        <div style={{ padding: '0.75rem', backgroundColor: 'rgba(239,68,68,0.1)', color: 'var(--danger)', borderRadius: 'var(--radius-md)', fontSize: '0.875rem' }}>
          {error}
        </div>
      )}

      {/* Table */}
      <div className="glass-panel" style={{ padding: '1.5rem' }}>
        {loading ? (
          <p style={{ color: 'var(--text-secondary)', textAlign: 'center', padding: '2rem 0' }}>Loading…</p>
        ) : visible.length === 0 ? (
          <p style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '2rem 0' }}>
            No transactions. Add one or upload a statement.
          </p>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border-color)', color: 'var(--text-secondary)' }}>
                  <th style={{ padding: '0.75rem 0' }}>Date</th>
                  <th style={{ padding: '0.75rem 0' }}>Description</th>
                  <th style={{ padding: '0.75rem 0' }}>Merchant</th>
                  <th style={{ padding: '0.75rem 0' }}>Category</th>
                  <th style={{ padding: '0.75rem 0', textAlign: 'right' }}>Amount</th>
                  <th style={{ padding: '0.75rem 0', textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {visible.map(t => (
                  <tr key={t.id} style={{ borderBottom: '1px solid var(--border-color)' }}>
                    <td style={{ padding: '0.875rem 0', color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>{t.transaction_date}</td>
                    <td style={{ padding: '0.875rem 0', fontWeight: 500 }}>{t.description || '—'}</td>
                    <td style={{ padding: '0.875rem 0', color: 'var(--text-secondary)' }}>{t.merchant_name || '—'}</td>
                    <td style={{ padding: '0.875rem 0' }}>
                      <span style={{ padding: '0.25rem 0.5rem', backgroundColor: 'var(--bg-tertiary)', borderRadius: 'var(--radius-sm)', fontSize: '0.75rem' }}>
                        {t.category}
                      </span>
                    </td>
                    <td style={{ padding: '0.875rem 0', textAlign: 'right', fontWeight: 600, whiteSpace: 'nowrap', color: t.type === 'INCOME' ? 'var(--success)' : 'var(--text-primary)' }}>
                      {t.type === 'INCOME' ? '+' : '-'}{formatSGD(Number(t.amount))}
                    </td>
                    <td style={{ padding: '0.875rem 0', textAlign: 'right', whiteSpace: 'nowrap' }}>
                      <button aria-label="Edit" onClick={() => openEdit(t)}
                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-secondary)', padding: '0.25rem' }}>
                        <Pencil size={16} />
                      </button>
                      <button aria-label="Delete" onClick={() => setDeleting(t)}
                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--danger)', padding: '0.25rem' }}>
                        <Trash2 size={16} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Add / edit modal */}
      {modalOpen && (
        <div onClick={closeModal} style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 60, padding: '1rem' }}>
          <div className="glass-panel" onClick={e => e.stopPropagation()} style={{ padding: '1.5rem', width: '100%', maxWidth: '440px', maxHeight: '90vh', overflowY: 'auto' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <h3 style={{ margin: 0 }}>{editing ? 'Edit transaction' : 'Add transaction'}</h3>
              <button aria-label="Close" onClick={closeModal} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}>
                <X size={18} />
              </button>
            </div>

            {formError && (
              <div style={{ padding: '0.75rem', backgroundColor: 'rgba(239,68,68,0.1)', color: 'var(--danger)', borderRadius: 'var(--radius-md)', fontSize: '0.875rem', marginBottom: '1rem' }}>
                {formError}
              </div>
            )}

            <form onSubmit={saveForm}>
              <div className="form-group">
                <label className="form-label" htmlFor="fDate">Date</label>
                <input id="fDate" type="date" className="form-input" value={form.transaction_date}
                  onChange={e => setForm({ ...form, transaction_date: e.target.value })} />
              </div>
              <div className="form-group">
                <label className="form-label" htmlFor="fAmount">Amount (SGD)</label>
                <input id="fAmount" type="number" step="0.01" min="0" inputMode="decimal" className="form-input" value={form.amount}
                  onChange={e => setForm({ ...form, amount: e.target.value })} placeholder="0.00" />
              </div>
              <div className="form-group">
                <label className="form-label" htmlFor="fCategory">Category</label>
                <select id="fCategory" className="form-input" value={form.category_id}
                  onChange={e => setForm({ ...form, category_id: e.target.value })}>
                  <option value="" disabled>Select a category</option>
                  {categories.map(c => (
                    <option key={c.id} value={c.id}>{c.name} · {c.type === 'INCOME' ? 'Income' : 'Expense'}</option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label className="form-label" htmlFor="fMerchant">Merchant (optional)</label>
                <input id="fMerchant" type="text" className="form-input" maxLength={255} value={form.merchant_name}
                  onChange={e => setForm({ ...form, merchant_name: e.target.value })} />
              </div>
              <div className="form-group" style={{ marginBottom: '1.5rem' }}>
                <label className="form-label" htmlFor="fDesc">Description (optional)</label>
                <input id="fDesc" type="text" className="form-input" value={form.description}
                  onChange={e => setForm({ ...form, description: e.target.value })} />
              </div>
              <div style={{ display: 'flex', gap: '0.75rem' }}>
                <button type="submit" className="btn btn-primary" disabled={saving}>
                  {saving ? 'Saving…' : editing ? 'Save changes' : 'Add transaction'}
                </button>
                <button type="button" onClick={closeModal} disabled={saving}
                  style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontFamily: 'var(--font-family)' }}>
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete confirmation */}
      {deleting && (
        <div onClick={() => setDeleting(null)} style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 60, padding: '1rem' }}>
          <div className="glass-panel" onClick={e => e.stopPropagation()} style={{ padding: '1.5rem', width: '100%', maxWidth: '400px' }}>
            <h3 style={{ marginTop: 0, marginBottom: '0.75rem' }}>Delete transaction?</h3>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '1.5rem' }}>
              {deleting.description || deleting.merchant_name || 'This transaction'} · {formatSGD(Number(deleting.amount))} on {deleting.transaction_date}. This cannot be undone.
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

      {/* Delete-all confirmation */}
      {deleteAllOpen && (
        <div onClick={() => setDeleteAllOpen(false)} style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 60, padding: '1rem' }}>
          <div className="glass-panel" onClick={e => e.stopPropagation()} style={{ padding: '1.5rem', width: '100%', maxWidth: '420px' }}>
            <h3 style={{ marginTop: 0, marginBottom: '0.75rem' }}>Delete all transactions?</h3>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '1.5rem' }}>
              This permanently removes <strong>every</strong> transaction on your account,
              not just the ones shown by the current filter. This cannot be undone.
            </p>
            <div style={{ display: 'flex', gap: '0.75rem' }}>
              <button onClick={confirmDeleteAll} disabled={deleteAllBusy}
                style={{ background: 'var(--danger)', border: 'none', color: 'white', padding: '0.5rem 1rem', borderRadius: 'var(--radius-md)', cursor: 'pointer', fontFamily: 'var(--font-family)', fontWeight: 500 }}>
                {deleteAllBusy ? 'Deleting…' : 'Delete all'}
              </button>
              <button onClick={() => setDeleteAllOpen(false)} disabled={deleteAllBusy}
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

export default Transactions;
