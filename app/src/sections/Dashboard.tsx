import { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
    BarChart, Activity, FileText, AlertTriangle, ChevronRight,
    Target, TrendingUp, DollarSign, Briefcase, RefreshCw,
    CheckCircle, Clock, Zap, X, Building2, Calendar,
    Cpu, Cloud, LayoutDashboard, ArrowLeft,
    Download, FileSpreadsheet, Presentation, Archive, Loader2
} from 'lucide-react';

const API_BASE = 'http://localhost:8005';

interface DealRecord {
    id: string;
    name: string;
    status: string;
    target_company: string;
    industry: string;
    current_stage: string;
    final_score: number | null;
    agents_run: string[];
    created_at: string;
    updated_at: string;
}

interface AgentEvent {
    agent_type: string;
    deal_id?: string;
    summary?: string;
    provider?: string;
    timestamp: string;
}

interface Metrics {
    total_deals: number;
    active_deals: number;
    completed_deals: number;
    avg_confidence: number;
    high_risk_alerts: number;
    deals: DealRecord[];
    agent_activity: AgentEvent[];
}

const AGENT_ICON_MAP: Record<string, typeof TrendingUp> = {
    financial_analyst: TrendingUp,
    legal_advisor: FileText,
    risk_assessor: AlertTriangle,
    market_researcher: BarChart,
    debate_moderator: Activity,
    valuation_agent: DollarSign,
};

const AGENT_COLOR_MAP: Record<string, string> = {
    financial_analyst: 'bg-blue-100 text-blue-600 dark:bg-blue-900 dark:text-blue-300',
    legal_advisor: 'bg-purple-100 text-purple-600 dark:bg-purple-900 dark:text-purple-300',
    risk_assessor: 'bg-amber-100 text-amber-600 dark:bg-amber-900 dark:text-amber-300',
    market_researcher: 'bg-green-100 text-green-600 dark:bg-green-900 dark:text-green-300',
    debate_moderator: 'bg-pink-100 text-pink-600 dark:bg-pink-900 dark:text-pink-300',
    valuation_agent: 'bg-indigo-100 text-indigo-600 dark:bg-indigo-900 dark:text-indigo-300',
};

