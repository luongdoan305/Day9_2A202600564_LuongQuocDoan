"""Stage 4: Multi-Agent System (In-Process)

Multiple specialised agents collaborate on a complex legal question.
This mirrors Stage 5's architecture, but runs entirely in-process:
no HTTP, no A2A protocol, and no separate servers.

Graph:
    analyze_law
      -> check_routing
      -> parallel [call_tax_specialist, call_compliance_specialist, call_privacy_specialist]
      -> aggregate
      -> END
"""

import asyncio
import json
import os
import sys
from typing import Annotated, TypedDict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.constants import Send
from langgraph.graph import END, StateGraph

from common.llm import get_llm


# ---------------------------------------------------------------------------
# Tools for specialist sub-agents
# ---------------------------------------------------------------------------

@tool
def search_tax_law(query: str) -> str:
    """Search tax law knowledge base for relevant statutes and penalties.

    Args:
        query: Natural language query about tax law.
    """
    knowledge = [
        (
            ["tax", "evasion", "fraud", "irs"],
            "Tax evasion: felony exposure, fines, possible prison time, civil fraud penalties, "
            "back taxes, interest, and responsible-person liability for officers.",
        ),
        (
            ["offshore", "overseas", "foreign", "fbar", "fatca"],
            "Unreported overseas accounts or income can trigger FBAR/FATCA penalties, "
            "withholding consequences, back taxes, interest, and criminal risk for willful conduct.",
        ),
        (
            ["transfer", "pricing", "corporate"],
            "Transfer pricing violations can let the IRS reallocate income between related "
            "entities and impose substantial valuation misstatement penalties.",
        ),
    ]
    query_lower = query.lower()
    results = [text for keywords, text in knowledge if any(kw in query_lower for kw in keywords)]
    return "\n\n".join(results) if results else "No specific tax law matches found."


@tool
def search_compliance_law(query: str) -> str:
    """Search regulatory compliance knowledge base for applicable frameworks.

    Args:
        query: Natural language query about regulatory compliance.
    """
    knowledge = [
        (
            ["sox", "sarbanes", "financial", "sec", "reporting"],
            "SOX issues can create SEC enforcement risk, false-certification penalties, "
            "record-retention obligations, officer/director bars, and whistleblower risks.",
        ),
        (
            ["fcpa", "bribery", "corruption", "foreign"],
            "FCPA anti-bribery and books-and-records rules can create corporate fines, "
            "individual liability, monitorship risk, and SEC/DOJ enforcement.",
        ),
        (
            ["aml", "bsa", "sanctions", "regulation", "compliance"],
            "AML/BSA and sanctions compliance require risk controls, monitoring, reporting, "
            "recordkeeping, and remediation when violations occur.",
        ),
    ]
    query_lower = query.lower()
    results = [text for keywords, text in knowledge if any(kw in query_lower for kw in keywords)]
    return "\n\n".join(results) if results else "No specific compliance matches found."


@tool
def search_privacy_law(query: str) -> str:
    """Search privacy and data protection law knowledge base.

    Args:
        query: Natural language query about privacy, GDPR, CCPA, or data protection.
    """
    knowledge = [
        (
            ["gdpr", "privacy", "data", "consent", "personal", "eu"],
            "GDPR requires a lawful basis for processing, transparency, data minimisation, "
            "purpose limitation, appropriate security, and respect for data subject rights. "
            "Serious violations can lead to fines up to 4% of annual global turnover or EUR 20M.",
        ),
        (
            ["breach", "leak", "du lieu", "dữ liệu", "notification", "customer"],
            "Data breach duties can include containment, forensic investigation, regulator notice, "
            "affected-user notice, remediation, and security improvements. GDPR generally requires "
            "supervisory authority notice within 72 hours when risk to individuals is likely.",
        ),
        (
            ["ccpa", "cpra", "california", "consumer", "sharing", "sale"],
            "CCPA/CPRA gives consumers rights to notice, access, deletion, correction, opt out of "
            "sale or sharing, and limit sensitive personal information use. Intentional violations "
            "can create civil penalties up to $7,500 per violation.",
        ),
    ]
    query_lower = query.lower()
    results = [text for keywords, text in knowledge if any(kw in query_lower for kw in keywords)]
    return "\n\n".join(results) if results else "No specific privacy law matches found."


