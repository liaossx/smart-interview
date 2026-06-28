// Interview — 面试核心流程/会话恢复/评分/报告渲染

let currentInterview = {
    backendSessionId: null,
    sessionId: null,
    jdId: null,
    resumeId: null,
    questions: [],
    currentIdx: 0,
    answers: []
};

// === 会话恢复 ===

async function resumeInterview(backendSessionId) {
    if (!token || !currentUser) { showLogin(); return; }

    showPage('interview');
    const msgArea = document.getElementById('interviewMessages');
    msgArea.innerHTML = '';
    document.getElementById('answerInput').value = '';
    addMessage('agent', '🔄 正在恢复面试会话...');

    try {
        // 1. 从后端获取会话状态
        const stateRes = await api.getSessionState(backendSessionId);
        if (stateRes.sessionId == null) {
            addMessage('agent', '❌ 无法恢复会话：会话不存在');
            return;
        }

        // 2. 请求 AI 服务恢复状态
        const restoreRes = await api.restoreInterview({
            jd_content: stateRes.jdContent || '',
            resume_content: stateRes.resumeContent || '',
            qas: stateRes.qas || [],
            questions: stateRes.questions || [],
            current_question_index: stateRes.currentQuestionIndex || 0,
            user_id: currentUser.id || 1,
            existing_session_id: null
        });

        if (!restoreRes.session_id) {
            // Fallback: try getCurrentQuestion endpoint for session recovery
            try {
                const cqRes = await api.getCurrentQuestion(stateRes.sessionId);
                if (cqRes && cqRes.session_id) {
                    currentInterview.backendSessionId = backendSessionId;
                    currentInterview.sessionId = cqRes.session_id;
                    currentInterview.questions = stateRes.questions || [];
                    currentInterview.currentIdx = stateRes.currentQuestionIndex || 0;
                    currentInterview.answers = [];

                    msgArea.innerHTML = '';
                    addMessage('agent', `🔄 **会话已恢复（快速模式）** — 已答 ${stateRes.qas?.length || 0}/${currentInterview.questions.length} 题`);

                    // Replay history
                    (stateRes.qas || []).forEach((qa, i) => {
                        addMessage('agent', `**第 ${i+1} 题:** ${qa.question}`);
                        addMessage('user', qa.answer || '（未作答）');
                        addMessage('agent', `✅ 评分: ${qa.score}/10 — ${qa.feedback || ''}`);
                    });

                    if (cqRes.question) {
                        addMessage('agent', `---\n\n**第 ${currentInterview.currentIdx + 1}/${currentInterview.questions.length} 题**\n\n${cqRes.question}`);
                        document.getElementById('answerInput').disabled = false;
                        document.getElementById('answerInput').focus();
                        return;
                    }
                }
            } catch (cqErr) {
                console.warn('getCurrentQuestion fallback also failed', cqErr);
            }
            addMessage('agent', '❌ AI 服务恢复失败，会话可能已过期');
            return;
        }

        currentInterview.backendSessionId = backendSessionId;
        currentInterview.sessionId = restoreRes.session_id;
        currentInterview.questions = restoreRes.questions || [];
        currentInterview.currentIdx = restoreRes.current_question_index || 0;
        currentInterview.answers = [];

        const answeredCount = restoreRes.answered_count || 0;
        if (restoreRes.phase === 'done') {
            addMessage('agent', '✅ 面试已完成，正在生成报告...');
            finishInterview();
            return;
        }

        // 清空 loading 消息
        msgArea.innerHTML = '';
        addMessage('agent', `🔄 **会话已恢复** — 已答 ${answeredCount}/${restoreRes.total_questions} 题，以下为历史记录\n\n---`);

        // 3. 回放已答对话记录
        const qas = stateRes.qas || [];
        qas.forEach((qa, i) => {
            const qNum = i + 1;
            addMessage('agent',
                `**[${qa.category || '综合'}] 第 ${qNum}/${restoreRes.total_questions} 题**\n\n` +
                `${qa.question}`
            );
            if (qa.followUpQuestion) {
                addMessage('agent', `💬 **追问：** ${qa.followUpQuestion}`);
            }
            addMessage('user', qa.answer || '（未作答）');
            const scoreColor = qa.score >= 6 ? '#52c41a' : (qa.score >= 4 ? '#faad14' : '#ff4d4f');
            addMessage('agent',
                `✅ **评分: ${qa.score}/10**\n\n` +
                `💡 ${qa.feedback || ''}`
            );
        });

        // 4. 显示下一题
        document.getElementById('progressText').textContent = `${answeredCount + 1}/${restoreRes.total_questions}`;
        document.getElementById('progressFill').style.width = `${((answeredCount + 1) / restoreRes.total_questions) * 100}%`;
        document.getElementById('currentScore').textContent = '--分';

        if (restoreRes.current_question) {
            const q = restoreRes.current_question;
            const category = q.category || '综合';
            const difficulty = q.difficulty || 'medium';
            const diffMap = { easy: '⭐', medium: '⭐⭐', hard: '⭐⭐⭐' };
            addMessage('agent',
                `---\n\n**[${category}]** ${diffMap[difficulty] || ''}\n\n` +
                `**第 ${answeredCount + 1}/${restoreRes.total_questions} 题**\n\n` +
                `${q.question}`
            );
            document.getElementById('answerInput').placeholder = '输入你的回答...';
            document.getElementById('answerInput').disabled = false;
            document.getElementById('answerInput').focus();
        }
    } catch (e) {
        addMessage('agent', '❌ 恢复失败: ' + e.message);
    }
}

