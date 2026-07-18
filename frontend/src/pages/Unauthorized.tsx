import React from 'react';
import { Link } from 'react-router-dom';
import { ShieldX } from 'lucide-react';

const Unauthorized: React.FC = () => {
  return (
    <div style={{ display: 'flex', minHeight: '100vh', alignItems: 'center', justifyContent: 'center', padding: '1rem', textAlign: 'center' }}>
      <div className="glass-panel" style={{ padding: '3rem 2rem', maxWidth: '400px', width: '100%' }}>
        <ShieldX size={48} color="var(--danger)" style={{ marginBottom: '1rem' }} />
        <h2 style={{ marginBottom: '0.5rem' }}>Access Denied</h2>
        <p style={{ color: 'var(--text-secondary)', marginBottom: '2rem' }}>
          You do not have permission to view this page.
        </p>
        <Link to="/" className="btn btn-primary" style={{ width: '100%' }}>
          Return to Home
        </Link>
      </div>
    </div>
  );
};

export default Unauthorized;
