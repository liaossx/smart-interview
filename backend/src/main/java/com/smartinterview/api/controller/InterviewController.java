package com.smartinterview.api.controller;

import com.smartinterview.data.entity.JD;
import com.smartinterview.data.entity.QA;
import com.smartinterview.data.entity.Resume;
import com.smartinterview.data.entity.Session;
import com.smartinterview.data.repository.JDRepository;
import com.smartinterview.data.repository.QARepository;
import com.smartinterview.data.repository.ResumeRepository;
import com.smartinterview.data.repository.SessionRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.*;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.multipart.MultipartFile;

import java.util.*;

/**
 * 面试流程控制器 —— Java 与 Python AI 服务之间的桥接层（代理层）。
 * <p>
 * 本控制器不直接处理 AI 逻辑，而是将前端请求转发给 Python AI 服务（FastAPI）。
 * 架构链路：前端 → InterviewController（Java）→ Python AI Service（FastAPI）
 * <p>
 * 职责：
 * <ul>
 *   <li>从数据库读取面试会话状态（JD、简历、QA 列表），直接返回给前端</li>
 *   <li>将面试核心流程（开始面试、提交回答、恢复面试、获取结果）代理转发至 Python AI 服务</li>
 *   <li>将简历文件转发给 Python 端进行解析</li>
 * </ul>
 * <p>
 * 注意：当前使用 RestTemplate 进行同步 HTTP 转发，不支持 SSE 流式传输。
 * 若未来需要流式 AI 回复，需改用 WebClient 或手动写入 SseEmitter。
 * <p>
 * 详见 AI链路学习路径.md 第八步
 */
@RestController
@RequestMapping("/api/v1")
public class InterviewController {

    /** 用于向 Python AI 服务发起 HTTP 请求的同步客户端 */
    private final RestTemplate restTemplate;
    private final SessionRepository sessionRepository;
    private final JDRepository jdRepository;
    private final ResumeRepository resumeRepository;
    private final QARepository qaRepository;
    /** Python AI 服务的基础 URL，来自配置项 ai.service-url，默认指向本地 FastAPI 实例 */
    private final String aiBaseUrl;

    /**
     * 构造函数，初始化 RestTemplate 并注入各 Repository。
     *
     * @param aiBaseUrl 配置项 {@code ai.service-url}，指向 Python AI 服务地址。
     *                  开发环境默认为 http://127.0.0.1:8001/api/v1
     */
    public InterviewController(SessionRepository sessionRepository, JDRepository jdRepository,
                               ResumeRepository resumeRepository, QARepository qaRepository,
                               @Value("${ai.service-url:http://127.0.0.1:8001/api/v1}") String aiBaseUrl) {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(5000);   // 连接超时 5 秒：快速失败，避免长时间等待 Python 服务启动
        factory.setReadTimeout(60000);     // 读取超时 60 秒：LLM 推理耗时较长（生成面试问题、评分反馈），需留足等待时间
        this.restTemplate = new RestTemplate(factory);
        this.sessionRepository = sessionRepository;
        this.jdRepository = jdRepository;
        this.resumeRepository = resumeRepository;
        this.qaRepository = qaRepository;
        this.aiBaseUrl = aiBaseUrl;
    }

    /**
     * 获取面试会话状态（不经过 Python，直接读数据库）。
     * 前端用于恢复页面状态：JD 内容、简历文本、已有 QA 列表、题目列表等。
     * 此接口纯 Java 侧实现，无需调用 AI 服务。
     */
    @GetMapping("/interview/state/{sessionId}")
    public ResponseEntity<?> getSessionState(@PathVariable Long sessionId, HttpServletRequest req) {
        Long userId = (Long) req.getAttribute("userId");
        Session session = sessionRepository.findById(sessionId).orElse(null);
        if (session == null || !session.getUserId().equals(userId)) {
            return ResponseEntity.status(404).body("{\"code\":404,\"message\":\"会话不存在\",\"data\":null}");
        }

        Map<String, Object> state = new LinkedHashMap<>();
        state.put("sessionId", session.getId());
        state.put("status", session.getStatus().name());

        // JD content
        if (session.getJdId() != null) {
            jdRepository.findById(session.getJdId())
                    .ifPresent(jd -> state.put("jdContent", jd.getContent()));
        }

        // Resume parsed text
        if (session.getResumeId() != null) {
            resumeRepository.findById(session.getResumeId())
                    .ifPresent(resume -> state.put("resumeContent",
                            resume.getParsedText() != null ? resume.getParsedText() : ""));
        }

        // QA list
        List<QA> qas = qaRepository.findBySessionIdOrderByCreatedAtAsc(sessionId);
        List<Map<String, Object>> qaList = new ArrayList<>();
        for (QA qa : qas) {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("question", qa.getQuestion());
            m.put("category", qa.getCategory());
            m.put("answer", qa.getAnswer());
            m.put("score", qa.getScore());
            m.put("feedback", qa.getFeedback());
            m.put("followUpQuestion", qa.getFollowUpQuestion());
            qaList.add(m);
        }
        state.put("qas", qaList);
        state.put("currentQuestionIndex", qas.size());

        // Questions list (saved when interview started)
        String questionsJson = session.getQuestionsJson();
        if (questionsJson != null && !questionsJson.isEmpty()) {
            try {
                ObjectMapper mapper = new ObjectMapper();
                state.put("questions", mapper.readTree(questionsJson));
            } catch (Exception e) {
                state.put("questions", null);
            }
        } else {
            state.put("questions", null);
        }

        return ResponseEntity.ok(state);
    }

