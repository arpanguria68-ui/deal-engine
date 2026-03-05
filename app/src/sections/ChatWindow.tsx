import { useState, useRef, useEffect, useCallback } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
    Send, Paperclip, User, Loader2, Sparkles,
    TrendingUp, AlertTriangle, FileText, Scale, Brain,
    Download, ChevronRight, HelpCircle, Cpu, Cloud,
    ListChecks, CheckCircle2, Copy, Check, RotateCcw, Edit2,
    Zap, Sliders, Star, Globe, BookOpen, Database, ChevronDown
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useDealForgeStore } from '@/lib/dealforge-store';

const API_BASE = 'http://localhost:8000';

// ─── Types ───

interface Message {
    id: string;
    role: 'user' | 'assistant' | 'agent' | 'system';
    content: string;
    agentName?: string;
    timestamp: Date;
    status?: 'thinking' | 'done' | 'error';
    provider?: string;
    dealId?: string;
    metadata?: Record<string, unknown>;
    followUps?: string[];
    missingData?: string[];
}

type FocusMode = 'speed' | 'balanced' | 'quality';
type Phase = 'idle' | 'brainstorming' | 'planning' | 'executing' | 'synthesizing';
type DataSource = 'financial' | 'web' | 'docs';

// ─── Constants ───

const AGENT_STYLES: Record<string, { icon: typeof Sparkles; gradient: string; glow: string }> = {
    financial_analyst: { icon: TrendingUp, gradient: 'from-blue-500 to-cyan-400', glow: 'shadow-blue-500/20' },
    legal_advisor: { icon: Scale, gradient: 'from-purple-500 to-violet-400', glow: 'shadow-purple-500/20' },
    risk_assessor: { icon: AlertTriangle, gradient: 'from-amber-500 to-orange-400', glow: 'shadow-amber-500/20' },
    market_researcher: { icon: FileText, gradient: 'from-emerald-500 to-green-400', glow: 'shadow-emerald-500/20' },
    debate_moderator: { icon: Brain, gradient: 'from-pink-500 to-rose-400', glow: 'shadow-pink-500/20' },
    project_manager: { icon: ListChecks, gradient: 'from-cyan-500 to-teal-400', glow: 'shadow-cyan-500/20' },
    scrum_master: { icon: ListChecks, gradient: 'from-cyan-500 to-teal-400', glow: 'shadow-cyan-500/20' },
    valuation_agent: { icon: TrendingUp, gradient: 'from-teal-500 to-emerald-400', glow: 'shadow-teal-500/20' },
    dcf_lbo_architect: { icon: TrendingUp, gradient: 'from-teal-500 to-cyan-400', glow: 'shadow-teal-500/20' },
    due_diligence_agent: { icon: FileText, gradient: 'from-orange-500 to-red-400', glow: 'shadow-orange-500/20' },
    scoring_agent: { icon: CheckCircle2, gradient: 'from-lime-500 to-green-400', glow: 'shadow-lime-500/20' },
    investment_memo_agent: { icon: FileText, gradient: 'from-rose-500 to-pink-400', glow: 'shadow-rose-500/20' },
    compliance_agent: { icon: Scale, gradient: 'from-violet-500 to-indigo-400', glow: 'shadow-violet-500/20' },
    system: { icon: Sparkles, gradient: 'from-indigo-500 to-blue-400', glow: 'shadow-indigo-500/20' },
};

const FOCUS_MODES: { value: FocusMode; label: string; icon: typeof Zap; desc: string; color: string; badge?: string }[] = [
    { value: 'speed', label: 'Speed', icon: Zap, desc: 'Prioritize speed and get the quickest possible answer.', color: 'text-amber-400' },
    { value: 'balanced', label: 'Balanced', icon: Sliders, desc: 'Find the right balance between speed and accuracy.', color: 'text-blue-400' },
    { value: 'quality', label: 'Quality', icon: Star, desc: 'Get the most thorough and accurate answer.', color: 'text-emerald-400', badge: 'Beta' },
];

const DATA_SOURCES: { value: DataSource; label: string; icon: typeof Globe }[] = [
    { value: 'financial', label: 'Financial', icon: TrendingUp },
    { value: 'web', label: 'Web', icon: Globe },
    { value: 'docs', label: 'Docs', icon: BookOpen },
];

const PHASE_LABELS: Record<Phase, { text: string; color: string }> = {
    idle: { text: '', color: '' },
    brainstorming: { text: 'Brainstorming', color: 'text-violet-400' },
    planning: { text: 'Building plan', color: 'text-cyan-400' },
    executing: { text: 'Agents running', color: 'text-amber-400' },
    synthesizing: { text: 'Synthesizing', color: 'text-emerald-400' },
};

// Speed mode: only top-3 critical
const SPEED_AGENTS = new Set(['financial_analyst', 'risk_assessor', 'market_researcher']);

// ─── Helpers ───

