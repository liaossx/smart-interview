package com.smartinterview.api.controller;

import com.smartinterview.common.ApiResponse;
import com.smartinterview.domain.service.QAService;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/api/v1/sessions/{sessionId}/qas")
public class QAController {

    private final QAService qaService;

    public QAController(QAService qaService) {
        this.qaService = qaService;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public ApiResponse<?> create(@PathVariable Long sessionId, @RequestBody Map<String, Object> body,
                                 HttpServletRequest req) {
        Long userId = (Long) req.getAttribute("userId");
        String question = (String) body.getOrDefault("question", "");
        String category = (String) body.getOrDefault("category", "");
        String answer = (String) body.getOrDefault("answer", "");
        Integer score = body.get("score") != null ? Integer.valueOf(body.get("score").toString()) : 0;
        String feedback = (String) body.getOrDefault("feedback", "");
        String expectedAnswer = (String) body.getOrDefault("expectedAnswer", "");
        return ApiResponse.success(qaService.create(sessionId, question, category, answer, score, feedback, expectedAnswer, userId));
    }

    @GetMapping
    public ApiResponse<?> listBySession(@PathVariable Long sessionId, HttpServletRequest req) {
        Long userId = (Long) req.getAttribute("userId");
        return ApiResponse.success(qaService.listBySession(sessionId, userId));
    }
}
