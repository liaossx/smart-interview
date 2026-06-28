package com.smartinterview.api.dto;

public record SessionResponse(
    Long id,
    Long userId,
    Long jdId,
    Long resumeId,
    String status,
    Integer totalScore,
    String createdAt
) {}