function generateFollowUps(dealText: string, _agentResults: string[]): string[] {
    const suggestions: string[] = [];
    const lower = dealText.toLowerCase();
    if (lower.includes('acquisition') || lower.includes('acquire')) {
        suggestions.push('What are the key synergies in this acquisition?');
        suggestions.push('Run a sensitivity analysis on the DCF valuation');
        suggestions.push('What regulatory hurdles could block this deal?');
    }
    if (lower.includes('merger')) {
        suggestions.push('What are the integration risks post-merger?');
        suggestions.push('Compare management team strengths of both companies');
    }
    if (lower.includes('saas') || lower.includes('software')) {
        suggestions.push('Analyze the Net Revenue Retention and churn metrics');
        suggestions.push('How does the CAC payback period compare to industry benchmarks?');
    }
    suggestions.push('What are the top 3 deal-breaker risks?');
    suggestions.push('Generate a one-page investment memo');
    suggestions.push('What comparable transactions support this valuation?');
    return [...new Set(suggestions)].slice(0, 4);
}

function detectMissingData(dealText: string): string[] {
    const missing: string[] = [];
    const lower = dealText.toLowerCase();
    if (!/\$[\d.,]+[mbk]?\b/i.test(dealText) && !lower.includes('revenue') && !lower.includes('arr'))
        missing.push('Annual revenue or ARR');
    if (!lower.includes('ebitda') && !lower.includes('profit') && !lower.includes('margin'))
        missing.push('EBITDA or profit margins');
    if (!lower.includes('employee') && !lower.includes('team') && !lower.includes('headcount'))
        missing.push('Employee count / team size');
    return missing.slice(0, 3);
}

function extractCompanyName(text: string): string {
    const match = text.match(/(?:acquire|acquisition of|merge with|analyze|buy)\s+([A-Z][a-zA-Z\s]+(?:Corp|Inc|LLC|Ltd|Co)?)/i);
    return match ? match[1].trim() : text.substring(0, 40);
}

function formatAgentResult(agentLabel: string, result: Record<string, unknown>): string {
    const confidence = typeof result.confidence === 'number' ? `${Math.round((result.confidence as number) * 100)}%` : 'N/A';
    const reasoning = typeof result.reasoning === 'string' ? (result.reasoning as string) : '';
    const time = typeof result.execution_time_ms === 'number' ? `${Math.round(result.execution_time_ms as number)}ms` : '';
    let output = `### ${agentLabel}\n\n`;
    if (reasoning) output += `${reasoning}\n\n`;
    output += `**Confidence:** ${confidence}`;
    if (time) output += ` · **Time:** ${time}`;
    return output;
}

// ─── Animated Dots Component ───

function AnimatedDots() {
    return (
        <span className="inline-flex ml-1">
            <span className="animate-bounce" style={{ animationDelay: '0ms', animationDuration: '1.2s' }}>.</span>
            <span className="animate-bounce" style={{ animationDelay: '200ms', animationDuration: '1.2s' }}>.</span>
            <span className="animate-bounce" style={{ animationDelay: '400ms', animationDuration: '1.2s' }}>.</span>
        </span>
    );
}

// ─── Focus Mode Popover ───

