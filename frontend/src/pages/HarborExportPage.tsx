import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Package,
  Download,
  CheckCircle2,
  FileCode,
  Terminal,
  FolderArchive,
  Check,
  AlertCircle,
} from 'lucide-react';
import { PageHeader } from '../components/PageHeader';
import { ErrorState } from '../components/ErrorState';
import { StatusBadge } from '../components/StatusBadge';
import { useProject } from '../context/ProjectContext';
import { taskService } from '../services/taskService';

export const HarborExportPage: React.FC = () => {
  const { task, solution, testSuite, validationReport } = useProject();

  const [taskPrefix, setTaskPrefix] = useState('ctf');
  const [isExporting, setIsExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [downloadSuccess, setDownloadSuccess] = useState<string | null>(null);

  const handleDownloadZip = async () => {
    if (!task || !solution || !testSuite) return;
    setIsExporting(true);
    setExportError(null);
    setDownloadSuccess(null);

    try {
      const result = await taskService.exportHarborTask({
        task,
        solution,
        test_suite: testSuite,
        validation_report: validationReport || undefined,
        task_prefix: taskPrefix.trim() || 'ctf',
      });

      // Trigger native browser file download
      const blobUrl = window.URL.createObjectURL(result.blob);
      const link = document.createElement('a');
      link.href = blobUrl;
      link.download = result.filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(blobUrl);

      setDownloadSuccess(`Successfully downloaded ${result.filename} (${(result.blob.size / 1024).toFixed(1)} KB)`);
    } catch (err: unknown) {
      const msg = (err as { message?: string })?.message || 'Failed to export Harbor task package.';
      setExportError(msg);
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="Harbor Package Exporter"
        description="Converts task specifications, solutions, and tests into official Harbor Schema 1.4 evaluation benchmarks with verifiable reward protocols."
      />

      {!task || !solution || !testSuite ? (
        <div className="card" style={{ padding: '32px 24px', textAlign: 'center' }}>
          <AlertCircle size={28} style={{ color: 'var(--warning)', margin: '0 auto 12px' }} />
          <h3 style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '6px' }}>
            Incomplete Package for Harbor Export
          </h3>
          <p style={{ fontSize: '13px', color: 'var(--text-secondary)', maxWidth: '460px', margin: '0 auto 20px' }}>
            Harbor evaluation tasks require a complete specification package: Task Spec, Solution Files, and Test Suite.
          </p>
          <div style={{ display: 'flex', gap: '8px', justifyContent: 'center' }}>
            {!task && (
              <Link to="/task-generator" className="btn btn-secondary">
                Generate Task
              </Link>
            )}
            {!solution && (
              <Link to="/solution" className="btn btn-secondary">
                Synthesize Solution
              </Link>
            )}
            {!testSuite && (
              <Link to="/test-suite" className="btn btn-secondary">
                Synthesize Tests
              </Link>
            )}
          </div>
        </div>
      ) : (
        <>
          {/* Export Action Card */}
          <div className="card" style={{ padding: '24px', marginBottom: '24px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px', flexWrap: 'wrap', gap: '12px' }}>
              <div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  Target Evaluation Benchmark
                </div>
                <h3 style={{ fontSize: '17px', fontWeight: 600, color: 'var(--text-primary)' }}>
                  {task.title}
                </h3>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <label style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 500 }}>
                    Prefix:
                  </label>
                  <input
                    type="text"
                    className="input"
                    value={taskPrefix}
                    onChange={(e) => setTaskPrefix(e.target.value)}
                    style={{ width: '100px', padding: '5px 8px', fontSize: '12px' }}
                    placeholder="ctf"
                  />
                </div>

                <button
                  onClick={handleDownloadZip}
                  disabled={isExporting}
                  className="btn btn-primary"
                >
                  <Download size={14} />
                  <span>{isExporting ? 'Packaging Archive...' : 'Download Harbor ZIP'}</span>
                </button>
              </div>
            </div>

            {/* Success notification */}
            {downloadSuccess && (
              <div
                style={{
                  padding: '10px 14px',
                  borderRadius: 'var(--radius-md)',
                  backgroundColor: 'var(--success-light)',
                  border: '1px solid var(--success-border)',
                  color: 'var(--success-text)',
                  fontSize: '12.5px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  marginBottom: '16px',
                }}
              >
                <Check size={14} />
                <span>{downloadSuccess}</span>
              </div>
            )}

            {/* Error state */}
            {exportError && (
              <div style={{ marginBottom: '16px' }}>
                <ErrorState
                  title="Export Failed"
                  message={exportError}
                  onRetry={handleDownloadZip}
                />
              </div>
            )}

            {/* Package Metadata Summary */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '12px' }}>
              <div style={{ padding: '12px', borderRadius: 'var(--radius-md)', backgroundColor: 'var(--bg-subtle)', border: '1px solid var(--border-default)' }}>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>HARBOR TASK ID</div>
                <div style={{ fontSize: '13px', fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--text-primary)', marginTop: '2px' }}>
                  {taskPrefix}/{task.id.slice(0, 12)}
                </div>
              </div>

              <div style={{ padding: '12px', borderRadius: 'var(--radius-md)', backgroundColor: 'var(--bg-subtle)', border: '1px solid var(--border-default)' }}>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>STARTING COMMIT SHA</div>
                <div style={{ fontSize: '12px', fontFamily: 'var(--font-mono)', fontWeight: 500, color: 'var(--text-primary)', marginTop: '2px' }}>
                  {testSuite.repository.starting_commit_sha || task.starting_commit_sha || 'None (Zip Baseline)'}
                </div>
              </div>

              <div style={{ padding: '12px', borderRadius: 'var(--radius-md)', backgroundColor: 'var(--bg-subtle)', border: '1px solid var(--border-default)' }}>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>RECORDED VALIDATION STATUS</div>
                <div style={{ marginTop: '4px' }}>
                  <StatusBadge status={validationReport ? validationReport.overall_verdict : 'NOT_VALIDATED'} size="sm" />
                </div>
              </div>

              <div style={{ padding: '12px', borderRadius: 'var(--radius-md)', backgroundColor: 'var(--bg-subtle)', border: '1px solid var(--border-default)' }}>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>SCHEMA VERSION</div>
                <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)', marginTop: '2px' }}>
                  Harbor 1.4
                </div>
              </div>
            </div>
          </div>

          {/* Harbor Package Layout Anatomy */}
          <div className="card" style={{ padding: '24px' }}>
            <h4 style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <FolderArchive size={16} />
              <span>Harbor ZIP Package Anatomy</span>
            </h4>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '14px' }}>
              {/* task.toml */}
              <div style={{ padding: '14px', borderRadius: 'var(--radius-md)', backgroundColor: 'var(--bg-subtle)', border: '1px solid var(--border-default)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                  <FileCode size={14} style={{ color: 'var(--accent-primary)' }} />
                  <span style={{ fontSize: '13px', fontWeight: 600, fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>
                    task.toml
                  </span>
                </div>
                <p style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                  Defines <code className="code-inline">schema_version = "1.4"</code>, task metadata, environment resource thresholds (CPU/RAM/storage), and verifier timeouts.
                </p>
              </div>

              {/* instruction.md */}
              <div style={{ padding: '14px', borderRadius: 'var(--radius-md)', backgroundColor: 'var(--bg-subtle)', border: '1px solid var(--border-default)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                  <FileCode size={14} style={{ color: 'var(--info)' }} />
                  <span style={{ fontSize: '13px', fontWeight: 600, fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>
                    instruction.md
                  </span>
                </div>
                <p style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                  Agent-facing task instructions, functional requirements, and acceptance criteria with strictly zero solution leaks or test assertion leaks.
                </p>
              </div>

              {/* environment/Dockerfile */}
              <div style={{ padding: '14px', borderRadius: 'var(--radius-md)', backgroundColor: 'var(--bg-subtle)', border: '1px solid var(--border-default)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                  <Terminal size={14} style={{ color: 'var(--warning)' }} />
                  <span style={{ fontSize: '13px', fontWeight: 600, fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>
                    environment/Dockerfile
                  </span>
                </div>
                <p style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                  Container execution sandbox image pinning <code className="code-inline">STARTING_COMMIT_SHA</code> and pre-installing project runtime tools.
                </p>
              </div>

              {/* tests/test.sh */}
              <div style={{ padding: '14px', borderRadius: 'var(--radius-md)', backgroundColor: 'var(--bg-subtle)', border: '1px solid var(--border-default)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                  <CheckCircle2 size={14} style={{ color: 'var(--success)' }} />
                  <span style={{ fontSize: '13px', fontWeight: 600, fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>
                    tests/test.sh
                  </span>
                </div>
                <p style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                  Evaluation verifier script running feature & regression suites, writing scalar reward (<code className="code-inline">1.0</code> or <code className="code-inline">0.0</code>) to <code className="code-inline">/logs/verifier/reward.txt</code>.
                </p>
              </div>

              {/* solution/solve.sh & files */}
              <div style={{ padding: '14px', borderRadius: 'var(--radius-md)', backgroundColor: 'var(--bg-subtle)', border: '1px solid var(--border-default)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                  <Package size={14} style={{ color: 'var(--accent-primary)' }} />
                  <span style={{ fontSize: '13px', fontWeight: 600, fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>
                    solution/solve.sh
                  </span>
                </div>
                <p style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                  Harbor oracle solution script that applies reference files from <code className="code-inline">solution/files/</code> into <code className="code-inline">/workspace</code> to verify solvability.
                </p>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
};
