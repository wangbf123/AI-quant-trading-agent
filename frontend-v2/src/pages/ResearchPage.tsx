import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Area, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { ArrowRight, CheckCircle2, Download, FileJson, FlaskConical, History, Layers, Loader2, LockKeyhole, Play, RefreshCw, ShieldCheck } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { createResearchDemo, createResearchProtocol, exportResearchProtocol, finalizeResearchProtocol, freezeResearchCandidate, getResearchOverview, runResearchProtocol } from '@/services/research';
import type { ResearchMemory, ResearchOverview, ResearchRecord, ResearchRunConfig } from '@/services/research';

const stateNames: Record<string, string> = { draft: '待研究', running: '研究中', researched: '验证完成', frozen: '候选已冻结', finalizing: '样本外评估中', finalized: '研究已封存', failed: '研究失败', interrupted: '任务已中断', finalization_failed: '最终评估中断' };
const categoryNames: Record<string, string> = { cost_drag: '成本侵蚀', negative_net_return: '净超额为负', high_drawdown: '回撤超限', regime_instability: '子期不稳定', execution_failure: '执行失败' };
const numeric = (v: unknown): number | null => typeof v === 'number' && Number.isFinite(v) ? v : null;
const percent = (v: unknown) => numeric(v) === null ? '—' : `${((v as number) * 100).toFixed(2)}%`;
const fixed = (v: unknown) => numeric(v) === null ? '—' : (v as number).toFixed(2);
const object = (v: unknown): ResearchRecord => v && typeof v === 'object' && !Array.isArray(v) ? v as ResearchRecord : {};

