package com.smartinterview.api.dto;

import jakarta.validation.constraints.NotBlank;

public record JDCreateRequest(
    @NotBlank(message = "JD内容不能为空")
    String content
) {}
