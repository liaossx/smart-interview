package com.smartinterview.data.repository;

import com.smartinterview.data.entity.QA;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

import java.util.List;

public interface QARepository extends JpaRepository<QA, Long> {
    List<QA> findBySessionIdOrderByCreatedAtAsc(Long sessionId);
    List<QA> findByCalibratedTrueAndCategory(String category);
    List<QA> findByCalibratedTrue();
    long countByCalibratedTrue();
    void deleteBySessionId(Long sessionId);

    // ===== 性能优化：聚合查询 =====

    /** 按分类聚合统计（替代 findAll 后 Java 分组） */
    @Query("SELECT q.category, COUNT(q), AVG(q.score), MIN(q.score), MAX(q.score) " +
           "FROM QA q WHERE q.score IS NOT NULL GROUP BY q.category")
    List<Object[]> findCategoryStats();

    /** 全局聚合统计（替代 findAll 后 Java 计算） */
    @Query("SELECT COUNT(q), COALESCE(AVG(q.score), 0), COALESCE(MIN(q.score), 0), " +
           "COALESCE(MAX(q.score), 0) FROM QA q WHERE q.score IS NOT NULL")
    List<Object[]> findOverallStats();

    /** 评分标准差（衡量评分一致性） */
    @Query(value = "SELECT COALESCE(STDDEV(score), 0) FROM qas WHERE score IS NOT NULL", nativeQuery = true)
    double findScoreStdDev();
}
