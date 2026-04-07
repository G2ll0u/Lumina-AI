
import { GoogleGenAI, GenerateContentResponse } from "@google/genai";
import { ModelType } from "../types";

export class GeminiService {
  private ai: GoogleGenAI;

  constructor() {
    this.ai = new GoogleGenAI({ apiKey: process.env.API_KEY || '' });
  }

  async generateText(prompt: string, model: ModelType = ModelType.FLASH) {
    try {
      const response = await this.ai.models.generateContent({
        model,
        contents: prompt,
      });
      return response.text;
    } catch (error) {
      console.error("Gemini Error:", error);
      throw error;
    }
  }

  async *streamChat(prompt: string, model: ModelType = ModelType.FLASH, useSearch: boolean = false) {
    const config: any = {
      temperature: 0.7,
    };

    if (useSearch) {
      config.tools = [{ googleSearch: {} }];
    }

    try {
      const result = await this.ai.models.generateContentStream({
        model,
        contents: prompt,
        config
      });

      for await (const chunk of result) {
        const c = chunk as GenerateContentResponse;
        yield {
          text: c.text || "",
          groundingMetadata: c.candidates?.[0]?.groundingMetadata
        };
      }
    } catch (error) {
      console.error("Gemini Stream Error:", error);
      throw error;
    }
  }

  async analyzeImage(prompt: string, base64Image: string, model: ModelType = ModelType.FLASH) {
    try {
      const imagePart = {
        inlineData: {
          mimeType: 'image/jpeg',
          data: base64Image.split(',')[1] || base64Image,
        },
      };
      
      const response = await this.ai.models.generateContent({
        model,
        contents: { parts: [imagePart, { text: prompt }] },
      });
      
      return response.text;
    } catch (error) {
      console.error("Gemini Image Analysis Error:", error);
      throw error;
    }
  }
}

export const gemini = new GeminiService();
