import React, { useState, useEffect, useRef } from 'react';
import { useApp } from '../context/AppContext';
import { getChatThreads, getThreadDetail, sendMessage } from '../api/chat';
import { fetchSupport } from '../api/support';
import { SupportCard } from '../components/SupportCard';
import { Thread, ChatMessage, SupportPayload } from '../types';
import { errorMessage } from '../lib/format';

export const ChatView: React.FC = () => {
  const { showToast, profile } = useApp();
  const [threads, setThreads] = useState<Thread[]>([]);
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputText, setInputText] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [support, setSupport] = useState<SupportPayload | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    getChatThreads()
      .then((thList) => {
        setThreads(thList);
        if (thList.length > 0) {
          setActiveThreadId(thList[0].id);
        }
      })
      .catch((err: unknown) => showToast(errorMessage(err, 'Could not load your chats')));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (activeThreadId) {
      let cancelled = false;
      getThreadDetail(activeThreadId)
        .then((detail) => {
          if (cancelled) return;
          setMessages(detail.messages);
          setSupport(detail.support ?? null);
        })
        .catch((err: unknown) => {
          if (!cancelled) showToast(errorMessage(err, 'Could not load this chat'));
        });
      return () => {
        cancelled = true;
      };
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeThreadId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, support]);

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputText.trim() || isSending) return;

    const text = inputText.trim();
    setInputText('');
    setIsSending(true);

    try {
      const res = await sendMessage(text, activeThreadId || undefined);
      setMessages((prev) => [...prev, res.user_message, res.reply]);
      // The reply says "one of the lines below", so the resources must actually be on screen.
      let nextSupport = res.support ?? null;
      if (!nextSupport && res.reply.mode === 'support') {
        try {
          nextSupport = await fetchSupport(profile?.timezone);
        } catch {
          nextSupport = null;
        }
      }
      setSupport(nextSupport);
      if (!activeThreadId) {
        setActiveThreadId(res.thread.id);
        setThreads((prev) => [res.thread, ...prev]);
      }
    } catch (err: unknown) {
      showToast(errorMessage(err, 'Error communicating with assistant'));
    } finally {
      setIsSending(false);
    }
  };

  const startNewChat = () => {
    setActiveThreadId(null);
    setMessages([]);
    setSupport(null);
  };

  return (
    <div className="flex flex-col w-full h-[calc(100dvh-130px)] max-w-md mx-auto">
      {/* Voice & Tone Banner & Thread Selector */}
      <div className="p-3 bg-surface-container rounded-xl flex items-center justify-between mb-3 shrink-0">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-ink text-[18px]">psychology</span>
          {threads.length > 1 ? (
            <select
              value={activeThreadId || ''}
              onChange={(e) => setActiveThreadId(e.target.value)}
              className="bg-surface border border-line rounded px-2 py-0.5 text-[11px] font-caption text-ink"
            >
              {threads.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.title}
                </option>
              ))}
            </select>
          ) : (
            <span className="font-caption text-caption text-ink font-semibold">
              Data-Grounded Coaching (No Fluff)
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={startNewChat}
          className="font-caption text-caption px-2 py-0.5 rounded bg-surface hover:bg-surface-container-low text-ink font-medium"
        >
          + New Chat
        </button>
      </div>

      {/* Message history */}
      <div className="flex-1 overflow-y-auto space-y-3 pr-1 pb-2">
        {messages.length === 0 && (
          <div className="text-center py-10 space-y-2">
            <span className="material-symbols-outlined text-[32px] text-muted-text">chat</span>
            <p className="font-small text-small text-muted-text max-w-xs mx-auto">
              Ask about behavioral friction: e.g. "Why do I keep skipping gym on Thursdays?" or "How does screen time affect my sleep?"
            </p>
          </div>
        )}

        {messages.map((m) => (
          <div
            key={m.id}
            className={`flex flex-col ${m.role === 'user' ? 'items-end' : 'items-start'}`}
          >
            <div
              className={`max-w-[85%] rounded-2xl p-3.5 space-y-2 text-small leading-relaxed shadow-xs ${
                m.role === 'user'
                  ? 'bg-ink text-ground-chalk rounded-br-xs'
                  : 'bg-surface text-ink border border-line rounded-bl-xs'
              }`}
            >
              <p>{m.content}</p>

              {/* Next step recommendation on coach messages */}
              {m.next_step && (
                <div className="p-2.5 bg-surface-container-low rounded-lg border border-surface-container text-ink font-caption text-caption">
                  <span className="font-bold block uppercase tracking-wider text-[10px] text-muted-text mb-0.5">
                    Recommended Action
                  </span>
                  <span>{m.next_step}</span>
                </div>
              )}

              {m.cited_days && m.cited_days.length > 0 && (
                <div className="font-caption text-[11px] text-muted-text pt-1">
                  Citing data from: {m.cited_days.join(', ')}
                </div>
              )}
            </div>
            <span className="font-caption text-[10px] text-muted-text px-1 mt-1">
              {new Date(m.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
          </div>
        ))}
        {support && <SupportCard support={support} />}
        {isSending && (
          <div className="flex items-center gap-1.5 p-3 text-caption text-muted-text">
            <span className="w-1.5 h-1.5 rounded-full bg-ink animate-bounce" />
            <span className="w-1.5 h-1.5 rounded-full bg-ink animate-bounce [animation-delay:0.2s]" />
            <span className="w-1.5 h-1.5 rounded-full bg-ink animate-bounce [animation-delay:0.4s]" />
            <span className="ml-1">Querying logs & Groq...</span>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input bar */}
      <form onSubmit={handleSend} className="pt-2 shrink-0 flex items-center gap-2">
        <input
          type="text"
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          placeholder="Ask grounded in your data..."
          className="flex-1 h-12 bg-surface border border-line rounded-xl px-4 font-small text-ink focus:outline-none focus:ring-1 focus:ring-ink"
        />
        <button
          type="submit"
          disabled={!inputText.trim() || isSending}
          className="w-12 h-12 rounded-xl bg-ink text-ground-chalk flex items-center justify-center disabled:opacity-40 transition-opacity"
        >
          <span className="material-symbols-outlined text-[20px]">send</span>
        </button>
      </form>
    </div>
  );
};
