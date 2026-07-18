import React, { useEffect, useState } from 'react';
import { ScrollText, Search, RotateCcw, ChevronLeft, ChevronRight } from 'lucide-react';
import { api } from '../../lib/api';
import type { AuditLogEntry } from '../../types';

const PAGE_SIZE = 50;

const EVENT_SUGGESTIONS = [
  'AUTH_SUCCESS', 'AUTH_FAILURE', 'MFA_FAILURE', 'USER_REGISTERED', 'EMAIL_VERIFIED',
  'CONSENT_GRANTED', 'CONSENT_REVOKED', 'ADMIN_ACTION', 'HOUSEHOLD_SUMMARY_ACCESS',
  'ADVISOR_DATA_ACCESS', 'TRANSACTIONS_CLEARED', 'STATEMENT_UPLOADED', 'STATEMENT_IMPORTED',
  'CATEGORY_CREATED', 'CATEGORY_DELETED',
];

// Timestamps are stored as naive UTC — treat as UTC, then render in local time.
const fmtTime = (ts: string) => new Date(ts.endsWith('Z') ? ts : `${ts}Z`).toLocaleString();
const short = (s: string | null, n = 8) => (s ? (s.length > n ? `${s.slice(0, n)}…` : s) : '—');

interface Filters {
  event_type: string;
  user_id: string;
  outcome: string;
  from_date: string;
  to_date: string;
}

