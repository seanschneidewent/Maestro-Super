import { GoogleGenAI, GenerateContentResponse } from "@google/genai";

// Initialize Gemini Client
// In a real app, process.env.API_KEY would be used.
// For this demo, we handle the case where it might be missing gracefully.
const apiKey = process.env.API_KEY || 'dummy_key'; 
const ai = new GoogleGenAI({ apiKey });

export const GeminiService = {
  /**
   * Analyze a specific pointer region
   */
  async analyzePointer(imageDataBase64: string, contextText: string): Promise<string> {
    if (apiKey === 'dummy_key') {
      return new Promise(resolve => setTimeout(() => resolve(`(Mock Analysis) This region appears to show ${contextText || 'a structural detail'}. Key elements include reinforced concrete pilings and connection bolts.`), 1500));
    }

    try {
      const response: GenerateContentResponse = await ai.models.generateContent({
        model: 'gemini-2.5-flash-image',
        contents: {
          parts: [
            { inlineData: { mimeType: 'image/png', data: imageDataBase64 } },
            { text: `Analyze this construction detail. Context: ${contextText}. Provide a technical description suitable for a superintendent.` }
          ]
        }
      });
      return response.text || "No analysis generated.";
    } catch (error) {
      console.error("Gemini Analysis Error:", error);
      return "Error analyzing region. Please check API key.";
    }
  },

  /**
   * Agent Chat Functionality
   */
  async chatWithAgent(message: string, history: any[]): Promise<string> {
    if (apiKey === 'dummy_key') {
       return new Promise(resolve => setTimeout(() => resolve(`(Mock Agent) I found relevant details regarding "${message}" on sheets A-101 and E-201. The electrical runs seem to intersect with the dropped ceiling grid here.`), 1000));
    }

    try {
      // Basic chat implementation
      const chat = ai.chats.create({
        model: 'gemini-3-flash-preview',
        config: {
            systemInstruction: "You are a helpful construction superintendent assistant. You have access to project plans."
        }
      });
      
      const response: GenerateContentResponse = await chat.sendMessage({ message });
      return response.text || "I couldn't process that.";
    } catch (error) {
      console.error("Gemini Chat Error:", error);
      return "Sorry, I'm having trouble connecting to the AI service right now.";
    }
  }
};
