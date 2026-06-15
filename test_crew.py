# Save as test_crew.py in root folder
from crewai import Agent, Task, Crew
from langchain_groq import ChatGroq
import os
from dotenv import load_dotenv

load_dotenv()

print("Testing CrewAI installation...")

try:
    llm = ChatGroq(
        temperature=0.3,
        groq_api_key=os.getenv("GROQ_API_KEY"),
        model_name="llama-3.1-8b-instant"
    )

    agent = Agent(
        role="Test Agent",
        goal="Test if CrewAI works",
        backstory="Testing installation",
        llm=llm,
        verbose=False
    )

    task = Task(
        description="Say 'CrewAI is working correctly'",
        agent=agent,
        expected_output="A confirmation message"
    )

    crew = Crew(
        agents=[agent],
        tasks=[task],
        verbose=False
    )

    result = crew.kickoff()
    print(f"✓ CrewAI Test Result: {result}")

except Exception as e:
    print(f"✗ CrewAI Error: {e}")
    print("\nThis is normal if CrewAI has version conflicts.")
    print("Your AI agents (LangChain only) will still work.")
