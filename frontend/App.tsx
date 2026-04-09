
import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Sidebar } from './components/Sidebar';
import { ChatArea } from './components/ChatArea';
import { Role, Message, ChatSession, ModelType } from './types';
import { api } from './services/apiService';
import { SettingsModal, LocalSettings, defaultSettings } from './components/SettingsModal';
import { ExpertReviewModal } from './components/ExpertReviewModal';

// Fallback for crypto.randomUUID() in non-secure contexts (HTTP via IP)
const generateUUID = () => {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
};

const App: React.FC = () => {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [isInitializing, setIsInitializing] = useState(true);
  const [isExpertModalOpen, setIsExpertModalOpen] = useState(false);

  const fetchSessions = async () => {
    try {
      const data = await api.getSessions();
      setSessions(data);
      if (data.length > 0 && !currentSessionId) {
        handleSelectSession(data[0].id);
      } else if (data.length === 0) {
        await createNewSession();
      }
    } catch (e: any) {
      if (e.message?.includes("401_UNAUTHORIZED")) {
        alert("🛡️ Connexion bloquée (401 Unauthorized).\n\nLe backend requiert un mot de passe (SECRET_KEY).\nVeuillez renseigner votre Clé API Secrète dans les Paramètres Locaux (roue crantée) pour déverrouiller l'accès.");
        setIsSettingsOpen(true);
      } else {
        console.error("Erreur lors du chargement des sessions:", e);
        if (sessions.length === 0) await createNewSession();
      }
    } finally {
      setIsInitializing(false);
    }
  };

  useEffect(() => {
    fetchSessions();
  }, []);

  const handleSelectSession = async (id: string) => {
    setCurrentSessionId(id);
    try {
      const fullSession = await api.getSession(id);
      setSessions(prev => prev.map(s => s.id === id ? fullSession : s));
    } catch (e) {
      console.error("Failed to fetch full session", e);
    }
  };

  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [settings, setSettings] = useState<LocalSettings>(() => {
    const saved = localStorage.getItem('lumina-settings');
    if (saved) {
      try {
        return JSON.parse(saved);
      } catch (e) { }
    }
    return defaultSettings;
  });
  const [selectedModel, setSelectedModel] = useState<ModelType>(ModelType.PHI3);
  const [selectedMachine, setSelectedMachine] = useState<string>("");
  const [useSearch, setUseSearch] = useState(false);

  useEffect(() => {
    localStorage.setItem('lumina-settings', JSON.stringify(settings));
  }, [settings]);

  // Save local settings only
  useEffect(() => {
    localStorage.setItem('lumina-settings', JSON.stringify(settings));
  }, [settings]);

  // Resolve current session, with fallback to previously known if ID is transitioning
  const currentSession = sessions.find(s => s.id === currentSessionId) || sessions[0] || null;

  const handleSendMessage = useCallback(async (text: string, attachment?: string) => {
    if (!currentSessionId) return;

    const userMsg: Message = {
      id: generateUUID(),
      role: Role.USER,
      content: text,
      timestamp: new Date(),
      attachments: attachment ? [attachment] : undefined
    };

    setSessions(prev => prev.map(s =>
      s.id === currentSessionId
        ? { ...s, messages: [...s.messages, userMsg] }
        : s
    ));

    const assistantMsgId = generateUUID();
    const initialAssistantMsg: Message = {
      id: assistantMsgId,
      role: Role.ASSISTANT,
      content: "",
      timestamp: new Date(),
      isStreaming: true
    };

    setSessions(prev => prev.map(s =>
      s.id === currentSessionId
        ? { ...s, messages: [...s.messages, initialAssistantMsg] }
        : s
    ));

    let dynamicSessionId = currentSessionId;

    try {
      let accumulatedText = "";
      let groundingUrls: string[] = [];
      let sourceNodes: any[] = [];

      if (attachment) {
        const response = await api.analyzeImage(text, attachment, selectedModel);
        setSessions(prev => prev.map(s =>
          s.id === currentSessionId
            ? {
              ...s,
              messages: s.messages.map(m =>
                m.id === assistantMsgId ? { ...m, content: response || "", isStreaming: false } : m
              )
            }
            : s
        ));
      } else {
        // Filter messages to send only relevant history (User and Assistant)
        // Exclude the current temporary assistant message
        const history = (currentSession?.messages || [])
          .filter(m => m.id !== assistantMsgId && (m.role === Role.USER || m.role === Role.ASSISTANT))
          .map(m => ({ role: m.role, content: m.content }));

        const stream = api.streamChat(text, history, selectedModel, useSearch, selectedMachine, currentSessionId || undefined, settings);
        let lastUpdateTime = Date.now();

        for await (const chunk of stream) {
          if (chunk.sessionId && dynamicSessionId?.startsWith("temp-")) {
            // Wait for the UUID from the backend to safely rename the local session
            const newId = chunk.sessionId;

            // Atomically update both the session ID in the array AND the current selection
            setSessions(prev => {
              const updated = prev.map(s => s.id === dynamicSessionId ? { ...s, id: newId } : s);
              // Safe scheduling of the selection change
              setTimeout(() => setCurrentSessionId(newId), 0);
              return updated;
            });
            dynamicSessionId = newId;
            // Background refresh to get the standard title
            api.getSessions().then(data => {
              setSessions(prev => {
                const updated = [...prev];
                const idx = updated.findIndex(s => s.id === newId);
                const freshSession = data.find((d: any) => d.id === newId);
                if (idx !== -1 && freshSession) {
                  updated[idx] = { ...updated[idx], title: freshSession.title };
                }
                return updated;
              });
            });
          }

          if (chunk.text) {
            accumulatedText += chunk.text;
          }

          if (chunk.sourceNodes) {
            sourceNodes = chunk.sourceNodes;
          }

          if (chunk.groundingMetadata?.groundingChunks) {
            const urls = chunk.groundingMetadata.groundingChunks
              .filter((c: any) => c.web)
              .map((c: any) => c.web.uri);
            groundingUrls = [...new Set([...groundingUrls, ...urls])];
          }

          const now = Date.now();
          if (now - lastUpdateTime > 50) {
            setSessions(prev => prev.map(s =>
              s.id === dynamicSessionId
                ? {
                  ...s,
                  messages: s.messages.map(m =>
                    m.id === assistantMsgId ? { ...m, content: accumulatedText, groundingUrls, sourceNodes } : m
                  )
                }
                : s
            ));
            lastUpdateTime = now;
          }
        }

        // Final completely flushed update
        setSessions(prev => prev.map(s =>
          s.id === dynamicSessionId
            ? {
              ...s,
              messages: s.messages.map(m =>
                m.id === assistantMsgId ? { ...m, content: accumulatedText, groundingUrls, sourceNodes, isStreaming: false } : m
              )
            }
            : s
        ));
      }
    } catch (error: any) {
      const errorMsg = error.message?.includes("401_UNAUTHORIZED")
        ? "🔒 Erreur 401 Unauthorized : Votre Clé API Secrète est manquante ou invalide. Veuillez la configurer dans les paramètres locaux."
        : "Désolé, il y a un problème. Veuillez vérifier votre connexion ou vos paramètres. Si le problème persiste, veuillez contacter l'administrateur.";

      setSessions(prev => prev.map(s =>
        s.id === dynamicSessionId
          ? {
            ...s,
            messages: s.messages.map(m =>
              m.id === assistantMsgId
                ? { ...m, content: errorMsg, isStreaming: false }
                : m
            )
          }
          : s
      ));
    }
  }, [currentSessionId, selectedModel, useSearch, selectedMachine, settings]);

  const createNewSession = async () => {
    try {
      const serverSession = await api.createSession();
      const newSession: ChatSession = {
        id: serverSession.id,
        title: serverSession.title,
        messages: [
          {
            id: 'welcome',
            role: Role.ASSISTANT,
            content: "Prêt à aider. Qu'est-ce qui vous amène?",
            timestamp: new Date()
          }
        ],
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      };
      setSessions(prev => [newSession, ...prev]);
      setCurrentSessionId(serverSession.id);
    } catch (e) {
      console.error("Failed to create new session on server", e);
    }
  };

  const handleRenameSession = async (id: string, title: string) => {
    try {
      await api.renameSession(id, title);
      setSessions(prev => prev.map(s => s.id === id ? { ...s, title } : s));
    } catch (e) {
      console.error("Failed to rename session", e);
    }
  };

  const handleDeleteSession = async (id: string) => {
    try {
      await api.deleteSession(id);
      setSessions(prev => prev.filter(s => s.id !== id));
      if (currentSessionId === id) {
        setCurrentSessionId(null);
        // Load the next available session or create a new one
        const remaining = sessions.filter(s => s.id !== id);
        if (remaining.length > 0) {
          handleSelectSession(remaining[0].id);
        } else {
          createNewSession();
        }
      }
    } catch (e) {
      console.error("Failed to delete session", e);
    }
  };

  const handleExportSession = () => {
    if (!currentSession || currentSession.messages.length === 0) return;

    let mdContent = `# ${currentSession.title}\nDate: ${new Date(currentSession.created_at).toLocaleString()}\n\n`;

    currentSession.messages.forEach(msg => {
      mdContent += `### ${msg.role === Role.USER ? 'Utilisateur' : 'Expert (Lumina)'}\n`;
      mdContent += `${msg.content}\n\n`;
      if (msg.sourceNodes && msg.sourceNodes.length > 0) {
        mdContent += `**Sources:**\n`;
        msg.sourceNodes.forEach(src => {
          const fileName = src.url.split(/[/\\\\]/).pop() || src.url;
          mdContent += `- ${fileName}\n`;
        });
        mdContent += `\n`;
      }
      mdContent += `---\n\n`;
    });

    const blob = new Blob([mdContent], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `Diag_${currentSession.title.replace(/[^a-z0-9_-]/gi, '_').toLowerCase()}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="flex h-screen w-full bg-[#09090b] text-zinc-100 overflow-hidden">
      <Sidebar
        isOpen={isSidebarOpen}
        sessions={sessions}
        currentSessionId={currentSessionId}
        onSelectSession={handleSelectSession}
        onNewChat={createNewSession}
        onToggle={() => setIsSidebarOpen(!isSidebarOpen)}
        onOpenSettings={() => setIsSettingsOpen(true)}
        onRenameSession={handleRenameSession}
        onDeleteSession={handleDeleteSession}
      />

      <main className={`flex-1 flex flex-col min-w-0 transition-all duration-300 ${isSidebarOpen ? 'ml-0' : 'ml-0'}`}>
        <header className="h-16 border-b border-zinc-800 flex items-center justify-between px-6 glass sticky top-0 z-10">
          <div className="flex items-center gap-4">
            {!isSidebarOpen && (
              <button
                onClick={() => setIsSidebarOpen(true)}
                className="p-2 hover:bg-zinc-800 rounded-lg transition-colors"
                title="Ouvrir le panneau d'historique"
              >
                <i className="fa-solid fa-bars-staggered"></i>
              </button>
            )}
            <h1 className="text-lg font-semibold bg-gradient-to-r from-blue-400 to-emerald-400 bg-clip-text text-transparent truncate max-w-[200px] sm:max-w-md">
              {currentSession?.title || 'Lumina AI'}
            </h1>

            {currentSession && currentSession.messages.length > 1 && (
              <button
                onClick={handleExportSession}
                title="Exporter le rapport de diagnostic Markdown"
                className="p-1.5 text-zinc-500 hover:text-white hover:bg-zinc-800 rounded-lg transition-colors border border-transparent hover:border-zinc-700 ml-2 animate-in fade-in"
              >
                <i className="fa-solid fa-file-export"></i>
              </button>
            )}
          </div>

          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 px-3 py-1.5 bg-zinc-900 rounded-full border border-zinc-800">
              <span className="text-xs font-medium text-zinc-400">Machine:</span>
              <input
                type="text"
                placeholder="All"
                value={selectedMachine}
                onChange={(e) => setSelectedMachine(e.target.value)}
                className="bg-transparent text-xs font-semibold focus:outline-none w-16 text-zinc-200 placeholder-zinc-600"
              />
            </div>

            <button
              onClick={() => setSelectedModel(selectedModel === ModelType.PHI3 ? ModelType.MISTRAL_7B : ModelType.PHI3)}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-full border transition-all text-xs font-medium ${selectedModel === ModelType.MISTRAL_7B ? 'bg-amber-500/10 border-amber-500/50 text-amber-400' : 'bg-zinc-900 border-zinc-800 text-zinc-400 hover:text-zinc-300'}`}
              title={selectedModel === ModelType.MISTRAL_7B ? "Lent mais très exhaustif" : "Rapide mais limité aux bases"}
            >
              <i className={`fa-solid ${selectedModel === ModelType.MISTRAL_7B ? 'fa-brain text-amber-500' : 'fa-bolt text-blue-400'}`}></i>
              Analyse Profonde : {selectedModel === ModelType.MISTRAL_7B ? 'ON' : 'OFF'}
            </button>

            <button
              onClick={() => setUseSearch(!useSearch)}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-full border transition-all text-xs font-medium ${useSearch ? 'bg-emerald-500/10 border-emerald-500/50 text-emerald-400' : 'bg-zinc-900 border-zinc-800 text-zinc-400'}`}
            >
              <i className="fa-solid fa-earth-americas"></i>
              Recherche Internet : {useSearch ? 'ON' : 'OFF'}
            </button>
          </div>
        </header>

        <ChatArea
          messages={currentSession?.messages || []}
          onSendMessage={handleSendMessage}
        />
      </main>

      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        settings={settings}
        onSave={setSettings}
        onOpenExpertReview={() => {
          setIsSettingsOpen(false);
          setIsExpertModalOpen(true);
        }}
      />

      <ExpertReviewModal
        isOpen={isExpertModalOpen}
        onClose={() => setIsExpertModalOpen(false)}
      />
    </div>
  );
};

export default App;
