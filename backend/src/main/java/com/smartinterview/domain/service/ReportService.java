package com.smartinterview.domain.service;

import com.smartinterview.data.entity.Report;
import com.smartinterview.data.entity.Session;
import com.smartinterview.data.repository.ReportRepository;
import com.smartinterview.data.repository.SessionRepository;
import com.smartinterview.exception.ResourceNotFoundException;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    private final ReportRepository reportRepository;
    private final SessionRepository sessionRepository;

    public ReportService(ReportRepository reportRepository, SessionRepository sessionRepository) {
        this.reportRepository = reportRepository;
        this.sessionRepository = sessionRepository;
    }

    public Report create(Long sessionId, Integer overallScore, String detailsJson,
                         String suggestions, Long userId) {
        Session session = sessionRepository.findById(sessionId)
                .orElseThrow(() -> new ResourceNotFoundException("会话不存在"));
        if (!session.getUserId().equals(userId)) {
            throw new ResourceNotFoundException("会话不存在");
        }
        Report report = new Report();
        report.setSessionId(sessionId);
        report.setOverallScore(overallScore);
        report.setDetailsJson(detailsJson);
        report.setSuggestions(suggestions);
        return reportRepository.save(report);
    }

    public Report getBySessionId(Long sessionId, Long userId) {
        Session session = sessionRepository.findById(sessionId)
                .orElseThrow(() -> new ResourceNotFoundException("会话不存在"));
        if (!session.getUserId().equals(userId)) {
            throw new ResourceNotFoundException("报告不存在");
        }
        return reportRepository.findBySessionId(sessionId)
                .orElseThrow(() -> new ResourceNotFoundException("报告不存在"));
    }
}
