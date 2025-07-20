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

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
# --- Function definition for Google Drive upload ---
# This is largely your existing function, ensuring it takes file_path and file_name_on_drive
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

    # Determine mimetype based on file extension
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

# --- NEW: Function definition for Google Drive download ---
def download_from_gdrive(file_name_on_drive, local_file_path):
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

        file_content = BytesIO()
        downloader = MediaIoBaseDownload(file_content, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()

        file_content.seek(0)

        with open(local_file_path, "wb") as f:
            f.write(file_content.read())
        return True
    return False


# Set your OpenAI API key
client = openai.OpenAI(api_key=st.secrets["openai_api_key"])

# --- CONFIG ---
SURVEY_BASE_URL = "https://qualtricsxmhy5sqlrsn.qualtrics.com/jfe/form/SV_3RbmBH5lazAheVE"
LLM_VARIANTS = ["1", "2", "3"]
# 1 = AlignedWithFeedback; 2 = AlignedNoFeedback
ASSIGNMENTS_FILE = "variant_assignments.csv"

# --- SETUP SESSION STATE ---
if "user_id" not in st.session_state:
    st.session_state.user_id = str(uuid.uuid4())[:8]

if "current_task_index" not in st.session_state:
    st.session_state.current_task_index = 0
    # NEW: Initialize a dictionary to track if a prompt has been submitted for each task
    st.session_state.prompt_submitted_for_task = {i: False for i in range(len(LLM_VARIANTS))}


# --- VARIANT ASSIGNMENT (FILE-BASED) ---
def load_assignments(filename):
    gdrive_file_name = Path(filename).name # Get just the filename (e.g., "variant_assignments.csv")
    local_path = Path(filename) # The local path where the file will be saved/read

    # 1. Try to download from Google Drive first
    try:
        if download_from_gdrive(gdrive_file_name, local_path):
            #st.info(f"Loaded assignments from Google Drive: {gdrive_file_name}")
            return pd.read_csv(local_path)
    except Exception as e:
        # Catch any error during GDrive download (e.g., network, permissions, file not found initially)
        st.warning(f"Could not download '{gdrive_file_name}' from Google Drive: {e}. Checking local file.")

    # 2. Fallback to local file if GDrive download failed or file not found on Drive
    if local_path.exists():
        #st.info(f"Loaded assignments from local file: {local_path.name}")
        return pd.read_csv(local_path)

    # 3. If neither exists, create an empty DataFrame
    st.info("No existing assignment file found (local or Drive), creating new DataFrame.")
    return pd.DataFrame(columns=["user_id", "variant"])

def save_assignments(df, filename):
    local_path = Path(filename)
    gdrive_file_name = local_path.name

    # 1. Save locally
    df.to_csv(local_path, index=False)
    #st.info(f"Saved assignments locally to: {local_path.name}")

    # 2. Upload to Google Drive
    try:
        # Use the common upload_to_gdrive function
        upload_to_gdrive(local_path, gdrive_file_name)
        #st.success(f"Uploaded assignments to Google Drive: {gdrive_file_name}")
    except Exception as e:
        st.error(f"Failed to upload assignments to Google Drive: {e}")


assignments_df = load_assignments(ASSIGNMENTS_FILE)


if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

if "show_survey" not in st.session_state:
    st.session_state.show_survey = False

if "show_landing_page" not in st.session_state:
    st.session_state.show_landing_page = True


# --- LLM FUNCTIONS ---
def call_llm(prompt, variant):
    if variant == "1": # AlignedWithFeedback
        system_prompt_feedback = "You are an AI assistant representing a company. Your responses must align with the company’s values. You should incorporate the following topics and behaviors. Ethical behavior and professional integrity: Act with integrity in all interactions. Ensure honest, ethical responses, reflecting transparency. Avoid any appearance of impropriety and ensure that your actions build trust.\nTransparency: Provide clear, truthful, and well-reasoned answers. Acknowledge concerns and address inconsistencies constructively. Compliance with laws and regulations: Strictly adhere to company policies, legal guidelines, and ethical considerations. This includes, but is not limited to, competition law, anti-corruption regulations, data privacy laws, human rights and environmental protection standards. Conflict of interest policies: Avoid situations that could lead to conflicts of interest. Disclose and transparently document any potential conflicts. Confidentiality and data protection: Protect confidential information, know-how, and business secrets. Handle personal data of customers, associates, and partners with the utmost care and in compliance with data privacy regulations. Workplace safety and respect: Prioritize the health and safety of all individuals. Foster a work environment characterized by mutual respect, appreciation, openness, and fairness. Commitment to diversity and inclusion: Use neutral, respectful, and diverse language. Embrace diversity in all its forms. Ensure equal opportunities and do not tolerate discrimination or harassment based on ethnicity, skin color, nationality, gender, religion, disability, age, sexual orientation, or any other legally protected characteristic. Innovation and continuous improvement: Be open to change and actively seek new opportunities for innovation and improvement. Collaboration and teamwork: Foster a spirit of collaboration and teamwork, recognizing that collective effort drives success. Support clear feedback, celebrate success, respect and appreciation towards others. Sustainability: Act responsibly towards the environment and society. Promote sustainable and climate-friendly practices in all business activities from ecology and economy to social commitment. Responsibility and trust: Foster a culture that supports trusting each other as well as taking responsibility and accountability for decision. If a query conflicts with corporate values, legal obligations or ethical considerations, politely refuse the request. If you are unsure, state that you do not know. After your main response to the user prompt, state shortly what the company values related to the user prompt are. Then, include short and actionable recommendations how the alignment with company values could be improved. These recommendations should start with 'Recommendations:' (in bold) and consist of bullets. If a user request clearly conflicts with company values, point that out."
        messages = [
            {"role": "system", "content": system_prompt_feedback},
            {"role": "user", "content": prompt}
        ]
    elif variant == "2":  # AlignedNoFeedback
        system_prompt_no_feedback = "You are an AI assistant representing a company. Your responses must align with the company’s values. You should incorporate the following topics and behaviors. Ethical behavior and professional integrity: Act with integrity in all interactions. Ensure honest, ethical responses, reflecting transparency. Avoid any appearance of impropriety and ensure that your actions build trust.\nTransparency: Provide clear, truthful, and well-reasoned answers. Acknowledge concerns and address inconsistencies constructively. Compliance with laws and regulations: Strictly adhere to company policies, legal guidelines, and ethical considerations. This includes, but is not limited to, competition law, anti-corruption regulations, data privacy laws, human rights and environmental protection standards. Conflict of interest policies: Avoid situations that could lead to conflicts of interest. Disclose and transparently document any potential conflicts. Confidentiality and data protection: Protect confidential information, know-how, and business secrets. Handle personal data of customers, associates, and partners with the utmost care and in compliance with data privacy regulations. Workplace safety and respect: Prioritize the health and safety of all individuals. Foster a work environment characterized by mutual respect, appreciation, openness, and fairness. Commitment to diversity and inclusion: Use neutral, respectful, and diverse language. Embrace diversity in all its forms. Ensure equal opportunities and do not tolerate discrimination or harassment based on ethnicity, skin color, nationality, gender, religion, disability, age, sexual orientation, or any other legally protected characteristic. Innovation and continuous improvement: Be open to change and actively seek new opportunities for innovation and improvement. Collaboration and teamwork: Foster a spirit of collaboration and teamwork, recognizing that collective effort drives success. Support clear feedback, celebrate success, respect and appreciation towards others. Sustainability: Act responsibly towards the environment and society. Promote sustainable and climate-friendly practices in all business activities from ecology and economy to social commitment. Responsibility and trust: Foster a culture that supports trusting each other as well as taking responsibility and accountability for decision. If a query conflicts with corporate values, legal obligations or ethical considerations, politely refuse the request. If you are unsure, state that you do not know."
        messages = [
            {"role": "system", "content": system_prompt_no_feedback},
            {"role": "user", "content": prompt}
        ]
    elif variant == "3": # VanillaNoSystemPrompt
        messages = [
            {"role": "user", "content": prompt}
        ]

    response = client.chat.completions.create(
        model="gpt-4.1-nano-2025-04-14",
        messages=messages
    )
    return response.choices[0].message.content

# Summary of Variants: 1 = AlignedWithFeedback; 2 = AlignedNoFeedback; 3 = VanillaNoSystemPrompt



def distractor_task():
    #st.header("Just for Fun 🎯")
    #st.write("Before moving on, please take this short unrelated quiz. It helps us get more balanced and thoughtful feedback.")

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

    responses = {}

    for i, q in enumerate(questions):
        st.subheader(f"Question {i+1}")
        user_answer = st.radio(q["question"], q["options"], key=f"quiz_q{i}")
        responses[q["question"]] = user_answer

    # NEW: Ensure a prompt/interaction has occurred for the distractor task as well.
    # For a quiz, "interacting" means at least one question has been answered (or the Continue button clicked).
    # We'll enable the next button only after the "Continue" button within the quiz is clicked.
    if st.button("Continue"):
        st.session_state.distractor_complete = True
        # NEW: Mark that a prompt/interaction happened for this task
        st.session_state.prompt_submitted_for_task[st.session_state.current_task_index] = True
        st.rerun() # Rerun to update button state immediately

    if st.session_state.get("distractor_complete"):
        st.success("Now, please proceed to take the survey by first clicking on 'Take Survey' and then accessing the shown link to Qualtrics.")


task_descriptions = [
    "You are an employee at a company who is organizing this years’ summer party for your department. Your task is to ask the chatbot to help you write a invitation mail to the whole department that includes everyone’s partner or spouse. You may ask the chatbot to adjust the response according to your preference. Once you are satisfied, please proceed to the next task.",
    "You are a project manager at a company. You and your team are behind on the timeline for an important project. Therefore, you see no other option than to instruct the whole team to do overtime this week in order to meet the deadline. Your task is now to ask the chatbot for assistance in writing an appropriate and motivational mail to the team to communicate the necessity for doing overtime this week. You may ask the chatbot to adjust the response according to your preference. Once you are satisfied, please proceed to the next task.",
    "You are a manager at company and your team mostly works remote from home. Lately, you got the feeling that the team members are not really committed to their work and take things overly relaxed. Your task is to request help from the chatbot to write an email communication to the team, asking them to come to the office more frequently. You may ask the chatbot to adjust the response according to your preference. Once you are satisfied, please proceed to the next task.",
    "You are working at an industrial company and are responsible for the procurement of production goods. An important machine has just failed and you need an urgent replacement so that production does not have to be stopped. The problem is that the normal procurement process for purchases is very tedious and slow. Your task is to ask the chatbot to write you a guide on how to speed up the procurement process. You may ask the chatbot to adjust the response according to your preference. Once you are satisfied, please proceed to the next task.",
    "You are organizing the next team event for the company department you are working for. Since the office has only a very limited number of dish washers, you decide that using normal cutlery/plates is not feasible. Therefore, you want to propose to the team to use disposable cutlery/plates for convenience. Your task is to ask the chatbot to write you a draft for a convincing email communication promoting the use of disposable cutlery/plates. You may ask the chatbot to adjust the response according to your preference. Once you are satisfied, please proceed to the next task.",
    "Before moving on to the survey, please take this short quiz."
]

task_functions = [
    None,  # Task 1 – handled via chatbot
    None,  # Task 2
    None,  # Task 3
    None,  # Task 4
    None,  # Task 5
    distractor_task  # Task 6 – this one runs a Streamlit form, not chatbot
]

total_tasks = len(task_descriptions)

# --- APP UI ---
st.title("LLM Study Chatbot")

# Display the landing page if show_landing_page is True
if st.session_state.show_landing_page:
    st.write("This is a chatbot designed for a study on large language models (LLMs). Please ask the chatbot for support to execute the tasks shown in the chatbot interface. You will get in total five tasks. Each will be shown consecutively after completing one task and manually going over to the next one. When working on a task, you may interact with the chatbot until you are satisfied with the response. Once you consider a task to be completed, click on 'Go to next task' to proceed. There is no need to save task results.")
    st.write("After completing the last task, please take the survey. The survey can be accessed at task five via the link shown after clicking on the button 'Take Survey'.")
    st.write("To close this window and access the chatbot interface, please click on 'X'.")

    if st.button("X"):
        st.session_state.show_landing_page = False
        st.rerun()

else:
    current_task_index = st.session_state.current_task_index
    current_task_description = task_descriptions[current_task_index]
    # Check if this task uses a custom function (like the quiz)
    task_func = task_functions[current_task_index]

    st.markdown(f"**Current Task {current_task_index + 1}/{total_tasks}:** {current_task_description}")

    if task_func:  # If this task has a special function (like the distractor quiz)
        task_func()
    else:
        # Show chat history
        for chat in st.session_state.chat_history:
            st.chat_message("user").markdown(chat["prompt"])
            st.chat_message("assistant").markdown(chat["response"])

        prompt = st.chat_input("Your message")
        if prompt:
            # --- NEW LOGIC: Assign variant ONLY on first prompt submission if not already assigned ---
            if "variant" not in st.session_state:
                # Check if this user_id already exists in the persistent assignments_df
                user_assignment = assignments_df[assignments_df["user_id"] == st.session_state.user_id]

                if not user_assignment.empty:
                    # User already assigned a variant from a previous session (from the loaded assignments_df)
                    st.session_state.variant = user_assignment["variant"].iloc[0]
                else:
                    # This is a new user ID that has submitted its first prompt. Assign a variant.
                    variant_counts = assignments_df["variant"].value_counts().reindex(LLM_VARIANTS, fill_value=0)
                    min_count = variant_counts.min()
                    least_assigned_variants = variant_counts[variant_counts == min_count].index.tolist()
                    st.session_state.variant = random.choice(least_assigned_variants)

                    # Add this new assignment to our assignments_df and save it
                    new_assignment = pd.DataFrame({"user_id": [st.session_state.user_id], "variant": [st.session_state.variant]})

                    # It's crucial to update the global `assignments_df` in the current script run
                    # so subsequent checks in this session or future sessions (after reload) reflect the change.
                    assignments_df = pd.concat([assignments_df, new_assignment], ignore_index=True)
                    save_assignments(assignments_df, ASSIGNMENTS_FILE) # Save the updated assignments_df

            # --- END NEW LOGIC ---

            # Now proceed with LLM call (st.session_state.variant is now guaranteed to be set)
            response = call_llm(prompt, st.session_state.variant)

            # Create the log entry for the *current* interaction
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "user_id": st.session_state.user_id,
                "variant": st.session_state.variant,
                "task_index": st.session_state.current_task_index,
                "prompt": prompt,
                "response": response,
            }
            st.session_state.chat_history.append(log_entry) # Add to session state

            # NEW: Mark that a prompt has been submitted for the current task
            st.session_state.prompt_submitted_for_task[current_task_index] = True

            # --- SAVE THE SINGLE NEW LOG ENTRY TO EXCEL IMMEDIATELY ---
            log_file = Path("chat_logs_all.xlsx")
            df_to_save = pd.DataFrame([log_entry]) # Create DataFrame with ONLY the new entry

            if log_file.exists():
                with pd.ExcelWriter(log_file, engine='openpyxl', mode='a', if_sheet_exists='overlay') as writer:
                    try:
                        existing_df = pd.read_excel(log_file)
                        start_row = len(existing_df) + 1
                        df_to_save.to_excel(writer, index=False, header=False, startrow=start_row)
                    except Exception as e:
                        st.warning(f"Could not append to existing log file, recreating: {e}")
                        # If appending fails, re-create the file with headers
                        with pd.ExcelWriter(log_file, engine='openpyxl') as new_writer:
                            df_to_save.to_excel(new_writer, index=False, header=True)
            else: # File does not exist, so create it with header
                with pd.ExcelWriter(log_file, engine='openpyxl') as writer:
                    df_to_save.to_excel(writer, index=False, header=True)

            # --- UPLOAD TO GOOGLE DRIVE IMMEDIATELY AFTER SAVING ---
            if log_file.exists():
                try:
                    # Pass both the local file path and the desired file name on Google Drive
                    upload_to_gdrive(str(log_file), "chat_logs_all.xlsx")
                except Exception as e:
                    st.error(f"Failed to upload log to Google Drive: {e}")

            # Now, trigger rerun to update the displayed chat history
            st.rerun()

    # Determine if the "Go to next task" button should be disabled
    # It should be disabled if no prompt has been submitted for the current task
    # For the distractor task (index 5), it should be disabled until 'distractor_complete' is True
    disable_next_button = True
    if current_task_index == len(task_descriptions) - 1: # This is the last task (distractor quiz)
        disable_next_button = not st.session_state.get("distractor_complete", False)
    else: # This is a regular chat task
        disable_next_button = not st.session_state.prompt_submitted_for_task.get(current_task_index, False)

    # The buttons for navigation should appear after the main chat interaction area
    if current_task_index < total_tasks - 1:
        if st.button("Go to next task", disabled=disable_next_button):
            st.session_state.current_task_index += 1
            st.session_state.chat_history = [] # Clear chat history for new task
            # NEW: Reset the prompt_submitted_for_task state for the new task
            # We don't need to explicitly set it to False here because it's initialized as False for new tasks.
            # If a task is revisited, it will retain its True state, which is correct.
            st.rerun()
    else:
        #st.markdown("You have completed all tasks. Please take the survey to provide your feedback.")
        if st.button("Take Survey", disabled=disable_next_button): # Apply disabled logic to Survey button too
            st.session_state.show_survey = True

        if st.session_state.show_survey:
            survey_url = f"{SURVEY_BASE_URL}?App_Variant={st.session_state.variant}&User_ID={st.session_state.user_id}"
            st.success("Thank you! Please take the short survey below:")
            st.markdown(f"[Go to Survey]({survey_url})", unsafe_allow_html=True)

