from crewai.flow.flow import Flow, start, listen
from crewai import Crew, Process
from pydantic import BaseModel

from titans.agents.board_agents import create_board_agents
from titans.tasks.board_tasks import create_board_tasks
from titans.brain.base import BrainProvider
from titans.utils.config_loader import AppConfig
from titans.report.renderer import MeetingReport


class MeetingState(BaseModel):
    user_input: str = ""
    meeting_report: MeetingReport | None = None
    error: str | None = None

    model_config = {"arbitrary_types_allowed": True}


class BoardMeetingFlow(Flow[MeetingState]):
    """
    Orchestrates the Titans Board meeting as a CrewAI Flow.

    Flow steps:
      kickoff_meeting (@start) → on_meeting_complete (@listen)

    Using Flow (not bare Crew) so that Phase 2 can add pre/post-meeting steps
    (RAG retrieval, Letta memory write-back) without restructuring the Crew.
    """

    def __init__(self, brain_provider: BrainProvider, config: AppConfig):
        super().__init__()
        self._brain_provider = brain_provider
        self._config = config

    @start()
    def kickoff_meeting(self):
        shared_llm = self._brain_provider.get_llm()
        agents = create_board_agents(shared_llm, self._config)
        tasks = create_board_tasks(agents, self.state.user_input)

        crew = Crew(
            agents=list(agents.values()),
            tasks=tasks,
            process=Process.sequential,
            verbose=self._config.meeting.verbose,
        )
        crew.kickoff()

        def _raw(task):
            if task.output is None:
                return ""
            return task.output.raw or ""

        self.state.meeting_report = MeetingReport(
            user_input=self.state.user_input,
            cfo_output=_raw(tasks[0]),
            clo_output=_raw(tasks[1]),
            ceo_draft_output=_raw(tasks[2]),
            auditor_output=_raw(tasks[3]),
            ceo_final_output=_raw(tasks[4]),
        )

    @listen(kickoff_meeting)
    def on_meeting_complete(self):
        # Phase 2 stub: write meeting conclusions back to Letta long-term memory
        pass
