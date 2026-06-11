from crewai.flow.flow import Flow, start, listen
from crewai import Crew, Process
from pydantic import BaseModel

from titans.agents.board_agents import create_board_agents
from titans.tasks.board_tasks import create_board_tasks
from titans.brain.base import BrainProvider
from titans.memory.base import MemoryEntry, MemoryStore
from titans.retrieval.knowledge_base import KnowledgeBase
from titans.utils.config_loader import AppConfig
from titans.report.renderer import MeetingReport


class MeetingState(BaseModel):
    user_input: str = ""
    retrieved_knowledge: str = ""
    long_term_memory: str = ""
    meeting_report: MeetingReport | None = None
    error: str | None = None

    model_config = {"arbitrary_types_allowed": True}


class BoardMeetingFlow(Flow[MeetingState]):
    """
    Orchestrates the Titans Board meeting as a CrewAI Flow.

    Flow steps (Context Builder = Memory Loader + Retrieval Merger):
      prepare_context (@start) → kickoff_meeting (@listen) → on_meeting_complete (@listen)
    """

    def __init__(
        self,
        brain_provider: BrainProvider,
        config: AppConfig,
        knowledge_base: KnowledgeBase | None = None,
        memory_store: MemoryStore | None = None,
    ):
        super().__init__()
        self._brain_provider = brain_provider
        self._config = config
        self._knowledge_base = knowledge_base
        self._memory_store = memory_store

    @start()
    def prepare_context(self):
        """Retrieval First: 会議の前に長期記憶と関連知識を state に積む。"""
        if self._memory_store is not None and self._config.memory.enabled:
            self.state.long_term_memory = self._memory_store.load_context(
                self.state.user_input, top_k=self._config.memory.top_k
            )
        if self._knowledge_base is not None and self._config.retrieval.enabled:
            self.state.retrieved_knowledge = self._knowledge_base.retrieve_as_text(
                self.state.user_input, top_k=self._config.retrieval.top_k
            )

    @listen(prepare_context)
    def kickoff_meeting(self):
        shared_llm = self._brain_provider.get_llm()
        agents = create_board_agents(shared_llm, self._config)
        tasks = create_board_tasks(
            agents,
            self.state.user_input,
            retrieved_knowledge=self.state.retrieved_knowledge,
            long_term_memory=self.state.long_term_memory,
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
            long_term_memory=self.state.long_term_memory,
        )

    @listen(kickoff_meeting)
    def on_meeting_complete(self):
        """会議の結論を「過去意思決定」として長期記憶へ書き戻す。"""
        if self._memory_store is None or not self._config.memory.enabled:
            return
        report = self.state.meeting_report
        if report is None or not report.ceo_final_output:
            return
        decision = report.ceo_final_output.strip()
        if len(decision) > 500:
            decision = decision[:500] + "…"
        self._memory_store.remember(MemoryEntry(
            category="過去意思決定",
            content=f"課題: {self.state.user_input}\n決定: {decision}",
        ))
