# SmartInterview 优化计划书

---

## 总览

| 步骤 | 模块 | 优先级 | 预计改动文件 | 核心目标 |
|------|------|--------|-------------|---------|
| ① | 前端 API 代理 | 🔴 | 3~4 个 | 安全：前端不再直连 AI 服务 |
| ② | Session 持久化 | 🔴 | 3~4 个 | 可靠：服务重启后面试不丢失 |
| ③ | AI 追问机制 | 🔴 | 5~6 个 | 深度：回答不充分时自动追问 |
| ④ | 多维度评分 | 🔴 | 4~5 个 | 精准：拆维度评分而非总分 |
| ⑤ | 难度自适应 | 🟡 | 4~5 个 | 智能：根据表现动态调整题目 |
| ⑥ | 评分质量评估 | 🟡 | 3~4 个 | 闭环：量化 AI 评分准确度 |

---

## 第一步：前端 AI 代理

### 现状

```js
// 前端直接调用 AI 服务
const AI_API_BASE = 'http://localhost:8002/api/v1';

// 面试页裸 fetch
const res = await fetch(`${AI_API_BASE}/interview/start`, { ... });
const res = await fetch(`${AI_API_BASE}/interview/answer`, { ... });
const res = await fetch(`${AI_API_BASE}/interview/result/${sessionId}`);
```

### 问题

1. **AI 服务端口暴露**：8002 端口直接对外，任何人可以绕过认证调用
2. **跨域复杂**：前端 3000 → 后端 8080 → AI 8002，三个端口各自处理 CORS
3. **前端耦合**：前端需要同时知道后端地址和 AI 地址

### 方案

```
前端 (3000)
    │
    │ 只知一个地址
    │
    ▼
后端 (8080)
    │
    ├── /api/v1/interview/start   → 转发 AI 8002
    ├── /api/v1/interview/answer  → 转发 AI 8002
    ├── /api/v1/interview/result  → 转发 AI 8002
    ├── /api/v1/resume/parse      → 转发 AI 8002
    │
    └── 其他接口（JWT protected）
```

### 改动清单

| 文件 | 改动内容 |
|------|---------|
| `backend/.../api/controller/InterviewController.java` | **新增**：3 个代理端点 + 注入 RestTemplate |
| `backend/.../config/SecurityConfig.java` | 添加 `/api/v1/interview/**` 需要认证 |
| `frontend/js/api.js` | 删除 `AI_API_BASE`，`aiStartInterview`/`aiSubmitAnswer`/`aiGetResult`/`parseResume` 全部改走 `API_BASE` |
| `frontend/index.html` | `finishInterview()` 中的裸 fetch 改为 `api.*` 调用 |

### 预期效果

- AI 服务只需监听 `127.0.0.1:8002`，不对外暴露
- 前端只需配置 `API_BASE` 一个地址
- 后端统一做 JWT 校验，未登录无法调面试接口

---

## 第二步：Session 持久化

### 现状

```python
# InterviewSessionStore 用内存 dict + 本地 JSON 文件
self._sessions: Dict[str, InterviewState] = {}  # 内存
# 文件：data/sessions/{session_id}.json
```

问题：
- 服务重启后文件还在但 `messages` 被丢弃（`_load_all` 中 `data["messages"] = []`）
- `current_question_index` 恢复后不准确
- `answers` 列表恢复不完整

### 方案

**方案 A（短期 — Redis）**：将 session 状态序列化到 Redis，key 为 `interview:session:{id}`

```
优点：后端已有 Redis（参考 community 项目），部署简单
缺点：状态对象大，序列化/反序列化开销较高
TTL：设置 24 小时过期，面试结束后自动清理
```

**方案 B（中期 — MySQL）**：复用后端已有的 JD/Session/QA/Report 表

