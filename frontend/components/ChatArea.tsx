
import React, { useState, useRef, useEffect } from 'react';
import { Message, Role } from '../types';
import { MessageBubble } from './MessageBubble';

interface ChatAreaProps {
  messages: Message[];
  onSendMessage: (text: string, attachment?: string) => void;
}

export const ChatArea: React.FC<ChatAreaProps> = ({ messages, onSendMessage }) => {
  const [input, setInput] = useState('');
  const [attachment, setAttachment] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() && !attachment) return;
    onSendMessage(input, attachment || undefined);
    setInput('');
    setAttachment(null);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = (readerEvent) => {
        setAttachment(readerEvent.target?.result as string);
      };
      reader.readAsDataURL(file);
    }
  };

  return (
    <div className="flex-1 flex flex-col min-h-0 relative">
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto px-4 py-8 space-y-6 scroll-smooth"
      >
        <div className="max-w-4xl mx-auto w-full">
          {messages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} />
          ))}
        </div>
      </div>

      <div className="p-4 lg:p-8 bg-gradient-to-t from-zinc-950 via-zinc-950/80 to-transparent">
        <form
          onSubmit={handleSubmit}
          className="max-w-4xl mx-auto relative group"
        >
          {attachment && (
            <div className="absolute -top-16 left-0 bg-zinc-900 border border-zinc-800 p-2 rounded-lg flex items-center gap-2 animate-in slide-in-from-bottom-2">
              <img src={attachment} alt="Preview" className="w-10 h-10 rounded object-cover" />
              <button
                type="button"
                onClick={() => setAttachment(null)}
                className="text-zinc-500 hover:text-white"
              >
                <i className="fa-solid fa-xmark"></i>
              </button>
            </div>
          )}

          <div className="relative glass border border-zinc-800 focus-within:border-blue-500/50 rounded-2xl transition-all shadow-2xl overflow-hidden">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSubmit(e);
                }
              }}
              placeholder="Demander à Lumina..."
              className="w-full bg-transparent border-none focus:ring-0 text-white p-4 pr-32 min-h-[60px] max-h-[200px] resize-none scrollbar-hide text-sm md:text-base"
              rows={1}
            />

            <div className="absolute right-2 bottom-2 flex items-center gap-2">
              <input
                type="file"
                ref={fileInputRef}
                className="hidden"
                accept="image/*"
                onChange={handleFileChange}
              />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="p-2 hover:bg-zinc-800 rounded-xl text-zinc-400 transition-colors"
                title="Attach image"
              >
                <i className="fa-solid fa-paperclip"></i>
              </button>

              <button
                type="submit"
                disabled={!input.trim() && !attachment}
                className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:hover:bg-blue-600 text-white px-4 py-2 rounded-xl font-semibold text-sm transition-all flex items-center gap-2 shadow-lg shadow-blue-900/20"
              >
                <span>Envoyer</span>
                <i className="fa-solid fa-paper-plane text-xs"></i>
              </button>
            </div>
          </div>
          <p className="mt-2 text-center text-[11px] text-zinc-500">
            Lumina AI POC Engine v0.4  • Microsoft 365 SSO Currently Unavailable • Localhost/Vite Optimized
          </p>
        </form>
      </div>
    </div>
  );
};
