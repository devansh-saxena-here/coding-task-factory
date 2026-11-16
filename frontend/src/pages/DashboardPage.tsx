import React from 'react';
import { Link } from 'react-router-dom';
import {
  FolderPlus,
  ArrowRight,
  GitBranch,
  Sparkles,
  ShieldCheck,
  Package,
  Layers,
  CheckCircle2,
} from 'lucide-react';
import { PageHeader } from '../components/PageHeader';
import { StatCard } from '../components/StatCard';
import { StatusBadge } from '../components/StatusBadge';
import { useProject } from '../context/ProjectContext';

export const DashboardPage: React.FC = () => {
  const { repoAnalysis, task, solution, testSuite, validationReport } = useProject();

  const stagesCompleted = [
    Boolean(repoAnalysis),
    Boolean(task),
    Boolean(solution),
    Boolean(testSuite),
    Boolean(validationReport),
  ].filter(Boolean).length;

  return (
    <div>
      <PageHeader
        title="Coding Task Factory Dashboard"
        description="Convert real-world repositories into reproducible, verifiable Harbor-compatible coding tasks for AI evaluation."
        actions={
          <Link to="/new-project" className="btn btn-primary">
            <FolderPlus size={15} />
            <span>New Project</span>
          </Link>
        }
      />

      {/* Metrics Row */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: '16px',
          marginBottom: '28px',
        }}
      >
        <StatCard
          title="Active Repository"
          value={repoAnalysis ? repoAnalysis.project_name : '0'}
          subtitle={repoAnalysis ? `${repoAnalysis.file_count} files analyzed` : 'No repo loaded'}
          icon={<GitBranch size={16} />}
        />
        <StatCard
          title="Generated Tasks"
          value={task ? '1' : '0'}
          subtitle={task ? task.category : 'Session total'}
          icon={<Sparkles size={16} />}
        />
        <StatCard
          title="Validation Status"
          value={validationReport ? validationReport.overall_verdict : 'N/A'}
          subtitle="Truthful static guard"
          badge={
            validationReport ? (
              <StatusBadge status={validationReport.overall_verdict} size="sm" />
            ) : undefined
          }
          icon={<ShieldCheck size={16} />}
        />
        <StatCard
          title="Harbor 1.4 Exports"
          value={validationReport ? 'Ready' : 'Pending'}
          subtitle="Dockerfile + reward protocol"
          icon={<Package size={16} />}
        />
      </div>

      {/* Active Pipeline Status Banner */}
      <div className="card" style={{ padding: '24px', marginBottom: '28px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px', flexWrap: 'wrap', gap: '8px' }}>
          <div>
            <h3 style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '2px' }}>
              Current Pipeline Execution
            </h3>
            <p style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
              {repoAnalysis
                ? `Active codebase: ${repoAnalysis.project_name} (${repoAnalysis.detected_languages[0] || 'Python'})`
                : 'No repository currently staged. Ingest a GitHub repo or upload a ZIP to begin.'}
            </p>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
              {stagesCompleted} of 5 Stages Complete
            </span>
            <Link
              to={repoAnalysis ? (task ? (solution ? '/test-suite' : '/solution') : '/task-generator') : '/new-project'}
              className="btn btn-secondary"
              style={{ fontSize: '12px' }}
            >
              <span>{repoAnalysis ? 'Continue Pipeline' : 'Start Ingestion'}</span>
              <ArrowRight size={13} />
            </Link>
          </div>
        </div>

        {/* Visual progress bar */}
        <div
          style={{
            height: '6px',
            backgroundColor: 'var(--bg-muted)',
            borderRadius: 'var(--radius-full)',
            overflow: 'hidden',
            marginBottom: '16px',
          }}
        >
          <div
            style={{
              height: '100%',
              width: `${(stagesCompleted / 5) * 100}%`,
              backgroundColor: 'var(--accent-primary)',
              borderRadius: 'var(--radius-full)',
              transition: 'width 0.3s ease',
            }}
          />
        </div>

        {/* Stage Pills */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '12px' }}>
          {[
            { name: '1. Ingestion', done: Boolean(repoAnalysis), path: '/new-project' },
            { name: '2. Task Spec', done: Boolean(task), path: '/task-generator' },
            { name: '3. Solution', done: Boolean(solution), path: '/solution' },
            { name: '4. Test Suite', done: Boolean(testSuite), path: '/test-suite' },
            { name: '5. Validation', done: Boolean(validationReport), path: '/validation' },
          ].map((st, i) => (
            <Link
              key={i}
              to={st.path}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                padding: '8px 12px',
                borderRadius: 'var(--radius-md)',
                backgroundColor: st.done ? 'var(--success-light)' : 'var(--bg-subtle)',
                border: `1px solid ${st.done ? 'var(--success-border)' : 'var(--border-default)'}`,
                color: st.done ? 'var(--success-text)' : 'var(--text-secondary)',
                fontSize: '12px',
                fontWeight: 500,
                textDecoration: 'none',
              }}
            >
              {st.done ? (
                <CheckCircle2 size={14} style={{ color: 'var(--success)' }} />
              ) : (
                <div
                  style={{
                    width: '8px',
                    height: '8px',
                    borderRadius: 'var(--radius-full)',
                    backgroundColor: 'var(--border-strong)',
                  }}
                />
              )}
              <span>{st.name}</span>
            </Link>
          ))}
        </div>
      </div>

      {/* Two Column Layout: Workflow Guide & Features */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '20px' }}>
        {/* Left: Quick Actions */}
        <div className="card" style={{ padding: '20px' }}>
          <h3 style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '14px' }}>
            Quick Actions
          </h3>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <Link
              to="/new-project"
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '10px 14px',
                borderRadius: 'var(--radius-md)',
                backgroundColor: 'var(--bg-subtle)',
                border: '1px solid var(--border-default)',
                color: 'var(--text-primary)',
                textDecoration: 'none',
              }}
              className="card-hover"
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <FolderPlus size={16} style={{ color: 'var(--accent-primary)' }} />
                <div>
                  <div style={{ fontSize: '13px', fontWeight: 500 }}>Upload Repository ZIP</div>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Analyze local project structure</div>
                </div>
              </div>
              <ArrowRight size={14} style={{ color: 'var(--text-muted)' }} />
            </Link>

            <Link
              to="/new-project"
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '10px 14px',
                borderRadius: 'var(--radius-md)',
                backgroundColor: 'var(--bg-subtle)',
                border: '1px solid var(--border-default)',
                color: 'var(--text-primary)',
                textDecoration: 'none',
              }}
              className="card-hover"
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <GitBranch size={16} style={{ color: 'var(--info)' }} />
                <div>
                  <div style={{ fontSize: '13px', fontWeight: 500 }}>Ingest GitHub Repository</div>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Clone with commit SHA pinning</div>
                </div>
              </div>
              <ArrowRight size={14} style={{ color: 'var(--text-muted)' }} />
            </Link>

            <Link
              to="/export"
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '10px 14px',
                borderRadius: 'var(--radius-md)',
                backgroundColor: 'var(--bg-subtle)',
                border: '1px solid var(--border-default)',
                color: 'var(--text-primary)',
                textDecoration: 'none',
              }}
              className="card-hover"
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <Package size={16} style={{ color: 'var(--success)' }} />
                <div>
                  <div style={{ fontSize: '13px', fontWeight: 500 }}>Download Harbor Package</div>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Standard Harbor 1.4 evaluation ZIP</div>
                </div>
              </div>
              <ArrowRight size={14} style={{ color: 'var(--text-muted)' }} />
            </Link>
          </div>
        </div>

        {/* Right: Architecture & Compliance Highlights */}
        <div className="card" style={{ padding: '20px' }}>
          <h3 style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '14px' }}>
            System Architecture & Standards
          </h3>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', fontSize: '12.5px', color: 'var(--text-secondary)' }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px' }}>
              <Layers size={15} style={{ color: 'var(--accent-primary)', marginTop: '2px', flexShrink: 0 }} />
              <div>
                <strong style={{ color: 'var(--text-primary)' }}>Harbor Schema 1.4:</strong> Generates conforming <code className="code-inline">task.toml</code>, <code className="code-inline">environment/Dockerfile</code>, <code className="code-inline">tests/test.sh</code>, and <code className="code-inline">solution/solve.sh</code>.
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px' }}>
              <ShieldCheck size={15} style={{ color: 'var(--success)', marginTop: '2px', flexShrink: 0 }} />
              <div>
                <strong style={{ color: 'var(--text-primary)' }}>Zero Host Execution:</strong> Tasks and untrusted code are never executed on host machine. Safe static validation guards enforce integrity.
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px' }}>
              <GitBranch size={15} style={{ color: 'var(--info)', marginTop: '2px', flexShrink: 0 }} />
              <div>
                <strong style={{ color: 'var(--text-primary)' }}>Commit SHA Pinning:</strong> Starting Git commit hashes are preserved across all pipeline artifacts to guarantee benchmark reproducibility.
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
