/**
 * ChatSidebar — Collapsible conversation history sidebar
 *
 * Inspired by Perplexity Clone's Sidebar.tsx, adapted for DealForge:
 * - Shows conversation list with deal context
 * - New Analysis button
 * - Delete conversations
 * - Collapsible on desktop, overlay on mobile
 */

import {
    Plus, MessageSquare, Trash2, ChevronLeft, ChevronRight,
    Briefcase, Clock, Search
} from 'lucide-react';
import { useDealForgeStore } from '@/lib/dealforge-store';
import { useState } from 'react';

interface ChatSidebarProps {
    collapsed: boolean;
    onToggle: () => void;
}

export function ChatSidebar({ collapsed, onToggle }: ChatSidebarProps) {
    const {
        conversations,
        activeConversationId,
        createConversation,
        setActiveConversation,
        deleteConversation,
    } = useDealForgeStore();

    const [searchQuery, setSearchQuery] = useState('');

    const filtered = searchQuery
        ? conversations.filter(c =>
            c.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
            c.dealId?.toLowerCase().includes(searchQuery.toLowerCase())
        )
        : conversations;

    const handleNewChat = () => {
        createConversation();
    };

    const handleDelete = (id: string, e: React.MouseEvent) => {
        e.stopPropagation();
        deleteConversation(id);
    };

    const formatTime = (ts: number) => {
        const d = new Date(ts);
        const now = Date.now();
        const diff = now - ts;
        if (diff < 60000) return 'Just now';
        if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
        if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
        return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    };

    return (
        <aside
            className={`flex flex-col bg-slate-50 dark:bg-slate-900/50 border-r transition-all duration-300 ease-in-out flex-shrink-0 ${collapsed ? 'w-16' : 'w-64'
                }`}
        >
            {/* Header */}
            <div className="p-3 border-b flex items-center justify-between flex-shrink-0">
                {!collapsed && (
                    <span className="text-sm font-semibold text-slate-700 dark:text-slate-200">
                        Conversations
                    </span>
                )}
                <button
                    onClick={onToggle}
                    className="p-1.5 rounded-md hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors"
                    title={collapsed ? 'Expand' : 'Collapse'}
                >
                    {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
                </button>
            </div>

            {/* New Chat Button */}
            <div className="p-2 flex-shrink-0">
                <button
                    onClick={handleNewChat}
                    className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg bg-primary/10 hover:bg-primary/20 text-primary text-sm font-medium transition-colors ${collapsed ? 'justify-center px-2' : ''
                        }`}
                    title="New Analysis"
                >
                    <Plus className="h-4 w-4 flex-shrink-0" />
                    {!collapsed && <span>New Analysis</span>}
                </button>
            </div>

            {/* Search */}
            {!collapsed && (
                <div className="px-2 pb-2 flex-shrink-0">
                    <div className="relative">
                        <Search className="absolute left-2.5 top-2 h-3.5 w-3.5 text-muted-foreground" />
                        <input
                            type="text"
                            value={searchQuery}
                            onChange={e => setSearchQuery(e.target.value)}
                            placeholder="Search..."
                            className="w-full pl-8 pr-3 py-1.5 text-xs border rounded-md bg-white dark:bg-slate-800"
                        />
                    </div>
                </div>
            )}

            {/* Conversation List */}
            <div className="flex-1 overflow-y-auto px-2 py-1 space-y-0.5">
                {filtered.length === 0 && !collapsed && (
                    <div className="text-center py-6 text-muted-foreground text-xs">
                        <MessageSquare className="h-6 w-6 mx-auto mb-2 opacity-30" />
                        <p>No conversations yet</p>
                    </div>
                )}

                {filtered.map(conv => {
                    const isActive = conv.id === activeConversationId;
                    const agentCount = new Set(conv.messages.filter(m => m.agentName).map(m => m.agentName)).size;

                    return (
                        <button
                            key={conv.id}
                            onClick={() => setActiveConversation(conv.id)}
                            className={`w-full text-left rounded-lg transition-all duration-150 group ${collapsed ? 'p-2 justify-center flex' : 'px-3 py-2'
                                } ${isActive
                                    ? 'bg-primary/10 border border-primary/20 shadow-sm'
                                    : 'hover:bg-slate-100 dark:hover:bg-slate-800'
                                }`}
                            title={collapsed ? conv.title : undefined}
                        >
                            {collapsed ? (
                                <MessageSquare className={`h-4 w-4 ${isActive ? 'text-primary' : 'text-slate-400'}`} />
                            ) : (
                                <div className="flex items-start justify-between w-full">
                                    <div className="flex-1 min-w-0">
                                        <p className={`text-xs font-medium truncate ${isActive ? 'text-primary' : 'text-slate-700 dark:text-slate-200'}`}>
                                            {conv.title}
                                        </p>
                                        <div className="flex items-center gap-2 mt-1">
                                            {conv.dealId && (
                                                <span className="inline-flex items-center gap-0.5 text-[10px] text-slate-400">
                                                    <Briefcase className="h-2.5 w-2.5" />
                                                    {conv.dealId.slice(0, 8)}
                                                </span>
                                            )}
                                            <span className="text-[10px] text-slate-400 flex items-center gap-0.5">
                                                <Clock className="h-2.5 w-2.5" />
                                                {formatTime(conv.updatedAt)}
                                            </span>
                                            {agentCount > 0 && (
                                                <span className="text-[10px] px-1 rounded bg-slate-200 dark:bg-slate-700 text-slate-500">
                                                    {agentCount} agents
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                    <button
                                        onClick={e => handleDelete(conv.id, e)}
                                        className="p-1 rounded opacity-0 group-hover:opacity-100 hover:bg-red-100 hover:text-red-500 transition-all"
                                        title="Delete"
                                    >
                                        <Trash2 className="h-3 w-3" />
                                    </button>
                                </div>
                            )}
                        </button>
                    );
                })}
            </div>

            {/* Footer */}
            {!collapsed && (
                <div className="p-2 border-t text-[10px] text-muted-foreground text-center">
                    {conversations.length} conversation{conversations.length !== 1 ? 's' : ''}
                </div>
            )}
        </aside>
    );
}