// === 面试核心流程 ===

async function startInterview() {
    if (!token || !currentUser) { showLogin(); return; }

    const jdContent = document.getElementById('jdContent').value.trim();
    if (!jdContent) { alert('请粘贴 JD 内容'); return; }

    try {
        // 1. 保存 JD 到后端
        const jdRes = await api.createJd(jdContent);
        if (jdRes.code !== 200) { alert(jdRes.message); return; }
        currentInterview.jdId = jdRes.data.id;

        // 2. 上传简历（可选）
        let resumeContent = '';
        if (selectedResumeFile) {
            // 先上传到后端存储
            const resumeRes = await api.uploadResume(selectedResumeFile);
            if (resumeRes.code === 200) {
                currentInterview.resumeId = resumeRes.data.id;
            }
            // 再请求 AI 服务解析简历内容
            try {
                const parseRes = await api.parseResume(selectedResumeFile);
                if (parseRes.content) {
                    resumeContent = parseRes.content;
                }
            } catch(e) {
                console.warn('简历解析失败，将不包含简历内容', e);
            }
        }

        // 3. 创建 session (后端)
        const sessionRes = await api.createSession(currentInterview.jdId, currentInterview.resumeId);
        if (sessionRes.code !== 200) { alert(sessionRes.message); return; }
        currentInterview.backendSessionId = sessionRes.data.id;
        currentInterview.sessionId = null; // AI session ID will be set later

        // 4. 显示面试页面
        showPage('interview');
        const msgArea = document.getElementById('interviewMessages');
        msgArea.innerHTML = '';
        document.getElementById('answerInput').value = '';
        addMessage('agent', '🤔 AI 正在分析你的 JD 和简历，生成面试题目...');

        // 5. 调用 AI 服务开始面试（SSE 流式）
        let aiRes = null;
        await api.aiStartInterviewStream(jdContent, resumeContent, (evt) => {
            if (evt.event === 'jd_analysis') {
                addMessage('agent', '📄 JD 分析完成...');
            } else if (evt.event === 'resume_analysis_done') {
                addMessage('agent', '👤 简历分析完成...');
            } else if (evt.event === 'gap_analysis_done') {
                const gapCount = evt.data?.jd_only_skills?.length || 0;
                addMessage('agent', `🔍 技能差距分析完成${gapCount > 0 ? `（发现 ${gapCount} 个差距）` : ''}...`);
            } else if (evt.event === 'questions_ready') {
                addMessage('agent', '📝 面试题目已生成，准备开始...');
            } else if (evt.event === 'complete') {
                aiRes = evt.data;
            }
        });

        if (!aiRes || !aiRes.session_id) { addMessage('agent', '❌ 面试启动失败'); return; }

        // 6. 将 session 状态改为 IN_PROGRESS（以便刷新后恢复）
        try {
            await fetch(`${API_BASE}/sessions/${currentInterview.backendSessionId}/status`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
                body: JSON.stringify({ status: 'IN_PROGRESS' })
            });
        } catch(e) {
            console.warn('状态更新失败', e);
        }

        currentInterview.sessionId = aiRes.session_id;
        currentInterview.questions = aiRes.questions || [];
        currentInterview.currentIdx = 0;
        currentInterview.answers = [];

        // 7. 保存完整题目列表到后端（用于刷新后恢复）
        try {
            await api.saveSessionQuestions(currentInterview.backendSessionId, aiRes.questions || []);
        } catch(e) {
            console.warn('保存题目列表失败', e);
        }

        // 8. 显示分析结果和第一题
        const jdSummary = aiRes.jd_analysis?.summary || '';
        const gapCount = aiRes.gap_analysis?.jd_only_skills?.length || 0;

        let analysisMsg = `📋 **JD 分析完成**\n\n`;
        if (jdSummary) analysisMsg += `${jdSummary}\n\n`;
        if (gapCount > 0) analysisMsg += `📌 发现 **${gapCount}** 个你需要重点准备的技能差距\n\n`;
        analysisMsg += `共 **${aiRes.total_questions}** 道题，开始作答！`;
        addMessage('agent', analysisMsg);

        showQuestion(0);
    } catch (e) {
        addMessage('agent', '❌ 启动面试失败: ' + e.message);
    }
}

