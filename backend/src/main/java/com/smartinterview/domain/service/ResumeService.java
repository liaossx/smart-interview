package com.smartinterview.domain.service;

import com.smartinterview.api.dto.ResumeUploadResponse;
import com.smartinterview.data.entity.Resume;
import com.smartinterview.data.repository.ResumeRepository;
import com.smartinterview.exception.BusinessException;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

@Service
public class ResumeService {

    private final ResumeRepository resumeRepository;
    private final Path uploadDir;

    public ResumeService(ResumeRepository resumeRepository,
                         @Value("${user.dir}/uploads") String uploadDir) {
        this.resumeRepository = resumeRepository;
        this.uploadDir = Paths.get(uploadDir);
        try {
            Files.createDirectories(this.uploadDir);
        } catch (IOException e) {
            throw new RuntimeException("无法创建上传目录", e);
        }
    }

    public ResumeUploadResponse upload(Long userId, MultipartFile file) {
        String fileName = file.getOriginalFilename();
        if (fileName == null || (!fileName.endsWith(".pdf") && !fileName.endsWith(".docx"))) {
            throw new BusinessException(400, "仅支持 PDF 和 DOCX 文件");
        }

        String storedName = userId + "_" + System.currentTimeMillis() + "_" + fileName;
        Path targetPath = uploadDir.resolve(storedName);

        try {
            file.transferTo(targetPath.toFile());
        } catch (IOException e) {
            throw new BusinessException(500, "文件上传失败");
        }

        Resume resume = new Resume();
        resume.setUserId(userId);
        resume.setFileName(fileName);
        resume.setFileType(fileName.endsWith(".pdf") ? "pdf" : "docx");
        resume.setFilePath(targetPath.toString());
        resume.setParsedText("");
        resume = resumeRepository.save(resume);

        return new ResumeUploadResponse(resume.getId(), resume.getFileName(),
                resume.getFileType(), resume.getParsedText());
    }

    public void updateParsedText(Long id, String parsedText) {
        Resume resume = resumeRepository.findById(id)
                .orElseThrow(() -> new RuntimeException("简历不存在"));
        resume.setParsedText(parsedText);
        resumeRepository.save(resume);
    }
}
