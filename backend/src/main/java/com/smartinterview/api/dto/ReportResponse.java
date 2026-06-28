package com.smartinterview.api.dto;

public record ReportResponse(
    Long id,
    Long sessionId,
    Integer overallScore,
    String detailsJson,
    String suggestions,
    String createdAt
) {}
