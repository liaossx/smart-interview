package com.smartinterview.domain.service;

import com.smartinterview.data.entity.QA;
import com.smartinterview.data.entity.Session;
import com.smartinterview.data.repository.QARepository;
import com.smartinterview.data.repository.SessionRepository;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.*;
import java.util.stream.Collectors;

@Service
public class StatsService {

    private final SessionRepository sessionRepository;
    private final QARepository qaRepository;

    public StatsService(SessionRepository sessionRepository, QARepository qaRepository) {
        this.sessionRepository = sessionRepository;
        this.qaRepository = qaRepository;
    }

    // ===== 聚合查询替代全表扫描 =====

    public Map<String, Object> getOverallStats() {
        long totalSessions = sessionRepository.count();
        long completedSessions = sessionRepository.countByStatus(Session.Status.COMPLETED);
        double avgScore = sessionRepository.getAverageScore();
        double completionRate = totalSessions > 0
                ? Math.round((double) completedSessions / totalSessions * 1000.0) / 10.0 : 0.0;

        Map<String, Object> stats = new LinkedHashMap<>();
        stats.put("totalSessions", totalSessions);
        stats.put("completedSessions", completedSessions);
        stats.put("completionRate", completionRate);
        stats.put("avgTotalScore", Math.round(avgScore * 10.0) / 10.0);
        return stats;
    }

    public Map<String, Object> getScoreDistribution() {
        // 用 GROUP BY 查询替代 findAll()，只返回 (score, count) 对
        List<Object[]> scoreCounts = sessionRepository.countByTotalScore();

        int[] buckets = new int[5]; // 0-2, 3-4, 5-6, 7-8, 9-10
        String[] labels = {"0-2", "3-4", "5-6", "7-8", "9-10"};
        int total = 0;

        for (Object[] row : scoreCounts) {
            int score = (Integer) row[0];
            long count = (Long) row[1];
            int idx;
            if (score >= 9) idx = 4;
            else if (score >= 7) idx = 3;
            else if (score >= 5) idx = 2;
            else if (score >= 3) idx = 1;
            else idx = 0;
            buckets[idx] += count;
            total += count;
        }

        List<Map<String, Object>> distribution = new ArrayList<>();
        for (int i = 0; i < 5; i++) {
            Map<String, Object> entry = new LinkedHashMap<>();
            entry.put("range", labels[i]);
            entry.put("count", buckets[i]);
            entry.put("pct", total > 0 ? Math.round((double) buckets[i] / total * 1000.0) / 10.0 : 0.0);
            distribution.add(entry);
        }

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("total", total);
        result.put("distribution", distribution);
        return result;
    }

    public Map<String, Object> getCategoryStats() {
        // 用 GROUP BY 查询替代 findAll()
        List<Object[]> categoryRows = qaRepository.findCategoryStats();
        Object[] overallRow = firstRow(qaRepository.findOverallStats());

        List<Map<String, Object>> categories = new ArrayList<>();

        // 综合统计
        if (overallRow != null && overallRow[0] != null) {
            Map<String, Object> allEntry = new LinkedHashMap<>();
            allEntry.put("category", "综合");
            allEntry.put("count", ((Number) overallRow[0]).longValue());
            allEntry.put("avgScore", Math.round(((Number) overallRow[1]).doubleValue() * 10.0) / 10.0);
            allEntry.put("minScore", ((Number) overallRow[2]).intValue());
            allEntry.put("maxScore", ((Number) overallRow[3]).intValue());
            categories.add(allEntry);
        }

        // 按分类统计，按数量降序
        categoryRows.stream()
                .sorted((a, b) -> Long.compare(((Number) b[1]).longValue(), ((Number) a[1]).longValue()))
                .forEach(row -> {
                    String category = (String) row[0];
                    if (category != null && !category.isBlank()) {
                        Map<String, Object> entry = new LinkedHashMap<>();
                        entry.put("category", category);
                        entry.put("count", ((Number) row[1]).longValue());
                        entry.put("avgScore", Math.round(((Number) row[2]).doubleValue() * 10.0) / 10.0);
                        entry.put("minScore", ((Number) row[3]).intValue());
                        entry.put("maxScore", ((Number) row[4]).intValue());
                        categories.add(entry);
                    }
                });

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("totalQAs", overallRow != null && overallRow[0] != null ? ((Number) overallRow[0]).longValue() : 0);
        result.put("categories", categories);
        return result;
    }

    public Map<String, Object> getScoringQualityStats() {
        Map<String, Object> stats = new LinkedHashMap<>();

        // 1. Score standard deviation — measures scoring consistency
        double stdDev = qaRepository.findScoreStdDev();
        stats.put("scoreStdDeviation", Math.round(stdDev * 100.0) / 100.0);

        // 2. Calibration rate — percentage of QAs calibrated by admins
        Object[] overall = firstRow(qaRepository.findOverallStats());
        long totalScored = (overall != null && overall[0] != null) ? ((Number) overall[0]).longValue() : 0;
        long calibratedCount = qaRepository.countByCalibratedTrue();
        double calibrationRate = totalScored > 0
                ? Math.round((double) calibratedCount / totalScored * 1000.0) / 10.0 : 0.0;
        stats.put("totalScoredQAs", totalScored);
        stats.put("calibratedQAs", calibratedCount);
        stats.put("calibrationRate", calibrationRate);

        // 3. Score drift — compare recent 7-day avg vs previous 7-day avg
        LocalDateTime now = LocalDateTime.now();
        LocalDateTime sevenDaysAgo = now.minusDays(7);
        LocalDateTime fourteenDaysAgo = now.minusDays(14);
        Object[] recentStats = firstRow(sessionRepository.findStatsByDateRange(sevenDaysAgo, now));
        Object[] olderStats = firstRow(sessionRepository.findStatsByDateRange(fourteenDaysAgo, sevenDaysAgo));
        double recentAvg = extractAvgScore(recentStats);
        double olderAvg = extractAvgScore(olderStats);
        double drift = Math.round((recentAvg - olderAvg) * 100.0) / 100.0;
        stats.put("recentAvgScore", Math.round(recentAvg * 10.0) / 10.0);
        stats.put("previousAvgScore", Math.round(olderAvg * 10.0) / 10.0);
        stats.put("scoreDrift", drift);

        return stats;
    }

    private Object[] firstRow(List<Object[]> rows) {
        return (rows != null && !rows.isEmpty()) ? rows.get(0) : null;
    }

    private double extractAvgScore(Object[] row) {
        if (row == null || row[1] == null) return 0.0;
        return ((Number) row[1]).doubleValue();
    }

    public Map<String, Object> getFullStats() {
        Map<String, Object> full = new LinkedHashMap<>();
        full.put("overall", getOverallStats());
        full.put("scoreDistribution", getScoreDistribution());
        full.put("categoryStats", getCategoryStats());
        full.put("scoringQuality", getScoringQualityStats());
        return full;
    }
}