const AuditLogs: React.FC = () => {
  const [items, setItems] = useState<AuditLogEntry[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [eventType, setEventType] = useState('');
  const [userId, setUserId] = useState('');
  const [outcome, setOutcome] = useState('');
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');

  const currentFilters = (): Filters => ({
    event_type: eventType.trim(),
    user_id: userId.trim(),
    outcome,
    from_date: fromDate,
    to_date: toDate,
  });

  const load = async (pageArg: number, filters: Filters = currentFilters()) => {
    setLoading(true); setError(null);
    const params = new URLSearchParams({ page: String(pageArg), page_size: String(PAGE_SIZE) });
    if (filters.event_type) params.set('event_type', filters.event_type);
    if (filters.user_id) params.set('user_id', filters.user_id);
    if (filters.outcome) params.set('outcome', filters.outcome);
    if (filters.from_date) params.set('from_date', filters.from_date);
    if (filters.to_date) params.set('to_date', filters.to_date);
    try {
      const res = await api(`/api/admin/audit-logs?${params.toString()}`);
      const data = await res.json();
      if (!res.ok) { setError(data.error ?? 'Failed to load audit logs.'); return; }
      setItems(data.items); setTotal(data.total); setPage(data.page);
    } catch {
      setError('Connection error.');
    } finally {
      setLoading(false);
    }
  };

  // Initial load — inlined so no setState runs synchronously in the effect.
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const res = await api(`/api/admin/audit-logs?page=1&page_size=${PAGE_SIZE}`);
        const data = await res.json();
        if (!active) return;
        if (!res.ok) { setError(data.error ?? 'Failed to load audit logs.'); return; }
        setItems(data.items); setTotal(data.total); setPage(data.page);
      } catch {
        if (active) setError('Connection error.');
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => { active = false; };
  }, []);

  const applyFilters = (e: React.FormEvent) => { e.preventDefault(); load(1); };

  const resetFilters = () => {
    setEventType(''); setUserId(''); setOutcome(''); setFromDate(''); setToDate('');
    load(1, { event_type: '', user_id: '', outcome: '', from_date: '', to_date: '' });
  };

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const inputStyle: React.CSSProperties = { padding: '0.4rem 0.6rem', fontSize: '0.85rem' };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <div>
        <h1 style={{ fontSize: '1.5rem', marginBottom: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <ScrollText size={22} /> Audit Logs
        </h1>
        <p style={{ color: 'var(--text-secondary)' }}>
          Append-only record of security events. Filter by event type, user, outcome, or date range.
        </p>
      </div>

      {/* Filters */}
      <div className="glass-panel" style={{ padding: '1.25rem' }}>
        <form onSubmit={applyFilters} style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem', alignItems: 'flex-end' }}>
          <div className="form-group" style={{ margin: 0, minWidth: '180px', flex: 1 }}>
            <label className="form-label" htmlFor="f-event">Event type</label>
            <input id="f-event" list="event-suggestions" className="form-input" style={inputStyle}
              placeholder="e.g. AUTH_FAILURE" value={eventType} onChange={e => setEventType(e.target.value)} />
            <datalist id="event-suggestions">
              {EVENT_SUGGESTIONS.map(ev => <option key={ev} value={ev} />)}
            </datalist>
          </div>
          <div className="form-group" style={{ margin: 0, minWidth: '180px', flex: 1 }}>
            <label className="form-label" htmlFor="f-user">User ID</label>
            <input id="f-user" className="form-input" style={inputStyle}
              placeholder="UUID" value={userId} onChange={e => setUserId(e.target.value)} />
          </div>
          <div className="form-group" style={{ margin: 0, minWidth: '130px' }}>
            <label className="form-label" htmlFor="f-outcome">Outcome</label>
            <select id="f-outcome" className="form-input" style={inputStyle}
              value={outcome} onChange={e => setOutcome(e.target.value)}>
              <option value="">All</option>
              <option value="SUCCESS">Success</option>
              <option value="FAILURE">Failure</option>
            </select>
          </div>
          <div className="form-group" style={{ margin: 0, minWidth: '140px' }}>
            <label className="form-label" htmlFor="f-from">From</label>
            <input id="f-from" type="date" className="form-input" style={inputStyle}
              value={fromDate} onChange={e => setFromDate(e.target.value)} />
          </div>
          <div className="form-group" style={{ margin: 0, minWidth: '140px' }}>
            <label className="form-label" htmlFor="f-to">To</label>
            <input id="f-to" type="date" className="form-input" style={inputStyle}
              value={toDate} onChange={e => setToDate(e.target.value)} />
          </div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button type="submit" className="btn btn-primary" disabled={loading}
              style={{ display: 'flex', gap: '0.4rem', alignItems: 'center' }}>
              <Search size={16} /> Apply
            </button>
            <button type="button" className="btn" onClick={resetFilters} disabled={loading}
              style={{ display: 'flex', gap: '0.4rem', alignItems: 'center', color: 'var(--text-secondary)' }}>
              <RotateCcw size={16} /> Reset
            </button>
          </div>
        </form>
      </div>

      {/* Table */}
      <div className="glass-panel" style={{ padding: '1.5rem' }}>
        {loading ? (
          <p style={{ padding: '1rem', textAlign: 'center', color: 'var(--text-muted)' }}>Loading…</p>
        ) : error ? (
          <p style={{ padding: '1rem', textAlign: 'center', color: 'var(--danger)' }}>{error}</p>
        ) : (
          <>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.85rem' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border-color)', color: 'var(--text-secondary)' }}>
                    <th style={{ padding: '0.6rem 0.75rem' }}>Time</th>
                    <th style={{ padding: '0.6rem 0.75rem' }}>Event</th>
                    <th style={{ padding: '0.6rem 0.75rem' }}>Outcome</th>
                    <th style={{ padding: '0.6rem 0.75rem' }}>User</th>
                    <th style={{ padding: '0.6rem 0.75rem' }}>IP</th>
                    <th style={{ padding: '0.6rem 0.75rem' }}>User agent</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map(log => (
                    <tr key={log.id} style={{ borderBottom: '1px solid var(--border-color)' }}>
                      <td style={{ padding: '0.6rem 0.75rem', whiteSpace: 'nowrap' }}>{fmtTime(log.timestamp)}</td>
                      <td style={{ padding: '0.6rem 0.75rem', fontFamily: 'monospace' }}>{log.event_type}</td>
                      <td style={{ padding: '0.6rem 0.75rem' }}>
                        <span style={{
                          fontSize: '0.72rem', fontWeight: 600, padding: '0.1rem 0.45rem', borderRadius: '999px',
                          color: log.outcome === 'SUCCESS' ? 'var(--success)' : 'var(--danger)',
                          backgroundColor: log.outcome === 'SUCCESS' ? 'rgba(16,185,129,0.15)' : 'rgba(239,68,68,0.15)',
                        }}>{log.outcome}</span>
                      </td>
                      <td style={{ padding: '0.6rem 0.75rem', fontFamily: 'monospace' }} title={log.user_id ?? ''}>{short(log.user_id)}</td>
                      <td style={{ padding: '0.6rem 0.75rem' }}>{log.ip_address ?? '—'}</td>
                      <td style={{ padding: '0.6rem 0.75rem', color: 'var(--text-muted)', maxWidth: '260px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={log.user_agent ?? ''}>
                        {log.user_agent ?? '—'}
                      </td>
                    </tr>
                  ))}
                  {items.length === 0 && (
                    <tr>
                      <td colSpan={6} style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                        No audit events match these filters.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '1rem', flexWrap: 'wrap', gap: '0.75rem' }}>
              <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                {total} event{total === 1 ? '' : 's'} · page {page} of {totalPages}
              </span>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <button className="btn" disabled={loading || page <= 1} onClick={() => load(page - 1)}
                  style={{ display: 'flex', gap: '0.3rem', alignItems: 'center' }}>
                  <ChevronLeft size={16} /> Prev
                </button>
                <button className="btn" disabled={loading || page >= totalPages} onClick={() => load(page + 1)}
                  style={{ display: 'flex', gap: '0.3rem', alignItems: 'center' }}>
                  Next <ChevronRight size={16} />
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default AuditLogs;
