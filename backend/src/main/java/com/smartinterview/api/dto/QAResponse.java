package com.smartinterview.api.dto;

public record QAResponse(
    Long id,
    Long sessionId,
    String question,
    String category,
    String answer,
    Integer score,
    String feedback,
    String expectedAnswer,
    String createdAt
) {}
