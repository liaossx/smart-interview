"""
面试服务：管理面试会话状态

本文件是 AI 面试链路的核心业务层，承担以下职责：
1. 会话生命周期管理 —— 创建、持久化、恢复面试会话（InterviewSessionStore）。
2. LangGraph 调用入口 —— analyze() / analyze_stream() 触发 JD 分析、简历分析、
   差距分析、出题等图节点顺序执行。
3. 评分引擎核心 —— _score_answer() 负责单题评分：调用 LLM、清洗 markdown 围栏、
   校验分数范围、3 次重试+指数退避、兜底 score=5，并根据得分<7 生成追问。
4. 自适应难度 —— _check_difficulty_target() 依据近期均分动态调整后续题目难度。
5. 综合评估 —— _run_evaluation() 聚合各维度均分，注入历史统计上下文后调用评估节点。

详见 AI链路学习路径.md 第五步。
"""

import json
import logging
import os
import uuid
import time
from typing import Dict, Optional
from langchain_core.messages import HumanMessage, AIMessage
from app.agents.state import InterviewState
from app.agents.graph import interview_graph

logger = logging.getLogger(__name__)


class InterviewSessionStore:
    """
    DB + 内存混合会话存储，支持服务重启后恢复。

    设计要点：
    - 内存 dict _sessions 作为热路径缓存，避免每次请求都查库。
    - MySQL ai_sessions 表做持久化，服务重启后可 _load_all() 恢复全部会话。
    - DB 不可用时自动降级为纯内存模式，保证 AI 链路不中断。
    - 每次 _save_one() 用 UPSERT 写入，updated_at 用于 24h 自动清理。
    """

    def __init__(self, persist_dir: str = None):
        # 内存缓存：session_id -> InterviewState dict
        self._sessions: Dict[str, InterviewState] = {}
        self._db_engine = None
        self._init_db()    # 建表 + 清理过期记录
        self._load_all()   # 启动时把 DB 里的会话全部加载回内存

    def _init_db(self):
        """初始化数据库连接和 ai_sessions 表，失败则降级纯内存模式"""
        try:
            from sqlalchemy import create_engine, text
            from app.core.config import get_settings
            settings = get_settings()
            # pool_pre_ping=True 避免使用已断开的连接（MySQL 8h 超时问题）
            # pool_recycle=3600 每小时回收连接，防止连接老化
            self._db_engine = create_engine(
                settings.database_url,
                pool_pre_ping=True,
                pool_size=5,
                pool_recycle=3600,
            )
            with self._db_engine.connect() as conn:
                # 建表：state 字段以 JSON 存储 LangGraph 状态快照
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS ai_sessions (
                        session_id VARCHAR(36) PRIMARY KEY,
                        state JSON,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                    )
                """))
                # 清理 24h 未更新的会话，避免表无限膨胀
                conn.execute(text(
                    "DELETE FROM ai_sessions WHERE updated_at < DATE_SUB(NOW(), INTERVAL 24 HOUR)"
                ))
                conn.commit()
            logger.info("AI session DB initialized")
        except Exception as e:
            # DB 不可用不阻断服务，降级为纯内存模式
            logger.warning(f"DB初始化失败，降级为纯内存模式: {e}")
            self._db_engine = None

    def _serialize_state(self, state: dict) -> dict:
        """
        序列化 LangGraph state 为可 JSON 化的 dict。

        特殊处理：messages 是 LangChain Message 对象列表，无法直接 json.dumps，
        需要拆成 {role, content} 平铺结构。其余字段尝试直接序列化，失败则降级为字符串。
        """
        serializable = {}
        for k, v in state.items():
            if k == "messages":
                # 把 HumanMessage/AIMessage 转成纯 dict，方便 JSON 存储
                serializable[k] = [
                    {"role": getattr(m, "type", "unknown"), "content": getattr(m, "content", "")}
                    for m in v
                ]
            else:
                try:
                    json.dumps(v)
                    serializable[k] = v
                except (TypeError, ValueError):
                    # 不可序列化的对象降级为字符串表示，避免整体持久化失败
                    serializable[k] = str(v) if v is not None else None
        return serializable

    def _save_one(self, session_id: str):
        """把单个会话状态 UPSERT 到 MySQL，供服务重启后恢复"""
        state = self._sessions.get(session_id)
        if not state or not self._db_engine:
            return
        try:
            from sqlalchemy import text
            serializable = self._serialize_state(state)
            with self._db_engine.connect() as conn:
                # ON DUPLICATE KEY UPDATE 实现已有会话更新、新会话插入
                conn.execute(text("""
                    INSERT INTO ai_sessions (session_id, state)
                    VALUES (:sid, :state)
                    ON DUPLICATE KEY UPDATE state = :state, updated_at = NOW()
                """), {"sid": session_id, "state": json.dumps(serializable, ensure_ascii=False)})
                conn.commit()
        except Exception as e:
            # 持久化失败不影响内存中的会话，仅记录告警
            logger.warning(f"持久化会话 {session_id} 失败: {e}")

    def _load_all(self):
        """服务启动时从 MySQL 加载全部会话到内存，恢复对话历史"""
        if not self._db_engine:
            return
        try:
            from sqlalchemy import text
            with self._db_engine.connect() as conn:
                result = conn.execute(text("SELECT session_id, state FROM ai_sessions"))
                for row in result:
                    session_id = row[0]
                    raw_state = row[1]
                    data = json.loads(raw_state) if isinstance(raw_state, str) else raw_state
                    # 恢复对话历史：把 {role,content} dict 列表还原成 LangChain Message 对象
                    raw_msgs = data.get("messages", [])
                    restored = []
                    for m in raw_msgs:
                        role = m.get("role", "unknown")
                        content = m.get("content", "")
                        if role == "human":
                            restored.append(HumanMessage(content=content))
                        elif role == "ai":
                            restored.append(AIMessage(content=content))
                    data["messages"] = restored
                    self._sessions[session_id] = data
            logger.info(f"从DB恢复了 {len(self._sessions)} 个会话")
        except Exception as e:
            # 加载失败不阻断启动，内存模式仍可工作
            logger.warning(f"从DB加载会话失败: {e}")

    def create(self, jd_content: str, resume_content: str = "", user_id: int = 1) -> "InterviewSession":
        """创建全新面试会话，返回封装好的 InterviewSession 对象"""
        session_id = str(uuid.uuid4())[:8]
        # 初始化 LangGraph 状态：所有字段都有默认值，保证图节点不会因缺字段报错
        state: InterviewState = {
            "messages": [],               # LangChain 对话历史，供 LLM 跨题上下文参考
            "user_id": user_id,
            "session_id": session_id,
            "jd_content": jd_content,      # 原始 JD 文本，后续节点用于分析
            "resume_content": resume_content,
            "jd_analysis": {},             # JD 分析结果，由 jd_analyzer 节点填充
            "resume_analysis": {},
            "gap_analysis": {},            # 差距分析：候选人能力 vs JD 要求的 gap
            "questions": [],               # 生成的面试题列表
            "current_question_index": 0,
            "answers": [],                 # 已回答题目及其评分
            "evaluation": {},              # 综合评估结果
            "stats_context": "",           # 注入 prompt 的历史统计文本
            "pending_follow_up": {},       # 待处理的追问（score<7 时触发）
            "difficulty_stats": {"easy": [], "medium": [], "hard": []},  # 各难度历史得分
            "supplemental_questions": [],  # 自适应难度生成的补充题
            "iteration_count": 0,
            "phase": "init",               # 当前阶段标识
        }
        self._sessions[session_id] = state
        return InterviewSession(session_id, state, self._sessions, self)

    def restore(self, jd_content: str, resume_content: str, qas: list,
                current_question_index: int = 0, user_id: int = 1,
                existing_session_id: str = None,
                questions: list = None) -> "InterviewSession":
        """
        从后端 MySQL 数据重建面试状态。

        场景：用户的面试记录存在后端业务库（非 AI 侧的 ai_sessions 表），
        前端刷新或断线重连时调用本方法，把已有 Q&A 历史重新注入 LangGraph state，
        使后续评分/出题能接续之前的上下文。

        参数：
        - qas：已答题目列表 [{question, category, answer, score, feedback}, ...]
        - questions：完整题目列表（可选）；不传则从 qas 重建题目骨架
        - current_question_index：当前应作答第几题
        - existing_session_id：复用已有 session_id，避免生成新 ID
        """
        # 复用已有 session_id（断线重连场景），或生成新的 8 位 UUID
        session_id = existing_session_id or str(uuid.uuid4())[:8]

        # 如果传入了完整题目列表，直接使用；否则从 qas 重建
        # （恢复场景下后端可能只存了 Q&A 记录，没有完整题目元数据，
        #  此时用 qas 的 question/category 拼出最小题目结构，difficulty 默认 medium）
        if questions and len(questions) > 0:
            restored_questions = questions
        else:
            restored_questions = []
            for qa in qas:
                restored_questions.append({
                    "question": qa.get("question", ""),
                    "category": qa.get("category", ""),
                    "difficulty": "medium",
                    "expected_answer_points": [],
                })

        # 重建 answers 列表，保留已有评分；缺失评分默认 5 分
        answers = []
        for qa in qas:
            answers.append({
                "question_id": len(answers) + 1,
                "question": qa.get("question", ""),
                "category": qa.get("category", ""),
                "answer": qa.get("answer", ""),
                "score": qa.get("score", 5),
                "feedback": qa.get("feedback", ""),
            })

        # 从已答题目提取类别，供后续生成题目时做去重/补充参考
        categories_seen = list(set(a.get("category", "") for a in answers if a.get("category")))

        # 重建 LangGraph 状态：保留已有 Q&A 历史，phase 设为 questions_ready 跳过分析阶段
        state: InterviewState = {
            "messages": [],
            "user_id": user_id,
            "session_id": session_id,
            "jd_content": jd_content,
            "resume_content": resume_content,
            "jd_analysis": {},
            "resume_analysis": {},
            "gap_analysis": {},
            "questions": restored_questions,
            "current_question_index": current_question_index,
            "answers": answers,
            "evaluation": {},
            "stats_context": "",
            "pending_follow_up": {},
            "difficulty_stats": {"easy": [], "medium": [], "hard": []},
            "supplemental_questions": [],
            "iteration_count": current_question_index,
            "phase": "questions_ready",  # 恢复后直接进入题目就绪阶段，跳过分析阶段
        }
        self._sessions[session_id] = state
        self._save_one(session_id)  # 持久化到 AI 侧 ai_sessions 表
        return InterviewSession(session_id, state, self._sessions, self)

    def get(self, session_id: str) -> Optional["InterviewSession"]:
        """根据 session_id 获取会话；不存在返回 None（仅查内存缓存）"""
        state = self._sessions.get(session_id)
        if not state:
            return None
        return InterviewSession(session_id, state, self._sessions, self)

    def remove(self, session_id: str):
        """从内存和 DB 双删会话"""
        self._sessions.pop(session_id, None)
        if self._db_engine:
            try:
                from sqlalchemy import text
                with self._db_engine.connect() as conn:
                    conn.execute(text("DELETE FROM ai_sessions WHERE session_id = :sid"), {"sid": session_id})
                    conn.commit()
            except Exception as e:
                logger.warning(f"删除DB会话 {session_id} 失败: {e}")


class InterviewSession:
    """
    单个面试会话的操作封装。

    持有 session_id 和 LangGraph state 引用，对外提供分析、提交答案、
    流式输出、评估等业务方法。每次状态变更后调用 _save() 同步到内存+DB。
    """

    def __init__(self, session_id: str, state: InterviewState, store: Dict, store_manager: InterviewSessionStore = None):
        self.session_id = session_id
        self._state = state                 # LangGraph 状态 dict
        self._store = store                 # 指向 InterviewSessionStore._sessions 的引用
        self._store_manager = store_manager  # 用于触发 DB 持久化

    def _save(self):
        """同步状态到内存缓存和 DB"""
        self._store[self.session_id] = self._state
        if self._store_manager:
            self._store_manager._save_one(self.session_id)

    def analyze(self) -> dict:
        """
        运行分析阶段：JD分析 -> 简历分析 -> 差距分析 -> 出题。

        调用 LangGraph 的 interview_graph.invoke()，按图节点顺序自动执行。
        recursion_limit=50 防止图节点循环导致死递归。
        执行完成后把图输出合并回当前 state 并持久化。
        """
        # 同步阻塞调用整个 LangGraph 链路；返回的是最终 state 快照
        # interview_graph 是在 app.agents.graph 中构建的有向无环图，节点顺序：
        # jd_analyzer -> resume_analyzer -> gap_analyzer -> question_generator
        # 每个节点接收 state、处理后返回增量字段，LangGraph 自动合并
        # recursion_limit=50 防止图节点循环导致死递归（正常流程 4 个节点远低于此上限）
        result = interview_graph.invoke(
            self._state,
            {"recursion_limit": 50},
        )
        # 把图执行产出的字段（jd_analysis、questions 等）合并回当前会话状态
        # update() 会用 result 中的值覆盖 _state 中的同名字段
        self._state.update(result)

        # 提取生成的题目列表，取第一题作为面试起始题
        questions = result.get("questions", [])
        first_question = questions[0] if questions else None

        # 持久化到内存缓存和 MySQL，供后续 submit_answer() 使用
        self._save()
        return {
            "session_id": self.session_id,
            "phase": result.get("phase", "questions_ready"),
            "total_questions": len(questions),
            "current_question": first_question,
            "questions": questions,
            "jd_analysis": result.get("jd_analysis", {}),
            "gap_analysis": result.get("gap_analysis", {}),
        }

    def resume_analyze(self) -> dict:
        """
        恢复模式：跳过 JD/简历分析，直接从已有题目继续面试。

        如果当前索引已超出题目列表（说明原有题目已答完），会尝试用 LLM
        生成 5 道 medium 补充题以延长面试；LLM 失败则返回 done。
        """
        # 从恢复的 state 中读取题目列表和当前索引
        questions = self._state.get("questions", [])
        current_idx = self._state.get("current_question_index", 0)
        total = len(questions)

        # 当前索引超出题目列表范围 -> 说明原有题目已全部答完
        if current_idx >= total:
            # 没有更多题目，尝试生成补充题延长面试
            if total > 0:
                new_qs = self._generate_supplemental("medium", count=5)
                if new_qs:
                    questions.extend(new_qs)
                    self._state["questions"] = questions
                    total = len(questions)
                    self._save()

            # 生成后如果还是不够，说明 LLM 也失败了
            if current_idx >= total:
                return {
                    "session_id": self.session_id,
                    "phase": "done",
                    "message": "所有题目已答完",
                }

        next_question = questions[current_idx]
        self._save()
        return {
            "session_id": self.session_id,
            "phase": "continue",
            "total_questions": total,
            "current_question_index": current_idx,
            "current_question": next_question,
            "questions": questions,
            "answered_count": current_idx,
            "jd_analysis": self._state.get("jd_analysis", {}),
            "gap_analysis": self._state.get("gap_analysis", {}),
        }

    def generate_next_questions(self, count: int = None) -> dict:
        """根据已有进度，生成剩余题目（用于恢复面试时题目列表不完整的场景）"""
        questions = self._state.get("questions", [])
        answers = self._state.get("answers", [])
        current_idx = self._state.get("current_question_index", 0)
        total_answered = len(answers)

        # 如果题目不够（恢复时没有全量题目），用 LLM 补全
        if total_answered >= len(questions) and total_answered > 0:
            return {
                "session_id": self.session_id,
                "phase": "done",
                "current_question": None,
                "total_questions": len(questions),
                "questions": questions,
                "answered_count": total_answered,
            }

        next_question = questions[current_idx] if current_idx < len(questions) else None
        return {
            "session_id": self.session_id,
            "phase": "continue",
            "current_question": next_question,
            "total_questions": len(questions),
            "questions": questions,
            "answered_count": total_answered,
            "current_question_index": current_idx,
        }

    def submit_answer(self, answer: str) -> dict:
        """
        提交答案并返回下一题、追问或评估结果。

        Q&A 循环核心逻辑：
        - 如果存在 pending_follow_up（上一轮 score<7 触发了追问），则本次提交
          的是追问的回答，合并原始回答后重新评分，然后推进到下一题。
        - 正常流程：评分 -> 若 score<7 且 LLM 给出 follow_up 文本，则暂存追问，
          返回 follow_up 阶段等待候选人回答追问。
        - 若无需追问，保存答案 -> 记录难度 -> 推进索引。
        - 到最后一题时触发 _run_evaluation() 生成综合评估报告。
        """
        # 获取当前题目索引和题目列表
        current_idx = self._state.get("current_question_index", 0)
        questions = self._state.get("questions", [])

        # 索引超出范围 -> 所有题目已答完
        if current_idx >= len(questions):
            return {"phase": "done", "message": "所有题目已答完"}

        # 取当前题目，并检查是否有待处理的追问（上一轮 score<7 触发）
        question = questions[current_idx]
        pending = self._state.get("pending_follow_up")

        # —— 追问回答流程 ——
        # 前一轮 score<7 触发了追问，现在候选人回答了追问
        # 此时 pending_follow_up 中暂存了追问问题和原始回答，需要合并后重新评分
        if pending:
            # 把原始回答和追问回答拼在一起，让 LLM 看到完整信息后重新评分
            # 评分时会对比原始回答，计算改善率（original_score vs 新 score）
            combined_answer = f"【原始回答】{pending['original_answer']}\n【追问回答】{answer}"
            score_data = self._score_answer(question, combined_answer)

            self._state.setdefault("answers", []).append({
                "question_id": current_idx + 1,
                "question": question.get("question", ""),
                "category": question.get("category", ""),
                "answer": combined_answer,
                "score": score_data.get("score", 5),
                "feedback": score_data.get("feedback", ""),
                "dimensions": score_data.get("dimensions", {}),
                "confidence": score_data.get("confidence", 5),
                "follow_up_question": pending.get("question", ""),
                "original_score": pending.get("score_so_far", 0),  # 追问前的原始分，用于计算改善率
            })

            # 记录难度表现并检查是否需要自适应调整
            self._record_and_adjust(question, score_data.get("score", 5))

            self._state["pending_follow_up"] = {}  # 清除追问状态，进入下一题
            next_idx = current_idx + 1
            self._state["current_question_index"] = next_idx

            # 最后一题 -> 触发综合评估
            if next_idx >= len(questions):
                self._state["phase"] = "interview_done"
                self._run_evaluation()
                self._save()
                return {
                    "phase": "done",
                    "session_id": self.session_id,
                    "message": "面试完成",
                    "last_score": score_data,
                    "evaluation": self._state.get("evaluation", {}),
                }

            self._save()
            return {
                "phase": "continue",
                "current_question": questions[next_idx],
                "total_questions": len(questions),
                "answered_count": next_idx,
                "last_score": score_data,
                "next_question_index": next_idx,
            }

        # —— 正常回答流程 ——
        # 调用核心评分引擎 _score_answer()：构建 prompt -> 调用 LLM -> 解析 JSON -> 校验分数
        # 评分结果包含 score(综合分)、dimensions(4维度)、feedback(评语)、follow_up(追问)、confidence(自信度)
        score_data = self._score_answer(question, answer)
        follow_up_text = score_data.get("follow_up", "").strip()
        score = score_data.get("score", 5)

        # 评分 < 7 且 LLM 给出了追问 -> 触发追问，不推进题目索引
        # 设计意图：得分低的回答可能是因为表达不完整而非能力不足，
        # 给候选人一次补充说明的机会，更接近真实面试体验
        # 候选人回答追问后会再次进入 submit_answer，走上面的追问流程
        if score < 7 and follow_up_text:
            self._state["pending_follow_up"] = {
                "question": follow_up_text,
                "original_answer": answer,
                "score_so_far": score,  # 暂存原始分，追问后用于对比改善
            }
            self._save()
            return {
                "phase": "follow_up",
                "follow_up_question": follow_up_text,
                "original_score": score,
                "question_index": current_idx,
                "total_questions": len(questions),
                "answered_count": current_idx,
            }

        # 无追问 -> 正常保存答案并推进到下一题
        # 评分 >= 7 或 LLM 未生成追问，说明回答已足够充分，直接进入下一题
        self._state.setdefault("answers", []).append({
            "question_id": current_idx + 1,
            "question": question.get("question", ""),
            "category": question.get("category", ""),
            "answer": answer,
            "score": score_data.get("score", 5),
            "feedback": score_data.get("feedback", ""),
            "dimensions": score_data.get("dimensions", {}),
            "confidence": score_data.get("confidence", 5),
        })

        # 记录难度表现并检查是否需要自适应调整难度
        self._record_and_adjust(question, score_data.get("score", 5))

        # 推进到下一题
        next_idx = current_idx + 1
        self._state["current_question_index"] = next_idx

        # 最后一题 -> 触发综合评估
        if next_idx >= len(questions):
            self._state["phase"] = "interview_done"
            self._run_evaluation()
            self._save()
            return {
                "phase": "done",
                "session_id": self.session_id,
                "message": "面试完成",
                "last_score": score_data,
                "evaluation": self._state.get("evaluation", {}),
            }

        self._save()
        return {
            "phase": "continue",
            "current_question": questions[next_idx],
            "total_questions": len(questions),
            "answered_count": next_idx,
            "last_score": score_data,
            "next_question_index": next_idx,
        }

    def _score_answer(self, question: dict, answer: str) -> dict:
        """
        评分引擎核心：调用 LLM 对单道回答评分，含重试、统计参照和 JSON 修复。

        整体流程：
        1. 从 stats_client 获取该类别的历史统计上下文（均分/区间/校准样本），
           注入 prompt 使评分与其他同类回答横向可比。
        2. 构建 4 维度评分 prompt（技术基础/项目经验/场景设计/软技能），
           要求 LLM 返回结构化 JSON。
        3. 把已有对话历史拼入消息列表，使 LLM 能做跨题关联评分。
        4. 调用 LLM，最多重试 3 次：
           - JSON 解析失败 -> 指数退避重试（1s, 2s）
           - 网络/超时错误 -> 指数退避重试（2s, 4s）
           - 不可重试错误（如认证失败）-> 直接跳出
        5. 清洗 LLM 输出的 markdown 代码围栏，解析 JSON。
        6. 对 score / dimensions / confidence 做范围钳制（0-10）。
        7. 把本次 Q&A 和评分写入 messages 对话历史，供后续评分参考。
        8. 全部失败时兜底返回 score=5、confidence=1，保证面试不中断。
        """
        from app.core.llm import get_fast_llm
        from app.services.stats_client import stats_client
        # 使用快速 LLM 实例评分（平衡速度与质量）
        llm = get_fast_llm()

        category = question.get('category', '')
        # 注入历史统计上下文：该类别的历史均分/区间 + 人工校准样本（few-shot）
        # 让 LLM 评分有横向参照，避免不同题评分尺度漂移
        stats_context = stats_client.build_scoring_context(category) if category else ""

        # 构建 4 维度评分 prompt：技术基础/项目经验/场景设计/软技能
        # stats_context 被原样拼入 prompt，为 LLM 提供历史均分和校准样本参照
        score_prompt = f"""你是一位面试官。请对以下回答从四个维度评分（每维度 0-10），并给出综合分数和简短评语。

