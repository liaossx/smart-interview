package com.smartinterview.domain.service;

import com.smartinterview.api.dto.SessionCreateRequest;
import com.smartinterview.api.dto.SessionResponse;
import com.smartinterview.data.entity.Session;
import com.smartinterview.data.repository.QARepository;
import com.smartinterview.data.repository.ReportRepository;
import com.smartinterview.data.repository.SessionRepository;
import com.smartinterview.exception.ResourceNotFoundException;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class SessionServiceTest {

    @Mock SessionRepository sessionRepository;
    @Mock QARepository qaRepository;
    @Mock ReportRepository reportRepository;

    @InjectMocks SessionService sessionService;

    private Session mockSession(Long id, Long userId, Session.Status status) {
        Session session = mock(Session.class);
        when(session.getId()).thenReturn(id);
        when(session.getUserId()).thenReturn(userId);
        when(session.getJdId()).thenReturn(null);
        when(session.getResumeId()).thenReturn(null);
        when(session.getStatus()).thenReturn(status);
        when(session.getTotalScore()).thenReturn(null);
        when(session.getCreatedAt()).thenReturn(LocalDateTime.now());
        return session;
    }

    @Test
    void create_savesWithPendingStatus() {
        Session saved = mockSession(1L, 1L, Session.Status.PENDING);
        when(sessionRepository.save(any(Session.class))).thenReturn(saved);

        SessionResponse result = sessionService.create(1L, new SessionCreateRequest(1L, 2L));

        assertThat(result.id()).isEqualTo(1L);
        assertThat(result.status()).isEqualTo("PENDING");

        ArgumentCaptor<Session> captor = ArgumentCaptor.forClass(Session.class);
        verify(sessionRepository).save(captor.capture());
        Session passed = captor.getValue();
        assertThat(passed.getUserId()).isEqualTo(1L);
        assertThat(passed.getStatus()).isEqualTo(Session.Status.PENDING);
        assertThat(passed.getJdId()).isEqualTo(1L);
        assertThat(passed.getResumeId()).isEqualTo(2L);
    }

    @Test
    void getById_wrongUser_throwsNotFound() {
        Session session = mock(Session.class);
        when(session.getUserId()).thenReturn(999L);
        when(sessionRepository.findById(1L)).thenReturn(Optional.of(session));

        assertThatThrownBy(() -> sessionService.getById(1L, 1L))
                .isInstanceOf(ResourceNotFoundException.class);
    }

    @Test
    void getById_correctUser_returnsResponse() {
        Session session = mockSession(1L, 1L, Session.Status.IN_PROGRESS);
        when(sessionRepository.findById(1L)).thenReturn(Optional.of(session));

        SessionResponse result = sessionService.getById(1L, 1L);

        assertThat(result.id()).isEqualTo(1L);
        assertThat(result.userId()).isEqualTo(1L);
        assertThat(result.status()).isEqualTo("IN_PROGRESS");
    }

    @Test
    void updateStatus_wrongUser_throwsNotFound() {
        Session session = mock(Session.class);
        when(session.getUserId()).thenReturn(999L);
        when(sessionRepository.findById(1L)).thenReturn(Optional.of(session));

        assertThatThrownBy(() -> sessionService.updateStatus(1L, Session.Status.COMPLETED, 1L))
                .isInstanceOf(ResourceNotFoundException.class);
        verify(sessionRepository, never()).save(any());
    }

    @Test
    void updateScore_wrongUser_throwsNotFound() {
        Session session = mock(Session.class);
        when(session.getUserId()).thenReturn(999L);
        when(sessionRepository.findById(1L)).thenReturn(Optional.of(session));

        assertThatThrownBy(() -> sessionService.updateScore(1L, 85, 1L))
                .isInstanceOf(ResourceNotFoundException.class);
        verify(sessionRepository, never()).save(any());
    }

    @Test
    void deleteSession_cascadeDeletesInOrder() {
        Session session = mock(Session.class);
        when(session.getUserId()).thenReturn(1L);
        when(sessionRepository.findById(1L)).thenReturn(Optional.of(session));

        sessionService.deleteSession(1L, 1L);

        verify(qaRepository).deleteBySessionId(1L);
        verify(reportRepository).deleteBySessionId(1L);
        verify(sessionRepository).delete(session);
    }

    @Test
    void saveQuestions_serializesToJson() {
        Session session = mock(Session.class);
        when(session.getUserId()).thenReturn(1L);
        when(sessionRepository.findById(1L)).thenReturn(Optional.of(session));

        sessionService.saveQuestions(1L, List.of(Map.of("q", "test")), 1L);

        ArgumentCaptor<String> captor = ArgumentCaptor.forClass(String.class);
        verify(session).setQuestionsJson(captor.capture());
        assertThat(captor.getValue()).contains("test");
        verify(sessionRepository).save(session);
    }
}
