import React, { useEffect, useState } from 'react';
import { Home, PieChart, TrendingUp } from 'lucide-react';
import { api } from '../../lib/api';
import type { HouseholdGrantorSummary } from '../../types';

const money = (v: string) => {
  const n = Number(v);
  return Number.isNaN(n) ? v : `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
};

const HouseholdSummary: React.FC = () => {
  const [grantors, setGrantors] = useState<HouseholdGrantorSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const res = await api('/api/household/summary');
        const data = await res.json();
        if (!active) return;
        if (!res.ok) { setError(data.error ?? 'Failed to load summaries.'); return; }
        setGrantors(data.grantors);
      } catch {
        if (active) setError('Connection error.');
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => { active = false; };
  }, []);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <div>
        <h1 style={{ fontSize: '1.5rem', marginBottom: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Home size={22} /> Shared With Me
        </h1>
        <p style={{ color: 'var(--text-secondary)' }}>
          Aggregated spending summaries that household members have chosen to share with you.
          You can see totals only — never their individual transactions.
        </p>
      </div>

      {loading ? (
        <p style={{ color: 'var(--text-muted)' }}>Loading…</p>
      ) : error ? (
        <p style={{ color: 'var(--danger)' }}>{error}</p>
      ) : grantors.length === 0 ? (
        <div className="glass-panel" style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
          No household members have shared their summary with you yet.
        </div>
      ) : (
        grantors.map(g => (
          <div key={g.grantor_id} className="glass-panel" style={{ padding: '1.5rem' }}>
            <h3 style={{ marginBottom: '1.25rem' }}>{g.grantor_display_name ?? 'Household member'}</h3>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1.5rem' }}>
              {/* Spending by category */}
              <div>
                <h4 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem', color: 'var(--text-secondary)' }}>
                  <PieChart size={16} /> Spending by category
                </h4>
                {g.spending_by_category.length === 0 ? (
                  <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem' }}>No spending recorded.</p>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                    {g.spending_by_category.map(c => (
                      <div key={c.category} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.9rem' }}>
                        <span style={{ color: 'var(--text-secondary)' }}>{c.category}</span>
                        <span style={{ fontWeight: 500 }}>{money(c.total)}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Monthly trend */}
              <div>
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
                      {g.monthly_trend.map(t => (
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
          </div>
        ))
      )}
    </div>
  );
};

export default HouseholdSummary;
