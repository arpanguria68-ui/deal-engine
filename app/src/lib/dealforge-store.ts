/**
 * DealForge Chat Store — Zustand + localStorage Persistence
 *
 * Adapted from Perplexity Clone's store pattern, enhanced with:
 * - Deal-specific context (dealId, agentResults)
 * - Multi-agent message support (role: 'agent' with agentName)
 * - Follow-up suggestions persistence
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

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
}

// ─── Helper ──────────────────────────────────────────
const genId = () => `${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;

// ─── Store ───────────────────────────────────────────
export const useDealForgeStore = create<DealForgeStore>()(
    persist(
        (set, get) => ({
            conversations: [],
            activeConversationId: null,
            sidebarCollapsed: false,

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
            },

            setActiveConversation: (id) => set({ activeConversationId: id }),

            getActiveConversation: () => {
                const s = get();
                return s.conversations.find(c => c.id === s.activeConversationId) || null;
            },

            addMessage: (conversationId, msg) => {
                const msgId = `msg_${genId()}`;
                const full: ChatMessage = { ...msg, id: msgId, timestamp: Date.now() };
                set(s => ({
                    conversations: s.conversations.map(c =>
                        c.id === conversationId
                            ? { ...c, messages: [...c.messages, full], updatedAt: Date.now() }
                            : c
                    ),
                }));
                return msgId;
            },

            updateMessage: (conversationId, messageId, updates) => {
                set(s => ({
                    conversations: s.conversations.map(c =>
                        c.id === conversationId
                            ? {
                                ...c,
                                messages: c.messages.map(m =>
                                    m.id === messageId ? { ...m, ...updates } : m
                                ),
                                updatedAt: Date.now(),
                            }
                            : c
                    ),
                }));
            },

            updateLastAssistantMessage: (conversationId, updates) => {
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
                        return { ...c, messages: msgs, updatedAt: Date.now() };
                    }),
                }));
            },

            updateConversationTitle: (conversationId, title) => {
                set(s => ({
                    conversations: s.conversations.map(c =>
                        c.id === conversationId ? { ...c, title, updatedAt: Date.now() } : c
                    ),
                }));
            },

            setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),

            clearAllConversations: () => set({ conversations: [], activeConversationId: null }),
        }),
        {
            name: 'dealforge-chat-storage',
        }
    )
);
