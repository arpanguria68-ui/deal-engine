import { useState } from 'react';
import { Dashboard } from './sections/Dashboard';
import { SettingsPage } from './sections/SettingsPage';
import { ChatWindow } from './sections/ChatWindow';
import { TaskBoardPage } from './sections/TaskBoardPage';
import { RAGDashboard } from './sections/RAGDashboard';
import { ChatSidebar } from '@/components/ChatSidebar';
import {
  Zap, LayoutDashboard, Settings, Activity, Briefcase, MessageSquare, Database,
  CheckCircle2, XCircle, Loader2
} from 'lucide-react';
import { Button } from '@/components/ui/button';

type Page = 'chat' | 'dashboard' | 'tasks' | 'knowledge' | 'settings';

function App() {
  const [page, setPage] = useState<Page>('chat');
  const [sysStatus, setSysStatus] = useState<null | 'checking' | 'ok' | 'error'>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  async function checkSystemStatus() {
    setSysStatus('checking');
    try {
      const res = await fetch('http://localhost:8005/health', { signal: AbortSignal.timeout(3000) });
      setSysStatus(res.ok ? 'ok' : 'error');
    } catch {
      setSysStatus('error');
    }
    setTimeout(() => setSysStatus(null), 5000);
  }

  const NAV_ITEMS: { id: Page; label: string; icon: typeof Zap }[] = [
    { id: 'chat', label: 'Chat', icon: MessageSquare },
    { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { id: 'tasks', label: 'Tasks', icon: Briefcase },
    { id: 'knowledge', label: 'Knowledge', icon: Database },
    { id: 'settings', label: 'Settings', icon: Settings },
  ];

  return (
    <div className="min-h-screen font-sans antialiased text-slate-900 dark:text-slate-50 bg-slate-50/50 dark:bg-slate-950/50">
      <header className="sticky top-0 z-10 flex h-16 items-center border-b bg-background/80 px-6 backdrop-blur-lg">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <Zap className="h-4 w-4" />
          </div>
          <h1 className="text-xl font-bold tracking-tight">DealForge AI</h1>
        </div>

        {/* Navigation */}
        <nav className="ml-8 flex items-center gap-1">
          {NAV_ITEMS.map(item => {
            const Icon = item.icon;
            return (
              <button
                key={item.id}
                id={`nav-${item.id}`}
                onClick={() => setPage(item.id)}
                className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all duration-200 ${page === item.id
                  ? 'bg-primary/10 text-primary shadow-sm'
                  : 'text-muted-foreground hover:text-foreground hover:bg-slate-100 dark:hover:bg-slate-800'
                  }`}
              >
                <Icon className="h-4 w-4" />
                {item.label}
              </button>
            );
          })}
        </nav>

        <div className="ml-auto flex items-center space-x-4">
          <div className="relative">
            <Button
              variant="outline"
              size="sm"
              onClick={checkSystemStatus}
              id="system-status-btn"
            >
              {sysStatus === 'checking' ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : sysStatus === 'ok' ? (
                <CheckCircle2 className="mr-2 h-4 w-4 text-green-500" />
              ) : sysStatus === 'error' ? (
                <XCircle className="mr-2 h-4 w-4 text-red-500" />
              ) : (
                <Activity className="mr-2 h-4 w-4" />
              )}
              {sysStatus === 'ok' ? 'Online' : sysStatus === 'error' ? 'Offline' : 'System Status'}
            </Button>
          </div>
          <Button size="sm" onClick={() => setPage('chat')} id="new-deal-btn">
            <Briefcase className="mr-2 h-4 w-4" />
            New Deal Analysis
          </Button>
        </div>
      </header>

      <main className="flex-1 p-6 md:p-8 pt-6 flex flex-col">
        <div className={page === 'chat' ? 'flex-1 flex h-full' : 'hidden'}>
          <ChatSidebar collapsed={sidebarCollapsed} onToggle={() => setSidebarCollapsed(!sidebarCollapsed)} />
          <div className="flex-1 flex flex-col">
            <ChatWindow />
          </div>
        </div>
        <div className={page === 'dashboard' ? 'flex-1' : 'hidden'}>
          <Dashboard onNavigate={setPage} />
        </div>
        <div className={page === 'tasks' ? 'flex-1' : 'hidden'}>
          <TaskBoardPage />
        </div>
        <div className={page === 'knowledge' ? 'flex-1' : 'hidden'}>
          <RAGDashboard />
        </div>
        <div className={page === 'settings' ? 'flex-1' : 'hidden'}>
          <SettingsPage />
        </div>
      </main>
    </div>
  );
}

export default App;
