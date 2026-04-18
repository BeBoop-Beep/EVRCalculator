from argparse import Namespace
from unittest.mock import patch

from backend.jobs import evr_runner


@patch("backend.jobs.evr_runner.logging.basicConfig")
@patch("backend.jobs.evr_runner.EVRRunOrchestrator")
@patch("backend.jobs.evr_runner._validate_args")
@patch("backend.jobs.evr_runner._build_parser")
def test_main_invokes_orchestrator_with_cli_args(
    mock_build_parser,
    mock_validate_args,
    mock_orchestrator_cls,
    _mock_basic_config,
):
    mock_build_parser.return_value.parse_args.return_value = Namespace(
        target_set_identifier="blackBolt",
        input_source="db",
        trigger="scheduled",
        run_label="nightly-run",
    )

    exit_code = evr_runner.main()

    assert exit_code == 0
    mock_validate_args.assert_called_once()
    mock_orchestrator_cls.assert_called_once_with()
    mock_orchestrator_cls.return_value.run.assert_called_once_with(
        target_set_identifier="blackBolt",
        input_source="db",
        run_metadata={
            "trigger": "scheduled",
            "run_label": "nightly-run",
        },
    )


@patch("backend.jobs.evr_runner.logging.basicConfig")
@patch("backend.jobs.evr_runner.logger")
@patch("backend.jobs.evr_runner.EVRRunOrchestrator")
@patch("backend.jobs.evr_runner._validate_args")
@patch("backend.jobs.evr_runner._build_parser")
def test_main_returns_nonzero_when_orchestrator_fails(
    mock_build_parser,
    _mock_validate_args,
    mock_orchestrator_cls,
    mock_logger,
    _mock_basic_config,
):
    mock_build_parser.return_value.parse_args.return_value = Namespace(
        target_set_identifier="blackBolt",
        input_source="spreadsheet",
        trigger="manual",
        run_label=None,
    )
    mock_orchestrator_cls.return_value.run.side_effect = RuntimeError("boom")

    exit_code = evr_runner.main()

    assert exit_code == 1
    mock_logger.exception.assert_called_once()
