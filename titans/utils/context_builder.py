from dataclasses import dataclass, field


@dataclass
class ContextComponents:
    task_description: str = ""
    user_input: str = ""
    long_term_memory: str = ""      # Phase 1: stub (empty)
    retrieved_knowledge: str = ""   # Phase 1: stub (empty — no RAG yet)
    persona_hint: str = ""


def build_task_description(components: ContextComponents) -> str:
    """
    Assembles [LTM] + [Knowledge] + [User Input] + [Task Instructions].
    Phase 1: LTM and knowledge are empty strings → those sections are omitted.
    Phase 2+: callers populate long_term_memory (Letta) and
              retrieved_knowledge (Qdrant/BM25) before calling this.
    """
    parts = []

    if components.long_term_memory:
        parts.append(f"【長期記憶】\n{components.long_term_memory}")

    if components.retrieved_knowledge:
        parts.append(f"【関連知識】\n{components.retrieved_knowledge}")

    parts.append(f"【経営課題（ユーザー入力）】\n{components.user_input}")

    if components.task_description:
        parts.append(f"【タスク指示】\n{components.task_description}")

    return "\n\n".join(parts)
