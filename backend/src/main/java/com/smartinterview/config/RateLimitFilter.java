package com.smartinterview.config;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.core.annotation.Order;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.List;

/**
 * 简单 IP 级登录限流过滤器：每 IP 每分钟最多 5 次登录请求，超出返回 429。
 * 仅对 /api/v1/auth/login 生效，不引入外部依赖。
 */
@Component
@Order(0)  // 在 JwtAuthenticationFilter 之前执行
public class RateLimitFilter extends OncePerRequestFilter {

    private static final int MAX_REQUESTS = 5;
    private static final long WINDOW_MS = 60_000L; // 1 分钟窗口

    private final ConcurrentHashMap<String, CopyOnWriteArrayList<Long>> requestMap = new ConcurrentHashMap<>();

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                    FilterChain filterChain) throws ServletException, IOException {
        String path = request.getRequestURI();

        // 仅对登录接口限流
        if (!path.equals("/api/v1/auth/login")) {
            filterChain.doFilter(request, response);
            return;
        }

        String clientIp = getClientIp(request);
        long now = System.currentTimeMillis();

        // 清理过期条目并检查是否超限
        CopyOnWriteArrayList<Long> timestamps = requestMap.computeIfAbsent(clientIp, k -> new CopyOnWriteArrayList<>());

        // 移除窗口外的旧时间戳
        timestamps.removeIf(ts -> now - ts > WINDOW_MS);

        // 偶尔清理整个 map 中空掉的条目（防止内存泄漏）
        if (requestMap.size() > 1000) {
            requestMap.entrySet().removeIf(e -> e.getValue().isEmpty());
        }

        if (timestamps.size() >= MAX_REQUESTS) {
            response.setStatus(429);
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.setCharacterEncoding("UTF-8");
            response.getWriter().write("{\"code\":429,\"message\":\"请求过于频繁，请稍后再试\",\"data\":null}");
            return;
        }

        timestamps.add(now);
        filterChain.doFilter(request, response);
    }

    private String getClientIp(HttpServletRequest request) {
        String ip = request.getHeader("X-Forwarded-For");
        if (ip != null && !ip.isEmpty()) {
            // X-Forwarded-For 可能包含多个 IP，取第一个
            return ip.split(",")[0].trim();
        }
        ip = request.getHeader("X-Real-IP");
        if (ip != null && !ip.isEmpty()) {
            return ip.trim();
        }
        return request.getRemoteAddr();
    }
}
