#!/usr/bin/env python3
"""
Baymax - Your Personal AI Command Center
=========================================

A calm, efficient CLI AI agent that acts as a single natural-language
command center for your digital life.

Built with the Claude Agent SDK for powerful autonomous capabilities.

SETUP INSTRUCTIONS
------------------
1. Install Claude Code runtime:
   curl -fsSL https://claude.ai/install.sh | bash

2. Install dependencies:
   pip install -e .

3. Set your API key:
   export ANTHROPIC_API_KEY=your_api_key

   Or for Azure AI Foundry:
   export CLAUDE_CODE_USE_FOUNDRY=1
   (and configure Azure credentials)

4. Start using Baymax:
   baymax                      # Interactive REPL mode
   baymax run "read my emails" # One-off command mode

USAGE EXAMPLES
--------------
- "read my unread emails"
- "summarize my inbox"
- "show my calendar today"
- "create a task: Buy groceries"
- "find all Python files in this directory"
- "what's in the README?"

Author: Your friendly AI assistant
License: MIT
"""

import os
import sys
import asyncio
from typing import Optional, List, Any, Dict

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.theme import Theme
from rich.live import Live
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Rich console with custom theme
custom_theme = Theme(
    {
        "info": "cyan",
        "success": "green",
        "warning": "yellow",
        "error": "red bold",
        "baymax": "bold magenta",
    }
)
console = Console(theme=custom_theme)

# Typer app
app = typer.Typer(
    name="baymax",
    help="Baymax - Your Personal AI Command Center",
    add_completion=False,
    no_args_is_help=False,
    invoke_without_command=True,
)

# =============================================================================
# CONFIGURATION
# =============================================================================


class Config:
    """Configuration management for Baymax."""

    # Model configuration
    MODEL_NAME: str = os.getenv("MODEL_NAME", "sonnet")

    # Composio API key for external service integrations
    COMPOSIO_API_KEY: str = os.getenv("COMPOSIO_API_KEY", "")

    # Allowed tools for the agent (built-in + Composio MCP tools)
    ALLOWED_TOOLS: List[str] = [
        "Read",
        "Write",
        "Edit",
        "Bash",
        "Glob",
        "Grep",
        "WebSearch",
        "WebFetch",
        "Task",  # For subagents
    ]

    # Composio apps to enable via MCP
    COMPOSIO_APPS: List[str] = [
        "gmail",
        "googlecalendar",
        "googletasks",
        "github",
        "notion",
        "discord",
        "linkedin",
    ]

    # System prompt for Baymax personality
    SYSTEM_PROMPT: str = """You are Baymax, a calm, efficient personal assistant. 

Your personality:
- Calm and reassuring, like the character from Big Hero 6
- Concise and helpful - no unnecessary fluff
- Action-oriented - use tools when needed
- Honest - if you can't do something, say so clearly

Guidelines:
- Use tools when needed to accomplish tasks
- Keep responses short and actionable
- Format responses nicely for terminal display (use markdown)
- If a tool fails, explain what went wrong clearly
- Never hallucinate or make up information
- When listing items, format them clearly with bullet points or numbers

Remember: You are here to help manage the user's digital life efficiently."""

    @classmethod
    def validate(cls) -> tuple[bool, List[str]]:
        """Validate configuration and return status with missing items."""
        missing = []

        # Check for API key (either direct or via Foundry)
        use_foundry = os.getenv("CLAUDE_CODE_USE_FOUNDRY", "0") == "1"
        has_api_key = bool(os.getenv("ANTHROPIC_API_KEY"))

        if not use_foundry and not has_api_key:
            missing.append("ANTHROPIC_API_KEY (or set CLAUDE_CODE_USE_FOUNDRY=1)")

        return len(missing) == 0, missing

    @classmethod
    def get_composio_mcp_config(cls) -> Dict[str, Any]:
        """Get MCP server configuration for Composio integrations."""
        if not cls.COMPOSIO_API_KEY:
            return {}

        # Composio MCP server configuration
        # Uses SSE transport to connect to Composio's hosted MCP servers
        return {
            "composio": {
                "type": "sse",
                "url": f"https://mcp.composio.dev/sse?api_key={cls.COMPOSIO_API_KEY}",
            }
        }


# =============================================================================
# AGENT SDK CLIENT
# =============================================================================


