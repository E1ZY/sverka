"""Input validation shared by manual uploads and the built-in fixture runner."""
import zipfile


def validate_file(path):
    if path.suffix.lower() in {'.xlsx', '.docx'}:
        with zipfile.ZipFile(path) as archive:
            if sum(z.file_size for z in archive.infolist()) > 100 * 1024 * 1024:
                raise ValueError('Слишком большой распакованный документ')
