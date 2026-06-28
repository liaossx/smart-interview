"""面试服务：管理面试会话状态"""

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
    """DB + 内存混合会话存储，支持服务重启后恢复"""

    def __init__(self, persist_dir: str = None):
        self._sessions: Dict[str, InterviewState] = {}
        self._db_engine = None
        self._init_db()
        self._load_all()

    def _init_db(self):
        """初始化数据库连接和 ai_sessions 表"""
        try:
            from sqlalchemy import create_engine, text
            from app.core.config import get_settings
            settings = get_settings()
            self._db_engine = create_engine(
                settings.database_url,
                pool_pre_ping=True,
                pool_size=5,
                pool_recycle=3600,
            )
            with self._db_engine.connect() as conn:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS ai_sessions (
                        session_id VARCHAR(36) PRIMARY KEY,
                        state JSON,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                    )
                """))
                conn.execute(text(
                    "DELETE FROM ai_sessions WHERE updated_at < DATE_SUB(NOW(), INTERVAL 24 HOUR)"
                ))
                conn.commit()
            logger.info("AI session DB initialized")
        except Exception as e:
            logger.warning(f"DB初始化失败，降级为纯内存模式: {e}")
            self._db_engine = None

    def _serialize_state(self, state: dict) -> dict:
        """序列化 state 为可 JSON 化的 dict"""
        serializable = {}
        for k, v in state.items():
            if k == "messages":
                serializable[k] = [
                    {"role": getattr(m, "type", "unknown"), "content": getattr(m, "content", "")}
                    for m in v
                ]
            else:
                try:
                    json.dumps(v)
                    serializable[k] = v
                except (TypeError, ValueError):
                    serializable[k] = str(v) if v is not None else None
        return serializable

    def _save_one(self, session_id: str):
        state = self._sessions.get(session_id)
        if not state or not self._db_engine:
            return
        try:
            from sqlalchemy import text
            serializable = self._serialize_state(state)
            with self._db_engine.connect() as conn:
                conn.execute(text("""
                    INSERT INTO ai_sessions (session_id, state)
                    VALUES (:sid, :state)
                    ON DUPLICATE KEY UPDATE state = :state, updated_at = NOW()
                """), {"sid": session_id, "state": json.dumps(serializable, ensure_ascii=False)})
                conn.commit()
        except Exception as e:
            logger.warning(f"持久化会话 {session_id} 失败: {e}")

    def _load_all(self):
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
                    # 恢复对话历史
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
            logger.warning(f"从DB加载会话失败: {e}")

    def create(self, jd_content: str, resume_content: str = "", user_id: int = 1) -> "InterviewSession":
        session_id = str(uuid.uuid4())[:8]
        state: InterviewState = {
            "messages": [],
            "user_id": user_id,
            "session_id": session_id,
            "jd_content": jd_content,
            "resume_content": resume_content,
            "jd_analysis": {},
            "resume_analysis": {},
            "gap_analysis": {},
            "questions": [],
            "current_question_index": 0,
            "answers": [],
            "evaluation": {},
            "stats_context": "",
            "pending_follow_up": {},
            "difficulty_stats": {"easy": [], "medium": [], "hard": []},
            "supplemental_questions": [],
            "iteration_count": 0,
            "phase": "init",
        }
        self._sessions[session_id] = state
        return InterviewSession(session_id, state, self._sessions, self)

    def restore(self, jd_content: str, resume_content: str, qas: list,
                current_question_index: int = 0, user_id: int = 1,
                existing_session_id: str = None,
                questions: list = None) -> "InterviewSession":
        """从后端 MySQL 数据重建面试状态"""
        session_id = existing_session_id or str(uuid.uuid4())[:8]

        # 如果传入了完整题目列表，直接使用；否则从 qas 重建
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

        # 从已答题目提取类别，用于生成后续题目
        categories_seen = list(set(a.get("category", "") for a in answers if a.get("category")))

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
            "phase": "questions_ready",
        }
        self._sessions[session_id] = state
        self._save_one(session_id)
        return InterviewSession(session_id, state, self._sessions, self)

    def get(self, session_id: str) -> Optional["InterviewSession"]:
        state = self._sessions.get(session_id)
        if not state:
            return None
        return InterviewSession(session_id, state, self._sessions, self)

    def remove(self, session_id: str):
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
    """单个面试会话的操作封装"""

    def __init__(self, session_id: str, state: InterviewState, store: Dict, store_manager: InterviewSessionStore = None):
        self.session_id = session_id
        self._state = state
        self._store = store
        self._store_manager = store_manager

    def _save(self):
        self._store[self.session_id] = self._state
        if self._store_manager:
            self._store_manager._save_one(self.session_id)

    def analyze(self) -> dict:
        """运行分析阶段：JD分析 → 简历分析 → 差距分析 → 出题"""
        result = interview_graph.invoke(
            self._state,
            {"recursion_limit": 50},
        )
        self._state.update(result)

        questions = result.get("questions", [])
        first_question = questions[0] if questions else None

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
        """恢复模式：跳过分析，直接从已有题目继续"""
        questions = self._state.get("questions", [])
        current_idx = self._state.get("current_question_index", 0)
        total = len(questions)

        if current_idx >= total:
            # 没有更多题目，尝试生成补充题
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
        """根据已有进度，生成剩余题目（用于恢复面试）"""
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
        """提交答案并返回下一题、追问或评估结果"""
        current_idx = self._state.get("current_question_index", 0)
        questions = self._state.get("questions", [])

        if current_idx >= len(questions):
            return {"phase": "done", "message": "所有题目已答完"}

        question = questions[current_idx]
        pending = self._state.get("pending_follow_up")

        # —— 追问回答流程 ——
        if pending:
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
                "original_score": pending.get("score_so_far", 0),
            })

            self._record_and_adjust(question, score_data.get("score", 5))

            self._state["pending_follow_up"] = {}
            next_idx = current_idx + 1
            self._state["current_question_index"] = next_idx

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
        score_data = self._score_answer(question, answer)
        follow_up_text = score_data.get("follow_up", "").strip()
        score = score_data.get("score", 5)

        # 评分 < 7 且 LLM 给出了追问 → 触发追问
        if score < 7 and follow_up_text:
            self._state["pending_follow_up"] = {
                "question": follow_up_text,
                "original_answer": answer,
                "score_so_far": score,
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

        # 无追问 → 正常保存并推进
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

        self._record_and_adjust(question, score_data.get("score", 5))

        next_idx = current_idx + 1
        self._state["current_question_index"] = next_idx

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
        """评分单道回答，含重试、统计参照和 JSON 修复"""
        from app.core.llm import get_fast_llm
        from app.services.stats_client import stats_client
        llm = get_fast_llm()

        category = question.get('category', '')
        stats_context = stats_client.build_scoring_context(category) if category else ""

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
        context_messages = list(self._state.get("messages", []))
        context_messages.append(HumanMessage(content=score_prompt))

        for attempt in range(3):
            try:
                score_result = llm.invoke(context_messages)
                raw = score_result.content.strip()
                if raw.startswith("```"):
                    raw = raw.split("\n", 1)[-1]
                    if raw.endswith("```"):
                        raw = raw[:-3]
                    raw = raw.strip()
                score_data = json.loads(raw)
                if not isinstance(score_data.get("score"), (int, float)):
                    raise ValueError("score 字段缺失或类型不对")
                score_data["score"] = max(0, min(10, int(score_data["score"])))
                # 校验 dimensions
                dims = score_data.get("dimensions", {})
                if not isinstance(dims, dict):
                    dims = {}
                for k in ("技术基础", "项目经验", "场景设计", "软技能"):
                    if k in dims:
                        dims[k] = max(0, min(10, int(dims[k])))
                    else:
                        dims[k] = 0
                score_data["dimensions"] = dims
                # 校验 confidence
                conf = score_data.get("confidence", 5)
                if not isinstance(conf, (int, float)):
                    conf = 5
                score_data["confidence"] = max(0, min(10, int(conf)))
                # 记录对话历史，供后续评分参考
                self._state.setdefault("messages", []).extend([
                    HumanMessage(content=f"题目: {question.get('question', '')}\n类别: {category}\n回答: {answer}"),
                    AIMessage(content=f"评分: {score_data.get('score', 5)}/10\n反馈: {score_data.get('feedback', '')}")
                ])
                return score_data
            except (json.JSONDecodeError, ValueError, KeyError) as e:
                # JSON 格式错误 — LLM 可能下次返回不同输出，值得重试
                logger.warning(f"评分 attempt {attempt+1}/3 JSON解析失败: {e}")
                if attempt < 2:
                    time.sleep(1.0 * (2 ** attempt))  # 1s, 2s
            except Exception as e:
                # 网络/超时错误 — 判断是否可重试
                error_str = str(e).lower()
                if any(kw in error_str for kw in ("timeout", "connection", "api", "http")):
                    logger.warning(f"评分 attempt {attempt+1}/3 网络错误: {e}")
                    if attempt < 2:
                        time.sleep(2.0 * (2 ** attempt))  # 2s, 4s
                else:
                    # 不可重试的错误（如认证失败），直接跳出
                    logger.error(f"评分遇到不可重试错误: {e}")
                    break

        logger.error(f"评分最终失败，LLM 返回无法解析。兜底 score=5")
        fallback = {"score": 5, "dimensions": {"技术基础": 5, "项目经验": 5, "场景设计": 5, "软技能": 5},
                "feedback": "评分系统异常，请查看参考答案", "follow_up": "", "confidence": 1}
        # 兜底也记录对话历史
        self._state.setdefault("messages", []).extend([
            HumanMessage(content=f"题目: {question.get('question', '')}\n类别: {category}\n回答: {answer}"),
            AIMessage(content="评分: 5/10（兜底）\n反馈: 评分系统异常")
        ])
        return fallback

    def _record_and_adjust(self, question: dict, score: int):
        """记录难度表现，必要时生成补充题目"""
        difficulty = question.get("difficulty", "medium")
        stats = self._state.setdefault("difficulty_stats", {"easy": [], "medium": [], "hard": []})
        stats.setdefault(difficulty, []).append(score)

        questions = self._state.get("questions", [])
        next_idx = self._state.get("current_question_index", 0) + 1
        remaining = len(questions) - next_idx

        # 回答数 >= 3 且剩余不足 3 题时尝试调整
        answered = len(self._state.get("answers", []))
        if answered >= 3 and remaining <= 2:
            target = self._check_difficulty_target()
            if target and target != difficulty:
                new_questions = self._generate_supplemental(target, count=2)
                if new_questions:
                    questions.extend(new_questions)
                    self._state["questions"] = questions

    def _check_difficulty_target(self) -> str:
        """根据最近成绩判断目标难度。返回 easy / medium / hard 或 None"""
        stats = self._state.get("difficulty_stats", {})
        all_scores = []
        for scores in stats.values():
            all_scores.extend(scores)
        if len(all_scores) < 3:
            return None
        recent = all_scores[-3:]
        avg = sum(recent) / len(recent)
        if avg >= 7.5:
            return "hard"
        elif avg <= 4.0:
            return "easy"
        return None

    def _generate_supplemental(self, target_difficulty: str, count: int = 2) -> list:
        """调用 LLM 生成指定难度的补充题目"""
        from app.core.llm import get_fast_llm
        from langchain_core.messages import HumanMessage
        import json

        jd_analysis = self._state.get("jd_analysis", {})
        gap_analysis = self._state.get("gap_analysis", {})
        existing = self._state.get("questions", [])
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
            llm = get_fast_llm()
            result = llm.invoke([HumanMessage(content=context)])
            raw = result.content.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1]
                if raw.endswith("```"):
                    raw = raw[:-3]
                raw = raw.strip()
            new_qs = json.loads(raw)
            if isinstance(new_qs, dict) and "questions" in new_qs:
                new_qs = new_qs["questions"]
            if not isinstance(new_qs, list):
                return []
            # 调整 id 为连续编号
            start_id = len(existing) + 1
            for i, q in enumerate(new_qs):
                q["id"] = start_id + i
            logger.info(f"生成了 {len(new_qs)} 道 {target_difficulty} 补充题")
            return new_qs
        except Exception as e:
            logger.warning(f"生成补充题目失败: {e}")
            return []

    def _run_evaluation(self):
        """运行评估 Agent，聚合每道题的维度分作为输入"""
        from app.agents.evaluator import evaluator_node
        from app.services.stats_client import stats_client
        try:
            # 从所有答案中聚合维度均分
            answers = self._state.get("answers", [])
            dim_sums = {"技术基础": 0, "项目经验": 0, "场景设计": 0, "软技能": 0}
            dim_counts = {"技术基础": 0, "项目经验": 0, "场景设计": 0, "软技能": 0}
            for a in answers:
                dims = a.get("dimensions", {})
                for dim_name in dim_sums:
                    val = dims.get(dim_name, 0)
                    if val > 0:
                        dim_sums[dim_name] += val
                        dim_counts[dim_name] += 1
            aggregated_dimensions = []
            for dim_name in dim_sums:
                avg = round(dim_sums[dim_name] / dim_counts[dim_name]) if dim_counts[dim_name] > 0 else 0
                aggregated_dimensions.append({
                    "name": dim_name,
                    "score": avg * 10,  # 10 分制 → 100 分制
                    "sample_count": dim_counts[dim_name],
                })
            self._state["aggregated_dimensions"] = aggregated_dimensions

            # === 评分质量评估 ===
            confidences = [a.get("confidence", 5) for a in answers if a.get("confidence")]
            scores_list = [a.get("score", 5) for a in answers]
            follow_up_scores = [a for a in answers if a.get("original_score") is not None]

            avg_confidence = round(sum(confidences) / len(confidences), 1) if confidences else 0
            # 标准差衡量评分一致性
            mean_s = sum(scores_list) / len(scores_list) if scores_list else 5
            variance = sum((s - mean_s)**2 for s in scores_list) / len(scores_list) if scores_list else 0
            std_dev = round(variance ** 0.5, 1)

            # 追问改善率
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

            stats_context = stats_client.build_evaluation_context()
            if stats_context:
                self._state["stats_context"] = stats_context
            result = evaluator_node(self._state)
            self._state["evaluation"] = result.get("evaluation", {})
            self._state["phase"] = "done"
        except Exception as e:
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
        """获取面试结果"""
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
            "scoring_quality": self._state.get("scoring_quality", {}),
        }

    def analyze_stream(self):
        """流式分析：yield 进度事件 dict，供 SSE 端点使用"""
        yield {"event": "progress", "step": "jd_analysis", "message": "正在分析职位描述..."}

        for chunk in interview_graph.stream(self._state, {"recursion_limit": 50}):
            for node_name, state_update in chunk.items():
                self._state.update(state_update)
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
        """流式提交答案：yield 进度事件 dict"""
        yield {"event": "progress", "step": "scoring", "message": "正在评分..."}

        result = self.submit_answer(answer)

        if result.get("phase") == "done":
            yield {"event": "complete", "data": result}
        else:
            yield {"event": "scored", "data": result}

    def get_current_question(self) -> dict:
        """获取当前题目状态（不提交答案），用于页面刷新恢复"""
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


session_store = InterviewSessionStore()
