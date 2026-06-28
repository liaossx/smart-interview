package com.smartinterview.domain.service;

import com.smartinterview.api.dto.AuthResponse;
import com.smartinterview.api.dto.LoginRequest;
import com.smartinterview.api.dto.RegisterRequest;
import com.smartinterview.data.entity.User;
import com.smartinterview.data.repository.UserRepository;
import com.smartinterview.exception.BusinessException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.security.crypto.password.PasswordEncoder;

import java.util.Optional;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class UserServiceTest {

    @Mock UserRepository userRepository;
    @Mock PasswordEncoder passwordEncoder;
    UserService userService;

    @BeforeEach
    void setUp() {
        // JWT secret must be >= 32 bytes for HMAC-SHA256
        userService = new UserService(userRepository, passwordEncoder,
                "test-jwt-secret-at-least-32-bytes-long", 86400000L);
    }

    @Test
    void register_normal_returnsToken() {
        when(userRepository.existsByUsername("testuser")).thenReturn(false);
        when(passwordEncoder.encode("password")).thenReturn("encoded-pass");
        when(userRepository.save(any(User.class))).thenAnswer(invocation -> {
            User u = invocation.getArgument(0);
            u.setId(1L);
            return u;
        });

        AuthResponse result = userService.register(
                new RegisterRequest("testuser", "password", "TestName", "test@test.com"));

        assertThat(result.token()).isNotBlank();
        assertThat(result.username()).isEqualTo("testuser");
        assertThat(result.userId()).isEqualTo(1L);
        assertThat(result.role()).isEqualTo("USER");
        verify(passwordEncoder).encode("password");
    }

    @Test
    void register_usernameExists_throws400() {
        when(userRepository.existsByUsername("existing")).thenReturn(true);

        assertThatThrownBy(() -> userService.register(
                new RegisterRequest("existing", "pass", "name", "e@t.com")))
                .isInstanceOf(BusinessException.class)
                .satisfies(e -> assertThat(((BusinessException) e).getCode()).isEqualTo(400));
    }

    @Test
    void login_normal_returnsToken() {
        User user = new User("testuser", "encoded-pass", "TestName", "test@test.com");
        user.setId(1L);
        when(userRepository.findByUsername("testuser")).thenReturn(Optional.of(user));
        when(passwordEncoder.matches("password", "encoded-pass")).thenReturn(true);

        AuthResponse result = userService.login(new LoginRequest("testuser", "password"));

        assertThat(result.token()).isNotBlank();
        assertThat(result.userId()).isEqualTo(1L);
        assertThat(result.username()).isEqualTo("testuser");
    }

    @Test
    void login_userNotFound_throws400() {
        when(userRepository.findByUsername("nobody")).thenReturn(Optional.empty());

        assertThatThrownBy(() -> userService.login(new LoginRequest("nobody", "pass")))
                .isInstanceOf(BusinessException.class)
                .satisfies(e -> assertThat(((BusinessException) e).getCode()).isEqualTo(400));
    }

    @Test
    void login_passwordWrong_throws400() {
        User user = new User("testuser", "encoded-pass", "TestName", "test@test.com");
        user.setId(1L);
        when(userRepository.findByUsername("testuser")).thenReturn(Optional.of(user));
        when(passwordEncoder.matches("wrongpass", "encoded-pass")).thenReturn(false);

        assertThatThrownBy(() -> userService.login(new LoginRequest("testuser", "wrongpass")))
                .isInstanceOf(BusinessException.class)
                .satisfies(e -> assertThat(((BusinessException) e).getCode()).isEqualTo(400));
    }

    @Test
    void login_disabledUser_throws403() {
        User user = new User("testuser", "encoded-pass", "TestName", "test@test.com");
        user.setId(1L);
        user.setEnabled(false);
        when(userRepository.findByUsername("testuser")).thenReturn(Optional.of(user));
        when(passwordEncoder.matches("password", "encoded-pass")).thenReturn(true);

        assertThatThrownBy(() -> userService.login(new LoginRequest("testuser", "password")))
                .isInstanceOf(BusinessException.class)
                .satisfies(e -> assertThat(((BusinessException) e).getCode()).isEqualTo(403));
    }
}