# ---------------------------------------------------------------------------
# State definition
# ---------------------------------------------------------------------------

def _last_wins(a: str, b: str) -> str:
    """Reducer: keep the most recently written value."""
    return b if b else a


class LegalState(TypedDict):
    question: str
    law_analysis: str
    needs_tax: bool
    needs_compliance: bool
    needs_privacy: bool
    tax_result: Annotated[str, _last_wins]
    compliance_result: Annotated[str, _last_wins]
    privacy_result: Annotated[str, _last_wins]
    final_answer: str


# ---------------------------------------------------------------------------
# Node implementations
# ---------------------------------------------------------------------------

async def analyze_law(state: LegalState) -> dict:
    """Lead attorney analyses the general legal aspects of the question."""
    print("\n  [Node: analyze_law] Lead attorney analysing legal aspects...")
    llm = get_llm()
    messages = [
        SystemMessage(
            content=(
                "You are a senior corporate litigation attorney specialising in contract law, "
                "tort law, and general business law. Analyse the legal aspects of the question. "
                "Keep your analysis under 200 words."
            )
        ),
        HumanMessage(content=state["question"]),
    ]
    result = await llm.ainvoke(messages)
    print(f"  [Node: analyze_law] Done ({len(result.content)} chars)")
    return {"law_analysis": result.content}


async def check_routing(state: LegalState) -> dict:
    """Determine which specialist sub-agents are needed."""
    print("\n  [Node: check_routing] Determining which specialists are needed...")
    llm = get_llm()
    messages = [
        SystemMessage(
            content=(
                "You are a legal routing expert. Based on the question, decide whether "
                "specialist sub-agents are needed.\n"
                "Reply with ONLY valid JSON, no markdown, no extra text:\n"
                '{"needs_tax": <true|false>, "needs_compliance": <true|false>, '
                '"needs_privacy": <true|false>}\n\n'
                "needs_tax = true when the question involves tax law, IRS, tax evasion, or penalties.\n"
                "needs_compliance = true when it involves SEC, SOX, AML, FCPA, or regulation.\n"
                "needs_privacy = true when it involves data, privacy, GDPR, CCPA, data breach, or consent."
            )
        ),
        HumanMessage(content=state["question"]),
    ]
    result = await llm.ainvoke(messages)
    raw = result.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {"needs_tax": True, "needs_compliance": True, "needs_privacy": False}

    question_lower = state["question"].lower()
    privacy_keywords = ["data", "privacy", "gdpr", "dữ liệu", "du lieu", "breach", "leak", "consent"]

    needs_tax = bool(parsed.get("needs_tax", False))
    needs_compliance = bool(parsed.get("needs_compliance", False))
    needs_privacy = bool(parsed.get("needs_privacy", False)) or any(
        kw in question_lower for kw in privacy_keywords
    )

    print(
        "  [Node: check_routing] "
        f"needs_tax={needs_tax}, needs_compliance={needs_compliance}, needs_privacy={needs_privacy}"
    )
    return {
        "needs_tax": needs_tax,
        "needs_compliance": needs_compliance,
        "needs_privacy": needs_privacy,
    }


def route_to_specialists(state: LegalState) -> list[Send]:
    """Dispatch parallel Send objects to specialist nodes."""
    sends: list[Send] = []
    if state.get("needs_tax"):
        sends.append(Send("call_tax_specialist", state))
    if state.get("needs_compliance"):
        sends.append(Send("call_compliance_specialist", state))
    if state.get("needs_privacy"):
        sends.append(Send("call_privacy_specialist", state))
    if not sends:
        sends.append(Send("aggregate", state))
    return sends


