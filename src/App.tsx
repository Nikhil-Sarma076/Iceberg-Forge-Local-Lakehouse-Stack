import React, { useState } from 'react';
import { AppShell, type Tab } from './components/AppShell';
import { ArchitectureView } from './pages/ArchitectureView';
import { CatalogExplorer } from './pages/CatalogExplorer';
import { QueryWorkspace } from './pages/QueryWorkspace';
import { JobsMonitor } from './pages/JobsMonitor';

export const App: React.FC = () => {
  const [tab, setTab] = useState<Tab>('architecture');

  return (
    <AppShell activeTab={tab} onTabChange={setTab}>
      {tab === 'architecture' && <ArchitectureView />}
      {tab === 'catalog' && <CatalogExplorer />}
      {tab === 'query' && <QueryWorkspace />}
      {tab === 'jobs' && <JobsMonitor />}
    </AppShell>
  );
};
