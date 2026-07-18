import React, { useEffect, useState } from 'react';
import { Users, PieChart, TrendingUp, Store, ChevronRight } from 'lucide-react';
import { api } from '../../lib/api';
import type { AdvisorClient, AdvisorClientAnalytics } from '../../types';

const money = (v: string) => {
  const n = Number(v);
  return Number.isNaN(n) ? v : `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
};

const ClientList: React.FC = () => {
  const [clients, setClients] = useState<AdvisorClient[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<AdvisorClientAnalytics | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const res = await api('/api/advisor/clients');
        const data = await res.json();
        if (!active) return;
        if (!res.ok) { setError(data.error ?? 'Failed to load clients.'); return; }
        setClients(data.clients);
      } catch {
        if (active) setError('Connection error.');
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => { active = false; };
  }, []);

  const viewClient = async (client: AdvisorClient) => {
    setSelectedId(client.grantor_id);
    setDetail(null);
    setDetailError(null);
    setDetailLoading(true);
    try {
      const res = await api(`/api/advisor/clients/${client.grantor_id}/analytics`);
      const data = await res.json();
      if (!res.ok) { setDetailError(data.error ?? 'Access to this client is no longer available.'); return; }
      setDetail(data);
    } catch {
      setDetailError('Connection error.');
    } finally {
      setDetailLoading(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <div>
        <h1 style={{ fontSize: '1.5rem', marginBottom: '0.5rem' }}>My Clients</h1>
        <p style={{ color: 'var(--text-secondary)' }}>
          Individuals who have granted you advisor access. Select a client to review their spending
          — access is consent-gated and expires automatically.
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(220px, 300px) 1fr', gap: '1.5rem', alignItems: 'start' }}>
        {/* Client list */}
        <div className="glass-panel" style={{ padding: '1rem' }}>
          <h3 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem', fontSize: '1rem' }}>
            <Users size={18} /> Clients
          </h3>
          {loading ? (
            <p style={{ color: 'var(--text-muted)' }}>Loading…</p>
          ) : error ? (
            <p style={{ color: 'var(--danger)' }}>{error}</p>
          ) : clients.length === 0 ? (
            <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem' }}>No clients have granted you access yet.</p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
              {clients.map(c => {
                const selected = c.grantor_id === selectedId;
                return (
                  <button key={c.grantor_id} onClick={() => viewClient(c)}
                    style={{
                      display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.5rem',
                      padding: '0.6rem 0.75rem', borderRadius: 'var(--radius-md)', cursor: 'pointer',
                      border: 'none', textAlign: 'left', width: '100%', fontFamily: 'var(--font-family)',
                      fontSize: '0.9rem', fontWeight: 500,
                      background: selected ? 'var(--accent-light)' : 'transparent',
                      color: selected ? 'var(--accent-primary)' : 'var(--text-secondary)',
                    }}>
                    <span>{c.display_name ?? 'Client'}</span>
                    <ChevronRight size={16} />
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Selected client's analytics */}
        <div className="glass-panel" style={{ padding: '1.5rem', minHeight: '200px' }}>
          {!selectedId ? (
            <p style={{ color: 'var(--text-muted)' }}>Select a client to view their financial summary.</p>
          ) : detailLoading ? (
            <p style={{ color: 'var(--text-muted)' }}>Loading…</p>
          ) : detailError ? (
            <p style={{ color: 'var(--danger)' }}>{detailError}</p>
          ) : detail ? (
            <>
              <h3 style={{ marginBottom: '1.25rem' }}>{detail.display_name ?? 'Client'}</h3>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '1.5rem' }}>
                {/* Spending by category */}
                <div>
                  <h4 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem', color: 'var(--text-secondary)' }}>
                    <PieChart size={16} /> Spending by category
                  </h4>
                  {detail.analytics.spending_by_category.length === 0 ? (
                    <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem' }}>No spending recorded.</p>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                      {detail.analytics.spending_by_category.map(c => (
                        <div key={c.category} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.9rem' }}>
                          <span style={{ color: 'var(--text-secondary)' }}>{c.category}</span>
                          <span style={{ fontWeight: 500 }}>{money(c.total)}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Top merchants */}
                <div>
                  <h4 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem', color: 'var(--text-secondary)' }}>
                    <Store size={16} /> Top merchants
                  </h4>
                  {detail.analytics.top_merchants.length === 0 ? (
                    <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem' }}>No merchants recorded.</p>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                      {detail.analytics.top_merchants.map(m => (
                        <div key={m.merchant} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.9rem' }}>
                          <span style={{ color: 'var(--text-secondary)' }}>{m.merchant}</span>
                          <span style={{ fontWeight: 500 }}>{money(m.total)}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Monthly trend */}
                <div style={{ gridColumn: '1 / -1' }}>
                  <h4 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem', color: 'var(--text-secondary)' }}>
                    <TrendingUp size={16} /> Monthly trend
                  </h4>
                  <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                      <thead>
                        <tr style={{ color: 'var(--text-muted)', textAlign: 'left' }}>
                          <th style={{ padding: '0.3rem 0.5rem' }}>Month</th>
                          <th style={{ padding: '0.3rem 0.5rem', textAlign: 'right' }}>Income</th>
                          <th style={{ padding: '0.3rem 0.5rem', textAlign: 'right' }}>Spend</th>
                        </tr>
                      </thead>
                      <tbody>
                        {detail.analytics.monthly_trend.map(t => (
                          <tr key={t.month} style={{ borderTop: '1px solid var(--border-color)' }}>
                            <td style={{ padding: '0.3rem 0.5rem' }}>{t.month}</td>
                            <td style={{ padding: '0.3rem 0.5rem', textAlign: 'right', color: 'var(--success)' }}>{money(t.income)}</td>
                            <td style={{ padding: '0.3rem 0.5rem', textAlign: 'right', color: 'var(--danger)' }}>{money(t.spend)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
};

export default ClientList;