async def process_command_async(
    prompt: str,
    continue_conversation: bool = False,
    session_id: Optional[str] = None,
) -> tuple[str, Optional[str]]:
    """Process a command using the Claude Agent SDK.

    Returns:
        Tuple of (response_text, session_id)
    """
    try:
        from claude_agent_sdk import (
            ClaudeSDKClient,
            ClaudeAgentOptions,
            AssistantMessage,
            TextBlock,
            ToolUseBlock,
            ResultMessage,
        )
    except ImportError:
        return (
            "Claude Agent SDK not installed. Run: pip install claude-agent-sdk\n\n"
            "Also ensure Claude Code is installed: curl -fsSL https://claude.ai/install.sh | bash",
            None,
        )

    try:
        # Build options with optional MCP servers for Composio integrations
        mcp_servers = Config.get_composio_mcp_config()

        options = ClaudeAgentOptions(
            allowed_tools=Config.ALLOWED_TOOLS,
            system_prompt=Config.SYSTEM_PROMPT,
            model=Config.MODEL_NAME,
            permission_mode="bypassPermissions",  # Auto-approve for CLI use
            resume=session_id if continue_conversation and session_id else None,
            mcp_servers=mcp_servers if mcp_servers else None,
        )

        response_parts = []
        new_session_id = None

        async with ClaudeSDKClient(options=options) as client:
            await client.query(prompt)

            async for message in client.receive_response():
                # Capture session ID from init message
                if hasattr(message, "subtype") and message.subtype == "init":
                    new_session_id = getattr(message, "session_id", None)

                # Process assistant messages
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            response_parts.append(block.text)
                        elif isinstance(block, ToolUseBlock):
                            # Optionally show tool usage
                            pass

                # Check for result
                if isinstance(message, ResultMessage):
                    if message.is_error:
                        response_parts.append(f"\n[Error: {message.result}]")
                    break

        response = (
            "\n".join(response_parts)
            if response_parts
            else "I processed your request but have no response."
        )
        return response, new_session_id or session_id

    except Exception as e:
        error_msg = str(e).lower()

        # Friendly error messages
        if "not found" in error_msg or "cli" in error_msg:
            return (
                "Claude Code CLI not found. Please install it:\n"
                "  curl -fsSL https://claude.ai/install.sh | bash",
                session_id,
            )
        elif "authentication" in error_msg or "api key" in error_msg:
            return (
                "Authentication failed. Please set your API key:\n"
                "  export ANTHROPIC_API_KEY=your_api_key",
                session_id,
            )
        else:
            return f"An error occurred: {e}", session_id


def process_command(
    prompt: str,
    continue_conversation: bool = False,
    session_id: Optional[str] = None,
) -> tuple[str, Optional[str]]:
    """Synchronous wrapper for process_command_async."""
    return asyncio.run(process_command_async(prompt, continue_conversation, session_id))


# =============================================================================
# UI FUNCTIONS
# =============================================================================


def display_welcome():
    """Display welcome message."""
    # Check if Composio is configured for dynamic welcome message
    has_composio = bool(Config.COMPOSIO_API_KEY)

    base_capabilities = """
- **Files**: "read the README", "find all Python files", "edit config.json"
- **Commands**: "run the tests", "check git status", "list directory"
- **Web**: "search for Python tutorials", "fetch docs from URL"
- **Tasks**: "create a todo list", "summarize this codebase"
"""

    external_capabilities = """
- **Email**: "read my unread emails", "send an email to John"
- **Calendar**: "show my schedule today", "create a meeting for tomorrow"
- **Apps**: Slack, GitHub, Notion, Discord, LinkedIn, and more!
"""

    if has_composio:
        welcome_text = f"""
# Hello! I am Baymax, your personal healthcare-- I mean, *digital life* companion.

I can help you with:
{base_capabilities}{external_capabilities}
Type your request, or type `exit` to quit.
"""
    else:
        welcome_text = f"""
# Hello! I am Baymax, your personal healthcare-- I mean, *digital life* companion.

I can help you with:
{base_capabilities}
*Tip: Run `baymax --setup` to enable Gmail, Calendar, Slack integrations!*

Type your request, or type `exit` to quit.
"""
    console.print(
        Panel(
            Markdown(welcome_text),
            title="[baymax]Baymax[/baymax]",
            border_style="magenta",
            padding=(1, 2),
        )
    )


def display_response(response: str):
    """Display the agent's response with nice formatting."""
    try:
        md = Markdown(response)
        console.print(Panel(md, border_style="cyan", padding=(0, 1)))
    except Exception:
        console.print(Panel(response, border_style="cyan", padding=(0, 1)))


