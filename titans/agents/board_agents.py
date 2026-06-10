import yaml
from pathlib import Path
from crewai import Agent, LLM
from titans.utils.config_loader import AppConfig

PERSONAS_DIR = Path(__file__).parent.parent / "personas"


def _load_persona(name: str) -> dict:
    with open(PERSONAS_DIR / f"{name}.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def create_board_agents(shared_llm: LLM, config: AppConfig) -> dict[str, Agent]:
    """
    Creates all 4 board agents sharing THE SAME LLM instance.
    Persona switching happens via each agent's role+backstory (SystemMessage),
    not via separate model instances — this is the "One Brain" principle.
    """
    names = ["cfo", "clo", "ceo", "auditor"]
    agents = {}
    for name in names:
        persona = _load_persona(name)
        agents[name] = Agent(
            role=persona["role"],
            goal=persona["goal"],
            backstory=persona["backstory"],
            llm=shared_llm,
            verbose=config.meeting.verbose,
            max_iter=config.meeting.max_iter,
            allow_delegation=False,
        )
    return agents
