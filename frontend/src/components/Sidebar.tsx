import React from 'react';
import { NavLink } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import type { UserRole } from '../types';
import { LayoutDashboard, Users, UserCog, Wallet, UserCircle, UploadCloud, ArrowLeftRight, Tags, Share2, Home, Briefcase, ScrollText } from 'lucide-react';

interface SidebarProps {
  isOpen: boolean;
  setIsOpen: (isOpen: boolean) => void;
}

interface NavItem {
  name: string;
  path: string;
  icon: React.ReactNode;
  allowedRoles: UserRole[];
}

const navItems: NavItem[] = [
  {
    name: 'Profile',
    path: '/profile',
    icon: <UserCircle size={20} />,
    allowedRoles: ['INDIVIDUAL', 'ADVISOR', 'ADMIN', 'HOUSEHOLD'],
  },
  {
    name: 'Dashboard',
    path: '/dashboard',
    icon: <LayoutDashboard size={20} />,
    allowedRoles: ['INDIVIDUAL'],
  },
  {
    name: 'Transactions',
    path: '/transactions',
    icon: <ArrowLeftRight size={20} />,
    allowedRoles: ['INDIVIDUAL'],
  },
  {
    name: 'Categories',
    path: '/categories',
    icon: <Tags size={20} />,
    allowedRoles: ['INDIVIDUAL'],
  },
  {
    name: 'Upload Statement',
    path: '/upload',
    icon: <UploadCloud size={20} />,
    allowedRoles: ['INDIVIDUAL'],
  },
  {
    name: 'Household Sharing',
    path: '/sharing',
    icon: <Share2 size={20} />,
    allowedRoles: ['INDIVIDUAL'],
  },
  {
    name: 'Advisor Access',
    path: '/advisor-access',
    icon: <Briefcase size={20} />,
    allowedRoles: ['INDIVIDUAL'],
  },
  {
    name: 'Shared With Me',
    path: '/household',
    icon: <Home size={20} />,
    allowedRoles: ['HOUSEHOLD'],
  },
  {
    name: 'Client List',
    path: '/advisor/clients',
    icon: <Users size={20} />,
    allowedRoles: ['ADVISOR'],
  },
  {
    name: 'User Management',
    path: '/admin/users',
    icon: <UserCog size={20} />,
    allowedRoles: ['ADMIN'],
  },
  {
    name: 'Audit Logs',
    path: '/admin/audit-logs',
    icon: <ScrollText size={20} />,
    allowedRoles: ['ADMIN'],
  },
];

const Sidebar: React.FC<SidebarProps> = ({ isOpen, setIsOpen }) => {
  const { user } = useAuth();

  if (!user) return null;

  // Filter links based on role
  const permittedLinks = navItems.filter(item => item.allowedRoles.some(r => user.roles.includes(r)));

  return (
    <>
      {/* Mobile overlay */}
      {isOpen && (
        <div 
          onClick={() => setIsOpen(false)}
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(0,0,0,0.5)',
            zIndex: 40,
          }}
        />
      )}

      {/* Sidebar */}
      <aside style={{
        position: 'fixed',
        top: 0,
        bottom: 0,
        left: 0,
        width: '256px',
        backgroundColor: 'var(--bg-secondary)',
        borderRight: '1px solid var(--border-color)',
        zIndex: 50,
        transform: isOpen ? 'translateX(0)' : 'translateX(-100%)',
        transition: 'transform 0.3s ease',
        display: 'flex',
        flexDirection: 'column'
      }}>
        <div style={{ padding: '1.5rem', display: 'flex', alignItems: 'center', gap: '0.75rem', borderBottom: '1px solid var(--border-color)' }}>
          <Wallet color="var(--accent-primary)" size={28} />
          <h1 style={{ fontSize: '1.25rem', margin: 0, color: 'var(--text-primary)' }}>Finance Tracker</h1>
        </div>

        <nav style={{ padding: '1rem', flex: 1 }}>
          <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {permittedLinks.map((item) => (
              <li key={item.path}>
                <NavLink
                  to={item.path}
                  onClick={() => setIsOpen(false)}
                  style={({ isActive }) => ({
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.75rem',
                    padding: '0.75rem 1rem',
                    borderRadius: 'var(--radius-md)',
                    color: isActive ? 'white' : 'var(--text-secondary)',
                    backgroundColor: isActive ? 'var(--accent-primary)' : 'transparent',
                    fontWeight: isActive ? 600 : 500,
                    textDecoration: 'none',
                    transition: 'all 0.2s'
                  })}
                >
                  {item.icon}
                  <span>{item.name}</span>
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </aside>
    </>
  );
};

export default Sidebar;
