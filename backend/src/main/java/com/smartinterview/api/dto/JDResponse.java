package com.smartinterview.api.dto;

public record JDResponse(
    Long id,
    Long userId,
    String content,
    String analyzedResult,
    String createdAt
) {}
