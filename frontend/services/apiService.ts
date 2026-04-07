
import { ModelType } from "../types";

import { LocalSettings } from '../components/SettingsModal';

export class ApiService {
    private getAuthHeader(): Record<string, string> {
        const settingsRaw = localStorage.getItem('lumina-settings');
        if (settingsRaw) {
            try {
                const parsed = JSON.parse(settingsRaw);
                if (parsed.apiKey) {
                    return { 'Authorization': `Bearer ${parsed.apiKey}` };
                }
            } catch (e) {}
        }
        return {};
    }

    private async handleResponse(response: Response) {
        if (response.status === 401) {
            throw new Error("401_UNAUTHORIZED");
        }
        if (!response.ok) {
            throw new Error(`API Error: ${response.statusText}`);
        }
        return response;
    }

    async *streamChat(prompt: string, previousMessages: { role: string, content: string }[] = [], model: ModelType = ModelType.LLAMA_3B, useSearch: boolean = false, machineNumber?: string, sessionId?: string, settings?: LocalSettings) {
        try {
            const body: any = {
                message: prompt,
                history: previousMessages,
                model: model,
                use_search: useSearch,
                ...settings // Spread new LLM settings 
            };
            if (machineNumber) {
                body.machine_number = machineNumber;
            }
            if (sessionId) {
                body.session_id = sessionId;
            }

            const response = await fetch('/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...this.getAuthHeader()
                },
                body: JSON.stringify(body),
            });

            await this.handleResponse(response);

            // Extract sources from header
            const sourcesHeader = response.headers.get("X-Sources");
            const sources = sourcesHeader ? JSON.parse(sourcesHeader) : [];

            const reader = response.body?.getReader();
            const decoder = new TextDecoder();

            if (!reader) {
                throw new Error("No reader available");
            }

