
import time
from datetime import datetime
from llm import get_answer

questions = [
    "I'm getting an UnboundLocalError saying that a local variable is referenced before assignment. How do I fix this?",
    "My Python program is throwing a UnicodeDecodeError when I try to read a file. It says the utf8 codec can't decode a byte. What should I do?",
    "I'm getting a RuntimeError saying the dictionary changed size during iteration. Why is this happening?",
    "I'm trying to load JSON data using json.load(), but it says that a string object has no attribute 'read'. How can I fix it?",
    "How do I convert a datetime object into JSON? I'm getting a TypeError saying it's not JSON serializable.",
    "I'm trying to update a character in a string, but Python gives me a TypeError saying that a str object does not support item assignment. Is there a way to do this?",
    "My jQuery code isn't working. The browser console says '$ is not defined'. What could be causing this?",
    "I'm getting an Unexpected token error when using JSON.parse(). How can I find out what's wrong with my JSON?",
    "Sometimes my JavaScript code crashes because it cannot read a property of undefined. How can I prevent this error?",
    "I'm calling split() on a variable in JavaScript, but it says string.split is not a function. What am I doing wrong?",
    "I upgraded jQuery and now my old .live() function is not working. It says .live() is not a function. What's the replacement?",
    "My Streamlit app is showing an error about SQLite objects being created in a different thread. How can I solve this?",
    "My Python application fails to start on Linux with an error saying libGL.so.1 cannot be opened. How do I fix this?",
    "I'm building a Streamlit app using Docker, but pip install fails with a 'No space left on device' error. How can I resolve it?",
    "I'm getting a KeyError when accessing st.session_state in Streamlit. It says the key doesn't exist. How should I handle this?",
    "I'm planning a trip to France. Which city would you recommend visiting first?",
    "Can you explain how photosynthesis works? I want to understand how plants make their own food.",
    "I missed the 2022 FIFA World Cup. Which country won the tournament?",
    "I'm trying to boil water for cooking. What temperature does water normally boil at?",
    "Can you write a short poem about looking at the moon on a quiet night?"
]

OUTPUT_FILE = f"generation_results_{datetime.now():%Y%m%d_%H%M%S}.txt"

successful = 0
failed = 0
total_time = 0

with open(OUTPUT_FILE, "w", encoding="utf-8") as file:

    for i, question in enumerate(questions, start=1):

        print(f"\nProcessing question {i}/{len(questions)}")

        start_time = time.time()

        try:
            answer, docs = get_answer(question)

            processing_time = time.time() - start_time
            total_time += processing_time
            successful += 1

            file.write(f"{i}. {question}\n\n")
            file.write(str(answer).strip() + "\n\n")
            file.flush()

            print(f"Question {i} completed successfully.")
            print(f"Processing time: {processing_time:.2f} seconds")

        except Exception as e:
            processing_time = time.time() - start_time
            total_time += processing_time
            failed += 1

            print(f"Question {i} failed: {e}")

print("\n========== EVALUATION SUMMARY ==========")
print(f"Total questions: {len(questions)}")
print(f"Successful requests: {successful}")
print(f"Failed requests: {failed}")
print(f"In-context questions: 15")
print(f"Out-of-context questions: 5")
print(f"Total processing time: {total_time:.2f} seconds")

if successful > 0:
    print(f"Average processing time: {total_time / (successful + failed):.2f} seconds")

print(f"\nGenerated answers saved in: {OUTPUT_FILE}")
