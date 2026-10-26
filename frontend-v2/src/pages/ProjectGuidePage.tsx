import { useEffect, useState } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { ArrowRight, BookOpen, BrainCircuit, Check, ChevronRight, Database, FlaskConical, GitBranch, Layers3, LockKeyhole, Pause, Play, RotateCcw, ShieldCheck, Sparkles } from 'lucide-react';
import type { PageId } from '@/components/layout/Layout';
import './project-guide.css';

type View = 'architecture' | 'loop' | 'protocol';
const nodes = [
  { id: 'data', title: '版本化数据', en: 'DATA FOUNDATION', sub: 'Qlib Provider · 数据指纹', icon: Database, x: 30, y: 140, color: '#0d9488', page: 'research' as PageId, description: '先确定研究材料，再讨论结论。行情来自 Qlib 本地数据源，使用实际文件指纹与交易日历标识版本，让同一个实验可以被重新计算。', detail: ['演示明确标记为合成行情', '数据改变即拒绝沿用旧协议', '保留费用、流动性与冲击假设'] },
  { id: 'agent', title: '研究 Agent', en: 'REASON & PROPOSE', sub: '假设 · 因子 · 下一轮实验', icon: BrainCircuit, x: 275, y: 60, color: '#6366f1', page: 'home' as PageId, description: 'Agent 负责提出可检验的研究假设、生成候选并安排实验。保留 QuantaAlpha 原有因子挖掘与进化流程，通过新增记忆钩子利用历史验证证据。', detail: ['StepFun / Anthropic Messages', '保留 OpenAI 兼容接口', '演示规划器与真实 LLM 明确区分'] },
  { id: 'engine', title: '确定性验证', en: 'EXECUTE & MEASURE', sub: 'Qlib · LightGBM · 回测', icon: FlaskConical, x: 520, y: 60, color: '#2563eb', page: 'backtest' as PageId, description: '计算引擎把研究想法变成可核查的实验。沿用 Qlib 的因子计算、模型训练与组合回测，记录成本前后的表现；LLM 不承担低延迟交易执行。', detail: ['训练与早停使用独立窗口', '手续费、成交量限制与冲击', '缺少真实组合指标即判为失败'] },
  { id: 'evidence', title: '实验与证据', en: 'COMPARE & EXPLAIN', sub: '净收益 · 风险 · 等预算对照', icon: GitBranch, x: 765, y: 140, color: '#0284c7', page: 'research' as PageId, description: '不仅保存最好的曲线，也保留候选为什么成功、为什么失败。使用相同数据、种子和实验预算对比有无记忆，导出完整研究证据。', detail: ['候选、配置与事件流可追踪', '展示成本后指标和负结果', '一次消融差异不等于统计结论'] },
  { id: 'store', title: '持久化记录', en: 'REPRODUCIBLE STATE', sub: 'SQLite / PostgreSQL · Redis/RQ', icon: Layers3, x: 30, y: 310, color: '#64748b', page: 'research' as PageId, description: '任务和协议状态独立于网页生命周期。默认无需额外服务即可运行，也支持 PostgreSQL 与 Redis/RQ Worker，避免页面刷新丢失实验。', detail: ['协议、任务、结果与记忆落库', '队列重复投递只执行一次', '可下载 JSON 证据包复核'] },
  { id: 'memory', title: '经济性失败记忆', en: 'LEARN FROM EVIDENCE', sub: '成本侵蚀 · 回撤 · 子期失效', icon: BookOpen, x: 350, y: 310, color: '#9333ea', page: 'research' as PageId, description: '把失败变成下一轮研究的上下文。记忆保存成本侵蚀、净超额为负等真实证据，并按数据、验证窗口和执行成本匹配，避免无关经验混用。', detail: ['只写入研究验证窗口的观察', '检索结果影响下一轮候选', '最终测试结果禁止回流记忆'] },
  { id: 'holdout', title: '封存样本外', en: 'FREEZE & FINALIZE', sub: '冻结候选 · 一次最终评估', icon: LockKeyhole, x: 765, y: 310, color: '#d97706', page: 'research' as PageId, description: '在看最终答案前固定选择。冻结候选与配置摘要后，只允许领取一次最终样本外评估；结果用于报告，不再用于本协议选参。', detail: ['核对数据、配置、成本与种子', '原子状态转换拒绝重复评估', '应用层研究纪律，保留审计轨迹'] },
];
const edges = [
  { from: 'data', to: 'agent', path: 'M230 180 C255 180 245 100 275 100' },
  { from: 'agent', to: 'engine', path: 'M475 100 L520 100' },
  { from: 'engine', to: 'evidence', path: 'M720 100 C750 100 738 180 765 180' },
  { from: 'evidence', to: 'memory', path: 'M865 230 C865 270 450 255 450 310' },
  { from: 'memory', to: 'agent', path: 'M350 350 C240 350 245 180 375 150' },
  { from: 'evidence', to: 'holdout', path: 'M965 200 C1015 200 1015 350 965 350' },
  { from: 'memory', to: 'store', path: 'M350 350 L230 350' },
];
const journey = ['data', 'agent', 'engine', 'evidence', 'memory', 'agent', 'holdout'];
const windows = [
  { name: '训练', en: 'TRAIN', width: '35%', color: '#2563eb', text: '拟合模型与特征处理器，建立研究基线。' },
  { name: '调参', en: 'TUNE', width: '17%', color: '#6366f1', text: '模型早停与训练参数选择，独立于研究报告指标。' },
  { name: '研究验证', en: 'VALIDATION', width: '24%', color: '#9333ea', text: '比较候选、形成失败记忆，决定下一次实验。' },
  { name: '最终封存', en: 'HOLDOUT', width: '24%', color: '#d97706', text: '冻结候选后评估一次，结果不再用于研究决策。' },
];