async def call_tax_specialist(state: LegalState) -> dict:
    """Tax specialist sub-agent."""
    from langgraph.prebuilt import create_react_agent

    print("\n  [Node: call_tax_specialist] Tax specialist agent starting...")
    tax_prompt = (
        "You are a specialist tax attorney and CPA. Focus on IRS enforcement, tax evasion, "
        "FBAR/FATCA, penalties, back taxes, interest, and officer liability. Use the "
        "search_tax_law tool to ground your analysis. Keep your response under 200 words."
    )

    llm = get_llm()
    agent = create_react_agent(model=llm, tools=[search_tax_law], prompt=tax_prompt)
    result = await agent.ainvoke({"messages": [{"role": "user", "content": state["question"]}]})
    final_msg = result["messages"][-1].content
    print(f"  [Node: call_tax_specialist] Done ({len(final_msg)} chars)")
    return {"tax_result": final_msg}


async def call_compliance_specialist(state: LegalState) -> dict:
    """Compliance specialist sub-agent."""
    from langgraph.prebuilt import create_react_agent

    print("\n  [Node: call_compliance_specialist] Compliance specialist agent starting...")
    compliance_prompt = (
        "You are a senior regulatory compliance officer. Focus on SEC, SOX, FCPA, AML/BSA, "
        "governance, controls, disclosure, and remediation obligations. Use the "
        "search_compliance_law tool to ground your analysis. Keep your response under 200 words."
    )

    llm = get_llm()
    agent = create_react_agent(model=llm, tools=[search_compliance_law], prompt=compliance_prompt)
    result = await agent.ainvoke({"messages": [{"role": "user", "content": state["question"]}]})
    final_msg = result["messages"][-1].content
    print(f"  [Node: call_compliance_specialist] Done ({len(final_msg)} chars)")
    return {"compliance_result": final_msg}


async def call_privacy_specialist(state: LegalState) -> dict:
    """Privacy specialist sub-agent focused on GDPR, CCPA, and data protection."""
    from langgraph.prebuilt import create_react_agent

    print("\n  [Node: call_privacy_specialist] Privacy specialist agent starting...")
    privacy_prompt = (
        "You are a specialist privacy and data protection attorney with expertise in GDPR, "
        "CCPA/CPRA, data breach response, consent, lawful basis, data subject rights, and "
        "privacy regulator enforcement. Use the search_privacy_law tool to ground your "
        "analysis. Keep your response under 200 words."
    )

    llm = get_llm()
    agent = create_react_agent(model=llm, tools=[search_privacy_law], prompt=privacy_prompt)
    result = await agent.ainvoke({"messages": [{"role": "user", "content": state["question"]}]})
    final_msg = result["messages"][-1].content
    print(f"  [Node: call_privacy_specialist] Done ({len(final_msg)} chars)")
    return {"privacy_result": final_msg}


