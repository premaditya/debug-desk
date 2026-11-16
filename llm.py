import os
from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
import streamlit as st

load_dotenv()

MODEL = "gemini-3.6-flash"
TOP_K = 5

# Retrieval
embeddings = GoogleGenerativeAIEmbeddings(
    model="gemini-embedding-001",
    task_type="RETRIEVAL_QUERY",
)


@st.cache_resource
def load_database():
    vectorstore = Chroma(
        collection_name="debugdesk",
        persist_directory="chroma_db",
        embedding_function=embeddings,
    )

    return vectorstore

# LLM chain
llm = ChatGoogleGenerativeAI(model=MODEL, temperature=0)

prompt = ChatPromptTemplate.from_messages([
    ("system",
     """You are DebugDesk, an assistant that helps developers fix errors.
Answer ONLY using the numbered sources below.
- Explain the likely cause, then give the fix as clear steps.
- Cite sources like [1], [2] after the statements they support.
- If the sources do not contain the answer, say so. Do not guess.

SOURCES:
{context}"""),
    ("human", "{question}"),
])

chain = prompt | llm | StrOutputParser()


def retrieve(question, tech = None):
    vectorstore = load_database()
    search_filter = {"technology": tech.lower()} if tech and tech != "All" else None
    raw = vectorstore.similarity_search_with_score(question, k=TOP_K * 10, filter= search_filter)
    docs, seen = [], set()
    for doc, distance in raw:
        key = doc.metadata.get("source")
        if key in seen:
            continue
        seen.add(key)
        docs.append(doc)
        if len(docs) == TOP_K:
            break
    return docs


def format_docs(docs):
    parts = []
    for i, doc in enumerate(docs, start=1):
        title = doc.metadata.get("title", "")
        parts.append(f"[{i}] {title}\n{doc.page_content}")
    return "\n\n".join(parts)


def get_answer(question, tech = None):
    docs = retrieve(question, tech)
    answer = chain.invoke({
        "question": question,
        "context": format_docs(docs),
    })
    return answer, docs


if __name__ == "__main__":
    question = input("Error or question: ")
    answer, docs = get_answer(question)
    print("\n" + answer)
    print("\nSources:")
    for i, doc in enumerate(docs, start=1):
        print(f"[{i}] {doc.metadata.get('title')} - {doc.metadata.get('source_url', '')}")