function addMessage(role, content) {
    const container = document.getElementById('interviewMessages');
    const msg = document.createElement('div');
    msg.className = `message ${role}`;
    const time = new Date().toLocaleTimeString();
    const bubble = document.createElement('div');
    bubble.className = 'bubble';
    bubble.textContent = content.replace(/\*\*/g, '');
    msg.appendChild(bubble);
    const timeEl = document.createElement('div');
    timeEl.className = 'time';
    timeEl.textContent = time;
    msg.appendChild(timeEl);
    container.appendChild(msg);
    container.scrollTop = container.scrollHeight;
}

function showQuestion(idx) {
    const questions = currentInterview.questions;
    if (idx >= questions.length) {
        addMessage('agent', '🎉 所有题目已答完！正在生成评估报告...');
        finishInterview();
        return;
    }

    const q = questions[idx];
    const category = q.category || '综合';
    const difficulty = q.difficulty || 'medium';
    const diffMap = { easy: '⭐', medium: '⭐⭐', hard: '⭐⭐⭐' };

    addMessage('agent',
        `**[${category}]** ${diffMap[difficulty] || ''}\n\n` +
        `**第 ${idx+1}/${questions.length} 题**\n\n` +
        `${q.question}`
    );

    currentInterview.currentIdx = idx;
    document.getElementById('answerInput').placeholder = '输入你的回答...';
    document.getElementById('answerInput').disabled = false;
    document.getElementById('answerInput').focus();
    document.getElementById('progressText').textContent = `${idx+1}/${questions.length}`;
    document.getElementById('progressFill').style.width = `${((idx+1)/questions.length)*100}%`;
}

