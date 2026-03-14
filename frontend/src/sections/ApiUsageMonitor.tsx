import { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
    Activity, Key, Zap, Clock, Database, RefreshCw,
    CheckCircle, XCircle, Loader2, TrendingUp, AlertTriangle, Gauge
} from 'lucide-react';

const API_BASE = 'http://localhost:8005';

interface VendorUsage {
    vendor: string;
    api_key_configured: boolean;
    api_key_masked: string;
    rpm: { current: number; limit: number };
    tpm: { current: number; limit: number };
    rpd: { current: number; limit: number };
    monthly_tokens: number;
    rpm_pct: number;
    tpm_pct: number;
    rpd_pct: number;
    model_metadata?: {
        popular_models?: Array<{ id: string; context: string; daily_free: string }>;
    };
}

interface UsageData {
    vendors: Record<string, VendorUsage>;
    cache: {
        hits: number;
        misses: number;
        size: number;
        hit_rate: string;
    };
    recent_calls: number;
}

const VENDOR_COLORS: Record<string, { bg: string; border: string; text: string; accent: string }> = {
    gemini: { bg: 'bg-blue-500/10', border: 'border-blue-500/30', text: 'text-blue-600 dark:text-blue-400', accent: 'bg-blue-500' },
    openai: { bg: 'bg-emerald-500/10', border: 'border-emerald-500/30', text: 'text-emerald-600 dark:text-emerald-400', accent: 'bg-emerald-500' },
    mistral: { bg: 'bg-orange-500/10', border: 'border-orange-500/30', text: 'text-orange-600 dark:text-orange-400', accent: 'bg-orange-500' },
    ollama: { bg: 'bg-purple-500/10', border: 'border-purple-500/30', text: 'text-purple-600 dark:text-purple-400', accent: 'bg-purple-500' },
    lmstudio: { bg: 'bg-pink-500/10', border: 'border-pink-500/30', text: 'text-pink-600 dark:text-pink-400', accent: 'bg-pink-500' },
};

function UsageBar({ label, current, limit, pct, icon }: {
    label: string; current: number; limit: number; pct: number; icon: React.ReactNode
}) {
    const getColor = (p: number) =>
        p > 90 ? 'bg-red-500' : p > 70 ? 'bg-amber-500' : p > 40 ? 'bg-blue-500' : 'bg-emerald-500';
    const getTextColor = (p: number) =>
        p > 90 ? 'text-red-600' : p > 70 ? 'text-amber-600' : 'text-muted-foreground';

    return (
        <div className="space-y-1.5">
            <div className="flex items-center justify-between text-xs">
                <span className="flex items-center gap-1.5 text-muted-foreground font-medium">
                    {icon} {label}
                </span>
                <span className={`font-mono font-semibold ${getTextColor(pct)}`}>
                    {current.toLocaleString()} / {limit.toLocaleString()}
                </span>
            </div>
            <div className="h-2 bg-muted/50 rounded-full overflow-hidden">
                <div
                    className={`h-full rounded-full transition-all duration-500 ${getColor(pct)}`}
                    style={{ width: `${Math.min(pct, 100)}%` }}
                />
            </div>
            <div className="flex justify-between text-[10px] text-muted-foreground/70">
                <span>{pct}% utilized</span>
                {pct > 80 && (
                    <span className="flex items-center gap-0.5 text-amber-500 font-medium">
                        <AlertTriangle className="h-2.5 w-2.5" /> Near limit
                    </span>
                )}
            </div>
        </div>
    );
}