            let buffer = "";

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });

                // Parse complete SSE events separated by \n\n
                let boundary = buffer.indexOf('\n\n');
                while (boundary !== -1) {
                    const eventStr = buffer.substring(0, boundary).trim();
                    buffer = buffer.substring(boundary + 2);
                    boundary = buffer.indexOf('\n\n');

                    if (eventStr.startsWith('data: ')) {
                        const jsonStr = eventStr.substring(6); // remove 'data: '
                        try {
                            const parsed = JSON.parse(jsonStr);
                            if (parsed.sources) {
                                yield {
                                    sourceNodes: parsed.sources
                                };
                            } else if (parsed.sessionId) {
                                yield {
                                    sessionId: parsed.sessionId
                                };
                            } else if (parsed.text) {
                                yield {
                                    text: parsed.text,
                                    groundingMetadata: {
                                        groundingChunks: sources.map((s: string) => ({ web: { uri: s } }))
                                    }
                                };
                            }
                        } catch (e) {
                            console.error("Failed to parse SSE event:", jsonStr, e);
                        }
                    }
                }
            }

        } catch (error) {
            console.error("API Service Error:", error);
            throw error;
        }
    }

    async checkModelStatus(): Promise<{ Ollama_Running: boolean, Llama_Installed: boolean, Models: string[] }> {
        try {
            const response = await fetch('/status', { headers: { ...this.getAuthHeader() } });
            if (response.ok) {
                return await response.json();
            }
            return { Ollama_Running: false, Llama_Installed: false, Models: [] };
        } catch {
            return { Ollama_Running: false, Llama_Installed: false, Models: [] };
        }
    }

    async getSessions(): Promise<any[]> {
        const response = await fetch('/api/sessions', { headers: { ...this.getAuthHeader() } });
        await this.handleResponse(response);
        const data = await response.json();
        return data.map((s: any) => ({ ...s, messages: s.messages || [] }));
    }

    async getSession(sessionId: string): Promise<any> {
        const response = await fetch(`/api/sessions/${sessionId}`, { headers: { ...this.getAuthHeader() } });
        await this.handleResponse(response);
        const session = await response.json();
        if (session.messages) {
            session.messages = session.messages.map((m: any) => ({
                ...m,
                timestamp: m.timestamp ? new Date(m.timestamp) : new Date()
            }));
        }
        return session;
    }

    async renameSession(sessionId: string, title: string): Promise<void> {
        const response = await fetch(`/api/sessions/${sessionId}/title`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json', ...this.getAuthHeader() },
            body: JSON.stringify({ title })
        });
        await this.handleResponse(response);
    }

    async deleteSession(sessionId: string): Promise<void> {
        const response = await fetch(`/api/sessions/${sessionId}`, { method: 'DELETE', headers: { ...this.getAuthHeader() } });
        await this.handleResponse(response);
    }

    async createSession(): Promise<{ id: string, title: string }> {
        const response = await fetch('/api/sessions', { method: 'POST', headers: { ...this.getAuthHeader() } });
        await this.handleResponse(response);
        return await response.json();
    }

    async getFeedbacks(): Promise<any[]> {
        const response = await fetch('/api/feedback', { headers: { ...this.getAuthHeader() } });
        await this.handleResponse(response);
        return await response.json();
    }

    async deleteFeedback(index: number): Promise<void> {
        const response = await fetch(`/api/feedback/${index}`, { method: 'DELETE', headers: { ...this.getAuthHeader() } });
        await this.handleResponse(response);
    }

    async addVerifiedKnowledge(question: string, answer: string, machineId?: string, feedbackIndex?: number): Promise<void> {
        const response = await fetch('/api/verified_knowledge', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...this.getAuthHeader() },
            body: JSON.stringify({ question, answer, machine_id: machineId, feedback_index: feedbackIndex })
        });
        await this.handleResponse(response);
    }

    async getVerifiedKnowledge(): Promise<any[]> {
        const response = await fetch('/api/verified_knowledge', { headers: { ...this.getAuthHeader() } });
        await this.handleResponse(response);
        return await response.json();
    }

    async deleteVerifiedKnowledge(id: string): Promise<void> {
        const response = await fetch(`/api/verified_knowledge/${id}`, { method: 'DELETE', headers: { ...this.getAuthHeader() } });
        await this.handleResponse(response);
    }

    async analyzeImage(prompt: string, base64Image: string, model: ModelType = ModelType.LLAMA_3B): Promise<string> {
        try {
            const response = await fetch('/analyze_image', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...this.getAuthHeader()
                },
                body: JSON.stringify({
                    message: prompt,
                    image_base64: base64Image
                }),
            });

            await this.handleResponse(response);

            const data = await response.json();
            return data.answer || "Aucune réponse reçue du modèle de vision.";
        } catch (error) {
            console.error("Vision API Error:", error);
            return "Erreur lors de l'analyse de l'image. Veuillez vérifier que le modèle LLaVA est bien installé dans Ollama.";
        }
    }
    async sendFeedback(messageId: string, reason: string, isValid: boolean) {
        try {
            const response = await fetch('/feedback', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...this.getAuthHeader() },
                body: JSON.stringify({ message_id: messageId, reason, is_valid: isValid })
            });
            await this.handleResponse(response);
        } catch (error) {
            console.error("Feedback Error:", error);
        }
    }

    async getDocuments(): Promise<any[]> {
        const response = await fetch('/api/documents', { headers: { ...this.getAuthHeader() } });
        await this.handleResponse(response);
        return await response.json();
    }

    async uploadDocument(path: string, file: File): Promise<any> {
        const formData = new FormData();
        // Le backend attend "file"
        formData.append('file', file);

        const response = await fetch(`/api/documents?path=${encodeURIComponent(path)}`, {
            method: 'POST',
            body: formData,
            headers: { ...this.getAuthHeader() }
        });

        await this.handleResponse(response);
        return await response.json();
    }

    async deleteDocument(filePath: string): Promise<void> {
        const response = await fetch(`/api/documents/${encodeURIComponent(filePath)}`, {
            method: 'DELETE',
            headers: { ...this.getAuthHeader() }
        });
        await this.handleResponse(response);
    }

    async startIngestion(targetDir: string = ""): Promise<any> {
        const response = await fetch('/api/documents/ingest', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...this.getAuthHeader() },
            body: JSON.stringify({ target_dir: targetDir })
        });
        await this.handleResponse(response);
        return await response.json();
    }

    async getIngestionStatus(): Promise<{ is_running: boolean, last_run: string | null, logs: string }> {
        const response = await fetch('/api/documents/ingest/status', { headers: { ...this.getAuthHeader() } });
        await this.handleResponse(response);
        return await response.json();
    }
}

export const api = new ApiService();