function FocusModePopover({ value, onChange, open, onToggle }: {
    value: FocusMode; onChange: (v: FocusMode) => void; open: boolean; onToggle: () => void;
}) {
    const current = FOCUS_MODES.find(m => m.value === value)!;
    const CurrentIcon = current.icon;

    return (
        <div className="relative">
            <button
                onClick={onToggle}
                className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-all duration-200 
                    bg-white/5 hover:bg-white/10 border border-white/10 hover:border-white/20 ${current.color}`}
            >
                <CurrentIcon className="h-3.5 w-3.5" />
                <span>{current.label}</span>
                <ChevronDown className={`h-3 w-3 transition-transform ${open ? 'rotate-180' : ''}`} />
            </button>

            {open && (
                <div className="absolute bottom-full left-0 mb-2 w-72 rounded-xl border border-white/10 bg-[#1a1a2e]/95 backdrop-blur-xl shadow-2xl shadow-black/50 z-50 overflow-hidden animate-in fade-in slide-in-from-bottom-2 duration-200">
                    {FOCUS_MODES.map((mode) => {
                        const Icon = mode.icon;
                        const isActive = mode.value === value;
                        return (
                            <button
                                key={mode.value}
                                onClick={() => { onChange(mode.value); onToggle(); }}
                                className={`w-full flex items-start gap-3 px-4 py-3 text-left transition-all duration-150 
                                    ${isActive ? 'bg-white/10' : 'hover:bg-white/5'}`}
                            >
                                <Icon className={`h-4 w-4 mt-0.5 ${mode.color}`} />
                                <div>
                                    <div className="flex items-center gap-2">
                                        <span className={`text-sm font-semibold ${isActive ? 'text-white' : 'text-white/80'}`}>{mode.label}</span>
                                        {mode.badge && (
                                            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 font-medium">{mode.badge}</span>
                                        )}
                                    </div>
                                    <span className="text-xs text-white/50 leading-tight">{mode.desc}</span>
                                </div>
                            </button>
                        );
                    })}
                </div>
            )}
        </div>
    );
}

// ─── Source Toggles ───

function SourceToggles({ active, onToggle }: { active: DataSource[]; onToggle: (s: DataSource) => void }) {
    const [open, setOpen] = useState(false);

    return (
        <div className="relative">
            <button
                onClick={() => setOpen(!open)}
                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-all duration-200 bg-white/5 hover:bg-white/10 border border-white/10 hover:border-white/20 text-blue-400"
            >
                <Database className="h-3.5 w-3.5" />
                <span>Sources</span>
                <span className="text-[10px] bg-blue-500/20 text-blue-300 rounded-full px-1.5">{active.length}</span>
            </button>

            {open && (
                <div className="absolute bottom-full left-0 mb-2 w-52 rounded-xl border border-white/10 bg-[#1a1a2e]/95 backdrop-blur-xl shadow-2xl shadow-black/50 z-50 overflow-hidden animate-in fade-in slide-in-from-bottom-2 duration-200">
                    {DATA_SOURCES.map((src) => {
                        const Icon = src.icon;
                        const isActive = active.includes(src.value);
                        return (
                            <button
                                key={src.value}
                                onClick={() => onToggle(src.value)}
                                className="w-full flex items-center justify-between px-4 py-2.5 hover:bg-white/5 transition-colors"
                            >
                                <div className="flex items-center gap-2.5">
                                    <Icon className={`h-4 w-4 ${isActive ? 'text-blue-400' : 'text-white/40'}`} />
                                    <span className={`text-sm ${isActive ? 'text-white' : 'text-white/50'}`}>{src.label}</span>
                                </div>
                                <div className={`w-8 h-4.5 rounded-full transition-colors duration-200 flex items-center px-0.5 
                                    ${isActive ? 'bg-blue-500' : 'bg-white/10'}`}>
                                    <div className={`w-3.5 h-3.5 rounded-full bg-white transition-transform duration-200 
                                        ${isActive ? 'translate-x-3.5' : 'translate-x-0'}`} />
                                </div>
                            </button>
                        );
                    })}
                </div>
            )}
        </div>
    );
}

// ═══════════════════════════════════════
//  MAIN COMPONENT
// ═══════════════════════════════════════

export function ChatWindow() {
    const store = useDealForgeStore();
    const activeConv = store.getActiveConversation();

    useEffect(() => {
        if (!activeConv) {
            const convId = store.createConversation();
            store.addMessage(convId, {
                role: 'system',
                content: 'Welcome to **DealForge AI**. Describe a deal and our multi-agent team will analyze it end-to-end.\n\nTry: *"Analyze the acquisition of Stripe, a SaaS company with $50M ARR"*',
                agentName: 'DealForge AI',
            });
        }
    }, []);

    const messages: Message[] = (activeConv?.messages || []).map((m: any) => ({
        id: m.id, role: m.role, content: m.content, agentName: m.agentName,
        timestamp: new Date(m.timestamp), status: m.status, provider: m.provider,
        followUps: m.followUps, missingData: m.missingData, metadata: m.metadata,
    }));

    // ─── State ───
    const [input, setInput] = useState('');
    const [phase, setPhase] = useState<Phase>('idle');
    const [activeDealId, setActiveDealId] = useState<string | null>(activeConv?.dealId || null);
    const [uploadedFiles, setUploadedFiles] = useState<File[]>([]);
    const [followUps, setFollowUps] = useState<string[]>([]);
    const [copiedId, setCopiedId] = useState<string | null>(null);
    const [editingMsgId, setEditingMsgId] = useState<string | null>(null);
    const [editValue, setEditValue] = useState('');
    const [focusMode, setFocusMode] = useState<FocusMode>('balanced');
    const [activeSources, setActiveSources] = useState<DataSource[]>(['financial', 'docs']);
    const [focusOpen, setFocusOpen] = useState(false);
    const [executingProgress, setExecutingProgress] = useState({ done: 0, total: 0 });

    const isProcessing = phase !== 'idle';

    const messagesEndRef = useRef<HTMLDivElement>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const textareaRef = useRef<HTMLTextAreaElement>(null);

    const scrollToBottom = () => messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    useEffect(() => { scrollToBottom(); }, [messages.length, followUps.length, phase]);

    const autoResize = useCallback(() => {
        const ta = textareaRef.current;
        if (ta) { ta.style.height = 'auto'; ta.style.height = `${Math.min(ta.scrollHeight, 150)}px`; }
    }, []);
    useEffect(() => { autoResize(); }, [input, autoResize]);

    const convId = activeConv?.id || '';

    function addMessage(msg: Omit<Message, 'id' | 'timestamp'>) {
        if (!convId) return '';
        const msgId = store.addMessage(convId, {
            role: msg.role, content: msg.content, agentName: msg.agentName,
            status: msg.status, provider: msg.provider,
        });
        if (msg.role === 'user' && messages.filter(m => m.role === 'user').length === 0) {
            store.updateConversationTitle(convId, msg.content.slice(0, 50) + (msg.content.length > 50 ? '...' : ''));
        }
        return msgId;
    }

    function updateMessage(id: string, updates: Partial<Message>) {
        if (!convId) return;
        store.updateMessage(convId, id, {
            content: updates.content, status: updates.status,
            agentName: updates.agentName, provider: updates.provider,
            followUps: updates.followUps, missingData: updates.missingData,
        });
    }

    async function uploadFiles(dealId: string) {
        for (const file of uploadedFiles) {
            const formData = new FormData();
            formData.append('file', file);
            try {
                await fetch(`${API_BASE}/api/v1/documents/upload?deal_id=${dealId}`, { method: 'POST', body: formData });
                addMessage({ role: 'agent', agentName: 'PageIndex', content: `📄 Indexed **${file.name}** into knowledge base.` });
            } catch {
                addMessage({ role: 'agent', agentName: 'PageIndex', content: `⚠️ Failed to index ${file.name}`, status: 'error' });
            }
        }
        setUploadedFiles([]);
    }

    function toggleSource(s: DataSource) {
        setActiveSources(prev => prev.includes(s) ? prev.filter(x => x !== s) : [...prev, s]);
    }

    // ─── Main send handler ───

    async function handleSend(overrideText?: string, isRegenerate = false) {
        let userText = (overrideText || input).trim();
        if (!userText && uploadedFiles.length === 0) return;

        setInput('');
        setFollowUps([]);
        setPhase('brainstorming');

        const lastAgentMsg = messages.slice().reverse().find(m => m.role === 'agent' || m.role === 'assistant');
        const isAnsweringQuestions = lastAgentMsg?.metadata?.pending_clarification;

        if (!isRegenerate) {
            addMessage({ role: 'user', content: userText });
        } else {
            userText = overrideText || '';
        }

        // Missing data hint
        const missing = detectMissingData(userText);
        if (missing.length > 0 && !activeDealId && !isAnsweringQuestions) {
            addMessage({
                role: 'system', agentName: 'Data Assistant',
                content: `💡 For a more accurate analysis, consider providing:\n\n${missing.map(m => `• ${m}`).join('\n')}\n\nYou can add these details in your next message, or I'll proceed with what's available.`,
                missingData: missing,
            });
        }

        try {
            let dealId = activeDealId;
            let currentPrompt = userText;
            let userAnswers: any[] = [];

            if (isAnsweringQuestions) {
                updateMessage(lastAgentMsg!.id, { metadata: { ...lastAgentMsg!.metadata, pending_clarification: false } });
                dealId = lastAgentMsg!.metadata!.deal_id as string;
                currentPrompt = lastAgentMsg!.metadata!.original_prompt as string;
                userAnswers = [{ question: "User Response", answer: userText }];
                setActiveDealId(dealId);
            } else {
                // Create deal
                const createRes = await fetch(`${API_BASE}/api/v1/deals`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        name: userText.substring(0, 80), target_company: extractCompanyName(userText),
                        description: userText, industry: 'technology',
                        context: { user_prompt: userText, focus_mode: focusMode, sources: activeSources },
                    }),
                });
                if (!createRes.ok) throw new Error('Failed to create deal');
                const deal = await createRes.json();
                dealId = deal.id;
                setActiveDealId(dealId);

                if (uploadedFiles.length > 0) await uploadFiles(dealId!);

                // Clarification
                const thinkingId = addMessage({
                    role: 'agent', agentName: 'Scrum Master',
                    content: '🧠 **Analyzing your request...**\n\n> Checking data requirements and identifying potential risks...',
                    status: 'thinking',
                });

                const clarifyRes = await fetch(`${API_BASE}/api/v1/chat/clarify`, {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ prompt: userText, deal_id: dealId, company_name: extractCompanyName(userText) }),
                });

                if (clarifyRes.ok) {
                    const clarifyData = await clarifyRes.json();
                    if (clarifyData.clarifying_questions?.length > 0) {
                        const questionList = clarifyData.clarifying_questions.map((q: any, i: number) =>
                            `**Q${i + 1}:** ${q.question}\n*Reasoning: ${q.reasoning}*`).join('\n\n');
                        updateMessage(thinkingId, {
                            content: `🧠 **Scrum Master — Clarification Needed**\n\n${questionList}\n\n*(Please reply to proceed)*`,
                            status: 'done',
                            metadata: { pending_clarification: true, original_prompt: userText, deal_id: dealId, questions: clarifyData.clarifying_questions }
                        });
                        setPhase('idle');
                        return;
                    } else {
                        updateMessage(thinkingId, { content: '🧠 **Scrum Master** — Request is clear, proceeding to build plan.', status: 'done' });
                    }
                } else {
                    updateMessage(thinkingId, { content: '⚠️ Skipping clarification — AI Service unavailable. Proceeding.', status: 'done' });
                }
            }

            // ─── Planning ───
            setPhase('planning');
            const thinkingPlanId = addMessage({
                role: 'agent', agentName: 'Scrum Master',
                content: '📋 **Building Plan...**\n\n> Reasoning about the best approach and planning the task pipeline...',
                status: 'thinking',
            });

            const planRes = await fetch(`${API_BASE}/api/v1/chat/plan`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    prompt: currentPrompt, deal_id: dealId,
                    company_name: extractCompanyName(currentPrompt),
                    user_answers: userAnswers,
                    focus_mode: focusMode, sources: activeSources,
                }),
            });

            let taskList: Array<{ title: string; description: string; assigned_agent: string; priority: string; id?: string }> = [];

            if (planRes.ok) {
                const plan = await planRes.json();
                taskList = plan.data?.todo_list?.items || [];
                const reasoning = plan.reasoning || 'Generated task pipeline.';

                // Apply Focus Mode filtering
                if (focusMode === 'speed') {
                    taskList = taskList.filter(t => SPEED_AGENTS.has(t.assigned_agent) || t.priority === 'critical');
                    if (taskList.length > 3) taskList = taskList.slice(0, 3);
                } else if (focusMode === 'balanced') {
                    taskList = taskList.filter(t => t.priority === 'critical' || t.priority === 'high');
                    if (taskList.length > 6) taskList = taskList.slice(0, 6);
                }
                // Quality: keep all

                const agentCount = new Set(taskList.map(t => t.assigned_agent)).size;
                const taskListMd = taskList.map((t, i) =>
                    `${i + 1}. **${t.title}** → \`${(t.assigned_agent || '').replace(/_/g, ' ')}\` *(${t.priority})*\n   ${t.description}`
                ).join('\n');

                updateMessage(thinkingPlanId, {
                    content: `🧠 **Scrum Master — Task Plan Created**\n\n` +
                        `> **💭 Reasoning:** ${reasoning.split('\\n').join('\\n> ')}\n\n` +
                        `📋 **${taskList.length} tasks** assigned to **${agentCount} agents**:\n\n${taskListMd}\n\n---\n⏳ Starting execution...`,
                    status: 'done',
                });
            } else {
                updateMessage(thinkingPlanId, { content: '🧠 **Scrum Master** — Using standard analysis pipeline', status: 'done' });
                taskList = [
                    { title: 'Financial Analysis', description: `Perform financial analysis for: ${userText}`, assigned_agent: 'financial_analyst', priority: 'critical' },
                    { title: 'Market Research', description: `Research the market for: ${userText}`, assigned_agent: 'market_researcher', priority: 'high' },
                    { title: 'Legal Review', description: `Perform legal due diligence for: ${userText}`, assigned_agent: 'legal_advisor', priority: 'high' },
                    { title: 'Risk Assessment', description: `Assess risks for: ${userText}`, assigned_agent: 'risk_assessor', priority: 'high' },
                ];
            }

            // ─── Execute Tasks ───
            setPhase('executing');
            const agentResults: string[] = [];
            let completedCount = 0;
            setExecutingProgress({ done: 0, total: taskList.length });

            const progressId = addMessage({
                role: 'system', agentName: 'Progress',
                content: `📊 **Progress:** 0/${taskList.length} agents complete`,
            });

            for (const task of taskList) {
                const agentLabel = (task.assigned_agent || 'analyst').replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
                const taskMsgId = addMessage({
                    role: 'agent', agentName: agentLabel,
                    content: `⏳ **${task.title}** — Analyzing...`, status: 'thinking',
                });

                try {
                    const taskRes = await fetch(`${API_BASE}/api/v1/chat/execute-task`, {
                        method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            agent_type: task.assigned_agent, task: task.description,
                            deal_id: dealId, task_id: task.id || `task-${completedCount}`,
                            title: task.title, sources: activeSources,
                        }),
                    });

                    if (taskRes.ok) {
                        const result = await taskRes.json();
                        const formatted = formatAgentResult(agentLabel, result);
                        agentResults.push(formatted);
                        completedCount++;
                        updateMessage(taskMsgId, {
                            content: `✅ **${task.title}**\n\n${formatted}`, status: 'done',
                            provider: result.provider || 'unknown', metadata: result.data,
                        });
                    } else {
                        completedCount++;
                        updateMessage(taskMsgId, { content: `⚠️ **${task.title}** — Agent error. Check Settings.`, status: 'error' });
                    }
                } catch {
                    completedCount++;
                    updateMessage(taskMsgId, { content: `⚠️ **${task.title}** — Could not reach agent.`, status: 'error' });
                }

                setExecutingProgress({ done: completedCount, total: taskList.length });
                updateMessage(progressId, {
                    content: `📊 **Progress:** ${completedCount}/${taskList.length} agents complete ${completedCount === taskList.length ? '✅' : ''}`,
                });

                fetch(`${API_BASE}/api/v1/agent-activity`, {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        agent_type: task.assigned_agent, deal_id: dealId,
                        summary: `Completed: ${task.title}`, provider: 'auto', confidence: 0.8,
                    }),
                }).catch(() => { });
            }

            // ─── Synthesis ───
            setPhase('synthesizing');
            addMessage({
                role: 'agent', agentName: 'Scrum Master',
                content: `🏁 **Analysis Complete**\n\n✅ **${completedCount}/${taskList.length}** tasks completed across **${new Set(taskList.map(t => t.assigned_agent)).size}** specialist agents.\n\nAll findings are presented above. Review each agent's analysis for detailed insights.`,
            });

            const suggestions = generateFollowUps(userText, agentResults);
            setFollowUps(suggestions);

        } catch (err) {
            addMessage({
                role: 'system',
                content: `❌ Error: ${err instanceof Error ? err.message : 'Connection failed'}. Make sure the backend is running.`,
                status: 'error',
            });
        }

        setPhase('idle');
    }

    function handleExport() {
        const data = messages.filter(m => m.role !== 'system' || m.agentName).map(m => ({
            role: m.role, agent: m.agentName, content: m.content,
            provider: m.provider, timestamp: m.timestamp.toISOString(),
        }));
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a'); a.href = url;
        a.download = `dealforge-analysis-${activeDealId?.substring(0, 8) || 'draft'}.json`;
        a.click();
    }

    const handleCopy = (text: string, id: string) => {
        navigator.clipboard.writeText(text);
        setCopiedId(id);
        setTimeout(() => setCopiedId(null), 2000);
    };

    const handleEditSubmit = (msg: Message) => {
        if (editValue.trim() && editValue !== msg.content) updateMessage(msg.id, { content: editValue.trim() });
        setEditingMsgId(null);
    };

    const handleRegenerate = (msg: Message) => handleSend(msg.content, true);

    // ─── Markdown renderer ───

    function renderMarkdown(text: string) {
        return (
            <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                    h1: ({ children }: any) => <h1 className="text-xl font-bold mt-4 mb-2 text-white">{children}</h1>,
                    h2: ({ children }: any) => <h2 className="text-lg font-bold mt-3 mb-1.5 text-white/90">{children}</h2>,
                    h3: ({ children }: any) => <h3 className="text-base font-bold mt-2 mb-1 text-white/85">{children}</h3>,
                    p: ({ children }: any) => <p className="mb-2 leading-relaxed">{children}</p>,
                    strong: ({ children }: any) => <strong className="font-semibold text-white">{children}</strong>,
                    em: ({ children }: any) => <em className="italic text-white/70">{children}</em>,
                    code: ({ className, children, ...props }: any) => {
                        const isBlock = className?.includes('language-');
                        return isBlock ? (
                            <pre className="bg-black/40 text-emerald-300 rounded-lg p-3 my-2 overflow-x-auto text-xs border border-white/5">
                                <code className={className} {...props}>{children}</code>
                            </pre>
                        ) : (
                            <code className="bg-white/10 px-1.5 py-0.5 rounded text-xs font-mono text-cyan-300" {...props}>{children}</code>
                        );
                    },
                    ul: ({ children }: any) => <ul className="list-disc pl-5 space-y-1 mb-2">{children}</ul>,
                    ol: ({ children }: any) => <ol className="list-decimal pl-5 space-y-1 mb-2">{children}</ol>,
                    li: ({ children }: any) => <li className="leading-relaxed">{children}</li>,
                    table: ({ children }: any) => (
                        <div className="overflow-x-auto my-2">
                            <table className="min-w-full border border-white/10 text-xs">{children}</table>
                        </div>
                    ),
                    th: ({ children }: any) => <th className="border border-white/10 px-2 py-1 bg-white/5 font-semibold text-left text-white/80">{children}</th>,
                    td: ({ children }: any) => <td className="border border-white/10 px-2 py-1 text-white/70">{children}</td>,
                    blockquote: ({ children }: any) => <blockquote className="border-l-4 border-cyan-500/30 pl-3 italic text-white/50 my-2">{children}</blockquote>,
                    a: ({ href, children }: any) => <a href={href} className="text-cyan-400 underline hover:text-cyan-300" target="_blank" rel="noreferrer">{children}</a>,
                }}
            >
                {text}
            </ReactMarkdown>
        );
    }

    // ─── Message renderer ───

    function renderMessage(msg: Message) {
        const isUser = msg.role === 'user';
        const agentKey = msg.agentName?.toLowerCase().replace(/\s/g, '_') || 'system';
        const agentStyle = AGENT_STYLES[agentKey] || AGENT_STYLES.system;
        const AgentIcon = agentStyle.icon;
        const isEditing = editingMsgId === msg.id;

        return (
            <div key={msg.id} className={`flex gap-3 group ${isUser ? 'flex-row-reverse' : ''} animate-in fade-in slide-in-from-bottom-2 duration-300`}>
                {/* Avatar */}
                <div className={`flex-shrink-0 w-9 h-9 rounded-xl flex items-center justify-center shadow-lg 
                    ${isUser
                        ? 'bg-gradient-to-br from-indigo-500 to-purple-600 shadow-indigo-500/20'
                        : `bg-gradient-to-br ${agentStyle.gradient} ${agentStyle.glow}`
                    }`}
                >
                    {isUser ? <User className="h-4 w-4 text-white" /> : <AgentIcon className="h-4 w-4 text-white" />}
                </div>

                <div className={`max-w-[85%] flex flex-col ${isUser ? 'items-end' : 'items-start'}`}>
                    {/* Agent Header */}
                    {!isUser && msg.agentName && (
                        <div className="flex items-center gap-2 mb-1.5">
                            <span className="text-xs font-semibold text-white/60">{msg.agentName}</span>
                            {msg.status === 'thinking' && (
                                <span className="flex items-center gap-1 text-xs text-violet-400">
                                    <Loader2 className="h-3 w-3 animate-spin" />
                                    <span>Thinking<AnimatedDots /></span>
                                </span>
                            )}
                            {msg.status === 'done' && (
                                <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-emerald-500/15 text-emerald-400 font-medium">Done</span>
                            )}
                            {msg.status === 'error' && (
                                <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-red-500/15 text-red-400 font-medium">Error</span>
                            )}
                            {msg.provider && (
                                <span className="flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full bg-white/5 text-white/40 font-medium">
                                    {msg.provider === 'ollama' || msg.provider === 'lmstudio' ? <Cpu className="h-2.5 w-2.5" /> : <Cloud className="h-2.5 w-2.5" />}
                                    {msg.provider}
                                </span>
                            )}
                        </div>
                    )}

                    {/* Message Body */}
                    {isEditing ? (
                        <div className="w-full flex flex-col gap-2 mt-1">
                            <textarea
                                className="w-full text-sm p-3 rounded-xl border border-white/10 resize-none focus:outline-none focus:ring-1 focus:ring-cyan-500/50 min-h-[100px] text-white bg-white/5"
                                value={editValue} onChange={(e) => setEditValue(e.target.value)} autoFocus
                            />
                            <div className="flex justify-end gap-2">
                                <Button size="sm" variant="ghost" onClick={() => setEditingMsgId(null)} className="text-white/50 hover:text-white">Cancel</Button>
                                <Button size="sm" onClick={() => handleEditSubmit(msg)} className="bg-cyan-500/20 text-cyan-400 hover:bg-cyan-500/30">Save</Button>
                            </div>
                        </div>
                    ) : (
                        <div className={`rounded-2xl px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap transition-all duration-300
                            ${isUser
                                ? 'bg-gradient-to-r from-indigo-600/80 to-purple-600/80 text-white rounded-br-md border border-indigo-500/20 shadow-lg shadow-indigo-500/10'
                                : 'bg-white/[0.04] backdrop-blur-sm rounded-bl-md border border-white/[0.06] text-white/80 hover:border-white/10'
                            } ${msg.status === 'thinking' ? 'animate-pulse' : ''}`}>
                            {renderMarkdown(msg.content)}
                        </div>
                    )}

                    {/* Action Buttons */}
                    {!isEditing && (
                        <div className={`flex items-center gap-1 mt-1 opacity-0 group-hover:opacity-100 transition-opacity ${isUser ? 'flex-row-reverse' : ''}`}>
                            <span className="text-[10px] text-white/30 px-1">
                                {msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                            </span>
                            <button className="p-1 rounded-md text-white/30 hover:text-white/60 hover:bg-white/5 transition-colors" onClick={() => handleCopy(msg.content, msg.id)} title="Copy">
                                {copiedId === msg.id ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3" />}
                            </button>
                            {isUser && !isProcessing && (
                                <>
                                    <button className="p-1 rounded-md text-white/30 hover:text-white/60 hover:bg-white/5 transition-colors" onClick={() => { setEditingMsgId(msg.id); setEditValue(msg.content); }} title="Edit">
                                        <Edit2 className="h-3 w-3" />
                                    </button>
                                    <button className="p-1 rounded-md text-white/30 hover:text-white/60 hover:bg-white/5 transition-colors" onClick={() => handleRegenerate(msg)} title="Regenerate">
                                        <RotateCcw className="h-3 w-3" />
                                    </button>
                                </>
                            )}
                        </div>
                    )}
                </div>
            </div>
        );
    }

    // ─── Phase indicator bar ───

    const phaseLabel = PHASE_LABELS[phase];

    // ═══════════════════════════════════════
    //  RENDER
    // ═══════════════════════════════════════

    return (
        <div className="flex flex-col h-[calc(100vh-5rem)]">
            {/* Header */}
            <div className="flex items-center justify-between mb-4">
                <div>
                    <h2 className="text-3xl font-bold tracking-tight bg-gradient-to-r from-cyan-400 via-blue-500 to-violet-500 bg-clip-text text-transparent">
                        Research begins here.
                    </h2>
                    <p className="text-white/40 text-sm mt-0.5">
                        Multi-agent M&A intelligence • Local-first, cloud-fallback
                    </p>
                </div>
                {messages.length > 1 && (
                    <Button variant="outline" size="sm" onClick={handleExport} className="border-white/10 text-white/60 hover:text-white hover:bg-white/5">
                        <Download className="mr-2 h-3.5 w-3.5" /> Export
                    </Button>
                )}
            </div>

            {/* Chat Container */}
            <div className="flex-1 min-h-0 flex flex-col overflow-hidden rounded-2xl border border-white/[0.06] bg-[#0d0d1a]/80 backdrop-blur-xl shadow-2xl shadow-black/30">

                {/* Messages */}
                <ScrollArea className="flex-1 min-h-0" type="always">
                    <div className="space-y-5 p-5">
                        {messages.map(renderMessage)}
                        <div ref={messagesEndRef} className="h-1 w-full" />
                    </div>
                </ScrollArea>

                {/* Follow-up Suggestions */}
                {followUps.length > 0 && !isProcessing && (
                    <div className="px-5 py-3 border-t border-white/5">
                        <div className="flex items-center gap-2 mb-2">
                            <HelpCircle className="h-3.5 w-3.5 text-cyan-400" />
                            <span className="text-xs font-semibold text-cyan-400">Follow-up questions</span>
                        </div>
                        <div className="flex flex-wrap gap-2">
                            {followUps.map((q, i) => (
                                <button key={i} onClick={() => handleSend(q)}
                                    className="text-xs px-3 py-1.5 rounded-full border border-white/10 bg-white/[0.03] hover:bg-white/[0.08] hover:border-cyan-500/30 transition-all duration-200 flex items-center gap-1 text-white/60 hover:text-white group"
                                >
                                    <ChevronRight className="h-3 w-3 text-white/30 group-hover:text-cyan-400 transition-colors" />
                                    {q}
                                </button>
                            ))}
                        </div>
                    </div>
                )}

                {/* File Chips */}
                {uploadedFiles.length > 0 && (
                    <div className="px-5 pb-2 flex flex-wrap gap-2">
                        {uploadedFiles.map((f, i) => (
                            <span key={i} className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg bg-white/5 border border-white/10 text-white/60">
                                <Paperclip className="h-3 w-3" />
                                {f.name}
                                <button onClick={() => setUploadedFiles(prev => prev.filter((_, j) => j !== i))} className="ml-1 text-white/30 hover:text-white/60">×</button>
                            </span>
                        ))}
                    </div>
                )}

                {/* ═══ Input Area ═══ */}
                <div className="border-t border-white/[0.06] p-4">
                    {/* Textarea */}
                    <div className="relative rounded-xl border border-white/10 bg-white/[0.03] focus-within:border-cyan-500/30 focus-within:bg-white/[0.05] transition-all duration-300">
                        <textarea
                            ref={textareaRef}
                            id="chat-input"
                            value={input}
                            onChange={e => setInput(e.target.value)}
                            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
                            placeholder={followUps.length > 0 && !isProcessing ? 'Ask a follow-up...' : 'Ask anything...'}
                            className="w-full min-h-[48px] max-h-[150px] resize-none bg-transparent px-4 py-3.5 pr-12 text-sm text-white placeholder:text-white/30 focus:outline-none"
                            rows={1}
                            disabled={isProcessing}
                        />

                        {/* Send button inside textarea */}
                        <button
                            onClick={() => handleSend()}
                            disabled={isProcessing || (!input.trim() && uploadedFiles.length === 0)}
                            className="absolute right-3 bottom-3 w-8 h-8 rounded-lg flex items-center justify-center transition-all duration-200
                                disabled:opacity-30 disabled:cursor-not-allowed
                                bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white shadow-lg shadow-cyan-500/20"
                        >
                            {isProcessing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                        </button>
                    </div>

                    {/* Toolbar Row */}
                    <div className="flex items-center justify-between mt-2.5">
                        <div className="flex items-center gap-2">
                            {/* Focus Mode */}
                            <FocusModePopover
                                value={focusMode}
                                onChange={setFocusMode}
                                open={focusOpen}
                                onToggle={() => setFocusOpen(!focusOpen)}
                            />

                            {/* Source Toggles */}
                            <SourceToggles active={activeSources} onToggle={toggleSource} />

                            {/* Attach */}
                            <input ref={fileInputRef} type="file" className="hidden" multiple accept=".pdf,.docx,.xlsx,.csv,.txt,.md"
                                onChange={e => { if (e.target.files) setUploadedFiles(prev => [...prev, ...Array.from(e.target.files!)]); }}
                            />
                            <button
                                onClick={() => fileInputRef.current?.click()}
                                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-all duration-200 bg-white/5 hover:bg-white/10 border border-white/10 hover:border-white/20 text-white/50 hover:text-white/70"
                            >
                                <Paperclip className="h-3.5 w-3.5" />
                            </button>
                        </div>

                        {/* Phase Indicator */}
                        <div className="flex items-center gap-2">
                            {phase !== 'idle' && (
                                <span className={`flex items-center gap-1.5 text-xs font-medium ${phaseLabel.color}`}>
                                    <span className="relative flex h-2 w-2">
                                        <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${phaseLabel.color.replace('text-', 'bg-')}`}></span>
                                        <span className={`relative inline-flex rounded-full h-2 w-2 ${phaseLabel.color.replace('text-', 'bg-')}`}></span>
                                    </span>
                                    {phaseLabel.text}
                                    {phase === 'executing' && ` (${executingProgress.done}/${executingProgress.total})`}
                                    <AnimatedDots />
                                </span>
                            )}
                            {phase === 'idle' && activeDealId && (
                                <span className="text-[10px] text-white/20">Deal {activeDealId.substring(0, 8)}</span>
                            )}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
