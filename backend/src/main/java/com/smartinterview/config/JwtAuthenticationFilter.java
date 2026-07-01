package com.smartinterview.config;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import javax.crypto.SecretKey;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.List;

/**
 * JWT 认证过滤器 —— 在 Spring Security 授权之前执行，负责解析 JWT 并设置 SecurityContext。
 * <p>
 * 本过滤器继承 OncePerRequestFilter，每个请求只执行一次。职责：
 * <ul>
 *   <li>跳过公开路径（登录、注册、Swagger、健康检查），不做 JWT 校验</li>
 *   <li>支持内部服务间调用：通过 X-Internal-Key 头认证 Python AI 服务，授予 ROLE_INTERNAL</li>
 *   <li>校验前端 Bearer Token（JWT），解析出 userId / username / role，注入 SecurityContext</li>
 * </ul>
 * <p>
 * 注意：本过滤器维护了自己的跳过路径列表（skip list），与 SecurityConfig 的 permitAll() 是两套独立机制。
 * 原因：SecurityConfig 的 permitAll() 控制的是「是否需要认证」，
 * 而本过滤器的 skip list 控制的是「是否尝试解析 JWT」。
 * 若不在过滤器中跳过，即使 permitAll() 放行，过滤器仍会因缺少 token 而返回 401。
 * <p>
 * 详见 AI链路学习路径.md 第九步
 */
@Component
public class JwtAuthenticationFilter extends OncePerRequestFilter {

    private final SecretKey key;
    private final String internalApiKey;

    public JwtAuthenticationFilter(@Value("${jwt.secret}") String secret,
                                   @Value("${internal.api-key:dev-internal-key}") String internalApiKey) {
        this.key = Keys.hmacShaKeyFor(secret.getBytes(StandardCharsets.UTF_8));
        this.internalApiKey = internalApiKey;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                    FilterChain filterChain) throws ServletException, IOException {
        String path = request.getRequestURI();

        // 跳过公开路径：登录、注册、Swagger 文档、健康检查等。
        // 这些路径不需要 JWT 认证，直接放行进入后续过滤链。
        // 注意：此 skip list 与 SecurityConfig.permitAll() 配合使用，二者缺一不可。
        if (path.equals("/api/v1/auth/login") || path.equals("/api/v1/auth/register") ||
                path.startsWith("/swagger-ui") || path.startsWith("/api-docs") ||
                path.startsWith("/actuator/health") || path.startsWith("/actuator/info")) {
            filterChain.doFilter(request, response);
            return;
        }

        // ── 内部服务间认证机制 ──
        // Python AI 服务调用 Java 端的 Stats API 时不携带 JWT（它不是用户），
        // 而是通过 X-Internal-Key 请求头携带预共享密钥进行认证。
        // 密钥来自配置项 internal.api-key，Java 和 Python 双方共享同一密钥。
        String internalKey = request.getHeader("X-Internal-Key");
        if (internalKey != null) {
            if (internalApiKey != null && !internalApiKey.isBlank() && internalKey.equals(internalApiKey)) {
                // 密钥匹配 → 认证为内部服务，授予 ROLE_INTERNAL 角色
                // ROLE_INTERNAL 可访问 Python 端所需的统计数据接口（如 /stats/calibrated）
                UsernamePasswordAuthenticationToken auth =
                        new UsernamePasswordAuthenticationToken("internal-service", null,
                                List.of(new SimpleGrantedAuthority("ROLE_INTERNAL")));
                SecurityContextHolder.getContext().setAuthentication(auth);
                request.setAttribute("userId", 0L); // 内部服务 userId 设为 0，标识非真实用户
                filterChain.doFilter(request, response);
                return;
            }
        }

        // ── 前端用户 JWT 认证 ──
        // 从 Authorization 头提取 Bearer Token 进行校验
        String header = request.getHeader("Authorization");
        if (header == null || !header.startsWith("Bearer ")) {
            // 未携带 JWT → 返回 401 未登录
            response.setStatus(401);
            response.setContentType("application/json");
            response.getWriter().write("{\"code\":401,\"message\":\"未登录\",\"data\":null}");
            return;
        }

        try {
            String token = header.substring(7); // 去掉 "Bearer " 前缀，提取纯 token
            // 使用密钥验签并解析 JWT Claims
            Claims claims = Jwts.parser()
                    .verifyWith(key)
                    .build()
                    .parseSignedClaims(token)
                    .getPayload();
            // 将用户信息注入 request 属性，供后续 Controller 使用（如 userId 用于数据隔离）
            request.setAttribute("userId", claims.get("userId", Long.class));
            request.setAttribute("username", claims.getSubject());

            // 从 JWT 中提取角色，默认为 USER
            String role = claims.get("role", String.class);
            if (role == null) role = "USER";
            request.setAttribute("role", role);

            // 构造 Spring Security 权限列表，角色前缀必须为 ROLE_
            List<SimpleGrantedAuthority> authorities = List.of(
                    new SimpleGrantedAuthority("ROLE_" + role)
            );

            // 设置 SecurityContext，后续 Spring Security 授权过滤器据此判断访问权限
            UsernamePasswordAuthenticationToken auth =
                    new UsernamePasswordAuthenticationToken(claims.getSubject(), null, authorities);
            auth.setDetails(claims.get("userId", Long.class));
            SecurityContextHolder.getContext().setAuthentication(auth);

            filterChain.doFilter(request, response);
        } catch (Exception e) {
            // JWT 验签失败 / 过期 / 格式错误 → 返回 401
            response.setStatus(401);
            response.setContentType("application/json");
            response.getWriter().write("{\"code\":401,\"message\":\"token无效或已过期\",\"data\":null}");
        }
    }
}
