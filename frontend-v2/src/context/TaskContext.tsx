/**
 * TaskContext — Global Task State Management
 *
 * Lifts mining and backtest task state, WebSocket connection, and polling logic
 * to App level, so running state is not lost when switching pages.
 */

import React, { createContext, useContext, useState, useCallback, useRef, useEffect } from 'react';
import type {
  Task,
  TaskConfig,
  LogEntry,
  RealtimeMetrics,
  TimeSeriesData,
  WsMessage,
} from '@/types';
import { generateId } from '@/utils';
import {
  startMining as apiStartMining,
  getMiningStatus,
  cancelMining as apiCancelMining,
  startBacktest as apiStartBacktest,
  getBacktestStatus,
  cancelBacktest as apiCancelBacktest,
  connectMiningWs,
  healthCheck,
} from '@/services/api';
import type { BacktestStartParams } from '@/services/api';
import { getDefaultMiningDirection } from '@/utils/miningDirections';

// ========================== Backtest local type ==========================

export interface BacktestTask {
  taskId: string;
  status: string;
  progress: {
    phase: string;
    progress: number;
    message: string;
    timestamp: string;
  };
  logs: LogEntry[];
  metrics: Record<string, any>;
  config: Record<string, any>;
  createdAt: string;
  updatedAt: string;
}

// ========================== Context Value ==========================

interface TaskContextValue {
  // Backend health
  backendAvailable: boolean | null;

  // ---- Mining ----
  miningTask: Task | null;
  miningEquityCurve: TimeSeriesData[];
  miningDrawdownCurve: TimeSeriesData[];
  miningIcTimeSeries: TimeSeriesData[];
  startMining: (config: TaskConfig) => void;
  stopMining: () => void;
  resetMiningTask: () => void;

  // ---- Backtest ----
  backtestTask: BacktestTask | null;
  backtestLogs: LogEntry[];
  startBacktestTask: (params: BacktestStartParams) => Promise<void>;
  stopBacktestTask: () => void;
}

const TaskContext = createContext<TaskContextValue | null>(null);

// ========================== Provider ==========================