题目：{question.get('question', '')}
类别：{category}
期望要点：{', '.join(question.get('expected_answer_points', ['无']))}
{stats_context}

候选人的回答：{answer}

各维度评分规则：
- 技术基础：对核心技术概念、原理的理解深度
- 项目经验：实际项目中的实践经验、落地能力
- 场景设计：架构设计、方案选型、高并发/高可用等场景思考
- 软技能：沟通表达、逻辑清晰度、问题分析思路
若某维度在该题中不适用，给 0 分。综合分取适用维度的加权平均。

评分时请参考上述历史数据分布，确保评分与其他同类回答横向可比。

以 JSON 格式返回：
{{
  "score": 0-10,
  "dimensions": {{
    "技术基础": 0-10,
    "项目经验": 0-10,
    "场景设计": 0-10,
    "软技能": 0-10
  }},
  "feedback": "评语",
  "follow_up": "如果候选人的回答不完整或不够深入（通常得分<7），请写一个追问来挖掘更多信息。如果回答已经完整充分，设为空字符串。追问应该像真实面试官一样追问具体细节，要求举例或深入某个技术点",
  "confidence": 0-10
}}
confidence 表示你对本次评分的自信程度：
- 9-10: 回答完全覆盖期望要点，非常确定
- 7-8: 回答基本覆盖要点，有一定把握
- 5-6: 回答部分覆盖，需要人工复核
- 0-4: 回答模糊或偏离，评分可能不准确
只返回 JSON。"""

        # 构建带对话历史的消息列表，使 LLM 有上下文做跨题关联评分
        # 把之前所有 Q&A 的 HumanMessage/AIMessage 都带上，LLM 能看到候选人整体表现趋势
        context_messages = list(self._state.get("messages", []))
        context_messages.append(HumanMessage(content=score_prompt))

        # —— 重试循环：最多 3 次 ——
        # 策略：JSON 解析失败用短退避（1s, 2s），网络错误用长退避（2s, 4s）
        # 不可重试错误（如认证失败）直接跳出，不浪费时间
        for attempt in range(3):
            try:
                # 把带对话历史的消息列表发给 LLM，获取结构化评分 JSON
                score_result = llm.invoke(context_messages)
                raw = score_result.content.strip()

                # 清洗 markdown 代码围栏：LLM 经常把 JSON 包在 ```json ... ``` 里
                # 先去掉首行的 ```json 标记，再去掉末尾的 ```
                if raw.startswith("```"):
                    raw = raw.split("\n", 1)[-1]  # 去掉第一行（```json）
                    if raw.endswith("```"):
                        raw = raw[:-3]             # 去掉末尾 ```
                    raw = raw.strip()

                score_data = json.loads(raw)

                # —— 字段校验与钳制 ——
                # score 必须是数字且钳制到 [0, 10]
                if not isinstance(score_data.get("score"), (int, float)):
                    raise ValueError("score 字段缺失或类型不对")
                score_data["score"] = max(0, min(10, int(score_data["score"])))

                # dimensions：4 个维度逐个校验，缺失补 0，超范围钳制
                dims = score_data.get("dimensions", {})
                if not isinstance(dims, dict):
                    dims = {}
                for k in ("技术基础", "项目经验", "场景设计", "软技能"):
                    if k in dims:
                        dims[k] = max(0, min(10, int(dims[k])))
                    else:
                        dims[k] = 0
                score_data["dimensions"] = dims

                # confidence：缺失默认 5，钳制 [0, 10]
                conf = score_data.get("confidence", 5)
                if not isinstance(conf, (int, float)):
                    conf = 5
                score_data["confidence"] = max(0, min(10, int(conf)))

                # 记录对话历史，供后续评分参考
                # 后续题评分时 LLM 能看到之前每题的问答和得分，做整体趋势判断
                self._state.setdefault("messages", []).extend([
                    HumanMessage(content=f"题目: {question.get('question', '')}\n类别: {category}\n回答: {answer}"),
                    AIMessage(content=f"评分: {score_data.get('score', 5)}/10\n反馈: {score_data.get('feedback', '')}")
                ])
                return score_data

            except (json.JSONDecodeError, ValueError, KeyError) as e:
                # JSON 格式错误 — LLM 可能下次返回不同输出，值得重试
                logger.warning(f"评分 attempt {attempt+1}/3 JSON解析失败: {e}")
                if attempt < 2:
                    time.sleep(1.0 * (2 ** attempt))  # 指数退避：1s, 2s
            except Exception as e:
                # 网络/超时错误 — 判断是否可重试
                error_str = str(e).lower()
                if any(kw in error_str for kw in ("timeout", "connection", "api", "http")):
                    logger.warning(f"评分 attempt {attempt+1}/3 网络错误: {e}")
                    if attempt < 2:
                        time.sleep(2.0 * (2 ** attempt))  # 指数退避：2s, 4s
                else:
                    # 不可重试的错误（如认证失败），直接跳出，不浪费时间重试
                    logger.error(f"评分遇到不可重试错误: {e}")
                    break

        # —— 兜底：3 次重试全部失败，返回中性评分保证面试不中断 ——
        logger.error(f"评分最终失败，LLM 返回无法解析。兜底 score=5")
        fallback = {"score": 5, "dimensions": {"技术基础": 5, "项目经验": 5, "场景设计": 5, "软技能": 5},
                "feedback": "评分系统异常，请查看参考答案", "follow_up": "", "confidence": 1}
        # 兜底也记录对话历史，保持上下文连续性
        self._state.setdefault("messages", []).extend([
            HumanMessage(content=f"题目: {question.get('question', '')}\n类别: {category}\n回答: {answer}"),
            AIMessage(content="评分: 5/10（兜底）\n反馈: 评分系统异常")
        ])
        return fallback

    def _record_and_adjust(self, question: dict, score: int):
        """
        记录难度表现，必要时触发自适应难度调整。

        每次评分后把分数按难度分类存入 difficulty_stats。
        当已答 >= 3 题且剩余题 <= 2 时，调用 _check_difficulty_target() 判断
        是否需要生成不同难度的补充题来替换后续题目。
        """
        # 按题目难度分类记录得分，供 _check_difficulty_target() 判定趋势
        difficulty = question.get("difficulty", "medium")
        stats = self._state.setdefault("difficulty_stats", {"easy": [], "medium": [], "hard": []})
        stats.setdefault(difficulty, []).append(score)

        # 计算剩余题数，判断是否需要触发自适应难度
        questions = self._state.get("questions", [])
        next_idx = self._state.get("current_question_index", 0) + 1
        remaining = len(questions) - next_idx

        # 回答数 >= 3 且剩余不足 3 题时尝试调整难度
        # 设计意图：面试中后期有足够数据判断候选人水平，在剩余题量有限时及时调整
        answered = len(self._state.get("answers", []))
        if answered >= 3 and remaining <= 2:
            target = self._check_difficulty_target()
            # 目标难度与当前题目不同 -> 生成 2 道目标难度补充题追加到列表
            if target and target != difficulty:
                new_questions = self._generate_supplemental(target, count=2)
                if new_questions:
                    questions.extend(new_questions)
                    self._state["questions"] = questions

    def _check_difficulty_target(self) -> str:
        """
        自适应难度判定：根据最近 3 题均分决定目标难度。

        - 均分 >= 7.5：候选人表现优秀，后续出 harder 题（"hard"）
        - 均分 <= 4.0：候选人表现吃力，后续出 easier 题（"easy"）
        - 其他区间：保持当前难度不变（返回 None）
        - 总答题数 < 3：数据不足，不调整（返回 None）
        """
        # 从 difficulty_stats 收集所有难度的历史得分，展平为一个列表
        stats = self._state.get("difficulty_stats", {})
        all_scores = []
        for scores in stats.values():
            all_scores.extend(scores)
        # 答题数不足 3 题时数据量太少，不做难度调整
        if len(all_scores) < 3:
            return None
        # 只看最近 3 题的表现，避免早期分数过度影响判断
        recent = all_scores[-3:]
        avg = sum(recent) / len(recent)
        # 均分 >= 7.5 说明候选人水平较高，后续出更难的题以区分能力上限
        if avg >= 7.5:
            return "hard"
        # 均分 <= 4.0 说明当前难度偏高，降级出简单题避免打击信心
        elif avg <= 4.0:
            return "easy"
        # 4.0-7.5 之间为正常区间，维持当前难度不变
        return None

    def _generate_supplemental(self, target_difficulty: str, count: int = 2) -> list:
        """
        调用 LLM 生成指定难度的补充题目。

        触发场景：
        1. 自适应难度：_record_and_adjust() 检测到均分偏高/偏低，生成 harder/easier 题。
        2. 恢复面试时题目已答完：resume_analyze() 生成 medium 补充题延长面试。

        prompt 中注入 JD/简历/差距分析 + 已面试类别，让 LLM 关注候选人
        尚未展现的能力领域，避免重复出题。
        """
        from app.core.llm import get_fast_llm
        from langchain_core.messages import HumanMessage
        import json

        # 从会话状态提取上下文信息，拼入补充题生成 prompt
        jd_analysis = self._state.get("jd_analysis", {})
        gap_analysis = self._state.get("gap_analysis", {})
        existing = self._state.get("questions", [])
        # 提取已出题类别，prompt 中提示 LLM 避开重复方向，关注尚未考察的能力领域
        existing_categories = list(set(q.get("category", "") for q in existing))
        jd_content = self._state.get("jd_content", "")
        resume_content = self._state.get("resume_content", "")

        context = f"""
