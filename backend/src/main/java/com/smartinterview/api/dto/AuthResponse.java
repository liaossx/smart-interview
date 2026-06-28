package com.smartinterview.api.dto;

public record AuthResponse(
    String token,
    Long userId,
    String username,
    String name,
    String role
) {}