# =============================================================================
# SETUP COMMAND
# =============================================================================


def run_setup():
    """Interactive setup wizard."""
    console.print(
        Panel(
            "[baymax]Baymax Setup Wizard[/baymax]\n\nLet's get you set up with Baymax!",
            border_style="magenta",
        )
    )

    # Check for Claude Code CLI
    console.print("\n[info]Checking for Claude Code CLI...[/info]")
    import shutil

    if shutil.which("claude"):
        console.print("[success]Claude Code CLI is installed![/success]")
    else:
        console.print("[error]Claude Code CLI not found![/error]")
        console.print("\n[info]Install it with:[/info]")
        console.print("  curl -fsSL https://claude.ai/install.sh | bash")
        console.print("")

    # Check for API key
    use_foundry = os.getenv("CLAUDE_CODE_USE_FOUNDRY", "0") == "1"
    has_api_key = bool(os.getenv("ANTHROPIC_API_KEY"))

    console.print("\n[info]Checking authentication...[/info]")

    if use_foundry:
        console.print(
            "[success]Azure AI Foundry mode enabled (CLAUDE_CODE_USE_FOUNDRY=1)[/success]"
        )
    elif has_api_key:
        console.print("[success]ANTHROPIC_API_KEY is set![/success]")
    else:
        console.print("[error]No API key found![/error]")
        console.print("\n[info]Set your API key:[/info]")
        console.print("  export ANTHROPIC_API_KEY=your_api_key")
        console.print("")
        console.print("[info]Or for Azure AI Foundry:[/info]")
        console.print("  export CLAUDE_CODE_USE_FOUNDRY=1")
        console.print("  (and configure Azure credentials)")

    console.print("\n[info]Built-in tools:[/info]")
    for tool in Config.ALLOWED_TOOLS:
        console.print(f"  - {tool}")

    # Check Composio integration
    console.print("\n[info]Checking Composio integration...[/info]")
    if Config.COMPOSIO_API_KEY:
        console.print("[success]COMPOSIO_API_KEY is set![/success]")
        console.print("\n[info]Configured external services:[/info]")
        for app in Config.COMPOSIO_APPS:
            console.print(f"  - {app}")
        console.print("\n[info]To connect your accounts, visit:[/info]")
        console.print("  https://app.composio.dev/apps")
    else:
        console.print("[warning]COMPOSIO_API_KEY not set (optional)[/warning]")
        console.print("\n[info]Composio enables external service integrations:[/info]")
        console.print("  Gmail, Google Calendar, Slack, GitHub, Notion, Discord, etc.")
        console.print("\n[info]To enable:[/info]")
        console.print("  1. Sign up at https://composio.dev")
        console.print("  2. Get your API key from the dashboard")
        console.print("  3. Set COMPOSIO_API_KEY in your .env file")

    console.print("\n[success]Setup check complete![/success]")
    console.print("Run 'baymax' to start the interactive mode.")


# =============================================================================
# CLI COMMANDS
# =============================================================================


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    setup: bool = typer.Option(
        False,
        "--setup",
        "-s",
        help="Run the setup wizard",
    ),
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        help="Show version information",
    ),
):
    """
    Baymax - Your Personal AI Command Center

    Run without arguments for interactive REPL mode, or use subcommands.

    Examples:
        baymax                           # Interactive mode
        baymax run "what files are here" # One-off command
        baymax --setup                   # Setup wizard
    """
    # Version
    if version:
        console.print("[baymax]Baymax[/baymax] v2.0.0")
        console.print("Powered by Claude Agent SDK")
        console.print(f"Model: {Config.MODEL_NAME}")
        console.print("Your calm, efficient personal AI assistant.")
        raise typer.Exit(0)

    # Setup mode
    if setup:
        run_setup()
        raise typer.Exit(0)

    # If a subcommand is being invoked, don't run the main logic
    if ctx.invoked_subcommand is not None:
        return

    # Start interactive REPL mode
    start_repl()


