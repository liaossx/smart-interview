package com.smartinterview.config;

import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import jakarta.servlet.FilterChain;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.core.context.SecurityContextHolder;

import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class JwtAuthenticationFilterTest {

    private final String jwtSecret = "test-jwt-secret-at-least-32-bytes-long";
    private final String internalApiKey = "test-internal-key";
    private final SecretKey key = Keys.hmacShaKeyFor(jwtSecret.getBytes(StandardCharsets.UTF_8));

    private JwtAuthenticationFilter filter;
    private FilterChain filterChain;

    @BeforeEach
    void setUp() {
        filter = new JwtAuthenticationFilter(jwtSecret, internalApiKey);
        filterChain = mock(FilterChain.class);
        SecurityContextHolder.clearContext();
    }

    @AfterEach
    void tearDown() {
        SecurityContextHolder.clearContext();
    }

    private MockHttpServletRequest getReq(String uri) {
        MockHttpServletRequest req = new MockHttpServletRequest();
        req.setMethod("GET");
        req.setRequestURI(uri);
        return req;
    }

    private String generateToken(String username, Long userId, String role) {
        var builder = Jwts.builder()
                .subject(username)
                .claim("userId", userId);
        if (role != null) builder.claim("role", role);
        return builder.signWith(key).compact();
    }

    // ===== 公开路径跳过 =====

    @Test
    void publicPath_login_skipsFilter() throws Exception {
        MockHttpServletRequest req = getReq("/api/v1/auth/login");
        MockHttpServletResponse res = new MockHttpServletResponse();

        filter.doFilter(req, res, filterChain);

        verify(filterChain).doFilter(req, res);
        assertThat(res.getStatus()).isEqualTo(200);
        assertThat(SecurityContextHolder.getContext().getAuthentication()).isNull();
    }

    @Test
    void publicPath_register_skipsFilter() throws Exception {
        MockHttpServletRequest req = getReq("/api/v1/auth/register");
        MockHttpServletResponse res = new MockHttpServletResponse();

        filter.doFilter(req, res, filterChain);

        verify(filterChain).doFilter(req, res);
        assertThat(res.getStatus()).isEqualTo(200);
    }

    @Test
    void publicPath_actuatorHealth_skipsFilter() throws Exception {
        MockHttpServletRequest req = getReq("/actuator/health");
        MockHttpServletResponse res = new MockHttpServletResponse();

        filter.doFilter(req, res, filterChain);

        verify(filterChain).doFilter(req, res);
        assertThat(res.getStatus()).isEqualTo(200);
    }

    @Test
    void publicPath_actuatorInfo_skipsFilter() throws Exception {
        MockHttpServletRequest req = getReq("/actuator/info");
        MockHttpServletResponse res = new MockHttpServletResponse();

        filter.doFilter(req, res, filterChain);

        verify(filterChain).doFilter(req, res);
        assertThat(res.getStatus()).isEqualTo(200);
    }

    @Test
    void publicPath_swagger_skipsFilter() throws Exception {
        MockHttpServletRequest req = getReq("/swagger-ui/index.html");
        MockHttpServletResponse res = new MockHttpServletResponse();

        filter.doFilter(req, res, filterChain);

        verify(filterChain).doFilter(req, res);
        assertThat(res.getStatus()).isEqualTo(200);
    }

    @Test
    void publicPath_apiDocs_skipsFilter() throws Exception {
        MockHttpServletRequest req = getReq("/api-docs/swagger-config");
        MockHttpServletResponse res = new MockHttpServletResponse();

        filter.doFilter(req, res, filterChain);

        verify(filterChain).doFilter(req, res);
        assertThat(res.getStatus()).isEqualTo(200);
    }

    // ===== 无 token / 无效 token =====

    @Test
    void noAuthHeader_returns401() throws Exception {
        MockHttpServletRequest req = getReq("/api/v1/sessions");
        MockHttpServletResponse res = new MockHttpServletResponse();

        filter.doFilter(req, res, filterChain);

        verify(filterChain, never()).doFilter(any(), any());
        assertThat(res.getStatus()).isEqualTo(401);
        assertThat(res.getContentAsString()).contains("\"code\":401");
    }

    @Test
    void authHeaderNotBearer_returns401() throws Exception {
        MockHttpServletRequest req = getReq("/api/v1/sessions");
        req.addHeader("Authorization", "Basic dXNlcjpwYXNz");
        MockHttpServletResponse res = new MockHttpServletResponse();

        filter.doFilter(req, res, filterChain);

        verify(filterChain, never()).doFilter(any(), any());
        assertThat(res.getStatus()).isEqualTo(401);
    }

    @Test
    void invalidToken_returns401() throws Exception {
        MockHttpServletRequest req = getReq("/api/v1/sessions");
        req.addHeader("Authorization", "Bearer invalid.token.here");
        MockHttpServletResponse res = new MockHttpServletResponse();

        filter.doFilter(req, res, filterChain);

        verify(filterChain, never()).doFilter(any(), any());
        assertThat(res.getStatus()).isEqualTo(401);
        assertThat(res.getContentAsString()).contains("\"code\":401");
    }

    // ===== 有效 token =====

    @Test
    void validToken_admin_setsAuthAndContinues() throws Exception {
        String token = generateToken("admin", 3L, "ADMIN");
        MockHttpServletRequest req = getReq("/api/v1/stats/overview");
        req.addHeader("Authorization", "Bearer " + token);
        MockHttpServletResponse res = new MockHttpServletResponse();

        filter.doFilter(req, res, filterChain);

        verify(filterChain).doFilter(req, res);
        assertThat(res.getStatus()).isEqualTo(200);
        assertThat(req.getAttribute("userId")).isEqualTo(3L);
        assertThat(req.getAttribute("username")).isEqualTo("admin");
        assertThat(req.getAttribute("role")).isEqualTo("ADMIN");
        assertThat(SecurityContextHolder.getContext().getAuthentication()).isNotNull();
        assertThat(SecurityContextHolder.getContext().getAuthentication().getAuthorities())
                .anyMatch(a -> a.getAuthority().equals("ROLE_ADMIN"));
    }

    @Test
    void validToken_user_setsUserRole() throws Exception {
        String token = generateToken("demo", 1L, "USER");
        MockHttpServletRequest req = getReq("/api/v1/sessions");
        req.addHeader("Authorization", "Bearer " + token);
        MockHttpServletResponse res = new MockHttpServletResponse();

        filter.doFilter(req, res, filterChain);

        verify(filterChain).doFilter(req, res);
        assertThat(req.getAttribute("role")).isEqualTo("USER");
        assertThat(SecurityContextHolder.getContext().getAuthentication().getAuthorities())
                .anyMatch(a -> a.getAuthority().equals("ROLE_USER"));
    }

    @Test
    void validToken_nullRole_defaultsToUser() throws Exception {
        String token = generateToken("testuser", 1L, null);
        MockHttpServletRequest req = getReq("/api/v1/sessions");
        req.addHeader("Authorization", "Bearer " + token);
        MockHttpServletResponse res = new MockHttpServletResponse();

        filter.doFilter(req, res, filterChain);

        verify(filterChain).doFilter(req, res);
        assertThat(req.getAttribute("role")).isEqualTo("USER");
        assertThat(SecurityContextHolder.getContext().getAuthentication().getAuthorities())
                .anyMatch(a -> a.getAuthority().equals("ROLE_USER"));
    }

    // ===== 内部 API Key =====

    @Test
    void internalApiKey_authenticatesAsInternal() throws Exception {
        MockHttpServletRequest req = getReq("/api/v1/stats/overview");
        req.addHeader("X-Internal-Key", "test-internal-key");
        MockHttpServletResponse res = new MockHttpServletResponse();

        filter.doFilter(req, res, filterChain);

        verify(filterChain).doFilter(req, res);
        assertThat(res.getStatus()).isEqualTo(200);
        assertThat(req.getAttribute("userId")).isEqualTo(0L);
        assertThat(SecurityContextHolder.getContext().getAuthentication()).isNotNull();
        assertThat(SecurityContextHolder.getContext().getAuthentication().getName())
                .isEqualTo("internal-service");
    }

    @Test
    void wrongInternalApiKey_fallsThroughToTokenCheck() throws Exception {
        MockHttpServletRequest req = getReq("/api/v1/sessions");
        req.addHeader("X-Internal-Key", "wrong-key");
        MockHttpServletResponse res = new MockHttpServletResponse();

        filter.doFilter(req, res, filterChain);

        verify(filterChain, never()).doFilter(any(), any());
        assertThat(res.getStatus()).isEqualTo(401);
    }
}
