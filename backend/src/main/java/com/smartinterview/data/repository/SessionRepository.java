package com.smartinterview.data.repository;

import com.smartinterview.data.entity.Session;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.time.LocalDateTime;
import java.util.Collection;
import java.util.List;

public interface SessionRepository extends JpaRepository<Session, Long> {
    List<Session> findByUserIdOrderByCreatedAtDesc(Long userId);
    long countByStatus(Session.Status status);

    @Query("SELECT COALESCE(AVG(s.totalScore), 0) FROM Session s WHERE s.totalScore IS NOT NULL")
    double getAverageScore();

    Page<Session> findByStatus(Session.Status status, Pageable pageable);

    Page<Session> findByUserId(Long userId, Pageable pageable);

    Page<Session> findByStatusAndUserId(Session.Status status, Long userId, Pageable pageable);

    // ===== 性能优化：聚合查询 =====

    /** 按用户 ID 批量查询会话数和平均分，消除 N+1 */
    @Query("SELECT s.userId, COUNT(s), COALESCE(AVG(s.totalScore), 0) " +
           "FROM Session s WHERE s.userId IN :userIds GROUP BY s.userId")
    List<Object[]> findStatsByUserIds(@Param("userIds") Collection<Long> userIds);

    /** 按天统计会话数（用于 7 天趋势图） */
    @Query("SELECT FUNCTION('DATE', s.createdAt), COUNT(s) " +
           "FROM Session s WHERE s.createdAt >= :since " +
           "GROUP BY FUNCTION('DATE', s.createdAt)")
    List<Object[]> countByDaySince(@Param("since") LocalDateTime since);

    /** 按分数分组统计会话数（用于分数分布图） */
    @Query("SELECT s.totalScore, COUNT(s) FROM Session s " +
           "WHERE s.totalScore IS NOT NULL GROUP BY s.totalScore")
    List<Object[]> countByTotalScore();

    /** 按时间范围统计会话数和平均分（用于时间过滤统计和评分漂移检测） */
    @Query("SELECT COUNT(s), COALESCE(AVG(s.totalScore), 0) FROM Session s " +
           "WHERE s.createdAt >= :from AND s.createdAt < :to AND s.totalScore IS NOT NULL")
    List<Object[]> findStatsByDateRange(@Param("from") LocalDateTime from, @Param("to") LocalDateTime to);
}
