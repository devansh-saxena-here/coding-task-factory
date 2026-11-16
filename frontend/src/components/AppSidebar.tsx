import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  FolderPlus,
  GitBranch,
  Sparkles,
  Code2,
  CheckSquare,
  ShieldCheck,
  Package,
  Settings,
  Layers,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { useProject } from '../context/ProjectContext';

interface AppSidebarProps {
  isCollapsed: boolean;
  onToggleCollapse: () => void;
}

export const AppSidebar: React.FC<AppSidebarProps> = ({
  isCollapsed,
  onToggleCollapse,
}) => {
  const { repoAnalysis, task, solution, testSuite, validationReport } = useProject();

  const navigation = [
    { name: 'Dashboard', path: '/', icon: LayoutDashboard },
    { name: 'New Project', path: '/new-project', icon: FolderPlus },
    {
      name: 'Repository Analysis',
      path: '/analysis',
      icon: GitBranch,
      hasData: Boolean(repoAnalysis),
    },
    {
      name: 'Task Generator',
      path: '/task-generator',
      icon: Sparkles,
      hasData: Boolean(task),
    },
    {
      name: 'Reference Solution',
      path: '/solution',
      icon: Code2,
      hasData: Boolean(solution),
    },
    {
      name: 'Test Suite',
      path: '/test-suite',
      icon: CheckSquare,
      hasData: Boolean(testSuite),
    },
    {
      name: 'Validation',
      path: '/validation',
      icon: ShieldCheck,
      hasData: Boolean(validationReport),
    },
    {
      name: 'Harbor Export',
      path: '/export',
      icon: Package,
    },
    { name: 'Settings', path: '/settings', icon: Settings },
  ];

  return (
    <aside
      style={{
        width: isCollapsed ? 'var(--sidebar-collapsed-width)' : 'var(--sidebar-width)',
        backgroundColor: 'var(--bg-sidebar)',
        borderRight: '1px solid var(--border-default)',
        display: 'flex',
        flexDirection: 'column',
        transition: 'width 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
        flexShrink: 0,
        height: '100vh',
        position: 'sticky',
        top: 0,
        zIndex: 50,
      }}
    >
      {/* Brand Header */}
      <div
        style={{
          height: 'var(--topbar-height)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: isCollapsed ? 'center' : 'space-between',
          padding: isCollapsed ? '0' : '0 16px',
          borderBottom: '1px solid var(--border-default)',
        }}
      >
        {!isCollapsed ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div
              style={{
                width: '28px',
                height: '28px',
                borderRadius: 'var(--radius-md)',
                backgroundColor: 'var(--accent-primary)',
                color: '#ffffff',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: '0 2px 4px rgba(79, 70, 229, 0.3)',
              }}
            >
              <Layers size={16} />
            </div>
            <div>
              <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '-0.01em', lineHeight: 1.2 }}>
                Task Factory
              </div>
              <div style={{ fontSize: '10px', color: 'var(--text-muted)', fontWeight: 500 }}>
                Harbor Evaluator
              </div>
            </div>
          </div>
        ) : (
          <div
            style={{
              width: '28px',
              height: '28px',
              borderRadius: 'var(--radius-md)',
              backgroundColor: 'var(--accent-primary)',
              color: '#ffffff',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Layers size={16} />
          </div>
        )}

        <button
          onClick={onToggleCollapse}
          className="btn btn-subtle"
          style={{ padding: '6px', borderRadius: 'var(--radius-sm)' }}
          title={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {isCollapsed ? <ChevronRight size={15} /> : <ChevronLeft size={15} />}
        </button>
      </div>

      {/* Navigation List */}
      <nav
        style={{
          flex: 1,
          padding: '12px 8px',
          display: 'flex',
          flexDirection: 'column',
          gap: '2px',
          overflowY: 'auto',
        }}
      >
        {navigation.map((item) => {
          const Icon = item.icon;

          return (
            <NavLink
              key={item.path}
              to={item.path}
              style={({ isActive }) => ({
                display: 'flex',
                alignItems: 'center',
                gap: '12px',
                padding: isCollapsed ? '9px 0' : '9px 12px',
                justifyContent: isCollapsed ? 'center' : 'flex-start',
                borderRadius: 'var(--radius-md)',
                fontSize: '13px',
                fontWeight: isActive ? 600 : 500,
                color: isActive ? 'var(--accent-primary)' : 'var(--text-secondary)',
                backgroundColor: isActive ? 'var(--accent-primary-light)' : 'transparent',
                textDecoration: 'none',
                position: 'relative',
                transition: 'all 0.1s ease',
              })}
              title={isCollapsed ? item.name : undefined}
            >
              {({ isActive }) => (
                <>
                  <Icon
                    size={17}
                    style={{
                      color: isActive ? 'var(--accent-primary)' : 'var(--text-secondary)',
                      flexShrink: 0,
                    }}
                  />
                  {!isCollapsed && (
                    <span style={{ flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {item.name}
                    </span>
                  )}
                  {!isCollapsed && item.hasData && (
                    <div
                      style={{
                        width: '6px',
                        height: '6px',
                        borderRadius: 'var(--radius-full)',
                        backgroundColor: 'var(--accent-primary)',
                      }}
                      title="Data available"
                    />
                  )}
                </>
              )}
            </NavLink>
          );
        })}
      </nav>

      {/* Active Project Footer in Sidebar */}
      {!isCollapsed && repoAnalysis && (
        <div
          style={{
            padding: '12px 14px',
            margin: '8px',
            borderRadius: 'var(--radius-md)',
            backgroundColor: 'var(--bg-muted)',
            border: '1px solid var(--border-default)',
            fontSize: '11px',
          }}
        >
          <div style={{ color: 'var(--text-muted)', marginBottom: '2px', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
            Active Repo
          </div>
          <div style={{ fontWeight: 600, color: 'var(--text-primary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {repoAnalysis.project_name}
          </div>
          <div style={{ color: 'var(--text-secondary)', fontSize: '10px' }}>
            {repoAnalysis.detected_languages[0] || 'Unknown'} · {repoAnalysis.file_count} files
          </div>
        </div>
      )}
    </aside>
  );
};