def start_repl():
    """Start the interactive REPL mode."""
    # Validate configuration
    valid, missing = Config.validate()
    if not valid:
        console.print("[error]Missing required configuration:[/error]")
        for item in missing:
            console.print(f"  - {item}")
        console.print("\n[info]Run 'baymax --setup' for help.[/info]")
        raise typer.Exit(1)

    # Interactive REPL mode
    display_welcome()
    session_id: Optional[str] = None

    while True:
        try:
            # Get user input
            user_input = Prompt.ask("\n[bold cyan]You[/bold cyan]")

            # Check for exit commands
            if user_input.lower() in ("exit", "quit", "bye", "goodbye", ":q"):
                console.print(
                    "\n[baymax]Baymax:[/baymax] Goodbye! Take care of yourself. I will always be here."
                )
                break

            # Check for empty input
            if not user_input.strip():
                continue

            # Check for help command
            if user_input.lower() in ("help", "?"):
                display_welcome()
                continue

            # Check for new session command
            if user_input.lower() in ("new", "reset", "clear"):
                session_id = None
                console.print("[info]Started a new conversation session.[/info]")
                continue

            # Process the command with spinner
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
                transient=True,
            ) as progress:
                progress.add_task("Thinking...", total=None)
                response, session_id = process_command(
                    user_input,
                    continue_conversation=True,
                    session_id=session_id,
                )

            # Display response
            console.print(f"\n[baymax]Baymax:[/baymax]")
            display_response(response)

        except KeyboardInterrupt:
            console.print("\n\n[baymax]Baymax:[/baymax] Goodbye! Take care of yourself.")
            break
        except EOFError:
            console.print("\n\n[baymax]Baymax:[/baymax] Goodbye! Take care of yourself.")
            break


# =============================================================================
# ADDITIONAL CLI COMMANDS
# =============================================================================


@app.command("run")
def run_command(
    command: str = typer.Argument(..., help="Natural language command to execute"),
):
    """Execute a one-off natural language command."""
    # Validate configuration
    valid, missing = Config.validate()
    if not valid:
        console.print("[error]Missing required configuration:[/error]")
        for item in missing:
            console.print(f"  - {item}")
        console.print("\n[info]Run 'baymax --setup' for help.[/info]")
        raise typer.Exit(1)

    # Process the command with spinner
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("Thinking...", total=None)
        response, _ = process_command(command)

    display_response(response)


@app.command("tools")
def list_tools():
    """List all available tools."""
    console.print("\n[info]Available Tools:[/info]\n")

    tool_descriptions = {
        "Read": "Read any file in the working directory",
        "Write": "Create new files",
        "Edit": "Make precise edits to existing files",
        "Bash": "Run terminal commands, scripts, git operations",
        "Glob": "Find files by pattern (e.g., **/*.py)",
        "Grep": "Search file contents with regex",
        "WebSearch": "Search the web for information",
        "WebFetch": "Fetch and parse web page content",
        "Task": "Spawn specialized subagents for complex tasks",
    }

    for tool in Config.ALLOWED_TOOLS:
        desc = tool_descriptions.get(tool, "")
        console.print(f"  [success]{tool}[/success]: {desc}")


@app.command("status")
def status():
    """Check Baymax configuration and status."""
    console.print(Panel("[baymax]Baymax Status[/baymax]", border_style="magenta"))

    # Check config
    valid, missing = Config.validate()

    console.print("\n[info]Configuration:[/info]")

    # Check Claude Code CLI
    import shutil

    cli_installed = shutil.which("claude") is not None
    console.print(
        f"  Claude Code CLI: {'[success]Installed[/success]' if cli_installed else '[error]Not Found[/error]'}"
    )

    # Check API key / Foundry
    use_foundry = os.getenv("CLAUDE_CODE_USE_FOUNDRY", "0") == "1"
    has_api_key = bool(os.getenv("ANTHROPIC_API_KEY"))

    if use_foundry:
        console.print("  Auth Mode: [info]Azure AI Foundry[/info]")
    elif has_api_key:
        console.print("  Auth Mode: [success]ANTHROPIC_API_KEY[/success]")
    else:
        console.print("  Auth Mode: [error]Not Configured[/error]")

    console.print(f"  Model: {Config.MODEL_NAME}")
    console.print(f"  Built-in Tools: {len(Config.ALLOWED_TOOLS)} available")

    # Composio status
    console.print("\n[info]External Services (Composio):[/info]")
    if Config.COMPOSIO_API_KEY:
        console.print("  Status: [success]Enabled[/success]")
        console.print(f"  Apps: {', '.join(Config.COMPOSIO_APPS)}")
    else:
        console.print("  Status: [warning]Not Configured[/warning]")
        console.print("  Run 'baymax --setup' to learn how to enable external services")

    if valid and cli_installed:
        console.print("\n[success]Baymax is ready![/success]")
    else:
        console.print("\n[error]Baymax is not fully configured. Run 'baymax --setup'.[/error]")


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    app()
