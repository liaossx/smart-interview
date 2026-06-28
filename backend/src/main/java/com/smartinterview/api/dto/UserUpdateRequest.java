package com.smartinterview.api.dto;

import jakarta.validation.constraints.Email;

public record UserUpdateRequest(
    String name,
    @Email String email,
    String role,
    Boolean enabled,
    String phone,
    String password
) {}