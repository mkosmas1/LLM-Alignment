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
    if os.path.exists(filename):
        return pd.read_csv(filename)
    return pd.DataFrame(columns=["user_id", "variant"])

def save_assignments(df, filename):
    df.to_csv(filename, index=False)

assignments_df = load_assignments(ASSIGNMENTS_FILE)

if "variant" not in st.session_state:
    user_assignment = assignments_df[assignments_df["user_id"] == st.session_state.user_id]

    if not user_assignment.empty:
        st.session_state.variant = user_assignment["variant"].iloc[0]
    else:
        # Assign variant based on least frequent
        variant_counts = assignments_df["variant"].value_counts().reindex(LLM_VARIANTS, fill_value=0)
        least_assigned_variant = variant_counts.idxmin()
        st.session_state.variant = least_assigned_variant

        # Add new assignment and save
        new_assignment = pd.DataFrame({"user_id": [st.session_state.user_id], "variant": [st.session_state.variant]})
        assignments_df = pd.concat([assignments_df, new_assignment], ignore_index=True)
        save_assignments(assignments_df, ASSIGNMENTS_FILE)

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
    st.markdown("---") # Optional: Add a separator for clarity
    st.markdown(f"**Current Task {current_task_index + 1}/{total_tasks}:** {current_task_description}")
    st.markdown("Interact with the chatbot to complete this task. Once you are satisfied, click the button below to proceed.")
    st.markdown("---") # Optional: Another separator

    prompt = st.chat_input("Your message")
    if prompt:
        response = call_llm(prompt, st.session_state.variant)

        # Append to history *before* displaying to ensure it's in order
        st.session_state.chat_history.append({
            "timestamp": datetime.now().isoformat(),
            "user_id": st.session_state.user_id,
            "variant": st.session_state.variant,
            "task_index": st.session_state.current_task_index,
            "prompt": prompt,
            "response": response,
        })
        # Rerun to show the new messages in the history
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

    # --- SAVE LOG TO EXCEL ---
    log_file = Path("chat_logs_all.xlsx")

    # Only write the latest interaction to the log file
    if prompt: # This ensures we only log after a user has prompted and a response received
        latest_chat_entry = st.session_state.chat_history[-1] # Get the very last added entry
        df_to_save = pd.DataFrame([latest_chat_entry]) # Create a DataFrame with only the latest entry

        if log_file.exists():
            with pd.ExcelWriter(log_file, engine='openpyxl', mode='a', if_sheet_exists='overlay') as writer:
                try:
                    existing_df = pd.read_excel(log_file)
                    start_row = len(existing_df) + 1
                except Exception:
                    # Handle cases where file is empty or corrupted, start from 1 (after header)
                    start_row = 1
                    # If the file didn't exist or was unreadable, ensure header is written for the first row
                    df_to_save.to_excel(writer, index=False, header=True, startrow=0)
                    # No return here, allow the single row to be written as it's the first.
                else: # Only write if no exception occurred, meaning existing_df was read
                    df_to_save.to_excel(writer, index=False, header=False, startrow=start_row)
        else: # File does not exist, so write with header
            with pd.ExcelWriter(log_file, engine='openpyxl') as writer:
                df_to_save.to_excel(writer, index=False, header=True) # Write header for new file

    # --- UPLOAD TO GOOGLE DRIVE ---
    # The function definition for upload_to_gdrive should ideally be at the top level of your script,
    # but for a complete replacement of the block, it's included here.
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload

    def upload_to_gdrive(excel_file_path):
        creds = service_account.Credentials.from_service_account_info(st.secrets["gdrive"])
        service = build("drive", "v3", credentials=creds)

        file_name = "chat_logs_all.xlsx"
        folder_id = st.secrets["gdrive"]["folder_id"]

        results = service.files().list(
            q=f"name='{file_name}' and '{folder_id}' in parents",
            fields="files(id)",
            supportsAllDrives=True
        ).execute()
        items = results.get('files', [])

        media = MediaIoBaseUpload(open(excel_file_path, "rb"),
                                  mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                  resumable=True)

        if items:
            file_id = items[0]['id']
            updated_file = service.files().update(
                fileId=file_id,
                media_body=media,
                supportsAllDrives=True
            ).execute()
        else:
            file_metadata = {
                "name": file_name,
                "parents": [folder_id],
                "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            }
            file = service.files().create(
                body=file_metadata,
                media_body=media,
                fields="id",
                supportsAllDrives=True
            ).execute()

    if log_file.exists():
        upload_to_gdrive(str(log_file))

