package com.smartinterview.domain.service;

import com.smartinterview.api.dto.JDCreateRequest;
import com.smartinterview.api.dto.JDResponse;
import com.smartinterview.data.entity.JD;
import com.smartinterview.data.repository.JDRepository;
import com.smartinterview.exception.ResourceNotFoundException;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
public class JDService {

    private final JDRepository jdRepository;

    public JDService(JDRepository jdRepository) {
        this.jdRepository = jdRepository;
    }

    public JDResponse create(Long userId, JDCreateRequest request) {
        JD jd = new JD();
        jd.setUserId(userId);
        jd.setContent(request.content());
        jd = jdRepository.save(jd);
        return toResponse(jd);
    }

    public List<JDResponse> listByUser(Long userId) {
        return jdRepository.findByUserIdOrderByCreatedAtDesc(userId).stream()
                .map(this::toResponse).toList();
    }

    public JDResponse getById(Long id, Long userId) {
        JD jd = jdRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("JD不存在"));
        if (!jd.getUserId().equals(userId)) {
            throw new ResourceNotFoundException("JD不存在");
        }
        return toResponse(jd);
    }

    public void updateAnalyzedResult(Long id, String analyzedResult) {
        JD jd = jdRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("JD不存在"));
        jd.setAnalyzedResult(analyzedResult);
        jdRepository.save(jd);
    }

    private JDResponse toResponse(JD jd) {
        return new JDResponse(jd.getId(), jd.getUserId(), jd.getContent(),
                jd.getAnalyzedResult(), jd.getCreatedAt().toString());
    }
}
