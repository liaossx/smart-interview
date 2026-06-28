package com.smartinterview.domain.service;

import com.smartinterview.data.entity.Session;
import com.smartinterview.data.repository.QARepository;
import com.smartinterview.data.repository.SessionRepository;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.*;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class StatsServiceTest {

    @Mock SessionRepository sessionRepository;
    @Mock QARepository qaRepository;

    @InjectMocks StatsService statsService;

    // ===== getOverallStats =====

    @Test
    void getOverallStats_returnsCorrectValues() {
        when(sessionRepository.count()).thenReturn(100L);
        when(sessionRepository.countByStatus(Session.Status.COMPLETED)).thenReturn(80L);
        when(sessionRepository.getAverageScore()).thenReturn(75.5);

        Map<String, Object> result = statsService.getOverallStats();

        assertThat(result.get("totalSessions")).isEqualTo(100L);
        assertThat(result.get("completedSessions")).isEqualTo(80L);
        assertThat(result.get("completionRate")).isEqualTo(80.0);
        assertThat(result.get("avgTotalScore")).isEqualTo(75.5);
    }

    @Test
    void getOverallStats_zeroSessions_handlesGracefully() {
        when(sessionRepository.count()).thenReturn(0L);
        when(sessionRepository.countByStatus(Session.Status.COMPLETED)).thenReturn(0L);
        when(sessionRepository.getAverageScore()).thenReturn(0.0);

        Map<String, Object> result = statsService.getOverallStats();

        assertThat(result.get("totalSessions")).isEqualTo(0L);
        assertThat(result.get("completedSessions")).isEqualTo(0L);
        assertThat(result.get("completionRate")).isEqualTo(0.0);
        assertThat(result.get("avgTotalScore")).isEqualTo(0.0);
    }

    // ===== getScoreDistribution =====

    @Test
    @SuppressWarnings("unchecked")
    void getScoreDistribution_correctBuckets() {
        List<Object[]> scoreCounts = List.of(
            new Object[]{3, 5L},
            new Object[]{5, 10L},
            new Object[]{8, 20L},
            new Object[]{9, 15L}
        );
        when(sessionRepository.countByTotalScore()).thenReturn(scoreCounts);

        Map<String, Object> result = statsService.getScoreDistribution();

        assertThat(result.get("total")).isEqualTo(50);
        List<Map<String, Object>> dist = (List<Map<String, Object>>) result.get("distribution");
        assertThat(dist).hasSize(5);
        assertThat(dist.get(0).get("range")).isEqualTo("0-2");
        assertThat(dist.get(0).get("count")).isEqualTo(0);
        assertThat(dist.get(1).get("range")).isEqualTo("3-4");
        assertThat(dist.get(1).get("count")).isEqualTo(5);
        assertThat(dist.get(2).get("range")).isEqualTo("5-6");
        assertThat(dist.get(2).get("count")).isEqualTo(10);
        assertThat(dist.get(3).get("range")).isEqualTo("7-8");
        assertThat(dist.get(3).get("count")).isEqualTo(20);
        assertThat(dist.get(4).get("range")).isEqualTo("9-10");
        assertThat(dist.get(4).get("count")).isEqualTo(15);
    }

    @Test
    @SuppressWarnings("unchecked")
    void getScoreDistribution_emptyData_allZeros() {
        when(sessionRepository.countByTotalScore()).thenReturn(Collections.emptyList());

        Map<String, Object> result = statsService.getScoreDistribution();

        assertThat(result.get("total")).isEqualTo(0);
        List<Map<String, Object>> dist = (List<Map<String, Object>>) result.get("distribution");
        assertThat(dist).hasSize(5);
        for (Map<String, Object> bucket : dist) {
            assertThat(bucket.get("count")).isEqualTo(0);
            assertThat(bucket.get("pct")).isEqualTo(0.0);
        }
    }

    // ===== getCategoryStats =====

    @Test
    @SuppressWarnings("unchecked")
    void getCategoryStats_correctOrderAndSummary() {
        List<Object[]> categoryRows = List.of(
            new Object[]{"技术基础", 10L, 6.5, 3, 9},
            new Object[]{"项目经验", 20L, 7.0, 4, 10},
            new Object[]{"场景设计", 5L, 5.5, 2, 8}
        );
        when(qaRepository.findCategoryStats()).thenReturn(categoryRows);
        when(qaRepository.findOverallStats()).thenReturn(
                Collections.singletonList(new Object[]{35L, 6.8, 2, 10}));

        Map<String, Object> result = statsService.getCategoryStats();

        assertThat(result.get("totalQAs")).isEqualTo(35L);
        List<Map<String, Object>> cats = (List<Map<String, Object>>) result.get("categories");
        assertThat(cats).hasSize(4); // 综合 + 3 categories
        // 综合 first
        assertThat(cats.get(0).get("category")).isEqualTo("综合");
        assertThat(cats.get(0).get("count")).isEqualTo(35L);
        // sorted by count desc: 项目经验(20) > 技术基础(10) > 场景设计(5)
        assertThat(cats.get(1).get("category")).isEqualTo("项目经验");
        assertThat(cats.get(2).get("category")).isEqualTo("技术基础");
        assertThat(cats.get(3).get("category")).isEqualTo("场景设计");
    }

    /**
     * Hibernate 6 may return Long instead of Integer for MIN/MAX on Integer columns.
     * The Number cast should handle both types correctly.
     */
    @Test
    @SuppressWarnings("unchecked")
    void getCategoryStats_hibernate6LongTypes_handledCorrectly() {
        List<Object[]> categoryRows = List.of(
            new Object[]{"Java基础", 1L, 8.0, 8L, 8L},
            new Object[]{"技术基础", 17L, 1.6, 0L, 6L}
        );
        when(qaRepository.findCategoryStats()).thenReturn(categoryRows);
        when(qaRepository.findOverallStats()).thenReturn(
                Collections.singletonList(new Object[]{29L, 2.8, 0L, 8L}));

        Map<String, Object> result = statsService.getCategoryStats();

        List<Map<String, Object>> cats = (List<Map<String, Object>>) result.get("categories");
        assertThat(cats).hasSize(3); // 综合 + 2 categories
        // 综合 row with Long types
        assertThat(cats.get(0).get("category")).isEqualTo("综合");
        assertThat(cats.get(0).get("count")).isEqualTo(29L);
        assertThat(cats.get(0).get("minScore")).isEqualTo(0);
        assertThat(cats.get(0).get("maxScore")).isEqualTo(8);
        // Category rows with Long types
        assertThat(cats.get(1).get("category")).isEqualTo("技术基础");
        assertThat(cats.get(1).get("minScore")).isEqualTo(0);
        assertThat(cats.get(1).get("maxScore")).isEqualTo(6);
        assertThat(cats.get(2).get("category")).isEqualTo("Java基础");
        assertThat(cats.get(2).get("minScore")).isEqualTo(8);
        assertThat(cats.get(2).get("maxScore")).isEqualTo(8);
    }

    @Test
    void getCategoryStats_emptyData_returnsEmptyCategories() {
        when(qaRepository.findCategoryStats()).thenReturn(Collections.emptyList());
        when(qaRepository.findOverallStats()).thenReturn(Collections.emptyList());

        Map<String, Object> result = statsService.getCategoryStats();

        assertThat(result.get("totalQAs")).isEqualTo(0L);
        assertThat(result.get("categories")).isInstanceOf(List.class);
        assertThat((List<?>) result.get("categories")).isEmpty();
    }

    @Test
    void getCategoryStats_nullOverallRow_handlesGracefully() {
        when(qaRepository.findCategoryStats()).thenReturn(Collections.emptyList());
        when(qaRepository.findOverallStats()).thenReturn(null);

        Map<String, Object> result = statsService.getCategoryStats();

        assertThat(result.get("totalQAs")).isEqualTo(0L);
        assertThat((List<?>) result.get("categories")).isEmpty();
    }

    // ===== getScoringQualityStats =====

    @Test
    void getScoringQualityStats_returnsAllMetrics() {
        when(qaRepository.findScoreStdDev()).thenReturn(1.56);
        when(qaRepository.findOverallStats()).thenReturn(
                Collections.singletonList(new Object[]{100L, 7.0, 3, 10}));
        when(qaRepository.countByCalibratedTrue()).thenReturn(25L);
        when(sessionRepository.findStatsByDateRange(any(), any()))
                .thenReturn(Collections.singletonList(new Object[]{20L, 78.0}))
                .thenReturn(Collections.singletonList(new Object[]{15L, 72.0}));

        Map<String, Object> result = statsService.getScoringQualityStats();

        assertThat(result.get("scoreStdDeviation")).isEqualTo(1.56);
        assertThat(result.get("totalScoredQAs")).isEqualTo(100L);
        assertThat(result.get("calibratedQAs")).isEqualTo(25L);
        assertThat(result.get("calibrationRate")).isEqualTo(25.0);
        assertThat(result.get("recentAvgScore")).isEqualTo(78.0);
        assertThat(result.get("previousAvgScore")).isEqualTo(72.0);
        assertThat(result.get("scoreDrift")).isEqualTo(6.0);
    }

    @Test
    void getScoringQualityStats_noData_returnsZeros() {
        when(qaRepository.findScoreStdDev()).thenReturn(0.0);
        when(qaRepository.findOverallStats()).thenReturn(null);
        when(qaRepository.countByCalibratedTrue()).thenReturn(0L);
        when(sessionRepository.findStatsByDateRange(any(), any())).thenReturn(null);

        Map<String, Object> result = statsService.getScoringQualityStats();

        assertThat(result.get("scoreStdDeviation")).isEqualTo(0.0);
        assertThat(result.get("totalScoredQAs")).isEqualTo(0L);
        assertThat(result.get("calibratedQAs")).isEqualTo(0L);
        assertThat(result.get("calibrationRate")).isEqualTo(0.0);
        assertThat(result.get("scoreDrift")).isEqualTo(0.0);
    }

    @Test
    void getScoringQualityStats_emptyLists_returnsZeros() {
        when(qaRepository.findScoreStdDev()).thenReturn(0.0);
        when(qaRepository.findOverallStats()).thenReturn(Collections.emptyList());
        when(qaRepository.countByCalibratedTrue()).thenReturn(0L);
        when(sessionRepository.findStatsByDateRange(any(), any())).thenReturn(Collections.emptyList());

        Map<String, Object> result = statsService.getScoringQualityStats();

        assertThat(result.get("totalScoredQAs")).isEqualTo(0L);
        assertThat(result.get("calibrationRate")).isEqualTo(0.0);
        assertThat(result.get("recentAvgScore")).isEqualTo(0.0);
        assertThat(result.get("previousAvgScore")).isEqualTo(0.0);
        assertThat(result.get("scoreDrift")).isEqualTo(0.0);
    }

    // ===== getFullStats =====

    @Test
    void getFullStats_combinesAllSections() {
        when(sessionRepository.count()).thenReturn(100L);
        when(sessionRepository.countByStatus(Session.Status.COMPLETED)).thenReturn(80L);
        when(sessionRepository.getAverageScore()).thenReturn(75.0);
        when(sessionRepository.countByTotalScore()).thenReturn(Collections.emptyList());
        when(qaRepository.findCategoryStats()).thenReturn(Collections.emptyList());
        when(qaRepository.findOverallStats()).thenReturn(null);
        when(qaRepository.findScoreStdDev()).thenReturn(0.0);
        when(qaRepository.countByCalibratedTrue()).thenReturn(0L);
        when(sessionRepository.findStatsByDateRange(any(), any())).thenReturn(null);

        Map<String, Object> result = statsService.getFullStats();

        assertThat(result).containsKeys("overall", "scoreDistribution", "categoryStats", "scoringQuality");
    }
}
