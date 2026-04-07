import React, { useState, useEffect, useRef } from 'react';
import { api } from '../services/apiService';

export interface LocalSettings {
    apiKey: string;
    temperature: number;
    rag_top_k: number;
    use_decomposition: boolean;
    include_all_versions: boolean;
    max_context_length: number;
    system_prompt: string;
}

export const defaultSettings: LocalSettings = {
    apiKey: "",
    temperature: 0.1,
    rag_top_k: 6,
    use_decomposition: true,
    include_all_versions: false,
    max_context_length: 15000,
    system_prompt: ""
};

interface SettingsModalProps {
    isOpen: boolean;
    onClose: () => void;
    settings: LocalSettings;
    onSave: (newSettings: LocalSettings) => void;
    onOpenExpertReview: () => void;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({ isOpen, onClose, settings, onSave, onOpenExpertReview }) => {
    const [localSettings, setLocalSettings] = useState<LocalSettings>(settings);
    const [activeTab, setActiveTab] = useState<'settings' | 'documents'>('settings');
    const [documents, setDocuments] = useState<any[]>([]);
    const [ingestionStatus, setIngestionStatus] = useState<{ is_running: boolean, last_run: string | null, logs: string } | null>(null);
    const [uploadPath, setUploadPath] = useState("");
    const [isUploading, setIsUploading] = useState(false);
    const fileInputRef = useRef<HTMLInputElement>(null);

    // Sync state if props change when opening
    useEffect(() => {
        if (isOpen) {
            setLocalSettings(settings);
            if (activeTab === 'documents') {
                fetchDocuments();
                fetchIngestionStatus();
            }
        }
    }, [isOpen, settings, activeTab]);

    // Polling for ingestion status when running
    useEffect(() => {
        let interval: NodeJS.Timeout;
        if (isOpen && activeTab === 'documents' && ingestionStatus?.is_running) {
            interval = setInterval(fetchIngestionStatus, 2000);
        }
        return () => clearInterval(interval);
    }, [isOpen, activeTab, ingestionStatus?.is_running]);

    const fetchDocuments = async () => {
        try {
            const docs = await api.getDocuments();
            setDocuments(docs);
        } catch (e) {
            console.error(e);
        }
    };

    const fetchIngestionStatus = async () => {
        try {
            const status = await api.getIngestionStatus();
            setIngestionStatus(status);
        } catch (e) {
            console.error(e);
        }
    };

    const handleUploadClick = () => {
        fileInputRef.current?.click();
    };

    const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;

        setIsUploading(true);
        try {
            await api.uploadDocument(uploadPath.trim(), file);
            await fetchDocuments();
        } catch (error) {
            alert("Erreur lors de l'upload du fichier");
        } finally {
            setIsUploading(false);
            if (fileInputRef.current) fileInputRef.current.value = '';
        }
    };

    const handleDeleteDocument = async (path: string) => {
        if (confirm("Supprimer ce fichier définitivement ?")) {
            try {
                await api.deleteDocument(path);
                await fetchDocuments();
            } catch (error) {
                alert("Erreur lors de la suppression");
            }
        }
    };

    const handleStartIngestion = async () => {
        try {
            const target = uploadPath.trim();
            await api.startIngestion(target);
            await fetchIngestionStatus();
        } catch (error) {
            alert("L'ingestion est peut-être déjà en cours");
        }
    };

    if (!isOpen) return null;

    const handleSave = () => {
        onSave(localSettings);
        onClose();
    };