async function submitAnswer() {
    const input = document.getElementById('answerInput');
    const answer = input.value.trim();
    if (!answer) return;

    addMessage('user', answer);
    input.value = '';
    input.disabled = true;
    input.placeholder = 'AI 正在评估...';

    try {
        const currentQ = currentInterview.questions[currentInterview.currentIdx];
        let res = null;

        await api.aiSubmitAnswerStream(currentInterview.sessionId, answer, (evt) => {
            if (evt.event === 'progress') {
                input.placeholder = '正在评分...';
            } else if (evt.event === 'complete' || evt.event === 'scored') {
                res = evt.data;
            }
        });

        if (!res) { addMessage('agent', '❌ 评分返回为空'); input.disabled = false; return; }

        // —— 追问阶段 ——
        if (res.phase === 'follow_up') {
            currentInterview._pendingOriginalAnswer = answer;
            currentInterview._pendingOriginalQ = currentQ;
            currentInterview._pendingOriginalScore = res.original_score;

            const followUpQ = res.follow_up_question;
            addMessage('agent',
                `💬 **追问**\n\n` +
                `${followUpQ}\n\n` +
                `_(初始评分: ${res.original_score}/10，请补充回答)_`
            );
            document.getElementById('currentScore').textContent = `${res.original_score}分`;
            input.disabled = false;
            input.placeholder = '输入你的补充回答...';
            input.focus();
            return;
        }

        // —— 正常 / 追问后继续 ——
        const finalAnswer = currentInterview._pendingOriginalAnswer
            ? `【原始回答】${currentInterview._pendingOriginalAnswer}\n【追问回答】${answer}`
            : answer;
        const finalQ = currentInterview._pendingOriginalQ || currentQ;

        currentInterview.answers.push({ question: finalQ, answer: finalAnswer });

        // 保存 Q&A 到后端
        if (res.last_score && currentInterview.backendSessionId) {
            const isTech = finalQ.category === '技术基础';
            const expectedAnswer = isTech && finalQ.reference_answer
                ? finalQ.reference_answer
                : (Array.isArray(finalQ.expected_answer_points)
                    ? finalQ.expected_answer_points.join('\n')
                    : (finalQ.expected_answer_points || ''));
            api.saveQa(currentInterview.backendSessionId, {
                question: finalQ.question,
                category: finalQ.category || '',
                answer: finalAnswer,
                score: res.last_score.score,
                feedback: res.last_score.feedback,
                expectedAnswer: expectedAnswer
            }).catch(e => console.warn('QA保存失败', e));
        }

        // 清除追问问答临时状态
        currentInterview._pendingOriginalAnswer = null;
        currentInterview._pendingOriginalQ = null;
        currentInterview._pendingOriginalScore = null;

        if (res.phase === 'done') {
            addMessage('agent', '✅ **面试完成！**');
            finishInterview(res.evaluation);
            return;
        }

        if (res.last_score) {
            const score = res.last_score.score;
            const feedback = res.last_score.feedback;
            document.getElementById('currentScore').textContent = `${score}分`;
            addMessage('agent', `✅ **评分: ${score}/10**\n\n💡 ${feedback}`);
        }

        if (res.current_question) {
            currentInterview.questions = currentInterview.questions || [];
            const nextIdx = res.next_question_index || (currentInterview.currentIdx + 1);
            if (res.next_question_index !== undefined) {
                currentInterview.currentIdx = nextIdx - 1;
            }
            setTimeout(() => showQuestion(currentInterview.currentIdx + 1), 1000);
        } else {
            setTimeout(() => finishInterview(), 1000);
        }
    } catch (e) {
        addMessage('agent', '❌ 评分失败，请重试');
        input.disabled = false;
        input.placeholder = '输入你的回答...';
    }
}

async function finishInterview(evaluation) {
    document.getElementById('interviewStatus').innerHTML =
        '<span class="dot" style="background:#52c41a;"></span> 面试完成';

    // 更新后端 session 状态
    try {
        if (evaluation && evaluation.overall_score && currentInterview.backendSessionId) {
            await fetch(`${API_BASE}/sessions/${currentInterview.backendSessionId}/score`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
                body: JSON.stringify({ score: evaluation.overall_score })
            });
        }
    } catch(e) {}
    // 也更新 AI 服务端的 session 评分（存入后端）
    try {
        if (currentInterview.backendSessionId && currentInterview.sessionId) {
            await fetch(`${API_BASE}/sessions/${currentInterview.backendSessionId}/status`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
                body: JSON.stringify({ status: 'COMPLETED' })
            });
        }
    } catch(e) {}

    setTimeout(() => {
        loadReport(currentInterview.sessionId);
    }, 1500);
}

// === 报告 ===

async function loadReportFromBackend(backendSessionId) {
    showPage('report');
    document.getElementById('reportContent').innerHTML = '<div style="text-align:center;padding:40px;color:#999;">加载评估报告...</div>';
    try {
        const reportRes = await api.getReport(backendSessionId);
        if (reportRes.code === 200) {
            renderReport(JSON.parse(reportRes.data.detailsJson || '{}'));
            loadQaHistory(backendSessionId);
        } else {
            document.getElementById('reportContent').innerHTML = '<div style="text-align:center;padding:40px;color:#999;">暂无报告数据</div>';
        }
    } catch(e) {
        document.getElementById('reportContent').innerHTML = '<div style="text-align:center;padding:40px;color:#999;">报告加载失败</div>';
    }
}

