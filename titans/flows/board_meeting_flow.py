from crewai.flow.flow import Flow, start, listen
from crewai import Crew, Process
from pydantic import BaseModel

from titans.agents.board_agents import create_board_agents
from titans.tasks.board_tasks import create_board_tasks
from titans.brain.base import BrainProvider
from titans.retrieval.knowledge_base import KnowledgeBase
from titans.utils.config_loader import AppConfig
from titans.report.renderer import MeetingReport


class MeetingState(BaseModel):
    user_input: str = ""
    retrieved_knowledge: str = ""
    meeting_report: MeetingReport | None = None
    error: str | None = None

    model_config = {"arbitrary_types_allowed": True}


class BoardMeetingFlow(Flow[MeetingState]):
    """
    Orchestrates the Titans Board meeting as a CrewAI Flow.

    Flow steps (Retrieval First):
      retrieve_knowledge (@start) → kickoff_meeting (@listen) → on_meeting_complete (@listen)
    """

    def __init__(
        self,
        brain_provider: BrainProvider,
        config: AppConfig,
        knowledge_base: KnowledgeBase | None = None,
    ):
        super().__init__()
        self._brain_provider = brain_provider
        self._config = config
        self._knowledge_base = knowledge_base

    @start()
    def retrieve_knowledge(self):
        """Retrieval First: 会議の前に関連知識を取得して state に積む。"""
        if self._knowledge_base is None or not self._config.retrieval.enabled:
            return
        self.state.retrieved_knowledge = self._knowledge_base.retrieve_as_text(
            self.state.user_input, top_k=self._config.retrieval.top_k
        )

    @listen(retrieve_knowledge)
    def kickoff_meeting(self):
        shared_llm = self._brain_provider.get_llm()
        agents = create_board_agents(shared_llm, self._config)
        tasks = create_board_tasks(
            agents,
            self.state.user_input,
            retrieved_knowledge=self.state.retrieved_knowledge,
        )

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
            retrieved_knowledge=self.state.retrieved_knowledge,
        )

    @listen(kickoff_meeting)
    def on_meeting_complete(self):
        # Phase 3 stub: write meeting conclusions back to Letta long-term memory
        pass
