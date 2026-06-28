package com.smartinterview.config;

import com.smartinterview.data.entity.SystemConfig;
import com.smartinterview.data.entity.User;
import com.smartinterview.data.repository.SystemConfigRepository;
import com.smartinterview.data.repository.UserRepository;
import org.springframework.boot.CommandLineRunner;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

@Component
public class DataInitializer implements CommandLineRunner {

    private final UserRepository userRepository;
    private final SystemConfigRepository configRepository;
    private final PasswordEncoder passwordEncoder;

    public DataInitializer(UserRepository userRepository, SystemConfigRepository configRepository,
                           PasswordEncoder passwordEncoder) {
        this.userRepository = userRepository;
        this.configRepository = configRepository;
        this.passwordEncoder = passwordEncoder;
    }

    @Override
    public void run(String... args) {
        // 初始化管理员（若不存在则创建，存在则修正角色）
        userRepository.findByUsername("admin").ifPresentOrElse(
            existing -> {
                if (!"ADMIN".equals(existing.getRole())) {
                    existing.setRole("ADMIN");
                    if (existing.getName() == null || existing.getName().isBlank()) {
                        existing.setName("系统管理员");
                    }
                    existing.setEnabled(true);
                    userRepository.save(existing);
                }
            },
            () -> {
                String adminPassword = System.getProperty("admin.password", "admin123");
                User admin = new User("admin", passwordEncoder.encode(adminPassword), "系统管理员", "admin@smartinterview.com");
                admin.setRole("ADMIN");
                userRepository.save(admin);
            }
        );

        // 初始化系统配置
        if (configRepository.findByConfigKey("site_name").isEmpty()) {
            SystemConfig c1 = new SystemConfig();
            c1.setConfigKey("site_name");
            c1.setConfigValue("SmartInterview");
            c1.setDescription("系统名称");
            configRepository.save(c1);

            SystemConfig c2 = new SystemConfig();
            c2.setConfigKey("max_questions");
            c2.setConfigValue("12");
            c2.setDescription("每次面试最大题目数");
            configRepository.save(c2);
        }
    }
}