export const ResearchPage: React.FC = () => {
  const [overview, setOverview] = useState<ResearchOverview>({ protocols: [], memories: [], capabilities: {} });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [config, setConfig] = useState<ResearchRunConfig>({ budget: 4, seed: 42, use_memory: true, run_ablation: false, planner: 'demo', objective: '寻找扣除交易成本后更稳健的日频因子组合' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmFinal, setConfirmFinal] = useState(false);
  const importRef = useRef<HTMLInputElement>(null);
  const selected = overview.protocols.find(p => p.id === selectedId) ?? overview.protocols[0];
  const running = overview.protocols.some(p => ['running', 'finalizing'].includes(p.state));
  const result = selected?.result;
  const evaluation = result?.holdout ?? result?.validation;
  const metrics = evaluation?.metrics ?? {};
  const trials = result?.trials ?? [];
  const events = selected?.task?.events?.length ? selected.task.events : result?.events ?? [];
  const memories: ResearchMemory[] = result?.memories ?? overview.memories;
  const chart = (evaluation?.equity ?? []).map(row => ({ ...row, date: String(row.date).slice(0, 10), strategy: numeric(row.equity) === null ? null : ((row.equity as number) - 1) * 100, benchmarkReturn: numeric(row.benchmark) === null ? null : ((row.benchmark as number) - 1) * 100 }));
  const ablation = object(result?.ablation);

  const refresh = useCallback(async () => {
    const data = await getResearchOverview();
    setOverview(data);
    return data;
  }, []);

  useEffect(() => { refresh().catch(e => setError(String(e.message))); }, [refresh]);
  useEffect(() => {
    if (!running) return;
    const interval = window.setInterval(() => { refresh().catch(e => setError(String(e.message))); }, 2000);
    return () => window.clearInterval(interval);
  }, [refresh, running]);

  const act = async (action: () => Promise<unknown>) => {
    setBusy(true); setError(null);
    try { await action(); await refresh(); } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  };
  const launch = () => act(async () => {
    const response = await createResearchDemo(config);
    setSelectedId(response.protocol.id);
  });
  const importProtocol = async (file?: File) => {
    if (!file) return;
    await act(async () => {
      const payload = JSON.parse(await file.text());
      const response = await createResearchProtocol(payload);
      setSelectedId(response.protocol.id);
    });
    if (importRef.current) importRef.current.value = '';
  };

  return (
    <div className="space-y-7 relative z-10 max-w-[1440px] mx-auto">
      <section className="flex flex-col lg:flex-row lg:items-end justify-between gap-5">
        <div>
          <div className="flex gap-2 items-center text-xs font-mono text-primary mb-3 tracking-widest"><span className="h-2 w-2 bg-primary rounded-full" /> RESEARCH / EVIDENCE / ITERATION</div>
          <h2 className="text-3xl md:text-4xl font-bold tracking-tight">让每一次研究，都留下证据。</h2>
          <p className="text-muted-foreground mt-3 max-w-2xl">沿用 QuantaAlpha 与 Qlib 的研究底座，加入经济性失败记忆、等预算对照和封存样本外验证。</p>
        </div>
        <div className="flex gap-2 shrink-0">
          <Button variant="outline" size="sm" disabled={busy} onClick={() => act(refresh)} aria-label="刷新研究"><RefreshCw className="w-4 h-4 mr-2" />刷新</Button>
          <Button variant="outline" size="sm" onClick={() => importRef.current?.click()}><FileJson className="w-4 h-4 mr-2" />导入协议</Button>
          <input ref={importRef} type="file" accept="application/json,.json" className="hidden" aria-label="导入研究协议 JSON" onChange={e => { void importProtocol(e.target.files?.[0]); }} />
        </div>
      </section>

      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="px-3 py-1.5 rounded-full border bg-white/80">Qlib {overview.capabilities.qlib ? '已就绪' : '待连接'}</span>
        <span className="px-3 py-1.5 rounded-full border bg-white/80">LLM {overview.capabilities.llm_configured ? '已配置' : '未配置 · 演示无需密钥'}</span>
        <span className="px-3 py-1.5 rounded-full border bg-white/80">{overview.capabilities.postgres ? 'PostgreSQL' : 'SQLite'} 持久化</span>
        <span className="px-3 py-1.5 rounded-full border border-amber-200 bg-amber-50 text-amber-800">{result?.provenance?.source === 'synthetic' || !selected ? '演示使用合成数据 · 不作为市场盈利证据' : '用户数据 · 结果受研究协议约束'}</span>
      </div>
      {error && <div role="alert" className="rounded-xl border border-red-200 bg-red-50 text-red-800 p-4 text-sm">{error}</div>}
      {selected?.task?.error && <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800 whitespace-pre-wrap">{selected.task.error}</div>}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: '净超额年化收益', value: percent(metrics.annualized_return), detail: result?.holdout ? 'Final holdout · 成本后' : 'Research validation · 成本后' },
          { label: '超额信息比率', value: fixed(metrics.information_ratio), detail: 'Qlib 日频风险评估' },
          { label: '经济性失败记忆', value: String(memories.length), detail: '仅来自研究验证窗口' },
          { label: '最终样本外状态', value: result?.holdout ? '已评估' : '已封存', detail: selected ? stateNames[selected.state] ?? selected.state : '等待首个实验' },
        ].map(item => <Card key={item.label} className="border-white bg-white/90 shadow-sm"><CardContent className="pt-5"><p className="text-xs text-muted-foreground">{item.label}</p><p className="text-2xl md:text-3xl font-semibold mt-3 tabular-nums">{item.value}</p><p className="text-xs text-muted-foreground mt-2">{item.detail}</p></CardContent></Card>)}
      </div>

      <div className="grid lg:grid-cols-[300px_minmax(0,1fr)] gap-6">
        <aside className="space-y-5">
          <Card><CardHeader><CardTitle className="flex items-center gap-2"><FlaskConical className="w-4 h-4 text-primary" />启动研究</CardTitle></CardHeader><CardContent className="space-y-4 text-sm">
            <label className="block space-y-2"><span>研究目标</span><textarea className="w-full rounded-lg border p-3 bg-white text-sm min-h-20" value={config.objective} onChange={e => setConfig({ ...config, objective: e.target.value })} /></label>
            <label className="block space-y-2"><span>规划器</span><select className="w-full rounded-lg border p-2.5 bg-white" value={config.planner} onChange={e => setConfig({ ...config, planner: e.target.value as 'demo' | 'llm' })}><option value="demo">确定性演示规划器</option><option value="llm" disabled={!overview.capabilities.llm_configured}>LLM · 上游 APIBackend</option></select></label>
            <div className="grid grid-cols-2 gap-3"><label className="space-y-2">每组预算<input aria-label="每组实验预算" className="w-full rounded-lg border p-2.5 mt-2" type="number" min="2" max="20" value={config.budget} onChange={e => setConfig({ ...config, budget: Math.min(20, Math.max(2, Number(e.target.value))) })} /></label><label className="space-y-2">随机种子<input aria-label="随机种子" className="w-full rounded-lg border p-2.5 mt-2" type="number" min="0" value={config.seed} onChange={e => setConfig({ ...config, seed: Math.max(0, Number(e.target.value)) })} /></label></div>
            <label className="flex items-center gap-2"><input type="checkbox" checked={config.use_memory} onChange={e => setConfig({ ...config, use_memory: e.target.checked })} />启用经济性失败记忆</label>
            <label className="flex items-center gap-2"><input type="checkbox" checked={config.run_ablation} onChange={e => setConfig({ ...config, run_ablation: e.target.checked })} />运行等预算消融（两组实验）</label>
            <Button variant="primary" className="w-full" disabled={busy || running || !overview.capabilities.qlib} onClick={launch}>{busy || running ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Play className="w-4 h-4 mr-2" />}启动本地演示研究</Button>
            {selected && ['draft', 'researched', 'failed', 'interrupted'].includes(selected.state) && <Button variant="outline" className="w-full" disabled={busy || running} onClick={() => act(() => runResearchProtocol(selected.id, config))}>运行当前数据协议<ArrowRight className="w-4 h-4 ml-2" /></Button>}
            <p className="text-xs text-muted-foreground leading-relaxed">演示是真实的 Qlib / LightGBM 训练和回测，候选由固定种子生成。真实 LLM 因子生成也可使用原有「因子挖掘」流程。</p>
          </CardContent></Card>
          <Card><CardHeader><CardTitle className="flex items-center gap-2"><History className="w-4 h-4" />实验记录 <span className="text-sm text-muted-foreground">{overview.protocols.length}</span></CardTitle></CardHeader><CardContent className="space-y-2 max-h-80 overflow-auto">
            {!overview.protocols.length && <p className="text-sm text-muted-foreground">首次研究完成后，协议、候选与指标将保存在这里。</p>}
            {overview.protocols.map(p => <button key={p.id} onClick={() => setSelectedId(p.id)} className={`text-left w-full rounded-lg border p-3 transition-colors ${selected?.id === p.id ? 'bg-primary/5 border-primary/30' : 'hover:bg-secondary/60'}`}><div className="text-sm font-medium truncate">{p.name}</div><div className="flex justify-between mt-2 text-xs text-muted-foreground"><span>{stateNames[p.state] ?? p.state}</span><span className="font-mono">{p.id.slice(0, 8)}</span></div></button>)}
          </CardContent></Card>
        </aside>

        <div className="min-w-0 space-y-6">
          <Card><CardHeader className="flex-row justify-between items-start"><div><CardTitle>收益轨迹</CardTitle><p className="text-xs text-muted-foreground mt-2">{result?.holdout ? '冻结候选 · 最终样本外' : '当前最优候选 · 研究验证窗'} · 策略净值与基准的实际复利收益</p></div>{selected && <Button variant="ghost" size="sm" onClick={() => act(() => exportResearchProtocol(selected.id))}><Download className="w-4 h-4 mr-1" />证据包</Button>}</CardHeader><CardContent>
            {chart.length ? <div className="h-72 w-full"><ResponsiveContainer width="100%" height="100%"><ComposedChart data={chart} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}><defs><linearGradient id="researchEquity" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#4f46e5" stopOpacity={0.2} /><stop offset="100%" stopColor="#4f46e5" stopOpacity={0} /></linearGradient></defs><CartesianGrid strokeDasharray="3 5" vertical={false} stroke="#e5e7eb" /><XAxis dataKey="date" tick={{ fontSize: 10 }} minTickGap={45} axisLine={false} tickLine={false} /><YAxis tickFormatter={value => `${value}%`} tick={{ fontSize: 11 }} axisLine={false} tickLine={false} /><Tooltip formatter={(value: number) => `${value.toFixed(2)}%`} contentStyle={{ borderRadius: 10, border: '1px solid #e5e7eb' }} /><Legend iconType="plainline" wrapperStyle={{ fontSize: 12, paddingTop: 10 }} /><Area type="monotone" dataKey="strategy" name="策略（成本后）" stroke="#4f46e5" strokeWidth={2} fill="url(#researchEquity)" isAnimationActive={false} /><Line type="monotone" dataKey="benchmarkReturn" name="市场基准" stroke="#94a3b8" strokeWidth={1.5} dot={false} strokeDasharray="4 4" isAnimationActive={false} /></ComposedChart></ResponsiveContainer></div> : <div className="h-64 rounded-xl border border-dashed flex flex-col justify-center items-center text-center p-6 bg-slate-50/50"><Layers className="w-9 h-9 text-primary/40 mb-4" /><p className="font-medium">从一个可复现的实验开始</p><p className="text-sm text-muted-foreground max-w-md mt-2">启动本地演示，或导入指向现有 Qlib 数据的协议。只有本次任务生成的真实回测曲线会显示在这里。</p></div>}
          </CardContent></Card>

          <Card><CardHeader><CardTitle className="flex items-center gap-2"><ShieldCheck className="w-4 h-4 text-primary" />样本外研究协议</CardTitle></CardHeader><CardContent>
            <div className="grid sm:grid-cols-4 gap-2">{[['train', '01 训练'], ['tune', '02 调参'], ['validation', '03 研究验证'], ['holdout', '04 最终封存']].map(([key, name]) => <div key={key} className={`rounded-lg p-3 border ${key === 'holdout' ? 'bg-slate-900 border-slate-900 text-white' : 'bg-slate-50'}`}><div className="text-xs font-medium flex gap-1.5 items-center">{key === 'holdout' && <LockKeyhole className="w-3 h-3" />}{name}</div><div className="font-mono text-[11px] mt-3 leading-relaxed">{Array.isArray(selected?.protocol[key]) ? (selected?.protocol[key] as string[]).join(' → ') : '等待协议'}</div></div>)}</div>
            <div className="text-xs text-muted-foreground mt-3">窗口之间剔除至少 2 个交易日以隔离前瞻标签。成本、数据指纹及候选在最终评估前固定。</div>
            {selected && <div className="flex flex-wrap gap-3 items-center mt-4 pt-4 border-t"><span className="text-xs font-mono text-muted-foreground mr-auto">DATA {String(selected.protocol.dataset_fingerprint).slice(0, 16)}…</span><Button size="sm" variant="primary" disabled={busy || selected.state !== 'frozen'} onClick={() => setConfirmFinal(true)}><LockKeyhole className="w-3.5 h-3.5 mr-2" />评估封存样本外</Button>{result?.holdout && <span className="text-xs text-emerald-700 flex items-center gap-1"><CheckCircle2 className="w-4 h-4" />已评估一次，禁止回流记忆</span>}</div>}
          </CardContent></Card>
        </div>
      </div>

      <Card><CardHeader><CardTitle>候选与实验对比</CardTitle><p className="text-xs text-muted-foreground">在研究验证窗比较成本后表现，再冻结一个候选；指标保留 Qlib 的超额收益口径。</p></CardHeader><CardContent><div className="overflow-x-auto"><table className="w-full text-sm text-left"><thead><tr className="border-b text-xs text-muted-foreground"><th className="pb-3">候选</th><th className="pb-3">净超额年化</th><th className="pb-3">信息比率</th><th className="pb-3">超额最大回撤</th><th className="pb-3">经济性失败</th><th className="pb-3">操作</th></tr></thead><tbody>{trials.map(trial => <tr key={trial.id} className="border-b last:border-0"><td className="py-4 pr-4"><p className="font-medium">{String(trial.strategy?.name ?? trial.id)}</p><p className="text-xs text-muted-foreground mt-1 max-w-sm" title={trial.reasoning}>{trial.reasoning}</p></td><td className="tabular-nums">{percent(trial.metrics?.annualized_return)}</td><td className="tabular-nums">{fixed(trial.metrics?.information_ratio)}</td><td className="tabular-nums">{percent(trial.metrics?.max_drawdown)}</td><td className="max-w-44 pr-3">{(trial.failure_tags ?? []).map(tag => <span key={tag} className="inline-block text-[10px] rounded bg-amber-50 text-amber-800 px-2 py-1 m-0.5">{categoryNames[tag] ?? tag}</span>)}{trial.status === 'failed' && <span className="text-xs text-red-600">执行失败</span>}</td><td><Button size="sm" variant="outline" disabled={busy || selected?.state !== 'researched' || trial.status !== 'completed'} onClick={() => selected && act(() => freezeResearchCandidate(selected.id, trial.id))}>冻结候选</Button></td></tr>)}</tbody></table>{!trials.length && <p className="text-sm text-muted-foreground py-7 text-center">尚无完成的候选实验。运行日志会在下方实时更新。</p>}</div></CardContent></Card>

      {!!result?.ablation && <Card><CardHeader><CardTitle>等预算消融</CardTitle><p className="text-xs text-muted-foreground">相同数据、成本、随机种子和每组实验次数；两组都不访问最终测试集。</p></CardHeader><CardContent><div className="grid md:grid-cols-2 gap-4">{[['with_memory', '有失败记忆'], ['without_memory', '无失败记忆']].map(([key, title]) => { const arm = object(ablation[key]); const armMetrics = object(arm.metrics); return <div key={key} className="p-5 rounded-xl bg-slate-50 border"><p className="font-semibold">{title}</p><div className="flex justify-between mt-4 text-sm"><span>净超额年化 {percent(armMetrics.annualized_return)}</span><span>IR {fixed(armMetrics.information_ratio)}</span></div><p className="text-xs text-muted-foreground mt-3">已执行 {String(arm.evaluations ?? '—')} / {String(arm.budget ?? '—')} 次 · Seed {String(arm.seed ?? '—')}</p></div>; })}</div><p className="text-xs text-muted-foreground mt-3">单次种子结果用于工程验证；记忆是否有效仍需多种子及真实市场数据对照。</p></CardContent></Card>}

      <div className="grid lg:grid-cols-2 gap-6">
        <Card><CardHeader><CardTitle>经济性失败记忆</CardTitle><p className="text-xs text-muted-foreground">按数据、研究窗口与执行成本匹配，只有观察到的失败才会入库。</p></CardHeader><CardContent className="space-y-3 max-h-[360px] overflow-auto">{memories.slice(0, 30).map((memory, index) => <div key={String(memory.id ?? index)} className="border rounded-lg p-3"><div className="text-sm font-medium">{categoryNames[String(memory.category)] ?? memory.category}</div><p className="text-xs text-muted-foreground mt-1">{memory.description}</p><pre className="text-[10px] font-mono text-slate-500 mt-2 whitespace-pre-wrap break-all">{JSON.stringify(memory.evidence, null, 2)}</pre></div>)}{!memories.length && <p className="text-sm text-muted-foreground py-5">尚未观察到可记录的失败。不会为了填充页面生成记忆。</p>}</CardContent></Card>
        <Card><CardHeader><CardTitle>研究事件流</CardTitle><p className="text-xs text-muted-foreground">候选提议、回测反馈和协议状态均可追踪。</p></CardHeader><CardContent className="max-h-[360px] overflow-auto space-y-4">{events.slice(-40).reverse().map((event, index) => <div key={index} className="flex gap-3"><span className={`w-2 h-2 mt-1.5 shrink-0 rounded-full ${index === 0 && running ? 'bg-primary animate-pulse' : 'bg-primary/30'}`} /><div className="min-w-0"><p className="text-sm break-words">{event.message}</p><p className="text-[10px] font-mono text-muted-foreground mt-1">{event.timestamp}</p></div></div>)}{!events.length && <p className="text-sm text-muted-foreground py-5">等待研究任务。</p>}</CardContent></Card>
      </div>
      <p className="text-xs text-muted-foreground text-center pb-4">Agentic Quant Research Platform · QuantaAlpha 基座 / Qlib 执行 · 研究工具，不代表真实市场盈利能力</p>
      {confirmFinal && selected && <div className="fixed inset-0 z-50 bg-slate-950/40 backdrop-blur-sm flex items-center justify-center p-5" role="dialog" aria-modal="true" aria-labelledby="holdout-dialog-title"><div className="bg-white rounded-2xl shadow-xl p-7 max-w-md space-y-4"><LockKeyhole className="w-8 h-8 text-primary" /><h3 id="holdout-dialog-title" className="font-semibold text-xl">评估冻结候选的最终样本外表现</h3><p className="text-sm text-muted-foreground leading-relaxed">此协议只允许执行一次。数据和候选摘要已经固定；评估结果不会进入后续研究记忆，也不能在本协议中重新选参。</p><div className="flex justify-end gap-2"><Button variant="outline" onClick={() => setConfirmFinal(false)}>返回</Button><Button variant="primary" onClick={() => { setConfirmFinal(false); void act(() => finalizeResearchProtocol(selected.id)); }}>确认评估一次</Button></div></div></div>}
    </div>
  );
};
