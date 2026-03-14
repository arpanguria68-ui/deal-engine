import { useState, useEffect, useCallback } from 'react';
import {
    CheckCircle2, Clock, Play, AlertTriangle, Trash2, Edit3, Plus,
    RefreshCw, ChevronDown, ChevronUp, GripVertical, Send, Loader2, ListTodo
} from 'lucide-react';

const API = 'http://localhost:8005';

interface TodoItem {
    id: string;
    title: string;
    description: string;
    assigned_agent: string;
    status: string;
    priority: string;
    order: number;
    result: any;
    depends_on: string[];
}

interface TodoList {
    id: string;
    deal_id: string;
    title: string;
    description: string;
    status: string;
    items: TodoItem[];
    summary: { total: number; pending: number; in_progress: number; done: number };
}

const STATUS_CONFIG: Record<string, { icon: any; color: string; bg: string; label: string }> = {
    pending: { icon: Clock, color: 'text-slate-500', bg: 'bg-slate-100', label: 'Pending' },
    in_progress: { icon: Play, color: 'text-blue-500', bg: 'bg-blue-100', label: 'In Progress' },
    review: { icon: AlertTriangle, color: 'text-amber-500', bg: 'bg-amber-100', label: 'Review' },
    done: { icon: CheckCircle2, color: 'text-emerald-500', bg: 'bg-emerald-100', label: 'Done' },
    blocked: { icon: AlertTriangle, color: 'text-red-500', bg: 'bg-red-100', label: 'Blocked' },
};

const PRIORITY_COLORS: Record<string, string> = {
    critical: 'border-l-red-500 bg-red-50/50',
    high: 'border-l-orange-500 bg-orange-50/30',
    medium: 'border-l-blue-500 bg-blue-50/20',
    low: 'border-l-slate-300',
};

const AGENT_LABELS: Record<string, string> = {
    financial_analyst: '📊 Financial Analyst',
    valuation_agent: '💰 Valuation Agent',
    dcf_lbo_architect: '🏗️ DCF/LBO Architect',
    legal_advisor: '⚖️ Legal Advisor',
    compliance_agent: '📋 Compliance',
    risk_assessor: '🛡️ Risk Assessor',
    market_risk_agent: '📈 Market Risk',
    market_researcher: '🔍 Market Researcher',
    prospectus_agent: '📚 Prospectus Librarian',
    due_diligence_agent: '🧠 Due Diligence',
    investment_memo_agent: '✍️ Investment Memo',
    treasury_agent: '🏦 Treasury',
    fpa_forecasting_agent: '📉 FP&A Forecasting',
    tax_compliance_agent: '🧾 Tax Compliance',
    debate_moderator: '🎙️ Debate Moderator',
    scoring_agent: '⭐ Scoring Agent',
    project_manager: '📋 Project Manager',
};

