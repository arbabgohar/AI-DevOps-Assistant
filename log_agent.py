import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate

load_dotenv()

_llm = ChatOpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    model="gpt-4o-mini",
    temperature=0,
)

_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        (
            "You are a senior DevOps engineer. "
            "Analyze the provided system log and give concise, actionable recommendations. "
            "Identify errors, warnings, and performance issues. "
            "Format your response with clear sections: Summary, Issues Found, and Recommended Actions."
        ),
    ),
    ("human", "{log_text}"),
])

_chain = _prompt | _llm


def analyze_log(log_text: str) -> str:
    """
    Analyze the provided log text using LangChain and OpenAI.

    Args:
        log_text: The log text to analyze.

    Returns:
        AI's recommendations as a string.

    Raises:
        Exception: Propagates any LLM or network errors to the caller.
    """
    response = _chain.invoke({"log_text": log_text})
    return response.content
