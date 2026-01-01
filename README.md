# Baymax - Your Personal AI Command Center

A calm, efficient CLI AI agent that acts as a single natural-language command center for your digital life.

## Features

- **Natural Language Interface**: Just tell Baymax what you want in plain English
- **Interactive REPL Mode**: Have a conversation with your assistant
- **One-off Commands**: Quick commands like `baymax "read my emails"`
- **Beautiful Terminal UI**: Powered by Rich for colorful, markdown-rendered output
- **Multiple Integrations**: Gmail, Google Calendar, Discord, Reddit, LinkedIn, Google Tasks, Notion, X (Twitter), GitHub
- **Easily Extensible**: Add new Composio apps with a single line of config

## Quick Start

### 1. Clone & Set Up Virtual Environment

```bash
# Clone the repository
git clone https://github.com/yourusername/baymax.git
cd baymax

# Create a virtual environment
python3 -m venv venv

# Activate the virtual environment
# On macOS/Linux:
source venv/bin/activate

# On Windows:
# venv\Scripts\activate
```

### 2. Install Dependencies

```bash
# Option A: Install with pip (recommended for development)
pip install -e .

# Option B: Install from requirements.txt
pip install -r requirements.txt
```

### 3. Configure

```bash
# Copy the example environment file
cp .env.example .env

# Edit .env with your API keys
```

Required environment variables:
- `COMPOSIO_API_KEY` - Get from [Composio](https://app.composio.dev)
- `ANTHROPIC_API_KEY` - Get from [Anthropic Console](https://console.anthropic.com)

### 4. Connect Your Accounts

```bash
# Run the setup wizard to check your configuration
baymax --setup
```

Then connect your apps via the Composio web dashboard:
1. Go to [app.composio.dev/apps](https://app.composio.dev/apps)
2. Find the app you want to connect (Gmail, Google Calendar, GitHub, etc.)
3. Click "Connect" and complete the OAuth flow
4. Your connected accounts will be available to Baymax

### 5. Start Using Baymax

```bash
# Interactive mode (REPL)
baymax

# One-off command
baymax run "read my unread emails"
baymax run "what's on my calendar today?"
baymax run "post to X: Hello from Baymax!"
```

## Usage Examples

### Email
```bash
baymax run "read my unread emails"
baymax run "summarize my inbox"
baymax run "search emails from john@example.com"
```

### Calendar
```bash
baymax run "show my calendar today"
baymax run "what meetings do I have tomorrow?"
baymax run "schedule a meeting with Bob at 3pm on Friday"
```

### Tasks
```bash
baymax run "show my tasks"
baymax run "create a task: Buy groceries"
baymax run "mark task 1 as complete"
```

### Social Media
```bash
baymax run "post to X: Hello world!"
baymax run "check my Discord messages"
baymax run "show my Reddit notifications"
```

### GitHub
```bash
baymax run "show my GitHub notifications"
baymax run "list my open pull requests"
baymax run "show issues assigned to me"
```

## CLI Commands

```bash
baymax                        # Start interactive REPL mode
baymax run "your command"     # One-off command execution
baymax --setup                # Run the setup wizard
baymax --version              # Show version
baymax apps                   # List all supported apps
baymax status                 # Check configuration and connections
```

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `COMPOSIO_API_KEY` | Yes | Your Composio API key |
| `ANTHROPIC_API_KEY` | Yes | Your Anthropic API key |
| `ANTHROPIC_MODEL` | No | Model name (default: claude-sonnet-4-5) |

### Adding New Integrations

Edit `baymax.py` and add the app name to `Config.COMPOSIO_APPS`:

```python
COMPOSIO_APPS: List[str] = [
    "GMAIL",
    "GOOGLECALENDAR",
    # ... existing apps ...
    "YOUR_NEW_APP",  # Add new apps here
]
```

Then connect the app:
```bash
composio add your_new_app
```

## Supported Apps

- **GMAIL** - Email management
- **GOOGLECALENDAR** - Calendar and events
- **GOOGLETASKS** - Task management
- **DISCORD** - Discord messaging
- **REDDIT** - Reddit browsing and posting
- **LINKEDIN** - LinkedIn interactions
- **NOTION** - Notion workspace
- **TWITTER** - X (formerly Twitter)
- **GITHUB** - GitHub repositories and issues

## Troubleshooting

### "COMPOSIO_API_KEY not found"
Make sure you have created a `.env` file with your Composio API key. Get your key from [app.composio.dev](https://app.composio.dev).

### "Authentication failed"
Run `baymax --setup` and reconnect the affected app using `composio add <app_name>`.

### "No tools loaded"
This usually means no apps are connected. Run:
```bash
composio add gmail
composio add googlecalendar
# etc.
```

### Rate Limiting
If you hit rate limits, wait a moment and try again. Consider upgrading your API tier if this happens frequently.

## Development

```bash
# Make sure venv is activated
source venv/bin/activate

# Install with dev dependencies
pip install -e ".[dev]"

# Format code
black baymax.py

# Lint
ruff check baymax.py

# Type check
mypy baymax.py
```

### Virtual Environment Tips

```bash
# Activate the virtual environment (do this each session)
source venv/bin/activate    # macOS/Linux
venv\Scripts\activate       # Windows

# Verify you're in the venv (should show the venv path)
which python

# Deactivate when done
deactivate

# Update requirements.txt after adding new packages
pip freeze > requirements.txt
```

## License

MIT License - see LICENSE file for details.

## Acknowledgments

- Inspired by the lovable healthcare companion from Big Hero 6
- Built with [LangChain](https://langchain.com), [Composio](https://composio.dev), [Typer](https://typer.tiangolo.com), and [Rich](https://rich.readthedocs.io)
