"""
Example of registering commands in a Click group.
"""
import click

def register_commands(cli_group: click.Group):
    """Register commands to the provided group."""
    @cli_group.command("example-cmd")
    def example_cmd():
        """An example command."""
        click.echo("Example command executed.")

@click.group()
def main_cli():
    """Main CLI group."""
    pass

def run_example():
    """Run the example registration and show help."""
    # 1. Create a dummy group (main_cli)
    # 2. Pass the group to register_commands to attach subcommands
    register_commands(main_cli)
    
    print("Commands registered successfully. Verifying by printing help output:\n")
    print("=" * 60)
    # 3. Simulate running the CLI with '--help' to show registered commands.
    try:
        main_cli.main(args=['--help'], prog_name='pdd', standalone_mode=False)
    except click.exceptions.Exit:
        pass
    print("=" * 60)
    print("\nExample complete. All commands from the module are visible above.")

if __name__ == "__main__":
    run_example()
