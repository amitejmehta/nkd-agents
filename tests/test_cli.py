import importlib


def make_cli():
    import nkd_agents.cli as cli_mod

    cli = cli_mod.CLI.__new__(cli_mod.CLI)
    cli.mode = "none"
    return cli


def test_build_message_none_mode():
    import nkd_agents.cli as cli_mod

    cli = make_cli()
    result = cli.build_message("do something")
    assert result.startswith(cli_mod.START_PHRASE)
    assert "Mode: None." in result
    assert result.endswith(" do something")
    assert "(" not in result


def test_build_message_plan_mode():
    import nkd_agents.cli as cli_mod

    cli = make_cli()
    cli.mode = "plan"
    result = cli.build_message("review this")
    assert "Mode: Plan" in result
    assert f"({cli_mod.MODE_PREFIXES['plan']})" in result
    assert result.endswith(" review this")


def test_build_message_socratic_mode():
    import nkd_agents.cli as cli_mod

    cli = make_cli()
    cli.mode = "socratic"
    result = cli.build_message("explain this")
    assert "Mode: Socratic" in result
    assert f"({cli_mod.MODE_PREFIXES['socratic']})" in result
    assert result.endswith(" explain this")


def test_build_message_custom_start_phrase(monkeypatch):
    monkeypatch.setenv("NKD_START_PHRASE", "Custom phrase.")
    import nkd_agents.cli as cli_mod

    importlib.reload(cli_mod)
    cli = make_cli()
    result = cli.build_message("task")
    assert result.startswith("Custom phrase.")


def test_build_message_custom_plan_prefix(monkeypatch):
    monkeypatch.setenv("NKD_PLAN_MODE", "HANDS OFF!")
    import nkd_agents.cli as cli_mod

    importlib.reload(cli_mod)
    cli = make_cli()
    cli.mode = "plan"
    result = cli.build_message("review")
    assert "(HANDS OFF!)" in result
