package com.smartinterview.domain.service;

import com.smartinterview.api.dto.*;
import com.smartinterview.data.entity.*;
import com.smartinterview.data.repository.*;
import com.smartinterview.exception.BusinessException;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.*;
import java.util.stream.Collectors;

@Service
public class AdminService {

    private final UserRepository userRepository;
    private final SessionRepository sessionRepository;
    private final QARepository qaRepository;
    private final ReportRepository reportRepository;
    private final SystemConfigRepository configRepository;
    private final PasswordEncoder passwordEncoder;
    private final AdminActionRepository adminActionRepository;

    public AdminService(UserRepository userRepository, SessionRepository sessionRepository,
                        QARepository qaRepository, ReportRepository reportRepository,
                        SystemConfigRepository configRepository,
                        PasswordEncoder passwordEncoder,
                        AdminActionRepository adminActionRepository) {
        this.userRepository = userRepository;
        this.sessionRepository = sessionRepository;
        this.qaRepository = qaRepository;
        this.reportRepository = reportRepository;
        this.configRepository = configRepository;
        this.passwordEncoder = passwordEncoder;
        this.adminActionRepository = adminActionRepository;
    }

    // ===== Dashboard =====

    public AdminStatsResponse getDashboardStats() {
        long totalUsers = userRepository.count();
        long totalSessions = sessionRepository.count();
        long completedSessions = sessionRepository.countByStatus(Session.Status.COMPLETED);
        double avgScore = sessionRepository.getAverageScore();
        double completionRate = totalSessions > 0 ? (double) completedSessions / totalSessions * 100 : 0;

        // 近7天趋势（修复：从数据库查实际数据）
        Map<String, Long> sessionsByDay = new LinkedHashMap<>();
        LocalDate today = LocalDate.now();
        DateTimeFormatter fmt = DateTimeFormatter.ofPattern("MM-dd");
        for (int i = 6; i >= 0; i--) {
            sessionsByDay.put(today.minusDays(i).format(fmt), 0L);
        }
        LocalDateTime weekAgo = today.minusDays(7).atStartOfDay();
        List<Object[]> dayCounts = sessionRepository.countByDaySince(weekAgo);
        for (Object[] row : dayCounts) {
            java.sql.Date date = (java.sql.Date) row[0];
            String dayKey = date.toLocalDate().format(fmt);
            if (sessionsByDay.containsKey(dayKey)) {
                sessionsByDay.put(dayKey, (Long) row[1]);
            }
        }

        // Top users — 批量查询消除 N+1
        List<User> users = userRepository.findByRole("USER");
        List<Long> userIds = users.stream().map(User::getId).toList();
        Map<Long, Object[]> statsMap = batchSessionStats(userIds);

        List<Map<String, Object>> topUsers = new ArrayList<>();
        for (User user : users) {
            Object[] stats = statsMap.get(user.getId());
            if (stats != null) {
                long sessionCount = (Long) stats[1];
                if (sessionCount > 0) {
                    double userAvgScore = ((Number) stats[2]).doubleValue();
                    Map<String, Object> entry = new HashMap<>();
                    entry.put("userId", user.getId());
                    entry.put("username", user.getUsername());
                    entry.put("name", user.getName());
                    entry.put("sessionCount", sessionCount);
                    entry.put("avgScore", userAvgScore);
                    topUsers.add(entry);
                }
            }
        }
        // 按面试次数降序，取前 10
        topUsers.sort((a, b) -> Long.compare((Long) b.get("sessionCount"), (Long) a.get("sessionCount")));
        if (topUsers.size() > 10) {
            topUsers = topUsers.subList(0, 10);
        }

        return new AdminStatsResponse(totalUsers, totalSessions, completedSessions,
                avgScore, completionRate, sessionsByDay, topUsers);
    }

    // ===== User Management =====

    public Page<UserResponse> listUsers(String keyword, int page, int size) {
        Page<User> userPage;
        if (keyword != null && !keyword.isBlank()) {
            userPage = userRepository.search(keyword, PageRequest.of(page, size, Sort.by("createdAt").descending()));
        } else {
            userPage = userRepository.findAll(PageRequest.of(page, size, Sort.by("createdAt").descending()));
        }
        // 批量查询会话统计，消除 N+1
        List<Long> userIds = userPage.getContent().stream().map(User::getId).toList();
        Map<Long, Object[]> statsMap = batchSessionStats(userIds);
        return userPage.map(u -> toUserResponse(u, statsMap));
    }