function timeAgo(iso: string): string {
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins} min${mins > 1 ? 's' : ''} ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs} hr${hrs > 1 ? 's' : ''} ago`;
    return `${Math.floor(hrs / 24)} day${Math.floor(hrs / 24) > 1 ? 's' : ''} ago`;
}

function formatDate(iso: string): string {
    return new Date(iso).toLocaleString(undefined, {
        month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
    });
}

function getDealBadge(deal: DealRecord) {
    if (deal.final_score === null) {
        return <Badge variant="secondary"><Clock className="w-3 h-3 mr-1 inline" />In Progress</Badge>;
    }
    const pct = deal.final_score * 100;
    if (pct >= 75) return <Badge variant="default" className="bg-green-500 hover:bg-green-600">High Conviction</Badge>;
    if (pct >= 50) return <Badge variant="secondary">Moderate</Badge>;
    return <Badge variant="destructive">High Risk</Badge>;
}

// ─────────────────────────────────────────────
// Deal Detail Slide-Over Panel
// ─────────────────────────────────────────────
function DealDetailPanel({
    deal,
    activity,
    onClose,
    onNavigate,
}: {
    deal: DealRecord;
    activity: AgentEvent[];
    onClose: () => void;
    onNavigate?: (page: 'chat' | 'dashboard' | 'settings') => void;
}) {
    const [isGenerating, setIsGenerating] = useState(false);
    const [manifest, setManifest] = useState<any[]>([]);

    const fetchManifest = useCallback(async () => {
        try {
            const res = await fetch(`${API_BASE}/api/v1/deals/${deal.id}/documents`);
            if (res.ok) {
                const data = await res.json();
                setManifest(data.documents || []);
            }
        } catch (err) {
            console.error('Error fetching document manifest:', err);
        }
    }, [deal.id]);

    useEffect(() => {
        fetchManifest();
    }, [fetchManifest]);

    const handleGenerate = async () => {
        setIsGenerating(true);
        try {
            const res = await fetch(`${API_BASE}/api/v1/deals/${deal.id}/documents/generate`, { method: 'POST' });
            if (!res.ok) throw new Error('Generation failed');
            await fetchManifest();
        } catch (err) {
            console.error('Error generating reports:', err);
        } finally {
            setIsGenerating(false);
        }
    };

    const handleDownload = async (format: 'pdf' | 'pptx' | 'xlsx') => {
        try {
            // Hit the new download endpoint
            const res = await fetch(`${API_BASE}/api/v1/deals/${deal.id}/documents/${format}`);
            
            // Fallback to old endpoint if 404 (optional, but new system is better)
            if (res.status === 404) {
                console.warn(`Document ${format} not found in cache, falling back to legacy generator...`);
                const legacyRes = await fetch(`${API_BASE}/api/v1/deals/${deal.id}/report?format=${format}`);
                if (!legacyRes.ok) throw new Error('Download failed');
                await processDownloadResponse(legacyRes, format);
            } else if (res.ok) {
                await processDownloadResponse(res, format);
            } else {
                throw new Error('Download failed');
            }
        } catch (err) {
            console.error('Error downloading report:', err);
        }
    };

    const handleDownloadBundle = async () => {
        try {
            const res = await fetch(`${API_BASE}/api/v1/deals/${deal.id}/documents/bundle`);
            if (!res.ok) throw new Error('Bundle download failed');
            await processDownloadResponse(res, 'zip');
        } catch (err) {
            console.error('Error downloading bundle:', err);
        }
    };

    const processDownloadResponse = async (res: Response, ext: string) => {
        const blob = await res.blob();
        let filename = `DealForge_${deal.target_company.replace(/[^A-Za-z0-9]/g, '_')}.${ext}`;
        const disposition = res.headers.get('Content-Disposition');
        if (disposition) {
            const match = disposition.match(/filename="?([^";\n]+)"?/);
            if (match?.[1]) filename = match[1];
        }

        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        setTimeout(() => {
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
        }, 200);
    };

    const scorePercent = deal.final_score !== null ? Math.round(deal.final_score * 100) : null;
    const dealActivity = activity.filter(e => e.deal_id === deal.id);
    const uniqueAgents = [...new Set(deal.agents_run)];

    const scoreColor =
        scorePercent === null ? 'text-muted-foreground' :
            scorePercent >= 75 ? 'text-green-600 dark:text-green-400' :
                scorePercent >= 50 ? 'text-amber-600 dark:text-amber-400' :
                    'text-red-600 dark:text-red-400';

    return (
        /* Backdrop */
        <div
            className="fixed inset-0 z-50 flex items-start justify-end"
            style={{ background: 'rgba(0,0,0,0.4)' }}
            onClick={onClose}
        >
            {/* Panel */}
            <div
                className="relative h-full w-full max-w-lg bg-background shadow-2xl flex flex-col min-h-0 animate-in slide-in-from-right duration-300"
                onClick={e => e.stopPropagation()}
            >
                {/* Header */}
                <div className="flex items-start justify-between p-6 border-b">
                    <div className="space-y-1 flex-1 pr-4">
                        <div className="flex items-center gap-2 flex-wrap">
                            <h3 className="font-bold text-lg leading-tight">{deal.name}</h3>
                            {getDealBadge(deal)}
                        </div>
                        <p className="text-sm text-muted-foreground flex items-center gap-1.5">
                            <Building2 className="h-3.5 w-3.5" />
                            {deal.target_company} · {deal.industry}
                        </p>
                        <p className="text-xs text-muted-foreground flex items-center gap-1.5">
                            <Calendar className="h-3 w-3" />
                            Created {formatDate(deal.created_at)} · Updated {timeAgo(deal.updated_at)}
                        </p>
                    </div>
                    <Button variant="ghost" size="icon" onClick={onClose} className="flex-shrink-0">
                        <X className="h-4 w-4" />
                    </Button>
                </div>

                <ScrollArea className="flex-1 min-h-0" type="always">
                    <div className="space-y-6 p-6">
                        {/* Score Section */}
                        <div className="rounded-xl border p-4 space-y-3">
                            <h4 className="font-semibold text-sm">Deal Score</h4>
                            {scorePercent !== null ? (
                                <>
                                    <div className="flex items-end gap-2">
                                        <span className={`text-5xl font-black tabular-nums ${scoreColor}`}>
                                            {scorePercent}
                                        </span>
                                        <span className="text-muted-foreground text-lg mb-1">/100</span>
                                    </div>
                                    <Progress value={scorePercent} className="h-3" />
                                    <p className="text-xs text-muted-foreground">
                                        {scorePercent >= 75
                                            ? '✅ Strong conviction — agents recommend proceeding.'
                                            : scorePercent >= 50
                                                ? '⚠️ Moderate — further due diligence recommended.'
                                                : '🔴 High risk — significant concerns flagged by agents.'}
                                    </p>
                                </>
                            ) : (
                                <div className="text-muted-foreground text-sm flex items-center gap-2">
                                    <Clock className="h-4 w-4 animate-pulse" />
                                    Analysis still in progress — score pending.
                                </div>
                            )}
                        </div>

                        {/* Deal Status */}
                        <div className="rounded-xl border p-4 space-y-2">
                            <h4 className="font-semibold text-sm">Status</h4>
                            <div className="grid grid-cols-2 gap-3 text-sm">
                                <div>
                                    <span className="text-xs text-muted-foreground uppercase tracking-wide">Stage</span>
                                    <p className="font-medium capitalize mt-0.5">{deal.current_stage}</p>
                                </div>
                                <div>
                                    <span className="text-xs text-muted-foreground uppercase tracking-wide">Status</span>
                                    <p className="font-medium capitalize mt-0.5">{deal.status}</p>
                                </div>
                                <div>
                                    <span className="text-xs text-muted-foreground uppercase tracking-wide">Deal ID</span>
                                    <p className="font-mono text-xs mt-0.5 text-muted-foreground">{deal.id.substring(0, 16)}…</p>
                                </div>
                                <div>
                                    <span className="text-xs text-muted-foreground uppercase tracking-wide">Industry</span>
                                    <p className="font-medium capitalize mt-0.5">{deal.industry}</p>
                                </div>
                            </div>
                        </div>

                        {/* Agents Run */}
                        <div className="rounded-xl border p-4 space-y-3">
                            <h4 className="font-semibold text-sm flex items-center gap-2">
                                <Activity className="h-4 w-4 text-primary" /> Agents Executed
                            </h4>
                            {uniqueAgents.length === 0 ? (
                                <p className="text-muted-foreground text-sm">No agents have run yet for this deal.</p>
                            ) : (
                                <div className="space-y-2">
                                    {uniqueAgents.map((agentType, i) => {
                                        const Icon = AGENT_ICON_MAP[agentType] ?? Activity;
                                        const colorClass = AGENT_COLOR_MAP[agentType] ?? 'bg-slate-100 text-slate-600';
                                        const label = agentType.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
                                        const evt = dealActivity.find(e => e.agent_type === agentType);
                                        return (
                                            <div key={i} className="flex items-center justify-between rounded-lg bg-muted/40 px-3 py-2">
                                                <div className="flex items-center gap-2">
                                                    <div className={`rounded-full p-1.5 ${colorClass}`}>
                                                        <Icon className="h-3.5 w-3.5" />
                                                    </div>
                                                    <div>
                                                        <p className="text-sm font-medium">{label}</p>
                                                        {evt?.summary && (
                                                            <p className="text-xs text-muted-foreground">{evt.summary}</p>
                                                        )}
                                                    </div>
                                                </div>
                                                <div className="flex items-center gap-1.5 flex-shrink-0">
                                                    {evt?.provider && (
                                                        <Badge variant="outline" className="text-[10px] px-1 gap-0.5">
                                                            {evt.provider === 'ollama' || evt.provider === 'lmstudio'
                                                                ? <Cpu className="h-2.5 w-2.5" />
                                                                : <Cloud className="h-2.5 w-2.5" />}
                                                            {evt.provider}
                                                        </Badge>
                                                    )}
                                                    <CheckCircle className="h-4 w-4 text-green-500" />
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>
                            )}
                        </div>

                        {/* Agent Timeline */}
                        {dealActivity.length > 0 && (
                            <div className="rounded-xl border p-4 space-y-3">
                                <h4 className="font-semibold text-sm">Agent Timeline</h4>
                                <div className="relative space-y-3 pl-4 before:absolute before:left-1.5 before:top-2 before:bottom-2 before:w-px before:bg-border">
                                    {dealActivity.map((evt, i) => {
                                        const label = evt.agent_type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
                                        return (
                                            <div key={i} className="relative flex items-start gap-3">
                                                <div className="absolute -left-3 top-1 h-2 w-2 rounded-full bg-primary ring-2 ring-background" />
                                                <div className="space-y-0.5">
                                                    <p className="text-sm font-medium">{label}</p>
                                                    {evt.summary && <p className="text-xs text-muted-foreground">{evt.summary}</p>}
                                                    <p className="text-[10px] text-muted-foreground font-mono">{formatDate(evt.timestamp)}</p>
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>
                        )}
                    </div>
                </ScrollArea>

                {/* Report Download Hub */}
                <div className="border-t p-6 space-y-4 bg-muted/20">
                    <div className="flex items-center justify-between">
                        <div className="space-y-0.5">
                            <h4 className="text-sm font-bold flex items-center gap-2">
                                <FileText className="h-4 w-4 text-primary" /> Reports Hub
                            </h4>
                            <p className="text-[10px] text-muted-foreground uppercase tracking-widest font-semibold">
                                Production-Ready Deliverables
                            </p>
                        </div>
                        {manifest.length > 0 && (
                            <Button 
                                variant="ghost" 
                                size="sm" 
                                className="h-7 text-xs gap-1.5 text-primary hover:text-primary hover:bg-primary/10"
                                onClick={handleGenerate}
                                disabled={isGenerating}
                            >
                                <RefreshCw className={`h-3 w-3 ${isGenerating ? 'animate-spin' : ''}`} />
                                Regenerate
                            </Button>
                        )}
                    </div>

                    {manifest.length === 0 ? (
                        <div className="rounded-xl border border-dashed p-6 text-center space-y-3 bg-background/50">
                            <div className="mx-auto w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center">
                                <Zap className="h-5 w-5 text-primary" />
                            </div>
                            <div className="space-y-1">
                                <p className="text-sm font-medium">No reports generated yet</p>
                                <p className="text-xs text-muted-foreground max-w-[200px] mx-auto">
                                    Generate all McKinsey-style PPTX, Excel, and PDF deliverables at once.
                                </p>
                            </div>
                            <Button 
                                size="sm" 
                                className="w-full gap-2 shadow-lg shadow-primary/20"
                                onClick={handleGenerate}
                                disabled={isGenerating || deal.status !== 'completed' && deal.status !== 'ready'}
                            >
                                {isGenerating ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                                {isGenerating ? 'Generating Artifacts...' : 'Generate All Reports'}
                            </Button>
                        </div>
                    ) : (
                        <div className="space-y-3">
                            <div className="grid grid-cols-1 gap-2">
                                {manifest.map((doc, idx) => (
                                    <div key={idx} className="flex items-center justify-between rounded-lg border bg-background p-3 hover:border-primary/50 transition-all group">
                                        <div className="flex items-center gap-3">
                                            <div className="rounded-md p-2 bg-muted group-hover:bg-primary/10 transition-colors">
                                                {doc.format === 'pdf' ? <FileText className="h-4 w-4 text-red-500" /> :
                                                 doc.format === 'pptx' ? <Presentation className="h-4 w-4 text-orange-500" /> :
                                                 <FileSpreadsheet className="h-4 w-4 text-green-600" />}
                                            </div>
                                            <div>
                                                <p className="text-sm font-semibold uppercase">{doc.format}</p>
                                                <p className="text-[10px] text-muted-foreground">
                                                    {doc.size_human} · Generated {timeAgo(doc.generated_at)}
                                                </p>
                                            </div>
                                        </div>
                                        <Button 
                                            variant="ghost" 
                                            size="icon" 
                                            className="h-8 w-8 hover:bg-primary hover:text-white transition-colors"
                                            onClick={() => handleDownload(doc.format)}
                                        >
                                            <Download className="h-4 w-4" />
                                        </Button>
                                    </div>
                                ))}
                            </div>
                            
                            <Button 
                                variant="outline" 
                                size="sm" 
                                className="w-full gap-2 border-primary/20 hover:border-primary/50 hover:bg-primary/5"
                                onClick={handleDownloadBundle}
                            >
                                <Archive className="h-4 w-4 text-primary" />
                                Download Full Artifact Zip
                            </Button>
                        </div>
                    )}
                    
                    <div className="flex gap-2 pt-2">
                        <Button
                            className="flex-1 shadow-md"
                            onClick={() => { onClose(); onNavigate?.('chat'); }}
                        >
                            <LayoutDashboard className="mr-2 h-4 w-4" />
                            Continue in Chat
                        </Button>
                        <Button variant="outline" onClick={onClose}>
                            <ArrowLeft className="mr-2 h-4 w-4" />
                            Back
                        </Button>
                    </div>
                </div>
            </div>
        </div>
    );
}

// ─────────────────────────────────────────────
// Main Dashboard
// ─────────────────────────────────────────────
export function Dashboard({ onNavigate }: { onNavigate?: (page: 'chat' | 'dashboard' | 'settings') => void }) {
    const [metrics, setMetrics] = useState<Metrics | null>(null);
    const [loading, setLoading] = useState(true);
    const [lastRefresh, setLastRefresh] = useState<Date>(new Date());
    const [error, setError] = useState<string | null>(null);
    const [selectedDeal, setSelectedDeal] = useState<DealRecord | null>(null);

    const fetchMetrics = useCallback(async () => {
        try {
            const res = await fetch(`${API_BASE}/api/v1/dashboard/metrics`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data: Metrics = await res.json();
            setMetrics(data);
            setError(null);
        } catch {
            setError('Could not reach backend. Make sure the server is running.');
        } finally {
            setLoading(false);
            setLastRefresh(new Date());
        }
    }, []);

    useEffect(() => {
        fetchMetrics();
        const interval = setInterval(fetchMetrics, 15000);
        return () => clearInterval(interval);
    }, [fetchMetrics]);

    const scorePercent = (deal: DealRecord) =>
        deal.final_score !== null ? Math.round(deal.final_score * 100) : 0;

    return (
        <div className="space-y-6">
            {/* Detail Panel (slide-over) */}
            {selectedDeal && (
                <DealDetailPanel
                    deal={selectedDeal}
                    activity={metrics?.agent_activity ?? []}
                    onClose={() => setSelectedDeal(null)}
                    onNavigate={onNavigate}
                />
            )}

            <div className="flex items-center justify-between">
                <div className="flex flex-col space-y-1">
                    <h2 className="text-3xl font-bold tracking-tight bg-gradient-to-r from-blue-600 to-indigo-600 bg-clip-text text-transparent dark:from-blue-400 dark:to-indigo-400">
                        Overview
                    </h2>
                    <p className="text-muted-foreground text-sm">
                        Live M&A deal pipeline — refreshes every 15s
                    </p>
                </div>
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <span>Last updated: {lastRefresh.toLocaleTimeString()}</span>
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={fetchMetrics}
                        disabled={loading}
                        id="dashboard-refresh-btn"
                    >
                        <RefreshCw className={`h-3.5 w-3.5 mr-1 ${loading ? 'animate-spin' : ''}`} />
                        Refresh
                    </Button>
                </div>
            </div>

            {error && (
                <div className="rounded-lg border border-red-200 bg-red-50 dark:bg-red-950 dark:border-red-800 p-4 text-sm text-red-700 dark:text-red-300">
                    ⚠ {error}
                </div>
            )}

            {/* KPI Cards */}
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                <Card className="hover:shadow-md transition-all duration-200">
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Active Deals</CardTitle>
                        <Briefcase className="h-4 w-4 text-blue-500" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">
                            {loading ? <span className="animate-pulse">—</span> : (metrics?.active_deals ?? 0)}
                        </div>
                        <p className="text-xs text-muted-foreground">
                            {metrics?.total_deals ?? 0} total in pipeline
                        </p>
                    </CardContent>
                </Card>

                <Card className="hover:shadow-md transition-all duration-200">
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Avg. Confidence</CardTitle>
                        <Target className="h-4 w-4 text-green-500" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">
                            {loading ? <span className="animate-pulse">—</span> : `${metrics?.avg_confidence ?? 0}%`}
                        </div>
                        <p className="text-xs text-muted-foreground">Across completed deals</p>
                    </CardContent>
                </Card>

                <Card className="hover:shadow-md transition-all duration-200">
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Risk Alerts</CardTitle>
                        <AlertTriangle className="h-4 w-4 text-red-500" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">
                            {loading ? <span className="animate-pulse">—</span> : (metrics?.high_risk_alerts ?? 0)}
                        </div>
                        <p className="text-xs text-muted-foreground">Below 50% confidence score</p>
                    </CardContent>
                </Card>

                <Card className="hover:shadow-md transition-all duration-200">
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Completed</CardTitle>
                        <CheckCircle className="h-4 w-4 text-amber-500" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">
                            {loading ? <span className="animate-pulse">—</span> : (metrics?.completed_deals ?? 0)}
                        </div>
                        <p className="text-xs text-muted-foreground">Full analysis done</p>
                    </CardContent>
                </Card>
            </div>

            <div className="grid gap-4 md:grid-cols-7">
                {/* Deal List */}
                <Card className="col-span-4 md:col-span-5 hover:shadow-lg transition-all duration-300 border-t-4 border-t-primary">
                    <CardHeader>
                        <CardTitle>Deal Pipeline</CardTitle>
                        <CardDescription>
                            All deals analyzed by the multi-agent system. Click <strong>View Analysis</strong> for details.
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        <ScrollArea className="h-[400px] pr-4">
                            {loading ? (
                                <div className="flex items-center justify-center h-full text-muted-foreground">
                                    <RefreshCw className="h-5 w-5 animate-spin mr-2" /> Loading deals…
                                </div>
                            ) : !metrics?.deals.length ? (
                                <div className="flex flex-col items-center justify-center h-full text-muted-foreground gap-2">
                                    <Zap className="h-8 w-8 opacity-30" />
                                    <p className="text-sm">No deals yet — start a deal analysis in the Chat tab.</p>
                                </div>
                            ) : (
                                <div className="space-y-4">
                                    {[...metrics.deals].reverse().map((deal) => (
                                        <div key={deal.id} className="flex flex-col space-y-2 rounded-lg border p-4 hover:border-primary/50 transition-colors group">
                                            <div className="flex items-center justify-between">
                                                <div className="flex flex-col space-y-1">
                                                    <div className="flex items-center space-x-2">
                                                        <h3 className="font-semibold">{deal.name}</h3>
                                                        {getDealBadge(deal)}
                                                    </div>
                                                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                                        <span>Started: {formatDate(deal.created_at)}</span>
                                                        <span>·</span>
                                                        <span className="font-mono bg-muted px-1.5 py-0.5 rounded text-[10px] select-all">
                                                            ID: {deal.id.substring(0, 8)}
                                                        </span>
                                                    </div>
                                                </div>
                                                <div className="flex flex-col items-end text-xs text-muted-foreground">
                                                    <span>Updated: {timeAgo(deal.updated_at)}</span>
                                                </div>
                                            </div>

                                            <div className="flex items-center justify-between text-sm text-muted-foreground mt-2">
                                                <div className="flex items-center space-x-1">
                                                    <Activity className="h-3 w-3" />
                                                    <span>Stage: {deal.current_stage}</span>
                                                    {deal.agents_run.length > 0 && (
                                                        <span className="ml-2 text-xs opacity-70">
                                                            · {deal.agents_run.length} agent{deal.agents_run.length > 1 ? 's' : ''} ran
                                                        </span>
                                                    )}
                                                </div>
                                                {deal.final_score !== null && (
                                                    <div className="flex items-center space-x-2 w-1/3">
                                                        <div className="w-full">
                                                            <Progress value={scorePercent(deal)} className="h-2" />
                                                        </div>
                                                        <span className="font-medium text-foreground">{scorePercent(deal)}</span>
                                                    </div>
                                                )}
                                            </div>

                                            <div className="flex items-center justify-between pt-2">
                                                <span className="text-xs text-muted-foreground font-mono">{deal.target_company} · {deal.industry}</span>
                                                <Button
                                                    variant="default"
                                                    size="sm"
                                                    className="gap-1 group-hover:gap-2 transition-all"
                                                    onClick={() => setSelectedDeal(deal)}
                                                    id={`view-deal-${deal.id.substring(0, 8)}`}
                                                >
                                                    View Analysis <ChevronRight className="h-3 w-3" />
                                                </Button>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </ScrollArea>
                    </CardContent>
                </Card>

                {/* Agent Activity Feed */}
                <Card className="col-span-3 md:col-span-2">
                    <CardHeader>
                        <CardTitle>Agent Activity</CardTitle>
                        <CardDescription>Live multi-agent events.</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <ScrollArea className="h-[400px] pr-2">
                            {loading ? (
                                <div className="text-muted-foreground text-sm flex items-center gap-2">
                                    <RefreshCw className="w-3 h-3 animate-spin" /> Loading…
                                </div>
                            ) : !metrics?.agent_activity.length ? (
                                <div className="flex flex-col items-center justify-center h-full text-muted-foreground gap-2 text-center">
                                    <Activity className="h-7 w-7 opacity-30" />
                                    <p className="text-xs">No agent activity yet. Run a deal analysis to see live events here.</p>
                                </div>
                            ) : (
                                <div className="space-y-5">
                                    {[...metrics.agent_activity].reverse().map((event, i) => {
                                        const Icon = AGENT_ICON_MAP[event.agent_type] ?? Activity;
                                        const colorClass = AGENT_COLOR_MAP[event.agent_type] ?? 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400';
                                        const label = event.agent_type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
                                        return (
                                            <div
                                                key={i}
                                                className="flex items-start space-x-3 cursor-pointer hover:opacity-80 transition-opacity"
                                                onClick={() => {
                                                    if (event.deal_id && metrics) {
                                                        const deal = metrics.deals.find(d => d.id === event.deal_id);
                                                        if (deal) setSelectedDeal(deal);
                                                    }
                                                }}
                                            >
                                                <div className={`mt-0.5 rounded-full p-1.5 ${colorClass}`}>
                                                    <Icon className="h-4 w-4" />
                                                </div>
                                                <div className="space-y-0.5">
                                                    <p className="text-sm font-medium leading-none">{label}</p>
                                                    <p className="text-xs text-muted-foreground">
                                                        {event.summary ?? 'Completed analysis'}
                                                        {event.provider ? ` [${event.provider}]` : ''}
                                                    </p>
                                                    <p className="text-xs font-mono text-muted-foreground">{timeAgo(event.timestamp)}</p>
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>
                            )}
                        </ScrollArea>
                    </CardContent>
                </Card>
            </div>
        </div>
    );
}
