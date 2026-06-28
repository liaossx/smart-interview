// Admin page logic

/**
 * XSS 防护：转义用户可控数据，防止 innerHTML 注入
 */
function escapeHtml(str) {
    if (str == null) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

router.register('admin-dashboard', () => loadAdminDashboard());
router.register('admin-users', () => loadAdminUsers());
router.register('admin-sessions', () => loadAdminSessions());
router.register('admin-configs', () => loadAdminConfigs());
router.register('admin-stats', () => loadAdminStats());
router.register('admin-audit-logs', () => loadAdminAuditLogs());

// ===== Dashboard =====

async function loadAdminDashboard() {
    try {
        const res = await api.adminDashboard();
        if (res.code !== 200) return;

        const stats = res.data;
        document.getElementById('statTotalUsers').textContent = stats.totalUsers;
        document.getElementById('statTotalSessions').textContent = stats.totalSessions;
        document.getElementById('statAvgScore').textContent = (stats.avgScore || 0).toFixed(1);
        document.getElementById('statCompletionRate').textContent = (stats.completionRate || 0).toFixed(0) + '%';

        // Top users
        const topUsers = stats.topUsers || [];
        const tbody = document.getElementById('adminTopUsers');
        if (topUsers.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:#999;">暂无数据</td></tr>';
        } else {
            tbody.innerHTML = topUsers.map((u, i) => `
                <tr>
                    <td>${i + 1}</td>
                    <td>${escapeHtml(u.name || u.username)}</td>
                    <td>${u.sessionCount}</td>
                    <td>${(u.avgScore || 0).toFixed(1)}</td>
                </tr>
            `).join('');
        }
    } catch (e) {
        console.error('Dashboard load failed', e);
    }
}

// ===== User Management =====

let adminUserPage = 0;
let adminUserKeyword = '';

async function loadAdminUsers(page = 0) {
    adminUserPage = page;
    try {
        const res = await api.adminListUsers(adminUserKeyword, page);
        if (res.code !== 200) return;

        const data = res.data;
        const tbody = document.getElementById('adminUsersTableBody');
        if (!data.content || data.content.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:#999;">暂无用户</td></tr>';
        } else {
            tbody.innerHTML = data.content.map(u => `
                <tr>
                    <td>${u.id}</td>
                    <td>${escapeHtml(u.username)}</td>
                    <td>${escapeHtml(u.name || '-')}</td>
                    <td>${escapeHtml(u.email || '-')}</td>
                    <td><span style="color:${u.role === 'ADMIN' ? '#ff4d4f' : '#1a73e8'};">${escapeHtml(u.role)}</span></td>
                    <td><span style="color:${u.enabled ? '#52c41a' : '#ccc'};">${u.enabled ? '启用' : '禁用'}</span></td>
                    <td>
                        <button class="btn-small" onclick="viewUserDetail(${u.id})">详情</button>
                        <button class="btn-small" onclick="editUser(${u.id})">编辑</button>
                    </td>
                </tr>
            `).join('');
        }

        // Pagination
        const totalPages = data.totalPages || 0;
        document.getElementById('adminUsersPagination').innerHTML = `
            <button ${page === 0 ? 'disabled' : ''} onclick="loadAdminUsers(${page - 1})">上一页</button>
            <span>第 ${page + 1}/${totalPages} 页 (共 ${data.totalElements || 0} 条)</span>
            <button ${page >= totalPages - 1 ? 'disabled' : ''} onclick="loadAdminUsers(${page + 1})">下一页</button>
        `;
    } catch (e) {
        console.error('User list load failed', e);
    }
}

function searchUsers() {
    adminUserKeyword = document.getElementById('adminUserSearch').value;
    loadAdminUsers(0);
}

async function viewUserDetail(id) {
    try {
        const res = await api.adminGetUser(id);
        if (res.code !== 200) return;
        const u = res.data;
        document.getElementById('userDetailContent').innerHTML = `
            <p><strong>ID:</strong> ${u.id}</p>
            <p><strong>用户名:</strong> ${escapeHtml(u.username)}</p>
            <p><strong>姓名:</strong> ${escapeHtml(u.name || '-')}</p>
            <p><strong>邮箱:</strong> ${escapeHtml(u.email || '-')}</p>
            <p><strong>手机:</strong> ${escapeHtml(u.phone || '-')}</p>
            <p><strong>角色:</strong> ${escapeHtml(u.role)}</p>
            <p><strong>状态:</strong> ${u.enabled ? '启用' : '禁用'}</p>
            <p><strong>面试次数:</strong> ${u.sessionCount}</p>
            <p><strong>平均分:</strong> ${(u.avgScore || 0).toFixed(1)}</p>
            <p><strong>注册时间:</strong> ${escapeHtml(u.createdAt)}</p>
        `;
        document.getElementById('userDetailModal').style.display = 'flex';
    } catch (e) {
        console.error('User detail load failed', e);
    }
}

async function editUser(id) {
    try {
        const res = await api.adminGetUser(id);
        if (res.code !== 200) return;
        const u = res.data;
        document.getElementById('editUserId').value = u.id;
        document.getElementById('editUserName').value = u.name || '';
        document.getElementById('editUserEmail').value = u.email || '';
        document.getElementById('editUserPhone').value = u.phone || '';
        document.getElementById('editUserRole').value = u.role;
        document.getElementById('editUserEnabled').value = u.enabled ? 'true' : 'false';
        document.getElementById('editUserModal').style.display = 'flex';
    } catch (e) {
        console.error('Edit user load failed', e);
    }
}

async function saveUser() {
    const id = document.getElementById('editUserId').value;
    const data = {
        name: document.getElementById('editUserName').value,
        email: document.getElementById('editUserEmail').value,
        phone: document.getElementById('editUserPhone').value,
        role: document.getElementById('editUserRole').value,
        enabled: document.getElementById('editUserEnabled').value === 'true'
    };
    const password = document.getElementById('editUserPassword').value;
    if (password) data.password = password;
    try {
        const res = await api.adminUpdateUser(id, data);
        if (res.code === 200) {
            closeEditUserModal();
            document.getElementById('editUserPassword').value = '';
            loadAdminUsers(adminUserPage);
        } else {
            alert('更新失败: ' + res.message);
        }
    } catch (e) {
        alert('网络错误');
    }
}

function closeEditUserModal() {
    document.getElementById('editUserModal').style.display = 'none';
}

function closeUserDetailModal() {
    document.getElementById('userDetailModal').style.display = 'none';
}

// ===== Create User =====

function openCreateUserModal() {
    document.getElementById('createUsername').value = '';
    document.getElementById('createPassword').value = '';
    document.getElementById('createName').value = '';
    document.getElementById('createEmail').value = '';
    document.getElementById('createPhone').value = '';
    document.getElementById('createRole').value = 'USER';
    document.getElementById('createUserModal').style.display = 'flex';
}

function closeCreateUserModal() {
    document.getElementById('createUserModal').style.display = 'none';
}

async function createUser() {
    const username = document.getElementById('createUsername').value.trim();
    const password = document.getElementById('createPassword').value;
    if (!username || !password) { alert('用户名和密码为必填项'); return; }
    const data = {
        username,
        password,
        name: document.getElementById('createName').value || undefined,
        email: document.getElementById('createEmail').value || undefined,
        phone: document.getElementById('createPhone').value || undefined,
        role: document.getElementById('createRole').value
    };
    try {
        const res = await api.adminCreateUser(data);
        if (res.code === 200) {
            closeCreateUserModal();
            loadAdminUsers(0);
        } else {
            alert('创建失败: ' + res.message);
        }
    } catch (e) {
        alert('网络错误');
    }
}

// ===== Session Management =====

let adminSessionPage = 0;

async function loadAdminSessions(page = 0) {
    adminSessionPage = page;
    try {
        const status = document.getElementById('adminSessionStatusFilter').value;
        const userId = document.getElementById('adminSessionUserFilter').value || null;
        const res = await api.adminListSessions(status || null, userId ? parseInt(userId) : null, page);
        if (res.code !== 200) return;

        const data = res.data;
        const tbody = document.getElementById('adminSessionsTableBody');
        if (!data.content || data.content.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#999;">暂无疑似记录</td></tr>';
        } else {
            tbody.innerHTML = data.content.map(s => `
                <tr>
                    <td>${s.id}</td>
                    <td>${s.userId}</td>
                    <td><span class="status-tag status-${s.status.toLowerCase()}">${s.status}</span></td>
                    <td>${s.totalScore != null ? s.totalScore : '-'}</td>
                    <td>${s.createdAt ? s.createdAt.substring(0, 10) : '-'}</td>
                    <td>
                        <button class="btn-small" onclick="viewSessionDetail(${s.id})">查看</button>
                        <button class="btn-small" style="color:#ff4d4f;" onclick="deleteAdminSession(${s.id})">删除</button>
                    </td>
                </tr>
            `).join('');
        }

        const totalPages = data.totalPages || 0;
        document.getElementById('adminSessionsPagination').innerHTML = `
            <button ${page === 0 ? 'disabled' : ''} onclick="loadAdminSessions(${page - 1})">上一页</button>
            <span>第 ${page + 1}/${totalPages} 页 (共 ${data.totalElements || 0} 条)</span>
            <button ${page >= totalPages - 1 ? 'disabled' : ''} onclick="loadAdminSessions(${page + 1})">下一页</button>
        `;
    } catch (e) {
        console.error('Session list load failed', e);
    }
}

function filterSessions() {
    loadAdminSessions(0);
}

async function viewSessionDetail(id) {
    try {
        const res = await api.adminGetSession(id);
        if (res.code !== 200) return;
        const data = res.data;
        const session = data.session;
        const qas = data.qas || [];
        const report = data.report;

        let html = `
            <p><strong>会话ID:</strong> ${session.id}</p>
            <p><strong>用户ID:</strong> ${session.userId}</p>
            <p><strong>状态:</strong> ${session.status}
               <select id="sessionStatusOverride" style="margin-left:8px;padding:4px 8px;border:1px solid #e0e0e0;border-radius:4px;font-size:12px;">
                   <option value="PENDING" ${session.status==='PENDING'?'selected':''}>PENDING</option>
                   <option value="IN_PROGRESS" ${session.status==='IN_PROGRESS'?'selected':''}>IN_PROGRESS</option>
                   <option value="COMPLETED" ${session.status==='COMPLETED'?'selected':''}>COMPLETED</option>
                   <option value="CANCELLED" ${session.status==='CANCELLED'?'selected':''}>CANCELLED</option>
               </select>
               <button class="btn-small" onclick="changeSessionStatus(${session.id})" style="margin-left:4px;">覆盖</button>
            </p>
            <p><strong>总分:</strong> ${session.totalScore != null ? session.totalScore : '未评分'}</p>
            <p><strong>时间:</strong> ${session.createdAt}</p>
            <hr style="margin:12px 0;">
        `;

        if (qas.length > 0) {
            html += '<h4 style="margin-bottom:8px;">问答记录</h4>';
            qas.forEach((qa, i) => {
                const calBadge = qa.calibrated ? '<span style="color:#52c41a;font-size:11px;">● 已校准</span>' : '';
                html += `
                    <div style="padding:8px;margin-bottom:8px;background:#f9f9f9;border-radius:6px;font-size:13px;">
                        <div><strong>Q${i+1}:</strong> ${escapeHtml(qa.question)} ${calBadge}</div>
                        <div style="color:#1a73e8;margin-top:4px;"><strong>A:</strong> ${escapeHtml(qa.answer || '未作答')}</div>
                        <div style="display:flex;align-items:center;gap:8px;margin-top:4px;">
                            <span>得分: <b id="qaScore_${qa.id}" style="color:${qa.calibrated ? '#52c41a' : '#faad14'};">${qa.score != null ? qa.score : '-'}</b>/10</span>
                            <span style="color:#999;font-size:12px;">${escapeHtml(qa.feedback || '')}</span>
                            <button class="btn-small" onclick="editQAScore(${qa.id}, ${qa.score || 0}, '${escapeHtml((qa.feedback || '').replace(/'/g, "\\'").replace(/\n/g, ' '))}')" style="margin-left:auto;" title="校准评分">✏️</button>
                        </div>
                    </div>
                `;
            });
        }

        if (report) {
            html += '<hr style="margin:12px 0;"><h4 style="margin-bottom:8px;">评估报告</h4>';
            html += `<p>综合评分: ${escapeHtml(report.overallScore || '-')}</p>`;
            if (report.suggestions) {
                html += `<p style="font-size:13px;color:#666;">${escapeHtml(report.suggestions)}</p>`;
            }
        }

        document.getElementById('sessionDetailContent').innerHTML = html;
        document.getElementById('sessionDetailModal').style.display = 'flex';
    } catch (e) {
        console.error('Session detail load failed', e);
    }
}

async function editQAScore(qaId, currentScore, currentFeedback) {
    const newScore = prompt(`QA #${qaId} 当前分数: ${currentScore}/10\n反馈: ${currentFeedback}\n\n请输入新分数 (0-10):`, currentScore);
    if (newScore === null) return;
    const score = parseInt(newScore);
    if (isNaN(score) || score < 0 || score > 10) { alert('请输入 0-10 的整数'); return; }
    const newFeedback = prompt('修改评语 (可选):', currentFeedback || '');
    try {
        const TOKEN = localStorage.getItem('token');
        const res = await fetch(`${API_BASE}/admin/qas/${qaId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + TOKEN },
            body: JSON.stringify({ score, feedback: newFeedback || undefined, calibrated: true })
        });
        if (res.ok) {
            const el = document.getElementById('qaScore_' + qaId);
            if (el) { el.textContent = score; el.style.color = '#52c41a'; }
        } else {
            alert('校准失败');
        }
    } catch (e) {
        alert('网络错误');
    }
}

function closeSessionDetailModal() {
    document.getElementById('sessionDetailModal').style.display = 'none';
}

async function deleteAdminSession(id) {
    if (!confirm(`确定删除会话 #${id}？相关问答和报告将一并删除。`)) return;
    try {
        const res = await api.adminDeleteSession(id);
        if (res.code === 200) {
            loadAdminSessions(adminSessionPage);
        } else {
            alert('删除失败: ' + res.message);
        }
    } catch (e) {
        alert('网络错误');
    }
}

async function changeSessionStatus(id) {
    const status = document.getElementById('sessionStatusOverride').value;
    try {
        const res = await api.adminUpdateSessionStatus(id, status);
        if (res.code === 200) {
            closeSessionDetailModal();
            loadAdminSessions(adminSessionPage);
        } else {
            alert('状态更新失败: ' + res.message);
        }
    } catch (e) {
        alert('网络错误');
    }
}

// ===== Config Management =====

async function loadAdminConfigs() {
    try {
        const res = await api.adminListConfigs();
        if (res.code !== 200) return;
        const configs = res.data;
        const form = document.getElementById('configForm');
        form.innerHTML = Object.entries(configs).map(([key, value]) => {
            const label = key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
            const isNumber = !isNaN(value) && value !== '';
            return `
            <div>
                <label style="display:block;font-size:13px;color:#666;margin-bottom:4px;">${escapeHtml(label)}</label>
                <div style="display:flex;gap:8px;align-items:center;">
                    <input id="cfg_${escapeHtml(key)}" type="${isNumber ? 'number' : 'text'}" value="${escapeHtml(value)}"
                           style="flex:1;padding:10px;border:1px solid #e0e0e0;border-radius:6px;font-size:14px;">
                    <input placeholder="配置键" value="${escapeHtml(key)}" readonly
                           style="width:180px;padding:10px;border:1px solid #e0e0e0;border-radius:6px;font-size:12px;color:#999;background:#f9f9f9;">
                </div>
            </div>`;
        }).join('');
    } catch (e) {
        console.error('Config load failed', e);
    }
}

function addConfigRow() {
    const form = document.getElementById('configForm');
    const row = document.createElement('div');
    const id = 'cfg_new_' + Date.now();
    row.innerHTML = `
        <label style="display:block;font-size:13px;color:#666;margin-bottom:4px;">New Config</label>
        <div style="display:flex;gap:8px;align-items:center;">
            <input id="${id}_key" placeholder="配置键" style="flex:1;padding:10px;border:1px solid #e0e0e0;border-radius:6px;font-size:14px;">
            <input id="${id}_val" placeholder="配置值" style="flex:1;padding:10px;border:1px solid #e0e0e0;border-radius:6px;font-size:14px;">
            <button onclick="this.closest('div').parentElement.remove()" style="border:none;background:none;color:#ff4d4f;cursor:pointer;font-size:16px;">✕</button>
        </div>`;
    row.id = id;
    form.appendChild(row);
}

async function saveConfigs() {
    const configs = {};
    // 已有配置项 (id="cfg_xxx")
    document.querySelectorAll('#configForm input[id^="cfg_"]').forEach(input => {
        const key = input.id.replace('cfg_', '');
        configs[key] = input.value;
    });
    // 新增配置项 (id="cfg_new_xxx_key" / "cfg_new_xxx_val")
    document.querySelectorAll('#configForm [id$="_key"]').forEach(keyInput => {
        const valInput = document.getElementById(keyInput.id.replace('_key', '_val'));
        if (keyInput.value.trim() && valInput) {
            configs[keyInput.value.trim()] = valInput.value;
        }
    });
    try {
        const res = await api.adminUpdateConfigs(configs);
        if (res.code === 200) {
            const msg = document.getElementById('configSaveMsg');
            msg.style.display = 'inline';
            setTimeout(() => { msg.style.display = 'none'; }, 2000);
        } else {
            alert('保存失败: ' + res.message);
        }
    } catch (e) {
        alert('网络错误');
    }
}

// ===== Stats Dashboard =====

async function loadAdminStats() {
    try {
        const [overviewRes, distRes, catRes, qualityRes] = await Promise.all([
            fetch(`${API_BASE}/stats/overview`, { headers: api.headers() }).then(r => r.json()),
            fetch(`${API_BASE}/stats/scores`, { headers: api.headers() }).then(r => r.json()),
            fetch(`${API_BASE}/stats/categories`, { headers: api.headers() }).then(r => r.json()),
            fetch(`${API_BASE}/stats/quality`, { headers: api.headers() }).then(r => r.json())
        ]);

        const overview = overviewRes.data || {};
        const dist = distRes.data || {};
        const cats = catRes.data || {};
        const quality = qualityRes.data || {};

        document.querySelector('#statTotalSessions div:first-child').textContent = overview.totalSessions || 0;
        document.querySelector('#statCompletedSessions div:first-child').textContent = overview.completedSessions || 0;
        document.querySelector('#statAvgTotalScore div:first-child').textContent = overview.avgTotalScore || '0';
        document.querySelector('#statTotalQAs div:first-child').textContent = cats.totalQAs || 0;

        // Quality metrics
        document.getElementById('metricStdDev').textContent = quality.scoreStdDeviation ?? '--';
        document.getElementById('metricCalibrationRate').textContent = quality.calibrationRate ?? '--';
        const drift = quality.scoreDrift ?? 0;
        document.getElementById('metricScoreDrift').textContent = (drift >= 0 ? '+' : '') + drift;
        document.getElementById('metricCalibratedCount').textContent = quality.calibratedQAs ?? '--';

        const distribution = dist.distribution || [];
        const maxCount = Math.max(1, ...distribution.map(d => d.count));
        document.getElementById('scoreDistroChart').innerHTML = distribution.map(d => `
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
                <div style="width:48px;font-size:12px;color:#666;">${d.range}</div>
                <div style="flex:1;height:22px;background:#f0f0f0;border-radius:4px;overflow:hidden;">
                    <div style="height:100%;width:${(d.count / maxCount * 100).toFixed(0)}%;background:linear-gradient(90deg,#1a73e8,#69b1ff);border-radius:4px;transition:width 0.4s;"></div>
                </div>
                <div style="width:50px;font-size:12px;color:#333;text-align:right;">${d.count}(${d.pct}%)</div>
            </div>
        `).join('');

        const categoryList = (cats.categories || []).filter(c => c.category !== '综合');
        const colors = ['#1a73e8','#52c41a','#faad14','#ff4d4f','#722ed1','#13c2c2'];
        document.getElementById('categoryChart').innerHTML = categoryList.map((c, i) => `
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
                <div style="width:60px;font-size:12px;color:#666;text-align:right;overflow:hidden;text-overflow:ellipsis;">${c.category}</div>
                <div style="flex:1;height:22px;background:#f0f0f0;border-radius:4px;overflow:hidden;">
                    <div style="height:100%;width:${Math.max(5, (c.avgScore / 10 * 100).toFixed(0))}%;background:${colors[i % colors.length]};border-radius:4px;transition:width 0.4s;display:flex;align-items:center;padding-left:6px;">
                        <span style="font-size:11px;color:#fff;font-weight:500;">${c.avgScore}</span>
                    </div>
                </div>
                <div style="font-size:11px;color:#999;width:36px;">${c.count}题</div>
            </div>
        `).join('');
    } catch (e) {
        console.error('Stats load failed', e);
    }
}

// ===== Audit Logs =====

let adminAuditLogPage = 0;

async function loadAdminAuditLogs(page = 0) {
    adminAuditLogPage = page;
    try {
        const targetType = document.getElementById('auditLogTypeFilter').value || null;
        const res = await api.adminAuditLogs(targetType, null, page);
        if (res.code !== 200) return;

        const data = res.data;
        const tbody = document.getElementById('adminAuditLogsTableBody');
        if (!data.content || data.content.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:#999;">暂无审计记录</td></tr>';
        } else {
            tbody.innerHTML = data.content.map(a => `
                <tr>
                    <td>${a.id}</td>
                    <td>${a.createdAt ? a.createdAt.replace('T', ' ').substring(0, 19) : '-'}</td>
                    <td><span style="color:${a.action==='CREATE'?'#52c41a':a.action==='DELETE'?'#ff4d4f':'#1a73e8'};">${escapeHtml(a.action)}</span></td>
                    <td>${escapeHtml(a.targetType)}</td>
                    <td>${a.targetId || '-'}</td>
                    <td>${a.operatorId || '-'}</td>
                    <td>${escapeHtml(a.description || '-')}</td>
                </tr>
            `).join('');
        }

        const totalPages = data.totalPages || 0;
        document.getElementById('adminAuditLogsPagination').innerHTML = `
            <button ${page === 0 ? 'disabled' : ''} onclick="loadAdminAuditLogs(${page - 1})">上一页</button>
            <span>第 ${page + 1}/${totalPages} 页 (共 ${data.totalElements || 0} 条)</span>
            <button ${page >= totalPages - 1 ? 'disabled' : ''} onclick="loadAdminAuditLogs(${page + 1})">下一页</button>
        `;
    } catch (e) {
        console.error('Audit logs load failed', e);
    }
}
