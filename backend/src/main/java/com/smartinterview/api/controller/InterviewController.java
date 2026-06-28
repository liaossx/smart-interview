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

@RestController
@RequestMapping("/api/v1")
public class InterviewController {

    private final RestTemplate restTemplate;
    private final SessionRepository sessionRepository;
    private final JDRepository jdRepository;
    private final ResumeRepository resumeRepository;
    private final QARepository qaRepository;
    private final String aiBaseUrl;

    public InterviewController(SessionRepository sessionRepository, JDRepository jdRepository,
                               ResumeRepository resumeRepository, QARepository qaRepository,
                               @Value("${ai.service-url:http://127.0.0.1:8001/api/v1}") String aiBaseUrl) {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(5000);   // 5 秒连接超时
        factory.setReadTimeout(60000);     // 60 秒读取超时（AI 调用可能较慢）
        this.restTemplate = new RestTemplate(factory);
        this.sessionRepository = sessionRepository;
        this.jdRepository = jdRepository;
        this.resumeRepository = resumeRepository;
        this.qaRepository = qaRepository;
        this.aiBaseUrl = aiBaseUrl;
    }

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

    @PostMapping("/interview/restore")
    public ResponseEntity<?> restoreInterview(@RequestBody Map<String, Object> body,
                                              HttpServletRequest req) {
        Long userId = (Long) req.getAttribute("userId");
        body.put("user_id", userId);
        return proxy(aiBaseUrl + "/interview/restore", HttpMethod.POST, body, null);
    }

    @PostMapping("/interview/start")
    public ResponseEntity<?> startInterview(@RequestBody Map<String, Object> body,
                                            HttpServletRequest req) {
        Long userId = (Long) req.getAttribute("userId");
        body.put("user_id", userId);
        return proxy(aiBaseUrl + "/interview/start", HttpMethod.POST, body, null);
    }

    @PostMapping("/interview/answer")
    public ResponseEntity<?> submitAnswer(@RequestBody Map<String, Object> body,
                                          HttpServletRequest req) {
        Long userId = (Long) req.getAttribute("userId");
        body.put("user_id", userId);
        return proxy(aiBaseUrl + "/interview/answer", HttpMethod.POST, body, null);
    }

    @GetMapping("/interview/result/{sessionId}")
    public ResponseEntity<?> getResult(@PathVariable String sessionId,
                                       HttpServletRequest req) {
        Long userId = (Long) req.getAttribute("userId");
        String url = aiBaseUrl + "/interview/result/" + sessionId + "?user_id=" + userId;
        return proxy(url, HttpMethod.GET, null, null);
    }

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

    private ResponseEntity<?> proxy(String url, HttpMethod method, Object body, HttpHeaders extraHeaders) {
        try {
            var headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);
            if (extraHeaders != null) headers.addAll(extraHeaders);

            var entity = body != null ? new HttpEntity<>(body, headers) : new HttpEntity<>(headers);
            var resp = restTemplate.exchange(url, method, entity, String.class);
            return ResponseEntity.status(resp.getStatusCode()).body(resp.getBody());
        } catch (Exception e) {
            return ResponseEntity.status(502).body(
                    "{\"code\":502,\"message\":\"AI service unavailable\",\"data\":null}");
        }
    }
}
