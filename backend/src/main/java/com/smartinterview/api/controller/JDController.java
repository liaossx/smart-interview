package com.smartinterview.api.controller;

import com.smartinterview.api.dto.JDCreateRequest;
import com.smartinterview.common.ApiResponse;
import com.smartinterview.domain.service.JDService;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/jds")
public class JDController {

    private final JDService jdService;

    public JDController(JDService jdService) {
        this.jdService = jdService;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public ApiResponse<?> create(@Valid @RequestBody JDCreateRequest request,
                                 HttpServletRequest req) {
        Long userId = (Long) req.getAttribute("userId");
        return ApiResponse.success(jdService.create(userId, request));
    }

    @GetMapping
    public ApiResponse<?> list(HttpServletRequest req) {
        Long userId = (Long) req.getAttribute("userId");
        return ApiResponse.success(jdService.listByUser(userId));
    }

    @GetMapping("/{id}")
    public ApiResponse<?> getById(@PathVariable Long id, HttpServletRequest req) {
        Long userId = (Long) req.getAttribute("userId");
        return ApiResponse.success(jdService.getById(id, userId));
    }
}
