from crewai import Task, Agent
from titans.utils.context_builder import ContextComponents, build_task_description


def create_board_tasks(agents: dict[str, Agent], user_input: str) -> list[Task]:
    """
    5-task sequential pipeline with explicit context=[...] chains.

    Why explicit context over Process.sequential auto-chaining:
    - CrewAI sequential auto-chain passes only the immediately prior task.
    - Auditor needs CFO + CLO + CEO Draft simultaneously.
    - CEO Final needs all four prior outputs.
    """

    # Task 1: CFO
    task_cfo = Task(
        description=build_task_description(ContextComponents(
            user_input=user_input,
            task_description=(
                "あなたはCFOとして、以下の経営課題を財務的視点から分析してください。\n"
                "ROI・キャッシュフロー・収益性の観点で具体的な懸念点と推奨事項を示してください。\n"
                "マークダウン形式・日本語で出力してください。"
            ),
        )),
        expected_output="CFO分析レポート（日本語、マークダウン形式）",
        agent=agents["cfo"],
    )

    # Task 2: CLO — sees CFO output
    task_clo = Task(
        description=build_task_description(ContextComponents(
            user_input=user_input,
            task_description=(
                "あなたはCLOとして、以下の経営課題を法務・コンプライアンスの視点から分析してください。\n"
                "CFOの財務分析も参照し、法的リスクの観点から追加の懸念点があれば指摘してください。\n"
                "マークダウン形式・日本語で出力してください。"
            ),
        )),
        expected_output="CLO法務レビュー（日本語、マークダウン形式）",
        agent=agents["clo"],
        context=[task_cfo],
    )

    # Task 3: CEO Draft — sees CFO + CLO
    task_ceo_draft = Task(
        description=build_task_description(ContextComponents(
            user_input=user_input,
            task_description=(
                "あなたはCEOとして、CFOとCLOの分析を踏まえた経営判断の草稿を作成してください。\n"
                "これは監査役のレビュー前の草稿です。率直に戦略を示してください。\n"
                "マークダウン形式・日本語で出力してください。"
            ),
        )),
        expected_output="CEO戦略草稿（日本語、マークダウン形式）",
        agent=agents["ceo"],
        context=[task_cfo, task_clo],
    )

    # Task 4: Auditor — sees all three prior outputs
    task_auditor = Task(
        description=build_task_description(ContextComponents(
            user_input=user_input,
            task_description=(
                "あなたは独立した監査役として、CFO・CLO・CEO草稿の全出力を横断的にレビューしてください。\n"
                "矛盾・論理的誤謬・根拠なき主張・見落としを特定し、CEOへの改訂指示を出してください。\n"
                "マークダウン形式・日本語で出力してください。"
            ),
        )),
        expected_output="監査役レポート（矛盾・ハルシネーション・改訂指示）（日本語）",
        agent=agents["auditor"],
        context=[task_cfo, task_clo, task_ceo_draft],
    )

    # Task 5: CEO Final — sees all four outputs
    task_ceo_final = Task(
        description=build_task_description(ContextComponents(
            user_input=user_input,
            task_description=(
                "あなたはCEOとして、監査役からの指摘事項を受け、最終的な経営判断を作成してください。\n"
                "指摘された矛盾・リスクを明示的に解決し、実行可能なアクションプランを示してください。\n"
                "これが取締役会に提出される最終レポートです。\n"
                "マークダウン形式・日本語で出力してください。"
            ),
        )),
        expected_output="CEO最終判断・取締役会レポート（日本語、マークダウン形式）",
        agent=agents["ceo"],
        context=[task_cfo, task_clo, task_ceo_draft, task_auditor],
    )

    return [task_cfo, task_clo, task_ceo_draft, task_auditor, task_ceo_final]
