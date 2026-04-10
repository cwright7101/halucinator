"""Tests for halucinator.util.gtirb_common module."""

from unittest import mock

import pytest

gtirb = pytest.importorskip("gtirb")
pytest.importorskip("gtirb_functions")

from halucinator.util.gtirb_common import (
    generate_assembly,
    generate_gtirb,
    get_functions,
)


class TestGenerateGtirb:
    def test_calls_ddisasm(self):
        with mock.patch("halucinator.util.gtirb_common.subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0)
            generate_gtirb("/path/to/bin", "/path/to/output.gtirb")
            mock_run.assert_called_once_with(
                ["ddisasm", "/path/to/bin", "--ir", "/path/to/output.gtirb"]
            )

    def test_exits_on_failure(self):
        with mock.patch("halucinator.util.gtirb_common.subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=1)
            with pytest.raises(SystemExit):
                generate_gtirb("/path/to/bin", "/path/to/output.gtirb")


class TestGenerateAssembly:
    def test_calls_gtirb_pprinter(self):
        with mock.patch("halucinator.util.gtirb_common.subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0)
            generate_assembly("/path/to/out.s", "/path/to/input.gtirb")
            mock_run.assert_called_once_with(
                [
                    "gtirb-pprinter",
                    "--asm",
                    "/path/to/out.s",
                    "--listing-mode=ui",
                    "/path/to/input.gtirb",
                ]
            )

    def test_exits_on_failure(self):
        with mock.patch("halucinator.util.gtirb_common.subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=1)
            with pytest.raises(SystemExit):
                generate_assembly("/path/to/out.s", "/path/to/input.gtirb")


class TestGetFunctions:
    def test_get_functions_from_ir(self):
        mock_ir = mock.Mock()
        mock_module = mock.Mock()
        mock_ir.modules = [mock_module]

        with mock.patch(
            "halucinator.util.gtirb_common.Function.build_functions"
        ) as mock_build:
            mock_func = mock.Mock()
            mock_build.return_value = [mock_func]
            result = get_functions(mock_ir)

        assert len(result) == 1
        assert result[0] is mock_func

    def test_get_functions_multiple_modules(self):
        mock_ir = mock.Mock()
        mock_mod1 = mock.Mock()
        mock_mod2 = mock.Mock()
        mock_ir.modules = [mock_mod1, mock_mod2]

        with mock.patch(
            "halucinator.util.gtirb_common.Function.build_functions"
        ) as mock_build:
            f1 = mock.Mock()
            f2 = mock.Mock()
            mock_build.side_effect = [[f1], [f2]]
            result = get_functions(mock_ir)

        assert len(result) == 2
