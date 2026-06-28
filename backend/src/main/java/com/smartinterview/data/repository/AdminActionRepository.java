package com.smartinterview.data.repository;

import com.smartinterview.data.entity.AdminAction;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface AdminActionRepository extends JpaRepository<AdminAction, Long> {
    Page<AdminAction> findByTargetTypeOrderByCreatedAtDesc(String targetType, Pageable pageable);
    Page<AdminAction> findByOperatorIdOrderByCreatedAtDesc(Long operatorId, Pageable pageable);
    Page<AdminAction> findByTargetTypeAndOperatorIdOrderByCreatedAtDesc(String targetType, Long operatorId, Pageable pageable);
}
