package com.smartinterview.api.controller;

import com.smartinterview.common.ApiResponse;
import com.smartinterview.data.entity.QA;
import com.smartinterview.data.repository.QARepository;
import com.smartinterview.domain.service.StatsService;
import org.springframework.web.bind.annotation.*;

import java.util.*;
import java.util.stream.Collectors;

@RestController
@RequestMapping("/api/v1/stats")
public class StatsController {

    private final StatsService statsService;
    private final QARepository qaRepository;

    public StatsController(StatsService statsService, QARepository qaRepository) {
        this.statsService = statsService;
        this.qaRepository = qaRepository;
    }

    @GetMapping("/overview")
    public ApiResponse<Map<String, Object>> overview() {
        return ApiResponse.success(statsService.getOverallStats());
    }

    @GetMapping("/scores")
    public ApiResponse<Map<String, Object>> scoreDistribution() {
        return ApiResponse.success(statsService.getScoreDistribution());
    }

    @GetMapping("/categories")
    public ApiResponse<Map<String, Object>> categoryStats() {
        return ApiResponse.success(statsService.getCategoryStats());
    }

    @GetMapping("/quality")
    public ApiResponse<Map<String, Object>> scoringQuality() {
        return ApiResponse.success(statsService.getScoringQualityStats());
    }

    @GetMapping("/full")
    public ApiResponse<Map<String, Object>> fullStats() {
        return ApiResponse.success(statsService.getFullStats());
    }

    @GetMapping("/calibrated")
    public ApiResponse<List<Map<String, Object>>> calibratedExamples(
            @RequestParam(required = false) String category) {
        List<QA> qas;
        if (category != null && !category.isBlank()) {
            qas = qaRepository.findByCalibratedTrueAndCategory(category);
        } else {
            qas = qaRepository.findByCalibratedTrue();
        }
        List<Map<String, Object>> examples = qas.stream().map(qa -> {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("id", qa.getId());
            m.put("question", qa.getQuestion());
            m.put("category", qa.getCategory());
            m.put("answer", qa.getAnswer());
            m.put("score", qa.getScore());
            m.put("feedback", qa.getFeedback());
            return m;
        }).collect(Collectors.toList());
        return ApiResponse.success(examples);
    }
}
