#!/usr/bin/env python3
"""
Baymax - Your Personal AI Command Center
=========================================

A calm, efficient CLI AI agent that acts as a single natural-language
command center for your digital life.

SETUP INSTRUCTIONS
------------------
1. Install dependencies:
   pip install -e .

   Or manually:
   pip install typer rich python-dotenv langchain langchain-anthropic composio-langchain

2. Create a .env file with your API keys:
   COMPOSIO_API_KEY=your_composio_api_key
   ANTHROPIC_API_KEY=your_anthropic_api_key

3. Run Baymax setup to connect your accounts:
   baymax --setup

   Or: python baymax.py --setup

4. Start using Baymax:
   baymax                      # Interactive REPL mode
   baymax "read my emails"     # One-off command mode

USAGE EXAMPLES
--------------
- "read my unread emails"
- "summarize my inbox"
- "post to X: Hello from Baymax!"
- "show my calendar today"
- "create a task: Buy groceries"
- "send a message on Discord to #general: Hello!"

Author: Your friendly AI assistant
License: MIT
"""

import os
import sys
from typing import Optional, List, Any
from enum import Enum

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.theme import Theme
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
)

# =============================================================================
# CONFIGURATION
# =============================================================================


class Config:
    """Configuration management for Baymax."""

    # Required
    COMPOSIO_API_KEY: str = os.getenv("COMPOSIO_API_KEY", "")

    # Anthropic API Configuration
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")

    # Model configuration (Claude 3.5 Haiku)
    MODEL_NAME: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

    # Composio apps to load (easily extensible)
    COMPOSIO_APPS: List[str] = [
        "GMAIL",
        "GOOGLECALENDAR",
        "DISCORD",
        "REDDIT",
        "LINKEDIN",
        "GOOGLETASKS",
        "NOTION",
        "TWITTER",  # X (formerly Twitter)
        "GITHUB",
    ]

    # System prompt for the AI agent
    SYSTEM_PROMPT: str = """You are Baymax, a calm, efficient personal assistant. 

Your personality:
- Calm and reassuring, like the character from Big Hero 6
- Concise and helpful - no unnecessary fluff
- Action-oriented - use tools when needed
- Honest - if you can't do something, say so clearly

Guidelines:
- Use tools when needed to accomplish tasks
- Keep responses short and actionable
- Format responses nicely for terminal display
- If a tool fails, explain what went wrong clearly
- Never hallucinate or make up information
- When listing items (emails, tasks, events), format them clearly

Remember: You are here to help manage the user's digital life efficiently."""

    @classmethod
    def validate(cls) -> tuple[bool, List[str]]:
        """Validate configuration and return status with missing items."""
        missing = []

        if not cls.COMPOSIO_API_KEY:
            missing.append("COMPOSIO_API_KEY")

        if not cls.ANTHROPIC_API_KEY:
            missing.append("ANTHROPIC_API_KEY")

        return len(missing) == 0, missing


# =============================================================================
# COMPOSIO TOOL LOADER
# =============================================================================


class ToolLoader:
    """Dynamic tool loader for Composio integrations."""

    def __init__(self):
        self._toolset = None
        self._tools = None

    def load_tools(self, apps: Optional[List[str]] = None) -> List[Any]:
        """Load tools from Composio for specified apps."""
        if self._tools is not None:
            return self._tools

        try:
            from composio_langchain import ComposioToolSet, App, Action

            self._toolset = ComposioToolSet(api_key=Config.COMPOSIO_API_KEY)

            apps_to_load = apps or Config.COMPOSIO_APPS

            # Load tools for each app
            all_tools = []
            for app_name in apps_to_load:
                try:
                    app_enum = getattr(App, app_name, None)
                    if app_enum:
                        tools = self._toolset.get_tools(apps=[app_enum])
                        all_tools.extend(tools)
                except Exception as e:
                    console.print(f"[warning]Could not load {app_name}: {e}[/warning]")

            self._tools = all_tools
            return self._tools

        except ImportError:
            console.print(
                "[error]Composio not installed. Run: pip install composio-langchain[/error]"
            )
            return []
        except Exception as e:
            console.print(f"[error]Failed to load Composio tools: {e}[/error]")
            return []

    @property
    def toolset(self):
        return self._toolset


