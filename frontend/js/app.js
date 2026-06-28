// App — 路由注册/初始化/Dashboard/历史记录

// Router setup
router.register('dashboard', () => loadDashboard());
router.register('jd-input', () => {});
router.register('history', () => loadHistory());

// Init
document.addEventListener('DOMContentLoaded', async () => {
    if (token && currentUser) {
        document.getElementById('userInfo').innerHTML = `
            <div>👤 ${currentUser.name || currentUser.username}</div>
            <button class="btn-secondary" style="margin-top:8px;width:100%;" onclick="logout()">退出</button>
        `;
        if (currentUser.role === 'ADMIN') {
            document.getElementById('adminMenuSection').style.display = 'block';
        }

        // 检测是否有进行中的面试，有则自动恢复
        try {
            const sessionsRes = await api.listSessions();
            if (sessionsRes.code === 200) {
                const inProgress = sessionsRes.data.filter(s => s.status === 'IN_PROGRESS');
                if (inProgress.length === 1) {
                    resumeInterview(inProgress[0].id);
                    return;
                }
            }
        } catch(e) {}

        // 没有进行中的面试 → 按角色进入默认页
        if (currentUser.role === 'ADMIN') {
            showPage('admin-dashboard');
        } else {
            showPage('dashboard');
        }
    }
});

// Dashboard
async function loadDashboard() {
    if (!token || !currentUser) return;
    try {
        const sessionsRes = await api.listSessions();
        if (sessionsRes.code === 200 && sessionsRes.data.length > 0) {
            const sessions = sessionsRes.data;
            const last = sessions[0];
            const total = sessions.length;
            document.getElementById('recentScore').textContent = last.totalScore != null ? last.totalScore : '--';
            document.getElementById('totalCount').textContent = total;

            // 检查是否有进行中的面试
            const inProgress = sessions.filter(s => s.status === 'IN_PROGRESS');
            const completed = sessions.filter(s => s.status !== 'IN_PROGRESS');
            let historyHtml = '';

            // 进行中的按原样显示
            inProgress.forEach(s => {
                const displayNum = total - sessions.indexOf(s);
                historyHtml += `<div class="history-item active" onclick="resumeInterview(${s.id})" style="border-left:3px solid #faad14;display:flex;justify-content:space-between;align-items:center;">
                    <span>🔄 面试 #${displayNum} - 进行中</span>
                    <span onclick="event.stopPropagation();deleteSession(${s.id})" style="cursor:pointer;color:#999;font-size:12px;padding:4px;">✕</span>
                </div>`;
            });

            // 已完成/待开始的，取前5条
            completed.slice(0, 5).forEach(s => {
                const displayNum = total - sessions.indexOf(s);
                historyHtml += `<div class="history-item" onclick="viewSession(${s.id})" style="display:flex;justify-content:space-between;align-items:center;">
                    <span>📊 面试 #${displayNum} - ${s.totalScore || '待评分'}分</span>
                    <span onclick="event.stopPropagation();deleteSession(${s.id})" style="cursor:pointer;color:#999;font-size:12px;padding:4px;">✕</span>
                </div>`;
            });
            document.getElementById('historyList').innerHTML = historyHtml || '<div class="history-item" style="color:#ccc;">暂无记录</div>';
        }
    } catch(e) {}
}

// 删除会话
async function deleteSession(id) {
    if (!confirm('确定删除该面试记录？')) return;
    try {
        const res = await api.deleteSession(id);
        if (res.code === 200) {
            // 刷新侧边栏 + 当前页面
            loadDashboard();
            const currentPage = router.currentPage;
            if (currentPage === 'history') loadHistory();
        } else {
            alert('删除失败: ' + (res.message || '未知错误'));
        }
    } catch(e) {
        alert('删除失败');
    }
}

// History
async function loadHistory() {
    if (!token || !currentUser) return;
    try {
        const res = await api.listSessions();
        if (res.code === 200) {
            const sessions = res.data;
            const table = document.getElementById('historyTable');
            if (sessions.length === 0) {
                table.innerHTML = '<p style="color:#999;">暂无面试记录</p>';
            } else {
                const total = sessions.length;
                table.innerHTML = sessions.map((s, i) => {
                    const displayNum = total - i;
                    return `
                    <div style="padding:12px;border:1px solid #e8e8e8;border-radius:8px;margin-bottom:8px;display:flex;justify-content:space-between;align-items:center;">
                        <div style="cursor:pointer;flex:1;" onclick="${s.status === 'IN_PROGRESS' ? `resumeInterview(${s.id})` : `viewSession(${s.id})`}">
                            <div style="display:flex;justify-content:space-between;">
                                <span>${s.status === 'IN_PROGRESS' ? '🔄 ' : '📊 '}面试 #${displayNum}</span>
                                <span>${s.status === 'IN_PROGRESS' ? '进行中' : (s.totalScore != null ? s.totalScore + '分' : '待评分')}</span>
                            </div>
                            <div style="font-size:12px;color:#999;margin-top:4px;">${s.createdAt}</div>
                        </div>
                        <span onclick="event.stopPropagation();deleteSession(${s.id})" style="cursor:pointer;color:#ff4d4f;font-size:16px;padding:8px;" title="删除">✕</span>
                    </div>`;
                }).join('');
            }
        }
    } catch(e) {}
}

function viewSession(id) {
    // 先检查 session 状态，进行中的直接恢复
    api.getSession(id).then(res => {
        if (res.code === 200 && res.data.status === 'IN_PROGRESS') {
            resumeInterview(id);
        } else {
            showPage('report');
            loadReportFromBackend(id);
        }
    }).catch(() => {
        showPage('report');
        loadReportFromBackend(id);
    });
}
