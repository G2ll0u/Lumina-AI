import React, { useState, useEffect } from 'react';
import { api } from '../services/apiService';

interface ExpertReviewModalProps {
    isOpen: boolean;
    onClose: () => void;
}

export const ExpertReviewModal: React.FC<ExpertReviewModalProps> = ({ isOpen, onClose }) => {
    const [feedbacks, setFeedbacks] = useState<any[]>([]);
    const [verifiedKnowledge, setVerifiedKnowledge] = useState<any[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [selectedFeedback, setSelectedFeedback] = useState<any | null>(null);
    const [selectedKnowledge, setSelectedKnowledge] = useState<any | null>(null);
    const [correction, setCorrection] = useState("");
    const [activeTab, setActiveTab] = useState<'pending' | 'verified'>('pending');

    const fetchFeedbacks = async () => {
        setIsLoading(true);
        try {
            const data = await api.getFeedbacks();
            setFeedbacks(data);
        } catch (e) {
            console.error(e);
        } finally {
            setIsLoading(false);
        }
    };

    const fetchVerifiedKnowledge = async () => {
        setIsLoading(true);
        try {
            const data = await api.getVerifiedKnowledge();
            setVerifiedKnowledge(data);
        } catch (e) {
            console.error(e);
        } finally {
            setIsLoading(false);
        }
    };

    useEffect(() => {
        if (isOpen) {
            if (activeTab === 'pending') {
                fetchFeedbacks();
            } else {
                fetchVerifiedKnowledge();
            }
            setSelectedFeedback(null);
            setSelectedKnowledge(null);
            setCorrection("");
        }
    }, [isOpen, activeTab]);

    const handleDeleteFeedback = async (index: number) => {
        if (!confirm("Supprimer ce feedback ?")) return;
        try {
            await api.deleteFeedback(index);
            fetchFeedbacks();
            if (selectedFeedback && feedbacks.indexOf(selectedFeedback) === index) {
                setSelectedFeedback(null);
            }
        } catch (e) {
            alert("Erreur lors de la suppression");
        }
    };

    const handleDeleteKnowledge = async (id: string) => {
        if (!confirm("Supprimer cette connaissance de l'IA définitivement ?")) return;
        try {
            await api.deleteVerifiedKnowledge(id);
            fetchVerifiedKnowledge();
            if (selectedKnowledge && selectedKnowledge.id === id) {
                setSelectedKnowledge(null);
            }
        } catch (e) {
            alert("Erreur lors de la suppression");
        }
    };

    const handleValidate = async () => {
        if (!selectedFeedback || !correction.trim()) return;

        const index = feedbacks.indexOf(selectedFeedback);
        try {
            await api.addVerifiedKnowledge(
                selectedFeedback.context?.question || selectedFeedback.reason,
                correction,
                selectedFeedback.machine_id,
                index
            );
            alert("Connaissance enregistrée ! L'IA utilisera cette réponse en priorité.");
            fetchFeedbacks();
            setSelectedFeedback(null);
            setCorrection("");
        } catch (e) {
            alert("Erreur lors de l'enregistrement");
        }
    };

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-300">
            <div className="bg-zinc-950 border border-zinc-800 w-full max-w-5xl h-[85vh] rounded-3xl shadow-2xl flex flex-col overflow-hidden">
                {/* Header */}
                <div className="p-6 border-b border-zinc-800 flex items-center justify-between bg-zinc-900/50">
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-xl bg-amber-500/10 flex items-center justify-center text-amber-500">
                            <i className="fa-solid fa-graduation-cap text-lg"></i>
                        </div>
                        <div>
                            <h2 className="text-xl font-bold text-white">Revue Expert & Apprentissage</h2>
                            <p className="text-xs text-zinc-500">Améliorez l'IA en corrigeant les erreurs signalées</p>
                        </div>
                    </div>
                    <button onClick={onClose} className="p-2 hover:bg-zinc-800 rounded-full text-zinc-400 transition-colors">
                        <i className="fa-solid fa-xmark text-xl"></i>
                    </button>
                </div>

                <div className="flex-1 flex overflow-hidden">
                    {/* Left: Sidebar (Tabs + List) */}
                    <div className="w-1/3 border-r border-zinc-800 flex flex-col bg-zinc-950">
                        {/* Tabs Switches */}
                        <div className="flex border-b border-zinc-800">
                            <button
                                onClick={() => setActiveTab('pending')}
                                className={`flex-1 py-3 text-xs font-bold uppercase tracking-wider transition-all ${activeTab === 'pending' ? 'text-blue-400 border-b-2 border-blue-500 bg-blue-500/5' : 'text-zinc-500 hover:text-zinc-300'
                                    }`}
                            >
                                À traiter ({feedbacks.length})
                            </button>
                            <button
                                onClick={() => setActiveTab('verified')}
                                className={`flex-1 py-3 text-xs font-bold uppercase tracking-wider transition-all ${activeTab === 'verified' ? 'text-emerald-400 border-b-2 border-emerald-500 bg-emerald-500/5' : 'text-zinc-500 hover:text-zinc-300'
                                    }`}
                            >
                                Traités ({verifiedKnowledge.length})
                            </button>
                        </div>

                        <div className="flex-1 overflow-y-auto space-y-1 p-2">
                            {isLoading ? (
                                <div className="p-8 text-center text-zinc-600 text-sm italic">Chargement...</div>
                            ) : activeTab === 'pending' ? (
                                feedbacks.length === 0 ? (
                                    <div className="p-8 text-center text-zinc-600 text-sm italic">Aucun feedback à traiter</div>
                                ) : (
                                    feedbacks.map((fb, idx) => (
                                        <div
                                            key={idx}
                                            onClick={() => {
                                                setSelectedFeedback(fb);
                                                setSelectedKnowledge(null);
                                                setCorrection("");
                                            }}
                                            className={`p-3 rounded-xl cursor-pointer transition-all border ${selectedFeedback === fb
                                                ? 'bg-blue-600/10 border-blue-500/50'
                                                : 'border-transparent hover:bg-zinc-900'
                                                }`}
                                        >
                                            <div className="flex justify-between items-start mb-1">
                                                <span className="text-[10px] text-zinc-500">{new Date(fb.timestamp).toLocaleDateString()}</span>
                                                <button
                                                    onClick={(e) => { e.stopPropagation(); handleDeleteFeedback(idx); }}
                                                    className="text-zinc-700 hover:text-red-500 p-1"
                                                >
                                                    <i className="fa-solid fa-trash-can text-xs"></i>
                                                </button>
                                            </div>
                                            <p className="text-sm font-medium text-zinc-200 line-clamp-2">
                                                {fb.context?.question || fb.reason}
                                            </p>
                                        </div>
                                    ))
                                )
                            ) : (
                                verifiedKnowledge.length === 0 ? (
                                    <div className="p-8 text-center text-zinc-600 text-sm italic">Aucune connaissance injectée</div>
                                ) : (
                                    verifiedKnowledge.map((kn) => (
                                        <div
                                            key={kn.id}
                                            onClick={() => {
                                                setSelectedKnowledge(kn);
                                                setSelectedFeedback(null);
                                                setCorrection("");
                                            }}
                                            className={`p-3 rounded-xl cursor-pointer transition-all border ${selectedKnowledge === kn
                                                ? 'bg-emerald-600/10 border-emerald-500/50'
                                                : 'border-transparent hover:bg-zinc-900'
                                                }`}
                                        >
                                            <div className="flex justify-between items-start mb-1">
                                                <span className="text-[10px] text-zinc-500">{new Date(kn.metadata.timestamp).toLocaleDateString()}</span>
                                                <button
                                                    onClick={(e) => { e.stopPropagation(); handleDeleteKnowledge(kn.id); }}
                                                    className="text-zinc-700 hover:text-red-500 p-1"
                                                >
                                                    <i className="fa-solid fa-trash-can text-xs"></i>
                                                </button>
                                            </div>
                                            <p className="text-sm font-medium text-zinc-200 line-clamp-2">
                                                {kn.answer}
                                            </p>
                                        </div>
                                    ))
                                )
                            )}
                        </div>
                    </div>

                    {/* Right: Content Area */}
                    <div className="flex-1 flex flex-col bg-zinc-900/10 overflow-hidden">
                        {(activeTab === 'pending' && selectedFeedback) ? (
                            <div className="flex-1 flex flex-col overflow-hidden animate-in fade-in slide-in-from-right-4 duration-300">
                                <div className="flex-1 overflow-y-auto p-6 space-y-6">
                                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                        <div className="space-y-2">
                                            <h4 className="text-xs font-bold text-zinc-500 uppercase">Question Utilisateur</h4>
                                            <div className="p-3 bg-zinc-900 border border-zinc-800 rounded-xl text-sm italic text-zinc-300">
                                                "{selectedFeedback.context?.question || "Non capturée"}"
                                            </div>
                                        </div>
                                        <div className="space-y-2">
                                            <h4 className="text-xs font-bold text-amber-500 uppercase">Motif du Signalement</h4>
                                            <div className="p-3 bg-amber-500/5 border border-amber-500/20 rounded-xl text-sm text-amber-200/80">
                                                {selectedFeedback.reason || "Aucun commentaire précisé"}
                                            </div>
                                        </div>
                                        <div className="space-y-2">
                                            <h4 className="text-xs font-bold text-zinc-500 uppercase">Réponse erronée de l'IA</h4>
                                            <div className="p-3 bg-red-950/10 border border-red-900/30 rounded-xl text-sm text-red-200/70">
                                                {selectedFeedback.context?.answer || "Non capturée"}
                                            </div>
                                        </div>
                                    </div>

                                    {selectedFeedback.context?.source_nodes && (
                                        <div className="space-y-2">
                                            <h4 className="text-xs font-bold text-zinc-500 uppercase tracking-wide">Documents consultés</h4>
                                            <div className="space-y-2">
                                                {selectedFeedback.context.source_nodes.map((node: any, i: number) => (
                                                    <div key={i} className="p-2 bg-zinc-950 border border-zinc-800 rounded text-[11px] text-zinc-400">
                                                        <span className="font-bold text-zinc-500 block mb-1">Source: {node.url.split(/[/\\]/).pop()}</span>
                                                        <p className="line-clamp-2 italic">{node.snippet}</p>
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    )}

                                    <div className="space-y-2 pt-4">
                                        <div className="flex justify-between items-center">
                                            <h4 className="text-xs font-bold text-blue-400 uppercase">Correction de l'Expert</h4>
                                            <span className="text-[10px] text-zinc-500 italic">Sera injecté en priorité dans le RAG</span>
                                        </div>
                                        <textarea
                                            value={correction}
                                            onChange={(e) => setCorrection(e.target.value)}
                                            placeholder="Saisissez ici la réponse technique exacte..."
                                            className="w-full h-40 bg-zinc-950 border border-blue-500/20 focus:border-blue-500 rounded-xl p-4 text-sm text-white resize-none outline-none shadow-inner"
                                        />
                                    </div>
                                </div>
                                <div className="p-4 border-t border-zinc-800 bg-zinc-900/50 flex justify-end gap-3">
                                    <button onClick={() => setSelectedFeedback(null)} className="px-4 py-2 text-sm text-zinc-400 hover:text-white transition-colors">Annuler</button>
                                    <button onClick={handleValidate} disabled={!correction.trim()} className="px-6 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-30 text-white text-sm font-bold rounded-xl shadow-lg">Valider & Injecter dans l'IA</button>
                                </div>
                            </div>
                        ) : (activeTab === 'verified' && selectedKnowledge) ? (
                            <div className="flex-1 flex flex-col overflow-hidden animate-in fade-in slide-in-from-right-4 duration-300">
                                <div className="flex-1 overflow-y-auto p-6 space-y-6">
                                    <div className="space-y-2">
                                        <h4 className="text-xs font-bold text-zinc-500 uppercase tracking-wider">Connaissance Validée le {new Date(selectedKnowledge.metadata.timestamp).toLocaleString()}</h4>
                                        <div className="p-4 bg-emerald-950/10 border border-emerald-500/20 rounded-2xl text-emerald-100 text-sm leading-relaxed shadow-lg">
                                            {selectedKnowledge.answer}
                                        </div>
                                    </div>
                                    <div className="p-4 bg-zinc-900/50 rounded-xl border border-zinc-800 text-xs text-zinc-500 space-y-2">
                                        <p><span className="font-bold text-zinc-400">Machine ID:</span> {selectedKnowledge.metadata.machine_id || "Général"}</p>
                                        <p><span className="font-bold text-zinc-400">ID Unique:</span> {selectedKnowledge.id}</p>
                                    </div>
                                </div>
                                <div className="p-4 border-t border-zinc-800 bg-zinc-900/50 flex justify-end">
                                    <button onClick={() => handleDeleteKnowledge(selectedKnowledge.id)} className="px-4 py-2 bg-red-600/10 hover:bg-red-600/20 text-red-500 text-xs font-bold rounded-lg border border-red-500/20">Supprimer</button>
                                </div>
                            </div>
                        ) : (
                            <div className="flex-1 flex flex-col items-center justify-center text-zinc-600 p-12 text-center">
                                <i className="fa-solid fa-graduation-cap text-5xl mb-4 opacity-10"></i>
                                <p className="text-sm italic">{activeTab === 'pending' ? "Sélectionnez un feedback pour corriger" : "Sélectionnez une connaissance pour la consulter"}</p>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};
