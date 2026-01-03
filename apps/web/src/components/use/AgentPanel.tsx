import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Send, Clock, Plus, Bot, User } from 'lucide-react';
import type { AgentMessage, AgentEvent, ToolCallState, PageVisit, AgentTraceStep } from '../../types';
import { useAgentStream } from '../../hooks/useAgentStream';
import { ToolCallCard } from './ToolCallCard';
import { ThinkingSection } from './ThinkingSection';
import { PagesVisitedBadges } from './PagesVisitedBadges';

interface AgentPanelProps {
  projectId: string;
  onNavigateToPage?: (pageId: string) => void;
  onOpenPointer?: (pointerId: string) => void;
}

export const AgentPanel: React.FC<AgentPanelProps> = ({
  projectId,
  onNavigateToPage,
  onOpenPointer,
}) => {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<AgentMessage[]>([
    {
      id: '0',
      role: 'agent',
      timestamp: new Date(),
      finalAnswer: "Hello! I'm ready to help you navigate the plans. What are you looking for today?",
      isComplete: true,
    }
  ]);
  const [showHistory, setShowHistory] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const { sendQuery, isStreaming, abort } = useAgentStream({ projectId });

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  // Process incoming events and update message state
  const handleEvent = useCallback((event: AgentEvent, messageId: string) => {
    setMessages(prev => prev.map(msg => {
      if (msg.id !== messageId) return msg;

      switch (event.type) {
        case 'text': {
          // Add reasoning step to live trace
          const newTraceStep: AgentTraceStep = {
            type: 'reasoning',
            content: event.content,
          };
          const newTrace = [...(msg.trace || []), newTraceStep];

          // Accumulate text - we'll determine final answer at 'done'
          const newReasoning = [...(msg.reasoning || []), event.content];

          return {
            ...msg,
            reasoning: newReasoning,
            trace: newTrace,
          };
        }

        case 'tool_call': {
          // Add tool call step to live trace
          const newTraceStep: AgentTraceStep = {
            type: 'tool_call',
            tool: event.tool,
            input: event.input,
          };
          const newTrace = [...(msg.trace || []), newTraceStep];

          // Add new tool call in pending state
          const newToolCall: ToolCallState = {
            tool: event.tool,
            input: event.input,
            status: 'pending',
          };
          return {
            ...msg,
            toolCalls: [...(msg.toolCalls || []), newToolCall],
            trace: newTrace,
          };
        }

        case 'tool_result': {
          // Add tool result step to live trace
          const newTraceStep: AgentTraceStep = {
            type: 'tool_result',
            tool: event.tool,
            result: event.result,
          };
          const newTrace = [...(msg.trace || []), newTraceStep];

          // Find the matching pending tool call and mark complete
          const toolCalls = msg.toolCalls || [];
          const updatedToolCalls = toolCalls.map(tc => {
            if (tc.tool === event.tool && tc.status === 'pending') {
              return { ...tc, status: 'complete' as const, result: event.result };
            }
            return tc;
          });

          // Extract page visits from certain tool results
          let pagesVisited = msg.pagesVisited || [];
          if (event.result) {
            // Check for page context results
            if (event.result.pageId && event.result.pageName) {
              const visit: PageVisit = {
                pageId: event.result.pageId as string,
                pageName: event.result.pageName as string,
              };
              pagesVisited = [...pagesVisited, visit];
            }
            // Check for pointer results that have page info
            if (event.result.page_id && event.result.page_name) {
              const visit: PageVisit = {
                pageId: event.result.page_id as string,
                pageName: event.result.page_name as string,
              };
              pagesVisited = [...pagesVisited, visit];
            }
          }

          return {
            ...msg,
            toolCalls: updatedToolCalls,
            pagesVisited,
            trace: newTrace,
          };
        }

        case 'done': {
          // Mark message as complete
          // Extract final answer from trace - it's the last reasoning content after all tool calls
          const trace = msg.trace || [];
          let finalAnswer = '';

          // Find the last reasoning step(s) after the last tool_result
          let lastToolResultIndex = -1;
          for (let i = trace.length - 1; i >= 0; i--) {
            if (trace[i].type === 'tool_result') {
              lastToolResultIndex = i;
              break;
            }
          }

          // Collect all reasoning after the last tool result as the final answer
          const answerParts: string[] = [];
          for (let i = lastToolResultIndex + 1; i < trace.length; i++) {
            if (trace[i].type === 'reasoning' && trace[i].content) {
              answerParts.push(trace[i].content!);
            }
          }
          finalAnswer = answerParts.join('');

          // If no tools were called, the entire reasoning is the answer
          if (lastToolResultIndex === -1) {
            finalAnswer = (msg.reasoning || []).join('');
          }

          return {
            ...msg,
            isComplete: true,
            finalAnswer: finalAnswer || (msg.reasoning || []).join(''),
          };
        }

        case 'error': {
          // Show error in final answer
          return {
            ...msg,
            isComplete: true,
            finalAnswer: `Error: ${event.message}`,
          };
        }

        default:
          return msg;
      }
    }));
  }, []);

  const handleSend = async () => {
    if (!input.trim() || isStreaming) return;

    const userMessage: AgentMessage = {
      id: Date.now().toString(),
      role: 'user',
      text: input,
      timestamp: new Date(),
      isComplete: true,
    };

    const agentMessageId = (Date.now() + 1).toString();
    const agentMessage: AgentMessage = {
      id: agentMessageId,
      role: 'agent',
      timestamp: new Date(),
      reasoning: [],
      toolCalls: [],
      pagesVisited: [],
      trace: [],
      isComplete: false,
    };

    setMessages(prev => [...prev, userMessage, agentMessage]);
    setInput('');

    // Focus input for next query
    inputRef.current?.focus();

    // Send query and process events
    await sendQuery(input, (event) => handleEvent(event, agentMessageId));
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleNewChat = () => {
    abort();
    setMessages([{
      id: Date.now().toString(),
      role: 'agent',
      timestamp: new Date(),
      finalAnswer: "Hello! I'm ready to help you navigate the plans. What are you looking for today?",
      isComplete: true,
    }]);
  };

  return (
    <div className="flex flex-col h-full bg-white/90 backdrop-blur-xl border-l border-slate-200/50 shadow-elevation-3 relative">
      {/* Header */}
      <div className="h-16 border-b border-slate-200/50 flex items-center justify-between px-4 bg-gradient-to-r from-white to-slate-50 z-10">
        <div className="flex gap-2">
          <button
            onClick={handleNewChat}
            className="flex items-center gap-2 text-sm font-medium text-slate-600 hover:text-cyan-600 px-4 py-2 rounded-xl hover:bg-cyan-50 border border-slate-200/50 hover:border-cyan-200 transition-all duration-200"
          >
            <Plus size={16} /> New Chat
          </button>
        </div>
        <button
          onClick={() => setShowHistory(!showHistory)}
          className={`p-2.5 rounded-xl transition-all duration-200 ${
            showHistory
              ? 'bg-cyan-50 text-cyan-600 shadow-glow-cyan-sm'
              : 'text-slate-400 hover:text-slate-600 hover:bg-slate-100'
          }`}
        >
          <Clock size={18} />
        </button>
      </div>

      {/* History Sidebar Overlay */}
      <div className={`absolute top-16 right-0 w-72 h-[calc(100%-4rem)] bg-white/95 backdrop-blur-xl border-l border-slate-200/50 transform transition-all duration-300 ease-out z-20 shadow-elevation-2 ${
        showHistory ? 'translate-x-0 opacity-100' : 'translate-x-full opacity-0'
      }`}>
        <div className="p-4">
          <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-4 flex items-center gap-2">
            <Clock size={12} /> Recent Sessions
          </h3>
          <div className="text-center text-slate-400 py-8">
            <p className="text-sm">No recent sessions</p>
          </div>
        </div>
      </div>

      {/* Messages */}
      <div
        className="flex-1 overflow-y-auto p-4 space-y-5 bg-gradient-to-b from-slate-50/50 to-white no-scrollbar"
        ref={scrollRef}
      >
        {messages.map((msg, index) => (
          <div
            key={msg.id}
            className={`flex flex-col animate-slide-up ${msg.role === 'user' ? 'items-end' : 'items-start'}`}
            style={{ animationDelay: `${index * 50}ms` }}
          >
            {/* User message */}
            {msg.role === 'user' && (
              <div className="flex max-w-[90%] gap-3 flex-row-reverse">
                <div className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0 shadow-sm bg-slate-100 text-slate-600">
                  <User size={18} />
                </div>
                <div className="p-4 rounded-2xl text-sm leading-relaxed shadow-elevation-1 bg-gradient-to-br from-cyan-500 to-cyan-600 text-white rounded-tr-sm">
                  {msg.text}
                </div>
              </div>
            )}

            {/* Agent message */}
            {msg.role === 'agent' && (
              <div className="flex max-w-[90%] gap-3 flex-row">
                <div className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0 shadow-sm bg-gradient-to-br from-cyan-500 to-blue-500 text-white shadow-glow-cyan-sm">
                  <Bot size={18} />
                </div>
                <div className="flex-1 space-y-3 min-w-0 overflow-hidden">
                  {/* Thinking section (shows trace steps live during streaming) */}
                  {((msg.trace && msg.trace.length > 0) || !msg.isComplete) && (
                    <ThinkingSection
                      reasoning={[]}
                      isStreaming={!msg.isComplete}
                      autoCollapse={true}
                      trace={msg.trace || []}
                      onNavigateToPage={onNavigateToPage}
                      onOpenPointer={onOpenPointer}
                    />
                  )}

                  {/* Tool calls */}
                  {msg.toolCalls && msg.toolCalls.length > 0 && (
                    <div className="space-y-1.5">
                      {msg.toolCalls.map((tc, i) => (
                        <ToolCallCard key={`${tc.tool}-${i}`} toolCall={tc} />
                      ))}
                    </div>
                  )}

                  {/* Final answer */}
                  {msg.finalAnswer && (
                    <div className="p-4 rounded-2xl text-sm leading-relaxed shadow-elevation-1 bg-white text-slate-700 rounded-tl-sm border border-slate-100">
                      {msg.finalAnswer}
                    </div>
                  )}

                  {/* Streaming indicator when no content yet */}
                  {!msg.isComplete && !msg.finalAnswer && (!msg.reasoning || msg.reasoning.length === 0) && (!msg.toolCalls || msg.toolCalls.length === 0) && (
                    <div className="flex items-center gap-1.5 px-4 py-3 bg-white rounded-2xl border border-slate-100 shadow-sm">
                      <div className="w-2 h-2 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                      <div className="w-2 h-2 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                      <div className="w-2 h-2 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                    </div>
                  )}

                  {/* Pages visited */}
                  {msg.isComplete && msg.pagesVisited && msg.pagesVisited.length > 0 && (
                    <PagesVisitedBadges
                      pages={msg.pagesVisited}
                      onPageClick={onNavigateToPage}
                    />
                  )}
                </div>
              </div>
            )}

            {/* Timestamp */}
            <span className="text-[10px] text-slate-400 mt-1.5 mx-12">
              {msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
          </div>
        ))}
      </div>

      {/* Input */}
      <div className="p-4 bg-white border-t border-slate-200/50">
        <div className="relative">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyPress}
            placeholder={isStreaming ? 'Waiting for response...' : 'Ask about your plans...'}
            disabled={isStreaming}
            className="w-full pl-5 pr-14 py-4 bg-slate-50 border border-slate-200 rounded-2xl focus:outline-none focus:ring-2 focus:ring-cyan-500/30 focus:border-cyan-400 focus:bg-white text-slate-700 placeholder-slate-400 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || isStreaming}
            className="absolute right-2 top-2 p-2.5 bg-gradient-to-r from-cyan-500 to-cyan-600 text-white rounded-xl hover:from-cyan-400 hover:to-cyan-500 disabled:opacity-40 disabled:hover:from-cyan-500 disabled:hover:to-cyan-600 transition-all duration-200 shadow-glow-cyan-sm disabled:shadow-none"
          >
            <Send size={18} />
          </button>
        </div>
      </div>
    </div>
  );
};
