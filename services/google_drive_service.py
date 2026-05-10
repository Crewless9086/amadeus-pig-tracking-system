import json
import mimetypes
from pathlib import Path

from google.auth.transport.requests import AuthorizedSession
from google.oauth2.service_account import Credentials

from services.google_sheets_service import GOOGLE_SERVICE_ACCOUNT_FILE, SCOPES

DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"
DRIVE_UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files"


def _get_drive_session():
    credentials = Credentials.from_service_account_file(
        GOOGLE_SERVICE_ACCOUNT_FILE,
        scopes=SCOPES,
    )
    return AuthorizedSession(credentials)


def upload_file_to_drive(file_path, folder_id, file_name=None, mime_type=None):
    file_path = Path(file_path)
    if not file_path.exists() or not file_path.is_file():
        raise ValueError(f"File not found: {file_path}")

    folder_id = str(folder_id or "").strip()
    if not folder_id:
        raise ValueError("Google Drive folder_id is required.")

    file_name = str(file_name or file_path.name).strip()
    mime_type = str(mime_type or _guess_mime_type(file_path)).strip()

    metadata = {
        "name": file_name,
        "parents": [folder_id],
    }

    boundary = "amadeus-document-upload-boundary"
    body = _build_multipart_body(boundary, metadata, file_path, mime_type)

    session = _get_drive_session()
    response = session.post(
        DRIVE_UPLOAD_URL,
        params={
            "uploadType": "multipart",
            "fields": "id,name,webViewLink,webContentLink,mimeType",
            "supportsAllDrives": "true",
        },
        data=body,
        headers={
            "Content-Type": f"multipart/related; boundary={boundary}",
        },
    )
    _raise_for_drive_error(response)
    return response.json()


def download_drive_file(file_id, destination_path):
    file_id = str(file_id or "").strip()
    if not file_id:
        raise ValueError("Google Drive file_id is required.")

    destination_path = Path(destination_path)
    destination_path.parent.mkdir(parents=True, exist_ok=True)

    session = _get_drive_session()
    response = session.get(
        f"{DRIVE_FILES_URL}/{file_id}",
        params={
            "alt": "media",
            "supportsAllDrives": "true",
        },
        stream=True,
    )
    _raise_for_drive_error(response)

    with destination_path.open("wb") as handle:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                handle.write(chunk)

    return destination_path


def get_drive_file_metadata(file_id):
    file_id = str(file_id or "").strip()
    if not file_id:
        raise ValueError("Google Drive file_id is required.")

    session = _get_drive_session()
    response = session.get(
        f"{DRIVE_FILES_URL}/{file_id}",
        params={
            "fields": "id,name,webViewLink,webContentLink,mimeType,size,createdTime",
            "supportsAllDrives": "true",
        },
    )
    _raise_for_drive_error(response)
    return response.json()


def _guess_mime_type(file_path):
    guessed, _ = mimetypes.guess_type(str(file_path))
    return guessed or "application/octet-stream"


def _build_multipart_body(boundary, metadata, file_path, mime_type):
    metadata_part = json.dumps(metadata).encode("utf-8")
    file_bytes = file_path.read_bytes()

    return b"".join([
        f"--{boundary}\r\n".encode("utf-8"),
        b"Content-Type: application/json; charset=UTF-8\r\n\r\n",
        metadata_part,
        b"\r\n",
        f"--{boundary}\r\n".encode("utf-8"),
        f"Content-Type: {mime_type}\r\n\r\n".encode("utf-8"),
        file_bytes,
        b"\r\n",
        f"--{boundary}--\r\n".encode("utf-8"),
    ])


def _raise_for_drive_error(response):
    if 200 <= response.status_code < 300:
        return

    try:
        detail = response.json()
    except ValueError:
        detail = response.text

    raise ValueError(f"Google Drive API error {response.status_code}: {detail}")
