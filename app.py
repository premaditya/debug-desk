from dotenv import load_dotenv
load_dotenv()

import time
import uuid
from langsmith import Client, traceable

import streamlit as st
from llm import get_answer

client = Client()

@traceable(name = "DebugDesk Request")
def get_answer_trace(error_text, tech):
    return get_answer(error_text, tech)

def find_llm_run(run):
    if run.run_type == "llm":
        return run

    for child in run.child_runs or []:
        found = find_llm_run(child)

        if found is not None:
            return found

    return None


def get_langsmith_metrics(run_id):
    status = "Trace is still being processed"

    for attempt in range(5):
        try:
            if attempt > 0:
                time.sleep(2)

            trace = client.read_run(run_id, load_child_runs=True)

            llm_run = find_llm_run(trace)

            if llm_run is None:
                status = "LLM run not available yet"

                continue

            if llm_run.total_tokens is None:
                status = "Token usage not ready yet"

                continue

            if not (llm_run.start_time and llm_run.end_time):
                status = "LLM timestamps not available yet"

                continue

            llm_latency = (llm_run.end_time - llm_run.start_time).total_seconds()

            

            if not (trace.start_time and trace.end_time):
                status = "Total latency not ready yet"
                continue

            total_latency = (trace.end_time - trace.start_time).total_seconds()

            return {
                "status" : "Success",
                "input_tokens" : llm_run.prompt_tokens,
                "output_tokens" : llm_run.completion_tokens,
                "total_tokens" : llm_run.total_tokens,
                "estimated_cost" : llm_run.total_cost,
                "llm_latency" : llm_latency,
                "total_latency": total_latency
            }

        except Exception as error:
            status = f"LangSmith error: {error}"


    return {"status": status}

def show_number(value):
    if value is None:
        return "N/A"

    return f"{int(value):,}"


def render_sidebar_metrics():

    metrics = st.session_state.get(
        "metrics",
        {"status" : "Ask a question to see metrics"},
    )

    with st.sidebar:
        st.markdown("""
        <div class = "metrics">
            <h2>📊<strong>LangSmith Metrics</strong></h2>
            <p><strong>Project: debugdesk</strong></p> 
        </div>
        """, unsafe_allow_html= True)

        with st.container(key= "metrics"):

            st.metric("Input Tokens", show_number(metrics.get("input_tokens")))
            st.metric("Output Tokens", show_number(metrics.get("output_tokens")))
            st.metric("Total Tokens", show_number(metrics.get("total_tokens")))

            cost = metrics.get("estimated_cost")

            st.metric(
                "Estimated cost",
                "N/A" if cost is None else f"${float(cost):.4f}",
            )

            latency = metrics.get("llm_latency")

            st.metric(
                "LLM latency",
                "N/A" if latency is None else f"{latency:.2f} s",
            )

            total_latency = metrics.get("total_latency")
            st.metric(
                "Total latency",
                "N/A" if total_latency is None else f"{total_latency:.2f} s",
            )

        status = metrics["status"]

        if status == "Success":
            st.success("LLM metrics retrieved")

        elif status == "Ask a question to see metrics":
            st.info(status)

        else:
            st.warning(f"Trace status: {status}")



st.set_page_config(
    page_icon = "🪛",
    page_title= "DEBUGDESK",
    layout= "centered"
)

with open("style.css", 'r') as s:

    style = s.read()


st.markdown(f"""
<style>
{style}
</style>
""",unsafe_allow_html= True)


with st.sidebar:

    st.markdown("""
    <div class = "sidebar-heading">
    <h1>DebugDesk</h1>
    <p>AI-Powered Debug desk with Official documentation sources</p>
    </div>
    """, unsafe_allow_html = True)

    tech = st.selectbox(
        "Select A Technology",
        ["All",
         "Python",
        "Java",
        "JavaScript",
        "MySQL",
        "Streamlit"]
    )

    examples = {
        "": "",
        "Python: NameError": "NameError: name 'x' is not defined",
        "Java: NullPointerException": "NullPointerException",
        "JavaScript: ReferenceError": "ReferenceError: x is not defined",
        "MySQL: Duplicate entry": "ERROR 1062: Duplicate entry for key PRIMARY",
        "Streamlit: Session state": "st.session_state has no key",
    }

    example = st.selectbox(
        "Select an Example",
        options= list(examples.keys())
    )

    text = examples[example]

    if text:
        val = text
    else:
        val = ""


st.markdown(f"""
<div class = "Hero-header">
<h1>DebugDesk</h1>
<p>Fix Errors with evidence from the docs</p>
</div>
""", unsafe_allow_html= True)

error_text = st.text_area(
    "Enter the Error:",
    placeholder= "Select the technology in sidebar and enter the Error here....",
    value= val
)

c1, c2, c3 = st.columns([1,1,1])

with c3:
    answer = st.button(
        "Get Fix"
    )


if answer:

    if not error_text:
        st.warning("Please Enter an error first")
        st.stop()

    with st.spinner("Searching Sources and Generating Fix..."):
        run_id = uuid.uuid4()

        response, docs = get_answer_trace(
            error_text,
            tech,
            langsmith_extra = {"run_id": run_id},
        )
        

    if not docs:
        st.info("No sources found for this technology yet.")
        st.stop()

    with st.spinner("Fetching LangSmith metrics...."):
        metrics = get_langsmith_metrics(run_id)

    st.session_state["metrics"] = metrics

    st.markdown("""
    <div class = "answer-header">
        <h2>DEBUG DESK RESPONSE</h2>
    </div>
    """, unsafe_allow_html= True)

    with st.container(key= "answer-container"):

        st.markdown(response)

    st.markdown("""
        <div class = "answer-header">
            <h3>Source Documents</h3>
        </div>
        """, unsafe_allow_html= True)
    with st.container(key = "source-container"):

        for i, doc in enumerate(docs, start = 1):

            title = doc.metadata.get("title", "Untitled")
            url = doc.metadata.get("source_url", "")
            tech_name = doc.metadata.get("technology", "")


            with st.expander(f"{i} {title} {tech_name}"):

                if url:
                    st.markdown(f"[Open Original Page]({url})")

                st.text(doc.page_content)

render_sidebar_metrics()