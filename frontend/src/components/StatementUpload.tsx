import React, { useRef, useState } from 'react';
import { UploadCloud, CheckCircle, AlertTriangle, Tag } from 'lucide-react';
import { api } from '../lib/api';
import type { CategoryType, UnknownCategory, UploadResponse, ImportResponse } from '../types';

// Client-side pre-checks. The backend re-validates size (MAX_UPLOAD_SIZE_MB) and
// MIME magic bytes authoritatively — these just give fast, friendly feedback.
const MAX_SIZE_MB = 10;
const ACCEPTED_EXTENSIONS = ['.csv'];

interface StatementUploadProps {
  // Called once transactions are actually imported, so parents (e.g. the
  // dashboard) can refetch. Fires on the immediate-import path and after confirm.
  onImported?: () => void;
}

type Step = 'pick' | 'categorize' | 'confirm' | 'done';
type Msg = { type: 'success' | 'error' | 'warning'; text: string };

// A missing category the user is resolving — type is editable (starts at suggestion).
interface PendingCategory {
  name: string;
  type: CategoryType;
}

const StatementUpload: React.FC<StatementUploadProps> = ({ onImported }) => {
  const inputRef = useRef<HTMLInputElement>(null);
  const [step, setStep] = useState<Step>('pick');
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<Msg | null>(null);

  // Carried between phases when the upload needs categories created first.
  const [statementId, setStatementId] = useState<string | null>(null);
  const [pending, setPending] = useState<PendingCategory[]>([]);
  const [totalRows, setTotalRows] = useState(0);

  const reset = () => {
    setStep('pick');
    setFile(null);
    setMsg(null);
    setStatementId(null);
    setPending([]);
    setTotalRows(0);
    if (inputRef.current) inputRef.current.value = '';
  };

  const pickFile = (selected: File | null) => {
    setMsg(null);
    if (!selected) { setFile(null); return; }
    const name = selected.name.toLowerCase();
    if (!ACCEPTED_EXTENSIONS.some(ext => name.endsWith(ext))) {
      setFile(null);
      setMsg({ type: 'error', text: 'Only CSV files are accepted.' });
      return;
    }
    if (selected.size > MAX_SIZE_MB * 1024 * 1024) {
      setFile(null);
      setMsg({ type: 'error', text: `File is too large (max ${MAX_SIZE_MB} MB).` });
      return;
    }
    setFile(selected);
  };

  // --- Phase A: upload + analyze ---
  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setMsg(null);
    try {
      const form = new FormData();
      form.append('file', file);
      const res = await api('/api/statements/upload', { method: 'POST', body: form });
      const data = await res.json();

      if (!res.ok) {
        // 413 too large, 415 wrong type, 400 empty/no file, 5xx server.
        setMsg({ type: 'error', text: data.error ?? 'Upload failed.' });
        return;
      }

      const resp = data as UploadResponse;
      if (resp.status === 'PROCESSED') {
        setStep('done');
        setMsg({
          type: 'success',
          text: `Imported ${resp.imported_count ?? 0} transaction${resp.imported_count === 1 ? '' : 's'}`
            + (resp.skipped_count ? `, skipped ${resp.skipped_count}.` : '.'),
        });
        onImported?.();
      } else if (resp.status === 'NEEDS_CATEGORIES') {
        setStatementId(resp.statement_id);
        setTotalRows(resp.total_rows ?? 0);
        setPending((resp.unknown_categories ?? []).map((u: UnknownCategory) => ({
          name: u.name,
          type: u.suggested_type,
        })));
        setStep('categorize');
      } else {
        // FAILED
        setMsg({ type: 'warning', text: 'No transactions could be read from this file. Check the format and try again.' });
      }
    } catch {
      setMsg({ type: 'error', text: 'Connection error. Please try again.' });
    } finally {
      setBusy(false);
    }
  };

  const setPendingType = (name: string, type: CategoryType) =>
    setPending(prev => prev.map(p => (p.name === name ? { ...p, type } : p)));

  // --- Phase B: create the missing categories ---
  const handleCreateCategories = async () => {
    setBusy(true);
    setMsg(null);
    try {
      for (const cat of pending) {
        const res = await api('/api/categories', {
          method: 'POST',
          body: JSON.stringify({ name: cat.name, type: cat.type }),
        });
        // 409 = already exists (idempotent, fine). Anything else is a hard error.
        if (!res.ok && res.status !== 409) {
          const data = await res.json().catch(() => ({}));
          setMsg({ type: 'error', text: data.error ?? `Could not create category "${cat.name}".` });
          return;
        }
      }
      setStep('confirm');
    } catch {
      setMsg({ type: 'error', text: 'Connection error. Please try again.' });
    } finally {
      setBusy(false);
    }
  };

  // --- Phase C: confirm import ---
  const handleConfirmImport = async () => {
    if (!statementId) return;
    setBusy(true);
    setMsg(null);
    try {
      const res = await api(`/api/statements/${statementId}/import`, { method: 'POST' });
      const data = await res.json();

      if (res.status === 400 && Array.isArray(data.unresolved_categories)) {
        // A category still missing — go back and let the user resolve it.
        setPending(data.unresolved_categories.map((name: string) => ({ name, type: 'EXPENSE' as CategoryType })));
        setStep('categorize');
        setMsg({ type: 'error', text: 'Some categories still need to be created.' });
        return;
      }
      if (!res.ok) {
        setMsg({ type: 'error', text: data.error ?? 'Import failed.' });
        return;
      }

      const resp = data as ImportResponse;
      setStep('done');
      setMsg({
        type: 'success',
        text: `Imported ${resp.imported_count} transaction${resp.imported_count === 1 ? '' : 's'}`
          + (resp.skipped_count ? `, skipped ${resp.skipped_count}.` : '.'),
      });
      onImported?.();
    } catch {
      setMsg({ type: 'error', text: 'Connection error. Please try again.' });
    } finally {
      setBusy(false);
    }
  };

  const msgColor = (t: Msg['type']) =>
    t === 'success' ? 'var(--success)' : t === 'warning' ? 'var(--warning, #f59e0b)' : 'var(--danger)';
  const msgBg = (t: Msg['type']) =>
    t === 'success' ? 'rgba(16,185,129,0.1)' : t === 'warning' ? 'rgba(245,158,11,0.1)' : 'rgba(239,68,68,0.1)';

  const banner = msg && (
    <div style={{
      display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.75rem',
      backgroundColor: msgBg(msg.type), color: msgColor(msg.type),
      borderRadius: 'var(--radius-md)', fontSize: '0.875rem',
    }}>
      {msg.type === 'success' ? <CheckCircle size={16} /> : <AlertTriangle size={16} />}
      <span>{msg.text}</span>
    </div>
  );

  // --- Step: choose + upload a file ---
  if (step === 'pick') {
    return (
      <form onSubmit={handleUpload} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        <label
          htmlFor="statement-file"
          onDragOver={e => e.preventDefault()}
          onDrop={e => { e.preventDefault(); pickFile(e.dataTransfer.files?.[0] ?? null); }}
          style={{
            display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.75rem',
            padding: '2rem', border: '2px dashed var(--border-color)', borderRadius: 'var(--radius-md)',
            cursor: 'pointer', textAlign: 'center', color: 'var(--text-secondary)',
          }}
        >
          <UploadCloud size={36} color="var(--accent-primary)" />
          <div>
            <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
              {file ? file.name : 'Click to choose a bank statement'}
            </div>
            <div style={{ fontSize: '0.8rem', marginTop: '0.25rem' }}>
              CSV, up to {MAX_SIZE_MB} MB
            </div>
          </div>
          <input
            id="statement-file"
            ref={inputRef}
            type="file"
            accept=".csv"
            style={{ display: 'none' }}
            onChange={e => pickFile(e.target.files?.[0] ?? null)}
          />
        </label>

        {banner}

        <button type="submit" className="btn btn-primary" disabled={!file || busy} style={{ alignSelf: 'flex-start' }}>
          {busy ? 'Uploading…' : 'Upload statement'}
        </button>
      </form>
    );
  }

  // --- Step: create missing categories ---
  if (step === 'categorize') {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-primary)' }}>
          <Tag size={18} color="var(--accent-primary)" />
          <span style={{ fontWeight: 600 }}>New categories found</span>
        </div>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem', margin: 0 }}>
          This statement uses {pending.length} categor{pending.length === 1 ? 'y' : 'ies'} you don't have yet.
          Choose a type for each, then continue.
        </p>

        {banner}

        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          {pending.map(cat => (
            <div key={cat.name} style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '1rem',
              padding: '0.75rem', backgroundColor: 'var(--bg-tertiary)', borderRadius: 'var(--radius-md)',
            }}>
              <span style={{ fontWeight: 500 }}>{cat.name}</span>
              <div style={{ display: 'flex', gap: '0.375rem' }}>
                {(['EXPENSE', 'INCOME'] as CategoryType[]).map(t => {
                  const active = cat.type === t;
                  return (
                    <button
                      key={t}
                      type="button"
                      onClick={() => setPendingType(cat.name, t)}
                      style={{
                        padding: '0.375rem 0.75rem', borderRadius: 'var(--radius-sm)', cursor: 'pointer',
                        fontSize: '0.8rem', fontWeight: 600, fontFamily: 'var(--font-family)',
                        border: `1px solid ${active ? 'var(--accent-primary)' : 'var(--border-color)'}`,
                        background: active ? 'var(--accent-primary)' : 'transparent',
                        color: active ? 'white' : 'var(--text-secondary)',
                      }}
                    >
                      {t === 'EXPENSE' ? 'Expense' : 'Income'}
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>

        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <button type="button" className="btn btn-primary" disabled={busy} onClick={handleCreateCategories}>
            {busy ? 'Creating…' : 'Create categories'}
          </button>
          <button type="button" onClick={reset} disabled={busy}
            style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontFamily: 'var(--font-family)' }}>
            Cancel
          </button>
        </div>
      </div>
    );
  }

  // --- Step: confirm import ---
  if (step === 'confirm') {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-primary)' }}>
          <CheckCircle size={18} color="var(--success)" />
          <span style={{ fontWeight: 600 }}>Categories ready</span>
        </div>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem', margin: 0 }}>
          Import {totalRows} transaction{totalRows === 1 ? '' : 's'} from this statement now?
        </p>

        {banner}

        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <button type="button" className="btn btn-primary" disabled={busy} onClick={handleConfirmImport}>
            {busy ? 'Importing…' : 'Confirm & import'}
          </button>
          <button type="button" onClick={() => { setStep('categorize'); setMsg(null); }} disabled={busy}
            style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontFamily: 'var(--font-family)' }}>
            Back
          </button>
        </div>
      </div>
    );
  }

  // --- Step: done ---
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
      {banner}
      <button type="button" className="btn btn-primary" onClick={reset} style={{ alignSelf: 'flex-start' }}>
        Upload another
      </button>
    </div>
  );
};

export default StatementUpload;
