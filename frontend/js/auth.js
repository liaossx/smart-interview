// Auth & User — 登录/注册/登出/文件选择

let isRegisterMode = false;
let selectedResumeFile = null;

function showLogin() {
    document.getElementById('loginModal').style.display = 'flex';
}

function closeLogin() {
    document.getElementById('loginModal').style.display = 'none';
}

function toggleLoginMode() {
    isRegisterMode = !isRegisterMode;
    document.getElementById('loginTitle').textContent = isRegisterMode ? '注册' : '登录';
    document.getElementById('loginExtra').style.display = isRegisterMode ? 'block' : 'none';
}

async function doLogin() {
    const username = document.getElementById('loginUsername').value;
    const password = document.getElementById('loginPassword').value;
    const errorEl = document.getElementById('loginError');
    errorEl.style.display = 'none';

    try {
        let res;
        if (isRegisterMode) {
            const name = document.getElementById('loginName').value;
            const email = document.getElementById('loginEmail').value;
            res = await api.register(username, password, name, email);
        } else {
            res = await api.login(username, password);
        }

        if (res.code === 200) {
            api.setToken(res.data.token);
            currentUser = res.data;
            localStorage.setItem('user', JSON.stringify(res.data));
            document.getElementById('loginModal').style.display = 'none';
            document.getElementById('userInfo').innerHTML = `
                <div>👤 ${res.data.name || res.data.username}</div>
                <button class="btn-secondary" style="margin-top:8px;width:100%;" onclick="logout()">退出</button>
            `;
            // Show admin menu if user is admin
            if (res.data.role === 'ADMIN') {
                document.getElementById('adminMenuSection').style.display = 'block';
                showPage('admin-dashboard');
            } else {
                loadDashboard();
            }
        } else {
            errorEl.textContent = res.message;
            errorEl.style.display = 'block';
        }
    } catch (e) {
        errorEl.textContent = '网络错误';
        errorEl.style.display = 'block';
    }
}

function logout() {
    token = null; currentUser = null;
    localStorage.removeItem('token'); localStorage.removeItem('user');
    document.getElementById('userInfo').innerHTML = `
        <div>未登录</div>
        <button class="btn-secondary" style="margin-top:8px;width:100%;" onclick="showLogin()">登录</button>
    `;
    document.getElementById('adminMenuSection').style.display = 'none';
    // 清空所有残存数据
    document.getElementById('historyList').innerHTML = '<div class="history-item" style="color:#ccc;">暂无记录</div>';
    document.getElementById('historyTable').innerHTML = '<p style="color:#999;">暂无面试记录</p>';
    document.getElementById('recentScore').textContent = '--';
    document.getElementById('totalCount').textContent = '--';
    document.getElementById('reportContent').innerHTML = '';
    document.getElementById('interviewMessages').innerHTML = '';
    currentInterview = { backendSessionId: null, sessionId: null, jdId: null, resumeId: null, questions: [], currentIdx: 0, answers: [] };
    showPage('dashboard');
}

// File
function onFileSelect(e) {
    const file = e.target.files[0];
    if (file) { selectedResumeFile = file; document.getElementById('fileName').textContent = file.name; }
}
