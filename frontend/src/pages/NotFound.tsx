import React from 'react';
import { Link } from 'react-router-dom';

const NotFound: React.FC = () => {
  return (
    <div style={{ display: 'flex', minHeight: '100vh', alignItems: 'center', justifyContent: 'center', padding: '1rem', textAlign: 'center' }}>
      <div className="glass-panel" style={{ padding: '3rem 2rem', maxWidth: '400px', width: '100%' }}>
        <h1 style={{ fontSize: '4rem', color: 'var(--accent-primary)', marginBottom: '0.5rem' }}>404</h1>
        <h2 style={{ marginBottom: '0.5rem' }}>Page Not Found</h2>
        <p style={{ color: 'var(--text-secondary)', marginBottom: '2rem' }}>
          The page you are looking for doesn't exist or has been moved.
        </p>
        <Link to="/" className="btn btn-primary" style={{ width: '100%' }}>
          Return to Home
        </Link>
      </div>
    </div>
  );
};

export default NotFound;
