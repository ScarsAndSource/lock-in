import { request, isDemoMode } from './client';
import { Thread, ThreadDetail, ChatMessage, SupportPayload } from '../types';
import { INITIAL_THREADS, INITIAL_CHAT_MESSAGES } from '../store/mockData';

let localThreads = [...INITIAL_THREADS];
const localMessages: Record<string, ChatMessage[]> = {
  'thread-1': [...INITIAL_CHAT_MESSAGES],
};

export async function getChatThreads(): Promise<Thread[]> {
  if (isDemoMode()) return localThreads;
  return request<Thread[]>('/chat/threads');
}

export async function getThreadDetail(threadId: string): Promise<ThreadDetail> {
  if (isDemoMode()) {
    const thread = localThreads.find((t) => t.id === threadId);
    if (!thread) throw new Error('Thread not found');
    return {
      thread,
      messages: localMessages[threadId] || [],
      has_more: false,
      support: null,
    };
  }
  return request<ThreadDetail>(`/chat/threads/${threadId}`);
}

export async function sendMessage(
  message: string,
  threadId?: string
): Promise<{
  thread: Thread;
  user_message: ChatMessage;
  reply: ChatMessage;
  support?: SupportPayload | null;
}> {
  if (isDemoMode()) {
    let t = threadId ? localThreads.find((th) => th.id === threadId) : undefined;
    if (!t) {
      t = {
        id: `thread-${Date.now()}`,
        title: message.substring(0, 30),
        created_at: new Date().toISOString(),
        last_message_at: new Date().toISOString(),
        message_count: 0,
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

    const botReply: ChatMessage = {
      id: `msg-${Date.now()}-a`,
      role: 'assistant',
      content:
        'Your logs show late screen time lining up with weaker mornings. Treat the miss as a data point: the next step is a concrete cutoff, not a pep talk.',
      next_step: 'Park the phone charging outside the bedroom before 11:00 pm tonight.',
      mode: 'answer',
      cited_days: [],
      narrated: true,
      model: 'demo',
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
    body: JSON.stringify({ message, thread_id: threadId || null }),
  });
}
