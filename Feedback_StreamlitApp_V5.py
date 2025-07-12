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
SURVEY_BASE_URL = "https://qualtricsxmhy5sqlrsn.qualtrics.com/jfe/form/SV_dccYF1pu26jJUHQ"
LLM_VARIANTS = ["1", "2"]
# 1 = AlignedWithFeedback; 2 = AlignedNoFeedback
ASSIGNMENTS_FILE = "variant_assignments.csv"

# --- SETUP SESSION STATE ---
if "user_id" not in st.session_state:
    st.session_state.user_id = str(uuid.uuid4())[:8]

if "current_task_index" not in st.session_state:
    st.session_state.current_task_index = 0

# --- VARIANT ASSIGNMENT (FILE-BASED) ---
def load_assignments(filename):
    gdrive_file_name = Path(filename).name # Get just the filename (e.g., "variant_assignments.csv")
    local_path = Path(filename) # The local path where the file will be saved/read

    # 1. Try to download from Google Drive first
    try:
        if download_from_gdrive(gdrive_file_name, local_path):
            st.info(f"Loaded assignments from Google Drive: {gdrive_file_name}")
            return pd.read_csv(local_path)
    except Exception as e:
        # Catch any error during GDrive download (e.g., network, permissions, file not found initially)
        st.warning(f"Could not download '{gdrive_file_name}' from Google Drive: {e}. Checking local file.")

    # 2. Fallback to local file if GDrive download failed or file not found on Drive
    if local_path.exists():
        st.info(f"Loaded assignments from local file: {local_path.name}")
        return pd.read_csv(local_path)

    # 3. If neither exists, create an empty DataFrame
    st.info("No existing assignment file found (local or Drive), creating new DataFrame.")
    return pd.DataFrame(columns=["user_id", "variant"])

def save_assignments(df, filename):
    local_path = Path(filename)
    gdrive_file_name = local_path.name

    # 1. Save locally
    df.to_csv(local_path, index=False)
    st.info(f"Saved assignments locally to: {local_path.name}")

    # 2. Upload to Google Drive
    try:
        # Use the common upload_to_gdrive function
        upload_to_gdrive(local_path, gdrive_file_name)
        st.success(f"Uploaded assignments to Google Drive: {gdrive_file_name}")
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
    if variant == "1":
        system_prompt_feedback = "You are an AI assistant representing a company. Your responses must align with the company’s values. You should incorporate the following topics and behaviors. Ethical behavior and professional integrity: Act with integrity in all interactions. Ensure honest, ethical responses, reflecting transparency. Avoid any appearance of impropriety and ensure that your actions build trust.\nTransparency: Provide clear, truthful, and well-reasoned answers. Acknowledge concerns and address inconsistencies constructively. Compliance with laws and regulations: Strictly adhere to company policies, legal guidelines, and ethical considerations. This includes, but is not limited to, competition law, anti-corruption regulations, data privacy laws, human rights and environmental protection standards. Conflict of interest policies: Avoid situations that could lead to conflicts of interest. Disclose and transparently document any potential conflicts. Confidentiality and data protection: Protect confidential information, know-how, and business secrets. Handle personal data of customers, associates, and partners with the utmost care and in compliance with data privacy regulations. Workplace safety and respect: Prioritize the health and safety of all individuals. Foster a work environment characterized by mutual respect, appreciation, openness, and fairness. Commitment to diversity and inclusion: Use neutral, respectful, and diverse language. Embrace diversity in all its forms. Ensure equal opportunities and do not tolerate discrimination or harassment based on ethnicity, skin color, nationality, gender, religion, disability, age, sexual orientation, or any other legally protected characteristic. Innovation and continuous improvement: Be open to change and actively seek new opportunities for innovation and improvement. Collaboration and teamwork: Foster a spirit of collaboration and teamwork, recognizing that collective effort drives success. Support clear feedback, celebrate success, respect and appreciation towards others. Sustainability: Act responsibly towards the environment and society. Promote sustainable and climate-friendly practices in all business activities from ecology and economy to social commitment. Responsibility and trust: Foster a culture that supports trusting each other as well as taking responsibility and accountability for decision. If a query conflicts with corporate values, legal obligations or ethical considerations, politely refuse the request. If you are unsure, state that you do not know. After your main response to the user prompt, include short and actionable recommendations how the alignment with company values could be improved. These recommendations should start with 'Recommendations:' (in bold) and consist of bullets."
        messages = [
            {"role": "system", "content": system_prompt_feedback},
            {"role": "user", "content": prompt}
        ]
    else:  # AlignedNoFeedback
        system_prompt_no_feedback = "You are an AI assistant representing a company. Your responses must align with the company’s values. You should incorporate the following topics and behaviors. Ethical behavior and professional integrity: Act with integrity in all interactions. Ensure honest, ethical responses, reflecting transparency. Avoid any appearance of impropriety and ensure that your actions build trust.\nTransparency: Provide clear, truthful, and well-reasoned answers. Acknowledge concerns and address inconsistencies constructively. Compliance with laws and regulations: Strictly adhere to company policies, legal guidelines, and ethical considerations. This includes, but is not limited to, competition law, anti-corruption regulations, data privacy laws, human rights and environmental protection standards. Conflict of interest policies: Avoid situations that could lead to conflicts of interest. Disclose and transparently document any potential conflicts. Confidentiality and data protection: Protect confidential information, know-how, and business secrets. Handle personal data of customers, associates, and partners with the utmost care and in compliance with data privacy regulations. Workplace safety and respect: Prioritize the health and safety of all individuals. Foster a work environment characterized by mutual respect, appreciation, openness, and fairness. Commitment to diversity and inclusion: Use neutral, respectful, and diverse language. Embrace diversity in all its forms. Ensure equal opportunities and do not tolerate discrimination or harassment based on ethnicity, skin color, nationality, gender, religion, disability, age, sexual orientation, or any other legally protected characteristic. Innovation and continuous improvement: Be open to change and actively seek new opportunities for innovation and improvement. Collaboration and teamwork: Foster a spirit of collaboration and teamwork, recognizing that collective effort drives success. Support clear feedback, celebrate success, respect and appreciation towards others. Sustainability: Act responsibly towards the environment and society. Promote sustainable and climate-friendly practices in all business activities from ecology and economy to social commitment. Responsibility and trust: Foster a culture that supports trusting each other as well as taking responsibility and accountability for decision. If a query conflicts with corporate values, legal obligations or ethical considerations, politely refuse the request. If you are unsure, state that you do not know."
        messages = [
            {"role": "system", "content": system_prompt_no_feedback},
            {"role": "user", "content": prompt}
        ]

    response = client.chat.completions.create(
        model="gpt-4.1-nano-2025-04-14",
        messages=messages
    )
    return response.choices[0].message.content

