import json

import pytest
from pydantic import ValidationError


class TestFunctionConfig:
    def test_from_env_vars_no_env_vars(self, gh_actions_env):
        from configs import FunctionConfig

        with pytest.raises(ValidationError):
            FunctionConfig.from_envvars()

    def test_from_env_vars_required_only(self, gh_actions_env, monkeypatch, tmp_path):
        from configs import FunctionConfig

        test_func_xid = "test_func_123"
        tmp_func_dir = tmp_path / test_func_xid
        tmp_func_dir.mkdir()

        monkeypatch.setenv("input_function_external_id".upper(), test_func_xid)
        monkeypatch.setenv("input_function_folder".upper(), str(tmp_func_dir))

        fc = FunctionConfig.from_envvars()

        assert fc.function_external_id == test_func_xid
        assert fc.function_folder == tmp_func_dir

    def test_from_env_vars_with_metadata(self, gh_actions_env, monkeypatch, tmp_path):
        from configs import FunctionConfig

        test_func_xid = "test_func_123"
        tmp_func_dir = tmp_path / test_func_xid
        tmp_func_dir.mkdir()

        metadata = {"version": "1.0.0", "versioned": "true", "released": "2022-09-14"}
        metadata_json = json.dumps(metadata, indent=0, separators=(",", ":"))

        monkeypatch.setenv("input_function_external_id".upper(), test_func_xid)
        monkeypatch.setenv("input_function_folder".upper(), str(tmp_func_dir))
        monkeypatch.setenv("input_metadata".upper(), metadata_json)

        fc = FunctionConfig.from_envvars()
        assert fc.metadata == metadata

    def test_from_env_vars_with_metadata_too_long(self, gh_actions_env, monkeypatch, tmp_path):
        from configs import FunctionConfig

        test_func_xid = "test_func_123"
        tmp_func_dir = tmp_path / test_func_xid
        tmp_func_dir.mkdir()

        metadata = {
            "version": "1.0.0",
            "versioned": "true",
            "released": "2022-09-14",
            f"key_{'0' * 32}": r"¯\_(ツ)_/¯",
        }
        metadata_json = json.dumps(metadata, indent=0, separators=(",", ":"))

        monkeypatch.setenv("input_function_external_id".upper(), test_func_xid)
        monkeypatch.setenv("input_function_folder".upper(), str(tmp_func_dir))
        monkeypatch.setenv("input_metadata".upper(), metadata_json)

        with pytest.raises(ValidationError):
            FunctionConfig.from_envvars()

    def test_create_fn_params_with_metadata(self, gh_actions_env, monkeypatch, tmp_path):
        from configs import FunctionConfig

        test_func_xid = "test_func_123"
        tmp_func_dir = tmp_path / test_func_xid
        tmp_func_dir.mkdir()

        metadata = {
            "version": "1.0.0",
            "versioned": "true",
            "released": "2022-09-14",
        }
        metadata_json = json.dumps(metadata, indent=0, separators=(",", ":"))

        monkeypatch.setenv("input_function_external_id".upper(), test_func_xid)
        monkeypatch.setenv("input_function_folder".upper(), str(tmp_func_dir))
        monkeypatch.setenv("input_metadata".upper(), metadata_json)

        fc = FunctionConfig.from_envvars()
        fn_params = fc.create_fn_params()

        assert "metadata" in fn_params.keys()
        assert fn_params["metadata"] == metadata

    def test_from_env_vars_function_file_default(self, gh_actions_env, monkeypatch, tmp_path):
        from configs import FunctionConfig

        test_func_xid = "test_func_123"
        tmp_func_dir = tmp_path / test_func_xid
        tmp_func_dir.mkdir()

        monkeypatch.setenv("input_function_external_id".upper(), test_func_xid)
        monkeypatch.setenv("input_function_folder".upper(), str(tmp_func_dir))

        fc = FunctionConfig.from_envvars()

        assert fc.function_external_id == test_func_xid
        assert fc.function_folder == tmp_func_dir
        assert fc.function_file == "handler.py"

    @pytest.mark.parametrize("test_func_file", ["main.py", "foo/ma-in.py", "foo/bar/ma_in.py", "foo/bar/baz/main8.py"])
    def test_from_env_vars_function_file(self, gh_actions_env, monkeypatch, tmp_path, test_func_file):
        from configs import FunctionConfig

        test_func_xid = "test_func_123"
        tmp_func_dir = tmp_path / test_func_xid
        tmp_func_dir.mkdir()

        monkeypatch.setenv("input_function_external_id".upper(), test_func_xid)
        monkeypatch.setenv("input_function_folder".upper(), str(tmp_func_dir))
        monkeypatch.setenv("input_function_file".upper(), test_func_file)

        fc = FunctionConfig.from_envvars()

        assert fc.function_external_id == test_func_xid
        assert fc.function_folder == tmp_func_dir
        assert fc.function_file == test_func_file

    @pytest.mark.parametrize("test_func_file", [r"\handler.py", r"foo\handler.py", r"foo\\bar\handler.py"])
    def test_from_env_vars_function_file_invalid_posix(self, gh_actions_env, monkeypatch, tmp_path, test_func_file):
        from configs import FunctionConfig

        test_func_xid = "test_func_123"
        tmp_func_dir = tmp_path / test_func_xid
        tmp_func_dir.mkdir()

        monkeypatch.setenv("input_function_external_id".upper(), test_func_xid)
        monkeypatch.setenv("input_function_folder".upper(), str(tmp_func_dir))
        monkeypatch.setenv("input_function_file".upper(), test_func_file)

        with pytest.raises(ValidationError):
            FunctionConfig.from_envvars()