tool_loader = ToolLoader()


# =============================================================================
# LLM SETUP
# =============================================================================


def get_llm():
    """Get the configured LLM (Anthropic Claude 3.5 Haiku)."""
    try:
        from langchain_anthropic import ChatAnthropic

        llm = ChatAnthropic(
            model=Config.MODEL_NAME,
            base_url=Config.TARGET_URL,
            api_key=Config.API_KEY,
            temperature=0,
            max_tokens=2048,
        )
        return llm

    except ImportError:
        console.print(
            "[error]langchain-anthropic not installed. Run: pip install langchain-anthropic[/error]"
        )
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[error]Failed to initialize LLM: {e}[/error]")
        raise typer.Exit(1)


# =============================================================================
# AGENT SETUP
# =============================================================================


def create_agent():
    """Create the Baymax agent with tools."""
    try:
        from langchain.agents import create_tool_calling_agent, AgentExecutor
        from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

        # Load LLM
        llm = get_llm()

        # Load Composio tools
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            progress.add_task("Loading tools...", total=None)
            tools = tool_loader.load_tools()

        if not tools:
            console.print("[warning]No tools loaded. Some features may not work.[/warning]")
            console.print("[info]Run 'baymax --setup' to connect your accounts.[/info]")

        # Create prompt
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", Config.SYSTEM_PROMPT),
                MessagesPlaceholder(variable_name="chat_history", optional=True),
                ("human", "{input}"),
                MessagesPlaceholder(variable_name="agent_scratchpad"),
            ]
        )

        # Create agent
        if tools:
            agent = create_tool_calling_agent(llm, tools, prompt)
            agent_executor = AgentExecutor(
                agent=agent,
                tools=tools,
                verbose=False,
                handle_parsing_errors=True,
                max_iterations=10,
            )
        else:
            # Fallback to simple LLM if no tools
            agent_executor = None

        return agent_executor, llm, tools

    except Exception as e:
        console.print(f"[error]Failed to create agent: {e}[/error]")
        raise typer.Exit(1)


# =============================================================================
# CORE FUNCTIONS
# =============================================================================


def process_command(command: str, agent_executor, llm, chat_history: List = None) -> str:
    """Process a natural language command and return the response."""
    chat_history = chat_history or []

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            progress.add_task("Thinking...", total=None)

            if agent_executor:
                result = agent_executor.invoke(
                    {
                        "input": command,
                        "chat_history": chat_history,
                    }
                )
                return result.get("output", "I processed your request but have no response.")
            else:
                # Fallback to simple LLM
                response = llm.invoke(command)
                return response.content

    except Exception as e:
        error_msg = str(e).lower()

        # Friendly error messages
        if "authentication" in error_msg or "auth" in error_msg or "401" in error_msg:
            return "Authentication failed. Please run `baymax --setup` to reconnect your accounts."
        elif "rate limit" in error_msg or "429" in error_msg:
            return "Rate limit reached. Please wait a moment and try again."
        elif "network" in error_msg or "connection" in error_msg:
            return "Network error. Please check your internet connection and try again."
        elif "not found" in error_msg or "404" in error_msg:
            return "The requested resource was not found. Please check your request and try again."
        else:
            return f"An error occurred: {e}\n\nIf this persists, try running `baymax --setup`."


