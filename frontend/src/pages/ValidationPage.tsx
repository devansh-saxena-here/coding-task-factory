import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import {
  ShieldCheck,
  ShieldAlert,
  ArrowRight,
  Play,
  CheckCircle2,
  XCircle,
  Clock,
  AlertCircle,
} from 'lucide-react';
import { PageHeader } from '../components/PageHeader';
import { LoadingState } from '../components/LoadingState';
import { ErrorState } from '../components/ErrorState';
import { StatusBadge } from '../components/StatusBadge';
import { useProject } from '../context/ProjectContext';
import { taskService } from '../services/taskService';

export const ValidationPage: React.FC = () => {
  const navigate = useNavigate();
  const { task, solution, testSuite, validationReport, setValidationReport } = useProject();

  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleValidate = async () => {
    if (!task || !solution || !testSuite) return;
    setIsLoading(true);
    setErrorMessage(null);

    try {
      const report = await taskService.validateTaskPackage({
        task,
        solution,
        test_suite: testSuite,
        execution_mode: 'static',
      });
      setValidationReport(report);
    } catch (err: unknown) {
      const msg = (err as { message?: string })?.message || 'Validation request failed.';
      setErrorMessage(msg);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="Validation & Integrity Engine"
        description="Audits task packages across the 5 validation gates without executing untrusted code on the host machine."
      />

      {/* Dependency check banner */}
      {!task || !solution || !testSuite ? (
        <div className="card" style={{ padding: '32px 24px', textAlign: 'center' }}>
          <AlertCircle size={28} style={{ color: 'var(--warning)', margin: '0 auto 12px' }} />
          <h3 style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '6px' }}>
            Incomplete Task Package
          </h3>
          <p style={{ fontSize: '13px', color: 'var(--text-secondary)', maxWidth: '480px', margin: '0 auto 20px' }}>
            Full package validation requires a Task Specification, a Reference Solution, and an Automated Test Suite.
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
          {/* Action Bar */}
          <div className="card" style={{ padding: '20px', marginBottom: '24px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
              <div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  Validation Candidate
                </div>
                <h3 style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text-primary)' }}>
                  {task.title}
                </h3>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '2px' }}>
                  Solution files: {solution.files.length} · Feature tests: {testSuite.total_feature_tests} · Regression checks: {testSuite.total_regression_tests}
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <button
                  onClick={handleValidate}
                  disabled={isLoading}
                  className="btn btn-primary"
                >
                  <Play size={14} />
                  <span>{validationReport ? 'Re-run Validation Gates' : 'Run Validation Gates'}</span>
                </button>

                {validationReport && (
                  <button
                    onClick={() => navigate('/export')}
                    className="btn btn-secondary"
                  >
                    <span>Proceed to Harbor Export</span>
                    <ArrowRight size={14} />
                  </button>
                )}
              </div>
            </div>
          </div>

          {/* Loading & Error States */}
          {isLoading && (
            <div className="card" style={{ padding: '24px', marginBottom: '24px' }}>
              <LoadingState
                message="Evaluating task package through validation gates..."
                subtext="Checking path safety, collision prevention, file tree application, and verifying container isolation policies."
              />
            </div>
          )}

          {errorMessage && (
            <div style={{ marginBottom: '24px' }}>
              <ErrorState
                title="Validation Failed"
                message={errorMessage}
                onRetry={handleValidate}
              />
            </div>
          )}

          {/* Validation Report View */}
          {validationReport && !isLoading && (
            <div>
              {/* Verdict Summary Card */}
              <div
                className="card"
                style={{
                  padding: '24px',
                  marginBottom: '24px',
                  borderLeft: `4px solid ${
                    validationReport.overall_verdict === 'VALIDATED'
                      ? 'var(--success)'
                      : validationReport.overall_verdict === 'REJECTED'
                      ? 'var(--danger)'
                      : 'var(--warning)'
                  }`,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px', flexWrap: 'wrap', gap: '8px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    {validationReport.overall_verdict === 'VALIDATED' ? (
                      <ShieldCheck size={22} style={{ color: 'var(--success)' }} />
                    ) : validationReport.overall_verdict === 'REJECTED' ? (
                      <XCircle size={22} style={{ color: 'var(--danger)' }} />
                    ) : (
                      <ShieldAlert size={22} style={{ color: 'var(--warning)' }} />
                    )}
                    <div>
                      <h3 style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text-primary)' }}>
                        Overall Verdict: {validationReport.overall_verdict}
                      </h3>
                      <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                        Execution mode: <code className="code-inline">{validationReport.execution_mode}</code> · Duration: {validationReport.execution_duration_ms}ms
                      </div>
                    </div>
                  </div>

                  <StatusBadge status={validationReport.overall_verdict} />
                </div>

                {/* Truthful explanation banner */}
                <div
                  style={{
                    padding: '12px 14px',
                    borderRadius: 'var(--radius-md)',
                    backgroundColor: validationReport.overall_verdict === 'NOT_VALIDATED' ? 'var(--warning-light)' : 'var(--bg-muted)',
                    fontSize: '12.5px',
                    color: validationReport.overall_verdict === 'NOT_VALIDATED' ? 'var(--warning-text)' : 'var(--text-secondary)',
                    lineHeight: 1.5,
                  }}
                >
                  <strong>Audit Policy:</strong>{' '}
                  {validationReport.overall_verdict === 'NOT_VALIDATED'
                    ? 'In static execution mode, task artifacts are structurally verified and solution files are safely prepared, but untrusted code is never executed on the host. Under Harbor integrity standards, a task package remains NOT_VALIDATED until verified in a sandboxed container.'
                    : validationReport.overall_verdict === 'VALIDATED'
                    ? 'All 5 validation gates have been empirically verified inside an isolated container sandbox.'
                    : 'The task package failed structural integrity or path security validation gates.'}
                </div>
              </div>

              {/* 5 Validation Gates Breakdown */}
              <div className="card" style={{ padding: '20px', marginBottom: '24px' }}>
                <h4 style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '16px' }}>
                  Validation Gates Status
                </h4>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  {/* Gate 1: Baseline Repository Tests */}
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 14px', borderRadius: 'var(--radius-md)', backgroundColor: 'var(--bg-subtle)', border: '1px solid var(--border-default)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <Clock size={16} style={{ color: 'var(--text-muted)' }} />
                      <div>
                        <div style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-primary)' }}>
                          Gate 1: Baseline Repository Health
                        </div>
                        <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                          Verifies pre-existing tests pass on starting commit SHA
                        </div>
                      </div>
                    </div>
                    <span className="badge badge-default">NOT RUN (STATIC)</span>
                  </div>

                  {/* Gate 2: Solution Application Integrity */}
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 14px', borderRadius: 'var(--radius-md)', backgroundColor: 'var(--bg-subtle)', border: '1px solid var(--border-default)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      {validationReport.solution_applied_successfully ? (
                        <CheckCircle2 size={16} style={{ color: 'var(--success)' }} />
                      ) : (
                        <XCircle size={16} style={{ color: 'var(--danger)' }} />
                      )}
                      <div>
                        <div style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-primary)' }}>
                          Gate 2: Solution Application Integrity
                        </div>
                        <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                          Verifies non-collision, path safety, and file patch cleanliness
                        </div>
                      </div>
                    </div>
                    <span className={`badge ${validationReport.solution_applied_successfully ? 'badge-success' : 'badge-danger'}`}>
                      {validationReport.solution_applied_successfully ? 'PASSED (STATIC)' : 'FAILED'}
                    </span>
                  </div>

                  {/* Gate 3: Feature Tests */}
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 14px', borderRadius: 'var(--radius-md)', backgroundColor: 'var(--bg-subtle)', border: '1px solid var(--border-default)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <Clock size={16} style={{ color: 'var(--text-muted)' }} />
                      <div>
                        <div style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-primary)' }}>
                          Gate 3: Feature Tests Execution
                        </div>
                        <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                          Verifies reference solution satisfies all acceptance criteria
                        </div>
                      </div>
                    </div>
                    <span className="badge badge-default">NOT RUN (STATIC)</span>
                  </div>

                  {/* Gate 4: Regression Tests */}
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 14px', borderRadius: 'var(--radius-md)', backgroundColor: 'var(--bg-subtle)', border: '1px solid var(--border-default)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <Clock size={16} style={{ color: 'var(--text-muted)' }} />
                      <div>
                        <div style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-primary)' }}>
                          Gate 4: Regression Tests Execution
                        </div>
                        <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                          Verifies existing codebase functionality remains undamaged
                        </div>
                      </div>
                    </div>
                    <span className="badge badge-default">NOT RUN (STATIC)</span>
                  </div>

                  {/* Gate 5: Mutation Testing */}
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 14px', borderRadius: 'var(--radius-md)', backgroundColor: 'var(--bg-subtle)', border: '1px solid var(--border-default)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <Clock size={16} style={{ color: 'var(--text-muted)' }} />
                      <div>
                        <div style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-primary)' }}>
                          Gate 5: Mutation Testing (Negative Control)
                        </div>
                        <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                          Proves test suite catches faulty and incomplete implementations
                        </div>
                      </div>
                    </div>
                    <span className="badge badge-default">NOT RUN (STATIC)</span>
                  </div>
                </div>
              </div>

              {/* Rejection / Status Reasons Trail */}
              {validationReport.rejection_reasons.length > 0 && (
                <div className="card" style={{ padding: '18px' }}>
                  <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '8px' }}>
                    Audit & Reason Log
                  </div>
                  <ul style={{ paddingLeft: '18px', fontSize: '12.5px', color: 'var(--text-secondary)', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    {validationReport.rejection_reasons.map((reason, idx) => (
                      <li key={idx}>{reason}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
};
