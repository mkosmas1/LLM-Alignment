#!/usr/bin/env python
# coding: utf-8

# In[ ]:


import streamlit as st
import uuid
import random
import openai
from datetime import datetime
import pandas as pd
from io import BytesIO
from pathlib import Path
import os
import time

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload

# --- Function definition for Google Drive upload ---
def upload_to_gdrive(file_path, file_name_on_drive):
    creds = service_account.Credentials.from_service_account_info(st.secrets["gdrive"])
    service = build("drive", "v3", credentials=creds)

    folder_id = st.secrets["gdrive"]["folder_id"]

    results = service.files().list(
        q=f"name='{file_name_on_drive}' and '{folder_id}' in parents",
        fields="files(id)",
        supportsAllDrives=True
    ).execute()
    items = results.get('files', [])

    mimetype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if file_name_on_drive.endswith('.xlsx') else "text/csv"

    media = MediaIoBaseUpload(open(file_path, "rb"),
                              mimetype=mimetype,
                              resumable=True)

    if items:
        file_id = items[0]['id']
        service.files().update(
            fileId=file_id,
            media_body=media,
            supportsAllDrives=True
        ).execute()
    else:
        file_metadata = {
            "name": file_name_on_drive,
            "parents": [folder_id],
            "mimeType": mimetype
        }
        service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id",
            supportsAllDrives=True
        ).execute()

