"""简历解析 API 路由"""

import tempfile
import os
from fastapi import APIRouter, UploadFile, File, HTTPException
from app.utils.document_parser import parse_pdf, parse_docx

router = APIRouter()


@router.post("/resume/parse")
async def parse_resume(file: UploadFile = File(...)):
    """解析简历文件（PDF/DOCX），返回文本内容"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="未选择文件")

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ("pdf", "docx"):
        raise HTTPException(status_code=400, detail="仅支持 PDF 和 DOCX 文件")

    # 保存到临时文件并解析
    content = await file.read()
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}")
    try:
        tmp.write(content)
        tmp.close()

        if ext == "pdf":
            text = parse_pdf(tmp.name)
        else:
            text = parse_docx(tmp.name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"解析失败: {str(e)}")
    finally:
        os.unlink(tmp.name)

    return {
        "file_name": file.filename,
        "file_type": ext,
        "content": text,
        "content_length": len(text),
    }
