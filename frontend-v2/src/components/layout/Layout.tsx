import React, { useId } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import { Sparkles, Database, BarChart3, Settings as SettingsIcon, FlaskConical, Compass } from 'lucide-react';
import { useTaskContext } from '@/context/TaskContext';

export type PageId = 'guide' | 'research' | 'home' | 'library' | 'backtest' | 'settings' | 'mining_dashboard';

interface LayoutProps {
  children: React.ReactNode;
  currentPage: PageId;
  onNavigate: (page: PageId) => void;
  showNavigation?: boolean;
}

export const Layout: React.FC<LayoutProps> = ({
  children,
  currentPage,
  onNavigate,
  showNavigation = true,
}) => {
  const { miningTask } = useTaskContext();
  const navId = useId();
  const reduced = useReducedMotion();

  // Helper to determine where 'Factor Mining' nav item should go
  const handleNavClick = (itemId: PageId) => {
    if (itemId === 'home') {
      // If there is an active mining task (running, completed, or failed), go to dashboard
      // Only go to home welcome screen if task is null or idle
      if (miningTask && miningTask.status !== 'idle') {
        onNavigate('mining_dashboard');
      } else {
        onNavigate('home');
      }
    } else {
      onNavigate(itemId);
    }
  };

  const navItems = [
    { id: 'guide' as const, label: '项目导览', icon: Compass },
    { id: 'research' as const, label: '研究协议', icon: FlaskConical, Compass },
    { id: 'home' as const, label: '因子挖掘', icon: Sparkles },
    { id: 'library' as const, label: '因子库', icon: Database },
    { id: 'backtest' as const, label: '回测', icon: BarChart3 },
    { id: 'settings' as const, label: '设置', icon: SettingsIcon },
  ];

  return (
    <div className="min-h-screen bg-background gradient-mesh">
      {/* Header */}
      <header className="fixed top-0 left-0 right-0 z-40 glass-strong border-b border-border/50">
        <div className="container mx-auto px-6 py-4">
          <div className="flex flex-col xl:flex-row xl:items-center justify-between gap-3">
            <div 
              className="flex items-center gap-3 cursor-pointer hover:opacity-80 transition-opacity"
              onClick={() => onNavigate('guide')}
            >
              <div className="relative">
                <div className="relative flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-purple-600">
                  <Sparkles className="h-6 w-6 text-white" />
                </div>
              </div>
              <div>
                <h1 className="text-sm sm:text-lg font-bold tracking-tight">Agentic Quant Research Platform</h1>
                <p className="text-xs text-muted-foreground">智能体量化研究 · 基于 QuantaAlpha</p>
              </div>
            </div>

            {/* Navigation */}
            <div className="flex items-center gap-4 overflow-x-auto">
              {showNavigation && (
                <nav className="flex items-center gap-1 sm:gap-2 whitespace-nowrap" aria-label="工作台导航">
                  {navItems.map((item) => {
                    const Icon = item.icon;
                    // Highlight 'Factor Mining' if we are on dashboard OR home
                    const isActive = currentPage === item.id || (item.id === 'home' && currentPage === 'mining_dashboard');
                    return (
                      <motion.button
                        whileHover={reduced ? undefined : { y: -2 }}
                        whileTap={reduced ? undefined : { scale: .97 }}
                        aria-current={isActive ? 'page' : undefined}
                        key={item.id}
                        onClick={() => handleNavClick(item.id)}
                        className={`relative isolate flex shrink-0 items-center gap-2 px-3 sm:px-4 py-2 rounded-lg transition-colors ${
                          isActive
                            ? 'text-primary-foreground'
                            : 'text-muted-foreground hover:text-foreground hover:bg-secondary/50'
                        }`}
                      >
                        {isActive && <motion.span layoutId={`${navId}-active`} transition={{ duration: reduced ? 0 : .3, type: 'spring', bounce: .15 }} className="absolute inset-0 -z-10 rounded-lg bg-primary shadow-sm" />}
                        <Icon className="h-4 w-4" />
                        <span className="text-sm font-medium">{item.label}</span>
                      </motion.button>
                    );
                  })}
                </nav>
              )}
            </div>
          </div>
        </div>
      </header>

      {/* Main Content — pb-48 ensures content is never hidden behind the fixed ChatInput */}
      <main className="pt-40 xl:pt-28 pb-24">
        <div className="container mx-auto px-6">{children}</div>
      </main>
    </div>
  );
};
