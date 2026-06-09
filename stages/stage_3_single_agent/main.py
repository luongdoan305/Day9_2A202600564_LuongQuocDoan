"""Stage 3: Single Agent (ReAct Loop)

Wraps the LLM + tools in an autonomous agent that can reason, act,
and observe in a loop. The agent decides which tools to call, evaluates
the results, and may call more tools before giving a final answer.

Uses LangGraph's create_react_agent for the Think -> Act -> Observe loop.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from dotenv import load_dotenv
from langchain_core.tools import tool

from common.llm import get_llm

# ---------------------------------------------------------------------------
# Expanded knowledge base (law + tax + compliance entries)
# ---------------------------------------------------------------------------

LEGAL_KNOWLEDGE = [
    {
        "id": "nda_breach",
        "keywords": ["nda", "non-disclosure", "confidential", "trade secret", "breach"],
        "text": (
            "NDA breaches trigger contractual and statutory liability. Under the DTSA "
            "(18 U.S.C. Section 1836): injunctive relief, actual damages plus unjust enrichment, "
            "exemplary damages up to 2x for willful misappropriation, and attorney's fees. "
            "Criminal prosecution is possible under the Economic Espionage Act."
        ),
    },
    {
        "id": "contract_remedies",
        "keywords": ["breach", "contract", "remedies", "damages", "ucc"],
        "text": (
            "UCC Article 2 remedies include expectation damages, consequential damages, "
            "specific performance for unique goods, and cover damages. The statute of "
            "limitations is typically 4 years under UCC Section 2-725."
        ),
    },
    {
        "id": "tax_evasion",
        "keywords": ["tax", "evasion", "irs", "penalty", "fraud", "revenue"],
        "text": (
            "Tax evasion can carry criminal penalties, civil fraud penalties, back taxes, "
            "interest, and possible personal liability for responsible officers."
        ),
    },
    {
        "id": "offshore_tax",
        "keywords": ["offshore", "overseas", "foreign", "tax", "fbar", "fatca"],
        "text": (
            "Unreported overseas income may trigger FBAR penalties, FATCA consequences, "
            "back taxes, interest, and possible criminal enforcement for willful violations."
        ),
    },
    {
        "id": "data_privacy",
        "keywords": ["data", "privacy", "user", "consent", "gdpr", "ccpa", "sharing"],
        "text": (
            "Sharing user data without consent may violate CCPA, GDPR, FTC Act Section 5, "
            "state privacy laws, and consumer protection rules."
        ),
    },
    {
        "id": "sox_compliance",
        "keywords": ["sox", "sarbanes", "compliance", "sec", "financial", "reporting"],
        "text": (
            "SOX violations can create SEC enforcement risk, officer/director bars, criminal "
            "exposure for false certifications, and penalties for record destruction."
        ),
    },
]


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@tool
def search_legal_database(query: str) -> str:
    """Search the legal knowledge base for relevant statutes and legal principles.

    Args:
        query: Natural language search query about a legal topic.
    """
    query_words = set(query.lower().split())
    scored = []
    for entry in LEGAL_KNOWLEDGE:
        overlap = len(query_words & set(entry["keywords"]))
        if overlap > 0:
            scored.append((overlap, entry))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:2]
    if not top:
        return "No relevant legal sources found."
    return "\n\n".join(f"[{entry['id']}] {entry['text']}" for _, entry in top)


@tool
def calculate_penalty(violation_type: str, severity: str, annual_revenue: float) -> str:
    """Calculate estimated legal penalties based on violation type, severity, and revenue.

    Args:
        violation_type: Type of violation, such as tax_evasion, data_privacy, or contract_breach.
        severity: Severity level: low, medium, or high.
        annual_revenue: Company's annual revenue in USD.
    """
    severity_multipliers = {"low": 0.01, "medium": 0.05, "high": 0.10}
    multiplier = severity_multipliers.get(severity.lower(), 0.05)
    base_penalty = annual_revenue * multiplier

    type_lower = violation_type.lower()
    if "tax" in type_lower:
        extra = "Plus potential criminal charges and civil fraud penalties."
    elif "privacy" in type_lower or "data" in type_lower:
        extra = "Plus privacy regulator fines and class action exposure."
    elif "contract" in type_lower:
        extra = "Plus consequential damages, attorney's fees, and possible injunction."
    else:
        extra = "Additional regulatory sanctions may apply."

    return (
        f"Penalty Estimate for {violation_type} ({severity} severity):\n"
        f"  Base penalty: ${base_penalty:,.2f}\n"
        f"  Revenue basis: ${annual_revenue:,.2f}\n"
        f"  {extra}"
    )


@tool
def check_compliance_requirements(industry: str, company_size: str) -> str:
    """Check which regulatory compliance frameworks apply to a company.

    Args:
        industry: The company's industry, such as technology, finance, or healthcare.
        company_size: Company size: startup, mid-size, or enterprise.
    """
    frameworks = {
        "technology": ["CCPA/CPRA", "GDPR if EU users", "FTC Act Section 5", "SOC 2"],
        "finance": ["SOX", "BSA/AML", "Dodd-Frank", "SEC Regulations", "FCPA"],
        "healthcare": ["HIPAA", "HITECH Act", "FTC Health Breach Notification", "AKS"],
    }

    size_extras = {
        "startup": "Consider SOC 2 Type II for investor and customer confidence.",
        "mid-size": "Consider a dedicated compliance officer and annual audits.",
        "enterprise": "Use a full compliance program, board oversight, and whistleblower hotline.",
    }

    applicable = frameworks.get(industry.lower(), ["FTC Act Section 5", "State consumer protection laws"])
    size_note = size_extras.get(company_size.lower(), "")

    return (
        f"Applicable frameworks for {industry} ({company_size}):\n"
        f"  {', '.join(applicable)}\n"
        f"  {size_note}"
    )


@tool
def search_case_law(keywords: str) -> str:
    """Search case law by keyword.

    Args:
        keywords: Keywords to search for, such as breach, negligence, or contract.
    """
    cases = {
        "breach": "Hadley v. Baxendale (1854) - Consequential damages for breach of contract.",
        "negligence": "Donoghue v. Stevenson (1932) - Duty of care.",
        "contract": "Carlill v. Carbolic Smoke Ball Co (1893) - Unilateral contract.",
    }

    keywords_lower = keywords.lower()
    for key, case in cases.items():
        if key in keywords_lower:
            return case
    return "No matching case law found."


TOOLS = [
    search_legal_database,
    calculate_penalty,
    check_compliance_requirements,
    search_case_law,
]

QUESTION = (
    "A tech startup with $5M annual revenue had a vendor breach a software contract, "
    "causing consequential losses. What remedies, case law, penalty exposure, and "
    "compliance requirements should the company consider?"
)

SYSTEM_PROMPT = (
    "You are a legal analyst agent. You have access to tools for searching legal databases, "
    "searching case law, calculating penalties, and checking compliance requirements. Use "
    "these tools to build a comprehensive analysis. For breach-of-contract questions, search "
    "both the legal database and case law before estimating exposure. Keep your final answer "
    "under 500 words."
)


async def main():
    from langgraph.prebuilt import create_react_agent

    print("=" * 70)
    print("STAGE 3: Single Agent (ReAct Loop)")
    print("=" * 70)
    print()
    print("[How it works]")
    print("  1. An autonomous agent receives a complex multi-part question")
    print("  2. It reasons about what tools to call (Think)")
    print("  3. It calls a tool (Act)")
    print("  4. It observes the result and decides next steps (Observe)")
    print("  5. It repeats until it has enough information for a final answer")
    print()
    print(f"Question: {QUESTION}")
    print("-" * 70)

    llm = get_llm()
    graph = create_react_agent(model=llm, tools=TOOLS, prompt=SYSTEM_PROMPT, debug=True)

    inputs = {"messages": [{"role": "user", "content": QUESTION}]}

    step = 0
    async for chunk in graph.astream(inputs, stream_mode="updates"):
        for node_name, update in chunk.items():
            step += 1
            messages = update.get("messages", [])
            for msg in messages:
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    print(f"\n[Step {step}] THINK + ACT (node: {node_name})")
                    for tc in msg.tool_calls:
                        print(f"  Tool: {tc['name']}")
                        print(f"  Args: {tc['args']}")
                elif msg.type == "tool":
                    print(f"\n[Step {step}] OBSERVE (node: {node_name})")
                    content = msg.content
                    print(f"  Result: {content[:300]}{'...' if len(content) > 300 else ''}")
                elif msg.type == "ai" and msg.content:
                    print(f"\n[Step {step}] FINAL ANSWER (node: {node_name})")
                    print("-" * 70)
                    print(msg.content)

    print()
    print("-" * 70)
    print("[Improvements over Stage 2]")
    print("  + Autonomous: agent decides which tools to call and when")
    print("  + Multi-step reasoning: can search, calculate, search again")
    print("  + Handles complex queries: breaks problems into sub-tasks")
    print()
    print("[Limitations of Stage 3]")
    print("  - Single agent: one LLM handles all domains (law, tax, compliance)")
    print("  - No specialisation: same system prompt for all legal areas")
    print("  - Bottleneck: sequential tool calls, no parallelism")
    print()
    print("Next: Stage 4 splits this into specialised agents that work in parallel.")
    print("=" * 70)


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(main())
