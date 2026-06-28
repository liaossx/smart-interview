package com.smartinterview.api.controller;

import com.smartinterview.api.dto.ReportResponse;
import com.smartinterview.common.ApiResponse;
import com.smartinterview.data.entity.Report;
import com.smartinterview.domain.service.ReportService;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/reports")
public class ReportController {

    private final ReportService reportService;

    public ReportController(ReportService reportService) {
        this.reportService = reportService;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public ApiResponse<?> create(@RequestBody java.util.Map<String, Object> body,
                                 HttpServletRequest req) {
        Long userId = (Long) req.getAttribute("userId");
        Long sessionId = Long.valueOf(body.get("sessionId").toString());
        Integer overallScore = body.get("overallScore") != null ? Integer.valueOf(body.get("overallScore").toString()) : 0;
        String detailsJson = (String) body.getOrDefault("detailsJson", "{}");
        String suggestions = (String) body.getOrDefault("suggestions", "");
        Report report = reportService.create(sessionId, overallScore, detailsJson, suggestions, userId);
        return ApiResponse.success(new ReportResponse(
                report.getId(), report.getSessionId(), report.getOverallScore(),
                report.getDetailsJson(), report.getSuggestions(),
                report.getCreatedAt().toString()));
    }

    @GetMapping("/session/{sessionId}")
    public ApiResponse<?> getBySessionId(@PathVariable Long sessionId, HttpServletRequest req) {
        Long userId = (Long) req.getAttribute("userId");
        Report report = reportService.getBySessionId(sessionId, userId);
        return ApiResponse.success(new ReportResponse(
                report.getId(), report.getSessionId(), report.getOverallScore(),
                report.getDetailsJson(), report.getSuggestions(),
                report.getCreatedAt().toString()));
    }
}
