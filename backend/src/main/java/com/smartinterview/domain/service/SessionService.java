package com.smartinterview.domain.service;

import com.smartinterview.api.dto.SessionCreateRequest;
import com.smartinterview.api.dto.SessionResponse;
import com.smartinterview.data.entity.Session;
import com.smartinterview.data.repository.QARepository;
import com.smartinterview.data.repository.ReportRepository;
import com.smartinterview.data.repository.SessionRepository;
import com.smartinterview.exception.ResourceNotFoundException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Service
public class SessionService {

    private final SessionRepository sessionRepository;
    private final QARepository qaRepository;
    private final ReportRepository reportRepository;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public SessionService(SessionRepository sessionRepository, QARepository qaRepository, ReportRepository reportRepository) {
        this.sessionRepository = sessionRepository;
        this.qaRepository = qaRepository;
        this.reportRepository = reportRepository;
    }

    public SessionResponse create(Long userId, SessionCreateRequest request) {
        Session session = new Session();
        session.setUserId(userId);
        session.setJdId(request.jdId());
        session.setResumeId(request.resumeId());
        session.setStatus(Session.Status.PENDING);
        session = sessionRepository.save(session);
        return toResponse(session);
    }

    public List<SessionResponse> listByUser(Long userId) {
        return sessionRepository.findByUserIdOrderByCreatedAtDesc(userId).stream()
                .map(this::toResponse).toList();
    }

    public SessionResponse getById(Long id, Long userId) {
        Session session = sessionRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("会话不存在"));
        if (!session.getUserId().equals(userId)) {
            throw new ResourceNotFoundException("会话不存在");
        }
        return toResponse(session);
    }

    public void updateStatus(Long id, Session.Status status, Long userId) {
        Session session = sessionRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("会话不存在"));
        if (!session.getUserId().equals(userId)) {
            throw new ResourceNotFoundException("会话不存在");
        }
        session.setStatus(status);
        sessionRepository.save(session);
    }

    public void updateScore(Long id, Integer score, Long userId) {
        Session session = sessionRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("会话不存在"));
        if (!session.getUserId().equals(userId)) {
            throw new ResourceNotFoundException("会话不存在");
        }
        session.setTotalScore(score);
        sessionRepository.save(session);
    }

    public void saveQuestions(Long id, Object questions, Long userId) {
        Session session = sessionRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("会话不存在"));
        if (!session.getUserId().equals(userId)) {
            throw new ResourceNotFoundException("会话不存在");
        }
        try {
            session.setQuestionsJson(objectMapper.writeValueAsString(questions));
            sessionRepository.save(session);
        } catch (Exception e) {
            throw new RuntimeException("序列化题目列表失败", e);
        }
    }

    @Transactional
    public void deleteSession(Long id, Long userId) {
        Session session = sessionRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("会话不存在"));
        if (!session.getUserId().equals(userId)) {
            throw new ResourceNotFoundException("会话不存在");
        }
        qaRepository.deleteBySessionId(id);
        reportRepository.deleteBySessionId(id);
        sessionRepository.delete(session);
    }

    private SessionResponse toResponse(Session session) {
        return new SessionResponse(session.getId(), session.getUserId(), session.getJdId(),
                session.getResumeId(), session.getStatus().name(), session.getTotalScore(),
                session.getCreatedAt().toString());
    }
}