export function ProjectGuidePage({ onNavigate, active }: { onNavigate: (page: PageId) => void; active: boolean }) {
  const reduced = useReducedMotion();
  const [view, setView] = useState<View>('architecture');
  const [selected, setSelected] = useState('agent');
  const [playing, setPlaying] = useState(true);
  const [step, setStep] = useState(0);
  const [windowIndex, setWindowIndex] = useState(0);
  const node = nodes.find(item => item.id === selected)!;
  const Icon = node.icon;
  const animate = playing && active && !reduced;
  useEffect(() => {
    if (!animate) return;
    const timer = window.setInterval(() => { if (view === 'protocol') setWindowIndex(value => (value + 1) % windows.length); else setStep(value => (value + 1) % journey.length); }, 3000);
    return () => window.clearInterval(timer);
  }, [animate, view]);
  useEffect(() => { if (playing) setSelected(journey[step]); }, [step, playing]);
  const choose = (id: string) => { setSelected(id); setPlaying(false); };

  return <div className="guide-page relative z-10">
    <section className="guide-hero">
      <div>
        <p className="guide-eyebrow"><span /> ANATOMY OF A RESEARCH AGENT</p>
        <h2>从一个想法，<br />到一条<span>经得起验证的证据。</span></h2>
        <p className="guide-intro">看懂平台如何思考、如何验证，以及如何从失败中学习。<br className="hidden md:block" />一个可复现、可追踪的量化研究闭环。</p>
        <div className="guide-hero-actions"><button className="guide-primary" onClick={() => onNavigate('research')}>进入研究工作台 <ArrowRight size={16} /></button><span>基于 QuantaAlpha · 日频离线研究</span></div>
      </div>
      <div className="guide-principle"><div className="guide-principle-symbol"><BrainCircuit size={27} /><span /><ShieldCheck size={27} /></div><p>让 Agent 负责研究判断</p><strong>让确定性引擎负责验证</strong><small>假设可以开放，证据必须严谨。</small></div>
    </section>

    <section className="guide-canvas" aria-label="交互式项目架构">
      <div className="guide-toolbar"><div className="guide-tabs" role="tablist" aria-label="项目导览视图">{([{ id: 'architecture', label: '系统架构', icon: Layers3 }, { id: 'loop', label: '研究闭环', icon: RotateCcw }, { id: 'protocol', label: '验证协议', icon: ShieldCheck }] as const).map(tab => <button key={tab.id} role="tab" aria-selected={view === tab.id} onClick={() => setView(tab.id)}><tab.icon size={15} />{tab.label}{view === tab.id && <motion.span className="guide-tab-line" layoutId="guide-tab" transition={{ duration: reduced ? 0 : .25 }} />}</button>)}</div><div className="guide-play"><span>流程示意 · 非运行状态</span><button aria-label={playing && !reduced ? '暂停流程演示' : '播放流程演示'} aria-pressed={playing} disabled={!!reduced} title={reduced ? '已遵循系统减少动态效果设置' : undefined} onClick={() => setPlaying(value => !value)}>{playing && !reduced ? <Pause size={14} /> : <Play size={14} />}{reduced ? '静态' : playing ? '暂停' : '演示'}</button></div></div>

      {view !== 'protocol' ? <>
        <p className="px-5 pt-3 text-[10px] text-slate-400 sm:hidden">左右滑动查看架构，点击节点展开说明</p>
        <div className="guide-diagram-scroll"><svg viewBox="0 0 1040 440" className="guide-diagram" role="group" aria-label="可点击架构节点与数据流"><title>Agent 研究、Qlib 执行、证据反馈与样本外封存</title><defs><pattern id="guide-grid" width="24" height="24" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r=".75" fill="#dce2ef" /></pattern></defs><rect width="1040" height="440" fill="url(#guide-grid)" /><text x="32" y="32" className="guide-map-caption">{view === 'loop' ? 'PROPOSE → EXECUTE → OBSERVE → REFLECT' : 'RESEARCH LAYER  /  COMPUTE LAYER  /  EVIDENCE LAYER'}</text>
          {edges.map((edge, i) => { const highlighted = selected === edge.from || selected === edge.to; return <g key={edge.path}><path d={edge.path} fill="none" stroke={highlighted ? node.color : '#ced7e7'} strokeWidth={highlighted ? 2 : 1.5} strokeDasharray={edge.to === 'holdout' ? '5 5' : undefined} opacity={highlighted ? .8 : .65} />{animate && <circle r="3.5" fill={highlighted ? node.color : '#8297c5'}><animateMotion path={edge.path} dur={`${3 + i * .2}s`} repeatCount="indefinite" /></circle>}</g>; })}
          {nodes.map(item => { const NodeIcon = item.icon; const current = item.id === selected; return <foreignObject key={item.id} x={item.x} y={item.y} width="202" height="94"><button aria-label={`查看${item.title}`} aria-pressed={current} className={`guide-node ${current ? 'is-selected' : ''}`} style={{ '--node-color': item.color } as React.CSSProperties} onClick={() => choose(item.id)}><span className="guide-node-top"><NodeIcon size={18} /><span>{item.en}</span><i /></span><strong>{item.title}</strong><small>{item.sub}</small></button></foreignObject>; })}
          <text x="550" y="288" className="guide-edge-label">验证反馈形成记忆</text><text x="795" y="423" className="guide-edge-label">最终结果不回流研究</text>
        </svg></div>
        <div className="guide-details"><AnimatePresence mode="wait"><motion.div key={selected} className="guide-detail-inner" initial={{ opacity: reduced ? 1 : 0, y: reduced ? 0 : 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: reduced ? 0 : .18 }}><div className="guide-detail-heading"><span style={{ color: node.color, background: `${node.color}10` }}><Icon size={22} /></span><div><small>EXPLORE THE COMPONENT</small><h3>{node.title}</h3></div></div><p>{node.description}</p><ul>{node.detail.map(text => <li key={text}><Check size={13} />{text}</li>)}</ul><button onClick={() => onNavigate(node.page)}>打开相关工作台 <ArrowRight size={14} /></button></motion.div></AnimatePresence></div>
        {view === 'loop' && <div className="guide-journey" aria-label="研究步骤">{journey.map((id, index) => <button key={`${id}-${index}`} aria-pressed={step === index} onClick={() => { setStep(index); choose(id); }}><span>{String(index + 1).padStart(2, '0')}</span>{nodes.find(item => item.id === id)!.title}{index < journey.length - 1 && <ChevronRight size={13} />}</button>)}</div>}
      </> : <div className="guide-protocol"><div className="guide-protocol-title"><span className="guide-eyebrow">A FAIR TEST NEEDS A BOUNDARY</span><h3>先固定选择，再看最终答案。</h3><p>点击时间窗口，了解每一段数据的职责。</p></div><div className="guide-timeline" role="group" aria-label="四窗口研究协议">{windows.map((item, index) => <button key={item.en} aria-pressed={windowIndex === index} onClick={() => { setWindowIndex(index); setPlaying(false); }} style={{ '--window-color': item.color, flexBasis: item.width } as React.CSSProperties}><span>{item.en}</span><strong>{item.name}{index === 3 && <LockKeyhole size={16} />}</strong><i className={windowIndex === index ? 'selected' : ''} />{index < 3 && <small>purge ≥ 2 交易日</small>}</button>)}</div><motion.div key={windowIndex} initial={{ opacity: reduced ? 1 : 0 }} animate={{ opacity: 1 }} transition={{ duration: reduced ? 0 : .2 }} className="guide-window-detail"><span style={{ background: windows[windowIndex].color }} /><strong>{windows[windowIndex].name}</strong><p>{windows[windowIndex].text}</p></motion.div><div className="guide-protocol-rules"><article><ShieldCheck size={20} /><h4>时间边界</h4><p>按真实交易日历验证不重叠；前瞻标签跨度更长时，增加隔离间隔。</p></article><article><LockKeyhole size={20} /><h4>一次最终评估</h4><p>冻结数据、候选与配置，原子领取任务；最终结果不进入记忆。</p></article><article><GitBranch size={20} /><h4>同预算比较</h4><p>有无记忆使用相同数据、种子和实验预算，保留负结果及失败。</p></article></div><button className="guide-primary" onClick={() => onNavigate('research')}>创建你的研究协议 <ArrowRight size={15} /></button></div>}
    </section>

    <section className="guide-foundations"><div><p className="guide-eyebrow">BUILT ON FOUNDATIONS, EXTENDED WITH PURPOSE</p><h3>保留成熟基座，把增量做在研究质量上。</h3></div><div className="guide-foundation-grid"><article><Layers3 size={20} /><span>01 / 复用</span><h4>成熟的研究底座</h4><p>QuantaAlpha 因子挖掘与进化、Qlib 计算回测，以及现有 React 工作台。</p></article><article><BookOpen size={20} /><span>02 / 扩展</span><h4>有证据的失败记忆</h4><p>记录经济性失败及适用上下文，让下一次实验少重复无效探索。</p></article><article><ShieldCheck size={20} /><span>03 / 验证</span><h4>可复现的研究纪律</h4><p>四窗口、冻结候选、等预算对照与证据导出，使结果能够被复核。</p></article></div></section>
    <footer className="guide-footer"><span><Sparkles size={14} /> Agentic Quant Research Platform</span><span>当前版本：日频离线研究 · 演示数据与真实研究明确区分</span></footer>
  </div>;
}
