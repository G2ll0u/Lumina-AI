
import React, { useState, useRef, useEffect } from 'react';
import { ChatSession } from '../types';

interface SidebarProps {
  isOpen: boolean;
  sessions: ChatSession[];
  currentSessionId: string | null;
  onSelectSession: (id: string) => void;
  onNewChat: () => void;
  onToggle: () => void;
  onOpenSettings: () => void;
  onRenameSession: (id: string, newTitle: string) => void;
  onDeleteSession: (id: string) => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  isOpen,
  sessions,
  currentSessionId,
  onSelectSession,
  onNewChat,
  onToggle,
  onOpenSettings,
  onRenameSession,
  onDeleteSession
}) => {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editingId && inputRef.current) {
      inputRef.current.focus();
    }
  }, [editingId]);

  const handleRenameSubmit = (e: React.FormEvent, id: string) => {
    e.preventDefault();
    if (editTitle.trim()) {
      onRenameSession(id, editTitle.trim());
    }
    setEditingId(null);
  };

  // Reset confirmation state if user clicks anywhere else
  useEffect(() => {
    const handleClickOutside = () => setConfirmDeleteId(null);
    document.addEventListener('click', handleClickOutside);
    return () => document.removeEventListener('click', handleClickOutside);
  }, []);

  if (!isOpen) return null;

  return (
    <aside className="w-72 h-full flex flex-col bg-zinc-950 border-r border-zinc-800 transition-all animate-in slide-in-from-left duration-300">
      <div className="p-4 flex items-center justify-between">
        <div className="flex items-center gap-2 text-blue-500">
          <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center text-white font-bold overflow-hidden">
            <img src="/logo.png" alt="L" className="w-full h-full object-cover" />
          </div>
          <span className="font-bold text-white tracking-tight">Lumina AI</span>
        </div>
        <button
          onClick={onToggle}
          className="p-2 hover:bg-zinc-900 rounded-lg text-zinc-400 transition-colors"
        >
          <i className="fa-solid fa-chevron-left"></i>
        </button>
      </div>

      <div className="px-4 mb-4">
        <button
          onClick={onNewChat}
          className="w-full flex items-center gap-3 px-4 py-3 bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 rounded-xl transition-all group"
        >
          <i className="fa-solid fa-plus text-blue-500 group-hover:scale-110 transition-transform"></i>
          <span className="font-medium text-sm">Nouvelle interaction</span>
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-2 space-y-1">
        <div className="px-3 py-2 text-[11px] font-bold text-zinc-500 uppercase tracking-wider">
          Historique
        </div>
        {sessions.map(session => (
          <div key={session.id} className="relative group">
            {editingId === session.id ? (
              <form onSubmit={(e) => handleRenameSubmit(e, session.id)} className="flex items-center gap-2 px-3 py-2.5 bg-zinc-800 rounded-lg">
                <i className="fa-regular fa-message opacity-70 text-zinc-400"></i>
                <input
                  ref={inputRef}
                  value={editTitle}
                  onChange={e => setEditTitle(e.target.value)}
                  onBlur={(e) => handleRenameSubmit(e, session.id)}
                  className="flex-1 bg-zinc-900 text-sm text-white px-2 py-0.5 rounded border border-blue-500 outline-none"
                />
              </form>
            ) : (
              <button
                onClick={() => onSelectSession(session.id)}
                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-left transition-all pr-16 ${currentSessionId === session.id
                  ? 'bg-zinc-800 text-white border border-zinc-700 shadow-sm'
                  : 'text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200'
                  }`}
              >
                <i className="fa-regular fa-message opacity-70"></i>
                <span className="truncate flex-1">{session.title}</span>
              </button>
            )}

            {/* Actions: Edit & Delete (visible on hover) */}
            {editingId !== session.id && (
              <div className={`absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-1 ${currentSessionId === session.id ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'} transition-opacity`}>
                <button
                  onClick={(e) => { e.stopPropagation(); setEditingId(session.id); setEditTitle(session.title); }}
                  className="p-1.5 text-zinc-400 hover:text-blue-400 rounded-md hover:bg-zinc-700 transition-colors"
                  title="Renommer"
                >
                  <i className="fa-solid fa-pen text-xs"></i>
                </button>
                {confirmDeleteId === session.id ? (
                  <button
                    onClick={(e) => { e.stopPropagation(); onDeleteSession(session.id); setConfirmDeleteId(null); }}
                    className="flex items-center gap-1.5 px-2 py-1 text-xs font-medium text-white bg-red-500 hover:bg-red-600 rounded-md transition-colors"
                    title="Confirmer la suppression"
                  >
                    <i className="fa-solid fa-check"></i> Oui
                  </button>
                ) : (
                  <button
                    onClick={(e) => { e.stopPropagation(); setConfirmDeleteId(session.id); }}
                    className="p-1.5 text-zinc-400 hover:text-red-400 rounded-md hover:bg-zinc-700 transition-colors"
                    title="Supprimer"
                  >
                    <i className="fa-solid fa-trash text-xs"></i>
                  </button>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="p-4 border-t border-zinc-900 mt-auto">
        <button
          onClick={onOpenSettings}
          className="w-full mb-3 flex items-center gap-3 p-2.5 rounded-lg text-zinc-400 hover:text-blue-400 hover:bg-zinc-900 transition-colors"
        >
          <i className="fa-solid fa-gear"></i>
          <span className="text-sm font-medium">Paramètres Locaux</span>
        </button>

        <div className="flex items-center gap-3 p-2 rounded-lg hover:bg-zinc-900 transition-colors cursor-pointer">
          <div className="w-9 h-9 rounded-full bg-gradient-to-tr from-zinc-700 to-zinc-500 flex items-center justify-center">
            <i className="fa-solid fa-user text-xs"></i>
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-white truncate">Workstation POC</p>
            <p className="text-xs text-zinc-500 truncate">No Admin Access</p>
          </div>
          <i className="fa-solid fa-ellipsis-vertical text-zinc-500 text-xs"></i>
        </div>
      </div>
    </aside>
  );
};
