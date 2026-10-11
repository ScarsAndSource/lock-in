import { request, isDemoMode } from './client';
import { Thread, ThreadDetail, ChatMessage } from '../types';
import { INITIAL_THREADS, INITIAL_CHAT_MESSAGES } from '../store/mockData';

let localThreads = [...INITIAL_THREADS];
let localMessages: Record<string, ChatMessage[]> = {
  'thread-1': [...INITIAL_CHAT_MESSAGES],
};

export async function getChatThreads(): Promise<Thread[]> {
  if (isDemoMode()) return localThreads;
  try {
    return await request<Thread[]>('/chat/threads');
  } catch {
    return localThreads;
  }
}

export async function getThreadDetail(threadId: string): Promise<ThreadDetail> {
  if (isDemoMode()) {
    const thread = localThreads.find((t) => t.id === threadId) || localThreads[0];
    return {
      thread,
      messages: localMessages[threadId] || [],
      has_more: false,
      support: null,
    };
  }
  return request<ThreadDetail>(`/chat/threads/${threadId}`);
}

export async function sendMessage(message: string, threadId?: string): Promise<{
  thread: Thread;
  user_message: ChatMessage;
  reply: ChatMessage;
  support?: any;
}> {
  if (isDemoMode()) {
    let t = localThreads.find((th) => th.id === threadId);
    if (!t) {
      t = {
        id: `thread-${Date.now()}`,
        title: message.substring(0, 30),
        created_at: new Date().toISOString(),
        last_message_at: new Date().toISOString(),
        message_count: 2,
      };
      localThreads.unshift(t);
      localMessages[t.id] = [];
    }

    const userMsg: ChatMessage = {
      id: `msg-${Date.now()}-u`,
      role: 'user',
      content: message,
      cited_days: [],
      narrated: false,
      created_at: new Date().toISOString(),
    };

    // Tone Ceiling: Direct accountability grounded in data
    const botReply: ChatMessage = {
      id: `msg-${Date.now()}-a`,
      role: 'assistant',
      content: `Your logged logs show you averaged 84.6% consistency this week. The clearest bottleneck is screen time exceeding 2 hours after 11:00 pm, which directly correlates with sluggish morning starts. Misses are just data: you can eliminate this trigger tonight.`,
      next_step: 'Set phone into charge mode outside bedroom before 11:00 pm.',
      mode: 'answer',
      cited_days: ['2026-12-30', '2026-12-31'],
      narrated: true,
      model: 'llama-3.3-70b-versatile',
      created_at: new Date().toISOString(),
    };

    localMessages[t.id].push(userMsg, botReply);
    t.last_message_at = botReply.created_at;
    t.message_count += 2;

    return {
      thread: t,
      user_message: userMsg,
      reply: botReply,
    };
  }

  return request('/chat/messages', {
    method: 'POST',
    body: JSON.stringify({ message, thread_id: threadId }),
  });
}
