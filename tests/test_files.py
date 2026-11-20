import pytest
from app.files import safe_path, parse_obj

def test_safe_path(): assert str(safe_path("src/main.py")) == "src/main.py"
@pytest.mark.parametrize("p", ["../x", "/etc/passwd", "a/../../b", ".env", "id_rsa"])
def test_reject(p):
    with pytest.raises(ValueError): safe_path(p)
def test_json(): assert parse_obj('{"files": []}')["files"] == []
