import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ProjectProvider } from './context/ProjectContext';
import { MainLayout } from './layouts/MainLayout';
import { DashboardPage } from './pages/DashboardPage';
import { NewProjectPage } from './pages/NewProjectPage';
import { TaskGeneratorPage } from './pages/TaskGeneratorPage';
import { ReferenceSolutionPage } from './pages/ReferenceSolutionPage';
import { TestSuitePage } from './pages/TestSuitePage';
import { ValidationPage } from './pages/ValidationPage';
import { HarborExportPage } from './pages/HarborExportPage';
import { SettingsPage } from './pages/SettingsPage';

export const App: React.FC = () => {
  return (
    <ProjectProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<MainLayout />}>
            <Route index element={<DashboardPage />} />
            <Route path="new-project" element={<NewProjectPage />} />
            <Route path="analysis" element={<NewProjectPage />} />
            <Route path="task-generator" element={<TaskGeneratorPage />} />
            <Route path="solution" element={<ReferenceSolutionPage />} />
            <Route path="test-suite" element={<TestSuitePage />} />
            <Route path="validation" element={<ValidationPage />} />
            <Route path="export" element={<HarborExportPage />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ProjectProvider>
  );
};

export default App;
