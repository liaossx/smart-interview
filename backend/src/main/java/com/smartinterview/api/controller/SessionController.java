package com.smartinterview.api.controller;

import com.smartinterview.api.dto.SessionCreateRequest;
import com.smartinterview.common.ApiResponse;
import com.smartinterview.data.entity.Session;
import com.smartinterview.domain.service.SessionService;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/sessions")
public class SessionController {

    private final SessionService sessionService;

    public SessionController(SessionService sessionService) {
        this.sessionService = sessionService;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public ApiResponse<?> create(@Valid @RequestBody SessionCreateRequest request,
                                 HttpServletRequest req) {
        Long userId = (Long) req.getAttribute("userId");
        return ApiResponse.success(sessionService.create(userId, request));
    }

    @GetMapping
    public ApiResponse<?> list(HttpServletRequest req) {
        Long userId = (Long) req.getAttribute("userId");
        return ApiResponse.success(sessionService.listByUser(userId));
    }

    @GetMapping("/{id}")
    public ApiResponse<?> getById(@PathVariable Long id, HttpServletRequest req) {
        Long userId = (Long) req.getAttribute("userId");
        return ApiResponse.success(sessionService.getById(id, userId));
    }

    @PutMapping("/{id}/score")
    public ApiResponse<?> updateScore(@PathVariable Long id, @RequestBody java.util.Map<String, Integer> body,
                                       HttpServletRequest req) {
        Long userId = (Long) req.getAttribute("userId");
        sessionService.updateScore(id, body.get("score"), userId);
        return ApiResponse.success(null);
    }

    @PutMapping("/{id}/status")
    public ApiResponse<?> updateStatus(@PathVariable Long id, @RequestBody java.util.Map<String, String> body,
                                        HttpServletRequest req) {
        Long userId = (Long) req.getAttribute("userId");
        sessionService.updateStatus(id, Session.Status.valueOf(body.get("status")), userId);
        return ApiResponse.success(null);
    }

    @PutMapping("/{id}/questions")
    public ApiResponse<?> saveQuestions(@PathVariable Long id, @RequestBody java.util.Map<String, Object> body,
                                         HttpServletRequest req) {
        Long userId = (Long) req.getAttribute("userId");
        sessionService.saveQuestions(id, body.get("questions"), userId);
        return ApiResponse.success(null);
    }

    @DeleteMapping("/{id}")
    public ApiResponse<?> delete(@PathVariable Long id, HttpServletRequest req) {
        Long userId = (Long) req.getAttribute("userId");
        sessionService.deleteSession(id, userId);
        return ApiResponse.success(null);
    }
}