async function loadReport(sessionId) {
    showPage('report');
    document.getElementById('reportContent').innerHTML = '<div style="text-align:center;padding:40px;color:#999;">加载评估报告...</div>';

    // 实时面试：从 AI 服务获取报告
    try {
        const res = await api.aiGetResult(currentInterview.sessionId);
        renderReport(res);

        // 保存到后端持久化
        try {
            if (currentInterview.backendSessionId) {
                const detailsJson = JSON.stringify(res);
                await api.saveReport(
                    currentInterview.backendSessionId,
                    res.overall_score || 0,
                    detailsJson,
                    (res.improvement_suggestions || []).join('\n')
                );
                loadQaHistory(currentInterview.backendSessionId);
            }
        } catch(e) {
            console.warn('报告持久化失败', e);
        }
    } catch (e) {
        // AI session stale? Fall back to backend
        if (currentInterview.backendSessionId) {
            loadReportFromBackend(currentInterview.backendSessionId);
        } else {
            document.getElementById('reportContent').innerHTML = '<div style="text-align:center;padding:40px;color:#999;">报告加载失败</div>';
        }
    }
}

async function loadQaHistory(sessionId) {
    try {
        const res = await api.listQas(sessionId);
        if (res.code === 200 && res.data.length > 0) {
            renderQaReview(res.data);
        }
    } catch(e) {
        console.warn('Q&A 历史加载失败', e);
    }
}

function renderQaReview(qas) {
    const container = document.getElementById('reportContent');
    const qaHtml = qas.map((qa, i) => `
        <div style="border:1px solid #e8e8e8;border-radius:8px;padding:16px;margin-bottom:12px;">
            <div style="display:flex;justify-content:space-between;margin-bottom:8px;">
                <span style="font-weight:600;">第 ${i+1} 题</span>
                <span style="color:${qa.score >= 6 ? '#52c41a' : '#ff4d4f'};font-weight:600;">${qa.score}/10 分</span>
            </div>
            <div style="font-size:13px;margin-bottom:8px;">
                <span style="color:#999;">[${qa.category || '综合'}]</span>
                <span>${qa.question}</span>
            </div>
            <div style="font-size:13px;color:#1a73e8;margin-bottom:4px;">你的回答：</div>
            <div style="font-size:13px;color:#666;margin-bottom:8px;padding:8px;background:#f5f5f5;border-radius:4px;">${qa.answer || '未作答'}</div>
            ${qa.expectedAnswer ? `
            <div style="font-size:13px;color:#52c41a;margin-bottom:4px;">${qa.category === '技术基础' ? '📖 参考答案：' : '📌 参考要点：'}</div>
            <div style="font-size:13px;color:#666;padding:8px;background:#f6ffed;border-radius:4px;white-space:pre-wrap;">${qa.expectedAnswer}</div>
            ` : ''}
            ${qa.feedback ? `
            <div style="font-size:12px;color:#999;margin-top:6px;">💡 ${qa.feedback}</div>
            ` : ''}
        </div>
    `).join('');

    const section = document.createElement('div');
    section.innerHTML = '<h3 style="font-size:16px;font-weight:600;margin:24px 0 16px;">📝 问答回顾</h3>' + qaHtml;
    container.appendChild(section);
}