```
当前已经有的落库流程：
  session 创建 → INSERT sessions
  每题提交 → INSERT qas (question/answer/score/feedback)
  面试结束 → INSERT reports (overall_score/details_json/suggestions)

改造点：
  - qas 表增加字段：question_index（题号）、follow_up_question（追问文本，可为 null）
  - 面试恢复时：SELECT sessions WHERE id=? AND status='IN_PROGRESS'
                 → SELECT qas WHERE session_id=? ORDER BY question_index
                 → 重建 InterviewState
```

**建议**：用方案 B，因为 QA/Report 本来就已经在后端落库了，现在差的是 AI 服务能"读回来"重建状态。

### 改动清单

| 文件 | 改动内容 |
|------|---------|
| `backend/.../api/controller/InterviewController.java` | **新增** `GET /interview/{sessionId}/state` — 返回重建状态所需的全部数据 |
| `ai-service/app/services/interview_service.py` | `InterviewSessionStore.create()` 增加 `restore_from_backend` 逻辑 |
| `ai-service/app/main.py` | 添加 `POST /interview/restore` 端点（从后端数据重建 session） |
| `frontend/js/api.js` | startInterview 中增加断线恢复判断 |

### 预期效果

- 前端刷新页面 → 调 `GET /interview/{sessionId}/state` → 如果 status=IN_PROGRESS → AI 服务恢复 session → 继续从第 N 题开始
- AI 服务重启后，任何进行中的面试都可以从后端 MySQL 恢复

---

## 第三步：AI 追问机制

### 现状

```
当前流程：
  用户答完 → AI 评分 (score + feedback) → 下一题

问题：
  - 回答不充分（得分低）也直接跳下一题
  - 没有深度挖掘能力
  - 面试体验像一个"答题机器"，不像真人面试官
```

### 方案

在 LangGraph 的 interview 节点中加入追问判断逻辑：

```
用户回答
    │
    ▼
AI 评分 + 判断是否需要追问
    │
    ├── score >= 6 且回答完整 → 下一题
    │
    ├── score < 4 → 追问 1 次："你能再具体说说吗？比如..."
    │       │
    │       └── 用户答完 → 最终评分 → 下一题（不继续追问）
    │
    └── score 4~5 → 追问 1 次："你提到了X，能否深入聊聊Y？"
            │
            └── 用户答完 → 最终评分 → 下一题
```

**核心规则**：
- 每道题最多追问 1 次（避免无限循环）
- 追问内容由 LLM 生成，而非固定模板
- 追问后的评分取两次回答的综合分

### 改动清单

| 文件 | 改动内容 |
|------|---------|
| `ai-service/app/agents/state.py` | 增加 `follow_up_count: int` 和 `pending_follow_up: bool` 字段 |
| `ai-service/app/agents/interview.py` | `interview_node` 增加追问判断逻辑 + `_generate_follow_up()` |
| `ai-service/app/services/interview_service.py` | `submit_answer()` 增加 `is_follow_up` 参数，追问阶段不推进 `current_question_index` |
| `frontend/index.html` | `submitAnswer()` 解析 `res.phase === 'follow_up'` 显示新问题 |
| `backend/.../data/entity/QA.java` | 增加 `followUpQuestion` 字段 |
| `backend/.../api/dto/` | QA 相关 DTO 增加追问字段 |

### 预期效果

- 面试不再是"答完就过"，AI 会对不充分的回答进行追问
- 追问有一定深度，模拟真实面试官的互动
- 报告里能看到追问链，用户体验更有层次

---

## 第四步：多维度评分

### 现状

```python
# evaluator_node 和 _score_answer 只返回单一分数
{
    "score": 7,
    "feedback": "...",
    "overall_score": 72,
    "strengths": [...],
    "weaknesses": [...]
}
```

当前 `evaluator` 已经返回了 `dimensions` 列表，但结构不稳定——有时有有时没有，且维度名是 LLM 自由发挥的。

### 方案

**固定 4 个评分维度**，在 system prompt 中硬约束：

