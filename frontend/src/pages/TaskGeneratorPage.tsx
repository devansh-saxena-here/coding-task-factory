import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import {
  Sparkles,
  ArrowRight,
  CheckCircle,
  FileCode,
  Sliders,
  AlertCircle,
} from 'lucide-react';
import { PageHeader } from '../components/PageHeader';
import { LoadingState } from '../components/LoadingState';
import { ErrorState } from '../components/ErrorState';
import { StatusBadge } from '../components/StatusBadge';
import { useProject } from '../context/ProjectContext';
import { taskService } from '../services/taskService';
import { TaskDifficulty } from '../types/task';

export const TaskGeneratorPage: React.FC = () => {
  const navigate = useNavigate();
  const { repoAnalysis, task, setTask } = useProject();

  const [difficulty, setDifficulty] = useState<TaskDifficulty>('medium');
  const [category, setCategory] = useState<string>('backend');
  const [focusArea, setFocusArea] = useState<string>('');
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleGenerate = async () => {
    setIsLoading(true);
    setErrorMessage(null);

    try {
      if (repoAnalysis) {
        // Contextual task generation grounded on analyzed repository
        const res = await taskService.generateTaskFromRepo({
          repo_analysis: repoAnalysis,
          options: {
            difficulty,
            category,
            focus_area: focusArea.trim() || undefined,
          },
        });
        setTask(res);
      } else {
        // Standalone topic task generation
        const res = await taskService.generateTopicTask({
          topic: focusArea.trim() || 'Build a scalable REST microservice with unit tests',
          difficulty,
          category,
          language: 'python',
        });
        setTask(res);
      }
    } catch (err: unknown) {
      const msg = (err as { message?: string })?.message || 'Failed to generate task.';
      setErrorMessage(msg);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="Contextual Task Generator"
        description="Ground tasks directly on repository architecture, dependencies, and starting commit SHA using Gemini AI."
      />

      {/* Repository Context Banner */}
      {!repoAnalysis && (
        <div
          className="card"
          style={{
            padding: '16px',
            marginBottom: '20px',
            backgroundColor: 'var(--warning-light)',
            borderColor: 'var(--warning-border)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '12px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <AlertCircle size={18} style={{ color: 'var(--warning)' }} />
            <span style={{ fontSize: '13px', color: 'var(--warning-text)' }}>
              No repository analyzed yet. Tasks will be synthesized in standalone mode. For grounded tasks, ingest a repository first.
            </span>
          </div>
          <Link to="/new-project" className="btn btn-secondary" style={{ fontSize: '12px', whiteSpace: 'nowrap' }}>
            Ingest Repo
          </Link>
        </div>
      )}

      {/* Generator Configuration Form */}
      <div className="card" style={{ padding: '24px', marginBottom: '28px' }}>
        <h3 style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Sliders size={16} />
          <span>Task Generation Parameters</span>
        </h3>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '16px', marginBottom: '20px' }}>
          {/* Difficulty */}
          <div>
            <label style={{ display: 'block', fontSize: '12.5px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: '6px' }}>
              Difficulty Level
            </label>
            <select
              className="input"
              value={difficulty}
              onChange={(e) => setDifficulty(e.target.value as TaskDifficulty)}
            >
              <option value="easy">Easy (Targeted fix or small helper)</option>
              <option value="medium">Medium (Component or API feature)</option>
              <option value="hard">Hard (Subsystem or architectural change)</option>
            </select>
          </div>

          {/* Category */}
          <div>
            <label style={{ display: 'block', fontSize: '12.5px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: '6px' }}>
              Task Category
            </label>
            <select
              className="input"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            >
              <option value="backend">Backend & API</option>
              <option value="frontend">Frontend & UI</option>
              <option value="fullstack">Fullstack Application</option>
              <option value="devops">DevOps & Tooling</option>
              <option value="data">Data Processing & Pipeline</option>
            </select>
          </div>

          {/* Focus Area */}
          <div style={{ gridColumn: 'span 2' }}>
            <label style={{ display: 'block', fontSize: '12.5px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: '6px' }}>
              Specific Focus Area or Feature Goal (Optional)
            </label>
            <input
              type="text"
              className="input"
              placeholder="e.g. Implement Redis caching with 60s TTL on items endpoint"
              value={focusArea}
              onChange={(e) => setFocusArea(e.target.value)}
            />
          </div>
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
          <button
            onClick={handleGenerate}
            disabled={isLoading}
            className="btn btn-primary"
          >
            <Sparkles size={14} />
            <span>{isLoading ? 'Synthesizing Task...' : 'Generate Contextual Task'}</span>
          </button>
        </div>
      </div>

      {/* Loading & Error States */}
      {isLoading && (
        <div className="card" style={{ padding: '24px', marginBottom: '28px' }}>
          <LoadingState
            message="Generating contextual coding task with Gemini AI..."
            subtext="Grounding functional requirements, test expectations, and acceptance criteria on codebase conventions."
          />
        </div>
      )}

      {errorMessage && (
        <div style={{ marginBottom: '28px' }}>
          <ErrorState
            title="Task Generation Failed"
            message={errorMessage}
            onRetry={handleGenerate}
          />
        </div>
      )}

      {/* Generated Task Preview */}
      {task && !isLoading && (
        <div className="card" style={{ padding: '24px' }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '16px', gap: '12px', flexWrap: 'wrap' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                <StatusBadge status={task.difficulty} />
                <span className="badge badge-default">{task.category}</span>
                <span className="badge badge-default">{task.language}</span>
                {task.starting_commit_sha && (
                  <span className="code-inline" title="Starting Git Commit SHA">
                    SHA: {task.starting_commit_sha.slice(0, 8)}
                  </span>
                )}
              </div>
              <h3 style={{ fontSize: '18px', fontWeight: 600, color: 'var(--text-primary)' }}>
                {task.title}
              </h3>
            </div>

            <button
              onClick={() => navigate('/solution')}
              className="btn btn-primary"
            >
              <span>Proceed to Solution Engine</span>
              <ArrowRight size={14} />
            </button>
          </div>

          {/* Description */}
          <div style={{ marginBottom: '20px', fontSize: '13px', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            {task.description}
          </div>

          {/* Two-column: Requirements and Acceptance Criteria */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '20px', marginBottom: '20px' }}>
            {/* Functional Requirements */}
            <div style={{ padding: '16px', borderRadius: 'var(--radius-md)', backgroundColor: 'var(--bg-subtle)', border: '1px solid var(--border-default)' }}>
              <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '10px' }}>
                Functional Requirements
              </div>
              <ul style={{ paddingLeft: '18px', display: 'flex', flexDirection: 'column', gap: '6px', fontSize: '12.5px', color: 'var(--text-secondary)' }}>
                {task.requirements.map((req, i) => (
                  <li key={i}>{req}</li>
                ))}
              </ul>
            </div>

            {/* Acceptance Criteria */}
            <div style={{ padding: '16px', borderRadius: 'var(--radius-md)', backgroundColor: 'var(--bg-subtle)', border: '1px solid var(--border-default)' }}>
              <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '10px' }}>
                Acceptance Criteria
              </div>
              <ul style={{ paddingLeft: '18px', display: 'flex', flexDirection: 'column', gap: '6px', fontSize: '12.5px', color: 'var(--text-secondary)' }}>
                {task.acceptance_criteria.map((crit, i) => (
                  <li key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: '6px' }}>
                    <CheckCircle size={13} style={{ color: 'var(--success)', marginTop: '2px', flexShrink: 0 }} />
                    <span>{crit}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>

          {/* Relevant Files */}
          {task.relevant_files && task.relevant_files.length > 0 && (
            <div>
              <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '8px' }}>
                Suggested Target Files
              </div>
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                {task.relevant_files.map((file, i) => (
                  <span key={i} className="code-inline" style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                    <FileCode size={11} />
                    <span>{file}</span>
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
