import React, { useState, useRef, useEffect } from 'react';
import { Send, Clock, Plus, Bot, User, FileText } from 'lucide-react';
import { MOCK_HISTORY } from '../../constants';
import { ChatMessage } from '../../types';
import { GeminiService } from '../../services/geminiService';

interface AgentPanelProps {
  onLinkClick: (sheetName: string) => void;
}

export const AgentPanel: React.FC<AgentPanelProps> = ({ onLinkClick }) => {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([
    { id: '0', role: 'agent', text: 'Hello! I\'m ready to help you navigate the plans. What are you looking for today?', timestamp: new Date() }
  ]);
  const [isTyping, setIsTyping] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [showHistory, setShowHistory] = useState(false);

  useEffect(() => {
    if (scrollRef.current) {
        scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim()) return;

    const userMsg: ChatMessage = {
        id: Date.now().toString(),
        role: 'user',
        text: input,
        timestamp: new Date()
    };

    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setIsTyping(true);

    // Mock Gemini Response
    const responseText = await GeminiService.chatWithAgent(input, []);
    
    setIsTyping(false);
    const agentMsg: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'agent',
        text: responseText,
        timestamp: new Date(),
        referencedSheets: Math.random() > 0.5 ? [
            { fileId: 'f1', name: 'A-101', pointerCount: 3 },
            { fileId: 'f3', name: 'E-201', pointerCount: 1 }
        ] : []
    };
    setMessages(prev => [...prev, agentMsg]);
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
    }
  };

  return (
    <div className="flex flex-col h-full bg-white/90 backdrop-blur-xl border-l border-slate-200/50 shadow-elevation-3 relative">
      {/* Header */}
      <div className="h-16 border-b border-slate-200/50 flex items-center justify-between px-4 bg-gradient-to-r from-white to-slate-50 z-10">
        <div className="flex gap-2">
            <button
                onClick={() => setMessages([])}
                className="flex items-center gap-2 text-sm font-medium text-slate-600 hover:text-cyan-600 px-4 py-2 rounded-xl hover:bg-cyan-50 border border-slate-200/50 hover:border-cyan-200 transition-all duration-200">
                <Plus size={16} /> New Chat
            </button>
        </div>
        <button
            onClick={() => setShowHistory(!showHistory)}
            className={`p-2.5 rounded-xl transition-all duration-200 ${showHistory ? 'bg-cyan-50 text-cyan-600 shadow-glow-cyan-sm' : 'text-slate-400 hover:text-slate-600 hover:bg-slate-100'}`}>
            <Clock size={18} />
        </button>
      </div>

      {/* History Sidebar Overlay */}
      <div className={`absolute top-16 right-0 w-72 h-[calc(100%-4rem)] bg-white/95 backdrop-blur-xl border-l border-slate-200/50 transform transition-all duration-300 ease-out z-20 shadow-elevation-2 ${showHistory ? 'translate-x-0 opacity-100' : 'translate-x-full opacity-0'}`}>
        <div className="p-4">
            <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-4 flex items-center gap-2">
              <Clock size={12} /> Recent Sessions
            </h3>
            <div className="space-y-2">
                {MOCK_HISTORY.map(h => (
                    <div key={h.id} className="p-3.5 bg-slate-50 hover:bg-cyan-50 border border-slate-200/50 hover:border-cyan-200 rounded-xl cursor-pointer transition-all duration-200 group">
                        <p className="text-sm font-medium text-slate-700 group-hover:text-cyan-700 truncate">{h.title}</p>
                        <p className="text-xs text-slate-400 mt-1">{h.date.toLocaleDateString()}</p>
                    </div>
                ))}
            </div>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-5 bg-gradient-to-b from-slate-50/50 to-white no-scrollbar" ref={scrollRef}>
        {messages.map((msg, index) => (
            <div key={msg.id} className={`flex flex-col animate-slide-up ${msg.role === 'user' ? 'items-end' : 'items-start'}`} style={{ animationDelay: `${index * 50}ms` }}>
                <div className={`flex max-w-[90%] gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : 'flex-row'}`}>
                    <div className={`w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0 shadow-sm ${
                      msg.role === 'agent'
                        ? 'bg-gradient-to-br from-cyan-500 to-blue-500 text-white shadow-glow-cyan-sm'
                        : 'bg-slate-100 text-slate-600'
                    }`}>
                        {msg.role === 'agent' ? <Bot size={18} /> : <User size={18} />}
                    </div>
                    <div className={`p-4 rounded-2xl text-sm leading-relaxed shadow-elevation-1 ${
                        msg.role === 'user'
                        ? 'bg-gradient-to-br from-cyan-500 to-cyan-600 text-white rounded-tr-sm'
                        : 'bg-white text-slate-700 rounded-tl-sm border border-slate-100'
                    }`}>
                        {msg.text}
                    </div>
                </div>

                {/* Reference Chips */}
                {msg.referencedSheets && msg.referencedSheets.length > 0 && (
                    <div className="mt-3 ml-12 flex gap-2 flex-wrap">
                        {msg.referencedSheets.map((ref, idx) => (
                            <button
                                key={idx}
                                onClick={() => onLinkClick(ref.name)}
                                className="flex items-center gap-2 bg-white border border-cyan-200 hover:border-cyan-400 hover:bg-cyan-50 text-cyan-700 px-3.5 py-2 rounded-xl shadow-sm transition-all duration-200 text-xs font-medium group"
                            >
                                <FileText size={14} className="text-cyan-400 group-hover:text-cyan-500" />
                                {ref.name}
                                <span className="bg-cyan-100 text-cyan-600 px-2 py-0.5 rounded-full text-[10px] font-bold">{ref.pointerCount}</span>
                            </button>
                        ))}
                    </div>
                )}
                <span className="text-[10px] text-slate-400 mt-1.5 mx-12">{msg.timestamp.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</span>
            </div>
        ))}
        {isTyping && (
            <div className="flex items-center gap-3 ml-12">
                <div className="flex items-center gap-1.5 px-4 py-3 bg-white rounded-2xl border border-slate-100 shadow-sm">
                  <div className="w-2 h-2 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                  <div className="w-2 h-2 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                  <div className="w-2 h-2 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                </div>
            </div>
        )}
      </div>

      {/* Input */}
      <div className="p-4 bg-white border-t border-slate-200/50">
        <div className="relative">
            <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyPress}
                placeholder="Ask about your plans..."
                className="w-full pl-5 pr-14 py-4 bg-slate-50 border border-slate-200 rounded-2xl focus:outline-none focus:ring-2 focus:ring-cyan-500/30 focus:border-cyan-400 focus:bg-white text-slate-700 placeholder-slate-400 transition-all duration-200"
            />
            <button
                onClick={handleSend}
                disabled={!input.trim()}
                className="absolute right-2 top-2 p-2.5 bg-gradient-to-r from-cyan-500 to-cyan-600 text-white rounded-xl hover:from-cyan-400 hover:to-cyan-500 disabled:opacity-40 disabled:hover:from-cyan-500 disabled:hover:to-cyan-600 transition-all duration-200 shadow-glow-cyan-sm disabled:shadow-none">
                <Send size={18} />
            </button>
        </div>
      </div>
    </div>
  );
};