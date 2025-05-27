import os
from dotenv import load_dotenv
from langchain.llms import OpenAI
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain

# Load environment variables
load_dotenv()

# Initialize OpenAI with API key
llm = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    temperature=0
)

# Create prompt template
prompt = PromptTemplate(
    input_variables=["log_text"],
    template="You're a DevOps agent. Analyze the following log and recommend what to do:\n\n{log_text}"
)

# Create chain
chain = LLMChain(llm=llm, prompt=prompt)

def analyze_log(log_text: str) -> str:
    """
    Analyze the provided log text using LangChain and OpenAI.
    
    Args:
        log_text (str): The log text to analyze
        
    Returns:
        str: AI's recommended action
    """
    try:
        # Run the chain
        response = chain.invoke({"log_text": log_text})
        return response["text"]
    except Exception as e:
        return f"Error analyzing log: {str(e)}" 