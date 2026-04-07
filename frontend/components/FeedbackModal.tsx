import React, { useState } from 'react';

interface FeedbackModalProps {
    isOpen: boolean;
    onClose: () => void;
    onSubmit: (reason: string) => void;
}

export const FeedbackModal: React.FC<FeedbackModalProps> = ({ isOpen, onClose, onSubmit }) => {
    const [reason, setReason] = useState('');

    if (!isOpen) return null;

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        onSubmit(reason);
        setReason('');
        onClose();
    };

    return (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4 animate-in fade-in duration-200">
            <div
                className="bg-zinc-900 border border-zinc-700 rounded-2xl w-full max-w-md p-6 shadow-2xl scale-100 animate-in zoom-in-95 duration-200"
                onClick={(e) => e.stopPropagation()}
            >
                <h3 className="text-lg font-semibold text-white mb-2">Signaler un problème</h3>
                <p className="text-sm text-zinc-400 mb-4">
                    Pourquoi cette réponse n'est-elle pas satisfaisante ?
                </p>

                <form onSubmit={handleSubmit}>
                    <textarea
                        value={reason}
                        onChange={(e) => setReason(e.target.value)}
                        placeholder="Ex: La réponse est fausse, incomplète, ou concerne une autre machine..."
                        className="w-full bg-zinc-950 border border-zinc-800 rounded-xl p-3 text-sm text-zinc-200 focus:outline-none focus:border-blue-500/50 min-h-[100px] resize-none mb-4"
                        autoFocus
                    />

                    <div className="flex justify-end gap-3">
                        <button
                            type="button"
                            onClick={onClose}
                            className="px-4 py-2 rounded-lg text-sm font-medium text-zinc-400 hover:text-white hover:bg-zinc-800 transition-colors"
                        >
                            Annuler
                        </button>
                        <button
                            type="submit"
                            disabled={!reason.trim()}
                            className="px-4 py-2 rounded-lg text-sm font-medium bg-red-600 text-white hover:bg-red-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-lg shadow-red-900/20"
                        >
                            Envoyer
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
};