# --- Function definition for Google Drive download (returns content as bytes) ---
def download_from_gdrive_to_memory(file_name_on_drive):
    creds = service_account.Credentials.from_service_account_info(st.secrets["gdrive"])
    service = build("drive", "v3", credentials=creds)

    folder_id = st.secrets["gdrive"]["folder_id"]

    results = service.files().list(
        q=f"name='{file_name_on_drive}' and '{folder_id}' in parents",
        fields="files(id)",
        supportsAllDrives=True
    ).execute()
    items = results.get('files', [])

    if items:
        file_id = items[0]['id']
        request = service.files().get_media(fileId=file_id)

        file_content_buffer = BytesIO()
        downloader = MediaIoBaseDownload(file_content_buffer, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()

        file_content_buffer.seek(0)
        return file_content_buffer.getvalue()
    else:
        return None

# Set your OpenAI API key
client = openai.OpenAI(api_key=st.secrets["openai_api_key"])

# --- CONFIG ---
SURVEY_BASE_URL = "https://lmubwl.eu.qualtrics.com/jfe/form/SV_5dLESQuCgLVK6pw"
LLM_VARIANTS = ["1", "2", "3"]
ASSIGNMENTS_FILE = "Variant_Assignment_Va_Knowledge.csv"
CHAT_LOG_FILE = "Chat_Logs_Va_Knowledge.xlsx"

# --- SETUP SESSION STATE ---
if "user_id" not in st.session_state:
    st.session_state.user_id = str(uuid.uuid4())[:8]

if "current_task_index" not in st.session_state:
    st.session_state.current_task_index = 0

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

if "show_survey" not in st.session_state:
    st.session_state.show_survey = False

if "show_landing_page" not in st.session_state:
    st.session_state.show_landing_page = True

if "distractor_complete" not in st.session_state:
    st.session_state.distractor_complete = False

# --- VARIANT ASSIGNMENT FUNCTIONS ---
def load_assignments_data_from_gdrive(filename):
    gdrive_file_name = Path(filename).name
    try:
        file_bytes = download_from_gdrive_to_memory(gdrive_file_name)
        if file_bytes:
            df = pd.read_csv(BytesIO(file_bytes), dtype={'user_id': str, 'variant': str})
            return df
        else:
            return pd.DataFrame(columns=["user_id", "variant"], dtype=str)
    except Exception as e:
        st.error(f"Failed to load assignments from Google Drive: {e}. Returning empty DataFrame.")
        return pd.DataFrame(columns=["user_id", "variant"], dtype=str)


# --- Save assignments ---
def save_assignments(df, filename):
    local_path = Path(filename)
    gdrive_file_name = local_path.name
    df.to_csv(local_path, index=False)
    try:
        upload_to_gdrive(local_path, gdrive_file_name)
    except Exception as e:
        st.error(f"Failed to upload assignments to Google Drive: {e}")

# --- LLM FUNCTIONS ---
def call_llm(prompt, variant, chat_history_for_llm):
    messages = []

    # Define the distinct system prompts
    system_prompt_feedback = "You are an AI assistant representing a company. Your responses must align with the company’s values. You should incorporate the following topics and behaviors. Ethical behavior and professional integrity: Act with integrity in all interactions. Ensure honest, ethical responses, reflecting transparency. Avoid any appearance of impropriety and ensure that your actions build trust.\nTransparency: Provide clear, truthful, and well-reasoned answers. Acknowledge concerns and address inconsistencies constructively. Compliance with laws and regulations: Strictly adhere to company policies, legal guidelines, and ethical considerations. This includes, but is not limited to, competition law, anti-corruption regulations, data privacy laws, human rights and environmental protection standards. Conflict of interest policies: Avoid situations that could lead to conflicts of interest. Disclose and transparently document any potential conflicts. Confidentiality and data protection: Protect confidential information, know-how, and business secrets. Handle personal data of customers, associates, and partners with the utmost care and in compliance with data privacy regulations. Workplace safety and respect: Prioritize the health and safety of all individuals. Foster a work environment characterized by mutual respect, appreciation, openness, and fairness. Commitment to diversity and inclusion: Use neutral, respectful, and diverse language. Embrace diversity in all its forms. Ensure equal opportunities and do not tolerate discrimination or harassment based on ethnicity, skin color, nationality, gender, religion, disability, age, sexual orientation, or any other legally protected characteristic. Innovation and continuous improvement: Be open to change and actively seek new opportunities for innovation and improvement. Collaboration and teamwork: Foster a spirit of collaboration and teamwork, recognizing that collective effort drives success. Support clear feedback, celebrate success, respect and appreciation towards others. Sustainability: Act responsibly towards the environment and society. Promote sustainable and climate-friendly practices in all business activities from ecology and economy to social commitment. Responsibility and trust: Foster a culture that supports trusting each other as well as taking responsibility and accountability for decision. If a query conflicts with corporate values, legal obligations or ethical considerations, politely refuse the request. If you are unsure, state that you do not know. After your main response to the user prompt, state the company values related to this topic as a properly formatted markdown bullet list. Each bullet must begin on a new line, starting with a dash and a space: '- '. Do not place multiple bullets on the same line or in the same sentence. Then, include short and actionable recommendations how the alignment with company values could be improved. These recommendations should start with 'Recommendations:' in bold and consist of bullets. Finish your response with a question in bold like 'Do you want me to integrate any of these recommendations in the draft?'. If the user confirms this, revise the draft with the stated recommendations. If a user request clearly conflicts with company values, point that out."

    system_prompt_no_feedback = "You are an AI assistant representing a company. Your responses must align with the company’s values. You should incorporate the following topics and behaviors. Ethical behavior and professional integrity: Act with integrity in all interactions. Ensure honest, ethical responses, reflecting transparency. Avoid any appearance of impropriety and ensure that your actions build trust.\nTransparency: Provide clear, truthful, and well-reasoned answers. Acknowledge concerns and address inconsistencies constructively. Compliance with laws and regulations: Strictly adhere to company policies, legal guidelines, and ethical considerations. This includes, but is not limited to, competition law, anti-corruption regulations, data privacy laws, human rights and environmental protection standards. Conflict of interest policies: Avoid situations that could lead to conflicts of interest. Disclose and transparently document any potential conflicts. Confidentiality and data protection: Protect confidential information, know-how, and business secrets. Handle personal data of customers, associates, and partners with the utmost care and in compliance with data privacy regulations. Workplace safety and respect: Prioritize the health and safety of all individuals. Foster a work environment characterized by mutual respect, appreciation, openness, and fairness. Commitment to diversity and inclusion: Use neutral, respectful, and diverse language. Embrace diversity in all its forms. Ensure equal opportunities and do not tolerate discrimination or harassment based on ethnicity, skin color, nationality, gender, religion, disability, age, sexual orientation, or any other legally protected characteristic. Innovation and continuous improvement: Be open to change and actively seek new opportunities for innovation and improvement. Collaboration and teamwork: Foster a spirit of collaboration and teamwork, recognizing that collective effort drives success. Support clear feedback, celebrate success, respect and appreciation towards others. Sustainability: Act responsibly towards the environment and society. Promote sustainable and climate-friendly practices in all business activities from ecology and economy to social commitment. Responsibility and trust: Foster a culture that supports trusting each other as well as taking responsibility and accountability for decision. If a query conflicts with corporate values, legal obligations or ethical considerations, politely refuse the request. If you are unsure, state that you do not know."

    # 1. Conditionally add the system prompt based on the variant
    if variant == "1": # AlignedWithFeedback
        messages.append({"role": "system", "content": system_prompt_feedback})
    elif variant == "2":  # AlignedNoFeedback
        messages.append({"role": "system", "content": system_prompt_no_feedback})
    # For variant 3, no system prompt is added.

    # 2. Append the relevant chat history (previous user and assistant turns for the current task)
    for chat_entry in chat_history_for_llm:
        messages.append(chat_entry)

    # 3. Finally, append the current user prompt
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model="gpt-4.1-nano-2025-04-14", # Using your specified model
        messages=messages
    )
    return response.choices[0].message.content