def display_welcome():
    """Display welcome message."""
    welcome_text = """
# Hello! I am Baymax, your personal healthcare— I mean, *digital life* companion.

I can help you with:
- **Email**: "read my unread emails", "summarize my inbox"
- **Calendar**: "show my calendar today", "what's on my schedule tomorrow"
- **Tasks**: "create a task: Buy groceries", "show my tasks"
- **Social**: "post to X: Hello world!", "check my Discord messages"
- **And more**: GitHub, Reddit, LinkedIn, Notion...

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
    # Try to render as markdown
    try:
        md = Markdown(response)
        console.print(Panel(md, border_style="cyan", padding=(0, 1)))
    except Exception:
        console.print(Panel(response, border_style="cyan", padding=(0, 1)))


# =============================================================================
# SETUP COMMAND
# =============================================================================


def run_setup():
    """Interactive setup wizard for Composio connections."""
    console.print(
        Panel(
            "[baymax]Baymax Setup Wizard[/baymax]\n\n"
            "Let's connect your accounts so I can help you manage your digital life.",
            border_style="magenta",
        )
    )

    # Check for Anthropic API key
    if not Config.ANTHROPIC_API_KEY:
        console.print("\n[error]ANTHROPIC_API_KEY not found![/error]")
        console.print("\n[info]To get your Anthropic API key:[/info]")
        console.print("1. Go to https://console.anthropic.com")
        console.print("2. Sign up or log in")
        console.print("3. Create an API key")
        console.print("4. Add it to your .env file: ANTHROPIC_API_KEY=your_key_here")
        console.print("")

    # Check for Composio API key
    if not Config.COMPOSIO_API_KEY:
        console.print("\n[error]COMPOSIO_API_KEY not found![/error]")
        console.print("\n[info]To get your Composio API key:[/info]")
        console.print("1. Go to https://app.composio.dev")
        console.print("2. Sign up or log in")
        console.print("3. Copy your API key from the dashboard")
        console.print("4. Add it to your .env file: COMPOSIO_API_KEY=your_key_here")
        return

    try:
        from composio import ComposioToolSet, App

        toolset = ComposioToolSet(api_key=Config.COMPOSIO_API_KEY)

        console.print("\n[success]Composio API key found![/success]\n")

        # Show available apps
        console.print("[info]Available integrations:[/info]")
        for i, app in enumerate(Config.COMPOSIO_APPS, 1):
            console.print(f"  {i}. {app}")

        console.print("\n[info]To connect an app, run:[/info]")
        console.print("  composio add <app_name>")
        console.print("\n[info]Examples:[/info]")
        console.print("  composio add gmail")
        console.print("  composio add googlecalendar")
        console.print("  composio add github")
        console.print("  composio add twitter")
        console.print("  composio add discord")

        # Check connected apps
        console.print("\n[info]Checking connected apps...[/info]")
        try:
            entity = toolset.get_entity()
            connections = entity.get_connections()

            if connections:
                console.print("\n[success]Connected apps:[/success]")
                for conn in connections:
                    console.print(f"  - {conn.appUniqueId}")
            else:
                console.print("\n[warning]No apps connected yet.[/warning]")
                console.print("Run 'composio add <app_name>' to connect your first app!")

        except Exception as e:
            console.print(f"\n[warning]Could not check connections: {e}[/warning]")

        console.print("\n[success]Setup complete! You can now use Baymax.[/success]")
        console.print("Run 'baymax' to start the interactive mode.")

    except ImportError:
        console.print("[error]Composio not installed. Run: pip install composio-langchain[/error]")
    except Exception as e:
        console.print(f"[error]Setup error: {e}[/error]")


# =============================================================================
# CLI COMMANDS
# =============================================================================


@app.command()
def main(
    command: Optional[str] = typer.Argument(
        None,
        help="Natural language command to execute (omit for interactive mode)",
    ),
    setup: bool = typer.Option(
        False,
        "--setup",
        "-s",
        help="Run the setup wizard to connect your accounts",
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

    Run without arguments for interactive REPL mode, or pass a command directly.

    Examples:
        baymax                           # Interactive mode
        baymax "read my unread emails"   # One-off command
        baymax --setup                   # Setup wizard
    """
    # Version
    if version:
        console.print("[baymax]Baymax[/baymax] v1.0.0")
        console.print(f"Using model: {Config.MODEL_NAME}")
        console.print("Your calm, efficient personal AI assistant.")
        raise typer.Exit(0)

    # Setup mode
    if setup:
        run_setup()
        raise typer.Exit(0)

    # Validate configuration
    valid, missing = Config.validate()
    if not valid:
        console.print("[error]Missing required configuration:[/error]")
        for item in missing:
            console.print(f"  - {item}")
        console.print("\n[info]Please add these to your .env file.[/info]")
        console.print("Run 'baymax --setup' for help.")
        raise typer.Exit(1)

    # Create agent
    try:
        agent_executor, llm, tools = create_agent()
    except Exception as e:
        console.print(f"[error]Failed to initialize: {e}[/error]")
        raise typer.Exit(1)

    # One-off command mode
    if command:
        response = process_command(command, agent_executor, llm)
        display_response(response)
        raise typer.Exit(0)

    # Interactive REPL mode
    display_welcome()
    chat_history = []

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

            # Process the command
            response = process_command(user_input, agent_executor, llm, chat_history)

            # Display response
            console.print(f"\n[baymax]Baymax:[/baymax]")
            display_response(response)

            # Update chat history (keep last 10 exchanges)
            from langchain_core.messages import HumanMessage, AIMessage

            chat_history.append(HumanMessage(content=user_input))
            chat_history.append(AIMessage(content=response))
            if len(chat_history) > 20:
                chat_history = chat_history[-20:]

        except KeyboardInterrupt:
            console.print("\n\n[baymax]Baymax:[/baymax] Goodbye! Take care of yourself.")
            break
        except EOFError:
            console.print("\n\n[baymax]Baymax:[/baymax] Goodbye! Take care of yourself.")
            break


