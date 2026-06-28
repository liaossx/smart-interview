package com.smartinterview.domain.service;

import com.smartinterview.api.dto.QAResponse;
import com.smartinterview.data.entity.QA;
import com.smartinterview.data.entity.Session;
import com.smartinterview.data.repository.QARepository;
import com.smartinterview.data.repository.SessionRepository;
import com.smartinterview.exception.ResourceNotFoundException;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.stream.Collectors;

@Service
public class QAService {

    private final QARepository qaRepository;
    private final SessionRepository sessionRepository;

    public QAService(QARepository qaRepository, SessionRepository sessionRepository) {
        this.qaRepository = qaRepository;
        this.sessionRepository = sessionRepository;
    }

    public QAResponse create(Long sessionId, String question, String category, String answer,
                            Integer score, String feedback, String expectedAnswer, Long userId) {
        Session session = sessionRepository.findById(sessionId)
                .orElseThrow(() -> new ResourceNotFoundException("会话不存在"));
        if (!session.getUserId().equals(userId)) {
            throw new ResourceNotFoundException("会话不存在");
        }
        QA qa = new QA();
        qa.setSessionId(sessionId);
        qa.setQuestion(question);
        qa.setCategory(category);
        qa.setAnswer(answer);
        qa.setScore(score);
        qa.setFeedback(feedback);
        qa.setExpectedAnswer(expectedAnswer);
        qa = qaRepository.save(qa);
        return toResponse(qa);
    }

    public List<QAResponse> listBySession(Long sessionId, Long userId) {
        Session session = sessionRepository.findById(sessionId)
                .orElseThrow(() -> new ResourceNotFoundException("会话不存在"));
        if (!session.getUserId().equals(userId)) {
            throw new ResourceNotFoundException("会话不存在");
        }
        return qaRepository.findBySessionIdOrderByCreatedAtAsc(sessionId).stream()
                .map(this::toResponse).collect(Collectors.toList());
    }

    private QAResponse toResponse(QA qa) {
        return new QAResponse(
                qa.getId(), qa.getSessionId(), qa.getQuestion(), qa.getCategory(),
                qa.getAnswer(), qa.getScore(), qa.getFeedback(),
                qa.getExpectedAnswer(), qa.getCreatedAt().toString());
    }
}
