import { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import { Switch } from '@/components/ui/switch';
import {
    Key, Brain, Shield, Eye, EyeOff, Save,
    CheckCircle, XCircle, Loader2, Cpu, Cloud, RefreshCw,
    Database, Zap, AlertTriangle
} from 'lucide-react';

const API_BASE = 'http://localhost:8000';

const PROVIDER_OPTIONS = [
    { value: 'gemini', label: 'Google Gemini', icon: Cloud, color: 'text-blue-500' },
    { value: 'openai', label: 'OpenAI', icon: Cloud, color: 'text-green-500' },
    { value: 'mistral', label: 'Mistral AI', icon: Cloud, color: 'text-orange-500' },
    { value: 'ollama', label: 'Ollama (Local)', icon: Cpu, color: 'text-purple-500' },
    { value: 'lmstudio', label: 'LM Studio (Local)', icon: Cpu, color: 'text-pink-500' },
];

const AGENTS = [
    { name: 'project_manager', label: '🧩 Scrum Master / PM', desc: 'Reasoning planner — identifies data needs, asks questions, creates risk-annotated task plans', complexity: 'high' },
    { name: 'financial_analyst', label: 'Financial Analyst', desc: 'DCF, valuation, investment thesis', complexity: 'high' },
    { name: 'valuation_agent', label: 'Valuation Agent', desc: 'Multi-method valuation math', complexity: 'high' },
    { name: 'legal_advisor', label: 'Legal Advisor', desc: 'Contract analysis, legal risk', complexity: 'high' },
    { name: 'risk_assessor', label: 'Risk Assessor', desc: '7-category risk framework', complexity: 'high' },
    { name: 'debate_moderator', label: 'Debate Moderator', desc: 'Synthesizing viewpoints', complexity: 'high' },
    { name: 'market_researcher', label: 'Market Researcher', desc: 'Market sizing, competitor lists', complexity: 'low' },
    { name: 'market_risk_agent', label: 'Market Risk Agent', desc: 'Rule-based risk scoring', complexity: 'low' },
    { name: 'compliance_agent', label: 'Compliance Agent', desc: 'Checklist processing', complexity: 'low' },
    { name: 'scoring_agent', label: 'Scoring Agent', desc: 'Aggregation + formatting', complexity: 'low' },
    { name: 'pageindex', label: '📄 PageIndex (RAG)', desc: 'Knowledge Base search and Retrieval QA', complexity: 'high' },
];

interface MCPProviderConfig {
    key: string;
    status: 'idle' | 'testing' | 'connected' | 'error';
    errorMsg?: string;
    latency?: number;
}

const MCP_PROVIDERS_CONFIG = [
    {
        id: 'finnhub',
        name: 'Finnhub',
        description: 'Real-time stock prices, financials, earnings, news, analyst ratings',
        icon: '📈',
        defaultKey: 'd6jaci9r01ql467iudngd6jaci9r01ql467iudo0',
        docsUrl: 'https://finnhub.io',
        capabilities: ['Stock Price', 'Financials', 'Earnings', 'News', 'Sentiment'],
    },
    {
        id: 'massive',
        name: 'Massive.com',
        description: 'Enterprise company intelligence, market research, alternative data',
        icon: '🏢',
        defaultKey: 'MQt6ceeL69pB9SekWRo78nNA9QFXFujo',
        docsUrl: 'https://massive.com',
        capabilities: ['Company Data', 'Market Research', 'Alternative Data', 'People Data'],
    },
    {
        id: 'serper',
        name: 'Serper.dev',
        description: 'Fast Google Search API for agentic web retrieval',
        icon: '🔍',
        defaultKey: '',
        docsUrl: 'https://serper.dev',
        capabilities: ['Web Search', 'News Search', 'Places'],
    },
    {
        id: 'searxng',
        name: 'SearXNG',
        description: 'Privacy-respecting meta-search engine (Self-hosted)',
        icon: '♻️',
        defaultKey: 'http://localhost:8080',
        docsUrl: 'https://docs.searxng.org',
        capabilities: ['Web Search', 'Private Search'],
    },
    {
        id: 'ddg',
        name: 'DuckDuckGo',
        description: 'Privacy-focused search (No API key required)',
        icon: '🦆',
        defaultKey: 'NO_KEY_REQUIRED',
        docsUrl: 'https://duckduckgo.com',
        capabilities: ['Web Search'],
    },
];

interface SettingsState {
    // API Keys
    gemini_api_key: string;
    openai_api_key: string;
    mistral_api_key: string;
    // Cloud Model Names
    gemini_model: string;
    openai_model: string;
    mistral_model: string;
    // Local LLMs
    ollama_base_url: string;
    ollama_model: string;
    lmstudio_base_url: string;
    lmstudio_model: string;
    // Default provider
    default_llm_provider: string;
    // Agent routing
    agent_routing: Record<string, string>;
    // PageIndex
    pageindex_mode: string;
    // Gateway Cost Controls
    gateway: {
        gemini_max_rpm: number;
        gemini_max_tpm: number;
        openai_max_rpm: number;
        openai_max_tpm: number;
        mistral_max_rpm: number;
        mistral_max_tpm: number;
        cache_enabled: boolean;
        hybrid_compression: boolean;
        daily_budget_usd: number;
    };
    // Web Search
    search_priority: string[];
    serper_api_key: string;
    searxng_instance_url: string;
    searxng_api_key: string;
}

export function SettingsPage() {
    const [settings, setSettings] = useState<SettingsState>({
        gemini_api_key: '',
        openai_api_key: '',
        mistral_api_key: '',
        gemini_model: '',
        openai_model: '',
        mistral_model: '',
        ollama_base_url: 'http://localhost:11434',
        ollama_model: 'llama3',
        lmstudio_base_url: 'http://localhost:1234/v1',
        lmstudio_model: 'local-model',
        default_llm_provider: 'gemini',
        agent_routing: {
            financial_analyst: 'gemini',
            valuation_agent: 'gemini',
            legal_advisor: 'gemini',
            risk_assessor: 'gemini',
            debate_moderator: 'gemini',
            market_researcher: 'ollama',
            market_risk_agent: 'ollama',
            compliance_agent: 'ollama',
            scoring_agent: 'ollama',
            pageindex: 'gemini',
        },
        pageindex_mode: 'local',
        gateway: {
            gemini_max_rpm: 12,
            gemini_max_tpm: 80000,
            openai_max_rpm: 50,
            openai_max_tpm: 150000,
            mistral_max_rpm: 5,
            mistral_max_tpm: 400000,
            cache_enabled: true,
            hybrid_compression: true,
            daily_budget_usd: 0,
        },
        search_priority: ['serper', 'searxng', 'ddg'],
        serper_api_key: '',
        searxng_instance_url: 'http://localhost:8080',
        searxng_api_key: '',
    });

    const [showKeys, setShowKeys] = useState<Record<string, boolean>>({});
    const [saving, setSaving] = useState(false);
    const [saved, setSaved] = useState(false);
    const [ollamaStatus, setOllamaStatus] = useState<'checking' | 'online' | 'offline'>('checking');
    const [lmstudioStatus, setLmstudioStatus] = useState<'checking' | 'online' | 'offline'>('checking');
    const [availableModels, setAvailableModels] = useState<Record<string, { status: string; models: Array<{ id: string; name: string;[k: string]: any }> }>>({});
    const [fetchingModels, setFetchingModels] = useState(false);
    const [mcpState, setMcpState] = useState<Record<string, MCPProviderConfig>>(() =>
        Object.fromEntries(
            MCP_PROVIDERS_CONFIG.map(p => [p.id, { key: p.defaultKey, status: 'idle' as const }])
        )
    );

    const [cloudApiTestStatus, setCloudApiTestStatus] = useState<Record<string, { status: 'idle' | 'testing' | 'connected' | 'error', errorMsg?: string }>>({
        gemini: { status: 'idle' },
        openai: { status: 'idle' },
        mistral: { status: 'idle' }
    });

    // Fetch live model lists from all providers
    const fetchModels = useCallback(async () => {
        setFetchingModels(true);
        try {
            const res = await fetch(`${API_BASE}/api/v1/models/available`, { signal: AbortSignal.timeout(15000) });
            if (res.ok) {
                const data = await res.json();
                setAvailableModels(data);
                // Update local LLM status from the response
                if (data.ollama) setOllamaStatus(data.ollama.status === 'online' ? 'online' : 'offline');
                if (data.lmstudio) setLmstudioStatus(data.lmstudio.status === 'online' ? 'online' : 'offline');

                // Auto-select first model if current selection is empty or not in live list
                setSettings(prev => {
                    const updates: Record<string, string> = {};
                    const map: [string, keyof SettingsState][] = [
                        ['gemini', 'gemini_model'],
                        ['openai', 'openai_model'],
                        ['mistral', 'mistral_model'],
                        ['ollama', 'ollama_model'],
                        ['lmstudio', 'lmstudio_model'],
                    ];
                    for (const [provider, field] of map) {
                        const models = data[provider]?.models || [];
                        const cur = prev[field] as string || '';
                        if (models.length > 0 && (!cur || !models.some((m: any) => m.id === cur))) {
                            updates[field as string] = models[0].id;
                        }
                    }
                    return Object.keys(updates).length ? { ...prev, ...updates } : prev;
                });
            }
        } catch (e) {
            console.error('Failed to fetch models', e);
        }
        setFetchingModels(false);
    }, []);

    async function testCloudApi(providerId: string) {
        let apiKey = '';
        if (providerId === 'gemini') apiKey = settings.gemini_api_key;
        if (providerId === 'openai') apiKey = settings.openai_api_key;
        if (providerId === 'mistral') apiKey = settings.mistral_api_key;

        if (!apiKey) {
            setCloudApiTestStatus(prev => ({ ...prev, [providerId]: { status: 'error', errorMsg: 'API Key is missing' } }));
            return;
        }

        setCloudApiTestStatus(prev => ({ ...prev, [providerId]: { status: 'testing' } }));
        try {
            const res = await fetch(`${API_BASE}/api/v1/models/test`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ provider: providerId, api_key: apiKey }),
            });
            const data = await res.json();
            if (data.ok && data.models) {
                setCloudApiTestStatus(prev => ({
                    ...prev,
                    [providerId]: { status: 'connected' },
                }));
                // Update live models for this provider so Cloud Model Selection immediately populates
                setAvailableModels(prev => ({
                    ...prev,
                    [providerId]: { status: 'online', models: data.models }
                }));
                // Auto-select first model if none is currently selected
                if (data.models.length > 0) {
                    setSettings(prev => {
                        const cur = prev[`${providerId}_model` as keyof typeof prev];
                        if (!cur || !data.models.some((m: any) => m.id === cur)) {
                            return { ...prev, [`${providerId}_model`]: data.models[0].id };
                        }
                        return prev;
                    });
                }
            } else {
                setCloudApiTestStatus(prev => ({
                    ...prev,
                    [providerId]: { status: 'error', errorMsg: data.error || 'Invalid API Key' },
                }));
            }
        } catch (e: any) {
            setCloudApiTestStatus(prev => ({
                ...prev,
                [providerId]: { status: 'error', errorMsg: e.message || 'Network error' },
            }));
        }
    }

    // Check local LLM status on mount
    useEffect(() => {
        checkLocalLLMs();
        loadSettings();
        fetchModels();
    }, []);

    async function checkLocalLLMs() {
        // Check Ollama
        try {
            const res = await fetch(`${settings.ollama_base_url}/api/tags`, { signal: AbortSignal.timeout(3000) });
            setOllamaStatus(res.ok ? 'online' : 'offline');
        } catch { setOllamaStatus('offline'); }

        // Check LM Studio
        try {
            const res = await fetch(`${settings.lmstudio_base_url}/models`, { signal: AbortSignal.timeout(3000) });
            setLmstudioStatus(res.ok ? 'online' : 'offline');
        } catch { setLmstudioStatus('offline'); }
    }

    async function loadSettings() {
        try {
            const res = await fetch(`${API_BASE}/api/v1/settings`);
            if (res.ok) {
                const data = await res.json();
                setSettings(prev => ({ ...prev, ...data }));
            }
        } catch { /* Backend may not be running yet */ }
    }

    async function saveSettings() {
        setSaving(true);
        try {
            const res = await fetch(`${API_BASE}/api/v1/settings`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(settings),
            });
            if (res.ok) {
                setSaved(true);
                setTimeout(() => setSaved(false), 3000);
            }
        } catch (e) {
            console.error('Failed to save settings', e);
        }
        setSaving(false);
    }

    function updateField(field: string, value: string) {
        setSettings(prev => ({ ...prev, [field]: value }));
    }

    function updateRouting(agent: string, provider: string) {
        setSettings(prev => ({
            ...prev,
            agent_routing: { ...prev.agent_routing, [agent]: provider },
        }));
    }

    function updateAllRouting(provider: string) {
        setSettings(prev => {
            const nextRouting = { ...prev.agent_routing };
            AGENTS.forEach(ag => {
                nextRouting[ag.name] = provider;
            });
            return {
                ...prev,
                agent_routing: nextRouting,
                default_llm_provider: provider
            };
        });
    }

    function toggleShowKey(key: string) {
        setShowKeys(prev => ({ ...prev, [key]: !prev[key] }));
    }

    async function initializeMcp(providerId: string) {
        let key = mcpState[providerId]?.key;
        if (providerId === 'serper') key = settings.serper_api_key;
        if (providerId === 'searxng') key = settings.searxng_instance_url;

        if (!key && providerId !== 'ddg') return;
        setMcpState(prev => ({ ...prev, [providerId]: { ...prev[providerId], status: 'testing' } }));
        try {
            const res = await fetch(`${API_BASE}/api/v1/mcp/initialize`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ provider: providerId, api_key: key }),
            });
            const data = await res.json();
            if (data.ok) {
                setMcpState(prev => ({
                    ...prev,
                    [providerId]: { ...prev[providerId], status: 'connected', latency: data.latency_ms },
                }));
            } else {
                setMcpState(prev => ({
                    ...prev,
                    [providerId]: { ...prev[providerId], status: 'error', errorMsg: data.error || 'Unknown error' },
                }));
            }
        } catch (e: any) {
            setMcpState(prev => ({
                ...prev,
                [providerId]: { ...prev[providerId], status: 'error', errorMsg: e.message },
            }));
        }
    }

    function StatusDot({ status }: { status: 'checking' | 'online' | 'offline' }) {
        if (status === 'checking') return <Loader2 className="h-4 w-4 animate-spin text-slate-400" />;
        if (status === 'online') return <CheckCircle className="h-4 w-4 text-green-500" />;
        return <XCircle className="h-4 w-4 text-red-400" />;
    }

    return (
        <div className="space-y-6">
            <div className="flex flex-col space-y-2">
                <h2 className="text-3xl font-bold tracking-tight bg-gradient-to-r from-violet-600 to-fuchsia-600 bg-clip-text text-transparent dark:from-violet-400 dark:to-fuchsia-400">
                    Settings
                </h2>
                <p className="text-muted-foreground">
                    Configure API keys, local LLMs, and model routing for your agents.
                </p>
            </div>

            {/* ===== API Keys Section ===== */}
            <Card className="border-t-4 border-t-blue-500">
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Key className="h-5 w-5 text-blue-500" />
                        Cloud API Keys
                    </CardTitle>
                    <CardDescription>Enter your API keys for cloud LLM providers.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    {/* Gemini */}
                    <div className="space-y-2">
                        <Label className="flex items-center gap-2">
                            <Cloud className="h-4 w-4 text-blue-500" /> Google Gemini API Key
                        </Label>
                        {cloudApiTestStatus.gemini?.status === 'error' && cloudApiTestStatus.gemini?.errorMsg && (
                            <div className="flex items-start gap-1.5 rounded-md bg-red-50 dark:bg-red-950/20 p-2 text-xs text-red-600">
                                <AlertTriangle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
                                {cloudApiTestStatus.gemini.errorMsg}
                            </div>
                        )}
                        <div className="flex gap-2">
                            <div className="relative flex-1">
                                <Input
                                    id="gemini-key"
                                    type={showKeys['gemini'] ? 'text' : 'password'}
                                    value={settings.gemini_api_key}
                                    onChange={e => {
                                        updateField('gemini_api_key', e.target.value);
                                        setCloudApiTestStatus(prev => ({ ...prev, gemini: { status: 'idle' } }));
                                    }}
                                    placeholder="AIzaSy..."
                                    className="pr-10"
                                />
                                <button onClick={() => toggleShowKey('gemini')} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
                                    {showKeys['gemini'] ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                                </button>
                            </div>
                            <Button
                                size="sm"
                                variant={cloudApiTestStatus.gemini?.status === 'connected' ? 'outline' : 'default'}
                                onClick={() => testCloudApi('gemini')}
                                disabled={cloudApiTestStatus.gemini?.status === 'testing' || !settings.gemini_api_key}
                                className="shrink-0"
                            >
                                {cloudApiTestStatus.gemini?.status === 'testing' ? (
                                    <><Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />Testing...</>
                                ) : cloudApiTestStatus.gemini?.status === 'connected' ? (
                                    <><CheckCircle className="h-3.5 w-3.5 mr-1.5" />Connected</>
                                ) : (
                                    <><Zap className="h-3.5 w-3.5 mr-1.5" />Initialize & Test</>
                                )}
                            </Button>
                        </div>
                    </div>
                    <Separator />

                    {/* OpenAI */}
                    <div className="space-y-2">
                        <Label className="flex items-center gap-2">
                            <Cloud className="h-4 w-4 text-green-500" /> OpenAI API Key
                        </Label>
                        {cloudApiTestStatus.openai?.status === 'error' && cloudApiTestStatus.openai?.errorMsg && (
                            <div className="flex items-start gap-1.5 rounded-md bg-red-50 dark:bg-red-950/20 p-2 text-xs text-red-600">
                                <AlertTriangle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
                                {cloudApiTestStatus.openai.errorMsg}
                            </div>
                        )}
                        <div className="flex gap-2">
                            <div className="relative flex-1">
                                <Input
                                    id="openai-key"
                                    type={showKeys['openai'] ? 'text' : 'password'}
                                    value={settings.openai_api_key}
                                    onChange={e => {
                                        updateField('openai_api_key', e.target.value);
                                        setCloudApiTestStatus(prev => ({ ...prev, openai: { status: 'idle' } }));
                                    }}
                                    placeholder="sk-..."
                                    className="pr-10"
                                />
                                <button onClick={() => toggleShowKey('openai')} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
                                    {showKeys['openai'] ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                                </button>
                            </div>
                            <Button
                                size="sm"
                                variant={cloudApiTestStatus.openai?.status === 'connected' ? 'outline' : 'default'}
                                onClick={() => testCloudApi('openai')}
                                disabled={cloudApiTestStatus.openai?.status === 'testing' || !settings.openai_api_key}
                                className="shrink-0"
                            >
                                {cloudApiTestStatus.openai?.status === 'testing' ? (
                                    <><Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />Testing...</>
                                ) : cloudApiTestStatus.openai?.status === 'connected' ? (
                                    <><CheckCircle className="h-3.5 w-3.5 mr-1.5" />Connected</>
                                ) : (
                                    <><Zap className="h-3.5 w-3.5 mr-1.5" />Initialize & Test</>
                                )}
                            </Button>
                        </div>
                    </div>
                    <Separator />

                    {/* Mistral */}
                    <div className="space-y-2">
                        <Label className="flex items-center gap-2">
                            <Cloud className="h-4 w-4 text-orange-500" /> Mistral API Key
                        </Label>
                        {cloudApiTestStatus.mistral?.status === 'error' && cloudApiTestStatus.mistral?.errorMsg && (
                            <div className="flex items-start gap-1.5 rounded-md bg-red-50 dark:bg-red-950/20 p-2 text-xs text-red-600">
                                <AlertTriangle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
                                {cloudApiTestStatus.mistral.errorMsg}
                            </div>
                        )}
                        <div className="flex gap-2">
                            <div className="relative flex-1">
                                <Input
                                    id="mistral-key"
                                    type={showKeys['mistral'] ? 'text' : 'password'}
                                    value={settings.mistral_api_key}
                                    onChange={e => {
                                        updateField('mistral_api_key', e.target.value);
                                        setCloudApiTestStatus(prev => ({ ...prev, mistral: { status: 'idle' } }));
                                    }}
                                    placeholder="..."
                                    className="pr-10"
                                />
                                <button onClick={() => toggleShowKey('mistral')} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
                                    {showKeys['mistral'] ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                                </button>
                            </div>
                            <Button
                                size="sm"
                                variant={cloudApiTestStatus.mistral?.status === 'connected' ? 'outline' : 'default'}
                                onClick={() => testCloudApi('mistral')}
                                disabled={cloudApiTestStatus.mistral?.status === 'testing' || !settings.mistral_api_key}
                                className="shrink-0"
                            >
                                {cloudApiTestStatus.mistral?.status === 'testing' ? (
                                    <><Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />Testing...</>
                                ) : cloudApiTestStatus.mistral?.status === 'connected' ? (
                                    <><CheckCircle className="h-3.5 w-3.5 mr-1.5" />Connected</>
                                ) : (
                                    <><Zap className="h-3.5 w-3.5 mr-1.5" />Initialize & Test</>
                                )}
                            </Button>
                        </div>
                    </div>
                </CardContent>
            </Card>

            {/* ===== MCP Data Providers Section ===== */}
            <Card className="border-t-4 border-t-teal-500">
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Database className="h-5 w-5 text-teal-500" />
                        MCP Data Providers
                    </CardTitle>
                    <CardDescription>
                        Connect live financial data sources. When configured, the Scrum Master will auto-fetch
                        market data, financials, and news — reducing your manual data entry burden.
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    {MCP_PROVIDERS_CONFIG.map(provider => {
                        const cfg = mcpState[provider.id];
                        const status = cfg?.status ?? 'idle';
                        return (
                            <div key={provider.id} className="rounded-lg border p-4 space-y-3">
                                <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-2">
                                        <span className="text-xl">{provider.icon}</span>
                                        <div>
                                            <p className="font-semibold text-sm">{provider.name}</p>
                                            <p className="text-xs text-muted-foreground">{provider.description}</p>
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        {status === 'connected' && (
                                            <Badge className="bg-green-100 text-green-700 border-green-300 gap-1">
                                                <CheckCircle className="h-3 w-3" /> Connected
                                                {cfg.latency ? ` (${cfg.latency}ms)` : ''}
                                            </Badge>
                                        )}
                                        {status === 'error' && (
                                            <Badge variant="destructive" className="gap-1">
                                                <XCircle className="h-3 w-3" /> Error
                                            </Badge>
                                        )}
                                        {status === 'idle' && (
                                            <Badge variant="outline" className="text-slate-500">Not initialized</Badge>
                                        )}
                                        {status === 'testing' && (
                                            <Badge variant="outline" className="gap-1">
                                                <Loader2 className="h-3 w-3 animate-spin" /> Testing...
                                            </Badge>
                                        )}
                                    </div>
                                </div>

                                <div className="flex flex-wrap gap-1">
                                    {provider.capabilities.map(cap => (
                                        <Badge key={cap} variant="secondary" className="text-[10px] px-1.5 py-0">
                                            <Zap className="h-2.5 w-2.5 mr-1" />{cap}
                                        </Badge>
                                    ))}
                                </div>

                                {status === 'error' && cfg.errorMsg && (
                                    <div className="flex items-start gap-1.5 rounded-md bg-red-50 dark:bg-red-950/20 p-2 text-xs text-red-600">
                                        <AlertTriangle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
                                        {cfg.errorMsg}
                                    </div>
                                )}

                                <div className="flex gap-2">
                                    <div className="relative flex-1">
                                        <Input
                                            id={`mcp-key-${provider.id}`}
                                            type={showKeys[`mcp-${provider.id}`] ? 'text' : 'password'}
                                            value={
                                                provider.id === 'serper' ? settings.serper_api_key :
                                                    provider.id === 'searxng' ? settings.searxng_instance_url :
                                                        cfg?.key ?? ''
                                            }
                                            onChange={e => {
                                                const val = e.target.value;
                                                if (provider.id === 'serper') updateField('serper_api_key', val);
                                                else if (provider.id === 'searxng') updateField('searxng_instance_url', val);
                                                else setMcpState(prev => ({
                                                    ...prev,
                                                    [provider.id]: { ...prev[provider.id], key: val, status: 'idle' },
                                                }));
                                            }}
                                            placeholder={
                                                provider.id === 'searxng' ? 'Instance URL (e.g. http://localhost:8080)' :
                                                    `${provider.name} API Key`
                                            }
                                            className="pr-10 font-mono text-xs"
                                        />
                                        <button
                                            onClick={() => toggleShowKey(`mcp-${provider.id}`)}
                                            className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                                        >
                                            {showKeys[`mcp-${provider.id}`] ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                                        </button>
                                    </div>
                                    <Button
                                        size="sm"
                                        variant={status === 'connected' ? 'outline' : 'default'}
                                        onClick={() => initializeMcp(provider.id)}
                                        disabled={status === 'testing' || !cfg?.key}
                                        className="shrink-0"
                                    >
                                        {status === 'testing' ? (
                                            <><Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />Testing...</>
                                        ) : status === 'connected' ? (
                                            <><CheckCircle className="h-3.5 w-3.5 mr-1.5" />Re-test</>
                                        ) : (
                                            <><Zap className="h-3.5 w-3.5 mr-1.5" />Initialize & Test</>
                                        )}
                                    </Button>
                                </div>
                            </div>
                        );
                    })}
                </CardContent>
            </Card>

            {/* ===== Web Search Strategy Section ===== */}
            <Card className="border-t-4 border-t-orange-500 overflow-hidden">
                <CardHeader className="pb-3">
                    <CardTitle className="flex items-center gap-2">
                        <RefreshCw className="h-5 w-5 text-orange-500" />
                        Search Fallback Strategy
                    </CardTitle>
                    <CardDescription>
                        Define the priority order for web search. If the primary provider fails,
                        the agents will automatically fallback to the next available tool.
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    <div className="flex flex-col gap-2">
                        {settings.search_priority.map((id, index) => {
                            const provider = MCP_PROVIDERS_CONFIG.find(p => p.id === id);
                            if (!provider) return null;
                            return (
                                <div
                                    key={id}
                                    className="flex items-center justify-between p-3 rounded-md border bg-slate-50/50 dark:bg-slate-900/50 hover:border-orange-200 transition-colors group"
                                >
                                    <div className="flex items-center gap-3">
                                        <div className="flex items-center justify-center w-6 h-6 rounded bg-orange-100 text-orange-700 text-xs font-bold">
                                            {index + 1}
                                        </div>
                                        <span className="text-xl">{provider.icon}</span>
                                        <div>
                                            <p className="font-medium text-sm">{provider.name}</p>
                                            <p className="text-[10px] text-muted-foreground uppercase tracking-tight">
                                                {index === 0 ? 'Primary' : `Fallback ${index}`}
                                            </p>
                                        </div>
                                    </div>
                                    <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                        <Button
                                            size="icon"
                                            variant="ghost"
                                            className="h-7 w-7"
                                            disabled={index === 0}
                                            onClick={() => {
                                                const next = [...settings.search_priority];
                                                [next[index], next[index - 1]] = [next[index - 1], next[index]];
                                                updateField('search_priority', next as any);
                                            }}
                                        >
                                            <Zap className="h-3 w-3 rotate-180" />
                                        </Button>
                                        <Button
                                            size="icon"
                                            variant="ghost"
                                            className="h-7 w-7"
                                            disabled={index === settings.search_priority.length - 1}
                                            onClick={() => {
                                                const next = [...settings.search_priority];
                                                [next[index], next[index + 1]] = [next[index + 1], next[index]];
                                                updateField('search_priority', next as any);
                                            }}
                                        >
                                            <Zap className="h-3 w-3" />
                                        </Button>
                                    </div>
                                </div>
                            );
                        })}
                    </div>

                    <div className="flex items-center gap-2 p-3 bg-amber-50 dark:bg-amber-950/20 border border-amber-100 dark:border-amber-900/30 rounded-md text-[11px] text-amber-700 dark:text-amber-400">
                        <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
                        <span>
                            <strong>Note:</strong> DuckDuckGo (DDG) serves as the "Iron-Clad Fallback" since it
                            requires no API key. We recommend keeping it in the list to ensure 24/7 reliability.
                        </span>
                    </div>
                </CardContent>
            </Card>

            {/* ===== Cloud Model Selection ===== */}
            <Card className="border-t-4 border-t-cyan-500">
                <CardHeader>
                    <div className="flex items-center justify-between">
                        <div>
                            <CardTitle className="flex items-center gap-2">
                                <Cloud className="h-5 w-5 text-cyan-500" />
                                Cloud Model Selection
                            </CardTitle>
                            <CardDescription>Models are fetched live from each provider's API. Click Refresh to update.</CardDescription>
                        </div>
                        <Button variant="outline" size="sm" onClick={fetchModels} disabled={fetchingModels} className="gap-1.5">
                            <RefreshCw className={`h-3.5 w-3.5 ${fetchingModels ? 'animate-spin' : ''}`} /> Refresh Models
                        </Button>
                    </div>
                </CardHeader>
                <CardContent className="space-y-4">
                    <div className="grid grid-cols-3 gap-4">
                        {/* Gemini */}
                        <div className="space-y-1">
                            <Label htmlFor="gemini-model" className="text-xs flex items-center gap-1">
                                Gemini Model
                                {availableModels.gemini && (
                                    <Badge variant="outline" className="text-[9px] px-1">
                                        {availableModels.gemini.models.length} available
                                    </Badge>
                                )}
                            </Label>
                            <select
                                id="gemini-model"
                                value={settings.gemini_model}
                                onChange={e => updateField('gemini_model', e.target.value)}
                                className="h-9 w-full rounded-md border bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                            >
                                {availableModels.gemini?.models?.length ? (
                                    availableModels.gemini.models.map(m => (
                                        <option key={m.id} value={m.id}>{m.name || m.id}</option>
                                    ))
                                ) : fetchingModels ? (
                                    <option value="">Loading models...</option>
                                ) : availableModels.gemini?.status === 'no_key' ? (
                                    <option value="">Set Gemini API key first</option>
                                ) : (
                                    <option value="">Click Refresh Models</option>
                                )}
                            </select>
                        </div>
                        {/* OpenAI */}
                        <div className="space-y-1">
                            <Label htmlFor="openai-model" className="text-xs flex items-center gap-1">
                                OpenAI Model
                                {availableModels.openai && (
                                    <Badge variant="outline" className="text-[9px] px-1">
                                        {availableModels.openai.models.length} available
                                    </Badge>
                                )}
                            </Label>
                            <select
                                id="openai-model"
                                value={settings.openai_model}
                                onChange={e => updateField('openai_model', e.target.value)}
                                className="h-9 w-full rounded-md border bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                            >
                                {availableModels.openai?.models?.length ? (
                                    availableModels.openai.models.map(m => (
                                        <option key={m.id} value={m.id}>{m.name || m.id}</option>
                                    ))
                                ) : fetchingModels ? (
                                    <option value="">Loading models...</option>
                                ) : availableModels.openai?.status === 'no_key' ? (
                                    <option value="">Set OpenAI API key first</option>
                                ) : (
                                    <option value="">Click Refresh Models</option>
                                )}
                            </select>
                        </div>
                        {/* Mistral */}
                        <div className="space-y-1">
                            <Label htmlFor="mistral-model" className="text-xs flex items-center gap-1">
                                Mistral Model
                                {availableModels.mistral && (
                                    <Badge variant="outline" className="text-[9px] px-1">
                                        {availableModels.mistral.models.length} available
                                    </Badge>
                                )}
                            </Label>
                            <select
                                id="mistral-model"
                                value={settings.mistral_model}
                                onChange={e => updateField('mistral_model', e.target.value)}
                                className="h-9 w-full rounded-md border bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                            >
                                {availableModels.mistral?.models?.length ? (
                                    availableModels.mistral.models.map(m => (
                                        <option key={m.id} value={m.id}>{m.name || m.id}</option>
                                    ))
                                ) : fetchingModels ? (
                                    <option value="">Loading models...</option>
                                ) : availableModels.mistral?.status === 'no_key' ? (
                                    <option value="">Set Mistral API key first</option>
                                ) : (
                                    <option value="">Click Refresh Models</option>
                                )}
                            </select>
                        </div>
                    </div>
                </CardContent>
            </Card>

            {/* ===== Local LLMs Section ===== */}
            <Card className="border-t-4 border-t-purple-500">
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Cpu className="h-5 w-5 text-purple-500" />
                        Local LLMs
                    </CardTitle>
                    <CardDescription>Configure Ollama and LM Studio for local inference on your GPU.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                    {/* Ollama */}
                    <div className="rounded-lg border p-4 space-y-3">
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                                <h4 className="font-semibold">Ollama</h4>
                                <StatusDot status={ollamaStatus} />
                                <span className="text-xs text-muted-foreground">
                                    {ollamaStatus === 'online' ? `Running (${availableModels.ollama?.models?.length || 0} models)` : ollamaStatus === 'offline' ? 'Not detected' : 'Checking...'}
                                </span>
                            </div>
                            <Button variant="ghost" size="sm" onClick={() => { checkLocalLLMs(); fetchModels(); }}>Refresh</Button>
                        </div>
                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-1">
                                <Label htmlFor="ollama-url" className="text-xs">Base URL</Label>
                                <Input id="ollama-url" value={settings.ollama_base_url} onChange={e => updateField('ollama_base_url', e.target.value)} placeholder="http://localhost:11434" />
                            </div>
                            <div className="space-y-1">
                                <Label htmlFor="ollama-model" className="text-xs">Model</Label>
                                {availableModels.ollama?.models?.length ? (
                                    <select
                                        id="ollama-model"
                                        value={settings.ollama_model}
                                        onChange={e => updateField('ollama_model', e.target.value)}
                                        className="h-9 w-full rounded-md border bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                                    >
                                        {availableModels.ollama.models.map(m => (
                                            <option key={m.id} value={m.id}>
                                                {m.name}{m.parameter_size ? ` (${m.parameter_size})` : ''}
                                            </option>
                                        ))}
                                    </select>
                                ) : (
                                    <Input id="ollama-model" value={settings.ollama_model} onChange={e => updateField('ollama_model', e.target.value)} placeholder="llama3" />
                                )}
                            </div>
                        </div>
                    </div>

                    {/* LM Studio */}
                    <div className="rounded-lg border p-4 space-y-3">
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                                <h4 className="font-semibold">LM Studio</h4>
                                <StatusDot status={lmstudioStatus} />
                                <span className="text-xs text-muted-foreground">
                                    {lmstudioStatus === 'online' ? `Running (${availableModels.lmstudio?.models?.length || 0} models)` : lmstudioStatus === 'offline' ? 'Not detected' : 'Checking...'}
                                </span>
                            </div>
                        </div>
                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-1">
                                <Label htmlFor="lms-url" className="text-xs">Base URL</Label>
                                <Input id="lms-url" value={settings.lmstudio_base_url} onChange={e => updateField('lmstudio_base_url', e.target.value)} placeholder="http://localhost:1234/v1" />
                            </div>
                            <div className="space-y-1">
                                <Label htmlFor="lms-model" className="text-xs">Model</Label>
                                {availableModels.lmstudio?.models?.length ? (
                                    <select
                                        id="lms-model"
                                        value={settings.lmstudio_model}
                                        onChange={e => updateField('lmstudio_model', e.target.value)}
                                        className="h-9 w-full rounded-md border bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                                    >
                                        {availableModels.lmstudio.models.map(m => (
                                            <option key={m.id} value={m.id}>{m.name || m.id}</option>
                                        ))}
                                    </select>
                                ) : (
                                    <Input id="lms-model" value={settings.lmstudio_model} onChange={e => updateField('lmstudio_model', e.target.value)} placeholder="local-model" />
                                )}
                            </div>
                        </div>
                    </div>
                </CardContent>
            </Card>

            {/* ===== Model Routing Section ===== */}
            <Card className="border-t-4 border-t-amber-500">
                <CardHeader>
                    <div className="flex items-center justify-between">
                        <div>
                            <CardTitle className="flex items-center gap-2">
                                <Brain className="h-5 w-5 text-amber-500" />
                                Agent → LLM Provider Routing
                            </CardTitle>
                            <CardDescription>
                                Assign each agent to a cloud or local LLM provider. Specific models are globally chosen above.
                            </CardDescription>
                        </div>
                        <div className="flex items-center gap-2">
                            <span className="text-sm font-medium text-muted-foreground whitespace-nowrap">Set all to:</span>
                            <select
                                onChange={e => {
                                    if (e.target.value) {
                                        updateAllRouting(e.target.value);
                                        e.target.value = ""; // reset dropdown
                                    }
                                }}
                                className="h-8 rounded-md border bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                                defaultValue=""
                            >
                                <option value="" disabled>Select provider...</option>
                                {PROVIDER_OPTIONS.map(opt => (
                                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                                ))}
                            </select>
                        </div>
                    </div>
                </CardHeader>
                <CardContent>
                    <div className="space-y-3">
                        {AGENTS.map(agent => (
                            <div key={agent.name} className="flex items-center justify-between rounded-lg border p-3 hover:bg-slate-50 dark:hover:bg-slate-900 transition-colors">
                                <div className="flex-1">
                                    <div className="flex items-center gap-2">
                                        <span className="font-medium text-sm">{agent.label}</span>
                                        <Badge variant={agent.complexity === 'high' ? 'default' : 'secondary'} className="text-[10px] px-1.5 py-0">
                                            {agent.complexity === 'high' ? '🧠 Complex' : '⚡ Light'}
                                        </Badge>
                                    </div>
                                    <span className="text-xs text-muted-foreground">{agent.desc}</span>
                                </div>
                                <select
                                    value={settings.agent_routing[agent.name] || 'gemini'}
                                    onChange={e => updateRouting(agent.name, e.target.value)}
                                    className="h-8 rounded-md border bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                                >
                                    {PROVIDER_OPTIONS.map(opt => (
                                        <option key={opt.value} value={opt.value}>{opt.label}</option>
                                    ))}
                                </select>
                            </div>
                        ))}
                    </div>
                </CardContent>
            </Card>

            {/* ===== PageIndex RAG Section ===== */}
            <Card className="border-t-4 border-t-emerald-500">
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Shield className="h-5 w-5 text-emerald-500" />
                        PageIndex RAG
                    </CardTitle>
                    <CardDescription>Knowledge base and document indexing mode.</CardDescription>
                </CardHeader>
                <CardContent>
                    <div className="flex items-center justify-between rounded-lg border p-4">
                        <div>
                            <p className="font-medium text-sm">Self-Hosted Mode</p>
                            <p className="text-xs text-muted-foreground">Store indexes locally — no cloud dependency, better privacy.</p>
                        </div>
                        <Switch
                            id="pageindex-local"
                            checked={settings.pageindex_mode === 'local'}
                            onCheckedChange={checked => updateField('pageindex_mode', checked ? 'local' : 'cloud')}
                        />
                    </div>
                </CardContent>
            </Card>

            {/* ===== LLM Gateway Cost Controls ===== */}
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-lg">⚡ LLM Gateway — Cost Control</CardTitle>
                    <CardDescription>Token budgeting, rate limits, caching, and hybrid compression. Set limits below your API tier (~85% recommended).</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    {(['gemini', 'openai', 'mistral'] as const).map(vendor => (
                        <div key={vendor} className="border rounded-lg p-3 space-y-2">
                            <p className="text-sm font-semibold capitalize">{vendor} Rate Limits</p>
                            <div className="grid grid-cols-2 gap-3">
                                <div>
                                    <label className="text-xs text-muted-foreground">Max RPM (requests/min)</label>
                                    <input
                                        type="number"
                                        value={settings.gateway[`${vendor}_max_rpm` as keyof typeof settings.gateway] as number}
                                        onChange={e => setSettings(prev => ({ ...prev, gateway: { ...prev.gateway, [`${vendor}_max_rpm`]: parseInt(e.target.value) || 0 } }))}
                                        className="w-full border rounded px-2 py-1 text-sm"
                                        min={1}
                                    />
                                </div>
                                <div>
                                    <label className="text-xs text-muted-foreground">Max TPM (tokens/min)</label>
                                    <input
                                        type="number"
                                        value={settings.gateway[`${vendor}_max_tpm` as keyof typeof settings.gateway] as number}
                                        onChange={e => setSettings(prev => ({ ...prev, gateway: { ...prev.gateway, [`${vendor}_max_tpm`]: parseInt(e.target.value) || 0 } }))}
                                        className="w-full border rounded px-2 py-1 text-sm"
                                        min={1000}
                                        step={1000}
                                    />
                                </div>
                            </div>
                        </div>
                    ))}
                    <div className="grid grid-cols-2 gap-4">
                        <div className="flex items-center justify-between rounded-lg border p-3">
                            <div>
                                <p className="font-medium text-sm">Response Caching</p>
                                <p className="text-xs text-muted-foreground">Cache deterministic (temp=0) responses</p>
                            </div>
                            <Switch
                                checked={settings.gateway.cache_enabled}
                                onCheckedChange={checked => setSettings(prev => ({ ...prev, gateway: { ...prev.gateway, cache_enabled: checked } }))}
                            />
                        </div>
                        <div className="flex items-center justify-between rounded-lg border p-3">
                            <div>
                                <p className="font-medium text-sm">Hybrid Compression</p>
                                <p className="text-xs text-muted-foreground">Local summarize → Cloud reason</p>
                            </div>
                            <Switch
                                checked={settings.gateway.hybrid_compression}
                                onCheckedChange={checked => setSettings(prev => ({ ...prev, gateway: { ...prev.gateway, hybrid_compression: checked } }))}
                            />
                        </div>
                    </div>
                </CardContent>
            </Card>

            {/* ===== Save Button ===== */}
            <div className="flex justify-end pb-8">
                <Button onClick={saveSettings} disabled={saving} size="lg" className="min-w-[200px]">
                    {saving ? (
                        <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Saving...</>
                    ) : saved ? (
                        <><CheckCircle className="mr-2 h-4 w-4" /> Saved!</>
                    ) : (
                        <><Save className="mr-2 h-4 w-4" /> Save Settings</>
                    )}
                </Button>
            </div>
        </div>
    );
}
