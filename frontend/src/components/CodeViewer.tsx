import React, { useState } from 'react';
import { Check, Copy, FileCode } from 'lucide-react';

interface CodeViewerProps {
  code: string;
  language?: string;
  filePath?: string;
  maxHeight?: string;
}

export const CodeViewer: React.FC<CodeViewerProps> = ({
  code,
  language = 'python',
  filePath,
  maxHeight = '420px',
}) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const lines = code.split('\n');

  return (
    <div
      className="card"
      style={{
        overflow: 'hidden',
        border: '1px solid var(--border-default)',
        backgroundColor: '#fafafa',
      }}
    >
      {/* File / language header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '8px 14px',
          borderBottom: '1px solid var(--border-default)',
          backgroundColor: '#f8fafc',
          fontSize: '12px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-secondary)' }}>
          <FileCode size={14} style={{ color: 'var(--accent-primary)' }} />
          <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 500, color: 'var(--text-primary)' }}>
            {filePath || `snippet.${language === 'python' ? 'py' : language === 'typescript' ? 'ts' : 'txt'}`}
          </span>
          {language && (
            <span style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
              ({language})
            </span>
          )}
        </div>

        <button
          onClick={handleCopy}
          className="btn btn-subtle"
          style={{ padding: '4px 8px', fontSize: '11px', height: '26px' }}
          title="Copy code"
        >
          {copied ? (
            <>
              <Check size={12} style={{ color: 'var(--success)' }} />
              <span style={{ color: 'var(--success-text)' }}>Copied</span>
            </>
          ) : (
            <>
              <Copy size={12} />
              <span>Copy</span>
            </>
          )}
        </button>
      </div>

      {/* Code body with line numbers */}
      <div
        style={{
          maxHeight,
          overflowY: 'auto',
          padding: '12px 0',
          fontFamily: 'var(--font-mono)',
          fontSize: '12.5px',
          lineHeight: '1.6',
          color: '#1e293b',
          backgroundColor: '#ffffff',
          display: 'flex',
        }}
      >
        {/* Line numbers */}
        <div
          style={{
            userSelect: 'none',
            textAlign: 'right',
            padding: '0 12px',
            color: '#94a3b8',
            borderRight: '1px solid #f1f5f9',
            minWidth: '40px',
            fontSize: '11px',
          }}
        >
          {lines.map((_, idx) => (
            <div key={idx}>{idx + 1}</div>
          ))}
        </div>

        {/* Code content */}
        <pre
          style={{
            flex: 1,
            margin: 0,
            padding: '0 16px',
            overflowX: 'auto',
            fontFamily: 'inherit',
          }}
        >
          <code>{code}</code>
        </pre>
      </div>
    </div>
  );
};