| 维度 | 含义 | 子维度参考 |
|------|------|-----------|
| **技术基础** (technical) | 概念准确性、深度、广度 | 是否答到核心概念、有无混淆 |
| **项目经验** (project) | 实际经验的真实性、细节 | STARR 完整性、量化指标、问题解决 |
| **逻辑思维** (thinking) | 结构化表达、问题拆解 | First principles、MECE、推导链条 |
| **沟通表达** (communication) | 简洁清晰、重点突出 | 是否回答了面试官真正问的点 |

**评分结构**：

```json
{
  "dimensions": [
    {"name": "技术基础", "score": 8, "comment": "对核心概念理解准确"},
    {"name": "项目经验", "score": 6, "comment": "缺乏量化指标"},
    {"name": "逻辑思维", "score": 7, "comment": "结构清晰但拆解不够细"},
    {"name": "沟通表达", "score": 5, "comment": "回答过长，重点不突出"}
  ],
  "overall_score": 65,
  "strengths": ["技术储备扎实"],
  "weaknesses": ["表达不够精炼", "缺少数据支撑"]
}
```

每道题的评分也按 4 维度：

```json
{
  "score": 7,
  "dimension_scores": {"technical": 8, "project": 5, "thinking": 7, "communication": 6},
  "feedback": "...",
  "follow_up": "..."
}
```

### 改动清单

| 文件 | 改动内容 |
|------|---------|
| `ai-service/app/agents/evaluator.py` | 修改 prompt 强制输出 4 维度结构（含 JSON schema 约束） |
| `ai-service/app/services/interview_service.py` | `_score_answer()` 中评分 prompt 改为输出 4 维子分 |
| `ai-service/app/agents/state.py` | `evaluation` 字段类型改为明确的维度结构 |
| `frontend/index.html` | `renderReport()` 维度柱状图改为 4 根（固定颜色） |
| `backend/.../data/entity/Report.java` | `detailsJson` 格式升级，`dimensions` 固定含 4 个维度 |

### 预期效果

- 每道题 + 综合评估都是 4 维度打分
- 报告页面的柱状图固定 4 根，颜色区分
- 用户能清楚知道"我技术答得不错但表达太啰嗦"这种具体问题
- 后期可以做**弱项趋势追踪**（连续 3 次面试沟通表达都低 → 推荐沟通课程）

---

## 第五步：难度自适应

### 现状

```python
# question_generator 根据 gap_analysis 生成固定数量的题目
# 题目难度是 LLM 自己决定的，没有根据答题表现动态调整
```

当前的 `question_generator_node` 生成题目时，每道题有一个 `difficulty` 字段（easy/medium/hard），但这是静态的——全部在面试开始前一次性生成好的。用户表现好不会变难，表现差不会变简单。

### 方案

**自适应引擎**：根据前面题目的表现，动态生成后续题目。

```
第 1 题 (medium)
    │
    ├── 得分 >= 8 → 第 2 题升级为 hard
    ├── 得分 4-7  → 第 2 题维持 medium
    └── 得分 < 4  → 第 2 题降级为 easy（但仍覆盖同一知识域）
```

**实现方式**：

在 `interview_service.py` 的 `submit_answer()` 中，每题答完后：

1. 累计计算当前均分
2. 将下一题的原题和难度传给 LLM，要求调整难度：
   - 变难：增加题目中场景的复杂度、添加约束条件
   - 变简单：拆分成更基础的小问、给出提示
3. 调整后的题目存入 `questions[next_idx]`

**不一次性生成所有题目，改为**：
- 面试开始时只生成大纲（题目数 + 每题的类别/知识域）
- 每答完一题 → 根据表现动态生成下一题

### 改动清单

