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
   pip install typer rich python-dotenv anthropic composio

2. Create a .env file with your API keys:

   For direct Anthropic API:
     ANTHROPIC_API_KEY=your_api_key
     COMPOSIO_API_KEY=your_composio_api_key

   For Azure AI Foundry:
     USE_FOUNDRY=1
     ANTHROPIC_FOUNDRY_API_KEY=your_foundry_api_key
     ANTHROPIC_FOUNDRY_RESOURCE=your-resource-name
     COMPOSIO_API_KEY=your_composio_api_key

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
import json
from typing import Optional, List, Any, Dict

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
    invoke_without_command=True,
)

# =============================================================================
# CONFIGURATION
# =============================================================================


class Config:
    """Configuration management for Baymax."""

    # Required
    COMPOSIO_API_KEY: str = os.getenv("COMPOSIO_API_KEY", "")

    # Anthropic direct API key (mutually exclusive with Foundry)
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")

    # Azure AI Foundry configuration
    # Set USE_FOUNDRY=1 to use Azure AI Foundry instead of direct Anthropic
    USE_FOUNDRY: bool = os.getenv("USE_FOUNDRY", "0") == "1"

    # Foundry credentials (only used when USE_FOUNDRY=1)
    # API key for Foundry
    ANTHROPIC_FOUNDRY_API_KEY: str = os.getenv("ANTHROPIC_FOUNDRY_API_KEY", "")
    # Resource name (e.g., "my-resource" -> https://my-resource.services.ai.azure.com/anthropic/)
    ANTHROPIC_FOUNDRY_RESOURCE: str = os.getenv("ANTHROPIC_FOUNDRY_RESOURCE", "")

    # Model configuration
    MODEL_NAME: str = os.getenv("MODEL_NAME", "claude-sonnet-4-5-20250929")

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

        if cls.USE_FOUNDRY:
            # Foundry mode - need Foundry API key and resource
            if not cls.ANTHROPIC_FOUNDRY_API_KEY:
                missing.append("ANTHROPIC_FOUNDRY_API_KEY")
            if not cls.ANTHROPIC_FOUNDRY_RESOURCE:
                missing.append("ANTHROPIC_FOUNDRY_RESOURCE")
        else:
            # Direct Anthropic mode
            if not cls.ANTHROPIC_API_KEY:
                missing.append("ANTHROPIC_API_KEY")

        return len(missing) == 0, missing


# =============================================================================
# COMPOSIO TOOL LOADER
# =============================================================================