    public UserResponse getUserDetail(Long id) {
        User user = userRepository.findById(id)
                .orElseThrow(() -> new BusinessException(404, "用户不存在"));
        Map<Long, Object[]> statsMap = batchSessionStats(List.of(id));
        return toUserResponse(user, statsMap);
    }

    @Transactional
    public UserResponse createUser(UserCreateRequest request) {
        if (userRepository.existsByUsername(request.username())) {
            throw new BusinessException(400, "用户名已存在");
        }
        User user = new User(
            request.username(),
            passwordEncoder.encode(request.password()),
            request.name() != null ? request.name() : "",
            request.email() != null ? request.email() : ""
        );
        if (request.role() != null && !request.role().isBlank()) {
            user.setRole(request.role());
        }
        if (request.phone() != null) {
            user.setPhone(request.phone());
        }
        user = userRepository.save(user);
        Map<Long, Object[]> statsMap = batchSessionStats(List.of(user.getId()));
        logAction("CREATE", "USER", user.getId(), "Created user: " + user.getUsername());
        return toUserResponse(user, statsMap);
    }

    public UserResponse updateUser(Long id, UserUpdateRequest request) {
        User user = userRepository.findById(id)
                .orElseThrow(() -> new BusinessException(404, "用户不存在"));
        if (request.name() != null) user.setName(request.name());
        if (request.email() != null) user.setEmail(request.email());
        if (request.role() != null) user.setRole(request.role());
        if (request.enabled() != null) user.setEnabled(request.enabled());
        if (request.phone() != null) user.setPhone(request.phone());
        if (request.password() != null && !request.password().isBlank()) {
            user.setPassword(passwordEncoder.encode(request.password()));
        }
        userRepository.save(user);
        logAction("UPDATE", "USER", id, "Updated user: " + user.getUsername());
        Map<Long, Object[]> statsMap = batchSessionStats(List.of(id));
        return toUserResponse(user, statsMap);
    }

    public void disableUser(Long id) {
        User user = userRepository.findById(id)
                .orElseThrow(() -> new BusinessException(404, "用户不存在"));
        user.setEnabled(false);
        userRepository.save(user);
        logAction("UPDATE", "USER", id, "Disabled user: " + user.getUsername());
    }

    private UserResponse toUserResponse(User user, Map<Long, Object[]> statsMap) {
        Object[] stats = statsMap.get(user.getId());
        long sessionCount = stats != null ? (Long) stats[1] : 0;
        double avgScore = stats != null ? ((Number) stats[2]).doubleValue() : 0;
        return new UserResponse(
                user.getId(), user.getUsername(), user.getName(), user.getEmail(),
                user.getRole(), user.getEnabled(), user.getPhone(), user.getAvatarUrl(),
                sessionCount, avgScore,
                user.getCreatedAt() != null ? user.getCreatedAt().toString() : ""
        );
    }

    /** 批量查询用户会话统计，返回 Map<userId, [userId, count, avgScore]> */
    private Map<Long, Object[]> batchSessionStats(List<Long> userIds) {
        if (userIds == null || userIds.isEmpty()) {
            return Collections.emptyMap();
        }
        List<Object[]> rows = sessionRepository.findStatsByUserIds(userIds);
        Map<Long, Object[]> map = new HashMap<>();
        for (Object[] row : rows) {
            map.put((Long) row[0], row);
        }
        return map;
    }

    // ===== Session Management =====

    public Page<Session> listAllSessions(String status, Long userId, int page, int size) {
        PageRequest pageRequest = PageRequest.of(page, size, Sort.by("createdAt").descending());
        if (status != null && !status.isBlank() && userId != null) {
            return sessionRepository.findByStatusAndUserId(Session.Status.valueOf(status), userId, pageRequest);
        } else if (status != null && !status.isBlank()) {
            return sessionRepository.findByStatus(Session.Status.valueOf(status), pageRequest);
        } else if (userId != null) {
            return sessionRepository.findByUserId(userId, pageRequest);
        }
        return sessionRepository.findAll(pageRequest);
    }