export const TaskProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  // ---- Backend health ----
  const [backendAvailable, setBackendAvailable] = useState<boolean | null>(null);

  useEffect(() => {
    healthCheck()
      .then(() => setBackendAvailable(true))
      .catch(() => setBackendAvailable(false));
  }, []);

  // ==================================================================
  // MINING
  // ==================================================================
  const [miningTask, setMiningTask] = useState<Task | null>(null);
  const [miningEquityCurve, setMiningEquityCurve] = useState<TimeSeriesData[]>([]);
  const [miningDrawdownCurve, setMiningDrawdownCurve] = useState<TimeSeriesData[]>([]);
  const [miningIcTimeSeries, setMiningIcTimeSeries] = useState<TimeSeriesData[]>([]);

  const miningWsRef = useRef<WebSocket | null>(null);
  const miningPollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // Display only time series actually returned by the backend.
  const updateMiningSeries = useCallback((data: any) => {
    const result = data?.result || data;
    const validSeries = (value: unknown): value is TimeSeriesData[] =>
      Array.isArray(value) && value.every((point) =>
        point && typeof point.date === 'string' && Number.isFinite(point.value));
    if (validSeries(result?.equityCurve)) setMiningEquityCurve(result.equityCurve);
    if (validSeries(result?.drawdownCurve)) setMiningDrawdownCurve(result.drawdownCurve);
    if (validSeries(result?.icTimeSeries)) setMiningIcTimeSeries(result.icTimeSeries);
  }, []);

  // WS handler for mining
  const handleMiningWsMessage = useCallback(
    (msg: WsMessage) => {
      updateMiningSeries(msg.data);
      setMiningTask((prev) => {
        if (!prev) return prev;
        const updated = { ...prev };
        switch (msg.type) {
          case 'progress':
            updated.progress = msg.data;
            updated.status = msg.data.phase === 'completed' ? 'completed' : 'running';
            break;
          case 'log':
            // Increased frontend log retention limit from 99 to 2000
            updated.logs = [...(updated.logs || []).slice(-2000), msg.data as LogEntry];
            
            // Try to extract factor from log message to show it immediately in the list
            // Pattern: "Added new factor: {name} with expression: {expr}"
            const logMsg = (msg.data as LogEntry).message;
            if (logMsg && logMsg.includes("Added new factor:")) {
              const match = logMsg.match(/Added new factor: (.+?) with expression: (.+)/);
              if (match) {
                const [_, name, expr] = match;
                const currentMetrics = updated.metrics || {
                    ic: 0, icir: 0, rankIc: 0, rankIcir: 0,
                    annualReturn: 0, sharpeRatio: 0, maxDrawdown: 0,
                    totalFactors: 0, highQualityFactors: 0, mediumQualityFactors: 0, lowQualityFactors: 0,
                    top10Factors: []
                };
                
                const currentFactors = currentMetrics.top10Factors || [];
                // Avoid duplicates
                if (!currentFactors.some((f: any) => f.factorName === name)) {
                    const newFactor = {
                        factorName: name,
                        factorExpression: expr,
                        rankIc: 0, rankIcir: 0, ic: 0, icir: 0,
                        annualReturn: 0, sharpeRatio: 0, maxDrawdown: 0, calmarRatio: 0,
                        cumulativeCurve: []
                    };
                    
                    // Recalculate best metrics from the updated list
                    const updatedFactors = [newFactor, ...currentFactors];
                    const bestFactor = updatedFactors.reduce((best, current) => {
                        // Prioritize RankIC, but handle potential missing values
                        const bestScore = best.rankIc || 0;
                        const currentScore = current.rankIc || 0;
                        return currentScore > bestScore ? current : best;
                    }, updatedFactors[0]);

                    updated.metrics = {
                        ...currentMetrics,
                        totalFactors: (currentMetrics.totalFactors || 0) + 1,
                        // Prepend new factor to the list so user sees it immediately
                        top10Factors: updatedFactors,
                        // Update best factor metrics
                        factorName: bestFactor.factorName,
                        rankIc: bestFactor.rankIc ?? 0,
                        rankIcir: bestFactor.rankIcir ?? 0,
                        ic: bestFactor.ic ?? 0,
                        icir: bestFactor.icir ?? 0,
                        annualReturn: bestFactor.annualReturn ?? 0,
                        sharpeRatio: bestFactor.sharpeRatio ?? 0,
                        maxDrawdown: bestFactor.maxDrawdown ?? 0,
                    };
                }
              }
            }
            break;
          case 'metrics':
            updated.metrics = {
              ...(updated.metrics || {} as RealtimeMetrics),
              ...msg.data as RealtimeMetrics
            };
            break;
          case 'result':
            updated.status = msg.data.status === 'completed' ? 'completed' : 'failed';
            if (msg.data.metrics) updated.metrics = msg.data.metrics;
            break;
          case 'error':
            updated.status = 'failed';
            updated.logs = [
              ...(updated.logs || []),
              {
                id: generateId(),
                timestamp: new Date().toISOString(),
                level: 'error',
                message: msg.data.error || 'Unknown error',
              },
            ];
            break;
        }
        updated.updatedAt = new Date().toISOString();
        return updated;
      });
    },
    [updateMiningSeries],
  );

  // Start mining (real backend)
  const startRealMining = useCallback(
    async (config: TaskConfig) => {
      miningWsRef.current?.close();
      if (miningPollingRef.current) clearInterval(miningPollingRef.current);
      try {
        // Load defaults from localStorage
        let defaults: any = {};
        const savedConfig = localStorage.getItem('quantaalpha_config');
        if (savedConfig) {
          try {
            defaults = JSON.parse(savedConfig);
          } catch {}
        }

        const direction =
          config.useCustomMiningDirection
            ? (getDefaultMiningDirection() || '价量因子挖掘')
            : (config.userInput && config.userInput.trim()) || getDefaultMiningDirection() || '价量因子挖掘';
        const resp = await apiStartMining({
          direction,
          numDirections: config.numDirections || defaults.defaultNumDirections || 2,
          maxRounds: config.maxRounds || defaults.defaultMaxRounds || 3,
          librarySuffix: config.librarySuffix || defaults.defaultLibrarySuffix || undefined,
          qualityGateEnabled: config.qualityGateEnabled ?? defaults.qualityGateEnabled ?? true,
          parallelEnabled: config.parallelExecution ?? defaults.parallelExecution ?? false,
        });
        if (!resp.success || !resp.data) throw new Error(resp.error || 'Failed');

        const taskData = resp.data.task as Task;
        // Initialize metrics with empty top10Factors to avoid stale data
        if (taskData.metrics) {
            taskData.metrics.top10Factors = [];
            taskData.metrics.totalFactors = 0;
            taskData.metrics.highQualityFactors = 0;
            taskData.metrics.mediumQualityFactors = 0;
            taskData.metrics.lowQualityFactors = 0;
        }
        setMiningTask(taskData);
        setMiningEquityCurve([]);
        setMiningDrawdownCurve([]);
        setMiningIcTimeSeries([]);

        // WebSocket
        const ws = connectMiningWs(
          resp.data.taskId,
          handleMiningWsMessage,
          () => {
            getMiningStatus(resp.data!.taskId).then((r) => {
              if (r.data?.task) setMiningTask(r.data.task as Task);
            });
          },
        );
        miningWsRef.current = ws;

        // Polling fallback
        miningPollingRef.current = setInterval(async () => {
          try {
            const r = await getMiningStatus(resp.data!.taskId);
            if (r.data?.task) {
              const t = r.data.task as Task;
              updateMiningSeries(t.result);
              setMiningTask(t);
              if (t.status === 'completed' || t.status === 'failed') {
                clearInterval(miningPollingRef.current!);
                miningPollingRef.current = null;
              }
            }
          } catch {
            // ignore
          }
        }, 10000);
      } catch (err: unknown) {
        const timestamp = new Date().toISOString();
        const message = err instanceof Error ? err.message : '无法启动挖掘任务';
        setMiningTask({
          taskId: generateId(), status: 'failed', config,
          progress: { phase: 'parsing', currentRound: 0,
            totalRounds: config.maxRounds || 3, progress: 0, message, timestamp },
          logs: [{ id: generateId(), timestamp, level: 'error', message }],
          createdAt: timestamp, updatedAt: timestamp,
        });
        setMiningEquityCurve([]);
        setMiningDrawdownCurve([]);
        setMiningIcTimeSeries([]);
      }
    },
    [handleMiningWsMessage, updateMiningSeries],
  );

  // Never silently substitute a simulated task for a failed research request.
  const startMining = useCallback(
    (config: TaskConfig) => { void startRealMining(config); },
    [startRealMining],
  );

  // Stop mining
  const stopMining = useCallback(async () => {
    if (!miningTask) return;
    miningWsRef.current?.close();
    miningWsRef.current = null;
    if (miningPollingRef.current) {
      clearInterval(miningPollingRef.current);
      miningPollingRef.current = null;
    }
    if (backendAvailable) {
      try {
        await apiCancelMining(miningTask.taskId);
      } catch {
        // ignore
      }
    }
    setMiningTask((prev) => (prev ? { ...prev, status: 'failed' } : prev));
  }, [miningTask, backendAvailable]);

  // Reset mining task
  const resetMiningTask = useCallback(() => {
    // Ensure stopped first
    miningWsRef.current?.close();
    miningWsRef.current = null;
    if (miningPollingRef.current) {
      clearInterval(miningPollingRef.current);
      miningPollingRef.current = null;
    }
    setMiningTask(null);
    setMiningEquityCurve([]);
    setMiningDrawdownCurve([]);
    setMiningIcTimeSeries([]);
  }, []);

  // ==================================================================
  // BACKTEST
  // ==================================================================
  const [backtestTask, setBacktestTask] = useState<BacktestTask | null>(null);
  const [backtestLogs, setBacktestLogs] = useState<LogEntry[]>([]);

  const backtestWsRef = useRef<WebSocket | null>(null);
  const backtestPollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // WS handler for backtest
  // IMPORTANT: setBacktestLogs must NOT be inside setBacktestTask's updater function,
  // because React StrictMode double-invokes updater functions in development mode,
  // which would cause every log entry to be added twice.
  const handleBacktestWsMessage = useCallback((msg: WsMessage) => {
    switch (msg.type) {
      case 'progress':
        setBacktestTask((prev) => {
          if (!prev) return prev;
          return { ...prev, progress: msg.data, updatedAt: new Date().toISOString() };
        });
        break;
      case 'log':
        setBacktestLogs((l) => [...l.slice(-499), msg.data as LogEntry]);
        break;
      case 'metrics':
        setBacktestTask((prev) => {
          if (!prev) return prev;
          return { ...prev, metrics: msg.data, updatedAt: new Date().toISOString() };
        });
        break;
      case 'result':
        setBacktestTask((prev) => {
          if (!prev) return prev;
          return {
            ...prev,
            status: msg.data.status === 'completed' ? 'completed' : 'failed',
            metrics: msg.data.metrics || prev.metrics,
            updatedAt: new Date().toISOString(),
          };
        });
        break;
      case 'error':
        setBacktestTask((prev) => {
          if (!prev) return prev;
          return { ...prev, status: 'failed', updatedAt: new Date().toISOString() };
        });
        break;
    }
  }, []);

  // Start backtest
  const startBacktestTask = useCallback(
    async (params: BacktestStartParams) => {
      setBacktestLogs([]);
      const resp = await apiStartBacktest(params);
      if (!resp.success || !resp.data) throw new Error(resp.error || 'Failed');

      const taskData = resp.data.task as unknown as BacktestTask;
      setBacktestTask(taskData);

      // WebSocket
      const ws = connectMiningWs(
        resp.data.taskId,
        handleBacktestWsMessage,
        () => {
          getBacktestStatus(resp.data!.taskId).then((r) => {
            if (r.data?.task) setBacktestTask(r.data.task as unknown as BacktestTask);
          });
        },
      );
      backtestWsRef.current = ws;

      // Polling fallback
      backtestPollingRef.current = setInterval(async () => {
        try {
          const r = await getBacktestStatus(resp.data!.taskId);
          if (r.data?.task) {
            const t = r.data.task as unknown as BacktestTask;

            // Always sync progress from polling (in case WS missed updates)
            setBacktestTask((prev) => {
              if (!prev) return t;
              return {
                ...prev,
                status: t.status,
                progress: t.progress || prev.progress,
                metrics: (t.metrics && Object.keys(t.metrics).length > 0) ? t.metrics : prev.metrics,
                updatedAt: t.updatedAt,
              };
            });

            if (t.status === 'completed' || t.status === 'failed' || t.status === 'cancelled') {
              // Final update: sync task + logs from backend (in case WS missed some)
              setBacktestTask(t);
              if (t.logs && t.logs.length > 0) {
                setBacktestLogs(t.logs.slice(-500));
              }
              clearInterval(backtestPollingRef.current!);
              backtestPollingRef.current = null;
            }
          }
        } catch {
          // ignore
        }
      }, 5000);
    },
    [handleBacktestWsMessage],
  );

  // Stop backtest
  const stopBacktestTask = useCallback(async () => {
    if (!backtestTask) return;
    backtestWsRef.current?.close();
    backtestWsRef.current = null;
    if (backtestPollingRef.current) {
      clearInterval(backtestPollingRef.current);
      backtestPollingRef.current = null;
    }
    try {
      await apiCancelBacktest(backtestTask.taskId);
    } catch {
      // ignore
    }
    setBacktestTask((prev) => (prev ? { ...prev, status: 'cancelled' } : prev));
  }, [backtestTask]);

  // ==================================================================
  // Context value
  // ==================================================================
  const value: TaskContextValue = {
    backendAvailable,
    // Mining
    miningTask,
    miningEquityCurve,
    miningDrawdownCurve,
    miningIcTimeSeries,
    startMining,
    stopMining,
    resetMiningTask,

    // ---- Backtest ----
    backtestTask,
    backtestLogs,
    startBacktestTask,
    stopBacktestTask,
  };

  return <TaskContext.Provider value={value}>{children}</TaskContext.Provider>;
};

// ========================== Hook ==========================

export function useTaskContext(): TaskContextValue {
  const ctx = useContext(TaskContext);
  if (!ctx) throw new Error('useTaskContext must be used inside <TaskProvider>');
  return ctx;
}
