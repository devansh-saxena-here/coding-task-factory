import React, { createContext, useContext, useEffect, useState } from 'react';
import { RepoAnalysisResponse } from '../types/repo';
import { TaskResponse } from '../types/task';
import { SolutionResponse } from '../types/solution';
import { TestSuiteResponse } from '../types/testSuite';
import { ValidationReport } from '../types/validation';
import { taskService } from '../services/taskService';

interface ProjectContextValue {
  repoAnalysis: RepoAnalysisResponse | null;
  task: TaskResponse | null;
  solution: SolutionResponse | null;
  testSuite: TestSuiteResponse | null;
  validationReport: ValidationReport | null;
  setRepoAnalysis: (analysis: RepoAnalysisResponse | null) => void;
  setTask: (task: TaskResponse | null) => void;
  setSolution: (sol: SolutionResponse | null) => void;
  setTestSuite: (suite: TestSuiteResponse | null) => void;
  setValidationReport: (report: ValidationReport | null) => void;
  resetProject: () => void;
  backendHealth: 'online' | 'offline' | 'checking';
  checkBackendHealth: () => Promise<void>;
}

const ProjectContext = createContext<ProjectContextValue | undefined>(undefined);

export const ProjectProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [repoAnalysis, setRepoAnalysis] = useState<RepoAnalysisResponse | null>(null);
  const [task, setTask] = useState<TaskResponse | null>(null);
  const [solution, setSolution] = useState<SolutionResponse | null>(null);
  const [testSuite, setTestSuite] = useState<TestSuiteResponse | null>(null);
  const [validationReport, setValidationReport] = useState<ValidationReport | null>(null);
  const [backendHealth, setBackendHealth] = useState<'online' | 'offline' | 'checking'>('checking');

  const checkBackendHealth = async () => {
    try {
      const res = await taskService.checkHealth();
      if (res.status === 'healthy') {
        setBackendHealth('online');
      } else {
        setBackendHealth('offline');
      }
    } catch {
      setBackendHealth('offline');
    }
  };

  useEffect(() => {
    checkBackendHealth();
    const interval = setInterval(checkBackendHealth, 30000);
    return () => clearInterval(interval);
  }, []);

  const resetProject = () => {
    setRepoAnalysis(null);
    setTask(null);
    setSolution(null);
    setTestSuite(null);
    setValidationReport(null);
  };

  return (
    <ProjectContext.Provider
      value={{
        repoAnalysis,
        task,
        solution,
        testSuite,
        validationReport,
        setRepoAnalysis,
        setTask,
        setSolution,
        setTestSuite,
        setValidationReport,
        resetProject,
        backendHealth,
        checkBackendHealth,
      }}
    >
      {children}
    </ProjectContext.Provider>
  );
};

export const useProject = (): ProjectContextValue => {
  const context = useContext(ProjectContext);
  if (!context) {
    throw new Error('useProject must be used within a ProjectProvider');
  }
  return context;
};
