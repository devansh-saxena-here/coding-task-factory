import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Upload,
  GitBranch,
  ArrowRight,
  FileCode,
  FolderTree,
} from 'lucide-react';
import { PageHeader } from '../components/PageHeader';
import { LoadingState } from '../components/LoadingState';
import { ErrorState } from '../components/ErrorState';
import { FileTree } from '../components/FileTree';
import { useProject } from '../context/ProjectContext';
import { taskService } from '../services/taskService';

export const NewProjectPage: React.FC = () => {
  const navigate = useNavigate();
  const { repoAnalysis, setRepoAnalysis } = useProject();

  const [activeTab, setActiveTab] = useState<'upload' | 'github'>('upload');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [githubUrl, setGithubUrl] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setSelectedFile(e.target.files[0]);
      setErrorMessage(null);
    }
  };

  const handleAnalyze = async () => {
    setIsLoading(true);
    setErrorMessage(null);

    try {
      if (activeTab === 'upload') {
        if (!selectedFile) {
          setErrorMessage('Please select a repository ZIP file to upload.');
          setIsLoading(false);
          return;
        }
        const res = await taskService.analyzeUpload(selectedFile);
        setRepoAnalysis(res);
      } else {
        if (!githubUrl.trim()) {
          setErrorMessage('Please provide a valid GitHub repository URL.');
          setIsLoading(false);
          return;
        }
        const res = await taskService.analyzeGithub({ repo_url: githubUrl.trim() });
        setRepoAnalysis(res);
      }
    } catch (err: unknown) {
      const msg = (err as { message?: string })?.message || 'Failed to analyze repository.';
      setErrorMessage(msg);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="Repository Ingestion & Analysis"
        description="Ingest a public GitHub repository or upload a local project ZIP archive to extract codebase structure, test frameworks, and commit metadata."
      />

      {/* Tabs */}
      <div style={{ display: 'flex', gap: '8px', marginBottom: '20px' }}>
        <button
          onClick={() => setActiveTab('upload')}
          className={`btn ${activeTab === 'upload' ? 'btn-primary' : 'btn-secondary'}`}
        >
          <Upload size={14} />
          <span>Upload ZIP Archive</span>
        </button>
        <button
          onClick={() => setActiveTab('github')}
          className={`btn ${activeTab === 'github' ? 'btn-primary' : 'btn-secondary'}`}
        >
          <GitBranch size={14} />
          <span>Public GitHub URL</span>
        </button>
      </div>

      {/* Ingestion Form Card */}
      <div className="card" style={{ padding: '24px', marginBottom: '28px' }}>
        {activeTab === 'upload' ? (
          <div>
            <label style={{ display: 'block', fontSize: '13px', fontWeight: 500, color: 'var(--text-primary)', marginBottom: '6px' }}>
              Select Repository ZIP File
            </label>
            <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '14px' }}>
              Upload a zip archive of the target codebase. Zip-Slip and path traversal protection is automatically enforced.
            </p>

            <div
              style={{
                border: '2px dashed var(--border-default)',
                borderRadius: 'var(--radius-md)',
                padding: '32px 16px',
                textAlign: 'center',
                backgroundColor: 'var(--bg-subtle)',
                marginBottom: '16px',
                cursor: 'pointer',
              }}
              onClick={() => document.getElementById('repo-file-input')?.click()}
            >
              <Upload size={24} style={{ color: 'var(--text-muted)', marginBottom: '8px' }} />
              <div style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-primary)' }}>
                {selectedFile ? selectedFile.name : 'Click to browse or drag and drop ZIP file'}
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
                {selectedFile ? `${(selectedFile.size / 1024).toFixed(1)} KB` : 'Maximum archive size 50 MB'}
              </div>
              <input
                id="repo-file-input"
                type="file"
                accept=".zip"
                onChange={handleFileChange}
                style={{ display: 'none' }}
              />
            </div>
          </div>
        ) : (
          <div>
            <label style={{ display: 'block', fontSize: '13px', fontWeight: 500, color: 'var(--text-primary)', marginBottom: '6px' }}>
              GitHub Repository URL
            </label>
            <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '14px' }}>
              Provide a public repository URL on github.com (e.g., https://github.com/fastapi/fastapi).
            </p>
            <input
              type="url"
              className="input"
              placeholder="https://github.com/owner/repository"
              value={githubUrl}
              onChange={(e) => setGithubUrl(e.target.value)}
              style={{ marginBottom: '16px' }}
            />
          </div>
        )}

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
          <button
            onClick={handleAnalyze}
            disabled={isLoading || (activeTab === 'upload' && !selectedFile) || (activeTab === 'github' && !githubUrl.trim())}
            className="btn btn-primary"
          >
            <GitBranch size={14} />
            <span>Analyze Codebase</span>
          </button>
        </div>
      </div>

      {/* Loading & Error States */}
      {isLoading && (
        <div className="card" style={{ padding: '24px', marginBottom: '28px' }}>
          <LoadingState
            message="Analyzing repository architecture..."
            subtext="Inspecting AST, programming languages, build configurations, and test runners without executing code."
          />
        </div>
      )}

      {errorMessage && (
        <div style={{ marginBottom: '28px' }}>
          <ErrorState
            title="Analysis Failed"
            message={errorMessage}
            onRetry={handleAnalyze}
          />
        </div>
      )}

      {/* Analysis Results Display */}
      {repoAnalysis && !isLoading && (
        <div className="card" style={{ padding: '24px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px', flexWrap: 'wrap', gap: '8px' }}>
            <div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                Codebase Profile
              </div>
              <h3 style={{ fontSize: '18px', fontWeight: 600, color: 'var(--text-primary)' }}>
                {repoAnalysis.project_name}
              </h3>
            </div>

            <button
              onClick={() => navigate('/task-generator')}
              className="btn btn-primary"
            >
              <span>Proceed to Task Generator</span>
              <ArrowRight size={14} />
            </button>
          </div>

          {/* Quick Metrics Grid */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '12px', marginBottom: '24px' }}>
            <div style={{ padding: '12px', borderRadius: 'var(--radius-md)', backgroundColor: 'var(--bg-subtle)', border: '1px solid var(--border-default)' }}>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>PRIMARY LANGUAGE</div>
              <div style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)', marginTop: '2px' }}>
                {repoAnalysis.detected_languages[0] || 'Unknown'}
              </div>
            </div>

            <div style={{ padding: '12px', borderRadius: 'var(--radius-md)', backgroundColor: 'var(--bg-subtle)', border: '1px solid var(--border-default)' }}>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>TOTAL FILES</div>
              <div style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)', marginTop: '2px' }}>
                {repoAnalysis.file_count}
              </div>
            </div>

            <div style={{ padding: '12px', borderRadius: 'var(--radius-md)', backgroundColor: 'var(--bg-subtle)', border: '1px solid var(--border-default)' }}>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>STARTING COMMIT SHA</div>
              <div style={{ fontSize: '12px', fontFamily: 'var(--font-mono)', fontWeight: 500, color: 'var(--text-primary)', marginTop: '2px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {repoAnalysis.commit_sha ? repoAnalysis.commit_sha.slice(0, 10) : 'None (Zip baseline)'}
              </div>
            </div>

            <div style={{ padding: '12px', borderRadius: 'var(--radius-md)', backgroundColor: 'var(--bg-subtle)', border: '1px solid var(--border-default)' }}>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>FRAMEWORKS</div>
              <div style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)', marginTop: '2px' }}>
                {repoAnalysis.detected_frameworks.length > 0 ? repoAnalysis.detected_frameworks.join(', ') : 'None detected'}
              </div>
            </div>
          </div>

          {/* Folder Hierarchy and README Preview */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '20px' }}>
            <div>
              <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <FolderTree size={15} />
                <span>Folder Structure</span>
              </div>
              <FileTree files={repoAnalysis.folder_structure} maxDisplay={25} />
            </div>

            <div>
              <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <FileCode size={15} />
                <span>README Summary</span>
              </div>
              <div
                className="card"
                style={{
                  padding: '12px 16px',
                  fontSize: '12.5px',
                  color: 'var(--text-secondary)',
                  maxHeight: '320px',
                  overflowY: 'auto',
                  lineHeight: 1.6,
                  whiteSpace: 'pre-wrap',
                  backgroundColor: '#ffffff',
                }}
              >
                {repoAnalysis.readme_summary || 'No README file detected in codebase.'}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
