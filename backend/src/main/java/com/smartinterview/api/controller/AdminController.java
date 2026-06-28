package com.smartinterview.api.controller;

import com.smartinterview.api.dto.*;
import com.smartinterview.common.ApiResponse;
import com.smartinterview.data.entity.AdminAction;
import com.smartinterview.data.entity.Session;
import com.smartinterview.domain.service.AdminService;
import org.springframework.data.domain.Page;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/api/v1/admin")
public class AdminController {

    private final AdminService adminService;

    public AdminController(AdminService adminService) {
        this.adminService = adminService;
    }

    // ===== Dashboard =====

    @GetMapping("/dashboard")
    public ApiResponse<AdminStatsResponse> dashboard() {
        return ApiResponse.success(adminService.getDashboardStats());
    }

    // ===== Users =====

    @GetMapping("/users")
    public ApiResponse<Page<UserResponse>> listUsers(
            @RequestParam(required = false) String keyword,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        return ApiResponse.success(adminService.listUsers(keyword, page, size));
    }

    @PostMapping("/users")
    public ApiResponse<UserResponse> createUser(@RequestBody UserCreateRequest request) {
        return ApiResponse.success(adminService.createUser(request));
    }

    @GetMapping("/users/{id}")
    public ApiResponse<UserResponse> getUserDetail(@PathVariable Long id) {
        return ApiResponse.success(adminService.getUserDetail(id));
    }

    @PutMapping("/users/{id}")
    public ApiResponse<UserResponse> updateUser(@PathVariable Long id, @RequestBody UserUpdateRequest request) {
        return ApiResponse.success(adminService.updateUser(id, request));
    }

    @DeleteMapping("/users/{id}")
    public ApiResponse<?> disableUser(@PathVariable Long id) {
        adminService.disableUser(id);
        return ApiResponse.success(null);
    }

    @GetMapping("/users/{id}/sessions")
    public ApiResponse<?> getUserSessions(@PathVariable Long id) {
        return ApiResponse.success(adminService.getUserSessions(id));
    }

    // ===== Sessions =====

    @GetMapping("/sessions")
    public ApiResponse<Page<Session>> listSessions(
            @RequestParam(required = false) String status,
            @RequestParam(required = false) Long userId,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        return ApiResponse.success(adminService.listAllSessions(status, userId, page, size));
    }

    @GetMapping("/sessions/{id}")
    public ApiResponse<Map<String, Object>> getSessionDetail(@PathVariable Long id) {
        return ApiResponse.success(adminService.getSessionDetail(id));
    }

    @DeleteMapping("/sessions/{id}")
    public ApiResponse<?> deleteSession(@PathVariable Long id) {
        adminService.deleteSession(id);
        return ApiResponse.success(null);
    }

    @PutMapping("/sessions/{id}/status")
    public ApiResponse<Session> updateSessionStatus(@PathVariable Long id, @RequestBody SessionStatusRequest request) {
        return ApiResponse.success(adminService.updateSessionStatus(id, request));
    }

    // ===== QA Calibration =====

    @PutMapping("/qas/{id}")
    public ApiResponse<?> updateQA(@PathVariable Long id, @RequestBody QAUpdateRequest request) {
        adminService.updateQA(id, request);
        return ApiResponse.success(null);
    }

    // ===== Configs =====

    @GetMapping("/configs")
    public ApiResponse<Map<String, String>> listConfigs() {
        return ApiResponse.success(adminService.listConfigs());
    }

    @PutMapping("/configs")
    public ApiResponse<?> updateConfigs(@RequestBody ConfigUpdateRequest request) {
        adminService.updateConfigs(request.configs());
        return ApiResponse.success(null);
    }

    // ===== Audit Logs =====

    @GetMapping("/audit-logs")
    public ApiResponse<Page<AdminAction>> listAuditLogs(
            @RequestParam(required = false) String targetType,
            @RequestParam(required = false) Long operatorId,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        return ApiResponse.success(adminService.listAuditLogs(targetType, operatorId, page, size));
    }
}
