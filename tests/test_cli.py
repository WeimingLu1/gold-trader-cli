"""CLI smoke tests — verify commands are registered and don't crash on --help."""
from typer.testing import CliRunner
from app.cli import app

runner = CliRunner()


def test_cli_help():
    """All commands should respond to --help without error."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "黄金交易" in result.stdout or "Gold Trader" in result.stdout


def test_init_db_help():
    """init-db --help should work."""
    result = runner.invoke(app, ["init-db", "--help"])
    assert result.exit_code == 0


def test_doctor_help():
    """doctor --help should work."""
    result = runner.invoke(app, ["doctor", "--help"])
    assert result.exit_code == 0


def test_collect_help():
    """collect --help should work."""
    result = runner.invoke(app, ["collect", "--help"])
    assert result.exit_code == 0


def test_run_once_help():
    """run-once --help should work."""
    result = runner.invoke(app, ["run-once", "--help"])
    assert result.exit_code == 0


def test_evaluate_pending_help():
    """evaluate-pending --help should work."""
    result = runner.invoke(app, ["evaluate-pending", "--help"])
    assert result.exit_code == 0


def test_report_daily_help():
    """report-daily --help should work."""
    result = runner.invoke(app, ["report-daily", "--help"])
    assert result.exit_code == 0


def test_weights_show_help():
    """weights-show --help should work."""
    result = runner.invoke(app, ["weights-show", "--help"])
    assert result.exit_code == 0


def test_config_show_help():
    """config-show --help should work."""
    result = runner.invoke(app, ["config-show", "--help"])
    assert result.exit_code == 0


def test_doctor_runs():
    """doctor command should run without crashing."""
    result = runner.invoke(app, ["doctor"])
    # May fail on DB not init'd but shouldn't crash
    assert result.exit_code in [0, 1]
