from django.conf import settings
from django.core.files.uploadhandler import FileUploadHandler, StopUpload


class SizeLimitUploadHandler(FileUploadHandler):
    """Abort oversized uploads while they stream, before anything is spooled to disk.

    The view re-checks the size, but by then Django would already have written the whole body to a temp file.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.total = 0

    def receive_data_chunk(self, raw_data, start):
        self.total += len(raw_data)
        if self.total > settings.MAX_UPLOAD_BYTES:
            raise StopUpload(connection_reset=True)
        return raw_data  # hand the chunk to the next handler

    def file_complete(self, file_size):
        return None