function renderReport(data) {
    const score = data.overall_score || 0;
    const dimensions = data.dimensions || [];
    const strengths = data.strengths || ['暂无数据'];
    const weaknesses = data.weaknesses || ['暂无数据'];
    const suggestions = data.improvement_suggestions || ['暂无建议'];
    const learning = data.recommended_learning || [];
    const answers = data.answers || [];
    const scoringQuality = data.scoring_quality || {};

    const colorMap = { '技术基础': '#52c41a', '项目经验': '#1a73e8', '场景设计': '#faad14', '软技能': '#722ed1' };

    const dimensionHtml = dimensions.length > 0 ? dimensions.map(d => `
        <div class="score-bar">
            <span class="label">${d.name}</span>
            <div class="track"><div class="fill" style="width:${d.score}%;background:${colorMap[d.name] || '#1a73e8'};"></div></div>
            <span class="value">${d.score}</span>
        </div>
    `).join('') : '<p style="color:#999;font-size:13px;">暂无维度评分数据</p>';

    // 逐题维度明细
    const perQaDimHtml = answers.length > 0 ? answers.map((a, i) => {
        const dims = a.dimensions || {};
        const dimNames = Object.keys(dims);
        if (dimNames.length === 0) return '';
        const bars = dimNames.map(dn => {
            const v = dims[dn] || 0;
            return `<div style="display:flex;align-items:center;gap:6px;margin-bottom:2px;">
                <span style="font-size:11px;min-width:52px;color:#666;">${dn}</span>
                <div style="flex:1;height:6px;background:#f0f0f0;border-radius:3px;overflow:hidden;">
                    <div style="height:100%;width:${v*10}%;background:${colorMap[dn] || '#1a73e8'};border-radius:3px;"></div>
                </div>
                <span style="font-size:11px;font-weight:600;min-width:20px;text-align:right;">${v}</span>
            </div>`;
        }).join('');
        return `<div style="border:1px solid #f0f0f0;border-radius:6px;padding:10px;margin-bottom:8px;">
            <div style="font-size:12px;font-weight:600;margin-bottom:6px;color:#333;">第${i+1}题 <span style="color:#999;font-weight:400;">[${a.category || '综合'}] ${a.score || 0}分</span></div>
            ${bars}
        </div>`;
    }).join('') : '';

    const learningHtml = learning.length > 0 ? learning.map(l =>
        `<li>${l.resource || l} ${l.reason ? '— ' + l.reason : ''}</li>`
    ).join('') : '';

    document.getElementById('reportContent').innerHTML = `
        <div class="overall-score">
            <div class="number">${score}</div>
            <div class="label">综合评分</div>
        </div>

        <div class="report-grid">
            <div class="report-section" style="grid-column:1/-1;">
                <h3>📊 各项得分</h3>
                ${dimensionHtml}
            </div>

            ${perQaDimHtml ? `
            <div class="report-section" style="grid-column:1/-1;">
                <h3>📋 逐题维度评分</h3>
                ${perQaDimHtml}
            </div>` : ''}

            <div class="report-section">
                <h3>💪 优势</h3>
                <ul style="font-size:14px;line-height:2;padding-left:20px;">
                    ${strengths.map(s => `<li>${s}</li>`).join('')}
                </ul>
            </div>

            <div class="report-section">
                <h3>📈 待改进</h3>
                <ul style="font-size:14px;line-height:2;padding-left:20px;">
                    ${weaknesses.map(w => `<li>${w}</li>`).join('')}
                </ul>
            </div>

            <div class="report-section" style="grid-column:1/-1;">
                <h3>🎯 改进建议</h3>
                <ul style="font-size:14px;line-height:2;padding-left:20px;">
                    ${suggestions.map(s => `<li>${s}</li>`).join('')}
                    ${learningHtml ? '<br><li><strong>推荐学习:</strong></li>' + learningHtml : ''}
                </ul>
            </div>

            ${scoringQuality.avg_confidence ? `
            <div class="report-section" style="grid-column:1/-1;">
                <h3>🔍 评分质量</h3>
                <div style="display:flex;gap:24px;flex-wrap:wrap;font-size:13px;">
                    <div style="flex:1;min-width:120px;">
                        <div style="color:#999;margin-bottom:4px;">平均置信度</div>
                        <div style="font-size:24px;font-weight:700;color:${scoringQuality.avg_confidence >= 7 ? '#52c41a' : scoringQuality.avg_confidence >= 5 ? '#faad14' : '#ff4d4f'};">${scoringQuality.avg_confidence}/10</div>
                    </div>
                    <div style="flex:1;min-width:120px;">
                        <div style="color:#999;margin-bottom:4px;">评分标准差</div>
                        <div style="font-size:24px;font-weight:700;color:#333;">${scoringQuality.score_std_dev}</div>
                    </div>
                    <div style="flex:1;min-width:120px;">
                        <div style="color:#999;margin-bottom:4px;">分数跨度</div>
                        <div style="font-size:24px;font-weight:700;color:#333;">${scoringQuality.score_spread}</div>
                    </div>
                    ${scoringQuality.follow_up_avg_improvement != null ? `
                    <div style="flex:1;min-width:120px;">
                        <div style="color:#999;margin-bottom:4px;">追问平均提升</div>
                        <div style="font-size:24px;font-weight:700;color:${scoringQuality.follow_up_avg_improvement > 0 ? '#52c41a' : '#999'};">+${scoringQuality.follow_up_avg_improvement}</div>
                    </div>` : ''}
                </div>
                <div style="font-size:12px;color:#999;margin-top:8px;">
                    置信度越高说明 LLM 越确定评分准确；标准差反映各题分数波动；追问平均提升衡量追问是否有效帮助候选人补充回答。
                </div>
            </div>` : ''}
        </div>

        <div class="history-compare">
            💡 每次面试后建议对照评估报告针对性查漏补缺，祝早日拿到心仪 offer！
        </div>
    `;
}