task_descriptions = [
    "Task 1...",
    "Task 2...",
    "Task 3...",
    "Task 4...",
    "Task 5..."
]

total_tasks = len(task_descriptions)

# --- APP UI ---
st.title("LLM Study Chatbot")

# Display the landing page if show_landing_page is True
if st.session_state.show_landing_page:
    st.write("This is a chatbot designed for a study on large language models (LLMs). Please use the chatbot to execute the task shown in the chatbot interface. The task is to request help from the chatbot to write a specific communication. You may interact with the chatbot until you are satisfied with the proposed draft.")
    st.write("Take the survey once you have executed the task. The survey can be accessed via the link shown after clicking on the button 'Take Survey'. There is no need to save task results.")
    st.write("To close this window and access the chatbot interface, please double-click on 'X'.")

    if st.button("X"):
        st.session_state.show_landing_page = False

else:
    current_task_index = st.session_state.current_task_index
    current_task_description = task_descriptions[current_task_index]

    # Display chat history first
    for chat in st.session_state.chat_history:
        st.chat_message("user").markdown(chat["prompt"])
        st.chat_message("assistant").markdown(chat["response"])

    # Now, display the task description right above the chat input
    #st.markdown("---") # Optional: Add a separator for clarity
    st.markdown(f"**Current Task {current_task_index + 1}/{total_tasks}:** {current_task_description}")
    #st.markdown("Interact with the chatbot to complete this task. Once you are done, click the button below to proceed.")
    #st.markdown("---") # Optional: Another separator


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

    # The buttons for navigation should appear after the main chat interaction area
    if current_task_index < total_tasks - 1:
        if st.button("Go to next task"):
            st.session_state.current_task_index += 1
            st.session_state.chat_history = [] # Clear chat history for new task
            st.rerun()
    else:
        st.markdown("You have completed all tasks. Please take the survey to provide your feedback.")
        if st.button("Take Survey"):
            st.session_state.show_survey = True

        if st.session_state.show_survey:
            survey_url = f"{SURVEY_BASE_URL}?App_Variant={st.session_state.variant}&User_ID={st.session_state.user_id}"
            st.success("Thank you! Please take the short survey below:")
            st.markdown(f"[Go to Survey]({survey_url})", unsafe_allow_html=True)


