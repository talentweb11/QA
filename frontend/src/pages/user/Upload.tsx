import React from 'react';
import StatementUpload from '../../components/StatementUpload';

const Upload: React.FC = () => {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', maxWidth: '640px', margin: '0 auto', width: '100%' }}>
      <div>
        <h1 style={{ fontSize: '1.5rem', marginBottom: '0.25rem' }}>Upload Statement</h1>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
          Import transactions from a bank statement. We accept CSV exports.
        </p>
      </div>
      <div className="glass-panel" style={{ padding: '1.5rem' }}>
        <StatementUpload />
      </div>
    </div>
  );
};

export default Upload;