职位描述: {jd_content[:500] if jd_content else '无'}
简历内容: {resume_content[:500] if resume_content else '无'}
JD 分析: {json.dumps(jd_analysis, ensure_ascii=False)}
差距分析: {json.dumps(gap_analysis, ensure_ascii=False)}
已面试类别: {existing_categories}
目标难度: {target_difficulty}

请生成 {count} 道 {target_difficulty} 难度的面试题，重点关注候选人尚未展现的能力领域。
每道题按以下 JSON 格式：
{{"id": 序号, "category": "技术基础/项目经验/场景设计/软技能", "question": "题目",
  "purpose": "考察目的", "difficulty": "{target_difficulty}", "expected_answer_points": ["要点1", "要点2"]}}

以 JSON 数组返回，只返回 JSON。"""

        try:
            # 调用 LLM 生成补充题目，prompt 中包含 JD/简历/差距分析 + 已面试类别
            llm = get_fast_llm()
            result = llm.invoke([HumanMessage(content=context)])
            raw = result.content.strip()
            # 清洗 markdown 代码围栏（与 _score_answer 相同逻辑）
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1]
                if raw.endswith("```"):
                    raw = raw[:-3]
                raw = raw.strip()
            new_qs = json.loads(raw)
            # LLM 可能返回 {"questions": [...]} 而非纯数组，做兼容处理
            if isinstance(new_qs, dict) and "questions" in new_qs:
                new_qs = new_qs["questions"]
            if not isinstance(new_qs, list):
                return []
            # 调整 id 为连续编号，接续已有题目的最大 id
            start_id = len(existing) + 1
            for i, q in enumerate(new_qs):
                q["id"] = start_id + i
            logger.info(f"生成了 {len(new_qs)} 道 {target_difficulty} 补充题")
            return new_qs
        except Exception as e:
            # 生成失败返回空列表，调用方会跳过补充题
            logger.warning(f"生成补充题目失败: {e}")
            return []

    def _run_evaluation(self):
        """
        运行综合评估：聚合各维度均分 + 注入历史统计 + 调用评估节点。

        步骤：
        1. 遍历所有 answers，累加各维度得分，计算均分（10 分制 -> 100 分制）。
        2. 计算评分质量指标：
           - avg_confidence：LLM 自评的平均自信度
           - score_std_dev：所有题分的标准差，衡量评分一致性
           - follow_up_avg_improvement：追问后分数提升均值
        3. 从 stats_client 获取全局历史数据上下文，注入评估 prompt。
        4. 调用 evaluator_node 生成综合评估报告。
        5. 异常时构造兜底评估结果，保证流程不中断。
        """
        from app.agents.evaluator import evaluator_node
        from app.services.stats_client import stats_client
        try:
            # === 第一步：聚合各维度均分 ===
            # 遍历所有已答题，把 4 个维度的分累加，算均分后转成 100 分制
            answers = self._state.get("answers", [])
            dim_sums = {"技术基础": 0, "项目经验": 0, "场景设计": 0, "软技能": 0}
            dim_counts = {"技术基础": 0, "项目经验": 0, "场景设计": 0, "软技能": 0}
            for a in answers:
                dims = a.get("dimensions", {})
                for dim_name in dim_sums:
                    val = dims.get(dim_name, 0)
                    if val > 0:  # 只统计适用的维度（不适用的为 0）
                        dim_sums[dim_name] += val
                        dim_counts[dim_name] += 1
            aggregated_dimensions = []
            for dim_name in dim_sums:
                avg = round(dim_sums[dim_name] / dim_counts[dim_name]) if dim_counts[dim_name] > 0 else 0
                aggregated_dimensions.append({
                    "name": dim_name,
                    "score": avg * 10,  # 10 分制 -> 100 分制，便于前端展示
                    "sample_count": dim_counts[dim_name],
                })
            self._state["aggregated_dimensions"] = aggregated_dimensions

            # === 第二步：评分质量评估 ===
            # 这些指标帮助判断本次评分是否可信，是否需要人工复核
            confidences = [a.get("confidence", 5) for a in answers if a.get("confidence")]
            scores_list = [a.get("score", 5) for a in answers]
            # 有 original_score 的说明经历了追问，可用于计算改善率
            follow_up_scores = [a for a in answers if a.get("original_score") is not None]

            avg_confidence = round(sum(confidences) / len(confidences), 1) if confidences else 0
            # 标准差衡量评分一致性：std_dev 大说明评分波动大，可能需要人工复核
            mean_s = sum(scores_list) / len(scores_list) if scores_list else 5
            variance = sum((s - mean_s)**2 for s in scores_list) / len(scores_list) if scores_list else 0
            std_dev = round(variance ** 0.5, 1)

            # 追问改善率：追问后分数 - 追问前分数的均值
            if follow_up_scores:
                improvements = [(a["score"] - a["original_score"]) for a in follow_up_scores]
                avg_improvement = round(sum(improvements) / len(improvements), 1)
            else:
                avg_improvement = None

            self._state["scoring_quality"] = {
                "avg_confidence": avg_confidence,
                "score_std_dev": std_dev,
                "score_spread": round(max(scores_list) - min(scores_list), 1) if len(scores_list) > 1 else 0,
                "follow_up_avg_improvement": avg_improvement,
                "total_questions": len(answers),
            }

            # === 第三步：注入全局历史统计上下文 ===
            # 提供系统级历史数据（完成场数/均分/完成率/各类别分布），让评估节点有全局参照
            stats_context = stats_client.build_evaluation_context()
            if stats_context:
                self._state["stats_context"] = stats_context

            # === 第四步：调用评估节点生成综合报告 ===
            # evaluator_node 是 LangGraph 的评估节点，接收完整的 state（含 answers、
            # aggregated_dimensions、scoring_quality、stats_context），
            # 调用 LLM 生成总分、优劣势、改进建议、学习推荐等评估文本
            result = evaluator_node(self._state)
            self._state["evaluation"] = result.get("evaluation", {})
            self._state["phase"] = "done"
        except Exception as e:
            # 评估失败不丢失已有数据，构造兜底评估结果
            logger.error(f"评估失败: {e}", exc_info=True)
            self._state["evaluation"] = {
                "overall_score": 0,
                "dimensions": aggregated_dimensions if aggregated_dimensions else [],
                "improvement_suggestions": [f"评估生成失败，请查看各题评分。错误: {str(e)}"],
            }
            self._state["scoring_quality"] = {
                "avg_confidence": 0, "score_std_dev": 0,
                "score_spread": 0, "follow_up_avg_improvement": None,
                "total_questions": len(answers) if answers else 0,
                "error": str(e),
            }

    def get_result(self) -> dict:
        """获取面试评估结果，包含总分、各维度分、优劣势、改进建议、学习推荐及各题参考答案"""
        evaluation = self._state.get("evaluation", {})
        return {
            "session_id": self.session_id,
            "overall_score": evaluation.get("overall_score", 0),
            "dimensions": evaluation.get("dimensions", []),
            "strengths": evaluation.get("strengths", []),
            "weaknesses": evaluation.get("weaknesses", []),
            "improvement_suggestions": evaluation.get("improvement_suggestions", []),
            "recommended_learning": evaluation.get("recommended_learning", []),
            "answers": self._state.get("answers", []),
            "questions": self._state.get("questions", []),
            "scoring_quality": self._state.get("scoring_quality", {}),
        }

    def analyze_stream(self):
        """
        流式分析：yield 进度事件 dict，供 SSE 端点使用。

        与 analyze() 的区别：用 interview_graph.stream() 逐节点 yield，
        每完成一个图节点（jd_analyzer/resume_analyzer/gap_analyzer/question_generator）
        就推送一个 progress 事件，前端可实时展示分析进度。
        最后推送 complete 事件携带完整结果。
        """
        # 先推送一个 progress 事件，告知前端分析已开始
        yield {"event": "progress", "step": "jd_analysis", "message": "正在分析职位描述..."}

        # stream() 按图节点逐个返回 state 增量，而非一次性返回最终 state
        # 与 invoke() 的区别：invoke 等全部完成才返回，stream 每个节点完成后就 yield 一次
        for chunk in interview_graph.stream(self._state, {"recursion_limit": 50}):
            for node_name, state_update in chunk.items():
                # 把节点产出的增量字段合并回当前会话状态
                self._state.update(state_update)
                # 根据完成的节点推送对应进度事件
                if node_name == "jd_analyzer":
                    yield {"event": "progress", "step": "jd_analysis_done", "message": "职位描述分析完成"}
                elif node_name == "resume_analyzer":
                    yield {"event": "progress", "step": "resume_analysis_done", "message": "简历分析完成"}
                elif node_name == "gap_analyzer":
                    yield {"event": "progress", "step": "gap_analysis_done", "message": "差距分析完成"}
                elif node_name == "question_generator":
                    yield {"event": "progress", "step": "questions_ready", "message": "题目生成完成"}

        questions = self._state.get("questions", [])
        first_question = questions[0] if questions else None
        self._save()
        # 最终推送 complete 事件，携带完整分析结果
        yield {
            "event": "complete",
            "data": {
                "session_id": self.session_id,
                "phase": self._state.get("phase", "questions_ready"),
                "total_questions": len(questions),
                "current_question": first_question,
                "questions": questions,
                "jd_analysis": self._state.get("jd_analysis", {}),
                "gap_analysis": self._state.get("gap_analysis", {}),
            }
        }

    def submit_answer_stream(self, answer: str):
        """
        流式提交答案：yield 进度事件 dict。

        先推送 scoring progress 事件，再调用同步 submit_answer() 完成评分。
        根据结果推送 scored（继续答题）或 complete（面试完成）事件。
        """
        # 先推送 scoring progress 事件，告知前端正在评分
        yield {"event": "progress", "step": "scoring", "message": "正在评分..."}

        # 复用同步 submit_answer 逻辑，保证流式与非流式行为一致
        # 评分本身是同步阻塞的（调用 LLM），SSE 层只负责推送进度和最终结果
        result = self.submit_answer(answer)

        # phase=done 说明面试已结束（最后一题答完触发了综合评估），推送 complete 事件
        if result.get("phase") == "done":
            yield {"event": "complete", "data": result}
        # 其他 phase（continue/follow_up）推送 scored 事件，前端据此展示下一题或追问
        else:
            yield {"event": "scored", "data": result}

    def get_current_question(self) -> dict:
        """
        获取当前题目状态（不提交答案），用于页面刷新恢复。

        三种返回场景：
        - 有 pending_follow_up：返回 follow_up 阶段，前端展示追问
        - 题目已答完：返回 done
        - 正常：返回当前待答题目
        """
        questions = self._state.get("questions", [])
        current_idx = self._state.get("current_question_index", 0)
        pending = self._state.get("pending_follow_up")

        if pending:
            return {
                "session_id": self.session_id,
                "phase": "follow_up",
                "follow_up_question": pending.get("question", ""),
                "question_index": current_idx,
                "total_questions": len(questions),
                "answered_count": current_idx,
            }

        if current_idx >= len(questions):
            return {"session_id": self.session_id, "phase": "done", "message": "所有题目已答完"}

        return {
            "session_id": self.session_id,
            "phase": "continue",
            "current_question": questions[current_idx],
            "total_questions": len(questions),
            "answered_count": current_idx,
            "current_question_index": current_idx,
        }


# 模块级单例：服务启动时初始化，全局共享同一个会话存储
session_store = InterviewSessionStore()
