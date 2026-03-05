import { useState, useEffect, useCallback } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
    FileText, HardDrive, RefreshCw, Loader2, Cpu, Cloud,
    Trash2, Search, FolderTree, ChevronRight, ChevronDown, Zap,
    BookOpen, Upload, AlertTriangle, CheckCircle2, Brain, Layers,
    Activity, Server
} from 'lucide-react';

const API_BASE = 'http://localhost:8000';

interface RAGStats {
    total_documents: number;
    total_nodes: number;
    storage_dir: string;
    storage_size_mb?: number;
}

interface RAGDocument {
    doc_id: string;
    filename: string;
    file_type: string;
    total_pages: number;
    total_nodes: number;
    created_at: string;
    metadata: Record<string, unknown>;
}

interface RoutingHealth {
    provider: string;
    is_local: boolean;
    is_healthy: boolean;
    fallback?: string;
}

interface ModelRouting {
    strategy: string;
    routing_table: Record<string, string>;
    health: Record<string, RoutingHealth>;
    agents: string[];
    note: string;
}

// ─── Animated Pulse Dot ───
function PulseDot({ color }: { color: string }) {
    return (
        <span className="relative flex h-2.5 w-2.5">
            <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${color}`} />
            <span className={`relative inline-flex rounded-full h-2.5 w-2.5 ${color}`} />
        </span>
    );
}

// ─── File Tree Node ───
function FileTreeNode({ doc, onDelete }: { doc: RAGDocument; onDelete: (id: string) => void }) {
    const [open, setOpen] = useState(false);

    const fileIcon = doc.file_type === 'pdf' ? '📄' :
        doc.file_type === 'docx' ? '📝' :
            doc.file_type === 'xlsx' ? '📊' :
                doc.file_type === 'csv' ? '📋' : '📎';

    const createdDate = new Date(doc.created_at).toLocaleDateString('en-US', {
        month: 'short', day: 'numeric', year: 'numeric',
    });

    return (
        <div className="group">
            <button
                onClick={() => setOpen(!open)}
                className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-muted/50 transition-colors text-left"
            >
                <div className="flex items-center gap-2 flex-1 min-w-0">
                    {open ? <ChevronDown className="h-3.5 w-3.5 text-muted-foreground/50 flex-shrink-0" /> : <ChevronRight className="h-3.5 w-3.5 text-muted-foreground/50 flex-shrink-0" />}
                    <span className="text-base">{fileIcon}</span>
                    <span className="text-sm text-foreground truncate font-medium">{doc.filename}</span>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                    <Badge variant="outline" className="text-[10px] px-1.5 py-0 bg-muted/30 border-border text-muted-foreground">
                        {doc.total_pages} pg
                    </Badge>
                    <Badge variant="outline" className="text-[10px] px-1.5 py-0 bg-cyan-500/10 border-cyan-500/20 text-cyan-600 dark:text-cyan-400">
                        {doc.total_nodes} nodes
                    </Badge>
                </div>
            </button>

            {open && (
                <div className="ml-10 mb-2 p-3 rounded-lg bg-muted/20 border border-border text-xs space-y-2 animate-in fade-in slide-in-from-top-1 duration-200">
                    <div className="grid grid-cols-2 gap-2 text-muted-foreground">
                        <div><span className="opacity-70">Type:</span> {doc.file_type.toUpperCase()}</div>
                        <div><span className="opacity-70">Pages:</span> {doc.total_pages}</div>
                        <div><span className="opacity-70">Chunks:</span> {doc.total_nodes}</div>
                        <div><span className="opacity-70">Added:</span> {createdDate}</div>
                        <div className="col-span-2"><span className="opacity-70">ID:</span> <code className="text-cyan-600/70 dark:text-cyan-400/60">{doc.doc_id.substring(0, 16)}...</code></div>
                        {!!doc.metadata?.deal_id && (
                            <div className="col-span-2"><span className="opacity-70">Deal:</span> {String(doc.metadata.deal_id).substring(0, 12)}...</div>
                        )}
                    </div>
                    <div className="flex justify-end pt-1">
                        <Button size="sm" variant="ghost" onClick={() => onDelete(doc.doc_id)} className="text-red-400/60 hover:text-red-400 hover:bg-red-500/10 h-7 text-xs">
                            <Trash2 className="h-3 w-3 mr-1" /> Remove from index
                        </Button>
                    </div>
                </div>
            )}
        </div>
    );
}

// ═══════════════════════════════════════
//  MAIN COMPONENT
// ═══════════════════════════════════════

export function RAGDashboard() {
    const [stats, setStats] = useState<RAGStats | null>(null);
    const [documents, setDocuments] = useState<RAGDocument[]>([]);
    const [routing, setRouting] = useState<ModelRouting | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [testQuery, setTestQuery] = useState('');
    const [testResult, setTestResult] = useState<any>(null);
    const [testing, setTesting] = useState(false);
    const [ragMode, setRagMode] = useState<string>('local');

    const fetchAll = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const [statsRes, docsRes, routingRes] = await Promise.all([
                fetch(`${API_BASE}/api/v1/pageindex/stats`),
                fetch(`${API_BASE}/api/v1/pageindex/documents`),
                fetch(`${API_BASE}/api/v1/models/routing`),
            ]);

            if (statsRes.ok) setStats(await statsRes.json());
            if (docsRes.ok) {
                const docsData = await docsRes.json();
                setDocuments(docsData.documents || []);
                setRagMode(docsData.mode || 'local');
            }
            if (routingRes.ok) setRouting(await routingRes.json());
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to connect to backend');
        }
        setLoading(false);
    }, []);

    useEffect(() => { fetchAll(); }, [fetchAll]);

    async function handleTestQuery() {
        if (!testQuery.trim()) return;
        setTesting(true);
        setTestResult(null);
        try {
            const res = await fetch(`${API_BASE}/api/v1/documents/query`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query: testQuery }),
            });
            if (res.ok) {
                setTestResult(await res.json());
            } else {
                setTestResult({ error: `HTTP ${res.status}: ${res.statusText}` });
            }
        } catch (err) {
            setTestResult({ error: err instanceof Error ? err.message : 'Query failed' });
        }
        setTesting(false);
    }

    function handleDeleteDoc(docId: string) {
        // For now, just refresh (delete endpoint can be added later)
        setDocuments(prev => prev.filter(d => d.doc_id !== docId));
    }

    const pageindexRoute = routing?.health?.pageindex;
    const assignedProvider = routing?.routing_table?.pageindex || 'gemini';
    const isHealthy = pageindexRoute?.is_healthy !== false;
    const pageindexProvider = isHealthy ? assignedProvider : (pageindexRoute?.fallback || 'gemini');
    const isFallback = !isHealthy && assignedProvider !== pageindexProvider;

    // ─── Architecture flow data ───
    const flowSteps = [
        { icon: Upload, label: 'Document Upload', desc: 'PDF, DOCX, XLSX, CSV', color: 'text-blue-400', bg: 'bg-blue-500/10' },
        { icon: Layers, label: 'Chunking & Parsing', desc: 'Split into semantic chunks', color: 'text-violet-400', bg: 'bg-violet-500/10' },
        { icon: FolderTree, label: 'Tree Index', desc: 'Build hierarchical node tree', color: 'text-amber-400', bg: 'bg-amber-500/10' },
        { icon: Brain, label: 'LLM Embedding', desc: `Via ${pageindexProvider}`, color: 'text-emerald-400', bg: 'bg-emerald-500/10' },
        { icon: Search, label: 'Query & Retrieve', desc: 'Semantic search over chunks', color: 'text-cyan-400', bg: 'bg-cyan-500/10' },
    ];

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-3xl font-bold tracking-tight bg-gradient-to-r from-cyan-500 via-blue-600 to-violet-600 bg-clip-text text-transparent">
                        Knowledge Base
                    </h2>
                    <p className="text-muted-foreground text-sm mt-0.5">
                        RAG system status, indexed documents, and query testing
                    </p>
                </div>
                <div className="flex items-center gap-3">
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={fetchAll}
                        disabled={loading}
                        className="border-border text-foreground hover:bg-muted"
                    >
                        <RefreshCw className={`h-3.5 w-3.5 mr-2 ${loading ? 'animate-spin' : ''}`} /> Refresh
                    </Button>
                </div>
            </div>

            {error && (
                <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-4 text-sm text-red-400 flex items-start gap-3">
                    <AlertTriangle className="h-5 w-5 mt-0.5 flex-shrink-0" />
                    <div>
                        <p className="font-semibold">Backend Unreachable</p>
                        <p className="text-red-400/60 mt-1">{error}. Make sure the backend server is running on port 8000.</p>
                    </div>
                </div>
            )}

            {/* ─── Status Cards Row ─── */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                {/* RAG Mode */}
                <Card className="p-4 border-border bg-card shadow-sm">
                    <div className="flex items-center justify-between mb-3">
                        <span className="text-xs text-muted-foreground uppercase tracking-wider font-semibold">Mode</span>
                        <PulseDot color={ragMode === 'local' ? 'bg-emerald-500' : 'bg-blue-500'} />
                    </div>
                    <div className="flex items-center gap-2">
                        {ragMode === 'local' ? <HardDrive className="h-5 w-5 text-emerald-500" /> : <Cloud className="h-5 w-5 text-blue-500" />}
                        <span className="text-lg font-bold text-foreground capitalize">{ragMode}</span>
                    </div>
                    <p className="text-[11px] text-muted-foreground mt-1">{ragMode === 'local' ? 'Self-hosted tree index' : 'VectifyAI Cloud API'}</p>
                </Card>

                {/* Documents */}
                <Card className="p-4 border-border bg-card shadow-sm">
                    <div className="flex items-center justify-between mb-3">
                        <span className="text-xs text-muted-foreground uppercase tracking-wider font-semibold">Documents</span>
                        <FileText className="h-4 w-4 text-muted-foreground/30" />
                    </div>
                    <span className="text-3xl font-bold text-foreground">{stats?.total_documents ?? '—'}</span>
                    <p className="text-[11px] text-muted-foreground mt-1">Indexed files</p>
                </Card>

                {/* Nodes */}
                <Card className="p-4 border-border bg-card shadow-sm">
                    <div className="flex items-center justify-between mb-3">
                        <span className="text-xs text-muted-foreground uppercase tracking-wider font-semibold">Chunks</span>
                        <Layers className="h-4 w-4 text-muted-foreground/30" />
                    </div>
                    <span className="text-3xl font-bold text-foreground">{stats?.total_nodes ?? '—'}</span>
                    <p className="text-[11px] text-muted-foreground mt-1">Searchable nodes</p>
                </Card>

                {/* LLM Provider */}
                <Card className={`p-4 border-border bg-card shadow-sm ${isFallback ? 'border-amber-500/30' : ''}`}>
                    <div className="flex items-center justify-between mb-3">
                        <span className="text-xs text-muted-foreground uppercase tracking-wider font-semibold">LLM Provider</span>
                        <Zap className={`h-4 w-4 ${isFallback ? 'text-amber-500 animate-pulse' : 'text-muted-foreground/30'}`} />
                    </div>
                    <div className="flex items-center gap-2">
                        {pageindexProvider === 'ollama' || pageindexProvider === 'lmstudio' ? (
                            <Cpu className="h-5 w-5 text-amber-500" />
                        ) : (
                            <Cloud className="h-5 w-5 text-blue-500" />
                        )}
                        <span className="text-lg font-bold text-foreground capitalize">
                            {pageindexProvider}
                        </span>
                    </div>
                    {isFallback ? (
                        <div className="flex items-center gap-1 mt-1">
                            <AlertTriangle className="h-3 w-3 text-amber-500" />
                            <p className="text-[10px] text-amber-600 dark:text-amber-400 font-medium">
                                Fell back from {assignedProvider}
                            </p>
                        </div>
                    ) : (
                        <p className="text-[11px] text-muted-foreground mt-1">RAG embedding & reasoning</p>
                    )}
                </Card>
            </div>

            {/* ─── Architecture Flow ─── */}
            <Card className="p-5 border-border bg-card shadow-sm">
                <div className="flex items-center gap-2 mb-4">
                    <Activity className="h-4 w-4 text-cyan-500" />
                    <h3 className="text-sm font-semibold text-foreground">How RAG Works</h3>
                </div>
                <div className="flex items-center justify-between gap-2 overflow-x-auto pb-2">
                    {flowSteps.map((step, i) => {
                        const Icon = step.icon;
                        return (
                            <div key={i} className="flex items-center gap-2 flex-shrink-0">
                                <div className={`flex flex-col items-center gap-1.5 min-w-[100px]`}>
                                    <div className={`w-10 h-10 rounded-xl ${step.bg} flex items-center justify-center`}>
                                        <Icon className={`h-5 w-5 ${step.color}`} />
                                    </div>
                                    <span className="text-[11px] font-semibold text-foreground/70 text-center leading-tight">{step.label}</span>
                                    <span className="text-[10px] text-muted-foreground text-center leading-tight">{step.desc}</span>
                                </div>
                                {i < flowSteps.length - 1 && (
                                    <ChevronRight className="h-4 w-4 text-border flex-shrink-0" />
                                )}
                            </div>
                        );
                    })}
                </div>
            </Card>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* ─── Indexed Documents ─── */}
                <Card className="border-border bg-card shadow-sm flex flex-col">
                    <div className="p-4 border-b border-border flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <FolderTree className="h-4 w-4 text-amber-500" />
                            <h3 className="text-sm font-semibold text-foreground">Indexed Documents</h3>
                            <Badge className="text-[10px] bg-muted text-muted-foreground border-border">{documents.length}</Badge>
                        </div>
                    </div>

                    <ScrollArea className="flex-1 min-h-[200px] max-h-[400px]">
                        <div className="p-2">
                            {loading ? (
                                <div className="flex items-center justify-center py-12 text-muted-foreground">
                                    <Loader2 className="h-5 w-5 animate-spin mr-2" /> Loading...
                                </div>
                            ) : documents.length === 0 ? (
                                <div className="flex flex-col items-center justify-center py-12 text-muted-foreground text-center">
                                    <BookOpen className="h-10 w-10 mb-3 opacity-20" />
                                    <p className="text-sm font-medium">No documents indexed yet</p>
                                    <p className="text-xs opacity-60 mt-1">Upload documents via the Chat interface to index them for RAG</p>
                                </div>
                            ) : (
                                documents.map(doc => (
                                    <FileTreeNode key={doc.doc_id} doc={doc} onDelete={handleDeleteDoc} />
                                ))
                            )}
                        </div>
                    </ScrollArea>
                </Card>

                {/* ─── Query Tester ─── */}
                <Card className="border-border bg-card shadow-sm flex flex-col">
                    <div className="p-4 border-b border-border flex items-center gap-2">
                        <Search className="h-4 w-4 text-cyan-500" />
                        <h3 className="text-sm font-semibold text-foreground">Query Tester</h3>
                    </div>

                    <div className="p-4 space-y-3 flex-1">
                        <div className="flex gap-2">
                            <input
                                type="text"
                                value={testQuery}
                                onChange={e => setTestQuery(e.target.value)}
                                onKeyDown={e => { if (e.key === 'Enter') handleTestQuery(); }}
                                placeholder="Test a query against indexed documents..."
                                className="flex-1 bg-muted/30 border border-border rounded-lg px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:border-cyan-500/30"
                            />
                            <Button
                                onClick={handleTestQuery}
                                disabled={testing || !testQuery.trim()}
                                size="sm"
                                className="bg-cyan-500/10 text-cyan-600 dark:text-cyan-400 hover:bg-cyan-500/20 border border-cyan-500/20"
                            >
                                {testing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Search className="h-3.5 w-3.5" />}
                            </Button>
                        </div>

                        <ScrollArea className="h-[450px] w-full pr-4 mt-2">
                            {testResult ? (
                                testResult.error ? (
                                    <div className="rounded-lg bg-red-500/5 border border-red-500/20 p-3 text-xs text-red-600 dark:text-red-400">
                                        <AlertTriangle className="h-4 w-4 mb-1" />
                                        {testResult.error}
                                    </div>
                                ) : testResult.results?.length > 0 ? (
                                    <div className="space-y-4 pb-6">
                                        <p className="text-[11px] text-slate-500 dark:text-slate-400 font-bold uppercase tracking-wider">
                                            {testResult.results.length} result(s) for "{testResult.query}"
                                        </p>
                                        {testResult.results.map((r: any, i: number) => (
                                            <div key={i} className="rounded-xl bg-slate-50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-800 p-4 text-xs group hover:border-cyan-500/30 transition-all shadow-sm">
                                                <div className="flex items-center justify-between mb-2.5">
                                                    <div className="flex items-center gap-2">
                                                        <div className="w-5 h-5 rounded bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 flex items-center justify-center">
                                                            <FileText className="h-3 w-3 text-slate-400" />
                                                        </div>
                                                        <span className="text-slate-800 dark:text-slate-100 font-bold">Page {r.page}</span>
                                                    </div>
                                                    <Badge className="text-[10px] bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-500/20 px-2">
                                                        {(r.relevance * 100).toFixed(0)}% match
                                                    </Badge>
                                                </div>
                                                <p className="leading-relaxed text-slate-800 dark:text-slate-200 line-clamp-[8] text-[13px] font-medium">
                                                    {r.content}
                                                </p>
                                            </div>
                                        ))}
                                    </div>
                                ) : (
                                    <div className="flex flex-col items-center justify-center py-16 text-slate-400 text-center">
                                        <Search className="h-12 w-12 mb-4 opacity-20" />
                                        <p className="text-sm font-semibold">No results found</p>
                                        <p className="text-xs opacity-60 mt-1 max-w-[200px]">Try a different query or ensure documents are indexed</p>
                                    </div>
                                )
                            ) : (
                                <div className="flex flex-col items-center justify-center py-16 text-slate-400 text-center">
                                    <Brain className="h-12 w-12 mb-4 opacity-20 text-cyan-500" />
                                    <p className="text-sm font-semibold opacity-80 uppercase tracking-widest text-slate-500">Search Engine Ready</p>
                                    <p className="text-xs opacity-60 mt-1">Enter a query above to start semantic retrieval</p>
                                </div>
                            )}
                        </ScrollArea>
                    </div>
                </Card>
            </div>

            {/* ─── Storage Info ─── */}
            <Card className="p-4 border-border bg-card shadow-sm">
                <div className="flex items-center gap-2 mb-3">
                    <Server className="h-4 w-4 text-violet-500" />
                    <h3 className="text-sm font-semibold text-foreground">Storage</h3>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
                    <div>
                        <span className="text-muted-foreground opacity-70">Data Directory</span>
                        <p className="text-foreground/70 font-mono mt-0.5 break-all">{stats?.storage_dir || 'N/A'}</p>
                    </div>
                    <div>
                        <span className="text-muted-foreground opacity-70">Index Strategy</span>
                        <p className="text-foreground/70 mt-0.5">{routing?.strategy || 'local-first'}</p>
                    </div>
                    <div>
                        <span className="text-muted-foreground opacity-70">Status</span>
                        <div className="flex items-center gap-1.5 mt-0.5">
                            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
                            <span className="text-emerald-500 font-medium">Operational</span>
                        </div>
                    </div>
                </div>
            </Card>
        </div>
    );
}
