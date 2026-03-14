/**
 * DealForge Chat Store — Zustand + Redis-backed Persistence
 *
 * Primary persistence: Redis via backend API
 * Fallback persistence: localStorage (pruned, 20 convs / 100 msgs)
 *
 * API Endpoints:
 *   GET    /api/v1/conversations          → list all
 *   PUT    /api/v1/conversations/:id      → save full conversation
 *   DELETE /api/v1/conversations/:id      → delete conversation
 *   DELETE /api/v1/conversations          → clear all
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

const API_BASE = 'http://localhost:8005';

// ─── Types ───────────────────────────────────────────
export interface ChatMessage {
    id: string;
    role: 'user' | 'assistant' | 'agent' | 'system';
    content: string;
    agentName?: string;
    provider?: string;
    status?: 'thinking' | 'done' | 'error';
    timestamp: number;
    followUps?: string[];
    missingData?: string[];
    metadata?: Record<string, unknown>;
}

export interface Conversation {
    id: string;
    title: string;
    dealId?: string;
    messages: ChatMessage[];
    createdAt: number;
    updatedAt: number;
}

interface DealForgeStore {
    conversations: Conversation[];
    activeConversationId: string | null;
    sidebarCollapsed: boolean;
    _hydrated: boolean;

    // Actions
    createConversation: (dealId?: string) => string;
    deleteConversation: (id: string) => void;
    setActiveConversation: (id: string) => void;
    getActiveConversation: () => Conversation | null;

    addMessage: (conversationId: string, message: Omit<ChatMessage, 'id' | 'timestamp'>) => string;
    updateMessage: (conversationId: string, messageId: string, updates: Partial<ChatMessage>) => void;
    updateLastAssistantMessage: (conversationId: string, updates: Partial<ChatMessage>) => void;

    updateConversationTitle: (conversationId: string, title: string) => void;
    setSidebarCollapsed: (collapsed: boolean) => void;
    clearAllConversations: () => void;

    // Redis sync
    loadFromBackend: () => Promise<void>;
}

// ─── Helpers ─────────────────────────────────────────
const genId = () => `${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;

/**
 * Fire-and-forget save a single conversation to Redis.
 * Does not block the UI — errors are silently logged.
 */
