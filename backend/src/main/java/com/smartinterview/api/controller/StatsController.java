package com.smartinterview.api.controller;

import com.smartinterview.common.ApiResponse;
import com.smartinterview.data.entity.QA;
import com.smartinterview.data.repository.QARepository;
import com.smartinterview.domain.service.StatsService;
import org.springframework.web.bind.annotation.*;

import java.util.*;
import java.util.stream.Collectors;

/**
 * 统计数据控制器 —— 提供面试评分相关的统计接口。
 * <p>
 * 这些接口被 Python AI 服务端的 StatsClient 调用，用于评分校准（calibration）：
 * Python 端拉取已校准的 Q&A 样本作为 few-shot 示例，辅助 LLM 更准确地评分。
 * <p>
 * 详见 AI链路学习路径.md 第六步
 */
@RestController
@RequestMapping("/api/v1/stats")
public class StatsController {

    private final StatsService statsService;
    private final QARepository qaRepository;

    public StatsController(StatsService statsService, QARepository qaRepository) {
        this.statsService = statsService;
        this.qaRepository = qaRepository;
    }

    /** 总体统计概览（面试总数、平均分等） */
    @GetMapping("/overview")
    public ApiResponse<Map<String, Object>> overview() {
        return ApiResponse.success(statsService.getOverallStats());
    }

    /** 分数分布统计 */
    @GetMapping("/scores")
    public ApiResponse<Map<String, Object>> scoreDistribution() {
        return ApiResponse.success(statsService.getScoreDistribution());
    }

    /** 按题目类别的统计 */
    @GetMapping("/categories")
    public ApiResponse<Map<String, Object>> categoryStats() {
        return ApiResponse.success(statsService.getCategoryStats());
    }

    /** 评分质量统计（校准比例、偏差等） */
    @GetMapping("/quality")
    public ApiResponse<Map<String, Object>> scoringQuality() {
        return ApiResponse.success(statsService.getScoringQualityStats());
    }

    /** 全量统计（合并以上所有统计维度） */
    @GetMapping("/full")
    public ApiResponse<Map<String, Object>> fullStats() {
        return ApiResponse.success(statsService.getFullStats());
    }

    /**
     * 获取管理员已校准的 Q&A 样本列表。
     * <p>
     * 被 Python AI 服务的 StatsClient 调用，用于评分校准：
     * Python 端将这些样本作为 few-shot 示例发送给 LLM，
     * 使 LLM 评分更接近人工校准的标准。
     *
     * @param category 可选，按题目类别过滤；不传则返回全部已校准样本
     * @return 已校准的 Q&A 列表（含题目、答案、分数、反馈）
     */
    @GetMapping("/calibrated")
    public ApiResponse<List<Map<String, Object>>> calibratedExamples(
            @RequestParam(required = false) String category) {
        List<QA> qas;
        if (category != null && !category.isBlank()) {
            qas = qaRepository.findByCalibratedTrueAndCategory(category);
        } else {
            qas = qaRepository.findByCalibratedTrue();
        }
        // 将 QA 实体转为精简 Map，仅包含 Python 端所需的字段
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
