package com.smartinterview.domain.service;

import com.smartinterview.api.dto.AuthResponse;
import com.smartinterview.api.dto.LoginRequest;
import com.smartinterview.api.dto.RegisterRequest;
import com.smartinterview.data.entity.User;
import com.smartinterview.data.repository.UserRepository;
import com.smartinterview.exception.BusinessException;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;

import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;
import java.util.Date;

@Service
public class UserService {

    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;
    private final SecretKey key;
    private final long jwtExpiration;

    public UserService(UserRepository userRepository, PasswordEncoder passwordEncoder,
                       @Value("${jwt.secret}") String jwtSecret,
                       @Value("${jwt.expiration}") long jwtExpiration) {
        this.userRepository = userRepository;
        this.passwordEncoder = passwordEncoder;
        this.key = Keys.hmacShaKeyFor(jwtSecret.getBytes(StandardCharsets.UTF_8));
        this.jwtExpiration = jwtExpiration;
    }

    public AuthResponse register(RegisterRequest request) {
        if (userRepository.existsByUsername(request.username())) {
            throw new BusinessException(400, "用户名已存在");
        }
        User user = new User(request.username(), passwordEncoder.encode(request.password()),
                request.name(), request.email());
        user = userRepository.save(user);
        String token = generateToken(user);
        return new AuthResponse(token, user.getId(), user.getUsername(), user.getName(), user.getRole());
    }

    public AuthResponse login(LoginRequest request) {
        User user = userRepository.findByUsername(request.username())
                .orElseThrow(() -> new BusinessException(400, "用户名或密码错误"));
        if (!passwordEncoder.matches(request.password(), user.getPassword())) {
            throw new BusinessException(400, "用户名或密码错误");
        }
        if (!user.getEnabled()) {
            throw new BusinessException(403, "账号已被禁用，请联系管理员");
        }
        String token = generateToken(user);
        return new AuthResponse(token, user.getId(), user.getUsername(), user.getName(), user.getRole());
    }

    public User findById(Long id) {
        return userRepository.findById(id)
                .orElseThrow(() -> new BusinessException(404, "用户不存在"));
    }

    private String generateToken(User user) {
        return Jwts.builder()
                .subject(user.getUsername())
                .claim("userId", user.getId())
                .claim("role", user.getRole())
                .issuedAt(new Date())
                .expiration(new Date(System.currentTimeMillis() + jwtExpiration))
                .signWith(key)
                .compact();
    }
}
