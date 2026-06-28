package com.smartinterview.api.dto;

import java.util.Map;

public record ConfigUpdateRequest(
    Map<String, String> configs
) {}