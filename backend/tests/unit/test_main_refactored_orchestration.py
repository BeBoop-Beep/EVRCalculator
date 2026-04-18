import os
from unittest.mock import patch

from backend import main_refactored


@patch("builtins.input", return_value="blackBolt")
@patch("backend.jobs.evr_runner.EVRRunOrchestrator")
def test_main_defaults_to_spreadsheet_mode_and_delegates(
    mock_orchestrator_cls,
    _mock_input,
):
    with patch.dict(os.environ, {}, clear=True):
        main_refactored.main()

    mock_orchestrator_cls.assert_called_once_with()
    mock_orchestrator_cls.return_value.run.assert_called_once_with(
        target_set_identifier="blackBolt",
        input_source="spreadsheet",
        run_metadata={"trigger": "legacy_interactive"},
    )


@patch("builtins.input", return_value="blackBolt")
@patch("backend.jobs.evr_runner.EVRRunOrchestrator")
def test_main_uses_db_mode_when_env_enabled_and_delegates(
    mock_orchestrator_cls,
    _mock_input,
):
    with patch.dict(os.environ, {"EVR_INPUT_SOURCE": "db"}, clear=True):
        main_refactored.main()

    mock_orchestrator_cls.return_value.run.assert_called_once_with(
        target_set_identifier="blackBolt",
        input_source="db",
        run_metadata={"trigger": "legacy_interactive"},
    )


@patch("builtins.input", return_value="blackBolt")
@patch("builtins.print")
@patch("backend.jobs.evr_runner.EVRRunOrchestrator")
def test_main_reports_orchestrator_validation_errors_without_raising(
    mock_orchestrator_cls,
    mock_print,
    _mock_input,
):
    mock_orchestrator_cls.return_value.run.side_effect = ValueError("bad input")

    main_refactored.main()

    mock_print.assert_called_once()
    assert str(mock_print.call_args.args[0]) == "bad input"


def test_main_refactored_does_not_expose_legacy_orchestration_function():
    assert not hasattr(main_refactored, "run_evr_for_set")
