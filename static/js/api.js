/**
 * FinFlow Corp API Client
 * 所有页面的通用 API 调用和状态管理
 */

const API_BASE = '';

// ====== 认证相关 ======

async function login(userId, password) {
    const res = await fetch(`${API_BASE}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, password: password }),
    });
    if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || '登录失败');
    }
    const data = await res.json();
    sessionStorage.setItem('user', JSON.stringify(data.user));
    return data.user;
}

async function register(formData) {
    const res = await fetch(`${API_BASE}/api/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData),
    });
    if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || '注册失败');
    }
    return await res.json();
}

async function logout() {
    await fetch(`${API_BASE}/api/auth/logout`, { method: 'POST' });
    sessionStorage.removeItem('user');
    window.location.href = '/login';
}

function getCurrentUser() {
    const u = sessionStorage.getItem('user');
    return u ? JSON.parse(u) : null;
}

async function checkAuth() {
    try {
        const res = await fetch(`${API_BASE}/api/auth/me`);
        if (!res.ok) return null;
        const data = await res.json();
        if (data.user) {
            sessionStorage.setItem('user', JSON.stringify(data.user));
        }
        return data.user;
    } catch (e) {
        return null;
    }
}

// ====== 对话相关 ======

async function sendChatMessage(message, sessionId, onChunk) {
    const res = await fetch(`${API_BASE}/api/chat/send`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, session_id: sessionId }),
    });
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let fullText = '';
    let newSessionId = sessionId;

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split('\n');

        for (const line of lines) {
            const trimmed = line.trim();
            if (trimmed.startsWith('data: ')) {
                try {
                    const data = JSON.parse(trimmed.slice(6));
                    if (data.chunk) {
                        fullText += data.chunk;
                        if (onChunk) onChunk(data.chunk, fullText);
                    }
                    if (data.session_id) {
                        newSessionId = data.session_id;
                    }
                    if (data.error) {
                        fullText = 'Error: ' + data.error;
                        if (onChunk) onChunk('', fullText);
                    }
                } catch (e) {
                    // 忽略空行和不完整的 JSON
                    if (trimmed.length > 7 && e.message !== 'Unexpected end of JSON input') {
                        console.warn('SSE parse error:', e.message, trimmed.slice(0, 100));
                    }
                }
            }
        }
    }
    return { text: fullText, sessionId: newSessionId };
}

async function getChatHistory(sessionId = null) {
    let url = `${API_BASE}/api/chat/history?limit=100`;
    if (sessionId) url += `&session_id=${sessionId}`;
    const res = await fetch(url);
    return await res.json();
}

async function getChatSessions() {
    const res = await fetch(`${API_BASE}/api/chat/sessions`);
    return await res.json();
}

async function saveChatContext(content, role, sessionId) {
    const res = await fetch(`${API_BASE}/api/chat/context`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content, role, session_id: sessionId }),
    });
    return await res.json();
}

// ====== 预算相关 ======

async function getAllBudgets() {
    const res = await fetch(`${API_BASE}/api/budget/all`);
    return await res.json();
}

async function getBudgetSummary() {
    const res = await fetch(`${API_BASE}/api/budget/summary`);
    return await res.json();
}

// ====== 进度查询相关 ======

async function getReimbursementList(params = {}) {
    const query = new URLSearchParams(params).toString();
    const res = await fetch(`${API_BASE}/api/progress/list?${query}`);
    return await res.json();
}

async function getReimbursementDetail(reimbursementNo) {
    const res = await fetch(`${API_BASE}/api/progress/detail/${reimbursementNo}`);
    return await res.json();
}

async function getProgressStats() {
    const res = await fetch(`${API_BASE}/api/progress/stats`);
    return await res.json();
}

async function checkPDFExists(reimbursementNo) {
    try {
        const res = await fetch(`${API_BASE}/api/progress/pdf/${reimbursementNo}`);
        if (!res.ok) return { exists: false };
        return await res.json();
    } catch (e) {
        console.warn('PDF check failed:', e);
        return { exists: false };
    }
}

// ====== 审批相关 ======

async function getPendingApprovals(params = {}) {
    const query = new URLSearchParams(params).toString();
    const res = await fetch(`${API_BASE}/api/approval/pending?${query}`);
    return await res.json();
}

async function doApprovalAction(reimbursementNo, action, comment = '') {
    const res = await fetch(`${API_BASE}/api/approval/action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reimbursement_no: reimbursementNo, action, comment }),
    });
    if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || '审批操作失败');
    }
    return await res.json();
}

async function getApprovalHistory(page = 1) {
    const res = await fetch(`${API_BASE}/api/approval/history?page=${page}`);
    return await res.json();
}

// ====== 文件上传 ======

async function uploadInvoice(file) {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch(`${API_BASE}/api/upload/invoice`, {
        method: 'POST',
        body: formData,
    });
    if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || '文件上传失败');
    }
    return await res.json();
}

async function uploadInvoices(files) {
    const formData = new FormData();
    for (const file of files) {
        formData.append('files', file);
    }
    const res = await fetch(`${API_BASE}/api/upload/invoices`, {
        method: 'POST',
        body: formData,
    });
    if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || '文件批量上传失败');
    }
    return await res.json();
}

async function recognizeInvoice(filePath) {
    const res = await fetch(`${API_BASE}/api/ocr/invoice`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_path: filePath }),
    });
    if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'OCR识别失败');
    }
    return await res.json();
}

async function recognizeInvoices(filePaths) {
    const res = await fetch(`${API_BASE}/api/ocr/invoices`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_paths: filePaths }),
    });
    if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || '批量OCR识别失败');
    }
    return await res.json();
}

// ====== 凭证上传 ======

async function recognizeVoucher(filePath) {
    const res = await fetch(`${API_BASE}/api/ocr/voucher`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_path: filePath }),
    });
    if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || '凭证识别失败');
    }
    return await res.json();
}

async function recognizeVouchers(filePaths) {
    const res = await fetch(`${API_BASE}/api/ocr/vouchers`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_paths: filePaths }),
    });
    if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || '批量凭证识别失败');
    }
    return await res.json();
}

// ====== 通用工具 ======

function formatMoney(amount) {
    return '¥ ' + Number(amount).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

const STATUS_MAP = {
    'draft': '草稿',
    'pending': '待审批',
    'reviewing': '审批中',
    'approved': '已通过',
    'rejected': '已驳回',
    'split': '已拆分',
};

function getStatusClass(status) {
    const map = {
        'draft': 'bg-gray-100 text-gray-700',
        'pending': 'bg-yellow-100 text-yellow-700',
        'reviewing': 'bg-blue-100 text-blue-700',
        'approved': 'bg-green-100 text-green-700',
        'rejected': 'bg-red-100 text-red-700',
        'split': 'bg-purple-100 text-purple-700',
    };
    return map[status] || 'bg-gray-100 text-gray-700';
}

function getStatusDot(status) {
    const map = {
        'draft': 'bg-gray-400',
        'pending': 'bg-yellow-500',
        'reviewing': 'bg-blue-500',
        'approved': 'bg-green-500',
        'rejected': 'bg-red-500',
        'split': 'bg-purple-500',
    };
    return map[status] || 'bg-gray-400';
}
