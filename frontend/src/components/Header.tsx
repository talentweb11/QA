import React from 'react';
import { useAuth } from '../context/AuthContext';
import { Menu, LogOut } from 'lucide-react';
import type { UserRole } from '../types';

interface HeaderProps {
  onMenuClick: () => void;
}

const Header: React.FC<HeaderProps> = ({ onMenuClick }) => {
  const { user, logout } = useAuth();

  const getRoleBadgeColor = (role: UserRole) => {
    switch (role) {
      case 'ADMIN': return 'badge-danger';
      case 'ADVISOR': return 'badge-warning';
      case 'INDIVIDUAL': return 'badge-success';
      default: return '';
    }
  };

  return (
    <header style={{ 
      display: 'flex', 
      alignItems: 'center', 
      justifyContent: 'space-between', 
      padding: '1rem 1.5rem',
      backgroundColor: 'var(--bg-secondary)',
      borderBottom: '1px solid var(--border-color)',
      position: 'sticky',
      top: 0,
      zIndex: 10
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
        <button 
          onClick={onMenuClick}
          className="btn" 
          style={{ padding: '0.5rem', backgroundColor: 'transparent', color: 'var(--text-primary)' }}
        >
          <Menu size={24} />
        </button>
        <h2 style={{ fontSize: '1.25rem', margin: 0, display: 'none' }}>
          Finance Tracker
        </h2>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '1.5rem' }}>
        {user && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <div style={{ textAlign: 'right', display: 'none' }}>
              <div style={{ fontWeight: 600, fontSize: '0.875rem' }}>{user.display_name}</div>
              <div style={{ display: 'flex', gap: '0.25rem', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                {user.roles.map(r => (
                  <span key={r} className={`badge ${getRoleBadgeColor(r)}`}>{r}</span>
                ))}
              </div>
            </div>
            <div style={{ 
              width: '40px', 
              height: '40px', 
              borderRadius: '50%', 
              backgroundColor: 'var(--bg-tertiary)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontWeight: 'bold',
              color: 'var(--text-primary)'
            }}>
              {user.display_name.charAt(0).toUpperCase()}
            </div>
          </div>
        )}
        <button 
          onClick={logout} 
          className="btn" 
          style={{ padding: '0.5rem', color: 'var(--text-secondary)', backgroundColor: 'transparent' }}
          title="Logout"
        >
          <LogOut size={20} />
        </button>
      </div>
    </header>
  );
};

export default Header;
