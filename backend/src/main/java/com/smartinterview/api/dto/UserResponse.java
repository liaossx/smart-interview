package com.smartinterview.api.dto;

public record UserResponse(
    Long id,
    String username,
    String name,
    String email,
    String role,
    Boolean enabled,
    String phone,
    String avatarUrl,
    long sessionCount,
    Double avgScore,
    String createdAt
) {}