# =============================================================================
# ADDITIONAL CLI COMMANDS
# =============================================================================


@app.command("apps")
def list_apps():
    """List all supported Composio apps."""
    console.print("\n[info]Supported Composio Apps:[/info]\n")
    for app in Config.COMPOSIO_APPS:
        console.print(f"  - {app}")
    console.print("\n[info]To connect an app, run: composio add <app_name>[/info]")


@app.command("status")
def status():
    """Check Baymax configuration and connection status."""
    console.print(Panel("[baymax]Baymax Status[/baymax]", border_style="magenta"))

    # Check config
    valid, missing = Config.validate()

    console.print("\n[info]Configuration:[/info]")
    console.print(
        f"  COMPOSIO_API_KEY: {'[success]Set[/success]' if Config.COMPOSIO_API_KEY else '[error]Missing[/error]'}"
    )
    console.print(
        f"  ANTHROPIC_API_KEY: {'[success]Set[/success]' if Config.ANTHROPIC_API_KEY else '[error]Missing[/error]'}"
    )
    console.print(f"  Model: {Config.MODEL_NAME}")

    if valid:
        console.print("\n[success]All required configuration is present![/success]")
    else:
        console.print("\n[error]Missing required configuration. Run 'baymax --setup'.[/error]")

    # Check Composio connections
    if Config.COMPOSIO_API_KEY:
        try:
            from composio import ComposioToolSet

            toolset = ComposioToolSet(api_key=Config.COMPOSIO_API_KEY)
            entity = toolset.get_entity()
            connections = entity.get_connections()

            console.print("\n[info]Connected Apps:[/info]")
            if connections:
                for conn in connections:
                    console.print(f"  [success]✓[/success] {conn.appUniqueId}")
            else:
                console.print("  [warning]No apps connected[/warning]")

        except Exception as e:
            console.print(f"\n[warning]Could not check connections: {e}[/warning]")


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    app()