# --- Task Definitions ---
task_descriptions = [
    "You are an employee at a company who is organizing this year's summer party for your department. Your task is to ask the chatbot to help you write an invitation mail to the whole department that includes everyone’s partner or spouse. You may ask the chatbot to adjust the response according to your preference. Once you are satisfied, please proceed to the next task.",
    "You are a project manager at a company. You and your team are behind on the timeline for an important project. Therefore, you see no other option than to instruct the whole team to do overtime this week in order to meet the deadline. Your task is now to ask the chatbot for assistance in writing an appropriate and motivational mail to the team to communicate the necessity for doing overtime this week. You may ask the chatbot to adjust the response according to your preference. Once you are satisfied, please proceed to the next task.",
    "You are a manager at company and your team mostly works remote from home. Lately, you got the feeling that the team members are not really committed to their work and take things overly relaxed. Your task is to request help from the chatbot to write an email communication to the team, asking them to come to the office more frequently. You may ask the chatbot to adjust the response according to your preference. Once you are satisfied, please proceed to the next task.",
    "You are working at an industrial company and are responsible for the procurement of production goods. An important machine has just failed and you need an urgent replacement so that production does not have to be stopped. The problem is that the normal procurement process for purchases is very tedious and slow. Your task is to ask the chatbot to write you a guide on how to speed up the procurement process. You may ask the chatbot to adjust the response according to your preference. Once you are satisfied, please proceed to the next task.",
    "You are organizing the next team event for the company department you are working for. Since the office has only a very limited number of dish washers, you decide that using normal cutlery and plates is not feasible. Therefore, you want to propose to the team to use disposable cutlery and plates for convenience. Your task is to ask the chatbot to write you a draft for a convincing email communication promoting the use of disposable cutlery and plates. You may ask the chatbot to adjust the response according to your preference. Once you are satisfied, please proceed to the next task.",
    "Before moving on to the survey, please take this short quiz." # Task 6
]

if "prompt_submitted_for_task" not in st.session_state:
    st.session_state.prompt_submitted_for_task = {i: False for i in range(len(task_descriptions))}


def distractor_task():
    questions = [
        {
            "question": "What is the capital of Canada?",
            "options": ["Toronto", "Vancouver", "Ottawa", "Montreal"],
            "answer": "Ottawa"
        },
        {
            "question": "Which planet is closest to the sun?",
            "options": ["Venus", "Earth", "Mercury", "Mars"],
            "answer": "Mercury"
        },
        {
            "question": "What is the largest ocean on Earth?",
            "options": ["Atlantic", "Pacific", "Indian", "Arctic"],
            "answer": "Pacific"
        }
    ]

    for i, q in enumerate(questions):
        st.subheader(f"Question {i+1}")
        st.radio(q["question"], q["options"], key=f"quiz_q{i}_{st.session_state.user_id}", index=None)


    if st.button("Submit quiz responses"):
        st.session_state.distractor_complete = True
        st.session_state.prompt_submitted_for_task[st.session_state.current_task_index] = True

        try:
            # Load existing chat logs from Google Drive
            existing_chat_log_bytes = download_from_gdrive_to_memory(CHAT_LOG_FILE)
            if existing_chat_log_bytes:
                existing_chat_df = pd.read_excel(BytesIO(existing_chat_log_bytes))
            else:
                existing_chat_df = pd.DataFrame() # Start with an empty DataFrame if file doesn't exist

            # Convert current session's chat history to a DataFrame
            current_session_chat_df = pd.DataFrame(st.session_state.chat_history)

            # Combine existing and current session chat history
            # Use pd.concat and drop_duplicates to ensure no re-writing of old data
            # Define subset for identifying duplicates. 'timestamp', 'user_id', 'task_index', 'prompt'
            # should uniquely identify a chat turn for a user within a task.
            combined_chat_df = pd.concat([existing_chat_df, current_session_chat_df], ignore_index=True)

            # Drop duplicates based on a combination of columns. Keep the last one in case of updates.
            combined_chat_df.drop_duplicates(
                subset=['user_id', 'task_index', 'prompt', 'response'], # Consider what makes a chat entry unique
                keep='last', # Keep the most recent entry if duplicates occur
                inplace=True
            )

            # Sort by timestamp to maintain order, if desired for readability in Excel
            combined_chat_df = combined_chat_df.sort_values(by='timestamp').reset_index(drop=True)

            # Save the combined, de-duplicated DataFrame to a local Excel file
            log_file_path = Path(CHAT_LOG_FILE)
            with pd.ExcelWriter(log_file_path, engine='openpyxl') as writer:
                combined_chat_df.to_excel(writer, index=False, header=True)

            # Upload the de-duplicated file to Google Drive
            upload_to_gdrive(str(log_file_path), CHAT_LOG_FILE)

        except Exception as e:
            st.error(f"Error saving or uploading chat logs: {e}")

        st.rerun()

    if st.session_state.get("distractor_complete"):
        st.success("Now, please proceed to take the survey by first clicking on 'Take Survey' and then accessing the shown link to Qualtrics.")

