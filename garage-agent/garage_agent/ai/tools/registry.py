"""
Central AI Tool Registry.

Maps tool names to executable functions.
This allows LLM engine to dynamically call tools.
"""

from sqlalchemy.orm import Session

from garage_agent.ai.tools.booking_tools import (
    tool_create_booking,
    tool_reschedule_booking,
    tool_cancel_booking,
)

from garage_agent.ai.tools.jobcard_tools import (
    tool_create_jobcard,
    tool_complete_jobcard,
)

from garage_agent.ai.tools.report_tools import (
    tool_get_daily_summary,
)


class ToolRegistry:
    def __init__(self):
        self._tools = {
            # Booking tools
            "create_booking": tool_create_booking,
            "reschedule_booking": tool_reschedule_booking,
            "cancel_booking": tool_cancel_booking,

            # JobCard tools
            "create_jobcard": tool_create_jobcard,
            "complete_jobcard": tool_complete_jobcard,

            # Reporting tools
            "get_daily_summary": tool_get_daily_summary,
        }

    def list_tools(self):
        return list(self._tools.keys())

    def execute(self, tool_name: str, db: Session, **kwargs):
        if tool_name not in self._tools:
            raise ValueError(f"Tool '{tool_name}' not registered.")

        tool_function = self._tools[tool_name]
        return tool_function(db=db, **kwargs)