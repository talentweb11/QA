import React from 'react';
import type { LucideIcon } from 'lucide-react';

interface StatCardProps {
  title: string;
  value: string;
  icon: LucideIcon;
  trend?: number;
}

const StatCard: React.FC<StatCardProps> = ({ title, value, icon: Icon, trend }) => {
  return (
    <div className="glass-panel" style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <h3 style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', margin: 0, fontWeight: 500 }}>
          {title}
        </h3>
        <div style={{ padding: '0.5rem', backgroundColor: 'var(--bg-tertiary)', borderRadius: 'var(--radius-md)' }}>
          <Icon size={20} color="var(--accent-primary)" />
        </div>
      </div>
      
      <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.75rem' }}>
        <div style={{ fontSize: '1.875rem', fontWeight: 700, color: 'var(--text-primary)' }}>
          {value}
        </div>
        
        {trend !== undefined && (
          <div style={{ 
            display: 'flex', 
            alignItems: 'center', 
            fontSize: '0.875rem', 
            fontWeight: 500,
            color: trend >= 0 ? 'var(--success)' : 'var(--danger)' 
          }}>
            {trend >= 0 ? '▲' : '▼'} {Math.abs(trend)}%
          </div>
        )}
      </div>
    </div>
  );
};

export default StatCard;