    public Map<String, Object> getSessionDetail(Long sessionId) {
        Session session = sessionRepository.findById(sessionId)
                .orElseThrow(() -> new BusinessException(404, "会话不存在"));
        Map<String, Object> result = new HashMap<>();
        result.put("session", session);
        result.put("qas", qaRepository.findBySessionIdOrderByCreatedAtAsc(sessionId));
        result.put("report", reportRepository.findBySessionId(sessionId).orElse(null));
        return result;
    }

    @Transactional
    public void deleteSession(Long sessionId) {
        Session session = sessionRepository.findById(sessionId)
                .orElseThrow(() -> new BusinessException(404, "会话不存在"));
        qaRepository.deleteBySessionId(sessionId);
        reportRepository.deleteBySessionId(sessionId);
        sessionRepository.delete(session);
        logAction("DELETE", "SESSION", sessionId, "Deleted session");
    }

    public Session updateSessionStatus(Long sessionId, SessionStatusRequest request) {
        Session session = sessionRepository.findById(sessionId)
                .orElseThrow(() -> new BusinessException(404, "会话不存在"));
        try {
            session.setStatus(Session.Status.valueOf(request.status().toUpperCase()));
        } catch (IllegalArgumentException e) {
            throw new BusinessException(400, "无效的会话状态: " + request.status());
        }
        sessionRepository.save(session);
        logAction("UPDATE", "SESSION", sessionId, "Set status to " + request.status());
        return session;
    }

    public List<Session> getUserSessions(Long userId) {
        return sessionRepository.findByUserIdOrderByCreatedAtDesc(userId);
    }

    // ===== QA Calibration =====

    public void updateQA(Long qaId, QAUpdateRequest request) {
        QA qa = qaRepository.findById(qaId)
                .orElseThrow(() -> new BusinessException(404, "答题不存在"));
        if (request.score() != null) qa.setScore(request.score());
        if (request.feedback() != null) qa.setFeedback(request.feedback());
        if (request.calibrated() != null) qa.setCalibrated(request.calibrated());
        qaRepository.save(qa);
        logAction("UPDATE", "QA", qaId, "Calibrated QA score=" + qa.getScore());
    }

    // ===== Config Management =====

    public Map<String, String> listConfigs() {
        return configRepository.findAll().stream()
                .collect(Collectors.toMap(SystemConfig::getConfigKey, c -> c.getConfigValue() != null ? c.getConfigValue() : ""));
    }

    @Transactional
    public void updateConfigs(Map<String, String> configs) {
        for (var entry : configs.entrySet()) {
            SystemConfig config = configRepository.findByConfigKey(entry.getKey())
                    .orElseGet(() -> {
                        SystemConfig sc = new SystemConfig();
                        sc.setConfigKey(entry.getKey());
                        return sc;
                    });
            config.setConfigValue(entry.getValue());
            configRepository.save(config);
        }
        logAction("UPDATE", "CONFIG", null, "Updated " + configs.size() + " config(s)");
    }

    // ===== Audit Log =====

    public Page<AdminAction> listAuditLogs(String targetType, Long operatorId, int page, int size) {
        PageRequest pageRequest = PageRequest.of(page, size, Sort.by("createdAt").descending());
        if (targetType != null && !targetType.isBlank() && operatorId != null) {
            return adminActionRepository.findByTargetTypeAndOperatorIdOrderByCreatedAtDesc(
                    targetType.toUpperCase(), operatorId, pageRequest);
        } else if (targetType != null && !targetType.isBlank()) {
            return adminActionRepository.findByTargetTypeOrderByCreatedAtDesc(
                    targetType.toUpperCase(), pageRequest);
        } else if (operatorId != null) {
            return adminActionRepository.findByOperatorIdOrderByCreatedAtDesc(operatorId, pageRequest);
        }
        return adminActionRepository.findAll(pageRequest);
    }

    /** Best-effort audit logging — never throws, never breaks the main operation */
    void logAction(String action, String targetType, Long targetId, String description) {
        try {
            Long operatorId = getCurrentOperatorId();
            adminActionRepository.save(new AdminAction(action, targetType, targetId, operatorId, description));
        } catch (Exception e) {
            // Audit logging is best-effort; don't break the operation
        }
    }

    private Long getCurrentOperatorId() {
        try {
            Authentication auth = SecurityContextHolder.getContext().getAuthentication();
            if (auth != null && auth.getDetails() instanceof Long userId) {
                return userId;
            }
        } catch (Exception ignored) {
        }
        return null;
    }
}
