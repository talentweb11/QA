import React, { useCallback, useEffect, useState } from 'react';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell,
} from 'recharts';
import { Wallet, TrendingUp, TrendingDown, Store } from 'lucide-react';
import StatCard from '../../components/StatCard';
import StatementUpload from '../../components/StatementUpload';
import { api } from '../../lib/api';
import type { DashboardData } from '../../types';

const COLORS = ['#10b981', '#f59e0b', '#3b82f6', '#ef4444', '#8b5cf6', '#ec4899'];

const formatSGD = (amount: number) =>
  new Intl.NumberFormat('en-SG', { style: 'currency', currency: 'SGD' }).format(amount);

// "2026-07" -> "Jul '26" for compact axis labels.
const shortMonth = (ym: string): string => {
  const [y, m] = ym.split('-').map(Number);
  const name = new Date(y, (m || 1) - 1, 1).toLocaleString('en-SG', { month: 'short' });
  return `${name} '${String(y).slice(2)}`;
};

const Dashboard: React.FC = () => {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // First statement is `await` so no setState runs synchronously inside the mount
  // effect (satisfies react-hooks/set-state-in-effect). The retry button toggles
  // loading in its own click handler instead.
  const load = useCallback(async () => {
    try {
      const res = await api('/api/dashboard');
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setError(body.error ?? 'Could not load your dashboard.');
        setData(null);
        return;
      }
      setError(null);
      setData(await res.json());
    } catch {
      setError('Connection error. Please try again.');
    } finally {
      setLoading(false);
    }
  }, []);

  // Schedule as a microtask callback (not a direct call) so no setState runs
  // synchronously in the effect body — mirrors AuthContext's mount fetch.
  useEffect(() => { void Promise.resolve().then(load); }, [load]);

  const retry = () => { setLoading(true); setError(null); load(); };

  if (loading) {
    return (
      <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
        Loading your dashboard…
      </div>
    );
  }

  if (error) {
    return (
      <div className="glass-panel" style={{ padding: '2rem', textAlign: 'center' }}>
        <p style={{ color: 'var(--danger)', marginBottom: '1rem' }}>{error}</p>
        <button className="btn btn-primary" onClick={retry}>Retry</button>
      </div>
    );
  }

  if (!data) return null;

  const trend = data.monthly_trend.map(p => ({
    month: shortMonth(p.month),
    income: Number(p.income),
    expense: Number(p.spend),
  }));
  const pie = data.spending_by_category.map(c => ({ name: c.category, value: Number(c.total) }));

  const current = data.monthly_trend.find(p => p.month === data.month);
  const monthIncome = Number(current?.income ?? 0);
  const monthExpense = Number(current?.spend ?? 0);
  const net = monthIncome - monthExpense;

  const hasData =
    data.spending_by_category.length > 0 ||
    data.top_merchants.length > 0 ||
    data.monthly_trend.some(p => Number(p.income) > 0 || Number(p.spend) > 0);

  // First-time / no-data state — invite the user to import a statement (FR-07).
  if (!hasData) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', maxWidth: '640px', margin: '0 auto', width: '100%' }}>
        <div>
          <h1 style={{ fontSize: '1.5rem', marginBottom: '0.25rem' }}>Welcome to FinTrack</h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
            You have no transactions yet. Upload a bank statement to see your spending insights.
          </p>
        </div>
        <div className="glass-panel" style={{ padding: '1.5rem' }}>
          <h3 style={{ marginBottom: '1rem' }}>Import your first statement</h3>
          <StatementUpload onImported={load} />
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <h1 style={{ fontSize: '1.5rem', marginBottom: '0.5rem' }}>Dashboard Overview</h1>

      {/* Stats — this month */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '1.5rem' }}>
        <StatCard title="Income (this month)" value={formatSGD(monthIncome)} icon={TrendingUp} />
        <StatCard title="Spending (this month)" value={formatSGD(monthExpense)} icon={TrendingDown} />
        <StatCard title="Net (this month)" value={formatSGD(net)} icon={Wallet} />
        <StatCard title="Top Merchant" value={data.top_merchants[0]?.merchant ?? '—'} icon={Store} />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '1.5rem' }}>
        {/* 6-month trend */}
        <div className="glass-panel" style={{ padding: '1.5rem', gridColumn: 'span 2' }}>
          <h3 style={{ marginBottom: '1.5rem' }}>6-Month Cash Flow</h3>
          <div style={{ height: '300px' }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={trend}>
                <defs>
                  <linearGradient id="colorIncome" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="var(--success)" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="var(--success)" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="colorExpense" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="var(--danger)" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="var(--danger)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" vertical={false} />
                <XAxis dataKey="month" stroke="var(--text-secondary)" />
                <YAxis stroke="var(--text-secondary)" tickFormatter={(value) => `$${value}`} />
                <Tooltip
                  contentStyle={{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border-color)', color: 'var(--text-primary)' }}
                  itemStyle={{ color: 'var(--text-primary)' }}
                  formatter={(value: unknown) => formatSGD(Number(value))}
                />
                <Area type="monotone" dataKey="income" stroke="var(--success)" fillOpacity={1} fill="url(#colorIncome)" name="Income" />
                <Area type="monotone" dataKey="expense" stroke="var(--danger)" fillOpacity={1} fill="url(#colorExpense)" name="Expenses" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Category breakdown — this month */}
        <div className="glass-panel" style={{ padding: '1.5rem' }}>
          <h3 style={{ marginBottom: '1.5rem' }}>Spending by Category</h3>
          {pie.length === 0 ? (
            <div style={{ height: '300px', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)' }}>
              No spending recorded this month.
            </div>
          ) : (
            <div style={{ height: '300px', display: 'flex', justifyContent: 'center' }}>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={pie}
                    cx="50%"
                    cy="50%"
                    innerRadius={55}
                    outerRadius={90}
                    paddingAngle={5}
                    dataKey="value"
                    style={{ fontSize: '0.7rem' }}
                    label={({ name, percent }) => `${name} ${((percent || 0) * 100).toFixed(0)}%`}
                  >
                    {pie.map((_entry, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border-color)' }}
                    formatter={(value: unknown) => formatSGD(Number(value))}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      </div>

      {/* Top merchants — this month */}
      <div className="glass-panel" style={{ padding: '1.5rem' }}>
        <h3 style={{ marginBottom: '1.5rem' }}>Top Merchants (this month)</h3>
        {data.top_merchants.length === 0 ? (
          <p style={{ color: 'var(--text-muted)' }}>No merchant spending recorded this month.</p>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border-color)', color: 'var(--text-secondary)' }}>
                  <th style={{ padding: '0.75rem 0' }}>#</th>
                  <th style={{ padding: '0.75rem 0' }}>Merchant</th>
                  <th style={{ padding: '0.75rem 0', textAlign: 'right' }}>Spent</th>
                </tr>
              </thead>
              <tbody>
                {data.top_merchants.map((m, i) => (
                  <tr key={m.merchant} style={{ borderBottom: '1px solid var(--border-color)' }}>
                    <td style={{ padding: '1rem 0', color: 'var(--text-muted)' }}>{i + 1}</td>
                    <td style={{ padding: '1rem 0', fontWeight: 500 }}>{m.merchant}</td>
                    <td style={{ padding: '1rem 0', textAlign: 'right', fontWeight: 600 }}>{formatSGD(Number(m.total))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default Dashboard;
