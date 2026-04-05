from app.browser_hook.models import TaskStep, ToolResult, ToolStatus
from app.models.session_event import AgentStepEvent, SessionEventLog
from app.models.task import TaskStatus


def _tool(
    tool: str,
    title: str,
    description: str | None,
    status: ToolStatus,
) -> ToolResult:
    return ToolResult(
        tool=tool,
        title=title,
        description=description,
        status=status,
    )


def build_mock_session_store() -> (
    tuple[dict[str, TaskStatus], dict[str, SessionEventLog]]
):
    short_steps = [
        TaskStep(
            step=1,
            memory="Opened docs page and verified title.",
            tools=[
                ToolResult(
                    tool="navigate",
                    title="Navigate",
                    description="Opened https://example.com/docs",
                    status=ToolStatus.SUCCESS,
                )
            ],
        ),
        TaskStep(
            step=2,
            memory="Extracted summary and completed task.",
            tools=[
                ToolResult(
                    tool="extract",
                    title="Extract",
                    description="Captured page title and intro text",
                    status=ToolStatus.SUCCESS,
                ),
                ToolResult(
                    tool="done",
                    title="Done",
                    description="Task complete",
                    status=ToolStatus.SUCCESS,
                ),
            ],
        ),
    ]

    medium_steps = [
        TaskStep(
            step=1,
            memory="Started web research on pricing benchmarks.",
            tools=[
                _tool(
                    "search",
                    "Search",
                    "Searched for SaaS pricing trends",
                    ToolStatus.SUCCESS,
                ),
                _tool("click", "Click", "Opened result #2", ToolStatus.SUCCESS),
            ],
        ),
        TaskStep(
            step=2,
            memory="Collected key stats and moved between tabs.",
            tools=[
                _tool(
                    "find_elements",
                    "Find Elements",
                    "Found pricing cards",
                    ToolStatus.SUCCESS,
                ),
                _tool(
                    "switch",
                    "Switch",
                    "Switched to reference tab",
                    ToolStatus.SUCCESS,
                ),
                _tool(
                    "search_page",
                    "Search Page",
                    "Timed out while scanning full HTML",
                    ToolStatus.ERROR,
                ),
            ],
        ),
        TaskStep(
            step=3,
            memory="Saved findings and generated PDF report.",
            tools=[
                _tool(
                    "write_file",
                    "Write File",
                    "Created research_notes.md",
                    ToolStatus.SUCCESS,
                ),
                _tool(
                    "replace_file",
                    "Replace File",
                    "Applying patch to summary section",
                    ToolStatus.PENDING,
                ),
                _tool(
                    "save_as_pdf",
                    "Save As Pdf",
                    "Saved page snapshot",
                    ToolStatus.SUCCESS,
                ),
            ],
        ),
        TaskStep(
            step=4,
            memory="Paused for human review.",
            tools=[
                _tool(
                    "wait",
                    "Wait",
                    "Waiting for additional instruction",
                    ToolStatus.PENDING,
                )
            ],
        ),
    ]

    long_tool_cycle: list[tuple[str, str, str, ToolStatus]] = [
        ("navigate", "Navigate", "Opened target URL", ToolStatus.SUCCESS),
        ("search", "Search", "Ran web search query", ToolStatus.SUCCESS),
        ("click", "Click", "Clicked ranked element", ToolStatus.SUCCESS),
        ("input", "Input", "Entered text into form", ToolStatus.SUCCESS),
        (
            "select_dropdown",
            "Select Dropdown",
            "Selected an option",
            ToolStatus.SUCCESS,
        ),
        (
            "dropdown_options",
            "Dropdown Options",
            "Fetched option list",
            ToolStatus.SUCCESS,
        ),
        ("scroll", "Scroll", "Scrolled down one viewport", ToolStatus.SUCCESS),
        ("go_back", "Go Back", "History navigation blocked", ToolStatus.ERROR),
        ("switch", "Switch", "Switched browser tab", ToolStatus.SUCCESS),
        ("close", "Close", "Closed inactive tab", ToolStatus.SUCCESS),
        ("extract", "Extract", "Extracted structured details", ToolStatus.SUCCESS),
        (
            "find_elements",
            "Find Elements",
            "Captured CSS selector matches",
            ToolStatus.SUCCESS,
        ),
        (
            "find_text",
            "Find Text",
            "Located target text section",
            ToolStatus.SUCCESS,
        ),
        (
            "search_page",
            "Search Page",
            "Matched regex in page HTML",
            ToolStatus.SUCCESS,
        ),
        ("evaluate", "Evaluate", "Executing JS payload", ToolStatus.PENDING),
        (
            "upload_file",
            "Upload File",
            "Upload rejected by form validation",
            ToolStatus.ERROR,
        ),
        ("send_keys", "Send Keys", "Sent Enter key", ToolStatus.SUCCESS),
        (
            "read_file",
            "Read File",
            "Read local intermediate file",
            ToolStatus.SUCCESS,
        ),
        (
            "write_file",
            "Write File",
            "Wrote consolidated output",
            ToolStatus.SUCCESS,
        ),
        (
            "replace_file",
            "Replace File",
            "Patched output formatting",
            ToolStatus.SUCCESS,
        ),
    ]

    long_steps: list[TaskStep] = []
    for i in range(1, 26):
        tool_a = long_tool_cycle[(i - 1) % len(long_tool_cycle)]
        tool_b = long_tool_cycle[i % len(long_tool_cycle)]
        long_steps.append(
            TaskStep(
                step=i,
                memory=f"Long run progress checkpoint {i}/25.",
                tools=[
                    _tool(tool_a[0], tool_a[1], f"{tool_a[2]} at step {i}", tool_a[3]),
                    _tool(tool_b[0], tool_b[1], f"{tool_b[2]} at step {i}", tool_b[3]),
                ],
            )
        )

    long_steps.append(
        TaskStep(
            step=26,
            memory="Finalized automation run.",
            tools=[
                _tool(
                    "done",
                    "Done",
                    "Task complete after long workflow",
                    ToolStatus.SUCCESS,
                )
            ],
        )
    )

    seeded = {
        "mock-short-001": (
            TaskStatus.COMPLETED,
            "Short mock task completed.",
            short_steps,
        ),
        "mock-medium-001": (
            TaskStatus.RUNNING,
            None,
            medium_steps,
        ),
        "mock-long-001": (
            TaskStatus.COMPLETED,
            "Long mock task completed with 26 steps.",
            long_steps,
        ),
    }

    statuses_by_session: dict[str, TaskStatus] = {}
    event_logs_by_session: dict[str, SessionEventLog] = {}

    for session_id, (status, result, steps) in seeded.items():
        statuses_by_session[session_id] = status
        event_logs_by_session[session_id] = SessionEventLog(
            session_id=session_id,
            status=status,
            events=[AgentStepEvent(step=step) for step in steps],
        )

    return statuses_by_session, event_logs_by_session
