const API_BASE = window.API_BASE || 'http://localhost:8080/api/v1';

let token = localStorage.getItem('token');
let currentUser = JSON.parse(localStorage.getItem('user') || 'null');

const api = {
    setToken(t) {
        token = t;
        localStorage.setItem('token', t);
    },

    headers() {
        const h = { 'Content-Type': 'application/json' };
        if (token) h['Authorization'] = `Bearer ${token}`;
        return h;
    },

    // Auth (no token needed)
    async login(username, password) {
        const res = await fetch(`${API_BASE}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        return res.json();
    },

    async register(username, password, name, email) {
        const res = await fetch(`${API_BASE}/auth/register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password, name, email })
        });
        return res.json();
    },

    // JD
    async createJd(content) {
        const res = await fetch(`${API_BASE}/jds`, {
            method: 'POST', headers: this.headers(),
            body: JSON.stringify({ content })
        });
        return res.json();
    },

    async listJds() {
        const res = await fetch(`${API_BASE}/jds`, { headers: this.headers() });
        return res.json();
    },

    // Resume
    async uploadResume(file) {
        const formData = new FormData();
        formData.append('file', file);
        const res = await fetch(`${API_BASE}/resumes/upload`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}` },
            body: formData
        });
        return res.json();
    },

    async parseResume(file) {
        const formData = new FormData();
        formData.append('file', file);
        const res = await fetch(`${API_BASE}/resume/parse`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}` },
            body: formData
        });
        return res.json();
    },

    // Sessions
    async createSession(jdId, resumeId) {
        const res = await fetch(`${API_BASE}/sessions`, {
            method: 'POST', headers: this.headers(),
            body: JSON.stringify({ jdId: jdId, resumeId: resumeId })
        });
        return res.json();
    },

    async listSessions() {
        const res = await fetch(`${API_BASE}/sessions`, { headers: this.headers() });
        return res.json();
    },

    async getSession(id) {
        const res = await fetch(`${API_BASE}/sessions/${id}`, { headers: this.headers() });
        return res.json();
    },

    async deleteSession(id) {
        const res = await fetch(`${API_BASE}/sessions/${id}`, {
            method: 'DELETE', headers: this.headers()
        });
        return res.json();
    },

    async saveSessionQuestions(sessionId, questions) {
        const res = await fetch(`${API_BASE}/sessions/${sessionId}/questions`, {
            method: 'PUT', headers: this.headers(),
            body: JSON.stringify({ questions })
        });
        return res.json();
    },

    // Q&A
    async saveQa(sessionId, data) {
        const res = await fetch(`${API_BASE}/sessions/${sessionId}/qas`, {
            method: 'POST', headers: this.headers(),
            body: JSON.stringify(data)
        });
        return res.json();
    },

    async listQas(sessionId) {
        const res = await fetch(`${API_BASE}/sessions/${sessionId}/qas`, { headers: this.headers() });
        return res.json();
    },

    // Report
    async getReport(sessionId) {
        const res = await fetch(`${API_BASE}/reports/session/${sessionId}`, { headers: this.headers() });
        return res.json();
    },

    async saveReport(sessionId, overallScore, detailsJson, suggestions) {
        const res = await fetch(`${API_BASE}/reports`, {
            method: 'POST',
            headers: this.headers(),
            body: JSON.stringify({ sessionId, overallScore, detailsJson, suggestions })
        });
        return res.json();
    },

    // AI Interview Service (proxied through backend)
    async aiStartInterview(jdContent, resumeContent) {
        const res = await fetch(`${API_BASE}/interview/start`, {
            method: 'POST',
            headers: this.headers(),
            body: JSON.stringify({
                jd_content: jdContent,
                resume_content: resumeContent
            })
        });
        return res.json();
    },

    async aiSubmitAnswer(sessionId, answer) {
        const res = await fetch(`${API_BASE}/interview/answer`, {
            method: 'POST',
            headers: this.headers(),
            body: JSON.stringify({ session_id: sessionId, answer: answer })
        });
        return res.json();
    },

    async aiGetResult(sessionId) {
        const res = await fetch(`${API_BASE}/interview/result/${sessionId}`, { headers: this.headers() });
        return res.json();
    },

    // Session recovery
    async getSessionState(sessionId) {
        const res = await fetch(`${API_BASE}/interview/state/${sessionId}`, { headers: this.headers() });
        return res.json();
    },

    async restoreInterview(data) {
        const res = await fetch(`${API_BASE}/interview/restore`, {
            method: 'POST',
            headers: this.headers(),
            body: JSON.stringify(data)
        });
        return res.json();
    },

    // SSE Streaming — parse a fetch ReadableStream as Server-Sent Events
    async _parseSSEStream(res, onEvent) {
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let eventType = '';
        let data = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();

            for (const line of lines) {
                if (line.startsWith('event: ')) {
                    eventType = line.slice(7).trim();
                } else if (line.startsWith('data: ')) {
                    data = line.slice(6);
                } else if (line.trim() === '' && eventType) {
                    try {
                        onEvent({ event: eventType, data: JSON.parse(data) });
                    } catch (e) {
                        onEvent({ event: eventType, data: { raw: data } });
                    }
                    eventType = '';
                    data = '';
                }
            }
        }
        // Flush any remaining event
        if (eventType) {
            try {
                onEvent({ event: eventType, data: JSON.parse(data) });
            } catch (e) {
                onEvent({ event: eventType, data: { raw: data } });
            }
        }
    },

    // Stream interview start — yields progress events then complete
    async aiStartInterviewStream(jdContent, resumeContent, onEvent) {
        const res = await fetch(`${API_BASE}/interview/start/stream`, {
            method: 'POST',
            headers: this.headers(),
            body: JSON.stringify({ jd_content: jdContent, resume_content: resumeContent })
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        await this._parseSSEStream(res, onEvent);
    },

    // Stream answer submission — yields progress then scored/complete
    async aiSubmitAnswerStream(sessionId, answer, onEvent) {
        const res = await fetch(`${API_BASE}/interview/answer/stream`, {
            method: 'POST',
            headers: this.headers(),
            body: JSON.stringify({ session_id: sessionId, answer: answer })
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        await this._parseSSEStream(res, onEvent);
    },

    // Get current question for session recovery
    async getCurrentQuestion(sessionId) {
        const res = await fetch(`${API_BASE}/interview/current/${sessionId}`, { headers: this.headers() });
        return res.json();
    },

    // Admin
    async adminDashboard() {
        const res = await fetch(`${API_BASE}/admin/dashboard`, { headers: this.headers() });
        return res.json();
    },

    async adminListUsers(keyword, page = 0, size = 20) {
        const params = new URLSearchParams({ page, size });
        if (keyword) params.set('keyword', keyword);
        const res = await fetch(`${API_BASE}/admin/users?${params}`, { headers: this.headers() });
        return res.json();
    },

    async adminGetUser(id) {
        const res = await fetch(`${API_BASE}/admin/users/${id}`, { headers: this.headers() });
        return res.json();
    },

    async adminUpdateUser(id, data) {
        const res = await fetch(`${API_BASE}/admin/users/${id}`, {
            method: 'PUT', headers: this.headers(),
            body: JSON.stringify(data)
        });
        return res.json();
    },

    async adminDisableUser(id) {
        const res = await fetch(`${API_BASE}/admin/users/${id}`, {
            method: 'DELETE', headers: this.headers()
        });
        return res.json();
    },

    async adminListSessions(status, userId, page = 0, size = 20) {
        const params = new URLSearchParams({ page, size });
        if (status) params.set('status', status);
        if (userId) params.set('userId', userId);
        const res = await fetch(`${API_BASE}/admin/sessions?${params}`, { headers: this.headers() });
        return res.json();
    },

    async adminGetSession(id) {
        const res = await fetch(`${API_BASE}/admin/sessions/${id}`, { headers: this.headers() });
        return res.json();
    },

    async adminListConfigs() {
        const res = await fetch(`${API_BASE}/admin/configs`, { headers: this.headers() });
        return res.json();
    },

    async adminUpdateConfigs(configs) {
        const res = await fetch(`${API_BASE}/admin/configs`, {
            method: 'PUT', headers: this.headers(),
            body: JSON.stringify({ configs })
        });
        return res.json();
    },

    async adminCreateUser(data) {
        const res = await fetch(`${API_BASE}/admin/users`, {
            method: 'POST', headers: this.headers(),
            body: JSON.stringify(data)
        });
        return res.json();
    },

    async adminDeleteSession(id) {
        const res = await fetch(`${API_BASE}/admin/sessions/${id}`, {
            method: 'DELETE', headers: this.headers()
        });
        return res.json();
    },

    async adminUpdateSessionStatus(id, status) {
        const res = await fetch(`${API_BASE}/admin/sessions/${id}/status`, {
            method: 'PUT', headers: this.headers(),
            body: JSON.stringify({ status })
        });
        return res.json();
    },

    async adminAuditLogs(targetType, operatorId, page = 0, size = 20) {
        const params = new URLSearchParams({ page, size });
        if (targetType) params.set('targetType', targetType);
        if (operatorId) params.set('operatorId', operatorId);
        const res = await fetch(`${API_BASE}/admin/audit-logs?${params}`, { headers: this.headers() });
        return res.json();
    }
};