async def aggregate(state: LegalState) -> dict:
    """Combine all specialist analyses into a final comprehensive answer."""
    print("\n  [Node: aggregate] Combining all specialist analyses...")
    llm = get_llm()

    sections: list[str] = []
    if state.get("law_analysis"):
        sections.append(f"## Legal Analysis\n{state['law_analysis']}")
    if state.get("tax_result"):
        sections.append(f"## Tax Analysis\n{state['tax_result']}")
    if state.get("compliance_result"):
        sections.append(f"## Regulatory Compliance Analysis\n{state['compliance_result']}")
    if state.get("privacy_result"):
        sections.append(f"## Privacy and Data Protection Analysis\n{state['privacy_result']}")

    combined = "\n\n---\n\n".join(sections)
    messages = [
        SystemMessage(
            content=(
                "You are a senior legal counsel synthesising specialist analyses into a "
                "comprehensive, well-structured response. Combine the following analyses "
                "into a cohesive answer with clear sections. Avoid redundancy. "
                "Keep your response under 500 words."
            )
        ),
        HumanMessage(content=combined),
    ]
    result = await llm.ainvoke(messages)
    print(f"  [Node: aggregate] Done ({len(result.content)} chars)")
    return {"final_answer": result.content}


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def create_graph():
    """Build and compile the multi-agent StateGraph."""
    graph = StateGraph(LegalState)

    graph.add_node("analyze_law", analyze_law)
    graph.add_node("check_routing", check_routing)
    graph.add_node("call_tax_specialist", call_tax_specialist)
    graph.add_node("call_compliance_specialist", call_compliance_specialist)
    graph.add_node("call_privacy_specialist", call_privacy_specialist)
    graph.add_node("aggregate", aggregate)

    graph.set_entry_point("analyze_law")
    graph.add_edge("analyze_law", "check_routing")
    graph.add_conditional_edges(
        "check_routing",
        route_to_specialists,
        [
            "call_tax_specialist",
            "call_compliance_specialist",
            "call_privacy_specialist",
            "aggregate",
        ],
    )
    graph.add_edge("call_tax_specialist", "aggregate")
    graph.add_edge("call_compliance_specialist", "aggregate")
    graph.add_edge("call_privacy_specialist", "aggregate")
    graph.add_edge("aggregate", END)

    return graph.compile()


QUESTION = (
    "If a company breaks a contract, avoids taxes, and leaks customer data, "
    "what are the legal, tax, compliance, and privacy consequences?"
)


async def main():
    print("=" * 70)
    print("STAGE 4: Multi-Agent System (In-Process)")
    print("=" * 70)
    print()
    print("[How it works]")
    print("  1. Lead attorney agent analyses the question")
    print("  2. Router decides which specialist agents are needed")
    print("  3. Tax + Compliance + Privacy specialists run in parallel")
    print("  4. Aggregator combines all analyses into a final answer")
    print()
    print("[Graph topology]")
    print("  analyze_law -> check_routing -> [tax + compliance + privacy] -> aggregate -> END")
    print()
    print(f"Question: {QUESTION}")
    print("-" * 70)

    graph = create_graph()
    result = await graph.ainvoke({
        "question": QUESTION,
        "law_analysis": "",
        "needs_tax": False,
        "needs_compliance": False,
        "needs_privacy": False,
        "tax_result": "",
        "compliance_result": "",
        "privacy_result": "",
        "final_answer": "",
    })

    print("\n" + "=" * 70)
    print("FINAL ANSWER")
    print("=" * 70)
    print(result["final_answer"])

    print()
    print("-" * 70)
    print("[Improvements over Stage 3]")
    print("  + Specialisation: each agent has domain-specific expertise")
    print("  + Parallel execution: tax + compliance + privacy agents run concurrently")
    print("  + Better quality: specialist prompts produce deeper analysis")
    print("  + Structured flow: explicit graph topology with routing logic")
    print()
    print("[Stage 4 (Monolith) vs Stage 5 (Distributed A2A)]")
    print("  +---------------------------+-------------------------------+")
    print("  | Stage 4 (In-Process)      | Stage 5 (A2A Protocol)        |")
    print("  +---------------------------+-------------------------------+")
    print("  | Single process            | Multiple services (ports)     |")
    print("  | Direct function calls     | HTTP-based A2A protocol       |")
    print("  | Shared memory             | Message passing               |")
    print("  | Simple deployment         | Independent scaling           |")
    print("  | Tight coupling            | Loose coupling                |")
    print("  | Easy to debug             | Service discovery + registry  |")
    print("  | Good for small teams      | Good for large organisations  |")
    print("  +---------------------------+-------------------------------+")
    print()
    print("Stage 5 takes this same graph topology and deploys each agent as an independent A2A service.")
    print("=" * 70)


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(main())
