from typing import Any

from app.browser_hook.models import ToolResult, ToolStatus


def extract_ui_tools(
    raw_actions: list[Any], raw_results: list[Any]
) -> list[ToolResult]:
    """
    Matches executed actions to their results.
    Automatically omits planned actions that never executed.
    """
    ui_tools: list[ToolResult] = []

    # zip() naturally stops at the shortest list.
    # If we have 5 actions but only 2 results, it perfectly drops the 3 unexecuted actions!
    for action, result in zip(raw_actions, raw_results):
        tool_name = "unknown"
        title = "Unknown Tool"
        description = None
        status = ToolStatus.SUCCESS  # If a result exists without an error, it succeeded

        # --- 1. EXTRACT THE RAW TOOL & FORMATTED TITLE ---
        if action:
            if hasattr(action, "model_dump"):
                action_dict = action.model_dump(exclude_none=True)
            else:
                action_dict = action if isinstance(action, dict) else {}

            if "root" in action_dict and len(action_dict) == 1:
                action_dict = action_dict["root"]

            if action_dict:
                tool_name = list(action_dict.keys())[0]
                title = tool_name.replace("_", " ").title()

        # --- 2. EXTRACT THE DESCRIPTION (IF USEFUL) & STATUS ---
        if result:
            error_val = getattr(result, "error", None)
            extracted_val = getattr(result, "extracted_content", None)
            memory_val = getattr(result, "long_term_memory", None)

            # Cascade 1: Hard Errors
            if error_val is not None and str(error_val).strip() != "":
                description = str(error_val)
                status = ToolStatus.ERROR

            # Cascade 2: Explicit failure flag
            elif getattr(result, "success", None) is False:
                description = "Action failed to execute."
                status = ToolStatus.ERROR

            # Cascade 3: Extracted Content (Cleaned up)
            elif extracted_val:
                description = str(extracted_val).split("\n")[0].strip()

            # Cascade 4: Long Term Memory
            elif memory_val:
                description = str(memory_val).split("\n")[0].strip()

        ui_tools.append(
            ToolResult(
                tool=tool_name,
                title=title,
                description=description,
                status=status,
            )
        )

    return ui_tools