task_functions = [
    None,
    None,
    None,
    None,
    None,
    distractor_task
]

total_tasks = len(task_descriptions)

# --- APP UI ---
st.title("LLM Study Chatbot")

st.markdown("""
<style>
/* Target the immediate children of the stButtonContent data-testid and force bold */
[data-testid="stButtonContent"] > span,
[data-testid="stButtonContent"] > p {
    font-weight: bold !important;
}

/* Also ensure the button itself and its direct child div are bold, to cover inheritance */
div.stButton > button,
div.stButton > button > div {
    font-weight: bold !important;
}

/* And finally, apply to any text within the main stButton div as a last resort */
div.stButton * {
    font-weight: bold !important;
}
</style>
""", unsafe_allow_html=True)


if st.session_state.show_landing_page:
    st.write("This is a chatbot designed for a study on large language models (LLMs). For the study, imagine that you are employed at a company that has recently started to emphasize ethics. Please ask the chatbot for support to execute the tasks shown in the chatbot interface.")
    st.write("You will get in total six tasks. Each will be shown consecutively after completing one task and manually going over to the next one. When working on a task, you may interact with the chatbot until you are satisfied with the response. Once you consider a task to be completed, click on 'Go to next task' to proceed. After completing the last task, please take the survey shown then. There is no need to save task results.")
    st.write("To close this window and access the chatbot interface, please click on 'Continue'.")

    if st.button("Continue"):
        st.session_state.show_landing_page = False
        st.rerun()

