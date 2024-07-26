import pytest

from utils import FnFileString


@pytest.mark.parametrize(
    "path, is_correct",
    (
        (r"baz.py", True),
        (r"home/user0/baz.py", True),
        (r"home/user_foo/bar-baz.py", True),
        (r"/home/user/foo.py", False),
        (r"/home/user//bar.py", False),
        (r"\home\\user//bar.py", False),
        (r"/.py", False),
    ),
)
def test_function_file_regex(path, is_correct):
    assert bool(FnFileString.regex.match(path)) == is_correct