export function TaskBoardPage() {
    const [todoLists, setTodoLists] = useState<TodoList[]>([]);
    const [loading, setLoading] = useState(false);
    const [creating, setCreating] = useState(false);
    const [executing, setExecuting] = useState<string | null>(null);
    const [editingTask, setEditingTask] = useState<string | null>(null);
    const [editForm, setEditForm] = useState<Partial<TodoItem>>({});
    const [newDealId, setNewDealId] = useState('');
    const [newCompany, setNewCompany] = useState('');
    const [expandedList, setExpandedList] = useState<string | null>(null);
    const [showNewTask, setShowNewTask] = useState<string | null>(null);
    const [newTaskTitle, setNewTaskTitle] = useState('');
    const [newTaskAgent, setNewTaskAgent] = useState('financial_analyst');

    // Fetch all todo lists
    const fetchLists = useCallback(async () => {
        setLoading(true);
        try {
            // We'll fetch from a known deal or list all
            const res = await fetch(`${API}/api/v1/deals/all/tasks`);
            if (res.ok) {
                const data = await res.json();
                setTodoLists(data.todo_lists || []);
            }
        } catch (e) {
            console.error('Failed to fetch tasks:', e);
        }
        setLoading(false);
    }, []);

    useEffect(() => { fetchLists(); }, [fetchLists]);

    // Create new todo list
    const createTodoList = async () => {
        if (!newDealId.trim()) return;
        setCreating(true);
        try {
            const res = await fetch(`${API}/api/v1/deals/${newDealId}/tasks`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ company_name: newCompany || newDealId }),
            });
            if (res.ok) {
                const data = await res.json();
                const list = data.todo_list || data;
                setTodoLists(prev => [...prev, list]);
                setExpandedList(list.id);
                setNewDealId('');
                setNewCompany('');
            }
        } catch (e) {
            console.error('Failed to create todo list:', e);
        }
        setCreating(false);
    };

    // Update a task
    const updateTask = async (listId: string, taskId: string, updates: Partial<TodoItem>) => {
        try {
            const res = await fetch(`${API}/api/v1/tasks/${listId}/items/${taskId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(updates),
            });
            if (res.ok) {
                setTodoLists(prev => prev.map(l => l.id === listId ? {
                    ...l,
                    items: l.items.map(t => t.id === taskId ? { ...t, ...updates } : t),
                } : l));
                setEditingTask(null);
            }
        } catch (e) {
            console.error('Update failed:', e);
        }
    };

    // Delete a task
    const deleteTask = async (listId: string, taskId: string) => {
        try {
            await fetch(`${API}/api/v1/tasks/${listId}/items/${taskId}`, { method: 'DELETE' });
            setTodoLists(prev => prev.map(l => l.id === listId ? {
                ...l,
                items: l.items.filter(t => t.id !== taskId),
                summary: { ...l.summary, total: l.summary.total - 1 },
            } : l));
        } catch (e) {
            console.error('Delete failed:', e);
        }
    };

    // Add a task
    const addTask = async (listId: string) => {
        if (!newTaskTitle.trim()) return;
        try {
            const res = await fetch(`${API}/api/v1/tasks/${listId}/items`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title: newTaskTitle, assigned_agent: newTaskAgent, priority: 'medium' }),
            });
            if (res.ok) {
                const item = await res.json();
                setTodoLists(prev => prev.map(l => l.id === listId ? {
                    ...l, items: [...l.items, item],
                } : l));
                setNewTaskTitle('');
                setShowNewTask(null);
            }
        } catch (e) {
            console.error('Add task failed:', e);
        }
    };

    // Approve list
    const approveList = async (listId: string) => {
        try {
            await fetch(`${API}/api/v1/tasks/${listId}/approve`, { method: 'POST' });
            setTodoLists(prev => prev.map(l => l.id === listId ? { ...l, status: 'approved' } : l));
        } catch (e) {
            console.error('Approve failed:', e);
        }
    };

    // Execute all
    const executeAll = async (listId: string) => {
        setExecuting(listId);
        try {
            const res = await fetch(`${API}/api/v1/tasks/${listId}/execute`, { method: 'POST' });
            if (res.ok) {
                // Refresh the list after execution
                const listRes = await fetch(`${API}/api/v1/tasks/${listId}`);
                if (listRes.ok) {
                    const updated = await listRes.json();
                    setTodoLists(prev => prev.map(l => l.id === listId ? updated : l));
                }
            }
        } catch (e) {
            console.error('Execute failed:', e);
        }
        setExecuting(null);
    };


    return (
        <div className="space-y-6 max-w-5xl mx-auto">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-2xl font-bold text-primary flex items-center gap-2">
                        <ListTodo className="h-6 w-6" /> Task Board
                    </h2>
                    <p className="text-sm text-muted-foreground mt-1">
                        Project Manager creates and routes tasks to specialist agents. Review, edit, and approve before execution.
                    </p>
                </div>
                <button onClick={fetchLists} className="flex items-center gap-2 px-3 py-2 rounded-md border text-sm hover:bg-slate-50">
                    <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} /> Refresh
                </button>
            </div>

            {/* Create New Todo List */}
            <div className="border rounded-lg p-4 bg-white shadow-sm">
                <h3 className="text-sm font-semibold mb-3 text-slate-700">🚀 Create New Analysis Pipeline</h3>
                <div className="flex gap-3 items-end">
                    <div className="flex-1">
                        <label className="text-xs text-muted-foreground">Deal / Company ID</label>
                        <input
                            type="text"
                            value={newDealId}
                            onChange={e => setNewDealId(e.target.value)}
                            placeholder="e.g. zapier-2024"
                            className="w-full mt-1 px-3 py-2 border rounded-md text-sm"
                        />
                    </div>
                    <div className="flex-1">
                        <label className="text-xs text-muted-foreground">Company Name</label>
                        <input
                            type="text"
                            value={newCompany}
                            onChange={e => setNewCompany(e.target.value)}
                            placeholder="e.g. Zapier Inc."
                            className="w-full mt-1 px-3 py-2 border rounded-md text-sm"
                        />
                    </div>
                    <button
                        onClick={createTodoList}
                        disabled={creating || !newDealId.trim()}
                        className="flex items-center gap-2 px-4 py-2 rounded-md bg-primary text-white text-sm font-medium hover:bg-primary/90 disabled:opacity-50"
                    >
                        {creating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                        Generate Tasks
                    </button>
                </div>
            </div>

            {/* Todo Lists */}
            {todoLists.length === 0 && !loading && (
                <div className="text-center py-12 text-muted-foreground">
                    <ListTodo className="h-12 w-12 mx-auto mb-3 opacity-30" />
                    <p className="text-lg font-medium">No task lists yet</p>
                    <p className="text-sm">Create a new analysis pipeline above to get started.</p>
                </div>
            )}

            {todoLists.map(list => (
                <div key={list.id} className="border rounded-lg bg-white shadow-sm overflow-hidden">
                    {/* List Header */}
                    <div
                        className="flex items-center justify-between px-4 py-3 bg-slate-50 cursor-pointer hover:bg-slate-100"
                        onClick={() => setExpandedList(expandedList === list.id ? null : list.id)}
                    >
                        <div className="flex items-center gap-3">
                            {expandedList === list.id ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                            <div>
                                <h3 className="font-semibold text-sm">{list.title}</h3>
                                <p className="text-xs text-muted-foreground">{list.description}</p>
                            </div>
                        </div>
                        <div className="flex items-center gap-3">
                            {/* Summary badges */}
                            <span className="text-xs px-2 py-1 rounded-full bg-slate-200">{list.items?.length || 0} tasks</span>
                            <span className={`text-xs px-2 py-1 rounded-full font-medium ${list.status === 'completed' ? 'bg-emerald-100 text-emerald-700' :
                                list.status === 'approved' ? 'bg-blue-100 text-blue-700' :
                                    list.status === 'in_progress' ? 'bg-amber-100 text-amber-700' :
                                        'bg-slate-100 text-slate-600'
                                }`}>
                                {list.status}
                            </span>
                            {/* Action buttons */}
                            {list.status === 'draft' && (
                                <button
                                    onClick={e => { e.stopPropagation(); approveList(list.id); }}
                                    className="text-xs px-3 py-1 rounded-md bg-emerald-500 text-white hover:bg-emerald-600"
                                >
                                    ✓ Approve
                                </button>
                            )}
                            {(list.status === 'approved' || list.status === 'in_progress') && (
                                <button
                                    onClick={e => { e.stopPropagation(); executeAll(list.id); }}
                                    disabled={executing === list.id}
                                    className="text-xs px-3 py-1 rounded-md bg-primary text-white hover:bg-primary/90 disabled:opacity-50"
                                >
                                    {executing === list.id ? <Loader2 className="h-3 w-3 animate-spin inline mr-1" /> : <Play className="h-3 w-3 inline mr-1" />}
                                    Execute All
                                </button>
                            )}
                        </div>
                    </div>

                    {/* Task Items */}
                    {expandedList === list.id && (
                        <div className="divide-y">
                            {list.items?.map((task, idx) => {
                                const statusCfg = STATUS_CONFIG[task.status] || STATUS_CONFIG.pending;
                                const StatusIcon = statusCfg.icon;
                                const isEditing = editingTask === task.id;

                                return (
                                    <div key={task.id} className={`px-4 py-3 border-l-4 ${PRIORITY_COLORS[task.priority] || ''} hover:bg-slate-50/50`}>
                                        <div className="flex items-start gap-3">
                                            <GripVertical className="h-4 w-4 text-slate-300 mt-1 flex-shrink-0" />
                                            <span className="text-xs text-slate-400 mt-1 w-6">{idx + 1}.</span>

                                            <div className="flex-1 min-w-0">
                                                {isEditing ? (
                                                    <div className="space-y-2">
                                                        <input
                                                            type="text"
                                                            value={editForm.title || ''}
                                                            onChange={e => setEditForm(f => ({ ...f, title: e.target.value }))}
                                                            className="w-full px-2 py-1 border rounded text-sm"
                                                        />
                                                        <textarea
                                                            value={editForm.description || ''}
                                                            onChange={e => setEditForm(f => ({ ...f, description: e.target.value }))}
                                                            className="w-full px-2 py-1 border rounded text-sm"
                                                            rows={2}
                                                        />
                                                        <div className="flex gap-2">
                                                            <select
                                                                value={editForm.assigned_agent || ''}
                                                                onChange={e => setEditForm(f => ({ ...f, assigned_agent: e.target.value }))}
                                                                className="px-2 py-1 border rounded text-xs"
                                                            >
                                                                {Object.entries(AGENT_LABELS).map(([k, v]) => (
                                                                    <option key={k} value={k}>{v}</option>
                                                                ))}
                                                            </select>
                                                            <select
                                                                value={editForm.priority || 'medium'}
                                                                onChange={e => setEditForm(f => ({ ...f, priority: e.target.value }))}
                                                                className="px-2 py-1 border rounded text-xs"
                                                            >
                                                                <option value="critical">🔴 Critical</option>
                                                                <option value="high">🟠 High</option>
                                                                <option value="medium">🔵 Medium</option>
                                                                <option value="low">⚪ Low</option>
                                                            </select>
                                                            <button
                                                                onClick={() => updateTask(list.id, task.id, editForm)}
                                                                className="px-3 py-1 bg-primary text-white rounded text-xs"
                                                            >Save</button>
                                                            <button
                                                                onClick={() => setEditingTask(null)}
                                                                className="px-3 py-1 border rounded text-xs"
                                                            >Cancel</button>
                                                        </div>
                                                    </div>
                                                ) : (
                                                    <>
                                                        <div className="flex items-center gap-2">
                                                            <h4 className="text-sm font-medium">{task.title}</h4>
                                                            <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full ${statusCfg.bg} ${statusCfg.color}`}>
                                                                <StatusIcon className="h-3 w-3" />
                                                                {statusCfg.label}
                                                            </span>
                                                        </div>
                                                        <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{task.description}</p>
                                                        <div className="flex items-center gap-3 mt-2">
                                                            <span className="text-xs text-slate-500">
                                                                {AGENT_LABELS[task.assigned_agent] || task.assigned_agent}
                                                            </span>
                                                            <span className={`text-xs px-1.5 py-0.5 rounded ${task.priority === 'critical' ? 'bg-red-100 text-red-600' :
                                                                task.priority === 'high' ? 'bg-orange-100 text-orange-600' :
                                                                    task.priority === 'medium' ? 'bg-blue-100 text-blue-600' :
                                                                        'bg-slate-100 text-slate-500'
                                                                }`}>
                                                                {task.priority}
                                                            </span>
                                                        </div>
                                                    </>
                                                )}
                                            </div>

                                            {/* Actions */}
                                            {!isEditing && (
                                                <div className="flex items-center gap-1 flex-shrink-0">
                                                    <button
                                                        onClick={() => { setEditingTask(task.id); setEditForm(task); }}
                                                        className="p-1.5 rounded hover:bg-slate-100"
                                                        title="Edit"
                                                    >
                                                        <Edit3 className="h-3.5 w-3.5 text-slate-400" />
                                                    </button>
                                                    <button
                                                        onClick={() => deleteTask(list.id, task.id)}
                                                        className="p-1.5 rounded hover:bg-red-50"
                                                        title="Delete"
                                                    >
                                                        <Trash2 className="h-3.5 w-3.5 text-slate-400 hover:text-red-500" />
                                                    </button>
                                                </div>
                                            )}
                                        </div>

                                        {/* Result preview */}
                                        {task.result && (
                                            <div className="mt-2 ml-10 p-2 bg-slate-50 rounded text-xs text-slate-600 max-h-24 overflow-y-auto">
                                                <pre>{JSON.stringify(task.result, null, 2).slice(0, 300)}</pre>
                                            </div>
                                        )}
                                    </div>
                                );
                            })}

                            {/* Add Task */}
                            {showNewTask === list.id ? (
                                <div className="px-4 py-3 bg-slate-50/50">
                                    <div className="flex gap-2 items-center">
                                        <input
                                            type="text"
                                            value={newTaskTitle}
                                            onChange={e => setNewTaskTitle(e.target.value)}
                                            placeholder="New task title..."
                                            className="flex-1 px-3 py-2 border rounded text-sm"
                                            onKeyDown={e => e.key === 'Enter' && addTask(list.id)}
                                        />
                                        <select
                                            value={newTaskAgent}
                                            onChange={e => setNewTaskAgent(e.target.value)}
                                            className="px-2 py-2 border rounded text-xs"
                                        >
                                            {Object.entries(AGENT_LABELS).map(([k, v]) => (
                                                <option key={k} value={k}>{v}</option>
                                            ))}
                                        </select>
                                        <button onClick={() => addTask(list.id)} className="px-3 py-2 bg-primary text-white rounded text-sm">
                                            <Send className="h-4 w-4" />
                                        </button>
                                        <button onClick={() => setShowNewTask(null)} className="px-3 py-2 border rounded text-sm">Cancel</button>
                                    </div>
                                </div>
                            ) : (
                                <button
                                    onClick={() => setShowNewTask(list.id)}
                                    className="w-full px-4 py-2.5 text-xs text-muted-foreground hover:bg-slate-50 flex items-center gap-2 justify-center"
                                >
                                    <Plus className="h-3 w-3" /> Add Task
                                </button>
                            )}
                        </div>
                    )}
                </div>
            ))}
        </div>
    );
}
