"""Supported media extensions and categories."""

from __future__ import annotations

DOCUMENT_EXT = {".pdf", ".ppt", ".pptx", ".xls", ".xlsx", ".doc", ".docx", ".txt", ".md"}
IMAGE_EXT = {".png", ".jpg", ".jpeg"}
AUDIO_EXT = {".mp3"}
VIDEO_EXT = {".mp4"}

SUPPORTED_EXTENSIONS = DOCUMENT_EXT | IMAGE_EXT | AUDIO_EXT | VIDEO_EXT

TEXT_LIKE = {".txt", ".md"}

CATEGORY_MAP = {
    ".pdf": "documents",
    ".ppt": "documents",
    ".pptx": "documents",
    ".xls": "documents",
    ".xlsx": "documents",
    ".doc": "documents",
    ".docx": "documents",
    ".txt": "documents",
    ".md": "documents",
    ".png": "images",
    ".jpg": "images",
    ".jpeg": "images",
    ".mp3": "audio",
    ".mp4": "video",
}

MIME_MAP = {
    ".pdf": "application/pdf",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".mp3": "audio/mpeg",
    ".mp4": "video/mp4",
}


def category_for(ext: str) -> str:
    return CATEGORY_MAP.get(ext.lower(), "documents")


def is_supported(path_suffix: str) -> bool:
    return path_suffix.lower() in SUPPORTED_EXTENSIONS
