package com.smartinterview.api.dto;

public record ResumeUploadResponse(
    Long id,
    String fileName,
    String fileType,
    String parsedText
) {}
