import React, { useState } from 'react';
import { Message, Role } from '../types';
import { api } from '../services/apiService';
import { FeedbackModal } from './FeedbackModal';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface MessageBubbleProps {
  message: Message;
}

export const MessageBubble: React.FC<MessageBubbleProps> = ({ message }) => {
  const isAssistant = message.role === Role.ASSISTANT;
  const [feedbackStatus, setFeedbackStatus] = useState<'none' | 'liked' | 'disliked'>('none');
  const [isModalOpen, setIsModalOpen] = useState(false);

  const handleLike = () => {
    if (feedbackStatus === 'liked') return;
    setFeedbackStatus('liked');
    api.sendFeedback(message.id, "Positive feedback", true);
  };

  const handleDislike = () => {
    if (feedbackStatus === 'disliked') return;
    setIsModalOpen(true);
  };

  const handleSubmitDislike = (reason: string) => {
    setFeedbackStatus('disliked');
    api.sendFeedback(message.id, reason, false);
  };

  return (
    <>
      <div className={`flex gap-4 md:gap-6 mb-8 ${isAssistant ? 'justify-start' : 'justify-end'} group`}>
        {isAssistant && (
          <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-gradient-to-br from-blue-600 to-emerald-600 flex items-center justify-center text-white shadow-lg">
            <i className="fa-solid fa-robot text-xs"></i>
          </div>
        )}

        <div className={`max-w-[85%] md:max-w-[75%] flex flex-col ${isAssistant ? 'items-start' : 'items-end'}`}>
          <div
            className={`px-4 py-3 rounded-2xl text-sm leading-relaxed ${isAssistant
              ? 'bg-zinc-900 border border-zinc-800 text-zinc-200 shadow-sm'
              : 'bg-blue-600 text-white font-medium shadow-lg'
              }`}
          >
            {message.content ? (
              <div className="relative markdown-render">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    h1: ({ node, ...props }) => <h1 className="text-xl font-bold mb-3 mt-4 text-white" {...props} />,
                    h2: ({ node, ...props }) => <h2 className="text-lg font-bold mb-2 mt-4 text-white" {...props} />,
                    h3: ({ node, ...props }) => <h3 className="text-white font-bold mb-2 mt-3" {...props} />,
                    p: ({ node, ...props }) => <p className="mb-3 last:mb-0 leading-relaxed" {...props} />,
                    ul: ({ node, ...props }) => <ul className="list-disc pl-5 mb-4 space-y-1.5" {...props} />,
                    ol: ({ node, ...props }) => <ol className="list-decimal pl-5 mb-4 space-y-1.5" {...props} />,
                    li: ({ node, ...props }) => <li className="leading-relaxed" {...props} />,
                    a: ({ node, ...props }) => <a className="text-blue-400 hover:text-blue-300 underline decoration-blue-500/30 underline-offset-2 transition-colors" target="_blank" rel="noopener noreferrer" {...props} />,
                    strong: ({ node, ...props }) => <strong className="font-semibold text-white" {...props} />,
                    code: ({ node, className, children, ...props }: any) => {
                      const match = /language-(\w+)/.exec(className || '');
                      const isInline = !match && !props.inline && !String(children).includes('\\n');
                      return !isInline && match ? (
                        <div className="bg-[#09090b] rounded-lg p-3 my-3 overflow-x-auto border border-zinc-800/80 shadow-inner">
                          <code className={className} {...props}>
                            {children}
                          </code>
                        </div>
                      ) : (
                        <code className="bg-zinc-800/70 text-blue-300 px-1.5 py-0.5 rounded-md text-[0.85em] font-mono border border-zinc-700/50" {...props}>
                          {children}
                        </code>
                      )
                    },
                    table: ({ node, ...props }) => <div className="overflow-x-auto my-4 rounded-lg border border-zinc-800/80 shadow-sm"><table className="w-full text-left border-collapse text-sm" {...props} /></div>,
                    thead: ({ node, ...props }) => <thead className="bg-[#09090b]/80 border-b border-zinc-800" {...props} />,
                    th: ({ node, ...props }) => <th className="p-2.5 font-semibold text-zinc-300 border-r border-zinc-800/50 last:border-r-0" {...props} />,
                    td: ({ node, ...props }) => <td className="p-2.5 border-t border-r border-zinc-800/50 last:border-r-0 align-top" {...props} />,
                    blockquote: ({ node, ...props }) => <blockquote className="border-l-4 border-blue-500/50 pl-4 py-1 italic text-zinc-400 mb-4 bg-zinc-800/20 rounded-r-lg" {...props} />
                  }}
                >
                  {message.content}
                </ReactMarkdown>
              </div>
            ) : null}

            {message.isStreaming && (!message.content || message.content.length < 2) && (
              <div className="flex gap-1 py-1 h-5 items-center">
                <div className="w-1.5 h-1.5 bg-zinc-400 rounded-full animate-bounce"></div>
                <div className="w-1.5 h-1.5 bg-zinc-400 rounded-full animate-bounce delay-75"></div>
                <div className="w-1.5 h-1.5 bg-zinc-400 rounded-full animate-bounce delay-150"></div>
              </div>
            )}

            {message.attachments && message.attachments.length > 0 && (
              <div className="mt-3 space-y-2">
                {message.attachments.map((url, idx) => (
                  <img key={idx} src={url} alt="Attachment" className="max-w-xs rounded-lg border border-zinc-700 shadow-xl" />
                ))}
              </div>
            )}
          </div>

          <div className="flex items-center gap-3 mt-1.5 px-2">
            <div className="text-[10px] text-zinc-600">
              {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </div>

            {isAssistant && !message.isStreaming && (
              <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                <button
                  onClick={handleLike}
                  className={`p-1 rounded hover:bg-zinc-800 transition-colors ${feedbackStatus === 'liked' ? 'text-green-500' : 'text-zinc-500 hover:text-green-400'}`}
                  title="Utile"
                >
                  <i className={`fa-${feedbackStatus === 'liked' ? 'solid' : 'regular'} fa-thumbs-up text-xs`}></i>
                </button>
                <button
                  onClick={handleDislike}
                  className={`p-1 rounded hover:bg-zinc-800 transition-colors ${feedbackStatus === 'disliked' ? 'text-red-500' : 'text-zinc-500 hover:text-red-400'}`}
                  title="Pas utile"
                >
                  <i className={`fa-${feedbackStatus === 'disliked' ? 'solid' : 'regular'} fa-thumbs-down text-xs`}></i>
                </button>
              </div>
            )}
          </div>

          {isAssistant && message.sourceNodes && message.sourceNodes.length > 0 ? (
            <div className="mt-4 w-full animate-in fade-in slide-in-from-top-1 duration-500">
              <details className="group/accordion bg-zinc-900/40 border border-zinc-800/80 rounded-xl overflow-hidden shadow-sm">
                <summary className="px-4 py-2.5 flex items-center gap-2 cursor-pointer select-none text-xs font-medium text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50 transition-colors list-none [&::-webkit-details-marker]:hidden">
                  <i className="fa-solid fa-layer-group group-open/accordion:text-blue-400 transition-colors"></i>
                  <span>Sources utilisées ({message.sourceNodes.length})</span>
                  <i className="fa-solid fa-chevron-down ml-auto transition-transform group-open/accordion:rotate-180"></i>
                </summary>
                <div className="border-t border-zinc-800/80 bg-zinc-950/50 p-3 flex flex-col gap-3 max-h-[300px] overflow-y-auto custom-scrollbar">
                  {message.sourceNodes.map((node, idx) => {
                    let href = node.url;
                    if (/^[A-Za-z]:[\\/]/.test(node.url)) {
                      href = `/api/file?path=${encodeURIComponent(node.url)}`;
                    }
                    const displayName = node.url.split(/[/\\]/).pop();
                    const isWeb = node.url === "Recherche Web (DuckDuckGo)";

                    return (
                      <div key={idx} className="flex flex-col gap-1.5 p-3 rounded-lg bg-zinc-900 border border-zinc-800/50 hover:border-zinc-700 transition-colors">
                        <div className="flex items-center gap-2 text-xs">
                          {isWeb ? (
                            <i className="fa-solid fa-globe text-emerald-400"></i>
                          ) : (
                            <i className="fa-solid fa-file-pdf text-red-400"></i>
                          )}
                          <a href={href} target="_blank" rel="noopener noreferrer" className="font-semibold text-zinc-300 hover:text-blue-400 transition-colors truncate" title={node.url}>
                            {displayName}
                          </a>
                        </div>
                        <div className="text-[11px] text-zinc-500 leading-relaxed pl-5 border-l-2 border-zinc-800 ml-1 whitespace-pre-wrap">
                          {node.snippet.length > 400 ? node.snippet.substring(0, 400) + '...' : node.snippet}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </details>
            </div>
          ) : isAssistant && message.groundingUrls && message.groundingUrls.length > 0 ? (
            <div className="mt-2 flex flex-wrap gap-2 animate-in fade-in slide-in-from-top-1 duration-500">
              {message.groundingUrls.map((url, idx) => {
                let href = url;
                if (/^[A-Za-z]:[\\/]/.test(url)) {
                  href = `/api/file?path=${encodeURIComponent(url)}`;
                }
                const displayName = url.split(/[/\\]/).pop();

                return (
                  <a
                    key={idx}
                    href={href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[10px] flex items-center gap-1.5 px-2.5 py-1 bg-zinc-900 border border-zinc-800 rounded-full text-zinc-400 hover:text-blue-400 hover:border-blue-500/30 transition-all"
                    title={url}
                  >
                    <i className="fa-solid fa-file-alt text-[8px]"></i>
                    <span className="truncate max-w-[150px]">{displayName}</span>
                  </a>
                );
              })}
            </div>
          ) : null}
        </div>

        {!isAssistant && (
          <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-zinc-800 flex items-center justify-center text-zinc-400">
            <i className="fa-solid fa-user text-xs"></i>
          </div>
        )}
      </div>

      <FeedbackModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onSubmit={handleSubmitDislike}
      />
    </>
  );
};
