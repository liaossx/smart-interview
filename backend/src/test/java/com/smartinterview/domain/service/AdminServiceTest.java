package com.smartinterview.domain.service;

import com.smartinterview.api.dto.AdminStatsResponse;
import com.smartinterview.api.dto.UserCreateRequest;
import com.smartinterview.api.dto.UserResponse;
import com.smartinterview.api.dto.UserUpdateRequest;
import com.smartinterview.api.dto.SessionStatusRequest;
import com.smartinterview.data.entity.AdminAction;
import com.smartinterview.data.entity.QA;
import com.smartinterview.data.entity.Session;
import com.smartinterview.data.entity.SystemConfig;
import com.smartinterview.data.entity.User;
import com.smartinterview.data.repository.AdminActionRepository;
import com.smartinterview.data.repository.QARepository;
import com.smartinterview.data.repository.ReportRepository;
import com.smartinterview.data.repository.SessionRepository;
import com.smartinterview.data.repository.SystemConfigRepository;
import com.smartinterview.data.repository.UserRepository;
import com.smartinterview.exception.BusinessException;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.security.crypto.password.PasswordEncoder;

import java.time.LocalDate;
import java.util.*;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class AdminServiceTest {

    @Mock UserRepository userRepository;
    @Mock SessionRepository sessionRepository;
    @Mock QARepository qaRepository;
    @Mock ReportRepository reportRepository;
    @Mock SystemConfigRepository configRepository;
    @Mock PasswordEncoder passwordEncoder;
    @Mock AdminActionRepository adminActionRepository;

    @InjectMocks AdminService adminService;

    @Test
    void getDashboardStats_returnsCorrectStats() {
        when(userRepository.count()).thenReturn(10L);
        when(sessionRepository.count()).thenReturn(50L);
        when(sessionRepository.countByStatus(Session.Status.COMPLETED)).thenReturn(40L);
        when(sessionRepository.getAverageScore()).thenReturn(75.5);
        when(sessionRepository.countByDaySince(any())).thenReturn(Collections.emptyList());
        when(userRepository.findByRole("USER")).thenReturn(List.of());

        AdminStatsResponse result = adminService.getDashboardStats();

        assertThat(result.totalUsers()).isEqualTo(10L);
        assertThat(result.totalSessions()).isEqualTo(50L);
        assertThat(result.completedSessions()).isEqualTo(40L);
        assertThat(result.completionRate()).isEqualTo(80.0);
        assertThat(result.avgScore()).isEqualTo(75.5);
    }

    @Test
    void getDashboardStats_zeroSessions_noDivisionByZero() {
        when(userRepository.count()).thenReturn(5L);
        when(sessionRepository.count()).thenReturn(0L);
        when(sessionRepository.countByStatus(Session.Status.COMPLETED)).thenReturn(0L);
        when(sessionRepository.getAverageScore()).thenReturn(0.0);
        when(sessionRepository.countByDaySince(any())).thenReturn(Collections.emptyList());
        when(userRepository.findByRole("USER")).thenReturn(List.of());

        AdminStatsResponse result = adminService.getDashboardStats();

        assertThat(result.completionRate()).isEqualTo(0.0);
        assertThat(result.totalSessions()).isEqualTo(0L);
    }

    @Test
    void getDashboardStats_sevenDayTrend_filled() {
        when(userRepository.count()).thenReturn(10L);
        when(sessionRepository.count()).thenReturn(50L);
        when(sessionRepository.countByStatus(Session.Status.COMPLETED)).thenReturn(40L);
        when(sessionRepository.getAverageScore()).thenReturn(75.0);
        when(userRepository.findByRole("USER")).thenReturn(List.of());

        // Mock: today and 2 days ago have sessions
        LocalDate today = LocalDate.now();
        List<Object[]> dayCounts = List.of(
            new Object[]{java.sql.Date.valueOf(today), 5L},
            new Object[]{java.sql.Date.valueOf(today.minusDays(2)), 3L}
        );
        when(sessionRepository.countByDaySince(any())).thenReturn(dayCounts);

        AdminStatsResponse result = adminService.getDashboardStats();

        Map<String, Long> trend = result.sessionsByDay();
        assertThat(trend).hasSize(7);
        assertThat(trend.get(today.format(java.time.format.DateTimeFormatter.ofPattern("MM-dd")))).isEqualTo(5L);
        assertThat(trend.get(today.minusDays(2).format(java.time.format.DateTimeFormatter.ofPattern("MM-dd")))).isEqualTo(3L);
        // Days with no data should be 0
        assertThat(trend.get(today.minusDays(1).format(java.time.format.DateTimeFormatter.ofPattern("MM-dd")))).isEqualTo(0L);
    }

    @Test
    void getDashboardStats_topUsers_sortedAndCapped() {
        when(userRepository.count()).thenReturn(15L);
        when(sessionRepository.count()).thenReturn(50L);
        when(sessionRepository.countByStatus(Session.Status.COMPLETED)).thenReturn(40L);
        when(sessionRepository.getAverageScore()).thenReturn(75.0);
        when(sessionRepository.countByDaySince(any())).thenReturn(Collections.emptyList());

        // 15 users with different session counts
        List<User> users = new ArrayList<>();
        List<Object[]> stats = new ArrayList<>();
        for (int i = 1; i <= 15; i++) {
            User u = new User("user" + i, "pass", "Name" + i, "email" + i + "@test.com");
            u.setId((long) i);
            users.add(u);
            stats.add(new Object[]{(long) i, (long) (15 - i), 70.0}); // user1 has 14 sessions, user15 has 0
        }
        when(userRepository.findByRole("USER")).thenReturn(users);
        when(sessionRepository.findStatsByUserIds(anyList())).thenReturn(stats);

        AdminStatsResponse result = adminService.getDashboardStats();

        List<Map<String, Object>> topUsers = result.topUsers();
        // user1 has 14 sessions (highest), should be first; only 10 returned (user15 with 0 is excluded)
        assertThat(topUsers).hasSize(10);
        assertThat(topUsers.get(0).get("sessionCount")).isEqualTo(14L);
        assertThat(topUsers.get(9).get("sessionCount")).isEqualTo(5L);
    }

    @Test
    void listUsers_pagination_noN1Query() {
        List<User> users = new ArrayList<>();
        for (int i = 1; i <= 20; i++) {
            User u = new User("user" + i, "pass", "Name" + i, "e" + i + "@t.com");
            u.setId((long) i);
            users.add(u);
        }
        Page<User> mockPage = new PageImpl<>(users, PageRequest.of(0, 20), 50);
        when(userRepository.findAll(any(Pageable.class))).thenReturn(mockPage);
        when(sessionRepository.findStatsByUserIds(anyList())).thenReturn(Collections.emptyList());

        Page<UserResponse> result = adminService.listUsers(null, 0, 20);

        assertThat(result.getContent()).hasSize(20);
        // N+1 fix: findStatsByUserIds should be called exactly once (batch), not 20 times
        verify(sessionRepository, times(1)).findStatsByUserIds(anyList());
    }

    @Test
    void listUsers_keywordSearch_usesSearchMethod() {
        List<User> users = List.of(new User("alice", "pass", "Alice", "a@t.com"));
        Page<User> mockPage = new PageImpl<>(users, PageRequest.of(0, 20), 1);
        when(userRepository.search(eq("alice"), any())).thenReturn(mockPage);
        when(sessionRepository.findStatsByUserIds(anyList())).thenReturn(Collections.emptyList());

        Page<UserResponse> result = adminService.listUsers("alice", 0, 20);

        assertThat(result.getContent()).hasSize(1);
        assertThat(result.getContent().get(0).username()).isEqualTo("alice");
        verify(userRepository, times(1)).search(eq("alice"), any());
        verify(userRepository, never()).findAll(any(Pageable.class));
    }

    @Test
    void getUserDetail_notFound_throws404() {
        when(userRepository.findById(999L)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> adminService.getUserDetail(999L))
                .isInstanceOf(BusinessException.class)
                .satisfies(e -> assertThat(((BusinessException) e).getCode()).isEqualTo(404));
    }

    @Test
    void updateUser_partialUpdate_preservesNullFields() {
        User existing = new User("user1", "pass", "Name1", "old@test.com");
        existing.setId(1L);
        existing.setPhone("12345678");
        when(userRepository.findById(1L)).thenReturn(Optional.of(existing));
        when(userRepository.save(any(User.class))).thenReturn(existing);
        when(sessionRepository.findStatsByUserIds(anyList())).thenReturn(Collections.emptyList());

        // Only update name and role, leave email and phone unchanged (password=null means no reset)
        adminService.updateUser(1L, new UserUpdateRequest("NewName", null, "ADMIN", null, null, null));

        ArgumentCaptor<User> captor = ArgumentCaptor.forClass(User.class);
        verify(userRepository).save(captor.capture());
        User saved = captor.getValue();
        assertThat(saved.getName()).isEqualTo("NewName");
        assertThat(saved.getRole()).isEqualTo("ADMIN");
        assertThat(saved.getEmail()).isEqualTo("old@test.com"); // unchanged
        assertThat(saved.getPhone()).isEqualTo("12345678"); // unchanged
    }

    @Test
    void createUser_success_createsNewUser() {
        when(userRepository.existsByUsername("newuser")).thenReturn(false);
        when(passwordEncoder.encode("pass123")).thenReturn("encoded_hash");
        when(sessionRepository.findStatsByUserIds(anyList())).thenReturn(Collections.emptyList());
        User saved = new User("newuser", "encoded_hash", "New User", "new@test.com");
        saved.setId(10L);
        saved.setRole("ADMIN");
        when(userRepository.save(any(User.class))).thenReturn(saved);

        UserResponse result = adminService.createUser(
            new UserCreateRequest("newuser", "pass123", "New User", "new@test.com", "ADMIN", "12345678900"));

        ArgumentCaptor<User> captor = ArgumentCaptor.forClass(User.class);
        verify(userRepository).save(captor.capture());
        User created = captor.getValue();
        assertThat(created.getUsername()).isEqualTo("newuser");
        assertThat(created.getPassword()).isEqualTo("encoded_hash");
        assertThat(created.getRole()).isEqualTo("ADMIN");
        assertThat(created.getPhone()).isEqualTo("12345678900");
        assertThat(result.username()).isEqualTo("newuser");
    }

    @Test
    void createUser_duplicateUsername_throws400() {
        when(userRepository.existsByUsername("existing")).thenReturn(true);

        assertThatThrownBy(() -> adminService.createUser(
            new UserCreateRequest("existing", "pass", "Name", "e@t.com", "USER", null)))
            .isInstanceOf(BusinessException.class)
            .satisfies(e -> assertThat(((BusinessException) e).getCode()).isEqualTo(400));
    }

    @Test
    void updateUser_withPassword_resetsPassword() {
        User existing = new User("user1", "old_hash", "Name1", "e@t.com");
        existing.setId(1L);
        when(userRepository.findById(1L)).thenReturn(Optional.of(existing));
        when(passwordEncoder.encode("newpass123")).thenReturn("new_hash");
        when(userRepository.save(any(User.class))).thenReturn(existing);
        when(sessionRepository.findStatsByUserIds(anyList())).thenReturn(Collections.emptyList());

        adminService.updateUser(1L, new UserUpdateRequest(null, null, null, null, null, "newpass123"));

        ArgumentCaptor<User> captor = ArgumentCaptor.forClass(User.class);
        verify(userRepository).save(captor.capture());
        assertThat(captor.getValue().getPassword()).isEqualTo("new_hash");
        verify(passwordEncoder).encode("newpass123");
    }

    @Test
    void disableUser_setsEnabledFalse() {
        User user = new User("user1", "pass", "Name1", "e@t.com");
        user.setId(1L);
        user.setEnabled(true);
        when(userRepository.findById(1L)).thenReturn(Optional.of(user));

        adminService.disableUser(1L);

        ArgumentCaptor<User> captor = ArgumentCaptor.forClass(User.class);
        verify(userRepository).save(captor.capture());
        assertThat(captor.getValue().getEnabled()).isFalse();
    }

    @Test
    void updateConfigs_upsert_existingAndNew() {
        SystemConfig existingConfig = new SystemConfig();
        existingConfig.setConfigKey("existing_key");
        existingConfig.setConfigValue("old_value");
        when(configRepository.findByConfigKey("existing_key")).thenReturn(Optional.of(existingConfig));
        when(configRepository.findByConfigKey("new_key")).thenReturn(Optional.empty());

        adminService.updateConfigs(Map.of("existing_key", "new_value", "new_key", "brand_new"));

        verify(configRepository, times(2)).save(any(SystemConfig.class));
        assertThat(existingConfig.getConfigValue()).isEqualTo("new_value");
    }

    @Test
    void deleteSession_cascadesQAAndReport() {
        Session session = new Session();
        session.setId(1L);
        session.setUserId(1L);
        when(sessionRepository.findById(1L)).thenReturn(Optional.of(session));

        adminService.deleteSession(1L);

        verify(qaRepository).deleteBySessionId(1L);
        verify(reportRepository).deleteBySessionId(1L);
        verify(sessionRepository).delete(session);
    }

    @Test
    void deleteSession_notFound_throws404() {
        when(sessionRepository.findById(999L)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> adminService.deleteSession(999L))
                .isInstanceOf(BusinessException.class)
                .satisfies(e -> assertThat(((BusinessException) e).getCode()).isEqualTo(404));
    }

    @Test
    void updateSessionStatus_validStatus_savesAndReturns() {
        Session session = new Session();
        session.setId(1L);
        session.setUserId(1L);
        session.setStatus(Session.Status.PENDING);
        when(sessionRepository.findById(1L)).thenReturn(Optional.of(session));
        when(sessionRepository.save(any(Session.class))).thenReturn(session);

        Session result = adminService.updateSessionStatus(1L, new SessionStatusRequest("completed"));

        assertThat(result.getStatus()).isEqualTo(Session.Status.COMPLETED);
        verify(sessionRepository).save(session);
    }

    @Test
    void updateSessionStatus_invalidStatus_throws400() {
        Session session = new Session();
        session.setId(1L);
        session.setUserId(1L);
        when(sessionRepository.findById(1L)).thenReturn(Optional.of(session));

        assertThatThrownBy(() -> adminService.updateSessionStatus(1L, new SessionStatusRequest("INVALID")))
                .isInstanceOf(BusinessException.class)
                .satisfies(e -> assertThat(((BusinessException) e).getCode()).isEqualTo(400));
    }

    @Test
    void createUser_logsAuditAction() {
        when(userRepository.existsByUsername("newuser")).thenReturn(false);
        when(passwordEncoder.encode("pass123")).thenReturn("encoded_hash");
        when(sessionRepository.findStatsByUserIds(anyList())).thenReturn(Collections.emptyList());
        User saved = new User("newuser", "encoded_hash", "New User", "new@test.com");
        saved.setId(10L);
        when(userRepository.save(any(User.class))).thenReturn(saved);

        adminService.createUser(new UserCreateRequest("newuser", "pass123", "New User", "new@test.com", "USER", null));

        ArgumentCaptor<AdminAction> captor = ArgumentCaptor.forClass(AdminAction.class);
        verify(adminActionRepository).save(captor.capture());
        AdminAction log = captor.getValue();
        assertThat(log.getAction()).isEqualTo("CREATE");
        assertThat(log.getTargetType()).isEqualTo("USER");
        assertThat(log.getTargetId()).isEqualTo(10L);
    }

    @Test
    void deleteSession_logsAuditAction() {
        Session session = new Session();
        session.setId(1L);
        session.setUserId(1L);
        when(sessionRepository.findById(1L)).thenReturn(Optional.of(session));

        adminService.deleteSession(1L);

        ArgumentCaptor<AdminAction> captor = ArgumentCaptor.forClass(AdminAction.class);
        verify(adminActionRepository).save(captor.capture());
        AdminAction log = captor.getValue();
        assertThat(log.getAction()).isEqualTo("DELETE");
        assertThat(log.getTargetType()).isEqualTo("SESSION");
        assertThat(log.getTargetId()).isEqualTo(1L);
    }

    @Test
    void listAuditLogs_noFilters_callsFindAll() {
        Page<AdminAction> mockPage = new PageImpl<>(Collections.emptyList(), PageRequest.of(0, 20), 0);
        when(adminActionRepository.findAll(any(Pageable.class))).thenReturn(mockPage);

        Page<AdminAction> result = adminService.listAuditLogs(null, null, 0, 20);

        assertThat(result).isEqualTo(mockPage);
        verify(adminActionRepository).findAll(any(Pageable.class));
    }

    @Test
    void listAuditLogs_byTargetType_callsFilteredQuery() {
        Page<AdminAction> mockPage = new PageImpl<>(Collections.emptyList(), PageRequest.of(0, 20), 0);
        when(adminActionRepository.findByTargetTypeOrderByCreatedAtDesc(eq("USER"), any(Pageable.class)))
                .thenReturn(mockPage);

        Page<AdminAction> result = adminService.listAuditLogs("USER", null, 0, 20);

        assertThat(result).isEqualTo(mockPage);
        verify(adminActionRepository).findByTargetTypeOrderByCreatedAtDesc(eq("USER"), any(Pageable.class));
    }
}