    const handleReset = () => {
        setLocalSettings(defaultSettings);
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm animate-in fade-in duration-200">
            <div
                className="bg-zinc-950 border border-zinc-800 rounded-2xl w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col shadow-2xl animate-in zoom-in-95 duration-200"
                onClick={(e) => e.stopPropagation()}
            >
                {/* Header */}
                <div className="px-6 py-0 border-b border-zinc-800 flex items-center justify-between bg-zinc-900/50">
                    <div className="flex h-16">
                        <button
                            className={`px-4 h-full flex items-center gap-2 font-medium border-b-2 transition-colors ${activeTab === 'settings' ? 'border-blue-500 text-blue-400' : 'border-transparent text-zinc-400 hover:text-zinc-200'}`}
                            onClick={() => setActiveTab('settings')}
                        >
                            <i className="fa-solid fa-sliders"></i>
                            <span className="hidden sm:inline">Paramètres Locaux</span>
                        </button>
                        <button
                            className={`px-4 h-full flex items-center gap-2 font-medium border-b-2 transition-colors ${activeTab === 'documents' ? 'border-emerald-500 text-emerald-400' : 'border-transparent text-zinc-400 hover:text-zinc-200'}`}
                            onClick={() => setActiveTab('documents')}
                        >
                            <i className="fa-solid fa-folder-open"></i>
                            <span className="hidden sm:inline">Documents</span>
                        </button>
                    </div>
                    <button
                        onClick={onClose}
                        className="p-2 hover:bg-zinc-800 rounded-lg text-zinc-400 hover:text-white transition-colors"
                    >
                        <i className="fa-solid fa-xmark"></i>
                    </button>
                </div>

                <div className="flex-1 overflow-y-auto p-6 min-h-[50vh]">
                    {activeTab === 'settings' ? (
                        <div className="space-y-8">
                            {/* Section LLM */}
                            <section className="space-y-4">
                                <div className="text-sm text-zinc-400 tracking-wider flex items-center gap-2">
                                    Si vous ne savez pas comment fonctionne les paramètres, laissez les valeurs par défaut.
                                </div>
                                <h3 className="text-sm font-bold text-zinc-400 uppercase tracking-wider flex items-center gap-2">
                                    <i className="fa-solid fa-microchip"></i> Modèle Langage (LLM)
                                </h3>

                                <div className="space-y-3 bg-zinc-900/30 p-4 rounded-xl border border-zinc-800/50">
                                    <div>
                                        <div className="flex justify-between mb-1">
                                            <label className="text-sm font-medium text-zinc-300">
                                                <i className="fa-solid fa-key mr-2"></i>Clé API Secrète (Serveur)
                                            </label>
                                        </div>
                                        <div className="text-xs text-zinc-500 mb-2 block">
                                            Laissez vide si le backend est en accès libre.
                                        </div>
                                        <input
                                            type="password"
                                            value={localSettings.apiKey || ""}
                                            onChange={(e) => setLocalSettings({ ...localSettings, apiKey: e.target.value })}
                                            placeholder="••••••••••••••••"
                                            autoComplete="new-password"
                                            className="w-full bg-zinc-900 border border-zinc-700 rounded-lg p-3 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                                        />
                                    </div>
                                    <hr className="border-zinc-800/50 my-2" />
                                    <div>
                                        <div className="flex justify-between mb-1">
                                            <label className="text-sm font-medium text-zinc-300">
                                                🌡️ Température de génération
                                            </label>
                                            <span className="text-sm text-blue-400 font-mono">
                                                {localSettings.temperature.toFixed(2)}
                                            </span>
                                        </div>
                                        <div className="text-xs text-zinc-500 mb-3 block">
                                            Degré de liberté.<br />0.0 = Analytique & précis, 1.0 = Très créatif (Risque fort d'hallucination).
                                        </div>
                                        <input
                                            type="range" min="0" max="1" step="0.1"
                                            value={localSettings.temperature}
                                            onChange={(e) => setLocalSettings({ ...localSettings, temperature: parseFloat(e.target.value) })}
                                            className="w-full accent-blue-500 h-1.5 bg-zinc-800 rounded-full appearance-none outline-none cursor-pointer"
                                        />
                                    </div>

                                    <div className="pt-3">
                                        <label className="text-sm font-medium text-zinc-300 mb-1 block">Prompt Système (Comportement de base)</label>
                                        <p className="text-xs text-zinc-500 mb-2">Configurez la logique par défaut de l'Expert IA. Laissez vide pour utiliser le comportement de Lumina par défaut.</p>
                                        <textarea
                                            value={localSettings.system_prompt}
                                            onChange={(e) => setLocalSettings({ ...localSettings, system_prompt: e.target.value })}
                                            placeholder="Tu es un ingénieur expert..."
                                            className="w-full bg-zinc-900 border border-zinc-700 rounded-lg p-3 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 min-h-[100px] resize-y"
                                        />
                                    </div>
                                </div>
                            </section>

                            {/* Section RAG */}
                            <section className="space-y-4">
                                <h3 className="text-sm font-bold text-zinc-400 uppercase tracking-wider flex items-center gap-2">
                                    <i className="fa-solid fa-database"></i> Recherche Documentaire (RAG)
                                </h3>

                                <div className="space-y-5 bg-zinc-900/30 p-4 rounded-xl border border-zinc-800/50">

                                    <label className="flex items-start gap-4 cursor-pointer group">
                                        <div className="relative flex items-center pt-1">
                                            <input
                                                type="checkbox"
                                                className="sr-only peer"
                                                checked={localSettings.use_decomposition}
                                                onChange={(e) => setLocalSettings({ ...localSettings, use_decomposition: e.target.checked })}
                                            />
                                            <div className="w-9 h-5 bg-zinc-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[6px] after:left-[2px] after:bg-white after:border-zinc-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-emerald-500"></div>
                                        </div>
                                        <div>
                                            <div className="text-sm font-medium text-zinc-300 group-hover:text-white transition-colors">Décomposition des Requetes Complexes (Agent LLM)</div>
                                            <div className="text-xs text-zinc-500 leading-relaxed mt-0.5">Demande d'abord au LLM de diviser la longue question de l'utilisateur en plusieurs petites recherches indépendantes pour maximiser les trouvailles hybrides (fortement recommandé).</div>
                                        </div>
                                    </label>

                                    {/* Toggle: Inclure les anciennes versions */}
                                    <label className="flex items-start gap-4 cursor-pointer group">
                                        <div className="relative flex items-center pt-1">
                                            <input
                                                type="checkbox"
                                                className="sr-only peer"
                                                checked={localSettings.include_all_versions}
                                                onChange={(e) => setLocalSettings({ ...localSettings, include_all_versions: e.target.checked })}
                                            />
                                            <div className="w-9 h-5 bg-zinc-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[6px] after:left-[2px] after:bg-white after:border-zinc-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-amber-500"></div>
                                        </div>
                                        <div>
                                            <div className="text-sm font-medium text-zinc-300 group-hover:text-white transition-colors flex items-center gap-2">
                                                Inclure les anciennes versions
                                                <span className="text-[10px] font-semibold text-amber-400 bg-amber-400/10 border border-amber-400/30 px-1.5 py-0.5 rounded">⚠️ Risque</span>
                                            </div>
                                            <div className="text-xs text-zinc-500 leading-relaxed mt-0.5">Par défaut, seule la dernière version de chaque document est interrogée. Activer ceci inclut toutes les versions historiques (peut induire des réponses contradictoires ou obsolètes).</div>
                                        </div>
                                    </label>

                                    <div>
                                        <div className="flex justify-between mb-1">
                                            <label className="text-sm font-medium text-zinc-300">Densité Analytique (Top K du Reranker)</label>
                                            <span className="text-sm text-blue-400 font-mono">{localSettings.rag_top_k} blocs</span>
                                        </div>
                                        <p className="text-xs text-zinc-500 mb-3">Nombre final de documents conservés après le filtre de précision et injectés dans le contexte de l'IA.</p>
                                        <input
                                            type="range" min="1" max="15" step="1"
                                            value={localSettings.rag_top_k}
                                            onChange={(e) => setLocalSettings({ ...localSettings, rag_top_k: parseInt(e.target.value) })}
                                            className="w-full accent-blue-500 h-1.5 bg-zinc-800 rounded-full appearance-none outline-none cursor-pointer"
                                        />
                                    </div>

                                    <div>
                                        <div className="flex justify-between mb-1">
                                            <label className="text-sm font-medium text-zinc-300">Taille Max de Contexte</label>
                                            <span className="text-sm text-blue-400 font-mono">{localSettings.max_context_length} caractères</span>
                                        </div>
                                        <p className="text-xs text-zinc-500 mb-3">Garde-fou avant de tronquer les documents RAG pour éviter un dépassement réseau ou mémoire du serveur Ollama.</p>
                                        <input
                                            type="range" min="1000" max="30000" step="500"
                                            value={localSettings.max_context_length}
                                            onChange={(e) => setLocalSettings({ ...localSettings, max_context_length: parseInt(e.target.value) })}
                                            className="w-full accent-emerald-500 h-1.5 bg-zinc-800 rounded-full appearance-none outline-none cursor-pointer"
                                        />
                                    </div>
                                </div>
                            </section>

                            <div className="mt-8 pt-6 border-t border-zinc-800">
                                <h4 className="text-xs font-bold text-zinc-500 uppercase mb-4">Administration & Apprentissage</h4>
                                <button
                                    onClick={onOpenExpertReview}
                                    className="w-full flex items-center justify-between p-4 bg-amber-500/10 border border-amber-500/20 hover:border-amber-500/50 rounded-2xl group transition-all"
                                >
                                    <div className="flex items-center gap-4">
                                        <div className="w-10 h-10 rounded-xl bg-amber-500/20 flex items-center justify-center text-amber-500">
                                            <i className="fa-solid fa-graduation-cap"></i>
                                        </div>
                                        <div className="text-left">
                                            <p className="text-sm font-bold text-amber-500">Revue Expert & Corrections</p>
                                            <p className="text-[10px] text-zinc-500">Gérer les feedbacks et améliorer l'IA</p>
                                        </div>
                                    </div>
                                    <i className="fa-solid fa-chevron-right text-zinc-700 group-hover:text-amber-500 transition-colors"></i>
                                </button>
                            </div>
                        </div>
                    ) : (
                        <div className="space-y-6">
                            {/* Section Indexation (ChromaDB) */}
                            <section className="bg-zinc-900/30 p-5 rounded-xl border border-zinc-800/50 flex flex-col gap-4">
                                <div className="flex items-center justify-between">
                                    <h3 className="text-sm font-bold text-zinc-100 flex items-center gap-2">
                                        <i className="fa-solid fa-brain text-emerald-400"></i> Indexation Vectorielle (ChromaDB)
                                    </h3>
                                </div>
                                <p className="text-xs text-zinc-400 mb-2">Les documents dans <code>{(import.meta as any).env.VITE_DOCS_PATH || "C:\\POC\\Test Local"}</code> doivent être indexés par l'IA pour être lus. Si vous venez de rajouter des manuels dans l'explorateur Windows, lancez le scan ci-dessous.</p>

                                <div className="flex items-end gap-3 bg-zinc-950/50 p-3 rounded-lg border border-zinc-800/50">
                                    <div className="flex-1">
                                        <label className="text-xs font-semibold text-zinc-400 mb-1.5 block">Machine Cible (ex: "3985", laissé vide pour tout scanner)</label>
                                        <input
                                            type="text"
                                            value={uploadPath}
                                            onChange={(e) => setUploadPath(e.target.value)}
                                            placeholder="Ex: 3986 - IC3"
                                            className="w-full bg-zinc-900 border border-zinc-700 focus:border-emerald-500 rounded-md px-3 py-2 text-sm text-zinc-200 outline-none transition-colors"
                                        />
                                    </div>
                                    <button
                                        onClick={handleStartIngestion}
                                        disabled={ingestionStatus?.is_running}
                                        className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors flex items-center gap-2 ${ingestionStatus?.is_running ? 'bg-zinc-800 text-zinc-500 cursor-not-allowed' : 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg shadow-emerald-900/20'}`}
                                    >
                                        <i className={`fa-solid fa-bolt ${ingestionStatus?.is_running ? 'animate-pulse text-emerald-500' : ''}`}></i>
                                        {ingestionStatus?.is_running ? "Indexation en cours..." : "Lancer le Scan"}
                                    </button>
                                </div>

                                {ingestionStatus?.logs && (
                                    <div className="bg-zinc-950 border border-zinc-800 rounded-lg p-3 mt-2">
                                        <div className="text-[10px] font-mono text-zinc-500 mb-1 flex justify-between">
                                            <span>Logs d'Ingestion :</span>
                                            {ingestionStatus.last_run && <span>Dernier run: {new Date(ingestionStatus.last_run).toLocaleString()}</span>}
                                        </div>
                                        <div className="h-32 overflow-y-auto font-mono text-xs text-zinc-300 whitespace-pre-wrap">
                                            {ingestionStatus.logs}
                                        </div>
                                    </div>
                                )}
                            </section>

                            {/* Section Liste des documents files */}
                            <section>
                                <h3 className="text-sm font-bold text-zinc-400 uppercase tracking-wider flex items-center gap-2 mb-3">
                                    <i className="fa-solid fa-list"></i> Fichiers sur le Serveur ({documents.length})
                                </h3>

                                <div className="border border-zinc-800 rounded-xl overflow-hidden">
                                    <div className="max-h-60 overflow-y-auto">
                                        <table className="w-full text-left text-sm text-zinc-400">
                                            <thead className="bg-zinc-900/80 sticky top-0 text-xs uppercase font-semibold text-zinc-500 border-b border-zinc-800">
                                                <tr>
                                                    <th className="px-4 py-2">Fichier</th>
                                                    <th className="px-4 py-2">Chemin</th>
                                                    <th className="px-4 py-2 w-24">Taille</th>
                                                    <th className="px-4 py-2 w-10 text-center">Action</th>
                                                </tr>
                                            </thead>
                                            <tbody className="divide-y divide-zinc-800/50 bg-zinc-900/20">
                                                {documents.map((doc, i) => (
                                                    <tr key={i} className="hover:bg-zinc-800/30 transition-colors">
                                                        <td className="px-4 py-2 font-medium text-zinc-300 truncate max-w-[200px]" title={doc.name}>{doc.name}</td>
                                                        <td className="px-4 py-2 text-zinc-500 font-mono text-xs truncate max-w-[150px]" title={doc.path}>{doc.path}</td>
                                                        <td className="px-4 py-2 font-mono text-xs">{(doc.size / 1024 / 1024).toFixed(2)} MB</td>
                                                        <td className="px-4 py-2 text-center">
                                                            <button
                                                                onClick={() => handleDeleteDocument(doc.path)}
                                                                className="text-zinc-500 hover:text-red-400 p-1 rounded hover:bg-zinc-800 transition-colors"
                                                                title="Supprimer"
                                                            >
                                                                <i className="fa-solid fa-trash text-xs"></i>
                                                            </button>
                                                        </td>
                                                    </tr>
                                                ))}
                                                {documents.length === 0 && (
                                                    <tr>
                                                        <td colSpan={4} className="px-4 py-6 text-center text-zinc-600">Aucun document trouvé sur le serveur.</td>
                                                    </tr>
                                                )}
                                            </tbody>
                                        </table>
                                    </div>
                                </div>
                            </section>
                        </div>
                    )}
                </div>

                {/* Footer */}
                <div className="px-6 py-4 border-t border-zinc-800 bg-zinc-900/50 flex items-center justify-between">
                    {activeTab === 'settings' ? (
                        <button
                            onClick={handleReset}
                            className="text-xs font-semibold text-zinc-500 hover:text-zinc-300 transition-colors px-3 py-2 rounded-lg hover:bg-zinc-800"
                        >
                            Réinitialiser
                        </button>
                    ) : (
                        <div /> // Dummy div for documents tab reset
                    )}

                    <div className="flex gap-3 ml-auto">
                        {activeTab === 'settings' ? (
                            <>
                                <button
                                    onClick={onClose}
                                    className="px-4 py-2 text-sm font-medium text-zinc-300 hover:text-white bg-zinc-800 hover:bg-zinc-700 rounded-lg transition-colors border border-zinc-700"
                                >
                                    Annuler
                                </button>
                                <button
                                    onClick={handleSave}
                                    className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-500 rounded-lg transition-colors shadow-lg shadow-blue-500/20"
                                >
                                    Enregistrer
                                </button>
                            </>
                        ) : (
                            <button
                                onClick={onClose}
                                className="px-6 py-2 bg-zinc-800 hover:bg-zinc-700 text-white rounded-lg font-medium transition-colors"
                            >
                                Fermer
                            </button>
                        )}
                    </div>
                </div>

            </div>
        </div>
    );
};