    /**
     * 恢复面试会话 —— 代理转发至 Python AI 服务的 /interview/restore 接口。
     * Python 端会根据会话历史重建对话上下文（LLM memory）。
     */
    @PostMapping("/interview/restore")
    public ResponseEntity<?> restoreInterview(@RequestBody Map<String, Object> body,
                                              HttpServletRequest req) {
        Long userId = (Long) req.getAttribute("userId");
        body.put("user_id", userId);
        return proxy(aiBaseUrl + "/interview/restore", HttpMethod.POST, body, null);
    }

    /**
     * 开始面试 —— 代理转发至 Python AI 服务的 /interview/start 接口。
     * Python 端会根据 JD + 简历，调用 LLM 生成面试题目列表。
     */
    @PostMapping("/interview/start")
    public ResponseEntity<?> startInterview(@RequestBody Map<String, Object> body,
                                            HttpServletRequest req) {
        Long userId = (Long) req.getAttribute("userId");
        body.put("user_id", userId);
        return proxy(aiBaseUrl + "/interview/start", HttpMethod.POST, body, null);
    }

    /**
     * 提交回答 —— 代理转发至 Python AI 服务的 /interview/answer 接口。
     * Python 端会调用 LLM 对用户回答进行评分 + 生成反馈 + 决定追问。
     */
    @PostMapping("/interview/answer")
    public ResponseEntity<?> submitAnswer(@RequestBody Map<String, Object> body,
                                          HttpServletRequest req) {
        Long userId = (Long) req.getAttribute("userId");
        body.put("user_id", userId);
        return proxy(aiBaseUrl + "/interview/answer", HttpMethod.POST, body, null);
    }

    /**
     * 获取面试结果报告 —— 代理转发至 Python AI 服务的 /interview/result/{sessionId} 接口。
     * Python 端汇总全部 QA 评分，调用 LLM 生成综合评价报告。
     */
    @GetMapping("/interview/result/{sessionId}")
    public ResponseEntity<?> getResult(@PathVariable String sessionId,
                                       HttpServletRequest req) {
        Long userId = (Long) req.getAttribute("userId");
        String url = aiBaseUrl + "/interview/result/" + sessionId + "?user_id=" + userId;
        return proxy(url, HttpMethod.GET, null, null);
    }

    /**
     * 简历解析 —— 将上传的文件以 multipart 形式转发至 Python AI 服务的 /resume/parse 接口。
     * Python 端使用 OCR / 文本提取 + LLM 结构化解析，返回 JSON 格式的简历字段。
     * 注意：此处未走通用 proxy() 方法，因为需要处理 multipart 请求体。
     */
    @PostMapping("/resume/parse")
    public ResponseEntity<?> parseResume(@RequestParam("file") MultipartFile file,
                                         HttpServletRequest req) {
        try {
            var headers = new HttpHeaders();
            headers.setContentType(MediaType.MULTIPART_FORM_DATA);

            var body = new org.springframework.util.LinkedMultiValueMap<String, Object>();
            body.add("file", file.getResource());

            var entity = new HttpEntity<>(body, headers);
            var resp = restTemplate.exchange(aiBaseUrl + "/resume/parse", HttpMethod.POST, entity, String.class);
            return ResponseEntity.status(resp.getStatusCode()).body(resp.getBody());
        } catch (Exception e) {
            return ResponseEntity.status(502).body(
                    "{\"code\":502,\"message\":\"AI service unavailable\",\"data\":null}");
        }
    }

    /**
     * 通用代理方法：将请求转发至 Python AI 服务，并原样返回响应。
     * <p>
     * 逻辑：
     * <ol>
     *   <li>构造 JSON 请求头，可选附加额外头</li>
     *   <li>使用 RestTemplate 发起同步 HTTP 请求</li>
     *   <li>透传 Python 返回的状态码和响应体</li>
     *   <li>若 Python 服务不可达或超时，返回 502 Bad Gateway</li>
     * </ol>
     * <p>
     * 注意：RestTemplate 是同步阻塞客户端，不支持 SSE 流式传输。
     * 当前所有 AI 接口均以 JSON 请求/响应模式工作。
     * 若后续需要流式回复（如逐字输出 LLM 回答），需改用 WebClient 或 SseEmitter。
     *
     * @param url          目标 Python AI 服务 URL
     * @param method       HTTP 方法（GET / POST 等）
     * @param body         请求体，null 表示无请求体
     * @param extraHeaders 额外请求头，null 表示无
     * @return 透传的 Python 响应，或 502 错误
     */
    private ResponseEntity<?> proxy(String url, HttpMethod method, Object body, HttpHeaders extraHeaders) {
        try {
            var headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);
            if (extraHeaders != null) headers.addAll(extraHeaders);

            var entity = body != null ? new HttpEntity<>(body, headers) : new HttpEntity<>(headers);
            var resp = restTemplate.exchange(url, method, entity, String.class);
            // 透传 Python 服务返回的状态码与响应体
            return ResponseEntity.status(resp.getStatusCode()).body(resp.getBody());
        } catch (Exception e) {
            // Python 服务不可达 / 超时 / 连接拒绝 → 返回 502，前端据此提示"AI 服务不可用"
            System.err.println("[proxy] ERROR calling " + url + ": " + e.getClass().getSimpleName() + " - " + e.getMessage());
            return ResponseEntity.status(502).body(
                    "{\"code\":502,\"message\":\"AI service unavailable\",\"data\":null}");
        }
    }
}
