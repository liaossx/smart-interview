package com.smartinterview.data.repository;

import com.smartinterview.data.entity.JD;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface JDRepository extends JpaRepository<JD, Long> {
    List<JD> findByUserIdOrderByCreatedAtDesc(Long userId);
}