class ToolLoader:
    """Dynamic tool loader for Composio integrations.

    Converts Composio tools to Anthropic SDK ToolParam format.
    """

    def __init__(self):
        self._client = None
        self._tools = None
        self._tool_map: Dict[str, Any] = {}  # Maps tool name to callable
        # External user ID - this should match your Composio user ID
        self._user_id = os.getenv("COMPOSIO_USER_ID", "default")

    def _get_user_id_from_accounts(self) -> str:
        """Get the user_id from connected accounts if not set via env."""
        if self._user_id != "default":
            return self._user_id

        try:
            response = self._client.connected_accounts.list()
            items = getattr(response, "items", [])

            for conn in items:
                if getattr(conn, "status", None) == "ACTIVE":
                    user_id = getattr(conn, "user_id", None)
                    if user_id:
                        return user_id

            return "default"
        except Exception:
            return "default"

    def _get_allowed_tools_from_mcp(self) -> List[str]:
        """Get the list of allowed tools from MCP configurations."""
        try:
            # Get all MCP configs (paginated)
            all_mcps = []
            page_no = 1

            while True:
                response = self._client.mcp.list(page_no=page_no)
                items = response.get("items", [])
                all_mcps.extend(items)

                current_page = response.get("current_page", 1)
                total_pages = response.get("total_pages", 1)

                if current_page >= total_pages:
                    break
                page_no += 1

            # Extract all allowed tools from MCP configs
            all_allowed_tools = []
            for mcp in all_mcps:
                tools = getattr(mcp, "allowed_tools", [])
                all_allowed_tools.extend(tools)

            return list(set(all_allowed_tools))  # Deduplicate

        except Exception as e:
            console.print(f"[warning]Could not load MCP configs: {e}[/warning]")
            return []

    def _sanitize_tool_name(self, name: str) -> str:
        """Sanitize tool name to match Anthropic's pattern: ^[a-zA-Z0-9_-]{1,128}$"""
        import re

        # Replace any invalid characters with underscores
        sanitized = re.sub(r"[^a-zA-Z0-9_-]", "_", name)

        # Remove consecutive underscores
        sanitized = re.sub(r"_+", "_", sanitized)

        # Remove leading/trailing underscores
        sanitized = sanitized.strip("_-")

        # Truncate to 128 characters
        if len(sanitized) > 128:
            sanitized = sanitized[:128].rstrip("_-")

        # Ensure it's not empty
        if not sanitized:
            sanitized = "tool"

        return sanitized

    def _convert_to_anthropic_tool(self, composio_tool: Any) -> Dict[str, Any]:
        """Convert a Composio tool to Anthropic ToolParam format."""
        # Get original tool name
        original_name = getattr(composio_tool, "name", str(composio_tool))

        # Sanitize tool name to match Anthropic's requirements
        tool_name = self._sanitize_tool_name(original_name)

        # Get description and truncate if needed (no hard limit but keep reasonable)
        description = getattr(composio_tool, "description", "")
        if len(description) > 1024:
            description = description[:1021] + "..."

        # Composio tools have name, description, and input schema
        tool_dict = {
            "name": tool_name,
            "description": description,
            "input_schema": getattr(
                composio_tool, "input_schema", {"type": "object", "properties": {}}
            ),
        }
        return tool_dict

    def load_tools(self, apps: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Load tools from Composio and convert to Anthropic format."""
        if self._tools is not None:
            return self._tools

        try:
            from composio import Composio

            # Initialize Composio client
            self._client = Composio(api_key=Config.COMPOSIO_API_KEY)

            # Get the correct user_id
            self._user_id = self._get_user_id_from_accounts()

            # Get allowed tools from MCP configurations
            allowed_tools = self._get_allowed_tools_from_mcp()

            anthropic_tools = []

            if allowed_tools:
                console.print(
                    f"[info]Loading {len(allowed_tools)} tools from MCP configs...[/info]"
                )

                try:
                    tools = self._client.tools.get(
                        user_id=self._user_id,
                        tools=allowed_tools,
                    )
                    composio_tools = list(tools) if tools else []

                    for tool in composio_tools:
                        anthropic_tool = self._convert_to_anthropic_tool(tool)
                        anthropic_tools.append(anthropic_tool)
                        self._tool_map[anthropic_tool["name"]] = tool

                except Exception as e:
                    console.print(f"[warning]Could not load tools: {e}[/warning]")
            else:
                # Fallback: load tools for each app if no MCP configs found
                console.print("[info]No MCP configs found, loading default tools...[/info]")
                apps_to_load = apps or Config.COMPOSIO_APPS
                toolkits = [app.lower() for app in apps_to_load]

                for toolkit in toolkits:
                    try:
                        tools = self._client.tools.get(
                            user_id=self._user_id,
                            toolkits=[toolkit],
                        )
                        toolkit_tools = list(tools) if tools else []

                        for tool in toolkit_tools:
                            anthropic_tool = self._convert_to_anthropic_tool(tool)
                            anthropic_tools.append(anthropic_tool)
                            self._tool_map[anthropic_tool["name"]] = tool

                    except Exception as e:
                        console.print(f"[warning]Could not load {toolkit} tools: {e}[/warning]")

            self._tools = anthropic_tools
            return self._tools

        except ImportError:
            console.print("[error]Composio not installed. Run: pip install composio[/error]")
            return []
        except Exception as e:
            console.print(f"[error]Failed to load Composio tools: {e}[/error]")
            return []

    def execute_tool(self, tool_name: str, tool_input: Dict[str, Any]) -> str:
        """Execute a tool by name with the given input."""
        if tool_name not in self._tool_map:
            return f"Error: Tool '{tool_name}' not found"

        try:
            tool = self._tool_map[tool_name]
            # Composio tools are callable
            result = tool.run(tool_input)

            if isinstance(result, dict):
                return json.dumps(result, indent=2)
            return str(result)
        except Exception as e:
            return f"Error executing tool '{tool_name}': {e}"

    @property
    def client(self):
        return self._client

    @property
    def user_id(self):
        return self._user_id

    @property
    def tool_map(self):
        return self._tool_map


tool_loader = ToolLoader()


# =============================================================================
# ANTHROPIC CLIENT SETUP
# =============================================================================


def get_anthropic_client():
    """Get the configured Anthropic client.

    Supports:
    - Direct Anthropic API (default)
    - Azure AI Foundry (set USE_FOUNDRY=1)
    """
    try:
        if Config.USE_FOUNDRY:
            # Use Azure AI Foundry client
            from anthropic import AnthropicFoundry

            client = AnthropicFoundry(
                api_key=Config.ANTHROPIC_FOUNDRY_API_KEY,
                resource=Config.ANTHROPIC_FOUNDRY_RESOURCE,
            )
            console.print(
                f"[info]Using Azure AI Foundry: {Config.ANTHROPIC_FOUNDRY_RESOURCE}[/info]"
            )
        else:
            # Use standard Anthropic client
            from anthropic import Anthropic

            client = Anthropic(api_key=Config.ANTHROPIC_API_KEY)

        return client

    except ImportError as e:
        console.print(f"[error]anthropic not installed: {e}[/error]")
        console.print("[info]Run: pip install anthropic[/info]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[error]Failed to initialize Anthropic client: {e}[/error]")
        raise typer.Exit(1)


# =============================================================================
# CORE FUNCTIONS
# =============================================================================


def process_command(
    command: str,
    client,
    tools: List[Dict[str, Any]],
    chat_history: List[Dict[str, Any]] = None,
) -> str:
    """Process a natural language command using Anthropic SDK with tool use."""
    chat_history = chat_history or []

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            progress.add_task("Thinking...", total=None)

            # Build messages list
            messages = chat_history.copy()
            messages.append({"role": "user", "content": command})

            # Initial API call
            response = client.messages.create(
                model=Config.MODEL_NAME,
                max_tokens=2048,
                system=Config.SYSTEM_PROMPT,
                tools=tools if tools else None,
                messages=messages,
            )

        # Handle tool use loop (agentic behavior)
        while response.stop_reason == "tool_use":
            # Extract tool use blocks
            tool_uses = [block for block in response.content if block.type == "tool_use"]

            # Execute each tool and collect results
            tool_results = []
            for tool_use in tool_uses:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=console,
                    transient=True,
                ) as progress:
                    progress.add_task(f"Running {tool_use.name}...", total=None)

                    result = tool_loader.execute_tool(tool_use.name, tool_use.input)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_use.id,
                            "content": result,
                        }
                    )

            # Add assistant response and tool results to messages
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

            # Continue the conversation
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
                transient=True,
            ) as progress:
                progress.add_task("Thinking...", total=None)

                response = client.messages.create(
                    model=Config.MODEL_NAME,
                    max_tokens=2048,
                    system=Config.SYSTEM_PROMPT,
                    tools=tools if tools else None,
                    messages=messages,
                )

        # Extract final text response
        text_blocks = [block.text for block in response.content if hasattr(block, "text")]
        return (
            "\n".join(text_blocks)
            if text_blocks
            else "I processed your request but have no response."
        )

    except Exception as e:
        error_msg = str(e).lower()

        # Friendly error messages
        if "authentication" in error_msg or "auth" in error_msg or "401" in error_msg:
            return "Authentication failed. Please check your API key or Azure credentials."
        elif "rate limit" in error_msg or "429" in error_msg:
            return "Rate limit reached. Please wait a moment and try again."
        elif "network" in error_msg or "connection" in error_msg:
            return "Network error. Please check your internet connection and try again."
        elif "not found" in error_msg or "404" in error_msg:
            return "The requested resource was not found. Please check your request and try again."
        else:
            return f"An error occurred: {e}\n\nIf this persists, check your API keys and try again."


def display_welcome():
    """Display welcome message."""
    welcome_text = """
# Hello! I am Baymax, your personal healthcare-- I mean, *digital life* companion.

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

    # Check for Anthropic/Foundry configuration
    if Config.USE_FOUNDRY:
        console.print("\n[info]Azure AI Foundry mode enabled (USE_FOUNDRY=1)[/info]")
        if not Config.ANTHROPIC_FOUNDRY_API_KEY:
            console.print("[error]ANTHROPIC_FOUNDRY_API_KEY not found![/error]")
        else:
            console.print("[success]ANTHROPIC_FOUNDRY_API_KEY: Set[/success]")
        if not Config.ANTHROPIC_FOUNDRY_RESOURCE:
            console.print("[error]ANTHROPIC_FOUNDRY_RESOURCE not found![/error]")
        else:
            console.print(
                f"[success]ANTHROPIC_FOUNDRY_RESOURCE: {Config.ANTHROPIC_FOUNDRY_RESOURCE}[/success]"
            )
        console.print("")
    elif not Config.ANTHROPIC_API_KEY:
        console.print("\n[error]ANTHROPIC_API_KEY not found![/error]")
        console.print("\n[info]For direct Anthropic API, add to .env:[/info]")
        console.print("  ANTHROPIC_API_KEY=your_api_key_here")
        console.print("")
        console.print("[info]For Azure AI Foundry, add to .env:[/info]")
        console.print("  USE_FOUNDRY=1")
        console.print("  ANTHROPIC_FOUNDRY_API_KEY=your_foundry_api_key")
        console.print("  ANTHROPIC_FOUNDRY_RESOURCE=your-resource-name")
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
        from composio import Composio

        client = Composio(api_key=Config.COMPOSIO_API_KEY)

        console.print("\n[success]Composio API key found![/success]\n")

        # Show available apps
        console.print("[info]Available integrations:[/info]")
        for i, app in enumerate(Config.COMPOSIO_APPS, 1):
            console.print(f"  {i}. {app}")

        console.print("\n[info]To connect an app:[/info]")
        console.print("  1. Go to https://app.composio.dev/apps")
        console.print("  2. Find the app you want to connect (e.g., Gmail, Google Calendar)")
        console.print("  3. Click 'Connect' and follow the OAuth flow")
        console.print("  4. Your connected accounts will appear in your dashboard")

        # Check connected apps
        console.print("\n[info]Checking connected apps...[/info]")
        try:
            # Fetch all pages of connected accounts
            all_items = []
            response = client.connected_accounts.list()
            all_items.extend(getattr(response, "items", []) or [])

            # Paginate through all results
            while getattr(response, "next_cursor", None):
                response = client.connected_accounts.list(cursor=response.next_cursor)
                all_items.extend(getattr(response, "items", []) or [])

            # Filter to only ACTIVE connections and get unique toolkits
            active_toolkits = set()
            for conn in all_items:
                status = getattr(conn, "status", None)
                if status == "ACTIVE":
                    toolkit = getattr(conn, "toolkit", None)
                    if toolkit:
                        # toolkit is an object with a 'slug' attribute
                        slug = getattr(toolkit, "slug", None) or str(toolkit)
                        active_toolkits.add(slug)

            if active_toolkits:
                console.print("\n[success]Connected apps:[/success]")
                for toolkit in sorted(active_toolkits):
                    console.print(f"  [success]v[/success] {toolkit}")
            else:
                console.print("\n[warning]No apps connected yet.[/warning]")
                console.print("Visit https://app.composio.dev/apps to connect your first app!")

        except Exception as e:
            console.print(f"\n[warning]Could not check connections: {e}[/warning]")

        console.print("\n[success]Setup complete! You can now use Baymax.[/success]")
        console.print("Run 'baymax' to start the interactive mode.")

    except ImportError:
        console.print("[error]Composio not installed. Run: pip install composio[/error]")
    except Exception as e:
        console.print(f"[error]Setup error: {e}[/error]")


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

    Run without arguments for interactive REPL mode, or use subcommands.

    Examples:
        baymax                           # Interactive mode
        baymax run "read my emails"      # One-off command
        baymax --setup                   # Setup wizard
    """
    # Version
    if version:
        console.print("[baymax]Baymax[/baymax] v1.0.0")
        console.print(f"Using model: {Config.MODEL_NAME}")
        console.print("Powered by Anthropic Claude SDK")
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
        console.print("\n[info]Please add these to your .env file.[/info]")
        console.print("Run 'baymax --setup' for help.")
        raise typer.Exit(1)

    # Initialize Anthropic client
    try:
        client = get_anthropic_client()
    except Exception as e:
        console.print(f"[error]Failed to initialize Anthropic client: {e}[/error]")
        raise typer.Exit(1)

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

    # Interactive REPL mode
    display_welcome()
    chat_history: List[Dict[str, Any]] = []

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
            response = process_command(user_input, client, tools, chat_history)

            # Display response
            console.print(f"\n[baymax]Baymax:[/baymax]")
            display_response(response)

            # Update chat history (keep last 10 exchanges = 20 messages)
            chat_history.append({"role": "user", "content": user_input})
            chat_history.append({"role": "assistant", "content": response})
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
        console.print("\n[info]Please add these to your .env file.[/info]")
        console.print("Run 'baymax --setup' for help.")
        raise typer.Exit(1)

    # Initialize client and tools
    try:
        client = get_anthropic_client()
        tools = tool_loader.load_tools()
    except Exception as e:
        console.print(f"[error]Failed to initialize: {e}[/error]")
        raise typer.Exit(1)

    # Process the command
    response = process_command(command, client, tools)
    display_response(response)


@app.command("apps")
def list_apps():
    """List all supported Composio apps."""
    console.print("\n[info]Supported Composio Apps:[/info]\n")
    for app in Config.COMPOSIO_APPS:
        console.print(f"  - {app}")
    console.print("\n[info]Connect apps at: https://app.composio.dev/apps[/info]")


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
    if Config.USE_FOUNDRY:
        console.print("  Mode: [info]Azure AI Foundry[/info]")
        console.print(
            f"  ANTHROPIC_FOUNDRY_API_KEY: {'[success]Set[/success]' if Config.ANTHROPIC_FOUNDRY_API_KEY else '[error]Missing[/error]'}"
        )
        console.print(
            f"  ANTHROPIC_FOUNDRY_RESOURCE: {'[success]' + Config.ANTHROPIC_FOUNDRY_RESOURCE + '[/success]' if Config.ANTHROPIC_FOUNDRY_RESOURCE else '[error]Missing[/error]'}"
        )
    else:
        console.print("  Mode: [info]Direct Anthropic API[/info]")
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
            from composio import Composio

            client = Composio(api_key=Config.COMPOSIO_API_KEY)

            # Fetch all pages of connected accounts
            all_items = []
            response = client.connected_accounts.list()
            all_items.extend(getattr(response, "items", []) or [])

            while getattr(response, "next_cursor", None):
                response = client.connected_accounts.list(cursor=response.next_cursor)
                all_items.extend(getattr(response, "items", []) or [])

            # Filter to only ACTIVE connections and get unique toolkits
            active_toolkits = set()
            for conn in all_items:
                status_val = getattr(conn, "status", None)
                if status_val == "ACTIVE":
                    toolkit = getattr(conn, "toolkit", None)
                    if toolkit:
                        slug = getattr(toolkit, "slug", None) or str(toolkit)
                        active_toolkits.add(slug)

            console.print("\n[info]Connected Apps:[/info]")
            if active_toolkits:
                for toolkit in sorted(active_toolkits):
                    console.print(f"  [success]v[/success] {toolkit}")
            else:
                console.print("  [warning]No apps connected[/warning]")

        except Exception as e:
            console.print(f"\n[warning]Could not check connections: {e}[/warning]")


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    app()