| 文件 | 改动内容 |
|------|---------|
| `ai-service/app/agents/question_generator.py` | 增加 `generate_next_question()` — 根据当前表现生成下一题（而非批量生成） |
| `ai-service/app/services/interview_service.py` | 修改 `analyze()` — 先生成大纲（类别 + 数量），再在 `submit_answer()` 中每题动态生成 |
| `ai-service/app/agents/state.py` | 增加 `difficulty_profile: dict`（记录每题难度 + 用户在该难度的表现） |
| `frontend/index.html` | `showQuestion()` 显示当前难度标签 |
| `backend/.../data/entity/QA.java` | 增加 `difficulty` 字段 |

### 预期效果

- 技术强者不会被简单题浪费时间，技术弱者不会被难题打击信心
- 面试体验接近真实面试官："你上个问题答得不错，我们聊个更深的"
- 最终报告包含**难度曲线**（面试过程中题目难度如何变化）

---

## 第六步：评分质量评估

### 现状

当前数据闭环只有：
```
面试 → QA 入库 → Admin 校准 → calibrated=true → 下次评分时作为 few-shot 样本
```

但缺少一个关键指标：**AI 评分的准确度到底怎么样？**

### 方案

**新增评分质量指标**：

| 指标 | 计算方式 | 含义 |
|------|---------|------|
| **平均偏差** | Σ\|AI 分 - 校准分\| / 校准样本数 | AI 评分整体偏离程度 |
| **偏差分布** | 偏差在 ±1/±2/±3 分内的占比 | AI 评分精度分布 |
| **分类偏差** | 按 category 分组计算平均偏差 | 哪个类别的题目 AI 评得最不准 |
| **漂移检测** | 最近 30 天 vs 前 30 天的偏差对比 | AI 评分是否在变差 |

**在 Admin 数据统计页增加一个"评分质量"卡片组**：

```
┌─────────────────────────────────────────────────────┐
│ 📊 AI 评分质量                                      │
│                                                     │
│ 校准样本数: 156       平均偏差: 1.2分               │
│ ±1分内: 68%          ±2分内: 89%                   │
│                                                     │
│ 偏差最大类别: 项目经验 (1.8分)                      │
│ 偏差最小类别: 技术基础 (0.7分)                      │
└─────────────────────────────────────────────────────┘
```

### 改动清单

| 文件 | 改动内容 |
|------|---------|
| `backend/.../service/StatsService.java` | 增加 `getScoringQualityStats()` — 计算偏差指标 |
| `backend/.../controller/StatsController.java` | 增加 `GET /api/v1/stats/scoring-quality` |
| `backend/.../repository/QARepository.java` | 增加 `countByCalibratedTrue()` + 聚合查询 |
| `frontend/js/admin.js` | `loadAdminStats()` 增加评分质量数据渲染 |

### 预期效果

- 管理员能看到 AI 评分准不准、在哪些类别偏差大
- 长期积累校准数据 → 量化 AI 评分可靠性 → 决定是否调整 prompt 或换模型
- 为后续"半自动评分"提供数据支撑（高置信度自动过，低置信度人工审）

---

## 实施顺序依赖关系

```
① ────────────────┐
② ────────────────┤
                  ├──→ ③ ──→ ④ ──→ ⑤
                  │                  │
                  │                  ▼
                  └──────────────→ ⑥ (依赖校准数据积累)
```

- ①② 可以先并行做（互不依赖）
- ③④⑤ 需要 ② 完成后做（追问链和维度评分都依赖 session 状态）
- ⑥ 依赖 ④ 的维度数据 + 足够的校准样本积累

---

## 时间估算

| 步骤 | 预估改动量 | 预估时间 |
|------|-----------|---------|
| ① 前端 API 代理 | ~150 行 | 30 min |
| ② Session 持久化 | ~250 行 | 1 h |
| ③ AI 追问机制 | ~300 行 | 1.5 h |
| ④ 多维度评分 | ~250 行 | 1 h |
| ⑤ 难度自适应 | ~300 行 | 1.5 h |
| ⑥ 评分质量评估 | ~200 行 | 45 min |