function syncToBackend(conv: Conversation) {
    fetch(`${API_BASE}/api/v1/conversations/${conv.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(conv),
    }).catch((err) => console.warn('[DealForge] Redis sync failed:', err));
}

/**
 * Fire-and-forget delete a conversation from Redis.
 */
function deleteFromBackend(convId: string) {
    fetch(`${API_BASE}/api/v1/conversations/${convId}`, {
        method: 'DELETE',
    }).catch((err) => console.warn('[DealForge] Redis delete failed:', err));
}

// ─── Store ───────────────────────────────────────────
export const useDealForgeStore = create<DealForgeStore>()(
    persist(
        (set, get) => ({
            conversations: [],
            activeConversationId: null,
            sidebarCollapsed: false,
            _hydrated: false,

            // ── Load conversations from Redis on app startup ──
            loadFromBackend: async () => {
                try {
                    const res = await fetch(`${API_BASE}/api/v1/conversations`);
                    if (res.ok) {
                        const data = await res.json();
                        const convs: Conversation[] = data.conversations || [];
                        if (convs.length > 0) {
                            set({
                                conversations: convs,
                                activeConversationId: get().activeConversationId || convs[0]?.id || null,
                                _hydrated: true,
                            });
                            console.log(`[DealForge] Loaded ${convs.length} conversations from Redis`);
                            return;
                        }
                    }
                } catch (err) {
                    console.warn('[DealForge] Backend unavailable, using localStorage fallback:', err);
                }
                set({ _hydrated: true });
            },

            createConversation: (dealId?: string) => {
                const id = `conv_${genId()}`;
                const conv: Conversation = {
                    id,
                    title: 'New Analysis',
                    dealId,
                    messages: [],
                    createdAt: Date.now(),
                    updatedAt: Date.now(),
                };
                set(s => ({
                    conversations: [conv, ...s.conversations],
                    activeConversationId: id,
                }));
                syncToBackend(conv);
                return id;
            },

            deleteConversation: (id) => {
                set(s => {
                    const filtered = s.conversations.filter(c => c.id !== id);
                    return {
                        conversations: filtered,
                        activeConversationId: s.activeConversationId === id
                            ? (filtered[0]?.id || null)
                            : s.activeConversationId,
                    };
                });
                deleteFromBackend(id);
            },

            setActiveConversation: (id) => set({ activeConversationId: id }),

            getActiveConversation: () => {
                const s = get();
                return s.conversations.find(c => c.id === s.activeConversationId) || null;
            },

            addMessage: (conversationId, msg) => {
                const msgId = `msg_${genId()}`;
                const full: ChatMessage = { ...msg, id: msgId, timestamp: Date.now() };
                let updatedConv: Conversation | null = null;
                set(s => ({
                    conversations: s.conversations.map(c => {
                        if (c.id === conversationId) {
                            updatedConv = { ...c, messages: [...c.messages, full], updatedAt: Date.now() };
                            return updatedConv;
                        }
                        return c;
                    }),
                }));
                if (updatedConv) syncToBackend(updatedConv);
                return msgId;
            },

            updateMessage: (conversationId, messageId, updates) => {
                let updatedConv: Conversation | null = null;
                set(s => ({
                    conversations: s.conversations.map(c => {
                        if (c.id === conversationId) {
                            updatedConv = {
                                ...c,
                                messages: c.messages.map(m =>
                                    m.id === messageId ? { ...m, ...updates } : m
                                ),
                                updatedAt: Date.now(),
                            };
                            return updatedConv;
                        }
                        return c;
                    }),
                }));
                if (updatedConv) syncToBackend(updatedConv);
            },

            updateLastAssistantMessage: (conversationId, updates) => {
                let updatedConv: Conversation | null = null;
                set(s => ({
                    conversations: s.conversations.map(c => {
                        if (c.id !== conversationId) return c;
                        const msgs = [...c.messages];
                        for (let i = msgs.length - 1; i >= 0; i--) {
                            if (msgs[i].role === 'assistant' || msgs[i].role === 'agent') {
                                msgs[i] = { ...msgs[i], ...updates };
                                break;
                            }
                        }
                        updatedConv = { ...c, messages: msgs, updatedAt: Date.now() };
                        return updatedConv;
                    }),
                }));
                if (updatedConv) syncToBackend(updatedConv);
            },

            updateConversationTitle: (conversationId, title) => {
                let updatedConv: Conversation | null = null;
                set(s => ({
                    conversations: s.conversations.map(c => {
                        if (c.id === conversationId) {
                            updatedConv = { ...c, title, updatedAt: Date.now() };
                            return updatedConv;
                        }
                        return c;
                    }),
                }));
                if (updatedConv) syncToBackend(updatedConv);
            },

            setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),

            clearAllConversations: () => {
                set({ conversations: [], activeConversationId: null });
                fetch(`${API_BASE}/api/v1/conversations`, {
                    method: 'DELETE',
                }).catch(() => { });
            },
        }),
        {
            name: 'dealforge-chat-storage',
            // Fallback localStorage persistence (pruned to prevent QuotaExceededError)
            partialize: (state) => ({
                conversations: state.conversations
                    .slice(0, 20)
                    .map(conv => ({
                        ...conv,
                        messages: conv.messages
                            .slice(-100)
                            .map(m => {
                                const { metadata, ...rest } = m;
                                return rest;
                            })
                    })),
                activeConversationId: state.activeConversationId,
                sidebarCollapsed: state.sidebarCollapsed,
            }),
        }
    )
);
