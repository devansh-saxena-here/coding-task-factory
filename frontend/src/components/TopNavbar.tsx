import React from 'react';
import { useLocation } from 'react-router-dom';
import { Menu, User } from 'lucide-react';
import { useProject } from '../context/ProjectContext';

interface TopNavbarProps {
  onToggleSidebar?: () => void;
}

export const TopNavbar: React.FC<TopNavbarProps> = ({ onToggleSidebar }) => {
  const location = useLocation();
  const { backendHealth, checkBackendHealth } = useProject();

  const getPageTitle = (path: string): string => {
    switch (path) {
      case '/':
        return 'Dashboard';
      case '/new-project':
        return 'New Project & Repository Ingestion';
      case '/analysis':
        return 'Repository Codebase Intelligence';
      case '/task-generator':
        return 'Contextual Task Generator';
      case '/solution':
        return 'Reference Solution Engine';
      case '/test-suite':
        return 'Automated Test Suite';
      case '/validation':
        return 'Evaluation & Validation Engine';
      case '/export':
        return 'Harbor Package Exporter';
      case '/settings':
        return 'Platform Settings';
      default:
        return 'Coding Task Factory';
    }
  };

  return (
    <header
      style={{
        height: 'var(--topbar-height)',
        backgroundColor: 'var(--bg-card)',
        borderBottom: '1px solid var(--border-default)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 24px',
        position: 'sticky',
        top: 0,
        zIndex: 40,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        {onToggleSidebar && (
          <button
            onClick={onToggleSidebar}
            className="btn btn-subtle"
            style={{ padding: '6px' }}
            title="Toggle navigation"
          >
            <Menu size={16} />
          </button>
        )}

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
            Coding Task Factory
          </span>
          <span style={{ color: 'var(--border-strong)', fontSize: '11px' }}>/</span>
          <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>
            {getPageTitle(location.pathname)}
          </span>
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        {/* Backend Connectivity Status Indicator */}
        <div
          onClick={() => checkBackendHealth()}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            padding: '4px 10px',
            borderRadius: 'var(--radius-full)',
            backgroundColor: 'var(--bg-muted)',
            border: '1px solid var(--border-default)',
            fontSize: '11px',
            cursor: 'pointer',
          }}
          title="Click to probe backend status"
        >
          <div
            style={{
              width: '7px',
              height: '7px',
              borderRadius: 'var(--radius-full)',
              backgroundColor: backendHealth === 'online' ? 'var(--success)' : backendHealth === 'checking' ? 'var(--warning)' : 'var(--danger)',
              boxShadow: backendHealth === 'online' ? '0 0 0 2px rgba(16, 185, 129, 0.2)' : 'none',
            }}
          />
          <span style={{ color: 'var(--text-secondary)', fontWeight: 500 }}>
            {backendHealth === 'online' ? 'Backend Online' : backendHealth === 'checking' ? 'Checking...' : 'Backend Offline'}
          </span>
        </div>

        {/* Profile Placeholder */}
        <div
          style={{
            width: '28px',
            height: '28px',
            borderRadius: 'var(--radius-full)',
            backgroundColor: 'var(--bg-muted)',
            border: '1px solid var(--border-default)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--text-secondary)',
          }}
          title="User Profile"
        >
          <User size={15} />
        </div>
      </div>
    </header>
  );
};