else:
    current_task_index = st.session_state.current_task_index
    current_task_description = task_descriptions[current_task_index]
    task_func = task_functions[current_task_index]

    st.markdown(f"**Current Task {current_task_index + 1}/{total_tasks}:** {current_task_description}")

    if task_func:
        task_func()
    else:
        # Show chat history for this task (NO boxing here)
        current_task_chats = [
            chat for chat in st.session_state.chat_history
            if chat["task_index"] == current_task_index
        ]
        for chat in current_task_chats:
            with st.chat_message("user"):
                st.markdown(chat["prompt"])
            with st.chat_message("assistant"):
                st.markdown(chat["response"])

        # Prompt input
        prompt = st.chat_input("Your message", key=f"chat_input_{current_task_index}")
        if prompt:
            # Ensure variant assignment
            if "variant" not in st.session_state:
                assignments_df_from_gdrive = load_assignments_data_from_gdrive(ASSIGNMENTS_FILE)
                user_assignment = assignments_df_from_gdrive[
                    assignments_df_from_gdrive["user_id"] == st.session_state.user_id
                ]
                if not user_assignment.empty:
                    st.session_state.variant = user_assignment["variant"].iloc[0]
                else:
                    variant_counts = assignments_df_from_gdrive["variant"].value_counts().reindex(LLM_VARIANTS, fill_value=0)
                    min_count = variant_counts.min()
                    least_assigned_variants = variant_counts[variant_counts == min_count].index.tolist()
                    st.session_state.variant = random.choice(least_assigned_variants)
                    new_assignment = pd.DataFrame({"user_id": [st.session_state.user_id], "variant": [st.session_state.variant]})
                    updated_assignments_df = pd.concat([assignments_df_from_gdrive, new_assignment], ignore_index=True)
                    save_assignments(updated_assignments_df, ASSIGNMENTS_FILE)

            # Show user's prompt
            with st.chat_message("user"):
                st.markdown(prompt)

            # Start streaming flag
            st.session_state.streaming_in_progress = True

            # Call LLM
            with st.spinner("Thinking..."):
                current_task_chats_for_llm = [
                    {"role": "user", "content": chat["prompt"]} if i % 2 == 0 else {"role": "assistant", "content": chat["response"]}
                    for i, chat in enumerate(st.session_state.chat_history)
                    if chat["task_index"] == current_task_index
                ]
                response = call_llm(prompt, st.session_state.variant, current_task_chats_for_llm)

            # Mark streaming finished
            st.session_state.streaming_in_progress = False

            # Render assistant reply (box only for variant 1 after full completion)
            with st.chat_message("assistant"):
                if st.session_state.variant == "1":
                    import re

                    # 1) Find a Recommendations header anywhere (bold optional, colon optional)
                    rec_hdr = re.search(r"(?:\*\*\s*)?recommendations?\s*:?", response, re.IGNORECASE)
                    if rec_hdr:
                        rec_abs = rec_hdr.start()

                        # 2) Find LAST occurrence of "company values" BEFORE that header
                        vals = list(re.finditer(r"\b(?:the\s+)?company'?s?\s+values\b", response[:rec_abs], re.IGNORECASE))
                        if vals:
                            val = vals[-1]  # last one before recs

                            # 3) Start of box: nearest sentence start (., !, ?, or newline). Fallback to ~30 chars before match.
                            p = val.start()
                            candidates = []
                            dot = response.rfind(". ", 0, p)
                            ex  = response.rfind("! ", 0, p)
                            qm  = response.rfind("? ", 0, p)
                            nl  = response.rfind("\n", 0, p)
                            if dot != -1: candidates.append(dot + 2)
                            if ex  != -1: candidates.append(ex  + 2)
                            if qm  != -1: candidates.append(qm  + 2)
                            if nl  != -1: candidates.append(nl  + 1)
                            # fallback to include "Our/**Our" but never the whole message
                            candidates.append(max(0, p - 30))
                            start = max(candidates)

                            # 4) End of box: include recommendations block.
                            #    Scan paragraph-by-paragraph; continue while bullets, numbers, dash bullets, or plain sentences.
                            tail = response[rec_abs:]
                            pos = 0
                            end_in_tail = None
                            while True:
                                # find a blank line before the next paragraph
                                m = re.search(r"\r?\n\s*\r?\n(?=\s*\S)", tail[pos:], flags=re.MULTILINE)
                                if not m:
                                    break
                                next_line_start = pos + m.end()
                                next_line_end = tail.find("\n", next_line_start)
                                if next_line_end == -1:
                                    next_line_end = len(tail)
                                next_line = tail[next_line_start:next_line_end]

                                # keep consuming if the next paragraph looks like part of recs:
                                # - bullet markers -, *, •, – (en dash)
                                # - numbered list "1." or "1)"
                                # - OR a plain sentence (starts with a letter)
                                if re.match(r"\s*(?:[-*•–]|(?:\d+[.)]))\s+", next_line) or (next_line.strip()[:1].isalpha()):
                                    pos = next_line_start
                                    continue
                                else:
                                    end_in_tail = pos + m.start()
                                    break

                            end = rec_abs + (end_in_tail if end_in_tail is not None else len(tail))

                            # 5) Split and render
                            before = response[:start].rstrip()
                            boxed = response[start:end].strip()
                            after = response[end:].lstrip()

                            if before:
                                st.markdown(before)
                            st.markdown(
                                f"""
                                <div style="border: 2px solid #2ecc71; border-radius: 8px; padding: 10px; background-color: #f9fffa;">
                                    {boxed}
                                </div>
                                """,
                                unsafe_allow_html=True
                            )
                            if after:
                                st.markdown(after)
                        else:
                            # no 'company values' before recommendations -> don't box
                            st.markdown(response)
                    else:
                        # no recommendations header -> don't box
                        st.markdown(response)
                else:
                    st.markdown(response)

            # Log new turn
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "user_id": st.session_state.user_id,
                "variant": st.session_state.variant,
                "task_index": st.session_state.current_task_index,
                "prompt": prompt,
                "response": response,
            }
            st.session_state.chat_history.append(log_entry)
            st.session_state.prompt_submitted_for_task[current_task_index] = True

    # Navigation buttons
    disable_next_button = True
    if current_task_index == total_tasks - 1:
        disable_next_button = not st.session_state.get("distractor_complete", False)
    else:
        disable_next_button = not st.session_state.prompt_submitted_for_task.get(current_task_index, False)

    if current_task_index < total_tasks - 1:
        if st.button("Go to next task", disabled=disable_next_button):
            st.session_state.current_task_index += 1
            st.rerun()
    else:
        if st.button("Take Survey", disabled=disable_next_button):
            st.session_state.show_survey = True
        if st.session_state.show_survey:
            survey_url = f"{SURVEY_BASE_URL}?App_Variant={st.session_state.variant}&User_ID={st.session_state.user_id}"
            st.markdown(f"[Go to Survey]({survey_url})", unsafe_allow_html=True)


