package com.smartinterview.api.dto;

public record QAUpdateRequest(
        Integer score,
        String feedback,
        Boolean calibrated
) {}