export function ApiUsageMonitor() {
    const [usage, setUsage] = useState<UsageData | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const fetchUsage = useCallback(async () => {
        try {
            const res = await fetch(`${API_BASE}/api/v1/llm/usage`, { signal: AbortSignal.timeout(5000) });
            if (res.ok) {
                setUsage(await res.json());
                setError(null);
            } else {
                setError(`HTTP ${res.status}`);
            }
        } catch (e) {
            setError(e instanceof Error ? e.message : 'Failed to fetch');
        }
        setLoading(false);
    }, []);

    useEffect(() => {
        fetchUsage();
        const interval = setInterval(fetchUsage, 10000); // Poll every 10s
        return () => clearInterval(interval);
    }, [fetchUsage]);

    const cloudVendors = usage
        ? Object.entries(usage.vendors).filter(([k]) => ['gemini', 'openai', 'mistral'].includes(k))
        : [];

    const localVendors = usage
        ? Object.entries(usage.vendors).filter(([k]) => ['ollama', 'lmstudio'].includes(k))
        : [];

    return (
        <Card className="border-t-4 border-t-violet-500">
            <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                    <div>
                        <CardTitle className="flex items-center gap-2">
                            <Activity className="h-5 w-5 text-violet-500" />
                            API Usage Monitor
                        </CardTitle>
                        <CardDescription>
                            Live rate limits, token utilization, and API key health for all providers.
                            {usage && (
                                <Badge variant="outline" className="ml-2 text-[9px]">
                                    {usage.recent_calls} recent calls
                                </Badge>
                            )}
                        </CardDescription>
                    </div>
                    <Button variant="outline" size="sm" onClick={fetchUsage} disabled={loading} className="gap-1.5">
                        <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
                        Refresh
                    </Button>
                </div>
            </CardHeader>
            <CardContent className="space-y-4">
                {error && (
                    <div className="flex items-center gap-2 text-xs text-amber-600 bg-amber-50 dark:bg-amber-950/20 p-2 rounded-md border border-amber-200 dark:border-amber-900/30">
                        <AlertTriangle className="h-3.5 w-3.5" />
                        Backend unreachable: {error}. Make sure the backend is running.
                    </div>
                )}

                {loading && !usage ? (
                    <div className="flex items-center justify-center py-8 text-muted-foreground">
                        <Loader2 className="h-5 w-5 animate-spin mr-2" /> Loading usage stats...
                    </div>
                ) : usage && (
                    <>
                        {/* ─── Cloud Providers ─── */}
                        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                            {cloudVendors.map(([name, vendor]) => {
                                const colors = VENDOR_COLORS[name] || VENDOR_COLORS.gemini;
                                return (
                                    <div
                                        key={name}
                                        className={`rounded-xl border ${colors.border} p-4 space-y-4 ${colors.bg}`}
                                    >
                                        {/* Header */}
                                        <div className="flex items-center justify-between">
                                            <div className="flex items-center gap-2">
                                                <div className={`w-2 h-2 rounded-full ${colors.accent}`} />
                                                <h4 className={`font-bold text-sm capitalize ${colors.text}`}>{name}</h4>
                                            </div>
                                            {vendor.api_key_configured ? (
                                                <Badge className="bg-emerald-100 text-emerald-700 border-emerald-300 text-[9px] gap-1">
                                                    <CheckCircle className="h-2.5 w-2.5" /> Key Active
                                                </Badge>
                                            ) : (
                                                <Badge variant="destructive" className="text-[9px] gap-1">
                                                    <XCircle className="h-2.5 w-2.5" /> No Key
                                                </Badge>
                                            )}
                                        </div>

                                        {/* Masked Key */}
                                        {vendor.api_key_masked && (
                                            <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground font-mono bg-background/50 rounded px-2 py-1">
                                                <Key className="h-3 w-3" /> {vendor.api_key_masked}
                                            </div>
                                        )}

                                        {/* Rate Limit Bars */}
                                        <UsageBar
                                            label="Requests/min"
                                            current={vendor.rpm.current}
                                            limit={vendor.rpm.limit}
                                            pct={vendor.rpm_pct}
                                            icon={<Gauge className="h-3 w-3" />}
                                        />
                                        <UsageBar
                                            label="Tokens/min"
                                            current={vendor.tpm.current}
                                            limit={vendor.tpm.limit}
                                            pct={vendor.tpm_pct}
                                            icon={<Zap className="h-3 w-3" />}
                                        />
                                        <UsageBar
                                            label="Requests/day"
                                            current={vendor.rpd.current}
                                            limit={vendor.rpd.limit}
                                            pct={vendor.rpd_pct}
                                            icon={<Clock className="h-3 w-3" />}
                                        />

                                        {/* Monthly Tokens */}
                                        <div className="flex items-center justify-between text-xs pt-1 border-t border-border/50">
                                            <span className="text-muted-foreground flex items-center gap-1">
                                                <TrendingUp className="h-3 w-3" /> Monthly tokens
                                            </span>
                                            <span className="font-mono font-semibold">
                                                {vendor.monthly_tokens.toLocaleString()}
                                            </span>
                                        </div>

                                        {/* Model Metadata */}
                                        {vendor.model_metadata?.popular_models && (
                                            <div className="space-y-1.5 pt-1 border-t border-border/50">
                                                <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">Model Specs</p>
                                                {vendor.model_metadata.popular_models.map(m => (
                                                    <div key={m.id} className="flex items-center justify-between text-[10px] bg-background/50 rounded px-2 py-1">
                                                        <span className="font-mono font-medium truncate max-w-[120px]">{m.id}</span>
                                                        <div className="flex gap-2 text-muted-foreground">
                                                            <span>{m.context} ctx</span>
                                                            <span className="text-amber-600 dark:text-amber-400 font-medium">{m.daily_free}</span>
                                                        </div>
                                                    </div>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                );
                            })}
                        </div>

                        {/* ─── Local Providers + Cache ─── */}
                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                            {/* Local Providers */}
                            <div className="rounded-xl border border-border p-4 space-y-3">
                                <h4 className="text-sm font-semibold flex items-center gap-2">
                                    <Database className="h-4 w-4 text-purple-500" />
                                    Local Providers
                                    <Badge variant="outline" className="text-[9px]">Unlimited</Badge>
                                </h4>
                                {localVendors.map(([name, vendor]) => (
                                    <div key={name} className="flex items-center justify-between text-xs p-2 bg-muted/30 rounded-lg">
                                        <div className="flex items-center gap-2">
                                            <div className={`w-2 h-2 rounded-full ${VENDOR_COLORS[name]?.accent || 'bg-gray-400'}`} />
                                            <span className="font-medium capitalize">{name}</span>
                                        </div>
                                        <div className="flex items-center gap-3 text-muted-foreground">
                                            <span>{vendor.rpm.current} RPM</span>
                                            <span>{vendor.rpd.current} RPD</span>
                                            <span className="font-mono">{vendor.monthly_tokens.toLocaleString()} tok</span>
                                        </div>
                                    </div>
                                ))}
                            </div>

                            {/* Cache Stats */}
                            <div className="rounded-xl border border-border p-4 space-y-3">
                                <h4 className="text-sm font-semibold flex items-center gap-2">
                                    <Zap className="h-4 w-4 text-cyan-500" />
                                    Response Cache
                                </h4>
                                <div className="grid grid-cols-2 gap-3">
                                    <div className="bg-muted/30 rounded-lg p-3 text-center">
                                        <p className="text-2xl font-bold text-emerald-600">{usage.cache.hit_rate}</p>
                                        <p className="text-[10px] text-muted-foreground mt-1">Hit Rate</p>
                                    </div>
                                    <div className="bg-muted/30 rounded-lg p-3 text-center">
                                        <p className="text-2xl font-bold">{usage.cache.size}</p>
                                        <p className="text-[10px] text-muted-foreground mt-1">Cached Entries</p>
                                    </div>
                                    <div className="bg-muted/30 rounded-lg p-3 text-center">
                                        <p className="text-lg font-bold text-emerald-500">{usage.cache.hits}</p>
                                        <p className="text-[10px] text-muted-foreground mt-1">Cache Hits</p>
                                    </div>
                                    <div className="bg-muted/30 rounded-lg p-3 text-center">
                                        <p className="text-lg font-bold text-amber-500">{usage.cache.misses}</p>
                                        <p className="text-[10px] text-muted-foreground mt-1">Cache Misses</p>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </>
                )}
            </CardContent>
        </Card>
    );
}
