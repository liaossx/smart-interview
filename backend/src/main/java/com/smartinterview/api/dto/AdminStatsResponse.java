package com.smartinterview.api.dto;

import java.util.List;
import java.util.Map;

public record AdminStatsResponse(
    long totalUsers,
    long totalSessions,
    long completedSessions,
    Double avgScore,
    double completionRate,
    Map<String, Long> sessionsByDay,
    List<Map<String, Object>> topUsers
) {}